"""Diagnostics helpers for Paw Control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .gps_settings import GPSSettingsStore
from .route_store import RouteHistoryStore

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.device_registry import DeviceEntry


_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Collect diagnostics for a config entry."""
    data: dict[str, Any] = {
        "options": entry.options or {},
        "version": hass.data.get(DOMAIN, {}).get("version"),
    }
    # Include GPS settings and a short route index for the first dog
    try:
        store1 = GPSSettingsStore(hass, entry.entry_id, DOMAIN)
        store2 = RouteHistoryStore(hass, entry.entry_id, DOMAIN)
        data["gps_settings"] = await store1.async_load()
        dogs = (entry.options or {}).get("dogs") or []
        dog = (dogs[0].get("dog_id") or dogs[0].get("name")) if dogs else "dog"
        data["route_history_index"] = await store2.async_list(dog)
        # Truncate list length for diagnostics
        if (
            isinstance(data["route_history_index"], list)
            and len(data["route_history_index"]) > 50
        ):
            data["route_history_index"] = data["route_history_index"][-50:]
    except (HomeAssistantError, OSError, ValueError) as exc:
        _LOGGER.warning("Failed to collect diagnostics data: %s", exc)
    return data


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Collect diagnostics for a specific device."""
    # Try to extract dog_id from device identifiers
    dog_id = None
    for domain, ident in device.identifiers:
        if domain == DOMAIN:
            dog_id = ident
            break
    base = await async_get_config_entry_diagnostics(hass, entry)
    base["device"] = {"name": device.name, "id": device.id, "dog_id": dog_id}
    return base
