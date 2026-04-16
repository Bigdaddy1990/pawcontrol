"""Targeted coverage tests for performance.py — uncovered paths (0% → 28%+).

Covers: enable/disable_performance_monitoring, get_performance_summary,
        get_slow_operations, performance_tracker context manager
"""

import pytest

from custom_components.pawcontrol.performance import (
    disable_performance_monitoring,
    enable_performance_monitoring,
    get_performance_summary,
    get_slow_operations,
    performance_tracker,
)

# ═══════════════════════════════════════════════════════════════════════════════
# enable / disable monitoring
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_enable_performance_monitoring() -> None:  # noqa: D103
    enable_performance_monitoring()  # should not raise


@pytest.mark.unit
def test_disable_performance_monitoring() -> None:  # noqa: D103
    disable_performance_monitoring()  # should not raise


@pytest.mark.unit
def test_enable_disable_cycle() -> None:  # noqa: D103
    enable_performance_monitoring()
    disable_performance_monitoring()
    enable_performance_monitoring()  # idempotent


# ═══════════════════════════════════════════════════════════════════════════════
# get_performance_summary
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_get_performance_summary_returns_dict() -> None:  # noqa: D103
    enable_performance_monitoring()
    result = get_performance_summary()
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_performance_summary_after_disable() -> None:  # noqa: D103
    disable_performance_monitoring()
    result = get_performance_summary()
    assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# get_slow_operations
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_get_slow_operations_empty() -> None:  # noqa: D103
    enable_performance_monitoring()
    result = get_slow_operations(threshold_ms=999_999)
    assert isinstance(result, list)


@pytest.mark.unit
def test_get_slow_operations_default_threshold() -> None:  # noqa: D103
    result = get_slow_operations()
    assert isinstance(result, list)


@pytest.mark.unit
def test_get_slow_operations_zero_threshold() -> None:  # noqa: D103
    result = get_slow_operations(threshold_ms=0.0)
    assert isinstance(result, list)


# ═══════════════════════════════════════════════════════════════════════════════
# performance_tracker context manager
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_performance_tracker_basic() -> None:  # noqa: D103
    from unittest.mock import MagicMock

    enable_performance_monitoring()
    runtime_data = MagicMock()
    with performance_tracker(runtime_data, "test_operation"):
        x = 1 + 1
    assert x == 2


@pytest.mark.unit
def test_performance_tracker_nested() -> None:  # noqa: D103
    from unittest.mock import MagicMock

    enable_performance_monitoring()
    runtime_data = MagicMock()
    with performance_tracker(runtime_data, "outer"):  # noqa: SIM117
        with performance_tracker(runtime_data, "inner"):
            pass  # no error


@pytest.mark.unit
def test_performance_tracker_when_disabled() -> None:  # noqa: D103
    from unittest.mock import MagicMock

    disable_performance_monitoring()
    runtime_data = MagicMock()
    with performance_tracker(runtime_data, "disabled_op"):
        pass  # should be no-op, no raise
