"""export 包：结果导出与溯源（禁止 import Qt，硬性架构规则 #1）.

- ``features_io``：特征长表 → CSV（中文表头 + BOM）/ HDF5，PSD 曲线宽表
- ``epochs_io``：mne.Epochs → HDF5（跨工具）/ FIF（mne 无损往返）
- ``provenance``：``<名>.pipeline.json`` 溯源 sidecar（每次导出自动随写）
"""

from __future__ import annotations

from . import epochs_io, features_io, provenance  # noqa: F401

__all__ = ["features_io", "epochs_io", "provenance"]
