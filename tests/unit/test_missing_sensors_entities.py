"""Entity-focused coverage tests for ``missing_sensors`` sensors."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from custom_components.pawcontrol import missing_sensors


@dataclass(slots=True)
class _Entry:
    entry_id: str = "entry-1"


class _Coordinator:
    """Minimal coordinator double for missing sensor entity tests."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, Any]] = {}
        self.config_entry = _Entry()
        self.last_update_success = True
        self.last_update_success_time = datetime(2026, 1, 1, tzinfo=UTC)
        self.last_exception = None
        self.runtime_managers = None
        self.available = True

    def async_add_listener(self, _callback):
        return lambda: None

    async def async_request_refresh(self) -> None:
        return None

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        return self.data.get(dog_id)

    def get_enabled_modules(self, _dog_id: str) -> frozenset[str]:
        return frozenset()


def _coordinator() -> _Coordinator:
    coordinator = _Coordinator()
    coordinator.data["dog-1"] = {
        "dog_info": {
            "dog_id": "dog-1",
            "dog_name": "Buddy",
            "dog_weight": "20.0",
        }
    }
    return coordinator


def _bind_module_data(
    entity: Any,
    *,
    walk: dict[str, object] | None = None,
    health: dict[str, object] | None = None,
    feeding: dict[str, object] | None = None,
) -> None:
    values = {"walk": walk, "health": health, "feeding": feeding}

    def _get_module_data(module: str) -> dict[str, object] | None:
        return values.get(module)

    entity._get_module_data = _get_module_data  # type: ignore[method-assign]


def test_health_and_feeding_payload_helpers_reject_non_mapping_data() -> None:
    """Non-mapping module payloads should resolve to ``None``."""

    def _module_data(module: str) -> object:
        return [] if module in {"health", "feeding"} else None

    provider = SimpleNamespace(_get_module_data=_module_data)

    assert missing_sensors._health_payload(provider) is None
    assert missing_sensors._feeding_payload(provider) is None


def test_calculate_activity_level_returns_unknown_for_type_errors() -> None:
    """Type coercion errors should hit the defensive ``TypeError`` branch."""
    walk_data = {"walks_today": object(), "total_duration_today": 30}

    assert missing_sensors.calculate_activity_level(walk_data, None) == "unknown"


def test_derive_next_feeding_time_handles_zero_division_guard(monkeypatch) -> None:
    """A defensive ``ZeroDivisionError`` branch should return ``None``."""

    class _ZeroDivisor:
        def __le__(self, _other: object) -> bool:
            return False

        def __rtruediv__(self, _other: object) -> float:
            raise ZeroDivisionError("forced for coverage")

    monkeypatch.setattr(
        missing_sensors,
        "int",
        lambda _value: _ZeroDivisor(),
        raising=False,
    )

    feeding_data = {
        "config": {"meals_per_day": "3"},
        "last_feeding": "2026-01-01T08:00:00+00:00",
    }
    assert missing_sensors.derive_next_feeding_time(feeding_data) is None


def test_activity_level_sensor_native_value_and_attributes() -> None:
    """Activity sensor should derive value and expose walk/health metadata."""
    sensor = missing_sensors.PawControlActivityLevelSensor(
        _coordinator(), "dog-1", "Buddy"
    )
    walk_data = {
        "walks_today": "2",
        "total_duration_today": "65",
        "last_walk": datetime(2026, 1, 8, 8, tzinfo=UTC),
    }
    health_data = {"activity_level": "high"}
    _bind_module_data(sensor, walk=walk_data, health=health_data)

    assert sensor.native_value == "high"

    attrs = sensor.extra_state_attributes
    assert attrs["walks_today"] == 2
    assert attrs["total_walk_minutes_today"] == 65.0
    assert attrs["health_activity_level"] == "high"
    assert attrs["activity_source"] == "health_data"


def test_calories_burned_sensor_native_value_and_attributes() -> None:
    """Calories sensor should resolve weight and expose calculation metadata."""
    sensor = missing_sensors.PawControlCaloriesBurnedTodaySensor(
        _coordinator(),
        "dog-1",
        "Buddy",
    )
    walk_data = {"total_duration_today": "30", "total_distance_today": "500"}
    health_data = {"activity_level": "high", "weight": "18.0"}
    _bind_module_data(sensor, walk=walk_data, health=health_data)

    resolved_weight = sensor._resolve_dog_weight(health_data)
    assert resolved_weight == 20.0
    assert sensor.native_value == 480.0

    attrs = sensor.extra_state_attributes
    assert attrs["dog_weight_kg"] == 20.0
    assert attrs["walk_minutes_today"] == 30.0
    assert attrs["walk_distance_meters_today"] == 500.0
    assert attrs["calories_per_minute"] == 10.0
    assert attrs["calories_per_100m"] == 20.0


def test_last_feeding_sensor_paths(monkeypatch) -> None:
    """Last feeding sensor should cover native value and attribute branches."""
    sensor = missing_sensors.PawControlLastFeedingHoursSensor(
        _coordinator(), "dog-1", "Buddy"
    )
    reference = datetime(2026, 1, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.pawcontrol.missing_sensors.dt_util.utcnow",
        lambda: reference,
    )

    feeding_with_datetime = {
        "last_feeding": reference - timedelta(hours=9),
        "total_feedings_today": "2",
        "config": {"meals_per_day": 2},
    }
    _bind_module_data(sensor, feeding=feeding_with_datetime)
    assert sensor.native_value == 9.0
    attrs_datetime = sensor.extra_state_attributes
    assert attrs_datetime["feedings_today"] == 2
    assert attrs_datetime["is_overdue"] is True

    feeding_with_number = {
        "last_feeding": 1_700_000_000,
        "total_feedings_today": 1,
        "config": {"meals_per_day": 3},
    }
    _bind_module_data(sensor, feeding=feeding_with_number)
    attrs_number = sensor.extra_state_attributes
    assert isinstance(attrs_number["last_feeding_time"], float)

    feeding_with_string = {
        "last_feeding": "2026-01-08T01:00:00+00:00",
        "total_feedings_today": 1,
        "config": {"meals_per_day": 2},
    }
    _bind_module_data(sensor, feeding=feeding_with_string)
    attrs_string = sensor.extra_state_attributes
    assert attrs_string["last_feeding_time"] == "2026-01-08T01:00:00+00:00"

    feeding_with_unknown = {
        "last_feeding": object(),
        "total_feedings_today": 1,
        "config": {"meals_per_day": 2},
    }
    _bind_module_data(sensor, feeding=feeding_with_unknown)
    attrs_unknown = sensor.extra_state_attributes
    assert attrs_unknown["last_feeding_time"] is None

    _bind_module_data(sensor, feeding=None)
    assert sensor.native_value is None
    assert isinstance(sensor.extra_state_attributes, dict)
    assert sensor._is_feeding_overdue({"last_feeding": "invalid"}) is False


def test_total_walk_distance_sensor_paths() -> None:
    """Total distance sensor should aggregate history and guard invalid values."""
    sensor = missing_sensors.PawControlTotalWalkDistanceSensor(
        _coordinator(), "dog-1", "Buddy"
    )

    walk_data = {
        "total_distance_lifetime": 0,
        "walks_history": [{"distance": 600}, {"distance": 400}],
        "total_walks_lifetime": 5,
        "distance_this_week": 2_300,
        "distance_this_month": 7_800,
    }
    _bind_module_data(sensor, walk=walk_data)
    assert sensor.native_value == 1.0

    attrs = sensor.extra_state_attributes
    assert attrs["total_walks"] == 5
    assert attrs["total_distance_meters"] == 0.0
    assert attrs["distance_this_week_km"] == 2.3
    assert attrs["distance_this_month_km"] == 7.8

    _bind_module_data(sensor, walk={"total_distance_lifetime": "bad"})
    assert sensor.native_value == 0.0

    _bind_module_data(sensor, walk={"total_distance_lifetime": []})
    assert sensor.native_value == 0.0

    _bind_module_data(sensor, walk={"total_distance_lifetime": object()})
    assert sensor.native_value == 0.0

    _bind_module_data(sensor, walk=None)
    assert sensor.native_value == 0.0
    assert isinstance(sensor.extra_state_attributes, dict)


def test_walks_this_week_sensor_paths(monkeypatch) -> None:
    """Weekly walk sensor should count history and expose weekly summaries."""
    sensor = missing_sensors.PawControlWalksThisWeekSensor(
        _coordinator(), "dog-1", "Buddy"
    )
    now = datetime(2026, 1, 8, 12, tzinfo=UTC)
    monkeypatch.setattr(
        "custom_components.pawcontrol.missing_sensors.dt_util.utcnow",
        lambda: now,
    )

    start_of_week = (now - timedelta(days=now.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    within_week = (start_of_week + timedelta(days=1)).isoformat()
    before_week = (start_of_week - timedelta(days=1)).isoformat()
    walk_data = {
        "walks_this_week": 0,
        "walks_history": [
            {"timestamp": within_week},
            {"end_time": within_week},
            {"timestamp": before_week},
            {"timestamp": object()},
        ],
        "walks_today": 2,
        "total_duration_this_week": 120.0,
        "distance_this_week": 3_500.0,
    }
    _bind_module_data(sensor, walk=walk_data)

    assert sensor.native_value == 2
    attrs = sensor.extra_state_attributes
    assert attrs["walks_today"] == 2
    assert attrs["days_this_week"] == now.weekday() + 1
    assert attrs["distance_this_week_km"] == 3.5

    _bind_module_data(sensor, walk={"walks_this_week": "broken"})
    assert sensor.native_value == 0

    _bind_module_data(sensor, walk={"walks_this_week": 4})
    assert sensor.native_value == 4

    _bind_module_data(sensor, walk={"walks_this_week": 0})
    assert sensor.native_value == 0

    _bind_module_data(sensor, walk={"walks_this_week": object()})
    assert sensor.native_value == 0

    _bind_module_data(sensor, walk=None)
    assert sensor.native_value == 0
    assert isinstance(sensor.extra_state_attributes, dict)
