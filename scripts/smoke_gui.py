"""GUI 冒烟脚本：启动主窗口，数秒后自检并自动退出.

用途：M0 验证 + 以后每次里程碑收尾快速回归（真窗口真实渲染一次）。
运行：conda activate dlv && python scripts/smoke_gui.py
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDockWidget

from dataloadv.ui.main_window import MainWindow


def main() -> int:
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
            app.quit()  # 关键：回调内任何异常都不能阻塞退出（上次踩坑点）

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


if __name__ == "__main__":
    raise SystemExit(main())
