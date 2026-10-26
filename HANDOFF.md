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
| PyInstaller（M10 打包） | 6.22.2 | conda-forge（`conda install -n dlv -c conda-forge pyinstaller`） |

> neo/pynwb 是**可选依赖**（import-guard）：缺失时应用照常运行，只是 NWB/Blackrock/OE/Intan 格式不可用。

## 运行与测试

```bash
conda activate dlv
dataloadv                                    # 启动应用（或 python -m dataloadv）
QT_QPA_PLATFORM=offscreen pytest             # 全部单测（2026-10-26 M15：375 passed，含 real 数据项；
                                             #   MainWindow 级测试须 offscreen——坑 #45）
pytest -m real                               # 仅真实数据冒烟（data/sheep 缺失自动跳过；建议同带 offscreen）
python scripts/e2e_m9.py                     # M9 端到端：连续导出 EDF/FIF+批处理逐文件（幂等；须 offscreen）
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

## 打包（M10）

```bash
# 本机 macOS 包（dlv 环境、项目根；产物 dist/DataloadV.app + onedir 目录 dist/DataloadV/）
python -m PyInstaller dataloadv.spec --noconfirm          # 全量 ~40s，解压 293MB
cd dist && zip -r -y DataloadV-<版本>-macOS-arm64.zip DataloadV.app   # 版本取 pyproject；-y 保符号链接

# 打包产物无头自检（app 内置 --smoke 分支：起主窗口自检后自动退出）
QT_QPA_PLATFORM=offscreen dist/DataloadV.app/Contents/MacOS/DataloadV --smoke   # 末行 SMOKE OK

# Windows 包：push 后 GitHub Actions 出（.github/workflows/build.yml，
#   workflow_dispatch 手动触发或 push tag v* 发版；产物 DataloadV-{ver}-win64.zip）
#   CI runner 用 setup-python 3.10 + pip install -e ".[extra-readers]" pyinstaller——
#   PySide6/mne/edfio/neo/pynwb 全走 pip（runner 无 conda-forge Qt；pip 版 PySide6 在
#   win 正常）。与 dlv conda 环境等价性：核心包同名同主版本（PySide6/pyqtgraph/mne/
#   edfio/neo/pynwb/numpy/scipy/pandas/h5py/pydantic），来源渠道不同（conda-forge vs
#   PyPI wheel）——二进制同为官方发布，行为等价；Windows 侧首跑后须真人双击验收
```

## 架构导览（M16 清理后的实际结构；MANUAL §1.5 为缩略版，本节为权威）

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
│   └── nwb_reader.py        # NWB（M5，可选）
│
│   （export/ 尚有 continuous_io.py——M9 连续数据 EDF/FIF 导出）
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
│   ├── spectral.py          # mean_welch/array_welch + BandPowerFeature（δθαβγ+自定义+相对/对数+time_windows）+ WelchPsdFeature（仅 raw）
│   ├── units.py             # feature_unit 特征名→单位映射（M14，图表纵轴用）
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
│   ├── continuous_io.py     # 处理后连续 raw → EDF（channelwise 16-bit）/ FIF（float32 _raw 后缀）（M9）
│   └── provenance.py        # <名>.pipeline.json：app/pipeline/features/recordings/library_versions/extra
├── workers/generic.py       # run_in_thread：后台任务→_MainRelay 主线程回调（见坑 #7/#13）
├── packaging/entry.py       # PyInstaller 入口 shim（console_script 等价 5 行；spec 指向它）（M10）
│                            #   dataloadv.spec（仓库根）：单份跨平台——darwin 出 .app/win32 出
│                            #   onedir .exe；hiddenimports+collect_submodules+数据文件（坑 #59）
└── ui/                      # 全部 Qt 代码
    ├── main_window.py       # 主窗口：导入/浏览/特征/批处理结果 tab、设置、采样率询问
    ├── state.py             # SessionState 信号中枢（recording_opened 等）
    ├── strings_zh.py        # 全部中文文案集中（class S；M5 段 BATCH_*/SET_*）
    ├── dialogs/import_dialog.py   # 导入控制器：worker 扫描→进度→错误表
    ├── dialogs/batch_dialog.py    # 批处理两页对话框：选择(过滤/全选/导出组)↔运行；queue.Queue+QTimer 事件泵（M5）
    ├── dialogs/settings_dialog.py # 设置：线程数/缓存 GB/默认导出目录（M5）
    └── widgets/             # workspace_tree / meta_table / signal_browser / event_lane /
                              #   event_list（M11 事件清单）/ feature_charts（M8.3/M14 图表区）/ log_panel /
                              #   event_list（M11 事件 marker 列表：双击行 _center_at 定位；M12 移入左栏）/
                              #   signal_browser（M12：比例尺下拉/紧凑显示/三行 gfx 主图+同段时频图
                              #   turbo+turbo 色标+事件条，setXLink 像素对齐见坑 #64）/
                              #   log_panel
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
57. **M8.2 pyqtgraph 0.14 刻度与图例的五则**（离屏实测）：①`AxisItem.setTicks` 三态——`[[...]]` 自定义刻度、`[]` **空刻度（无任何刻度）**、`None` **恢复默认自动刻度系统**；内部 `_tickLevels` 可读（自定义=列表、空/自动后=None/[]，断言"无自定义刻度"用 `not _tickLevels` 兼容两态）。**切换视图不复位 ticks 就是残留**（通道名 ticks 经 invertY 翻到左上角飘字的根因）。②`plot.clear()` **会**清 LegendItem 条目（`leg.items` 变空——M8 "不用 legend 防 clear 状态残留"的顾虑在 0.14 不成立），但**图例框本身不清**（空框仍显示）——须手动 `legend.hide()`。③LegendItem 0.14 默认 **NoBrush 无底框**（文字直压曲线），`setBrush(mkBrush(255,255,255,210))`+`setPen` 加底；**`columnCount` 是 int 属性不是方法**（`setColumnCount(n)` 是方法）——单列条目多时矮窗口排不到底被截断，`setColumnCount(ceil(n/12))` 分列。④`TextItem` 有 `setFont` 无 `font()` getter——取回走内部 `t.textItem.font()`（QGraphicsTextItem）；堆叠行内嵌标签在矮窗口（500px/25 行）默认字号**盒高≥行距相邻相触**，显式 8pt 压盒高（M6 全高浏览器不受此限保持默认）。⑤离屏 `QFont()` 默认族在 macOS offscreen 有一次性 50ms 字体族别名告警（无害）。⑥**全量 pytest 期间别并发 e2e/smoke 等 QT 重活**：曾出现 pytest 死等（主线程 QEventLoop::exec、后台线程全 cond_wait，CPU 归零）——kill 重跑即过（-v 日志同批测试全绿），属并发负载下的偶发竞态非测试问题；macOS 抓 Python 栈 py-spy 要 sudo，用系统 `sample <pid> 2 -file` 看特征帧（exec/cond_wait）即可判"挂"还是"慢"。**2026-09-07 第二次实证**：全量 pytest（`| tail` 管道）期间并发跑 python 验证脚本（纯 io/numpy 无 Qt）→ 224 位出 E + 挂死（ps 判据：进程 25 分钟累计 CPU 仅 6.4s）；kill 后 `-v` 直写文件重跑 **298 绿 6.3s** 零 E——并发窗口内即使非 Qt 脚本也可能踩中；另：`| tail` 管道让挂死无进度可见（坑 #36 自食），全量回归一律 `-v` 直写文件。
  **2026-10-13/14 Heisenbug 挂死（✅ 2026-10-14 根因闭环：qtbot.waitUntil 的 Qt 侧超时会饿死）**：全量
  pytest 在高负载系统（load 4.7、机器 61 天未重启）下 ~50% 概率挂死——主线程
  QEventLoop::exec、worker 全 cond_wait、CPU 归零（#57⑥ 同族但挂率异常高）。**已确认
  事实**：①挂点漂移但集中在 test_ui_browser_m12.py 尾部至 m6 首测试之间（215/216 项
  交界，即 m12 全部完成后 qtbot 清理链/m6 开场）；②最小组合 m12+m6 可复现（3 轮 1 挂，
  -q 模式；同组合 -v 4 轮全绿，但全量 -v 亦挂过 1 次——输出模式非决定性）；③观测手段
  一介入（-s / faulthandler 包装）就不挂（Heisenbug 本征）；④faulthandler.dump_traceback
  _later 的 dump 会落进 pytest 的 fd 捕获——须 -s 才可见；⑤pytest-qt 的 waitUntil 内部
  是 QEventLoop.exec + QTimer 超时（wait_signal.py:26/639）——**事件分发饿死时超时本身
  失效 → 永等**，这正是挂死的形态学解释。**已做的防御**：test_ui_browser_m12 全部等待改
  `_poll_until`（Python 层 time.monotonic deadline + qtbot.wait(50) 轮询——超时检查不
  依赖 Qt 事件，最坏 15s 明确 FAIL 而非永挂）——**挂死仍发生**，说明还有别的 exec 入口
  （嫌疑：qtbot fixture teardown 的 widget 清理链/pytest-qt 内部等待，未定位）。
  **接手排查线索**：先重启机器（排除 61 天累积的内核状态）复测挂率；若复现，用
  `pytest tests/test_ui_browser_m12.py tests/test_ui_browser_m6.py -q` 循环复现 +
  lldb attach（sample 拿不到 Python 帧，py-spy 需 sudo）；重点查 pytest-qt qtbot
  teardown 对 5 个 SignalBrowserView（各持 QTimer/PyQtGraph scene/后台线程 relay）的
  清理顺序。**根因闭环（2026-10-14，重启机器排除系统因素后）**：conftest 注入文件级时间
  戳探针（不经 pytest fd 捕获、不改变 Qt 时序——-s 观测会让它消失，纯 Heisenbug）→
  精确挂点=test_ui_browser_m6.py::TestGainInput 的 fixture setup 里的
  `qtbot.waitUntil(_loaded_once)`——**根因即 waitUntil 本身**（内部 QEventLoop.exec +
  Qt 侧 QTimer 超时，事件分发被饿死时超时失效 → 永等；M12 的 300ms TFR QTimer+后台
  线程活动只是放大了触发窗口，地雷从 M8 的 keepalive 等待范式就埋下）。**解法=全部
  16 处 qtbot.waitUntil 替换为 conftest 的 `wait_until`**（Python 层 time.monotonic
  deadline + qtbot.wait(50) 轮询——超时检查不依赖 Qt 事件，最坏明确 FAIL 不永挂；
  tests/conftest.py 共享、各测试文件 `from conftest import wait_until`）。替换后全量
  5 连绿（此前重启后仍 2/3 挂）+ e2e/smoke 回归过。**规则：本项目测试一律用
  `wait_until`，禁止 `qtbot.waitUntil`**；时间戳探针转常设，再有挂死看
  /tmp/pytest_trace.log 最后一个 START 无 FINISH 即精确挂点。（2026-10-14 又见一例**退出阶段挂**：trace 全部 FINISH 但进程不退——挂点在测试体之后（qapp/pytest-qt 清理段），探针测不到；kill 重跑即绿，低频，暂记档不深挖。）
58. **M9 连续数据导出的五则**（mne 1.12 / edfio 0.4.16 实测）：①**`mne.export.export_raw` 的 `physical_range` 默认 "auto" 按通道类型统一量程**——录制里混一个 ±375000µV 开路饱和通道（羊数据 CH5-8 就是），该类型 16-bit 步长被拖到 ≈11.4µV/LSB，正常 20µV 信号直接被量化抹平；**必须 "channelwise"**（每通道按自身 min/max 用足量程）。②**EDF 按整秒数据记录写盘**：`crop(0, 30)` 含端点 7501 样本 → 读回 7750（补到 31 记录）——断言时长用「≤1 记录补齐」口径，不能写死 `n_times == 30*fs`。③**FIF 文件名规约**：缺 `.fif` 后缀 `raw.save` 抛 OSError、缺 `_raw` 只是 warning——wrapper 主动补 `_raw` 保干净；mne≥1.9 `raw.save` 返回 fnames **列表**（2GB split），取 `[0]`。④**白名单外通道类型是 mne 导出的静默硬伤**：misc 等类型数据留 V 却标 µV（单位错标），必须在 wrapper 前置拒绝（eeg/ecog/seeg/eog/ecg/emg/bio/dbs/stim 之外）；通道名 >16 字符抛英文 RuntimeError、非 ASCII 时 edfio 编码直接炸——都前置转中文 ValueError。⑤**`QAction.triggered` 直连带参方法会把 `checked=False` 传进去**：`menu.addAction(text, method)` 的 method 签名带可选参（如 `export_processed(fmt=None)`）时 False 非 None、格式守卫失效——lambda 包一层；面板按钮 `clicked` 同理（M9 全部 lambda 接线）。

59. **M10 PyInstaller 打包的七则**（PyInstaller 6.22.2 / mne 1.12 / macOS arm64 实测）：①**spec 全局变量是 `SPECPATH`（str）没有 `SPECDIR`**——写 SPECDIR 是 NameError 秒退；用 `ROOT = Path(SPECPATH)`。②**mne 1.12 用 lazy_loader 惰性加载子模块，静态分析扫不到**——不处理则冻结环境 `import mne` 当场崩（`No module named 'mne.utils._logging'`，从 `mne.set_log_level` 的 lazy 属性链触发）；解法 `collect_submodules('mne')` 收全子模块**名字**（纯代码进 PYZ，几 MB），并剔除 `mne.tests`/`mne.testing`；neo（rawio 后端按格式名动态分发）/pynwb/hdmf 同款处理。③**`collect_data_files('mne'/'pynwb'/'hdmf')` 收数据文件最小集**（mne 通道模板/montage、pynwb/hdmf 命名空间 schema JSON）——实测够用，**不要 `collect_all`**（连测试数据几百 MB 一起拖）。④**warn-<名>.txt 的 "missing module named mne.utils.warn/verbose/logger" 是 lazy_loader 噪音**——真提供者（mne.utils._logging）已在 PYZ，冒烟通过是实证；delayed/optional 的 missing 条目不是待办清单。⑤**本机构建 .app 无 quarantine 属性**——本机双击不出 Gatekeeper 提示（`xattr` 无 com.apple.quarantine）；提示只在下载/他机拷贝的包上出现，`spctl -a` rejected 是未签名**预期**。mac 压分发包必须 `zip -r -y`（保 .app 内符号链接），Windows 用 Compress-Archive。⑥**CI runner 不用 conda**——setup-python 3.10 + `pip install -e ".[extra-readers]" pyinstaller` 装齐（pip 版 PySide6 在 win 正常），与 dlv conda 环境核心包同名同主版本、渠道不同但等价；CI 绿≠Windows 能跑，**必须真人双击验收一次**。⑦**app 内置 `--smoke` 分支**（main 里 argparse flag → smoke_gui.py 等价逻辑自检退出）——打包产物无头验证用 `QT_QPA_PLATFORM=offscreen <二进制> --smoke`；改动遵循"最小化"（不动 MainWindow、不加新模块）。另：全量打包实测仅 293MB（预判 1.2–1.8GB 未发生），瘦身不值得冒险动 excludes——体积让位可用性。

60. **M10-3 CI 首跑 Windows 只炸 upload-artifact 的根因：`Compress-Archive` 的 `-DestinationPath` 不写目录 = 相对 CWD（仓库根），不是相对 `-Path` 的源目录**——产物 zip 落在仓库根而 upload-artifact `path: dist/DataloadV-*-win64.zip` 去 `dist\` 找，`if-no-files-found: error` 在最后一步报错（PyInstaller 打包与压 zip 本身全成功，别误诊成构建问题）。mac job 是 `cd dist && zip` 所以没踩。修法：`-DestinationPath "dist\DataloadV-$VER-win64.zip"`。教训：①**产物写出路径与 upload path 要逐字对账**（双平台 job 步骤对称 ≠ 路径语义对称）；②pwsh 相对路径锚定 CWD，跨平台 workflow 里写全相对前缀最稳；③CI 失败先看失败的是**哪一步**——步骤级 API（`/actions/runs/{id}/jobs`）免凭据可查，日志下载才需要 token。

61. **初始窗口尺寸硬编超屏 + Dock 首布局用构建期 hint（M10 后 Windows 真机反馈，2026-09-01 修复）**：`self.resize(1440, 900)` 在 1366×768 笔记本或 1080p@125% 缩放（有效逻辑高 864）上**超出屏幕**——右侧处理 Dock（面板最小宽实测 419，@125% ≈524）被屏幕边缘直接裁掉；用户"全屏→恢复正常"的机理：最大化触发 QMainWindow 整体重排、还原后 Dock 保持适配尺寸。修复两件套（main_window.py）：①初始尺寸按主屏 `availableGeometry()` 收口并居中（大屏保持 1440×900）；②`showEvent` 首次显示时 `resizeDocks` 按面板**当时**（过 DPI/字体 polish 的）`sizeHint` 显式定左右 Dock 宽（自动下限=面板最小宽，不会压瘪）——QMainWindow 首布局用的是构建期 sizeHint，Windows 高 DPI 下与 polish 后的真实值有偏差。**测试坑**：offscreen 平台默认屏 800×800（正好是小屏模拟），但本 PySide6 6.11 构建忽略 `QT_QPA_PLATFORM=offscreen:screenSize=WxH` 参数（实测恒 800×800）——大屏用例只能打桩模块级 `QGuiApplication`（沿坑 #31/#54 patch 先例），测试见 test_ui_window_sizing.py。

62. **EDF 头 physical_dimension 写非标单位串 = 幅值显示放大 10⁶（sheep4 定论 + 应用兜底，2026-09-07）**：新设备导出的 `ZJDJ-260906-0101.edf` 把 16 通道单位字段全写成 **`AuV`**——mne/edfio 的单位白名单不认它，读取时**不换算、物理值裸当伏特**，应用比例尺显示 10⁶ µV（数据实际 std≈1.2，本意微伏）。**排查指纹**：①比例尺/幅值比预期大 10⁶ 倍；②`edfio.read_edf` 逐信号看 `physical_dimension` 是否在 `uV/mV/V` 等标准串内；③数字值 std 极小（~6 LSB）说明信号本身没饱和没坏。**双修复**：A）`scripts/fix_edf_unit.py`——字节级只改头内单位字段（布局按坑 #44 字段主序，dim 区 `256+ns*96`，每信号 8B；逐通道 `--from` 精确匹配防误伤、Annotations 空字段自动跳过），数据区零改动（ADC 数字值逐位一致实证），输出 `_fixed.edf` 副本、原文件不动（data/ 只读）；B）**应用内自动兜底**（`io/mne_readers.py` EdfReader）——load_raw 后 `_scan_nonstandard_edf_units` 扫头（几百字节），非标数据通道按 µV 缩放 ×1e-6 + warning + meta.notes 打 `EDF_UNIT_FLAG` 待提示标记，UI 打开时弹一次告知框后清标记（main_window._notify_edf_unit_fallback，FS_UNSET 同款机制）；**B 与 A 殊途同归**（兜底读原文件 == mne 读修复副本，allclose 实证）。**实现要点**：mne 白名单 = µV 三种码位变体/uV/mV，"V" 本义伏特也归标准、空单位不猜（语义未知）；`read_raw_edf` 的 `units=` 参数**不能覆盖已写单位**（文件有单位且与传入不同直接 ValueError）——只能读后缩放；LAZY 请求在非标件上强制整载（lazy 数据按需从文件读无法原地修正，非标件罕见整载换正确性值得）；正常件路径零改动（lazy 保持、数值逐位一致）。测试 test_io_edf_unit_fallback.py 8 项（含 MainWindow 弹窗清标记，win fixture 三重隔离）。**注意**：EDF 头里"数字值→物理值"换算由 phys/digital min/max 决定（这个设备写对了），单位字段只影响读入方的**量纲解释**——所以错单位不动数据、改标签即愈。

63. **`QTableView.setSortingEnabled(True)` 会触发一次隐式初始排序，行为不可依赖（M11 实测）**：本 PySide6 6.11 构建实测启用时按**第 0 列降序**排（Qt 文档未承诺此行为，proxy 初始顺序因此不确定）——事件列表首跑双击"行 2"实际命中 source 行 0。规则：①启用排序后**必须 `horizontalHeader().setSortIndicator(列, 序)` 显式定初始序**（本项定为时间列升序=事件清单天然序），箭头显示与实际排序一致；②测试/调用方**不得硬编码 proxy 行号**——按业务键（如 onset）经 `onset_at_row` 反查目标行；③显隐断言用 `isHidden()`（显式 setVisible 语义）而非 `isVisible()`——offscreen 下顶级窗口未 show，isVisible 恒 False。

64. **M12 浏览器四项改造的五则（pyqtgraph 0.14 / mne 1.12 实测）**：①**`setXLink` 是像素对齐不是复制范围**——两图数据区需在屏幕重叠，左轴宽度不等时主图 [30,40] 映射成副图 [30.56,40]（事件时间错位 0.56s，Plan agent 离屏实测）；解法=三行左轴统一 `setWidth(46)`（主图/事件条从"整体隐藏"改"定宽空刻度"，常量 `event_lane.ROW_AXIS_W`）；link 必须在首次 setXRange 前建立（构造顺序天然满足，注释固化）。②**mne 时频 Nyquist 硬边界**：sfreq=80 文件默认 2–45Hz 抛 "Cannot compute freq above Nyquist"——必须钳制自建频率表（初版 0.475；**M13 精修后 = min(150, Nyq×0.49)**，见 TfrConfig）；**短窗硬边界**：<2s 抛 "wavelet longer than signal"（2Hz 核≈1.6s）。③**浏览器 TFR 防抖必须用实例 `QTimer(singleShot).start()`**——重启即取消旧定时；`QTimer.singleShot` 不可取消，连续拖动会堆叠计算。④**复位类按钮批量 setCheckState 要 `blockSignals` 包住**——否则 N 次 itemChanged→N 次刷新（与 `_refresh_ch_list_text` 同模式）。⑤**e2e 时频 rect 断言口径**：双击跳转居中 0 时视口 [-5,5] 左半为负（无数据段），TFR image 只覆盖 `get_window` clamp 后的实际窗 [0,5]——断言用视口与数据域 [0,dur] 的**交集**，别拿视口直接比。另：raw 窗口 TFR 的 dB 口径是"相对各频点峰值"（times≥0 无基线分支），文案勿复用"基线校正"。⑥**ColorBarItem 的联动方向是单向 cb→img（离屏实证）**：`cb.setLevels(low, high)` 自动同步绑定的 ImageItem；`img.setImage(autoLevels=True)` **不**联动 cb（色标留在旧范围）——程序侧更新范围一律经 cb.setLevels；用户拖动结束发 `sigLevelsChangeFinished`（程序 setLevels 不发，可安全用作"用户调过"的锁定信号）；无内置双击行为，eventFilter 拦 GraphicsSceneMouseDoubleClick 自定义。**HistogramLUTItem 慎用于纯展示场景**：自带渐变编辑器（色标上双击/拖动会生成多个三角切分点），用户会误触且无意义——只需色标+范围时用 ColorBarItem。
  ⑦**M13 时频四方法四则**：a）**invertY(True) 与 ImageItem y 向下坐标的组合实际
  朝向是高频在下**（`vb.mapFromView` 像素实证；M8 起两处注释"低频在下"均写反——
  浏览器 M13 已去 invertY 翻转、epochs_preview 仅勘误注释行为未动）；b）
  **`tfr_array_stockwell` 恒返 3 元组** (psd,itc,freqs)（return_itc=False 也是 3 个，
  itc=None；psd (n_ch,n_f,n_t) 频率线性数千格、fmin/fmax 不含精确端点、超 Nyquist
  **静默截断**——与 morlet/multitaper 的 ValueError 不同，统一在 cfg.effective_fmax
  钳制）；c）**线性轴方法抽行必须分段 max 池化**——均匀抽样实测漏窄峰（stockwell
  1933 格抽 40 行行距 2.9Hz > 10Hz 正弦 0.06Hz 峰宽，峰差从 9dB 掉到 -0.8dB）；
  d）三个 tfr_array_* 在 mne 1.12 均挂 @legacy（统一入口 compute_tfr 存在）——array
  版仍完全可用，项目沿用。四方法耗时（10s@250Hz）：morlet 3ms/multitaper 20ms/
  stockwell 130ms/stft 0.2ms。
  ⑧**scipy.stft 返回相对窗口的 0 起时间轴**（2026-10-14 用户真窗口暴露）：morlet/
  stockwell 分支沿用调用方传入的绝对秒，stft 的 t 却从 0 起——窗口在 [30,40] 这类位置
  时热图 rect 落在时间轴 0-10s（视口外）=「图没加载出来」；离屏默认 [0,10] 窗口的测试
  碰巧撞对放过了它。修：stft 分支平移回绝对时间 `t + times[0]`；回归哨兵=非零窗口
  断言 rect.left。**教训：跨方法统一三元组约定时，每个方法的坐标语义（绝对/相对）要
  逐一核对，测试别只用默认窗口。另：`_set_x_range` 路径的两级防抖（30ms refresh +
  300ms TFR）窗口内 timer/running 都是"未跑"状态——负向条件（not isActive/not running）
  全部提前满足，等待必须用正向业务终态（`_tfr_seq` 递增）——本坑第三次实证。
  ⑨**M14 图表三则**：a）pg 0.14 箱线是 **`pg.BoxplotItem`（小写 p）**，`hasattr(pg,
  'BoxPlotItem')`=False；正确用法 `BoxplotItem(loc=[...], data=[每箱样本数组...],
  width=, pen=, brush=, medianPen=)`——旧式 x/height 参数**不报错但静默画不出**
  （generatePicture 只读 loc/data）；默认须长 IQR×1.5、outlier=True 收集离群点。
  b）**`GraphicsLayout.items` 是 {item→'list'} 注册表**——keys() 才是布局内控件
  （values() 是属性名字符串，拿 PlotItem 用 items.keys() 过滤 isinstance）。
  c'）**并排条形/箱线的"贴合"要用槽位制根除**（2026-10-15 四次迭代教训）：组内均分制
  （组宽/n_ser 再乘填充系数）下系列间绝对间隙只有百分之几通道距——改填充系数
  （0.9→0.68→0.55）三轮都"看不出变化"（间隙像素级）；散点 jitter 越箱缘还会把间隙
  填满。定稿：**每（通道×系列）独占宽 1.0 的 x 槽位**（x=j*n_ser+k），箱/柱宽恒定
  槽距比例（0.55/0.9），刻度放组中心 j*n_ser+(n_ser-1)/2——空隙 45% 槽距恒定，
  与系列数无关。
  c"）**BoxplotItem 遇 NaN 值组闪退**（2026-10-15 用户滚动崩溃，日志实锤）：pg 的
  IQR_1p5 须函数 `np.max(data[data<=upper_theory])`——NaN 比较恒 False，组内全 NaN
  或混合时筛选结果空数组 → np.max 抛 ValueError → ViewBox.prepareForPaint（滚动重绘）
  全链崩。NaN 源头：常数序列（饱和/平线通道）的 scipy kurtosis 返回 NaN。**修在
  数据入口**（groups 构造滤 NaN）而非替换 whiskerFunc——单点防御。教训：喂 pg 绘制
  项的数据先滤 NaN（pg 大量 `data[mask]` 聚合无空数组防御）。
c）**FeatureTable.to_wide 的 aggfunc="first" 丢同键重复值**——需要原始值分布
  （箱线/ violin）的场景直接用长表 df groupby；另：**特征单位映射**在
  features/units.py（后缀规则+qc 特殊表+bandpower 判定；未知名兜底 "" 不猜）。

65. **中文 Windows GBK locale 读 UTF-8 资源必炸 + PEP 540 UTF-8 模式自举（v0.2.0 Windows 实锤，2026-10-19 修复发 v0.2.1）**：用户中文 Windows（ANSI=GBK/cp936）打开任何数据必崩——`signal_browser._build_ui` 的 `pg.colormap.get("turbo")`（M13 起浏览器构建必经）→ pyqtgraph `colormap._getFromFile` 的 `open(filename,'r')` **不带 encoding**（平台默认编码）→ `UnicodeDecodeError: 'gbk' codec can't decode`；macOS locale 即 UTF-8 故本机全绿——**"本地绿 ≠ 用户绿"的 locale 维度**（继坑 #61 DPI 维度之后第二例）。字节级疑点存档：dlv（conda）与 PyPI 两渠道 pyqtgraph 0.14.0 的 73 个渐变 CSV 实测均 GBK 安全纯 ASCII（dist 内逐字节比对一致），用户包内哪个文件含非 ASCII 字节未能本机复现（手机照片 OCR 的字节/位置细节存疑）——但机制确定（无 encoding 的 open），同类隐患含 mne/pynwb 等库的资源读取。**修法=类级根治**：新 `dataloadv/_utf8.py` 的 `ensure_utf8_mode()`——Windows 且非 UTF-8 模式时设 `PYTHONUTF8=1` 并 `execv` 自重启一次（PEP 540 UTF-8 模式只能启动时生效；`DLV_UTF8_RESTARTED` 标记双保险防异常环境下的重启循环）；在 `packaging/entry.py` 与 `__main__.py` 的 **import 重库之前**调用（`dataloadv/__init__` 纯常量，导入 `_utf8` 不触发 Qt）。代价：Windows 冷启动多一次进程拉起（约 1s，无感）。测试 test_utf8_bootstrap.py 打桩 os.name/sys.flags 验证分支；真机证明靠 Windows 复验。

66. **execv 的 args[0] 是程序名占位 + windowed 模式 sys.stderr 为 None（v0.2.1 事故，2026-10-19 当天修复发 v0.2.2）**：v0.2.1 在中文 Windows **双击直接打不开**——自举写 `os.execv(exe, [exe, *sys.argv])` 把 `sys.argv[0]`（exe 路径本身）**重复拼成了位置参数**，子进程 argparse 遇未知位置参数走报错路径 → `print_usage` 写 `sys.stderr` → **console=False 的打包版 sys.stderr 是 None** → `AttributeError: 'NoneType' object has no attribute 'write'` → PyInstaller 弹 "Unhandled exception in script"（用户照片 traceback 实锤：entry.py:20 → app.py main → argparse）。三层教训：①**execv 参数语义**——args 列表 [0] 位是程序名占位，不是要追加的参数；原进程 argv[0] 绝不能再拼入（冻结态 `[exe, *sys.argv[1:]]`，源码 `python -m` 态须重建 `["-m", "dataloadv", ...]`——参数构造收敛到 `_restart_argv()` 并有形态回归测试）；②**windowed 打包版的 sys.stderr/stdout 是 None**——任何写它们的库路径（argparse 报错、print、第三方 warning）都会 AttributeError，main() 入口垫 devnull 兜底；③**macOS 上 no-op 的平台分支，单测必须覆盖参数构造**——真机行为拦不住时，把"将传给系统调用的值"的断言做全（本坑的 frozen/source 两形态断言就是当时缺口）。另：execv 包 OSError 兜底（杀软拦截时清标记照常启动——自举是增强不是依赖）。

## 当前接手要点（2026-10-26，M16 全项目清理完成；M11–M15 均已交付）

- **唯一真实待办**：用户 Windows 复验 v0.2.2 打包版（TODO 末条）。
- **M11 事件 marker 列表**：左栏下方（M12 自底部移入）；双击行 `_center_at`；面板常驻
  （空态"无事件"——用户裁定，勿改回自动隐藏）。
- **M12 浏览器四项**：比例尺下拉（自动档**持续**重估——M15 改）、紧凑显示（`_row_map`
  每帧重算）、事件列表左栏、同段时频图（setXLink 像素对齐——三行左轴统一 46px，坑 #64①）。
- **M13 时频四方法**：`TfrConfig`+`compute_window_tfr`（morlet/multitaper/stockwell/stft）；
  fmax 默认 150、上限 Nyquist×**0.49**（250Hz→122.5）；线性轴方法分段 max 池化保窄峰；
  stft 时间轴须平移回绝对秒（坑 #64⑧）。
- **M14 图表区**：PSD y=dB/x=线性/`_PlainAxis` 普通数字刻度；特征网格默认箱线（jitter
  散点+槽位制 x=j·n_ser+k 根除贴合——组内均分制调参四轮无效的教训在坑 #64⑨）；
  NaN 特征值须在 groups 入口滤（pg IQR 须函数遇 NaN 闪退）。
- **M15 三件套**：全选/全不选切换；比例尺自动档持续重估；特征 channels 字段
  `_ChannelPickerEdit`（空=全部语义；无活动录制回退 QLineEdit）。
- **M16 清理**：代码层 40 项（死代码 24 处/注释过时 22 处）+ 文档计数校准（e2e 实测
  154 项）+ 六处冗余收敛（环境/版本/架构树/打包/数据/功能清单各留一份权威）。
- 打包版功能=发版 tag 时点：**v0.2.2 含至 M14+sheep4 兜底**；M15 及以后须发新 tag。

