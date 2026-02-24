"""Unit tests for input validation sanitizers and validators."""

from pathlib import Path

import pytest

from custom_components.pawcontrol.exceptions import ValidationError
from custom_components.pawcontrol.input_validation import (
    InputSanitizer,
    InputValidator,
    ValidationResult,
    sanitize_user_input,
    validate_and_sanitize,
)


def test_validation_result_bool_uses_valid_flag() -> None:
    assert bool(ValidationResult(is_valid=True, sanitized_value="x", errors=[]))
    assert not bool(
        ValidationResult(is_valid=False, sanitized_value=None, errors=["e"])
    )


def test_sanitize_sql_escapes_quotes_and_blocks_injection() -> None:
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_sql("O'Brien") == "O''Brien"

    with pytest.raises(ValidationError, match="SQL injection pattern"):
        sanitizer.sanitize_sql("users; DELETE FROM accounts")


def test_sanitize_url_rejects_invalid_protocols() -> None:
    sanitizer = InputSanitizer()

    assert (
        sanitizer.sanitize_url("https://example.com/path?q=1")
        == "https://example.com/path?q=1"
    )

    with pytest.raises(ValidationError, match="Only http and https"):
        sanitizer.sanitize_url("ftp://example.com")

    with pytest.raises(ValidationError, match="JavaScript protocol"):
        sanitizer.sanitize_url("https://example.com/javascript:alert(1)")


def test_sanitize_path_rejects_traversal_and_normalizes() -> None:
    sanitizer = InputSanitizer()

    with pytest.raises(ValidationError, match="Path traversal"):
        sanitizer.sanitize_path("../secrets.txt")

    normalized = sanitizer.sanitize_path("tests")
    assert normalized == str(Path("tests").resolve())


def test_validator_integer_float_and_dict_paths() -> None:
    validator = InputValidator()

    type_error = validator.validate_integer(None)
    assert not type_error.is_valid
    assert type_error.errors == ["Cannot convert to integer: None"]

    range_error = validator.validate_float("3.5", min_value=4.0)
    assert not range_error.is_valid
    assert "minimum" in range_error.errors[0]

    schema = {
        "name": {"type": "str", "required": True, "max_length": 4},
        "age": {"type": "int", "required": True, "min_value": 1},
        "website": {"type": "url"},
        "passthrough": {"type": "unknown"},
    }
    result = validator.validate_dict(
        {
            "name": "Buddy",
            "age": "7",
            "website": "https://example.com",
            "passthrough": "value",
        },
        schema,
    )

    assert result.is_valid
    assert result.sanitized_value == {
        "name": "Budd",
        "age": 7,
        "website": "https://example.com",
        "passthrough": "value",
    }


def test_validate_and_sanitize_success_and_failure() -> None:
    assert sanitize_user_input("  hello\x01 ", max_length=10) == "hello"
    assert validate_and_sanitize("42", "validate_integer", min_value=0) == 42

    with pytest.raises(ValidationError, match="Validation failed"):
        validate_and_sanitize("x", "validate_integer")
