# REVIEW — 开发审核记录

> 每个里程碑完成验证后追加一节。记录：做了什么、怎么验的、结果如何、发现的问题与修正。重大方案变更也记录于此。

---

## M0 骨架+治理 — ✅ 完成（2026-08-18）

**做了什么**
1. git 仓库初始化（仓库级身份 `DataloadV Dev <dev@dataloadv.local>`，仿 pipelineMotor，不动全局配置）；`.gitignore` 排除 `data/`、全部电生理数据扩展名、Python/IDE 缓存
2. 六个治理文件建立：plan.md（批准方案正式版）/ review.md / STATUS.md / TODO.md / HANDOFF.md / README.md
3. conda env `dlv`（Python 3.10）：conda-forge 装 numpy=1.26.4、scipy、pandas、h5py、pydantic、PySide6、pyqtgraph、pyyaml、pytest、pytest-qt；pip 装 mne==1.12.0、edfio（用户要求 conda 优先、MNE 走 pip）
4. 包骨架：pyproject.toml（hatchling/src-layout/`dataloadv` 入口/[dev] 与 [extra-readers] extras）；`app.py` 入口（高 DPI、excepthook→日志）、`__main__.py`、`core/logging_setup.py`（控制台+滚动文件+Qt 桥接 Handler）、`workers/generic.py`（run_in_thread 信号回调）、`ui/main_window.py`（三 Dock + 中文菜单 + 状态栏）、`ui/strings_zh.py`（文案集中）、`ui/widgets/log_panel.py`（日志面板）；io/proc/features/batch/export 空包就位
5. tests/conftest.py：确定性 synthetic_raw 夹具（8导/250Hz/60s，ch0=10Hz α正弦、ch1=10Hz+50Hz 工频、3 事件）+ `real` 标记自动跳过机制；scripts/smoke_gui.py GUI 自检脚本

**验证执行与结果**

| 验证项 | 结果 |
|---|---|
| 治理文件齐全且与实际一致 | ✅ 6 文件 + .gitignore |
| conda env dlv 可用 | ✅ 版本见 STATUS.md（PySide6 6.11.0 + pyqtgraph 0.14.0 + mne 1.12.0 组合可用） |
| `pytest` | ✅ 3 passed（test_app_smoke.py） |
| `dataloadv` 启动出深色空窗口 | ✅ smoke_gui.py 输出：标题"DataloadV 电生理数据平台"、Dock=[工作区,处理,日志]、菜单=[文件,查看,处理,帮助]、Tab=1、日志面板在位 |
| 首次 git commit | ✅ `M0: 项目骨架+治理文件+conda环境+主窗口` |

**发现的问题与修正**
1. `mne.Annotations` 不接受 `verbose` 参数 → conftest.py 移除该参数（TypeError，测试期发现）
2. 冒烟脚本首版在 QTimer 回调里访问 `QAction.title`（应为 `.text()`）抛异常，且异常导致 `app.quit()` 未执行、进程悬挂 120s+ → 重写为 scripts/smoke_gui.py，**断言全部包 try、quit 放 finally**，任何回调异常都不再阻塞退出。教训已写入 HANDOFF.md 坑清单

**架构规则自查**
- core/ 无 Qt import ✅（logging_setup 的 QtLogHandler 仅做回调收集，UI 侧装配合）
- UI 无重计算 ✅（骨架期无计算；workers 通道就绪）
- 治理四件事齐做 ✅（本文件 + STATUS/TODO/HANDOFF 更新 + commit）

---

## M1 工作区 + EDF + 信号浏览器 — ✅ 完成（2026-08-18）

**做了什么**
1. `core/recording.py`：RecordingMeta(pydantic) / EventTable(ndarray 事件表) / Recording(惰性句柄 + get_window) / LoadPolicy / LoadedRawCache(全局 LRU，pin/逐出)
2. `core/workspace.py`：Workspace + ImportSource 两级模型、按 path 去重、JSON 原子写（tmp+rename）、当前工作区记忆
3. `io/`：BaseReader ABC（read_meta 仅头 / open / load_raw / sniff / 文件名实体猜测）、@register_reader 注册表、open_file/scan_folder（逐文件容错 + 进度回调）、sniffing.py（EDF 魔数，M2 扩充）、EdfReader（latin1 自动回退）
4. `ui/`：SessionState（信号中枢）、ImportController（文件/文件夹导入 → worker 扫描 → 状态栏进度 → 错误表对话框）、WorkspaceTree（树+筛选）、MetaTableView（排序/筛选表）、SignalBrowserView（窗口化读取 + min/max 峰值包络 + 通道开关 + 增益 + 事件线 + 跳转导航）、EventLane（全程事件概览 + 点击跳转）
5. 测试：test_readers_edf.py（合成 EDF 全流程 + 3 个真实羊文件 latin1 + 目录扫描 + 未知格式报错）、test_workspace.py（去重/删除/持久化往返/LRU 逐出与 pin）
6. 脚本：scripts/e2e_m1.py（幂等端到端：真实导入 sheep+S001 → 浏览 → 渲染 → 释放）

**验证执行与结果**

| 验证项 | 结果 |
|---|---|
| `pytest`（17 项，含 real 标记羊数据 5 项） | ✅ 17 passed |
| E2E：sheep 3 文件扫描 0 错误（latin1 生效） | ✅ |
| E2E：S001 14 文件扫描 0 错误 | ✅ |
| E2E：工作区入库 17 条，树/表刷新 | ✅ |
| E2E：羊 EDF 浏览 tab 打开、8 通道曲线有真实数据 | ✅ |
| E2E：S001R03 30 个事件读入，跳转后事件线渲染 | ✅ |
| E2E：关闭 tab 后数据释放 | ✅ |
| `scripts/smoke_gui.py` 回归 | ✅ SMOKE OK |

**计划偏离（实证驱动）**
1. **取消 .edf.event 边车解析**：实测 PhysioNet EDF 内嵌注释完整（S001R03 共 30 个 T0/T1/T2），边车为 WFDB 冗余副本。sidecar_events.py 从 M1 范围移除（plan.md 原有此项；若未来遇到只有边车的数据集再补，记入 TODO backlog）
2. **S001 每被试 14 个文件**（非 64）：e2e 断言按实测修正

**发现的问题与修正（全部有测试或 e2e 复现）**
1. LoadedRawCache 锁内逐出死锁：_evict_locked 在持锁下调 rec.unload()→forget() 再拿锁 → 重构为"锁内摘链选受害者 + 锁外 unload"
2. PySide6 worker 被 GC：信号连接不持有 Python receiver 引用，Worker 局部变量在 run 触发前被回收（线程空转、回调丢失）→ worker 挂到 thread 属性保活（thread._dlv_worker）
3. EventLane 构造期 self.scene() 为 None（PlotItem 未加入 GraphicsLayoutWidget 前无 scene）→ wire_click() 延迟到挂载后调用
4. load_raw 收到 str（meta.path）时 path.name 崩 → _read_edf_robust 统一 Path() 归一
5. base_meta 直接构造 RecordingMeta 缺必填字段（pydantic 校验失败）→ 重构为 common_meta_fields() 返回 dict、子类一次构造完整 meta
6. 主窗口 _build_menus 引用尚未创建的 self.importer → 初始化顺序调整
7. MainWindow 初版有两条重复的建 tab 路径 → 收敛为 recording_opened 信号单一通路

**架构规则自查**
- core/io 无 Qt import ✅（io 层仅 numpy/mne/pydantic）
- UI 不直接算：扫描/打开/加载全走 run_in_thread ✅；浏览器 _refresh_data 是像素级有界操作（窗口读取+抽取），属显示职责 ✅
- 跨线程只传纯 Python/mne 对象 ✅（open_file 返回 Recording 含 mne 句柄，纯数据对象）

**收尾四件事**：治理文件已更新（STATUS/TODO/HANDOFF）→ review.md 本节 ✅ → 上下文检查：本会话已执行一次压缩（压缩前全部关键状态已落盘治理文件），当前占用远低于 70% 阈值，无需再压 → git commit `M1: ...` ✅

---

## M2 读取器全覆盖（2026-08-18 完成）

**做了什么**
1. `io/mne_readers.py` 重写：`_MneRawReader` 模板基类（read_meta/open/load_raw/events_from_raw 全部通用实现），8 个子类只声明差异——EdfReader（latin1 回退）、BdfReader（stim auto）、GdfReader（事件套官方中文标签）、BrainVisionReader（.vhdr）、FifReader（epoched 文件/MaxShield 双中文提示重试）、EeglabReader、CntReader、EgiReader（.egi/.mff 目录）
2. `io/event_maps.py`：GDF 事件码官方中文映射 16 码（276/277/768/769-772/781/783/1023/1072/1077-1081/32766）——**码表以官方 desc_2a.pdf/desc_2b.pdf 原文为准**（pypdf 提取），未知码原样返回不猜
3. `io/bciciv_mat.py`：ds1（whosmat 判形 + 只 loadmat nfo/mrk 跳过 cnt；eval 无 mrk 时明确 note"评估集无标注"）；ds4（纯 whosmat 头解析 <1s；fs=1000 来自官方 desc_4.pdf；加载跳过 test_data；手套 5 指为 misc 通道）；GenericMatReader 识别 ds3 后明确拒绝（分段 MEG 记 backlog）、未知结构拒绝猜测
4. `io/table.py` CSV/TXT：分隔符嗅探（, ; \t | 空格）+ 数值性验证（≥90% 行全 float，挡住 SHA256SUMS.txt 类文件）+ FS_UNSET_NOTE 标记 → 主窗口 QInputDialog 询问采样率 → `core/fs_store.py` 记忆（~/.dataloadv/table_fs.json）
5. `io/hdf5.py`：零数据 IO 定位（3 层递归找 2-D 数值数据集、最大者胜、次大 >50% 拒绝歧义）；fs 从 attrs 四个别名或 FsStore
6. `io/sniffing.py` 补 GDF/BDF/HDF5/BrainVision 魔数；registry 支持 .mff 目录候选；base.py 文件名实体加 2b 三段式（B0303T）与 ds1 calib/eval 模式
7. **`workers/generic.py` 加 `_MainRelay`**（M2 最关键产品修复，见下）
8. 测试：synthetic_helpers.py（savemat 伪造 ds1/ds4/ds3/未知 mat + 4 分隔符 CSV + 可配 HDF5）+ test_readers_m2.py 26 项；scripts/e2e_m2.py 17 项端到端

**验证执行与结果**

| 验证项 | 结果 |
|---|---|
| `pytest` 全量（M1 17 + M2 新增 26） | ✅ 43 passed |
| 4.9GB dataset 全量扫描 <2min | ✅ **5.2s**（目标 120s） |
| 扫描识别 1606 条、错误仅 3 条已知结构（ds3×2 + SHA256SUMS.txt） | ✅（诚实报错而非误导入） |
| 每格式各开一个能绘图：羊 EDF / 2a GDF / 2b GDF / ds1 mat / ds4 mat / CSV | ✅ 六格式曲线均有真实数据 |
| 2a GDF 中文标签（769→提示：左手（类1）等 769-772） | ✅；2a 事件 603 个 |
| 2b GDF（B0303T）实体解析 + 781 BCI 反馈标签 | ✅ |
| ds1 mat：200 事件中文标签 + µV 标度正确 | ✅ |
| ds4 mat 134MB 加载 <10s | ✅ **0.2s**（跳过 test_data） |
| 元数据表 1606 行可用（1000+ 文件） | ✅ |
| 六 tab 全部关闭后数据释放 | ✅ |
| e2e_m1 回归（幂等总量断言修复后） | ✅ ALL OK 13 项 |
| smoke_gui 回归 | ✅ SMOKE OK |

**计划偏离（实证驱动）**
1. **GDF 码表来源改官方 PDF**：WebSearch 摘要多处错误（781 误作 correction/beep、1077 误作 eyes closed）——落盘官方 desc_2a/2b.pdf 用 pypdf 提取原文核实（781=BCI feedback continuous，1077-1081=眼动伪迹）。计划未预料，码表以实测原文为准
2. **ds1 评估集实际无 mrk 变量**（pipelineMotor yaml 所说"评估集有提示"与实物不符）：读取成功但 n_events=0，notes 明确说明，不猜标签
3. **ds4 train_data 是 double 非 int32、文件无采样率**：fs=1000Hz 取自官方 desc_4.pdf，读取器内固化并注释来源
4. **发现数据集混有 ds3 分段 MEG（S1/S2.mat）**：识别后明确拒绝（"分段结构，已记入 backlog"）——M2 范围不含 ds3，记入 TODO backlog
5. **BDF/CNT/EGI/BrainVision/EEGLAB 无真实数据**：无法按计划"每格式开真实文件"——以模板基类 + FIF 合成往返测试保证（五格式走同一模板代码路径，风险集中在 `_read_fn` 参数，见 TODO backlog 待真实数据冒烟）

**发现的问题与修正（全部有测试或 e2e 复现）**
1. **类属性函数变绑定方法**：`_read_fn = mne.io.read_raw_gdf` 使 `self._read_fn(path)` 实为 `read_raw_gdf(self, path)`（"File must be path-like, got GdfReader"）→ 全部 `staticmethod(...)` 包住
2. **e2e_m2 两次不定时挂起（0.1% CPU 空转）**：根因是产品缺陷——`on_error=lambda: QMessageBox.critical(...)` 普通函数连接在 **worker 线程**直连执行，非 GUI 线程弹模态框 macOS 上不定时冻结。三层修复：① 产品修复 `_MainRelay`（回调保证主线程）；② e2e patch QMessageBox；③ 连续 8/8+6/6 全过确认
3. **bciciv_mat 初版三处缺陷**（cnt 形状索引 [1]→[0]、无结构守卫致 ds1 读取器碰 ds4 文件、load_raw 重复解析 meta）→ 整文件重写（whosmat 让位守卫 + `_read_header` 复用）
4. **hdf5 read_meta 曾整读数据集**（`d[()]` 只为拿形状）→ `_locate`（只看 shape/attrs）与 load_raw 分离
5. **散文 txt 误判合法表格**（空格分列恰好一致）→ 嗅探后加数值性验证（≥90% 行全 float）
6. **savemat struct 含 None 字段 TypeError** → 合成夹具删 None 占位
7. **e2e 幂等**：重复运行 added=0 触发断言失败 → 总量断言（len(workspace)==1606）
8. **M1 旧测试与新读取器冲突**：note.txt 被 TableReader 接管报错（预期行为）→ 夹具改 note.md

**架构规则自查**
- core/io 无 Qt import ✅（新增 fs_store/bciciv_mat/table/hdf5/event_maps 仅 numpy/scipy/h5py/mne/pydantic）
- UI 不直接算：采样率询问后的 meta 更新是字段赋值；六格式打开仍走 `_open_recording_async`（run_in_thread + _MainRelay）✅
- 跨线程只传纯 Python/mne 对象 ✅（_MainRelay 槽参数 object/str，投递到主线程后才转 Python 回调）

**收尾四件事**：治理文件已更新（STATUS/TODO/HANDOFF：坑清单 11→17 条、架构树 M2 版、接手要点改 M3）→ review.md 本节 ✅ → 上下文检查：M2 开发期间本会话上下文已满并自动压缩过一次（压缩摘要续接完成全部 M2 工作与验证）；当前窗口以摘要重启，占用远低于 70% 阈值，无需再压——全部关键状态已落盘治理文件 → git commit `M2: ...` ✅

## M3 预处理链 + 预览（2026-08-18 完成）

**做了什么**：proc 层（ProcessingContext 副本隔离 + ProcStep ABC/STEP_REGISTRY/apply_pipeline 阶段检查 + 6 步骤：bandpass/notch/reref/resample/bads/epoching + step_to/from_dict 序列化）→ features/spectral.py mean_welch → UI（params_form pydantic 自动表单、pipeline_panel 步骤链编排、psd_view 原始 vs 处理后对比、epochs_preview 分段视图、signal_browser 坏道右键标记灰显+联动）→ 主窗口接线（处理菜单/预览 tab/分段预览 tab）→ tests +29 → e2e_m3。

**验证执行情况**

| 验证项 | 结果 |
|---|---|
| pytest 全量 | ✅ **72 passed**（M3 新增 29：proc 23 + UI 6；1.55s） |
| 表单往返不变量（6 步骤默认值 → 表单 → collect 全等） | ✅ |
| 陷波 50Hz 抑制 >10×（合成 ch1 30µV 工频） | ✅ |
| 副本隔离（from_recording 后原始 raw 逐位不变） | ✅ np.array_equal |
| 重参考后跨通道均值 ≈0（mne 1.12 返回副本陷阱已处理） | ✅ <1e-15 |
| 阶段守卫（分段后陷波 → 中文"需要连续数据"报错） | ✅ |
| 序列化往返（step_to_dict → step_from_dict 参数全等） | ✅ |
| **验收 1：羊 EDF 带通1-40+陷波50+平均参考 后 50Hz PSD 比值 <0.1** | ✅ **0.0001**（e2e_m3，全 GUI 路径） |
| **验收 2：A01T 事件分段（769-772，-1~4s）= 288** | ✅ **288**（pytest real 项 + e2e_m3 双验证） |
| 坏道标记联动（浏览器右键 → bads 步骤默认带入） | ✅（e2e 阶段 1） |
| 分段预览 tab（总数 + 每类计数 + 跨段平均波形） | ✅（e2e 阶段 2） |
| tab 关闭释放（预览/分段 tab teardown） | ✅ |
| e2e_m3 全量 | ✅ ALL OK（11 项） |
| e2e_m1 / e2e_m2 / smoke_gui 回归 | ✅ ALL OK / ALL OK / SMOKE OK |

**计划偏离（实证驱动）**
1. **notch 限 raw 阶段**（applies_to={"raw"}）：计划未预见 mne Epochs 无 notch_filter——分段前陷波是标准流程，顺序错误由 apply_pipeline 阶段检查给中文提示（不静默跳过）
2. **PSD 对比取前 120s**：超长文件全量 Welch 无谓耗时，120s 已覆盖工频/α 验证需求（参数在 _psd_job 内注释说明）
3. **分段预览为独立 EpochsPreviewView 而非复用浏览器**：epochs 是 3-D 数据，浏览器窗口化绘制模型不适用；跨段平均 + 每类计数已满足"确认分段正确"的验收意图
4. **预览 Recording 不入工作区**：meta.model_copy 换新 rec_id/format="预览"，避免污染持久化工作区（计划未明确，按"预览是临时视图"理解）

**发现的问题与修正（全部有测试或 e2e 复现）**
1. **mne 1.12 set_eeg_reference 返回副本非就地**（测试实测均值不归零 1.4e-5 → `inst is raw` 为 False）→ 用返回值写回 ctx.raw/ctx.epochs
2. **Epochs 无 event_name**（AttributeError）→ event_id 逆映射统计每类段数
3. **compute_psd fmax=None TypeError** → None 时显式传 Nyquist
4. **A01T "Event time samples were not unique"**：根因有二——① e2e 在表单构建后改 _steps 参数被 collect() 冲回默认（event_codes 空=全事件→同刻重复）；② 全码确有同刻事件 → add_step(**overrides) 先合后建表单 + mne.Epochs(event_repeated="drop")
5. **e2e PSD 比值恒 1.0000**：start_preview 后当前 tab 已切预览，"原始"取成了预览自身 → shared dict 保存原浏览器引用
6. **_on_select IndexError**：list.clear() 触发 currentRowChanged(-1) 用过期行号 → 行号边界守卫
7. **BadChannelsParams 空列表 validator 致 default_params() ValidationError**（表单往返测试暴露）→ 校验移到 apply() 给中文 StepError——**pydantic 步骤参数默认值必须可构造**是通用规则
8. **baseline (None,0)+tmin=0 单样本拒绝** → epoching 内自动转 (0.0,0.0)

**架构规则自查**
- proc/features 无 Qt import ✅（仅 numpy/mne/pydantic）；UI 新控件只编排不计算——预览/PSD 全部经 run_in_thread worker（_MainRelay 保护），apply_pipeline 在 worker 内执行 ✅
- 跨线程只传纯 Python/mne 对象 ✅（preview_ready 信号传 ProcessingContext——dataclass 持 mne 对象，符合规则 3）
- 副本隔离：预览全程在 raw.copy() 上，原始 Recording 逐位不动（pytest 断言）✅

**收尾四件事**：治理文件已更新（STATUS：M3 完成态+72 绿+实证结论 7 条+变更记录；TODO：M3 全勾、M4 置下一个；HANDOFF：坑清单 17→24 条、架构树 M3 版、接手要点改 M4）→ review.md 本节 ✅ → 上下文检查：本窗口自压缩摘要重启后连续完成 M2 收尾+DATA_NOTES 建立+整个 M3（proc/features/UI/测试/e2e），上下文占用已高，全部关键状态均已落盘治理文件——**建议用户执行 /compact 后再开 M4** → git commit `M3: ...`

---

## M4 — 特征 + 导出（2026-08-18 完成）

**做了什么**（按 TODO.md M4 节，特征范围=用户确认的"四层组合"）：

1. **proc/crop.py** 时间窗裁剪步骤（第③层）：CropParams（tmin≥0 / tmax=None=到结尾 / validator tmax>tmin）；raw 分支**绝对时间**（预检查越界给中文错；事件表不动——first_samp 机制保证绝对样本号仍成立）、epochs 分支**相对事件锚点**（无重叠预检查给"分段数为 0"中文错——mne 会先抛英文错，见问题 5）；applies_to={"raw","epochs"}
2. **features/base.py** FeatureExtractor ABC + FEATURE_REGISTRY + apply_features + 通道选择（DATA_CH_TYPES 白名单 {"eeg","ecog","seeg","meg","dbs"}；空=数据通道排除坏道；白名单空集回退非 misc）——与 proc/base.py **完全同构**（step_id property 别名使 ParamsForm 零改动复用）
3. **三提取器**：spectral.py 扩展 array_welch（scipy welch nperseg 沿 -1 轴广播，[ch,t]/[ep,ch,t] 一次算全部）+ BandPowerFeature（δθαβγ 标准频段 + "名字：起-止"自定义；trapz 积分 ×1e12→µV²；relative 除总功率 / log10 加后缀）+ WelchPsdFeature（曲线，**仅 raw 阶段**）；timedomain.py TimeDomainStatsFeature（rms_uv/var_uv2/mav_uv/ptp_uv/iqr_uv/zc_rate/kurtosis/skewness 8 统计量；过零带阈值滞回；µV 基准名字带单位）
4. **batch/results.py** FeatureTable：长表 COLUMNS 7 列（recording/subject/epoch_index/event_code/channel/feature/value）+ COLUMNS_ZH 中文表头 + to_wide（pivot_table **dropna=False**）+ summary_zh；epoch_index 惰性转 Int64
5. **UI**：pipeline_panel 加特征区（特征列表 + 添加特征菜单 + 「用当前显示窗口」预填按钮 + 「计算特征」按钮；步骤/特征互斥选择共用表单区，_write_back_form 切换前回写）；use_viewport_window 读 browser._visible_range → clamp [0,duration] round 2 → 更新最后一个 crop 或 add_step（第④层：**预填可改、不隐式绑定视口**）；feature_table.py 特征结果 tab（QAbstractTableModel + UserRole 数值排序代理 + CSV/HDF5/分段导出按钮 + sidecar + teardown）；main_window features_ready 接线开 tab、处理菜单 4 动作
6. **export/ 三模块**：features_io（CSV UTF-8 BOM + 中文表头；曲线宽表 <stem>_psd[N].csv 按频率轴分组；HDF5 /features 每列数据集 + /psd/<i>/{freqs,psd}）+ epochs_io（HDF5 /epochs/data f4 + times + event_codes + attrs；FIF mne 无损；均带回读）+ provenance（<名>.pipeline.json：app/created/pipeline/features/recordings/library_versions/extra）
7. **测试**：tests +50 = 122 绿（crop 6 / 三提取器 20 / FeatureTable+序列化 6 / 导出往返 12 / UI 11）；**e2e_m4 18 项 ALL OK**（四轮调试后，逐模块 patch + 轮询上限规约化）

**验证表**

| 验证项 | 结果 |
|---|---|
| pytest 全量 | ✅ **122 passed**（M3 的 72 + M4 新增 50） |
| **验收 1：单文件特征 CSV Excel 可开（BOM+中文表头）** | ✅ BOM `EF BB BF` + 表头「录制,被试,段序号,事件码,通道,特征,数值」+ 104 行 = 8 通道 × 13 特征（e2e 阶段 1/3） |
| **验收 2：epochs HDF5 回读形状一致** | ✅ A01T (288, 25, 2501) 往返一致；FIF 回读 288 段（e2e 阶段 4） |
| **验收 3：sidecar 合法且含管线** | ✅ features.pipeline.json 含 bandpass,notch,crop + 3 特征 + 文件清单 + 库版本 |
| 处理后 PSD 50Hz 峰消除（复用 M3 口径） | ✅ 50Hz 0.4 vs 10Hz 7130 µV²/Hz（陷波+带通后） |
| 「用当前显示窗口」预填 crop=视口 | ✅ [125,145]s（视口中点 20s 宽，非全长） |
| A01T 逐段特征 | ✅ 288 段 × 25 通道 × 2 频段 = **14400 行**；事件码 {769,770,771,772} 逐段带入 |
| 长表↔宽表互转 | ✅ to_wide 文件级+段级行共存（dropna=False） |
| 序列化往返（step/feature to/from_dict） | ✅ pytest 全等断言 |
| e2e_m1/m2/m3 + smoke_gui 回归 | ✅ ALL OK / ALL OK / ALL OK / SMOKE OK |

**计划偏离（实证驱动）**
1. **WelchPsdFeature 仅 raw 阶段**（applies_to={"raw"}）：计划未预见 epochs 曲线量爆炸（288 段 × 25 通道 = 7200 条曲线无浏览价值）；段级频谱用 BandPower 标量表达——M4 e2e 采纳此边界
2. **导出按钮集成在 FeatureTableView 而非独立 ExportDialog**：计划列了 dialogs/export，实现时发现导出与结果 tab 上下文强耦合（sidecar 要当次管线快照），独立对话框反而要回传状态——按钮+菜单三动作更直接
3. **2a GDF 25 通道（22 EEG+3 EOG）全部标 eeg**：类型白名单无法自动排除 EOG，默认全取（14400 行而非 12672）——排除 EOG 须在特征参数 channels 显式写 22 通道名（实证结论记 STATUS #2）；这是数据集元数据缺陷而非代码缺陷
4. **crop 在 epochs 阶段的语义是相对事件锚点**（mne Epochs.crop 行为），与 raw 的绝对时间不同——docstring 明确区分，UI 参数标题注明"相对事件"

**发现的问题与修正（全部有测试或 e2e 复现）**
1. **scipy.signal.welch 参数名 nperseg**（无下划线）→ TypeError 后改用（mne 风格是 n_per_seg，惯性坑）
2. **spectral.py 两处笔误**：错误类型注解 ExtractorResultR、description 内嵌英文双引号语法错 → 修正
3. **Epochs.crop 窗外先抛英文错**（"tmin must be less than..."）→ crop.py 加无重叠预检查（中文"分段数为 0…相对事件锚点"）放在 mne 调用**之前**
4. **pivot_table 默认 dropna=True 丢文件级行**：wide (0,5) 空 → to_wide 传 dropna=False
5. **Qt6 无 SortRole**：AttributeError → UserRole + setSortRole；且 DisplayRole 字符串排序 "10"<"2" 乱序 → data() UserRole 分支数值列返回 float；headerData/proxy.sort 枚举须显式（Qt.Orientation.Horizontal / Qt.SortOrder.AscendingOrder，PySide6 不接受 int 位置参数）
6. **e2e 第一轮卡死（CPU 0%）**：只 patch 了 main_window 的 QMessageBox，pipeline_panel/feature_table 的 from-import 独立引用未 patch → 真弹模态框阻塞 offscreen 事件循环 → **逐模块 patch（mw/ft_mod/pp_mod）+ 所有轮询加 tries 上限**（防永久挂死）——规约已写入 HANDOFF 坑 #31
7. **e2e getSaveFileName patch lambda 返回 bug**：条件表达式 True 分支返回字符串非 tuple → 改 def 返回 tuple
8. **e2e 阶段 2 IndexError**：羊"卧"文件 events 为空（onset[0] 越界）→ _center_at(duration/2) 中点定位替代事件定位
9. **e2e 阶段 4 取错特征 tab**：views[0] 取到阶段 1 羊的 tab → views[-1] 取最新 + recording_names() 校验含 "A01T"
10. **A01T 行数 14400 ≠ 预期 12672**：`Counter({'eeg': 25})` 实测——25 通道全标 eeg（偏离 3）→ 断言改 288×25×2 并记实证结论
11. **test_relative_powers_sum_to_one 和=0.99937**：标准频段 1-45Hz vs 分析带 0.5-45Hz 缺口 + 边界点 trapz 各半 → 容差 abs=5e-3 并注释原因
12. **test_mean_curve_peak_at_10hz 失败**：通道平均峰在 50.05Hz（30µV 工频 > 2×20µV α 合成功率）→ 改单通道指定测 α 峰（坑 #32）
13. **pipeline_panel 重写引入 _select_step_row 重复 addItem** → 拆分：add_step 内联 addItem+setCurrentRow；_select_step_row 只刷新文字+选中（viewport 更新场景）；_move_step 用 setCurrentRow

**架构规则自查**
- proc/features/batch/export 无 Qt import ✅（features/export 仅 numpy/scipy/pandas/h5py/mne/pydantic）；UI 新控件只编排不计算——特征计算/导出全部 run_in_thread worker（_MainRelay 保护）✅
- 跨线程只传纯 Python/mne 对象 ✅（features_ready 信号传 FeatureTable + ProcessingContext + dict 列表）
- data/ 只读 ✅（全部导出走 QFileDialog 用户路径 + tempfile）；配置 ~/.dataloadv ✅

**收尾四件事**：治理文件已更新（STATUS：M4 完成态 + 122 绿 + e2e_m4 18 项数字 + 实证结论 8 条 + 变更记录；TODO：M4 全勾含四层决策原文、M5 置下一个；HANDOFF：坑清单 24→32 条、架构树 M4 版、接手要点改 M5）→ review.md 本节 ✅ → 上下文检测：本会话自压缩摘要重启后连续完成整个 M4（约 20 个文件创建/修改 + 4 轮 e2e 调试），占用已高，全部关键状态均已落盘治理文件——**建议用户执行 /compact 后再开 M5** → git commit `M4: 特征+导出——crop时间窗+3提取器+FeatureTable长表+特征面板(视口预填)+CSV/HDF5/FIF导出+sidecar`

## M5 — 批处理 + 扩展格式 + 收尾（2026-08-18 完成，v1 收官）

### 做了什么

**批处理引擎（batch 层，纯 Python——架构规则 #1 优先于 plan.md 原文的 BatchEngine(QObject)）**
- `batch/jobs.py`：PipelineSpec（steps/features 的 dict 快照 + `resolved_steps()/resolved_features()` 启动前校验 + summary_zh）；JobSpec（paths/pipeline/n_workers 1-8 默认 2/导出三参）；FileStatus 枚举 + FileResult（path/recording/status/duration_s/n_values/error/**log 逐文件日志**）；BatchSummary（n_ok/n_failed/n_cancelled/n_values + summary_zh）
- `batch/engine.py`：`run()` 阻塞整体（resolved 校验 → ThreadPoolExecutor 默认 2 线程 → 汇总 → _export）；`_process_one()` 单文件全链：open_file(PRELOAD) → FS_UNSET_NOTE 检查（中文"请先在浏览 tab 打开设定采样率"）→ from_recording → **LoadedRawCache.pin**（防多 worker 并发整载时 LRU 互逐）→ apply_pipeline/apply_features（cancel_check=取消事件）→ 锁内 add_result → unpin+unload；单文件失败记 FileResult(failed, 中文 error, log) **继续下一文件**；回调（on_progress/on_file_done）在 worker 线程执行、`_safe_call` 兜底
- `proc/base.py` + `features/base.py`：新增第三参 `cancel_check`（逐步骤/逐特征检查，为真抛新 `PipelineCancelled(StepError)`——取消不落 error 字段、有独立状态）
- `core/app_settings.py`：AppSettings（n_workers/cache_gb/export_dir）pydantic + 临时文件 rename **原子写** + `apply()` 热生效（直接写 LoadedRawCache.instance().byte_budget）+ 损坏文件容错回默认

**UI（全部只编排不计算）**
- `ui/widgets/batch_view.py`：BatchProgressView（逐文件表/进度条/取消按钮；状态着色——成功绿/失败红/取消灰；失败行 tooltip=错误原因；**双击任意行弹 FileLogDialog** 看该文件逐行日志含【错误】行）；cancel_requested 信号只转发
- `ui/dialogs/batch_dialog.py`：两页（选择：过滤框+可勾选清单+全选/全不选+管线摘要+导出组 CSV/H5/文件名/目录/线程 SpinBox ↔ 运行页）；**线程模型：引擎回调 worker 线程 → 只塞 queue.Queue → 主线程 QTimer 150ms 事件泵（单轮上限 200）→ 喂视图**——UI 全程响应；运行前五重校验（无文件/管线非法/特征空/无导出目录）全中文 QMessageBox；closeEvent 运行中=请求取消
- `ui/dialogs/settings_dialog.py`：三字段表单（workers/cache 附当前生效值/export_dir+浏览）→ save+apply
- 主窗口：文件菜单「设置…」、处理菜单「批处理…」、`_on_batch_finished` 开 FeatureTableView 结果 tab（题"批处理 · {name}"，pipeline_dicts/feature_dicts 注入保证 sidecar 同源）

**扩展格式（import-guard 可选依赖）**
- `io/neo_reader.py`：_NeoRawReader 模板（`requires_extra="neo"`；make_rawio→parse_header；header 是 **numpy structured array** 按**字段名**取行；`_stream_index` 选点数最多的流；`_stream_channels` 按 stream_id 过滤；read_meta 零数据 IO；load_raw 整载+逐列单位换算（_UNITS_TO_V，rescale 后是通道单位浮点）+ (n_times,n_ch)→转置；extract_events 失败降级空表）+ BlackrockReader（.nev/.ns1-.ns6，全名失败回退基名）+ OpenEphysReader（.continuous→parent 目录）+ IntanReader（.rhd/.rhs）
- `io/nwb_reader.py`：`requires_extra="pynwb"`；`_find_series`（acquisition→processing 找 ElectricalSeries，无→中文拒绝）；read_meta 零数据 IO（shape 是 HDF5 属性）；load_raw（data×conversion+offset→伏特；(n_times,n_ch)/(n_ch,n_times) 双向 _orient 长轴为时间）；事件 trials 优先→epochs→空；通道名 `region["label"][:]`（colnames 是 None 不可判）

**README 重写**：v1 功能全览（数据管理/波形浏览/预处理/特征/批处理/导出/设置六块）、快速开始+典型流程五步、验证口径（pytest 137 + e2e_m1–m5）、技术栈加 neo/pynwb（可选）。

### 验证

| 验证项 | 结果 |
|---|---|
| pytest 全量 | ✅ **137 passed**（M4 的 122 + M5 新增 15：batch 10 + readers 5） |
| **验收 1：45 个 2b GDF 批处理全程 UI 响应** | ✅ e2e_m5：45 真实 + 1 损坏（patch 注入）→ **45 成功 1 失败不杀整批**，78240 行特征，8.5s（2 worker）；UI 心跳计时器 86 次 ≈9s **全程响应**（事件循环未被占住） |
| **验收 2：中途取消有效** | ✅ 第二批不导出、等首个文件完成后取消 → 整批 cancelled、成功 4/取消 41/失败 0（未开始文件全为「已取消」，绝无跑完） |
| **验收 3：错误可查** | ✅ 失败行红显「失败」+ tooltip=中文原因；FileLogDialog 含【错误】行与完整逐文件日志 |
| 分段/特征正确性 | ✅ 每文件 ≥1440 值（T=120 段×6 导×2 频段；E 文件 783:160 段）；长表覆盖 45 录制；summary.n_values=逐文件之和 |
| CSV/sidecar 导出 | ✅ CSV BOM+中文表头 78240 行与特征表一致；sidecar 含 epoching+bandpower(params.bands=α,β)+45 文件+extra.batch(n_files=46/n_workers=2/files_written) |
| 批处理结果 tab | ✅ 主窗口开「批处理 · e2e_m5_features」，长表可排序浏览 |
| 扩展格式注册 | ✅ blackrock/openephys/intan/nwb 四读取器注册并接管扩展名 |
| NWB 真实往返（pytest） | ✅ pynwb 写出（Subject/ElectricalSeries 4 导 250Hz 20µV α/trials）→ read_meta（0 IO）/load_raw（幅值一致）/open（事件+被试）全链 |
| neo 模板逻辑（pytest 桩） | ✅ structured array 头、选点数最多流、uV/V 逐列换算、(2,4) 转置、事件时间戳→秒 |
| 设置 | ✅ 往返持久化+apply 热生效+损坏文件容错（pytest） |
| 回归 | ✅ e2e_m1 13 / e2e_m2 17 / e2e_m3 11 / e2e_m4 18 项 + smoke_gui 全绿 |

### 计划偏离（实证/规则驱动）

1. **BatchEngine 纯 Python 非 QObject**：plan.md 原文写 BatchEngine(QObject)+信号，但硬性架构规则 #1 禁止 batch 层 import Qt——规则优先。改纯 Python 引擎（回调在 worker 线程执行）+ UI 侧 queue.Queue + QTimer 150ms 事件泵转主线程，同时满足规则与"队列连接回主线程"的 plan 意图（e2e 心跳 86 次证明 UI 响应不受损）
2. **Intan 用 neo.rawio.IntanRawIO 而非 vendored read_intan.py**：plan 说 vendored（1000+ 行第三方代码）；neo 依赖已在场（Blackrock/OE 同源），依赖统一、零维护面——弃 vendored
3. **e2e 分段码含 783**：原按 plan 验收思路 769/770，实测 2b E（评估）文件这两码全 0（未知类 cue 是 783）——同一码表必须含 783 才能跑通 45 文件（T=120/E=160 段）；记 STATUS 实证结论 M5-#1
4. **README 无截图**：headless 开发环境无截图条件，改为文字典型流程五步（plan 说 M5 补截图，验收不受影响）
5. **neo 用 pip、pynwb 用 conda**：conda search 实证 neo 不在 conda-forge → pip 例外（用户 conda 优先原则的边界案例）；pynwb dry-run 干净 → conda——安装命令已记 HANDOFF §环境搭建

### 发现的问题与修正（全部有测试或 e2e 复现）

1. **mne 无 `write_raw_edf`**（引擎冒烟 AttributeError）→ 查 tests/test_readers_edf.py 惯例改 `raw.export(path, fmt="edf", overwrite=True)`
2. **engine.py 重命名 `_finish`→`_stamp` 漏改调用点**：顶部取消分支仍调旧名，AttributeError 被意外异常分支吞掉转 failed——单测 test_engine_cancel_after_first_file 抓到 → 改 `_stamp(result_for(path, CANCELLED, log=logs), t0)`
3. **jobs.py 初版 n_values 占位写错**（`n_new - sum(1 for _ in ())` 无意义表达式）→ 重写为直接 `len(result.scalars)`、删多余 `_count_scalar_rows` 与无用参数
4. **batch_view `_results` 未初始化** → __init__ 补 `self._results: dict = {}`
5. **batch_dialog 信号未声明 + Qt 魔数**：`batch_finished` 忘声明（运行期 AttributeError）；`0x0100`/`|0x02` 魔数——**0x02 是 ItemIsEditable 不是 UserCheckable**（勾选框点击进编辑的静默错行为）→ 全枚举 `Qt.ItemDataRole.UserRole`/`Qt.ItemFlag.ItemIsUserCheckable`/`Qt.CheckState.*`
6. **neo_reader 初版两处结构错**：load_raw 返回 (raw, events) 元组破坏 Recording.ensure_raw 契约；header 行类型靠猜 → 查 baserawio 源码确认 structured array + 字段名访问，整文件重写（open() 单独走 make_rawio+extract_events 不触信号数据）
7. **pynwb 4.x 测试三轮**：add_electrode location 必填（""被拒）→ "皮层"；电极表默认无 label 列 → add_electrode_column；`region.colnames` 是 None 抛 TypeError 被吞 → 探测后改 try/except 直取 `region["label"][:]`
8. **桩 rawio 流/通道不配对**（n_streams=1 时流 id 挂错）→ 桩改 `picked_sid = streams[-1][1]` 让通道挂将被选中的流；转置断言 d[1,0] 写错（应为 ch_V 首样本 1.0）；桩测试路径需 `path.touch()`（common_meta_fields 要 stat）
9. **e2e 迷你预跑抓到真接线缺失**：_new_dialog 没连 `win._on_batch_finished` → 批处理结果 tab 不开 → 补连线（同菜单路径）
10. **e2e 第一轮崩溃丢输出**：`dlg._btn_cancel` 属性名错（按钮在 BatchProgressView 上）+ stdout 块缓冲把已过检查项全吞 → 改 `dlg._progress._btn_cancel` + check() 一律 `flush=True`
11. **e2e sidecar 断言写错**：`bands=["alpha","beta"]` 是**一个**特征（双频段）非两个特征——断言改为语义更强的 feature 链 + params.bands + extra.batch.n_files 校验

### 架构规则自查

- batch/proc/features/export/io/core 无 Qt import ✅（grep 复核，仅 docstring 提及"禁止 import"字样）；BatchEngine 纯 Python ✅
- UI 只编排不计算 ✅（引擎在 worker 线程；事件泵只搬运事件；取消按钮只调 engine.cancel() 立即返回）
- 跨线程只传纯 Python/mne 对象 ✅（queue.Queue 事件是 tuple/FileResult——pydantic 纯 Python）
- data/ 只读 ✅（导出去用户目录/TMP；设置写 ~/.dataloadv，e2e 用 SETTINGS_PATH 指向 TMP 防污染）

**收尾四件事**：治理文件已更新（STATUS：M5 完成态 + 137 绿 + e2e_m5 19 项数字 + 实证结论 7 条 + 变更记录；TODO：M5 全勾含架构决策原文、backlog 补 Blackrock/OE/Intan/NWB 实测项；HANDOFF：环境加 neo pip/pynwb conda 分渠道命令、版本表、架构树 M5 版、坑清单 32→37 条、接手要点改 v1 收官）→ review.md 本节 ✅ → 上下文检测：本会话自压缩重启后完成整个 M5（约 14 个文件创建 + 4 个修改 + 3 轮 e2e 调试），占用已高，全部关键状态均已落盘治理文件——**建议用户执行 /compact** → git commit `M5: 批处理+扩展格式+设置——BatchEngine纯Python线程池/取消/逐文件日志+对话框(队列事件泵)+neo(Blackrock/OE/Intan)+NWB+README；v1 收官`

## M6 — 浏览体验优化（2026-08-18 完成，用户实测 v1 后三点反馈驱动）

### 背景与做了什么

用户反馈：①阅览界面通道名重叠、名末有"…"截断，且无每通道幅值标注（附截图；实测 2b GDF
通道名本身干净，非数据问题）；②需要一屏时长选项 + 滚轮/方向键调窗口 + 首末翻屏按钮；
③浏览/PSD 等绘图背景换白、配色随之调整。用户经问答确认两项决策：**滚轮=平移**
（缩放交给时长选项/右键框选/Ctrl+滚轮）、**全局换白**（不加主题开关）。

1. **通道标签重构（重叠/截断的根因修复）**：旧实现把全部通道名 `setTicks` 进 y 轴固定刻度，
   且主图未锁 y 轴——pyqtgraph 默认滚轮**同时缩放 x/y**，滚几下通道刻度挤成一团、长名截断。
   改为：左轴隐藏；每通道一条 `pg.TextItem` 内嵌在曲线行左端（半透明白底压波形上可读、
   随视口/间距估计/通道显隐联动）——任意导联数（含 64 导）不重叠不截断显全名；
   `setMouseEnabled(x=True, y=False)` 锁死 y。
2. **滚轮/键盘交互**：`_PanViewBox(pg.ViewBox)` 重载 `wheelEvent`——竖滚=时间平移
   （步长一屏 10%，向上=更早）、**Ctrl+滚轮**=以鼠标位置为锚点缩放（×1.25/档）；右键拖框缩放
   保留。键盘 ←/→=翻屏、Home/End=首末屏、↑/↓=增益 ±1（StrongFocus + `_gfx` 焦点代理）。
3. **窗口导航**：工具栏 `|◀ 最前 / ◀ 上一屏 / 一屏时长下拉（1/2/5/10/30/60 s 预设+可编辑自定义）
   / 下一屏 ▶ / 最末 ▶|`；翻屏步进 **0.9 屏**（留 10% 上下文）；`_set_x_range` 统一 clamp
   [0,duration]；时长变化保持视口中心；视口实际宽度回写时长框（拖框/Ctrl 滚轮后保持一致）。
   新锚点方法：`_set_window_s/_page/_go_edge`（供测试断言）。
4. **幅值标尺**：右上角固定 60px 竖线 + "X µV" 标注；换算 `像素长度 ÷ 增益 → 真实幅度 →
   _nice_number`（1/2/5×10^k；恒等式 `_nice_number(v/10)==_nice_number(v)/10` 保证增益联动
   断言稳定）——堆叠显示全通道共享比例尺（EEG 浏览器标准做法），随增益/视口动态更新。
5. **浅色主题**：`main_window` 一处 `pg.setConfigOptions(background="w", foreground="k")`；
   配色集中调整：波形曲线 `#7fbfff`→`S.SIGNAL_PEN_COLOR(#1f77b4)`（浏览器/toggle_bad/
   epochs_preview 三处统一走 S 常量）、PSD `_SERIES_COLORS` 首色 `#e8e8e8`→`#d62728`
   （原始=红、处理后=蓝——**旧首色在白底上完全不可见，换色是功能修复**）、事件调色板黄
   `#e0e05c`→`#b8860b`（暗金）、事件图例 `#cccccc`→`S.PLOT_TEXT_COLOR(#333333)`、
   batch 状态色加深 `#1e8e3e/#c5221f/#666666`（白表格底可辨）；坏道 `#8a8a8a`、网格保留。
6. **两个存量增益 bug 修复（M6 测试暴露，均自 M1 潜伏）**：
   - ①增益只乘**间距**不乘波形：`out_v + idx*spacing*gain` → 修正为 `out_v*gain + idx*spacing`
     （gain>1 时上方通道飞出固定 yRange、gain<1 时全部叠回基线，与"只缩波形不挪基线"语义相反）；
   - ②`self._gain` 初值 1.0——它存的是**滑杆刻度值**（增益=10^(x/10)），滑杆初始 0 而字段却是
     1.0 → 首帧起一直带 10^0.1≈**1.26× 隐形增益**。

### 验证

| 验证项 | 结果 |
|---|---|
| pytest 全量 | ✅ **150 passed**（137 + 新 13：tests/test_ui_browser_m6.py——标签全名且左轴隐藏/标签随视口/增益 ×10 且 yRange 纹丝不动/标尺 µV 且随增益变化/_nice_number 阶梯+恒等式/一屏时长保持中心/翻屏 0.9 屏/首末屏/越界 clamp/时长框回写+无效输入忽略/滚轮平移 y 不动/Ctrl 滚轮宽度 0.8×） |
| e2e_m1 扩为 18 项 | ✅ ALL OK（+5 项 M6 断言走真实羊 EDF 全路径：通道标签全名内嵌/一屏时长设 5s/下一屏步进 0.9 屏/最末屏 [dur-w,dur]/幅值标尺标注 µV） |
| 回归 | ✅ e2e_m3 11 项 ALL OK（预览/PSD 压制比 0.0001/分段 288）+ smoke_gui SMOKE OK |
| 白底对比度 | ✅ 全部换色在白底可辨（PSD 旧首色 #e8e8e8 白底不可见为功能缺陷，本次一并消除） |

### 发现的问题与修正

1. **增益初值 bug 的侦破**：新测试断言幅度 ×10 实得 7.94——三轮诊断（minmax_decimate 间碟
   对照/纯 pyqtgraph 最小复现排除 setData 改写/包装 `_refresh_data_inner`）定位
   yData = out_v × 1.2589 = 10^0.1：`_gain` 字段语义是滑杆值却初始化成 1.0。首帧隐形 1.26×
   因幅度差异小从未被察觉，属 M1 存量问题，本次一并修复并加回归断言。
2. e2e_m1 追加断言时 Edit old_string 漏了 `v = sheep_views[0]` 行不匹配 → 重读源文件按精确文本插入。

### 架构规则自查

- 计算层六包无 Qt import ✅（M6 只改 ui/、tests/、scripts/e2e_m1.py）
- UI 只编排不计算 ✅（标签/标尺为绘制层；所有导航只动视口，数据仍走 get_window 窗口化读取）
- 跨线程只传纯 Python/mne 对象 ✅（未新增线程路径）
- data/ 只读 ✅（测试用 tmp_path FIF 往返；e2e 沿用真实数据只读）

**收尾四件事**：STATUS（M6 完成态/150 绿/e2e_m1 18 项/实证结论/变更记录）→ TODO（M6 小节全勾 + backlog 两项）→ HANDOFF（坑 #38/#39、接手要点）→ MANUAL（§2.2/§2.3/§3.1/§3.5/§3.7/§5.3 白底与交互表重写）→ README（浏览行/验证口径）→ review.md 本节 → 上下文检测 → git commit

---

## M6.5 — 读取派发魔数校验（2026-08-24 完成，用户发现羊数据实为 BDF）

### 背景与根因

用户更新 sheep3 数据时发现：`data/sheep`、`sheep2`、`sheep3` 共 6 个 `.edf` 文件**内容全是
BDF**（文件头 `\xffBIOSEMI`，BioSemi 24-bit）。此前 open_file 只按扩展名派发 → EdfReader →
`read_raw_edf` 把 24-bit 样本按 16-bit 解码：

- **样本数虚增 1.5×**（卧文件 180 s 读成 270 s——45000×3 字节按 2 字节切 = 67500"样本"）
- **全部数值错位**（字节流错切片，±4096 µV 的伪范围）——M1–M6 所有羊数据的波形/PSD/滤波/特征
  均为伪数据
- 诊断途中实锤 `read_raw_bdf` 也打不开这些文件：mne 公共入口 `_check_args` **按扩展名硬拒绝**
  （"Only BDF files are supported, got edf"）——mne 内部同样信扩展名
- data/ 全量魔数普查：仅这 6 处内容/扩展名不符，其余数据集全部一致

### 改动（6 文件 + 治理）

| 文件 | 改动 |
|---|---|
| `io/sniffing.py` | **修 EDF 分支 off-by-one**：版本域是字节 0–7 共 8 字节，旧代码查 `head[1:9]` 把患者域首字节卷进来——真 EDF（患者域不以空格/B 开头）嗅探漏判返回 None（反向冒烟时暴露：真 EDF 改 .bdf 后缀仍被 BdfReader 错读）。改为严格 `head[:8] == b"0"+7空格`；删除无引用且语义错误的 `is_edf`（".edf 直接信扩展名"正是本 bug 的假设） |
| `io/registry.py` | 新 `_dispatch_readers`：**魔数内容优先派发**——嗅探出 EDF/BDF/GDF/BrainVision（可唯一定位读取器）时以内容为准，扩展名不符记 warning；**且不让扩展名候选兜底**（内容明确时按扩展名再试只会错位解码）。"hdf5" 是家族签名（NWB/Intan/通用同头）不参与，细分仍靠扩展名 |
| `io/mne_readers.py` | `_read_edf_robust` → 通用 `_read_mne_robust`：①扩展名不符被 `_check_args` 拒时**file-like 对象重读同一公共入口**绕过（用户指定方案：read_raw_bdf 自 MNE 1.10 官方支持 file-like、edf/gdf 同路径实测可用，不直接实例化 Raw* 构造器；file-like 强制 preload=True，仅误标文件承担整载）；②latin1 回退保留（file-like 路径上撞 invalid byte 时 seek(0) 回卷重读）。配套 `_detach_file_handles`：读后剥离 mne 内部两处句柄残留（`_raw_extras[*]["blob"]` + `_init_kwargs["input_fname"]`，init_kwargs 回填真实路径）——否则 `raw.copy()`/deepcopy 抛 "cannot pickle '_io.BufferedReader'"（e2e_m3 预览链路第一个撞上，pytest 156 绿没拦住——单测没覆盖误标文件 raw 的 copy 路径，已补回归测试）。模板基类加 `_robust` 声明，EDF/BDF/GDF 三读取器统一走它 |
| `core/workspace.py` | `add_metas` 重复导入时**保留 rec_id、用新扫描结果刷新内容**（此前保留旧条目——重导入无法修正旧 meta；rec_id 绑定文件而非某次扫描） |
| `tests/test_readers_edf.py` | 羊测试重写为 `test_sheep_mislabeled_bdf`（format=BDF + 三文件真实时长 180/182/222 s）；新增魔数表/反向误标（真 EDF 存 .bdf）/内容优先不兜底/latin1 回归/**组合回退（错扩展名+非 UTF-8 注释叠加）**/**file-like raw 可 copy（deepcopy 回归）**六测 |
| `tests/test_workspace.py` | 新增重导入刷新测试（rec_id 稳定 + 内容更新） |
| `scripts/e2e_m1.py` | 羊段加"按 BDF 解码"断言（format=BDF、dur=180）→ 19 项 |

### 用户追加两问（同日闭环）

1. **羊标注通道是否非 UTF-8**：逐字节核查 6 个羊 BDF 的 "BDF Annotations" 通道——**全为纯 ASCII**（高位字节集为空），内容是标准 TAL 时间戳 `+0/+1/+2…\x14\x14\x00`（每秒一条**空文本**注释）；满足 UTF-8，默认 utf8 编码零报错。**"羊需要 latin1"确系 M1 按 EDF 误解码 BDF 的副产品**（错位字节被当注释文本），无需改码——latin1 回退机制保留给真 latin1 老文件（合成回归测试锁定）。零事件（e2e_m2 断言）是空注释的数据属性，非读取 bug。
   核查顺带实证 EDF/BDF 头布局（三次偏移猜错后）：记录数@236/每记录秒@244/ns@252，信号子头**字段主序**（samples 区在 `256+ns*216`），非每通道 256B 块——HANDOFF 坑 #44。
2. **读取方式改 file-like + read_raw_bdf**（用户建议）：如上表——弃 Raw* 直接构造，改 file-like 走公共入口；代价 preload=True 仅误标文件承担；连带发现并修复 deepcopy 残留句柄坑。

### 验证

| 项 | 结果 |
|---|---|
| pytest | ✅ 157 绿（150 + 净增 7：魔数表/反向误标/不兜底/latin1 回归/重导入刷新/组合回退/file-like raw 可 copy；羊参数化重写不增减） |
| e2e_m1 | ✅ 19 项 ALL OK（新断言 format=BDF, dur=180.0） |
| e2e_m2/m3/m4/m5 + smoke | ✅ 全部 ALL OK / SMOKE OK（羊文件作为预览/管线输入自动走 BDF 路径；m3 曾因 deepcopy 坑挂死，修复后 ALL OK——288 分段/50Hz 压制 0.0137 全对） |
| 双向误标 | ✅ 假 EDF→BDF 读取正确；真 EDF 改 .bdf 后缀→EDF 读取正确（file-like 绕过路径） |
| 标注通道编码 | ✅ 6 羊文件标注通道 UTF-8 判定全过（纯 ASCII）；utf8 默认编码读取零报错零事件 |
| PhysioNet 回归 | ✅ 64 导/30 事件不变（标准 EDF 扩展名与内容一致，不受影响） |

### 架构规则自查

- 计算层六包无 Qt import ✅（改动全在 io/、core/workspace、tests/、scripts/）
- UI 只编排不计算 ✅（未动 UI 层）
- 跨线程只传纯 Python/mne 对象 ✅（未新增线程路径）
- data/ 只读 ✅（对照实验复制到 /tmp 改名，原始 6 文件未动一字节）

**收尾四件事**：STATUS（157 绿/e2e_m1 19 项/实证结论/变更记录）→ TODO（M6.5 小节全勾）→ HANDOFF（坑 #40–#44、pytest 157）→ DATA_NOTES（羊三目录 BDF 实锤 + 真实时长表 + latin1 坑再认识 + 标注通道核查结论）→ MANUAL/README → review.md 本节 → 上下文检测 → git commit（用户指令后）
