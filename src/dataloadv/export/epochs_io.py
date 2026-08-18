"""分段数据导出：HDF5（跨工具通用）或 FIF（mne 原生，无损往返）.

- HDF5 结构（v1 固定）::

      /epochs/data        [n_epochs, n_channels, n_times]  float32（V）
      /epochs/times       [n_times]                         float64（相对事件锚点，s）
      /epochs/event_codes [n_epochs]                        int64（原始码经 event_id 逆映射前的 mne 整数码）
      /epochs/… attrs：sfreq / ch_names / ch_types / bads / tmin / tmax /
                       baseline / event_id_map（mne 整数码→原始事件码 JSON）

  事件码说明：``event_codes`` 存 mne 的整数码（跨段可比），原始字符串码
  （如 "769"/"T1"）在 ``event_id_map`` attrs 里查——回读方按需映射。
- FIF：``epochs.save()``——mne 生态内往返无损，任何 mne 工具直接可读

float32 决策：288×22×1251 的 double 是 63 MB、float32 是 32 MB；分析精度
足够，回读验证用 allclose（rtol=1e-5）而非逐位相等。

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import h5py
import numpy as np

logger = logging.getLogger(__name__)


def export_epochs(epochs, path: str | Path, fmt: str = "hdf5") -> Path:
    """把 mne.Epochs 写出为 HDF5 或 FIF.

    :param epochs: mne.Epochs（需已含数据——本项目管线产物天然满足）
    :param fmt: "hdf5" | "fif"
    :returns: 实际写出的路径（后缀按格式规范化）
    """
    path = Path(path)
    if fmt == "fif":
        out = path.with_suffix(".fif")
        epochs.save(out, overwrite=True, fmt="single", verbose="ERROR")
        logger.info("分段 FIF 已写出：%s（%d 段）", out, len(epochs))
        return out
    if fmt != "hdf5":
        raise ValueError(f"未知的分段导出格式「{fmt}」——可用：hdf5 / fif")
    out = path.with_suffix(".h5")
    data = epochs.get_data()  # [n_ep, n_ch, n_t]，V
    with h5py.File(out, "w") as f:
        g = f.create_group("epochs")
        g.create_dataset("data", data=data.astype("f4"))
        g.create_dataset("times", data=np.asarray(epochs.times, dtype="f8"))
        g.create_dataset("event_codes", data=epochs.events[:, -1].astype("i8"))
        g.attrs["sfreq"] = float(epochs.info["sfreq"])
        g.attrs["ch_names"] = list(epochs.info["ch_names"])
        g.attrs["ch_types"] = list(epochs.get_channel_types())
        g.attrs["bads"] = list(epochs.info.get("bads", []))
        g.attrs["tmin"] = float(epochs.tmin)
        g.attrs["tmax"] = float(epochs.tmax)
        # mne 整数码 → 原始事件码字符串（逆映射，HANDOFF 坑 #20：Epochs 无 event_name）
        g.attrs["event_id_map"] = json.dumps(
            {str(v): k for k, v in epochs.event_id.items()}, ensure_ascii=False
        )
    logger.info("分段 HDF5 已写出：%s（%d 段 × %d 通道 × %d 点）",
                out, *data.shape)
    return out


def read_epochs_hdf5(path: str | Path) -> dict:
    """回读 ``export_epochs`` 的 HDF5 产物（测试与下游脚本用）.

    :returns: {"data", "times", "event_codes", "sfreq", "ch_names", "ch_types",
               "bads", "tmin", "tmax", "event_id_map"}
    """
    with h5py.File(Path(path), "r") as f:
        g = f["epochs"]
        raw_names = g.attrs.get("ch_names", [])
        return {
            "data": np.asarray(g["data"]),
            "times": np.asarray(g["times"]),
            "event_codes": np.asarray(g["event_codes"]),
            "sfreq": float(g.attrs["sfreq"]),
            "ch_names": [s.decode() if isinstance(s, bytes) else str(s) for s in raw_names],
            "ch_types": [s.decode() if isinstance(s, bytes) else str(s)
                         for s in g.attrs.get("ch_types", [])],
            "bads": [s.decode() if isinstance(s, bytes) else str(s)
                     for s in g.attrs.get("bads", [])],
            "tmin": float(g.attrs["tmin"]),
            "tmax": float(g.attrs["tmax"]),
            "event_id_map": json.loads(g.attrs["event_id_map"]),
        }
