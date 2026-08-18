"""处理管线面板（右 Dock）：步骤编排 + 特征编排 + 预览 + PSD 对比 + 特征计算.

数据流（架构规则 #2：UI 不做计算）：
- 步骤链/特征链只是 [(id, params模型)] 列表，**不持有数据**
- 「预览当前文件」：``run_in_thread`` 里 from_recording（副本）→ apply_pipeline
  → 主线程回调发 ``preview_ready`` 信号 → 主窗口开预览 tab
- 「对比 PSD」：worker 里算原始/处理后两条 Welch 平均谱 → 主线程画 PsdView
- 「计算特征」（M4）：worker 里 副本 →（可选管线）→ apply_features →
  FeatureTable → 主线程发 ``features_ready`` → 主窗口开 FeatureTableView tab

与浏览器的联动：
- 添加「坏导联处理」步骤时，参数默认带入当前浏览 tab 已标记的坏道（右键标记）
- 「用当前显示窗口」按钮：把浏览器视口起止**预填**进 crop 步骤参数——可见
  可改、不隐式绑定视口（四层决策第④层：保证管线记录可复现）
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...batch import FeatureTable
from ...core.recording import LoadPolicy
from ...features import (
    FEATURE_REGISTRY,
    apply_features,
    feature_to_dict,
)
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
    """处理管线编排面板（步骤 + 特征）.

    :param get_active_browser: 返回当前激活的浏览 tab（无则 None）——主窗口注入
    :signal preview_ready(object): 预览完成（携带 ProcessingContext），主窗口开 tab
    :signal features_ready(object): 特征计算完成（携带
        {"table", "ctx", "feature_dicts"}），主窗口开特征结果 tab
    """

    preview_ready = Signal(object)
    features_ready = Signal(object)

    def __init__(self, get_active_browser: Callable[[], Optional[SignalBrowserView]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._get_active = get_active_browser
        self._steps: list[dict] = []    # [{"step": id, "params": 模型}]
        self._features: list[dict] = []  # [{"feature": id, "params": 模型}]
        self._last_ctx: Optional[ProcessingContext] = None  # 最近一次预览结果（PSD 对比用）
        self._form: Optional[ParamsForm] = None
        self._form_kind: Optional[str] = None  # 当前表单属于 "step" | "feature"
        self._selected_row: Optional[int] = None
        self._psd_view = None  # PsdView 独立窗口（重复点按复用）
        self._build_ui()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)

        lay.addWidget(QLabel(S.PIPE_LBL_STEPS))
        self._list = QListWidget()
        self._list.setMaximumHeight(110)
        self._list.currentRowChanged.connect(self._on_select_step)
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

        # ---------------- M4：特征区（与步骤区共用下方参数表单） ----------------
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        lay.addWidget(line)
        lay.addWidget(QLabel(S.FEAT_LBL_LIST))
        self._feat_list = QListWidget()
        self._feat_list.setMaximumHeight(80)
        self._feat_list.currentRowChanged.connect(self._on_select_feature)
        lay.addWidget(self._feat_list)

        feat_row = QHBoxLayout()
        self._btn_feat_add = QToolButton()
        self._btn_feat_add.setText(S.FEAT_BTN_ADD)
        self._btn_feat_add.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._btn_feat_add.setMenu(self._build_feat_menu())
        self._btn_viewport = QPushButton(S.FEAT_BTN_VIEWPORT)
        self._btn_viewport.clicked.connect(self.use_viewport_window)
        self._btn_feat_remove = QPushButton(S.FEAT_BTN_REMOVE)
        self._btn_feat_remove.clicked.connect(self._remove_feature)
        feat_row.addWidget(self._btn_feat_add)
        feat_row.addWidget(self._btn_viewport)
        feat_row.addWidget(self._btn_feat_remove)
        lay.addLayout(feat_row)

        lay.addWidget(QLabel(S.PIPE_LBL_PARAMS))
        self._form_host = QScrollArea()
        self._form_host.setWidgetResizable(True)
        self._form_host.setWidget(QLabel(S.FEAT_EMPTY_HINT))
        lay.addWidget(self._form_host, 1)

        actions = QHBoxLayout()
        self._btn_preview = QPushButton(S.PIPE_BTN_PREVIEW)
        self._btn_psd = QPushButton(S.PIPE_BTN_PSD)
        self._btn_run_feat = QPushButton(S.FEAT_BTN_RUN)
        self._btn_preview.clicked.connect(self.start_preview)
        self._btn_psd.clicked.connect(self.start_psd)
        self._btn_run_feat.clicked.connect(self.start_features)
        actions.addWidget(self._btn_preview)
        actions.addWidget(self._btn_psd)
        actions.addWidget(self._btn_run_feat)
        lay.addLayout(actions)

    def _build_add_menu(self) -> QMenu:
        """「添加步骤」菜单：按注册顺序列出全部步骤（中文名）."""
        menu = QMenu(self)
        for step in STEP_REGISTRY.values():
            menu.addAction(step.label_zh, lambda s=step.step_id: self._add_step(s))
        return menu

    def _build_feat_menu(self) -> QMenu:
        """「添加特征」菜单：按注册顺序列出全部特征提取器."""
        menu = QMenu(self)
        for fx in FEATURE_REGISTRY.values():
            menu.addAction(fx.label_zh, lambda f=fx.feature_id: self.add_feature(f))
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
            self._show_form("step", max(0, min(row, len(self._steps) - 1)))

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
        self._show_form(None, -1)

    def _label(self, step_id: str) -> str:
        step = STEP_REGISTRY[step_id]
        return f"{step.label_zh}（{params_summary(self._find_params(step_id))}）"

    def _find_params(self, step_id: str):
        for entry in self._steps:
            if entry["step"] == step_id:
                return entry["params"]
        return STEP_REGISTRY[step_id].default_params()

    # ------------------------------------------------------------------ 特征链编辑（M4）

    def add_feature(self, feature_id: str, **overrides) -> None:
        """添加特征提取器（overrides 先于表单合入，理由同 add_step）."""
        fx = FEATURE_REGISTRY[feature_id]
        self._features.append({"feature": feature_id, "params": fx.make_params(overrides)})
        self._select_feature_row(len(self._features) - 1)

    def _remove_feature(self) -> None:
        row = self._feat_list.currentRow()
        if 0 <= row < len(self._features):
            self._features.pop(row)
            self._feat_list.takeItem(row)
            self._show_form("feature", max(0, min(row, len(self._features) - 1)))

    def _feature_label(self, feature_id: str) -> str:
        fx = FEATURE_REGISTRY[feature_id]
        entry = next((e for e in self._features if e["feature"] == feature_id), None)
        summary = params_summary(entry["params"]) if entry else "默认参数"
        return f"{fx.label_zh}（{summary}）"

    def feature_dicts(self) -> list[dict]:
        """当前特征链 → 可 JSON 序列化 dict 列表（sidecar/M5 批处理复用）."""
        return [feature_to_dict(e["feature"], e["params"]) for e in self._features]

    # ------------------------------------------------------------------ 表单（步骤/特征共用）

    def _on_select_step(self, row: int) -> None:
        """步骤列表选中变化：互斥（清特征选择）+ 回写旧表单."""
        if row >= 0:
            self._feat_list.setCurrentRow(-1)
        self._write_back_form()
        self._show_form("step" if 0 <= row < len(self._steps) else None, row)

    def _on_select_feature(self, row: int) -> None:
        if row >= 0:
            self._list.setCurrentRow(-1)
        self._write_back_form()
        self._show_form("feature" if 0 <= row < len(self._features) else None, row)

    def _select_step_row(self, row: int) -> None:
        """刷新步骤行文字并选中（更新已有条目场景——不添加新行）."""
        item = self._list.item(row)
        if item is not None:
            item.setText(self._label(self._steps[row]["step"]))
        self._list.setCurrentRow(row)

    def _select_feature_row(self, row: int) -> None:
        """添加特征行并选中（add_feature 专用——append 语义）."""
        self._feat_list.addItem(self._feature_label(self._features[row]["feature"]))
        self._feat_list.setCurrentRow(row)

    def _write_back_form(self) -> None:
        """切换选择前把当前表单值写回其条目（半填的值不回写，预览时统一校验）."""
        if self._form is None or self._form_kind is None or self._selected_row is None:
            return
        chain = self._steps if self._form_kind == "step" else self._features
        if not (0 <= self._selected_row < len(chain)):
            return
        try:
            chain[self._selected_row]["params"] = self._form.collect()
        except ValueError:
            pass

    def _show_form(self, kind: Optional[str], row: int) -> None:
        """为选中条目重建参数表单；kind=None 显示空提示.

        步骤与特征共用一个表单区——两者的参数模型/表单接口完全同构。
        """
        self._form = None
        self._form_kind = kind
        chain = self._steps if kind == "step" else self._features if kind == "feature" else None
        if chain is None or not (0 <= row < len(chain)):
            self._selected_row = None
            self._form_host.setWidget(QLabel(S.FEAT_EMPTY_HINT))
            return
        self._selected_row = row
        entry = chain[row]
        owner = (STEP_REGISTRY[entry["step"]] if kind == "step"
                 else FEATURE_REGISTRY[entry["feature"]])
        self._form = ParamsForm(owner, entry["params"])
        # 表单编辑 → 实时写回条目 + 刷新列表行文字（try 容忍半填状态）
        self._form.edited.connect(lambda: self._live_collect())
        self._form_host.setWidget(self._form)

    def _live_collect(self) -> None:
        if self._form is None or self._form_kind is None or self._selected_row is None:
            return
        chain = self._steps if self._form_kind == "step" else self._features
        key = "step" if self._form_kind == "step" else "feature"
        lst = self._list if self._form_kind == "step" else self._feat_list
        try:
            chain[self._selected_row]["params"] = self._form.collect()
            item = lst.item(self._selected_row)
            if item is not None:
                item.setText(self._label(chain[self._selected_row][key])
                             if key == "step"
                             else self._feature_label(chain[self._selected_row][key]))
        except ValueError:
            pass  # 半填状态（如刚清空文本框）不回写，等下次编辑或运行时校验

    # ------------------------------------------------------------------ 收集

    def collect_pipeline(self) -> list[dict]:
        """收集步骤链（预览前统一校验；空链/非法直接抛 ValueError 中文）."""
        self._write_back_form()
        if not self._steps:
            raise ValueError(S.PIPE_MSG_NO_STEPS)
        return self._steps

    def collect_features(self) -> list[dict]:
        """收集特征链（计算特征前统一校验）."""
        self._write_back_form()
        if not self._features:
            raise ValueError(S.FEAT_MSG_NO_FEATURES)
        return self._features

    def pipeline_dicts(self) -> list[dict]:
        """当前管线 → 可 JSON 序列化 dict 列表（M5 批处理/导出 sidecar 复用）."""
        self._write_back_form()
        return [step_to_dict(e["step"], e["params"]) for e in self._steps]

    def _active_recording(self):
        browser = self._get_active()
        if browser is None:
            raise ValueError(S.FEAT_MSG_NO_ACTIVE)
        if not browser._loaded_once:  # noqa: SLF001 - 面板与浏览器同包内协作
            raise ValueError(S.PIPE_MSG_NOT_LOADED)
        return browser.rec

    # ------------------------------------------------------------------ 预览（M3）

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

    # ------------------------------------------------------------------ PSD 对比（M3）

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

    # ------------------------------------------------------------------ 视口预填（M4 第④层）

    def use_viewport_window(self) -> None:
        """把当前浏览 tab 的视口起止**预填**进 crop 步骤（无则新增）.

        不隐式绑定视口：值进参数表单，用户可见可改——管线记录始终可复现。
        """
        browser = self._get_active()
        if browser is None:
            QMessageBox.information(self, S.FEAT_BTN_VIEWPORT, S.FEAT_MSG_NO_ACTIVE)
            return
        if not browser._loaded_once:  # noqa: SLF001 - 同包协作
            QMessageBox.information(self, S.FEAT_BTN_VIEWPORT, S.FEAT_MSG_VIEWPORT_NO_DATA)
            return
        t0, t1 = browser._visible_range()  # noqa: SLF001 - 同包协作
        duration = browser.rec.meta.duration_s
        t0, t1 = max(0.0, round(t0, 2)), min(duration, round(t1, 2))
        if t1 - t0 < 1.0:
            QMessageBox.warning(
                self, S.FEAT_BTN_VIEWPORT,
                f"当前显示窗口过短（{t1 - t0:.2f} s），不适合做特征计算——请先缩小缩放")
            return
        # 找最后一个 crop 步骤：就地更新其参数（保持用户已有步骤顺序）
        for row in range(len(self._steps) - 1, -1, -1):
            if self._steps[row]["step"] == "crop":
                self._steps[row]["params"] = STEP_REGISTRY["crop"].make_params(
                    {"tmin": t0, "tmax": t1})
                self._select_step_row(row)  # 选中并刷新该行文字（表单同步显示新值）
                break
        else:
            self.add_step("crop", tmin=t0, tmax=t1)
        self.window().statusBar().showMessage(
            S.FEAT_MSG_VIEWPORT_APPLIED.format(t0=t0, t1=t1), 5000)

    # ------------------------------------------------------------------ 特征计算（M4）

    def start_features(self) -> None:
        """管线（可选）+ 特征 → FeatureTable：worker 全链路，主线程开 tab."""
        try:
            steps = [(e["step"], e["params"]) for e in self.collect_pipeline()] \
                if self._steps else []
            feats = [(e["feature"], e["params"]) for e in self.collect_features()]
            rec = self._active_recording()
        except ValueError as e:
            QMessageBox.warning(self, S.PIPE_PREVIEW_FAIL_TITLE, str(e))
            return
        self._btn_run_feat.setEnabled(False)
        self.window().statusBar().showMessage(S.FEAT_MSG_RUNNING)

        def job(rec=rec, steps=steps, feats=feats):
            ctx = ProcessingContext.from_recording(rec)
            if steps:
                apply_pipeline(ctx, steps)
            result = apply_features(ctx, feats)
            table = FeatureTable()
            table.add_result(result, rec.meta.filename, rec.meta.subject or "")
            return {"table": table, "ctx": ctx, "feature_dicts": [
                feature_to_dict(f, p) for f, p in feats]}

        run_in_thread(
            job,
            on_done=self._on_features_done,
            on_error=lambda m: (self._btn_run_feat.setEnabled(True),
                                QMessageBox.critical(self, S.PIPE_PREVIEW_FAIL_TITLE, m)),
        )

    def _on_features_done(self, payload: dict) -> None:
        self._btn_run_feat.setEnabled(True)
        self.window().statusBar().showMessage(S.STATUS_READY)
        payload["pipeline_dicts"] = payload["ctx"].history  # sidecar 记实际执行的步骤
        self.features_ready.emit(payload)


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
