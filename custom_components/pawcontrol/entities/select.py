"""Select platform for Paw Control integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    HEALTH_STATUS_OPTIONS,
    MOOD_OPTIONS,
    ENERGY_LEVEL_OPTIONS,
    ACTIVITY_LEVELS,
    SIZE_CATEGORIES,
    EMERGENCY_LEVELS,
    WALK_TYPES,
)
from .coordinator import PawControlCoordinator
from .entities import PawControlSelectEntity
from .helpers.entity import get_icon

_LOGGER = logging.getLogger(__name__)


SELECT_ENTITIES: list[dict] = [
    {"key": "health_status", "options": HEALTH_STATUS_OPTIONS, "icon": get_icon("health")},
    {"key": "mood", "options": MOOD_OPTIONS, "icon": get_icon("mood")},
    {"key": "energy_level", "options": ENERGY_LEVEL_OPTIONS, "icon": "mdi:battery"},
    {
        "key": "appetite_level",
        "options": [
            "Kein Appetit",
            "Wenig Appetit",
            "Normal",
            "Guter Appetit",
            "Sehr guter Appetit",
        ],
        "icon": get_icon("food"),
    },
    {"key": "activity_level", "options": ACTIVITY_LEVELS, "icon": get_icon("walk")},
    {"key": "preferred_walk_type", "options": WALK_TYPES, "icon": get_icon("walk")},
    {"key": "size_category", "options": SIZE_CATEGORIES, "icon": get_icon("weight")},
    {"key": "emergency_level", "options": EMERGENCY_LEVELS, "icon": get_icon("emergency")},
    {
        "key": "gps_source_type",
        "options": [
            "Manual",
            "Smartphone",
            "Device Tracker",
            "Person Entity",
            "Tractive",
            "Webhook",
            "MQTT",
        ],
        "icon": get_icon("gps"),
    },
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    coordinator: PawControlCoordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
    dog_name = coordinator.dog_name

    entities = [
        PawControlSelectEntity(coordinator, dog_name=dog_name, **cfg)
        for cfg in SELECT_ENTITIES
    ]

    async_add_entities(entities)

