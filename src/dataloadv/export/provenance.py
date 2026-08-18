"""导出溯源 sidecar：``<名>.pipeline.json``——可复现性的书面记录.

每次导出（特征 CSV/HDF5、分段 HDF5/FIF）自动随数据写出同名 ``.pipeline.json``，
内容：全部处理步骤参数 + 特征提取器参数 + 文件清单 + 应用/库版本。这是与
pipelineMotor 的互操作边界——对方按同一份 JSON 描述即可重建处理过程。

字段结构（v1）::

    {
      "app": "DataloadV", "app_version": "…", "created": "ISO8601(UTC)",
      "pipeline":  [{"step": "bandpass", "params": {…}}, …],
      "features":  [{"feature": "bandpower", "params": {…}}, …],
      "recordings": ["A01T.gdf", …],
      "library_versions": {"mne": "…", "numpy": "…", "scipy": "…"}
    }

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

logger = logging.getLogger(__name__)


def _app_version() -> str:
    """应用版本（开发环境未安装包时回退源码里的 __version__）."""
    try:
        return metadata.version("dataloadv")
    except metadata.PackageNotFoundError:
        from .. import __version__

        return __version__


def _library_versions() -> dict[str, str]:
    """与处理结果数值相关的库版本（复现实验的最小集合）."""
    versions = {}
    for pkg in ("mne", "numpy", "scipy", "pandas", "h5py"):
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:  # 缺失不致命（只记录在场的）
            continue
    return versions


def write_provenance(
    path: str | Path,
    *,
    pipeline: list[dict],
    features: list[dict] | None = None,
    recordings: list[str] | None = None,
    extra: dict | None = None,
) -> Path:
    """写出 ``.pipeline.json``（``path`` 的后缀会被替换）.

    :param pipeline: 处理步骤 dict 列表（``proc.step_to_dict`` 产物 /
        ``pipeline_panel.pipeline_dicts()`` 或 ctx.history）
    :param features: 特征提取器 dict 列表（``features.feature_to_dict`` 产物）
    :param recordings: 数据文件名清单（展示名，不含绝对路径——不泄露本机结构）
    :param extra: 调用方附加信息（如 {"exported": "features.csv", "format": "csv"}）
    :returns: 实际写出的 sidecar 路径
    """
    path = Path(path)
    sidecar = path.with_suffix(".pipeline.json")
    doc = {
        "app": "DataloadV",
        "app_version": _app_version(),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pipeline": pipeline,
        "features": features or [],
        "recordings": recordings or [],
        "library_versions": _library_versions(),
    }
    if extra:
        doc["extra"] = extra
    sidecar.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("溯源 sidecar 已写出：%s", sidecar)
    return sidecar
