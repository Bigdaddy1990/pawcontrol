"""Additional coverage tests for grooming translation helpers."""

from types import SimpleNamespace

from custom_components.pawcontrol import grooming_translations


def test_translated_grooming_label_unknown_key_formats_values() -> None:
    """Unknown label keys should format using provided values."""
    result = grooming_translations.translated_grooming_label(
        None,
        "en",
        "Hello {name}",
        name="Milo",
    )

    assert result == "Hello Milo"


def test_translated_grooming_label_uses_component_lookup_when_hass_available(
    monkeypatch,
) -> None:
    """Known keys should resolve via translation lookup when hass is present."""
    hass = SimpleNamespace()

    monkeypatch.setattr(
        grooming_translations,
        "get_cached_component_translation_lookup",
        lambda _hass, _language: ({"grooming_label_button_action": "Aktivieren"}, {}),
    )
    monkeypatch.setattr(
        grooming_translations,
        "resolve_component_translation",
        lambda translations, _fallback, key, default: translations.get(key, default),
    )

    result = grooming_translations.translated_grooming_label(
        hass,
        "de",
        "button_action",
    )

    assert result == "Aktivieren"


def test_translated_grooming_template_unknown_key_formats_values() -> None:
    """Unknown template keys should still be format-capable."""
    result = grooming_translations.translated_grooming_template(
        None,
        "en",
        "Reminder for {dog}",
        dog="Luna",
    )

    assert result == "Reminder for Luna"


def test_translated_grooming_template_with_hass_uses_fallback_default(
    monkeypatch,
) -> None:
    """Template translations should fall back to provided key when unresolved."""
    hass = SimpleNamespace()

    monkeypatch.setattr(
        grooming_translations,
        "get_cached_component_translation_lookup",
        lambda _hass, _language: ({}, {}),
    )

    captured: dict[str, object] = {}

    def _resolve(translations, fallback, key, default) -> str:
        captured["inputs"] = (translations, fallback, key, default)
        return "Template {dog}"

    monkeypatch.setattr(
        grooming_translations, "resolve_component_translation", _resolve
    )

    result = grooming_translations.translated_grooming_template(
        hass,
        "en",
        "notification_message",
        dog="Bello",
    )

    assert result == "Template Bello"
    assert captured["inputs"] == (
        {},
        {},
        "grooming_template_notification_message",
        "notification_message",
    )
