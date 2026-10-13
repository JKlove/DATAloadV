"""事件 marker 列表测试（M11）：列文本/数值排序/双击跳转信号/浏览器集成.

夹具口径：
- 独立构造（TestEventListView）仿 test_ui_browser_m6.TestOverviewLane 的
  独立 EventLane 模式——直接造 EventTable 喂 EventListView。
- 浏览器集成（TestBrowserIntegration）走 FIF 真路径：conftest 的
  synthetic_raw 含 3 个已知事件 T0@10s / T1@20s / T2@30s（250 Hz），
  初始视口 [0, 10)——双击 T2 行后视口中心应 ≈ 30 s。

显隐断言用 ``isHidden()``（显式 setVisible 语义）而非 ``isVisible()``：
offscreen 下顶级窗口未 show，isVisible 恒 False，isHidden 才反映挂载代码
里 setVisible(len(events) > 0) 的意图。
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from PySide6.QtCore import Qt  # noqa: E402

from dataloadv.core.recording import EventTable  # noqa: E402
from dataloadv.ui.strings_zh import S  # noqa: E402
from dataloadv.ui.widgets.event_list import EventListView  # noqa: E402
from dataloadv.ui.widgets.event_lane import event_color  # noqa: E402


def _table_3() -> EventTable:
    """三个事件：含中文 label、label 空退化 code、跨数量级 onset."""
    return EventTable(
        onset=np.array([10.0, 100.0, 20.0]),
        duration=np.array([0.0, 1.5, 0.0]),
        code=["T0", "T1", ""],
        label=["静息", "", "自定义标记"],  # T1 的 label 空 → 名称退 code
    )


class TestEventListView:
    """控件级：模型列文本、排序角色、双击信号、名称配色."""

    def test_rows_and_column_text(self, qtbot):
        view = EventListView()
        qtbot.addWidget(view)
        view.set_events(_table_3(), sfreq=250.0)
        m = view._model
        assert m.rowCount() == 3
        # 行 0：T0 静息 @10s → 样本 2500
        assert m.data(m.index(0, 0), Qt.ItemDataRole.DisplayRole) == "1"
        assert m.data(m.index(0, 1), Qt.ItemDataRole.DisplayRole) == "静息"
        assert m.data(m.index(0, 2), Qt.ItemDataRole.DisplayRole) == "10.000"
        assert m.data(m.index(0, 3), Qt.ItemDataRole.DisplayRole) == "2500"
        assert m.data(m.index(0, 4), Qt.ItemDataRole.DisplayRole) == "0.000"
        # 行 1：label 空 → 名称退化 code "T1"；持续 1.5s
        assert m.data(m.index(1, 1), Qt.ItemDataRole.DisplayRole) == "T1"
        assert m.data(m.index(1, 4), Qt.ItemDataRole.DisplayRole) == "1.500"
        # 行 2：label 中文、code 空 → 样本点 = 20*250
        assert m.data(m.index(2, 1), Qt.ItemDataRole.DisplayRole) == "自定义标记"
        assert m.data(m.index(2, 3), Qt.ItemDataRole.DisplayRole) == "5000"

    def test_numeric_sort_role(self, qtbot):
        """数值列 UserRole 必须是数值（坑 #30：字符串排序 100 < 20 乱序）."""
        view = EventListView()
        qtbot.addWidget(view)
        view.set_events(_table_3(), sfreq=250.0)
        m = view._model
        assert m.data(m.index(1, 2), Qt.ItemDataRole.UserRole) == 100.0
        assert isinstance(m.data(m.index(1, 3), Qt.ItemDataRole.UserRole), int)
        # 按时间列排序后首行应是最小 onset（10.0），字符串序会误排 100.0
        view._proxy.sort(2, Qt.SortOrder.AscendingOrder)
        assert view.onset_at_row(0) == pytest.approx(10.0)

    def test_double_click_emits_onset(self, qtbot):
        view = EventListView()
        qtbot.addWidget(view)
        view.set_events(_table_3(), sfreq=250.0)
        got: list[float] = []
        view.jump_requested.connect(lambda t: got.append(t))
        # 初始序 = 时间列升序，但不硬编码行号——按 onset 定位目标行更稳
        row = next(r for r in range(3) if view.onset_at_row(r) == pytest.approx(20.0))
        view._on_double_click(view._proxy.index(row, 0))
        assert got == [20.0]

    def test_name_color_matches_event_line(self, qtbot):
        """名称列前景色与波形事件竖线同色（event_color 同源）."""
        view = EventListView()
        qtbot.addWidget(view)
        t = _table_3()
        view.set_events(t, sfreq=250.0)
        m = view._model
        for row in range(3):
            brush = m.data(m.index(row, 1), Qt.ItemDataRole.ForegroundRole)
            expect = event_color(t.code[row], t.code)
            assert brush.color().name() == expect


@pytest.fixture()
def browser(tmp_path, qtbot, synthetic_raw):
    """FIF 往返 → open_file → 浏览器（与 test_ui_browser_m6 同款；synthetic_raw
    含 T0@10s/T1@20s/T2@30s 三事件）."""
    from dataloadv.io.registry import open_file
    from dataloadv.ui.widgets.signal_browser import SignalBrowserView

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
def browser_noev(tmp_path, qtbot):
    """无 annotations 的 FIF → 浏览器（事件列表面板应保持隐藏）."""
    import mne

    from dataloadv.io.registry import open_file
    from dataloadv.ui.widgets.signal_browser import SignalBrowserView

    raw = mne.io.RawArray(
        np.zeros((2, 2500)), mne.create_info(2, 250.0, "eeg"), verbose="ERROR"
    )
    fif = tmp_path / "noev.fif"
    raw.save(fif, overwrite=True, verbose="ERROR")
    rec = open_file(fif)
    view = SignalBrowserView(rec)
    qtbot.addWidget(view)
    qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
    yield view
    view.teardown()
    rec.unload()


class TestBrowserIntegration:
    """浏览器级：面板显隐、双击行 → _center_at 定位联动."""

    def test_panel_visible_with_events(self, browser):
        """有事件（synthetic 3 个）→ 面板非隐藏、行数 3、空态层不显示."""
        assert not browser._event_list.isHidden()
        assert browser._event_list.row_count() == 3
        assert browser._event_list._empty_lbl.isHidden()

    def test_panel_shows_empty_state_without_events(self, browser_noev):
        """无事件 → 面板仍常驻（不隐藏），空态提示层显示且行数 0."""
        assert not browser_noev._event_list.isHidden()
        assert browser_noev._event_list.row_count() == 0
        assert not browser_noev._event_list._empty_lbl.isHidden()

    def test_double_click_centers_on_event(self, browser):
        """双击 T2 行 → 视口中心 ≈ 30 s（初始视口 [0,10)）."""
        view = browser
        # proxy 未排序时行序 = source 序，但稳妥起见按 onset 找目标行
        row = next(r for r in range(view._event_list.row_count())
                   if view._event_list.onset_at_row(r) == pytest.approx(30.0))
        view._event_list._on_double_click(view._event_list._proxy.index(row, 0))
        t0, t1 = view._visible_range()
        assert (t0 + t1) / 2 == pytest.approx(30.0, abs=1e-6)
