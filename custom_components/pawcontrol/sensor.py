"""Sensor platform for the Paw Control integration with profile-based entity creation.

Performance-optimized for Home Assistant 2025.9.0+ with Python 3.13.
Reduces entity count from 54+ to 8-18 per dog using profile-based factory.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from typing import Any, Optional, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
)
from .coordinator import PawControlCoordinator
from .entity_factory import EntityFactory
from .utils import create_device_info

_LOGGER = logging.getLogger(__name__)

# Type aliases
SensorValue = Union[str, int, float, datetime, None]
AttributeDict = dict[str, Any]

# OPTIMIZATION: Performance tuning for profile-based setup
ENTITY_CREATION_DELAY = 0.01  # 10ms between batches (reduced for fewer entities)
MAX_ENTITIES_PER_BATCH = 8  # Smaller batches for profile-based creation
PARALLEL_THRESHOLD = 15  # Lower threshold due to fewer entities
ACTIVITY_SCORE_CACHE_TTL = 300  # 5 minutes cache for activity scores


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Paw Control sensor platform with profile-based entity creation."""

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

    # Initialize entity factory
    entity_factory = EntityFactory(coordinator)

    # Get profile from options (default to 'standard')
    profile = entry.options.get("entity_profile", "standard")

    _LOGGER.info("Setting up sensors with profile '%s' for %d dogs", profile, len(dogs))

    # PERFORMANCE OPTIMIZATION: Profile-based entity creation
    all_entities = []
    total_entities_created = 0

    for dog in dogs:
        dog_id: str = dog[CONF_DOG_ID]
        dog_name: str = dog[CONF_DOG_NAME]
        modules: dict[str, bool] = dog.get("modules", {})

        # Create profile-based entities using factory
        dog_entities = entity_factory.create_entities_for_dog(
            dog_id=dog_id, dog_name=dog_name, profile=profile, modules=modules
        )

        all_entities.extend(dog_entities)
        total_entities_created += len(dog_entities)

        _LOGGER.info(
            "Created %d entities for dog: %s (%s) with profile '%s'",
            len(dog_entities),
            dog_name,
            dog_id,
            profile,
        )

    # OPTIMIZATION: Smart batching based on reduced entity count
    if total_entities_created <= PARALLEL_THRESHOLD:
        # Small setup: Create all at once
        async_add_entities(all_entities, update_before_add=False)
        _LOGGER.info(
            "Created %d sensor entities (single batch) - %d%% reduction from legacy count",
            total_entities_created,
            int(
                (1 - total_entities_created / (len(dogs) * 54)) * 100
            ),  # 54 was legacy count
        )
    else:
        # Large setup: Batch creation with minimal delays
        async def add_entity_batch(entities: list[PawControlSensorBase]) -> None:
            """Add a batch of entities asynchronously."""
            async_add_entities(entities, update_before_add=False)

        # Create tasks for parallel entity addition
        tasks = []
        for i in range(0, len(all_entities), MAX_ENTITIES_PER_BATCH):
            batch = all_entities[i : i + MAX_ENTITIES_PER_BATCH]
            tasks.append(add_entity_batch(batch))

            # Add small delay between batches
            if i + MAX_ENTITIES_PER_BATCH < len(all_entities):
                await asyncio.sleep(ENTITY_CREATION_DELAY)

        # Execute all tasks
        if tasks:
            await asyncio.gather(*tasks)

        _LOGGER.info(
            "Created %d sensor entities for %d dogs (profile-based batching) - %d%% performance improvement",
            total_entities_created,
            len(dogs),
            int((1 - total_entities_created / (len(dogs) * 54)) * 100),
        )

    # Log profile statistics
    profile_info = entity_factory.get_profile_info(profile)
    _LOGGER.info(
        "Profile '%s': %s - avg %.1f entities/dog (max %d)",
        profile,
        profile_info["description"],
        total_entities_created / len(dogs),
        profile_info["max_entities"],
    )


class PawControlSensorBase(CoordinatorEntity[PawControlCoordinator], SensorEntity):
    """Base sensor class with optimized data access and caching."""

    _attr_should_poll = False
    _attr_has_entity_name = True

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
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._sensor_type = sensor_type
        self._attr_unique_id = f"pawcontrol_{dog_id}_{sensor_type}"
        self._attr_name = f"{dog_name} {sensor_type.replace('_', ' ').title()}"
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        # Device info for proper grouping - HA 2025.8+ compatible with configuration_url
        self._attr_device_info = create_device_info(dog_id, dog_name)

        # OPTIMIZATION: Per-update module data cache
        self._module_cache: dict[str, Any] = {}
        self._cache_timestamp: Optional[datetime] = None

    def _get_dog_data(self) -> Optional[dict[str, Any]]:
        """Get dog data from coordinator."""
        if not self.coordinator.available:
            return None
        return self.coordinator.get_dog_data(self._dog_id)

    def _get_module_data(self, module: str) -> Optional[dict[str, Any]]:
        """Get module data with per-update caching."""
        # OPTIMIZATION: Cache module data for the current update cycle
        now = dt_util.utcnow()
        if (
            self._cache_timestamp is None
            or (now - self._cache_timestamp).total_seconds() > 1
        ):
            # Cache expired or first access
            self._module_cache.clear()
            self._cache_timestamp = now

        if module not in self._module_cache:
            dog_data = self._get_dog_data()
            if dog_data:
                self._module_cache[module] = dog_data.get(module, {})
            else:
                self._module_cache[module] = None

        return self._module_cache[module]

    @property
    def available(self) -> bool:
        return self.coordinator.available and self._get_dog_data() is not None

    @property
    def extra_state_attributes(self) -> AttributeDict:
        attrs: AttributeDict = {
            ATTR_DOG_ID: self._dog_id,
            ATTR_DOG_NAME: self._dog_name,
            "sensor_type": self._sensor_type,
        }
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


# Core Sensor Implementations (Always Created)


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

        for module in ["feeding", "walk", "health"]:
            module_data = dog_data.get(module, {})
            timestamp_key = (
                f"last_{module}" if module != "health" else "last_health_entry"
            )
            if timestamp_str := module_data.get(timestamp_key):
                if isinstance(timestamp_str, str):
                    with suppress(ValueError, TypeError):
                        timestamps.append(datetime.fromisoformat(timestamp_str))
                elif isinstance(timestamp_str, datetime):
                    timestamps.append(timestamp_str)

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
            return STATE_UNKNOWN

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
            return f"at_{zone}" if zone != STATE_UNKNOWN else "away"

        return "away"


class PawControlActivityScoreSensor(PawControlSensorBase):
    """Sensor for calculating activity score with caching."""

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
        # OPTIMIZATION: Cache for activity score
        self._cached_score: Optional[float] = None
        self._score_cache_time: Optional[datetime] = None

    @property
    def native_value(self) -> Optional[float]:
        """Calculate and return the activity score with caching."""
        # OPTIMIZATION: Use cached score if still valid
        now = dt_util.utcnow()
        if (
            self._cached_score is not None
            and self._score_cache_time is not None
            and (now - self._score_cache_time).total_seconds()
            < ACTIVITY_SCORE_CACHE_TTL
        ):
            return self._cached_score

        # Calculate new score
        dog_data = self._get_dog_data()
        if not dog_data:
            return None

        score_components = []

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

        total_weight = sum(weight for _, _, weight in score_components)
        weighted_sum = sum(score * weight for _, score, weight in score_components)

        score = round((weighted_sum / total_weight) if total_weight > 0 else 0, 1)

        # Cache the result
        self._cached_score = score
        self._score_cache_time = now

        return score

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


class PawControlActivityLevelSensor(PawControlActivityScoreSensor):
    """Backward-compatible alias for activity score sensor."""

    pass


# Essential Feeding Sensors


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
            if isinstance(last_feeding, str):
                with suppress(ValueError, TypeError):
                    return datetime.fromisoformat(last_feeding)
            elif isinstance(last_feeding, datetime):
                return last_feeding

        return None


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


class PawControlHealthAwarePortionSensor(PawControlSensorBase):
    """Sensor for health-aware calculated portion size."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_aware_portion",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="g",
            icon="mdi:scale",
        )

    @property
    def native_value(self) -> Optional[float]:
        """Return health-aware calculated portion size."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None

        # Get health-aware portion from feeding manager
        health_portion = feeding_data.get("health_aware_portion")
        if health_portion is not None:
            return round(float(health_portion), 1)

        # Fallback to basic portion calculation
        daily_amount = feeding_data.get("daily_amount_target", 500)
        meals_per_day = feeding_data.get("config", {}).get("meals_per_day", 2)

        if meals_per_day > 0:
            return round(daily_amount / meals_per_day, 1)

        return None


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


class PawControlFeedingRecommendationSensor(PawControlSensorBase):
    """Sensor for feeding recommendations based on health analysis."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "feeding_recommendation",
            icon="mdi:lightbulb",
        )

    @property
    def native_value(self) -> str:
        """Return primary feeding recommendation."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return "No data available"

        # Get feeding analysis
        analysis = feeding_data.get("feeding_analysis", {})
        recommendations = analysis.get("recommendations", [])

        if recommendations:
            return recommendations[0]  # Primary recommendation

        # Default based on adherence
        adherence = feeding_data.get("schedule_adherence", 100)
        if adherence >= 90:
            return "Feeding schedule is well maintained"
        elif adherence >= 70:
            return "Consider improving meal timing consistency"
        else:
            return "Feeding schedule needs attention"


class PawControlDietValidationStatusSensor(PawControlSensorBase):
    """Sensor for overall diet validation status."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "diet_validation_status",
            icon="mdi:food-apple",
        )

    @property
    def native_value(self) -> str:
        """Return diet validation status."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return "no_data"

        diet_validation = feeding_data.get("diet_validation_summary")
        if not diet_validation:
            return "no_validation"

        if diet_validation.get("conflict_count", 0) > 0:
            return "conflicts_detected"
        elif diet_validation.get("warning_count", 0) > 0:
            return "warnings_present"
        else:
            return "validated_safe"


# Essential Walk Sensors


class PawControlLastWalkSensor(PawControlSensorBase):
    """Sensor for last walk timestamp."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:walk",
        )

    @property
    def native_value(self) -> Optional[datetime]:
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
                return None
        return None


class PawControlWalkCountTodaySensor(PawControlSensorBase):
    """Sensor for walk count today."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
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
        walk_data = self._get_module_data("walk")
        return walk_data.get("walks_today", 0) if walk_data else 0


class PawControlLastWalkDurationSensor(PawControlSensorBase):
    """Sensor for duration of last walk."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_walk_duration",
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement="min",
            icon="mdi:timer",
        )

    @property
    def native_value(self) -> Optional[int]:
        walk_data = self._get_module_data("walk")
        return walk_data.get("last_walk_duration") if walk_data else None


class PawControlTotalWalkTimeTodaySensor(PawControlSensorBase):
    """Sensor for total walk time today."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_walk_time_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement="min",
            icon="mdi:timer-sand",
        )

    @property
    def native_value(self) -> int:
        walk_data = self._get_module_data("walk")
        return walk_data.get("total_duration_today", 0) if walk_data else 0


class PawControlWeeklyWalkCountSensor(PawControlSensorBase):
    """Sensor for weekly walk count."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weekly_walk_count",
            state_class=SensorStateClass.TOTAL_INCREASING,
            icon="mdi:counter",
        )

    @property
    def native_value(self) -> int:
        walk_data = self._get_module_data("walk")
        return walk_data.get("weekly_walks", 0) if walk_data else 0


class PawControlAverageWalkDurationSensor(PawControlSensorBase):
    """Sensor for average walk duration."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "average_walk_duration",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.DURATION,
            unit_of_measurement="min",
            icon="mdi:timer-outline",
        )

    @property
    def native_value(self) -> Optional[float]:
        walk_data = self._get_module_data("walk")
        return walk_data.get("average_duration") if walk_data else None


# Essential GPS Sensors


class PawControlCurrentZoneSensor(PawControlSensorBase):
    """Sensor for current zone."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(coordinator, dog_id, dog_name, "current_zone", icon="mdi:map")

    @property
    def native_value(self) -> str:
        gps_data = self._get_module_data("gps")
        return gps_data.get("zone", STATE_UNKNOWN) if gps_data else STATE_UNKNOWN


class PawControlDistanceFromHomeSensor(PawControlSensorBase):
    """Sensor for distance from home."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "distance_from_home",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="m",
            icon="mdi:map-marker-distance",
        )

    @property
    def native_value(self) -> Optional[float]:
        gps_data = self._get_module_data("gps")
        return gps_data.get("distance_from_home") if gps_data else None


class PawControlCurrentSpeedSensor(PawControlSensorBase):
    """Sensor for current speed."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "current_speed",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="km/h",
            icon="mdi:speedometer",
        )

    @property
    def native_value(self) -> Optional[float]:
        gps_data = self._get_module_data("gps")
        return gps_data.get("current_speed") if gps_data else None


class PawControlGPSAccuracySensor(PawControlSensorBase):
    """Sensor for GPS accuracy."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_accuracy",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="m",
            icon="mdi:crosshairs-gps",
        )

    @property
    def native_value(self) -> Optional[float]:
        gps_data = self._get_module_data("gps")
        return gps_data.get("accuracy") if gps_data else None


class PawControlTotalDistanceTodaySensor(PawControlSensorBase):
    """Sensor for total distance today."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "total_distance_today",
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit_of_measurement="m",
            icon="mdi:map-marker-path",
        )

    @property
    def native_value(self) -> float:
        gps_data = self._get_module_data("gps")
        return gps_data.get("total_distance_today", 0.0) if gps_data else 0.0


class PawControlGPSBatteryLevelSensor(PawControlSensorBase):
    """Sensor for GPS tracker battery level."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "gps_battery_level",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.BATTERY,
            unit_of_measurement=PERCENTAGE,
            icon="mdi:battery",
        )

    @property
    def native_value(self) -> Optional[int]:
        gps_data = self._get_module_data("gps")
        return gps_data.get("battery") if gps_data else None


# Essential Health Sensors


class PawControlHealthStatusSensor(PawControlSensorBase):
    """Sensor for overall health status."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "health_status",
            icon="mdi:heart-pulse",
        )

    @property
    def native_value(self) -> str:
        health_data = self._get_module_data("health")
        return (
            health_data.get("health_status", "good") if health_data else STATE_UNKNOWN
        )


class PawControlWeightSensor(PawControlSensorBase):
    """Sensor for dog weight."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight",
            state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.WEIGHT,
            unit_of_measurement="kg",
            icon="mdi:scale-bathroom",
        )

    @property
    def native_value(self) -> Optional[float]:
        health_data = self._get_module_data("health")
        return health_data.get("weight") if health_data else None


class PawControlBodyConditionScoreSensor(PawControlSensorBase):
    """Sensor for body condition score (1-9 scale)."""

    def __init__(
        self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
    ) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "body_condition_score",
            state_class=SensorStateClass.MEASUREMENT,
            icon="mdi:weight",
        )

    @property
    def native_value(self) -> Optional[int]:
        """Return body condition score."""
        health_data = self._get_module_data("health")
        if not health_data:
            return None

        return health_data.get("body_condition_score")


class PawControlWeightTrendSensor(PawControlSensorBase):
    """Sensor for dog weight trend."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "weight_trend",
            icon="mdi:trending-up",
        )

    @property
    def native_value(self) -> str:
        health_data = self._get_module_data("health")
        return (
            health_data.get("weight_trend", "stable") if health_data else STATE_UNKNOWN
        )


class PawControlLastVetVisitSensor(PawControlSensorBase):
    """Sensor for last vet visit timestamp."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "last_vet_visit",
            device_class=SensorDeviceClass.TIMESTAMP,
            icon="mdi:stethoscope",
        )

    @property
    def native_value(self) -> Optional[datetime]:
        health_data = self._get_module_data("health")
        if not health_data:
            return None
        if last_visit := health_data.get("last_vet_visit"):
            try:
                if isinstance(last_visit, str):
                    return datetime.fromisoformat(last_visit)
                elif isinstance(last_visit, datetime):
                    return last_visit
            except (ValueError, TypeError):
                return None
        return None


# Advanced Feeding Sensors (for detailed meal tracking)


class PawControlFeedingCountTodaySensor(PawControlSensorBase):
    """Sensor for feeding count by meal type with strict type validation."""

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
        """Return feeding count for meal type with consistent typing."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return 0

        feedings_today = feeding_data.get("feedings_today")

        # Expected dict: {'breakfast': int, 'lunch': int, 'dinner': int, 'snack': int}
        if isinstance(feedings_today, dict):
            try:
                return int(feedings_today.get(self._meal_type, 0))
            except (TypeError, ValueError):
                _LOGGER.warning(
                    "feedings_today[%s] not coercible to int: %s",
                    self._meal_type,
                    feedings_today.get(self._meal_type),
                )
                return 0

        return 0


class PawControlMealPortionSensor(PawControlSensorBase):
    """Sensor for specific meal type portion with health awareness."""

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
            f"{meal_type}_portion",
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement="g",
            icon="mdi:bowl-mix",
        )
        self._attr_name = f"{dog_name} {meal_type.title()} Portion"

    @property
    def native_value(self) -> Optional[float]:
        """Return portion size for specific meal type."""
        feeding_data = self._get_module_data("feeding")
        if not feeding_data:
            return None

        # Try to get health-aware portion for this meal type
        meal_portion_key = f"{self._meal_type}_portion"
        meal_portion = feeding_data.get(meal_portion_key)

        if meal_portion is not None:
            return round(float(meal_portion), 1)

        # Fallback to calculated portion
        base_portion = feeding_data.get("health_aware_portion")
        if base_portion:
            # Apply meal-type specific multipliers
            multipliers = {
                "breakfast": 1.1,
                "lunch": 0.9,
                "dinner": 1.0,
                "snack": 0.3,
            }
            multiplier = multipliers.get(self._meal_type, 1.0)
            return round(base_portion * multiplier, 1)

        return None


# Grooming Sensors


class PawControlDaysSinceGroomingSensor(PawControlSensorBase):
    """Sensor for days since last grooming."""

    def __init__(self, coordinator, dog_id: str, dog_name: str) -> None:
        super().__init__(
            coordinator,
            dog_id,
            dog_name,
            "days_since_grooming",
            icon="mdi:content-cut",
        )

    @property
    def native_value(self) -> Optional[int]:
        grooming_data = self._get_module_data("grooming")
        if not grooming_data:
            return None
        last = grooming_data.get("last_grooming")
        if not last:
            return None
        try:
            last_dt = datetime.fromisoformat(last)
        except (ValueError, TypeError):
            return None
        return (dt_util.utcnow().date() - last_dt.date()).days


# Additional sensors omitted for brevity - they would follow the same pattern
# and be created based on profile requirements through the EntityFactory
