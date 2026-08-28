"""M6 UI 测试：信号浏览器通道标签 / 幅值标尺 / 窗口导航 / 增益语义 / 滚轮平移.

用户实测 v1 后的三点反馈（通道名重叠截断、无幅值标注、无窗口导航）
在 M6 全部重构——本文件把每一处修复固定成回归：任何退化都能被抓住。
夹具走真实路径：合成 raw 存 FIF → 读取器注册表打开 → SignalBrowserView。
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from PySide6.QtCore import QPointF, Qt  # noqa: E402

from dataloadv.core.recording import EventTable  # noqa: E402
from dataloadv.io.registry import open_file  # noqa: E402
from dataloadv.ui.strings_zh import S  # noqa: E402
from dataloadv.ui.widgets.event_lane import EventLane  # noqa: E402
from dataloadv.ui.widgets.signal_browser import (  # noqa: E402
    SignalBrowserView,
    _SAMPLES_PER_PIXEL,
    _fmt_offset_uv,
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


@pytest.fixture()
def offset_browser_mod(tmp_path, qtbot):
    """clinicaldata 形态合成：3 条大偏移真信号 + 5 条饱和安全线（M6.8 提为模块级共用）.

    CH1 +50mV 偏移正弦 / CH2 −30mV 偏移噪声 / CH3 +5mV 偏移正弦 /
    CH4-8 饱和平线 0.375V——TestOffsetRobustDisplay 与 TestDcToggle 共用。
    """
    mne = pytest.importorskip("mne")
    rng = np.random.default_rng(7)
    sfreq, n_seconds, n_channels = 250.0, 60.0, 8
    t = np.arange(int(sfreq * n_seconds)) / sfreq
    data = np.zeros((n_channels, len(t)))
    data[0] = 50e-3 + 100e-6 * np.sin(2 * np.pi * 10.0 * t)  # +50mV 偏移
    data[1] = -30e-3 + 80e-6 * rng.normal(size=len(t))       # −30mV 偏移
    data[2] = 5e-3 + 60e-6 * np.sin(2 * np.pi * 7.0 * t)     # +5mV 偏移
    data[3:] = 0.375                                          # 饱和平线
    info = mne.create_info(
        ch_names=[f"CH{i + 1}" for i in range(n_channels)], sfreq=sfreq, ch_types="eeg"
    )
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    fif = tmp_path / "offset.fif"
    raw.save(fif, overwrite=True, verbose="ERROR")
    rec = open_file(fif)
    view = SignalBrowserView(rec)
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
    view._refresh_data()
    yield view
    view.teardown()
    rec.unload()


class _FakeKey:
    """keyPressEvent 需要的最小事件桩（key/accept）."""

    def __init__(self, key) -> None:
        self._k = key
        self.accepted = False

    def key(self):
        return self._k

    def accept(self) -> None:
        self.accepted = True


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


class TestRenderTwoModes:
    """M6.7 渲染修复：raw 透传整段连线 / 抽取后才用 pairs.

    旧版无条件 ``connect="pairs"``：raw 透传序列被 0-1/2-3/… 隔段漏画，
    波形呈断续虚线（用户实测"9s 屏线太虚"）；且阈值 2 样本/px 让 250Hz
    数据的 9s/10s 一屏恰跨抽取档（10s 密集竖线带）——两处都要有回归。
    """

    @staticmethod
    def _max_points(browser) -> int:
        # 与 _refresh_data_inner 同口径（vb 未显示时 width() 可能为 0 → 下限 100）
        return max(int(browser._plot.vb.width()), 100) * _SAMPLES_PER_PIXEL

    def test_sparse_window_draws_connected_polyline(self, browser):
        sf = browser.rec.raw.info["sfreq"]
        w = 0.5 * self._max_points(browser) / sf  # 样本数 = 阈值一半 → raw 透传
        browser._set_window_s(w)
        browser._refresh_data()
        t0, t1 = browser._visible_range()
        assert (t1 - t0) * sf <= self._max_points(browser)  # 前提自检：折线档
        assert browser._channels[0]["curve"].opts["connect"] == "all"

    def test_dense_window_switches_to_envelope_pairs(self, browser):
        sf = browser.rec.raw.info["sfreq"]
        dur = browser.rec.meta.duration_s
        w = min(dur, 4 * self._max_points(browser) / sf)  # ≫ 阈值（clamp 到全长）
        browser._set_window_s(w)
        browser._refresh_data()
        t0, t1 = browser._visible_range()
        assert (t1 - t0) * sf > self._max_points(browser)  # 前提自检：包络档
        assert browser._channels[0]["curve"].opts["connect"] == "pairs"


class TestOffsetRobustDisplay:
    """M6.7b 行居中修复：DC 耦合数据（数万 µV 直流偏移）不再"空白 tab".

    根因复现形态 = clinicaldata：CH1-4 真信号骑在几万 µV 直流上、CH5-8
    饱和平线（±375000 µV）。旧版按绝对值堆叠 + y 轴锁定 → 曲线全部画在
    yRange 外（工具栏/标签/网格照常画，用户看到的是"加载成功的空白"）。
    """

    @pytest.fixture()
    def offset_browser(self, offset_browser_mod):
        """兼容层：M6.8 把夹具提为模块级（TestDcToggle 共用），类内名字保留."""
        return offset_browser_mod

    def test_every_channel_body_inside_locked_yrange(self, offset_browser):
        """每通道显示中位数必须落在锁定 yRange 内（空白 tab 的直接回归）."""
        view = offset_browser
        y0, y1 = view._plot.getViewBox().viewRange()[1]
        margin = 0.05 * (y1 - y0)
        for ch in view._channels:
            y = ch["curve"].yData
            assert y is not None and len(y) > 0, f"{ch['name']} 无曲线数据"
            med = float(np.median(y))
            assert y0 - margin <= med <= y1 + margin, (
                f"{ch['name']} 显示中位数 {med:.0f} µV 在 yRange [{y0:.0f}, {y1:.0f}] 外"
                " —— 曲线画到了视野外（M6.7b 前的空白 tab 形态）"
            )

    def test_spacing_ignores_flat_saturated_channels(self, offset_browser):
        """间距只按有交流起伏的通道估计：5/8 平线不得把间距压塌到 0."""
        view = offset_browser
        data = view.rec.raw.get_data() * 1e6  # µV（与浏览器同口径）
        stds = np.median(np.abs(data - np.median(data, axis=1, keepdims=True)), axis=1)
        live = stds[stds > 0.01]
        assert len(live) == 3  # 前提自检：恰 3 条活通道
        assert view._spacing_uv == pytest.approx(float(np.median(live)) * 8.0, rel=0.05)

    def test_flat_channels_render_as_lines_at_own_rows(self, offset_browser):
        """饱和平线：显示为贴着自己行的平线（而不是视野外的 375000µV）."""
        view = offset_browser
        y0, y1 = view._plot.getViewBox().viewRange()[1]
        for ch in view._channels[3:]:  # CH4-CH8 全平
            y = ch["curve"].yData
            assert float(np.ptp(y)) < 1e-6  # 平线本身仍是平的（未造假波动）
            assert abs(float(np.median(y)) - ch["idx"] * view._spacing_uv) < 1.0

    def test_all_flat_recording_keeps_default_spacing(self, tmp_path, qtbot):
        """整条录制全平（TPDJ-位置1 形态）：间距保持默认 100µV，不塌缩."""
        mne = pytest.importorskip("mne")
        n_channels, n_times = 8, 2500
        data = np.full((n_channels, n_times), 0.375)
        info = mne.create_info(
            ch_names=[f"CH{i + 1}" for i in range(n_channels)], sfreq=250.0, ch_types="eeg"
        )
        raw = mne.io.RawArray(data, info, verbose="ERROR")
        fif = tmp_path / "allflat.fif"
        raw.save(fif, overwrite=True, verbose="ERROR")
        rec = open_file(fif)
        view = SignalBrowserView(rec)
        qtbot.addWidget(view)
        qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
        view._refresh_data()
        try:
            assert view._spacing_uv == 100.0  # 全平 → 不覆盖默认值
            y0, y1 = view._plot.getViewBox().viewRange()[1]
            assert (y1 - y0) > 500  # yRange 未塌缩
            for ch in view._channels:  # 平线各自贴行可见
                med = float(np.median(ch["curve"].yData))
                assert y0 <= med <= y1
        finally:
            view.teardown()
            rec.unload()


class TestMinMaxDecimateValues:
    """minmax_decimate 数值正确性回归（M6.7b）.

    旧版 ``v_max = t[rows, i_max]``（单字符笔误，随 M6.6 提交潜伏）——
    包络的 max 点全变成时间戳（~0-10 的小值），上半包络塌到 0 附近：
    常数通道显示为锯齿而非平线、密集窗口呈"从真实值直落到 0"的密集
    竖线带。connect 标志的旧测试抓不到这种数值级退化，这里按值断言。
    """

    def test_constant_input_stays_constant(self):
        from dataloadv.ui.widgets.signal_browser import minmax_decimate

        n = 2500
        t = np.arange(n) / 250.0
        v = np.full(n, 375010.0)  # 饱和平线（clinicaldata CH5-8 形态）
        ot, ov = minmax_decimate(t, v, 300)
        assert len(ot) == len(ov) > 0
        assert np.all(ov == 375010.0)  # 平线进、平线出（绝不能混入时间戳）
        assert np.median(ot) >= 0  # 时间轴本身也未被数值污染

    def test_pairs_preserve_bucket_min_max(self):
        from dataloadv.ui.widgets.signal_browser import minmax_decimate

        n = 2500
        t = np.arange(n) / 250.0
        # 周期取 16 样本 = 桶宽（250/16 Hz）：每桶恰一整周期，必含全局极值，
        # 极值覆盖可作精确断言（相位不齐的正弦只能容忍到半桶相位差）
        v = 50000.0 + 100.0 * np.sin(2 * np.pi * (250.0 / 16.0) * t)  # 带直流的正弦
        ot, ov = minmax_decimate(t, v, 300)
        pairs_v = ov.reshape(-1, 2)
        pairs_t = ot.reshape(-1, 2)
        # 每对按时间序（先早后晚）——包络竖线方向一致的契约
        assert np.all(pairs_t[:, 1] >= pairs_t[:, 0] - 1e-12)
        # 值必须全部来自真实数据范围（时间戳泄漏会混入 ~0-10 的小值）
        assert pairs_v.min() > 40000.0
        assert pairs_v.min() >= v.min() - 1e-9 and pairs_v.max() <= v.max() + 1e-9
        # 全体包络的极值必须覆盖原信号极值（峰值抽取的本职）
        assert abs(pairs_v.min() - v.min()) < 5.0 and abs(pairs_v.max() - v.max()) < 5.0


class TestStepSecond:
    """M6.8 ±1s 按钮：固定 1 秒步进（补充 0.9 屏翻屏的细分辨率）."""

    def test_step_s_moves_exactly_one_second(self, browser):
        browser._go_edge(first=True)
        browser._step_s(+1)
        t0, t1 = browser._visible_range()
        assert abs(t0 - 1.0) < 1e-6
        w0 = browser._visible_range()[1] - t0
        assert abs((t1 - t0) - w0) < 1e-6  # 宽度不变

    def test_step_s_clamps_at_edges(self, browser):
        browser._go_edge(first=False)
        dur = browser.rec.meta.duration_s
        for _ in range(3):
            browser._step_s(+1)
        t0, t1 = browser._visible_range()
        assert abs(t1 - dur) < 1e-3  # 停在最末，不越界

    def test_buttons_wired(self, browser):
        browser._go_edge(first=True)
        browser._btn_next_s.click()
        assert abs(browser._visible_range()[0] - 1.0) < 1e-6
        browser._btn_prev_s.click()
        assert abs(browser._visible_range()[0]) < 1e-6


class TestGainInput:
    """M6.8 增益输入框：精确倍率权威源 + 三入口统一.

    两个被回归的坑：①滑杆真实范围是 0.01×–100×（10^(±20/10)，旧注释/手册
    写的 0.1×–10× 是错的）——输入框两端必须覆盖，否则滑杆拉满时双向脱钩；
    ②键盘 ↑↓ 曾走 slider.setValue(int)，会把输入框设的小数增益取整抹掉
    （2.5× 一键跳到 10×）。
    """

    def test_spin_is_authoritative(self, browser):
        ch0 = browser._channels[0]  # idx=0：居中模式下基线项=0，幅度可直接读
        base_ptp = float(np.ptp(ch0["curve"].yData))
        browser._gain_spin.setValue(2.5)
        assert browser._gain_scale() == pytest.approx(2.5)
        amp_ptp = float(np.ptp(ch0["curve"].yData))
        assert abs(amp_ptp / base_ptp - 2.5) < 1e-6

    def test_slider_spin_two_way_sync(self, browser):
        browser._gain_slider.setValue(10)
        assert browser._gain_spin.value() == pytest.approx(10.0)
        assert browser._gain_scale() == pytest.approx(10.0)
        browser._gain_spin.setValue(0.05)
        assert browser._gain_slider.value() == round(10 * math.log10(0.05))

    def test_keyboard_preserves_fraction(self, browser):
        browser._gain_spin.setValue(2.5)
        browser.keyPressEvent(_FakeKey(Qt.Key.Key_Up))
        assert browser._gain_scale() == pytest.approx(2.5 * 10 ** 0.1)  # +1.0 dB×10
        browser.keyPressEvent(_FakeKey(Qt.Key.Key_Down))
        assert browser._gain_scale() == pytest.approx(2.5)

    def test_range_covers_slider_both_ends(self, browser):
        browser._gain_slider.setValue(-20)
        assert browser._gain_spin.value() == pytest.approx(0.01)
        browser._gain_slider.setValue(20)
        assert browser._gain_spin.value() == pytest.approx(100.0)


class TestDcToggle:
    """M6.8 行居中开关：默认开（M6.7b 行为）；关=绝对电平 + y 自适配."""

    def test_default_centered_row_alignment(self, offset_browser_mod):
        """默认勾选 = M6.7b 行为不变的哨兵：CH1 显示中位 ≈ 行 0."""
        view = offset_browser_mod
        assert view._center_cb.isChecked()
        med = float(np.median(view._channels[0]["curve"].yData))
        assert abs(med - 0.0) < 1.0  # 行 0 中心（µV 级容差）

    def test_absolute_mode_shows_raw_level(self, offset_browser_mod):
        """关闭行居中：显示值 = 原始电平（CH1 ≈ +50000 µV 直流上）."""
        view = offset_browser_mod
        view._center_cb.setChecked(False)
        view._refresh_data()
        med = float(np.median(view._channels[0]["curve"].yData))
        assert med == pytest.approx(50e3, rel=1e-3)  # gain=1，+50mV 偏移

    def test_absolute_mode_yrange_fits_data(self, offset_browser_mod):
        """绝对模式 y 自适配：曲线中位必须落在 yRange 内（"空白"镜像回归）."""
        view = offset_browser_mod
        view._center_cb.setChecked(False)
        view._refresh_data()
        y0, y1 = view._plot.getViewBox().viewRange()[1]
        for ch in view._channels:
            med = float(np.median(ch["curve"].yData))
            assert y0 <= med <= y1, f"{ch['name']} 绝对电平 {med:.0f} 出界"

    def test_toggle_roundtrip_restores_rows(self, offset_browser_mod):
        """关→开：行对齐与堆叠 yRange 完全恢复."""
        view = offset_browser_mod
        view._center_cb.setChecked(False)
        view._refresh_data()
        view._center_cb.setChecked(True)
        view._refresh_data()
        med = float(np.median(view._channels[0]["curve"].yData))
        assert abs(med) < 1.0
        y0, y1 = view._plot.getViewBox().viewRange()[1]
        n = len(view._channels)
        s = view._spacing_uv
        assert y0 == pytest.approx(-1.5 * s, rel=1e-3)
        assert y1 == pytest.approx((n + 0.5) * s, rel=1e-3)

    def test_absolute_label_follows_median(self, offset_browser_mod):
        """绝对模式行标签贴曲线中位（行结构让位后标签是唯一行标识）."""
        view = offset_browser_mod
        view._center_cb.setChecked(False)
        view._refresh_data()
        label_y = view._channels[0]["label"].pos().y()
        assert label_y == pytest.approx(50e3, rel=0.05)


class TestChannelOffsets:
    """M6.8 通道列表直流偏移显示 + UserRole 名称迁移."""

    def test_offset_text_appears(self, offset_browser_mod, qtbot):
        view = offset_browser_mod
        qtbot.waitUntil(
            lambda: "µV" in view._ch_list.item(0).text(), timeout=10000
        )
        txt = view._ch_list.item(0).text()
        assert txt.startswith("CH1") and "+50.0k" in txt  # 50mV → +50.0k µV

    def test_userrole_preserves_name(self, offset_browser_mod):
        view = offset_browser_mod
        item = view._ch_list.item(0)
        assert item.data(Qt.ItemDataRole.UserRole) == view.rec.meta.channel_names[0]
        # 坏道标记按名字往返（右键菜单的取值路径）
        name = item.data(Qt.ItemDataRole.UserRole)
        view.toggle_bad(name)
        assert name in view.current_bads()
        view.toggle_bad(name)
        assert name not in view.current_bads()

    def test_fmt_offset_units(self):
        assert _fmt_offset_uv(375000.0) == "+375.0k"
        assert _fmt_offset_uv(5.2e6) == "+5.20M"
        assert _fmt_offset_uv(12.3) == "+12.3"
        assert _fmt_offset_uv(-4500.0) == "-4.5k"


class TestOverviewLane:
    """M6.8 总览时间轴滑块（event_lane 首个测试）：x 锁定 + 双向联动 + 防回环."""

    def test_lane_x_locked_to_duration(self, browser):
        lane = browser._lane
        vb = lane.getViewBox()
        dur = browser.rec.meta.duration_s
        x0, x1 = vb.viewRange()[0]
        assert abs(x0) < 1e-6 and abs(x1 - dur) < 1e-3
        assert tuple(vb.state["mouseEnabled"]) == (False, False)  # 不许拖走自己

    def test_set_viewport_positions_region(self, browser):
        browser._lane.set_viewport(10.0, 15.0)
        r = browser._lane._region.getRegion()
        assert r[0] == pytest.approx(10.0, abs=1e-9)
        assert r[1] == pytest.approx(15.0, abs=1e-9)

    def test_region_drag_moves_main_view(self, browser, qtbot):
        browser._set_x_range(15.0, 25.0)  # 先同步 region（宽 10）
        browser._lane._region.setRegion((20.0, 30.0))  # 模拟用户拖滑块（同宽）
        qtbot.waitUntil(
            lambda: abs(browser._visible_range()[0] - 20.0) < 1e-3, timeout=2000
        )
        t0, t1 = browser._visible_range()
        assert abs(t1 - 30.0) < 1e-3

    def test_region_drag_preserves_window_width(self, browser, qtbot):
        """拖出界被 bounds 压窄（瞬时错宽）不得改掉一屏时长（中心重锚）."""
        browser._set_x_range(15.0, 25.0)
        w0 = browser._visible_range()[1] - browser._visible_range()[0]
        browser._lane._region.setRegion((20.0, 80.0))  # 故意错宽 60s
        qtbot.wait(50)
        w1 = browser._visible_range()[1] - browser._visible_range()[0]
        assert abs(w1 - w0) < 1e-3  # 主图宽度纹丝不动

    def test_main_view_reflects_to_region(self, browser):
        browser._page(+1)
        r = browser._lane._region.getRegion()
        t0, t1 = browser._visible_range()
        assert r[0] == pytest.approx(t0, abs=1e-3)
        assert r[1] == pytest.approx(t1, abs=1e-3)

    def test_no_echo_loop_on_writeback(self, browser, qtbot):
        """主图回写路径（值相同早退 + _syncing）不得再外发 viewport_moved."""
        calls: list[tuple] = []
        browser._lane.viewport_moved.connect(lambda *a: calls.append(a))
        browser._set_x_range(30.0, 35.0)
        qtbot.wait(50)
        assert calls == []
        browser._page(+1)  # 翻屏也走回写
        qtbot.wait(50)
        assert calls == []

    def test_none_events_uses_strings(self, qtbot):
        """无事件图例用文案常量（不再硬编码中文）."""
        import pyqtgraph as pg

        gfx = pg.GraphicsLayoutWidget()
        lane = EventLane()
        gfx.addItem(lane, 0, 0)
        qtbot.addWidget(gfx)
        lane.set_events(EventTable(), 10.0)
        assert lane._legend_item.toPlainText() == S.EVENT_LANE_NONE
