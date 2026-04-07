"""Hotspot package 4: sensor native value and fallback guard coverage."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import sensor


class _ProbeSensor(sensor.PawControlSensorBase):
    """Concrete probe for base sensor behavior."""

    @property
    def native_value(self) -> str:
        return "probe"


def _build_probe() -> _ProbeSensor:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return _ProbeSensor(coordinator, "dog-1", "Rex", "probe")


def _build_hours_sensor() -> sensor.PawControlLastFeedingHoursSensor:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return sensor.PawControlLastFeedingHoursSensor(coordinator, "dog-1", "Rex")


@pytest.mark.parametrize(
    ("coordinator_available", "dog_data", "expected"),
    [
        (True, {"dog_id": "dog-1"}, True),
        (False, {"dog_id": "dog-1"}, False),
        (True, None, False),
    ],
)
def test_base_sensor_available_requires_coordinator_and_dog_data(
    coordinator_available: bool,
    dog_data: object,
    expected: bool,
) -> None:
    """Availability should short-circuit when coordinator or dog payload is missing."""
    probe = _build_probe()
    probe.coordinator.available = coordinator_available
    probe._get_dog_data = lambda: dog_data

    assert probe.available is expected


@pytest.mark.parametrize(
    ("config_payload", "last_feeding", "expected_iso"),
    [
        ({"meals_per_day": 4}, datetime(2026, 4, 7, 8, 0), "2026-04-07T14:00:00"),
        ({"meals_per_day": 0}, datetime(2026, 4, 7, 8, 0), None),
        ("invalid", datetime(2026, 4, 7, 8, 0), "2026-04-07T20:00:00"),
    ],
)
def test_calculate_next_feeding_due_handles_config_variants(
    config_payload: object,
    last_feeding: datetime,
    expected_iso: str | None,
) -> None:
    """Next-feeding calculation should support mapping and fallback paths."""
    feeding_sensor = _build_hours_sensor()
    payload = {"config": config_payload}

    result = feeding_sensor._calculate_next_feeding_due(payload, last_feeding)

    assert result == expected_iso


@pytest.mark.parametrize(
    ("raw_value", "default", "expected"),
    [
        (True, 0, 1),
        ("7.9", 0, 7),
        ("bad", 5, 5),
        (object(), 3, 3),
    ],
)
def test_coerce_int_defensive_guards(
    raw_value: object, default: int, expected: int
) -> None:
    """Integer coercion should safely clamp invalid or unsupported payload types."""
    probe = _build_probe()

    assert probe._coerce_int(raw_value, default) == expected


@pytest.mark.parametrize(
    ("walk_payload", "expected"),
    [
        ({"total_duration_today": "35", "total_distance_today": "2500"}, 280.0),
        ({"total_duration_today": None, "total_distance_today": "bad"}, 0.0),
        ({"total_duration_today": 20, "total_distance_today": 1000}, 128.0),
    ],
)
def test_calories_sensor_native_value_fallback_paths(
    monkeypatch: pytest.MonkeyPatch,
    walk_payload: dict[str, object],
    expected: float,
) -> None:
    """Calories sensor should use direct value or defensive activity fallback."""
    calories_sensor = sensor.PawControlCaloriesBurnedTodaySensor(
        SimpleNamespace(available=True, update_interval=timedelta(minutes=5)),
        "dog-1",
        "Rex",
    )
    calories_sensor._get_walk_module = lambda: walk_payload
    monkeypatch.setattr(
        calories_sensor,
        "_get_dog_data",
        lambda: {"dog_info": {"dog_weight": 10}},
    )

    assert calories_sensor.native_value == pytest.approx(expected, abs=0.1)
