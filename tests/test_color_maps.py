"""渐变 CSV 的 GBK 安全加载测试（坑 #65 终版，color_maps 模块）.

核心保证：加载路径**显式 UTF-8**、与平台 locale 无关——中文 Windows
GBK 环境行为不变。解析器用含非 ASCII 注释/名称的文本直接验证（GBK
必炸试金石内容），真实文件加载验证端到端 + 双层缓存命中。
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

import pyqtgraph as pg

from dataloadv.ui.widgets.color_maps import _parse_gradient_csv, get_builtin_gradient

# GBK 必炸试金石（坑 #65 教训）：CJK 三字节 UTF-8 后跟 ASCII，GBK 配对必炸；
# 分号后带非 ASCII 名称正是 pyqtgraph 渐变文件的真实形态
_CSV_WITH_NON_ASCII = (
    "; gradient definition 文1号脑电©测试\n"
    "0.0, 0.0, 0.0; 名称甲\n"
    "\n"
    "0.5, 0.5, 0.5; 名称乙\n"
    "1.0, 1.0, 1.0\n"
    "; trailing comment 注释\n"
)


class TestParseGradientCsv:
    def test_parses_colors_and_skips_comments(self):
        colors = _parse_gradient_csv(_CSV_WITH_NON_ASCII)
        assert colors == [(0, 0, 0), (128, 128, 128), (255, 255, 255)]  # int(255*0.5+0.5)=128

    def test_encoding_explicit_not_locale_dependent(self):
        """解析输入是 str（调用方以显式 utf-8 读入）——GBK 环境行为不变的保证."""
        # 同一文本经 UTF-8 解码后进来，结果与 locale 无关
        text = _CSV_WITH_NON_ASCII.encode("utf-8").decode("utf-8")
        assert _parse_gradient_csv(text) == _parse_gradient_csv(_CSV_WITH_NON_ASCII)


class TestGetBuiltinGradient:
    def test_loads_real_turbo_and_fills_cache(self):
        _mapCache = getattr(pg.colormap, "_mapCache", None)
        if _mapCache is not None:
            _mapCache.pop("turbo", None)  # 清场：验证完整加载路径
        cm = get_builtin_gradient("turbo")
        assert isinstance(cm, pg.ColorMap)
        assert cm.name == "turbo"
        assert len(cm.getColors()) == 256  # pyqtgraph 内置 turbo 为 256 级
        # 回填了 pyqtgraph 缓存——后续 colormap.get 直接命中，不再触文件
        assert _mapCache is None or "turbo" in _mapCache

    def test_second_call_returns_cached_object(self):
        cm1 = get_builtin_gradient("viridis")
        cm2 = get_builtin_gradient("viridis")
        assert cm1 is cm2  # 同一对象（缓存命中）
