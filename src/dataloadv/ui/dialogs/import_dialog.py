"""导入控制器：文件/文件夹选取 → 后台扫描 → 入库 + 错误表展示.

流程（全程主线程只做 UI，扫描在 worker 线程）：
1. ``import_files()`` / ``import_folder()`` 弹原生文件选择器
2. 扫描在 ``run_in_thread`` 中执行，进度经信号回状态栏进度条
3. 完成：并入工作区 → 保存 JSON → 刷新树/表 → 有失败则弹错误表对话框
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHeaderView,
    QMessageBox,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ...core.workspace import Workspace
from ...io.registry import ScanReport, scan_folder
from ...workers.generic import run_in_thread
from ..strings_zh import S

logger = logging.getLogger(__name__)

# 支持的文件选择过滤器（随读取器扩充；M2 起可从注册表自动生成）
_FILE_FILTER = "电生理数据文件 (*.edf *.bdf *.gdf *.vhdr *.fif *.set *.cnt *.mff *.mat);;所有文件 (*)"


class _ScanSignals(QObject):
    """扫描线程 → 主线程的信号桥（进度 + 完成）."""

    progress = Signal(int, int, str)  # done, total, current_name
    done = Signal(object)  # ScanReport + source_path（经 tuple 打包）
    failed = Signal(str)


class ImportController(QObject):
    """主窗口持有的导入控制器."""

    def __init__(self, parent: QWidget, workspace_provider, refresh_callback) -> None:
        """
        :param workspace_provider: () -> Workspace（导入完成时取工作区并入）
        :param refresh_callback: 导入入库后调用（主窗口刷新树/表）
        """
        super().__init__(parent)
        self._parent = parent
        self._get_ws = workspace_provider
        self._refresh = refresh_callback
        self._signals = _ScanSignals()
        self._progress: QProgressBar | None = None
        self._busy = False  # 同时只跑一个导入，避免进度条打架

    # ------------------------------------------------------------ 入口

    def import_files(self) -> None:
        """菜单：导入文件…（多选）."""
        paths, _ = QFileDialog.getOpenFileNames(
            self._parent, S.DLG_IMPORT_FILES, "", _FILE_FILTER
        )
        if not paths or self._busy:
            return
        # 单/多文件扫描极快，但仍走 worker 保持"UI 不计算"规则的一致性
        self._run_scan(paths[0] if len(paths) == 1 else str(paths[0]), files=paths)

    def import_folder(self) -> None:
        """菜单：导入文件夹…（递归）."""
        d = QFileDialog.getExistingDirectory(self._parent, S.DLG_IMPORT_FOLDER)
        if d and not self._busy:
            self._run_scan(d, folder=d)

    # ------------------------------------------------------------ 扫描执行

    def _run_scan(self, source_path: str, files: list[str] | None = None, folder: str | None = None) -> None:
        """启动后台扫描.

        :param source_path: 工作区树上的来源节点路径（文件导入取首个文件所在目录）
        """
        self._busy = True
        self._ensure_progress()

        def _work(folder=folder, files=files):
            """worker 线程体：目录扫描或逐文件读取，只回纯 Python 对象."""
            report = ScanReport()
            if folder:
                report = scan_folder(
                    folder,
                    recursive=True,
                    progress_cb=lambda d, t, n: self._signals.progress.emit(d, t, n),
                )
            elif files:
                from ...io.registry import ScanItem, open_file
                from ...io.base import ScanError

                for i, p in enumerate(files, start=1):
                    self._signals.progress.emit(i, len(files), p.rsplit("/", 1)[-1])
                    try:
                        report.items.append(ScanItem(meta=open_file(p).meta))
                    except ScanError as e:
                        report.errors.append(e)
                    except Exception as e:  # noqa: BLE001
                        report.errors.append(ScanError(p, "", f"意外错误：{e}"))
            return (report, source_path)

        run_in_thread(
            _work,
            on_done=self._on_done,
            on_error=self._on_error,
        )

    def _ensure_progress(self) -> None:
        """拿主窗口状态栏的进度条（懒创建）."""
        if self._progress is None:
            self._progress = QProgressBar()
            self._progress.setMaximumHeight(14)
            self._signals.progress.connect(self._on_progress)
            statusbar = self._parent.statusBar() if isinstance(self._parent, QWidget) else None
            if statusbar is not None:
                statusbar.addPermanentWidget(self._progress)
        self._progress.show()

    # ------------------------------------------------------------ 回调（主线程）

    def _on_progress(self, done: int, total: int, name: str) -> None:
        if self._progress is not None:
            self._progress.setMaximum(max(total, 1))
            self._progress.setValue(done)
        sb = self._parent.statusBar() if isinstance(self._parent, QWidget) else None
        if sb is not None:
            sb.showMessage(S.IMPORT_SCANNING.format(name=name))

    def _on_done(self, payload) -> None:
        report, source_path = payload
        ws: Workspace = self._get_ws()
        added, dup = ws.add_metas(source_path, [item.meta for item in report.items])
        ws.save()
        self._refresh()
        self._finish_progress()
        self._busy = False
        sb = self._parent.statusBar() if isinstance(self._parent, QWidget) else None
        if sb is not None:
            sb.showMessage(
                S.IMPORT_DONE_FMT.format(added=added, dup=dup, errors=len(report.errors)), 8000
            )
        if report.errors:
            self._show_errors(report)

    def _on_error(self, message: str) -> None:
        self._finish_progress()
        self._busy = False
        QMessageBox.critical(self._parent, S.LOAD_FAILED_TITLE, message)

    def _finish_progress(self) -> None:
        if self._progress is not None:
            self._progress.hide()
            self._progress.reset()

    # ------------------------------------------------------------ 错误表

    @staticmethod
    def _show_errors(report: ScanReport) -> None:
        """失败明细对话框：文件 + 中文错误信息两列表格."""
        dlg = QMessageBox(
            QMessageBox.Icon.Warning,
            S.IMPORT_ERR_TITLE.format(n=len(report.errors)),
            f"{len(report.errors)} 个文件未能导入，详情见下表。",
        )
        table = QTableWidget(len(report.errors), 2)
        table.setHorizontalHeaderLabels([S.IMPORT_ERR_COL_FILE, S.IMPORT_ERR_COL_MSG])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setMaximumHeight(260)
        for i, err in enumerate(report.errors):
            table.setItem(i, 0, QTableWidgetItem(err.path.rsplit("/", 1)[-1]))
            table.setItem(i, 1, QTableWidgetItem(err.message))
        dlg.layout().addWidget(table, 1, 1)
        dlg.exec()
