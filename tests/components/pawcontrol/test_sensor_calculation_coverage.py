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
    monkeypatch.setattr(
        activity_sensor, "_calculate_health_score", lambda _payload: 100.0
    )

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
    monkeypatch.setattr(
        activity_sensor, "_calculate_feeding_score", lambda _payload: 70.0
    )

    result = activity_sensor._compute_activity_score_optimized(
        {"walk": {}, "feeding": {}},
    )

    assert result == 70.0


@pytest.mark.parametrize(
    ("module_name", "error"),
    [
        ("walk", TypeError("walk")),
        ("walk", ValueError("walk")),
        ("walk", KeyError("walk")),
        ("feeding", TypeError("feeding")),
        ("feeding", ValueError("feeding")),
        ("feeding", KeyError("feeding")),
        ("gps", TypeError("gps")),
        ("gps", ValueError("gps")),
        ("gps", KeyError("gps")),
        ("health", TypeError("health")),
        ("health", ValueError("health")),
        ("health", KeyError("health")),
    ],
)
def test_compute_activity_score_optimized_catches_module_exception_branches(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    error: Exception,
) -> None:
    """Each module error branch should be defensive and keep valid scores."""
    activity_sensor = _activity_sensor()
    dog_data = {"walk": {}, "feeding": {}, "gps": {}, "health": {}}

    monkeypatch.setattr(activity_sensor, "_calculate_walk_score", lambda _payload: 80.0)
    monkeypatch.setattr(
        activity_sensor,
        "_calculate_feeding_score",
        lambda _payload: 80.0,
    )
    monkeypatch.setattr(activity_sensor, "_calculate_gps_score", lambda _payload: 80.0)
    monkeypatch.setattr(
        activity_sensor, "_calculate_health_score", lambda _payload: 80.0
    )

    score_method_name = f"_calculate_{module_name}_score"
    monkeypatch.setattr(
        activity_sensor,
        score_method_name,
        lambda _payload: (_ for _ in ()).throw(error),
    )

    result = activity_sensor._compute_activity_score_optimized(dog_data)

    assert result == 80.0


def test_activity_score_native_value_defensive_fallback_when_compute_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """native_value should show no value instead of surfacing exceptions."""
    activity_sensor = _activity_sensor()
    monkeypatch.setattr(
        activity_sensor,
        "_get_dog_data",
        lambda: {"walk": {"walks_today": 2}},
    )
    monkeypatch.setattr(
        activity_sensor,
        "_compute_activity_score_optimized",
        lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert activity_sensor.native_value is None


def test_activity_score_native_value_unavailable_when_dog_data_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sensor should be unavailable and expose no native value without dog data."""
    activity_sensor = _activity_sensor()
    monkeypatch.setattr(activity_sensor, "_get_dog_data", lambda: None)

    assert activity_sensor.available is False
    assert activity_sensor.native_value is None


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


@pytest.mark.parametrize(
    ("walk_data", "expected"),
    [
        ({"total_duration_today": 0, "total_distance_today": 1_000}, 0.0),
        ({"total_duration_today": 10, "total_distance_today": 100}, 64.0),
        ({"total_duration_today": 10, "total_distance_today": 600}, 80.0),
        ({"total_duration_today": 10, "total_distance_today": 1_200}, 112.0),
        ({"total_duration_today": 10, "total_distance_today": 2_000}, 144.0),
    ],
)
def test_calculate_calories_from_activity_speed_intensity_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    walk_data: dict[str, int],
    expected: float,
) -> None:
    """Calorie helper should apply the documented intensity factors."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(
        calorie_sensor,
        "_get_dog_data",
        lambda: {"dog_info": {"dog_weight": 8.0}},
    )

    assert calorie_sensor._calculate_calories_from_activity(walk_data) == expected


@pytest.mark.parametrize("walk_payload", [None, "bad", 42])
def test_calorie_native_value_missing_or_invalid_walk_payload_returns_zero(
    monkeypatch: pytest.MonkeyPatch,
    walk_payload: object,
) -> None:
    """native_value should return 0.0 for unavailable/invalid activity input."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(calorie_sensor, "_get_walk_module", lambda: walk_payload)

    assert calorie_sensor.native_value == 0.0


@pytest.mark.parametrize(
    "error", [TypeError("bad"), ValueError("bad"), AttributeError("bad")]
)
def test_calorie_native_value_exception_branches_fall_back_to_zero(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    """All explicit exception branches should produce a user-visible zero value."""
    calorie_sensor = _calorie_sensor()
    monkeypatch.setattr(calorie_sensor, "_get_walk_module", lambda: {"x": 1})
    monkeypatch.setattr(
        calorie_sensor,
        "_calculate_calories_from_activity",
        lambda _payload: (_ for _ in ()).throw(error),
    )

    assert calorie_sensor.native_value == 0.0


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


def test_garden_attributes_user_visible_fallbacks_for_invalid_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid nested payload shapes should still expose stable null attributes."""
    probe = _garden_probe()
    monkeypatch.setattr(
        probe,
        "_get_garden_data",
        lambda: {
            "status": "idle",
            "last_session": ["wrong"],
            "stats": "wrong",
            "active_session": "wrong",
        },
    )

    attrs = probe._garden_attributes()

    assert attrs["garden_status"] == "idle"
    assert attrs["started_at"] is None
    assert attrs["duration_minutes"] is None
    assert attrs["last_seen"] is None


def test_garden_attributes_prefers_active_session_values_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Active session fields should override fallback session fields for visibility."""
    probe = _garden_probe()
    monkeypatch.setattr(
        probe,
        "_get_garden_data",
        lambda: {
            "last_session": {
                "start_time": "2026-04-07T09:00:00+00:00",
                "duration_minutes": 25,
                "end_time": "2026-04-07T09:25:00+00:00",
            },
            "active_session": {
                "start_time": "2026-04-07T11:00:00+00:00",
                "duration_minutes": 5,
            },
        },
    )

    attrs = probe._garden_attributes()

    assert attrs["duration_minutes"] == pytest.approx(5.0)
    assert attrs["started_at"] is not None
    assert attrs["last_seen"] is not None
