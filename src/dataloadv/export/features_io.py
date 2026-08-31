"""特征表导出：CSV（UTF-8 BOM，Excel 直接双击可开）与 HDF5.

- CSV 长表：列头用中文（COLUMNS_ZH）——M4 验证标准"Excel 可开中文表头"；
  epoch_index/event_code 为 None 的文件级行输出空单元格
- 曲线：CSV 时另写宽表 ``<名>_psd.csv``（freq 列 + 每曲线一列，列头
  "录制/通道"）；不同 freqs 轴（如不同采样率的录制）按轴分组各写一个文件
- HDF5：/features 下每列一个数据集（字符串列 utf-8 变长）+ /psd/<i>/{freqs,psd}
  与 attrs（recording/channel）——跨工具（Python/MATLAB）回读友好

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

from ..batch.results import COLUMNS, COLUMNS_ZH, FeatureTable

logger = logging.getLogger(__name__)


def export_features_csv(table: FeatureTable, path: str | Path) -> list[Path]:
    """长表 → CSV（中文表头、BOM）；有曲线时加写 PSD 宽表文件.

    :returns: 实际写出的全部文件（sidecar 由调用方统一写，不在此列）
    """
    path = Path(path)
    df = table.df
    out = df.rename(columns=COLUMNS_ZH)  # 中文表头
    out.to_csv(path, index=False, encoding="utf-8-sig")  # BOM：Excel 双击即正确识别
    written = [path]
    if table.curves:
        written.extend(_export_curves_csv(table.curves, path))
    logger.info("特征 CSV 已写出：%s（%d 行）", "、".join(map(str, written)), len(df))
    return written


def _export_curves_csv(curves: list[dict], main_path: Path) -> list[Path]:
    """曲线 → 宽表 CSV：freq 列 + 每条曲线一列；不同 freqs 轴分组写文件."""
    # 按频率轴分组（不同采样率/参数的录制轴不同，不能混在一张表）
    groups: dict[tuple[float, ...], list[dict]] = {}
    for c in curves:
        key = tuple(np.round(c["freqs"], 6))
        groups.setdefault(key, []).append(c)
    written = []
    for gi, (freqs, group) in enumerate(groups.items()):
        stem = main_path.with_suffix("")  # a.csv → a_psd.csv / a_psd2.csv …
        p = stem.with_name(f"{stem.name}_psd{'' if gi == 0 else gi + 1}.csv")
        data = {"freq (Hz)": list(freqs)}
        for c in group:
            # M8.3 列头带时间窗标记（window="" 时与旧格式逐字节一致，零回归）
            data[f"{c['recording']} · {c['channel']}{c.get('window', '')} (µV²/Hz)"] = list(c["psd"])
        pd.DataFrame(data).to_csv(p, index=False, encoding="utf-8-sig")
        written.append(p)
    return written


def export_features_hdf5(table: FeatureTable, path: str | Path) -> Path:
    """长表 + 曲线 → HDF5（/features/* 列数据集 + /psd/<i>/{freqs,psd}）."""
    path = Path(path)
    df = table.df
    utf8 = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "w") as f:
        g = f.create_group("features")
        g.attrs["columns"] = COLUMNS  # 列顺序（value 为 float，其余字符串）
        g.attrs["n_rows"] = len(df)
        g.create_dataset("value", data=df["value"].to_numpy(dtype="f8"))
        for col in ("recording", "subject", "event_code", "channel", "feature"):
            vals = ["" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)
                    for v in df[col]]
            g.create_dataset(col, data=np.asarray(vals, dtype=object), dtype=utf8)
        # 段序号：文件级行（None）用 -1 表示——HDF5 无原生可空整数
        ep = df["epoch_index"].to_numpy(dtype="float64")
        g.create_dataset("epoch_index", data=np.where(np.isnan(ep), -1, ep), dtype="i8")
        if table.curves:
            cg = f.create_group("psd")
            cg.attrs["psd_unit"] = "uV^2/Hz"
            for i, c in enumerate(table.curves):
                d = cg.create_group(f"{i:04d}")
                d.attrs["recording"] = c["recording"]
                d.attrs["channel"] = c["channel"]
                d.attrs["window"] = str(c.get("window", ""))  # M8.3 时间窗标记
                d.create_dataset("freqs", data=c["freqs"])
                d.create_dataset("psd", data=c["psd"])
    logger.info("特征 HDF5 已写出：%s（%d 行，%d 条曲线）", path, len(df), len(table.curves))
    return path


def read_features_hdf5(path: str | Path) -> tuple[pd.DataFrame, list[dict]]:
    """回读 ``export_features_hdf5`` 的产物（测试与下游脚本用）.

    :returns: (长表 DataFrame——列结构与 COLUMNS 一致, 曲线列表)
    """
    with h5py.File(Path(path), "r") as f:
        g = f["features"]
        data = {"value": np.asarray(g["value"])}
        for col in ("recording", "subject", "event_code", "channel", "feature"):
            data[col] = [s.decode("utf-8") for s in np.asarray(g[col])]
        ep = np.asarray(g["epoch_index"])
        data["epoch_index"] = pd.array(np.where(ep < 0, None, ep), dtype="Int64")
        df = pd.DataFrame(data)[list(COLUMNS)]
        curves = []
        if "psd" in f:
            for key in sorted(f["psd"]):
                d = f["psd"][key]
                curves.append({
                    "recording": d.attrs["recording"],
                    "channel": d.attrs["channel"],
                    # 旧文件无 window attrs → ""（等价全量），不炸回读
                    "window": d.attrs.get("window", ""),
                    "freqs": np.asarray(d["freqs"]),
                    "psd": np.asarray(d["psd"]),
                })
    return df, curves
