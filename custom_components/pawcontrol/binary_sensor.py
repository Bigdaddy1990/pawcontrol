"""Binary sensor platform for PawControl integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    ICON_DOG,
    ICON_FOOD,
    ICON_WALK,
    ICON_EMERGENCY,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl binary sensor entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Always create basic binary sensors
        entities.extend([
            PawControlIsHungryBinarySensor(coordinator, config),
            PawControlNeedsWalkBinarySensor(coordinator, config),
            PawControlNeedsAttentionBinarySensor(coordinator, config),
            PawControlIsOutsideBinarySensor(coordinator, config),
            PawControlEmergencyModeBinarySensor(coordinator, config),
            PawControlVisitorModeBinarySensor(coordinator, config),
        ])
        
        # Add module-specific binary sensors
        modules = config.get("modules", {})
        
        if modules.get("gps", {}).get("enabled", False):
            entities.append(PawControlGPSTrackingBinarySensor(coordinator, config))
        
        if modules.get("health", {}).get("enabled", False):
            entities.append(PawControlHealthAlertBinarySensor(coordinator, config))
    
    async_add_entities(entities)


class PawControlBinarySensorBase(CoordinatorEntity, BinarySensorEntity):
    """Base class for PawControl binary sensors."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_")

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._dog_id)},
            "name": f"PawControl - {self._dog_name}",
            "manufacturer": "PawControl",
            "model": "Dog Management System",
            "sw_version": "1.0.0",
        }


class PawControlIsHungryBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for hunger status."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_is_hungry"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Ist hungrig"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_FOOD

    @property
    def is_on(self):
        """Return true if hungry."""
        return self.coordinator.data.get("status", {}).get("is_hungry", False)

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.PROBLEM


class PawControlNeedsWalkBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for walk requirement."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_needs_walk"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Braucht Spaziergang"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WALK

    @property
    def is_on(self):
        """Return true if needs walk."""
        return self.coordinator.data.get("status", {}).get("needs_walk", False)

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.PROBLEM


class PawControlNeedsAttentionBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for attention requirement."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_needs_attention"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Braucht Aufmerksamkeit"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:heart"

    @property
    def is_on(self):
        """Return true if needs attention."""
        return self.coordinator.data.get("status", {}).get("needs_attention", False)

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.PROBLEM


class PawControlIsOutsideBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for outside status."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_is_outside"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Ist draußen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:tree"

    @property
    def is_on(self):
        """Return true if outside."""
        return self.coordinator.data.get("status", {}).get("is_outside", False)

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.PRESENCE


class PawControlEmergencyModeBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for emergency mode."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_emergency_mode"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Notfallmodus"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_EMERGENCY

    @property
    def is_on(self):
        """Return true if emergency mode is active."""
        return self.coordinator.data.get("status", {}).get("emergency_mode", False)

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.SAFETY

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        status = self.coordinator.data.get("status", {})
        attrs = {}
        if status.get("emergency_reason"):
            attrs["reason"] = status["emergency_reason"]
        return attrs


class PawControlVisitorModeBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for visitor mode."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_visitor_mode"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Besuchermodus"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:account-group"

    @property
    def is_on(self):
        """Return true if visitor mode is active."""
        return self.coordinator.data.get("status", {}).get("visitor_mode", False)

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        status = self.coordinator.data.get("status", {})
        attrs = {}
        if status.get("visitor_name"):
            attrs["visitor"] = status["visitor_name"]
        if status.get("visitor_instructions"):
            attrs["instructions"] = status["visitor_instructions"]
        return attrs


class PawControlGPSTrackingBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for GPS tracking status."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_gps_tracking"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} GPS-Tracking"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:crosshairs-gps"

    @property
    def is_on(self):
        """Return true if GPS tracking is active."""
        location = self.coordinator.data.get("location", {})
        return location.get("last_update") is not None

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.CONNECTIVITY


class PawControlHealthAlertBinarySensor(PawControlBinarySensorBase):
    """Binary sensor for health alerts."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_alert"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsalarm"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:medical-bag"

    @property
    def is_on(self):
        """Return true if there's a health alert."""
        health = self.coordinator.data.get("health", {})
        profile = self.coordinator.data.get("profile", {})
        
        # Check for abnormal temperature
        temp = health.get("temperature", 38.5)
        if temp < 37.5 or temp > 39.5:
            return True
        
        # Check for poor health status
        health_status = profile.get("health_status", "Gut")
        if health_status in ["Unwohl", "Krank"]:
            return True
        
        # Check for symptoms
        if health.get("symptoms"):
            return True
        
        return False

    @property
    def device_class(self):
        """Return the device class."""
        return BinarySensorDeviceClass.PROBLEM

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        health = self.coordinator.data.get("health", {})
        profile = self.coordinator.data.get("profile", {})
        
        return {
            "temperature": health.get("temperature"),
            "health_status": profile.get("health_status"),
            "symptoms": health.get("symptoms", []),
        }
