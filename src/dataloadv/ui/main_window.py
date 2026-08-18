"""主窗口：布局、菜单与会话编排.

布局（plan.md §4）：
- 左 Dock：工作区树（WorkspaceTree）
- 中央：QTabWidget——元数据表（全局）+ 每条打开的录制一个 SignalBrowserView
- 右 Dock：处理管线（M3 前为占位）
- 下 Dock：日志面板
- 状态栏：消息 + 导入进度条 + 版本号

打开录制的线程模型：双击（树/表）→ ``run_in_thread(open_file)``（头+事件读取
在 worker）→ 主线程建 SignalBrowserView tab（其内部再异步 ensure_raw 数据）。
"""

from __future__ import annotations

import logging

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QDockWidget,
    QTabWidget,
)

from .. import __version__
from ..core.fs_store import FsStore
from ..io.registry import open_file
from ..io.table import FS_UNSET_NOTE
from ..proc.context import ProcessingContext
from ..proc.preview import make_preview_recording
from ..workers.generic import run_in_thread
from .dialogs.import_dialog import ImportController
from .state import SessionState
from .strings_zh import S
from .widgets.epochs_preview import EpochsPreviewView
from .widgets.log_panel import LogPanel
from .widgets.meta_table import MetaTableView
from .widgets.pipeline_panel import PipelinePanel
from .widgets.signal_browser import SignalBrowserView
from .widgets.workspace_tree import WorkspaceTree

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """应用主窗口."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(S.APP_TITLE)
        self.resize(1440, 900)

        # pyqtgraph 全局深色主题（关闭抗锯齿换取大数据量绘制性能，
        # 信号浏览器用峰值包络弥补视觉锯齿——见 signal_browser.py 模块说明）
        pg.setConfigOptions(background="k", foreground="w", antialias=False)

        self.state = SessionState()
        self.state.workspace_changed.connect(self._refresh_views)
        self.state.recording_opened.connect(self._on_recording_opened)
        self._browser_tabs: dict[str, QWidget] = {}  # rec_id -> SignalBrowserView

        self._build_central()
        self._build_docks()
        # 导入控制器须先于菜单存在（菜单动作直接引用它的方法）
        self.importer = ImportController(
            self, lambda: self.state.workspace, self._refresh_views
        )
        self._build_menus()
        self._build_statusbar()

        self._refresh_views()
        logger.info("主窗口就绪（工作区：%s，%d 条录制）", self.state.workspace.name, len(self.state.workspace))

    # ------------------------------------------------------------------ 布局

    def _build_central(self) -> None:
        """中央 tab 区：元数据表 + 各浏览 tab."""
        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close)
        self.setCentralWidget(self.tabs)

        self.meta_view = MetaTableView()
        self.meta_view.open_requested.connect(self._open_recording_async)
        self.tabs.addTab(self.meta_view, S.TAB_META_TABLE)

    def _build_docks(self) -> None:
        """左工作区树 / 右处理管线 / 下日志."""
        self.workspace_tree = WorkspaceTree()
        self.workspace_tree.open_requested.connect(self._open_recording_async)
        self._dock_workspace = QDockWidget(S.DOCK_WORKSPACE, self)
        self._dock_workspace.setWidget(self.workspace_tree)

        # M3：处理管线面板（预览结果经 preview_ready 回主窗口开 tab）
        # M4：特征计算结果经 features_ready 开特征结果 tab
        self.pipeline_panel = PipelinePanel(self._get_active_browser, self)
        self.pipeline_panel.preview_ready.connect(self._on_preview_ready)
        self.pipeline_panel.features_ready.connect(self._on_features_ready)
        self._dock_pipeline = QDockWidget(S.DOCK_PIPELINE, self)
        self._dock_pipeline.setWidget(self.pipeline_panel)

        self.log_panel = LogPanel(self)
        self._dock_log = QDockWidget(S.DOCK_LOG, self)
        self._dock_log.setWidget(self.log_panel)

        for dock, area in (
            (self._dock_workspace, Qt.DockWidgetArea.LeftDockWidgetArea),
            (self._dock_pipeline, Qt.DockWidgetArea.RightDockWidgetArea),
            (self._dock_log, Qt.DockWidgetArea.BottomDockWidgetArea),
        ):
            dock.setFeatures(
                QDockWidget.DockWidgetFeature.DockWidgetClosable
                | QDockWidget.DockWidgetFeature.DockWidgetMovable
                | QDockWidget.DockWidgetFeature.DockWidgetFloatable
            )
            self.addDockWidget(area, dock)

    def _build_menus(self) -> None:
        """中文菜单（导入 M1 / 处理 M3 已接通）."""
        menu_file = self.menuBar().addMenu(S.MENU_FILE)
        menu_view = self.menuBar().addMenu(S.MENU_VIEW)
        menu_proc = self.menuBar().addMenu(S.MENU_PROCESS)
        menu_help = self.menuBar().addMenu(S.MENU_HELP)

        act_import_files = menu_file.addAction(S.ACT_IMPORT_FILES, self.importer.import_files)
        act_import_folder = menu_file.addAction(S.ACT_IMPORT_FOLDER, self.importer.import_folder)
        menu_file.addSeparator()
        menu_file.addAction(S.ACT_EXIT, self.close)

        for title, dock in (
            (S.DOCK_WORKSPACE, self._dock_workspace),
            (S.DOCK_PIPELINE, self._dock_pipeline),
            (S.DOCK_LOG, self._dock_log),
        ):
            menu_view.addAction(dock.toggleViewAction())

        menu_help.addAction(S.ACT_ABOUT, self._show_about)
        self._import_actions = (act_import_files, act_import_folder)

        # 处理菜单：与右 Dock 面板按钮同一动作（M3 预览/PSD；M4 视口预填/特征）
        menu_proc.addAction(S.PIPE_BTN_PREVIEW, self.pipeline_panel.start_preview)
        menu_proc.addAction(S.PIPE_BTN_PSD, self.pipeline_panel.start_psd)
        menu_proc.addSeparator()
        menu_proc.addAction(S.FEAT_BTN_VIEWPORT, self.pipeline_panel.use_viewport_window)
        menu_proc.addAction(S.FEAT_BTN_RUN, self.pipeline_panel.start_features)

    def _build_statusbar(self) -> None:
        self.statusBar().showMessage(S.STATUS_READY)
        self.statusBar().addPermanentWidget(QLabel(S.STATUS_VERSION_FMT.format(version=__version__)))

    # ------------------------------------------------------------------ 数据流

    def _refresh_views(self) -> None:
        """工作区变化后刷新树与元数据表."""
        ws = self.state.workspace
        self.workspace_tree.refresh(ws)
        self.meta_view.refresh(ws.all_metas())

    def _open_recording_async(self, meta_path: str) -> None:
        """后台打开录制（去重：已在开的 tab 直接置前）."""
        for rec in self.state.open_recordings.values():
            if rec.meta.path == meta_path:
                self._focus_browser_tab(rec)
                return
        self.statusBar().showMessage(S.STATUS_OPENING.format(name=meta_path.rsplit("/", 1)[-1]))
        run_in_thread(
            open_file,
            path=meta_path,
            on_done=self._on_opened,
            on_error=lambda m: QMessageBox.critical(self, S.LOAD_FAILED_TITLE, m),
        )

    def _on_opened(self, rec) -> None:
        """worker 返回 Recording（主线程）：登记 → recording_opened 信号开 tab.

        CSV/TXT/HDF5 等文件内不含采样率：先问一次（FsStore 持久记忆），
        用户取消则不开 tab（以错误采样率浏览是坏数据）。
        """
        if FS_UNSET_NOTE in rec.meta.notes and not self._ask_sample_rate(rec):
            self.statusBar().showMessage(S.STATUS_READY)
            return
        self.state.attach_open(rec)
        self.statusBar().showMessage(S.STATUS_READY)

    def _ask_sample_rate(self, rec) -> bool:
        """询问采样率并写回 meta 与 FsStore；返回 False = 用户取消."""
        n_times = max(1, round(rec.meta.duration_s * rec.meta.sfreq))
        fs, ok = QInputDialog.getDouble(
            self, S.ASK_FS_TITLE, S.ASK_FS_TEXT.format(name=rec.meta.filename),
            value=250.0, minValue=0.1, maxValue=100000.0, decimals=2,
        )
        if not ok:
            return False
        FsStore().put(rec.meta.path, fs)
        rec.meta.sfreq = fs
        rec.meta.duration_s = n_times / fs
        rec.meta.notes = rec.meta.notes.replace(FS_UNSET_NOTE, "").strip("；; ")
        # 工作区里的同一条 meta 同步（表里时长列才正确）
        ws_meta = self.state.workspace.find_by_path(rec.meta.path)
        if ws_meta is not None:
            ws_meta.sfreq, ws_meta.duration_s = fs, rec.meta.duration_s
            ws_meta.notes = rec.meta.notes
            self.state.workspace.save()
            self.meta_view.refresh(self.state.workspace.all_metas())
        logger.info("采样率已设定：%s → %s Hz（已记忆）", rec.meta.filename, fs)
        return True

    def _on_recording_opened(self, rec) -> None:
        """建浏览 tab（SessionState.recording_opened 的唯一消费者）."""
        view = SignalBrowserView(rec)
        self._browser_tabs[rec.meta.rec_id] = view
        self.tabs.addTab(view, S.BROWSER_TITLE_FMT.format(name=rec.meta.filename))
        self.tabs.setCurrentWidget(view)

    def _focus_browser_tab(self, rec) -> None:
        """把某录制的浏览 tab 置前."""
        widget = self._browser_tabs.get(rec.meta.rec_id)
        if widget is not None:
            self.tabs.setCurrentWidget(widget)

    def _on_tab_close(self, index: int) -> None:
        """关 tab：元数据表常驻不可关；浏览/预览 tab 释放数据."""
        widget = self.tabs.widget(index)
        if widget is self.meta_view:
            return
        if hasattr(widget, "teardown"):  # SignalBrowserView / EpochsPreviewView
            widget.teardown()
        if hasattr(widget, "rec"):  # SignalBrowserView（含预览副本）
            self.state.close_recording(widget.rec)  # 未登记的预览Recording此处为安全 no-op+卸载
            self._browser_tabs.pop(widget.rec.meta.rec_id, None)
        self.tabs.removeTab(index)

    # ------------------------------------------------------------------ 预览（M3）

    def _get_active_browser(self) -> SignalBrowserView | None:
        """当前激活 tab 若是信号浏览器则返回之（预览作用于它）."""
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SignalBrowserView) else None

    def _on_preview_ready(self, ctx: ProcessingContext) -> None:
        """管线面板预览完成（主线程）：raw→浏览 tab；epochs→分段预览 tab."""
        browser = self._get_active_browser()
        name = browser.rec.meta.filename if browser is not None else "数据"
        if ctx.stage == "raw":
            preview_rec = make_preview_recording(browser.rec, ctx)
            view = SignalBrowserView(preview_rec)
            self._browser_tabs[preview_rec.meta.rec_id] = view
            self.tabs.addTab(view, S.PIPE_PREVIEW_TAB_FMT.format(name=name))
        else:
            view = EpochsPreviewView(ctx, name)
            self.tabs.addTab(view, S.PIPE_EPOCHS_TAB_FMT.format(name=name))
        self.tabs.setCurrentWidget(view)
        logger.info("预览 tab 已建立：%s（阶段 %s，%d 步）", name, ctx.stage, len(ctx.history))

    # ------------------------------------------------------------------ 特征（M4）

    def _on_features_ready(self, payload: dict) -> None:
        """特征计算完成（主线程）：开特征结果 tab（表格 + 导出按钮）."""
        from .widgets.feature_table import FeatureTableView

        browser = self._get_active_browser()
        name = browser.rec.meta.filename if browser is not None else "数据"
        view = FeatureTableView(
            payload["table"], payload["ctx"],
            pipeline_dicts=payload.get("pipeline_dicts"),
            feature_dicts=payload.get("feature_dicts"),
        )
        self.tabs.addTab(view, S.FEAT_TAB_FMT.format(name=name))
        self.tabs.setCurrentWidget(view)
        logger.info("特征结果 tab 已建立：%s（%s）", name, payload["table"].summary_zh())

    # ------------------------------------------------------------------ 其他

    def _show_about(self) -> None:
        QMessageBox.about(self, S.ACT_ABOUT, S.ABOUT_TEXT)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        """关闭前释放所有打开的数据并保存工作区."""
        for rec in list(self.state.open_recordings.values()):
            rec.unload()
        self.state.workspace.save()
        self.log_panel.teardown()
        super().closeEvent(event)
