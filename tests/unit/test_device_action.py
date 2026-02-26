"""Unit tests for PawControl device actions."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.exceptions import HomeAssistantError

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol import device_action


async def test_async_get_actions_returns_empty_without_dog_context(monkeypatch) -> None:
    """No actions should be exposed when the device cannot be mapped to a dog."""
    monkeypatch.setattr(
        device_action,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id=None),
    )

    actions = await device_action.async_get_actions(SimpleNamespace(), "device-1")

    assert actions == []


async def test_async_get_actions_returns_all_registered_actions(monkeypatch) -> None:
    """Resolved devices should expose all PawControl action definitions."""
    monkeypatch.setattr(
        device_action,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id="buddy"),
    )

    actions = await device_action.async_get_actions(SimpleNamespace(), "device-2")

    assert [action[CONF_TYPE] for action in actions] == [
        "log_feeding",
        "start_walk",
        "end_walk",
    ]
    assert all(action[CONF_DOMAIN] == DOMAIN for action in actions)
    assert all(action[CONF_DEVICE_ID] == "device-2" for action in actions)


@pytest.mark.parametrize(
    ("action_type", "expected_keys"),
    [
        ("log_feeding", {device_action.CONF_AMOUNT, device_action.CONF_MEAL_TYPE}),
        ("start_walk", {device_action.CONF_WALK_TYPE}),
        ("end_walk", {device_action.CONF_WALK_NOTES, device_action.CONF_SAVE_ROUTE}),
    ],
)
async def test_async_get_action_capabilities_returns_schema_fields(
    action_type: str,
    expected_keys: set[str],
) -> None:
    """Capability lookup should return field schemas for supported action types."""
    capabilities = await device_action.async_get_action_capabilities(
        SimpleNamespace(),
        {CONF_TYPE: action_type},
    )

    assert "fields" in capabilities
    assert expected_keys.issubset(set(capabilities["fields"].schema))


async def test_async_get_action_capabilities_returns_empty_for_unknown_type() -> None:
    """Unknown action types should not expose capability fields."""
    capabilities = await device_action.async_get_action_capabilities(
        SimpleNamespace(),
        {CONF_TYPE: "unknown"},
    )

    assert capabilities == {}


async def test_async_call_action_requires_runtime_context(monkeypatch) -> None:
    """Actions should fail fast when runtime data is unavailable."""
    monkeypatch.setattr(
        device_action,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(dog_id=None, runtime_data=None),
    )

    with pytest.raises(HomeAssistantError, match="runtime data"):
        await device_action.async_call_action(
            SimpleNamespace(),
            {
                CONF_DEVICE_ID: "device-3",
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "start_walk",
            },
            {},
        )


async def test_async_call_action_dispatches_to_runtime_managers(monkeypatch) -> None:
    """Known action types should call their matching manager methods."""
    feeding_manager = SimpleNamespace(async_add_feeding=AsyncMock())
    walk_manager = SimpleNamespace(async_start_walk=AsyncMock(), async_end_walk=AsyncMock())
    runtime_data = SimpleNamespace(
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
    )
    monkeypatch.setattr(
        device_action,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=runtime_data,
        ),
    )

    await device_action.async_call_action(
        SimpleNamespace(),
        {
            CONF_DEVICE_ID: "device-4",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "log_feeding",
            device_action.CONF_AMOUNT: "120",
            device_action.CONF_MEAL_TYPE: "dinner",
            device_action.CONF_NOTES: "extra",
            device_action.CONF_SCHEDULED: True,
        },
        {},
    )
    await device_action.async_call_action(
        SimpleNamespace(),
        {
            CONF_DEVICE_ID: "device-4",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "start_walk",
        },
        {},
    )
    await device_action.async_call_action(
        SimpleNamespace(),
        {
            CONF_DEVICE_ID: "device-4",
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: "end_walk",
            device_action.CONF_WALK_NOTES: "done",
            device_action.CONF_SAVE_ROUTE: False,
        },
        {},
    )

    feeding_manager.async_add_feeding.assert_awaited_once_with(
        "buddy",
        120.0,
        meal_type="dinner",
        notes="extra",
        scheduled=True,
    )
    walk_manager.async_start_walk.assert_awaited_once_with("buddy", "manual")
    walk_manager.async_end_walk.assert_awaited_once_with(
        "buddy",
        notes="done",
        save_route=False,
    )


async def test_async_call_action_requires_amount_for_log_feeding(monkeypatch) -> None:
    """Log feeding actions must include an amount."""
    runtime_data = SimpleNamespace(
        feeding_manager=SimpleNamespace(async_add_feeding=AsyncMock()),
        walk_manager=SimpleNamespace(async_start_walk=AsyncMock(), async_end_walk=AsyncMock()),
    )
    monkeypatch.setattr(
        device_action,
        "resolve_device_context",
        lambda _hass, _device_id: SimpleNamespace(
            dog_id="buddy",
            runtime_data=runtime_data,
        ),
    )

    with pytest.raises(HomeAssistantError, match="amount is required"):
        await device_action.async_call_action(
            SimpleNamespace(),
            {
                CONF_DEVICE_ID: "device-5",
                CONF_DOMAIN: DOMAIN,
                CONF_TYPE: "log_feeding",
            },
            {},
        )
