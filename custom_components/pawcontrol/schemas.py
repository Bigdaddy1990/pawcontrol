"""Validation schemas for PawControl."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
  CONF_GPS_SOURCE,
  CONF_GPS_UPDATE_INTERVAL,
)

GPS_PUSH_PAYLOAD_SCHEMA = vol.Schema(
  {
    vol.Required("dog_id"): cv.string,
    vol.Required("latitude"): vol.Coerce(float),
    vol.Required("longitude"): vol.Coerce(float),
    vol.Optional("battery"): vol.Coerce(int),
    vol.Optional("accuracy"): vol.Coerce(int),
    vol.Optional("timestamp"): cv.positive_int,
    vol.Optional("speed"): vol.Coerce(float),
  },
  extra=vol.ALLOW_EXTRA,
)


GPS_OPTIONS_SCHEMA = vol.Schema(
  {
    vol.Optional(CONF_GPS_SOURCE): cv.string,
    vol.Optional(CONF_GPS_UPDATE_INTERVAL): cv.positive_int,
  },
  extra=vol.ALLOW_EXTRA,
)


def validate_gps_push_payload(payload: dict) -> dict:
  """Validate and normalize GPS push payload."""
  try:
    return GPS_PUSH_PAYLOAD_SCHEMA(payload)
  except vol.Invalid as err:
    raise ValueError(f"Invalid payload: {err}") from err
