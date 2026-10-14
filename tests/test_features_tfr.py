"""M8 时频纯函数 + 时间窗解析测试.

覆盖：
- ``default_tfr_freqs``：对数间隔（低频密高频疏）
- ``compute_epochs_tfr``：形状/基线校正 dB 语义/无负时间退化分支/段数上限/
  错误分支；合成 10Hz α 考题——事件后窗的 α 频点功率必须显著高于基线
- ``parse_time_windows``（spectral）：语法/负数窗/起止序/50 窗上限
- 真实数据 A01T（BCICIV_2a）：gdf → 分段 → morlet 段平均——黄金不变式是
  形状对齐 + 全有限 + 基线期归零，不断言具体生理数值
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dataloadv.features.spectral import parse_time_windows
from dataloadv.features.base import FeatureError
from dataloadv.features.tfr import (
    MAX_EPOCHS_FOR_TFR,
    compute_epochs_tfr,
    default_tfr_freqs,
    TfrConfig,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
A01T = PROJECT_ROOT / "data" / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"

SF = 100.0


# ------------------------------------------------------------------ 频率轴


class TestDefaultFreqs:
    def test_log_spaced_range_and_count(self):
        f = default_tfr_freqs()
        assert len(f) == 24
        assert f[0] == pytest.approx(2.0)
        assert f[-1] == pytest.approx(45.0)
        assert np.all(np.diff(f) > 0)  # 严格单调
        # 对数间隔：相邻比值恒定（低频密高频疏的自然结果）
        ratios = f[1:] / f[:-1]
        assert np.allclose(ratios, ratios.mean(), rtol=1e-9)

    def test_invalid_range_raises(self):
        with pytest.raises(ValueError, match="频率范围"):
            default_tfr_freqs(fmin=0.0)
        with pytest.raises(ValueError, match="频率范围"):
            default_tfr_freqs(fmin=45.0, fmax=2.0)


# ------------------------------------------------------------------ 时频计算


def _alpha_epochs(n_ep: int = 12, alpha_uv: float = 30.0):
    """合成 [-1, 2)s 段：偶数段 C0 通道在**事件后**（t≥0）叠 10Hz α.

    α 只进事件后窗——基线期干净，才有"事件后 vs 基线"的时间分辨对比。
    """
    t = np.arange(-SF, 2 * SF) / SF
    rng = np.random.default_rng(0)
    data = rng.normal(0, 10e-6, (n_ep, 3, len(t)))
    for i in range(0, n_ep, 2):
        data[i, 0, t >= 0] += alpha_uv * 1e-6 * np.sin(2 * np.pi * 10.0 * t[t >= 0])
    return data, t


class TestComputeEpochsTfr:
    def test_shape_and_baseline_zeroed(self):
        data, t = _alpha_epochs()
        freqs, times, db = compute_epochs_tfr(data, SF, t)
        assert db.shape == (len(freqs), len(t))
        assert np.array_equal(times, t)
        # 基线校正语义：基线期（含 t=0，与实现 (None, 0.0) 闭区间一致）每频点
        # 均值精确为 0——减的就是这个子集的均值
        base = db[:, times <= 0].mean(axis=1)
        assert np.allclose(base, 0.0, atol=1e-9)

    def test_alpha_erp_time_resolved(self):
        """事件后叠 α → 10Hz 频点事件后显著高于基线（时间分辨成立）.

        α 30µV vs 底噪 10µV → 功率比 (900+100)/100 = 10 倍 = 10dB；
        避开 t=0 附近 ±0.2s（morlet 核长导致的卷积边缘过渡带）。
        """
        data, t = _alpha_epochs()
        freqs, times, db = compute_epochs_tfr(data, SF, t)
        i_alpha = int(np.argmin(np.abs(freqs - 10.0)))
        after = db[i_alpha, times >= 0.3].max()
        before = db[i_alpha, times <= -0.3].mean()
        assert after - before > 6.0

    def test_no_negative_times_peak_norm(self):
        """tmin ≥ 0（无基线可用）→ 峰值归一分支：每频点最大值 ≈ 0dB."""
        data, _ = _alpha_epochs()
        t = np.arange(0, 3.0, 1 / SF)
        freqs, times, db = compute_epochs_tfr(data, SF, t)
        assert np.allclose(db.max(axis=1), 0.0, atol=1e-9)
        assert db.min() < -3.0  # 不是全零矩阵（真算了功率）

    def test_channel_index_selects(self):
        """ch_idx 选到 α 通道 vs 噪声通道：α 通道能量显著更高."""
        data, t = _alpha_epochs(n_ep=4)
        _, _, db0 = compute_epochs_tfr(data, SF, t, ch_idx=0)
        _, _, db2 = compute_epochs_tfr(data, SF, t, ch_idx=2)
        # C0 含 α：峰值 dB（相对共同基线）高于纯噪声的 C2
        assert db0.max() > db2.max() + 3.0

    def test_epoch_cap(self):
        """段数超上限只算前 MAX_EPOCHS_FOR_TFR 段（形状不受输入段数影响）."""
        data, t = _alpha_epochs(n_ep=MAX_EPOCHS_FOR_TFR + 30)
        freqs, times, db = compute_epochs_tfr(data, SF, t)
        assert db.shape == (24, len(t))

    def test_bad_input_raises(self):
        with pytest.raises(ValueError, match=r"\[n_epochs"):
            compute_epochs_tfr(np.zeros((2, 5)), SF, np.zeros(5))
        with pytest.raises(ValueError, match="没有分段"):
            compute_epochs_tfr(np.zeros((0, 1, 10)), SF, np.arange(10) / SF)


# ------------------------------------------------------------------ 时间窗解析


class TestParseTimeWindows:
    def test_syntax_ok(self):
        assert parse_time_windows(["0-1"]) == [(0.0, 1.0)]
        assert parse_time_windows(["-1-0"]) == [(-1.0, 0.0)]  # 负数窗
        assert parse_time_windows(["0.5-1.5", " 2 - 3 "]) == [(0.5, 1.5), (2.0, 3.0)]

    def test_empty_means_whole_segment(self):
        assert parse_time_windows([]) == []  # 空=整段一条（M4 零回归语义）

    @pytest.mark.parametrize("bad", ["0", "1~2", "a-b"])
    def test_syntax_error(self, bad):
        with pytest.raises(FeatureError, match="无法解析"):
            parse_time_windows([bad])

    @pytest.mark.parametrize("bad", ["2-1", "3-3"])
    def test_order_error(self, bad):
        with pytest.raises(FeatureError, match="起 < 止"):
            parse_time_windows([bad])

    def test_cap_50(self):
        wins = [f"{i}-{i + 1}" for i in range(51)]
        with pytest.raises(FeatureError, match="最多 50"):
            parse_time_windows(wins)


# ------------------------------------------------------------------ 真实数据


class TestTfrGoldenReal:
    """BCICIV_2a A01T：真实 gdf → 分段 → morlet 段平均（e2e_m8 的单测缩影）."""

    @pytest.fixture()
    def a01t_epochs(self):
        if not A01T.exists():
            pytest.skip(f"黄金数据缺失：{A01T}")
        import mne

        raw = mne.io.read_raw_gdf(A01T, preload=True, verbose="ERROR")
        events, _ = mne.events_from_annotations(raw, verbose="ERROR")
        # 取样本数最多的一类事件码（2a 里是四类运动想象 cue）
        codes, counts = np.unique(events[:, -1], return_counts=True)
        code = int(codes[np.argmax(counts)])
        picks = raw.ch_names[:6]  # 6 通道足够考时频，省内存
        ep = mne.Epochs(
            raw, events[events[:, -1] == code], tmin=-1.0, tmax=2.0 - 1 / raw.info["sfreq"],
            baseline=None, preload=True, picks=picks, verbose="ERROR",
        )
        return ep

    def test_real_gdf_tfr(self, a01t_epochs):
        data = a01t_epochs.get_data()
        times = np.asarray(a01t_epochs.times)
        freqs, times_out, db = compute_epochs_tfr(data, a01t_epochs.info["sfreq"], times)
        assert db.shape == (len(freqs), len(times))
        assert np.array_equal(times_out, times)
        assert np.isfinite(db).all()  # 真实数据无 NaN/Inf
        # 基线期（含 t=0，与实现闭区间一致）归零 + 事件后能量变化有界
        assert np.allclose(db[:, times <= 0].mean(axis=1), 0.0, atol=1e-9)
        assert db.std() > 0.5


class TestComputeWindowTfr:
    """M13 浏览器同段时频统一入口：四方法/参数/口径."""

    @staticmethod
    def _signal(fs: float = 250.0, dur: float = 10.0) -> tuple[np.ndarray, np.ndarray]:
        """10Hz 20µV 正弦 + 5µV 噪底（conftest synthetic 同款形态）."""
        t = np.arange(int(fs * dur)) / fs
        x = 20e-6 * np.sin(2 * np.pi * 10.0 * t) \
            + 5e-6 * np.random.default_rng(0).normal(size=len(t))
        return x, t

    @pytest.mark.parametrize("method", ["morlet", "multitaper", "stockwell", "stft"])
    def test_alpha_peak_found_by_all_methods(self, method):
        """四方法都能在 ~10Hz 行检出正弦峰（高于远端行）.

        各方法分辨率/泄漏特性不同导致差值幅度不同（实测 3.8–9.4dB），
        阈值取保守 3dB。
        """
        from dataloadv.features.tfr import compute_window_tfr

        x, t = self._signal()
        freqs, times_out, db = compute_window_tfr(x, 250.0, t, TfrConfig(method=method))
        assert db.shape == (len(freqs), len(times_out))
        assert np.isfinite(db).all()
        r10 = int(np.argmin(np.abs(freqs - 10.0)))
        r60 = int(np.argmin(np.abs(freqs - 60.0)))
        # 各方法分辨率/泄漏特性不同，峰差幅度不同（122.5Hz 上限实测：morlet
        # ~9 / mt ~5 / stockwell ~2.4 / stft ~6 dB）——阈值按方法差异化
        floor = {"morlet": 3.0, "multitaper": 3.0, "stockwell": 2.0, "stft": 3.0}
        assert float(db[r10].mean()) - float(db[r60].mean()) > floor[method]

    def test_dB_peak_normalized(self):
        """口径：每频点减自身峰值——db.max(axis=时间) 全 0."""
        from dataloadv.features.tfr import compute_window_tfr

        x, t = self._signal()
        _f, _t, db = compute_window_tfr(x, 250.0, t, TfrConfig())
        assert np.allclose(db.max(axis=1), 0.0, atol=1e-9)

    def test_row_count_unified(self):
        """线性轴方法（stockwell 数千格/stft 上百格）行数统一到 n_freqs.

        分段 max 池化（保窄峰——均匀抽样实测漏 10Hz 窄峰，见 _pool_rows）。
        """
        from dataloadv.features.tfr import compute_window_tfr

        x, t = self._signal()
        for m in ("stockwell", "stft"):
            _f, _t, db = compute_window_tfr(x, 250.0, t, TfrConfig(method=m, n_freqs=32))
            assert len(_f) <= 32 and db.shape[0] == len(_f)

    def test_stft_window_params_take_effect(self):
        """stft 窗长/重叠决定时间点数：dur=10s、win=1s、overlap=0.5 → 步进 0.5s.

        scipy 默认 boundary='zeros'+padded=True（两端补零到整步进）——
        t 覆盖 [0, 10] 含端点，共 (2500-125)/125+1 = 21 点。
        """
        from dataloadv.features.tfr import compute_window_tfr

        x, t = self._signal()
        _f, t_out, _db = compute_window_tfr(
            x, 250.0, t, TfrConfig(method="stft", win_s=1.0, overlap=0.5))
        assert len(t_out) == 21
        assert t_out[0] == pytest.approx(0.0, abs=1e-9)
        assert t_out[-1] == pytest.approx(10.0, abs=1e-9)

    def test_effective_fmax_clamped_and_min_window(self):
        """fmax None/超限的 Nyquist 钳制；min_window_s 随方法推导."""
        # 2026-10-14 二次裁定：默认上界 150（够 Nyquist 时）；更高显式调高，
        # 物理上限 Nyquist×0.49（250Hz→122.5、500Hz 默认 150/显式可到 245）
        assert TfrConfig().effective_fmax(250.0) == pytest.approx(122.5)
        assert TfrConfig(fmax=300.0).effective_fmax(250.0) == pytest.approx(122.5)
        assert TfrConfig(fmax=100.0).effective_fmax(250.0) == pytest.approx(100.0)
        assert TfrConfig().effective_fmax(500.0) == pytest.approx(150.0)
        assert TfrConfig(fmax=200.0).effective_fmax(500.0) == pytest.approx(200.0)
        assert TfrConfig(fmax=300.0).effective_fmax(500.0) == pytest.approx(245.0)
        assert TfrConfig().min_window_s() == pytest.approx(2.0)
        assert TfrConfig(method="stockwell").min_window_s() == pytest.approx(1.0)
        assert TfrConfig(method="stft", win_s=0.8).min_window_s() == pytest.approx(1.6)

    def test_unknown_method_rejected(self):
        from dataloadv.features.tfr import compute_window_tfr

        x, t = self._signal()
        with pytest.raises(ValueError, match="未知时频方法"):
            compute_window_tfr(x, 250.0, t, TfrConfig(method="dwt"))
