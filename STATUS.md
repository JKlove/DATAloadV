# STATUS — 项目状态快照

> 本文件回答"现在做到哪了"。每里程碑完成及重要提交后更新。最后更新：2026-08-18（M5 完成，v1 收官）

## 当前里程碑

- **M5 批处理+扩展格式+收尾：✅ 完成（2026-08-18）**，验证全过（pytest 137 绿 + e2e_m5 19 项 ALL OK：45 个 2b GDF 批处理 45 成功 1 容错 78240 行特征 8.5s、UI 心跳全程响应、中途取消有效、sidecar 可复现，见 review.md）
- **v1 全部里程碑（M0–M5）完成**——后续事项见 TODO.md「Backlog」

## 里程碑总览

| 里程碑 | 状态 | 完成日期 | 说明 |
|---|---|---|---|
| M0 骨架+治理 | ✅ 完成 | 2026-08-18 | git 仓库、治理文件、conda env dlv、包骨架、主窗口、冒烟通过 |
| M1 工作区+EDF+信号浏览器 | ✅ 完成 | 2026-08-18 | Recording/Workspace/EdfReader(latin1)/导入/工作区树/元数据表/信号浏览器/事件条；E2E 全过 |
| M2 读取器全覆盖 | ✅ 完成 | 2026-08-18 | 8 格式 mne 模板家族 + ds1/ds4 mat + CSV/TXT + HDF5 + GDF 官方码表中文标签；4.9GB 扫描 5.9s/1606 条 |
| M3 预处理链+预览 | ✅ 完成 | 2026-08-18 | proc 层 6 步骤+序列化、管线面板+pydantic 自动表单、预览副本 tab+分段预览、PSD 对比、坏道标记联动 |
| M4 特征+导出 | ✅ 完成 | 2026-08-18 | crop 时间窗+3 提取器+FeatureTable 长表+特征面板（视口预填）+CSV/HDF5/FIF 导出+sidecar |
| M5 批处理引擎+扩展格式 | ✅ 完成 | 2026-08-18 | BatchEngine(纯 Python 线程池/取消/逐文件容错)+批处理对话框(队列事件泵)+neo(Blackrock/OE/Intan)+NWB 读取器+设置+README；e2e_m5 19 项 |

## 环境

- conda env：`dlv`（Python 3.10），安装命令见 HANDOFF.md §环境搭建
- 关键包版本：numpy 1.26.4 / scipy 1.15.2 / pandas 2.3.3 / h5py 3.16.0 / pydantic 2.13.4 / PySide6 6.11.0 / pyqtgraph 0.14.0 / mne 1.12.0（pip）/ edfio 0.4.16（pip）/ **neo 0.14.5（pip——conda-forge 无此包）/ pynwb 4.1.0（conda-forge）**（M5）

## 测试

- `pytest`：**137 passed**（M5 新增 15：batch 10——引擎容错/取消/导出/设置 + readers 5——NWB pynwb 真实往返/neo 桩模板；含真实羊 latin1 + 真实 GDF 测试）
- `python scripts/e2e_m1.py`：**ALL OK（13 项）**——sheep + S001 真实导入 → 浏览 → 释放（幂等总量断言）
- `python scripts/e2e_m2.py`：**ALL OK（17 项）**——4.9GB dataset 扫描 5.2s / 识别 1606 条 / 3 条已知结构报错 / 六格式（EDF/GDF 2a/GDF 2b/ds1/ds4/CSV）逐个打开均有真实曲线 / GDF 中文标签 / 六 tab 关闭释放
- `python scripts/e2e_m3.py`：**ALL OK（11 项）**——羊 EDF 三步预览（带通+陷波+重参考）50Hz PSD 压制比 0.0001、坏道标记联动、A01T 分段预览 288 段、tab 释放
- `python scripts/e2e_m4.py`：**ALL OK（18 项）**——羊 EDF 管线（带通+陷波+裁剪前 30s）+三特征 104 行（8 导×13 特征）、处理后 PSD 50Hz 峰已消（0.4 vs 7130 µV²/Hz）、「用当前显示窗口」预填 crop=视口 [125,145]s、CSV BOM+中文表头 104 行、sidecar 含全管线、A01T 逐段特征 288 段×25 导×2 频段=14400 行、事件码 769-772 逐段带入、分段 HDF5 形状一致、FIF 回读 288 段
- `python scripts/e2e_m5.py`：**ALL OK（19 项）**——45 个 2b GDF + 1 损坏文件批处理（分段 769/770/783 + bandpower 双频段）：45 成功 1 失败不杀整批、78240 行特征 8.5s（2 worker）、UI 心跳 86 次≈9s 全程响应、失败行红显+tooltip+日志对话框、批处理结果 tab、CSV BOM 中文表头 78240 行一致、sidecar 含 epoching+bandpower(params.bands=αβ)+45 文件+batch extra(n_files=46/n_workers=2)、中途取消（4 成功/41 已取消/0 误跑）、neo/nwb 四读取器注册、tab 关闭释放；**m1/m2/m3/m4 + smoke_gui 回归全绿**
- `python scripts/smoke_gui.py`：SMOKE OK

## M2 关键实证结论（写代码前实测，避免踩坑）

1. **GDF 事件码表以官方 desc_2a.pdf / desc_2b.pdf 原文为准**（pypdf 提取）——搜索摘要多处错误（781 实为 "BCI feedback (continuous)"，1077–1081 是眼动伪迹标记）
2. **ds1 评估集（BCICIV_eval_ds1*）实际不含 mrk 变量**——pipelineMotor yaml 所说"评估集有提示"与实物不符；读取时明确 note 而非猜标签
3. **ds4 train_data 是 double、文件内无采样率**——fs=1000Hz 来自官方 desc_4.pdf；读取时跳过 test_data（~100MB）
4. **2b 文件名是 B0303T 三段式**（被试+场次+T/E），原正则不覆盖，已加模式
5. 数据集里混有 **ds3 分段 MEG（S1/S2.mat）与 SHA256SUMS.txt**——识别后明确拒绝（ds3 已记 backlog），txt 数值性验证挡住校验文件

## M3 关键实证结论（写代码前实测，避免踩坑）

1. **mne 1.12 `set_eeg_reference` 返回副本而非就地修改**——必须用返回值写回 ctx.raw/ctx.epochs，否则重参考悄悄失效（测试实测 `inst is raw` 为 False）
2. **mne `Epochs` 没有 `notch_filter`**——陷波步骤 `applies_to` 限定 raw 阶段；分段前陷波是标准流程，顺序错误由 apply_pipeline 的阶段检查给出中文提示
3. **`Epochs` 没有 `event_name` 属性**——统计每类段数用 `event_id` 逆映射（`{v: k for k, v in event_id.items()}`）
4. **`compute_psd` 不接受 `fmax=None`**（np.isfinite 报 TypeError）——fmax 为 None 时显式传 Nyquist（sfreq/2）
5. **同一时刻多个事件会让 `mne.Epochs` 抛 "Event time samples were not unique"**——传 `event_repeated="drop"`；且管线面板的参数覆盖必须在**表单构建之前**合入（表单 collect 会用默认值冲掉后改的条目）
6. **pydantic 步骤参数默认值必须可构造**——空列表类校验（如坏道非空）不能放模型 validator（default_params() 会失败），要放 apply() 执行期
7. **tmin=0 时 baseline (None, 0) 只有一个样本**，mne 拒绝——epoching 内自动转 (0.0, 0.0)

## M4 关键实证结论（写代码前实测，避免踩坑）

1. **`raw.crop` 会同步更新内部 first_samp**——裁剪后 EventTable 的绝对秒 onset 与分段步骤的绝对样本号**依然成立**（e2e 验证：crop[5,25] 后 20s 事件保留、30s 事件自然丢弃）；crop 步骤不需要改事件表
2. **mne 读 BCI-IV 2a GDF 时 25 通道（22 EEG + 3 EOG）全部标为 `eeg` 类型**——特征层的类型白名单无法自动排除 EOG；默认取全部 25 数据通道（e2e A01T = 288×25×2 = 14400 行），要排除 EOG 需在特征参数 channels 里显式指定 22 个通道名
3. **`scipy.signal.welch` 参数名是 `nperseg`（无下划线）**——不是 mne 风格的 `n_per_seg`
4. **pandas `pivot_table` 默认 `dropna=True` 会把组键含 NA 的行整组丢掉**——文件级特征行（epoch_index=None）在宽表里全部消失；`to_wide()` 必须传 `dropna=False`
5. **`mne.Epochs.crop` 窗完全在段窗外时先抛英文错**（"tmin must be less than..."）——中文预检查（无重叠→"分段数为 0"）要放在 crop 调用之前
6. **Qt6 无 `Qt.ItemDataRole.SortRole`**——自定义排序角色用 UserRole 惯例 + `setSortRole`；且必须让数值列返回 float，否则代理按字符串排序（"10" < "2" 乱序）
7. **e2e patch QMessageBox 必须逐模块进行**——`from PySide6.QtWidgets import QMessageBox` 是各模块的独立引用，只 patch main_window 的不影响 pipeline_panel/feature_table；漏 patch 的模块真弹模态框 → offscreen 事件循环永久阻塞（CPU 0% 假死）
8. **通道平均 PSD 的谱峰取决于各通道幅度²**——羊数据 30µV 工频 > 2×20µV α 的合成功率，平均曲线峰在 50Hz；断言 α 主导要用纯 α 通道（单通道指定）

## M5 关键实证结论（写代码前实测，避免踩坑）

1. **2b E（评估）文件 769/770 事件全为 0，未知类 cue 用 783（160 段）**——T（训练）文件才是 769:60+770:60=120 段；同一分段码表跑通两类文件必须含 783，否则 18 个 E 文件分段数为 0（e2e 统计 45 文件实测：T=120 段/E=160 段）
2. **neo 不在 conda-forge**（`conda search -c conda-forge neo` 模糊命中 sse2neon）→ pip 例外（0.14.5）；**pynwb 在 conda-forge 且 dry-run 干净**（只新增 hdmf/attrs/jsonschema，不动 numpy/mne）→ conda 装（4.1.0）；两者与 mne 1.12 共存无冲突（137 绿验证）
3. **neo.rawio 0.14 的 header 是 numpy structured array**——`header['signal_channels']` 行取值用字段名（row['name']/row['units']/row['stream_id']），不是下标也不是 dict；`rescale_signal_raw_to_float` 得到的是**通道单位**浮点，到伏特要自己按 units 查表换算（_UNITS_TO_V）
4. **pynwb 4.x 三处接口坑**：`add_electrode` 的 location 必填非空（""被拒）；电极表默认**无 label 列**需 `add_electrode_column("label", ...)`；`DynamicTableRegion.colnames` 是 None（不能判列存在性），取列直接 `region["label"][:]`（try/except 包住）
5. **mne 无 `write_raw_edf`**——合成 EDF 用 `raw.export(path, fmt="edf", overwrite=True)`
6. **Qt6 魔数全部禁用**：0x02 是 `ItemIsEditable` 不是 UserCheckable（运行期静默错行为）；必须 `Qt.ItemDataRole.UserRole` / `Qt.ItemFlag.ItemIsUserCheckable` / `Qt.CheckState.Checked` 全枚举
7. **stdout 重定向到文件是块缓冲**——e2e 中途崩溃时已过检查项的 print 全丢在缓冲区；脚本类 print 一律 `flush=True`

## 最近变更记录（新条目加在最上面）

- 2026-08-18（v1 收官后补充）：编写 **MANUAL.md**（说明/运行/使用/调试一册通览，README 已链接）；盘点 UI 时发现并修复 **事件跳转按钮接线反了**（signal_browser.py：`◀ 上一事件`误接 `_jump_event(+1)` 即跳更晚事件——两按钮 lambda 对调，代码内留注释；e2e_m1 直接调 `_jump_event(1)` 语义未受影响，回归 ALL OK）。

- 2026-08-18（M5 完成，v1 收官）：batch/jobs.py（JobSpec/PipelineSpec 启动前校验/FileResult/BatchSummary）+ batch/engine.py（**BatchEngine 纯 Python**——ThreadPoolExecutor 默认 2 线程、threading.Event 取消、单文件失败不杀整批、LoadedRawCache pin 防并发互逐、_export CSV/H5+sidecar batch extra）；proc/base.py + features/base.py 加 `cancel_check`（逐步骤检查抛 PipelineCancelled）；core/app_settings.py（pydantic 设置 + 原子写 + 热生效）；UI（batch_view 进度表/失败行红显/双击日志对话框、batch_dialog 两页+queue.Queue+QTimer150ms 事件泵、settings_dialog 三字段、主窗口文件/处理菜单接线 + 批处理结果 tab）；io/neo_reader.py（_NeoRawReader 模板 + Blackrock/OpenEphys/Intan）+ io/nwb_reader.py（ElectricalSeries/trials→EventTable）；README 重写（v1 全览/典型流程/验证口径）；tests +15（137 绿）；e2e_m5 19 项 ALL OK + m1-m4/smoke 回归全绿。

- 2026-08-18（M4 完成）：proc/crop.py（时间窗裁剪，四层决策第③层；raw 绝对时间/epochs 相对事件锚点）；features/base.py（FeatureExtractor ABC + FEATURE_REGISTRY + apply_features，与 proc 层同构）+ spectral.py 扩展（array_welch 数组版 + BandPowerFeature 频带功率 δθαβγ+自定义+相对/对数 + WelchPsdFeature PSD 曲线仅 raw）+ timedomain.py（8 统计量纯 numpy）；batch/results.py FeatureTable（长表 COLUMNS 7 列 + 中文表头映射 + to_wide dropna=False）；export/ 三模块（features_io CSV BOM 中文表头+曲线宽表分轴分组/HDF5、epochs_io HDF5 结构化+FIF、provenance .pipeline.json sidecar）；UI（pipeline_panel 特征区+视口预填+features_ready、feature_table.py 特征结果 tab 数值排序、主窗口处理菜单 4 动作）；tests +50（122 绿）；e2e_m4（18 项：羊 104 行/50Hz 峰消除、A01T 14400 行、HDF5/FIF 回读一致）。

- 2026-08-18（M3 完成）：proc/（context/base/filters/referencing/resample/bads/epoching/preview——6 步骤 + STEP_REGISTRY + apply_pipeline 阶段检查 + 预览副本包装）；features/spectral.py mean_welch；UI（params_form pydantic 自动表单/pipeline_panel/psd_view/epochs_preview）；signal_browser 坏道右键标记+灰显+bads_changed 联动；主窗口处理菜单+预览 tab 接线；tests +29（72 绿）；e2e_m3（11 项：羊 50Hz 压制比 0.0001、A01T 288 段）。

- 2026-08-18（M2 完成）：io/mne_readers.py 重写为 `_MneRawReader` 模板基类家族（8 格式，`_read_fn` 必须 staticmethod）；io/event_maps.py（GDF 官方码表 16 码中文标签）；io/bciciv_mat.py（ds1 头只 loadmat nfo/mrk、ds4 纯 whosmat、未知 mat 拒绝猜测）；io/table.py（分隔符嗅探+数值性验证+FS_UNSET_NOTE）+ io/hdf5.py（零数据 IO 定位信号集）；core/fs_store.py（CSV/HDF5 采样率询问记忆）；主窗口采样率询问对话框；**workers/generic.py 加 `_MainRelay`**（修 worker 线程回调弹窗冻结——M2 最关键产品修复）；嗅探补 GDF/BDF/HDF5/BrainVision 魔数；e2e_m2.py（17 项）。
- 2026-08-18（M1 完成）：core/recording.py（Recording/EventTable/LRU 缓存，修锁内逐出死锁）+ core/workspace.py（JSON 原子持久化）；io 层（BaseReader ABC/注册表/scan_folder 进度回调/EDF latin1 回退）；UI（导入控制器+错误表/工作区树/元数据表/信号浏览器窗口化+峰值包络/事件条+跳转导航）；修 3 个实测坑（PySide worker GC、PlotItem 构造期无 scene、load_raw 收 str path）；E2E 脚本幂等化。
- 2026-08-18（M0 完成）：conda env dlv、包骨架、主窗口、治理文件、首次 commit。
- 2026-08-18（启动）：方案批准、git 初始化。
