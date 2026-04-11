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


def test_normalize_language_ignores_blank_supported_entries() -> None:
    """Blank supported codes should be discarded after normalization."""
    supported = {"EN_us", " _ ", "de-DE"}

    assert normalize_language("en-GB", supported=supported, default="fr") == "en"
    assert normalize_language("it", supported=supported, default="fr") == "fr"


def test_normalize_language_accepts_values_when_supported_missing() -> None:
    """Without a supported set, normalized values should pass through."""
    assert normalize_language("  ES-mx  ", supported=None, default="en") == "es"


def test_normalize_language_rejects_language_not_in_normalized_supported_set() -> None:
    """Normalized supported values should enforce the fallback when unmatched."""
    supported = {" _ ", "DE_de"}

    assert normalize_language("pt-BR", supported=supported, default="en-US") == "en"


def test_normalize_language_handles_none_entries_inside_supported_collection() -> None:
    """Non-string supported entries that normalize empty should be ignored."""
    supported: set[str | None] = {None, "fr-FR"}

    assert normalize_language("fr-CA", supported=supported, default="en") == "fr"
