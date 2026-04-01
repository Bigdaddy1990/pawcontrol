"""Tests for error classification helpers."""

from custom_components.pawcontrol.error_classification import (
    _normalise_text,
    classify_error_reason,
)


def test_normalise_text_handles_none_and_exceptions() -> None:
    """_normalise_text should safely normalize optional values."""
    assert _normalise_text(None) == ""
    assert _normalise_text("  HeLLo  ") == "hello"
    assert _normalise_text(ValueError("  Bad Token  ")) == "bad token"


def test_classify_error_reason_prefers_explicit_reason_mapping() -> None:
    """Known reason strings should map to stable class labels."""
    assert classify_error_reason("missing_services_api") == "missing_service"
    assert classify_error_reason("service_not_executed") == "guard_skipped"


def test_classify_error_reason_detects_auth_unreachable_timeout_and_rate_limit() -> (
    None
):
    """Message hint matching should classify common backend/API failures."""
    assert classify_error_reason(None, error="unauthorized request") == "auth_error"
    assert classify_error_reason(None, error="Connection refused by host") == (
        "device_unreachable"
    )
    assert (
        classify_error_reason(None, error=TimeoutError("deadline exceeded"))
        == "timeout"
    )
    assert classify_error_reason(None, error="429 too many requests") == "rate_limited"


def test_classify_error_reason_returns_exception_and_unknown_fallbacks() -> None:
    """Unhandled inputs should return exception/unknown fallback labels."""
    assert classify_error_reason(" exception ") == "exception"
    assert classify_error_reason("not_mapped", error="something else") == "unknown"
