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
