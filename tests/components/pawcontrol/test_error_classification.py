"""Tests for error classification helpers."""

import pytest

from custom_components.pawcontrol.error_classification import (
    _normalise_text,
    classify_error_reason,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        ("  Timeout  ", "timeout"),
        (123, "123"),
        (ValueError("  Bad Token  "), "bad token"),
    ],
)
def test_normalise_text_handles_common_inputs(
    value: object | None, expected: str
) -> None:
    """_normalise_text should normalize different value types consistently."""
    assert _normalise_text(value) == expected


@pytest.mark.parametrize(
    ("reason", "error", "expected"),
    [
        ("missing_instance", None, "missing_service"),
        ("service_not_executed", "ignored", "guard_skipped"),
        ("exception", None, "exception"),
        (None, "invalid credentials", "auth_error"),
        (None, "Host is down", "device_unreachable"),
        (None, "deadline exceeded while waiting", "timeout"),
        (None, "HTTP 429 too many requests", "rate_limited"),
        ("unknown_reason", "completely novel error", "unknown"),
    ],
)
def test_classify_error_reason(
    reason: str | None,
    error: Exception | str | None,
    expected: str,
) -> None:
    """classify_error_reason should map explicit reasons and text hints."""
    assert classify_error_reason(reason, error=error) == expected


def test_classify_error_reason_prioritises_explicit_reason_mapping() -> None:
    """Reason mappings should win over conflicting text hints."""
    assert (
        classify_error_reason("service_unavailable", error="token expired")
        == "missing_service"
    )
