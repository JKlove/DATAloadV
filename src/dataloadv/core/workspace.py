"""工作区：导入来源与录制条目的集合 + JSON 持久化.

模型（两级）：

- ``ImportSource``：一次导入动作（一个文件或一个目录扫描），是工作区树的
  分组节点。记录路径与导入时间；``options`` 留给 CSV 采样率等来源级设置。
- ``Workspace``：全部 ImportSource 及其下 RecordingMeta 的容器。负责
  按 path 去重（同一文件重复导入不产生新条目）、按来源/标签分组查询。

持久化：``~/.dataloadv/workspaces/<name>/workspace.json``——只存 meta
（头信息），不存任何数据本体；重开应用恢复列表瞬间完成。当前工作区名
记录在 ``~/.dataloadv/current_workspace.txt``。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

from .recording import RecordingMeta

logger = logging.getLogger(__name__)

# 应用数据根目录（与 logging_setup.APP_DIR 保持一致）
APP_DIR = Path.home() / ".dataloadv"
WORKSPACE_ROOT = APP_DIR / "workspaces"
CURRENT_WS_FILE = APP_DIR / "current_workspace.txt"

DEFAULT_WORKSPACE = "默认工作区"


class ImportSource:
    """一次导入来源（一个目录或一个文件），工作区树的分组节点."""

    def __init__(self, path: str, imported_at: float | None = None, options: dict | None = None):
        self.path = path
        self.imported_at = imported_at or time.time()
        self.options = options or {}  # 来源级设置（如 CSV 的默认采样率）
        self.recordings: dict[str, RecordingMeta] = {}  # path -> meta

    @property
    def name(self) -> str:
        """树节点显示名：目录名/文件名."""
        return Path(self.path).name or self.path

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "imported_at": self.imported_at,
            "options": self.options,
            "recordings": [m.model_dump() for m in self.recordings.values()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImportSource":
        src = cls(d["path"], d.get("imported_at"), d.get("options"))
        src.recordings = {m["path"]: RecordingMeta(**m) for m in d.get("recordings", [])}
        return src


class Workspace:
    """一个工作区：导入来源集合 + 查询/去重/持久化."""

    def __init__(self, name: str = DEFAULT_WORKSPACE):
        self.name = name
        self.sources: dict[str, ImportSource] = {}  # source.path -> ImportSource
        self._file = WORKSPACE_ROOT / self._safe_name() / "workspace.json"

    # ------------------------------------------------------------ 管理

    def _safe_name(self) -> str:
        """工作区名转安全目录名（防路径穿越/非法字符）."""
        return "".join(c if c.isalnum() or c in "-_" else "_" for c in self.name) or "ws"

    def add_metas(self, source_path: str, metas: list[RecordingMeta]) -> tuple[int, int]:
        """把一批扫描结果并入指定来源（按 path 去重）.

        :returns: (新增条数, 重复跳过条数)——UI 导入完成提示用
        """
        src = self.sources.setdefault(source_path, ImportSource(source_path))
        added = dup = 0
        for meta in metas:
            meta.import_source = source_path
            if meta.path in src.recordings:
                dup += 1  # 同一文件已在此来源下：保留原条目（rec_id 稳定）
                continue
            src.recordings[meta.path] = meta
            added += 1
        return added, dup

    def remove_recording(self, meta_path: str) -> None:
        """从工作区移除一条录制（只动索引，不删数据文件）."""
        for src in self.sources.values():
            src.recordings.pop(meta_path, None)
        self.remove_empty_sources()

    def remove_source(self, source_path: str) -> None:
        """移除整个导入来源及其下全部条目."""
        self.sources.pop(source_path, None)

    def remove_empty_sources(self) -> None:
        """清掉已无任何录制的来源节点."""
        self.sources = {p: s for p, s in self.sources.items() if s.recordings}

    # ------------------------------------------------------------ 查询

    def all_metas(self) -> list[RecordingMeta]:
        """全部录制元数据（元数据表数据源）."""
        return [m for s in self.sources.values() for m in s.recordings.values()]

    def find_by_path(self, path: str) -> Optional[RecordingMeta]:
        for s in self.sources.values():
            if path in s.recordings:
                return s.recordings[path]
        return None

    def __len__(self) -> int:
        return len(self.all_metas())

    # ------------------------------------------------------------ 持久化

    def save(self) -> Path:
        """写 JSON（原子替换：先写临时文件再 rename，防半截文件）."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": self.name,
            "saved_at": time.time(),
            "sources": [s.to_dict() for s in self.sources.values()],
        }
        tmp = self._file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self._file)
        logger.info("工作区已保存：%s（%d 条录制）", self._file, len(self))
        return self._file

    @classmethod
    def load(cls, name: str) -> "Workspace":
        """按名加载；不存在则返回同名空工作区."""
        ws = cls(name)
        if ws._file.exists():
            try:
                payload = json.loads(ws._file.read_text(encoding="utf-8"))
                ws.sources = {
                    d["path"]: ImportSource.from_dict(d) for d in payload.get("sources", [])
                }
                logger.info("工作区已加载：%s（%d 来源 %d 条）", name, len(ws.sources), len(ws))
            except Exception:  # noqa: BLE001 - 损坏则从空开始，不崩
                logger.exception("工作区文件损坏，从空工作区开始：%s", ws._file)
        return ws

    @classmethod
    def set_current(cls, name: str) -> None:
        """记住当前工作区名（下次启动自动恢复）."""
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CURRENT_WS_FILE.write_text(name, encoding="utf-8")

    @classmethod
    def current_name(cls) -> str:
        if CURRENT_WS_FILE.exists():
            name = CURRENT_WS_FILE.read_text(encoding="utf-8").strip()
            if name:
                return name
        return DEFAULT_WORKSPACE
