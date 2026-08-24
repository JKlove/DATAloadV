"""基于 MNE 的读取器家族（EDF/BDF/GDF/BrainVision/FIF/EEGLAB/CNT/EGI）.

结构：``_MneRawReader`` 模板基类实现"读头→建 meta→按策略载数据"的通用
流程，每格式子类只声明差异（mne 函数、扩展名、事件后处理钩子）。
新增一种 mne 原生格式 = 追加一个 ~10 行的子类。

实测依据（2026-08-18，dlv 环境 mne 1.12.0）：
1. 羊 EDF 注释/TAL 通道含非 UTF-8 字节（0xc6），默认编码抛
   "Encountered invalid byte in at least one annotations channel"——
   需 encoding="latin1" 重试（pipelineMotor formats.py 同款解法）。
2. PhysioNet EDF 内嵌注释完整，.edf.event 边车为冗余副本，不解析。
3. BCI-IV 2a/2b GDF：事件是 annotations，description 为 "769" 这类
   数字串（A01T: 769×72/770×72/771×72/772×72…）——经 event_maps
   翻译成中文标签（码表来自官方 desc_2a.pdf / desc_2b.pdf 原文）。
4.（2026-08-24）mne 公共入口 read_raw_edf/bdf/gdf 的 _check_args 按扩展名
   硬拒绝（"Only BDF files are supported, got edf"），但 file-like 对象
   完全绕过该检查（read_raw_bdf 自 MNE 1.10 官方支持 file-like，edf/gdf
   同路径，1.12 实测可用）——扩展名与内容不符时（sheep 系列 .edf 实为
   BDF）传文件对象走公共入口重读。代价：file-like 要求整载（preload=True），
   仅误标文件承担。见 _read_mne_robust。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar, Callable, Optional

import mne

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .event_maps import apply_gdf_labels
from .registry import register_reader

logger = logging.getLogger(__name__)
mne.set_log_level("ERROR")

# mne 对非 UTF-8 注释通道的报错文案片段（用于识别"该用 latin1 重试"的场景）
_LATIN1_HINT = "invalid byte"
# mne _check_args 扩展名硬检查的报错文案片段（识别"该绕过包装层"的场景）
_EXT_HINT = "files are supported"


def _detach_file_handles(raw, path_str: str):
    """file-like 读取后剥离 mne 内部残留的文件对象引用（两处，缺一不可）.

    mne 会把 file-like input 存进 ``_raw_extras[*]["blob"]``（懒读数据用）
    和 ``_init_kwargs["input_fname"]``——整载后这两处引用已无用途，但残留
    会让 raw.copy()/deepcopy 抛 "cannot pickle '_io.BufferedReader'"
    （2026-08-24 e2e_m3 预览链路实测，只剥 blob 仍炸）。剥离后 raw 为纯
    内存对象，复制/跨线程传递安全（架构规则 #3）；init_kwargs 回填真实
    路径字符串，保住 mne repr 等场景的可用性。
    """
    for extra in getattr(raw, "_raw_extras", None) or []:
        if isinstance(extra, dict) and hasattr(extra.get("blob"), "read"):
            extra["blob"] = None
    kw = getattr(raw, "_init_kwargs", None)
    if isinstance(kw, dict) and hasattr(kw.get("input_fname"), "read"):
        kw["input_fname"] = path_str
    return raw


def _read_mne_robust(read_fn: Callable, path: Path, **kwargs):
    """mne 公共入口 + 两类内容级回退的统一读取助手（EDF/BDF/GDF 共用）.

    1. 扩展名与内容不符（如 \xffBIOSEMI 头的 BDF 存成 .edf）：公共入口的
       _check_args 抛 NotImplementedError——改传 file-like 对象重读同一
       公共入口（_check_args 对 file-like 跳过扩展名检查；read_raw_bdf
       自 MNE 1.10 官方支持 file-like，edf/gdf 同路径，不直接实例化
       Raw* 构造器）。代价是 file-like 必须整载（preload=True）——仅误标
       文件承担，正常扩展名路径不受影响；格式正确性已由 registry 魔数
       派发保证。
    2. 非 UTF-8 注释通道（invalid byte）：encoding="latin1" 重读（真
       latin1 老文件场景；羊数据 M1 时触发的"latin1"实为按 EDF 误解码
       BDF 的副产品，M6.5 已翻案，回退行为另有合成回归测试锁定）。

    path 兼容 str（Recording.meta.path 存的是字符串）。
    """
    p = str(path)
    name = Path(p).name
    try:
        return read_fn(p, **kwargs)
    except NotImplementedError as e:
        if _EXT_HINT not in str(e):
            raise
        logger.info("扩展名与文件内容不符，改用文件对象绕过 mne 扩展名检查：%s", name)
        full = dict(kwargs, preload=True)  # file-like 强制整载（mne _check_args）
        with open(p, "rb") as fh:
            try:
                return _detach_file_handles(read_fn(fh, **full), p)
            except Exception as e2:  # noqa: BLE001 - file-like 路径同样可能撞编码问题
                if _LATIN1_HINT not in str(e2):
                    raise
                logger.info("含非 UTF-8 注释，改用 latin1 读取：%s", name)
                fh.seek(0)  # 读取指针已前移，回卷到文件头供 latin1 重读
                return _detach_file_handles(read_fn(fh, encoding="latin1", **full), p)
    except Exception as e:  # noqa: BLE001 - mne 对此场景抛通用 Exception
        if _LATIN1_HINT not in str(e):
            raise
        logger.info("含非 UTF-8 注释，改用 latin1 读取：%s", name)
        return read_fn(p, encoding="latin1", **kwargs)


class _MneRawReader(BaseReader):
    """mne.io.read_raw_* 家族的读取器模板.

    子类需声明（类属性）：
    - ``_fmt``：RecordingMeta.format 展示名（如 "GDF"）
    - ``_read_fn``：mne 读取函数（如 mne.io.read_raw_gdf）
    - ``_extra``：固定传给 _read_fn 的额外 kwargs（如 stim_channel）
    - ``_robust``：True 时 _read 走 _read_mne_robust（扩展名不符时
      file-like 绕过 + latin1 回退）；EDF 家族三格式适用，其余格式
      不声明则保持直接调 _read_fn

    可覆盖的钩子：
    - ``_read``：读取入口（FIF 覆盖它加 MaxShield/分段文件处理）
    - ``events_from_raw``：事件表构建（默认 mne annotations 直转；GDF 覆盖它
      翻译数字码为中文标签）
    """

    _fmt = ""
    _read_fn: ClassVar[Optional[Callable]] = None
    _robust: ClassVar[bool] = False
    _extra: ClassVar[dict] = {}

    # ------------------------------------------------------------------ 钩子
    def _read(self, path: Path, preload: bool):
        """默认读取路径：_read_fn(path, **_extra, preload=..., verbose=...).

        声明 _robust 时改走 _read_mne_robust（内容级回退见其 docstring）。
        """
        if self._read_fn is None:
            raise NotImplementedError(f"{type(self).__name__} 未声明 _read_fn")
        if self._robust:
            return _read_mne_robust(
                self._read_fn, path,
                preload=preload, verbose="ERROR", **self._extra,
            )
        return self._read_fn(str(path), **self._extra, preload=preload, verbose="ERROR")

    def events_from_raw(self, raw) -> EventTable:
        """从已构造的 raw 抽事件表（默认 annotations 直转）."""
        return EventTable.from_mne_annotations(raw)

    # ------------------------------------------------------------------ 契约
    def read_meta(self, path: Path) -> RecordingMeta:
        """仅解析头（preload=False 时 mne 只读头与注释，不搬数据）."""
        raw = self._read(path, preload=False)
        events = self.events_from_raw(raw)
        return self._meta_from_raw(path, raw, events)

    def load_raw(self, path: Path, policy: LoadPolicy):
        """按策略加载：PRELOAD 整载 / LAZY 仅句柄."""
        return self._read(path, preload=policy is not LoadPolicy.LAZY)

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        """打开：头 + 事件一次读出（事件在头里，不增加数据 IO）."""
        raw = self._read(path, preload=False)
        events = self.events_from_raw(raw)
        meta = self._meta_from_raw(path, raw, events)
        rec = Recording(meta, events, self)
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec

    # ------------------------------------------------------------------ 共用
    def _meta_from_raw(self, path: Path, raw, events: EventTable) -> RecordingMeta:
        """由 mne 头信息一次构造完整 RecordingMeta（模板基类统一实现）."""
        return RecordingMeta(
            **self.common_meta_fields(path, self._fmt),
            n_channels=len(raw.ch_names),
            channel_names=list(raw.ch_names),
            channel_types=list(raw.get_channel_types()),
            sfreq=float(raw.info["sfreq"]),
            duration_s=raw.n_times / raw.info["sfreq"],
            n_events=len(events),
            event_summary=events.codes_summary(),
        )


@register_reader
class EdfReader(_MneRawReader):
    """EDF / EDF+（PhysioNet 临床 EEG 等）——latin1 自动回退.

    注意：内容为 BDF 的 .edf 文件不会到这里——registry 魔数派发会直接
    给 BdfReader（sheep 系列即此情况）。
    """

    reader_id = "edf"
    extensions = (".edf",)
    _fmt = "EDF"
    _read_fn = staticmethod(mne.io.read_raw_edf)
    _robust = True
    _extra = {"stim_channel": "auto"}


@register_reader
class BdfReader(_MneRawReader):
    """BDF / BDF+（Biosemi，临床 EEG 常见；sheep 系列实为 BDF 内容的 .edf）.

    扩展名不是 .bdf 时 mne 公共入口会拒绝——_read_mne_robust 自动改传
    file-like 对象走同一公共入口（不直接实例化 RawBDF 构造器）。
    """

    reader_id = "bdf"
    extensions = (".bdf",)
    _fmt = "BDF"
    _read_fn = staticmethod(mne.io.read_raw_bdf)
    _robust = True
    _extra = {"stim_channel": "auto"}


@register_reader
class GdfReader(_MneRawReader):
    """GDF（BCI Competition IV 2a/2b）——数字事件码翻译为中文标签."""

    reader_id = "gdf"
    extensions = (".gdf",)
    _fmt = "GDF"
    _read_fn = staticmethod(mne.io.read_raw_gdf)
    _robust = True

    def events_from_raw(self, raw) -> EventTable:
        """GDF 事件码 → 中文标签（2a/2b 官方码表，见 event_maps.py）."""
        return apply_gdf_labels(EventTable.from_mne_annotations(raw))


@register_reader
class BrainVisionReader(_MneRawReader):
    """BrainVision 三件套（.vhdr 头 + .eeg 数据 + .vmk 标记）.

    只接管 .vhdr（入口文件）；.eeg/.vmk 是数据本体，扫描时按"无读取器
    接管"忽略——绝不能当独立录制导入（会跟 .vhdr 内容重复）。
    """

    reader_id = "brainvision"
    extensions = (".vhdr",)
    _fmt = "BrainVision"
    _read_fn = staticmethod(mne.io.read_raw_brainvision)


@register_reader
class FifReader(_MneRawReader):
    """FIF（MNE 原生；连续数据）.

    分段（Epochs）FIF 与 MaxShield 记录给出明确中文提示而非底层报错。
    """

    reader_id = "fif"
    extensions = (".fif",)
    _fmt = "FIF"
    _read_fn = staticmethod(mne.io.read_raw_fif)

    def _read(self, path: Path, preload: bool):
        try:
            return mne.io.read_raw_fif(str(path), preload=preload, verbose="ERROR")
        except ValueError as e:
            if "poches" in str(e):  # read_epochs 的文件，当前应用只支持连续数据
                raise ScanError(
                    str(path), self.reader_id,
                    "该 FIF 文件存的是分段数据（Epochs），当前版本支持连续录制；"
                    "分段数据请先用其他工具转出原始连续段",
                ) from e
            raise
        except RuntimeError as e:
            # Neuromag MaxShield 记录需显式确认才读（默认拒绝是 mne 的安全行为）
            if "MaxShield" in str(e):
                logger.info("FIF 为 MaxShield 记录，加 allow_maxshield 重读：%s", path.name)
                return mne.io.read_raw_fif(
                    str(path), allow_maxshield=True, preload=preload, verbose="ERROR"
                )
            raise


@register_reader
class EeglabReader(_MneRawReader):
    """EEGLAB .set（指向 .fdt 或内嵌矩阵）."""

    reader_id = "eeglab"
    extensions = (".set",)
    _fmt = "EEGLAB"
    _read_fn = staticmethod(mne.io.read_raw_eeglab)


@register_reader
class CntReader(_MneRawReader):
    """CNT（Neuroscan）."""

    reader_id = "cnt"
    extensions = (".cnt",)
    _fmt = "CNT"
    _read_fn = staticmethod(mne.io.read_raw_cnt)


@register_reader
class EgiReader(_MneRawReader):
    """EGI（.egi 单文件 / .mff 目录包）."""

    reader_id = "egi"
    extensions = (".egi", ".mff")
    _fmt = "EGI"
    _read_fn = staticmethod(mne.io.read_raw_egi)
