"""GPS flow helpers for Paw Control configuration and options."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
import logging
from typing import TYPE_CHECKING, Any, Protocol, cast

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ..const import (
  CONF_GPS_ACCURACY_FILTER,
  CONF_GPS_DISTANCE_FILTER,
  CONF_GPS_SOURCE,
  CONF_GPS_UPDATE_INTERVAL,
  DEFAULT_GPS_ACCURACY_FILTER,
  DEFAULT_GPS_DISTANCE_FILTER,
  DEFAULT_GPS_UPDATE_INTERVAL,
  MAX_GEOFENCE_RADIUS,
  MIN_GEOFENCE_RADIUS,
  MODULE_FEEDING,
  MODULE_GPS,
  MODULE_HEALTH,
  MODULE_NOTIFICATIONS,
  MODULE_WALK,
)
from ..exceptions import ValidationError
from ..flow_helpers import coerce_bool
from ..flow_validators import (
  validate_flow_gps_coordinates,
  validate_flow_timer_interval,
)
from ..schemas import (
  GEOFENCE_OPTIONS_JSON_SCHEMA,
  GPS_DOG_CONFIG_JSON_SCHEMA,
  GPS_OPTIONS_JSON_SCHEMA,
  validate_json_schema_payload,
)
from ..types import (
  AUTO_TRACK_WALKS_FIELD,
  DOG_GPS_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DOG_OPTIONS_FIELD,
  GEOFENCE_ALERTS_FIELD,
  GEOFENCE_ENABLED_FIELD,
  GEOFENCE_LAT_FIELD,
  GEOFENCE_LON_FIELD,
  GEOFENCE_RADIUS_FIELD,
  GEOFENCE_RESTRICTED_ZONE_FIELD,
  GEOFENCE_SAFE_ZONE_FIELD,
  GEOFENCE_USE_HOME_FIELD,
  GEOFENCE_ZONE_ENTRY_FIELD,
  GEOFENCE_ZONE_EXIT_FIELD,
  GPS_ACCURACY_FILTER_FIELD,
  GPS_DISTANCE_FILTER_FIELD,
  GPS_ENABLED_FIELD,
  GPS_SETTINGS_FIELD,
  GPS_UPDATE_INTERVAL_FIELD,
  ROUTE_HISTORY_DAYS_FIELD,
  ROUTE_RECORDING_FIELD,
  AddAnotherDogInput,
  ConfigFlowDiscoveryData,
  ConfigFlowPlaceholders,
  DogConfigData,
  DogFeedingStepInput,
  DogGPSConfig,
  DogGPSStepInput,
  DogHealthStepInput,
  DogOptionsMap,
  DogSetupStepInput,
  GeofenceOptions,
  GPSOptions,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  OptionsDogSelectionInput,
  OptionsGPSSettingsInput,
  ensure_dog_modules_config,
  ensure_dog_options_entry,
)
from ..validation import (
  InputValidator,
  validate_float_range,
  validate_gps_accuracy_value,
  validate_gps_interval,
  validate_gps_source,
)
from ..validation_helpers import safe_validate_interval
from .gps_helpers import build_dog_gps_placeholders, validation_error_key
from .gps_schemas import (
  build_dog_gps_schema,
  build_geofence_settings_schema,
  build_gps_settings_schema,
)

_LOGGER = logging.getLogger(__name__)


def _validate_gps_update_interval(
  value: JSONValue | None,
  *,
  field: str,
  minimum: int,
  maximum: int,
) -> int:
  """Validate a required GPS update interval for flow steps."""  # noqa: E111

  validated = validate_gps_interval(  # noqa: E111
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    required=True,
  )
  if validated is None:  # noqa: E111
    # Defensive guard: required=True should return an int or raise.
    raise ValidationError(field, value, "gps_update_interval_required")
  return validated  # noqa: E111


def _validate_gps_accuracy(
  value: JSONValue | None,
  *,
  field: str,
  minimum: float,
  maximum: float,
) -> float:
  """Validate a required GPS accuracy filter for flow steps."""  # noqa: E111

  validated = InputValidator.validate_gps_accuracy(  # noqa: E111
    value,
    required=True,
    field=field,
    min_value=minimum,
    max_value=maximum,
  )
  if validated is None:  # noqa: E111
    # Defensive guard: required=True should return a float or raise.
    raise ValidationError(field, value, "gps_accuracy_required")
  return validated  # noqa: E111


class GPSDefaultsHost(Protocol):
  """Protocol describing the config flow host requirements."""  # noqa: E111

  _discovery_info: ConfigFlowDiscoveryData  # noqa: E111


class GPSModuleDefaultsMixin(GPSDefaultsHost):
  """Provide GPS-aware defaults for module selection."""  # noqa: E111

  def _get_enhanced_modules_schema(self, dog_config: DogConfigData) -> vol.Schema:  # noqa: E111
    """Get enhanced modules schema with smart defaults.

    Args:
        dog_config: Dog configuration

    Returns:
        Enhanced modules schema
    """
    # Smart defaults based on discovery info or dog characteristics
    defaults = {
      MODULE_FEEDING: True,
      MODULE_WALK: True,
      MODULE_HEALTH: True,
      MODULE_GPS: self._should_enable_gps(dog_config),
      MODULE_NOTIFICATIONS: True,
    }

    return vol.Schema(
      {
        vol.Optional(
          MODULE_FEEDING,
          default=defaults[MODULE_FEEDING],
        ): cv.boolean,
        vol.Optional(MODULE_WALK, default=defaults[MODULE_WALK]): cv.boolean,
        vol.Optional(
          MODULE_HEALTH,
          default=defaults[MODULE_HEALTH],
        ): cv.boolean,
        vol.Optional(MODULE_GPS, default=defaults[MODULE_GPS]): cv.boolean,
        vol.Optional(
          MODULE_NOTIFICATIONS,
          default=defaults[MODULE_NOTIFICATIONS],
        ): cv.boolean,
      },
    )

  def _should_enable_gps(self, dog_config: DogConfigData) -> bool:  # noqa: E111
    """Determine if GPS should be enabled by default.

    Args:
        dog_config: Dog configuration

    Returns:
        True if GPS should be enabled by default
    """
    # Enable GPS for discovered devices or large dogs
    if self._discovery_info:
      return True  # noqa: E111

    dog_size = dog_config.get("dog_size", "medium")
    return dog_size in {"large", "giant"}

  def _get_smart_module_defaults(self, dog_config: DogConfigData) -> str:  # noqa: E111
    """Get explanation for smart module defaults.

    Args:
        dog_config: Dog configuration

    Returns:
        Explanation text
    """
    reasons = []

    if self._discovery_info:
      reasons.append("GPS enabled due to discovered tracking device")  # noqa: E111

    dog_size = dog_config.get("dog_size", "medium")
    if dog_size in {"large", "giant"}:
      reasons.append("GPS recommended for larger dogs")  # noqa: E111

    return "; ".join(reasons) if reasons else "Standard defaults applied"


if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant  # noqa: E111

  class DogGPSFlowHost(Protocol):  # noqa: E111
    _current_dog_config: DogConfigData | None
    _dogs: list[DogConfigData]
    hass: HomeAssistant

    def _get_available_device_trackers(self) -> dict[str, str]: ...

    def _get_available_person_entities(self) -> dict[str, str]: ...

    async def async_step_add_dog(
      self,
      user_input: DogSetupStepInput | None = None,
    ) -> ConfigFlowResult: ...

    async def async_step_dog_feeding(
      self,
      user_input: DogFeedingStepInput | None = None,
    ) -> ConfigFlowResult: ...

    async def async_step_dog_health(
      self,
      user_input: DogHealthStepInput | None = None,
    ) -> ConfigFlowResult: ...

    async def async_step_add_another_dog(
      self,
      user_input: AddAnotherDogInput | None = None,
    ) -> ConfigFlowResult: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
      description_placeholders: ConfigFlowPlaceholders | None = None,
    ) -> ConfigFlowResult: ...

else:  # pragma: no cover
  DogGPSFlowHost = object  # noqa: E111


class DogGPSFlowMixin(DogGPSFlowHost):
  """Handle GPS configuration steps in the config flow."""  # noqa: E111

  _current_dog_config: DogConfigData | None  # noqa: E111

  async def async_step_dog_gps(  # noqa: E111
    self,
    user_input: DogGPSStepInput | None = None,
  ) -> ConfigFlowResult:
    """Configure GPS settings for the specific dog."""

    current_dog = self._current_dog_config
    if current_dog is None:
      _LOGGER.error(  # noqa: E111
        "GPS configuration step invoked without active dog; restarting add_dog",
      )
      return await self.async_step_add_dog()  # noqa: E111

    if user_input is not None:
      errors: dict[str, str] = {}  # noqa: E111
      try:  # noqa: E111
        gps_source = validate_gps_source(
          self.hass,
          user_input.get(CONF_GPS_SOURCE),
          field=CONF_GPS_SOURCE,
          allow_manual=True,
        )
      except ValidationError as err:  # noqa: E111
        if err.constraint == "gps_source_unavailable":
          errors[CONF_GPS_SOURCE] = "gps_entity_unavailable"  # noqa: E111
        elif err.constraint == "gps_source_not_found":
          errors[CONF_GPS_SOURCE] = "gps_entity_not_found"  # noqa: E111
        else:
          errors[CONF_GPS_SOURCE] = "required"  # noqa: E111
        gps_source = "manual"

      try:  # noqa: E111
        gps_update_interval = _validate_gps_update_interval(
          user_input.get("gps_update_interval"),
          field="gps_update_interval",
          minimum=5,
          maximum=600,
        )
      except ValidationError as err:  # noqa: E111
        errors["gps_update_interval"] = validation_error_key(
          err,
          "validation_error",
        )
        gps_update_interval = DEFAULT_GPS_UPDATE_INTERVAL

      try:  # noqa: E111
        gps_accuracy = _validate_gps_accuracy(
          user_input.get("gps_accuracy_filter"),
          field="gps_accuracy_filter",
          minimum=5.0,
          maximum=500.0,
        )
      except ValidationError as err:  # noqa: E111
        errors["gps_accuracy_filter"] = validation_error_key(
          err,
          "validation_error",
        )
        gps_accuracy = DEFAULT_GPS_ACCURACY_FILTER

      try:  # noqa: E111
        home_zone_radius = InputValidator.validate_geofence_radius(
          user_input.get("home_zone_radius"),
          required=True,
          field="home_zone_radius",
          min_value=10.0,
          max_value=500.0,
        )
      except ValidationError as err:  # noqa: E111
        errors["home_zone_radius"] = validation_error_key(
          err,
          "validation_error",
        )
        home_zone_radius = 50.0

      if errors:  # noqa: E111
        return self.async_show_form(
          step_id="dog_gps",
          data_schema=self._get_dog_gps_schema(),
          errors=errors,
          description_placeholders=dict(
            cast(
              Mapping[str, str],
              build_dog_gps_placeholders(
                dog_name=current_dog[DOG_NAME_FIELD],
              ),
            ),
          ),
        )

      home_zone_radius = home_zone_radius if home_zone_radius is not None else 50.0  # noqa: E111

      gps_config: DogGPSConfig = {  # noqa: E111
        "gps_source": gps_source,
        "gps_update_interval": gps_update_interval,
        "gps_accuracy_filter": gps_accuracy,
        "enable_geofencing": coerce_bool(
          user_input.get("enable_geofencing"),
          default=True,
        ),
        "home_zone_radius": home_zone_radius,
      }
      schema_issues = validate_json_schema_payload(  # noqa: E111
        gps_config,
        GPS_DOG_CONFIG_JSON_SCHEMA,
      )
      if schema_issues:  # noqa: E111
        _LOGGER.error(
          "GPS config failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )
      current_dog[DOG_GPS_CONFIG_FIELD] = gps_config  # noqa: E111

      modules = ensure_dog_modules_config(current_dog)  # noqa: E111
      if modules.get(MODULE_HEALTH, False):  # noqa: E111
        return await self.async_step_dog_health()
      return await self.async_step_dog_feeding()  # noqa: E111

    return self.async_show_form(
      step_id="dog_gps",
      data_schema=self._get_dog_gps_schema(),
      description_placeholders=dict(
        cast(
          Mapping[str, str],
          build_dog_gps_placeholders(
            dog_name=current_dog[DOG_NAME_FIELD],
          ),
        ),
      ),
    )

  def _get_dog_gps_schema(self) -> vol.Schema:  # noqa: E111
    """Build the schema for GPS configuration."""

    gps_sources = self._get_available_device_trackers()
    return build_dog_gps_schema(gps_sources)


if TYPE_CHECKING:

  class GPSOptionsHost(Protocol):  # noqa: E111
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]

    def _clone_options(self) -> dict[str, JSONValue]: ...

    def _current_dog_options(self) -> DogOptionsMap: ...

    def _current_options(self) -> Mapping[str, JSONValue]: ...

    def _normalise_options_snapshot(
      self,
      options: Mapping[str, JSONValue],
    ) -> Mapping[str, JSONValue]: ...

    def _select_dog_by_id(
      self,
      dog_id: str | None,
    ) -> DogConfigData | None: ...

    def _require_current_dog(self) -> DogConfigData | None: ...

    def _build_dog_selector_schema(self) -> vol.Schema: ...

    def _coerce_str(
      self,
      value: Any,
      default: str | None,
    ) -> str | None: ...

    def _coerce_bool(
      self,
      value: Any,
      default: bool,
    ) -> bool: ...

    def _coerce_float(
      self,
      value: Any,
      default: float | None,
    ) -> float | None: ...

    def _normalise_gps_settings(
      self,
      raw: Mapping[str, JSONValue],
    ) -> GPSOptions: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
      description_placeholders: Mapping[str, str] | None = None,
    ) -> ConfigFlowResult: ...

    def async_create_entry(
      self,
      *,
      title: str,
      data: Mapping[str, JSONValue],
    ) -> ConfigFlowResult: ...

    async def async_step_init(self) -> ConfigFlowResult: ...

else:  # pragma: no cover
  from ..options_flow_shared import OptionsFlowSharedMixin  # noqa: E111

  class GPSOptionsHost(OptionsFlowSharedMixin):  # noqa: E111
    """Runtime host for GPS options mixin."""

    pass


class GPSOptionsMixin(GPSOptionsHost):
  _current_dog_config: DogConfigData | None  # noqa: E111
  """Handle per-dog GPS and geofencing options."""  # noqa: E111

  def _current_gps_options(self, dog_id: str) -> GPSOptions:  # noqa: E111
    """Return the stored GPS configuration with legacy fallbacks."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get(GPS_SETTINGS_FIELD)
    if isinstance(raw, Mapping):
      current = cast(GPSOptions, dict(raw))  # noqa: E111
    else:
      legacy = self._current_options().get(GPS_SETTINGS_FIELD, {})  # noqa: E111
      current = (  # noqa: E111
        cast(GPSOptions, dict(legacy))
        if isinstance(
          legacy,
          Mapping,
        )
        else {}
      )

    if (
      GPS_UPDATE_INTERVAL_FIELD not in current
      and (interval := self._current_options().get(CONF_GPS_UPDATE_INTERVAL))
      is not None
    ):
      if isinstance(interval, int):  # noqa: E111
        current[GPS_UPDATE_INTERVAL_FIELD] = interval
      elif isinstance(interval, float):  # noqa: E111
        current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)
      elif isinstance(interval, str):  # noqa: E111
        with suppress(ValueError):
          current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)  # noqa: E111

    if (
      GPS_ACCURACY_FILTER_FIELD not in current
      and (accuracy := self._current_options().get(CONF_GPS_ACCURACY_FILTER))
      is not None
    ):
      if isinstance(accuracy, int | float):  # noqa: E111
        current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)
      elif isinstance(accuracy, str):  # noqa: E111
        with suppress(ValueError):
          current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)  # noqa: E111

    if (
      GPS_DISTANCE_FILTER_FIELD not in current
      and (distance := self._current_options().get(CONF_GPS_DISTANCE_FILTER))
      is not None
    ):
      if isinstance(distance, int | float):  # noqa: E111
        current[GPS_DISTANCE_FILTER_FIELD] = float(distance)
      elif isinstance(distance, str):  # noqa: E111
        with suppress(ValueError):
          current[GPS_DISTANCE_FILTER_FIELD] = float(distance)  # noqa: E111

    return self._normalise_gps_settings(current)

  def _current_geofence_options(self, dog_id: str) -> GeofenceOptions:  # noqa: E111
    """Fetch the stored geofence configuration as a typed mapping."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get("geofence_settings")
    if isinstance(raw, Mapping):
      return cast(GeofenceOptions, dict(raw))  # noqa: E111

    legacy = self._current_options().get("geofence_settings", {})
    if isinstance(legacy, Mapping):
      return cast(GeofenceOptions, dict(legacy))  # noqa: E111

    return cast(GeofenceOptions, {})

  async def async_step_select_dog_for_gps_settings(  # noqa: E111
    self,
    user_input: OptionsDogSelectionInput | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure GPS settings for."""

    if not self._dogs:
      return await self.async_step_init()  # noqa: E111

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")  # noqa: E111
      self._select_dog_by_id(  # noqa: E111
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:  # noqa: E111
        return await self.async_step_gps_settings()
      return await self.async_step_init()  # noqa: E111

    return self.async_show_form(
      step_id="select_dog_for_gps_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_select_dog_for_geofence_settings(  # noqa: E111
    self,
    user_input: OptionsDogSelectionInput | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure geofencing for."""

    if not self._dogs:
      return await self.async_step_init()  # noqa: E111

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")  # noqa: E111
      self._select_dog_by_id(  # noqa: E111
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:  # noqa: E111
        return await self.async_step_geofence_settings()
      return await self.async_step_init()  # noqa: E111

    return self.async_show_form(
      step_id="select_dog_for_geofence_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_gps_settings(  # noqa: E111
    self,
    user_input: OptionsGPSSettingsInput | None = None,
  ) -> ConfigFlowResult:
    """Configure GPS settings."""

    explicitly_selected_dog = self._current_dog
    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_gps_settings()  # noqa: E111

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_gps_settings()  # noqa: E111

    persist_dog_id: str | None = None
    if explicitly_selected_dog is not None:
      explicit_id = explicitly_selected_dog.get(DOG_ID_FIELD)  # noqa: E111
      if isinstance(explicit_id, str):  # noqa: E111
        persist_dog_id = explicit_id

    current_options = self._current_gps_options(dog_id)
    if user_input is not None:
      errors: dict[str, str] = {}  # noqa: E111

      try:  # noqa: E111
        gps_update_interval = _validate_gps_update_interval(
          user_input.get(GPS_UPDATE_INTERVAL_FIELD),
          field=GPS_UPDATE_INTERVAL_FIELD,
          minimum=5,
          maximum=600,
        )
      except ValidationError as err:  # noqa: E111
        errors[GPS_UPDATE_INTERVAL_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        gps_update_interval = DEFAULT_GPS_UPDATE_INTERVAL

      try:  # noqa: E111
        gps_accuracy = _validate_gps_accuracy(
          user_input.get(GPS_ACCURACY_FILTER_FIELD),
          field=GPS_ACCURACY_FILTER_FIELD,
          minimum=5.0,
          maximum=500.0,
        )
      except ValidationError as err:  # noqa: E111
        errors[GPS_ACCURACY_FILTER_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        gps_accuracy = DEFAULT_GPS_ACCURACY_FILTER

      try:  # noqa: E111
        gps_distance = validate_float_range(
          user_input.get(GPS_DISTANCE_FILTER_FIELD),
          field=GPS_DISTANCE_FILTER_FIELD,
          minimum=1.0,
          maximum=2000.0,
          required=True,
        )
      except ValidationError:  # noqa: E111
        errors[GPS_DISTANCE_FILTER_FIELD] = "invalid_configuration"
        gps_distance = DEFAULT_GPS_DISTANCE_FILTER

      try:  # noqa: E111
        route_history = validate_flow_timer_interval(
          user_input.get(ROUTE_HISTORY_DAYS_FIELD),
          field=ROUTE_HISTORY_DAYS_FIELD,
          minimum=1,
          maximum=365,
          required=True,
        )
      except ValidationError:  # noqa: E111
        errors[ROUTE_HISTORY_DAYS_FIELD] = "invalid_configuration"
        route_history = 30

      if errors:  # noqa: E111
        return self.async_show_form(
          step_id="gps_settings",
          data_schema=self._build_gps_settings_schema(current_options),
          errors=errors,
        )

      current_options = cast(  # noqa: E111
        GPSOptions,
        {
          GPS_ENABLED_FIELD: coerce_bool(
            user_input.get(GPS_ENABLED_FIELD),
            default=True,
          ),
          GPS_UPDATE_INTERVAL_FIELD: gps_update_interval,
          GPS_ACCURACY_FILTER_FIELD: gps_accuracy,
          GPS_DISTANCE_FILTER_FIELD: gps_distance,
          ROUTE_RECORDING_FIELD: coerce_bool(
            user_input.get(ROUTE_RECORDING_FIELD),
            default=True,
          ),
          ROUTE_HISTORY_DAYS_FIELD: route_history,
          AUTO_TRACK_WALKS_FIELD: coerce_bool(
            user_input.get(AUTO_TRACK_WALKS_FIELD),
            default=True,
          ),
        },
      )

      schema_issues = validate_json_schema_payload(  # noqa: E111
        current_options,
        GPS_OPTIONS_JSON_SCHEMA,
      )
      if schema_issues:  # noqa: E111
        _LOGGER.error(
          "GPS options failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )

      updated_options = self._clone_options()  # noqa: E111
      if persist_dog_id is not None:  # noqa: E111
        dog_options = self._current_dog_options()
        dog_entry = ensure_dog_options_entry(
          cast(
            JSONLikeMapping,
            dict(dog_options.get(persist_dog_id, {})),
          ),
          dog_id=persist_dog_id,
        )
        dog_entry[GPS_SETTINGS_FIELD] = current_options
        dog_entry[DOG_ID_FIELD] = persist_dog_id
        dog_options[persist_dog_id] = dog_entry
        updated_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)
      updated_options[GPS_SETTINGS_FIELD] = cast(  # noqa: E111
        JSONValue,
        current_options,
      )

      return self.async_create_entry(  # noqa: E111
        title="GPS settings updated",
        data=self._normalise_options_snapshot(updated_options),
      )

    return self.async_show_form(
      step_id="gps_settings",
      data_schema=self._build_gps_settings_schema(current_options),
    )

  async def async_step_geofence_settings(  # noqa: E111
    self,
    user_input: OptionsGPSSettingsInput | None = None,
  ) -> ConfigFlowResult:
    """Handle geofence settings step for the selected dog."""

    explicitly_selected_dog = self._current_dog
    self._require_current_dog()

    dog_id: str | None = None
    if explicitly_selected_dog:
      current_dog_id = explicitly_selected_dog.get(DOG_ID_FIELD)  # noqa: E111
      if isinstance(current_dog_id, str):  # noqa: E111
        dog_id = current_dog_id

    if dog_id is not None:
      current_options = self._current_geofence_options(dog_id)  # noqa: E111
    else:
      legacy_options = self._current_options().get("geofence_settings", {})  # noqa: E111
      current_options = (  # noqa: E111
        cast(GeofenceOptions, dict(legacy_options))
        if isinstance(legacy_options, Mapping)
        else cast(GeofenceOptions, {})
      )

    if user_input is not None:
      errors: dict[str, str] = {}  # noqa: E111

      try:  # noqa: E111
        geofence_radius = InputValidator.validate_geofence_radius(
          user_input.get(GEOFENCE_RADIUS_FIELD),
          required=True,
          field=GEOFENCE_RADIUS_FIELD,
          min_value=float(MIN_GEOFENCE_RADIUS),
          max_value=float(MAX_GEOFENCE_RADIUS),
        )
      except ValidationError as err:  # noqa: E111
        errors[GEOFENCE_RADIUS_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        geofence_radius = current_options.get(GEOFENCE_RADIUS_FIELD, 100.0)

      geofence_lat: float | None  # noqa: E111
      geofence_lon: float | None  # noqa: E111
      try:  # noqa: E111
        geofence_lat, geofence_lon = validate_flow_gps_coordinates(
          user_input.get(GEOFENCE_LAT_FIELD),
          user_input.get(GEOFENCE_LON_FIELD),
          latitude_field=GEOFENCE_LAT_FIELD,
          longitude_field=GEOFENCE_LON_FIELD,
        )
      except ValidationError as err:  # noqa: E111
        errors[err.field] = validation_error_key(
          err,
          "invalid_configuration",
        )
        geofence_lat = current_options.get(GEOFENCE_LAT_FIELD)
        geofence_lon = current_options.get(GEOFENCE_LON_FIELD)

      if errors:  # noqa: E111
        return self.async_show_form(
          step_id="geofence_settings",
          data_schema=self._build_geofence_settings_schema(current_options),
          errors=errors,
        )

      geofence_radius_m = int(round(geofence_radius))  # noqa: E111
      if geofence_radius_m != geofence_radius:  # noqa: E111
        _LOGGER.debug(
          "Geofence radius %.3f normalized to integer %d for options schema",
          geofence_radius,
          geofence_radius_m,
        )

      geofence_options = cast(  # noqa: E111
        GeofenceOptions,
        {
          GEOFENCE_ENABLED_FIELD: coerce_bool(
            user_input.get(GEOFENCE_ENABLED_FIELD),
            default=True,
          ),
          GEOFENCE_USE_HOME_FIELD: coerce_bool(
            user_input.get(GEOFENCE_USE_HOME_FIELD),
            default=True,
          ),
          GEOFENCE_RADIUS_FIELD: geofence_radius_m,
          GEOFENCE_LAT_FIELD: geofence_lat,
          GEOFENCE_LON_FIELD: geofence_lon,
          GEOFENCE_ALERTS_FIELD: coerce_bool(
            user_input.get(GEOFENCE_ALERTS_FIELD),
            default=True,
          ),
          GEOFENCE_SAFE_ZONE_FIELD: coerce_bool(
            user_input.get(GEOFENCE_SAFE_ZONE_FIELD),
            default=True,
          ),
          GEOFENCE_RESTRICTED_ZONE_FIELD: coerce_bool(
            user_input.get(GEOFENCE_RESTRICTED_ZONE_FIELD),
            default=True,
          ),
          GEOFENCE_ZONE_ENTRY_FIELD: coerce_bool(
            user_input.get(GEOFENCE_ZONE_ENTRY_FIELD),
            default=True,
          ),
          GEOFENCE_ZONE_EXIT_FIELD: coerce_bool(
            user_input.get(GEOFENCE_ZONE_EXIT_FIELD),
            default=True,
          ),
        },
      )

      schema_issues = validate_json_schema_payload(  # noqa: E111
        geofence_options,
        GEOFENCE_OPTIONS_JSON_SCHEMA,
      )
      if schema_issues:  # noqa: E111
        _LOGGER.error(
          "Geofence options failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )

      updated_options = self._clone_options()  # noqa: E111
      updated_options["geofence_settings"] = cast(JSONValue, geofence_options)  # noqa: E111
      if dog_id is not None:  # noqa: E111
        dog_options = self._current_dog_options()
        dog_entry = ensure_dog_options_entry(
          cast(
            JSONLikeMapping,
            dict(dog_options.get(dog_id, {})),
          ),
          dog_id=dog_id,
        )
        dog_entry["geofence_settings"] = geofence_options
        dog_entry[DOG_ID_FIELD] = dog_id
        dog_options[dog_id] = dog_entry
        updated_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)

      return self.async_create_entry(  # noqa: E111
        title="Geofence settings updated",
        data=self._normalise_options_snapshot(updated_options),
      )

    return self.async_show_form(
      step_id="geofence_settings",
      data_schema=self._build_geofence_settings_schema(current_options),
    )

  def _build_gps_settings_schema(  # noqa: E111
    self,
    current_options: GPSOptions,
  ) -> vol.Schema:
    """Build schema for GPS settings."""

    return build_gps_settings_schema(current_options)

  def _build_geofence_settings_schema(  # noqa: E111
    self,
    current_options: GeofenceOptions,
  ) -> vol.Schema:
    """Build schema for geofence settings."""

    return build_geofence_settings_schema(current_options)


class GPSOptionsNormalizerHost(Protocol):
  """Protocol describing the options flow host requirements."""  # noqa: E111

  def _coerce_bool(self, value: Any, default: bool) -> bool: ...  # noqa: E111


class GPSOptionsNormalizerMixin(GPSOptionsNormalizerHost):
  """Mixin providing GPS normalization for options payloads."""  # noqa: E111

  @staticmethod  # noqa: E111
  def _coerce_bool(value: Any, default: bool) -> bool:  # noqa: E111
    """Return a boolean using Home Assistant style truthiness rules."""

    if value is None:
      return default  # noqa: E111
    if isinstance(value, bool):
      return value  # noqa: E111
    if isinstance(value, str):
      return value.strip().lower() in {"1", "true", "on", "yes"}  # noqa: E111
    return bool(value)

  def _normalise_gps_settings(self, raw: Mapping[str, JSONValue]) -> GPSOptions:  # noqa: E111
    """Return a normalised GPS options payload."""

    def _safe_interval(
      value: JSONValue | None,
      *,
      default: int,
      minimum: int,
      maximum: int,
      field: str,
    ) -> int:
      return safe_validate_interval(  # noqa: E111
        value,
        default=default,
        minimum=minimum,
        maximum=maximum,
        field=field,
        clamp=True,
      )

    def _safe_float_range(
      value: JSONValue | None,
      *,
      default: float,
      minimum: float,
      maximum: float,
      field: str,
    ) -> float:
      try:  # noqa: E111
        return validate_float_range(
          value,
          field=field,
          minimum=minimum,
          maximum=maximum,
          default=default,
          clamp=True,
        )
      except ValidationError:  # noqa: E111
        return default

    def _safe_gps_interval(
      value: JSONValue | None,
      *,
      default: int,
      minimum: int,
      maximum: int,
      field: str,
    ) -> int:
      try:  # noqa: E111
        return cast(
          int,
          validate_gps_interval(
            value,
            default=default,
            minimum=minimum,
            maximum=maximum,
            field=field,
            clamp=True,
          ),
        )
      except ValidationError:  # noqa: E111
        return default

    def _safe_gps_accuracy(
      value: JSONValue | None,
      *,
      default: float,
      minimum: float,
      maximum: float,
      field: str,
    ) -> float:
      try:  # noqa: E111
        return cast(
          float,
          validate_gps_accuracy_value(
            value,
            field=field,
            min_value=minimum,
            max_value=maximum,
            default=default,
            clamp=True,
          ),
        )
      except ValidationError:  # noqa: E111
        return default

    payload = cast(
      GPSOptions,
      {
        GPS_ENABLED_FIELD: self._coerce_bool(raw.get(GPS_ENABLED_FIELD), True),
        GPS_UPDATE_INTERVAL_FIELD: _safe_gps_interval(
          raw.get(GPS_UPDATE_INTERVAL_FIELD),
          default=DEFAULT_GPS_UPDATE_INTERVAL,
          minimum=5,
          maximum=600,
          field=GPS_UPDATE_INTERVAL_FIELD,
        ),
        GPS_ACCURACY_FILTER_FIELD: _safe_gps_accuracy(
          raw.get(GPS_ACCURACY_FILTER_FIELD),
          default=float(DEFAULT_GPS_ACCURACY_FILTER),
          minimum=5.0,
          maximum=500.0,
          field=GPS_ACCURACY_FILTER_FIELD,
        ),
        GPS_DISTANCE_FILTER_FIELD: _safe_float_range(
          raw.get(GPS_DISTANCE_FILTER_FIELD),
          default=30.0,
          minimum=1.0,
          maximum=2000.0,
          field=GPS_DISTANCE_FILTER_FIELD,
        ),
        ROUTE_RECORDING_FIELD: self._coerce_bool(
          raw.get(ROUTE_RECORDING_FIELD),
          True,
        ),
        ROUTE_HISTORY_DAYS_FIELD: _safe_interval(
          raw.get(ROUTE_HISTORY_DAYS_FIELD),
          default=30,
          minimum=1,
          maximum=365,
          field=ROUTE_HISTORY_DAYS_FIELD,
        ),
        AUTO_TRACK_WALKS_FIELD: self._coerce_bool(
          raw.get(AUTO_TRACK_WALKS_FIELD),
          True,
        ),
      },
    )
    schema_issues = validate_json_schema_payload(
      payload,
      GPS_OPTIONS_JSON_SCHEMA,
    )
    if schema_issues:
      _LOGGER.warning(  # noqa: E111
        "GPS options payload failed JSON schema validation; using defaults: %s",
        [issue.constraint for issue in schema_issues],
      )
      payload = cast(  # noqa: E111
        GPSOptions,
        {
          GPS_ENABLED_FIELD: True,
          GPS_UPDATE_INTERVAL_FIELD: DEFAULT_GPS_UPDATE_INTERVAL,
          GPS_ACCURACY_FILTER_FIELD: float(DEFAULT_GPS_ACCURACY_FILTER),
          GPS_DISTANCE_FILTER_FIELD: float(DEFAULT_GPS_DISTANCE_FILTER),
          ROUTE_RECORDING_FIELD: True,
          ROUTE_HISTORY_DAYS_FIELD: 30,
          AUTO_TRACK_WALKS_FIELD: True,
        },
      )
    return cast(GPSOptions, payload)

  def _normalise_gps_options_snapshot(  # noqa: E111
    self,
    mutable: JSONMutableMapping,
  ) -> GPSOptions | None:
    """Normalise GPS payloads in the options snapshot."""

    gps_settings: GPSOptions | None = None

    if DOG_OPTIONS_FIELD in mutable:
      raw_dog_options = mutable.get(DOG_OPTIONS_FIELD)  # noqa: E111
      typed_dog_options: DogOptionsMap = {}  # noqa: E111
      if isinstance(raw_dog_options, Mapping):  # noqa: E111
        for raw_id, raw_entry in raw_dog_options.items():
          dog_id = str(raw_id)  # noqa: E111
          entry_source = (  # noqa: E111
            cast(Mapping[str, JSONValue], raw_entry)
            if isinstance(raw_entry, Mapping)
            else {}
          )
          entry = ensure_dog_options_entry(  # noqa: E111
            cast(JSONLikeMapping, dict(entry_source)),
            dog_id=dog_id,
          )
          dog_gps = entry.get(GPS_SETTINGS_FIELD)  # noqa: E111
          if isinstance(dog_gps, Mapping):  # noqa: E111
            entry[GPS_SETTINGS_FIELD] = self._normalise_gps_settings(
              cast(Mapping[str, JSONValue], dog_gps),
            )
            gps_settings = entry[GPS_SETTINGS_FIELD]
          if dog_id and entry.get(DOG_ID_FIELD) != dog_id:  # noqa: E111
            entry[DOG_ID_FIELD] = dog_id
          typed_dog_options[dog_id] = entry  # noqa: E111
      mutable[DOG_OPTIONS_FIELD] = cast(JSONValue, typed_dog_options)  # noqa: E111

    if GPS_SETTINGS_FIELD in mutable:
      raw_gps_settings = mutable.get(GPS_SETTINGS_FIELD)  # noqa: E111
      if isinstance(raw_gps_settings, Mapping):  # noqa: E111
        gps_settings = self._normalise_gps_settings(
          cast(Mapping[str, JSONValue], raw_gps_settings),
        )
        mutable[GPS_SETTINGS_FIELD] = cast(JSONValue, gps_settings)

    if gps_settings is not None:
      mutable[CONF_GPS_UPDATE_INTERVAL] = cast(  # noqa: E111
        JSONValue,
        gps_settings[GPS_UPDATE_INTERVAL_FIELD],
      )
      mutable[CONF_GPS_ACCURACY_FILTER] = cast(  # noqa: E111
        JSONValue,
        gps_settings[GPS_ACCURACY_FILTER_FIELD],
      )
      mutable[CONF_GPS_DISTANCE_FILTER] = cast(  # noqa: E111
        JSONValue,
        gps_settings[GPS_DISTANCE_FILTER_FIELD],
      )

    return gps_settings
