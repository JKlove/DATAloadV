"""UTF-8 模式自举（坑 #65）的单元测试——打桩层面验证决策逻辑.

真机 GBK 崩溃无法在 macOS 复现（locale 即 UTF-8，且 pyqtgraph 0.14.0
PyPI/conda 两渠道 wheel 的渐变 CSV 实测均 GBK 安全——用户 Windows 包的
字节级差异本机不可复现），故此处验证：何种环境触发重启、重启参数正确、
防循环双保险。端到端证明靠 Windows 真机复验（v0.2.1）。
"""

from __future__ import annotations

import os
import sys
import types

import pytest

from dataloadv._utf8 import ensure_utf8_mode


class TestEnsureUtf8Mode:
    """四分支：posix 不重启 / 已 UTF-8 不重启 / Windows 旧编码重启 / 防循环放弃."""

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
        assert ensure_utf8_mode() is True
        assert os.environ["PYTHONUTF8"] == "1"
        assert os.environ["DLV_UTF8_RESTARTED"] == "1"
        # 自重启带全参（--smoke 等命令行参数不丢）
        assert calls == [(sys.executable, [sys.executable, *sys.argv])]

    def test_no_loop_guard(self, monkeypatch):
        """标记仍在但 UTF-8 模式未生效（异常环境）——放弃重启防无限循环."""
        calls: list = []
        monkeypatch.setattr(os, "execv", lambda *a: calls.append(a))
        self._patch_env(monkeypatch, "nt", 0)
        monkeypatch.setenv("DLV_UTF8_RESTARTED", "1")
        assert ensure_utf8_mode() is False
        assert calls == []
