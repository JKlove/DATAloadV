# DataloadV 打包与发版手册（runbook）

> **定位**：打包/发版的**流程权威**——怎么打包、怎么发版、出了问题去哪查。
> 机制与环境（依赖版本、构建命令、与 dlv 等价性）权威是 HANDOFF.md「打包」节；
> 版本历史看 STATUS.md 变更记录；本文不重复它们的内容。
> 初版为 2026-09-01 M10 打包任务交接书（任务已完成），2026-10-26 重构为常态手册。

## 文件地图（谁负责什么）

| 文件 | 角色 |
|---|---|
| `dataloadv.spec` | 唯一打包定义，跨平台单份（darwin 出 .app / win32 出 onedir .exe），本机与 CI 共用 |
| `packaging/entry.py` | 打包入口 shim：console_script 等价物 + UTF-8 自举**前置**调用（坑 #65/#66） |
| `src/dataloadv/_utf8.py` | 中文 Windows GBK 自救：运行时包装 `builtins.open` 补 UTF-8 默认编码（冻结环境不吃 PYTHONUTF8，坑 #65；非 Windows no-op） |
| `.github/workflows/build.yml` | CI 双平台出包：测试门禁 → PyInstaller → 压 zip → artifacts（workflow_dispatch / push tag v* 触发） |
| `app.py` 的 `--smoke` | 打包产物无头自检：起主窗口自检后自动退出，末行 `SMOKE OK` |

## 发版流程（按序执行；命令细节见 HANDOFF「打包」节）

前提：dlv 环境、项目根、工作树干净。

1. **改版本号（两处）**：`pyproject.toml` 的 `version` + `src/dataloadv/__init__.py` 的
   `__version__`。修复发 patch（0.2.2→0.2.3），功能增量发 minor（0.1.1→0.2.0）。
2. **全量测试**：`QT_QPA_PLATFORM=offscreen python -m pytest`（基线绿数见 STATUS 头注）。
3. **本机重打包 + 冒烟**：`python -m PyInstaller dataloadv.spec --noconfirm` →
   `QT_QPA_PLATFORM=offscreen dist/DataloadV.app/Contents/MacOS/DataloadV --smoke`。
   只要动了打包相关代码（spec / entry / _utf8 / 依赖变化）**必须**做这步，别只信 CI。
4. **本机隐私清理**（分发或换机前）：`~/.dataloadv` 各工作区索引剔除私有条目——
   判定规则=来源**路径段**含 `clinicaldata` 或**以 `sheep` 开头**（泛化匹配，
   覆盖未来 sheepN；e2e 重跑会重新引入，每次发版重查）；走 Workspace API
   `remove_source()` 只清索引不删磁盘文件；指针复位「默认工作区」；分发 zip
   列表 `grep -iE "sheep|clinical|DGDJ|TPDJ|01号|02号|Animal Exp"` 零命中核查。
   工作区从不进包——此步管的是**本机默认加载**的隐私面。
5. **治理同步 + commit/push**：STATUS 变更记录加发版条（版本/内容/验证数字）；
   中文提交信息，身份 JKlove。
6. **打 tag 触发 CI**：`git tag v<版本> && git push origin v<版本>` → Actions 双平台
   （测试门禁不过不会出包）。
7. **下载 + 验收**：Actions 页（登录态）下载 `DataloadV-<版本>-win64.zip` /
   `-macOS-arm64.zip`。**CI 绿 ≠ Windows 能跑**——涉及 Windows 行为的改动
   （入口/编码/路径/DPI）须真人双击验收一次才算闭环（前车之鉴：#65/#66）。

## 已裁决事项（不要重新论证）

- **PyInstaller 6.x 单份 spec 跨平台**；不用 briefcase / py2app / constructor / conda-pack。
- **onedir + zip 分发**（非 onefile：onefile 每次启动解包到临时目录，科学栈体积下
  慢数秒）。产物名 `DataloadV-{版本}-macOS-arm64.zip` / `-win64.zip`。
- **不签名不公证**（无 Apple 开发者账号）。首开：mac 右键→打开（或
  `xattr -cr DataloadV.app`）；Windows SmartScreen 更多信息→仍要运行（README/MANUAL 已写）。
- **不做 dmg / Inno Setup 安装器**（zip 解压即用满足需求，二期再议）。
- **瘦身取消**（M10-4 裁决）：全量 293MB ≪ ≤900MB 目标，`excludes` 永久留空。
- **CI 不用 conda**：setup-python 3.10 + pip（含 dev 测试件）；与 dlv conda 环境的
  等价性论证见 HANDOFF「打包」节。
- Intel mac（Universal2 构建）未做——有真实需求再议。

## 打包相关坑索引（详情在 HANDOFF 坑列表，这里只给钥匙）

| 坑 | 一句话 |
|---|---|
| #59 | PyInstaller 七则：spec 全局是 SPECPATH；mne lazy_loader→collect_submodules 四包；collect_data 最小集别用 collect_all；warn 文件 missing 多为 lazy_loader 噪音 |
| #60 | CI 产物写出路径与 upload path 逐字对账（Compress-Archive 相对路径落 CWD=仓库根） |
| #61 | 初始窗口尺寸按屏收口 + 首显示 resizeDocks（小屏/高 DPI 首布局截断） |
| #65 | 中文 Windows GBK 读 UTF-8 资源必炸 → `builtins.open` 运行时补丁（`_utf8.py`；冻结环境不吃 PYTHONUTF8，重启路线已废） |
| #66 | （历史）execv 参数 argv[0] 不重复拼；windowed 模式 `sys.stderr is None` 要垫（entry/app，垫 stderr 仍在用） |

## 红线（打包场景违反即事故）

1. `data/`（4.9GB 真实数据）只读，绝不进包（spec 的 datas 只来自 site-packages）。
2. 分发/换机前完成发版流程第 4 步隐私清理；临床 EEG 截图不得上传公开图床。
3. 无头 / 打包产物自动化一律 `QT_QPA_PLATFORM=offscreen`。
4. macOS 上 no-op 的平台分支（如 `_utf8` 的 Windows 补丁路径），改动时必须做
   **行为级断言**（真机行为本地拦不住）；依赖解释器启动配置的策略（环境变量/
   启动参数）在冻结环境一律实测——bootloader 不保证标准 CPython 行为
   （坑 #65/#66 两轮教训）。
5. 项目通用约束（conda 优先、中文注释、治理实时同步、命令习惯）见
   HANDOFF「代码风格约定」「当前接手要点」。

## 出问题怎么排查

- **产物起不来/行为异常**：先 `QT_QPA_PLATFORM=offscreen <二进制> --smoke`，
  拿退出码 + 日志 `~/.dataloadv/logs/dataloadv.log`。
- **Windows 崩溃对话框**：照片/截图里的 traceback 逐帧对源码行号
  （历史两例 #65/#66 均此法定位）。
- **冻结环境缺模块**：先看 `build/DataloadV/warn-DataloadV.txt`——lazy_loader 类
  missing 多为噪音（#59④），真缺才补 hiddenimports/collect，补完必须重新冒烟。
- **CI 失败**：先看失败的是哪一步——`/actions/runs/{id}/jobs` API 免凭据可查
  步骤级结论（日志下载才需要 token）。
- **最后回退路线**：conda constructor 打安装包（方案 B，评估记录在治理文件）。
