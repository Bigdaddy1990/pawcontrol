"""Helpers for PawControl device automations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
import logging
from typing import Final, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

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

  runtime_data: PawControlRuntimeData | None = None
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
