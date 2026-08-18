"""M5 端到端验收：批处理引擎 + 对话框 + 扩展格式注册.

自动化替代人工点按，走真实 UI 代码路径（对话框 API 驱动）：

1. 全量批处理（M5 验收主项）：工作区导入 45 个 2b GDF → 批处理对话框
   全选 + 1 个损坏文件（patch 进路径清单）→ 分段(769/770)+双频段特征
   → CSV 导出。断言：45 成功 1 失败、长表跨 45 个录制、CSV BOM+中文表头
   行数一致、sidecar 含完整管线与文件清单、失败行红显且日志可查
2. UI 全程响应：批处理期间 100ms 心跳计时器持续跳动（事件循环未被占住）
3. 中途取消：第二批跑到首个文件完成后取消 → 整批标记取消、未开始文件
   全为已取消、绝无全部跑完
4. 扩展格式：neo（Blackrock/Open Ephys/Intan）与 NWB 读取器已注册
5. 收尾：关闭全部 tab、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && QT_QPA_PLATFORM=offscreen python scripts/e2e_m5.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
GDF_2B_DIR = DATA / "dataset" / "BCICIV_2b_gdf"
TMP = Path(tempfile.mkdtemp(prefix="e2e_m5_"))

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    # flush=True：重定向到文件时 stdout 是块缓冲，中途崩溃不丢已过的检查项
    print(("✅" if ok else "❌"), name, detail, flush=True)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QTextEdit

    from dataloadv.core import app_settings as app_settings_mod
    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.dialogs import batch_dialog as bd_mod
    from dataloadv.ui.dialogs.batch_dialog import BatchDialog

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框——逐模块 patch
    for mod in (mw, bd_mod):
        mod.QMessageBox = type(  # noqa: 各模块独立引用，逐个替换
            "FakeBox", (), {k: staticmethod(lambda *a, **k: print("[patched]", k))
                            for k in ("critical", "warning", "information")})

    # 设置写进临时目录（不污染用户 ~/.dataloadv/settings.json）
    app_settings_mod.SETTINGS_PATH = TMP / "settings.json"

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m5_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m5_一次性工作区")

    # ------------------------------------------------ 导入 45 个 2b GDF
    from dataloadv.io.registry import scan_folder

    report = scan_folder(GDF_2B_DIR, recursive=False)
    paths = sorted(str(Path(it.meta.path)) for it in report.items)
    ws = win.state.workspace
    ws.add_metas(str(GDF_2B_DIR), [it.meta for it in report.items])
    ws.save()
    win.state.notify_workspace_changed()
    check("扫描 2b 目录并导入工作区", len(paths) == 45,
          f"（{len(report.items)} 个 GDF，{len(report.errors)} 个错误）")

    # 面板组链：分段 + 双频段频带功率（批处理吃面板链的 dict 快照）。
    # 事件码取 769/770/783：T（训练）文件 120 段；E（评估）文件无类别标签、
    # cue 用 783（未知类）标 160 段——同一码表跑通两类文件才叫批处理
    panel = win.pipeline_panel
    panel.add_step("epoching", event_codes=["769", "770", "783"], tmin=-1.0, tmax=4.0)
    panel.add_feature("bandpower", bands=["alpha", "beta"])

    shared: dict = {}

    def _new_dialog() -> BatchDialog:
        # 与主窗口菜单路径同构的接线：结果既喂 e2e 断言也开批处理结果 tab
        dlg = BatchDialog(
            lambda: ws.all_metas(),
            panel.pipeline_dicts,
            panel.feature_dicts,
            win,
        )
        shared["payloads"] = []
        dlg.batch_finished.connect(shared["payloads"].append)
        dlg.batch_finished.connect(win._on_batch_finished)  # noqa: SLF001 - e2e 同菜单路径
        shared["dlg"] = dlg
        return dlg

    def _make_broken_gdf() -> Path:
        p = TMP / "broken.gdf"
        p.write_bytes(b"\x00" * 4096)  # 假 GDF：魔数都过不了
        return p

    # ------------------------------------------------ 阶段 1：全量批处理
    def _stage1():
        dlg = _new_dialog()
        dlg._set_all_checked(True)
        # 验收"错误可查"：把一个损坏文件混进路径清单（45 真实 + 1 损坏）
        broken = _make_broken_gdf()
        dlg._selected_paths = lambda: [*paths, str(broken)]  # noqa: PLW0642 - e2e 注入
        dlg._dir.setText(str(TMP))
        dlg._name.setText("e2e_m5_features")
        dlg._cb_csv.setChecked(True)
        dlg._cb_h5.setChecked(False)
        check("对话框勾选 46 路径（45 真 + 1 坏）", len(dlg._selected_paths()) == 46)

        # UI 响应性探针：批处理期间 100ms 心跳（事件循环被占住则心跳停止）
        ticks: list[float] = []

        def _tick():
            ticks.append(time.monotonic())

        heartbeat = QTimer(win)
        heartbeat.setInterval(100)
        heartbeat.timeout.connect(_tick)
        heartbeat.start()
        shared["ticks"] = ticks
        shared["heartbeat"] = heartbeat

        dlg._on_run_clicked()
        check("已切到运行页", dlg._stack.currentIndex() == 1)
        QTimer.singleShot(500, lambda: _stage1_wait(tries=480))  # 上限 ~8 分钟

    def _stage1_wait(tries: int):
        dlg = shared["dlg"]
        if not shared["payloads"] and tries > 0:
            QTimer.singleShot(1000, lambda: _stage1_wait(tries - 1))
            return
        shared["heartbeat"].stop()
        if not shared["payloads"]:
            check("批处理完成（收到结果）", False, "（等待超时）")
            QTimer.singleShot(300, _stage3)
            return
        payload = shared["payloads"][0]
        summary = payload["summary"]
        table = payload["table"]
        dlg = shared["dlg"]

        check("45 成功 + 1 失败（坏文件不杀整批）",
              summary.n_ok == 45 and summary.n_failed == 1,
              f"（{summary.summary_zh()}）")
        check("长表覆盖 45 个录制", table.n_recordings == 45,
              f"（{table.n_recordings}）")
        check("summary 行数 = 逐文件行数之和",
              summary.n_values == sum(r.n_values for r in summary.results)
              and summary.n_values > 45 * 100,
              f"（总 {summary.n_values} 行）")
        # T 文件 120 段、E 文件 783 标 160 段；每文件 ≥ 120 段 × 6 通道 × 2 频段
        ok_vals = [r.n_values for r in summary.results if r.ok]
        check("每个成功文件特征值数 ≥ 1440（≥120 段×6 导×2 频段）",
              all(v >= 1440 for v in ok_vals), f"（最小 {min(ok_vals)}）")

        # UI 全程响应：心跳数 ≥ 10（≥1 s，说明事件循环没被批处理占住）
        n_ticks = len(shared["ticks"])
        check("批处理期间 UI 事件循环持续响应（心跳计时器）",
              n_ticks >= 10, f"（心跳 {n_ticks} 次 ≈ {n_ticks * 0.1:.0f} s）")

        # 失败行红显 + 错误可查（不 exec 弹窗，直接验证日志对话框内容）
        failed = next(r for r in summary.results if not r.ok)
        view = dlg._progress
        row = view._row_of(failed.path)
        status_text = view._table.item(row, 1).text()
        tooltip = view._table.item(row, 1).toolTip()
        check("失败行状态「失败」+ 悬停原因", status_text == "失败" and bool(tooltip),
              f"（{status_text} / {tooltip[:40]}）")
        from dataloadv.ui.widgets.batch_view import FileLogDialog

        log_dlg = FileLogDialog(failed, win)
        log_text = log_dlg.findChildren(QTextEdit)[0].toPlainText()
        check("双击日志对话框含错误信息", "【错误】" in log_text and failed.error in log_text,
              f"（{failed.error[:40]}）")

        # 批处理结果 tab（主窗口）
        titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
        check("主窗口开出批处理结果 tab",
              any(t.startswith("批处理 · ") for t in titles), f"（{titles[-1]}）")

        # CSV + sidecar
        csv_path = TMP / "e2e_m5_features.csv"
        raw_bytes = csv_path.read_bytes()
        header = raw_bytes[3:].decode("utf-8").splitlines()[0]
        n_lines = len(raw_bytes.decode("utf-8").splitlines()) - 1
        check("CSV 已导出且带 BOM + 中文表头",
              raw_bytes[:3] == b"\xef\xbb\xbf"
              and header == "录制,被试,段序号,事件码,通道,特征,数值")
        check("CSV 行数与特征表一致", n_lines == len(table), f"（{n_lines} 行）")
        sidecar = json.loads((TMP / "e2e_m5_features.pipeline.json").read_text("utf-8"))
        # 注意特征链语义：bands=["alpha","beta"] 是**一个** bandpower 特征（双频段），
        # sidecar 记特征链（1 条）+ 每条完整 params——比数条目更强的可复现性断言
        feats = sidecar["features"]
        check("sidecar 含分段步骤/bandpower 双频段/45 文件",
              [s["step"] for s in sidecar["pipeline"]] == ["epoching"]
              and [f["feature"] for f in feats] == ["bandpower"]
              and feats[0]["params"]["bands"] == ["alpha", "beta"]
              and len(sidecar["recordings"]) == 45
              and sidecar["extra"]["batch"]["n_files"] == 46,
              f"（{len(sidecar['recordings'])} 文件 / batch n_files="
              f"{sidecar['extra']['batch']['n_files']}）")
        QTimer.singleShot(300, _stage2)

    # ------------------------------------------------ 阶段 2：中途取消
    def _stage2():
        dlg = _new_dialog()
        dlg._set_all_checked(True)
        dlg._dir.setText("")  # 不导出——本阶段只验取消
        dlg._cb_csv.setChecked(False)
        dlg._cb_h5.setChecked(False)
        dlg._on_run_clicked()
        shared["cancelled"] = False
        QTimer.singleShot(300, lambda: _stage2_cancel(tries=120))  # 等首个文件完成

    def _stage2_cancel(tries: int):
        dlg = shared["dlg"]
        done = dlg._progress._bar.value()
        if done < 1 and tries > 0:  # 至少 1 个文件完成后再取消（取消必有效）
            QTimer.singleShot(500, lambda: _stage2_cancel(tries - 1))
            return
        dlg._on_cancel_clicked()
        check("取消已请求（首个文件完成后）", True, f"（当时已完成 {done} 个）")
        QTimer.singleShot(500, lambda: _stage2_wait(tries=180))

    def _stage2_wait(tries: int):
        dlg = shared["dlg"]
        # 完成判据：取消按钮被 finish() 置灰 且 摘要行已填（都在进度视图上）
        finished = (not dlg._progress._btn_cancel.isEnabled()
                    and dlg._progress._summary_line.text())
        if not finished and tries > 0:
            QTimer.singleShot(1000, lambda: _stage2_wait(tries - 1))
            return
        payloads = shared["payloads"]
        if not payloads:
            check("取消批处理收尾", False, "（等待超时）")
            QTimer.singleShot(300, _stage3)
            return
        summary = payloads[0]["summary"]
        check("整批标记已取消", summary.cancelled)
        check("未开始的文件全为「已取消」（没跑完 45 个）",
              summary.n_cancelled >= 1 and summary.n_ok < 45,
              f"（成功 {summary.n_ok} / 取消 {summary.n_cancelled} / 失败 {summary.n_failed}）")
        QTimer.singleShot(300, _stage3)

    # ------------------------------------------------ 阶段 3：扩展格式 + 收尾
    def _stage3():
        from dataloadv.io.registry import READER_REGISTRY

        got = [rid for rid in ("blackrock", "openephys", "intan", "nwb")
               if rid in READER_REGISTRY]
        check("扩展格式读取器已注册（neo/nwb 在场）",
              len(got) == 4, f"（{got}）")
        _finish()

    def _finish():
        try:
            for i in range(win.tabs.count() - 1, 0, -1):
                win._on_tab_close(i)
            check("关闭全部 tab 后数据释放", not win.state.open_recordings)
            win.state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check("收尾清理", False, str(e))
        ok = all(c[1] for c in checks)
        print("\nE2E M5:", "ALL OK" if ok else "FAILED", flush=True)
        print(f"（导出产物在 {TMP}）", flush=True)
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
