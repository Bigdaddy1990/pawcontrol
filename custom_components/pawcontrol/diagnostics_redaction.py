"""Helpers for redacting sensitive diagnostics information."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

__all__ = [
    "compile_redaction_patterns",
    "redact_sensitive_data",
]


def compile_redaction_patterns(keys: Iterable[str]) -> tuple[re.Pattern[str], ...]:
    """Return compiled regex patterns for ``keys`` respecting word boundaries."""

    normalized = {key.lower() for key in keys}
    return tuple(
        re.compile(rf"(?:^|[^a-z0-9]){re.escape(key)}(?:$|[^a-z0-9])")
        for key in sorted(normalized)
    )


def redact_sensitive_data(data: Any, *, patterns: tuple[re.Pattern[str], ...]) -> Any:
    """Recursively redact sensitive data using precompiled ``patterns``."""

    if isinstance(data, dict):
        redacted: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(pattern.search(key_lower) for pattern in patterns):
                redacted[key] = "**REDACTED**"
            else:
                redacted[key] = redact_sensitive_data(value, patterns=patterns)
        return redacted

    if isinstance(data, list):
        return [redact_sensitive_data(item, patterns=patterns) for item in data]

    if isinstance(data, str):
        if _looks_like_sensitive_string(data):
            return "**REDACTED**"
        return data

    return data


def _looks_like_sensitive_string(value: str) -> bool:
    """Return True if ``value`` appears to contain sensitive information."""

    sensitive_patterns = [
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        r"\b[A-Za-z0-9]{20,}\b",
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ]

    return any(re.search(pattern, value) for pattern in sensitive_patterns)
