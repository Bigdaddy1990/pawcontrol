"""Sensor platform for the Paw Control integration.

Optimized for Home Assistant 2025.8.2 with Python 3.13 and fixes the
Entity Registry logging issue when multiple dogs are configured.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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

# Type aliases
SensorValue = Union[str, int, float, datetime, None]
AttributeDict = dict[str, Any]

# Entity Registry optimization: reduced logging frequency
ENTITY_CREATION_DELAY = 0.05  # 50ms between entity groups
MAX_ENTITIES_PER_BATCH = 5  # Smaller batches for better performance


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Paw Control sensor platform with entity registry optimization.

    Fixes the "logging too frequently" issue by:
    - using optimized batch processing
    - reducing entity creation frequency
    - grouping entities by dog
    """
    runtime_data = getattr(entry, "runtime_data", None)

    if runtime_data:
        coordinator: PawControlCoordinator = runtime_data["coordinator"]
        dogs: list[dict[str, Any]] = runtime_data.get("dogs", [])
    else:
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        dogs = entry.data.get(CONF_DOGS, [])

    if not dogs:
        _LOGGER.warning("No dogs configured for sensor platform")
        return

    # OPTIMIZATION: group entities by dog for better registry performance
    entities_by_dog: dict[str, list[PawControlSensorBase]] = {}

    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

        dog_entities = []

        # Base sensors - always created
        dog_entities.extend(_create_base_sensors(coordinator, dog_id, dog_name))

        # Module-specific sensors
        if modules.get(MODULE_FEEDING, False):
            dog_entities.extend(_create_feeding_sensors(coordinator, dog_id, dog_name))

        if modules.get(MODULE_WALK, False):
            dog_entities.extend(_create_walk_sensors(coordinator, dog_id, dog_name))

        if modules.get(MODULE_GPS, False):
            dog_entities.extend(_create_gps_sensors(coordinator, dog_id, dog_name))

        if modules.get(MODULE_HEALTH, False):
            dog_entities.extend(_create_health_sensors(coordinator, dog_id, dog_name))

        entities_by_dog[dog_id] = dog_entities

        _LOGGER.debug(
            "Prepared %d sensor entities for dog: %s (%s)",
            len(dog_entities),
            dog_name,
            dog_id,
        )

    # Optimized entity creation to avoid overloading the registry
    total_entities = sum(len(entities) for entities in entities_by_dog.values())

    if total_entities <= 10:
        # Few entities: create all at once
        all_entities = []
        for dog_entities in entities_by_dog.values():
            all_entities.extend(dog_entities)
        async_add_entities(all_entities, update_before_add=False)
        _LOGGER.info("Created %d sensor entities (single batch)", total_entities)
    else:
        # Staggered entity creation for multiple dogs
        # Create entities per dog with small delays
        created_count = 0

        for dog_id, dog_entities in entities_by_dog.items():
            # Split large dog groups into smaller batches
            for i in range(0, len(dog_entities), MAX_ENTITIES_PER_BATCH):
                batch = dog_entities[i : i + MAX_ENTITIES_PER_BATCH]

                # Add batch without update_before_add for better performance
                async_add_entities(batch, update_before_add=False)
                created_count += len(batch)

                # Small delay between batches to relieve the registry
                if created_count < total_entities:
                    await asyncio.sleep(ENTITY_CREATION_DELAY)

        _LOGGER.info(
            "Created %d sensor entities for %d dogs (optimized batching)",
            total_entities,
            len(dogs),
        )


def _create_base_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create base sensors that are always present for every dog."""
    return [
        PawControlLastActionSensor(coordinator, dog_id, dog_name),
        PawControlDogStatusSensor(coordinator, dog_id, dog_name),
        PawControlActivityScoreSensor(coordinator, dog_id, dog_name),
    ]


def _create_feeding_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create feeding-related sensors for a dog."""
    sensors = [
        PawControlLastFeedingSensor(coordinator, dog_id, dog_name),
        PawControlLastFeedingHoursSensor(coordinator, dog_id, dog_name),
        PawControlTotalFeedingsTodaySensor(coordinator, dog_id, dog_name),
        PawControlDailyCaloriesSensor(coordinator, dog_id, dog_name),
        PawControlFeedingScheduleAdherenceSensor(coordinator, dog_id, dog_name),
    ]

    # Add meal type sensors only when needed
    for meal_type in ["breakfast", "lunch", "dinner", "snack"]:
        sensors.append(
            PawControlFeedingCountTodaySensor(coordinator, dog_id, dog_name, meal_type)
        )

    return sensors


def _create_walk_sensors(
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create walk-related sensors for a dog."""
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
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create GPS and location-related sensors for a dog."""
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
    coordinator: PawControlCoordinator, dog_id: str, dog_name: str
) -> list[PawControlSensorBase]:
    """Create health and medical-related sensors for a dog."""
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

    Optimized for reduced update frequency and improved performance.
    """

    # Class-level optimization flags
    _attr_should_poll = False  # Rely on coordinator updates
    _attr_has_entity_name = True  # Use modern entity naming

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
        entity_category: Optional[EntityCategory] = None,
    ) -> None:
        """Initialize the sensor entity."""
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

        # Device info - HA 2025.8.2 compatible
        self._attr_device_info = {
            "identifiers": {(DOMAIN, dog_id)},
            "name": dog_name,
            "manufacturer": "Paw Control",
            "model": "Smart Dog Monitoring",
            "sw_version": "1.0.0",
            "configuration_url": "https://github.com/BigDaddy1990/pawcontrol",
        }

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes."""
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "sensor_type": self._sensor_type,
        }

        # Add dog info if available
        dog_data = self._get_dog_data()
        if dog_data and "dog_info" in dog_data:
            dog_info = dog_data["dog_info"]
            attrs.update(
                {
                    "dog_breed": dog_info.get("dog_breed", ""),
                    "dog_age": dog_info.get("dog_age"),
                    "dog_size": dog_info.get("dog_size"),
                    "dog_weight": dog_info.get("dog_weight"),
                }
            )

        return attrs

    def _get_dog_data(self) -> Optional[dict[str, Any]]:
        """Get data for this sensor's dog from the coordinator."""
        if not self.coordinator.available:
            return None
        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> Optional[dict[str, Any]]:
        """Get specific module data for this dog."""
        return self.coordinator.get_module_data(self._dog_id, module)

    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        return self.coordinator.available and self._get_dog_data() is not None


# Sensor implementations


class PawControlLastActionSensor(PawControlSensorBase):
    """Sensor for tracking the last action timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:clock-outline",
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the most recent action timestamp."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return None

        timestamps: list[datetime] = []

        # Safely parse timestamps
        for module in ["feeding", "walk", "health"]:
            module_data = dog_data.get(module, {})
            timestamp_key = (
                f"last_{module}" if module != "health" else "last_health_entry"
            )

            if timestamp_str := module_data.get(timestamp_key):
                try:
                    if isinstance(timestamp_str, str):
                        timestamps.append(datetime.fromisoformat(timestamp_str))
                    elif isinstance(timestamp_str, datetime):
                        timestamps.append(timestamp_str)
                except (ValueError, TypeError):
                    pass

        return max(timestamps) if timestamps else None


class PawControlDogStatusSensor(PawControlSensorBase):
    """Sensor for overall dog status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(coordinator, dog_id, dog_name, "status", icon="mdi:dog")

    @property
    def native_value(self) -> str:
        """Return the current status of the dog."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return "unknown"

        walk_data = dog_data.get("walk", {})
        feeding_data = dog_data.get("feeding", {})
        gps_data = dog_data.get("gps", {})

        if walk_data.get("walk_in_progress", False):
            return "walking"

        if gps_data.get("zone") == "home":
            if feeding_data.get("is_hungry", False):
                return "hungry"
            elif walk_data.get("needs_walk", False):
                return "needs_walk"
            else:
                return "home"
        elif zone := gps_data.get("zone"):
            return f"at_{zone}" if zone != "unknown" else "away"

        return "away"


class PawControlActivityScoreSensor(PawControlSensorBase):
    """Sensor for calculating activity score."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "activity_score",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:chart-line",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Calculate and return the activity score."""
        dog_data = self._get_dog_data()
        if not dog_data:
            return None

        score_components = []

        # Calculate component scores
        if walk_score := self._calculate_walk_score(dog_data.get("walk", {})):
            score_components.append(("walk", walk_score, 0.4))

        if feeding_score := self._calculate_feeding_score(dog_data.get("feeding", {})):
            score_components.append(("feeding", feeding_score, 0.2))

        if gps_score := self._calculate_gps_score(dog_data.get("gps", {})):
            score_components.append(("gps", gps_score, 0.25))

        if health_score := self._calculate_health_score(dog_data.get("health", {})):
            score_components.append(("health", health_score, 0.15))

        if not score_components:
            return None

        # Calculate weighted average
        total_weight = sum(weight for _, _, weight in score_components)
        weighted_sum = sum(score * weight for _, score, weight in score_components)

        return round((weighted_sum / total_weight) if total_weight > 0 else 0, 1)

    def _calculate_walk_score(self, walk_data: dict) -> Optional[float]:
        """Calculate walk activity score."""
        walks_today = walk_data.get("walks_today", 0)
        total_duration = walk_data.get("total_duration_today", 0)

        if walks_today == 0:
            return 0.0

        walk_count_score = min(walks_today * 25, 75)
        duration_score = min(total_duration / 60 * 10, 25)

        return walk_count_score + duration_score

    def _calculate_feeding_score(self, feeding_data: dict) -> Optional[float]:
        """Calculate feeding regularity score."""
        adherence = feeding_data.get("feeding_schedule_adherence", 0)
        target_met = feeding_data.get("daily_target_met", False)

        score = adherence
        if target_met:
            score += 20

        return min(score, 100)

    def _calculate_gps_score(self, gps_data: dict) -> Optional[float]:
        """Calculate GPS activity score."""
        if not gps_data.get("last_seen"):
            return 0.0

        # Simple freshness score
        return 80.0 if gps_data.get("zone") else 0.0

    def _calculate_health_score(self, health_data: dict) -> Optional[float]:
        """Calculate health maintenance score."""
        status = health_data.get("health_status", "good")

        scores = {
            "excellent": 100,
            "very_good": 90,
            "good": 80,
            "normal": 70,
            "unwell": 40,
            "sick": 20,
        }

        return float(scores.get(status, 70))


# Feeding Sensors


class PawControlLastFeedingSensor(PawControlSensorBase):
    """Sensor for last feeding timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:food-drumstick",
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last feeding timestamp."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None

        if last_feeding := feeding_data.get("last_feeding"):
            try:
                if isinstance(last_feeding, str):
                    return datetime.fromisoformat(last_feeding)
                elif isinstance(last_feeding, datetime):
                    return last_feeding
            except (ValueError, TypeError):
                pass

        return None


class PawControlLastFeedingHoursSensor(PawControlSensorBase):
    """Sensor for hours since last feeding."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_feeding_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="h",
            icon="mdi:clock-outline",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return hours since last feeding."""
        feeding_data = self._get_module_data("feeding")
        return feeding_data.get("last_feeding_hours") if feeding_data else None


class PawControlTotalFeedingsTodaySensor(PawControlSensorBase):
    """Sensor for total feedings today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_feedings_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )

    @property
    def native_value(self) -> int:
        """Return total feedings today."""
        feeding_data = self._get_module_data("feeding")
        return feeding_data.get("total_feedings_today", 0) if feeding_data else 0


class PawControlDailyCaloriesSensor(PawControlSensorBase):
    """Sensor for daily calorie intake."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "daily_calories",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="kcal",
            icon="mdi:fire",
        )

    @property
    def native_value(self) -> float:
        """Return daily calorie intake."""
        feeding_data = self._get_module_data("feeding")
        return feeding_data.get("total_calories_today", 0.0) if feeding_data else 0.0


class PawControlFeedingScheduleAdherenceSensor(PawControlSensorBase):
    """Sensor for feeding schedule adherence."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_schedule_adherence",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:calendar-check",
        )

    @property
    def native_value(self) -> float:
        """Return feeding schedule adherence."""
        feeding_data = self._get_module_data("feeding")
        return (
            feeding_data.get("feeding_schedule_adherence", 100.0)
            if feeding_data
            else 100.0
        )


class PawControlFeedingCountTodaySensor(PawControlSensorBase):
    """Sensor for feeding count by meal type."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        meal_type: str,
    ) -> None:
        self._meal_type = meal_type
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            f"feeding_count_today_{meal_type}",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )
        self._attr_name = f"{dog_name} {meal_type.title()} Count Today"

    @property
    def native_value(self) -> int:
        """Return feeding count for meal type."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 0

        feedings_today = feeding_data.get("feedings_today")

        # Handle case where feedings_today is a dict with meal type breakdown
        if isinstance(feedings_today, dict):
            return feedings_today.get(self._meal_type, 0)

        # Handle case where feedings_today is just a total count (int)
        # We cannot provide meal-specific data from total count, so return 0
        if isinstance(feedings_today, (int, float)):
            # Log warning for debugging
            _LOGGER.debug(
                "feedings_today is %s (%s), expected dict for meal type breakdown",
                type(feedings_today).__name__,
                feedings_today,
            )
            return 0

        return 0


# Walk Sensors


class PawControlLastWalkSensor(PawControlSensorBase):
    """Sensor for last walk timestamp."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:dog-side",
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return the last walk timestamp."""
        walk_data = self._get_module_data("walk")
        if not walk_data:
            return None

        if last_walk := walk_data.get("last_walk"):
            try:
                if isinstance(last_walk, str):
                    return datetime.fromisoformat(last_walk)
                elif isinstance(last_walk, datetime):
                    return last_walk
            except (ValueError, TypeError):
                pass

        return None


class PawControlLastWalkHoursSensor(PawControlSensorBase):
    """Sensor for hours since last walk."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_hours",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="h",
            icon="mdi:clock-outline",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return hours since last walk."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("last_walk_hours") if walk_data else None


class PawControlLastWalkDurationSensor(PawControlSensorBase):
    """Sensor for last walk duration."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="min",
            icon="mdi:timer",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return last walk duration in minutes."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("last_walk_duration") if walk_data else None


class PawControlWalkCountTodaySensor(PawControlSensorBase):
    """Sensor for walk count today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "walk_count_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )

    @property
    def native_value(self) -> int:
        """Return walk count today."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("walks_today", 0) if walk_data else 0


class PawControlTotalWalkTimeTodaySensor(PawControlSensorBase):
    """Sensor for total walk time today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_walk_time_today",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="min",
            icon="mdi:timer-sand",
        )

    @property
    def native_value(self) -> int:
        """Return total walk time today in minutes."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("total_duration_today", 0) if walk_data else 0


class PawControlWeeklyWalkCountSensor(PawControlSensorBase):
    """Sensor for weekly walk count."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weekly_walk_count",
            state_class=SensorStateClass.TOTAL,
            icon="mdi:calendar-week",
        )

    @property
    def native_value(self) -> int:
        """Return weekly walk count."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("weekly_walk_count", 0) if walk_data else 0


class PawControlAverageWalkDurationSensor(PawControlSensorBase):
    """Sensor for average walk duration."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "average_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="min",
            icon="mdi:timer-outline",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return average walk duration."""
        walk_data = self._get_module_data("walk")
        return walk_data.get("average_walk_duration") if walk_data else None


# GPS Sensors


class PawControlCurrentSpeedSensor(PawControlSensorBase):
    """Sensor for current speed."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "current_speed",
            device_class=SensorDeviceClass.SPEED,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="km/h",
            icon="mdi:speedometer",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return current speed."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("current_speed") if gps_data else None


class PawControlDistanceFromHomeSensor(PawControlSensorBase):
    """Sensor for distance from home."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "distance_from_home",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="m",
            icon="mdi:home-map-marker",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return distance from home."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("distance_from_home") if gps_data else None


class PawControlGPSAccuracySensor(PawControlSensorBase):
    """Sensor for GPS accuracy."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_accuracy",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="m",
            icon="mdi:crosshairs-gps",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return GPS accuracy."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("gps_accuracy") if gps_data else None


class PawControlLastWalkDistanceSensor(PawControlSensorBase):
    """Sensor for last walk distance."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_distance",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="km",
            icon="mdi:map-marker-distance",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return last walk distance."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("last_walk_distance") if gps_data else None


class PawControlTotalDistanceTodaySensor(PawControlSensorBase):
    """Sensor for total distance today."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_distance_today",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="km",
            icon="mdi:map-clock",
        )

    @property
    def native_value(self) -> float:
        """Return total distance today."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("total_distance_today", 0.0) if gps_data else 0.0


class PawControlWeeklyDistanceSensor(PawControlSensorBase):
    """Sensor for weekly distance."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weekly_distance",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL,
            unit_of_measurement="km",
            icon="mdi:map-legend",
        )

    @property
    def native_value(self) -> float:
        """Return weekly distance."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("weekly_distance", 0.0) if gps_data else 0.0


class PawControlCurrentZoneSensor(PawControlSensorBase):
    """Sensor for current zone."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator, dog_id, dog_name, "current_zone", icon="mdi:map-marker"
        )

    @property
    def native_value(self) -> str:
        """Return current zone."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("zone", "unknown") if gps_data else "unknown"


class PawControlGPSBatteryLevelSensor(PawControlSensorBase):
    """Sensor for GPS battery level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_battery_level",
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:battery",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return GPS battery level."""
        gps_data = self._get_module_data("gps")
        return gps_data.get("battery_level") if gps_data else None


# Health Sensors


class PawControlWeightSensor(PawControlSensorBase):
    """Sensor for dog weight."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="kg",
            icon="mdi:weight",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return dog weight."""
        health_data = self._get_module_data("health")
        return health_data.get("weight") if health_data else None


class PawControlWeightTrendSensor(PawControlSensorBase):
    """Sensor for weight trend."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator, dog_id, dog_name, "weight_trend", icon="mdi:trending-up"
        )

    @property
    def native_value(self) -> str:
        """Return weight trend."""
        health_data = self._get_module_data("health")
        return health_data.get("weight_trend", "stable") if health_data else "stable"


class PawControlActivityLevelSensor(PawControlSensorBase):
    """Sensor for activity level."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator, dog_id, dog_name, "activity_level", icon="mdi:run"
        )

    @property
    def native_value(self) -> str:
        """Return activity level."""
        health_data = self._get_module_data("health")
        return health_data.get("activity_level", "normal") if health_data else "normal"


class PawControlLastVetVisitSensor(PawControlSensorBase):
    """Sensor for last vet visit."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_vet_visit",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:medical-bag",
        )

    @property
    def native_value(self) -> Optional[datetime]:
        """Return last vet visit timestamp."""
        health_data = self._get_module_data("health")
        if not health_data:
            return None

        if last_vet := health_data.get("last_vet_visit"):
            try:
                if isinstance(last_vet, str):
                    return datetime.fromisoformat(last_vet)
                elif isinstance(last_vet, datetime):
                    return last_vet
            except (ValueError, TypeError):
                pass

        return None


class PawControlDaysSinceGroomingSensor(PawControlSensorBase):
    """Sensor for days since grooming."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "days_since_grooming",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="days",
            icon="mdi:content-cut",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return days since grooming."""
        health_data = self._get_module_data("health")
        return health_data.get("days_since_grooming") if health_data else None


class PawControlHealthStatusSensor(PawControlSensorBase):
    """Sensor for health status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator, dog_id, dog_name, "health_status", icon="mdi:heart"
        )

    @property
    def native_value(self) -> str:
        """Return health status."""
        health_data = self._get_module_data("health")
        return health_data.get("health_status", "good") if health_data else "good"


class PawControlMedicationDueSensor(PawControlSensorBase):
    """Sensor for medication due status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator, dog_id, dog_name, "medication_due", icon="mdi:pill"
        )

    @property
    def native_value(self) -> str:
        """Return medication due status."""
        health_data = self._get_module_data("health")
        if health_data and health_data.get("medication_due"):
            return "due"
        return "not_due"

    @property
    def extra_state_attributes(self) -> AttributeDict:
        """Return additional state attributes."""
        attrs = super().extra_state_attributes

        health_data = self._get_module_data("health")
        if health_data and (med_details := health_data.get("medication_details")):
            attrs["medication_name"] = med_details.get("name")
            attrs["medication_dosage"] = med_details.get("dosage")
            attrs["next_dose_time"] = med_details.get("next_dose_time")

        return attrs
