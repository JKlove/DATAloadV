"""读取器抽象基类——所有格式的读取器都实现本契约.

契约（三方法 + 四类属性）：

- ``read_meta(path)``：**只读文件头**，返回 RecordingMeta。必须快（5–50ms/文件），
  因为批量导入 1500 文件全靠它；绝不能触碰数据本体。
- ``open(path, policy)``：返回完整 Recording（meta + events，按需附带已加载 raw）。
- ``load_raw(path, policy)``：供 Recording.ensure_raw 按 LAZY/PRELOAD 拿 mne 句柄。
- ``sniff(path, head)``：内容嗅探（魔数），扩展名不可信时的兜底判定。

类属性：
- ``reader_id``：注册键（如 "edf"）
- ``extensions``：接管的扩展名（含点，小写）
- ``lazy_capable``：该格式 mne 是否支持按窗口懒读（决定 recommended_policy）
- ``requires_extra``：可选依赖名（"neo"/"pynwb"…）；import 失败时注册表跳过该读取器

新增格式 = 继承本类 + 实现三方法 + @register_reader 装饰，零其他改动。
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Optional

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta


class ScanError(Exception):
    """导入扫描中单文件失败（不中断整体扫描，进错误表）.

    ``message`` 面向用户，必须中文、可操作（说清缺什么/该怎么修）。
    """

    def __init__(self, path: str, reader_id: str, message: str) -> None:
        super().__init__(message)
        self.path = path
        self.reader_id = reader_id
        self.message = message


class BaseReader(ABC):
    """一种数据格式的读取器."""

    reader_id: ClassVar[str] = ""
    extensions: ClassVar[tuple[str, ...]] = ()
    lazy_capable: ClassVar[bool] = True
    requires_extra: ClassVar[Optional[str]] = None  # None=无第三方依赖

    # ------------------------------------------------------------------ 抽象

    @abstractmethod
    def read_meta(self, path: Path) -> RecordingMeta:
        """仅解析文件头，返回元数据（快、无数据 IO）."""

    @abstractmethod
    def load_raw(self, path: Path, policy: LoadPolicy):
        """按策略加载 mne Raw（PRELOAD 时整载，LAZY 时 preload=False）."""

    # ------------------------------------------------------------------ 默认实现

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        """打开文件返回 Recording（meta + events；数据按需）.

        默认流程：read_meta → 构造空/头事件表 → 按需 ensure_raw。
        事件需特殊解析的格式（GDF 码表、.edf.event 边车）覆盖本方法。
        """
        meta = self.read_meta(path)
        events = EventTable()
        rec = Recording(meta, events, self)
        if policy is not LoadPolicy.HEADER_ONLY:
            raw = rec.ensure_raw(policy)
            if len(events) == 0 and getattr(raw, "annotations", None) is not None:
                rec.events = EventTable.from_mne_annotations(raw)
                meta.n_events = len(rec.events)
                meta.event_summary = rec.events.codes_summary()
        return rec

    def sniff(self, path: Path, head: bytes) -> bool:  # noqa: ARG002 - head 由子类用
        """内容嗅探：默认仅信任扩展名（多数格式魔数检查在 sniffing.py 统一做）."""
        return path.suffix.lower() in self.extensions

    # ------------------------------------------------------------------ 共用工具

    def filename_entities(self, path: Path) -> dict[str, Optional[str]]:
        """从文件名猜 BIDS 风格实体（subject/run/task），猜不出值为 None.

        已知模式（按需扩充）：
        - BCI-IV 2a/2b：``A01T.gdf`` → subject=A01, task=T（T=训练/E=评估）
        - BCI-IV 1/4：``sub1_comp.mat`` → subject=sub1
        - PhysioNet：``S001R01.edf`` → subject=S001, run=R01
        """
        name = path.stem
        out: dict[str, Optional[str]] = {"subject": None, "session": None, "run": None, "task": None}
        m = re.fullmatch(r"([A-Za-z]\d{2})([TE])(?:\.cdt)?", name)  # BCI 2a/2b
        if m:
            out["subject"], out["task"] = m.group(1), {"T": "train", "E": "eval"}[m.group(2)]
            return out
        m = re.fullmatch(r"(sub\d+).*", name)  # BCI 1/4 mat
        if m:
            out["subject"] = m.group(1)
            return out
        m = re.fullmatch(r"(S\d{3})(R\d{2})", name)  # PhysioNet EEGMMIDB
        if m:
            out["subject"], out["run"] = m.group(1), m.group(2)
            return out
        return out

    def common_meta_fields(self, path: Path, fmt: str) -> dict:
        """RecordingMeta 的公共字段（实体猜测 + 文件属性），返回 dict 而非实例.

        为什么不直接构造 RecordingMeta：通道数/采样率等必填字段只有子类
        读完头才知道——返回 dict 让子类 ``RecordingMeta(**self.common_meta_fields(...), n_channels=..., ...)``
        一次构造成功，避免"先造半成品再补字段"的中间态。
        """
        stat = path.stat()
        ents = self.filename_entities(path)
        return {
            "path": str(path),
            "format": fmt,
            "reader_id": self.reader_id,
            "subject": ents["subject"],
            "session": ents["session"],
            "run": ents["run"],
            "task": ents["task"],
            "file_size": stat.st_size,
            "mtime": stat.st_mtime,
        }
