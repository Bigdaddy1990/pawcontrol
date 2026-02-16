"""Tests for weather translation resolution and fallbacks."""

from __future__ import annotations

from typing import cast
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
import pytest
from tests.weather_test_support import ensure_weather_module_compat

ensure_weather_module_compat()

from custom_components.pawcontrol.weather_manager import (
  AlertTranslationParts,
  WeatherHealthManager,
  WeatherTranslationParts,
)
from custom_components.pawcontrol.weather_translations import (
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  WEATHER_ALERT_KEY_SET,
  WEATHER_RECOMMENDATION_KEY_SET,
  get_weather_translations,
)


@pytest.fixture
def weather_manager() -> WeatherHealthManager:
  """Create a weather manager with deterministic translations."""  # noqa: E111

  manager = WeatherHealthManager(MagicMock(spec=HomeAssistant))  # noqa: E111
  manager._english_translations = get_weather_translations(DEFAULT_LANGUAGE)  # noqa: E111
  return manager  # noqa: E111


def test_get_translation_returns_localized_text(
  weather_manager: WeatherHealthManager,
) -> None:
  """Localized translations should resolve from the active catalog."""  # noqa: E111

  weather_manager._translations = get_weather_translations("de")  # noqa: E111

  title = weather_manager._get_translation(  # noqa: E111
    "weather.alerts.extreme_heat_warning.title",
  )
  message = weather_manager._get_translation(  # noqa: E111
    "weather.alerts.extreme_heat_warning.message",
    temperature=32,
    feels_like=35,
  )

  assert title == "🔥 Warnung vor extremer Hitze"  # noqa: E111
  assert "Temperatur 32°C" in message  # noqa: E111
  assert "gefühlte 35°C" in message  # noqa: E111


def test_get_translation_uses_english_fallback_when_missing_local_entry(
  weather_manager: WeatherHealthManager,
) -> None:
  """Missing localized entries should fall back to the English catalog."""  # noqa: E111

  translations = get_weather_translations("de")  # noqa: E111
  translations["alerts"].pop("extreme_heat_warning")  # noqa: E111
  weather_manager._translations = translations  # noqa: E111

  fallback = weather_manager._get_translation(  # noqa: E111
    "weather.alerts.extreme_heat_warning.title",
  )

  assert fallback == "🔥 Extreme Heat Warning"  # noqa: E111


def test_get_translation_returns_original_key_when_fallback_missing(
  weather_manager: WeatherHealthManager,
) -> None:
  """If neither catalog has a key the original dotted key should be returned."""  # noqa: E111

  weather_manager._translations = get_weather_translations("de")  # noqa: E111

  result = weather_manager._get_translation("weather.alerts.unknown.key")  # noqa: E111

  assert result == "weather.alerts.unknown.key"  # noqa: E111


def test_get_translation_handles_format_errors_in_fallback(
  weather_manager: WeatherHealthManager,
) -> None:
  """Fallback formatting errors should yield the template text without substitution."""  # noqa: E111

  translations = get_weather_translations("de")  # noqa: E111
  translations["alerts"].pop("extreme_heat_warning")  # noqa: E111
  weather_manager._translations = translations  # noqa: E111

  template = weather_manager._get_translation(  # noqa: E111
    "weather.alerts.extreme_heat_warning.message",
    temperature=30,
  )

  assert template.startswith("Temperature {temperature}°C")  # noqa: E111
  assert "{feels_like}" in template  # noqa: E111


def test_get_translation_handles_non_string_local_entries(
  weather_manager: WeatherHealthManager,
) -> None:
  """Mappings at localized leaves should fall back to English strings."""  # noqa: E111

  translations = get_weather_translations("de")  # noqa: E111
  cast(dict[str, object], translations["alerts"]["extreme_heat_warning"])["title"] = {  # noqa: E111
    "value": "mapping"
  }
  weather_manager._translations = translations  # noqa: E111

  fallback = weather_manager._get_translation(  # noqa: E111
    "weather.alerts.extreme_heat_warning.title",
  )

  assert fallback == "🔥 Extreme Heat Warning"  # noqa: E111


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
  """The resolver should return strings or None for missing leaves."""  # noqa: E111

  catalog = get_weather_translations(DEFAULT_LANGUAGE)  # noqa: E111

  assert WeatherHealthManager._resolve_translation_value(catalog, parts) == expected  # noqa: E111


def test_resolve_translation_value_returns_none_for_missing_alert() -> None:
  """Missing alert entries should return None to trigger fallbacks."""  # noqa: E111

  catalog = get_weather_translations(DEFAULT_LANGUAGE)  # noqa: E111
  catalog["alerts"].pop("extreme_heat_warning")  # noqa: E111

  parts: AlertTranslationParts = (  # noqa: E111
    "alerts",
    "extreme_heat_warning",
    "title",
  )

  assert WeatherHealthManager._resolve_translation_value(catalog, parts) is None  # noqa: E111


@pytest.mark.parametrize(
  "key",
  [
    "weather.alerts",
    "weather.alerts.extreme_heat_warning.title.extra",
    "weather.unknown.section",
  ],
)
def test_parse_translation_key_rejects_invalid_paths(key: str) -> None:
  """Invalid keys should return None so callers can fall back."""  # noqa: E111

  assert WeatherHealthManager._parse_translation_key(key) is None  # noqa: E111


def test_parse_translation_key_allows_weather_prefix() -> None:
  """Keys with the leading weather prefix should parse correctly."""  # noqa: E111

  parts = WeatherHealthManager._parse_translation_key(  # noqa: E111
    "weather.alerts.extreme_heat_warning.title"
  )

  assert parts == ("alerts", "extreme_heat_warning", "title")  # noqa: E111


def test_resolve_translation_value_rejects_unknown_section() -> None:
  """Unknown sections must raise ValueError for guard-rails."""  # noqa: E111

  catalog = get_weather_translations(DEFAULT_LANGUAGE)  # noqa: E111

  with pytest.raises(ValueError):  # noqa: E111
    WeatherHealthManager._resolve_translation_value(
      catalog, cast(WeatherTranslationParts, ("unknown",))
    )


def test_translation_catalog_keys_match_literal_definitions() -> None:
  """Every catalog must provide entries for all declared translation keys."""  # noqa: E111

  for language in SUPPORTED_LANGUAGES:  # noqa: E111
    catalog = get_weather_translations(language)

    assert frozenset(catalog["alerts"]) == WEATHER_ALERT_KEY_SET
    assert frozenset(catalog["recommendations"]) == WEATHER_RECOMMENDATION_KEY_SET

    for translation in catalog["alerts"].values():
      assert isinstance(translation["title"], str)  # noqa: E111
      assert isinstance(translation["message"], str)  # noqa: E111

    for recommendation in catalog["recommendations"].values():
      assert isinstance(recommendation, str)  # noqa: E111
