"""M8.1 端到端验收：三锚定分段 + 时频观感修复（Y/配色/缓存）+ 第五视图.

自动化替代人工点按，走真实 UI 代码路径（面板 API 驱动）：

1. A01T（有事件数据走无事件路径也不受影响）：手动时刻锚点 [10,20,30.5,350]
   → 4 段「手动」（显式锚点零静默丢弃）
2. 蝶形 → 时频：热图纵向铺满（Y span < 60——上一视图残留被 autoRange 复位）
3. 配色切 jet：查找表首行变深蓝（b > r），levels 不受扰动
4. 切走再切回：缓存命中同步绘制（ImageItem 立即在，无「计算中」闪烁）
5. 清空步骤换固定窗滑窗 [-1,4]s：段数按样本域公式现算比对（≈538，不硬编码）
6. 第五视图单段浏览：全通道堆叠 + 段号跳段 + ▶ 翻段（滑窗模式=翻页滑动看数据）
7. 收尾：关闭全部 tab（保留首页）、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && QT_QPA_PLATFORM=offscreen python -u scripts/e2e_m81.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"

check: list[tuple[str, bool, str]] = []


def check_item(name: str, ok: bool, detail: str = "") -> None:
    check.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail, flush=True)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.widgets.epochs_preview import EpochsPreviewView

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框
    mw.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else "", flush=True))
    mw.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else "", flush=True))

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m81_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m81_一次性工作区")

    panel = win.pipeline_panel
    shared: dict = {}

    # ------------------------------------------------ 阶段 1：手动时刻锚点分段
    def _stage1():
        win._open_recording_async(str(GDF_2A))
        QTimer.singleShot(5000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or "A01T" not in browser.rec.meta.filename:
            check_item("打开 A01T", False, "（当前 tab 不是 A01T）")
            QTimer.singleShot(300, _finish)
            return
        if not browser._loaded_once:
            QTimer.singleShot(1000, _stage1b)
            return
        shared["browser"] = browser
        meta = browser.rec.meta
        shared["n_ch"] = len(meta.channel_names)
        shared["sfreq"] = meta.sfreq
        shared["n_times"] = int(round(meta.duration_s * meta.sfreq))
        # 手动锚点 [10, 20, 30.5, 350]：350+4 < 2690s 数据尾，全部合法
        panel.add_step("epoching", anchor="手动时刻",
                       anchors_s=[10.0, 20.0, 30.5, 350.0], tmin=-1.0, tmax=4.0)
        panel.start_preview()
        QTimer.singleShot(6000, _stage1c)

    def _stage1c(tries: int = 10):
        v = _find_preview()
        if v is None:
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage1c(tries - 1))
                return
            check_item("分段预览 tab 建立（手动时刻）", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        shared["view"] = v
        n = len(v.ctx.epochs)
        check_item("手动时刻：4 锚点 → 4 段（零静默丢弃）", n == 4, f"(实际 {n})")
        check_item("伪事件码 =「手动」", set(v.ctx.epochs.event_id) == {"手动"})
        QTimer.singleShot(300, _stage2)

    # ------------------------------------------------ 阶段 2：时频 Y 铺满（观感修复）
    def _stage2():
        v = shared["view"]
        v._view_combo.setCurrentIndex(1)  # ERP 蝶形：setYRange(-span, +span)
        by0, _ = v._plot.vb.viewRange()[1]
        check_item("蝶形 Y 范围含负半轴（残留源）", by0 < 0, f"(y0={by0:.1f})")
        v._view_combo.setCurrentIndex(3)  # 时频：后台 morlet
        QTimer.singleShot(300, lambda: _stage2b(40))

    def _stage2b(tries: int = 40):
        v = shared["view"]
        imgs = [it for it in v._plot.items if type(it).__name__ == "ImageItem"]
        if not imgs and tries > 0:
            QTimer.singleShot(300, lambda: _stage2b(tries - 1))
            return
        if not imgs:
            check_item("时频热图出现", False, "（等待超时）")
            QTimer.singleShot(300, _stage5)
            return
        fy0, fy1 = v._plot.vb.viewRange()[1]
        check_item("时频 Y 铺满（span < 60，残留时被压成一条）",
                   43 < fy1 - fy0 < 60, f"(span={fy1 - fy0:.1f}Hz)")
        QTimer.singleShot(300, _stage3)

    # ------------------------------------------------ 阶段 3：jet 配色只换查找表
    def _stage3():
        import numpy as np

        v = shared["view"]
        img = next(it for it in v._plot.items if type(it).__name__ == "ImageItem")
        levels_before = img.getLevels()
        lut_before = np.asarray(img.lut(n=256)).copy()  # img.lut 是可调用引用须显式取表
        v._cmap_combo.setCurrentText("jet")
        lut_after = np.asarray(img.lut(n=256))
        ok = (not np.array_equal(lut_after, lut_before)
              and lut_after[0, 2] > lut_after[0, 0]        # jet 首行深蓝（b>r）
              and np.array_equal(img.getLevels(), levels_before))
        check_item("切 jet：查找表换色 + levels 不扰动", ok)
        QTimer.singleShot(300, _stage4)

    # ------------------------------------------------ 阶段 4：切走切回缓存命中
    def _stage4():
        v = shared["view"]
        v._view_combo.setCurrentIndex(1)  # 切走（蝶形）
        v._view_combo.setCurrentIndex(3)  # 切回：应命中缓存**同步**绘制
        imgs = [it for it in v._plot.items if type(it).__name__ == "ImageItem"]
        # 走线程路径时此刻只有「计算中」提示、无 ImageItem——同步回调内立即有即缓存
        ok = bool(imgs) and "计算中" not in v._hint.text() and v._lut is not None
        check_item("切走切回：缓存命中秒显（零重算零线程）", ok)
        QTimer.singleShot(300, _stage5)

    # ------------------------------------------------ 阶段 5：固定窗滑窗（无事件路径）
    def _stage5():
        import numpy as np

        v = shared["view"]
        win._on_tab_close(win.tabs.indexOf(v))  # 关旧预览 tab，active 切回浏览器
        win.tabs.setCurrentWidget(shared["browser"])  # 预览作用于当前 tab 的数据
        # 样本域公式（epoching._fixed_anchors 同式）：first=-tmin_s、
        # last=n_times-1-tmax_s、step=窗长·fs（无重叠）
        tmin_s = int(round(-1.0 * shared["sfreq"]))
        tmax_s = int(round(4.0 * shared["sfreq"]))
        first = max(0, -tmin_s)
        step = int(round(5.0 * shared["sfreq"]))
        shared["want_fixed"] = len(np.arange(first, shared["n_times"] - tmax_s, step))
        panel._clear_steps()  # 「清空」按钮同一路径
        panel.add_step("epoching", anchor="固定窗滑窗", tmin=-1.0, tmax=4.0)
        panel.start_preview()
        QTimer.singleShot(6000, _stage5b)

    def _stage5b(tries: int = 10):
        v = _find_preview()
        if v is None:
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage5b(tries - 1))
                return
            check_item("滑窗分段预览 tab 建立", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        n = len(v.ctx.epochs)
        want = shared["want_fixed"]
        check_item(f"固定窗滑窗 [-1,4]s → {want} 段（样本域公式现算）",
                   n == want, f"(实际 {n}，预期 {want})")
        check_item("伪事件码 =「滑窗」", set(v.ctx.epochs.event_id) == {"滑窗"})
        shared["view"] = v
        QTimer.singleShot(300, _stage6)

    # ------------------------------------------------ 阶段 6：第五视图单段浏览
    def _stage6():
        v = shared["view"]
        v._view_combo.setCurrentIndex(4)  # 第五视图（append 尾部，索引 4）
        n_curves = len(v._plot.listDataItems())
        check_item(f"单段浏览：第 1 段全通道堆叠（{shared['n_ch']} 曲线）",
                   n_curves == shared["n_ch"], f"(实际 {n_curves})")
        check_item("段号控件启用 + 事件码=滑窗",
                   v._seg_spin.isEnabled() and "第 1 /" in v._hint.text()
                   and "滑窗" in v._hint.text(), f"({v._hint.text()})")
        v._seg_spin.setValue(3)
        ok3 = "第 3 /" in v._hint.text()
        v._btn_next.click()  # 3 → 4（◀▶ 与 ←→ 同入口 _nav_segment）
        QTimer.singleShot(200, _stage6b)
        shared["seg_ok"] = ok3

    def _stage6b():
        v = shared["view"]
        ok = shared.pop("seg_ok") and v._seg_spin.value() == 4 and "第 4 /" in v._hint.text()
        check_item("跳段/▶ 翻段重画（滑窗模式=翻页滑动看数据）", ok,
                   f"(段号 {v._seg_spin.value()})")
        QTimer.singleShot(300, _finish)

    # ------------------------------------------------ 收尾（照抄 e2e_m8）
    def _find_preview() -> EpochsPreviewView | None:
        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, EpochsPreviewView)]
        return views[-1] if views else None

    def _finish():
        try:
            for i in range(win.tabs.count() - 1, 0, -1):  # 保留首页（坑：删到 0 崩）
                win._on_tab_close(i)
            check_item("关闭全部 tab 后数据释放", not win.state.open_recordings)
            win.state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check_item("收尾清理", False, str(e))
        ok = all(c[1] for c in check)
        print("\nE2E M8.1:", "ALL OK" if ok else "FAILED", flush=True)
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in check if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
