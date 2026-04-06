"""Additional lifecycle branch coverage for integration entry orchestration."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol import _should_skip_optional_setup
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed


class _ConfigEntriesStub:
    """Minimal config entries manager for unload tests."""

    def __init__(
        self,
        *,
        unload_ok: bool = True,
        loaded_entries: list[Any] | None = None,
    ) -> None:
        self._unload_ok = unload_ok
        self._loaded_entries = loaded_entries if loaded_entries is not None else []

    async def async_unload_platforms(self, entry: Any, platforms: Any) -> bool:
        return self._unload_ok

    def async_loaded_entries(self, domain: str) -> list[Any]:
        return self._loaded_entries


class _ServiceManagerStub:
    """Service manager stub exposing async shutdown."""

    async def async_shutdown(self) -> None:
        return None


def test_should_skip_optional_setup_without_services() -> None:
    """Missing hass.services indicates a mocked environment."""
    hass = SimpleNamespace()

    assert _should_skip_optional_setup(hass) is True


def test_should_skip_optional_setup_with_mocked_services_module() -> None:
    """Services class from unittest.mock should force optional setup skip."""
    services = type("Services", (), {"__module__": "unittest.mock"})()
    hass = SimpleNamespace(services=services)

    assert _should_skip_optional_setup(hass) is True


def test_should_skip_optional_setup_with_mocked_async_call() -> None:
    """Mocked async_call callable should also force optional setup skip."""

    class _Services:
        __module__ = "homeassistant.core"

        def __init__(self) -> None:
            self.async_call = type(
                "MockedAsyncCall",
                (),
                {"__module__": "unittest.mock"},
            )()

    hass = SimpleNamespace(services=_Services())

    assert _should_skip_optional_setup(hass) is True


@pytest.mark.asyncio
async def test_async_unload_entry_returns_false_when_platform_unload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should abort when Home Assistant platform unload fails."""
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=False),
        data={"pawcontrol": {}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is False


@pytest.mark.asyncio
async def test_async_unload_entry_handles_service_manager_shutdown_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts from service manager shutdown should be swallowed."""
    service_manager = _ServiceManagerStub()
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True, loaded_entries=[object()]),
        data={"pawcontrol": {"service_manager": service_manager}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.pop_runtime_data", lambda *_: None
    )

    async def _raise_timeout(awaitable: Any, timeout: int) -> Any:
        raise TimeoutError

    monkeypatch.setattr("custom_components.pawcontrol.asyncio.wait_for", _raise_timeout)

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True


@pytest.mark.asyncio
async def test_async_reload_entry_propagates_not_ready_and_auth_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should surface retriable and auth setup errors as-is."""
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(
            unload_ok=True, loaded_entries=[object(), object()]
        ),
        data={"pawcontrol": {}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.pop_runtime_data", lambda *_: None
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=ConfigEntryNotReady("retry")),
    )
    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_reload_entry(hass, entry)

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=ConfigEntryAuthFailed("auth")),
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await pawcontrol_init.async_reload_entry(hass, entry)


def test_should_skip_optional_setup_returns_false_for_real_services() -> None:
    """Non-mock services should keep optional setup enabled."""

    class _Services:
        __module__ = "homeassistant.core"

        async def async_call(self, *_: Any, **__: Any) -> None:
            return None

    hass = SimpleNamespace(services=_Services())

    assert _should_skip_optional_setup(hass) is False


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_restarts_dead_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background task monitor should restart dead garden tasks once."""
    restart_calls: list[str] = []

    async def _restart_cleanup() -> None:
        restart_calls.append("cleanup")

    async def _restart_stats() -> None:
        restart_calls.append("stats")

    class _DoneTask:
        def done(self) -> bool:
            return True

    garden_manager = SimpleNamespace(
        _cleanup_task=_DoneTask(),
        _stats_update_task=_DoneTask(),
        async_start_cleanup_task=_restart_cleanup,
        async_start_stats_update_task=_restart_stats,
    )
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    sleep_calls = 0

    async def _cancel_sleep(_: int) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr(
        "custom_components.pawcontrol.asyncio.sleep",
        _cancel_sleep,
    )

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)

    assert restart_calls == ["cleanup", "stats"]


@pytest.mark.asyncio
async def test_async_reload_entry_logs_and_raises_unexpected_setup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected setup errors should bubble up unchanged during reload."""
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True, loaded_entries=[object()]),
        data={"pawcontrol": {}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})

    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.get_runtime_data", lambda *_: None
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.pop_runtime_data", lambda *_: None
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await pawcontrol_init.async_reload_entry(hass, entry)
