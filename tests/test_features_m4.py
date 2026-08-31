"""M4 特征层测试：crop 步骤 + 三提取器 + FeatureTable + 序列化.

合成断言基于 conftest 的 synthetic_raw（ch0/ch1 含 10Hz 正弦 → α 频段主导；
事件 onset 10/20/30s，code T0/T1/T2）。
"""

from __future__ import annotations

import numpy as np
import pytest

from dataloadv.batch import FeatureTable
from dataloadv.core.recording import EventTable
from dataloadv.features import (
    FEATURE_REGISTRY,
    apply_features,
    feature_from_dict,
    feature_to_dict,
)
from dataloadv.features.base import FeatureError
from dataloadv.features.spectral import array_welch, parse_bands
from dataloadv.proc import STEP_REGISTRY, ProcessingContext, StepError, apply_pipeline


def make_ctx(synthetic_raw) -> ProcessingContext:
    return ProcessingContext(
        raw=synthetic_raw.copy(), events=EventTable.from_mne_annotations(synthetic_raw)
    )


# ---------------------------------------------------------------------- crop
class TestCrop:
    def test_crop_raw_duration_and_events(self, synthetic_raw):
        """裁到 [5, 25]s：时长 20s；窗口内事件（10/20s）保留、窗外（30s）丢弃."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("crop", STEP_REGISTRY["crop"].make_params({"tmin": 5.0, "tmax": 25.0}))])
        assert abs(ctx.raw.times[-1] - 20.0) < 0.02
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 1.0}))])
        assert len(ctx.epochs) == 2  # T0@10s + T1@20s；T2@30s 在窗外

    def test_tmax_none_means_to_end(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("crop", STEP_REGISTRY["crop"].make_params({"tmin": 30.0}))])
        assert abs(ctx.raw.times[-1] - 30.0) < 0.02

    def test_tmax_beyond_data_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("crop", STEP_REGISTRY["crop"].make_params({"tmin": 0.0, "tmax": 99.0}))])
        assert "超出数据长度" in str(ei.value)

    def test_tmin_beyond_data_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("crop", STEP_REGISTRY["crop"].make_params({"tmin": 60.0}))])
        assert "不小于数据长度" in str(ei.value)

    def test_crop_epochs_relative_time(self, synthetic_raw):
        """epochs 阶段：裁剪是相对事件锚点的——每段只留 [0, 1]s."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [
            ("epoching", STEP_REGISTRY["epoching"].make_params({"tmin": -1.0, "tmax": 2.0})),
            ("crop", STEP_REGISTRY["crop"].make_params({"tmin": 0.0, "tmax": 1.0})),
        ])
        assert len(ctx.epochs) == 3
        assert abs(ctx.epochs.tmin) < 1e-9 and abs(ctx.epochs.tmax - 1.0) < 1e-9
        assert ctx.epochs.get_data().shape[2] == pytest.approx(251, abs=1)

    def test_crop_epochs_to_empty_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 2.0}))])
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("crop", STEP_REGISTRY["crop"].make_params({"tmin": 5.0}))])
        assert "分段数为 0" in str(ei.value)


# ------------------------------------------------------------------ 频带功率
class TestBandPower:
    def _rows(self, ctx, **overrides):
        params = FEATURE_REGISTRY["bandpower"].make_params(overrides)
        return apply_features(ctx, [("bandpower", params)]).scalars

    def test_alpha_dominates_for_10hz_sine(self, synthetic_raw):
        """ch0 是 10Hz 正弦：α 功率应为五个标准频段中最大（显著 > 其他）."""
        ctx = make_ctx(synthetic_raw)
        rows = self._rows(ctx)
        by = {(r["channel"], r["feature"]): r["value"] for r in rows}
        powers = {b: by[("EEG00", b)] for b in ("delta", "theta", "alpha", "beta", "gamma")}
        assert max(powers, key=powers.get) == "alpha"
        assert powers["alpha"] > 10 * max(v for k, v in powers.items() if k != "alpha")

    def test_relative_powers_sum_to_one(self, synthetic_raw):
        """相对功率和 ≈ 1：标准频段 1-45Hz 相对分析带 0.5-45Hz 有 0.5Hz 缺口，
        且频段边界点被相邻两段 trapz 各计一半——容差 5e-3."""
        ctx = make_ctx(synthetic_raw)
        rows = self._rows(ctx, relative=True)
        vals = [r["value"] for r in rows if r["channel"] == "EEG00" and r["epoch_index"] is None]
        assert sum(vals) == pytest.approx(1.0, abs=5e-3)
        assert all(r["feature"].endswith("_rel") for r in rows)

    def test_log10_suffix(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        plain = {(r["channel"], r["feature"]): r["value"] for r in self._rows(ctx, bands=["alpha"])}
        logged = {(r["channel"], r["feature"]): r["value"] for r in self._rows(ctx, bands=["alpha"], log10=True)}
        assert ("EEG00", "alpha_log") in logged
        assert logged[("EEG00", "alpha_log")] == pytest.approx(np.log10(plain[("EEG00", "alpha")]), rel=1e-9)

    def test_custom_band_syntax(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        rows = self._rows(ctx, bands=["mu:8-12"])
        assert {r["feature"] for r in rows} == {"mu"}
        # mu(8-12) 覆盖 10Hz 峰 → 与 alpha(8-13) 同量级
        alpha = {(r["channel"], r["feature"]): r["value"] for r in self._rows(ctx, bands=["alpha"])}
        assert rows[0]["value"] == pytest.approx(alpha[("EEG00", "alpha")], rel=0.5)

    def test_unknown_band_refused(self, synthetic_raw):
        with pytest.raises(FeatureError) as ei:
            parse_bands(["spindle"])
        assert "无法解析" in str(ei.value)

    def test_band_outside_range_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError) as ei:
            self._rows(ctx, bands=["high:200-300"], fmax=45.0)
        assert "不在分析范围" in str(ei.value)

    def test_unknown_channel_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError) as ei:
            self._rows(ctx, channels=["不存在的通道"])
        assert "不存在" in str(ei.value)

    def test_bads_excluded_by_default(self, synthetic_raw):
        """默认通道=数据通道排除坏道：标记 EEG00 后特征表不再有它."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("bads", STEP_REGISTRY["bads"].make_params({"channels": ["EEG00"]}))])
        rows = self._rows(ctx, bands=["alpha"])
        assert {r["channel"] for r in rows} == {f"EEG{i:02d}" for i in range(1, 8)}

    def test_epochs_one_row_per_epoch(self, synthetic_raw):
        """epochs 逐段：3 段 × 8 通道 × 1 频段 = 24 行，段序号/事件码正确."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 2.0}))])
        rows = self._rows(ctx, bands=["alpha"])
        assert len(rows) == 24
        assert {r["epoch_index"] for r in rows} == {0, 1, 2}
        assert {r["event_code"] for r in rows} == {"T0", "T1", "T2"}

    # -------------------------------------------------- M8：时间分辨 time_windows

    @staticmethod
    def _time_resolved_raw():
        """10s 合成：ch0 前 5s 纯噪声、后 5s 叠 10Hz α（raw 绝对窗考题）."""
        import mne

        sf = 250.0
        t = np.arange(int(sf * 10)) / sf
        rng = np.random.default_rng(7)
        data = rng.normal(0, 5e-6, (2, len(t)))
        data[0, t >= 5.0] += 25e-6 * np.sin(2 * np.pi * 10.0 * t[t >= 5.0])
        return mne.io.RawArray(data, mne.create_info(["A", "B"], sf, "eeg"),
                               verbose="ERROR")

    def test_time_windows_abs_on_raw(self):
        """raw 绝对窗：整段条目 + 两个窗条目并存；后 5s 窗的 α ≫ 前 5s 窗."""
        ctx = ProcessingContext(raw=self._time_resolved_raw(), stage="raw")
        rows = self._rows(ctx, bands=["alpha"], time_windows=["0-5", "5-10"])
        by = {(r["channel"], r["feature"]): r["value"] for r in rows}
        assert set(by) == {
            ("A", "alpha"), ("B", "alpha"),  # 整段摘要条目始终在（spans 首项）
            ("A", "alpha@0-5s"), ("A", "alpha@5-10s"),
            ("B", "alpha@0-5s"), ("B", "alpha@5-10s"),
        }
        assert by[("A", "alpha@5-10s")] > 50 * by[("A", "alpha@0-5s")]
        # 默认（空窗）＝ M4 行为：特征名裸频段、整段一条
        plain = self._rows(ctx, bands=["alpha"])
        assert {r["feature"] for r in plain} == {"alpha"}

    def test_time_windows_relative_on_epochs(self, synthetic_raw):
        """epochs 相对窗：窗坐标=事件锚点系（-1-0 / 0-2），行数=段×通道×窗.

        ch0 全程 10Hz 正弦（平稳）：Welch 是密度归一（V²/Hz），频带积分对
        窗长不敏感——两窗功率应近似相等（窗长只改频率分辨率/方差）。
        """
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": -1.0, "tmax": 2.0}))])
        rows = self._rows(ctx, bands=["alpha"], channels=["EEG00"],
                          time_windows=["-1-0", "0-2"])
        feats = {r["feature"] for r in rows}
        assert feats == {"alpha", "alpha@-1-0s", "alpha@0-2s"}  # 整段条目+两窗
        assert len(rows) == 3 * 3  # 3 段 × (整段 + 2 窗)
        by = {(r["epoch_index"], r["feature"]): r["value"] for r in rows}
        for ep in range(3):
            w1, w2 = by[(ep, "alpha@-1-0s")], by[(ep, "alpha@0-2s")]
            assert w2 == pytest.approx(w1, rel=0.3)  # 平稳密度不变式

    def test_time_windows_out_of_range_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError, match="超出数据时间范围"):
            self._rows(ctx, time_windows=["55-65"])  # 60s 录制，65 越界

    def test_time_windows_too_few_samples_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError, match="不足 2 个采样点"):
            self._rows(ctx, time_windows=["10-10.001"])  # 250Hz 下 0 个整点


# ------------------------------------------------------------------ 时域统计
class TestTimeDomain:
    def _rows(self, ctx, **overrides):
        params = FEATURE_REGISTRY["timedomain"].make_params(overrides)
        return apply_features(ctx, [("timedomain", params)]).scalars

    def test_rms_matches_math(self, synthetic_raw):
        """ch0 = 20µV 正弦 + 5µV 噪声：rms = sqrt((20/√2)² + 5²) ≈ 15µV."""
        ctx = make_ctx(synthetic_raw)
        rows = self._rows(ctx, stats=["rms_uv"])
        v = next(r["value"] for r in rows if r["channel"] == "EEG00" and r["epoch_index"] is None)
        assert 12.0 < v < 18.0

    def test_ptp_and_zc_rate(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        rows = self._rows(ctx, stats=["ptp_uv", "zc_rate"])
        by = {(r["channel"], r["feature"]): r["value"] for r in rows}
        # 峰峰值 ≥ 2×正弦幅度（40µV），噪声使实际略大但不至于翻倍
        assert by[("EEG00", "ptp_uv")] > 40.0
        # 10Hz 正弦每秒过零 20 次（噪声抖动被阈值滞回抑制）
        assert 18.0 < by[("EEG00", "zc_rate")] < 24.0

    def test_unknown_stat_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError) as ei:
            self._rows(ctx, stats=["median_uv"])
        assert "未知统计量" in str(ei.value)

    def test_epochs_per_epoch_stats(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 2.0}))])
        rows = self._rows(ctx, stats=["rms_uv"])
        assert len(rows) == 24  # 3 段 × 8 通道


# ------------------------------------------------------------------ PSD 曲线
class TestWelchPsd:
    def _curves(self, ctx, **overrides):
        params = FEATURE_REGISTRY["welch_psd"].make_params(overrides)
        return apply_features(ctx, [("welch_psd", params)]).curves

    def test_default_all_channels_and_peak(self, synthetic_raw):
        """M8.3：留空=全部数据通道逐通道各一条（通道平均语义已废）.

        纯 10Hz 通道（EEG00）的谱峰应在 10Hz；全量窗的 window=""（新字段）。
        """
        ctx = make_ctx(synthetic_raw)
        curves = self._curves(ctx)
        assert len(curves) == 8  # 8 通道 × 全量 1 窗
        assert [c["channel"] for c in curves] == [f"EEG{i:02d}" for i in range(8)]
        assert all(c["window"] == "" for c in curves)
        c0 = next(c for c in curves if c["channel"] == "EEG00")
        assert c0["freqs"][np.argmax(c0["psd"])] == pytest.approx(10.0, abs=1.0)

    def test_per_channel_curves(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        params = FEATURE_REGISTRY["welch_psd"].make_params({"channels": ["EEG00", "EEG01"]})
        result = apply_features(ctx, [("welch_psd", params)])
        assert [c["channel"] for c in result.curves] == ["EEG00", "EEG01"]

    def test_time_windows_subwindows(self, synthetic_raw):
        """时间窗 0-30：全量 8 条（window=""）+ 子窗 8 条（"@0-30s"）.

        ch0 平稳 10Hz 正弦：子窗谱峰仍在 10Hz（平稳信号窗不改变峰位）。
        """
        ctx = make_ctx(synthetic_raw)
        curves = self._curves(ctx, time_windows=["0-30"])
        assert len(curves) == 16
        assert sum(c["window"] == "" for c in curves) == 8
        assert sum(c["window"] == "@0-30s" for c in curves) == 8
        sub = next(c for c in curves if c["channel"] == "EEG00" and c["window"])
        assert sub["freqs"][np.argmax(sub["psd"])] == pytest.approx(10.0, abs=1.0)

    def test_time_windows_out_of_range_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError, match="超出数据时间范围"):
            self._curves(ctx, time_windows=["55-65"])  # 60s 录制，65 越界

    def test_time_windows_too_few_samples_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(FeatureError, match="不足 2 个采样点"):
            self._curves(ctx, time_windows=["10-10.001"])  # 250Hz 下 0 个整点

    def test_refused_on_epochs_stage(self, synthetic_raw):
        """PSD 曲线仅 raw：epochs 阶段给中文阶段错误."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 1.0}))])
        with pytest.raises(FeatureError) as ei:
            apply_features(ctx, [("welch_psd", FEATURE_REGISTRY["welch_psd"].default_params())])
        assert "只支持连续数据" in str(ei.value)


# ------------------------------------------------------------ 序列化 / 表
class TestRegistryAndTable:
    def test_serialization_roundtrip(self):
        feats = [(fid, fx.default_params()) for fid, fx in FEATURE_REGISTRY.items()]
        dumped = [feature_to_dict(f, p) for f, p in feats]
        loaded = [feature_from_dict(d) for d in dumped]
        assert [(f, p.model_dump()) for f, p in loaded] == [(f, p.model_dump()) for f, p in feats]
        assert all(isinstance(d["params"], dict) for d in dumped)  # JSON 可序列化

    def test_unknown_feature_refused(self):
        with pytest.raises(FeatureError) as ei:
            feature_from_dict({"feature": "nonexistent", "params": {}})
        assert "未知特征提取器" in str(ei.value)

    def test_table_long_and_wide(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        res = apply_features(ctx, [
            ("bandpower", FEATURE_REGISTRY["bandpower"].make_params({"bands": ["alpha", "beta"]})),
            ("timedomain", FEATURE_REGISTRY["timedomain"].make_params({"stats": ["rms_uv"]})),
            ("welch_psd", FEATURE_REGISTRY["welch_psd"].default_params()),
        ])
        table = FeatureTable()
        table.add_result(res, "test.gdf", "S01")
        assert len(table) == 8 * 3  # 8 通道 × (2 频段 + 1 统计量)
        assert table.n_recordings == 1 and table.recording_names() == ["test.gdf"]
        assert len(table.curves) == 8  # M8.3：留空=逐通道各一条
        wide = table.to_wide()
        assert wide.shape == (8, 3 + 5)  # 8 行（通道）× 3 特征列 + 5 索引列
        assert {"alpha", "beta", "rms_uv"} <= set(wide.columns)

    def test_table_multi_recording(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        res = apply_features(ctx, [("bandpower", FEATURE_REGISTRY["bandpower"].make_params({"bands": ["alpha"]}))])
        table = FeatureTable()
        table.add_result(res, "a.gdf", "S01")
        table.add_result(res, "b.gdf", "S02")
        assert table.n_recordings == 2
        assert len(table) == 16
        assert set(table.df["recording"]) == {"a.gdf", "b.gdf"}

    def test_array_welch_shapes(self, synthetic_raw):
        """array_welch 的 2D/3D 广播：一次调用算全部通道/段."""
        data2d = synthetic_raw.get_data(picks=[0, 1])
        f, p = array_welch(data2d, 250.0, fmax=45.0)
        assert p.shape == (2, f.size)
        f3, p3 = array_welch(data2d[None].repeat(3, 0), 250.0, fmax=45.0)
        assert p3.shape == (3, 2, f3.size)
