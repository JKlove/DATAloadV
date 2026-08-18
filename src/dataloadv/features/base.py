"""特征提取器抽象基类 + 注册表——与 proc/base.py 同构（M4）.

设计（刻意与 proc 层同一套约定：学会一层即可维护两层）：
- 每个提取器 = ``pydantic 参数模型`` + ``extract(ctx, params) -> ExtractorResult``
- 参数模型字段用 ``Field(title="中文名")`` → ``ui/widgets/params_form.py`` 自动
  生成参数表单（表单只依赖 ``params_cls``/``make_params``/``step_id`` 三个名字，
  提取器全都提供），新增提取器**零 UI 代码**
- ``applies_to`` 声明适用阶段：``raw`` = 处理上下文全量（文件级摘要，批处理
  基线）；``epochs`` = 逐段（每段每通道各一行——BCI 事件锁时分析）
- 序列化（feature_to_dict/from_dict）与 proc 步骤同一套 dict 约定 → 导出
  sidecar（provenance）直接收录

产出（``ExtractorResult``）分两类：
- **标量行**（scalars）：进 FeatureTable 长表。字段约定：
  ``epoch_index``（raw 阶段为 None）/ ``event_code``（同前）/ ``channel`` /
  ``feature``（短名，如 ``bp_alpha``；跨提取器不重名由命名前缀保证）/
  ``value``（float）。recording/subject 等文件级字段由 FeatureTable.add_result
  统一补——提取器不感知文件身份，保持纯粹
- **曲线行**（curves）：仅 PSD 类提取器（raw 阶段）。``channel`` /
  ``freqs`` / ``psd``（µV²/Hz）。量随段数爆炸，epochs 阶段不支持曲线——
  段级频谱需求用 BandPower 标量表达

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, Optional

import numpy as np
from pydantic import BaseModel

if TYPE_CHECKING:  # 仅类型标注，避免运行时循环 import
    from ..proc.context import ProcessingContext


class FeatureError(Exception):
    """特征计算失败（参数非法/阶段不符/数据不满足前提等）.

    ``message`` 面向用户：中文、说清缺什么/该怎么修（与 StepError 同约定）。
    """


@dataclass
class ExtractorResult:
    """一次 extract 的产出（标量行 + 曲线行，见模块 docstring 的字段约定）."""

    scalars: list[dict] = field(default_factory=list)
    curves: list[dict] = field(default_factory=list)

    def __bool__(self) -> bool:
        """空结果判 False（"什么都没提取到"的统一判据）."""
        return bool(self.scalars or self.curves)


class FeatureExtractor(ABC):
    """一个特征提取器.

    类属性（与 ProcStep 同名同义，便于统一表单/序列化）：
    - ``feature_id``：注册键（序列化用，稳定不改名）
    - ``label_zh``：UI 显示名（如"频带功率"）
    - ``params_cls``：参数 pydantic 模型
    - ``applies_to``：适用阶段集合，{"raw"} / {"epochs"} / {"raw","epochs"}
    """

    feature_id: ClassVar[str] = ""
    label_zh: ClassVar[str] = ""
    params_cls: ClassVar[type[BaseModel]] = BaseModel
    applies_to: ClassVar[frozenset[str]] = frozenset({"raw", "epochs"})

    @property
    def step_id(self) -> str:
        """``feature_id`` 的别名——``ParamsForm`` 对 proc/feature 两层零改动复用."""
        return self.feature_id

    @abstractmethod
    def extract(self, ctx: "ProcessingContext", params: BaseModel) -> ExtractorResult:
        """在 ``ctx`` 上计算特征.

        :raises FeatureError: 任何失败（中文信息）；ctx 不被修改（特征是只读操作）
        """

    # ------------------------------------------------------------------ 序列化

    def default_params(self) -> BaseModel:
        """参数默认值实例（UI 添加特征时初始化表单用）."""
        return self.params_cls()

    def make_params(self, data: dict) -> BaseModel:
        """从 dict 构造参数（反序列化/批处理配置用），校验失败转 FeatureError."""
        try:
            return self.params_cls(**data)
        except Exception as e:  # noqa: BLE001 - pydantic 校验错误统一转中文
            raise FeatureError(f"特征「{self.label_zh}」参数不合法：{e}") from e


# 注册表：feature_id -> 实例（提取器无状态，进程内单例足够）
FEATURE_REGISTRY: dict[str, FeatureExtractor] = {}


def register_feature(cls: type[FeatureExtractor]) -> type[FeatureExtractor]:
    """类装饰器：实例化并注册（``features/__init__.py`` import 各模块即完成注册）."""
    fx = cls()
    if not cls.feature_id:
        raise ValueError(f"{cls.__name__} 缺少 feature_id")
    if cls.feature_id in FEATURE_REGISTRY:
        raise ValueError(f"特征提取器重复注册：{cls.feature_id}")
    FEATURE_REGISTRY[cls.feature_id] = fx
    return cls


def feature_to_dict(feature_id: str, params: BaseModel) -> dict:
    """特征条目 → 可 JSON 序列化 dict（sidecar 的原子单元，与 step_to_dict 同构）."""
    return {"feature": feature_id, "params": params.model_dump()}


def feature_from_dict(d: dict) -> tuple[str, BaseModel]:
    """dict → (feature_id, params)；未知特征/参数非法给中文错误."""
    feature_id = d.get("feature", "")
    fx = FEATURE_REGISTRY.get(feature_id)
    if fx is None:
        known = "、".join(sorted(FEATURE_REGISTRY)) or "（无）"
        raise FeatureError(f"未知特征提取器「{feature_id}」。可用特征：{known}")
    return feature_id, fx.make_params(d.get("params", {}))


def apply_features(
    ctx: "ProcessingContext", features: list[tuple[str, BaseModel]]
) -> ExtractorResult:
    """按序执行全部特征提取器，合并产出（管线执行完毕后调用）.

    :param features: [(feature_id, params), ...]——UI 面板 / 批处理引擎共用入口
    :raises FeatureError: 首个失败即终止（中文信息）
    """
    out = ExtractorResult()
    for i, (feature_id, params) in enumerate(features, 1):
        fx = FEATURE_REGISTRY.get(feature_id)
        if fx is None:
            raise FeatureError(f"未知特征提取器「{feature_id}」")
        if ctx.stage not in fx.applies_to:
            want = "连续数据（raw）" if "raw" in fx.applies_to else "分段数据（epochs）"
            raise FeatureError(
                f"第 {i} 个特征「{fx.label_zh}」只支持{want}，当前是"
                f"{'分段' if ctx.stage == 'epochs' else '连续'}阶段"
                f"——请调整管线（分段前后）或删掉该特征"
            )
        t0 = time.perf_counter()
        try:
            r = fx.extract(ctx, params)
        except FeatureError:
            raise  # 提取器自己抛的中文错误原样上抛
        except Exception as e:  # noqa: BLE001 - numpy/mne 底层异常包装成中文
            raise FeatureError(f"第 {i} 个特征「{fx.label_zh}」计算失败：{e}") from e
        out.scalars.extend(r.scalars)
        out.curves.extend(r.curves)
        dt = (time.perf_counter() - t0) * 1000
        ctx.log(f"特征 {fx.label_zh}：{len(r.scalars)} 个标量值、{len(r.curves)} 条曲线，{dt:.0f} ms")
    return out


# ---------------------------------------------------------------------- 通道选择

# 视为"数据通道"的类型白名单：特征计算只针对脑电类信号；misc（BCI 2a 的
# 眼电/手套等辅助通道）、stim、eog 等不进特征表——批处理对比才有可比性
DATA_CH_TYPES = frozenset({"eeg", "ecog", "seeg", "meg", "dbs"})


def pick_channels(ctx: "ProcessingContext", names: Optional[list[str]] = None) -> list[str]:
    """解析特征通道参数：空=全部数据通道（排除已标记坏道）；否则校验存在性.

    白名单过滤后为空时回退为"全部非 misc 通道"——兼容通道类型标注不规范的
    数据集（不静默产出空结果，也不让整条管线失败）。
    :raises FeatureError: 显式指定的通道名不存在（中文提示可用通道）
    """
    obj = ctx.raw if ctx.stage == "raw" else ctx.epochs
    ch_names = list(obj.info["ch_names"])
    ch_types = obj.get_channel_types()
    bads = set(obj.info.get("bads", []))
    if names:
        missing = [c for c in names if c not in ch_names]
        if missing:
            raise FeatureError(
                f"通道 {missing} 不存在。可用通道：{'、'.join(ch_names[:12])}…"
            )
        return list(names)
    picked = [c for c, t in zip(ch_names, ch_types) if t in DATA_CH_TYPES and c not in bads]
    if not picked:  # 类型标注不规范 → 回退全部非 misc（保证有产出）
        picked = [c for c, t in zip(ch_names, ch_types) if t != "misc" and c not in bads]
    if not picked:
        raise FeatureError("没有可用数据通道（全部被标记为坏道或均为辅助通道）")
    return picked


def picks_indices(ctx: "ProcessingContext", names: list[str]) -> list[int]:
    """通道名 → mne picks 索引（pick_channels 之后的第二步）."""
    ch_names = ctx.ch_names
    return [ch_names.index(c) for c in names]
