"""通用 HDF5 读取器（.h5 / .hdf5）——已知结构放行，未知拒绝猜测.

接受的结构（诚实边界）：
- 根下（或一级子组里，最多下钻 3 层）恰好一个显著大的 2-D 数值数据集，
  形状 (n_ch, n_times) 或 (n_times, n_ch)——行数/列数较大者为时间轴
- 采样率取数据集或根的属性 ``sfreq`` / ``fs`` / ``sample_rate`` /
  ``sampling_rate``；没有则与 CSV 同策略：meta 标记未设定，UI 打开时
  询问并记忆（``core.fs_store.FsStore``）

拒绝的结构：
- 多个同级大数组（不知道哪个是信号）、无非 2-D 数值数据集
  ——列出找到的结构让用户判断，不猜

性能：``read_meta`` 只看形状与属性（零数据 IO，GB 级文件毫秒级）；
``load_raw`` 才把数据集读进内存。

注：NWB / Intan rhs.md 也是 HDF5，但有各自的标准结构——M5 用专用
读取器（pynwb / vendored Intan reader）接管，不归本读取器猜。
"""

from __future__ import annotations

import logging
from pathlib import Path

import mne
import numpy as np

from ..core.fs_store import FsStore
from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .registry import register_reader
from .table import FS_UNSET_NOTE

logger = logging.getLogger(__name__)
mne.set_log_level("ERROR")

# 约定俗成的采样率属性名（数据集或根组上找）
_FS_ATTRS = ("sfreq", "fs", "sample_rate", "sampling_rate")


def _walk_datasets(grp) -> list[tuple[str, object]]:
    """递归收集 (路径, dataset)，最多下钻 3 层（再深说明不是简单布局）."""
    out: list[tuple[str, object]] = []

    def _walk(g, depth: int) -> None:
        if depth > 3:
            return
        for key in g:
            item = g[key]
            if hasattr(item, "shape"):  # Dataset
                out.append((item.name, item))
            else:  # Group
                _walk(item, depth + 1)

    _walk(grp, 0)
    return out


@register_reader
class Hdf5Reader(BaseReader):
    """通用 HDF5：单个 2-D 数值矩阵 + （属性或询问得知的）采样率."""

    reader_id = "hdf5"
    extensions = (".h5", ".hdf5")
    lazy_capable = False

    # ------------------------------------------------------------------ 定位
    def _locate(self, path: Path) -> tuple[str, tuple[int, int], int, float | None]:
        """零数据 IO 定位信号数据集.

        :returns: (数据集路径, 形状, 时间轴 0/1, 采样率或 None)
        :raises ScanError: 无候选 / 结构有歧义（拒绝猜测）
        """
        import h5py

        with h5py.File(str(path), "r") as f:
            dsets = [
                (name, d) for name, d in _walk_datasets(f)
                if d.ndim == 2 and np.issubdtype(d.dtype, np.number)
            ]
            if not dsets:
                raise ScanError(
                    str(path), self.reader_id,
                    "HDF5 内没有 2-D 数值数据集（可能只是分组容器或字符串表）",
                )
            dsets.sort(key=lambda nd: nd[1].size, reverse=True)
            name, d = dsets[0]
            # 次大者若与最大同量级（>50% 大小），结构有歧义——拒绝猜测
            if len(dsets) > 1 and dsets[1][1].size > 0.5 * d.size:
                names = "、".join(n for n, _ in dsets[:4])
                raise ScanError(
                    str(path), self.reader_id,
                    f"HDF5 内有多个同级大数组（{names}），不确定哪个是信号；"
                    "请反馈文件结构以添加专用读取器",
                )
            time_axis = 0 if d.shape[0] >= d.shape[1] else 1
            fs = FsStore().get(path)
            if not fs:  # 属性里找约定俗成的采样率键（数据集优先，根组兜底）
                for attrs in (d.attrs, f.attrs):
                    for k in _FS_ATTRS:
                        if k in attrs:
                            fs = float(np.ravel(attrs[k])[0])
                            break
                    if fs:
                        break
            return name, tuple(d.shape), time_axis, fs

    # ------------------------------------------------------------------ 契约
    def read_meta(self, path: Path) -> RecordingMeta:
        _name, shape, time_axis, fs = self._locate(path)
        n_ch, n_t = (shape[1], shape[0]) if time_axis == 0 else shape
        return RecordingMeta(
            **self.common_meta_fields(path, "HDF5"),
            n_channels=n_ch,
            channel_names=[f"ch{i+1}" for i in range(n_ch)],
            channel_types=["misc"] * n_ch,  # 通道类型未知，不冒充 eeg
            sfreq=fs if fs else 1.0,
            duration_s=n_t / (fs if fs else 1.0),
            n_events=0, event_summary={},
            notes=FS_UNSET_NOTE if not fs else "通用 HDF5：单位与通道类型未知",
        )

    def load_raw(self, path: Path, policy: LoadPolicy):
        name, _shape, time_axis, fs = self._locate(path)
        import h5py

        with h5py.File(str(path), "r") as f:
            arr = f[name][()]  # 离开文件作用域前读入内存
        data = arr.T if time_axis == 0 else arr  # → [ch, time]
        info = mne.create_info(
            [f"ch{i+1}" for i in range(data.shape[0])],
            fs if fs else 1.0, ch_types="misc", verbose="ERROR",
        )
        return mne.io.RawArray(
            np.ascontiguousarray(data, dtype=np.float64), info, verbose="ERROR"
        )

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        meta = self.read_meta(path)
        rec = Recording(meta, EventTable(), self)
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec
