"""Options flow for PawControl.

Home Assistant guidance for integrations of this size favors keeping options
flow logic in a single module.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import (
  CONF_DATA_RETENTION_DAYS,
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  DEFAULT_GPS_UPDATE_INTERVAL,
  DEFAULT_PERFORMANCE_MODE,
  DOG_ID_PATTERN,
  DOG_SIZE_WEIGHT_RANGES,
  DOG_SIZES,
  MAX_DOG_AGE,
  MAX_DOG_NAME_LENGTH,
  MAX_DOG_WEIGHT,
  MIN_DOG_AGE,
  MIN_DOG_NAME_LENGTH,
  MIN_DOG_WEIGHT,
  PERFORMANCE_MODES,
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
  normalize_dog_id,
  validate_dog_name,
  validate_time_window,
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
      if isinstance(dog_id, str) and dog_id in options:
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
        {**user_input, CONF_DOG_ID: self._selected_dog_id},
        errors,
        current_dog_id=self._selected_dog_id,
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
      if isinstance(dog_id, str) and dog_id in options:
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

  async def async_step_gps_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure GPS settings."""
    errors: dict[str, str] = {}
    current = dict(self.config_entry.options)

    if user_input is not None:
      self._validate_gps_settings(user_input, errors)
      if not errors:
        payload = self._normalise_gps_settings(user_input)
        return self._create_entry_with_options(payload)

    return self.async_show_form(
      step_id="gps_settings",
      data_schema=vol.Schema(
        {
          vol.Optional(
            GPS_ENABLED_FIELD,
            default=bool(current.get(GPS_ENABLED_FIELD, True)),
          ): bool,
          vol.Optional(
            GPS_UPDATE_INTERVAL_FIELD,
            default=int(
              current.get(GPS_UPDATE_INTERVAL_FIELD, DEFAULT_GPS_UPDATE_INTERVAL)
            ),
          ): cv.positive_int,
          vol.Optional(
            GPS_ACCURACY_FILTER_FIELD,
            default=float(current.get(GPS_ACCURACY_FILTER_FIELD, 50.0)),
          ): vol.Coerce(float),
          vol.Optional(
            GPS_DISTANCE_FILTER_FIELD,
            default=float(current.get(GPS_DISTANCE_FILTER_FIELD, 10.0)),
          ): vol.Coerce(float),
          vol.Optional(
            ROUTE_RECORDING_FIELD,
            default=bool(current.get(ROUTE_RECORDING_FIELD, True)),
          ): bool,
          vol.Optional(
            ROUTE_HISTORY_DAYS_FIELD,
            default=int(current.get(ROUTE_HISTORY_DAYS_FIELD, 30)),
          ): cv.positive_int,
          vol.Optional(
            AUTO_TRACK_WALKS_FIELD,
            default=bool(current.get(AUTO_TRACK_WALKS_FIELD, False)),
          ): bool,
        },
      ),
      errors=errors,
    )

  async def async_step_notifications(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure notification settings."""
    errors: dict[str, str] = {}
    current = dict(self.config_entry.options)

    if user_input is not None:
      quiet_hours_enabled = bool(user_input.get(NOTIFICATION_QUIET_HOURS_FIELD, True))
      if quiet_hours_enabled:
        try:
          validate_time_window(
            user_input.get(NOTIFICATION_QUIET_START_FIELD),
            user_input.get(NOTIFICATION_QUIET_END_FIELD),
            start_field=NOTIFICATION_QUIET_START_FIELD,
            end_field=NOTIFICATION_QUIET_END_FIELD,
            invalid_start_constraint="quiet_start_invalid",
            invalid_end_constraint="quiet_end_invalid",
          )
        except ValidationError as err:
          if err.field == NOTIFICATION_QUIET_START_FIELD:
            errors[NOTIFICATION_QUIET_START_FIELD] = "quiet_start_invalid"
          elif err.field == NOTIFICATION_QUIET_END_FIELD:
            errors[NOTIFICATION_QUIET_END_FIELD] = "quiet_end_invalid"

      if not errors:
        payload = self._build_notification_settings_payload(user_input, current)
        return self._create_entry_with_options(payload)

    return self.async_show_form(
      step_id="notifications",
      data_schema=build_notifications_schema(current),
      errors=errors,
    )

  async def async_step_system_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure global system settings."""
    errors: dict[str, str] = {}
    current = dict(self.config_entry.options)

    if user_input is not None:
      retention = self._coerce_retention_days(user_input.get(CONF_DATA_RETENTION_DAYS))
      if retention is None:
        errors[CONF_DATA_RETENTION_DAYS] = "invalid_configuration"
      else:
        payload = {
          "performance_mode": self._coerce_performance_mode(
            user_input.get("performance_mode"),
          ),
          "enable_analytics": bool(user_input.get("enable_analytics")),
          "enable_cloud_backup": bool(user_input.get("enable_cloud_backup")),
          CONF_DATA_RETENTION_DAYS: retention,
          "debug_logging": bool(user_input.get("debug_logging")),
        }
        return self._create_entry_with_options(payload)

    return self.async_show_form(
      step_id="system_settings",
      data_schema=vol.Schema(
        {
          vol.Optional(
            "performance_mode",
            default=current.get("performance_mode", DEFAULT_PERFORMANCE_MODE),
          ): selector.SelectSelector(
            selector.SelectSelectorConfig(
              options=[
                selector.SelectOptionDict(value=mode, label=mode)
                for mode in PERFORMANCE_MODES
              ],
            ),
          ),
          vol.Optional(
            "enable_analytics",
            default=bool(current.get("enable_analytics", False)),
          ): bool,
          vol.Optional(
            "enable_cloud_backup",
            default=bool(current.get("enable_cloud_backup", False)),
          ): bool,
          vol.Optional(
            CONF_DATA_RETENTION_DAYS,
            default=int(current.get(CONF_DATA_RETENTION_DAYS, 90)),
          ): cv.positive_int,
          vol.Optional(
            "debug_logging",
            default=bool(current.get("debug_logging", False)),
          ): bool,
        },
      ),
      errors=errors,
    )

  async def async_step_dashboard_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure dashboard settings."""
    current = dict(self.config_entry.options)
    if user_input is not None:
      payload = {
        DASHBOARD_MODE_FIELD: str(
          user_input.get(
            DASHBOARD_MODE_FIELD, current.get(DASHBOARD_MODE_FIELD, "full")
          )
        ),
        SHOW_STATISTICS_FIELD: bool(user_input.get(SHOW_STATISTICS_FIELD, True)),
        SHOW_ALERTS_FIELD: bool(user_input.get(SHOW_ALERTS_FIELD, True)),
        SHOW_MAPS_FIELD: bool(user_input.get(SHOW_MAPS_FIELD, True)),
        COMPACT_MODE_FIELD: bool(user_input.get(COMPACT_MODE_FIELD, False)),
        AUTO_REFRESH_FIELD: bool(user_input.get(AUTO_REFRESH_FIELD, True)),
      }
      return self._create_entry_with_options(payload)

    return self.async_show_form(
      step_id="dashboard_settings",
      data_schema=vol.Schema(
        {
          vol.Optional(
            DASHBOARD_MODE_FIELD,
            default=current.get(DASHBOARD_MODE_FIELD, "full"),
          ): selector.SelectSelector(
            selector.SelectSelectorConfig(
              options=[
                selector.SelectOptionDict(value="compact", label="compact"),
                selector.SelectOptionDict(value="full", label="full"),
              ],
            ),
          ),
          vol.Optional(
            SHOW_STATISTICS_FIELD,
            default=bool(current.get(SHOW_STATISTICS_FIELD, True)),
          ): bool,
          vol.Optional(
            SHOW_ALERTS_FIELD,
            default=bool(current.get(SHOW_ALERTS_FIELD, True)),
          ): bool,
          vol.Optional(
            SHOW_MAPS_FIELD,
            default=bool(current.get(SHOW_MAPS_FIELD, True)),
          ): bool,
          vol.Optional(
            COMPACT_MODE_FIELD,
            default=bool(current.get(COMPACT_MODE_FIELD, False)),
          ): bool,
          vol.Optional(
            AUTO_REFRESH_FIELD,
            default=bool(current.get(AUTO_REFRESH_FIELD, True)),
          ): bool,
        },
      ),
    )

  def _create_entry_with_options(self, updates: dict[str, Any]) -> ConfigFlowResult:
    merged = {**self.config_entry.options, **updates}
    return self.async_create_entry(title="", data=merged)

  def _update_dogs(self) -> None:
    self.hass.config_entries.async_update_entry(
      self.config_entry,
      data={**self.config_entry.data, CONF_DOGS: self._dogs},
    )

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

  def _coerce_retention_days(self, value: Any) -> int | None:
    if value in (None, ""):
      return 90
    try:
      retention = coerce_int(CONF_DATA_RETENTION_DAYS, value)
    except InputCoercionError:
      return None
    if retention < 30 or retention > 365:
      return None
    return retention

  def _coerce_performance_mode(self, value: Any) -> str:
    if isinstance(value, str) and value in PERFORMANCE_MODES:
      return value
    return DEFAULT_PERFORMANCE_MODE

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


__all__ = (
  "GPSOptionsNormalizerMixin",
  "PawControlOptionsFlow",
  "build_notifications_schema",
)
