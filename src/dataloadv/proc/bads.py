"""坏导联步骤（BadChannelsStep）：标记或插值坏通道.

与浏览器的联动：浏览器通道列表右键"标记坏道"会写入 raw.info["bads"] 并灰显
曲线；本步骤的 ``channels`` 参数默认值由 UI 侧用浏览器当前标记预填（见
pipeline_panel），也可手动输入通道名。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class BadChannelsParams(BaseModel):
    """坏道处理参数.

    - ``action="mark"``：只标记（info["bads"]）——滤波/平均等操作自动排除坏道，
      数据本体不动（可逆，最安全）
    - ``action="interpolate"``：标记后立刻插值重建（需通道位置信息；EEG 常用）
    """

    channels: list[str] = Field(
        default=[], title="坏道通道",
        description="通道名用逗号分隔；默认带入浏览器中已标记的坏道",
    )
    action: Literal["mark", "interpolate"] = Field(
        default="mark", title="处理方式",
        description="mark=仅标记（推荐，可逆）；interpolate=插值替换（需电极位置）",
    )
    # 空列表不在模型层拦——默认值必须是可构造的（表单先建、跑步骤时才校验）


@register_step
class BadChannelsStep(ProcStep):
    """坏导联标记/插值."""

    step_id = "bads"
    label_zh = "坏导联处理"
    params_cls = BadChannelsParams
    applies_to = frozenset({"raw", "epochs"})

    def apply(self, ctx: ProcessingContext, params: BadChannelsParams) -> ProcessingContext:
        if not params.channels:
            raise StepError("坏道列表为空——至少给出一个通道名，或在浏览器右键标记后重新添加本步骤")
        obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
        ch_names = ctx.ch_names
        missing = [c for c in params.channels if c not in ch_names]
        if missing:
            raise StepError(f"坏道通道 {missing} 不存在。可用通道：{'、'.join(ch_names[:12])}…")
        # 重新赋值（而非 +=）：保证幂等——重复执行不会让 bads 越积越多
        obj.info["bads"] = sorted(set(obj.info.get("bads", [])) | set(params.channels))
        if params.action == "interpolate":
            try:
                obj.interpolate_bads(verbose="ERROR")
            except Exception as e:  # noqa: BLE001 - mne 对无位置数据报英文错——转中文指引
                raise StepError(
                    f"坏道插值失败：{e}。插值需要电极位置（montage）信息——"
                    "没有位置数据时请改用「仅标记」方式"
                ) from e
            ctx.log(f"已插值坏道：{params.channels}")
        else:
            ctx.log(f"已标记坏道（处理时自动排除）：{params.channels}")
        return ctx
