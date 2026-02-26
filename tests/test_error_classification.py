"""Tests for error classification helpers."""

import pytest

from custom_components.pawcontrol.error_classification import classify_error_reason


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("missing_instance", "missing_service"),
        ("missing_services_api", "missing_service"),
        ("missing_notify_service", "missing_service"),
        ("service_not_executed", "guard_skipped"),
        ("service_unavailable", "missing_service"),
        ("auth_error", "auth_error"),
        ("authentication_error", "auth_error"),
        ("authentication_failed", "auth_error"),
        ("unauthorized", "auth_error"),
        ("forbidden", "auth_error"),
    ],
)
def test_classify_error_reason_uses_explicit_reason_mapping(
    reason: str, expected: str
) -> None:
    """Known reason labels should map to stable classifications."""
    assert classify_error_reason(reason) == expected


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("Invalid login token", "auth_error"),
        ("Device unreachable", "device_unreachable"),
        ("Connection refused", "device_unreachable"),
        ("request timeout", "timeout"),
        ("deadline exceeded", "timeout"),
        ("429 too many requests", "rate_limited"),
        ("Rate limit reached", "rate_limited"),
    ],
)
def test_classify_error_reason_uses_error_hints(error: str, expected: str) -> None:
    """Unmapped reasons should fall back to classification by error text hints."""
    assert classify_error_reason("not_mapped", error=error) == expected


def test_classify_error_reason_handles_none_and_whitespace_unknown() -> None:
    """Unknown or empty inputs should classify as unknown."""
    assert classify_error_reason(None, error=None) == "unknown"
    assert classify_error_reason("  ", error="  ") == "unknown"


def test_classify_error_reason_treats_exception_reason_explicitly() -> None:
    """The explicit exception reason should classify to exception."""
    assert classify_error_reason("exception") == "exception"


def test_classify_error_reason_handles_exception_objects() -> None:
    """Exception objects should be normalized from their string representation."""
    error = RuntimeError("Host is down")
    assert classify_error_reason("not_mapped", error=error) == "device_unreachable"


def test_classify_error_reason_preserves_reason_mapping_precedence() -> None:
    """Known reasons should win over conflicting error hint text."""
    assert (
        classify_error_reason(
            "service_not_executed",
            error="Authentication failed due to bad credentials",
        )
        == "guard_skipped"
    )
