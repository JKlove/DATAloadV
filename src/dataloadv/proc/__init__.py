"""proc 包：预处理步骤层（禁止 import Qt，硬性架构规则 #1）.

import 本包即完成全部步骤注册（``STEP_REGISTRY`` 就绪）。
对外主入口：
- ``STEP_REGISTRY``：step_id -> ProcStep 实例
- ``ProcessingContext``：管线数据载体
- ``apply_pipeline``：[(step_id, params), ...] 顺序执行（预览/批处理共用）
"""

from __future__ import annotations

from .base import (
    STEP_REGISTRY,
    ProcStep,
    StepError,
    apply_pipeline,
    params_summary,
    register_step,
    step_from_dict,
    step_to_dict,
)
from .context import ProcessingContext

# 步骤模块 import 触发注册（顺序即 UI"添加步骤"菜单的展示顺序）
from . import filters, referencing, resample, bads, epoching  # noqa: F401,E402

__all__ = [
    "STEP_REGISTRY",
    "ProcStep",
    "StepError",
    "ProcessingContext",
    "apply_pipeline",
    "params_summary",
    "register_step",
    "step_to_dict",
    "step_from_dict",
]
