"""EDF 读取器测试：合成 EDF 全流程 + 真实羊数据（实为 BDF 的 .edf）.

2026-08-24 实证：data/sheep、sheep2、sheep3 的 6 个 .edf 文件内容全是
BDF（\xffBIOSEMI 头）——按 EDF 读会把 24-bit 样本按 16-bit 解码，时长
虚增 1.5×、数值全部错位。registry 现按魔数"内容优先"派发，本文件锁定
该行为（真实数据 + 合成双向误标）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dataloadv.core.recording import EventTable, LoadPolicy, LoadedRawCache
from dataloadv.io.registry import READER_REGISTRY, open_file, scan_folder
from dataloadv.io.sniffing import sniff_format

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
    ("edf_name", "dur_s"),
    [
        ("data(DGDJ-卧-接地-2)-HKY.edf", 180.0),
        ("data(DGDJ-站-接地-4)-HKY.edf", 182.0),
        ("data(DGDJ-走动-接地-3)-HKY.edf", 222.0),
    ],
)
def test_sheep_mislabeled_bdf(edf_name: str, dur_s: float):
    """真实羊数据：.edf 扩展名实为 BDF——按魔数以 BDF 读取，解码正确.

    时长断言用 BDF 正确解码值（按 EDF 错误解码会虚增 1.5×：180→270）。
    """
    path = SHEEP / edf_name
    rec = open_file(path)
    assert rec.meta.format == "BDF"
    assert rec.meta.n_channels == 8
    assert rec.meta.sfreq == pytest.approx(250.0)
    assert rec.meta.duration_s == pytest.approx(dur_s, abs=0.5)
    data, times = rec.get_window(10.0, 11.0)
    assert data.shape == (8, 250)
    assert np.isfinite(data).all()
    rec.unload()


@pytest.mark.real
def test_scan_sheep_folder():
    """目录扫描：3 个羊文件全识别、零错误，且 meta 格式判为 BDF."""
    report = scan_folder(SHEEP)
    assert len(report.items) == 3
    assert report.errors == []
    assert all(i.meta.format == "BDF" for i in report.items)
    metas = {i.meta.filename for i in report.items}
    assert any("卧" in m for m in metas)


def test_sniff_format_magic_table(tmp_path):
    """魔数表：EDF 严格前 8 字节版本域（患者域不参与）/BDF/GDF/HDF5/未知.

    EDF 分支曾查 head[1:9]（越界到患者域首字节），真 EDF 会漏判——
    b"0       X" 锁定只认 '0'+7 空格。
    """
    def probe(data: bytes) -> str | None:
        p = tmp_path / "x.bin"
        p.write_bytes(data)
        return sniff_format(p)

    assert probe(b"0       X") == "edf"
    assert probe(b"\xffBIOSEMI" + b"\x00" * 8) == "bdf"
    assert probe(b"GDF ") == "gdf"
    assert probe(b"GDC") == "gdf"  # v1.x 老头（'GDC' 三字节）
    assert probe(b"\x89HDF\r\n\x1a\n") == "hdf5"
    assert probe(b"\x89PNG\r\n\x1a\n") is None  # 拒绝猜测：未知魔数返回 None


def test_open_reverse_mislabel_edf_as_bdf_ext(tmp_path):
    """反向误标：真 EDF 内容存成 .bdf → 按内容以 EDF 读取.

    mne read_raw_edf 公共入口按扩展名硬拒绝（"Only EDF files are
    supported"），此处锁定 file-like 对象绕过扩展名检查、仍走公共
    入口（read_raw_edf，不直接实例化 Raw* 构造器）的回退路径。
    """
    path = _write_synth_edf(tmp_path)
    renamed = path.with_suffix(".bdf")
    path.rename(renamed)
    rec = open_file(renamed)
    assert rec.meta.format == "EDF"
    assert rec.meta.n_channels == 3
    assert rec.meta.duration_s == pytest.approx(20.0, abs=0.2)
    assert len(rec.events) == 2


def test_mislabel_plus_latin1_combined_fallback(tmp_path):
    """组合回退：错扩展名 + 非 UTF-8 注释同时出现 → file-like + latin1 都生效.

    覆盖 _read_mne_robust 的嵌套分支：file-like 重读仍撞 invalid byte
    时，seek(0) 回卷后以 latin1 再读——两条回退叠加的完整链路。
    """
    path = _write_synth_edf(tmp_path)
    data = path.read_bytes()
    i = data.rfind(b"T0")
    assert i > 0
    path.write_bytes(data[:i] + b"\xc6" + data[i + 1:])
    renamed = path.with_suffix(".bdf")
    path.rename(renamed)

    rec = open_file(renamed)
    assert rec.meta.format == "EDF"
    assert len(rec.events) == 2
    rec.unload()


def test_mislabeled_file_like_raw_is_copyable(tmp_path):
    """file-like 绕过读取的 raw 必须可 copy/deepcopy（预览链路硬依赖）.

    file-like 改造实测坑：mne 把 file-like 存进 _raw_extras[*]["blob"] 与
    _init_kwargs["input_fname"]，残留引用使 raw.copy() 抛
    "cannot pickle '_io.BufferedReader'"（e2e_m3 预览的 ProcessingContext
    即 raw.copy()）。_detach_file_handles 剥离两处——本测试锁住该行为。
    """
    path = _write_synth_edf(tmp_path)
    renamed = path.with_suffix(".bdf")
    path.rename(renamed)
    rec = open_file(renamed, LoadPolicy.PRELOAD)

    copied = rec.raw.copy()  # deepcopy 全对象图
    assert copied.n_times == rec.raw.n_times
    assert len(copied.annotations) == len(rec.raw.annotations)
    assert copied.ch_names == rec.raw.ch_names
    # 剥离后数据仍完整可取（整载在内存，不经文件句柄）
    assert copied.get_data(start=0, stop=10).shape[0] == 3
    rec.unload()


def test_edf_latin1_fallback_on_nonutf8_annotation(tmp_path):
    """真 EDF 注释通道含非 UTF-8 字节 → 自动 latin1 回退读取.

    背景翻案（M6.5）：M1 时羊数据触发此回退，实为 BDF 被 EDF 错误解码的
    副产品（错位字节被当注释文本 UTF-8 解码）；羊按 BDF 读后不再触发。
    本测试用手工植入非法字节的合成 EDF 锁住回退行为——真 latin1 老文件
    （欧洲旧记录仪重音字符）仍会走到这条路，防止回归。
    """
    path = _write_synth_edf(tmp_path)
    data = path.read_bytes()
    i = data.rfind(b"T0")  # 数据区注释文本（头部无 "T0" 子串）
    assert i > 0
    path.write_bytes(data[:i] + b"\xc6" + data[i + 1:])  # 等长替换成 latin1 字节

    rec = open_file(path)
    assert rec.meta.format == "EDF"
    assert len(rec.events) == 2  # 注释仍解析出 2 个事件（坏字节按 latin1 解码）
    assert rec.events.code[0].endswith("0") and rec.events.code[1] == "T1"
    rec.unload()


def test_content_wins_over_extension_no_fallback(tmp_path):
    """内容优先且不兜底：\xffBIOSEMI 头的损坏 .edf → 错误必须来自 bdf 读取器.

    若派发回落扩展名候选（edf 读取器），BDF 内容会被静默错位解码——
    锁定"魔数明确时不给扩展名候选兜底"的语义。
    """
    bad = tmp_path / "fake.edf"
    bad.write_bytes(b"\xffBIOSEMI" + b"\x00" * 56)
    from dataloadv.io.base import ScanError

    with pytest.raises(ScanError) as ei:
        open_file(bad)
    assert ei.value.reader_id == "bdf"


def test_scan_folder_unknown_extensions_ignored(tmp_path):
    """无读取器接管的扩展名静默跳过（不产生错误行）——RECORDS/图片等配套文件场景.

    注：.txt/.csv 自 M2 起由 TableReader 接管（非数值 txt 会进错误表并
    说明原因，见 test_readers_m2.py::test_prose_txt_refused）。
    """
    (tmp_path / "RECORDS").write_text("x")
    (tmp_path / "note.md").write_text("x")
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
