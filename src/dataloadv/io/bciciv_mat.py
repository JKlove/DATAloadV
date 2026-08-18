"""BCI Competition IV 的 .mat 读取器（数据集 1 / 4）+ 通用 .mat 拒绝猜测.

实测结构（2026-08-18 whosmat/loadmat 探测，data/dataset/ 实物）：

**数据集 1**（``BCICIV_calib_ds1a.mat`` / ``BCICIV_eval_ds1a.mat``）：
- ``cnt``  int16 (T×59) 连续 EEG，物理值 µV = 0.1 × cnt（0.1 µV/LSB）
- ``nfo``  struct：fs=100、clab（59 通道名）、classes（每被试 3 选 2，
  如 ['left','foot']，出自 {left, right, foot}）
- ``mrk``  struct（**仅 calib 有**；实测 eval 文件根本没有 mrk 变量）：
  pos（提示的样本下标）+ y（±1 类别，+1=nfo.classes[0]，-1=classes[1]）

**数据集 4**（``sub1_comp.mat``，113–134MB）：
- ``train_data`` double (400000×62) ECoG，原始 ADC 任意单位（官方未给
  µV 标度；desc_4.pdf 确认采样率 1000 Hz、带宽 0.15–200 Hz）
- ``train_dg``  double (400000×5) 数据手套 5 指屈曲（原 25Hz 上采样到 1kHz）
- ``test_data`` (200000×62) 评估集 ECoG，无标签——当前不读（meta 备注说明）

**数据集 3**（``S1.mat``）：分段 MEG（training_data 为 4 类 cell），v1
不支持——识别出来并给中文指引，而不是报"未知结构"。

**通用 .mat**：拒绝猜测。列出变量名与形状，说明缺什么信息。

多候选机制：.mat 扩展名有 3 个读取器注册（ds1/ds4/generic），open_file
按注册序逐个尝试。每个专用读取器先 whosmat（零数据 IO、毫秒级）判定
"是不是我的结构"，不是则立刻抛错让位——134MB 的 ds4 文件被 ds1 读取器
礼貌让行，全程不搬数据。

内存策略：ds1 的 read_meta 只 loadmat(variable_names=["nfo","mrk"])（跳过
几十 MB 的 cnt）；ds4 的 read_meta 纯 whosmat；ds4 的 load_raw 只取
train_data/train_dg 两个变量（跳过 test_data 的 ~100MB）。
"""

from __future__ import annotations

import logging
from pathlib import Path

import mne
import numpy as np
from scipy.io import loadmat, whosmat

from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .registry import register_reader

logger = logging.getLogger(__name__)
mne.set_log_level("ERROR")

# ds1 int16 → µV 的标度（官方 0.1 µV/LSB）
_DS1_LSB_TO_UV = 0.1
# ds4 采样率：文件里没有 fs 字段，1000 Hz 来自官方 desc_4.pdf
# （pipelineMotor configs/bciciv_4_mat.yaml 同源确认）
_DS4_SFREQ = 1000.0
# ds4 数据手套 5 指通道名（与 desc_4.pdf / 文献一致，保留英文便于对照）
_DS4_GLOVE_NAMES = ["thumb", "index", "middle", "ring", "little"]
# ds1 nfo.classes 的英文类名 → 中文标签（类名出自 {left, right, foot}）
_DS1_CLASS_ZH = {"left": "左手", "right": "右手", "foot": "脚"}


def _cell_str_list(arr) -> list[str]:
    """MATLAB cell 数组（(1,N) 每格一个字符数组）→ Python 字符串列表."""
    out: list[str] = []
    for e in np.ravel(np.asarray(arr)):
        if isinstance(e, np.ndarray):
            out.append(str(e.ravel()[0]) if e.size else "")
        else:
            out.append(str(e))
    return out


def _whosmat_vars(path: Path) -> dict[str, tuple]:
    """whosmat → {变量名: 形状}（结构判定与头解析的统一入口，零数据 IO）."""
    return {name: tuple(shape) for name, shape, _dt in whosmat(str(path))}


class _BciMatReader(BaseReader):
    """BCI-IV mat 家族公共：mat 无按窗口懒读能力，始终物化 RawArray."""

    lazy_capable = False

    def _not_mine(self, path: Path) -> ScanError:
        """结构不符时抛给 open_file 的"让位"错误（换下一候选尝试）."""
        return ScanError(str(path), self.reader_id, "结构不符（内部让位，用户不可见）")


@register_reader
class BciDs1Reader(_BciMatReader):
    """BCI-IV 数据集 1：59 导运动想象 EEG（calibration/evaluation 两类文件）."""

    reader_id = "bciciv_ds1"
    extensions = (".mat",)

    def read_meta(self, path: Path) -> RecordingMeta:
        return self._read_header(path)[0]

    def _read_header(self, path: Path) -> tuple[RecordingMeta, EventTable]:
        """whosmat 判结构 → 只读 nfo/mrk 小变量 → (meta, events).

        eval 文件无 mrk：events 为空、notes 说明标签未发布。
        """
        vars_ = _whosmat_vars(path)
        if "cnt" not in vars_ or "nfo" not in vars_:
            raise self._not_mine(path)
        d = loadmat(str(path), variable_names=["nfo", "mrk"])
        nfo = d["nfo"][0, 0]
        fs = float(nfo["fs"].ravel()[0])
        clab = _cell_str_list(nfo["clab"])
        n_t = vars_["cnt"][0]  # cnt (T, C) 的时间轴长度
        if "mrk" in d:
            events = self._events_from(d, fs)
            notes = ""
        else:
            events = EventTable()
            notes = "评估集：文件不含 mrk 标注（标签未随数据发布）"
        meta = RecordingMeta(
            **self.common_meta_fields(path, "BCI-IV ds1"),
            n_channels=len(clab), channel_names=clab,
            channel_types=["eeg"] * len(clab),
            sfreq=fs, duration_s=n_t / fs,
            n_events=len(events), event_summary=events.codes_summary(),
            notes=notes,
        )
        return meta, events

    @staticmethod
    def _events_from(d: dict, fs: float) -> EventTable:
        """mrk.pos（样本下标）+ mrk.y（±1）→ EventTable；code 用官方类名."""
        mrk = d["mrk"][0, 0]
        pos = np.asarray(mrk["pos"], dtype=float).ravel()
        y = np.asarray(mrk["y"], dtype=float).ravel()
        classes = _cell_str_list(d["nfo"][0, 0]["classes"])
        # +1 → classes[0]，-1 → classes[1]（BBCI 约定，pipelineMotor 同源确认）
        code_of = {1: classes[0], -1: classes[1]}
        codes, labels = [], []
        for lab in y:
            name = code_of.get(int(lab), "未知")
            codes.append(name)
            labels.append(_DS1_CLASS_ZH.get(name, name))
        return EventTable(
            onset=pos / fs, duration=np.zeros(len(pos)), code=codes, label=labels,
        )

    def load_raw(self, path: Path, policy: LoadPolicy):
        d = loadmat(str(path), variable_names=["cnt", "nfo"])
        nfo = d["nfo"][0, 0]
        fs = float(nfo["fs"].ravel()[0])
        clab = _cell_str_list(nfo["clab"])
        cnt = d["cnt"]
        # int16 LSB → µV（×0.1）→ 伏特（×1e-6）一步合并；转置成 mne 的 [ch, time]
        data = (cnt.astype(np.float64) * (_DS1_LSB_TO_UV * 1e-6)).T
        del cnt, d
        info = mne.create_info(clab, fs, ch_types="eeg", verbose="ERROR")
        return mne.io.RawArray(data, info, verbose="ERROR")

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        meta, events = self._read_header(path)
        rec = Recording(meta, events, self)
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec


@register_reader
class BciDs4Reader(_BciMatReader):
    """BCI-IV 数据集 4：ECoG + 数据手套连续屈曲（回归任务，无离散事件）.

    train_data → ecog 通道；train_dg → 5 个 misc 通道（与 ECoG 同屏浏览，
    手套屈曲轨迹叠加在 ECoG 下方，肉眼即可对齐放电与动作）。
    """

    reader_id = "bciciv_ds4"
    extensions = (".mat",)

    @staticmethod
    def _channels(n_ecog: int) -> tuple[list[str], list[str]]:
        """ECoG 通道文件里没有名字——合成 E1..En（与文献一致），手套用指名."""
        names = [f"E{i + 1}" for i in range(n_ecog)] + _DS4_GLOVE_NAMES
        return names, ["ecog"] * n_ecog + ["misc"] * len(_DS4_GLOVE_NAMES)

    def read_meta(self, path: Path) -> RecordingMeta:
        vars_ = _whosmat_vars(path)
        if "train_data" not in vars_ or "train_dg" not in vars_:
            raise self._not_mine(path)
        t, c = vars_["train_data"][:2]
        names, types = self._channels(c)
        return RecordingMeta(
            **self.common_meta_fields(path, "BCI-IV ds4"),
            n_channels=len(names), channel_names=names, channel_types=types,
            sfreq=_DS4_SFREQ, duration_s=t / _DS4_SFREQ,
            n_events=0, event_summary={},
            notes="ECoG 为原始 ADC 任意单位（官方未给 µV 标度）；"
                  "test_data（评估集，无标签）未读取，当前展示 train 部分",
        )

    def load_raw(self, path: Path, policy: LoadPolicy):
        vars_ = _whosmat_vars(path)
        if "train_data" not in vars_:
            raise self._not_mine(path)
        # 只取需要的两个变量（test_data 另占 ~100MB，跳过不读）
        d = loadmat(str(path), variable_names=["train_data", "train_dg"])
        ecog, glove = d["train_data"], d["train_dg"]  # 各为 (T, C)
        data = np.empty((ecog.shape[1] + glove.shape[1], ecog.shape[0]), dtype=np.float64)
        data[: ecog.shape[1]] = ecog.T
        data[ecog.shape[1]:] = glove.T
        del ecog, glove, d  # float64 中间体立即释放（134MB 文件峰值内存关键）
        names, types = self._channels(data.shape[0] - len(_DS4_GLOVE_NAMES))
        info = mne.create_info(names, _DS4_SFREQ, ch_types=types, verbose="ERROR")
        return mne.io.RawArray(data, info, verbose="ERROR")

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        meta = self.read_meta(path)
        rec = Recording(meta, EventTable(), self)  # 连续回归任务：无离散事件
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec


@register_reader
class GenericMatReader(_BciMatReader):
    """通用 .mat 兜底：不猜测未知结构，给可读诊断.

    为什么拒绝：采样率、物理单位、行列方向、通道类型全都无从得知，
    任何猜测都会产出"看起来对、其实错"的数据（如把 59×T 读成 59 通道
    或把 a.u. 当 µV）。宁可少一种格式，不可错一份数据。

    特例：BCI-IV ds3（S1/S2.mat，分段 MEG）识别后明确告知"分段数据暂
    不支持"，与"未知结构"区分开。
    """

    reader_id = "mat_generic"
    extensions = (".mat",)

    def read_meta(self, path: Path) -> RecordingMeta:
        vars_ = _whosmat_vars(path)
        names = set(vars_)
        if "Info" in names and "training_data" in names:
            raise ScanError(
                str(path), self.reader_id,
                "该文件是 BCI-IV 数据集 3（分段 MEG，按试次存储）。"
                "当前版本支持连续录制数据；分段数据读取已记入 backlog（TODO.md）",
            )
        shape_str = "、".join(f"{n}{s}" for n, s in list(vars_.items())[:6])
        raise ScanError(
            str(path), self.reader_id,
            f"无法识别的 .mat 结构（变量：{shape_str or '空'}）。"
            "采样率/单位/方向未知，本项目不猜测。请转换为 EDF/FIF，"
            "或反馈文件结构以添加专用读取器",
        )

    def load_raw(self, path: Path, policy: LoadPolicy):
        self.read_meta(path)  # 永远在读头阶段拒绝
        raise ScanError(str(path), self.reader_id, "不应到达此处")  # pragma: no cover
