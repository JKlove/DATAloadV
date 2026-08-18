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
