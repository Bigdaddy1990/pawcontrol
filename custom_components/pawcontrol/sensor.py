"""Sensor platform for Paw Control integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

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
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_MODULES,
    MODULE_WALK,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_GROOMING,
    MODULE_TRAINING,
    MODULE_GPS,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Paw Control sensor entities."""
    coordinator: PawControlCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    
    entities = []
    dogs = entry.options.get(CONF_DOGS, [])
    
    for dog in dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if not dog_id:
            continue
        
        dog_name = dog.get(CONF_DOG_NAME, dog_id)
        modules = dog.get(CONF_DOG_MODULES, {})
        
        # Always add basic sensors
        entities.extend([
            LastActionSensor(coordinator, dog_id, dog_name),
            LastWalkSensor(coordinator, dog_id, dog_name),
            LastFeedingSensor(coordinator, dog_id, dog_name),
            FeedingCountSensor(coordinator, dog_id, dog_name, "breakfast"),
            FeedingCountSensor(coordinator, dog_id, dog_name, "lunch"),
            FeedingCountSensor(coordinator, dog_id, dog_name, "dinner"),
            FeedingCountSensor(coordinator, dog_id, dog_name, "snack"),
            PoopCountSensor(coordinator, dog_id, dog_name),
        ])
        
        # Walk module sensors
        if modules.get(MODULE_WALK):
            entities.extend([
                WalkDurationSensor(coordinator, dog_id, dog_name),
                WalkDistanceSensor(coordinator, dog_id, dog_name),
                WalkCountSensor(coordinator, dog_id, dog_name),
                TotalDistanceTodaySensor(coordinator, dog_id, dog_name),
            ])
        
        # Health module sensors
        if modules.get(MODULE_HEALTH):
            entities.extend([
                WeightSensor(coordinator, dog_id, dog_name),
                WeightTrendSensor(coordinator, dog_id, dog_name),
                LastMedicationSensor(coordinator, dog_id, dog_name),
                MedicationCountSensor(coordinator, dog_id, dog_name),
            ])
        
        # Grooming module sensors
        if modules.get(MODULE_GROOMING):
            entities.extend([
                LastGroomingSensor(coordinator, dog_id, dog_name),
                DaysSinceGroomingSensor(coordinator, dog_id, dog_name),
            ])
        
        # Training module sensors
        if modules.get(MODULE_TRAINING):
            entities.extend([
                LastTrainingSensor(coordinator, dog_id, dog_name),
                TrainingDurationSensor(coordinator, dog_id, dog_name),
                TrainingCountSensor(coordinator, dog_id, dog_name),
            ])
        
        # Activity sensors
        entities.extend([
            PlayTimeTodaySensor(coordinator, dog_id, dog_name),
            ActivityLevelSensor(coordinator, dog_id, dog_name),
            CaloriesBurnedSensor(coordinator, dog_id, dog_name),
        ])

    # Use keyword argument for clarity instead of a positional boolean,
    # following best practices for readability.
    async_add_entities(entities, update_before_add=True)


class PawControlSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for Paw Control sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        dog_id: str,
        dog_name: str,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._dog_id = dog_id
        self._dog_name = dog_name
        self._sensor_type = sensor_type
        
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.sensor.{sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"🐕 {dog_name}",
            manufacturer="Paw Control",
            model="Smart Dog Manager",
            sw_version="1.0.0",
        )

    @property
    def dog_data(self) -> dict:
        """Get dog data from coordinator."""
        return self.coordinator.get_dog_data(self._dog_id)


class LastActionSensor(PawControlSensorBase):
    """Sensor for last action timestamp."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_action")
        self._attr_name = "Last Action"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:history"

    @property
    def native_value(self) -> datetime | None:
        """Return the last action timestamp."""
        value = self.dog_data.get("statistics", {}).get("last_action")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None


class LastWalkSensor(PawControlSensorBase):
    """Sensor for last walk timestamp."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_walk")
        self._attr_name = "Last Walk"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:dog-side"

    @property
    def native_value(self) -> datetime | None:
        """Return the last walk timestamp."""
        value = self.dog_data.get("walk", {}).get("last_walk")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None


class WalkDurationSensor(PawControlSensorBase):
    """Sensor for last walk duration."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_duration")
        self._attr_name = "Walk Duration"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:timer"

    @property
    def native_value(self) -> float | None:
        """Return the last walk duration."""
        return self.dog_data.get("walk", {}).get("walk_duration_min", 0)


class WalkDistanceSensor(PawControlSensorBase):
    """Sensor for last walk distance."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walk_distance")
        self._attr_name = "Walk Distance"
        self._attr_native_unit_of_measurement = UnitOfLength.METERS
        self._attr_device_class = SensorDeviceClass.DISTANCE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:map-marker-distance"

    @property
    def native_value(self) -> float | None:
        """Return the last walk distance."""
        return self.dog_data.get("walk", {}).get("walk_distance_m", 0)


class WalkCountSensor(PawControlSensorBase):
    """Sensor for walks today count."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "walks_today")
        self._attr_name = "Walks Today"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        """Return the walks today count."""
        return self.dog_data.get("walk", {}).get("walks_today", 0)


class TotalDistanceTodaySensor(PawControlSensorBase):
    """Sensor for total distance walked today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "total_distance_today")
        self._attr_name = "Total Distance Today"
        self._attr_native_unit_of_measurement = UnitOfLength.METERS
        self._attr_device_class = SensorDeviceClass.DISTANCE
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:map-marker-path"

    @property
    def native_value(self) -> float:
        """Return the total distance walked today."""
        return self.dog_data.get("walk", {}).get("total_distance_today", 0)


class LastFeedingSensor(PawControlSensorBase):
    """Sensor for last feeding timestamp."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_feeding")
        self._attr_name = "Last Feeding"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:food-drumstick"

    @property
    def native_value(self) -> datetime | None:
        """Return the last feeding timestamp."""
        value = self.dog_data.get("feeding", {}).get("last_feeding")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        feeding_data = self.dog_data.get("feeding", {})
        return {
            "meal_type": feeding_data.get("last_meal_type"),
            "portion_g": feeding_data.get("last_portion_g"),
            "food_type": feeding_data.get("last_food_type"),
        }


class FeedingCountSensor(PawControlSensorBase):
    """Sensor for feeding count by meal type."""

    def __init__(self, coordinator, dog_id, dog_name, meal_type):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, f"feeding_{meal_type}")
        self._meal_type = meal_type
        self._attr_name = f"{meal_type.capitalize()} Count"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        """Return the feeding count for this meal type."""
        feedings = self.dog_data.get("feeding", {}).get("feedings_today", {})
        return feedings.get(self._meal_type, 0)


class WeightSensor(PawControlSensorBase):
    """Sensor for dog weight."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "weight")
        self._attr_name = "Weight"
        self._attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
        self._attr_device_class = SensorDeviceClass.WEIGHT
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:weight"

    @property
    def native_value(self) -> float | None:
        """Return the dog's weight."""
        return self.dog_data.get("health", {}).get("weight_kg", 0)


class WeightTrendSensor(PawControlSensorBase):
    """Sensor for weight trend."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "weight_trend")
        self._attr_name = "Weight Trend"
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:trending-up"

    @property
    def native_value(self) -> float | None:
        """Calculate weight trend percentage."""
        weight_trend = self.dog_data.get("health", {}).get("weight_trend", [])
        if len(weight_trend) < 2:
            return 0
        
        # Calculate trend from last two measurements
        current = weight_trend[-1].get("weight", 0)
        previous = weight_trend[-2].get("weight", 0)
        
        if previous > 0:
            return round(((current - previous) / previous) * 100, 2)
        return 0


class LastMedicationSensor(PawControlSensorBase):
    """Sensor for last medication timestamp."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_medication")
        self._attr_name = "Last Medication"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:pill"

    @property
    def native_value(self) -> datetime | None:
        """Return the last medication timestamp."""
        value = self.dog_data.get("health", {}).get("last_medication")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        health_data = self.dog_data.get("health", {})
        return {
            "medication_name": health_data.get("medication_name"),
            "dose": health_data.get("medication_dose"),
        }


class MedicationCountSensor(PawControlSensorBase):
    """Sensor for medications given today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "medications_today")
        self._attr_name = "Medications Today"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        """Return the medication count for today."""
        return self.dog_data.get("health", {}).get("medications_today", 0)


class LastGroomingSensor(PawControlSensorBase):
    """Sensor for last grooming date."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_grooming")
        self._attr_name = "Last Grooming"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:content-cut"

    @property
    def native_value(self) -> datetime | None:
        """Return the last grooming timestamp."""
        value = self.dog_data.get("grooming", {}).get("last_grooming")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        grooming_data = self.dog_data.get("grooming", {})
        return {
            "grooming_type": grooming_data.get("grooming_type"),
            "interval_days": grooming_data.get("grooming_interval_days", 30),
        }


class DaysSinceGroomingSensor(PawControlSensorBase):
    """Sensor for days since last grooming."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "days_since_grooming")
        self._attr_name = "Days Since Grooming"
        self._attr_native_unit_of_measurement = "days"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:calendar-clock"

    @property
    def native_value(self) -> int | None:
        """Return days since last grooming."""
        last_grooming = self.dog_data.get("grooming", {}).get("last_grooming")
        if not last_grooming:
            return None
        
        try:
            last_date = datetime.fromisoformat(last_grooming)
            return (datetime.now() - last_date).days
        except (ValueError, TypeError):
            return None


class LastTrainingSensor(PawControlSensorBase):
    """Sensor for last training session."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "last_training")
        self._attr_name = "Last Training"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_icon = "mdi:school"

    @property
    def native_value(self) -> datetime | None:
        """Return the last training timestamp."""
        value = self.dog_data.get("training", {}).get("last_training")
        if value:
            try:
                return datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return None
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        training_data = self.dog_data.get("training", {})
        return {
            "topic": training_data.get("last_topic"),
            "duration_min": training_data.get("training_duration_min"),
        }


class TrainingDurationSensor(PawControlSensorBase):
    """Sensor for training duration."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "training_duration")
        self._attr_name = "Training Duration"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self) -> float:
        """Return the training duration."""
        return self.dog_data.get("training", {}).get("training_duration_min", 0)


class TrainingCountSensor(PawControlSensorBase):
    """Sensor for training sessions today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "training_sessions_today")
        self._attr_name = "Training Sessions Today"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int:
        """Return the training sessions count for today."""
        return self.dog_data.get("training", {}).get("training_sessions_today", 0)


class PlayTimeTodaySensor(PawControlSensorBase):
    """Sensor for play time today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "play_time_today")
        self._attr_name = "Play Time Today"
        self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        self._attr_device_class = SensorDeviceClass.DURATION
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:tennis-ball"

    @property
    def native_value(self) -> float:
        """Return the play time for today."""
        return self.dog_data.get("activity", {}).get("play_duration_today_min", 0)


class ActivityLevelSensor(PawControlSensorBase):
    """Sensor for activity level."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "activity_level")
        self._attr_name = "Activity Level"
        self._attr_icon = "mdi:run"

    @property
    def native_value(self) -> str:
        """Return the activity level."""
        return self.dog_data.get("activity", {}).get("activity_level", "medium")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        activity_data = self.dog_data.get("activity", {})
        walk_data = self.dog_data.get("walk", {})
        
        total_activity_min = (
            walk_data.get("walk_duration_min", 0) +
            activity_data.get("play_duration_today_min", 0)
        )
        
        return {
            "total_activity_min": total_activity_min,
            "walks_today": walk_data.get("walks_today", 0),
            "play_time_min": activity_data.get("play_duration_today_min", 0),
        }


class CaloriesBurnedSensor(PawControlSensorBase):
    """Sensor for calories burned today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "calories_burned_today")
        self._attr_name = "Calories Burned Today"
        self._attr_native_unit_of_measurement = "kcal"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:fire"

    @property
    def native_value(self) -> float:
        """Return the calories burned today."""
        return self.dog_data.get("activity", {}).get("calories_burned_today", 0)


class PoopCountSensor(PawControlSensorBase):
    """Sensor for poop count today."""

    def __init__(self, coordinator, dog_id, dog_name):
        """Initialize the sensor."""
        super().__init__(coordinator, dog_id, dog_name, "poop_count_today")
        self._attr_name = "Poop Count Today"
        self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        self._attr_icon = "mdi:emoticon-poop"

    @property
    def native_value(self) -> int:
        """Return the poop count for today."""
        return self.dog_data.get("statistics", {}).get("poop_count_today", 0)
