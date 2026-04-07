"""Focused failure-path unit tests for ``services.py``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import HomeAssistantError


def _runtime_data_with_coordinator(
    *,
    mock_hass: SimpleNamespace,
    runtime_managers: SimpleNamespace,
    dog_configs: dict[str, dict[str, object]] | None = None,
) -> tuple[SimpleNamespace, SimpleNamespace]:
    """Build a minimal runtime/coordinator pair for service handler tests."""
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    dogs = dog_configs or {}

    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_managers,
        get_dog_config=Mock(side_effect=lambda dog_id: dogs.get(dog_id)),
        get_configured_dog_ids=Mock(return_value=set(dogs)),
        async_request_refresh=AsyncMock(),
    )
    for manager_name, manager_value in vars(runtime_managers).items():
        setattr(coordinator, manager_name, manager_value)

    runtime_data = SimpleNamespace(performance_stats={}, coordinator=coordinator)
    return runtime_data, config_entry


async def _register_handler(
    *,
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    runtime_data: SimpleNamespace,
    config_entry: SimpleNamespace,
    service_name: str,
) -> object:
    """Register all services and return the selected wrapped handler."""
    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.has_service = Mock(return_value=False)
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )

    await services.async_setup_services(mock_hass)

    for call in mock_hass.services.async_register.call_args_list:
        if call.args[0] == DOMAIN and call.args[1] == service_name:
            return call.args[2]

    raise AssertionError(f"Service handler {service_name} was not registered")


def test_coerce_service_bool_false_variants_are_deterministic() -> None:
    """False-like service values should map to the ``return False`` branches."""
    assert services._coerce_service_bool("off", field="enabled") is False
    assert services._coerce_service_bool(0, field="enabled") is False


@pytest.mark.asyncio
async def test_service_wrapper_marks_handler_exception_as_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrapped handlers should propagate manager exceptions as HomeAssistantError."""
    runtime_data = SimpleNamespace(performance_stats={})
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(side_effect=RuntimeError("smtp down"))
    )
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
        notification_manager=notification_manager,
        get_dog_config=Mock(return_value=None),
        get_configured_dog_ids=Mock(return_value=set()),
    )
    runtime_data.coordinator = coordinator

    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.has_service = Mock(return_value=False)
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )

    await services.async_setup_services(mock_hass)

    handler = None
    for call in mock_hass.services.async_register.call_args_list:
        if (
            call.args[0] == DOMAIN
            and call.args[1] == services.SERVICE_SEND_NOTIFICATION
        ):
            handler = call.args[2]
            break

    assert handler is not None

    with pytest.raises(
        HomeAssistantError, match="Failed to send the PawControl notification"
    ):
        await handler(
            SimpleNamespace(data={"title": "A", "message": "B"}, context=None)
        )


@pytest.mark.asyncio
async def test_add_gps_point_success_and_false_paths_persist_user_visible_result(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPS add handler should report added/ignored outcomes per manager bool."""
    walk_manager = SimpleNamespace(
        async_add_gps_point=AsyncMock(side_effect=[True, False])
    )
    runtime_data, config_entry = _runtime_data_with_coordinator(
        mock_hass=mock_hass,
        runtime_managers=SimpleNamespace(walk_manager=walk_manager),
        dog_configs={"buddy": {"name": "Buddy"}},
    )
    handler = await _register_handler(
        mock_hass=mock_hass,
        monkeypatch=monkeypatch,
        runtime_data=runtime_data,
        config_entry=config_entry,
        service_name=services.SERVICE_ADD_GPS_POINT,
    )

    payload = {"dog_id": "buddy", "latitude": 51.1234, "longitude": 8.5678}
    await handler(SimpleNamespace(data=payload, context=None))
    first_result = runtime_data.performance_stats["last_service_result"]
    assert first_result["status"] == "success"
    assert first_result["details"]["result"] == "added"

    await handler(SimpleNamespace(data=payload, context=None))
    second_result = runtime_data.performance_stats["last_service_result"]
    assert second_result["status"] == "success"
    assert second_result["details"]["result"] == "ignored"


@pytest.mark.asyncio
async def test_add_gps_point_invalid_dog_id_raises_validation_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown dog IDs should fail fast with a user-facing validation hint."""
    walk_manager = SimpleNamespace(async_add_gps_point=AsyncMock())
    runtime_data, config_entry = _runtime_data_with_coordinator(
        mock_hass=mock_hass,
        runtime_managers=SimpleNamespace(walk_manager=walk_manager),
        dog_configs={"buddy": {"name": "Buddy"}},
    )
    handler = await _register_handler(
        mock_hass=mock_hass,
        monkeypatch=monkeypatch,
        runtime_data=runtime_data,
        config_entry=config_entry,
        service_name=services.SERVICE_ADD_GPS_POINT,
    )

    with pytest.raises(ServiceValidationError, match="Unknown dog_id 'ghost'.*buddy"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "ghost", "latitude": 51.1234, "longitude": 8.5678},
                context=None,
            )
        )


@pytest.mark.asyncio
async def test_add_gps_point_exception_is_wrapped_and_recorded(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected GPS manager failures should be wrapped into HomeAssistantError."""
    walk_manager = SimpleNamespace(
        async_add_gps_point=AsyncMock(side_effect=RuntimeError("gps cache exploded"))
    )
    runtime_data, config_entry = _runtime_data_with_coordinator(
        mock_hass=mock_hass,
        runtime_managers=SimpleNamespace(walk_manager=walk_manager),
        dog_configs={"buddy": {"name": "Buddy"}},
    )
    handler = await _register_handler(
        mock_hass=mock_hass,
        monkeypatch=monkeypatch,
        runtime_data=runtime_data,
        config_entry=config_entry,
        service_name=services.SERVICE_ADD_GPS_POINT,
    )

    with pytest.raises(HomeAssistantError, match="Failed to add GPS point for buddy"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "latitude": 51.1234, "longitude": 8.5678},
                context=None,
            )
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["status"] == "error"
    assert "Failed to add GPS point for buddy" in result["message"]


@pytest.mark.asyncio
async def test_update_health_success_and_no_update_paths_are_exposed(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health update handler should report updated/no_update based on manager bool."""
    feeding_manager = SimpleNamespace(
        async_update_health_data=AsyncMock(side_effect=[True, False])
    )
    runtime_data, config_entry = _runtime_data_with_coordinator(
        mock_hass=mock_hass,
        runtime_managers=SimpleNamespace(feeding_manager=feeding_manager),
        dog_configs={"buddy": {"name": "Buddy"}},
    )
    handler = await _register_handler(
        mock_hass=mock_hass,
        monkeypatch=monkeypatch,
        runtime_data=runtime_data,
        config_entry=config_entry,
        service_name=services.SERVICE_UPDATE_HEALTH,
    )

    data = {"dog_id": "buddy", "weight": 14.2}
    await handler(SimpleNamespace(data=data, context=None))
    first_result = runtime_data.performance_stats["last_service_result"]
    assert first_result["details"]["result"] == "updated"
    runtime_data.coordinator.async_request_refresh.assert_awaited_once()

    await handler(SimpleNamespace(data=data, context=None))
    second_result = runtime_data.performance_stats["last_service_result"]
    assert second_result["details"]["result"] == "no_update"
    assert runtime_data.coordinator.async_request_refresh.await_count == 1


@pytest.mark.asyncio
async def test_update_health_invalid_input_and_exception_paths(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health handler should fail for invalid IDs and wrap runtime exceptions."""
    feeding_manager = SimpleNamespace(
        async_update_health_data=AsyncMock(
            side_effect=RuntimeError("storage unavailable")
        )
    )
    runtime_data, config_entry = _runtime_data_with_coordinator(
        mock_hass=mock_hass,
        runtime_managers=SimpleNamespace(feeding_manager=feeding_manager),
        dog_configs={"buddy": {"name": "Buddy"}},
    )
    handler = await _register_handler(
        mock_hass=mock_hass,
        monkeypatch=monkeypatch,
        runtime_data=runtime_data,
        config_entry=config_entry,
        service_name=services.SERVICE_UPDATE_HEALTH,
    )

    with pytest.raises(ServiceValidationError, match="Unknown dog_id 'ghost'.*buddy"):
        await handler(
            SimpleNamespace(data={"dog_id": "ghost", "weight": 15.0}, context=None)
        )

    with pytest.raises(
        HomeAssistantError, match="Failed to update health data for buddy"
    ):
        await handler(
            SimpleNamespace(data={"dog_id": "buddy", "weight": 15.0}, context=None)
        )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["status"] == "error"
    assert "Failed to update health data for buddy" in result["message"]
