from __future__ import annotations

import pytest

from custom_components.pawcontrol.language import normalize_language


def test_normalize_language_rejects_empty_default() -> None:
    """An empty default language is invalid."""
    with pytest.raises(ValueError, match="non-empty"):
        normalize_language("en", default="")


def test_normalize_language_uses_default_for_empty_input() -> None:
    """Missing language should return the provided default."""
    assert normalize_language(None, default="de") == "de"
    assert normalize_language("", default="de") == "de"


def test_normalize_language_normalizes_format_when_supported_is_omitted() -> None:
    """Underscores/casing should be normalized to lowercase primary language."""
    assert normalize_language("PT_BR") == "pt"
    assert normalize_language(" es-MX ") == "es"


def test_normalize_language_applies_supported_allowlist() -> None:
    """Unsupported values should fallback to the default language."""
    supported = {"en", "de", "fr"}
    assert normalize_language("de-DE", supported=supported, default="en") == "de"
    assert normalize_language("it", supported=supported, default="en") == "en"


def test_normalize_language_returns_default_when_normalized_value_is_blank() -> None:
    """Inputs that normalize to blank values should fallback to default."""
    assert normalize_language("___", default="en") == "en"
