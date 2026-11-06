"""pyqtgraph 内置渐变的内嵌加载（坑 #65 终章三，v0.2.5）.

pyqtgraph ``colormap.get()`` 读自带渐变 CSV 用**平台默认编码**（``open``
不带 encoding）——中文 Windows（GBK）下崩 ``UnicodeDecodeError``（v0.2.0
用户实锤）。v0.2.4 调查发现更深一层：**用户机器包内的 turbo.csv 与一切
分发渠道内容不一致**（conda/PyPI 通用 wheel 均纯 ASCII；用户机含 0xa9/
0xab/0xbd，UTF-8/GBK 双不可解码，疑似该机解压/杀软改写文本文件，且自
v0.2.0 起即如此）——任何"从盘读渐变文件"的方案在该机器上都不可靠。

终章方案：turbo/viridis 的 256 级 RGBA 以 base64 内嵌（由 pristine 官方
文件程序化生成，回归测试与 ``pg.colormap.get`` 逐字节交叉核验）——零
磁盘 IO、零编码依赖、与平台/机器状态无关；仍回填 pyqtgraph ``_mapCache``
（进程内后续 ``colormap.get`` 命中缓存）。jet/hot 公式生成不走文件。

方案史（HANDOFF 坑 #65 三章）：v0.2.1 PYTHONUTF8 自重启（冻结环境无效）→
v0.2.3 全局包装 builtins.open（Windows 引爆 shiboken 导入）→ v0.2.4
显式 UTF-8 读文件（用户机文件内容本身异常）→ v0.2.5 内嵌。
"""

from __future__ import annotations

import base64

import numpy as np
import pyqtgraph as pg

# 256 级 × RGBA（uint8）——pyqtgraph 0.14.0 colors/maps 官方定义的程序化转储
_TURBO_B64 = (
    "MBI7/zIVQ/8zGEr/NBtR/zUeWP82IV//NyRm/zgnbf85KnP/Oi15/zsvgP88Mob/PTWL/z44kf8/"
    "O5f/Pz6c/0BAov9BQ6f/QUas/0JJsf9CS7X/Q066/0RRv/9EVMP/RFbH/0VZy/9FXM//RV7T/0Zh"
    "1v9GZNr/Rmbd/0Zp4P9Ga+P/R27m/0dx6f9Hc+v/R3bu/0d48P9He/L/Rn30/0aA9v9Ggvj/RoX6"
    "/0aH+/9Fivz/RYz9/0SP/v9Dkf7/QpT//0GW//9Amf//Ppv+/z2e/v87oP3/OqP8/zil+/83qPr/"
    "Nav4/zOt9/8xr/X/L7L0/y608v8st/D/Krnu/yi86/8nvun/JcDn/yPD5P8ixeL/IMff/x/J3f8e"
    "y9r/HM3Y/xvQ1f8a0tL/GtTQ/xnVzf8Y18r/GNnI/xjbxf8Y3cL/GN7A/xjgvf8Z4rv/GeO5/xrk"
    "tv8c5rT/Heey/x/pr/8g6qz/Iuuq/yXsp/8n7qT/Ku+h/yzwnv8v8Zv/MvKY/zXzlP849JH/PPWO"
    "/z/2iv9D94f/RviE/0r4gP9O+X3/Uvp6/1X6dv9Z+3P/Xfxv/2H8bP9l/Wn/af1m/23+Yv9x/l//"
    "df5c/3n+Wf99/1b/gP9T/4T/Uf+I/07/i/9L/4//Sf+S/0f/lv5E/5n+Qv+c/kD/n/0//6H9Pf+k"
    "/Dz/p/w6/6n7Of+s+zj/r/o3/7H5Nv+0+Db/t/c1/7n2Nf+89TT/vvQ0/8HzNP/D8TT/xvA0/8jv"
    "NP/L7TT/zew0/9DqNP/S6TX/1Oc1/9flNf/Z5Db/2+I2/93gN//f3zf/4d03/+PbOP/l2Tj/59c5"
    "/+nVOf/r0zn/7NE6/+7POv/vzTr/8cs6//LJOv/0xzr/9cU6//bDOv/3wTr/+L45//m8Of/6ujn/"
    "+7g4//u2N//8szb//LE2//2uNf/9rDT//qkz//6nMv/+pDH//qEw//6eL//+my3//pks//6WK//+"
    "kyr//pAp//2NJ//9iib//Icl//yEI//7gSL/+34h//p7H//5eB7/+XUd//hyHP/3bxr/9mwZ//Vp"
    "GP/0Zhf/82MV//JgFP/xXRP/8FsS/+9YEf/tVRD/7FMP/+tQDv/qTg3/6EsM/+dJDP/lRwv/5EUK"
    "/+JDCv/hQQn/3z8I/909CP/cOwf/2jkH/9g3Bv/WNQb/1DMF/9IxBf/QLwX/zi0E/8wrBP/KKgT/"
    "yCgD/8UmA//DJQP/wSMC/74hAv+8IAL/uR4C/7cdAv+0GwH/shoB/68YAf+sFwH/qRYB/6cUAf+k"
    "EwH/oRIB/54QAf+bDwH/mA4B/5UNAf+SCwH/jgoB/4sJAv+ICAL/hQcC/4EGAv9+BQL/egQD/w=="
)
_VIRIDIS_B64 = (
    "RAFU/0QCVv9FBFf/RQVZ/0YHWv9GCFz/Rgpd/0YLXv9HDWD/Rw5h/0cQY/9HEWT/RxNl/0gUZ/9I"
    "Fmj/SBdp/0gYav9IGmz/SBtt/0gcbv9IHW//SB9w/0ggcf9IIXP/SCN0/0gkdf9IJXb/SCZ3/0go"
    "eP9IKXn/Ryp6/0csev9HLXv/Ry58/0cvff9GMH7/RjJ+/0Yzf/9GNID/RTWB/0U3gf9FOIL/RDmD"
    "/0Q6g/9EO4T/Qz2E/0M+hf9CP4X/QkCG/0JBhv9BQof/QUSH/0BFiP9ARoj/P0eI/z9Iif8+SYn/"
    "PkqJ/z5Miv89TYr/PU6K/zxPiv88UIv/O1GL/ztSi/86U4v/OlSM/zlVjP85Voz/OFiM/zhZjP83"
    "Woz/N1uN/zZcjf82XY3/NV6N/zVfjf80YI3/NGGN/zNijf8zY43/MmSO/zJljv8xZo7/MWeO/zFo"
    "jv8waY7/MGqO/y9rjv8vbI7/Lm2O/y5ujv8ub47/LXCO/y1xjv8scY7/LHKO/yxzjv8rdI7/K3WO"
    "/yp2jv8qd47/KniO/yl5jv8peo7/KXuO/yh8jv8ofY7/J36O/yd/jv8ngI7/JoGO/yaCjv8mgo7/"
    "JYOO/yWEjv8lhY7/JIaO/ySHjv8jiI7/I4mO/yOKjf8ii43/IoyN/yKNjf8hjo3/IY+N/yGQjf8h"
    "kYz/IJKM/yCSjP8gk4z/H5SM/x+Vi/8flov/H5eL/x+Yi/8fmYr/H5qK/x6biv8enIn/Hp2J/x+e"
    "if8fn4j/H6CI/x+hiP8foYf/H6KH/yCjhv8gpIb/IaWF/yGmhf8ip4X/IqiE/yOpg/8kqoP/JauC"
    "/yWsgv8mrYH/J62B/yiugP8pr3//KrB//yyxfv8tsn3/LrN8/y+0fP8xtXv/MrZ6/zS2ef81t3n/"
    "N7h4/zi5d/86unb/O7t1/z28dP8/vHP/QL1y/0K+cf9Ev3D/RsBv/0jBbv9KwW3/TMJs/07Da/9Q"
    "xGr/UsVp/1TFaP9Wxmf/WMdl/1rIZP9cyGP/Xsli/2DKYP9jy1//Zcte/2fMXP9pzVv/bM1a/27O"
    "WP9wz1f/c9BW/3XQVP930VP/etFR/3zSUP9/007/gdNN/4TUS/+G1Un/idVI/4vWRv+O1kX/kNdD"
    "/5PXQf+V2ED/mNg+/5vZPP+d2Tv/oNo5/6LaN/+l2zb/qNs0/6rcMv+t3DD/sN0v/7LdLf+13iv/"
    "uN4p/7reKP+93yb/wN8l/8LfI//F4CH/yOAg/8rhH//N4R3/0OEc/9LiG//V4hr/2OIZ/9rjGf/d"
    "4xj/3+MY/+LkGP/l5Bn/5+QZ/+rlGv/s5Rv/7+Uc//HlHf/05h7/9uYg//jmIf/75yP//ecl/w=="
)

_EMBEDDED = {"turbo": _TURBO_B64, "viridis": _VIRIDIS_B64}


def get_builtin_gradient(name: str) -> pg.ColorMap:
    """按名称取内置渐变（纯内嵌数据，零磁盘 IO、零编码依赖）.

    优先级：pyqtgraph ``_mapCache`` → 内嵌 base64 解码构造（并回填缓存）。
    未知名称退回 ``pg.colormap.get``（当前无此调用路径，防御性保留——该
    回退在中文 Windows 上对文件型渐变仍走平台默认编码，勿新增依赖）。
    """
    cache = getattr(pg.colormap, "_mapCache", None)
    if cache is not None and name in cache:
        return cache[name]
    b64 = _EMBEDDED.get(name)
    if b64 is None:
        return pg.colormap.get(name)
    colors = np.frombuffer(base64.b64decode(b64), dtype=np.uint8).reshape(-1, 4)
    cm = pg.ColorMap(pos=np.linspace(0.0, 1.0, len(colors)), color=colors, name=name)
    if cache is not None:
        cache[name] = cm  # 回填：进程内后续查找不再构造
    return cm
