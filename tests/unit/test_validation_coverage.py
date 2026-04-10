"""Targeted coverage tests for validation.py."""

from datetime import time
from enum import Enum

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    clamp_float_range,
    clamp_int_range,
    coerce_float,
    coerce_int,
    normalize_dog_id,
    validate_notification_targets,
    validate_time_window,
)


class DemoNotification(Enum):
    PUSH = "push"
    EMAIL = "email"


@pytest.mark.unit
def test_clamp_float_range_within_bounds() -> None:
    result = clamp_float_range(
        5.0, field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(5.0)


@pytest.mark.unit
def test_clamp_float_range_invalid_uses_default() -> None:
    result = clamp_float_range(
        "not-a-number", field="weight", minimum=0.0, maximum=100.0, default=50.0
    )
    assert result == pytest.approx(50.0)


@pytest.mark.unit
def test_clamp_int_range_above_max() -> None:
    result = clamp_int_range(99, field="meals", minimum=1, maximum=6, default=2)
    assert result == 6


@pytest.mark.unit
def test_coerce_float_bool_rejected() -> None:
    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", True)


@pytest.mark.unit
def test_coerce_int_fractional_string_rejected() -> None:
    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("meals", "2.9")


@pytest.mark.unit
def test_normalize_dog_id_normalizes_spaces() -> None:
    assert normalize_dog_id("  My Dog  ") == "my_dog"


@pytest.mark.unit
def test_normalize_dog_id_non_string_rejected() -> None:
    with pytest.raises(InputCoercionError, match="Must be a string"):
        normalize_dog_id(123)


@pytest.mark.unit
def test_validate_notification_targets_filters_duplicates_and_invalid() -> None:
    result = validate_notification_targets(
        ["push", DemoNotification.EMAIL, "sms", "push"],
        enum_type=DemoNotification,
    )
    assert result.targets == [DemoNotification.PUSH, DemoNotification.EMAIL]
    assert result.invalid == ["sms"]


@pytest.mark.unit
def test_validate_time_window_uses_defaults_for_empty_values() -> None:
    start, end = validate_time_window(
        "  ",
        None,
        start_field="start",
        end_field="end",
        default_start="07:00:00",
        default_end=time(21, 0),
    )
    assert start == "07:00:00"
    assert end == "21:00:00"


@pytest.mark.unit
def test_validate_time_window_rejects_invalid_end() -> None:
    with pytest.raises(ValidationError):
        validate_time_window(
            "08:00:00",
            "invalid",
            start_field="start",
            end_field="end",
        )
