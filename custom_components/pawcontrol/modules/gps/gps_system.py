import logging
import asyncio
import datetime
from typing import Optional, Callable, Any, Dict
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import ATTR_LATITUDE, ATTR_LONGITUDE
from homeassistant.helpers.entity import DeviceInfo, Entity, EntityCategory
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.device_tracker import SourceType, DeviceTrackerEntity
from homeassistant.components.binary_sensor import BinarySensorEntity, DEVICE_CLASS_PROBLEM
from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from .utils import register_services

_LOGGER = logging.getLogger(__name__)

class PawControlGPSCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, device_id: str, update_interval: int = 30):
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_gps_coordinator",
            update_interval=datetime.timedelta(seconds=update_interval),
        )
        self.device_id = device_id
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.gps_source = None

    async def _async_update_data(self):
        _LOGGER.debug("Fetching GPS data for device %s", self.device_id)
        self.latitude = 51.0504
        self.longitude = 13.7373
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.gps_source
        }

class PawControlGPSTracker(DeviceTrackerEntity):
    def __init__(self, coordinator: PawControlGPSCoordinator, device_id: str):
        self.coordinator = coordinator
        self._attr_name = f"PawControl GPS Tracker {device_id}"
        self._attr_unique_id = f"{DOMAIN}_gps_tracker_{device_id}"
        self._device_id = device_id
        self._attr_should_poll = False
        self._attr_source_type = SourceType.GPS

    @property
    def latitude(self) -> Optional[float]:
        return self.coordinator.latitude

    @property
    def longitude(self) -> Optional[float]:
        return self.coordinator.longitude

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return {"source": self.coordinator.gps_source}

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers = {(DOMAIN, self._device_id)},
            name = self._attr_name,
            manufacturer = "PawControl"
        )

    async def async_update(self):
        await self.coordinator.async_request_refresh()

class PawControlLocationSensor(Entity):
    def __init__(self, coordinator, device_id: str):
        self._coordinator = coordinator
        self._attr_name = f"PawControl GPS Location {device_id}"
        self._attr_unique_id = f"{DOMAIN}_gps_location_{device_id}"
        self._device_id = device_id
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def state(self):
        return (
            f"{self._coordinator.latitude}, {self._coordinator.longitude}"
            if self._coordinator.latitude and self._coordinator.longitude else None
        )

    @property
    def extra_state_attributes(self):
        return {
            "latitude": self._coordinator.latitude,
            "longitude": self._coordinator.longitude
        }

class PawControlInZoneBinarySensor(BinarySensorEntity):
    def __init__(self, coordinator, device_id: str):
        self._coordinator = coordinator
        self._attr_name = f"PawControl In Zone {device_id}"
        self._attr_unique_id = f"{DOMAIN}_in_zone_{device_id}"
        self._device_id = device_id
        self._attr_device_class = DEVICE_CLASS_PROBLEM

    @property
    def is_on(self):
        return True

    @property
    def extra_state_attributes(self):
        return {
            "latitude": self._coordinator.latitude,
            "longitude": self._coordinator.longitude
        }

class PawControlRefreshGPSButton(ButtonEntity):
    def __init__(self, coordinator, device_id: str):
        self._coordinator = coordinator
        self._attr_name = f"PawControl GPS Refresh {device_id}"
        self._attr_unique_id = f"{DOMAIN}_gps_refresh_{device_id}"

    async def async_press(self):
        await self._coordinator._async_update_data()

async def async_setup_entry(hass: HomeAssistant, entry):
    _LOGGER.info("Setting up PawControl GPS system from config entry")
    device_id = entry.data.get("device_id", "default")
    update_interval = entry.options.get("gps_update_interval", 30)

    coordinator = PawControlGPSCoordinator(hass, device_id, update_interval)
    await coordinator.async_config_entry_first_refresh()

    tracker = PawControlGPSTracker(coordinator, device_id)

    async def async_add_entities():
        async_add_entities = hass.data[DOMAIN].get("async_add_entities")
        if async_add_entities:
            async_add_entities([tracker], update_before_add=True)
        else:
            _LOGGER.error("async_add_entities not found in hass.data[DOMAIN]")

    hass.async_create_task(async_add_entities())

    async def handle_manual_gps_update(call):
        _LOGGER.info("Manual GPS update requested.")
        await coordinator.async_request_refresh()

    register_services(hass, DOMAIN, {"update_gps": handle_manual_gps_update})

    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    _LOGGER.info("Unloading PawControl GPS system")
    return True
