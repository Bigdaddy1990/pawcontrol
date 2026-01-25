"""Shared error classification helpers for PawControl telemetry."""

from __future__ import annotations

from typing import Final

type ErrorClassification = str


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
  """Return a lowercase string for matching against ``value``."""

  if value is None:
    return ""
  if isinstance(value, Exception):
    text = str(value)
  else:
    text = str(value)
  return text.strip().lower()


def classify_error_reason(
  reason: str | None,
  *,
  error: Exception | str | None = None,
) -> ErrorClassification:
  """Return a stable classification for error ``reason`` and ``error``."""

  reason_text = _normalise_text(reason)
  if reason_text:
    classified = _REASON_CLASSIFICATIONS.get(reason_text)
    if classified is not None:
      return classified

  error_text = _normalise_text(error)
  for hint in _AUTH_HINTS:
    if hint in error_text:
      return "auth_error"
  for hint in _UNREACHABLE_HINTS:
    if hint in error_text:
      return "device_unreachable"
  for hint in _TIMEOUT_HINTS:
    if hint in error_text:
      return "timeout"
  for hint in _RATE_LIMIT_HINTS:
    if hint in error_text:
      return "rate_limited"

  if reason_text == "exception":
    return "exception"

  return "unknown"
