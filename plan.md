# DataloadV — 电生理数据平台开发计划

> 本文件是项目的正式开发计划（2026-08-18 与使用者讨论批准）。重大方案变更时更新本文件并在 review.md 记录变更原因。
> 接手开发请先读：`plan.md`（本文件，总体方案）→ `STATUS.md`（现在做到哪了）→ `TODO.md`（接下来做什么）→ `HANDOFF.md`（怎么搭环境、怎么跑）。

## 1. 背景与目标

用户在介入式 BCI 研究中需要处理大量电生理数据（羊实验 EDF、BCI Competition IV GDF/MAT、PhysioNet EDF），现有工作流依赖脚本（../pipelineMotor），缺少可视化交互工具。本项目的目标：在 `/Users/huyingbing/VSproject/intervention BCI/DataloadV/` 构建一个**独立桌面应用**，提供数据读取/管理 → 波形浏览 → 预处理 → 简单特征提取 → 批量处理 → 结果导出的完整 GUI 工作流，每个环节对应独立功能窗口/面板，支持单文件与批量操作。

**已确认的决策**（与用户讨论确定）：

| 项 | 决策 |
|---|---|
| 技术栈 | PySide6 桌面应用 + pyqtgraph 信号可视化 |
| 数据格式 | 全覆盖：MNE 原生格式 + BCI-IV .mat + NWB/Intan/Open Ephys/Blackrock（neo/pynwb）+ CSV/TXT/HDF5/通用 .mat |
| 功能范围 | 基础版：数据管理、波形浏览、预处理链、简单特征、批处理、导出 |
| 定位 | 独立工具，标准格式导出（CSV/HDF5/FIF + JSON 管线记录），与 pipelineMotor 格式互通但零代码耦合 |
| UI 语言 | 界面中文，代码标识符英文 |
| 工程治理 | 本地 git 仓库；plan/review/STATUS/TODO/HANDOFF 治理文件随开发实时更新；conda 优先装包；代码中文注释详尽 |

**现状**：DataloadV 目前只有 `data/`（dataset 4.9GB / sheep / sheep2 / clinicaldata 空），零代码。参考项目 `../pipelineMotor/`（src-layout、pyproject、conda env `py310lg`: Python 3.10.20 + mne 1.12.0）。**已验证的事实**：羊 EDF 注释通道含非 UTF-8 字节需 latin1 回退（pipelineMotor `src/motor_bci/data/adapters/formats.py:286` 已踩坑）；BCI-IV .mat 结构解析参考 `pipelineMotor/src/motor_bci/data/mat_loader.py`（重新实现，不导入其代码）。

## 2. 环境与工程骨架

- **专用 conda 环境 `dlv`**（Python 3.10，不碰已验证的 `py310lg`——避免 PySide6/neo/pynwb 破坏研究环境）
- **安装策略（用户要求）：conda 优先**——能从 conda-forge 装的都用 conda 装；conda 装不到或版本不合适的（如 MNE 及个别包）用 pip 补装。实际安装命令逐条记录进 HANDOFF.md，保证环境可复现
- 包名 `dataloadv`，hatchling + src-layout（与 pipelineMotor 惯例一致），入口 `dataloadv` 命令 + `python -m dataloadv`
- 核心依赖：numpy / scipy / pandas / mne 1.12.0 / edfio / pydantic v2 / h5py / PySide6 ≥6.5 / pyqtgraph ≥0.13.7 /（M5）neo / pynwb / vendored Intan reader；dev: pytest, pytest-qt
- `data/` 全程只读；应用配置写 `~/.dataloadv/`，导出由用户选择目录

### 项目治理规则

**本地 git 仓库**：`.gitignore` 排除 `data/`（4.9GB 数据不入库）、`__pycache__`、`.DS_Store`、`*.pyc`、构建产物；每个里程碑完成并通过验证后提交一次 commit，消息注明里程碑编号与内容。仓库级身份 `DataloadV Dev <dev@dataloadv.local>`（仿 pipelineMotor 惯例，不动全局配置）。

**六个治理文件**（项目根目录，随开发实时更新，任何人凭它们即可接手）：

| 文件 | 内容与更新节奏 |
|---|---|
| `plan.md` | 本开发计划，含架构决策与里程碑；重大方案变更时更新 |
| `review.md` | 开发审核记录：每个里程碑的验证执行情况、测试结果、发现的问题与修正；每里程碑验证后追加一节 |
| `STATUS.md` | 当前状态快照：已完成/进行中的里程碑、测试通过数、环境信息、最后更新时间；每里程碑及重要提交后更新 |
| `TODO.md` | 待办清单：下一里程碑任务拆解、已知问题、暂缓项（backlog）；随进展勾选与增删 |
| `HANDOFF.md` | 接手指南：如何搭环境（全部安装命令）、如何运行/测试、架构导览、关键设计决策及其原因、代码风格约定、坑与注意事项；每里程碑更新 |
| `README.md` | 项目简介、快速上手、截图（M5 补充） |

**注释规范（用户要求）**：所有模块/类/函数写中文 docstring（说明用途、参数、返回、异常）；关键算法逻辑（峰值抽取、事件映射、latin1 回退、LRU 逐出等）处写中文行内注释解释"为什么"；非显而易见的数据结构字段逐一说明。目标是用户本人或任何接手者不读实现也能理解和使用。

**上下文管理（用户要求，2026-08-18 更新）**：上下文检测在**每个里程碑的中间检查点（每完成 1–2 个子任务/模块）和收尾时都要做**；一旦**接近或超过 70%**：先把关键状态写入治理文件（本就应实时写入），随即主动提示并执行压缩。配套原则：**一切关键状态以治理文件为准、不依赖对话记忆**——进行中的任务进度、待办、已做决策、环境变更、发现的坑，实时（而非仅里程碑末）反映在 STATUS/TODO/HANDOFF 中，保证任何时刻发生上下文压缩或换人接手，凭文件即可无损继续开发。

**硬性架构规则**：
1. `core/ io/ proc/ features/ batch/ export/` 不得 import PySide6/pyqtgraph（计算层与 UI 层彻底分离，UI 可替换）
2. UI 绝不直接做计算，一律经 `workers/` 或 `batch/` 线程 + 信号回调（界面永不卡死）
3. 跨线程只传纯 Python/mne 对象，不传 Qt 控件
4. 上下文检测双检查点：里程碑**中途**（每 1–2 个子任务）与**收尾**各查一次，接近/超过 70% 先落盘治理文件再压缩；5. 里程碑收尾必须"更新治理文件 → review.md 记录验证 → 上下文检测 → git commit"四件事齐做才算完成

## 3. 包结构

```
DataloadV/
├── .git/                             # 本地 git 仓库
├── .gitignore                        # 排除 data/、__pycache__、.DS_Store、构建产物
├── pyproject.toml / README.md
├── plan.md / review.md / STATUS.md / TODO.md / HANDOFF.md   # 治理文件
├── src/dataloadv/
│   ├── app.py / __main__.py          # QApplication 入口、excepthook→日志
│   ├── core/                         # 禁止 import Qt
│   │   ├── recording.py              # RecordingMeta(pydantic), EventTable, Recording, LoadPolicy, LoadedRawCache(LRU)
│   │   └── workspace.py              # Workspace + JSON 持久化 (~/.dataloadv/)
│   ├── io/                           # 读取器层，禁止 import Qt
│   │   ├── base.py                   # BaseReader ABC: read_meta(仅头)/open/sniff
│   │   ├── registry.py               # @register_reader 字典注册表 + open_file() + scan_folder()
│   │   ├── sniffing.py               # 魔数嗅探 (EDF/GDF/FIF/HDF5/NWB/BV)
│   │   ├── mne_readers.py            # EDF(latin1回退+.edf.event边车)/BDF/GDF/BrainVision/FIF/EEGLAB/CNT/EGI
│   │   ├── bciciv_mat.py             # BCI-IV ds1(cnt/mrk/nfo) + ds4(train_data/train_dg→glove为misc通道) + 通用mat(拒绝猜测)
│   │   ├── event_maps.py             # GDF 事件码映射(769-772/783/1023/32766)→中文标签
│   │   ├── table.py / hdf5.py        # CSV/TXT(分隔符嗅探+fs询问持久化)、HDF5
│   │   ├── neo_reader.py / nwb_reader.py / intan.py   # M5, import-guarded 可选依赖
│   │   └── third_party/intan/        # vendored read_intan.py
│   ├── proc/                         # 处理步骤，禁止 import Qt
│   │   ├── context.py                # ProcessingContext(stage: raw|epochs, history)
│   │   ├── base.py                   # ProcStep ABC + STEP_REGISTRY + to_dict/from_dict
│   │   ├── filters.py                # BandPassStep 带通 / NotchStep 陷波
│   │   ├── referencing.py            # RerefStep 重参考(平均/自定义)
│   │   ├── resample.py               # ResampleStep 降采样
│   │   ├── bads.py                   # BadChannelsStep 坏导联(标记/插值)
│   │   └── epoching.py               # EpochingStep 事件分段(tmin/tmax/baseline/reject)
│   ├── features/                     # 特征提取，禁止 import Qt
│   │   ├── base.py                   # FeatureExtractor ABC + registry
│   │   ├── spectral.py               # WelchPsdFeature / BandPowerFeature(δθαβγ+自定义, 相对/对数)
│   │   └── timedomain.py             # TimeDomainStatsFeature(rms/var/mav/zc/ptp/iqr/kurt/skew)
│   ├── batch/
│   │   ├── jobs.py                   # JobSpec/PipelineSpec/FileResult/BatchSummary (pydantic)
│   │   ├── engine.py                 # BatchEngine(QObject) + 2线程池 + 取消 + 逐文件日志捕获
│   │   └── results.py                # FeatureTable (长表 DataFrame)
│   ├── export/
│   │   ├── features_io.py            # CSV(UTF-8 BOM)/HDF5
│   │   ├── epochs_io.py              # HDF5(/epochs/data|times|event_codes + /info attrs)/FIF
│   │   └── provenance.py             # <name>.pipeline.json 记录全部步骤参数+文件清单
│   ├── workers/generic.py            # run_in_thread(fn): Worker(QObject) finished/failed 信号
│   └── ui/
│       ├── main_window.py            # QMainWindow: 左工作区dock/中tab区/右处理dock/下日志dock
│       ├── strings_zh.py             # class S 全部中文标签 + 步骤参数标签表
│       ├── state.py                  # SessionState
│       ├── dialogs/                  # 导入/批处理/导出/工作区 对话框
│       └── widgets/
│           ├── workspace_tree.py     # 工作区树(多选/过滤)
│           ├── meta_table.py         # 元数据表(QTableView+排序过滤, 1500行可用)
│           ├── signal_browser.py     # 信号浏览器(核心性能件)
│           ├── event_lane.py         # 全程事件条+前后跳转
│           ├── psd_view.py           # PSD 对数坐标图
│           ├── pipeline_panel.py     # 步骤链编排(增删改排序)+预览按钮
│           ├── params_form.py        # 由 pydantic 模型自动生成参数表单
│           ├── batch_view.py         # 逐文件进度/结果表(错误红行+日志详情)
│           ├── feature_table.py      # 特征结果表
│           └── log_panel.py          # 日志面板+状态栏进度条
└── tests/
    ├── conftest.py                   # synthetic_raw fixture; real 标记用 data/sheep
    ├── synthetic_helpers.py          # savemat 伪造 BCI-IV ds1/ds4 结构
    └── test_*.py                     # registry/readers/proc/features/batch/export/ui_smoke
```

## 4. 核心设计

**Recording 统一模型**（一切的基础）：`Recording` 持有 `RecordingMeta`(pydantic, 头信息可 JSON 持久化) + `EventTable`(onset/duration/code/中文label) + `provenance`(处理历史) + 惰性 mne Raw 句柄。加载策略：预估 <200MB 直接 preload；≥200MB 用 LAZY 按窗口 `get_data(start,stop)` 服务绘图；`LoadedRawCache` 全局 LRU（默认 1.5GB 预算）在 tab 关闭后逐出。批处理强制 preload→处理→unload 逐文件进行。

**读取器注册表**：每格式一个 Reader 类（`extensions` + `read_meta` 仅解析头 + `open` 返回 Recording），扩展名→魔数嗅探两级解析。批量导入返回 `ScanReport{items, errors}`——单文件失败进错误表，绝不中断 1500 文件扫描；头解析 ~5-20ms/文件在工作线程流式填充表格。已知结构自动识别（BCI-IV ds1/ds4、Intan/mne 导出的 HDF5），未知 .mat/CSV 结构**拒绝猜测**，报中文可操作错误。

**处理步骤**：每步 = pydantic 参数模型 + `apply(ctx)->ctx`，注册进 STEP_REGISTRY；`PipelineSpec`（steps+features+export）整体序列化为 JSON——预览、批处理、导出 sidecar 共用同一可复现描述。分段步骤把 stage 从 raw 翻转为 epochs。

**信号浏览器**（性能关键）：pyqtgraph `GraphicsLayoutWidget`，每启用通道一条 `PlotCurveItem` 垂直偏移堆叠 + 底部事件条 x 轴联动。视口变化（30ms 防抖）→ 读可见窗口 → 按像素桶 min/max 峰值抽取（包络绘制，无混叠）+ `setDownsampling(peak)` + `setClipToView`。事件画彩色虚线 InfiniteLine；通道面板支持启用/排序/增益/坏道标记（灰显）。134MB 文件与 1500 文件目录都流畅（后者在打开 tab 前不加载任何原始数据）。

**批处理引擎**：`BatchEngine(QObject)` + 默认 2 工作线程（内存而非 GIL 是瓶颈）；信号 `progress/file_done/finished/failed` 队列连接回主线程；`threading.Event` 取消，逐文件、逐步骤检查；每文件捕获独立日志存入 `FileResult`。

**导出**：特征长表（recording/subject/epoch_index/event_code/channel/feature/value）→ CSV(UTF-8 BOM 供 Excel) / HDF5，可选透视为宽表；分段数据 → HDF5（data/times/event_codes + info attrs）或 FIF；每次导出自动写 `<name>.pipeline.json`（全部步骤参数 + 文件清单 + 版本）——这是与 pipelineMotor 的互操作边界。

## 5. 里程碑（每个都可运行验证）

| 里程碑 | 内容 | 验证标准 |
|---|---|---|
| **M0 骨架+治理** | git init + .gitignore + 六个治理文件 + conda env `dlv`（conda 优先安装，命令记入 HANDOFF）+ pyproject + 空包结构 + MainWindow(dock布局+中文菜单+日志面板) + workers | 治理文件齐全且内容与实际一致；应用启动出深色空窗口；trivial pytest 通过；首次 git commit |
| **M1 工作区+EDF+信号浏览器** | Recording 模型 + Workspace + EdfReader(latin1回退+.event边车) + 嗅探 + 导入对话框(扫描worker+错误表) + 元数据表 + 信号浏览器 + 事件条 | 导入 `data/sheep/`(非UTF8文件验证回退) 和 PhysioNet S001(64导,T0/T1/T2事件渲染)，浏览/缩放/跳转事件流畅 |
| **M2 读取器全覆盖** | 其余 MNE 原生读取器 + BCI-IV ds1/ds4/通用mat + GDF事件映射 + CSV/TXT/HDF5 | 4.9GB `data/dataset/` 全量扫描 <2min 带进度和逐文件错误报告；每种格式各开一个能正确绘图；2a GDF 显示 769-772 中文标签；ds4 mat <10s 加载 |
| **M3 预处理链+预览** | 6 个 proc 步骤 + PipelineDock + pydantic 自动参数表单 + 当前文件预览(处理副本tab+步骤日志) + PSD 视图 + 浏览器坏道标记联动 | 羊文件上 带通+陷波+重参考 预览后 PSD 中 50Hz 消失；2a GDF 分段数正确(如 A01T: 288) |
| **M4 特征+导出** | 3 个特征提取器 + FeatureTable/视图 + 导出对话框 + CSV/HDF5/FIF 写出 + JSON sidecar | 单文件批处理产出 Excel 可开(中文表头)的 CSV；epochs HDF5 回读形状一致；sidecar 合法 |
| **M5 批处理引擎+扩展格式+收尾** | BatchEngine(池/取消/逐文件日志) + BatchView + neo/pynwb/Intan 读取器 + 设置对话框 + README | 选 45 个 2b GDF 跑 管线+特征+CSV 导出全程 UI 响应；中途取消有效；错误行可点击看日志 |

## 6. 验证方式

- **单测**：pytest 全绿——合成数据(8导/250Hz/60s 正弦+50Hz工频+噪声+已知事件)覆盖 registry/各读取器/每步骤(陷波后 PSD 比率断言、分段数断言)/特征(10Hz 正弦功率落在α)/批处理(3文件含1损坏→2成功1报错+中途取消)/导出往返；`synthetic_helpers.py` 用 savemat 伪造 ds1/ds4 结构避免 134MB 测试夹具
- **真实数据冒烟**：`@pytest.mark.real` 标记的羊 EDF 测试（文件夹迁移时优雅跳过）
- **UI 冒烟**：pytest-qt 实例化 MainWindow、断言 dock/标题、打开合成记录、`qtbot.waitSignal` 预览作业（headless 跳过）
- **端到端人工验收**：按 M1–M5 各自验证标准在真实数据上操作
- **治理检查**（每里程碑收尾必做）：review.md 追加本里程碑验证执行情况与结果 → STATUS/TODO/HANDOFF 同步更新 → 上下文检测（中途+收尾双检查点，接近/超过 70% 先落盘再压缩）→ git commit——四件事齐做才算里程碑完成

## 7. 风险与对策

- neo/pynwb 与 mne 1.12 依赖冲突 → 隔离 `dlv` 环境 + 版本锁定 + import-guard（缺失时应用照常运行）
- pyqtgraph↔PySide6 兼容 → pyqtgraph ≥0.13.7 + PySide6 ≥6.5,<7，M0 首次启动即在本机验证
- 大文件内存 → float32 物化+del 中间体、LoadedRawCache 预算、窗口化读取
- GDF 注释怪癖（2a/2b）→ 显式事件码映射表；eval 文件 783 未知类标"未知(评估)"不崩溃
- 羊 EDF 非 UTF-8 → 自动 latin1 重试（pipelineMotor 已验证的既有解法）
- 1500 文件扫描卡 UI → 仅头解析在工作线程 + 流式填充 + 可取消
- 未知结构误猜 → 拒绝猜测原则，进错误表给出中文指引
- 范围蔓延向解码/BIDS → v1 边界：管理/浏览/预处理/特征/导出，导出即互操作边界

## 8. v2 方向（2026-08-28 与使用者讨论批准：M7 → M8 → M9）

> v1（M0–M5）2026-08-18 收官后，M6–M6.8 共 6 轮反馈驱动迭代已完成（浏览器体验/读取正确性/
> 工作区管理，详见 STATUS.md 变更记录与 review.md 各节，提交至 a47df7a）。以下为批准的后续
> 里程碑，每个仍走"治理文件更新 → review.md 记录 → 上下文检测 → git commit"四件事收尾。

| 里程碑 | 内容 | 验证标准 |
|---|---|---|
| **M7 信号质量体检（QC）** ✅ 2026-08-28 完成 | QC 做成**特征提取器**接入现有注册表（自动获得参数表单/批处理/FeatureTable 导出，零新 UI 架构）：逐通道开路复用检测（邻道逐样本同值）、饱和占比、死值、直流中位、漂移斜率；浏览 tab 一键「质量体检」+ 通道质量标记 + **自动建议**坏道（人工确认后生效，不静默改 bads）。依据：收官后至少 4 轮（羊噪声感/clinicaldata 空白/慢漂移普查/通道质量核查）是同一套诊断的手工重复 | 羊/clinicaldata 已知定论做**黄金标准回归**（CH5–8 必须报开路/饱和、CH1–3 必须报真信号带大直流、TPDJ-位置1 必须报全平，期望值=DATA_NOTES §1/§8）；pytest + e2e 全绿 → **实际达成**：pytest 213 绿（+20）+ e2e_m7 16 项×2 幂等；黄金标准全复现（羊 CH5-8 四通道开路复用判坏、CH1-4 真信号不坏——实测判疑似属设计语义、TPDJ-位置1 八通道全坏且 M7 指标精化"全平"概括为两型伪迹）；02号脑电 2 文件顺带诊断入册 |
| **M8 分段分析可视化** ✅ 2026-08-28 完成 | 平均 ERP 曲线（butterfly + 单通道放大）、时频图（mne.time_frequency，morlet）、时间分辨频带功率特征（现 bandpower 只有全段平均）。依据：ERD/ERS 是运动想象 BCI 核心指标，当前分段只有波形 | A01T/2b 真实数据上 ERP/时频可读；时间分辨特征进批处理 FeatureTable 并随导出链出表 → **实际达成**：epochs 预览**四视图**（平均堆叠/蝶形/单通道按事件码分色平均+逐段灰底/时频 morlet 热图后台线程）数据一次取齐切换零重算；`compute_epochs_tfr` 纯函数（基线校正 dB，两道闸防单样本基线）；bandpower `time_windows`（`起-止` 秒可负，epochs 相对事件锚点/raw 绝对秒，窗进特征名，整段条目并存，默认空零回归）；pytest 242 绿（+29）+ e2e_m8 13 项（A01T 四视图+21600 行时间分辨特征+CSV 回读）；**验收口径迭代**：ERD 教科书方向被数据推翻（原始未处理数据群体中位 1.05 无方向），改守恒式（子窗时长加权混合，中位误差<12%）——断数据不断理论 |
| **M8.1 三锚定分段+时频观感+单段浏览** ✅ 2026-08-28 完成 | （M8 后用户三问题反馈增补）①无事件数据可分段（固定窗滑窗/手动时刻锚点）；②时频热图纵向铺满+jet/hot 配色+结果缓存；③第五视图单段浏览（翻页看数据） | 手动/滑窗分段数与样本域公式一致；观感截图级验收 → **实际达成**：epoching `anchor/step_s/anchors_s`（事件锚定默认零回归；手动越界显式报错列全部无效锚点；锚点样本域构造防 mne 静默丢段）；时频 autoRange 修复 Y 压扁（堆叠/蝶形 setYRange 残留根因）+配色下拉（jet/hot 公式 uint8 生成——float 色被按 0..255 截断成全黑）+按通道缓存零重算；第五视图 append 尾部保 e2e_m8 索引稳定；pytest 257 绿（+15）+ e2e_m81 12 项（滑窗 538 段公式现算）+ e2e_m8 13 项零回归 |
| **M9 处理后连续数据导出** ✅ 2026-08-31 完成 | 预处理后的 raw 导出 EDF/FIF + sidecar（目前只能导特征与 epochs，补齐与 pipelineMotor 的连续数据互操作） | 导出回读一致（mne 读回数值/时长/事件对照）；sidecar 含全管线 → **实际达成**：`export/continuous_io`（EDF 走 `mne.export`+**physical_range="channelwise"**——默认按类型统一量程会被羊 ±375000µV 开路饱和通道拖到步长 11.4µV/LSB 抹掉正常信号；FIF `raw.save(fmt="single")` 强制 `_raw` 规约后缀；通道类型白名单+标签 ≤16 ASCII 前置中文守卫）双入口（面板「导出连续数据…」单文件 / 批处理导出组两复选框逐文件——含 epoching 的管线自动跳过+导出失败降级日志不杀特征；顺带修 run() 尾部只勾 raw 误写特征 CSV 的分支漏洞）；pytest 287 绿（+16）+ e2e_m9 16 项（羊 50Hz 压制随导出保真比值 0.0000、FIF 往返最大偏差 2.9e-11V、批处理 3 文件全 ok） |
| **M10 双平台打包** 🔶 2026-09-01 机器验证过（人工验收与 CI push 待办） | PyInstaller 双平台免安装分发包（macOS .app 本机打 + Windows .exe 走 GitHub Actions），免 Python/conda 环境配置；实施指令自包含于 PACKAGING_HANDOFF.md | 目标机器双击打开→羊数据导入→浏览→预览→特征→导出 CSV+EDF 全流程；日志/设置写 ~/.dataloadv/ → **实际达成（机器可验部分）**：单份 spec 跨平台 + entry shim + app `--smoke` 自检；macOS 全量 42s/293MB/zip 119MB；offscreen 冒烟 SMOKE OK、真窗口存活+优雅退出、PYZ 延迟依赖核实、pytest 287 零回归；CI workflow actionlint 过（未 push）；瘦身取消（293MB≪900MB）；**待办**：用户五步流程亲眼验收、push CI 首跑、Windows 真机真人验收 |

**随里程碑捎带**：`conda env export` 锁定 environment.yml（配合已改的相对路径安装说明，完整可复现）。

**明确暂不做**（维持 backlog）：ds3 分段 MEG、.edf.event WFDB 边车、CNT/EGI/BrainVision/EEGLAB/neo 系真实数据补测（等真实文件到位）、界面主题切换。
