"""Unit tests for grooming translation helpers.

Validates that the grooming translation module correctly resolves label
and template keys, applies format values, and gracefully degrades to
default strings when no hass instance or cache lookup is available.
"""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.pawcontrol.grooming_translations import (
    GROOMING_LABEL_TRANSLATION_KEYS,
    GROOMING_TEMPLATE_TRANSLATION_KEYS,
    translated_grooming_label,
    translated_grooming_template,
)


@pytest.mark.unit
def test_translated_grooming_label_returns_key_when_unknown() -> None:
    """Unknown keys should be returned as-is without crashing."""
    result = translated_grooming_label(None, None, "nonexistent_key")
    assert result == "nonexistent_key"


@pytest.mark.unit
def test_translated_grooming_label_applies_format_values_for_unknown_key() -> None:
    """Unknown keys support format placeholders when values are provided."""
    result = translated_grooming_label(None, None, "hello {name}", name="World")
    assert result == "hello World"


@pytest.mark.unit
def test_translated_grooming_label_no_hass_returns_translation_key() -> None:
    """When hass is None the raw translation key is returned."""
    key = "button_action"
    result = translated_grooming_label(None, "en", key)
    expected_key = GROOMING_LABEL_TRANSLATION_KEYS[key]
    assert result == expected_key


@pytest.mark.unit
def test_translated_grooming_label_with_format_values_no_hass() -> None:
    """Format values are applied to translation keys even when hass is None."""
    key = "button_error"
    result = translated_grooming_label(None, "en", key, reason="timeout")
    # The translation key itself does not contain {reason}, so it is returned as-is
    assert result == GROOMING_LABEL_TRANSLATION_KEYS[key]


@pytest.mark.unit
def test_translated_grooming_label_with_hass_and_cache_hit() -> None:
    """With hass available the cache lookup path is exercised."""
    mock_hass = MagicMock()
    translation_key = GROOMING_LABEL_TRANSLATION_KEYS["button_action"]
    resolved = "Perform Grooming Action"

    with (
        patch(
            "custom_components.pawcontrol.grooming_translations.get_cached_component_translation_lookup",
            return_value=({"en": {translation_key: resolved}}, {}),
        ),
        patch(
            "custom_components.pawcontrol.grooming_translations.resolve_component_translation",
            return_value=resolved,
        ),
    ):
        result = translated_grooming_label(mock_hass, "en", "button_action")

    assert result == resolved


@pytest.mark.unit
def test_translated_grooming_label_with_hass_and_format_values() -> None:
    """Format values are applied to resolved translations."""
    mock_hass = MagicMock()
    translation_key = GROOMING_LABEL_TRANSLATION_KEYS["button_action"]
    resolved_template = "Action for {dog}"

    with (
        patch(
            "custom_components.pawcontrol.grooming_translations.get_cached_component_translation_lookup",
            return_value=({"en": {translation_key: resolved_template}}, {}),
        ),
        patch(
            "custom_components.pawcontrol.grooming_translations.resolve_component_translation",
            return_value=resolved_template,
        ),
    ):
        result = translated_grooming_label(mock_hass, "en", "button_action", dog="Buddy")

    assert result == "Action for Buddy"


@pytest.mark.unit
def test_translated_grooming_template_returns_formatted_key_for_unknown() -> None:
    """Unknown template keys are formatted with supplied values."""
    result = translated_grooming_template(None, None, "missing_{key}", key="test")
    assert result == "missing_test"


@pytest.mark.unit
def test_translated_grooming_template_no_hass_returns_translation_key() -> None:
    """Without hass, the mapped translation key is returned as template."""
    key = "helper_due"
    result = translated_grooming_template(None, "de", key)
    expected = GROOMING_TEMPLATE_TRANSLATION_KEYS[key]
    assert result == expected


@pytest.mark.unit
def test_translated_grooming_template_with_hass_resolved() -> None:
    """With hass the resolved template is returned and format applied."""
    mock_hass = MagicMock()
    translation_key = GROOMING_TEMPLATE_TRANSLATION_KEYS["notification_title"]
    resolved = "Grooming due for {dog}"

    with (
        patch(
            "custom_components.pawcontrol.grooming_translations.get_cached_component_translation_lookup",
            return_value=({translation_key: resolved}, {}),
        ),
        patch(
            "custom_components.pawcontrol.grooming_translations.resolve_component_translation",
            return_value=resolved,
        ),
    ):
        result = translated_grooming_template(
            mock_hass, "en", "notification_title", dog="Max"
        )

    assert result == "Grooming due for Max"


@pytest.mark.unit
def test_all_label_keys_are_mapped() -> None:
    """Every entry in GROOMING_LABEL_TRANSLATION_KEYS maps a non-empty string."""
    for key, value in GROOMING_LABEL_TRANSLATION_KEYS.items():
        assert isinstance(key, str) and key, f"Label key must be non-empty: {key!r}"
        assert isinstance(value, str) and value, (
            f"Label translation key for {key!r} must be non-empty"
        )


@pytest.mark.unit
def test_all_template_keys_are_mapped() -> None:
    """Every entry in GROOMING_TEMPLATE_TRANSLATION_KEYS maps a non-empty string."""
    for key, value in GROOMING_TEMPLATE_TRANSLATION_KEYS.items():
        assert isinstance(key, str) and key
        assert isinstance(value, str) and value
