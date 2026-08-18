"""neo 系读取器：Blackrock / Open Ephys（legacy）/ Intan（rhd·rhs）.

设计（M2 模板家族的延续）：
- 一个模板基类 ``_NeoRawReader`` 吃掉 neo.rawio 的全部共性：解析头 →
  选流 → 取数据 → 按通道单位换算成伏特 → mne RawArray；事件通道 →
  EventTable。三个子类只声明 neo 的 RawIO 类 + 构造方式 + 接管扩展名
- ``requires_extra = "neo"``：neo 缺失时注册表自动跳过（import-guard，
  应用其余功能不受影响——neo 是 pip 安装的可选依赖）
- 通道类型统一标 ``eeg``（neo 头里没有模态信息；下游特征白名单
  DATA_CH_TYPES 含 eeg，可直接提特征）

与 plan 的偏离（记入 review.md）：Intan 不再 vendored 官方 read_intan.py
（1000+ 行第三方代码），改用 neo.rawio.IntanRawIO——依赖统一、维护面小。

neo.rawio 关键事实（0.14 实测，baserawio 源码核实）：
- ``header['signal_channels']`` / ``['signal_streams']`` 是 **numpy
  structured array**——行用字段名取值：``row['name']`` / ``row['units']`` /
  ``row['stream_id']``
- ``get_analogsignal_chunk(stream_index=..)`` 返回 (n_times, n_ch) 原始整数；
  ``rescale_signal_raw_to_float`` 应用 gain/offset 得到**通道单位**下的
  浮点值——单位到伏特的最后一步由本模块按 units 字典换算
- ``parse_header()`` 只读头；事件时间戳（``get_event_timestamps``）与信号
  数据（chunk）分开读取——``open()`` 拿事件不触信号数据，浏览 tab 惰性
  整载时才真正读数据

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar, Optional

import numpy as np

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .registry import register_reader

logger = logging.getLogger(__name__)

try:  # import-guard：缺 neo 时类定义仍可 import（注册表会跳过注册）
    import neo.rawio as neo_rawio_mod
except ImportError:  # pragma: no cover - 环境相关
    neo_rawio_mod = None

# 通道单位 → 伏特换算（neo 头的 units 字段取值有限，未知单位明确报错不猜）
_UNITS_TO_V = {"V": 1.0, "mV": 1e-3, "uV": 1e-6, "µV": 1e-6, "nV": 1e-9}


class _NeoRawReader(BaseReader):
    """neo.rawio 模板基类：子类给 RawIO 类名与构造参数即可.

    类属性：
    - ``rawio_cls_name``：neo.rawio 里的类名（延迟取类——缺 neo 也能定义本类）
    - ``open_kw``：构造参数名（"filename" / "dirname"）
    - ``fmt_display``：meta.format 显示名
    """

    requires_extra: ClassVar[Optional[str]] = "neo"
    lazy_capable: ClassVar[bool] = False  # neo 无按窗口懒读 → 始终整载
    rawio_cls_name: ClassVar[str] = ""
    open_kw: ClassVar[str] = "filename"
    fmt_display: ClassVar[str] = "neo"

    # ------------------------------------------------------------------ rawio

    @property
    def rawio_cls(self):
        return getattr(neo_rawio_mod, self.rawio_cls_name)

    def make_rawio(self, path: Path):
        """构造并 parse_header（头解析失败转中文 ScanError）.

        子类可覆盖（Blackrock 需要去扩展名的基名回退——neo 对
        ``xxx.ns5`` / ``xxx.nev`` / 纯基名 ``xxx`` 三种写法兼容性随版本变）.
        """
        try:
            rawio = self.rawio_cls(**{self.open_kw: str(path)})
            rawio.parse_header()
            return rawio
        except Exception as e:  # noqa: BLE001 - neo 异常转中文可操作信息
            raise ScanError(str(path), self.reader_id,
                            f"解析 {path.name} 失败（{self.fmt_display}）：{e}") from e

    # ------------------------------------------------------------------ 头信息

    def _stream_index(self, rawio, path: Path) -> int:
        """选信号流（多流时取时间点最多的——通常主采样流）."""
        n_streams = rawio.signal_streams_count()
        if n_streams == 0:
            raise ScanError(str(path), self.reader_id,
                            f"{path.name} 里没有连续信号通道（{self.fmt_display}）")
        best, best_size = 0, -1
        for i in range(n_streams):
            size = rawio.get_signal_size(block_index=0, seg_index=0, stream_index=i)
            if size > best_size:
                best, best_size = i, size
        if n_streams > 1:
            logger.info("%s 含 %d 个信号流，取时间点最多的流 #%d",
                        self.fmt_display, n_streams, best)
        return best

    def _stream_channels(self, rawio, stream_index: int) -> list:
        """头里属于该流的信号通道行（numpy record，字段名取值）."""
        sid = rawio.header["signal_streams"][stream_index]["id"]
        return [ch for ch in rawio.header["signal_channels"]
                if ch["stream_id"] == sid]

    def read_meta(self, path: Path) -> RecordingMeta:
        """仅解析头（parse_header 不触信号数据本体）."""
        rawio = self.make_rawio(path)
        i = self._stream_index(rawio, path)
        chans = self._stream_channels(rawio, i)
        if len(chans) == 0:
            raise ScanError(str(path), self.reader_id, "该信号流没有通道")
        sfreq = float(rawio.get_signal_sampling_rate(stream_index=i))
        n_times = rawio.get_signal_size(block_index=0, seg_index=0, stream_index=i)
        names = [str(c["name"]) for c in chans]
        return RecordingMeta(
            **self.common_meta_fields(path, self.fmt_display),
            n_channels=len(names),
            channel_names=names,
            channel_types=["eeg"] * len(names),
            sfreq=sfreq,
            duration_s=n_times / sfreq,
            notes=f"{self.fmt_display}（经 neo 读取；通道类型按 eeg 处理）",
        )

    # ------------------------------------------------------------------ 数据

    def load_raw(self, path: Path, policy: LoadPolicy):
        """整载信号数据 → mne RawArray（BaseReader 契约：只返回 raw）.

        neo 无懒读，policy 实际不区分——始终整载（lazy_capable=False，
        Recording.recommended_policy 会给 PRELOAD）。
        """
        import mne

        mne.set_log_level("ERROR")
        rawio = self.make_rawio(path)
        i = self._stream_index(rawio, path)
        chans = self._stream_channels(rawio, i)
        names = [str(c["name"]) for c in chans]

        chunk = rawio.get_analogsignal_chunk(
            block_index=0, seg_index=0, stream_index=i)  # (n_times, n_ch) 原始整数
        scaled = rawio.rescale_signal_raw_to_float(
            chunk, dtype="float64", stream_index=i)  # gain/offset 后（通道单位）
        # 通道单位 → 伏特（逐列乘；未知单位报中文错，绝不静默错单位）
        factors = np.array([_unit_factor(c, path) for c in chans])
        data_v = scaled * factors[None, :]  # (n_times, n_ch)
        sfreq = float(rawio.get_signal_sampling_rate(stream_index=i))

        info = mne.create_info(names, sfreq, ch_types=["eeg"] * len(names))
        return mne.io.RawArray(data_v.T, info, verbose="ERROR")  # (n_ch, n_times)

    # ------------------------------------------------------------------ 事件 + open

    def extract_events(self, rawio, path: Path) -> EventTable:
        """neo 事件通道 → EventTable（失败降级为空表——事件不该挡住浏览）."""
        try:
            n_ev = rawio.event_channels_count()
        except Exception:  # noqa: BLE001 - 无事件接口的格式
            return EventTable()
        onsets, codes = [], []
        try:
            for j in range(n_ev):
                ts, _dur, labels = rawio.get_event_timestamps(
                    block_index=0, seg_index=0, event_channel_index=j)
                if ts is None or len(ts) == 0:
                    continue
                sec = rawio.rescale_event_timestamp(
                    ts, dtype="float64", event_channel_index=j)
                onsets.append(np.asarray(sec, dtype=float))
                codes.extend(str(x) for x in np.atleast_1d(labels))
            if not onsets:
                return EventTable()
            return EventTable(
                onset=np.concatenate(onsets),
                duration=np.zeros(sum(len(o) for o in onsets)),
                code=codes, label=list(codes),
            )
        except Exception as e:  # noqa: BLE001 - 事件解析失败不挡数据
            logger.warning("%s 事件解析失败（忽略事件）：%s", path.name, e)
            return EventTable()

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY):
        """覆盖默认 open：parse_header 后单独取事件（不触信号数据）."""
        meta = self.read_meta(path)
        rawio = self.make_rawio(path)  # read_meta 内已 parse 过；再来一次换取事件
        events = self.extract_events(rawio, path)
        meta.n_events = len(events)
        meta.event_summary = events.codes_summary()
        rec = Recording(meta, events, self)
        if policy is not LoadPolicy.HEADER_ONLY:
            rec.ensure_raw(policy)
        return rec


def _unit_factor(chan_row, path: Path) -> float:
    """信号通道头行 → 单位到伏特的系数（未知单位给中文错误）."""
    units = str(chan_row["units"])
    if units not in _UNITS_TO_V:
        raise ScanError(
            str(path), "neo",
            f"通道单位「{units}」无法换算（已知：{'、'.join(_UNITS_TO_V)}）——"
            "请把数据导出为已知单位后重试",
        )
    return _UNITS_TO_V[units]


# ====================================================================== 子类

@register_reader
class BlackrockReader(_NeoRawReader):
    """Blackrock (.nev + .ns1-.ns6)：事件来自 .nev，数据来自高采样 .nsX."""

    reader_id = "blackrock"
    extensions = (".nev", ".ns1", ".ns2", ".ns3", ".ns4", ".ns5", ".ns6")
    rawio_cls_name = "BlackrockRawIO"
    fmt_display = "Blackrock"

    def make_rawio(self, path: Path):
        """带扩展名失败时回退去扩展名基名（neo 对基名/全名的兼容随版本变）."""
        try:
            return super().make_rawio(path)
        except ScanError:
            return super().make_rawio(path.with_suffix(""))


@register_reader
class OpenEphysReader(_NeoRawReader):
    """Open Ephys legacy 连续格式（.continuous；新版导出走 NWB）.

    neo 的 OpenEphysRawIO 收**目录**——传入单个 .continuous 文件时取其
    父目录（多文件 = 一条录制的各通道，neo 自行配对）。
    """

    reader_id = "openephys"
    extensions = (".continuous",)
    rawio_cls_name = "OpenEphysRawIO"
    open_kw = "dirname"
    fmt_display = "Open Ephys"

    def make_rawio(self, path: Path):
        return super().make_rawio(path.parent)


@register_reader
class IntanReader(_NeoRawReader):
    """Intan (.rhd/.rhs)：单文件即完整录制（含采样率与放大倍数）."""

    reader_id = "intan"
    extensions = (".rhd", ".rhs")
    rawio_cls_name = "IntanRawIO"
    fmt_display = "Intan"
