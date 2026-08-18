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
