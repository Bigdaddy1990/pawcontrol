"""Number platform for Paw Control integration."""
from __future__ import annotations

import logging
from homeassistant.components.number import NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import PawControlCoordinator
from .entities import PawControlNumberEntity
from .helpers.entity import get_icon

_LOGGER = logging.getLogger(__name__)


NUMBER_ENTITIES: list[dict] = [
    {
        "key": "weight",
        "unit": "kg",
        "device_class": NumberDeviceClass.WEIGHT,
        "min_value": 0.5,
        "max_value": 100.0,
        "step": 0.1,
        "mode": "slider",
    },
    {
        "key": "age_years",
        "icon": "mdi:calendar",
        "unit": "Jahre",
        "min_value": 0,
        "max_value": 25,
        "step": 0.1,
        "mode": "slider",
    },
    {
        "key": "temperature",
        "device_class": NumberDeviceClass.TEMPERATURE,
        "unit": "°C",
        "min_value": 35.0,
        "max_value": 42.0,
        "step": 0.1,
        "mode": "slider",
    },
    {
        "key": "daily_food_amount",
        "icon": get_icon("food"),
        "unit": "g",
        "min_value": 0,
        "max_value": 2000,
        "step": 10,
        "mode": "slider",
    },
    {
        "key": "daily_walk_duration",
        "icon": get_icon("walk"),
        "device_class": NumberDeviceClass.DURATION,
        "unit": "min",
        "min_value": 0,
        "max_value": 480,
        "step": 5,
        "mode": "slider",
    },
    {
        "key": "daily_play_duration",
        "icon": get_icon("play"),
        "device_class": NumberDeviceClass.DURATION,
        "unit": "min",
        "min_value": 0,
        "max_value": 240,
        "step": 5,
        "mode": "slider",
    },
    {
        "key": "gps_signal_strength",
        "icon": get_icon("signal"),
        "device_class": NumberDeviceClass.SIGNAL_STRENGTH,
        "unit": "%",
        "min_value": 0,
        "max_value": 100,
    },
    {
        "key": "gps_battery_level",
        "icon": get_icon("battery"),
        "unit": "%",
        "min_value": 0,
        "max_value": 100,
    },
    {
        "key": "home_distance",
        "icon": get_icon("home"),
        "unit": "m",
        "min_value": 0,
        "max_value": 10000,
    },
    {
        "key": "geofence_radius",
        "icon": get_icon("home"),
        "unit": "m",
        "min_value": 10,
        "max_value": 10000,
    },
    {
        "key": "current_walk_distance",
        "icon": get_icon("walk"),
        "unit": "m",
        "min_value": 0,
        "max_value": 100000,
    },
    {
        "key": "current_walk_duration",
        "icon": get_icon("walk"),
        "device_class": NumberDeviceClass.DURATION,
        "unit": "min",
        "min_value": 0,
        "max_value": 1440,
    },
    {
        "key": "current_walk_speed",
        "icon": get_icon("walk"),
        "unit": "km/h",
        "min_value": 0,
        "max_value": 50,
        "step": 0.1,
    },
    {
        "key": "walk_distance_today",
        "icon": get_icon("walk"),
        "unit": "km",
        "min_value": 0,
        "max_value": 100,
    },
    {
        "key": "walk_distance_weekly",
        "icon": get_icon("walk"),
        "unit": "km",
        "min_value": 0,
        "max_value": 1000,
    },
    {
        "key": "calories_burned_walk",
        "icon": get_icon("statistics"),
        "unit": "kcal",
        "min_value": 0,
        "max_value": 5000,
    },
    {
        "key": "health_score",
        "icon": get_icon("health"),
        "unit": "%",
        "min_value": 0,
        "max_value": 100,
    },
    {
        "key": "happiness_score",
        "icon": get_icon("status"),
        "unit": "%",
        "min_value": 0,
        "max_value": 100,
    },
    {
        "key": "activity_score",
        "icon": get_icon("statistics"),
        "unit": "%",
        "min_value": 0,
        "max_value": 100,
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the number platform."""
    coordinator: PawControlCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name

    entities = [
        PawControlNumberEntity(coordinator, dog_name=dog_name, **cfg)
        for cfg in NUMBER_ENTITIES
    ]

    async_add_entities(entities)

