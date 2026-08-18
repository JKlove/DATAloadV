"""通用后台任务工具：把任意函数放到 QThread 执行，结果经信号回主线程.

用法（UI 侧）::

    def _on_done(result):
        ...  # 已在主线程，可安全操作控件

    run_in_thread(load_big_file, path="/x/y.edf", on_done=_on_done,
                  on_error=lambda msg: QMessageBox.critical(self, "错误", msg))

设计要点：
- Worker 只在自身线程里调用目标函数；finished/failed 经 ``_MainRelay``
  （主线程 QObject）转投——回调**保证在主线程**执行，无论调用方传的是
  bound method 还是普通 lambda（M2 修复：直连 lambda 会在 worker 线程
  执行，在非 GUI 线程弹 QMessageBox 导致 macOS 上不定时进程冻结）
- 线程与 Worker 的生命周期自动管理：任务结束后线程退出并 deleteLater，
  调用方无需保存引用（内部用列表保活直至结束）
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

logger = logging.getLogger(__name__)

# 保活容器：QThread 对象必须有 Python 引用，否则执行中途被 GC 导致崩溃
_keepalive: list[QThread] = []


class _MainRelay(QObject):
    """主线程回调中转.

    worker 的信号连到本对象的槽；本对象创建于调用线程（主线程），Auto
    连接 + 跨线程发射 → 队列投递到主线程事件循环——槽里再调 Python
    回调，回调必在主线程执行（弹窗/控件操作安全）。
    """

    def __init__(self, on_done: Optional[Callable], on_error: Optional[Callable]) -> None:
        super().__init__()
        self._on_done = on_done
        self._on_error = on_error

    @Slot(object)
    def _ok(self, result) -> None:
        if self._on_done is not None:
            self._on_done(result)

    @Slot(str)
    def _err(self, msg: str) -> None:
        if self._on_error is not None:
            self._on_error(msg)


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
        """在所属工作线程的事件循环里被调用（经 started 信号触发）."""
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
    """把 ``fn(**kwargs)`` 放到新 QThread 执行，完成后回调（回调必在主线程）.

    :param fn: 目标函数（同进程直接引用即可，无需可 pickle）
    :param on_done: 成功回调，入参为返回值；None 则忽略
    :param on_error: 失败回调，入参为格式化异常文本；None 则仅记日志
    :param kwargs: 传给 fn 的关键字参数
    :returns: QThread 引用（一般无需使用；线程自动清理）
    """
    thread = QThread()
    worker = Worker(fn, kwargs)
    worker.moveToThread(thread)
    relay = _MainRelay(on_done, on_error)  # 创建于调用线程（主线程）→ 队列投递

    # 线程启动后触发 worker.run；结束后按序清理 worker → 线程 → 保活容器
    thread.started.connect(worker.run)
    worker.finished.connect(relay._ok)  # relay 亲和主线程 → 回调必在主线程
    worker.failed.connect(relay._err)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(lambda t=thread: _cleanup(t))

    # 关键保活：PySide6 的信号连接不持有 Python 侧 receiver 引用——
    # worker/relay 若只作局部变量会在触发前被 GC（线程空转、回调丢失，
    # M1 e2e 实测踩坑）。挂到 thread 属性上随线程同生共死。
    thread._dlv_worker = worker  # noqa: SLF001 - 保活约定，见注释
    thread._dlv_relay = relay  # noqa: SLF001
    _keepalive.append(thread)
    thread.start()
    return thread


def _cleanup(thread: QThread) -> None:
    """线程结束后从保活容器移除（deleteLater 触发，安全）."""
    try:
        _keepalive.remove(thread)
    except ValueError:
        pass
