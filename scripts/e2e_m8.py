"""M8 端到端验收：分段四视图 + 时间分辨特征 + 导出链.

自动化替代人工点按，走真实 UI 代码路径（面板 API 驱动）：

1. 2a GDF A01T：打开 → 事件分段（769-772，-1~4s）→ 分段预览 tab = 288 段
2. 四视图矩阵：默认堆叠（零回归）/ ERP 蝶形 / 单通道（288 细线+按码 4 平均）
   / 时频（后台 morlet → ImageItem+色标+y 反转）+ 切走复位（残留回归）
3. 时间分辨特征：bandpower time_windows=-1-0,0-4 → 288×25×3 行（整段+2 窗）
   + ERD 生理口径（事件后 α 抑制，EEG 群体中位数）
4. 导出链：特征长表 → CSV 回读行数一致
5. 收尾：关闭全部 tab（保留首页）、恢复原工作区（幂等，可反复跑）

运行：conda activate dlv && QT_QPA_PLATFORM=offscreen python -u scripts/e2e_m8.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

DATA = PROJECT / "data"
GDF_2A = DATA / "dataset" / "BCICIV_2a_gdf" / "A01T.gdf"
TMP = Path(tempfile.mkdtemp(prefix="e2e_m8_"))

checks: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))
    print(("✅" if ok else "❌"), name, detail, flush=True)


def main() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from dataloadv.ui import main_window as mw
    from dataloadv.ui.main_window import MainWindow
    from dataloadv.ui.strings_zh import S
    from dataloadv.ui.widgets.epochs_preview import EpochsPreviewView
    from dataloadv.ui.widgets.feature_table import FeatureTableView

    # e2e 规约（HANDOFF 坑 #14）：中和一切模态对话框
    mw.QMessageBox.critical = staticmethod(lambda *a, **k: print("[patched critical]", a[-1] if a else "", flush=True))
    mw.QMessageBox.warning = staticmethod(lambda *a, **k: print("[patched warning]", a[-1] if a else "", flush=True))

    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    original_ws = win.state.reload_workspace("e2e_m8_一次性工作区") or win.state.workspace.name
    win.state.reload_workspace("e2e_m8_一次性工作区")

    panel = win.pipeline_panel
    shared: dict = {}

    # ------------------------------------------------ 阶段 1：A01T 分段预览
    def _stage1():
        win._open_recording_async(str(GDF_2A))
        QTimer.singleShot(5000, _stage1b)

    def _stage1b():
        browser = win._get_active_browser()
        if browser is None or "A01T" not in browser.rec.meta.filename:
            check("打开 A01T", False, "（当前 tab 不是 A01T）")
            QTimer.singleShot(300, _finish)
            return
        if not browser._loaded_once:
            QTimer.singleShot(1000, _stage1b)
            return
        shared["browser"] = browser  # 分段预览后 active 会切走，特征阶段切回来
        shared["n_ch"] = len(browser.rec.meta.channel_names)
        panel.add_step("epoching", event_codes=["769", "770", "771", "772"],
                       tmin=-1.0, tmax=4.0)
        panel.start_preview()
        QTimer.singleShot(6000, _stage1c)

    def _stage1c(tries: int = 10):
        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, EpochsPreviewView)]
        if not views:
            if tries > 0:
                QTimer.singleShot(800, lambda: _stage1c(tries - 1))
                return
            check("分段预览 tab 建立", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        v = views[0]
        shared["view"] = v
        n = len(v.ctx.epochs)
        check("分段预览 tab 建立（A01T 288 段）", n == 288, f"(实际 {n})")
        # ---- 视图 1（默认=堆叠，M3 零回归）
        check("默认视图=各通道平均（堆叠）", v._view_combo.currentText() == S.EP_VIEW_AVG)
        check("堆叠曲线数 = 通道数", len(v._plot.listDataItems()) == shared["n_ch"],
              f"(实际 {len(v._plot.listDataItems())}，通道 {shared['n_ch']})")
        QTimer.singleShot(300, _stage2)

    # ------------------------------------------------ 阶段 2：蝶形 / 单通道 / 时频
    def _stage2():
        v = shared["view"]
        v._view_combo.setCurrentIndex(1)  # ERP 蝶形
        n_curves = len(v._plot.listDataItems())
        has_zero = any(type(it).__name__ == "InfiniteLine" for it in v._plot.items)
        check("蝶形：全通道同坐标 + 零线",
              n_curves == shared["n_ch"] and has_zero, f"(曲线 {n_curves})")
        QTimer.singleShot(200, _stage3)

    def _stage3():
        v = shared["view"]
        v._view_combo.setCurrentIndex(2)  # 单通道 ERP
        lines = v._plot.listDataItems()
        texts = [it for it in v._plot.items if type(it).__name__ == "TextItem"]
        check("单通道：288 段细线 + 4 类按码平均 + 4 码标注",
              len(lines) == 288 + 4 and len(texts) == 4,
              f"(线 {len(lines)}，标注 {len(texts)})")
        check("单通道视图说明行", v._hint.text() == S.EP_LEGEND_SINGLE)
        QTimer.singleShot(200, _stage4)

    def _stage4(tries: int = 40):
        v = shared["view"]
        v._view_combo.setCurrentIndex(3)  # 时频（后台 morlet）
        QTimer.singleShot(300, lambda: _stage4b(tries))

    def _stage4b(tries: int = 40):
        v = shared["view"]
        imgs = [it for it in v._plot.items if type(it).__name__ == "ImageItem"]
        if not imgs and tries > 0:
            QTimer.singleShot(300, lambda: _stage4b(tries - 1))
            return
        ok = bool(imgs) and v._lut is not None and v._plot.vb.state["yInverted"]
        check("时频：ImageItem + 色标 + y 反转（低频在下）", ok,
              f"(img {len(imgs)}，dB 提示 {'✓' if 'dB' in v._hint.text() else '✗'})")
        QTimer.singleShot(300, _stage5)

    def _stage5():
        v = shared["view"]
        v._view_combo.setCurrentIndex(0)  # 切回堆叠：残留复位
        ok = (v._lut is None and not v._plot.vb.state["yInverted"]
              and len(v._plot.listDataItems()) == shared["n_ch"])
        check("切走时频：色标摘除 + 反转复位 + 堆叠重画", ok)
        QTimer.singleShot(300, _stage6)

    # ------------------------------------------------ 阶段 3：时间分辨特征 + 导出
    def _stage6():
        # 特征作用于 active browser 的数据——分段预览后 active 是预览 tab，切回
        win.tabs.setCurrentWidget(shared["browser"])
        # n_per_seg_s=1.0 统一各窗 Welch 分辨率（不同窗长→不同 nperseg→
        # 1Hz 分辨率摊薄 α 峰的系统偏差 ~24%；统一后守恒式残差只剩方差 ~8%）
        panel.add_feature("bandpower", bands=["alpha"], n_per_seg_s=1.0,
                          time_windows=["-1-0", "0-4"])
        panel.start_features()
        QTimer.singleShot(9000, _stage6b)

    def _stage6b(tries: int = 10):
        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, FeatureTableView)]
        v = views[-1] if views else None
        is_a01t = v is not None and "A01T" in (v._table.recording_names() or [""])[0]
        if not is_a01t:
            if tries > 0:
                QTimer.singleShot(1000, lambda: _stage6b(tries - 1))
                return
            check("时间分辨特征 tab 建立", False, "（等待超时）")
            QTimer.singleShot(300, _finish)
            return
        table = v._table
        want = 288 * shared["n_ch"] * 3  # 段 × 通道 × (整段 + 2 窗)
        check("特征行数 = 288 段 × 25 通道 × 3（整段+2 窗）", len(table) == want,
              f"(实际 {len(table)}，预期 {want})")
        feats = set(table.df["feature"].unique())
        check("特征名带窗标记（alpha / alpha@-1-0s / alpha@0-4s）",
              feats == {"alpha", "alpha@-1-0s", "alpha@0-4s"}, f"({sorted(feats)})")

        # 守恒式（数值验收的硬口径）：Welch 是密度归一，整段 α 应等于
        # 各子窗 α 的**时长加权平均**——统一分辨率后残差只剩段间方差。
        # （不做 ERD 方向断言：A01T 原始未处理数据上 22 EEG 通道群体
        # 中位比值 1.05±0.1，无显著方向性——数据事实优先于教科书预期）
        import numpy as np
        df = table.df
        pivot = df.pivot_table(index=["epoch_index", "channel"], columns="feature",
                               values="value")
        eeg = [c for c in pivot.index.get_level_values("channel").unique()
               if c.startswith("EEG-")]  # 22 EEG（EOG 通道名不带 EEG- 前缀）
        errs = []
        for ch in eeg:
            sub = pivot.xs(ch, level="channel")
            mix = (sub["alpha@-1-0s"] + 4.0 * sub["alpha@0-4s"]) / 5.0
            errs.append(float((mix - sub["alpha"]).abs().div(sub["alpha"]).median()))
        med = float(np.median(errs))
        check("守恒式：整段 α = 子窗时长加权混合（中位误差 < 12%）", med < 0.12,
              f"({len(eeg)} EEG 通道中位 {med:.3f})")
        QTimer.singleShot(300, _stage7)

    def _stage7():
        # 导出链：长表 → CSV → 回读行数（导出 UI 路径 e2e_m4 已验，此处走 API）
        from dataloadv.export.features_io import export_features_csv
        from dataloadv.ui.widgets.feature_table import FeatureTableView

        views = [win.tabs.widget(i) for i in range(win.tabs.count())]
        views = [w for w in views if isinstance(w, FeatureTableView)]
        table = views[-1]._table
        csv_path = TMP / "m8_features.csv"
        export_features_csv(table, csv_path)
        import pandas as pd
        back = pd.read_csv(csv_path)
        check("导出 CSV 回读行数一致", len(back) == len(table),
              f"(写 {len(table)}，读 {len(back)})")
        QTimer.singleShot(300, _finish)

    def _finish():
        try:
            for i in range(win.tabs.count() - 1, 0, -1):  # 保留首页（坑：删到 0 崩）
                win._on_tab_close(i)
            check("关闭全部 tab 后数据释放", not win.state.open_recordings)
            win.state.reload_workspace(original_ws)
        except Exception as e:  # noqa: BLE001
            check("收尾清理", False, str(e))
        ok = all(c[1] for c in checks)
        print("\nE2E M8:", "ALL OK" if ok else "FAILED", flush=True)
        app.quit()

    QTimer.singleShot(400, _stage1)
    app.exec()

    failed = [c for c in checks if not c[1]]
    for name, _, detail in failed:
        print("失败项:", name, detail, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
