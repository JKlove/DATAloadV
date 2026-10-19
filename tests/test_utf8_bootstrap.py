"""UTF-8 模式自举（坑 #65/#66）的单元测试——打桩层面验证决策逻辑与参数构造.

v0.2.1 事故（Windows 打不开）根因：execv 参数表把 argv[0] 重复拼成位置
参数——本文件新增的 frozen/source 两形态参数断言就是当时的缺口（macOS
上自举 no-op，真机行为只有参数构造断言能拦）。真机 GBK 崩溃本身无法在
macOS 复现（locale 即 UTF-8），端到端证明靠 Windows 真机复验（v0.2.2）。
"""

from __future__ import annotations

import os
import sys
import types

import pytest

from dataloadv._utf8 import _restart_argv, ensure_utf8_mode


class TestEnsureUtf8Mode:
    """分支与兜底：posix 不重启 / 已 UTF-8 不重启 / Windows 旧编码重启 / 防循环 / execv 失败兜底."""

    @staticmethod
    def _patch_env(monkeypatch, os_name: str, utf8_mode: int) -> None:
        """打桩 os.name 与 sys.flags（structseq 只读，整体换 SimpleNamespace）.

        顺带用 monkeypatch 清空两个环境变量——teardown 自动还原到测试前
        状态（被测函数内的直接赋值也因此被回收，不污染后续测试）。
        """
        monkeypatch.setattr(os, "name", os_name)
        monkeypatch.setattr(sys, "flags", types.SimpleNamespace(utf8_mode=utf8_mode))
        monkeypatch.delenv("PYTHONUTF8", raising=False)
        monkeypatch.delenv("DLV_UTF8_RESTARTED", raising=False)

    def test_noop_on_posix(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(os, "execv", lambda *a: calls.append(a))
        self._patch_env(monkeypatch, "posix", 0)
        assert ensure_utf8_mode() is False
        assert calls == []  # macOS/Linux（locale 即 UTF-8）永不重启

    def test_noop_when_utf8_mode_on(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(os, "execv", lambda *a: calls.append(a))
        self._patch_env(monkeypatch, "nt", 1)
        assert ensure_utf8_mode() is False
        assert calls == []  # 已是 UTF-8 模式（重启后的进程）不再触发

    def test_restart_on_windows_legacy_encoding(self, monkeypatch):
        calls: list = []
        monkeypatch.setattr(os, "execv", lambda *a: calls.append(a))
        self._patch_env(monkeypatch, "nt", 0)
        # 冻结态打桩：exe 路径 + 原 argv[0]（模拟 v0.2.1 事故现场）
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "argv", ["C:\\app\\DataloadV.exe", "--smoke"])
        monkeypatch.setattr(sys, "executable", "C:\\app\\DataloadV.exe")
        assert ensure_utf8_mode() is True
        assert os.environ["PYTHONUTF8"] == "1"
        assert os.environ["DLV_UTF8_RESTARTED"] == "1"
        # 关键断言（坑 #66 回归）：exe 路径不得重复成位置参数
        assert calls == [("C:\\app\\DataloadV.exe", ["C:\\app\\DataloadV.exe", "--smoke"])]

    def test_no_loop_guard(self, monkeypatch):
        """标记仍在但 UTF-8 模式未生效（异常环境）——放弃重启防无限循环."""
        calls: list = []
        monkeypatch.setattr(os, "execv", lambda *a: calls.append(a))
        self._patch_env(monkeypatch, "nt", 0)
        monkeypatch.setenv("DLV_UTF8_RESTARTED", "1")
        assert ensure_utf8_mode() is False
        assert calls == []

    def test_execv_failure_falls_back(self, monkeypatch):
        """execv 抛 OSError（杀软/权限）——清标记照常启动，绝不死于自举."""
        def _boom(*a):
            raise OSError("blocked")
        self._patch_env(monkeypatch, "nt", 0)
        monkeypatch.setattr(os, "execv", _boom)
        assert ensure_utf8_mode() is False
        assert "DLV_UTF8_RESTARTED" not in os.environ  # 标记已清（可诊断重试）


class TestRestartArgv:
    """参数构造两形态（v0.2.1 事故的直接回归网）."""

    def test_frozen_no_argv0_duplication(self, monkeypatch):
        """冻结态：exe + 原参数——argv[0]（exe 路径）绝不能重复拼入."""
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "argv", ["C:\\app\\DataloadV.exe"])
        monkeypatch.setattr(sys, "executable", "C:\\app\\DataloadV.exe")
        assert _restart_argv() == ["C:\\app\\DataloadV.exe"]

    def test_frozen_keeps_user_args(self, monkeypatch):
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "argv", ["C:\\app\\DataloadV.exe", "--smoke"])
        monkeypatch.setattr(sys, "executable", "C:\\app\\DataloadV.exe")
        assert _restart_argv() == ["C:\\app\\DataloadV.exe", "--smoke"]

    def test_source_mode_reconstructs_dash_m(self, monkeypatch):
        """源码态（python -m dataloadv）：重启命令必须重建 -m dataloadv."""
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.setattr(
            sys, "argv",
            ["/repo/src/dataloadv/__main__.py", "--smoke"],
        )
        monkeypatch.setattr(sys, "executable", "/opt/python3.10/bin/python3.10")
        assert _restart_argv() == [
            "/opt/python3.10/bin/python3.10", "-m", "dataloadv", "--smoke",
        ]
