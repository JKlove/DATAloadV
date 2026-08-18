"""特征结果视图（中央 tab）：长表浏览 + 导出（CSV / HDF5 / 分段数据）.

数据流（架构规则 #2：UI 不做计算）：
- 表格只读展示 ``FeatureTable.df``（QAbstractTableModel + 排序过滤代理，
  数万行级别流畅——288 段×22 通道×13 特征 ≈ 8 万行是常态）
- 导出按钮 → ``run_in_thread`` 里调 export 层写文件 + provenance sidecar
  → 主线程弹完成提示（文件清单）

导出的 sidecar 内容（管线+特征+文件清单）由构造参数传入——本视图不回头
问管线面板，快照式记录当次计算的确切配置。
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ...batch.results import COLUMNS, COLUMNS_ZH, FeatureTable
from ...export import epochs_io, features_io, provenance
from ...workers.generic import run_in_thread
from ..strings_zh import S

logger = logging.getLogger(__name__)


class _LongTableModel(QAbstractTableModel):
    """长表 → Qt 表模型（只读；列头用中文）."""

    def __init__(self) -> None:
        super().__init__()
        self._df = None

    def set_table(self, table: FeatureTable) -> None:
        self.beginResetModel()
        self._df = table.df
        self.endResetModel()

    # Qt 命名约定的必要方法
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return COLUMNS_ZH[COLUMNS[section]]
        return section + 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        v = self._df.iloc[index.row(), index.column()]
        # 文件级行的 epoch_index/event_code 是 <NA>/None → 空单元格
        if v is None or v is pd.NA or (isinstance(v, float) and np.isnan(v)):
            return "" if role == Qt.ItemDataRole.DisplayRole else None
        if role == Qt.ItemDataRole.UserRole:
            # 排序角色（Qt6 无预定义 SortRole，用 UserRole 惯例）：
            # 数值列返回 float——字符串排序会让 "10" < "2" 乱序
            return float(v) if isinstance(v, (float, int, np.integer)) else str(v)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if isinstance(v, float):
            return f"{v:.6g}"  # 特征值跨数量级：6 位有效数字足够且省宽
        return str(v)


class FeatureTableView(QWidget):
    """一个特征结果 tab.

    :param table: FeatureTable（计算产物）
    :param ctx: 该次计算的 ProcessingContext（分段导出用；None=无分段）
    :param pipeline_dicts: 管线步骤 dict 列表（sidecar）
    :param feature_dicts: 特征提取器 dict 列表（sidecar）
    """

    def __init__(
        self,
        table: FeatureTable,
        ctx=None,
        pipeline_dicts: Optional[list[dict]] = None,
        feature_dicts: Optional[list[dict]] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._table = table
        self._ctx = ctx
        self._pipeline_dicts = pipeline_dicts or []
        self._feature_dicts = feature_dicts or []
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        top = QHBoxLayout()
        self._summary = QLabel(self._table.summary_zh() if len(self._table) else S.FEAT_TABLE_EMPTY)
        top.addWidget(self._summary, 1)
        self._btn_csv = QPushButton(S.FEAT_EXPORT_CSV)
        self._btn_h5 = QPushButton(S.FEAT_EXPORT_H5)
        self._btn_csv.clicked.connect(lambda: self._export_features("csv"))
        self._btn_h5.clicked.connect(lambda: self._export_features("hdf5"))
        top.addWidget(self._btn_csv)
        top.addWidget(self._btn_h5)
        if self._ctx is not None and self._ctx.stage == "epochs":
            self._btn_epochs = QPushButton(S.FEAT_EXPORT_EPOCHS)
            self._btn_epochs.clicked.connect(self._export_epochs)
            top.addWidget(self._btn_epochs)
        lay.addLayout(top)

        self._model = _LongTableModel()
        self._model.set_table(self._table)
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.ItemDataRole.UserRole)  # 数值列按 float 排序
        view = QTableView()
        view.setModel(self._proxy)
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.horizontalHeader().setStretchLastSection(False)
        lay.addWidget(view, 1)

    # ------------------------------------------------------------------ 导出

    def _export_features(self, fmt: str) -> None:
        """特征表导出（CSV / HDF5）+ 自动 sidecar；worker 里写盘."""
        suffix = "csv (*.csv)" if fmt == "csv" else "h5 (*.h5)"
        path, _ = QFileDialog.getSaveFileName(
            self, S.FEAT_EXPORT_CSV if fmt == "csv" else S.FEAT_EXPORT_H5,
            "features.csv" if fmt == "csv" else "features.h5", suffix,
        )
        if not path:
            return
        self._set_busy(True)

        def job(path=path, fmt=fmt):
            files = (
                features_io.export_features_csv(self._table, path)
                if fmt == "csv" else [features_io.export_features_hdf5(self._table, path)]
            )
            sidecar = provenance.write_provenance(
                path, pipeline=self._pipeline_dicts, features=self._feature_dicts,
                recordings=self._table.recording_names(),
                extra={"exported": [f.name for f in files], "format": fmt},
            )
            return [*files, sidecar]

        run_in_thread(
            job,
            on_done=self._on_export_done,
            on_error=lambda m: (self._set_busy(False),
                                QMessageBox.critical(self, S.FEAT_EXPORT_FAIL_TITLE, m)),
        )

    def _export_epochs(self) -> None:
        """分段数据导出：HDF5 或 FIF（菜单选择格式）."""
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        h5_act = menu.addAction(S.FEAT_EXPORT_EPOCHS_H5)
        fif_act = menu.addAction(S.FEAT_EXPORT_EPOCHS_FIF)
        act = menu.exec(self.mapToGlobal(self._btn_epochs.rect().bottomLeft()))
        if act not in (h5_act, fif_act):
            return
        fmt = "hdf5" if act is h5_act else "fif"
        default = "epochs.h5" if fmt == "hdf5" else "epochs-epo.fif"
        path, _ = QFileDialog.getSaveFileName(
            self, S.FEAT_EXPORT_EPOCHS, default,
            "HDF5 (*.h5)" if fmt == "hdf5" else "FIF (*.fif)",
        )
        if not path:
            return
        self._set_busy(True)

        def job(path=path, fmt=fmt):
            out = epochs_io.export_epochs(self._ctx.epochs, path, fmt=fmt)
            sidecar = provenance.write_provenance(
                out, pipeline=self._pipeline_dicts, features=[],
                recordings=self._table.recording_names(),
                extra={"exported": out.name, "format": fmt, "kind": "epochs"},
            )
            return [out, sidecar]

        run_in_thread(
            job,
            on_done=self._on_export_done,
            on_error=lambda m: (self._set_busy(False),
                                QMessageBox.critical(self, S.FEAT_EXPORT_FAIL_TITLE, m)),
        )

    def _on_export_done(self, files: list) -> None:
        self._set_busy(False)
        QMessageBox.information(
            self, S.FEAT_EXPORT_DONE_TITLE,
            S.FEAT_EXPORT_DONE_FMT.format(
                n=len(files), files="\n".join(str(f) for f in files)),
        )

    def _set_busy(self, busy: bool) -> None:
        for btn in (getattr(self, "_btn_csv", None), getattr(self, "_btn_h5", None),
                    getattr(self, "_btn_epochs", None)):
            if btn is not None:
                btn.setEnabled(not busy)
        self.window().statusBar().showMessage(
            S.FEAT_MSG_RUNNING if busy else S.STATUS_READY)

    # ------------------------------------------------------------------ 释放

    def teardown(self) -> None:
        """tab 关闭：释放 ctx 数据（epochs 数组可达数十 MB）."""
        self._table = None
        if self._ctx is not None:
            self._ctx.raw = None
            self._ctx.epochs = None
        self._ctx = None
        logger.info("特征结果 tab 已释放")
