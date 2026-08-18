# DataloadV 手册 —— 项目说明 · 运行 · 使用 · 调试

> 一册通览：项目是什么、怎么搭怎么跑、界面怎么用、出问题怎么排、想扩展怎么加。
> 与其他文档的分工：简介见 [README.md](README.md)，开发方案见 [plan.md](plan.md)，进度快照见
> [STATUS.md](STATUS.md)，待办见 [TODO.md](TODO.md)，接手细节与坑清单见 [HANDOFF.md](HANDOFF.md)，
> 验证记录见 [review.md](review.md)，数据集详情见 [DATA_NOTES.md](DATA_NOTES.md)。
>
> **版本基线**：v1（里程碑 M0–M5 全部完成）+ M6 浏览体验优化（2026-08-18）；
> 验证口径：pytest 150 绿 + e2e_m1–m5 共 83 项 + GUI 冒烟全过。

---

## 1. 项目说明

### 1.1 定位与边界

DataloadV 是面向**介入式 BCI 研究**的电生理数据桌面工作台（macOS 优先，PySide6 浅色白底绘图、
全中文），覆盖一条完整工作流：

```
读取（16 种格式） → 工作区管理 → 波形浏览 → 预处理链 → 特征提取 → 批处理 → 导出（CSV/HDF5/FIF + JSON sidecar）
```

- **与 pipelineMotor 的关系**：零代码耦合。互操作只发生在导出物——特征长表 CSV/HDF5、
  分段数据 HDF5/FIF、`<名>.pipeline.json` 管线溯源文件（全部步骤参数 + 文件清单 + 库版本），
  下游脚本凭 sidecar 可完整复现处理过程。
- **v1 边界**（防范围蔓延，超出的一律明确拒绝并给中文提示而非猜测）：不做解码/分类、
  不做 BIDS 转换、未知结构的 .mat/HDF5 拒绝猜测、ds3 分段 MEG 明确拒绝（记 backlog）。

### 1.2 功能总览

| 模块 | 能力 | 入口 |
|---|---|---|
| 数据管理 | 16 格式导入（单文件/整目录递归）、元数据表（10 列排序过滤）、工作区持久化、逐文件错误报告 | 文件菜单 → 导入文件…/导入文件夹… |
| 波形浏览 | 多通道滚动浏览（峰值包络防混叠）、一屏时长选择+翻屏导航（按钮/滚轮/键盘）、幅值标尺、事件竖线叠加与跳转、事件概览条点击定位、通道显隐、纵向增益、右键坏道标记 | 工作区树/元数据表双击 |
| 预处理 | 7 种步骤组成链（自上而下执行）、pydantic 参数自动表单、当前文件预览（处理副本新 tab）、原始 vs 处理后 PSD 对比 | 右侧「处理」Dock |
| 特征提取 | 3 种提取器（频带功率/PSD 曲线/时域统计）、raw 全量摘要或 epochs 逐段、「用当前显示窗口」一键预填时间窗 | 右侧「处理」Dock → 计算特征 |
| 批处理 | 面板管线+特征链批量套到工作区任意文件子集；2–8 线程并行、逐文件进度/日志、单文件失败不杀整批、随时取消、UI 全程响应 | 处理菜单 → 批处理… |
| 导出 | 特征 CSV（UTF-8 BOM，Excel 直开）/HDF5、分段数据 HDF5/FIF、每次导出自动随写 sidecar | 特征结果 tab → 导出按钮 |
| 设置 | 批处理默认线程数、数据缓存预算（GB）、默认导出目录 | 文件菜单 → 设置… |

### 1.3 支持的数据格式

**内置 11 个读取器（核心依赖即可用）**：

| 格式 | 扩展名 | 读取途径 | 备注 |
|---|---|---|---|
| EDF/EDF+ | `.edf` | mne | 非 UTF-8 文件自动 latin1 回退（羊数据实证） |
| BDF | `.bdf` | mne | 模板路径，无真实数据实测（backlog） |
| GDF | `.gdf` | mne | BCI-IV 2a/2b；事件码→中文标签（官方 PDF 核实 16 码） |
| BrainVision | `.vhdr` | mne | 入口取头文件，数据文件随行 |
| FIF | `.fif` | mne | mne 原生，合成往返有测试 |
| EEGLAB | `.set` | mne | 同上 |
| CNT / EGI | `.cnt` `.egi` `.mff` | mne | `.mff` 为目录，注册表自动展开候选 |
| BCI-IV ds1/ds4 | `.mat` | 自研解析 | ds1 头只读 nfo/mrk；ds4 纯 whosmat 跳过 test_data |
| 通用 .mat | `.mat` | 拒绝猜测 | 识别不了给中文指引，绝不明猜结构 |
| CSV/TXT | `.csv` `.txt` | 自研 | 分隔符嗅探+数值性验证；文件内无采样率 → 打开时询问一次并记忆 |
| 通用 HDF5 | `.h5` `.hdf5` | 自研 | 零数据 IO 定位二维信号集，歧义拒绝 |

**可选 4 个读取器（`pip install -e ".[extra-readers]"` 或按 §2.1 安装 neo/pynwb 后启用；
缺失时应用照常运行，仅这些格式不可用）**：

| 格式 | 扩展名 | 读取途径 | 备注 |
|---|---|---|---|
| Blackrock | `.nev` `.ns1`–`.ns6` | neo.rawio | 全名打开失败自动回退去扩展名基名 |
| Open Ephys | `.continuous` | neo.rawio | 收**目录**（文件取 parent） |
| Intan | `.rhd` `.rhs` | neo.rawio | — |
| NWB | `.nwb` | pynwb | 取第一个 ElectricalSeries；trials/epochs 表→事件 |

### 1.4 技术栈与版本（2026-08-18 实测安装）

| 包 | 版本 | 来源 |
|---|---|---|
| Python | 3.10 | conda env `dlv` |
| numpy / scipy / pandas | 1.26.4 / 1.15.2 / 2.3.3 | conda-forge |
| PySide6 / pyqtgraph | 6.11.0 / 0.14.0 | conda-forge |
| pydantic / h5py | 2.13.4 / 3.16.0 | conda-forge |
| mne / edfio | 1.12.0 / 0.4.16 | pip |
| neo / pynwb（可选） | 0.14.5 / 4.1.0 | pip / conda-forge |

### 1.5 架构与目录

**分层铁律（四条硬性规则，改代码前必读）**：

1. `core/io/proc/features/batch/export` 六个计算层包**禁止 import PySide6/pyqtgraph**；
2. UI 只编排不计算——一切耗时操作走 worker 线程 + 信号回调；
3. 跨线程只传纯 Python / mne 对象；
4. 每里程碑收尾四件事：治理文件 → review 记录 → 上下文检测 → git commit。

```
src/dataloadv/
├── app.py / __main__.py      # 入口：QApplication、深色主题、excepthook→日志
├── core/                     # 计算层（无 Qt）
│   ├── recording.py          #   Recording / RecordingMeta / EventTable / LoadPolicy / LoadedRawCache(LRU)
│   ├── workspace.py          #   工作区 + ~/.dataloadv/ JSON 持久化
│   ├── fs_store.py           #   CSV/HDF5 采样率询问记忆
│   └── app_settings.py       #   应用设置（原子写 + 热生效）
├── io/                       # 读取器层（无 Qt）：注册表模式，每格式一个 Reader 类
│   ├── registry.py           #   @register_reader + open_file/scan_folder（容错+进度）
│   ├── mne_readers.py        #   _MneRawReader 模板 + 8 格式子类
│   ├── bciciv_mat.py / table.py / hdf5.py / sniffing.py / event_maps.py
│   └── neo_reader.py / nwb_reader.py   # 可选依赖读取器（import-guard）
├── proc/                     # 预处理层（无 Qt）：7 步骤 + STEP_REGISTRY + apply_pipeline
├── features/                 # 特征层（无 Qt）：3 提取器 + FEATURE_REGISTRY + apply_features（与 proc 同构）
├── batch/                    # 批处理层（无 Qt）：jobs.py 任务模型 + engine.py 纯 Python 引擎 + results.py 长表
├── export/                   # 导出层（无 Qt）：features_io / epochs_io / provenance(sidecar)
├── workers/generic.py        # run_in_thread：后台任务 + _MainRelay 主线程回调保护
└── ui/                       # 全部 Qt 代码：main_window + state(信号中枢) + strings_zh(全中文文案)
    ├── dialogs/              #   import / batch / settings
    └── widgets/              #   工作区树/元数据表/信号浏览器/事件条/管线面板/参数表单/
                              #   PSD 视图/分段预览/特征表/批处理视图/日志面板
```

### 1.6 核心设计模型

- **Recording 统一模型**：一切数据入口。`RecordingMeta`（pydantic，头信息可 JSON 持久化）+
  `EventTable`（onset/duration/code/中文 label）+ 惰性 mne Raw 句柄。加载策略
  `LoadPolicy.HEADER_ONLY / PRELOAD`：浏览 tab 打开时只读头（毫秒级），首帧数据后台整载；
  大文件按窗口读。**LoadedRawCache** 全局 LRU（默认预算 1.5GB，可在设置改）在 tab 关闭后
  逐出释放内存；批处理并发处理时 pin 防互逐。
- **读取器注册表**：`@register_reader` 装饰器自注册；扩展名 → 魔数嗅探两级解析；
  `scan_folder` 单文件失败进错误表**绝不中断整批**（4.9GB/1606 条实测 6s）。
- **步骤/特征同构注册表**：每个处理步骤 = pydantic 参数模型 + `apply(ctx)->ctx`；每个特征 =
  参数模型 + `extract(ctx)`。注册后参数表单**零 UI 代码**自动生成（`params_form.py`）。
  `to_dict/from_dict` 序列化保证「面板上组好的链」＝「批处理跑的链」＝「sidecar 记的链」。
- **阶段模型**：`ProcessingContext.stage` 为 `raw` 或 `epochs`；`epoching` 步骤把 raw 翻转为
  epochs；滤波类步骤的阶段约束由 `apply_pipeline` 统一检查（如陷波仅限 raw——mne Epochs
  无 notch_filter），顺序错误给中文提示。
- **批处理线程模型**：`BatchEngine` 是**纯 Python**（架构规则 #1 优先于早期方案的 QObject）：
  回调在 worker 线程执行 → 只往 `queue.Queue` 塞事件 → UI 侧 QTimer 150ms 事件泵转主线程。
  取消 = `threading.Event`，引擎在**步骤边界**停止（proc/features 各步检查 `cancel_check`）。
- **导出即互操作**：特征长表 7 列（录制/被试/段序号/事件码/通道/特征/数值）；每次导出自动写
  `<名>.pipeline.json`（步骤+特征全参数、文件清单、库版本、batch 扩展信息）。

### 1.7 数据与配置的存放约定

| 位置 | 内容 | 权限 |
|---|---|---|
| `data/` | 原始数据集（4.9GB：dataset/sheep/sheep2） | **只读**，应用绝不写入 |
| `~/.dataloadv/` | settings.json（设置）、workspaces/（工作区）、logs/（日志）、table_fs.json（采样率记忆） | 应用可写 |
| 用户选择的目录 | 导出产物（CSV/HDF5/FIF/sidecar） | 经保存对话框 |

---

## 2. 运行

### 2.1 从零安装（macOS，完整命令）

```bash
# 1. conda 环境（专用；绝不使用 py310lg——那是 pipelineMotor 的冻结研究环境）
source ~/miniconda3/etc/profile.d/conda.sh
conda create -y -n dlv python=3.10
conda activate dlv

# 2. 科学/GUI 栈（conda-forge 优先）
conda install -y -c conda-forge "numpy=1.26.4" "scipy>=1.10" "pandas>=2.0" \
    "h5py>=3.8" "pydantic>=2.4,<3" "PySide6>=6.5,<7" "pyqtgraph>=0.13.7" \
    pyyaml pytest pytest-qt

# 3. MNE 等 conda 缺失的包（pip 补）
pip install "mne==1.12.0" edfio

# 4. 可选格式依赖（Blackrock/Open Ephys/Intan/NWB；不装则这四种格式不可用）
conda install -y -c conda-forge "pynwb>=3.0"   # pynwb 走 conda
pip install "neo>=0.13"                        # neo 不在 conda-forge，pip 例外

# 5. 本包可编辑安装（含 dev 依赖）
pip install -e "/Users/huyingbing/VSproject/intervention BCI/DataloadV[dev]"
```

### 2.2 启动

```bash
conda activate dlv
dataloadv            # 或 python -m dataloadv
```

**两个常见疑问（2026-08-18 实测）**：

- **必须 activate 吗？** 不必——依赖只存在于 `dlv` 环境（所以必须用它的 Python），但入口有三种
  免激活走法：`~/miniconda3/envs/dlv/bin/dataloadv`（绝对路径直调）、`conda run -n dlv dataloadv`、
  或往 `~/.zshrc` 加一行 `alias dataloadv='~/miniconda3/envs/dlv/bin/dataloadv'` 后任何终端直敲。
- **必须 cd 到项目目录吗？** 不必——本包是 `pip install -e`（可编辑安装），已注册进 dlv 环境，
  **任何目录**下 `dataloadv` 都能启动；工作区/设置/日志在 `~/.dataloadv/`、工作区记录的是绝对
  路径，换目录启动无影响。唯一例外是**开发调试**：`pytest` 的 testpaths 是相对路径，跑测试请
  回项目根目录（e2e 脚本从哪跑都行，按 `__file__` 自定位）。

启动即浅色（白底绘图）主题、PingFang SC 中文字体、1440×900 主窗口；未捕获异常自动写入日志文件（§4.1）。

### 2.3 安装验证

| 命令 | 预期 |
|---|---|
| `pytest` | 150 passed（含真实数据项） |
| `python scripts/smoke_gui.py` | 末行 SMOKE OK（真窗口自检后自动退出） |
| `python scripts/e2e_m1.py` … `e2e_m5.py` | 各打印 ALL OK（真实数据端到端，幂等可反复跑；m1 含 M6 浏览交互 18 项） |

### 2.4 无头/远程环境

```bash
QT_QPA_PLATFORM=offscreen python scripts/e2e_m1.py   # CI/SSH 无显示器的跑法
```

---

## 3. 使用

### 3.1 界面总览

```
┌────────────────────────────────────────────────────────────────────┐
│ 文件(导入文件…/导入文件夹…/设置…/退出) 查看(dock显隐) 处理(预览/PSD/   │
│ 特征/批处理…) 帮助(关于)                                            │
├──────────┬──────────────────────────────────────────┬─────────────┤
│ 工作区    │  tab 区：元数据表(常驻) │ 浏览 │ 预览 · …  │ 处理        │
│ (Dock)   │                       │ 分段预览 │ 特征 · … │ (管线面板)  │
│ 树+过滤   │                       │ 批处理 · …              │ 步骤链      │
│          │                                              │ 特征链      │
│          │                                              │ 参数表单    │
├──────────┴──────────────────────────────────────────┴─────────────┤
│ 日志(Dock)：全应用运行日志（≤5000 行滚动）                          │
├────────────────────────────────────────────────────────────────────┤
│ 状态栏：临时消息 / 导入进度条 / 版本号                               │
└────────────────────────────────────────────────────────────────────┘
```

**除浏览 tab 内的导航键（←/→/Home/End/↑/↓，见 §3.5）外没有全局快捷键**——其余操作走菜单、按钮、鼠标。

### 3.2 五分钟走通（典型流程）

1. **导入**：文件 → 导入文件夹… → 选数据目录（递归扫描，状态栏有进度；失败文件弹错误表）。
2. **浏览**：在元数据表或工作区树**双击**任意一行 → 开浏览 tab，滚轮平移/翻屏按钮查看波形与事件线，右上角幅值标尺读幅度。
3. **组链**：右侧「处理」Dock → 添加步骤（如 带通滤波 → 陷波（工频））→ **预览当前文件**
   → 开「预览 · …」tab 看处理效果 → **对比 PSD** 看 50Hz 工频峰是否消失。
4. **特征**：添加特征（如 频带功率，频段选 α/β）→ 计算特征 → 开「特征 · …」tab。
5. **批处理**：处理 → 批处理… → 勾选文件、选导出目录 → 开始 → 完成后自动开「批处理 · …」
   结果 tab → 导出 CSV。

### 3.3 数据导入与工作区

- **导入文件…**：多选文件对话框（常用格式过滤器 + 所有文件）。
- **导入文件夹…**：固定**递归**扫描所选目录。扫描在后台线程，状态栏显示
  「正在扫描：{name}」+ 进度条；完成显示「导入完成：新增 N 条，重复 N 条，失败 N 条」。
- 单文件失败（损坏/结构未知/依赖缺失）**不中断整批**：结束后弹「部分文件导入失败」对话框，
  内嵌 文件/错误 两列表格逐条给中文原因。
- **工作区**：导入来源 → 录制 两级树；关窗自动保存，下次启动原样恢复；重复导入自动去重。
- **采样率询问**：CSV/TXT/HDF5 等文件内不含采样率时，打开浏览会弹「设定采样率」输入框
  （默认 250 Hz）——**同一文件只需输一次**，选择记住后此后直接使用（存 `~/.dataloadv/table_fs.json`）。

### 3.4 元数据表与工作区树

- **元数据表**（常驻首个 tab）：10 列（名称/被试/格式/通道数/采样率/时长/事件数/任务/Run/
  导入来源）；点列头排序（数值列按数值）；顶部过滤框全列包含匹配；双击行开浏览 tab；
  支持整行多选（Ctrl/Shift，供批处理取文件集）。
- **工作区树**（左 Dock）：按导入来源分组；过滤框按文件名/被试匹配；双击录制条目开浏览 tab。

### 3.5 波形浏览（浏览 tab）

| 操作 | 效果 |
|---|---|
| **滚轮** | 时间轴**平移**（一屏的 10%；向上滚看更早）——y 轴已锁定，通道行不会被滚轮压挤 |
| **Ctrl+滚轮** | 以鼠标位置为锚点缩放一屏时长（×1.25/档） |
| **← / →** | 上一屏 / 下一屏（步进 0.9 屏，留 10% 上下文；需先点一下图区获得焦点） |
| **Home / End** | 最前一屏 / 最后一屏 |
| **↑ / ↓** | 纵向增益 ±1 档（等效拖滑杆） |
| 「一屏时长 (s)」下拉 | 选 1/2/5/10/30/60 s 预设，或直接输入自定义秒数；视口中心保持不变；拖框缩放后此处回显实际宽度 |
| 「\|◀ 最前 / ◀ 上一屏 / 下一屏 ▶ / 最末 ▶\|」 | 与键盘等价的翻屏按钮 |
| 左键拖动 | 平移；**右键拖动**框选缩放（pyqtgraph 原生，仅 x 轴） |
| 「◀ 上一事件 / 下一事件 ▶」 | 从当前视口中心跳到前/后最近事件并居中（2026-08-18 修正过接线，此前方向相反） |
| 点击底部事件概览条 | 主视图居中到点击时刻（视口宽度不变） |
| 「纵向增益」滑杆 | 0.1×–10× 指数刻度，只缩放波形不挪基线，拖动即时生效 |
| 通道列表勾选 | 显示/隐藏对应曲线与名称标签（顺序即文件通道顺序） |
| 通道**右键 → 标记为坏道** | 曲线变灰；写入 raw.info['bads'] 并联动管线面板（之后添加「坏导联处理」步骤时自动带入这些通道） |

通道名显示在每条曲线行**左端内侧**（全名、任意导联数不重叠不截断）；绘图区右上角是**幅值
比例尺**——竖线长度固定 60px，标注换算回真实微伏值并随增益动态更新（堆叠显示下所有通道
共享同一比例尺）。

性能说明：视口变化经 30ms 防抖后**只读可见窗口**的数据，按像素桶 min/max 峰值包络绘制——
GB 级文件浏览与小文件同速，且无混叠伪影；初始窗口 10 秒。

事件显示：主图内彩色竖直虚线（颜色按事件码稳定分配），事件条图例显示「事件码×次数」；
GDF 事件码自动转中文标签（如 769 → 左手运动想象 cue）。

### 3.6 预处理管线（7 种步骤）

右侧「处理」Dock → **添加步骤**下拉菜单（按序执行；`删除/上移/下移/清空`调整）；
选中任一步骤即在下方参数表单中编辑（改动实时保存）。

| 步骤 | 用途 | 关键参数 | 阶段约束 |
|---|---|---|---|
| 带通滤波 | 去漂移/高频噪声 | l_freq/h_freq（可只设一端） | raw+epochs |
| 陷波（工频） | 去 50/60Hz 工频 | freq（默认 50） | **仅 raw**（分段前做） |
| 重参考 | 平均参考/自定义 | reference 列表 | raw+epochs |
| 降采样 | 降采样率 | sfreq（只降不升） | raw+epochs |
| 坏导联处理 | 标记或插值 | channels（带入浏览器标记）/mode | raw+epochs |
| 事件分段 | 按事件码切段 | event_codes/tmin/tmax/baseline/reject_uv | raw→**epochs**（阶段翻转） |
| 时间窗裁剪 | 只留一段时间 | tmin/tmax（raw=绝对时间；epochs=相对事件锚点） | raw+epochs |

**特征范围四层组合**（选定数据范围的方式）：① 全量默认（文件级摘要）；② epochs 逐段
（每段一行）；③ 时间窗裁剪步骤（显式窗口，进 sidecar 可复现）；④ 「用当前显示窗口」按钮
把当前视口**预填**进裁剪步骤参数（只预填不隐式绑定，保证可复现）。滤波类步骤始终全量做
（避免边界效应），crop 只裁数据范围。

### 3.7 预览与 PSD 对比

- **预览当前文件**：对当前浏览 tab 数据的**副本**执行整条链（原始数据逐位不变）——
  raw 阶段开「预览 · {name}」tab（可继续缩放浏览），epochs 阶段开「分段预览 · {name}」tab
  （分段总数、各类事件码计数、各通道跨段平均波形）。
- **对比 PSD**：独立窗口，双对数坐标，**红线=原始、蓝线=处理后**（通道平均 Welch，取前 120s；
  浅色主题下原始=红/处理后=蓝，与浏览器波形深蓝区分）。
  典型验收：羊数据 带通+陷波 后 50Hz 峰消失。

### 3.8 特征提取（3 种提取器）

**添加特征**下拉：`频带功率`（δ/θ/α/β/γ + 自定义「频段:起-止」，可选相对功率/对数）、
`PSD 曲线`（仅 raw 阶段——逐段曲线量爆炸无浏览价值）、`时域统计`（rms/var/mav/ptp/iqr/
过零率/峭度/偏度 8 项）。**计算特征**后开「特征 · {name}」tab。

通道说明：特征默认作用于全部数据通道；BCI-IV 2a/2b 的 GDF 被 mne 全部标为 eeg（EOG 不被
类型白名单排除）——要排除眼电需在特征参数 channels 里显式写 EEG 通道名（见 §4.2 #6）。

### 3.9 批处理

处理菜单 → **批处理…**（或右 Dock 底部按钮）：

1. **选择页**：过滤框 + 可勾选文件清单（全选/全不选）；管线摘要行（面板当前链的快照）；
   导出组（CSV/HDF5 勾选、文件名、导出目录、线程数 1–8 默认 2）。
2. **运行页**：逐文件表格（等待中/处理中/成功/失败/已取消 + 耗时 + 特征值数，状态着色）；
   进度条；**取消批处理**按钮（请求后引擎在当前步骤边界停止，未开始文件标记「已取消」）；
   **双击任意行弹该文件逐行日志**（失败行含【错误】原因；失败行悬停 tooltip 亦可直接看原因）。
3. **结束**：摘要行显示 成功/失败/取消/总特征值数/用时/写出文件；至少一个文件成功即自动开
   「批处理 · {name}」结果 tab（与其他特征 tab 一样可排序、可导出）。

行为要点：单文件失败（文件损坏/格式不识别/未设采样率）**不杀整批**；导出自动带 sidecar
（extra.batch 记 n_files/n_workers/files_written）；运行中关闭对话框=请求取消（不强杀线程）。

### 3.10 导出（产物一览）

| 产物 | 内容 | 打开方式 |
|---|---|---|
| `*.csv` 特征长表 | 7 列中文表头，UTF-8 **带 BOM** | Excel 双击直开不乱码 |
| `*.h5` 特征 | /features 长表 + /psd/<i> 曲线 | h5py/pandas/HDFView |
| `epochs.h5` 分段 | /epochs/data(N段×N导×N点) + times + event_codes + info attrs | h5py；形状与界面一致 |
| `epochs-epo.fif` 分段 | mne Epochs 无损 | `mne.read_epochs()` |
| `*.pipeline.json` sidecar | 步骤+特征全参数/文件清单/库版本/batch 信息 | 任何 JSON 阅读器；复现凭据 |

导出入口都在特征/批处理结果 tab 右上（「导出分段…」仅分段阶段出现，二选一 HDF5/FIF）；
每次导出 sidecar 自动随写。

### 3.11 设置（文件 → 设置…）

| 字段 | 含义 | 生效方式 |
|---|---|---|
| 批处理默认线程数 | 新批处理对话框的初始值 | 保存即持久 |
| 数据缓存预算 (GB) | LoadedRawCache LRU 上限（浏览 tab 关闭后按此逐出内存） | 保存即热生效 |
| 默认导出目录 | 批处理对话框导出路径初始值 | 保存即持久 |

设置存 `~/.dataloadv/settings.json`（临时文件+rename 原子写；文件损坏自动回默认值）。

---

## 4. 调试

### 4.1 日志体系（三个出口，同一数据源）

| 出口 | 位置 | 用途 |
|---|---|---|
| 界面日志面板 | 底部「日志」Dock（≤5000 行滚动） | 实时观察；worker 线程日志也汇入（信号桥回主线程） |
| 滚动日志文件 | `~/.dataloadv/logs/dataloadv.log`（5MB×3 备份，utf-8） | **事后排障首选**；未捕获异常完整堆栈必落此处 |
| 控制台 | 启动终端 | 与文件同内容 |

- 格式：`时间 [级别] 模块名: 消息`；默认 INFO 级。
- **崩溃排查**：`app.py` 装了全局 excepthook——未捕获异常不会静默消失，完整 traceback 以
  CRITICAL 写入上述三个出口；查日志文件末尾即得现场。
- 临时提级（排查读取器细节）：在 Python 会话中
  `import logging; logging.getLogger().setLevel(logging.DEBUG)`（文件级修改入口在
  `core/logging_setup.py` 的 `setup_logging(level)`）。

### 4.2 常见问题速查

| # | 症状 | 原因 | 处置 |
|---|---|---|---|
| 1 | 打开 CSV/TXT/HDF5 弹「设定采样率」 | 文件内不含采样率 | 输入一次即永久记忆；填错可删 `~/.dataloadv/table_fs.json` 对应条目重来 |
| 2 | 批处理某文件失败，日志含「采样率未设定…浏览 tab」 | 该文件从未打开过、无采样率记忆 | 先双击打开该文件完成采样率设定，再批处理 |
| 3 | 批处理某文件失败「Bad GDF file…」等 | 文件损坏 | 属预期容错——看失败行日志；其余文件不受影响 |
| 4 | 2b 评估(E)文件分段数为 0 | E 文件 769/770 事件全 0，未知类 cue 是 **783** | 事件分段步骤的 event_codes 加上 783（T 文件 120 段/E 文件 160 段） |
| 5 | GDF 打开时控制台刷 RuntimeWarning「Highpass 100 > Lowpass 0.5」 | 2b 文件头自带矛盾滤波参数 | 无害（mne 自动置 0），不影响任何数值结果 |
| 6 | 2a/2b 特征行数比预期多（25 导而非 22） | mne 把 22 EEG+3 EOG 全标 eeg，类型白名单拦不住 | 特征参数 channels 显式列 22 个 EEG 通道名 |
| 7 | 未知 .mat 导入失败「无法识别结构」 | 设计如此：拒绝猜测 | 按错误提示确认文件结构；BCI-IV ds1/ds4 有专用读取器 |
| 8 | Blackrock/OE/Intan/NWB 格式列表里没有 | neo/pynwb 未安装 | 按 §2.1 第 4 步安装；装完重启应用 |
| 9 | 大文件多开后内存上涨 | LRU 缓存逐出有延迟 | 关闭不用的浏览 tab 即释放；或在设置调低缓存预算 |
| 10 | 陷波步骤报「仅支持 raw 阶段」 | mne Epochs 无 notch_filter | 把陷波移到事件分段**之前** |
| 11 | 界面卡死（历史） | 早期 worker 线程弹模态框（macOS 冻结） | 已修复（_MainRelay）；若复现请记日志时间点报 HANDOFF 坑 #13 |
| 12 | e2e/测试脚本「假死」CPU 0% | 模态对话框未中和 | e2e 规约：逐模块 patch QMessageBox + 轮询加 tries 上限（HANDOFF 坑 #31） |

### 4.3 测试体系

```bash
pytest                    # 全部 150 项
pytest -m real            # 仅真实数据冒烟（data/sheep 缺失自动跳过）
pytest tests/test_proc_m3.py -k "epoching"   # 单文件/单关键字
QT_QPA_PLATFORM=offscreen python scripts/e2e_m5.py   # 无头跑端到端
```

- **e2e 幂等原理**：脚本开头切到一次性工作区、结束切回原工作区并关全部 tab；断言用总量
  而非新增数——可反复跑不污染状态。
- 单测分层：synthetic_helpers 合成 8 导/250Hz 数据覆盖各模块；`real` 标记项用
  data/sheep 真实 latin1 EDF 与真实 GDF；NWB 用 pynwb 真实写读往返；neo 系用桩 rawio
  验证模板逻辑（无真实样例文件的诚实边界，记 backlog）。

### 4.4 性能与内存要点

- 浏览只读可见窗口 + 峰值包络 → 渲染与文件大小无关；4.9GB 目录扫描 6s（头解析流式填充）。
- 内存由 LoadedRawCache LRU 统一管理（预算可设）；批处理逐文件 整载→处理→卸载，
  并发时 pin 防互逐；ds4 大 mat（134MB）物化 float32 并及时 del 中间体。
- mne 滤波需 preload=True——预览/批处理入口已自动保证。

### 4.5 扩展开发指南（三件套惯例）

**新增处理步骤**（proc 层）：
1. 参数模型 + 步骤类（`ProcStep` 子类，`apply(ctx)->ctx`，中文 docstring）+ `@register_step`；
2. `strings_zh.py` 加步骤中文名与参数标签；
3. tests 加往返/效果断言。参数表单自动出现，UI 零改动。

**新增特征提取器**（features 层）：同上，`FeatureExtractor` 子类 + `extract(ctx)` +
`step_id` property 别名（params_form 零改动复用的关键）。

**新增读取格式**：mne 可读的用 `_MneRawReader` 模板子类（只声明 `_fmt`/`_read_fn`——
**必须 staticmethod 包住**/`_extra`）；neo 可读的用 `_NeoRawReader` 模板；其余独立实现
`BaseReader`（read_meta 仅头/open/load_raw）。可选依赖用 `requires_extra` 声明，注册表
import-guard 自动跳过。

**红线自查**（提交前）：计算层六包无 Qt import（`grep -rn "PySide6\|pyqtgraph" src/dataloadv/{core,io,proc,features,batch,export}/`）；
UI 新控件不直接计算；跨线程只传纯 Python/mne 对象。

### 4.6 崩溃/异常排查流程

1. 看 `~/.dataloadv/logs/dataloadv.log` 末尾（CRITICAL = 未捕获异常全栈）；
2. 复现路径若在界面操作，对照 §4.2 速查表；
3. 用对应 e2e 脚本在 offscreen 下复现（可反复跑）；
4. 修改后跑 `pytest` + 对应 e2e + `smoke_gui`；
5. 新发现的坑回写 HANDOFF 坑清单与 STATUS 实证结论。

---

## 5. 附录

### 5.1 治理文件索引

| 文件 | 内容 | 更新节奏 |
|---|---|---|
| plan.md | 开发方案（架构决策/里程碑） | 重大方案变更 |
| review.md | 每里程碑验证执行记录 | 每里程碑 |
| STATUS.md | 进度快照/实证结论/变更记录 | 每里程碑 |
| TODO.md | 待办与 backlog | 随进展 |
| HANDOFF.md | 环境复现/架构导览/37 条坑清单 | 每里程碑 |
| DATA_NOTES.md | 数据集来源/结构/事件码表/坑 | 新数据实证 |
| MANUAL.md | 本手册（使用+排障+扩展） | 重大功能变化 |

### 5.2 真实数据路径速查

羊 EDF `data/sheep/*.edf`；PhysioNet `data/dataset/files/S001/`；2a GDF
`data/dataset/BCICIV_2a_gdf/A01T.gdf`；2b GDF 目录 `data/dataset/BCICIV_2b_gdf/`（45 文件，
批处理验收集）；ds1 `data/dataset/BCICIV_1_mat/BCICIV_calib_ds1a.mat`；ds4
`data/dataset/BCICIV_4_mat/sub1_comp.mat`。

### 5.3 已知边界（v1 收官时点）

- BDF/CNT/EGI/BrainVision/EEGLAB、Blackrock/Open Ephys/Intan/NWB 均无真实样例实测
  （模板+往返/桩测试保证，取得文件后 `open_file()` 冒烟即可，风险低）；
- ds3 分段 MEG 明确拒绝；.edf.event 边车不需要（内嵌注释已完整）；
- 除浏览 tab 导航键（§3.5，M6 加入）外无全局快捷键、无通道拖拽排序、无导出对话框（导出按钮内嵌在结果 tab）——均记 backlog 见 TODO.md；
- epochs 分段预览的通道名仍走 y 轴刻度（静态图、通道少，未触发重叠问题；记 backlog）。
