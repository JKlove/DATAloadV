"""特征结果图表区（M8.3）：PSD 曲线多通道一图 + 标量特征柱状网格.

架构规则 #2：UI 不做计算——本模块只做**展示聚合**（柱状网格把分段行按
事件码求均值、曲线只筛 psd>0 的点便于 log 轴绘制），先例
epochs_preview._draw_average；特征数值本身一律来自 features 层。

三个入口：
- ``PsdCurvesChart``：``FeatureTable.curves`` → log-log 叠加图（逐通道×逐
  时间窗一条曲线，intColor 分色，图例蝶形同款分列）
- ``FeatureBarGrid``：``FeatureTable.df`` 长表 → 每特征一格的柱状网格
  （分段数据按事件码求均值聚合——288 段画不了，类间比较是 BCI 常态；
  纯 raw 行系列=录制名）。每特征一格天然解决时域 8 统计量量纲不同的问题
- ``make_charts_area``：按 table 内容组装（双有=QTabWidget、单有=单图、
  全无=None——空表零观感变化）
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...batch.results import FeatureTable
from ..strings_zh import S

# 截断上限：超限只画前 N 条/项并出提示（45 文件×22 通道=990 条曲线的
# 批处理场景，全画既卡也看不清）
MAX_CURVES = 60
MAX_FEATURES = 24
MAX_SERIES = 12
_GRID_COLS = 3  # 柱状网格每行格数


def _make_legend(plot: pg.PlotItem, n_items: int) -> pg.LegendItem:
    """蝶形图同款图例（M8.2 观感）：8pt 文字、半透明白底、灰框、自动分列.

    0.14 图例默认无底框（NoBrush）文字压曲线，且单列超过 ~12 行在矮窗口
    排不到底被裁断——每列至多 12 行自动分列（≥73 项封顶 6 列接受截断）。
    """
    legend = plot.addLegend(labelTextSize="8pt", offset=(10, 10))
    legend.setBrush(pg.mkBrush(255, 255, 255, 210))
    legend.setPen(pg.mkPen("#bbbbbb"))
    legend.setColumnCount(min((n_items + 11) // 12, 6))
    return legend


class PsdCurvesChart(QWidget):
    """PSD 曲线叠加图（log-log，复用管线 PSD 视图的轴标签与画法）.

    :param curves: FeatureTable.curves——每条含 recording/channel/window/
      freqs/psd（µV²/Hz）；freqs/psd 为空的条目跳过
    """

    def __init__(self, curves: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        usable = [c for c in curves if len(c.get("freqs", [])) and len(c.get("psd", []))]
        multi_rec = len({str(c.get("recording", "")) for c in usable}) > 1
        shown = usable[:MAX_CURVES]
        # 测试断言用：实际绘制数与总数（截断提示走 FEAT_CHART_CURVE_TRUNC）
        self.n_curves = len(shown)
        self.total_curves = len(usable)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if self.total_curves > self.n_curves:
            lay.addWidget(QLabel(S.FEAT_CHART_CURVE_TRUNC.format(
                total=self.total_curves, n=self.n_curves)))

        self._plot = pg.PlotItem()
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setLabel("bottom", S.PIPE_PSD_AXIS_X)
        self._plot.setLabel("left", S.PIPE_PSD_AXIS_Y)
        self._plot.setLogMode(x=True, y=True)  # 双对数：脑电谱斜率直观
        gfx = pg.GraphicsLayoutWidget()
        gfx.addItem(self._plot, 0, 0)
        lay.addWidget(gfx, 1)

        if not shown:
            return
        legend = _make_legend(self._plot, self.n_curves)
        for i, c in enumerate(shown):
            freqs = np.asarray(c["freqs"], dtype=float)
            psd = np.asarray(c["psd"], dtype=float)
            mask = psd > 0  # log 轴不能画 0/负值
            label = f"{c.get('channel', '')}{c.get('window', '')}"
            if multi_rec:
                label = f"{c.get('recording', '')} · {label}"
            item = self._plot.plot(
                freqs[mask], psd[mask],
                pen=pg.mkPen(pg.intColor(i, hues=max(self.n_curves, 6)), width=1),
            )
            legend.addItem(item, label)


class FeatureBarGrid(QWidget):
    """标量特征柱状网格：每特征一格（title=特征名），x=通道，系列分组着色.

    展示聚合规则（hint 与 docstring 同口径）：
    - 有分段行（epoch_index 非 NA）→ 按 (录制, 事件码, 通道, 特征) 求均值，
      系列=事件码（多录制=「录制 · 码」）——段数动辄数百，画不了也看不出
      规律，类间比较才是 BCI 常态
    - 纯 raw 行 → 系列=录制名（多录制跨文件对比）
    - event_code 缺失的行（raw 混入/未知码）→ 系列回落为录制名

    构造期同步聚合（80k 行 groupby 毫秒级，无后台线程无竞态）；聚合结果
    存 ``self.aggregated``、展示的特征名存 ``self.feature_names``（测试
    数值断言不解析像素）。
    """

    def __init__(self, table: FeatureTable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        df = table.df
        multi_rec = df["recording"].nunique() > 1
        has_epochs = bool(df["epoch_index"].notna().any())

        # 展示聚合：dropna=False 让文件级行（event_code 为 NA）保留成组
        agg = (
            df.groupby(["recording", "event_code", "channel", "feature"],
                       dropna=False, sort=False, observed=True)["value"]
            .mean().reset_index()
        )

        def _series_of(rec: str, code) -> str:
            if pd.notna(code):
                return f"{rec} · {code}" if multi_rec else str(code)
            return str(rec)

        agg["series"] = [
            _series_of(r, c) for r, c in zip(agg["recording"], agg["event_code"])
        ]
        self.aggregated = agg
        self.has_epochs = has_epochs

        channels = list(dict.fromkeys(agg["channel"].astype(str)))
        features_all = list(dict.fromkeys(agg["feature"].astype(str)))
        series_all = list(dict.fromkeys(agg["series"]))
        shown_features = features_all[:MAX_FEATURES]
        shown_series = series_all[:MAX_SERIES]
        self.feature_names = shown_features
        self.series_names = shown_series

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if has_epochs:
            lay.addWidget(QLabel(S.FEAT_CHART_EP_AGG))
        if len(series_all) > len(shown_series):
            lay.addWidget(QLabel(S.FEAT_CHART_SERIES_TRUNC.format(
                total=len(series_all), n=len(shown_series))))
        if len(features_all) > len(shown_features):
            lay.addWidget(QLabel(S.FEAT_CHART_FEATURE_TRUNC.format(
                total=len(features_all), n=len(shown_features))))

        # (特征, 系列, 通道) → 值：画格时 O(1) 取数
        lookup = {
            (f, s, ch): v
            for f, s, ch, v in zip(agg["feature"].astype(str), agg["series"],
                                   agg["channel"].astype(str), agg["value"])
        }
        n_ch, n_ser = len(channels), len(shown_series)
        bar_w = 0.8 / max(n_ser, 1)
        gfx = pg.GraphicsLayoutWidget()
        for i, fname in enumerate(shown_features):
            plot = gfx.addPlot(i // _GRID_COLS, i % _GRID_COLS, title=fname)
            plot.showGrid(x=True, y=True, alpha=0.25)
            for k, sname in enumerate(shown_series):
                hs = np.asarray(
                    [lookup.get((fname, sname, ch), np.nan) for ch in channels],
                    dtype=float,
                )
                m = ~np.isnan(hs)
                if not m.any():
                    continue
                # 同通道内系列并排（组内居中），宽度=组宽/系列数
                xs = np.arange(n_ch) + (k - (n_ser - 1) / 2.0) * bar_w
                plot.addItem(pg.BarGraphItem(
                    x=xs[m], height=hs[m], width=bar_w * 0.9,
                    brush=pg.intColor(k, hues=max(n_ser, 6)), pen=None,
                ))
            # x 轴通道名；>12 个时隔名标注（22 通道全标会重叠）
            step = 1 if n_ch <= 12 else 2
            plot.getAxis("bottom").setTicks(
                [[(j, ch) for j, ch in enumerate(channels) if j % step == 0]]
            )
            if i == 0 and n_ser > 1:
                # 系列图例只挂第一格（各格 intColor 口径一致，颜色可通用）
                legend = _make_legend(plot, n_ser)
                for k, sname in enumerate(shown_series):
                    dummy = pg.PlotDataItem(
                        pen=None, symbol="s", symbolSize=10,
                        symbolBrush=pg.intColor(k, hues=max(n_ser, 6)),
                    )
                    legend.addItem(dummy, sname)

        # 多行内容超出视口 → 滚动（每格固定 ~240px 行高）
        gfx.setMinimumHeight(math.ceil(len(shown_features) / _GRID_COLS) * 240)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(gfx)
        lay.addWidget(scroll, 1)


def make_charts_area(table: FeatureTable) -> QWidget | None:
    """按 table 内容组装图表区：双有=QTabWidget（PSD|柱状）、单有=单图、全无=None.

    feature_table._build_ui 用 None 分支保持空表零观感变化。
    """
    curves = list(getattr(table, "curves", None) or [])
    has_rows = table is not None and not table.df.empty
    if curves and has_rows:
        tabs = QTabWidget()
        tabs.addTab(PsdCurvesChart(curves), S.FEAT_TAB_PSD)
        tabs.addTab(FeatureBarGrid(table), S.FEAT_TAB_BARS)
        return tabs
    if curves:
        return PsdCurvesChart(curves)
    if has_rows:
        return FeatureBarGrid(table)
    return None
