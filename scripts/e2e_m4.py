"""M4 端到端验收：管线+特征计算 → 特征结果 tab → CSV/HDF5/分段导出 → sidecar.

自动化替代人工点按，走真实 UI 代码路径（面板 API 驱动）：

1. 羊 EDF：打开 → 带通+陷波+时间窗裁剪(前 30s) → 三特征全开 → 计算特征
   → 特征结果 tab 建立、行数与曲线数正确
2. 视口预填（四层决策第④层）：「用当前显示窗口」→ crop 步骤出现在链上、
   时间窗值在数据范围内
3. 导出（走视图按钮路径，QFileDialog 被 patch）：CSV 读回 BOM + 中文表头
   + 行数一致（M4 验收口径）；sidecar 合法且含管线步骤
4. 2a GDF A01T：分段 → 逐段频带功率 → 288 段断言；分段 HDF5/FIF 导出回读
   形状与段数一致（M4 验收口径）
5. 收尾：关闭全部 tab、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && python scripts/e2e_m4.py
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
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"
TMP = Path(tempfile.mkdtemp(prefix="e2e_m4_"))

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.export import epochs_io, features_io
    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.widgets import feature_table as ft_mod
    from dataloadv.ui.widgets import pipeline_panel as pp_mod
    from dataloadv.ui.widgets.feature_table import FeatureTableView

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框——**逐模块** patch
    # （QMessageBox 是各模块 from-import 的独立引用，只 patch 一处不生效）
    for mod in (mw, ft_mod, pp_mod):
        mod.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else ""))
        mod.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else ""))
        mod.QMessageBox.information = staticmethod(lambda *a, **k: print("[patched info]", a[-1] if a else ""))
    # 导出路径固定到临时目录（走视图的完整导出代码路径，只是不弹文件对话框）
    def _save_name(*a, **_k):
        default = a[2] if len(a) > 2 else "out.bin"
        return str(TMP / default), ""

    ft_mod.QFileDialog.getSaveFileName = staticmethod(_save_name)

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m4_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m4_一次性工作区")

    panel = win.pipeline_panel
    shared: dict = {}  # 跨 QTimer 闭包传引用

    # ------------------------------------------------- 阶段 1：羊 EDF 管线+特征
    def _stage1():
        win._open_recording_async(str(SHEEP_EDF))
        QTimer.singleShot(2000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or not browser._loaded_once:
            QTimer.singleShot(800, _stage1b)
            return
        check("羊 EDF 浏览 tab 就绪", True)
        shared["browser"] = browser
        shared["n_data_ch"] = len(browser.rec.meta.channel_names)
        panel.add_step("bandpass", l_freq=1.0, h_freq=40.0)
        panel.add_step("notch", freqs=[50.0])
        panel.add_step("crop", tmin=0.0, tmax=30.0)
        panel.add_feature("bandpower")
        panel.add_feature("timedomain")
        panel.add_feature("welch_psd")
        check("面板加入 3 步骤 + 3 特征",
              len(panel._steps) == 3 and len(panel._features) == 3)
        panel.start_features()
        QTimer.singleShot(3500, _stage1c)

    def _stage1c(tries: int = 10):
        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, FeatureTableView)]
        if not views:
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage1c(tries - 1))
                return
            check("特征结果 tab 建立", False, "（等待超时——见上方 [patched] 错误信息）")
            QTimer.singleShot(300, _finish)
            return
        check("特征结果 tab 建立", True)
        v = views[0]
        shared["view"] = v
        table = v._table
        n_ch = shared["n_data_ch"]
        want = n_ch * (5 + 8)  # 8 数据通道 × (5 标准频段 + 8 时域统计量)
        check("特征行数正确（长表）", len(table) == want,
              f"(实际 {len(table)}，预期 {want} = {n_ch} 通道 × 13 特征)")
        # M8.3：留空=逐通道各一条（通道平均语义已废）——通道集合与数据通道一致
        n_curve_ch = len({c["channel"] for c in table.curves})
        check("PSD 曲线逐通道各一条", n_curve_ch == n_ch and len(table.curves) == n_ch,
              f"(实际 {len(table.curves)} 条 / {n_curve_ch} 个通道，预期 {n_ch})")
        # 陷波断言复用 M3 口径（M8.3 改全曲线）：处理后各曲线在 50Hz 处的谱值
        # 应低于自身 10Hz 谱值的 5 倍——全曲线比值取中位数（羊数据工频在 50Hz）
        import numpy as np

        ratios = []
        for c in table.curves:
            i50 = abs(c["freqs"] - 50.0).argmin()
            ialpha = abs(c["freqs"] - 10.0).argmin()
            ratios.append(float(c["psd"][i50]) / max(float(c["psd"][ialpha]), 1e-30))
        med = float(np.median(ratios))
        check("处理后 PSD：50Hz 不再是全局尖峰", med < 5.0,
              f"(50Hz/10Hz 比值中位数 {med:.2f}，共 {len(ratios)} 条曲线)")
        QTimer.singleShot(300, _stage2)

    # ------------------------------------------------- 阶段 2：视口预填（第④层）
    def _stage2():
        win.tabs.setCurrentWidget(shared["browser"])
        panel._clear_steps()
        panel._features.clear()
        panel._feat_list.clear()  # 清空特征区（A01T 阶段重新组链）
        # 把视口缩到一段真实范围——验证预填的是视口而非全长
        browser = shared["browser"]
        browser._center_at(browser.rec.meta.duration_s / 2.0, width_s=20.0)
        browser._refresh_data()
        t0, t1 = browser._visible_range()  # 预期值（clamp/取整前的原始视口）
        panel.use_viewport_window()
        crops = [e for e in panel._steps if e["step"] == "crop"]
        ok = bool(crops)
        check("「用当前显示窗口」自动加 crop 步骤", ok)
        if ok:
            tmin, tmax = crops[0]["params"].tmin, crops[0]["params"].tmax
            duration = browser.rec.meta.duration_s
            want0, want1 = max(0.0, round(t0, 2)), min(duration, round(t1, 2))
            check("crop 时间窗 = 当前视口（可见可改、不隐式绑定）",
                  tmin == want0 and tmax == want1 and (tmax - tmin) < duration,
                  f"([{tmin}, {tmax}] s / 视口 [{want0:.1f}, {want1:.1f}] / 全长 {duration:.0f} s)")
        panel._clear_steps()
        QTimer.singleShot(300, _stage3)

    # ------------------------------------------------- 阶段 3：导出（CSV + sidecar）
    def _stage3():
        v = shared["view"]
        v._btn_csv.click()  # QFileDialog 已 patch → 固定路径 → worker 写盘
        QTimer.singleShot(1500, _stage3b)

    def _stage3b(tries: int = 10):
        csv_path = TMP / "features.csv"
        if not csv_path.exists():
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage3b(tries - 1))
                return
            check("CSV 已导出且带 BOM", False, "（等待导出超时）")
            QTimer.singleShot(300, _finish)
            return
        raw_bytes = csv_path.read_bytes()
        check("CSV 已导出且带 BOM", raw_bytes[:3] == b"\xef\xbb\xbf")
        header = raw_bytes[3:].decode("utf-8").splitlines()[0]
        check("CSV 中文表头（Excel 可直接打开）",
              header == "录制,被试,段序号,事件码,通道,特征,数值", f"({header})")
        n_lines = len(raw_bytes.decode("utf-8").splitlines()) - 1
        check("CSV 行数与特征表一致", n_lines == shared["view"]._table.__len__(),
              f"({n_lines} 行)")
        sidecar = TMP / "features.pipeline.json"
        ok = sidecar.exists()
        check("sidecar .pipeline.json 已写出", ok)
        if ok:
            doc = json.loads(sidecar.read_text(encoding="utf-8"))
            steps = [s["step"] for s in doc["pipeline"]]
            check("sidecar 含完整管线（bandpass/notch/crop）",
                  steps == ["bandpass", "notch", "crop"], f"({steps})")
            check("sidecar 含特征与文件清单",
                  len(doc["features"]) == 3 and doc["recordings"] ==
                  [shared["browser"].rec.meta.filename])
        QTimer.singleShot(300, _stage4)

    # ------------------------------------------------- 阶段 4：A01T 分段 + 导出
    def _stage4():
        win._open_recording_async(str(GDF_2A))
        QTimer.singleShot(5000, _stage4b)

    def _stage4b():
        browser = win._get_active_browser()
        if browser is None or "A01T" not in browser.rec.meta.filename:
            check("打开 A01T", False, "（当前 tab 不是 A01T）")
            QTimer.singleShot(300, _finish)
            return
        if not browser._loaded_once:
            QTimer.singleShot(1000, _stage4b)
            return
        shared["a01t_ch"] = len(browser.rec.meta.channel_names)
        panel.add_step("epoching", event_codes=["769", "770", "771", "772"],
                       tmin=-1.0, tmax=4.0)
        panel.add_feature("bandpower", bands=["alpha", "beta"])
        panel.start_features()
        QTimer.singleShot(8000, _stage4c)

    def _stage4c(tries: int = 10):
        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, FeatureTableView)]
        # 取**最新**的特征 tab（阶段 1 羊的 tab 仍开着），并校验确是 A01T
        v = views[-1] if views else None
        is_a01t = v is not None and "A01T" in (v._table.recording_names() or [""])[0]
        if not is_a01t:
            if tries > 0:
                QTimer.singleShot(1000, lambda: _stage4c(tries - 1))
                return
            check("A01T 特征 tab 建立", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        check("A01T 特征 tab 建立", True)
        # mne 读 2a GDF 时 25 通道（22 EEG + 3 EOG）全部标为 eeg 类型——EOG
        # 无法按类型白名单自动排除（M4 实证结论），特征默认取全部 25 数据通道；
        # 要排除 EOG 可在特征参数里指定 22 个通道名
        n_ch = shared["a01t_ch"]
        want = 288 * n_ch * 2
        table = v._table
        check("逐段特征行数 = 288 段 × 25 通道 × 2 频段", len(table) == want,
              f"(实际 {len(table)}，预期 {want})")
        codes = set(table.df["event_code"].dropna().astype(str))
        check("事件码逐段带入（769-772）",
              codes == {"769", "770", "771", "772"}, f"({sorted(codes)})")
        ctx = v._ctx
        # 分段导出：HDF5 与 FIF 各一份（直接走 export 层；按钮菜单路径已被
        # 阶段 3 的按钮流程覆盖）
        h5 = epochs_io.export_epochs(ctx.epochs, TMP / "a01t.h5")
        back = epochs_io.read_epochs_hdf5(h5)
        check("分段 HDF5 回读形状一致",
              back["data"].shape == ctx.epochs.get_data().shape,
              f"({back['data'].shape})")
        import mne
        fif = epochs_io.export_epochs(ctx.epochs, TMP / "a01t.h5", fmt="fif")
        rt = mne.read_epochs(fif, verbose="ERROR")
        check("分段 FIF 回读段数 = 288", len(rt) == 288, f"(实际 {len(rt)})")
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
        print("\nE2E M4:", "ALL OK" if ok else "FAILED")
        print(f"（导出产物在 {TMP}）")
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
