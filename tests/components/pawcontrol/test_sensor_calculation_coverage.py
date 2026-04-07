"""Focused coverage tests for sensor-side calculation helpers."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("aiohttp")

from custom_components.pawcontrol import sensor


class _GardenProbe(sensor.PawControlGardenSensorBase):
    """Concrete helper for validating garden attribute generation."""

    @property
    def native_value(self) -> str:
        return "ok"


def _activity_sensor() -> sensor.PawControlActivityScoreSensor:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return sensor.PawControlActivityScoreSensor(coordinator, "dog-1", "Rex")


def _calorie_sensor() -> sensor.PawControlCaloriesBurnedTodaySensor:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return sensor.PawControlCaloriesBurnedTodaySensor(coordinator, "dog-1", "Rex")


def _garden_probe() -> _GardenProbe:
    coordinator = SimpleNamespace(available=True, update_interval=timedelta(minutes=5))
    return _GardenProbe(coordinator, "dog-1", "Rex", "garden_probe")


def test_compute_activity_score_optimized_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Activity score should aggregate weighted module scores."""
    activity_sensor = _activity_sensor()
    monkeypatch.setattr(activity_sensor, "_calculate_walk_score", lambda _payload: 80.0)
    monkeypatch.setattr(
        activity_sensor,
        "_calculate_feeding_score",
        lambda _payload: 60.0,
    )
    monkeypatch.setattr(activity_sensor, "_calculate_gps_score", lambda _payload: 50.0)
    monkeypatch.setattr(activity_sensor, "_calculate_health_score", lambda _payload: 100.0)

    result = activity_sensor._compute_activity_score_optimized(
        {"walk": {}, "feeding": {}, "gps": {}, "health": {}},
    )

    assert result == pytest.approx(74.1)


def test_compute_activity_score_optimized_invalid_payload_returns_none() -> None:
    """Invalid payload shapes should safely produce a None result."""
    activity_sensor = _activity_sensor()

    assert activity_sensor._compute_activity_score_optimized({}) is None


def test_compute_activity_score_optimized_fallback_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-module exceptions should be ignored when other modules are valid."""
    activity_sensor = _activity_sensor()
    monkeypatch.setattr(
        activity_sensor,
        "_calculate_walk_score",
        lambda _payload: (_ for _ in ()).throw(TypeError("bad-walk")),
    )
    monkeypatch.setattr(activity_sensor, "_calculate_feeding_score", lambda _payload: 70.0)

    result = activity_sensor._compute_activity_score_optimized(
        {"walk": {}, "feeding": {}},
    )

    assert result == 70.0


def test_calculate_calories_from_activity_success_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calorie helper should compute values from valid duration/distance input."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(
        calorie_sensor,
        "_get_dog_data",
        lambda: {"dog_info": {"dog_weight": 10.0}},
    )

    result = calorie_sensor._calculate_calories_from_activity(
        {"total_duration_today": 30, "total_distance_today": 3000},
    )

    assert result == pytest.approx(336.0)


def test_calculate_calories_from_activity_invalid_input_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid types should not crash and should return 0.0."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(calorie_sensor, "_get_dog_data", lambda: "bad")

    result = calorie_sensor._calculate_calories_from_activity(
        {"total_duration_today": "bad", "total_distance_today": 3000},
    )

    assert result == 0.0


def test_calculate_calories_from_activity_fallback_missing_dog_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing dog payload should trigger the explicit fallback branch."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(calorie_sensor, "_get_dog_data", lambda: None)

    result = calorie_sensor._calculate_calories_from_activity(
        {"total_duration_today": 20, "total_distance_today": 1200},
    )

    assert result == 0.0


def test_garden_attributes_success_path_with_structured_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garden attribute helper should expose key telemetry fields."""
    probe = _garden_probe()
    monkeypatch.setattr(
        probe,
        "_get_garden_data",
        lambda: {
            "status": "active",
            "sessions_today": 2,
            "last_session": {
                "session_id": "s1",
                "start_time": "2026-04-07T09:00:00+00:00",
                "end_time": "2026-04-07T09:20:00+00:00",
                "duration_minutes": 20,
            },
            "stats": {"last_garden_visit": "2026-04-07T09:20:00+00:00"},
        },
    )

    attrs = probe._garden_attributes()

    assert attrs["garden_status"] == "active"
    assert attrs["last_session_id"] == "s1"
    assert attrs["duration_minutes"] == pytest.approx(20.0)


def test_garden_attributes_invalid_input_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-mapping session payloads should be ignored safely."""
    probe = _garden_probe()
    monkeypatch.setattr(probe, "_get_garden_data", lambda: {"last_session": "bad"})

    attrs = probe._garden_attributes()

    assert attrs["last_session_start"] is None
    assert attrs["last_seen"] is None


def test_garden_attributes_fallback_to_stats_when_last_session_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fallback branch should source last_seen from stats when session is absent."""
    probe = _garden_probe()
    monkeypatch.setattr(
        probe,
        "_get_garden_data",
        lambda: {"stats": {"last_garden_visit": "2026-04-07T10:30:00+00:00"}},
    )

    attrs = probe._garden_attributes()

    assert attrs["last_seen"] is not None
