"""文件内容嗅探（魔数）——扩展名不可信或缺失时的格式判定.

M1 仅实现 EDF（当前唯一读取器）；M2 随其余格式补全。魔数依据：
- EDF：字节 0 = '0'（ASCII 48），字节 1–8 为 8 字节版本域（空格或 'B'）
- GDF：'GDC' 开头
- FIF：首 4 字节 0x0F 0xF5 ... 的 tag 流（0xFIF 双精度标记）
- HDF5 家族（NWB/HDF5/Intan rhs）：\\x89HDF\\r\\n\\x1a\\n
- BrainVision .vhdr：文本，首行含 "Brain Vision Data Exchange Header"
"""

from __future__ import annotations

from pathlib import Path

# 各格式的魔数判定函数：读文件头若干字节 → 格式名（与 reader_id 对应）或 None
MAGIC_CHECKS: list[tuple[int, callable]] = []  # [(读多少字节, 判定函数)]，M2 填充


def sniff_format(path: Path) -> str | None:
    """嗅探文件真实格式（返回 reader_id；识别不出返回 None）.

    M1：仅实现 EDF（唯一已注册读取器）；M2 扩充判定表。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return None

    if len(head) >= 9 and head[0:1] == b"0" and head[1:9].strip(b" B") == b"":
        return "edf"  # '0' + 8 字节版本域（EDF 规范头）
    return None


def is_edf(path: Path) -> bool:
    """便捷判定：是否 EDF 文件（含扩展名路径——.edf 直接信扩展名）."""
    if path.suffix.lower() == ".edf":
        return True
    return sniff_format(path) == "edf"
