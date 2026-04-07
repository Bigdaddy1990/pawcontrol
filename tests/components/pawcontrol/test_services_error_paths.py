"""Error-path coverage for PawControl services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.core import Context
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import (
    DOMAIN,
    EVENT_FEEDING_COMPLIANCE_CHECKED,
    SERVICE_CHECK_FEEDING_COMPLIANCE,
    SERVICE_START_GROOMING,
)
from custom_components.pawcontrol.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
)


async def _register_services_and_get_handler(
    hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_name: str,
) -> object:
    """Register services and return the wrapped handler for ``service_name``."""
    hass.data = {}
    hass.services.async_register = Mock()
    hass.services.has_service = Mock(return_value=False)
    if "async_entries" not in vars(hass.config_entries):
        hass.config_entries.async_entries = Mock(return_value=[])

    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)

    await services.async_setup_services(hass)

    for call in hass.services.async_register.call_args_list:
        domain, registered_service, handler = call.args[:3]
        if domain == DOMAIN and registered_service == service_name:
            return handler

    raise AssertionError(f"Service handler {service_name} not registered")


@pytest.mark.asyncio
async def test_given_notification_service_when_coordinator_missing_then_raise_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """send_notification should abort with a user-facing setup message."""
    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    call = SimpleNamespace(data={"title": "Hi", "message": "There"}, context=None)

    with pytest.raises(ServiceValidationError, match="PawControl is not set up"):
        await handler(call)


@pytest.mark.asyncio
async def test_given_async_setup_services_when_reconfigured_then_replace_listener(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should replace old listeners and keep target handlers registered."""
    removed = Mock()
    mock_hass.data = {DOMAIN: {"_service_coordinator_listener": removed}}
    mock_hass.services.async_register = Mock()
    mock_hass.services.has_service = Mock(return_value=False)
    if "async_entries" not in vars(mock_hass.config_entries):
        mock_hass.config_entries.async_entries = Mock(return_value=[])

    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)

    await services.async_setup_services(mock_hass)

    removed.assert_called_once_with()
    registered = {
        call.args[1] for call in mock_hass.services.async_register.call_args_list
    }
    assert services.SERVICE_SEND_NOTIFICATION in registered
    assert SERVICE_START_GROOMING in registered


@pytest.mark.asyncio
async def test_given_notification_service_when_expires_hours_invalid_then_raise_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Invalid expiry payload should raise validation errors and persist status."""
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(
            notification_manager=SimpleNamespace(async_send_notification=AsyncMock())
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        notification_manager=SimpleNamespace(async_send_notification=AsyncMock()),
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    runtime_data.coordinator = coordinator

    def _runtime_lookup(_hass: object, _entry: object) -> object:
        return runtime_data

    monkeypatch.setattr(services, "get_runtime_data", _runtime_lookup)

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    call = SimpleNamespace(
        data={
            "title": "Reminder",
            "message": "Feed now",
            "dog_id": "buddy",
            "expires_in_hours": "soon",
        },
        context=None,
    )

    with pytest.raises(
        ServiceValidationError, match="expires_in_hours must be a number"
    ):
        await handler(call)

    result = runtime_data.performance_stats["last_service_result"]
    assert result["service"] == services.SERVICE_SEND_NOTIFICATION
    assert result["status"] == "error"


@pytest.mark.asyncio
async def test_given_notification_service_when_runtime_fails_then_wrap_and_track(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Unexpected delivery errors should be wrapped and persisted."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(side_effect=RuntimeError("smtp down"))
    )
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(notification_manager=notification_manager)
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        notification_manager=notification_manager,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    runtime_data.coordinator = coordinator

    def _runtime_lookup(_hass: object, _entry: object) -> object:
        return runtime_data

    monkeypatch.setattr(services, "get_runtime_data", _runtime_lookup)

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    with pytest.raises(
        HomeAssistantError,
        match="Failed to send the PawControl notification",
    ):
        await handler(
            SimpleNamespace(data={"title": "A", "message": "B"}, context=None)
        )

    metrics = runtime_data.performance_stats["rejection_metrics"]
    assert metrics["last_failure_reason"] == "exception"
    assert runtime_data.performance_stats["last_service_result"]["status"] == "error"


@pytest.mark.asyncio
async def test_given_start_grooming_when_data_manager_missing_then_abort_guard(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Missing manager should trigger early abort semantics."""
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(data_manager=None),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
        get_configured_dog_name=runtime_data.coordinator.get_configured_dog_name,
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    runtime_data = SimpleNamespace(
        performance_stats=runtime_data.performance_stats, coordinator=coordinator
    )
    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        SERVICE_START_GROOMING,
    )

    with pytest.raises(HomeAssistantError, match="data manager is not ready yet"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "grooming_type": "bath"}, context=None
            )
        )


@pytest.mark.asyncio
async def test_given_feeding_compliance_service_when_successful_then_emit_event(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Success path should fire the user-visible compliance event."""
    feeding_result = {
        "status": "completed",
        "compliance_score": 95,
        "compliance_rate": 0.95,
        "days_analyzed": 7,
        "days_with_issues": 0,
        "compliance_issues": [],
        "missed_meals": [],
    }
    feeding_manager = SimpleNamespace(
        async_check_feeding_compliance=AsyncMock(return_value=feeding_result)
    )
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(
            feeding_manager=feeding_manager,
            notification_manager=None,
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        feeding_manager=feeding_manager,
        notification_manager=None,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])
    mock_hass.config = SimpleNamespace(language="de")

    runtime_data.coordinator = coordinator

    def _runtime_lookup(_hass: object, _entry: object) -> object:
        return runtime_data

    monkeypatch.setattr(services, "get_runtime_data", _runtime_lookup)
    monkeypatch.setattr(
        services,
        "async_publish_feeding_compliance_issue",
        AsyncMock(),
    )
    monkeypatch.setattr(
        services,
        "async_build_feeding_compliance_summary",
        AsyncMock(return_value={"title": "OK", "message": "Alles gut"}),
    )

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        SERVICE_CHECK_FEEDING_COMPLIANCE,
    )

    await handler(
        SimpleNamespace(
            data={"dog_id": "buddy", "days_to_check": 7, "notify_on_issues": False},
            context=Context(context_id="ctx-1", user_id="user-1"),
        )
    )

    mock_hass.bus.async_fire.assert_called_once()
    fired_event_type = mock_hass.bus.async_fire.call_args.args[0]
    assert fired_event_type == EVENT_FEEDING_COMPLIANCE_CHECKED
    assert runtime_data.performance_stats["last_service_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_given_feeding_compliance_when_manager_raises_then_wrap_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Unexpected manager errors should be wrapped into HomeAssistantError."""
    feeding_manager = SimpleNamespace(
        async_check_feeding_compliance=AsyncMock(side_effect=RuntimeError("api boom"))
    )
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(
            feeding_manager=feeding_manager,
            notification_manager=None,
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        feeding_manager=feeding_manager,
        notification_manager=None,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    runtime_data.coordinator = coordinator

    def _runtime_lookup(_hass: object, _entry: object) -> object:
        return runtime_data

    monkeypatch.setattr(services, "get_runtime_data", _runtime_lookup)

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        SERVICE_CHECK_FEEDING_COMPLIANCE,
    )

    with pytest.raises(HomeAssistantError, match="Failed to check feeding compliance"):
        await handler(SimpleNamespace(data={"dog_id": "buddy"}, context=None))

    assert runtime_data.performance_stats["last_service_result"]["status"] == "error"


def test_given_record_service_result_when_runtime_data_missing_then_return_early() -> (
    None
):
    """Runtime-data guard should no-op cleanly for abort branches."""
    services._record_service_result(None, service="send_notification", status="error")


def test_given_record_service_result_when_rejections_exist_then_include_details() -> (
    None
):
    """Rejection metrics should surface in persisted service details."""
    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": {"rejected_call_count": 2}}
    )

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="error",
        details={"source": "test"},
    )

    result = runtime_data.performance_stats["last_service_result"]
    assert result["details"]["resilience"]["rejected_call_count"] == 2
    assert result["status"] == "error"


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            services.SERVICE_SEND_NOTIFICATION_SCHEMA,
            {"message": "Body only"},
        ),
        (
            services.SERVICE_SEND_NOTIFICATION_SCHEMA,
            {"title": "Title only"},
        ),
        (
            services.SERVICE_START_GROOMING_SCHEMA,
            {"dog_id": "buddy"},
        ),
        (
            services.SERVICE_START_GROOMING_SCHEMA,
            {"grooming_type": "bath"},
        ),
    ],
)
def test_given_service_schema_when_required_field_missing_then_raise_invalid(
    schema: object,
    payload: dict[str, object],
) -> None:
    """Service schemas must reject payloads that miss required user input."""
    with pytest.raises(services.vol.Invalid):
        schema(payload)


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            services.SERVICE_SEND_NOTIFICATION_SCHEMA,
            {"title": "A", "message": "B", "channels": "mobile"},
        ),
        (
            services.SERVICE_START_GROOMING_SCHEMA,
            {"dog_id": "buddy", "grooming_type": "bath", "groomer": 42},
        ),
    ],
)
def test_given_service_schema_when_payload_types_invalid_then_raise_invalid(
    schema: object,
    payload: dict[str, object],
) -> None:
    """Service schemas should reject invalid datatypes before handler execution."""
    with pytest.raises(services.vol.Invalid):
        schema(payload)


@pytest.mark.parametrize(
    ("payload", "expected_type", "expected_priority"),
    [
        ({"notification_type": "unknown"}, "system_info", "normal"),
        ({"notification_type": []}, "system_info", "normal"),
        ({"priority": "invalid"}, "system_info", "normal"),
        ({"priority": []}, "system_info", "normal"),
    ],
)
@pytest.mark.asyncio
async def test_given_notification_service_when_enum_coercion_fails_then_defaults_used(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
    payload: dict[str, object],
    expected_type: str,
    expected_priority: str,
) -> None:
    """ValueError/TypeError enum paths should not leak exceptions and use defaults."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(return_value="notification-1")
    )
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        notification_manager=notification_manager,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
    )
    runtime_data.coordinator = coordinator
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])
    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    call_data = {"title": "Heads up", "message": "Dinner time", **payload}
    await handler(SimpleNamespace(data=call_data, context=None))

    send_call = notification_manager.async_send_notification.await_args.kwargs
    assert send_call["notification_type"].value == expected_type
    assert send_call["priority"].value == expected_priority
    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["status"] == "success"
    assert last_result["details"]["notification_type"] == expected_type
    assert last_result["details"]["priority"] == expected_priority


@pytest.mark.parametrize(
    "manager_error",
    [ValueError("bad duration"), TypeError("bad payload"), RuntimeError("boom")],
)
@pytest.mark.asyncio
async def test_given_start_grooming_when_manager_raises_then_wrap_and_track(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
    manager_error: Exception,
) -> None:
    """Boundary exceptions in grooming startup should produce stable user errors."""
    data_manager = SimpleNamespace(
        async_start_grooming_session=AsyncMock(side_effect=manager_error)
    )
    runtime_data = service_runtime_factory(
        runtime_managers=SimpleNamespace(
            data_manager=data_manager,
            notification_manager=None,
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
        get_configured_dog_name=runtime_data.coordinator.get_configured_dog_name,
        async_request_refresh=AsyncMock(),
    )
    runtime_data.coordinator = coordinator
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])
    monkeypatch.setattr(
        services,
        "get_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    handler = await _register_services_and_get_handler(
        mock_hass,
        monkeypatch,
        SERVICE_START_GROOMING,
    )

    with pytest.raises(HomeAssistantError, match="Failed to start grooming"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "grooming_type": "bath"},
                context=None,
            )
        )

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["status"] == "error"
    assert last_result["service"] == SERVICE_START_GROOMING
    assert "reminder_attached" in last_result["diagnostics"]["metadata"]
