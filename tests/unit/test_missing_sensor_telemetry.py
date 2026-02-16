from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import cast

from homeassistant.util import dt as dt_util

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

"""Unit tests for the derived PawControl sensor telemetry helpers."""


def _walk_payload(
  overrides: Mapping[str, object] | None = None,
) -> WalkModuleTelemetry:
  base: WalkModuleTelemetry = {  # noqa: E111
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
  if overrides:  # noqa: E111
    base.update(overrides)
  return cast(WalkModuleTelemetry, base)  # noqa: E111


def _health_payload(
  overrides: Mapping[str, object] | None = None,
) -> HealthModulePayload:
  base: HealthModulePayload = {  # noqa: E111
    "status": "ok",
    "activity_level": "moderate",
    "weight": 25.0,
  }
  if overrides:  # noqa: E111
    base.update(overrides)
  return cast(HealthModulePayload, base)  # noqa: E111


def _feeding_payload(
  overrides: Mapping[str, object] | None = None,
) -> FeedingModuleTelemetry:
  base: FeedingModuleTelemetry = {  # noqa: E111
    "status": "ready",
    "last_feeding": "2024-01-01T08:00:00+00:00",
    "total_feedings_today": 1,
    "feedings_today": {},
  }
  if overrides:  # noqa: E111
    base.update(overrides)
  return cast(FeedingModuleTelemetry, base)  # noqa: E111


def test_calculate_activity_level_prefers_health_snapshot() -> None:
  walk_data = _walk_payload({"walks_today": 3, "total_duration_today": 95.0})  # noqa: E111
  health_data = _health_payload({"activity_level": "very_high"})  # noqa: E111
  assert calculate_activity_level(walk_data, health_data) == "very_high"  # noqa: E111
  assert calculate_activity_level(None, None) == "unknown"  # noqa: E111


def test_calculate_calories_burned_today_applies_multiplier() -> None:
  walk_data = _walk_payload({  # noqa: E111
    "total_distance_today": 2000.0,
    "total_duration_today": 60.0,
  })
  health_data = _health_payload({"activity_level": "high"})  # noqa: E111
  assert calculate_calories_burned_today(walk_data, 30.0, health_data) == 1800.0  # noqa: E111


def test_calculate_hours_since_uses_reference_timestamp() -> None:
  reference = datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)  # noqa: E111, UP017
  assert calculate_hours_since("2024-01-01T10:00:00+00:00", reference=reference) == 6.0  # noqa: E111
  assert calculate_hours_since(None, reference=reference) is None  # noqa: E111


def test_derive_next_feeding_time_respects_schedule() -> None:
  feeding_data = _feeding_payload({"config": {"meals_per_day": 3}})  # noqa: E111
  assert derive_next_feeding_time(feeding_data) == "16:00"  # noqa: E111
  invalid_data = _feeding_payload({"config": {"meals_per_day": 0}})  # noqa: E111
  assert derive_next_feeding_time(invalid_data) is None  # noqa: E111
