"""Coverage-focused tests for error classification helpers."""

import pytest

from custom_components.pawcontrol.error_classification import (
    _normalise_text,
    classify_error_reason,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("  Mixed CASE  ", "mixed case"),
        (RuntimeError("  LOGIN FAILED  "), "login failed"),
        (1234, "1234"),
    ],
)
def test_normalise_text_handles_supported_inputs(value: object, expected: str) -> None:
    """_normalise_text should trim and lower-case diverse value types."""
    assert _normalise_text(value) == expected


@pytest.mark.parametrize(
    ("reason", "error", "expected"),
    [
        (" FORBIDDEN ", None, "auth_error"),
        ("not_mapped", "network is unreachable", "device_unreachable"),
        ("not_mapped", "timed out while fetching", "timeout"),
        ("not_mapped", "too many requests", "rate_limited"),
        ("exception", "No hint text", "exception"),
    ],
)
def test_classify_error_reason_normalizes_reason_and_error(
    reason: str,
    error: str | None,
    expected: str,
) -> None:
    """Reason and error text should both be normalized before classification."""
    assert classify_error_reason(reason, error=error) == expected


def test_classify_error_reason_handles_exception_error_and_unknown_reason() -> None:
    """Unknown reasons with exception objects should still use error hints."""
    error = ConnectionError("Device offline")
    assert classify_error_reason("unmapped", error=error) == "device_unreachable"


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("missing_services_api", "missing_service"),
        ("service_not_executed", "guard_skipped"),
        (None, "unknown"),
    ],
)
def test_classify_error_reason_supports_explicit_reason_mappings(
    reason: str | None,
    expected: str,
) -> None:
    """Mapped reasons should resolve without relying on free-form error hints."""
    assert classify_error_reason(reason, error=None) == expected
