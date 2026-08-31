"""信号质量体检（M7）——把四轮手工"噪声感"诊断固化成可复跑的指标.

方法论来源（DATA_NOTES §8 + M6.6/M6.7b 实证）：
- 羊 BDF：CH5-8 开路复用——逐样本与别的通道完全相同、且钉在满量程极值上
  （±375000µV 饱和死值）；CH1-3 真实皮层信号带大直流但活度正常；
- clinicaldata TPDJ-位置1：八通道全平（死放大器）；
- clinicaldata DGDJ：真信号带基线漂移——漂移只"疑似"不定"坏"。

由此定下的判定规则（刻意**不用绝对饱和电平阈值**——BioSemi 满量程 ±375000µV
与 g.USBamp ±5000µV 差两个数量级，无法共用阈值，改看"钉在本通道自身极值
上的样本占比"）：

- **bad**（建议标坏道）满足其一：
  标准差 < ``dead_std_uv``（死值）；平直占比 ≥ ``flat_bad_pct``（与前一样本
  完全相同的样本比例）；钉极值占比 ≥ ``rail_bad_pct``（疑似满量程饱和）；
  与其他通道逐样本完全相同（开路复用）；
- **suspect**（疑似，建议人工复核）：钉极值占比 ≥ ``rail_suspect_pct``；
  |漂移| ≥ ``drift_suspect_uv_min``（窗中位数对时间最小二乘斜率，µV/min）；
- **good**：其余。直流偏移只进指标不定级——DC 耦合放大器固有直流，
  羊 CH1-3 的大直流是真实信号（M6.7b 定论）。

两条使用路径共用同一纯计算（``compute_channel_qc`` 收 ``get_window`` 闭包，
不整载大文件——与浏览器偏移统计同款分窗采样）：
1. 浏览器「质量体检」按钮：``rec.get_window`` 直连（LAZY 亦不整载）；
2. 特征提取器（``QualityCheckFeature``）：``ctx.raw`` 分窗闭包——注册进
   FEATURE_REGISTRY 后自动获得参数表单/批处理/CSV·HDF5 导出，零新 UI。

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
from pydantic import BaseModel, Field

from .base import (
    DATA_CH_TYPES,
    FeatureError,
    FeatureExtractor,
    ExtractorResult,
    register_feature,
)

# get_window 闭包签名与 core.recording.Recording.get_window 一致：
# (t0, t1, picks) -> (data[ch, n_times]（伏特）, times)
GetWindow = Callable[[float, float, Optional[list[int]]], tuple[np.ndarray, np.ndarray]]


class QualityCheckParams(BaseModel):
    """质量体检参数（全部有量纲默认值——跨设备无须改）."""

    channels: str = Field(
        "", title="通道", description="留空=全部数据通道；可填逗号分隔子集（如 EEG0,EEG3）"
    )
    n_windows: int = Field(
        20, title="采样窗数", ge=1, le=200,
        description="全程均匀撒 N 个窗计算统计（不整载大文件）",
    )
    win_s: float = Field(2.0, title="窗长（秒）", gt=0.0, le=600.0)
    dead_std_uv: float = Field(
        0.01, title="死值标准差阈值（µV）", ge=0.0,
        description="窗内样本标准差低于此值判死值",
    )
    flat_bad_pct: float = Field(
        99.0, title="平直判定（%）", ge=0.0, le=100.0,
        description="与前一样本完全相同的样本占比达到此值判坏",
    )
    rail_bad_pct: float = Field(
        50.0, title="饱和判定（%）", ge=0.0, le=100.0,
        description="钉在本通道极值上的样本占比达到此值判坏",
    )
    rail_suspect_pct: float = Field(
        1.0, title="饱和疑似（%）", ge=0.0, le=100.0,
        description="钉极值占比达到此值判疑似（低于判坏线）",
    )
    drift_suspect_uv_min: float = Field(
        50.0, title="漂移疑似（µV/min）", ge=0.0,
        description="窗中位数对时间的斜率达到此值判疑似",
    )


def _plan_windows(duration_s: float, n_windows: int, win_s: float) -> list[tuple[float, float]]:
    """全程均匀撒窗，返回 [(t0, t1), ...]（t1 ≤ duration）.

    时长不足 ``win_s * n_windows`` 时收缩窗数（保住首窗从 0 起）；
    时长连一个满窗都不够时退化为单窗 [0, duration)。
    """
    if duration_s <= 0.0:
        return []
    n = max(1, min(n_windows, int(duration_s // win_s) or 1))
    if n == 1:
        return [(0.0, min(win_s, duration_s))]
    step = (duration_s - win_s) / (n - 1)  # 末窗恰好贴到 duration
    return [(i * step, i * step + win_s) for i in range(n)]


def compute_channel_qc(
    get_window: GetWindow,
    ch_names: list[str],
    sfreq: float,
    duration_s: float,
    params: QualityCheckParams | None = None,
) -> list[dict]:
    """纯计算：逐通道质量体检.

    :param get_window: ``(t0, t1, picks) -> (data 伏特, times)`` 闭包——
        浏览器传 ``rec.get_window``（LAZY 不整载），提取器传 ``ctx.raw``
        分窗闭包（PRELOAD 亦只取窗）。
    :param ch_names: 参检通道名（顺序即 picks 索引顺序）。
    :param sfreq: 采样率（Hz，仅用于漂移斜率换算的窗中心采样）。
    :param duration_s: 总时长（秒）。
    :param params: 判定阈值；None 用默认。
    :return: 逐通道 ``{"channel", "quality"(good/suspect/bad),
        "reasons"(中文问题清单), "metrics"(dict[str, float]),
        "dup_with"(开路复用的对端通道名或 None)}``。

    采样策略：``_plan_windows`` 均匀撒窗 → 逐窗 ``get_window`` → 沿时间拼接
    后算全局统计（钉极值要用全程极值；窗间边界 diff 是真实的相邻时刻比较，
    不引入假差异）。
    """
    p = params or QualityCheckParams()
    windows = _plan_windows(duration_s, p.n_windows, p.win_s)
    if not windows:
        raise FeatureError("录制时长为 0，无法做质量体检")

    picks = list(range(len(ch_names)))
    blocks: list[np.ndarray] = []  # 每窗 (n_ch, n_t) µV
    for t0, t1 in windows:
        data, _ = get_window(t0, t1, picks)
        blocks.append(np.asarray(data, dtype=np.float64) * 1e6)  # V → µV
    x = np.concatenate(blocks, axis=1)  # (n_ch, n_total)

    # 逐窗中位数 → 对窗中心最小二乘 → 漂移斜率（µV/min）
    centers = np.array([(t0 + t1) / 2.0 for t0, t1 in windows])
    win_medians = np.array([np.median(b, axis=1) for b in blocks])  # (n_win, n_ch)
    slope_uv_s = np.polyfit(centers, win_medians, 1)[0]  # (n_ch,)
    drift_uv_min = slope_uv_s * 60.0

    results: list[dict] = []
    # 开路复用：逐对完全相同（第一个命中的对端即停）——羊 CH5-8 全相同会
    # 两两命中，dup_with 记最先遇到的对端即可
    dup_with: list[Optional[str]] = [None] * len(ch_names)
    for i in range(len(ch_names)):
        if dup_with[i] is not None:
            continue
        for j in range(i + 1, len(ch_names)):
            if dup_with[j] is None and np.array_equal(x[i], x[j]):
                dup_with[i] = ch_names[j]
                dup_with[j] = ch_names[i]
                break

    for i, name in enumerate(ch_names):
        row = x[i]
        std_uv = float(np.std(row))
        dc_uv = float(np.median(row))
        flat_pct = float(np.mean(np.diff(row) == 0.0) * 100.0)
        vmax, vmin = row.max(), row.min()
        rail_pct = float(np.mean((row == vmax) | (row == vmin)) * 100.0)
        drift = float(drift_uv_min[i])

        reasons: list[str] = []
        if dup_with[i] is not None:
            reasons.append(f"与通道 {dup_with[i]} 逐样本完全相同（疑似开路复用）")
        if std_uv < p.dead_std_uv:
            reasons.append(f"标准差 {std_uv:.4f} µV 低于死值阈值 {p.dead_std_uv} µV")
        if flat_pct >= p.flat_bad_pct:
            reasons.append(f"{flat_pct:.1f}% 样本与前一样本完全相同（平直死值）")
        if rail_pct >= p.rail_bad_pct:
            reasons.append(
                f"{rail_pct:.1f}% 样本钉在本通道极值上（疑似满量程饱和）"
            )
        elif rail_pct >= p.rail_suspect_pct:
            reasons.append(
                f"{rail_pct:.1f}% 样本钉在极值上（饱和疑似，未达判坏线）"
            )
        if abs(drift) >= p.drift_suspect_uv_min:
            reasons.append(
                f"漂移 {drift:+.1f} µV/min 超过疑似线 {p.drift_suspect_uv_min} µV/min"
            )

        bad = (
            dup_with[i] is not None
            or std_uv < p.dead_std_uv
            or flat_pct >= p.flat_bad_pct
            or rail_pct >= p.rail_bad_pct
        )
        suspect = not bad and bool(reasons)  # 到这里 reasons 只剩疑似项
        quality = "bad" if bad else ("suspect" if suspect else "good")

        results.append({
            "channel": name,
            "quality": quality,
            "reasons": reasons,
            "metrics": {
                "qc_level": {"good": 0.0, "suspect": 1.0, "bad": 2.0}[quality],
                "qc_bad_flag": 1.0 if bad else 0.0,
                "qc_suspect_flag": 1.0 if suspect else 0.0,
                "qc_dup_flag": 1.0 if dup_with[i] is not None else 0.0,
                "qc_dc_uv": dc_uv,
                "qc_std_uv": std_uv,
                "qc_drift_uv_min": drift,
                "qc_flat_pct": flat_pct,
                "qc_rail_pct": rail_pct,
            },
            "dup_with": dup_with[i],
        })
    return results


@register_feature
class QualityCheckFeature(FeatureExtractor):
    """质量体检作为特征提取器——接入注册表即得表单/批处理/导出（M4 架构红利）.

    与其他提取器的语义差异：``pick_channels`` 会排除坏道，而 QC 的对象恰恰
    **包含**坏道（坏道正是要体检出来的），故自带通道选择（``DATA_CH_TYPES``
    全集，不剔除 ``info["bads"]``）。
    """

    feature_id = "qc"
    label_zh = "信号质量体检"
    params_cls = QualityCheckParams
    applies_to = frozenset({"raw"})  # 分段后做文件级体检已无意义

    def extract(self, ctx, params: QualityCheckParams) -> ExtractorResult:  # type: ignore[override]
        if ctx.stage != "raw":
            raise FeatureError("信号质量体检仅支持连续数据（raw）阶段——请在分段前体检")
        raw = ctx.raw
        names = list(raw.ch_names)
        types = list(raw.get_channel_types())
        # 全部数据通道（含坏道），保持文件内顺序
        channels = [n for n, t in zip(names, types) if t in DATA_CH_TYPES]
        if not channels:
            raise FeatureError("文件中没有数据通道（eeg/ecog/seeg/meg/dbs），无法体检")
        if params.channels.strip():
            wanted = [s.strip() for s in params.channels.split(",") if s.strip()]
            unknown = [s for s in wanted if s not in channels]
            if unknown:
                raise FeatureError(
                    f"质量体检通道不存在或非数据通道：{'、'.join(unknown)}。"
                    f"可用：{'、'.join(channels)}"
                )
            channels = wanted
        picks = [names.index(c) for c in channels]
        n_times = raw.n_times
        sf = float(raw.info["sfreq"])

        def _gw(t0: float, t1: float, sel: Optional[list[int]] = None):
            # 与 Recording.get_window 同语义的 raw 分窗（start 含 stop 不含；
            # 钳到 [0, n_times]，保底 2 样本防退化窗）
            s0 = max(0, int(round(t0 * sf)))
            s1 = min(n_times, max(s0 + 2, int(round(t1 * sf))))
            data = raw.get_data(picks=sel, start=s0, stop=s1)
            return data, None

        rows = compute_channel_qc(_gw, channels, sf, n_times / sf, params)
        result = ExtractorResult()
        for row in rows:
            for feat, value in row["metrics"].items():
                result.scalars.append({
                    "epoch_index": None,
                    "event_code": None,
                    "channel": row["channel"],
                    "feature": feat,
                    "value": float(value),
                })
        return result
