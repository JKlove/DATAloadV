"""特征名→单位映射测试（M14，features/units.py）.

规则来源：timedomain 的 ``_uv``/``_uv2``/``_rate`` 命名、qc 的 ``_pct``/
漂移/分级、bandpower 的 ``_rel``/``_log``/标准带名与 ``@时间窗`` 后缀。
"""

from __future__ import annotations

import pytest

from dataloadv.features.units import feature_unit


@pytest.mark.parametrize(
    ("name", "expect"),
    [
        # 时域（timedomain 命名后缀即单位编码）
        ("rms_uv", "µV"), ("var_uv2", "µV²"), ("mav_uv", "µV"),
        ("ptp_uv", "µV"), ("iqr_uv", "µV"), ("zc_rate", "次/s"),
        ("kurtosis", ""), ("skewness", ""),
        # bandpower：标准带名 / 相对 / 对数 / 组合 / 带时间窗
        ("alpha", "µV²"), ("delta", "µV²"),
        ("alpha_rel", ""), ("alpha_log", "log(µV²)"), ("alpha_rel_log", ""),
        ("alpha@0-1s", "µV²"), ("alpha_rel@0-1s", ""),
        # qc（特殊表 + 前缀规则）
        ("qc_dc_uv", "µV"), ("qc_std_uv", "µV"), ("qc_drift_uv_min", "µV/min"),
        ("qc_flat_pct", "%"), ("qc_rail_pct", "%"),
        ("qc_level", ""), ("qc_bad_flag", ""),
        # 兜底：未知名不猜（自定义带名如 mu 暂无单位——宁缺勿错）
        ("mu", ""), ("whatever", ""),
    ],
)
def test_feature_unit(name, expect):
    assert feature_unit(name) == expect
