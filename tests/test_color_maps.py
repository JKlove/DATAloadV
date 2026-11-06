"""内嵌渐变加载测试（坑 #65 终章三，color_maps 模块）.

核心保证：**零磁盘 IO、零编码依赖**——与平台 locale、机器上 pyqtgraph
数据文件的实际状态完全无关（用户机 turbo.csv 被改写的教训）。交叉核验：
内嵌数据与本地 pristine 文件加载的官方定义逐字节一致。
"""

from __future__ import annotations

import base64

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

import pyqtgraph as pg

from dataloadv.ui.widgets.color_maps import _EMBEDDED, get_builtin_gradient


class TestEmbeddedData:
    def test_base64_valid_and_256_rgba(self):
        for name, b64 in _EMBEDDED.items():
            raw = base64.b64decode(b64, validate=True)
            assert len(raw) == 256 * 4
            np.frombuffer(raw, dtype=np.uint8).reshape(-1, 4)  # 形状可解

    def test_matches_official_definition(self):
        """交叉核验：内嵌值 == 本地 pristine 文件经 pg.colormap.get 的官方值."""
        for name in _EMBEDDED:
            ours = np.asarray(get_builtin_gradient(name).getColors(), dtype=np.uint8)
            official = np.asarray(pg.colormap.get(name).getColors(), dtype=np.uint8)
            assert np.array_equal(ours, official), f"{name} 与官方定义不一致"


class TestGetBuiltinGradient:
    def test_no_disk_io(self, tmp_path, monkeypatch):
        """打桩 open 抛异常——内嵌路径不触任何文件读取（终章核心保证）."""
        import builtins

        real_open = builtins.open

        def _no_open(*a, **k):
            raise AssertionError(f"内嵌渐变不应读盘: {a[0]}")

        pg.colormap._mapCache.pop("turbo", None)  # 清缓存走完整路径
        monkeypatch.setattr(builtins, "open", _no_open)
        try:
            cm = get_builtin_gradient("turbo")
            assert isinstance(cm, pg.ColorMap)
        finally:
            monkeypatch.setattr(builtins, "open", real_open)
            pg.colormap._mapCache.pop("turbo", None)  # 清掉本次回填，别污染其他测试

    def test_second_call_returns_cached_object(self):
        cm1 = get_builtin_gradient("viridis")
        cm2 = get_builtin_gradient("viridis")
        assert cm1 is cm2

    def test_unknown_name_falls_back_to_pyqtgraph(self):
        # 防御性回退路径：未知名交给 pg.colormap.get（其行为=抛 FileNotFoundError）
        with pytest.raises(Exception):
            get_builtin_gradient("no_such_gradient")
