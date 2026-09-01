"""批处理对话框：文件勾选 → 运行（进度页）→ 结果交接.

线程模型（架构规则 #2 的标准形状）：
- 引擎 ``run()`` 整体丢进一个后台 QThread（workers.generic.run_in_thread）
- 引擎回调（on_progress / on_file_done）在**worker 线程**执行 → 只往
  ``queue.Queue`` 塞事件，绝不触碰控件
- 主线程 QTimer 每 150 ms 排空队列 → 喂给 BatchProgressView——UI 全程
  响应（事件循环从不被批处理占住），这也是 M5 验收标准之一
- 「取消」= engine.cancel()（threading.Event）——立即返回，引擎在
  当前步骤边界停止；对话框关闭时若仍在跑也自动请求取消

管线来源：右侧管线面板的当前步骤链 + 特征链（零转换 dict 快照）——
"面板上组好的链"与"批处理跑的链"是同一份描述，可复现性由此保证。
"""

from __future__ import annotations

import logging
import queue
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ...batch.engine import BatchEngine
from ...batch.jobs import JobSpec, PipelineSpec
from ...core.app_settings import AppSettings
from ...core.recording import RecordingMeta
from ..strings_zh import S
from ..widgets.batch_view import BatchProgressView

logger = logging.getLogger(__name__)


class BatchDialog(QDialog):
    """两页批处理对话框（选择页 ↔ 运行页）.

    :param get_metas: 返回当前工作区全部 RecordingMeta（选择页数据源）
    :param get_pipeline_dicts: 返回步骤链 dict 快照（pipeline_panel.pipeline_dicts）
    :param get_feature_dicts: 返回特征链 dict 快照（pipeline_panel.feature_dicts）
    :signal batch_finished(object): 整批结束且至少有一行特征——携带
        {"table", "summary", "job"}，主窗口据此开特征结果 tab
    """

    batch_finished = Signal(object)

    def __init__(
        self,
        get_metas: Callable[[], list[RecordingMeta]],
        get_pipeline_dicts: Callable[[], list[dict]],
        get_feature_dicts: Callable[[], list[dict]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(S.BATCH_DLG_TITLE)
        self.resize(760, 560)
        self._get_metas = get_metas
        self._get_pipeline = get_pipeline_dicts
        self._get_features = get_feature_dicts
        self._settings = AppSettings.load()
        self._engine: BatchEngine | None = None
        self._events: queue.Queue = queue.Queue()  # worker 线程 → 主线程的事件口
        self._build_ui()
        self._fill_files()
        self._refresh_pipeline_line()

        # 事件泵：运行期间每 150 ms 排空队列（worker 回调只塞队列）
        self._pump = QTimer(self)
        self._pump.setInterval(150)
        self._pump.timeout.connect(self._drain_events)

    # ================================================================== UI

    def _build_ui(self) -> None:
        self._stack = QStackedLayout(self)
        self._stack.addWidget(self._build_select_page())
        self._progress = BatchProgressView()
        self._progress.cancel_requested.connect(self._on_cancel_clicked)
        self._stack.addWidget(self._progress)

    def _build_select_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)

        lay.addWidget(QLabel(S.BATCH_LBL_FILES))
        row = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(S.BATCH_LBL_FILTER)
        self._filter.textChanged.connect(self._apply_filter)
        btn_all = QPushButton(S.BATCH_BTN_ALL)
        btn_none = QPushButton(S.BATCH_BTN_NONE)
        btn_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_none.clicked.connect(lambda: self._set_all_checked(False))
        row.addWidget(self._filter, 1)
        row.addWidget(btn_all)
        row.addWidget(btn_none)
        lay.addLayout(row)

        self._files = QListWidget()
        self._files.itemChanged.connect(lambda _it: self._update_count())
        lay.addWidget(self._files, 1)
        self._count = QLabel("")
        lay.addWidget(self._count)

        lay.addWidget(QLabel(S.BATCH_LBL_PIPELINE))
        self._pipeline_line = QLabel("")
        self._pipeline_line.setWordWrap(True)
        lay.addWidget(self._pipeline_line)

        box = QGroupBox(S.BATCH_LBL_EXPORT)
        grid = QGridLayout(box)
        self._cb_csv = QCheckBox(S.BATCH_CB_CSV)
        self._cb_h5 = QCheckBox(S.BATCH_CB_H5)
        self._cb_csv.setChecked(True)
        grid.addWidget(self._cb_csv, 0, 0)
        grid.addWidget(self._cb_h5, 0, 1)
        # M9：逐文件连续数据导出（特征表导出相互独立，可只勾其一）
        self._cb_raw_edf = QCheckBox(S.BATCH_CB_RAW_EDF)
        self._cb_raw_fif = QCheckBox(S.BATCH_CB_RAW_FIF)
        grid.addWidget(self._cb_raw_edf, 0, 2)
        grid.addWidget(self._cb_raw_fif, 0, 3)
        grid.addWidget(QLabel(S.BATCH_LBL_NAME), 1, 0)
        self._name = QLineEdit("batch_features")
        grid.addWidget(self._name, 1, 1)
        grid.addWidget(QLabel(S.BATCH_LBL_DIR), 2, 0)
        dir_row = QHBoxLayout()
        self._dir = QLineEdit(self._settings.export_dir)
        btn_browse = QPushButton(S.BATCH_BTN_BROWSE)
        btn_browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir, 1)
        dir_row.addWidget(btn_browse)
        grid.addLayout(dir_row, 2, 1)
        grid.addWidget(QLabel(S.BATCH_LBL_WORKERS), 3, 0)
        self._workers = QSpinBox()
        self._workers.setRange(1, 8)
        self._workers.setValue(self._settings.n_workers)
        grid.addWidget(self._workers, 3, 1)
        lay.addWidget(box)

        actions = QHBoxLayout()
        self._btn_run = QPushButton(S.BATCH_BTN_RUN)
        self._btn_run.setDefault(True)
        self._btn_run.clicked.connect(self._on_run_clicked)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.reject)
        actions.addStretch(1)
        actions.addWidget(btn_close)
        actions.addWidget(self._btn_run)
        lay.addLayout(actions)
        return page

    # ------------------------------------------------------------- 选择页数据

    def _fill_files(self) -> None:
        """按工作区录制清单填选择页（文件名 + 被试提示；默认全不勾）."""
        self._files.blockSignals(True)
        self._files.clear()
        for meta in self._get_metas():
            label = meta.filename
            if meta.subject:
                label += f"（{meta.subject}）"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, meta.path)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            self._files.addItem(it)
        self._files.blockSignals(False)
        self._update_count()

    def _apply_filter(self, text: str) -> None:
        """过滤（隐藏不匹配行；勾选状态保留）."""
        text = text.strip().lower()
        for i in range(self._files.count()):
            it = self._files.item(i)
            it.setHidden(bool(text) and text not in it.text().lower())

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self._files.blockSignals(True)
        for i in range(self._files.count()):
            if not self._files.item(i).isHidden():  # 只动过滤后可见行
                self._files.item(i).setCheckState(state)
        self._files.blockSignals(False)
        self._update_count()

    def _selected_paths(self) -> list[str]:
        out = []
        for i in range(self._files.count()):
            it = self._files.item(i)
            if it.checkState() == Qt.CheckState.Checked and not it.isHidden():
                out.append(it.data(Qt.ItemDataRole.UserRole))
        return out

    def _update_count(self) -> None:
        self._count.setText(S.BATCH_LBL_SELECTED_FMT.format(
            n=len(self._selected_paths()), total=self._files.count()))

    def _refresh_pipeline_line(self) -> None:
        """管线摘要（打开对话框时取面板快照；特征空给醒目提示）."""
        spec = PipelineSpec(steps=self._get_pipeline(), features=self._get_features())
        self._pipeline_line.setText(spec.summary_zh())

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, S.BATCH_LBL_DIR, self._dir.text())
        if d:
            self._dir.setText(d)

    # ================================================================== 运行

    def _on_run_clicked(self) -> None:
        """校验 → 组 JobSpec → 切运行页 → 后台线程起引擎."""
        paths = self._selected_paths()
        if not paths:
            QMessageBox.warning(self, S.BATCH_DLG_TITLE, S.BATCH_MSG_NO_FILES)
            return
        try:
            spec = PipelineSpec(steps=self._get_pipeline(), features=self._get_features())
            spec.resolved_steps()  # 启动前校验（未知步骤/参数非法在此报中文错）
            spec.resolved_features()
        except Exception as e:  # noqa: BLE001 - StepError/FeatureError 都给用户看
            QMessageBox.warning(self, S.BATCH_DLG_TITLE,
                                f"{S.BATCH_MSG_BAD_PIPELINE}：\n{e}")
            return
        if not spec.features:
            QMessageBox.warning(self, S.BATCH_DLG_TITLE, S.BATCH_MSG_NO_FEATURES)
            return
        export_dir = self._dir.text().strip()
        wants_feat = self._cb_csv.isChecked() or self._cb_h5.isChecked()
        wants_raw = self._cb_raw_edf.isChecked() or self._cb_raw_fif.isChecked()
        if (wants_feat or wants_raw) and not export_dir:
            QMessageBox.warning(self, S.BATCH_DLG_TITLE, S.BATCH_MSG_NO_EXPORT_DIR)
            return

        job = JobSpec(
            name=self._name.text().strip() or "batch_features",
            paths=paths,
            pipeline=spec,
            n_workers=self._workers.value(),
            export_csv=self._cb_csv.isChecked(),
            export_hdf5=self._cb_h5.isChecked(),
            export_raw_edf=self._cb_raw_edf.isChecked(),
            export_raw_fif=self._cb_raw_fif.isChecked(),
            export_dir=export_dir if (wants_feat or wants_raw) else "",
        )
        # 记住本次导出目录（下次对话框直接带上）
        if export_dir:
            self._settings.export_dir = export_dir
            self._settings.save()

        self._engine = BatchEngine(
            job,
            on_file_done=lambda r: self._events.put(("file", r)),
            on_progress=lambda d, t, n: self._events.put(("progress", d, t, n)),
        )
        while not self._events.empty():  # 清掉上一批残留
            self._events.get_nowait()
        self._progress.begin(paths)
        self._stack.setCurrentIndex(1)
        self._btn_run.setEnabled(False)
        self._pump.start()

        from ...workers.generic import run_in_thread

        run_in_thread(self._engine.run, on_done=self._on_run_done,
                      on_error=self._on_run_error)

    # ------------------------------------------------------------- 事件泵

    def _drain_events(self) -> None:
        """主线程：排空 worker 塞进来的事件（进度/单文件结果）."""
        drained = 0
        while drained < 200:  # 单轮上限防御（正常量级远小于此）
            try:
                ev = self._events.get_nowait()
            except queue.Empty:
                break
            drained += 1
            if ev[0] == "progress":
                _, done, total, name = ev
                self._progress.set_progress(done, total)
                self._progress.mark_running(name)
            elif ev[0] == "file":
                self._progress.update_file(ev[1])

    # ------------------------------------------------------------- 终态

    def _on_cancel_clicked(self) -> None:
        if self._engine is not None:
            self._engine.cancel()
            self._progress.set_cancelling()

    def _on_run_error(self, msg: str) -> None:
        """引擎启动即失败（管线描述非法等）：回选择页给用户看错误."""
        self._pump.stop()
        self._btn_run.setEnabled(True)
        self._stack.setCurrentIndex(0)
        self._drain_events()
        QMessageBox.critical(self, S.BATCH_DLG_TITLE,
                             f"{S.BATCH_MSG_BAD_PIPELINE}：\n{msg.splitlines()[-1]}")

    def _on_run_done(self, summary) -> None:
        """整批结束（主线程）：停泵、收尾展示、交接结果."""
        self._pump.stop()
        self._drain_events()  # 收尾前排空残余事件（终态行不丢）
        self._btn_run.setEnabled(True)
        self._progress.finish(summary)
        logger.info("批处理对话框收尾：%s", summary.summary_zh())
        if summary.n_ok > 0 and len(self._engine.table) > 0:
            self.batch_finished.emit({
                "table": self._engine.table,
                "summary": summary,
                "job": self._engine.job,
            })

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名约定
        """运行中关闭 = 请求取消（后台线程自然收尾，不强杀）."""
        if self._engine is not None and not self._engine.cancelled:
            self._engine.cancel()
        self._pump.stop()
        super().closeEvent(event)
