# STATUS — 项目状态快照

> 本文件回答"现在做到哪了"。每里程碑完成及重要提交后更新。最后更新：2026-08-18（M2 完成）

## 当前里程碑

- **M2 读取器全覆盖：✅ 完成（2026-08-18）**，验证全过（pytest 43 绿 + E2E 17 项 + dataset 扫描 5.9s，见 review.md）
- **下一个：M3 预处理链+预览**（任务拆解见 TODO.md）

## 里程碑总览

| 里程碑 | 状态 | 完成日期 | 说明 |
|---|---|---|---|
| M0 骨架+治理 | ✅ 完成 | 2026-08-18 | git 仓库、治理文件、conda env dlv、包骨架、主窗口、冒烟通过 |
| M1 工作区+EDF+信号浏览器 | ✅ 完成 | 2026-08-18 | Recording/Workspace/EdfReader(latin1)/导入/工作区树/元数据表/信号浏览器/事件条；E2E 全过 |
| M2 读取器全覆盖 | ✅ 完成 | 2026-08-18 | 8 格式 mne 模板家族 + ds1/ds4 mat + CSV/TXT + HDF5 + GDF 官方码表中文标签；4.9GB 扫描 5.9s/1606 条 |
| M3 预处理链+预览 | ⬜ 未开始 | — | 6 个处理步骤、管线面板、预览、PSD |
| M4 特征+导出 | ⬜ 未开始 | — | 3 个特征提取器、导出、JSON sidecar |
| M5 批处理引擎+扩展格式 | ⬜ 未开始 | — | BatchEngine、neo/pynwb/Intan、设置、README |

## 环境

- conda env：`dlv`（Python 3.10），安装命令见 HANDOFF.md §环境搭建
- 关键包版本：numpy 1.26.4 / scipy 1.15.2 / pandas 2.3.3 / h5py 3.16.0 / pydantic 2.13.4 / PySide6 6.11.0 / pyqtgraph 0.14.0 / mne 1.12.0（pip）/ edfio 0.4.16（pip）

## 测试

- `pytest`：**43 passed**（M2 新增 26：ds1/ds4/拒绝猜测/CSV/HDF5/GDF 标签/FIF 往返/嗅探；含 3 个真实羊文件 latin1 + 2 个真实 GDF 测试）
- `python scripts/e2e_m1.py`：**ALL OK（13 项）**——sheep + S001 真实导入 → 浏览 → 释放（幂等总量断言）
- `python scripts/e2e_m2.py`：**ALL OK（17 项）**——4.9GB dataset 扫描 5.2s / 识别 1606 条 / 3 条已知结构报错 / 六格式（EDF/GDF 2a/GDF 2b/ds1/ds4/CSV）逐个打开均有真实曲线 / GDF 中文标签 / 六 tab 关闭释放
- `python scripts/smoke_gui.py`：SMOKE OK

## M2 关键实证结论（写代码前实测，避免踩坑）

1. **GDF 事件码表以官方 desc_2a.pdf / desc_2b.pdf 原文为准**（pypdf 提取）——搜索摘要多处错误（781 实为 "BCI feedback (continuous)"，1077–1081 是眼动伪迹标记）
2. **ds1 评估集（BCICIV_eval_ds1*）实际不含 mrk 变量**——pipelineMotor yaml 所说"评估集有提示"与实物不符；读取时明确 note 而非猜标签
3. **ds4 train_data 是 double、文件内无采样率**——fs=1000Hz 来自官方 desc_4.pdf；读取时跳过 test_data（~100MB）
4. **2b 文件名是 B0303T 三段式**（被试+场次+T/E），原正则不覆盖，已加模式
5. 数据集里混有 **ds3 分段 MEG（S1/S2.mat）与 SHA256SUMS.txt**——识别后明确拒绝（ds3 已记 backlog），txt 数值性验证挡住校验文件

## 最近变更记录（新条目加在最上面）

- 2026-08-18（M2 完成）：io/mne_readers.py 重写为 `_MneRawReader` 模板基类家族（8 格式，`_read_fn` 必须 staticmethod）；io/event_maps.py（GDF 官方码表 16 码中文标签）；io/bciciv_mat.py（ds1 头只 loadmat nfo/mrk、ds4 纯 whosmat、未知 mat 拒绝猜测）；io/table.py（分隔符嗅探+数值性验证+FS_UNSET_NOTE）+ io/hdf5.py（零数据 IO 定位信号集）；core/fs_store.py（CSV/HDF5 采样率询问记忆）；主窗口采样率询问对话框；**workers/generic.py 加 `_MainRelay`**（修 worker 线程回调弹窗冻结——M2 最关键产品修复）；嗅探补 GDF/BDF/HDF5/BrainVision 魔数；e2e_m2.py（17 项）。
- 2026-08-18（M1 完成）：core/recording.py（Recording/EventTable/LRU 缓存，修锁内逐出死锁）+ core/workspace.py（JSON 原子持久化）；io 层（BaseReader ABC/注册表/scan_folder 进度回调/EDF latin1 回退）；UI（导入控制器+错误表/工作区树/元数据表/信号浏览器窗口化+峰值包络/事件条+跳转导航）；修 3 个实测坑（PySide worker GC、PlotItem 构造期无 scene、load_raw 收 str path）；E2E 脚本幂等化。
- 2026-08-18（M0 完成）：conda env dlv、包骨架、主窗口、治理文件、首次 commit。
- 2026-08-18（启动）：方案批准、git 初始化。
