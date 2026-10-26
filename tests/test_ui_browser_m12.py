"""M12 浏览器四项改造：比例尺下拉 / 紧凑显示 / 三行对齐 / 同段时频图.

夹具：browser（FIF 真路径，synthetic_raw = 8 导/250Hz/60s，ch0=10Hz 20µV
正弦 + 5µV 噪底、ch1 另有 50Hz（在默认 2–45Hz 外）、ch2-7 纯噪声；
T0/T1/T2@10/20/30s）——与 test_ui_browser_m6 同款。

TFR 等待范式（坑 #55④）：waitUntil(not _tfr_running) + waitUntil(not
_keepalive)（workers/generic 模块级容器清空 = 线程链收完的本质判据）。
"""

from __future__ import annotations

import time

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from PySide6.QtCore import Qt  # noqa: E402

from dataloadv.features.tfr import default_tfr_freqs  # noqa: E402
from dataloadv.ui.strings_zh import S  # noqa: E402
from dataloadv.workers.generic import _keepalive as _KA_THREADS  # noqa: E402


def _poll_until(qtbot, cond, what: str, timeout_s: float = 15.0) -> None:
    """Python 层 deadline 轮询等待（防挂死兜底）.

    qtbot.waitUntil 的超时检查在 Qt 事件循环侧——事件分发被饿死时超时本身
    也不触发 → 永等挂死（2026-10-13 全量 Heisenbug，系统高负载下 ~50% 复
    现，挂点集中在 TFR 等待；观测手段 -s/faulthandler 一介入就绿）。
    本函数条件与超时都在 Python 层：最坏 timeout_s 后明确 FAIL 可见。
    """
    deadline = time.monotonic() + timeout_s
    while not cond():
        if time.monotonic() > deadline:
            pytest.fail(f"轮询超时（{timeout_s}s）：{what}")
        qtbot.wait(50)


@pytest.fixture()
def browser(tmp_path, qtbot, synthetic_raw):
    """FIF 往返 → open_file → 浏览器（等首帧；TFR 防抖 300ms 后算完）.

    等待一律走 _poll_until（Python 层 deadline）——qtbot.waitUntil 内部是
    QEventLoop.exec + QTimer 超时，事件分发被饿死时超时本身失效 → 永等
    挂死（2026-10-13 全量 Heisenbug 根因，见 _poll_until docstring）。
    """
    from dataloadv.io.registry import open_file
    from dataloadv.ui.widgets.signal_browser import SignalBrowserView

    fif = tmp_path / "synth.fif"
    synthetic_raw.save(fif, overwrite=True, verbose="ERROR")
    rec = open_file(fif)
    view = SignalBrowserView(rec)
    qtbot.addWidget(view)
    _poll_until(qtbot, lambda: view._loaded_once, "浏览器首帧加载")
    view._refresh_data()
    _wait_tfr(view, qtbot)
    yield view
    view.teardown()
    rec.unload()


def _wait_tfr(view, qtbot, done=None) -> None:
    """等时频计算链收完：防抖到期 → 后台算完 → 线程链回收（keepalive 清空
    = on_done 已在主线程执行完）.

    ``done`` 可传业务终态谓词（默认 None 只等链收完）——比等 timer 内部状态
    稳：_set_x_range 路径有 30ms refresh 防抖窗口，timer 尚未 start 时
    ``not isActive()`` 恒真会提前退出；一律等业务条件（_poll_until 见其
    docstring——Python 层超时防挂死）。
    """
    if done is not None:
        _poll_until(qtbot, done, "TFR 业务终态")
    _poll_until(
        qtbot,
        lambda: not view._tfr_timer.isActive() and not view._tfr_running
        and not _KA_THREADS,
        "TFR 计算链收尾",
    )


class TestScaleCombo:
    """比例尺下拉（M12a）：固定行距 / 自动重估 / 与增益正交."""

    def test_fixed_value_locks_spacing(self, browser):
        s = browser._spacing_uv  # 自动估计值（首帧 MAD×8）
        browser._scale_combo.setCurrentText("50")
        assert browser._spacing_uv == 50.0
        assert browser._spacing_estimated  # 锁定后首帧估计不再覆盖
        y0, y1 = browser._plot.getViewBox().viewRange()[1]
        assert y0 == pytest.approx(-1.5 * 50.0)
        assert y1 == pytest.approx(8.5 * 50.0)  # n=8：(-1.5, n+0.5)×s
        assert s != 50.0  # 前提自检：原估计值确非 50（合成数据 MAD×8 量级 ~40）

    def test_back_to_auto_reestimates(self, browser, qtbot):
        browser._scale_combo.setCurrentText("500")
        browser._set_x_range(20.0, 30.0)  # 换一个窗口供重估
        browser._scale_combo.setCurrentText(S.SCALE_AUTO)
        _poll_until(qtbot, lambda: browser._spacing_estimated, "比例尺自动重估")
        # 重估口径与首帧一致：当前窗口数据 live MAD×8（test_ui_browser_m6 L321 范式）
        t0, t1 = browser._visible_range()
        data, _ = browser.rec.get_window(t0, t1, None)
        data_uv = data * 1e6
        stds = np.median(np.abs(data_uv - np.median(data_uv, axis=1, keepdims=True)), axis=1)
        live = stds[stds > 0.01]
        expect = float(np.median(live)) * 8.0
        assert browser._spacing_uv == pytest.approx(expect, rel=0.05)

    def test_orthogonal_to_gain(self, browser):
        browser._scale_combo.setCurrentText("50")
        y_before = browser._plot.getViewBox().viewRange()[1]
        browser._set_gain(10.0)  # +10 dB×10 = 10×
        assert browser._spacing_uv == 50.0  # 行距纹丝不动
        assert browser._plot.getViewBox().viewRange()[1] == y_before


class TestCompactDisplay:
    """紧凑显示（M12c）：紧凑重排 / 即时收缩 / 复位 / 默认留空位回归."""

    @staticmethod
    def _leave(view, keep: list[int]) -> None:
        """只勾 keep 指定通道（blockSignals 防连发，改完刷一帧）."""
        view._ch_list.blockSignals(True)
        try:
            for i in range(view._ch_list.count()):
                st = (Qt.CheckState.Checked if i in keep
                      else Qt.CheckState.Unchecked)
                view._ch_list.item(i).setCheckState(st)
        finally:
            view._ch_list.blockSignals(False)
        for ch in view._channels:
            on = ch["idx"] in keep
            ch["enabled"] = on
            ch["curve"].setVisible(on)
            ch["label"].setVisible(on)
        view._refresh_data()

    def test_compact_repacks_rows(self, browser):
        self._leave(browser, [0, 3, 5])
        browser._set_compact(True)
        # 自动档下 spacing 随勾选集持续重估（M15）——断言前重读当前值，
        # 不捕获改勾选前的旧值
        s = browser._spacing_uv
        y0, y1 = browser._plot.getViewBox().viewRange()[1]
        assert y0 == pytest.approx(-1.5 * s, rel=1e-6)
        assert y1 == pytest.approx(3.5 * s, rel=1e-6)  # n=勾选数 3
        # 首通道贴 0 行、第三通道（原 idx5）贴 2 行（紧凑不留空位）；容差
        # 1µV——曲线 yData 是 min-max 抽取后的 (min,max) 对序列，中位数相对
        # 原始中位数有亚 µV 偏移（M6.6 平线贴行断言同款口径）
        assert float(np.median(browser._channels[0]["curve"].yData)) == pytest.approx(0.0, abs=1.0)
        assert float(np.median(browser._channels[5]["curve"].yData)) == pytest.approx(2 * s, abs=1.0)

    def test_toggle_while_compact_repacks(self, browser):
        browser._set_compact(True)
        self._leave(browser, [0, 3, 5])
        self._leave(browser, [3, 5])  # 紧凑下再关一个——即时收缩，无需再点按钮
        assert browser._row_count() == 2
        assert browser._row_of(browser._channels[3]) == 0  # 原第 2 勾选升为 0 行

    def test_reset_restores_all(self, browser):
        self._leave(browser, [1, 2])
        browser._set_compact(True)
        browser._set_compact(False)  # 复位
        assert all(c["enabled"] for c in browser._channels)
        assert all(browser._ch_list.item(i).checkState() == Qt.CheckState.Checked
                   for i in range(browser._ch_list.count()))
        s = browser._spacing_uv
        y0, y1 = browser._plot.getViewBox().viewRange()[1]
        assert y0 == pytest.approx(-1.5 * s) and y1 == pytest.approx(8.5 * s)
        # 末通道回原 7 行（留空位语义；抽取中位偏差容差同上）
        assert float(np.median(browser._channels[7]["curve"].yData)) == pytest.approx(7 * s, abs=1.0)

    def test_default_keeps_gaps(self, browser):
        """默认非紧凑：只留末通道仍贴原 7 行（既有留空位语义回归哨兵）."""
        s = browser._spacing_uv
        self._leave(browser, [7])
        browser._refresh_data()
        assert float(np.median(browser._channels[7]["curve"].yData)) == pytest.approx(7 * s, abs=1.0)


class TestTfrAlignment:
    """三行 gfx 布局与 setXLink 像素对齐（M12d）."""

    def test_rows_share_data_geometry(self, browser):
        """三行绘图区（vb 数据区）屏幕几何左右缘一致（像素对齐的充要条件）."""
        vbs = [browser._plot.vb, browser._tfr_plot.vb, browser._lane.vb]
        rects = [vb.mapRectToScene(vb.boundingRect()) for vb in vbs]
        for r in rects:
            assert r.width() > 0
        assert rects[0].left() == pytest.approx(rects[1].left(), abs=0.6)
        assert rects[0].right() == pytest.approx(rects[1].right(), abs=0.6)

    def test_x_range_follows_main(self, browser):
        browser._set_x_range(20.0, 30.0)
        tfr_x = browser._tfr_plot.vb.viewRange()[0]
        assert tfr_x[0] == pytest.approx(20.0, abs=1e-6)
        assert tfr_x[1] == pytest.approx(30.0, abs=1e-6)

    def test_left_axes_uniform_empty(self, browser):
        from dataloadv.ui.widgets.event_lane import ROW_AXIS_W

        # _tickLevels 三态（坑 #57①）：setTicks([]) 自定义空刻度=[]；
        # 从未自定义的自动刻度系统=None。主图/事件条=空刻度；TFR=自动频率刻度
        assert browser._plot.getAxis("left")._tickLevels == []
        assert browser._lane.getAxis("left")._tickLevels == []
        assert browser._tfr_plot.getAxis("left")._tickLevels is None
        for p in (browser._plot, browser._tfr_plot, browser._lane):
            assert p.getAxis("left").width() == ROW_AXIS_W


class TestBrowserTfr:
    """同段时频图（M12e）：计算回填 / 频率形态 / 短窗占位 / teardown 竞态."""

    def test_image_and_lut_present(self, browser, qtbot):
        img = browser._tfr_img
        assert img.image is not None  # 已回填
        t0, t1 = browser._visible_range()
        # boundingRect 是像素坐标，setRect 的数据域映射须 mapRectToView
        # （坑 #55① 同款口径）
        r = img.mapRectToView(img.boundingRect())
        # 容差 = 采样间隔量级：get_window 的 times 端点按采样对齐（含端点差
        # 1 样本 = 4ms@250Hz），rect 覆盖 [times[0], times[-1]]
        assert r.left() == pytest.approx(t0, abs=0.02)
        assert r.width() == pytest.approx(t1 - t0, abs=0.02)
        # turbo 色标+直方图已挂进 scene，且自动范围已按数据设置
        assert browser._tfr_lut.scene() is not None
        lo, hi = browser._tfr_img.getLevels()
        assert lo == pytest.approx(float(img.image.min()), abs=1e-4)
        assert hi == pytest.approx(float(img.image.max()), abs=1e-4)

    def test_levels_locked_across_pages(self, browser, qtbot):
        """用户拖过范围后跨屏保持；双击色标恢复自动."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent

        browser._tfr_lut.setLevels(-5.0, -1.0)  # 模拟用户拖动后的范围
        browser._set_x_range(30.0, 40.0)  # 翻屏（数据范围不同）
        # 直接等终态（_set_x_range 经 30ms refresh 防抖才 schedule TFR——通用
        # _wait_tfr 在该窗口内会提前退出）
        _poll_until(qtbot, lambda: browser._tfr_levels_locked, "范围锁定")
        _poll_until(qtbot, lambda: not _KA_THREADS, "锁定轮收尾")
        assert tuple(browser._tfr_img.getLevels()) == pytest.approx((-5.0, -1.0))
        # 双击色标 → 解锁 + 按当前图重设
        ev = QMouseEvent(QEvent.Type.GraphicsSceneMouseDoubleClick, QPointF(0, 0),
                         QPointF(0, 0), Qt.MouseButton.LeftButton,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        assert browser.eventFilter(browser._tfr_lut, ev) is True
        assert not browser._tfr_levels_locked
        lo, hi = browser._tfr_img.getLevels()
        assert lo == pytest.approx(float(browser._tfr_img.image.min()), abs=1e-4)
        assert hi == pytest.approx(float(browser._tfr_img.image.max()), abs=1e-4)

    def test_gradient_editor_not_interactive(self, browser, qtbot):
        """渐变编辑器鼠标全被吃掉（三角切分点不会再被拖出）."""
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtGui import QMouseEvent

        def _press():
            return QMouseEvent(QEvent.Type.GraphicsSceneMousePress, QPointF(0, 0),
                               QPointF(0, 0), Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier)

        assert browser.eventFilter(browser._tfr_lut.gradient, _press()) is True

    def test_alpha_peak_in_tfr(self, browser, qtbot):
        """ch0（10Hz 正弦）时频在 ~10Hz 显著高于 ~30Hz；纯噪声通道无此差异."""
        freqs = browser._tfr_freqs
        row10 = int(np.argmin(np.abs(freqs - 10.0)))
        row30 = int(np.argmin(np.abs(freqs - 30.0)))
        db = browser._tfr_img.image.T  # 转回 [n_freq, n_times]
        d_ch0 = float(np.mean(db[row10])) - float(np.mean(db[row30]))
        assert d_ch0 > 6.0  # dB 差（10Hz 正弦 20µV vs 5µV 噪底）
        browser._tfr_ch_combo.setCurrentIndex(2)  # 纯噪声通道
        _wait_tfr(browser, qtbot)
        db2 = browser._tfr_img.image.T
        d_ch2 = float(np.mean(db2[row10])) - float(np.mean(db2[row30]))
        assert abs(d_ch2) < 3.0

    def test_short_window_placeholder(self, browser, qtbot):
        browser._set_window_s(1.0)  # 一屏 1s（< 默认 morlet 2s 下限）
        _poll_until(qtbot,
                    lambda: browser._tfr_hint.isVisible()
                    and browser._tfr_hint.toPlainText()
                    == S.BROWSER_TFR_SHORT.format(t=2.0),
                    "短窗占位")

    def test_teardown_during_compute(self, browser, qtbot, tmp_path):
        """触发计算后立即 teardown：代币作废 + 不炸（关 tab 竞态兜底）."""
        browser._set_x_range(5.0, 25.0)
        browser._schedule_tfr()
        browser.teardown()
        _poll_until(qtbot, lambda: not _KA_THREADS, "teardown 竞态线程回收")

    def test_channel_switch_bumps_seq(self, browser, qtbot):
        before = browser._tfr_seq
        browser._tfr_ch_combo.setCurrentIndex(4)
        # 等"新请求已发起且已算完"的业务终态（seq 递增）——不轮询 timer 内部
        # 状态（本用例是 2026-10-13 全量挂死 Heisenbug 的集中挂点；等待走
        # Python 层 deadline 轮询，最坏 15s 明确 FAIL 而非永挂）
        _poll_until(qtbot, lambda: browser._tfr_seq > before, "通道切换触发计算")
        _poll_until(qtbot, lambda: not browser._tfr_running and not _KA_THREADS,
                    "通道切换计算收尾")


class TestTfrM13:
    """M13：频率轴翻转（低频在下）/ 150Hz 钳制 / 设置对话框流程."""

    def test_low_freq_at_bottom(self, browser):
        """低频数据映射到屏幕更下方（用户要求的朝向；旧 invertY 是高频在下）."""
        from PySide6.QtCore import QPointF

        vb = browser._tfr_plot.vb
        lo = vb.mapFromView(QPointF(0, 10.0)).y()   # 低频像素 y
        hi = vb.mapFromView(QPointF(0, 100.0)).y()  # 高频像素 y
        assert lo > hi  # 像素 y 大 = 屏幕下方

    def test_fmax_clamped_to_nyquist(self, browser):
        """250Hz 采样 → 频率上限 122.5（Nyquist×0.49——150 硬顶已放开）."""
        y0, y1 = browser._tfr_plot.vb.viewRange()[1]
        assert y0 == pytest.approx(0.0, abs=1e-9)      # 频率轴含 0 起点
        assert y1 == pytest.approx(122.5, abs=1e-6)

    def test_stft_uses_absolute_time(self, browser, qtbot):
        """stft 热图 rect 用绝对时间（回归哨兵：scipy t 是相对窗口的 0 起轴，
        窗口在 [30,40] 时旧版画到 0-10s 视口外=「图没加载」——2026-10-14
        用户真窗口实测暴露，离屏默认 [0,10] 窗口碰巧撞对）."""
        browser._tfr_cfg = type(browser._tfr_cfg)(method="stft")
        seq0 = browser._tfr_seq
        browser._set_x_range(30.0, 40.0)
        # 等"新请求已发起"的业务终态——_set_x_range 路径有 30ms refresh 防抖
        # + 300ms TFR 防抖两级窗口，期间 timer 未 start/running 未置位，任何
        # "未在跑"的负向条件都会提前满足（防抖窗口陷阱，坑 #64⑤ 同型）
        _poll_until(qtbot, lambda: browser._tfr_seq > seq0, "stft 新计算发起")
        _poll_until(qtbot, lambda: not browser._tfr_running and not _KA_THREADS,
                    "stft 中窗计算收尾")
        assert browser._tfr_img.image is not None
        r = browser._tfr_img.mapRectToView(browser._tfr_img.boundingRect())
        assert r.left() == pytest.approx(30.0, abs=0.05)

    def test_settings_dialog_applies_config(self, browser, qtbot, monkeypatch):
        """设置对话框：改方法+参数 → 确定后 cfg 更新并触发重算."""
        from dataloadv.ui.dialogs.tfr_settings_dialog import TfrSettingsDialog

        before_seq = browser._tfr_seq
        dlg = TfrSettingsDialog(browser._tfr_cfg, browser.rec.meta.sfreq)
        qtbot.addWidget(dlg)
        dlg._method.setCurrentIndex(3)  # stft
        dlg._win.setValue(1.0)
        dlg._fmin.setValue(1.0)
        dlg._on_save()
        assert dlg.result() == TfrSettingsDialog.DialogCode.Accepted
        cfg = dlg.config()
        assert cfg.method == "stft" and cfg.win_s == 1.0 and cfg.fmin == 1.0

        # 应用到浏览器（走 _open_tfr_settings 的应用段——对话框已 accept）
        browser._tfr_cfg = cfg
        fmax = cfg.effective_fmax(browser.rec.meta.sfreq)
        browser._tfr_freqs = default_tfr_freqs(cfg.fmin, fmax, cfg.n_freqs)
        browser._schedule_tfr()
        _poll_until(qtbot, lambda: browser._tfr_seq > before_seq, "设置后重算触发")
        _poll_until(qtbot, lambda: not browser._tfr_running and not _KA_THREADS,
                    "设置后计算收尾")
        # stft 结果已回填（时间点数 = 窗中心数 ≪ 原始采样点数）
        assert browser._tfr_img.image is not None
        assert browser._tfr_img.image.shape[0] < 100  # n_times'（窗中心）


class TestToggleAllChannels:
    """M15：全选/全不选切换按钮."""

    def test_toggle_roundtrip(self, browser):
        assert all(c["enabled"] for c in browser._channels)
        browser._toggle_all_channels()  # 全勾 → 全不勾
        assert not any(c["enabled"] for c in browser._channels)
        assert not browser._channels[0]["curve"].isVisible()
        browser._toggle_all_channels()  # 非全勾 → 全勾
        assert all(c["enabled"] for c in browser._channels)
        assert browser._channels[0]["curve"].isVisible()
        # 部分勾选状态再点 → 全勾（"否则=全勾"语义）
        browser._ch_list.item(0).setCheckState(Qt.CheckState.Unchecked)
        browser._toggle_all_channels()
        assert all(c["enabled"] for c in browser._channels)


class TestAutoScaleTracksSelection:
    """M15：自动档按勾选通道的实际波动持续重估比例尺."""

    def test_selection_change_updates_spacing(self, browser):
        # synthetic：ch0/ch1=10Hz 20µV 正弦（大信号 MAD），ch2-7=5µV 噪底
        # ——8 通道的 MAD 中位数被 6 个噪声通道主导（≈噪声级）
        full = browser._spacing_uv
        # 只留大信号正弦通道 → 波动大 → spacing 显著大于全通道估计
        # （方向注意：全通道中位数=噪声级，纯噪声子集与它几乎相同——用
        # 大信号子集才能拉开差值）
        TestCompactDisplay._leave(browser, [0, 1])
        big = browser._spacing_uv
        assert big > full * 1.5
        # 固定档不受勾选影响
        browser._scale_combo.setCurrentText("50")
        TestCompactDisplay._leave(browser, [2, 3])
        assert browser._spacing_uv == 50.0
