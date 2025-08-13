"""Sensor factory to eliminate code duplication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


@dataclass
class SensorConfig:
    """Configuration for a sensor."""

    key: str
    name: str
    data_path: str
    device_class: Optional[SensorDeviceClass] = None
    state_class: Optional[SensorStateClass] = None
    unit: Optional[str] = None
    options: Optional[list[str]] = None
    entity_category: Optional[str] = None
    default_value: Any = None
    transform_func: Optional[callable] = None


class ConfigurableDogSensor(SensorEntity, RestoreSensor):
    def __init__(
        self, hass: HomeAssistant, dog_id: str, title: str, config: SensorConfig
    ):
        self.hass = hass
        self._dog = dog_id
        self._name = title
        self._config = config
        self._attr_unique_id = f"{DOMAIN}.{dog_id}.sensor.{config.key}"
        self._attr_translation_key = config.key
        self._apply_class_map(config.key)
        self._apply_classes_from_key(config.key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dog_id)},
            name=f"Hund {title}",
            manufacturer="Paw Control",
            model="PawControl Sensors",
        )

        # Apply configuration
        if config.device_class:
            self._attr_device_class = config.device_class
        if config.state_class:
            self._attr_state_class = config.state_class
        if config.unit:
            self._attr_native_unit_of_measurement = config.unit
        if config.options:
            self._attr_options = config.options
        if config.entity_category:
            self._attr_entity_category = config.entity_category

    def _get_coordinator_data(self, path: str, default: Any = None) -> Any:
        """Get data from coordinator safely."""
        domain_data = self.hass.data.get(DOMAIN, {})
        for entry_data in domain_data.values():
            if isinstance(entry_data, dict) and "coordinator" in entry_data:
                coordinator = entry_data["coordinator"]
                if coordinator and hasattr(coordinator, "get_dog_data"):
                    dog_data = coordinator.get_dog_data(self._dog)
                    if dog_data:
                        keys = path.split(".")
                        data = dog_data
                        try:
                            for key in keys:
                                data = data.get(key, {})
                                if not isinstance(data, dict):
                                    return data if data is not None else default
                        except (AttributeError, TypeError):
                            return default
        return default

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        value = self._get_coordinator_data(
            self._config.data_path, self._config.default_value
        )

        if self._config.transform_func and value is not None:
            try:
                return self._config.transform_func(value)
            except (ValueError, TypeError):
                return self._config.default_value

        return value


def create_sensor_configs() -> Dict[str, SensorConfig]:
    """Create all sensor configurations."""
    return {
        # Walk sensors
        "walk_distance_current": SensorConfig(
            key="walk_distance_current",
            name="Walk Distance Current",
            data_path="walk.walk_distance_m",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit="m",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1),
        ),
        "walk_distance_last": SensorConfig(
            key="walk_distance_last",
            name="Walk Distance Last",
            data_path="walk.walk_distance_m",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit="m",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1),
        ),
        "walk_duration_last": SensorConfig(
            key="walk_duration_last",
            name="Walk Duration Last",
            data_path="walk.walk_duration_min",
            state_class=SensorStateClass.MEASUREMENT,
            unit="min",
            default_value=0,
            transform_func=lambda x: int(float(x)),
        ),
        "walk_distance_today": SensorConfig(
            key="walk_distance_today",
            name="Walk Distance Today",
            data_path="walk.total_distance_today",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.TOTAL,
            unit="m",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1),
        ),
        # Health sensors
        "last_action": SensorConfig(
            key="last_action",
            name="Last Action",
            data_path="statistics.last_action",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        "last_feeding": SensorConfig(
            key="last_feeding",
            name="Last Feeding",
            data_path="feeding.last_feeding",
            device_class=SensorDeviceClass.TIMESTAMP,
        ),
        "poop_count_today": SensorConfig(
            key="poop_count_today",
            name="Poop Count Today",
            data_path="statistics.poop_count_today",
            state_class=SensorStateClass.TOTAL,
            default_value=0,
            transform_func=lambda x: int(float(x)),
        ),
        "weight": SensorConfig(
            key="weight",
            name="Weight",
            data_path="health.weight_kg",
            device_class=SensorDeviceClass.WEIGHT,
            state_class=SensorStateClass.MEASUREMENT,
            unit="kg",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1),
        ),
        "activity_level": SensorConfig(
            key="activity_level",
            name="Activity Level",
            data_path="activity.activity_level",
            options=["low", "medium", "high"],
            default_value="medium",
        ),
        "calories_burned_today": SensorConfig(
            key="calories_burned_today",
            name="Calories Burned Today",
            data_path="activity.calories_burned_today",
            state_class=SensorStateClass.TOTAL,
            unit="kcal",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1),
        ),
        # GPS Diagnostic sensors
        "gps_points_total": SensorConfig(
            key="gps_points_total",
            name="GPS Points Total",
            data_path="gps.points_total",
            entity_category="diagnostic",
            state_class=SensorStateClass.TOTAL,
            default_value=0,
            transform_func=lambda x: int(float(x)),
        ),
        "gps_accuracy_avg": SensorConfig(
            key="gps_accuracy_avg",
            name="GPS Accuracy Average",
            data_path="gps.accuracy_avg",
            entity_category="diagnostic",
            device_class=SensorDeviceClass.DISTANCE,
            state_class=SensorStateClass.MEASUREMENT,
            unit="m",
            transform_func=lambda x: round(float(x), 1) if x is not None else None,
        ),
    }


def create_dog_sensors(
    hass: HomeAssistant, dog_id: str, title: str
) -> list[ConfigurableDogSensor]:
    """Create all sensors for a dog using factory pattern."""
    configs = create_sensor_configs()
    return [
        ConfigurableDogSensor(hass, dog_id, title, config)
        for config in configs.values()
    ]

    def _apply_classes_from_key(self, key: str):
        if "battery" in key:
            self._attr_device_class = "battery"
            self._attr_state_class = "measurement"
            self._attr_native_unit_of_measurement = "%"
        elif any(k in key for k in ["distance", "meters", "km"]):
            self._attr_device_class = "distance"
            self._attr_state_class = "measurement"
        elif any(k in key for k in ["duration", "time", "seconds", "minutes", "hours"]):
            self._attr_device_class = None
            self._attr_state_class = "measurement"
        elif any(k in key for k in ["speed", "pace"]):
            self._attr_device_class = "speed"
            self._attr_state_class = "measurement"


CLASS_MAP = {
    "battery_level": {
        "device_class": "battery",
        "state_class": "measurement",
        "unit": "%",
    },
    "distance_m": {
        "device_class": "distance",
        "state_class": "measurement",
        "unit": "m",
    },
    "distance_km": {
        "device_class": "distance",
        "state_class": "measurement",
        "unit": "km",
    },
    "speed_m_s": {"device_class": "speed", "state_class": "measurement", "unit": "m/s"},
    "speed_km_h": {
        "device_class": "speed",
        "state_class": "measurement",
        "unit": "km/h",
    },
    "duration_s": {"device_class": None, "state_class": "measurement", "unit": "s"},
    "duration_min": {"device_class": None, "state_class": "measurement", "unit": "min"},
    "steps": {"device_class": None, "state_class": "total_increasing", "unit": None},
    "calories": {"device_class": None, "state_class": "measurement", "unit": "kcal"},
    "temperature_c": {
        "device_class": "temperature",
        "state_class": "measurement",
        "unit": "°C",
    },

        ,
        "safe_inside": SensorConfig(
            key="safe_inside",
            name="Safe Zone Inside",
            data_path="safe_zone.inside",
            device_class=None,
            state_class=SensorStateClass.MEASUREMENT,
            unit=None,
            default_value=0,
            transform_func=lambda x: 1 if x is True else 0 if x is False else None,
        ),
        "safe_enters": SensorConfig(
            key="safe_enters",
            name="Safe Zone Enters Today",
            data_path="safe_zone.enters",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit=None,
            default_value=0,
        ),
        "safe_leaves": SensorConfig(
            key="safe_leaves",
            name="Safe Zone Leaves Today",
            data_path="safe_zone.leaves",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit=None,
            default_value=0,
        ),
        "safe_time_today_min": SensorConfig(
            key="safe_time_today_min",
            name="Safe Zone Time Today",
            data_path="safe_zone.time_today_s",
            device_class=None,
            state_class=SensorStateClass.MEASUREMENT,
            unit="min",
            default_value=0.0,
            transform_func=lambda s: round(float(s)/60.0, 1) if s is not None else None,
        )

        ,
        "geofence_enters_today": SensorConfig(
            key="geofence_enters_today",
            name="Geofence Enters Today",
            data_path="location.enters_today",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit=None,
            default_value=0,
            transform_func=lambda x: int(x) if x is not None else 0,
        ),
        "geofence_leaves_today": SensorConfig(
            key="geofence_leaves_today",
            name="Geofence Leaves Today",
            data_path="location.leaves_today",
            device_class=None,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit=None,
            default_value=0,
            transform_func=lambda x: int(x) if x is not None else 0,
        ),
        "geofence_time_inside_today_min": SensorConfig(
            key="geofence_time_inside_today_min",
            name="Geofence Time Inside Today",
            data_path="location.time_inside_today_min",
            device_class=SensorDeviceClass.DURATION,
            state_class=SensorStateClass.TOTAL_INCREASING,
            unit="min",
            default_value=0.0,
            transform_func=lambda x: round(float(x), 1) if x is not None else 0.0,
        )
        }


def _apply_class_map(self, key: str):
    meta = CLASS_MAP.get(key)
    if not meta:
        return
    self._attr_device_class = meta.get("device_class")
    self._attr_state_class = meta.get("state_class")
    unit = meta.get("unit")
    if unit is not None:
        self._attr_native_unit_of_measurement = unit
