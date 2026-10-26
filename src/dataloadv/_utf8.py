"""非 UTF-8 locale 运行时补丁（坑 #65，v0.2.0/v0.2.2 Windows 两轮实锤）.

中文 Windows 的 ANSI 代码页是 GBK（cp936），而 Python ``open()`` 不带
encoding 时用平台默认编码——pyqtgraph ``colormap.get()`` 读自带渐变
CSV（UTF-8）即 ``UnicodeDecodeError: 'gbk' codec can't decode ...``，
浏览器构建必经 ``pg.colormap.get("turbo")`` → 打开任何数据都崩
（macOS 默认 UTF-8 故本机全绿）。同类隐患：任何第三方库按默认编码读
UTF-8 资源文件（mne/pynwb 模板同理）。

**策略沿革（为什么是运行时补丁）**：
- v0.2.1 曾用「设 ``PYTHONUTF8`` + execv 自重启」走 PEP 540——v0.2.1 拼错
  argv 打不开（坑 #66）；v0.2.2 修对后**仍然 GBK 崩**，本机决定性实验实锤：
  **PyInstaller 6.22.2 冻结解释器不应用 ``PYTHONUTF8``**（冻结 probe 实测
  ``PYTHONUTF8=1`` 下 ``sys.flags.utf8_mode`` 仍为 0）——自重启路线在冻结
  环境从根上无效，整体移除。
- 现行：包装 ``builtins.open``——文本模式且 encoding 未以任何形式指定
  （kwarg 或位置参数）时补 UTF-8。不依赖解释器启动配置（冻结环境自带
  Python 3.10 永远固定），语义等同 PEP 540 对 ``open()`` 的效果：显式
  encoding 透传、二进制不受影响、无 encoding 的写文件也变 UTF-8。

必须在 import PySide6/pyqtgraph/mne 等**之前**调用（本模块因此零第三方
依赖，且经 ``dataloadv/__init__``（纯常量）导入不触发重库加载）。
"""

from __future__ import annotations

import builtins
import os
import sys

_PATCH_FLAG = "_dataloadv_utf8_open"  # 打在包装函数上的幂等标记


def ensure_utf8_mode() -> bool:
    """中文 Windows 下给 ``builtins.open`` 补 UTF-8 默认编码；返回是否打了补丁.

    - macOS/Linux（locale 即 UTF-8）与已开 UTF-8 模式的进程：no-op；
    - Windows 非 UTF-8 模式：包装 ``builtins.open``（幂等，重复调用安全）；
      之后所有不带 encoding 的文本 ``open()`` 默认 UTF-8——pyqtgraph 渐变
      CSV、mne/pynwb 模板等第三方资源读取不再被 GBK 炸；
    - 纯运行时手段，无进程重启、无环境变量依赖（冻结环境实证无效，见模块
      docstring），任何失败模式都不影响应用启动。
    """
    if os.name != "nt" or sys.flags.utf8_mode:
        return False
    if getattr(builtins.open, _PATCH_FLAG, False):
        return False  # 已打过（幂等）
    orig_open = builtins.open

    def _utf8_open(file, mode: str = "r", *args, encoding=None, **kwargs):
        # open 签名 file, mode, buffering, encoding, errors, ...——位置
        # encoding 落在 args[1]，len(args) >= 2 说明调用方位置传了编码，
        # 连同 kwarg 形式一律尊重原值，只在"完全未指定"时补 UTF-8。
        if encoding is None:
            if "b" not in mode and len(args) < 2:
                kwargs["encoding"] = "utf-8"
            return orig_open(file, mode, *args, **kwargs)
        return orig_open(file, mode, *args, encoding=encoding, **kwargs)

    setattr(_utf8_open, _PATCH_FLAG, True)
    builtins.open = _utf8_open
    return True
