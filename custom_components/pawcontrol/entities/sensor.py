"""Sensor platform for Paw Control - REPARIERT UND VEREINFACHT."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PawControlCoordinator
from .entities import PawControlSensorEntity
from .helpers.entity import get_icon, parse_datetime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name
    
    entities = [
        PawControlStatusSensor(coordinator, dog_name),
        PawControlDailySummarySensor(coordinator, dog_name),
        PawControlLastWalkSensor(coordinator, dog_name),
        PawControlWalkCountSensor(coordinator, dog_name),
        PawControlWeightSensor(coordinator, dog_name),
        PawControlHealthStatusSensor(coordinator, dog_name),
        PawControlLocationSensor(coordinator, dog_name),
        PawControlGPSSignalSensor(coordinator, dog_name),
    ]
    
    async_add_entities(entities)


class PawControlStatusSensor(PawControlSensorEntity):
    """Sensor for overall dog status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="status")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        return self.coordinator.get_status_summary()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data:
            feeding = self.coordinator.data.get("feeding_status", {})
            activity = self.coordinator.data.get("activity_status", {})
            
            attrs.update({
                "morning_fed": feeding.get("morning_fed", False),
                "evening_fed": feeding.get("evening_fed", False),
                "was_outside": activity.get("was_outside", False),
                "walked_today": activity.get("walked_today", False),
                "poop_done": activity.get("poop_done", False),
                "walk_count": activity.get("walk_count", 0),
            })
        
        return attrs


class PawControlDailySummarySensor(PawControlSensorEntity):
    """Sensor for daily summary."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="daily_summary", icon="mdi:calendar-today")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Keine Daten verfügbar"
        
        try:
            activity = self.coordinator.data.get("activity_status", {})
            feeding = self.coordinator.data.get("feeding_status", {})
            
            walk_count = activity.get("walk_count", 0)
            fed_count = sum([
                feeding.get("morning_fed", False),
                feeding.get("evening_fed", False)
            ])
            
            return f"🚶 {walk_count} Spaziergänge, 🍽️ {fed_count} Mahlzeiten"
            
        except Exception as e:
            _LOGGER.error("Error getting daily summary: %s", e)
            return "Fehler beim Laden"


class PawControlLastWalkSensor(PawControlSensorEntity):
    """Sensor for last walk time."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="last_walk",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=get_icon("walk"),
        )

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        try:
            activity = self.coordinator.data.get("activity_status", {})
            last_walk = parse_datetime(activity.get("last_walk"))
            return last_walk
        except Exception as e:
            _LOGGER.error("Error parsing last walk time: %s", e)
            return None


class PawControlWalkCountSensor(PawControlSensorEntity):
    """Sensor for walk count."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="walk_count", icon=get_icon("walk"))

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return 0
        
        activity = self.coordinator.data.get("activity_status", {})
        return activity.get("walk_count", 0)


class PawControlWeightSensor(PawControlSensorEntity):
    """Sensor for weight."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="weight",
            icon=get_icon("weight"),
            device_class=SensorDeviceClass.WEIGHT,
            unit="kg",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        health = self.coordinator.data.get("health_status", {})
        return health.get("weight")


class PawControlHealthStatusSensor(PawControlSensorEntity):
    """Sensor for health status."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="health_status")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Unbekannt"
        
        health = self.coordinator.data.get("health_status", {})
        return health.get("status", "Gut")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data:
            health = self.coordinator.data.get("health_status", {})
            attrs.update({
                "weight": health.get("weight"),
                "health_notes": health.get("health_notes", ""),
            })
        
        return attrs


class PawControlLocationSensor(PawControlSensorEntity):
    """Sensor for current location."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_name=dog_name, key="location")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return "Unbekannt"
        
        location = self.coordinator.data.get("location_status", {})
        return location.get("current_location", "Unbekannt")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data:
            location = self.coordinator.data.get("location_status", {})
            current_loc = location.get("current_location", "")
            
            # Try to parse coordinates
            if current_loc and "," in current_loc:
                try:
                    lat_str, lon_str = current_loc.split(",")
                    attrs.update({
                        "latitude": float(lat_str.strip()),
                        "longitude": float(lon_str.strip()),
                    })
                except (ValueError, IndexError):
                    pass
            
            attrs.update({
                "gps_signal": location.get("gps_signal", 0),
                "gps_available": location.get("gps_available", False),
            })
        
        return attrs


class PawControlGPSSignalSensor(PawControlSensorEntity):
    """Sensor for GPS signal strength."""

    def __init__(self, coordinator: PawControlCoordinator, dog_name: str) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            dog_name=dog_name,
            key="gps_signal",
            icon=get_icon("signal"),
            unit="%",
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return 0
        
        location = self.coordinator.data.get("location_status", {})
        return location.get("gps_signal", 0)
