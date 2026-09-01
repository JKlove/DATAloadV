"""M9 端到端验收：预处理后连续数据导出（EDF/FIF）——单文件 + 批处理.

自动化替代人工点按，走真实 UI 代码路径（面板 API 驱动）：

1. 羊 EDF：打开 → 带通+陷波+裁剪(前 30s) → 预览当前文件 → _last_ctx 就绪
2. 面板导出 EDF（getSaveFileName 被 patch 定向临时目录；格式菜单绕过——
   export_processed(fmt=...) 参数化直调）→ 读回断：通道数/采样率（用
   browser.rec.meta 动态值，不写死）、时长 = 30 s × 采样率、50Hz 工频
   已随导出保真（PSD 比值 < 0.1，M3 口径）、sidecar 管线+kind=raw
3. 同一 ctx 导出 FIF → 读回 allclose（float32 精度）
4. 批处理：直构 JobSpec（羊 data 目录全部 EDF、bandpass+notch、bandpower、
   export_raw_edf、n_workers=2）同步直跑 BatchEngine.run() → 每文件
   _proc.edf + sidecar、全部 ok、任一读回 50Hz 压制
5. 收尾：关闭全部 tab、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && python scripts/e2e_m9.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
SHEEP_EDF = next((p for p in (DATA / "sheep").glob("*.edf") if "卧" in p.name), None)
SHEEP_ALL = sorted((DATA / "sheep").glob("*.edf"))
TMP = Path(tempfile.mkdtemp(prefix="e2e_m9_"))

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail, flush=True)


def _psd50_ratio(raw) -> float:
    """各通道 50Hz/10Hz 谱值比的中位数（M3 陷波验收口径）."""
    import numpy as np

    spec = raw.compute_psd(method="welch", fmin=1.0, fmax=70.0, verbose="ERROR")
    freqs = spec.freqs
    psd = spec.get_data()
    i50 = abs(freqs - 50.0).argmin()
    i10 = abs(freqs - 10.0).argmin()
    ratios = psd[:, i50] / np.maximum(psd[:, i10], 1e-30)
    return float(np.median(ratios))


def main() -> int:
    import mne
    import numpy as np
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.batch.engine import BatchEngine
    from dataloadv.batch.jobs import JobSpec, PipelineSpec
    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.widgets import pipeline_panel as pp_mod

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框——**逐模块** patch
    for mod in (mw, pp_mod):
        mod.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else "", flush=True))
        mod.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else "", flush=True))
        mod.QMessageBox.information = staticmethod(lambda *a, **k: print("[patched info]", a[-1] if a else "", flush=True))

    # 导出路径固定到临时目录（走面板完整导出代码路径，只是不弹文件对话框）
    def _save_name(*a, **_k):
        default = a[2] if len(a) > 2 else "out.bin"
        return str(TMP / default), ""

    pp_mod.QFileDialog.getSaveFileName = staticmethod(_save_name)

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m9_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m9_一次性工作区")

    panel = win.pipeline_panel
    shared: dict = {}  # 跨 QTimer 闭包传引用

    # ------------------------------------------------- 阶段 1：羊 EDF 预览
    def _stage1():
        win._open_recording_async(str(SHEEP_EDF))
        QTimer.singleShot(2000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or not browser._loaded_once:
            QTimer.singleShot(800, _stage1b)
            return
        check("羊 EDF 浏览 tab 就绪", True, f"({browser.rec.meta.filename})")
        shared["browser"] = browser
        panel.add_step("bandpass", l_freq=1.0, h_freq=40.0)
        panel.add_step("notch", freqs=[50.0])
        panel.add_step("crop", tmin=0.0, tmax=30.0)
        panel.start_preview()
        QTimer.singleShot(3000, _stage1c)

    def _stage1c(tries: int = 12):
        ctx = panel._last_ctx
        if ctx is None or ctx.raw is None:
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage1c(tries - 1))
                return
            check("预览完成，_last_ctx 就绪", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        check("预览完成，_last_ctx.stage == raw", ctx.stage == "raw",
              f"(stage={ctx.stage}，{len(ctx.history)} 步)")
        QTimer.singleShot(300, _stage2)

    # ------------------------------------------------- 阶段 2：面板导出 EDF
    def _stage2():
        panel.export_processed(fmt="edf")  # 格式参数化直调（菜单只选格式）
        stem = Path(shared["browser"].rec.meta.filename).stem
        shared["stem"] = stem
        QTimer.singleShot(2500, _stage2b)

    def _stage2b(tries: int = 12):
        out = TMP / f"{shared['stem']}_proc.edf"
        sidecar = TMP / f"{shared['stem']}_proc.pipeline.json"
        if not out.exists() or not sidecar.exists():
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage2b(tries - 1))
                return
            check("EDF + sidecar 已写出", False, f"（{out.name} 等待超时）")
            QTimer.singleShot(300, _finish)
            return
        check("EDF + sidecar 已写出", True)
        meta = shared["browser"].rec.meta  # 通道数/采样率用运行时动态值，不写死
        back = mne.io.read_raw_edf(out, preload=True, verbose="ERROR")
        check("读回通道数与源一致", len(back.ch_names) == len(meta.channel_names),
              f"(实际 {len(back.ch_names)}，预期 {len(meta.channel_names)})")
        check("读回采样率与源一致", back.info["sfreq"] == meta.sfreq,
              f"(实际 {back.info['sfreq']:g}，预期 {meta.sfreq:g})")
        # EDF 按整秒数据记录写盘（mne 官方行为）：crop 含端点 7501 样本
        # → 补齐到 31 记录；容差 = 不超过 1 个数据记录的边缘补齐
        n_crop = int(30 * meta.sfreq) + 1
        pad = back.n_times - n_crop
        check("读回时长 = 裁剪窗 30 s（整秒补齐 ≤1 记录）",
              0 <= pad <= round(meta.sfreq),
              f"(裁剪窗 {n_crop} 样本，读回 {back.n_times}，补齐 {pad})")
        ratio = _psd50_ratio(back)
        check("50Hz 工频随导出保真（PSD 比值 < 0.1）", ratio < 0.1,
              f"(50Hz/10Hz 比值中位数 {ratio:.4f})")
        doc = json.loads(sidecar.read_text(encoding="utf-8"))
        steps = [s["step"] for s in doc["pipeline"]]
        check("sidecar 管线 = bandpass/notch/crop 且 kind=raw",
              steps == ["bandpass", "notch", "crop"] and doc["extra"]["kind"] == "raw",
              f"({steps})")
        check("导出后按钮恢复可用", panel._btn_export.isEnabled())
        QTimer.singleShot(300, _stage3)

    # ------------------------------------------------- 阶段 3：同一 ctx 导出 FIF
    def _stage3():
        panel.export_processed(fmt="fif")
        QTimer.singleShot(2500, _stage3b)

    def _stage3b(tries: int = 12):
        out = TMP / f"{shared['stem']}_proc_raw.fif"
        if not out.exists():
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage3b(tries - 1))
                return
            check("FIF 已写出（_raw 规约后缀）", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        check("FIF 已写出（_raw 规约后缀）", True, f"({out.name})")
        back = mne.io.read_raw_fif(out, preload=True, verbose="ERROR")
        ref = panel._last_ctx.raw.get_data()
        ok = np.allclose(back.get_data(), ref, rtol=1e-6, atol=1e-12)
        check("FIF 数值无损往返（float32 精度）", ok,
              f"(最大偏差 {np.abs(back.get_data() - ref).max():.3e} V)")
        QTimer.singleShot(300, _stage4)

    # ------------------------------------------------- 阶段 4：批处理引擎直跑
    def _stage4():
        job = JobSpec(
            name="e2e_m9批",
            paths=[str(p) for p in SHEEP_ALL],
            pipeline=PipelineSpec(
                steps=[{"step": "bandpass", "params": {"l_freq": 1.0, "h_freq": 40.0}},
                       {"step": "notch", "params": {"freqs": [50.0]}}],
                features=[{"feature": "bandpower", "params": {"bands": ["alpha"]}}],
            ),
            n_workers=2,
            export_raw_edf=True,
            export_dir=str(TMP / "batch"),
        )
        shared["summary"] = BatchEngine(job).run()  # 同步直跑（纯 Python，无 Qt）
        QTimer.singleShot(300, _stage4b)

    def _stage4b():
        summary = shared["summary"]
        n_ok = sum(1 for r in summary.results if r.status.value == "ok")
        check(f"批处理 {len(SHEEP_ALL)} 个羊文件全部 ok", n_ok == len(SHEEP_ALL),
              f"(n_ok={n_ok})")
        outs = sorted((TMP / "batch").glob("*_proc.edf"))
        sides = sorted((TMP / "batch").glob("*_proc.pipeline.json"))
        check("每文件一个 _proc.edf + sidecar",
              len(outs) == len(SHEEP_ALL) == len(sides),
              f"(数据 {len(outs)} / sidecar {len(sides)} / 源 {len(SHEEP_ALL)})")
        raw_files = [p for p in summary.files_written if p.endswith("_proc.edf")]
        check("files_written 汇总含全部连续产物", len(raw_files) == len(SHEEP_ALL),
              f"({len(raw_files)} 条)")
        if outs:
            back = mne.io.read_raw_edf(outs[0], preload=True, verbose="ERROR")
            ratio = _psd50_ratio(back)
            check("批处理产物 50Hz 压制随导出保真", ratio < 0.1,
                  f"(比值中位数 {ratio:.4f}，{outs[0].name})")
        QTimer.singleShot(300, _finish)

    def _finish():
        try:
            for i in range(win.tabs.count() - 1, 0, -1):
                win._on_tab_close(i)
            check("关闭全部 tab 后数据释放", not win.state.open_recordings)
            win.state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check("收尾清理", False, str(e))
        ok = all(c[1] for c in checks)
        print("\nE2E M9:", "ALL OK" if ok else "FAILED", flush=True)
        print(f"（导出产物在 {TMP}）", flush=True)
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
