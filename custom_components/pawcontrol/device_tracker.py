
from __future__ import annotations
from typing import Any
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
PARALLEL_UPDATES = 0

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    dogs = (entry.options or {}).get("dogs", [])
    entities: list[PawDeviceTracker] = []
    for d in dogs:
        dog_id = d.get("dog_id") or d.get("name")
        name = d.get("name") or dog_id or "Dog"
        if not dog_id:
            continue
        entities.append(PawDeviceTracker(hass, entry.entry_id, dog_id, name))
    if entities:
        async_add_entities(entities, update_before_add=False)

class PawDeviceTracker(TrackerEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, dog_id: str, title: str):
        self.hass = hass
        self._dog = dog_id
        self._title = title
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.tracker"
        self._attr_name = f"{title} Tracker"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, dog_id)}, name=f"Hund {title}", manufacturer="Paw Control", model="Tracker")
        self._lat: float | None = None
        self._lon: float | None = None
        self._acc: float | None = None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    async def async_added_to_hass(self) -> None:
        sig = f"{DOMAIN}_gps_update_{self._dog}"
        self.async_on_remove(async_dispatcher_connect(self.hass, sig, self._on_gps))

    def _on_gps(self, lat: float, lon: float, acc: float | None = None) -> None:
        self._lat, self._lon, self._acc = lat, lon, acc
        self.async_write_ha_state()

    @property
    def latitude(self) -> float | None:
        return self._lat

    @property
    def longitude(self) -> float | None:
        return self._lon

    @property
    def location_accuracy(self) -> float | None:
        return self._acc
