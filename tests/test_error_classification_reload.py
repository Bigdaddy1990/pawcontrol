"""Tests for verifying error classification behavior and module reloads."""

import importlib

import pytest

from custom_components.pawcontrol import error_classification


class _CustomError(Exception):
    """Custom error used to exercise Exception normalization."""


def test_error_classification_module_reload_executes_top_level() -> None:
    """Reloading the module should preserve expected classifications."""
    importlib.reload(error_classification)

    assert (
        error_classification.classify_error_reason("missing_instance")
        == "missing_service"
    )
    assert error_classification.classify_error_reason("service_not_executed") == (
        "guard_skipped"
    )
    assert error_classification.classify_error_reason(None, error="Timed out") == (
        "timeout"
    )


@pytest.mark.parametrize(
    ("reason", "error", "expected"),
    [
        pytest.param(
            "missing_services_api", None, "missing_service", id="mapped-reason"
        ),
        pytest.param(
            "AUTHENTICATION_ERROR", None, "auth_error", id="mapped-reason-normalized"
        ),
        pytest.param(None, "forbidden by policy", "auth_error", id="auth-hint"),
        pytest.param(None, "host is down", "device_unreachable", id="unreachable-hint"),
        pytest.param(None, "Deadline exceeded", "timeout", id="timeout-hint"),
        pytest.param(
            None, "429 too many requests", "rate_limited", id="rate-limit-hint"
        ),
        pytest.param("exception", "", "exception", id="explicit-exception"),
        pytest.param(None, None, "unknown", id="unknown-default"),
    ],
)
def test_classify_error_reason_branches(
    reason: str | None,
    error: Exception | str | None,
    expected: str,
) -> None:
    """Classifier should route reasons and message hints to stable categories."""
    assert error_classification.classify_error_reason(reason, error=error) == expected


def test_classify_error_reason_prefers_reason_mapping_over_error_hints() -> None:
    """An explicit mapped reason should win over unrelated error hint text."""
    assert (
        error_classification.classify_error_reason(
            "service_unavailable",
            error="token expired",
        )
        == "missing_service"
    )


def test_classify_error_reason_normalizes_exception_objects() -> None:
    """Exception instances should be stringified and normalized before matching."""
    assert (
        error_classification.classify_error_reason(
            None,
            error=_CustomError(" Connection Reset by peer "),
        )
        == "device_unreachable"
    )
