"""M3 端到端验收：处理管线面板 → 预览 → PSD 对比 → 分段预览.

自动化替代人工点按，走真实 UI 代码路径（面板 API 驱动，而非绕过面板直接调 proc）：

1. 羊 EDF：打开 → 带通+陷波+重参考 三步预览 → 预览 tab 出现且曲线有数据
   → 数值断言 50Hz PSD 被压制（M3 验收口径）
2. 坏道联动：浏览器右键标记（API 等价 toggle_bad）→ 添加坏导联步骤
   → 默认参数带入标记
3. 2a GDF A01T：事件分段预览 → 分段总数 = 288（M3 验收口径）
4. 收尾：关闭全部 tab、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && python scripts/e2e_m3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
SHEEP_EDF = next((p for p in (DATA / "sheep").glob("*.edf") if "卧" in p.name), None)
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.features.spectral import mean_welch
    from dataloadv.proc import STEP_REGISTRY
    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.widgets.epochs_preview import EpochsPreviewView
    from dataloadv.ui.widgets.signal_browser import SignalBrowserView

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框
    mw.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else ""))
    mw.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else ""))

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m3_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m3_一次性工作区")

    panel = win.pipeline_panel
    shared: dict = {}  # 跨 QTimer 闭包传引用（原始浏览器等）

    # ---------------------------------------------------------------- 阶段 1：羊 EDF 三步预览
    def _stage1():
        win._open_recording_async(str(SHEEP_EDF))
        QTimer.singleShot(2000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or not browser._loaded_once:
            QTimer.singleShot(800, _stage1b)
            return
        try:
            check("羊 EDF 浏览 tab 就绪", True)
            shared["original"] = browser  # 预览后当前 tab 会切到预览，原始引用先存住
            # 组装三步管线（面板公开 API：overrides 先于表单合入，不会被表单冲掉）
            panel.add_step("bandpass", l_freq=1.0, h_freq=40.0)
            panel.add_step("notch", freqs=[50.0])
            panel.add_step("reref")
            check("面板加入 3 个步骤", len(panel._steps) == 3 and panel._list.count() == 3)
            check("参数表单自动生成（选中步骤）", panel._form is not None)

            # 坏道联动：标记 → 添加坏导联步骤 → 默认带入
            browser.toggle_bad(browser.rec.meta.channel_names[0])
            panel.add_step("bads")
            channels = panel._steps[-1]["params"].channels
            check("坏道标记联动 BadChannelsStep 默认参数",
                  browser.rec.meta.channel_names[0] in channels)
            panel._remove_step()  # 坏道步骤不进本条预览（插值无 montage 会失败，mark 也无需）
            browser.toggle_bad(browser.rec.meta.channel_names[0])  # 还原标记

            panel.start_preview()
            QTimer.singleShot(2500, _stage1c)
        finally:
            pass

    def _stage1c():
        previews = [w for w in win._browser_tabs.values() if w.rec.meta.format == "预览"]
        ok = bool(previews) and previews[0]._loaded_once
        check("预览 tab 建立（处理副本）", bool(previews))
        if not ok:
            QTimer.singleShot(800, _stage1c)
            return
        v = previews[0]
        v._refresh_data()
        enabled = [c for c in v._channels if c["enabled"]]
        got = any(c["curve"].xData is not None and len(c["curve"].xData) > 0 for c in enabled)
        check("预览曲线有真实数据（8 通道）", got and len(enabled) == 8)

        # 数值验收：50Hz PSD 压制（原始 vs 处理副本，Welch 通道平均）
        raw_before = shared["original"].rec.raw  # 预览后 active 已是预览 tab，须用原引用
        f, p_before = mean_welch(raw_before.copy().crop(0, 120.0))
        _, p_after = mean_welch(v.rec.raw.copy().crop(0, 120.0))
        i50 = abs(f - 50.0).argmin()
        ratio = p_after[i50] / p_before[i50]
        check("羊数据 50Hz 工频被压制（PSD 比值 < 0.1）", ratio < 0.1, f"(比值 {ratio:.4f})")
        QTimer.singleShot(300, _stage2)

    # ---------------------------------------------------------------- 阶段 2：2a GDF 分段预览
    def _stage2():
        panel._clear_steps()
        win._open_recording_async(str(GDF_2A))
        QTimer.singleShot(5000, _stage2b)

    def _stage2b():
        browser = win._get_active_browser()
        if browser is None or "A01T" not in browser.rec.meta.filename:
            check("打开 A01T", False, "（当前 tab 不是 A01T）")
            QTimer.singleShot(300, _finish)
            return
        if not browser._loaded_once:
            QTimer.singleShot(1000, _stage2b)
            return
        panel.add_step("epoching", event_codes=["769", "770", "771", "772"],
                       tmin=-1.0, tmax=4.0)
        panel.start_preview()
        QTimer.singleShot(6000, _stage2c)

    def _stage2c():
        try:
            epochs_views = [win.tabs.widget(i) for i in range(win.tabs.count())]
            epochs_views = [w for w in epochs_views if isinstance(w, EpochsPreviewView)]
            ok = bool(epochs_views)
            check("分段预览 tab 建立", ok)
            if ok:
                n = len(epochs_views[0].ctx.epochs)
                check("A01T 分段总数 = 288", n == 288, f"(实际 {n})")
        finally:
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
        print("\nE2E M3:", "ALL OK" if ok else "FAILED")
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
