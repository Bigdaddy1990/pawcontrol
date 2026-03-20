"""Unit tests for PawControl device triggers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_FROM,
    CONF_METADATA,
    CONF_PLATFORM,
    CONF_TO,
    CONF_TYPE,
)
import pytest
import voluptuous as vol

from custom_components.pawcontrol import device_trigger
from custom_components.pawcontrol.const import DOMAIN


@pytest.mark.asyncio
async def test_async_get_triggers_returns_empty_without_dog_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No triggers should be exposed when the device has no dog mapping."""
    monkeypatch.setattr(
        device_trigger,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id=None),
    )

    triggers = await device_trigger.async_get_triggers(SimpleNamespace(), "device-1")

    assert triggers == []


@pytest.mark.asyncio
async def test_async_get_triggers_builds_payloads_for_resolved_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolved entities should produce one trigger payload per definition."""
    monkeypatch.setattr(
        device_trigger,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id="buddy"),
    )
    monkeypatch.setattr(
        device_trigger,
        "build_device_automation_metadata",
        lambda: {"secondary": False, "generated": True},
    )
    monkeypatch.setattr(
        device_trigger,
        "build_unique_id",
        lambda dog_id, suffix: f"{dog_id}:{suffix}",
    )
    monkeypatch.setattr(
        device_trigger,
        "resolve_entity_id",
        lambda _hass, _device_id, unique_id, _platform: (
            f"sensor.{unique_id.replace(':', '_')}" if "status" in unique_id else None
        ),
    )

    triggers = await device_trigger.async_get_triggers(SimpleNamespace(), "device-2")

    assert triggers == [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-2",
            CONF_DOMAIN: DOMAIN,
            CONF_METADATA: {"secondary": False, "generated": True},
            CONF_TYPE: "status_changed",
            CONF_ENTITY_ID: "sensor.buddy_status",
        }
    ]


@pytest.mark.asyncio
async def test_async_get_triggers_includes_state_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Definitions with explicit state transitions should preserve them."""
    monkeypatch.setattr(
        device_trigger,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id="buddy"),
    )
    monkeypatch.setattr(
        device_trigger,
        "build_device_automation_metadata",
        lambda: {"secondary": False},
    )
    monkeypatch.setattr(
        device_trigger,
        "build_unique_id",
        lambda dog_id, suffix: f"{dog_id}:{suffix}",
    )
    monkeypatch.setattr(
        device_trigger,
        "resolve_entity_id",
        lambda _hass, _device_id, unique_id, _platform: (
            "binary_sensor.buddy_walk_in_progress"
            if unique_id.endswith("walk_in_progress")
            else None
        ),
    )

    triggers = await device_trigger.async_get_triggers(SimpleNamespace(), "device-3")

    assert triggers == [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-3",
            CONF_DOMAIN: DOMAIN,
            CONF_METADATA: {"secondary": False},
            CONF_TYPE: "walk_started",
            CONF_ENTITY_ID: "binary_sensor.buddy_walk_in_progress",
            CONF_TO: "on",
        },
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-3",
            CONF_DOMAIN: DOMAIN,
            CONF_METADATA: {"secondary": False},
            CONF_TYPE: "walk_ended",
            CONF_ENTITY_ID: "binary_sensor.buddy_walk_in_progress",
            CONF_TO: "off",
        },
    ]


@pytest.mark.asyncio
async def test_async_get_triggers_includes_from_state_transitions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom trigger definitions with from-state filters should preserve them."""
    monkeypatch.setattr(
        device_trigger,
        "TRIGGER_DEFINITIONS",
        (
            device_trigger.TriggerDefinition(
                "status_left",
                "sensor",
                "status",
                from_state="playing",
            ),
        ),
    )
    monkeypatch.setattr(
        device_trigger,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id="buddy"),
    )
    monkeypatch.setattr(
        device_trigger,
        "build_device_automation_metadata",
        lambda: {"secondary": False},
    )
    monkeypatch.setattr(
        device_trigger,
        "build_unique_id",
        lambda dog_id, suffix: f"{dog_id}:{suffix}",
    )
    monkeypatch.setattr(
        device_trigger,
        "resolve_entity_id",
        lambda *_args: "sensor.buddy_status",
    )

    triggers = await device_trigger.async_get_triggers(SimpleNamespace(), "device-4")

    assert triggers == [
        {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: "device-4",
            CONF_DOMAIN: DOMAIN,
            CONF_METADATA: {"secondary": False},
            CONF_TYPE: "status_left",
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_FROM: "playing",
        }
    ]


@pytest.mark.asyncio
async def test_async_get_trigger_capabilities_only_exposes_status_filters() -> None:
    """Only the status trigger supports from/to capability fields."""
    capabilities = await device_trigger.async_get_trigger_capabilities(
        SimpleNamespace(),
        {CONF_TYPE: "status_changed"},
    )

    assert "extra_fields" in capabilities
    assert capabilities["extra_fields"]({CONF_FROM: "idle", CONF_TO: "playing"}) == {
        CONF_FROM: "idle",
        CONF_TO: "playing",
    }
    assert (
        await device_trigger.async_get_trigger_capabilities(
            SimpleNamespace(),
            {CONF_TYPE: "walk_started"},
        )
        == {}
    )


@pytest.mark.asyncio
async def test_async_attach_trigger_requires_entity_id() -> None:
    """Attaching a trigger without an entity id should fail validation."""
    with pytest.raises(vol.Invalid, match="Missing entity_id"):
        await device_trigger.async_attach_trigger(
            SimpleNamespace(),
            {
                CONF_DEVICE_ID: "device-4",
                CONF_DOMAIN: DOMAIN,
                CONF_PLATFORM: "device",
                CONF_TYPE: "status_changed",
            },
            AsyncMock(),
            {},
        )


@pytest.mark.asyncio
async def test_async_attach_trigger_filters_state_changes_and_dispatches_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Matching events should dispatch the action payload once."""
    captured: dict[str, object] = {}
    scheduled: list[asyncio.Task[None]] = []

    def _track_state_change(_hass, entity_ids, callback):
        captured["entity_ids"] = entity_ids
        captured["callback"] = callback
        return Mock(name="unsubscribe")

    monkeypatch.setattr(
        device_trigger,
        "async_track_state_change_event",
        _track_state_change,
    )

    action = AsyncMock()
    hass = SimpleNamespace(
        async_create_task=lambda coro: scheduled.append(asyncio.create_task(coro)),
    )
    trigger_info = {"description": "Dog status changed"}

    unsubscribe = await device_trigger.async_attach_trigger(
        hass,
        {
            CONF_DEVICE_ID: "device-5",
            CONF_DOMAIN: DOMAIN,
            CONF_PLATFORM: "device",
            CONF_TYPE: "status_changed",
            CONF_ENTITY_ID: "sensor.buddy_status",
            CONF_FROM: "idle",
            CONF_TO: "playing",
        },
        action,
        trigger_info,
    )

    assert callable(unsubscribe)
    assert captured["entity_ids"] == ["sensor.buddy_status"]

    callback = captured["callback"]
    assert callable(callback)

    callback(
        SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state="sleeping"),
                "new_state": SimpleNamespace(state="playing"),
            }
        )
    )
    assert scheduled == []

    callback(
        SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state="idle"),
                "new_state": SimpleNamespace(state="sleeping"),
            }
        )
    )
    assert scheduled == []

    callback(
        SimpleNamespace(
            data={
                "old_state": SimpleNamespace(state="idle"),
                "new_state": SimpleNamespace(state="playing"),
            }
        )
    )
    await asyncio.gather(*scheduled)

    action.assert_awaited_once()
    payload = action.await_args.args[0]
    assert payload == {
        "platform": "device",
        "device_id": "device-5",
        "domain": DOMAIN,
        "type": "status_changed",
        "entity_id": "sensor.buddy_status",
        "from_state": SimpleNamespace(state="idle"),
        "to_state": SimpleNamespace(state="playing"),
        "description": "Dog status changed",
    }
