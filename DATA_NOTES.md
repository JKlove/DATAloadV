# DATA_NOTES — 本地数据集说明

> `data/` 目录全部数据的信息说明：来源、结构、关键参数、事件编码、已知坑、以及本项目（DataloadV）对它的读取行为。
> 该目录**全程只读**。本文档随新数据/新实证发现更新。最后更新：2026-08-18（M2 完成时全部核实）

## 目录总览

| 目录 | 内容 | 规模 | 状态 |
|---|---|---|---|
| `data/sheep/` | 羊在体实验 EDF（3 种姿态） | 3 文件 | ✅ M1 起支持 |
| `data/sheep2/` | 羊实验 EDF 第二批 | 2 文件 | ✅（同为 EDF 路径） |
| `data/dataset/files/` | PhysioNet eegmmidb（运动想象） | 109 被试 × 14 run，3060 文件，3.4GB | ✅ M1 起支持 |
| `data/dataset/BCICIV_2a_gdf/` | BCI Competition IV 2a | 9 被试 × (T/E)，18 文件，575MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_2b_gdf/` | BCI Competition IV 2b | 45 文件，271MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_1_mat/` | BCI Competition IV 1（ds1） | 7 被试 × (calib/eval)，14 文件，340MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_3_mat/` | BCI Competition IV 3（ds3，分段 MEG） | S1/S2.mat + SensorPos.pdf，14MB | ❌ 识别后拒绝（backlog） |
| `data/dataset/BCICIV_4_mat/` | BCI Competition IV 4（ds4，ECoG+手套） | 3 文件，372MB | ✅ M2 起支持 |
| `data/clinicaldata/` | 临床数据（预留） | 空 | — |

---

## 1. `sheep/` — 羊在体电生理实验

- **文件**：`data(DGDJ-卧-接地-2)-HKY.edf`、`data(DGDJ-站-接地-4)-HKY.edf`、`data(DGDJ-走动-接地-3)-HKY.edf`
- **命名含义**：DGDJ = 电极记号；`卧/站/走动` = 姿态；`接地` = 接地条件；数字 = 实验序号；HKY = 实验者标记
- **参数**（头解析实测）：8 导 / 250 Hz / 时长约 270 s（各文件不同）/ 无事件标注
- **已知坑**：文件名与内嵌注释含**非 UTF-8 字节（latin1 区）**——mne 默认编码直接 UnicodeDecodeError。
  本项目 `EdfReader` 内置 latin1 自动回退（解法源自 pipelineMotor `formats.py` 的 EdfLatin1Adapter）
- **sheep2/**：`data2.edf`、`data3.edf`（8 导 / 250 Hz / 1500 s / 无事件），同走 EDF 读取路径

## 2. `dataset/files/` — PhysioNet eegmmidb（EEG Motor Movement/Imagery）

- **内容**：S001–S109 共 109 被试，每人 R01–R14 共 14 个 run（任务：睁闭眼、真实/想象左右手握拳等）
- **参数**：64 导 EEG（国际 10-10，Sharbrough 导联，位置图见目录下 `64_channel_sharbrough.pdf`）/ 160 Hz
- **事件**：EDF 内嵌 T0（静息）/T1（左拳真实或想象）/T2（右拳）标注，实测 S001R03 含 30 个（T0×15/T1×8/T2×7）；
  每个文件另有 `.edf.event` WFDB 边车——实测为**内嵌注释的冗余副本**，本项目不解析（backlog）
- **杂项文件**：`RECORDS`/`ANNOTATORS`/`SHA256SUMS.txt`/导联图 png 等——扫描时被忽略或（txt）数值性验证挡下

## 3. `dataset/BCICIV_2a_gdf/` — BCI Competition IV 数据集 2a

- **内容**：A01–A09 共 9 被试，各 1 个训练（`A0xT.gdf`）+ 1 个评估（`A0xE.gdf`）文件
- **参数**：22 EEG + 3 EOG = 25 导 / 250 Hz；4 类运动想象（左手/右手/双脚/舌头）
- **事件**：见下表官方码表；A01T 实测 603 个事件
- **来源**：http://www.bbci.de/competition/iv/ （官方说明 desc_2a.pdf，本项目码表即由其原文提取核实）

## 4. `dataset/BCICIV_2b_gdf/` — BCI Competition IV 数据集 2b

- **内容**：B01–B09 共 9 被试 × 5 文件（`B0x01T`–`B0x05E`），共 45 文件；命名 = 被试 + 场次 + T/E
- **参数**：3 双极 EEG（C3/Cz/C4）+ 3 EOG = 6 导 / 250 Hz（B0101T 实测 2419 s、271 事件）；2 类想象（左右手）
- **事件**：同下表；含 781（BCI 连续反馈）码

### GDF 官方事件码表（2a/2b 共用，本项目 `io/event_maps.py` 的依据）

| 码 | 含义 | 码 | 含义 |
|---|---|---|---|
| 276 | 静息（睁眼） | 1072 | 眼动 |
| 277 | 静息（闭眼） | 1077 | 水平眼动 |
| 768 | 试次开始 | 1078 | 垂直眼动 |
| 769 | 提示：左手（类1） | 1079 | 眼球旋转 |
| 770 | 提示：右手（类2） | 1081 | 眨眼 |
| 771 | 提示：双脚（类3） | 32766 | 新 run 开始 |
| 772 | 提示：舌头（类4） | 1023 | 被拒绝试次 |
| 781 | BCI 反馈（连续） | 783 | 提示：未知（评估集） |

> ⚠️ 以上译自官方 desc_2a.pdf / desc_2b.pdf **原文**（pypdf 提取）。网络搜索摘要多处错误（如把 781 误作 correction/beep、1077 误作 eyes closed），勿引用二手转述。

## 5. `dataset/BCICIV_1_mat/` — BCI Competition IV 数据集 1（ds1，皮质电极运动想象）

- **内容**：7 被试 ds1a–ds1g，各 1 个 `BCICIV_calib_ds1x.mat`（校准）+ 1 个 `BCICIV_eval_ds1x.mat`（评估）
- **结构**：calib = `{cnt[59×N], nfo{fs,clab,classes}, mrk{pos,y}}`；eval = **只有 cnt/nfo，无 mrk**
  （评估集标签未随数据发布——pipelineMotor yaml 所说"评估集有提示"与实物不符）
- **参数**（calib ds1a 实测）：59 导 / 100 Hz / 1906 s / 200 事件
- **标度**：cnt 为 int16，LSB = **0.1 µV**（本项目读取时换算为伏特）
- **事件**：mrk.y ∈ {+1,-1} → 类名 left/foot（code），中文标签 左手/脚

## 6. `dataset/BCICIV_3_mat/` — BCI Competition IV 数据集 3（ds3，MEG）❌ 暂不支持

- **内容**：S1.mat / S2.mat（分段 MEG）+ SensorPos.pdf（传感器位置图）
- **为何拒绝**：数据为**分段（epoched）结构**而非连续记录，与本项目当前连续 raw 模型不匹配。
  读取时给出明确中文说明并指向 backlog（TODO.md），**不猜测结构**
- **何时补**：M3 分段（epochs）模型落地且确有需求时

## 7. `dataset/BCICIV_4_mat/` — BCI Competition IV 数据集 4（ds4，ECoG 手指运动）

- **内容**：`sub1_comp.mat` / `sub2_comp.mat` / `sub3_comp.mat`（134/125/113MB）
- **结构**：`{train_data[ECoG×N], train_dg[手套5指×N], test_data, test_dg}`
- **参数**（sub1 实测）：64 ECoG + 5 手套 = 67 导（手套为 misc 通道 thumb/index/middle/ring/little）/ 1000 Hz / 400 s
- **已知坑**：① 文件内**无采样率**——fs=1000 Hz 来自官方 desc_4.pdf；② train_data 是 **double** 非 int32；
  ③ test_data ~100MB 且无标签——本项目读取时跳过（加载实测 0.2s）
- **无离散事件**：连续回归任务（预测手指弯曲度），事件数为 0

---

## 与本项目读取器的对应关系

| 数据 | 读取器（reader_id） | 备注 |
|---|---|---|
| sheep / sheep2 / PhysioNet | `edf` | latin1 回退仅羊文件需要，其余同路径 |
| 2a / 2b | `gdf` | 事件自动套用上表中文标签 |
| ds1 calib/eval | `bciciv_ds1` | eval 无事件（notes 说明） |
| ds4 | `bciciv_ds4` | 头解析纯 whosmat（<1s），加载跳过 test_data |
| ds3 / 未知 mat | —（明确报错） | 拒绝猜测原则 |
