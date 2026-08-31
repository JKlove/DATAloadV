# STATUS — 项目状态快照

> 本文件回答"现在做到哪了"。每里程碑完成及重要提交后更新。最后更新：2026-08-30（M8.3 特征图表区完成；下一 M9 连续导出）

## 当前里程碑

- **M8.3 特征结果图表区：✅ 完成（2026-08-30）**——用户两点需求：①`welch_psd` 语义升级
  （**逐通道各一条**——通道平均语义废除；可选 `时间窗`，两参留空=全量逐通道；窗标记
  `@起-止s` 进图例/CSV 列名/HDF5 attrs，旧文件回读兜底空串）；②特征结果 tab 从纯长表
  扩成**表+图表**（QSplitter 3:2）——「PSD 曲线」页多通道多窗 log-log 一张图（超 60 条
  截断+提示）、「特征柱状图」页**每特征一格**网格（Y 量程独立天然解决量纲差异；分段
  数据按事件码求均值聚合，每类事件一条系列+提示行说明口径；特征>24/系列>12 截断）；
  批处理结果 tab 同一控件两入口同享。`_resolve_spans` 抽模块级共用（BandPower 行为零变）。
  pytest **271 绿**（+10）+ e2e_m4 **19 项**（逐通道断言+全曲线 50Hz 压制中位数）+ smoke +
  三形态白底截图目视确认（像素统计证伪分析器"黑底"幻觉——pg 全局主题在 MainWindow 里
  设置，独立截图须手动复刻）

- **M8 分段分析可视化：✅ 完成（2026-08-28）**——分段预览从单一"各通道平均堆叠"扩成**四视图**
  （数据一次取齐缓存零重算）：①堆叠（M3 现状零回归）②**ERP 蝶形图**（全通道同坐标分色+零线）
  ③**单通道 ERP**（逐段半透明细线 + **按事件码分色**平均粗线，曲线尾标注码——类间差异一眼可辨）
  ④**时频图**（morlet 段平均功率热图，`features/tfr.py` 纯函数后台线程计算，基线校正 dB、
  低频在下、色标可调）；配套 `BandPowerParams.time_windows`——**时间分辨频带功率**进特征/批处理链
  （`起-止` 秒可负，epochs 相对事件锚点/raw 绝对秒，窗进特征名如 `alpha@0-1s`，默认空=整段零回归）。
  e2e 数值验收用**守恒式**（整段 α = 子窗时长加权混合，统一 Welch 分辨率后 22 EEG 通道中位误差 8.2%）；
  不做 ERD 方向断言——A01T 原始数据群体中位 1.05±0.1 无显著方向（数据事实优先于教科书预期）。
  pytest **242 绿**（+29）+ e2e_m8 **13 项** + e2e_m1–m5/m7/smoke 回归全过

- **M7 信号质量体检（QC）：✅ 完成（2026-08-28）**——固化收官后 4 轮手工"噪声感"诊断的方法论：
  `features/qc.py` 双入口（浏览器一键 + 特征提取器注册表，同一 `compute_channel_qc` 纯函数收
  `get_window` 闭包分窗采样不整载）；逐通道指标——开路复用（邻道逐样本同值）/死值/平线占比/
  钉极值占比（**无绝对饱和阈值**：跨设备满量程差 2 数量级，看钉本通道极值占比）/漂移斜率
  µV/min/直流中位（只进指标不定级，DC 耦合固有）；三级 ✓好/?疑似/✗坏，浏览器通道列表前缀
  +tooltip 中文明细，坏道**建议确认**（question 弹窗 Yes→toggle_bad，不静默改 bads）。
  **黄金标准全复现**：羊 CH5-8 四通道开路复用判坏、CH1-4 真信号不坏（实测判疑似——低频峰值
  平台 2.3% 触发疑似线属设计语义）、TPDJ-位置1 八通道全坏（**M7 指标精化 M6.7b"全平"概括**：
  CH2/4/8 真平线+CH2≡CH4 复用、其余钉满量程+跳变）；02号脑电 2 文件顺带诊断入册（DATA_NOTES
  §8）。pytest **213 绿**（+20）+ e2e_m7 **16 项**×2 幂等 + e2e_m1–m5/smoke 回归全过

- **M6.8 浏览器四功能：✅ 完成（2026-08-28，commit 255e67d 随 M6.7–M6.8 一并提交）**，用户四项需求驱动：
  ①「行居中」开关（默认开=M6.7b 行为；关=绝对电平+y 自适配±2%，通道列表显示各通道直流偏移）；
  ②增益输入框 0.01–100×（三入口统一 `_set_gain(float)`，键盘保小数；**勘误旧注释"0.1×–10×"**）；
  ③底部总览时间轴滑块（拖动定位/点击居中共存，lane 自身 x 轴三重锁死——修"时间轴拖动逻辑不清晰"）；
  ④「◀ 1s / 1s ▶」秒级步进。pytest **193 绿**（+22，event_lane 首次有测试）+ e2e_m1 22 项 +
  真窗口四态截图确认（见 review.md M6.8 节）

- **M6.7 渲染两档 + M6.7b 行居中：✅ 完成（2026-08-27）**，用户"10s 密集/9s 发虚"与"第二个数据
  打开后 tab 空白"驱动：connect 按是否抽取分支+抽取阈值 3 样本/px+antialias 恢复；行居中（显示值
  减本窗中位）修 DC 耦合大偏移"空白 tab"主因+minmax_decimate 双 t 笔误；工作区测试污染事故修复
  （用户数据已复原）。pytest 165→171 绿（见 review.md M6.7/M6.7b 节）

- **M6.6 工作区移除条目 + 羊通道质量定论 / M6.5 读取派发魔数校验：✅ 完成（2026-08-24）**——
  树右键/Del 移除（只清索引不删磁盘文件）；羊 .edf 实为 BDF 的魔数优先纠正（详见下方变更记录）
- **v1 全部里程碑（M0–M5）+ M6–M6.8 浏览与读取系列优化 + M7 质量体检 + M8 分段可视化完成**——**下一里程碑：M9 处理后连续数据导出（方向 M7→M8→M9 见 plan.md §8，任务拆解见 TODO.md）**

## 里程碑总览

| 里程碑 | 状态 | 完成日期 | 说明 |
|---|---|---|---|
| M0 骨架+治理 | ✅ 完成 | 2026-08-18 | git 仓库、治理文件、conda env dlv、包骨架、主窗口、冒烟通过 |
| M1 工作区+EDF+信号浏览器 | ✅ 完成 | 2026-08-18 | Recording/Workspace/EdfReader(latin1)/导入/工作区树/元数据表/信号浏览器/事件条；E2E 全过 |
| M2 读取器全覆盖 | ✅ 完成 | 2026-08-18 | 8 格式 mne 模板家族 + ds1/ds4 mat + CSV/TXT + HDF5 + GDF 官方码表中文标签；4.9GB 扫描 5.9s/1606 条 |
| M3 预处理链+预览 | ✅ 完成 | 2026-08-18 | proc 层 6 步骤+序列化、管线面板+pydantic 自动表单、预览副本 tab+分段预览、PSD 对比、坏道标记联动 |
| M4 特征+导出 | ✅ 完成 | 2026-08-18 | crop 时间窗+3 提取器+FeatureTable 长表+特征面板（视口预填）+CSV/HDF5/FIF 导出+sidecar |
| M5 批处理引擎+扩展格式 | ✅ 完成 | 2026-08-18 | BatchEngine(纯 Python 线程池/取消/逐文件容错)+批处理对话框(队列事件泵)+neo(Blackrock/OE/Intan)+NWB 读取器+设置+README；e2e_m5 19 项 |
| M6 浏览体验优化 | ✅ 完成 | 2026-08-18 | 通道标签内嵌重构+幅值标尺+窗口导航(时长/滚轮平移/翻屏/键盘)+浅色主题+增益双 bug 修复；pytest 150 / e2e_m1 18 项 |
| M6.5 读取派发魔数校验 | ✅ 完成 | 2026-08-24 | 魔数内容优先派发+mne 扩展名检查绕过（file-like）+sniff off-by-one+重导入刷新；纠正羊数据 BDF 错解码（1.5× 时长/数值错位）；标注通道核查全 ASCII；pytest 157 / e2e_m1 19 项 |
| M6.6 工作区移除+羊通道定论 | ✅ 完成 | 2026-08-24 | 树右键/Del 移除条目（单条/整组确认，只清索引不删磁盘文件）+持久化；羊通道质量核查（CH5-8 开路复用同值、CH1-3 真实带大直流）；pytest 163 |
| M6.7 渲染两档+测试隔离 | ✅ 完成 | 2026-08-27 | connect 按抽取分支+阈值 3 样本/px+antialias；工作区测试污染事故修复（用户数据已复原）；pytest 165 |
| M6.7b 行居中+minmax 笔误 | ✅ 完成 | 2026-08-27 | 显示值减本窗中位（DC 耦合大偏移"空白 tab"主因）+包络双 t 笔误；真窗口四连开 4/4 确认；pytest 171 |
| M6.8 浏览器四功能 | ✅ 完成 | 2026-08-28 | 行居中开关+通道直流偏移显示+增益输入框 0.01–100×+总览时间轴滑块+±1s 步进；pytest 193 / e2e_m1 22 项 |
| M7 信号质量体检 | ✅ 完成 | 2026-08-28 | qc 特征提取器+浏览器一键体检（✓/?/✗ 前缀+tooltip 明细+坏道建议确认）；黄金标准全复现（羊 CH5-8 坏/TPDJ-位置1 全坏）+02号脑电入册；pytest 213 / e2e_m7 16 项 |
| M8 分段分析可视化 | ✅ 完成 | 2026-08-28 | 分段预览四视图（堆叠/ERP 蝶形/单通道按码分色/时频 morlet 热图）+bandpower time_windows 时间分辨特征（窗进特征名）；守恒式数值验收 8.2%；pytest 242 / e2e_m8 13 项 |
| M8.1 三锚定分段+时频观感+单段浏览 | ✅ 完成 | 2026-08-28 | 分段锚定三模式（事件锚定/固定窗滑窗/手动时刻——无事件数据可分段）+时频 Y 铺满修复/jet·hot 配色/按通道缓存+第五视图单段浏览（◀▶ 翻段）；pytest 257 / e2e_m81 12 项 |
| M8.2 视图观感精修 | ✅ 完成 | 2026-08-28 | 堆叠系通道名行首内嵌标签（y 轴刻度挤叠根除）+蝶形图图例（自动分列）+切时频 ticks 残留清理（左上角飘字根因）；离屏截图目视确认；pytest 261 |
| M8.3 特征结果图表区 | ✅ 完成 | 2026-08-30 | welch_psd 逐通道+时间窗（通道平均语义废除）+结果 tab 表+图表（PSD log-log/特征柱状网格、分段按事件码聚合）；批处理同享；pytest 271 / e2e_m4 19 项 |

## 环境

- conda env：`dlv`（Python 3.10），安装命令见 HANDOFF.md §环境搭建
- 关键包版本：numpy 1.26.4 / scipy 1.15.2 / pandas 2.3.3 / h5py 3.16.0 / pydantic 2.13.4 / PySide6 6.11.0 / pyqtgraph 0.14.0 / mne 1.12.0（pip）/ edfio 0.4.16（pip）/ **neo 0.14.5（pip——conda-forge 无此包）/ pynwb 4.1.0（conda-forge）**（M5）

## 测试

- `QT_QPA_PLATFORM=offscreen pytest`：**261 passed**（M7 后 213 + M8 净增 29：tfr 纯函数 17 含真实 A01T 黄金（频率轴 2/计算 6/时间窗解析 6/真实 gdf 1）+ 四视图 widget 8（堆叠数值断言/蝶形/单通道按码分色/时频 ImageItem·色标·y 反转/切走残留复位/teardown 幂等/迟到回调丢弃）+ bandpower time_windows 4（raw 绝对窗数值/epochs 相对窗密度不变式/越界拒绝/采样点不足拒绝）；**M8.1 净增 15**：epoching 锚定 9（滑窗 11 段样本序列 `arange(250,14000,1250)`/半重叠 22 段差 625/步进>窗长拒/窗超长拒/手动 3 段锚点样本 7625/越界列全部无效锚点/空锚点拒/默认=事件锚定/序列化往返）+ 预览 6（Y 残留修复/配色 LUT 换色 levels 不扰动/缓存零重算/控件随视图启停/单段浏览数值断言+跳段 clamp）；**M8.2 净增 4**：行内嵌标签文本+8pt+y 轴无刻度/图例逐通道条目+切走隐藏/25 通道图例分列 3/单段浏览→时频左轴无通道名残留且频率=自动刻度；**M8.3 净增 10**：welch 语义 5（默认 8 曲线+通道名单+window 空+EEG00 峰 10Hz/逐通道曲线/子窗 0-30→16 条+全量 8 条 window 空+窗 8 条 @0-30s+峰仍 10Hz/越界拒/不足 2 采样点拒）+ 导出 2（窗进宽表列头+HDF5 attrs 往返）+ 图表区 3（PSD 曲线数/60 截断+hint 含总数/柱格按事件码聚合 T1=(1+3)/2=2、T2=10 走 aggregated 数值断言）。**须 offscreen：MainWindow 级测试在 macOS 真窗口模式会挂住**）
- `python scripts/e2e_m1.py`：**ALL OK（22 项）**——sheep + S001 真实导入 → 浏览 → 释放（幂等总量断言）；M6 追加 5 项 + M6.5 追加 1 项（羊数据按 BDF 解码：魔数优先于扩展名）+ M6.8 追加 3 项（±1s 平移/绝对模式 y 自适配/总览滑块跟随视口）
- `python scripts/e2e_m7.py`：**ALL OK（16 项）×2 幂等**——羊浏览器体检（4 bad 全复用→Yes 自动标坏道→列表 ✗/✓ 前缀→tooltip 明细→按钮恢复）/ TPDJ-位置1 八通道全坏 / 特征链（注册表→FeatureTable→CSV·HDF5 回读分级一致）；**须逐模块 patch signal_browser.QMessageBox**（该模块 M7 起有模块级引用，MainWindow 的 patch 罩不到）
- `python scripts/e2e_m2.py`：**ALL OK（17 项）**——4.9GB dataset 扫描 5.2s / 识别 1606 条 / 3 条已知结构报错 / 六格式（EDF/GDF 2a/GDF 2b/ds1/ds4/CSV）逐个打开均有真实曲线 / GDF 中文标签 / 六 tab 关闭释放
- `python scripts/e2e_m3.py`：**ALL OK（10 项）**——羊 BDF（.edf 误标）三步预览（带通+陷波+重参考）50Hz PSD 压制比 0.0001、坏道标记联动、A01T 分段预览 288 段、tab 释放
- `python scripts/e2e_m4.py`：**ALL OK（18 项）**——羊 EDF 管线（带通+陷波+裁剪前 30s）+三特征 104 行（8 导×13 特征）、处理后 PSD 50Hz 峰已消（0.4 vs 7130 µV²/Hz）、「用当前显示窗口」预填 crop=视口 [125,145]s、CSV BOM+中文表头 104 行、sidecar 含全管线、A01T 逐段特征 288 段×25 导×2 频段=14400 行、事件码 769-772 逐段带入、分段 HDF5 形状一致、FIF 回读 288 段
- `python scripts/e2e_m5.py`：**ALL OK（19 项）**——45 个 2b GDF + 1 损坏文件批处理（分段 769/770/783 + bandpower 双频段）：45 成功 1 失败不杀整批、78240 行特征 8.5s（2 worker）、UI 心跳 86 次≈9s 全程响应、失败行红显+tooltip+日志对话框、批处理结果 tab、CSV BOM 中文表头 78240 行一致、sidecar 含 epoching+bandpower(params.bands=αβ)+45 文件+batch extra(n_files=46/n_workers=2)、中途取消（4 成功/41 已取消/0 误跑）、neo/nwb 四读取器注册、tab 关闭释放；**m1/m2/m3/m4 + smoke_gui 回归全绿**
- `python scripts/e2e_m8.py`：**ALL OK（13 项）**——A01T 分段预览四视图矩阵（288 段/堆叠 25 曲线/蝶形+零线/单通道 288 细线+4 按码平均+4 标注/时频 ImageItem+色标+y 反转/切走复位）+ 时间分辨特征（21600 行=288×25×3、特征名带窗标记、**守恒式中位误差 8.2%<12%**）+ 导出 CSV 回读 21600 行一致；**分段预览后 active tab 是预览视图，特征面板要 active browser——切回浏览器 tab 再算**（e2e_m4 路径差异）
- `python scripts/e2e_m81.py`：**ALL OK（12 项）**——A01T 手动锚点 [10,20,30.5,350]→4 段「手动」零静默丢弃；蝶形→时频 Y span 47.5Hz 铺满（残留时压成一条）；切 jet 查找表换色且 levels 不扰动；切走切回缓存命中秒显（零线程零重算）；固定窗滑窗 [-1,4]s→**538 段**（样本域公式现算 `arange(250, 672528-1000, 1250)`，不硬编码）；第五视图 25 通道堆叠+段号跳段/▶ 翻段
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

## M6 关键实证结论（写代码前实测，避免踩坑）

1. **pyqtgraph ViewBox 默认滚轮同时缩放 x/y**——y 未锁时滚几下通道刻度挤成一团（用户"通道名重叠"截图根因之一，与 y 轴全量 setTicks 截断叠加）；必须 `setMouseEnabled(x=True, y=False)` 并在子类 `wheelEvent` 里接管滚轮（重载后不调 super，默认缩放不再发生）
2. **y 轴 setTicks 放全部通道名不可扩展**：导联一多必然挤叠+"…"截断；曲线行内嵌 TextItem（anchor=(0,0.5) + 半透明白 fill）是任意通道数下都不重叠的解
3. **`PlotCurveItem.yData` 就是 setData 传入数组本体**（shares_memory 实证）——增益断言可直接读曲线数据做比值；诊断中曾疑 yData 被 pyqtgraph 改写，纯 pyqtgraph 最小复现排除
4. **浏览器增益两个存量 bug（M1 起）**：增益只乘通道间距不乘波形（`out_v + idx*spacing*gain`）；`_gain` 存滑杆刻度值却初始化 1.0 → 首帧隐形 10^0.1≈1.26× 增益（新测试断言 ×10 实得 7.94 顺藤摸出）
5. **PSD 首色 #e8e8e8 在白底完全不可见**——深底换白底不只是背景一行，浅色系配色（波形 #7fbfff、事件黄 #e0e05c、图例 #cccccc、batch 状态色）全部要跟着换成白底可辨浓度

## M6.5 关键实证结论（写代码前实测，避免踩坑）

1. **sheep 系列 6 个 .edf 内容全是 BDF**（`\xffBIOSEMI` 头）——按 EDF 读把 24-bit 样本按 16-bit 解码：**样本数虚增 1.5×（180s→270s）、数值全部错位**；data/ 全量普查仅此 6 处不符，其余数据集扩展名与内容一致
2. **mne 公共入口（read_raw_edf/bdf/gdf）的 `_check_args` 按扩展名硬拒绝**（"Only BDF files are supported, got edf"）——mne 内部同样信扩展名；但 **file-like 对象完全绕过该检查**（仅要求 preload=True；read_raw_bdf 自 MNE 1.10 官方支持，edf/gdf 同路径，1.12 实测）——扩展名不符时传文件对象重读公共入口（不直接实例化 Raw* 构造器，用户指定）。file-like 读后须 `_detach_file_handles` 剥离 mne 内部两处句柄残留（`_raw_extras[*]["blob"]` + `_init_kwargs["input_fname"]`），否则 raw.copy()/deepcopy 抛 cannot pickle（e2e_m3 预览链路实测）
3. **sniff EDF 分支曾有 off-by-one**（M2 潜伏）：版本域是字节 0–7 共 8 字节，旧代码查 `head[1:9]` 把患者域首字节卷进来——真 EDF（患者域不以空格/B 开头）嗅探漏判返回 None；此前无人察觉因 .edf 走扩展名快路径从不嗅探
4. **内容嗅探必须"唯一定位"才可参与派发**：hdf5 签名是家族级（NWB/Intan rhs/通用 HDF5 同头），盲目提升通用读取器会抢 NWB 的活——只对 EDF/BDF/GDF/BrainVision 做内容优先
5. **魔数明确时不给扩展名候选兜底**：BDF 内容让 EDF 读取器"再试一次"只会静默产出错位数据——宁可读失败报错，不可错读成功
6. **羊 6 个 BDF 的标注通道（BDF Annotations）全为纯 ASCII**（2026-08-24 逐字节核查）：内容是标准 TAL `+N\x14\x14\x00`——每秒一条**空文本**注释，满足 UTF-8；utf8 默认编码读取零报错、零事件（空注释无意义事件是数据本身属性）。"羊需要 latin1"确系 M1 按 EDF 误解码 BDF 的副产品，机制保留给真 latin1 老文件（合成回归测试锁定）
7. **EDF/BDF 头部手工解析布局**：固定头 256B 内记录数@236、每记录秒@244、ns@252；信号子头**字段主序**（所有 label ns×16B 连续，samples 区在 `256+ns*216`），数据区起点=headerbytes 字段（自校验）——不是"每通道 256B 块"（两次踩坑后实证，HANDOFF 坑 #44）

## M6.6 关键实证结论（写代码前实测，避免踩坑）

1. **羊"全是噪声"根因是通道本身未接电极**（不是读取 bug）：CH5==CH6==CH7==CH8 逐样本
   `np.array_equal` 全 True——采集箱把开路通道复用成同一段缓冲；数值钉 ±375000µV 满量程
   饱和或 std=0。CH1–CH3 为真实信号（去直流+带通 1–40Hz 后 std≈279µV、宽带 β 为主），
   但带数十 mV 直流偏移——直接浏览"信号骑大斜线"。换算 0.125µV/LSB 与手算一致
2. **Qt 焦点模型：焦点在 QTreeWidget 内层时容器收不到 keyPress**——Del 键删除必须在树本体
   子类重载 `keyPressEvent`（`_TreeWithDel`），容器级 QSS/事件过滤方案无效
3. **MainWindow 级 pytest 在 macOS 真窗口模式会挂住**——全套 pytest 从此必须带
   `QT_QPA_PLATFORM=offscreen`（此前只有 e2e/无头脚本需要）；又及 `| tail` 管道缓冲全部
   输出直到进程结束，长命令一律后台直跑+`python -u`
4. **测试间会通过 ~/.dataloadv/workspaces/<名>.json 持久化耦合**——MainWindow 测试的工作区
   名必须每测试唯一（`request.node.name`）+ teardown unlink，否则"删了 1 条"的上一步状态
   污染下一步（曾 3==2 假失败）

## M6.7 关键实证结论（写代码前实测，避免踩坑）

1. **pyqtgraph `connect="pairs"` 会把 raw 透传序列隔段漏画**（0-1/2-3/… 只连一半段）——
   用户"9s 屏线太虚"的直接根因；pairs 只对 min/max 成对结构合法，raw 必须用默认 "all"
2. **抽取阈值悬崖正好卡在 9s/10s 之间（Retina）**：`vb.width()` 返回**逻辑像素**
   （≈物理一半；实测布局 1212px）→ 旧阈值 max_points=2424，250Hz 数据 10s=2500>2424
   触发 m=2 抽取（相邻样本画成竖线=密集成带）、9s=2250≤2424 走 raw。阈值提到 3 样本/px
   后 1/2/5/10s 预设全留折线档（30s=7500 才切包络），观感连续无跳变
3. **`minmax_decimate` 在 m=2 时输出点数==输入点数**（2500→1250 桶×2 点）——判断
   "是否抽取"不能用长度比较，用同一条件 `n > max_points`
4. **工作区测试隔离事故链（M6.6 埋雷 → M6.7 实锤）**：持久化真实布局是
   `workspaces/<名>/workspace.json` 目录（teardown 按 `<名>.json` glob 永远落空）+
   `current_workspace.txt` 全局标记被测试改写不恢复（用户 GUI 续进测试名工作区，当天
   1574 条真实导入被困 `test_删除_*` 目录）+ qtbot 关窗 closeEvent 自动 save 再落盘
   → 后续 pytest 首载 1574 条稳定失败。fixture 三重隔离：preset 标记/closeEvent 落盘
   改道 tmp/按真实布局 rmtree + 恢复标记；用户数据已修复（并入 默认工作区 1572 条，
   备份 /tmp/dataloadv_repair_backup_20260827_160326）

## M7 关键实证结论（写代码前实测，避免踩坑）

1. **饱和判定不能用绝对电平阈值**——BioSemi 满量程 ±375000 µV 与 g.USBamp ±5000 µV 差两个
   数量级，共用阈值必错一边；改"钉在本通道自身极值上的样本占比"（rail_pct，恒值通道
   max==min 时按逻辑或计 100% 不双计）
2. **低频大信号天然有"峰值平台"**——采样率快于信号变化时，慢信号在极值附近连续多样本取同
   值（羊皮层 CH1–4 rail≈2.3% > 疑似线 1%）：疑似级是正确语义（建议人工复核），不是误报；
   "真信号不坏"才是黄金不变式，不是"真信号必 good"
3. **TPDJ-位置1 死放大器有两种伪迹形态**——M6.7b"八通道全平"是粗粒度概括；M7 指标分层：
   CH2/4/8 真·平线（flat≈100%，且 CH2≡CH4 逐样本相同）与 CH1/3/5/6/7 钉满量程+偶发跳变
   （rail 50–85%、漂移 −2k~−13k µV/min）——全坏结论不变，机制更精细
4. **QC 通道选择与 pick_channels 语义相反**——`features/base.py` 的 `pick_channels` 排除
   `info["bads"]`，而 QC 的体检对象恰恰包含坏道（坏道正是要检出的），QualityCheckFeature
   自带通道选择（DATA_CH_TYPES 全集、不剔除 bads）
5. **信号浏览器 M7 起有模块级 QMessageBox 引用**——e2e/测试须单独 patch
   `dataloadv.ui.widgets.signal_browser.QMessageBox`（MainWindow 的 patch 罩不到子模块，
   HANDOFF 坑 #14 规约的新实例）
6. **分窗拼接的边界 diff 是真实相邻时刻比较**——窗 i 末样本与窗 i+1 首样本拼接后做
   `diff==0` 平直统计，不引入假差异（恒值通道实测 flat 99.97% 而非 100%，容差断言即可）

## M6.8 关键实证结论（写代码前实测，避免踩坑）

1. **pyqtgraph `LinearRegionItem` 做"总览视口滑块"的三个源码级细节**（0.14.0 实读源码验证）：
   逐线 `for line in region.lines: line.setMovable(False)` 冻结边缘 = "只平移不改宽"（拖区域
   本身就是两线整体移动，宽度天然保持）；`setRegion` 值相同早退不 emit、值不同会 emit——
   程序化回写必须 `_syncing` 标志包住防回环；拖出 `[0,duration]` 时两线**各自**被 bounds
   钳制→区域瞬时压窄——消费侧只取 region 中心按主图自身宽度重锚，绝不采纳两缘宽度
2. **增益滑杆 `-20..20` 配 `10^(x/10)` 实际是 0.01×–100×**——旧代码注释与 MANUAL 都写成
   "0.1×–10×"（做输入框时照注释定范围会与滑杆两端脱钩）；键盘 ↑↓ 若走 `slider.setValue(int)`
   会把小数增益取整抹掉——三入口（滑杆/输入框/键盘）统一收敛 `_set_gain(float)`
3. **`QListWidget.itemChanged` 在 `setText` 时也触发**（不只是勾选变化）——批量更新列表文本
   必须 `blockSignals(True)` 包住，否则一次偏移更新连发 N 次无谓刷新；通道名权威源迁
   `UserRole`（item.text() 会被偏移值拼接，右键/坏道标记不得再拿它当名字）
4. **pyqtgraph 杂项**：`vb.state["mouseEnabled"]` 返回 **list 不是 tuple**（断言比较要
   `tuple()` 包）；`setMouseEnabled(False,False)` 后 items 仍收鼠标事件（点击居中与拖滑块
   共存的前提）；PlotItem 子类重载 mouseDragEvent 不会被调——拖拽事件走 ViewBox（注入
   `_PanViewBox` 子类模式）

## M8 关键实证结论（写代码前后实测，避免踩坑）

1. **不同窗长的 Welch nperseg 是系统偏差源**：`array_welch` 的 nperseg=min(默认 4s, 窗长)——1s 窗 1Hz 分辨率会把窄 α 峰摊薄，4s 窗 0.25Hz 抓得全。A01T 实测"整段=子窗时长加权混合"守恒式残差 **24%**（分辨率差异主导）；统一 `n_per_seg_s=1.0` 后降到 **8.2%**（只剩段间方差）。**跨窗对比要么等长窗、要么统一分辨率参数**（已写进 MANUAL §3.8 参数建议）
2. **A01T 原始数据无显著 ERD 方向**：等长 1s 窗下 22 EEG 通道 after/before 群体中位 1.05（带 0.94–1.18）、C3/C4/Cz 1.05–1.18——教科书 ERD 要预处理+去伪迹+对侧导联+被试群才稳定。**黄金断言用守恒式（管线正确性）不用生理方向**（M7"真信号不坏"同款方法论：断数据可复现的事实，不断教科书预期）
3. **`mne.events_from_annotations` 返回重映射 id**：events 第三列是按注释名排序的连续整数（1..n），不是原码 769——离线验证脚本要用 `event_id['769']` 查表；UI 面板 epoching 按 annotation **名**过滤不受影响
4. **pyqtgraph 时频热图三细节**：①`ImageItem.boundingRect()` 是像素坐标（300×24），视图坐标要 `mapRectToView()`；②`invertY(True)` 是 ViewBox 级状态，切走时频视图不显式复位会把其它视图上下镜像；③`HistogramLUTItem` 挂在 `GraphicsLayoutWidget` 侧列，`plot.clear()` 清不到——切视图须显式 `removeItem`（残留回归已入测试）
5. **Qt 测试等后台线程要等"真收尾"**：`ImageItem` 出现 ≠ 线程收完（deleteLater 链在事件循环里排队）——伪造 `_tfr_running` 状态后退出会话，QThread 析构竞态打出 "Signal source has been deleted"。测试里 `qtbot.waitUntil(lambda: not _keepalive)` 才是线程链走完的本质判据
6. **`tfr_array_morlet` 基线单样本陷阱**：`baseline=(None, 0)` 在 tmin≥0 的数据上罩住单个 t=0 样本，单样本"均值"校正无统计意义——`compute_epochs_tfr` 用 `times[0] < 0` 且基线 ≥2 采样点两道闸落实"无基线走峰值归一"（docstring 声称的分支实现时漏了，测试逼出）

## M8.1 关键实证结论（写代码前后实测，避免踩坑）

1. **`pg.ColorMap` 收 0..1 float 色数组会按 0..255 截断**（0.75→0）：得到近全黑热图且**无任何告警**——jet/hot 公式生成必须 `np.round(rgb*255).astype(np.uint8)` 传 (256,3) uint8；viridis/turbo/plasma 用 `pg.colormap.get()` 内置可得，jet/hot 抛 FileNotFoundError（dlv 环境 pyqtgraph 0.14.0 实测）
2. **`ImageItem.lut` 是 `HistogramLUTItem.getLookupTable` 的可调用引用**（随 gradient 实时变）不是数组：`np.asarray(img.lut)` 得 bound method 对象数组（比较恒无意义）；签名 `getLookupTable(img=None, n=None, alpha=None)` **首参是 img**——`img.lut(256)` 报 `'int' object has no attribute 'dtype'`，取表须 `img.lut(n=256)`。另 `img.getLevels()` 返回 ndarray，断言相等须 `np.array_equal`（`==` 得数组触发 truth-value 歧义）
3. **mne.Epochs 锚点保留条件（1.12 实测）**：`anchor + round(tmin·fs) ≥ 0` 且 `anchor ≤ n_times − 1 − round(tmax·fs)`；窗长 = `round(tmax·fs) − round(tmin·fs) + 1`（双端闭）；越界锚点被 `on_missing="ignore"` **静默丢弃**——自定义锚点序列必须样本域构造+预检报错。A01T（250Hz/672528 样本）fixed [-1,4]s → `arange(250, 671528, 1250)` 共 **538 段**（合成 60s 数据 11 段、步进 2.5s 半重叠 22 段——Plan 期估 23 是错的，段数按公式现算不硬编码）
4. **程序化 `setYRange` 会禁用 autoRange**：堆叠/蝶形视图设过 Y 范围后，时频视图不显式 `autoRange()` 则热图被残留范围（实测蝶形后 [-89, 800+]）压成一条——观感 bug 根因；autoRange 必须在 `addItem(img)` 之后调用，与 invertY 先后无关
5. **中文 Literal 兼作 pydantic 枚举值三处实测通过**：pydantic 精确匹配校验 / 旧 JSON 缺键默认回填 / QComboBox 往返原值——且值即**冻结的序列化格式**（换词=旧 pipeline JSON 全不兼容），词表一次定稿；`ensure_ascii=False` 下中文值可直接 `json.dumps`
6. **PSD 两链路定论**（用户问梳理）：对比 PSD（M3，mean_welch 通道平均、固定参数取前 120s、独立窗口看图、仅 raw 阶段）vs PSD 曲线特征（M4，参数可调进特征表导出）——同底层纯函数不同职责**不冲突不重叠**；对比 PSD 支持 epochs 可作后续增强（用户指示后开工）。**M8.3 更新**：特征链 welch 已改逐通道语义（通道平均废除），对比 PSD 仍是 mean_welch 通道平均不受影响——两链路差异从此更明确（特征链=逐通道参数化，对比链=快速总览）

## 最近变更记录（新条目加在最上面）

- 2026-08-30（M8.3 完成，用户两点需求驱动）：**特征结果图表区 + welch 逐通道语义**。
  **①`welch_psd` 参数化**：`channels` 留空从"通道平均一条"改为**逐通道各一条**（语义废除，
  "(通道平均)"字面量删除；`mean_welch` 保留——对比 PSD 仍用）；新增 `time_windows`
  （raw 绝对秒、逗号分隔多窗，格式同 BandPower）；窗标记 `@起-止s` 进 curve dict
  `window` 字段（纯 str 不违反禁 Qt/跨线程规则）→ CSV 宽表列头/HDF5 attrs（旧文件
  回读 `.get("window","")` 兜底）。窗校验抽模块级 `_resolve_spans` 供 BandPower/WelchPsd
  共用（错误消息逐字保留，测试即护栏）。**②结果 tab 图表区**（`feature_charts.py` 新建，
  feature_table 只加编排）：QSplitter 上表（原工具行+长表平移）下图 3:2；「PSD 曲线」页
  log-log 多通道多窗一张图（`pg.intColor(i,hues=n)` 分色、复用对比 PSD 轴标签、蝶形同款
  分列图例、超 60 条截断+hint）；「特征柱状图」页**每特征一格** 3 列网格（Y 量程独立——
  量纲差异天然解决；BarGraphItem 通道并列、组内按系列错位；分段数据 `groupby
  (recording,event_code,channel,feature).mean()` **按事件码求均值聚合**+提示行说明口径；
  特征>24/系列>12 截断+hint；QScrollArea 滚动）。批处理结果 tab 同一 FeatureTableView，
  两入口同享。验证：pytest **271 绿**（+10）+ e2e_m4 **19 项**（"PSD 曲线逐通道各一条
  8/8"、50Hz 压制改全曲线比值中位数 0.00）+ smoke + 三形态（raw 双窗/raw 柱状/epochs
  按码聚合柱状）白底截图目视确认——分析器报"黑底"经像素统计证伪（RGB 251 纯白）：
  **pg 全局白底主题在 MainWindow 里 `setConfigOptions` 设置，独立离屏截图脚本须手动
  复刻**，否则观感误判；合成数据同形白噪声 PSD 曲线重叠属数据特性非配色 bug。

- 2026-08-28（M8.2 完成，用户三截图反馈驱动）：**五视图观感三修**。
  **①堆叠系通道名挤叠**（各通道平均/单段浏览两视图）：y 轴 setTicks 放 25 导联名在有限
  窗高下必挤叠——改 M6 浏览器同款**行首内嵌 TextItem**（`anchor=(0,0.5)`、半透明白底、
  行首行基线；预览 tab 比浏览器矮，显式 8pt 压盒高——默认字号盒高≥行距相邻相触，离屏
  渲染实测）。**②蝶形图图例**：M8 "plot.clear() 清不到 legend 条目状态残留"的顾虑在 0.14
  实测**不成立**（clear 会清条目）——`addLegend(labelTextSize="8pt")` 逐通道挂"色线=通道名"；
  0.14 图例默认 **NoBrush 无底框**（文字压曲线）→ 半透明白底+灰框；单列 25 条在矮窗口
  排不到底被截断 → `setColumnCount`（每列至多 12 行自动分列，25 通道=3 列）。
  **③切时频图左轴 ticks 残留**（单段浏览→时频左上角飘通道名，用户截图证实）：根因=`_redraw`
  复位 invertY/label 但没清 ticks——堆叠系视图的通道名 ticks 残留、经 invertY(True) 翻到
  左上角；`_redraw` 统一 `setTicks([])` + 图例清空隐藏，`_draw_tfr` 里 **`setTicks(None)`
  恢复默认自动刻度系统**（`[]`=无刻度、`None`=自动——旧代码从蝶形切时频频率刻度被砍的
  暗病顺带修复）。验证：pytest **261 绿**（+4）+ e2e_m8 13 项 + e2e_m81 12 项零回归 +
  smoke + 离屏渲染 25 通道四视图截图亲眼确认。HANDOFF 坑 #57 新增。

- 2026-08-28（M8.1 完成，用户三问题反馈+时频截图驱动）：**三锚定分段 + 时频观感 + 单段浏览**。
  **①epoching 三锚定**：`EpochingParams` 加 `anchor: Literal["事件锚定","固定窗滑窗","手动时刻"]`
  （默认事件锚定——旧 JSON 缺键回填零回归）+ `step_s`（滑窗步进，空=无重叠）+ `anchors_s`
  （手动锚点秒）；锚点构造抽成 `_events/_fixed/_manual_anchors` 三个 @staticmethod（统一返回
  样本/码/event_id，事件分支纯搬移零修改），apply 三分支分发+尾段（reject/baseline/mne.Epochs/
  阶段翻转）一行不动；滑窗/手动**不查事件表**——CSV/TXT/HDF5、ds1/ds4 评估集等无事件数据
  从此可分段；手动锚点窗口越界**显式报错列出全部无效锚点**（mne `on_missing="ignore"` 会静默
  丢——显式枚举的输入要最小惊讶）；锚点一律**样本域**构造（秒域四舍五入差 1 样本会被静默丢）。
  **②时频观感三修**（用户截图证实热图纵向压成一条）：根因=堆叠/蝶形程序化 `setYRange` 禁用了
  autoRange，上一视图大范围残留——`_draw_tfr` 末尾 `autoRange()` 修复；配色下拉
  viridis/jet/hot（jet/hot 公式生成 **(256,3) uint8**——pg.ColorMap 收 0..1 float 色数组按
  0..255 截断得近全黑图且无告警；`setColorMap` 只换查找表不碰 levels，换色零亮度扰动）；
  时频结果**按通道缓存**（命中同步绘制零线程零重算，换配色/切走切回不再"计算中"闪烁）。
  **③第五视图「单段浏览」**（用户确认）：第 N 段全通道堆叠 + 段号 SpinBox + ◀/▶ + ←/→ 键盘
  （QShortcut 作用域限预览内），滑窗分段模式下即"翻页滑动看数据"；堆叠画法与平均视图共用
  `_draw_stacked`；第五项 **append 尾部**保 e2e_m8 按索引 0-3 寻址稳定。验证：pytest **257 绿**
  （+15）+ e2e_m81 **12 项** + e2e_m8 13 项零回归 + smoke。HANDOFF 坑 #56 新增；STATUS 上方
  新增"M8.1 关键实证结论"6 条。

- 2026-08-28（M8 完成，"可以按计划继续开发"指令）：**分段分析可视化**。
  **①EpochsPreviewView 四视图重构**：构造时一次取齐 `_data/_times/_codes/_ch_names/_sfreq`
  缓存（四视图切换零重算）；视图下拉+通道下拉（单通道/时频模式才启用）；`_redraw` 统一清空分发
  并**复位时频残留**（invertY/轴标签/LUT 色标——坑 #55）；teardown 幂等（`_data=None` 早退 +
  二调保护）。**②蝶形图**：`pg.intColor(i, hues=n)` 全通道同坐标+InfiniteLine 零线。**③单通道
  ERP**：逐段半透明灰细线（alpha 60）+**按事件码 `event_color` 分色**平均粗线（宽 2）+尾部
  TextItem 标码（不用 legend——clear 状态残留）。**④时频图**：`features/tfr.py`
  `compute_epochs_tfr`（morlet 段平均功率→基线 dB；2-45Hz 对数 24 点、n_cycles=freqs/2 下限 2、
  段数上限 80）经 `run_in_thread` 后台算（2a 60 段实测 0.02s）；ImageItem+setRect 贴数据坐标+
  invertY（低频在下）+HistogramLUT 色标；**迟到回调双保险**（`_data is None` + 视图模式 guard
  ——用户切走后结果丢弃不覆盖新视图）。**⑤`BandPowerParams.time_windows`**：`起-止` 秒语法
  （可负，`-1-0`）；epochs 相对事件锚点（epochs.times 坐标）/raw 绝对秒；越界容差一个采样
  周期（10s 录制输 0-10 天然合法）；窗标记拼进特征名 `alpha@0-1s`；spans=`[(None,"")]+窗`
  ——**整段条目始终在**，默认空=整段一条零回归。验证：pytest **242 绿**（+29）+ e2e_m8
  **13 项** + e2e_m1–m5/m7/smoke 回归全过。HANDOFF 坑 #55 新增；STATUS 上方新增"M8 关键实证
  结论"6 条。

- 2026-08-28（M7 完成，"直接按计划开始推进开发"指令，v2 方向首个里程碑）：**信号质量体检**
  ——固化收官后 4 轮手工"噪声感"诊断（羊噪声感/clinicaldata 空白/慢漂移普查/通道质量核查）。
  **①`features/qc.py` 双入口一算力**：`compute_channel_qc(get_window 闭包, ...)` 纯函数——
  浏览器传 `rec.get_window`（LAZY 不整载）、提取器传 `ctx.raw` 分窗闭包（PRELOAD 亦只取窗）；
  `_plan_windows` 均匀撒 ≤n_windows 个 win_s 窗→拼接算全局统计（钉极值要全程极值）。
  **②指标与分级**：开路复用（逐对 `np.array_equal`，先命中先记 dup_with）/死值（std<阈值）/
  平线占比（diff==0）/钉极值占比（**无绝对饱和阈值**，看钉本通道极值占比——满量程跨设备
  差 2 数量级）/漂移（窗中位数对窗中心最小二乘 µV/min）/直流中位（只进指标不定级）；
  bad=复用|死值|平直≥99%|钉极值≥50%，suspect=钉极值≥1% 或 |漂移|≥50µV/min。
  **③浏览器接线**：工具栏「质量体检」按钮→`run_in_thread` 防重入→通道列表 ✓/?/✗ 前缀+
  tooltip 中文问题明细与全部指标（`blockSignals` 包 setText/setToolTip——itemChanged 两者都
  触发）→坏道**建议确认**（question 弹窗列出坏通道与原因，Yes→逐个 toggle_bad 复用现有
  灰显/info["bads"]/bads_changed 机制，不静默改 bads）。**④注册表红利**：QualityCheckFeature
  （qc 排"添加特征"菜单首位）自动获得参数表单/批处理/CSV·HDF5 导出——零新 UI 架构；
  QC 通道选择与 pick_channels 相反：坏道参检不排除。**⑤黄金标准全复现**：羊 CH5-8 四通道
  开路复用判坏/CH1-4 真信号不坏（实测判疑似——低频峰值平台 rail≈2.3%、CH2/3 真实慢漂移，
  "疑似=建议人工复核"正是设计语义）/TPDJ-位置1 八通道全坏（M7 精化 M6.7b"全平"概括：分
  平线型与钉满量程+跳变型，CH2≡CH4 复用）；02号脑电 2 文件顺带诊断入册（DGDJ：CH5-8 两对
  复用坏；金盘：CH1≡CH2、CH4≡CH8 坏 4，CH3/5/6/7 真信号）。验证：pytest **213 绿**（+20，
  一个测试文件覆盖纯函数→注册表→UI→真实数据）+ e2e_m7 **16 项×2 幂等**（须逐模块 patch
  signal_browser.QMessageBox）+ e2e_m1–m5/smoke 回归全过。STATUS 上方新增"M7 关键实证
  结论"6 条。

- 2026-08-28（M6.8 完成，用户四项浏览增强需求驱动）：**①行居中开关**：工具栏 QCheckBox「行居中」默认开（=M6.7b 行为，现有回归零改动）；关闭 = 绝对电平显示（`out_v*gain`、无行偏移、通道间真实电平差直接可见）+ `_apply_y_range` 每次 y 自适配本窗口数据范围±2%（否则大偏移数据绝对模式又是"空白"镜像）；绝对模式行标签贴曲线本窗口中位（`ch["_med"]` 兜底隐藏通道）。**②通道列表直流偏移显示**：`_compute_channel_offsets` 后台分窗中位数取中位数（≤20 个均匀 2s 窗，不整载 LAZY 大文件）→ 主线程 `blockSignals` 包住拼 `"CH1  +68.9k µV"`（`itemChanged` 在 setText 也触发，不挡连发刷新）；通道名权威源迁 `UserRole`（右键/坏道标记不得再拿 item.text()）。**③增益输入框**：QDoubleSpinBox 0.01–100×（**勘误：滑杆 -20..20 配 10^(x/10) 实际就是 0.01–100×，旧注释/手册的"0.1×–10×"是错的**）；三入口统一 `_set_gain(float)`——滑杆粗调吸附、键盘 ±1.0 保小数（旧 setValue(int) 会把 2.5× 取整成 10×）、`_gain_syncing` 防环。**④总览时间轴滑块**：EventLane 升级——LinearRegionItem 做视口滑块（**逐线 setMovable(False) 冻结边缘=只平移不改宽**；拖出界 bounds 压窄由 browser 中心重锚自愈）、x 三重锁死 [0,duration]（旧版 setMouseEnabled(x=True) 允许用户拖走 lane 自己+autoRange 随事件漂移=用户"时间轴拖动逻辑不清晰"的根源）、`set_viewport`/`viewport_moved`+`_syncing` 双向防环、主图回写直连不经防抖（拖主图时滑块跟手）；顺带修 L89 硬编码"无事件"→`S.EVENT_LANE_NONE`。**⑤±1s 按钮**（`_step_s`，补充 0.9 屏翻屏的细分辨率）。验证：pytest **193 绿**×2（+22 项：TestStepSecond 3/TestGainInput 4/TestDcToggle 5/TestChannelOffsets 3/TestOverviewLane 7——event_lane 首次有测试）+ e2e_m1 **22 项** + e2e_m3 10 项 + smoke 回归 + 真窗口 DGDJ-位置4 四态截图亲眼确认（居中+偏移列表 / 绝对 y 自适配含 375k 饱和平线 / 2.50× 输入 / 回居中+滑块拖动 [31,41]+时间标签 36.00s/76.0s）。HANDOFF 坑 #52（LinearRegionItem 三细节）/#53（两处注释骗人+itemChanged setText）新增。

- 2026-08-27（M6.7b 完成，用户"第二个数据打开后 tab 空白"截图驱动）：**根因不是加载而是显示几何**（日志无错误/worker 健全/refresh 跑完；截图时间标签"5.00 s / 76.0 s"即 refresh 完成的证据）。**主因**：M6 锁 y 轴 + 堆叠公式假设基线 0 µV，clinicaldata（BioSemi BDF DC 耦合）CH1–4 真信号骑 4.5k–69k µV 直流偏移、CH5–8 饱和平线 ±375000 µV → 曲线全画在锁定 yRange 外，工具栏/标签/网格照常画 = "加载成功的空白"；"第一个能看"是位置1 偏移恰好落界的巧合。**修法 = 行居中**（EEG 浏览器标准做法）：显示值 = (原始值 − 本窗口该通道中位数) × gain + idx×spacing；`_estimate_spacing` 改只按有交流起伏通道（MAD>0.01µV）估计（≥5 条饱和平线会把间距 MAD 拖到 0 塌缩，TPDJ 形态），全平保持默认 100µV。**次因（顺带挖出随 M6.6 潜伏的笔误）**：`minmax_decimate` `t_max, v_max = t[…], t[…]` 双 t（单字符同字节长度，diff 隐形）→ 包络档 max 点全是时间戳、上半包络塌 0——正是 M6.7"10s 密集竖线带"观感的成分之一；诊断指纹 = 常数 375010 进 median 出 187505。验证：pytest **171 绿**×2（+TestOffsetRobustDisplay 4 项：显示中位在界内/平线不塌间距/平线贴行/全平默认间距；+TestMinMaxDecimateValues 2 项：常数进出/桶极值覆盖）+ e2e_m1 19 项 + e2e_m3 10 项 + smoke 回归 + **真窗口用户精确时序四连开（0/11/13/14s）逐 tab 截图亲眼确认 4/4 波形可见**（含用户截图中空白的位置4；教训：非白像素比例会被网格线假阳性，必须看内容——坑 #51）。clinicaldata 通道质量定论写入 DATA_NOTES §8；HANDOFF 坑 #49/#50/#51 新增。

- 2026-08-27（M6.7 完成，用户"10s 密集/9s 发虚"反馈驱动）：**①浏览渲染两档修复**：signal_browser.py raw 透传改 `connect="all"`（旧版无条件 pairs → 隔段漏画=虚线根因）+ 抽取阈值 `_SAMPLES_PER_PIXEL` 2→3 样本/px（Retina 逻辑px 1212 下旧阈值 2424 恰卡在 250Hz 数据 9s=2250/10s=2500 之间——10s 密竖线带、9s 断续虚线的观感突变全由跨档造成；3 让 1/2/5/10s 预设全留折线档、30s+ 才包络）+ main_window antialias 恢复 True（两档绘制点数约束在 ~3×像素宽内，关 AA 亚像素 1px 线段整段丢失）；离屏前后对比渲染实证（sheep/GDF 9s/10s 修后均为连续实线、30s 包络不变）。tests/test_ui_browser_m6.py +TestRenderTwoModes 2 项（折线档 connect=all/包络档 pairs，前提自检跨阈值）。**②工作区测试污染事故修复**：test_ui_workspace_remove.py `win` fixture 三重隔离重写——旧 teardown glob 的 `workspaces/<名>.json` 从不存在（真实布局是目录）、`current_workspace.txt` 标记被劫持不恢复（用户当天 1574 条真实导入被困 `test_删除_*` 目录、后续 pytest 首载 1574 稳定失败）；修法 = 构造前 preset 标记 + teardown closeEvent 落盘改道 tmp + 按真实布局 rmtree + 恢复标记；**用户数据已修复**（清合成来源并入 默认工作区 1572 条/7 来源、标记恢复、4 个残留目录清除，备份 /tmp/dataloadv_repair_backup_20260827_160326）。pytest **165 绿** + e2e_m1 19 项 + smoke 回归；HANDOFF 坑 #45 修正/#47/#48 新增。

- 2026-08-26（诊断闭环，零代码改动）：**慢漂移/幅值增长四轮实证**（用户"sheep+GDF 基线左低右高、幅值越来越高；EDF/MAT 无此问题"提问）：①sheep=**真实漂移**三形态——卧幅值 std ×300（6→1997µV）/data2 基线单调上斜 +204µV/min/术中全通道同号 22.5k→197kµV（参考漂移），纯 mne file-like 直读交叉一致排除读取层，0.5Hz 高通后羊残差 −890µV→建议 高通+去均值/重参考 组合；②GDF 63 文件全量普查——EEG 基线全库 ≤3µV 平稳，唯一例外 B0204E 88µV 系 **EOG 眼电**末段暴跌（EEG 本身 0.1µV 平稳）；"幅值增长"= 开头静息段 + EOG 任务锁定尖峰（EEG std 全程 3–11µV）、无尾部零填充；③EDF/MAT 平稳=录制硬件差异（BioSemi DC 耦合 vs g.USBamp 0.5–100Hz 带通 vs 离线预处理）。方法学：首末窗均值差/std 比 + 时间分辨剖面 + 逐通道×逐时段矩阵 + 纯 mne 交叉 + 整文件 1s 包络 PNG（pyqtgraph offscreen grab）。定论写入 DATA_NOTES §1/§4。

- 2026-08-24（M6.6 完成，用户两问驱动）：**①羊"噪声感"诊断定论**（诊断脚本实证，零代码改动）：CH5–CH8 逐样本相同=开路通道复用（饱和/死值伪迹）、CH4 部分饱和、CH1–CH3 真实皮层信号带大直流偏移、换算 0.125µV/LSB 正确——结论与浏览建议（右键标坏道 CH4–CH8 + 去均值/带通后看 CH1–CH3）写入 DATA_NOTES §1；**②工作区移除条目功能**：ui/strings_zh.py +5 文案（右键菜单/确认框/状态栏）；ui/widgets/workspace_tree.py 加 `remove_requested(list)` 信号（右键菜单 + `_TreeWithDel` 内层树接管 Del/Backspace——焦点在树上容器收不到 keyPress；`_paths_for_item` 分类：录制项单 path/来源节点整组/根不参与）；ui/main_window.py `_remove_from_workspace`（多条先 QMessageBox 确认 → workspace.remove_recording + save + notify 刷新，**只清索引不删磁盘文件**，已开 tab 保留）；tests/test_ui_workspace_remove.py 新建 +6（163 绿，**MainWindow 级测试须 offscreen**）；e2e_m1 19 项 + smoke 回归；MANUAL §3.4/计数、README 计数同步。

- 2026-08-24（M6.5 完成，用户发现羊数据实为 BDF 驱动）：io/registry.py 新 `_dispatch_readers` **魔数内容优先派发**（EDF/BDF/GDF/BrainVision 嗅探定位读取器，扩展名不符记 warning、不兜底）+ io/mne_readers.py 通用 `_read_mne_robust`（mne `_check_args` 扩展名硬拒绝时 **file-like 对象重读公共入口**绕过——用户指定方案，不直接实例化 Raw*；读后 `_detach_file_handles` 剥离 mne 内部两处句柄残留防 deepcopy 炸；latin1 回退保留；模板基类加 `_robust` 声明）+ io/sniffing.py 修 EDF 分支 off-by-one（`head[:8]` 严格 8 字节版本域；删无引用的 `is_edf`）+ core/workspace.py `add_metas` 重复导入刷新 meta（rec_id 稳定、内容以新扫描为准）；**纠正 M1 以来羊数据按 EDF 错误解码的数据正确性 bug**（真实时长：sheep 180/182/222s、sheep2 1000/1075s、sheep3 301s）；**同日两项用户问题闭环**：①羊标注通道逐字节核查——全纯 ASCII TAL 空注释、满足 UTF-8（"羊需要 latin1"为误解码副产品，无需改码）；②读取方式改 file-like+read_raw_bdf（含 deepcopy 残留句柄坑修复，e2e_m3 预览链路回归验证）；tests 重写羊断言+净增 6（157 绿）；e2e_m1 +1 项（19 项 ALL OK）+ m2–m5/smoke 回归；DATA_NOTES 羊三目录重写 + MANUAL/README 同步。

- 2026-08-18（M6 完成，用户实测反馈驱动）：signal_browser.py 重构——`_PanViewBox`（滚轮=平移/Ctrl+滚轮=锚点缩放、y 锁定）、通道名 TextItem 行内嵌（删 y 轴 setTicks）、幅值标尺（60px 固定像素 + `_nice_number` 1/2/5×10^k 换算 µV）、窗口导航（|◀/◀/一屏时长 QComboBox/▶/▶|、`_set_x_range` 统一 clamp、翻屏 0.9 屏、键盘 ←→Home End ↑↓、StrongFocus+焦点代理）；**修复增益双 bug**（乘间距不乘波形→乘波形不乘间距；`_gain` 初值 1.0→0.0）；浅色主题（main_window `background="w"` + S.SIGNAL_PEN_COLOR #1f77b4 / S.PLOT_TEXT_COLOR #333333 / PSD 色板 #d62728,#1f77b4,#2ca02c,#9467bd / 事件黄→#b8860b / batch 状态色加深）；tests/test_ui_browser_m6.py +13（150 绿）；e2e_m1 +5 项（18 项 ALL OK）+ e2e_m3/smoke 回归；MANUAL 交互表重写。

- 2026-08-18（v1 收官后补充）：编写 **MANUAL.md**（说明/运行/使用/调试一册通览，README 已链接）；盘点 UI 时发现并修复 **事件跳转按钮接线反了**（signal_browser.py：`◀ 上一事件`误接 `_jump_event(+1)` 即跳更晚事件——两按钮 lambda 对调，代码内留注释；e2e_m1 直接调 `_jump_event(1)` 语义未受影响，回归 ALL OK）。

- 2026-08-18（M5 完成，v1 收官）：batch/jobs.py（JobSpec/PipelineSpec 启动前校验/FileResult/BatchSummary）+ batch/engine.py（**BatchEngine 纯 Python**——ThreadPoolExecutor 默认 2 线程、threading.Event 取消、单文件失败不杀整批、LoadedRawCache pin 防并发互逐、_export CSV/H5+sidecar batch extra）；proc/base.py + features/base.py 加 `cancel_check`（逐步骤检查抛 PipelineCancelled）；core/app_settings.py（pydantic 设置 + 原子写 + 热生效）；UI（batch_view 进度表/失败行红显/双击日志对话框、batch_dialog 两页+queue.Queue+QTimer150ms 事件泵、settings_dialog 三字段、主窗口文件/处理菜单接线 + 批处理结果 tab）；io/neo_reader.py（_NeoRawReader 模板 + Blackrock/OpenEphys/Intan）+ io/nwb_reader.py（ElectricalSeries/trials→EventTable）；README 重写（v1 全览/典型流程/验证口径）；tests +15（137 绿）；e2e_m5 19 项 ALL OK + m1-m4/smoke 回归全绿。

- 2026-08-18（M4 完成）：proc/crop.py（时间窗裁剪，四层决策第③层；raw 绝对时间/epochs 相对事件锚点）；features/base.py（FeatureExtractor ABC + FEATURE_REGISTRY + apply_features，与 proc 层同构）+ spectral.py 扩展（array_welch 数组版 + BandPowerFeature 频带功率 δθαβγ+自定义+相对/对数 + WelchPsdFeature PSD 曲线仅 raw）+ timedomain.py（8 统计量纯 numpy）；batch/results.py FeatureTable（长表 COLUMNS 7 列 + 中文表头映射 + to_wide dropna=False）；export/ 三模块（features_io CSV BOM 中文表头+曲线宽表分轴分组/HDF5、epochs_io HDF5 结构化+FIF、provenance .pipeline.json sidecar）；UI（pipeline_panel 特征区+视口预填+features_ready、feature_table.py 特征结果 tab 数值排序、主窗口处理菜单 4 动作）；tests +50（122 绿）；e2e_m4（18 项：羊 104 行/50Hz 峰消除、A01T 14400 行、HDF5/FIF 回读一致）。

- 2026-08-18（M3 完成）：proc/（context/base/filters/referencing/resample/bads/epoching/preview——6 步骤 + STEP_REGISTRY + apply_pipeline 阶段检查 + 预览副本包装）；features/spectral.py mean_welch；UI（params_form pydantic 自动表单/pipeline_panel/psd_view/epochs_preview）；signal_browser 坏道右键标记+灰显+bads_changed 联动；主窗口处理菜单+预览 tab 接线；tests +29（72 绿）；e2e_m3（11 项：羊 50Hz 压制比 0.0001、A01T 288 段）。

- 2026-08-18（M2 完成）：io/mne_readers.py 重写为 `_MneRawReader` 模板基类家族（8 格式，`_read_fn` 必须 staticmethod）；io/event_maps.py（GDF 官方码表 16 码中文标签）；io/bciciv_mat.py（ds1 头只 loadmat nfo/mrk、ds4 纯 whosmat、未知 mat 拒绝猜测）；io/table.py（分隔符嗅探+数值性验证+FS_UNSET_NOTE）+ io/hdf5.py（零数据 IO 定位信号集）；core/fs_store.py（CSV/HDF5 采样率询问记忆）；主窗口采样率询问对话框；**workers/generic.py 加 `_MainRelay`**（修 worker 线程回调弹窗冻结——M2 最关键产品修复）；嗅探补 GDF/BDF/HDF5/BrainVision 魔数；e2e_m2.py（17 项）。
- 2026-08-18（M1 完成）：core/recording.py（Recording/EventTable/LRU 缓存，修锁内逐出死锁）+ core/workspace.py（JSON 原子持久化）；io 层（BaseReader ABC/注册表/scan_folder 进度回调/EDF latin1 回退）；UI（导入控制器+错误表/工作区树/元数据表/信号浏览器窗口化+峰值包络/事件条+跳转导航）；修 3 个实测坑（PySide worker GC、PlotItem 构造期无 scene、load_raw 收 str path）；E2E 脚本幂等化。
- 2026-08-18（M0 完成）：conda env dlv、包骨架、主窗口、治理文件、首次 commit。
- 2026-08-18（启动）：方案批准、git 初始化。
