"""Tests for flow validator wrapper functions."""

from __future__ import annotations

from typing import Any

from custom_components.pawcontrol import flow_validators


class _Recorder:
    """Capture call arguments and return a fixed value."""

    def __init__(self, return_value: Any) -> None:
        self.return_value = return_value
        self.args: tuple[Any, ...] | None = None
        self.kwargs: dict[str, Any] | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.args = args
        self.kwargs = kwargs
        return self.return_value


def test_validate_flow_dog_name_delegates_with_defaults(monkeypatch) -> None:
    """Dog name wrapper should pass default field/required values."""
    recorder = _Recorder("Luna")
    monkeypatch.setattr(flow_validators, "validate_dog_name", recorder)

    result = flow_validators.validate_flow_dog_name("Luna")

    assert result == "Luna"
    assert recorder.args == ("Luna",)
    assert recorder.kwargs == {"field": "dog_name", "required": True}


def test_validate_flow_gps_coordinates_delegates_fields(monkeypatch) -> None:
    """GPS coordinate wrapper should pass custom field names through."""
    recorder = _Recorder((12.34, 56.78))
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_gps_coordinates",
        recorder,
    )

    result = flow_validators.validate_flow_gps_coordinates(
        "12.34",
        "56.78",
        latitude_field="lat",
        longitude_field="lon",
    )

    assert result == (12.34, 56.78)
    assert recorder.args == ("12.34", "56.78")
    assert recorder.kwargs == {"latitude_field": "lat", "longitude_field": "lon"}


def test_validate_flow_gps_accuracy_delegates(monkeypatch) -> None:
    """GPS accuracy wrapper should forward the boundary arguments."""
    recorder = _Recorder(9.5)
    monkeypatch.setattr(
        flow_validators.InputValidator, "validate_gps_accuracy", recorder
    )

    result = flow_validators.validate_flow_gps_accuracy(
        "9.5",
        field="accuracy",
        min_value=1.0,
        max_value=50.0,
        required=False,
    )

    assert result == 9.5
    assert recorder.args == ("9.5",)
    assert recorder.kwargs == {
        "field": "accuracy",
        "min_value": 1.0,
        "max_value": 50.0,
        "required": False,
    }


def test_validate_flow_geofence_radius_delegates(monkeypatch) -> None:
    """Geofence radius wrapper should call InputValidator consistently."""
    recorder = _Recorder(100.0)
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_geofence_radius",
        recorder,
    )

    result = flow_validators.validate_flow_geofence_radius(
        "100",
        field="radius",
        min_value=10.0,
        max_value=1000.0,
    )

    assert result == 100.0
    assert recorder.args == ("100",)
    assert recorder.kwargs == {
        "field": "radius",
        "min_value": 10.0,
        "max_value": 1000.0,
        "required": True,
    }


def test_validate_flow_gps_interval_delegates(monkeypatch) -> None:
    """GPS interval wrapper should preserve clamp/default controls."""
    recorder = _Recorder(60)
    monkeypatch.setattr(flow_validators, "validate_gps_interval", recorder)

    result = flow_validators.validate_flow_gps_interval(
        "60",
        field="gps_interval",
        minimum=10,
        maximum=300,
        default=120,
        clamp=True,
        required=True,
    )

    assert result == 60
    assert recorder.args == ("60",)
    assert recorder.kwargs == {
        "field": "gps_interval",
        "minimum": 10,
        "maximum": 300,
        "default": 120,
        "clamp": True,
        "required": True,
    }


def test_validate_flow_timer_interval_delegates(monkeypatch) -> None:
    """Timer interval wrapper should call validate_interval."""
    recorder = _Recorder(15)
    monkeypatch.setattr(flow_validators, "validate_interval", recorder)

    result = flow_validators.validate_flow_timer_interval(
        "15",
        field="walk_interval",
        minimum=5,
        maximum=60,
    )

    assert result == 15
    assert recorder.args == ("15",)
    assert recorder.kwargs == {
        "field": "walk_interval",
        "minimum": 5,
        "maximum": 60,
        "default": None,
        "clamp": False,
        "required": False,
    }


def test_validate_flow_time_window_delegates(monkeypatch) -> None:
    """Time window wrapper should proxy default time values."""
    recorder = _Recorder(("08:00", "18:00"))
    monkeypatch.setattr(flow_validators, "validate_time_window", recorder)

    result = flow_validators.validate_flow_time_window(
        "08:00",
        "18:00",
        start_field="start",
        end_field="end",
        default_start="06:00",
        default_end="22:00",
    )

    assert result == ("08:00", "18:00")
    assert recorder.args == ("08:00", "18:00")
    assert recorder.kwargs == {
        "start_field": "start",
        "end_field": "end",
        "default_start": "06:00",
        "default_end": "22:00",
    }


def test_validation_error_reexport_and_all_contract() -> None:
    """Module should re-export ValidationError in __all__."""
    assert "ValidationError" in flow_validators.__all__
    assert flow_validators.ValidationError.__name__ == "ValidationError"
