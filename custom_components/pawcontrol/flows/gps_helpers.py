"""GPS helper utilities for Paw Control flows."""

from __future__ import annotations

from typing import Mapping

from ..exceptions import ValidationError
from ..types import (
  DOG_GPS_PLACEHOLDERS_TEMPLATE,
  ConfigFlowPlaceholders,
  clone_placeholders,
  freeze_placeholders,
)


def validation_error_key(error: ValidationError, fallback: str) -> str:
  """Return a translation key for a validation error."""

  return error.constraint or fallback


def build_dog_gps_placeholders(*, dog_name: str) -> ConfigFlowPlaceholders:
  """Return immutable placeholders for the GPS configuration step."""

  placeholders = clone_placeholders(DOG_GPS_PLACEHOLDERS_TEMPLATE)
  placeholders["dog_name"] = dog_name
  return freeze_placeholders(placeholders)


def build_gps_source_options(
  gps_sources: Mapping[str, str],
) -> dict[str, str]:
  """Return ordered GPS source options with push/manual defaults."""

  base_push_sources = {
    "webhook": "Webhook (Push)",
    "mqtt": "MQTT (Push)",
  }
  if not gps_sources:
    return {
      **base_push_sources,
      "manual": "Manual Location Entry",
    }

  return {
    **gps_sources,
    **base_push_sources,
    "manual": "Manual Location Entry",
  }
