"""预处理步骤抽象基类 + 注册表 + 序列化——M3 预处理链的地基.

设计（plan.md §4）：

- 每个处理步骤 = ``pydantic 参数模型`` + ``apply(ctx) -> ctx``，注册进 ``STEP_REGISTRY``
- 参数模型字段用 ``Field(title="中文名")``——``ui/widgets/params_form.py`` 据此自动生成
  参数表单，新增步骤**零 UI 代码**
- ``applies_to`` 声明步骤适用的阶段（raw 连续 / epochs 分段）；epoching 步骤把
  stage 从 raw 翻转为 epochs
- 序列化（to_dict/from_dict）让 预览 / 批处理 / 导出 sidecar 共用同一份可复现
  的管线描述（M5 的 PipelineSpec 直接吃这里的 dict 列表）

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel

if TYPE_CHECKING:  # 仅类型标注，避免运行时循环 import
    from .context import ProcessingContext


class StepError(Exception):
    """步骤执行失败（参数非法/数据不满足前提等）.

    ``message`` 面向用户：中文、说清缺什么/该怎么修（与 io 层 ScanError 同约定）。
    """


class PipelineCancelled(StepError):
    """管线被外部取消（批处理引擎的 threading.Event 经 ``cancel_check`` 传入）.

    继承 StepError：调用方已有的错误处理路径自然兼容；引擎额外识别本类型，
    把文件结局记为 cancelled 而非 failed。
    """


class ProcStep(ABC):
    """一个预处理步骤.

    类属性：
    - ``step_id``：注册键（序列化用，稳定不改名）
    - ``label_zh``：UI 显示名（如"带通滤波"）
    - ``params_cls``：参数 pydantic 模型
    - ``applies_to``：适用阶段集合，{"raw"} / {"epochs"} / {"raw","epochs"}
    """

    step_id: ClassVar[str] = ""
    label_zh: ClassVar[str] = ""
    params_cls: ClassVar[type[BaseModel]] = BaseModel
    applies_to: ClassVar[frozenset[str]] = frozenset({"raw"})

    @abstractmethod
    def apply(self, ctx: "ProcessingContext", params: BaseModel) -> "ProcessingContext":
        """在 ``ctx`` 上执行本步骤（就地修改并返回同一 ctx 便于链式）.

        :raises StepError: 任何失败（中文信息）；ctx 保持可继续使用
        """

    # ------------------------------------------------------------------ 序列化

    def default_params(self) -> BaseModel:
        """参数默认值实例（UI 添加步骤时初始化表单用）."""
        return self.params_cls()

    def make_params(self, data: dict) -> BaseModel:
        """从 dict 构造参数（反序列化/批处理配置用），校验失败转 StepError."""
        try:
            return self.params_cls(**data)
        except Exception as e:  # noqa: BLE001 - pydantic 校验错误统一转中文步骤错误
            raise StepError(f"步骤「{self.label_zh}」参数不合法：{e}") from e


# 注册表：step_id -> 实例（步骤无状态，进程内单例足够）
STEP_REGISTRY: dict[str, ProcStep] = {}


def register_step(cls: type[ProcStep]) -> type[ProcStep]:
    """类装饰器：实例化并注册（``proc/__init__.py`` import 各步骤模块即完成注册）."""
    step = cls()
    if not cls.step_id:
        raise ValueError(f"{cls.__name__} 缺少 step_id")
    if cls.step_id in STEP_REGISTRY:
        raise ValueError(f"步骤重复注册：{cls.step_id}")
    STEP_REGISTRY[cls.step_id] = step
    return cls


def step_to_dict(step_id: str, params: BaseModel) -> dict:
    """步骤实例 → 可 JSON 序列化 dict（管线持久化/导出 sidecar 的原子单元）."""
    return {"step": step_id, "params": params.model_dump()}


def step_from_dict(d: dict) -> tuple[str, BaseModel]:
    """dict → (step_id, params)；未知步骤/参数非法给中文错误."""
    step_id = d.get("step", "")
    step = STEP_REGISTRY.get(step_id)
    if step is None:
        known = "、".join(sorted(STEP_REGISTRY)) or "（无）"
        raise StepError(f"未知处理步骤「{step_id}」。可用步骤：{known}")
    return step_id, step.make_params(d.get("params", {}))


def params_summary(params: BaseModel, max_len: int = 60) -> str:
    """参数摘要（UI 步骤列表一行内展示），超长截断."""
    parts = [f"{k}={v}" for k, v in params.model_dump().items() if v not in (None, [], ())]
    s = "，".join(parts) if parts else "默认参数"
    return s if len(s) <= max_len else s[: max_len - 1] + "…"


def apply_pipeline(
    ctx: "ProcessingContext",
    steps: list[tuple[str, BaseModel]],
    cancel_check=None,
) -> "ProcessingContext":
    """按序执行整条管线，逐步记录 history 与中文日志.

    :param steps: [(step_id, params), ...]——UI 面板 / 批处理引擎共用入口
    :param cancel_check: 可选取消探针 ``() -> bool``（批处理引擎传
        threading.Event.is_set）；每步**之前**检查，为真抛 PipelineCancelled
    :raises StepError: 首个失败步骤即终止（ctx 中 history 已含此前成功步骤）
    :raises PipelineCancelled: cancel_check 为真（StepError 子类）
    """
    for i, (step_id, params) in enumerate(steps, 1):
        if cancel_check is not None and cancel_check():
            raise PipelineCancelled("批处理已取消")
        step = STEP_REGISTRY.get(step_id)
        if step is None:
            raise StepError(f"未知处理步骤「{step_id}」")
        # 阶段检查放在 apply 之前：给用户明确的"顺序不对"提示而非底层异常
        if ctx.stage not in step.applies_to:
            want = "连续数据（raw）" if "raw" in step.applies_to else "分段数据（epochs）"
            raise StepError(
                f"第 {i} 步「{step.label_zh}」需要{want}，当前已是"
                f"{'分段' if ctx.stage == 'epochs' else '连续'}阶段——请调整步骤顺序"
            )
        t0 = time.perf_counter()
        try:
            step.apply(ctx, params)
        except StepError:
            raise  # 步骤自己抛的中文错误原样上抛
        except Exception as e:  # noqa: BLE001 - mne/底层异常包装成中文可操作信息
            raise StepError(f"第 {i} 步「{step.label_zh}」执行失败：{e}") from e
        dt = (time.perf_counter() - t0) * 1000
        ctx.history.append(step_to_dict(step_id, params))
        ctx.log(f"第 {i} 步 {step.label_zh}（{params_summary(params)}）完成，{dt:.0f} ms")
    return ctx
