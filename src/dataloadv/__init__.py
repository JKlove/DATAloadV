"""DataloadV 电生理数据平台.

顶层包。子模块分层（详见项目 HANDOFF.md 架构导览）：
- core/    计算层核心：Recording 数据模型、工作区（禁止 import Qt）
- io/      数据读取器层：每格式一个 Reader，注册表模式（禁止 import Qt）
- proc/    预处理步骤（禁止 import Qt）
- features/ 特征提取器（禁止 import Qt）
- batch/   批处理引擎（禁止 import Qt）
- export/  结果导出与溯源（禁止 import Qt）
- workers/ Qt 后台任务基础设施
- ui/      全部 Qt 界面代码（唯一允许 import PySide6/pyqtgraph 的地方）
"""

__version__ = "0.1.1"
