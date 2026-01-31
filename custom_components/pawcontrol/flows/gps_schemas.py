"""GPS schema builders for Paw Control flows."""

from __future__ import annotations

from typing import Mapping

import voluptuous as vol

from ..const import (
  CONF_GPS_SOURCE,
  DEFAULT_GPS_ACCURACY_FILTER,
  DEFAULT_GPS_DISTANCE_FILTER,
  DEFAULT_GPS_UPDATE_INTERVAL,
  GPS_ACCURACY_FILTER_SELECTOR,
  GPS_UPDATE_INTERVAL_SELECTOR,
  MAX_GEOFENCE_RADIUS,
  MIN_GEOFENCE_RADIUS,
)
from ..selector_shim import selector
from ..types import (
  AUTO_TRACK_WALKS_FIELD,
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
  GPS_UPDATE_INTERVAL_FIELD,
  ROUTE_HISTORY_DAYS_FIELD,
  ROUTE_RECORDING_FIELD,
  GeofenceOptions,
  GPSOptions,
)
from .gps_helpers import build_gps_source_options


def build_dog_gps_schema(gps_sources: Mapping[str, str]) -> vol.Schema:
  """Build the schema for GPS configuration."""

  gps_source_schema = selector(
    {
      "select": {
        "options": build_gps_source_options(gps_sources),
        "mode": "dropdown",
      }
    },
  )

  return vol.Schema(
    {
      vol.Required(CONF_GPS_SOURCE): gps_source_schema,
      vol.Required(
        "gps_update_interval",
        default=DEFAULT_GPS_UPDATE_INTERVAL,
      ): selector(GPS_UPDATE_INTERVAL_SELECTOR),
      vol.Required(
        "gps_accuracy_filter",
        default=DEFAULT_GPS_ACCURACY_FILTER,
      ): selector(GPS_ACCURACY_FILTER_SELECTOR),
      vol.Optional("enable_geofencing", default=True): bool,
      vol.Optional("home_zone_radius", default=50): vol.Coerce(float),
    },
  )


def build_gps_settings_schema(current_options: GPSOptions) -> vol.Schema:
  """Build schema for GPS settings."""

  return vol.Schema(
    {
      vol.Optional(
        GPS_ENABLED_FIELD,
        default=current_options.get(GPS_ENABLED_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GPS_UPDATE_INTERVAL_FIELD,
        default=current_options.get(
          GPS_UPDATE_INTERVAL_FIELD,
          DEFAULT_GPS_UPDATE_INTERVAL,
        ),
      ): selector(GPS_UPDATE_INTERVAL_SELECTOR),
      vol.Optional(
        GPS_ACCURACY_FILTER_FIELD,
        default=current_options.get(
          GPS_ACCURACY_FILTER_FIELD,
          DEFAULT_GPS_ACCURACY_FILTER,
        ),
      ): selector(GPS_ACCURACY_FILTER_SELECTOR),
      vol.Optional(
        GPS_DISTANCE_FILTER_FIELD,
        default=current_options.get(
          GPS_DISTANCE_FILTER_FIELD,
          DEFAULT_GPS_DISTANCE_FILTER,
        ),
      ): selector(
        {
          "number": {
            "mode": "box",
            "min": 1,
            "max": 2000,
            "unit_of_measurement": "m",
            "step": 1,
          }
        },
      ),
      vol.Optional(
        ROUTE_RECORDING_FIELD,
        default=current_options.get(ROUTE_RECORDING_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        ROUTE_HISTORY_DAYS_FIELD,
        default=current_options.get(ROUTE_HISTORY_DAYS_FIELD, 30),
      ): selector(
        {
          "number": {
            "mode": "box",
            "min": 1,
            "max": 365,
            "unit_of_measurement": "days",
            "step": 1,
          }
        },
      ),
      vol.Optional(
        AUTO_TRACK_WALKS_FIELD,
        default=current_options.get(AUTO_TRACK_WALKS_FIELD, True),
      ): selector({"boolean": {}}),
    },
  )


def build_geofence_settings_schema(current_options: GeofenceOptions) -> vol.Schema:
  """Build schema for geofence settings."""

  geofence_latitude = current_options.get(GEOFENCE_LAT_FIELD) or "52.5200"
  geofence_longitude = current_options.get(GEOFENCE_LON_FIELD) or "13.4050"

  return vol.Schema(
    {
      vol.Optional(
        GEOFENCE_ENABLED_FIELD,
        default=current_options.get(GEOFENCE_ENABLED_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_USE_HOME_FIELD,
        default=current_options.get(GEOFENCE_USE_HOME_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_RADIUS_FIELD,
        default=current_options.get(GEOFENCE_RADIUS_FIELD, 100.0),
      ): selector(
        {
          "number": {
            "mode": "box",
            "min": MIN_GEOFENCE_RADIUS,
            "max": MAX_GEOFENCE_RADIUS,
            "unit_of_measurement": "m",
            "step": 1,
          }
        },
      ),
      vol.Optional(
        GEOFENCE_LAT_FIELD,
        default=geofence_latitude,
      ): selector({"text": {}}),
      vol.Optional(
        GEOFENCE_LON_FIELD,
        default=geofence_longitude,
      ): selector({"text": {}}),
      vol.Optional(
        GEOFENCE_ALERTS_FIELD,
        default=current_options.get(GEOFENCE_ALERTS_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_SAFE_ZONE_FIELD,
        default=current_options.get(GEOFENCE_SAFE_ZONE_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_RESTRICTED_ZONE_FIELD,
        default=current_options.get(GEOFENCE_RESTRICTED_ZONE_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_ZONE_ENTRY_FIELD,
        default=current_options.get(GEOFENCE_ZONE_ENTRY_FIELD, True),
      ): selector({"boolean": {}}),
      vol.Optional(
        GEOFENCE_ZONE_EXIT_FIELD,
        default=current_options.get(GEOFENCE_ZONE_EXIT_FIELD, True),
      ): selector({"boolean": {}}),
    },
  )
