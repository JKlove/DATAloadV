"""会话状态：主窗口与各视图/对话框共享的纯数据中枢.

刻意不放业务逻辑：只是"当前工作区 + 已打开 Recording + 当前选择"的容器，
配少量信号（Qt 侧观察者），让工作区树、元数据表、浏览器 tab 保持同步。
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from ..core.recording import Recording
from ..core.workspace import Workspace

logger = logging.getLogger(__name__)


class SessionState(QObject):
    """应用会话状态.

    :signals:
        workspace_changed: 工作区内容变化（导入/删除后，树与表全量刷新）
        recording_opened(object): 浏览 tab 请求（携带 Recording）
        selection_changed(list[RecordingMeta]): 元数据表多选变化（批处理输入）
    """

    workspace_changed = Signal()
    recording_opened = Signal(object)
    selection_changed = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.workspace = Workspace.load(Workspace.current_name())
        # 打开中的 Recording（浏览 tab 存活期间持有；tab 关闭时 unload）
        self.open_recordings: dict[str, Recording] = {}  # rec_id -> Recording

    # ------------------------------------------------------------ 工作区

    def reload_workspace(self, name: str) -> None:
        """切换/新建工作区."""
        for rec in self.open_recordings.values():
            rec.unload()
        self.open_recordings.clear()
        self.workspace = Workspace.load(name)
        Workspace.set_current(name)
        self.workspace_changed.emit()

    def notify_workspace_changed(self) -> None:
        """工作区内容变更后调用（保存已由调用方完成）."""
        self.workspace_changed.emit()

    # ------------------------------------------------------------ 打开/关闭

    def open_recording(self, meta_path: str) -> Recording | None:
        """按路径打开（或复用已打开的）Recording，发 recording_opened 信号.

        打开动作在后台线程执行（大文件头读取也要几十 ms），调用方是
        workers 的 on_done 回调；本方法只在主线程调用。
        """
        existing = next(
            (r for r in self.open_recordings.values() if r.meta.path == meta_path), None
        )
        if existing is not None:
            self.recording_opened.emit(existing)
            return existing
        return None  # 未打开过的走后台 open_file 流程（见 MainWindow._open_recording_async）

    def attach_open(self, rec: Recording) -> None:
        """后台打开完成后登记并广播."""
        self.open_recordings[rec.meta.rec_id] = rec
        self.recording_opened.emit(rec)

    def close_recording(self, rec: Recording) -> None:
        """浏览 tab 关闭：释放数据、移出登记."""
        rec.unload()
        self.open_recordings.pop(rec.meta.rec_id, None)
