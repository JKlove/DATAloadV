"""batch 包：批处理引擎（禁止 import Qt）.

- ``results.FeatureTable``：特征长表（M4 起可用；批处理引擎逐文件并入）
- ``jobs``：JobSpec / PipelineSpec / FileResult / BatchSummary——一次批处理
  的完整可复现描述（可 JSON 持久化）
- ``engine.BatchEngine``：纯 Python 引擎（线程池 / 取消 / 逐文件日志 /
  末尾导出）；UI 层负责把回调转回主线程
"""

from __future__ import annotations

from .results import COLUMNS, COLUMNS_ZH, FeatureTable

__all__ = ["COLUMNS", "COLUMNS_ZH", "FeatureTable"]
