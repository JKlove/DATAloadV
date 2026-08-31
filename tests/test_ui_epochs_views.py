"""M8 分段预览四视图 + M8.1（配色/缓存/单段浏览/Y 修复）测试（offscreen）.

覆盖 EpochsPreviewView 的视图切换矩阵：
- 默认=各通道平均（堆叠，M3 零回归）：曲线数 + 数值断言（均值+行偏移）
- ERP 蝶形：全通道同坐标 + 零线
- 单通道：12 段细线 + 按事件码分色平均（含事件后 α 的类间差异）
- 时频：后台线程算完 → ImageItem + 色标 + y 反转；切走后 LUT/反转复位
  （残留回归）；teardown 后迟到回调不炸
- M8.1：Y 残留修复（autoRange 铺满）；viridis/jet/hot 配色只换查找表不扰动
  levels；结果按通道缓存（切走切回零重算）；第五视图单段浏览（◀▶/段号框/边界 clamp）
"""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

import dataloadv.ui.widgets.epochs_preview as ep
from dataloadv.ui.strings_zh import S
from dataloadv.workers.generic import _keepalive as _KA_THREADS

SF = 100.0
ALPHA_UV = 30.0


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_epochs():
    """合成 12 段（left/right 交替）× 3 通道 [-1,2)s；left 段 C0 事件后叠 α."""
    import mne
    from mne import Epochs, annotations_from_events, create_info
    from mne.io import RawArray

    rng = np.random.default_rng(0)
    data = rng.normal(0, 10e-6, (3, 1400))
    events = np.column_stack([
        np.arange(100, 1201, 100), np.zeros(12, int), np.array([1, 2] * 6, int),
    ])
    raw = RawArray(data, create_info(["C1", "C2", "C3"], SF, "eeg"), verbose="ERROR")
    raw.set_annotations(annotations_from_events(events, SF, verbose="ERROR"))
    epochs = Epochs(raw, events, tmin=-1.0, tmax=2.0 - 1 / SF, baseline=None,
                    preload=True, verbose="ERROR")
    ed = epochs.get_data().copy()
    t = epochs.times
    for i in range(0, 12, 2):  # left 段（码 1）：事件后 C1 叠 α
        ed[i, 0, t >= 0] += ALPHA_UV * 1e-6 * np.sin(2 * np.pi * 10.0 * t[t >= 0])
    epochs._data[:, :, :] = ed
    return epochs, ed


@pytest.fixture()
def view(qapp, qtbot):
    from dataloadv.proc.context import ProcessingContext

    epochs, ed = _make_epochs()
    ctx = ProcessingContext(raw=None, stage="epochs")
    ctx.epochs = epochs
    w = ep.EpochsPreviewView(ctx, "test")
    qtbot.addWidget(w)
    w.resize(900, 600)
    yield w
    w.teardown()


def _wait_tfr(view, qtbot):
    """等时频后台线程落地 + 真收尾（keepalive 清空＝线程链走完 deleteLater）."""
    view._start_tfr()
    qtbot.waitUntil(lambda: not view._tfr_running, timeout=15000)
    qtbot.waitUntil(
        lambda: any(type(it).__name__ == "ImageItem" for it in view._plot.items),
        timeout=5000,
    )
    qtbot.waitUntil(lambda: not _KA_THREADS, timeout=15000)


class TestAvgView:
    def test_default_is_avg_stacked(self, view, qtbot):
        """默认视图=平均堆叠：3 曲线 + 第 2 条=通道均值(µV)+1×行偏移（数值断言）."""
        assert view._view_combo.currentText() == S.EP_VIEW_AVG
        items = view._plot.listDataItems()
        assert len(items) == 3
        assert not view._ch_combo.isEnabled()  # 堆叠视图不需要选通道
        _, ed = _make_epochs()
        exp1 = ed[:, 1, :].mean(axis=0) * 1e6
        spacing = float(np.median(np.abs(ed.mean(axis=0)).max(axis=-1) * 3e6))
        assert np.allclose(items[1].yData[: len(exp1)], exp1 + spacing, atol=0.5)

    def test_stacked_channel_labels_inline(self, view, qtbot):
        """M8.2：通道名行首内嵌（TextItem 8pt），y 轴无通道刻度（导联多时刻度必挤叠）."""
        texts = [it for it in view._plot.items if type(it).__name__ == "TextItem"]
        assert [t.toPlainText() for t in texts] == view._ch_names
        assert not view._plot.getAxis("left")._tickLevels  # 不走 y 轴刻度
        # 8pt 小字：预览 tab 矮窗口下默认字号标签盒高≥行距会相触（M8.2 离屏实测）
        # （TextItem 只暴露 setFont；取回走内部 QGraphicsTextItem）
        assert all(t.textItem.font().pointSizeF() == 8.0 for t in texts)


class TestButterflyView:
    def test_curves_and_zero_line(self, view, qtbot):
        """蝶形：3 曲线同坐标 + 零基准线 + y 不反转."""
        view._view_combo.setCurrentIndex(1)
        assert len(view._plot.listDataItems()) == 3
        assert any(type(it).__name__ == "InfiniteLine" for it in view._plot.items)
        assert not view._plot.vb.state["yInverted"]

    def test_butterfly_legend_and_hide_on_leave(self, view, qtbot):
        """M8.2：蝶形带图例（逐通道色=名字，矮窗口自动分列防裁断）；切走视图图例隐藏."""
        view._view_combo.setCurrentIndex(1)
        assert view._legend is not None
        assert len(view._legend.items) == 3  # 每通道一条
        assert view._legend.columnCount == 1  # 3 通道单列（每列至多 12 行；int 属性非方法）
        view._view_combo.setCurrentIndex(0)  # 切回堆叠
        assert len(view._legend.items) == 0 and not view._legend.isVisible()

    def test_butterfly_legend_columns_for_many_channels(self, view, qtbot):
        """25 通道 → 3 列（每列 ≤12 行，矮窗口单列 25 条排不到底被裁断——离屏实测）."""
        view._ch_names = [f"CH{i:02d}" for i in range(25)]
        # 数据同步扩到 25 通道（_draw_butterfly 按通道维取 avg[i]）
        view._data = np.concatenate([view._data] + [view._data[:, :1]] * 22, axis=1)
        view._view_combo.setCurrentIndex(1)
        assert len(view._legend.items) == 25
        assert view._legend.columnCount == 3


# --------------------------------------------- M8.2：行刻度不残留到其它视图
# --------------------------------------------- M8.2：行刻度不残留到其它视图
class TestAxisResidue:
    def test_stacked_ticks_not_left_on_tfr(self, view, qtbot):
        """单段浏览（曾设行刻度的堆叠系视图）→ 时频：左轴无通道名残留（左上角飘字回归）."""
        view._view_combo.setCurrentIndex(4)  # 单段浏览（_draw_stacked 路径）
        view._view_combo.setCurrentIndex(3)  # 时频
        _wait_tfr(view, qtbot)
        assert view._plot.vb.state["yInverted"]
        ticks = view._plot.getAxis("left")._tickLevels
        flat = [t for level in (ticks or []) for _, t in
                (level if isinstance(level, list) else [])]
        assert not any(t in view._ch_names for t in flat)  # 无自定义通道名刻度
        assert view._plot.getAxis("left")._tickLevels is None  # 频率=自动刻度系统


class TestSingleView:
    def test_segments_and_group_means(self, view, qtbot):
        """单通道：12 细线 + 2 平均粗线 + 2 码标注；含 α 的码平均幅度显著大."""
        view._view_combo.setCurrentIndex(2)
        assert view._ch_combo.isEnabled()
        lines = view._plot.listDataItems()
        texts = [it for it in view._plot.items if type(it).__name__ == "TextItem"]
        assert len(lines) == 14  # 12 段 + 2 平均
        assert len(texts) == 2
        # 平均线在细线之后追加（列表尾部两条）；α 只进 left 码 → ptp 差异显著
        ptp = [float(np.ptp(l.yData)) for l in lines[-2:]]
        assert max(ptp) > min(ptp) * 2.5
        # 曲线 x 轴=epochs.times（事件锚点坐标）
        assert np.allclose(lines[-1].xData, view._times)

    def test_channel_switch_redraws(self, view, qtbot):
        """换通道重画：C2（无 α）两平均线幅度接近（类间差异只剩噪声）."""
        view._view_combo.setCurrentIndex(2)
        view._ch_combo.setCurrentIndex(1)  # C2
        lines = view._plot.listDataItems()
        assert len(lines) == 14
        ptp = [float(np.ptp(l.yData)) for l in lines[-2:]]
        assert max(ptp) < min(ptp) * 2.5  # 无 α → 无大差异


class TestTfrView:
    def test_image_lut_invert(self, view, qtbot):
        """时频：后台算完 → ImageItem + 色标挂载 + y 反转（低频在下）."""
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        imgs = [it for it in view._plot.items if type(it).__name__ == "ImageItem"]
        assert len(imgs) == 1
        assert view._lut is not None
        assert view._plot.vb.state["yInverted"]
        assert "dB" in view._hint.text()
        # 像素格贴数据坐标：宽度=时间范围（3s），高度=频率范围（2-45Hz）
        rect = imgs[0].mapRectToView(imgs[0].boundingRect())
        assert rect.width() == pytest.approx(3.0, abs=0.05)
        assert rect.height() == pytest.approx(43.0, abs=0.5)

    def test_leave_tfr_resets(self, view, qtbot):
        """切走时频：色标摘除 + y 反转复位（残留回归）+ 蝶形重画."""
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        assert view._lut is not None
        view._view_combo.setCurrentIndex(1)
        assert view._lut is None
        assert not view._plot.vb.state["yInverted"]
        assert len(view._plot.listDataItems()) == 3

    def test_teardown_safe_for_late_callback(self, view, qtbot):
        """teardown 后迟到的 _draw_tfr：_data None 早退——不炸、不新画任何项."""
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        view.teardown()
        assert view._data is None and view.ctx is None
        n_before = len(view._plot.items)
        view._draw_tfr((np.arange(24.0), np.arange(3.0), np.zeros((24, 3))))
        assert len(view._plot.items) == n_before  # 早退：没有新 ImageItem/LUT
        view.teardown()  # 幂等：二次调用不崩

    def test_stale_result_does_not_overwrite(self, view, qtbot):
        """用户已切走视图后后台返回：丢弃结果（不覆盖当前视图）."""
        view._view_combo.setCurrentIndex(3)
        view._tfr_running = True  # 模拟计算中切走
        view._view_combo.setCurrentIndex(1)
        view._draw_tfr((np.arange(24.0), np.arange(3.0), np.zeros((24, 3))))
        assert all(type(it).__name__ != "ImageItem" for it in view._plot.items)
        assert len(view._plot.listDataItems()) == 3  # 蝶形还在
        # 等 setCurrentIndex(3) 启动的真线程完整收尾（防会话退出时 QThread 竞态）
        qtbot.waitUntil(lambda: not _KA_THREADS, timeout=15000)


# ------------------------------------------------------- M8.1：Y 修复 / 配色 / 缓存
class TestTfrYRange:
    def test_yrange_fills_after_butterfly(self, view, qtbot):
        """观感修复：蝶形的大 Y 范围（含负值）不残留到时频——autoRange 铺满 2-45Hz."""
        view._view_combo.setCurrentIndex(1)  # 蝶形：setYRange(-span, +span)
        by0, by1 = view._plot.vb.viewRange()[1]
        assert by0 < 0  # 蝶形 y 范围含负半轴（残留时低频起点会 < 0）
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        fy0, fy1 = view._plot.vb.viewRange()[1]
        assert -1 < fy0 < 2.5  # 低频贴 2Hz 起（autoRange 少量 padding；残留时=蝶形深负下界）
        assert 43 <= fy1 - fy0 < 60  # 频率跨度的自然范围（残留时被压/被撑）


class TestTfrCmap:
    def test_cmap_changes_lut_not_levels(self, view, qtbot):
        """切 jet：查找表首行变深蓝（viridis 首行紫绿）且 levels 逐位不变."""
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        img = next(it for it in view._plot.items if type(it).__name__ == "ImageItem")
        levels_before = img.getLevels()
        # img.lut 是 HistogramLUTItem.getLookupTable 的可调用引用（随 gradient 变），
        # 须显式取表物化成数组再比较
        lut_before = np.asarray(img.lut(n=256)).copy()
        view._cmap_combo.setCurrentText("jet")
        lut_after = np.asarray(img.lut(n=256))
        assert lut_after.shape == lut_before.shape
        assert not np.array_equal(lut_after, lut_before)  # 配色真的换了
        assert lut_after[0, 2] > lut_after[0, 0]  # jet 从深蓝起（b>r）
        assert lut_before[0, 0] > lut_before[0, 1]  # viridis 首行 [68,1,84]（r>g）
        assert np.array_equal(img.getLevels(), levels_before)  # 换色不扰动亮度映射

    def test_controls_enable_by_view(self, view, qtbot):
        """配色下拉仅时频启用；段号框/◀▶ 仅单段浏览启用；互不串台."""
        assert not view._cmap_combo.isEnabled()
        assert not view._seg_spin.isEnabled() and not view._btn_next.isEnabled()
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        assert view._cmap_combo.isEnabled()
        assert not view._seg_spin.isEnabled()
        view._view_combo.setCurrentIndex(4)
        assert view._seg_spin.isEnabled() and view._btn_prev.isEnabled()
        assert not view._cmap_combo.isEnabled()


class TestTfrCache:
    def test_cached_channel_skips_recompute(self, view, qtbot, monkeypatch):
        """切走再切回同一通道：缓存命中同步绘制，零线程零重算."""
        view._view_combo.setCurrentIndex(3)
        _wait_tfr(view, qtbot)
        calls = []

        def fake(*a, **k):  # 记录调用并返回合法小结果（不应被走到缓存命中的路径）
            calls.append(1)
            return (np.linspace(2.0, 45.0, 24), view._times,
                    np.zeros((24, len(view._times))))

        monkeypatch.setattr(ep, "compute_epochs_tfr", fake)
        view._view_combo.setCurrentIndex(1)  # 切走（蝶形）
        view._view_combo.setCurrentIndex(3)  # 切回：命中 ch0 缓存
        assert any(type(it).__name__ == "ImageItem" for it in view._plot.items)
        assert not calls  # 没进线程重算
        view._ch_combo.setCurrentIndex(1)  # 换 ch1：未命中 → 正常进线程
        qtbot.waitUntil(lambda: bool(calls), timeout=15000)
        qtbot.waitUntil(lambda: not _KA_THREADS, timeout=15000)


# ------------------------------------------------------- M8.1：第五视图单段浏览
class TestSegmentView:
    def test_shows_one_epoch_stacked(self, view, qtbot):
        """第五视图：第 1 段全通道堆叠；行 0 曲线=该段 C1 原始值（数值断言）."""
        view._view_combo.setCurrentIndex(4)
        assert S.EP_VIEW_SEGMENT in view._view_combo.currentText()
        items = view._plot.listDataItems()
        assert len(items) == 3  # n_ch 条曲线
        _, ed = _make_epochs()
        assert np.allclose(items[0].yData, ed[0, 0] * 1e6, atol=0.5)  # 行 0 无偏移
        assert "第 1 / 12 段" in view._hint.text()

    def test_nav_buttons_and_clamp(self, view, qtbot):
        """段号框跳段重画；▶ 到末段后 clamp；_nav_segment（←→ 同路）回退."""
        view._view_combo.setCurrentIndex(4)
        _, ed = _make_epochs()
        view._seg_spin.setValue(3)
        assert np.allclose(view._plot.listDataItems()[0].yData,
                           ed[2, 0] * 1e6, atol=0.5)
        assert "第 3 / 12 段" in view._hint.text()
        view._btn_next.click()
        view._btn_next.click()  # 3 → 5
        assert view._seg_spin.value() == 5
        view._seg_spin.setValue(12)
        view._btn_next.click()  # 末段再 ▶：SpinBox 自带 clamp
        assert view._seg_spin.value() == 12
        view._nav_segment(-1)  # ←（QShortcut 同一入口）
        assert view._seg_spin.value() == 11
        assert "第 11 / 12 段" in view._hint.text()
