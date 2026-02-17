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
# StructuredLogger
# ---------------------------------------------------------------------------


class StructuredLogger:
    """Context-aware structured logger for PawControl.

    Wraps :class:`logging.Logger` and accepts keyword-argument context that
    is appended to every log message as ``key=repr(value)`` pairs.  This
    keeps structured metadata visible in plain-text HA logs without
    requiring a JSON log handler.

    Sensitive keys are automatically redacted before the message is emitted
    so credentials never reach the log file.

    Usage::

        _LOGGER = StructuredLogger(__name__)

        _LOGGER.warning(
            "Webhook timestamp too old",
            timestamp=ts,
            current_time=now,
            diff=diff,
        )

    Args:
        name: Logger name, typically ``__name__`` from the calling module.
    """

    __slots__ = ("_logger",)

    def __init__(self, name: str) -> None:
        """Initialise a :class:`StructuredLogger` for *name*.

        Args:
            name: Logger name passed straight to :func:`logging.getLogger`.
        """
        self._logger: logging.Logger = logging.getLogger(name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_context(**kwargs: Any) -> str:
        """Format keyword context pairs as a ``' | key=repr(value)'`` suffix.

        Sensitive keys are redacted before formatting.

        Args:
            **kwargs: Arbitrary structured context to append.

        Returns:
            Formatted context suffix, or ``""`` when *kwargs* is empty.
        """
        if not kwargs:
            return ""
        pairs: list[str] = []
        for k, v in kwargs.items():
            safe_v = _REDACTED if _is_sensitive_key(k.lower()) else v
            pairs.append(f"{k}={safe_v!r}")
        return " | " + " ".join(pairs)

    def _emit(
        self,
        level: int,
        message: str,
        /,
        *args: object,
        exc_info: bool = False,
        stack_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Emit a log record at *level* with optional structured context.

        Args:
            level: :mod:`logging` level constant (e.g. ``logging.DEBUG``).
            message: Log message, optionally with ``%``-style placeholders.
            *args: Positional arguments for ``%``-style message formatting.
            exc_info: When ``True`` the current exception is attached.
            stack_info: When ``True`` the current stack is attached.
            **kwargs: Structured context key/value pairs.
        """
        if not self._logger.isEnabledFor(level):
            return
        suffix = self._format_context(**kwargs)
        if args:
            # Honour %-style formatting so existing callers using
            # ``_LOGGER.debug("foo %s", bar)`` continue to work.
            try:
                formatted = message % args + suffix
            except TypeError, ValueError:
                formatted = str(message) + str(args) + suffix
        else:
            formatted = message + suffix
        self._logger.log(level, formatted, exc_info=exc_info, stack_info=stack_info)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def debug(self, message: str, /, *args: object, **kwargs: Any) -> None:
        """Log a DEBUG message with optional structured context.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            **kwargs: Structured context key/value pairs.
        """
        self._emit(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, /, *args: object, **kwargs: Any) -> None:
        """Log an INFO message with optional structured context.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            **kwargs: Structured context key/value pairs.
        """
        self._emit(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, /, *args: object, **kwargs: Any) -> None:
        """Log a WARNING message with optional structured context.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            **kwargs: Structured context key/value pairs.
        """
        self._emit(logging.WARNING, message, *args, **kwargs)

    def error(
        self,
        message: str,
        /,
        *args: object,
        exc_info: bool = False,
        **kwargs: Any,
    ) -> None:
        """Log an ERROR message with optional structured context.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            exc_info: When ``True`` the current exception is attached.
            **kwargs: Structured context key/value pairs.
        """
        self._emit(logging.ERROR, message, *args, exc_info=exc_info, **kwargs)

    def exception(self, message: str, /, *args: object, **kwargs: Any) -> None:
        """Log at ERROR level and attach the current exception traceback.

        Equivalent to ``error(message, exc_info=True, …)``.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            **kwargs: Structured context key/value pairs (never exc_info).
        """
        self._emit(logging.ERROR, message, *args, exc_info=True, **kwargs)

    def critical(self, message: str, /, *args: object, **kwargs: Any) -> None:
        """Log a CRITICAL message with optional structured context.

        Args:
            message: Log message.
            *args: ``%``-style format arguments.
            **kwargs: Structured context key/value pairs.
        """
        self._emit(logging.CRITICAL, message, *args, **kwargs)

    @property
    def logger(self) -> logging.Logger:
        """Return the underlying :class:`logging.Logger` instance.

        Useful when interacting with third-party code that expects a stdlib
        logger directly.
        """
        return self._logger

    def isEnabledFor(self, level: int) -> bool:
        """Return ``True`` if *level* would produce a log record.

        Delegates directly to the underlying :class:`logging.Logger`.

        Args:
            level: :mod:`logging` level constant.
        """
        return self._logger.isEnabledFor(level)


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
    "StructuredLogger",
    "get_logger",
    "log_api_client_build_error",
    "log_config_entry_setup",
    "redact_sensitive",
    "redact_value",
]
