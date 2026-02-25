"""Unit tests for cache repair helper utilities."""

from __future__ import annotations

from dataclasses import dataclass
import sys

from custom_components.pawcontrol.coordinator_support import (
    _build_repair_telemetry,
    ensure_cache_repair_aggregate,
)
from custom_components.pawcontrol.types import CacheRepairAggregate


@dataclass(slots=True)
class _AltAggregate:
    """Alternative aggregate type used to validate module-class detection."""

    total_caches: int


class _TypesModuleStub:
    """Stub module object exposing a replacement aggregate class."""

    CacheRepairAggregate = _AltAggregate


def test_build_repair_telemetry_returns_none_without_summary() -> None:
    """None or empty summaries should not produce telemetry."""
    assert _build_repair_telemetry(None) is None


def test_build_repair_telemetry_counts_only_non_empty_entries() -> None:
    """Telemetry should include only populated anomaly counters."""
    summary = CacheRepairAggregate(
        total_caches=3,
        anomaly_count=2,
        severity="warning",
        generated_at="2026-01-01T00:00:00+00:00",
        caches_with_errors=["cache-a", "", "cache-b", 0],  # type: ignore[list-item]
        caches_with_expired_entries=["cache-a"],
        caches_with_pending_expired_entries=["cache-c", ""],
        caches_with_override_flags=["cache-a"],
        caches_with_low_hit_rate=["cache-b"],
        issues=[{"cache": "cache-a"}, {"cache": "cache-b"}],
    )

    telemetry = _build_repair_telemetry(summary)

    assert telemetry == {
        "severity": "warning",
        "anomaly_count": 2,
        "total_caches": 3,
        "generated_at": "2026-01-01T00:00:00+00:00",
        "issues": 2,
        "caches_with_errors": 2,
        "caches_with_expired_entries": 1,
        "caches_with_pending_expired_entries": 1,
        "caches_with_override_flags": 1,
        "caches_with_low_hit_rate": 1,
    }


def test_ensure_cache_repair_aggregate_supports_runtime_rebound_class(
    monkeypatch,
) -> None:
    """When types module is rebound, helper should still accept that class."""
    summary = _AltAggregate(total_caches=1)
    monkeypatch.setitem(
        sys.modules,
        "custom_components.pawcontrol.types",
        _TypesModuleStub(),
    )

    assert ensure_cache_repair_aggregate(summary) is summary


def test_ensure_cache_repair_aggregate_rejects_non_matching_object() -> None:
    """Unknown summary objects should be discarded."""
    assert ensure_cache_repair_aggregate(object()) is None
