"""信号浏览器：多通道波形浏览 tab（性能关键路径）.

绘制策略（为什么这样快）：
1. **窗口化读取**：视口变化（30ms 防抖）→ 只读可见 [t0,t1) 的数据
   （``Recording.get_window``，LAZY 大文件也只读这一段）
2. **两档绘制**（M6.7 修复）：样本数 ≤ ~3×像素宽 → 原始折线整段连线
   （``connect="all"``，此密度下折线仍可读）；超出 → 每桶 (min,max) 对的
   包络（``connect="pairs"``）——点数与数据总量无关（134MB 文件与 1MB
   文件同速）。旧版 raw 透传也带 pairs（隔段漏画呈虚线）+ 阈值 2 样本/px
   使 250Hz 数据的 9s/10s 一屏恰跨档（10s 密集竖线带、9s 断续发虚）
3. 通道垂直堆叠：每通道一条曲线 + 固定 y 偏移；通道名画在曲线行左端
   **内侧**（M6 重构，替代旧的 y 轴刻度——任意导联数都不重叠、不截断）
4. **行居中**（M6.7b 修复）：每通道按**本窗口中位数**对齐到自己的行——
   DC 耦合数据（BioSemi BDF，clinicaldata/羊系列）通道带数万 µV 直流
   偏移，若按绝对值堆叠，曲线全画在锁定 yRange 外数千 µV 处，波形区
   一片空白（用户实测"第二个数据打开后 tab 空白"的根因——其实加载
   都成功了，只是画到了视野外）。EEG 浏览器标准做法即行居中显示。

交互（M6 重构，用户实测反馈驱动；M6.8 增四项）：
- **滚轮 = 平移**时间轴（y 轴锁定，通道行不再被滚轮压挤重叠）；
  **Ctrl+滚轮** = 以鼠标位置为锚点缩放一屏时长；右键拖框 = 框选缩放
- 键盘 ←/→ = 上一/下一屏、Home/End = 最前/最后一屏、↑/↓ = 增益 ±1 档
  （点一下图区获取焦点；通道列表/时长框/滑杆聚焦时按键归控件原生行为）
- 工具栏：|◀ 最前 / ◀ 上一屏 / **◀ 1s / 1s ▶**（M6.8 秒级步进）/ 下一屏 ▶ /
  最末 ▶| / 一屏时长下拉（可输入自定义秒）
- **总览时间轴滑块**（M6.8）：底部事件条升级——当前视口为半透明滑块，
  拖动定位；点时间轴任意位置居中过去；x 轴锁死 [0, 时长]
- **行居中开关**（M6.8）：默认开（每通道减本窗口中位数贴行）；关闭后按
  绝对电平显示（通道间真实电平差），y 轴自动适配数据范围；通道列表每行
  显示该通道的直流偏移（后台统计，"CH1  +45.2k µV"）
- **增益**：滑杆粗调（10^(x/10) 指数刻度）+ 输入框精确倍率（0.01–100×，
  权威源）；右上角**幅值标尺**竖线像素长度固定，标注换算回真实 µV
- 事件跳转、通道显隐、右键坏道标记沿用旧版
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core.recording import LoadPolicy, Recording
from ...features.qc import QualityCheckParams, compute_channel_qc
from ...workers.generic import run_in_thread
from ..strings_zh import S
from .event_lane import EventLane, event_color

logger = logging.getLogger(__name__)

# 防抖毫秒数：拖动/缩放时避免每个中间视口都触发读盘
_REFRESH_DEBOUNCE_MS = 30
# raw 折线保留到 ~3 样本/像素才切换包络（M6.7：旧值 2 时 250Hz 数据的
# 9s/10s 一屏恰跨抽取阈值——Retina ~1212 逻辑px 绘图区下 2500 vs 2250 对
# 阈值 2424：10s 密集成竖线带、9s 断续虚线；3 样本/px 折线仍可读，且让
# 常用预设 1/2/5/10s 全部留在折线档，观感连续无跳变）
_SAMPLES_PER_PIXEL = 3
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
    # v_max 曾误写成 t[rows, i_max]（单字符变量名同长，肉眼极难发现）——
    # 包络的"max 点"全部变成时间戳（~0-10 的 小值），上半包络塌到 0 附近，
    # 密集窗口渲染成从真实 min 直落到 0 的密集竖线带（M6.7b 定位修复）
    t_max, v_max = t[rows, i_max], v[rows, i_max]
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


def _fmt_offset_uv(v: float) -> str:
    """通道直流偏移（µV）→ 紧凑带符号文本：+45.2k / −375.0k / +5.20M / +12.3.

    clinicaldata 级偏移（数千到数十万 µV）用 k/M 缩写才能塞进通道列表行。
    """
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:+.2f}M"
    if a >= 1e3:
        return f"{v / 1e3:+.1f}k"
    return f"{v:+.1f}"


# 质量体检三级 → 通道列表前缀 / 中文结论（M7；文案在 strings_zh，禁止写死）
_QC_PREFIX = {
    "good": S.QC_PREFIX_GOOD,
    "suspect": S.QC_PREFIX_SUSPECT,
    "bad": S.QC_PREFIX_BAD,
}
_QC_QUALITY = {
    "good": S.QC_QUALITY_GOOD,
    "suspect": S.QC_QUALITY_SUSPECT,
    "bad": S.QC_QUALITY_BAD,
}


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
        self._gain = 0.0  # 增益的权威值（dB×10 浮点，增益=10^(x/10)）；初值 0 = 1.0×。
        # （M6 修复：旧值 1.0 让首帧一直带 10^0.1≈1.26× 的隐形增益——
        #   滑杆初始就是 0，字段却初始化成 1.0，从 M1 潜伏至今）
        # （M6.8 改为浮点：滑杆整数刻度只是粗调吸附，输入框才是精确权威源）
        self._gain_syncing = False  # 程序化同步滑杆/输入框时不触发用户处理逻辑
        self._abs_lo: float | None = None  # 绝对模式 y 自适配范围（本窗口数据×增益）
        self._abs_hi: float | None = None
        self._event_lines: list[pg.InfiniteLine] = []
        self._loaded_once = False
        # 坏道标记（raw 未加载时先记在这里，加载后一次性写入 info["bads"]）
        self._bad_names: set[str] = set()
        self._combo_lock = False  # 时长框程序化回写时不触发用户处理逻辑
        # 质量体检结果（M7）：通道名 -> compute_channel_qc 的行 dict；
        # None/空 = 尚未体检（列表行不显示前缀）。体检与偏移统计都只拼
        # 通道列表文本，两者由 _refresh_ch_list_text 统一合成
        self._qc: dict[str, dict] = {}
        self._qc_running = False  # 防重入：计算期间禁用按钮
        self._ch_offsets: np.ndarray | None = None  # 直流偏移（µV，行文本用）

        self._build_ui()
        self._populate_channels()

        # 首帧数据（含 ensure_raw）在后台线程，避免大文件头读取卡 UI
        run_in_thread(
            lambda: self.rec.ensure_raw(self.rec.recommended_policy()),
            on_done=self._on_raw_ready,
            on_error=lambda m: logger.error("加载数据失败 %s：%s", self.rec.meta.filename, m),
        )

    # ------------------------------------------------------------------ UI 构建

    def _build_ui(self) -> None:
        # 工具条：翻屏导航 + 一屏时长（M6）+ 秒级平移（M6.8）｜
        # 时间 + 事件跳转 + 行居中开关 + 增益滑杆/输入框（M6.8）
        bar = QHBoxLayout()
        self._btn_first = QPushButton(S.BTN_GO_FIRST)
        self._btn_prev_page = QPushButton(S.BTN_PREV_PAGE)
        self._btn_prev_s = QPushButton(S.BTN_PREV_S)  # ±1s：细于 0.9 屏的步进
        self._btn_next_s = QPushButton(S.BTN_NEXT_S)
        self._btn_next_page = QPushButton(S.BTN_NEXT_PAGE)
        self._btn_last = QPushButton(S.BTN_GO_LAST)
        self._btn_first.clicked.connect(lambda: self._go_edge(first=True))
        self._btn_prev_page.clicked.connect(lambda: self._page(-1))
        self._btn_prev_s.clicked.connect(lambda: self._step_s(-1))
        self._btn_next_s.clicked.connect(lambda: self._step_s(+1))
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

        # 质量体检（M7）：左组尾部——先体检通道质量再往下走分析
        self._btn_qc = QPushButton(S.BTN_QC)
        self._btn_qc.setToolTip(S.BTN_QC_TIP)
        self._btn_qc.clicked.connect(self._run_qc)

        self._lbl_time = QLabel(S.BROWSER_NO_DATA)
        self._btn_prev = QPushButton(S.BTN_PREV_EVENT)
        self._btn_next = QPushButton(S.BTN_NEXT_EVENT)
        # 「◀ 上一事件」= 时间更早（direction=-1）；「下一事件 ▶」= 更晚（+1）。
        # 曾长期接反（prev→+1/next→-1），写使用手册盘点 UI 时发现于 2026-08-18 修正。
        self._btn_prev.clicked.connect(lambda: self._jump_event(-1))
        self._btn_next.clicked.connect(lambda: self._jump_event(+1))
        # 行居中开关（M6.8）：默认勾选 = M6.7b 行为；不勾显示绝对电平
        self._center_cb = QCheckBox(S.CB_ROW_CENTER)
        self._center_cb.setChecked(True)
        self._center_cb.setToolTip(S.CB_ROW_CENTER_TIP)
        self._center_cb.toggled.connect(lambda _on: self._refresh_data())
        gain_lbl = QLabel(S.LBL_GAIN)
        self._gain_slider = QSlider(Qt.Orientation.Horizontal)
        self._gain_slider.setRange(-20, 20)  # 10^(x/10)：0.01× – 100×，指数刻度（粗调）
        self._gain_slider.setValue(0)
        self._gain_slider.valueChanged.connect(self._on_gain)
        self._gain_slider.setMaximumWidth(160)
        # 增益输入框（M6.8）：精确倍率的权威源（滑杆整数刻度只能 10^(n/10) 档，
        # 无法设 2.5× 这类值）；双向同步见 _set_gain
        self._gain_spin = QDoubleSpinBox()
        self._gain_spin.setRange(0.01, 100.0)  # 与滑杆 -20..20 对应（同一对数尺度）
        self._gain_spin.setDecimals(2)
        self._gain_spin.setSingleStep(0.1)
        self._gain_spin.setSuffix(f" {S.GAIN_SUFFIX}")
        self._gain_spin.setValue(1.0)
        self._gain_spin.valueChanged.connect(self._on_gain_spin)
        self._gain_spin.setMaximumWidth(90)
        for w in (
            self._btn_first, self._btn_prev_page, self._btn_prev_s, self._btn_next_s,
            self._btn_next_page, self._btn_last, win_lbl, self._window_combo,
            self._btn_qc,
        ):
            bar.addWidget(w)
        bar.addStretch(1)
        for w in (
            self._lbl_time, self._btn_prev, self._btn_next, self._center_cb,
            gain_lbl, self._gain_slider, self._gain_spin,
        ):
            bar.addWidget(w)

        # 通道列表（左）：勾选显隐 + 右键标记坏道（M3 与 BadChannelsStep 联动）；
        # M6.8 起每行还显示该通道的直流偏移（后台算好后拼进 text）
        self._ch_list = QListWidget()
        self._ch_list.setMaximumWidth(200)
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
        # 总览滑块双向联动（M6.8）：拖滑块 → 主图跟随；主图视口变化 → 滑块回写
        self._lane.viewport_moved.connect(self._on_lane_viewport)
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
            # 名称的权威源放 UserRole（M6.8）：text 后续会被拼上直流偏移值
            # （"CH1  +45.2k µV"），右键菜单/坏道标记不能再拿 text 当名字
            item.setData(Qt.ItemDataRole.UserRole, name)
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
        # 总览滑块即时回写（M6.8）：直连、不走 30ms 防抖——拖主图/滚轮时
        # 滑块跟手；读数刷新仍走防抖（数据量被像素约束，两者不冲突）
        vb.sigRangeChanged.connect(lambda *_a: self._lane.set_viewport(*self._visible_range()))
        self._refresh_data()
        # 各通道直流偏移统计（通道列表显示用）：后台算，完成后主线程拼进列表
        run_in_thread(
            self._compute_channel_offsets,
            on_done=self._apply_channel_offsets,
            on_error=lambda m: logger.warning("通道偏移统计失败 %s：%s",
                                              self.rec.meta.filename, m),
        )

    def _compute_channel_offsets(self) -> np.ndarray:
        """每通道的直流偏移（µV）= 分窗中位数再取中位数（后台线程执行）.

        不整载 ``get_data()``（LAZY 大文件会物化整个数组）：沿录制全长取
        ≤20 个均匀分布的 2s 窗逐窗取中位数，再对窗口取中位数——对 DC
        偏移这一统计量与全程中位数等价，且对局部瞬态/慢漂移更稳健。
        """
        n_ch = len(self.rec.meta.channel_names)
        dur = self.rec.meta.duration_s
        m = min(20, max(1, int(dur / 2)))  # 窗数：2s 窗且至多 20 个
        medians = np.zeros((m, n_ch))
        for k in range(m):
            t0 = dur * k / m
            t1 = min(t0 + 2.0, dur)
            if t1 <= t0:
                t1 = min(t0 + 0.1, dur)
            data, _ = self.rec.get_window(t0, t1, list(range(n_ch)))
            if data.shape[1] == 0:
                continue
            medians[k] = np.median(data * _UV, axis=1)
        return np.median(medians, axis=0)

    def _apply_channel_offsets(self, offsets: np.ndarray) -> None:
        """偏移统计完成（主线程）：存值后重拼通道列表行文本（见 _refresh_ch_list_text）."""
        self._ch_offsets = offsets
        self._refresh_ch_list_text()

    def _refresh_ch_list_text(self) -> None:
        """按最新的偏移/体检结果重拼通道列表行文本与悬浮提示.

        行文本 = [体检前缀] + 通道名 + [直流偏移]；体检前缀 ✓/?/✗ 只在
        做过体检后出现，tooltip 携带问题明细与全部指标。名称权威源仍是
        UserRole（M6.8 约定不变）。``blockSignals`` 必须有——
        ``itemChanged`` 在 ``setText``/``setToolTip`` 时都触发，不挡会连发
        N 次 ``_on_channel_toggle`` → 无谓刷新。
        """
        offsets = self._ch_offsets
        self._ch_list.blockSignals(True)
        try:
            for i in range(self._ch_list.count()):
                item = self._ch_list.item(i)
                name = item.data(Qt.ItemDataRole.UserRole)
                text = name
                qc = self._qc.get(name)
                if qc is not None:
                    text = _QC_PREFIX[qc["quality"]] + text
                if offsets is not None and i < len(offsets):
                    text += f"  {_fmt_offset_uv(float(offsets[i]))} {S.UNIT_UV}"
                item.setText(text)
                item.setToolTip(self._qc_tooltip(name) if qc else "")
        finally:
            self._ch_list.blockSignals(False)

    # ------------------------------------------------------------------ 质量体检（M7）

    def _run_qc(self) -> None:
        """「质量体检」按钮：后台算 compute_channel_qc，完成后标记列表+建议坏道.

        防重入：计算期间禁用按钮；首帧未加载完直接忽略（按钮在加载完成前
        点了也不该炸）。
        """
        if not self._loaded_once or self._qc_running:
            return
        self._qc_running = True
        self._btn_qc.setEnabled(False)
        run_in_thread(
            self._compute_qc,
            on_done=self._apply_qc,
            on_error=self._on_qc_error,
        )

    def _compute_qc(self) -> list[dict]:
        """逐通道体检（后台线程）：与偏移统计同款 get_window 分窗采样，不整载."""
        names = list(self.rec.meta.channel_names)
        return compute_channel_qc(
            self.rec.get_window, names, self.rec.meta.sfreq,
            self.rec.meta.duration_s, QualityCheckParams(),
        )

    def _on_qc_error(self, msg: str) -> None:
        """体检失败（主线程）：恢复按钮并给出可见反馈（只打日志用户看不见）."""
        self._qc_running = False
        self._btn_qc.setEnabled(True)
        logger.warning("质量体检失败 %s：%s", self.rec.meta.filename, msg)
        QMessageBox.critical(self, S.QC_SUGGEST_TITLE, S.QC_FAIL_TEXT.format(msg=msg))

    def _apply_qc(self, rows: list[dict]) -> None:
        """体检完成（主线程）：存结果 → 重拼列表 → 坏道建议确认.

        确认走 QMessageBox.question（e2e 须逐模块 patch 本模块的
        QMessageBox——MainWindow 的 patch 罩不到这里）；「是」则逐个
        ``toggle_bad`` 复用现有坏道机制（曲线灰显 + info["bads"] +
        bads_changed 广播），不另造一套标记。
        """
        self._qc_running = False
        self._btn_qc.setEnabled(True)
        self._qc = {r["channel"]: r for r in rows}
        self._refresh_ch_list_text()
        bad_rows = [r for r in rows if r["quality"] == "bad"]
        if not bad_rows:
            QMessageBox.information(
                self, S.QC_SUGGEST_TITLE, S.QC_ALL_GOOD.format(n=len(rows))
            )
            return
        lines = "\n".join(
            f"{S.QC_PREFIX_BAD}{r['channel']}——{'；'.join(r['reasons'])}"
            for r in bad_rows
        )
        answer = QMessageBox.question(
            self, S.QC_SUGGEST_TITLE,
            S.QC_SUGGEST_TEXT.format(n=len(bad_rows), lines=lines),
        )
        if answer == QMessageBox.StandardButton.Yes:
            for r in bad_rows:
                if r["channel"] not in self._bad_names:
                    self.toggle_bad(r["channel"])

    def _qc_tooltip(self, name: str) -> str:
        """体检行悬浮提示：质量结论 + 问题明细 + 全部指标（中文）."""
        qc = self._qc.get(name)
        if qc is None:
            return ""
        m = qc["metrics"]
        stats = S.QC_TIP_STATS.format(
            dc=_fmt_offset_uv(m["qc_dc_uv"]),
            std=_fmt_offset_uv(m["qc_std_uv"]),
            drift=f"{m['qc_drift_uv_min']:+.1f}",
            flat=f"{m['qc_flat_pct']:.1f}",
            rail=f"{m['qc_rail_pct']:.1f}",
        )
        body = "\n".join(qc["reasons"]) if qc["reasons"] else S.QC_NO_ISSUE
        return f"{name} [{_QC_QUALITY[qc['quality']]}]\n{body}\n{stats}"

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
            # 行居中的基线 = 每通道**本窗口**中位数（随视口重算）：不管通道
            # 带多大直流偏移/慢漂移，波形始终落在自己行的附近（M6.7b）。
            # 窗口内漂移的"斜率形状"仍然如实呈现，只有跨窗口的绝对电平
            # 不再进入画面（EEG 浏览器通行语义；绝对电平看特征/导出）。
            # M6.8 起可由「行居中」开关关闭——关闭后按绝对电平显示（见下）。
            centering = self._center_cb.isChecked()
            if centering and data_uv.shape[1] > 0:
                baselines = np.median(data_uv, axis=1)
            else:
                baselines = np.zeros(len(enabled))
            gain = self._gain_scale()
            # 绝对模式的 y 自适配范围（本窗口数据 × 增益；空窗口保持原范围）
            self._abs_lo = float(data_uv.min()) * gain if data_uv.size else None
            self._abs_hi = float(data_uv.max()) * gain if data_uv.size else None
            for row, ch in enumerate(enabled):
                out_t, out_v = minmax_decimate(times, data_uv[row], max_points)
                # connect 只对抽取后的 (min,max) 成对结构用 "pairs"；raw 透传
                # （n ≤ max_points，minmax_decimate 原样返回）必须 "all" 整段
                # 连线——原始序列带 pairs 会 0-1/2-3/… 隔段漏画，波形呈断续
                # 虚线（M6.7 修复，"9s 屏线太虚"根因）
                connect = "pairs" if len(times) > max_points else "all"
                # 显示值（行居中）=（原始值 − 行基线）× 增益 + 行位置：增益只
                # 缩波形不挪基线（M6 修复语义不变）；行基线扣除让 DC 耦合
                # 数据的波形留在锁定 yRange 内（M6.7b，"空白 tab"根因）。
                # 显示值（绝对模式）= 原始值 × 增益：无行偏移、纯电平堆叠，
                # 通道间真实电平差直接可见（yRange 同步自适配，见 _apply_y_range）
                if centering:
                    disp = (out_v - baselines[row]) * gain + ch["idx"] * self._spacing_uv
                else:
                    disp = out_v * gain
                    # 记本窗口中位（含增益）供标签贴行用；隐藏通道用旧值兜底
                    ch["_med"] = (
                        float(np.median(data_uv[row])) * gain
                        if data_uv.shape[1] > 0
                        else ch.get("_med", ch["idx"] * self._spacing_uv)
                    )
                ch["curve"].setData(out_t, disp, connect=connect)
        # 通道标签跟随视口左缘（所有通道都更新，含隐藏——便宜且状态一致）；
        # 绝对模式标签贴曲线本窗口中位（行结构已让位于绝对电平，标签是唯一
        # 行标识；隐藏通道沿用上次 _med 兜底，其 label 本就不可见）
        margin = (t1 - t0) * 0.012
        centering = self._center_cb.isChecked()
        for ch in self._channels:
            y = (
                ch["idx"] * self._spacing_uv
                if centering
                else ch.get("_med", ch["idx"] * self._spacing_uv)
            )
            ch["label"].setPos(t0 + margin, y)
        # y 轴范围按模式应用（行居中=堆叠行布局；绝对=数据自适配）。
        # 放在 _estimate_spacing 之后：首帧同一次刷新内后写的胜出，天然正确。
        self._apply_y_range()
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
        只统计**有交流起伏的通道**（M6.7b）：开路/饱和平线的 MAD=0，
        若一并取中位数，平线过半时（clinicaldata TPDJ 系 8 通道 5 条平）
        中位数恰为 0 → 间距塌缩 → yRange 塌缩 → 全部画到视野外。
        """
        stds = np.median(np.abs(data_uv - np.median(data_uv, axis=1, keepdims=True)), axis=1)
        live = stds[stds > 0.01]  # µV 级阈值：真信号 MAD ≥ µV 级，平线严格为 0
        amp = float(np.median(live)) * _SPACING_MAD_SCALE if len(live) else 0.0
        if amp > 1e-3:  # 全平数据（如常数导联）不覆盖默认值
            self._spacing_uv = amp
            n = len(self._channels)
            self._plot.setYRange(
                -1.5 * self._spacing_uv, (n + 0.5) * self._spacing_uv, padding=0
            )
        self._spacing_estimated = True

    def _apply_y_range(self) -> None:
        """按显示模式应用 y 轴范围（M6.8）——每次刷新末尾调用.

        - 行居中：堆叠行布局 ``[-1.5s, (n+0.5)s]``（与首帧/间距估计同公式），
          同值重复设置幂等无害；从绝对模式切回时靠它恢复行布局。
        - 绝对模式：y 自适配本窗口数据范围（留 2% 边）——大直流偏移数据
          若沿用堆叠 yRange 会全部画在视野外（M6.7b"空白 tab"的绝对模式
          镜像）。与 y 轴锁定不冲突：锁定只禁用户手势，程序 setYRange 照常。

        幅值标尺是纯视图几何（视口高度÷增益换算真实 µV），与模式无关。
        """
        n = max(len(self._channels), 1)
        if self._center_cb.isChecked():
            self._plot.setYRange(
                -1.5 * self._spacing_uv, (n + 0.5) * self._spacing_uv, padding=0
            )
        elif self._abs_lo is not None and self._abs_hi is not None and self._abs_hi > self._abs_lo:
            pad = (self._abs_hi - self._abs_lo) * 0.02
            self._plot.setYRange(self._abs_lo - pad, self._abs_hi + pad, padding=0)

    def _gain_scale(self) -> float:
        """增益 → 显示缩放（10^(x/10)，只缩波形不挪基线）."""
        return 10.0 ** (self._gain / 10.0)

    def _set_gain(self, value: float) -> None:
        """增益三入口（滑杆/输入框/键盘）的统一出口（M6.8）.

        ``_gain`` 是 dB×10 浮点权威值；滑杆整数刻度吸附最近档（粗调），
        输入框显示精确倍率。同步期间置 ``_gain_syncing`` 挡回环
        （与 ``_combo_lock`` 同一模式）。
        """
        v = min(max(value, -20.0), 20.0)
        self._gain = v
        self._gain_syncing = True
        try:
            self._gain_slider.setValue(int(round(v)))
            self._gain_spin.setValue(10.0 ** (v / 10.0))
        finally:
            self._gain_syncing = False
        self._refresh_data()

    def _on_gain(self, value: int) -> None:
        if self._gain_syncing:
            return
        self._set_gain(float(value))

    def _on_gain_spin(self, value: float) -> None:
        """输入框倍率 → dB×10（10·log₁₀；0 被范围下限挡在外面）."""
        if self._gain_syncing or value <= 0:
            return
        self._set_gain(10.0 * math.log10(value))

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

    def _step_s(self, direction: int) -> None:
        """上一/下一秒（M6.8）：固定 1s 步进，补充翻屏（0.9 屏）的细分辨率.

        高倍放大（一屏 2–5s）时翻屏一步就是大半屏，秒级步进才能逐秒推进。
        """
        t0, t1 = self._visible_range()
        self._set_x_range(t0 + direction, t1 + direction)

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

    def _on_lane_viewport(self, t0: float, t1: float) -> None:
        """总览滑块拖动 → 主图跟随（M6.8）——**只取中心、按自身宽度重锚**.

        不直接采纳滑块两缘的宽度：拖出 [0, duration] 时滑块两条边界线
        各自被 bounds 钳制、区域会瞬时压窄——若照单全收就把一屏时长
        永久改掉了。取中心 + 主图当前宽度后，clamp/回写把滑块纠正回来。
        """
        t0c, t1c = self._visible_range()
        w = t1c - t0c
        c = (t0 + t1) / 2
        self._set_x_range(c - w / 2, c + w / 2)

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
            # 直接在权威值上 ±1（M6.8）：走滑杆 setValue(int) 会把输入框设的
            # 小数增益（如 2.5× ≈ 3.98 dB×10）取整抹掉，一键跳变 4 倍
            self._set_gain(self._gain + 1.0)
        elif k == Qt.Key.Key_Down:
            self._set_gain(self._gain - 1.0)
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
        """通道右键 → 标记/取消坏道（名字取 UserRole——text 已被偏移值拼接）."""
        item = self._ch_list.itemAt(pos)
        if item is None:
            return
        name = item.data(Qt.ItemDataRole.UserRole)
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
