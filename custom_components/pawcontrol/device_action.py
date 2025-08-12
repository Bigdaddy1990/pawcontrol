"""Device actions for Paw Control integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_ACTION_BASE_SCHEMA
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_TYPE,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

from .const import (
    DOMAIN,
    SERVICE_GPS_START_WALK,
    SERVICE_GPS_END_WALK,
    SERVICE_SEND_MEDICATION_REMINDER,
    SERVICE_NOTIFY_TEST,
)

ACTION_TYPES = {
    "start_walk",
    "end_walk",
    "give_medication",
    "test_notification",
}

ACTION_SCHEMA = DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
    }
)


async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device actions for Paw Control devices."""
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)

    if not device:
        return []

    # Check if this is a Paw Control device
    domain_in_identifiers = any(
        identifier[0] == DOMAIN for identifier in device.identifiers
    )

    if not domain_in_identifiers:
        return []

    actions = []

    # Get dog_id from device identifiers
    dog_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            dog_id = identifier[1]
            break

    if not dog_id or dog_id == "global":
        return []

    # Add all action types for this dog
    for action_type in ACTION_TYPES:
        actions.append(
            {
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: action_type,
            }
        )

    return actions


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    action_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]

    # Get dog_id from device
    registry = dr.async_get(hass)
    device = registry.async_get(device_id)

    if not device:
        raise ValueError(f"Device {device_id} not found")

    dog_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            dog_id = identifier[1]
            break

    if not dog_id:
        raise ValueError(f"Dog ID not found for device {device_id}")

    # Map action types to service calls using existing services
    if action_type == "start_walk":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GPS_START_WALK,
            {"dog_id": dog_id, "walk_type": "automation"},
            blocking=True,
            context=context,
        )
    elif action_type == "end_walk":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_GPS_END_WALK,
            {"dog_id": dog_id, "notes": "Beendet durch Automation"},
            blocking=True,
            context=context,
        )
    elif action_type == "give_medication":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SEND_MEDICATION_REMINDER,
            {
                "dog_id": dog_id,
                "notes": "Erinnerung durch Automation"
            },
            blocking=True,
            context=context,
        )
    elif action_type == "test_notification":
        await hass.services.async_call(
            DOMAIN,
            SERVICE_NOTIFY_TEST,
            {},
            blocking=True,
            context=context,
        )
    else:
        raise ValueError(f"Unknown action type: {action_type}")


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return {}
