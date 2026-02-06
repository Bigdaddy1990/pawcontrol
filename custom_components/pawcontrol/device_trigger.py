"""Device triggers for PawControl."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from collections.abc import Callable
from typing import Final, cast

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import (
  CONF_DEVICE_ID,
  CONF_DOMAIN,
  CONF_ENTITY_ID,
  CONF_FROM,
  CONF_PLATFORM,
  CONF_TO,
  CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_state_change_event
import voluptuous as vol

from .const import DOMAIN
from .device_automation_helpers import (
  build_unique_id,
  resolve_device_context,
  resolve_entity_id,
)

_LOGGER = logging.getLogger(__name__)

_ENTITY_ID_VALIDATOR = cast(vol.Any, getattr(cv, "entity_id", cv.string))


@dataclass(frozen=True, slots=True)
class TriggerDefinition:
  """Definition for a device trigger tied to an entity."""

  type: str
  platform: str
  entity_suffix: str
  to_state: str | None = None
  from_state: str | None = None


TRIGGER_DEFINITIONS: Final[tuple[TriggerDefinition, ...]] = (
  TriggerDefinition("hungry", "binary_sensor", "is_hungry", to_state="on"),
  TriggerDefinition("needs_walk", "binary_sensor", "needs_walk", to_state="on"),
  TriggerDefinition(
    "walk_started",
    "binary_sensor",
    "walk_in_progress",
    to_state="on",
  ),
  TriggerDefinition(
    "walk_ended",
    "binary_sensor",
    "walk_in_progress",
    to_state="off",
  ),
  TriggerDefinition(
    "attention_needed",
    "binary_sensor",
    "attention_needed",
    to_state="on",
  ),
  TriggerDefinition(
    "safe_zone_entered",
    "binary_sensor",
    "in_safe_zone",
    to_state="on",
  ),
  TriggerDefinition(
    "safe_zone_left",
    "binary_sensor",
    "in_safe_zone",
    to_state="off",
  ),
  TriggerDefinition("status_changed", "sensor", "status"),
)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
  {
    vol.Required(CONF_TYPE): vol.In(
      {definition.type for definition in TRIGGER_DEFINITIONS}
    ),
    vol.Optional(CONF_ENTITY_ID): _ENTITY_ID_VALIDATOR,
    vol.Optional(CONF_FROM): cv.string,
    vol.Optional(CONF_TO): cv.string,
  },
)


async def async_get_triggers(
  hass: HomeAssistant,
  device_id: str,
) -> list[dict[str, str]]:
  """List device triggers for PawControl devices."""

  context = resolve_device_context(hass, device_id)
  if context.dog_id is None:
    return []

  triggers: list[dict[str, str]] = []
  for definition in TRIGGER_DEFINITIONS:
    unique_id = build_unique_id(context.dog_id, definition.entity_suffix)
    entity_id = resolve_entity_id(
      hass,
      device_id,
      unique_id,
      definition.platform,
    )
    if entity_id is None:
      continue

    trigger: dict[str, str] = {
      CONF_PLATFORM: "device",
      CONF_DEVICE_ID: device_id,
      CONF_DOMAIN: DOMAIN,
      CONF_TYPE: definition.type,
      CONF_ENTITY_ID: entity_id,
    }
    if definition.from_state is not None:
      trigger[CONF_FROM] = definition.from_state
    if definition.to_state is not None:
      trigger[CONF_TO] = definition.to_state
    triggers.append(trigger)

  return triggers


async def async_get_trigger_capabilities(
  hass: HomeAssistant,
  config: dict[str, str],
) -> dict[str, vol.Schema]:
  """Return trigger capability schemas."""

  if config.get(CONF_TYPE) != "status_changed":
    return {}

  return {
    "extra_fields": vol.Schema(
      {
        vol.Optional(CONF_FROM): cv.string,
        vol.Optional(CONF_TO): cv.string,
      },
    ),
  }


async def async_attach_trigger(
  hass: HomeAssistant,
  config: dict[str, str],
  action: Callable[[dict[str, object]], object],
  trigger_info: dict[str, str],
) -> CALLBACK_TYPE:
  """Attach a trigger for PawControl device automation."""

  validated = TRIGGER_SCHEMA(config)
  entity_id = validated.get(CONF_ENTITY_ID)
  if not entity_id:
    raise vol.Invalid("Missing entity_id for PawControl device trigger")

  trigger_data = {
    "platform": "device",
    "device_id": validated[CONF_DEVICE_ID],
    "domain": DOMAIN,
    "type": validated[CONF_TYPE],
    "entity_id": entity_id,
  }

  @callback
  def _handle_event(event: Event) -> None:
    old_state = event.data.get("old_state")
    new_state = event.data.get("new_state")

    from_state = validated.get(CONF_FROM)
    to_state = validated.get(CONF_TO)

    if from_state is not None and (old_state is None or old_state.state != from_state):
      return
    if to_state is not None and (new_state is None or new_state.state != to_state):
      return

    payload = dict(trigger_data)
    payload.update(
      {
        "from_state": old_state,
        "to_state": new_state,
        "description": trigger_info.get("description"),
      },
    )
    hass.async_create_task(action(payload))

  return async_track_state_change_event(
    hass,
    [entity_id],
    _handle_event,
  )
