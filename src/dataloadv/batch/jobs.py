"""批处理任务模型（pydantic）——一次批处理的完整可复现描述.

设计（plan.md §4"批处理引擎"）：
- ``PipelineSpec``：步骤链 + 特征链的**可序列化** dict 描述——与
  ``pipeline_panel.pipeline_dicts()`` / ``feature_dicts()`` 产物同构，
  即"UI 面板上组好的链"零转换直接进批处理；``resolved_*()`` 再把 dict
  还原成 (id, params 模型) 供引擎执行（未知步骤/参数非法在启动前就报中文错）
- ``JobSpec``：文件清单 + 线程数 + 导出开关——整份可 JSON 持久化，
  复现一次批处理只需要它
- ``FileResult`` / ``BatchSummary``：逐文件与整批的结果记录（状态、耗时、
  行数、**逐文件日志**——错误可查的验收标准就靠它）

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

from ..features.base import feature_from_dict
from ..proc.base import step_from_dict


class PipelineSpec(BaseModel):
    """步骤链 + 特征链（dict 列表，与导出 sidecar 的原子单元同构）.

    字段：
    - ``steps``：[{"step": id, "params": {...}}, ...]（``proc.step_to_dict`` 产物）
    - ``features``：[{"feature": id, "params": {...}}, ...]（``feature_to_dict`` 产物）
    """

    steps: list[dict] = Field(default_factory=list)
    features: list[dict] = Field(default_factory=list)

    # ------------------------------------------------------------------ 还原

    def resolved_steps(self) -> list[tuple[str, BaseModel]]:
        """dict → [(step_id, params 模型)]（引擎执行用）.

        :raises StepError: 未知步骤 / 参数非法（中文信息——启动批处理前即可发现）
        """
        return [step_from_dict(d) for d in self.steps]

    def resolved_features(self) -> list[tuple[str, BaseModel]]:
        """dict → [(feature_id, params 模型)]；错误约定同上."""
        return [feature_from_dict(d) for d in self.features]

    # ------------------------------------------------------------------ 展示

    def summary_zh(self) -> str:
        """一行中文摘要（对话框里显示"这次批处理要做什么"）."""
        from ..features.base import FEATURE_REGISTRY
        from ..proc.base import STEP_REGISTRY

        parts: list[str] = []
        if self.steps:
            names = []
            for d in self.steps:
                step = STEP_REGISTRY.get(d.get("step", ""))
                names.append(step.label_zh if step else d.get("step", "?"))
            parts.append("步骤：" + "→".join(names))
        else:
            parts.append("步骤：无（原始数据直接提特征）")
        if self.features:
            names = []
            for d in self.features:
                fx = FEATURE_REGISTRY.get(d.get("feature", ""))
                names.append(fx.label_zh if fx else d.get("feature", "?"))
            parts.append("特征：" + "、".join(names))
        else:
            parts.append("特征：无")
        return "；".join(parts)


class JobSpec(BaseModel):
    """一次批处理作业的完整输入.

    字段：
    - ``name``：作业名（导出文件主名 / UI 展示）
    - ``paths``：数据文件绝对路径清单（顺序即处理顺序）
    - ``pipeline``：管线 + 特征链（见 PipelineSpec）
    - ``n_workers``：并发线程数（默认 2——瓶颈是内存带宽而非 GIL，
      plan.md §4；上限 8 防误配）
    - ``export_csv`` / ``export_hdf5``：完成后是否导出特征表
    - ``export_raw_edf`` / ``export_raw_fif``：M9——逐文件把处理后的连续
      raw 落盘（每文件一个 ``<文件名>_proc.edf/_raw.fif`` + 各自 sidecar；
      管线含 epoching 的文件自动跳过并在日志注明）
    - ``export_dir``：导出目录；空串 = 不写文件（结果只在 FeatureTable，
      用户可事后在特征结果 tab 里手动导出）
    """

    name: str = "批处理"
    paths: list[str]
    pipeline: PipelineSpec
    n_workers: int = Field(default=2, ge=1, le=8)
    export_csv: bool = False
    export_hdf5: bool = False
    export_raw_edf: bool = False
    export_raw_fif: bool = False
    export_dir: str = ""

    def wants_export(self) -> bool:
        """是否需要在批处理结束后写文件（特征表与连续数据任一勾选即算）."""
        return bool(self.export_dir) and (
            self.export_csv or self.export_hdf5
            or self.export_raw_edf or self.export_raw_fif)


class FileStatus(str, Enum):
    """单文件的处理结局.

    - ``ok``：管线+特征全部完成（哪怕特征为空——空结果是数据本身没有
      可提的东西，不是错误）
    - ``failed``：读取/管线/特征任一环节失败（error 里有中文原因）
    - ``cancelled``：取消时尚未开始或进行中被放弃
    - ``skipped``：保留状态（v1 未用——如未来按条件过滤文件）
    """

    OK = "ok"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class FileResult(BaseModel):
    """单文件的处理结果（含逐文件日志——"错误可查"的数据来源）.

    字段：
    - ``path`` / ``recording``：完整路径与展示文件名
    - ``status``：结局（见 FileStatus）
    - ``duration_s``：本文件净处理耗时（不含排队）
    - ``n_values`` / ``n_curves``：并入特征长表的行数 / 曲线数（失败的为 0）
    - ``error``：中文错误信息（仅 failed 非空）
    - ``log``：逐文件日志行（ctx 的中文日志 + 引擎补充的起止行）
    """

    path: str
    recording: str
    status: FileStatus
    duration_s: float = 0.0
    n_values: int = 0
    n_curves: int = 0
    error: str = ""
    log: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is FileStatus.OK


class BatchSummary(BaseModel):
    """整批批处理的汇总（结束时一次性产出）.

    - ``results``：逐文件结果（与 JobSpec.paths 同序）
    - ``files_written``：导出写出的文件（CSV/HDF5/sidecar 的完整路径）
    - ``cancelled``：整批是否因用户取消提前终止
    """

    job: JobSpec
    results: list[FileResult] = Field(default_factory=list)
    elapsed_s: float = 0.0
    files_written: list[str] = Field(default_factory=list)
    cancelled: bool = False

    # ------------------------------------------------------------------ 统计

    @property
    def n_ok(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def n_failed(self) -> int:
        return sum(1 for r in self.results if r.status is FileStatus.FAILED)

    @property
    def n_cancelled(self) -> int:
        return sum(1 for r in self.results if r.status is FileStatus.CANCELLED)

    @property
    def n_total(self) -> int:
        return len(self.results)

    @property
    def n_values(self) -> int:
        """全批并入长表的总行数."""
        return sum(r.n_values for r in self.results)

    def summary_zh(self) -> str:
        """一行中文摘要（批处理视图收尾展示 / 日志）."""
        base = (
            f"{self.n_total} 个文件：成功 {self.n_ok}、失败 {self.n_failed}"
            + (f"、取消 {self.n_cancelled}" if self.n_cancelled else "")
            + f"，共 {self.n_values} 行特征，用时 {self.elapsed_s:.1f} s"
        )
        if self.cancelled:
            base += "（已取消）"
        return base


def result_for(path: str, status: FileStatus, **fields) -> FileResult:
    """构造 FileResult 的便捷函数（recording 字段从 path 派生，免重复）."""
    return FileResult(path=path, recording=Path(path).name, status=status, **fields)
