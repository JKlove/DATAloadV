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

## M1 工作区 + EDF + 信号浏览器（下一个，进行中）

- [ ] core/recording.py：RecordingMeta / EventTable / Recording / LoadPolicy / LoadedRawCache
- [ ] core/workspace.py：Workspace + JSON 持久化（~/.dataloadv/）
- [ ] io/base.py + io/registry.py + io/sniffing.py：读取器 ABC + 注册表 + 魔数嗅探
- [ ] io/mne_readers.py 的 EdfReader（latin1 回退 + .edf.event 边车解析）
- [ ] ui/dialogs/import_dialog.py：导入文件/文件夹（扫描 worker + 错误表）
- [ ] ui/widgets/workspace_tree.py 工作区树 + meta_table.py 元数据表
- [ ] ui/widgets/signal_browser.py 信号浏览器（窗口化读取 + 峰值抽取包络绘制）+ event_lane.py 事件条
- [ ] tests：conftest synthetic_raw + EDF 读取测试（real 标记用 data/sheep）
- [ ] 验证：导入 sheep 3 文件 + PhysioNet S001，浏览/缩放/跳转事件流畅

## M2 读取器全覆盖

- [ ] mne_readers.py 补全：BDF/GDF/BrainVision/FIF/EEGLAB/CNT/EGI
- [ ] io/bciciv_mat.py：ds1（cnt/mrk/nfo）+ ds4（train_data/train_dg→glove misc 通道）+ 通用 mat 拒绝猜测
- [ ] io/event_maps.py：GDF 事件码→中文标签映射（769-772/783/1023/32766）
- [ ] io/table.py CSV/TXT + io/hdf5.py 通用 HDF5
- [ ] 验证：4.9GB dataset 全量扫描 <2min；每格式开一个能绘图；ds4 mat <10s

## M3 预处理链 + 预览

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

- （暂无）
