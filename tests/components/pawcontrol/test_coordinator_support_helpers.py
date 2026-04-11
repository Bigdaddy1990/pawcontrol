"""Coverage tests for coordinator support helper functions."""

from types import SimpleNamespace

from custom_components.pawcontrol import coordinator_support
from custom_components.pawcontrol.types import CacheRepairAggregate


def test_build_repair_telemetry_returns_none_for_empty_summary() -> None:
    """Falsy summaries should not emit telemetry payloads."""
    assert coordinator_support._build_repair_telemetry(None) is None


def test_build_repair_telemetry_counts_only_nonempty_entries() -> None:
    """Telemetry should only include non-empty string counters and issue totals."""
    summary = CacheRepairAggregate(
        total_caches=4,
        anomaly_count=3,
        severity="warning",
        generated_at="2026-04-11T10:00:00+00:00",
        caches_with_errors=["api", "", "sync"],
        caches_with_expired_entries=["metrics", ""],
        caches_with_pending_expired_entries=["pending"],
        caches_with_override_flags=["", "door"],
        caches_with_low_hit_rate=["weather", ""],
        issues=[{"cache": "api"}],
    )

    assert coordinator_support._build_repair_telemetry(summary) == {
        "severity": "warning",
        "anomaly_count": 3,
        "total_caches": 4,
        "generated_at": "2026-04-11T10:00:00+00:00",
        "issues": 1,
        "caches_with_errors": 2,
        "caches_with_expired_entries": 1,
        "caches_with_pending_expired_entries": 1,
        "caches_with_override_flags": 1,
        "caches_with_low_hit_rate": 1,
    }


def test_ensure_cache_repair_aggregate_uses_runtime_types_module(monkeypatch) -> None:
    """Runtime types module overrides should still recognize aggregate payloads."""
    replacement_aggregate = type("ReplacementAggregate", (), {})
    runtime_types = SimpleNamespace(CacheRepairAggregate=replacement_aggregate)
    monkeypatch.setitem(
        coordinator_support.sys.modules,
        "custom_components.pawcontrol.types",
        runtime_types,
    )

    replacement_instance = replacement_aggregate()

    assert (
        coordinator_support.ensure_cache_repair_aggregate(replacement_instance)
        is replacement_instance
    )
    assert coordinator_support.ensure_cache_repair_aggregate(object()) is None
