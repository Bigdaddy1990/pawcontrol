from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, condition
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.config_validation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE

from .const import DOMAIN

CONDITION_TYPES = {"is_home", "in_geofence"}

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(CONDITION_TYPES),
    }
)

async def async_get_conditions(hass: HomeAssistant, device_id: str) -> list[dict[str, Any]]:
    """List device conditions for a device."""
    return [
        {CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: c}
        for c in CONDITION_TYPES
    ]

def _dog_id_from_device_id(hass: HomeAssistant, device_id: str | None) -> str | None:
    if not device_id:
        return None
    dev_reg = dr.async_get(hass)
    dev = dev_reg.async_get(device_id)
    if not dev or not dev.identifiers:
        return None
    for idt in dev.identifiers:
        if idt[0] == DOMAIN:
            return idt[1]
    return None

def _get_coordinator(hass: HomeAssistant, dog_id: str | None):
    data = hass.data.get(DOMAIN) or {}
    for entry_id, st in data.items():
        coord = st.get("coordinator")
        if coord and getattr(coord, "_dog_data", {}).get(dog_id) is not None:
            return coord
    return None

@callback
def async_condition_from_config(config: ConfigType, config_validation: bool):
    """Create a function to test a device condition."""
    if config_validation:
        config = CONDITION_SCHEMA(config)

    cond_type: str = config[CONF_TYPE]
    device_id: str = config[CONF_DEVICE_ID]

    async def _check(hass: HomeAssistant, variables: dict[str, Any]) -> bool:
        dog_id = _dog_id_from_device_id(hass, device_id)
        if not dog_id:
            return False
        coord = _get_coordinator(hass, dog_id)
        if not coord:
            return False
        dog = coord._dog_data.get(dog_id) or {}
        loc = dog.get("location") or {}
        is_home = bool(loc.get("is_home", False))
        if cond_type == "is_home":
            return is_home
        if cond_type == "in_geofence":
            return is_home
        return False

    return _check
