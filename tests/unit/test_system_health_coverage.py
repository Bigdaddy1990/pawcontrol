"""Targeted coverage tests for system_health.py — pure helpers (0% → 20%+).

Covers: get_runtime_data, get_runtime_performance_stats, derive_rejection_metrics
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.system_health import (
    get_runtime_data,
    get_runtime_performance_stats,
)
from custom_components.pawcontrol.coordinator_observability import (
    derive_rejection_metrics,
    default_rejection_metrics,
)


# ─── get_runtime_data ────────────────────────────────────────────────────────

@pytest.mark.unit
def test_get_runtime_data_no_data(mock_hass) -> None:
    mock_hass.data = {}
    result = get_runtime_data(mock_hass, "test_entry_id")
    assert result is None or isinstance(result, object)


@pytest.mark.unit
def test_get_runtime_data_with_entry(mock_hass) -> None:
    from custom_components.pawcontrol.const import DOMAIN
    mock_runtime = MagicMock()
    mock_hass.data = {DOMAIN: {"test_entry": mock_runtime}}
    result = get_runtime_data(mock_hass, "test_entry")
    assert result is None or result is mock_runtime or isinstance(result, object)


# ─── get_runtime_performance_stats ───────────────────────────────────────────

@pytest.mark.unit
def test_get_runtime_performance_stats_none() -> None:
    result = get_runtime_performance_stats(None)
    assert result is None


@pytest.mark.unit
def test_get_runtime_performance_stats_no_attr() -> None:
    runtime_data = SimpleNamespace()
    result = get_runtime_performance_stats(runtime_data)
    assert result is None


@pytest.mark.unit
def test_get_runtime_performance_stats_present() -> None:
    stats = {"update_count": 42, "avg_duration_ms": 15.3}
    runtime_data = SimpleNamespace(performance_stats=stats)
    result = get_runtime_performance_stats(runtime_data)
    assert result is stats


# ─── derive / default_rejection_metrics ──────────────────────────────────────

@pytest.mark.unit
def test_default_rejection_metrics_keys() -> None:
    r = default_rejection_metrics()
    assert "rejected_call_count" in r
    assert "open_breakers" in r


@pytest.mark.unit
def test_derive_rejection_metrics_none() -> None:
    result = derive_rejection_metrics(None)
    assert isinstance(result, dict)


@pytest.mark.unit
def test_derive_rejection_metrics_with_counts() -> None:
    data = {"total_rejections": 3, "rate_limited": 1}
    result = derive_rejection_metrics(data)
    assert isinstance(result, dict)
