"""Binary sensor platform for Paw Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_MODULES,
    MODULE_WALK,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_GROOMING,
    MODULE_GPS,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control binary sensor entities."""
    coordinator: PawControlCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])
    
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue
        
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})
        
        # Walk module binary sensors
        if modules.get(MODULE_WALK):
            entities.extend([
                NeedsWalkBinarySensor(coordinator, dog_id, dog_name),
                WalkInProgressBinarySensor(coordinator, dog_id, dog_name),
            ])
        
        # Feeding module binary sensors
        if modules.get(MODULE_FEEDING):
            entities.append(
                IsHungryBinarySensor(coordinator, dog_id, dog_name)
            )
        
        # Grooming module binary sensors
        if modules.get(MODULE_GROOMING):
            entities.append(
                NeedsGroomingBinarySensor(coordinator, dog_id, dog_name)
            )
        
        # GPS module binary sensors
        if modules.get(MODULE_GPS):
            entities.append(
                IsHomeBinarySensor(coordinator, dog_id, dog_name)
            )
    
    # Global binary sensors
    entities.extend([
        VisitorModeBinarySensor(coordinator),
        EmergencyModeBinarySensor(coordinator),
    ])
    
    async_add_entities(entities, True)


class PawControlBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for Paw Control binary sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._sensor_type = sensor_type
        
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.binary_sensor.{sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def dog_data(self) -> dict:
        """Get dog data from coordinator."""
        return self.coordinator.get_dog_data(self._dog_id)


class NeedsWalkBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for whether dog needs a walk."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "needs_walk")
        self._attr_name = "Needs Walk"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:dog-side"

    @property
    def is_on(self) -> bool:
        """Return True if dog needs a walk."""
        return self.dog_data.get("walk", {}).get("needs_walk", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        walk_data = self.dog_data.get("walk", {})
        return {
            "last_walk": walk_data.get("last_walk"),
            "walks_today": walk_data.get("walks_today", 0),
        }


class WalkInProgressBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for whether walk is in progress."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_in_progress")
        self._attr_name = "Walk In Progress"
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_icon = "mdi:walk"

    @property
    def is_on(self) -> bool:
        """Return True if walk is in progress."""
        return self.dog_data.get("walk", {}).get("walk_in_progress", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        walk_data = self.dog_data.get("walk", {})
        return {
            "start_time": walk_data.get("walk_start_time"),
            "current_duration_min": walk_data.get("walk_duration_min", 0),
            "current_distance_m": walk_data.get("walk_distance_m", 0),
        }


class IsHungryBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for whether dog is hungry."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "is_hungry")
        self._attr_name = "Is Hungry"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:food-drumstick-off"

    @property
    def is_on(self) -> bool:
        """Return True if dog is hungry."""
        return self.dog_data.get("feeding", {}).get("is_hungry", False)

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        return "mdi:food-drumstick-off" if self.is_on else "mdi:food-drumstick"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        feeding_data = self.dog_data.get("feeding", {})
        return {
            "last_feeding": feeding_data.get("last_feeding"),
            "last_meal_type": feeding_data.get("last_meal_type"),
            "feedings_today": feeding_data.get("feedings_today", {}),
        }


class NeedsGroomingBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for whether dog needs grooming."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "needs_grooming")
        self._attr_name = "Needs Grooming"
        self._attr_device_class = BinarySensorDeviceClass.PROBLEM
        self._attr_icon = "mdi:content-cut"

    @property
    def is_on(self) -> bool:
        """Return True if dog needs grooming."""
        return self.dog_data.get("grooming", {}).get("needs_grooming", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        grooming_data = self.dog_data.get("grooming", {})
        return {
            "last_grooming": grooming_data.get("last_grooming"),
            "grooming_type": grooming_data.get("grooming_type"),
            "interval_days": grooming_data.get("grooming_interval_days", 30),
        }


class IsHomeBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for whether dog is at home."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "is_home")
        self._attr_name = "Is Home"
        self._attr_device_class = BinarySensorDeviceClass.PRESENCE
        self._attr_icon = "mdi:home"

    @property
    def is_on(self) -> bool:
        """Return True if dog is at home."""
        return self.dog_data.get("location", {}).get("is_home", True)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        location_data = self.dog_data.get("location", {})
        return {
            "current_location": location_data.get("current_location", "home"),
            "distance_from_home": location_data.get("distance_from_home", 0),
            "last_gps_update": location_data.get("last_gps_update"),
        }


class VisitorModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for visitor mode status."""

    _attr_has_entity_name = True
    _attr_name = "Visitor Mode"
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_icon = "mdi:account-group"

    def __init__(self, coordinator: PawControlCoordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}.global.binary_sensor.visitor_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool:
        """Return True if visitor mode is active."""
        return self.coordinator.visitor_mode


class EmergencyModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for emergency mode status."""

    _attr_has_entity_name = True
    _attr_name = "Emergency Mode"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: PawControlCoordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}.global.binary_sensor.emergency_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def is_on(self) -> bool:
        """Return True if emergency mode is active."""
        return self.coordinator.emergency_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self.coordinator.emergency_mode:
            return {
                "level": self.coordinator.emergency_level,
            }
        return {}
