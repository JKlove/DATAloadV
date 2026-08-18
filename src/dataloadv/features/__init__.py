"""features 包：特征提取器层（禁止 import Qt，硬性架构规则 #1）.

import 本包即完成全部提取器注册（``FEATURE_REGISTRY`` 就绪）。
对外主入口：
- ``FEATURE_REGISTRY``：feature_id -> FeatureExtractor 实例
- ``apply_features``：管线执行完后 [(feature_id, params), ...] 顺序计算
- ``ExtractorResult`` / ``pick_channels``：提取器产出与通道选择约定
"""

from __future__ import annotations

from .base import (
    FEATURE_REGISTRY,
    ExtractorResult,
    FeatureError,
    FeatureExtractor,
    apply_features,
    feature_from_dict,
    feature_to_dict,
    pick_channels,
    register_feature,
)

# 提取器模块 import 触发注册（顺序即 UI"添加特征"菜单的展示顺序）
from . import spectral, timedomain  # noqa: F401,E402

__all__ = [
    "FEATURE_REGISTRY",
    "ExtractorResult",
    "FeatureError",
    "FeatureExtractor",
    "apply_features",
    "feature_to_dict",
    "feature_from_dict",
    "pick_channels",
    "register_feature",
]
