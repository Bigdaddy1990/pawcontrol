from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from typing import cast

from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.missing_sensors import (
    _feeding_payload,
    _health_payload,
    _normalise_attributes,
    _walk_payload,
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


def _make_walk_payload(
    overrides: Mapping[str, object] | None = None,
) -> WalkModuleTelemetry:
    base: WalkModuleTelemetry = {
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
    if overrides:
        base.update(overrides)
    return cast(WalkModuleTelemetry, base)


def _make_health_payload(
    overrides: Mapping[str, object] | None = None,
) -> HealthModulePayload:
    base: HealthModulePayload = {
        "status": "ok",
        "activity_level": "moderate",
        "weight": 25.0,
    }
    if overrides:
        base.update(overrides)
    return cast(HealthModulePayload, base)


def _make_feeding_payload(
    overrides: Mapping[str, object] | None = None,
) -> FeedingModuleTelemetry:
    base: FeedingModuleTelemetry = {
        "status": "ready",
        "last_feeding": "2024-01-01T08:00:00+00:00",
        "total_feedings_today": 1,
        "feedings_today": {},
    }
    if overrides:
        base.update(overrides)
    return cast(FeedingModuleTelemetry, base)


def test_calculate_activity_level_prefers_health_snapshot() -> None:
    walk_data = _make_walk_payload({"walks_today": 3, "total_duration_today": 95.0})
    health_data = _make_health_payload({"activity_level": "very_high"})
    assert calculate_activity_level(walk_data, health_data) == "very_high"
    assert calculate_activity_level(None, None) == "unknown"


def test_module_payload_helpers_filter_non_mapping_module_data() -> None:
    @dataclass(slots=True)
    class _Provider:
        value: object

        def _get_module_data(self, module: str) -> object:
            return self.value if module == "walk" else None

    assert _walk_payload(_Provider(value={"walks_today": 1})) == {"walks_today": 1}
    assert _walk_payload(_Provider(value=["unexpected"])) is None


def test_health_and_feeding_payload_helpers_use_module_specific_keys() -> None:
    @dataclass(slots=True)
    class _Provider:
        values: dict[str, object]

        def _get_module_data(self, module: str) -> object:
            return self.values.get(module)

    provider = _Provider(
        values={
            "health": {"activity_level": "high"},
            "feeding": {"last_feeding": "2024-01-01T10:00:00+00:00"},
        }
    )

    assert _health_payload(provider) == {"activity_level": "high"}
    assert _feeding_payload(provider) == {"last_feeding": "2024-01-01T10:00:00+00:00"}


def test_normalise_attributes_converts_datetimes_to_isoformat() -> None:
    attrs = {
        "last_updated": datetime(2024, 1, 1, 12, 30, tzinfo=UTC),
        "count": 3,
    }

    assert _normalise_attributes(attrs) == {
        "last_updated": "2024-01-01T12:30:00+00:00",
        "count": 3,
    }


def test_calculate_activity_level_handles_invalid_payloads() -> None:
    """Invalid payload values should return unknown instead of raising."""
    walk_data = _make_walk_payload({"walks_today": "not-a-number"})
    assert calculate_activity_level(walk_data, None) == "unknown"

    # Unknown health strings should not break the calculated baseline.
    health_data = _make_health_payload({"activity_level": "unexpected"})
    assert calculate_activity_level(_make_walk_payload(), health_data) == "high"


def test_calculate_calories_burned_today_applies_multiplier() -> None:
    walk_data = _make_walk_payload({
        "total_distance_today": 2000.0,
        "total_duration_today": 60.0,
    })
    health_data = _make_health_payload({"activity_level": "high"})
    assert calculate_calories_burned_today(walk_data, 30.0, health_data) == 1800.0


def test_calculate_calories_burned_today_handles_invalid_numeric_input() -> None:
    """Invalid telemetry should be coerced to a safe 0.0 response."""
    walk_data = _make_walk_payload({"total_duration_today": "broken"})
    assert calculate_calories_burned_today(walk_data, 25.0, None) == 0.0

    assert calculate_calories_burned_today(None, 25.0, None) == 0.0


def test_calculate_hours_since_uses_reference_timestamp() -> None:
    reference = datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)  # noqa: UP017
    assert (
        calculate_hours_since("2024-01-01T10:00:00+00:00", reference=reference) == 6.0
    )
    assert calculate_hours_since(None, reference=reference) is None


def test_calculate_hours_since_rejects_unparseable_timestamps() -> None:
    reference = datetime(2024, 1, 1, 16, 0, tzinfo=timezone.utc)  # noqa: UP017
    assert calculate_hours_since("not-a-timestamp", reference=reference) is None


def test_derive_next_feeding_time_respects_schedule() -> None:
    feeding_data = _make_feeding_payload({"config": {"meals_per_day": 3}})
    assert derive_next_feeding_time(feeding_data) == "16:00"
    invalid_data = _make_feeding_payload({"config": {"meals_per_day": 0}})
    assert derive_next_feeding_time(invalid_data) is None


def test_derive_next_feeding_time_handles_missing_or_invalid_fields() -> None:
    """Scheduling helper should short-circuit on malformed input payloads."""
    assert derive_next_feeding_time(None) is None
    assert derive_next_feeding_time(_make_feeding_payload()) is None
    assert derive_next_feeding_time(_make_feeding_payload({"config": {}})) is None
    assert (
        derive_next_feeding_time(
            _make_feeding_payload({"config": {"meals_per_day": "x"}})
        )
        is None
    )
    assert (
        derive_next_feeding_time(
            _make_feeding_payload({
                "config": {"meals_per_day": 2},
                "last_feeding": "not-a-datetime",
            })
        )
        is None
    )
