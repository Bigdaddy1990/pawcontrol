"""Additional coverage tests for core validation helpers."""

from datetime import time as dt_time
from enum import StrEnum

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    _is_empty,
    _parse_time_string,
    coerce_float,
    coerce_int,
    normalize_dog_id,
    validate_notification_targets,
)


class _Target(StrEnum):
    """Notification target enum for coercion tests."""

    PUSH = "push"
    EMAIL = "email"


def test_is_empty_and_normalize_dog_id_behaviour() -> None:
    """Empty checks and dog ID normalization should handle edge cases."""
    assert _is_empty(None) is True
    assert _is_empty("   ") is True
    assert _is_empty("dog") is False

    assert normalize_dog_id(None) == ""
    assert normalize_dog_id("  My Dog  ") == "my_dog"

    with pytest.raises(InputCoercionError, match="Must be a string"):
        normalize_dog_id(42)


def test_parse_time_string_supports_time_and_rejects_invalid_values() -> None:
    """Time parsing should normalize valid input and raise on invalid values."""
    assert _parse_time_string("quiet_start", None, "invalid_time") is None
    assert _parse_time_string("quiet_start", "  ", "invalid_time") is None
    assert (
        _parse_time_string("quiet_start", dt_time(21, 30, 45), "invalid_time")
        == "21:30:45"
    )
    assert _parse_time_string("quiet_start", "21:30", "invalid_time") == "21:30:00"

    with pytest.raises(ValidationError, match="invalid_time"):
        _parse_time_string("quiet_start", object(), "invalid_time")

    with pytest.raises(ValidationError, match="invalid_time"):
        _parse_time_string("quiet_start", "not-a-time", "invalid_time")


def test_coerce_float_handles_numbers_and_reports_invalid_input() -> None:
    """Float coercion should accept numeric values and reject invalid ones."""
    assert coerce_float("weight", 1.5) == 1.5
    assert coerce_float("weight", " 3.25 ") == 3.25

    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", True)

    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", "")

    with pytest.raises(InputCoercionError, match="Must be numeric"):
        coerce_float("weight", "abc")


def test_coerce_int_handles_fractional_and_invalid_values() -> None:
    """Integer coercion should reject fractions and non-numeric inputs."""
    assert coerce_int("interval", 5) == 5
    assert coerce_int("interval", 5.0) == 5
    assert coerce_int("interval", " 7 ") == 7
    assert coerce_int("interval", "8.0") == 8

    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("interval", 1.2)

    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("interval", "9.5")

    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("interval", False)


def test_validate_notification_targets_handles_iterables_duplicates_and_invalid() -> (
    None
):
    """Notification target parsing should dedupe valid enums and track invalids."""
    parsed = validate_notification_targets(
        [_Target.PUSH, "email", "push", "sms", object()],
        enum_type=_Target,
    )

    assert parsed.targets == [_Target.PUSH, _Target.EMAIL]
    assert parsed.invalid[0] == "sms"
    assert "object" in parsed.invalid[1]


def test_validate_notification_targets_handles_scalar_and_none() -> None:
    """Scalar and missing targets should be normalized consistently."""
    assert validate_notification_targets(None, enum_type=_Target).targets == []
    assert validate_notification_targets("push", enum_type=_Target).targets == [
        _Target.PUSH
    ]
