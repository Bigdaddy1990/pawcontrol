"""Device conditions for the Paw Control integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.config_validation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.helpers.typing import ConfigType

from .compat import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from .const import DOMAIN

CONDITION_TYPES = {"is_home", "in_geofence"}

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(CONDITION_TYPES),
    }
)


async def async_get_conditions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device conditions for a device."""
    return [
        {CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: c}
        for c in CONDITION_TYPES
    ]


def _dog_id_from_device_id(hass: HomeAssistant, device_id: str | None) -> str | None:
    """Return the Paw Control dog identifier for a device."""
    if not device_id:
        return None
    if dev := dr.async_get(hass).async_get(device_id):
        return next(
            (identifier for domain, identifier in dev.identifiers if domain == DOMAIN),
            None,
        )
    return None


def _get_coordinator(hass: HomeAssistant, dog_id: str | None):
    """Retrieve the coordinator containing data for the given dog."""
    if not dog_id:
        return None

    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(getattr(entry, "runtime_data", None), "coordinator", None)
        if coordinator and dog_id in getattr(coordinator, "_dog_data", {}):
            return coordinator

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

        coordinator = _get_coordinator(hass, dog_id)
        if not coordinator:
            return False

        dog = coordinator._dog_data.get(dog_id, {})
        loc = dog.get("location", {})
        is_home = bool(loc.get("is_home"))

        return {"is_home": is_home, "in_geofence": is_home}.get(cond_type, False)

    return _check
