"""Options flow for PawControl."""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  CONF_MQTT_ENABLED,
  CONF_MQTT_TOPIC,
  CONF_NOTIFICATIONS,
  CONF_PUSH_NONCE_TTL_SECONDS,
  CONF_PUSH_PAYLOAD_MAX_BYTES,
  CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
  CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
  CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
  CONF_RESET_TIME,
  CONF_WEBHOOK_ENABLED,
  CONF_WEBHOOK_REQUIRE_SIGNATURE,
  CONF_WEBHOOK_SECRET,
  CONF_WEATHER_ALERTS,
  CONF_WEATHER_ENTITY,
  CONF_WEATHER_HEALTH_MONITORING,
  DEFAULT_GPS_UPDATE_INTERVAL,
  DEFAULT_RESET_TIME,
  DOG_ID_PATTERN,
  DOG_SIZE_WEIGHT_RANGES,
  DOG_SIZES,
  MAX_DOG_AGE,
  MAX_DOG_NAME_LENGTH,
  MIN_DOG_AGE,
  MIN_DOG_NAME_LENGTH,
  MIN_DOG_WEIGHT,
)
from .exceptions import ValidationError
from .types import (
  AUTO_REFRESH_FIELD,
  AUTO_TRACK_WALKS_FIELD,
  COMPACT_MODE_FIELD,
  DASHBOARD_MODE_FIELD,
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
  SHOW_ALERTS_FIELD,
  SHOW_MAPS_FIELD,
  SHOW_STATISTICS_FIELD,
)
from .validation import (
  InputCoercionError,
  coerce_float,
  coerce_int,
  ensure_notification_options,
  normalize_dog_id,
  validate_dog_name,
  validate_gps_accuracy_value,
  validate_gps_update_interval,
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
    self._selected_dog_id: str | None = None

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

  def _update_dogs(self) -> None:
    self._dogs = list(self._dogs)
    if self.hass is None:
      return
    self.hass.config_entries.async_update_entry(
      self.config_entry,
      data={**self.config_entry.data, CONF_DOGS: self._dogs},
    )

  def _create_options_entry(self, updates: dict[str, Any]) -> ConfigFlowResult:
    updated = dict(self.config_entry.options)
    updated.update(updates)
    return self.async_create_entry(title="", data=updated)

  def _dog_options(self) -> list[selector.SelectOptionDict]:
    return [
      selector.SelectOptionDict(
        value=str(dog.get(CONF_DOG_ID, "")),
        label=str(dog.get(CONF_DOG_NAME, dog.get(CONF_DOG_ID, ""))),
      )
      for dog in self._dogs
      if dog.get(CONF_DOG_ID)
    ]

  def _get_selected_dog(self) -> dict[str, Any] | None:
    if self._selected_dog_id is None:
      return None
    for dog in self._dogs:
      if dog.get(CONF_DOG_ID) == self._selected_dog_id:
        return dog
    return None

  def _summarize_dogs(self) -> str:
    summary = [
      f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})" for dog in self._dogs
    ]
    return "\n".join(summary) if summary else "-"

  def _build_dog_schema(self, current: dict[str, Any] | None = None) -> vol.Schema:
    current = current or {}
    size_options = [
      selector.SelectOptionDict(value=size, label=size.title()) for size in DOG_SIZES
    ]
    is_new = current == {}
    name_key = vol.Required if is_new else vol.Optional
    schema: dict[Any, Any] = {
      name_key(
        CONF_DOG_NAME,
        default=str(current.get(CONF_DOG_NAME, "")),
      ): cv.string,
    }
    if is_new:
      schema[vol.Required(CONF_DOG_ID)] = cv.string
    schema.update(
      {
        vol.Optional(
          CONF_DOG_BREED,
          default=str(current.get(CONF_DOG_BREED, "")),
        ): cv.string,
        vol.Optional(
          CONF_DOG_AGE,
          default=current.get(CONF_DOG_AGE),
        ): vol.Any(cv.positive_int, cv.string, None),
        vol.Optional(
          CONF_DOG_WEIGHT,
          default=current.get(CONF_DOG_WEIGHT),
        ): vol.Any(vol.Coerce(float), cv.string, None),
        vol.Optional(
          CONF_DOG_SIZE,
          default=current.get(CONF_DOG_SIZE),
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(options=size_options),
        ),
      }
    )
    return vol.Schema(schema)

  def _validate_dog_input(
    self,
    user_input: dict[str, Any],
    errors: dict[str, str],
    *,
    current_dog_id: str | None = None,
  ) -> dict[str, Any]:
    dog_id_raw = user_input.get(CONF_DOG_ID, current_dog_id)
    dog_name_raw = user_input.get(CONF_DOG_NAME)
    try:
      dog_id = normalize_dog_id(dog_id_raw)
    except InputCoercionError:
      dog_id = ""

    if not dog_id or len(dog_id) < MIN_DOG_NAME_LENGTH:
      errors[CONF_DOG_ID] = "dog_id_too_short"
    elif len(dog_id) > MAX_DOG_NAME_LENGTH:
      errors[CONF_DOG_ID] = "dog_id_too_long"
    elif not DOG_ID_PATTERN.match(dog_id):
      errors[CONF_DOG_ID] = "invalid_dog_id_format"
    elif any(
      dog.get(CONF_DOG_ID) == dog_id
      for dog in self._dogs
      if dog.get(CONF_DOG_ID) != current_dog_id
    ):
      errors[CONF_DOG_ID] = "dog_id_already_exists"

    try:
      dog_name = validate_dog_name(dog_name_raw)
    except ValidationError as err:
      errors[CONF_DOG_NAME] = err.constraint or "dog_name_invalid"
      dog_name = None

    if dog_name and any(
      dog.get(CONF_DOG_NAME, "").casefold() == dog_name.casefold()
      for dog in self._dogs
      if dog.get(CONF_DOG_ID) != current_dog_id
    ):
      errors[CONF_DOG_NAME] = "dog_name_already_exists"

    breed = user_input.get(CONF_DOG_BREED)
    breed = breed.strip() if isinstance(breed, str) and breed.strip() else None

    dog_age = self._coerce_dog_age(user_input.get(CONF_DOG_AGE), errors)
    dog_weight = self._coerce_dog_weight(user_input.get(CONF_DOG_WEIGHT), errors)
    dog_size = user_input.get(CONF_DOG_SIZE)
    if dog_size is not None and dog_size not in DOG_SIZES:
      errors[CONF_DOG_SIZE] = "invalid_dog_size"

    if (
      dog_weight is not None
      and isinstance(dog_size, str)
      and dog_size in DOG_SIZE_WEIGHT_RANGES
    ):
      weight_min, weight_max = DOG_SIZE_WEIGHT_RANGES[dog_size]
      if not weight_min <= dog_weight <= weight_max:
        errors[CONF_DOG_WEIGHT] = "weight_size_mismatch"

    return {
      CONF_DOG_ID: dog_id,
      CONF_DOG_NAME: dog_name,
      CONF_DOG_BREED: breed,
      CONF_DOG_AGE: dog_age,
      CONF_DOG_WEIGHT: dog_weight,
      CONF_DOG_SIZE: dog_size,
    }

  def _coerce_dog_age(self, value: Any, errors: dict[str, str]) -> int | None:
    if value in (None, ""):
      return None
    try:
      age = coerce_int(CONF_DOG_AGE, value)
    except InputCoercionError:
      errors[CONF_DOG_AGE] = "invalid_age_format"
      return None
    if age < MIN_DOG_AGE or age > MAX_DOG_AGE:
      errors[CONF_DOG_AGE] = "age_out_of_range"
      return None
    return age

  def _coerce_dog_weight(self, value: Any, errors: dict[str, str]) -> float | None:
    if value in (None, ""):
      return None
    try:
      weight = coerce_float(CONF_DOG_WEIGHT, value)
    except InputCoercionError:
      errors[CONF_DOG_WEIGHT] = "invalid_weight_format"
      return None
    if weight < MIN_DOG_WEIGHT or weight > MAX_DOG_WEIGHT:
      errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
      return None
    return float(weight)

  def _validate_gps_settings(
    self,
    user_input: dict[str, Any],
    errors: dict[str, str],
  ) -> None:
    for field, minimum, maximum, error_key in (
      (GPS_UPDATE_INTERVAL_FIELD, 30, 3600, "gps_update_interval_out_of_range"),
      (ROUTE_HISTORY_DAYS_FIELD, 1, 365, "invalid_configuration"),
    ):
      if user_input.get(field) in (None, ""):
        continue
      try:
        value = coerce_int(field, user_input.get(field))
      except InputCoercionError:
        errors[field] = (
          "gps_update_interval_not_numeric"
          if field == GPS_UPDATE_INTERVAL_FIELD
          else "invalid_configuration"
        )
        continue
      if value < minimum or value > maximum:
        errors[field] = error_key

    for field, minimum, maximum in (
      (GPS_ACCURACY_FILTER_FIELD, 1.0, 500.0),
      (GPS_DISTANCE_FILTER_FIELD, 1.0, 1000.0),
    ):
      if user_input.get(field) in (None, ""):
        continue
      try:
        value = coerce_float(field, user_input.get(field))
      except InputCoercionError:
        errors[field] = "gps_accuracy_not_numeric"
        continue
      if value < minimum or value > maximum:
        errors[field] = "gps_accuracy_out_of_range"

  def _gps_settings_schema(self, current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
      {
        vol.Optional(
          GPS_ENABLED_FIELD, default=current.get(GPS_ENABLED_FIELD, True)
        ): bool,
        vol.Optional(
          GPS_UPDATE_INTERVAL_FIELD,
          default=current.get(GPS_UPDATE_INTERVAL_FIELD, DEFAULT_GPS_UPDATE_INTERVAL),
        ): int,
        vol.Optional(
          GPS_ACCURACY_FILTER_FIELD,
          default=current.get(GPS_ACCURACY_FILTER_FIELD, 50.0),
        ): float,
        vol.Optional(
          GPS_DISTANCE_FILTER_FIELD,
          default=current.get(GPS_DISTANCE_FILTER_FIELD, 10.0),
        ): float,
        vol.Optional(
          ROUTE_RECORDING_FIELD,
          default=current.get(ROUTE_RECORDING_FIELD, True),
        ): bool,
        vol.Optional(
          ROUTE_HISTORY_DAYS_FIELD,
          default=current.get(ROUTE_HISTORY_DAYS_FIELD, 30),
        ): int,
        vol.Optional(
          AUTO_TRACK_WALKS_FIELD,
          default=current.get(AUTO_TRACK_WALKS_FIELD, False),
        ): bool,
      },
    )

  def _system_settings_schema(self, current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
      {
        vol.Optional(
          "data_retention_days",
          default=current.get("data_retention_days", 90),
        ): int,
        vol.Optional("auto_backup", default=current.get("auto_backup", False)): bool,
        vol.Optional(
          "performance_mode",
          default=current.get("performance_mode", "balanced"),
        ): vol.In(["minimal", "balanced", "full"]),
        vol.Optional(
          "enable_analytics",
          default=current.get("enable_analytics", False),
        ): bool,
        vol.Optional(
          "enable_cloud_backup",
          default=current.get("enable_cloud_backup", False),
        ): bool,
        vol.Optional(
          "resilience_skip_threshold",
          default=current.get("resilience_skip_threshold", 3),
        ): int,
        vol.Optional(
          "resilience_breaker_threshold",
          default=current.get("resilience_breaker_threshold", 1),
        ): int,
        vol.Optional(
          "manual_check_event",
          default=current.get("manual_check_event", ""),
        ): str,
        vol.Optional(
          "manual_guard_event",
          default=current.get("manual_guard_event", ""),
        ): str,
        vol.Optional(
          "manual_breaker_event",
          default=current.get("manual_breaker_event", ""),
        ): str,
        vol.Optional(
          CONF_RESET_TIME,
          default=self.config_entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
        ): str,
      },
    )

  async def async_step_init(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage the options."""
    return self.async_show_menu(
      step_id="init",
      menu_options=[
        "manage_dogs",
        "gps_settings",
        "notifications",
        "system_settings",
        "push_settings",
        "weather_settings",
        "dashboard_settings",
      ],
    )

  async def async_step_manage_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage dog profiles."""
    return self.async_show_menu(
      step_id="manage_dogs",
      menu_options=["add_dog", "edit_dog_select", "remove_dog_select", "init"],
      description_placeholders={
        "dogs_list": self._summarize_dogs(),
        "current_dogs_count": str(len(self._dogs)),
      },
    )

  async def async_step_add_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Add a new dog via the options flow."""
    errors: dict[str, str] = {}
    if user_input is not None:
      payload = self._validate_dog_input(user_input, errors)
      if not errors:
        self._dogs.append(payload)
        self._update_dogs()
        return await self.async_step_manage_dogs()

    return self.async_show_form(
      step_id="add_dog",
      data_schema=self._build_dog_schema(),
      errors=errors,
      description_placeholders={"dog_count": str(len(self._dogs))},
    )

  async def async_step_edit_dog_select(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select a dog to edit."""
    errors: dict[str, str] = {}
    options = self._dog_options()
    if not options:
      return self.async_abort(reason="no_dogs_configured")

    if user_input is not None:
      dog_id = user_input.get(CONF_DOG_ID)
      if isinstance(dog_id, str) and any(
        opt["value"] == dog_id for opt in options
      ):
        self._selected_dog_id = dog_id
        return await self.async_step_edit_dog()
      errors[CONF_DOG_ID] = "invalid_configuration"

    return self.async_show_form(
      step_id="edit_dog_select",
      data_schema=vol.Schema(
        {
          vol.Required(CONF_DOG_ID): selector.SelectSelector(
            selector.SelectSelectorConfig(options=options),
          )
        }
      ),
      errors=errors,
    )

  async def async_step_edit_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Edit the selected dog."""
    if self._selected_dog_id is None:
      return await self.async_step_edit_dog_select()

    current = self._get_selected_dog()
    if current is None:
      self._selected_dog_id = None
      return await self.async_step_edit_dog_select()

    errors: dict[str, str] = {}
    if user_input is not None:
      payload = self._validate_dog_input(
        user_input, errors, current_dog_id=self._selected_dog_id
      )
      if not errors:
        for index, dog in enumerate(self._dogs):
          if dog.get(CONF_DOG_ID) == self._selected_dog_id:
            self._dogs[index] = {**dog, **payload}
            break
        self._update_dogs()
        self._selected_dog_id = None
        return await self.async_step_manage_dogs()

    return self.async_show_form(
      step_id="edit_dog",
      data_schema=self._build_dog_schema(current),
      errors=errors,
      description_placeholders={"dog_name": str(current.get(CONF_DOG_NAME, ""))},
    )

  async def async_step_remove_dog_select(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select a dog to remove."""
    errors: dict[str, str] = {}
    options = self._dog_options()
    if not options:
      return self.async_abort(reason="no_dogs_configured")

    if user_input is not None:
      dog_id = user_input.get(CONF_DOG_ID)
      if isinstance(dog_id, str) and any(
        opt["value"] == dog_id for opt in options
      ):
        self._selected_dog_id = dog_id
        return await self.async_step_remove_dog_confirm()
      errors[CONF_DOG_ID] = "invalid_configuration"

    return self.async_show_form(
      step_id="remove_dog_select",
      data_schema=vol.Schema(
        {
          vol.Required(CONF_DOG_ID): selector.SelectSelector(
            selector.SelectSelectorConfig(options=options),
          )
        }
      ),
      errors=errors,
    )

  async def async_step_remove_dog_confirm(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Confirm dog removal."""
    if self._selected_dog_id is None:
      return await self.async_step_remove_dog_select()

    errors: dict[str, str] = {}
    current = self._get_selected_dog()
    if current is None:
      self._selected_dog_id = None
      return await self.async_step_remove_dog_select()

    if user_input is not None:
      if bool(user_input.get("confirm_remove")):
        if len(self._dogs) <= 1:
          errors["base"] = "no_dogs_configured"
        else:
          self._dogs = [
            dog for dog in self._dogs if dog.get(CONF_DOG_ID) != self._selected_dog_id
          ]
          self._update_dogs()
          self._selected_dog_id = None
          return await self.async_step_manage_dogs()
      else:
        self._selected_dog_id = None
        return await self.async_step_manage_dogs()

    return self.async_show_form(
      step_id="remove_dog_confirm",
      data_schema=vol.Schema({vol.Required("confirm_remove"): bool}),
      errors=errors,
      description_placeholders={"dog_name": str(current.get(CONF_DOG_NAME, ""))},
    )

  async def async_step_notifications(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage notification settings."""
    current: dict[str, Any] = {}
    stored = self.config_entry.options.get(CONF_NOTIFICATIONS)
    if isinstance(stored, dict):
      current = stored

    if user_input is not None:
      errors: dict[str, str] = {}
      try:
        dt_time.fromisoformat(str(user_input.get(NOTIFICATION_QUIET_START_FIELD)))
      except (TypeError, ValueError):
        errors[NOTIFICATION_QUIET_START_FIELD] = "quiet_start_invalid"
      try:
        dt_time.fromisoformat(str(user_input.get(NOTIFICATION_QUIET_END_FIELD)))
      except (TypeError, ValueError):
        errors[NOTIFICATION_QUIET_END_FIELD] = "quiet_end_invalid"

      if errors:
        return self.async_show_form(
          step_id="notifications",
          data_schema=build_notifications_schema(current),
          errors=errors,
        )

      normalized = ensure_notification_options(
        user_input,
        defaults=current,
      )
      return self._create_options_entry({CONF_NOTIFICATIONS: normalized})

    return self.async_show_form(
      step_id="notifications",
      data_schema=build_notifications_schema(current),
    )

  async def async_step_gps_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage GPS settings."""
    current: dict[str, Any] = {}
    stored = self.config_entry.options.get("gps_settings")
    if isinstance(stored, dict):
      current = stored

    if user_input is not None:
      errors: dict[str, str] = {}
      gps_enabled = bool(user_input.get(GPS_ENABLED_FIELD, True))
      if gps_enabled:
        try:
          validate_gps_update_interval(
            user_input.get(GPS_UPDATE_INTERVAL_FIELD),
            minimum=30,
            maximum=3600,
            required=True,
          )
        except ValidationError as err:
          errors[GPS_UPDATE_INTERVAL_FIELD] = (
            err.constraint or "gps_update_interval_out_of_range"
          )
        try:
          validate_gps_accuracy_value(
            user_input.get(GPS_ACCURACY_FILTER_FIELD),
            field=GPS_ACCURACY_FILTER_FIELD,
            required=False,
            min_value=1.0,
            max_value=500.0,
          )
        except ValidationError as err:
          errors[GPS_ACCURACY_FILTER_FIELD] = (
            err.constraint or "gps_accuracy_out_of_range"
          )

      if errors:
        return self.async_show_form(
          step_id="gps_settings",
          data_schema=self._gps_settings_schema(current),
          errors=errors,
        )

      normalized = self._normalise_gps_settings(user_input)
      return self._create_options_entry({"gps_settings": normalized})

    return self.async_show_form(
      step_id="gps_settings",
      data_schema=self._gps_settings_schema(current),
    )

  async def async_step_system_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage system settings."""
    current: dict[str, Any] = {}
    stored = self.config_entry.options.get("system_settings")
    if isinstance(stored, dict):
      current = stored

    if user_input is not None:
      errors: dict[str, str] = {}
      reset_time = user_input.get(CONF_RESET_TIME)
      if reset_time:
        try:
          dt_time.fromisoformat(str(reset_time))
        except ValueError:
          errors[CONF_RESET_TIME] = "invalid_time_format"
      if errors:
        return self.async_show_form(
          step_id="system_settings",
          data_schema=self._system_settings_schema(current),
          errors=errors,
        )

      updates = {
        "system_settings": {
          **current,
          "data_retention_days": user_input.get("data_retention_days"),
          "auto_backup": user_input.get("auto_backup"),
          "performance_mode": user_input.get("performance_mode"),
          "enable_analytics": user_input.get("enable_analytics"),
          "enable_cloud_backup": user_input.get("enable_cloud_backup"),
          "resilience_skip_threshold": user_input.get("resilience_skip_threshold"),
          "resilience_breaker_threshold": user_input.get(
            "resilience_breaker_threshold"
          ),
          "manual_check_event": user_input.get("manual_check_event"),
          "manual_guard_event": user_input.get("manual_guard_event"),
          "manual_breaker_event": user_input.get("manual_breaker_event"),
        },
        CONF_RESET_TIME: user_input.get(CONF_RESET_TIME, DEFAULT_RESET_TIME),
      }
      return self._create_options_entry(updates)

    return self.async_show_form(
      step_id="system_settings",
      data_schema=self._system_settings_schema(current),
    )

  async def async_step_dashboard_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure dashboard settings."""
    current: dict[str, Any] = {}
    stored = self.config_entry.options.get("dashboard_settings")
    if isinstance(stored, dict):
      current = stored

    if user_input is not None:
      return self._create_options_entry({"dashboard_settings": user_input})

    schema = vol.Schema(
      {
        vol.Optional(
          "show_statistics", default=current.get("show_statistics", True)
        ): bool,
        vol.Optional("show_alerts", default=current.get("show_alerts", True)): bool,
        vol.Optional("compact_mode", default=current.get("compact_mode", False)): bool,
        vol.Optional("show_maps", default=current.get("show_maps", True)): bool,
      },
    )
    return self.async_show_form(step_id="dashboard_settings", data_schema=schema)

  async def async_step_push_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure push ingestion settings."""
    if user_input is not None:
      updates = {
        CONF_WEBHOOK_ENABLED: user_input.get(CONF_WEBHOOK_ENABLED, True),
        CONF_WEBHOOK_REQUIRE_SIGNATURE: user_input.get(
          CONF_WEBHOOK_REQUIRE_SIGNATURE,
          True,
        ),
        CONF_WEBHOOK_SECRET: user_input.get(CONF_WEBHOOK_SECRET),
        CONF_MQTT_ENABLED: user_input.get(CONF_MQTT_ENABLED, False),
        CONF_MQTT_TOPIC: user_input.get(CONF_MQTT_TOPIC),
        CONF_PUSH_PAYLOAD_MAX_BYTES: user_input.get(CONF_PUSH_PAYLOAD_MAX_BYTES),
        CONF_PUSH_NONCE_TTL_SECONDS: user_input.get(CONF_PUSH_NONCE_TTL_SECONDS),
        CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE: user_input.get(
          CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
        ),
        CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE: user_input.get(
          CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
        ),
        CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE: user_input.get(
          CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
        ),
      }
      return self._create_options_entry(updates)

    schema = vol.Schema(
      {
        vol.Optional(
          CONF_WEBHOOK_ENABLED,
          default=self.config_entry.options.get(CONF_WEBHOOK_ENABLED, True),
        ): bool,
        vol.Optional(
          CONF_WEBHOOK_REQUIRE_SIGNATURE,
          default=self.config_entry.options.get(
            CONF_WEBHOOK_REQUIRE_SIGNATURE,
            True,
          ),
        ): bool,
        vol.Optional(
          CONF_WEBHOOK_SECRET,
          default=self.config_entry.options.get(CONF_WEBHOOK_SECRET, ""),
        ): str,
        vol.Optional(
          CONF_MQTT_ENABLED,
          default=self.config_entry.options.get(CONF_MQTT_ENABLED, False),
        ): bool,
        vol.Optional(
          CONF_MQTT_TOPIC,
          default=self.config_entry.options.get(CONF_MQTT_TOPIC, ""),
        ): str,
        vol.Optional(
          CONF_PUSH_PAYLOAD_MAX_BYTES,
          default=self.config_entry.options.get(CONF_PUSH_PAYLOAD_MAX_BYTES, 8192),
        ): int,
        vol.Optional(
          CONF_PUSH_NONCE_TTL_SECONDS,
          default=self.config_entry.options.get(CONF_PUSH_NONCE_TTL_SECONDS, 300),
        ): int,
        vol.Optional(
          CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
          default=self.config_entry.options.get(
            CONF_PUSH_RATE_LIMIT_WEBHOOK_PER_MINUTE,
            60,
          ),
        ): int,
        vol.Optional(
          CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE,
          default=self.config_entry.options.get(
            CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE, 120
          ),
        ): int,
        vol.Optional(
          CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
          default=self.config_entry.options.get(
            CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE, 90
          ),
        ): int,
      },
    )
    return self.async_show_form(step_id="push_settings", data_schema=schema)

  async def async_step_weather_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure weather settings."""
    current: dict[str, Any] = {}
    stored = self.config_entry.options.get("weather_settings")
    if isinstance(stored, dict):
      current = stored

    if user_input is not None:
      updates = {
        "weather_settings": {
          **current,
          CONF_WEATHER_ENTITY: user_input.get(CONF_WEATHER_ENTITY),
          CONF_WEATHER_HEALTH_MONITORING: user_input.get(
            CONF_WEATHER_HEALTH_MONITORING,
            True,
          ),
          CONF_WEATHER_ALERTS: user_input.get(CONF_WEATHER_ALERTS, True),
        },
      }
      return self._create_options_entry(updates)

    schema = vol.Schema(
      {
        vol.Optional(
          CONF_WEATHER_ENTITY,
          default=current.get(CONF_WEATHER_ENTITY, ""),
        ): str,
        vol.Optional(
          CONF_WEATHER_HEALTH_MONITORING,
          default=current.get(CONF_WEATHER_HEALTH_MONITORING, True),
        ): bool,
        vol.Optional(
          CONF_WEATHER_ALERTS,
          default=current.get(CONF_WEATHER_ALERTS, True),
        ): bool,
      },
    )
    return self.async_show_form(step_id="weather_settings", data_schema=schema)


__all__ = (
  "GPSOptionsNormalizerMixin",
  "PawControlOptionsFlow",
  "build_notifications_schema",
)
