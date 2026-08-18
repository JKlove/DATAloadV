"""EDF 读取器测试：合成 EDF 全流程 + 真实羊数据 latin1 冒烟."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dataloadv.core.recording import EventTable, LoadPolicy, LoadedRawCache
from dataloadv.io.registry import READER_REGISTRY, open_file, scan_folder

SHEEP = Path(__file__).resolve().parent.parent / "data" / "sheep"


def _write_synth_edf(tmp_path: Path) -> Path:
    """用 mne 导出一个含注释的合成 EDF（读取器测试的标准夹具）."""
    import mne

    rng = np.random.default_rng(7)
    sfreq = 200.0
    info = mne.create_info(["Fp1", "Fp2", "C3"], sfreq, "eeg")
    data = rng.normal(0, 30e-6, (3, int(sfreq * 20)))
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    raw.set_annotations(
        mne.Annotations(onset=[2.0, 8.0], duration=[0.0, 1.0], description=["T0", "T1"])
    )
    out = tmp_path / "synth.edf"
    raw.export(out, fmt="edf", overwrite=True)
    return out


def test_edf_reader_registered():
    assert "edf" in READER_REGISTRY


def test_read_meta_and_open_roundtrip(tmp_path):
    """头读取 → open → 事件/通道/时长一致；LAZY 与 PRELOAD 行为正确."""
    path = _write_synth_edf(tmp_path)
    meta = READER_REGISTRY["edf"].read_meta(path)
    assert meta.format == "EDF"
    assert meta.n_channels == 3
    assert meta.sfreq == pytest.approx(200.0, rel=0.01)
    assert meta.duration_s == pytest.approx(20.0, abs=0.2)
    assert meta.n_events == 2
    assert meta.event_summary == {"T0": 1, "T1": 1}

    LoadedRawCache.reset(byte_budget=10**9)
    rec = open_file(path)
    assert rec.meta.path == str(path)
    # HEADER_ONLY 打开：事件已在头里解析好
    assert len(rec.events) == 2
    assert rec.events.code == ["T0", "T1"]
    assert not rec.is_loaded()

    # get_window 自动加载并按窗口取数
    data, times = rec.get_window(0.0, 1.0)
    assert data.shape[0] == 3
    assert 190 <= data.shape[1] <= 210
    assert times[0] == pytest.approx(0.0)
    rec.unload()


@pytest.mark.real
@pytest.mark.parametrize(
    "edf_name",
    ["data(DGDJ-卧-接地-2)-HKY.edf", "data(DGDJ-站-接地-4)-HKY.edf", "data(DGDJ-走动-接地-3)-HKY.edf"],
)
def test_sheep_edf_latin1(edf_name: str):
    """真实羊 EDF：默认编码必炸的文件能靠 latin1 回退打开（HANDOFF 坑 #1）."""
    path = SHEEP / edf_name
    rec = open_file(path)
    assert rec.meta.n_channels == 8
    assert rec.meta.sfreq == pytest.approx(250.0)
    assert rec.meta.duration_s > 60
    data, times = rec.get_window(10.0, 11.0)
    assert data.shape == (8, 250)
    assert np.isfinite(data).all()
    rec.unload()


@pytest.mark.real
def test_scan_sheep_folder():
    """目录扫描：3 个羊 EDF 全识别、零错误（.DS_Store 若存在则计入 skipped）."""
    report = scan_folder(SHEEP)
    assert len(report.items) == 3
    assert report.errors == []
    metas = {i.meta.filename for i in report.items}
    assert any("卧" in m for m in metas)


def test_scan_folder_unknown_extensions_ignored(tmp_path):
    """未知扩展名静默跳过（不产生错误行）——RECORDS/图片等配套文件场景."""
    (tmp_path / "RECORDS").write_text("x")
    (tmp_path / "note.txt").write_text("x")
    (tmp_path / "img.png").write_bytes(b"\x89PNG")
    report = scan_folder(tmp_path)
    assert report.items == []
    assert report.errors == []
    assert report.skipped == 3


def test_open_file_unsupported(tmp_path):
    """无读取器接管的扩展名 → 中文 ScanError."""
    bad = tmp_path / "x.xyz"
    bad.write_bytes(b"\x00\x01")
    from dataloadv.io.base import ScanError

    with pytest.raises(ScanError) as ei:
        open_file(bad)
    assert "不支持的格式" in ei.value.message


def test_event_table_window_filter():
    """in_window 边界：左闭右开."""
    ev = EventTable(
        onset=np.array([1.0, 2.0, 3.0]),
        duration=np.zeros(3),
        code=["A", "B", "A"],
        label=["A", "B", "A"],
    )
    assert ev.in_window(1.0, 2.0) == [0]
    assert ev.in_window(0.5, 3.5) == [0, 1, 2]
    assert ev.in_window(3.1, 5.0) == []
    assert ev.codes_summary() == {"A": 2, "B": 1}
