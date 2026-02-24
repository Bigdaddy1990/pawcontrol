"""Tests for config/options flow validator wrapper functions."""

from __future__ import annotations

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
