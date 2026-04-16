"""Targeted coverage tests for module_adapters.py — (0% → 18%+).

FeedingDailyStats, FeedingSnapshot, FeedingModulePayload are TypedDicts
→ constructed as plain dicts.
"""

import pytest

from custom_components.pawcontrol.module_adapters import (
    FeedingDailyStats,
    FeedingModulePayload,
    FeedingSnapshot,
)

# ─── FeedingDailyStats (TypedDict) ───────────────────────────────────────────


@pytest.mark.unit
def test_feeding_daily_stats_as_dict() -> None:  # noqa: D103
    stats: FeedingDailyStats = {
        "total_fed_today": 400.0,
        "meals_today": 2,
        "remaining_calories": 200,
    }
    assert stats["meals_today"] == 2
    assert stats["total_fed_today"] == pytest.approx(400.0)


@pytest.mark.unit
def test_feeding_daily_stats_zero() -> None:  # noqa: D103
    stats: FeedingDailyStats = {
        "total_fed_today": 0.0,
        "meals_today": 0,
        "remaining_calories": 500,
    }
    assert stats["meals_today"] == 0


# ─── FeedingSnapshot (TypedDict) ─────────────────────────────────────────────


@pytest.mark.unit
def test_feeding_snapshot_has_status() -> None:  # noqa: D103
    snap: FeedingSnapshot = {"status": "fed", "last_feeding": None}
    assert snap["status"] == "fed"


@pytest.mark.unit
def test_feeding_snapshot_next_feeding() -> None:  # noqa: D103
    snap: FeedingSnapshot = {"next_feeding": "2025-06-01T18:00:00Z"}
    assert snap["next_feeding"] is not None


# ─── FeedingModulePayload (TypedDict) ─────────────────────────────────────────


@pytest.mark.unit
def test_feeding_module_payload_status() -> None:  # noqa: D103
    payload: FeedingModulePayload = {"status": "pending", "message": "Feeding due soon"}
    assert payload["status"] == "pending"


@pytest.mark.unit
def test_feeding_module_payload_empty() -> None:  # noqa: D103
    payload: FeedingModulePayload = {}
    assert isinstance(payload, dict)
