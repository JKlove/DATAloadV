"""M3 预处理链测试：6 个步骤 + 管线执行 + 序列化 + 真实数据验收.

真实数据测试（``real`` 标记）：2a GDF A01T 分段数 = 288（官方口径，4 类提示事件）；
合成测试基于 conftest 的 synthetic_raw（ch1 含 50Hz 工频，专供陷波断言）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dataloadv.core.recording import EventTable
from dataloadv.features.spectral import mean_welch
from dataloadv.io.registry import open_file
from dataloadv.proc import (
    STEP_REGISTRY,
    ProcessingContext,
    StepError,
    apply_pipeline,
    step_from_dict,
    step_to_dict,
)

DATA = Path(__file__).resolve().parent.parent / "data"
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"


def make_ctx(synthetic_raw) -> ProcessingContext:
    """从合成 raw 建上下文（事件从 annotations 提取）."""
    return ProcessingContext(
        raw=synthetic_raw.copy(), events=EventTable.from_mne_annotations(synthetic_raw)
    )


# ------------------------------------------------------------------ 带通/陷波
class TestFilters:
    def test_notch_kills_50hz(self, synthetic_raw):
        """合成 ch1 有 30µV 50Hz 工频：陷波后 50Hz PSD 至少压掉一个数量级."""
        f, before = mean_welch(synthetic_raw)
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("notch", STEP_REGISTRY["notch"].make_params({"freqs": [50.0]}))])
        _, after = mean_welch(ctx.raw)
        i50 = np.argmin(np.abs(f - 50.0))
        assert before[i50] / after[i50] > 10.0, "50Hz 抑制不足"

    def test_bandpass_attenuates_out_of_band(self, synthetic_raw):
        """带通 8-13Hz 后：10Hz（α 正弦）保留，50Hz 工频被显著压制."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("bandpass", STEP_REGISTRY["bandpass"].make_params({"l_freq": 8.0, "h_freq": 13.0}))])
        f, p = mean_welch(ctx.raw)
        i10, i50 = np.argmin(np.abs(f - 10.0)), np.argmin(np.abs(f - 50.0))
        # 50Hz 已在带外：能量远小于带内 10Hz
        assert p[i50] < p[i10] / 100.0
        assert p[i10] > 1e-12  # α 信号仍在

    def test_bandpass_param_validation(self):
        with pytest.raises(StepError):
            STEP_REGISTRY["bandpass"].make_params({"l_freq": 50.0, "h_freq": 10.0})

    def test_notch_freq_above_nyquist_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("notch", STEP_REGISTRY["notch"].make_params({"freqs": [200.0]}))])
        assert "Nyquist" in str(ei.value)


# -------------------------------------------------------------------- 重参考
class TestReref:
    def test_average_reference_zero_mean(self, synthetic_raw):
        """平均参考后，任一时刻跨通道均值应≈0（mne 语义）."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("reref", STEP_REGISTRY["reref"].make_params({}))])
        data = ctx.raw.get_data()
        assert np.abs(data.mean(axis=0)).max() < 1e-15

    def test_custom_ref_subtracts_channel(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        ch0 = synthetic_raw.get_data(picks=[0])
        apply_pipeline(ctx, [("reref", STEP_REGISTRY["reref"].make_params(
            {"mode": "custom", "ref_channels": ["EEG00"]}))])
        # 以 EEG00 为参考：除参考道自身归零，其余道 = 原值 - ch0
        data = ctx.raw.get_data()
        assert np.allclose(data[0], 0.0, atol=1e-15)
        assert np.allclose(data[1], synthetic_raw.get_data(picks=[1])[0] - ch0[0], atol=1e-12)

    def test_unknown_ref_channel(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("reref", STEP_REGISTRY["reref"].make_params(
                {"mode": "custom", "ref_channels": ["不存在的通道"]}))])
        assert "不存在" in str(ei.value)


# -------------------------------------------------------------------- 降采样
class TestResample:
    def test_downsample_halves(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        n0 = ctx.raw.n_times
        apply_pipeline(ctx, [("resample", STEP_REGISTRY["resample"].make_params({"sfreq": 125.0}))])
        assert ctx.sfreq == 125.0
        assert abs(ctx.raw.n_times - n0 / 2) <= 1
        assert abs(ctx.raw.times[-1] - synthetic_raw.times[-1]) < 0.02  # 时长不变

    def test_upsample_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("resample", STEP_REGISTRY["resample"].make_params({"sfreq": 500.0}))])
        assert "升采样" in str(ei.value)


# ---------------------------------------------------------------------- 坏道
class TestBads:
    def test_mark_bads(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("bads", STEP_REGISTRY["bads"].make_params(
            {"channels": ["EEG01", "EEG02"], "action": "mark"}))])
        assert set(ctx.raw.info["bads"]) == {"EEG01", "EEG02"}

    def test_mark_idempotent(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        p = STEP_REGISTRY["bads"].make_params({"channels": ["EEG01"]})
        apply_pipeline(ctx, [("bads", p)]); apply_pipeline(ctx, [("bads", p)])
        assert ctx.raw.info["bads"] == ["EEG01"]  # 重复执行不累积

    def test_unknown_channel_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("bads", STEP_REGISTRY["bads"].make_params({"channels": ["XX"]}))])
        assert "不存在" in str(ei.value)

    def test_empty_channels_refused(self, synthetic_raw):
        """空坏道列表：默认值可构造（表单需要），执行时明确拒绝."""
        assert STEP_REGISTRY["bads"].make_params({"channels": []}).channels == []
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("bads", STEP_REGISTRY["bads"].make_params({"channels": []}))])
        assert "坏道列表为空" in str(ei.value)


# ---------------------------------------------------------------------- 分段
class TestEpoching:
    def test_epoch_count_and_classes(self, synthetic_raw):
        """3 事件（T0/T1/T2）只留 T1/T2 → 2 段；类别与顺序正确."""
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"event_codes": ["T1", "T2"], "tmin": -1.0, "tmax": 2.0}))])
        assert ctx.stage == "epochs" and ctx.raw is None
        assert len(ctx.epochs) == 2
        assert len(ctx.epochs.times) == int(3.0 * 250) + 1  # -1..2s 共 3s

    def test_all_codes_when_empty(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
            {"tmin": 0.0, "tmax": 1.0}))])
        assert len(ctx.epochs) == 3  # T0/T1/T2 全保留

    def test_reject_uv_drops_noisy(self, synthetic_raw):
        """把 reject 阈值压到远小于信号幅度 → 所有段被丢弃 → 明确中文报错."""
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
                {"tmin": 0.0, "tmax": 1.0, "reject_uv": 0.001}))])
        assert "分段结果为空" in str(ei.value)

    def test_unknown_code_refused(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
                {"event_codes": ["T9"]}))])
        assert "不存在" in str(ei.value)

    def test_no_events_refused(self, synthetic_raw):
        ctx = ProcessingContext(raw=synthetic_raw.copy(), events=EventTable())
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params({}))])
        assert "没有事件" in str(ei.value)


# ------------------------------------------------------------ 管线/序列化/阶段
class TestPipeline:
    def test_full_chain_and_stage_guard(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        spec = [
            ("bandpass", STEP_REGISTRY["bandpass"].make_params({"l_freq": 1.0, "h_freq": 100.0})),
            ("notch", STEP_REGISTRY["notch"].make_params({"freqs": [50.0]})),
            ("reref", STEP_REGISTRY["reref"].make_params({})),
            ("epoching", STEP_REGISTRY["epoching"].make_params({"tmin": -0.5, "tmax": 1.0})),
        ]
        apply_pipeline(ctx, spec)
        assert ctx.stage == "epochs" and len(ctx.history) == 4
        # 分段后不允许再陷波（raw 阶段步骤）——中文阶段错误
        with pytest.raises(StepError) as ei:
            apply_pipeline(ctx, [("notch", STEP_REGISTRY["notch"].make_params({"freqs": [50.0]}))])
        assert "连续数据" in str(ei.value)

    def test_serialization_roundtrip(self, synthetic_raw):
        ctx = make_ctx(synthetic_raw)
        spec = [
            ("bandpass", STEP_REGISTRY["bandpass"].make_params({"l_freq": 1.0, "h_freq": 40.0})),
            ("epoching", STEP_REGISTRY["epoching"].make_params({"tmin": 0.0, "tmax": 1.0})),
        ]
        apply_pipeline(ctx, spec)
        dumped = [step_to_dict(s, p) for s, p in spec]
        loaded = [step_from_dict(d) for d in dumped]
        assert [(s, p.model_dump()) for s, p in loaded] == [(s, p.model_dump()) for s, p in spec]
        assert all(isinstance(d["params"], dict) for d in dumped)  # JSON 可序列化

    def test_unknown_step_refused(self):
        with pytest.raises(StepError) as ei:
            step_from_dict({"step": "nonexistent", "params": {}})
        assert "未知处理步骤" in str(ei.value)

    def test_from_recording_makes_copy(self, tmp_path, synthetic_raw):
        """from_recording 在副本上处理：原始 raw 数据不被改动."""
        p = tmp_path / "m3.fif"
        synthetic_raw.save(p, overwrite=True)
        rec = open_file(p)
        ctx = ProcessingContext.from_recording(rec)
        before = rec.raw.get_data(picks=[1])[0].copy()
        apply_pipeline(ctx, [("notch", STEP_REGISTRY["notch"].make_params({"freqs": [50.0]}))])
        after = rec.raw.get_data(picks=[1])[0]
        assert np.array_equal(before, after)  # 原始不动


# ------------------------------------------------------------------ 真实数据
class TestReal2a:
    @pytest.mark.real
    @pytest.mark.skipif(not GDF_2A.exists(), reason="无 2a GDF 数据")
    def test_a01t_epoch_count_288(self):
        """M3 验收口径：A01T 的 4 类提示事件（769-772）各 72 次 → 分段 288."""
        rec = open_file(GDF_2A)
        ctx = ProcessingContext.from_recording(rec)
        apply_pipeline(ctx, [
            ("bandpass", STEP_REGISTRY["bandpass"].make_params({"l_freq": 1.0, "h_freq": 40.0})),
            ("epoching", STEP_REGISTRY["epoching"].make_params(
                {"event_codes": ["769", "770", "771", "772"],
                 "tmin": -1.0, "tmax": 4.0, "baseline": (None, 0.0)})),
        ])
        assert ctx.stage == "epochs"
        assert len(ctx.epochs) == 288, f"分段数 {len(ctx.epochs)} ≠ 288"
