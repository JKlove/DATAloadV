"""时间窗裁剪步骤（CropStep）——M4 特征范围"四层组合"的第③层.

口径（用户 2026-08-18 决策，见 TODO.md M4 节）：
- 预处理滤波类步骤（带通/陷波）仍**全量**执行——边界效应与滤波器状态连续性
  决定了不能按窗滤波；本步骤只做**数据范围裁剪**，应放在滤波步骤之后
- 与特征入口「用当前显示窗口」按钮的关系：按钮只把浏览器视口起止**预填**进
  本步骤参数（用户可见可改），绝不隐式绑定视口——视口随时变，隐式绑定会让
  管线记录不可复现

两阶段语义（tmin/tmax 都是秒，但坐标系不同）：
- raw：**绝对时间**（从文件开头起算）。裁剪后 mne 会同步更新内部 first_samp，
  因此 ``ctx.events`` 的 onset（绝对秒）与分段步骤的绝对样本号依然成立——
  窗口外的事件在后续分段时被自然丢弃，无需在这里改事件表
- epochs：**相对事件锚点**的时间（与分段窗口同一坐标系，mne.Epochs.crop 语义）
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class CropParams(BaseModel):
    """裁剪参数：起点必填（默认 0=从头），终点留空=到数据结尾."""

    tmin: float = Field(
        default=0.0, title="起始时间", ge=0.0,
        json_schema_extra={"unit": "s", "decimals": 2, "min": 0.0, "max": 86400.0},
        description="裁剪窗口起点（raw=从文件开头起算；epochs=相对事件锚点）",
    )
    tmax: Optional[float] = Field(
        default=None, title="结束时间",
        json_schema_extra={"unit": "s", "decimals": 2, "min": 0.1, "max": 86400.0},
        description="裁剪窗口终点，留空=到数据结尾（坐标系同上）",
    )

    @model_validator(mode="after")
    def _check_window(self) -> "CropParams":
        if self.tmax is not None and self.tmax <= self.tmin:
            raise ValueError(f"结束时间（{self.tmax}）必须大于起始时间（{self.tmin}）")
        return self


@register_step
class CropStep(ProcStep):
    """时间窗裁剪（raw.crop / epochs.crop，就地修改）."""

    step_id = "crop"
    label_zh = "时间窗裁剪"
    params_cls = CropParams
    applies_to = frozenset({"raw", "epochs"})

    def apply(self, ctx: ProcessingContext, params: CropParams) -> ProcessingContext:
        if ctx.stage == "raw":
            self._crop_raw(ctx, params)
        else:
            self._crop_epochs(ctx, params)
        return ctx

    # ------------------------------------------------------------------ raw 分支

    def _crop_raw(self, ctx: ProcessingContext, params: CropParams) -> None:
        raw = ctx.raw
        total = float(raw.times[-1])
        tmax = params.tmax if params.tmax is not None else total
        # 预检查给中文提示（mne 超界时抛英文错或静默截断，都不利排障）
        if params.tmin >= total:
            raise StepError(f"起始时间（{params.tmin:g} s）不小于数据长度（{total:.1f} s），裁剪窗口为空")
        if tmax > total + 1e-9:  # 1e-9 容浮点尾差（如视口预填 times[-1]）
            raise StepError(f"结束时间（{tmax:g} s）超出数据长度（{total:.1f} s）")
        n_ev_total = len(ctx.events)
        # 事件表不动（绝对坐标系仍成立）；统计窗口内事件数帮用户预期分段结果
        n_ev_in = sum(1 for onset in ctx.events.onset if params.tmin <= onset <= tmax)
        n0 = raw.n_times
        raw.crop(params.tmin, tmax)  # 就地修改；first_samp 同步更新（见模块 docstring）
        ctx.log(f"已裁剪到 [{params.tmin:g}, {tmax:g}] s（{n0}→{raw.n_times} 采样点；"
                f"窗口内事件 {n_ev_in}/{n_ev_total} 个，其余在后续分段时被丢弃）")

    # ------------------------------------------------------------------ epochs 分支

    def _crop_epochs(self, ctx: ProcessingContext, params: CropParams) -> None:
        epochs = ctx.epochs
        n0 = len(epochs)
        old_tmin, old_tmax = float(epochs.tmin), float(epochs.tmax)
        new_tmax = params.tmax if params.tmax is not None else old_tmax
        # 窗完全在段窗口外时 mne 抛英文错——预先转成与下方一致的中文提示
        if params.tmin > old_tmax or new_tmax < old_tmin:
            raise StepError(
                f"裁剪后分段数为 0（原 {n0} 段，段窗口 [{old_tmin:g}, {old_tmax:g}] s"
                f" 与裁剪窗 [{params.tmin:g}, {new_tmax:g}] s 无重叠）。"
                "epochs 阶段的起止时间是**相对事件锚点**的——请检查起止值"
            )
        # tmax=None 对 mne 表示"不裁这一侧"，与本参数"到结尾"语义一致
        epochs.crop(params.tmin, params.tmax)
        if len(epochs) == 0:
            raise StepError(
                f"裁剪后分段数为 0（原 {n0} 段，段窗口 [{old_tmin:g}, {old_tmax:g}] s"
                f" → [{params.tmin:g}, {params.tmax if params.tmax is not None else old_tmax:g}] s）。"
                "相对事件的时间窗内已无采样点——请检查起止值"
            )
        ctx.log(f"已把每段裁剪到 [{params.tmin:g}, "
                f"{params.tmax if params.tmax is not None else old_tmax:g}] s"
                f"（相对事件锚点；{n0}→{len(epochs)} 段存活）")
