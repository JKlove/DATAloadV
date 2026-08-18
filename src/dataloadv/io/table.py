"""CSV / TXT 数值表格读取器（分隔符嗅探 + 采样率询问记忆）.

职责边界（拒绝猜测原则的体现）：
- **分隔符**：可嗅探（逗号/分号/制表符/空格/竖线），嗅探结果连同数据
  一起验证——解析出的列数必须全程一致才算数。
- **表头**：首行全部非数值 → 当通道名；否则无表头，合成 ch1..chN。
- **采样率**：文件里不存在，物理上无从嗅探。问用户（UI 层），答案经
  ``core.fs_store.FsStore`` 持久记忆；问之前 meta 里 sfreq=1.0 且
  notes 带 ``FS_UNSET_NOTE`` 标记——UI 看到标记弹询问框。
- **单位**：假定伏特？不——表格数据单位同样未知，原样读入（大多数
  导出的 CSV 是 µV）。notes 里注明"单位未知，原样显示"。

非数值表格（说明文件、校验和清单等）给出明确中文报错进错误表。
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

import mne
import numpy as np

from ..core.fs_store import FsStore
from ..core.recording import EventTable, LoadPolicy, Recording, RecordingMeta
from .base import BaseReader, ScanError
from .registry import register_reader

logger = logging.getLogger(__name__)
mne.set_log_level("ERROR")

# meta.notes 里的"采样率未设定"标记（UI 检测它弹询问框；问完清除）
FS_UNSET_NOTE = "采样率未设定（打开时询问）"
# 嗅探分隔符的候选（顺序即优先级；空格单独处理——连续空格算一个）
_DELIMS = [",", ";", "\t", "|", " "]
# read_meta 时预读的行数（够判结构就行，大文件不全读）
_PEEK_LINES = 64


def _sniff_delimiter(path: Path) -> tuple[str, list[list[str]]]:
    """读前几行 + 嗅探分隔符.

    :returns: (分隔符, 每行字段列表)
    :raises ScanError: 空文件 / 嗅探不出一致的分隔符
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        lines = [f.readline() for _ in range(_PEEK_LINES)]
    lines = [ln.rstrip("\r\n") for ln in lines if ln.strip()]
    if not lines:
        raise ScanError(str(path), "table", "文件为空或没有可解析的行")

    best: tuple[str, list[list[str]]] | None = None
    best_score = 0
    for delim in _DELIMS:
        rows = [next(csv.reader([ln], delimiter=delim)) for ln in lines]
        n_cols = {len(r) for r in rows}
        # 合格判定：≥2 列且所有行列数一致；列数最多者胜（区分逗号与分号场景）
        if len(n_cols) == 1 and min(n_cols) >= 2 and min(n_cols) > best_score:
            best, best_score = (delim, rows), min(n_cols)
    if best is None:
        raise ScanError(
            str(path), "table",
            "无法按数值表格解析（嗅探不出一致的列分隔符）。"
            "若是说明/校验文件可忽略本条；若是数据请转为 CSV（逗号分隔）后导入",
        )
    delim, rows = best
    # 数值性验证：除可能的表头行外，抽样行必须几乎全是数值——
    # 否则是"碰巧分列成功的散文"（如校验和清单），导入只会得到垃圾数据
    body = rows[1:] if not _is_numeric_row(rows[0]) else rows
    frac = sum(_is_numeric_row(r) for r in body) / max(len(body), 1)
    if frac < 0.9:
        raise ScanError(
            str(path), "table",
            "表格内容不是数值（可能是说明/校验文件），已跳过；"
            "若是数据文件请检查格式后重试",
        )
    return delim, rows


def _is_numeric_row(fields: list[str]) -> bool:
    """整行都能转 float 才算数值行（表头判定用）."""
    try:
        for x in fields:
            float(x)
        return True
    except ValueError:
        return False


@register_reader
class TableReader(BaseReader):
    """CSV / TXT：数值矩阵 → 连续录制（通道 × 时间的表格形式）."""

    reader_id = "table"
    extensions = (".csv", ".txt")
    lazy_capable = False  # 表格读取即全量（RawArray 物化）

    def _read_table(self, path: Path) -> tuple[list[str], np.ndarray, float | None]:
        """全量读取 → (通道名, 数据[ch,time], 已知采样率或 None).

        用 numpy 直接解析（比 pandas 少一层依赖行为差异），逐块拼装。
        """
        delim, peek = _sniff_delimiter(path)
        has_header = not _is_numeric_row(peek[0])
        names = (
            [f.strip() or f"ch{i+1}" for i, f in enumerate(peek[0])]
            if has_header else [f"ch{i+1}" for i in range(len(peek[1]))]
        )
        fs = FsStore().get(path)

        # 全量读（np.loadtxt 逐行解析浮点；首行表头用 skiprows 跳过）
        try:
            data = np.loadtxt(path, delimiter=delim, skiprows=1 if has_header else 0,
                              ndmin=2, encoding="utf-8-sig")
        except ValueError as e:
            raise ScanError(
                str(path), self.reader_id,
                f"表格含非数值内容，无法转为信号矩阵：{e}",
            ) from e
        if data.shape[1] != len(names):  # 行列方向：CSV 惯例每行一个时刻
            # 列数与表头不符时以数据为准（截断/补齐通道名）
            if data.shape[1] > len(names):
                names += [f"ch{i+1}" for i in range(len(names), data.shape[1])]
            else:
                names = names[: data.shape[1]]
        return names, data.T, fs  # 转置 → [ch, time]

    def read_meta(self, path: Path) -> RecordingMeta:
        delim, peek = _sniff_delimiter(path)
        has_header = not _is_numeric_row(peek[0])
        n_ch = len(peek[0]) if has_header else len(peek[1])
        # 行数 = 全文件行数 - 表头（读字节数 \\n，大文件也便宜）
        with open(path, "rb") as f:
            n_rows = sum(chunk.count(b"\n") for chunk in iter(lambda: f.read(1 << 20), b""))
        n_times = max(n_rows - (1 if has_header else 0), 1)
        fs = FsStore().get(path)
        meta = RecordingMeta(
            **self.common_meta_fields(path, "CSV/TXT"),
            n_channels=n_ch,
            channel_names=[f"ch{i+1}" for i in range(n_ch)],
            channel_types=["misc"] * n_ch,  # 单位未知 → misc（不冒充 eeg）
            sfreq=fs if fs else 1.0,
            duration_s=n_times / (fs if fs else 1.0),
            n_events=0, event_summary={},
            notes=FS_UNSET_NOTE if not fs else "表格数据：单位未知，原样显示",
        )
        return meta

    def load_raw(self, path: Path, policy: LoadPolicy):
        names, data, fs = self._read_table(path)
        info = mne.create_info(names, fs if fs else 1.0, ch_types="misc", verbose="ERROR")
        return mne.io.RawArray(data, info, verbose="ERROR")

    def open(self, path: Path, policy: LoadPolicy = LoadPolicy.HEADER_ONLY) -> Recording:
        meta = self.read_meta(path)
        rec = Recording(meta, EventTable(), self)
        if policy is LoadPolicy.PRELOAD:
            rec.ensure_raw(LoadPolicy.PRELOAD)
        return rec
