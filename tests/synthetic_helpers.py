"""合成数据文件工厂：伪造各格式的测试夹具（不用 134MB 真文件跑单测）.

覆盖：BCI-IV ds1/ds4 的 .mat 结构、CSV/TXT 表格、通用 HDF5。
结构严格按 2026-08-18 对 data/dataset 实物的 whosmat/loadmat 探测结果
伪造（见 io/bciciv_mat.py 模块 docstring）——保证"合成能过 = 真件能过"。
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
from scipy.io import savemat


def make_ds1_mat(path: Path, n_times: int = 5000, fs: float = 100.0,
                 n_events: int = 8, with_mrk: bool = True) -> Path:
    """伪造 BCI-IV ds1 结构：cnt(int16 T×59) + nfo{fs,clab,classes} + mrk{pos,y}.

    信号有真实幅度：基线 + 正弦（µV 量级，0.1µV/LSB 标度下 int16 有意义）。
    """
    rng = np.random.default_rng(7)
    t = np.arange(n_times) / fs
    # cnt 单位 0.1µV/LSB：50µV 峰峰值正弦 → ±250 LSB，远在 int16 范围内
    sig = (30 * np.sin(2 * np.pi * 10 * t)[None, :] * np.ones((59, 1))
           + rng.normal(0, 5, (59, n_times)))
    cnt = np.round(sig / 0.1).astype(np.int16)  # (ch, T) → 存成 (T, ch)
    clab = [f"ch{i+1}" for i in range(59)]
    nfo = {"fs": np.array([[fs]]), "clab": np.array(clab, dtype=object).reshape(1, 59),
           "classes": np.array(["left", "foot"], dtype=object).reshape(1, 2)}
    out: dict = {
        "cnt": cnt.T,
        "nfo": np.array([(nfo["fs"], nfo["clab"], nfo["classes"])],
                        dtype=[("fs", "O"), ("clab", "O"), ("classes", "O")]),
    }
    if with_mrk:
        pos = np.linspace(500, n_times - 500, n_events).astype(np.int32).reshape(1, -1)
        y = rng.choice([-1, 1], size=n_events).astype(np.int16).reshape(1, -1)
        out["mrk"] = np.array([(pos, y)], dtype=[("pos", "O"), ("y", "O")])
    savemat(str(path), out)
    return path


def make_ds4_mat(path: Path, n_times: int = 3000, n_ch: int = 8) -> Path:
    """伪造 BCI-IV ds4 结构：train_data(T×C) + train_dg(T×5) + test_data(T×C)."""
    rng = np.random.default_rng(11)
    t = np.arange(n_times) / 1000.0
    ecog = (rng.normal(0, 500, (n_times, n_ch)) + 200 * np.sin(2 * np.pi * 8 * t)[:, None])
    glove = rng.normal(0, 1, (n_times, 5)) * 0.5 + 0.5
    savemat(str(path), {
        "train_data": ecog, "test_data": ecog[: n_times // 2],
        "train_dg": glove,
    })
    return path


def make_ds3_like_mat(path: Path) -> Path:
    """伪造 BCI-IV ds3 结构（Info + training_data cell）——用于"识别后拒绝"."""
    info = {"Task": np.array(["Classification of directionally modulated MEG activity."]),
            "SampleRate": np.array([[400.0]])}
    savemat(str(path), {
        "Info": np.array([(info["Task"], info["SampleRate"])],
                         dtype=[("Task", "O"), ("SampleRate", "O")]),
        "training_data": np.zeros((1, 4), dtype=object),
        "test_data": np.zeros((4, 400, 10)),
    })
    return path


def make_unknown_mat(path: Path) -> Path:
    """结构不明的 .mat（任意变量名）——用于通用读取器拒绝猜测."""
    savemat(str(path), {"banana": np.zeros((3, 3)), "apple": np.zeros(5)})
    return path


def make_csv(path: Path, n_times: int = 500, n_ch: int = 4, delim: str = ",",
             header: bool = True, fs: float | None = None) -> Path:
    """数值 CSV/TXT：正弦 + 噪声；delim 可选逗号/分号/制表符/空格."""
    rng = np.random.default_rng(3)
    t = np.arange(n_times) / (fs or 250.0)
    data = np.column_stack([np.sin(2 * np.pi * (5 + i) * t) + rng.normal(0, 0.1, n_times)
                            for i in range(n_ch)])
    lines = []
    if header:
        lines.append(delim.join(f"ch{i+1}" for i in range(n_ch)))
    for row in data:
        lines.append(delim.join(f"{v:.6f}" for v in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_hdf5(path: Path, shape: tuple[int, int], time_axis: int = 0,
              fs: float | None = 250.0, fs_attr: str = "sfreq") -> Path:
    """通用 HDF5：单个 2-D 数据集 + 可选采样率属性.

    time_axis=0 → 数据集形状 (T, ch)（HDF5 流式写入惯例）；1 → (ch, T)。
    """
    rng = np.random.default_rng(5)
    with h5py.File(str(path), "w") as f:
        d = f.create_dataset("signal", data=rng.normal(0, 1, shape).astype(np.float32))
        if fs is not None:
            d.attrs[fs_attr] = fs
    return path


def make_synth_edf(path: Path, seed: int = 0, n_seconds: float = 20.0,
                   n_ch: int = 4, fs: float = 250.0) -> Path:
    """合成连续 EDF（M9 批处理导出测试用）：10µV 白噪声 + 10Hz 正弦.

    经 mne.export 写盘——edfio 产出的真实 EDF 结构，io 注册表读回路径
    与真件一致（合成能过 = 真件能过，本文件总约定）。
    """
    import mne

    rng = np.random.default_rng(seed)
    t = np.arange(int(n_seconds * fs)) / fs
    data = (rng.normal(0, 10e-6, (n_ch, len(t)))  # V（mne 约定）
            + 20e-6 * np.sin(2 * np.pi * 10 * t)[None, :])
    raw = mne.io.RawArray(data, mne.create_info(n_ch, fs, "eeg"), verbose="ERROR")
    raw.export(path, fmt="edf", overwrite=True, verbose="ERROR")
    return path
