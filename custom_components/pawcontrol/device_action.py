from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.config_validation import DEVICE_ACTION_BASE_SCHEMA
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_POST_LOCATION,
    SERVICE_GPS_START_WALK,
    SERVICE_TOGGLE_GEOFENCE_ALERTS,
)

SIMPLE_ACTION_SERVICES = {
    "start_walk": SERVICE_GPS_START_WALK,
    "end_walk": SERVICE_GPS_END_WALK,
}

ACTION_TYPES = {
    "post_location",
    *SIMPLE_ACTION_SERVICES,
    "toggle_geofence_alerts",
}

ACTION_SCHEMA = DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
        vol.Optional("enabled"): bool,
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional("accuracy_m"): vol.Coerce(float),
        vol.Optional("speed_m_s"): vol.Coerce(float),
        vol.Optional("timestamp"): str,
    }
)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    return [
        {CONF_DOMAIN: DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: t}
        for t in ACTION_TYPES
    ]


def _dog_id_from_device_id(hass: HomeAssistant, device_id: str | None) -> str | None:
    if not device_id:
        return None
    if dev := dr.async_get(hass).async_get(device_id):
        return next(
            (identifier for domain, identifier in dev.identifiers if domain == DOMAIN),
            None,
        )
    return None


async def async_call_action_from_config(
    hass: HomeAssistant, config: ConfigType, variables: dict[str, Any], context: Any
) -> None:
    if "type" not in config or "device_id" not in config:
        raise InvalidDeviceAutomationConfig("Missing required keys")

    action_type: str = config[CONF_TYPE]
    device_id: str = config[CONF_DEVICE_ID]
    dog_id = _dog_id_from_device_id(hass, device_id)
    if not dog_id:
        raise InvalidDeviceAutomationConfig("Device has no Paw Control dog identifier")

    if action_type in SIMPLE_ACTION_SERVICES:
        await hass.services.async_call(
            DOMAIN,
            SIMPLE_ACTION_SERVICES[action_type],
            {"dog_id": dog_id},
            blocking=True,
            context=context,
        )
        return
    if action_type == "toggle_geofence_alerts":
        enabled = bool(config.get("enabled", True))
        await hass.services.async_call(
            DOMAIN,
            SERVICE_TOGGLE_GEOFENCE_ALERTS,
            {"dog_id": dog_id, "enabled": enabled},
            blocking=True,
            context=context,
        )
        return

    if action_type == "post_location":
        if "latitude" not in config or "longitude" not in config:
            raise InvalidDeviceAutomationConfig("Missing required coordinates")
        data: dict[str, Any] = {
            "dog_id": dog_id,
            "latitude": config["latitude"],
            "longitude": config["longitude"],
        }
        if "accuracy_m" in config:
            data["accuracy_m"] = config["accuracy_m"]
        if "speed_m_s" in config:
            data["speed_m_s"] = config["speed_m_s"]
        if "timestamp" in config:
            data["timestamp"] = config["timestamp"]
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GPS_POST_LOCATION,
            data,
            blocking=True,
            context=context,
        )
        return

    raise InvalidDeviceAutomationConfig(f"Unsupported action type: {action_type}")
