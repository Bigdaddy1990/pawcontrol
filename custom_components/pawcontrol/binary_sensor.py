"""Binary sensor platform for Paw Control integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .entity import PawControlBinarySensorEntity

PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control binary sensor entities."""
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

        modules = dog.get(CONF_DOG_MODULES, {})

        # Walk module binary sensors
        if modules.get(MODULE_WALK):
            entities.extend(
                [
                    NeedsWalkBinarySensor(coordinator, entry, dog_id),
                    WalkInProgressBinarySensor(coordinator, entry, dog_id),
                ]
            )

        # Feeding module binary sensors
        if modules.get(MODULE_FEEDING):
            entities.append(IsHungryBinarySensor(coordinator, entry, dog_id))

        # Grooming module binary sensors
        if modules.get(MODULE_GROOMING):
            entities.append(NeedsGroomingBinarySensor(coordinator, entry, dog_id))

        # GPS module binary sensors
        if modules.get(MODULE_GPS):
            entities.append(IsHomeBinarySensor(coordinator, entry, dog_id))

    # Global binary sensors
    entities.extend(
        [
            VisitorModeBinarySensor(coordinator, entry),
            EmergencyModeBinarySensor(coordinator, entry),
        ]
    )

    async_add_entities(entities, True)


class NeedsWalkBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor for whether dog needs a walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "needs_walk",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
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


class WalkInProgressBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor for whether walk is in progress."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walk_in_progress",
            device_class=BinarySensorDeviceClass.RUNNING,
        )
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


class IsHungryBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor for whether dog is hungry."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "is_hungry",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
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


class NeedsGroomingBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor for whether dog needs grooming."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "needs_grooming",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )
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


class IsHomeBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor for whether dog is at home."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "is_home",
            device_class=BinarySensorDeviceClass.PRESENCE,
        )
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
            "enters_today": location_data.get("enters_today", 0),
            "leaves_today": location_data.get("leaves_today", 0),
            "time_inside_today_min": location_data.get("time_inside_today_min", 0.0),
        }


class VisitorModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for visitor mode status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_icon = "mdi:account-group"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PawControlCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_visitor_mode"
        self._attr_translation_key = "visitor_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return "Visitor Mode"

    @property
    def is_on(self) -> bool:
        """Return True if visitor mode is active."""
        return self.coordinator.visitor_mode


class EmergencyModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for emergency mode status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PawControlCoordinator, entry: ConfigEntry):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_emergency_mode"
        self._attr_translation_key = "emergency_mode"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return "Emergency Mode"

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
