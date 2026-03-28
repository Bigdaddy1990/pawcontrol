"""Tests for language normalization helpers."""

import pytest

from custom_components.pawcontrol.language import normalize_language


def test_normalize_language_uses_normalized_default_for_empty_language() -> None:
    """Falsy language values should fall back to normalized default."""
    assert normalize_language(None, default="DE_de") == "de"
    assert normalize_language("", default="fr-FR") == "fr"


def test_normalize_language_returns_normalized_language_without_supported_set() -> None:
    """Language values should normalize to base lowercase locale."""
    assert normalize_language("PT_br") == "pt"
    assert normalize_language(" En-US ") == "en"


def test_normalize_language_falls_back_for_whitespace_or_unknown_supported() -> None:
    """Unsupported/blank normalized languages should return normalized default."""
    supported = {"en", "de-DE", ""}

    assert normalize_language("   ", supported=supported, default="EN") == "en"
    assert normalize_language("fr", supported=supported, default="de") == "de"


def test_normalize_language_accepts_supported_normalized_language() -> None:
    """A supported normalized language should be returned as-is."""
    supported = {"en-US", "de", "fr_CA"}

    assert normalize_language("fr-FR", supported=supported, default="en") == "fr"


@pytest.mark.parametrize("default", ["", "   ", "__"])
def test_normalize_language_rejects_empty_default(default: str) -> None:
    """Default language must normalize to a non-empty language code."""
    with pytest.raises(ValueError, match="default language must be a non-empty string"):
        normalize_language("en", default=default)


def test_normalize_code_handles_none() -> None:
    """Internal normalization should treat None as an empty code."""
    from custom_components.pawcontrol.language import _normalize_code

    assert _normalize_code(None) == ""
