"""M7 信号质量体检测试：纯计算指标/分级 → 提取器注册表 → 浏览器接线 → 真实黄金标准.

黄金标准来自四轮手工诊断的定论（DATA_NOTES §8）：
- 羊 BDF：CH5-8 开路复用（逐样本相同 + 钉满量程）必须判坏；CH1-3 大直流
  真实皮层信号必须不坏（直流只进指标不定级）；
- clinicaldata TPDJ-位置1：八通道全平（死放大器）必须全坏。

任何阈值/判定逻辑的退化都会被这两组真实数据抓住。
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest

mne = pytest.importorskip("mne")

from dataloadv.features import FEATURE_REGISTRY  # noqa: E402
from dataloadv.features.base import FeatureError  # noqa: E402
from dataloadv.features.qc import (  # noqa: E402
    QualityCheckFeature,
    QualityCheckParams,
    _plan_windows,
    compute_channel_qc,
)
from dataloadv.proc.context import ProcessingContext  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHEEP = PROJECT_ROOT / "data" / "sheep"
TPDJ1 = PROJECT_ROOT / "data" / "clinicaldata" / "01号脑电" / "TPDJ" / (
    "data-01号-TPDJ-位置1（中后颞区）.edf"
)

SF, DUR, N_CH = 250.0, 60.0, 6


def _qc_raw() -> "mne.io.RawArray":
    """合成体检考题：CH0 大直流真信号 / CH1=CH2 开路复用钉满量程 /
    CH3 死值平线 / CH4 强漂移 / CH5 正常噪声."""
    rng = np.random.default_rng(0)
    t = np.arange(int(SF * DUR)) / SF
    d = rng.normal(0, 20e-6, (N_CH, len(t)))
    d[0] += 5e-3 + 20e-6 * np.sin(2 * np.pi * 10 * t)  # 大直流 + 真信号
    d[1] = 0.375  # 钉满量程（BioSemi ±375 mV 形态）
    d[2] = 0.375  # 与 CH1 逐样本相同 → 开路复用
    d[3] = 0.0  # 死值平线
    d[4] += (t / 60.0) * 2e-3  # 线性漂移 ≈ +2000 µV/min
    info = mne.create_info([f"EEG{i}" for i in range(N_CH)], SF, ch_types="eeg")
    return mne.io.RawArray(d, info, verbose="ERROR")


def _rows(raw: "mne.io.RawArray", params: QualityCheckParams | None = None):
    """raw → 提取器路径的逐通道行（channel/quality/metrics）."""
    ctx = ProcessingContext(raw=raw)
    result = FEATURE_REGISTRY["qc"].extract(ctx, params or QualityCheckParams())
    by_ch: dict[str, dict[str, float]] = {}
    for r in result.scalars:
        by_ch.setdefault(r["channel"], {})[r["feature"]] = r["value"]
    return by_ch


# --------------------------------------------------------------------- 撒窗策略

class TestPlanWindows:
    """_plan_windows：均匀撒窗 / 窗数收缩 / 短录制退化（不整载的前提）."""

    def test_even_windows_cover_and_fit(self):
        wins = _plan_windows(60.0, 20, 2.0)
        assert len(wins) == 20
        assert wins[0] == (0.0, 2.0)
        assert wins[-1][1] == pytest.approx(60.0)  # 末窗贴到结尾
        assert all(t1 - t0 == pytest.approx(2.0) for t0, t1 in wins)

    def test_shrink_when_short(self):
        # 10s 只容 5 个 2s 窗 → 收缩到 5，仍均匀铺满
        wins = _plan_windows(10.0, 20, 2.0)
        assert len(wins) == 5
        assert wins[0][0] == 0.0 and wins[-1][1] == pytest.approx(10.0)

    def test_single_window_degrades(self):
        # 时长不足一个满窗 → 单窗 [0, duration)
        assert _plan_windows(1.5, 20, 2.0) == [(0.0, 1.5)]
        assert _plan_windows(2.0, 20, 2.0) == [(0.0, 2.0)]


# --------------------------------------------------------------------- 纯计算

class TestComputeChannelQc:
    """compute_channel_qc：指标数值与三级分级（合成考题逐通道验证）."""

    @pytest.fixture()
    def rows(self):
        raw = _qc_raw()
        names = list(raw.ch_names)
        n = raw.n_times

        def gw(t0, t1, picks=None):
            s0, s1 = int(t0 * SF), int(t1 * SF)
            return raw.get_data(picks=picks, start=s0, stop=s1), None

        return compute_channel_qc(gw, names, SF, DUR)

    def test_grading_matches_diagnosis(self, rows):
        """四轮手工诊断的合成复刻：0 好 / 1-2 坏(复用) / 3 坏(死值) / 4 疑似(漂移) / 5 好."""
        q = {r["channel"]: r["quality"] for r in rows}
        assert q == {
            "EEG0": "good", "EEG1": "bad", "EEG2": "bad",
            "EEG3": "bad", "EEG4": "suspect", "EEG5": "good",
        }

    def test_dup_pair_points_at_each_other(self, rows):
        by = {r["channel"]: r for r in rows}
        assert by["EEG1"]["dup_with"] == "EEG2"
        assert by["EEG2"]["dup_with"] == "EEG1"
        assert by["EEG1"]["metrics"]["qc_dup_flag"] == 1.0
        assert by["EEG0"]["dup_with"] is None

    def test_metrics_values(self, rows):
        by = {r["channel"]: r for r in rows}
        m0 = by["EEG0"]["metrics"]
        # 大直流只进指标不定级（M6.7b 定论：直流耦合固有直流是真信号）
        assert m0["qc_dc_uv"] == pytest.approx(5000.0, abs=50.0)
        assert m0["qc_std_uv"] > 10.0  # 真信号活度
        # 漂移数值 ≈ 已知斜率 2000 µV/min
        assert by["EEG4"]["metrics"]["qc_drift_uv_min"] == pytest.approx(2000.0, rel=0.05)
        # 死值平线：std=0、平直占比 100%、钉极值 100%（恒值通道 max==min）
        m3 = by["EEG3"]["metrics"]
        assert m3["qc_std_uv"] == pytest.approx(0.0)
        assert m3["qc_flat_pct"] == pytest.approx(100.0)
        assert m3["qc_rail_pct"] == pytest.approx(100.0)
        # 钉满量程复用通道的钉极值占比也是 100%
        assert by["EEG1"]["metrics"]["qc_rail_pct"] == pytest.approx(100.0)

    def test_reasons_are_chinese_and_specific(self, rows):
        by = {r["channel"]: r for r in rows}
        assert any("开路复用" in s for s in by["EEG1"]["reasons"])
        assert any("死值" in s for s in by["EEG3"]["reasons"])
        assert any("漂移" in s for s in by["EEG4"]["reasons"])
        assert by["EEG0"]["reasons"] == []
        # 指标键齐套（表头/导出列依赖）
        assert set(by["EEG0"]["metrics"]) == {
            "qc_level", "qc_bad_flag", "qc_suspect_flag", "qc_dup_flag",
            "qc_dc_uv", "qc_std_uv", "qc_drift_uv_min", "qc_flat_pct", "qc_rail_pct",
        }

    def test_windowed_sampling_never_loads_all(self):
        """分窗采样回归：get_window 只被调 n_windows 次、每次 ≤ 窗长样本数
        （LAZY 大文件不整载是 QC 的硬承诺，退化成 get_data() 会被抓住）."""
        calls: list[tuple[float, float, int]] = []
        n_times = int(SF * DUR)

        def gw(t0, t1, picks=None):
            calls.append((t0, t1, picks.count(None) if picks else -1))
            n = max(2, int((t1 - t0) * SF))
            return np.zeros((N_CH, min(n, n_times))), None

        compute_channel_qc(gw, [f"EEG{i}" for i in range(N_CH)], SF, DUR)
        assert len(calls) == 20  # 默认 n_windows
        assert all((t1 - t0) <= 2.0 + 1e-9 for t0, t1, _ in calls)

    def test_partial_rail_is_suspect(self):
        """钉极值占比 1%–50% → 疑似不满坏（间歇性饱和的正确分级）."""
        n = int(SF * DUR)
        d = np.zeros((1, n))
        d[0, : int(n * 0.3)] = 1.0  # 30% 时间钉在极值上
        d[0, int(n * 0.3):] = np.linspace(0.0, 0.5, n - int(n * 0.3))  # 其余爬坡

        def gw(t0, t1, picks=None):
            s0, s1 = int(t0 * SF), min(int(t1 * SF), n)
            return d[:, s0:s1], None

        rows = compute_channel_qc(gw, ["EEG0"], SF, DUR)
        r = rows[0]
        assert 20.0 <= r["metrics"]["qc_rail_pct"] <= 40.0
        assert r["quality"] == "suspect"
        assert r["metrics"]["qc_suspect_flag"] == 1.0


# --------------------------------------------------------------------- 提取器

class TestQualityCheckFeature:
    """注册表接入：菜单顺序 / 坏道不排除 / 通道子集 / 阶段守卫 / 中文报错."""

    def test_registered_and_menu_order(self):
        assert "qc" in FEATURE_REGISTRY
        assert isinstance(FEATURE_REGISTRY["qc"], QualityCheckFeature)
        # qc 排菜单首位（先体检后提特征的使用次序——features/__init__ 顺序）
        assert list(FEATURE_REGISTRY)[0] == "qc"

    def test_bad_channels_are_inspected_not_excluded(self):
        """与 pick_channels 语义相反的硬约定：info["bads"] 里的通道照样参检."""
        raw = _qc_raw()
        raw.info["bads"] = ["EEG1"]
        by = _rows(raw)
        assert "EEG1" in by  # 不被剔除
        assert by["EEG1"]["qc_level"] == 2.0

    def test_channel_subset_and_unknown(self):
        raw = _qc_raw()
        by = _rows(raw, QualityCheckParams(channels="EEG0, EEG3"))
        assert set(by) == {"EEG0", "EEG3"}
        with pytest.raises(FeatureError, match="不存在"):
            _rows(raw, QualityCheckParams(channels="NOPE"))

    def test_epochs_stage_rejected(self):
        ctx = ProcessingContext(stage="epochs")
        with pytest.raises(FeatureError, match="raw"):
            FEATURE_REGISTRY["qc"].extract(ctx, QualityCheckParams())

    def test_table_and_csv_roundtrip(self, tmp_path):
        """特征长表 → CSV 回读：qc 指标以行进表，批处理/导出链零额外代码."""
        from dataloadv.batch.results import FeatureTable
        from dataloadv.export.features_io import export_features_csv

        ctx = ProcessingContext(raw=_qc_raw())
        result = FEATURE_REGISTRY["qc"].extract(ctx, QualityCheckParams())
        table = FeatureTable()
        table.add_result(result, recording="synthetic.fif", subject="S01")
        csv_path = tmp_path / "qc.csv"
        written = export_features_csv(table, csv_path)
        assert written == [csv_path]
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        levels = {r["通道"]: float(r["数值"]) for r in rows if r["特征"] == "qc_level"}
        assert levels["EEG1"] == 2.0 and levels["EEG0"] == 0.0
        assert len(rows) == 6 * 9  # 6 通道 × 9 指标


# --------------------------------------------------------------------- 浏览器路径

pytest.importorskip("PySide6", reason="无 GUI 环境")


class _QcMsgBox:
    """signal_browser 模块级 QMessageBox 桩（逐模块 patch——MainWindow 的
    patch 罩不到子模块；e2e_m7 同款）."""

    StandardButton = type("S", (), {"Yes": 1})
    boxes: list[tuple[str, str]] = []
    answer = StandardButton.Yes

    @classmethod
    def question(cls, parent, title, text, *a, **k):
        cls.boxes.append(("question", text))
        return cls.answer

    @classmethod
    def information(cls, parent, title, text, *a, **k):
        cls.boxes.append(("information", text))

    @classmethod
    def critical(cls, parent, title, text, *a, **k):
        cls.boxes.append(("critical", text))


class TestQcBrowser:
    """浏览器「质量体检」按钮：列表前缀/tooltip/建议坏道确认全链路."""

    @pytest.fixture()
    def qc_browser(self, tmp_path, qtbot, monkeypatch):
        import dataloadv.ui.widgets.signal_browser as sb
        from dataloadv.io.registry import open_file

        fif = tmp_path / "qc.fif"
        _qc_raw().save(fif, overwrite=True, verbose="ERROR")
        rec = open_file(fif)
        view = sb.SignalBrowserView(rec)
        qtbot.addWidget(view)
        qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
        _QcMsgBox.boxes.clear()
        monkeypatch.setattr(sb, "QMessageBox", _QcMsgBox)
        yield view
        view.teardown()
        rec.unload()

    def _run_and_wait(self, view, qtbot):
        view._run_qc()
        qtbot.waitUntil(
            lambda: not view._qc_running and bool(view._qc), timeout=10000
        )

    def test_marks_and_suggests_bads(self, qc_browser, qtbot):
        """✓/✗ 前缀 + tooltip 明细 + question(Yes) → 三个坏道写进 info["bads"]."""
        view = qc_browser
        self._run_and_wait(view, qtbot)
        texts = [view._ch_list.item(i).text() for i in range(view._ch_list.count())]
        assert texts[0].startswith("✓ EEG0")
        assert texts[1].startswith("✗ EEG1") and texts[2].startswith("✗ EEG2")
        assert texts[4].startswith("? EEG4")  # 漂移疑似
        tip = view._ch_list.item(1).toolTip()
        assert "开路复用" in tip and "[坏]" in tip
        assert view._ch_list.item(0).toolTip().startswith("EEG0 [好]")
        # 弹窗一次、内容含通道清单；Yes → 坏道标记（曲线灰显 + info["bads"]）
        kinds = [k for k, _ in _QcMsgBox.boxes]
        assert kinds == ["question"]
        assert "EEG1" in _QcMsgBox.boxes[0][1]
        assert view.current_bads() == ["EEG1", "EEG2", "EEG3"]
        assert set(view.rec.raw.info["bads"]) == {"EEG1", "EEG2", "EEG3"}

    def test_all_good_shows_information_only(self, tmp_path, qtbot, monkeypatch):
        """全部合格 → information 分支，不弹 question、不标坏道."""
        import dataloadv.ui.widgets.signal_browser as sb
        from dataloadv.io.registry import open_file

        rng = np.random.default_rng(5)
        d = rng.normal(0, 30e-6, (3, int(SF * DUR)))
        raw = mne.io.RawArray(
            d, mne.create_info(["A", "B", "C"], SF, ch_types="eeg"), verbose="ERROR"
        )
        fif = tmp_path / "good.fif"
        raw.save(fif, overwrite=True, verbose="ERROR")
        rec = open_file(fif)
        view = sb.SignalBrowserView(rec)
        qtbot.addWidget(view)
        qtbot.waitUntil(lambda: view._loaded_once, timeout=10000)
        _QcMsgBox.boxes.clear()
        monkeypatch.setattr(sb, "QMessageBox", _QcMsgBox)
        try:
            self._run_and_wait(view, qtbot)
            kinds = [k for k, _ in _QcMsgBox.boxes]
            assert kinds == ["information"]
            assert view.current_bads() == []
            assert view._ch_list.item(0).text().startswith("✓ A")
        finally:
            view.teardown()
            rec.unload()

    def test_no_reentry_and_guard(self, qc_browser):
        """首帧未完成时点击早退；计算期间按钮禁用."""
        view = qc_browser
        view._loaded_once = False
        view._run_qc()  # 早退：不应进入计算
        assert view._qc == {}
        view._loaded_once = True
        view._qc_running = True
        view._run_qc()  # 防重入：直接返回
        assert view._qc == {}


# --------------------------------------------------------------------- 真实黄金标准

@pytest.mark.real
class TestQcGoldenReal:
    """真实数据黄金标准：四轮手工诊断定论的可复跑化（M7 的验收线）."""

    @staticmethod
    def _qc_via_recording(path: Path):
        from dataloadv.features.qc import QualityCheckParams
        from dataloadv.io.registry import open_file

        rec = open_file(path)
        rows = compute_channel_qc(
            rec.get_window, list(rec.meta.channel_names),
            rec.meta.sfreq, rec.meta.duration_s, QualityCheckParams(),
        )
        rec.unload()
        return rows

    def test_sheep_open_circuit_vs_real_signal(self):
        """羊 BDF：4 个开路复用通道（CH5-8）必须坏；其余真信号通道**不得判坏**.

        实测其余通道判 suspect（低频大信号峰值平台触发钉极值疑似线 2.3%、
        皮层信号带真实慢漂移）——"疑似=建议人工复核"正是设计语义；
        黄金不变式是"真信号不坏"，不是"真信号必 good"。
        """
        files = sorted(SHEEP.glob("*.edf"))
        assert files, f"羊数据缺失：{SHEEP}"
        rows = self._qc_via_recording(files[0])
        bads = [r for r in rows if r["quality"] == "bad"]
        rest = [r for r in rows if r["quality"] != "bad"]
        # CH5-8 四通道开路复用：全部坏且都报复用（M6.6 定论）
        assert len(bads) == 4
        assert all(r["metrics"]["qc_dup_flag"] == 1.0 for r in bads)
        assert all(r["dup_with"] for r in bads)
        assert all(r["metrics"]["qc_rail_pct"] == pytest.approx(100.0) for r in bads)
        # CH1-4 大直流真实皮层信号：不坏、活度真实、直流只进指标
        assert len(rest) == 4
        assert all(r["quality"] in ("good", "suspect") for r in rest)
        assert all(r["metrics"]["qc_bad_flag"] == 0.0 for r in rest)
        assert all(r["metrics"]["qc_std_uv"] > 1.0 for r in rest)
        assert all(abs(r["metrics"]["qc_dc_uv"]) > 1000.0 for r in rest)

    def test_clinical_tpdj_pos1_all_bad(self):
        """clinicaldata TPDJ-位置1：八通道死放大器必须全坏.

        M7 实测精化了 M6.7b 的"全平"概括——通道分两型：CH2/4/8 真·全平
        （flat 100% + CH2≡CH4 开路复用）；CH1/3/5/6/7 钉满量程 + 偶发跳变
        （rail 50–85%、漂移上千 µV/min）。共同不变式：全坏、过半样本钉极值、
        电平顶在满量程大量级。
        """
        assert TPDJ1.exists(), f"临床数据缺失：{TPDJ1}"
        rows = self._qc_via_recording(TPDJ1)
        assert len(rows) == 8
        assert all(r["quality"] == "bad" for r in rows)
        assert all(r["metrics"]["qc_rail_pct"] >= 50.0 for r in rows)
        assert all(abs(r["metrics"]["qc_dc_uv"]) > 100_000.0 for r in rows)
        by = {r["channel"]: r for r in rows}
        assert by["CH2"]["dup_with"] == "CH4"  # 死放大器也有开路复用
        assert by["CH2"]["metrics"]["qc_flat_pct"] == pytest.approx(100.0, abs=0.1)

    def test_sheep_extractor_and_export_chain(self, tmp_path):
        """羊数据走提取器路径（PRELOAD ctx）+ 长表导出：与浏览器路径同一分级."""
        from dataloadv.batch.results import FeatureTable
        from dataloadv.export.features_io import export_features_hdf5, read_features_hdf5
        from dataloadv.io.registry import open_file

        files = sorted(SHEEP.glob("*.edf"))
        rec = open_file(files[0])
        ctx = ProcessingContext.from_recording(rec)
        result = FEATURE_REGISTRY["qc"].extract(ctx, QualityCheckParams())
        table = FeatureTable()
        table.add_result(result, recording=rec.meta.filename, subject="sheep")
        h5 = tmp_path / "sheep_qc.h5"
        export_features_hdf5(table, h5)
        df, _curves = read_features_hdf5(h5)
        levels = df[(df["feature"] == "qc_level")]["value"].to_numpy()
        assert len(levels) == 8
        assert (levels == 2.0).sum() == 4  # 与 get_window 路径同一批坏道
        rec.unload()
