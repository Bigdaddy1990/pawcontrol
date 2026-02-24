"""Tests for weather translation helpers."""

from collections.abc import Mapping
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
