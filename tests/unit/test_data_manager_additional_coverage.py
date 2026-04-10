"""Additional branch coverage for data_manager cache/report helpers."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager


@pytest.mark.unit
def test_cache_repair_summary_collects_errors_and_normalizes_values() -> None:
    """Cache repair summaries should normalize numeric text and anomaly payloads."""
    manager = object.__new__(PawControlDataManager)

    summary = manager.cache_repair_summary({
        "": {"stats": {"entries": 99}},  # ignored empty cache name
        "feeding": {
            "stats": {
                "entries": "4",
                "hits": "2",
                "misses": "3",
            },
            "diagnostics": {
                "expired_entries": "2",
                "pending_expired_entries": "1",
                "active_override_flags": "1",
                "errors": "cache read timeout",
                "timestamp_anomalies": {"buddy": "clock skew"},
            },
        },
    })

    assert summary is not None
    assert summary.severity == "error"
    assert summary.total_caches == 2
    assert summary.anomaly_count == 1
    assert summary.totals.entries == 4
    assert summary.totals.hits == 2
    assert summary.totals.misses == 3
    assert summary.totals.expired_entries == 2
    assert summary.caches_with_errors == ["feeding"]
    assert summary.issues is not None
    assert summary.issues[0]["timestamp_anomalies"] == {"buddy": "clock skew"}
    assert summary.issues[0]["errors"] == ["cache read timeout"]


@pytest.mark.unit
def test_cache_repair_summary_derives_hit_rate_when_missing() -> None:
    """Summaries should derive low hit-rate anomalies from hits/misses counts."""
    manager = object.__new__(PawControlDataManager)

    summary = manager.cache_repair_summary({
        "health": {
            "stats": {
                "entries": 5,
                "hits": 1,
                "misses": 4,
            },
            "diagnostics": {},
        }
    })

    assert summary is not None
    assert summary.severity == "warning"
    assert summary.caches_with_low_hit_rate == ["health"]
    assert summary.caches_with_errors is None
    assert summary.totals.overall_hit_rate == 20.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_get_module_history_filters_sorts_and_limits() -> None:
    """History retrieval should filter by bounds and sort newest-first."""
    manager = object.__new__(PawControlDataManager)

    now = datetime.now(UTC)
    manager._dog_profiles = {
        "buddy": SimpleNamespace(
            health_history=[
                {"timestamp": (now - timedelta(days=2)).isoformat(), "weight": 10},
                {"timestamp": (now - timedelta(hours=2)).isoformat(), "weight": 11},
                {"timestamp": "not-a-date", "weight": 12},
                123,
            ]
        )
    }

    result = await manager.async_get_module_history(
        "health",
        "buddy",
        since=now - timedelta(days=1),
        limit=1,
    )

    assert len(result) == 1
    assert result[0]["weight"] == 11

    assert await manager.async_get_module_history("unknown", "buddy") == []
    assert await manager.async_get_module_history("health", "missing") == []
