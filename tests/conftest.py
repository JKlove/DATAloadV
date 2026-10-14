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


# ---- 挂死防御：共享等待助手 + 测试时间戳探针（2026-10-14 根因闭环后常设）----
# wait_until：替代 qtbot.waitUntil——后者内部是 QEventLoop.exec + Qt 侧
# QTimer 超时（pytestqt/wait_signal.py），事件分发被饿死时超时本身失效 →
# 永等挂死（2026-10-13/14 全量 Heisenbug，HANDOFF 坑 #57⑥ 档案）。本助手
# 条件与 deadline 都在 Python 层（time.monotonic），最坏 timeout_s 秒后
# 明确 FAIL 可见，不会永挂。坑 #57⑥（已根除）。时间戳探针常设：
# 文件级写入不经 pytest fd 捕获、不改变 Qt 时序（-s 观测会改变行为）——再有
# 挂死时看 /tmp/pytest_trace.log 最后一个 START 无 FINISH 即精确挂点，零成本。
import time as _time


def wait_until(qtbot, cond, what: str = "条件", timeout_s: float = 15.0) -> None:
    """Python 层 deadline 轮询等待（qtbot.waitUntil 的防挂死替代）."""
    deadline = _time.monotonic() + timeout_s
    while not cond():
        if _time.monotonic() > deadline:
            import pytest
            pytest.fail(f"等待超时（{timeout_s}s）：{what}")
        qtbot.wait(50)


def pytest_runtest_logstart(nodeid, location):
    try:
        with open("/tmp/pytest_trace.log", "a") as _f:
            _f.write(f"START {_time.monotonic():.3f} {nodeid}\n")
    except OSError:
        pass


def pytest_runtest_logfinish(nodeid, location):
    try:
        with open("/tmp/pytest_trace.log", "a") as _f:
            _f.write(f"FINISH {_time.monotonic():.3f} {nodeid}\n")
    except OSError:
        pass
