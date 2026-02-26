"""Unit tests for language normalization helpers."""

import pytest

from custom_components.pawcontrol.language import normalize_language


def test_normalize_language_uses_default_for_missing_language() -> None:
    """None and empty values should resolve to the configured default."""
    assert normalize_language(None) == "en"
    assert normalize_language("") == "en"


def test_normalize_language_normalizes_delimiters_and_case() -> None:
    """Regional variants should collapse to lower-case base language codes."""
    assert normalize_language("DE_de") == "de"
    assert normalize_language("  fr-CA  ") == "fr"


def test_normalize_language_returns_default_for_empty_normalized_value() -> None:
    """Whitespace-only values should fall back to the default language."""
    assert normalize_language("   ") == "en"


def test_normalize_language_honors_supported_languages() -> None:
    """Unsupported languages should fall back when supported values are provided."""
    supported = {"en", "de"}

    assert normalize_language("de-DE", supported=supported) == "de"
    assert normalize_language("fr-FR", supported=supported) == "en"


def test_normalize_language_requires_non_empty_default() -> None:
    """An empty default should fail fast with a clear exception."""
    with pytest.raises(ValueError, match="default language must be a non-empty"):
        normalize_language("de", default="")


def test_normalize_language_rejects_whitespace_only_default() -> None:
    """Whitespace-only defaults should fail fast like other empty defaults."""
    with pytest.raises(ValueError, match="default language must be a non-empty"):
        normalize_language(None, default="   ")
