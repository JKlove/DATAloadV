"""工作区删除 UI 测试：树信号载荷 + 主窗口端到端（索引移除 + 持久化）.

交互入口（2026-08-26 用户需求）：树右键"从工作区移除"/Del 键 →
``remove_requested(list[str])`` → 主窗口确认（多条）→ workspace.remove +
save + notify（树/表刷新）。移除只清索引，磁盘数据文件不动。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from dataloadv.core.recording import RecordingMeta  # noqa: E402
from dataloadv.core.workspace import Workspace  # noqa: E402


def _meta(path: str) -> RecordingMeta:
    """最小可用合成元数据（与 test_workspace.py 同款）."""
    n = 4
    return RecordingMeta(
        path=path,
        format="EDF",
        reader_id="edf",
        n_channels=n,
        channel_names=[f"ch{i}" for i in range(n)],
        channel_types=["eeg"] * n,
        sfreq=250.0,
        duration_s=10.0,
    )


def _ws_two_sources() -> Workspace:
    ws = Workspace("删除测试")
    ws.add_metas("/src/a", [_meta("/src/a/x.edf"), _meta("/src/a/y.edf")])
    ws.add_metas("/src/b", [_meta("/src/b/z.edf")])
    return ws


class TestTreeRemoveSignal:
    """树侧：_paths_for_item 分类 + remove_requested 载荷."""

    def test_recording_item_yields_single_path(self, qtbot):
        from dataloadv.ui.widgets.workspace_tree import WorkspaceTree

        tree = WorkspaceTree()
        qtbot.addWidget(tree)
        tree.refresh(_ws_two_sources())
        root = tree._tree.topLevelItem(0)
        src_a = root.child(0)
        item_x = src_a.child(0)

        got: list = []
        tree.remove_requested.connect(lambda paths: got.append(paths))
        tree._delete_current(item_x)
        assert got == [["/src/a/x.edf"]]

    def test_source_item_yields_all_children(self, qtbot):
        from dataloadv.ui.widgets.workspace_tree import WorkspaceTree

        tree = WorkspaceTree()
        qtbot.addWidget(tree)
        tree.refresh(_ws_two_sources())
        root = tree._tree.topLevelItem(0)
        src_a = root.child(0)

        got: list = []
        tree.remove_requested.connect(lambda paths: got.append(paths))
        tree._delete_current(src_a)
        assert sorted(got[0]) == ["/src/a/x.edf", "/src/a/y.edf"]

    def test_root_item_yields_nothing(self, qtbot):
        from dataloadv.ui.widgets.workspace_tree import WorkspaceTree

        tree = WorkspaceTree()
        qtbot.addWidget(tree)
        tree.refresh(_ws_two_sources())
        got: list = []
        tree.remove_requested.connect(lambda paths: got.append(paths))
        tree._delete_current(tree._tree.topLevelItem(0))
        tree._delete_current(None)
        assert got == []  # 根节点/空选择不参与移除


class TestMainWindowRemove:
    """主窗口端到端：移除 → 索引清掉 + JSON 落库 + 树/表刷新."""

    @pytest.fixture()
    def win(self, qtbot, tmp_path, request):
        """一次性工作区隔离的 MainWindow（不碰用户真实 ~/.dataloadv 工作区）.

        每个测试用唯一工作区名：save 落 ~/.dataloadv/workspaces/<name>.json，
        测试间不通过持久化文件耦合；teardown 清掉自己的落盘。
        """
        from dataloadv.ui.main_window import MainWindow

        name = f"test_删除_{request.node.name}"
        win = MainWindow()
        qtbot.addWidget(win)
        win.state.reload_workspace(name)
        win._test_ws_name = name  # 重载断言用（见 test_multi_remove_with_confirm）
        yield win
        for p in Path.home().glob(f".dataloadv/workspaces/{name}.json"):
            p.unlink(missing_ok=True)

    def test_single_remove_no_dialog(self, win):
        from dataloadv.ui import main_window as mw

        called = []
        mw.QMessageBox.question = staticmethod(
            lambda *a, **k: called.append(a) or 2  # 2=No——单条不应弹框，弹了也拒
        )
        ws = win.state.workspace
        ws.add_metas("/src/a", [_meta("/src/a/x.edf"), _meta("/src/a/y.edf")])
        win.state.notify_workspace_changed()

        win._remove_from_workspace(["/src/a/x.edf"])

        assert called == []  # 单条无确认框
        assert len(ws) == 1
        assert ws.find_by_path("/src/a/x.edf") is None
        # 树同步刷新（工作区行计数 = 1）
        assert win.workspace_tree._tree.topLevelItem(0).childCount() == 1

    def test_multi_remove_with_confirm(self, win):
        from PySide6.QtWidgets import QMessageBox

        from dataloadv.ui import main_window as mw

        mw.QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes
        )
        ws = win.state.workspace
        ws.add_metas("/src/a", [_meta("/src/a/x.edf"), _meta("/src/a/y.edf")])
        ws.add_metas("/src/b", [_meta("/src/b/z.edf")])
        win.state.notify_workspace_changed()

        win._remove_from_workspace(["/src/a/x.edf", "/src/a/y.edf"])

        assert len(ws) == 1  # 只剩 /src/b/z.edf；空来源 a 节点自动清理
        assert ws.find_by_path("/src/a/x.edf") is None
        assert "/src/a" not in ws.sources
        # 持久化：重载同工作区名，仍只有 1 条（save 真落盘）
        win.state.reload_workspace(win._test_ws_name)
        assert len(win.state.workspace) == 1
        assert win.state.workspace.find_by_path("/src/b/z.edf") is not None

    def test_multi_remove_declined_keeps_entries(self, win):
        from PySide6.QtWidgets import QMessageBox

        from dataloadv.ui import main_window as mw

        mw.QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.No
        )
        ws = win.state.workspace
        ws.add_metas("/src/a", [_meta("/src/a/x.edf"), _meta("/src/a/y.edf")])
        win.state.notify_workspace_changed()

        win._remove_from_workspace(["/src/a/x.edf", "/src/a/y.edf"])

        assert len(ws) == 2  # 用户拒绝 → 原样保留
