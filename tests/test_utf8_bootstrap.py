"""UTF-8 运行时补丁（坑 #65）的单元测试——补丁行为在 macOS 上可完整验证.

策略沿革：v0.2.1 曾用 execv 自重启走 PEP 540——v0.2.2 用户复验仍 GBK 崩，
冻结 probe 实验实锤 **PyInstaller 6.22.2 冻结解释器不应用 PYTHONUTF8**
（设变量后 sys.flags.utf8_mode 仍 0），该路线整体移除。现行方案是纯运行时
的 builtins.open 补丁，**行为不依赖平台**——本文件的行为断言（GBK 不安全
内容的六种 open 形态）在 macOS 跑即等价于真机验证，不再有"本地拦不住"的
平台分支。
"""

from __future__ import annotations

import builtins
import os
import types

import pytest

from dataloadv import _utf8 as utf8_mod
from dataloadv._utf8 import ensure_utf8_mode

# "文1号脑电©测试" 的 UTF-8 字节含 GBK 非法配对（CJK 三字节 + ASCII 数字/
# 符号，GBK 首字节后跟 <0x40 的尾字节）——GBK 解码必炸，是补丁效果的试金石
_GBK_UNSAFE = "文1号脑电©测试"


class TestEnsureUtf8Mode:
    """分支与行为：posix no-op / 已 UTF-8 no-op / 补丁六语义 / 幂等."""

    @staticmethod
    def _force_nt(monkeypatch, utf8_mode: int = 0) -> None:
        """只在 _utf8 模块命名空间内伪装成"中文 Windows 未开 UTF-8 模式".

        **不碰全局 os.name**——全局打桩会让 pathlib 以为在 Windows 上
        （新建 WindowsPath 在 macOS 直接 NotImplementedError，曾把 pytest
        报告链炸成 INTERNALERROR）；builtins.open 是真打（要验证的就是它）。
        """
        monkeypatch.setattr(utf8_mod, "os", types.SimpleNamespace(name="nt"))
        monkeypatch.setattr(
            utf8_mod, "sys",
            types.SimpleNamespace(flags=types.SimpleNamespace(utf8_mode=utf8_mode)),
        )

    @pytest.fixture()
    def restore_open(self, monkeypatch):
        """保底恢复 builtins.open——先让 monkeypatch 记住原对象，teardown
        自动还原（即使被测代码替换了它）。"""
        monkeypatch.setattr(builtins, "open", builtins.open)

    def test_noop_on_posix(self):
        """macOS/Linux（locale 即 UTF-8）：不打补丁，builtins.open 原样."""
        if os.name != "posix":
            pytest.skip("非 posix 平台")
        assert ensure_utf8_mode() is False
        assert not getattr(builtins.open, "_dataloadv_utf8_open", False)

    def test_noop_when_utf8_mode_on(self, monkeypatch):
        self._force_nt(monkeypatch, utf8_mode=1)
        assert ensure_utf8_mode() is False
        assert not getattr(builtins.open, "_dataloadv_utf8_open", False)

    def test_patch_reads_gbk_unsafe_utf8(self, monkeypatch, tmp_path, restore_open):
        """核心行为：补丁后无 encoding 的 open 能读 GBK 不安全的 UTF-8 文件.

        （内容确实 GBK 不可解由下方 explicit/positional 两测试的 raises 证明，
        macOS 本地 locale 是 UTF-8，无法做"打桩前必炸"的对照——不假装有。）
        """
        p = tmp_path / "u8.txt"
        p.write_bytes(_GBK_UNSAFE.encode("utf-8"))
        self._force_nt(monkeypatch)
        assert ensure_utf8_mode() is True
        with open(p) as f:  # 补丁后：不再炸
            assert f.read() == _GBK_UNSAFE

    def test_explicit_encoding_kwarg_respected(self, monkeypatch, tmp_path, restore_open):
        """显式 encoding（kwarg）透传原语义——GBK 读仍按 GBK 炸."""
        p = tmp_path / "u8.txt"
        p.write_bytes(_GBK_UNSAFE.encode("utf-8"))
        self._force_nt(monkeypatch)
        ensure_utf8_mode()
        with pytest.raises(UnicodeDecodeError):
            with open(p, encoding="gbk") as f:
                f.read()

    def test_positional_encoding_respected(self, monkeypatch, tmp_path, restore_open):
        """位置参数传 encoding（open(f,'r',-1,'gbk')）不被补丁覆盖."""
        p = tmp_path / "u8.txt"
        p.write_bytes(_GBK_UNSAFE.encode("utf-8"))
        self._force_nt(monkeypatch)
        ensure_utf8_mode()
        with pytest.raises(UnicodeDecodeError):
            with open(p, "r", -1, "gbk") as f:
                f.read()

    def test_binary_mode_unaffected(self, monkeypatch, tmp_path, restore_open):
        """二进制模式原样透传（字节不走编码层）."""
        p = tmp_path / "u8.txt"
        raw = _GBK_UNSAFE.encode("utf-8")
        p.write_bytes(raw)
        self._force_nt(monkeypatch)
        ensure_utf8_mode()
        with open(p, "rb") as f:
            assert f.read() == raw
        with open(p, "rb") as f:  # buffering 位置参数同样透传
            assert f.read() == raw

    def test_write_default_becomes_utf8(self, monkeypatch, tmp_path, restore_open):
        """无 encoding 的写文件默认变 UTF-8（与 PEP 540 对 open() 的语义一致）."""
        p = tmp_path / "w.txt"
        self._force_nt(monkeypatch)
        ensure_utf8_mode()
        with open(p, "w") as f:
            f.write(_GBK_UNSAFE)
        assert p.read_bytes() == _GBK_UNSAFE.encode("utf-8")

    def test_idempotent(self, monkeypatch, restore_open):
        """重复调用安全（幂等标记，不叠包装层）."""
        self._force_nt(monkeypatch)
        assert ensure_utf8_mode() is True
        assert ensure_utf8_mode() is False  # 第二次不再打
