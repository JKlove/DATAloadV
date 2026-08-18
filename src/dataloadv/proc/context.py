"""ProcessingContext——预处理管线的数据载体（一条管线从头到尾持有它）.

职责（刻意保持"哑容器 + 少量工具"）：
- 持有当前数据对象：``raw``（mne Raw，连续阶段）或 ``epochs``（mne Epochs，分段阶段）
- ``stage`` 声明当前处于哪个阶段（epoching 步骤会把它从 raw 翻转为 epochs）
- ``events``：原始 EventTable（分段步骤的输入；在 raw 阶段仅透传）
- ``history`` / ``logs``：已执行步骤（序列化 dict）与中文日志（预览面板/批处理报告展示）

预览的内存模型：``from_recording`` 会 ``raw.copy()``——预览/批处理在**副本**上
操作，原始浏览数据不受影响；代价是内存翻倍（v1 接受；大文件预览前注意 LoadedRawCache）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from ..core.recording import EventTable, LoadPolicy, Recording

logger = logging.getLogger(__name__)


@dataclass
class ProcessingContext:
    """一条预处理管线的执行上下文."""

    raw: Optional[object] = None      # mne.io.BaseRaw（stage=="raw" 时非 None）
    epochs: Optional[object] = None   # mne.Epochs（stage=="epochs" 时非 None）
    stage: str = "raw"                # "raw" | "epochs"
    events: EventTable = field(default_factory=EventTable)
    history: list[dict] = field(default_factory=list)   # 已执行步骤 [{step, params}]
    _logs: list[str] = field(default_factory=list)      # 中文日志（log() 追加）

    # ------------------------------------------------------------------ 构造

    @classmethod
    def from_recording(cls, rec: Recording) -> "ProcessingContext":
        """从打开的 Recording 建上下文（预览/批处理管线的起点）.

        - 强制 PRELOAD：mne 滤波/分段都需要整载（坑 #3，见 HANDOFF.md）
        - ``raw.copy()``：后续步骤全在副本上，原始浏览数据不动
        :raises ValueError: 数据加载失败（调用方转中文提示）
        """
        raw = rec.ensure_raw(LoadPolicy.PRELOAD)
        ctx = cls(raw=raw.copy(), events=rec.events)
        ctx.log(f"已载入 {rec.meta.filename}（{rec.meta.n_channels} 导 / "
                f"{rec.meta.sfreq:g} Hz / {rec.meta.duration_s:.1f} s），在副本上处理")
        return ctx

    # ------------------------------------------------------------------ 工具

    @property
    def sfreq(self) -> float:
        """当前采样率（raw 与 epochs 的 info 里都有）."""
        obj = self.raw if self.stage == "raw" else self.epochs
        return float(obj.info["sfreq"])

    @property
    def ch_names(self) -> list[str]:
        obj = self.raw if self.stage == "raw" else self.epochs
        return list(obj.info["ch_names"])

    def log(self, message: str) -> None:
        """追加一行中文日志（预览面板逐条显示）."""
        logger.info("[管线] %s", message)
        self._logs.append(message)

    @property
    def logs(self) -> list[str]:
        return list(self._logs)
