"""Tests for flow validator wrapper helpers."""

from collections.abc import Callable
from typing import Any

import pytest

from custom_components.pawcontrol import flow_validators


@pytest.mark.parametrize(
    ("helper_name", "target_name", "args", "kwargs", "expected", "expected_kwargs"),
    [
        (
            "validate_flow_dog_name",
            "validate_dog_name",
            ("Milo",),
            {},
            "Milo",
            {"field": "dog_name", "required": True},
        ),
        (
            "validate_flow_gps_coordinates",
            "InputValidator.validate_gps_coordinates",
            (52.5, 13.4),
            {},
            (52.5, 13.4),
            {"latitude_field": "latitude", "longitude_field": "longitude"},
        ),
        (
            "validate_flow_gps_accuracy",
            "InputValidator.validate_gps_accuracy",
            (5.0,),
            {"field": "gps_accuracy", "min_value": 1.0, "max_value": 10.0},
            5.0,
            {
                "field": "gps_accuracy",
                "min_value": 1.0,
                "max_value": 10.0,
                "required": True,
            },
        ),
        (
            "validate_flow_geofence_radius",
            "InputValidator.validate_geofence_radius",
            (25.0,),
            {"field": "radius", "min_value": 10.0, "max_value": 100.0},
            25.0,
            {
                "field": "radius",
                "min_value": 10.0,
                "max_value": 100.0,
                "required": True,
            },
        ),
        (
            "validate_flow_gps_interval",
            "validate_gps_interval",
            (30,),
            {"field": "gps_interval", "minimum": 10, "maximum": 60},
            30,
            {
                "field": "gps_interval",
                "minimum": 10,
                "maximum": 60,
                "default": None,
                "clamp": False,
                "required": False,
            },
        ),
        (
            "validate_flow_timer_interval",
            "validate_interval",
            (120,),
            {"field": "interval", "minimum": 60, "maximum": 300},
            120,
            {
                "field": "interval",
                "minimum": 60,
                "maximum": 300,
                "default": None,
                "clamp": False,
                "required": False,
            },
        ),
        (
            "validate_flow_time_window",
            "validate_time_window",
            ("08:00", "20:00"),
            {"start_field": "start", "end_field": "end"},
            ("08:00", "20:00"),
            {
                "start_field": "start",
                "end_field": "end",
                "default_start": None,
                "default_end": None,
            },
        ),
    ],
)
def test_flow_validator_wrappers_delegate_to_core_validators(
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    target_name: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    expected: Any,
    expected_kwargs: dict[str, Any],
) -> None:
    """Each wrapper should forward arguments to the underlying validator."""
    recorded: dict[str, Any] = {}

    def _capture_call(*call_args: Any, **call_kwargs: Any) -> Any:
        recorded["args"] = call_args
        recorded["kwargs"] = call_kwargs
        return expected

    if target_name.startswith("InputValidator."):
        attr_name = target_name.rsplit(".", maxsplit=1)[1]
        monkeypatch.setattr(flow_validators.InputValidator, attr_name, _capture_call)
    else:
        monkeypatch.setattr(flow_validators, target_name, _capture_call)

    helper: Callable[..., Any] = getattr(flow_validators, helper_name)
    result = helper(*args, **kwargs)

    assert result == expected
    assert recorded["args"] == args
    assert recorded["kwargs"] == expected_kwargs


def test_flow_validators_exports_validation_error_and_public_wrappers() -> None:
    """Module exports should include all public wrappers and ValidationError."""
    expected_exports = {
        "ValidationError",
        "validate_flow_dog_name",
        "validate_flow_geofence_radius",
        "validate_flow_gps_accuracy",
        "validate_flow_gps_coordinates",
        "validate_flow_gps_interval",
        "validate_flow_time_window",
        "validate_flow_timer_interval",
    }

    assert set(flow_validators.__all__) == expected_exports
    assert flow_validators.ValidationError.__name__ == "ValidationError"
