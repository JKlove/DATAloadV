"""基于 MNE 的读取器（EDF 先行；其余 MNE 原生格式 M2 补全）.

EdfReader 的两个实测依据（2026-08-18，dlv 环境 mne 1.12.0）：
1. 羊 EDF 注释/TAL 通道含非 UTF-8 字节（0xc6），默认编码抛
   "Encountered invalid byte in at least one annotations channel"——
   需 encoding="latin1" 重试（pipelineMotor formats.py 同款解法）。
2. PhysioNet EEGMMIDB 的 EDF **内嵌注释即完整任务序列**
   （S001R03: T0×15 / T1×8 / T2×7），配套 .edf.event 边车为 WFDB
   格式的冗余副本——故不做边车解析（原计划有，实证后取消，见 review.md）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import mne

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader
from .registry import register_reader

logger = logging.getLogger(__name__)
mne.set_log_level("ERROR")

# mne 对非 UTF-8 注释通道的报错文案片段（用于识别"该用 latin1 重试"的场景）
_LATIN1_HINT = "invalid byte"


def _read_edf_robust(path: Path | str, **kwargs):
    """读 EDF：默认编码失败且提示 invalid byte 时自动 latin1 重试.

    path 兼容 str（Recording.meta.path 存的是字符串）。
    """
    path = Path(path)
    try:
        return mne.io.read_raw_edf(str(path), stim_channel="auto", verbose="ERROR", **kwargs)
    except Exception as e:  # noqa: BLE001 - mne 对此场景抛通用 Exception
        if _LATIN1_HINT in str(e):
            logger.info("EDF 含非 UTF-8 注释，改用 latin1 读取：%s", path.name)
            return mne.io.read_raw_edf(
                str(path), stim_channel="auto", encoding="latin1", verbose="ERROR", **kwargs
            )
        raise


@register_reader
class EdfReader(BaseReader):
    """EDF / EDF+ 读取器（sheep 动物数据与 PhysioNet 临床 EEG 的格式）."""

    reader_id = "edf"
    extensions = (".edf",)
    lazy_capable = True  # mne EDF 支持按窗口读（preload=False）

    def read_meta(self, path: Path) -> RecordingMeta:
        """仅解析头（preload=False 时 mne 只读头与注释，不搬数据）."""
        raw = _read_edf_robust(path, preload=False)
        events = EventTable.from_mne_annotations(raw)
        return self._meta_from_raw(path, raw, events)

    def load_raw(self, path: Path, policy: LoadPolicy):
        """按策略加载：PRELOAD 整载 / LAZY 仅句柄."""
        preload = policy is not LoadPolicy.LAZY
        return _read_edf_robust(path, preload=preload)

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        """打开 EDF：头 + 注释一次读出（注释在头里，不增加数据 IO）."""
        raw = _read_edf_robust(path, preload=False)
        events = EventTable.from_mne_annotations(raw)
        meta = self._meta_from_raw(path, raw, events)
        rec = Recording(meta, events, self)
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec

    def _meta_from_raw(self, path: Path, raw, events: EventTable) -> RecordingMeta:
        """由 mne 头信息一次构造完整 RecordingMeta."""
        return RecordingMeta(
            **self.common_meta_fields(path, "EDF"),
            n_channels=len(raw.ch_names),
            channel_names=list(raw.ch_names),
            channel_types=list(raw.get_channel_types()),
            sfreq=float(raw.info["sfreq"]),
            duration_s=raw.n_times / raw.info["sfreq"],
            n_events=len(events),
            event_summary=events.codes_summary(),
        )
