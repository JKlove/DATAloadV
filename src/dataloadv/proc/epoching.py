"""事件分段步骤（EpochingStep）——把连续 raw 切成 epochs，三种锚定方式.

阶段翻转：本步骤执行后 ``ctx.stage`` 从 "raw" 变为 "epochs"，``ctx.raw``
释放（内存让位给 epochs）。后续仅接受 applies_to 含 "epochs" 的步骤。

锚定方式（M8.1 起）：
- **事件锚定**（默认，M3 现状）：锚点 = ``ctx.events``（读取器解析好的 EventTable，
  GDF 已带中文标签；code 为字符串，如 "769"/"T1"/"left"）中选中事件码的 onset。
  空事件表报错（本步骤历史行为，回归测试守门）。
- **固定窗滑窗**：无事件数据按固定窗全程滑动切段——锚点 = 从数据起点起、
  每隔「步进」秒一个，保证每段完整落在数据内（尾部不足一窗丢弃，与
  mne.make_fixed_length_events 惯例一致）。伪事件码「滑窗」。
- **手动时刻**：用户显式枚举锚点时刻（秒），每点取 [tmin, tmax] 相对窗
  （如 -1~+4）。锚点窗口越界**报错**而非静默丢——显式枚举的输入要最小惊讶。
  伪事件码「手动」。

边界口径（mne 1.12 实测）：一段被保留当且仅当
``anchor + round(tmin·fs) ≥ 0`` 且 ``anchor ≤ n_times − 1 − round(tmax·fs)``；
窗长 = ``round(tmax·fs) − round(tmin·fs) + 1``（双端闭）。锚点序列一律在
**样本域**构造（秒域四舍五入与样本域取整会差 1 个样本，导致段被静默丢弃）。
"""

from __future__ import annotations

from collections import Counter
from typing import Literal, Optional

import mne
import numpy as np
from pydantic import BaseModel, Field, model_validator

from .base import ProcStep, StepError, register_step
from .context import ProcessingContext


class EpochingParams(BaseModel):
    """分段参数.

    ``baseline``：基线校正窗口 ``(起, 止)``（秒，相对锚点；None=用 tmin/0）。
    传 None 整体表示**不做**基线校正。
    ``reject_uv``：峰峰值剔除阈值（µV），超出该幅度的分段被丢弃；None=不剔除。
    """

    anchor: Literal["事件锚定", "固定窗滑窗", "手动时刻"] = Field(
        default="事件锚定", title="锚定方式",
        description="事件锚定=按事件表切段；固定窗滑窗=无事件数据按固定窗滑段"
                    "（窗长=段终点−段起点）；手动时刻=按给定时刻列表切段",
    )
    event_codes: list[str] = Field(
        default=[], title="事件码（空=全部）",
        description="要保留的事件码，逗号分隔（如 769,770,771,772）；"
                    "留空=全部事件；仅锚定方式=事件锚定时生效",
    )
    step_s: Optional[float] = Field(
        default=None, title="滑窗步进（秒，空=无重叠）", gt=0.0, le=120.0,
        description="仅固定窗滑窗模式生效；步进=相邻两段锚点间距，"
                    "小于窗长即有重叠；留空=步进=窗长",
        json_schema_extra={"unit": "s", "min": 0.1, "max": 120.0, "decimals": 2},
    )
    anchors_s: list[float] = Field(
        default=[], title="锚点时刻（秒）",
        description="如 10, 20, 30.5；仅手动时刻模式生效；每点取段起点~段终点相对窗",
    )
    tmin: float = Field(
        default=-1.0, title="段起点（相对锚点）", ge=-60.0, le=0.0,
        json_schema_extra={"unit": "s", "decimals": 2},
    )
    tmax: float = Field(
        default=4.0, title="段终点（相对锚点）", gt=0.0, le=120.0,
        json_schema_extra={"unit": "s", "decimals": 2},
    )
    baseline: Optional[tuple[Optional[float], Optional[float]]] = Field(
        default=(None, 0.0), title="基线窗口",
        description="格式：起,止（秒，相对锚点；可用 无 表示开放端），如 无,0 或 -0.5,0；"
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
        if self.anchor == "手动时刻" and not self.anchors_s:
            raise ValueError("锚定方式为「手动时刻」时必须给出至少一个锚点时刻")
        if (self.anchor == "固定窗滑窗" and self.step_s is not None
                and self.step_s > self.tmax - self.tmin):
            raise ValueError(
                f"滑窗步进（{self.step_s:g}s）不能大于窗长（{self.tmax - self.tmin:g}s）"
            )
        return self


@register_step
class EpochingStep(ProcStep):
    """分段（mne.Epochs）：事件/固定窗滑窗/手动时刻三种锚定，raw → epochs 阶段翻转."""

    step_id = "epoching"
    label_zh = "事件分段"
    params_cls = EpochingParams
    applies_to = frozenset({"raw"})  # 只能对连续数据分段

    # ------------------------------------------------------------- 锚点来源（三选一）
    # 统一返回 (锚点样本数组, 逐段事件码 list, event_id 映射)；apply 据此拼 mne events。

    @staticmethod
    def _events_anchors(ev, params: EpochingParams, sfreq: float):
        """事件锚定：事件表筛选/排序/event_id（M3 现状逻辑原样搬移）."""
        codes_all = sorted(set(ev.code))
        keep = [c for c in codes_all if not params.event_codes or c in set(params.event_codes)]
        if not keep:
            raise StepError(
                f"事件码 {params.event_codes} 在本录制中不存在。实际可用事件码：{'、'.join(codes_all)}"
            )
        keep_set = set(keep)
        idx = [i for i, c in enumerate(ev.code) if c in keep_set]
        # 事件 onset（秒）→ 锚点样本序号
        samples = np.round(np.asarray(ev.onset)[idx] * sfreq).astype(np.int64)
        codes = [ev.code[i] for i in idx]
        order = np.argsort(samples, kind="stable")  # mne 要求按样本升序
        samples, codes = samples[order], [codes[j] for j in order]
        event_id = {c: i + 1 for i, c in enumerate(keep)}  # 任意稳定整数映射
        return samples, codes, event_id

    @staticmethod
    def _fixed_anchors(params: EpochingParams, sfreq: float, n_times: int):
        """固定窗滑窗：从数据起点起每隔「步进」取一个锚点，每段完整落在数据内.

        全程样本域计算（秒域近似会差 1 个样本导致段被 mne 静默丢弃）；
        尾部不足一窗的部分丢弃——生成器行为不报错（与 mne.make_fixed_length_events
        惯例一致），段数由 log 的 N/M 计数可见。
        """
        tmin_s = int(round(params.tmin * sfreq))
        tmax_s = int(round(params.tmax * sfreq))
        first = max(0, -tmin_s)  # 首段恰从样本 0 起（tmin=-1@250Hz → 首锚 1.0s）
        step = int(round((params.step_s if params.step_s is not None
                          else params.tmax - params.tmin) * sfreq))
        step = max(step, 1)  # 极小步进取整到 0 的守卫
        last = n_times - 1 - tmax_s  # mne 保留上界（实测口径）
        samples = np.arange(first, last + 1, step, dtype=np.int64)
        if not len(samples):
            raise StepError(
                f"数据长度（{n_times / sfreq:.1f}s）不足以切出一段 "
                f"[{params.tmin:g}, {params.tmax:g}]s 的完整窗口"
            )
        return samples, ["滑窗"] * len(samples), {"滑窗": 1}

    @staticmethod
    def _manual_anchors(params: EpochingParams, sfreq: float, n_times: int):
        """手动时刻：用户显式枚举锚点（秒），窗口越界报错列出全部无效锚点.

        显式枚举的输入要最小惊讶——「要 5 段得 3 段」比报错更难排查
        （越界锚点会被 mne on_missing="ignore" 静默丢弃）。保留条件逐字
        采用 mne 实测口径：s + round(tmin·fs) ≥ 0 且 s ≤ n_times − 1 − round(tmax·fs)。
        """
        tmin_s = int(round(params.tmin * sfreq))
        last = n_times - 1 - int(round(params.tmax * sfreq))
        bad, samples = [], []
        for a in params.anchors_s:
            s = int(round(a * sfreq))
            if s + tmin_s >= 0 and s <= last:
                samples.append(s)
            else:
                bad.append(a)
        if bad:
            raise StepError(
                f"锚点 {bad} 的段窗口 [{params.tmin:g}, {params.tmax:g}]s 超出数据范围"
                f"（0 ~ {n_times / sfreq:.1f}s）；请修正锚点或缩小窗口"
            )
        samples = np.sort(np.asarray(samples, dtype=np.int64))  # mne 要求升序
        return samples, ["手动"] * len(samples), {"手动": 1}

    def apply(self, ctx: ProcessingContext, params: EpochingParams) -> ProcessingContext:
        raw = ctx.raw
        sfreq = raw.info["sfreq"]
        n_times = raw.n_times
        if params.anchor == "事件锚定":
            if len(ctx.events) == 0:
                raise StepError("该录制没有事件标注，事件锚定不可用——"
                                "可改用「固定窗滑窗」或「手动时刻」锚定方式")
            samples, codes, event_id = self._events_anchors(ctx.events, params, sfreq)
        elif params.anchor == "固定窗滑窗":
            samples, codes, event_id = self._fixed_anchors(params, sfreq, n_times)
        else:
            samples, codes, event_id = self._manual_anchors(params, sfreq, n_times)
        # 锚点 → mne events 三列数组 [样本序号, 前一事件值(0), 事件码整数]
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
        ctx.log(f"分段完成：{len(epochs)}/{n_want} 段（{params.anchor}），"
                f"每段 {(params.tmax - params.tmin):g}s；"
                f"按类：{'，'.join(f'{k}×{v}' for k, v in sorted(kept.items()))}")
        return ctx
