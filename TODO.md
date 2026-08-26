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

## M5 批处理 + 扩展格式 + 收尾（✅ 2026-08-18 完成，v1 收官，验证见 review.md）

> **架构决策（与 plan.md 原文偏离，规则优先）**：plan 写 BatchEngine(QObject)，但硬性规则 #1 禁止
> batch 层 import Qt → 实现为**纯 Python 引擎**（回调在 worker 线程执行）+ UI 侧 queue.Queue +
> QTimer 150ms 事件泵转主线程——同时满足规则与"队列连接回主线程"的意图。
> Intan 同理弃 vendored read_intan.py（1000+ 行第三方代码），改用 neo.rawio.IntanRawIO。

- [x] batch/jobs.py：JobSpec/PipelineSpec（steps/features dict 列表 + resolved_* 启动前校验 + summary_zh）
      /FileStatus/FileResult（含逐文件日志）/BatchSummary（n_ok/n_failed/n_cancelled/n_values）
- [x] batch/engine.py：BatchEngine 纯 Python——ThreadPoolExecutor（默认 2）+ threading.Event 取消
      （逐步骤检查）+ 单文件失败不杀整批 + LoadedRawCache.pin 防多 worker 并发互逐 + 导出
      （CSV/H5 + sidecar extra.batch）；proc/base.py、features/base.py 加 cancel_check 参数
      （新 PipelineCancelled(StepError)）
- [x] UI：batch_view.py（逐文件进度表/失败红显/双击日志对话框）+ batch_dialog.py（两页选择↔运行，
      事件泵）+ settings_dialog.py（线程数/缓存 GB/导出目录）+ core/app_settings.py（原子写+热生效）
      + 主窗口接线（文件菜单设置、处理菜单批处理、批处理结果 tab）
- [x] io/neo_reader.py（_NeoRawReader 模板：structured array 头/选点数最多流/逐列单位换算/事件表）
      + Blackrock/OE/Intan 三读取器；io/nwb_reader.py（ElectricalSeries 双形状支持/trials→事件）
- [x] README 重写（v1 功能全览/快速开始/典型流程五步/验证口径；截图以 headless 条件改为文字流程）
- [x] 验证：pytest 137 绿（+15：batch 10 + readers 5——NWB pynwb 真实往返）；e2e_m5 19 项 ALL OK
      ——45 个 2b GDF（含 1 损坏）：45 成功 1 容错、78240 行 8.5s、UI 心跳 86 次全程响应、
      取消 4/41 有效、失败行日志可查、CSV/sidecar 一致；e2e_m1-m4 + smoke 回归全绿
- [x] 收尾四件事：review.md → STATUS/TODO/HANDOFF → 上下文检测 → git commit

## M6 浏览体验优化（✅ 2026-08-18 完成，用户实测 v1 三点反馈，验证见 review.md）

> **两项用户决策**：滚轮=平移（缩放交给时长选项/右键框选/Ctrl+滚轮微调）；全局换白底（不加主题开关）。

- [x] 通道标签重构：删 y 轴 setTicks（挤叠+"…"截断源头）→ 每通道 TextItem 内嵌曲线行左端
      （半透明白底、随视口/间距/显隐联动）；左轴隐藏；y 轴锁定 setMouseEnabled(x=True, y=False)
- [x] 滚轮/键盘：_PanViewBox 重载 wheelEvent（竖滚=平移 10% 一屏、Ctrl+滚轮=鼠标锚点 ×1.25 缩放）；
      键盘 ←/→ 翻屏、Home/End 首末屏、↑/↓ 增益 ±1（StrongFocus + _gfx 焦点代理）
- [x] 窗口导航：|◀ 最前 / ◀ 上一屏 / 一屏时长下拉（1/2/5/10/30/60 s + 可编辑）/ 下一屏 ▶ / 最末 ▶|；
      翻屏 0.9 屏；_set_x_range 统一 clamp [0,dur]；时长变更保持视口中心；视口宽度回写时长框
- [x] 幅值标尺：右上角 60px 竖线 + µV 标注（像素长度÷增益→真实幅度→_nice_number 1/2/5×10^k），
      随增益/视口动态更新
- [x] 浅色主题：pg.setConfigOptions(background="w")；波形 #1f77b4 / PSD #d62728,#1f77b4,#2ca02c,#9467bd
      / 事件黄→#b8860b / 图例 #333333 / batch 状态色加深；坏道灰与网格保留
- [x] 存量增益双 bug 修复：①乘间距不乘波形 → out_v*gain + idx*spacing；②_gain 初值 1.0（滑杆值！）
      → 首帧隐形 1.26× → 0.0
- [x] 验证：pytest 150 绿（+13 test_ui_browser_m6）；e2e_m1 扩 18 项 ALL OK（+5 M6 断言）；
      e2e_m3 + smoke 回归全绿
- [x] 收尾四件事：STATUS/TODO/HANDOFF/MANUAL/README → review.md → 上下文检测 → git commit

## M6.5 读取派发魔数校验（✅ 2026-08-24 完成，用户发现羊数据实为 BDF 驱动，验证见 review.md）

> sheep/sheep2/sheep3 共 6 个 .edf 内容全是 BDF（\xffBIOSEMI 头）——此前按 EDF 解码
> 24-bit 样本读成 16-bit，**时长虚增 1.5×、数值全部错位**（数据正确性 bug）。

- [x] 核实：6 文件魔数普查 + 对照解码（45000→67500 样本实锤 1.5×）；data/ 其余数据集无不符
- [x] io/registry.py `_dispatch_readers`：魔数内容优先派发（EDF/BDF/GDF/BrainVision 唯一定位
      时以内容为准，扩展名不符 warning、**不给扩展名候选兜底**；hdf5 家族签名不参与）
- [x] io/mne_readers.py：`_read_mne_robust` 通用助手（mne `_check_args` 扩展名硬拒绝 →
      **file-like 对象重读公共入口**绕过——用户指定方案（read_raw_bdf 自 MNE 1.10 支持
      file-like，edf/gdf 同路径），不直接实例化 Raw* 构造器；读后 `_detach_file_handles`
      剥离 mne 内部两处句柄残留（否则 raw.copy()/deepcopy 炸，e2e_m3 实测）；latin1 回退保留）；
      模板基类 `_robust` 声明
- [x] io/sniffing.py：修 EDF 分支 off-by-one（版本域 = 字节 0–7，旧查 head[1:9] 漏判真 EDF）；
      删无引用且语义错误的 `is_edf`
- [x] core/workspace.py：`add_metas` 重复导入刷新 meta（rec_id 稳定）——用户重导入羊文件夹
      一次即修正旧条目（EDF/270s → BDF/真实时长）
- [x] 用户问题①核查：6 个羊 BDF 标注通道逐字节验证——全为纯 ASCII TAL 空注释
      （`+N\x14\x14\x00`），满足 UTF-8、零事件是数据属性——"羊需要 latin1"系 M1 误解码
      副产品，无需改码（latin1 机制保留给真 latin1 文件）
- [x] 验证：pytest 157 绿（羊断言重写 format=BDF+真实时长；+魔数表/反向误标/不兜底/latin1 回归/
      重导入刷新/组合回退/file-like raw 可 copy）；e2e_m1 19 项 ALL OK（+羊按 BDF 解码断言）；
      e2e_m2–m5 + smoke 回归全绿
- [x] 收尾四件事：DATA_NOTES（羊三目录 BDF 实锤+真实时长表）→ STATUS/TODO/HANDOFF →
      review.md → 上下文检测 → git commit（用户指令后）

## M6.6 工作区移除条目 + 羊通道质量定论（✅ 2026-08-24 完成，用户两问驱动，验证见 review.md）

> ①"数据读出来都是噪声"→ 诊断定论（零代码改动，结论入 DATA_NOTES）；②"能否从工作区删除
> 导入的数据"→ 功能落地（树右键/Del 移除，只清索引不删磁盘文件）。

- [x] 问题①诊断：羊 CH5–CH8 逐样本 `np.array_equal` 全 True = 开路通道复用（饱和/死值伪迹）；
      CH4 部分饱和；CH1–CH3 真实皮层信号（去直流+带通后 std≈279µV）带大直流偏移；
      换算 0.125µV/LSB 与手算一致——读取与换算链均正确，"噪声感"是数据本身属性
- [x] 问题②功能：workspace_tree.py `remove_requested(list)` 信号 + 右键菜单 + `_TreeWithDel`
      内层树接管 Del/Backspace（焦点在树上，容器收不到 keyPress）；`_paths_for_item` 分类
      （录制项单 path / 来源节点整组 / 根不参与）
- [x] 主窗口 `_remove_from_workspace`：多条先 QMessageBox 确认 → remove_recording + save +
      notify 刷新；**只清工作区索引，磁盘数据文件不动**；已开浏览 tab 保留
- [x] 验证：pytest 163 绿（+6 test_ui_workspace_remove——树载荷 3 + 主窗口端到端 3，
      MainWindow 级测试须 offscreen）；e2e_m1 19 项 + smoke 回归
- [x] 收尾四件事：DATA_NOTES/STATUS/TODO/HANDOFF/MANUAL/README → review.md → 上下文检测 →
      git commit（用户指令后）

## 已知问题 / Backlog（v1 收官后暂缓项）

- .edf.event WFDB 边车解析：M1 实测 PhysioNet EDF 内嵌注释已完整，边车为冗余副本，暂不需要；若未来遇到只有边车、无内嵌注释的数据集再补
- **ds3 分段 MEG 读取**（data/dataset 里的 S1/S2.mat，BCI-IV 数据集 3）：数据是分段结构（非连续），与当前连续 raw 模型不匹配；M2 已识别并明确拒绝（提示记入 backlog）。若未来分段数据需求明确再实现
- **CNT/EGI/BrainVision/EEGLAB 无真实数据实测**：M2 只有模板基类 + FIF 合成往返测试保证；拿到真实文件后跑 `open_file()` 冒烟即可（读取器走同一模板路径，风险低）。BDF 已于 M6.5 用真实羊数据实测（6 个 .edf 误标文件，含标注通道逐字节核查）
- **Blackrock/Open Ephys/Intan/NWB 无真实数据实测**（M5）：neo 系用桩 rawio 验证模板关键逻辑（换算/转置/选流/事件）、NWB 用 pynwb 完整写支持做真实往返；拿到真实文件后跑 `open_file()` 冒烟即可（neo 模板路径统一，风险低）
- eeglabio / pybv 装入 dev 依赖做 EEGLAB/BrainVision 合成往返：v1 收官时评估——neo/pynwb 已覆盖 M5 验收，暂缓，等真实数据再决定
- 2b GDF 头自带 highpass 100 > lowpass 0.5 触发 mne RuntimeWarning（每文件两条，无害）；如需清净可在读取器预处理 info（暂缓——不改数据语义，仅日志噪音）
- **epochs_preview 仍用 y 轴 setTicks 标通道名**（M6 只重构了信号浏览器）：分段预览通道数通常 ≤25 且图形静态、无滚轮 y 缩放路径，实际不会触发重叠；若未来分段通道很多再改行内嵌标签
- **白底对比度人工目检**：M6 换色均按白底可辨原则挑选并有测试覆盖存在性，但整体观感（如网格浓度、事件色区分度）未做截图级人工评审——用户日常使用中如有个别颜色不顺眼，改 strings_zh/各控件色值即可（均为一处常量）
