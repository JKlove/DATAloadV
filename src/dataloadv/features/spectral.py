"""Welch 谱估计工具——M3 PSD 视图与 M4 频谱类特征共用.

只放"纯计算"：输入 mne Raw/Epochs（或数据数组），输出 (freqs, psd)。
UI（psd_view）与特征提取器（M4 spectral 特征）都调这里，避免两份实现。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

# PSD 默认频率范围：0.5 Hz 以下对电生理意义不大且 log 轴显示困难
FMIN_DEFAULT = 0.5


def mean_welch(
    inst,
    picks: Optional[list[int]] = None,
    fmin: float = FMIN_DEFAULT,
    fmax: Optional[float] = None,
    n_per_seg_s: float = 4.0,
) -> tuple[np.ndarray, np.ndarray]:
    """对 Raw 或 Epochs 计算 Welch PSD，再对通道（与分段）求平均.

    :param inst: mne.io.BaseRaw 或 mne.Epochs（需已含数据）
    :param picks: 通道索引；None = 全部数据通道（mne 默认，自动排除 misc/bads）
    :param fmax: 上限频率；None = Nyquist
    :param n_per_seg_s: 每段长度（秒）——决定频率分辨率；过长则段数少、方差大
    :returns: (freqs[n], psd_mean[n])，单位 V²/Hz（显示层自行 ×1e12 转 µV²/Hz）
    """
    sfreq = inst.info["sfreq"]
    n_per_seg = max(256, int(n_per_seg_s * sfreq))  # 下限 256 点防超短窗口
    if fmax is None:
        fmax = sfreq / 2.0  # mne 1.12 的 compute_psd 不接受 fmax=None，须显式 Nyquist
    psd = inst.compute_psd(
        method="welch", fmin=fmin, fmax=fmax, picks=picks,
        n_per_seg=n_per_seg, average="mean", verbose="ERROR",
    )
    data = psd.get_data()  # [ch, freqs]（Epochs 时 compute_psd 已先对段平均）
    freqs = np.asarray(psd.freqs, dtype=float)
    return freqs, data.mean(axis=0)
