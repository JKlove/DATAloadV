"""BatchEngine——纯 Python 批处理引擎（线程池 / 取消 / 逐文件日志 / 末尾导出）.

架构位置（硬性规则 #1：batch 层禁止 import Qt）：
- 本类**不持有任何 Qt 对象**；进度经构造时传入的回调上抛——回调在
  **worker 线程**被调用，UI 侧（batch_dialog）用线程安全队列 +
  QTimer 转回主线程，测试侧直接在同步回调里断言
- ``run()`` 阻塞执行整批：UI 把它整个丢进一个后台 QThread
  （workers.generic.run_in_thread），并发由内部的
  ``concurrent.futures.ThreadPoolExecutor`` 提供（默认 2 线程——
  瓶颈是内存带宽而非 GIL，plan.md §4）

单文件流水线（与 pipeline_panel.start_features 的 worker 完全同构——
单文件与批处理走同一条代码路径，行为才可能一致）::

    open_file(path, PRELOAD) → ProcessingContext.from_recording（副本）
    → apply_pipeline（逐步骤查取消）→ apply_features → FeatureTable.add_result
    → rec.unload()（用完即弃，内存可控）

逐文件容错：任何单文件失败记 ``FileResult(status=failed, error=中文原因)``
并继续下一个文件——绝不让一个坏文件杀掉整批（与 scan_folder 同约定）。

内存配合 ``LoadedRawCache``：处理期间 pin 住该文件的 Recording——
两个 worker 同时整载大文件时，LRU 不会把对方正在用的数据逐出。

本模块禁止 import PySide6/pyqtgraph（硬性架构规则 #1）。
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

from ..core.recording import LoadPolicy, LoadedRawCache, Recording
from ..export.continuous_io import export_continuous
from ..export.features_io import export_features_csv, export_features_hdf5
from ..export.provenance import write_provenance
from ..features.base import FeatureError, apply_features
from ..io.base import ScanError
from ..io.registry import open_file
from ..io.table import FS_UNSET_NOTE
from ..proc.base import PipelineCancelled, StepError, apply_pipeline
from ..proc.context import ProcessingContext
from .jobs import (
    BatchSummary,
    FileResult,
    FileStatus,
    JobSpec,
    PipelineSpec,
    result_for,
)
from .results import FeatureTable

logger = logging.getLogger(__name__)

# 回调类型：on_file_done(FileResult)、on_progress(done, total, current_name)
FileDoneCb = Callable[[FileResult], None]
ProgressCb = Callable[[int, int, str], None]


class BatchEngine:
    """执行一个 JobSpec：并发处理文件清单，累积特征长表，可选末尾导出.

    用法（UI / 测试统一）::

        eng = BatchEngine(job, on_file_done=cb, on_progress=cb2)
        summary = eng.run()          # 阻塞直至整批结束（含导出）
        summary.results / eng.table  # 逐文件结果 / 合并特征表

    线程规则：``cancel()`` 可从任意线程调用（threading.Event）；
    两个回调在 worker 线程执行，禁止在其中触碰 Qt 控件。
    """

    def __init__(
        self,
        job: JobSpec,
        on_file_done: Optional[FileDoneCb] = None,
        on_progress: Optional[ProgressCb] = None,
    ) -> None:
        self._job = job
        self._on_file_done = on_file_done
        self._on_progress = on_progress
        self._cancel = threading.Event()  # 取消信号：跨线程 set，worker 逐步骤查
        self._table = FeatureTable()
        self._table_lock = threading.Lock()  # 多 worker 并发 add_result 的互斥
        # M9：逐文件连续导出的产物汇集（run() 尾部并入 summary.files_written）
        self._raw_written: list[str] = []
        self._raw_lock = threading.Lock()  # 多 worker 并发追加的互斥
        self._done_count = 0
        self._count_lock = threading.Lock()

    # ------------------------------------------------------------------ 控制

    @property
    def job(self) -> JobSpec:
        return self._job

    @property
    def table(self) -> FeatureTable:
        """合并特征长表（run() 过程中逐文件增长；读它请自带锁外快照语义）."""
        return self._table

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        """请求取消（任意线程可调；已开始的文件做完当前步骤即停）."""
        self._cancel.set()
        logger.info("批处理收到取消请求（%s）", self._job.name)

    # ------------------------------------------------------------------ 执行

    def run(self) -> BatchSummary:
        """阻塞执行整批（在调用线程里跑池、等池、导出）.

        :raises StepError/FeatureError: 管线/特征描述本身非法——这会让**每个**
            文件都失败，启动前由调用方先 ``PipelineSpec.resolved_*()`` 校验更友好；
            引擎不吞这类错误（早失败早修）
        :returns: BatchSummary（含逐文件结果与导出文件清单）
        """
        job = self._job
        steps = job.pipeline.resolved_steps()  # 描述非法在此抛中文错误
        feats = job.pipeline.resolved_features()
        t0 = time.perf_counter()
        results: dict[int, FileResult] = {}  # 序号 → 结果（保 JobSpec.paths 顺序）
        lock = threading.Lock()

        def _work(index: int, path: str) -> None:
            r = self._process_one(path, steps, feats)
            with lock:
                results[index] = r
            with self._count_lock:
                self._done_count += 1
                done = self._done_count
            if self._on_progress is not None:
                self._safe_call(self._on_progress, done, len(job.paths), r.recording)
            if self._on_file_done is not None:
                self._safe_call(self._on_file_done, r)

        with ThreadPoolExecutor(max_workers=job.n_workers) as pool:
            # 全部提交（FIFO 队列按提交顺序派发）；已取消时 worker 秒退，
            # 未开始的文件由 _process_one 直接记 cancelled
            futures = [pool.submit(_work, i, p) for i, p in enumerate(job.paths)]
            for f in futures:
                f.result()  # _work 内部已兜底一切异常，这里只等齐

        cancelled = self._cancel.is_set()
        summary = BatchSummary(
            job=job,
            results=[results.get(i, result_for(p, FileStatus.CANCELLED))
                     for i, p in enumerate(job.paths)],
            elapsed_s=time.perf_counter() - t0,
            cancelled=cancelled,
        )
        # 末尾导出（整批一次；文件级字段 recording 已在长表里，跨文件可区分）。
        # 特征表导出与连续数据导出相互独立：只勾连续格式时不得误写特征文件
        # （旧逻辑 wants_export() 一票通过就进 _export，会把 CSV/HDF5 都写出去）
        files: list[str] = []
        if (job.export_csv or job.export_hdf5) and len(self._table) > 0:
            files += self._export(job)
        files += self._raw_written  # 逐文件连续导出已在 _process_one 内完成
        summary.files_written = files
        logger.info(
            "批处理「%s」结束：%s", job.name, summary.summary_zh()
        )
        return summary

    # ------------------------------------------------------------------ 单文件

    def _process_one(
        self,
        path: str,
        steps: list[tuple[str, object]],
        feats: list[tuple[str, object]],
    ) -> FileResult:
        """处理单个文件（worker 线程内）：开→管线→特征→并入长表→卸载.

        任何失败都转成 failed 结果（中文原因 + 日志），绝不上抛——
        单文件失败不能中断整批。
        """
        t0 = time.perf_counter()
        name = Path(path).name
        logs: list[str] = [f"—— 开始处理 {name} ——"]
        rec: Optional[Recording] = None
        pinned = False
        try:
            if self._cancel.is_set():
                return self._stamp(result_for(path, FileStatus.CANCELLED, log=logs), t0)
            rec = open_file(path, LoadPolicy.PRELOAD)
            if FS_UNSET_NOTE in rec.meta.notes:
                # CSV/TXT/通用 HDF5 且采样率从未设定：以错误采样率跑管线是
                # 坏数据——明确失败并告诉用户怎么修（先在浏览 tab 里打开一次）
                raise StepError(
                    f"{name} 的采样率未设定（表格/通用 HDF5 内无此信息）。"
                    "请先在浏览 tab 打开该文件并设定采样率，再纳入批处理"
                )
            logs.append(f"已打开（{rec.meta.n_channels} 导 / {rec.meta.sfreq:g} Hz / "
                        f"{rec.meta.duration_s:.1f} s）")
            ctx = ProcessingContext.from_recording(rec)
            # pin：两个 worker 并发整载时防 LRU 把正在用的数据逐出
            LoadedRawCache.instance().pin(rec)
            pinned = True
            try:
                if steps:
                    apply_pipeline(ctx, steps, cancel_check=self._cancel.is_set)
                # M9：连续导出须紧跟管线（epoching 步骤会把 ctx.raw 换成
                # epochs——之后再导就没有连续数据了）；放在 apply_features
                # 之前且自成 try（见 _export_continuous）：导出失败不连累特征
                self._export_continuous(path, ctx, logs)
                result = apply_features(ctx, feats, cancel_check=self._cancel.is_set)
            finally:
                if pinned:
                    LoadedRawCache.instance().unpin(rec)
            # 并入共享长表（多 worker 并发点，锁保护）；add_result 恰好
            # 每个标量追加一行，故 n_values = len(result.scalars)
            with self._table_lock:
                self._table.add_result(result, rec.meta.filename, rec.meta.subject or "")
            logs.extend(ctx.logs)
            out = result_for(
                path, FileStatus.OK,
                duration_s=time.perf_counter() - t0,
                n_values=len(result.scalars),
                n_curves=len(result.curves),
                log=logs,
            )
            out.log.append(f"—— 完成：{out.n_values} 个特征值、"
                           f"{out.n_curves} 条曲线，{out.duration_s:.1f} s ——")
            return out
        except PipelineCancelled:
            logs.append("—— 已取消 ——")
            return self._stamp(result_for(path, FileStatus.CANCELLED, log=logs), t0)
        except (StepError, FeatureError, ScanError) as e:
            # 预期内的失败：中文信息已是用户可读的最终形态
            logs.append(f"—— 失败：{e} ——")
            return self._stamp(
                result_for(path, FileStatus.FAILED, error=str(e), log=logs), t0)
        except Exception as e:  # noqa: BLE001 - 意外异常也要进结果而非杀整批
            tail = traceback.format_exc().strip().splitlines()[-3:]
            logs.append("—— 意外失败：" + " | ".join(tail) + " ——")
            logger.exception("批处理单文件意外失败：%s", name)
            return self._stamp(
                result_for(path, FileStatus.FAILED, error=f"意外错误：{e}", log=logs),
                t0)
        finally:
            if rec is not None:
                if pinned:
                    LoadedRawCache.instance().unpin(rec)
                rec.unload()  # 用完即弃：meta/events 不再需要，数据立即归还

    @staticmethod
    def _stamp(result: FileResult, t0: float) -> FileResult:
        """统一补齐 duration_s（取消/失败路径没有自己的计时点）."""
        return result.model_copy(update={"duration_s": time.perf_counter() - t0})

    # ------------------------------------------------------------------ 导出

    def _export_continuous(self, path: str, ctx: ProcessingContext,
                           logs: list[str]) -> list[str]:
        """逐文件连续数据导出（M9；worker 线程内，紧跟 apply_pipeline 之后）.

        - 未勾任何连续格式 / 未给导出目录：无事发生，返回 []
        - 管线含 epoching（ctx.stage != "raw"）：日志记「已跳过」——分段产物
          请走特征结果 tab 的「导出分段…」，此处没有连续数据可写
        - 导出/溯源任一异常：只降级为该文件日志（status 仍 ok）——连续导出
          是附加产物，不应连累特征计算的成败
        :returns: 本文件实际写出的路径（含 sidecar；已同时汇集进 _raw_written）
        """
        job = self._job
        fmts = [f for f, on in (("edf", job.export_raw_edf),
                                ("fif", job.export_raw_fif)) if on]
        if not fmts or not job.export_dir:
            return []
        if ctx.stage != "raw" or ctx.raw is None:
            logs.append("—— 连续导出已跳过：管线含分段步骤，无连续数据产物 ——")
            return []
        stem = Path(path).stem
        written: list[str] = []
        try:
            out_dir = Path(job.export_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            for fmt in fmts:
                out = export_continuous(ctx.raw, out_dir / f"{stem}_proc.{fmt}", fmt=fmt)
                sidecar = write_provenance(
                    out, pipeline=ctx.history, recordings=[path],
                    extra={"exported": out.name, "format": fmt, "kind": "raw"})
                written += [str(out), str(sidecar)]
                logs.append(f"连续 {fmt.upper()} 已写出：{out.name}")
            with self._raw_lock:
                self._raw_written += written
        except Exception as e:  # noqa: BLE001 - 导出失败降级为日志，不杀特征计算
            logs.append(f"—— 连续导出失败：{e} ——")
            logger.exception("批处理连续导出失败：%s", path)
        return written

    def _export(self, job: JobSpec) -> list[str]:
        """整批结束后导出特征表 + sidecar（在 run() 调用线程执行）.

        文件主名用作业名；CSV/HDF5 与单文件导出同一套代码（中文表头/
        BOM/曲线宽表口径一致）；sidecar 记录完整管线与文件清单——
        这是批处理可复现性的载体。
        """
        out_dir = Path(job.export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        try:
            if job.export_csv:
                written += [str(p) for p in export_features_csv(
                    self._table, out_dir / f"{job.name}.csv")]
            if job.export_hdf5:
                written.append(str(export_features_hdf5(
                    self._table, out_dir / f"{job.name}.h5")))
            sidecar = write_provenance(
                out_dir / f"{job.name}.csv",
                pipeline=job.pipeline.steps,
                features=job.pipeline.features,
                recordings=self._table.recording_names(),
                extra={"batch": {"n_files": len(job.paths),
                                 "n_workers": job.n_workers,
                                 "files_written": [Path(p).name for p in written],
                                 "raw_files_written": [Path(p).name
                                                       for p in self._raw_written]}},
            )
            written.append(str(sidecar))
        except Exception as e:  # noqa: BLE001 - 导出失败不吞：记日志并在结果里可见
            logger.exception("批处理导出失败")
            raise StepError(f"导出失败：{e}") from e
        return written

    # ------------------------------------------------------------------ 工具

    @staticmethod
    def _safe_call(cb, *args) -> None:
        """回调绝不影响批处理（坏回调只记日志）."""
        try:
            cb(*args)
        except Exception:  # noqa: BLE001
            logger.exception("批处理回调异常（忽略）")
