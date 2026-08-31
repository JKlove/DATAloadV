"""时频分析纯计算（M8）——morlet 小波功率谱，供分段预览/未来特征共用.

与 qc.py 同定位：**纯 Python/numpy 计算层**（禁止 import PySide6/pyqtgraph，
硬性架构规则 #1）——UI 只编排（后台线程调用 + 结果交给 ImageItem 画热图）。

- ``default_tfr_freqs``：2–45 Hz 对数间隔 24 点——低频密高频疏，符合
  电生理分析习惯（δ 段 1Hz 差异与 γ 段 5Hz 差异同屏可辨）
- ``compute_epochs_tfr``：[n_ep, n_ch, n_times]（伏特）→ 段平均功率 →
  基线校正 dB。基线期取 (None, 0.0)（= 事件前全部分段前期）；数据无
  负时间（tmin ≥ 0）时跳过校正（dB 相对每频点最大值归一，仍可读）

n_cycles = freqs/2（低频时间窗长、高频短——时频分辨率的惯例折衷；
下限 2 防最低频点退化成 <2 个周期的卷积核）。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from mne.time_frequency import tfr_array_morlet

# 单次时频计算的段数上限：段平均在此规模内统计意义足够，且 UI 后台计算
# 毫秒级返回；超出时调用方应均匀抽样（预览是看形态，不是出数据）
MAX_EPOCHS_FOR_TFR = 80


def default_tfr_freqs(fmin: float = 2.0, fmax: float = 45.0, n: int = 24) -> np.ndarray:
    """默认分析频率轴：对数间隔（低频密、高频疏）."""
    if not (0.0 < fmin < fmax):
        raise ValueError(f"频率范围必须满足 0 < 低 < 高，收到 {fmin}-{fmax} Hz")
    return np.logspace(np.log10(fmin), np.log10(fmax), n)


def compute_epochs_tfr(
    data: np.ndarray,
    sfreq: float,
    times: np.ndarray,
    freqs: Optional[np.ndarray] = None,
    baseline: Optional[tuple[Optional[float], Optional[float]]] = (None, 0.0),
    ch_idx: int = 0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """morlet TFR 的段平均功率 → 基线校正 dB.

    :param data: [n_epochs, n_ch, n_times]，单位伏特（mne 原生口径）。
    :param times: 段内时间轴（秒，相对事件锚点，tmin 可为负）。
    :param freqs: 分析频率轴；None = ``default_tfr_freqs``。
    :param baseline: 基线期 (起, 止) 秒，None 端 = 开区间（(None, 0) = 事件前
        全部）；None 参数 = 不校正（tmin ≥ 0 的数据自动走此分支）。
    :param ch_idx: 分析通道行（UI 单通道视图传选中行；多通道请各自调用）。
    :returns: (freqs, times, db[n_freq, n_times])——db = 10·log10(功率)，
        逐频点减基线期均值（无基线时减频点最大值，仅缩放显示）。
    """
    if data.ndim != 3:
        raise ValueError(f"data 应为 [n_epochs, n_ch, n_times]，收到形状 {data.shape}")
    sub = data[:MAX_EPOCHS_FOR_TFR, ch_idx : ch_idx + 1, :]  # [≤80, 1, n_t]
    if sub.shape[0] < 1:
        raise ValueError("没有分段可计算时频")
    freqs = default_tfr_freqs() if freqs is None else np.asarray(freqs, dtype=float)
    n_cycles = np.maximum(freqs / 2.0, 2.0)
    power = tfr_array_morlet(
        sub, sfreq, freqs, n_cycles=n_cycles, output="power",
        zero_mean=True, verbose="ERROR",
    )  # [n_ep_kept, 1, n_freq, n_times]
    mean_power = power[:, 0].mean(axis=0)  # [n_freq, n_times]
    db = 10.0 * np.log10(np.maximum(mean_power, 1e-40))  # 下限防 log(0)

    # 基线校正：仅当数据有负时间（tmin < 0，事件前可作基线）且基线期
    # ≥2 个采样点时执行——tmin ≥ 0 时 (None, 0) 只会罩住单个 t=0 样本，
    # 单样本"均值"无统计意义（docstring 声称的跳过分支靠这两道闸落实）
    if baseline is not None and times[0] < 0:
        lo, hi = baseline
        b0 = times[0] if lo is None else lo
        b1 = times[-1] if hi is None else hi
        bmask = (times >= b0) & (times <= b1)
        if bmask.all() or int(bmask.sum()) < 2:
            bmask = np.zeros_like(times, dtype=bool)  # 全段/单点 → 无从校正
    else:
        bmask = np.zeros_like(times, dtype=bool)

    if bmask.any():
        db = db - db[:, bmask].mean(axis=1, keepdims=True)
    else:
        # 无可用基线（tmin ≥ 0 或基线期覆盖全段）：相对每频点峰值归一，
        # 色标读数是"相对该频点峰值的 dB"而非"相对基线变化"
        db = db - db.max(axis=1, keepdims=True)
    return freqs, times, db
