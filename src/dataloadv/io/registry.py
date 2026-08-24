"""读取器注册表 + 统一入口（open_file / scan_folder）.

设计：模块级字典 + 类装饰器，刻意不用 entry_points 机制——本地应用无需
插件发现，少一层魔法；新增格式仍只是"继承 BaseReader + 装饰"两步。

解析顺序（open_file / scan_folder 共用）：
1. 魔数嗅探（sniffing.sniff_format）：嗅探出可唯一定位读取器的格式
   （EDF/BDF/GDF/BrainVision）时**以内容为准**派发——扩展名不符记
   warning 但不拦（2026-08-24 实证：data/sheep 系列全是 BDF 内容的
   .edf 文件，按扩展名读 EDF 会把 24-bit 样本按 16-bit 解码，样本数
   虚增 1.5×、数值全部错位）；
2. 嗅探不出（无魔数格式或家族签名 "hdf5"）→ 扩展名精确匹配（快路径）
3. 仍无 → ScanError（中文、可操作）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..core.recording import LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .sniffing import sniff_format

logger = logging.getLogger(__name__)

READER_REGISTRY: dict[str, BaseReader] = {}

# 魔数可唯一定位读取器的格式才参与"内容优先"派发；"hdf5" 是家族签名
# （NWB/Intan rhs/通用 HDF5 同头），细分仍靠扩展名，不参与提升。
_CONTENT_FIRST = frozenset({"edf", "bdf", "gdf", "brainvision"})

# .event 边车等无读取器接管的配套文件：扫描时不报错、不进列表（skipped 计数）


def register_reader(cls: type[BaseReader]) -> type[BaseReader]:
    """类装饰器：把读取器实例注册进全局表（import 即注册）."""
    if not cls.reader_id:
        raise ValueError(f"{cls.__name__} 缺少 reader_id")
    if cls.reader_id in READER_REGISTRY:
        raise ValueError(f"reader_id 重复：{cls.reader_id}")
    if cls.requires_extra:
        # 可选依赖守卫：缺包则跳过注册（应用其余功能不受影响）
        try:
            __import__(cls.requires_extra)
        except ImportError:
            logger.info("可选依赖 %s 缺失，读取器 %s 未启用", cls.requires_extra, cls.reader_id)
            return cls
    READER_REGISTRY[cls.reader_id] = cls()
    return cls


def _readers_for(path: Path) -> list[BaseReader]:
    """按扩展名找候选读取器（可能多个，如 .mat 有 BCI-IV 与通用两个）."""
    ext = path.suffix.lower()
    return [r for r in READER_REGISTRY.values() if ext in r.extensions]


def _dispatch_readers(path: Path) -> tuple[list[BaseReader], bool]:
    """内容优先的读取器派发（open_file 的候选来源）.

    魔数嗅探能唯一定位读取器（_CONTENT_FIRST）时以内容为准——扩展名说
    .edf 但文件头是 \xffBIOSEMI 就派 BDF 读取器，且**不让扩展名候选兜底**
    （内容明确时按扩展名再试只会把 24-bit 样本错位解码成伪数据）。
    嗅探不出（无魔数格式/家族签名）时回退扩展名匹配。

    :returns: (候选读取器列表, 内容与扩展名是否冲突)——冲突时调用方记
        warning，UI 日志面板可见"按什么格式读了"
    """
    sniffed = sniff_format(path)
    if sniffed in _CONTENT_FIRST:
        reader = READER_REGISTRY.get(sniffed)
        if reader is not None:
            mismatch = path.suffix.lower() not in reader.extensions
            return [reader], mismatch
    return _readers_for(path), False


def open_file(path: str | Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
    """打开单个数据文件为 Recording.

    派发见 _dispatch_readers（魔数内容优先，扩展名兜底）。

    :raises ScanError: 无读取器可接 / 候选读取失败（附最后一次原因）
    """
    path = Path(path)
    candidates, mismatch = _dispatch_readers(path)
    if mismatch:
        logger.warning(
            "文件头魔数与扩展名 %s 不符，按 %s 读取（以内容为准）：%s",
            path.suffix or "(无扩展名)", candidates[0].reader_id.upper(), path.name,
        )
    last_err: Exception | None = None
    for reader in candidates:
        try:
            rec = reader.open(path, policy)
            rec.meta.import_source = rec.meta.import_source or str(path.parent)
            return rec
        except Exception as e:  # noqa: BLE001 - 逐候选尝试，全部失败才抛
            last_err = e
            logger.debug("读取器 %s 打开 %s 失败：%s", reader.reader_id, path.name, e)
    if candidates:
        raise ScanError(
            str(path),
            candidates[0].reader_id,
            f"文件无法读取（{path.name}）：{last_err}",
        )
    raise ScanError(str(path), "", f"不支持的格式：{path.suffix or '(无扩展名)'}（{path.name}）")


@dataclass
class ScanItem:
    """扫描成功条目：meta +（若头里就有事件）事件摘要."""

    meta: RecordingMeta


@dataclass
class ScanReport:
    """一次目录扫描的结果：成功条目 + 逐文件错误（绝不因单文件中断）."""

    items: list[ScanItem] = field(default_factory=list)
    errors: list[ScanError] = field(default_factory=list)
    skipped: int = 0  # 按扩展名忽略的非录制文件数
    scanned: int = 0  # 实际尝试解析的文件数

    @property
    def ok(self) -> bool:
        return not self.errors


def scan_folder(
    root: str | Path, recursive: bool = True, progress_cb=None
) -> ScanReport:
    """扫描目录下所有可识别的录制文件，仅解析头（批量导入入口）.

    :param progress_cb: 可选回调 ``cb(done, total, current_name)``，每处理一个
        候选文件调用一次（UI 进度条用；工作线程中调用，UI 侧需经信号转主线程）
    逐文件容错：任何单文件失败进 ``errors``，扫描继续；调用方（UI 的
    导入对话框）负责把错误表展示给用户。
    """
    root = Path(root)
    report = ScanReport()
    it = sorted(p for p in (root.rglob("*") if recursive else root.glob("*")))

    def _is_candidate(p: Path) -> bool:
        """候选 = 有读取器接管的文件，或 EGI .mff 这类"目录即录制"的包."""
        return (p.is_file() or p.suffix.lower() == ".mff") and bool(_readers_for(p))

    # 先数出候选总量（进度分母；只数有读取器接管的）
    candidates = [p for p in it if _is_candidate(p)]
    total = len(candidates)
    for done, path in enumerate(candidates, start=1):
        report.scanned += 1
        if progress_cb is not None:
            try:
                progress_cb(done, total, path.name)
            except Exception:  # noqa: BLE001 - 进度回调绝不影响扫描
                pass
        try:
            rec = open_file(path, LoadPolicy.HEADER_ONLY)
            report.items.append(ScanItem(meta=rec.meta))
        except ScanError as e:
            report.errors.append(e)
        except Exception as e:  # noqa: BLE001 - 扫描器绝不能被单文件异常杀死
            report.errors.append(ScanError(str(path), "", f"意外错误：{e}"))
    # 其余文件（配套索引/图片/边车）统一计 skipped（.mff 目录计入候选口径）
    report.skipped = sum(1 for p in it if p.is_file() or p.suffix.lower() == ".mff") - total
    logger.info(
        "扫描 %s：识别 %d，失败 %d，忽略 %d",
        root, len(report.items), len(report.errors), report.skipped,
    )
    return report
