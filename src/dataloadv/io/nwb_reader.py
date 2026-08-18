"""NWB 读取器（pynwb）：NWB::Neurodata 神经电生理标准格式的只读入口.

定位：读取 ``acquisition``（或 ``processing/ecephys``）里的第一个
``ElectricalSeries`` 作为连续数据；``intervals``（trials/epochs）表与
``acquisition`` 里的 TimeSeries 事件转 EventTable。这是 v1 的诚实边界——
复杂 NWB（多 ElectricalSeries、多 session）不猜，明确提示。

实现要点：
- ``read_meta`` **零数据 IO**：HDF5 数据集的 shape 属性不触值即可拿到
  （GB 级文件毫秒级），采样率来自 series.rate / starting_time
- ``load_raw`` 才把数据读进内存：data × conversion(+offset) → 伏特，
  mne RawArray；shape (n_times, n_ch) 与 (n_ch, n_times) 两种存放都支持
  （按较长的轴是时间轴判定——与 io/hdf5.py 同约定）
- ``requires_extra = "pynwb"``：pynwb 缺失时注册表跳过（conda 安装的可选
  依赖；应用其余功能不受影响）
- 通道类型标 ``eeg``（NWB 电极表无模态映射时；有 location 信息但语义
  不稳定，v1 不映射）

事件来源优先级：trials 表（start_time + tags）> epochs 表 > 无事件。

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


@register_reader
class NwbReader(BaseReader):
    """NWB 文件（.nwb）——pynwb 读取 ElectricalSeries."""

    reader_id = "nwb"
    extensions = (".nwb",)
    lazy_capable = False  # pynwb 无按窗口懒读 → 始终整载
    requires_extra: ClassVar[Optional[str]] = "pynwb"
    fmt_display = "NWB"

    # ------------------------------------------------------------------ 打开

    def _open_io(self, path: Path):
        """pynwb 打开文件（失败转中文 ScanError）."""
        from pynwb import NWBHDF5IO

        try:
            io = NWBHDF5IO(str(path), mode="r", load_namespaces=True)
        except Exception as e:  # noqa: BLE001 - pynwb/h5py 异常转中文
            raise ScanError(str(path), self.reader_id,
                            f"打开 NWB 文件失败（{path.name}）：{e}") from e
        return io

    def _find_series(self, nwbfile, path: Path):
        """找第一个 ElectricalSeries（acquisition 优先，其次 processing）.

        :raises ScanError: 没有 ElectricalSeries（说明这不是电生理 NWB，
            或结构超出 v1 支持范围——明确说，不猜）
        """
        from pynwb.ecephys import ElectricalSeries

        candidates = [v for v in nwbfile.acquisition.values()
                      if isinstance(v, ElectricalSeries)]
        if not candidates:
            for mod in nwbfile.processing.values():
                candidates += [v for v in getattr(mod, "data_interfaces", {}).values()
                               if isinstance(v, ElectricalSeries)]
        if not candidates:
            raise ScanError(
                str(path), self.reader_id,
                f"{path.name} 里没有找到 ElectricalSeries（电生理数据系列）。"
                "可能不是神经电生理 NWB 文件，或结构超出当前支持范围",
            )
        if len(candidates) > 1:
            logger.info("NWB 含 %d 个 ElectricalSeries，取第一个：%s",
                        len(candidates), candidates[0].name)
        return candidates[0]

    # ------------------------------------------------------------------ 头信息

    def read_meta(self, path: Path) -> RecordingMeta:
        """仅解析头（零数据 IO：shape 是 HDF5 属性，不触值）."""
        io = self._open_io(path)
        try:
            nwbfile = io.read()
            series = self._find_series(nwbfile, path)
            shape = tuple(int(x) for x in series.data.shape)
            n_times, n_ch = self._orient(shape)
            rate = self._rate(series)
            names = self._channel_names(nwbfile, series, n_ch)
            notes = [f"NWB（pynwb 读取；series={series.name}；通道类型按 eeg 处理）"]
            if nwbfile.subject is not None and nwbfile.subject.subject_id:
                notes.append(f"被试 {nwbfile.subject.subject_id}")
            meta = RecordingMeta(
                **self.common_meta_fields(path, self.fmt_display),
                n_channels=n_ch,
                channel_names=names,
                channel_types=["eeg"] * n_ch,
                sfreq=rate,
                duration_s=n_times / rate,
                notes="；".join(notes),
            )
            # 被试实体：NWB 头里有就用它（文件名猜不出的场景）
            if nwbfile.subject is not None and nwbfile.subject.subject_id:
                meta.subject = nwbfile.subject.subject_id
            return meta
        finally:
            io.close()

    # ------------------------------------------------------------------ 数据

    def load_raw(self, path: Path, policy: LoadPolicy):
        """整载数据 → mne RawArray（conversion/offset → 伏特）."""
        import mne

        mne.set_log_level("ERROR")
        io = self._open_io(path)
        try:
            nwbfile = io.read()
            series = self._find_series(nwbfile, path)
            data = np.asarray(series.data[()])  # 整读（pynwb 无懒读）
            n_times, n_ch = self._orient(tuple(data.shape))
            if data.shape[0] != n_times:  # (n_ch, n_times) 存放 → 转成行=时间
                data = data.T
            # NWB 约定 data × conversion + offset = 伏特
            conv = float(getattr(series, "conversion", 1.0) or 1.0)
            off = float(getattr(series, "offset", 0.0) or 0.0)
            data_v = data.astype(np.float64) * conv + off
            rate = self._rate(series)
            names = self._channel_names(nwbfile, series, n_ch)
            info = mne.create_info(names, rate, ch_types=["eeg"] * n_ch)
            return mne.io.RawArray(data_v.T, info, verbose="ERROR")
        finally:
            io.close()

    # ------------------------------------------------------------------ 事件 + open

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY):
        """覆盖默认 open：事件来自 trials/epochs 表（零数据 IO）."""
        io = self._open_io(path)
        try:
            nwbfile = io.read()
            self._find_series(nwbfile, path)  # 头校验（顺带在 meta 前发现结构问题）
            events = self._events(nwbfile)
        finally:
            io.close()
        meta = self.read_meta(path)
        meta.n_events = len(events)
        meta.event_summary = events.codes_summary()
        rec = Recording(meta, events, self)
        if policy is not LoadPolicy.HEADER_ONLY:
            rec.ensure_raw(policy)
        return rec

    def _events(self, nwbfile) -> EventTable:
        """trials/epochs 表 → EventTable（无表则空；失败不挡数据）."""
        try:
            for name in ("trials", "epochs"):
                table = getattr(nwbfile, name, None)
                if table is None or len(table) == 0:
                    continue
                onset = np.asarray(table["start_time"][:], dtype=float)
                dur = np.asarray(table["stop_time"][:] if "stop_time" in table.colnames
                                 else np.zeros(len(table)), dtype=float)
                dur = np.maximum(dur - onset, 0.0)
                # 码：tags 列（list of list）平铺；无 tags 用表名
                if "tags" in table.colnames:
                    codes = [str(t[0]) if len(t) else name
                             for t in table["tags"][:]]
                else:
                    codes = [name] * len(table)
                return EventTable(onset=onset, duration=dur,
                                  code=codes, label=list(codes))
        except Exception as e:  # noqa: BLE001 - 事件失败只降级
            logger.warning("NWB 事件表解析失败（忽略事件）：%s", e)
        return EventTable()

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _orient(shape: tuple[int, ...]) -> tuple[int, int]:
        """(n_times, n_ch)：较长轴为时间（与 io/hdf5.py 同约定）."""
        if len(shape) != 2:
            raise ScanError("", "nwb",
                            f"ElectricalSeries 数据不是二维（shape={shape}）——"
                            "超出当前支持范围")
        a, b = shape
        return (a, b) if a >= b else (b, a)

    @staticmethod
    def _rate(series) -> float:
        """采样率：rate 属性优先；只有 timestamps 时取中位间隔的倒数."""
        rate = getattr(series, "rate", None)
        if rate:
            return float(rate)
        ts = getattr(series, "timestamps", None)
        if ts is not None and len(ts) > 1:
            return float(1.0 / np.median(np.diff(np.asarray(ts[:1000], dtype=float))))
        raise ScanError("", "nwb", "ElectricalSeries 既无 rate 也无 timestamps——无法确定采样率")

    def _channel_names(self, nwbfile, series, n_ch: int) -> list[str]:
        """通道名：电极表 region 的 label 列（实测 ``region["label"][:]`` 可取，
        注意 ``region.colnames`` 是 None——不能拿它判列存在性）；取不到按序号编."""
        region = getattr(series, "electrodes", None)
        if region is not None:
            try:
                names = [str(x) for x in region["label"][:]]
                if len(names) == n_ch:
                    return names
            except Exception:  # noqa: BLE001 - 无 label 列/结构异常 → 回退编号
                pass
        return [f"ch{i:03d}" for i in range(n_ch)]
