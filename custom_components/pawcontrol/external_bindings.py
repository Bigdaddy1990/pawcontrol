"""External entity bindings for PawControl.

Binds external Home Assistant entities as data sources without requiring
vendor-specific code.

Implemented:
- GPS source bindings: when a dog's gps_source is set to an entity_id
  (device_tracker.* / person.* or any entity that provides latitude/longitude
  attributes), PawControl listens for state changes and forwards coordinates
  into the GPS manager.

Notes:
- This is independent from webhook/MQTT push. It is used when the GPS source
  is an entity_id, not one of the push keywords.
- Telemetry / strict source checks for webhook/MQTT are handled by push_router.py.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final, cast

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import event as event_helper
from homeassistant.util import dt as dt_util

from .compat import ConfigEntry
from .const import CONF_DOGS, CONF_GPS_SOURCE, DOMAIN
from .gps_manager import LocationSource
from .runtime_data import require_runtime_data
import contextlib

_LOGGER = logging.getLogger(__name__)

_STORE_KEY: Final[str] = "_external_bindings"
_MIN_METERS: Final[float] = 5.0
_DEBOUNCE_SECONDS: Final[float] = 2.0


@dataclass(slots=True)
class _Binding:
  unsub: Callable[[], None]
  task: asyncio.Task[None] | None


def _domain_store(hass: HomeAssistant) -> dict[str, Any]:
  store = hass.data.setdefault(DOMAIN, {})
  if not isinstance(store, dict):
    hass.data[DOMAIN] = {}
    store = hass.data[DOMAIN]
  return cast(dict[str, Any], store)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
  r = 6371000.0
  phi1 = math.radians(lat1)
  phi2 = math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dl = math.radians(lon2 - lon1)
  a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dl / 2) ** 2
  return 2 * r * math.asin(math.sqrt(a))


def _extract_coords(
  state_obj: Any,
) -> tuple[float | None, float | None, float | None, float | None]:
  attrs = getattr(state_obj, "attributes", None)
  if not isinstance(attrs, Mapping):
    return None, None, None, None

  lat = attrs.get("latitude")
  lon = attrs.get("longitude")
  acc = attrs.get("gps_accuracy") or attrs.get("accuracy")
  alt = attrs.get("altitude")

  if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
    return (
      float(lat),
      float(lon),
      float(acc) if isinstance(acc, (int, float)) else None,
      float(alt) if isinstance(alt, (int, float)) else None,
    )
  return None, None, None, None


async def async_setup_external_bindings(
  hass: HomeAssistant, entry: ConfigEntry
) -> None:
  """Set up external entity listeners for this config entry."""
  runtime_data = require_runtime_data(hass, entry)
  coordinator = runtime_data.coordinator
  gps_manager = runtime_data.gps_geofence_manager or coordinator.gps_geofence_manager
  if gps_manager is None:
    _LOGGER.debug("External bindings skipped (GPS manager unavailable)")
    return

  store = _domain_store(hass)
  bindings = store.setdefault(_STORE_KEY, {}).setdefault(entry.entry_id, {})
  if not isinstance(bindings, dict):
    store[_STORE_KEY][entry.entry_id] = {}
    bindings = store[_STORE_KEY][entry.entry_id]

  async def _process_change(dog_id: str, entity_id: str, event: Event) -> None:
    # Debounce
    await asyncio.sleep(_DEBOUNCE_SECONDS)
    new_state = event.data.get("new_state")
    if new_state is None:
      return
    lat, lon, acc, alt = _extract_coords(new_state)
    if lat is None or lon is None:
      return

    # Ignore tiny movements (noise)
    try:
      current = await gps_manager.async_get_current_location(dog_id)
    except Exception:
      current = None
    if (
      current
      and isinstance(current.latitude, (int, float))
      and isinstance(current.longitude, (int, float))
      and _haversine_m(float(current.latitude), float(current.longitude), lat, lon)
      < _MIN_METERS
    ):
      return

    try:
      ok = await gps_manager.async_add_gps_point(
        dog_id=dog_id,
        latitude=lat,
        longitude=lon,
        altitude=alt,
        accuracy=acc,
        timestamp=dt_util.utcnow(),
        source=LocationSource.ENTITY,
      )
      if ok:
        await coordinator.async_patch_gps_update(dog_id)
    except Exception as err:  # pragma: no cover
      _LOGGER.debug(
        "External GPS binding update failed for %s from %s: %s", dog_id, entity_id, err
      )

  dogs = entry.data.get(CONF_DOGS, [])
  if not isinstance(dogs, list):
    return

  for dog in dogs:
    if not isinstance(dog, Mapping):
      continue
    dog_id = dog.get("dog_id")
    if not isinstance(dog_id, str) or not dog_id:
      continue

    gps_cfg = dog.get("gps_config")
    src = gps_cfg.get(CONF_GPS_SOURCE) if isinstance(gps_cfg, Mapping) else None
    if not isinstance(src, str) or not src.strip():
      continue

    source = src.strip()
    if source in {"manual", "webhook", "mqtt"}:
      continue
    if "." not in source:
      continue

    dog_id_str = dog_id
    if dog_id_str in bindings:
      continue

    @callback
    def _on_change(
      event: Event,
      dog_id: str = dog_id_str,
      source: str = source,
    ) -> None:
      binding = cast(_Binding | None, bindings.get(dog_id))
      if binding is None:
        return
      if binding.task and not binding.task.done():
        binding.task.cancel()
      binding.task = hass.async_create_task(_process_change(dog_id, source, event))

    unsub = event_helper.async_track_state_change_event(hass, [source], _on_change)
    bindings[dog_id_str] = _Binding(unsub=unsub, task=None)

  _LOGGER.debug("External GPS bindings ready for entry %s", entry.entry_id)


async def async_unload_external_bindings(
  hass: HomeAssistant, entry: ConfigEntry
) -> None:
  """Unload external entity listeners for this entry."""
  store = _domain_store(hass)
  entry_map = store.get(_STORE_KEY)
  if not isinstance(entry_map, dict):
    return
  bindings = entry_map.pop(entry.entry_id, None)
  if not isinstance(bindings, dict):
    return
  for binding in bindings.values():
    if isinstance(binding, _Binding):
      with contextlib.suppress(Exception):
        binding.unsub()
      if binding.task and not binding.task.done():
        binding.task.cancel()
