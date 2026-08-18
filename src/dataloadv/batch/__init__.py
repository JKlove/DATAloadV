"""batch 包：批处理引擎（禁止 import Qt）.

- ``results.FeatureTable``：特征长表（M4 起可用；M5 批处理引擎逐文件并入）
- ``engine.BatchEngine``：M5（2 线程池/取消/逐文件日志）
"""

from __future__ import annotations

from .results import COLUMNS, COLUMNS_ZH, FeatureTable

__all__ = ["COLUMNS", "COLUMNS_ZH", "FeatureTable"]
