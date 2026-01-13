"""Schemas and constants used by the PawControl config flow."""

from __future__ import annotations

from typing import Final

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_MODULES,
    DOG_SIZES,
    MAX_DOG_AGE,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)

# Pre-compiled validation sets for O(1) lookups
VALID_DOG_SIZES: frozenset[str] = frozenset(DOG_SIZES)

# Optimized schema definitions using constants from const.py
DOG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required(CONF_DOG_NAME): cv.string,
        vol.Optional(CONF_DOG_BREED, default=""): cv.string,
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE)
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT)
        ),
        vol.Optional(CONF_DOG_SIZE, default="medium"): vol.In(VALID_DOG_SIZES),
        vol.Optional(CONF_MODULES, default={}): dict,
    }
)

MODULE_SELECTION_KEYS: Final[tuple[str, ...]] = (
    MODULE_FEEDING,
    MODULE_WALK,
    MODULE_HEALTH,
    MODULE_GPS,
    MODULE_NOTIFICATIONS,
)

MODULES_SCHEMA = vol.Schema(
    {
        vol.Optional(MODULE_FEEDING, default=True): cv.boolean,
        vol.Optional(MODULE_WALK, default=True): cv.boolean,
        vol.Optional(MODULE_HEALTH, default=True): cv.boolean,
        vol.Optional(MODULE_GPS, default=False): cv.boolean,
        vol.Optional(MODULE_NOTIFICATIONS, default=True): cv.boolean,
    }
)
