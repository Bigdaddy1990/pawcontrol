"""Walk schema builders for Paw Control flows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from ..selector_shim import selector
from ..types import DoorSensorSettingsConfig
from .walk_helpers import WALK_SETTINGS_FIELDS

(
  WALK_DETECTION_TIMEOUT_FIELD,
  MINIMUM_WALK_DURATION_FIELD,
  MAXIMUM_WALK_DURATION_FIELD,
  AUTO_END_WALKS_FIELD,
) = WALK_SETTINGS_FIELDS


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
      WALK_DETECTION_TIMEOUT_FIELD,
      default=_value(
        WALK_DETECTION_TIMEOUT_FIELD,
        defaults.walk_detection_timeout,
      ),
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
      MINIMUM_WALK_DURATION_FIELD,
      default=_value(
        MINIMUM_WALK_DURATION_FIELD,
        defaults.minimum_walk_duration,
      ),
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
      MAXIMUM_WALK_DURATION_FIELD,
      default=_value(
        MAXIMUM_WALK_DURATION_FIELD,
        defaults.maximum_walk_duration,
      ),
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
      AUTO_END_WALKS_FIELD,
      default=_value(AUTO_END_WALKS_FIELD, defaults.auto_end_walks),
    ): selector.BooleanSelector(),
  }
