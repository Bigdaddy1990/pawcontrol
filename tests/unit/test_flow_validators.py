"""Tests for flow-level validation wrapper helpers."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.pawcontrol import flow_validators


def test_validate_flow_dog_name_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dog-name flow helper should delegate to validate_dog_name."""

    captured: dict[str, Any] = {}

    def _fake_validate(name: Any, *, field: str, required: bool) -> str | None:
        captured.update({"name": name, "field": field, "required": required})
        return "Fido"

    monkeypatch.setattr(flow_validators, "validate_dog_name", _fake_validate)

    assert (
        flow_validators.validate_flow_dog_name(" fido ", field="dog", required=False)
        == "Fido"
    )
    assert captured == {"name": " fido ", "field": "dog", "required": False}


def test_validate_flow_gps_helpers_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    """GPS flow helpers should pass through arguments to InputValidator."""

    captured: dict[str, Any] = {}

    def _fake_coords(
        latitude: Any,
        longitude: Any,
        *,
        latitude_field: str,
        longitude_field: str,
    ) -> tuple[float, float]:
        captured["coords"] = {
            "latitude": latitude,
            "longitude": longitude,
            "latitude_field": latitude_field,
            "longitude_field": longitude_field,
        }
        return (51.5, -0.1)

    def _fake_accuracy(
        value: Any,
        *,
        field: str,
        min_value: float,
        max_value: float,
        required: bool,
    ) -> float | None:
        captured["accuracy"] = {
            "value": value,
            "field": field,
            "min_value": min_value,
            "max_value": max_value,
            "required": required,
        }
        return 10.5

    def _fake_radius(
        value: Any,
        *,
        field: str,
        min_value: float,
        max_value: float,
        required: bool,
    ) -> float | None:
        captured["radius"] = {
            "value": value,
            "field": field,
            "min_value": min_value,
            "max_value": max_value,
            "required": required,
        }
        return 200.0

    monkeypatch.setattr(
        flow_validators.InputValidator, "validate_gps_coordinates", _fake_coords
    )
    monkeypatch.setattr(
        flow_validators.InputValidator, "validate_gps_accuracy", _fake_accuracy
    )
    monkeypatch.setattr(
        flow_validators.InputValidator, "validate_geofence_radius", _fake_radius
    )

    assert flow_validators.validate_flow_gps_coordinates(1, 2) == (51.5, -0.1)
    assert flow_validators.validate_flow_gps_accuracy(
        "10", field="acc", min_value=1.0, max_value=20.0, required=False
    ) == 10.5
    assert flow_validators.validate_flow_geofence_radius(
        "200", field="radius", min_value=10.0, max_value=500.0
    ) == 200.0

    assert captured["coords"]["latitude"] == 1
    assert captured["coords"]["longitude_field"] == "longitude"
    assert captured["accuracy"]["required"] is False
    assert captured["radius"]["max_value"] == 500.0


def test_validate_flow_interval_helpers_delegate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Interval and time-window helpers should delegate to validation module."""

    captured: dict[str, Any] = {}

    def _fake_gps_interval(value: Any, **kwargs: Any) -> int | None:
        captured["gps"] = {"value": value, **kwargs}
        return 15

    def _fake_interval(value: Any, **kwargs: Any) -> int:
        captured["interval"] = {"value": value, **kwargs}
        return 30

    def _fake_time_window(start: Any, end: Any, **kwargs: Any) -> tuple[str, str]:
        captured["window"] = {"start": start, "end": end, **kwargs}
        return ("08:00", "09:00")

    monkeypatch.setattr(flow_validators, "validate_gps_interval", _fake_gps_interval)
    monkeypatch.setattr(flow_validators, "validate_interval", _fake_interval)
    monkeypatch.setattr(flow_validators, "validate_time_window", _fake_time_window)

    assert flow_validators.validate_flow_gps_interval(
        "15", field="gps_interval", minimum=5, maximum=60, required=True
    ) == 15
    assert flow_validators.validate_flow_timer_interval(
        "30", field="timer", minimum=10, maximum=120, default=60
    ) == 30
    assert flow_validators.validate_flow_time_window(
        "08:00",
        "09:00",
        start_field="start_time",
        end_field="end_time",
    ) == ("08:00", "09:00")

    assert captured["gps"]["required"] is True
    assert captured["interval"]["default"] == 60
    assert captured["window"]["start_field"] == "start_time"


def test_flow_validators_exports_validation_error() -> None:
    """The compatibility export list should include ValidationError."""

    assert "ValidationError" in flow_validators.__all__
    assert flow_validators.ValidationError.__name__ == "ValidationError"
