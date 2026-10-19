"""PyInstaller 打包入口 shim.

为什么不用 app.py 直接做 Analysis 入口：console_script `dataloadv` 指向
``dataloadv.app:main``，从 main() 进才能保证初始化顺序（日志→异常钩子→主窗口）
与安装版完全一致；直接 Analysis app.py 会以模块脚本方式执行，绕过同一入口。
此文件即 console_script 的等价物，不含任何业务逻辑。

ensure_utf8_mode()（坑 #65）必须在 import dataloadv.app（连带
PySide6/pyqtgraph/mne）**之前**执行：中文 Windows ANSI=GBK，pyqtgraph
colormap.get 按平台默认编码读 UTF-8 渐变 CSV 必炸，Windows 首启自重启
一次进 PEP 540 UTF-8 模式（非 Windows 平台 no-op）。
"""

from dataloadv._utf8 import ensure_utf8_mode

ensure_utf8_mode()

from dataloadv.app import main  # noqa: E402（须在 UTF-8 自举之后）

raise SystemExit(main())
