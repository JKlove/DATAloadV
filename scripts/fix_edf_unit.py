#!/usr/bin/env python
"""修复 EDF 文件头 physical_dimension 单位字段错误的字节级小工具。

背景（2026-09-07，sheep4 数据排查结论）：
    某些设备/导出软件会把 EDF 头的物理单位字段写错——例如 260906 采集的
    ZJDJ 系列文件写成了 'AuV'（后缀 uV 表明本意是微伏，前缀 'A' 是导出笔误）。
    mne/edfio 的单位白名单里没有 'AuV'，读取时不做换算、把物理值裸当伏特，
    导致应用里幅值显示放大 10^6 倍（比例尺出现 10^6 µV）。

    本工具只改头里的单位标签字节，数据区一个字节都不动，输出修正副本，
    原文件绝不修改（data/ 只读铁律）。

用法：
    python scripts/fix_edf_unit.py <输入.edf> [--from AuV] [--to uV] [--out 输出.edf]

    --from  期望在 physical_dimension 字段看到的原单位串（strip 后精确匹配；
            不匹配的通道跳过并逐个报告，防止误伤）
    --to    替换成的单位串（ASCII，长度 <= 8；右侧空格填充到 8 字节定长）
    --out   输出路径，默认与输入同目录 <stem>_fixed.edf；输出已存在时拒绝覆盖

EDF 头布局备忘（按字段分组，非按信号分块；256 + ns*96 为 dim 区起点）：
    主头 256 字节：n_signals 位于 [252:256]
    信号字段区：label(ns*16) transducer(ns*80) physical_dimension(ns*8)
    physical_min/max(ns*8+8) digital_min/max prefiltering(ns*80)
    samples_per_datarecord(ns*8) reserved(ns*32) —— 每信号合计仍 256 字节
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def fix_edf_unit(src: Path, dst: Path, from_unit: str, to_unit: str) -> int:
    """把 src 文件头中单位等于 from_unit 的通道改为 to_unit，整文件复制到 dst。

    返回实际修改的通道数；任何结构异常直接抛错终止（宁可不动也不改错）。
    """
    if to_unit != to_unit.encode("ascii", "strict").decode():
        raise ValueError(f"目标单位必须是 ASCII：{to_unit!r}")
    if len(to_unit) > 8:
        raise ValueError(f"目标单位最长 8 字符（EDF 字段定长）：{to_unit!r}")

    data = bytearray(src.read_bytes())
    if len(data) < 256:
        raise ValueError(f"文件不足 256 字节，不是 EDF：{src}")
    version = data[0:8]
    if not version.lstrip().endswith(b"EDF") and not version.startswith(b"0"):
        raise ValueError(f"版本字段异常，疑似非 EDF 文件：{version!r}")

    ns = int(bytes(data[252:256]))
    header_bytes = int(bytes(data[184:192]))
    expected_header = 256 + ns * 256
    if header_bytes != expected_header:
        raise ValueError(
            f"头长不自洽：声明 {header_bytes}，按 ns={ns} 应为 {expected_header}"
        )

    # physical_dimension 按字段分组：所有通道的 8 字节字段连续排列
    dim_base = 256 + ns * 96
    to_field = to_unit.encode("ascii").ljust(8)

    changed = 0
    for i in range(ns):
        off = dim_base + i * 8
        old = bytes(data[off : off + 8])
        label = bytes(data[256 + i * 16 : 256 + i * 16 + 16]).decode("ascii").strip()
        if old.decode("ascii", "replace").strip() == from_unit:
            data[off : off + 8] = to_field
            changed += 1
            print(f"  [{i:2d}] {label!r:20s} {old!r} -> {to_field!r}", flush=True)
        else:
            print(f"  [{i:2d}] {label!r:20s} {old!r} 跳过（不等于 --from）", flush=True)

    if changed == 0:
        raise ValueError(f"没有任何通道的单位等于 {from_unit!r}，未写出文件")

    dst.write_bytes(bytes(data))
    return changed


def main(argv: list[str] | None = None) -> int:
    """命令行入口：解析参数、调 fix_edf_unit、打印验证提示。"""
    ap = argparse.ArgumentParser(description="EDF 头单位字段字节级修复（数据区零改动）")
    ap.add_argument("src", type=Path, help="输入 EDF（原文件不会被修改）")
    ap.add_argument("--from", dest="from_unit", default="AuV", help="原单位串（默认 AuV）")
    ap.add_argument("--to", dest="to_unit", default="uV", help="新单位串（默认 uV）")
    ap.add_argument("--out", type=Path, default=None, help="输出路径（默认同目录 <stem>_fixed.edf）")
    args = ap.parse_args(argv)

    src: Path = args.src
    dst: Path = args.out or src.with_name(src.stem + "_fixed" + src.suffix)
    if not src.is_file():
        print(f"输入不存在：{src}", file=sys.stderr, flush=True)
        return 2
    if dst.exists():
        print(f"输出已存在，拒绝覆盖（先手动删除）：{dst}", file=sys.stderr, flush=True)
        return 2

    print(f"输入: {src}", flush=True)
    print(f"输出: {dst}", flush=True)
    n = fix_edf_unit(src, dst, args.from_unit, args.to_unit)
    print(f"完成：修改 {n} 个通道的单位字段 {args.from_unit!r} -> {args.to_unit!r}；"
          f"数据区零改动", flush=True)
    print(f"验证建议：mne.io.read_raw_edf({str(dst)!r}) 后 get_data().std()*1e6 应为微伏级",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
