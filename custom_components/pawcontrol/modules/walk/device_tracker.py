"""Device tracker platform for Paw Control."""
from __future__ import annotations

import logging
from homeassistant.components.device_tracker import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PawControlCoordinator
from .entities import PawControlDeviceTrackerEntity
from .gps_handler import PawControlGPSHandler
from .helpers.entity import get_icon
from .helpers.gps import is_valid_gps_coords

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device tracker platform."""
    coordinator: PawControlCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name

    if "gps_handler" not in hass.data[DOMAIN][config_entry.entry_id]:
        gps_handler = PawControlGPSHandler(hass, dog_name, config_entry.data)
        await gps_handler.async_setup()
        hass.data[DOMAIN][config_entry.entry_id]["gps_handler"] = gps_handler
    else:
        gps_handler = hass.data[DOMAIN][config_entry.entry_id]["gps_handler"]

    entities = [PawControlDeviceTracker(coordinator, dog_name, gps_handler)]

    async_add_entities(entities)


class PawControlDeviceTracker(PawControlDeviceTrackerEntity):
    """GPS device tracker for the dog."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_name: str,
        gps_handler: PawControlGPSHandler,
    ) -> None:
        super().__init__(coordinator, dog_name=dog_name, key="device_tracker", icon=get_icon("gps"))
        self._gps_handler = gps_handler

    def _update_state(self) -> None:
        location = self._gps_handler.get_current_location()
        if location and is_valid_gps_coords(location[0], location[1]):
            self._state = {"lat": location[0], "lon": location[1]}
        else:
            self._state = None

    @property
    def latitude(self):
        return self._state["lat"] if self._state else None

    @property
    def longitude(self):
        return self._state["lon"] if self._state else None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

