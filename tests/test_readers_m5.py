"""M5 扩展格式读取器测试：NWB 真实往返 + neo 模板（桩 rawio）.

测试策略（无真实 Blackrock/OE/Intan/NWB 样例文件的诚实边界）：
- NWB：pynwb 有完整写支持——**合成写出 → 读回往返**是实打实的全链路验证
- neo 系：用桩 rawio（numpy structured array 头 + 小数组）验证模板的
  关键逻辑：单位换算 uV→V、(n_times, n_ch)→(n_ch, n_times) 转置、
  多流选点数最多的流、事件时间戳→EventTable
- 注册/守卫：neo 与 pynwb 在场时三个 neo 读取器 + nwb 读取器都已注册；
  缺依赖时的跳过路径与 M2 相同（registry 的 import-guard，不重复测）
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

mne = pytest.importorskip("mne")
mne.set_log_level("ERROR")

from dataloadv.io.registry import READER_REGISTRY, open_file  # noqa: E402
from dataloadv.core.recording import LoadPolicy  # noqa: E402


# ---------------------------------------------------------------- NWB 往返

@pytest.fixture
def synth_nwb(tmp_path: Path) -> Path:
    """pynwb 写一个含 被试/电极表/ElectricalSeries/trials 的标准 NWB."""
    pynwb = pytest.importorskip("pynwb")
    from pynwb import NWBFile, NWBHDF5IO
    from pynwb.ecephys import ElectricalSeries
    from pynwb.file import Subject

    sf, n_ch, n_seconds = 250.0, 4, 10.0
    t = np.arange(int(sf * n_seconds)) / sf
    data = np.stack([20e-6 * np.sin(2 * np.pi * 10.0 * t) for _ in range(n_ch)], axis=1)

    nwb = NWBFile(
        session_description="合成测试", identifier="dlv-test",
        session_start_time=datetime.now(timezone.utc),
        subject=Subject(subject_id="S01"),
    )
    dev = nwb.create_device(name="amp")
    grp = nwb.create_electrode_group(name="g", device=dev, description="", location="")
    nwb.add_electrode_column("label", "通道名")  # pynwb 4 电极表默认无 label 列
    for i in range(n_ch):
        nwb.add_electrode(group=grp, label=f"EEG{i}", location="皮层")
    region = nwb.create_electrode_table_region(
        region=list(range(n_ch)), description="全部通道")
    series = ElectricalSeries(
        name="TestSeries", data=data, electrodes=region, rate=sf,
        conversion=1.0,  # data 已是伏特
    )
    nwb.add_acquisition(series)
    nwb.add_trial(start_time=2.0, stop_time=2.5, tags="T1")
    nwb.add_trial(start_time=6.0, stop_time=6.5, tags="T2")

    path = tmp_path / "synth.nwb"
    with NWBHDF5IO(path, "w") as io:
        io.write(nwb)
    return path


def test_nwb_reader_roundtrip(synth_nwb):
    """写出 → read_meta（零数据 IO）→ load_raw → open（含事件与被试）."""
    reader = READER_REGISTRY["nwb"]

    meta = reader.read_meta(synth_nwb)
    assert meta.n_channels == 4 and meta.sfreq == 250.0
    assert meta.duration_s == pytest.approx(10.0)
    assert meta.subject == "S01"  # NWB 头里的被试优先于文件名猜测
    assert meta.channel_names == ["EEG0", "EEG1", "EEG2", "EEG3"]

    raw = reader.load_raw(synth_nwb, LoadPolicy.PRELOAD)
    assert raw.n_times == 2500 and len(raw.ch_names) == 4
    # 第 0 通道 10Hz 正弦幅度 20µV——读回的伏特值应当一致（无缩放丢失）
    seg = raw.get_data(start=0, stop=250)[0]
    assert np.abs(seg).max() == pytest.approx(20e-6, rel=0.05)

    rec = reader.open(synth_nwb, LoadPolicy.HEADER_ONLY)
    assert rec.meta.n_events == 2
    assert list(rec.events.code) == ["T1", "T2"]
    assert rec.events.onset[0] == pytest.approx(2.0)

    # 统一入口也能按扩展名找到读取器
    rec2 = open_file(synth_nwb, LoadPolicy.HEADER_ONLY)
    assert rec2.meta.format == "NWB"


def test_nwb_reader_rejects_non_ecephys(tmp_path):
    """没有 ElectricalSeries 的 NWB → 明确中文拒绝（不猜）."""
    pynwb = pytest.importorskip("pynwb")
    from pynwb import NWBFile, NWBHDF5IO

    nwb = NWBFile(session_description="空", identifier="empty",
                  session_start_time=datetime.now(timezone.utc))
    path = tmp_path / "empty.nwb"
    with NWBHDF5IO(path, "w") as io:
        io.write(nwb)
    from dataloadv.io.base import ScanError

    with pytest.raises(ScanError, match="没有找到 ElectricalSeries"):
        READER_REGISTRY["nwb"].read_meta(path)


# ---------------------------------------------------------------- neo 模板（桩）

class _StubRawIO:
    """最小 neo.rawio 桩：structured array 头 + 小数组（模板逻辑验证用）."""

    def __init__(self, data, sfreq, n_streams=1, events=True):
        self._data = data  # (n_times, n_ch) 原始整数
        self._sfreq = sfreq
        n_ch = data.shape[1]
        # 流 0 故意只有一半点数——模板应选**点数最多**的最后一个流
        streams = [("s0", "sid0"), ("s1", "sid1")][: max(1, n_streams)]
        picked_sid = streams[-1][1]  # 通道全部挂在将被选中的流上
        self.header = {
            "signal_streams": np.array(
                streams, dtype=[("name", "U16"), ("id", "U16")]),
            # 单位一列 uV 一列 V：验证逐列换算
            "signal_channels": np.array(
                [("ch_uV", "0", sfreq, "int16", "uV", 1.0, 0.0, picked_sid),
                 ("ch_V", "1", sfreq, "int16", "V", 1.0, 0.0, picked_sid)][:n_ch],
                dtype=[("name", "U16"), ("id", "U8"), ("sampling_rate", "f8"),
                       ("dtype", "U8"), ("units", "U8"), ("gain", "f8"),
                       ("offset", "f8"), ("stream_id", "U16")]),
        }
        self._events = events
        self._picked = len(streams) - 1

    def signal_streams_count(self):
        return len(self.header["signal_streams"])

    def get_signal_size(self, block_index, seg_index, stream_index):
        return (self._data.shape[0] if stream_index == self._picked
                else self._data.shape[0] // 2)

    def get_signal_sampling_rate(self, stream_index):
        return self._sfreq

    def get_analogsignal_chunk(self, block_index, seg_index, stream_index):
        assert stream_index == self._picked, "模板应选点数最多的流"
        return self._data

    def rescale_signal_raw_to_float(self, chunk, dtype, stream_index):
        return chunk.astype(np.float64)  # 桩里 gain=1、offset=0

    def event_channels_count(self):
        return 1 if self._events else 0

    def get_event_timestamps(self, block_index, seg_index, event_channel_index):
        return (np.array([0, 250], dtype=np.int64), None,
                np.array(["ev_a", "ev_b"]))

    def rescale_event_timestamp(self, ts, dtype, event_channel_index):
        return ts / 250.0  # 样点 → 秒


def _stub_reader(data, sfreq=250.0, **kw):
    """构造接桩的模板子类实例（不注册——只测逻辑）."""
    from dataloadv.io.neo_reader import _NeoRawReader

    stub = _StubRawIO(data, sfreq, **kw)

    class _T(_NeoRawReader):
        reader_id = "_test_stub"
        rawio_cls_name = "IntanRawIO"  # 类名不会被用到（make_rawio 已覆盖）
        fmt_display = "桩"

        def make_rawio(self, path):
            return stub

    return _T(), stub


def test_neo_template_units_and_transpose(tmp_path):
    """uV/V 逐列换算到伏特 + (n_times,n_ch)→(n_ch,n_times) 转置 + 选最多点流."""
    data = np.array([[1000, 1], [2000, 2], [3000, 3], [4000, 4]], dtype=np.int16)
    reader, _ = _stub_reader(data)
    path = tmp_path / "x.rhd"
    path.touch()  # read_meta/common_meta_fields 要 stat

    raw = reader.load_raw(path, LoadPolicy.PRELOAD)
    assert raw.ch_names == ["ch_uV", "ch_V"]
    d = raw.get_data()
    assert d.shape == (2, 4)  # (n_ch, n_times)：转置后行=通道
    # ch_uV：原始 1000（桩 gain=1）× 1e-6 V = 1 mV；ch_V：原始值即伏特
    assert d[0, 0] == pytest.approx(1000 * 1e-6)
    assert d[1, 0] == pytest.approx(1.0)
    assert d[1, 3] == pytest.approx(4.0)


def test_neo_template_events_and_meta(tmp_path):
    """事件时间戳→EventTable（秒）；read_meta 的通道/采样率/时长."""
    data = np.zeros((500, 2), dtype=np.int16)
    reader, _ = _stub_reader(data)
    path = tmp_path / "x.rhd"
    path.touch()  # read_meta/common_meta_fields 要 stat

    events = reader.extract_events(reader.make_rawio(path), path)
    assert len(events) == 2
    assert list(events.code) == ["ev_a", "ev_b"]
    assert events.onset[1] == pytest.approx(1.0)  # 250 样点 / 250 Hz

    meta = reader.read_meta(path)
    assert meta.n_channels == 2 and meta.sfreq == 250.0
    assert meta.duration_s == pytest.approx(2.0)


def test_neo_readers_registered():
    """neo/pynwb 在场：三个 neo 读取器 + NWB 都已注册并接管对应扩展名."""
    for rid in ("blackrock", "openephys", "intan", "nwb"):
        assert rid in READER_REGISTRY, f"{rid} 未注册"
    assert ".nev" in READER_REGISTRY["blackrock"].extensions
    assert ".continuous" in READER_REGISTRY["openephys"].extensions
    assert ".rhd" in READER_REGISTRY["intan"].extensions
    assert ".nwb" in READER_REGISTRY["nwb"].extensions
