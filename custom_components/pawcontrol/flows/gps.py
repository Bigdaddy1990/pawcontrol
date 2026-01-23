"""GPS and geofencing flow mixins for Paw Control."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, Any, Protocol, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigFlowResult

from ..const import (
  CONF_GPS_ACCURACY_FILTER,
  CONF_GPS_DISTANCE_FILTER,
  CONF_GPS_SOURCE,
  CONF_GPS_UPDATE_INTERVAL,
  DEFAULT_GPS_ACCURACY_FILTER,
  DEFAULT_GPS_DISTANCE_FILTER,
  DEFAULT_GPS_UPDATE_INTERVAL,
  GPS_ACCURACY_FILTER_SELECTOR,
  GPS_UPDATE_INTERVAL_SELECTOR,
  MAX_GEOFENCE_RADIUS,
  MIN_GEOFENCE_RADIUS,
  MODULE_FEEDING,
  MODULE_HEALTH,
)
from ..exceptions import ValidationError
from ..flow_helpers import coerce_bool
from ..selector_shim import selector
from ..types import (
  AUTO_TRACK_WALKS_FIELD,
  DOG_GPS_PLACEHOLDERS_TEMPLATE,
  DOG_GPS_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DOG_OPTIONS_FIELD,
  ConfigFlowPlaceholders,
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
  DogConfigData,
  DogGPSConfig,
  DogOptionsMap,
  GeofenceOptions,
  GPSOptions,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  OptionsGeofenceInput,
  clone_placeholders,
  ensure_dog_modules_config,
  ensure_dog_options_entry,
  freeze_placeholders,
)
from ..validators import (
  validate_coordinate,
  validate_gps_source,
  validate_radius,
  validate_timer,
)

_LOGGER = logging.getLogger(__name__)


def _build_dog_gps_placeholders(*, dog_name: str) -> ConfigFlowPlaceholders:
  """Return immutable placeholders for the GPS configuration step."""

  placeholders = clone_placeholders(DOG_GPS_PLACEHOLDERS_TEMPLATE)
  placeholders["dog_name"] = dog_name
  return freeze_placeholders(placeholders)


if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant

  class DogGPSFlowHost(Protocol):
    _current_dog_config: DogConfigData | None
    _dogs: list[DogConfigData]
    hass: HomeAssistant

    def _get_available_device_trackers(self) -> dict[str, str]: ...

    def _get_available_person_entities(self) -> dict[str, str]: ...

    async def async_step_add_dog(self) -> ConfigFlowResult: ...

    async def async_step_dog_feeding(self) -> ConfigFlowResult: ...

    async def async_step_dog_health(self) -> ConfigFlowResult: ...

    async def async_step_add_another_dog(self) -> ConfigFlowResult: ...

    def async_show_form(
      self,
      *,
      step_id: str,
      data_schema: vol.Schema,
      errors: dict[str, str] | None = None,
      description_placeholders: Mapping[str, str] | None = None,
    ) -> ConfigFlowResult: ...

else:  # pragma: no cover
  DogGPSFlowHost = object


class DogGPSFlowMixin(DogGPSFlowHost):
  """Handle GPS configuration steps in the config flow."""

  async def async_step_dog_gps(
    self,
    user_input: dict[str, Any] | None = None,
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
        gps_update_interval = validate_timer(
          user_input.get("gps_update_interval"),
          field="gps_update_interval",
          min_value=5,
          max_value=600,
        )
      except ValidationError:
        errors["gps_update_interval"] = "invalid_interval"
        gps_update_interval = DEFAULT_GPS_UPDATE_INTERVAL

      try:
        gps_accuracy = validate_radius(
          user_input.get("gps_accuracy_filter"),
          field="gps_accuracy_filter",
          min_value=5,
          max_value=500,
        )
      except ValidationError:
        errors["gps_accuracy_filter"] = "invalid_accuracy"
        gps_accuracy = DEFAULT_GPS_ACCURACY_FILTER

      try:
        home_zone_radius = validate_radius(
          user_input.get("home_zone_radius"),
          field="home_zone_radius",
          min_value=10,
          max_value=500,
        )
      except ValidationError:
        errors["home_zone_radius"] = "radius_out_of_range"
        home_zone_radius = 50.0

      if errors:
        return self.async_show_form(
          step_id="dog_gps",
          data_schema=self._get_dog_gps_schema(),
          errors=errors,
          description_placeholders=dict(
            _build_dog_gps_placeholders(
              dog_name=current_dog[DOG_NAME_FIELD],
            ),
          ),
        )

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

      current_dog[DOG_GPS_CONFIG_FIELD] = gps_config

      modules = ensure_dog_modules_config(current_dog)
      if modules.get(MODULE_FEEDING, False):
        return await self.async_step_dog_feeding()
      if modules.get(MODULE_HEALTH, False):
        return await self.async_step_dog_health()

      self._dogs.append(current_dog)
      self._current_dog_config = None
      return await self.async_step_add_another_dog()

    return self.async_show_form(
      step_id="dog_gps",
      data_schema=self._get_dog_gps_schema(),
      description_placeholders=dict(
        _build_dog_gps_placeholders(dog_name=current_dog[DOG_NAME_FIELD]),
      ),
    )

  def _get_dog_gps_schema(self) -> vol.Schema:
    """Return the GPS configuration schema for the current dog."""

    device_trackers = self._get_available_device_trackers()
    person_entities = self._get_available_person_entities()

    gps_options: list[str | dict[str, str]] = ["manual"]
    if device_trackers:
      gps_options.extend(device_trackers.keys())
    if person_entities:
      gps_options.extend(person_entities.keys())
    gps_options.extend(["webhook", "mqtt", "tractive"])

    return vol.Schema(
      {
        vol.Required(
          CONF_GPS_SOURCE,
          default="manual",
        ): selector.SelectSelector(
          selector.SelectSelectorConfig(
            options=gps_options,
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="gps_source",
          ),
        ),
        vol.Optional(
          "gps_update_interval",
          default=DEFAULT_GPS_UPDATE_INTERVAL,
        ): GPS_UPDATE_INTERVAL_SELECTOR,
        vol.Optional(
          "gps_accuracy_filter",
          default=DEFAULT_GPS_ACCURACY_FILTER,
        ): GPS_ACCURACY_FILTER_SELECTOR,
        vol.Optional(
          "enable_geofencing",
          default=True,
        ): selector.BooleanSelector(),
        vol.Optional("home_zone_radius", default=50): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=10,
            max=500,
            step=10,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="meters",
          ),
        ),
      },
    )


if TYPE_CHECKING:

  class GPSOptionsHost:
    _current_dog: DogConfigData | None
    _dogs: list[DogConfigData]
    hass: HomeAssistant

    def _clone_options(self) -> dict[str, JSONValue]: ...

    def _current_dog_options(self) -> DogOptionsMap: ...

    def _current_options(self) -> Mapping[str, JSONValue]: ...

    def _normalise_options_snapshot(
      self,
      options: Mapping[str, JSONValue] | JSONMutableMapping,
    ) -> Mapping[str, JSONValue]: ...

    def _build_dog_selector_schema(self) -> vol.Schema: ...

    def _require_current_dog(self) -> DogConfigData | None: ...

    def _select_dog_by_id(
      self,
      dog_id: str | None,
    ) -> DogConfigData | None: ...

    def _coerce_bool(self, value: Any, default: bool) -> bool: ...

    def _coerce_optional_float(
      self,
      value: Any,
      default: float | None,
    ) -> float | None: ...

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

    current.setdefault(GPS_ENABLED_FIELD, True)
    current.setdefault(ROUTE_RECORDING_FIELD, True)
    current.setdefault(ROUTE_HISTORY_DAYS_FIELD, 30)
    current.setdefault(AUTO_TRACK_WALKS_FIELD, True)

    return current

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
    user_input: dict[str, Any] | None = None,
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
    user_input: dict[str, Any] | None = None,
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
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure per-dog GPS tracking settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_gps_settings()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_gps_settings()

    if user_input is not None:
      try:
        current_settings = self._current_gps_options(dog_id)
        typed_input = cast(dict[str, Any], user_input)
        interval = validate_timer(
          typed_input.get(GPS_UPDATE_INTERVAL_FIELD),
          field=GPS_UPDATE_INTERVAL_FIELD,
          min_value=5,
          max_value=600,
        )
        accuracy = validate_radius(
          typed_input.get(GPS_ACCURACY_FILTER_FIELD),
          field=GPS_ACCURACY_FILTER_FIELD,
          min_value=5,
          max_value=500,
        )
        distance = validate_radius(
          typed_input.get(GPS_DISTANCE_FILTER_FIELD),
          field=GPS_DISTANCE_FILTER_FIELD,
          min_value=1,
          max_value=2000,
        )

        new_settings: GPSOptions = {
          GPS_ENABLED_FIELD: self._coerce_bool(
            typed_input.get(GPS_ENABLED_FIELD),
            current_settings.get(GPS_ENABLED_FIELD, True),
          ),
          GPS_UPDATE_INTERVAL_FIELD: interval,
          GPS_ACCURACY_FILTER_FIELD: accuracy,
          GPS_DISTANCE_FILTER_FIELD: distance,
          ROUTE_RECORDING_FIELD: self._coerce_bool(
            typed_input.get(ROUTE_RECORDING_FIELD),
            current_settings.get(ROUTE_RECORDING_FIELD, True),
          ),
          ROUTE_HISTORY_DAYS_FIELD: cast(
            int,
            typed_input.get(
              ROUTE_HISTORY_DAYS_FIELD,
              current_settings.get(ROUTE_HISTORY_DAYS_FIELD, 30),
            ),
          ),
          AUTO_TRACK_WALKS_FIELD: self._coerce_bool(
            typed_input.get(AUTO_TRACK_WALKS_FIELD),
            current_settings.get(AUTO_TRACK_WALKS_FIELD, True),
          ),
        }

        new_options = self._clone_options()
        dog_options = self._current_dog_options()
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
          dog_id=dog_id,
        )
        entry[GPS_SETTINGS_FIELD] = new_settings
        if dog_id in dog_options or not dog_options:
          dog_options[dog_id] = entry
          new_options[DOG_OPTIONS_FIELD] = dog_options
        new_options[GPS_SETTINGS_FIELD] = new_settings

        typed_options = self._normalise_options_snapshot(new_options)
        return self.async_create_entry(title="", data=typed_options)

      except ValidationError:
        return self.async_show_form(
          step_id="gps_settings",
          data_schema=self._get_gps_settings_schema(dog_id, user_input),
          errors={"base": "invalid_configuration"},
        )

    return self.async_show_form(
      step_id="gps_settings",
      data_schema=self._get_gps_settings_schema(dog_id),
    )

  def _get_gps_settings_schema(
    self,
    dog_id: str,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get GPS settings schema with current values."""

    current = self._current_gps_options(dog_id)
    current_values = user_input or {}

    return vol.Schema(
      {
        vol.Optional(
          GPS_ENABLED_FIELD,
          default=current_values.get(
            GPS_ENABLED_FIELD,
            current.get(GPS_ENABLED_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GPS_UPDATE_INTERVAL_FIELD,
          default=current_values.get(
            GPS_UPDATE_INTERVAL_FIELD,
            current.get(GPS_UPDATE_INTERVAL_FIELD, DEFAULT_GPS_UPDATE_INTERVAL),
          ),
        ): GPS_UPDATE_INTERVAL_SELECTOR,
        vol.Optional(
          GPS_ACCURACY_FILTER_FIELD,
          default=current_values.get(
            GPS_ACCURACY_FILTER_FIELD,
            current.get(GPS_ACCURACY_FILTER_FIELD, DEFAULT_GPS_ACCURACY_FILTER),
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=5,
            max=500,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="meters",
          ),
        ),
        vol.Optional(
          GPS_DISTANCE_FILTER_FIELD,
          default=current_values.get(
            GPS_DISTANCE_FILTER_FIELD,
            current.get(GPS_DISTANCE_FILTER_FIELD, DEFAULT_GPS_DISTANCE_FILTER),
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=1,
            max=2000,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="meters",
          ),
        ),
        vol.Optional(
          ROUTE_RECORDING_FIELD,
          default=current_values.get(
            ROUTE_RECORDING_FIELD,
            current.get(ROUTE_RECORDING_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          ROUTE_HISTORY_DAYS_FIELD,
          default=current_values.get(
            ROUTE_HISTORY_DAYS_FIELD,
            current.get(ROUTE_HISTORY_DAYS_FIELD, 30),
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=1,
            max=365,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="days",
          ),
        ),
        vol.Optional(
          AUTO_TRACK_WALKS_FIELD,
          default=current_values.get(
            AUTO_TRACK_WALKS_FIELD,
            current.get(AUTO_TRACK_WALKS_FIELD, True),
          ),
        ): selector.BooleanSelector(),
      },
    )

  async def async_step_geofence_settings(
    self,
    user_input: dict[str, Any] | None = None,
  ) -> ConfigFlowResult:
    """Configure geofencing and zone settings."""

    current_dog = self._require_current_dog()
    if current_dog is None:
      return await self.async_step_select_dog_for_geofence_settings()

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return await self.async_step_select_dog_for_geofence_settings()

    if user_input is not None:
      try:
        typed_input = cast(OptionsGeofenceInput, dict(user_input))
        radius = validate_radius(
          typed_input.get(GEOFENCE_RADIUS_FIELD),
          field=GEOFENCE_RADIUS_FIELD,
          min_value=MIN_GEOFENCE_RADIUS,
          max_value=MAX_GEOFENCE_RADIUS,
        )
        new_options = self._clone_options()
        current_geofence = self._current_geofence_options(dog_id)
        default_lat = (
          float(self.hass.config.latitude)
          if self.hass.config.latitude is not None
          else None
        )
        default_lon = (
          float(self.hass.config.longitude)
          if self.hass.config.longitude is not None
          else None
        )
        lat = validate_coordinate(
          typed_input.get(GEOFENCE_LAT_FIELD),
          field=GEOFENCE_LAT_FIELD,
          min_value=-90.0,
          max_value=90.0,
          allow_none=True,
        )
        lon = validate_coordinate(
          typed_input.get(GEOFENCE_LON_FIELD),
          field=GEOFENCE_LON_FIELD,
          min_value=-180.0,
          max_value=180.0,
          allow_none=True,
        )

        dog_options = self._current_dog_options()
        entry = ensure_dog_options_entry(
          cast(JSONLikeMapping, dict(dog_options.get(dog_id, {}))),
          dog_id=dog_id,
        )
        entry["geofence_settings"] = self._build_geofence_settings(
          typed_input,
          current_geofence,
          radius=int(radius),
          default_lat=lat if lat is not None else default_lat,
          default_lon=lon if lon is not None else default_lon,
        )
        if dog_id in dog_options or not dog_options:
          dog_options[dog_id] = entry
          new_options[DOG_OPTIONS_FIELD] = dog_options
        new_options["geofence_settings"] = entry["geofence_settings"]

        typed_options = self._normalise_options_snapshot(new_options)

        return self.async_create_entry(title="", data=typed_options)

      except ValidationError as err:
        error_key = "invalid_configuration"
        if err.constraint == "coordinate_out_of_range":
          error_key = "invalid_configuration"
        if err.field == GEOFENCE_RADIUS_FIELD:
          return self.async_show_form(
            step_id="geofence_settings",
            data_schema=self._get_geofence_settings_schema(
              dog_id,
              user_input,
            ),
            errors={GEOFENCE_RADIUS_FIELD: "radius_out_of_range"},
          )
        if err.field in {GEOFENCE_LAT_FIELD, GEOFENCE_LON_FIELD}:
          return self.async_show_form(
            step_id="geofence_settings",
            data_schema=self._get_geofence_settings_schema(
              dog_id,
              user_input,
            ),
            errors={err.field: error_key},
          )
        return self.async_show_form(
          step_id="geofence_settings",
          data_schema=self._get_geofence_settings_schema(
            dog_id,
            user_input,
          ),
          errors={"base": error_key},
        )
      except Exception:
        return self.async_show_form(
          step_id="geofence_settings",
          data_schema=self._get_geofence_settings_schema(
            dog_id,
            user_input,
          ),
          errors={"base": "geofence_update_failed"},
        )

    return self.async_show_form(
      step_id="geofence_settings",
      data_schema=self._get_geofence_settings_schema(dog_id),
      description_placeholders=dict(
        self._get_geofence_description_placeholders(),
      ),
    )

  def _get_geofence_settings_schema(
    self,
    dog_id: str,
    user_input: dict[str, Any] | None = None,
  ) -> vol.Schema:
    """Get geofencing settings schema with current values."""

    current_geofence = self._current_geofence_options(dog_id)
    current_values = user_input or {}

    default_lat = current_geofence.get(GEOFENCE_LAT_FIELD)
    default_lon = current_geofence.get(GEOFENCE_LON_FIELD)

    return vol.Schema(
      {
        vol.Optional(
          GEOFENCE_ENABLED_FIELD,
          default=current_values.get(
            GEOFENCE_ENABLED_FIELD,
            current_geofence.get(GEOFENCE_ENABLED_FIELD, False),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_USE_HOME_FIELD,
          default=current_values.get(
            GEOFENCE_USE_HOME_FIELD,
            current_geofence.get(GEOFENCE_USE_HOME_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_LAT_FIELD,
          default=current_values.get(
            GEOFENCE_LAT_FIELD,
            default_lat,
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=-90,
            max=90,
            step=0.000001,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="°",
          ),
        ),
        vol.Optional(
          GEOFENCE_LON_FIELD,
          default=current_values.get(
            GEOFENCE_LON_FIELD,
            default_lon,
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=-180,
            max=180,
            step=0.000001,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="°",
          ),
        ),
        vol.Optional(
          GEOFENCE_RADIUS_FIELD,
          default=current_values.get(
            GEOFENCE_RADIUS_FIELD,
            current_geofence.get(GEOFENCE_RADIUS_FIELD, 50),
          ),
        ): selector.NumberSelector(
          selector.NumberSelectorConfig(
            min=MIN_GEOFENCE_RADIUS,
            max=MAX_GEOFENCE_RADIUS,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="meters",
          ),
        ),
        vol.Optional(
          GEOFENCE_ALERTS_FIELD,
          default=current_values.get(
            GEOFENCE_ALERTS_FIELD,
            current_geofence.get(GEOFENCE_ALERTS_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_SAFE_ZONE_FIELD,
          default=current_values.get(
            GEOFENCE_SAFE_ZONE_FIELD,
            current_geofence.get(GEOFENCE_SAFE_ZONE_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_RESTRICTED_ZONE_FIELD,
          default=current_values.get(
            GEOFENCE_RESTRICTED_ZONE_FIELD,
            current_geofence.get(
              GEOFENCE_RESTRICTED_ZONE_FIELD,
              True,
            ),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_ZONE_ENTRY_FIELD,
          default=current_values.get(
            GEOFENCE_ZONE_ENTRY_FIELD,
            current_geofence.get(GEOFENCE_ZONE_ENTRY_FIELD, True),
          ),
        ): selector.BooleanSelector(),
        vol.Optional(
          GEOFENCE_ZONE_EXIT_FIELD,
          default=current_values.get(
            GEOFENCE_ZONE_EXIT_FIELD,
            current_geofence.get(GEOFENCE_ZONE_EXIT_FIELD, True),
          ),
        ): selector.BooleanSelector(),
      },
    )

  def _build_geofence_settings(
    self,
    user_input: OptionsGeofenceInput,
    current: GeofenceOptions,
    *,
    radius: int,
    default_lat: float | None,
    default_lon: float | None,
  ) -> GeofenceOptions:
    """Create a typed geofence payload from the submitted form data."""

    lat_source = user_input.get(GEOFENCE_LAT_FIELD)
    lon_source = user_input.get(GEOFENCE_LON_FIELD)
    lat = self._coerce_optional_float(
      lat_source,
      current.get(GEOFENCE_LAT_FIELD, default_lat),
    )
    lon = self._coerce_optional_float(
      lon_source,
      current.get(GEOFENCE_LON_FIELD, default_lon),
    )

    geofence: GeofenceOptions = {
      GEOFENCE_ENABLED_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_ENABLED_FIELD),
        current.get(GEOFENCE_ENABLED_FIELD, False),
      ),
      GEOFENCE_USE_HOME_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_USE_HOME_FIELD),
        current.get(GEOFENCE_USE_HOME_FIELD, True),
      ),
      GEOFENCE_LAT_FIELD: lat,
      GEOFENCE_LON_FIELD: lon,
      GEOFENCE_RADIUS_FIELD: radius,
      GEOFENCE_ALERTS_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_ALERTS_FIELD),
        current.get(GEOFENCE_ALERTS_FIELD, True),
      ),
      GEOFENCE_SAFE_ZONE_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_SAFE_ZONE_FIELD),
        current.get(GEOFENCE_SAFE_ZONE_FIELD, True),
      ),
      GEOFENCE_RESTRICTED_ZONE_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_RESTRICTED_ZONE_FIELD),
        current.get(GEOFENCE_RESTRICTED_ZONE_FIELD, True),
      ),
      GEOFENCE_ZONE_ENTRY_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_ZONE_ENTRY_FIELD),
        current.get(GEOFENCE_ZONE_ENTRY_FIELD, True),
      ),
      GEOFENCE_ZONE_EXIT_FIELD: self._coerce_bool(
        user_input.get(GEOFENCE_ZONE_EXIT_FIELD),
        current.get(GEOFENCE_ZONE_EXIT_FIELD, True),
      ),
    }

    return geofence

  def _get_geofence_description_placeholders(self) -> Mapping[str, str]:
    """Build geofence description placeholders."""

    current_dog = self._current_dog
    if not current_dog:
      return {}

    dog_id = current_dog.get(DOG_ID_FIELD)
    if not isinstance(dog_id, str):
      return {}

    current_geofence = self._current_geofence_options(dog_id)

    geofencing_enabled = current_geofence.get(
      GEOFENCE_ENABLED_FIELD,
      False,
    )
    home_lat = self.hass.config.latitude
    home_lon = self.hass.config.longitude
    geofence_lat = current_geofence.get(GEOFENCE_LAT_FIELD, home_lat)
    geofence_lon = current_geofence.get(GEOFENCE_LON_FIELD, home_lon)
    geofence_radius = current_geofence.get(GEOFENCE_RADIUS_FIELD, 50)

    return {
      "geofencing_enabled": "yes" if geofencing_enabled else "no",
      "geofence_lat": str(geofence_lat) if geofence_lat is not None else "n/a",
      "geofence_lon": str(geofence_lon) if geofence_lon is not None else "n/a",
      "geofence_radius": str(geofence_radius),
    }
