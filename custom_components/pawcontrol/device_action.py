"""Device actions for PawControl."""

from dataclasses import dataclass
import logging
from typing import Final, cast

from homeassistant.components.device_automation import DEVICE_ACTION_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_METADATA, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
from .device_automation_helpers import (
    build_device_automation_metadata,
    resolve_device_context,
)
from .types import DeviceActionPayload

_LOGGER = logging.getLogger(__name__)

CONF_AMOUNT = "amount"
CONF_MEAL_TYPE = "meal_type"
CONF_NOTES = "notes"
CONF_SCHEDULED = "scheduled"
CONF_WALK_TYPE = "walk_type"
CONF_WALK_NOTES = "walk_notes"
CONF_SAVE_ROUTE = "save_route"


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Definition for a device action."""  # noqa: E111

    type: str  # noqa: E111


ACTION_DEFINITIONS: Final[tuple[ActionDefinition, ...]] = (
    ActionDefinition("log_feeding"),
    ActionDefinition("start_walk"),
    ActionDefinition("end_walk"),
)

ACTION_SCHEMA = DEVICE_ACTION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In({
            definition.type for definition in ACTION_DEFINITIONS
        }),
        vol.Optional(CONF_AMOUNT): vol.Coerce(float),
        vol.Optional(CONF_MEAL_TYPE): cv.string,
        vol.Optional(CONF_NOTES): cv.string,
        vol.Optional(CONF_SCHEDULED): cv.boolean,
        vol.Optional(CONF_WALK_TYPE): cv.string,
        vol.Optional(CONF_WALK_NOTES): cv.string,
        vol.Optional(CONF_SAVE_ROUTE): cv.boolean,
    },
)


async def async_get_actions(
    hass: HomeAssistant,
    device_id: str,
) -> list[DeviceActionPayload]:
    """List device actions for PawControl devices."""  # noqa: E111

    context = resolve_device_context(hass, device_id)  # noqa: E111
    if context.dog_id is None:  # noqa: E111
        return []

    return [  # noqa: E111
        {
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_METADATA: build_device_automation_metadata(),
            CONF_TYPE: definition.type,
        }
        for definition in ACTION_DEFINITIONS
    ]


async def async_get_action_capabilities(
    hass: HomeAssistant,
    config: dict[str, str],
) -> dict[str, vol.Schema]:
    """Return action capability schemas."""  # noqa: E111

    action_type = config.get(CONF_TYPE)  # noqa: E111
    if action_type == "log_feeding":  # noqa: E111
        return {
            "fields": vol.Schema(
                {
                    vol.Required(CONF_AMOUNT): vol.Coerce(float),
                    vol.Optional(CONF_MEAL_TYPE): cv.string,
                    vol.Optional(CONF_NOTES): cv.string,
                    vol.Optional(CONF_SCHEDULED): cv.boolean,
                },
            ),
        }

    if action_type == "start_walk":  # noqa: E111
        return {
            "fields": vol.Schema(
                {
                    vol.Optional(CONF_WALK_TYPE): cv.string,
                },
            ),
        }

    if action_type == "end_walk":  # noqa: E111
        return {
            "fields": vol.Schema(
                {
                    vol.Optional(CONF_WALK_NOTES): cv.string,
                    vol.Optional(CONF_SAVE_ROUTE): cv.boolean,
                },
            ),
        }

    return {}  # noqa: E111


async def async_call_action(
    hass: HomeAssistant,
    config: dict[str, str],
    variables: dict[str, object],
    context: object | None = None,
) -> None:
    """Execute a PawControl device action."""  # noqa: E111

    validated = ACTION_SCHEMA(config)  # noqa: E111
    context_data = resolve_device_context(hass, validated[CONF_DEVICE_ID])  # noqa: E111

    dog_id = context_data.dog_id  # noqa: E111
    runtime_data = context_data.runtime_data  # noqa: E111

    if dog_id is None or runtime_data is None:  # noqa: E111
        raise HomeAssistantError("PawControl device runtime data not available")

    action_type = validated[CONF_TYPE]  # noqa: E111

    if action_type == "log_feeding":  # noqa: E111
        amount = validated.get(CONF_AMOUNT)
        if amount is None:
            raise HomeAssistantError("Feeding amount is required for log_feeding")  # noqa: E111

        await runtime_data.feeding_manager.async_add_feeding(
            dog_id,
            cast(float, amount),
            meal_type=validated.get(CONF_MEAL_TYPE),
            notes=validated.get(CONF_NOTES),
            scheduled=validated.get(CONF_SCHEDULED, False),
        )
        return

    if action_type == "start_walk":  # noqa: E111
        await runtime_data.walk_manager.async_start_walk(
            dog_id,
            validated.get(CONF_WALK_TYPE, "manual"),
        )
        return

    if action_type == "end_walk":  # noqa: E111
        await runtime_data.walk_manager.async_end_walk(
            dog_id,
            notes=validated.get(CONF_WALK_NOTES),
            save_route=validated.get(CONF_SAVE_ROUTE, True),
        )
        return

    _LOGGER.debug("Unhandled PawControl device action: %s", action_type)  # noqa: E111
