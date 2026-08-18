"""处理管线面板（右 Dock）：步骤编排 + 参数编辑 + 当前文件预览 + PSD 对比.

数据流（架构规则 #2：UI 不做计算）：
- 步骤链只是 [(step_id, params模型)] 列表，**不持有数据**
- 「预览当前文件」：``run_in_thread`` 里 from_recording（副本）→ apply_pipeline
  → 主线程回调发 ``preview_ready`` 信号 → 主窗口开预览 tab
- 「对比 PSD」：worker 里算原始/处理后两条 Welch 平均谱 → 主线程画 PsdView

与浏览器的联动：添加「坏导联处理」步骤时，参数默认带入当前浏览 tab 已标记
的坏道（右键标记），也可在表单里手改。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.recording import LoadPolicy
from ...features.spectral import mean_welch
from ...proc import (
    STEP_REGISTRY,
    ProcessingContext,
    apply_pipeline,
    params_summary,
    step_to_dict,
)
from ...workers.generic import run_in_thread
from ..strings_zh import S
from .params_form import ParamsForm
from .signal_browser import SignalBrowserView

logger = logging.getLogger(__name__)

# PSD 只取每条数据开头的这一段（长文件全算 Welch 太慢，谱前 2 分钟已够看）
_PSD_MAX_SECONDS = 120.0


class PipelinePanel(QWidget):
    """处理管线编排面板.

    :param get_active_browser: 返回当前激活的浏览 tab（无则 None）——主窗口注入
    :signal preview_ready(object): 预览完成（携带 ProcessingContext），主窗口开 tab
    """

    preview_ready = Signal(object)

    def __init__(self, get_active_browser: Callable[[], Optional[SignalBrowserView]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._get_active = get_active_browser
        self._steps: list[dict] = []  # [{"step": id, "params": 模型}]
        self._last_ctx: Optional[ProcessingContext] = None  # 最近一次预览结果（PSD 对比用）
        self._form: Optional[ParamsForm] = None
        self._psd_view = None  # PsdView 独立窗口（重复点按复用）
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        lay.addWidget(QLabel(S.PIPE_LBL_STEPS))
        self._list = QListWidget()
        self._list.setMaximumHeight(140)
        self._list.currentRowChanged.connect(self._on_select)
        lay.addWidget(self._list)

        row = QHBoxLayout()
        self._btn_add = QToolButton()
        self._btn_add.setText(S.PIPE_BTN_ADD)
        self._btn_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_add.setMenu(self._build_add_menu())
        for title, fn in (
            (S.PIPE_BTN_REMOVE, self._remove_step),
            (S.PIPE_BTN_UP, lambda: self._move_step(-1)),
            (S.PIPE_BTN_DOWN, lambda: self._move_step(+1)),
            (S.PIPE_BTN_CLEAR, self._clear_steps),
        ):
            btn = QPushButton(title)
            btn.clicked.connect(fn)
            row.addWidget(btn)
        row.insertWidget(0, self._btn_add)
        lay.addLayout(row)

        lay.addWidget(QLabel(S.PIPE_LBL_PARAMS))
        self._form_host = QScrollArea()
        self._form_host.setWidgetResizable(True)
        self._form_host.setWidget(QLabel(S.PIPE_EMPTY_HINT))
        lay.addWidget(self._form_host, 1)

        actions = QHBoxLayout()
        self._btn_preview = QPushButton(S.PIPE_BTN_PREVIEW)
        self._btn_psd = QPushButton(S.PIPE_BTN_PSD)
        self._btn_preview.clicked.connect(self.start_preview)
        self._btn_psd.clicked.connect(self.start_psd)
        actions.addWidget(self._btn_preview)
        actions.addWidget(self._btn_psd)
        lay.addLayout(actions)

    def _build_add_menu(self) -> QMenu:
        """「添加步骤」菜单：按注册顺序列出全部步骤（中文名）."""
        menu = QMenu(self)
        for step in STEP_REGISTRY.values():
            menu.addAction(step.label_zh, lambda s=step.step_id: self._add_step(s))
        return menu

    # ------------------------------------------------------------------ 步骤链编辑

    def add_step(self, step_id: str, **overrides) -> None:
        """添加步骤（坏导联步骤默认带入浏览器当前标记；overrides 先于表单生效）.

        注意 overrides 必须在表单构建**之前**合入——表单是选中步骤参数的展示源，
        后改 ``_steps`` 条目会被表单 collect 覆盖回去（e2e 踩过）。
        """
        step = STEP_REGISTRY[step_id]
        kwargs = dict(overrides)
        if step_id == "bads" and "channels" not in kwargs:
            browser = self._get_active()
            marked = browser.current_bads() if browser is not None else []
            if marked:  # 浏览器已标记 → 直接作为默认值（联动）
                kwargs["channels"] = marked
        self._steps.append({"step": step_id, "params": step.make_params(kwargs)})
        self._list.addItem(self._label(step_id))
        self._list.setCurrentRow(len(self._steps) - 1)

    _add_step = add_step  # 内部菜单连接用的别名（历史命名）

    def _remove_step(self) -> None:
        row = self._list.currentRow()
        if 0 <= row < len(self._steps):
            self._steps.pop(row)
            self._list.takeItem(row)
            self._show_form_for(max(0, min(row, len(self._steps) - 1)))

    def _move_step(self, delta: int) -> None:
        row = self._list.currentRow()
        target = row + delta
        if not (0 <= target < len(self._steps)):
            return
        self._steps[row], self._steps[target] = self._steps[target], self._steps[row]
        item = self._list.takeItem(row)
        self._list.insertItem(target, item)
        self._list.setCurrentRow(target)

    def _clear_steps(self) -> None:
        self._steps.clear()
        self._list.clear()
        self._show_form_for(-1)

    def _label(self, step_id: str) -> str:
        step = STEP_REGISTRY[step_id]
        return f"{step.label_zh}（{params_summary(self._find_params(step_id))}）"

    def _find_params(self, step_id: str):
        for entry in self._steps:
            if entry["step"] == step_id:
                return entry["params"]
        return STEP_REGISTRY[step_id].default_params()

    def _on_select(self, row: int) -> None:
        """选中变化前先把当前表单值写回条目（用户点了别的步骤=编辑结束）.

        行号守卫：清空/删除步骤会让列表触发 currentRowChanged，此时旧行号
        可能越界（e2e 实测 IndexError）——越界即跳过回写。
        """
        if (self._form is not None and self._selected_row is not None
                and 0 <= self._selected_row < len(self._steps)):
            try:
                self._steps[self._selected_row]["params"] = self._form.collect()
            except ValueError:
                pass  # 半填的值不回写（预览时统一校验并提示）
        self._show_form_for(row)

    _selected_row: Optional[int] = None

    def _show_form_for(self, row: int) -> None:
        """为第 row 步骤重建参数表单；row<0 显示空提示."""
        self._selected_row = row if 0 <= row < len(self._steps) else None
        self._form = None
        if self._selected_row is None:
            self._form_host.setWidget(QLabel(S.PIPE_EMPTY_HINT))
            return
        entry = self._steps[row]
        step = STEP_REGISTRY[entry["step"]]
        self._form = ParamsForm(step, entry["params"])
        # 表单编辑 → 实时写回条目 + 刷新列表行文字（try 容忍半填状态）
        self._form.edited.connect(lambda: self._live_collect(row))
        self._form_host.setWidget(self._form)

    def _live_collect(self, row: int) -> None:
        try:
            self._steps[row]["params"] = self._form.collect()
            self._list.item(row).setText(self._label(self._steps[row]["step"]))
        except ValueError:
            pass  # 半填状态（如刚清空文本框）不回写，等下次编辑或预览时校验

    # ------------------------------------------------------------------ 预览

    def collect_pipeline(self) -> list[dict]:
        """收集步骤链（预览/导出前统一校验；非法直接弹窗）."""
        if not self._steps:
            raise ValueError(S.PIPE_MSG_NO_STEPS)
        if self._form is not None and self._selected_row is not None:
            self._steps[self._selected_row]["params"] = self._form.collect()  # 强校验
        return self._steps

    def pipeline_dicts(self) -> list[dict]:
        """当前管线 → 可 JSON 序列化 dict 列表（M5 批处理/导出 sidecar 复用）."""
        return [step_to_dict(e["step"], e["params"]) for e in self._steps]

    def _active_recording(self):
        browser = self._get_active()
        if browser is None:
            raise ValueError(S.PIPE_MSG_NO_ACTIVE)
        if not browser._loaded_once:  # noqa: SLF001 - 面板与浏览器同包内协作
            raise ValueError(S.PIPE_MSG_NOT_LOADED)
        return browser.rec

    def start_preview(self) -> None:
        """预览当前 tab：worker 里副本+整条管线，主线程回调开 tab."""
        try:
            steps = [(e["step"], e["params"]) for e in self.collect_pipeline()]
            rec = self._active_recording()
        except ValueError as e:
            QMessageBox.warning(self, S.PIPE_PREVIEW_FAIL_TITLE, str(e))
            return
        self._btn_preview.setEnabled(False)
        self.window().statusBar().showMessage(S.PIPE_MSG_PREVIEW_RUNNING)

        def job(rec=rec, steps=steps):
            ctx = ProcessingContext.from_recording(rec)
            apply_pipeline(ctx, steps)
            return ctx

        run_in_thread(
            job,
            on_done=self._on_preview_done,
            on_error=lambda m: (self._btn_preview.setEnabled(True),
                                QMessageBox.critical(self, S.PIPE_PREVIEW_FAIL_TITLE, m)),
        )

    def _on_preview_done(self, ctx: ProcessingContext) -> None:
        self._btn_preview.setEnabled(True)
        self.window().statusBar().showMessage(S.STATUS_READY)
        self._last_ctx = ctx  # 「对比 PSD」用它
        self.preview_ready.emit(ctx)

    # ------------------------------------------------------------------ PSD 对比

    def start_psd(self) -> None:
        """原始 vs 最近预览 的 Welch 平均谱对比（无预览时只画原始）."""
        try:
            rec = self._active_recording()
        except ValueError as e:
            QMessageBox.warning(self, S.PIPE_PSD_TITLE, str(e))
            return
        ctx = self._last_ctx
        if ctx is None:
            self.window().statusBar().showMessage(S.PIPE_MSG_PSD_NO_PREVIEW, 5000)
        self._btn_psd.setEnabled(False)
        self.window().statusBar().showMessage(S.PIPE_MSG_PSD_RUNNING)
        run_in_thread(
            lambda: _psd_job(rec, ctx),
            on_done=self._on_psd_done,
            on_error=lambda m: (self._btn_psd.setEnabled(True),
                                QMessageBox.critical(self, S.PIPE_PSD_TITLE, m)),
        )

    def _on_psd_done(self, result) -> None:
        self._btn_psd.setEnabled(True)
        self.window().statusBar().showMessage(S.STATUS_READY)
        before, after = result
        series = [(S.PIPE_PSD_LABEL_BEFORE, before[0], before[1])]
        if after is not None:
            series.append((S.PIPE_PSD_LABEL_AFTER, after[0], after[1]))
        if self._psd_view is None:
            from .psd_view import PsdView

            self._psd_view = PsdView()  # 独立顶层窗口，重复点按复用
        self._psd_view.set_series(series)
        self._psd_view.show()
        self._psd_view.raise_()


def _psd_job(rec, ctx: Optional[ProcessingContext]):
    """worker 线程：算两条平均 PSD（返回 µV²/Hz；纯 numpy 跨线程安全）."""

    def _psd(raw):
        # 长文件只取前 _PSD_MAX_SECONDS：Welch 全算太慢且谱已具代表性
        seg = raw.copy().crop(0, min(_PSD_MAX_SECONDS, raw.times[-1]))
        seg.load_data()  # crop 副本可能仍是 lazy，Welch 需要数据
        f, p = mean_welch(seg)
        return f, p * 1e12  # V²/Hz → µV²/Hz

    raw = rec.ensure_raw(LoadPolicy.HEADER_ONLY)
    before = _psd(raw)
    after = _psd(ctx.raw) if ctx is not None and ctx.stage == "raw" else None
    return before, after
