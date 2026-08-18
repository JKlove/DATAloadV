"""信号浏览器：多通道波形浏览 tab（性能关键路径）.

绘制策略（为什么这样快）：
1. **窗口化读取**：视口变化（30ms 防抖）→ 只读可见 [t0,t1) 的数据
   （``Recording.get_window``，LAZY 大文件也只读这一段）
2. **峰值抽取**：每像素约 2 对 min/max 点，用 ``connect="pairs"`` 画包络
   ——无混叠伪影，点数与数据总量无关（134MB 文件与 1MB 文件同速）
3. 通道垂直堆叠：每通道一条曲线 + 固定 y 偏移；通道名画在曲线行左端
   **内侧**（M6 重构，替代旧的 y 轴刻度——任意导联数都不重叠、不截断）

交互（M6 重构，用户实测反馈驱动）：
- **滚轮 = 平移**时间轴（y 轴锁定，通道行不再被滚轮压挤重叠）；
  **Ctrl+滚轮** = 以鼠标位置为锚点缩放一屏时长；右键拖框 = 框选缩放
- 键盘 ←/→ = 上一/下一屏、Home/End = 最前/最后一屏、↑/↓ = 增益 ±1 档
  （点一下图区获取焦点；通道列表/时长框/滑杆聚焦时按键归控件原生行为）
- 工具栏：|◀ 最前 / ◀ 上一屏 / 一屏时长下拉（可输入自定义秒）/ 下一屏 ▶ / 最末 ▶|
- 右上角**幅值标尺**：竖线像素长度固定，标注换算回真实 µV（随增益动态更新）
- 事件跳转、增益滑杆、通道显隐、右键坏道标记沿用旧版
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core.recording import LoadPolicy, Recording
from ..strings_zh import S
from .event_lane import EventLane, event_color

logger = logging.getLogger(__name__)

# 防抖毫秒数：拖动/缩放时避免每个中间视口都触发读盘
_REFRESH_DEBOUNCE_MS = 30
# 每像素目标样本对数（min/max 各一），>1 时相邻桶之间留缝更接近传统示波器观感
_SAMPLES_PER_PIXEL = 2
# 初始显示窗口秒数（整个录制更短则全显）
_INITIAL_VIEW_S = 10.0
# 通道间距的稳健估计：振幅 = 全通道 MAD 的倍数（对尖峰/坏道不敏感）
_SPACING_MAD_SCALE = 8.0
_UV = 1e6  # 伏特 → 微伏
# 翻屏步进占一屏的比例（留 10% 上下文，避免信号被硬切断跟丢）
_PAGE_STEP = 0.9
# 滚轮平移步长占一屏的比例
_WHEEL_STEP_FRAC = 0.1
# Ctrl+滚轮每档缩放系数（×1.25 / ÷1.25，与常见看图工具一致）
_WHEEL_ZOOM_PER_NOTCH = 1.25
# 幅值标尺的像素长度（固定像素 → 换算回数据坐标，与增益解耦）
_SCALE_BAR_PX = 60.0


def minmax_decimate(times: np.ndarray, values: np.ndarray, max_points: int):
    """把 (times, values) 峰值抽取到 ≤ max_points 个点.

    返回 (out_t, out_v)：逐桶 (min,max) 交错对，配合 ``connect="pairs"``
    绘制成包络。输入短于 max_points 时原样返回。
    """
    n = len(times)
    if n <= max_points or n == 0:
        return times, values
    m = max(1, n // (max_points // 2))
    usable = (n // m) * m
    t = times[:usable].reshape(-1, m)
    v = values[:usable].reshape(-1, m)
    rows = np.arange(t.shape[0])
    i_min = v.argmin(axis=1)
    i_max = v.argmax(axis=1)
    t_min, v_min = t[rows, i_min], v[rows, i_min]
    t_max, v_max = t[rows, i_max], t[rows, i_max]
    # 保证每对内两点按时间序（包络竖线方向一致）
    swap = t_min > t_max
    out_t = np.empty(2 * t.shape[0])
    out_v = np.empty_like(out_t)
    out_t[0::2] = np.where(swap, t_max, t_min)
    out_v[0::2] = np.where(swap, v_max, v_min)
    out_t[1::2] = np.where(swap, t_min, t_max)
    out_v[1::2] = np.where(swap, v_min, v_max)
    return out_t, out_v


def _nice_number(v: float) -> float:
    """取 v 邻近的 1/2/5×10^k 漂亮数（幅值标尺长度换算用）.

    恒等式（测试依赖）：``_nice_number(v/10) == _nice_number(v)/10``——
    因为 1/2/5 阶梯乘除 10 只挪指数，尾数取值不变。
    """
    if not (v > 0) or not math.isfinite(v):
        return 1.0
    e = math.floor(math.log10(v))
    frac = v / 10.0**e
    for m in (1.0, 2.0, 5.0):
        if frac <= m * 1.000001:
            return m * 10.0**e
    return 10.0 ** (e + 1)


class _PanViewBox(pg.ViewBox):
    """滚轮平移的 ViewBox：竖滚=时间平移，Ctrl+滚轮=锚点缩放，y 轴锁定.

    pyqtgraph 默认滚轮同时缩放 x/y——y 被滚几下后通道行挤成一团
    （用户实测反馈的"通道名重叠"根因之一）。本类接管滚轮：y 轴用
    ``setMouseEnabled(x=True, y=False)`` 锁死，滚轮只动 x。
    """

    def __init__(self, browser: "SignalBrowserView") -> None:
        super().__init__()
        self._browser = browser  # 平移/缩放统一走浏览器的 clamp 出口

    def wheelEvent(self, ev, axis=None) -> None:  # noqa: N802 - Qt 命名
        if ev.delta() == 0:
            return
        t0, t1 = self.viewRange()[0]
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+滚轮：以鼠标下方时刻为锚点缩放（锚点在屏幕上不动）
            factor = (1.0 / _WHEEL_ZOOM_PER_NOTCH) if ev.delta() > 0 else _WHEEL_ZOOM_PER_NOTCH
            try:
                ta = float(self.mapSceneToView(ev.scenePos()).x())
            except Exception:  # noqa: BLE001 - scene 未就绪时退回视口中心
                ta = (t0 + t1) / 2
            self._browser._set_x_range(ta - (ta - t0) * factor, ta + (t1 - ta) * factor)
        else:
            # 竖滚 = 平移：向上滚（delta>0）看更早，步长一屏的 10%
            step = (t1 - t0) * _WHEEL_STEP_FRAC * (-1 if ev.delta() > 0 else 1)
            self._browser._set_x_range(t0 + step, t1 + step)
        ev.accept()


class SignalBrowserView(QWidget):
    """一条录制的浏览 tab 内容.

    :param recording: 已就绪的 Recording（数据未加载也可——首帧异步 ensure_raw）
    :param on_loaded: 数据就绪回调（主窗口用来解除"打开中"状态）
    """

    gain_changed = Signal(float)
    bads_changed = Signal(list)  # 坏道标记变化（携带通道名列表；管线面板联动）

    def __init__(self, recording: Recording, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.rec = recording
        # 每通道 {idx, name, curve, label, enabled}；label = 行内嵌通道名标签
        self._channels: list[dict] = []
        self._spacing_uv = 100.0  # 通道间距（µV），首帧数据到来后自动估计
        self._gain = 0.0  # 滑杆刻度值（增益=10^(x/10)）；初值 0 = 1.0×。
        # （M6 修复：旧值 1.0 让首帧一直带 10^0.1≈1.26× 的隐形增益——
        #   滑杆初始就是 0，字段却初始化成 1.0，从 M1 潜伏至今）
        self._event_lines: list[pg.InfiniteLine] = []
        self._loaded_once = False
        # 坏道标记（raw 未加载时先记在这里，加载后一次性写入 info["bads"]）
        self._bad_names: set[str] = set()
        self._combo_lock = False  # 时长框程序化回写时不触发用户处理逻辑

        self._build_ui()
        self._populate_channels()

        # 首帧数据（含 ensure_raw）在后台线程，避免大文件头读取卡 UI
        from ...workers.generic import run_in_thread

        run_in_thread(
            lambda: self.rec.ensure_raw(self.rec.recommended_policy()),
            on_done=self._on_raw_ready,
            on_error=lambda m: logger.error("加载数据失败 %s：%s", self.rec.meta.filename, m),
        )

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        # 工具条：翻屏导航 + 一屏时长（M6）｜ 时间 + 事件跳转 + 增益（旧版沿用）
        bar = QHBoxLayout()
        self._btn_first = QPushButton(S.BTN_GO_FIRST)
        self._btn_prev_page = QPushButton(S.BTN_PREV_PAGE)
        self._btn_next_page = QPushButton(S.BTN_NEXT_PAGE)
        self._btn_last = QPushButton(S.BTN_GO_LAST)
        self._btn_first.clicked.connect(lambda: self._go_edge(first=True))
        self._btn_prev_page.clicked.connect(lambda: self._page(-1))
        self._btn_next_page.clicked.connect(lambda: self._page(+1))
        self._btn_last.clicked.connect(lambda: self._go_edge(first=False))

        win_lbl = QLabel(S.LBL_WINDOW_S)
        self._window_combo = QComboBox()
        self._window_combo.setEditable(True)  # 预设之外可直接输入秒数
        self._window_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._window_combo.addItems(list(S.WINDOW_PRESETS))
        self._window_combo.setCurrentText(f"{_INITIAL_VIEW_S:g}")
        self._window_combo.setMaximumWidth(72)
        self._window_combo.currentTextChanged.connect(self._on_window_changed)

        self._lbl_time = QLabel(S.BROWSER_NO_DATA)
        self._btn_prev = QPushButton(S.BTN_PREV_EVENT)
        self._btn_next = QPushButton(S.BTN_NEXT_EVENT)
        # 「◀ 上一事件」= 时间更早（direction=-1）；「下一事件 ▶」= 更晚（+1）。
        # 曾长期接反（prev→+1/next→-1），写使用手册盘点 UI 时发现于 2026-08-18 修正。
        self._btn_prev.clicked.connect(lambda: self._jump_event(-1))
        self._btn_next.clicked.connect(lambda: self._jump_event(+1))
        gain_lbl = QLabel(S.LBL_GAIN)
        self._gain_slider = QSlider(Qt.Orientation.Horizontal)
        self._gain_slider.setRange(-20, 20)  # 10^(x/10)：0.1× – 10×，指数刻度
        self._gain_slider.setValue(0)
        self._gain_slider.valueChanged.connect(self._on_gain)
        self._gain_slider.setMaximumWidth(160)
        for w in (
            self._btn_first, self._btn_prev_page, self._btn_next_page, self._btn_last,
            win_lbl, self._window_combo,
        ):
            bar.addWidget(w)
        bar.addStretch(1)
        for w in (self._lbl_time, self._btn_prev, self._btn_next, gain_lbl, self._gain_slider):
            bar.addWidget(w)

        # 通道列表（左）：勾选显隐 + 右键标记坏道（M3 与 BadChannelsStep 联动）
        self._ch_list = QListWidget()
        self._ch_list.setMaximumWidth(150)
        self._ch_list.itemChanged.connect(self._on_channel_toggle)
        self._ch_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ch_list.customContextMenuRequested.connect(self._on_channel_context)

        # 图形区：主图 + 事件条
        self._gfx = pg.GraphicsLayoutWidget()
        self._plot = self._plot_item()
        self._gfx.addItem(self._plot, 0, 0)
        self._lane = EventLane()
        self._gfx.addItem(self._lane, 1, 0)
        self._lane.wire_click()  # 进 scene 后才能绑点击（见 EventLane.wire_click）
        self._lane.clicked_time.connect(self._center_at)
        # 行高：主图占 5，事件条占 1
        self._gfx.ci.layout.setRowStretchFactor(0, 5)
        self._gfx.ci.layout.setRowStretchFactor(1, 1)

        # 键盘导航需要焦点：点击图区 → 焦点代理到本控件 → keyPressEvent 生效
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._gfx.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._gfx.setFocusProxy(self)

        center = QHBoxLayout()
        center.addWidget(self._ch_list)
        center.addWidget(self._gfx, 1)

        root = QVBoxLayout(self)
        root.addLayout(bar)
        root.addLayout(center, 1)

    def _plot_item(self) -> pg.PlotItem:
        """主图配置：时间轴秒、滚轮平移 ViewBox、y 轴锁定."""
        p = pg.PlotItem(viewBox=_PanViewBox(self))
        p.showGrid(x=True, y=False, alpha=0.25)
        p.setLabel("bottom", S.LBL_TIME)
        p.setDownsampling(auto=True, mode="peak")  # 双保险（我们已自抽峰值）
        p.setClipToView(True)
        # y 锁定：通道行高只由间距估计决定，滚轮/拖动不再压缩通道
        p.getViewBox().setMouseEnabled(x=True, y=False)
        return p

    def _populate_channels(self) -> None:
        """按 meta 通道表建曲线/行内标签/列表项（数据未到也先建，首帧统一填数）."""
        names = self.rec.meta.channel_names
        label_fill = pg.mkBrush(255, 255, 255, 200)  # 半透明白底：压在波形上也读得清
        for i, name in enumerate(names):
            curve = pg.PlotCurveItem(pen=pg.mkPen(S.SIGNAL_PEN_COLOR, width=1))
            self._plot.addItem(curve)
            label = pg.TextItem(
                name, color=S.PLOT_TEXT_COLOR, anchor=(0, 0.5), fill=label_fill
            )
            self._plot.addItem(label)
            self._channels.append(
                {"idx": i, "name": name, "curve": curve, "label": label, "enabled": True}
            )
            label.setPos(0.0, i * self._spacing_uv)  # 先放个初值，首帧刷新对齐
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._ch_list.addItem(item)
        # M6：通道名不再走 y 轴刻度（全量 setTicks 在导联多时必然挤叠/截断）
        self._plot.getAxis("left").setVisible(False)

        # 幅值标尺（右上角竖线 + µV 标注；首帧数据后按视口高度换算）
        self._scale_line = pg.PlotCurveItem(pen=pg.mkPen("#666666", width=2))
        self._plot.addItem(self._scale_line)
        self._scale_text = pg.TextItem(
            "", color=S.PLOT_TEXT_COLOR, anchor=(1, 0.5), fill=label_fill
        )
        self._plot.addItem(self._scale_text)

        # 初始视图与 y 范围（间距首帧后修正）
        dur = self.rec.meta.duration_s
        self._plot.setXRange(0, min(_INITIAL_VIEW_S, dur), padding=0)
        n = max(len(names), 1)
        self._plot.setYRange(-1.5 * self._spacing_uv, (n + 0.5) * self._spacing_uv, padding=0)
        self._lane.set_events(self.rec.events, dur)

    # ------------------------------------------------------------------ 数据流

    def _on_raw_ready(self, _raw) -> None:
        """后台 ensure_raw 完成后（主线程）：绑定视口事件并画第一帧."""
        self._loaded_once = True
        if self._bad_names and self.rec.raw is not None:
            self.rec.raw.info["bads"] = self.current_bads()  # 加载前的标记补写
        vb = self._plot.getViewBox()
        vb.sigRangeChanged.connect(self._schedule_refresh)
        self._refresh_data()

    def _schedule_refresh(self, *_a) -> None:
        """视口变化 → 防抖后刷新（拖动过程只在停顿时真正读数）."""
        QTimer.singleShot(_REFRESH_DEBOUNCE_MS, self._refresh_data)

    def _visible_range(self) -> tuple[float, float]:
        t0, t1 = self._plot.getViewBox().viewRange()[0]
        return t0, t1

    def _refresh_data(self) -> None:
        """读可见窗口 → 峰值抽取 → 更新各曲线与事件线（同步，但量被像素约束）."""
        if not self._loaded_once:
            return
        try:
            self._refresh_data_inner()
        except Exception:  # noqa: BLE001 - 刷新异常不终止浏览（如文件被移动）
            logger.exception("刷新波形失败：%s", self.rec.meta.filename)

    def _refresh_data_inner(self) -> None:
        t0, t1 = self._visible_range()
        enabled = [c for c in self._channels if c["enabled"]]
        picks = [c["idx"] for c in enabled]
        if picks:
            data, times = self.rec.get_window(t0, t1, picks)
            data_uv = data * _UV
            width_px = max(int(self._plot.vb.width()), 100)
            max_points = width_px * _SAMPLES_PER_PIXEL
            if data_uv.shape[1] > 0 and not self._spacing_estimated:
                self._estimate_spacing(data_uv)
            gain = self._gain_scale()
            for row, ch in enumerate(enabled):
                out_t, out_v = minmax_decimate(times, data_uv[row], max_points)
                # 增益乘波形、间距不乘（M6 修复：旧版 `out_v + idx*spacing*gain`
                # 只拉开基线不缩波形，gain>1 时上方通道飞出固定 yRange、
                # gain<1 时全部叠回基线——与"只缩波形不挪基线"的语义相反）
                ch["curve"].setData(
                    out_t, out_v * gain + ch["idx"] * self._spacing_uv,
                    connect="pairs",
                )
        # 通道标签跟随视口左缘（所有通道都更新，含隐藏——便宜且状态一致）
        margin = (t1 - t0) * 0.012
        for ch in self._channels:
            ch["label"].setPos(t0 + margin, ch["idx"] * self._spacing_uv)
        self._update_scale_bar(t0, t1)
        self._update_window_label(t1 - t0)
        # 时间标签
        self._lbl_time.setText(
            S.TIME_FMT.format(t=(t0 + t1) / 2, total=self.rec.meta.duration_s)
        )
        self._update_event_lines(t0, t1)

    _spacing_estimated = False

    def _estimate_spacing(self, data_uv: np.ndarray) -> None:
        """用首帧数据的稳健振幅估计通道间距（一次即止）.

        MAD 对坏通道/瞬态尖峰不敏感，×8 保证相邻通道波形基本不重叠。
        """
        stds = np.median(np.abs(data_uv - np.median(data_uv, axis=1, keepdims=True)), axis=1)
        amp = float(np.median(stds)) * _SPACING_MAD_SCALE
        if amp > 1e-3:  # 全平数据（如常数导联）不覆盖默认值
            self._spacing_uv = amp
            n = len(self._channels)
            self._plot.setYRange(
                -1.5 * self._spacing_uv, (n + 0.5) * self._spacing_uv, padding=0
            )
        self._spacing_estimated = True

    def _gain_scale(self) -> float:
        """增益滑杆 → 显示缩放（10^(x/10)，只缩波形不挪基线）."""
        return 10.0 ** (self._gain / 10.0)

    def _on_gain(self, value: int) -> None:
        self._gain = value
        self._refresh_data()

    def _update_scale_bar(self, t0: float, t1: float) -> None:
        """右上角幅值标尺：像素长度固定，标注换算回真实 µV（含增益）.

        竖线画在**数据坐标**里（长度 = 真实幅度 × 增益），所以增益变化时
        线长跟着波形一起变，而文字标注（真实 µV）只反映数据本身——
        堆叠显示下所有通道共享同一比例尺（EEG 浏览器标准做法）。
        """
        vb = self._plot.getViewBox()
        _, (y0, y1) = vb.viewRange()
        if y1 - y0 <= 0:
            return
        h_px = float(max(vb.height(), 50))
        gain = self._gain_scale()
        # 60px 对应的数据坐标长度 ÷ 增益 = 真实信号幅度，再取漂亮数
        real_uv = _nice_number((y1 - y0) * (_SCALE_BAR_PX / h_px) / gain)
        x = t1 - (t1 - t0) * 0.03
        y_top = y0 + (y1 - y0) * 0.12
        self._scale_line.setData([x, x], [y_top, y_top + real_uv * gain])
        self._scale_text.setPos(x - (t1 - t0) * 0.012, y_top + real_uv * gain / 2)
        self._scale_text.setText(f"{real_uv:g} {S.UNIT_UV}")

    def _update_window_label(self, width_s: float) -> None:
        """把当前视口宽度回写到一屏时长框（拖框缩放/Ctrl+滚轮后保持一致）."""
        txt = f"{width_s:g}"
        if txt != self._window_combo.currentText():
            self._combo_lock = True
            self._window_combo.setCurrentText(txt)
            self._combo_lock = False

    def _update_event_lines(self, t0: float, t1: float) -> None:
        """可视区内事件画彩色虚线.

        可视区内事件数通常几十条以内，全量重建成本可忽略（比增量对比简单可靠）。
        """
        ev = self.rec.events
        for line in self._event_lines:
            self._plot.removeItem(line)
        self._event_lines = []
        if len(ev) == 0:
            return
        codes = sorted(set(ev.code))
        for i in ev.in_window(t0, t1):
            line = pg.InfiniteLine(
                pos=ev.onset[i], angle=90,
                pen=pg.mkPen(event_color(ev.code[i], codes), style=Qt.PenStyle.DashLine, width=1),
            )
            self._plot.addItem(line)
            self._event_lines.append(line)

    # ------------------------------------------------------------------ 导航

    def _set_x_range(self, t0: float, t1: float) -> None:
        """设置 x 视口并 clamp 到 [0, duration]（滚轮/按钮/键盘的统一出口）."""
        dur = self.rec.meta.duration_s
        w = t1 - t0
        if w >= dur:  # 一屏比全长还宽 → 全显
            self._plot.setXRange(0.0, dur, padding=0)
            return
        t0c = min(max(t0, 0.0), dur - w)
        self._plot.setXRange(t0c, t0c + w, padding=0)

    def _page(self, direction: int) -> None:
        """上一/下一屏：步进 0.9 屏（留 10% 上下文），到头 clamp."""
        t0, t1 = self._visible_range()
        w = t1 - t0
        self._set_x_range(t0 + direction * _PAGE_STEP * w, t1 + direction * _PAGE_STEP * w)

    def _go_edge(self, first: bool) -> None:
        """最前/最末一屏：[0, w] 或 [dur-w, dur]."""
        dur = self.rec.meta.duration_s
        t0, t1 = self._visible_range()
        w = min(t1 - t0, dur)
        left = 0.0 if first else dur - w
        self._set_x_range(left, left + w)

    def _set_window_s(self, w_s: float) -> None:
        """设置一屏时长（保持当前视口中心不变）."""
        if not (w_s > 0) or not math.isfinite(w_s):
            return
        t0, t1 = self._visible_range()
        c = (t0 + t1) / 2
        self._set_x_range(c - w_s / 2, c + w_s / 2)

    def _on_window_changed(self, text: str) -> None:
        """一屏时长框：用户选预设/输入秒数 → 调整视口宽度.

        输入到一半（"1."、空串）静默忽略；程序化回写由 ``_combo_lock`` 挡住。
        """
        if self._combo_lock:
            return
        try:
            w = float(text.strip())
        except ValueError:
            return
        if w > 0 and math.isfinite(w):
            self._set_window_s(w)

    def _center_at(self, t: float, width_s: float | None = None) -> None:
        """把视图居中到 t（宽度不变或指定）."""
        if width_s is None:
            t0, t1 = self._visible_range()
            width_s = max(t1 - t0, 0.5)
        self._plot.setXRange(t - width_s / 2, t + width_s / 2, padding=0)

    def _jump_event(self, direction: int) -> None:
        """上一/下一事件：从当前视图中心出发找最近的事件 onset."""
        ev = self.rec.events
        if len(ev) == 0:
            return
        t0, t1 = self._visible_range()
        center = (t0 + t1) / 2
        onsets = ev.onset
        if direction > 0:  # 下一事件（时间更晚）
            later = onsets[onsets > center + 1e-6]
            target = float(later.min()) if len(later) else float(onsets.min())
        else:  # 上一事件
            earlier = onsets[onsets < center - 1e-6]
            target = float(earlier.max()) if len(earlier) else float(onsets.max())
        self._center_at(target)

    def keyPressEvent(self, ev) -> None:  # noqa: N802 - Qt 命名
        """键盘导航：←/→ 翻屏、Home/End 首末屏、↑/↓ 增益（需先点图区获焦点）."""
        k = ev.key()
        if k == Qt.Key.Key_Left:
            self._page(-1)
        elif k == Qt.Key.Key_Right:
            self._page(+1)
        elif k == Qt.Key.Key_Home:
            self._go_edge(first=True)
        elif k == Qt.Key.Key_End:
            self._go_edge(first=False)
        elif k == Qt.Key.Key_Up:
            self._gain_slider.setValue(min(self._gain_slider.value() + 1, 20))
        elif k == Qt.Key.Key_Down:
            self._gain_slider.setValue(max(self._gain_slider.value() - 1, -20))
        else:
            super().keyPressEvent(ev)
            return
        ev.accept()

    def _on_channel_toggle(self, item: QListWidgetItem) -> None:
        """通道勾选变化 → 显隐对应曲线与标签并刷新（曲线保留，仅不画）."""
        row = self._ch_list.row(item)
        if 0 <= row < len(self._channels):
            on = item.checkState() == Qt.CheckState.Checked
            self._channels[row]["enabled"] = on
            self._channels[row]["curve"].setVisible(on)
            self._channels[row]["label"].setVisible(on)
            self._refresh_data()

    # ------------------------------------------------------------------ 坏道标记

    def current_bads(self) -> list[str]:
        """当前已标记的坏道（管线面板添加 BadChannelsStep 时的默认值）."""
        return sorted(self._bad_names)

    def _on_channel_context(self, pos) -> None:
        """通道右键 → 标记/取消坏道."""
        item = self._ch_list.itemAt(pos)
        if item is None:
            return
        name = item.text()
        menu = QMenu(self._ch_list)
        unmark = name in self._bad_names
        act = menu.addAction(S.MENU_UNMARK_BAD if unmark else S.MENU_MARK_BAD)
        if menu.exec(self._ch_list.mapToGlobal(pos)) is act:
            self.toggle_bad(name)

    def toggle_bad(self, name: str) -> None:
        """切换某通道的坏道标记：曲线灰显 + 写回 raw.info['bads'] + 广播."""
        if name not in self.rec.meta.channel_names:
            return
        if name in self._bad_names:
            self._bad_names.discard(name)
        else:
            self._bad_names.add(name)
        for ch in self._channels:
            if ch["name"] == name:
                color = S.BAD_PEN_COLOR if name in self._bad_names else S.SIGNAL_PEN_COLOR
                ch["curve"].setPen(pg.mkPen(color, width=1))
        if self.rec.raw is not None:  # 未加载时标记暂存，_on_raw_ready 统一写入
            self.rec.raw.info["bads"] = self.current_bads()
        self.bads_changed.emit(self.current_bads())

    def teardown(self) -> None:
        """tab 关闭清理（主窗口调用 state.close_recording 完成数据释放）."""
        try:
            self._plot.getViewBox().sigRangeChanged.disconnect(self._schedule_refresh)
        except (RuntimeError, TypeError):
            pass  # 未连接/已断开均视为正常
