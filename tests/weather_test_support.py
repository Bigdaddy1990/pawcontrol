"""Test helpers for weather module compatibility."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

import homeassistant.components.weather as weather_module
import homeassistant.const as ha_const

if TYPE_CHECKING:
  UnitOfTemperatureType = type[ha_const.UnitOfTemperature]
else:
  UnitOfTemperatureType = type

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


def ensure_weather_module_compat() -> UnitOfTemperatureType:
  """Ensure weather modules have the expected constants for tests."""

  for attr, value in _MISSING_WEATHER_ATTRS.items():
    if not hasattr(weather_module, attr):
      setattr(weather_module, attr, value)

  if not hasattr(ha_const, "UnitOfTemperature"):

    class UnitOfTemperature(str, Enum):
      CELSIUS = "°C"
      FAHRENHEIT = "°F"
      KELVIN = "K"

    ha_const.UnitOfTemperature = UnitOfTemperature

  return ha_const.UnitOfTemperature
