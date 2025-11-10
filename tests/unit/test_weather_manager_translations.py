"""Tests for weather translation resolution and fallbacks."""

from __future__ import annotations

from enum import Enum
from typing import cast
from unittest.mock import MagicMock

import homeassistant.components.weather as weather_module
import homeassistant.const as ha_const
import pytest
from homeassistant.core import HomeAssistant

_MISSING_WEATHER_ATTRS: dict[str, str] = {
    "DOMAIN": "weather",
    "ATTR_FORECAST": "forecast",
    "ATTR_FORECAST_CONDITION": "condition",
    "ATTR_FORECAST_HUMIDITY": "humidity",
    "ATTR_FORECAST_PRECIPITATION": "precipitation",
    "ATTR_FORECAST_PRECIPITATION_PROBABILITY": "precipitation_probability",
    "ATTR_FORECAST_PRESSURE": "pressure",
    "ATTR_FORECAST_TEMP": "temperature",
    "ATTR_FORECAST_TEMP_LOW": "templow",
    "ATTR_FORECAST_TIME": "datetime",
    "ATTR_FORECAST_UV_INDEX": "uv_index",
    "ATTR_FORECAST_WIND_SPEED": "wind_speed",
    "ATTR_WEATHER_HUMIDITY": "humidity",
    "ATTR_WEATHER_PRESSURE": "pressure",
    "ATTR_WEATHER_TEMPERATURE": "temperature",
    "ATTR_WEATHER_UV_INDEX": "uv_index",
    "ATTR_WEATHER_VISIBILITY": "visibility",
    "ATTR_WEATHER_WIND_SPEED": "wind_speed",
}

for attr, value in _MISSING_WEATHER_ATTRS.items():
    if not hasattr(weather_module, attr):
        setattr(weather_module, attr, value)

if not hasattr(ha_const, "UnitOfTemperature"):

    class UnitOfTemperature(str, Enum):
        CELSIUS = "°C"
        FAHRENHEIT = "°F"

    ha_const.UnitOfTemperature = UnitOfTemperature

from custom_components.pawcontrol.weather_manager import (
    AlertTranslationParts,
    WeatherHealthManager,
    WeatherTranslationParts,
)
from custom_components.pawcontrol.weather_translations import (
    DEFAULT_LANGUAGE,
    get_weather_translations,
)


@pytest.fixture
def weather_manager() -> WeatherHealthManager:
    """Create a weather manager with deterministic translations."""

    manager = WeatherHealthManager(MagicMock(spec=HomeAssistant))
    manager._english_translations = get_weather_translations(DEFAULT_LANGUAGE)
    return manager


def test_get_translation_returns_localized_text(
    weather_manager: WeatherHealthManager,
) -> None:
    """Localized translations should resolve from the active catalog."""

    weather_manager._translations = get_weather_translations("de")

    title = weather_manager._get_translation(
        "weather.alerts.extreme_heat_warning.title",
    )
    message = weather_manager._get_translation(
        "weather.alerts.extreme_heat_warning.message",
        temperature=32,
        feels_like=35,
    )

    assert title == "🔥 Warnung vor extremer Hitze"
    assert "Temperatur 32°C" in message
    assert "gefühlte 35°C" in message


def test_get_translation_uses_english_fallback_when_missing_local_entry(
    weather_manager: WeatherHealthManager,
) -> None:
    """Missing localized entries should fall back to the English catalog."""

    translations = get_weather_translations("de")
    translations["alerts"].pop("extreme_heat_warning")
    weather_manager._translations = translations

    fallback = weather_manager._get_translation(
        "weather.alerts.extreme_heat_warning.title",
    )

    assert fallback == "🔥 Extreme Heat Warning"


def test_get_translation_returns_original_key_when_fallback_missing(
    weather_manager: WeatherHealthManager,
) -> None:
    """If neither catalog has a key the original dotted key should be returned."""

    weather_manager._translations = get_weather_translations("de")

    result = weather_manager._get_translation("weather.alerts.unknown.key")

    assert result == "weather.alerts.unknown.key"


def test_get_translation_handles_format_errors_in_fallback(
    weather_manager: WeatherHealthManager,
) -> None:
    """Fallback formatting errors should yield the template text without substitution."""

    translations = get_weather_translations("de")
    translations["alerts"].pop("extreme_heat_warning")
    weather_manager._translations = translations

    template = weather_manager._get_translation(
        "weather.alerts.extreme_heat_warning.message",
        temperature=30,
    )

    assert template.startswith("Temperature {temperature}°C")
    assert "{feels_like}" in template


def test_get_translation_handles_non_string_local_entries(
    weather_manager: WeatherHealthManager,
) -> None:
    """Mappings at localized leaves should fall back to English strings."""

    translations = get_weather_translations("de")
    cast(dict[str, object], translations["alerts"]["extreme_heat_warning"])["title"] = {
        "value": "mapping"
    }
    weather_manager._translations = translations

    fallback = weather_manager._get_translation(
        "weather.alerts.extreme_heat_warning.title",
    )

    assert fallback == "🔥 Extreme Heat Warning"


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (
            ("alerts", "extreme_heat_warning", "title"),
            "🔥 Extreme Heat Warning",
        ),
        (
            ("recommendations", "provide_water"),
            "Provide constant access to cool water",
        ),
    ],
)
def test_resolve_translation_value_retrieves_values(
    parts: WeatherTranslationParts, expected: str | None
) -> None:
    """The resolver should return strings or None for missing leaves."""

    catalog = get_weather_translations(DEFAULT_LANGUAGE)

    assert WeatherHealthManager._resolve_translation_value(catalog, parts) == expected


def test_resolve_translation_value_returns_none_for_missing_alert() -> None:
    """Missing alert entries should return None to trigger fallbacks."""

    catalog = get_weather_translations(DEFAULT_LANGUAGE)
    catalog["alerts"].pop("extreme_heat_warning")

    parts: AlertTranslationParts = (
        "alerts",
        "extreme_heat_warning",
        "title",
    )

    assert WeatherHealthManager._resolve_translation_value(catalog, parts) is None


@pytest.mark.parametrize(
    "key",
    [
        "weather.alerts",
        "weather.alerts.extreme_heat_warning.title.extra",
        "weather.unknown.section",
    ],
)
def test_parse_translation_key_rejects_invalid_paths(key: str) -> None:
    """Invalid keys should return None so callers can fall back."""

    assert WeatherHealthManager._parse_translation_key(key) is None


def test_parse_translation_key_allows_weather_prefix() -> None:
    """Keys with the leading weather prefix should parse correctly."""

    parts = WeatherHealthManager._parse_translation_key(
        "weather.alerts.extreme_heat_warning.title"
    )

    assert parts == ("alerts", "extreme_heat_warning", "title")


def test_resolve_translation_value_rejects_unknown_section() -> None:
    """Unknown sections must raise ValueError for guard-rails."""

    catalog = get_weather_translations(DEFAULT_LANGUAGE)

    with pytest.raises(ValueError):
        WeatherHealthManager._resolve_translation_value(
            catalog, cast(WeatherTranslationParts, ("unknown",))
        )
