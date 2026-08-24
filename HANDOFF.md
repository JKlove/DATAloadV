# HANDOFF — 接手指南

> 任何人（包括未来的自己或 AI 助手）凭本文件 + plan.md + STATUS.md + TODO.md 即可接手继续开发，无需翻对话记录。

## 项目是什么

DataloadV：电生理数据桌面平台（PySide6 + pyqtgraph + MNE）。读取（EDF/GDF/MAT/BDF/BrainVision/FIF/EEGLAB/CNT/EGI/NWB/Intan/Open Ephys/Blackrock/CSV/HDF5）→ 管理 → 波形浏览 → 预处理 → 简单特征 → 批处理 → 导出。完整方案见 `plan.md`。

## 环境搭建（从零复现）

```bash
# 1. conda 环境（专用，不要用 py310lg——那是 pipelineMotor 的冻结研究环境）
source ~/miniconda3/etc/profile.d/conda.sh
conda create -y -n dlv python=3.10
conda activate dlv

# 2. 科学/GUI 栈 —— conda-forge 优先（用户要求 conda 优先装包）
conda install -y -c conda-forge "numpy=1.26.4" "scipy>=1.10" "pandas>=2.0" \
    "h5py>=3.8" "pydantic>=2.4,<3" "PySide6>=6.5,<7" "pyqtgraph>=0.13.7" \
    pyyaml pytest pytest-qt

# 3. MNE 及个别 conda 缺失的包 —— pip 补装（用户确认 MNE 用 pip）
pip install "mne==1.12.0" edfio

# 4. M5 扩展格式依赖 —— 分渠道（2026-08-18 实测：conda search 证明 neo 不在
#    conda-forge → pip 例外；pynwb 在 conda-forge 且 dry-run 干净 → conda）
conda install -y -c conda-forge "pynwb>=3.0"
pip install "neo>=0.13"

# 5. 本包可编辑安装（含 dev 依赖）
pip install -e "/Users/huyingbing/VSproject/intervention BCI/DataloadV[dev]"
```

**实际安装后的版本**（2026-08-18 M0 安装实测 + M5 追加，与 STATUS.md 保持同步）：

| 包 | 版本 | 来源 |
|---|---|---|
| Python | 3.10 | conda env `dlv` |
| numpy / scipy / pandas | 1.26.4 / 1.15.2 / 2.3.3 | conda-forge |
| PySide6 / pyqtgraph | 6.11.0 / 0.14.0 | conda-forge |
| mne / edfio | 1.12.0 / 0.4.16 | pip |
| pydantic / h5py | 2.13.4 / 3.16.0 | conda-forge |
| neo / pynwb（M5，可选） | 0.14.5 / 4.1.0 | pip / conda-forge |

> neo/pynwb 是**可选依赖**（import-guard）：缺失时应用照常运行，只是 NWB/Blackrock/OE/Intan 格式不可用。

## 运行与测试

```bash
conda activate dlv
dataloadv                                    # 启动应用（或 python -m dataloadv）
pytest                                       # 全部单测（M6.5：157 passed，含 real 数据项）
pytest -m real                               # 仅真实数据冒烟（data/sheep 缺失自动跳过）
python scripts/smoke_gui.py                  # GUI 冒烟：真窗口启动自检后自动退出
python scripts/e2e_m1.py                     # M1 端到端：真实导入→浏览→渲染→释放（幂等，可反复跑）
python scripts/e2e_m2.py                     # M2 端到端：4.9GB 扫描+六格式打开（幂等，可反复跑）
python scripts/e2e_m3.py                     # M3 端到端：预览/PSD 压制/分段/tab 释放（幂等，可反复跑）
python scripts/e2e_m4.py                     # M4 端到端：特征计算/视口预填/导出/分段回读（幂等，可反复跑）
python scripts/e2e_m5.py                     # M5 端到端：45 文件批处理+取消+扩展格式（幂等，可反复跑）
```

## 架构导览（M5 后的实际结构，v1 收官）

```
src/dataloadv/
├── app.py / __main__.py     # 入口：QApplication、高 DPI、excepthook→日志
├── core/                    # 计算层核心（禁止 import Qt）
│   ├── recording.py         # Recording/RecordingMeta/EventTable/LoadPolicy/LoadedRawCache（M1）
│   ├── workspace.py         # Workspace + ~/.dataloadv/ JSON 持久化（M1）
│   ├── fs_store.py          # FsStore：CSV/HDF5 采样率询问记忆（~/.dataloadv/table_fs.json）（M2）
│   └── app_settings.py      # AppSettings：n_workers/cache_gb/export_dir（临时文件+rename 原子写；apply() 热生效）（M5）
├── io/                      # 读取器层（禁止 import Qt）——注册表模式，每格式一个 Reader
│   ├── base.py              # BaseReader ABC：read_meta 仅头/open/load_raw/sniff/common_meta_fields/filename_entities
│   ├── registry.py          # @register_reader + open_file/scan_folder（容错+进度回调+.mff 目录候选）；_dispatch_readers 魔数内容优先派发（M6.5）
│   ├── sniffing.py          # 魔数嗅探（EDF/GDF/BDF/HDF5/BrainVision）——版本域严格前 8 字节（坑 #41）
│   ├── mne_readers.py       # _MneRawReader 模板基类 + 8 子类（EDF/BDF/GDF/BV/FIF/EEGLAB/CNT/EGI）
│   ├── bciciv_mat.py        # BCI-IV ds1/ds4 专用 + 未知 mat 拒绝猜测（多候选让位链）
│   ├── event_maps.py        # GDF 官方事件码→中文标签（16 码，desc_2a/2b.pdf 原文核实）
│   ├── table.py             # CSV/TXT：分隔符嗅探+数值性验证+FS_UNSET_NOTE 询问标记
│   ├── hdf5.py              # 通用 HDF5：零数据 IO 定位 2-D 信号集，歧义拒绝
│   ├── neo_reader.py        # _NeoRawReader 模板（structured array 头/选点数最多流/逐列单位换算）
│   │                        #   + Blackrock(.nev/.ns*)/OpenEphys(.continuous→目录)/Intan(.rhd/.rhs)（M5，可选）
│   └── nwb_reader.py        # NWB：acquisition/processing 找 ElectricalSeries；trials/epochs→EventTable（M5，可选）
├── proc/                    # 预处理层（M3 建，M4 加 crop；禁止 import Qt）——每步=pydantic参数+apply(ctx)
│   ├── context.py           # ProcessingContext：raw/epochs/stage/events/history/logs + from_recording（副本隔离）
│   ├── base.py              # ProcStep ABC + STEP_REGISTRY + register_step + step_to/from_dict + apply_pipeline
│   │                        #   （M5 加 cancel_check 参数 + PipelineCancelled——逐步骤取消检查）
│   ├── filters.py           # bandpass（raw+epochs）/ notch（仅 raw——mne Epochs 无 notch_filter）
│   ├── referencing.py       # reref：平均/自定义参考（mne 1.12 返回副本，必须写回 ctx！）
│   ├── resample.py          # resample：降采样（升采样拒绝）
│   ├── bads.py              # bads：标记（幂等）/插值；默认值带入浏览器右键标记
│   ├── epoching.py          # epoching：事件分段（raw→epochs 阶段翻转；reject_uv 阈值丢弃）
│   ├── crop.py              # crop：时间窗裁剪（M4；raw 绝对时间/epochs 相对事件锚点；事件表不动）
│   └── preview.py           # PreviewReader + make_preview_recording：处理副本包装成可浏览 Recording
├── features/                # 特征提取层（M4；禁止 import Qt）——与 proc 层完全同构的注册表
│   ├── base.py              # FeatureExtractor ABC + FEATURE_REGISTRY + apply_features（M5 加 cancel_check）+ 通道选择
│   ├── spectral.py          # mean_welch/array_welch（scipy 广播）+ BandPowerFeature（δθαβγ+自定义+相对/对数）+ WelchPsdFeature（仅 raw）
│   └── timedomain.py        # TimeDomainStatsFeature：rms/var/mav/ptp/iqr/zc_rate/kurt/skew 8 统计量纯 numpy
├── batch/                   # 批处理层（M4 results + M5 引擎；禁止 import Qt——引擎是纯 Python）
│   ├── jobs.py              # JobSpec/PipelineSpec（dict 快照+resolved_* 启动前校验）/FileResult/FileStatus/BatchSummary（M5）
│   ├── engine.py            # BatchEngine：ThreadPoolExecutor(默认2) + threading.Event 取消 + 逐文件容错日志
│   │                        #   + LoadedRawCache pin + _export（CSV/H5+sidecar extra.batch）（M5）
│   └── results.py           # FeatureTable：长表 7 列 + COLUMNS_ZH 中文表头 + to_wide(dropna=False) + summary_zh
├── export/                  # 导出层（M4，禁止 import Qt）
│   ├── features_io.py       # CSV（UTF-8 BOM+中文表头；曲线另存宽表按频率轴分组）/ HDF5（/features + /psd/<i>）
│   ├── epochs_io.py         # epochs → HDF5（/epochs/data f4+times+event_codes+attrs）/ FIF（mne 无损）+ 回读
│   └── provenance.py        # <名>.pipeline.json：app/pipeline/features/recordings/library_versions/extra
├── workers/generic.py       # run_in_thread：后台任务→_MainRelay 主线程回调（见坑 #7/#13）
└── ui/                      # 全部 Qt 代码
    ├── main_window.py       # 主窗口：导入/浏览/特征/批处理结果 tab、设置、采样率询问
    ├── state.py             # SessionState 信号中枢（recording_opened 等）
    ├── strings_zh.py        # 全部中文文案集中（class S；M5 段 BATCH_*/SET_*）
    ├── dialogs/import_dialog.py   # 导入控制器：worker 扫描→进度→错误表
    ├── dialogs/batch_dialog.py    # 批处理两页对话框：选择(过滤/全选/导出组)↔运行；queue.Queue+QTimer 事件泵（M5）
    ├── dialogs/settings_dialog.py # 设置：线程数/缓存 GB/默认导出目录（M5）
    └── widgets/             # workspace_tree / meta_table / signal_browser / event_lane / log_panel
                              #   + params_form（pydantic 自动表单，步骤/特征共用——step_id 别名零改动）
                              #   + pipeline_panel（步骤链+特征链+预览+PSD+「用当前显示窗口」预填）
                              #   + psd_view / epochs_preview
                              #   + feature_table（特征结果 tab：长表排序浏览+CSV/HDF5/分段导出+sidecar）
                              #   + batch_view（批处理运行页：逐文件表/失败红显/双击日志对话框；M5）
                              #   signal_browser（M6 重构：_PanViewBox 滚轮平移/通道名行内嵌 TextItem/
                              #   幅值标尺 _nice_number/翻屏导航/键盘；绘图浅色主题在 main_window 一处）
```

**四条硬性规则**（review 时检查）：
1. core/io/proc/features/batch/export 不得 import PySide6/pyqtgraph
2. UI 不做计算，一律经 workers/batch 线程 + 信号
3. 跨线程只传纯 Python/mne 对象
4. 上下文检测双检查点（用户 2026-08-18 更新）：里程碑**中途**（每 1–2 个子任务）与**收尾**各查一次，接近/超过 70% → 先把关键状态写入治理文件再压缩；
5. 里程碑收尾四件事：治理文件更新 → review.md 记录 → 上下文检测 → git commit

## 代码风格约定

- 标识符英文，**docstring 与关键注释中文**（用户要求：后续维护者不读实现也能懂）
- 类/函数 docstring 写清：用途、参数、返回、异常；关键算法处注释解释"为什么"而非"是什么"
- pydantic v2 建模所有可序列化配置/参数；pandas 用于表格结果
- git：仓库级身份 `DataloadV Dev <dev@dataloadv.local>`；每里程碑一次 commit，消息格式 `M<编号>: <内容摘要>`

## 坑与注意事项（踩过的坑写这里，防止重蹈）

1. **羊 EDF 非 UTF-8**（M6.5 再认识：该现象发生在**错误的 EDF 解码路径**上——羊文件实为 BDF，按 BDF 读不触发编码问题；latin1 自动回退仍保留在 `_read_mne_robust`，对真 EDF 的非 UTF-8 注释仍有意义）：`mne.io.read_raw_edf` 默认编码抛 UnicodeDecodeError 时用 `encoding="latin1"` 重试（解法源自 pipelineMotor `formats.py` 的 EdfLatin1Adapter）。
2. **BCI-IV ds4 .mat 很大**（118–134MB）：loadmat 出来是 int32/float64，要 `astype(np.float32)` 物化并 `del` 中间体，否则内存翻倍。参考 pipelineMotor `data/mat_loader.py` 的结构解析（本项目重新实现，不导入）。
3. **mne 滤波需要 preload=True**：浏览器展示可保持 lazy，但预览/批处理在第一步前必须确保 preload。
4. **`data/` 目录只读**：4.9GB 原始数据，应用绝不写入；用户配置在 `~/.dataloadv/`，导出去用户选择的目录。
5. **Qt 回调里绝不能让异常挡住退出**：M0 冒烟首版在 QTimer 回调中抛 AttributeError 导致 `app.quit()` 未执行、进程悬挂。规则：自检/回调类代码把断言包 try、把 quit/cleanup 放 finally（见 scripts/smoke_gui.py）。
6. **`mne.Annotations` 不接受 `verbose` 参数**（与多数 mne 类不同），构造时不要传。
7. **PySide6 信号连接不持有 Python receiver 引用**：Worker 作为局部变量在 run 触发前就可能被 GC（线程空转、回调静默丢失，伴随 "QThread: Destroyed while thread is still running"）。解法：`thread._dlv_worker = worker` 保活（workers/generic.py 已内置）。
8. **pg.PlotItem 构造期 `self.scene()` 为 None**：要绑 sigMouseClicked 等场景级事件，必须在加入 GraphicsLayoutWidget 之后——EventLane 用 `wire_click()` 延迟绑定模式，浏览器挂载后调用。
9. **读取器收到的 path 可能是 str**（如 meta.path 从 JSON 反序列化回来）：所有 `path.name`/`path.suffix` 操作前先 `path = Path(path)` 归一（_read_edf_robust 已内置）。
10. **锁内调 unload 的死锁模式**：LoadedRawCache 曾在持锁状态下调 `rec.unload()`→`forget()` 再拿非重入锁。规则：锁内只"选受害者摘链"，实际 unload 在锁外执行（_pick_victims_locked / _unload_victims 分离）。
11. **e2e/测试脚本必须幂等**：工作区持久化在 `~/.dataloadv`，脚本开头 `reload_workspace("一次性名字")`、结束切回原工作区，否则二次运行全是"重复导入"。断言要用**总量**（`len(workspace)==N`）而非新增数（added）。
12. **类属性赋普通函数会变绑定方法**：`_read_fn = mne.io.read_raw_gdf` 写在 class body 里是 descriptor，`self._read_fn(path)` 实为 `read_raw_gdf(self, path)`——读取器实例被当文件名传进去（报 "File must be an instance of path-like, got GdfReader"）。规则：类属性持有函数必须 `staticmethod(...)` 包住。
13. **worker 线程回调弹模态框 = macOS 不定时冻结**（M2 最关键产品修复）：`worker.failed.connect(lambda m: QMessageBox.critical(...))` 这种无 QObject receiver 的普通函数连接是直连——lambda 在**发射线程（worker 线程）**执行，非 GUI 线程创建模态对话框在 macOS 上不定时挂死整个进程（e2e_m2 两次 0.1% CPU 空转卡死）。解法：workers/generic.py 的 `_MainRelay`（主线程 QObject 槽中转，回调保证主线程执行）。UI 侧用 `run_in_thread` 即自动获得保护；任何新的信号→弹窗路径都要确认槽对象亲和主线程。
14. **e2e 脚本必须中和模态对话框**：任何真实代码路径可能弹 QMessageBox 的地方，e2e 开头 patch 掉（`mw.QMessageBox.critical = staticmethod(lambda *a, **k: print(...))`），否则一旦有弹窗脚本永远等不到下一个 QTimer。
15. **scipy.io.savemat 的 struct 不接受 None 字段**（`Could not convert None to array`）：合成 mat 夹具里别放 None 占位，删掉该字段即可。
16. **搜索摘要不可信，官方 PDF 才是权威**：GDF 事件码表从搜索结果拿到的"含义"多处错误（781 被猜成 correction/beep wrong、1077 被猜成 eyes closed）；用 pypdf（一次性 pip 工具，不入应用依赖）从官方 desc_2a.pdf/desc_2b.pdf 提取原文核实——781 = "BCI feedback (continuous)"，1077–1081 = 眼动伪迹标记。
17. **macOS zsh 无 `timeout` 命令**：限时跑命令用执行工具自带的 timeout 参数，别写 `timeout 60 cmd`。
18. **mne 1.12 `set_eeg_reference` 返回副本非就地**（M3 实测 `inst is raw` 为 False）：必须用返回值写回 ctx.raw/ctx.epochs，否则重参考悄悄失效。
19. **mne `Epochs` 没有 `notch_filter` 也没有 `event_name`**：陷波限 raw 阶段（applies_to）；每类段数统计用 `event_id` 逆映射 `{v: k for k, v in event_id.items()}`。
20. **`compute_psd` 不接受 `fmax=None`**（np.isfinite 报 TypeError）：fmax 为 None 时显式传 Nyquist（sfreq/2）。
21. **同刻多事件 + 表单覆盖时序**（M3 e2e 排障）：① 同一时刻多事件会让 `mne.Epochs` 抛 "Event time samples were not unique"——必须 `event_repeated="drop"`；② PipelinePanel 的参数覆盖必须在**表单构建之前**合入（`add_step(step_id, **overrides)`），表单 collect() 会用控件当前值冲掉之后改的 `_steps` 条目。
22. **pydantic 步骤参数默认值必须可构造**：空列表/非空类校验放模型 validator 会让 `default_params()` 直接 ValidationError（表单往返测试暴露）——此类校验移到 apply() 执行期给中文 StepError。
23. **QListWidget 清空触发 currentRowChanged(-1)**：清空/删除步骤行时 `list.clear()` 会用过期行号调 `_on_select`——槽函数必须做行号边界守卫。
24. **tmin=0 时 baseline (None, 0) 只含一个样本**，mne 拒绝（"Baseline interval is only one sample"）：epoching 内自动转 (0.0, 0.0)。
25. **`raw.crop` 会同步更新内部 first_samp**（M4 实测）：裁剪后 EventTable 绝对秒 onset 与 epoching 的绝对样本号依然成立——crop 步骤**不需要改事件表**；e2e 验证 crop[5,25] 后窗口内事件保留、窗外自然丢弃。
26. **mne 读 BCI-IV 2a GDF 时 25 通道（22 EEG + 3 EOG）全部标为 `eeg`**：特征层按类型白名单无法排除 EOG——默认取全部 25 数据通道；要排除 EOG 须在特征参数 channels 里显式写 22 个通道名。
27. **`scipy.signal.welch` 参数名是 `nperseg`（无下划线）**，不是 mne 风格的 `n_per_seg`——TypeError 才发现。
28. **pandas `pivot_table` 默认 `dropna=True` 会把组键含 NA 的行整组丢掉**：文件级特征行（epoch_index=None）在宽表里全部消失——`to_wide()` 必须传 `dropna=False`。
29. **`mne.Epochs.crop` 窗完全在段外时先抛英文错**（"tmin must be less than..."）：中文预检查（无重叠→"分段数为 0"）必须放在 crop 调用之前；同类思路适用于一切 mne 参数校验前置。
30. **Qt6 无 `Qt.ItemDataRole.SortRole`**：自定义排序角色用 UserRole + `setSortRole(UserRole)`；且数值列 data() 的 UserRole 分支必须返回 float——否则代理按字符串排序（"10" < "2" 乱序）。
31. **e2e patch QMessageBox 必须逐模块进行**：`from PySide6.QtWidgets import QMessageBox` 是各模块的独立引用，只 patch main_window 的不影响 pipeline_panel/feature_table；漏 patch 的模块真弹模态框 → offscreen 事件循环永久阻塞（CPU 0% 假死，坑 #14 的 M4 变体）。
32. **通道平均 PSD 的谱峰取决于各通道幅度²**：羊数据 30µV 工频 > 2×20µV α 的合成功率，平均曲线峰在 50Hz——断言 α 主导要用单通道指定，不能用通道平均。
33. **neo.rawio 0.14 的 header 是 numpy structured array**：`header['signal_channels']` 行取值用**字段名**（row['name']/row['units']/row['stream_id']），不是下标也不是 dict；`rescale_signal_raw_to_float` 得到的是**通道单位**浮点，到伏特要自己按 units 查表（neo_reader._UNITS_TO_V）；Blackrock 传全名失败时回退去扩展名基名；OpenEphysRawIO 收**目录**（.continuous 文件取 parent）；IntanRawIO 收文件。
34. **pynwb 4.x 三处接口坑**：`add_electrode` 的 location 必填非空（""被拒）；电极表默认**无 label 列**需 `add_electrode_column("label", ...)`；`DynamicTableRegion.colnames` 是 **None**（不能判列存在），取列直接 `region["label"][:]`（try/except 包住）——M5 测试三轮才探明。
35. **Qt6 魔数全部禁用**：`0x02` 是 `ItemIsEditable` 不是 UserCheckable（运行期静默错行为：单击进入编辑而非切换勾选）；必须 `Qt.ItemDataRole.UserRole` / `Qt.ItemFlag.ItemIsUserCheckable` / `Qt.CheckState.Checked` 全枚举写法。
36. **mne 无 `write_raw_edf`**：合成 EDF 用 `raw.export(path, fmt="edf", overwrite=True)`。同类：**stdout 重定向到文件是块缓冲**——e2e 中途崩溃时已过检查项的 print 全丢在缓冲区，脚本类 print 一律 `flush=True`。
37. **2b E（评估）文件 769/770 事件全 0，未知类 cue 是 783**：T 文件 769:60+770:60=120 段，E 文件 783:160 段——同一分段码表跑通两类文件必须含 783（M5 e2e 实测；正文见 STATUS 实证结论 M5-#1）。
38. **pyqtgraph ViewBox 默认滚轮同时缩放 x/y，且 y 轴 setTicks 放全部通道名不可扩展**（M6 用户反馈"通道名重叠/…"根因）：解法组合——`setMouseEnabled(x=True, y=False)` 锁 y + 子类 ViewBox 重载 `wheelEvent` 接管滚轮（不调 super）+ 通道名改曲线行内嵌 `pg.TextItem`（半透明白 fill 压波形上可读）。另：`PlotCurveItem.yData` 就是 setData 传入数组本体（shares_memory 实证），读曲线数据做断言安全。
39. **浏览器增益两个存量 bug（M1 起，M6 修复）**：①增益只乘通道间距不乘波形（`out_v + idx*spacing*gain`——语义应为 `out_v*gain + idx*spacing`）；②`_gain` 字段存的是**滑杆刻度值**（增益=10^(x/10)）却初始化 1.0 → 首帧起隐形 1.26×。教训：存"控件原始刻度"的字段，初值必须与控件初值一致。
40. **mne 公共入口（read_raw_edf/bdf/gdf）按扩展名硬拒绝，file-like 对象可绕过**（M6.5，用户指定方案）：`_check_args` 抛 "Only BDF files are supported, got edf"，但对 file-like **跳过扩展名检查**（仅要求 preload=True；read_raw_bdf 自 MNE 1.10 官方支持 file-like，edf/gdf 同路径）——扩展名与内容不符时（sheep 系列 .edf 实为 BDF）传文件对象重读同一公共入口即可，**不要直接实例化 Raw* 构造器**。**错格式解码的症状要认得**：BDF 24-bit 样本按 EDF 16-bit 读 = 样本数虚增 1.5×（180s→270s）+ 数值全部错位且"看起来正常"（有限值、有峰形）——长度比值是最快破案点。另：内容派发必须"唯一定位"才提升（hdf5 是家族签名，抢了 NWB 的活），且魔数明确时**不给扩展名候选兜底**（错读成功比读失败更糟）。
41. **EDF 头版本域是字节 0–7 共 8 字节**（M6.5 修 off-by-one）：嗅探判 EDF 只能看前 8 字节（`b"0"+7空格`）——越一位就把患者域首字节卷进来，真 EDF 患者名不以空格开头就漏判返回 None。此前 M2–M6 无人察觉：.edf 走扩展名快路径从不触发嗅探。教训：**给"快路径"兜底的慢路径，同样要有测试覆盖，否则它烂了都不知道**。
42. **file-like 读取的 raw 内部残留文件句柄，copy()/deepcopy 直接炸**（M6.5 file-like 改造实测）：mne 把 file-like 存进**两处**——`_raw_extras[*]["blob"]`（懒读数据用）和 `_init_kwargs["input_fname"]`——整载后引用已无用途，但 `raw.copy()` 抛 "cannot pickle '_io.BufferedReader'"（只剥 blob 仍炸，第二处藏在 _init_kwargs）。`_detach_file_handles` 读后剥离两处（init_kwargs 回填真实路径）。教训：**绕过库入口的方案要全链路验证**——pytest 156 绿没拦住它，e2e_m3 预览（ProcessingContext 即 raw.copy()）第一个撞上。
43. **e2e 轮询分支必须有 tries 上限 + check print 要 flush**（M6.5 排障半天教训）：e2e_m3 的 `_stage1c` 轮询无上限，worker 静默失败后每 800ms 打一条 ❌ 无限循环=假死；且其 check() print 无 flush=True，后台/管道运行时块缓冲看不到任何输出（坑 #36 的规约只落实在新脚本）。排障正确姿势：`python -u` + 不接 tail 管道直跑。
44. **EDF/BDF 头部手工解析布局（两次踩坑后实证）**：固定头 256B 内**记录数@236、每记录秒数@244、通道数@252**（240/248 是空档，别按"标准偏移 240"记）；信号子头是**字段主序**——所有 label 连续（每通道 16B）→ 所有 transducer（80B）→ … → samples 字段区在 `256 + ns*216`，**不是**每通道 256B 块。羊文件 ns=9：labels@256、samples@2200、数据区@2560（=headerbytes 字段值，可自校验）。

## 当前接手要点（2026-08-24，M6.5 已完成）

- **M6.5 读取派发魔数校验完成（用户发现羊数据实为 BDF 驱动）**：`open_file` 走 `_dispatch_readers` 魔数内容优先派发（EDF/BDF/GDF/BrainVision 唯一定位时以内容为准、不兜底；hdf5 家族除外）；`_read_mne_robust` 扩展名不符时**file-like 绕过**（用户指定：走 read_raw_* 公共入口、不直接实例化 Raw*；读后 `_detach_file_handles` 剥离残留句柄，坑 #42）+latin1 回退；sniff EDF 分支 off-by-one 修复；workspace 重导入刷新 meta——**纠正了 M1 以来羊数据错位解码的数据正确性 bug**。**羊标注通道核查定论（2026-08-24）**：6 个羊 BDF 的 BDF Annotations 通道全是纯 ASCII TAL（`+N\x14\x14\x00` 每秒一条空注释），满足 UTF-8、零事件是数据本身属性——"羊需要 latin1"是 M1 误解码副产品，机制保留给真 latin1 文件。pytest 157 绿 + e2e_m1 19 项 + m2–m5/smoke 回归全过（见 review.md M6.5 节）
- **用户工作区旧羊条目需重导入一次刷新**（format/时长从 EDF/270s → BDF/真实时长）——`add_metas` 现在重复导入即刷新（rec_id 稳定）；data/sheep、sheep2、sheep3 三个文件夹都重导
- **M6 浏览体验优化完成（用户实测 v1 三点反馈驱动）**：通道标签行内嵌（y 轴 setTicks 已废弃）、幅值标尺、窗口导航（一屏时长下拉/翻屏按钮/滚轮平移/Ctrl+滚轮缩放/键盘 ←→ Home End ↑↓）、全局浅色主题、增益双 bug 修复
- **v1 全部里程碑（M0–M5）完成并验证**：pytest + e2e_m1–m5 + smoke_gui 全过（见 review.md 各节）。后续事项见 TODO.md「Backlog」（Blackrock/OE/Intan/NWB 真实数据实测、ds3、eeglabio/pybv 等）
- **批处理架构（M5 关键决策）**：BatchEngine 是**纯 Python**（无 QObject——架构规则 #1 优先于 plan.md 原文"BatchEngine(QObject)"）；回调（on_progress/on_file_done）在 worker 线程执行 → UI 侧 `queue.Queue` + QTimer 150ms 事件泵（batch_dialog._drain_events）转主线程；`run()` 整体经 `run_in_thread` 丢进一个 QThread，内部 ThreadPoolExecutor 提供并发；取消 = `engine.cancel()`（threading.Event）立即返回，引擎在**步骤边界**停止（proc/features 的 cancel_check 逐步骤检查，抛 PipelineCancelled）
- 批处理新增文件三件套已定型：管线/特征输入用 `pipeline_panel.pipeline_dicts()`/`feature_dicts()`（dict 快照，JobSpec 零转换）；结果并入 `FeatureTable.add_result()`（多文件长表 recording 列区分）；导出走 engine._export（sidecar extra.batch 记 n_files/n_workers/files_written）
- **特征范围决策（用户 2026-08-18 确认）：四层组合**——全量默认 + epochs 逐段 + crop 步骤（显式时间窗，进 sidecar）+ 视口一键预填（不隐式绑定）；滤波类预处理仍全量（边界效应），crop 只裁数据范围
- **ProcStep/FeatureExtractor 同构注册表**：pydantic 参数模型 + `apply(ctx)`；注册后 params_form 零 UI 代码自动出表单（FeatureExtractor 的 `step_id` property 别名是零改动复用的关键）。**新步骤/特征三件套：参数模型 + 类 + strings_zh 文案**
- 预览机制：`ProcessingContext.from_recording` 强制 PRELOAD + `raw.copy()`（原始逐位不变，pytest 有断言）；处理副本经 `make_preview_recording` 包装成不注册、不入工作区的 Recording → 复用全部浏览器机制
- 读取器新格式套路：mne 系用 `_MneRawReader` 模板基类，只声明 `_fmt`/`_read_fn`（**staticmethod 包住**，坑 #12）/`_extra`，EDF 家族再加 `_robust=True`（file-like 绕过+latin1 回退，坑 #40/#42）；neo 系用 `_NeoRawReader` 模板（坑 #33）；NWB 单独实现（坑 #34）；`RecordingMeta(**self.common_meta_fields(path, fmt), ...)` 一次构造；neo/pynwb 均为 import-guard 可选依赖（缺失时应用照常运行）
- 真实数据路径速查：羊数据（**BDF 内容的 .edf**）`data/sheep|sheep2|sheep3/*.edf`；PhysioNet `data/dataset/files/S001/`；2a GDF `data/dataset/BCICIV_2a_gdf/A01T.gdf`；2b GDF `data/dataset/BCICIV_2b_gdf/`（M5 批处理验收用整个目录 45 文件）；ds1 mat `data/dataset/BCICIV_1_mat/BCICIV_calib_ds1a.mat`；ds4 mat `data/dataset/BCICIV_4_mat/sub1_comp.mat`
- **数据集详细信息（来源/结构/参数/事件码表/已知坑）全部在根目录 `DATA_NOTES.md`**（2026-08-18 按用户要求建立），改读取器前先读它；新数据/新实证发现要回写它
