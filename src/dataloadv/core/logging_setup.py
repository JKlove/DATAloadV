"""日志基础设施.

设计：
- ``setup_logging()`` 在应用启动时调用一次：根 logger 输出到控制台 + 滚动文件
  ``~/.dataloadv/logs/dataloadv.log``（文件便于事后排查崩溃原因）
- UI 侧的日志面板（ui/widgets/log_panel.py）通过 ``attach_qt_handler()`` 拿到一个
  特殊 Handler 的引用，日志记录经 Qt 信号转发到主线程渲染——线程安全且不卡 UI
- 批处理引擎给每个任务临时挂接独立 Handler 捕获逐文件日志（M5 实现，见 batch/）

为什么用 logging 标准库而非 print：worker 线程、批处理、读取器报错统一走一个
通道，UI 面板/文件/控制台三个出口自动同步。
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

# 应用数据目录：所有可写状态（配置/日志/工作区索引）都集中在 ~/.dataloadv/
APP_DIR = Path.home() / ".dataloadv"
LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "dataloadv.log"

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """初始化根 logger（控制台 + 滚动文件）.

    幂等：重复调用不会重复挂 Handler。

    :param level: 根 logger 级别，默认 INFO
    """
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # 滚动文件：单文件 5MB，保留 3 个备份，避免长期使用撑爆磁盘
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _configured = True


class QtLogHandler(logging.Handler):
    """把日志记录转发给 UI 的桥接 Handler.

    本类只做"收集"（emit 时缓存最近若干条 + 调用回调），**不依赖 Qt**——
    真正把记录送到主线程的信号装配件在 ui/widgets/log_panel.py 中完成，
    以此保持 core/ 不 import Qt 的架构约束。UI 未启动时（纯命令行/测试）
    本 Handler 静默丢弃，不影响任何功能。
    """

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self._callback = None  # 由 UI 注入：callable(str)，线程安全性由 UI 侧保证
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def attach(self, callback) -> None:
        """注入 UI 回调；传 None 则断开（窗口关闭时调用）."""
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        if self._callback is None:
            return
        try:
            self._callback(self.format(record))
        except Exception:  # noqa: BLE001 - 日志通道绝不能反过来把应用搞崩
            pass
