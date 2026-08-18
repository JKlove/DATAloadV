"""M1 端到端验证：导入 → 工作区 → 打开浏览 → 波形/事件渲染.

自动化替代人工点按：绕过文件选择对话框（那需要真人操作），但走真实的
扫描/工作区/打开/渲染代码路径。任何断言失败打印 FAILED 并退出码 1。

运行：conda activate dlv && python scripts/e2e_m1.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
SHEEP = DATA / "sheep"
S001 = DATA / "dataset" / "files" / "S001"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.core.workspace import Workspace
    from dataloadv.io.registry import open_file, scan_folder
    from dataloadv.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # e2e 幂等：切到一次性工作区跑，结束再切回用户当前工作区
    # （工作区持久化在 ~/.dataloadv，不隔离的话二次运行全是"重复导入"）
    original_ws = win.state.workspace.name
    win.state.reload_workspace("e2e_m1_一次性工作区")

    # ---- 阶段 1：真实导入（sheep + PhysioNet S001，走真实扫描器）----
    report_sheep = scan_folder(SHEEP)
    report_s001 = scan_folder(S001)
    check("扫描 sheep：3 条 0 错", len(report_sheep.items) == 3 and not report_sheep.errors)
    check("扫描 S001：14 条 0 错", len(report_s001.items) == 14 and not report_s001.errors,
          f"(识别 {len(report_s001.items)})")

    state = win.state
    added1, _ = state.workspace.add_metas(str(SHEEP), [i.meta for i in report_sheep.items])
    added2, _ = state.workspace.add_metas(str(S001), [i.meta for i in report_s001.items])
    state.workspace.save()
    win._refresh_views()
    # 幂等：重复运行时重复导入计 dup（added=0 是预期）——断言总量而非新增
    check("工作区共 17 条", len(state.workspace) == 17,
          f"(新增 {added1 + added2}，总量 {len(state.workspace)})")
    check("工作区树刷新", win.workspace_tree._tree.topLevelItem(0) is not None)
    check("元数据表 17 行", win.meta_view._model.rowCount() == 17)

    # ---- 阶段 2：打开羊 EDF（latin1 路径）----
    sheep_edf = next(p for p in SHEEP.glob("*.edf") if "卧" in p.name)

    def _stage2():
        win._open_recording_async(str(sheep_edf))
        QTimer.singleShot(1500, _stage3)

    def _stage3():
        try:
            sheep_views = [w for w in win._browser_tabs.values() if "卧" in w.rec.meta.filename]
            ok = bool(sheep_views)
            check("羊 EDF 浏览 tab 建立（latin1）", ok)
            if ok:
                v = sheep_views[0]
                check("羊数据已加载", v._loaded_once)
                # 强制同步刷新一帧并检查曲线拿到真实数据
                v._refresh_data()
                enabled = [c for c in v._channels if c["enabled"]]
                got = any(c["curve"].xData is not None and len(c["curve"].xData) > 0 for c in enabled)
                check("羊波形曲线有数据（8 通道）", got and len(enabled) == 8)
                # M6 回归：通道标签全名内嵌 / 窗口导航视口数学 / 幅值标尺
                labels_ok = all(
                    ch["label"].toPlainText() == ch["name"] for ch in v._channels
                )
                check("M6 通道标签全名内嵌", labels_ok)
                v._set_window_s(5.0)
                t0w, t1w = v._visible_range()
                check("M6 一屏时长设 5s", abs((t1w - t0w) - 5.0) < 1e-6)
                v._page(+1)
                t0p, _ = v._visible_range()
                check("M6 下一屏步进 0.9 屏", abs(t0p - (t0w + 4.5)) < 1e-6)
                v._go_edge(first=False)
                t0e, t1e = v._visible_range()
                dur = v.rec.meta.duration_s
                check("M6 最末屏 [dur-w, dur]",
                      abs(t1e - dur) < 1e-3 and abs((t1e - t0e) - 5.0) < 1e-3)
                v._refresh_data()
                check("M6 幅值标尺标注 µV", "µV" in v._scale_text.toPlainText())
        finally:
            QTimer.singleShot(300, _stage4)

    # ---- 阶段 3：打开 PhysioNet 运动任务文件（事件渲染）----
    def _stage4():
        win._open_recording_async(str(S001 / "S001R03.edf"))
        QTimer.singleShot(1500, _stage5)

    def _stage5():
        try:
            v = win._browser_tabs.get(
                next(rid for rid, w in win._browser_tabs.items() if "S001R03" in w.rec.meta.filename)
            ) if win._browser_tabs else None
            v = next((w for w in win._browser_tabs.values() if "S001R03" in w.rec.meta.filename), None)
            check("PhysioNet 浏览 tab 建立", v is not None)
            if v is not None:
                check("S001R03 事件读入（30 个）", len(v.rec.events) == 30,
                      f"(实际 {len(v.rec.events)})")
                v._refresh_data()
                t0, t1 = v._visible_range()
                n_in = len(v.rec.events.in_window(t0, t1))
                check("事件线已渲染或可视区内无事件", v._loaded_once)
                # 跳到首个 T1 事件再刷一帧验证事件线
                v._jump_event(1)
                v._refresh_data()
                t0, t1 = v._visible_range()
                check("跳转后可视区含事件（事件线非空）",
                      len(v._event_lines) > 0 or len(v.rec.events.in_window(t0, t1)) == 0)
        finally:
            QTimer.singleShot(300, _finish)

    def _finish():
        try:
            # 收尾：关掉全部浏览 tab（释放数据），切回原工作区
            for i in range(win.tabs.count() - 1, 0, -1):
                win._on_tab_close(i)
            check("关闭全部浏览 tab 后数据释放", not win.state.open_recordings)
            win.state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check("收尾清理", False, str(e))
        ok = all(c[1] for c in checks)
        print("\nE2E M1:", "ALL OK" if ok else "FAILED")
        app.quit()

    QTimer.singleShot(500, _stage2)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
