"""Walk schema builders for Paw Control flows."""

from __future__ import annotations

from typing import Any, Mapping

import voluptuous as vol

from ..selector_shim import selector
from ..types import DoorSensorSettingsConfig
from .walk_helpers import WALK_SETTINGS_FIELDS


def build_walk_timing_schema_fields(
  values: Mapping[str, Any],
  defaults: DoorSensorSettingsConfig,
) -> dict[vol.Optional, object]:
  """Build schema fields for walk timing settings."""

  def _value(key: str, fallback: Any) -> Any:
    return values.get(key, fallback)

  fields: dict[vol.Optional, object] = {}
  fields[
    vol.Optional(
      WALK_SETTINGS_FIELDS[0],
      default=_value(WALK_SETTINGS_FIELDS[0], defaults.walk_detection_timeout),
    )
  ] = selector.NumberSelector(
    selector.NumberSelectorConfig(
      min=30,
      max=21600,
      step=30,
      mode=selector.NumberSelectorMode.BOX,
      unit_of_measurement="seconds",
    ),
  )
  fields[
    vol.Optional(
      WALK_SETTINGS_FIELDS[1],
      default=_value(WALK_SETTINGS_FIELDS[1], defaults.minimum_walk_duration),
    )
  ] = selector.NumberSelector(
    selector.NumberSelectorConfig(
      min=60,
      max=21600,
      step=30,
      mode=selector.NumberSelectorMode.BOX,
      unit_of_measurement="seconds",
    ),
  )
  fields[
    vol.Optional(
      WALK_SETTINGS_FIELDS[2],
      default=_value(WALK_SETTINGS_FIELDS[2], defaults.maximum_walk_duration),
    )
  ] = selector.NumberSelector(
    selector.NumberSelectorConfig(
      min=120,
      max=43200,
      step=60,
      mode=selector.NumberSelectorMode.BOX,
      unit_of_measurement="seconds",
    ),
  )
  return fields


def build_auto_end_walks_field(
  values: Mapping[str, Any],
  defaults: DoorSensorSettingsConfig,
) -> dict[vol.Optional, object]:
  """Build schema field for the auto-end walks toggle."""

  def _value(key: str, fallback: Any) -> Any:
    return values.get(key, fallback)

  return {
    vol.Optional(
      WALK_SETTINGS_FIELDS[3],
      default=_value(WALK_SETTINGS_FIELDS[3], defaults.auto_end_walks),
    ): selector.BooleanSelector(),
  }
