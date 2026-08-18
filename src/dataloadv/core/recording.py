"""Recording 统一数据模型——整个应用的数据地基.

三个核心概念：

1. ``RecordingMeta``（pydantic）：仅从文件头解析的元数据，可 JSON 序列化持久化。
   批量导入 1500 个文件时**只**生成它（不碰数据本体），元数据表/工作区树都吃它。
2. ``EventTable``：事件/标注表（onset/duration/code/中文label）。持有 numpy 数组，
   故不用 pydantic；提供与 mne.Annotations 互转、窗口内筛选等工具方法。
3. ``Recording``：应用对"一条录制"的完整句柄 = meta + events + 惰性 mne Raw +
   provenance（处理历史）。按需加载（LAZY/PRELOAD），配合 ``LoadedRawCache``
   全局 LRU 控制内存。

加载策略（见 plan.md §4）：
- 预估数据 < ``SMALL_FILE_BYTES`` → PRELOAD（浏览更跟手，且支持后续就地处理）
- ≥ → LAZY：mne 按窗口读 ``raw.get_data(start, stop)`` 服务绘图
- 批处理/预览强制 PRELOAD（mne 滤波需要），用完即 ``unload()``
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import numpy as np
from pydantic import BaseModel, Field

if TYPE_CHECKING:  # 仅类型标注用，避免运行时循环 import
    from ..io.base import BaseReader

logger = logging.getLogger(__name__)

# 预估数据量小于该值直接整载（8 字节/样本 × 通道 × 时点）；200MB 与 plan.md §4 一致
SMALL_FILE_BYTES = 200 * 1024 * 1024


class LoadPolicy(str, Enum):
    """数据加载策略.

    - HEADER_ONLY：仅元数据（批量导入扫描用，绝不触碰数据本体）
    - LAZY：mne preload=False，按窗口读（大文件浏览）
    - PRELOAD：整载进内存（小文件浏览 / 一切需要就地处理的场景）
    """

    HEADER_ONLY = "header_only"
    LAZY = "lazy"
    PRELOAD = "preload"


class RecordingMeta(BaseModel):
    """仅由文件头派生的录制元数据（无数据本体，可持久化为 JSON）.

    字段说明：
    - ``rec_id``：应用内稳定标识（uuid4 hex）。同一文件重复导入时由 Workspace
      去重（按 path），故 rec_id 在一个工作区内与文件一一对应
    - ``subject/session/run/task``：从文件名/头信息猜出的 BIDS 风格实体，猜不出为 None
    - ``channel_types``：mne 类型串（eeg/ecog/misc/…），与 channel_names 一一对应
    - ``event_summary``：{事件码: 出现次数}，元数据表"事件数"列与筛选用
    - ``import_source``：产生本条目的导入来源路径（工作区按来源分组）
    """

    rec_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    path: str
    format: str  # 展示名，如 "EDF"
    reader_id: str
    subject: Optional[str] = None
    session: Optional[str] = None
    run: Optional[str] = None
    task: Optional[str] = None
    n_channels: int
    channel_names: list[str]
    channel_types: list[str]
    sfreq: float
    duration_s: float
    n_events: int = 0
    event_summary: dict[str, int] = Field(default_factory=dict)
    file_size: int = 0
    mtime: float = 0.0
    notes: str = ""
    tags: list[str] = Field(default_factory=list)
    import_source: Optional[str] = None

    @property
    def filename(self) -> str:
        """文件名（不含目录），列表展示用."""
        return Path(self.path).name

    def estimated_bytes(self) -> int:
        """按 float64 估算整载数据量（决定 LAZY/PRELOAD 的依据）."""
        n_times = int(self.duration_s * self.sfreq)
        return self.n_channels * n_times * 8


@dataclass
class EventTable:
    """事件/标注表.

    为什么不用 pydantic：onset/duration 是 numpy 数组，pydantic 校验 ndarray
    得写自定义类型，收益低；dataclass + 工具方法足够。
    - ``code``：事件码（GDF 数字码 "769"、PhysioNet "T1"、羊数据 "标注1"…）
    - ``label``：中文展示标签，与 code 等长（M1 阶段 label=code，M2 接事件码映射表）
    """

    onset: np.ndarray = field(default_factory=lambda: np.empty(0))  # 秒
    duration: np.ndarray = field(default_factory=lambda: np.empty(0))  # 秒
    code: list[str] = field(default_factory=list)
    label: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.code)

    @classmethod
    def from_mne_annotations(cls, raw) -> "EventTable":
        """从 mne Raw 的 Annotations 构建（EDF/GDF/FIF 等格式的常规路径）."""
        ann = getattr(raw, "annotations", None)
        if ann is None or len(ann) == 0:
            return cls()
        codes = [str(d) for d in ann.description]
        return cls(
            onset=np.asarray(ann.onset, dtype=float),
            duration=np.asarray(ann.duration, dtype=float),
            code=codes,
            label=list(codes),  # label=code；中文映射在展示层经 event_maps 完成
        )

    def in_window(self, t0: float, t1: float) -> list[int]:
        """返回 onset 落在 [t0, t1) 内的事件下标（浏览器画可视区内事件线用）."""
        if len(self) == 0:
            return []
        mask = (self.onset >= t0) & (self.onset < t1)
        return np.nonzero(mask)[0].tolist()

    def codes_summary(self) -> dict[str, int]:
        """{事件码: 次数}，写入 RecordingMeta.event_summary."""
        out: dict[str, int] = {}
        for c in self.code:
            out[c] = out.get(c, 0) + 1
        return out


class Recording:
    """一条录制的应用级句柄（非 QObject；线程规则见 HANDOFF.md）.

    生命周期：Reader.open() 创建（可能仅 HEADER/LAZY）→ UI 打开浏览 tab 时
    ``ensure_raw()`` → 浏览/处理 → tab 关闭或 LRU 逐出时 ``unload()``。
    """

    def __init__(self, meta: RecordingMeta, events: EventTable, reader: "BaseReader") -> None:
        self.meta = meta
        self.events = events
        self.reader = reader
        self.provenance: list[dict] = []  # 处理历史 [{step_id, params, applied_at}]
        self._raw = None  # mne.io.BaseRaw | None

    # ------------------------------------------------------------ 加载/卸载

    def is_loaded(self) -> bool:
        return self._raw is not None

    def ensure_raw(self, policy: LoadPolicy):
        """确保 mne Raw 以不低于 ``policy`` 的方式可用并返回之.

        - 已加载且满足请求（PRELOAD 已整载 / LAZY 任意已加载）→ 直接返回
        - HEADER_ONLY 请求但未加载 → 按 reader 推荐策略加载（浏览场景）
        """
        if self._raw is None:
            want = policy
            if want is LoadPolicy.HEADER_ONLY:
                # HEADER_ONLY 不是加载请求：按大小自动选 LAZY/PRELOAD
                want = self.recommended_policy()
            self._raw = self.reader.load_raw(self.meta.path, want)
            LoadedRawCache.instance().register(self)
        elif policy is LoadPolicy.PRELOAD and not getattr(self._raw, "preload", False):
            self._raw.load_data()  # LAZY → PRELOAD 升级（mne 就地补载数据）
            LoadedRawCache.instance().touch(self)
        return self._raw

    def recommended_policy(self) -> LoadPolicy:
        """按预估数据量推荐加载策略（plan §4：<200MB 整载，否则按窗口）."""
        if self.reader.lazy_capable:
            return LoadPolicy.PRELOAD if self.meta.estimated_bytes() < SMALL_FILE_BYTES else LoadPolicy.LAZY
        # 无 lazy 能力的格式（mat/csv/h5）读取器始终物化 RawArray
        return LoadPolicy.PRELOAD

    def unload(self) -> None:
        """释放数据本体（meta/events 保留，可随时 ensure_raw 重载）."""
        if self._raw is not None:
            logger.debug("卸载数据：%s", self.meta.filename)
        self._raw = None
        LoadedRawCache.instance().forget(self)

    # ------------------------------------------------------------ 数据访问

    def get_window(
        self, t0: float, t1: float, picks: Optional[list[int]] = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """读取时间窗 [t0, t1) 秒的数据.

        :param picks: 通道索引列表；None = 全部通道
        :returns: (data[ch, n_times], times[n_times])，单位为 mne 原生（伏特）
        """
        raw = self.ensure_raw(LoadPolicy.HEADER_ONLY)  # 确保有句柄（策略自动）
        sf = raw.info["sfreq"]
        start = max(0, int(round(t0 * sf)))
        stop = min(raw.n_times, int(round(t1 * sf)))
        if stop <= start:
            return np.empty((0 if picks is None else len(picks), 0)), np.empty(0)
        data = raw.get_data(picks=picks, start=start, stop=stop)
        times = np.arange(start, stop) / sf
        return data, times

    @property
    def raw(self):
        """当前 mne 句柄（可能为 None；需要数据请走 ensure_raw/get_window）."""
        return self._raw


class LoadedRawCache:
    """已加载 Recording 的全局 LRU（进程内单例）.

    目的：同时打开多个浏览 tab（如 3 个羊 EDF + 1 个大 mat）时内存可控。
    - 字节预算默认 1.5GB（可配）；超预算按 LRU 逐出，**被 pin 的不逐**
      （运行中的批处理任务、可见的浏览 tab 都会 pin 住自己的 Recording）
    - 线程安全：批处理 worker 与 UI 都会触碰，内部一把锁足够（操作皆轻量）
    """

    _instance: Optional["LoadedRawCache"] = None

    def __init__(self, byte_budget: int = 1536 * 1024 * 1024) -> None:
        self.byte_budget = byte_budget
        self._lock = threading.Lock()
        self._items: dict[str, tuple[Recording, int]] = {}  # rec_id -> (rec, pin_count)
        self._order: list[str] = []  # LRU 序：尾为最近使用

    @classmethod
    def instance(cls) -> "LoadedRawCache":
        """进程级单例（测试可用 ``reset()`` 重建）."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls, byte_budget: int = 1536 * 1024 * 1024) -> "LoadedRawCache":
        """重建单例（测试隔离用）."""
        cls._instance = cls(byte_budget)
        return cls._instance

    # ------------------------------------------------------------------ 操作

    def register(self, rec: Recording) -> None:
        """Recording 完成加载后登记（ensure_raw 自动调用）."""
        with self._lock:
            self._items[rec.meta.rec_id] = (rec, self._items.get(rec.meta.rec_id, (rec, 0))[1])
            self._touch_locked(rec.meta.rec_id)
            victims = self._pick_victims_locked()
        self._unload_victims(victims)  # 锁外执行（unload→forget 会拿锁）

    def touch(self, rec: Recording) -> None:
        """标记最近使用（每次窗口读取后调用，防正被浏览的对象被逐出）."""
        with self._lock:
            if rec.meta.rec_id in self._items:
                self._touch_locked(rec.meta.rec_id)

    def forget(self, rec: Recording) -> None:
        """Recording.unload 时移除登记."""
        with self._lock:
            self._items.pop(rec.meta.rec_id, None)
            if rec.meta.rec_id in self._order:
                self._order.remove(rec.meta.rec_id)

    def pin(self, rec: Recording) -> None:
        """加钉：批处理/可见 tab 持有期间不可被逐出."""
        with self._lock:
            if rec.meta.rec_id in self._items:
                cur = self._items[rec.meta.rec_id]
                self._items[rec.meta.rec_id] = (cur[0], cur[1] + 1)

    def unpin(self, rec: Recording) -> None:
        """去钉（引用计数减一）."""
        with self._lock:
            cur = self._items.get(rec.meta.rec_id)
            if cur and cur[1] > 0:
                self._items[rec.meta.rec_id] = (cur[0], cur[1] - 1)

    # ------------------------------------------------------------------ 内部

    def _touch_locked(self, rec_id: str) -> None:
        if rec_id in self._order:
            self._order.remove(rec_id)
        self._order.append(rec_id)

    def _pick_victims_locked(self) -> list[Recording]:
        """在持锁状态下挑选应逐出的 Recording（不执行 unload）.

        从 LRU 头部开始，跳过被 pin 的（移到队尾再议），直到总字节回到预算内。
        摘链而不执行任何回调——unload 必须在锁外做（其内部 forget 要拿锁，
        非重入锁下锁内调用会死锁；这是本方法存在的全部原因）。
        """
        total = sum(r.meta.estimated_bytes() for r, _ in self._items.values())
        victims: list[Recording] = []
        guard = 0  # 防御全被钉时的循环空转
        while total > self.byte_budget and self._order and guard <= len(self._order):
            guard += 1
            rec_id = self._order[0]
            entry = self._items.get(rec_id)
            if entry is None:
                self._order.pop(0)
                continue
            rec, pins = entry
            if pins > 0:
                self._order.pop(0)
                self._order.append(rec_id)  # 被钉的挪到队尾，继续看下一个
                continue
            total -= rec.meta.estimated_bytes()
            self._items.pop(rec_id, None)
            self._order.pop(0)
            victims.append(rec)
        return victims

    @staticmethod
    def _unload_victims(victims: list[Recording]) -> None:
        """锁外真正执行逐出（victims 已从表中摘除，forget 为 no-op）."""
        for rec in victims:
            logger.info("LRU 逐出：%s", rec.meta.filename)
            try:
                rec.unload()
            except Exception:  # noqa: BLE001 - 逐出失败不影响主流程
                logger.exception("逐出时出错（忽略）")
