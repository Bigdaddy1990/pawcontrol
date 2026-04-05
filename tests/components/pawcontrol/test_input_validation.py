"""Tests for input sanitization and validation helpers."""

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


def test_sanitize_url_handles_parse_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """URL sanitizer should wrap parse errors as validation errors."""
    sanitizer = InputSanitizer()

    def _raise_parse_error(_: str) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("urllib.parse.urlparse", _raise_parse_error)

    with pytest.raises(ValidationError, match="URL could not be parsed"):
        sanitizer.sanitize_url("https://example.com")


def test_sanitize_path_blocks_encoded_traversal_and_normalizes() -> None:
    """Path sanitizer should block traversal and normalize safe input."""
    sanitizer = InputSanitizer()

    normalized = sanitizer.sanitize_path("docs/readme.txt")
    assert Path(normalized).as_posix().endswith("docs/readme.txt")

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path("..%2fsecret.txt")

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path("safe/../secret.txt")


def test_sanitize_path_catches_segment_traversal_when_regexes_are_bypassed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path sanitizer should still reject '..' segments beyond regex matching."""
    sanitizer = InputSanitizer()
    monkeypatch.setattr(sanitizer, "PATH_TRAVERSAL_PATTERNS", ())

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path("safe/../secret.txt")


def test_sanitize_html_and_string_options() -> None:
    """General sanitizer should escape html and respect optional behaviors."""
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_html("<b>Bold</b>") == "&lt;b&gt;Bold&lt;/b&gt;"
    assert (
        sanitizer.sanitize_string(
            "  A-bC_\x01\n",
            strip_whitespace=False,
            allowed_chars=r"A-Za-z-",
        )
        == "A-bC"
    )


def test_validate_integer_handles_type_and_range_constraints() -> None:
    """Integer validator should return useful errors for conversion/range failures."""
    validator = InputValidator()

    type_error = validator.validate_integer(None)
    assert type_error.is_valid is False
    assert "Cannot convert to integer" in type_error.errors[0]

    value_error = validator.validate_integer("not-a-number")
    assert value_error.is_valid is False
    assert "Cannot convert to integer" in value_error.errors[0]

    too_high = validator.validate_integer("42", max_value=10)
    assert too_high.is_valid is False
    assert too_high.sanitized_value == 42
    assert "maximum 10" in too_high.errors[0]

    too_low = validator.validate_integer("-2", min_value=0)
    assert too_low.is_valid is False
    assert too_low.sanitized_value == -2
    assert "minimum 0" in too_low.errors[0]

    in_range = validator.validate_integer("7", min_value=0, max_value=10)
    assert in_range.is_valid is True
    assert in_range.sanitized_value == 7


def test_validate_float_and_phone_branches() -> None:
    """Float and phone validators should enforce conversion and length limits."""
    validator = InputValidator()

    type_error = validator.validate_float(None)
    assert type_error.is_valid is False
    assert "Cannot convert to float" in type_error.errors[0]

    value_error = validator.validate_float("nan-not-valid")
    assert value_error.is_valid is False
    assert "Cannot convert to float" in value_error.errors[0]

    too_low = validator.validate_float("-1.5", min_value=0)
    assert too_low.is_valid is False
    assert "minimum 0" in too_low.errors[0]

    too_short = validator.validate_phone("12")
    assert too_short.is_valid is False
    assert "Invalid phone number length" in too_short.errors[0]

    too_high = validator.validate_float("9.5", max_value=1.0)
    assert too_high.is_valid is False
    assert "maximum 1.0" in too_high.errors[0]


def test_validate_string_min_length_and_pattern() -> None:
    """String validator should enforce minimum length and regex pattern rules."""
    validator = InputValidator()

    result = validator.validate_string(" ab ", min_length=5, pattern=r"^[0-9]+$")
    assert result.is_valid is False
    assert len(result.errors) == 2


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


def test_validate_dict_url_float_and_unknown_types() -> None:
    """Dictionary validation should dispatch to url/float and fallback branches."""
    validator = InputValidator()
    schema = {
        "site": {"type": "url"},
        "weight": {"type": "float", "min_value": 1.0, "max_value": 20.0},
        "meta": {"type": "unsupported"},
    }

    result = validator.validate_dict(
        {
            "site": "ftp://example.com",
            "weight": "0.5",
            "meta": {"track": "collar"},
        },
        schema,
    )

    assert result.is_valid is False
    assert result.sanitized_value["meta"] == {"track": "collar"}
    assert any(error.startswith("site:") for error in result.errors)
    assert any(error.startswith("weight:") for error in result.errors)


def test_validate_dict_missing_required_field_and_optional_skip() -> None:
    """Schema validation should report missing required keys and skip absent optionals."""
    validator = InputValidator()
    schema = {
        "name": {"type": "str", "required": True},
        "nickname": {"type": "str", "required": False},
    }

    result = validator.validate_dict({}, schema)

    assert result.is_valid is False
    assert result.sanitized_value == {}
    assert result.errors == ["Missing required field: name"]


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


def test_validate_url_returns_validation_result_on_sanitizer_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """URL validator should convert sanitizer failures into invalid results."""
    validator = InputValidator()

    def _raise(_: str) -> str:
        raise ValidationError("invalid-url")

    monkeypatch.setattr(validator._sanitizer, "sanitize_url", _raise)

    result = validator.validate_url("bad")

    assert result.is_valid is False
    assert result.sanitized_value == "bad"
    assert len(result.errors) == 1
    assert "invalid-url" in result.errors[0]


def test_validate_dict_handles_float_and_url_rules() -> None:
    """Schema dict validation should route float and url rules through validators."""
    validator = InputValidator()

    result = validator.validate_dict(
        data={"threshold": "10.5", "endpoint": "https://example.com"},
        schema={
            "threshold": {"type": "float", "max_value": 5.0},
            "endpoint": {"type": "url"},
        },
    )

    assert result.is_valid is False
    assert "threshold: Value 10.5 > maximum 5.0" in result.errors
    assert result.sanitized_value == {"endpoint": "https://example.com"}
