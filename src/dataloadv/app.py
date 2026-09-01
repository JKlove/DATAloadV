"""应用入口.

职责：
- 创建 QApplication，配置高 DPI（绘图浅色主题在 main_window 的 pg.setConfigOptions 设置）
- 安装全局异常钩子：未捕获异常写入日志文件而不是静默崩溃
- 实例化主窗口并进入事件循环
- ``--smoke`` 冒烟自检分支：起主窗口→自检→自动退出（M10 打包产物无头验证用，
  逻辑等价 ``scripts/smoke_gui.py``，输出格式一致便于既有脚本/人眼比对）

用法：安装本包后运行 ``dataloadv``，或 ``python -m dataloadv``。
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDockWidget

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


def _run_smoke() -> int:
    """冒烟自检：启动主窗口，数秒后自检并自动退出.

    等价 ``scripts/smoke_gui.py``（打包产物无法直接跑 scripts/ 下的脚本，
    故在入口内置一份等价逻辑）。无头运行配 ``QT_QPA_PLATFORM=offscreen``。
    """
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    checks: dict[str, object] = {}

    def check_and_quit():
        """集中所有断言；任何一条失败也要保证 quit 被调用（finally）."""
        try:
            checks["title"] = win.windowTitle()
            checks["docks"] = [d.windowTitle() for d in win.findChildren(QDockWidget)]
            checks["menus"] = [m.text() for m in win.menuBar().actions()]
            checks["tabs"] = win.tabs.count()
            checks["log_widget"] = win.log_panel is not None
        finally:
            app.quit()  # 关键：回调内任何异常都不能阻塞退出（scripts/smoke_gui.py 踩过的坑）

    QTimer.singleShot(2500, check_and_quit)
    app.exec()

    print("窗口标题:", checks.get("title"))
    print("Dock:", checks.get("docks"))
    print("菜单:", checks.get("menus"))
    print("Tab数:", checks.get("tabs"))
    ok = (
        checks.get("title")
        and len(checks.get("docks", [])) >= 3
        and len(checks.get("menus", [])) >= 4
        and checks.get("tabs", 0) >= 1
        and checks.get("log_widget")
    )
    print("SMOKE", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    """应用主函数（console script 入口）.

    :param argv: 命令行参数，缺省取 ``sys.argv[1:]``（测试可显式传入）
    :returns: 进程退出码，0 表示正常退出
    """
    parser = argparse.ArgumentParser(prog="dataloadv", description="DataloadV 电生理数据平台")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="冒烟自检：启动主窗口自检后自动退出（打包产物无头验证用）",
    )
    args = parser.parse_args(argv)

    setup_logging()
    _install_excepthook()
    logger.info("DataloadV v%s 启动", __version__)

    if args.smoke:
        logger.info("--smoke 自检模式")
        return _run_smoke()

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
