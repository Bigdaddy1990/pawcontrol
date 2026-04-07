"""Focused failure-path unit tests for ``services.py``."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntryState
import pytest

from custom_components.pawcontrol import services
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.exceptions import HomeAssistantError


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
    monkeypatch.setattr(services, "get_runtime_data", lambda _hass, _entry: runtime_data)

    await services.async_setup_services(mock_hass)

    handler = None
    for call in mock_hass.services.async_register.call_args_list:
        if call.args[0] == DOMAIN and call.args[1] == services.SERVICE_SEND_NOTIFICATION:
            handler = call.args[2]
            break

    assert handler is not None

    with pytest.raises(HomeAssistantError, match="Failed to send the PawControl notification"):
        await handler(SimpleNamespace(data={"title": "A", "message": "B"}, context=None))
