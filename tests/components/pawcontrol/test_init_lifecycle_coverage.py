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


class _FailingServiceManagerStub:
    """Service manager stub that raises during shutdown."""

    async def async_shutdown(self) -> None:
        raise RuntimeError("shutdown failed")


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
async def test_async_unload_entry_handles_service_manager_shutdown_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generic service manager shutdown errors should be logged and ignored."""
    service_manager = _FailingServiceManagerStub()
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
async def test_async_monitor_background_tasks_handles_restart_and_loop_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restart failures and loop exceptions should be swallowed by monitor."""

    async def _raise_cleanup() -> None:
        raise RuntimeError("cleanup failed")

    async def _raise_stats() -> None:
        raise RuntimeError("stats failed")

    class _DoneTask:
        def done(self) -> bool:
            return True

    garden_manager = SimpleNamespace(
        _cleanup_task=_DoneTask(),
        _stats_update_task=_DoneTask(),
        async_start_cleanup_task=_raise_cleanup,
        async_start_stats_update_task=_raise_stats,
    )
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    sleep_calls = 0

    async def _sleep_then_cancel(_: int) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise ValueError("loop error")
        if sleep_calls > 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("custom_components.pawcontrol.asyncio.sleep", _sleep_then_cancel)

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)


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


@pytest.mark.asyncio
async def test_async_unload_entry_handles_service_manager_shutdown_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown exceptions should be logged and not abort unload."""

    class _FailingServiceManager:
        async def async_shutdown(self) -> None:
            msg = "shutdown failed"
            raise RuntimeError(msg)

    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True, loaded_entries=[object()]),
        data={"pawcontrol": {"service_manager": _FailingServiceManager()}},
    """Unload should ignore non-timeout shutdown errors from service manager."""

    class _BrokenServiceManager:
        async def async_shutdown(self) -> None:
            raise RuntimeError("shutdown failed")

    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True, loaded_entries=[object()]),
        data={"pawcontrol": {"service_manager": _BrokenServiceManager()}},
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
    monkeypatch.setattr("custom_components.pawcontrol.get_runtime_data", lambda *_: None)
    monkeypatch.setattr("custom_components.pawcontrol.pop_runtime_data", lambda *_: None)

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True


@pytest.mark.asyncio
async def test_async_reload_entry_returns_early_when_unload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should stop when unload fails and skip setup."""
    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-id")
    unload_entry = AsyncMock(return_value=False)
    setup_entry = AsyncMock()

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        unload_entry,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        setup_entry,
    )

    assert await pawcontrol_init.async_reload_entry(hass, entry) is None
    unload_entry.assert_awaited_once_with(hass, entry)
    setup_entry.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_reload_entry_completes_after_successful_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should complete when unload and setup both succeed."""
    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-id")
    unload_entry = AsyncMock(return_value=True)
    setup_entry = AsyncMock(return_value=True)

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        unload_entry,
    """Reload should stop immediately if unload fails."""
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=False),
        data={"pawcontrol": {}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    setup_mock = AsyncMock()

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        setup_mock,
    )

    await pawcontrol_init.async_reload_entry(hass, entry)

    setup_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_reload_entry_logs_completion_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should call setup when unload succeeds."""
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
    monkeypatch.setattr("custom_components.pawcontrol.get_runtime_data", lambda *_: None)

    await pawcontrol_init.async_reload_entry(hass, entry)

    setup_mock.assert_not_called()


@pytest.mark.asyncio
async def test_async_reload_entry_logs_success_after_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should complete when unload and setup both succeed."""
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True, loaded_entries=[object()]),
        data={"pawcontrol": {}},
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    setup_mock = AsyncMock(return_value=True)

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
        setup_entry,
    )

    assert await pawcontrol_init.async_reload_entry(hass, entry) is None
    unload_entry.assert_awaited_once_with(hass, entry)
    setup_entry.assert_awaited_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_handles_restart_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restart errors should be swallowed by background monitor safeguards."""

    async def _restart_cleanup() -> None:
        msg = "cleanup restart error"
        raise RuntimeError(msg)

    async def _restart_stats() -> None:
        msg = "stats restart error"
        raise RuntimeError(msg)
        setup_mock,
    )

    await pawcontrol_init.async_reload_entry(hass, entry)
    setup_mock.assert_awaited_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_logs_restart_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restart failures should be handled without stopping monitoring."""

    class _DoneTask:
        def done(self) -> bool:
            return True

    garden_manager = SimpleNamespace(
        _cleanup_task=_DoneTask(),
        _stats_update_task=_DoneTask(),
        async_start_cleanup_task=_restart_cleanup,
        async_start_stats_update_task=_restart_stats,
    async def _raise_restart() -> None:
        raise RuntimeError("restart failed")

    garden_manager = SimpleNamespace(
        _cleanup_task=_DoneTask(),
        _stats_update_task=_DoneTask(),
        async_start_cleanup_task=_raise_restart,
        async_start_stats_update_task=_raise_restart,
    )
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    sleep_calls = 0

    async def _cancel_sleep(_: int) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise asyncio.CancelledError

    monkeypatch.setattr("custom_components.pawcontrol.asyncio.sleep", _cancel_sleep)

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)
    monkeypatch.setattr(
        "custom_components.pawcontrol.asyncio.sleep",
        _cancel_sleep,
    )

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_handles_loop_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected loop errors should be logged and retried."""
    runtime_data = SimpleNamespace(garden_manager=None)
    calls = 0

    async def _sleep(_: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sleep failure")
        raise asyncio.CancelledError

    monkeypatch.setattr("custom_components.pawcontrol.asyncio.sleep", _sleep)

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)
    monkeypatch.setattr("custom_components.pawcontrol.get_runtime_data", lambda *_: None)
    monkeypatch.setattr("custom_components.pawcontrol.pop_runtime_data", lambda *_: None)
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(return_value=True),
    )

    await pawcontrol_init.async_reload_entry(hass, entry)
