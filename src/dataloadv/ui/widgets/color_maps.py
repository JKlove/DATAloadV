"""pyqtgraph 内置渐变的 GBK 安全加载（坑 #65 终版，v0.2.4）.

pyqtgraph ``colormap.get()`` 读自带渐变 CSV 用**平台默认编码**（``open``
不带 encoding）——中文 Windows（GBK）遇 UTF-8 内容必炸
``UnicodeDecodeError: 'gbk' codec...``（v0.2.0/v0.2.2 用户实锤，崩点
``signal_browser`` 构建必经的 turbo）。

方案沿革：v0.2.1/v0.2.2 的 PYTHONUTF8 自重启路线在冻结环境无效（坑 #65）；
v0.2.3 的全局包装 ``builtins.open`` 在 Windows 实锤引发**新崩溃**——
shiboken 导入期的容错路径依赖原解码行为，全局改内建函数把所有库的地基
一起换了（``cannot pickle 'EditorHelper' object``，坑 #65 终章二）。
故终版收敛为**调用点外科修**：本模块按显式 UTF-8 自己读渐变 CSV 构造
``ColorMap``，并写进 pyqtgraph 的 ``_mapCache``——之后进程内任何
``colormap.get`` 查找直接命中缓存，pyqtgraph 自己的文件读取路径完全
不会走到。本项目全部文件型渐变加载（turbo/viridis）一律经本模块；
jet/hot 是公式生成不走文件，不受影响。
"""

from __future__ import annotations

import os

import numpy as np
import pyqtgraph as pg


def _parse_gradient_csv(text: str) -> list[tuple[int, int, int]]:
    """解析 pyqtgraph 渐变 CSV 文本（与 colormap._getFromFile 同口径）.

    行格式 ``r,g,b[;名称/注释]``（分号后可含非 ASCII 名称——这正是 GBK
    炸点，我们读入时已显式 UTF-8 故安全）；空行与 ``;`` 注释行跳过。
    """
    colors: list[tuple[int, int, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        comp = line.split(";", 1)[0].split(",")
        if len(comp) < 3:
            continue
        colors.append(tuple(int(255 * float(c) + 0.5) for c in comp))  # type: ignore[arg-type]
    return colors


def get_builtin_gradient(name: str) -> pg.ColorMap:
    """按名称取 pyqtgraph 内置渐变（显式 UTF-8 读文件 + 双层缓存）.

    优先级：pyqtgraph ``_mapCache`` → 本模块自读 CSV 并回填 ``_mapCache``；
    CSV 缺失（理论上的裁剪环境）时退回 ``pg.colormap.get``（UTF-8 locale
    下等价正确，异常环境下至少不比现状差）。
    """
    cache = getattr(pg.colormap, "_mapCache", None)
    if cache is not None and name in cache:
        return cache[name]
    fn = os.path.join(os.path.dirname(pg.__file__), "colors", "maps", f"{name}.csv")
    try:
        # encoding 显式 utf-8（utf-8-sig 兼容 BOM）——与平台 locale 无关，
        # 中文 Windows GBK 下行为不变
        with open(fn, encoding="utf-8-sig") as fh:
            colors = _parse_gradient_csv(fh.read())
    except OSError:
        return pg.colormap.get(name)  # 文件不在：退回原路径（见 docstring）
    cm = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors, name=name)
    if cache is not None:
        cache[name] = cm  # 回填：进程内后续查找不再触文件
    return cm
