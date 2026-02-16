"""Helpers for PawControl device automations."""

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
import logging
from typing import Final

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN
from .dog_status import build_dog_status_snapshot
from .types import (
  CoordinatorDogData,
  DogStatusSnapshot,
  DomainRuntimeStoreEntry,
  PawControlRuntimeData,
)

_LOGGER = logging.getLogger(__name__)

_UNIQUE_ID_FORMAT: Final[str] = "pawcontrol_{dog_id}_{suffix}"
_DEFAULT_METADATA: Final[dict[str, bool]] = {"secondary": False}


@dataclass(slots=True)
class PawControlDeviceAutomationContext:
  """Resolved context for device automation lookups."""  # noqa: E111

  device_id: str  # noqa: E111
  dog_id: str | None  # noqa: E111
  runtime_data: PawControlRuntimeData | None  # noqa: E111


def build_unique_id(dog_id: str, suffix: str) -> str:
  """Build the stable unique_id used by PawControl entities."""  # noqa: E111

  return _UNIQUE_ID_FORMAT.format(dog_id=dog_id, suffix=suffix)  # noqa: E111


def build_device_automation_metadata() -> dict[str, bool]:
  """Return metadata for device automations."""  # noqa: E111

  return dict(_DEFAULT_METADATA)  # noqa: E111


def _extract_dog_id(device_entry: dr.DeviceEntry | None) -> str | None:
  """Extract the dog identifier from a device registry entry."""  # noqa: E111

  if device_entry is None:  # noqa: E111
    return None

  for domain, identifier in device_entry.identifiers:  # noqa: E111
    if domain == DOMAIN:
      return identifier  # noqa: E111

  return None  # noqa: E111


def _coerce_runtime_data(value: object | None) -> PawControlRuntimeData | None:
  """Return runtime data extracted from ``value`` when possible."""  # noqa: E111

  if isinstance(value, PawControlRuntimeData):  # noqa: E111
    return value
  if isinstance(value, DomainRuntimeStoreEntry):  # noqa: E111
    return value.unwrap()
  return None  # noqa: E111


def _resolve_runtime_data_from_store(
  hass: HomeAssistant,
  entry_ids: Iterable[str],
) -> PawControlRuntimeData | None:
  """Resolve runtime data from ``hass.data`` using entry identifiers."""  # noqa: E111

  domain_store = hass.data.get(DOMAIN)  # noqa: E111
  if not isinstance(domain_store, MutableMapping):  # noqa: E111
    return None

  for entry_id in entry_ids:  # noqa: E111
    runtime_data = _coerce_runtime_data(domain_store.get(entry_id))
    if runtime_data is not None:
      return runtime_data  # noqa: E111

  return None  # noqa: E111


def resolve_device_context(
  hass: HomeAssistant,
  device_id: str,
) -> PawControlDeviceAutomationContext:
  """Resolve the runtime data and dog identifier for a device."""  # noqa: E111

  device_registry = dr.async_get(hass)  # noqa: E111
  device_entry = device_registry.async_get(device_id)  # noqa: E111
  dog_id = _extract_dog_id(device_entry)  # noqa: E111

  runtime_data: PawControlRuntimeData | None = None  # noqa: E111
  entry_ids: Iterable[str] = ()  # noqa: E111
  if device_entry is not None:  # noqa: E111
    entry_ids = device_entry.config_entries

  runtime_data = _resolve_runtime_data_from_store(hass, entry_ids)  # noqa: E111

  return PawControlDeviceAutomationContext(  # noqa: E111
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
  """Resolve an entity id for a device-based automation."""  # noqa: E111

  entity_registry = er.async_get(hass)  # noqa: E111
  for entry in entity_registry.async_entries_for_device(device_id):  # noqa: E111
    if entry.unique_id == unique_id and entry.platform == platform:
      return entry.entity_id  # noqa: E111

  return None  # noqa: E111


def resolve_dog_data(
  runtime_data: PawControlRuntimeData | None,
  dog_id: str | None,
) -> CoordinatorDogData | None:
  """Return coordinator dog data when available."""  # noqa: E111

  if runtime_data is None or dog_id is None:  # noqa: E111
    return None

  coordinator = runtime_data.coordinator  # noqa: E111
  try:  # noqa: E111
    dog_data = coordinator.get_dog_data(dog_id)
  except Exception as err:  # pragma: no cover - defensive log path  # noqa: E111
    _LOGGER.debug("Failed to fetch dog data for %s: %s", dog_id, err)
    return None

  if isinstance(dog_data, Mapping):  # noqa: E111
    return dog_data

  return None  # noqa: E111


def resolve_status_snapshot(
  runtime_data: PawControlRuntimeData | None,
  dog_id: str | None,
) -> DogStatusSnapshot | None:
  """Return the status snapshot for a dog when data is available."""  # noqa: E111

  dog_data = resolve_dog_data(runtime_data, dog_id)  # noqa: E111
  if dog_data is None or dog_id is None:  # noqa: E111
    return None

  snapshot = dog_data.get("status_snapshot")  # noqa: E111
  if isinstance(snapshot, Mapping):  # noqa: E111
    return snapshot

  return build_dog_status_snapshot(dog_id, dog_data)  # noqa: E111
