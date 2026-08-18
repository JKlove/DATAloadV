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

# 4. 本包可编辑安装（含 dev 依赖）
pip install -e "/Users/huyingbing/VSproject/intervention BCI/DataloadV[dev]"
```

**实际安装后的版本**（2026-08-18 M0 安装实测，与 STATUS.md 保持同步）：

| 包 | 版本 | 来源 |
|---|---|---|
| Python | 3.10 | conda env `dlv` |
| numpy / scipy / pandas | 1.26.4 / 1.15.2 / 2.3.3 | conda-forge |
| PySide6 / pyqtgraph | 6.11.0 / 0.14.0 | conda-forge |
| mne / edfio | 1.12.0 / 0.4.16 | pip |
| pydantic / h5py | 2.13.4 / 3.16.0 | conda-forge |

## 运行与测试

```bash
conda activate dlv
dataloadv                                    # 启动应用（或 python -m dataloadv）
pytest                                       # 全部单测（M0：3 passed）
python scripts/smoke_gui.py                  # GUI 冒烟：真窗口启动自检后自动退出
pytest -m real                               # 真实数据冒烟（M1 起建立；data/sheep 缺失自动跳过）
```

## 架构导览（M0 时的骨架，后续里程碑充实）

```
src/dataloadv/
├── app.py / __main__.py     # 入口：QApplication、高 DPI、excepthook→日志
├── core/                    # 计算层核心（禁止 import Qt）
│   ├── recording.py         # Recording 统一数据模型 + LoadedRawCache 内存 LRU（M1）
│   └── workspace.py         # 工作区与持久化（M1）
├── io/                      # 读取器层（禁止 import Qt）——注册表模式，每格式一个 Reader
├── proc/                    # 预处理步骤（M3）——每步=pydantic参数+apply(ctx)，可序列化
├── features/                # 特征提取器（M4）
├── batch/                   # 批处理引擎（M5）
├── export/                  # 导出与溯源 sidecar（M4）
├── workers/generic.py       # run_in_thread：后台任务→信号回调
└── ui/                      # 全部 Qt 代码：主窗口/dock/对话框/部件；strings_zh.py 集中中文文案
```

**四条硬性规则**（review 时检查）：
1. core/io/proc/features/batch/export 不得 import PySide6/pyqtgraph
2. UI 不做计算，一律经 workers/batch 线程 + 信号
3. 跨线程只传纯 Python/mne 对象
4. 里程碑收尾四件事：治理文件更新 → review.md 记录 → 上下文检查（≥70% 压缩）→ git commit

## 代码风格约定

- 标识符英文，**docstring 与关键注释中文**（用户要求：后续维护者不读实现也能懂）
- 类/函数 docstring 写清：用途、参数、返回、异常；关键算法处注释解释"为什么"而非"是什么"
- pydantic v2 建模所有可序列化配置/参数；pandas 用于表格结果
- git：仓库级身份 `DataloadV Dev <dev@dataloadv.local>`；每里程碑一次 commit，消息格式 `M<编号>: <内容摘要>`

## 坑与注意事项（踩过的坑写这里，防止重蹈）

1. **羊 EDF 非 UTF-8**：注释/TAL 通道含非 UTF-8 字节（如 0xc6），`mne.io.read_raw_edf` 默认编码会抛 UnicodeDecodeError——必须 `encoding="latin1"` 重试（解法源自 pipelineMotor `formats.py` 的 EdfLatin1Adapter，本项目的 EdfReader 将其内置为自动回退）。
2. **BCI-IV ds4 .mat 很大**（118–134MB）：loadmat 出来是 int32/float64，要 `astype(np.float32)` 物化并 `del` 中间体，否则内存翻倍。参考 pipelineMotor `data/mat_loader.py` 的结构解析（本项目重新实现，不导入）。
3. **mne 滤波需要 preload=True**：浏览器展示可保持 lazy，但预览/批处理在第一步前必须确保 preload。
4. **`data/` 目录只读**：4.9GB 原始数据，应用绝不写入；用户配置在 `~/.dataloadv/`，导出去用户选择的目录。
5. **Qt 回调里绝不能让异常挡住退出**：M0 冒烟首版在 QTimer 回调中抛 AttributeError 导致 `app.quit()` 未执行、进程悬挂。规则：自检/回调类代码把断言包 try、把 quit/cleanup 放 finally（见 scripts/smoke_gui.py）。
6. **`mne.Annotations` 不接受 `verbose` 参数**（与多数 mne 类不同），构造时不要传。

## 当前接手要点（2026-08-18，M0 已完成）

- M0 全部完成并验证（见 review.md）；下一步是 **M1**，任务拆解见 TODO.md「M1」一节
- 已有代码量小（入口/日志/worker/主窗口骨架），先读 `plan.md` §4 核心设计再动工 Recording 模型
- M1 关键外部事实：sheep EDF 的 latin1 问题（坑 #1）、PhysioNet .edf 配套 .event 边车文件（WFDB 布局，事件从边车读）
