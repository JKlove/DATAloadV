"""工作区与 LoadedRawCache 单测（纯逻辑层，不依赖真实数据）."""

from __future__ import annotations

from pathlib import Path

from dataloadv.core.recording import LoadedRawCache, RecordingMeta, LoadPolicy
from dataloadv.core.workspace import Workspace


def _meta(path: str, n_ch: int = 4, sfreq: float = 250.0, dur: float = 10.0) -> RecordingMeta:
    """最小可用的合成元数据."""
    return RecordingMeta(
        path=path,
        format="EDF",
        reader_id="edf",
        n_channels=n_ch,
        channel_names=[f"ch{i}" for i in range(n_ch)],
        channel_types=["eeg"] * n_ch,
        sfreq=sfreq,
        duration_s=dur,
    )


def test_workspace_add_dedup(tmp_path):
    """同文件重复导入不产生新条目；不同来源分别计数."""
    ws = Workspace("测试工作区")
    added, dup = ws.add_metas("/a", [_meta("/a/x.edf"), _meta("/a/y.edf")])
    assert (added, dup) == (2, 0)
    added, dup = ws.add_metas("/a", [_meta("/a/x.edf")])
    assert (added, dup) == (0, 1)
    assert len(ws) == 2
    assert ws.find_by_path("/a/x.edf") is not None


def test_workspace_remove(tmp_path):
    ws = Workspace("测试工作区")
    ws.add_metas("/a", [_meta("/a/x.edf")])
    ws.remove_recording("/a/x.edf")
    assert len(ws) == 0
    assert ws.sources == {}  # 空来源自动清理


def test_workspace_persistence(tmp_path, monkeypatch):
    """save/load 往返：来源、条目、选项都保留."""
    monkeypatch.setattr(
        "dataloadv.core.workspace.WORKSPACE_ROOT", tmp_path / "workspaces"
    )
    ws = Workspace("persist_test")
    ws.add_metas("/src", [_meta("/src/a.edf", n_ch=16, sfreq=1000.0)])
    ws.save()

    ws2 = Workspace.load("persist_test")  # 同名 → 同 _file 路径
    assert len(ws2) == 1
    m = ws2.find_by_path("/src/a.edf")
    assert m is not None and m.n_channels == 16 and m.sfreq == 1000.0
    assert m.import_source == "/src"


def test_loaded_raw_cache_lru_eviction():
    """超预算时 LRU 逐出未 pin 的条目；pin 的保留（用假 Recording 验证逻辑）."""

    class _FakeRec:
        def __init__(self, rid, nbytes):
            from dataloadv.core.recording import RecordingMeta

            self.meta = RecordingMeta(
                path=f"/{rid}",
                format="EDF",
                reader_id="edf",
                n_channels=1,
                channel_names=["ch"],
                channel_types=["eeg"],
                sfreq=1.0,
                duration_s=nbytes / 8.0,  # estimated_bytes = n_ch*dur*8 = nbytes
            )
            self.unloaded = False

        def unload(self):
            self.unloaded = True

    cache = LoadedRawCache.reset(byte_budget=100)  # 每条 40 字节 → 3 条 = 120 超限
    a, b, c = _FakeRec("a", 40), _FakeRec("b", 40), _FakeRec("c", 40)
    cache.register(a)
    cache.register(b)
    cache.register(c)  # 注册 c 时 a 应被逐出（LRU 头）
    assert a.unloaded and not b.unloaded and not c.unloaded

    # pin 的不被逐出
    d = _FakeRec("d", 40)
    cache.pin(b)
    cache.register(d)  # b 被钉，应逐出 c
    assert c.unloaded and not b.unloaded and not d.unloaded
    assert b.unloaded is False


def test_load_policy_enum():
    assert LoadPolicy.PRELOAD != LoadPolicy.LAZY
