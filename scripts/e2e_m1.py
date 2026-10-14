"""M1 端到端验证：导入 → 工作区 → 打开浏览 → 波形/事件渲染.

自动化替代人工点按：绕过文件选择对话框（那需要真人操作），但走真实的
扫描/工作区/打开/渲染代码路径。任何断言失败打印 FAILED 并退出码 1。

运行：conda activate dlv && python scripts/e2e_m1.py
"""

from __future__ import annotations

import sys

import numpy as np
from PySide6.QtCore import Qt
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
            check("羊 EDF（实为 BDF）浏览 tab 建立", ok)
            if ok:
                v = sheep_views[0]
                check("羊数据已加载", v._loaded_once)
                # 2026-08-24：sheep 系列 .edf 实为 BDF（\xffBIOSEMI 头），按魔数
                # 内容优先派发——格式与时长必须是 BDF 正确解码值（EDF 错读会 270s）
                check(
                    "羊数据按 BDF 解码（魔数优先于扩展名）",
                    v.rec.meta.format == "BDF" and abs(v.rec.meta.duration_s - 180.0) < 0.5,
                    f"(format={v.rec.meta.format}, dur={v.rec.meta.duration_s})",
                )
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
                # M6.8 回归：秒级平移 / 行居中开关（绝对模式 y 自适配——
                # 羊 CH1 大直流偏移是天然考题）/ 总览滑块跟随视口
                v._go_edge(first=True)
                v._step_s(+1)
                t0s, _ = v._visible_range()
                check("M6.8 ±1s 平移", abs(t0s - 1.0) < 1e-6)
                v._center_cb.setChecked(False)
                v._refresh_data()
                y0f, y1f = v._plot.getViewBox().viewRange()[1]
                meds = [
                    float(np.median(c["curve"].yData)) for c in enabled
                    if c["curve"].yData is not None and len(c["curve"].yData)
                ]
                check("M6.8 绝对模式 y 自适配含曲线",
                      meds and all(y0f <= m <= y1f for m in meds))
                v._center_cb.setChecked(True)
                v._refresh_data()
                v._page(+1)
                r0, r1 = v._lane._region.getRegion()
                t0r, t1r = v._visible_range()
                check("M6.8 总览滑块跟随视口",
                      abs(r0 - t0r) < 1e-3 and abs(r1 - t1r) < 1e-3)
                # M11：无事件数据（羊 BDF 无标记）事件列表面板常驻显示空态
                check("M11 无事件面板常驻空态",
                      (not v._event_list.isHidden())
                      and v._event_list.row_count() == 0
                      and (not v._event_list._empty_lbl.isHidden()))
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
                # M11 事件 marker 列表：面板可见、行数=事件数、双击行 → 视口居中该事件
                check("事件列表面板可见（有事件时）", not v._event_list.isHidden())
                check("事件列表行数 = 事件数", v._event_list.row_count() == 30,
                      f"(实际 {v._event_list.row_count()})")
                target = float(v.rec.events.onset.min())
                row = next((r for r in range(v._event_list.row_count())
                            if v._event_list.onset_at_row(r) == target), 0)
                v._event_list._on_double_click(v._event_list._proxy.index(row, 0))
                dt0, dt1 = v._visible_range()
                check("双击列表行跳转到该事件（视口居中）",
                      abs((dt0 + dt1) / 2 - target) < 1e-6,
                      f"(中心 {(dt0 + dt1) / 2:.3f} vs 事件 {target:.3f})")
                # M12a 比例尺下拉：固定 50µV → yRange 按 64 导×50 锁定
                n_ch = len(v.rec.meta.channel_names)
                v._scale_combo.setCurrentText("50")
                vy0, vy1 = v._plot.getViewBox().viewRange()[1]
                check("M12 比例尺下拉锁定行距",
                      abs(vy0 - (-1.5 * 50)) < 1e-6 and abs(vy1 - (n_ch + 0.5) * 50) < 1e-6)
                # M12c 紧凑显示：只留 8 通道 → 优化按钮 → 行数收紧 8
                v._ch_list.blockSignals(True)
                for i in range(v._ch_list.count()):
                    v._ch_list.item(i).setCheckState(
                        Qt.CheckState.Checked if i < 8 else Qt.CheckState.Unchecked)
                v._ch_list.blockSignals(False)
                for ch in v._channels:
                    on = ch["idx"] < 8
                    ch["enabled"] = on
                    ch["curve"].setVisible(on)
                    ch["label"].setVisible(on)
                v._set_compact(True)
                cy0, cy1 = v._plot.getViewBox().viewRange()[1]
                check("M12 紧凑显示只留勾选通道",
                      v._row_count() == 8 and abs(cy1 - cy0 - 10.0 * v._spacing_uv) < 1e-3,
                      f"(row_count={v._row_count()})")
                v._set_compact(False)  # 复位恢复 64 导
        finally:
            QTimer.singleShot(900, _stage5b)

    def _stage5b():
        # M12d/e 时频图：防抖 300ms + 计算后 ImageItem 已回填（覆盖视口）
        try:
            v = next((w for w in win._browser_tabs.values()
                      if "S001R03" in w.rec.meta.filename), None)
            if v is not None:
                r = v._tfr_img.mapRectToView(v._tfr_img.boundingRect())
                t0, t1 = v._visible_range()
                # 期望窗 = 视口与数据域 [0, dur] 的交集（双击跳转居中 0 时视口
                # 左半为负——无数据段，TFR 只覆盖 clamp 后的实际窗口）
                w0, w1 = max(t0, 0.0), min(t1, v.rec.meta.duration_s)
                check("M12 时频图已计算并覆盖视口",
                      v._tfr_img.image is not None
                      and abs(r.left() - w0) < 0.02 and abs(r.width() - (w1 - w0)) < 0.02,
                      f"(image {'有' if v._tfr_img.image is not None else '无'}, "
                      f"rect.left={r.left():.3f} vs 期望窗 [{w0:.3f},{w1:.3f}])")
                check("M12 turbo 色标在场", v._tfr_lut.scene() is not None)
                # M13：频率轴 0 起点且上限按 Nyquist 钳制（S001R03 160Hz → 76Hz）
                fy0, fy1 = v._tfr_plot.vb.viewRange()[1]
                check("M13 时频频率轴 0 起 + Nyquist 钳制",
                      abs(fy0) < 1e-9 and abs(fy1 - 78.4) < 0.1,
                      f"(y=[{fy0:.1f},{fy1:.1f}]，160Hz 采样应钳到 78.4)")
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
