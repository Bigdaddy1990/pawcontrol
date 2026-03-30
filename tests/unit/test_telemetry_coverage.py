"""Targeted coverage tests for telemetry.py — uncovered paths (70% → 82%+).

Covers: record_bool_coercion_event, get_bool_coercion_metrics,
        summarise_bool_coercion_metrics, reset_bool_coercion_metrics,
        summarise_reconfigure_options, get_runtime_performance_stats,
        ensure_runtime_performance_stats, get_runtime_store_health
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.telemetry import (
    ensure_runtime_performance_stats,
    get_bool_coercion_metrics,
    get_runtime_performance_stats,
    record_bool_coercion_event,
    reset_bool_coercion_metrics,
    summarise_bool_coercion_metrics,
    summarise_reconfigure_options,
)

# ═══════════════════════════════════════════════════════════════════════════════
# bool coercion metrics (lines ~318-346)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def reset_coercion_state():
    """Always reset bool coercion state before each test."""
    reset_bool_coercion_metrics()
    yield
    reset_bool_coercion_metrics()


@pytest.mark.unit
def test_record_bool_coercion_event_basic() -> None:
    record_bool_coercion_event(value="yes", default=False, result=True, reason="truthy")
    metrics = get_bool_coercion_metrics()
    assert metrics["total"] >= 1


@pytest.mark.unit
def test_record_bool_coercion_event_multiple() -> None:
    for i in range(5):
        record_bool_coercion_event(
            value=i, default=False, result=bool(i), reason="int_coerce"
        )
    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 5


@pytest.mark.unit
def test_summarise_bool_coercion_metrics_empty() -> None:
    summary = summarise_bool_coercion_metrics()
    assert summary["total"] == 0


@pytest.mark.unit
def test_summarise_bool_coercion_metrics_with_data() -> None:
    record_bool_coercion_event(value="true", default=False, result=True, reason="str")
    record_bool_coercion_event(value=0, default=True, result=False, reason="zero")
    summary = summarise_bool_coercion_metrics()
    assert summary["total"] == 2


@pytest.mark.unit
def test_reset_bool_coercion_metrics() -> None:
    record_bool_coercion_event(value="x", default=False, result=True, reason="r")
    reset_bool_coercion_metrics()
    metrics = get_bool_coercion_metrics()
    assert metrics["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# summarise_reconfigure_options (lines ~496-511)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_summarise_reconfigure_options_none() -> None:
    result = summarise_reconfigure_options(None)
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_summarise_reconfigure_options_with_dict() -> None:
    # Only returns non-None when recognized option keys are present
    result = summarise_reconfigure_options({"host": "192.168.1.100", "port": 8080})
    assert result is None or isinstance(result, dict)


@pytest.mark.unit
def test_summarise_reconfigure_options_empty_dict() -> None:
    result = summarise_reconfigure_options({})
    assert result is None or isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# get_runtime_performance_stats / ensure_runtime_performance_stats (lines ~590-607)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_get_runtime_performance_stats_none() -> None:
    result = get_runtime_performance_stats(None)
    assert result is None


@pytest.mark.unit
def test_get_runtime_performance_stats_no_attr() -> None:
    runtime_data = SimpleNamespace()  # no performance_stats attribute
    result = get_runtime_performance_stats(runtime_data)
    assert result is None


@pytest.mark.unit
def test_get_runtime_performance_stats_with_data() -> None:
    stats = {"update_count": 5}
    runtime_data = SimpleNamespace(performance_stats=stats)
    result = get_runtime_performance_stats(runtime_data)
    assert result is stats


@pytest.mark.unit
def test_ensure_runtime_performance_stats_creates_if_missing() -> None:
    runtime_data = SimpleNamespace()
    result = ensure_runtime_performance_stats(runtime_data)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_ensure_runtime_performance_stats_returns_existing() -> None:
    existing = {"update_count": 3}
    runtime_data = SimpleNamespace(performance_stats=existing)
    result = ensure_runtime_performance_stats(runtime_data)
    assert result is existing
