"""Sensors for Paw Control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .compat import EntityCategory, UnitOfLength
from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS
from .coordinator import PawControlCoordinator
from .entity import PawControlSensorEntity

# Limit parallel updates to prevent overload
PARALLEL_UPDATES = 3


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Paw Control sensors."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator

    if not coordinator.last_update_success:
        raise PlatformNotReady

    dogs = entry.options.get(CONF_DOGS, [])
    entities: list[PawControlSensorEntity] = []

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        dog.get(CONF_DOG_NAME, dog_id)

        if not dog_id:
            continue

        # Walk sensors
        entities.extend(
            [
                WalkDistanceCurrentSensor(coordinator, entry, dog_id),
                WalkDistanceLastSensor(coordinator, entry, dog_id),
                WalkDurationLastSensor(coordinator, entry, dog_id),
                WalkDistanceTodaySensor(coordinator, entry, dog_id),
                WalksCountTodaySensor(coordinator, entry, dog_id),
            ]
        )

        # Feeding sensors
        entities.extend(
            [
                LastFeedingTimeSensor(coordinator, entry, dog_id),
                FeedingsCountTodaySensor(coordinator, entry, dog_id),
                TotalPortionsTodaySensor(coordinator, entry, dog_id),
            ]
        )

        # Health sensors
        entities.extend(
            [
                WeightSensor(coordinator, entry, dog_id),
                MedicationsTodaySensor(coordinator, entry, dog_id),
            ]
        )

        # Activity sensors
        entities.extend(
            [
                ActivityLevelSensor(coordinator, entry, dog_id),
                CaloriesBurnedTodaySensor(coordinator, entry, dog_id),
            ]
        )

        # Location sensors
        entities.extend(
            [
                DistanceFromHomeSensor(coordinator, entry, dog_id),
                GeofenceEntersTodaySensor(coordinator, entry, dog_id),
                GeofenceLeavesTodaySensor(coordinator, entry, dog_id),
                TimeInsideTodaySensor(coordinator, entry, dog_id),
            ]
        )

        # Statistics sensors
        entities.extend(
            [
                PoopCountTodaySensor(coordinator, entry, dog_id),
                LastActionSensor(coordinator, entry, dog_id),
            ]
        )

        # GPS diagnostic sensors (if GPS module enabled)
        if dog.get("modules", {}).get("gps", False):
            entities.extend(
                [
                    GPSAccuracyAvgSensor(coordinator, entry, dog_id),
                    GPSPointsTotalSensor(coordinator, entry, dog_id),
                ]
            )

    if entities:
        async_add_entities(entities)


# Walk Sensors
class WalkDistanceCurrentSensor(PawControlSensorEntity, SensorEntity):
    """Current walk distance sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walk_distance_current",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
        )
        self._attr_icon = "mdi:map-marker-distance"

    @property
    def native_value(self) -> float | None:
        """Return the current walk distance."""
        walk_data = self.dog_data.get("walk", {})
        if walk_data.get("walk_in_progress"):
            return walk_data.get("walk_distance_m", 0)
        return None


class WalkDistanceLastSensor(PawControlSensorEntity, SensorEntity):
    """Last walk distance sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walk_distance_last",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
        )
        self._attr_icon = "mdi:map-marker-check"

    @property
    def native_value(self) -> float | None:
        """Return the last walk distance."""
        walk_data = self.dog_data.get("walk", {})
        if not walk_data.get("walk_in_progress") and walk_data.get("last_walk"):
            return walk_data.get("walk_distance_m", 0)
        return None


class WalkDurationLastSensor(PawControlSensorEntity, SensorEntity):
    """Last walk duration sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walk_duration_last",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.MINUTES,
        )
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> float | None:
        """Return the last walk duration."""
        walk_data = self.dog_data.get("walk", {})
        if not walk_data.get("walk_in_progress") and walk_data.get("last_walk"):
            return walk_data.get("walk_duration_min", 0)
        return None


class WalkDistanceTodaySensor(PawControlSensorEntity, SensorEntity):
    """Total walk distance today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walk_distance_today",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfLength.METERS,
        )
        self._attr_icon = "mdi:sigma"

    @property
    def native_value(self) -> float:
        """Return the total walk distance today."""
        walk_data = self.dog_data.get("walk", {})
        return walk_data.get("total_distance_today", 0)


class WalksCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Walks count today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "walks_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="walks",
        )
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        """Return the number of walks today."""
        walk_data = self.dog_data.get("walk", {})
        return walk_data.get("walks_today", 0)


# Feeding Sensors
class LastFeedingTimeSensor(PawControlSensorEntity, SensorEntity):
    """Last feeding time sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._attr_icon = "mdi:food-drumstick"

    @property
    def native_value(self) -> str | None:
        """Return the last feeding time."""
        feeding_data = self.dog_data.get("feeding", {})
        return feeding_data.get("last_feeding")


class FeedingsCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Feedings count today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "feedings_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="feedings",
        )
        self._attr_icon = "mdi:food-variant"

    @property
    def native_value(self) -> int:
        """Return the number of feedings today."""
        feeding_data = self.dog_data.get("feeding", {})
        feedings = feeding_data.get("feedings_today", {})
        return sum(feedings.values())


class TotalPortionsTodaySensor(PawControlSensorEntity, SensorEntity):
    """Total portions today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "portions_today",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfMass.GRAMS,
        )
        self._attr_icon = "mdi:weight-gram"

    @property
    def native_value(self) -> float:
        """Return the total portions today."""
        feeding_data = self.dog_data.get("feeding", {})
        return feeding_data.get("total_portions_today", 0)


# Health Sensors
class WeightSensor(PawControlSensorEntity, SensorEntity):
    """Weight sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "weight",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfMass.KILOGRAMS,
        )
        self._attr_icon = "mdi:weight-kilogram"

    @property
    def native_value(self) -> float | None:
        """Return the weight."""
        health_data = self.dog_data.get("health", {})
        weight = health_data.get("weight_kg", 0)
        return weight if weight > 0 else None


class MedicationsTodaySensor(PawControlSensorEntity, SensorEntity):
    """Medications today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "medications_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="doses",
        )
        self._attr_icon = "mdi:pill"

    @property
    def native_value(self) -> int:
        """Return the number of medications today."""
        health_data = self.dog_data.get("health", {})
        return health_data.get("medications_today", 0)


# Activity Sensors
class ActivityLevelSensor(PawControlSensorEntity, SensorEntity):
    """Activity level sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "activity_level",
            device_class=SensorDeviceClass.ENUM,
        )
        self._attr_options = ["low", "medium", "high"]
        self._attr_icon = "mdi:run"

    @property
    def native_value(self) -> str:
        """Return the activity level."""
        activity_data = self.dog_data.get("activity", {})
        return activity_data.get("activity_level", "medium")


class CaloriesBurnedTodaySensor(PawControlSensorEntity, SensorEntity):
    """Calories burned today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "calories_burned_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="kcal",
        )
        self._attr_icon = "mdi:fire"

    @property
    def native_value(self) -> float:
        """Return the calories burned today."""
        activity_data = self.dog_data.get("activity", {})
        return activity_data.get("calories_burned_today", 0)


# Location Sensors
class DistanceFromHomeSensor(PawControlSensorEntity, SensorEntity):
    """Distance from home sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "distance_from_home",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
        )
        self._attr_icon = "mdi:home-map-marker"

    @property
    def native_value(self) -> float | None:
        """Return the distance from home."""
        location_data = self.dog_data.get("location", {})
        distance = location_data.get("distance_from_home", 0)
        return distance if distance >= 0 else None


class GeofenceEntersTodaySensor(PawControlSensorEntity, SensorEntity):
    """Geofence enters today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "geofence_enters_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="entries",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_icon = "mdi:location-enter"

    @property
    def native_value(self) -> int:
        """Return the number of geofence enters today."""
        location_data = self.dog_data.get("location", {})
        return location_data.get("enters_today", 0)


class GeofenceLeavesTodaySensor(PawControlSensorEntity, SensorEntity):
    """Geofence leaves today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "geofence_leaves_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="exits",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_icon = "mdi:location-exit"

    @property
    def native_value(self) -> int:
        """Return the number of geofence leaves today."""
        location_data = self.dog_data.get("location", {})
        return location_data.get("leaves_today", 0)


class TimeInsideTodaySensor(PawControlSensorEntity, SensorEntity):
    """Time inside geofence today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "time_inside_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement=UnitOfTime.MINUTES,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_icon = "mdi:timer-check"

    @property
    def native_value(self) -> float:
        """Return the time inside geofence today."""
        location_data = self.dog_data.get("location", {})
        return location_data.get("time_inside_today_min", 0)


# Statistics Sensors
class PoopCountTodaySensor(PawControlSensorEntity, SensorEntity):
    """Poop count today sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "poop_count_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="poops",
        )
        self._attr_icon = "mdi:emoticon-poop"

    @property
    def native_value(self) -> int:
        """Return the poop count today."""
        stats_data = self.dog_data.get("statistics", {})
        return stats_data.get("poop_count_today", 0)


class LastActionSensor(PawControlSensorEntity, SensorEntity):
    """Last action sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
        )
        self._attr_icon = "mdi:history"

    @property
    def native_value(self) -> str | None:
        """Return the last action time."""
        stats_data = self.dog_data.get("statistics", {})
        return stats_data.get("last_action")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        stats_data = self.dog_data.get("statistics", {})
        return {
            "action_type": stats_data.get("last_action_type"),
        }


# GPS Diagnostic Sensors
class GPSAccuracyAvgSensor(PawControlSensorEntity, SensorEntity):
    """GPS accuracy average sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "gps_accuracy_avg",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfLength.METERS,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_icon = "mdi:crosshairs-gps"

    @property
    def native_value(self) -> float | None:
        """Return the average GPS accuracy."""
        # This would be calculated from GPS handler data
        return None


class GPSPointsTotalSensor(PawControlSensorEntity, SensorEntity):
    """GPS points total sensor."""

    def __init__(
        self, coordinator: PawControlCoordinator, entry: ConfigEntry, dog_id: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            entry,
            dog_id,
            "gps_points_total",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="points",
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        self._attr_icon = "mdi:map-marker-multiple"

    @property
    def native_value(self) -> int:
        """Return the total GPS points."""
        # This would be calculated from GPS handler data
        return 0
