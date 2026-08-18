"""滤波步骤：带通（BandPassStep）与陷波（NotchStep）.

两者都是 mne Raw/Epochs 滤波方法的参数化包装；参数校验（l<h、非空频点等）
放在 pydantic 模型里，mne 调用只做执行。
"""

from __future__ import annotations

from typing import Literal, Optional

import mne
from pydantic import BaseModel, Field, model_validator

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class BandPassParams(BaseModel):
    """带通滤波参数.

    ``l_freq``/``h_freq`` 任一为 None 表示该侧不滤（如只做 1 Hz 高通）。
    ``unit``/``min``/``max``/``decimals`` 等额外键供 params_form 生成合适的输入控件。
    """

    l_freq: Optional[float] = Field(
        default=1.0, title="低截频率（高通）", ge=0,
        description="低于此频率的成分被衰减；留空（不勾选）= 不做高通",
        json_schema_extra={"unit": "Hz", "min": 0.0, "max": 500.0, "decimals": 1},
    )
    h_freq: Optional[float] = Field(
        default=40.0, title="高截频率（低通）",
        description="高于此频率的成分被衰减；留空（不勾选）= 不做低通",
        json_schema_extra={"unit": "Hz", "min": 0.1, "max": 2000.0, "decimals": 1},
    )
    method: Literal["fir", "iir"] = Field(
        default="fir", title="滤波器类型",
        description="fir 稳定且相位线性（默认）；iir 阶数低但需注意稳定性",
    )

    @model_validator(mode="after")
    def _check_range(self) -> "BandPassParams":
        # l=h 在 mne 里等于带阻语义，l>h 直接非法——都提前拦下给中文提示
        if self.l_freq is not None and self.h_freq is not None and self.l_freq >= self.h_freq:
            raise ValueError(f"低截频率（{self.l_freq}）必须小于高截频率（{self.h_freq}）")
        return self


@register_step
class BandPassStep(ProcStep):
    """带通滤波（raw.filter / epochs.filter）."""

    step_id = "bandpass"
    label_zh = "带通滤波"
    params_cls = BandPassParams
    applies_to = frozenset({"raw", "epochs"})

    def apply(self, ctx: ProcessingContext, params: BandPassParams) -> ProcessingContext:
        obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
        # 不勾选的一侧传 None：mne filter 语义 None=跳过该侧
        obj.filter(
            l_freq=params.l_freq, h_freq=params.h_freq,
            method=params.method, picks=None, verbose="ERROR",
        )
        return ctx


class NotchParams(BaseModel):
    """陷波参数（默认 50 Hz 工频；多频点如 [50, 100, 150] 可一并压制谐波）."""

    freqs: list[float] = Field(
        default=[50.0], title="陷波频点",
        description="要压制的频率（V/Hz）；多个用逗号分隔，如 50, 100, 150",
        json_schema_extra={"item_unit": "Hz"},
    )


@register_step
class NotchStep(ProcStep):
    """陷波滤波（notch_filter）——工频及其谐波抑制.

    仅 raw 阶段：mne 1.12 的 Epochs 无 notch_filter 方法（改写 epochs 私有
    _data 不可取）；分段前陷波也是标准流程——顺序错了会得到明确中文提示。
    """

    step_id = "notch"
    label_zh = "陷波（工频）"
    params_cls = NotchParams
    applies_to = frozenset({"raw"})

    def apply(self, ctx: ProcessingContext, params: NotchParams) -> ProcessingContext:
        if not params.freqs:
            raise StepError("陷波频点列表为空——至少给一个频率（如 50）")
        nyquist = ctx.sfreq / 2.0
        # 频点必须严格低于 Nyquist，否则 mne 内部报错且信息晦涩——提前中文拦截
        bad = [f for f in params.freqs if f <= 0 or f >= nyquist]
        if bad:
            raise StepError(f"陷波频点 {bad} 超出有效范围（0 < 频点 < Nyquist={nyquist:g} Hz）")
        obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
        obj.notch_filter(freqs=params.freqs, picks=None, verbose="ERROR")
        return ctx
