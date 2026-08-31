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
# （或一步到位：仓库根 environment.yml = M7 导出的全依赖含版本锁，
#   conda env create -f environment.yml 后只需做第 5 步）

# 5. 本包可编辑安装（含 dev 依赖）——在项目根目录（含 pyproject.toml 那层）执行；
#    用相对路径 "." 安装，不写死本机绝对路径（换终端/换用户/换克隆位置通用）
cd <项目根目录>             # 例：cd ~/VSproject/"intervention BCI"/DataloadV
pip install -e ".[dev]"
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
QT_QPA_PLATFORM=offscreen pytest             # 全部单测（M8.2：261 passed，含 real 数据项；
                                             #   MainWindow 级测试须 offscreen——坑 #45）
pytest -m real                               # 仅真实数据冒烟（data/sheep 缺失自动跳过；建议同带 offscreen）
python scripts/e2e_m81.py                    # M8.1 端到端：三锚定分段+时频观感+单段浏览（幂等；须 offscreen）
python scripts/e2e_m8.py                     # M8 端到端：分段四视图+时间分辨特征+守恒式（幂等；须 offscreen）
python scripts/e2e_m7.py                     # M7 端到端：质量体检真实黄金标准（幂等；须 offscreen）
python scripts/smoke_gui.py                  # GUI 冒烟：真窗口启动自检后自动退出
python scripts/e2e_m1.py                     # M1 端到端：真实导入→浏览→渲染→释放（幂等，可反复跑）
python scripts/e2e_m2.py                     # M2 端到端：4.9GB 扫描+六格式打开（幂等，可反复跑）
python scripts/e2e_m3.py                     # M3 端到端：预览/PSD 压制/分段/tab 释放（幂等，可反复跑）
python scripts/e2e_m4.py                     # M4 端到端：特征计算/视口预填/导出/分段回读（幂等，可反复跑）
python scripts/e2e_m5.py                     # M5 端到端：45 文件批处理+取消+扩展格式（幂等，可反复跑）
```

## 架构导览（M6.8 后的实际结构）

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
│   ├── qc.py                # compute_channel_qc 纯函数（get_window 闭包分窗采样）+ QualityCheckFeature（M7；排"添加特征"菜单首位；坏道参检不排除——与 pick_channels 语义相反）
│   ├── spectral.py          # mean_welch/array_welch（scipy 广播）+ BandPowerFeature（δθαβγ+自定义+相对/对数+M8 time_windows 时间窗）+ WelchPsdFeature（仅 raw）
│   ├── tfr.py               # compute_epochs_tfr：morlet 段平均功率→基线 dB（M8；禁 import Qt，UI 只编排）+ default_tfr_freqs 对数频率轴
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
                              #   幅值标尺 _nice_number/翻屏导航/键盘；绘图浅色主题在 main_window 一处；
                              #   M6.7b 行居中——M6.8 加开关+通道偏移显示 UserRole/增益输入框 _set_gain/
                              #   ±1s 步进/总览滑块接线 _on_lane_viewport）
                              #   event_lane（M6.8 升级总览轴：LinearRegionItem 视口滑块逐线冻边缘+
                              #   x 三重锁 [0,dur]+viewport_moved/set_viewport 双向防环）
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
- git：身份用仓库现有配置（史实 `JKlove <huyingbing13@gmail.com>`，勿另设假身份）；仅用户要求时 commit；不加 Co-Authored-By 尾注；消息中文、格式 `M<编号>: <主题——要点串联；pytest N绿+回归+治理同步>`

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
32. **通道平均 PSD 的谱峰取决于各通道幅度²**：羊数据 30µV 工频 > 2×20µV α 的合成功率，平均曲线峰在 50Hz——断言 α 主导要用单通道指定，不能用通道平均。（**M8.3 注**：特征链 welch 已改逐通道语义，通道平均只在**对比 PSD 视图**（mean_welch）仍存在，本坑适用于该链路。）
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
45. **MainWindow 级 pytest 必须带 `QT_QPA_PLATFORM=offscreen`**（M6.6 实测）：此前只有 e2e/无头脚本需要 offscreen，加入直接构造 MainWindow 的测试后，组合命令第二段漏 offscreen 在 macOS 真窗口模式挂住、240s 超时假挂——**全套 pytest 从此统一带 offscreen**。配套教训（坑 #36/#43 的重申）：`| tail` 管道缓冲全部输出直到进程结束，长命令一律后台直跑 + `python -u`，别接管道。另：MainWindow 测试间会经 `~/.dataloadv` 持久化耦合——工作区名用 `request.node.name` 每测试唯一（曾 3==2 假失败；M6.6 当时以为 teardown unlink 已解决，**实际清的路径从来不存在**，真解法见坑 #47）。
46. **焦点在 QTreeWidget 内层时，容器组件收不到 keyPressEvent**（M6.6）：Del 键删除必须在树本体的子类里重载 `keyPressEvent`（`_TreeWithDel`），在容器/事件过滤器层拦截无效——Qt 键事件先给焦点控件，树不冒泡给父容器。
47. **工作区测试隔离三重坑（M6.6 埋雷、M6.7 实锤事故后修复）**：① 持久化真实布局是 `~/.dataloadv/workspaces/<名>/workspace.json` **目录**（`<名>` 经 `_safe_name`，中文 isalnum() 为 True 所以基本原样保留）——teardown 按 `workspaces/<名>.json` glob **永远匹配不到任何文件**，测试目录全部残留；② `reload_workspace` 会写全局标记 `~/.dataloadv/current_workspace.txt` 且测试从不恢复——用户下次启动 GUI 直接续进测试名工作区，**当天全部真实导入落在 `test_删除_*` 目录**（1574 条），再被后续 pytest 的 `MainWindow()` 首载读回 → `len(ws)==1574` 稳定失败；③ qtbot 关窗触发 `closeEvent` → `workspace.save()` 把测试内容再落盘一遍（残留就是它写的）。修法（test_ui_workspace_remove.py `win` fixture 三重隔离）：构造前 preset 标记为测试名（顺带免去解析用户大 JSON）+ teardown 把 `state.workspace` 换成 `_file` 指向 tmp_path 的替身（closeEvent 落盘改道）+ 按真实布局 rmtree 目录 + 恢复用户标记（原先没有则 unlink）。用户数据已修复（清合成来源并入 默认工作区 1572 条、标记恢复；备份 `/tmp/dataloadv_repair_backup_20260827_160326`）。教训：**改全局可变状态的测试必须"存-改-恢复"三段式，且恢复路径要与真实布局对过**——写 teardown 时没有对过布局，等于没有 teardown。
48. **pyqtgraph `connect="pairs"` 只对 (min,max) 成对结构合法（M6.7 渲染双缺陷）**：① raw 透传序列带 pairs 会 0-1/2-3/… **隔段漏画**，波形呈断续虚线；② 抽取阈值（`_SAMPLES_PER_PIXEL=2`）在 Retina（`vb.width()` 返回**逻辑像素** ≈ 物理一半，~1212px 绘图区 → max_points=2424）下，250Hz 数据的 **9s 屏（2250≤2424 走 raw）与 10s 屏（2500>2424 走 m=2 抽取）恰跨档**——10s 每像素一根竖线密集成带、9s 断续发虚，观感突变全由阈值悬崖造成。修法：connect 按是否真抽取分支（`"pairs" if n>max_points else "all"`）+ 阈值 2→3 样本/px（折线在此密度仍可读，且 1/2/5/10s 预设全留在折线档，30s+ 才包络）+ antialias 恢复 True（两档绘制把点数约束在 ~3×像素宽内，开销可承受；关 AA 时亚像素 1px 线段会整段丢失）。另：`minmax_decimate` 在 m=2 时输出点数==输入点数，**不能用长度比较判断是否抽取**，要用同一条件 `n > max_points`。
49. **y 轴锁定 + 堆叠公式假设基线 0 → DC 耦合数据"空白 tab"（M6.7b 主根因）**：M6 锁了 y 轴（`setMouseEnabled(x=True, y=False)`）且 yRange 只按 MAD×8 间距估计——堆叠公式 `(值) + idx*spacing` 假设各通道基线在 0 µV。BioSemi BDF 是 **DC 耦合**：clinicaldata CH1–4 真信号骑在 4.5k–69k µV 直流偏移上、CH5–8 饱和平线 ±375000 µV → 曲线全部画在锁定 yRange 外数千 µV 处，而工具栏/标签/网格/标尺照常画 → 用户看到"加载成功的空白"（"退出重开才能看到第一个"是巧合：位置1 偏移恰好落在范围内）。修法 = **行居中**（EEG 浏览器标准做法）：显示值 = (原始值 − 本窗口该通道**中位数**) × gain + idx×spacing；窗口内漂移斜率形状仍如实呈现，跨窗口绝对电平不进画面。配套 `_estimate_spacing` 只按**有交流起伏的通道**（MAD>0.01µV）估间距——≥5 条饱和平线会把 MAD 中位数拖到 0、间距塌缩（TPDJ 形态），全平录音保持默认 100µV。回归 TestOffsetRobustDisplay 4 项（显示中位数必在 yRange 内/平线不压塌间距/平线贴行/全平不塌缩）。
50. **单字符变量名笔误在 git diff 中隐形——数值级回归测试是唯一防线（M6.7b 次根因）**：`minmax_decimate` 里 `t_max, v_max = t[rows, i_max], t[rows, i_max]`（第二处应为 `v`，**随 M6.6 提交潜伏了一个月**）——`t`→`v` 同字节长度，diff 一行不红、肉眼永远看不出。后果：包络档"max 点"全是时间戳（0–10 的小值）→ 上半包络塌到 0 附近，密集窗口呈"从真实 min 直落 0"的密集竖线带（用户 M6.7"10s 密集"观感的一部分成分）。诊断指纹：常数 375010 输入、median 输出 187505（=375010/2，时间戳与真值各半）。教训：①min/max 类函数必须有**常数进常数出**的数值断言（旧 connect 标志测试抓不到值污染）；②排查时若 Read/sed 显示的源码与行为矛盾，用 `ast.parse`+`ast.unparse`（或 `git show HEAD:<file>`）做终裁——本例磁盘实为双 t，中途多次 Read 显示 v，险些误判"已正确"。
51. **视觉验证方法学（M6.7b 排查中三连踩）**：①**非白像素占比不能证明波形渲染**——白底 alpha 0.25 网格线就能贡献 ~30–50% 非白像素，"有像素=有波形"是假阳性（此前离屏/真窗口 API 复现"全正常"的结论即被此误导）；②**视觉模型会误读小字号文本**——截断 tab 标签"TPDJ"被读成"EPGJ"，一度引向不存在的目录；③像素验证必须**看内容**（亲自读 PNG / 问"几条曲线、什么形态"），不能只看比例。另：pyc 缓存校验用 (magic, flags, mtime, size) 四元组——源码同尺寸替换且 mtime 撞车时旧 pyc 会被继续使用，排查"改了没生效"先 `find -name __pycache__ -exec rm -rf`。

52. **pyqtgraph `LinearRegionItem` 做"总览视口滑块"的三个源码级细节（M6.8，dlv 环境 0.14.0 实读源码验证）**：①拖区域=两条边界线按 delta **整体移动**（宽度天然保持），拖边界=各自独立 `InfiniteLine`——"只平移不许改宽"用**逐线 `for line in region.lines: line.setMovable(False)`** 冻结边缘实现（区域级 movable 仍 True，整体拖动/悬停亲和不受影响），比"宽度变了就 setRegion 弹回"干净（无回弹闪烁、无再入）；②`setRegion` **值相同早退不 emit、值不同会 emit** `sigRegionChanged`——程序化回写（主图视口→滑块）必须用 `_syncing` 标志包住，否则回写会被当成"用户拖动"再发 `viewport_moved` 成回环；③拖出 `[0,duration]` 时两线**各自**被 bounds 钳制（前缘停后缘继续）→ 区域瞬时压窄——消费侧（browser）**只取 region 中心、按主图自身宽度重锚**，绝不直接采纳两缘宽度，否则一次越界拖动就把一屏时长永久改掉。另：`ViewBox.setMouseEnabled(False,False)` 后 items 仍收鼠标事件（事件先给鼠标下 items，不 accept 才落 ViewBox）；左键单击不被 region 吃掉（scene 级 `sigMouseClicked` 照发），点击居中与拖滑块天然共存。

53. **两处潜伏的"注释/文档骗人"（M6.8 修正）**：①增益滑杆 `-20..20` 配 `10^(x/10)` 实际是 **0.01×–100×**——代码注释与 MANUAL 都写成"0.1×–10×"，做增益输入框时若照注释定范围（0.1–10）会与滑杆两端脱钩；②`QListWidget.itemChanged` 在 **`setText` 时也触发**（不只是勾选变化）——把偏移文本批量拼进行文本必须 `blockSignals(True)` 包住，否则一次更新连发 N 次 `_on_channel_toggle`→无谓刷新。配套迁移：通道名权威源挪到 `item.setData(UserRole, name)`（右键菜单/坏道标记不得再拿 `item.text()` 当名字）。另：键盘 ↑↓ 增益若走 `slider.setValue(int)` 会把输入框设的小数增益（2.5×≈3.98 dB×10）取整抹掉——三入口（滑杆/输入框/键盘）统一收敛到 `_set_gain(float)`。
54. **signal_browser 模块 M7 起有模块级 QMessageBox 引用**（坑 #31 规约的新实例）：质量体检的建议确认弹窗在 signal_browser 里直接 `from PySide6.QtWidgets import QMessageBox` 使用——e2e/测试只 patch main_window 的罩不到它，漏 patch 则 offscreen 事件循环挂死。e2e_m7 与 test_features_qc 都单独 patch `dataloadv.ui.widgets.signal_browser.QMessageBox`。另：QC 判定**没有绝对饱和电平阈值**（跨设备满量程差 2 数量级），靠"钉本通道极值占比"；低频大信号天然有峰值平台（羊 CH1–4 rail≈2.3% 触发疑似线）——"真信号不坏"是黄金不变式，"真信号必 good"不是。

55. **M8 时频视图与时间分辨特征的六个源码级细节**：①`pg.ImageItem.boundingRect()` 返回**像素坐标**（如 300×24），断言/布局要视图坐标须 `mapRectToView(boundingRect())`；②`invertY(True)` 是 ViewBox 级**粘性状态**——时频视图切走不显式 `invertY(False)` 复位，堆叠/蝶形全部上下镜像；③`HistogramLUTItem` 挂在 `GraphicsLayoutWidget` 侧列，`plot.clear()` **清不到**——切视图须显式 `removeItem`，否则色标残留（残留回归已入测试）；④后台线程回调要**双保险丢弃**：`self._data is None`（teardown）+ 当前视图模式 guard（用户已切走）——只查前者，计算返回时会用热图盖掉刚画好的其它视图；⑤**测试等后台线程要等"真收尾"**：ImageItem 出现 ≠ deleteLater 链走完，伪造 `_tfr_running` 后退出会话会打出 "Signal source has been deleted"——`qtbot.waitUntil(lambda: not _keepalive)` 才是线程链收完的本质判据（`workers/generic._keepalive` 模块级容器）；⑥**不同窗长的 Welch nperseg 是系统偏差**：`array_welch` 的 nperseg=min(4s 默认, 窗长)——1s 窗 1Hz 分辨率摊薄窄 α 峰 vs 4s 窗 0.25Hz，A01T 实测"整段=子窗时长加权混合"守恒残差 24%、统一 `n_per_seg_s=1.0` 后 8.2%——**跨窗对比要么等长窗要么统一分辨率**；配套：A01T 原始数据 22 EEG 群体 ERD 中位仅 1.05±0.1 无显著方向，黄金断言用守恒式不用生理方向（M7"数据事实优先"同款）。另：`mne.events_from_annotations` 返回的 events 第三列是**按注释名重映射的连续整数**不是原码 769——离线脚本要 `event_id['769']` 查表（UI 面板按 annotation 名过滤不受影响）。

56. **M8.1 分段锚定与时频观感的六个源码级细节**：①**`pg.ColorMap` 收 0..1 float 色数组会按 0..255 截断**（0.75→0）——近全黑热图且无告警；jet/hot 公式生成必须 `(256,3)` **uint8**（`np.round(rgb*255).astype(np.uint8)`）；viridis/turbo/plasma 是 `pg.colormap.get()` 内置、jet/hot 抛 FileNotFoundError（dlv 环境 0.14.0）。②**`ImageItem.lut` 是可调用不是数组**——`HistogramLUTItem.getLookupTable` 的引用（随 gradient 实时变），签名 `getLookupTable(img=None, n=None, alpha=None)` **首参是 img**：`img.lut(256)` 报 `'int' object has no attribute 'dtype'`，取表须 `img.lut(n=256)`；`np.asarray(img.lut)` 得 bound method 对象数组比较恒无意义。配套：`img.getLevels()` 返回 ndarray，断言相等须 `np.array_equal`（`==` 触发 truth-value 歧义）；`lut.gradient.setColorMap(cm)` 只走 gradientChanged→setLookupTable **不碰 levels**（换配色零亮度扰动），且须在 `setImageItem` 之后调用。③**mne.Epochs 锚点保留条件**（1.12 实测）：`anchor+round(tmin·fs) ≥ 0` 且 `anchor ≤ n_times−1−round(tmax·fs)`，越界锚点被 `on_missing="ignore"` **静默丢弃**——自定义锚点序列一律**样本域**构造（秒域近似差 1 样本就丢段）；手动时刻模式是用户显式枚举的输入，必须预检报错列出**全部**无效锚点（"要 5 段得 3 段"比报错难排查）。④**程序化 `setYRange` 会禁用 autoRange**——时频视图须在 `addItem(img)` 后显式 `autoRange()`，否则热图被上一视图残留 Y 范围压成一条（用户截图证实的观感 bug 根因；与 invertY 先后无关）。⑤**中文 Literal 值 = 冻结的序列化格式**：pydantic 校验/旧 JSON 缺键回填/QComboBox 往返三处实测兼容，但换词即旧 pipeline JSON 全不兼容——词表一次定稿；`json.dumps` 记得 `ensure_ascii=False`。⑥e2e_m8/e2e_m81 按视图**索引**寻址（setCurrentIndex(0..3/4)）——预览加新视图只能 append 尾部，不可插位。
57. **M8.2 pyqtgraph 0.14 刻度与图例的五则**（离屏实测）：①`AxisItem.setTicks` 三态——`[[...]]` 自定义刻度、`[]` **空刻度（无任何刻度）**、`None` **恢复默认自动刻度系统**；内部 `_tickLevels` 可读（自定义=列表、空/自动后=None/[]，断言"无自定义刻度"用 `not _tickLevels` 兼容两态）。**切换视图不复位 ticks 就是残留**（通道名 ticks 经 invertY 翻到左上角飘字的根因）。②`plot.clear()` **会**清 LegendItem 条目（`leg.items` 变空——M8 "不用 legend 防 clear 状态残留"的顾虑在 0.14 不成立），但**图例框本身不清**（空框仍显示）——须手动 `legend.hide()`。③LegendItem 0.14 默认 **NoBrush 无底框**（文字直压曲线），`setBrush(mkBrush(255,255,255,210))`+`setPen` 加底；**`columnCount` 是 int 属性不是方法**（`setColumnCount(n)` 是方法）——单列条目多时矮窗口排不到底被截断，`setColumnCount(ceil(n/12))` 分列。④`TextItem` 有 `setFont` 无 `font()` getter——取回走内部 `t.textItem.font()`（QGraphicsTextItem）；堆叠行内嵌标签在矮窗口（500px/25 行）默认字号**盒高≥行距相邻相触**，显式 8pt 压盒高（M6 全高浏览器不受此限保持默认）。⑤离屏 `QFont()` 默认族在 macOS offscreen 有一次性 50ms 字体族别名告警（无害）。⑥**全量 pytest 期间别并发 e2e/smoke 等 QT 重活**：曾出现 pytest 死等（主线程 QEventLoop::exec、后台线程全 cond_wait，CPU 归零）——kill 重跑即过（-v 日志同批测试全绿），属并发负载下的偶发竞态非测试问题；macOS 抓 Python 栈 py-spy 要 sudo，用系统 `sample <pid> 2 -file` 看特征帧（exec/cond_wait）即可判"挂"还是"慢"。

## 当前接手要点（2026-08-30，M8.3 特征结果图表区已完成）

- **M8.3 特征结果图表区（用户两点需求驱动）**：①**`welch_psd` 逐通道语义**——channels 留空=全部数据通道各一条（通道平均分支删除、"(通道平均)"字面量不再存在；`mean_welch` 保留给对比 PSD）；新增 `time_windows`（raw 绝对秒多窗）；curve dict 加 `"window"`（纯 str，`@起-止s`/空=全量）→ results/`features_io` 透传（宽表列头带窗标记、HDF5 attrs、回读兜底旧文件）。窗校验抽 `_resolve_spans(t_axis, spec)`（spectral.py 模块级）BandPower/WelchPsd 共用，错误消息逐字保留（测试钉死）。②**`ui/widgets/feature_charts.py` 新建**——`PsdCurvesChart`（log-log、`intColor(i,hues=n)`、蝶形同款分列图例 `_make_legend`、MAX_CURVES=60 截断+hint）；`FeatureBarGrid`（**每特征一格** 3 列网格 Y 独立、分段 `groupby(recording,event_code,channel,feature).mean()` 按事件码聚合、系列=code（多录制 `rec · code`）、MAX_FEATURES=24/MAX_SERIES=12、通道>12 隔名、QScrollArea；`self.aggregated`/`feature_names` 暴露给测试数值断言）；`make_charts_area(table)` 三态（双有=QTabWidget 两 tab/单有=单图/全无=None）。feature_table `_build_ui` 拆 `_build_table_area` + QSplitter 3:2，构造签名/`_model`/`_proxy` 全不动（e2e 寻址安全）；teardown 加 `_charts=None`。批处理结果 tab 同一控件。验证：pytest **271 绿**（+10）+ e2e_m4 **19 项** + smoke + 三形态白底截图确认。**新坑**：①pg 全局白底在 `MainWindow.__init__` 里 `setConfigOptions` 设置——独立离屏截图脚本必须手动复刻，否则黑底、且图像分析器会跟着误报"黑白割裂"（本次靠 PIL 像素统计证伪）；②视觉验证结论要交叉验证：同一分析器对同一图可自相矛盾（图例"半透明"vs"不透明"），色一致性靠代码层同源保证（图例 symbolBrush 与柱 brush 同 `intColor(k,hues)` 参数）比靠读图可靠。
- **M8.2 视图观感精修（用户三截图反馈驱动）**：①**堆叠系通道名行首内嵌**——各通道平均/单段浏览两视图的通道名从 y 轴 setTicks（25 导联必挤叠，用户截图证实）改 `_draw_stacked` 里 TextItem（`anchor=(0,0.5)`+半透明白底+行首行基线 `setPos(times[0], i*spacing)`，M6 浏览器同款）；预览 tab 矮，显式 **8pt** 压盒高（默认字号盒高≥行距相邻相触——坑 #57④）。②**蝶形图图例**——`_legend` 惰性建（`addLegend(labelTextSize="8pt")`+白底+灰框+`setColumnCount(ceil(n/12))` 分列）；`_redraw` 统一 `legend.clear()+hide()`（clear 清条目不清框——坑 #57②）。③**切视图 ticks 残留清理**——`_make_plot` 预置+`_redraw` 统一 `getAxis("left").setTicks([])`，`_draw_tfr` 里 `setTicks(None)` 恢复自动频率刻度（单段浏览→时频左上角飘通道名的根因+蝶形→时频频率刻度被砍暗病——坑 #57①）。验证：pytest **261 绿**（+4）+ e2e_m8 13 项 + e2e_m81 12 项零回归 + smoke + 离屏渲染 25 通道四视图截图亲眼确认（分析器辅助读图：标签盒高<行距/图例 3 列全可见/时频无残留）。
- **M8.1 三锚定分段+时频观感+单段浏览（用户三问题反馈+时频截图驱动）**：①**epoching 三锚定**——`EpochingParams.anchor/step_s/anchors_s`（中文 Literal 值兼作下拉显示与序列化值，冻结格式；默认事件锚定=旧 JSON 零回归）；锚点构造 `_events/_fixed/_manual_anchors` 三个 @staticmethod 统一返回 (samples, codes, event_id)，apply 三分支分发+尾段共享；滑窗/手动**不查事件表**（CSV/HDF5/ds1/ds4 无事件数据可分段）；手动越界 StepError 列全部无效锚点；锚点样本域构造防 off-by-one。②**时频三修**——`_draw_tfr` 末尾 `autoRange()`（堆叠/蝶形 setYRange 禁用 autoRange 的残留压扁根因）；配色下拉 `_TFR_CMAPS=("viridis","jet","hot")`（jet/hot 公式 **uint8** 生成——坑 #56①；换色不扰动 levels）；`_tfr_cache: dict[int, tuple]` 按通道缓存（命中同步绘制零线程；`_on_tfr_done` 守卫回填）。③**第五视图「单段浏览」**（索引 4 append 尾部保 e2e_m8 寻址稳定）——`_draw_stacked(rows_uv)` 与平均视图共用；段号 SpinBox+◀▶+←→（QShortcut WidgetWithChildrenShortcut 作用域限预览内）。验证：pytest **257 绿**（+15）+ e2e_m81 **12 项**（滑窗 538 段样本域公式现算）+ e2e_m8 13 项零回归 + smoke。
- **M8 分段分析可视化（"可以按计划继续开发"，v2 第二里程碑）**：①**EpochsPreviewView 四视图重构**——构造一次取齐 `_data/_times/_codes/_ch_names/_sfreq` 缓存（切换零重算）；视图下拉 + 通道下拉（单通道/时频模式启用）；`_redraw` 分发并**复位时频残留**（invertY/轴标签/LUT——坑 #55）；teardown 幂等（`_data=None` 早退 + 二调保护，e2e fixture 与关 tab 双路径）。视图=堆叠（M3 零回归）/蝶形（`pg.intColor(i,hues=n)` 同坐标+零线）/单通道（逐段 alpha-60 灰细线 + 按事件码 `event_color` 分色平均粗线 + 尾部 TextItem 标码——不用 legend 防 clear 状态残留）/时频（`run_in_thread` 后台算 `compute_epochs_tfr`，ImageItem+setRect+invertY+HistogramLUT；迟到回调双保险丢弃）。②**`features/tfr.py`**：morlet 段平均功率→基线 dB；频率轴 2-45Hz 对数 24 点、n_cycles=max(freqs/2,2)、段数上限 80、基线需 `times[0]<0` 且 ≥2 采样点否则峰值归一（tfr_array_morlet 的 (None,0) 在 tmin≥0 只罩单样本）。③**`BandPowerParams.time_windows`**：`起-止` 秒可负；epochs 相对事件锚点/raw 绝对秒；越界容差一个采样周期；窗进特征名 `alpha@0-1s`；spans=`[(None,"")]+窗`——整段条目始终并存，默认空零回归。验证：pytest **242 绿**（+29：tfr 17 含真实 A01T/四视图 8/time_windows 4）+ e2e_m8 **13 项**（守恒式 8.2%<12%）+ e2e_m1–m5/m7/smoke 回归全过。

- **M7 信号质量体检（"直接按计划开始推进开发"，v2 首里程碑）**：`features/qc.py` 双入口一算力——`compute_channel_qc(get_window 闭包)` 纯函数（浏览器传 `rec.get_window`、提取器传 `ctx.raw` 分窗闭包；`_plan_windows` 均匀撒窗拼接，LAZY 不整载）+ `QualityCheckFeature` 注册（qc 排"添加特征"菜单首位；**通道选择与 pick_channels 相反——坏道参检不排除**）；指标=开路复用/死值/平直占比/钉极值占比（无绝对阈值）/漂移 µV/min/直流中位（只进指标不定级），三级 good/suspect/bad。浏览器：工具栏「质量体检」→ `run_in_thread` 防重入 → 列表 ✓/?/✗ 前缀 + tooltip 中文明细（`_refresh_ch_list_text` 统一拼前缀+偏移，blockSignals 包 setText/setToolTip）→ 坏道**建议确认**（question 弹窗 Yes→逐个 `toggle_bad`，复用现有灰显/info["bads"]/bads_changed，不静默改 bads）。**黄金标准全复现**：羊 CH5-8 开路复用 4 坏、CH1-4 真信号不坏（实测判疑似——低频峰值平台 2.3% 触发疑似线，属设计语义）、TPDJ-位置1 八通道全坏（M7 精化 M6.7b"全平"概括：平线型 CH2/4/8 含 CH2≡CH4 复用 + 钉满量程跳变型）；02号脑电 2 文件顺带诊断入册（DATA_NOTES §8）。验证：pytest **213 绿**（+20）+ e2e_m7 **16 项×2 幂等**（坑 #54：须逐模块 patch signal_browser.QMessageBox）+ e2e_m1–m5/smoke 回归全过。

- **M6.8 浏览器四功能（用户四项需求驱动）**：①**行居中开关**（`_center_cb` 默认开=M6.7b 行为；关=绝对电平 `out_v*gain` 无行偏移 + `_apply_y_range` y 自适配本窗口数据±2%，绝对模式行标签贴曲线中位 `ch["_med"]`）；②**通道列表直流偏移显示**（后台 `_compute_channel_offsets`：≤20 个均匀 2s 窗分窗中位数取中位数，不整载 LAZY；主线程 `blockSignals` 包住 setText 拼 `"CH1  +68.9k µV"`；名称权威源迁 UserRole——右键/坏道不得再用 item.text()）；③**增益输入框**（QDoubleSpinBox 0.01–100× 权威源，三入口统一 `_set_gain(float)`：滑杆粗调吸附/键盘 ±1.0 dB×10 保小数/`_gain_syncing` 防环——坑 #53）；④**总览时间轴滑块**（EventLane：LinearRegionItem 逐线冻结边缘=只平移、x 三重锁死 [0,dur]、`set_viewport`/`viewport_moved` + `_syncing` 双向防环；browser `_on_lane_viewport` 只取中心按自身宽度重锚——坑 #52）+ **±1s 按钮**（`_step_s`）。验证：pytest **193 绿**×2（+22：TestStepSecond/TestGainInput/TestDcToggle/TestChannelOffsets/TestOverviewLane——event_lane 首次有测试）+ e2e_m1 22 项 + e2e_m3/smoke 回归 + 真窗口 DGDJ-位置4 四态截图亲眼确认（A 居中+列表偏移 / B 绝对 y 自适配含饱和平线 / C 2.50× / D 回居中+滑块 [31,41]+时间标签 36.00s/76.0s）。

- **M6.7b "第二个数据打开后 tab 空白"修复（用户四连开截图驱动）**：**不是加载问题**（日志无错误、worker 健全、refresh 跑完）——是显示几何问题。两个根因都已修：①主因 = y 锁定 + 堆叠假设基线 0，clinicaldata（BioSemi BDF **DC 耦合**）通道带 4.5k–69k µV 直流偏移 → 曲线画在锁定 yRange 外数千 µV 处，工具栏/标签照常画="加载成功的空白"；修法 = **行居中**（每通道减本窗口中位数再贴行，坑 #49）。②次因 = `minmax_decimate` 双 t 笔误（随 M6.6 潜伏，坑 #50），包络档上半包络塌 0。**"第一个能看"是巧合**（位置1 偏移恰好落在范围内）。验证：pytest 171 绿×2 + e2e_m1/m3/smoke 回归 + 真窗口四连开（用户精确时序 0/11/13/14s）逐 tab 截图亲眼确认 4/4 波形可见（含用户截图中空白的 位置4）。clinicaldata 通道质量定论已写入 DATA_NOTES §8（CH5–8 饱和平线、TPDJ-位置1 全平无信号）。

- **M6.7 浏览渲染修复 + 工作区测试污染事故修复（用户"10s 密集/9s 发虚"反馈驱动）**：①signal_browser 两档绘制——raw 透传 `connect="all"`（旧版无条件 pairs 隔段漏画=虚线根因）、抽取阈值 `_SAMPLES_PER_PIXEL` 2→3（Retina 逻辑px 下 9s/10s 恰跨旧阈值的悬崖，见坑 #48）、antialias 恢复 True；新增 TestRenderTwoModes 回归 2 项（pytest 165 绿）+ e2e_m1/smoke 回归。②test_ui_workspace_remove fixture 三重隔离重写（坑 #47）：旧 teardown 清的路径从不存在 + `current_workspace.txt` 标记被劫持不恢复——**用户 08-27 当天 1574 条真实导入曾被困在 `test_删除_*` 测试名目录里**，已修复（清合成来源并入 默认工作区 1572 条/7 来源、标记恢复、残留目录清除；完整备份 `/tmp/dataloadv_repair_backup_20260827_160326`）。

- **M6.6 工作区移除条目 + 羊通道质量定论完成（用户两问驱动）**：①"读出来都是噪声"——诊断定论（零代码改动，结论入 DATA_NOTES §1）：**不是读取 bug**——羊 CH5–CH8 逐样本完全相同（开路通道复用，钉 ±375000µV 饱合或 std=0）、CH4 部分饱和；CH1–CH3 真实皮层信号（去直流+带通后 std≈279µV）带大直流偏移；换算 0.125µV/LSB 正确。**用法**：右键标 CH4–CH8 坏道 + 对 CH1–CH3 加去均值/重参考+带通 1–40Hz 预览。②树右键/Del 移除条目：`remove_requested(list)` → `_remove_from_workspace`（多条确认 → remove_recording+save+notify）——**只清工作区索引不删磁盘文件**，已开 tab 保留。pytest 163 绿（+6；**须 offscreen**，坑 #45）+ e2e_m1 19 项 + smoke 回归（见 review.md M6.6 节）
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
