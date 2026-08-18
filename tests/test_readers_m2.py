"""M2 读取器测试：BCI-IV mat（ds1/ds4/拒绝猜测）+ CSV/TXT + HDF5 + GDF 中文标签.

合成夹具见 synthetic_helpers.py（结构按 data/dataset 实物探测结果伪造）；
真实数据测试（GDF 2a/2b、完整数据集扫描）用 ``real`` 标记，数据缺失自动跳过。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from synthetic_helpers import (
    make_csv,
    make_ds1_mat,
    make_ds3_like_mat,
    make_ds4_mat,
    make_hdf5,
    make_unknown_mat,
)

from dataloadv.core.fs_store import FsStore
from dataloadv.core.recording import LoadPolicy
from dataloadv.io.base import ScanError
from dataloadv.io.event_maps import GDF_CODE_LABELS, gdf_label
from dataloadv.io.registry import open_file
from dataloadv.io.sniffing import sniff_format
from dataloadv.io.table import FS_UNSET_NOTE

DATA = Path(__file__).resolve().parent.parent / "data"
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"
GDF_2B = DATA / "dataset" / "BCICIV_2b_gdf" / "B0303T.gdf"


# --------------------------------------------------------------------- ds1
class TestDs1:
    def test_meta_and_events(self, tmp_path):
        p = make_ds1_mat(tmp_path / "BCICIV_calib_ds1x.mat")
        rec = open_file(p)
        assert rec.meta.reader_id == "bciciv_ds1"
        assert rec.meta.n_channels == 59
        assert rec.meta.sfreq == 100.0
        assert rec.meta.n_events == 8
        # code 是官方类名，label 是中文（+1→classes[0]=left）
        assert set(rec.events.code) <= {"left", "foot"}
        assert set(rec.events.label) <= {"左手", "脚"}
        assert rec.meta.subject == "ds1x" and rec.meta.task == "calib"

    def test_eval_without_mrk(self, tmp_path):
        p = make_ds1_mat(tmp_path / "BCICIV_eval_ds1x.mat", with_mrk=False)
        rec = open_file(p)
        assert rec.meta.n_events == 0
        assert "mrk" in rec.meta.notes  # 说明评估集无标注

    def test_uv_scale(self, tmp_path):
        """合成幅度 30µV 正弦 ±5µV 噪声 → 读出电压应落在合理 µV 量级."""
        p = make_ds1_mat(tmp_path / "BCICIV_calib_ds1y.mat")
        rec = open_file(p, LoadPolicy.PRELOAD)
        d, _ = rec.get_window(0, 2, [0])
        uv = np.abs(d[0]) * 1e6
        assert 5 < uv.max() < 500, f"µV 量级异常：max={uv.max():.1f}"


# --------------------------------------------------------------------- ds4
class TestDs4:
    def test_meta(self, tmp_path):
        p = make_ds4_mat(tmp_path / "sub9_comp.mat", n_times=3000, n_ch=8)
        rec = open_file(p)
        assert rec.meta.reader_id == "bciciv_ds4"
        assert rec.meta.n_channels == 8 + 5  # ECoG + 手套 5 指
        assert rec.meta.sfreq == 1000.0
        assert rec.meta.channel_names[-5:] == ["thumb", "index", "middle", "ring", "little"]
        assert rec.meta.channel_types[-5:] == ["misc"] * 5
        assert rec.meta.n_events == 0  # 连续回归：无离散事件
        assert rec.meta.subject == "sub9"

    def test_load_values_preserved(self, tmp_path):
        p = make_ds4_mat(tmp_path / "sub9_comp.mat", n_times=1000, n_ch=4)
        rec = open_file(p, LoadPolicy.PRELOAD)
        d, _ = rec.get_window(0, 1)  # 前 1000 样本 = 全部
        assert d.shape[0] == 9
        assert np.isfinite(d).all()
        # 手套通道（末 5 个）合成值 ~N(0.5, 0.5)：std 远小于 ECoG 的 ~500
        assert d[4:].std() < d[:4].std() / 10


# ----------------------------------------------------------------- 拒绝猜测
class TestRefusal:
    def test_ds3_recognized_and_refused(self, tmp_path):
        p = make_ds3_like_mat(tmp_path / "S9.mat")
        with pytest.raises(ScanError) as ei:
            open_file(p)
        assert "数据集 3" in str(ei.value) and "分段" in str(ei.value)

    def test_unknown_mat_refused(self, tmp_path):
        p = make_unknown_mat(tmp_path / "weird.mat")
        with pytest.raises(ScanError) as ei:
            open_file(p)
        assert "不猜测" in str(ei.value) or "无法识别" in str(ei.value)


# --------------------------------------------------------------------- CSV
class TestTable:
    @pytest.fixture(autouse=True)
    def _isolated_fs_store(self, tmp_path, monkeypatch):
        """隔离 FsStore：绝不动用户真实的 ~/.dataloadv/table_fs.json."""
        import dataloadv.core.fs_store as fs_mod

        monkeypatch.setattr(fs_mod, "_STORE_PATH", tmp_path / "fs.json")

    @pytest.mark.parametrize("delim", [",", ";", "\t"])
    def test_delimiters_and_header(self, tmp_path, delim):
        p = make_csv(tmp_path / f"t{delim.strip() or 'sp'}.csv", delim=delim)
        rec = open_file(p)
        assert rec.meta.n_channels == 4
        assert rec.meta.channel_names == ["ch1", "ch2", "ch3", "ch4"]
        assert FS_UNSET_NOTE in rec.meta.notes  # 采样率未知 → 标记询问

    def test_no_header(self, tmp_path):
        p = make_csv(tmp_path / "raw.csv", header=False)
        rec = open_file(p)
        assert rec.meta.n_channels == 4

    def test_fs_store_remembered(self, tmp_path):
        """FsStore 记住的采样率直接生效（不再标记未设定）."""
        p = make_csv(tmp_path / "known.csv", fs=500.0)
        FsStore().put(p, 500.0)
        rec = open_file(p)
        assert rec.meta.sfreq == 500.0
        assert FS_UNSET_NOTE not in rec.meta.notes
        assert abs(rec.meta.duration_s - 1.0) < 0.01  # 500 样本 / 500 Hz

    def test_load_data(self, tmp_path):
        p = make_csv(tmp_path / "data.csv", n_times=400, fs=250.0)
        FsStore().put(p, 250.0)
        rec = open_file(p, LoadPolicy.PRELOAD)
        d, t = rec.get_window(0, 1.0)
        assert d.shape == (4, 250)
        assert abs(t[-1] - 0.996) < 1e-6

    def test_prose_txt_refused(self, tmp_path):
        """说明/校验文件（非数值表格）明确报错而非误导入."""
        p = tmp_path / "SHA256SUMS.txt"
        p.write_text("abc123 S001/S001R01.edf.event\ndef456 S001/S001R02.edf.event\n")
        with pytest.raises(ScanError) as ei:
            open_file(p)
        assert "不是数值" in str(ei.value) or "数值表格" in str(ei.value)


# -------------------------------------------------------------------- HDF5
class TestHdf5:
    def test_time_major_with_attr(self, tmp_path):
        p = make_hdf5(tmp_path / "a.h5", shape=(2000, 3), time_axis=0, fs=250.0)
        rec = open_file(p)
        assert rec.meta.n_channels == 3
        assert rec.meta.sfreq == 250.0
        assert abs(rec.meta.duration_s - 8.0) < 0.01

    def test_channel_major(self, tmp_path):
        p = make_hdf5(tmp_path / "b.h5", shape=(3, 2000), time_axis=1, fs=None)
        rec = open_file(p)
        assert rec.meta.n_channels == 3
        assert FS_UNSET_NOTE in rec.meta.notes  # 无 fs 属性 → 询问

    def test_fs_attr_aliases(self, tmp_path):
        p = make_hdf5(tmp_path / "c.h5", shape=(100, 2), fs=100.0, fs_attr="sample_rate")
        assert open_file(p).meta.sfreq == 100.0

    def test_ambiguous_refused(self, tmp_path):
        import h5py

        p = tmp_path / "amb.h5"
        with h5py.File(str(p), "w") as f:
            f.create_dataset("a", data=np.zeros((100, 10)))
            f.create_dataset("b", data=np.zeros((100, 10)))
        with pytest.raises(ScanError) as ei:
            open_file(p)
        assert "不确定" in str(ei.value)

    def test_no_2d_refused(self, tmp_path):
        import h5py

        p = tmp_path / "vec.h5"
        with h5py.File(str(p), "w") as f:
            f.create_dataset("v", data=np.zeros(100))
        with pytest.raises(ScanError):
            open_file(p)

    def test_load_values(self, tmp_path):
        p = make_hdf5(tmp_path / "d.h5", shape=(500, 2), fs=250.0)
        rec = open_file(p, LoadPolicy.PRELOAD)
        d, _ = rec.get_window(0, 1.0)
        assert d.shape == (2, 250)


# ----------------------------------------------------------------- GDF 标签
class TestGdfLabels:
    def test_map_table(self):
        assert gdf_label("769") == "提示：左手（类1）"
        assert gdf_label("783") == "提示：未知（评估集）"
        assert gdf_label("32766") == "新 run 开始"
        assert gdf_label("99999") == "99999"  # 未知码原样返回（不猜）
        assert gdf_label("T0") == "T0"  # 非数字不炸
        assert len(GDF_CODE_LABELS) == 16

    @pytest.mark.real
    @pytest.mark.skipif(not GDF_2A.exists(), reason="无 2a GDF 数据")
    def test_2a_real_chinese_labels(self):
        rec = open_file(GDF_2A)
        lab = dict(zip(rec.events.code, rec.events.label))
        assert lab["769"] == "提示：左手（类1）"
        assert lab["771"] == "提示：双脚（类3）"
        assert rec.meta.n_channels == 25 and rec.meta.sfreq == 250.0

    @pytest.mark.real
    @pytest.mark.skipif(not GDF_2B.exists(), reason="无 2b GDF 数据")
    def test_2b_real_entities_and_feedback(self):
        rec = open_file(GDF_2B)
        assert (rec.meta.subject, rec.meta.session, rec.meta.task) == ("B03", "03", "train")
        lab = dict(zip(rec.events.code, rec.events.label))
        assert lab["781"] == "BCI 反馈（连续）"


# --------------------------------------------------------------------- FIF
class TestFif:
    def test_roundtrip(self, tmp_path, synthetic_raw):
        """合成 raw → save FIF → open_file：头 + annotations 事件往返一致.

        （BDF/CNT/EGI/BrainVision/EEGLAB 无官方合成写出器，eeglabio/pybv
        未装——真实数据到位前由模板基类 + 静态审查保证，见 review.md M2）
        """
        p = tmp_path / "synth.fif"
        synthetic_raw.save(p, overwrite=True)
        rec = open_file(p)
        assert rec.meta.reader_id == "fif"
        assert rec.meta.n_channels == 8
        assert rec.meta.sfreq == 250.0
        assert rec.meta.n_events == 3
        assert set(rec.events.code) == {"T0", "T1", "T2"}

    def test_preload_window(self, tmp_path, synthetic_raw):
        p = tmp_path / "synth.fif"
        synthetic_raw.save(p, overwrite=True)
        rec = open_file(p, LoadPolicy.PRELOAD)
        d, t = rec.get_window(1.0, 2.0, [0])
        assert d.shape == (1, 250) and abs(t[0] - 1.0) < 1e-9


# -------------------------------------------------------------------- 嗅探
class TestSniffing:
    def test_magic_numbers(self, tmp_path):
        f = tmp_path / "x.bin"
        f.write_bytes(b"GDF \x02" + b"\x00" * 40)
        assert sniff_format(f) == "gdf"
        f.write_bytes(b"\xffBIOSEMI" + b"\x00" * 40)
        assert sniff_format(f) == "bdf"
        f.write_bytes(b"\x89HDF\r\n\x1a\n" + b"\x00" * 40)
        assert sniff_format(f) == "hdf5"
        f.write_bytes(b"Brain Vision Data Exchange Header File Version 1.0")
        assert sniff_format(f) == "brainvision"
        f.write_bytes(b"\x00" * 64)
        assert sniff_format(f) is None
