"""特征名 → 物理单位映射（M14）：特征图表纵轴标注用.

纯计算层（禁 import PySide6/pyqtgraph）。特征名的单位信息由生成侧的命名
约定编码（timedomain 的 ``rms_uv``/``var_uv2``、qc 的 ``*_pct``、bandpower
的 ``_rel``/``_log`` 修饰），本模块把约定集中成一张查询表——UI（特征图表
区纵轴标签）引用；未知名兜底返回 ""（无量纲，不猜）。
"""

from __future__ import annotations

# 时间窗后缀（bandpower 的 "@0-1s" 等）剥离前的原样名先查特殊表
_SPECIAL = {
    "qc_drift_uv_min": "µV/min",   # 漂移斜率
    "qc_level": "",                 # 质量分级 0/1/2
    "qc_bad_flag": "", "qc_suspect_flag": "", "qc_dup_flag": "",  # 0/1 标志
}


def feature_unit(name: str) -> str:
    """特征名 → 单位串（"" = 无量纲）.

    判定顺序（先剥 ``@时间窗`` 后缀再逐级判）：
    1. 特殊表（qc 漂移/分级/标志）；
    2. 前缀 ``qc_`` + 后缀 ``_uv``→µV、``_pct``→%；
    3. 通用后缀：``_uv2``→µV²、``_uv``→µV、``_rate``→次/s；
    4. bandpower 修饰：``_rel``（相对功率）→""（比例）、``_log``→log(µV²)
       （相对+log 先判 rel）；
    5. bandpower 基名（delta/theta/alpha/beta/gamma/自定义）→µV²；
    6. 兜底 ""（kurtosis/skewness 等无量纲、未知名不猜）。
    """
    base = name.split("@", 1)[0]  # 剥时间窗后缀（"@0-1s"）
    if base in _SPECIAL:
        return _SPECIAL[base]
    if base.startswith("qc_"):
        if base.endswith("_uv"):
            return "µV"
        if base.endswith("_pct"):
            return "%"
        return ""
    if base.endswith("_uv2"):
        return "µV²"
    if base.endswith("_uv"):
        return "µV"
    if base.endswith("_rate"):
        return "次/s"
    # 相对功率（0-1 比例）无论是否再取 log 都无量纲——先剥 _log 再判 _rel
    is_log = base.endswith("_log")
    if is_log:
        base = base[: -len("_log")]
    if base.endswith("_rel"):
        return ""
    if is_log:
        return "log(µV²)"
    if base in ("kurtosis", "skewness"):
        return ""
    # 标准频带基名 → µV²；自定义带名（如 mu）与未知名兜底 ""（单位不猜）
    if base in ("delta", "theta", "alpha", "beta", "gamma"):
        return "µV²"
    return ""
