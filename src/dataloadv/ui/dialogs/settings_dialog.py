"""设置对话框：并发线程 / 缓存预算 / 默认导出目录（AppSettings 的三个字段）.

保存即 ``AppSettings.save()`` + ``apply()``——缓存预算写进 LoadedRawCache
单例立即生效，无需重启；批处理对话框下次打开时读到新默认线程数。
"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ...core.app_settings import AppSettings
from ...core.recording import LoadedRawCache
from ..strings_zh import S

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """三个设置项的小对话框（确定=保存并应用，取消=不保存）."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.SETTINGS_TITLE)
        self._settings = AppSettings.load()
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._workers = QSpinBox()
        self._workers.setRange(1, 8)
        self._workers.setValue(self._settings.n_workers)
        self._workers.setToolTip("批处理对话框的默认并发线程数（每批仍可单独调整）")
        form.addRow(S.SETTINGS_LBL_WORKERS, self._workers)

        self._cache = QDoubleSpinBox()
        self._cache.setRange(0.1, 64.0)
        self._cache.setDecimals(1)
        self._cache.setSingleStep(0.5)
        self._cache.setValue(self._settings.cache_gb)
        cur = LoadedRawCache.instance().byte_budget / 1024**3
        form.addRow(S.SETTINGS_LBL_CACHE, self._cache)
        form.addRow("", QLabel(f"（当前生效：{cur:.1f} GB；修改后立即生效）"))

        self._dir = QLineEdit(self._settings.export_dir)
        row = QHBoxLayout()
        row.addWidget(self._dir, 1)
        btn = QPushButton(S.SETTINGS_BTN_BROWSE)
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        form.addRow(S.SETTINGS_LBL_EXPORT_DIR, row)

        lay.addLayout(form)

        actions = QHBoxLayout()
        btn_ok = QPushButton("保存")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_save)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        lay.addLayout(actions)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(self, S.SETTINGS_LBL_EXPORT_DIR, self._dir.text())
        if d:
            self._dir.setText(d)

    def _on_save(self) -> None:
        """校验导出目录存在性（填了但不存在 → 警告不保存）."""
        export_dir = self._dir.text().strip()
        if export_dir and not os.path.isdir(export_dir):
            QMessageBox.warning(self, S.SETTINGS_TITLE, f"目录不存在：{export_dir}")
            return
        self._settings.n_workers = self._workers.value()
        self._settings.cache_gb = self._cache.value()
        self._settings.export_dir = export_dir
        self._settings.save()
        self._settings.apply()
        logger.info("设置已更新：workers=%d cache=%.1fGB export_dir=%s",
                    self._settings.n_workers, self._settings.cache_gb,
                    self._settings.export_dir or "（未设）")
        self.accept()
