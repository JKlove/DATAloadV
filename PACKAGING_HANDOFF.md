# DataloadV 双平台打包——实施指令（交接文档）

> 本文档自包含：新开 Claude Code session 或交给任何实现者，读完即可开工，无需其他上下文。
> 由 M9 收官会话于 2026-09-01 依据当前代码实态（commit 4bdf905，pytest 287 绿）撰写。

## 执行状态（2026-09-01 M10 会话回填——接手先读这里）

- **M10-1 ✅**：PyInstaller 6.22.2（conda-forge）+ `packaging/entry.py` + `dataloadv.spec`
  已交付；全量构建 42s / .app 293MB / zip 119MB。
- **M10-2 🔶**：机器可验部分全过（offscreen `--smoke` SMOKE OK / 真窗口存活+优雅退出 /
  PYZ 延迟依赖核实 / pytest 287 零回归 / Gatekeeper 状态记录）；app 已加 `--smoke` 分支
  （本文"可选"增强，已实施）。**用户真窗口五步流程亲眼验收未做**。
- **M10-3 🔶（收尾就差真人验收）**：已 push（2cfea45 → main + tag `v0.1.0`）；CI 首跑 win
  只炸 upload-artifact（坑 #60），d684e11 修复后重跑**双绿**（run 33474440346，artifacts
  win64 136MB / macOS 94MB）；剩 Windows 真机真人双击验收后 M10 翻 ✅。
- **M10-4 ✅ 裁决取消**：全量 293MB 远低于 ≤900MB 目标（预估 1.2–1.8GB 未发生），
  excludes 留空。
- **M10-5 ✅**：治理七文件同步完成（STATUS/HANDOFF 坑 #59/README/MANUAL §2.5/TODO/plan/
  review）；commit 等用户指令。
- 实施偏差与坑：SPECDIR→SPECPATH、mne lazy_loader→collect_submodules（四包）——详见
  HANDOFF 坑 #59 与 STATUS "M10 关键实证结论"。剩余待办清单见 TODO.md M10 节。


## 使用方式

- **开新 session**：粘贴一句——"请读 PACKAGING_HANDOFF.md，按其实施步骤执行 DataloadV 双平台打包"。
- **交给别人**：把本文件 + 仓库一起交（本文件在 repo 根目录）。

## 任务

把 DataloadV 打成**免环境配置**的双平台分发包：

- **macOS**：PyInstaller → `DataloadV.app`（本机 darwin 直接打）
- **Windows**：PyInstaller → `DataloadV.exe`（**经 GitHub Actions 自动打包**——repo 已有
  remote `git@github.com:JKlove/DATAloadV.git`，无 Windows 本机也能出包）

**验收标准**：目标机器无 Python/无 conda——macOS 双击 .app / Windows 双击 .exe 打开应用，
导入 `data/sheep` 羊数据 → 波形浏览 → 预览（带通+陷波）→ 特征计算 → 导出 CSV 与连续 EDF
全流程可用；日志/设置正常写 `~/.dataloadv/`。

## 项目事实卡（2026-09-01 实态，动手前先自行核对）

| 项 | 值 |
|---|---|
| 仓库路径 | 克隆到哪就是哪（本仓克隆路径**含空格**——一切命令加引号） |
| 布局 | src-layout：`src/dataloadv/`；hatchling + pyproject.toml |
| 入口 | console_script `dataloadv = "dataloadv.app:main"`；也有 `python -m dataloadv`（`src/dataloadv/__main__.py`） |
| 环境 | conda env **`dlv`**（Python 3.10）。**绝对不碰 `py310lg`**（pipelineMotor 冻结研究环境） |
| GUI 栈 | PySide6 6.11.0（conda-forge）/ pyqtgraph 0.14.0 / mne 1.12.0（pip）/ edfio 0.4.16（pip）/ neo 0.14.5（pip）/ pynwb 4.1.0（conda-forge）/ numpy 1.26.4 / scipy 1.15.2 / pandas 2.3.3 / h5py 3.16.0 / pydantic 2.13.4 / PyYAML |
| 可选依赖 | `extra-readers`（neo/pynwb）——**函数内延迟 import + import-guard**，缺失时应用照常运行、仅对应格式不可用（Blackrock/OE/Intan/NWB 四格式受影响；核心 16 格式不依赖） |
| 延迟 import 模块 | `src/dataloadv/io/neo_reader.py`、`src/dataloadv/io/nwb_reader.py`——PyInstaller 静态分析扫不到，**必须显式 hiddenimports**（见坑 ①） |
| 运行时写入 | `~/.dataloadv/`（settings.json / logs / workspaces / table_fs.json）——打包版行为一致，无需改代码 |
| 测试基线 | `QT_QPA_PLATFORM=offscreen pytest` → **287 passed**；`scripts/smoke_gui.py` → SMOKE OK；e2e_m1–m9·m81 共 143 项 |
| git 身份 | 仓库史实 **JKlove <huyingbing13@gmail.com>**；中文提交信息；**仅用户要求时 commit**；**不加 Co-Authored-By 尾注** |
| 版本 | pyproject `version = "0.1.0"`（打包产物命名用它） |

## 铁律约束（违反任何一条都算事故）

1. conda 优先装包（conda-forge）；conda-forge 没有的才 pip。PyInstaller conda-forge 有。
2. `data/`（4.9GB 真实数据）全程**只读**，绝不打进包。
3. `~/.claude/settings.json` 含敏感凭据，勿读勿外泄。
4. 临床 EEG 截图不得上传公开图床（本环境 Read PNG 走 CDN 上传链路）。
5. e2e / 无头 / 打包产物自动化一律 `QT_QPA_PLATFORM=offscreen`；**全量 pytest 期间勿并发
   e2e/smoke 等 QT 重活**（HANDOFF 坑 #57⑥）。
6. 代码中文注释/docstring 详尽；界面中文进 `ui/strings_zh.py`（禁止控件代码写死中文）；
   标识符英文。
7. 治理文件（STATUS/TODO/HANDOFF/review/plan/README/MANUAL）随进度实时更新；所有新坑
   （尤其 PyInstaller/mne/CI 相关）写进 HANDOFF 坑列表。
8. 长命令别接 `| tail` 管道；跑脚本用 `python -u`。
9. 所有命令前缀：`source ~/miniconda3/etc/profile.d/conda.sh && conda activate dlv`。

## 技术裁决（已评估，按此执行，不要另起炉灶）

- **路线 = PyInstaller 6.x**（方案 A）。不用 briefcase / py2app / constructor / conda-pack。
- **单份 spec 跨平台**：`dataloadv.spec` 一个文件，`sys.platform` 分支处理平台差异
  （darwin 出 .app bundle，win32 出 onedir .exe）。GitHub Actions 与本机跑同一份 spec。
- **产物形态 = onedir + zip**（不是 onefile：onefile 每次启动解包到临时目录，启动慢数秒，
  科学栈大体积下体验差；onedir 压 zip 分发）。命名
  `DataloadV-{version}-macOS-arm64.zip` / `DataloadV-{version}-win64.zip`。
  注意本机是 Apple Silicon（arm64）；若还要覆盖 Intel mac 需 Universal2 构建——**先不做**，
  确认需求再说。
- **不签名不公证**（out of scope）：没有 Apple 开发者账号（$99/年）。macOS 产物首次打开
  需"右键→打开"或 `xattr -cr DataloadV.app`——把这句话写进 README/发布说明。**不要**花
  时间研究代码签名。Windows Defender SmartScreen 对未签名 exe 同理（"更多信息→仍要运行"）。
- **不做 dmg 安装器 / Inno Setup**：zip 解压即用已满足验收，安装器二期再说。

## 已预判的坑（按序处理）

1. **neo/pynwb 延迟 import 扫不到** → spec 的 `hiddenimports` 至少含：
   `dataloadv.io.neo_reader`、`dataloadv.io.nwb_reader`、`neo`、`neo.rawio`、`pynwb`、
   `hdmf`。装包前先确认 dlv 里这俩在（已确认在：neo 0.14.5 / pynwb 4.1.0）。
2. **mne 自带数据文件**（channels/data 等模板）→ `collect_data('mne')`。**不要无脑
   `collect_all('mne')`**——会把 mne.tests 等垃圾打进去、体积暴涨几百 MB；先最小集
   （hiddenimports 按报错逐个补）。
3. **mne.viz/matplotlib 瘦身**：本项目不用 mne 画图——`excludes` 试排除 `matplotlib`、
   `tkinter`、`mne.viz`、`IPython`、`jupyter`。**策略：第一轮全量打（确保能跑），冒烟
   通过后再瘦身，每轮瘦身后必须重新冒烟**（mne 部分路径会惰性 import matplotlib，
   排除可能炸导入链——炸了就把该项移出 excludes）。
4. **macOS .app 的 offscreen 平台插件**：想对打包产物跑离屏自动化验证，须确认
   `libqoffscreen.dylib` 被收进（PyInstaller 默认收全部 platforms 插件，一般没问题；
   缺了就在 spec 里 binaries 补）。
5. **路径含空格**（"intervention BCI"）：shell 命令、spec 路径、CI 工作目录全部引号包牢。
6. **Apple Silicon PyInstaller**：conda-forge 的 pyinstaller 在 arm64 正常；若遇到
   object-dedup 相关崩溃，先升级 pyinstaller 到最新。

## 实施步骤（建议拆 M10-1…M10-5，逐项验收）

### M10-1 macOS 本机打包（半天~1 天）

1. `conda install -n dlv -c conda-forge pyinstaller`（确认 6.x）。
2. 写 `dataloadv.spec`（仓库根）：
   - 入口：**不要**直接 Analysis `app.py`（console_script 的 main 才是稳定入口）——写一个
     5 行 shim `packaging/entry.py`：`from dataloadv.app import main; raise SystemExit(main())`，
     spec 指向它，`console=False`，`name="DataloadV"`。
   - `hiddenimports`（坑 ①清单）+ `collect_data('mne')` + `excludes=[]`（第一轮全量）。
   - pydantic v2：确认其编译扩展被收进（一般 hook 自动；报错则 hiddenimports 补
     `pydantic.deprecated.*` 按提示）。
3. 打包：`python -m PyInstaller dataloadv.spec --noconfirm`（在 dlv、项目根下）。
4. 记录：解包后体积、构建耗时（进 STATUS）。

### M10-2 macOS 冒烟验证（必须亲眼过，不许只看退出码）

1. 真窗口：双击 `dist/DataloadV.app`（或 `open dist/DataloadV.app`）——导入
   `data/sheep/data(DGDJ-卧-接地-2)-HKY.edf` → 浏览 → 加 bandpass+notch 预览 → 计算特征
   → 导出 CSV + 连续 EDF（M9 新功能，重点验：edfio 在冻结环境里写盘正常）。
2. 无头自动化（补一层保险）：
   `QT_QPA_PLATFORM=offscreen dist/DataloadV.app/Contents/MacOS/Dataloadv` 拉起确认不崩
   （能起主窗口即算过；若做完整 e2e 需给 app 加 `--smoke` 自检分支——**可选**，加的话走
   `strings_zh.py` 规则、改动最小化：argparse 一个 flag，main 里 `--smoke` 时跑
   `scripts/smoke_gui.py` 的等价逻辑后退出）。
3. 顺手验证 Gatekeeper 提示语出现（未签名预期行为），记录首次打开操作步骤。

### M10-3 GitHub Actions 双平台出包（半天~1 天）

1. 写 `.github/workflows/build.yml`：
   - 两个 job：`build-macos`（macos-latest，arm64）+ `build-win`（windows-latest）。
   - **runner 上不用 conda**（慢）——`actions/setup-python@v5` Python 3.10 + `pip install -e .[extra-readers] pyinstaller`（mne/edfio/neo/pynwb pip 全有，与 dlv 等价性说明写进 HANDOFF）。
   - Windows 注意：`pip install pyqtgraph PySide6` 走 pip（runner 无 conda-forge Qt，pip 版
     PySide6 在 win 正常）；checkout 后 `python -m PyInstaller dataloadv.spec --noconfirm`。
   - 产物：`actions/upload-artifact@v4` 两个 zip（`zip -r` 在 mac / `Compress-Archive` 在 win）。
   - 触发：`workflow_dispatch`（手动）+ `push tag v*`（发版）。**先 push 前问用户**（外发动作）。
2. 本地验证 workflow 语法：`actionlint` 或至少 YAML 解析；首次跑通后下载 win artifact，
   找一台真 Windows 机器（或用户本人）双击冒烟——**CI 绿 ≠ Windows 能跑**，必须真人验收
   一次并记录。

### M10-4 瘦身（可选，冒烟全过后才做）

按坑 ③ excludes 逐项排、每排一项重新冒烟；目标：macOS 解包体积从全量（预计 1.2–1.8GB）
压到 ≤900MB 量级。压不动就保留全量——**体积优先级低于可用性**。

### M10-5 治理同步 + 汇报

- README：快速开始加"免安装包"小节（下载 zip→解压→右键打开/更多信息仍要运行）。
- MANUAL §2：打包版运行说明 + `~/.dataloadv/` 位置不变。
- STATUS：M10 节 + 总览表行 + 体积/耗时数字。
- HANDOFF：**全部 PyInstaller/CI 新坑入坑列表**；接手要点加 M10 条目。
- TODO/review/plan（若立 M10）各就位。commit **等用户指令**。

## 风险与回退

- mne 在 PyInstaller 下的动态导入不可穷举 → 冒烟流程覆盖 导入/浏览/预览/特征/双格式导出
  五环节就是护栏；哪个环节炸就针对补 hiddenimports/collect（社区案例多，逐个能解）。
- pynwb/hdmf 数据文件缺失 → `collect_data('pynwb')`（其命名空间 JSON 必须随包）。
- Windows 字体/中文显示：PySide6 自带字体渲染，界面中文（strings_zh）在 win 无需额外字体
  （Qt 自带）；若乱码再查 `QT_FONT_DPI`/系统区域设置。
- 全部失败的最后回退：conda constructor 打 .pkg/.exe 安装包（方案 B，治理文件里留过评估
  记录）——工作量另计 1~2 天。
