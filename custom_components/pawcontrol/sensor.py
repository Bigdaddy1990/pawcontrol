"""Sensor platform for PawControl integration."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_DOG_NAME,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_GPS,
    MODULE_TRAINING,
    MODULE_GROOMING,
    ICON_DOG,
    ICON_HEALTH,
    ICON_WALK,
    ICON_FOOD,
    ICON_GPS,
    ICON_WEIGHT,
    ICON_TEMPERATURE,
    ICON_COUNTER,
    ICON_CALENDAR,
    ICON_CLOCK,
)
from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PawControl sensor entities."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    entities = []
    for dog_name, dog_data in entry_data.items():
        coordinator = dog_data["coordinator"]
        config = dog_data["config"]
        
        # Always create basic sensors
        entities.extend([
            PawControlStatusSensor(coordinator, config),
            PawControlHealthScoreSensor(coordinator, config),
            PawControlHappinessScoreSensor(coordinator, config),
            PawControlActivityScoreSensor(coordinator, config),
            PawControlDailySummarySensor(coordinator, config),
            PawControlLastActivitySensor(coordinator, config),
        ])
        
        # Get enabled modules
        modules = config.get(CONF_MODULES, {})
        
        # Feeding module sensors
        if modules.get(MODULE_FEEDING, {}).get("enabled", False):
            entities.extend([
                PawControlMealsTodaySensor(coordinator, config),
                PawControlLastFeedingSensor(coordinator, config),
                PawControlNextFeedingTimeSensor(coordinator, config),
                PawControlDailyFoodConsumedSensor(coordinator, config),
                PawControlWaterLevelSensor(coordinator, config),
                PawControlFeedingStreakSensor(coordinator, config),
            ])
        
        # Walk module sensors
        if modules.get(MODULE_WALK, {}).get("enabled", False):
            entities.extend([
                PawControlWalksTodaySensor(coordinator, config),
                PawControlWalkDistanceTodaySensor(coordinator, config),
                PawControlLastWalkSensor(coordinator, config),
                PawControlTotalWalkTimeTodaySensor(coordinator, config),
                PawControlAverageWalkDurationSensor(coordinator, config),
                PawControlCaloriesBurnedTodaySensor(coordinator, config),
                PawControlWeeklyWalkDistanceSensor(coordinator, config),
                PawControlCurrentWalkDurationSensor(coordinator, config),
                PawControlCurrentWalkDistanceSensor(coordinator, config),
            ])
        
        # Health module sensors
        if modules.get(MODULE_HEALTH, {}).get("enabled", False):
            entities.extend([
                PawControlWeightSensor(coordinator, config),
                PawControlTemperatureSensor(coordinator, config),
                PawControlHeartRateSensor(coordinator, config),
                PawControlRespiratoryRateSensor(coordinator, config),
                PawControlLastVetVisitSensor(coordinator, config),
                PawControlDaysSinceVetSensor(coordinator, config),
                PawControlMedicationCountSensor(coordinator, config),
                PawControlWeightTrendSensor(coordinator, config),
                PawControlBodyConditionScoreSensor(coordinator, config),
            ])
        
        # GPS module sensors
        if modules.get(MODULE_GPS, {}).get("enabled", False):
            entities.extend([
                PawControlLocationSensor(coordinator, config),
                PawControlDistanceFromHomeSensor(coordinator, config),
                PawControlGPSSignalSensor(coordinator, config),
                PawControlGPSBatteryLevelSensor(coordinator, config),
                PawControlCurrentSpeedSensor(coordinator, config),
                PawControlMaxSpeedTodaySensor(coordinator, config),
                PawControlTimeAwayFromHomeSensor(coordinator, config),
                PawControlLastSeenLocationSensor(coordinator, config),
            ])
        
        # Training module sensors
        if modules.get(MODULE_TRAINING, {}).get("enabled", False):
            entities.extend([
                PawControlTrainingSessionsTodaySensor(coordinator, config),
                PawControlTrainingSessionsWeekSensor(coordinator, config),
                PawControlLastTrainingSensor(coordinator, config),
                PawControlCommandsLearnedSensor(coordinator, config),
                PawControlTrainingSuccessRateSensor(coordinator, config),
                PawControlTrainingStreakSensor(coordinator, config),
            ])
        
        # Grooming module sensors
        if modules.get(MODULE_GROOMING, {}).get("enabled", False):
            entities.extend([
                PawControlLastGroomingSensor(coordinator, config),
                PawControlDaysSinceGroomingSensor(coordinator, config),
                PawControlGroomingDueSensor(coordinator, config),
                PawControlLastBathSensor(coordinator, config),
                PawControlLastNailTrimSensor(coordinator, config),
            ])
    
    async_add_entities(entities)


class PawControlSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for PawControl sensors."""

    def __init__(
        self,
        coordinator: PawControlCoordinator,
        config: dict[str, Any],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config = config
        self._dog_name = config.get(CONF_DOG_NAME, "Unknown")
        self._dog_id = self._dog_name.lower().replace(" ", "_").replace("-", "_")
        self._attr_has_entity_name = True

    @property
    def device_info(self):
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._dog_id)},
            "name": f"PawControl - {self._dog_name}",
            "manufacturer": "PawControl",
            "model": "Dog Management System",
            "sw_version": "1.0.0",
        }


# Basic Status Sensors
class PawControlStatusSensor(PawControlSensorBase):
    """Overall status sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_status"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Status"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_DOG

    @property
    def native_value(self):
        """Return the state."""
        status = self.coordinator.data.get("status", {})
        
        if status.get("emergency_mode"):
            return "🚨 Notfall"
        elif status.get("visitor_mode"):
            return "👥 Besuchermodus"
        elif status.get("walk_in_progress"):
            return "🚶 Beim Spaziergang"
        elif status.get("is_outside"):
            return "🌳 Draußen"
        elif status.get("is_sleeping"):
            return "😴 Schläft"
        elif status.get("training_in_progress"):
            return "🎾 Beim Training"
        elif status.get("needs_walk"):
            return "🚶 Braucht Spaziergang"
        elif status.get("is_hungry"):
            return "🍽️ Hungrig"
        elif status.get("needs_attention"):
            return "💗 Braucht Aufmerksamkeit"
        else:
            return "✅ Alles OK"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        status = self.coordinator.data.get("status", {})
        profile = self.coordinator.data.get("profile", {})
        
        return {
            "mood": profile.get("mood", "Unknown"),
            "health_status": profile.get("health_status", "Unknown"),
            "activity_level": profile.get("activity_level", "Unknown"),
            "last_feeding": status.get("last_feeding"),
            "last_walk": status.get("last_walk"),
            "last_medication": status.get("last_medication"),
            "needs_attention": status.get("needs_attention", False),
            "is_hungry": status.get("is_hungry", False),
            "needs_walk": status.get("needs_walk", False),
        }


class PawControlHealthScoreSensor(PawControlSensorBase):
    """Health score sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_health_score"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesundheitsscore"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_HEALTH

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("statistics", {}).get("health_score", 100)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlHappinessScoreSensor(PawControlSensorBase):
    """Happiness score sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_happiness_score"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Glücklichkeitsscore"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:emoticon-happy"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("statistics", {}).get("happiness_score", 100))

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlActivityScoreSensor(PawControlSensorBase):
    """Activity score sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_activity_score"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktivitätsscore"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:run"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("activity", {}).get("activity_score", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlDailySummarySensor(PawControlSensorBase):
    """Daily summary sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_daily_summary"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tageszusammenfassung"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-today"

    @property
    def native_value(self):
        """Return the state."""
        activity = self.coordinator.data.get("activity", {})
        
        meals = activity.get("daily_meals", 0)
        walks = activity.get("daily_walks", 0)
        distance = activity.get("walk_distance_today", 0)
        playtime = activity.get("daily_playtime", 0)
        
        return f"🍽️ {meals}x | 🚶 {walks}x | 📏 {distance:.1f}km | 🎾 {playtime}min"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        activity = self.coordinator.data.get("activity", {})
        
        return {
            "meals": activity.get("daily_meals", 0),
            "walks": activity.get("daily_walks", 0),
            "distance": activity.get("walk_distance_today", 0),
            "playtime": activity.get("daily_playtime", 0),
            "training": activity.get("daily_training", 0),
            "calories_burned": activity.get("calories_burned", 0),
        }


class PawControlLastActivitySensor(PawControlSensorBase):
    """Last activity sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_activity_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Aktivität"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:history"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_activity = self.coordinator.data.get("activity", {}).get("last_activity")
        if last_activity:
            try:
                return datetime.fromisoformat(last_activity)
            except (ValueError, TypeError):
                pass
        return None


# Feeding Module Sensors
class PawControlMealsTodaySensor(PawControlSensorBase):
    """Meals today counter sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_meals_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Mahlzeiten heute"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_FOOD

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("activity", {}).get("daily_meals", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlLastFeedingSensor(PawControlSensorBase):
    """Last feeding time sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_feeding"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Fütterung"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_FOOD

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_feeding = self.coordinator.data.get("status", {}).get("last_feeding")
        if last_feeding:
            try:
                return datetime.fromisoformat(last_feeding)
            except (ValueError, TypeError):
                pass
        return None


class PawControlNextFeedingTimeSensor(PawControlSensorBase):
    """Next feeding time sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_next_feeding_time"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Nächste Fütterung"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_CLOCK

    @property
    def native_value(self):
        """Return the state."""
        feeding = self.coordinator.data.get("feeding", {})
        now = dt_util.now()
        current_time = now.strftime("%H:%M")
        
        times = []
        if feeding.get("breakfast_time"):
            times.append(feeding["breakfast_time"])
        if feeding.get("lunch_time"):
            times.append(feeding["lunch_time"])
        if feeding.get("dinner_time"):
            times.append(feeding["dinner_time"])
        
        # Find next feeding time
        for time in sorted(times):
            if time > current_time:
                return f"Heute {time}"
        
        # If no more feedings today, return first one tomorrow
        if times:
            return f"Morgen {sorted(times)[0]}"
        
        return "Nicht geplant"


class PawControlDailyFoodConsumedSensor(PawControlSensorBase):
    """Daily food consumed sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_daily_food_consumed"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Futter heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:scale"

    @property
    def native_value(self):
        """Return the state."""
        feeding = self.coordinator.data.get("feeding", {})
        consumed = feeding.get("daily_consumed", 0)
        return consumed

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "g"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlWaterLevelSensor(PawControlSensorBase):
    """Water level sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_water_level"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Wasserstand"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:water"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("feeding", {}).get("water_level", 100)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlFeedingStreakSensor(PawControlSensorBase):
    """Feeding streak sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_feeding_streak"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Fütterungs-Streak"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:fire"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("statistics", {}).get("feeding_streak", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "Tage"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL


# Walk Module Sensors
class PawControlWalksTodaySensor(PawControlSensorBase):
    """Walks today counter sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_walks_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Spaziergänge heute"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WALK

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("activity", {}).get("daily_walks", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlWalkDistanceTodaySensor(PawControlSensorBase):
    """Walk distance today sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_walk_distance_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Spaziergang-Distanz heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:map-marker-distance"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("activity", {}).get("walk_distance_today", 0), 2)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfLength.KILOMETERS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlLastWalkSensor(PawControlSensorBase):
    """Last walk time sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_walk"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzter Spaziergang"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WALK

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_walk = self.coordinator.data.get("status", {}).get("last_walk")
        if last_walk:
            try:
                return datetime.fromisoformat(last_walk)
            except (ValueError, TypeError):
                pass
        return None


class PawControlTotalWalkTimeTodaySensor(PawControlSensorBase):
    """Total walk time today sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_total_walk_time_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gesamte Spazierzeit heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:timer"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("activity", {}).get("daily_walk_duration", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.MINUTES

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlAverageWalkDurationSensor(PawControlSensorBase):
    """Average walk duration sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_average_walk_duration"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Durchschnittliche Spaziergang-Dauer"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:timer-outline"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("statistics", {}).get("average_walk_duration", 0))

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.MINUTES

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlCaloriesBurnedTodaySensor(PawControlSensorBase):
    """Calories burned today sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_calories_burned_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Kalorien verbrannt heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:fire"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("activity", {}).get("calories_burned", 0))

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "kcal"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlWeeklyWalkDistanceSensor(PawControlSensorBase):
    """Weekly walk distance sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_weekly_walk_distance"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Wöchentliche Spaziergang-Distanz"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-week"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("statistics", {}).get("weekly_walk_distance", 0), 2)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfLength.KILOMETERS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL


class PawControlCurrentWalkDurationSensor(PawControlSensorBase):
    """Current walk duration sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_current_walk_duration"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktuelle Spaziergang-Dauer"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:timer-play"

    @property
    def native_value(self):
        """Return the state."""
        if self.coordinator.data.get("status", {}).get("walk_in_progress"):
            walk_start = self.coordinator.data.get("walk", {}).get("current_start")
            if walk_start:
                try:
                    start = datetime.fromisoformat(walk_start)
                    duration = (dt_util.now() - start).total_seconds() / 60
                    return round(duration)
                except (ValueError, TypeError):
                    pass
        return 0

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.MINUTES

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlCurrentWalkDistanceSensor(PawControlSensorBase):
    """Current walk distance sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_current_walk_distance"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktuelle Spaziergang-Distanz"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:map-marker-path"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("walk", {}).get("current_distance", 0), 2)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfLength.KILOMETERS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


# Health Module Sensors
class PawControlWeightSensor(PawControlSensorBase):
    """Weight sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_weight"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gewicht"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_WEIGHT

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("profile", {}).get("weight", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfMass.KILOGRAMS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.WEIGHT


class PawControlTemperatureSensor(PawControlSensorBase):
    """Temperature sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_temperature"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Temperatur"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_TEMPERATURE

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("health", {}).get("temperature", 38.5)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTemperature.CELSIUS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TEMPERATURE


class PawControlHeartRateSensor(PawControlSensorBase):
    """Heart rate sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_heart_rate"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Herzfrequenz"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:heart-pulse"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("health", {}).get("heart_rate", 80)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "bpm"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlRespiratoryRateSensor(PawControlSensorBase):
    """Respiratory rate sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_respiratory_rate"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Atemfrequenz"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:lungs"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("health", {}).get("respiratory_rate", 20)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "bpm"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlLastVetVisitSensor(PawControlSensorBase):
    """Last vet visit sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_vet_visit_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzter Tierarztbesuch"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:hospital-box"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_vet = self.coordinator.data.get("status", {}).get("last_vet_visit")
        if last_vet:
            try:
                return datetime.fromisoformat(last_vet)
            except (ValueError, TypeError):
                pass
        return None


class PawControlDaysSinceVetSensor(PawControlSensorBase):
    """Days since vet visit sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_days_since_vet"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tage seit Tierarzt"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-clock"

    @property
    def native_value(self):
        """Return the state."""
        last_vet = self.coordinator.data.get("status", {}).get("last_vet_visit")
        if last_vet:
            try:
                last = datetime.fromisoformat(last_vet)
                days = (dt_util.now() - last).days
                return days
            except (ValueError, TypeError):
                pass
        return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "Tage"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlMedicationCountSensor(PawControlSensorBase):
    """Medication count sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_medication_count"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Medikationen heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:pill"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("health", {}).get("daily_medications", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlWeightTrendSensor(PawControlSensorBase):
    """Weight trend sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_weight_trend"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gewichtstrend"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:trending-neutral"

    @property
    def native_value(self):
        """Return the state."""
        weight_history = self.coordinator.data.get("health", {}).get("weight_history", [])
        if len(weight_history) >= 2:
            recent = weight_history[-1].get("weight", 0)
            previous = weight_history[-2].get("weight", 0)
            diff = recent - previous
            if diff > 0.2:
                return "Zunehmend"
            elif diff < -0.2:
                return "Abnehmend"
        return "Stabil"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        weight_history = self.coordinator.data.get("health", {}).get("weight_history", [])
        if len(weight_history) >= 2:
            recent = weight_history[-1].get("weight", 0)
            previous = weight_history[-2].get("weight", 0)
            return {
                "change": round(recent - previous, 2),
                "last_weight": recent,
                "previous_weight": previous,
            }
        return {}


class PawControlBodyConditionScoreSensor(PawControlSensorBase):
    """Body condition score sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_body_condition_score"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Body Condition Score"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:scale-balance"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("health", {}).get("body_condition_score", 5)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        score = self.coordinator.data.get("health", {}).get("body_condition_score", 5)
        descriptions = {
            1: "Sehr mager",
            2: "Mager",
            3: "Dünn",
            4: "Unteres Idealgewicht",
            5: "Idealgewicht",
            6: "Oberes Idealgewicht",
            7: "Übergewichtig",
            8: "Fettleibig",
            9: "Schwer fettleibig"
        }
        return {
            "description": descriptions.get(score, "Unbekannt"),
            "ideal": score == 5,
        }


# GPS Module Sensors
class PawControlLocationSensor(PawControlSensorBase):
    """Location sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_location"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Standort"

    @property
    def icon(self):
        """Return the icon."""
        return ICON_GPS

    @property
    def native_value(self):
        """Return the state."""
        location = self.coordinator.data.get("location", {})
        if location.get("is_home"):
            return "🏠 Zuhause"
        elif location.get("current"):
            lat = location["current"].get("latitude", 0)
            lon = location["current"].get("longitude", 0)
            return f"📍 {lat:.5f}, {lon:.5f}"
        return "Unbekannt"

    @property
    def extra_state_attributes(self):
        """Return extra attributes."""
        location = self.coordinator.data.get("location", {})
        current = location.get("current", {})
        
        return {
            "latitude": current.get("latitude"),
            "longitude": current.get("longitude"),
            "accuracy": current.get("accuracy"),
            "last_update": location.get("last_update"),
            "is_home": location.get("is_home", True),
            "gps_source": location.get("source", "unknown"),
        }


class PawControlDistanceFromHomeSensor(PawControlSensorBase):
    """Distance from home sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_distance_from_home"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Entfernung von Zuhause"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:home-map-marker"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("location", {}).get("distance_from_home", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfLength.METERS

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlGPSSignalSensor(PawControlSensorBase):
    """GPS signal strength sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_gps_signal"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} GPS-Signal"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:signal"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("location", {}).get("gps_signal", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlGPSBatteryLevelSensor(PawControlSensorBase):
    """GPS battery level sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_gps_battery"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} GPS-Batterie"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:battery"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("location", {}).get("gps_battery", 100)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.BATTERY


class PawControlCurrentSpeedSensor(PawControlSensorBase):
    """Current speed sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_current_speed"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Aktuelle Geschwindigkeit"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:speedometer"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("location", {}).get("current_speed", 0), 1)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "km/h"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlMaxSpeedTodaySensor(PawControlSensorBase):
    """Max speed today sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_max_speed_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Höchstgeschwindigkeit heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:speedometer-medium"

    @property
    def native_value(self):
        """Return the state."""
        return round(self.coordinator.data.get("location", {}).get("max_speed_today", 0), 1)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "km/h"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlTimeAwayFromHomeSensor(PawControlSensorBase):
    """Time away from home sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_time_away_from_home"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Zeit von Zuhause weg"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:home-clock"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("location", {}).get("time_away_minutes", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return UnitOfTime.MINUTES

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlLastSeenLocationSensor(PawControlSensorBase):
    """Last seen location sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_seen_location"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Zuletzt gesehen"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:map-clock"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_update = self.coordinator.data.get("location", {}).get("last_update")
        if last_update:
            try:
                return datetime.fromisoformat(last_update)
            except (ValueError, TypeError):
                pass
        return None


# Training Module Sensors
class PawControlTrainingSessionsTodaySensor(PawControlSensorBase):
    """Training sessions today sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_training_sessions_today"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Trainingseinheiten heute"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:whistle"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("activity", {}).get("daily_training", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL_INCREASING


class PawControlTrainingSessionsWeekSensor(PawControlSensorBase):
    """Training sessions this week sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_training_sessions_week"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Trainingseinheiten diese Woche"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-week"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("statistics", {}).get("weekly_training_sessions", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL


class PawControlLastTrainingSensor(PawControlSensorBase):
    """Last training sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_training_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Training"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:whistle"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_training = self.coordinator.data.get("status", {}).get("last_training")
        if last_training:
            try:
                return datetime.fromisoformat(last_training)
            except (ValueError, TypeError):
                pass
        return None


class PawControlCommandsLearnedSensor(PawControlSensorBase):
    """Commands learned sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_commands_learned"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Gelernte Kommandos"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:school"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("training", {}).get("commands_learned_count", 0)

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL


class PawControlTrainingSuccessRateSensor(PawControlSensorBase):
    """Training success rate sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_training_success_rate"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Trainingserfolgsrate"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:percent"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("training", {}).get("success_rate", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return PERCENTAGE

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlTrainingStreakSensor(PawControlSensorBase):
    """Training streak sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_training_streak"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Trainings-Streak"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:fire"

    @property
    def native_value(self):
        """Return the state."""
        return self.coordinator.data.get("statistics", {}).get("training_streak", 0)

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "Tage"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.TOTAL


# Grooming Module Sensors
class PawControlLastGroomingSensor(PawControlSensorBase):
    """Last grooming sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_grooming_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Pflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:content-cut"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_grooming = self.coordinator.data.get("status", {}).get("last_grooming")
        if last_grooming:
            try:
                return datetime.fromisoformat(last_grooming)
            except (ValueError, TypeError):
                pass
        return None


class PawControlDaysSinceGroomingSensor(PawControlSensorBase):
    """Days since grooming sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_days_since_grooming"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Tage seit Pflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-clock"

    @property
    def native_value(self):
        """Return the state."""
        last_grooming = self.coordinator.data.get("status", {}).get("last_grooming")
        if last_grooming:
            try:
                last = datetime.fromisoformat(last_grooming)
                days = (dt_util.now() - last).days
                return days
            except (ValueError, TypeError):
                pass
        return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit."""
        return "Tage"

    @property
    def state_class(self):
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class PawControlGroomingDueSensor(PawControlSensorBase):
    """Grooming due sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_grooming_due"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Pflege fällig"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-alert"

    @property
    def native_value(self):
        """Return the state."""
        last_grooming = self.coordinator.data.get("status", {}).get("last_grooming")
        if last_grooming:
            try:
                last = datetime.fromisoformat(last_grooming)
                days_since = (dt_util.now() - last).days
                # Grooming typically every 4-6 weeks
                if days_since > 42:
                    return "Überfällig"
                elif days_since > 28:
                    return "Bald fällig"
                else:
                    return "Nicht fällig"
            except (ValueError, TypeError):
                pass
        return "Unbekannt"


class PawControlLastBathSensor(PawControlSensorBase):
    """Last bath sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_bath_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letztes Bad"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:shower"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_bath = self.coordinator.data.get("grooming", {}).get("last_bath")
        if last_bath:
            try:
                return datetime.fromisoformat(last_bath)
            except (ValueError, TypeError):
                pass
        return None


class PawControlLastNailTrimSensor(PawControlSensorBase):
    """Last nail trim sensor."""

    @property
    def unique_id(self):
        """Return unique ID."""
        return f"pawcontrol_{self._dog_id}_last_nail_trim_sensor"

    @property
    def name(self):
        """Return the name."""
        return f"{self._dog_name} Letzte Krallenpflege"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:hand-saw"

    @property
    def device_class(self):
        """Return the device class."""
        return SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        """Return the state."""
        last_nail = self.coordinator.data.get("grooming", {}).get("last_nail_trim")
        if last_nail:
            try:
                return datetime.fromisoformat(last_nail)
            except (ValueError, TypeError):
                pass
        return None
