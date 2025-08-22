"""Sensor platform for Paw Control integration.

This module provides comprehensive sensor entities for dog monitoring including
feeding, walking, GPS tracking, health, and activity sensors. All sensors are
designed to meet Home Assistant's Platinum quality standards with full type
annotations, async operations, and robust error handling.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfMass,
    UnitOfTime,
    UnitOfSpeed,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Type aliases for better code readability
SensorValue = Union[str, int, float, datetime, None]
AttributeDict = Dict[str, Any]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control sensor platform.
    
    Creates sensor entities for all configured dogs based on their
    enabled modules. Sensors are organized by functionality and provide
    comprehensive monitoring capabilities.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry containing dog configurations
        async_add_entities: Callback to add sensor entities
    """
    coordinator: PawControlCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    dogs: List[Dict[str, Any]] = entry.data.get(CONF_DOGS, [])
    
    entities: List[PawControlSensorBase] = []
    
    # Create sensors for each configured dog
    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: Dict[str, bool] = dog.get("modules", {})
        
        _LOGGER.debug("Creating sensors for dog: %s (%s)", dog_name, dog_id)
        
        # Base sensors - always created for every dog
        entities.extend(_create_base_sensors(coordinator, dog_id, dog_name))
        
        # Module-specific sensors
        if modules.get(MODULE_FEEDING, False):
            entities.extend(_create_feeding_sensors(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_WALK, False):
            entities.extend(_create_walk_sensors(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_GPS, False):
            entities.extend(_create_gps_sensors(coordinator, dog_id, dog_name))
        
        if modules.get(MODULE_HEALTH, False):
            entities.extend(_create_health_sensors(coordinator, dog_id, dog_name))
    
    # Add all entities at once for better performance
    async_add_entities(entities, update_before_add=True)
    
    _LOGGER.info(
        "Created %d sensor entities for %d dogs",
        len(entities),
        len(dogs)
    )


def _create_base_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlSensorBase]:
    """Create base sensors that are always present for every dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of base sensor entities
    """
    return [
        PawControlLastActionSensor(coordinator, dog_id, dog_name),
        PawControlDogStatusSensor(coordinator, dog_id, dog_name),
        PawControlActivityScoreSensor(coordinator, dog_id, dog_name),
    ]


def _create_feeding_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlSensorBase]:
    """Create feeding-related sensors for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of feeding sensor entities
    """
    sensors = [
        PawControlLastFeedingSensor(coordinator, dog_id, dog_name),
        PawControlLastFeedingHoursSensor(coordinator, dog_id, dog_name),
        PawControlTotalFeedingsTodaySensor(coordinator, dog_id, dog_name),
        PawControlDailyCaloriesSensor(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleAdherenceSensor(coordinator, dog_id, dog_name),
    ]
    
    # Add individual meal type sensors
    for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
        sensors.append(
            PawControlFeedingCountTodaySensor(
                coordinator, dog_id, dog_name, meal_type
            )
        )
    
    return sensors


def _create_walk_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlSensorBase]:
    """Create walk-related sensors for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of walk sensor entities
    """
    return [
        PawControlLastWalkSensor(coordinator, dog_id, dog_name),
        PawControlLastWalkHoursSensor(coordinator, dog_id, dog_name),
        PawControlLastWalkDurationSensor(coordinator, dog_id, dog_name),
        PawControlWalkCountTodaySensor(coordinator, dog_id, dog_name),
        PawControlTotalWalkTimeTodaySensor(coordinator, dog_id, dog_name),
        PawControlWeeklyWalkCountSensor(coordinator, dog_id, dog_name),
        PawControlAverageWalkDurationSensor(coordinator, dog_id, dog_name),
    ]


def _create_gps_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlSensorBase]:
    """Create GPS and location-related sensors for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of GPS sensor entities
    """
    return [
        PawControlCurrentSpeedSensor(coordinator, dog_id, dog_name),
        PawControlDistanceFromHomeSensor(coordinator, dog_id, dog_name),
        PawControlGPSAccuracySensor(coordinator, dog_id, dog_name),
        PawControlLastWalkDistanceSensor(coordinator, dog_id, dog_name),
        PawControlTotalDistanceTodaySensor(coordinator, dog_id, dog_name),
        PawControlWeeklyDistanceSensor(coordinator, dog_id, dog_name),
        PawControlCurrentZoneSensor(coordinator, dog_id, dog_name),
        PawControlGPSBatteryLevelSensor(coordinator, dog_id, dog_name),
    ]


def _create_health_sensors(
    coordinator: PawControlCoordinator,
    dog_id: str, 
    dog_name: str
) -> List[PawControlSensorBase]:
    """Create health and medical-related sensors for a dog.
    
    Args:
        coordinator: Data coordinator instance
        dog_id: Unique identifier for the dog
        dog_name: Display name for the dog
        
    Returns:
        List of health sensor entities
    """
    return [
        PawControlWeightSensor(coordinator, dog_id, dog_name),
        PawControlWeightTrendSensor(coordinator, dog_id, dog_name),
        PawControlActivityLevelSensor(coordinator, dog_id, dog_name),
        PawControlLastVetVisitSensor(coordinator, dog_id, dog_name),
        PawControlDaysSinceGroomingSensor(coordinator, dog_id, dog_name),
        PawControlHealthStatusSensor(coordinator, dog_id, dog_name),
        PawControlMedicationDueSensor(coordinator, dog_id, dog_name),
    ]


class PawControlSensorBase(CoordinatorEntity[PawControlCoordinator], SensorEntity):
    """Base class for all Paw Control sensor entities.
    
    Provides common functionality and ensures consistent behavior across
    all sensor types. Includes proper device grouping, state management,
    and error handling.
    """

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
        *,
        device_class: Optional[SensorDeviceClass] = None,
        state_class: Optional[SensorStateClass] = None,
        unit_of_measurement: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
    ) -> None:
        """Initialize the sensor entity.
        
        Args:
            coordinator: Data coordinator for updates
            dog_id: Unique identifier for the dog
            dog_name: Display name for the dog
            sensor_type: Type identifier for the sensor
            device_class: Home Assistant device class
            state_class: Home Assistant state class
            unit_of_measurement: Unit of measurement for values
            icon: Material Design icon
            entity_category: Entity category for organization
        """
        super().__init__(coordinator)
        
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._sensor_type = sensor_type
        
        # Entity configuration
        self._attr_unique_id = f"pawcontrol_{dog_id}_{sensor_type}"
        self._attr_name = f"{dog_name} {sensor_type.replace('_', ' ').title()}"
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        
        # Device info for proper grouping
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Monitoring",
            "sw_version": "1.0.0",
            "configuration_url": f"/config/integrations/integration/{DOMAIN}",
        }

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes for the sensor.
        
        Provides common attributes that are useful across all sensors
        including dog identification and last update information.
        
        Returns:
            Dictionary of additional state attributes
        """
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "last_update": dt_util.utcnow().isoformat(),
            "sensor_type": self._sensor_type,
        }
        
        # Add dog-specific information
        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update({
                "dog_breed": dog_info.get("dog_breed", ""),
                "dog_age": dog_info.get("dog_age"),
                "dog_size": dog_info.get("dog_size"),
                "dog_weight": dog_info.get("dog_weight"),
            })
        
        return attrs

    def _get_dog_data(self) -> Optional[Dict[str, Any]]:
        """Get data for this sensor's dog from the coordinator.
        
        Returns:
            Dog data dictionary or None if not available
        """
        if not self.coordinator.available:
            return None
        
        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> Optional[Dict[str, Any]]:
        """Get specific module data for this dog.
        
        Args:
            module: Module name to retrieve data for
            
        Returns:
            Module data dictionary or None if not available
        """
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the sensor is available.
        
        A sensor is available when the coordinator is available and
        the dog data can be retrieved.
        
        Returns:
            True if sensor is available, False otherwise
        """
        return (
            self.coordinator.available 
            and self._get_dog_data() is not None
        )


class PawControlLastActionSensor(PawControlSensorBase):
    """Sensor for tracking the last action timestamp across all modules.
    
    This sensor provides a unified view of when the dog was last active
    across feeding, walking, health, and other tracked activities.
    """

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the last action sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:clock-outline"
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the most recent action timestamp across all modules.
        
        Returns:
            Most recent activity timestamp or None if no activities recorded
        """
        dog_data = self._get_dog_data()
        if not dog_data:
            return None
        
        # Collect all timestamps from different modules
        timestamps: List[datetime] = []
        
        # Check feeding data
        feeding_data = dog_data.get("feeding", {})
        if feeding_data.get("last_feeding"):
            try:
                timestamps.append(datetime.fromisoformat(feeding_data["last_feeding"]))
            except (ValueError, TypeError):
                pass
        
        # Check walk data
        walk_data = dog_data.get("walk", {})
        if walk_data.get("last_walk"):
            try:
                timestamps.append(datetime.fromisoformat(walk_data["last_walk"]))
            except (ValueError, TypeError):
                pass
        
        # Check health data
        health_data = dog_data.get("health", {})
        if health_data.get("last_health_entry"):
            try:
                timestamps.append(datetime.fromisoformat(health_data["last_health_entry"]))
            except (ValueError, TypeError):
                pass
        
        return max(timestamps) if timestamps else None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional attributes for the last action sensor."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()
        
        if dog_data:
            # Add details about what the last action was
            feeding_data = dog_data.get("feeding", {})
            walk_data = dog_data.get("walk", {})
            health_data = dog_data.get("health", {})
            
            attrs.update({
                "last_feeding": feeding_data.get("last_feeding"),
                "last_walk": walk_data.get("last_walk"),
                "last_health_entry": health_data.get("last_health_entry"),
                "activity_summary": self._generate_activity_summary(dog_data),
            })
        
        return attrs

    def _generate_activity_summary(self, dog_data: Dict[str, Any]) -> str:
        """Generate a human-readable activity summary.
        
        Args:
            dog_data: Complete dog data from coordinator
            
        Returns:
            Formatted activity summary string
        """
        activities = []
        
        feeding_data = dog_data.get("feeding", {})
        if feeding_data.get("total_feedings_today", 0) > 0:
            activities.append(f"{feeding_data['total_feedings_today']} feedings")
        
        walk_data = dog_data.get("walk", {})
        if walk_data.get("walks_today", 0) > 0:
            activities.append(f"{walk_data['walks_today']} walks")
        
        if not activities:
            return "No activities today"
        
        return f"Today: {', '.join(activities)}"


class PawControlDogStatusSensor(PawControlSensorBase):
    """Sensor for overall dog status and activity level.
    
    Provides a comprehensive status indicator that considers all aspects
    of the dog's current state including location, activity, and needs.
    """

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the dog status sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "status",
            icon="mdi:dog"
        )

    @property
    def native_value(self) -> str:
        """Return the current status of the dog.
        
        Returns:
            Status string indicating the dog's current state
        """
        dog_data = self._get_dog_data()
        if not dog_data:
            return "unknown"
        
        # Determine status based on various factors
        walk_data = dog_data.get("walk", {})
        feeding_data = dog_data.get("feeding", {})
        gps_data = dog_data.get("gps", {})
        
        # Check if walking
        if walk_data.get("walk_in_progress", False):
            return "walking"
        
        # Check if at home
        if gps_data.get("zone") == "home":
            # Check if needs attention
            if feeding_data.get("is_hungry", False):
                return "hungry"
            elif walk_data.get("needs_walk", False):
                return "needs_walk"
            else:
                return "home"
        elif gps_data.get("zone") and gps_data["zone"] != "unknown":
            return f"at_{gps_data['zone']}"
        else:
            return "away"

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return detailed status attributes."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()
        
        if dog_data:
            walk_data = dog_data.get("walk", {})
            feeding_data = dog_data.get("feeding", {})
            gps_data = dog_data.get("gps", {})
            health_data = dog_data.get("health", {})
            
            attrs.update({
                "walk_in_progress": walk_data.get("walk_in_progress", False),
                "is_home": gps_data.get("zone") == "home",
                "current_zone": gps_data.get("zone", "unknown"),
                "needs_walk": walk_data.get("needs_walk", False),
                "is_hungry": feeding_data.get("is_hungry", False),
                "health_status": health_data.get("health_status", "unknown"),
                "activity_level": health_data.get("activity_level", "normal"),
                "last_seen": gps_data.get("last_seen"),
                "distance_from_home": gps_data.get("distance_from_home"),
            })
        
        return attrs


class PawControlActivityScoreSensor(PawControlSensorBase):
    """Sensor for calculating an overall activity score for the dog.
    
    Combines data from multiple modules to provide a single score
    representing the dog's daily activity level and wellness.
    """

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the activity score sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "activity_score",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:chart-line"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Calculate and return the activity score.
        
        Returns:
            Activity score as a percentage (0-100) or None if insufficient data
        """
        dog_data = self._get_dog_data()
        if not dog_data:
            return None
        
        score_components = []
        
        # Walk activity score (40% of total)
        walk_score = self._calculate_walk_score(dog_data.get("walk", {}))
        if walk_score is not None:
            score_components.append(("walk", walk_score, 0.4))
        
        # Feeding regularity score (20% of total)
        feeding_score = self._calculate_feeding_score(dog_data.get("feeding", {}))
        if feeding_score is not None:
            score_components.append(("feeding", feeding_score, 0.2))
        
        # GPS activity score (25% of total)
        gps_score = self._calculate_gps_score(dog_data.get("gps", {}))
        if gps_score is not None:
            score_components.append(("gps", gps_score, 0.25))
        
        # Health maintenance score (15% of total)
        health_score = self._calculate_health_score(dog_data.get("health", {}))
        if health_score is not None:
            score_components.append(("health", health_score, 0.15))
        
        if not score_components:
            return None
        
        # Calculate weighted average
        total_weight = sum(weight for _, _, weight in score_components)
        weighted_sum = sum(score * weight for _, score, weight in score_components)
        
        final_score = (weighted_sum / total_weight) if total_weight > 0 else 0
        return round(max(0, min(100, final_score)), 1)

    def _calculate_walk_score(self, walk_data: Dict[str, Any]) -> Optional[float]:
        """Calculate walk activity score component.
        
        Args:
            walk_data: Walk module data
            
        Returns:
            Walk score (0-100) or None if no data
        """
        walks_today = walk_data.get("walks_today", 0)
        total_duration = walk_data.get("total_duration_today", 0)
        
        if walks_today == 0:
            return 0
        
        # Score based on number of walks and duration
        walk_count_score = min(walks_today * 25, 75)  # Max 75 for 3+ walks
        duration_score = min(total_duration / 60 * 10, 25)  # Max 25 for 150+ minutes
        
        return walk_count_score + duration_score

    def _calculate_feeding_score(self, feeding_data: Dict[str, Any]) -> Optional[float]:
        """Calculate feeding regularity score component.
        
        Args:
            feeding_data: Feeding module data
            
        Returns:
            Feeding score (0-100) or None if no data
        """
        schedule_adherence = feeding_data.get("feeding_schedule_adherence", 0)
        daily_target_met = feeding_data.get("daily_target_met", False)
        
        base_score = schedule_adherence
        if daily_target_met:
            base_score += 20
        
        return min(base_score, 100)

    def _calculate_gps_score(self, gps_data: Dict[str, Any]) -> Optional[float]:
        """Calculate GPS activity score component.
        
        Args:
            gps_data: GPS module data
            
        Returns:
            GPS activity score (0-100) or None if no data
        """
        if not gps_data.get("last_seen"):
            return 0
        
        # Score based on GPS data freshness and movement
        last_seen = gps_data.get("last_seen")
        if last_seen:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen)
                hours_since = (dt_util.utcnow() - last_seen_dt).total_seconds() / 3600
                freshness_score = max(0, 100 - hours_since * 10)
            except (ValueError, TypeError):
                freshness_score = 0
        else:
            freshness_score = 0
        
        return freshness_score

    def _calculate_health_score(self, health_data: Dict[str, Any]) -> Optional[float]:
        """Calculate health maintenance score component.
        
        Args:
            health_data: Health module data
            
        Returns:
            Health maintenance score (0-100) or None if no data
        """
        health_status = health_data.get("health_status", "good")
        
        # Score based on health status
        health_scores = {
            "excellent": 100,
            "very_good": 90,
            "good": 80,
            "normal": 70,
            "unwell": 40,
            "sick": 20,
        }
        
        return health_scores.get(health_status, 70)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return detailed activity score breakdown."""
        attrs = super().extra_state_attributes
        dog_data = self._get_dog_data()
        
        if dog_data:
            attrs.update({
                "walk_score": self._calculate_walk_score(dog_data.get("walk", {})),
                "feeding_score": self._calculate_feeding_score(dog_data.get("feeding", {})),
                "gps_score": self._calculate_gps_score(dog_data.get("gps", {})),
                "health_score": self._calculate_health_score(dog_data.get("health", {})),
                "score_explanation": self._generate_score_explanation(dog_data),
            })
        
        return attrs

    def _generate_score_explanation(self, dog_data: Dict[str, Any]) -> str:
        """Generate an explanation of the activity score.
        
        Args:
            dog_data: Complete dog data
            
        Returns:
            Human-readable explanation of the score
        """
        explanations = []
        
        walk_data = dog_data.get("walk", {})
        if walk_data.get("walks_today", 0) == 0:
            explanations.append("No walks today")
        elif walk_data.get("walks_today", 0) >= 3:
            explanations.append("Great walk activity")
        
        feeding_data = dog_data.get("feeding", {})
        if feeding_data.get("daily_target_met", False):
            explanations.append("Feeding goals met")
        
        if not explanations:
            return "Activity tracking in progress"
        
        return "; ".join(explanations)


# Additional sensor classes for feeding module
class PawControlLastFeedingSensor(PawControlSensorBase):
    """Sensor for last feeding timestamp."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the last feeding sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:food-drumstick"
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last feeding timestamp."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None
        
        last_feeding = feeding_data.get("last_feeding")
        if last_feeding:
            try:
                return datetime.fromisoformat(last_feeding)
            except (ValueError, TypeError):
                return None
        
        return None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional feeding attributes."""
        attrs = super().extra_state_attributes
        feeding_data = self._get_module_data("feeding")
        
        if feeding_data:
            attrs.update({
                "last_feeding_type": feeding_data.get("last_feeding_type"),
                "next_feeding_due": feeding_data.get("next_feeding_due"),
                "feedings_today": feeding_data.get("total_feedings_today", 0),
                "is_hungry": feeding_data.get("is_hungry", False),
                "schedule_adherence": feeding_data.get("feeding_schedule_adherence", 100.0),
            })
        
        return attrs


class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor for hours since last feeding."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the hours since feeding sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_feeding_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return hours since last feeding."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None
        
        last_feeding = feeding_data.get("last_feeding")
        if not last_feeding:
            return None
        
        try:
            last_feeding_dt = datetime.fromisoformat(last_feeding)
            now = dt_util.utcnow()
            delta = now - last_feeding_dt
            return round(delta.total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            return None


class PawControlFeedingCountTodaySensor(PawControlSensorBase):
    """Sensor for feeding count today by meal type."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str,
        meal_type: str,
    ) -> None:
        """Initialize the feeding count sensor."""
        self._meal_type = meal_type
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            f"feeding_count_today_{meal_type}",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter"
        )
        self._attr_name = f"{dog_name} {meal_type.title()} Count Today"

    @property
    def native_value(self) -> int:
        """Return the feeding count for this meal type today."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 0
        
        feedings_today = feeding_data.get("feedings_today", {})
        return feedings_today.get(self._meal_type, 0)


class PawControlTotalFeedingsTodaySensor(PawControlSensorBase):
    """Sensor for total feedings today."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the total feedings sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "total_feedings_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter"
        )

    @property
    def native_value(self) -> int:
        """Return total feedings today."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 0
        
        return feeding_data.get("total_feedings_today", 0)


class PawControlDailyCaloriesSensor(PawControlSensorBase):
    """Sensor for daily calorie intake."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the daily calories sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "daily_calories",
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
            icon="mdi:fire"
        )

    @property
    def native_value(self) -> float:
        """Return estimated daily calorie intake."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 0.0
        
        # This would be calculated based on feeding data and food types
        # For now, return a placeholder calculation
        total_feedings = feeding_data.get("total_feedings_today", 0)
        return total_feedings * 200.0  # Simplified calculation


class PawControlFeedingScheduleAdherenceSensor(PawControlSensorBase):
    """Sensor for feeding schedule adherence."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the schedule adherence sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "feeding_schedule_adherence",
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:calendar-check"
        )

    @property
    def native_value(self) -> float:
        """Return feeding schedule adherence percentage."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 100.0
        
        return feeding_data.get("feeding_schedule_adherence", 100.0)


# Additional sensor classes would continue here for walk, GPS, and health modules...
# Due to length constraints, I'm showing the pattern for comprehensive sensor implementation.

# Walk sensor classes
class PawControlLastWalkSensor(PawControlSensorBase):
    """Sensor for last walk timestamp."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the last walk sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_walk",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:walk"
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last walk timestamp."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None
        
        last_walk = walk_data.get("last_walk")
        if last_walk:
            try:
                return datetime.fromisoformat(last_walk)
            except (ValueError, TypeError):
                return None
        
        return None


class PawControlLastWalkHoursSensor(PawControlSensorBase):
    """Sensor for hours since last walk."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the hours since walk sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_walk_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.HOURS,
            icon="mdi:clock-outline"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return hours since last walk."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None
        
        last_walk = walk_data.get("last_walk")
        if not last_walk:
            return None
        
        try:
            last_walk_dt = datetime.fromisoformat(last_walk)
            now = dt_util.utcnow()
            delta = now - last_walk_dt
            return round(delta.total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            return None


class PawControlLastWalkDurationSensor(PawControlSensorBase):
    """Sensor for last walk duration."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the walk duration sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return last walk duration in minutes."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None
        
        return walk_data.get("last_walk_duration")


class PawControlWalkCountTodaySensor(PawControlSensorBase):
    """Sensor for walk count today."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the walk count sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "walk_count_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter"
        )

    @property
    def native_value(self) -> int:
        """Return walk count today."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0
        
        return walk_data.get("walks_today", 0)


class PawControlTotalWalkTimeTodaySensor(PawControlSensorBase):
    """Sensor for total walk time today."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the total walk time sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "total_walk_time_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer-sand"
        )

    @property
    def native_value(self) -> float:
        """Return total walk time today in minutes."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0.0
        
        return walk_data.get("total_duration_today", 0.0)


class PawControlWeeklyWalkCountSensor(PawControlSensorBase):
    """Sensor for weekly walk count."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the weekly walk count sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "weekly_walk_count",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:calendar-week"
        )

    @property
    def native_value(self) -> int:
        """Return weekly walk count."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0
        
        return walk_data.get("weekly_walk_count", 0)


class PawControlAverageWalkDurationSensor(PawControlSensorBase):
    """Sensor for average walk duration."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the average walk duration sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "average_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.MINUTES,
            icon="mdi:timer-outline"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return average walk duration."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None
        
        walks_count = walk_data.get("weekly_walk_count", 0)
        total_duration = walk_data.get("weekly_duration", 0)
        
        if walks_count > 0:
            return round(total_duration / walks_count, 1)
        
        return None


# GPS sensor classes
class PawControlCurrentSpeedSensor(PawControlSensorBase):
    """Sensor for current speed."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the current speed sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "current_speed",
            device_class=SensorDeviceClass.SPEED,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
            icon="mdi:speedometer"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return current speed."""
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return None
        
        return gps_data.get("speed")


class PawControlDistanceFromHomeSensor(PawControlSensorBase):
    """Sensor for distance from home."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the distance from home sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "distance_from_home",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-distance"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return distance from home."""
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return None
        
        return gps_data.get("distance_from_home")


class PawControlGPSAccuracySensor(PawControlSensorBase):
    """Sensor for GPS accuracy."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the GPS accuracy sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "gps_accuracy",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:crosshairs-gps"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return GPS accuracy."""
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return None
        
        return gps_data.get("accuracy")


class PawControlLastWalkDistanceSensor(PawControlSensorBase):
    """Sensor for last walk distance."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the last walk distance sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_walk_distance",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-path"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return last walk distance."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None
        
        return walk_data.get("last_walk_distance")


class PawControlTotalDistanceTodaySensor(PawControlSensorBase):
    """Sensor for total distance today."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the total distance sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "total_distance_today",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            native_unit_of_measurement=UnitOfLength.METERS,
            icon="mdi:map-marker-path"
        )

    @property
    def native_value(self) -> float:
        """Return total distance today."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0.0
        
        return walk_data.get("total_distance_today", 0.0)


class PawControlWeeklyDistanceSensor(PawControlSensorBase):
    """Sensor for weekly distance."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the weekly distance sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "weekly_distance",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfLength.KILOMETERS,
            icon="mdi:map-marker-path"
        )

    @property
    def native_value(self) -> float:
        """Return weekly distance in kilometers."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return 0.0
        
        weekly_distance_m = walk_data.get("weekly_distance", 0.0)
        return round(weekly_distance_m / 1000, 2)  # Convert to kilometers


class PawControlCurrentZoneSensor(PawControlSensorBase):
    """Sensor for current zone."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the current zone sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "current_zone",
            icon="mdi:map-marker-circle"
        )

    @property
    def native_value(self) -> str:
        """Return current zone."""
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return "unknown"
        
        return gps_data.get("zone", "unknown")


class PawControlGPSBatteryLevelSensor(PawControlSensorBase):
    """Sensor for GPS device battery level."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the GPS battery sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "gps_battery_level",
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=PERCENTAGE,
            icon="mdi:battery"
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return GPS device battery level."""
        gps_data = self._get_module_data("gps")
        if not gps_data:
            return None
        
        return gps_data.get("battery_level")


# Health sensor classes
class PawControlWeightSensor(PawControlSensorBase):
    """Sensor for current weight."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the weight sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "weight",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfMass.KILOGRAMS,
            icon="mdi:scale"
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return current weight."""
        health_data = self._get_module_data("health")
        if not health_data:
            return None
        
        return health_data.get("current_weight")

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional weight attributes."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data("health")
        
        if health_data:
            attrs.update({
                "last_weight_date": health_data.get("last_weight_date"),
                "weight_trend": health_data.get("weight_trend", "stable"),
                "weight_change_percent": health_data.get("weight_change_percent", 0.0),
            })
        
        return attrs


class PawControlWeightTrendSensor(PawControlSensorBase):
    """Sensor for weight trend."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the weight trend sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "weight_trend",
            icon="mdi:trending-up"
        )

    @property
    def native_value(self) -> str:
        """Return weight trend."""
        health_data = self._get_module_data("health")
        if not health_data:
            return "stable"
        
        return health_data.get("weight_trend", "stable")


class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for activity level."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the activity level sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "activity_level",
            icon="mdi:run"
        )

    @property
    def native_value(self) -> str:
        """Return activity level."""
        health_data = self._get_module_data("health")
        if not health_data:
            return "normal"
        
        return health_data.get("activity_level", "normal")


class PawControlLastVetVisitSensor(PawControlSensorBase):
    """Sensor for last vet visit."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the last vet visit sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "last_vet_visit",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:medical-bag"
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return last vet visit timestamp."""
        health_data = self._get_module_data("health")
        if not health_data:
            return None
        
        last_visit = health_data.get("last_vet_visit")
        if last_visit:
            try:
                return datetime.fromisoformat(last_visit)
            except (ValueError, TypeError):
                return None
        
        return None


class PawControlDaysSinceGroomingSensor(PawControlSensorBase):
    """Sensor for days since last grooming."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the days since grooming sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "days_since_grooming",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            native_unit_of_measurement=UnitOfTime.DAYS,
            icon="mdi:content-cut"
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return days since last grooming."""
        health_data = self._get_module_data("health")
        if not health_data:
            return None
        
        last_grooming = health_data.get("last_grooming")
        if not last_grooming:
            return None
        
        try:
            last_grooming_dt = datetime.fromisoformat(last_grooming)
            now = dt_util.utcnow()
            delta = now - last_grooming_dt
            return delta.days
        except (ValueError, TypeError):
            return None


class PawControlHealthStatusSensor(PawControlSensorBase):
    """Sensor for health status."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the health status sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "health_status",
            icon="mdi:heart-pulse"
        )

    @property
    def native_value(self) -> str:
        """Return health status."""
        health_data = self._get_module_data("health")
        if not health_data:
            return "good"
        
        return health_data.get("health_status", "good")

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional health attributes."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data("health")
        
        if health_data:
            attrs.update({
                "next_checkup_due": health_data.get("next_checkup_due"),
                "medications_due": health_data.get("medications_due", []),
                "active_medications": health_data.get("active_medications", []),
                "grooming_due": health_data.get("grooming_due", False),
                "health_alerts": health_data.get("health_alerts", []),
            })
        
        return attrs


class PawControlMedicationDueSensor(PawControlSensorBase):
    """Sensor for medications due."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        dog_id: str, 
        dog_name: str
    ) -> None:
        """Initialize the medication due sensor."""
        super().__init__(
            coordinator, 
            dog_id, 
            dog_name, 
            "medications_due",
            icon="mdi:pill"
        )

    @property
    def native_value(self) -> int:
        """Return number of medications due."""
        health_data = self._get_module_data("health")
        if not health_data:
            return 0
        
        medications_due = health_data.get("medications_due", [])
        return len(medications_due)

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return medication details."""
        attrs = super().extra_state_attributes
        health_data = self._get_module_data("health")
        
        if health_data:
            attrs.update({
                "medications_due": health_data.get("medications_due", []),
                "active_medications": health_data.get("active_medications", []),
            })
        
        return attrs
