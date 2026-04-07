"""Error-path coverage for PawControl services."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntryState
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
async def test_send_notification_service_rejects_missing_coordinator(
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
async def test_send_notification_service_invalid_expires_in_hours_records_error(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid expiry payload should raise validation errors and persist status."""
    runtime_data = SimpleNamespace(performance_stats={})
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=SimpleNamespace(
            notification_manager=SimpleNamespace(async_send_notification=AsyncMock())
        ),
        notification_manager=SimpleNamespace(async_send_notification=AsyncMock()),
        get_dog_config=Mock(return_value={"name": "Buddy"}),
        get_configured_dog_ids=Mock(return_value={"buddy"}),
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
async def test_send_notification_service_wraps_runtime_exception(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected delivery errors should be wrapped and persisted."""
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
async def test_start_grooming_service_aborts_when_data_manager_missing(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing manager should trigger early abort semantics."""
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=SimpleNamespace(data_manager=None),
        get_dog_config=Mock(return_value={"name": "Buddy"}),
        get_configured_dog_ids=Mock(return_value={"buddy"}),
        get_configured_dog_name=Mock(return_value="Buddy"),
    )
    mock_hass.config_entries.async_entries = Mock(return_value=[config_entry])

    runtime_data = SimpleNamespace(performance_stats={}, coordinator=coordinator)
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
async def test_check_feeding_compliance_service_emits_event_on_success(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Success path should fire the user-visible compliance event."""
    runtime_data = SimpleNamespace(performance_stats={})
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
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=SimpleNamespace(
            feeding_manager=feeding_manager,
            notification_manager=None,
        ),
        feeding_manager=feeding_manager,
        notification_manager=None,
        get_dog_config=Mock(return_value={"name": "Buddy"}),
        get_configured_dog_ids=Mock(return_value={"buddy"}),
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
async def test_check_feeding_compliance_service_wraps_unexpected_errors(
    mock_hass: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected manager errors should be wrapped into HomeAssistantError."""
    runtime_data = SimpleNamespace(performance_stats={})
    feeding_manager = SimpleNamespace(
        async_check_feeding_compliance=AsyncMock(side_effect=RuntimeError("api boom"))
    )
    config_entry = SimpleNamespace(state=ConfigEntryState.LOADED, entry_id="entry-1")
    coordinator = SimpleNamespace(
        hass=mock_hass,
        config_entry=config_entry,
        runtime_managers=SimpleNamespace(
            feeding_manager=feeding_manager,
            notification_manager=None,
        ),
        feeding_manager=feeding_manager,
        notification_manager=None,
        get_dog_config=Mock(return_value={"name": "Buddy"}),
        get_configured_dog_ids=Mock(return_value={"buddy"}),
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


def test_record_service_result_returns_early_without_runtime_data() -> None:
    """Runtime-data guard should no-op cleanly for abort branches."""
    services._record_service_result(None, service="send_notification", status="error")


def test_record_service_result_adds_resilience_details_when_rejections_present() -> (
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
