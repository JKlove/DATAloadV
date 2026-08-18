"""M6 UI 测试：信号浏览器通道标签 / 幅值标尺 / 窗口导航 / 增益语义 / 滚轮平移.

用户实测 v1 后的三点反馈（通道名重叠截断、无幅值标注、无窗口导航）
在 M6 全部重构——本文件把每一处修复固定成回归：任何退化都能被抓住。
夹具走真实路径：合成 raw 存 FIF → 读取器注册表打开 → SignalBrowserView。
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from PySide6.QtCore import QPointF, Qt  # noqa: E402

from dataloadv.io.registry import open_file  # noqa: E402
from dataloadv.ui.widgets.signal_browser import (  # noqa: E402
    SignalBrowserView,
    _nice_number,
)


class _FakeWheel:
    """wheelEvent 需要的最小事件桩（delta/modifiers/scenePos/accept）."""

    def __init__(self, delta: int, ctrl: bool = False) -> None:
        self._d = delta
        self._ctrl = ctrl
        self.accepted = False

    def delta(self) -> int:
        return self._d

    def modifiers(self):
        return (
            Qt.KeyboardModifier.ControlModifier
            if self._ctrl
            else Qt.KeyboardModifier.NoModifier
        )

    def scenePos(self) -> QPointF:
        return QPointF(0.0, 0.0)

    def accept(self) -> None:
        self.accepted = True


@pytest.fixture()
def browser(tmp_path, qtbot, synthetic_raw):
    """FIF 往返 → open_file → 浏览器（等首帧加载完成）→ 测试后释放."""
    fif = tmp_path / "synth.fif"
    synthetic_raw.save(fif, overwrite=True, verbose="ERROR")
    rec = open_file(fif)
    view = SignalBrowserView(rec)
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
    view._refresh_data()
    yield view
    view.teardown()
    rec.unload()


class TestNiceNumber:
    def test_ladder_and_shift_identity(self):
        assert _nice_number(0.9) == 1.0
        assert _nice_number(2.1) == 5.0
        assert _nice_number(6.0) == 10.0
        # 标尺随增益变化依赖的恒等式：除 10 只挪指数不换尾数
        for v in (0.037, 0.5, 1.7, 3.0, 42.0, 900.0):
            assert _nice_number(v / 10) == _nice_number(v) / 10


class TestChannelLabels:
    """通道名内嵌标签（替代 y 轴刻度）——重叠/截断问题的回归."""

    def test_one_fullname_label_per_channel(self, browser):
        names = browser.rec.meta.channel_names
        assert len(browser._channels) == len(names) == 8
        for ch, name in zip(browser._channels, names):
            assert ch["label"].toPlainText() == name  # 全名，无 "…" 截断
        # 旧的 y 轴刻度通道名已隐藏（截断源头）
        assert not browser._plot.getAxis("left").isVisible()

    def test_labels_follow_viewport_left_edge(self, browser):
        browser._go_edge(first=True)
        browser._refresh_data()
        t0, t1 = browser._visible_range()
        x = browser._channels[0]["label"].pos().x()
        assert t0 <= x <= t0 + 0.05 * (t1 - t0)  # 视口左缘内侧一点


class TestGainScalesWaveform:
    """M6 增益 bug 修复：增益乘波形、不乘间距、不动 yRange."""

    def test_gain_multiplies_waveform_amplitude_only(self, browser):
        ch0 = browser._channels[0]  # idx=0：基线项 = 0*spacing，幅度可直接读
        assert ch0["curve"].yData is not None
        base_ptp = float(np.ptp(ch0["curve"].yData))
        y_before = browser._plot.getViewBox().viewRange()[1]

        browser._gain_slider.setValue(10)  # 10^(10/10) = 10×
        assert ch0["curve"].yData is not None
        amp_ptp = float(np.ptp(ch0["curve"].yData))

        # 波形幅度恰好 ×10（同一窗口同一抽取，唯一差别是增益因子）
        assert abs(amp_ptp / base_ptp - 10.0) < 1e-6
        # y 视口纹丝不动（旧 bug 的另一个面：间距被乘导致通道飞出视口）
        assert browser._plot.getViewBox().viewRange()[1] == y_before


class TestScaleBar:
    """右上角幅值标尺：标注 µV 且随增益换算."""

    def test_scale_bar_shows_uv_and_tracks_gain(self, browser):
        txt1 = browser._scale_text.toPlainText()
        assert "µV" in txt1 and any(c.isdigit() for c in txt1)
        browser._gain_slider.setValue(10)
        txt2 = browser._scale_text.toPlainText()
        # 增益 ×10 → 同像素长度对应的真实幅度 ÷10（_nice_number 恒等式保证）
        assert "µV" in txt2 and txt2 != txt1


class TestWindowNavigation:
    """一屏时长 / 翻屏 / 首末屏的视口数学（clamp 到 [0, duration]）."""

    def test_set_window_s_keeps_center(self, browser):
        browser._set_window_s(10.0)
        c0 = sum(browser._visible_range()) / 2
        browser._set_window_s(5.0)
        t0, t1 = browser._visible_range()
        assert abs((t1 - t0) - 5.0) < 1e-6
        assert abs((t0 + t1) / 2 - c0) < 1e-6

    def test_page_steps_ninety_percent(self, browser):
        browser._go_edge(first=True)
        w = browser._visible_range()[1]
        browser._page(+1)
        t0, t1 = browser._visible_range()
        assert abs(t0 - 0.9 * w) < 1e-6  # 步进 0.9 屏（留 10% 上下文）
        assert abs((t1 - t0) - w) < 1e-6

    def test_go_edge_first_and_last(self, browser):
        dur = browser.rec.meta.duration_s
        browser._set_window_s(5.0)
        browser._go_edge(first=False)
        t0, t1 = browser._visible_range()
        assert abs(t1 - dur) < 1e-6 and abs((t1 - t0) - 5.0) < 1e-6
        browser._go_edge(first=True)
        t0, t1 = browser._visible_range()
        assert abs(t0) < 1e-6 and abs((t1 - t0) - 5.0) < 1e-6

    def test_paging_past_end_clamps(self, browser):
        dur = browser.rec.meta.duration_s
        browser._set_window_s(5.0)
        browser._go_edge(first=False)
        for _ in range(3):
            browser._page(+1)
        t0, t1 = browser._visible_range()
        assert abs(t1 - dur) < 1e-3  # 停在最末屏，不越界

    def test_combo_text_follows_viewport(self, browser):
        browser._set_window_s(5.0)
        browser._refresh_data()
        assert browser._window_combo.currentText() == "5"
        browser._window_combo.setCurrentText("30")  # 模拟用户输入
        t0, t1 = browser._visible_range()
        assert abs((t1 - t0) - 30.0) < 1e-6

    def test_invalid_combo_input_ignored(self, browser):
        browser._set_window_s(5.0)
        browser._window_combo.setCurrentText("abc")  # 输入到一半的无效值
        browser._window_combo.setCurrentText("-3")
        t0, t1 = browser._visible_range()
        assert abs((t1 - t0) - 5.0) < 1e-6  # 视口不动


class TestWheel:
    """滚轮=平移（y 锁定）、Ctrl+滚轮=锚点缩放——通道压挤问题的回归."""

    def test_wheel_pans_x_only(self, browser):
        browser._go_edge(first=True)
        vb = browser._plot.getViewBox()
        t0_0, t1_0 = browser._visible_range()
        y_before = vb.viewRange()[1]
        vb.wheelEvent(_FakeWheel(delta=-120))  # 向下滚 → 时间更晚
        t0, t1 = browser._visible_range()
        assert t0 > t0_0  # 平移生效
        assert abs((t1 - t0) - (t1_0 - t0_0)) < 1e-6  # 一屏时长不变
        assert vb.viewRange()[1] == y_before  # y 轴纹丝不动

    def test_ctrl_wheel_scales_window_width(self, browser):
        browser._go_edge(first=True)
        vb = browser._plot.getViewBox()
        w0 = browser._visible_range()[1] - browser._visible_range()[0]
        vb.wheelEvent(_FakeWheel(delta=120, ctrl=True))  # 放大 → 时长缩短
        t0, t1 = browser._visible_range()
        assert abs((t1 - t0) / w0 - 0.8) < 1e-6  # 1/1.25
