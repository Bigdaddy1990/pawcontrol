"""Targeted coverage tests for telemetry.py — (0% → 20%+).

Covers: get_bool_coercion_metrics, BoolCoercionMetrics/Summary (TypedDicts)
"""

from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import telemetry
from custom_components.pawcontrol.telemetry import (
    BoolCoercionMetrics,
    BoolCoercionSummary,
    get_bool_coercion_metrics,
    get_runtime_bool_coercion_summary,
)

# ─── get_bool_coercion_metrics ────────────────────────────────────────────────


@pytest.mark.unit
def test_get_bool_coercion_metrics_returns_dict() -> None:  # noqa: D103
    result = get_bool_coercion_metrics()
    assert isinstance(result, dict)


@pytest.mark.unit
def test_get_bool_coercion_metrics_has_total_key() -> None:  # noqa: D103
    result = get_bool_coercion_metrics()
    assert "total" in result


@pytest.mark.unit
def test_get_bool_coercion_metrics_numeric_values() -> None:  # noqa: D103
    result = get_bool_coercion_metrics()
    assert result["total"] >= 0
    assert result["defaulted"] >= 0


# ─── get_runtime_bool_coercion_summary ────────────────────────────────────────


@pytest.mark.unit
def test_get_runtime_bool_coercion_summary_none() -> None:  # noqa: D103
    result = get_runtime_bool_coercion_summary(None)
    assert result is None or isinstance(result, dict)


# ─── BoolCoercionMetrics (TypedDict) ─────────────────────────────────────────


@pytest.mark.unit
def test_bool_coercion_metrics_as_dict() -> None:  # noqa: D103
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
def test_bool_coercion_metrics_empty() -> None:  # noqa: D103
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
def test_bool_coercion_summary_as_dict() -> None:  # noqa: D103
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


@pytest.mark.unit
def test_get_runtime_bool_coercion_summary_mapping_branch() -> None:
    """Runtime summary getter should return copied mappings when present."""
    runtime_data = SimpleNamespace(
        performance_stats={
            "bool_coercion_summary": {
                "recorded": True,
                "total": 1,
            }
        }
    )
    summary = get_runtime_bool_coercion_summary(runtime_data)
    assert summary is not None
    assert summary["recorded"] is True


@pytest.mark.unit
def test_summarise_bool_coercion_metrics_handles_non_sequence_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Summary builder should degrade gracefully when samples are malformed."""
    monkeypatch.setattr(
        telemetry,
        "get_bool_coercion_metrics",
        lambda: {
            "total": 1,
            "defaulted": 0,
            "fallback": 0,
            "reset_count": 0,
            "reason_counts": {"fallback": 1},
            "type_counts": {"str": 1},
            "samples": 123,
        },
    )
    summary = telemetry.summarise_bool_coercion_metrics(sample_limit=2)
    assert summary["reason_counts"] == {"fallback": 1}
    assert summary["type_counts"] == {"str": 1}
    assert summary["samples"] == []


@pytest.mark.unit
def test_scalar_list_repr_and_window_helpers_cover_fallback_paths() -> None:
    """Small helper functions should handle malformed and edge-case inputs."""
    assert telemetry._as_int(True) == 1
    assert telemetry._as_int(object()) == 0
    assert telemetry._as_list(None) == []

    shortened = telemetry._safe_repr("x" * 100, limit=10)
    assert shortened.endswith("…")

    assert telemetry._calculate_active_window_seconds("invalid", "invalid") is None
    assert (
        telemetry._calculate_active_window_seconds(
            "2026-04-17T12:00:00+00:00",
            "2026-04-17T11:59:00+00:00",
        )
        == 0.0
    )


@pytest.mark.unit
def test_runtime_performance_store_helpers_cover_none_branches() -> None:
    """Runtime-store helper accessors should return ``None`` for invalid containers."""
    snapshot = {
        "status": "current",
        "entry": {"status": "current"},
        "store": {"status": "current"},
        "divergence_detected": False,
    }

    assert telemetry.get_runtime_performance_stats(None) is None
    assert telemetry.update_runtime_store_health(None, snapshot) is None

    runtime_invalid = SimpleNamespace(performance_stats="invalid")
    assert telemetry.get_runtime_performance_stats(runtime_invalid) is None

    runtime_data = SimpleNamespace()
    stats = telemetry.ensure_runtime_performance_stats(runtime_data)
    assert isinstance(stats, dict)
    assert telemetry.get_runtime_entity_factory_guard_metrics(runtime_data) is None
    assert telemetry.get_runtime_store_health(runtime_data) is None


@pytest.mark.unit
def test_runtime_bool_coercion_summary_helpers_cover_mapping_and_store_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime bool-coercion helpers should return None for invalid data and store summaries."""
    runtime_invalid = SimpleNamespace(performance_stats={"bool_coercion_summary": "bad"})
    assert telemetry.get_runtime_bool_coercion_summary(runtime_invalid) is None

    runtime_data = SimpleNamespace(performance_stats={})
    monkeypatch.setattr(
        telemetry,
        "summarise_bool_coercion_metrics",
        lambda sample_limit=5: {
            "recorded": True,
            "total": sample_limit,
            "defaulted": 0,
            "fallback": 0,
            "reset_count": 0,
            "samples": [],
        },
    )
    summary = telemetry.update_runtime_bool_coercion_summary(
        runtime_data,
        sample_limit=3,
    )
    assert summary["total"] == 3
    assert runtime_data.performance_stats["bool_coercion_summary"]["total"] == 3


@pytest.mark.unit
def test_record_bool_coercion_event_recreates_missing_last_reset() -> None:
    """Recording coercions should repopulate ``last_reset`` when absent."""
    telemetry.reset_bool_coercion_metrics()
    telemetry._BOOL_COERCION_METRICS["last_reset"] = None
    telemetry.record_bool_coercion_event(
        value="yes",
        default=False,
        result=True,
        reason="truthy_string",
    )
    metrics = telemetry.get_bool_coercion_metrics()
    assert metrics["last_reset"] is not None
