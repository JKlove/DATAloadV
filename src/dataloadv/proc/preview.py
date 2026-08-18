"""预览 Recording 构造——把处理后的 ctx.raw 包装成浏览 tab 可用的 Recording.

复用而非新写浏览器：``PreviewReader`` 是一个"数据已在内存"的读取器，
``load_raw`` 直接返回处理副本，浏览器的窗口读取/峰值抽取/事件条全部照常工作。

注意：预览 Recording **不入工作区、不入注册表**（不接管任何扩展名），
生命周期 = 预览 tab 的生命周期（关闭 tab 即 unload 释放内存）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from uuid import uuid4

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from ..io.base import BaseReader
from .context import ProcessingContext


class PreviewReader(BaseReader):
    """持有已处理 raw 的内存读取器（仅供预览，绝不注册）."""

    reader_id = "preview"
    extensions: tuple[str, ...] = ()
    lazy_capable = False  # 数据已物化，没有"按窗口读盘"的需求

    def __init__(self, raw, meta: RecordingMeta) -> None:
        self._raw = raw
        self._meta = meta

    def read_meta(self, path: Path) -> RecordingMeta:  # noqa: ARG002 - path 不用
        return self._meta

    def load_raw(self, path: Path, policy: LoadPolicy):  # noqa: ARG002
        return self._raw


def make_preview_recording(source: Recording, ctx: ProcessingContext) -> Recording:
    """把处理后的 ctx.raw 包装成可开浏览 tab 的预览 Recording.

    meta 复制自源录制（保留 subject/事件等），但 rec_id 换新（同一文件可开
    多个不同管线的预览 tab 互不覆盖），通道/采样率/时长按处理结果更新。
    :raises ValueError: ctx 不在 raw 阶段（分段结果请走 EpochsPreviewView）
    """
    if ctx.stage != "raw" or ctx.raw is None:
        raise ValueError("预览浏览 tab 仅支持连续数据（raw）阶段；分段结果请用分段预览视图")
    raw = ctx.raw
    summary = " → ".join(h["step"] for h in ctx.history)  # 步骤 id 链，如 bandpass → notch
    meta = source.meta.model_copy(update={
        "rec_id": uuid4().hex,
        "format": "预览",
        "n_channels": len(raw.info["ch_names"]),
        "channel_names": list(raw.info["ch_names"]),
        "channel_types": list(raw.get_channel_types()),
        "sfreq": float(raw.info["sfreq"]),
        "duration_s": raw.n_times / raw.info["sfreq"],
        "n_events": len(ctx.events),
        "event_summary": ctx.events.codes_summary(),
        "notes": f"处理预览（{summary or '无步骤'}）",
    })
    # 事件表直接共享（预览只读它；分段等步骤也不改 EventTable 本身）
    return Recording(meta, ctx.events, PreviewReader(raw, meta))
