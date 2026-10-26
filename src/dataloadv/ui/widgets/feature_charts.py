"""特征结果图表区（M8.3 建；M14 改）：PSD 曲线 dB/线性轴 + 标量特征箱线网格.

架构规则 #2：UI 不做计算——本模块只做**展示变换与聚合**（PSD 曲线 µV²/Hz →
dB 的纯显示换算、箱线分组取原始值列表），先例 epochs_preview._draw_average；
特征数值本身一律来自 features 层（单位标注来自 features.units.feature_unit）。

三个入口：
- ``PsdCurvesChart``：``FeatureTable.curves`` → dB×线性频率叠加图（M14：原
  双对数改为 **y=dB（10·log10，re 1µV²/Hz）/ x=线性 Hz**，刻度一律普通数字）
- ``FeatureBarGrid``：``FeatureTable.df`` 长表 → 每特征一格的**箱线图网格**
  （M14：原按事件码求均值的柱状改为分箱——每事件码一个箱：中位线/四分位箱/
  1.5×IQR 须/离群点；**每特征一色**（格内系列同色相不同透明度）；纵轴标注
  特征单位）。每特征一格天然解决时域 8 统计量量纲不同的问题
- ``make_charts_area``：按 table 内容组装（双有=QTabWidget、单有=单图、
  全无=None——空表零观感变化）
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...batch.results import FeatureTable
from ...features.units import feature_unit
from ..strings_zh import S

# 截断上限：超限只画前 N 条/项并出提示（45 文件×22 通道=990 条曲线的
# 批处理场景，全画既卡也看不清）
MAX_CURVES = 60
MAX_FEATURES = 24
MAX_SERIES = 12
_GRID_COLS = 3  # 箱线网格每行格数


def _to_db(psd) -> np.ndarray:
    """PSD（µV²/Hz）→ dB（10·log10，re 1µV²/Hz）——纯显示换算.

    下限 1e-40 防 log(0)（tfr._db_peak_normalized 同款口径，无归一化）。
    """
    return 10.0 * np.log10(np.maximum(np.asarray(psd, dtype=float), 1e-40))


class _PlainAxis(pg.AxisItem):
    """刻度一律普通数字（``f"{v:g}"``）——杜绝 10⁻⁵/1e+05 科学计数样式.

    pg 默认：log 轴 logTickStrings 出 Unicode 上标指数、线性轴在
    |v|≥10000 或 ≤0.001 时走 %g 科学计数——覆写 tickStrings 强制普通
    小数（pg docstring 明示可覆写；2026-10-15 用户要求）。
    """

    def tickStrings(self, values, scale, spacing):
        return [f"{v:g}" for v in values]


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
    """PSD 曲线叠加图（M14：y=dB / x=线性 Hz / 普通数字刻度）.

    :param curves: FeatureTable.curves——每条含 recording/channel/window/
      freqs/psd（µV²/Hz）；freqs/psd 为空的条目跳过。y 数据经 _to_db 换算
      （显示变换，µV²/Hz 数值本身不改）。
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

        self._plot = pg.PlotItem(axisItems={
            "left": _PlainAxis(orientation="left"),
            "bottom": _PlainAxis(orientation="bottom"),
        })
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setLabel("bottom", S.PIPE_PSD_AXIS_X)
        self._plot.setLabel("left", S.PIPE_PSD_AXIS_Y_DB)
        gfx = pg.GraphicsLayoutWidget()
        gfx.addItem(self._plot, 0, 0)
        lay.addWidget(gfx, 1)

        if not shown:
            return
        legend = _make_legend(self._plot, self.n_curves)
        for i, c in enumerate(shown):
            freqs = np.asarray(c["freqs"], dtype=float)
            psd = np.asarray(c["psd"], dtype=float)
            mask = psd > 0  # 非正值无 dB 意义
            label = f"{c.get('channel', '')}{c.get('window', '')}"
            if multi_rec:
                label = f"{c.get('recording', '')} · {label}"
            item = self._plot.plot(
                freqs[mask], _to_db(psd[mask]),
                pen=pg.mkPen(pg.intColor(i, hues=max(self.n_curves, 6)), width=1),
            )
            legend.addItem(item, label)


class FeatureBarGrid(QWidget):
    """标量特征网格（类名承 M8.3 柱状，M14 起默认箱线）：每特征一格，x=通道，纵轴标注单位.

    两种展示形式（顶部下拉切换，2026-10-15 用户要求柱状回归）：
    - **箱线图**（默认）：按事件码分箱展示**全部段的原始值**（中位线/四分位箱/
      1.5×IQR 须/离群点）——分布形态保真；
    - **柱状图**：按事件码求**均值**柱（M8.3 原口径——类间比较的 BCI 常态；
      均值由 groups 值列表派生，不重复 groupby）。
    两模式**颜色同规**：每特征一色（intColor(特征序)），格内系列同色相不同
    透明度；纵轴 label=feature_unit(特征名)（无量纲则不设）。

    分组规则（hint 与 docstring 同口径）：系列=事件码（多录制=「录制 · 码」），
    纯 raw 行系列=录制名。构造期同步分组（80k 行 groupby 毫秒级）；结果存
    ``self.groups``（(特征, 系列, 通道) → 值列表，测试数值断言不解析像素）。
    """

    def __init__(self, table: FeatureTable, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        df = table.df
        multi_rec = df["recording"].nunique() > 1
        has_epochs = bool(df["epoch_index"].notna().any())

        # 展示分组：原始值列表（dropna=False 让文件级行保留成组）
        grouped = (
            df.groupby(["recording", "event_code", "channel", "feature"],
                       dropna=False, sort=False, observed=True)["value"]
            .apply(list).reset_index()
        )

        def _series_of(rec: str, code) -> str:
            if pd.notna(code):
                return f"{rec} · {code}" if multi_rec else str(code)
            return str(rec)

        grouped["series"] = [
            _series_of(r, c) for r, c in zip(grouped["recording"], grouped["event_code"])
        ]
        # (特征, 系列, 通道) → 值列表：画格时 O(1) 取数（测试同接口）；柱状
        # 模式的均值也由此派生（不重复 groupby）。**NaN 滤除**（2026-10-15
        # 闪退根因：常数序列的 kurtosis 等特征产 NaN，pg 的 IQR 须函数
        # np.max(data[data<=upper]) 遇 NaN 组得空数组抛 ValueError——滚动
        # 重绘 dataBounds 时整应用崩溃；此处在数据入口滤净）
        self.groups = {}
        for f, s, ch, vals in zip(grouped["feature"].astype(str),
                                  grouped["series"],
                                  grouped["channel"].astype(str),
                                  grouped["value"]):
            clean = [float(v) for v in vals if v == v]  # v==v 滤 NaN（快于 isnan）
            if clean:
                self.groups[(f, s, ch)] = clean
        self.has_epochs = has_epochs

        channels = list(dict.fromkeys(grouped["channel"].astype(str)))
        features_all = list(dict.fromkeys(grouped["feature"].astype(str)))
        series_all = list(dict.fromkeys(grouped["series"]))
        shown_features = features_all[:MAX_FEATURES]
        shown_series = series_all[:MAX_SERIES]
        self.feature_names = shown_features
        self.series_names = shown_series

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # 顶部行：提示 + 展示形式切换（箱线/柱状，2026-10-15 用户要求柱状回归）
        top = QHBoxLayout()
        if has_epochs:
            top.addWidget(QLabel(S.FEAT_CHART_EP_AGG), 1)
        self._view_combo = QComboBox()
        self._view_combo.addItem(S.FEAT_CHART_VIEW_BOX)
        self._view_combo.addItem(S.FEAT_CHART_VIEW_BAR)
        self._view_combo.currentIndexChanged.connect(self._on_view_changed)
        top.addWidget(self._view_combo)
        lay.addLayout(top)
        if len(series_all) > len(shown_series):
            lay.addWidget(QLabel(S.FEAT_CHART_SERIES_TRUNC.format(
                total=len(series_all), n=len(shown_series))))
        if len(features_all) > len(shown_features):
            lay.addWidget(QLabel(S.FEAT_CHART_FEATURE_TRUNC.format(
                total=len(features_all), n=len(shown_features))))

        self._channels = channels
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        lay.addWidget(self._scroll, 1)
        self._build_gfx("box")  # 默认箱线

    # ------------------------------------------------------------------ 网格构建
    def _build_gfx(self, mode: str) -> None:
        """按展示形式重建网格（box=箱线：原始值分布；bar=柱状：均值柱）.

        颜色两模式同规：每特征一色，格内系列同色相透明度梯度。
        """
        channels = self._channels
        shown_features = self.feature_names
        shown_series = self.series_names
        n_ch, n_ser = len(channels), len(shown_series)
        # 槽位制（2026-10-15 四次反馈定稿）：每个（通道×系列）独占一个宽 1.0
        # 的 x 槽位——系列间/通道间都有恒定 45% 槽距空隙，杜绝任何并排贴合
        # （组内均分制在多系列时系列间隙只有百分之几通道距，视觉上恒贴合）；
        # 柱状模式同槽位、柱宽恢复 0.9 槽（用户要求）
        _BOX_W = 0.55   # 箱宽（槽距单位）
        _BAR_W = 0.9    # 柱宽（槽距单位）
        gfx = pg.GraphicsLayoutWidget()
        for i, fname in enumerate(shown_features):
            plot = gfx.addPlot(i // _GRID_COLS, i % _GRID_COLS, title=fname)
            plot.showGrid(x=True, y=True, alpha=0.25)
            unit = feature_unit(fname)
            if unit:
                plot.setLabel("left", unit)  # 纵轴单位标注（无量纲不设）
            # 每特征一色（M14：原系列 intColor 跨格同色 → 特征专属色）；
            # 格内系列用同色相不同透明度区分
            base = pg.intColor(i, hues=max(len(shown_features), 6))
            for k, sname in enumerate(shown_series):
                vals = [self.groups.get((fname, sname, ch)) for ch in channels]
                m = [j for j, v in enumerate(vals) if v]
                if not m:
                    continue
                alpha = 0.35 + 0.4 * k / max(n_ser - 1, 1) if n_ser > 1 else 0.6
                # 槽位坐标：通道 j 的第 k 系列在 x = j*n_ser + k（整数槽位）
                xs = np.arange(n_ch) * n_ser + k
                if mode == "box":
                    # outlier=False：离群点改由下方 jitter 散点统一展示（全量
                    # 数据点分布，2026-10-15 用户要求的参考样式——避免与
                    # BoxplotItem 自身的离群符号重复）
                    plot.addItem(pg.BoxplotItem(
                        loc=xs[m], data=[vals[j] for j in m], width=_BOX_W,
                        pen=pg.mkPen(base.darker(150), width=1),
                        brush=pg.mkBrush(base, alpha=alpha),
                        medianPen=pg.mkPen("#333333", width=1),
                        outlier=False,
                    ))
                    # 实际数据点分布：全量值 jitter 散点。抖动幅度收在**箱体
                    # 内侧 80%**（±0.8×箱半宽——2026-10-15 三次反馈：原 ±40% 组距
                    # 超出箱缘，相邻系列的散点云把系列间空隙填满=视觉上箱仍
                    # "连在一起"；柱状无散点所以早一步显出间隔）。深灰小点半透明
                    rng = np.random.default_rng(0)  # 固定种子：同数据同抖动（可复现）
                    half = 0.75 * _BOX_W / 2.0  # 箱半宽的 75%（不越箱缘）
                    pts_x: list[np.ndarray] = []
                    pts_y: list[np.ndarray] = []
                    for j in m:
                        v = np.asarray(vals[j], dtype=float)
                        pts_x.append(xs[j] + rng.uniform(-half, half, size=len(v)))
                        pts_y.append(v)
                    if pts_x:
                        plot.addItem(pg.ScatterPlotItem(
                            x=np.concatenate(pts_x), y=np.concatenate(pts_y),
                            size=3, pen=None,
                            brush=pg.mkBrush(60, 60, 60, 130),
                        ))
                else:
                    # 柱状=均值（M8.3 原口径；均值由 groups 值列表派生）
                    hs = [float(np.mean(vals[j])) for j in m]
                    plot.addItem(pg.BarGraphItem(
                        x=xs[m], height=hs, width=_BAR_W,
                        brush=pg.mkBrush(base, alpha=alpha), pen=None,
                    ))
            # x 轴通道名：刻度放各通道系列的槽位组中心；>12 个时隔名标注
            step = 1 if n_ch <= 12 else 2
            centers = [j * n_ser + (n_ser - 1) / 2.0 for j in range(n_ch)]
            plot.getAxis("bottom").setTicks(
                [[(c, ch) for c, ch in zip(centers, channels) if i % step == 0]]
            )
            if i == 0 and n_ser > 1:
                # 系列图例只挂第一格（色块=该特征基色的透明度梯度）
                legend = _make_legend(plot, n_ser)
                base0 = pg.intColor(0, hues=max(len(shown_features), 6))
                for k, sname in enumerate(shown_series):
                    alpha = 0.35 + 0.4 * k / max(n_ser - 1, 1)
                    dummy = pg.PlotDataItem(
                        pen=None, symbol="s", symbolSize=10,
                        symbolBrush=pg.mkBrush(base0, alpha=alpha),
                    )
                    legend.addItem(dummy, sname)

        # 多行内容超出视口 → 滚动（每格固定 ~240px 行高）
        gfx.setMinimumHeight(math.ceil(len(shown_features) / _GRID_COLS) * 240)
        old = self._scroll.widget()
        if old is not None:
            old.deleteLater()
        self._scroll.setWidget(gfx)

    def _on_view_changed(self, index: int) -> None:
        """下拉切换展示形式：重建网格（索引 0=箱线、1=柱状）."""
        self._build_gfx("box" if index == 0 else "bar")


def make_charts_area(table: FeatureTable) -> QWidget | None:
    """按 table 内容组装图表区：双有=QTabWidget（PSD|特征网格）、单有=单图、全无=None.

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
