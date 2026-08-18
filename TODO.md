# TODO — 待办清单

> 本文件回答"接下来做什么"。随进展勾选与增删。完成项移入 STATUS.md 变更记录。

## M0 收尾（✅ 2026-08-18 完成，验证见 review.md）

- [x] conda 依赖安装完成，版本回填 STATUS.md 与 HANDOFF.md
- [x] pyproject.toml + src/dataloadv 包骨架
- [x] MainWindow：dock 布局 + 中文菜单 + 日志面板
- [x] workers/generic.py（run_in_thread）+ core/logging_setup.py
- [x] ui/strings_zh.py 中文标签模块
- [x] 验证：GUI 冒烟 SMOKE OK；pytest 3 passed
- [x] 治理收尾四件事：review.md → STATUS/TODO/HANDOFF → 上下文检查 → git commit

## M1 工作区 + EDF + 信号浏览器（✅ 2026-08-18 完成，验证见 review.md）

- [x] core/recording.py：RecordingMeta / EventTable / Recording / LoadPolicy / LoadedRawCache
- [x] core/workspace.py：Workspace + JSON 持久化（~/.dataloadv/）
- [x] io/base.py + io/registry.py + io/sniffing.py：读取器 ABC + 注册表 + 魔数嗅探
- [x] io/mne_readers.py 的 EdfReader（latin1 回退；.edf.event 边车解析经实测取消——EDF 内嵌注释已完整）
- [x] ui/dialogs/import_dialog.py：导入文件/文件夹（扫描 worker + 错误表）
- [x] ui/widgets/workspace_tree.py 工作区树 + meta_table.py 元数据表
- [x] ui/widgets/signal_browser.py 信号浏览器（窗口化读取 + 峰值抽取包络绘制）+ event_lane.py 事件条
- [x] tests：conftest synthetic_raw + EDF 读取测试（real 标记用 data/sheep）
- [x] 验证：导入 sheep 3 文件 + PhysioNet S001 → E2E 13 项全过（scripts/e2e_m1.py ALL OK）

## M2 读取器全覆盖（✅ 2026-08-18 完成，验证见 review.md）

- [x] mne_readers.py 重写为 `_MneRawReader` 模板基类家族：EDF(latin1)/BDF/GDF/BrainVision/FIF/EEGLAB/CNT/EGI
- [x] io/bciciv_mat.py：ds1（头只 loadmat nfo/mrk；eval 无 mrk 明确 note）+ ds4（纯 whosmat 头、跳过 test_data、fs=1000 官方）+ 通用 mat 拒绝猜测
- [x] io/event_maps.py：GDF 事件码→中文标签（官方 desc_2a/2b.pdf 原文核实的 16 码，非搜索摘要）
- [x] io/table.py CSV/TXT（分隔符嗅探+数值性验证+FsStore 询问记忆）+ io/hdf5.py（零数据 IO 定位）+ core/fs_store.py
- [x] 验证：4.9GB 扫描 5.2s <2min ✅；六格式打开绘图 ✅；ds4 加载 0.2s <10s ✅；pytest 43 绿；e2e_m2 17 项 ALL OK
- [x] 收尾四件事：review.md → STATUS/TODO/HANDOFF → 上下文检查 → git commit

## M3 预处理链 + 预览（下一个里程碑）

- [ ] proc/context.py + proc/base.py + 6 步骤（bandpass/notch/reref/resample/bads/epoching）
- [ ] ui/widgets/pipeline_panel.py + params_form.py（pydantic 自动表单）
- [ ] 当前文件预览（处理副本 tab + 步骤日志）+ psd_view.py
- [ ] 浏览器坏道标记联动 BadChannelsStep
- [ ] 验证：羊文件滤波后 50Hz 消失；2a GDF 分段数 = 288（A01T）

## M4 特征 + 导出

- [ ] features/ 三个提取器（Welch PSD / 频带功率 / 时域统计）
- [ ] batch/results.py FeatureTable + ui/widgets/feature_table.py
- [ ] export/：features_io（CSV BOM / HDF5）+ epochs_io（HDF5/FIF）+ provenance JSON sidecar
- [ ] 验证：CSV Excel 可开中文表头；HDF5 回读形状一致

## M5 批处理 + 扩展格式 + 收尾

- [ ] batch/engine.py（2 线程池/取消/逐文件日志）+ ui/widgets/batch_view.py
- [ ] neo_reader.py（Blackrock/Open Ephys）+ nwb_reader.py + intan.py（vendored）
- [ ] 设置对话框（线程数/内存预算/默认导出目录）+ README 截图
- [ ] 验证：45 个 2b GDF 批处理全程 UI 响应、可取消、错误可查

## 已知问题 / Backlog（暂缓项）

- .edf.event WFDB 边车解析：M1 实测 PhysioNet EDF 内嵌注释已完整，边车为冗余副本，暂不需要；若未来遇到只有边车、无内嵌注释的数据集再补
- **ds3 分段 MEG 读取**（data/dataset 里的 S1/S2.mat，BCI-IV 数据集 3）：数据是分段结构（非连续），与当前连续 raw 模型不匹配；M2 已识别并明确拒绝（提示记入 backlog）。若 M3 分段模型落地后需求明确再实现
- **BDF/CNT/EGI/BrainVision/EEGLAB 无真实数据实测**：M2 只有模板基类 + FIF 合成往返测试保证；拿到真实文件后跑 `open_file()` 冒烟即可（读取器走同一模板路径，风险低）
- eeglabio / pybv 装入 dev 依赖：可对 EEGLAB/BrainVision 做合成写出→读回往返测试（暂缓，等真实数据或 M5 收尾时决定）
