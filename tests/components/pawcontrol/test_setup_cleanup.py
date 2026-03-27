"""Tests for setup cleanup helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.pawcontrol.setup import cleanup


@pytest.mark.asyncio
async def test_async_cleanup_runtime_data_runs_all_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Top-level cleanup should execute each helper once in order."""
    runtime_data = SimpleNamespace()
    cancel_monitor = AsyncMock()
    cleanup_managers = AsyncMock()
    remove_listeners = Mock()
    shutdown_core = AsyncMock()
    clear_refs = Mock()

    monkeypatch.setattr(cleanup, "_async_cancel_background_monitor", cancel_monitor)
    monkeypatch.setattr(cleanup, "_async_cleanup_managers", cleanup_managers)
    monkeypatch.setattr(cleanup, "_remove_listeners", remove_listeners)
    monkeypatch.setattr(cleanup, "_async_shutdown_core_managers", shutdown_core)
    monkeypatch.setattr(cleanup, "_clear_coordinator_references", clear_refs)

    await cleanup.async_cleanup_runtime_data(runtime_data)

    cancel_monitor.assert_awaited_once_with(runtime_data)
    cleanup_managers.assert_awaited_once_with(runtime_data)
    remove_listeners.assert_called_once_with(runtime_data)
    shutdown_core.assert_awaited_once_with(runtime_data)
    clear_refs.assert_called_once_with(runtime_data)


@pytest.mark.asyncio
async def test_async_register_cleanup_stores_reload_listener() -> None:
    """Registering cleanup should save and auto-unload the listener."""
    unload_callback = Mock()
    entry = Mock()
    entry.entry_id = "entry-id"
    entry.add_update_listener = Mock(return_value=unload_callback)
    entry.async_on_unload = Mock()
    runtime_data = SimpleNamespace(reload_unsub=None)

    await cleanup.async_register_cleanup(SimpleNamespace(), entry, runtime_data)

    assert runtime_data.reload_unsub is unload_callback
    entry.async_on_unload.assert_called_once_with(unload_callback)


@pytest.mark.asyncio
async def test_async_reload_entry_wrapper_invokes_parent_reload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload wrapper should dispatch to package-level async_reload_entry."""
    reload_entry = AsyncMock()
    monkeypatch.setattr("custom_components.pawcontrol.async_reload_entry", reload_entry)
    wrapper = cleanup._async_reload_entry_wrapper(SimpleNamespace())
    hass = SimpleNamespace()
    entry = SimpleNamespace()

    await wrapper(hass, entry)

    reload_entry.assert_awaited_once_with(hass, entry)


@pytest.mark.asyncio
async def test_async_cancel_background_monitor_handles_cancelled_task() -> None:
    """Cancelled monitor tasks should be cleared without bubbling errors."""
    monitor_task = asyncio.create_task(asyncio.sleep(30))
    runtime_data = SimpleNamespace(background_monitor_task=monitor_task)

    await cleanup._async_cancel_background_monitor(runtime_data)

    assert monitor_task.cancelled()
    assert runtime_data.background_monitor_task is None


@pytest.mark.asyncio
async def test_async_cleanup_managers_invokes_only_present_managers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional managers should only run cleanup when configured."""
    run_method = AsyncMock()
    monkeypatch.setattr(cleanup, "_async_run_manager_method", run_method)
    runtime_data = SimpleNamespace(
        door_sensor_manager=object(),
        geofencing_manager=None,
        garden_manager=object(),
        helper_manager=None,
        script_manager=object(),
    )

    await cleanup._async_cleanup_managers(runtime_data)

    assert run_method.await_count == 3


@pytest.mark.asyncio
async def test_remove_listeners_tolerates_listener_errors() -> None:
    """Listener cleanup should swallow callback failures."""
    runtime_data = SimpleNamespace(
        daily_reset_unsub=Mock(side_effect=RuntimeError("daily")),
        reload_unsub=Mock(side_effect=RuntimeError("reload")),
    )

    cleanup._remove_listeners(runtime_data)

    runtime_data.daily_reset_unsub.assert_called_once()
    runtime_data.reload_unsub.assert_called_once()


@pytest.mark.asyncio
async def test_async_shutdown_core_managers_delegates_to_run_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Core manager shutdown should delegate through the shared helper."""
    run_method = AsyncMock()
    monkeypatch.setattr(cleanup, "_async_run_manager_method", run_method)
    runtime_data = SimpleNamespace(
        coordinator=object(),
        data_manager=object(),
        notification_manager=object(),
        feeding_manager=object(),
        walk_manager=object(),
    )

    await cleanup._async_shutdown_core_managers(runtime_data)

    assert run_method.await_count == 5


def test_clear_coordinator_references_swallows_errors() -> None:
    """Coordinator reference cleanup should not raise on manager errors."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            clear_runtime_managers=Mock(side_effect=RuntimeError)
        )
    )

    cleanup._clear_coordinator_references(runtime_data)


@pytest.mark.asyncio
async def test_async_run_manager_method_covers_error_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager runner should handle startup, timeout, and runtime failures."""
    startup_error_manager = SimpleNamespace(async_cleanup=Mock(side_effect=ValueError))
    await cleanup._async_run_manager_method(
        startup_error_manager,
        "async_cleanup",
        "startup",
        timeout=0.1,
    )

    async def _sleeper() -> None:
        await asyncio.sleep(0.1)

    timeout_manager = SimpleNamespace(async_cleanup=lambda: _sleeper())
    monkeypatch.setattr(
        cleanup.asyncio, "wait_for", AsyncMock(side_effect=TimeoutError)
    )
    await cleanup._async_run_manager_method(
        timeout_manager,
        "async_cleanup",
        "timeout",
        timeout=0.1,
    )

    failing_coro = AsyncMock(side_effect=RuntimeError("boom"))
    failing_manager = SimpleNamespace(async_cleanup=failing_coro)
    monkeypatch.setattr(
        cleanup.asyncio, "wait_for", AsyncMock(side_effect=RuntimeError)
    )
    await cleanup._async_run_manager_method(
        failing_manager,
        "async_cleanup",
        "failure",
        timeout=0.1,
    )


@pytest.mark.asyncio
async def test_async_run_manager_method_returns_for_missing_manager_or_method() -> None:
    """Manager runner should no-op when manager or method is unavailable."""
    await cleanup._async_run_manager_method(
        None,
        "async_cleanup",
        "none-manager",
        timeout=0.1,
    )

    await cleanup._async_run_manager_method(
        SimpleNamespace(),
        "async_cleanup",
        "missing-method",
        timeout=0.1,
    )


@pytest.mark.asyncio
async def test_async_run_manager_method_handles_non_awaitable_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synchronous manager methods should complete without awaiting wait_for."""
    wait_for = AsyncMock()
    monkeypatch.setattr(cleanup.asyncio, "wait_for", wait_for)

    manager = SimpleNamespace(async_cleanup=Mock(return_value=None))
    await cleanup._async_run_manager_method(
        manager,
        "async_cleanup",
        "sync-cleanup",
        timeout=0.1,
    )

    wait_for.assert_not_awaited()
