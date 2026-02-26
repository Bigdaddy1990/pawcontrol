"""Tests for weather translation helpers."""

from collections.abc import Mapping
from pathlib import Path
from unittest.mock import AsyncMock, patch

from custom_components.pawcontrol.weather_translations import (
    WEATHER_ALERT_KEYS,
    WEATHER_RECOMMENDATION_KEYS,
    async_get_weather_translations,
    empty_weather_translations,
    get_weather_translations,
)

HEAT_TITLE_KEY = "component.pawcontrol.common.weather_alert_extreme_heat_warning_title"
HEAT_MESSAGE_KEY = (
    "component.pawcontrol.common.weather_alert_extreme_heat_warning_message"
)
EXTRA_WATER_KEY = "component.pawcontrol.common.weather_recommendation_extra_water"


def test_empty_weather_translations_returns_empty_payload() -> None:
    """Empty helper should always return empty dictionaries."""
    assert empty_weather_translations() == {"alerts": {}, "recommendations": {}}


def test_get_weather_translations_uses_default_language_for_unknown_locale() -> None:
    """Unknown locales should fall back to the packaged English translations."""
    english = get_weather_translations("en")
    unknown = get_weather_translations("pt")

    assert unknown == english
    assert unknown["alerts"]["extreme_heat_warning"]["title"] == (
        "🔥 Extreme Heat Warning"
    )
    assert unknown["recommendations"]["extra_water"] == (
        "Provide extra water during outdoor activities"
    )


def test_get_weather_translations_contains_all_declared_keys() -> None:
    """Synchronous helper should include every alert/recommendation key."""
    translations = get_weather_translations("en")

    assert set(translations["alerts"]) == set(WEATHER_ALERT_KEYS)
    assert set(translations["recommendations"]) == set(WEATHER_RECOMMENDATION_KEYS)


def test_load_static_common_translations_returns_empty_when_files_are_missing() -> None:
    """Missing translation files should produce an empty common lookup."""
    with patch.object(Path, "exists", return_value=False):
        from custom_components.pawcontrol import weather_translations as module

        common = module._load_static_common_translations("fr")

    assert common == {}


def test_load_static_common_translations_handles_oserror() -> None:
    """File read errors should be swallowed and treated as missing translations."""
    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "read_text", side_effect=OSError),
    ):
        from custom_components.pawcontrol import weather_translations as module

        common = module._load_static_common_translations("fr")

    assert common == {}


def test_load_static_common_translations_handles_invalid_json() -> None:
    """Invalid translation JSON should fall back to an empty payload."""
    with (
        patch.object(Path, "exists", return_value=True),
        patch.object(Path, "read_text", return_value="{"),
    ):
        from custom_components.pawcontrol import weather_translations as module

        common = module._load_static_common_translations("fr")

    assert common == {}


async def test_async_get_weather_translations_prefers_requested_then_fallback() -> None:
    """Async translation helper should merge requested and fallback lookups."""
    requested: Mapping[str, str] = {
        HEAT_TITLE_KEY: "Localized title",
        EXTRA_WATER_KEY: "Localized recommendation",
    }
    fallback: Mapping[str, str] = {HEAT_MESSAGE_KEY: "Fallback message"}

    with patch(
        "custom_components.pawcontrol.weather_translations"
        ".async_get_component_translation_lookup",
        AsyncMock(return_value=(requested, fallback)),
    ):
        translations = await async_get_weather_translations(
            hass=object(),
            language="fr",
        )

    assert translations["alerts"]["extreme_heat_warning"]["title"] == "Localized title"
    assert (
        translations["alerts"]["extreme_heat_warning"]["message"] == "Fallback message"
    )
    assert translations["recommendations"]["extra_water"] == "Localized recommendation"
    assert translations["alerts"]["storm_warning"]["title"] == "storm_warning"
