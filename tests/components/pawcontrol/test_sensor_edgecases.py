"""Edge-case and regression tests for sensor helpers."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import sensor


class _GardenProbe(sensor.PawControlGardenSensorBase):
    """Concrete probe for garden base behavior."""

    @property
    def native_value(self) -> str:
        return "ok"


def _build_garden_probe() -> _GardenProbe:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return _GardenProbe(coordinator, "dog-1", "Rex", "garden_probe")


def _build_calorie_sensor() -> sensor.PawControlCaloriesBurnedTodaySensor:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return sensor.PawControlCaloriesBurnedTodaySensor(coordinator, "dog-1", "Rex")


@pytest.mark.parametrize(
    "garden_payload",
    [
        {"last_session": "invalid", "stats": "invalid"},
        {"last_session": 42, "stats": ["bad"]},
    ],
)
def test_garden_attributes_ignore_invalid_mapping_shapes_regression(
    monkeypatch: pytest.MonkeyPatch,
    garden_payload: dict[str, object],
) -> None:
    """Regression: non-mapping garden payload fragments should not crash."""
    probe = _build_garden_probe()
    monkeypatch.setattr(probe, "_get_garden_data", lambda: garden_payload)

    attrs = probe._garden_attributes()

    assert attrs["garden_status"] is None
    assert attrs["started_at"] is None
    assert attrs["last_seen"] is None


@pytest.mark.parametrize(
    ("walk_data", "expected"),
    [
        ({"calories_burned_today": "125.44"}, 125.4),
        ({"total_duration_today": 45, "total_distance_today": 4500}, 504.0),
        ([], 0.0),
    ],
)
def test_calories_native_value_decision_paths(
    monkeypatch: pytest.MonkeyPatch,
    walk_data: object,
    expected: float,
) -> None:
    """native_value should follow direct, fallback, and invalid-shape paths."""
    calorie_sensor = _build_calorie_sensor()
    calorie_sensor._get_walk_module = lambda: walk_data
    monkeypatch.setattr(
        calorie_sensor,
        "_get_dog_data",
        lambda: {"dog_info": {"dog_weight": 10}},
    )

    assert calorie_sensor.native_value == pytest.approx(expected)


@pytest.mark.parametrize(
    ("dog_data", "expected"),
    [
        ({"dog_info": {"dog_weight": 10}}, 320.0),
        (None, 0.0),
        ("bad", 0.0),
    ],
)
def test_calculate_calories_from_activity_handles_missing_and_wrong_types(
    monkeypatch: pytest.MonkeyPatch,
    dog_data: object,
    expected: float,
) -> None:
    """Calories fallback must tolerate missing dog data and wrong payload types."""
    calorie_sensor = _build_calorie_sensor()
    monkeypatch.setattr(calorie_sensor, "_get_dog_data", lambda: dog_data)

    result = calorie_sensor._calculate_calories_from_activity(
        {
            "total_duration_today": 40,
            "total_distance_today": 3000,
        },
    )

    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "raising_exception",
    [TypeError("x"), ValueError("x"), KeyError("x")],
)
def test_compute_activity_score_optimized_exception_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
    raising_exception: Exception,
) -> None:
    """Activity score optimizer should ignore per-module computation exceptions."""
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    activity_sensor = sensor.PawControlActivityScoreSensor(coordinator, "dog-1", "Rex")

    monkeypatch.setattr(
        activity_sensor,
        "_calculate_walk_score",
        lambda _payload: (_ for _ in ()).throw(raising_exception),
    )
    monkeypatch.setattr(
        activity_sensor,
        "_calculate_feeding_score",
        lambda _payload: 80.0,
    )

    result = activity_sensor._compute_activity_score_optimized(
        {
            "walk": {"present": True},
            "feeding": {"present": True},
        },
    )

    assert result == 80.0


@pytest.mark.parametrize(
    ("coordinator_available", "dog_data", "expected"),
    [
        (True, {"status": "ok"}, True),
        (False, {"status": "ok"}, False),
        (True, None, False),
    ],
)
def test_sensor_available_requires_coordinator_and_dog_data(
    monkeypatch: pytest.MonkeyPatch,
    coordinator_available: bool,
    dog_data: object,
    expected: bool,
) -> None:
    """Sensor availability should require coordinator and valid dog payload."""
    dog_status_sensor = sensor.PawControlDogStatusSensor(
        SimpleNamespace(
            available=coordinator_available,
            update_interval=timedelta(minutes=5),
        ),
        "dog-1",
        "Rex",
    )
    monkeypatch.setattr(dog_status_sensor, "_get_dog_data", lambda: dog_data)

    assert dog_status_sensor.available is expected


@pytest.mark.parametrize(
    ("status_snapshot", "walk_data", "feeding_data", "gps_data", "expected"),
    [
        ({"state": "sleeping"}, {}, {}, {}, "sleeping"),
        (None, {"walk_in_progress": True}, {}, {}, "walking"),
        (None, {}, {"is_hungry": True}, {"zone": "home"}, "hungry"),
        (None, {}, {"is_hungry": False}, {"zone": "garden"}, "at_garden"),
        (None, {}, {}, {"zone": "unknown"}, "away"),
    ],
)
def test_dog_status_native_value_decision_tree(
    monkeypatch: pytest.MonkeyPatch,
    status_snapshot: object,
    walk_data: object,
    feeding_data: object,
    gps_data: object,
    expected: str,
) -> None:
    """Status sensor should prioritize snapshot and then module-derived fallback."""
    dog_status_sensor = sensor.PawControlDogStatusSensor(
        SimpleNamespace(available=True, update_interval=timedelta(minutes=5)),
        "dog-1",
        "Rex",
    )

    monkeypatch.setattr(dog_status_sensor, "_get_dog_data", lambda: {"status": "ok"})
    monkeypatch.setattr(dog_status_sensor, "_get_status_snapshot", lambda: status_snapshot)
    monkeypatch.setattr(dog_status_sensor, "_get_walk_module", lambda: walk_data)
    monkeypatch.setattr(dog_status_sensor, "_get_feeding_module", lambda: feeding_data)
    monkeypatch.setattr(dog_status_sensor, "_get_gps_module", lambda: gps_data)

    assert dog_status_sensor.native_value == expected


def test_dog_status_native_value_returns_unknown_on_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected data-shape errors should degrade to unknown status safely."""
    dog_status_sensor = sensor.PawControlDogStatusSensor(
        SimpleNamespace(available=True, update_interval=timedelta(minutes=5)),
        "dog-1",
        "Rex",
    )
    monkeypatch.setattr(dog_status_sensor, "_get_dog_data", lambda: {"status": "ok"})
    monkeypatch.setattr(
        dog_status_sensor,
        "_get_status_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("status unavailable")),
    )

    assert dog_status_sensor.native_value == "unknown"
