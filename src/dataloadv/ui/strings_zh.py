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

    # ===== M2：采样率询问（CSV/TXT/HDF5 内无采样率）=====
    ASK_FS_TITLE = "设定采样率"
    ASK_FS_TEXT = (
        "文件 {name} 内不含采样率信息，\n"
        "请输入该数据的采样率（Hz）。\n（记住一次，之后直接使用）"
    )
