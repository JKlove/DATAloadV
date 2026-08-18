"""采样率记忆库：CSV/TXT/HDF5 等文件内不含采样率，用户告知一次后持久记忆.

为什么需要：表格/通用 HDF5 只有数值矩阵，采样率在文件里根本不存在。
问用户是唯一诚实的来源（不猜）；但每个文件问一次很烦——记住
"这个路径 → 这个采样率"，下次直接用。存储位置 ``~/.dataloadv/table_fs.json``
（data/ 目录只读，用户配置一律进 ``~/.dataloadv``，与工作区持久化同区）。

约定：值 ≤0 或删除键 = 忘记该文件的采样率（再次打开会重新询问）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 应用数据根（与 workspace.py 的 APP_DIR 保持一致；独立定义避免循环 import）
_STORE_PATH = Path.home() / ".dataloadv" / "table_fs.json"


class FsStore:
    """路径 → 采样率（Hz）的持久映射（JSON，原子写）.

    ``store_path`` 默认取模块级 ``_STORE_PATH``（延迟绑定：测试用
    monkeypatch 替换 ``_STORE_PATH`` 即可隔离，不动用户真实记忆文件）。
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = store_path if store_path is not None else _STORE_PATH
        self._data: dict[str, float] = {}
        self._load()

    # ------------------------------------------------------------------ 持久化
    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._data = {str(k): float(v) for k, v in raw.items() if float(v) > 0}
        except (json.JSONDecodeError, ValueError, OSError):
            # 损坏的记忆文件不致命：当作空库重新开始
            logger.warning("采样率记忆文件损坏，已忽略：%s", self._path)
            self._data = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(self._path)  # 原子替换（与 workspace.save 同策略）

    # ------------------------------------------------------------------ 读写
    def get(self, path: str | Path) -> float | None:
        """该文件的已知采样率；没记过返回 None."""
        return self._data.get(str(Path(path).resolve()))

    def put(self, path: str | Path, sfreq: float) -> None:
        """记住采样率（≤0 视为忘记）."""
        key = str(Path(path).resolve())
        if sfreq <= 0:
            self._data.pop(key, None)
        else:
            self._data[key] = float(sfreq)
        self._save()
