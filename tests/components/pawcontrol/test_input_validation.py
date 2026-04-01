"""Tests for input sanitization and validation helpers."""

from __future__ import annotations

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


def test_validation_result_bool_reflects_validity() -> None:
    """ValidationResult bool conversion should mirror is_valid."""
    assert bool(ValidationResult(True, "ok", [])) is True
    assert bool(ValidationResult(False, None, ["bad"])) is False


def test_sanitize_sql_escapes_quotes_and_blocks_injection() -> None:
    """SQL sanitizer should escape safe content and reject injected payloads."""
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_sql("O'Hara") == "O''Hara"

    with pytest.raises(ValidationError, match="SQL injection pattern detected"):
        sanitizer.sanitize_sql("x'; DROP TABLE dogs;")


def test_sanitize_url_rejects_invalid_scheme_and_javascript() -> None:
    """URL sanitizer should reject dangerous schemes and script URLs."""
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_url("https://example.com/path?q=1") == (
        "https://example.com/path?q=1"
    )

    with pytest.raises(ValidationError, match="Only http and https schemes"):
        sanitizer.sanitize_url("ftp://example.com")

    with pytest.raises(ValidationError, match="JavaScript protocol"):
        sanitizer.sanitize_url("https://example.com/javascript:alert(1)")


def test_sanitize_path_blocks_encoded_traversal_and_normalizes() -> None:
    """Path sanitizer should block traversal and normalize safe input."""
    sanitizer = InputSanitizer()

    normalized = sanitizer.sanitize_path("docs/readme.txt")
    assert Path(normalized).as_posix().endswith("docs/readme.txt")

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path("..%2fsecret.txt")


def test_validate_integer_handles_type_and_range_constraints() -> None:
    """Integer validator should return useful errors for conversion/range failures."""
    validator = InputValidator()

    type_error = validator.validate_integer(None)
    assert type_error.is_valid is False
    assert "Cannot convert to integer" in type_error.errors[0]

    too_high = validator.validate_integer("42", max_value=10)
    assert too_high.is_valid is False
    assert too_high.sanitized_value == 42
    assert "maximum 10" in too_high.errors[0]

    in_range = validator.validate_integer("7", min_value=0, max_value=10)
    assert in_range.is_valid is True
    assert in_range.sanitized_value == 7


def test_validate_dict_collects_errors_and_sanitizes_valid_fields() -> None:
    """Dictionary validation should keep sanitized values while collecting failures."""
    validator = InputValidator()
    schema = {
        "name": {"type": "str", "required": True, "max_length": 5},
        "age": {"type": "int", "min_value": 0, "max_value": 30},
        "email": {"type": "email"},
        "misc": {"type": "unknown"},
    }

    result = validator.validate_dict(
        {
            "name": "  Buddy  ",
            "age": "99",
            "email": "not-an-email",
            "misc": {"ok": True},
        },
        schema,
    )

    assert result.is_valid is False
    assert result.sanitized_value["name"] == "Buddy"
    assert result.sanitized_value["misc"] == {"ok": True}
    assert any(error.startswith("age:") for error in result.errors)
    assert any(error.startswith("email:") for error in result.errors)


def test_validate_and_sanitize_success_and_failure_paths() -> None:
    """Wrapper helper should return sanitized values and raise on invalid input."""
    assert (
        validate_and_sanitize("  hello  ", "validate_string", max_length=10) == "hello"
    )

    with pytest.raises(ValidationError, match="Validation failed"):
        validate_and_sanitize("bad-email", "validate_email")


def test_sanitize_user_input_enforces_length_and_removes_controls() -> None:
    """Convenience helper should trim, truncate, and strip disallowed chars."""
    cleaned = sanitize_user_input("  abc\x01\nxyz  ", max_length=5)
    assert cleaned == "abc\n"
