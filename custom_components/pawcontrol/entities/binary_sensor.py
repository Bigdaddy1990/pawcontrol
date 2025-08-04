"""Binary sensor platform for Paw Control - REPARIERT UND VEREINFACHT."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PawControlCoordinator
from .entities import PawControlBinarySensorEntity
from .helpers.entity import get_icon, parse_datetime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name
    
    entities = [
        PawControlIsHungryBinarySensor(coordinator, dog_name),
        PawControlNeedsWalkBinarySensor(coordinator, dog_name),
        PawControlIsOutsideBinarySensor(coordinator, dog_name),
        PawControlEmergencyModeBinarySensor(coordinator, dog_name),
        PawControlVisitorModeBinarySensor(coordinator, dog_name),
        PawControlNeedsAttentionBinarySensor(coordinator, dog_name),
        PawControlGPSTrackingBinarySensor(coordinator, dog_name),
    ]
    
    async_add_entities(entities)


class PawControlIsHungryBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for hunger status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="is_hungry")

    @property
    def is_on(self) -> bool | None:
        """Return true if the dog is hungry."""
        if not self.coordinator.data:
            return None
        
        feeding = self.coordinator.data.get("feeding_status", {})
        return feeding.get("needs_feeding", True)


class PawControlNeedsWalkBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for walk need status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="needs_walk", icon=get_icon("walk"))

    @property
    def is_on(self) -> bool | None:
        """Return true if the dog needs a walk."""
        if not self.coordinator.data:
            return None
        
        activity = self.coordinator.data.get("activity_status", {})
        return activity.get("needs_walk", True)


class PawControlIsOutsideBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for outside status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="is_outside",
            icon=get_icon("outside"),
            device_class=BinarySensorDeviceClass.PRESENCE,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the dog is outside."""
        if not self.coordinator.data:
            return None
        
        activity = self.coordinator.data.get("activity_status", {})
        return activity.get("was_outside", False)


class PawControlEmergencyModeBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for emergency mode."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="emergency_mode",
            icon=get_icon("emergency"),
            device_class=BinarySensorDeviceClass.PROBLEM,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if emergency mode is active."""
        try:
            emergency_state = self.hass.states.get(f"input_boolean.{self._dog_name}_emergency_mode")
            return emergency_state.state == "on" if emergency_state else False
        except Exception as e:
            _LOGGER.error("Error checking emergency mode: %s", e)
            return False


class PawControlVisitorModeBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for visitor mode."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="visitor_mode", icon=get_icon("visitor"))

    @property
    def is_on(self) -> bool | None:
        """Return true if visitor mode is active."""
        try:
            visitor_state = self.hass.states.get(
                f"input_boolean.{self._dog_name}_visitor_mode_input"
            )
            return visitor_state.state == "on" if visitor_state else False
        except Exception as e:
            _LOGGER.error("Error checking visitor mode: %s", e)
            return False


class PawControlNeedsAttentionBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for needs attention status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="needs_attention",
            icon="mdi:bell-alert",
            device_class=BinarySensorDeviceClass.PROBLEM,
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if dog needs attention."""
        if not self.coordinator.data:
            return None
        
        try:
            feeding = self.coordinator.data.get("feeding_status", {})
            activity = self.coordinator.data.get("activity_status", {})
            
            # Check if not fed for too long
            last_feeding = feeding.get("last_feeding")
            if last_feeding:
                try:
                    last_fed_time = parse_datetime(last_feeding)
                    if last_fed_time and datetime.now() - last_fed_time > timedelta(hours=12):
                        return True
                except ValueError:
                    pass
            
            # Check if not walked for too long
            last_walk = activity.get("last_walk")
            if last_walk:
                try:
                    last_walk_time = parse_datetime(last_walk)
                    if last_walk_time and datetime.now() - last_walk_time > timedelta(hours=8):
                        return True
                except ValueError:
                    pass
            
            # Check if emergency mode is active
            emergency_state = self.hass.states.get(f"input_boolean.{self._dog_name}_emergency_mode")
            if emergency_state and emergency_state.state == "on":
                return True
            
            return False
            
        except Exception as e:
            _LOGGER.error("Error calculating attention need: %s", e)
            return None


class PawControlGPSTrackingBinarySensor(PawControlBinarySensorEntity):
    """Binary sensor for GPS tracking status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="gps_tracking", icon=get_icon("gps"))

    @property
    def is_on(self) -> bool | None:
        """Return true if GPS tracking is active."""
        if not self.coordinator.data:
            return None
        
        location = self.coordinator.data.get("location_status", {})
        return location.get("gps_available", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data:
            location = self.coordinator.data.get("location_status", {})
            attrs.update({
                "gps_signal": location.get("gps_signal", 0),
                "current_location": location.get("current_location", "Unknown"),
            })
        
        return attrs
