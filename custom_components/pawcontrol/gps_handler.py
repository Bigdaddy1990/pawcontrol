from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN


def _get_entry(hass: HomeAssistant, call: ServiceCall):
    entry_id = call.data.get("config_entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if not entry:
            raise ServiceValidationError("Config entry not found")
        return entry
    # Fallback: first loaded entry
    domain = hass.data.get(DOMAIN, {})
    for eid in domain.keys():
        entry = hass.config_entries.async_get_entry(eid)
        if entry:
            return entry
    raise ServiceValidationError("No loaded Paw Control entries")


def _dog_id(entry, call: ServiceCall) -> str:
    dog_id = call.data.get("dog_id")
    if dog_id:
        return dog_id
    dogs = (entry.options or {}).get("dogs") or []
    if dogs and isinstance(dogs, list):
        return dogs[0].get("dog_id") or dogs[0].get("name") or "dog"
    return "dog"


async def async_update_location(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = _get_entry(hass, call)
    coord = getattr(entry, "runtime_data", None)
    coordinator = getattr(coord, "coordinator", None) if coord else None
    if not coordinator:
        # legacy fallback
        coordinator = (
            hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
        )
    if not coordinator:
        raise ServiceValidationError("Coordinator not available")

    dog = _dog_id(entry, call)
    lat = float(call.data.get("latitude"))
    lon = float(call.data.get("longitude"))
    acc = call.data.get("accuracy")
    acc = float(acc) if acc is not None else None

    # Update safe-zone and live distance via coordinator
    coordinator.process_location(dog, lat, lon, acc)

    # Mark last action
    try:
        coordinator._dog_data[dog]["statistics"]["last_action"] = (
            dt_util.now().isoformat()
        )
        coordinator._dog_data[dog]["statistics"]["last_action_type"] = (
            "gps_location_posted"
        )
    except Exception:
        pass


async def async_start_walk(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = _get_entry(hass, call)
    coord = getattr(entry, "runtime_data", None)
    coordinator = getattr(coord, "coordinator", None) if coord else None
    if not coordinator:
        coordinator = (
            hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
        )
    if not coordinator:
        raise ServiceValidationError("Coordinator not available")
    dog = _dog_id(entry, call)
    src = call.data.get("source") or "manual"
    coordinator.start_walk(dog, src)


async def async_end_walk(hass: HomeAssistant, call: ServiceCall) -> None:
    entry = _get_entry(hass, call)
    coord = getattr(entry, "runtime_data", None)
    coordinator = getattr(coord, "coordinator", None) if coord else None
    if not coordinator:
        coordinator = (
            hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinator")
        )
    if not coordinator:
        raise ServiceValidationError("Coordinator not available")
    dog = _dog_id(entry, call)
    reason = call.data.get("reason") or "manual"
    coordinator.end_walk(dog, reason)


async def async_pause_tracking(hass: HomeAssistant, call: ServiceCall) -> None:
    # Placeholder for pause state; can be stored on coordinator if needed.
    return


async def async_resume_tracking(hass: HomeAssistant, call: ServiceCall) -> None:
    # Placeholder for resume state.
    return


class PawControlGPSHandler:
    """Helper class to expose GPS service methods."""

    async def async_update_location(
        self, hass: HomeAssistant, call: ServiceCall
    ) -> None:
        await async_update_location(hass, call)

    async def async_start_walk(self, hass: HomeAssistant, call: ServiceCall) -> None:
        await async_start_walk(hass, call)

    async def async_end_walk(self, hass: HomeAssistant, call: ServiceCall) -> None:
        await async_end_walk(hass, call)

    async def async_pause_tracking(
        self, hass: HomeAssistant, call: ServiceCall
    ) -> None:
        await async_pause_tracking(hass, call)

    async def async_resume_tracking(
        self, hass: HomeAssistant, call: ServiceCall
    ) -> None:
        await async_resume_tracking(hass, call)
