"""工作区删除 UI 测试：树信号载荷 + 主窗口端到端（索引移除 + 持久化）.

交互入口（2026-08-26 用户需求）：树右键"从工作区移除"/Del 键 →
``remove_requested(list[str])`` → 主窗口确认（多条）→ workspace.remove +
save + notify（树/表刷新）。移除只清索引，磁盘数据文件不动。
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from dataloadv.core.recording import RecordingMeta  # noqa: E402
from dataloadv.core.workspace import APP_DIR, Workspace  # noqa: E402


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
        """一次性工作区隔离的 MainWindow（不碰用户真实 ~/.dataloadv 状态）.

        三重隔离（2026-08-27 修复——旧版隔离失效造成了实锤事故：teardown
        glob 的 ``workspaces/<名>.json`` 路径**从来不存在**（真实布局是
        ``workspaces/<名>/workspace.json`` 目录），测试目录全部残留；且
        ``reload_workspace`` 会改写全局"当前工作区"标记 ``current_workspace.txt``
        且从不恢复——用户下次启动 GUI 直接续进了测试名工作区，当天的
        1574 条真实导入全落在了 ``test_删除_*`` 目录里，再反过来污染测试）：
        1. 构造 MainWindow **前**先把标记 preset 成测试名——初始加载就不会
           去解析用户真实工作区；teardown 恢复用户原标记（原先没有则删掉）。
        2. teardown 把 ``state.workspace`` 换成落盘目标在 tmp_path 的替身——
           qtbot 关窗触发的 ``closeEvent`` 会 ``workspace.save()``，写进
           tmp 而不是 ``~/.dataloadv``。
        3. 按真实布局删 ``workspaces/<名>/`` 整个目录。
        """
        from dataloadv.ui.main_window import MainWindow

        name = f"test_删除_{request.node.name}"
        marker = APP_DIR / "current_workspace.txt"
        had_marker = marker.exists()
        before_text = marker.read_text(encoding="utf-8") if had_marker else None
        Workspace.set_current(name)  # MainWindow() 构造即加载空测试工作区
        win = MainWindow()
        qtbot.addWidget(win)
        win.state.reload_workspace(name)
        win._test_ws_name = name  # 重载断言用（见 test_multi_remove_with_confirm）
        yield win
        # ① closeEvent 落盘改道 tmp（qtbot 关窗发生在本 teardown 之后）
        stub = Workspace(name)
        stub._file = tmp_path / "close_event_save.json"
        win.state.workspace = stub
        # ② 删测试工作区目录（真实持久化布局）
        shutil.rmtree(Workspace(name)._file.parent, ignore_errors=True)
        # ③ 恢复用户"当前工作区"标记
        if had_marker:
            marker.write_text(before_text, encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)

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
