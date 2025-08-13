from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import DOMAIN

DEFAULT_DOG_ID = "dog"


def _get_entry(hass: HomeAssistant, call: ServiceCall) -> ConfigEntry:
    """Return a matching loaded entry for the GPS service call.

    The call may target a specific config entry via ``config_entry_id``. If not
    provided, the first loaded Paw Control entry is returned.
    """
    entry_id = call.data.get("config_entry_id")
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise ServiceValidationError("Config entry not found")
        return entry

    try:
        return next(
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        )
    except StopIteration as err:
        raise ServiceValidationError("No loaded Paw Control entries") from err


def _get_dog_id(entry: ConfigEntry, call: ServiceCall) -> str:
    """Return target dog identifier for a service call."""
    dog_id = call.data.get("dog_id")
    if dog_id:
        return dog_id

    dogs = entry.options.get("dogs")
    if isinstance(dogs, list) and dogs:
        first = dogs[0]
        return first.get("dog_id") or first.get("name") or DEFAULT_DOG_ID

    return DEFAULT_DOG_ID


def _get_entry_and_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[ConfigEntry, Any]:
    """Resolve config entry and its coordinator."""
    entry = _get_entry(hass, call)
    runtime = getattr(entry, "runtime_data", None)
    coordinator = getattr(runtime, "coordinator", None) if runtime else None
    if coordinator is None:
        raise ServiceValidationError("Coordinator not available")
    return entry, coordinator


async def async_update_location(hass: HomeAssistant, call: ServiceCall) -> None:
    entry, coordinator = _get_entry_and_coordinator(hass, call)

    dog = _get_dog_id(entry, call)
    lat = float(call.data.get("latitude"))
    lon = float(call.data.get("longitude"))
    acc = call.data.get("accuracy")
    acc = float(acc) if acc is not None else None

    # Update safe-zone and live distance via coordinator
    coordinator.process_location(dog, lat, lon, acc)

    # Mark last action
    stats = coordinator._dog_data.setdefault(dog, {}).setdefault("statistics", {})
    stats["last_action"] = dt_util.now().isoformat()
    stats["last_action_type"] = "gps_location_posted"


async def async_start_walk(hass: HomeAssistant, call: ServiceCall) -> None:
    entry, coordinator = _get_entry_and_coordinator(hass, call)
    dog = _get_dog_id(entry, call)
    src = call.data.get("source") or "manual"
    coordinator.start_walk(dog, src)


async def async_end_walk(hass: HomeAssistant, call: ServiceCall) -> None:
    entry, coordinator = _get_entry_and_coordinator(hass, call)
    dog = _get_dog_id(entry, call)
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

    def __init__(self, hass: HomeAssistant, options: dict | None) -> None:
        """Store reference to Home Assistant and configuration options."""
        self.hass = hass
        self.options = options or {}

    async def async_update_location(
        self, hass: HomeAssistant, call: ServiceCall
    ) -> None:
        await async_update_location(hass, call)

    async def async_setup(self) -> None:
        """Set up GPS handler (placeholder for future enhancements)."""
        return

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
