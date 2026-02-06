"""Device triggers for PawControl."""

from __future__ import annotations

from collections.abc import Callable, Iterable, MutableMapping
from dataclasses import dataclass
import logging
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
from homeassistant.helpers import (
  config_validation as cv,
  device_registry as dr,
  entity_registry as er,
)
from homeassistant.helpers.event import async_track_state_change_event
import voluptuous as vol

from .const import DOMAIN
from .types import DomainRuntimeStoreEntry, PawControlRuntimeData

_LOGGER = logging.getLogger(__name__)

_ENTITY_ID_VALIDATOR = cast(vol.Any, getattr(cv, "entity_id", cv.string))

_UNIQUE_ID_FORMAT: Final[str] = "pawcontrol_{dog_id}_{suffix}"


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


@dataclass(slots=True)
class PawControlDeviceAutomationContext:
  """Resolved context for device automation lookups."""

  device_id: str
  dog_id: str | None
  runtime_data: PawControlRuntimeData | None


def build_unique_id(dog_id: str, suffix: str) -> str:
  """Build the stable unique_id used by PawControl entities."""

  return _UNIQUE_ID_FORMAT.format(dog_id=dog_id, suffix=suffix)


def _extract_dog_id(device_entry: dr.DeviceEntry | None) -> str | None:
  """Extract the dog identifier from a device registry entry."""

  if device_entry is None:
    return None

  for domain, identifier in device_entry.identifiers:
    if domain == DOMAIN:
      return identifier

  return None


def _coerce_runtime_data(value: object | None) -> PawControlRuntimeData | None:
  """Return runtime data extracted from ``value`` when possible."""

  if isinstance(value, PawControlRuntimeData):
    return value
  if isinstance(value, DomainRuntimeStoreEntry):
    return value.unwrap()
  return None


def _resolve_runtime_data_from_store(
  hass: HomeAssistant,
  entry_ids: Iterable[str],
) -> PawControlRuntimeData | None:
  """Resolve runtime data from ``hass.data`` using entry identifiers."""

  domain_store = hass.data.get(DOMAIN)
  if not isinstance(domain_store, MutableMapping):
    return None

  for entry_id in entry_ids:
    runtime_data = _coerce_runtime_data(domain_store.get(entry_id))
    if runtime_data is not None:
      return runtime_data

  return None


def resolve_device_context(
  hass: HomeAssistant,
  device_id: str,
) -> PawControlDeviceAutomationContext:
  """Resolve the runtime data and dog identifier for a device."""

  device_registry = dr.async_get(hass)
  device_entry = device_registry.async_get(device_id)
  dog_id = _extract_dog_id(device_entry)

  entry_ids: Iterable[str] = ()
  if device_entry is not None:
    entry_ids = device_entry.config_entries

  runtime_data = _resolve_runtime_data_from_store(hass, entry_ids)

  return PawControlDeviceAutomationContext(
    device_id=device_id,
    dog_id=dog_id,
    runtime_data=runtime_data,
  )


def resolve_entity_id(
  hass: HomeAssistant,
  device_id: str,
  unique_id: str,
  platform: str,
) -> str | None:
  """Resolve an entity id for a device-based automation."""

  entity_registry = er.async_get(hass)
  for entry in entity_registry.async_entries_for_device(device_id):
    if entry.unique_id == unique_id and entry.platform == platform:
      return entry.entity_id

  return None


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
