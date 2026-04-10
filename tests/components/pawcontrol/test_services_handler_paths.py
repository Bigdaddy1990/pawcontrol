"""Dedicated service-handler path coverage for PawControl services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.core import Context
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import (
    DOMAIN,
    EVENT_FEEDING_COMPLIANCE_CHECKED,
    SERVICE_ADD_FEEDING,
    SERVICE_CHECK_FEEDING_COMPLIANCE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_START_GROOMING,
)
from custom_components.pawcontrol.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
)


async def _register_service_handler(
    hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_name: str,
):
    """Register services and return the wrapped handler for ``service_name``."""
    hass.data = {}
    hass.services.async_register = Mock()
    hass.services.has_service = Mock(return_value=False)
    hass.config_entries.async_entries = Mock(return_value=[])
    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)

    await services.async_setup_services(hass)

    for call in hass.services.async_register.call_args_list:
        domain, registered_service, handler = call.args[:3]
        if domain == DOMAIN and registered_service == service_name:
            return handler

    raise AssertionError(f"Service handler {service_name} was not registered")


def _build_runtime(
    *,
    mock_hass: SimpleNamespace,
    service_runtime_factory,
    runtime_managers: SimpleNamespace,
    dog_ids: set[str] | None = None,
    dog_config: dict[str, object] | None = None,
):
    runtime_data = service_runtime_factory(
        runtime_managers=runtime_managers,
        dog_ids=dog_ids,
        dog_config=dog_config,
    )
    config_entry = runtime_data.coordinator.config_entry
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=runtime_data.coordinator.runtime_managers,
        notification_manager=getattr(runtime_managers, "notification_manager", None),
        feeding_manager=getattr(runtime_managers, "feeding_manager", None),
        data_manager=getattr(runtime_managers, "data_manager", None),
        get_dog_config=runtime_data.coordinator.get_dog_config,
        get_configured_dog_ids=runtime_data.coordinator.get_configured_dog_ids,
        get_configured_dog_name=runtime_data.coordinator.get_configured_dog_name,
        async_request_refresh=AsyncMock(),
    )
    runtime_data.coordinator = coordinator
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])
    return runtime_data, coordinator


@pytest.mark.asyncio
async def test_async_setup_services_successfully_registers_target_handlers(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async_setup_services success-path should register all target handlers."""
    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.has_service = Mock(return_value=False)
    mock_hass.config_entries.async_entries = Mock(return_value=[])
    monkeypatch.setattr(services, "async_dispatcher_connect", lambda *_: lambda: None)

    await services.async_setup_services(mock_hass)

    registered = {
        call.args[1] for call in mock_hass.services.async_register.call_args_list
    }
    assert services.SERVICE_SEND_NOTIFICATION in registered
    assert SERVICE_CHECK_FEEDING_COMPLIANCE in registered
    assert SERVICE_START_GROOMING in registered


@pytest.mark.asyncio
async def test_async_setup_services_propagates_dispatcher_exception(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundary failures in HA dispatcher wiring should bubble up."""
    mock_hass.data = {}
    mock_hass.services.async_register = Mock()
    mock_hass.services.has_service = Mock(return_value=False)
    mock_hass.config_entries.async_entries = Mock(return_value=[])
    monkeypatch.setattr(
        services,
        "async_dispatcher_connect",
        Mock(side_effect=RuntimeError("dispatcher offline")),
    )

    with pytest.raises(RuntimeError, match="dispatcher offline"):
        await services.async_setup_services(mock_hass)


def test_async_setup_services_exposes_validation_schemas() -> None:
    """Schema validation errors are surfaced through setup-registered schema objects."""
    with pytest.raises(services.vol.Invalid):
        services.SERVICE_SEND_NOTIFICATION_SCHEMA({"title": "only-title"})


def test_record_service_result_success_path_sets_last_result() -> None:
    """_record_service_result should persist successful telemetry payloads."""
    runtime_data = SimpleNamespace(performance_stats={})

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="success",
        dog_id="buddy",
        details={"kind": "ok"},
    )

    last_result = runtime_data.performance_stats["last_service_result"]
    assert last_result["service"] == "send_notification"
    assert last_result["status"] == "success"
    assert last_result["dog_id"] == "buddy"


def test_record_service_result_sanitizes_invalid_guard_inputs() -> None:
    """Non-ServiceGuard inputs should be ignored instead of failing."""
    runtime_data = SimpleNamespace(performance_stats={})

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="success",
        guard=("bad", 123, None),
    )

    assert runtime_data.performance_stats["last_service_result"]["status"] == "success"
    assert "guard" not in runtime_data.performance_stats["last_service_result"]


def test_record_service_result_exception_path_rejection_metrics_in_details() -> None:
    """Rejection metrics should enrich details on error paths."""
    runtime_data = SimpleNamespace(
        performance_stats={"resilience_summary": {"rejected_call_count": 3}},
    )

    services._record_service_result(
        runtime_data,
        service="send_notification",
        status="error",
        details={"source": "test"},
    )

    details = runtime_data.performance_stats["last_service_result"]["details"]
    assert details["resilience"]["rejected_call_count"] == 3


def test_record_service_result_abort_path_runtime_missing_returns_early() -> None:
    """Missing runtime data is treated as abort/no-op semantics."""
    services._record_service_result(None, service="send_notification", status="error")


@pytest.mark.asyncio
async def test_send_notification_service_success_path(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """send_notification_service should send and persist successful details."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(return_value="notif-1"),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )

    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    await handler(
        SimpleNamespace(data={"title": "Hi", "message": "Dinner"}, context=None)
    )

    assert runtime_data.performance_stats["last_service_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_send_notification_service_validation_error_input(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Invalid expires_in_hours should raise a service validation error."""
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(
            notification_manager=SimpleNamespace(async_send_notification=AsyncMock()),
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    with pytest.raises(
        ServiceValidationError, match="expires_in_hours must be a number"
    ):
        await handler(
            SimpleNamespace(
                data={
                    "title": "Hi",
                    "message": "Dinner",
                    "dog_id": "buddy",
                    "expires_in_hours": "soon",
                },
                context=None,
            )
        )


@pytest.mark.asyncio
async def test_send_notification_service_exception_path_wraps_boundary_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Unexpected API failures should be wrapped into HomeAssistantError."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(side_effect=RuntimeError("smtp down")),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    with pytest.raises(
        HomeAssistantError, match="Failed to send the PawControl notification"
    ):
        await handler(
            SimpleNamespace(data={"title": "Hi", "message": "Dinner"}, context=None)
        )


@pytest.mark.asyncio
async def test_send_notification_service_abort_when_manager_missing(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Missing notification manager should abort early with user-facing error."""
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(notification_manager=None),
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )

    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        services.SERVICE_SEND_NOTIFICATION,
    )

    with pytest.raises(
        HomeAssistantError, match="notification manager is not ready yet"
    ):
        await handler(
            SimpleNamespace(data={"title": "Hi", "message": "Dinner"}, context=None)
        )


@pytest.mark.asyncio
async def test_check_feeding_compliance_service_success_and_abort_notification(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Success path with notify_on_issues=False should skip summary notifications."""
    feeding_result = {
        "status": "completed",
        "compliance_score": 91,
        "compliance_rate": 0.91,
        "days_analyzed": 7,
        "days_with_issues": 1,
        "compliance_issues": [],
        "missed_meals": [],
    }
    feeding_manager = SimpleNamespace(
        async_check_feeding_compliance=AsyncMock(return_value=feeding_result),
    )
    notification_manager = SimpleNamespace(
        async_send_feeding_compliance_summary=AsyncMock(return_value="notif-2"),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(
            feeding_manager=feeding_manager,
            notification_manager=notification_manager,
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    mock_hass.config = SimpleNamespace(language="de")

    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    monkeypatch.setattr(services, "async_publish_feeding_compliance_issue", AsyncMock())
    monkeypatch.setattr(
        services,
        "async_build_feeding_compliance_summary",
        AsyncMock(return_value={"title": "OK", "message": "Alles gut"}),
    )

    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        SERVICE_CHECK_FEEDING_COMPLIANCE,
    )

    await handler(
        SimpleNamespace(
            data={"dog_id": "buddy", "notify_on_issues": False},
            context=Context(context_id="ctx-1", user_id="user-1"),
        )
    )

    notification_manager.async_send_feeding_compliance_summary.assert_not_called()
    assert (
        mock_hass.bus.async_fire.call_args.args[0] == EVENT_FEEDING_COMPLIANCE_CHECKED
    )


@pytest.mark.asyncio
async def test_check_feeding_compliance_service_validation_error_unknown_dog(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Unknown dog IDs should raise a validation error."""
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(feeding_manager=SimpleNamespace()),
        dog_ids={"buddy"},
        dog_config=None,
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        SERVICE_CHECK_FEEDING_COMPLIANCE,
    )

    with pytest.raises(ServiceValidationError, match="Unknown dog_id"):
        await handler(SimpleNamespace(data={"dog_id": "ghost"}, context=None))


@pytest.mark.asyncio
async def test_check_feeding_compliance_service_exception_path(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Boundary exceptions from feeding manager should be wrapped."""
    feeding_manager = SimpleNamespace(
        async_check_feeding_compliance=AsyncMock(side_effect=RuntimeError("api down")),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(feeding_manager=feeding_manager),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass,
        monkeypatch,
        SERVICE_CHECK_FEEDING_COMPLIANCE,
    )

    with pytest.raises(HomeAssistantError, match="Failed to check feeding compliance"):
        await handler(SimpleNamespace(data={"dog_id": "buddy"}, context=None))


@pytest.mark.asyncio
async def test_start_grooming_service_success_path(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """start_grooming_service should start a session and persist success details."""
    data_manager = SimpleNamespace(
        async_start_grooming_session=AsyncMock(return_value="session-1"),
    )
    runtime_data, coordinator = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(
            data_manager=data_manager, notification_manager=None
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_START_GROOMING
    )

    await handler(
        SimpleNamespace(data={"dog_id": "buddy", "grooming_type": "bath"}, context=None)
    )

    coordinator.async_request_refresh.assert_awaited_once()
    assert runtime_data.performance_stats["last_service_result"]["status"] == "success"


@pytest.mark.asyncio
async def test_start_grooming_service_validation_error_unknown_dog(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Unknown dog IDs should fail fast in grooming service."""
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(data_manager=SimpleNamespace()),
        dog_ids={"buddy"},
        dog_config=None,
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_START_GROOMING
    )

    with pytest.raises(ServiceValidationError, match="Unknown dog_id"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "ghost", "grooming_type": "bath"}, context=None
            )
        )


@pytest.mark.asyncio
async def test_start_grooming_service_exception_path(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Boundary exceptions should be wrapped for grooming startup."""
    data_manager = SimpleNamespace(
        async_start_grooming_session=AsyncMock(side_effect=RuntimeError("db down")),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(
            data_manager=data_manager, notification_manager=None
        ),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_START_GROOMING
    )

    with pytest.raises(HomeAssistantError, match="Failed to start grooming"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "grooming_type": "bath"}, context=None
            )
        )


@pytest.mark.asyncio
async def test_start_grooming_service_abort_when_data_manager_missing(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Missing data manager should abort before calling service boundary."""
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(data_manager=None),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_START_GROOMING
    )

    with pytest.raises(HomeAssistantError, match="data manager is not ready yet"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "grooming_type": "bath"}, context=None
            )
        )


@pytest.mark.asyncio
async def test_send_notification_wrapper_records_error_service_telemetry(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Wrapped handlers should mark failed calls in runtime telemetry."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(side_effect=RuntimeError("smtp offline")),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_SEND_NOTIFICATION
    )

    with pytest.raises(
        HomeAssistantError, match="Failed to send the PawControl notification"
    ):
        await handler(
            SimpleNamespace(data={"title": "Hi", "message": "Dinner"}, context=None)
        )

    telemetry = runtime_data.performance_stats["service_call_telemetry"]
    assert telemetry["total_calls"] == 1
    assert telemetry["error_calls"] == 1
    assert telemetry["success_calls"] == 0
    assert telemetry["error_rate"] == 1.0
    assert telemetry["per_service"][SERVICE_SEND_NOTIFICATION]["error_calls"] == 1


@pytest.mark.asyncio
async def test_send_notification_wrapper_skips_telemetry_when_resolver_fails(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """Telemetry lookup failures should not mask handler success."""
    notification_manager = SimpleNamespace(
        async_send_notification=AsyncMock(return_value="notif-3"),
    )
    runtime_data, _ = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(notification_manager=notification_manager),
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_SEND_NOTIFICATION
    )
    monkeypatch.setattr(
        services, "get_runtime_data", Mock(side_effect=RuntimeError("metrics offline"))
    )

    await handler(
        SimpleNamespace(data={"title": "Hi", "message": "Dinner"}, context=None)
    )

    assert runtime_data.performance_stats["last_service_result"]["status"] == "success"
    assert "service_call_telemetry" not in runtime_data.performance_stats


@pytest.mark.asyncio
async def test_add_feeding_service_propagates_homeassistant_error_without_wrapping(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    service_runtime_factory,
) -> None:
    """HomeAssistantError should pass through central feeding handler unchanged."""
    feeding_manager = SimpleNamespace(
        async_add_feeding=AsyncMock(side_effect=HomeAssistantError("quota exceeded")),
        async_add_feeding_with_medication=AsyncMock(),
    )
    runtime_data, coordinator = _build_runtime(
        mock_hass=mock_hass,
        service_runtime_factory=service_runtime_factory,
        runtime_managers=SimpleNamespace(feeding_manager=feeding_manager),
        dog_ids={"buddy"},
        dog_config={"name": "Buddy"},
    )
    monkeypatch.setattr(
        services, "get_runtime_data", lambda _hass, _entry: runtime_data
    )
    handler = await _register_service_handler(
        mock_hass, monkeypatch, SERVICE_ADD_FEEDING
    )

    with pytest.raises(HomeAssistantError, match="quota exceeded"):
        await handler(
            SimpleNamespace(
                data={"dog_id": "buddy", "amount": 85.0, "meal_type": "breakfast"},
                context=None,
            )
        )

    coordinator.async_request_refresh.assert_not_awaited()
    assert runtime_data.performance_stats["last_service_result"]["status"] == "error"
    assert (
        runtime_data.performance_stats["last_service_result"]["message"]
        == "quota exceeded"
    )


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("false", False),
        ("off", False),
        ("0", False),
        (0, False),
    ],
)
def test_coerce_service_bool_false_branches_are_supported(
    raw_value: object,
    expected: bool,
) -> None:
    """Central boolean coercion should map known false-ish values to False."""
    assert services._coerce_service_bool(raw_value, field="enabled") is expected
