"""文件内容嗅探（魔数）——扩展名不可信或缺失时的格式判定.

魔数依据（各格式的二进制头规范）：
- EDF：字节 0 = '0'（ASCII 48），字节 1–8 为 8 字节版本域（空格或 'B'）
- GDF：v1.x 头三字节 'GDC'，v2.x 'GDF '（两代都在用）
- BDF：字节 0 = 0xFF，字节 1–8 = 'BIOSEMI'
- HDF5 家族（NWB/通用 HDF5/Intan rhs）：\\x89HDF\\r\\n\\x1a\\n
- BrainVision .vhdr：文本，开头含 "Brain Vision Data Exchange Header"

不做的：FIF 是 tag 流无固定魔数、EEGLAB .set 是 MAT 容器、CNT 无公开魔数
——这些格式扩展名即权威，不嗅探。
"""

from __future__ import annotations

from pathlib import Path

# HDF5 家族 8 字节签名（NWB / 通用 HDF5 / Intan rhs.md 等同用）
_HDF5_SIG = b"\x89HDF\r\n\x1a\n"
# BrainVision 头文件是文本，开头是固定声明（33 字节内可见）
_BV_SIG = b"Brain Vision Data Exchange Header"


def sniff_format(path: Path) -> str | None:
    """嗅探文件真实格式（返回 reader_id；识别不出返回 None）.

    覆盖有可靠魔数的格式；识别不出的文件即使扩展名像也别强猜
    （拒绝猜测原则——返回 None 让调用方报"不支持的格式"）。
    """
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return None

    if len(head) >= 9 and head[0:1] == b"0" and head[1:9].strip(b" B") == b"":
        return "edf"  # '0' + 8 字节版本域（EDF 规范头）
    if head[:3] in (b"GDC", b"GDF"):
        return "gdf"  # GDF v1 'GDC' / v2 'GDF '
    if len(head) >= 9 and head[0:1] == b"\xff" and head[1:8] == b"BIOSEMI":
        return "bdf"
    if head[:8] == _HDF5_SIG:
        return "hdf5"  # 具体 HDF5 方言（NWB/Intan/通用）由读取器各自判定
    if _BV_SIG in head:
        return "brainvision"
    return None


def is_edf(path: Path) -> bool:
    """便捷判定：是否 EDF 文件（含扩展名路径——.edf 直接信扩展名）."""
    if path.suffix.lower() == ".edf":
        return True
    return sniff_format(path) == "edf"
