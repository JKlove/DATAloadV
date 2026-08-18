"""分段（epochs）预览视图——M3 分段步骤后的预览 tab.

展示内容：
- 概要：分段总数 / 每类事件分段数（QTableWidget）
- 各通道跨段平均波形（µV，垂直偏移堆叠，与浏览器同风格）

数值计算全部来自 ctx.epochs（mne 对象），本控件只读展示。
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...proc.context import ProcessingContext
from ..strings_zh import S

logger = logging.getLogger(__name__)

_UV = 1e6


class EpochsPreviewView(QWidget):
    """分段结果预览 tab（持有 ProcessingContext；关闭 tab 即释放）."""

    def __init__(self, ctx: ProcessingContext, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx  # 持有引用＝持有 epochs 内存；teardown() 释放
        self._source_name = source_name

        epochs = ctx.epochs
        id_to_code = {v: k for k, v in epochs.event_id.items()}
        counts = Counter(id_to_code[int(c)] for c in epochs.events[:, -1])

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(S.PIPE_EPOCHS_TOTAL.format(n=len(epochs))))

        # 每类分段数表
        table = QTableWidget(len(counts), 2)
        table.setHorizontalHeaderLabels([S.COL_EVENTS, S.PIPE_EPOCHS_PER_CODE])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (code, n) in enumerate(sorted(counts.items())):
            table.setItem(row, 0, QTableWidgetItem(str(code)))
            table.setItem(row, 1, QTableWidgetItem(str(n)))
        table.setMaximumHeight(max(90, 30 * len(counts) + 40))
        lay.addWidget(table)

        lay.addWidget(QLabel(S.PIPE_EPOCHS_AVG_PLOT))
        plot = pg.PlotItem()
        plot.showGrid(x=True, y=False, alpha=0.25)
        plot.setLabel("bottom", S.LBL_TIME)
        gfx = pg.GraphicsLayoutWidget()
        gfx.addItem(plot, 0, 0)
        lay.addWidget(gfx, 1)
        self._draw_average(plot, epochs)

    @staticmethod
    def _draw_average(plot: pg.PlotItem, epochs) -> None:
        """各通道跨段平均波形（µV，垂直偏移堆叠）."""
        data = epochs.get_data()  # [n_epochs, n_ch, n_times]（伏特）
        avg = data.mean(axis=0) * _UV
        times = epochs.times
        ticks = []
        spacing = max(float(np.median(np.abs(avg).max(axis=1))) * 3.0, 1e-3)
        for i, name in enumerate(epochs.ch_names):
            plot.plot(times, avg[i] + i * spacing, pen=pg.mkPen("#7fbfff", width=1))
            ticks.append((float(i), name))
        plot.getAxis("left").setTicks([ticks])
        plot.setYRange(-spacing, (len(ticks) + 0.5) * spacing, padding=0)

    def teardown(self) -> None:
        """关闭 tab 时释放分段数据（主窗口 _on_tab_close 调用）."""
        self.ctx.epochs = None
        self.ctx = None
