"""Device conditions for PawControl."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Final, cast

from homeassistant.components.device_automation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.const import (
    CONF_CONDITION,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_METADATA,
    CONF_TYPE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

# ``ConditionCheckerType`` is only used for typing. Some Home Assistant test harness
# builds do not ship the helpers module that defines it, so we avoid importing it at
# runtime and provide a safe fallback.
if TYPE_CHECKING:  # pragma: no cover
    try:  # noqa: E111
        from homeassistant.helpers.condition import ConditionCheckerType
    except ImportError:  # noqa: E111
        try:
            from homeassistant.helpers.typing import ConditionCheckerType  # noqa: E111
        except ImportError:
            ConditionCheckerType = Callable[..., bool]  # noqa: E111
else:
    ConditionCheckerType = Callable[..., bool]  # type: ignore[assignment]  # noqa: E111

import voluptuous as vol

from .const import DOMAIN
from .device_automation_helpers import (
    build_device_automation_metadata,
    build_unique_id,
    resolve_device_context,
    resolve_entity_id,
    resolve_status_snapshot,
)
from .types import DeviceConditionPayload

_LOGGER = logging.getLogger(__name__)

_ENTITY_ID_VALIDATOR = cast(vol.Any, getattr(cv, "entity_id", cv.string))

CONF_STATUS = "status"


@dataclass(frozen=True, slots=True)
class ConditionDefinition:
    """Definition for a device condition."""  # noqa: E111

    type: str  # noqa: E111
    platform: str  # noqa: E111
    entity_suffix: str  # noqa: E111


CONDITION_DEFINITIONS: Final[tuple[ConditionDefinition, ...]] = (
    ConditionDefinition("is_hungry", "binary_sensor", "is_hungry"),
    ConditionDefinition("needs_walk", "binary_sensor", "needs_walk"),
    ConditionDefinition("on_walk", "binary_sensor", "walk_in_progress"),
    ConditionDefinition("in_safe_zone", "binary_sensor", "in_safe_zone"),
    ConditionDefinition("attention_needed", "binary_sensor", "attention_needed"),
    ConditionDefinition("status_is", "sensor", "status"),
)

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(
            {definition.type for definition in CONDITION_DEFINITIONS},
        ),
        vol.Optional(CONF_ENTITY_ID): _ENTITY_ID_VALIDATOR,
        vol.Optional(CONF_STATUS): cv.string,
    },
)


async def async_get_conditions(
    hass: HomeAssistant,
    device_id: str,
) -> list[DeviceConditionPayload]:
    """List device conditions for PawControl devices."""  # noqa: E111

    context = resolve_device_context(hass, device_id)  # noqa: E111
    if context.dog_id is None:  # noqa: E111
        return []

    conditions: list[DeviceConditionPayload] = []  # noqa: E111
    for definition in CONDITION_DEFINITIONS:  # noqa: E111
        unique_id = build_unique_id(context.dog_id, definition.entity_suffix)
        entity_id = resolve_entity_id(
            hass,
            device_id,
            unique_id,
            definition.platform,
        )
        if entity_id is None:
            continue  # noqa: E111

        conditions.append(
            {
                CONF_CONDITION: "device",
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_METADATA: build_device_automation_metadata(),
                CONF_TYPE: definition.type,
                CONF_ENTITY_ID: entity_id,
            },
        )

    return conditions  # noqa: E111


async def async_get_condition_capabilities(
    hass: HomeAssistant,
    config: dict[str, str],
) -> dict[str, vol.Schema]:
    """Return condition capability schemas."""  # noqa: E111

    if config.get(CONF_TYPE) != "status_is":  # noqa: E111
        return {}

    return {  # noqa: E111
        "extra_fields": vol.Schema(
            {
                vol.Required(CONF_STATUS): cv.string,
            },
        ),
    }


async def async_condition_from_config(
    hass: HomeAssistant,
    config: dict[str, str],
) -> ConditionCheckerType:
    """Create a condition checker for PawControl device automation."""  # noqa: E111

    validated = CONDITION_SCHEMA(config)  # noqa: E111
    device_id = validated[CONF_DEVICE_ID]  # noqa: E111
    context = resolve_device_context(hass, device_id)  # noqa: E111
    entity_id = validated.get(CONF_ENTITY_ID)  # noqa: E111
    condition_type = validated[CONF_TYPE]  # noqa: E111

    def _evaluate_state(expected_on: bool) -> bool:  # noqa: E111
        state = hass.states.get(entity_id) if entity_id else None
        if state is None:
            return False  # noqa: E111
        return (state.state == STATE_ON) is expected_on

    def _evaluate_status(expected_status: str) -> bool:  # noqa: E111
        snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
        if snapshot is not None:
            return snapshot.get("state") == expected_status  # noqa: E111

        state = hass.states.get(entity_id) if entity_id else None
        if state is None:
            return False  # noqa: E111
        return state.state == expected_status

    def _condition(  # noqa: E111
        _hass: HomeAssistant,
        _variables: Mapping[str, Any] | None,
    ) -> bool:
        match condition_type:
            case "is_hungry":  # noqa: E111
                snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
                if snapshot is not None:
                    return bool(snapshot.get("is_hungry", False))  # noqa: E111
                return _evaluate_state(True)
            case "needs_walk":  # noqa: E111
                snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
                if snapshot is not None:
                    return bool(snapshot.get("needs_walk", False))  # noqa: E111
                return _evaluate_state(True)
            case "on_walk":  # noqa: E111
                snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
                if snapshot is not None:
                    return bool(snapshot.get("on_walk", False))  # noqa: E111
                return _evaluate_state(True)
            case "in_safe_zone":  # noqa: E111
                snapshot = resolve_status_snapshot(context.runtime_data, context.dog_id)
                if snapshot is not None:
                    return bool(snapshot.get("in_safe_zone", True))  # noqa: E111
                return _evaluate_state(True)
            case "attention_needed":  # noqa: E111
                return _evaluate_state(True)
            case "status_is":  # noqa: E111
                expected = validated.get(CONF_STATUS)
                if not expected:
                    _LOGGER.debug("Missing status value for status_is condition")  # noqa: E111
                    return False  # noqa: E111
                return _evaluate_status(expected)
            case _:  # noqa: E111
                _LOGGER.debug("Unknown PawControl condition type: %s", condition_type)
                return False

    return _condition  # noqa: E111
