"""Device triggers and actions for Paw Control integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from .compat import CONF_DEVICE_ID, CONF_PLATFORM, CONF_DOMAIN, CONF_TYPE
from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
try:  # pragma: no cover - Home Assistant provides the event trigger module
    from homeassistant.components.homeassistant.triggers import event as event_trigger
except Exception:  # pragma: no cover - minimal fallback for tests

    class event_trigger:  # type: ignore[too-few-public-methods]
        CONF_PLATFORM = "platform"
        CONF_EVENT_TYPE = "event_type"
        CONF_EVENT_DATA = "event_data"

        @staticmethod
        def TRIGGER_SCHEMA(cfg):  # type: ignore[return-type]
            return cfg

        @staticmethod
        async def async_attach_trigger(hass, config, action, trigger_info, *, platform_type="event"):
            return lambda: None
try:  # pragma: no cover - Home Assistant provides these
    from homeassistant.core import CALLBACK_TYPE, HomeAssistant
except Exception:  # pragma: no cover - minimal stubs for tests
    from collections.abc import Callable as CALLBACK_TYPE  # type: ignore[assignment]

    class HomeAssistant:  # type: ignore[too-few-public-methods]
        pass

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
from .const import (
    DOMAIN,
    EVENT_DOG_FED,
    EVENT_GROOMING_DONE,
    EVENT_MEDICATION_GIVEN,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)

TRIGGER_TYPES = {
    "walk_started",
    "walk_ended",
    "dog_fed",
    "medication_given",
    "grooming_done",
    "gps_location_posted",
    "geofence_alert",
    "needs_walk",
    "is_hungry",
    "needs_grooming",
}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for Paw Control devices."""
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

    triggers = []

    # Get dog_id from device identifiers
    dog_id = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            dog_id = identifier[1]
            break

    if not dog_id or dog_id == "global":
        return []

    # Add all trigger types for this dog
    for trigger_type in TRIGGER_TYPES:
        triggers.append(
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: trigger_type,
                "metadata": {"secondary": False},
            }
        )

    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: CALLBACK_TYPE,
    trigger_info: dict[str, Any],
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    trigger_type = config[CONF_TYPE]
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

    # Map trigger types to events
    event_map = {
        "walk_started": EVENT_WALK_STARTED,
        "walk_ended": EVENT_WALK_ENDED,
        "dog_fed": EVENT_DOG_FED,
        "medication_given": EVENT_MEDICATION_GIVEN,
        "grooming_done": EVENT_GROOMING_DONE,
        "gps_location_posted": f"{DOMAIN}_gps_location_posted",
        "geofence_alert": f"{DOMAIN}_geofence_alert",
    }

    if trigger_type in event_map:
        # Event-based trigger
        event_config = {
            **event_trigger.TRIGGER_SCHEMA(
                {
                    event_trigger.CONF_PLATFORM: "event",
                    event_trigger.CONF_EVENT_TYPE: event_map[trigger_type],
                    event_trigger.CONF_EVENT_DATA: {"device_id": device_id},
                }
            ),
        }
        trig_info = {
            **trigger_info,
            "trigger_data": trigger_info.get("trigger_data", {}),
            "variables": trigger_info.get("variables", {}),
        }
        return await event_trigger.async_attach_trigger(
            hass, event_config, action, trig_info, platform_type="device"
        )

    # State-based triggers
    if trigger_type == "needs_walk":
        state_config = {
            "platform": "state",
            "entity_id": f"binary_sensor.{DOMAIN}_{dog_id}_needs_walk",
            "to": "on",
        }
    elif trigger_type == "is_hungry":
        state_config = {
            "platform": "state",
            "entity_id": f"binary_sensor.{DOMAIN}_{dog_id}_is_hungry",
            "to": "on",
        }
    elif trigger_type == "needs_grooming":
        state_config = {
            "platform": "state",
            "entity_id": f"binary_sensor.{DOMAIN}_{dog_id}_needs_grooming",
            "to": "on",
        }
    else:
        raise ValueError(f"Unknown trigger type: {trigger_type}")

    # Import state trigger
    from homeassistant.components.homeassistant.triggers import state as state_trigger

    state_config = state_trigger.TRIGGER_SCHEMA(state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List trigger capabilities."""
    return {}
