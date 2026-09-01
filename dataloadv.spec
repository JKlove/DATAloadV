# -*- mode: python ; coding: utf-8 -*-
# DataloadV 跨平台打包 spec（macOS .app / Windows onedir .exe 共用一份）
#
# 用法（项目根、dlv 环境下）：
#   python -m PyInstaller dataloadv.spec --noconfirm
#
# 设计依据 PACKAGING_HANDOFF.md（2026-09-01）：
# - 入口走 packaging/entry.py（console_script 等价 shim），不直接 Analysis app.py
# - hiddenimports 必须显式收录函数内延迟 import 的 io/neo_reader、io/nwb_reader
#   （PyInstaller 静态分析扫不到函数体内的 import）
# - mne 需要自带模板数据（montage/通道名映射等）→ collect_data_files('mne')；
#   刻意不用 collect_all('mne')——会把 mne.tests 等垃圾打进包、体积暴涨几百 MB
# - pynwb/hdmf 的命名空间 JSON 必须随包（缺失时 NWB 读取直接报 schema 找不到）
# - 第一轮全量打包（excludes=[]），冒烟通过后再按 M10-4 逐项瘦身
# - onedir 形态（非 onefile）：onefile 每次启动要解包到临时目录，科学栈体积下
#   启动慢数秒；onedir 压 zip 分发
# - 不签名不公证（无 Apple 开发者账号），首次打开走"右键→打开"

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# spec 文件所在目录（= 仓库根）。仓库路径含空格（"intervention BCI"），
# 所有拼接走 pathlib/列表传参，绝不手工拼 shell 字符串。
# 注意：PyInstaller 6.22.2 的 spec 全局只有 SPECPATH（str，spec 所在目录），
# 没有 SPECDIR——写 SPECDIR 会 NameError 秒退（已踩，坑入 HANDOFF）
ROOT = Path(SPECPATH)

# 版本号取自已安装包（本机 dlv / CI 均先 pip install -e . 再打包，必然可得）
import importlib.metadata

VERSION = importlib.metadata.version("dataloadv")

# ---------------------------------------------------------------- 数据文件
# mne：通道模板/montage/默认配置等运行期数据（最小集，不含测试数据）
datas = []
datas += collect_data_files("mne")
# pynwb/hdmf：NWB 命名空间 schema JSON/yaml，缺了 NWB 读取在运行期才炸
datas += collect_data_files("pynwb")
datas += collect_data_files("hdmf")

# ---------------------------------------------------------------- 隐式导入
hiddenimports = [
    # 本项目：函数体内延迟 import，静态分析扫不到（坑 ①）
    "dataloadv.io.neo_reader",
    "dataloadv.io.nwb_reader",
]

# mne 1.x 用 lazy_loader 惰性加载子模块（mne.utils._logging 等运行期才 import），
# neo 的 rawio 后端按格式名动态分发——静态分析都扫不到。实测不收全时
# 冻结环境起不来：`import mne` → mne.set_log_level → No module named
# 'mne.utils._logging'（坑 ②，已踩）。collect_submodules 只收子模块"名字"
# （进 PYZ 的纯代码），不像 collect_all 连测试数据几百 MB 一起拖；
# mne.tests / mne.testing 是测试专用命名空间，运行期无用，显式剔除。
for _pkg in ("mne", "neo", "pynwb", "hdmf"):
    _mods = collect_submodules(_pkg)
    if _pkg == "mne":
        _mods = [
            m
            for m in _mods
            if not (m.startswith("mne.tests") or m.startswith("mne.testing"))
        ]
    hiddenimports += _mods

# ---------------------------------------------------------------- 分析
a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],  # 兜底：即使 editable 安装机制变化也能找到包
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],  # 第一轮全量，确保能跑；瘦身（M10-4）冒烟全过后再动
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir 模式：二进制留在目录里，不塞进 exe
    name="DataloadV",
    debug=False,
    bootloader_args=[],
    strip=False,
    upx=False,
    console=False,  # 桌面应用，双击不闪终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # 不签名（无 Apple 开发者账号，技术裁决已定）
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DataloadV",  # onedir 目录名（Windows 分发形态）；macOS 供 BUNDLE 取用
)

# ---------------------------------------------------------------- 平台分支
if sys.platform == "darwin":
    # macOS：COLLECT 目录（dist/DataloadV/）再封一层 .app bundle，
    # 双击即用；Info.plist 补高 DPI 与中文显示相关声明
    app = BUNDLE(
        coll,
        name="DataloadV.app",
        version=VERSION,
        bundle_identifier="com.jklove.dataloadv",
        info_plist={
            "CFBundleName": "DataloadV",
            "CFBundleDisplayName": "DataloadV",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundlePackageType": "APPL",
            "NSHighResolutionCapable": True,  # Retina 全分辨率渲染
            "NSAppleEventsUsageDescription": "应用本身不发送 Apple 事件，占位声明",
        },
    )
# win32：COLLECT 产物 dist/DataloadV/（内含 DataloadV.exe）即最终形态，
# 压 zip 后命名 DataloadV-{version}-win64.zip，无需额外分支
