"""Config flow for PawControl integration.

Consolidated flow handling setup and initial dog configuration.
"""

from __future__ import annotations

from typing import Any, Final, Literal

import voluptuous as vol
from homeassistant.config_entries import (
  ConfigEntry,
  ConfigFlow,
  ConfigFlowResult,
  OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.util import dt as dt_util

from .const import (
  CONF_DATA_RETENTION_DAYS,
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
  CONF_DOGS,
  CONF_DOOR_SENSOR,
  CONF_GPS_SOURCE,
  CONF_NAME,
  CONF_NOTIFY_FALLBACK,
  DEFAULT_DASHBOARD_AUTO_CREATE,
  DEFAULT_DASHBOARD_MODE,
  DEFAULT_DASHBOARD_THEME,
  DEFAULT_PERFORMANCE_MODE,
  DOG_ID_PATTERN,
  DOG_SIZE_WEIGHT_RANGES,
  DOG_SIZES,
  DOMAIN,
  MAX_DOG_AGE,
  MAX_DOG_NAME_LENGTH,
  MAX_DOG_WEIGHT,
  MAX_DOGS_PER_ENTRY,
  MIN_DOG_AGE,
  MIN_DOG_NAME_LENGTH,
  MIN_DOG_WEIGHT,
  PERFORMANCE_MODES,
)
from .entity_factory import ENTITY_PROFILES
from .exceptions import ValidationError
from .options_flow import PawControlOptionsFlow
from .types import (
  AUTO_REFRESH_FIELD,
  COMPACT_MODE_FIELD,
  DASHBOARD_AUTO_CREATE_FIELD,
  DASHBOARD_ENABLED_FIELD,
  DASHBOARD_MODE_FIELD,
  DASHBOARD_PER_DOG_FIELD,
  DASHBOARD_THEME_FIELD,
  DOG_MODULES_FIELD,
  MODULE_TOGGLE_FLOW_FLAGS,
  SHOW_ALERTS_FIELD,
  SHOW_FEEDING_SCHEDULE_FIELD,
  SHOW_HEALTH_CHARTS_FIELD,
  SHOW_MAPS_FIELD,
  SHOW_STATISTICS_FIELD,
  dog_modules_from_flow_input,
)
from .validation import InputCoercionError, coerce_float, coerce_int, normalize_dog_id
from .validation import validate_dog_name

_DEFAULT_DOG_MODULES: Final[dict[str, bool]] = {
  "feeding": True,
  "walk": True,
  "health": True,
  "gps": True,
  "garden": False,
  "notifications": True,
  "dashboard": True,
  "visitor": False,
  "grooming": False,
  "medication": False,
  "training": False,
}
_DEFAULT_RETENTION_DAYS: Final[int] = 90
_DEFAULT_DASHBOARD_OPTIONS: Final[dict[str, bool | int | str]] = {
  DASHBOARD_ENABLED_FIELD: True,
  DASHBOARD_AUTO_CREATE_FIELD: DEFAULT_DASHBOARD_AUTO_CREATE,
  DASHBOARD_PER_DOG_FIELD: True,
  DASHBOARD_THEME_FIELD: DEFAULT_DASHBOARD_THEME,
  DASHBOARD_MODE_FIELD: DEFAULT_DASHBOARD_MODE,
  SHOW_STATISTICS_FIELD: True,
  SHOW_MAPS_FIELD: True,
  SHOW_HEALTH_CHARTS_FIELD: True,
  SHOW_FEEDING_SCHEDULE_FIELD: True,
  SHOW_ALERTS_FIELD: True,
  COMPACT_MODE_FIELD: False,
  AUTO_REFRESH_FIELD: True,
  "refresh_interval": 60,
}
  CONF_NAME,
  DOG_ID_PATTERN,
  DOMAIN,
  MAX_DOG_NAME_LENGTH,
  MIN_DOG_NAME_LENGTH,
)
from .entity_factory import EntityFactory
from .options_flow import PawControlOptionsFlow
from .types import VALID_DOG_SIZES, dog_modules_from_flow_input
from .validation import ValidationError, normalize_dog_id, validate_dog_name

DOG_SCHEMA = vol.Schema(
  {
    vol.Required(CONF_DOG_NAME): cv.string,
    vol.Required(CONF_DOG_ID): cv.string,
    vol.Optional(CONF_DOG_BREED): cv.string,
    vol.Optional(CONF_DOG_AGE): vol.Any(str, int, float),
    vol.Optional(CONF_DOG_WEIGHT): vol.Any(str, int, float),
    vol.Optional(CONF_DOG_SIZE): vol.In(sorted(VALID_DOG_SIZES)),
  },
)
INTEGRATION_NAME_SCHEMA = vol.Schema(
  {vol.Required(CONF_NAME): cv.string},
)


class PawControlConfigFlow(ConfigFlow, domain=DOMAIN):
  """Handle a config flow for PawControl."""

  VERSION = 1

  def __init__(self) -> None:
    """Initialize the config flow."""
    self._data: dict[str, Any] = {CONF_DOGS: []}
    self._options: dict[str, Any] = {}
    self._pending_dog: dict[str, Any] | None = None
    self._discovery_info: dict[str, Any] | None = None
    self._entry_name: str | None = None
    self._pending_dog: dict[str, Any] | None = None
    self._entity_profile: str = "standard"
    self._reauth_entry: ConfigEntry | None = None
    self._reconfigure_entry: ConfigEntry | None = None

  @staticmethod
  @callback
  def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
    """Get the options flow for this handler."""
    return PawControlOptionsFlow(config_entry)

  @staticmethod
  @callback
  def async_supports_options_flow(config_entry: ConfigEntry) -> bool:
    """Return True because this integration supports options."""
    return True

  @staticmethod
  @callback
  def async_supports_reconfigure_flow(config_entry: ConfigEntry) -> bool:
    """Return True because this integration supports reconfigure."""
    return True

  def _existing_dog_ids(self) -> set[str]:
    return {
      dog[CONF_DOG_ID]
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict) and dog.get(CONF_DOG_ID)
    }

  def _existing_dog_names(self) -> set[str]:
    return {
      dog[CONF_DOG_NAME].casefold()
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict) and isinstance(dog.get(CONF_DOG_NAME), str)
    }

  def _validate_integration_name(self, name: str | None) -> str | None:
    if name is None:
      return None
    trimmed = name.strip()
    if not trimmed:
      return None
    if len(trimmed) < MIN_DOG_NAME_LENGTH:
      raise ValidationError(CONF_NAME, trimmed, "integration_name_too_short")
    if len(trimmed) > MAX_DOG_NAME_LENGTH:
      raise ValidationError(CONF_NAME, trimmed, "integration_name_too_long")
    return trimmed

  def _validate_dog_id(self, raw_id: str | None) -> str:
    if raw_id is None:
      raise ValidationError(CONF_DOG_ID, raw_id, "dog_id_required")
    normalised = normalize_dog_id(raw_id)
    if len(normalised) < MIN_DOG_NAME_LENGTH:
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_short")
    if len(normalised) > MAX_DOG_NAME_LENGTH:
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_too_long")
    if not DOG_ID_PATTERN.match(normalised):
      raise ValidationError(CONF_DOG_ID, normalised, "invalid_dog_id_format")
    if normalised in self._existing_dog_ids():
      raise ValidationError(CONF_DOG_ID, normalised, "dog_id_already_exists")
    return normalised

  def _validate_dog_breed(self, breed: str | None) -> str | None:
    if not breed:
      return None
    trimmed = breed.strip()
    if not trimmed:
      return None
    if len(trimmed) > 50:
      raise ValidationError(CONF_DOG_BREED, trimmed, "breed_name_too_long")
    if not all(char.isalpha() or char in {" ", "-", "'"} for char in trimmed):
      raise ValidationError(CONF_DOG_BREED, trimmed, "invalid_dog_breed")
    return trimmed

  def _validate_dog_age(self, age_value: Any) -> int | None:
    if age_value is None or age_value == "":
      return None
    try:
      age = float(age_value)
    except (TypeError, ValueError) as err:
      raise ValidationError(CONF_DOG_AGE, age_value, "invalid_age_format") from err
    if age < 0 or age > 30:
      raise ValidationError(CONF_DOG_AGE, age, "age_out_of_range")
    return int(age)

  def _validate_dog_weight(self, weight_value: Any) -> float | None:
    if weight_value is None or weight_value == "":
      return None
    try:
      weight = float(weight_value)
    except (TypeError, ValueError) as err:
      raise ValidationError(
        CONF_DOG_WEIGHT,
        weight_value,
        "invalid_weight_format",
      ) from err
    if weight < 0.5 or weight > 200:
      raise ValidationError(CONF_DOG_WEIGHT, weight, "weight_out_of_range")
    return weight

  def _validate_dog_payload(
    self,
    user_input: dict[str, Any],
  ) -> tuple[dict[str, Any] | None, dict[str, str]]:
    errors: dict[str, str] = {}
    validated: dict[str, Any] = {}

    try:
      name = validate_dog_name(user_input.get(CONF_DOG_NAME))
      if name is not None:
        if name.casefold() in self._existing_dog_names():
          raise ValidationError(CONF_DOG_NAME, name, "dog_name_already_exists")
        validated[CONF_DOG_NAME] = name
    except ValidationError as err:
      errors[CONF_DOG_NAME] = err.constraint or "invalid_config"

    try:
      dog_id = self._validate_dog_id(user_input.get(CONF_DOG_ID))
      validated[CONF_DOG_ID] = dog_id
    except ValidationError as err:
      errors[CONF_DOG_ID] = err.constraint or "invalid_config"

    try:
      breed = self._validate_dog_breed(user_input.get(CONF_DOG_BREED))
      if breed:
        validated[CONF_DOG_BREED] = breed
    except ValidationError as err:
      errors[CONF_DOG_BREED] = err.constraint or "invalid_config"

    try:
      age = self._validate_dog_age(user_input.get(CONF_DOG_AGE))
      if age is not None:
        validated[CONF_DOG_AGE] = age
    except ValidationError as err:
      errors[CONF_DOG_AGE] = err.constraint or "invalid_config"

    try:
      weight = self._validate_dog_weight(user_input.get(CONF_DOG_WEIGHT))
      if weight is not None:
        validated[CONF_DOG_WEIGHT] = weight
    except ValidationError as err:
      errors[CONF_DOG_WEIGHT] = err.constraint or "invalid_config"

    size = user_input.get(CONF_DOG_SIZE)
    if size:
      if size not in VALID_DOG_SIZES:
        errors[CONF_DOG_SIZE] = "invalid_dog_size"
      else:
        validated[CONF_DOG_SIZE] = size

    if errors:
      return None, errors
    return validated, {}

  def _build_profile_options(self) -> dict[str, str]:
    factory = EntityFactory(None, prewarm=False)
    options: dict[str, str] = {}
    for profile in factory.get_available_profiles():
      info = factory.get_profile_info(profile)
      options[profile] = info.name
    return options

  def _build_setup_summary(self) -> str:
    dogs = self._data[CONF_DOGS]
    dog_names = [dog.get(CONF_DOG_NAME, "?") for dog in dogs if isinstance(dog, dict)]
    return f"Dogs: {', '.join(dog_names)}"

  async def async_step_user(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle the initial step."""
    await self.async_set_unique_id(DOMAIN)
    self._abort_if_unique_id_configured()

    errors: dict[str, str] = {}
    if user_input is not None:
      name, error_key = self._validate_integration_name(user_input.get(CONF_NAME))
      if error_key is None and name is not None:
        self._data[CONF_NAME] = name
        return await self.async_step_add_dog()
      errors[CONF_NAME] = error_key or "integration_name_required"

    return self.async_show_form(
      step_id="user",
      data_schema=vol.Schema({vol.Required(CONF_NAME): cv.string}),
      errors=errors,
    )
      await self.async_set_unique_id(DOMAIN)
      self._abort_if_unique_id_configured()
      errors: dict[str, str] = {}
      try:
        validated_name = self._validate_integration_name(user_input.get(CONF_NAME))
      except ValidationError as err:
        validated_name = None
        errors[CONF_NAME] = err.constraint or "invalid_config"

      if not validated_name:
        errors[CONF_NAME] = errors.get(CONF_NAME, "integration_name_required")
      if errors:
        return self.async_show_form(
          step_id="user",
          data_schema=INTEGRATION_NAME_SCHEMA,
          errors=errors,
        )
      self._entry_name = validated_name
      return await self.async_step_add_dog()

    return self.async_show_form(step_id="user", data_schema=INTEGRATION_NAME_SCHEMA)

  async def async_step_add_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle dog configuration."""
    if user_input is not None:
      dog_payload = self._validate_dog_input(user_input, errors)
      if not errors:
        self._pending_dog = dog_payload
        return await self.async_step_dog_modules()

    return self.async_show_form(
      step_id="add_dog",
      data_schema=self._build_dog_schema(),
      errors=errors,
      description_placeholders={"dog_count": str(len(self._data[CONF_DOGS]))},
    )

  async def async_step_dog_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Enable modules for the most recently added dog."""
    if self._pending_dog is None:
      return await self.async_step_add_dog()

    if user_input is not None:
      self._pending_dog[DOG_MODULES_FIELD] = dog_modules_from_flow_input(
        user_input,
      )
      self._data[CONF_DOGS].append(self._pending_dog)
      self._pending_dog = None
      return await self.async_step_add_another_dog()

    dog_name = str(self._pending_dog.get(CONF_DOG_NAME, ""))
    dog_size = str(self._pending_dog.get(CONF_DOG_SIZE, "unknown"))
    dog_age = str(self._pending_dog.get(CONF_DOG_AGE, "unknown"))
    return self.async_show_form(
      step_id="dog_modules",
      data_schema=self._build_module_schema(),
      description_placeholders={
        "dog_name": dog_name,
        "dog_size": dog_size,
        "dog_age": dog_age,
      },
    )

  async def async_step_add_another_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle asking if the user wants to add another dog."""
    errors: dict[str, str] = {}
    dog_count = len(self._data[CONF_DOGS])
    remaining = max(0, MAX_DOGS_PER_ENTRY - dog_count)

    if user_input is not None:
      if bool(user_input.get("add_another")) and remaining > 0:
        return await self.async_step_add_dog()
      return await self.async_step_entity_profile()

    return self.async_show_form(
      step_id="add_another_dog",
      data_schema=vol.Schema(
        {
          vol.Optional(
            "add_another",
            default=remaining > 0,
          ): bool,
        },
      ),
      errors=errors,
      description_placeholders={
        "dog_count": str(dog_count),
        "max_dogs": str(MAX_DOGS_PER_ENTRY),
        "dogs_list": self._summarize_dogs(),
        "remaining_spots": str(remaining),
      },
    )

  async def async_step_entity_profile(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select the entity profile for this configuration."""
    errors: dict[str, str] = {}
    if user_input is not None:
      profile = user_input.get("entity_profile")
      if isinstance(profile, str) and profile in ENTITY_PROFILES:
        self._data["entity_profile"] = profile
        self._options["entity_profile"] = profile
        return await self.async_step_configure_modules()
      errors["entity_profile"] = "invalid_profile"

    profile_options = [
      selector.SelectOptionDict(
        value=profile_key,
        label=profile_info.name,
      )
      for profile_key, profile_info in ENTITY_PROFILES.items()
    ]
    return self.async_show_form(
      step_id="entity_profile",
      data_schema=vol.Schema(
        {
          vol.Required(
            "entity_profile",
            default=self._options.get("entity_profile", "standard"),
          ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=profile_options),
          )
        },
      ),
      errors=errors,
      description_placeholders=self._build_profile_placeholders(),
    )

  async def async_step_configure_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Capture global settings."""
    errors: dict[str, str] = {}

    if user_input is not None:
      retention = self._coerce_retention_days(user_input.get(CONF_DATA_RETENTION_DAYS))
      if retention is None:
        errors[CONF_DATA_RETENTION_DAYS] = "invalid_config"
      else:
        self._options.update(
          {
            "performance_mode": self._coerce_performance_mode(
              user_input.get("performance_mode"),
            ),
            "enable_analytics": bool(user_input.get("enable_analytics")),
            "enable_cloud_backup": bool(user_input.get("enable_cloud_backup")),
            CONF_DATA_RETENTION_DAYS: retention,
            "debug_logging": bool(user_input.get("debug_logging")),
          },
        )
        return await self.async_step_configure_external_entities()

    return self.async_show_form(
      step_id="configure_modules",
      data_schema=vol.Schema(
        {
          vol.Optional(
            "performance_mode",
            default=self._options.get("performance_mode", DEFAULT_PERFORMANCE_MODE),
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
            default=bool(self._options.get("enable_analytics", False)),
          ): bool,
          vol.Optional(
            "enable_cloud_backup",
            default=bool(self._options.get("enable_cloud_backup", False)),
          ): bool,
          vol.Optional(
            CONF_DATA_RETENTION_DAYS,
            default=int(
              self._options.get(CONF_DATA_RETENTION_DAYS, _DEFAULT_RETENTION_DAYS)
            ),
          ): cv.positive_int,
          vol.Optional(
            "debug_logging",
            default=bool(self._options.get("debug_logging", False)),
          ): bool,
        },
      ),
      errors=errors,
      description_placeholders=self._build_module_placeholders(),
    )

  async def async_step_configure_external_entities(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure optional external entity bindings."""
    errors: dict[str, str] = {}

    if user_input is not None:
      gps_source = self._validate_entity(
        user_input.get(CONF_GPS_SOURCE),
        errors,
        field=CONF_GPS_SOURCE,
        error_key="gps_entity_not_found",
      )
      door_sensor = self._validate_entity(
        user_input.get(CONF_DOOR_SENSOR),
        errors,
        field=CONF_DOOR_SENSOR,
        error_key="door_sensor_not_found",
      )
      notify_fallback = self._validate_entity(
        user_input.get(CONF_NOTIFY_FALLBACK),
        errors,
        field=CONF_NOTIFY_FALLBACK,
        error_key="notification_service_not_found",
      )
      if not errors:
        external_entities: dict[str, Any] = {}
        if gps_source:
          external_entities[CONF_GPS_SOURCE] = gps_source
        if door_sensor:
          external_entities[CONF_DOOR_SENSOR] = door_sensor
        if notify_fallback:
          external_entities[CONF_NOTIFY_FALLBACK] = notify_fallback
        if external_entities:
          self._data["external_entities"] = external_entities
        return await self.async_step_configure_dashboard()

    return self.async_show_form(
      step_id="configure_external_entities",
      data_schema=vol.Schema(
        {
          vol.Optional(CONF_GPS_SOURCE): cv.string,
          vol.Optional(CONF_DOOR_SENSOR): cv.string,
          vol.Optional(CONF_NOTIFY_FALLBACK): cv.string,
        },
      ),
      errors=errors,
      description_placeholders=self._build_external_entity_placeholders(),
    )

  async def async_step_configure_dashboard(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Capture dashboard setup preferences."""
    errors: dict[str, str] = {}
    if user_input is not None:
      refresh_interval = self._coerce_refresh_interval(
        user_input.get("refresh_interval"),
      )
      if refresh_interval is None:
        errors["refresh_interval"] = "invalid_config"
      else:
        options = dict(_DEFAULT_DASHBOARD_OPTIONS)
        options.update(
          {
            DASHBOARD_AUTO_CREATE_FIELD: bool(
              user_input.get("auto_create_dashboard", DEFAULT_DASHBOARD_AUTO_CREATE),
            ),
            DASHBOARD_PER_DOG_FIELD: bool(
              user_input.get("create_per_dog_dashboards", True),
            ),
            DASHBOARD_THEME_FIELD: str(
              user_input.get("dashboard_theme", DEFAULT_DASHBOARD_THEME)
            ),
            DASHBOARD_MODE_FIELD: str(
              user_input.get("dashboard_mode", DEFAULT_DASHBOARD_MODE)
            ),
            SHOW_STATISTICS_FIELD: bool(user_input.get("show_statistics", True)),
            SHOW_MAPS_FIELD: bool(user_input.get("show_maps", True)),
            SHOW_HEALTH_CHARTS_FIELD: bool(
              user_input.get("show_health_charts", True),
            ),
            SHOW_FEEDING_SCHEDULE_FIELD: bool(
              user_input.get("show_feeding_schedule", True),
            ),
            SHOW_ALERTS_FIELD: bool(user_input.get("show_alerts", True)),
            COMPACT_MODE_FIELD: bool(user_input.get("compact_mode", False)),
            AUTO_REFRESH_FIELD: bool(user_input.get("auto_refresh", True)),
            "refresh_interval": refresh_interval,
          },
        )
        self._options.update(options)
        return await self.async_step_final_setup()

    return self.async_show_form(
      step_id="configure_dashboard",
      data_schema=vol.Schema(
        {
          vol.Optional(
            "auto_create_dashboard",
            default=self._options.get(
              DASHBOARD_AUTO_CREATE_FIELD,
              DEFAULT_DASHBOARD_AUTO_CREATE,
            ),
          ): bool,
          vol.Optional(
            "create_per_dog_dashboards",
            default=self._options.get(DASHBOARD_PER_DOG_FIELD, True),
          ): bool,
          vol.Optional(
            "dashboard_theme",
            default=self._options.get(DASHBOARD_THEME_FIELD, DEFAULT_DASHBOARD_THEME),
          ): cv.string,
          vol.Optional(
            "dashboard_mode",
            default=self._options.get(DASHBOARD_MODE_FIELD, DEFAULT_DASHBOARD_MODE),
          ): selector.SelectSelector(
            selector.SelectSelectorConfig(
              options=[
                selector.SelectOptionDict(value="compact", label="compact"),
                selector.SelectOptionDict(value="full", label="full"),
              ],
            ),
          ),
          vol.Optional(
            "show_statistics",
            default=self._options.get(SHOW_STATISTICS_FIELD, True),
          ): bool,
          vol.Optional(
            "show_maps",
            default=self._options.get(SHOW_MAPS_FIELD, True),
          ): bool,
          vol.Optional(
            "show_health_charts",
            default=self._options.get(SHOW_HEALTH_CHARTS_FIELD, True),
          ): bool,
          vol.Optional(
            "show_feeding_schedule",
            default=self._options.get(SHOW_FEEDING_SCHEDULE_FIELD, True),
          ): bool,
          vol.Optional(
            "show_alerts",
            default=self._options.get(SHOW_ALERTS_FIELD, True),
          ): bool,
          vol.Optional(
            "compact_mode",
            default=self._options.get(COMPACT_MODE_FIELD, False),
          ): bool,
          vol.Optional(
            "auto_refresh",
            default=self._options.get(AUTO_REFRESH_FIELD, True),
          ): bool,
          vol.Optional(
            "refresh_interval",
            default=int(self._options.get("refresh_interval", 60)),
          ): cv.positive_int,
        },
      ),
      errors=errors,
      description_placeholders=self._build_dashboard_placeholders(),
    )

  async def async_step_final_setup(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Summarize configuration and create entry."""
    if user_input is not None:
      self._data["setup_timestamp"] = dt_util.utcnow().isoformat()
      return self.async_create_entry(
        title="Paw Control",
        data=self._data,
        options=self._options,
      )

    return self.async_show_form(
      step_id="final_setup",
      data_schema=vol.Schema({}),
      description_placeholders=self._build_final_summary(),
    )

  async def async_step_reauth(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reauthentication."""
    entry_id = self.context.get("entry_id")
    if entry_id is None:
      return self.async_abort(reason="invalid_config")

    entry = self.hass.config_entries.async_get_entry(entry_id)
    if entry is None:
      return self.async_abort(reason="invalid_config")

    await self.async_set_unique_id(entry.unique_id or DOMAIN)
    return await self.async_step_reauth_confirm()

  async def async_step_reauth_confirm(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Confirm reauthentication."""
    entry_id = self.context.get("entry_id")
    if entry_id is None:
      return self.async_abort(reason="invalid_config")

    entry = self.hass.config_entries.async_get_entry(entry_id)
    if entry is None:
      return self.async_abort(reason="invalid_config")

    if user_input is not None:
      timestamp = dt_util.utcnow().isoformat()
      options = dict(entry.options)
      options["last_reauth"] = timestamp
      return self.async_update_reload_and_abort(
        entry,
        options=options,
      )

    issues_detected = entry.options.get("reauth_health_issues", [])
    issues_summary = ", ".join(issues_detected) if issues_detected else "-"
    return self.async_show_form(
      step_id="reauth_confirm",
      data_schema=vol.Schema({vol.Required("confirm"): bool}),
      description_placeholders={
        "integration_name": entry.title,
        "issues_detected": issues_summary,
      },
    )

  async def async_step_reconfigure(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reconfiguration flow."""
    entry_id = self.context.get("entry_id")
    if entry_id is None:
      return self.async_abort(reason="invalid_config")

    entry = self.hass.config_entries.async_get_entry(entry_id)
    if entry is None:
      return self.async_abort(reason="invalid_config")

    await self.async_set_unique_id(entry.unique_id or DOMAIN)

    if user_input is not None:
      profile = user_input.get("entity_profile")
      if not isinstance(profile, str) or profile not in ENTITY_PROFILES:
        return self.async_show_form(
          step_id="reconfigure",
          data_schema=self._build_reconfigure_schema(entry.options),
          errors={"entity_profile": "invalid_profile"},
          description_placeholders=self._build_reconfigure_placeholders(entry),
        )

      timestamp = dt_util.utcnow().isoformat()
      data_updates = dict(entry.data)
      data_updates["entity_profile"] = profile
      data_updates["reconfigure_timestamp"] = timestamp

      options_updates = dict(entry.options)
      options_updates["previous_profile"] = options_updates.get(
        "entity_profile",
        "standard",
      )
      options_updates["entity_profile"] = profile
      options_updates["last_reconfigure"] = timestamp

      return self.async_update_reload_and_abort(
        entry,
        data=data_updates,
        options=options_updates,
      )

    return self.async_show_form(
      step_id="reconfigure",
      data_schema=self._build_reconfigure_schema(entry.options),
      description_placeholders=self._build_reconfigure_placeholders(entry),
    )

  def _build_reconfigure_schema(self, options: dict[str, Any]) -> vol.Schema:
    profile_options = [
      selector.SelectOptionDict(value=profile, label=definition.name)
      for profile, definition in ENTITY_PROFILES.items()
    ]
    return vol.Schema(
      {
        vol.Required(
          "entity_profile",
          default=options.get("entity_profile", "standard"),
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(options=profile_options),
        ),
      },
    )

  def _build_reconfigure_placeholders(
    self,
    entry: ConfigEntry,
  ) -> dict[str, str]:
    current_profile = entry.options.get("entity_profile", "standard")
    profiles_info = ", ".join(ENTITY_PROFILES.keys())
    return {
      "current_profile": str(current_profile),
      "profiles_info": profiles_info,
    }

  def _validate_integration_name(self, value: Any) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
      return None, "integration_name_required"
    trimmed = value.strip()
    if not trimmed:
      return None, "integration_name_required"
    if len(trimmed) < MIN_DOG_NAME_LENGTH:
      return None, "integration_name_too_short"
    if len(trimmed) > MAX_DOG_NAME_LENGTH:
      return None, "integration_name_too_long"
    if trimmed.lower() in {"pawcontrol", "paw control"}:
      return None, "reserved_integration_name"
    return trimmed, None

  def _build_dog_schema(self) -> vol.Schema:
    size_options = [
      selector.SelectOptionDict(value=size, label=size.title()) for size in DOG_SIZES
    ]
    return vol.Schema(
      {
        vol.Required(CONF_DOG_NAME): cv.string,
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Optional(CONF_DOG_BREED): cv.string,
        vol.Optional(CONF_DOG_AGE): vol.Any(cv.positive_int, cv.string),
        vol.Optional(CONF_DOG_WEIGHT): vol.Any(vol.Coerce(float), cv.string),
        vol.Optional(CONF_DOG_SIZE): selector.SelectSelector(
          selector.SelectSelectorConfig(options=size_options),
        ),
      },
    )

  def _build_module_schema(self) -> vol.Schema:
    schema: dict[Any, Any] = {}
    for flow_flag, module_key in MODULE_TOGGLE_FLOW_FLAGS:
      default = _DEFAULT_DOG_MODULES.get(module_key, False)
      schema[vol.Optional(flow_flag, default=default)] = bool
    return vol.Schema(schema)

  def _validate_dog_input(
    self,
    user_input: dict[str, Any],
    errors: dict[str, str],
  ) -> dict[str, Any]:
    dog_id_raw = user_input.get(CONF_DOG_ID)
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
    elif any(dog.get(CONF_DOG_ID) == dog_id for dog in self._data[CONF_DOGS]):
      errors[CONF_DOG_ID] = "dog_id_already_exists"

    try:
      dog_name = validate_dog_name(dog_name_raw)
    except ValidationError as err:
      errors[CONF_DOG_NAME] = err.constraint or "dog_name_invalid"
      dog_name = None

    if dog_name and any(
      dog.get(CONF_DOG_NAME, "").casefold() == dog_name.casefold()
      for dog in self._data[CONF_DOGS]
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

  def _coerce_dog_age(
    self,
    value: Any,
    errors: dict[str, str],
  ) -> int | None:
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

  def _coerce_dog_weight(
    self,
    value: Any,
    errors: dict[str, str],
  ) -> float | None:
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

  def _coerce_performance_mode(self, value: Any) -> str:
    if isinstance(value, str) and value in PERFORMANCE_MODES:
      return value
    return DEFAULT_PERFORMANCE_MODE

  def _coerce_retention_days(self, value: Any) -> int | None:
    if value in (None, ""):
      return _DEFAULT_RETENTION_DAYS
    try:
      retention = coerce_int(CONF_DATA_RETENTION_DAYS, value)
    except InputCoercionError:
      return None
    if retention < 30 or retention > 365:
      return None
    return retention

  def _coerce_refresh_interval(self, value: Any) -> int | None:
    if value in (None, ""):
      return 60
    try:
      interval = coerce_int("refresh_interval", value)
    except InputCoercionError:
      return None
    if interval < 10 or interval > 3600:
      return None
    return interval

  def _summarize_dogs(self) -> str:
    summary = [
      f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})"
      for dog in self._data[CONF_DOGS]
    ]
    return "\n".join(summary) if summary else "-"

  def _build_module_placeholders(self) -> dict[str, str]:
    dogs = self._data[CONF_DOGS]
    total_modules = 0
    for dog in dogs:
      modules = dog.get(DOG_MODULES_FIELD, {})
      if isinstance(modules, dict):
        total_modules += sum(1 for value in modules.values() if value)
    module_summary = f"{total_modules} modules enabled across {len(dogs)} dogs"
    return {
      "dog_count": str(len(dogs)),
      "module_summary": module_summary,
      "total_modules": str(total_modules),
      "gps_dogs": str(
        sum(1 for dog in dogs if dog.get(DOG_MODULES_FIELD, {}).get("gps"))
      ),
      "health_dogs": str(
        sum(1 for dog in dogs if dog.get(DOG_MODULES_FIELD, {}).get("health"))
      ),
    }

  def _build_profile_placeholders(self) -> dict[str, str]:
    profile_descriptions = [
      f"{key}: {profile.description}" for key, profile in ENTITY_PROFILES.items()
    ]
    return {
      "dogs_count": str(len(self._data[CONF_DOGS])),
      "profiles_info": "\n".join(profile_descriptions),
      "compatibility_info": "Ready to create entities for selected profile.",
      "reconfigure_valid_dogs": str(len(self._data[CONF_DOGS])),
      "reconfigure_invalid_dogs": "0",
      "last_reconfigure": "-",
      "reconfigure_requested_profile": "-",
      "reconfigure_previous_profile": "-",
      "reconfigure_dogs": str(len(self._data[CONF_DOGS])),
      "reconfigure_entities": "-",
      "reconfigure_health": "-",
      "reconfigure_warnings": "-",
      "reconfigure_merge_notes": "-",
    }

  def _build_dashboard_placeholders(self) -> dict[str, str]:
    return {
      "dog_count": str(len(self._data[CONF_DOGS])),
      "dashboard_info": "Dashboard settings will be applied after setup.",
    }

  def _build_external_entity_placeholders(self) -> dict[str, str]:
    return {
      "gps_enabled": "true",
      "visitor_enabled": "true",
      "dog_count": str(len(self._data[CONF_DOGS])),
    }

  def _build_final_summary(self) -> dict[str, str]:
    summary_lines = [
      f"{dog.get(CONF_DOG_NAME)} ({dog.get(CONF_DOG_ID)})"
      for dog in self._data[CONF_DOGS]
    ]
    return {
      "setup_summary": "\n".join(summary_lines) if summary_lines else "-",
      "total_dogs": str(len(self._data[CONF_DOGS])),
    }

  def _validate_entity(
    self,
    value: Any,
    errors: dict[str, str],
    *,
    field: str,
    error_key: str,
  ) -> str | None:
    if value in (None, ""):
      return None
    if not isinstance(value, str):
      errors[field] = error_key
      return None
    if "." in value:
      domain, service = value.split(".", 1)
      if self.hass.services.has_service(domain, service):
        return value
    if self.hass.states.get(value):
      return value
    errors[field] = error_key
    return None
      validated, errors = self._validate_dog_payload(user_input)
      if not errors and validated is not None:
        self._pending_dog = validated
        return await self.async_step_dog_modules()
      return self.async_show_form(
        step_id="add_dog",
        data_schema=DOG_SCHEMA,
        errors=errors,
        description_placeholders={"dog_count": str(len(self._data[CONF_DOGS]))},
      )

    return self.async_show_form(
      step_id="add_dog",
      data_schema=DOG_SCHEMA,
      description_placeholders={"dog_count": str(len(self._data[CONF_DOGS]))},
    )

  async def async_step_dog_modules(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure per-dog modules."""
    if self._pending_dog is None:
      return await self.async_step_add_dog()

    module_schema = vol.Schema(
      {
        vol.Optional("enable_feeding", default=True): bool,
        vol.Optional("enable_walk", default=True): bool,
        vol.Optional("enable_health", default=True): bool,
        vol.Optional("enable_gps", default=True): bool,
        vol.Optional("enable_garden", default=False): bool,
        vol.Optional("enable_notifications", default=True): bool,
        vol.Optional("enable_dashboard", default=True): bool,
        vol.Optional("enable_visitor", default=False): bool,
        vol.Optional("enable_grooming", default=False): bool,
        vol.Optional("enable_medication", default=False): bool,
        vol.Optional("enable_training", default=False): bool,
      },
    )

    if user_input is not None:
      modules = dog_modules_from_flow_input(user_input)
      dog_entry = dict(self._pending_dog)
      dog_entry["modules"] = modules
      self._data[CONF_DOGS].append(dog_entry)
      self._pending_dog = None
      return await self.async_step_add_another_dog()

    placeholders = {
      "dog_name": str(self._pending_dog.get(CONF_DOG_NAME, "")),
      "dog_size": str(self._pending_dog.get(CONF_DOG_SIZE, "")),
      "dog_age": str(self._pending_dog.get(CONF_DOG_AGE, "")),
    }
    return self.async_show_form(
      step_id="dog_modules",
      data_schema=module_schema,
      description_placeholders=placeholders,
    )

  async def async_step_add_another_dog(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Ask if another dog should be added."""
    if user_input is not None:
      if user_input.get("add_another"):
        return await self.async_step_add_dog()
      return await self.async_step_entity_profile()

    dogs_list = ", ".join(
      dog.get(CONF_DOG_NAME, "")
      for dog in self._data[CONF_DOGS]
      if isinstance(dog, dict)
    )
    return self.async_show_form(
      step_id="add_another_dog",
      data_schema=vol.Schema({vol.Required("add_another", default=False): bool}),
      description_placeholders={
        "dog_count": str(len(self._data[CONF_DOGS])),
        "max_dogs": "10",
        "dogs_list": dogs_list,
        "remaining_spots": "0",
      },
    )

  async def async_step_entity_profile(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Select entity profile for this entry."""
    profile_options = self._build_profile_options()

    if user_input is not None:
      self._entity_profile = user_input["entity_profile"]
      return await self.async_step_final_setup()

    schema = vol.Schema(
      {
        vol.Required(
          "entity_profile",
          default=self._entity_profile,
        ): vol.In(profile_options),
      },
    )
    return self.async_show_form(
      step_id="entity_profile",
      data_schema=schema,
      description_placeholders={
        "dogs_count": str(len(self._data[CONF_DOGS])),
        "profiles_info": ", ".join(profile_options.values()),
        "compatibility_info": "Ready",
        "reconfigure_valid_dogs": str(len(self._data[CONF_DOGS])),
        "reconfigure_invalid_dogs": "0",
        "last_reconfigure": "Never",
        "reconfigure_requested_profile": self._entity_profile,
        "reconfigure_previous_profile": self._entity_profile,
        "reconfigure_dogs": str(len(self._data[CONF_DOGS])),
        "reconfigure_entities": "0",
        "reconfigure_health": "OK",
        "reconfigure_warnings": "None",
        "reconfigure_merge_notes": "None",
      },
    )

  async def async_step_final_setup(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Finalize configuration."""
    if user_input is not None:
      data = {
        CONF_NAME: self._entry_name or "Paw Control",
        CONF_DOGS: self._data[CONF_DOGS],
        "entity_profile": self._entity_profile,
        "setup_timestamp": dt_util.utcnow().isoformat(),
      }
      return self.async_create_entry(
        title=self._entry_name or "Paw Control",
        data=data,
      )

    return self.async_show_form(
      step_id="final_setup",
      data_schema=vol.Schema({}),
      description_placeholders={
        "setup_summary": self._build_setup_summary(),
        "total_dogs": str(len(self._data[CONF_DOGS])),
      },
    )

  async def async_step_reauth(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reauthentication."""
    entry_id = self.context.get("entry_id")
    if entry_id and self.hass:
      self._reauth_entry = self.hass.config_entries.async_get_entry(entry_id)
    return await self.async_step_reauth_confirm()

  async def async_step_reauth_confirm(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Confirm reauthentication."""
    if user_input is not None:
      if self._reauth_entry and self.hass:
        self.hass.config_entries.async_update_entry(
          self._reauth_entry,
          data={
            **self._reauth_entry.data,
            "reauth_timestamp": dt_util.utcnow().isoformat(),
          },
        )
      return self.async_abort(reason="reauth_successful")

    integration_name = self._reauth_entry.title if self._reauth_entry else "Paw Control"
    return self.async_show_form(
      step_id="reauth_confirm",
      data_schema=vol.Schema({vol.Required("confirm", default=True): bool}),
      description_placeholders={
        "integration_name": integration_name,
        "issues_detected": "Credentials refresh requested.",
      },
    )

  async def async_step_reconfigure(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Handle reconfigure flow."""
    entry_id = self.context.get("entry_id")
    if entry_id and self.hass:
      self._reconfigure_entry = self.hass.config_entries.async_get_entry(entry_id)
    profile_options = self._build_profile_options()
    current_profile = None
    if self._reconfigure_entry:
      current_profile = self._reconfigure_entry.options.get(
        "entity_profile",
        self._reconfigure_entry.data.get("entity_profile", "standard"),
      )

    if user_input is not None:
      if self._reconfigure_entry and self.hass:
        updated_options = dict(self._reconfigure_entry.options)
        updated_options["entity_profile"] = user_input["entity_profile"]
        updated_options["last_reconfigure"] = dt_util.utcnow().isoformat()
        self.hass.config_entries.async_update_entry(
          self._reconfigure_entry,
          data={
            **self._reconfigure_entry.data,
            "entity_profile": user_input["entity_profile"],
          },
          options=updated_options,
        )
      return self.async_abort(reason="reconfigure_successful")

    schema = vol.Schema(
      {
        vol.Required(
          "entity_profile",
          default=current_profile or self._entity_profile,
        ): vol.In(profile_options),
      },
    )
    return self.async_show_form(
      step_id="reconfigure",
      data_schema=schema,
      description_placeholders={
        "current_profile": current_profile or self._entity_profile,
        "profiles_info": ", ".join(profile_options.values()),
      },
    )


ConfigFlowAlias: Final[Literal["ConfigFlow"]] = "ConfigFlow"
ConfigFlow = PawControlConfigFlow

__all__: Final[tuple[Literal["ConfigFlow"], Literal["PawControlConfigFlow"]]] = (
  ConfigFlowAlias,
  "PawControlConfigFlow",
)
