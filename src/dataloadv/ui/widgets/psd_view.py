"""PSD 对比视图：原始 vs 处理后的功率谱叠加（M14：y=dB / x=线性 Hz）.

数值计算在 ``features/spectral.mean_welch``（UI 不做计算，架构规则 #2）；
本控件只负责展示：每条曲线一个标签/颜色，**y 轴 dB（10·log10，re 1µV²/
Hz）/ x 轴线性频率 / 刻度一律普通数字**（2026-10-15 用户要求：原双对数
轴出现 10⁻⁵/1e-5 科学计数样式且频率轴不均一）。
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..strings_zh import S
from .feature_charts import _PlainAxis, _to_db

logger = logging.getLogger(__name__)

# 曲线配色（白底高对比；第一条=原始=红，第二条=处理后=蓝——M6 换浅色主题时
# 首色由近白 #e8e8e8 更换，否则白底上完全不可见）
_SERIES_COLORS = ("#d62728", "#1f77b4", "#2ca02c", "#9467bd")


class PsdView(QWidget):
    """多曲线 PSD 对比小窗（作为独立顶层窗口或嵌入均可）."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.PIPE_PSD_TITLE)
        self.resize(760, 480)
        self._plot = pg.PlotItem(axisItems={
            "left": _PlainAxis(orientation="left"),
            "bottom": _PlainAxis(orientation="bottom"),
        })
        self._plot.showGrid(x=True, y=True, alpha=0.25)
        self._plot.setLabel("bottom", S.PIPE_PSD_AXIS_X)
        self._plot.setLabel("left", S.PIPE_PSD_AXIS_Y_DB)
        self._plot.addLegend(offset=(12, 12))
        gfx = pg.GraphicsLayoutWidget()
        gfx.addItem(self._plot, 0, 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(gfx)
        self._curves: list[pg.PlotDataItem] = []

    def set_series(self, series: list[tuple[str, np.ndarray, np.ndarray]]) -> None:
        """替换全部曲线.

        :param series: [(标签, freqs, psd µV²/Hz), ...]；psd≤0 的点丢弃
            （无 dB 意义）；y 数据经 _to_db 显示换算（µV²/Hz 数值不改）。
        """
        for c in self._curves:
            self._plot.removeItem(c)
        self._curves = []
        for i, (label, freqs, psd) in enumerate(series):
            if freqs is None or psd is None or len(freqs) == 0:
                continue
            mask = psd > 0
            color = _SERIES_COLORS[i % len(_SERIES_COLORS)]
            curve = self._plot.plot(
                freqs[mask], _to_db(psd[mask]),
                pen=pg.mkPen(color, width=2), name=label,
            )
            self._curves.append(curve)
