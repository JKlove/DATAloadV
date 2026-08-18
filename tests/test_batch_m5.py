"""M5 批处理引擎测试：任务模型往返 / 损坏文件容错 / 取消 / 导出 / 设置.

覆盖口径（plan.md §6 单测要求"3 文件含 1 损坏 → 2 成功 1 报错 + 中途取消"）：
- 3 合成 EDF + 1 损坏文件 → 3 ok + 1 failed（中文原因、日志齐、长表只含成功文件）
- 首个文件完成即取消 → 整批 cancelled、未开始的文件全部 cancelled
- 导出：CSV（BOM + 中文表头）+ HDF5 + sidecar（含完整管线与文件清单）
- 采样率未设定的表格文件进批处理 → 明确失败（提示先在浏览 tab 设定）
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

mne = pytest.importorskip("mne")
mne.set_log_level("ERROR")

from dataloadv.batch.engine import BatchEngine  # noqa: E402
from dataloadv.batch.jobs import (  # noqa: E402
    BatchSummary,
    FileStatus,
    JobSpec,
    PipelineSpec,
)
from dataloadv.core.app_settings import AppSettings  # noqa: E402
from dataloadv.proc.base import (  # noqa: E402
    PipelineCancelled,
    apply_pipeline,
)
from dataloadv.features.base import apply_features  # noqa: E402
from dataloadv.proc.context import ProcessingContext  # noqa: E402


# ---------------------------------------------------------------- 夹具

def _write_synth_edf(path: Path, seed: int = 0, n_seconds: float = 20.0) -> Path:
    """确定性合成 EDF（4 导 / 250Hz / 10Hz α 正弦 + 噪声）——批处理的标准口粮."""
    sf = 250.0
    t = np.arange(int(sf * n_seconds)) / sf
    rng = np.random.default_rng(seed)
    data = 20e-6 * np.sin(2 * np.pi * 10.0 * t) + rng.normal(0, 5e-6, (4, len(t)))
    raw = mne.io.RawArray(
        data, mne.create_info(4, sf, "eeg"), verbose="ERROR")
    raw.export(path, fmt="edf", overwrite=True, verbose="ERROR")
    return path


@pytest.fixture
def three_edf_plus_broken(tmp_path: Path) -> list[str]:
    """3 个可读 EDF + 1 个损坏 EDF（内容全零——魔数都过不了）."""
    paths = [str(_write_synth_edf(tmp_path / f"synth{i}.edf", seed=i)) for i in range(3)]
    broken = tmp_path / "broken.edf"
    broken.write_bytes(b"\x00" * 512)
    return paths + [str(broken)]


def _job(paths: list[str], **kw) -> JobSpec:
    """标准测试作业：无步骤 + 频带功率(α) + 时域统计（4 导 × 9 值/文件）."""
    return JobSpec(
        name="测试批",
        paths=paths,
        pipeline=PipelineSpec(
            steps=[],
            features=[
                {"feature": "bandpower", "params": {"bands": ["alpha"]}},
                {"feature": "timedomain", "params": {}},
            ],
        ),
        n_workers=2,
        **kw,
    )


# ---------------------------------------------------------------- 任务模型

def test_job_spec_json_roundtrip(three_edf_plus_broken):
    """JobSpec 整体可 JSON 往返（复现一次批处理只需要这份描述）."""
    job = _job(three_edf_plus_broken)
    restored = JobSpec(**json.loads(job.model_dump_json()))
    assert restored.paths == job.paths
    assert restored.pipeline.steps == job.pipeline.steps
    assert restored.pipeline.resolved_features()[0][0] == "bandpower"


def test_pipeline_spec_rejects_unknown_step():
    """未知步骤在启动前（resolved_steps）就报中文错误，而不是逐文件失败."""
    spec = PipelineSpec(steps=[{"step": "不存在的步骤", "params": {}}], features=[])
    from dataloadv.proc.base import StepError

    with pytest.raises(StepError, match="未知处理步骤"):
        spec.resolved_steps()


def test_file_result_summary_zh():
    """BatchSummary 中文摘要的分段拼接（含取消段）."""
    from dataloadv.batch.jobs import result_for

    job = _job(["/x/a.edf"])
    s = BatchSummary(
        job=job,
        results=[result_for("/x/a.edf", FileStatus.OK, n_values=36)],
        elapsed_s=1.234,
    )
    assert "成功 1" in s.summary_zh() and "36 行特征" in s.summary_zh()
    assert "取消" not in s.summary_zh()  # 无取消段时不出现


# ---------------------------------------------------------------- 引擎

def test_engine_tolerates_broken_file(three_edf_plus_broken):
    """3 成功 + 1 失败：坏文件不杀整批，失败行带中文原因与日志."""
    events: list = []
    eng = BatchEngine(_job(three_edf_plus_broken), on_file_done=events.append)
    summary = eng.run()

    assert summary.n_ok == 3 and summary.n_failed == 1
    assert summary.n_total == 4 and not summary.cancelled
    assert len(events) == 4  # 每个文件恰好一次回调
    failed = next(r for r in summary.results if r.status is FileStatus.FAILED)
    assert failed.recording == "broken.edf"
    assert failed.error  # 中文错误非空
    assert failed.n_values == 0
    # 长表只含成功文件：3 文件 × 4 导 × (1 频段 + 8 统计量) = 108
    assert len(eng.table) == 108
    assert eng.table.n_recordings == 3
    # 成功文件日志含起止行
    ok = next(r for r in summary.results if r.ok)
    assert ok.log[0].startswith("—— 开始处理")
    assert any("—— 完成" in line for line in ok.log)
    # 结果顺序与 JobSpec.paths 一致（表格按行号对齐的前提）
    assert [r.path for r in summary.results] == three_edf_plus_broken


def test_engine_cancel_after_first_file(three_edf_plus_broken):
    """首个文件完成即取消：整批标记取消，未开始的文件全为 cancelled."""
    eng: BatchEngine | None = None

    def _cancel_after_first(_result):
        # on_file_done 在 worker 线程执行——只调线程安全的 cancel()
        assert eng is not None
        eng.cancel()

    eng = BatchEngine(_job(three_edf_plus_broken), on_file_done=_cancel_after_first)
    summary = eng.run()

    assert summary.cancelled
    assert summary.n_cancelled >= 1  # 至少有文件没跑
    assert summary.n_ok + summary.n_failed + summary.n_cancelled == 4
    # 已取消文件绝不应贡献特征行
    n_from_ok = sum(r.n_values for r in summary.results if r.ok)
    assert len(eng.table) == n_from_ok


def test_apply_pipeline_cancel_check(synthetic_raw):
    """cancel_check 逐步骤生效：探针为真抛 PipelineCancelled（StepError 子类）."""
    from dataloadv.features.base import FEATURE_REGISTRY
    from dataloadv.proc.base import STEP_REGISTRY

    ctx = ProcessingContext(raw=synthetic_raw.copy(), stage="raw")
    steps = [("notch", STEP_REGISTRY["notch"].make_params({"freqs": [50.0]}))]
    with pytest.raises(PipelineCancelled):
        apply_pipeline(ctx, steps, cancel_check=lambda: True)
    # features 侧同一约定（取消先于提取，参数不会被触碰）
    feats = [("bandpower", FEATURE_REGISTRY["bandpower"].default_params())]
    with pytest.raises(PipelineCancelled):
        apply_features(ctx, feats, cancel_check=lambda: True)


def test_engine_exports_csv_hdf5_sidecar(three_edf_plus_broken, tmp_path):
    """末尾导出：CSV BOM+中文表头、HDF5、sidecar 含管线与文件清单."""
    out = tmp_path / "exports"
    job = _job(
        [p for p in three_edf_plus_broken if "broken" not in p],
        export_csv=True, export_hdf5=True, export_dir=str(out),
    )
    eng = BatchEngine(job)
    summary = eng.run()

    csv_path = out / "测试批.csv"
    assert csv_path.exists()
    raw_bytes = csv_path.read_bytes()
    assert raw_bytes[:3] == b"\xef\xbb\xbf"  # BOM
    header = raw_bytes[3:].decode("utf-8").splitlines()[0]
    assert header == "录制,被试,段序号,事件码,通道,特征,数值"
    assert (out / "测试批.h5").exists()
    sidecar = out / "测试批.pipeline.json"
    assert sidecar.exists()
    doc = json.loads(sidecar.read_text(encoding="utf-8"))
    assert [f["feature"] for f in doc["features"]] == ["bandpower", "timedomain"]
    assert len(doc["recordings"]) == 3
    assert str(csv_path) in summary.files_written
    assert any(p.endswith(".h5") for p in summary.files_written)


def test_engine_fails_chinese_on_unset_fs(tmp_path):
    """采样率未设定的表格文件：以错误采样率跑管线是坏数据——中文失败提示."""
    csv_path = tmp_path / "table.csv"
    csv_path.write_text("a,b,c\n1,2,3\n4,5,6\n", encoding="utf-8")
    eng = BatchEngine(_job([str(csv_path)]))
    summary = eng.run()

    assert summary.n_failed == 1
    r = summary.results[0]
    assert "采样率未设定" in r.error
    assert "浏览 tab" in r.error  # 告诉用户怎么修


# ---------------------------------------------------------------- 设置

def test_app_settings_roundtrip_and_apply(tmp_path, monkeypatch):
    """设置 JSON 往返 + apply() 热生效（cache 预算写进单例）."""
    from dataloadv.core import app_settings as mod
    from dataloadv.core.recording import LoadedRawCache

    fake = tmp_path / "settings.json"
    monkeypatch.setattr(mod, "SETTINGS_PATH", fake)
    LoadedRawCache.reset()  # 隔离单例

    s = AppSettings.load()  # 无文件 → 默认
    assert s.n_workers == 2 and s.cache_gb == 1.5
    s.n_workers, s.cache_gb, s.export_dir = 3, 2.0, str(tmp_path)
    s.save()
    s2 = AppSettings.load()
    assert (s2.n_workers, s2.cache_gb, s2.export_dir) == (3, 2.0, str(tmp_path))

    s2.apply()
    assert LoadedRawCache.instance().byte_budget == int(2.0 * 1024**3)


def test_app_settings_tolerates_corrupt_file(tmp_path, monkeypatch):
    """损坏的设置文件按无文件处理（默认值启动，不抛异常）."""
    from dataloadv.core import app_settings as mod

    fake = tmp_path / "settings.json"
    fake.write_text("{不是合法 JSON", encoding="utf-8")
    monkeypatch.setattr(mod, "SETTINGS_PATH", fake)
    assert AppSettings.load().n_workers == 2
