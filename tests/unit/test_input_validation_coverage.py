"""Additional branch coverage for input_validation helpers."""

from typing import Any

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.input_validation import (
    InputValidator,
    sanitize_user_input,
    validate_and_sanitize,
)


@pytest.mark.unit
def test_sanitize_user_input_removes_control_chars_and_limits_length() -> None:  # noqa: D103
    result = sanitize_user_input("  hi\x00there\nfriend  ", max_length=8)

    assert result == "hithere"


@pytest.mark.unit
def test_validate_dict_normalizes_types_and_reports_scalar_type_mismatch() -> None:  # noqa: D103
    validator = InputValidator()
    result = validator.validate_dict(
        {"email": 42, "phone": "+49 123 4567", "name": "Rex"},
        {
            "email": {"type": " EMAIL "},
            "phone": {"type": "phone"},
            "name": {"type": "text", "min_length": 2},
        },
    )

    assert not result.is_valid
    assert result.sanitized_value == {"phone": "+49 123 4567", "name": "Rex"}
    assert result.errors == [
        "email: Expected text input for ' EMAIL ' validation, got int"
    ]


@pytest.mark.unit
def test_validate_dict_uses_default_string_validator_for_empty_type() -> None:  # noqa: D103
    validator = InputValidator()
    result = validator.validate_dict(
        {"nickname": "  Buddy  "},
        {"nickname": {"type": "   ", "max_length": 5}},
    )

    assert result.is_valid
    assert result.sanitized_value == {"nickname": "Buddy"}


@pytest.mark.unit
def test_validate_dict_handles_validator_value_error_and_type_error() -> None:  # noqa: D103
    validator = InputValidator()

    def raise_value_error(value: Any, **_: Any) -> Any:
        raise ValueError("boom")

    def raise_type_error(value: Any, **_: Any) -> Any:
        raise TypeError("bad kwargs")

    validator.validate_string = raise_value_error  # type: ignore[method-assign]
    value_error = validator.validate_dict(
        {"name": "Rex"},
        {"name": {"type": "str", "min_length": 2}},
    )
    assert not value_error.is_valid
    assert value_error.errors == ["name: Validator 'str' rejected value"]

    validator.validate_string = raise_type_error  # type: ignore[method-assign]
    type_error = validator.validate_dict(
        {"name": "Rex"},
        {"name": {"type": "str", "min_length": 2}},
    )
    assert not type_error.is_valid
    assert type_error.errors == [
        "name: Validator 'str' rejected provided arguments",
    ]


@pytest.mark.unit
def test_validate_and_sanitize_wraps_validator_exceptions() -> None:  # noqa: D103
    validator = InputValidator()

    def raise_value_error(value: Any, **_: Any) -> Any:
        raise ValueError("bad data")

    validator.validate_integer = raise_value_error  # type: ignore[method-assign]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.pawcontrol.input_validation.InputValidator",
            lambda: validator,
        )
        with pytest.raises(ValidationError, match="Validation raised ValueError"):
            validate_and_sanitize("5", "validate_integer")


@pytest.mark.unit
def test_validate_and_sanitize_wraps_type_errors_and_unknown_validators() -> None:  # noqa: D103
    validator = InputValidator()

    def raise_type_error(value: Any, **_: Any) -> Any:
        raise TypeError("bad args")

    validator.validate_float = raise_type_error  # type: ignore[method-assign]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.pawcontrol.input_validation.InputValidator",
            lambda: validator,
        )
        with pytest.raises(ValidationError, match="Validation raised TypeError"):
            validate_and_sanitize("5", "validate_float")

    with pytest.raises(ValidationError, match="Unknown validator"):
        validate_and_sanitize("5", "validate_not_real")
