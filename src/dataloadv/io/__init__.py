"""io 包：数据读取器层（注册表模式，禁止 import Qt）.

import 本包即完成全部读取器注册（各模块的 @register_reader 装饰器在
导入时执行）。调用方只用 registry.open_file / scan_folder，不直接碰读取器。
"""

from . import bciciv_mat, hdf5, mne_readers, table  # noqa: F401 - 触发注册
from .registry import open_file, scan_folder  # noqa: F401 - 对外统一入口

__all__ = ["open_file", "scan_folder"]
