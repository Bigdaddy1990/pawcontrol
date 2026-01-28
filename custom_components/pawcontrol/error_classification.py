"""Shared error classification helpers for PawControl telemetry."""

from __future__ import annotations

from typing import Final

# Type alias for error classification strings
ErrorClassification = str

# Mapping of explicit reason strings to classification labels
_REASON_CLASSIFICATIONS: Final[dict[str, ErrorClassification]] = {
    "missing_instance": "missing_service",
    "missing_services_api": "missing_service",
    "missing_notify_service": "missing_service",
    "service_not_executed": "guard_skipped",
    "service_unavailable": "missing_service",
    "auth_error": "auth_error",
    "authentication_error": "auth_error",
    "authentication_failed": "auth_error",
    "unauthorized": "auth_error",
    "forbidden": "auth_error",
}

# Collections of keyword hints used to derive classifications from error messages
_AUTH_HINTS: Final[tuple[str, ...]] = (
    "auth",
    "unauthorized",
    "forbidden",
    "token",
    "credential",
    "login",
)
_UNREACHABLE_HINTS: Final[tuple[str, ...]] = (
    "unreachable",
    "not reachable",
    "host is down",
    "network is unreachable",
    "connection refused",
    "connection reset",
    "connection error",
    "device offline",
)
_TIMEOUT_HINTS: Final[tuple[str, ...]] = (
    "timeout",
    "timed out",
    "deadline exceeded",
)
_RATE_LIMIT_HINTS: Final[tuple[str, ...]] = (
    "rate limit",
    "too many requests",
    "429",
)


def _normalise_text(value: object | None) -> str:
    """Return a lowercase string suitable for matching against ``value``."""
    if value is None:
        return ""
    # When ``value`` is an Exception, use its string form; otherwise cast to str
    text = str(value) if isinstance(value, Exception) else str(value)
    return text.strip().lower()


def classify_error_reason(
    reason: str | None,
    *,
    error: Exception | str | None = None,
) -> ErrorClassification:
    """Return a stable classification for the given error ``reason`` and ``error``.

    This helper attempts to normalise both explicit reason strings and free-form
    error messages into a small set of categories, making it easier to aggregate
    metrics across diverse failures. It will always return one of a handful of
    known values such as ``auth_error``, ``device_unreachable``, ``timeout``,
    ``rate_limited``, ``missing_service``, ``guard_skipped``, ``exception`` or
    ``unknown``.
    """

    reason_text = _normalise_text(reason)
    if reason_text:
        classified = _REASON_CLASSIFICATIONS.get(reason_text)
        if classified is not None:
            return classified

    error_text = _normalise_text(error)
    # Hints to detect authentication/authorization errors
    for hint in _AUTH_HINTS:
        if hint in error_text:
            return "auth_error"
    # Hints to detect unreachable devices or network issues
    for hint in _UNREACHABLE_HINTS:
        if hint in error_text:
            return "device_unreachable"
    # Hints to detect timeout conditions
    for hint in _TIMEOUT_HINTS:
        if hint in error_text:
            return "timeout"
    # Hints to detect rate limiting
    for hint in _RATE_LIMIT_HINTS:
        if hint in error_text:
            return "rate_limited"

    # Explicitly classify generic exception reasons
    if reason_text == "exception":
        return "exception"

    return "unknown"