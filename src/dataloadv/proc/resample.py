"""降采样步骤（ResampleStep）——降低采样率以缩小数据量/加速后续分析.

注意：重采样后时长不变、事件 onset（秒）不变，但原始 annotations 会随 raw
一并重采样（mne 行为）；对后续按秒分段无影响。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class ResampleParams(BaseModel):
    """降采样参数：目标采样率必须低于当前值（高于当前=升采样，无意义且引入伪影）."""

    sfreq: float = Field(
        default=250.0, title="目标采样率", gt=0,
        json_schema_extra={"unit": "Hz", "min": 1.0, "max": 5000.0, "decimals": 1},
        description="常见：250（BCI 2a/2b 原生）、100（ds1 原生）、160（PhysioNet 原生）",
    )


@register_step
class ResampleStep(ProcStep):
    """降采样（raw.resample / epochs.resample）."""

    step_id = "resample"
    label_zh = "降采样"
    params_cls = ResampleParams
    applies_to = frozenset({"raw", "epochs"})

    def apply(self, ctx: ProcessingContext, params: ResampleParams) -> ProcessingContext:
        if params.sfreq >= ctx.sfreq:
            raise StepError(
                f"目标采样率（{params.sfreq:g}）应低于当前采样率（{ctx.sfreq:g}）——"
                "升采样不减少数据量还会引入插值伪影"
            )
        obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
        obj.resample(params.sfreq, verbose="ERROR")
        return ctx
