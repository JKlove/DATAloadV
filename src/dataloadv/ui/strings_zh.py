"""全部界面中文文案集中于此（用户要求界面中文、代码标识符英文）.

约定：
- ``S`` 类承载全局文案；新增界面文字一律先加到这里，禁止在控件代码里写死中文
- 后续里程碑的步骤参数标签（STEP_LABELS）、特征标签、事件码中文映射
  （event_maps）等也集中在本模块或其调用的模块，保证文案可统一维护
"""


class S:
    """全局界面文案常量（类属性访问：``S.APP_TITLE``）."""

    # 应用
    APP_TITLE = "DataloadV 电生理数据平台"

    # 菜单
    MENU_FILE = "文件"
    MENU_VIEW = "查看"
    MENU_PROCESS = "处理"
    MENU_HELP = "帮助"

    ACT_EXIT = "退出"
    ACT_ABOUT = "关于"
    ACT_IMPORT_FILES = "导入文件…"
    ACT_IMPORT_FOLDER = "导入文件夹…"
    ACT_EXPORT = "导出…"
    ACT_NEW_WORKSPACE = "新建工作区…"
    ACT_OPEN_WORKSPACE = "打开工作区…"

    # Dock / 面板标题
    DOCK_WORKSPACE = "工作区"
    DOCK_PIPELINE = "处理"
    DOCK_LOG = "日志"

    # 占位提示（M0 骨架；后续里程碑逐一替换为真实控件）
    PLACEHOLDER_WORKSPACE = "工作区（M1：数据导入与元数据浏览）"
    PLACEHOLDER_PIPELINE = "处理管线（M3：预处理步骤编排与预览）"
    PLACEHOLDER_TAB_WELCOME = "欢迎——使用 文件 菜单导入数据（M1 起可用）"

    # 通用按钮/状态
    BTN_CLOSE = "关闭"
    BTN_OK = "确定"
    BTN_CANCEL = "取消"
    STATUS_READY = "就绪"
    STATUS_VERSION_FMT = "版本 {version}"

    # 关于对话框
    ABOUT_TEXT = (
        "DataloadV 电生理数据平台\n\n"
        "电生理数据的读取、浏览、预处理与特征提取工作台。\n"
        "技术栈：Python / PySide6 / pyqtgraph / MNE\n\n"
        "开发计划与进度见项目目录下 plan.md / STATUS.md。"
    )

    # ===== M1：导入 / 工作区 / 元数据表 =====
    DLG_IMPORT_TITLE = "导入数据"
    DLG_IMPORT_FILES = "选择文件"
    DLG_IMPORT_FOLDER = "选择文件夹"
    IMPORT_SCANNING = "正在扫描：{name}"
    IMPORT_DONE_FMT = "导入完成：新增 {added} 条，重复 {dup} 条，失败 {errors} 条"
    IMPORT_ERR_COL_FILE = "文件"
    IMPORT_ERR_COL_MSG = "错误"
    IMPORT_ERR_TITLE = "部分文件导入失败（{n} 个）"
    BTN_SHOW_ERRORS = "查看失败详情"
    BTN_IMPORT_ANOTHER = "继续导入"

    COL_NAME = "名称"
    COL_SUBJECT = "被试"
    COL_FORMAT = "格式"
    COL_CHANNELS = "通道数"
    COL_SFREQ = "采样率 (Hz)"
    COL_DURATION = "时长 (s)"
    COL_EVENTS = "事件数"
    COL_SOURCE = "导入来源"
    COL_TASK = "任务"
    COL_RUN = "Run"

    TAB_META_TABLE = "元数据表"
    FILTER_HINT = "筛选（文件名/被试/格式…）"
    TREE_ROOT_FMT = "工作区：{name}（{n} 条）"
    STATUS_OPENING = "正在打开：{name}…"
    TREE_CTX_REMOVE = "从工作区移除"
    TREE_CTX_REMOVE_SOURCE = "移除该来源全部条目（{n} 条）"
    REMOVE_CONFIRM_TITLE = "移除确认"
    REMOVE_CONFIRM_TEXT_FMT = "将从工作区移除 {n} 条条目（仅清理工作区索引，不删除磁盘上的数据文件）。是否继续？"
    STATUS_REMOVED_FMT = "已从工作区移除 {n} 条"

    # ===== M1：信号浏览器 =====
    BROWSER_TITLE_FMT = "{name}"
    BROWSER_NO_DATA = "（无数据）"
    BTN_PREV_EVENT = "◀ 上一事件"
    BTN_NEXT_EVENT = "下一事件 ▶"
    BTN_JUMP = "跳转"
    LBL_TIME = "时间 (s)"
    LBL_GAIN = "纵向增益"
    LBL_CHANNELS = "通道"
    LBL_EVENT_LANE = "事件"
    EVENT_LANE_NONE = "无事件"
    UNIT_UV = "µV"
    TIME_FMT = "{t:.2f} s / {total:.1f} s"
    LOAD_FAILED_TITLE = "打开失败"

    # ===== M6：浏览器窗口导航 + 浅色主题配色 =====
    BTN_GO_FIRST = "|◀ 最前"
    BTN_PREV_PAGE = "◀ 上一屏"
    BTN_NEXT_PAGE = "下一屏 ▶"
    BTN_GO_LAST = "最末 ▶|"
    LBL_WINDOW_S = "一屏时长 (s)"
    WINDOW_PRESETS = ("1", "2", "5", "10", "30", "60")
    # 白底主题下的绘图配色（M6 全局换白，见 main_window 的 pg.setConfigOptions）
    SIGNAL_PEN_COLOR = "#1f77b4"   # 波形曲线：白底高对比深蓝（旧深底浅蓝 #7fbfff 弃用）
    PLOT_TEXT_COLOR = "#333333"    # 通道标签/事件图例等图内文字（旧 #cccccc 弃用）

    # ===== M6.8：DC 偏移开关 / 增益输入 / 总览滑块 / 秒级平移 =====
    BTN_PREV_S = "◀ 1s"           # 上一秒（补充翻屏 0.9 屏的细分辨率）
    BTN_NEXT_S = "1s ▶"           # 下一秒
    CB_ROW_CENTER = "行居中"       # DC 偏移开关：勾选=每通道减本窗口中位数对齐到行
    CB_ROW_CENTER_TIP = (
        "勾选：每通道减去本窗口中位数后对齐到自己的行（EEG 浏览器标准做法，\n"
        "直流耦合数据的大直流偏移不进画面）；\n"
        "不勾选：显示绝对电平（通道间真实电平差），y 轴按数据自动适配。"
    )
    GAIN_SUFFIX = "×"             # 增益输入框后缀（倍率）

    # ===== M7：信号质量体检（浏览器一键 + 特征提取器双入口）=====
    BTN_QC = "质量体检"            # 工具栏左组尾部按钮（计算期间禁用防重入）
    BTN_QC_TIP = (
        "逐通道体检：死值 / 平直 / 满量程饱和 / 开路复用 / 基线漂移，\n"
        "在通道列表标注 ✓ 好 / ? 疑似 / ✗ 坏，并把问题明细写进悬浮提示。"
    )
    QC_PREFIX_GOOD = "✓ "         # 通道列表前缀（good）
    QC_PREFIX_SUSPECT = "? "      # 疑似（suspect）
    QC_PREFIX_BAD = "✗ "          # 坏（bad）
    QC_QUALITY_GOOD = "好"
    QC_QUALITY_SUSPECT = "疑似"
    QC_QUALITY_BAD = "坏"
    QC_TIP_STATS = (
        "直流 {dc} µV | 标准差 {std} µV | 漂移 {drift} µV/min\n"
        "平直 {flat}% | 钉极值 {rail}%"
    )
    QC_SUGGEST_TITLE = "体检完成"
    QC_SUGGEST_TEXT = (
        "体检发现 {n} 个疑似坏通道：\n\n{lines}\n\n"
        "是否标记为坏道？（坏道曲线灰显，后续处理/特征默认排除）"
    )
    QC_ALL_GOOD = "体检完成：{n} 个通道全部合格，未发现疑似坏通道。"
    QC_NO_ISSUE = "未发现问题"     # 体检合格通道的 tooltip 明细行
    QC_FAIL_TEXT = "质量体检失败：\n{msg}"

    # ===== M8：分段预览三视图 + 时频 =====
    EP_VIEW_LABEL = "视图"          # 分段预览的视图模式下拉
    EP_VIEW_AVG = "各通道平均（堆叠）"       # M3 现状：垂直偏移堆叠
    EP_VIEW_BUTTERFLY = "ERP 蝶形图"        # 全通道同一坐标叠加
    EP_VIEW_SINGLE = "单通道 ERP"           # 逐段细线 + 按事件码分色平均
    EP_VIEW_TFR = "时频图（单通道）"         # morlet 段平均功率谱热图
    EP_LBL_CHANNEL = "通道"          # 单通道/时频视图的通道选择
    EP_TFR_COMPUTING = "时频计算中…（morlet，段平均）"
    EP_TFR_UNIT = "dB（基线校正）"    # 时频色标单位
    EP_TFR_FREQ_AXIS = "频率 (Hz)"
    EP_TFR_FAIL = "时频计算失败：{msg}"
    EP_LEGEND_SINGLE = "彩色粗线=按事件码平均；灰色细线=各分段"

    # ===== M8.1：时频配色 + 单段浏览 =====
    EP_LBL_CMAP = "配色"                    # 时频热图配色下拉（viridis/jet/hot 专有名词不翻）
    EP_VIEW_SEGMENT = "单段浏览（全通道）"     # 第五视图：第 N 段全通道堆叠
    EP_LBL_SEGMENT = "段号"
    EP_HINT_SEGMENT = "第 {i} / {n} 段 · 事件码 {code}（←/→ 翻段）"
    EP_BTN_SEG_PREV = "◀"
    EP_BTN_SEG_NEXT = "▶"

    # ===== M2：采样率询问（CSV/TXT/HDF5 内无采样率）=====
    ASK_FS_TITLE = "设定采样率"
    ASK_FS_TEXT = (
        "文件 {name} 内不含采样率信息，\n"
        "请输入该数据的采样率（Hz）。\n（记住一次，之后直接使用）"
    )

    # ===== M3：处理管线面板 =====
    PIPE_BTN_ADD = "添加步骤"
    PIPE_BTN_REMOVE = "删除"
    PIPE_BTN_UP = "上移"
    PIPE_BTN_DOWN = "下移"
    PIPE_BTN_CLEAR = "清空"
    PIPE_BTN_PREVIEW = "预览当前文件"
    PIPE_BTN_PSD = "对比 PSD"
    PIPE_LBL_STEPS = "处理步骤（自上而下执行）"
    PIPE_LBL_PARAMS = "步骤参数"
    PIPE_EMPTY_HINT = "先添加处理步骤，再点「预览当前文件」。\n预览在数据副本上进行，不影响原始数据。"
    PIPE_MSG_NO_STEPS = "尚未添加任何处理步骤"
    PIPE_MSG_NO_ACTIVE = "请先打开一个浏览 tab（预览作用于当前 tab 的数据）"
    PIPE_MSG_NOT_LOADED = "当前 tab 数据尚未加载完成，请稍候再试"
    PIPE_MSG_PARAMS_INVALID = "步骤参数不合法"
    PIPE_MSG_PREVIEW_RUNNING = "正在预览处理…"
    PIPE_MSG_PSD_RUNNING = "正在计算 PSD…"
    PIPE_MSG_PSD_NO_PREVIEW = "尚无预览结果——将只显示原始数据 PSD（先「预览当前文件」可对比）"
    PIPE_PREVIEW_TAB_FMT = "预览 · {name}"
    PIPE_PREVIEW_FAIL_TITLE = "预览失败"
    PIPE_PSD_TITLE = "功率谱对比（通道平均，Welch）"
    PIPE_PSD_LABEL_BEFORE = "原始"
    PIPE_PSD_LABEL_AFTER = "处理后"
    PIPE_PSD_AXIS_X = "频率 (Hz)"
    PIPE_PSD_AXIS_Y = "功率谱密度 (µV²/Hz)"
    PIPE_EPOCHS_TAB_FMT = "分段预览 · {name}"
    PIPE_EPOCHS_TOTAL = "分段总数：{n}"
    PIPE_EPOCHS_PER_CODE = "各类分段数"
    PIPE_EPOCHS_AVG_PLOT = "各通道分段平均波形（跨段平均，µV）"
    PIPE_EPOCHS_NO_PLOT = "（无分段可画）"

    # ===== M3：浏览器坏道标记 =====
    MENU_MARK_BAD = "标记为坏道"
    MENU_UNMARK_BAD = "取消坏道标记"
    BAD_PEN_COLOR = "#8a8a8a"  # 坏道曲线灰显色

    # ===== M4：特征提取 + 导出 =====
    FEAT_LBL_LIST = "特征提取（管线执行后逐个计算）"
    FEAT_BTN_ADD = "添加特征"
    FEAT_BTN_REMOVE = "删除"
    FEAT_BTN_VIEWPORT = "用当前显示窗口"
    FEAT_BTN_RUN = "计算特征"
    FEAT_EMPTY_HINT = "管线步骤（可选）执行完后，按此处的特征逐个计算。\n特征作用于处理后的数据：raw=全量摘要，epochs=逐段。"
    FEAT_MSG_NO_FEATURES = "尚未添加任何特征提取器"
    FEAT_MSG_NO_ACTIVE = "请先打开一个浏览 tab（特征作用于当前 tab 的数据）"
    FEAT_MSG_RUNNING = "正在计算特征…"
    FEAT_MSG_VIEWPORT_APPLIED = "已把当前显示窗口 [{t0:.1f}, {t1:.1f}] s 填入时间窗裁剪步骤（可再修改）"
    FEAT_MSG_VIEWPORT_NO_DATA = "当前 tab 数据尚未加载完成，无法读取显示窗口"
    FEAT_TAB_FMT = "特征 · {name}"
    FEAT_EXPORT_CSV = "导出 CSV"
    FEAT_EXPORT_H5 = "导出 HDF5"
    FEAT_EXPORT_EPOCHS = "导出分段…"
    FEAT_EXPORT_DONE_TITLE = "导出完成"
    FEAT_EXPORT_DONE_FMT = "已写出 {n} 个文件：\n{files}"
    FEAT_EXPORT_FAIL_TITLE = "导出失败"
    FEAT_TABLE_EMPTY = "（无特征结果）"
    FEAT_EPOCHS_FMT_HINT = "分段数据：{fmt}"
    FEAT_EXPORT_EPOCHS_H5 = "HDF5（跨工具）"
    FEAT_EXPORT_EPOCHS_FIF = "FIF（mne 无损）"
    # M8.3：特征结果图表区（PSD 曲线 tab + 柱状图 tab）
    FEAT_TAB_PSD = "PSD 曲线"
    FEAT_TAB_BARS = "特征柱状图"
    FEAT_CHART_CURVE_TRUNC = "曲线共 {total} 条，仅显示前 {n} 条（可收窄通道/时间窗后重算）"
    FEAT_CHART_EP_AGG = "分段数据已按事件码求均值聚合（每类事件一条系列）"
    FEAT_CHART_SERIES_TRUNC = "系列共 {total} 条，仅显示前 {n} 条"
    FEAT_CHART_FEATURE_TRUNC = "特征共 {total} 项，仅显示前 {n} 项（可在参数里收窄频段/统计量）"


    # ===== M5：批处理 =====
    BATCH_MENU_ACT = "批处理…"
    BATCH_DLG_TITLE = "批处理"
    BATCH_LBL_FILES = "文件（勾选要处理的；来自当前工作区）"
    BATCH_LBL_FILTER = "过滤（文件名/被试）"
    BATCH_BTN_ALL = "全选"
    BATCH_BTN_NONE = "全不选"
    BATCH_LBL_SELECTED_FMT = "已选 {n} / {total} 个文件"
    BATCH_LBL_PIPELINE = "管线（取自右侧管线面板当前步骤+特征链）"
    BATCH_LBL_EXPORT = "完成后导出"
    BATCH_CB_CSV = "CSV（Excel 可开）"
    BATCH_CB_H5 = "HDF5"
    BATCH_LBL_NAME = "导出名"
    BATCH_LBL_DIR = "导出目录"
    BATCH_BTN_BROWSE = "浏览…"
    BATCH_LBL_WORKERS = "并发线程"
    BATCH_BTN_RUN = "开始批处理"
    BATCH_MSG_NO_FILES = "请先勾选至少一个文件"
    BATCH_MSG_NO_FEATURES = "特征链为空——批处理至少需要一个特征提取器（在右侧管线面板「添加特征」）"
    BATCH_MSG_NO_EXPORT_DIR = "已勾选导出但未选择目录"
    BATCH_MSG_BAD_PIPELINE = "管线描述不合法"
    BATCH_MSG_RUNNING = "批处理进行中：{done} / {total}"
    BATCH_MSG_CANCELLING = "正在取消（当前步骤结束后停止）…"
    BATCH_BTN_CANCEL_RUN = "取消批处理"
    BATCH_COL_FILE = "文件"
    BATCH_COL_STATUS = "状态"
    BATCH_COL_TIME = "耗时"
    BATCH_COL_VALUES = "特征值"
    BATCH_ST_WAIT = "等待中"
    BATCH_ST_RUNNING = "处理中"
    BATCH_STATUS_ZH = {"ok": "成功", "failed": "失败", "cancelled": "已取消", "skipped": "跳过"}
    BATCH_LOG_TITLE_FMT = "处理日志 · {name}"
    BATCH_DONE_TITLE = "批处理完成"
    BATCH_ERR_VIEW_HINT = "双击行查看日志"

    # ===== M5：设置 =====
    SETTINGS_ACT = "设置…"
    SETTINGS_TITLE = "设置"
    SETTINGS_LBL_WORKERS = "批处理默认并发线程"
    SETTINGS_LBL_CACHE = "数据缓存预算 (GB)"
    SETTINGS_LBL_EXPORT_DIR = "默认导出目录"
    SETTINGS_BTN_BROWSE = "浏览…"
    SETTINGS_MSG_SAVED = "设置已保存"
    BATCH_TAB_FMT = "批处理 · {name}"
