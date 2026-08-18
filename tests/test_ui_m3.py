"""M3 UI 测试：参数自动表单（全部步骤默认值往返不变）+ 解析助手.

表单往返不变量很关键：任何"步骤参数类型 → 控件 → 取值"的映射错误都会让
默认值被悄悄改掉（用户没动任何控件，collect 出来的参数却变了）。
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from dataloadv.proc import STEP_REGISTRY  # noqa: E402
from dataloadv.ui.widgets.params_form import (  # noqa: E402
    ParamsForm,
    _parse_list,
    _parse_pair,
)


class TestParsers:
    def test_parse_list_float(self):
        assert _parse_list("50, 100 150", float) == [50.0, 100.0, 150.0]
        assert _parse_list("50，100", float) == [50.0, 100.0]  # 中文逗号
        assert _parse_list("", float) == []
        with pytest.raises(ValueError):
            _parse_list("50,abc", float)

    def test_parse_list_str(self):
        assert _parse_list("769，770 771", str) == ["769", "770", "771"]
        assert _parse_list("EEG01, EEG02", str) == ["EEG01", "EEG02"]

    def test_parse_pair(self):
        assert _parse_pair("无,0") == (None, 0.0)
        assert _parse_pair("-0.5, 0") == (-0.5, 0.0)
        assert _parse_pair("无") is None  # 整项不做基线
        assert _parse_pair("") is None
        with pytest.raises(ValueError):
            _parse_pair("1,2,3")
        with pytest.raises(ValueError):
            _parse_pair("a,b")


class TestFormRoundtrip:
    def test_all_steps_defaults_survive_roundtrip(self, qtbot):
        """每个步骤：默认参数 → 表单 → collect 应完全相等（用户未动控件）."""
        problems = []
        for step_id, step in STEP_REGISTRY.items():
            params = step.default_params()
            form = ParamsForm(step, params)
            qtbot.addWidget(form)
            try:
                out = form.collect()
            except ValueError as e:
                problems.append(f"{step_id}: collect 失败 {e}")
                continue
            if out.model_dump() != params.model_dump():
                problems.append(f"{step_id}: {params.model_dump()} != {out.model_dump()}")
        assert not problems, "；".join(problems)

    def test_form_reflects_overrides(self, qtbot):
        """非默认初值（如带通 2–30Hz）也应原样往返."""
        step = STEP_REGISTRY["bandpass"]
        params = step.make_params({"l_freq": 2.0, "h_freq": 30.0})
        form = ParamsForm(step, params)
        qtbot.addWidget(form)
        assert form.collect().model_dump() == params.model_dump()

    def test_optional_float_unchecked_gives_none(self, qtbot):
        """Optional 浮点开关关掉 → None（带通单侧不滤）."""
        step = STEP_REGISTRY["bandpass"]
        params = step.make_params({"l_freq": None, "h_freq": 40.0})
        form = ParamsForm(step, params)
        qtbot.addWidget(form)
        out = form.collect()
        assert out.l_freq is None and out.h_freq == 40.0
