"""Tests for config/options flow validator wrapper functions."""

from typing import Any

import pytest

from custom_components.pawcontrol import flow_validators
from custom_components.pawcontrol.exceptions import ValidationError


@pytest.mark.parametrize(
    ("wrapper_name", "target_name", "kwargs", "expected"),
    [
        (
            "validate_flow_dog_name",
            "validate_dog_name",
            {"name": "Luna", "field": "dog_name", "required": True},
            "Luna",
        ),
        (
            "validate_flow_gps_interval",
            "validate_gps_interval",
            {
                "value": "30",
                "field": "gps_interval",
                "minimum": 10,
                "maximum": 60,
                "default": 20,
                "clamp": False,
                "required": False,
            },
            30,
        ),
        (
            "validate_flow_timer_interval",
            "validate_interval",
            {
                "value": 15,
                "field": "timer_interval",
                "minimum": 5,
                "maximum": 20,
                "default": 10,
                "clamp": True,
                "required": True,
            },
            15,
        ),
        (
            "validate_flow_time_window",
            "validate_time_window",
            {
                "start": "08:00:00",
                "end": "09:00:00",
                "start_field": "start",
                "end_field": "end",
                "default_start": None,
                "default_end": None,
            },
            ("08:00:00", "09:00:00"),
        ),
    ],
)
def test_function_wrappers_delegate_to_validation_module(
    monkeypatch: pytest.MonkeyPatch,
    wrapper_name: str,
    target_name: str,
    kwargs: dict[str, Any],
    expected: Any,
) -> None:
    """Wrapper helpers should pass all args/kwargs to the validation API."""
    captured: dict[str, Any] = {}

    def _fake(*args: Any, **inner_kwargs: Any) -> Any:
        captured["args"] = args
        captured["kwargs"] = inner_kwargs
        return expected

    monkeypatch.setattr(flow_validators, target_name, _fake)

    wrapper = getattr(flow_validators, wrapper_name)
    result = wrapper(**kwargs)

    assert result == expected
    expected_args = tuple(kwargs.values())[: len(captured["args"])]
    expected_kwargs = {
        k: v
        for k, v in kwargs.items()
        if k not in tuple(kwargs)[: len(captured["args"])]
    }
    assert captured["args"] == expected_args
    assert captured["kwargs"] == expected_kwargs


def test_input_validator_wrappers_delegate_exactly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """InputValidator wrappers should forward values and keyword fields."""
    captured_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _capture(
        method_name: str, *args: Any, **kwargs: Any
    ) -> float | tuple[float, float]:
        captured_calls.append((method_name, args, kwargs))
        return (1.0, 2.0) if method_name == "validate_gps_coordinates" else 25.0

    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_gps_coordinates",
        staticmethod(
            lambda *args, **kwargs: _capture(
                "validate_gps_coordinates", *args, **kwargs
            )
        ),
    )
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_gps_accuracy",
        staticmethod(
            lambda *args, **kwargs: _capture("validate_gps_accuracy", *args, **kwargs)
        ),
    )
    monkeypatch.setattr(
        flow_validators.InputValidator,
        "validate_geofence_radius",
        staticmethod(
            lambda *args, **kwargs: _capture(
                "validate_geofence_radius", *args, **kwargs
            )
        ),
    )

    assert flow_validators.validate_flow_gps_coordinates("52.5", "13.4") == (1.0, 2.0)
    assert (
        flow_validators.validate_flow_gps_accuracy(
            "25",
            field="gps_accuracy",
            min_value=5,
            max_value=50,
            required=False,
        )
        == 25.0
    )
    assert (
        flow_validators.validate_flow_geofence_radius(
            "25",
            field="radius",
            min_value=10,
            max_value=100,
            required=True,
        )
        == 25.0
    )

    assert captured_calls == [
        (
            "validate_gps_coordinates",
            ("52.5", "13.4"),
            {"latitude_field": "latitude", "longitude_field": "longitude"},
        ),
        (
            "validate_gps_accuracy",
            ("25",),
            {
                "field": "gps_accuracy",
                "min_value": 5,
                "max_value": 50,
                "required": False,
            },
        ),
        (
            "validate_geofence_radius",
            ("25",),
            {"field": "radius", "min_value": 10, "max_value": 100, "required": True},
        ),
    ]


def test_flow_validators_exports_validation_error_symbol() -> None:
    """Public exports should expose ValidationError for flow modules."""
    assert flow_validators.ValidationError is ValidationError
    assert "ValidationError" in flow_validators.__all__


def test_validate_flow_wrappers_enforce_validation_rules() -> None:
    """Wrapper helpers should surface underlying validation failures."""
    with pytest.raises(ValidationError) as dog_error:
        flow_validators.validate_flow_dog_name("   ", required=True)
    assert dog_error.value.field == "dog_name"

    with pytest.raises(ValidationError) as gps_error:
        flow_validators.validate_flow_gps_interval(
            1,
            field="gps_interval",
            minimum=10,
            maximum=60,
            clamp=False,
            required=True,
        )
    assert gps_error.value.field == "gps_interval"


def test_validate_flow_time_window_supports_defaults_and_missing_values() -> None:
    """Time window wrapper should default missing values and reject empty windows."""
    assert flow_validators.validate_flow_time_window(
        None,
        None,
        start_field="quiet_start",
        end_field="quiet_end",
        default_start="22:00",
        default_end="06:00",
    ) == ("22:00:00", "06:00:00")

    with pytest.raises(ValidationError) as time_error:
        flow_validators.validate_flow_time_window(
            None,
            None,
            start_field="quiet_start",
            end_field="quiet_end",
        )
    assert time_error.value.field == "quiet_start"
def test_flow_validator_wrappers_validate_inputs_end_to_end() -> None:
    """Wrappers should enforce core validation constraints without monkeypatching."""
    assert flow_validators.validate_flow_dog_name("  Luna  ") == "Luna"
    assert flow_validators.validate_flow_gps_coordinates("52.5", "13.4") == (
        52.5,
        13.4,
    )
    assert (
        flow_validators.validate_flow_gps_accuracy(
            "25",
            field="gps_accuracy",
            min_value=10,
            max_value=50,
        )
        == 25.0
    )
    assert (
        flow_validators.validate_flow_geofence_radius(
            "150",
            field="radius",
            min_value=50,
            max_value=500,
        )
        == 150.0
    )
    assert (
        flow_validators.validate_flow_gps_interval(
            "60",
            field="gps_interval",
            minimum=30,
            maximum=300,
            required=True,
        )
        == 60
    )
    assert (
        flow_validators.validate_flow_timer_interval(
            "15",
            field="timer_interval",
            minimum=10,
            maximum=120,
            required=True,
        )
        == 15
    )
    assert flow_validators.validate_flow_time_window(
        "08:00:00",
        "10:30:00",
        start_field="start",
        end_field="end",
    ) == ("08:00:00", "10:30:00")


def test_flow_validator_wrappers_raise_validation_error_for_invalid_values() -> None:
    """Wrappers should surface validation errors from the shared validator API."""
    with pytest.raises(ValidationError):
        flow_validators.validate_flow_dog_name("", required=True)

    with pytest.raises(ValidationError):
        flow_validators.validate_flow_gps_coordinates("200", "13.4")

    with pytest.raises(ValidationError):
        flow_validators.validate_flow_time_window(
            "not-a-time",
            "09:00:00",
            start_field="start",
            end_field="end",
        )
