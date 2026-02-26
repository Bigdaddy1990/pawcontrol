"""Tests for PawControl device automations."""

import logging
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_CONDITION,
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FROM,
    CONF_METADATA,
    CONF_PLATFORM,
    CONF_TO,
    CONF_TYPE,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
import voluptuous as vol

from custom_components.pawcontrol.const import DOMAIN
import custom_components.pawcontrol.device_action as device_action_module
from custom_components.pawcontrol.device_action import (
    async_call_action,
    async_get_action_capabilities,
    async_get_actions,
)
from custom_components.pawcontrol.device_automation_helpers import build_unique_id
from custom_components.pawcontrol.device_condition import (
    async_condition_from_config,
    async_get_condition_capabilities,
    async_get_conditions,
)
from custom_components.pawcontrol.device_trigger import (
    async_attach_trigger,
    async_get_trigger_capabilities,
    async_get_triggers,
)
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData

DOG_ID = "buddy"
ENTRY_ID = "entry-1"


def _register_device(hass: HomeAssistant) -> dr.DeviceEntry:
    device_registry = dr.async_get(hass)
    return device_registry.async_get_or_create(
        config_entry_id=ENTRY_ID,
        identifiers={(DOMAIN, DOG_ID)},
    )


def _register_entity(
    hass: HomeAssistant,
    device_entry: dr.DeviceEntry,
    *,
    entity_id: str,
    platform: str,
    suffix: str,
) -> None:
    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        entity_id,
        config_entry_id=ENTRY_ID,
        device_id=device_entry.id,
        platform=platform,
        unique_id=build_unique_id(DOG_ID, suffix),
    )


@pytest.mark.asyncio
async def test_async_get_triggers_returns_available(hass: HomeAssistant) -> None:
    """Verify triggers are generated for registered device entities."""
    device_entry = _register_device(hass)
    _register_entity(
        hass,
        device_entry,
        entity_id="binary_sensor.pawcontrol_buddy_is_hungry",
        platform="binary_sensor",
        suffix="is_hungry",
    )
    _register_entity(
        hass,
        device_entry,
        entity_id="binary_sensor.pawcontrol_buddy_walk_in_progress",
        platform="binary_sensor",
        suffix="walk_in_progress",
    )
    _register_entity(
        hass,
        device_entry,
        entity_id="sensor.pawcontrol_buddy_status",
        platform="sensor",
        suffix="status",
    )

    triggers = await async_get_triggers(hass, device_entry.id)
    trigger_types = {trigger[CONF_TYPE] for trigger in triggers}

    assert "hungry" in trigger_types
    assert "walk_started" in trigger_types
    assert "walk_ended" in trigger_types
    assert "status_changed" in trigger_types
    assert all(CONF_METADATA in trigger for trigger in triggers)


@pytest.mark.asyncio
async def test_async_get_triggers_missing_device(hass: HomeAssistant) -> None:
    """Return no triggers when device is unknown."""
    triggers = await async_get_triggers(hass, "missing-device")

    assert triggers == []


@pytest.mark.asyncio
async def test_async_get_actions_returns_metadata(
    hass: HomeAssistant,
) -> None:
    """Verify action metadata is provided for devices."""
    device_entry = _register_device(hass)

    actions = await async_get_actions(hass, device_entry.id)

    assert actions
    assert all(CONF_METADATA in action for action in actions)


@pytest.mark.asyncio
async def test_async_get_actions_missing_device_returns_empty(
    hass: HomeAssistant,
) -> None:
    """Return no actions when the device cannot be resolved."""
    assert await async_get_actions(hass, "missing-device") == []


@pytest.mark.asyncio
async def test_async_get_conditions_returns_metadata(
    hass: HomeAssistant,
) -> None:
    """Verify condition metadata is provided for devices."""
    device_entry = _register_device(hass)
    entity_id = "binary_sensor.pawcontrol_buddy_is_hungry"
    _register_entity(
        hass,
        device_entry,
        entity_id=entity_id,
        platform="binary_sensor",
        suffix="is_hungry",
    )

    conditions = await async_get_conditions(hass, device_entry.id)

    assert conditions
    assert all(CONF_METADATA in condition for condition in conditions)


@pytest.mark.asyncio
async def test_condition_uses_entity_state_fallback(
    hass: HomeAssistant,
) -> None:
    """Verify conditions evaluate using entity state when no runtime data exists."""
    device_entry = _register_device(hass)
    entity_id = "binary_sensor.pawcontrol_buddy_is_hungry"
    _register_entity(
        hass,
        device_entry,
        entity_id=entity_id,
        platform="binary_sensor",
        suffix="is_hungry",
    )

    hass.states.async_set(entity_id, STATE_ON)

    condition = await async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "is_hungry",
            CONF_ENTITY_ID: entity_id,
        },
    )

    assert condition(hass, {})


@pytest.mark.asyncio
async def test_condition_missing_entity_returns_false(
    hass: HomeAssistant,
) -> None:
    """Ensure missing entities cause conditions to fail."""
    device_entry = _register_device(hass)

    condition = await async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "needs_walk",
            CONF_ENTITY_ID: "binary_sensor.pawcontrol_buddy_needs_walk",
        },
    )

    assert not condition(hass, {})


@pytest.mark.asyncio
async def test_condition_capabilities_status_is_requires_status(
    hass: HomeAssistant,
) -> None:
    """Ensure status conditions expose and validate the status field."""
    capabilities = await async_get_condition_capabilities(
        hass,
        {CONF_TYPE: "status_is"},
    )

    fields = capabilities["extra_fields"]
    fields({"status": "sleeping"})
    with pytest.raises(vol.Invalid):
        fields({})

    assert await async_get_condition_capabilities(hass, {CONF_TYPE: "needs_walk"}) == {}


@pytest.mark.asyncio
async def test_condition_status_is_uses_runtime_snapshot(
    hass: HomeAssistant,
) -> None:
    """Prefer runtime status snapshot values when evaluating status_is conditions."""
    device_entry = _register_device(hass)
    coordinator = Mock()
    coordinator.get_dog_data.return_value = {
        "status_snapshot": {"state": "sleeping"},
    }
    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=Mock(),
        notification_manager=Mock(),
        feeding_manager=AsyncMock(),
        walk_manager=AsyncMock(),
        entity_factory=Mock(),
        entity_profile="standard",
        dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
    )
    entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
    store_runtime_data(hass, entry, runtime_data)

    condition = await async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "status_is",
            "status": "sleeping",
        },
    )

    assert condition(hass, {})


@pytest.mark.asyncio
async def test_condition_status_is_missing_status_returns_false(
    hass: HomeAssistant,
) -> None:
    """Return false when status_is does not provide an expected status value."""
    device_entry = _register_device(hass)

    condition = await async_condition_from_config(
        hass,
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "status_is",
        },
    )

    assert not condition(hass, {})


@pytest.mark.asyncio
async def test_action_calls_feeding_manager(hass: HomeAssistant) -> None:
    """Verify device actions call managers with dog identifiers."""
    device_entry = _register_device(hass)

    feeding_manager = AsyncMock()
    walk_manager = AsyncMock()

    runtime_data = PawControlRuntimeData(
        coordinator=Mock(),
        data_manager=Mock(),
        notification_manager=Mock(),
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        entity_factory=Mock(),
        entity_profile="standard",
        dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
    )

    entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
    store_runtime_data(hass, entry, runtime_data)

    await async_call_action(
        hass,
        {
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "log_feeding",
            "amount": 120.0,
            "meal_type": "breakfast",
        },
        {},
    )

    feeding_manager.async_add_feeding.assert_awaited_once()
    call_args = feeding_manager.async_add_feeding.call_args
    assert call_args.args[0] == DOG_ID
    assert call_args.args[1] == 120.0


@pytest.mark.asyncio
async def test_action_capabilities_require_amount(
    hass: HomeAssistant,
) -> None:
    """Ensure feeding action capabilities require amount."""
    capabilities = await async_get_action_capabilities(
        hass,
        {CONF_TYPE: "log_feeding"},
    )

    fields = capabilities["fields"]
    fields({"amount": 1.0})
    with pytest.raises(vol.Invalid):
        fields({})


@pytest.mark.asyncio
async def test_action_capabilities_for_walk_actions(
    hass: HomeAssistant,
) -> None:
    """Ensure walk action capability schemas validate expected inputs."""
    start_capabilities = await async_get_action_capabilities(
        hass,
        {CONF_TYPE: "start_walk"},
    )
    start_capabilities["fields"]({"walk_type": "exercise"})

    end_capabilities = await async_get_action_capabilities(
        hass,
        {CONF_TYPE: "end_walk"},
    )
    end_capabilities["fields"]({"walk_notes": "quick walk", "save_route": True})


@pytest.mark.asyncio
async def test_action_capabilities_unknown_type_returns_empty(
    hass: HomeAssistant,
) -> None:
    """Return an empty capability map for unknown action types."""
    assert (await async_get_action_capabilities(hass, {CONF_TYPE: "unknown"})) == {}


@pytest.mark.asyncio
async def test_trigger_capabilities_status_changed(
    hass: HomeAssistant,
) -> None:
    """Ensure status trigger capabilities expose from/to fields."""
    capabilities = await async_get_trigger_capabilities(
        hass,
        {CONF_TYPE: "status_changed"},
    )

    fields = capabilities["extra_fields"]
    fields({CONF_FROM: "sleeping", CONF_TO: "playing"})

    assert (await async_get_trigger_capabilities(hass, {CONF_TYPE: "hungry"})) == {}


@pytest.mark.asyncio
async def test_attach_trigger_requires_entity_id(hass: HomeAssistant) -> None:
    """Reject trigger attachments that cannot resolve an entity."""
    with pytest.raises(vol.Invalid, match="Missing entity_id"):
        await async_attach_trigger(
            hass,
            {
                CONF_PLATFORM: "device",
                CONF_DEVICE_ID: "device-id",
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "hungry",
            },
            AsyncMock(),
            {"description": "Hungry trigger"},
        )


@pytest.mark.asyncio
async def test_attach_trigger_schedules_action_when_states_match(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attach trigger should dispatch the action payload when state filters match."""
    captured: dict[str, object] = {}
    unsubscribe = object()

    def _track_state_change_event(
        _hass: HomeAssistant,
        entity_ids: list[str],
        listener,
    ) -> object:
        captured["entity_ids"] = entity_ids
        captured["listener"] = listener
        return unsubscribe

    monkeypatch.setattr(
        "custom_components.pawcontrol.device_trigger.async_track_state_change_event",
        _track_state_change_event,
    )

    scheduled: list[object] = []
    monkeypatch.setattr(hass, "async_create_task", lambda coro: scheduled.append(coro))

    action = AsyncMock()
    removal = await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-id",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "hungry",
            CONF_ENTITY_ID: "binary_sensor.pawcontrol_buddy_is_hungry",
            CONF_FROM: "off",
            CONF_TO: "on",
        },
        action,
        {"description": "Hungry trigger"},
    )

    assert removal is unsubscribe
    assert captured["entity_ids"] == ["binary_sensor.pawcontrol_buddy_is_hungry"]

    callback = captured["listener"]
    event = Mock(
        data={
            "old_state": Mock(state="off"),
            "new_state": Mock(state="on"),
        }
    )
    callback(event)

    assert len(scheduled) == 1
    await scheduled[0]

    action.assert_awaited_once()
    payload = action.await_args.args[0]
    assert payload["platform"] == "device"
    assert payload["device_id"] == "device-id"
    assert payload["domain"] == DOMAIN
    assert payload["type"] == "hungry"
    assert payload["entity_id"] == "binary_sensor.pawcontrol_buddy_is_hungry"
    assert payload["description"] == "Hungry trigger"


@pytest.mark.asyncio
async def test_attach_trigger_ignores_events_that_do_not_match_filters(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """State filters should block callbacks when old/new values do not match."""
    captured: dict[str, object] = {}

    def _track_state_change_event(
        _hass: HomeAssistant,
        _entity_ids: list[str],
        listener,
    ) -> object:
        captured["listener"] = listener
        return object()

    monkeypatch.setattr(
        "custom_components.pawcontrol.device_trigger.async_track_state_change_event",
        _track_state_change_event,
    )

    action = AsyncMock()
    await async_attach_trigger(
        hass,
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-id",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "hungry",
            CONF_ENTITY_ID: "binary_sensor.pawcontrol_buddy_is_hungry",
            CONF_FROM: "off",
            CONF_TO: "on",
        },
        action,
        {"description": "Hungry trigger"},
    )

    callback = captured["listener"]
    callback(
        Mock(
            data={
                "old_state": Mock(state="idle"),
                "new_state": Mock(state="on"),
            }
        )
    )
    callback(
        Mock(
            data={
                "old_state": Mock(state="off"),
                "new_state": Mock(state="idle"),
            }
        )
    )

    action.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_missing_runtime_data_raises(
    hass: HomeAssistant,
) -> None:
    """Ensure actions raise when runtime data is missing."""
    with pytest.raises(HomeAssistantError):
        await async_call_action(
            hass,
            {
                CONF_DEVICE_ID: "missing-device",
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "start_walk",
            },
            {},
        )


@pytest.mark.asyncio
async def test_action_log_feeding_requires_amount(
    hass: HomeAssistant,
) -> None:
    """Validate log_feeding raises when amount is omitted."""
    device_entry = _register_device(hass)
    runtime_data = PawControlRuntimeData(
        coordinator=Mock(),
        data_manager=Mock(),
        notification_manager=Mock(),
        feeding_manager=AsyncMock(),
        walk_manager=AsyncMock(),
        entity_factory=Mock(),
        entity_profile="standard",
        dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
    )
    entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
    store_runtime_data(hass, entry, runtime_data)

    with pytest.raises(HomeAssistantError):
        await async_call_action(
            hass,
            {
                CONF_DEVICE_ID: device_entry.id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "log_feeding",
            },
            {},
        )


@pytest.mark.asyncio
async def test_action_calls_walk_manager_for_start_and_end(
    hass: HomeAssistant,
) -> None:
    """Ensure walk actions call async_start_walk and async_end_walk."""
    device_entry = _register_device(hass)

    walk_manager = AsyncMock()
    runtime_data = PawControlRuntimeData(
        coordinator=Mock(),
        data_manager=Mock(),
        notification_manager=Mock(),
        feeding_manager=AsyncMock(),
        walk_manager=walk_manager,
        entity_factory=Mock(),
        entity_profile="standard",
        dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
    )
    entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
    store_runtime_data(hass, entry, runtime_data)

    await async_call_action(
        hass,
        {
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "start_walk",
            "walk_type": "training",
        },
        {},
    )
    await async_call_action(
        hass,
        {
            CONF_DEVICE_ID: device_entry.id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "end_walk",
            "walk_notes": "great pace",
            "save_route": False,
        },
        {},
    )

    walk_manager.async_start_walk.assert_awaited_once_with(DOG_ID, "training")
    walk_manager.async_end_walk.assert_awaited_once_with(
        DOG_ID,
        notes="great pace",
        save_route=False,
    )


@pytest.mark.asyncio
async def test_action_unknown_type_logs_debug_and_returns(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure unknown actions are ignored with a debug log."""
    device_entry = _register_device(hass)
    feeding_manager = AsyncMock()
    walk_manager = AsyncMock()
    runtime_data = PawControlRuntimeData(
        coordinator=Mock(),
        data_manager=Mock(),
        notification_manager=Mock(),
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        entity_factory=Mock(),
        entity_profile="standard",
        dogs=[{"dog_id": DOG_ID, "dog_name": "Buddy"}],
    )
    entry = ConfigEntry(entry_id=ENTRY_ID, domain=DOMAIN, data={"dogs": []})
    store_runtime_data(hass, entry, runtime_data)
    monkeypatch.setattr(
        device_action_module,
        "ACTION_SCHEMA",
        vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): str,
                vol.Required(CONF_DOMAIN): str,
                vol.Required(CONF_TYPE): str,
            },
            extra=vol.ALLOW_EXTRA,
        ),
    )

    with caplog.at_level(logging.DEBUG):
        await async_call_action(
            hass,
            {
                CONF_DEVICE_ID: device_entry.id,
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "unknown_action",
            },
            {},
        )

    feeding_manager.async_add_feeding.assert_not_awaited()
    walk_manager.async_start_walk.assert_not_awaited()
    walk_manager.async_end_walk.assert_not_awaited()
    assert "Unhandled PawControl device action: unknown_action" in caplog.text
