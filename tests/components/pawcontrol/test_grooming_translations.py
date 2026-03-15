"""Tests for grooming translation helpers."""

from types import SimpleNamespace

from custom_components.pawcontrol import grooming_translations


def test_translated_grooming_label_returns_key_for_unknown_label() -> None:
    """Unknown labels should return the provided key verbatim."""
    assert (
        grooming_translations.translated_grooming_label(
            hass=None,
            language="en",
            key="custom_label",
        )
        == "custom_label"
    )


def test_translated_grooming_label_formats_unknown_label_values() -> None:
    """Unknown labels should still apply template value formatting."""
    assert (
        grooming_translations.translated_grooming_label(
            hass=None,
            language="en",
            key="next session for {dog_name}",
            dog_name="Rex",
        )
        == "next session for Rex"
    )


def test_translated_grooming_label_uses_translation_key_without_hass() -> None:
    """When hass is missing, helpers should expose the translation key token."""
    assert (
        grooming_translations.translated_grooming_label(
            hass=None,
            language="en",
            key="module_summary_label",
        )
        == "grooming_label_module_summary_label"
    )


def test_translated_grooming_label_resolves_cached_translations(
    monkeypatch,
) -> None:
    """Helpers should resolve and format translated labels when hass is available."""
    hass = SimpleNamespace()

    monkeypatch.setattr(
        grooming_translations,
        "get_cached_component_translation_lookup",
        lambda _hass, _language: (
            {"grooming_label_button_notes": "Notes for {dog_name}"},
            {},
        ),
    )

    monkeypatch.setattr(
        grooming_translations,
        "resolve_component_translation",
        lambda translations, _fallback, key, default: translations.get(key, default),
    )

    assert (
        grooming_translations.translated_grooming_label(
            hass=hass,
            language="de",
            key="button_notes",
            dog_name="Luna",
        )
        == "Notes for Luna"
    )


def test_translated_grooming_template_handles_known_and_unknown_keys(
    monkeypatch,
) -> None:
    """Template helper should format fallback strings and translated templates."""
    hass = SimpleNamespace()

    monkeypatch.setattr(
        grooming_translations,
        "get_cached_component_translation_lookup",
        lambda _hass, _language: (
            {
                "grooming_template_notification_title": "Grooming for {dog_name}",
            },
            {},
        ),
    )

    monkeypatch.setattr(
        grooming_translations,
        "resolve_component_translation",
        lambda translations, _fallback, key, default: translations.get(key, default),
    )

    assert (
        grooming_translations.translated_grooming_template(
            hass=hass,
            language="fr",
            template_key="notification_title",
            dog_name="Milo",
        )
        == "Grooming for Milo"
    )

    assert (
        grooming_translations.translated_grooming_template(
            hass=hass,
            language="fr",
            template_key="unknown template for {dog_name}",
            dog_name="Milo",
        )
        == "unknown template for Milo"
    )


def test_translated_grooming_template_uses_token_without_hass() -> None:
    """Known template keys should fall back to translation tokens without hass."""
    assert (
        grooming_translations.translated_grooming_template(
            hass=None,
            language="en",
            template_key="start_failure",
            reason="timeout",
        )
        == "grooming_template_start_failure"
    )
