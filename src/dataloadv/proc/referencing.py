"""重参考步骤（RerefStep）：平均参考或自定义参考电极.

mne ``set_eeg_reference`` 的参数化包装；``ch_type="auto"`` 让 mne 对 EEG/ECoG
数据自动选择参与参考的通道（羊 EDF 与 BCI 数据都在此覆盖范围内）。
"""

from __future__ import annotations

from typing import Literal

import mne
from pydantic import BaseModel, Field, model_validator

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class RerefParams(BaseModel):
    """重参考参数.

    - ``mode="average"``：全部数据通道的平均作为新参考（最常用）
    - ``mode="custom"``：用指定通道作参考（须给出 ``ref_channels``，如耳朵电极）
    """

    mode: Literal["average", "custom"] = Field(default="average", title="参考方式")
    ref_channels: list[str] = Field(
        default=[], title="参考通道（custom 方式用）",
        description="用逗号分隔通道名；仅「参考方式=custom」时生效",
    )

    @model_validator(mode="after")
    def _check_custom(self) -> "RerefParams":
        if self.mode == "custom" and not self.ref_channels:
            raise ValueError("参考方式为 custom 时必须至少给出一个参考通道")
        return self


@register_step
class RerefStep(ProcStep):
    """重参考（set_eeg_reference）."""

    step_id = "reref"
    label_zh = "重参考"
    params_cls = RerefParams
    applies_to = frozenset({"raw", "epochs"})

    def apply(self, ctx: ProcessingContext, params: RerefParams) -> ProcessingContext:
        obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
        ch_names = ctx.ch_names
        if params.mode == "custom":
            # 通道名打错是最常见失败——提前中文点名可用通道
            missing = [c for c in params.ref_channels if c not in ch_names]
            if missing:
                raise StepError(
                    f"参考通道 {missing} 不存在。可用通道：{('、'.join(ch_names[:12]))}…"
                )
            ref = params.ref_channels
        else:
            ref = "average"
        # mne 1.12 的 set_eeg_reference 默认返回**副本**而非就地修改——必须用返回值
        out = mne.set_eeg_reference(obj, ref_channels=ref, ch_type="auto", verbose="ERROR")
        new = out[0] if isinstance(out, tuple) else out
        if new is not obj:  # 防御：将来 mne 改回就地修改时这里自动失效
            if ctx.stage == "raw":
                ctx.raw = new
            else:
                ctx.epochs = new
        return ctx
