"""Tests for PawControl service handlers."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol import services as services_module
from custom_components.pawcontrol.const import (
    DOMAIN,
    MODULE_FEEDING,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.services import (
    SERVICE_ADD_GARDEN_ACTIVITY,
    SERVICE_CONFIRM_POOP,
    SERVICE_END_WALK,
    SERVICE_START_WALK,
    ConfigEntryState,
)
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    JSONLikeMapping,
    JSONMutableMapping,
    PawControlRuntimeData,
    ensure_dog_config_data,
    ensure_dog_modules_config,
)
from custom_components.pawcontrol.walk_manager import WeatherCondition
from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntryChange,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def coordinator_mock() -> SimpleNamespace:
    """Return a coordinator-like object with async mocks."""

    dog_config_raw = {
        DOG_ID_FIELD: "doggo",
        DOG_NAME_FIELD: "Doggo",
        DOG_MODULES_FIELD: ensure_dog_modules_config(
            {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_HEALTH: True,
            }
        ),
    }

    dog_config = ensure_dog_config_data(dog_config_raw)
    if dog_config is None:  # pragma: no cover - guard for static typing expectations
        raise AssertionError("dog fixture must normalise to DogConfigData")

    return SimpleNamespace(
        walk_manager=AsyncMock(),
        async_request_refresh=AsyncMock(),
        feeding_manager=None,
        data_manager=None,
        garden_manager=None,
        get_dog_config=lambda dog_id: dog_config if dog_id == "doggo" else None,
        get_configured_dog_ids=lambda: [dog_config[DOG_ID_FIELD]],
        get_configured_dog_name=lambda dog_id: dog_config[DOG_NAME_FIELD]
        if dog_id == dog_config[DOG_ID_FIELD]
        else None,
        dogs=[dog_config],
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
        if hasattr(entry, "mock_state"):
            entry.mock_state(hass, ConfigEntryState.LOADED)
        else:
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
            dogs=list(getattr(coordinator, "dogs", [])),
        )
        entry.runtime_data = runtime
    else:
        runtime.coordinator = coordinator

    coordinator.config_entry = entry
    coordinator.hass = hass

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


def _service_call(service: str, data: JSONLikeMapping) -> ServiceCall:
    """Create a ServiceCall instance mirroring Home Assistant behavior."""

    return ServiceCall(
        DOMAIN,
        service,
        cast(JSONMutableMapping, dict(data)),
    )


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
        _service_call(
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
        _service_call(
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
            _service_call(
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
            _service_call(
                SERVICE_CONFIRM_POOP,
                {"dog_id": "doggo", "confirmed": True},
            )
        )

    coordinator_mock.garden_manager.has_pending_confirmation.assert_called_once_with(
        "doggo"
    )
    coordinator_mock.garden_manager.async_handle_poop_confirmation.assert_not_awaited()

    runtime_data = coordinator_mock.config_entry.runtime_data
    stats = runtime_data.performance_stats
    assert stats["service_results"], "service results should capture validation failure"
    result = stats["service_results"][-1]
    assert result["service"] == SERVICE_CONFIRM_POOP
    assert result["status"] == "error"
    assert result["message"].startswith("No pending garden poop confirmation")
    details = result.get("details")
    assert isinstance(details, dict)
    assert details.get("confirmed") is True
    assert "quality" not in details
    assert "size" not in details


@pytest.mark.asyncio
async def test_add_garden_activity_requires_active_session(
    hass: HomeAssistant,
    coordinator_mock: SimpleNamespace,
) -> None:
    """Ensure add garden activity surfaces payload telemetry on failure."""

    coordinator_mock.garden_manager = SimpleNamespace(
        async_add_activity=AsyncMock(return_value=False),
    )

    handlers = await _register_services(hass, coordinator_mock)
    handler = handlers[(DOMAIN, SERVICE_ADD_GARDEN_ACTIVITY)]

    with pytest.raises(ServiceValidationError):
        await handler(
            _service_call(
                SERVICE_ADD_GARDEN_ACTIVITY,
                {
                    "dog_id": "doggo",
                    "activity_type": "poop",
                    "confirmed": False,
                    "notes": "test",
                },
            )
        )

    runtime_data = coordinator_mock.config_entry.runtime_data
    stats = runtime_data.performance_stats
    assert stats["service_results"], "service results should capture activity failure"
    result = stats["service_results"][-1]
    assert result["service"] == SERVICE_ADD_GARDEN_ACTIVITY
    assert result["status"] == "error"
    assert "Start a garden session before adding activities" in result["message"]
    details = result.get("details")
    assert isinstance(details, dict)
    assert details.get("activity_type") == "poop"
    assert details.get("confirmed") is False
    assert details.get("notes") == "test"


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

        call = _service_call(
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

    with patch.object(
        hass.config_entries, "async_entries", return_value=[entry]
    ) as entries_mock:
        handlers = await _register_services(hass, coordinator_mock)
        handler = handlers[(DOMAIN, SERVICE_START_WALK)]

        call = _service_call(
            SERVICE_START_WALK,
            {"dog_id": "doggo"},
        )

        await handler(call)
        assert entries_mock.call_count == 1

        entry.state = ConfigEntryState.SETUP_IN_PROGRESS
        async_dispatcher_send(
            hass,
            SIGNAL_CONFIG_ENTRY_CHANGED,
            ConfigEntryChange.UPDATED,
            entry,
        )

        with pytest.raises(ServiceValidationError):
            await handler(call)

    assert entries_mock.call_count == 2


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

    with patch.object(
        hass.config_entries, "async_entries", return_value=[entry]
    ) as entries_mock:
        handlers = await _register_services(hass, coordinator_mock)
        handler = handlers[(DOMAIN, SERVICE_START_WALK)]

        call = _service_call(
            SERVICE_START_WALK,
            {"dog_id": "doggo"},
        )

        await handler(call)
        assert entries_mock.call_count == 1

        async_dispatcher_send(
            hass,
            SIGNAL_CONFIG_ENTRY_CHANGED,
            ConfigEntryChange.UPDATED,
            other_entry,
        )

        await handler(call)

    # Cache is still valid, so async_entries should not have been queried again.
    assert entries_mock.call_count == 1


@pytest.mark.asyncio
async def test_resolver_requires_loaded_entry(hass: HomeAssistant) -> None:
    """Ensure services fail fast when no PawControl entry is available."""

    await services_module.async_setup_services(hass)
    resolver = services_module._coordinator_resolver(hass)

    with pytest.raises(ServiceValidationError):
        resolver.resolve()


@pytest.mark.asyncio
async def test_resolver_invalidates_on_config_entry_change(
    hass: HomeAssistant, coordinator_mock: SimpleNamespace
) -> None:
    """Invalidate the cached coordinator when the entry unloads."""

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="resolver-test")
    entry.add_to_hass(hass)
    if hasattr(entry, "mock_state"):
        entry.mock_state(hass, ConfigEntryState.LOADED)
    else:
        entry.state = ConfigEntryState.LOADED

    runtime = PawControlRuntimeData(
        coordinator=coordinator_mock,
        data_manager=SimpleNamespace(),
        notification_manager=SimpleNamespace(),
        feeding_manager=SimpleNamespace(),
        walk_manager=SimpleNamespace(),
        entity_factory=SimpleNamespace(),
        entity_profile="standard",
        dogs=[],
    )
    entry.runtime_data = runtime
    coordinator_mock.config_entry = entry
    coordinator_mock.hass = hass

    await services_module.async_setup_services(hass)
    resolver = services_module._coordinator_resolver(hass)

    assert resolver.resolve() is coordinator_mock

    if hasattr(entry, "mock_state"):
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
    else:
        entry.state = ConfigEntryState.NOT_LOADED
    async_dispatcher_send(
        hass, SIGNAL_CONFIG_ENTRY_CHANGED, ConfigEntryChange.REMOVED, entry
    )

    with pytest.raises(ServiceValidationError):
        resolver.resolve()


@pytest.mark.asyncio
async def test_async_unload_services_cleans_listener_and_resolver(
    hass: HomeAssistant,
) -> None:
    """Ensure unloading services removes dispatcher hooks and cached resolver."""

    unsub_called = False

    def _mock_async_dispatcher_connect(*_: Any, **__: Any) -> Callable[[], None]:
        nonlocal unsub_called

        def _unsubscribe() -> None:
            nonlocal unsub_called
            unsub_called = True

        return _unsubscribe

    with (
        patch.object(
            services_module,
            "async_dispatcher_connect",
            side_effect=_mock_async_dispatcher_connect,
        ),
        patch.object(
            type(hass.services), "async_register", autospec=True
        ) as register_mock,
    ):
        register_mock.side_effect = lambda *args, **kwargs: None
        await services_module.async_setup_services(hass)

    domain_data = hass.data[DOMAIN]
    assert "_service_coordinator_listener" in domain_data
    assert "_service_coordinator_resolver" in domain_data

    with patch.object(type(hass.services), "async_remove", create=True) as remove_mock:
        remove_mock.side_effect = lambda *args, **kwargs: None
        await services_module.async_unload_services(hass)

    assert unsub_called is True
    remaining = hass.data.get(DOMAIN, {})
    assert "_service_coordinator_listener" not in remaining
    assert "_service_coordinator_resolver" not in remaining
