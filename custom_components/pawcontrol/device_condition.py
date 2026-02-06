"""Device conditions for PawControl."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
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
from homeassistant.helpers import (
  config_validation as cv,
  device_registry as dr,
  entity_registry as er,
)

from collections.abc import Callable
from typing import TYPE_CHECKING

# ``ConditionCheckerType`` is only used for typing. Some Home Assistant test harness
# builds do not ship the helpers module that defines it, so we avoid importing it at
# runtime and provide a safe fallback.
if TYPE_CHECKING:  # pragma: no cover
  try:
    from homeassistant.helpers.condition import ConditionCheckerType
  except ImportError:
    try:
      from homeassistant.helpers.typing import ConditionCheckerType  # type: ignore[attr-defined]
    except ImportError:
      ConditionCheckerType = Callable[..., bool]  # type: ignore[assignment]
else:
  ConditionCheckerType = Callable[..., bool]  # type: ignore[assignment]

import voluptuous as vol

from .const import DOMAIN
from .dog_status import build_dog_status_snapshot
from .types import (
  CoordinatorDogData,
  DogStatusSnapshot,
  DomainRuntimeStoreEntry,
  PawControlRuntimeData,
)

_LOGGER = logging.getLogger(__name__)

_ENTITY_ID_VALIDATOR = cast(vol.Any, getattr(cv, "entity_id", cv.string))

CONF_STATUS = "status"

_UNIQUE_ID_FORMAT: Final[str] = "pawcontrol_{dog_id}_{suffix}"


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


def resolve_dog_data(
  runtime_data: PawControlRuntimeData | None,
  dog_id: str | None,
) -> CoordinatorDogData | None:
  """Return coordinator dog data when available."""

  if runtime_data is None or dog_id is None:
    return None

  coordinator = runtime_data.coordinator
  try:
    dog_data = coordinator.get_dog_data(dog_id)
  except Exception as err:  # pragma: no cover - defensive log path
    _LOGGER.debug("Failed to fetch dog data for %s: %s", dog_id, err)
    return None

  if isinstance(dog_data, Mapping):
    return cast(CoordinatorDogData, dog_data)

  return None


def resolve_status_snapshot(
  runtime_data: PawControlRuntimeData | None,
  dog_id: str | None,
) -> DogStatusSnapshot | None:
  """Return the status snapshot for a dog when data is available."""

  dog_data = resolve_dog_data(runtime_data, dog_id)
  if dog_data is None or dog_id is None:
    return None

  snapshot = dog_data.get("status_snapshot")
  if isinstance(snapshot, Mapping):
    return cast(DogStatusSnapshot, snapshot)

  return build_dog_status_snapshot(dog_id, dog_data)


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
