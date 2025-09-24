"""Translation validators used by hassfest tests."""

from __future__ import annotations

import re

import voluptuous as vol

_SINGLE_QUOTED_PLACEHOLDER = re.compile(r"'[^']*\{[^}]+\}[^']*'")


def string_no_single_quoted_placeholders(value: str) -> str:
    """Validate that a translation string does not single-quote placeholders."""

    if not isinstance(value, str):
        raise vol.Invalid("Translation value must be a string")
    if _SINGLE_QUOTED_PLACEHOLDER.search(value):
        raise vol.Invalid("Placeholders must not be enclosed in single quotes")
    return value


__all__ = ["string_no_single_quoted_placeholders"]
