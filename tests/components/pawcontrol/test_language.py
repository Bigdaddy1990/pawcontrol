"""Tests for language normalization helpers."""

from __future__ import annotations

import pytest

from custom_components.pawcontrol.language import normalize_language


def test_normalize_language_raises_for_empty_default() -> None:
    """An empty default language should be rejected."""
    with pytest.raises(ValueError, match="default language must be a non-empty string"):
        normalize_language("de", default="")


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
