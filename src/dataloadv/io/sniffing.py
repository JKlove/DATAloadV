"""文件内容嗅探（魔数）——扩展名不可信或缺失时的格式判定.

魔数依据（各格式的二进制头规范）：
- EDF：字节 0–7 为 8 字节版本域 = '0' + 7 空格（EDF/EDF+ 规范写法）
- GDF：v1.x 头三字节 'GDC'，v2.x 'GDF '（两代都在用）
- BDF：字节 0–7 = 0xFF + 'BIOSEMI'
- HDF5 家族（NWB/通用 HDF5/Intan rhs）：\\x89HDF\\r\\n\\x1a\\n
- BrainVision .vhdr：文本，开头含 "Brain Vision Data Exchange Header"

不做的：FIF 是 tag 流无固定魔数、EEGLAB .set 是 MAT 容器、CNT 无公开魔数
——这些格式扩展名即权威，不嗅探。

2026-08-24 实证（sheep 系列）：本地 data/sheep、sheep2、sheep3 共 6 个
.edf 文件内容全是 BDF（\xffBIOSEMI 头）——按扩展名派给 EDF 读取器会把
24-bit 样本按 16-bit 解码，样本数虚增 1.5×、数值全部错位。因此
registry.open_file 现按魔数做"内容优先"派发（嗅探结果能唯一定位读取器时
以内容为准，扩展名不符记 warning），本模块的 sniff_format 即权威判定。
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

    # EDF 版本域 = 字节 0–7（'0' + 7 空格）——只看前 8 字节，绝不越界到
    # 患者域（旧实现查 head[1:9] 把患者名首字节卷进来，真 EDF 会漏判）
    if head[:8] == b"0" + b" " * 7:
        return "edf"
    if head[:3] in (b"GDC", b"GDF"):
        return "gdf"  # GDF v1 'GDC' / v2 'GDF '
    if len(head) >= 9 and head[0:1] == b"\xff" and head[1:8] == b"BIOSEMI":
        return "bdf"
    if head[:8] == _HDF5_SIG:
        return "hdf5"  # 具体 HDF5 方言（NWB/Intan/通用）由读取器各自判定
    if _BV_SIG in head:
        return "brainvision"
    return None
