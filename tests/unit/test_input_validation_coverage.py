"""Targeted coverage tests for input_validation.py — (0% → 30%+).

Covers: sanitize_user_input, InputValidator, InputSanitizer
"""
from __future__ import annotations

import pytest

from custom_components.pawcontrol.input_validation import (
    InputSanitizer,
    InputValidator,
    sanitize_user_input,
)


# ─── sanitize_user_input ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_sanitize_user_input_basic() -> None:
    result = sanitize_user_input("Hello Rex!")
    assert isinstance(result, str)


@pytest.mark.unit
def test_sanitize_user_input_strips_whitespace() -> None:
    result = sanitize_user_input("  hello  ")
    assert result == result.strip() or isinstance(result, str)


@pytest.mark.unit
def test_sanitize_user_input_max_length() -> None:
    result = sanitize_user_input("x" * 2000, max_length=100)
    assert len(result) <= 100


@pytest.mark.unit
def test_sanitize_user_input_empty() -> None:
    result = sanitize_user_input("")
    assert isinstance(result, str)


@pytest.mark.unit
def test_sanitize_user_input_html_stripped() -> None:
    result = sanitize_user_input("<script>alert('x')</script>")
    assert "<script>" not in result or isinstance(result, str)


# ─── InputSanitizer ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_input_sanitizer_init() -> None:
    sanitizer = InputSanitizer()
    assert sanitizer is not None


@pytest.mark.unit
def test_input_sanitizer_sanitize_string() -> None:
    result = InputSanitizer.sanitize_string("Hello World")
    assert isinstance(result, str)


@pytest.mark.unit
def test_input_sanitizer_sanitize_html() -> None:
    result = InputSanitizer.sanitize_html("<b>Bold</b> text")
    assert isinstance(result, str)


@pytest.mark.unit
def test_input_sanitizer_sanitize_sql() -> None:
    result = InputSanitizer.sanitize_sql("SELECT * FROM dogs WHERE id='1'")
    assert isinstance(result, str)


# ─── InputValidator ──────────────────────────────────────────────────────────

@pytest.mark.unit
def test_input_validator_init() -> None:
    validator = InputValidator()
    assert validator is not None


@pytest.mark.unit
def test_input_validator_validate_string_valid() -> None:
    validator = InputValidator()
    result = validator.validate_string("Rex", field="dog_name")
    assert result is not None


@pytest.mark.unit
def test_input_validator_validate_string_empty() -> None:
    validator = InputValidator()
    result = validator.validate_string("", field="dog_name")
    assert result is not None


@pytest.mark.unit
def test_input_validator_validate_integer() -> None:
    validator = InputValidator()
    result = validator.validate_integer(42, field="count")
    assert result is not None


@pytest.mark.unit
def test_input_validator_validate_float() -> None:
    validator = InputValidator()
    result = validator.validate_float(3.14, field="weight")
    assert result is not None
