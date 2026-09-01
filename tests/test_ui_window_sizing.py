"""主窗口初始尺寸自适应屏幕的回归测试（M10 后续修复）.

背景（2026-09-01 Windows 真机反馈）：初始窗口硬编 1440×900，在 1366×768
笔记本或 1080p@125% 缩放（有效逻辑高 864）上超出屏幕，右侧处理 Dock 被
屏幕边缘裁掉；全屏→还原触发整体重排所以"恢复"。修复两件套：
1. 初始尺寸按主屏可用区域收口并居中（大屏保持 1440×900）；
2. 首次 showEvent 用 resizeDocks 按面板**当时**（过 DPI/字体 polish 的）
   尺寸提示显式定左右 Dock 宽，使初始布局与后续重排一致。

offscreen 平台默认屏 800×800（实测本 PySide6 构建忽略 screenSize 参数），
天然就是"小屏"模拟；大屏路径用打桩 QGuiApplication（沿坑 #31/#54 的
模块属性 patch 先例）。
"""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dataloadv.core.workspace import APP_DIR, Workspace  # noqa: E402


class _StubScreen:
    """打桩 QScreen：只提供 availableGeometry（MainWindow 取尺寸的唯一用途）."""

    def __init__(self, w: int, h: int) -> None:
        self._rect = QRect(0, 0, w, h)

    def availableGeometry(self) -> QRect:
        return self._rect


class _StubGuiApp:
    """打桩 QGuiApplication（模块属性 patch 用）."""

    screen_size = (1920, 1080)

    @staticmethod
    def primaryScreen() -> _StubScreen:
        w, h = _StubGuiApp.screen_size
        return _StubScreen(w, h)


class TestInitialWindowSizing:
    """初始窗口尺寸 + Dock 首布局三断言：不超屏 / dock 在窗内 / 面板不截断."""

    @pytest.fixture()
    def make_win(self, qtbot, tmp_path, request):
        """工厂 + 三重隔离（沿 test_ui_workspace_remove.py 的 win fixture 模式）.

        工厂而非直接 yield 窗口：大屏用例需要在构造**前**打桩
        QGuiApplication——工厂让每个测试自己决定构造时机。
        """
        from dataloadv.ui.main_window import MainWindow

        name = f"test_窗口尺寸_{request.node.name}"
        marker = APP_DIR / "current_workspace.txt"
        had_marker = marker.exists()
        before_text = marker.read_text(encoding="utf-8") if had_marker else None
        Workspace.set_current(name)  # MainWindow() 构造即加载空测试工作区
        holder: dict = {}

        def _make() -> "MainWindow":
            win = MainWindow()
            qtbot.addWidget(win)
            holder["win"] = win
            return win

        yield _make
        win = holder.get("win")
        if win is not None:
            # closeEvent 落盘改道 tmp（qtbot 关窗发生在本 teardown 之后）
            stub = Workspace(name)
            stub._file = tmp_path / "close_event_save.json"
            win.state.workspace = stub
        shutil.rmtree(Workspace(name)._file.parent, ignore_errors=True)
        if had_marker:
            marker.write_text(before_text, encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)

    @staticmethod
    def _assert_pipeline_dock_fits(win) -> None:
        """右侧处理 Dock 完全在窗口内，且面板实宽 ≥ 自身最小宽（内容不截断）."""
        d = win._dock_pipeline.geometry()
        assert d.right() < win.width(), f"处理 Dock 右缘 {d.right()} 超出窗口宽 {win.width()}"
        panel = win.pipeline_panel
        assert panel.width() >= panel.minimumSizeHint().width(), (
            f"面板实宽 {panel.width()} < 最小宽 {panel.minimumSizeHint().width()}"
        )

    def test_small_screen_clamps_window_and_fits_dock(self, make_win, qtbot):
        """小屏（offscreen 默认 800×800）：窗口收口到可用区域内，处理 Dock 完整可见."""
        win = make_win()
        win.show()
        qtbot.wait(50)  # 等 QMainWindow 首布局激活
        avail = QApplication.primaryScreen().availableGeometry()
        assert win.width() <= avail.width()
        assert win.height() <= avail.height()
        assert win._docks_sized  # showEvent 首显示钩子已跑
        self._assert_pipeline_dock_fits(win)

    def test_large_screen_keeps_1440x900(self, make_win, qtbot, monkeypatch):
        """大屏（打桩 1920×1080）：保持 1440×900 不被收口，Dock 照常完整."""
        from dataloadv.ui import main_window as mw

        monkeypatch.setattr(mw, "QGuiApplication", _StubGuiApp)
        win = make_win()
        assert (win.width(), win.height()) == (1440, 900)
        win.show()
        qtbot.wait(50)
        self._assert_pipeline_dock_fits(win)

    def test_scaled_1080p_height_clamped(self, make_win, qtbot, monkeypatch):
        """1080p@125%（有效逻辑 1536×864）：高收口到 864、宽保持 1440."""
        from dataloadv.ui import main_window as mw

        _StubGuiApp.screen_size = (1536, 864)
        monkeypatch.setattr(mw, "QGuiApplication", _StubGuiApp)
        win = make_win()
        assert (win.width(), win.height()) == (1440, 864)
        win.show()
        qtbot.wait(50)
        self._assert_pipeline_dock_fits(win)
