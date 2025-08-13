"""Sensors for Paw Control."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .compat import DeviceInfo, EntityCategory
from .const import CONF_DOG_ID, CONF_DOG_NAME, CONF_DOGS, DOMAIN
from .coordinator import PawControlCoordinator

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
    entities: list[PawControlSensor] = []

    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        dog_name = dog.get(CONF_DOG_NAME, dog_id)

        if not dog_id:
            continue

        # Walk sensors
        entities.extend(
            [
                WalkDistanceCurrentSensor(coordinator, dog_id, dog_name),
                WalkDistanceLastSensor(coordinator, dog_id, dog_name),
                WalkDurationLastSensor(coordinator, dog_id, dog_name),
                WalkDistanceTodaySensor(coordinator, dog_id, dog_name),
                WalksCountTodaySensor(coordinator, dog_id, dog_name),
            ]
        )

        # Feeding sensors
        entities.extend(
            [
                LastFeedingTimeSensor(coordinator, dog_id, dog_name),
                FeedingsCountTodaySensor(coordinator, dog_id, dog_name),
                TotalPortionsTodaySensor(coordinator, dog_id, dog_name),
            ]
        )

        # Health sensors
        entities.extend(
            [
                WeightSensor(coordinator, dog_id, dog_name),
                MedicationsTodaySensor(coordinator, dog_id, dog_name),
            ]
        )

        # Activity sensors
        entities.extend(
            [
                ActivityLevelSensor(coordinator, dog_id, dog_name),
                CaloriesBurnedTodaySensor(coordinator, dog_id, dog_name),
            ]
        )

        # Location sensors
        entities.extend(
            [
                DistanceFromHomeSensor(coordinator, dog_id, dog_name),
                GeofenceEntersTodaySensor(coordinator, dog_id, dog_name),
                GeofenceLeavesTodaySensor(coordinator, dog_id, dog_name),
                TimeInsideTodaySensor(coordinator, dog_id, dog_name),
            ]
        )

        # Statistics sensors
        entities.extend(
            [
                PoopCountTodaySensor(coordinator, dog_id, dog_name),
                LastActionSensor(coordinator, dog_id, dog_name),
            ]
        )

        # GPS diagnostic sensors (if GPS module enabled)
        if dog.get("modules", {}).get("gps", False):
            entities.extend(
                [
                    GPSAccuracyAvgSensor(coordinator, dog_id, dog_name),
                    GPSPointsTotalSensor(coordinator, dog_id, dog_name),
                ]
            )

    if entities:
        async_add_entities(entities)


class PawControlEntity(CoordinatorEntity):
    """Base entity for Paw Control integration."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.1.0",
        )

    def _get_dog_data(self) -> dict[str, Any]:
        """Get data for this dog from coordinator."""
        return self.coordinator.get_dog_data(self._dog_id)


class PawControlSensor(PawControlEntity, SensorEntity):
    """Base class for Paw Control sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_key: str,
        translation_key: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name)
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{DOMAIN}_{dog_id}_{sensor_key}"
        self._attr_translation_key = translation_key or sensor_key

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        # When has_entity_name is True, this becomes the entity name suffix
        return self._attr_translation_key.replace("_", " ").title()


# Walk Sensors
class WalkDistanceCurrentSensor(PawControlSensor):
    """Current walk distance sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-distance"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_distance_current")

    @property
    def native_value(self) -> float | None:
        """Return the current walk distance."""
        walk_data = self._get_dog_data().get("walk", {})
        if walk_data.get("walk_in_progress"):
            return walk_data.get("walk_distance_m", 0)
        return None


class WalkDistanceLastSensor(PawControlSensor):
    """Last walk distance sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:map-marker-check"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_distance_last")

    @property
    def native_value(self) -> float | None:
        """Return the last walk distance."""
        walk_data = self._get_dog_data().get("walk", {})
        if not walk_data.get("walk_in_progress") and walk_data.get("last_walk"):
            return walk_data.get("walk_distance_m", 0)
        return None


class WalkDurationLastSensor(PawControlSensor):
    """Last walk duration sensor."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:timer-outline"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_duration_last")

    @property
    def native_value(self) -> float | None:
        """Return the last walk duration."""
        walk_data = self._get_dog_data().get("walk", {})
        if not walk_data.get("walk_in_progress") and walk_data.get("last_walk"):
            return walk_data.get("walk_duration_min", 0)
        return None


class WalkDistanceTodaySensor(PawControlSensor):
    """Total walk distance today sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:sigma"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_distance_today")

    @property
    def native_value(self) -> float:
        """Return the total walk distance today."""
        walk_data = self._get_dog_data().get("walk", {})
        return walk_data.get("total_distance_today", 0)


class WalksCountTodaySensor(PawControlSensor):
    """Walks count today sensor."""

    _attr_native_unit_of_measurement = "walks"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walks_today")

    @property
    def native_value(self) -> int:
        """Return the number of walks today."""
        walk_data = self._get_dog_data().get("walk", {})
        return walk_data.get("walks_today", 0)


# Feeding Sensors
class LastFeedingTimeSensor(PawControlSensor):
    """Last feeding time sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:food-drumstick"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_feeding")

    @property
    def native_value(self) -> str | None:
        """Return the last feeding time."""
        feeding_data = self._get_dog_data().get("feeding", {})
        return feeding_data.get("last_feeding")


class FeedingsCountTodaySensor(PawControlSensor):
    """Feedings count today sensor."""

    _attr_native_unit_of_measurement = "feedings"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:food-variant"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "feedings_today")

    @property
    def native_value(self) -> int:
        """Return the number of feedings today."""
        feeding_data = self._get_dog_data().get("feeding", {})
        feedings = feeding_data.get("feedings_today", {})
        return sum(feedings.values())


class TotalPortionsTodaySensor(PawControlSensor):
    """Total portions today sensor."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.GRAMS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:weight-gram"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "portions_today")

    @property
    def native_value(self) -> float:
        """Return the total portions today."""
        feeding_data = self._get_dog_data().get("feeding", {})
        return feeding_data.get("total_portions_today", 0)


# Health Sensors
class WeightSensor(PawControlSensor):
    """Weight sensor."""

    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weight-kilogram"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "weight")

    @property
    def native_value(self) -> float | None:
        """Return the weight."""
        health_data = self._get_dog_data().get("health", {})
        weight = health_data.get("weight_kg", 0)
        return weight if weight > 0 else None


class MedicationsTodaySensor(PawControlSensor):
    """Medications today sensor."""

    _attr_native_unit_of_measurement = "doses"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:pill"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "medications_today")

    @property
    def native_value(self) -> int:
        """Return the number of medications today."""
        health_data = self._get_dog_data().get("health", {})
        return health_data.get("medications_today", 0)


# Activity Sensors
class ActivityLevelSensor(PawControlSensor):
    """Activity level sensor."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["low", "medium", "high"]
    _attr_icon = "mdi:run"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "activity_level")

    @property
    def native_value(self) -> str:
        """Return the activity level."""
        activity_data = self._get_dog_data().get("activity", {})
        return activity_data.get("activity_level", "medium")


class CaloriesBurnedTodaySensor(PawControlSensor):
    """Calories burned today sensor."""

    _attr_native_unit_of_measurement = "kcal"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:fire"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "calories_burned_today")

    @property
    def native_value(self) -> float:
        """Return the calories burned today."""
        activity_data = self._get_dog_data().get("activity", {})
        return activity_data.get("calories_burned_today", 0)


# Location Sensors
class DistanceFromHomeSensor(PawControlSensor):
    """Distance from home sensor."""

    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-map-marker"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "distance_from_home")

    @property
    def native_value(self) -> float | None:
        """Return the distance from home."""
        location_data = self._get_dog_data().get("location", {})
        distance = location_data.get("distance_from_home", 0)
        return distance if distance >= 0 else None


class GeofenceEntersTodaySensor(PawControlSensor):
    """Geofence enters today sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "entries"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:location-enter"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "geofence_enters_today")

    @property
    def native_value(self) -> int:
        """Return the number of geofence enters today."""
        location_data = self._get_dog_data().get("location", {})
        return location_data.get("enters_today", 0)


class GeofenceLeavesTodaySensor(PawControlSensor):
    """Geofence leaves today sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "exits"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:location-exit"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "geofence_leaves_today")

    @property
    def native_value(self) -> int:
        """Return the number of geofence leaves today."""
        location_data = self._get_dog_data().get("location", {})
        return location_data.get("leaves_today", 0)


class TimeInsideTodaySensor(PawControlSensor):
    """Time inside geofence today sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:timer-check"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "time_inside_today")

    @property
    def native_value(self) -> float:
        """Return the time inside geofence today."""
        location_data = self._get_dog_data().get("location", {})
        return location_data.get("time_inside_today_min", 0)


# Statistics Sensors
class PoopCountTodaySensor(PawControlSensor):
    """Poop count today sensor."""

    _attr_native_unit_of_measurement = "poops"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:emoticon-poop"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "poop_count_today")

    @property
    def native_value(self) -> int:
        """Return the poop count today."""
        stats_data = self._get_dog_data().get("statistics", {})
        return stats_data.get("poop_count_today", 0)


class LastActionSensor(PawControlSensor):
    """Last action sensor."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:history"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_action")

    @property
    def native_value(self) -> str | None:
        """Return the last action time."""
        stats_data = self._get_dog_data().get("statistics", {})
        return stats_data.get("last_action")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        stats_data = self._get_dog_data().get("statistics", {})
        return {
            "action_type": stats_data.get("last_action_type"),
        }


# GPS Diagnostic Sensors
class GPSAccuracyAvgSensor(PawControlSensor):
    """GPS accuracy average sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "gps_accuracy_avg")

    @property
    def native_value(self) -> float | None:
        """Return the average GPS accuracy."""
        # This would be calculated from GPS handler data
        return None


class GPSPointsTotalSensor(PawControlSensor):
    """GPS points total sensor."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "points"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:map-marker-multiple"

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "gps_points_total")

    @property
    def native_value(self) -> int:
        """Return the total GPS points."""
        # This would be calculated from GPS handler data
        return 0
