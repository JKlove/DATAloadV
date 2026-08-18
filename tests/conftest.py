"""pytest 共享夹具.

- ``synthetic_raw``：确定性合成 mne Raw（8 导/250Hz/60s，含 10Hz 正弦 + 50Hz 工频
  + 噪声 + 3 个已知事件），后续里程碑的 proc/features/读取器测试都基于它
- ``real`` 标记：需要本地真实数据的测试（data/sheep），数据缺失自动跳过
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

# 项目根目录与真实数据目录（data/ 全程只读，测试亦然）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHEEP_DIR = PROJECT_ROOT / "data" / "sheep"


def pytest_configure(config):
    config.addinivalue_line("markers", "real: 需要本地真实数据的冒烟测试")


def pytest_collection_modifyitems(config, items):
    """real 标记的数据目录不存在时整组跳过（文件夹迁移场景）."""
    if SHEEP_DIR.exists():
        return
    skip = pytest.mark.skip(reason=f"真实数据目录不存在：{SHEEP_DIR}")
    for item in items:
        if "real" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def synthetic_raw():
    """造一个确定性的合成 mne.Raw.

    内容设计（服务后续断言）：
    - ch0：10Hz 正弦 → 频带功率应显著落在 alpha(8-13Hz)
    - ch1：10Hz 正弦 + 50Hz 工频 → 陷波步骤后 50Hz 峰值应被压制
    - ch2-7：白噪声
    - Annotations：3 个事件（onset 10/20/30s，code T0/T1/T2）
    """
    mne = pytest.importorskip("mne")  # 环境缺 mne 时给出可读跳过原因
    rng = np.random.default_rng(42)  # 固定种子保证测试可复现
    sfreq, n_seconds, n_channels = 250.0, 60.0, 8
    n_times = int(sfreq * n_seconds)
    t = np.arange(n_times) / sfreq

    data = rng.normal(0, 5e-6, (n_channels, n_times))  # 5 µV 噪声底
    data[0] += 20e-6 * np.sin(2 * np.pi * 10.0 * t)          # alpha 正弦
    data[1] += 20e-6 * np.sin(2 * np.pi * 10.0 * t)
    data[1] += 30e-6 * np.sin(2 * np.pi * 50.0 * t)          # 工频干扰

    info = mne.create_info(
        ch_names=[f"EEG{i:02d}" for i in range(n_channels)], sfreq=sfreq, ch_types="eeg"
    )
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    raw.set_annotations(
        mne.Annotations(onset=[10.0, 20.0, 30.0], duration=[0.0, 0.0, 0.0], description=["T0", "T1", "T2"])
    )
    return raw
