"""Helpers for redacting sensitive diagnostics information."""

from collections.abc import Iterable, Mapping
import re
from typing import Final

from custom_components.pawcontrol.types import (
    JSONMutableMapping,
    JSONMutableSequence,
    JSONValue,
)

__all__ = [
    "compile_redaction_patterns",
    "redact_sensitive_data",
]


type RedactionPatterns = tuple[re.Pattern[str], ...]
"""Precompiled redaction expressions keyed by normalised field names."""


_REDACTED_REPLACEMENT: Final = "**REDACTED**"
"""Marker inserted when a value matches the redaction guardrails."""


def compile_redaction_patterns(keys: Iterable[str]) -> RedactionPatterns:
    """Return compiled regex patterns for ``keys`` respecting word boundaries."""  # noqa: E111

    normalized = {key.lower() for key in keys}  # noqa: E111
    return tuple(  # noqa: E111
        re.compile(rf"(?:^|[^a-z0-9]){re.escape(key)}(?:$|[^a-z0-9])")
        for key in sorted(normalized)
    )


def redact_sensitive_data(data: JSONValue, *, patterns: RedactionPatterns) -> JSONValue:
    """Recursively redact sensitive data using precompiled ``patterns``."""  # noqa: E111

    if isinstance(data, Mapping):  # noqa: E111
        redacted: JSONMutableMapping = {}
        for key, value in dict(data).items():
            key_lower = key.lower()  # noqa: E111
            if any(pattern.search(key_lower) for pattern in patterns):  # noqa: E111
                redacted[key] = _REDACTED_REPLACEMENT
            else:  # noqa: E111
                redacted[key] = redact_sensitive_data(value, patterns=patterns)
        return redacted

    if isinstance(data, list):  # noqa: E111
        redacted_sequence: JSONMutableSequence = [
            redact_sensitive_data(item, patterns=patterns) for item in data
        ]
        return redacted_sequence

    if isinstance(data, str):  # noqa: E111
        if _looks_like_sensitive_string(data):
            return _REDACTED_REPLACEMENT  # noqa: E111
        return data

    return data  # noqa: E111


def _looks_like_sensitive_string(value: str) -> bool:
    """Return True if ``value`` appears to contain sensitive information."""  # noqa: E111

    sensitive_patterns = [  # noqa: E111
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        r"\b[A-Za-z0-9]{20,}\b",
        r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b",
    ]

    return any(re.search(pattern, value) for pattern in sensitive_patterns)  # noqa: E111
