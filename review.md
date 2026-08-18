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
