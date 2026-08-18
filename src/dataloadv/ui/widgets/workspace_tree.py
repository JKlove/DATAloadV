"""工作区 Dock：导入来源 → 录制 的树 + 文本筛选.

交互约定：
- 双击录制项 → 发 ``open_requested(str)``（meta.path），主窗口后台打开浏览 tab
- 筛选框对"文件名/被试/格式"做包含匹配，命中的保留（来源节点无命中则隐藏）
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLineEdit,
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


class WorkspaceTree(QWidget):
    """左侧工作区面板（树 + 筛选框）."""

    open_requested = Signal(str)  # meta.path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(S.FILTER_HINT)
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._apply_filter)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_TREE_COLS))
        self._tree.setHeaderLabels([c[0] for c in _TREE_COLS])
        for i, (_, w) in enumerate(_TREE_COLS):
            self._tree.setColumnWidth(i, w)
        self._tree.itemDoubleClicked.connect(self._on_double_click)

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
