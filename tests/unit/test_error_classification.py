"""Tests for error classification helpers."""

from custom_components.pawcontrol.error_classification import classify_error_reason


def test_classify_error_reason_prefers_explicit_reason_mapping() -> None:
    """Known reason labels should map directly to stable categories."""
    assert classify_error_reason("missing_instance") == "missing_service"
    assert classify_error_reason("service_not_executed") == "guard_skipped"
    assert classify_error_reason("authentication_failed") == "auth_error"


def test_classify_error_reason_uses_hint_matching() -> None:
    """Message hint matching should classify common runtime failures."""
    assert (
        classify_error_reason(None, error="Token invalid for this login")
        == "auth_error"
    )
    assert (
        classify_error_reason("exception", error="Connection refused by host")
        == "device_unreachable"
    )
    assert classify_error_reason("", error="Deadline exceeded") == "timeout"
    assert (
        classify_error_reason("", error="HTTP 429 Too many requests") == "rate_limited"
    )


def test_classify_error_reason_handles_exception_values_and_unknown() -> None:
    """Exceptions should be normalized while unknown inputs fall back safely."""
    assert (
        classify_error_reason(
            "exception",
            error=RuntimeError("Credential check failed"),
        )
        == "auth_error"
    )
    assert classify_error_reason("exception") == "exception"
    assert classify_error_reason("something-new", error=None) == "unknown"
