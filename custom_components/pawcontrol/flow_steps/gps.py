"""GPS flow helpers for Paw Control configuration and options."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import Any
from typing import cast
from typing import Protocol
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import config_validation as cv

from ..const import CONF_GPS_ACCURACY_FILTER
from ..const import CONF_GPS_DISTANCE_FILTER
from ..const import CONF_GPS_SOURCE
from ..const import CONF_GPS_UPDATE_INTERVAL
from ..const import DEFAULT_GPS_ACCURACY_FILTER
from ..const import DEFAULT_GPS_DISTANCE_FILTER
from ..const import DEFAULT_GPS_UPDATE_INTERVAL
from ..const import MAX_GEOFENCE_RADIUS
from ..const import MIN_GEOFENCE_RADIUS
from ..const import MODULE_FEEDING
from ..const import MODULE_GPS
from ..const import MODULE_HEALTH
from ..const import MODULE_NOTIFICATIONS
from ..const import MODULE_WALK
from ..exceptions import ValidationError
from ..flow_helpers import coerce_bool
from ..flow_validators import validate_flow_gps_coordinates
from ..flow_validators import validate_flow_timer_interval
from ..schemas import GEOFENCE_OPTIONS_JSON_SCHEMA
from ..schemas import GPS_DOG_CONFIG_JSON_SCHEMA
from ..schemas import GPS_OPTIONS_JSON_SCHEMA
from ..schemas import validate_json_schema_payload
from ..types import AddAnotherDogInput
from ..types import AUTO_TRACK_WALKS_FIELD
from ..types import ConfigFlowDiscoveryData
from ..types import ConfigFlowPlaceholders
from ..types import DOG_GPS_CONFIG_FIELD
from ..types import DOG_ID_FIELD
from ..types import DOG_NAME_FIELD
from ..types import DOG_OPTIONS_FIELD
from ..types import DogConfigData
from ..types import DogFeedingStepInput
from ..types import DogGPSConfig
from ..types import DogGPSStepInput
from ..types import DogHealthStepInput
from ..types import DogOptionsMap
from ..types import DogSetupStepInput
from ..types import ensure_dog_modules_config
from ..types import ensure_dog_options_entry
from ..types import GEOFENCE_ALERTS_FIELD
from ..types import GEOFENCE_ENABLED_FIELD
from ..types import GEOFENCE_LAT_FIELD
from ..types import GEOFENCE_LON_FIELD
from ..types import GEOFENCE_RADIUS_FIELD
from ..types import GEOFENCE_RESTRICTED_ZONE_FIELD
from ..types import GEOFENCE_SAFE_ZONE_FIELD
from ..types import GEOFENCE_USE_HOME_FIELD
from ..types import GEOFENCE_ZONE_ENTRY_FIELD
from ..types import GEOFENCE_ZONE_EXIT_FIELD
from ..types import GeofenceOptions
from ..types import GPS_ACCURACY_FILTER_FIELD
from ..types import GPS_DISTANCE_FILTER_FIELD
from ..types import GPS_ENABLED_FIELD
from ..types import GPS_SETTINGS_FIELD
from ..types import GPS_UPDATE_INTERVAL_FIELD
from ..types import GPSOptions
from ..types import JSONLikeMapping
from ..types import JSONMutableMapping
from ..types import JSONValue
from ..types import OptionsDogSelectionInput
from ..types import OptionsGeofenceInput
from ..types import OptionsGPSSettingsInput
from ..types import ROUTE_HISTORY_DAYS_FIELD
from ..types import ROUTE_RECORDING_FIELD
from ..validation import InputValidator
from ..validation import validate_float_range
from ..validation import validate_gps_accuracy_value
from ..validation import validate_gps_interval
from ..validation import validate_gps_source
from ..validation_helpers import safe_validate_interval
from .gps_helpers import build_dog_gps_placeholders
from .gps_helpers import validation_error_key
from .gps_schemas import build_dog_gps_schema
from .gps_schemas import build_geofence_settings_schema
from .gps_schemas import build_gps_settings_schema

_LOGGER = logging.getLogger(__name__)


def _validate_gps_update_interval(
  value: JSONValue | None,
  *,
  field: str,
  minimum: int,
  maximum: int,
) -> int:
  """Validate a required GPS update interval for flow steps."""

  validated = validate_gps_interval(
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    required=True,
  )
  if validated is None:
    # Defensive guard: required=True should return an int or raise.
    raise ValidationError(field, value, "gps_update_interval_required")
  return validated


def _validate_gps_accuracy(
  value: JSONValue | None,
  *,
  field: str,
  minimum: float,
  maximum: float,
) -> float:
  """Validate a required GPS accuracy filter for flow steps."""

  validated = InputValidator.validate_gps_accuracy(
    value,
    required=True,
    field=field,
    min_value=minimum,
    max_value=maximum,
  )
  if validated is None:
    # Defensive guard: required=True should return a float or raise.
    raise ValidationError(field, value, "gps_accuracy_required")
  return validated


class GPSDefaultsHost(Protocol):
  """Protocol describing the config flow host requirements."""

  _discovery_info: ConfigFlowDiscoveryData


class GPSModuleDefaultsMixin(GPSDefaultsHost):
  """Provide GPS-aware defaults for module selection."""

  def _get_enhanced_modules_schema(self, dog_config: DogConfigData) -> vol.Schema:
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

  def _should_enable_gps(self, dog_config: DogConfigData) -> bool:
    """Determine if GPS should be enabled by default.

    Args:
        dog_config: Dog configuration

    Returns:
        True if GPS should be enabled by default
    """
    # Enable GPS for discovered devices or large dogs
    if self._discovery_info:
      return True

    dog_size = dog_config.get("dog_size", "medium")
    return dog_size in {"large", "giant"}

  def _get_smart_module_defaults(self, dog_config: DogConfigData) -> str:
    """Get explanation for smart module defaults.

    Args:
        dog_config: Dog configuration

    Returns:
        Explanation text
    """
    reasons = []

    if self._discovery_info:
      reasons.append("GPS enabled due to discovered tracking device")

    dog_size = dog_config.get("dog_size", "medium")
    if dog_size in {"large", "giant"}:
      reasons.append("GPS recommended for larger dogs")

    return "; ".join(reasons) if reasons else "Standard defaults applied"


if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant

  class DogGPSFlowHost(Protocol):
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
  DogGPSFlowHost = object


class DogGPSFlowMixin(DogGPSFlowHost):
  """Handle GPS configuration steps in the config flow."""

  _current_dog_config: DogConfigData | None

  async def async_step_dog_gps(
    self,
    user_input: DogGPSStepInput | None = None,
  ) -> ConfigFlowResult:
    """Configure GPS settings for the specific dog."""

    current_dog = self._current_dog_config
    if current_dog is None:
      _LOGGER.error(
        "GPS configuration step invoked without active dog; restarting add_dog",
      )
      return await self.async_step_add_dog()

    if user_input is not None:
      errors: dict[str, str] = {}
      try:
        gps_source = validate_gps_source(
          self.hass,
          user_input.get(CONF_GPS_SOURCE),
          field=CONF_GPS_SOURCE,
          allow_manual=True,
        )
      except ValidationError as err:
        if err.constraint == "gps_source_unavailable":
          errors[CONF_GPS_SOURCE] = "gps_entity_unavailable"
        elif err.constraint == "gps_source_not_found":
          errors[CONF_GPS_SOURCE] = "gps_entity_not_found"
        else:
          errors[CONF_GPS_SOURCE] = "required"
        gps_source = "manual"

      try:
        gps_update_interval = _validate_gps_update_interval(
          user_input.get("gps_update_interval"),
          field="gps_update_interval",
          minimum=5,
          maximum=600,
        )
      except ValidationError as err:
        errors["gps_update_interval"] = validation_error_key(
          err,
          "validation_error",
        )
        gps_update_interval = DEFAULT_GPS_UPDATE_INTERVAL

      try:
        gps_accuracy = _validate_gps_accuracy(
          user_input.get("gps_accuracy_filter"),
          field="gps_accuracy_filter",
          minimum=5.0,
          maximum=500.0,
        )
      except ValidationError as err:
        errors["gps_accuracy_filter"] = validation_error_key(
          err,
          "validation_error",
        )
        gps_accuracy = DEFAULT_GPS_ACCURACY_FILTER

      try:
        home_zone_radius = InputValidator.validate_geofence_radius(
          user_input.get("home_zone_radius"),
          required=True,
          field="home_zone_radius",
          min_value=10.0,
          max_value=500.0,
        )
      except ValidationError as err:
        errors["home_zone_radius"] = validation_error_key(
          err,
          "validation_error",
        )
        home_zone_radius = 50.0

      if errors:
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

      home_zone_radius = home_zone_radius if home_zone_radius is not None else 50.0

      gps_config: DogGPSConfig = {
        "gps_source": gps_source,
        "gps_update_interval": gps_update_interval,
        "gps_accuracy_filter": gps_accuracy,
        "enable_geofencing": coerce_bool(
          user_input.get("enable_geofencing"),
          default=True,
        ),
        "home_zone_radius": home_zone_radius,
      }
      schema_issues = validate_json_schema_payload(
        gps_config,
        GPS_DOG_CONFIG_JSON_SCHEMA,
      )
      if schema_issues:
        _LOGGER.error(
          "GPS config failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )
      current_dog[DOG_GPS_CONFIG_FIELD] = gps_config

      modules = ensure_dog_modules_config(current_dog)
      if modules.get(MODULE_HEALTH, False):
        return await self.async_step_dog_health()
      return await self.async_step_dog_feeding()

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

  def _get_dog_gps_schema(self) -> vol.Schema:
    """Build the schema for GPS configuration."""

    gps_sources = self._get_available_device_trackers()
    return build_dog_gps_schema(gps_sources)


if TYPE_CHECKING:

  class GPSOptionsHost(Protocol):
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
  from ..options_flow_shared import OptionsFlowSharedMixin

  class GPSOptionsHost(OptionsFlowSharedMixin):
    """Runtime host for GPS options mixin."""

    pass


class GPSOptionsMixin(GPSOptionsHost):
  _current_dog_config: DogConfigData | None
  """Handle per-dog GPS and geofencing options."""

  def _current_gps_options(self, dog_id: str) -> GPSOptions:
    """Return the stored GPS configuration with legacy fallbacks."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get(GPS_SETTINGS_FIELD)
    if isinstance(raw, Mapping):
      current = cast(GPSOptions, dict(raw))
    else:
      legacy = self._current_options().get(GPS_SETTINGS_FIELD, {})
      current = (
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
      if isinstance(interval, int):
        current[GPS_UPDATE_INTERVAL_FIELD] = interval
      elif isinstance(interval, float):
        current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)
      elif isinstance(interval, str):
        with suppress(ValueError):
          current[GPS_UPDATE_INTERVAL_FIELD] = int(interval)

    if (
      GPS_ACCURACY_FILTER_FIELD not in current
      and (accuracy := self._current_options().get(CONF_GPS_ACCURACY_FILTER))
      is not None
    ):
      if isinstance(accuracy, int | float):
        current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)
      elif isinstance(accuracy, str):
        with suppress(ValueError):
          current[GPS_ACCURACY_FILTER_FIELD] = float(accuracy)

    if (
      GPS_DISTANCE_FILTER_FIELD not in current
      and (distance := self._current_options().get(CONF_GPS_DISTANCE_FILTER))
      is not None
    ):
      if isinstance(distance, int | float):
        current[GPS_DISTANCE_FILTER_FIELD] = float(distance)
      elif isinstance(distance, str):
        with suppress(ValueError):
          current[GPS_DISTANCE_FILTER_FIELD] = float(distance)

    return self._normalise_gps_settings(current)

  def _current_geofence_options(self, dog_id: str) -> GeofenceOptions:
    """Fetch the stored geofence configuration as a typed mapping."""

    dog_options = self._current_dog_options()
    entry = dog_options.get(dog_id, {})
    raw = entry.get("geofence_settings")
    if isinstance(raw, Mapping):
      return cast(GeofenceOptions, dict(raw))

    legacy = self._current_options().get("geofence_settings", {})
    if isinstance(legacy, Mapping):
      return cast(GeofenceOptions, dict(legacy))

    return cast(GeofenceOptions, {})

  async def async_step_select_dog_for_gps_settings(
    self,
    user_input: OptionsDogSelectionInput | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure GPS settings for."""

    if not self._dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._select_dog_by_id(
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:
        return await self.async_step_gps_settings()
      return await self.async_step_init()

    return self.async_show_form(
      step_id="select_dog_for_gps_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_select_dog_for_geofence_settings(
    self,
    user_input: OptionsDogSelectionInput | None = None,
  ) -> ConfigFlowResult:
    """Select which dog to configure geofencing for."""

    if not self._dogs:
      return await self.async_step_init()

    if user_input is not None:
      selected_dog_id = user_input.get("dog_id")
      self._select_dog_by_id(
        selected_dog_id if isinstance(selected_dog_id, str) else None,
      )
      if self._current_dog:
        return await self.async_step_geofence_settings()
      return await self.async_step_init()

    return self.async_show_form(
      step_id="select_dog_for_geofence_settings",
      data_schema=self._build_dog_selector_schema(),
    )

  async def async_step_gps_settings(
    self,
    user_input: OptionsGPSSettingsInput | None = None,
  ) -> ConfigFlowResult:
    """Configure GPS settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_gps_settings()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_gps_settings()

    current_options = self._current_gps_options(dog_id)
    if user_input is not None:
      errors: dict[str, str] = {}

      try:
        gps_update_interval = _validate_gps_update_interval(
          user_input.get(GPS_UPDATE_INTERVAL_FIELD),
          field=GPS_UPDATE_INTERVAL_FIELD,
          minimum=5,
          maximum=600,
        )
      except ValidationError as err:
        errors[GPS_UPDATE_INTERVAL_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        gps_update_interval = DEFAULT_GPS_UPDATE_INTERVAL

      try:
        gps_accuracy = _validate_gps_accuracy(
          user_input.get(GPS_ACCURACY_FILTER_FIELD),
          field=GPS_ACCURACY_FILTER_FIELD,
          minimum=5.0,
          maximum=500.0,
        )
      except ValidationError as err:
        errors[GPS_ACCURACY_FILTER_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        gps_accuracy = DEFAULT_GPS_ACCURACY_FILTER

      try:
        gps_distance = validate_float_range(
          user_input.get(GPS_DISTANCE_FILTER_FIELD),
          field=GPS_DISTANCE_FILTER_FIELD,
          minimum=1.0,
          maximum=2000.0,
          required=True,
        )
      except ValidationError:
        errors[GPS_DISTANCE_FILTER_FIELD] = "invalid_configuration"
        gps_distance = DEFAULT_GPS_DISTANCE_FILTER

      try:
        route_history = validate_flow_timer_interval(
          user_input.get(ROUTE_HISTORY_DAYS_FIELD),
          field=ROUTE_HISTORY_DAYS_FIELD,
          minimum=1,
          maximum=365,
          required=True,
        )
      except ValidationError:
        errors[ROUTE_HISTORY_DAYS_FIELD] = "invalid_configuration"
        route_history = 30

      if errors:
        return self.async_show_form(
          step_id="gps_settings",
          data_schema=self._build_gps_settings_schema(current_options),
          errors=errors,
        )

      current_options = cast(
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

      schema_issues = validate_json_schema_payload(
        current_options,
        GPS_OPTIONS_JSON_SCHEMA,
      )
      if schema_issues:
        _LOGGER.error(
          "GPS options failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )

      updated_options = self._clone_options()
      dog_options = self._current_dog_options()
      dog_entry = ensure_dog_options_entry(
        cast(
          JSONLikeMapping,
          dict(dog_options.get(dog_id, {})),
        ),
        dog_id=dog_id,
      )
      dog_entry[GPS_SETTINGS_FIELD] = current_options
      dog_entry[DOG_ID_FIELD] = dog_id
      dog_options[dog_id] = dog_entry
      updated_options[DOG_OPTIONS_FIELD] = cast(JSONValue, dog_options)
      updated_options[GPS_SETTINGS_FIELD] = cast(
        JSONValue,
        current_options,
      )

      return self.async_create_entry(
        title="GPS settings updated",
        data=self._normalise_options_snapshot(updated_options),
      )

    return self.async_show_form(
      step_id="gps_settings",
      data_schema=self._build_gps_settings_schema(current_options),
    )

  def _build_gps_settings_schema(
    self,
    current_options: GPSOptions,
  ) -> vol.Schema:
    """Build schema for GPS settings."""

    return build_gps_settings_schema(current_options)

  async def async_step_geofence_settings(
    self,
    user_input: OptionsGeofenceInput | None = None,
  ) -> ConfigFlowResult:
    """Configure geofencing settings."""

    explicit_current_dog = self._current_dog is not None
    current_dog = self._require_current_dog()
    dog_id: str | None = None
    if current_dog is not None and explicit_current_dog:
      current_dog_id = current_dog.get(DOG_ID_FIELD)
      if isinstance(current_dog_id, str):
        dog_id = current_dog_id

    if dog_id is not None:
      current_options = self._current_geofence_options(dog_id)
    else:
      legacy_options = self._current_options().get("geofence_settings", {})
      current_options = (
        cast(GeofenceOptions, dict(legacy_options))
        if isinstance(legacy_options, Mapping)
        else cast(GeofenceOptions, {})
      )

    if user_input is not None:
      errors: dict[str, str] = {}

      try:
        geofence_radius = InputValidator.validate_geofence_radius(
          user_input.get(GEOFENCE_RADIUS_FIELD),
          required=True,
          field=GEOFENCE_RADIUS_FIELD,
          min_value=float(MIN_GEOFENCE_RADIUS),
          max_value=float(MAX_GEOFENCE_RADIUS),
        )
      except ValidationError as err:
        errors[GEOFENCE_RADIUS_FIELD] = validation_error_key(
          err,
          "invalid_configuration",
        )
        geofence_radius = current_options.get(GEOFENCE_RADIUS_FIELD, 100.0)

      geofence_lat: float | None
      geofence_lon: float | None
      try:
        geofence_lat, geofence_lon = validate_flow_gps_coordinates(
          user_input.get(GEOFENCE_LAT_FIELD),
          user_input.get(GEOFENCE_LON_FIELD),
          latitude_field=GEOFENCE_LAT_FIELD,
          longitude_field=GEOFENCE_LON_FIELD,
        )
      except ValidationError as err:
        errors[err.field] = validation_error_key(
          err,
          "invalid_configuration",
        )
        geofence_lat = current_options.get(GEOFENCE_LAT_FIELD)
        geofence_lon = current_options.get(GEOFENCE_LON_FIELD)

      if errors:
        return self.async_show_form(
          step_id="geofence_settings",
          data_schema=self._build_geofence_settings_schema(current_options),
          errors=errors,
        )

      geofence_options = cast(
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
          GEOFENCE_RADIUS_FIELD: int(round(float(geofence_radius))),
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

      schema_issues = validate_json_schema_payload(
        geofence_options,
        GEOFENCE_OPTIONS_JSON_SCHEMA,
      )
      if schema_issues:
        _LOGGER.error(
          "Geofence options failed JSON schema validation: %s",
          [issue.constraint for issue in schema_issues],
        )

      updated_options = self._clone_options()
      updated_options["geofence_settings"] = cast(JSONValue, geofence_options)
      if dog_id is not None:
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

      return self.async_create_entry(
        title="Geofence settings updated",
        data=self._normalise_options_snapshot(updated_options),
      )

    return self.async_show_form(
      step_id="geofence_settings",
      data_schema=self._build_geofence_settings_schema(current_options),
    )

  def _build_geofence_settings_schema(
    self,
    current_options: GeofenceOptions,
  ) -> vol.Schema:
    """Build schema for geofence settings."""

    return build_geofence_settings_schema(current_options)


class GPSOptionsNormalizerHost(Protocol):
  """Protocol describing the options flow host requirements."""

  def _coerce_bool(self, value: Any, default: bool) -> bool: ...


class GPSOptionsNormalizerMixin(GPSOptionsNormalizerHost):
  """Mixin providing GPS normalization for options payloads."""

  @staticmethod
  def _coerce_bool(value: Any, default: bool) -> bool:
    """Return a boolean using Home Assistant style truthiness rules."""

    if value is None:
      return default
    if isinstance(value, bool):
      return value
    if isinstance(value, str):
      return value.strip().lower() in {"1", "true", "on", "yes"}
    return bool(value)

  def _normalise_gps_settings(self, raw: Mapping[str, JSONValue]) -> GPSOptions:
    """Return a normalised GPS options payload."""

    def _safe_interval(
      value: JSONValue | None,
      *,
      default: int,
      minimum: int,
      maximum: int,
      field: str,
    ) -> int:
      return safe_validate_interval(
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
      try:
        return validate_float_range(
          value,
          field=field,
          minimum=minimum,
          maximum=maximum,
          default=default,
          clamp=True,
        )
      except ValidationError:
        return default

    def _safe_gps_interval(
      value: JSONValue | None,
      *,
      default: int,
      minimum: int,
      maximum: int,
      field: str,
    ) -> int:
      try:
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
      except ValidationError:
        return default

    def _safe_gps_accuracy(
      value: JSONValue | None,
      *,
      default: float,
      minimum: float,
      maximum: float,
      field: str,
    ) -> float:
      try:
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
      except ValidationError:
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
          default=float(DEFAULT_GPS_DISTANCE_FILTER),
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
      _LOGGER.warning(
        "GPS options payload failed JSON schema validation; using defaults: %s",
        [issue.constraint for issue in schema_issues],
      )
      payload = cast(
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

  def _normalise_gps_options_snapshot(
    self,
    mutable: JSONMutableMapping,
  ) -> GPSOptions | None:
    """Normalise GPS payloads in the options snapshot."""

    gps_settings: GPSOptions | None = None

    if DOG_OPTIONS_FIELD in mutable:
      raw_dog_options = mutable.get(DOG_OPTIONS_FIELD)
      typed_dog_options: DogOptionsMap = {}
      if isinstance(raw_dog_options, Mapping):
        for raw_id, raw_entry in raw_dog_options.items():
          dog_id = str(raw_id)
          entry_source = (
            cast(Mapping[str, JSONValue], raw_entry)
            if isinstance(raw_entry, Mapping)
            else {}
          )
          entry = ensure_dog_options_entry(
            cast(JSONLikeMapping, dict(entry_source)),
            dog_id=dog_id,
          )
          dog_gps = entry.get(GPS_SETTINGS_FIELD)
          if isinstance(dog_gps, Mapping):
            entry[GPS_SETTINGS_FIELD] = self._normalise_gps_settings(
              cast(Mapping[str, JSONValue], dog_gps),
            )
            gps_settings = entry[GPS_SETTINGS_FIELD]
          if dog_id and entry.get(DOG_ID_FIELD) != dog_id:
            entry[DOG_ID_FIELD] = dog_id
          typed_dog_options[dog_id] = entry
      mutable[DOG_OPTIONS_FIELD] = cast(JSONValue, typed_dog_options)

    if GPS_SETTINGS_FIELD in mutable:
      raw_gps_settings = mutable.get(GPS_SETTINGS_FIELD)
      if isinstance(raw_gps_settings, Mapping):
        gps_settings = self._normalise_gps_settings(
          cast(Mapping[str, JSONValue], raw_gps_settings),
        )
        mutable[GPS_SETTINGS_FIELD] = cast(JSONValue, gps_settings)

    if gps_settings is not None:
      mutable[CONF_GPS_UPDATE_INTERVAL] = cast(
        JSONValue,
        gps_settings[GPS_UPDATE_INTERVAL_FIELD],
      )
      mutable[CONF_GPS_ACCURACY_FILTER] = cast(
        JSONValue,
        gps_settings[GPS_ACCURACY_FILTER_FIELD],
      )
      mutable[CONF_GPS_DISTANCE_FILTER] = cast(
        JSONValue,
        gps_settings[GPS_DISTANCE_FILTER_FIELD],
      )

    return gps_settings
