"""分段（epochs）预览视图——M3 建立，M8 四视图，M8.1 加单段浏览.

展示内容：
- 概要：分段总数 / 每类事件分段数（QTableWidget）
- 五个视图（下拉切换，数据缓存零重算）：
  1. **各通道平均（堆叠）**：M3 现状——各通道跨段平均波形垂直偏移堆叠；
     通道名行首内嵌（M6 浏览器同款——y 轴刻度放全部通道名在导联多时必挤叠）；
  2. **ERP 蝶形图**：全通道同一坐标叠加（ERP 分析标准形态，通道分色 + 图例）；
  3. **单通道 ERP**：选中通道逐段细线 + **按事件码分色**的平均粗线
     （曲线尾标注事件码——类间差异一眼可辨，BCI 事件锁时分析主力视图）；
  4. **时频图（单通道）**：morlet 小波功率谱段平均热图（基线校正 dB，
     计算在后台线程——``features/tfr.py`` 纯函数，UI 只编排；
     结果按通道缓存，换配色/切走切回零重算；配色 viridis/jet/hot 可切）；
  5. **单段浏览（全通道）**：第 N 段全通道堆叠大图 + 段号框/◀▶/←→ 翻段
     （滑窗分段模式下即"翻页滑动看数据"；M8.1）。

数值计算来自 ctx.epochs（mne 对象）缓存数组；本控件只读展示。
"""

from __future__ import annotations

import logging
from collections import Counter

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...features.tfr import compute_epochs_tfr
from ...proc.context import ProcessingContext
from ...workers.generic import run_in_thread
from ..strings_zh import S
from .event_lane import event_color

logger = logging.getLogger(__name__)

_UV = 1e6
_EP_SEG_PEN_ALPHA = 60  # 单通道视图逐段细线的透明度（0-255）：前景留给平均线

# ------------------------------------------------------------------ 时频配色
# 专有名词不翻。viridis 用 pyqtgraph 内置；jet/hot 无内置文件（get 抛
# FileNotFoundError），用标准公式生成 256×3 **uint8**——pg.ColorMap 收
# 0..1 float 色数组会按 0..255 截断（0.75→0），得到近乎全黑的图且无告警。
_TFR_CMAPS = ("viridis", "jet", "hot")
_CMAP_POS = np.linspace(0.0, 1.0, 256)
_CMAP_CACHE: dict[str, pg.ColorMap] = {}


def _cmap_bytes(name: str) -> np.ndarray:
    """jet/hot 公式 → (256, 3) uint8 查找表."""
    t = np.linspace(0.0, 1.0, 256)
    if name == "hot":
        rgb = np.clip(np.stack([3 * t, 3 * t - 1.0, 3 * t - 2.0]), 0.0, 1.0)
    elif name == "jet":
        rgb = np.clip(np.stack([1.5 - np.abs(4 * t - 3.0),
                                1.5 - np.abs(4 * t - 2.0),
                                1.5 - np.abs(4 * t - 1.0)]), 0.0, 1.0)
    else:
        raise ValueError(f"无公式配色：{name}")
    return np.round(rgb.T * 255.0).astype(np.uint8)


def _tfr_colormap(name: str) -> pg.ColorMap:
    """配色名 → pg.ColorMap（进程级缓存；HistogramLUTItem.gradient 用）."""
    cm = _CMAP_CACHE.get(name)
    if cm is None:
        cm = (pg.colormap.get(name) if name == "viridis"
              else pg.ColorMap(_CMAP_POS, _cmap_bytes(name)))
        _CMAP_CACHE[name] = cm
    return cm


class EpochsPreviewView(QWidget):
    """分段结果预览 tab（持有 ProcessingContext；关闭 tab 即释放）."""

    def __init__(self, ctx: ProcessingContext, source_name: str, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx  # 持有引用＝持有 epochs 内存；teardown() 释放
        self._source_name = source_name
        self._tfr_running = False  # 时频后台计算防重入
        self._lut: pg.HistogramLUTItem | None = None  # 时频色标（仅 TFR 视图挂载）
        self._legend: pg.LegendItem | None = None  # 蝶形图图例（仅蝶形视图显示）
        # 时频结果缓存：通道索引 → (freqs, times, db)。_data 生命周期内不可变，
        # 键安全；命中即同步绘制零重算（换配色/切走切回都靠它）
        self._tfr_cache: dict[int, tuple] = {}

        epochs = ctx.epochs
        # 数据一次取齐缓存（预览数据量 = 段×通道×段长，量级可控），
        # 四视图切换零重算；时频视图只在后台线程里用它
        self._data = epochs.get_data()  # [n_ep, n_ch, n_t]（伏特）
        self._times = np.asarray(epochs.times, dtype=float)
        self._sfreq = float(epochs.info["sfreq"])
        self._ch_names = list(epochs.ch_names)
        id_to_code = {v: k for k, v in epochs.event_id.items()}
        self._codes = [id_to_code[int(c)] for c in epochs.events[:, -1]]
        self._all_codes = sorted(set(self._codes))

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(S.PIPE_EPOCHS_TOTAL.format(n=len(epochs))))

        # 每类分段数表（M3 现状保留）
        counts = Counter(self._codes)
        table = QTableWidget(len(counts), 2)
        table.setHorizontalHeaderLabels([S.COL_EVENTS, S.PIPE_EPOCHS_PER_CODE])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (code, n) in enumerate(sorted(counts.items())):
            table.setItem(row, 0, QTableWidgetItem(str(code)))
            table.setItem(row, 1, QTableWidgetItem(str(n)))
        table.setMaximumHeight(max(90, 30 * len(counts) + 40))
        lay.addWidget(table)

        # 视图切换行（M8）：模式下拉 + 通道选择（单通道/时频视图启用）
        # M8.1 追加：配色下拉（时频）+ 段号框/◀▶（单段浏览）——随视图启停
        bar = QVBoxLayout()
        combo_row = QWidget()
        h = QHBoxLayout(combo_row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel(S.EP_VIEW_LABEL))
        self._view_combo = QComboBox()
        self._view_combo.addItems(
            # 第五项固定在尾部：e2e_m8 按索引 0-3 寻址四视图，不可插位
            [S.EP_VIEW_AVG, S.EP_VIEW_BUTTERFLY, S.EP_VIEW_SINGLE, S.EP_VIEW_TFR,
             S.EP_VIEW_SEGMENT]
        )
        self._view_combo.currentTextChanged.connect(self._on_view_changed)
        h.addWidget(self._view_combo)
        h.addWidget(QLabel(S.EP_LBL_CHANNEL))
        self._ch_combo = QComboBox()
        self._ch_combo.addItems(self._ch_names)
        self._ch_combo.setEnabled(False)  # 默认视图（堆叠）不需要选通道
        self._ch_combo.currentIndexChanged.connect(lambda _i: self._redraw())
        h.addWidget(self._ch_combo)
        h.addWidget(QLabel(S.EP_LBL_CMAP))
        self._cmap_combo = QComboBox()
        self._cmap_combo.addItems(list(_TFR_CMAPS))
        self._cmap_combo.setEnabled(False)  # 仅时频视图启用
        self._cmap_combo.currentTextChanged.connect(self._on_cmap_changed)
        h.addWidget(self._cmap_combo)
        h.addWidget(QLabel(S.EP_LBL_SEGMENT))
        self._seg_spin = QSpinBox()
        self._seg_spin.setRange(1, len(epochs))
        self._seg_spin.setSuffix(f" / {len(epochs)}")
        self._seg_spin.setEnabled(False)  # 仅单段浏览视图启用
        self._seg_spin.valueChanged.connect(lambda _v: self._redraw())
        h.addWidget(self._seg_spin)
        self._btn_prev = QPushButton(S.EP_BTN_SEG_PREV)
        self._btn_next = QPushButton(S.EP_BTN_SEG_NEXT)
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_prev.clicked.connect(lambda: self._nav_segment(-1))
        self._btn_next.clicked.connect(lambda: self._nav_segment(1))
        h.addWidget(self._btn_prev)
        h.addWidget(self._btn_next)
        h.addStretch(1)
        self._hint = QLabel("")  # 视图说明行（如时频计算中）
        bar.addWidget(combo_row)
        bar.addWidget(self._hint)
        lay.addLayout(bar)

        self._gfx = pg.GraphicsLayoutWidget()
        self._plot = self._make_plot()
        self._gfx.addItem(self._plot, 0, 0)
        lay.addWidget(self._gfx, 1)

        # ←/→ 翻段（作用域限本预览控件内——WidgetWithChildrenShortcut，
        # 不与浏览 tab 的键盘导航冲突）
        for key, delta in ((Qt.Key.Key_Left, -1), (Qt.Key.Key_Right, 1)):
            sc = QShortcut(QKeySequence(key), self._gfx)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(lambda d=delta: self._nav_segment(d))

        self._draw_average()

    # ------------------------------------------------------------------ UI 构建

    def _make_plot(self) -> pg.PlotItem:
        p = pg.PlotItem()
        p.showGrid(x=True, y=False, alpha=0.25)
        p.setLabel("bottom", S.LBL_TIME)
        # 波形系视图左轴无刻度（通道身份在行内嵌标签/图例/事件码标注），
        # 仅时频视图恢复自动频率刻度（_draw_tfr 里 setTicks(None)）
        p.getAxis("left").setTicks([])
        return p

    # ------------------------------------------------------------------ 视图分发

    def _on_view_changed(self, _text: str) -> None:
        mode = self._view_combo.currentText()
        self._ch_combo.setEnabled(mode in (S.EP_VIEW_SINGLE, S.EP_VIEW_TFR))
        self._cmap_combo.setEnabled(mode == S.EP_VIEW_TFR)
        seg = mode == S.EP_VIEW_SEGMENT
        self._seg_spin.setEnabled(seg)
        self._btn_prev.setEnabled(seg)
        self._btn_next.setEnabled(seg)
        self._redraw()

    def _redraw(self) -> None:
        """按当前模式重画（清空旧曲线；时频/堆叠留下的轴状态与色标/图例一并复位）."""
        if self._data is None:
            return  # teardown 后的迟到信号
        mode = self._view_combo.currentText()
        self._plot.clear()
        # 上一视图的行刻度统一清（堆叠时代的通道名 ticks 残留到时频视图，
        # 会经 invertY 翻到左上角飘字——M8.2 用户截图证实）
        self._plot.getAxis("left").setTicks([])
        if self._legend is not None:  # 图例仅蝶形视图显示（plot.clear 清条目不清框）
            self._legend.clear()
            self._legend.hide()
        if mode != S.EP_VIEW_TFR:
            self._remove_lut()
            self._plot.invertY(False)  # 时频视图设过 True，不复位会镜像其它视图
            self._plot.getAxis("left").setLabel("")
        if mode == S.EP_VIEW_AVG:
            self._hint.setText("")
            self._draw_average()
        elif mode == S.EP_VIEW_BUTTERFLY:
            self._hint.setText("")
            self._draw_butterfly()
        elif mode == S.EP_VIEW_SINGLE:
            self._hint.setText(S.EP_LEGEND_SINGLE)
            self._draw_single()
        elif mode == S.EP_VIEW_SEGMENT:
            self._draw_segment()
        else:
            self._start_tfr()

    def _remove_lut(self) -> None:
        """摘掉时频色标（挂在 _gfx 侧列，plot.clear() 清不到——须显式移除）."""
        if self._lut is not None:
            self._gfx.removeItem(self._lut)
            self._lut = None

    # ------------------------------------------------------------------ 视图 1/2：堆叠与蝶形

    def _draw_stacked(self, rows_uv: np.ndarray) -> None:
        """垂直偏移堆叠画法（µV；行首内嵌通道名——平均视图与单段视图共用）.

        通道名不走 y 轴刻度（M8.2：25 导联在有限窗高下必挤叠，用户截图证实），
        改 M6 浏览器同款 TextItem 行首内嵌、半透明白底压波形可读。
        预览 tab 比浏览器矮（500px 高下 25 行默认字号的标签盒高≥行距，相邻相触），
        显式 8pt 小字压盒高——浏览器全高窗口不受此限故保持默认字号。
        """
        label_fill = pg.mkBrush(255, 255, 255, 200)
        label_font = QFont()
        label_font.setPointSizeF(8.0)
        spacing = max(float(np.median(np.abs(rows_uv).max(axis=1))) * 3.0, 1e-3)
        for i, name in enumerate(self._ch_names):
            y = rows_uv[i] + i * spacing
            self._plot.plot(self._times, y, pen=pg.mkPen(S.SIGNAL_PEN_COLOR, width=1))
            label = pg.TextItem(name, color=S.PLOT_TEXT_COLOR,
                                anchor=(0, 0.5), fill=label_fill)
            label.setFont(label_font)
            label.setPos(float(self._times[0]), float(i * spacing))  # 行首行基线
            self._plot.addItem(label)
        self._plot.setYRange(-spacing, (len(self._ch_names) + 0.5) * spacing, padding=0)

    def _draw_average(self) -> None:
        """各通道跨段平均波形（µV，垂直偏移堆叠——M3 现状形态）."""
        self._draw_stacked(self._data.mean(axis=0) * _UV)  # [n_ch, n_t]

    def _draw_butterfly(self) -> None:
        """ERP 蝶形图：全通道同一坐标叠加（µV，通道分色 + 图例，零基准线）.

        图例（M8.2）：plot.clear() 清曲线时 LegendItem 条目同被清（0.14 实测），
        但图例框不清——由 _redraw 统一 hide，这里惰性建+逐通道挂条目。
        0.14 图例默认无底框（NoBrush）文字压曲线，且单列 25 条在矮窗口排不到底
        被裁断——半透明白底+灰边框、每列至多 12 行自动分列（≥73 通道封顶 6 列
        接受截断，极端场景）。
        """
        avg = self._data.mean(axis=0) * _UV
        n = len(self._ch_names)
        if self._legend is None:
            self._legend = self._plot.addLegend(labelTextSize="8pt", offset=(10, 10))
            self._legend.setBrush(pg.mkBrush(255, 255, 255, 210))
            self._legend.setPen(pg.mkPen("#bbbbbb"))
        self._legend.clear()
        self._legend.show()
        self._legend.setColumnCount(min((n + 11) // 12, 6))
        for i, name in enumerate(self._ch_names):
            item = self._plot.plot(
                self._times, avg[i],
                pen=pg.mkPen(pg.intColor(i, hues=max(n, 6)), width=1),
            )
            self._legend.addItem(item, name)
        self._plot.addItem(pg.InfiniteLine(pos=0.0, angle=0, pen="#999999"))
        span = max(float(np.abs(avg).max()) * 1.1, 1e-1)
        self._plot.setYRange(-span, span, padding=0)

    # ------------------------------------------------------------------ 视图 3：单通道 ERP

    def _draw_single(self) -> None:
        """选中通道：逐段半透明细线 + 按事件码分色的平均粗线（尾标注码）."""
        ch = max(0, self._ch_combo.currentIndex())
        curves = self._data[:, ch, :] * _UV  # [n_ep, n_t]
        # 逐段细线（灰、半透明——背景纹理）
        for row in curves:
            self._plot.plot(
                self._times, row,
                pen=pg.mkPen((150, 150, 150, _EP_SEG_PEN_ALPHA), width=1),
            )
        # 按事件码分组的平均粗线（前景）
        fill = pg.mkBrush(255, 255, 255, 200)
        for code in self._all_codes:
            sel = [i for i, c in enumerate(self._codes) if c == code]
            if not sel:
                continue
            mean_uv = curves[sel].mean(axis=0)
            color = event_color(code, self._all_codes)
            self._plot.plot(
                self._times, mean_uv, pen=pg.mkPen(color, width=2),
            )
            label = pg.TextItem(str(code), color=S.PLOT_TEXT_COLOR,
                                anchor=(0, 0.5), fill=fill)
            label.setPos(float(self._times[-1]), float(mean_uv[-1]))
            self._plot.addItem(label)
        self._plot.autoRange()

    # ------------------------------------------------------------------ 视图 4：时频图

    # ------------------------------------------------------------------ 视图 5：单段浏览

    def _draw_segment(self) -> None:
        """第 N 段全通道堆叠大图（段号框/◀▶/←→ 翻段；hint 标段号与事件码）."""
        idx = min(max(self._seg_spin.value() - 1, 0), len(self._data) - 1)
        self._draw_stacked(self._data[idx] * _UV)
        self._hint.setText(S.EP_HINT_SEGMENT.format(
            i=idx + 1, n=len(self._data), code=self._codes[idx],
        ))

    def _nav_segment(self, delta: int) -> None:
        """翻段（◀▶/←→）：clamp 到 [1, 段数]；仅单段浏览视图响应."""
        if self._view_combo.currentText() != S.EP_VIEW_SEGMENT or self._data is None:
            return
        self._seg_spin.setValue(self._seg_spin.value() + delta)  # QSpinBox 自带 clamp

    # ------------------------------------------------------------------ 视图 4：时频图

    def _start_tfr(self) -> None:
        """morlet 时频（单通道，段平均）：优先缓存，未命中才进后台线程."""
        if self._tfr_running or self._data is None:
            return
        ch = max(0, self._ch_combo.currentIndex())
        hit = self._tfr_cache.get(ch)
        if hit is not None:
            self._draw_tfr(hit)  # 缓存命中：同步绘制，零线程零重算
            return
        self._tfr_running = True
        self._hint.setText(S.EP_TFR_COMPUTING)
        run_in_thread(
            lambda: compute_epochs_tfr(
                self._data, self._sfreq, self._times, ch_idx=ch,
            ),
            on_done=lambda r: self._on_tfr_done(ch, r),
            on_error=self._on_tfr_error,
        )

    def _on_tfr_done(self, ch: int, result: tuple) -> None:
        """后台时频完成：回填缓存（结果只依赖通道，视图已切走也存）再绘制."""
        if self._data is not None:  # teardown 后不回填
            self._tfr_cache[ch] = result
        self._draw_tfr(result)

    def _draw_tfr(self, result: tuple[np.ndarray, np.ndarray, np.ndarray]) -> None:
        """时频绘制（主线程；缓存命中与后台完成共用此路）：热图 + 色标."""
        self._tfr_running = False
        try:
            # tab 已关闭（teardown 置空）/ 用户已切走视图：丢弃本次结果，
            # 免得热图盖掉刚画好的其它视图
            if self._data is None or self._view_combo.currentText() != S.EP_VIEW_TFR:
                return
            freqs, times, db = result
            self._hint.setText(f"{S.EP_VIEW_TFR} · {S.EP_TFR_UNIT}")
            img = pg.ImageItem()
            # ImageItem 默认 col-major（image[x, y]）：转置成 [n_times, n_freq]
            img.setImage(db.T, autoLevels=True)
            img.setRect(QRectF(
                float(times[0]), float(freqs[0]),
                float(times[-1] - times[0]), float(freqs[-1] - freqs[0]),
            ))
            self._plot.clear()
            self._plot.addItem(img)
            self._plot.invertY(True)  # 低频在下（频率轴惯例）
            self._plot.getAxis("left").setLabel(S.EP_TFR_FREQ_AXIS)
            # 恢复自动频率刻度（_redraw/构造统一 setTicks([]) 无刻度；None=默认刻度系统）
            self._plot.getAxis("left").setTicks(None)
            self._remove_lut()  # 换通道重算时摘旧色标，防同格叠两个
            lut = pg.HistogramLUTItem()
            lut.setImageItem(img)
            # 须在 setImageItem 之后：挂接链会立即应用当前配色；
            # setColorMap 只改查找表不碰 levels（换配色零亮度扰动）
            lut.gradient.setColorMap(_tfr_colormap(self._cmap_combo.currentText()))
            self._gfx.addItem(lut, 0, 1)
            self._lut = lut
            # 复位上一视图残留的 Y 范围（堆叠/蝶形的 setYRange 会关掉
            # autoRange，不重开则热图被压成一条——M8.1 观感修复）
            self._plot.autoRange()
        except RuntimeError:
            pass  # C++ 对象已释放（关 tab 竞态）——静默丢弃本次结果

    def _on_cmap_changed(self, _text: str) -> None:
        """时频配色切换：只重设查找表，不重算不进线程."""
        if self._lut is not None and self._view_combo.currentText() == S.EP_VIEW_TFR:
            self._lut.gradient.setColorMap(_tfr_colormap(self._cmap_combo.currentText()))

    def _on_tfr_error(self, msg: str) -> None:
        self._tfr_running = False
        self._hint.setText(S.EP_TFR_FAIL.format(msg=msg))
        logger.warning("时频计算失败 %s：%s", self._source_name, msg)

    # ------------------------------------------------------------------ 生命周期

    def teardown(self) -> None:
        """关闭 tab 时释放分段数据（主窗口 _on_tab_close 调用；幂等）."""
        if self.ctx is None:
            return  # 已 teardown（e2e 关 tab 与测试 fixture 都可能二调）
        self._data = None  # 后台线程回来据此早退
        self._tfr_cache.clear()  # 缓存引用 _data 派生结果，一并放掉
        self.ctx.epochs = None
        self.ctx = None
