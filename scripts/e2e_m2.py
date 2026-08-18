"""M2 端到端验证：全格式扫描入库 → 每种格式打开浏览 → 波形渲染 → 释放.

覆盖 M2 验证标准：
1. 4.9GB dataset 全量扫描 <2min（含 1606 条入库、1500+ 行元数据表可用）
2. 每种格式各开一个能拿到真实波形数据（EDF/GDF 2a/GDF 2b/ds1/ds4/CSV）
3. GDF 中文事件标签进事件条
4. ds4 大文件加载 <10s

运行：conda activate dlv && python scripts/e2e_m2.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
SHEEP = DATA / "sheep"
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"
GDF_2B = DATA / "dataset" / "BCICIV_2b_gdf" / "B0303T.gdf"
DS1 = DATA / "dataset" / "BCICIV_1_mat" / "BCICIV_calib_ds1a.mat"
DS4 = DATA / "dataset" / "BCICIV_4_mat" / "sub1_comp.mat"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.core.fs_store import FsStore
    from dataloadv.io.registry import open_file, scan_folder
    from dataloadv.ui.main_window import MainWindow

    app = QApplication(sys.argv)

    # 无人值守关键：主窗口的打开失败回调会弹模态 QMessageBox（等人点），
    # e2e 里改为打印（e2e_m1 无此坑是因为全部打开都成功；教训记入 HANDOFF）
    import dataloadv.ui.main_window as mw

    _orig_critical = mw.QMessageBox.critical
    mw.QMessageBox.critical = staticmethod(
        lambda *a, **k: print("  [e2e] 打开失败对话框:", a[2] if len(a) > 2 else a)
    )

    win = MainWindow()
    win.show()
    state = win.state
    original_ws = state.workspace.name
    state.reload_workspace("e2e_m2_一次性工作区")

    # CSV 夹具 + 预置采样率（e2e 无人值守，跳过询问对话框路径——对话框逻辑
    # 由 FsStore 已知采样率前置等效覆盖：open 后 notes 不含"未设定"）
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="dlv_e2e_m2_"))
    import numpy as np

    csv_path = tmp / "synth.csv"
    t = np.arange(2000) / 250.0
    rows = ["ch1,ch2"] + [f"{np.sin(2*np.pi*10*tt):.6f},{np.cos(2*np.pi*10*tt):.6f}" for tt in t]
    csv_path.write_text("\n".join(rows) + "\n")
    FsStore().put(csv_path, 250.0)

    # ---- 阶段 1：全量扫描（计时 + 入库 + 表行数）----
    t0 = time.time()
    report = scan_folder(DATA / "dataset")
    dt_scan = time.time() - t0
    check("dataset 全量扫描 <120s", dt_scan < 120, f"({dt_scan:.1f}s)")
    check("识别 1606 条", len(report.items) == 1606, f"(实际 {len(report.items)})")
    check("3 条已知结构报错（ds3×2 + 说明 txt）", len(report.errors) == 3)

    added, dup = state.workspace.add_metas(str(DATA / "dataset"), [i.meta for i in report.items])
    state.workspace.save()
    win._refresh_views()
    # 幂等：重复运行时 dup=1606、added=0 是预期——只断言工作区总量
    check("全部入库（总量 1606）", len(state.workspace) == 1606,
          f"(新增 {added}，重复 {dup}，总量 {len(state.workspace)})")
    check("元数据表 1606 行可用", win.meta_view._model.rowCount() == 1606,
          f"(实际 {win.meta_view._model.rowCount()})")

    # ---- 阶段 2：逐格式打开（真实 MainWindow 打开通路）----
    targets = [
        ("羊 EDF", str(next(p for p in SHEEP.glob("*.edf") if "卧" in p.name)), 8, 0),
        ("2a GDF", str(GDF_2A), 25, 603),
        ("2b GDF", str(GDF_2B), 6, 533),
        ("ds1 mat", str(DS1), 59, 200),
        ("ds4 mat", str(DS4), 67, 0),
        ("CSV", str(csv_path), 2, 0),
    ]
    results: dict[str, tuple] = {}

    def open_next(i: int = 0):
        if i >= len(targets):
            QTimer.singleShot(400, _verify)
            return
        name, path, _nch, _nev = targets[i]
        t_open = time.time()
        win._open_recording_async(path)
        # 大文件给足加载时间（ds4 ~200MB 物化）
        timeout = 15000 if "ds4" in name else 4000

        def _done():
            results[name] = (time.time() - t_open,)
            open_next(i + 1)

        # 轮询等 tab 建立（run_in_thread 回调链完成）
        def _poll(attempt: int = 0):
            got = [w for w in win._browser_tabs.values()
                   if Path(w.rec.meta.path).name == Path(path).name]
            if got and got[0]._loaded_once:
                _done()
            elif attempt * 200 > timeout:
                results[name] = (-1.0,)
                open_next(i + 1)
            else:
                QTimer.singleShot(200, lambda: _poll(attempt + 1))

        _poll()

    def _verify():
        try:
            views = {Path(w.rec.meta.path).name: w for w in win._browser_tabs.values()}
            for name, path, n_ch, n_ev in targets:
                v = views.get(Path(path).name)
                ok = v is not None
                detail = ""
                if ok:
                    v._refresh_data()
                    enabled = [c for c in v._channels if c["enabled"]]
                    got = any(c["curve"].xData is not None and len(c["curve"].xData) > 0
                              for c in enabled)
                    ok = got and len(enabled) == n_ch
                    detail = f"({len(enabled)}/{n_ch} 通道, 曲线{'有' if got else '无'}数据)"
                check(f"{name} 打开且波形有数据", ok, detail)
            # GDF 2a：事件条拿到中文标签 + 事件数
            v2a = views.get(GDF_2A.name)
            if v2a is not None:
                lab = dict(zip(v2a.rec.events.code, v2a.rec.events.label))
                check("2a 中文事件标签", lab.get("769") == "提示：左手（类1）",
                      f"(769 → {lab.get('769')})")
                check("2a 事件 603", len(v2a.rec.events) == 603,
                      f"(实际 {len(v2a.rec.events)})")
            vds1 = views.get(DS1.name)
            if vds1 is not None:
                check("ds1 事件 200（左手/脚）", len(vds1.rec.events) == 200)
            t_open = results.get("ds4 mat", (0.0,))[0]
            check("ds4 加载 <10s", 0 < t_open < 10.0, f"({t_open:.1f}s)")
        except Exception as e:  # noqa: BLE001
            check("逐格式核验", False, str(e))
        finally:
            QTimer.singleShot(300, _finish)

    def _finish():
        try:
            n_before = len(win._browser_tabs)
            for i in range(win.tabs.count() - 1, 0, -1):
                win._on_tab_close(i)
            check("关闭 6 个浏览 tab 后数据释放",
                  not win.state.open_recordings and n_before == 6,
                  f"(关前 {n_before} tab)")
            state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check("收尾清理", False, str(e))
        ok = all(c[1] for c in checks)
        print("\nE2E M2:", "ALL OK" if ok else "FAILED")
        app.quit()

    QTimer.singleShot(500, open_next)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
