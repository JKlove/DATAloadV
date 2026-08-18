"""M4 UI 测试：特征参数自动表单往返 + 管线面板特征区 + 特征结果视图.

表单往返不变量（同 M3 的 test_ui_m3）：任何"参数类型 → 控件 → 取值"的映射
错误都会让默认值被悄悄改掉。特征提取器与 proc 步骤共用 ParamsForm——
两层任何一方的接口漂移都会在这里暴露。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from dataloadv.batch import FeatureTable  # noqa: E402
from dataloadv.features import FEATURE_REGISTRY  # noqa: E402
from dataloadv.ui.widgets.feature_table import FeatureTableView  # noqa: E402
from dataloadv.ui.widgets.params_form import ParamsForm  # noqa: E402
from dataloadv.ui.widgets.pipeline_panel import PipelinePanel  # noqa: E402


class TestFeatureFormRoundtrip:
    def test_all_features_defaults_survive_roundtrip(self, qtbot):
        """每个特征：默认参数 → 表单 → collect 应完全相等（用户未动控件）."""
        problems = []
        for fid, fx in FEATURE_REGISTRY.items():
            params = fx.default_params()
            form = ParamsForm(fx, params)
            qtbot.addWidget(form)
            try:
                out = form.collect()
            except ValueError as e:
                problems.append(f"{fid}: collect 失败 {e}")
                continue
            if out.model_dump() != params.model_dump():
                problems.append(f"{fid}: {params.model_dump()} != {out.model_dump()}")
        assert not problems, "；".join(problems)

    def test_feature_form_reflects_overrides(self, qtbot):
        """非默认初值（频带功率只取 α）也应原样往返."""
        fx = FEATURE_REGISTRY["bandpower"]
        params = fx.make_params({"bands": ["alpha"], "relative": True})
        form = ParamsForm(fx, params)
        qtbot.addWidget(form)
        assert form.collect().model_dump() == params.model_dump()


class TestPipelinePanelFeatures:
    def _panel(self, qtbot) -> PipelinePanel:
        panel = PipelinePanel(lambda: None)
        qtbot.addWidget(panel)
        return panel

    def test_add_and_remove_feature(self, qtbot):
        panel = self._panel(qtbot)
        panel.add_feature("bandpower")
        panel.add_feature("timedomain")
        assert len(panel._features) == 2 and panel._feat_list.count() == 2
        assert panel._form is not None and panel._form_kind == "feature"
        # 选中第 2 个 → 删除 → 剩 1 个
        panel._feat_list.setCurrentRow(1)
        panel._remove_feature()
        assert len(panel._features) == 1
        assert panel._features[0]["feature"] == "bandpower"

    def test_collect_features_empty_refused(self, qtbot):
        panel = self._panel(qtbot)
        with pytest.raises(ValueError):
            panel.collect_features()

    def test_feature_dicts_serializable(self, qtbot):
        panel = self._panel(qtbot)
        panel.add_feature("welch_psd")
        dicts = panel.feature_dicts()
        assert dicts == [{"feature": "welch_psd", "params":
                          FEATURE_REGISTRY["welch_psd"].default_params().model_dump()}]

    def test_step_and_feature_forms_exclusive(self, qtbot):
        """步骤/特征列表互斥：选特征时步骤选择被清、表单切到特征."""
        panel = self._panel(qtbot)
        panel.add_step("bandpass")
        panel.add_feature("bandpower")
        assert panel._form_kind == "feature"  # add_feature 已切换
        panel._list.setCurrentRow(0)  # 反向切回步骤
        assert panel._form_kind == "step" and panel._list.currentRow() == 0
        assert panel._feat_list.currentRow() == -1

    def test_step_params_survive_feature_selection(self, qtbot):
        """编辑步骤参数 → 切去看特征 → 切回来：步骤参数不被冲掉（回写机制）."""
        panel = self._panel(qtbot)
        panel.add_step("bandpass", l_freq=2.0, h_freq=30.0)
        panel.add_feature("bandpower")
        panel._list.setCurrentRow(0)  # 切回步骤
        params = panel._steps[0]["params"]
        assert params.l_freq == 2.0 and params.h_freq == 30.0

    def test_use_viewport_without_browser_shows_hint(self, qtbot, monkeypatch):
        """无活动浏览器时「用当前显示窗口」给提示而不是崩溃."""
        panel = self._panel(qtbot)
        called = []
        monkeypatch.setattr(
            "dataloadv.ui.widgets.pipeline_panel.QMessageBox.information",
            staticmethod(lambda *a, **k: called.append(a)),
        )
        panel.use_viewport_window()
        assert called  # 弹了提示（被 patch 捕获）


class TestFeatureTableView:
    def test_view_builds_and_teardown(self, qtbot):
        """视图：中文列头、行数与表一致、teardown 释放 ctx."""
        import numpy as np

        table = FeatureTable()
        table.add_result(
            type("R", (), {"scalars": [
                {"epoch_index": None, "event_code": None, "channel": "EEG00",
                 "feature": "alpha", "value": 1.5},
                {"epoch_index": 0, "event_code": "T1", "channel": "EEG00",
                 "feature": "alpha", "value": 2.5},
            ], "curves": []})(),
            recording="x.gdf", subject="S01",
        )
        ctx = type("C", (), {"stage": "raw", "raw": object(), "epochs": None})()
        view = FeatureTableView(table, ctx, pipeline_dicts=[], feature_dicts=[])
        qtbot.addWidget(view)
        from PySide6.QtCore import Qt

        model = view._model
        assert model.rowCount() == 2
        assert model.headerData(0, Qt.Orientation.Horizontal) == "录制"
        assert model.headerData(6, Qt.Orientation.Horizontal) == "数值"
        # 文件级行（epoch_index=<NA>）显示空串而非 "None"/"<NA>"
        assert model.data(model.createIndex(0, 2)) == ""
        assert model.data(model.createIndex(0, 6)) == "1.5"
        view.teardown()
        assert view._ctx is None and view._table is None

    def test_sort_proxy_sorts_values(self, qtbot):
        """排序代理：按数值列排序后顺序翻转（数万行表格的可用性基础）."""
        table = FeatureTable()
        scalars = [{"epoch_index": None, "event_code": None, "channel": "EEG00",
                    "feature": "alpha", "value": float(v)} for v in (3.0, 1.0, 2.0)]
        table.add_result(
            type("R", (), {"scalars": scalars, "curves": []})(),
            recording="x.gdf",
        )
        view = FeatureTableView(table, None)
        qtbot.addWidget(view)
        from PySide6.QtCore import Qt

        view._proxy.sort(6, Qt.SortOrder.AscendingOrder)  # 数值列升序
        rows = [view._proxy.data(view._proxy.index(r, 6)) for r in range(3)]
        assert rows == ["1", "2", "3"]

    def test_sort_numeric_not_lexical(self, qtbot):
        """跨数量级值按数值排序（10 > 2，而非字符串序 10 < 2）."""
        table = FeatureTable()
        scalars = [{"epoch_index": None, "event_code": None, "channel": "EEG00",
                    "feature": "alpha", "value": float(v)} for v in (10.0, 2.0)]
        table.add_result(
            type("R", (), {"scalars": scalars, "curves": []})(), recording="x.gdf",
        )
        view = FeatureTableView(table, None)
        qtbot.addWidget(view)
        from PySide6.QtCore import Qt

        view._proxy.sort(6, Qt.SortOrder.AscendingOrder)
        rows = [view._proxy.data(view._proxy.index(r, 6)) for r in range(2)]
        assert rows == ["2", "10"]
