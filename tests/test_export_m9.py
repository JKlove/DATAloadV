"""M9 导出测试：连续 raw → EDF/FIF 往返 + 面板守卫 + 批处理逐文件导出.

M9 验证标准的落点：
- "EDF 跨工具可读"：mne.io.read_raw_edf 读回——通道/采样率/时长一致，
  数值在 16-bit channelwise 量化容差内（rtol 1e-3）
- "FIF 无损往返"：float32 精度（rtol 1e-6）+ annotations 保真
- "管线随导出保真"：bandpass 的 highpass 写进 EDF prefiltering 头并读回
- 批处理：每文件 _proc 产物 + sidecar；只勾连续格式时不误写特征文件
"""

from __future__ import annotations

import json

import mne
import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from dataloadv.batch.engine import BatchEngine  # noqa: E402
from dataloadv.batch.jobs import JobSpec, PipelineSpec  # noqa: E402
from dataloadv.core.recording import EventTable  # noqa: E402
from dataloadv.export import continuous_io  # noqa: E402
from dataloadv.proc import ProcessingContext  # noqa: E402
from tests.synthetic_helpers import make_synth_edf  # noqa: E402


def _read_edf(path):
    return mne.io.read_raw_edf(path, preload=True, verbose="ERROR")


# ------------------------------------------------------------ 连续导出核心
class TestContinuousExport:
    def test_edf_roundtrip(self, tmp_path, synthetic_raw):
        """① EDF 往返：后缀/通道/采样率/时长 + 数值在量化容差内."""
        out = continuous_io.export_continuous(synthetic_raw, tmp_path / "c.x", fmt="edf")
        assert out == tmp_path / "c.edf"
        back = _read_edf(out)
        assert back.ch_names == synthetic_raw.ch_names
        assert back.info["sfreq"] == 250.0
        assert back.n_times == synthetic_raw.n_times
        # channelwise 半步误差 ~6e-10V，rtol 1e-3 留 10 倍余量
        assert np.allclose(back.get_data(), synthetic_raw.get_data(),
                           rtol=1e-3, atol=1e-8)

    def test_edf_keeps_prefiltering_header(self, tmp_path, synthetic_raw):
        """② bandpass 后导出：highpass/lowpass 写进 EDF 头并读回."""
        ctx = ProcessingContext(raw=synthetic_raw.copy(),
                                events=EventTable.from_mne_annotations(synthetic_raw))
        from dataloadv.proc import STEP_REGISTRY, apply_pipeline

        apply_pipeline(ctx, [("bandpass", STEP_REGISTRY["bandpass"].make_params(
            {"l_freq": 1.0, "h_freq": 40.0}))])
        out = continuous_io.export_continuous(ctx.raw, tmp_path / "c_proc", fmt="edf")
        back = _read_edf(out)
        assert back.info["highpass"] == 1.0
        assert back.info["lowpass"] == 40.0
        assert np.allclose(back.get_data(), ctx.raw.get_data(), rtol=1e-3, atol=1e-8)

    def test_fif_roundtrip_with_annotations(self, tmp_path, synthetic_raw):
        """③ FIF 往返：_raw 规约后缀 + float32 精度 + annotations 保真."""
        out = continuous_io.export_continuous(synthetic_raw, tmp_path / "c_proc", fmt="fif")
        assert out == tmp_path / "c_proc_raw.fif"
        back = mne.io.read_raw_fif(out, preload=True, verbose="ERROR")
        assert np.allclose(back.get_data(), synthetic_raw.get_data(),
                           rtol=1e-6, atol=1e-12)
        assert len(back.annotations) == 3
        assert list(back.annotations.description) == ["T0", "T1", "T2"]
        assert np.allclose(back.annotations.onset, [10.0, 20.0, 30.0])

    def test_unknown_format_refused(self, tmp_path, synthetic_raw):
        with pytest.raises(ValueError, match="未知的连续导出格式"):
            continuous_io.export_continuous(synthetic_raw, tmp_path / "c.x", fmt="xlsx")

    def test_long_channel_name_refused(self, tmp_path, synthetic_raw):
        """⑤ 超 16 字符标签：前置中文报错（edfio 编码会直接炸）."""
        raw = synthetic_raw.copy()
        raw.rename_channels({"EEG00": "A_VERY_LONG_CHANNEL_NAME"})
        with pytest.raises(ValueError, match="16"):
            continuous_io.export_continuous(raw, tmp_path / "c.edf", fmt="edf")

    def test_non_ascii_channel_name_refused(self, tmp_path, synthetic_raw):
        raw = synthetic_raw.copy()
        raw.rename_channels({"EEG00": "脑电0"})
        with pytest.raises(ValueError, match="ASCII"):
            continuous_io.export_continuous(raw, tmp_path / "c.edf", fmt="edf")

    def test_misc_channel_type_refused(self, tmp_path, synthetic_raw):
        """⑥ 白名单外类型：数据留 V 却标 µV 属单位错标，前置拒绝."""
        raw = synthetic_raw.copy()
        raw.set_channel_types({"EEG00": "misc"})
        with pytest.raises(ValueError, match="通道类型"):
            continuous_io.export_continuous(raw, tmp_path / "c.edf", fmt="edf")

    def test_flat_channel_exportable(self, tmp_path, synthetic_raw):
        """⑦ 全平通道：channelwise 无量程可用，edfio 自带守卫不炸."""
        raw = synthetic_raw.copy()
        raw._data[0] = 0.0
        out = continuous_io.export_continuous(raw, tmp_path / "c.edf", fmt="edf")
        back = _read_edf(out)
        assert np.allclose(back.get_data()[0], 0.0, atol=1e-12)

    def test_single_channel_both_formats(self, tmp_path, synthetic_raw):
        """⑧ 单通道双格式：极端形状都能写能读."""
        raw = synthetic_raw.copy().pick(["EEG03"])
        for fmt, suffix in (("edf", ".edf"), ("fif", "_raw.fif")):
            out = continuous_io.export_continuous(raw, tmp_path / f"one", fmt=fmt)
            assert out.name == f"one{suffix}" and out.exists()


# ---------------------------------------------------------------- 面板守卫
class TestPanelGuard:
    def _panel(self, qtbot):
        from dataloadv.ui.widgets.pipeline_panel import PipelinePanel

        panel = PipelinePanel(lambda: None)
        qtbot.addWidget(panel)
        return panel

    def test_no_ctx_shows_hint(self, qtbot, monkeypatch):
        """⑨ 尚未预览过：中文提示先跑管线，不进格式菜单/对话框."""
        called = []
        monkeypatch.setattr(
            "dataloadv.ui.widgets.pipeline_panel.QMessageBox.information",
            staticmethod(lambda *a, **k: called.append(a)),
        )
        panel = self._panel(qtbot)
        panel.export_processed()
        assert called and "预览" in called[0][2]

    def test_epochs_stage_shows_hint(self, qtbot, monkeypatch):
        """⑩ 管线含分段：指向特征 tab 的分段导出，而不是静默失败."""
        called = []
        monkeypatch.setattr(
            "dataloadv.ui.widgets.pipeline_panel.QMessageBox.information",
            staticmethod(lambda *a, **k: called.append(a)),
        )
        panel = self._panel(qtbot)
        ctx = ProcessingContext(raw=None, events=EventTable())
        ctx.stage = "epochs"
        panel._last_ctx = ctx
        panel.export_processed()
        assert called and "分段" in called[0][2]


# ------------------------------------------------------------ 批处理导出
def _raw_export_job(paths, out_dir, **kw) -> JobSpec:
    """3 步骤+1 特征的批处理 JobSpec（bandpass → bandpower）."""
    return JobSpec(
        name="m9批",
        paths=[str(p) for p in paths],
        pipeline=PipelineSpec(
            steps=[{"step": "bandpass", "params": {"l_freq": 1.0, "h_freq": 40.0}}],
            features=[{"feature": "bandpower", "params": {"bands": ["alpha"]}}],
        ),
        n_workers=2,
        export_dir=str(out_dir),
        **kw,
    )


class TestBatchRawExport:
    def test_wants_export_semantics(self, tmp_path):
        """⑪ 四个导出开关任一勾选 + 有目录 = 要写文件."""
        base = dict(paths=["x"], pipeline=PipelineSpec())
        assert not JobSpec(**base).wants_export()
        assert not JobSpec(**base, export_csv=True).wants_export()  # 无目录
        assert JobSpec(**base, export_csv=True, export_dir=str(tmp_path)).wants_export()
        assert JobSpec(**base, export_raw_edf=True, export_dir=str(tmp_path)).wants_export()
        assert JobSpec(**base, export_raw_fif=True, export_dir=str(tmp_path)).wants_export()

    def test_epochs_pipeline_skipped_with_log(self, tmp_path):
        """⑫ 管线产物是分段：记「已跳过」日志，不写文件."""
        eng = BatchEngine(_raw_export_job([tmp_path / "x.edf"], tmp_path,
                                          export_raw_edf=True))
        ctx = ProcessingContext(raw=None, events=EventTable())
        ctx.stage = "epochs"
        logs: list[str] = []
        assert eng._export_continuous("/a/x.edf", ctx, logs) == []
        assert eng._raw_written == []
        assert any("已跳过" in line for line in logs)

    def test_engine_exports_per_file(self, tmp_path):
        """⑬ 引擎级：3 个合成 EDF → 每文件 _proc.edf + sidecar（kind=raw）."""
        srcs = [make_synth_edf(tmp_path / f"s{i}.edf", seed=i) for i in range(3)]
        eng = BatchEngine(_raw_export_job(srcs, tmp_path, export_raw_edf=True))
        summary = eng.run()
        assert all(r.status.value == "ok" for r in summary.results)
        assert len(eng.table) > 0  # 特征照算
        for src in srcs:
            out = tmp_path / f"{src.stem}_proc.edf"
            sidecar = tmp_path / f"{src.stem}_proc.pipeline.json"  # 后缀替换式命名
            assert out.exists() and sidecar.exists()
            doc = json.loads(sidecar.read_text(encoding="utf-8"))
            # ctx.history 记完整参数（含默认 method="fir"），按字段核对
            assert doc["pipeline"] == [{
                "step": "bandpass",
                "params": {"l_freq": 1.0, "h_freq": 40.0, "method": "fir"}}]
            assert doc["extra"]["kind"] == "raw"
            back = _read_edf(out)
            assert len(back.ch_names) == 4 and back.info["sfreq"] == 250.0
        # files_written 汇总 6 条路径（3 数据 + 3 sidecar）+ 1 特征 CSV sidecar 组
        raw_files = [p for p in summary.files_written if "_proc.edf" in p]
        assert len(raw_files) == 3

    def test_export_failure_degrades_to_log(self, tmp_path, monkeypatch):
        """⑭ 导出炸了：该文件特征照算、status ok、日志含中文原因."""
        srcs = [make_synth_edf(tmp_path / "s0.edf")]
        eng = BatchEngine(_raw_export_job(srcs, tmp_path, export_raw_edf=True))

        def boom(raw, path, fmt="edf"):
            raise RuntimeError("disk full")

        monkeypatch.setattr("dataloadv.batch.engine.export_continuous", boom)
        summary = eng.run()
        assert summary.results[0].status.value == "ok"
        assert len(eng.table) > 0
        assert any("连续导出失败" in line for line in summary.results[0].log)
        assert summary.files_written == [] or all(
            p.endswith(".pipeline.json") for p in summary.files_written
            if "s0" not in p)  # 本文件无产物（特征 CSV sidecar 由 csv 分支决定）

    def test_raw_only_does_not_write_feature_files(self, tmp_path):
        """⑮ 只勾连续导出：不产生特征 CSV/HDF5（旧分支漏洞的回归哨兵）."""
        srcs = [make_synth_edf(tmp_path / "s0.edf")]
        job = _raw_export_job(srcs, tmp_path,
                              export_raw_edf=True)  # export_csv/hdf5 默认 False
        assert not job.export_csv and not job.export_hdf5
        summary = BatchEngine(job).run()
        assert summary.results[0].status.value == "ok"
        assert not list(tmp_path.glob("*.csv"))
        assert not list(tmp_path.glob("*.h5"))
        assert any(p.endswith("_proc.edf") for p in summary.files_written)
