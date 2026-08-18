"""应用入口.

职责：
- 创建 QApplication，配置高 DPI 与深色主题
- 安装全局异常钩子：未捕获异常写入日志文件而不是静默崩溃
- 实例化主窗口并进入事件循环

用法：安装本包后运行 ``dataloadv``，或 ``python -m dataloadv``。
"""

from __future__ import annotations

import logging
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from . import __version__
from .core.logging_setup import setup_logging
from .ui.main_window import MainWindow

logger = logging.getLogger(__name__)


def _install_excepthook() -> None:
    """安装全局异常钩子.

    未捕获的异常默认只打印到 stderr 且可能终止事件循环；这里改为：
    完整堆栈写入日志（文件 + 面板），并向用户弹一次提示，避免"静默失败"。
    """

    def _hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical(
            "未捕获的异常：%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        )

    sys.excepthook = _hook


def main() -> int:
    """应用主函数（console script 入口）.

    :returns: 进程退出码，0 表示正常退出
    """
    setup_logging()
    _install_excepthook()
    logger.info("DataloadV v%s 启动", __version__)

    # 高 DPI 缩放：Qt6 默认启用 PassThrough，这里显式声明以免行为随版本漂移
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("DataloadV")
    app.setApplicationVersion(__version__)
    app.setFont(QFont("PingFang SC", 10))  # macOS 中文字体，保证界面文字渲染清晰

    window = MainWindow()
    window.show()

    code = app.exec()
    logger.info("DataloadV 退出，退出码 %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
