"""通用后台任务工具：把任意函数放到 QThread 执行，结果经信号回主线程.

用法（UI 侧）::

    def _on_done(result):
        ...  # 已在主线程，可安全操作控件

    run_in_thread(load_big_file, path="/x/y.edf", on_done=_on_done,
                  on_error=lambda msg: QMessageBox.critical(self, "错误", msg))

设计要点：
- Worker 只在自身线程里调用目标函数；finished/failed 通过 Qt 信号（默认
  队列连接）投递回主线程，满足"跨线程只传纯 Python 对象"的架构规则
- 线程与 Worker 的生命周期自动管理：任务结束后线程退出并 deleteLater，
  调用方无需保存引用（内部用列表保活直至结束）
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger(__name__)

# 保活容器：QThread 对象必须有 Python 引用，否则执行中途被 GC 导致崩溃
_keepalive: list[QThread] = []


class Worker(QObject):
    """在工作线程中执行一个目标函数的 QObject.

    :signals:
        finished(object): 目标函数成功返回，携带返回值
        failed(str): 目标函数抛异常，携带格式化后的错误文本
    """

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[..., Any], kwargs: dict[str, Any]) -> None:
        super().__init__()
        self._fn = fn
        self._kwargs = kwargs

    def run(self) -> None:
        """在所属工作线程的事件循环里被调用（经 QMetaObject.invokeMethod 触发）."""
        try:
            result = self._fn(**self._kwargs)
        except Exception:  # noqa: BLE001 - 后台任务的任何异常都转为 failed 信号
            msg = "".join(traceback.format_exc())
            logger.error("后台任务失败：%s", msg)
            self.failed.emit(msg)
        else:
            self.finished.emit(result)


def run_in_thread(
    fn: Callable[..., Any],
    on_done: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
    **kwargs: Any,
) -> QThread:
    """把 ``fn(**kwargs)`` 放到新 QThread 执行，完成后回调（回调在主线程）.

    :param fn: 目标函数（必须可 pickle 无关——同进程直接引用即可）
    :param on_done: 成功回调，入参为返回值；None 则忽略
    :param on_error: 失败回调，入参为格式化异常文本；None 则仅记日志
    :param kwargs: 传给 fn 的关键字参数
    :returns: QThread 引用（一般无需使用；线程自动清理）
    """
    thread = QThread()
    worker = Worker(fn, kwargs)
    worker.moveToThread(thread)

    # 线程启动后触发 worker.run；结束后按序清理 worker → 线程 → 保活容器
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda t=thread: _cleanup(t))

    if on_done is not None:
        worker.finished.connect(on_done)
    if on_error is not None:
        worker.failed.connect(on_error)

    _keepalive.append(thread)
    thread.start()
    return thread


def _cleanup(thread: QThread) -> None:
    """线程结束后从保活容器移除（deleteLater 触发，安全）."""
    try:
        _keepalive.remove(thread)
    except ValueError:
        pass
