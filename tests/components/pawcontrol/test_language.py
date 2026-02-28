"""Tests for language normalization helpers."""

import pytest

from custom_components.pawcontrol.language import normalize_language


def test_normalize_language_raises_for_empty_default() -> None:
    """An empty default language should be rejected."""
    with pytest.raises(ValueError, match="default language must be a non-empty string"):
        normalize_language("de", default="")


def test_normalize_language_raises_for_default_that_normalizes_empty() -> None:
    """Defaults that collapse to empty values should be rejected."""
    with pytest.raises(ValueError, match="default language must be a non-empty string"):
        normalize_language("de", default=" _ ")


def test_normalize_language_handles_none_value() -> None:
    """A ``None`` language should resolve to the normalized default."""
    assert normalize_language(None, default="EN_us") == "en"


def test_normalize_code_returns_empty_for_none() -> None:
    """Internal normalization should gracefully handle ``None`` values."""
    from custom_components.pawcontrol.language import _normalize_code

    assert _normalize_code(None) == ""


def test_normalize_language_uses_default_when_language_missing() -> None:
    """Missing language values should return the configured default."""
    assert normalize_language(None, default="de") == "de"
    assert normalize_language("", default="de") == "de"


def test_normalize_language_normalizes_variant_to_base_code() -> None:
    """Language codes should normalize separators/casing and drop region variants."""
    assert normalize_language("EN_us") == "en"
    assert normalize_language(" pt-BR ") == "pt"


def test_normalize_language_uses_default_for_empty_normalized_value() -> None:
    """Values that normalize to empty strings should use the default."""
    assert normalize_language(" _ ", default="fr") == "fr"


def test_normalize_language_respects_supported_collection() -> None:
    """Supported language lists should gate normalized results."""
    supported = {"en", "de"}

    assert normalize_language("de-AT", supported=supported, default="en") == "de"
    assert normalize_language("fr", supported=supported, default="en") == "en"
