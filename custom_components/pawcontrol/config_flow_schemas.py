"""Schemas and constants used by the PawControl config flow."""
from __future__ import annotations

from typing import Final

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import CONF_DOG_AGE
from .const import CONF_DOG_BREED
from .const import CONF_DOG_ID
from .const import CONF_DOG_NAME
from .const import CONF_DOG_SIZE
from .const import CONF_DOG_WEIGHT
from .const import CONF_MODULES
from .const import DOG_SIZES
from .const import MAX_DOG_AGE
from .const import MAX_DOG_WEIGHT
from .const import MIN_DOG_AGE
from .const import MIN_DOG_WEIGHT
from .const import MODULE_FEEDING
from .const import MODULE_GPS
from .const import MODULE_HEALTH
from .const import MODULE_NOTIFICATIONS
from .const import MODULE_WALK

# Pre-compiled validation sets for O(1) lookups
VALID_DOG_SIZES: frozenset[str] = frozenset(DOG_SIZES)

# Optimized schema definitions using constants from const.py
DOG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required(CONF_DOG_NAME): cv.string,
        vol.Optional(CONF_DOG_BREED, default=''): cv.string,
        vol.Optional(CONF_DOG_AGE, default=3): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_DOG_AGE, max=MAX_DOG_AGE),
        ),
        vol.Optional(CONF_DOG_WEIGHT, default=20.0): vol.All(
            vol.Coerce(float), vol.Range(
                min=MIN_DOG_WEIGHT, max=MAX_DOG_WEIGHT,
            ),
        ),
        vol.Optional(CONF_DOG_SIZE, default='medium'): vol.In(VALID_DOG_SIZES),
        vol.Optional(CONF_MODULES, default={}): dict,
    },
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
    },
)
