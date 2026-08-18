"""M4 导出测试：CSV（中文表头 + BOM）/ HDF5 / FIF 往返 + sidecar 合法性.

M4 验证标准的落点：
- "CSV Excel 可开中文表头"：BOM 存在 + 表头是 COLUMNS_ZH 的中文
- "HDF5 回读形状一致"：value 数组逐位、epochs data 形状 + allclose
"""

from __future__ import annotations

import json

import mne
import numpy as np
import pandas as pd
import pytest

from dataloadv.batch import COLUMNS, COLUMNS_ZH, FeatureTable
from dataloadv.export import epochs_io, features_io, provenance
from dataloadv.features import FEATURE_REGISTRY, apply_features, feature_to_dict
from dataloadv.proc import STEP_REGISTRY, ProcessingContext, apply_pipeline
from dataloadv.core.recording import EventTable


@pytest.fixture
def raw_table(synthetic_raw) -> FeatureTable:
    """raw 全量特征表（含一条通道平均曲线）."""
    ctx = ProcessingContext(
        raw=synthetic_raw.copy(), events=EventTable.from_mne_annotations(synthetic_raw)
    )
    res = apply_features(ctx, [
        ("bandpower", FEATURE_REGISTRY["bandpower"].make_params({"bands": ["alpha", "beta"]})),
        ("welch_psd", FEATURE_REGISTRY["welch_psd"].default_params()),
    ])
    t = FeatureTable()
    t.add_result(res, "test.gdf", "S01")
    return t


@pytest.fixture
def epochs_ctx(synthetic_raw) -> ProcessingContext:
    ctx = ProcessingContext(
        raw=synthetic_raw.copy(), events=EventTable.from_mne_annotations(synthetic_raw)
    )
    apply_pipeline(ctx, [("epoching", STEP_REGISTRY["epoching"].make_params(
        {"tmin": -0.5, "tmax": 1.5}))])
    return ctx


# ------------------------------------------------------------------ 特征 CSV
class TestFeaturesCsv:
    def test_bom_and_chinese_header(self, tmp_path, raw_table):
        """M4 验收：BOM 存在、表头中文（Excel 双击即正确显示）."""
        (features_io.export_features_csv(raw_table, tmp_path / "f.csv"))
        raw_bytes = (tmp_path / "f.csv").read_bytes()
        assert raw_bytes[:3] == b"\xef\xbb\xbf"
        header = raw_bytes[3:].decode("utf-8").splitlines()[0]
        assert header == ",".join(COLUMNS_ZH[c] for c in COLUMNS)

    def test_roundtrip_values(self, tmp_path, raw_table):
        features_io.export_features_csv(raw_table, tmp_path / "f.csv")
        back = pd.read_csv(tmp_path / "f.csv", encoding="utf-8-sig")
        assert len(back) == len(raw_table.df)
        assert back[COLUMNS_ZH["value"]].to_numpy() == pytest.approx(
            raw_table.df["value"].to_numpy(), rel=1e-9)

    def test_epoch_none_becomes_empty_cell(self, tmp_path, synthetic_raw):
        """文件级行（epoch_index/event_code=None）在 CSV 中是空单元格."""
        ctx = ProcessingContext(raw=synthetic_raw.copy(), events=EventTable())
        res = apply_features(ctx, [("bandpower", FEATURE_REGISTRY["bandpower"].make_params({"bands": ["alpha"]}))])
        t = FeatureTable()
        t.add_result(res, "x.gdf")
        features_io.export_features_csv(t, tmp_path / "f.csv")
        back = pd.read_csv(tmp_path / "f.csv", encoding="utf-8-sig")
        assert back[COLUMNS_ZH["epoch_index"]].isna().all()
        assert back[COLUMNS_ZH["subject"]].isna().all() or (back[COLUMNS_ZH["subject"]] == "").all()

    def test_curve_wide_csv(self, tmp_path, raw_table):
        """曲线 → 独立宽表 <名>_psd.csv：freq 列 + 每曲线一列."""
        files = features_io.export_features_csv(raw_table, tmp_path / "f.csv")
        psd_csv = [p for p in files if "_psd" in p.name]
        assert len(psd_csv) == 1
        back = pd.read_csv(psd_csv[0], encoding="utf-8-sig")
        assert back.shape == (raw_table.curves[0]["freqs"].size, 2)  # freq 列 + 1 曲线列
        assert "µV²/Hz" in back.columns[1]

    def test_curves_grouped_by_freq_axis(self, tmp_path, raw_table):
        """两条频率轴不同的曲线 → 各写一个文件（不能混一张表）."""
        raw_table.curves.append({
            "recording": "other.gdf", "channel": "(通道平均)",
            "freqs": np.linspace(0.5, 40, 77), "psd": np.linspace(1, 2, 77),
        })
        files = features_io.export_features_csv(raw_table, tmp_path / "f.csv")
        assert len([p for p in files if "_psd" in p.name]) == 2


# ------------------------------------------------------------------ 特征 HDF5
class TestFeaturesHdf5:
    def test_roundtrip_values_and_strings(self, tmp_path, raw_table):
        h5 = features_io.export_features_hdf5(raw_table, tmp_path / "f.h5")
        df, curves = features_io.read_features_hdf5(h5)
        assert list(df.columns) == list(COLUMNS)
        assert df["value"].to_numpy() == pytest.approx(raw_table.df["value"].to_numpy(), rel=1e-12)
        assert list(df["recording"]) == list(raw_table.df["recording"])
        assert list(df["feature"]) == list(raw_table.df["feature"])
        assert list(df["channel"]) == list(raw_table.df["channel"])
        assert len(curves) == 1
        assert np.allclose(curves[0]["psd"], raw_table.curves[0]["psd"])
        assert np.allclose(curves[0]["freqs"], raw_table.curves[0]["freqs"])
        assert curves[0]["channel"] == "(通道平均)"

    def test_epoch_roundtrip_none_preserved(self, tmp_path, synthetic_raw):
        """段序号 None（文件级）经 -1 编码往返仍为 <NA>."""
        ctx = ProcessingContext(raw=synthetic_raw.copy(), events=EventTable())
        res = apply_features(ctx, [("bandpower", FEATURE_REGISTRY["bandpower"].make_params({"bands": ["alpha"]}))])
        t = FeatureTable()
        t.add_result(res, "x.gdf")
        h5 = features_io.export_features_hdf5(t, tmp_path / "f.h5")
        df, _ = features_io.read_features_hdf5(h5)
        assert df["epoch_index"].isna().all()


# ------------------------------------------------------------------ 分段导出
class TestEpochsExport:
    def test_hdf5_roundtrip_shape_and_values(self, tmp_path, epochs_ctx):
        out = epochs_io.export_epochs(epochs_ctx.epochs, tmp_path / "e.h5")
        assert out.suffix == ".h5"
        back = epochs_io.read_epochs_hdf5(out)
        src = epochs_ctx.epochs
        assert back["data"].shape == src.get_data().shape  # M4 验证标准：形状一致
        assert np.allclose(back["data"], src.get_data(), rtol=1e-5)  # f4 精度
        assert np.allclose(back["times"], src.times)
        assert back["ch_names"] == src.info["ch_names"]
        assert back["sfreq"] == src.info["sfreq"]
        assert list(back["event_codes"]) == list(src.events[:, -1])
        # 事件码映射：mne 整数码 → 原始字符串码
        id2code = {v: k for k, v in src.event_id.items()}
        assert back["event_id_map"] == {str(k): v for k, v in id2code.items()}

    def test_fif_roundtrip_with_mne(self, tmp_path, epochs_ctx):
        """FIF 导出 → mne.read_epochs 回读：段数/通道/事件全一致."""
        out = epochs_io.export_epochs(epochs_ctx.epochs, tmp_path / "e.h5", fmt="fif")
        assert out.suffix == ".fif"
        back = mne.read_epochs(out, verbose="ERROR")
        assert len(back) == len(epochs_ctx.epochs) == 3
        assert back.ch_names == epochs_ctx.epochs.info["ch_names"]
        assert np.allclose(back.get_data(), epochs_ctx.epochs.get_data(), atol=1e-18)

    def test_unknown_format_refused(self, tmp_path, epochs_ctx):
        with pytest.raises(ValueError, match="未知的分段导出格式"):
            epochs_io.export_epochs(epochs_ctx.epochs, tmp_path / "e.x", fmt="xlsx")


# ------------------------------------------------------------------ sidecar
class TestProvenance:
    def test_sidecar_json_valid_and_complete(self, tmp_path, raw_table, epochs_ctx):
        pipeline = epochs_ctx.history + [
            {"step": "crop", "params": {"tmin": 0.0, "tmax": 30.0}}
        ]
        feats = [feature_to_dict("bandpower", FEATURE_REGISTRY["bandpower"].default_params())]
        sc = provenance.write_provenance(
            tmp_path / "f.csv", pipeline=pipeline, features=feats,
            recordings=["A01T.gdf"], extra={"exported": "f.csv"},
        )
        assert sc.name == "f.pipeline.json"
        doc = json.loads(sc.read_text(encoding="utf-8"))
        assert doc["app"] == "DataloadV" and doc["app_version"]
        assert doc["pipeline"][0]["step"] in STEP_REGISTRY
        assert doc["features"][0]["feature"] == "bandpower"
        assert doc["recordings"] == ["A01T.gdf"]
        assert "mne" in doc["library_versions"]
        assert doc["extra"]["exported"] == "f.csv"

    def test_created_is_iso_utc(self, tmp_path):
        sc = provenance.write_provenance(tmp_path / "x.csv", pipeline=[])
        doc = json.loads(sc.read_text(encoding="utf-8"))
        assert doc["created"].endswith("+00:00") and "T" in doc["created"]
