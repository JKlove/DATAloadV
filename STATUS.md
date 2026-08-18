# STATUS — 项目状态快照

> 本文件回答"现在做到哪了"。每里程碑完成及重要提交后更新。最后更新：2026-08-18（M1 完成）

## 当前里程碑

- **M1 工作区+EDF+信号浏览器：✅ 完成（2026-08-18）**，验证全过（pytest 17 绿 + E2E 13 项全过，见 review.md）
- **下一个：M2 读取器全覆盖**（任务拆解见 TODO.md）

## 里程碑总览

| 里程碑 | 状态 | 完成日期 | 说明 |
|---|---|---|---|
| M0 骨架+治理 | ✅ 完成 | 2026-08-18 | git 仓库、治理文件、conda env dlv、包骨架、主窗口、冒烟通过 |
| M1 工作区+EDF+信号浏览器 | ✅ 完成 | 2026-08-18 | Recording/Workspace/EdfReader(latin1)/导入/工作区树/元数据表/信号浏览器/事件条；E2E 全过 |
| M2 读取器全覆盖 | ⬜ 未开始 | — | 全部 MNE 原生格式 + BCI-IV mat + CSV/TXT/HDF5 + GDF 事件映射 |
| M3 预处理链+预览 | ⬜ 未开始 | — | 6 个处理步骤、管线面板、预览、PSD |
| M4 特征+导出 | ⬜ 未开始 | — | 3 个特征提取器、导出、JSON sidecar |
| M5 批处理引擎+扩展格式 | ⬜ 未开始 | — | BatchEngine、neo/pynwb/Intan、设置、README |

## 环境

- conda env：`dlv`（Python 3.10），安装命令见 HANDOFF.md §环境搭建
- 关键包版本：numpy 1.26.4 / scipy 1.15.2 / pandas 2.3.3 / h5py 3.16.0 / pydantic 2.13.4 / PySide6 6.11.0 / pyqtgraph 0.14.0 / mne 1.12.0（pip）/ edfio 0.4.16（pip）

## 测试

- `pytest`：**17 passed**（EDF 读取器含 3 个真实羊文件 latin1 测试 + 工作区/缓存/事件表逻辑）
- `python scripts/e2e_m1.py`：**ALL OK（13 项）**——sheep 3 文件 + S001 14 文件真实导入 → 浏览 → 波形/事件渲染 → 释放
- `python scripts/smoke_gui.py`：SMOKE OK

## M1 关键实证结论（写代码前实测，避免踩坑）

1. PhysioNet EDF **内嵌注释完整**（S001R03: T0×15/T1×8/T2×7），.event 边车冗余 → 已从计划中删除边车解析
2. S001 每被试 **14 个 run**（R01–R14），共 109 被试（e2e 断言据此修正）
3. 羊 EDF latin1 回退在 mne 1.12 下实测有效（3 个文件全过）

## 最近变更记录（新条目加在最上面）

- 2026-08-18（M1 完成）：core/recording.py（Recording/EventTable/LRU 缓存，修锁内逐出死锁）+ core/workspace.py（JSON 原子持久化）；io 层（BaseReader ABC/注册表/scan_folder 进度回调/EDF latin1 回退）；UI（导入控制器+错误表/工作区树/元数据表/信号浏览器窗口化+峰值包络/事件条+跳转导航）；修 3 个实测坑（PySide worker GC、PlotItem 构造期无 scene、load_raw 收 str path）；E2E 脚本幂等化。
- 2026-08-18（M0 完成）：conda env dlv、包骨架、主窗口、治理文件、首次 commit。
- 2026-08-18（启动）：方案批准、git 初始化。
