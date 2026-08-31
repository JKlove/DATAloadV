"""频谱特征：Welch 工具函数 + 频带功率（BandPower）+ PSD 曲线（WelchPsd）.

分层：
- ``mean_welch`` / ``array_welch`` 是纯计算工具（M3 PSD 视图与 M4 特征共用；
  UI 的 psd_view 调前者做通道平均对比，特征提取器一律调后者逐通道）
- ``BandPowerFeature``：δ/θ/α/β/γ + 自定义频段的积分功率——**长表标量**，
  raw 全量一条/通道、epochs 逐段一条/通道（BCI 特征向量的主力）
- ``WelchPsdFeature``：逐通道×逐时间窗的完整 PSD 曲线——**曲线行**，
  仅 raw 阶段（epochs 曲线量爆炸，段级频谱用 BandPower 标量表达）
"""

from __future__ import annotations

import re
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field
from scipy.signal import welch as scipy_welch

from .base import (
    ExtractorResult,
    FeatureError,
    FeatureExtractor,
    pick_channels,
    picks_indices,
    register_feature,
)
from ..proc.context import ProcessingContext

# PSD 默认频率范围：0.5 Hz 以下对电生理意义不大且 log 轴显示困难
FMIN_DEFAULT = 0.5

# 标准临床/BCI 频段（Hz）：名字 → (下限, 上限)。中文标签导出/UI 展示用
STANDARD_BANDS: dict[str, tuple[float, float]] = {
    "delta": (1.0, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 45.0),
}
BAND_LABELS_ZH = {
    "delta": "δ (1-4 Hz)", "theta": "θ (4-8 Hz)", "alpha": "α (8-13 Hz)",
    "beta": "β (13-30 Hz)", "gamma": "γ (30-45 Hz)",
}


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


def array_welch(
    data: np.ndarray,
    sfreq: float,
    fmin: float = FMIN_DEFAULT,
    fmax: Optional[float] = None,
    n_per_seg_s: float = 4.0,
) -> tuple[np.ndarray, np.ndarray]:
    """对数据数组算逐通道 Welch PSD（scipy 沿时间轴广播，一次算完所有通道/段）.

    与 ``mean_welch``（走 mne、取平均）互补：特征提取需要**每通道/每段各自**
    的 PSD，不能先平均。

    :param data: [n_ch, n_times] 或 [n_epochs, n_ch, n_times]，单位 V
    :returns: (freqs[n_f], psd[..., n_f])——形状前缀与输入一致，单位 V²/Hz
    """
    n_per_seg = max(256, int(n_per_seg_s * sfreq))
    n_per_seg = min(n_per_seg, data.shape[-1])  # 短窗数据：整窗做一段
    freqs, psd = scipy_welch(
        data, fs=sfreq, nperseg=n_per_seg, axis=-1,
        average="mean", detrend="constant",
    )
    band = (freqs >= fmin) & (freqs <= (fmax if fmax is not None else sfreq / 2.0))
    return freqs[band], psd[..., band]


# ---------------------------------------------------------------------- 频段解析

# 自定义频段语法：名字:起-止（如 mu:8-12）；起止可为小数
_CUSTOM_BAND_RE = re.compile(r"^\s*([A-Za-z一-鿿][\w一-鿿]*)\s*:\s*([0-9.]+)\s*-\s*([0-9.]+)\s*$")


def parse_bands(spec: list[str]) -> dict[str, tuple[float, float]]:
    """频段参数 → {名字: (下限, 上限)}。标准名直取，自定义用 ``名字:起-止``.

    :raises FeatureError: 名字未知/语法错/上下限非法（中文提示）
    """
    out: dict[str, tuple[float, float]] = {}
    for item in spec:
        if item in STANDARD_BANDS:
            out[item] = STANDARD_BANDS[item]
            continue
        m = _CUSTOM_BAND_RE.match(item)
        if m is None:
            raise FeatureError(
                f"频段「{item}」无法解析。标准名：{'、'.join(STANDARD_BANDS)}；"
                "自定义格式：名字:起-止（如 mu:8-12）"
            )
        name, lo, hi = m.group(1), float(m.group(2)), float(m.group(3))
        if not (0.0 < lo < hi):
            raise FeatureError(f"自定义频段「{item}」的起止频率必须满足 0 < 起 < 止")
        if name in out:
            raise FeatureError(f"频段名「{name}」重复")
        out[name] = (lo, hi)
    return out or dict(STANDARD_BANDS)  # 空列表=全部标准频段（表单清空场景兜底）


# 时间窗语法：起-止（秒，支持负数——epochs 常见 -1 到 0 的事件前基线窗）
_TIME_WIN_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$")


def parse_time_windows(spec: list[str]) -> list[tuple[float, float]]:
    """时间窗参数 → [(起, 止), ...]（秒）.

    语法 ``起-止``（如 ``0-1``、``-1-0``、``0.5-1.5``），逗号分隔多窗；
    epochs 阶段窗相对事件锚点（= mne epochs.times 坐标），raw 阶段为
    录制内绝对秒。空列表 = 整段一条（M4 以来现状，零回归）。

    :raises FeatureError: 语法错/起不小于止/窗数超限（中文提示）。
    """
    out: list[tuple[float, float]] = []
    for item in spec:
        m = _TIME_WIN_RE.match(item)
        if m is None:
            raise FeatureError(
                f"时间窗「{item}」无法解析，格式：起-止（秒，可负，如 0-1、-1-0）"
            )
        lo, hi = float(m.group(1)), float(m.group(2))
        if not (lo < hi):
            raise FeatureError(f"时间窗「{item}」必须满足 起 < 止")
        out.append((lo, hi))
    if len(out) > 50:
        raise FeatureError(f"时间窗最多 50 个（收到 {len(out)}）——长表行数会爆炸")
    return out


def _resolve_spans(
    t_axis: np.ndarray, spec: list[str]
) -> list[tuple[np.ndarray | None, str]]:
    """时间窗参数 → [(样本 mask|None=全量, 窗后缀 "@lo-hi s"|"")]（BandPower/WelchPsd 共用）.

    越界容差=一个采样周期（离散语义：样本 t_i 代表 [t_i, t_i+dt) 的
    信号，故窗 [0, dur) 天然合法——10s 录制输 0-10 不应被拒）；
    窗内 <2 采样点拒。错误消息被 test_features_m4 钉死，改词须同步测试。
    """
    spans: list[tuple[np.ndarray | None, str]] = [(None, "")]
    for lo, hi in parse_time_windows(spec):
        dt = float(np.median(np.diff(t_axis)))
        if lo < t_axis[0] - dt or hi > t_axis[-1] + dt:
            raise FeatureError(
                f"时间窗 {lo:g}-{hi:g}s 超出数据时间范围 "
                f"[{t_axis[0]:g}, {t_axis[-1]:g}]s——请改窗或先调整分段窗长"
            )
        mask = (t_axis >= lo) & (t_axis < hi)
        if int(mask.sum()) < 2:
            raise FeatureError(f"时间窗 {lo:g}-{hi:g}s 内不足 2 个采样点")
        spans.append((mask, f"@{lo:g}-{hi:g}s"))
    return spans


# ------------------------------------------------------------------ 频带功率特征

class BandPowerParams(BaseModel):
    """频带功率参数.

    ``relative``：勾选后输出各频段占 fmin~fmax 总功率的比例（0-1），
    抵消通道间阻抗/增益差异——跨被试对比常用；不勾=绝对功率（µV²）。
    ``log10``：对值取常用对数（值恒正，安全）；功率跨数量级，取对数后
    分布接近正态，统计检验/机器学习输入更友好。
    """

    bands: list[str] = Field(
        default=list(STANDARD_BANDS), title="频段",
        description="标准名 delta/theta/alpha/beta/gamma，或自定义 名字:起-止（如 mu:8-12）；空=全部标准频段",
    )
    relative: bool = Field(
        default=False, title="相对功率",
        description="勾选=各频段占总功率比例（0-1，抵消通道增益差异）；不勾=绝对功率",
    )
    log10: bool = Field(
        default=False, title="对数变换",
        description="勾选=值取 log10（功率跨数量级，取对数便于统计比较）",
    )
    channels: list[str] = Field(
        default=[], title="通道（空=全部数据通道）",
        description="通道名逗号分隔；留空=全部数据通道（自动排除坏道与辅助通道）",
    )
    fmin: float = Field(
        default=FMIN_DEFAULT, title="分析下限频率",
        json_schema_extra={"unit": "Hz", "decimals": 2, "min": 0.0, "max": 500.0},
        description="相对功率的「总功率」在此限与上限之间统计",
    )
    fmax: float = Field(
        default=45.0, title="分析上限频率",
        json_schema_extra={"unit": "Hz", "decimals": 1, "min": 1.0, "max": 1000.0},
    )
    n_per_seg_s: float = Field(
        default=4.0, title="Welch 段长",
        json_schema_extra={"unit": "s", "decimals": 1, "min": 0.5, "max": 30.0},
        description="Welch 每段长度（秒）——决定频率分辨率（2Hz 段长≈0.5Hz 分辨率）",
    )
    time_windows: list[str] = Field(
        default=[], title="时间窗（秒，空=整段）",
        description="M8 时间分辨：逐窗各算一组频带功率，格式 起-止（可负，epochs 相对事件锚点/"
                    "raw 绝对秒），逗号分隔（如 -1-0, 0-1, 1-2）；窗进特征名（bp_alpha@0-1s）",
    )


@register_feature
class BandPowerFeature(FeatureExtractor):
    """频带功率：各频段积分功率（raw 每通道一行×频段；epochs 逐段逐通道）."""

    feature_id = "bandpower"
    label_zh = "频带功率"
    params_cls = BandPowerParams
    applies_to = frozenset({"raw", "epochs"})

    def extract(self, ctx: ProcessingContext, params: BandPowerParams) -> ExtractorResult:
        bands = parse_bands(params.bands)
        channels = pick_channels(ctx, params.channels)
        picks = picks_indices(ctx, channels)
        sfreq = ctx.sfreq
        # 统一取成 [n_epoch_or_1, n_ch, n_times]，raw 在最外层补一维——两阶段
        # 的计算路径完全一致，减少分叉
        if ctx.stage == "raw":
            data = ctx.raw.get_data(picks=picks)[None, ...]
            epoch_ids: list[int | None] = [None]
            codes: list[str | None] = [None]
            # raw 的窗=录制内绝对秒；时间轴自建（等价 arange/sfreq）
            t_axis = np.arange(data.shape[-1], dtype=float) / sfreq
        else:
            data = ctx.epochs.get_data(picks=picks)
            id2code = {v: k for k, v in ctx.epochs.event_id.items()}
            epoch_ids = list(range(len(ctx.epochs)))
            codes = [id2code.get(int(c)) for c in ctx.epochs.events[:, -1]]
            # epochs 的窗=相对事件锚点（mne epochs.times 坐标，tmin 可为负）
            t_axis = np.asarray(ctx.epochs.times, dtype=float)

        # M8 时间分辨：逐窗各算一组频带功率；空=整段一条（M4 现状，零回归）。
        # 窗标记拼进特征名（bp_alpha@0-1s）——长表/导出链零改动。
        # 窗解析/越界/采样点校验与 WelchPsd 共用 _resolve_spans（M8.3 抽取）。
        spans = _resolve_spans(t_axis, params.time_windows)

        result = ExtractorResult()
        for mask, suffix in spans:
            sub = data if mask is None else data[..., mask]
            freqs, psd = array_welch(
                sub, sfreq, params.fmin, params.fmax, params.n_per_seg_s
            )
            # µV²/Hz → 积分后 µV²（特征表以 µV 为基准单位，与浏览器/PSD 视图一致）
            psd_uv = psd * 1e12
            total = np.trapz(psd_uv, freqs, axis=-1)  # [n_epoch, n_ch] 分析带内总功率
            for name, (lo, hi) in bands.items():
                sel = (freqs >= lo) & (freqs <= hi)
                if not sel.any():
                    raise FeatureError(
                        f"频段 {name}（{lo}-{hi} Hz）完全不在分析范围 "
                        f"[{params.fmin:g}, {min(params.fmax, sfreq / 2):g}] Hz 内——"
                        "请检查频段定义或数据采样率"
                    )
                power = np.trapz(psd_uv[..., sel], freqs[sel], axis=-1)  # [n_epoch, n_ch]
                values = power / total if params.relative else power
                if params.log10:
                    values = np.log10(np.maximum(values, 1e-30))  # 下限防 log(0)
                fname = (name + ("_rel" if params.relative else "")
                         + ("_log" if params.log10 else "") + suffix)
                for i_ep in range(values.shape[0]):
                    for i_ch, ch in enumerate(channels):
                        result.scalars.append({
                            "epoch_index": epoch_ids[i_ep],
                            "event_code": codes[i_ep],
                            "channel": ch,
                            "feature": fname,
                            "value": float(values[i_ep, i_ch]),
                        })
        return result


# ------------------------------------------------------------------ PSD 曲线特征

class WelchPsdParams(BaseModel):
    """PSD 曲线参数（M8.3：通道/时间窗都可留空=全量数据逐通道）."""

    channels: list[str] = Field(
        default=[], title="通道（空=全部数据通道）",
        description="留空=全部数据通道，逐通道各一条曲线；指定通道名=仅这些通道",
    )
    time_windows: list[str] = Field(
        default=[], title="时间窗（秒，空=全量）",
        description="raw 绝对秒，格式 起-止（如 0-30），逗号分隔多窗；空=全量数据。"
                    "窗进曲线 window 字段（导出列名/图例带 @起-止s 标记）",
    )
    fmin: float = Field(
        default=FMIN_DEFAULT, title="起始频率",
        json_schema_extra={"unit": "Hz", "decimals": 2, "min": 0.0, "max": 100.0},
    )
    fmax: Optional[float] = Field(
        default=None, title="截止频率",
        description="留空=Nyquist；带外的工频段也常需要看，默认不截",
        json_schema_extra={"unit": "Hz", "decimals": 1, "min": 1.0, "max": 1000.0},
    )
    n_per_seg_s: float = Field(
        default=4.0, title="Welch 段长",
        json_schema_extra={"unit": "s", "decimals": 1, "min": 0.5, "max": 30.0},
    )


@register_feature
class WelchPsdFeature(FeatureExtractor):
    """Welch PSD 曲线（仅 raw 阶段）：逐通道×逐时间窗一条，导出为曲线行.

    M8.3 语义变更：通道留空不再走通道平均（那套口径保留在 M3 对比 PSD 视图
    ``mean_welch``），改为与 BandPower/timedomain 一致的"空=全部数据通道"；
    时间窗留空=全量数据，窗标记 "@lo-hi s" 进曲线 window 字段。
    """

    feature_id = "welch_psd"
    label_zh = "PSD 曲线"
    params_cls = WelchPsdParams
    applies_to = frozenset({"raw"})  # epochs 曲线量爆炸——段级频谱用频带功率

    def extract(self, ctx: ProcessingContext, params: WelchPsdParams) -> ExtractorResult:
        result = ExtractorResult()
        channels = pick_channels(ctx, params.channels)
        picks = picks_indices(ctx, channels)
        data = ctx.raw.get_data(picks=picks)
        # raw 的时间轴=录制内绝对秒（与 BandPower raw 分支同口径，自建等价 arange/sfreq）
        t_axis = np.arange(data.shape[-1], dtype=float) / ctx.sfreq
        for mask, suffix in _resolve_spans(t_axis, params.time_windows):
            sub = data if mask is None else data[..., mask]
            f, psd = array_welch(
                sub, ctx.sfreq, params.fmin, params.fmax, params.n_per_seg_s,
            )
            for i, ch in enumerate(channels):
                result.curves.append({
                    "channel": ch, "window": suffix,
                    "freqs": f, "psd": psd[i] * 1e12,  # → µV²/Hz
                })
        return result
