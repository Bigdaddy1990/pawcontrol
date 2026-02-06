"""Options flow for PawControl."""

from __future__ import annotations

from datetime import time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow

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
  MAX_DOG_NAME_LENGTH,
  MIN_DOG_NAME_LENGTH,
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
  VALID_DOG_SIZES,
  dog_modules_from_flow_input,
  ensure_notification_options,
)
from .validation import (
  ValidationError,
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

  def _update_entry_data(self, dogs: list[dict[str, Any]]) -> None:
    self._dogs = dogs
    if self.hass is None:
      return
    self.hass.config_entries.async_update_entry(
      self.config_entry,
      data={**self.config_entry.data, CONF_DOGS: dogs},
    )

  def _create_options_entry(self, updates: dict[str, Any]) -> ConfigFlowResult:
    updated = dict(self.config_entry.options)
    updated.update(updates)
    return self.async_create_entry(title="", data=updated)

  def _dog_options(self) -> dict[str, str]:
    return {
      dog[CONF_DOG_ID]: dog[CONF_DOG_NAME]
      for dog in self._dogs
      if isinstance(dog, dict)
    }

  def _find_dog(self, dog_id: str) -> dict[str, Any] | None:
    for dog in self._dogs:
      if isinstance(dog, dict) and dog.get(CONF_DOG_ID) == dog_id:
        return dog
    return None

  def _validate_dog_payload(
    self,
    user_input: dict[str, Any],
    *,
    existing_ids: set[str],
    existing_names: set[str],
  ) -> tuple[dict[str, Any] | None, dict[str, str]]:
    errors: dict[str, str] = {}
    validated: dict[str, Any] = {}

    try:
      name = validate_dog_name(user_input.get(CONF_DOG_NAME))
      if name is not None:
        if name.casefold() in existing_names:
          raise ValidationError(CONF_DOG_NAME, name, "dog_name_already_exists")
        validated[CONF_DOG_NAME] = name
    except ValidationError as err:
      errors[CONF_DOG_NAME] = err.constraint or "invalid_configuration"

    raw_id = user_input.get(CONF_DOG_ID)
    if raw_id is not None:
      try:
        normalised = normalize_dog_id(raw_id)
        if len(normalised) < MIN_DOG_NAME_LENGTH:
          raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_short")
        if len(normalised) > MAX_DOG_NAME_LENGTH:
          raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_long")
        if not DOG_ID_PATTERN.match(normalised):
          raise ValidationError(CONF_DOG_ID, normalised, "invalid_dog_id_format")
        if normalised in existing_ids:
          raise ValidationError(CONF_DOG_ID, normalised, "dog_id_already_exists")
        validated[CONF_DOG_ID] = normalised
      except ValidationError as err:
        errors[CONF_DOG_ID] = err.constraint or "invalid_configuration"
    else:
      errors[CONF_DOG_ID] = "dog_missing_id"

    breed = user_input.get(CONF_DOG_BREED)
    if breed:
      trimmed = str(breed).strip()
      if len(trimmed) > 50:
        errors[CONF_DOG_BREED] = "breed_name_too_long"
      elif not all(char.isalpha() or char in {" ", "-", "'"} for char in trimmed):
        errors[CONF_DOG_BREED] = "invalid_dog_breed"
      else:
        validated[CONF_DOG_BREED] = trimmed

    age_value = user_input.get(CONF_DOG_AGE)
    if age_value not in (None, ""):
      try:
        age = float(age_value)
      except (TypeError, ValueError):
        errors[CONF_DOG_AGE] = "invalid_age_format"
      else:
        if age < 0 or age > 30:
          errors[CONF_DOG_AGE] = "age_out_of_range"
        else:
          validated[CONF_DOG_AGE] = int(age)

    weight_value = user_input.get(CONF_DOG_WEIGHT)
    if weight_value not in (None, ""):
      try:
        weight = float(weight_value)
      except (TypeError, ValueError):
        errors[CONF_DOG_WEIGHT] = "invalid_weight_format"
      else:
        if weight < 0.5 or weight > 200:
          errors[CONF_DOG_WEIGHT] = "weight_out_of_range"
        else:
          validated[CONF_DOG_WEIGHT] = weight

    size = user_input.get(CONF_DOG_SIZE)
    if size:
      if size not in VALID_DOG_SIZES:
        errors[CONF_DOG_SIZE] = "invalid_dog_size"
      else:
        validated[CONF_DOG_SIZE] = size

    if errors:
      return None, errors
    return validated, {}

  @staticmethod
  def _parse_time(value: str | None, error_key: str) -> str | None:
    if value is None:
      return None
    try:
      parsed = dt_time.fromisoformat(value)
    except ValueError as err:
      raise ValidationError("time", value, error_key) from err
    return parsed.isoformat()

  async def async_step_init(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Manage the options."""
    return self.async_show_menu(
      step_id="init",
      menu_options=[
        "manage_dogs",
        "notifications",
        "gps_settings",
        "system_settings",
        "push_settings",
        "weather_settings",
        "dashboard_settings",
      ],
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
        self._parse_time(
          user_input.get(NOTIFICATION_QUIET_START_FIELD),
          "quiet_start_invalid",
        )
      except ValidationError as err:
        errors[NOTIFICATION_QUIET_START_FIELD] = err.constraint or "invalid_time_format"
      try:
        self._parse_time(
          user_input.get(NOTIFICATION_QUIET_END_FIELD),
          "quiet_end_invalid",
        )
      except ValidationError as err:
        errors[NOTIFICATION_QUIET_END_FIELD] = err.constraint or "invalid_time_format"

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

  def _gps_settings_schema(self, current: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
      {
        vol.Optional(GPS_ENABLED_FIELD, default=current.get(GPS_ENABLED_FIELD, True)): bool,
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
          "resilience_breaker_threshold": user_input.get("resilience_breaker_threshold"),
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

  async def async_step_manage_dogs(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select a dog to manage."""
    if user_input is not None:
      action = user_input.get("action")
      dog_id = user_input.get(CONF_DOG_ID)
      if action == "back":
        return await self.async_step_init()
      if dog_id:
        self._selected_dog_id = dog_id
      if action == "edit_dog":
        return await self.async_step_edit_dog()
      if action == "remove_dog":
        return await self.async_step_remove_dog()
      if action == "configure_modules":
        return await self.async_step_configure_modules()

    dog_options = self._dog_options()
    dogs_list = ", ".join(dog_options.values())
    schema = vol.Schema(
      {
        vol.Required("action"): vol.In(
          ["edit_dog", "remove_dog", "configure_modules", "back"],
        ),
        vol.Required(CONF_DOG_ID): vol.In(dog_options),
      },
    )
    return self.async_show_form(
      step_id="manage_dogs",
      data_schema=schema,
      description_placeholders={
        "dogs_list": dogs_list,
        "current_dogs_count": str(len(dog_options)),
      },
    )

  async def async_step_edit_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Edit dog metadata."""
    dog = self._find_dog(self._selected_dog_id or "")
    if dog is None:
      return await self.async_step_manage_dogs()

    existing_ids = {
      d[CONF_DOG_ID]
      for d in self._dogs
      if isinstance(d, dict) and d.get(CONF_DOG_ID) != dog.get(CONF_DOG_ID)
    }
    existing_names = {
      d[CONF_DOG_NAME].casefold()
      for d in self._dogs
      if isinstance(d, dict) and d.get(CONF_DOG_ID) != dog.get(CONF_DOG_ID)
    }

    if user_input is not None:
      validated, errors = self._validate_dog_payload(
        {**user_input, CONF_DOG_ID: dog.get(CONF_DOG_ID)},
        existing_ids=existing_ids,
        existing_names=existing_names,
      )
      if errors:
        return self.async_show_form(
          step_id="edit_dog",
          data_schema=self._edit_dog_schema(dog),
          errors=errors,
        )
      updated = {**dog, **(validated or {})}
      dogs = [
        updated if d.get(CONF_DOG_ID) == dog.get(CONF_DOG_ID) else d
        for d in self._dogs
      ]
      self._update_entry_data(dogs)
      return await self.async_step_manage_dogs()

    return self.async_show_form(
      step_id="edit_dog",
      data_schema=self._edit_dog_schema(dog),
    )

  def _edit_dog_schema(self, dog: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
      {
        vol.Required(CONF_DOG_NAME, default=dog.get(CONF_DOG_NAME, "")): str,
        vol.Optional(CONF_DOG_BREED, default=dog.get(CONF_DOG_BREED, "")): str,
        vol.Optional(CONF_DOG_AGE, default=dog.get(CONF_DOG_AGE, "")): vol.Any(
          str,
          int,
          float,
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=dog.get(CONF_DOG_WEIGHT, "")): vol.Any(
          str,
          int,
          float,
        ),
        vol.Optional(CONF_DOG_SIZE, default=dog.get(CONF_DOG_SIZE, "")): vol.In(
          sorted(VALID_DOG_SIZES),
        ),
      },
    )

  async def async_step_remove_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Remove a dog configuration."""
    dog = self._find_dog(self._selected_dog_id or "")
    if dog is None:
      return await self.async_step_manage_dogs()

    if user_input is not None:
      if user_input.get("confirm_remove"):
        dogs = [
          d
          for d in self._dogs
          if isinstance(d, dict) and d.get(CONF_DOG_ID) != dog.get(CONF_DOG_ID)
        ]
        self._update_entry_data(dogs)
      return await self.async_step_manage_dogs()

    return self.async_show_form(
      step_id="remove_dog",
      data_schema=vol.Schema({vol.Required("confirm_remove", default=False): bool}),
      description_placeholders={"dog_name": dog.get(CONF_DOG_NAME, "")},
    )

  async def async_step_configure_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure modules for a specific dog."""
    dog = self._find_dog(self._selected_dog_id or "")
    if dog is None:
      return await self.async_step_manage_dogs()

    existing_modules = (
      dog.get("modules", {}) if isinstance(dog.get("modules"), dict) else {}
    )
    schema = vol.Schema(
      {
        vol.Optional("enable_feeding", default=existing_modules.get("feeding", False)): bool,
        vol.Optional("enable_walk", default=existing_modules.get("walk", False)): bool,
        vol.Optional("enable_health", default=existing_modules.get("health", False)): bool,
        vol.Optional("enable_gps", default=existing_modules.get("gps", False)): bool,
        vol.Optional("enable_garden", default=existing_modules.get("garden", False)): bool,
        vol.Optional(
          "enable_notifications",
          default=existing_modules.get("notifications", False),
        ): bool,
        vol.Optional(
          "enable_dashboard",
          default=existing_modules.get("dashboard", False),
        ): bool,
        vol.Optional("enable_visitor", default=existing_modules.get("visitor", False)): bool,
        vol.Optional("enable_grooming", default=existing_modules.get("grooming", False)): bool,
        vol.Optional(
          "enable_medication",
          default=existing_modules.get("medication", False),
        ): bool,
        vol.Optional("enable_training", default=existing_modules.get("training", False)): bool,
      },
    )

    if user_input is not None:
      modules = dog_modules_from_flow_input(user_input, existing=existing_modules)
      updated = {**dog, "modules": modules}
      dogs = [
        updated if d.get(CONF_DOG_ID) == dog.get(CONF_DOG_ID) else d
        for d in self._dogs
      ]
      self._update_entry_data(dogs)
      return await self.async_step_manage_dogs()

    return self.async_show_form(step_id="configure_modules", data_schema=schema)

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
          default=self.config_entry.options.get(CONF_PUSH_RATE_LIMIT_MQTT_PER_MINUTE, 120),
        ): int,
        vol.Optional(
          CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE,
          default=self.config_entry.options.get(CONF_PUSH_RATE_LIMIT_ENTITY_PER_MINUTE, 90),
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
        vol.Optional("show_statistics", default=current.get("show_statistics", True)): bool,
        vol.Optional("show_alerts", default=current.get("show_alerts", True)): bool,
        vol.Optional("compact_mode", default=current.get("compact_mode", False)): bool,
        vol.Optional("show_maps", default=current.get("show_maps", True)): bool,
      },
    )
    return self.async_show_form(step_id="dashboard_settings", data_schema=schema)

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


__all__ = (
  "GPSOptionsNormalizerMixin",
  "PawControlOptionsFlow",
  "build_notifications_schema",
)
