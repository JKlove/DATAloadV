"""事件条：整个录制时程的事件概览 + 总览时间轴滑块（M6.8）.

- 每个事件画一根竖线刻度（scatter symbol "|"），颜色按事件码从调色板循环取
- 顶部文本行显示"事件码×次数"图例（无事件时显示"无事件"）
- **总览滑块**：当前主图视口画成半透明色块（``LinearRegionItem``），可整体
  拖动定位（边缘冻结——一屏时长只在主图侧调）；拖动 → ``viewport_moved(t0,t1)``
- 点击时间轴空白处 → ``clicked_time(float)``，主视图跳转居中到该时刻
- x 轴锁死 [0, duration] 且禁鼠标拖拽（M6.8 前允许拖动会挪走 lane 自己的
  x 轴、autoRange 又随事件范围漂移——用户"时间轴拖动逻辑不清晰"的根源）
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal

from ...core.recording import EventTable
from ..strings_zh import S

# 事件码调色板（顺序固定，保证同码同色；白底主题用色——黄取暗金，浅黄在白底不可辨）
EVENT_PALETTE = [
    "#e05c5c",  # 红
    "#5cb85c",  # 绿
    "#5c9ce0",  # 蓝
    "#e0a85c",  # 橙
    "#b45ce0",  # 紫
    "#5ce0d2",  # 青
    "#b8860b",  # 黄（暗金：旧 #e0e05c 在白底上与背景无法区分，M6 更换）
    "#e05c9e",  # 粉
]


def event_color(code: str, all_codes: list[str]) -> str:
    """事件码 → 稳定颜色（按它在码表中的序号取模调色板）."""
    try:
        idx = all_codes.index(code)
    except ValueError:
        idx = 0
    return EVENT_PALETTE[idx % len(EVENT_PALETTE)]


class EventLane(pg.PlotItem):
    """事件概览条 + 总览时间轴滑块."""

    clicked_time = Signal(float)
    # 用户拖动总览滑块（t0, t1 = 滑块两缘；主图侧只取中心——见 browser 接线）
    viewport_moved = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.showGrid(x=False, y=False)
        self.hideButtons()
        # 全禁鼠标拖拽（M6.8）：旧版 x=True 时用户一拖就挪走 lane 自己的
        # x 轴（setXLink 从未实现过，docstring 旧表述是错的），点击映射失真。
        # 视口滑块的拖动由 LinearRegionItem 自己处理，不依赖 ViewBox。
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        # y 固定 0–1（刻度线画在 0.15–0.85），不显示 y 轴
        self.setYRange(0, 1, padding=0)
        self.getAxis("left").setVisible(False)
        self.getAxis("bottom").setStyle(showValues=False)
        self._scatter: pg.ScatterPlotItem | None = None
        self._legend_item: pg.TextItem | None = None
        self._events = EventTable()
        self._duration = 1.0
        self._click_wired = False
        self._syncing = False  # 程序化 set_viewport 回写期间不外发 viewport_moved
        # 总览滑块：当前视口 [t0,t1] 的半透明色块。LinearRegionItem 拖区域
        # = 两条边界线整体移动（宽度天然保持）；拖边界 = 各自独立——逐线
        # setMovable(False) 冻结边缘即"只平移不改宽"（一屏时长归主图管）。
        # 拖出 [0,duration] 时两线各自被 bounds 钳制、区域瞬时压窄——主图
        # 侧只取中心按自身宽度重锚，失真经回写自愈（值相同则早退不 emit）。
        self._region = pg.LinearRegionItem(
            values=(0.0, 1.0),
            orientation="vertical",
            brush=pg.mkBrush(31, 119, 180, 40),   # SIGNAL_PEN_COLOR 同系半透明
            pen=pg.mkPen("#1f77b4", width=1),
            hoverBrush=pg.mkBrush(31, 119, 180, 70),
        )
        for line in self._region.lines:
            line.setMovable(False)
        self._region.sigRegionChanged.connect(self._on_region_changed)
        self.addItem(self._region)

    def wire_click(self) -> None:
        """挂进 GraphicsLayoutWidget 后调用：绑定 scene 点击事件.

        不能在 __init__ 里连——那时 PlotItem 尚未加入任何 scene，
        ``self.scene()`` 为 None（M1 e2e 实测踩坑）。
        """
        if self._click_wired:
            return
        scene = self.scene()
        if scene is not None:
            scene.sigMouseClicked.connect(self._on_click)
            self._click_wired = True

    # ------------------------------------------------------------ 数据

    def set_events(self, events: EventTable, duration_s: float) -> None:
        """更新事件与总时长（打开/换文件时调用一次）."""
        self._events = events
        self._duration = max(duration_s, 1e-6)
        if self._scatter is not None:
            self.removeItem(self._scatter)
            self._scatter = None
        if self._legend_item is not None:
            self.removeItem(self._legend_item)
            self._legend_item = None

        # 三重锁死 x 轴到 [0, duration]：limits 硬边界 + 显式设范围 + 关
        # autoRange（旧版散点 autoRange 让 x 漂到事件数据范围、无事件文件
        # 又不显示全程——总览轴的刻度基准必须恒定是录制全长）
        vb = self.getViewBox()
        if vb is not None:
            vb.setLimits(xMin=0.0, xMax=self._duration)
            vb.enableAutoRange(x=False, y=False)
        self.setXRange(0.0, self._duration, padding=0)

        codes = sorted(set(events.code)) if len(events) else []
        if not codes:
            self._legend_item = pg.TextItem(
                S.EVENT_LANE_NONE, color="#888888", anchor=(0, 1)
            )
            self.addItem(self._legend_item)
            self._legend_item.setPos(0, 0.98)
            return

        # 图例文本："T0×15  T1×8 …"（放条内左上）
        summary = events.codes_summary()
        legend = pg.TextItem(
            "  ".join(f"{c}×{summary[c]}" for c in codes), color=S.PLOT_TEXT_COLOR, anchor=(0, 1)
        )
        self.addItem(legend)
        legend.setPos(0, 0.98)
        self._legend_item = legend

        # 刻度散点：每码一簇（同色）
        brushes = [pg.mkBrush(event_color(c, codes)) for c in events.code]
        self._scatter = pg.ScatterPlotItem(
            x=events.onset, y=np.full(len(events), 0.5),
            symbol="|", size=16, brush=brushes, pen=None,
        )
        self.addItem(self._scatter)

    # ------------------------------------------------------------ 交互

    def set_viewport(self, t0: float, t1: float) -> None:
        """主图视口回写到总览滑块（程序化，不外发信号防回环）.

        值相同时早退——连 ``setRegion`` 都不调（pyqtgraph 值相同本就不
        emit，这里再省一次属性写）；值不同时 ``_syncing`` 包住 ``setRegion``
        吞掉它触发的 ``sigRegionChanged``。
        """
        if self._syncing:
            return
        r = self._region.getRegion()
        if abs(r[0] - t0) < 1e-9 and abs(r[1] - t1) < 1e-9:
            return
        self._syncing = True
        try:
            self._region.setRegion((t0, t1))
        finally:
            self._syncing = False

    def _on_region_changed(self, *_a) -> None:
        """用户拖动总览滑块 → 通知主图（程序化回写被 _syncing 挡在外面）.

        宽度失真（拖出界被 bounds 压窄）由 browser 侧中心重锚自愈。
        """
        if self._syncing:
            return
        t0, t1 = self._region.getRegion()
        self.viewport_moved.emit(t0, t1)

    def _on_click(self, ev) -> None:
        """点击事件条任意位置 → 发出该处时刻（主视图居中过去）."""
        if not self.sceneBoundingRect().contains(ev.scenePos()):
            return
        vb = self.getViewBox()
        if vb is None:
            return
        pt = vb.mapSceneToView(ev.scenePos())
        t = float(np.clip(pt.x(), 0.0, self._duration))
        self.clicked_time.emit(t)
