"""Translation helpers used by hassfest tests."""

from __future__ import annotations

import re

import voluptuous as vol

_SINGLE_QUOTED_PLACEHOLDER = re.compile(r"'[^']*\{[^}]+\}[^']*'")


def _ensure_no_single_quoted_placeholder(value: str) -> str:
    if _SINGLE_QUOTED_PLACEHOLDER.search(value):
        raise vol.Invalid("Placeholders may not be wrapped in single quotes")
    return value


string_no_single_quoted_placeholders = vol.All(
    str, _ensure_no_single_quoted_placeholder
)


__all__ = ["string_no_single_quoted_placeholders"]
