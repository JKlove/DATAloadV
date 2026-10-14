"""时频分析纯计算（M8 morlet；M13 扩四方法）——供分段预览/浏览器同段时频图共用.

与 qc.py 同定位：**纯 Python/numpy 计算层**（禁止 import PySide6/pyqtgraph，
硬性架构规则 #1）——UI 只编排（后台线程调用 + 结果交给 ImageItem 画热图）。

- ``default_tfr_freqs``：对数间隔频率轴（低频密高频疏）。
- ``compute_epochs_tfr``（M8）：[n_ep, n_ch, n_times]（伏特）→ 段平均 morlet
  功率 → 基线校正 dB——分段预览在用，语义不动。
- ``TfrConfig`` + ``compute_window_tfr``（M13）：浏览器同段时频图统一入口，
  四方法（morlet/multitaper/stockwell/stft，TFR_METHODS）+ 参数化配置；
  dB 口径统一"每频点减自身峰值"（浏览器无事件基线）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from mne.time_frequency import tfr_array_morlet, tfr_array_multitaper, tfr_array_stockwell
from scipy.signal import stft as scipy_stft

# 单次时频计算的段数上限：段平均在此规模内统计意义足够，且 UI 后台计算
# 毫秒级返回；超出时调用方应均匀抽样（预览是看形态，不是出数据）
MAX_EPOCHS_FOR_TFR = 80

# 浏览器时频图可选方法（M13）：四方法零新依赖（mne×3 + scipy×1）。
# DWT（离散小波）不在列——需新增 pywt 依赖且输出是倍频程带（非线性频率
# 轴），渲染语义与连续时频图差异大（2026-10-14 用户拍板"四方法零依赖"）。
# 注：mne 1.12 三个 tfr_array_* 均挂 @legacy（统一入口 compute_tfr 存在），
# array 版仍完全可用，项目沿用（M8 起先例）。
TFR_METHODS = ("morlet", "multitaper", "stockwell", "stft")

# 频率上限约束：唯一的物理上限是 Nyquist（sfreq/2）——mne 侧超限抛
# ValueError、stockwell 静默截断，统一在此钳制。0.49 系数留 1% 安全边。
# 默认上界 150Hz（2026-10-14 二次用户裁定：默认回到 150——覆盖典型脑电
# 频段；更高范围如肌电/尖波由用户在设置窗显式调高，上限只受 Nyquist）
TFR_FMAX_DEFAULT = 150.0
TFR_FMAX_NYQ_RATIO = 0.49


@dataclass
class TfrConfig:
    """浏览器时频图的计算配置（M13）——纯 dataclass，UI↔计算层共用.

    各参数按方法生效（不适用的被忽略）：
    - ``method``：四方法之一（TFR_METHODS）。
    - ``fmin/fmax/n_freqs``：公共频率范围与输出行数（四方法统一输出行数，
      线性轴方法分段 max 池化到 n_freqs 行）。fmax=None = **默认 150Hz**
      （受 Nyquist 钳制；更高范围由用户显式设 fmax 调高，上限=Nyquist×0.49）。
    - ``n_cycles_scale``：morlet/multitaper 的 n_cycles = max(f/scale, 2)
      （小 = 时间分辨率高；默认 2.0 = M8 起的 f/2 惯例）。
    - ``time_bandwidth``：multitaper（2–8，大 = 频率分辨率高、方差低）。
    - ``width``：stockwell（>1 频率分辨率高、<1 时间分辨率高）。
    - ``win_s/overlap``：stft 窗长（秒）与重叠比例。
    """

    method: str = "morlet"
    fmin: float = 2.0
    fmax: Optional[float] = None
    n_freqs: int = 40
    n_cycles_scale: float = 2.0
    time_bandwidth: float = 4.0
    width: float = 1.0
    win_s: float = 0.5
    overlap: float = 0.5

    def effective_fmax(self, sfreq: float) -> float:
        """实际上限：默认 150（够 Nyquist 时），显式可调高至 Nyquist×0.49.

        mne 侧（morlet/multitaper）超 Nyquist 抛 ValueError、stockwell 静默
        截断到 Nyquist 附近——两种失败模式不一致，统一在配置层钳制。
        fmax=None → min(150, Nyquist×0.49)；显式 fmax → min(fmax, 同钳制)
        （500Hz 文件默认 150、显式可到 245）。
        """
        cap = sfreq * TFR_FMAX_NYQ_RATIO
        default = min(TFR_FMAX_DEFAULT, cap)
        want = default if self.fmax is None else float(self.fmax)
        return min(want, cap)

    def min_window_s(self) -> float:
        """当前方法/参数下可计算的最短窗口（秒）——UI 短窗守卫用.

        - morlet/multitaper：2.0（2Hz 小波核 ≈1.6s + 余量，M12 实证 mne
          "wavelet longer than signal" 边界）；
        - stockwell：1.0（n_fft ≥ 信号长度，实测 2s@250Hz 可算、0.5s 也
          可——取 1.0 保守下限）；
        - stft：2×win_s（窗 + 至少一个重叠步进）。
        """
        if self.method == "stft":
            return 2.0 * self.win_s
        if self.method == "stockwell":
            return 1.0
        return 2.0


def _db_peak_normalized(power: np.ndarray) -> np.ndarray:
    """功率 → dB 并逐频点减自身峰值（浏览器无基线口径，M12 起）.

    db.max(axis=时间) == 0：色标读数是"相对该频点峰值的 dB"，纵向频率
    间可比。下限 1e-40 防 log(0)。
    """
    db = 10.0 * np.log10(np.maximum(power, 1e-40))
    return db - db.max(axis=1, keepdims=True)


def _pool_rows(a: np.ndarray, n: int, axis: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """沿 axis 分段取最大抽到 n 行（保窄峰）+ 各段的段中心索引.

    线性轴方法（stockwell 数千格 / stft 上百格）抽到统一行数时，**均匀
    抽样会漏掉窄于行距的谱峰**（实测 stockwell 1933 格抽 40 行、行距
    ≈2.9Hz，10Hz 正弦的 0.06Hz 窄峰恰被抽丢）——改分段 max 池化：每输出
    行 = 该频带内的最大值（"该频带内最强"，显示语义合理且峰不丢）。
    返回 (池化数组, 各段中心的原始索引)。
    """
    size = a.shape[axis]
    if size <= n:
        return a, np.arange(size)
    edges = np.linspace(0, size, n + 1)
    starts = edges[:-1].astype(int)
    ends = edges[1:].astype(int)
    segs = [(s, e) for s, e in zip(starts, ends) if e > s]
    out = np.stack([
        np.take(a, np.arange(s, e), axis=axis).max(axis=axis) for s, e in segs
    ])
    centers = np.array([(s + e - 1) // 2 for s, e in segs])
    return out, centers


def compute_window_tfr(
    data: np.ndarray,
    sfreq: float,
    times: np.ndarray,
    cfg: TfrConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """浏览器同段时频图统一入口（M13）：单通道窗口 → (freqs, times, db).

    :param data: [n_times] 一维（伏特）——浏览器当前窗口单通道。
    :param times: 窗口时间轴（秒，恒 ≥0——浏览器无事件基线）。
    :param cfg: 方法与参数（TfrConfig）。
    :returns: (freqs[n_freq], times[n_t'], db[n_freq, n_t'])——db 为每频点
        减峰值的 dB（_db_peak_normalized 口径，四方法一致）。stft 的
        times 为窗中心时刻（比窗口短——首尾各让半个窗）。
    """
    if data.ndim != 1:
        raise ValueError(f"data 应为一维 [n_times]，收到形状 {data.shape}")
    if cfg.method not in TFR_METHODS:
        raise ValueError(f"未知时频方法 {cfg.method!r}——可用：{TFR_METHODS}")
    fmax = cfg.effective_fmax(sfreq)
    x3 = data.reshape(1, 1, -1)

    if cfg.method in ("morlet", "multitaper"):
        freqs = default_tfr_freqs(cfg.fmin, fmax, cfg.n_freqs)
        n_cycles = np.maximum(freqs / cfg.n_cycles_scale, 2.0)
        if cfg.method == "morlet":
            power = tfr_array_morlet(
                x3, sfreq, freqs, n_cycles=n_cycles, output="power",
                zero_mean=True, verbose="ERROR",
            )
        else:
            power = tfr_array_multitaper(
                x3, sfreq, freqs, n_cycles=n_cycles,
                time_bandwidth=cfg.time_bandwidth, output="power",
                zero_mean=True, verbose="ERROR",
            )
        return freqs, times, _db_peak_normalized(power[0, 0])

    if cfg.method == "stockwell":
        # 返回恒 3 元组 (psd, itc, freqs)（return_itc=False 时 itc=None）；
        # psd (n_ch, n_freq, n_t) 频率轴线性、分辨率 = sfreq/n_fft（数千格）
        psd, _itc, freqs = tfr_array_stockwell(
            x3, sfreq, fmin=cfg.fmin, fmax=fmax, width=cfg.width,
            verbose="ERROR",
        )
        power = psd[0]  # [n_freq_native, n_times]
        power_p, centers = _pool_rows(power, cfg.n_freqs, axis=0)
        return freqs[centers], times, _db_peak_normalized(power_p)

    # stft：scipy 滑窗 FFT——|Zxx|² 即功率谱密度热图；times 为窗中心
    nperseg = max(int(round(cfg.win_s * sfreq)), 8)
    noverlap = min(int(round(nperseg * cfg.overlap)), nperseg - 1)
    f, t, zxx = scipy_stft(
        data, fs=sfreq, window="hann", nperseg=nperseg, noverlap=noverlap,
        detrend=False,
    )
    band = (f >= cfg.fmin) & (f <= fmax)
    power = (np.abs(zxx) ** 2)[band]  # [n_band, n_t']
    power_p, centers = _pool_rows(power, cfg.n_freqs, axis=0)
    # scipy 的 t 是**相对窗口起点**的时间（从 0 起）；morlet/stockwell 分支返回
    # 的是调用方传入的绝对秒——统一口径：平移回绝对时间（否则窗口在 [30,40]
    # 这类位置时热图被画到时间轴 0-10s 处、落在视口外=「图没加载」，
    # 2026-10-14 用户真窗口实测暴露；离屏默认 [0,10] 窗口碰巧撞对）
    return f[band][centers], t + times[0], _db_peak_normalized(power_p)


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
