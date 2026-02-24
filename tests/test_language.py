"""Tests for language normalization helpers."""

import pytest

from custom_components.pawcontrol.language import normalize_language


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (None, "en"),
        ("", "en"),
        ("de", "de"),
        ("PT_br", "pt"),
        (" fr-FR ", "fr"),
        ("___", "en"),
    ],
)
def test_normalize_language_without_supported(
    language: str | None,
    expected: str,
) -> None:
    """Normalize language values when no supported set is provided."""
    assert normalize_language(language) == expected


def test_normalize_language_supported_language_kept() -> None:
    """Supported normalized values should be returned unchanged."""
    assert normalize_language("DE_de", supported={"en", "de"}) == "de"


def test_normalize_language_unsupported_falls_back_to_default() -> None:
    """Unsupported languages should fall back to the configured default."""
    assert normalize_language("it", supported={"en", "de"}, default="de") == "de"


def test_normalize_language_rejects_empty_default() -> None:
    """An empty default language should raise a ValueError."""
    with pytest.raises(ValueError, match="default language"):
        normalize_language("en", default="")
