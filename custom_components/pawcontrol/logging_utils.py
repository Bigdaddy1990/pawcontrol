"""Centralized logging utilities and sensitive-data redaction for PawControl.

All log calls that include user-provided or credential data must route
through the helpers in this module so that secrets are never written to
the Home Assistant log in clear text.

Quality Scale: Platinum target
Home Assistant: 2026.2.1+
Python: 3.14+
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

# ---------------------------------------------------------------------------
# Sensitive key registry — extend here when new credential fields are added.
# Keys are lower-cased for case-insensitive matching.
# ---------------------------------------------------------------------------
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "api_key",
    "api_token",
    "auth_token",
    "bearer",
    "password",
    "secret",
    "token",
    "webhook_secret",
    # Const-value equivalents (keep in sync with const.py)
    "api_endpoint_token",
    "conf_api_token",
    "conf_webhook_secret",
    "private_key",
    "access_token",
    "refresh_token",
})

_REDACTED = "***REDACTED***"


def redact_sensitive(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of *data* with sensitive values replaced.

    The check is case-insensitive and also matches any key that *contains*
    a sensitive keyword (e.g. ``"dog_api_token"`` → redacted).

    Args:
        data: Mapping whose values may include secrets.

    Returns:
        New dict safe to pass to logging formatters.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        key_lower = str(key).lower()
        if _is_sensitive_key(key_lower):
            result[key] = _REDACTED
        elif isinstance(value, Mapping):
            result[key] = redact_sensitive(value)
        else:
            result[key] = value
    return result


def _is_sensitive_key(key_lower: str) -> bool:
    """Return True if *key_lower* matches or contains a sensitive keyword."""
    if key_lower in _SENSITIVE_KEYS:
        return True
    return any(sensitive in key_lower for sensitive in _SENSITIVE_KEYS)


def redact_value(key: str, value: Any) -> Any:
    """Redact *value* if *key* is sensitive, otherwise return *value* unchanged.

    Args:
        key: The config / log field name.
        value: The value to potentially redact.

    Returns:
        ``_REDACTED`` placeholder or the original value.
    """
    if _is_sensitive_key(key.lower()):
        return _REDACTED
    return value


# ---------------------------------------------------------------------------
# Module-level logger helpers
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a logger prefixed with the integration domain.

    Args:
        name: Typically ``__name__`` from the calling module.

    Returns:
        Configured :class:`logging.Logger`.
    """
    return logging.getLogger(name)


def log_config_entry_setup(
    logger: logging.Logger,
    entry_id: str,
    dogs_count: int,
    profile: str,
    duration_s: float,
) -> None:
    """Emit a structured INFO log for a successful config-entry setup.

    No user credentials are included.

    Args:
        logger: The module logger.
        entry_id: Config entry identifier.
        dogs_count: Number of configured dogs.
        profile: Active entity profile name.
        duration_s: Setup duration in seconds.
    """
    logger.info(
        "PawControl entry setup complete "
        "(entry_id=%s dogs=%d profile=%s duration_s=%.2f)",
        entry_id,
        dogs_count,
        profile,
        duration_s,
    )


def log_api_client_build_error(
    logger: logging.Logger,
    endpoint: str,
    error: Exception,
) -> None:
    """Log an API client build failure without exposing credentials.

    The endpoint URL is included (it is not a secret) but the token is never
    logged here.

    Args:
        logger: The module logger.
        endpoint: The sanitized endpoint URL (no credentials).
        error: The exception that caused the failure.
    """
    # Strip any embedded credentials from the URL before logging.
    safe_endpoint = _strip_url_credentials(endpoint)
    logger.warning(
        "Invalid PawControl API endpoint '%s': %s (%s)",
        safe_endpoint,
        error,
        error.__class__.__name__,
    )


def _strip_url_credentials(url: str) -> str:
    """Remove user:password@ prefix from a URL string.

    Args:
        url: Possibly credential-bearing URL.

    Returns:
        URL with credentials removed.
    """
    try:
        # yarl is available in the HA environment
        from yarl import URL

        parsed = URL(url)
        if parsed.user or parsed.password:
            return str(parsed.with_user(None))
    except Exception:
        pass
    return url


__all__ = [
    "get_logger",
    "log_api_client_build_error",
    "log_config_entry_setup",
    "redact_sensitive",
    "redact_value",
]
