"""非 UTF-8 locale 自举（坑 #65，v0.2.0 Windows 实锤事故）.

中文 Windows 的 ANSI 代码页是 GBK（cp936），而 Python ``open()`` 不带
encoding 时用平台默认编码——pyqtgraph ``colormap.get()`` 读自带渐变
CSV（UTF-8）即 ``UnicodeDecodeError: 'gbk' codec can't decode ...``，
v0.2.0 里浏览器构建必经 ``pg.colormap.get("turbo")`` → 打开任何数据都崩
（macOS 默认 UTF-8 故本机全绿）。同类隐患：任何第三方库按默认编码读
UTF-8 资源文件（mne/pynwb 模板同理）。

治本 = PEP 540 UTF-8 模式：解释器启动时读 ``PYTHONUTF8`` 环境变量生效，
之后所有 ``open()`` 默认 UTF-8。**该模式只能在启动时开启**，故 Windows
上首次启动设好变量后 ``execv`` 自重启一次；重启后 ``sys.flags.utf8_mode``
为 1，不再触发（另设 ``DLV_UTF8_RESTARTED`` 标记双保险防异常循环）。

必须在 import PySide6/pyqtgraph/mne 等**之前**调用（本模块因此零第三方
依赖，且经 ``dataloadv/__init__``（纯常量）导入不触发重库加载）。
"""

from __future__ import annotations

import os
import sys

_RESTART_MARKER = "DLV_UTF8_RESTARTED"


def ensure_utf8_mode() -> bool:
    """Windows 非 UTF-8 模式下自重启进 UTF-8 模式；返回是否发起了重启.

    - macOS/Linux（locale 即 UTF-8）与已开 UTF-8 模式的进程：no-op；
    - Windows 首启：设 ``PYTHONUTF8=1`` 后 execv 自重启（GUI 无感，多约
      1 秒启动）；重启后本函数因 utf8_mode=1 直接返回；
    - 防循环双保险：若标记仍在但 UTF-8 模式未生效（异常环境），不再
      重启、照常运行（宁可回退原行为也不无限拉起进程）。
    """
    if os.name != "nt" or sys.flags.utf8_mode:
        return False
    if os.environ.get(_RESTART_MARKER):
        return False  # 已重启过仍未生效——异常环境，放弃（防循环）
    os.environ["PYTHONUTF8"] = "1"
    os.environ[_RESTART_MARKER] = "1"
    os.execv(sys.executable, [sys.executable, *sys.argv])
    return True  # execv 正常不返回；仅被打桩替换时可达（测试用）
