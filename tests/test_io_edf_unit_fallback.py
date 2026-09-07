"""EDF 头物理单位字段非标的读取兜底（坑 #62；2026-09-07 sheep4 'AuV' 驱动）.

mne 1.12 对白名单外单位串一律 factor=1 按伏特解读——'AuV' 这类导出笔误
使幅值显示放大 10⁶ 倍。EdfReader 在 load_raw 后扫描头单位字段（仅头几百
字节，字段主序布局见坑 #44），非标数据通道按 µV 兜底缩放（×1e-6）并打
logger.warning + meta.notes 待提示标记；白名单内（uV/mV/V…）与空单位/
Annotations 通道不碰。UI 侧打开时弹一次告知框后清标记（TestUiNotify）。

夹具口径：make_synth_edf 造的是 uV 单位标准件；_patch_units 字节级改写
头内单位字段（与 scripts/fix_edf_unit.py 同款布局逻辑），数据区零改动。
"""

from __future__ import annotations

from pathlib import Path

import mne
import numpy as np
import pytest

pytest.importorskip("PySide6", reason="无 GUI 环境")

from tests.synthetic_helpers import make_synth_edf  # noqa: E402

mne.set_log_level("ERROR")


def _patch_units(path: Path, new_unit: str) -> None:
    """把 EDF 头内全部数据通道的 physical_dimension 字段字节级改写.

    布局（坑 #44 字段主序）：ns@主头[252:256]，label 区 256 起每通道 16B，
    单位字段区 256+ns*96 起每通道 8B；EDF Annotations 通道跳过。new_unit
    右侧空格填充到 8 字节定长。
    """
    data = bytearray(Path(path).read_bytes())
    ns = int(data[252:256])
    field = new_unit.encode("ascii").ljust(8)
    for i in range(ns):
        label = bytes(data[256 + i * 16:256 + (i + 1) * 16]).decode("latin-1").strip()
        if label.lower() == "edf annotations":
            continue
        off = 256 + ns * 96 + i * 8
        data[off:off + 8] = field
    Path(path).write_bytes(bytes(data))


def _baseline(path: Path) -> np.ndarray:
    """mne 直读（不经 EdfReader 兜底）作为对照基准."""
    return mne.io.read_raw_edf(str(path), preload=True, verbose="ERROR").get_data()


class TestUnitFallback:
    """io 层：非标单位检出 → 按 µV 缩放 + warning；白名单/空单位不碰."""

    def test_auv_scaled_to_uv(self, tmp_path, caplog):
        """'AuV' 笔误件：读出数值 == mne 直读 ×1e-6，且打中文 warning."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EdfReader

        base = tmp_path / "base.edf"
        make_synth_edf(base)
        bad = tmp_path / "bad.edf"
        make_synth_edf(bad, seed=7)
        _patch_units(bad, "AuV")

        with caplog.at_level("WARNING"):
            scaled = EdfReader().load_raw(bad, LoadPolicy.PRELOAD).get_data()
        assert np.allclose(scaled, _baseline(bad) * 1e-6)
        assert "非标" in caplog.text and "µV" in caplog.text

    def test_lazy_forces_preload_and_scales(self, tmp_path):
        """LAZY 请求也整载（lazy 无法原地修正数据）且数值正确."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EdfReader

        bad = tmp_path / "b.edf"
        make_synth_edf(bad)
        _patch_units(bad, "AuV")
        raw = EdfReader().load_raw(bad, LoadPolicy.LAZY)
        assert raw.preload
        assert np.allclose(raw.get_data(), _baseline(bad) * 1e-6)

    def test_meta_note_flagged_and_clean(self, tmp_path):
        """open() 的 meta.notes 带待提示标记；正常文件无标记."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EDF_UNIT_FLAG, EdfReader

        bad = tmp_path / "b.edf"
        good = tmp_path / "g.edf"
        make_synth_edf(bad)
        make_synth_edf(good)
        _patch_units(bad, "AuV")

        rec_bad = EdfReader().open(bad, LoadPolicy.HEADER_ONLY)
        assert EDF_UNIT_FLAG in rec_bad.meta.notes
        assert "已按 µV 兜底" in rec_bad.meta.notes
        rec_good = EdfReader().open(good, LoadPolicy.HEADER_ONLY)
        assert EDF_UNIT_FLAG not in rec_good.meta.notes

    def test_normal_edf_identical_no_warning(self, tmp_path, caplog):
        """正常 uV 件：数值与 mne 直读逐位一致，零 warning 零整载偏移."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EdfReader

        good = tmp_path / "g.edf"
        make_synth_edf(good)
        raw = EdfReader().load_raw(good, LoadPolicy.LAZY)
        assert not raw.preload  # 正常件保持 lazy，不因兜底检测整载
        assert np.array_equal(raw.get_data(), _baseline(good))
        assert "非标" not in caplog.text

    @pytest.mark.parametrize("unit", ["mV", "V"])
    def test_whitelist_units_untouched(self, tmp_path, unit):
        """mne 白名单内单位（mV/V）：mne 自己正确换算，兜底不再二次缩放."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EdfReader

        p = tmp_path / f"{unit}.edf"
        make_synth_edf(p)
        _patch_units(p, unit)
        assert np.allclose(EdfReader().load_raw(p, LoadPolicy.PRELOAD).get_data(),
                           _baseline(p))

    def test_empty_unit_not_guessed(self, tmp_path):
        """空单位语义未知：不猜测不缩放（数值 == mne 直读），仅非标串才兜底."""
        from dataloadv.core.recording import LoadPolicy
        from dataloadv.io.mne_readers import EdfReader

        p = tmp_path / "e.edf"
        make_synth_edf(p)
        _patch_units(p, "")
        raw = EdfReader().load_raw(p, LoadPolicy.PRELOAD)
        assert np.array_equal(raw.get_data(), _baseline(p))


class TestUiNotify:
    """UI 侧：打开非标件弹一次告知框 → 清待提示标记 → 工作区 meta 同步."""

    @pytest.fixture()
    def win(self, qtbot, tmp_path, request, monkeypatch):
        """一次性工作区隔离的 MainWindow（三重隔离，win fixture 同款）."""
        import shutil

        from dataloadv.core.workspace import APP_DIR, Workspace
        from dataloadv.ui.main_window import MainWindow

        name = f"test_单位兜底_{request.node.name}"
        marker = APP_DIR / "current_workspace.txt"
        had = marker.exists()
        before = marker.read_text(encoding="utf-8") if had else None
        Workspace.set_current(name)
        win = MainWindow()
        qtbot.addWidget(win)
        win.state.reload_workspace(name)
        yield win
        stub = Workspace(name)
        stub._file = tmp_path / "close_event_save.json"
        win.state.workspace = stub
        shutil.rmtree(Workspace(name)._file.parent, ignore_errors=True)
        if had:
            marker.write_text(before, encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)

    def test_dialog_once_and_flag_cleared(self, win, monkeypatch):
        """_notify_edf_unit_fallback：弹一次 + FLAG 清除 + ws_meta 同步."""
        import dataloadv.ui.main_window as mw
        from dataloadv.core.recording import RecordingMeta
        from dataloadv.io.mne_readers import EDF_UNIT_FLAG

        meta = RecordingMeta(
            path="/tmp/unit_bad.edf", format="EDF", reader_id="edf",
            n_channels=4, channel_names=[f"ch{i}" for i in range(4)],
            channel_types=["eeg"] * 4, sfreq=250.0, duration_s=20.0,
            notes=f"{EDF_UNIT_FLAG}单位字段非标（ch0「AuV」等，共 4 通道），已按 µV 兜底",
        )
        ws = win.state.workspace
        ws.add_metas("/src", [meta])
        ws.save()

        calls: list = []
        monkeypatch.setattr(
            mw.QMessageBox, "information",
            staticmethod(lambda *a, **k: calls.append(a)),
        )
        rec = type("R", (), {"meta": meta})()  # 仅 meta 字段的轻量替身
        win._notify_edf_unit_fallback(rec)

        assert len(calls) == 1
        assert mw.S.EDF_UNIT_TITLE in calls[0]
        assert EDF_UNIT_FLAG not in meta.notes
        assert "已按 µV 兜底" in meta.notes  # 说明文本本体留档
        ws_meta = ws.find_by_path(meta.path)
        assert ws_meta is not None and ws_meta.notes == meta.notes
