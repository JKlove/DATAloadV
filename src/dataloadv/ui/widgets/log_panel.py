"""日志面板（底部 Dock 内容）：滚动显示运行日志 + 状态栏进度条挂点.

线程安全说明：任何线程的 logger 记录经 QtLogHandler 的回调发出；这里用
``QTimer.singleShot(0, ...)``（或信号）把文本投递回主线程再写入控件，
避免 worker 线程直接触碰 QPlainTextEdit（架构规则 3）。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from ...core.logging_setup import QtLogHandler


class _LogBridge(QObject):
    """跨线程日志桥：日志文本 → Qt 信号（自动队列连接到主线程）."""

    line = Signal(str)


class LogPanel(QWidget):
    """底部日志面板.

    挂接根 logger 后自动显示全应用日志；窗口销毁时自动断开，
    纯命令行使用（无 UI）时 QtLogHandler 静默丢弃，互不影响。
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = _LogBridge()
        self._bridge.line.connect(self._append)

        self._view = QPlainTextEdit(self)
        self._view.setReadOnly(True)
        self._view.setMaximumBlockCount(5000)  # 限制行数，长期运行不撑内存
        self._view.setPlaceholderText("运行日志将显示在这里…")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        # 挂到根 logger：core 层的 QtLogHandler 本身不依赖 Qt（见 logging_setup.py）
        root = logging.getLogger()
        self._handler = QtLogHandler()
        self._handler.attach(self._bridge.line.emit)  # emit 从任意线程调用都安全
        root.addHandler(self._handler)

    def _append(self, text: str) -> None:
        """在主线程追加一行日志（经信号队列连接保证）."""
        self._view.appendPlainText(text)

    def teardown(self) -> None:
        """窗口销毁前调用：从根 logger 摘除 Handler，防止悬空回调."""
        logging.getLogger().removeHandler(self._handler)
        self._handler.attach(None)
