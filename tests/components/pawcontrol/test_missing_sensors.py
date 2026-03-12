"""Unit tests for derived telemetry helper functions in missing_sensors."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.pawcontrol import missing_sensors


class _IndexErrorMapping(dict[str, object]):
    """Mapping that raises IndexError for any key access."""

    def __getitem__(self, key: str) -> object:
        raise IndexError(key)


def test_calculate_activity_level_handles_none_payloads() -> None:
    """Missing walk and health payloads should produce unknown activity."""
    assert missing_sensors.calculate_activity_level(None, None) == "unknown"


@pytest.mark.parametrize(
    ("walk_data", "health_data", "expected"),
    [
        ({"walks_today": 3, "total_duration_today": 100.0}, None, "very_high"),
        ({"walks_today": 2, "total_duration_today": 60.0}, None, "high"),
        ({"walks_today": 1, "total_duration_today": 45.0}, None, "moderate"),
        ({"walks_today": 1, "total_duration_today": 10.0}, None, "low"),
        ({"walks_today": 0, "total_duration_today": 0.0}, None, "very_low"),
        (
            {"walks_today": 1, "total_duration_today": 30.0},
            {"activity_level": "high"},
            "high",
        ),
    ],
)
def test_calculate_activity_level_thresholds_and_health_override(
    walk_data: dict[str, object],
    health_data: dict[str, object] | None,
    expected: str,
) -> None:
    """Walk thresholds and optional health override should be respected."""
    assert missing_sensors.calculate_activity_level(walk_data, health_data) == expected


@pytest.mark.parametrize(
    "walk_data",
    [
        {"walks_today": "bad", "total_duration_today": 20.0},
        _IndexErrorMapping({"walks_today": 1}),
    ],
)
def test_calculate_activity_level_handles_invalid_inputs(walk_data: object) -> None:
    """Conversion/index errors should fall back to unknown activity level."""
    assert (
        missing_sensors.calculate_activity_level(
            walk_data,  # type: ignore[arg-type]
            {"activity_level": "low"},
        )
        == "unknown"
    )


def test_calculate_calories_burned_today_uses_multiplier() -> None:
    """Calories should combine duration and distance with health multiplier."""
    walk_data = {"total_duration_today": 30, "total_distance_today": 500}
    health_data = {"activity_level": "high"}

    assert (
        missing_sensors.calculate_calories_burned_today(
            walk_data,
            dog_weight_kg=10.0,
            health_data=health_data,
        )
        == 240.0
    )


@pytest.mark.parametrize(
    ("walk_data", "health_data"),
    [
        ({"total_duration_today": "bad", "total_distance_today": 100}, None),
        ({"total_duration_today": object(), "total_distance_today": 100}, None),
        (None, None),
    ],
)
def test_calculate_calories_burned_today_handles_invalid_data(
    walk_data: dict[str, object] | None,
    health_data: dict[str, object] | None,
) -> None:
    """Bad inputs or absent payloads should produce zero calories."""
    assert (
        missing_sensors.calculate_calories_burned_today(
            walk_data,  # type: ignore[arg-type]
            dog_weight_kg=12.0,
            health_data=health_data,  # type: ignore[arg-type]
        )
        == 0.0
    )


def test_calculate_hours_since_uses_reference_time() -> None:
    """Hour deltas should be measured from the explicit reference timestamp."""
    reference = datetime(2025, 1, 1, 12, tzinfo=UTC)
    timestamp = reference - timedelta(hours=2, minutes=30)

    result = missing_sensors.calculate_hours_since(timestamp, reference=reference)

    assert result == 2.5


@pytest.mark.parametrize("timestamp", [None, "not-a-date"])
def test_calculate_hours_since_handles_missing_or_invalid_timestamp(
    timestamp: object,
) -> None:
    """Invalid timestamps should return ``None`` instead of raising."""
    assert (
        missing_sensors.calculate_hours_since(  # type: ignore[arg-type]
            timestamp,
            reference=datetime(2025, 1, 1, tzinfo=UTC),
        )
        is None
    )


def test_derive_next_feeding_time_returns_formatted_time() -> None:
    """A valid feeding config should compute the next HH:MM feeding slot."""
    feeding_data = {
        "config": {"meals_per_day": 3},
        "last_feeding": "2025-01-01T06:00:00+00:00",
    }

    assert missing_sensors.derive_next_feeding_time(feeding_data) == "14:00"


@pytest.mark.parametrize(
    "feeding_data",
    [
        None,
        {},
        {"config": {}, "last_feeding": "2025-01-01T06:00:00+00:00"},
        {"config": {"meals_per_day": 0}, "last_feeding": "2025-01-01T06:00:00+00:00"},
        {
            "config": {"meals_per_day": "bad"},
            "last_feeding": "2025-01-01T06:00:00+00:00",
        },
        {"config": {"meals_per_day": 2}, "last_feeding": None},
        {"config": {"meals_per_day": 2}, "last_feeding": "invalid"},
    ],
)
def test_derive_next_feeding_time_handles_invalid_payloads(
    feeding_data: dict[str, object] | None,
) -> None:
    """Invalid feeding payloads should return ``None`` safely."""
    assert missing_sensors.derive_next_feeding_time(feeding_data) is None
