"""主窗口：整体布局与菜单（M0 骨架版，后续里程碑填充真实功能）.

布局约定（与 plan.md §4 一致）：
- 左侧 Dock：工作区（M1 实现为数据树 + 元数据表）
- 中央：QTabWidget（M1 起每个打开的记录一个浏览 tab + 全局功能 tab）
- 右侧 Dock：处理管线编排（M3）
- 底部 Dock：日志面板（M0 即可用）
- 状态栏：就绪状态 + 批处理/扫描进度条（M1/M5 挂接）
"""

from __future__ import annotations

import logging

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QDockWidget,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from .. import __version__
from .strings_zh import S
from .widgets.log_panel import LogPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """应用主窗口."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(S.APP_TITLE)
        self.resize(1440, 900)  # 16:10 常见桌面尺寸，小于此值用户可自行缩放

        # pyqtgraph 全局深色主题（与 Qt 控件配色统一；antialias 关闭是为大
        # 数据量绘图性能，信号浏览器用包络绘制弥补视觉锯齿）
        pg.setConfigOptions(background="k", foreground="w", antialias=False)

        self._build_central()
        self._build_docks()
        self._build_menus()
        self._build_statusbar()

    # ------------------------------------------------------------------ 布局

    def _build_central(self) -> None:
        """中央 tab 区（M0 仅一个欢迎占位 tab）."""
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close)
        self.setCentralWidget(self.tabs)
        self._add_welcome_tab()

    def _build_docks(self) -> None:
        """四个 Dock：左工作区 / 右处理 / 下日志（中央为 tab 区）."""
        # 左：工作区（M1 替换为 WorkspaceDock）
        self._dock_workspace = self._make_dock(S.DOCK_WORKSPACE, S.PLACEHOLDER_WORKSPACE)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock_workspace)

        # 右：处理管线（M3 替换为 PipelineDock）
        self._dock_pipeline = self._make_dock(S.DOCK_PIPELINE, S.PLACEHOLDER_PIPELINE)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._dock_pipeline)

        # 下：日志面板（M0 即真实可用）
        self.log_panel = LogPanel(self)
        self._dock_log = QDockWidget(S.DOCK_LOG, self)
        self._dock_log.setWidget(self.log_panel)
        self._dock_log.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._dock_log)

    @staticmethod
    def _make_dock(title: str, placeholder: str) -> QDockWidget:
        """造一个带占位内容的 Dock（骨架期用，后续里程碑被真实部件替换）."""
        dock = QDockWidget(title)
        label = QLabel(placeholder)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        dock.setWidget(label)
        return dock

    def _build_menus(self) -> None:
        """中文菜单栏（M0 大部分动作禁用，随里程碑逐一启用）."""
        menu_file = self.menuBar().addMenu(S.MENU_FILE)
        menu_view = self.menuBar().addMenu(S.MENU_VIEW)
        self.menuBar().addMenu(S.MENU_PROCESS)
        menu_help = self.menuBar().addMenu(S.MENU_HELP)

        # 文件菜单：M1 起接通导入/工作区动作
        for label in (
            S.ACT_NEW_WORKSPACE,
            S.ACT_OPEN_WORKSPACE,
            S.ACT_IMPORT_FILES,
            S.ACT_IMPORT_FOLDER,
            S.ACT_EXPORT,
        ):
            act = menu_file.addAction(label)
            act.setEnabled(False)  # 骨架期禁用；对应里程碑实现时启用并连接槽

        # 查看菜单：Dock 开关
        for title, dock in (
            (S.DOCK_WORKSPACE, self._dock_workspace),
            (S.DOCK_PIPELINE, self._dock_pipeline),
            (S.DOCK_LOG, self._dock_log),
        ):
            menu_view.addAction(dock.toggleViewAction())

        menu_file.addSeparator()
        menu_file.addAction(S.ACT_EXIT, self.close)
        menu_help.addAction(S.ACT_ABOUT, self._show_about)

    def _build_statusbar(self) -> None:
        """状态栏：就绪文案 + 版本号."""
        self.statusBar().showMessage(S.STATUS_READY)
        self.statusBar().addPermanentWidget(QLabel(S.STATUS_VERSION_FMT.format(version=__version__)))

    # ------------------------------------------------------------------ 槽

    def _on_tab_close(self, index: int) -> None:
        """关闭中央 tab；全部关闭后恢复欢迎占位 tab，防止中央区变空."""
        widget = self.tabs.widget(index)
        if widget is not None and hasattr(widget, "teardown"):
            widget.teardown()  # 浏览 tab 关闭时释放数据/断开日志（M1 起有意义）
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self._add_welcome_tab()

    def _add_welcome_tab(self) -> None:
        """添加欢迎占位 tab（M0 骨架；有真实 tab 时不显示）."""
        welcome = QLabel(S.PLACEHOLDER_TAB_WELCOME)
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tabs.addTab(welcome, "欢迎")

    def _show_about(self) -> None:
        QMessageBox.about(self, S.ACT_ABOUT, S.ABOUT_TEXT)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        """窗口关闭前断开日志 Handler."""
        self.log_panel.teardown()
        super().closeEvent(event)
