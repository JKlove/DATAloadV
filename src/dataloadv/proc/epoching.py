"""事件分段步骤（EpochingStep）——把连续 raw 按 EventTable 事件切成 epochs.

阶段翻转：本步骤执行后 ``ctx.stage`` 从 "raw" 变为 "epochs"，``ctx.raw``
释放（内存让位给 epochs）。后续仅接受 applies_to 含 "epochs" 的步骤。

事件来源：``ctx.events``（读取器解析好的 EventTable，GDF 文件已带中文标签；
code 为字符串，如 "769"/"T1"/"left"）。空 event_codes = 全部事件类型。
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import mne
import numpy as np
from pydantic import BaseModel, Field, model_validator

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class EpochingParams(BaseModel):
    """分段参数.

    ``baseline``：基线校正窗口 ``(起, 止)``（秒，相对事件 onset；None=用 tmin/0）。
    传 None 整体表示**不做**基线校正。
    ``reject_uv``：峰峰值剔除阈值（µV），超出该幅度的分段被丢弃；None=不剔除。
    """

    event_codes: list[str] = Field(
        default=[], title="事件码（空=全部）",
        description="要保留的事件码，逗号分隔（如 769,770,771,772）；留空=全部事件",
    )
    tmin: float = Field(
        default=-1.0, title="段起点（相对事件）", ge=-60.0, le=0.0,
        json_schema_extra={"unit": "s", "decimals": 2},
    )
    tmax: float = Field(
        default=4.0, title="段终点（相对事件）", gt=0.0, le=120.0,
        json_schema_extra={"unit": "s", "decimals": 2},
    )
    baseline: Optional[tuple[Optional[float], Optional[float]]] = Field(
        default=(None, 0.0), title="基线窗口",
        description="格式：起,止（秒，相对事件；可用 无 表示开放端），如 无,0 或 -0.5,0；"
                    "整项填 无 表示不做基线校正",
    )
    reject_uv: Optional[float] = Field(
        default=None, title="峰峰值剔除阈值",
        description="分段内任一数据通道峰峰值超过该值（µV）则丢弃该段；留空=不剔除",
        json_schema_extra={"unit": "µV", "min": 1.0, "max": 10000.0, "decimals": 0},
    )

    @model_validator(mode="after")
    def _check_window(self) -> "EpochingParams":
        if self.tmin >= self.tmax:
            raise ValueError(f"段起点（{self.tmin}）必须早于段终点（{self.tmax}）")
        return self


@register_step
class EpochingStep(ProcStep):
    """按事件分段（mne.Epochs），raw → epochs 阶段翻转."""

    step_id = "epoching"
    label_zh = "事件分段"
    params_cls = EpochingParams
    applies_to = frozenset({"raw"})  # 只能对连续数据分段

    def apply(self, ctx: ProcessingContext, params: EpochingParams) -> ProcessingContext:
        raw = ctx.raw
        ev = ctx.events
        if len(ev) == 0:
            raise StepError("该录制没有事件标注，无法分段（CSV/TXT、ds4 等无事件数据不适用本步骤）")
        codes_all = sorted(set(ev.code))
        keep = [c for c in codes_all if not params.event_codes or c in set(params.event_codes)]
        if not keep:
            raise StepError(
                f"事件码 {params.event_codes} 在本录制中不存在。实际可用事件码：{'、'.join(codes_all)}"
            )
        keep_set = set(keep)
        idx = [i for i, c in enumerate(ev.code) if c in keep_set]
        sfreq = raw.info["sfreq"]
        # 事件表 → mne events 三列数组 [样本序号, 前一事件值(0), 事件码整数]
        samples = np.round(np.asarray(ev.onset)[idx] * sfreq).astype(np.int64)
        codes = [ev.code[i] for i in idx]
        order = np.argsort(samples, kind="stable")  # mne 要求按样本升序
        samples, codes = samples[order], [codes[j] for j in order]
        event_id = {c: i + 1 for i, c in enumerate(keep)}  # 任意稳定整数映射
        events = np.column_stack([samples, np.zeros(len(samples), dtype=np.int64),
                                  np.array([event_id[c] for c in codes], dtype=np.int64)])
        # 峰峰值剔除阈值（µV→伏特）按在场的可剔除通道类型建 dict；misc（手套等）不参与
        reject = None
        if params.reject_uv is not None:
            present = set(raw.get_channel_types())
            reject = {t: params.reject_uv * 1e-6 for t in ("eeg", "ecog", "seeg", "meg") if t in present} or None
        baseline = tuple(params.baseline) if params.baseline else None
        # 边界修正：tmin=0 时基线 (None, 0) 只含 1 个采样点，mne 要求显式 (0, 0)
        if baseline is not None and baseline[0] is None and baseline[1] == 0.0 and params.tmin == 0.0:
            baseline = (0.0, 0.0)
        epochs = mne.Epochs(
            raw, events, event_id=event_id, tmin=params.tmin, tmax=params.tmax,
            baseline=baseline, reject=reject, preload=True,
            reject_by_annotation=True, verbose="ERROR", on_missing="ignore",
            event_repeated="drop",  # 同一样本刻多事件（如 32766+768 同点）保留首个
        )
        n_want = len(events)
        if len(epochs) == 0:
            raise StepError(
                f"分段结果为空（候选事件 {n_want} 个全部被丢弃）。常见原因：段窗口"
                f"[{params.tmin}, {params.tmax}]s 超出数据边界、或剔除阈值过小"
            )
        # 阶段翻转：raw 释放，后续步骤面向 epochs
        ctx.epochs, ctx.raw, ctx.stage = epochs, None, "epochs"
        id_to_code = {v: k for k, v in event_id.items()}  # 整数码 → 原始事件码
        kept = Counter(id_to_code[int(c)] for c in epochs.events[:, -1])
        ctx.log(f"分段完成：{len(epochs)}/{n_want} 段，每段 {(params.tmax - params.tmin):g}s；"
                f"按类：{'，'.join(f'{k}×{v}' for k, v in sorted(kept.items()))}")
        return ctx
