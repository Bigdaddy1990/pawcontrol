"""Additional coverage tests for shared error classification helpers."""

import pytest

from custom_components.pawcontrol.error_classification import classify_error_reason


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("missing_services_api", "missing_service"),
        ("missing_notify_service", "missing_service"),
        ("auth_error", "auth_error"),
        ("authentication_error", "auth_error"),
        ("authentication_failed", "auth_error"),
        ("unauthorized", "auth_error"),
        ("forbidden", "auth_error"),
    ],
)
def test_classify_error_reason_supports_all_explicit_reason_mappings(
    reason: str, expected: str
) -> None:
    """Every explicit reason mapping should classify deterministically."""
    assert classify_error_reason(reason) == expected


def test_classify_error_reason_prioritises_auth_hints_over_other_hints() -> None:
    """Auth hints are checked first and should win for mixed error messages."""
    error_text = "token expired and network is unreachable"
    assert classify_error_reason("unknown", error=error_text) == "auth_error"


def test_classify_error_reason_treats_whitespace_reason_as_unknown() -> None:
    """Whitespace-only reason strings should not resolve to explicit mappings."""
    assert classify_error_reason("   ", error=None) == "unknown"
