"""PyInstaller 打包入口 shim.

为什么不用 app.py 直接做 Analysis 入口：console_script `dataloadv` 指向
``dataloadv.app:main``，从 main() 进才能保证初始化顺序（日志→异常钩子→主窗口）
与安装版完全一致；直接 Analysis app.py 会以模块脚本方式执行，绕过同一入口。
此文件即 console_script 的等价物，5 行，不含任何业务逻辑。
"""

from dataloadv.app import main

raise SystemExit(main())
