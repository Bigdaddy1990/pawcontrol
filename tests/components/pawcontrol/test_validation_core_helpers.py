"""Additional coverage tests for core validation helpers."""

from datetime import time as dt_time
from enum import StrEnum

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.validation import (
    InputCoercionError,
    _coerce_float_with_constraint,
    _is_empty,
    _parse_time_string,
    coerce_float,
    coerce_int,
    normalize_dog_id,
    validate_dog_name,
    validate_name,
    validate_notification_targets,
    validate_time_window,
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

    with pytest.raises(InputCoercionError, match="Must be a whole number"):
        coerce_int("interval", object())


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


def test_validate_notification_targets_handles_type_error_candidates() -> None:
    """Non-coercible targets should be reported as invalid via TypeError handling."""
    parsed = validate_notification_targets([["nested"], {"set"}], enum_type=_Target)

    assert parsed.targets == []
    assert "['nested']" in parsed.invalid


def test_validate_time_window_uses_defaults_and_required_constraints() -> None:
    """Time window validation should consume defaults and raise required errors."""
    assert validate_time_window(
        "07:00",
        None,
        start_field="start",
        end_field="end",
        default_end="21:15",
    ) == ("07:00:00", "21:15:00")

    with pytest.raises(ValidationError, match="start_required"):
        validate_time_window(
            None,
            "09:00",
            start_field="start",
            end_field="end",
            required_start_constraint="start_required",
        )

    with pytest.raises(ValidationError, match="end_required"):
        validate_time_window(
            "07:00",
            None,
            start_field="start",
            end_field="end",
            required_end_constraint="end_required",
        )


def test_validate_time_window_accepts_native_time_objects() -> None:
    """Native ``datetime.time`` inputs should be serialized without errors."""
    assert validate_time_window(
        dt_time(6, 5),
        dt_time(22, 45),
        start_field="start",
        end_field="end",
    ) == ("06:05:00", "22:45:00")


def test_validate_name_and_float_constraint_helpers() -> None:
    """Name and float coercion helpers should normalize and map constraints."""
    assert validate_name("  Buddy  ") == "Buddy"

    with pytest.raises(ValidationError, match="name_invalid_type"):
        validate_name(5)

    with pytest.raises(ValidationError, match="must_be_numeric"):
        _coerce_float_with_constraint("weight", "not-a-number", "must_be_numeric")


def test_validate_name_rejects_required_too_short_and_too_long_values() -> None:
    """Name validation should raise dedicated constraints for length failures."""
    with pytest.raises(ValidationError, match="name_required"):
        validate_name("   ")

    with pytest.raises(ValidationError, match="name_too_short"):
        validate_name("A")

    with pytest.raises(ValidationError, match="name_too_long"):
        validate_name("A" * 80)


def test_validate_time_window_reports_invalid_default_constraints() -> None:
    """Time windows should bubble default parsing issues via configured constraints."""
    with pytest.raises(ValidationError, match="start_invalid"):
        validate_time_window(
            None,
            "09:00",
            start_field="start",
            end_field="end",
            default_start="bad-default",
            invalid_start_constraint="start_invalid",
        )

    with pytest.raises(ValidationError, match="end_invalid"):
        validate_time_window(
            "07:00",
            None,
            start_field="start",
            end_field="end",
            default_end="bad-default",
            invalid_end_constraint="end_invalid",
        )


@pytest.mark.parametrize(
    ("name", "kwargs", "expected"),
    [
        ("", {"required": False}, None),
        ("  Buddy  ", {}, "Buddy"),
    ],
)
def test_validate_dog_name_accepts_optional_empty_and_trims(
    name: str,
    kwargs: dict[str, bool],
    expected: str | None,
) -> None:
    """Dog name validation should trim values and allow optional empty fields."""
    assert validate_dog_name(name, **kwargs) == expected


def test_validate_dog_name_rejects_length_and_type_errors() -> None:
    """Dog name validation should emit specific constraints for invalid payloads."""
    with pytest.raises(ValidationError, match="dog_name_invalid"):
        validate_dog_name(123)

    with pytest.raises(ValidationError, match="dog_name_too_short"):
        validate_dog_name("A")

    with pytest.raises(ValidationError, match="dog_name_too_long"):
        validate_dog_name("A" * 65)


def test_validate_dog_name_rejects_untrimmed_payload_exceeding_max_length() -> None:
    """Inputs over max length before trimming should still fail."""
    with pytest.raises(ValidationError, match="dog_name_too_long"):
        validate_dog_name(f"{'A' * 63}   ")


def test_validate_notification_targets_treats_bytes_payload_as_scalar() -> None:
    """Byte payloads should go through the scalar fallback and be marked invalid."""
    parsed = validate_notification_targets(b"push", enum_type=_Target)

    assert parsed.targets == []
    assert parsed.invalid == ["b'push'"]
