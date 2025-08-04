"""Configuration helpers for Paw Control."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_GPS_ENABLE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_HEALTH_MODULE,
    CONF_WALK_MODULE,
    CONF_CREATE_DASHBOARD,
    ALL_MODULE_FLAGS,
)
from .helpers.config import ConfigHelper

def build_module_schema(defaults: dict | None = None) -> dict:
    """Build the module configuration schema."""
    if defaults is None:
        defaults = {}
    
    return {
        vol.Optional(CONF_GPS_ENABLE, default=defaults.get(CONF_GPS_ENABLE, True)): bool,
        vol.Optional(CONF_NOTIFICATIONS_ENABLED, default=defaults.get(CONF_NOTIFICATIONS_ENABLED, True)): bool,
        vol.Optional(CONF_HEALTH_MODULE, default=defaults.get(CONF_HEALTH_MODULE, True)): bool,
        vol.Optional(CONF_WALK_MODULE, default=defaults.get(CONF_WALK_MODULE, True)): bool,
        vol.Optional(CONF_CREATE_DASHBOARD, default=defaults.get(CONF_CREATE_DASHBOARD, True)): bool,
    }

async def get_all_configured_dogs(hass: HomeAssistant) -> list[dict]:
    """Get all configured dogs from config entries."""
    dogs = []
    
    for entry in hass.config_entries.async_entries("pawcontrol"):
        # Verwende ConfigHelper für erweiterte Konfiguration
        config_helper = ConfigHelper(hass, entry)
        dog_config = await config_helper.get_full_config()
        dogs.append(dog_config)
    
    return dogs
