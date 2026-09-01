"""连续 raw 导出：EDF（跨工具通用，16-bit 定点）或 FIF（mne 原生，无损往返）.

- EDF：``mne.export.export_raw``（内部 edfio）——V→µV 单位换算、prefiltering 头
  （由 info 的 highpass/lowpass/line_freq 组装）、annotations→EDF+C、整秒数据块
  edge-padding 等边角由官方维护。**physical_range="channelwise"**：每通道按自身
  min/max 用足 16-bit 量程——默认 "auto" 按通道类型统一量程，羊数据这类含
  ±375000µV 开路饱和通道的录制，统一量程下步长 ≈11.4µV/LSB 会把正常 20µV 级
  信号量化抹掉（见 MANUAL §3.8 限制小节）。
- FIF：``raw.save(fmt="single")``——float32，mne 生态内往返无损；文件名强制
  ``_raw`` 后缀（mne 命名规约：缺 ``.fif`` 是硬错，缺 ``_raw`` 是 warning）。
- 量化精度：EDF 步长 = (通道 max−min)/65535（channelwise），往返相对误差
  ~1e-4 量级；FIF 相对误差 ~6e-8（float32 eps）。

前置守卫（mne/edfio 的英文报错转为中文，且两类问题 edfio 直写同样躲不掉）：

1. 通道类型白名单外的通道（misc 等）在 mne 导出路径里数据留 V 却标 µV——
   单位错标是硬伤，前置拒绝；
2. 通道名 >16 字符或非 ASCII：mne 抛英文 RuntimeError / edfio 编码直接炸。

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import mne

logger = logging.getLogger(__name__)

# EDF 导出支持（µV 换算有定义）的通道类型——与 mne.export._edf_bdf 的换算
# 白名单对齐，越界类型数据留 V 却标 µV，属单位错标硬伤
_EDF_TYPES = {"eeg", "ecog", "seeg", "eog", "ecg", "emg", "bio", "dbs", "stim"}

# EDF 信号标签字段上限：16 个 ASCII 字符（规范头字段宽度）
_EDF_LABEL_MAX = 16


def _check_edf_exportable(raw) -> None:
    """EDF 导出前置校验：通道类型白名单 + 标签 ASCII ≤16 字符.

    :raises ValueError: 中文消息指出首个越界项（mne/edfio 的英文报错不可读）
    """
    bad_types = sorted(set(raw.get_channel_types()) - _EDF_TYPES)
    if bad_types:
        raise ValueError(
            f"通道类型 {bad_types} 不在 EDF 导出支持清单（µV 换算未定义）——请先转换或剔除")
    for name in raw.ch_names:
        if len(name) > _EDF_LABEL_MAX or not name.isascii():
            raise ValueError(
                f"通道名「{name}」超出 EDF 信号标签上限（{_EDF_LABEL_MAX} 个 ASCII 字符）——请先重命名")


def export_continuous(raw, path: str | Path, fmt: str = "edf") -> Path:
    """把处理后的连续 mne BaseRaw 写出为 EDF 或 FIF.

    :param raw: mne BaseRaw（需已 preload——本项目管线产物天然满足）
    :param fmt: "edf" | "fif"
    :returns: 实际写出的路径（后缀按格式规范化；FIF 补 ``_raw`` 规约后缀）
    """
    path = Path(path)
    if fmt == "edf":
        out = path.with_suffix(".edf")
        _check_edf_exportable(raw)
        mne.export.export_raw(out, raw, fmt="edf", physical_range="channelwise",
                              overwrite=True, verbose="ERROR")
        logger.info("连续 EDF 已写出：%s（%d 导 / %.1f s）",
                    out, len(raw.ch_names), raw.n_times / raw.info["sfreq"])
        return out
    if fmt == "fif":
        out = path.with_suffix(".fif")
        if not out.stem.endswith("_raw"):  # mne 命名规约（缺后缀仅警告，保持干净）
            out = out.with_name(f"{out.stem}_raw.fif")
        fnames = raw.save(out, overwrite=True, fmt="single", verbose="ERROR")
        logger.info("连续 FIF 已写出：%s（%d 导 / %d 个分片）",
                    out, len(raw.ch_names), len(fnames))
        return Path(fnames[0])
    raise ValueError(f"未知的连续导出格式「{fmt}」——可用：edf / fif")
