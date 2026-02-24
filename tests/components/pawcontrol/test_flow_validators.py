"""Tests for flow-level validation wrappers."""

import pytest

from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.flow_validators import (
    ValidationError,
    validate_flow_dog_name,
    validate_flow_geofence_radius,
    validate_flow_gps_accuracy,
    validate_flow_gps_coordinates,
    validate_flow_gps_interval,
    validate_flow_time_window,
    validate_flow_timer_interval,
)


def test_validate_flow_dog_name_passthrough() -> None:
    """Dog-name wrapper should trim and validate required names."""
    assert validate_flow_dog_name("  Luna  ") == "Luna"
    assert validate_flow_dog_name("", field=CONF_DOG_NAME, required=False) is None


def test_validate_flow_gps_coordinates_passthrough() -> None:
    """Coordinate wrapper should return validated float tuples."""
    assert validate_flow_gps_coordinates("48.8566", "2.3522") == (48.8566, 2.3522)


@pytest.mark.parametrize(
    "validator",
    [validate_flow_gps_accuracy, validate_flow_geofence_radius],
)
def test_validate_flow_accuracy_and_radius_wrappers(validator) -> None:
    """Numeric wrappers should validate required values and raise shared errors."""
    assert validator("5.5", field="radius", min_value=1.0, max_value=10.0) == 5.5

    with pytest.raises(ValidationError, match="not_numeric"):
        validator("bad", field="radius", min_value=1.0, max_value=10.0)


def test_validate_flow_interval_wrappers() -> None:
    """Interval wrappers should support defaults and clamping behavior."""
    assert (
        validate_flow_gps_interval(
            None,
            field="gps_interval",
            minimum=5,
            maximum=30,
            default=15,
            required=False,
        )
        == 15
    )

    assert (
        validate_flow_timer_interval(
            1,
            field="timer",
            minimum=5,
            maximum=30,
            default=15,
            clamp=True,
        )
        == 5
    )


def test_validate_flow_time_window_wrapper() -> None:
    """Time-window wrapper should return normalized start and end values."""
    assert validate_flow_time_window(
        "08:00",
        "10:00",
        start_field="start",
        end_field="end",
    ) == ("08:00:00", "10:00:00")
