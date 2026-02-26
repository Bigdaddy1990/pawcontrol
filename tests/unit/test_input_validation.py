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


def test_sanitize_html_and_string_filters() -> None:
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_html("<b>Hi</b>") == "&lt;b&gt;Hi&lt;/b&gt;"
    assert (
        sanitizer.sanitize_string(
            "  abc$%\x01\n  ",
            allowed_chars=r"a-zA-Z ",
            strip_whitespace=False,
        )
        == "  abc  "
    )


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


def test_sanitize_url_wraps_parse_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    sanitizer = InputSanitizer()

    monkeypatch.setattr(
        "custom_components.pawcontrol.input_validation.urllib.parse.urlparse",
        lambda _: (_ for _ in ()).throw(ValueError("broken parser")),
    )

    with pytest.raises(ValidationError, match="URL could not be parsed"):
        sanitizer.sanitize_url("https://example.com")


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


def test_validator_numeric_bounds_and_dict_optional_fields() -> None:
    validator = InputValidator()

    integer_bounds = validator.validate_integer("10", min_value=12, max_value=8)
    assert not integer_bounds.is_valid
    assert "minimum" in integer_bounds.errors[0]
    assert "maximum" in integer_bounds.errors[1]

    float_type_error = validator.validate_float(None)
    assert not float_type_error.is_valid
    assert float_type_error.errors == ["Cannot convert to float: None"]

    float_value_error = validator.validate_float("not-a-float")
    assert not float_value_error.is_valid
    assert float_value_error.errors == ["Cannot convert to float: not-a-float"]

    float_bounds = validator.validate_float("9.5", max_value=1.0)
    assert not float_bounds.is_valid
    assert "maximum" in float_bounds.errors[0]

    schema = {
        "optional": {"type": "str"},
        "weight": {"type": "float", "min_value": 1.0, "max_value": 50.0},
        "email": {"type": "email"},
    }
    result = validator.validate_dict(
        {"weight": "6.5", "email": "owner@example.com"},
        schema,
    )
    assert result.is_valid
    assert result.sanitized_value == {"weight": 6.5, "email": "owner@example.com"}


def test_validator_email_phone_string_and_invalid_dict() -> None:
    validator = InputValidator()

    assert validator.validate_email("user@example.com").is_valid
    invalid_email = validator.validate_email("user@@bad")
    assert not invalid_email.is_valid

    valid_phone = validator.validate_phone("+1 (555) 123-1234")
    assert valid_phone.is_valid
    assert valid_phone.sanitized_value == "+1 (555) 123-1234"
    invalid_phone = validator.validate_phone("12")
    assert not invalid_phone.is_valid

    string_result = validator.validate_string(
        " a1 ",
        min_length=3,
        max_length=4,
        pattern=r"^[a-z]+$",
    )
    assert not string_result.is_valid
    assert len(string_result.errors) == 2

    invalid_schema = {
        "required_field": {"type": "int", "required": True},
        "website": {"type": "url"},
    }
    dict_result = validator.validate_dict(
        {"website": "ftp://example.com"},
        invalid_schema,
    )
    assert not dict_result.is_valid
    assert "Missing required field: required_field" in dict_result.errors
    assert any(error.startswith("website:") for error in dict_result.errors)


def test_validate_and_sanitize_success_and_failure() -> None:
    assert sanitize_user_input("  hello\x01 ", max_length=10) == "hello"
    assert validate_and_sanitize("42", "validate_integer", min_value=0) == 42

    with pytest.raises(ValidationError, match="Validation failed"):
        validate_and_sanitize("x", "validate_integer")
