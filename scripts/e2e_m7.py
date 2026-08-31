"""M7 端到端验收：信号质量体检——浏览器一键体检 + 特征链 + 导出链.

自动化替代人工点按，走真实代码路径（浏览器按钮 → 后台线程 → 列表标记 →
坏道确认弹窗；提取器注册表 → FeatureTable → CSV/HDF5 导出）：

1. 羊 BDF：浏览器「质量体检」→ CH5-8 开路复用通道判坏（4 个），
   确认弹窗 Yes → 自动标坏道 + 曲线灰显 + info["bads"] 写入；
2. clinicaldata TPDJ-位置1：八通道死放大器全坏（黄金标准）；
3. 特征链：同一文件经 QualityCheckFeature 提取 → 长表 → CSV/HDF5 回读，
   分级与浏览器路径完全一致（两入口一算力的验证）；
4. 收尾：关闭全部 tab、恢复原工作区（幂等，可反复跑）。

运行：conda activate dlv && QT_QPA_PLATFORM=offscreen python scripts/e2e_m7.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
SHEEP_EDF = next((p for p in (DATA / "sheep").glob("*.edf") if "卧" in p.name), None)
TPDJ1 = next(
    (DATA / "clinicaldata" / "01号脑电" / "TPDJ").glob("*位置1*.edf"), None
)

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail, flush=True)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from dataloadv.io.registry import open_file
    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.widgets import signal_browser as sb

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框——MainWindow 与
    # signal_browser 是两个模块级引用，必须分别 patch（罩不到子模块）
    mw.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else "", flush=True))
    mw.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else "", flush=True))
    sb.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else "", flush=True))
    sb.QMessageBox.information = staticmethod(lambda *a, **k: print("[patched information]", a[-1] if a else "", flush=True))
    qc_calls: list[str] = []
    sb.QMessageBox.question = staticmethod(
        lambda *a, **k: (qc_calls.append(a[-1] if a else ""), QMessageBox.StandardButton.Yes)[1]
    )

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m7_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m7_一次性工作区")

    def _finish() -> int:
        failed = [c for c in checks if not c[1]]
        print(f"\n== e2e_m7 汇总：{len(checks) - len(failed)}/{len(checks)} 项通过 ==", flush=True)
        for name, ok, detail in checks:
            if not ok:
                print("❌", name, detail, flush=True)
        return 1 if failed else 0

    def _close_and(fn) -> None:
        """关掉浏览 tab（从后往前，保留 index 0 的常驻页——e2e_m3 同款）."""
        for i in range(win.tabs.count() - 1, 0, -1):
            w = win.tabs.widget(i)
            if hasattr(w, "teardown"):
                w.teardown()
            win.tabs.removeTab(i)
        QTimer.singleShot(300, fn)

    # ---------------------------------------------------------------- 阶段 1：羊浏览器体检
    def _stage1():
        win._open_recording_async(str(SHEEP_EDF))
        QTimer.singleShot(2000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or not browser._loaded_once:
            QTimer.singleShot(800, _stage1b)
            return
        try:
            browser._run_qc()  # 工具栏「质量体检」按钮的真实处理逻辑
            _stage1c(browser)
        except Exception as e:  # noqa: BLE001 - e2e 汇总报错不中断后续阶段
            check("羊：浏览器体检执行", False, repr(e))
            _close_and(_stage2)

    def _stage1c(browser, tries: int = 0):
        if (browser._qc_running or not browser._qc) and tries < 150:
            QTimer.singleShot(100, lambda: _stage1c(browser, tries + 1))
            return
        try:
            bads = [n for n, r in browser._qc.items() if r["quality"] == "bad"]
            check("羊：体检判坏 4 通道（CH5-8 开路复用）", len(bads) == 4, f"({bads})")
            check("羊：坏通道全部报复用",
                  all(browser._qc[n]["dup_with"] for n in bads))
            check("羊：确认弹窗弹出过一次", len(qc_calls) == 1)
            check("羊：Yes → 坏道自动标记", sorted(browser.current_bads()) == sorted(bads))
            check("羊：坏道写入 raw.info['bads']",
                  set(browser.rec.raw.info["bads"]) == set(bads))
            texts = {browser._ch_list.item(i).text()
                     for i in range(browser._ch_list.count())}
            check("羊：列表前缀 ✗/✓ 生效",
                  any(t.startswith("✗ ") for t in texts)
                  and any(t.startswith(("✓ ", "? ")) for t in texts))
            tips = [browser._qc[n]["reasons"] for n in bads]
            check("羊：tooltip 问题明细含「开路复用」",
                  any(any("开路复用" in s for s in rs) for rs in tips))
            check("羊：体检后按钮恢复可用",
                  browser._btn_qc.isEnabled() and not browser._qc_running)
        except Exception as e:  # noqa: BLE001
            check("羊：体检结果断言", False, repr(e))
        _close_and(_stage2)

    # ---------------------------------------------------------------- 阶段 2：TPDJ-位置1
    def _stage2():
        if TPDJ1 is None:
            check("clinicaldata TPDJ-位置1 存在", False, f"({TPDJ1})")
            _stage3()
            return
        win._open_recording_async(str(TPDJ1))
        QTimer.singleShot(2000, _stage2b)

    def _stage2b():
        browser = win._get_active_browser()
        if browser is None or not browser._loaded_once:
            QTimer.singleShot(800, _stage2b)
            return
        browser._run_qc()
        _stage2c(browser)

    def _stage2c(browser, tries: int = 0):
        if (browser._qc_running or not browser._qc) and tries < 150:
            QTimer.singleShot(100, lambda: _stage2c(browser, tries + 1))
            return
        try:
            bads = [n for n, r in browser._qc.items() if r["quality"] == "bad"]
            check("TPDJ-位置1：八通道死放大器全坏",
                  len(browser._qc) == 8 and len(bads) == 8, f"(坏 {len(bads)}/8)")
            check("TPDJ-位置1：Yes → 八通道全部标坏道", len(browser.current_bads()) == 8)
        except Exception as e:  # noqa: BLE001
            check("TPDJ-位置1：体检结果断言", False, repr(e))
        _close_and(_stage3)

    # ---------------------------------------------------------------- 阶段 3：特征链 + 导出
    def _stage3():
        from dataloadv.batch.results import FeatureTable
        from dataloadv.export.features_io import (
            export_features_csv,
            export_features_hdf5,
            read_features_hdf5,
        )
        from dataloadv.features import FEATURE_REGISTRY
        from dataloadv.features.qc import QualityCheckParams
        from dataloadv.proc.context import ProcessingContext

        try:
            check("注册表含 qc 且排菜单首位",
                  "qc" in FEATURE_REGISTRY and list(FEATURE_REGISTRY)[0] == "qc")
            rec = open_file(SHEEP_EDF)
            ctx = ProcessingContext.from_recording(rec)
            result = FEATURE_REGISTRY["qc"].extract(ctx, QualityCheckParams())
            table = FeatureTable()
            table.add_result(result, recording=rec.meta.filename, subject="sheep")
            df = table.df
            lv = df[df["feature"] == "qc_level"]["value"].tolist()
            check("特征链：8 通道 × qc_level 行", len(lv) == 8)
            check("特征链：判坏 4 通道（与浏览器路径一致）",
                  sum(1 for v in lv if v == 2.0) == 4)

            out = Path(tempfile.mkdtemp(prefix="e2e_m7_"))
            csv_path = out / "qc.csv"
            export_features_csv(table, csv_path)
            with open(csv_path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            levels = [float(r["数值"]) for r in rows if r["特征"] == "qc_level"]
            check("CSV 回读：中文表头 + qc_level 8 行", len(levels) == 8)
            check("CSV 回读：坏道数一致", sum(1 for v in levels if v == 2.0) == 4)

            h5_path = out / "qc.h5"
            export_features_hdf5(table, h5_path)
            df2, _ = read_features_hdf5(h5_path)
            lv2 = df2[df2["feature"] == "qc_level"]["value"].tolist()
            check("HDF5 回读：分级与 CSV 一致", lv2 == levels)
            rec.unload()
        except Exception as e:  # noqa: BLE001
            check("特征链/导出链", False, repr(e))
        QTimer.singleShot(200, _stage4)

    # ---------------------------------------------------------------- 阶段 4：收尾
    def _stage4():
        win.state.reload_workspace(original_ws)
        app.quit()

    QTimer.singleShot(300, _stage1)
    app.exec()
    return _finish()


if __name__ == "__main__":
    sys.exit(main())
