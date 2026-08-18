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
pytest                                       # 全部单测（M1：17 passed，含 5 个 real 羊数据项）
pytest -m real                               # 仅真实数据冒烟（data/sheep 缺失自动跳过）
python scripts/smoke_gui.py                  # GUI 冒烟：真窗口启动自检后自动退出
python scripts/e2e_m1.py                     # M1 端到端：真实导入→浏览→渲染→释放（幂等，可反复跑）
```

## 架构导览（M1 后的实际结构）

```
src/dataloadv/
├── app.py / __main__.py     # 入口：QApplication、高 DPI、excepthook→日志
├── core/                    # 计算层核心（禁止 import Qt）
│   ├── recording.py         # Recording/RecordingMeta/EventTable/LoadPolicy/LoadedRawCache（M1）
│   └── workspace.py         # Workspace + ~/.dataloadv/ JSON 持久化（M1）
├── io/                      # 读取器层（禁止 import Qt）——注册表模式，每格式一个 Reader
│   ├── base.py              # BaseReader ABC：read_meta 仅头/open/load_raw/sniff/common_meta_fields
│   ├── registry.py          # @register_reader + open_file/scan_folder（容错+进度回调）
│   ├── sniffing.py          # 魔数嗅探（EDF 已有，M2 扩充）
│   └── mne_readers.py       # EdfReader（latin1 自动回退）；M2 补 BDF/GDF/BV/FIF/EEGLAB/CNT/EGI
├── proc/                    # 预处理步骤（M3）——每步=pydantic参数+apply(ctx)，可序列化
├── features/                # 特征提取器（M4）
├── batch/                   # 批处理引擎（M5）
├── export/                  # 导出与溯源 sidecar（M4）
├── workers/generic.py       # run_in_thread：后台任务→信号回调（worker 挂 thread 保活，见坑 #7）
└── ui/                      # 全部 Qt 代码
    ├── main_window.py       # 主窗口：导入/工作区树 dock/元数据表/浏览 tab 区
    ├── state.py             # SessionState 信号中枢（recording_opened 等）
    ├── strings_zh.py        # 全部中文文案集中（class S）
    ├── dialogs/import_dialog.py   # 导入控制器：worker 扫描→进度→错误表
    └── widgets/             # workspace_tree / meta_table / signal_browser / event_lane / log_panel
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
7. **PySide6 信号连接不持有 Python receiver 引用**：Worker 作为局部变量在 run 触发前就可能被 GC（线程空转、回调静默丢失，伴随 "QThread: Destroyed while thread is still running"）。解法：`thread._dlv_worker = worker` 保活（workers/generic.py 已内置）。
8. **pg.PlotItem 构造期 `self.scene()` 为 None**：要绑 sigMouseClicked 等场景级事件，必须在加入 GraphicsLayoutWidget 之后——EventLane 用 `wire_click()` 延迟绑定模式，浏览器挂载后调用。
9. **读取器收到的 path 可能是 str**（如 meta.path 从 JSON 反序列化回来）：所有 `path.name`/`path.suffix` 操作前先 `path = Path(path)` 归一（_read_edf_robust 已内置）。
10. **锁内调 unload 的死锁模式**：LoadedRawCache 曾在持锁状态下调 `rec.unload()`→`forget()` 再拿非重入锁。规则：锁内只"选受害者摘链"，实际 unload 在锁外执行（_pick_victims_locked / _unload_victims 分离）。
11. **e2e/测试脚本必须幂等**：工作区持久化在 `~/.dataloadv`，脚本开头 `reload_workspace("一次性名字")`、结束切回原工作区，否则二次运行全是"重复导入"。

## 当前接手要点（2026-08-18，M1 已完成）

- M1 全部完成并验证（pytest 17 绿 + e2e_m1 13 项全过，见 review.md）；下一步是 **M2 读取器全覆盖**，任务拆解见 TODO.md「M2」一节
- M2 动工顺序建议：先 mne_readers.py 补 BDF/GDF/BrainVision/FIF/EEGLAB/CNT/EGI（全是 `mne.io.read_raw_*` 包装，模式照抄 EdfReader），再 event_maps.py GDF 事件码中文映射，最后 bciciv_mat.py（结构最复杂，参考坑 #2）与 table.py/hdf5.py
- M1 三条实证结论（写代码前实测得来，M2 沿用同方法论）：① PhysioNet EDF 内嵌注释完整，边车冗余已取消；② S001 每被试 14 个 run；③ latin1 回退 mne 1.12 实测有效
- 读取器新格式的通用套路：`RecordingMeta(**self.common_meta_fields(path, fmt), ...)` 一次构造（勿手拼 dict，会缺必填字段）；`_meta_from_raw` 用已构造的 raw 提 n_channels/freq/duration/events
