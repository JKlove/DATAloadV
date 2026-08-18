"""M0 骨架冒烟测试：包可导入、日志可初始化、合成数据夹具可用."""

from __future__ import annotations

import dataloadv
from dataloadv.core.logging_setup import setup_logging


def test_version() -> None:
    """包可导入且携带版本号."""
    assert isinstance(dataloadv.__version__, str)
    assert dataloadv.__version__


def test_setup_logging_idempotent(tmp_path) -> None:
    """日志初始化幂等：重复调用不重复挂 Handler."""
    import logging

    setup_logging()
    n_before = len(logging.getLogger().handlers)
    setup_logging()
    n_after = len(logging.getLogger().handlers)
    assert n_before == n_after and n_before > 0


def test_synthetic_raw_fixture(synthetic_raw) -> None:
    """合成数据夹具形态正确（后续所有功能测试的地基）."""
    raw = synthetic_raw
    assert raw.info["nchan"] == 8
    assert raw.info["sfreq"] == 250.0
    assert raw.n_times == 250 * 60
    assert len(raw.annotations) == 3
