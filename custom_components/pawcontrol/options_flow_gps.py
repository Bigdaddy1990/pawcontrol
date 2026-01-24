"""GPS options normalization helpers for the options flow."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Protocol, cast

from .const import (
  CONF_GPS_ACCURACY_FILTER,
  CONF_GPS_DISTANCE_FILTER,
  CONF_GPS_UPDATE_INTERVAL,
  DEFAULT_GPS_ACCURACY_FILTER,
  DEFAULT_GPS_DISTANCE_FILTER,
  DEFAULT_GPS_UPDATE_INTERVAL,
)
from .exceptions import ValidationError
from .options_flow_shared import DOG_OPTIONS_FIELD
from .schemas import GPS_OPTIONS_JSON_SCHEMA, validate_json_schema_payload
from .types import (
  AUTO_TRACK_WALKS_FIELD,
  DOG_ID_FIELD,
  GPS_ACCURACY_FILTER_FIELD,
  GPS_DISTANCE_FILTER_FIELD,
  GPS_ENABLED_FIELD,
  GPS_SETTINGS_FIELD,
  GPS_UPDATE_INTERVAL_FIELD,
  JSONLikeMapping,
  JSONMutableMapping,
  JSONValue,
  ROUTE_HISTORY_DAYS_FIELD,
  ROUTE_RECORDING_FIELD,
  DogOptionsMap,
  GPSOptions,
  ensure_dog_options_entry,
)
from .validation import validate_float_range, validate_interval

_LOGGER = logging.getLogger(__name__)


class GPSOptionsNormalizerHost(Protocol):
  """Protocol describing the options flow host requirements."""

  def _coerce_bool(self, value: Any, default: bool) -> bool: ...


class GPSOptionsNormalizerMixin(GPSOptionsNormalizerHost):
  """Mixin providing GPS normalization for options payloads."""

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
      try:
        return validate_interval(
          value,
          field=field,
          minimum=minimum,
          maximum=maximum,
          default=default,
          clamp=True,
        )
      except ValidationError:
        return default

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

    payload: GPSOptions = {
      GPS_ENABLED_FIELD: self._coerce_bool(raw.get(GPS_ENABLED_FIELD), True),
      GPS_UPDATE_INTERVAL_FIELD: _safe_interval(
        raw.get(GPS_UPDATE_INTERVAL_FIELD),
        default=DEFAULT_GPS_UPDATE_INTERVAL,
        minimum=5,
        maximum=600,
        field=GPS_UPDATE_INTERVAL_FIELD,
      ),
      GPS_ACCURACY_FILTER_FIELD: _safe_float_range(
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
    }
    schema_issues = validate_json_schema_payload(
      payload,
      GPS_OPTIONS_JSON_SCHEMA,
    )
    if schema_issues:
      _LOGGER.warning(
        "GPS options payload failed JSON schema validation; using defaults: %s",
        [issue.constraint for issue in schema_issues],
      )
      payload = {
        GPS_ENABLED_FIELD: True,
        GPS_UPDATE_INTERVAL_FIELD: DEFAULT_GPS_UPDATE_INTERVAL,
        GPS_ACCURACY_FILTER_FIELD: float(DEFAULT_GPS_ACCURACY_FILTER),
        GPS_DISTANCE_FILTER_FIELD: float(DEFAULT_GPS_DISTANCE_FILTER),
        ROUTE_RECORDING_FIELD: True,
        ROUTE_HISTORY_DAYS_FIELD: 30,
        AUTO_TRACK_WALKS_FIELD: True,
      }
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
