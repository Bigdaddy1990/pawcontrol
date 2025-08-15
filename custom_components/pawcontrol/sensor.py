"""Sensors for Paw Control integration.

This module provides comprehensive sensor entities for the Paw Control integration,
covering all aspects of dog monitoring including walks, feeding, health, activity,
location tracking, and statistics.

The sensors follow Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling
- Efficient data access patterns
- Comprehensive device classes and state classes
- Translation support
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .compat import EntityCategory, UnitOfLength, UnitOfMass, UnitOfTime
from .const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    ENTITY_UPDATE_DEBOUNCE_SECONDS,
    ICONS,
    MAX_CONCURRENT_UPDATES,
    MIN_MEANINGFUL_DISTANCE_M,
    MIN_MEANINGFUL_DURATION_S,
    MIN_MEANINGFUL_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_TRAINING,
    MODULE_WALK,
    STATUS_READY,
)
from .const import (
    DOMAIN as _DOMAIN,
)
from .entity import PawControlSensorEntity

DOMAIN = _DOMAIN

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Limit parallel updates to prevent coordinator overload (Platinum optimization)
PARALLEL_UPDATES = MAX_CONCURRENT_UPDATES

# Sensor configuration constants (Platinum optimization)
SENSOR_UPDATE_THRESHOLD = 0.1  # Minimum change to trigger state update
MIN_UPDATE_INTERVAL = ENTITY_UPDATE_DEBOUNCE_SECONDS


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Paw Control sensors from config entry.

    Creates sensor entities based on configured dogs and enabled modules.
    Only creates sensors for modules that are enabled for each dog.

    Platinum optimizations:
    - Validates coordinator health before setup
    - Efficient entity creation with early validation
    - Comprehensive error handling with recovery
    - Memory-efficient entity grouping

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

    # Platinum: Enhanced coordinator validation
    if not coordinator.last_update_success:
       _LOGGER.warning("Coordinator not ready, attempting refresh")
    if hasattr(coordinator, "async_refresh"):
        await coordinator.async_refresh()
        if not coordinator.last_update_success:
            _LOGGER.warning("Coordinator not ready, attempting refresh")
            if hasattr(coordinator, "async_refresh"):
                await coordinator.async_refresh()
                if not coordinator.last_update_success:
                    _LOGGER.error("Coordinator failed initial refresh")
                    raise PlatformNotReady("Coordinator failed to initialize")
            else:
                raise PlatformNotReady("Coordinator missing refresh method")

        # Platinum: Validate coordinator health status
        if hasattr(coordinator, "coordinator_status"):
            if coordinator.coordinator_status != STATUS_READY:
                _LOGGER.warning(
                    "Coordinator status is %s, may affect sensor reliability",
                    coordinator.coordinator_status,
                )

        dogs = entry.options.get(CONF_DOGS, [])
        entities: list[PawControlSensorEntity] = []
        entity_count_by_type: dict[str, int] = {}

        _LOGGER.debug("Setting up sensors for %d dogs", len(dogs))

        for dog in dogs:
            dog_id = dog.get(CONF_DOG_ID)
            dog_name = dog.get(CONF_DOG_NAME, dog_id)

            if not dog_id:
                _LOGGER.warning("Skipping dog with missing ID: %s", dog)
                continue

            # Get enabled modules for this dog
            dog_modules = dog.get("dog_modules", {})

            _LOGGER.debug(
                "Creating sensors for dog %s (%s) with modules: %s",
                dog_name,
                dog_id,
                list(dog_modules.keys()),
            )

            # Platinum: Track entity creation for monitoring
            dog_entity_count = 0

            # Core sensors (always enabled)
            core_entities = _create_core_sensors(coordinator, entry, dog_id)
            entities.extend(core_entities)
            dog_entity_count += len(core_entities)
            entity_count_by_type["core"] = entity_count_by_type.get("core", 0) + len(
                core_entities
            )

            # Walk sensors (if walk module enabled)
            if dog_modules.get(MODULE_WALK, True):
                walk_entities = _create_walk_sensors(coordinator, entry, dog_id)
                entities.extend(walk_entities)
                dog_entity_count += len(walk_entities)
                entity_count_by_type["walk"] = entity_count_by_type.get(
                    "walk", 0
                ) + len(walk_entities)

            # Feeding sensors (if feeding module enabled)
            if dog_modules.get(MODULE_FEEDING, True):
                feeding_entities = _create_feeding_sensors(coordinator, entry, dog_id)
                entities.extend(feeding_entities)
                dog_entity_count += len(feeding_entities)
                entity_count_by_type["feeding"] = entity_count_by_type.get(
                    "feeding", 0
                ) + len(feeding_entities)

            # Health sensors (if health module enabled)
            if dog_modules.get(MODULE_HEALTH, True):
                health_entities = _create_health_sensors(coordinator, entry, dog_id)
                entities.extend(health_entities)
                dog_entity_count += len(health_entities)
                entity_count_by_type["health"] = entity_count_by_type.get(
                    "health", 0
                ) + len(health_entities)

            # Activity sensors (always enabled with walk or feeding)
            if dog_modules.get(MODULE_WALK, True) or dog_modules.get(
                MODULE_FEEDING, True
            ):
                activity_entities = _create_activity_sensors(coordinator, entry, dog_id)
                entities.extend(activity_entities)
                dog_entity_count += len(activity_entities)
                entity_count_by_type["activity"] = entity_count_by_type.get(
                    "activity", 0
                ) + len(activity_entities)

            # Location sensors (if GPS module enabled)
            if dog_modules.get(MODULE_GPS, False):
                location_entities = _create_location_sensors(coordinator, entry, dog_id)
                entities.extend(location_entities)
                dog_entity_count += len(location_entities)
                entity_count_by_type["location"] = entity_count_by_type.get(
                    "location", 0
                ) + len(location_entities)

            # Statistics sensors (always enabled)
            stats_entities = _create_statistics_sensors(coordinator, entry, dog_id)
            entities.extend(stats_entities)
            dog_entity_count += len(stats_entities)
            entity_count_by_type["statistics"] = entity_count_by_type.get(
                "statistics", 0
            ) + len(stats_entities)

            # Grooming sensors (if grooming module enabled)
            if dog_modules.get(MODULE_GROOMING, False):
                grooming_entities = _create_grooming_sensors(coordinator, entry, dog_id)
                entities.extend(grooming_entities)
                dog_entity_count += len(grooming_entities)
                entity_count_by_type["grooming"] = entity_count_by_type.get(
                    "grooming", 0
                ) + len(grooming_entities)

            # Training sensors (if training module enabled)
            if dog_modules.get(MODULE_TRAINING, False):
                training_entities = _create_training_sensors(coordinator, entry, dog_id)
                entities.extend(training_entities)
                dog_entity_count += len(training_entities)
                entity_count_by_type["training"] = entity_count_by_type.get(
                    "training", 0
                ) + len(training_entities)

            _LOGGER.debug("Created %d sensors for dog %s", dog_entity_count, dog_name)

        # Platinum: Comprehensive logging with entity breakdown
        _LOGGER.info(
            "Created %d sensor entities across %d dogs - breakdown: %s",
            len(entities),
            len(dogs),
            entity_count_by_type,
        )

        if entities:
            async_add_entities(entities, update_before_add=True)

    except Exception as err:
        _LOGGER.error("Failed to setup sensors: %s", err)
        raise


def _create_core_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create core sensors that are always available.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of core sensor entities
    """
    return [
        LastActionSensor(coordinator, entry, dog_id),
        DogStatusSensor(coordinator, entry, dog_id),
    ]


def _create_walk_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create walk-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of walk sensor entities
    """
    return [
        WalkDistanceCurrentSensor(coordinator, entry, dog_id),
        WalkDistanceLastSensor(coordinator, entry, dog_id),
        WalkDurationCurrentSensor(coordinator, entry, dog_id),
        WalkDurationLastSensor(coordinator, entry, dog_id),
        WalkDistanceTodaySensor(coordinator, entry, dog_id),
        WalksCountTodaySensor(coordinator, entry, dog_id),
        LastWalkTimeSensor(coordinator, entry, dog_id),
    ]


def _create_feeding_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create feeding-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of feeding sensor entities
    """
    return [
        LastFeedingTimeSensor(coordinator, entry, dog_id),
        LastMealTypeSensor(coordinator, entry, dog_id),
        FeedingsCountTodaySensor(coordinator, entry, dog_id),
        TotalPortionsTodaySensor(coordinator, entry, dog_id),
        BreakfastCountSensor(coordinator, entry, dog_id),
        LunchCountSensor(coordinator, entry, dog_id),
        DinnerCountSensor(coordinator, entry, dog_id),
        SnackCountSensor(coordinator, entry, dog_id),
    ]


def _create_health_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create health-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of health sensor entities
    """
    return [
        WeightSensor(coordinator, entry, dog_id),
        MedicationsTodaySensor(coordinator, entry, dog_id),
        LastMedicationTimeSensor(coordinator, entry, dog_id),
        LastVetVisitSensor(coordinator, entry, dog_id),
        WeightTrendSensor(coordinator, entry, dog_id),
    ]


def _create_activity_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create activity-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of activity sensor entities
    """
    return [
        ActivityLevelSensor(coordinator, entry, dog_id),
        CaloriesBurnedTodaySensor(coordinator, entry, dog_id),
        PlayTimeTodaySensor(coordinator, entry, dog_id),
        LastPlayTimeSensor(coordinator, entry, dog_id),
    ]


def _create_location_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create location and GPS-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of location sensor entities
    """
    return [
        DistanceFromHomeSensor(coordinator, entry, dog_id),
        CurrentLocationSensor(coordinator, entry, dog_id),
        GeofenceEntersTodaySensor(coordinator, entry, dog_id),
        GeofenceLeavesTodaySensor(coordinator, entry, dog_id),
        TimeInsideTodaySensor(coordinator, entry, dog_id),
        LastGPSUpdateSensor(coordinator, entry, dog_id),
        GPSAccuracySensor(coordinator, entry, dog_id),
    ]


def _create_statistics_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create statistics sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of statistics sensor entities
    """
    return [
        PoopCountTodaySensor(coordinator, entry, dog_id),
        LastPoopTimeSensor(coordinator, entry, dog_id),
    ]


def _create_grooming_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create grooming-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of grooming sensor entities
    """
    return [
        LastGroomingTimeSensor(coordinator, entry, dog_id),
        LastGroomingTypeSensor(coordinator, entry, dog_id),
        DaysSinceGroomingSensor(coordinator, entry, dog_id),
    ]


def _create_training_sensors(
    coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
) -> list[PawControlSensorEntity]:
    """Create training-related sensors.

    Args:
        coordinator: Data coordinator
        entry: Config entry
        dog_id: Dog identifier

    Returns:
        List of training sensor entities
    """
    return [
        LastTrainingTimeSensor(coordinator, entry, dog_id),
        LastTrainingTopicSensor(coordinator, entry, dog_id),
        TrainingSessionsTodaySensor(coordinator, entry, dog_id),
        TrainingDurationTodaySensor(coordinator, entry, dog_id),
    ]


# ==============================================================================
# CORE SENSORS
# ==============================================================================


class LastActionSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for the last action performed for this dog.

    Tracks the timestamp and type of the most recent action (walk, feeding,
    medication, etc.) performed for the dog.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last action sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_action",
            translation_key="last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("statistics", "mdi:history"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the timestamp of the last action."""
        try:
            stats_data = self.dog_data.get("statistics", {})
            return stats_data.get("last_action")
        except Exception as err:
            _LOGGER.debug("Error getting last action for %s: %s", self.dog_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        try:
            stats_data = self.dog_data.get("statistics", {})
            attributes = super().extra_state_attributes or {}

            if action_type := stats_data.get("last_action_type"):
                attributes["action_type"] = action_type

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting last action attributes for %s: %s", self.dog_id, err
            )
            return super().extra_state_attributes


class DogStatusSensor(PawControlSensorEntity, SensorEntity):
    """Sensor providing overall status summary for the dog.

    Aggregates various data points to provide a high-level status
    indication like "active", "resting", "needs_attention", etc.
    """

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the dog status sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="status",
            translation_key="status",
            device_class=SensorDeviceClass.ENUM,
            icon=ICONS.get("dashboard", "mdi:information"),
        )
        self._attr_options = [
            "resting",
            "active",
            "walking",
            "needs_attention",
            "unknown",
        ]

    @property
    def native_value(self) -> str:
        """Return the current status of the dog."""
        try:
            walk_data = self.dog_data.get("walk", {})
            feeding_data = self.dog_data.get("feeding", {})

            # Check if currently walking
            if walk_data.get("walk_in_progress", False):
                return "walking"

            # Check if needs attention (hungry, needs walk, etc.)
            if walk_data.get("needs_walk", False) or feeding_data.get(
                "is_hungry", False
            ):
                return "needs_attention"

            # Check recent activity to determine active vs resting
            last_action = self.dog_data.get("statistics", {}).get("last_action")
            if last_action:
                try:
                    last_action_time = dt_util.parse_datetime(last_action)
                    if last_action_time:
                        time_since_action = dt_util.utcnow() - last_action_time
                        if time_since_action.total_seconds() < 3600:  # 1 hour
                            return "active"
                except (ValueError, TypeError):
                    pass

            return "resting"

        except Exception as err:
            _LOGGER.debug("Error calculating dog status for %s: %s", self.dog_id, err)
            return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional status information."""
        try:
            attributes = super().extra_state_attributes or {}

            walk_data = self.dog_data.get("walk", {})
            feeding_data = self.dog_data.get("feeding", {})

            attributes.update(
                {
                    "needs_walk": walk_data.get("needs_walk", False),
                    "is_hungry": feeding_data.get("is_hungry", False),
                    "walk_in_progress": walk_data.get("walk_in_progress", False),
                    "walks_today": walk_data.get("walks_today", 0),
                    "feedings_today": sum(
                        feeding_data.get("feedings_today", {}).values()
                    ),
                }
            )

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting status attributes for %s: %s", self.dog_id, err
            )
            return super().extra_state_attributes


# ==============================================================================
# WALK SENSORS
# ==============================================================================


class WalkDistanceCurrentSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current walk distance in progress.

    Platinum optimizations:
    - Validates meaningful distance changes
    - Efficient state updates with thresholds
    - Enhanced error handling
    """

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the current walk distance sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_distance_current",
            translation_key="walk_distance_current",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon=ICONS.get("walk", "mdi:map-marker-distance"),
            precision=1,
        )
        self._last_reported_value: float | None = None

    @property
    def native_value(self) -> float | None:
        """Return the current walk distance if walk is in progress."""
        try:
            walk_data = self.dog_data.get("walk", {})
            if walk_data.get("walk_in_progress", False):
                distance = walk_data.get("walk_distance_m", 0)

                # Platinum: Filter meaningless updates
                if distance >= MIN_MEANINGFUL_DISTANCE_M:
                    # Only update if change is significant enough
                    if (
                        self._last_reported_value is None
                        or abs(distance - self._last_reported_value)
                        >= SENSOR_UPDATE_THRESHOLD
                    ):
                        self._last_reported_value = distance
                        return distance
                    return self._last_reported_value
                return 0.0
            return None
        except Exception as err:
            _LOGGER.debug(
                "Error getting current walk distance for %s: %s", self.dog_id, err
            )
            return None

    @property
    def available(self) -> bool:
        """Only available when walk is in progress."""
        if not super().available:
            return False
        walk_data = self.dog_data.get("walk", {})
        return walk_data.get("walk_in_progress", False)


class WalkDistanceLastSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for last completed walk distance."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last walk distance sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_distance_last",
            translation_key="walk_distance_last",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon=ICONS.get("walk", "mdi:map-marker-check"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return the last walk distance."""
        try:
            walk_data = self.dog_data.get("walk", {})
            if not walk_data.get("walk_in_progress", False) and walk_data.get(
                "last_walk"
            ):
                distance = walk_data.get("walk_distance_m", 0)
                return distance if distance >= MIN_MEANINGFUL_DISTANCE_M else 0
            return None
        except Exception as err:
            _LOGGER.debug(
                "Error getting last walk distance for %s: %s", self.dog_id, err
            )
            return None


class WalkDurationCurrentSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current walk duration in progress."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the current walk duration sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_duration_current",
            translation_key="walk_duration_current",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon=ICONS.get("walk", "mdi:timer"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return the current walk duration if walk is in progress."""
        try:
            walk_data = self.dog_data.get("walk", {})
            if walk_data.get("walk_in_progress", False):
                start_time_str = walk_data.get("walk_start_time")
                if start_time_str:
                    try:
                        start_time = dt_util.parse_datetime(start_time_str)
                        if start_time:
                            duration_seconds = (
                                dt_util.utcnow() - start_time
                            ).total_seconds()
                            duration_minutes = duration_seconds / 60
                            return (
                                round(duration_minutes, 1)
                                if duration_minutes >= MIN_MEANINGFUL_DURATION_S / 60
                                else 0
                            )
                    except (ValueError, TypeError):
                        pass
            return None
        except Exception as err:
            _LOGGER.debug(
                "Error calculating current walk duration for %s: %s", self.dog_id, err
            )
            return None

    @property
    def available(self) -> bool:
        """Only available when walk is in progress."""
        if not super().available:
            return False
        walk_data = self.dog_data.get("walk", {})
        return walk_data.get("walk_in_progress", False)


class WalkDurationLastSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for last completed walk duration."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last walk duration sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_duration_last",
            translation_key="walk_duration_last",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon=ICONS.get("walk", "mdi:timer-outline"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return the last walk duration."""
        try:
            walk_data = self.dog_data.get("walk", {})
            if not walk_data.get("walk_in_progress", False) and walk_data.get(
                "last_walk"
            ):
                duration = walk_data.get("walk_duration_min", 0)
                return duration if duration >= MIN_MEANINGFUL_DURATION_S / 60 else 0
            return None
        except Exception as err:
            _LOGGER.debug(
                "Error getting last walk duration for %s: %s", self.dog_id, err
            )
            return None


class WalkDistanceTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total walk distance today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the total walk distance today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walk_distance_today",
            translation_key="walk_distance_today",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfLength.METERS,
            icon=ICONS.get("statistics", "mdi:sigma"),
            precision=1,
        )

    @property
    def native_value(self) -> float:
        """Return the total walk distance today."""
        try:
            walk_data = self.dog_data.get("walk", {})
            total_distance = walk_data.get("total_distance_today", 0)

            # Add current walk distance if in progress
            if walk_data.get("walk_in_progress", False):
                current_distance = walk_data.get("walk_distance_m", 0)
                total_distance += current_distance

            return round(total_distance, 1)
        except Exception as err:
            _LOGGER.debug(
                "Error getting total walk distance for %s: %s", self.dog_id, err
            )
            return 0


class WalksCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of walks completed today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the walks count today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="walks_today",
            translation_key="walks_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="walks",
            icon=ICONS.get("statistics", "mdi:counter"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of walks today."""
        try:
            walk_data = self.dog_data.get("walk", {})
            return walk_data.get("walks_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting walks count for %s: %s", self.dog_id, err)
            return 0


class LastWalkTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last completed walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last walk time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_walk_time",
            translation_key="last_walk_time",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("walk", "mdi:clock-check"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the timestamp of the last walk."""
        try:
            walk_data = self.dog_data.get("walk", {})
            return walk_data.get("last_walk")
        except Exception as err:
            _LOGGER.debug("Error getting last walk time for %s: %s", self.dog_id, err)
            return None


# ==============================================================================
# FEEDING SENSORS
# ==============================================================================


class LastFeedingTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last feeding."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last feeding time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_feeding",
            translation_key="last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("feeding", "mdi:food-drumstick"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the timestamp of the last feeding."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            return feeding_data.get("last_feeding")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last feeding time for %s: %s", self.dog_id, err
            )
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional feeding information."""
        try:
            attributes = super().extra_state_attributes or {}
            feeding_data = self.dog_data.get("feeding", {})

            attributes.update(
                {
                    "meal_type": feeding_data.get("last_meal_type"),
                    "portion_g": feeding_data.get("last_portion_g"),
                    "food_type": feeding_data.get("last_food_type"),
                }
            )

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting feeding attributes for %s: %s", self.dog_id, err
            )
            return super().extra_state_attributes


class LastMealTypeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for the type of the last meal."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last meal type sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_meal_type",
            translation_key="last_meal_type",
            device_class=SensorDeviceClass.ENUM,
            icon=ICONS.get("feeding", "mdi:food-variant"),
        )
        self._attr_options = ["breakfast", "lunch", "dinner", "snack"]

    @property
    def native_value(self) -> str | None:
        """Return the type of the last meal."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            return feeding_data.get("last_meal_type")
        except Exception as err:
            _LOGGER.debug("Error getting last meal type for %s: %s", self.dog_id, err)
            return None


class FeedingsCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total number of feedings today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the feedings count today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="feedings_today",
            translation_key="feedings_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="feedings",
            icon=ICONS.get("statistics", "mdi:food-variant"),
        )

    @property
    def native_value(self) -> int:
        """Return the total number of feedings today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings = feeding_data.get("feedings_today", {})
            return sum(feedings.values())
        except Exception as err:
            _LOGGER.debug("Error getting feedings count for %s: %s", self.dog_id, err)
            return 0


class TotalPortionsTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total food portions given today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the total portions today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="portions_today",
            translation_key="portions_today",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfMass.GRAMS,
            icon=ICONS.get("feeding", "mdi:weight-gram"),
        )

    @property
    def native_value(self) -> float:
        """Return the total portions given today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            return feeding_data.get("total_portions_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting total portions for %s: %s", self.dog_id, err)
            return 0


# Individual meal count sensors
class BreakfastCountSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for breakfast count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the breakfast count sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="breakfast_count",
            translation_key="breakfast_count",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="meals",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:coffee"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of breakfasts today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings = feeding_data.get("feedings_today", {})
            return feedings.get("breakfast", 0)
        except Exception as err:
            _LOGGER.debug("Error getting breakfast count for %s: %s", self.dog_id, err)
            return 0


class LunchCountSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for lunch count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the lunch count sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="lunch_count",
            translation_key="lunch_count",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="meals",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:silverware-fork-knife"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of lunches today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings = feeding_data.get("feedings_today", {})
            return feedings.get("lunch", 0)
        except Exception as err:
            _LOGGER.debug("Error getting lunch count for %s: %s", self.dog_id, err)
            return 0


class DinnerCountSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for dinner count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the dinner count sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="dinner_count",
            translation_key="dinner_count",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="meals",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:food-turkey"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of dinners today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings = feeding_data.get("feedings_today", {})
            return feedings.get("dinner", 0)
        except Exception as err:
            _LOGGER.debug("Error getting dinner count for %s: %s", self.dog_id, err)
            return 0


class SnackCountSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for snack count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the snack count sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="snack_count",
            translation_key="snack_count",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="snacks",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("feeding", "mdi:food-apple"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of snacks today."""
        try:
            feeding_data = self.dog_data.get("feeding", {})
            feedings = feeding_data.get("feedings_today", {})
            return feedings.get("snack", 0)
        except Exception as err:
            _LOGGER.debug("Error getting snack count for %s: %s", self.dog_id, err)
            return 0


# ==============================================================================
# HEALTH SENSORS
# ==============================================================================


class WeightSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for dog's current weight."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the weight sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="weight",
            translation_key="weight",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfMass.KILOGRAMS,
            icon=ICONS.get("health", "mdi:weight-kilogram"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return the dog's current weight."""
        try:
            health_data = self.dog_data.get("health", {})
            weight = health_data.get("weight_kg", 0)
            return weight if weight >= MIN_MEANINGFUL_WEIGHT else None
        except Exception as err:
            _LOGGER.debug("Error getting weight for %s: %s", self.dog_id, err)
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return weight trend information."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            # Add weight trend analysis
            weight_trend = health_data.get("weight_trend", [])
            if len(weight_trend) >= 2:
                recent_weights = [entry["weight"] for entry in weight_trend[-5:]]
                if len(recent_weights) >= 2:
                    weight_change = recent_weights[-1] - recent_weights[0]
                    attributes["weight_trend"] = (
                        "increasing"
                        if weight_change > 0.5
                        else "decreasing"
                        if weight_change < -0.5
                        else "stable"
                    )
                    attributes["weight_change_kg"] = round(weight_change, 1)

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting weight attributes for %s: %s", self.dog_id, err
            )
            return super().extra_state_attributes


class MedicationsTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of medications given today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the medications today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="medications_today",
            translation_key="medications_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="doses",
            icon=ICONS.get("medication", "mdi:pill"),
        )

    @property
    def native_value(self) -> int:
        """Return the number of medications given today."""
        try:
            health_data = self.dog_data.get("health", {})
            return health_data.get("medications_today", 0)
        except Exception as err:
            _LOGGER.debug(
                "Error getting medications count for %s: %s", self.dog_id, err
            )
            return 0


class LastMedicationTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last medication."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last medication time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_medication",
            translation_key="last_medication",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("medication", "mdi:pill"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the timestamp of the last medication."""
        try:
            health_data = self.dog_data.get("health", {})
            return health_data.get("last_medication")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last medication time for %s: %s", self.dog_id, err
            )
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return medication details."""
        try:
            attributes = super().extra_state_attributes or {}
            health_data = self.dog_data.get("health", {})

            attributes.update(
                {
                    "medication_name": health_data.get("medication_name"),
                    "medication_dose": health_data.get("medication_dose"),
                }
            )

            return attributes
        except Exception as err:
            _LOGGER.debug(
                "Error getting medication attributes for %s: %s", self.dog_id, err
            )
            return super().extra_state_attributes


class LastVetVisitSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last vet visit."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last vet visit sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_vet_visit",
            translation_key="last_vet_visit",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("health", "mdi:medical-bag"),
        )

    @property
    def native_value(self) -> str | None:
        """Return the timestamp of the last vet visit."""
        try:
            health_data = self.dog_data.get("health", {})
            return health_data.get("last_vet_visit")
        except Exception as err:
            _LOGGER.debug("Error getting last vet visit for %s: %s", self.dog_id, err)
            return None


class WeightTrendSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for weight trend analysis."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the weight trend sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="weight_trend",
            translation_key="weight_trend",
            device_class=SensorDeviceClass.ENUM,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("health", "mdi:trending-up"),
        )
        self._attr_options = ["increasing", "decreasing", "stable", "insufficient_data"]

    @property
    def native_value(self) -> str:
        """Return the weight trend analysis."""
        try:
            health_data = self.dog_data.get("health", {})
            weight_trend = health_data.get("weight_trend", [])

            if len(weight_trend) < 2:
                return "insufficient_data"

            # Analyze last 5 weight measurements
            recent_weights = [entry["weight"] for entry in weight_trend[-5:]]
            if len(recent_weights) >= 2:
                weight_change = recent_weights[-1] - recent_weights[0]
                if weight_change > 0.5:
                    return "increasing"
                elif weight_change < -0.5:
                    return "decreasing"
                else:
                    return "stable"

            return "insufficient_data"
        except Exception as err:
            _LOGGER.debug("Error calculating weight trend for %s: %s", self.dog_id, err)
            return "insufficient_data"


# ==============================================================================
# ACTIVITY SENSORS
# ==============================================================================


class ActivityLevelSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current activity level assessment."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the activity level sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="activity_level",
            translation_key="activity_level",
            device_class=SensorDeviceClass.ENUM,
            icon=ICONS.get("activity", "mdi:run"),
        )
        self._attr_options = ["low", "medium", "high"]

    @property
    def native_value(self) -> str:
        """Return the current activity level."""
        try:
            activity_data = self.dog_data.get("activity", {})
            return activity_data.get("activity_level", "medium")
        except Exception as err:
            _LOGGER.debug("Error getting activity level for %s: %s", self.dog_id, err)
            return "medium"


class CaloriesBurnedTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for estimated calories burned today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the calories burned today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="calories_burned_today",
            translation_key="calories_burned_today",
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="kcal",
            icon=ICONS.get("activity", "mdi:fire"),
            precision=1,
        )

    @property
    def native_value(self) -> float:
        """Return estimated calories burned today."""
        try:
            activity_data = self.dog_data.get("activity", {})
            return activity_data.get("calories_burned_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting calories burned for %s: %s", self.dog_id, err)
            return 0


class PlayTimeTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total play time today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the play time today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="play_time_today",
            translation_key="play_time_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon=ICONS.get("activity", "mdi:gamepad-variant"),
            precision=1,
        )

    @property
    def native_value(self) -> float:
        """Return total play time today."""
        try:
            activity_data = self.dog_data.get("activity", {})
            return activity_data.get("play_duration_today_min", 0)
        except Exception as err:
            _LOGGER.debug("Error getting play time for %s: %s", self.dog_id, err)
            return 0


class LastPlayTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last play session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last play time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_play_time",
            translation_key="last_play_time",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("activity", "mdi:gamepad-variant"),
        )

    @property
    def native_value(self) -> str | None:
        """Return timestamp of last play session."""
        try:
            activity_data = self.dog_data.get("activity", {})
            return activity_data.get("last_play")
        except Exception as err:
            _LOGGER.debug("Error getting last play time for %s: %s", self.dog_id, err)
            return None


# ==============================================================================
# LOCATION SENSORS (GPS MODULE)
# ==============================================================================


class DistanceFromHomeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current distance from home location."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the distance from home sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="distance_from_home",
            translation_key="distance_from_home",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            icon=ICONS.get("location", "mdi:home-map-marker"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return current distance from home."""
        try:
            location_data = self.dog_data.get("location", {})
            distance = location_data.get("distance_from_home", 0)
            return distance if distance >= 0 else None
        except Exception as err:
            _LOGGER.debug(
                "Error getting distance from home for %s: %s", self.dog_id, err
            )
            return None


class CurrentLocationSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current location description."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the current location sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="current_location",
            translation_key="current_location",
            device_class=SensorDeviceClass.ENUM,
            icon=ICONS.get("location", "mdi:map-marker"),
        )
        self._attr_options = ["home", "away", "unknown"]

    @property
    def native_value(self) -> str:
        """Return current location description."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("current_location", "unknown")
        except Exception as err:
            _LOGGER.debug("Error getting current location for %s: %s", self.dog_id, err)
            return "unknown"


class GeofenceEntersTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of geofence entries today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the geofence enters today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="geofence_enters_today",
            translation_key="geofence_enters_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="entries",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("location", "mdi:location-enter"),
        )

    @property
    def native_value(self) -> int:
        """Return number of geofence entries today."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("enters_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting geofence enters for %s: %s", self.dog_id, err)
            return 0


class GeofenceLeavesTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of geofence exits today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the geofence leaves today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="geofence_leaves_today",
            translation_key="geofence_leaves_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="exits",
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("location", "mdi:location-exit"),
        )

    @property
    def native_value(self) -> int:
        """Return number of geofence exits today."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("leaves_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting geofence leaves for %s: %s", self.dog_id, err)
            return 0


class TimeInsideTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total time inside geofence today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the time inside today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="time_inside_today",
            translation_key="time_inside_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.MINUTES,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("location", "mdi:timer-check"),
            precision=1,
        )

    @property
    def native_value(self) -> float:
        """Return total time inside geofence today."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("time_inside_today_min", 0)
        except Exception as err:
            _LOGGER.debug("Error getting time inside for %s: %s", self.dog_id, err)
            return 0


class LastGPSUpdateSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last GPS update."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last GPS update sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_gps_update",
            translation_key="last_gps_update",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("gps", "mdi:crosshairs-gps"),
        )

    @property
    def native_value(self) -> str | None:
        """Return timestamp of last GPS update."""
        try:
            location_data = self.dog_data.get("location", {})
            return location_data.get("last_gps_update")
        except Exception as err:
            _LOGGER.debug("Error getting last GPS update for %s: %s", self.dog_id, err)
            return None


class GPSAccuracySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for current GPS accuracy."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the GPS accuracy sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="gps_accuracy",
            translation_key="gps_accuracy",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            entity_category=EntityCategory.DIAGNOSTIC,
            icon=ICONS.get("gps", "mdi:crosshairs-gps"),
            precision=1,
        )

    @property
    def native_value(self) -> float | None:
        """Return current GPS accuracy."""
        try:
            # This would be populated from GPS handler data
            # For now, return None as it requires GPS handler integration
            return None
        except Exception as err:
            _LOGGER.debug("Error getting GPS accuracy for %s: %s", self.dog_id, err)
            return None


# ==============================================================================
# STATISTICS SENSORS
# ==============================================================================


class PoopCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of bathroom breaks today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the poop count today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="poop_count_today",
            translation_key="poop_count_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="events",
            icon=ICONS.get("statistics", "mdi:emoticon-poop"),
        )

    @property
    def native_value(self) -> int:
        """Return number of bathroom breaks today."""
        try:
            stats_data = self.dog_data.get("statistics", {})
            return stats_data.get("poop_count_today", 0)
        except Exception as err:
            _LOGGER.debug("Error getting poop count for %s: %s", self.dog_id, err)
            return 0


class LastPoopTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last bathroom break."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last poop time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_poop_time",
            translation_key="last_poop_time",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("statistics", "mdi:clock-check"),
        )

    @property
    def native_value(self) -> str | None:
        """Return timestamp of last bathroom break."""
        try:
            stats_data = self.dog_data.get("statistics", {})
            return stats_data.get("last_poop")
        except Exception as err:
            _LOGGER.debug("Error getting last poop time for %s: %s", self.dog_id, err)
            return None


# ==============================================================================
# GROOMING SENSORS
# ==============================================================================


class LastGroomingTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last grooming time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_grooming",
            translation_key="last_grooming",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("grooming", "mdi:shower"),
        )

    @property
    def native_value(self) -> str | None:
        """Return timestamp of last grooming session."""
        try:
            grooming_data = self.dog_data.get("grooming", {})
            return grooming_data.get("last_grooming")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last grooming time for %s: %s", self.dog_id, err
            )
            return None


class LastGroomingTypeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for type of last grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last grooming type sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_grooming_type",
            translation_key="last_grooming_type",
            device_class=SensorDeviceClass.ENUM,
            icon=ICONS.get("grooming", "mdi:content-cut"),
        )
        self._attr_options = ["bath", "brush", "ears", "eyes", "nails", "teeth", "trim"]

    @property
    def native_value(self) -> str | None:
        """Return type of last grooming session."""
        try:
            grooming_data = self.dog_data.get("grooming", {})
            return grooming_data.get("grooming_type")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last grooming type for %s: %s", self.dog_id, err
            )
            return None


class DaysSinceGroomingSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for days since last grooming session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the days since grooming sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="days_since_grooming",
            translation_key="days_since_grooming",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="d",
            icon=ICONS.get("grooming", "mdi:calendar-clock"),
        )

    @property
    def native_value(self) -> int | None:
        """Return days since last grooming session."""
        try:
            grooming_data = self.dog_data.get("grooming", {})
            last_grooming = grooming_data.get("last_grooming")

            if last_grooming:
                last_grooming_time = dt_util.parse_datetime(last_grooming)
                if last_grooming_time:
                    days_since = (dt_util.utcnow() - last_grooming_time).days
                    return max(0, days_since)
            return None
        except Exception as err:
            _LOGGER.debug(
                "Error calculating days since grooming for %s: %s", self.dog_id, err
            )
            return None


# ==============================================================================
# TRAINING SENSORS
# ==============================================================================


class LastTrainingTimeSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for timestamp of last training session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last training time sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_training",
            translation_key="last_training",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon=ICONS.get("training", "mdi:school"),
        )

    @property
    def native_value(self) -> str | None:
        """Return timestamp of last training session."""
        try:
            training_data = self.dog_data.get("training", {})
            return training_data.get("last_training")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last training time for %s: %s", self.dog_id, err
            )
            return None


class LastTrainingTopicSensor(PawControlSensorEntity, SensorEntity):
    """Sensor for topic of last training session."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the last training topic sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="last_training_topic",
            translation_key="last_training_topic",
            icon=ICONS.get("training", "mdi:book-open"),
        )

    @property
    def native_value(self) -> str | None:
        """Return topic of last training session."""
        try:
            training_data = self.dog_data.get("training", {})
            return training_data.get("last_topic")
        except Exception as err:
            _LOGGER.debug(
                "Error getting last training topic for %s: %s", self.dog_id, err
            )
            return None


class TrainingSessionsTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for number of training sessions today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the training sessions today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="training_sessions_today",
            translation_key="training_sessions_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="sessions",
            icon=ICONS.get("training", "mdi:counter"),
        )

    @property
    def native_value(self) -> int:
        """Return number of training sessions today."""
        try:
            training_data = self.dog_data.get("training", {})
            return training_data.get("training_sessions_today", 0)
        except Exception as err:
            _LOGGER.debug(
                "Error getting training sessions count for %s: %s", self.dog_id, err
            )
            return 0


class TrainingDurationTodaySensor(PawControlSensorEntity, SensorEntity):
    """Sensor for total training duration today."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the training duration today sensor."""
        super().__init__(
            coordinator=coordinator,
            entry=entry,
            dog_id=dog_id,
            entity_key="training_duration_today",
            translation_key="training_duration_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.MINUTES,
            icon=ICONS.get("training", "mdi:timer"),
            precision=1,
        )

    @property
    def native_value(self) -> float:
        """Return total training duration today."""
        try:
            training_data = self.dog_data.get("training", {})
            return training_data.get("training_duration_min", 0)
        except Exception as err:
            _LOGGER.debug(
                "Error getting training duration for %s: %s", self.dog_id, err
            )
            return 0
