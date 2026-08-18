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

## M3 预处理链 + 预览（✅ 2026-08-18 完成，验证见 review.md）

- [x] proc/context.py + proc/base.py（ProcStep ABC + STEP_REGISTRY + to/from_dict 序列化 + apply_pipeline）
- [x] 6 步骤：filters（bandpass/notch，notch 限 raw——mne Epochs 无 notch_filter）、referencing（reref）、resample、bads、epoching（raw→epochs 阶段翻转）
- [x] features/spectral.py mean_welch（M3 PSD 视图与 M4 特征共用）
- [x] tests/test_proc_m3.py 23 项全绿——**含真实 A01T 分段 = 288 验收**、陷波 50Hz 抑制 >10×、副本隔离
- [x] ui/widgets/pipeline_panel.py + params_form.py（pydantic 自动表单，6 步骤零 UI 代码）+ test_ui_m3 表单往返不变量
- [x] 预览：proc/preview.py 副本包装成浏览 tab；EpochsPreviewView 分段预览；psd_view.py 对比视图（原始 vs 处理后）
- [x] 浏览器坏道标记（右键 toggle_bad 灰显 + bads_changed）联动 BadChannelsStep 默认参数
- [x] e2e_m3 11 项 ALL OK：羊 50Hz 压制比 0.0001；A01T 分段 = 288（全 GUI 路径）
- [x] 收尾四件事：review.md → STATUS/TODO/HANDOFF → 上下文检测 → git commit

## M4 特征 + 导出（✅ 2026-08-18 完成，验证见 review.md）

> **特征范围决策（用户 2026-08-18 确认）：四层组合**——① 全量默认（文件级摘要/批处理基线）；
> ② epochs 逐段（每段一行长表，BCI 事件锁时分析）；③ proc 链加 `crop` 步骤实现显式任意时间窗
> （可序列化进 sidecar、批处理复用）；④ 特征入口"用当前显示窗口"按钮**预填**时间窗参数
> （不隐式绑定视口，保证可复现）。注意：预处理滤波类步骤仍全量做（边界效应/滤波器状态），
> crop 是裁剪数据范围而非按视口滤波。

- [x] proc/crop.py：时间窗裁剪步骤（tmin/tmax 秒，raw+epochs 皆可；raw 绝对时间/epochs 相对事件锚点；
      事件表不动——first_samp 机制保证绝对样本号仍成立，e2e 验证窗外事件自然丢弃）
- [x] features/base.py（FeatureExtractor ABC + FEATURE_REGISTRY，与 proc/base 同构；step_id 别名
      使 ParamsForm 零改动复用）+ 三提取器：BandPowerFeature（δθαβγ+自定义 频段:起-止、相对/对数，
      scipy welch 数组广播一次算全部段）/ WelchPsdFeature（曲线仅 raw 阶段）/ TimeDomainStatsFeature
      （8 统计量纯 numpy，过零带阈值滞回）
- [x] batch/results.py FeatureTable（长表 7 列 + 中文表头映射 + to_wide——**dropna=False** 否则文件级行
      整组丢失）+ ui/widgets/feature_table.py（UserRole 数值排序 + 三个导出按钮 + teardown）
- [x] 特征面板：管线面板特征区（与步骤区共用参数表单、互斥选择）+「用当前显示窗口」预填按钮
      （视口→最后一个 crop 步骤或新增；clamp 数据范围；可继续手改）
- [x] export/：features_io（CSV UTF-8 BOM 中文表头 + 曲线宽表按频率轴分组）+ epochs_io（HDF5
      /epochs/data|times|event_codes + attrs；FIF mne 无损）+ provenance.py（.pipeline.json：
      步骤+特征+文件清单+库版本）
- [x] 验证：pytest 122 绿（+50）；e2e_m4 18 项 ALL OK——CSV Excel 可开中文表头（录制,被试,段序号,
      事件码,通道,特征,数值）；HDF5 回读形状一致；FIF 回读 288 段；A01T 逐段 14400 行
      （288×25×2——mne 读 2a GDF 全 25 通道标 eeg，EOG 不自动排除，见 STATUS 实证结论 #2）
- [x] 收尾四件事：review.md → STATUS/TODO/HANDOFF → 上下文检测 → git commit

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
