# STATUS — 项目状态快照

> 本文件回答"现在做到哪了"。每里程碑完成及重要提交后更新。最后更新：2026-08-18（M0 完成）

## 当前里程碑

- **M0 骨架+治理：✅ 完成（2026-08-18）**，验证全过（见 review.md）
- **下一个：M1 工作区 + EDF 读取 + 信号浏览器**（任务拆解见 TODO.md）

## 里程碑总览

| 里程碑 | 状态 | 完成日期 | 说明 |
|---|---|---|---|
| M0 骨架+治理 | ✅ 完成 | 2026-08-18 | git 仓库、治理文件、conda env dlv、包骨架、主窗口（dock+中文菜单+日志面板）、3 个单测 + GUI 冒烟通过 |
| M1 工作区+EDF+信号浏览器 | ⬜ 未开始 | — | Recording 模型、Workspace、EdfReader、信号浏览器、事件条 |
| M2 读取器全覆盖 | ⬜ 未开始 | — | 全部 MNE 原生格式 + BCI-IV mat + CSV/TXT/HDF5 |
| M3 预处理链+预览 | ⬜ 未开始 | — | 6 个处理步骤、管线面板、预览、PSD |
| M4 特征+导出 | ⬜ 未开始 | — | 3 个特征提取器、导出、JSON sidecar |
| M5 批处理引擎+扩展格式 | ⬜ 未开始 | — | BatchEngine、neo/pynwb/Intan、设置、README |

## 环境

- conda env：`dlv`（Python 3.10.x），安装命令见 HANDOFF.md §环境搭建
- 关键包版本（conda-forge 为主，mne/edfio 走 pip）：

| 包 | 版本 | 来源 |
|---|---|---|
| Python | 3.10（conda env） | conda |
| numpy | 1.26.4 | conda-forge |
| scipy | 1.15.2 | conda-forge |
| pandas | 2.3.3 | conda-forge |
| h5py | 3.16.0 | conda-forge |
| pydantic | 2.13.4 | conda-forge |
| PySide6 | 6.11.0 | conda-forge |
| pyqtgraph | 0.14.0 | conda-forge |
| mne | 1.12.0 | pip |
| edfio | 0.4.16 | pip |
| pytest / pytest-qt | 8.x / 4.5.0 | conda-forge |

## 测试

- `pytest`：**3 passed**（tests/test_app_smoke.py：包版本/日志幂等/合成数据夹具）
- `python scripts/smoke_gui.py`：**SMOKE OK**（主窗口真实启动自检）
- 真实数据测试（`-m real`）：M1 起建立

## 最近变更记录（新条目加在最上面）

- 2026-08-18（M0 完成）：conda env dlv 建立并装齐依赖；pyproject + src 骨架（app/入口、core/logging_setup、workers/generic、ui/main_window+strings_zh+log_panel）；治理文件体系建立；pytest 3 绿 + GUI 冒烟通过；首次 git commit。
- 2026-08-18（启动）：方案批准（plan.md）、git 仓库初始化、治理文件建立。
