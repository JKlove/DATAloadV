"""工作区 Dock：导入来源 → 录制 的树 + 文本筛选.

交互约定：
- 双击录制项 → 发 ``open_requested(str)``（meta.path），主窗口后台打开浏览 tab
- 右键/Del 删除：录制项 → ``remove_requested([该条 path])``；来源节点 →
  ``remove_requested([该来源全部 path])``（主窗口统一确认并落库——移除只清
  工作区索引，不删磁盘数据文件）
- 筛选框对"文件名/被试/格式"做包含匹配，命中的保留（来源节点无命中则隐藏）
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QLineEdit,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.workspace import Workspace
from ..strings_zh import S

# 树列定义：(标题, 宽度像素)
_TREE_COLS = [
    (S.COL_NAME, 220),
    (S.COL_SUBJECT, 70),
    (S.COL_FORMAT, 55),
    (S.COL_SFREQ, 85),
    (S.COL_DURATION, 80),
    (S.COL_EVENTS, 60),
]


class _TreeWithDel(QTreeWidget):
    """内层树：Del/Backspace 转发删除回调（焦点在树上，容器收不到 keyPress）."""

    def __init__(self, on_delete, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_delete = on_delete  # (QTreeWidgetItem | None) → None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_delete(self.currentItem())
            return
        super().keyPressEvent(event)


class WorkspaceTree(QWidget):
    """左侧工作区面板（树 + 筛选框）."""

    open_requested = Signal(str)  # meta.path
    remove_requested = Signal(list)  # 待移除的 meta.path 列表（≥1 条；多条由主窗口确认）

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(S.FILTER_HINT)
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)

        self._tree = _TreeWithDel(self._delete_current)
        self._tree.setColumnCount(len(_TREE_COLS))
        self._tree.setHeaderLabels([c[0] for c in _TREE_COLS])
        for i, (_, w) in enumerate(_TREE_COLS):
            self._tree.setColumnWidth(i, w)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._filter)
        layout.addWidget(self._tree)

    # ------------------------------------------------------------ 数据

    def refresh(self, workspace: Workspace) -> None:
        """按工作区当前内容整体重建树（条目量 ≤ 数千，重建足够快）."""
        self._tree.clear()
        root = QTreeWidgetItem(
            [S.TREE_ROOT_FMT.format(name=workspace.name, n=len(workspace))]
        )
        root.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._tree.addTopLevelItem(root)

        for src in sorted(workspace.sources.values(), key=lambda s: s.name):
            src_item = QTreeWidgetItem([src.name, "", "", "", "", f"{len(src.recordings)}"])
            src_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            root.addChild(src_item)
            for meta in sorted(src.recordings.values(), key=lambda m: m.filename):
                item = QTreeWidgetItem(
                    [
                        meta.filename,
                        meta.subject or "",
                        meta.format,
                        f"{meta.sfreq:g}",
                        f"{meta.duration_s:.1f}",
                        str(meta.n_events),
                    ]
                )
                item.setData(0, Qt.ItemDataRole.UserRole, meta.path)  # 双击取回
                src_item.addChild(item)
        root.setExpanded(True)
        self._apply_filter(self._filter.text())

    # ------------------------------------------------------------ 交互

    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            self.open_requested.emit(path)

    def _paths_for_item(self, item: QTreeWidgetItem) -> list[str]:
        """树项 → 待移除 path 列表：录制项单条；来源节点整组；根节点空.

        根节点（工作区名）不参与移除——删全部走各来源或重新建工作区。
        """
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            return [path]
        if item.parent() is not None:  # 来源节点（根的孩子）
            return [
                item.child(j).data(0, Qt.ItemDataRole.UserRole)
                for j in range(item.childCount())
            ]
        return []

    def _on_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        paths = self._paths_for_item(item) if item is not None else []
        if not paths:
            return
        menu = QMenu(self._tree)
        label = (
            S.TREE_CTX_REMOVE
            if len(paths) == 1
            else S.TREE_CTX_REMOVE_SOURCE.format(n=len(paths))
        )
        menu.addAction(label, lambda: self.remove_requested.emit(paths))
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _delete_current(self, item) -> None:
        """Del 键入口（与右键菜单同一 remove_requested 信号）."""
        paths = self._paths_for_item(item) if item is not None else []
        if paths:
            self.remove_requested.emit(paths)

    def _apply_filter(self, text: str) -> None:
        """按包含匹配过滤（大小写不敏感）；来源节点按子节点是否有命中显隐."""
        text = text.strip().lower()
        root = self._tree.topLevelItem(0)
        if root is None:
            return
        for i in range(root.childCount()):
            src_item = root.child(i)
            any_hit = False
            for j in range(src_item.childCount()):
                child = src_item.child(j)
                hit = not text or text in child.text(0).lower() or text in child.text(1).lower()
                child.setHidden(not hit)
                any_hit = any_hit or hit
            src_item.setHidden(bool(text) and not any_hit)
