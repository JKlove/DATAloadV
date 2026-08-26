# DATA_NOTES — 本地数据集说明

> `data/` 目录全部数据的信息说明：来源、结构、关键参数、事件编码、已知坑、以及本项目（DataloadV）对它的读取行为。
> 该目录**全程只读**。本文档随新数据/新实证发现更新。最后更新：2026-08-24（羊通道质量核查：CH5–CH8 为开路复用通道）

## 目录总览

| 目录 | 内容 | 规模 | 状态 |
|---|---|---|---|
| `data/sheep/` | 羊在体实验（**BDF 内容的 .edf**，3 种姿态） | 3 文件 | ✅ M6.5 起按 BDF 正确读取 |
| `data/sheep2/` | 羊实验第二批（**BDF 内容的 .edf**） | 2 文件 | ✅（同上） |
| `data/sheep3/` | 羊实验第三批·术中（**BDF 内容的 .edf**） | 1 文件 | ✅ 2026-08-24 新增 |
| `data/dataset/files/` | PhysioNet eegmmidb（运动想象） | 109 被试 × 14 run，3060 文件，3.4GB | ✅ M1 起支持 |
| `data/dataset/BCICIV_2a_gdf/` | BCI Competition IV 2a | 9 被试 × (T/E)，18 文件，575MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_2b_gdf/` | BCI Competition IV 2b | 45 文件，271MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_1_mat/` | BCI Competition IV 1（ds1） | 7 被试 × (calib/eval)，14 文件，340MB | ✅ M2 起支持 |
| `data/dataset/BCICIV_3_mat/` | BCI Competition IV 3（ds3，分段 MEG） | S1/S2.mat + SensorPos.pdf，14MB | ❌ 识别后拒绝（backlog） |
| `data/dataset/BCICIV_4_mat/` | BCI Competition IV 4（ds4，ECoG+手套） | 3 文件，372MB | ✅ M2 起支持 |
| `data/clinicaldata/` | 临床数据（预留） | 空 | — |

---

## 1. `sheep/` + `sheep2/` + `sheep3/` — 羊在体电生理实验（**BDF 内容的 .edf**）

- **文件与真实时长**（BDF 正确解码实测，2026-08-24）：

| 文件 | 通道 | 采样率 | 时长 | 事件 |
|---|---|---|---|---|
| `sheep/data(DGDJ-卧-接地-2)-HKY.edf` | 8 | 250 Hz | 180 s | 无 |
| `sheep/data(DGDJ-站-接地-4)-HKY.edf` | 8 | 250 Hz | 182 s | 无 |
| `sheep/data(DGDJ-走动-接地-3)-HKY.edf` | 8 | 250 Hz | 222 s | 无 |
| `sheep2/data2.edf` | 8 | 250 Hz | 1000 s | 无 |
| `sheep2/data3.edf` | 8 | 250 Hz | 1075 s | 无 |
| `sheep3/data(ZJDJ-术中-羊20260713).edf` | 8 | 250 Hz | 301 s | 无 |

- **命名含义**：DGDJ = 电极记号；`卧/站/走动` = 姿态；`接地` = 接地条件；数字 = 实验序号；HKY = 实验者标记；
  ZJDJ（sheep3）= 另一电极记号，`术中` = 术中记录，羊20260713 = 日期
- **重大实锤（2026-08-24，用户发现）**：6 个 `.edf` 文件**内容全是 BDF**（文件头前 8 字节
  `\xffBIOSEMI`，BioSemi 24-bit 格式）——扩展名是错的。此前 M1–M6 按 EDF 路径读取，把 24-bit
  样本按 16-bit 解码：**样本数虚增 1.5×（如 180 s 读成 270 s）、全部数值错位**，当时的波形/
  PSD/滤波/特征都是伪数据。M6.5 起 `registry.open_file` 按魔数"内容优先"派发（`\xffBIOSEMI`
  → BdfReader），warning 提示扩展名不符
- **latin1 坑的再认识**：此前记录的"非 UTF-8 注释需 latin1 回退"发生在**错误的 EDF 解码路径**上；
  按 BDF 正确读取后羊文件不再触发编码错误。latin1 回退机制仍保留在 `_read_mne_robust`
  （对真 EDF 的非 UTF-8 注释仍有意义）
- **标注通道核查定论（2026-08-24，用户提问驱动逐字节验证）**：6 个文件的 "BDF Annotations"
  通道（BDF+C 格式第 9 个信号）**内容全为纯 ASCII**——标准 TAL 时间戳 `+0\x14\x14\x00`、
  `+1\x14\x14\x00`…（每秒一条**空文本**注释，去零后 20K–122K 字节，高位字节集为空）。
  满足 UTF-8、默认 utf8 编码零报错；**零事件是数据本身的属性**（空注释无语义），不是读取 bug。
  "羊需要 latin1"确系误解码副产品（错位字节被当注释文本做 UTF-8 校验才报 invalid byte）
- **文件头速查（手工解析实证）**：固定头 256B——记录数@236、每记录秒@244、ns@252；
  ns=9（8×CH + BDF Annotations）；信号子头**字段主序**（label 每通道 16B 连续排、
  samples 区在 `256+ns*216`），数据区起点 = headerbytes 字段值（如 2560，可自校验）
- **通道质量核查定论（2026-08-24，用户"读出来都是噪声"提问驱动）**——"噪声感"不是读取 bug，
  是**部分通道本身没有接电极**：
  - **CH5–CH8：逐样本完全相同**（`np.array_equal(CH5,CH6,CH7,CH8)` 全 True）= 采集箱把未接/
    开路通道**复用成同一段缓冲**；数值要么钉死在 ±375000 µV 满量程饱和、要么 std=0 死值。
    浏览器里这四条"波形"是伪迹，不是电生理信号。
  - **CH1/CH2/CH3：真实信号**——CH1 去直流 + 带通 1–40 Hz 后 std≈279 µV、宽带 β 节律为主，
    符合羊皮层场电位（LFP/ECoG 量级）特征；但**带大直流偏移**（mean 数十 mV），直接浏览
    会看到"信号骑在一条大斜线/台阶上"。CH4 部分文件饱和、部分活跃（阈值边界）。
  - **换算链正确**：physmin/max=±1048576 µV、digimin/max=±8388608 → 0.125 µV/LSB，mne
    按 BDF 解码的数值与手算一致，非读取错误。
  - **浏览建议**：右键把这批文件的 CH4–CH8 标为坏道（M6 已有功能）；对 CH1–CH3 先加
    `去均值/重参考` + `带通 1–40 Hz` 再浏览（处理面板预览即可，不动原文件）；sheep3（术中）
    噪声本底比 sheep/sheep2 大，属记录条件差异。

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
| sheep / sheep2 / sheep3 | `bdf` | **.edf 扩展名实为 BDF**——魔数内容优先派发（M6.5） |
| PhysioNet | `edf` | 标准 EDF，扩展名与内容一致 |
| 2a / 2b | `gdf` | 事件自动套用上表中文标签 |
| ds1 calib/eval | `bciciv_ds1` | eval 无事件（notes 说明） |
| ds4 | `bciciv_ds4` | 头解析纯 whosmat（<1s），加载跳过 test_data |
| ds3 / 未知 mat | —（明确报错） | 拒绝猜测原则 |
