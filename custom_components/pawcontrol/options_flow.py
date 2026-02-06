"""Options flow for PawControl.

Home Assistant guidance for integrations of this size favors keeping options
flow logic in a single module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow

from .const import (
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOGS,
  DEFAULT_GPS_UPDATE_INTERVAL,
)
from .types import (
  AUTO_TRACK_WALKS_FIELD,
  GPS_ACCURACY_FILTER_FIELD,
  GPS_DISTANCE_FILTER_FIELD,
  GPS_ENABLED_FIELD,
  GPS_UPDATE_INTERVAL_FIELD,
  NOTIFICATION_MOBILE_FIELD,
  NOTIFICATION_PRIORITY_FIELD,
  NOTIFICATION_QUIET_END_FIELD,
  NOTIFICATION_QUIET_HOURS_FIELD,
  NOTIFICATION_QUIET_START_FIELD,
  NOTIFICATION_REMINDER_REPEAT_FIELD,
  ROUTE_HISTORY_DAYS_FIELD,
  ROUTE_RECORDING_FIELD,
)


class GPSOptionsNormalizerMixin:
  """Normalize GPS options payloads for menu-driven options flows."""

  @staticmethod
  def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
      return value
    if isinstance(value, int | float):
      return bool(value)
    if isinstance(value, str):
      lowered = value.strip().lower()
      if lowered in {"true", "yes", "on", "1"}:
        return True
      if lowered in {"false", "no", "off", "0"}:
        return False
    return default

  def _normalise_gps_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a clamped/typed GPS settings mapping."""

    def _coerce_int(value: object, default: int, minimum: int, maximum: int) -> int:
      try:
        candidate = int(value)  # type: ignore[arg-type]
      except (TypeError, ValueError):
        return default
      return max(minimum, min(maximum, candidate))

    def _coerce_float(
      value: object,
      default: float,
      minimum: float,
      maximum: float,
    ) -> float:
      try:
        candidate = float(value)  # type: ignore[arg-type]
      except (TypeError, ValueError):
        return default
      return max(minimum, min(maximum, candidate))

    return {
      GPS_ENABLED_FIELD: self._coerce_bool(
        payload.get(GPS_ENABLED_FIELD), default=True
      ),
      GPS_UPDATE_INTERVAL_FIELD: _coerce_int(
        payload.get(GPS_UPDATE_INTERVAL_FIELD),
        default=DEFAULT_GPS_UPDATE_INTERVAL,
        minimum=30,
        maximum=3600,
      ),
      GPS_ACCURACY_FILTER_FIELD: _coerce_float(
        payload.get(GPS_ACCURACY_FILTER_FIELD),
        default=50.0,
        minimum=1.0,
        maximum=500.0,
      ),
      GPS_DISTANCE_FILTER_FIELD: _coerce_float(
        payload.get(GPS_DISTANCE_FILTER_FIELD),
        default=10.0,
        minimum=1.0,
        maximum=1000.0,
      ),
      ROUTE_RECORDING_FIELD: self._coerce_bool(
        payload.get(ROUTE_RECORDING_FIELD),
        default=True,
      ),
      ROUTE_HISTORY_DAYS_FIELD: _coerce_int(
        payload.get(ROUTE_HISTORY_DAYS_FIELD),
        default=30,
        minimum=1,
        maximum=365,
      ),
      AUTO_TRACK_WALKS_FIELD: self._coerce_bool(
        payload.get(AUTO_TRACK_WALKS_FIELD),
        default=False,
      ),
    }


def build_notifications_schema(current: dict[str, Any]) -> vol.Schema:
  """Build notifications schema with defaults from the current options."""

  return vol.Schema(
    {
      vol.Optional(
        NOTIFICATION_QUIET_HOURS_FIELD,
        default=bool(current.get(NOTIFICATION_QUIET_HOURS_FIELD, True)),
      ): bool,
      vol.Optional(
        NOTIFICATION_QUIET_START_FIELD,
        default=str(current.get(NOTIFICATION_QUIET_START_FIELD, "22:00:00")),
      ): str,
      vol.Optional(
        NOTIFICATION_QUIET_END_FIELD,
        default=str(current.get(NOTIFICATION_QUIET_END_FIELD, "07:00:00")),
      ): str,
      vol.Optional(
        NOTIFICATION_REMINDER_REPEAT_FIELD,
        default=int(current.get(NOTIFICATION_REMINDER_REPEAT_FIELD, 30)),
      ): vol.All(vol.Coerce(int), vol.Range(min=5, max=180)),
      vol.Optional(
        NOTIFICATION_PRIORITY_FIELD,
        default=bool(current.get(NOTIFICATION_PRIORITY_FIELD, True)),
      ): bool,
      vol.Optional(
        NOTIFICATION_MOBILE_FIELD,
        default=bool(current.get(NOTIFICATION_MOBILE_FIELD, True)),
      ): bool,
    },
  )


class PawControlOptionsFlow(GPSOptionsNormalizerMixin, OptionsFlow):
  """Handle options."""

  def __init__(self, config_entry: ConfigEntry) -> None:
    """Initialize options flow."""
    self.config_entry = config_entry
    self._dogs = list(config_entry.data.get(CONF_DOGS, []))

  @staticmethod
  def _build_notification_settings_payload(
    user_input: dict[str, Any],
    current: dict[str, Any],
  ) -> dict[str, Any]:
    """Normalize notification payload values from forms."""

    def _coerce_bool(value: object, default: bool) -> bool:
      if isinstance(value, bool):
        return value
      if isinstance(value, int | float):
        return bool(value)
      if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
          return True
        if lowered in {"false", "no", "off", "0"}:
          return False
      return default

    def _coerce_time(value: object, default: str) -> str:
      if isinstance(value, datetime):
        return value.isoformat()
      if isinstance(value, str) and value.strip():
        return value.strip()
      return default

    def _coerce_repeat(value: object, default: int) -> int:
      try:
        candidate = int(value)  # type: ignore[arg-type]
      except (TypeError, ValueError):
        return default
      return max(5, min(180, candidate))

    return {
      NOTIFICATION_QUIET_HOURS_FIELD: _coerce_bool(
        user_input.get(NOTIFICATION_QUIET_HOURS_FIELD),
        default=bool(current.get(NOTIFICATION_QUIET_HOURS_FIELD, True)),
      ),
      NOTIFICATION_QUIET_START_FIELD: _coerce_time(
        user_input.get(NOTIFICATION_QUIET_START_FIELD),
        default=str(current.get(NOTIFICATION_QUIET_START_FIELD, "22:00:00")),
      ),
      NOTIFICATION_QUIET_END_FIELD: _coerce_time(
        user_input.get(NOTIFICATION_QUIET_END_FIELD),
        default=str(current.get(NOTIFICATION_QUIET_END_FIELD, "07:00:00")),
      ),
      NOTIFICATION_REMINDER_REPEAT_FIELD: _coerce_repeat(
        user_input.get(NOTIFICATION_REMINDER_REPEAT_FIELD),
        default=int(current.get(NOTIFICATION_REMINDER_REPEAT_FIELD, 30)),
      ),
      NOTIFICATION_PRIORITY_FIELD: _coerce_bool(
        user_input.get(NOTIFICATION_PRIORITY_FIELD),
        default=bool(current.get(NOTIFICATION_PRIORITY_FIELD, True)),
      ),
      NOTIFICATION_MOBILE_FIELD: _coerce_bool(
        user_input.get(NOTIFICATION_MOBILE_FIELD),
        default=bool(current.get(NOTIFICATION_MOBILE_FIELD, True)),
      ),
    }

  async def async_step_init(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage the options."""
    return self.async_show_menu(
      step_id="init",
      menu_options=["manage_dogs", "global_settings"],
    )

  async def async_step_global_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage global settings."""
    if user_input is not None:
      return self.async_create_entry(title="", data=user_input)

    schema = vol.Schema({vol.Optional("enable_analytics", default=False): bool})
    return self.async_show_form(step_id="global_settings", data_schema=schema)

  async def async_step_manage_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select a dog to view."""
    if user_input is not None:
      return await self.async_step_init()

    dog_options = {dog[CONF_DOG_ID]: dog[CONF_DOG_NAME] for dog in self._dogs}
    return self.async_show_form(
      step_id="manage_dogs",
      data_schema=vol.Schema({vol.Required("dog"): vol.In(dog_options)}),
    )


__all__ = (
  "GPSOptionsNormalizerMixin",
  "PawControlOptionsFlow",
  "build_notifications_schema",
)
