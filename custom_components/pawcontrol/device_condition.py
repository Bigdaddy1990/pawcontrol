"""Device conditions for PawControl."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Final, cast

from homeassistant.components.device_automation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.const import (
  CONF_CONDITION,
  CONF_DEVICE_ID,
  CONF_DOMAIN,
  CONF_ENTITY_ID,
  CONF_TYPE,
  STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.condition import ConditionCheckerType
import voluptuous as vol

from .const import DOMAIN
from .device_automation_helpers import (
  build_unique_id,
  resolve_device_context,
  resolve_entity_id,
  resolve_status_snapshot,
)

_LOGGER = logging.getLogger(__name__)

_ENTITY_ID_VALIDATOR = cast(vol.Any, getattr(cv, "entity_id", cv.string))

CONF_STATUS = "status"


@dataclass(frozen=True, slots=True)
class ConditionDefinition:
  """Definition for a device condition."""

  type: str
  platform: str
  entity_suffix: str


CONDITION_DEFINITIONS: Final[tuple[ConditionDefinition, ...]] = (
  ConditionDefinition("is_hungry", "binary_sensor", "is_hungry"),
  ConditionDefinition("needs_walk", "binary_sensor", "needs_walk"),
  ConditionDefinition("on_walk", "binary_sensor", "walk_in_progress"),
  ConditionDefinition("in_safe_zone", "binary_sensor", "in_safe_zone"),
  ConditionDefinition("attention_needed", "binary_sensor", "attention_needed"),
  ConditionDefinition("status_is", "sensor", "status"),
)

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
  {
    vol.Required(CONF_TYPE): vol.In(
      {definition.type for definition in CONDITION_DEFINITIONS},
    ),
    vol.Optional(CONF_ENTITY_ID): _ENTITY_ID_VALIDATOR,
    vol.Optional(CONF_STATUS): cv.string,
  },
)


async def async_get_conditions(
  hass: HomeAssistant,
  device_id: str,
) -> list[dict[str, str]]:
  """List device conditions for PawControl devices."""

  context = resolve_device_context(hass, device_id)
  if context.dog_id is None:
    return []

  conditions: list[dict[str, str]] = []
  for definition in CONDITION_DEFINITIONS:
    unique_id = build_unique_id(context.dog_id, definition.entity_suffix)
    entity_id = resolve_entity_id(
      hass,
      device_id,
      unique_id,
      definition.platform,
    )
    if entity_id is None:
      continue

    conditions.append(
      {
        CONF_CONDITION: "device",
        CONF_DEVICE_ID: device_id,
        CONF_DOMAIN: DOMAIN,
        CONF_TYPE: definition.type,
        CONF_ENTITY_ID: entity_id,
      },
    )

  return conditions


async def async_get_condition_capabilities(
  hass: HomeAssistant,
  config: dict[str, str],
) -> dict[str, vol.Schema]:
  """Return condition capability schemas."""

  if config.get(CONF_TYPE) != "status_is":
    return {}

  return {
    "extra_fields": vol.Schema(
      {
        vol.Required(CONF_STATUS): cv.string,
      },
    ),
  }


async def async_condition_from_config(
  hass: HomeAssistant,
  config: dict[str, str],
) -> ConditionCheckerType:
  """Create a condition checker for PawControl device automation."""

  validated = CONDITION_SCHEMA(config)
  device_id = validated[CONF_DEVICE_ID]
  context = resolve_device_context(hass, device_id)
  entity_id = validated.get(CONF_ENTITY_ID)
  condition_type = validated[CONF_TYPE]

  def _evaluate_state(expected_on: bool) -> bool:
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
      return False
    return (state.state == STATE_ON) is expected_on

  def _evaluate_status(expected_status: str) -> bool:
    snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
    if snapshot is not None:
      return snapshot.get("state") == expected_status

    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
      return False
    return state.state == expected_status

  def _condition(_hass: HomeAssistant, _variables: dict[str, object]) -> bool:
    match condition_type:
      case "is_hungry":
        snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
        if snapshot is not None:
          return bool(snapshot.get("is_hungry", False))
        return _evaluate_state(True)
      case "needs_walk":
        snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
        if snapshot is not None:
          return bool(snapshot.get("needs_walk", False))
        return _evaluate_state(True)
      case "on_walk":
        snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
        if snapshot is not None:
          return bool(snapshot.get("on_walk", False))
        return _evaluate_state(True)
      case "in_safe_zone":
        snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
        if snapshot is not None:
          return bool(snapshot.get("in_safe_zone", True))
        return _evaluate_state(True)
      case "attention_needed":
        return _evaluate_state(True)
      case "status_is":
        expected = validated.get(CONF_STATUS)
        if not expected:
          _LOGGER.debug("Missing status value for status_is condition")
          return False
        return _evaluate_status(expected)
      case _:
        _LOGGER.debug("Unknown PawControl condition type: %s", condition_type)
        return False

  return _condition
