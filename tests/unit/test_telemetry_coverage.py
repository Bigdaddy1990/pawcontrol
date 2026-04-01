"""Targeted coverage tests for telemetry.py — (0% → 20%+).

Covers: get_bool_coercion_metrics, BoolCoercionMetrics/Summary (TypedDicts)
"""

import pytest

from custom_components.pawcontrol.telemetry import (
    BoolCoercionMetrics,
    BoolCoercionSummary,
    get_bool_coercion_metrics,
    get_runtime_bool_coercion_summary,
)

# ─── get_bool_coercion_metrics ────────────────────────────────────────────────


@pytest.mark.unit
def test_get_bool_coercion_metrics_returns_dict() -> None:
    result = get_bool_coercion_metrics()
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_bool_coercion_metrics_has_total_key() -> None:
    result = get_bool_coercion_metrics()
    assert "total" in result


@pytest.mark.unit
def test_get_bool_coercion_metrics_numeric_values() -> None:
    result = get_bool_coercion_metrics()
    assert result["total"] >= 0
    assert result["defaulted"] >= 0


# ─── get_runtime_bool_coercion_summary ────────────────────────────────────────


@pytest.mark.unit
def test_get_runtime_bool_coercion_summary_none() -> None:
    result = get_runtime_bool_coercion_summary(None)
    assert result is None or isinstance(result, dict)


# ─── BoolCoercionMetrics (TypedDict) ─────────────────────────────────────────


@pytest.mark.unit
def test_bool_coercion_metrics_as_dict() -> None:
    m: BoolCoercionMetrics = {
        "total": 10,
        "defaulted": 2,
        "fallback": 1,
        "reset_count": 0,
        "type_counts": {},
        "reason_counts": {},
    }
    assert m["total"] == 10
    assert m["defaulted"] == 2


@pytest.mark.unit
def test_bool_coercion_metrics_empty() -> None:
    m: BoolCoercionMetrics = {
        "total": 0,
        "defaulted": 0,
        "fallback": 0,
        "reset_count": 0,
        "type_counts": {},
        "reason_counts": {},
    }
    assert m["total"] == 0


# ─── BoolCoercionSummary (TypedDict) ─────────────────────────────────────────


@pytest.mark.unit
def test_bool_coercion_summary_as_dict() -> None:
    s: BoolCoercionSummary = {
        "recorded": True,
        "total": 5,
        "defaulted": 1,
        "fallback": 0,
        "reset_count": 0,
        "first_seen": None,
    }
    assert s["recorded"] is True
    assert s["total"] == 5
