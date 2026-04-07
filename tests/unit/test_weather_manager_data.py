"""Tests for weather data ingestion and fallback behaviour.

Quality Scale: Platinum target
Python: 3.13+
"""

import asyncio
from datetime import timedelta
from typing import cast

import homeassistant.components.weather as weather_module
import homeassistant.const as ha_const
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
from tests.weather_test_support import ensure_weather_module_compat

UnitOfTemperature = ensure_weather_module_compat()
STATE_UNAVAILABLE = ha_const.STATE_UNAVAILABLE

from custom_components.pawcontrol.weather_manager import (
    WeatherHealthImpact,
    WeatherHealthManager,
    WeatherSeverity,
)


@pytest.fixture
def weather_manager(hass: HomeAssistant) -> WeatherHealthManager:
    """Return a fresh weather health manager for each test."""
    manager = WeatherHealthManager(hass)
    asyncio.run(manager.async_load_translations())
    return manager


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a config entry populated with a single dog profile."""
    entry = MockConfigEntry(
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
    entry.add_to_hass(hass)
    return entry


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_converts_units_and_builds_alerts(
    hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
    """High heat and humidity should produce alerts and derived metrics."""
    hass.states.async_set(
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

    conditions = await weather_manager.async_update_weather_data("weather.backyard")

    assert conditions is not None
    assert conditions.source_entity == "weather.backyard"
    assert conditions.temperature_c is not None
    assert conditions.temperature_c == pytest.approx((98.0 - 32.0) * 5 / 9)
    assert conditions.heat_index is not None
    assert conditions.heat_index > conditions.temperature_c

    alerts = weather_manager.get_active_alerts()
    assert alerts  # Heat stress alert should be registered
    assert any(alert.alert_type == WeatherHealthImpact.HEAT_STRESS for alert in alerts)
    assert weather_manager.get_weather_health_score() < 60


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_missing_temperature_uses_fallbacks(
    hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
    """Missing temperature should skip alerts and fall back to default score."""
    hass.states.async_set(
        "weather.lawn",
        "cloudy",
        {
            weather_module.ATTR_WEATHER_HUMIDITY: 55,
            weather_module.ATTR_WEATHER_UV_INDEX: 2,
            weather_module.ATTR_WEATHER_WIND_SPEED: 5.0,
            weather_module.ATTR_WEATHER_VISIBILITY: 10.0,
        },
    )

    conditions = await weather_manager.async_update_weather_data("weather.lawn")

    assert conditions is not None
    assert conditions.temperature_c is None
    assert weather_manager.get_weather_health_score() == 50
    assert weather_manager.get_active_alerts() == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_preserves_previous_conditions_when_unavailable(
    hass: HomeAssistant, weather_manager: WeatherHealthManager
) -> None:
    """Unavailable states should leave the last good snapshot untouched."""
    hass.states.async_set(
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
    initial = await weather_manager.async_update_weather_data("weather.rooftop")
    assert initial is not None

    hass.states.async_set("weather.rooftop", STATE_UNAVAILABLE, {})
    updated = await weather_manager.async_update_weather_data("weather.rooftop")

    assert updated is None
    cached = weather_manager.get_current_conditions()
    assert cached is initial
    assert cached is not None
    assert cached.temperature_c == pytest.approx(24.0)
    assert weather_manager.get_weather_health_score() > 60


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_missing_translation_falls_back_to_english(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Broken locale entries should fall back to English strings."""
    original_get = weather_translations.get_weather_translations

    def _broken_get_weather_translations(language: str) -> WeatherTranslations:
        catalog = original_get(language)
        if language == "de":
            catalog["alerts"].pop("extreme_heat_warning", None)
        return catalog

    monkeypatch.setattr(
        weather_translations,
        "get_weather_translations",
        _broken_get_weather_translations,
        raising=True,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.weather_manager.get_weather_translations",
        _broken_get_weather_translations,
        raising=True,
    )

    manager = WeatherHealthManager(hass)
    await manager.async_load_translations("de")
    assert "extreme_heat_warning" not in manager._translations["alerts"]
    assert (
        manager._english_translations["alerts"]["extreme_heat_warning"]["title"]
        == "🔥 Extreme Heat Warning"
    )

    hass.states.async_set(
        "weather.terrace",
        "sunny",
        {
            weather_module.ATTR_WEATHER_TEMPERATURE: 100.0,
            "temperature_unit": UnitOfTemperature.FAHRENHEIT,
            weather_module.ATTR_WEATHER_HUMIDITY: 85,
            weather_module.ATTR_WEATHER_UV_INDEX: 9,
        },
    )

    conditions = await manager.async_update_weather_data("weather.terrace")

    assert conditions is not None
    alerts = manager.get_active_alerts()
    assert alerts
    assert any(alert.title == "🔥 Extreme Heat Warning" for alert in alerts)
    assert any("Temperature" in alert.message for alert in alerts)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_handles_formatting_errors_in_translations(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locale formatting errors should not break alert generation."""
    original_get = weather_translations.get_weather_translations

    def _formatting_error_translations(language: str) -> WeatherTranslations:
        catalog = original_get(language)
        if language == "de":
            german_alerts = catalog["alerts"].get("high_heat_advisory")
            if german_alerts:
                german_alerts["message"] = (
                    "Temperatur {temperature}°C und {missing_placeholder} erfordern Schutz"  # noqa: E501
                )
        return catalog

    monkeypatch.setattr(
        weather_translations,
        "get_weather_translations",
        _formatting_error_translations,
        raising=True,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.weather_manager.get_weather_translations",
        _formatting_error_translations,
        raising=True,
    )

    manager = WeatherHealthManager(hass)
    await manager.async_load_translations("de")

    hass.states.async_set(
        "weather.deck",
        "sunny",
        {
            weather_module.ATTR_WEATHER_TEMPERATURE: 32.0,
            weather_module.ATTR_WEATHER_HUMIDITY: 70,
            weather_module.ATTR_WEATHER_UV_INDEX: 7,
        },
    )

    conditions = await manager.async_update_weather_data("weather.deck")

    assert conditions is not None
    alerts = manager.get_active_alerts()
    assert alerts
    advisory = next(
        alert
        for alert in alerts
        if (
            alert.alert_type == WeatherHealthImpact.HEAT_STRESS
            and alert.severity == WeatherSeverity.HIGH
        )
    )
    assert advisory.message == "Temperature 32.0°C requires heat precautions for dogs"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_forecast_data_returns_none_for_missing_or_invalid_forecast(
    hass: HomeAssistant,
) -> None:
    """Forecast ingestion should deterministically reject malformed weather payloads."""
    manager = WeatherHealthManager(hass)
    await manager.async_load_translations()

    # Missing entity -> deterministic None
    assert await manager.async_update_forecast_data("weather.unknown") is None

    # Forecast attribute must be a sequence
    hass.states.async_set("weather.invalid_seq", "sunny", {"forecast": {"bad": True}})
    assert await manager.async_update_forecast_data("weather.invalid_seq") is None

    # Forecast sequence must contain mappings only
    hass.states.async_set("weather.invalid_item", "sunny", {"forecast": ["bad"]})
    assert await manager.async_update_forecast_data("weather.invalid_item") is None

    # Empty sequence should also short-circuit
    hass.states.async_set("weather.empty", "sunny", {"forecast": []})
    assert await manager.async_update_forecast_data("weather.empty") is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_forecast_data_filters_invalid_points_and_out_of_horizon(
    hass: HomeAssistant,
) -> None:
    """Forecast processing should keep only valid in-horizon entries."""
    manager = WeatherHealthManager(hass)
    await manager.async_load_translations()

    now = dt_util.utcnow()
    hass.states.async_set(
        "weather.partial",
        "sunny",
        {
            "forecast": [
                {"datetime": "not-a-datetime", "temperature": 18.0},
                {
                    "datetime": (now + timedelta(hours=48)).isoformat(),
                    "temperature": 17.0,
                },
                {
                    "datetime": (now + timedelta(hours=2)).isoformat(),
                    "temperature": 68.0,
                    "temperature_unit": UnitOfTemperature.FAHRENHEIT,
                    "humidity": 45,
                    "uv_index": 2,
                    "condition": "sunny",
                },
            ]
        },
    )

    forecast = await manager.async_update_forecast_data(
        "weather.partial",
        forecast_horizon_hours=6,
    )

    assert forecast is not None
    assert len(forecast.forecast_points) == 1
    assert forecast.forecast_points[0].temperature_c == pytest.approx(20.0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_weather_data_handles_resilience_timeout(
    hass: HomeAssistant,
) -> None:
    """Timeouts from resilience orchestration should fail closed with None."""
    manager = WeatherHealthManager(hass)
    await manager.async_load_translations()

    class _TimeoutResilience:
        async def execute_with_resilience(self, *_args, **_kwargs) -> None:
            raise TimeoutError("weather timeout")

    manager.resilience_manager = _TimeoutResilience()
    result = await manager.async_update_weather_data("weather.anything")
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_forecast_data_propagates_cancellation_from_resilience(
    hass: HomeAssistant,
) -> None:
    """Cancellation should propagate instead of being converted to a generic failure."""
    manager = WeatherHealthManager(hass)
    await manager.async_load_translations()

    class _CancelledResilience:
        async def execute_with_resilience(self, *_args, **_kwargs) -> None:
            raise asyncio.CancelledError

    manager.resilience_manager = _CancelledResilience()

    with pytest.raises(asyncio.CancelledError):
        await manager.async_update_forecast_data("weather.anything")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_returns_disabled_without_manager(
    config_entry: MockConfigEntry,
) -> None:
    """Adapters should surface a disabled status when no manager is attached."""
    adapter = WeatherModuleAdapter(
        config_entry=cast(PawControlConfigEntry, config_entry),
        ttl=timedelta(seconds=0),
    )

    payload = await adapter.async_get_data("test_dog")

    assert payload["status"] == "disabled"
    assert payload["alerts"] == []
    assert payload["recommendations"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_exposes_fallback_health_score(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    weather_manager: WeatherHealthManager,
) -> None:
    """When no conditions exist the adapter should return fallback scores."""
    adapter = WeatherModuleAdapter(
        config_entry=cast(PawControlConfigEntry, config_entry),
        ttl=timedelta(seconds=0),
    )
    adapter.attach(weather_manager)

    payload = await adapter.async_get_data("test_dog")

    assert payload["status"] == "ready"
    assert payload["health_score"] == 50
    assert payload["alerts"] == []
    assert payload["recommendations"] == [
        "Weather conditions are suitable for normal activities"
    ]
    assert "conditions" not in payload


@pytest.mark.unit
@pytest.mark.asyncio
async def test_weather_module_adapter_includes_conditions_when_available(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    weather_manager: WeatherHealthManager,
) -> None:
    """Adapters should embed the active conditions snapshot when present."""
    config_entry.options = {CONF_WEATHER_ENTITY: "weather.home"}
    hass.states.async_set(
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

    adapter = WeatherModuleAdapter(
        config_entry=cast(PawControlConfigEntry, config_entry),
        ttl=timedelta(seconds=0),
    )
    adapter.attach(weather_manager)

    payload = await adapter.async_get_data("test_dog")

    assert payload["status"] == "ready"
    assert payload["health_score"] < 100
    assert "conditions" in payload
    conditions = payload["conditions"]
    assert conditions["temperature_c"] == 30.0
    assert conditions["last_updated"]
    assert "activities" in payload["recommendations"][0].lower()
