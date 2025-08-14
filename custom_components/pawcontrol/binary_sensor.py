"""Binary sensor platform for Paw Control integration.

This module provides binary sensor entities for the Paw Control integration,
offering boolean state indicators for various dog care aspects like walk needs,
feeding status, grooming requirements, and system modes.

The binary sensors follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Efficient data access patterns
- Comprehensive device classes
- Translation support
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .compat import DeviceInfo, EntityCategory
from .const import (
    CONF_DOG_ID,
    CONF_DOG_MODULES,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    ICONS,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
)
from .entity import PawControlBinarySensorEntity

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# No parallel updates to avoid coordinator conflicts
PARALLEL_UPDATES = 0

# Constants for state evaluation
WALK_OVERDUE_HOURS = 8
GROOMING_OVERDUE_DAYS = 30
FEEDING_OVERDUE_HOURS = 6


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control binary sensor entities from config entry.
    
    Creates binary sensor entities based on configured dogs and enabled modules.
    Only creates sensors for modules that are enabled for each dog.
    
    Args:
        hass: Home Assistant instance
        entry: Configuration entry
        async_add_entities: Callback to add entities
        
    Raises:
        PlatformNotReady: If coordinator hasn't completed initial data refresh
    """
    try:
        runtime_data = entry.runtime_data
        coordinator: PawControlCoordinator = runtime_data.coordinator

        # Ensure coordinator has completed initial refresh
        if not coordinator.last_update_success:
            _LOGGER.warning("Coordinator not ready, attempting refresh")
            await coordinator.async_refresh()
            if not coordinator.last_update_success:
                raise PlatformNotReady

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[PawControlBinarySensorEntity | CoordinatorEntity] = []

        _LOGGER.debug("Setting up binary sensors for %d dogs", len(dogs))

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME, dog_id)

            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            # Get enabled modules for this dog
            dog_modules = dog.get(CONF_DOG_MODULES, {})
            
            _LOGGER.debug(
                "Creating binary sensors for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys())
            )

            # Walk module binary sensors
            if dog_modules.get(MODULE_WALK, True):
                entities.extend(_create_walk_binary_sensors(coordinator, entry, dog_id))

            # Feeding module binary sensors
            if dog_modules.get(MODULE_FEEDING, True):
                entities.extend(_create_feeding_binary_sensors(coordinator, entry, dog_id))

            # Health module binary sensors
            if dog_modules.get(MODULE_HEALTH, True):
                entities.extend(_create_health_binary_sensors(coordinator, entry, dog_id))

            # Grooming module binary sensors
            if dog_modules.get(MODULE_GROOMING, False):
                entities.extend(_create_grooming_binary_sensors(coordinator, entry, dog_id))

            # GPS module binary sensors
            if dog_modules.get(MODULE_GPS, False):
                entities.extend(_create_location_binary_sensors(coordinator, entry, dog_id))

            # Training module binary sensors
            if dog_modules.get(MODULE_TRAINING, False):
                entities.extend(_create_training_binary_sensors(coordinator, entry, dog_id))

        # System-wide binary sensors (always created)
        entities.extend(_create_system_binary_sensors(coordinator, entry))

        _LOGGER.info("Created %d binary sensor entities", len(entities))
        
        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup binary sensors: %s", err)
        raise


def _create_walk_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create walk-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of walk binary sensor entities
    """
    return [
        NeedsWalkBinarySensor(coordinator, entry, dog_id),
        WalkInProgressBinarySensor(coordinator, entry, dog_id),
        WalkOverdueBinarySensor(coordinator, entry, dog_id),
    ]


def _create_feeding_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create feeding-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of feeding binary sensor entities
    """
    return [
        IsHungryBinarySensor(coordinator, entry, dog_id),
        FeedingOverdueBinarySensor(coordinator, entry, dog_id),
        HasEatenTodayBinarySensor(coordinator, entry, dog_id),
    ]


def _create_health_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create health-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of health binary sensor entities
    """
    return [
        NeedsMedicationBinarySensor(coordinator, entry, dog_id),
        HealthConcernBinarySensor(coordinator, entry, dog_id),
    ]


def _create_grooming_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create grooming-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of grooming binary sensor entities
    """
    return [
        NeedsGroomingBinarySensor(coordinator, entry, dog_id),
        GroomingOverdueBinarySensor(coordinator, entry, dog_id),
    ]


def _create_location_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create location and GPS-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of location binary sensor entities
    """
    return [
        IsHomeBinarySensor(coordinator, entry, dog_id),
        GPSActiveBinarySensor(coordinator, entry, dog_id),
        GeofenceAlertsActiveBinarySensor(coordinator, entry, dog_id),
    ]


def _create_training_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry, 
    dog_id: str
) -> list[PawControlBinarySensorEntity]:
    """Create training-related binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier
        
    Returns:
        List of training binary sensor entities
    """
    return [
        TrainingDueBinarySensor(coordinator, entry, dog_id),
        TrainingInProgressBinarySensor(coordinator, entry, dog_id),
    ]


def _create_system_binary_sensors(
    coordinator: PawControlCoordinator, 
    entry: ConfigEntry
) -> list[CoordinatorEntity]:
    """Create system-wide binary sensors.
    
    Args:
        coordinator: Data coordinator
        entry: Config entry
        
    Returns:
        List of system binary sensor entities
    """
    return [
        VisitorModeBinarySensor(coordinator, entry),
        EmergencyModeBinarySensor(coordinator, entry),
        SystemHealthyBinarySensor(coordinator, entry),
    ]

# ==============================================================================
# WALK BINARY SENSORS
# ==============================================================================

class NeedsWalkBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog needs a walk.
    
    Evaluates walk needs based on time since last walk and configured thresholds.
    """

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the needs walk binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="needs_walk",
            translation_key="needs_walk",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon=ICONS.get("walk", "mdi:dog-side"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog needs a walk."""
        try:
            walk_data = self.dog_data.get("walk", {})
            return walk_data.get("needs_walk", False)
        except Exception as err:
            _LOGGER.debug("Error checking walk needs for %s: %s", self.dog_id, err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional walk information."""
        try:
            attributes = super().extra_state_attributes or {}
            walk_data = self.dog_data.get("walk", {})
            
            attributes.update({
                "last_walk": walk_data.get("last_walk"),
                "walks_today": walk_data.get("walks_today", 0),
                "walk_in_progress": walk_data.get("walk_in_progress", False),
                "total_distance_today": walk_data.get("total_distance_today", 0),
            })
            
            # Calculate hours since last walk
            if last_walk := walk_data.get("last_walk"):
                try:
                    last_walk_time = dt_util.parse_datetime(last_walk)
                    if last_walk_time:
                        hours_since = (dt_util.utcnow() - last_walk_time).total_seconds() / 3600
                        attributes["hours_since_last_walk"] = round(hours_since, 1)
                except (ValueError, TypeError):
                    pass
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting walk attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class WalkInProgressBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether a walk is currently in progress."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the walk in progress binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_in_progress",
            translation_key="walk_in_progress",
            device_class=BinarySensorDeviceClass.RUNNING,
            icon=ICONS.get("walk", "mdi:walk"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if walk is in progress."""
        try:
            walk_data = self.dog_data.get("walk", {})
            return walk_data.get("walk_in_progress", False)
        except Exception as err:
            _LOGGER.debug("Error checking walk progress for %s: %s", self.dog_id, err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return current walk details."""
        try:
            attributes = super().extra_state_attributes or {}
            walk_data = self.dog_data.get("walk", {})
            
            if walk_data.get("walk_in_progress", False):
                attributes.update({
                    "start_time": walk_data.get("walk_start_time"),
                    "current_distance_m": walk_data.get("walk_distance_m", 0),
                })
                
                # Calculate current duration
                if start_time_str := walk_data.get("walk_start_time"):
                    try:
                        start_time = dt_util.parse_datetime(start_time_str)
                        if start_time:
                            duration_minutes = (dt_util.utcnow() - start_time).total_seconds() / 60
                            attributes["current_duration_min"] = round(duration_minutes, 1)
                    except (ValueError, TypeError):
                        pass
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting walk progress attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class WalkOverdueBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether walk is significantly overdue."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the walk overdue binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_overdue",
            translation_key="walk_overdue",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("walk", "mdi:alert-circle"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if walk is significantly overdue."""
        try:
            walk_data = self.dog_data.get("walk", {})
            
            # Not overdue if walk is in progress
            if walk_data.get("walk_in_progress", False):
                return False
            
            last_walk = walk_data.get("last_walk")
            if not last_walk:
                return True  # No walk recorded = overdue
            
            try:
                last_walk_time = dt_util.parse_datetime(last_walk)
                if last_walk_time:
                    hours_since = (dt_util.utcnow() - last_walk_time).total_seconds() / 3600
                    return hours_since >= WALK_OVERDUE_HOURS
            except (ValueError, TypeError):
                pass
                
            return False
        except Exception as err:
            _LOGGER.debug("Error checking walk overdue for %s: %s", self.dog_id, err)
            return False

# ==============================================================================
# FEEDING BINARY SENSORS
# ==============================================================================

class IsHungryBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog is hungry based on feeding schedule."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the is hungry binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="is_hungry",
            translation_key="is_hungry",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon=ICONS.get("feeding", "mdi:food-drumstick-off"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog is hungry."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            return feeding_data.get("is_hungry", False)
        except Exception as err:
            _LOGGER.debug("Error checking hunger for %s: %s", self.dog_id, err)
            return False

    @property
    def icon(self) -> str:
        """Return icon based on hunger state."""
        return (
            "mdi:food-drumstick-off" if self.is_on 
            else ICONS.get("feeding", "mdi:food-drumstick")
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return feeding information."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})
            
            attributes.update({
                "last_feeding": feeding_data.get("last_feeding"),
                "last_meal_type": feeding_data.get("last_meal_type"),
                "total_feedings_today": sum(feeding_data.get("feedings_today", {}).values()),
                "total_portions_today": feeding_data.get("total_portions_today", 0),
            })
            
            # Add detailed feeding breakdown
            feedings_today = feeding_data.get("feedings_today", {})
            attributes.update({
                "breakfast_count": feedings_today.get("breakfast", 0),
                "lunch_count": feedings_today.get("lunch", 0),
                "dinner_count": feedings_today.get("dinner", 0),
                "snack_count": feedings_today.get("snack", 0),
            })
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting hunger attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class FeedingOverdueBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether feeding is significantly overdue."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the feeding overdue binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feeding_overdue",
            translation_key="feeding_overdue",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:alert-circle"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if feeding is significantly overdue."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            last_feeding = feeding_data.get("last_feeding")
            
            if not last_feeding:
                return True  # No feeding recorded = overdue
            
            try:
                last_feeding_time = dt_util.parse_datetime(last_feeding)
                if last_feeding_time:
                    hours_since = (dt_util.utcnow() - last_feeding_time).total_seconds() / 3600
                    return hours_since >= FEEDING_OVERDUE_HOURS
            except (ValueError, TypeError):
                pass
                
            return False
        except Exception as err:
            _LOGGER.debug("Error checking feeding overdue for %s: %s", self.dog_id, err)
            return False


class HasEatenTodayBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog has eaten today."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the has eaten today binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="has_eaten_today",
            translation_key="has_eaten_today",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:check-circle"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog has eaten today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings_today = feeding_data.get("feedings_today", {})
            return sum(feedings_today.values()) > 0
        except Exception as err:
            _LOGGER.debug("Error checking daily feeding for %s: %s", self.dog_id, err)
            return False

# ==============================================================================
# HEALTH BINARY SENSORS
# ==============================================================================

class NeedsMedicationBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog needs medication."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the needs medication binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="needs_medication",
            translation_key="needs_medication",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon=ICONS.get("medication", "mdi:pill"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog needs medication."""
        try:
            health_data = self.dog_data.get("health", {})
            next_medication_due = health_data.get("next_medication_due")
            
            if next_medication_due:
                try:
                    due_time = dt_util.parse_datetime(next_medication_due)
                    if due_time:
                        return dt_util.utcnow() >= due_time
                except (ValueError, TypeError):
                    pass
                    
            return False
        except Exception as err:
            _LOGGER.debug("Error checking medication needs for %s: %s", self.dog_id, err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return medication information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})
            
            attributes.update({
                "last_medication": health_data.get("last_medication"),
                "medication_name": health_data.get("medication_name"),
                "medication_dose": health_data.get("medication_dose"),
                "medications_today": health_data.get("medications_today", 0),
                "next_medication_due": health_data.get("next_medication_due"),
            })
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting medication attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class HealthConcernBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether there are health concerns."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the health concern binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="health_concern",
            translation_key="health_concern",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("health", "mdi:medical-bag"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if there are health concerns."""
        try:
            health_data = self.dog_data.get("health", {})
            
            # Check for overdue vaccinations, medications, or vet visits
            # This would be implemented based on vaccination schedules
            # For now, return False as placeholder
            return False
        except Exception as err:
            _LOGGER.debug("Error checking health concerns for %s: %s", self.dog_id, err)
            return False

# ==============================================================================
# GROOMING BINARY SENSORS
# ==============================================================================

class NeedsGroomingBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog needs grooming."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the needs grooming binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="needs_grooming",
            translation_key="needs_grooming",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon=ICONS.get("grooming", "mdi:content-cut"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog needs grooming."""
        try:
            grooming_data = self.dog_data.get("grooming", {})
            return grooming_data.get("needs_grooming", False)
        except Exception as err:
            _LOGGER.debug("Error checking grooming needs for %s: %s", self.dog_id, err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return grooming information."""
        try:
            attributes = super().extra_state_attributes or {}
            grooming_data = self.dog_data.get("grooming", {})
            
            attributes.update({
                "last_grooming": grooming_data.get("last_grooming"),
                "grooming_type": grooming_data.get("grooming_type"),
                "interval_days": grooming_data.get("grooming_interval_days", 30),
            })
            
            # Calculate days since last grooming
            if last_grooming := grooming_data.get("last_grooming"):
                try:
                    last_grooming_time = dt_util.parse_datetime(last_grooming)
                    if last_grooming_time:
                        days_since = (dt_util.utcnow() - last_grooming_time).days
                        attributes["days_since_last_grooming"] = max(0, days_since)
                except (ValueError, TypeError):
                    pass
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting grooming attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class GroomingOverdueBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether grooming is significantly overdue."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the grooming overdue binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="grooming_overdue",
            translation_key="grooming_overdue",
            device_class=BinarySensorDeviceClass.PROBLEM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("grooming", "mdi:alert-circle"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if grooming is significantly overdue."""
        try:
            grooming_data = self.dog_data.get("grooming", {})
            last_grooming = grooming_data.get("last_grooming")
            interval_days = grooming_data.get("grooming_interval_days", GROOMING_OVERDUE_DAYS)
            
            if not last_grooming:
                return True  # No grooming recorded = overdue
            
            try:
                last_grooming_time = dt_util.parse_datetime(last_grooming)
                if last_grooming_time:
                    days_since = (dt_util.utcnow() - last_grooming_time).days
                    return days_since >= (interval_days * 1.5)  # 50% past due
            except (ValueError, TypeError):
                pass
                
            return False
        except Exception as err:
            _LOGGER.debug("Error checking grooming overdue for %s: %s", self.dog_id, err)
            return False

# ==============================================================================
# LOCATION BINARY SENSORS
# ==============================================================================

class IsHomeBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether dog is at home location."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the is home binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="is_home",
            translation_key="is_home",
            device_class=BinarySensorDeviceClass.PRESENCE,
            icon=ICONS.get("location", "mdi:home"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if dog is at home."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("is_home", True)
        except Exception as err:
            _LOGGER.debug("Error checking home presence for %s: %s", self.dog_id, err)
            return True  # Default to home if unknown

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return location information."""
        try:
            attributes = super().extra_state_attributes or {}
            location_data = self.dog_data.get("location", {})
            
            attributes.update({
                "current_location": location_data.get("current_location", "home"),
                "distance_from_home": location_data.get("distance_from_home", 0),
                "last_gps_update": location_data.get("last_gps_update"),
                "enters_today": location_data.get("enters_today", 0),
                "leaves_today": location_data.get("leaves_today", 0),
                "time_inside_today_min": location_data.get("time_inside_today_min", 0.0),
            })
            
            return attributes
        except Exception as err:
            _LOGGER.debug("Error getting location attributes for %s: %s", self.dog_id, err)
            return super().extra_state_attributes


class GPSActiveBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether GPS tracking is active."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the GPS active binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="gps_active",
            translation_key="gps_active",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("gps", "mdi:crosshairs-gps"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if GPS is actively tracking."""
        try:
            location_data = self.dog_data.get("location", {})
            last_gps_update = location_data.get("last_gps_update")
            
            if last_gps_update:
                try:
                    last_update_time = dt_util.parse_datetime(last_gps_update)
                    if last_update_time:
                        # Consider GPS active if updated within last 15 minutes
                        minutes_since = (dt_util.utcnow() - last_update_time).total_seconds() / 60
                        return minutes_since <= 15
                except (ValueError, TypeError):
                    pass
                    
            return False
        except Exception as err:
            _LOGGER.debug("Error checking GPS status for %s: %s", self.dog_id, err)
            return False


class GeofenceAlertsActiveBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether geofence alerts are active."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the geofence alerts active binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="geofence_alerts_active",
            translation_key="geofence_alerts_active",
            device_class=BinarySensorDeviceClass.RUNNING,
            entity_category=EntityCategory.CONFIG,
            icon=ICONS.get("notifications", "mdi:shield-alert"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if geofence alerts are enabled."""
        try:
            # This would check geofence configuration
            # For now, return True as default
            return True
        except Exception as err:
            _LOGGER.debug("Error checking geofence alerts for %s: %s", self.dog_id, err)
            return True

# ==============================================================================
# TRAINING BINARY SENSORS
# ==============================================================================

class TrainingDueBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether training is due."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the training due binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="training_due",
            translation_key="training_due",
            device_class=BinarySensorDeviceClass.PROBLEM,
            icon=ICONS.get("training", "mdi:school"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if training is due."""
        try:
            training_data = self.dog_data.get("training", {})
            sessions_today = training_data.get("training_sessions_today", 0)
            
            # Consider training due if no sessions today and it's after 10 AM
            current_hour = dt_util.utcnow().hour
            return sessions_today == 0 and current_hour >= 10
        except Exception as err:
            _LOGGER.debug("Error checking training due for %s: %s", self.dog_id, err)
            return False


class TrainingInProgressBinarySensor(PawControlBinarySensorEntity, BinarySensorEntity):
    """Binary sensor indicating whether training is in progress."""

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry, 
        dog_id: str
    ) -> None:
        """Initialize the training in progress binary sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="training_in_progress",
            translation_key="training_in_progress",
            device_class=BinarySensorDeviceClass.RUNNING,
            icon=ICONS.get("training", "mdi:school"),
        )

    @property
    def is_on(self) -> bool:
        """Return True if training is in progress."""
        try:
            # This would track active training sessions
            # For now, return False as placeholder
            return False
        except Exception as err:
            _LOGGER.debug("Error checking training progress for %s: %s", self.dog_id, err)
            return False

# ==============================================================================
# SYSTEM BINARY SENSORS
# ==============================================================================

class VisitorModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for visitor mode status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry
    ) -> None:
        """Initialize the visitor mode binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_visitor_mode"
        self._attr_translation_key = "visitor_mode"
        self._attr_icon = ICONS.get("visitor", "mdi:account-group")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return "Visitor Mode"

    @property
    def is_on(self) -> bool:
        """Return True if visitor mode is active."""
        try:
            return self.coordinator.visitor_mode
        except Exception as err:
            _LOGGER.debug("Error getting visitor mode status: %s", err)
            return False


class EmergencyModeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for emergency mode status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry
    ) -> None:
        """Initialize the emergency mode binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_emergency_mode"
        self._attr_translation_key = "emergency_mode"
        self._attr_icon = ICONS.get("emergency", "mdi:alert-circle")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return "Emergency Mode"

    @property
    def is_on(self) -> bool:
        """Return True if emergency mode is active."""
        try:
            return self.coordinator.emergency_mode
        except Exception as err:
            _LOGGER.debug("Error getting emergency mode status: %s", err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return emergency mode details."""
        try:
            if self.coordinator.emergency_mode:
                return {
                    "level": self.coordinator.emergency_level,
                }
            return {}
        except Exception as err:
            _LOGGER.debug("Error getting emergency mode attributes: %s", err)
            return {}


class SystemHealthyBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for overall system health status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, 
        coordinator: PawControlCoordinator, 
        entry: ConfigEntry
    ) -> None:
        """Initialize the system healthy binary sensor."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_global_system_healthy"
        self._attr_translation_key = "system_healthy"
        self._attr_icon = ICONS.get("health", "mdi:heart-pulse")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "global")},
            name="Paw Control System",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
            configuration_url=f"/config/integrations/integration/{DOMAIN}",
        )

    @property
    def name(self) -> str:
        """Return name of the sensor."""
        return "System Healthy"

    @property
    def is_on(self) -> bool:
        """Return True if system is healthy (inverted - on means no problems)."""
        try:
            # System is healthy if coordinator is working and no emergency mode
            return (
                self.coordinator.last_update_success and
                not self.coordinator.emergency_mode
            )
        except Exception as err:
            _LOGGER.debug("Error checking system health: %s", err)
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return system health details."""
        try:
            return {
                "coordinator_available": self.coordinator.last_update_success,
                "last_update": self.coordinator.last_update_success_time.isoformat() 
                               if self.coordinator.last_update_success_time else None,
                "emergency_mode": self.coordinator.emergency_mode,
                "visitor_mode": self.coordinator.visitor_mode,
            }
        except Exception as err:
            _LOGGER.debug("Error getting system health attributes: %s", err)
            return {}
