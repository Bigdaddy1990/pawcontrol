"""Tests for switch service-oriented methods."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.exceptions import HomeAssistantError

from custom_components.pawcontrol.switch import PawControlVisitorModeSwitch


class _DummyCoordinator:
    """Minimal coordinator stub compatible with CoordinatorEntity."""

    def __init__(self) -> None:
        self.available = True
        self.last_update_success = True
        self.last_update_success_time = None
        self.last_exception = None
        self.config_entry = SimpleNamespace(entry_id="entry-1")

    def async_add_listener(self, update_callback):
        return lambda: None

    def get_dog_data(self, dog_id: str):
        return {"dog_info": {"dog_id": dog_id, "dog_name": "Buddy"}}


@pytest.mark.asyncio
async def test_visitor_mode_switch_turn_on_calls_service_with_expected_payload() -> (
    None
):
    coordinator = _DummyCoordinator()
    entity = PawControlVisitorModeSwitch(coordinator, "dog-1", "Buddy")
    entity._attr_hass = SimpleNamespace()
    entity.async_write_ha_state = Mock()
    entity._async_call_hass_service = AsyncMock(return_value=True)

    await entity.async_turn_on()

    entity._async_call_hass_service.assert_awaited_once_with(
        "pawcontrol",
        "set_visitor_mode",
        {
            "dog_id": "dog-1",
            "enabled": True,
            "visitor_name": "Switch Toggle",
            "reduced_alerts": True,
        },
        blocking=False,
    )
    assert entity.is_on is True


@pytest.mark.asyncio
async def test_visitor_mode_switch_service_failure_keeps_state_consistent() -> None:
    coordinator = _DummyCoordinator()
    entity = PawControlVisitorModeSwitch(coordinator, "dog-1", "Buddy")
    entity._attr_hass = SimpleNamespace()
    entity.async_write_ha_state = Mock()
    entity._is_on = False
    entity._async_call_hass_service = AsyncMock(return_value=False)

    with pytest.raises(
        HomeAssistantError,
        match="Failed to turn on visitor_mode",
    ):
        await entity.async_turn_on()

    assert entity._is_on is False


@pytest.mark.asyncio
async def test_visitor_mode_switch_turn_off_calls_service_with_expected_payload() -> (
    None
):
    coordinator = _DummyCoordinator()
    entity = PawControlVisitorModeSwitch(coordinator, "dog-1", "Buddy")
    entity.hass = SimpleNamespace()
    entity.async_write_ha_state = Mock()
    entity._is_on = True
    entity._async_call_hass_service = AsyncMock(return_value=True)

    await entity.async_turn_off()

    entity._async_call_hass_service.assert_awaited_once_with(
        "pawcontrol",
        "set_visitor_mode",
        {
            "dog_id": "dog-1",
            "enabled": False,
            "visitor_name": None,
            "reduced_alerts": False,
        },
        blocking=False,
    )
    assert entity.is_on is False


@pytest.mark.asyncio
async def test_visitor_mode_switch_command_exception_keeps_state_consistent() -> None:
    """Exceptions from command call should be wrapped and not flip state."""
    coordinator = _DummyCoordinator()
    entity = PawControlVisitorModeSwitch(coordinator, "dog-1", "Buddy")
    entity._attr_hass = SimpleNamespace()
    entity.async_write_ha_state = Mock()
    entity._is_on = False
    entity._async_call_hass_service = AsyncMock(side_effect=TimeoutError("timeout"))

    with pytest.raises(HomeAssistantError, match="Failed to turn on visitor_mode"):
        await entity.async_turn_on()

    assert entity._is_on is False
