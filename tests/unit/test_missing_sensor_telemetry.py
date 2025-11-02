from __future__ import annotations

"""Unit tests for the derived PawControl sensor telemetry helpers."""

from datetime import datetime, timezone
from typing import Any, cast

from custom_components.pawcontrol.missing_sensors import (
    calculate_activity_level,
    calculate_calories_burned_today,
    calculate_hours_since,
    derive_next_feeding_time,
)
from custom_components.pawcontrol.types import (
    FeedingModuleTelemetry,
    HealthModulePayload,
    WalkModuleTelemetry,
)
from homeassistant.util import dt as dt_util


def _walk_payload(**overrides: Any) -> WalkModuleTelemetry:
    base: dict[str, Any] = {
        "status": "ready",
        "walks_today": 2,
        "total_duration_today": 60.0,
        "total_distance_today": 2000.0,
        "weekly_walks": 4,
        "weekly_distance": 8000.0,
        "needs_walk": False,
        "walk_streak": 3,
        "energy_level": "moderate",
    }
    base.update(overrides)
    return cast(WalkModuleTelemetry, base)


def _health_payload(**overrides: Any) -> HealthModulePayload:
    base: dict[str, Any] = {
        "status": "ok",
        "activity_level": "moderate",
        "weight": 25.0,
    }
    base.update(overrides)
    return cast(HealthModulePayload, base)


def _feeding_payload(**overrides: Any) -> FeedingModuleTelemetry:
    base: dict[str, Any] = {
        "status": "ready",
        "last_feeding": "2024-01-01T08:00:00+00:00",
        "total_feedings_today": 1,
        "feedings_today": {},
    }
    base.update(overrides)
    return cast(FeedingModuleTelemetry, base)


def test_calculate_activity_level_prefers_health_snapshot() -> None:
    walk_data = _walk_payload(walks_today=3, total_duration_today=95.0)
    health_data = _health_payload(activity_level="very_high")
    assert calculate_activity_level(walk_data, health_data) == "very_high"
    assert calculate_activity_level(None, None) == "unknown"


def test_calculate_calories_burned_today_applies_multiplier() -> None:
    walk_data = _walk_payload(total_distance_today=2000.0, total_duration_today=60.0)
    health_data = _health_payload(activity_level="high")
    assert calculate_calories_burned_today(walk_data, 30.0, health_data) == 1800.0


def test_calculate_hours_since_uses_reference_timestamp() -> None:
    reference = datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)  # noqa: UP017
    assert (
        calculate_hours_since("2024-01-01T10:00:00+00:00", reference=reference) == 6.0
    )
    assert calculate_hours_since(None, reference=reference) is None


def test_derive_next_feeding_time_respects_schedule() -> None:
    feeding_data = _feeding_payload(config={"meals_per_day": 3})
    assert derive_next_feeding_time(feeding_data) == "16:00"
    invalid_data = _feeding_payload(config={"meals_per_day": 0})
    assert derive_next_feeding_time(invalid_data) is None
