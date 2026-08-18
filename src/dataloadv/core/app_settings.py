"""应用设置（pydantic + JSON 持久化到 ``~/.dataloadv/settings.json``）.

为什么放 core：设置是被 io/batch/UI 共享的纯数据（批处理默认线程数、
数据缓存预算、默认导出目录），持久化与 FsStore/Workspace 同区
（``~/.dataloadv``；data/ 全程只读）。

热应用：``apply()`` 把 cache_gb 直接写进 LoadedRawCache 单例——预算在
每次 LRU 逐出时读取，改完立即生效，无需重启。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path.home() / ".dataloadv" / "settings.json"


class AppSettings(BaseModel):
    """应用级设置（一项一个字段，UI 设置对话框逐项对应）.

    - ``n_workers``：批处理默认并发线程（对话里仍可按批覆盖）
    - ``cache_gb``：已加载录制的数据缓存预算（GB）→ LoadedRawCache
    - ``export_dir``：导出对话框的默认目录（空 = 记住上一次/用户自选）
    """

    n_workers: int = Field(default=2, ge=1, le=8)
    cache_gb: float = Field(default=1.5, gt=0, le=64)
    export_dir: str = ""

    # ------------------------------------------------------------------ 持久化

    @classmethod
    def load(cls) -> "AppSettings":
        """读设置（文件不存在/损坏 → 全默认值并记日志，绝不阻塞启动）."""
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            return cls(**json.loads(SETTINGS_PATH.read_text(encoding="utf-8")))
        except Exception as e:  # noqa: BLE001 - 损坏的设置文件按无文件处理
            logger.warning("设置文件不可读（%s），使用默认值：%s", SETTINGS_PATH, e)
            return cls()

    def save(self) -> None:
        """原子写出（临时文件 + rename，与 Workspace 同套路）."""
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(SETTINGS_PATH)
        logger.info("设置已保存：%s", SETTINGS_PATH)

    # ------------------------------------------------------------------ 应用

    def apply(self) -> None:
        """把设置写到运行中的单例（cache 预算立即生效）."""
        from .recording import LoadedRawCache

        LoadedRawCache.instance().byte_budget = int(self.cache_gb * 1024**3)
