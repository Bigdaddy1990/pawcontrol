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


def test_given_validation_result_when_cast_to_bool_then_reflects_validity() -> None:
    """ValidationResult bool conversion should mirror is_valid."""
    assert bool(ValidationResult(True, "ok", [])) is True
    assert bool(ValidationResult(False, None, ["bad"])) is False


def test_given_sql_input_when_sanitized_then_escape_or_reject_injection() -> None:
    """SQL sanitizer should escape safe content and reject injected payloads."""
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_sql("O'Hara") == "O''Hara"

    with pytest.raises(ValidationError, match="SQL injection pattern detected"):
        sanitizer.sanitize_sql("x'; DROP TABLE dogs;")


@pytest.mark.parametrize(
    ("url", "expected_message"),
    [
        ("ftp://example.com", "Only http and https schemes"),
        ("https://example.com/javascript:alert(1)", "JavaScript protocol"),
    ],
)
def test_given_url_input_when_scheme_or_protocol_is_unsafe_then_raise_validation_error(
    url: str,
    expected_message: str,
) -> None:
    """URL sanitizer should reject dangerous schemes and script URLs."""
    sanitizer = InputSanitizer()

    assert sanitizer.sanitize_url("https://example.com/path?q=1") == (
        "https://example.com/path?q=1"
    )

    with pytest.raises(ValidationError, match=expected_message):
        sanitizer.sanitize_url(url)


def test_given_url_when_parse_raises_then_wrap_as_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """URL sanitizer should wrap parse errors as validation errors."""
    sanitizer = InputSanitizer()

    def _raise_parse_error(_: str) -> object:
        raise RuntimeError("boom")

    monkeypatch.setattr("urllib.parse.urlparse", _raise_parse_error)

    with pytest.raises(ValidationError, match="URL could not be parsed"):
        sanitizer.sanitize_url("https://example.com")


@pytest.mark.parametrize(
    "path",
    [
        "..%2fsecret.txt",
        "safe/../secret.txt",
    ],
)
def test_given_path_when_traversal_pattern_detected_then_raise_validation_error(
    path: str,
) -> None:
    """Path sanitizer should block traversal and normalize safe input."""
    sanitizer = InputSanitizer()

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path(path)


def test_given_path_when_safe_then_returns_normalized_absolute_path() -> None:
    """Path sanitizer should normalize safe input."""
    sanitizer = InputSanitizer()
    normalized = sanitizer.sanitize_path("docs/readme.txt")
    assert Path(normalized).as_posix().endswith("docs/readme.txt")


def test_given_path_when_regex_patterns_are_bypassed_then_segment_guard_still_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path sanitizer should still reject '..' segments beyond regex matching."""
    sanitizer = InputSanitizer()
    monkeypatch.setattr(sanitizer, "PATH_TRAVERSAL_PATTERNS", ())

    with pytest.raises(ValidationError, match="Path traversal sequences"):
        sanitizer.sanitize_path("safe/../secret.txt")


def test_given_html_and_string_inputs_when_sanitized_then_escape_and_filter() -> None:
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


@pytest.mark.parametrize(
    ("value", "kwargs", "expected_valid", "expected_sanitized", "expected_error"),
    [
        (None, {}, False, None, "Cannot convert to integer"),
        ("not-a-number", {}, False, None, "Cannot convert to integer"),
        ("42", {"max_value": 10}, False, 42, "maximum 10"),
        ("-2", {"min_value": 0}, False, -2, "minimum 0"),
        ("7", {"min_value": 0, "max_value": 10}, True, 7, None),
    ],
)
def test_given_integer_input_when_validated_then_type_and_range_rules_apply(
    value: object,
    kwargs: dict[str, int],
    expected_valid: bool,
    expected_sanitized: int | None,
    expected_error: str | None,
) -> None:
    """Integer validator should return useful errors for conversion/range failures."""
    validator = InputValidator()

    result = validator.validate_integer(value, **kwargs)
    assert result.is_valid is expected_valid
    assert result.sanitized_value == expected_sanitized
    if expected_error is None:
        assert result.errors == []
    else:
        assert expected_error in result.errors[0]


@pytest.mark.parametrize(
    ("value", "kwargs", "expected_error"),
    [
        (None, {}, "Cannot convert to float"),
        ("nan-not-valid", {}, "Cannot convert to float"),
        ("-1.5", {"min_value": 0}, "minimum 0"),
        ("9.5", {"max_value": 1.0}, "maximum 1.0"),
    ],
)
def test_given_float_input_when_validated_then_guard_branches_return_errors(
    value: object,
    kwargs: dict[str, float],
    expected_error: str,
) -> None:
    """Float and phone validators should enforce conversion and length limits."""
    validator = InputValidator()

    result = validator.validate_float(value, **kwargs)
    assert result.is_valid is False
    assert expected_error in result.errors[0]


def test_given_phone_input_when_digit_count_is_invalid_then_return_error() -> None:
    """Phone validator should enforce minimum digit lengths."""
    validator = InputValidator()
    too_short = validator.validate_phone("12")
    assert too_short.is_valid is False
    assert "Invalid phone number length" in too_short.errors[0]


def test_given_string_input_when_validated_then_collect_length_and_pattern_errors() -> (
    None
):
    """String validator should enforce minimum length and regex pattern rules."""
    validator = InputValidator()

    result = validator.validate_string(" ab ", min_length=5, pattern=r"^[0-9]+$")
    assert result.is_valid is False
    assert len(result.errors) == 2


def test_given_schema_dict_when_validating_then_collect_errors_and_keep_valid() -> None:
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


def test_given_schema_with_url_float_unknown_when_validating_then_dispatch() -> None:
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


def test_given_schema_with_validator_aliases_when_validating_then_dispatches() -> None:
    """Schema aliases should normalize and dispatch to canonical validators."""
    validator = InputValidator()
    schema = {
        "title": {"type": " Text ", "max_length": 5},
        "count": {"type": "INTEGER", "min_value": 1, "max_value": 5},
    }

    result = validator.validate_dict(
        {"title": "  Puppy  ", "count": "4"},
        schema,
    )

    assert result.is_valid is True
    assert result.sanitized_value == {"title": "Puppy", "count": 4}
    assert result.errors == []


def test_given_non_string_for_string_field_when_validating_then_return_type_error() -> (
    None
):
    """String-like validators should reject non-string payloads with clear errors."""
    validator = InputValidator()
    schema = {"email": {"type": "email"}}

    result = validator.validate_dict({"email": 42}, schema)

    assert result.is_valid is False
    assert result.sanitized_value == {}
    assert "Expected text input" in result.errors[0]


def test_given_incompatible_validator_args_when_validating_then_capture_dispatch_error(
) -> None:
    """Validation dispatch should convert argument/type failures into field errors."""
    validator = InputValidator()
    schema = {
        "count": {
            "type": "int",
            "min_value": "bad",
            "max_value": 10,
        }
    }

    result = validator.validate_dict({"count": "4"}, schema)

    assert result.is_valid is False
    assert result.sanitized_value == {}
    assert "rejected provided arguments" in result.errors[0]


def test_given_validator_raises_value_error_when_validating_then_capture_dispatch_error(
) -> None:
    """Validation dispatch should map validator-raised ValueError to field errors."""
    validator = InputValidator()
    schema = {"count": {"type": "int"}}

    def _raise_value_error(value: object, **_: object) -> ValidationResult:
        raise ValueError(f"bad value: {value}")

    validator.validate_integer = _raise_value_error  # type: ignore[method-assign]

    result = validator.validate_dict({"count": "4"}, schema)

    assert result.is_valid is False
    assert result.sanitized_value == {}
    assert "rejected value" in result.errors[0]


def test_given_missing_required_field_when_validating_then_return_required_error() -> (
    None
):
    """Schema validation should flag missing required keys and skip optionals."""
    validator = InputValidator()
    schema = {
        "name": {"type": "str", "required": True},
        "nickname": {"type": "str", "required": False},
    }

    result = validator.validate_dict({}, schema)

    assert result.is_valid is False
    assert result.sanitized_value == {}
    assert result.errors == ["Missing required field: name"]


def test_given_validate_and_sanitize_when_called_then_return_value_or_raise() -> None:
    """Wrapper helper should return sanitized values and raise on invalid input."""
    assert (
        validate_and_sanitize("  hello  ", "validate_string", max_length=10) == "hello"
    )

    with pytest.raises(ValidationError, match="Validation failed"):
        validate_and_sanitize("bad-email", "validate_email")


def test_given_validate_and_sanitize_with_alias_name_then_normalizes_method_name() -> (
    None
):
    """Wrapper should normalize shorthand validator names to method calls."""
    assert validate_and_sanitize("  woof  ", "string", max_length=10) == "woof"


def test_given_validate_and_sanitize_when_unknown_validator_then_raise() -> None:
    """Wrapper should fail fast with a useful unknown-validator message."""
    with pytest.raises(ValidationError, match="Unknown validator"):
        validate_and_sanitize("value", "validate_does_not_exist")


def test_given_validate_and_sanitize_when_validator_raises_type_error_then_wrap() -> (
    None
):
    """Wrapper should convert validator-raised TypeError into ValidationError."""
    with pytest.raises(ValidationError, match="Validation raised TypeError"):
        validate_and_sanitize("anything", "validate_integer", extra_arg=True)


def test_given_validate_and_sanitize_when_validator_raises_value_error_then_wrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrapper should convert validator-raised ValueError into ValidationError."""
    validator = InputValidator()

    def _raise(_: object, **__: object) -> ValidationResult:
        raise ValueError("boom")

    monkeypatch.setattr(validator, "validate_integer", _raise)
    monkeypatch.setattr(
        "custom_components.pawcontrol.input_validation.InputValidator",
        lambda: validator,
    )

    with pytest.raises(ValidationError, match="Validation raised ValueError"):
        validate_and_sanitize("anything", "validate_integer")


def test_given_user_input_when_sanitized_then_trim_truncate_and_strip_controls() -> (
    None
):
    """Convenience helper should trim, truncate, and strip disallowed chars."""
    cleaned = sanitize_user_input("  abc\x01\nxyz  ", max_length=5)
    assert cleaned == "abc\n"


def test_given_url_validator_when_sanitizer_raises_then_return_invalid_result(
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


def test_given_dispatch_mapping_to_noncallable_when_validating_then_fallback_to_raw_value(  # noqa: E501
) -> None:
    """Validation dispatch should gracefully fall back when mapping is not callable."""
    validator = InputValidator()
    validator._validator_dispatch["custom"] = "validate_missing"
    schema = {"meta": {"type": "custom"}}

    result = validator.validate_dict({"meta": {"source": "manual"}}, schema)

    assert result.is_valid is True
    assert result.errors == []
    assert result.sanitized_value == {"meta": {"source": "manual"}}


def test_given_validator_kwargs_when_normalized_then_only_supported_keys_are_forwarded(
) -> None:
    """Validator kwargs normalization should drop unsupported schema attributes."""
    validator = InputValidator()
    schema = {
        "count": {
            "type": "int",
            "min_value": 1,
            "max_value": 5,
            "required": True,
            "description": "ignored metadata",
        }
    }

    result = validator.validate_dict({"count": "3"}, schema)

    assert result.is_valid is True
    assert result.errors == []
    assert result.sanitized_value == {"count": 3}
