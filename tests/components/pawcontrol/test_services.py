"""Tests for PawControl service handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol import services as services_module
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.services import (
    SERVICE_CONFIRM_POOP,
    SERVICE_END_WALK,
    SERVICE_START_WALK,
    ConfigEntryState,
)
from custom_components.pawcontrol.types import PawControlRuntimeData
from custom_components.pawcontrol.walk_manager import WeatherCondition
from homeassistant.config_entries import EVENT_CONFIG_ENTRY_STATE_CHANGED
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def coordinator_mock() -> SimpleNamespace:
    """Return a coordinator-like object with async mocks."""

    return SimpleNamespace(
        walk_manager=AsyncMock(),
        async_request_refresh=AsyncMock(),
        feeding_manager=None,
        data_manager=None,
        garden_manager=None,
        get_dog_config=lambda dog_id: {"dog_name": "Doggo"}
        if dog_id == "doggo"
        else None,
        get_configured_dog_ids=lambda: ["doggo"],
        get_configured_dog_name=lambda dog_id: "Doggo" if dog_id == "doggo" else None,
    )


async def _register_services(
    hass: HomeAssistant,
    coordinator: SimpleNamespace,
) -> dict[tuple[str, str], Callable[[ServiceCall], Awaitable[None]]]:
    """Register PawControl services and return the handlers."""

    entry = getattr(coordinator, "config_entry", None)
    if entry is None:
        entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="test-entry")
        entry.add_to_hass(hass)
    elif isinstance(entry, MockConfigEntry):
        entry.add_to_hass(hass)

    if getattr(entry, "state", None) is not ConfigEntryState.LOADED:
        entry.state = ConfigEntryState.LOADED
    if getattr(entry, "domain", None) != DOMAIN:
        entry.domain = DOMAIN

    runtime = getattr(entry, "runtime_data", None)
    if not isinstance(runtime, PawControlRuntimeData):
        runtime = PawControlRuntimeData(
            coordinator=coordinator,
            data_manager=getattr(coordinator, "data_manager", SimpleNamespace()),
            notification_manager=getattr(
                coordinator, "notification_manager", SimpleNamespace()
            ),
            feeding_manager=getattr(coordinator, "feeding_manager", SimpleNamespace()),
            walk_manager=getattr(coordinator, "walk_manager", SimpleNamespace()),
            entity_factory=getattr(coordinator, "entity_factory", SimpleNamespace()),
            entity_profile=getattr(coordinator, "entity_profile", "standard"),
            dogs=[],
        )
        entry.runtime_data = runtime
    else:
        runtime.coordinator = coordinator

    coordinator.config_entry = entry

    registered: dict[tuple[str, str], Callable[[ServiceCall], Awaitable[None]]] = {}

    def register(
        self,
        domain: str,
        service: str,
        handler: Callable[[ServiceCall], Awaitable[None]],
        schema: object | None = None,
    ) -> None:
        registered[(domain, service)] = handler

    with patch.object(
        type(hass.services), "async_register", side_effect=register, autospec=True
    ):
        await services_module.async_setup_services(hass)

    return registered


@pytest.mark.asyncio
async def test_start_walk_service_passes_metadata(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
) -> None:
    """Verify the walk start service forwards optional metadata correctly."""

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_START_WALK)]

    coordinator_mock.walk_manager.async_start_walk.return_value = "session-1"

    await handler(
        ServiceCall(
            hass,
            DOMAIN,
            SERVICE_START_WALK,
            {
                "dog_id": "doggo",
                "walker": "Alex",
                "weather": "cloudy",
                "leash_used": False,
            },
        )
    )

    await_args = coordinator_mock.walk_manager.async_start_walk.await_args
    assert await_args.kwargs["dog_id"] == "doggo"
    assert await_args.kwargs["walk_type"] == "manual"
    assert await_args.kwargs["walker"] == "Alex"
    assert await_args.kwargs["leash_used"] is False
    assert await_args.kwargs["weather"] == WeatherCondition.CLOUDY


@pytest.mark.asyncio
async def test_end_walk_service_updates_stats(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ensure the end walk service stores metadata and logs summary."""

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_END_WALK)]

    coordinator_mock.walk_manager.async_end_walk.return_value = {
        "distance": 1500.0,
        "duration": 900.0,
    }

    caplog.set_level(logging.INFO, logger="custom_components.pawcontrol.services")

    await handler(
        ServiceCall(
            hass,
            DOMAIN,
            SERVICE_END_WALK,
            {
                "dog_id": "doggo",
                "notes": "Great walk",
                "dog_weight_kg": 18.5,
            },
        )
    )

    await_args = coordinator_mock.walk_manager.async_end_walk.await_args
    assert await_args.kwargs["dog_id"] == "doggo"
    assert await_args.kwargs["notes"] == "Great walk"
    assert await_args.kwargs["dog_weight_kg"] == 18.5
    coordinator_mock.async_request_refresh.assert_awaited_once()

    assert any("Ended walk for doggo" in message for message in caplog.messages), (
        "Expected summary log message was not emitted"
    )


@pytest.mark.asyncio
async def test_service_rejects_unknown_dog(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
) -> None:
    """Ensure handlers raise ServiceValidationError for unknown dog ids."""

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_START_WALK)]

    with pytest.raises(ServiceValidationError):
        await handler(
            ServiceCall(
                hass,
                DOMAIN,
                SERVICE_START_WALK,
                {"dog_id": "unknown"},
            )
        )


@pytest.mark.asyncio
async def test_confirm_garden_poop_requires_pending_confirmation(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
) -> None:
    """Ensure poop confirmation service validates pending state."""

    coordinator_mock.garden_manager = SimpleNamespace(
        has_pending_confirmation=MagicMock(return_value=False),
        async_handle_poop_confirmation=AsyncMock(),
    )

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_CONFIRM_POOP)]

    with pytest.raises(ServiceValidationError):
        await handler(
            ServiceCall(
                hass,
                DOMAIN,
                SERVICE_CONFIRM_POOP,
                {"dog_id": "doggo", "confirmed": True},
            )
        )

    coordinator_mock.garden_manager.has_pending_confirmation.assert_called_once_with(
        "doggo"
    )
    coordinator_mock.garden_manager.async_handle_poop_confirmation.assert_not_awaited()


@pytest.mark.asyncio
async def test_coordinator_lookup_is_cached(
    hass: HomeAssistant, coordinator_mock: SimpleNamespace
) -> None:
    """Ensure coordinator lookup does not repeatedly query config entries."""

    hass.data.setdefault(DOMAIN, {})

    entry = SimpleNamespace(
        entry_id="test-entry",
        state=ConfigEntryState.LOADED,
        runtime_data=SimpleNamespace(coordinator=coordinator_mock),
    )
    coordinator_mock.config_entry = entry

    with patch.object(
        hass.config_entries, "async_entries", return_value=[entry]
    ) as entries_mock:
        handlers = await _register_services(hass, coordinator_mock)
        handler = handlers[(DOMAIN, SERVICE_START_WALK)]

        coordinator_mock.walk_manager.async_start_walk.return_value = "session-1"

        call = ServiceCall(
            hass,
            DOMAIN,
            SERVICE_START_WALK,
            {"dog_id": "doggo"},
        )

        await handler(call)
        await handler(call)

    assert entries_mock.call_count == 1


@pytest.mark.asyncio
async def test_config_entry_state_change_invalidates_cache(
    hass: HomeAssistant, coordinator_mock: SimpleNamespace
) -> None:
    """Ensure cached coordinator invalidates when entry state changes."""

    hass.data.setdefault(DOMAIN, {})

    entry = SimpleNamespace(
        entry_id="test-entry",
        state=ConfigEntryState.LOADED,
        domain=DOMAIN,
        runtime_data=SimpleNamespace(coordinator=coordinator_mock),
    )
    coordinator_mock.config_entry = entry

    with (
        patch.object(
            hass.config_entries, "async_entries", return_value=[entry]
        ) as entries_mock,
        patch.object(
            hass.config_entries, "async_get_entry", return_value=entry
        ) as get_entry_mock,
    ):
        handlers = await _register_services(hass, coordinator_mock)
        handler = handlers[(DOMAIN, SERVICE_START_WALK)]

        call = ServiceCall(
            hass,
            DOMAIN,
            SERVICE_START_WALK,
            {"dog_id": "doggo"},
        )

        await handler(call)
        assert entries_mock.call_count == 1

        hass.bus.async_fire(
            EVENT_CONFIG_ENTRY_STATE_CHANGED,
            {
                "entry_id": entry.entry_id,
                "from_state": ConfigEntryState.LOADED,
                "to_state": ConfigEntryState.SETUP_IN_PROGRESS,
            },
        )
        await hass.async_block_till_done()

        await handler(call)

    assert entries_mock.call_count == 2
    get_entry_mock.assert_called_with(entry.entry_id)


@pytest.mark.asyncio
async def test_other_entry_state_change_does_not_invalidate_cache(
    hass: HomeAssistant, coordinator_mock: SimpleNamespace
) -> None:
    """Ensure cache survives state changes for different config entries."""

    hass.data.setdefault(DOMAIN, {})

    entry = SimpleNamespace(
        entry_id="test-entry",
        state=ConfigEntryState.LOADED,
        domain=DOMAIN,
        runtime_data=SimpleNamespace(coordinator=coordinator_mock),
    )
    coordinator_mock.config_entry = entry

    other_entry = SimpleNamespace(
        entry_id="other-entry",
        domain=DOMAIN,
        state=ConfigEntryState.SETUP_ERROR,
    )

    with (
        patch.object(
            hass.config_entries, "async_entries", return_value=[entry]
        ) as entries_mock,
        patch.object(
            hass.config_entries,
            "async_get_entry",
            side_effect=lambda entry_id: entry
            if entry_id == entry.entry_id
            else other_entry,
        ),
    ):
        handlers = await _register_services(hass, coordinator_mock)
        handler = handlers[(DOMAIN, SERVICE_START_WALK)]

        call = ServiceCall(
            hass,
            DOMAIN,
            SERVICE_START_WALK,
            {"dog_id": "doggo"},
        )

        await handler(call)
        assert entries_mock.call_count == 1

        hass.bus.async_fire(
            EVENT_CONFIG_ENTRY_STATE_CHANGED,
            {
                "entry_id": other_entry.entry_id,
                "from_state": ConfigEntryState.LOADED,
                "to_state": ConfigEntryState.SETUP_ERROR,
            },
        )
        await hass.async_block_till_done()

        await handler(call)

    # Cache is still valid, so async_entries should not have been queried again.
    assert entries_mock.call_count == 1
