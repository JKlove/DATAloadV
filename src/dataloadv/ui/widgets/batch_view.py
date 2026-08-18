"""批处理进度视图：逐文件状态表 + 进度条 + 取消按钮 + 日志查看.

只做展示与用户操作，不做计算（架构规则 #2）：状态由 BatchDialog 从
引擎回调队列里取出后喂给本视图；「取消」按钮只调用引擎的 cancel()
（threading.Event，线程安全），不等待、不阻塞。

"错误可查"验收标准在这里落地：失败行红显，双击任意行弹出该文件的
逐行日志（ctx 中文日志 + 引擎起止行 + 错误原因）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...batch.jobs import BatchSummary, FileResult, FileStatus
from ..strings_zh import S

# 状态 → 前景色（失败红、成功绿、取消灰；M6 换白底主题后加深到白表格底可辨的浓度）
_STATUS_COLOR = {
    FileStatus.OK: QColor("#1e8e3e"),
    FileStatus.FAILED: QColor("#c5221f"),
    FileStatus.CANCELLED: QColor("#666666"),
    FileStatus.SKIPPED: QColor("#666666"),
}


class FileLogDialog(QDialog):
    """单文件处理日志查看器（只读文本，双击批处理表格行弹出）."""

    def __init__(self, result: FileResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.BATCH_LOG_TITLE_FMT.format(name=result.recording))
        self.resize(640, 420)
        lay = QVBoxLayout(self)
        text = QTextEdit()
        text.setReadOnly(True)
        lines = list(result.log)
        if result.error:
            lines.append("")
            lines.append(f"【错误】{result.error}")
        text.setPlainText("\n".join(lines) if lines else "（无日志）")
        lay.addWidget(text)
        btn = QPushButton("关闭")
        btn.clicked.connect(self.accept)
        lay.addWidget(btn)


class BatchProgressView(QWidget):
    """批处理运行页：逐文件表格 + 进度 + 摘要.

    :signal cancel_requested: 「取消批处理」按钮被点（对话框负责转给引擎）
    """

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[str] = []
        self._results: dict[str, FileResult] = {}  # path → 结果（双击查日志源）
        self._summary_line = QLabel("")
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        self._status_line = QLabel(S.BATCH_ST_WAIT)
        lay.addWidget(self._status_line)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [S.BATCH_COL_FILE, S.BATCH_COL_STATUS, S.BATCH_COL_TIME, S.BATCH_COL_VALUES])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 70)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self._table, 1)

        self._bar = QProgressBar()
        lay.addWidget(self._bar)
        self._summary_line.setWordWrap(True)
        lay.addWidget(self._summary_line)

        row = QHBoxLayout()
        self._btn_cancel = QPushButton(S.BATCH_BTN_CANCEL_RUN)
        self._btn_cancel.clicked.connect(self.cancel_requested.emit)
        hint = QLabel(S.BATCH_ERR_VIEW_HINT)
        row.addWidget(hint, 1)
        row.addWidget(self._btn_cancel)
        lay.addLayout(row)

    # ------------------------------------------------------------------ 状态喂入

    def begin(self, paths: list[str]) -> None:
        """开始一批：按文件清单建行（顺序即处理顺序）."""
        self._paths = list(paths)
        self._results.clear()
        self._table.setRowCount(len(self._paths))
        for i, p in enumerate(self._paths):
            self._table.setItem(i, 0, QTableWidgetItem(Path(p).name))
            self._table.setItem(i, 1, self._item(S.BATCH_ST_WAIT, None))
            self._table.setItem(i, 2, QTableWidgetItem(""))
            self._table.setItem(i, 3, QTableWidgetItem(""))
            self._table.item(i, 0).setToolTip(p)
        self._bar.setRange(0, len(self._paths))
        self._bar.setValue(0)
        self._btn_cancel.setEnabled(True)
        self._btn_cancel.setText(S.BATCH_BTN_CANCEL_RUN)
        self._summary_line.setText("")

    def mark_running(self, name: str) -> None:
        """某文件开始处理（进度回调携带当前文件名；只在还是"等待中"时更新）."""
        for i, p in enumerate(self._paths):
            if Path(p).name == name and self._table.item(i, 1).text() == S.BATCH_ST_WAIT:
                self._table.item(i, 1).setText(S.BATCH_ST_RUNNING)
                break

    def update_file(self, result: FileResult) -> None:
        """某文件出结果：状态/耗时/特征值数 + 颜色（顺手存进日志源）."""
        self._results[result.path] = result
        row = self._row_of(result.path)
        if row is None:
            return
        status_zh = S.BATCH_STATUS_ZH.get(result.status.value, result.status.value)
        self._table.setItem(row, 1, self._item(status_zh, result.status))
        self._table.setItem(row, 2, self._item(f"{result.duration_s:.1f} s", None))
        self._table.setItem(
            row, 3,
            self._item(str(result.n_values) if result.status is FileStatus.OK else "—", None))
        if result.error:
            self._table.item(row, 1).setToolTip(result.error)  # 悬停即见原因

    def set_progress(self, done: int, total: int) -> None:
        self._bar.setRange(0, total)
        self._bar.setValue(done)
        self._status_line.setText(S.BATCH_MSG_RUNNING.format(done=done, total=total))

    def set_cancelling(self) -> None:
        """取消已请求：按钮置灰改文案（真正的停止由引擎逐步骤完成）."""
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.setText(S.BATCH_MSG_CANCELLING)
        self._status_line.setText(S.BATCH_MSG_CANCELLING)

    def finish(self, summary: BatchSummary) -> None:
        """整批结束：摘要行 + 终态文案（失败行保持红显可双击查日志）."""
        self._btn_cancel.setEnabled(False)
        files = "\n".join(Path(p).name for p in summary.files_written)
        text = summary.summary_zh()
        if summary.files_written:
            text += "\n已写出：" + files
        self._summary_line.setText(text)
        self._status_line.setText(S.BATCH_DONE_TITLE if not summary.cancelled
                                  else S.BATCH_STATUS_ZH["cancelled"])

    # ------------------------------------------------------------------ 内部

    def _row_of(self, path: str) -> Optional[int]:
        for i, p in enumerate(self._paths):
            if p == path:
                return i
        return None

    @staticmethod
    def _item(text: str, status: Optional[FileStatus]) -> QTableWidgetItem:
        """带状态着色的表格单元（状态列按结局上色，其余列中性）."""
        it = QTableWidgetItem(text)
        if status is not None and status in _STATUS_COLOR:
            it.setForeground(_STATUS_COLOR[status])
        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return it

    def _on_double_click(self, row: int, _col: int) -> None:
        """双击行 → 该文件的日志对话框."""
        result = self._results.get(self._paths[row])
        if result is not None:
            dlg = FileLogDialog(result, self)
            dlg.exec()
