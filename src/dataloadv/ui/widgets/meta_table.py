"""元数据表：全部录制条目的可排序/可筛选表格（全局 tab）.

QTableView + QAbstractTableModel + QSortFilterProxyModel 的标准组合；
1500 行量级排序/筛选无压力（纯视图模型，不触数据本体）。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QSortFilterProxyModel,
    Qt,
    QModelIndex,
    Signal,
)
from PySide6.QtWidgets import QLineEdit, QTableView, QVBoxLayout, QWidget

from ...core.recording import RecordingMeta
from ..strings_zh import S

# 列定义：字段说明见 RecordingMeta docstring
_COLS: list[tuple[str, str]] = [
    ("name", S.COL_NAME),
    ("subject", S.COL_SUBJECT),
    ("format", S.COL_FORMAT),
    ("n_channels", S.COL_CHANNELS),
    ("sfreq", S.COL_SFREQ),
    ("duration_s", S.COL_DURATION),
    ("n_events", S.COL_EVENTS),
    ("task", S.COL_TASK),
    ("run", S.COL_RUN),
    ("source", S.COL_SOURCE),
]


class MetaTableModel(QAbstractTableModel):
    """RecordingMeta 列表的只读表模型."""

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[RecordingMeta] = []

    def set_rows(self, rows: list[RecordingMeta]) -> None:
        """整体替换（导入后刷新；量级 ≤ 数千，无需增量更新）."""
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def meta_at(self, proxy_row: int) -> RecordingMeta:
        return self._rows[proxy_row]

    # Qt 模型必备
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(_COLS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _COLS[section][1]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        meta = self._rows[index.row()]
        key = _COLS[index.column()][0]
        if key == "name":
            return meta.filename
        if key == "source":
            return meta.import_source or ""
        val = getattr(meta, key, "")
        if isinstance(val, float):
            return f"{val:g}"
        return str(val)


class _FilterProxy(QSortFilterProxyModel):
    """全列包含匹配筛选."""

    def __init__(self) -> None:
        super().__init__()
        self.text = ""

    def filter_accepts(self, display: str) -> bool:
        return not self.text or self.text in display.lower()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:  # noqa: N802
        model = self.sourceModel()
        for col in range(model.columnCount()):
            idx = model.index(source_row, col, source_parent)
            if self.filter_accepts(str(model.data(idx) or "").lower()):
                return True
        return False


class MetaTableView(QWidget):
    """元数据表 tab 内容（筛选框 + 表格）."""

    open_requested = Signal(str)  # 双击行的 meta.path
    selection_changed = Signal(list)  # 当前选中行的 meta 列表（批处理输入）

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = MetaTableModel()
        self._proxy = _FilterProxy()
        self._proxy.setSourceModel(self._model)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText(S.FILTER_HINT)
        self._filter.setClearButtonEnabled(True)
        self._filter.textChanged.connect(self._on_filter)

        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.selectionModel().selectionChanged.connect(self._on_selection)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.addWidget(self._filter)
        layout.addWidget(self._table)

    # ------------------------------------------------------------ 数据/交互

    def refresh(self, metas: list[RecordingMeta]) -> None:
        """刷新数据并回到未排序状态."""
        self._model.set_rows(metas)
        self._proxy.text = self._filter.text().strip().lower()
        self._proxy.invalidateFilter()

    def _on_filter(self, text: str) -> None:
        self._proxy.text = text.strip().lower()
        self._proxy.invalidateFilter()

    def _proxy_row_meta(self, proxy_index):
        src_index = self._proxy.mapToSource(proxy_index)
        return self._model.meta_at(src_index.row())

    def _on_double_click(self, proxy_index) -> None:
        meta = self._proxy_row_meta(proxy_index)
        if meta is not None:
            self.open_requested.emit(meta.path)

    def _on_selection(self, *_args) -> None:
        metas = [self._proxy_row_meta(i) for i in self._table.selectedIndexes()]
        # ExtendedSelection 下同一行多列会产生重复 index，按 rec_id 去重
        seen: dict[str, RecordingMeta] = {}
        for m in metas:
            if m is not None:
                seen[m.rec_id] = m
        self.selection_changed.emit(list(seen.values()))

    def selected_metas(self) -> list[RecordingMeta]:
        """当前选中行（供批处理对话框取文件集）."""
        return [
            self._proxy_row_meta(i)
            for i in sorted(self._table.selectionModel().selectedRows())
        ]
