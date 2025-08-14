"""Device tracker platform for Paw Control integration."""

from __future__ import annotations

import logging

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .compat import DeviceInfo
from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS, DOMAIN, MODULE_GPS
from .coordinator import PawControlCoordinator

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, 
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Paw Control device tracker entities."""
    coordinator: PawControlCoordinator = entry.runtime_data.coordinator
    
    if not coordinator.last_update_success:
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            raise PlatformNotReady
    
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])
    
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue
        
        # Only create device tracker if GPS module is enabled
        modules = dog.get("modules", {})
        if modules.get(MODULE_GPS, False):
            entities.append(PawDeviceTracker(coordinator, entry, dog_id))
    
    if entities:
        async_add_entities(entities, update_before_add=True)


class PawDeviceTracker(CoordinatorEntity, TrackerEntity):
    """Device tracker for a dog."""
    
    _attr_has_entity_name = True
    
    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the device tracker."""
        super().__init__(coordinator)
        self.entry = entry
        self.dog_id = dog_id
        
        # Get dog info
        self._dog_config = self._get_dog_config()
        dog_name = self._dog_config.get(CONF_DOG_NAME, dog_id)
        
        # Set attributes
        self._attr_unique_id = f"{entry.entry_id}_{dog_id}_tracker"
        self._attr_translation_key = "dog_tracker"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )
    
    def _get_dog_config(self) -> dict:
        """Get dog configuration from entry options."""
        dogs = self.entry.options.get(CONF_DOGS, [])
        for dog in dogs:
            if dog.get(CONF_DOG_ID) == self.dog_id:
                return dog
        return {}
    
    @property
    def name(self) -> str:
        """Return the name of the entity."""
        dog_name = self._dog_config.get(CONF_DOG_NAME, self.dog_id)
        return f"{dog_name} Location"
    
    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS
    
    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        location_data = self._get_location_data()
        
        # If we have stored GPS coordinates, use them
        if location_data.get("last_gps_update"):
            # Parse from stored location if available
            # For now, return None as we need actual GPS implementation
            return None
        
        # Check if we're at home and return home coordinates
        if location_data.get("is_home", True):
            return location_data.get("home_lat")
        
        return None
    
    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        location_data = self._get_location_data()
        
        # If we have stored GPS coordinates, use them
        if location_data.get("last_gps_update"):
            # Parse from stored location if available
            # For now, return None as we need actual GPS implementation
            return None
        
        # Check if we're at home and return home coordinates
        if location_data.get("is_home", True):
            return location_data.get("home_lon")
        
        return None
    
    @property
    def location_accuracy(self) -> float | None:
        """Return the location accuracy of the device."""
        location_data = self._get_location_data()
        
        # Return stored accuracy or default
        accuracy = location_data.get("last_accuracy")
        if accuracy is not None:
            return float(accuracy)
        
        # Default accuracy when at home
        if location_data.get("is_home", True):
            return 10.0  # 10 meters when at home
        
        return None
    
    @property
    def location_name(self) -> str | None:
        """Return a location name for the current location of the device."""
        location_data = self._get_location_data()
        current_location = location_data.get("current_location", "unknown")
        
        if current_location == "home":
            return "Home"
        elif current_location == "away":
            return None  # Let HA determine based on zones
        
        return current_location
    
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return (
            super().available 
            and self.dog_id in self.coordinator._dog_data
            and self._get_location_data() is not None
        )
    
    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        location_data = self._get_location_data()
        
        return {
            "distance_from_home": location_data.get("distance_from_home"),
            "last_gps_update": location_data.get("last_gps_update"),
            "enters_today": location_data.get("enters_today", 0),
            "leaves_today": location_data.get("leaves_today", 0),
            "time_inside_today_min": location_data.get("time_inside_today_min", 0),
        }
    
    def _get_location_data(self) -> dict:
        """Get location data for this dog."""
        dog_data = self.coordinator.get_dog_data(self.dog_id)
        return dog_data.get("location", {}) if dog_data else {}
