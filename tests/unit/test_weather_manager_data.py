"""Tests for weather data ingestion and fallback behaviour.

Quality Scale: Platinum target
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import cast

import homeassistant.components.weather as weather_module
import homeassistant.const as ha_const
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests.weather_test_support import ensure_weather_module_compat

from custom_components.pawcontrol import weather_translations
from custom_components.pawcontrol.const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOGS,
  CONF_WEATHER_ENTITY,
  DOMAIN,
)
from custom_components.pawcontrol.module_adapters import WeatherModuleAdapter
from custom_components.pawcontrol.types import PawControlConfigEntry
from custom_components.pawcontrol.weather_translations import WeatherTranslations

UnitOfTemperature = ensure_weather_module_compat()
STATE_UNAVAILABLE = ha_const.STATE_UNAVAILABLE

from custom_components.pawcontrol.weather_manager import (
  WeatherHealthImpact,
  WeatherHealthManager,
  WeatherSeverity,
)


@pytest.fixture
def weather_manager(hass: HomeAssistant) -> WeatherHealthManager:
  """Return a fresh weather health manager for each test."""  # noqa: E111

  manager = WeatherHealthManager(hass)  # noqa: E111
  asyncio.run(manager.async_load_translations())  # noqa: E111
  return manager  # noqa: E111


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
  """Return a config entry populated with a single dog profile."""  # noqa: E111

  entry = MockConfigEntry(  # noqa: E111
    domain=DOMAIN,
    data={
      CONF_DOGS: [
        {
          CONF_DOG_ID: "test_dog",
          CONF_DOG_BREED: "labrador_retriever",
          CONF_DOG_AGE: 72,
          "health_conditions": ["arthritis"],
        }
      ]
    },
    options={},
    unique_id="pawcontrol-test",
  )
  entry.add_to_hass(hass)  # noqa: E111
  return entry  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_converts_units_and_builds_alerts(
  hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
  """High heat and humidity should produce alerts and derived metrics."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "weather.backyard",
    "sunny",
    {
      weather_module.ATTR_WEATHER_TEMPERATURE: 98.0,
      "temperature_unit": UnitOfTemperature.FAHRENHEIT,
      weather_module.ATTR_WEATHER_HUMIDITY: 80,
      weather_module.ATTR_WEATHER_UV_INDEX: 9,
      weather_module.ATTR_WEATHER_WIND_SPEED: 12.0,
      weather_module.ATTR_WEATHER_VISIBILITY: 16.0,
    },
  )

  conditions = await weather_manager.async_update_weather_data("weather.backyard")  # noqa: E111

  assert conditions is not None  # noqa: E111
  assert conditions.source_entity == "weather.backyard"  # noqa: E111
  assert conditions.temperature_c is not None  # noqa: E111
  assert conditions.temperature_c == pytest.approx((98.0 - 32.0) * 5 / 9)  # noqa: E111
  assert conditions.heat_index is not None  # noqa: E111
  assert conditions.heat_index > conditions.temperature_c  # noqa: E111

  alerts = weather_manager.get_active_alerts()  # noqa: E111
  assert alerts  # Heat stress alert should be registered  # noqa: E111
  assert any(alert.alert_type == WeatherHealthImpact.HEAT_STRESS for alert in alerts)  # noqa: E111
  assert weather_manager.get_weather_health_score() < 60  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_missing_temperature_uses_fallbacks(
  hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
  """Missing temperature should skip alerts and fall back to default score."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "weather.lawn",
    "cloudy",
    {
      weather_module.ATTR_WEATHER_HUMIDITY: 55,
      weather_module.ATTR_WEATHER_UV_INDEX: 2,
      weather_module.ATTR_WEATHER_WIND_SPEED: 5.0,
      weather_module.ATTR_WEATHER_VISIBILITY: 10.0,
    },
  )

  conditions = await weather_manager.async_update_weather_data("weather.lawn")  # noqa: E111

  assert conditions is not None  # noqa: E111
  assert conditions.temperature_c is None  # noqa: E111
  assert weather_manager.get_weather_health_score() == 50  # noqa: E111
  assert weather_manager.get_active_alerts() == []  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_preserves_previous_conditions_when_unavailable(
  hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
  """Unavailable states should leave the last good snapshot untouched."""  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "weather.rooftop",
    "sunny",
    {
      weather_module.ATTR_WEATHER_TEMPERATURE: 24.0,
      weather_module.ATTR_WEATHER_HUMIDITY: 40,
      weather_module.ATTR_WEATHER_UV_INDEX: 4,
      weather_module.ATTR_WEATHER_WIND_SPEED: 8.0,
      weather_module.ATTR_WEATHER_VISIBILITY: 20.0,
    },
  )
  initial = await weather_manager.async_update_weather_data("weather.rooftop")  # noqa: E111
  assert initial is not None  # noqa: E111

  hass.states.async_set("weather.rooftop", STATE_UNAVAILABLE, {})  # noqa: E111
  updated = await weather_manager.async_update_weather_data("weather.rooftop")  # noqa: E111

  assert updated is None  # noqa: E111
  cached = weather_manager.get_current_conditions()  # noqa: E111
  assert cached is initial  # noqa: E111
  assert cached is not None  # noqa: E111
  assert cached.temperature_c == pytest.approx(24.0)  # noqa: E111
  assert weather_manager.get_weather_health_score() > 60  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_missing_translation_falls_back_to_english(
  hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Broken locale entries should fall back to English strings."""  # noqa: E111

  original_get = weather_translations.get_weather_translations  # noqa: E111

  def _broken_get_weather_translations(language: str) -> WeatherTranslations:  # noqa: E111
    catalog = original_get(language)
    if language == "de":
      catalog["alerts"].pop("extreme_heat_warning", None)  # noqa: E111
    return catalog

  monkeypatch.setattr(  # noqa: E111
    weather_translations,
    "get_weather_translations",
    _broken_get_weather_translations,
    raising=True,
  )
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.weather_manager.get_weather_translations",
    _broken_get_weather_translations,
    raising=True,
  )

  manager = WeatherHealthManager(hass)  # noqa: E111
  await manager.async_load_translations("de")  # noqa: E111
  assert "extreme_heat_warning" not in manager._translations["alerts"]  # noqa: E111
  assert (  # noqa: E111
    manager._english_translations["alerts"]["extreme_heat_warning"]["title"]
    == "🔥 Extreme Heat Warning"
  )

  hass.states.async_set(  # noqa: E111
    "weather.terrace",
    "sunny",
    {
      weather_module.ATTR_WEATHER_TEMPERATURE: 100.0,
      "temperature_unit": UnitOfTemperature.FAHRENHEIT,
      weather_module.ATTR_WEATHER_HUMIDITY: 85,
      weather_module.ATTR_WEATHER_UV_INDEX: 9,
    },
  )

  conditions = await manager.async_update_weather_data("weather.terrace")  # noqa: E111

  assert conditions is not None  # noqa: E111
  alerts = manager.get_active_alerts()  # noqa: E111
  assert alerts  # noqa: E111
  assert any(alert.title == "🔥 Extreme Heat Warning" for alert in alerts)  # noqa: E111
  assert any("Temperature" in alert.message for alert in alerts)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_handles_formatting_errors_in_translations(
  hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
  """Locale formatting errors should not break alert generation."""  # noqa: E111

  original_get = weather_translations.get_weather_translations  # noqa: E111

  def _formatting_error_translations(language: str) -> WeatherTranslations:  # noqa: E111
    catalog = original_get(language)
    if language == "de":
      german_alerts = catalog["alerts"].get("high_heat_advisory")  # noqa: E111
      if german_alerts:  # noqa: E111
        german_alerts["message"] = (
          "Temperatur {temperature}°C und {missing_placeholder} erfordern Schutz"
        )
    return catalog

  monkeypatch.setattr(  # noqa: E111
    weather_translations,
    "get_weather_translations",
    _formatting_error_translations,
    raising=True,
  )
  monkeypatch.setattr(  # noqa: E111
    "custom_components.pawcontrol.weather_manager.get_weather_translations",
    _formatting_error_translations,
    raising=True,
  )

  manager = WeatherHealthManager(hass)  # noqa: E111
  await manager.async_load_translations("de")  # noqa: E111

  hass.states.async_set(  # noqa: E111
    "weather.deck",
    "sunny",
    {
      weather_module.ATTR_WEATHER_TEMPERATURE: 32.0,
      weather_module.ATTR_WEATHER_HUMIDITY: 70,
      weather_module.ATTR_WEATHER_UV_INDEX: 7,
    },
  )

  conditions = await manager.async_update_weather_data("weather.deck")  # noqa: E111

  assert conditions is not None  # noqa: E111
  alerts = manager.get_active_alerts()  # noqa: E111
  assert alerts  # noqa: E111
  advisory = next(  # noqa: E111
    alert
    for alert in alerts
    if (
      alert.alert_type == WeatherHealthImpact.HEAT_STRESS
      and alert.severity == WeatherSeverity.HIGH
    )
  )
  assert advisory.message == "Temperature 32.0°C requires heat precautions for dogs"  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_returns_disabled_without_manager(
  config_entry: MockConfigEntry,
) -> None:
  """Adapters should surface a disabled status when no manager is attached."""  # noqa: E111

  adapter = WeatherModuleAdapter(  # noqa: E111
    config_entry=cast(PawControlConfigEntry, config_entry),
    ttl=timedelta(seconds=0),
  )

  payload = await adapter.async_get_data("test_dog")  # noqa: E111

  assert payload["status"] == "disabled"  # noqa: E111
  assert payload["alerts"] == []  # noqa: E111
  assert payload["recommendations"] == []  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_exposes_fallback_health_score(
  hass: HomeAssistant,
  config_entry: MockConfigEntry,
  weather_manager: WeatherHealthManager,
) -> None:
  """When no conditions exist the adapter should return fallback scores."""  # noqa: E111

  adapter = WeatherModuleAdapter(  # noqa: E111
    config_entry=cast(PawControlConfigEntry, config_entry),
    ttl=timedelta(seconds=0),
  )
  adapter.attach(weather_manager)  # noqa: E111

  payload = await adapter.async_get_data("test_dog")  # noqa: E111

  assert payload["status"] == "ready"  # noqa: E111
  assert payload["health_score"] == 50  # noqa: E111
  assert payload["alerts"] == []  # noqa: E111
  assert payload["recommendations"] == [  # noqa: E111
    "Weather conditions are suitable for normal activities"
  ]
  assert "conditions" not in payload  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_includes_conditions_when_available(
  hass: HomeAssistant,
  config_entry: MockConfigEntry,
  weather_manager: WeatherHealthManager,
) -> None:
  """Adapters should embed the active conditions snapshot when present."""  # noqa: E111

  config_entry.options = {CONF_WEATHER_ENTITY: "weather.home"}  # noqa: E111
  hass.states.async_set(  # noqa: E111
    "weather.home",
    "sunny",
    {
      weather_module.ATTR_WEATHER_TEMPERATURE: 30.0,
      weather_module.ATTR_WEATHER_HUMIDITY: 50,
      weather_module.ATTR_WEATHER_UV_INDEX: 6,
      weather_module.ATTR_WEATHER_WIND_SPEED: 10.0,
      weather_module.ATTR_WEATHER_VISIBILITY: 18.0,
      weather_module.ATTR_FORECAST: [],
    },
  )

  adapter = WeatherModuleAdapter(  # noqa: E111
    config_entry=cast(PawControlConfigEntry, config_entry),
    ttl=timedelta(seconds=0),
  )
  adapter.attach(weather_manager)  # noqa: E111

  payload = await adapter.async_get_data("test_dog")  # noqa: E111

  assert payload["status"] == "ready"  # noqa: E111
  assert payload["health_score"] < 100  # noqa: E111
  assert "conditions" in payload  # noqa: E111
  conditions = payload["conditions"]  # noqa: E111
  assert conditions["temperature_c"] == 30.0  # noqa: E111
  assert conditions["last_updated"]  # noqa: E111
  assert "activities" in payload["recommendations"][0].lower()  # noqa: E111
