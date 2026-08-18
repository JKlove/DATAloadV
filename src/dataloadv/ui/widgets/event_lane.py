"""事件条：整个录制时程的事件概览 + 点击导航.

- 每个事件画一根竖线刻度（scatter symbol "|"），颜色按事件码从调色板循环取
- 顶部文本行显示"事件码×次数"图例（无事件时显示"无事件"）
- 点击事件条 → 发 ``clicked_time(float)``，主视图跳转居中到该时刻
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
    """事件概览条（x 轴与主视图联动由外部 setXLink 完成）."""

    clicked_time = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.showGrid(x=False, y=False)
        self.hideButtons()
        self.setMouseEnabled(x=True, y=False)  # 只允许横向拖动概览
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

        codes = sorted(set(events.code)) if len(events) else []
        if not codes:
            self._legend_item = pg.TextItem("无事件", color="#888888", anchor=(0, 1))
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
