"""时域统计特征（TimeDomainStats）——每通道/每段一组的波形形态统计量.

全部纯 numpy/scipy 实现（无频谱计算，快）：对 BCI 2a 这类 288 段×22 通道的
数据一次 ``get_data`` 后向量化完成，不做 Python 级逐段循环。

统计量清单（名字进长表 feature 列，µV 基准与浏览器一致）：
- ``rms_uv``  均方根（幅度代表性的单一指标）
- ``var_uv2`` 方差
- ``mav_uv``  平均绝对值（均值幅度，抗离群）
- ``ptp_uv``  峰峰值（最大-最小）
- ``iqr_uv``  四分位距（稳健的离散度）
- ``zc_rate`` 过零率（次/秒；带阈值滞回防噪声抖动虚高）
- ``kurtosis`` 超额峰度（scipy fisher 默认：正态=0，尖峰>0）
- ``skewness`` 偏度（不对称性）
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field
from scipy.stats import iqr as scipy_iqr
from scipy.stats import kurtosis, skew

from .base import (
    ExtractorResult,
    FeatureError,
    FeatureExtractor,
    pick_channels,
    picks_indices,
    register_feature,
)
from ..proc.context import ProcessingContext


class TimeDomainParams(BaseModel):
    """时域统计参数.

    ``zc_threshold_uv``：过零判定的滞回阈值（µV）——相邻两个"过零穿越点"之间
    信号必须先超出该幅度才算一次真实穿越；过小会让噪声底把过零率抬高。
    """

    stats: list[str] = Field(
        default=["rms_uv", "var_uv2", "mav_uv", "ptp_uv", "iqr_uv",
                 "zc_rate", "kurtosis", "skewness"],
        title="统计量",
        description="留空=全部。可选：rms_uv/var_uv2/mav_uv/ptp_uv/iqr_uv/zc_rate/kurtosis/skewness",
    )
    channels: list[str] = Field(
        default=[], title="通道（空=全部数据通道）",
        description="通道名逗号分隔；留空=全部数据通道（自动排除坏道与辅助通道）",
    )
    zc_threshold_uv: float = Field(
        default=5.0, title="过零判定阈值",
        json_schema_extra={"unit": "µV", "decimals": 1, "min": 0.0, "max": 1000.0},
        description="过零计数前信号需超出的幅度（防噪声抖动虚高）",
    )


def zero_crossing_rate(x_uv: np.ndarray, threshold_uv: float) -> float:
    """带滞回的过零率（次/秒语义由调用方除时长；此处返回次数）.

    实现：把信号限制在 ±threshold 之外后数符号翻转——等效于"穿过零线的
    显著穿越"次数，噪声抖动在阈值带内的往返不计入。
    """
    if x_uv.size < 2:
        return 0.0
    sig = np.where(x_uv > threshold_uv, 1, np.where(x_uv < -threshold_uv, -1, 0))
    # 只统计非零符号之间的翻转（0=阈值带内，不参与）
    nz = sig[sig != 0]
    return float(np.count_nonzero(nz[1:] != nz[:-1]))


# 统计量名 → 计算函数（输入 µV 数组，输出 float；向量化沿最后轴）
def _stat_functions(zc_threshold_uv: float) -> dict[str, object]:
    return {
        "rms_uv": lambda x: np.sqrt(np.mean(x * x, axis=-1)),
        "var_uv2": lambda x: np.var(x, axis=-1),
        "mav_uv": lambda x: np.mean(np.abs(x), axis=-1),
        "ptp_uv": lambda x: np.ptp(x, axis=-1),
        "iqr_uv": lambda x: scipy_iqr(x, axis=-1),
        "kurtosis": lambda x: kurtosis(x, axis=-1),
        "skewness": lambda x: skew(x, axis=-1),
        # 过零率无法纯向量化（状态依赖）→ 逐通道循环，见 _apply_stats
        "zc_rate": None,
    }


@register_feature
class TimeDomainStatsFeature(FeatureExtractor):
    """时域统计：raw 每通道一组；epochs 逐段逐通道一组."""

    feature_id = "timedomain"
    label_zh = "时域统计"
    params_cls = TimeDomainParams
    applies_to = frozenset({"raw", "epochs"})

    def extract(self, ctx: ProcessingContext, params: TimeDomainParams) -> ExtractorResult:
        funcs = _stat_functions(params.zc_threshold_uv)
        unknown = [s for s in params.stats if s not in funcs]
        if unknown:
            raise FeatureError(
                f"未知统计量 {unknown}。可用：{'、'.join(funcs)}"
            )
        stats = params.stats or list(funcs)  # 空列表=全部（表单清空兜底）
        channels = pick_channels(ctx, params.channels)
        picks = picks_indices(ctx, channels)
        if ctx.stage == "raw":
            data = ctx.raw.get_data(picks=picks)[None, ...]  # [1, n_ch, n_t]
            epoch_ids: list[int | None] = [None]
            codes: list[str | None] = [None]
        else:
            data = ctx.epochs.get_data(picks=picks)  # [n_ep, n_ch, n_t]
            id2code = {v: k for k, v in ctx.epochs.event_id.items()}
            epoch_ids = list(range(len(ctx.epochs)))
            codes = [id2code.get(int(c)) for c in ctx.epochs.events[:, -1]]
        data_uv = data * 1e6  # V → µV（与特征表基准单位一致）
        duration_s = data_uv.shape[-1] / ctx.sfreq
        result = ExtractorResult()
        for name in stats:
            if name == "zc_rate":
                # 逐段逐通道（状态依赖无法沿轴向量化；288×22 量级毫秒级完成）
                vals = np.array([
                    [zero_crossing_rate(data_uv[i, c], params.zc_threshold_uv)
                     for c in range(data_uv.shape[1])]
                    for i in range(data_uv.shape[0])
                ]) / duration_s  # 次 → 次/秒
            else:
                vals = funcs[name](data_uv)  # [n_ep, n_ch]
            for i_ep in range(vals.shape[0]):
                for i_ch, ch in enumerate(channels):
                    result.scalars.append({
                        "epoch_index": epoch_ids[i_ep],
                        "event_code": codes[i_ep],
                        "channel": ch,
                        "feature": name,
                        "value": float(vals[i_ep, i_ch]),
                    })
        return result
