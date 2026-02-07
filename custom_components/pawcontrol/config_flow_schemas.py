"""Schemas and constants used by the PawControl config flow."""

from __future__ import annotations

from typing import Final

import voluptuous as vol

from .const import (
  CONF_DOG_AGE,
  CONF_DOG_BREED,
  CONF_DOG_ID,
  CONF_DOG_NAME,
  CONF_DOG_SIZE,
  CONF_DOG_WEIGHT,
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
from .selector_shim import selector

# Optimized schema definitions using constants from const.py
DOG_SCHEMA = vol.Schema(
  {
    vol.Required(CONF_DOG_ID): selector.TextSelector(
      selector.TextSelectorConfig(
        type=selector.TextSelectorType.TEXT,
        autocomplete="off",
      ),
    ),
    vol.Required(CONF_DOG_NAME): selector.TextSelector(
      selector.TextSelectorConfig(
        type=selector.TextSelectorType.TEXT,
        autocomplete="name",
      ),
    ),
    vol.Optional(CONF_DOG_BREED, default=""): selector.TextSelector(
      selector.TextSelectorConfig(
        type=selector.TextSelectorType.TEXT,
        autocomplete="off",
      ),
    ),
    vol.Optional(CONF_DOG_AGE, default=3): selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=MIN_DOG_AGE,
        max=MAX_DOG_AGE,
        step=1,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="years",
      ),
    ),
    vol.Optional(CONF_DOG_WEIGHT, default=20.0): selector.NumberSelector(
      selector.NumberSelectorConfig(
        min=MIN_DOG_WEIGHT,
        max=MAX_DOG_WEIGHT,
        step=0.1,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="kg",
      ),
    ),
    vol.Optional(CONF_DOG_SIZE, default="medium"): selector.SelectSelector(
      selector.SelectSelectorConfig(
        options=list(DOG_SIZES),
        mode=selector.SelectSelectorMode.DROPDOWN,
        translation_key="dog_size",
      ),
    ),
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
    vol.Optional(MODULE_FEEDING, default=True): selector.BooleanSelector(),
    vol.Optional(MODULE_WALK, default=True): selector.BooleanSelector(),
    vol.Optional(MODULE_HEALTH, default=True): selector.BooleanSelector(),
    vol.Optional(MODULE_GPS, default=False): selector.BooleanSelector(),
    vol.Optional(MODULE_NOTIFICATIONS, default=True): selector.BooleanSelector(),
  },
)
