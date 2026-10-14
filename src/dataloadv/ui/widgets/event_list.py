"""事件 marker 列表（M11）：双击行跳波形到该事件.

需求（2026-09-24 用户提出）：有标记的数据能看到事件清单（名称/时间/样本点），
双击某行 → 波形快速定位到该事件位置。位置沿革：M11 初版为浏览器底部横条；
M12（2026-10-13）按用户截图移入左栏通道列表下方（纵向面板，5 列
ResizeToContents 自适应列宽）。

结构（照 meta_table.py 的 QTableView + Model + Proxy 先例）：
- ``_EventListModel``：5 列（序号/名称/时间/样本点/持续），数值列 UserRole
  返数值（坑 #30：Qt6 无 SortRole，字符串排序会让 "100.0" < "20.0" 乱序）；
  名称列优先显示 EventTable.label（GDF 已映射中文），空则退化 code，且
  前景色用 event_color——与波形里的事件竖线同色，列表↔波形视觉对应。
- ``EventListView``：对外 ``jump_requested(float)`` 信号（onset 秒），
  双击行经 proxy→source 映射发射（meta_table 双击开 tab 同款）。
  跳转落点是 SignalBrowserView._center_at——事件线/时间标签/总览滑块
  全部经 sigRangeChanged 链自动联动，无需额外同步代码。

无事件时面板**常驻显示空态**（2026-09-24 用户裁定：不自动隐藏，面板在、
无数据行）——表格上覆盖居中灰字 S.EVENT_LANE_NONE（"无事件"，与事件条
占位同款文案），有事件时隐藏。
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...core.recording import EventTable
from ..strings_zh import S
from .event_lane import event_color

# 列定义：(字段 key, 中文标题, 是否数值列)——序号列放最前且参与排序
_COLS: list[tuple[str, str, bool]] = [
    ("idx", S.COL_EVENT_IDX, True),
    ("name", S.COL_EVENT_NAME, False),
    ("time", S.COL_EVENT_TIME, True),
    ("sample", S.COL_EVENT_SAMPLE, True),
    ("duration", S.COL_EVENT_DURATION, True),
]


class _EventListModel(QAbstractTableModel):
    """EventTable 的只读表模型：行=事件，列=_COLS.

    样本点（latency）= round(onset × sfreq)——EEG 领域习惯用样本索引
    标记事件位置；序号列 = 排序前的事件原始序号（与 EventTable 行号一致，
    排序后不重排，方便对照事件条/导出表）。
    """

    def __init__(self) -> None:
        super().__init__()
        self._events = EventTable()
        self._sfreq = 1.0

    def set_events(self, events: EventTable, sfreq: float) -> None:
        """整体重填（打开/换录制时调一次）；sfreq 用于样本点换算."""
        self.beginResetModel()
        self._events = events
        self._sfreq = float(sfreq) if sfreq > 0 else 1.0
        self.endResetModel()

    # ------------------------------------------------------------------ Qt 契约
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._events)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(_COLS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return _COLS[section][1]
        return None

    def _display_name(self, row: int) -> str:
        """名称列文本：label 优先（GDF 已映射中文），空则退化 code."""
        label = self._events.label[row].strip() if row < len(self._events.label) else ""
        return label or self._events.code[row]

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if row >= len(self._events):
            return None
        key, _title, numeric = _COLS[col]
        ev = self._events
        if role == Qt.ItemDataRole.DisplayRole:
            if key == "idx":
                return str(row + 1)
            if key == "name":
                return self._display_name(row)
            if key == "time":
                return f"{float(ev.onset[row]):.3f}"
            if key == "sample":
                return str(int(round(float(ev.onset[row]) * self._sfreq)))
            return f"{float(ev.duration[row]):.3f}"
        if role == Qt.ItemDataRole.UserRole:
            # 排序角色（坑 #30）：数值列必须给数值，否则按字符串排序乱序
            if key == "idx":
                return row + 1
            if key == "time":
                return float(ev.onset[row])
            if key == "sample":
                return int(round(float(ev.onset[row]) * self._sfreq))
            if key == "duration":
                return float(ev.duration[row])
            return self._display_name(row)
        if (role == Qt.ItemDataRole.ForegroundRole and key == "name"
                and len(ev.code) > 0):
            # 名称列与波形事件竖线同色（event_color 按码取色）
            return QBrush(QColor(event_color(ev.code[row], ev.code)))
        return None


class EventListView(QWidget):
    """事件清单面板：双击行发 jump_requested(onset 秒)，浏览器 _center_at 接收."""

    jump_requested = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._model = _EventListModel()
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)  # 数值排序（坑 #30）
        self._table = QTableView()
        self._table.setModel(self._proxy)
        # 表配置照 meta_table 先例：整行选择 + 只读 + 交替行色 + 末列拉伸
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        # 列宽自适应内容（M12 移入左栏后宽度有限，固定列宽会截断中文名）
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)  # # 列已有序号
        self._table.setSortingEnabled(True)
        # 启用排序会触发一次隐式初始排序（本 PySide6 构建实测按第 0 列降序，
        # 行为不可依赖）——显式定为时间列升序（事件清单的天然顺序），箭头同步
        self._table.horizontalHeader().setSortIndicator(
            2, Qt.SortOrder.AscendingOrder)
        self._table.doubleClicked.connect(self._on_double_click)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._table)
        # 空态覆盖层：居中灰字"无事件"（表头保留——面板常驻、仅无数据行）。
        # 作为本控件的子 QLabel 盖在表格上，resizeEvent 同步几何
        self._empty_lbl = QLabel(S.EVENT_LANE_NONE, self)
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #888888;")
        self._empty_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._empty_lbl.raise_()

    def resizeEvent(self, event) -> None:
        """尺寸变化时空态提示层跟随表格几何."""
        super().resizeEvent(event)
        self._empty_lbl.setGeometry(self._table.geometry())

    # ------------------------------------------------------------------ 对外
    def set_events(self, events: EventTable, sfreq: float) -> None:
        """重填事件表（浏览器在挂载 EventLane 的同位置调用）.

        空表切换到空态提示层（"无事件"），有数据恢复表格。
        """
        self._model.set_events(events, sfreq)
        empty = len(events) == 0
        self._empty_lbl.setVisible(empty)
        self._empty_lbl.setGeometry(self._table.geometry())

    def row_count(self) -> int:
        """当前事件行数（浏览器决定面板显隐用）."""
        return len(self._model._events)

    def onset_at_row(self, proxy_row: int) -> float | None:
        """按 proxy 行号取事件 onset 秒（越界返回 None）."""
        source_row = self._proxy.mapToSource(
            self._proxy.index(proxy_row, 0)).row()
        ev = self._model._events
        if 0 <= source_row < len(ev):
            return float(ev.onset[source_row])
        return None

    # ------------------------------------------------------------------ 内部
    def _on_double_click(self, proxy_index: QModelIndex) -> None:
        """双击行 → 发射该事件 onset（meta_table 双击开 tab 同款路径）."""
        if not proxy_index.isValid():
            return
        source_row = self._proxy.mapToSource(proxy_index).row()
        ev = self._model._events
        if 0 <= source_row < len(ev):
            self.jump_requested.emit(float(ev.onset[source_row]))
