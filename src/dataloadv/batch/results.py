"""FeatureTable——特征结果的统一载体（长表 + 曲线，pandas）.

长表（tidy）设计：一行 = 一个 (录制, 段, 通道, 特征) 的值。跨录制/跨提取器
拼接零成本，批处理（M5）逐文件 ``add_result`` 即得全库一张表；需要"每行一个
样本"的宽表（喂分类器/统计软件）时再 ``to_wide()`` 透视。

曲线（PSD）单独存放：freqs 轴无法塞进长表的 value 列，导出时写 HDF5 数据集
或 CSV 宽表（features_io 负责）。

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ..features.base import ExtractorResult

# 长表列（顺序即导出顺序；中文表头映射见 export/features_io.py）
COLUMNS = ["recording", "subject", "epoch_index", "event_code", "channel", "feature", "value"]

# 列名 → 中文表头（CSV 导出用——"Excel 可开中文表头"验证标准的数据来源）
COLUMNS_ZH = {
    "recording": "录制",
    "subject": "被试",
    "epoch_index": "段序号",
    "event_code": "事件码",
    "channel": "通道",
    "feature": "特征",
    "value": "数值",
}


class FeatureTable:
    """特征长表 + 曲线集合.

    用法（单文件 / 批处理统一）::

        table = FeatureTable()
        table.add_result(result, recording="A01T.gdf", subject="A01")
        table.df        # 长表 DataFrame
        table.to_wide() # 透视宽表（行=段×通道，列=特征）
    """

    def __init__(self) -> None:
        self._rows: list[dict] = []
        self._curves: list[dict] = []
        self._df_cache: Optional[pd.DataFrame] = None  # add_result 后失效重建

    # ------------------------------------------------------------------ 累积

    def add_result(self, result: ExtractorResult, recording: str, subject: str = "") -> None:
        """并入一次提取产出（文件级字段在这里统一补——提取器不感知文件身份）.

        :param recording: 录制显示名（一般用 meta.filename）
        :param subject: 被试名（可为空串；批处理跨被试对比时关键）
        """
        for s in result.scalars:
            row = {"recording": recording, "subject": subject or ""}
            row.update({k: s.get(k) for k in ("epoch_index", "event_code", "channel", "feature")})
            row["value"] = float(s["value"])
            self._rows.append(row)
        for c in result.curves:
            self._curves.append({
                "recording": recording,
                "channel": c.get("channel", ""),
                "freqs": np.asarray(c["freqs"], dtype=float),
                "psd": np.asarray(c["psd"], dtype=float),  # µV²/Hz
            })
        self._df_cache = None

    # ------------------------------------------------------------------ 读取

    @property
    def df(self) -> pd.DataFrame:
        """长表（惰性构建；epoch_index/event_code 为 None 表示文件级行）."""
        if self._df_cache is None:
            self._df_cache = pd.DataFrame(self._rows, columns=COLUMNS)
            if not self._df_cache.empty:
                # 段序号存 Int64：既保留 None（文件级）又可在 UI 排序/筛选为整数
                self._df_cache["epoch_index"] = self._df_cache["epoch_index"].astype("Int64")
        return self._df_cache

    @property
    def curves(self) -> list[dict]:
        """曲线行列表（每条含 recording/channel/freqs/psd）."""
        return self._curves

    def to_wide(self) -> pd.DataFrame:
        """透视宽表：行 = (录制, 被试, 段, 事件码, 通道)，列 = 特征名.

        同键重复值（如同一管线加两个同频段的频带功率）取首个——此时值本来就
        相同，无损；真的要区分请给频段起不同名字。
        """
        if self.df.empty:
            return pd.DataFrame()
        index = ["recording", "subject", "epoch_index", "event_code", "channel"]
        # dropna=False：文件级行的 epoch_index/event_code 是 <NA> 组键，
        # pandas 默认会把这些组整组丢掉——正是 raw 全量特征的主场景
        wide = self.df.pivot_table(
            index=index, columns="feature", values="value",
            aggfunc="first", dropna=False,
        ).reset_index()
        wide.columns.name = None  # 去掉 pivot 的 columns 名（导出表头干净）
        return wide

    # ------------------------------------------------------------------ 摘要

    def __len__(self) -> int:
        return len(self._rows)

    @property
    def n_recordings(self) -> int:
        return len({r["recording"] for r in self._rows} | {c["recording"] for c in self._curves})

    def recording_names(self) -> list[str]:
        """涉及的全部录制名（sidecar 文件清单用，保持首次出现顺序）."""
        seen: dict[str, None] = {}
        for r in [*self._rows, *self._curves]:
            seen.setdefault(r["recording"], None)
        return list(seen)

    def summary_zh(self) -> str:
        """中文一行摘要（UI tab 标题栏/日志）."""
        n_ep = self.df["epoch_index"].dropna().nunique() if not self.df.empty else 0
        parts = [f"{len(self._rows)} 个特征值", f"{self.n_recordings} 个录制"]
        if n_ep:
            parts.append(f"{n_ep} 个分段")
        if self._curves:
            parts.append(f"{len(self._curves)} 条 PSD 曲线")
        return "，".join(parts)
