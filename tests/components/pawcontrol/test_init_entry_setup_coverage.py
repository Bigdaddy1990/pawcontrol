"""Extra coverage tests for PawControl integration setup/unload orchestration."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.exceptions import PawControlSetupError
from homeassistant.exceptions import ConfigEntryNotReady


class _ConfigEntriesStub:
    """Config entries stub capturing unload arguments."""

    def __init__(self) -> None:
        self.unload_calls: list[tuple[object, tuple[object, ...]]] = []

    async def async_unload_platforms(
        self, entry: object, platforms: tuple[object, ...]
    ) -> bool:
        self.unload_calls.append((entry, platforms))
        return True

    def async_loaded_entries(self, _domain: str) -> list[object]:
        return [object(), object()]


class _SingleEntryConfigEntriesStub(_ConfigEntriesStub):
    """Config entries stub that reports one loaded entry."""

    def async_loaded_entries(self, _domain: str) -> list[object]:
        return [object()]


@pytest.mark.asyncio
async def test_async_setup_entry_wraps_unexpected_errors_and_disables_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected setup exceptions should become ``PawControlSetupError``."""
    entry = SimpleNamespace(entry_id="entry-id", options={"debug_logging": True})
    hass = SimpleNamespace()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(PawControlSetupError, match="Unexpected setup failure"):
        await pawcontrol_init.async_setup_entry(hass, entry)

    assert "entry-id" not in pawcontrol_init._DEBUG_LOGGER_ENTRIES


@pytest.mark.asyncio
async def test_async_setup_entry_ignores_daily_reset_scheduler_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily scheduler failures are non-critical and must not fail setup."""

    class _Coordinator:
        def __init__(self) -> None:
            self.started = False

        def async_start_background_tasks(self) -> None:
            self.started = True

    class _HelperManager:
        @staticmethod
        def get_helper_count() -> int:
            return 1

    class _DoorSensorManager:
        @staticmethod
        def get_configured_dogs() -> list[str]:
            return ["dog"]

    class _GeoFencingManager:
        @staticmethod
        def is_enabled() -> bool:
            return True

    runtime_data = SimpleNamespace(
        coordinator=_Coordinator(),
        helper_manager=_HelperManager(),
        door_sensor_manager=_DoorSensorManager(),
        geofencing_manager=_GeoFencingManager(),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )

    created_tasks: list[asyncio.Task[None]] = []

    def _create_task(coro: object) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        created_tasks.append(task)
        return task

    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(async_create_task=_create_task)

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: False,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        AsyncMock(return_value=runtime_data),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "store_runtime_data",
        lambda *_: None,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_platforms",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_daily_reset_scheduler",
        AsyncMock(side_effect=RuntimeError("scheduler down")),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        AsyncMock(),
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.coordinator.started is True
    assert runtime_data.daily_reset_unsub is None

    for task in created_tasks:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_async_setup_entry_stores_daily_reset_callback_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Daily reset callback should be stored when scheduler setup succeeds."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=lambda: None),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
async def test_async_setup_entry_stores_daily_reset_unsubscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful scheduler setup should populate runtime reset unsubscribe hook."""
async def test_async_setup_entry_tracks_daily_reset_unsubscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful scheduler setup should persist the returned unsubscribe callback."""

    class _Coordinator:
        def async_start_background_tasks(self) -> None:
            return None

    runtime_data = SimpleNamespace(
        coordinator=_Coordinator(),
        helper_manager=None,
        door_sensor_manager=None,
        geofencing_manager=None,
        daily_reset_unsub=None,
        background_monitor_task=None,
    )

    reset_unsub = object()
    created_tasks: list[asyncio.Task[None]] = []

    def _create_task(coro: object) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        created_tasks.append(task)
        return task

    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(async_create_task=_create_task)
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(async_create_task=lambda coro: asyncio.create_task(coro))
    reset_unsub = lambda: None

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: False,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        AsyncMock(return_value=runtime_data),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "store_runtime_data",
        lambda *_: None,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_platforms",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_daily_reset_scheduler",
        AsyncMock(return_value=reset_unsub),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        AsyncMock(),
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.daily_reset_unsub is reset_unsub

    for task in created_tasks:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_async_setup_entry_preserves_known_errors_and_disables_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known setup exceptions should be re-raised without wrapper conversion."""
    entry = SimpleNamespace(entry_id="entry-id", options={"debug_logging": True})

@pytest.mark.asyncio
async def test_async_setup_entry_disables_debug_on_known_setup_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known setup exceptions should still clear debug logging state."""
    entry = SimpleNamespace(entry_id="debug-entry", options={"debug_logging": True})
    hass = SimpleNamespace()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryNotReady("try later")),
        AsyncMock(side_effect=ConfigEntryNotReady("retry later")),
    )

    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_setup_entry(hass, entry)

    assert "entry-id" not in pawcontrol_init._DEBUG_LOGGER_ENTRIES
    assert "debug-entry" not in pawcontrol_init._DEBUG_LOGGER_ENTRIES


@pytest.mark.asyncio
async def test_async_unload_entry_uses_runtime_profile_platform_subset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should use active profile/module platform selection."""
    config_entries = _ConfigEntriesStub()
    runtime_data = SimpleNamespace(
        dogs=[{"modules": {"gps": True}}],
        entity_profile="gps_focus",
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(config_entries=config_entries, data={"pawcontrol": {}})

    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "get_runtime_data",
        lambda *_: runtime_data,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_cleanup_runtime_data",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        lambda *_: None,
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    assert config_entries.unload_calls
    _entry, platforms = config_entries.unload_calls[0]
    assert platforms == pawcontrol_init.get_platforms_for_profile_and_modules(
        runtime_data.dogs,
        runtime_data.entity_profile,
    )


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_restarts_failed_garden_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monitor should restart finished garden tasks and handle cancellation."""
    restart_cleanup = AsyncMock()
    restart_stats = AsyncMock()

    done_task = asyncio.get_running_loop().create_future()
    done_task.set_result(None)

    garden_manager = SimpleNamespace(
        _cleanup_task=done_task,
        _stats_update_task=done_task,
        async_start_cleanup_task=restart_cleanup,
        async_start_stats_update_task=restart_stats,
    )

    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    sleep_mock = AsyncMock(side_effect=[None, asyncio.CancelledError])
    monkeypatch.setitem(
        pawcontrol_init._async_monitor_background_tasks.__globals__,
        "asyncio",
        SimpleNamespace(sleep=sleep_mock, CancelledError=asyncio.CancelledError),
    )

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)

    assert restart_cleanup.await_count >= 1
    assert restart_stats.await_count >= 1


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_logs_restart_errors_and_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Restart hook failures and loop-level errors should not crash the monitor."""
async def test_async_monitor_background_tasks_logs_restart_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monitor should swallow restart failures and keep looping."""
    done_task = asyncio.get_running_loop().create_future()
    done_task.set_result(None)
    garden_manager = SimpleNamespace(
        _cleanup_task=done_task,
        _stats_update_task=done_task,
        async_start_cleanup_task=AsyncMock(side_effect=RuntimeError("cleanup failed")),
        async_start_stats_update_task=AsyncMock(
            side_effect=RuntimeError("stats failed")
        ),
        async_start_cleanup_task=AsyncMock(side_effect=RuntimeError("cleanup boom")),
        async_start_stats_update_task=AsyncMock(side_effect=RuntimeError("stats boom")),
    )
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    sleep_mock = AsyncMock(
        side_effect=[RuntimeError("tick failed"), None, asyncio.CancelledError]
        side_effect=[None, RuntimeError("loop boom"), asyncio.CancelledError]
    )
    monkeypatch.setitem(
        pawcontrol_init._async_monitor_background_tasks.__globals__,
        "asyncio",
        SimpleNamespace(sleep=sleep_mock, CancelledError=asyncio.CancelledError),
    )

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)


@pytest.mark.asyncio
async def test_async_unload_entry_logs_service_shutdown_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected shutdown errors should be swallowed during unload."""
    config_entries = _SingleEntryConfigEntriesStub()
    service_manager = SimpleNamespace(
        async_shutdown=AsyncMock(side_effect=RuntimeError("boom"))
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(
        config_entries=config_entries,
        data={"pawcontrol": {"service_manager": service_manager}},
    )

async def test_async_unload_entry_returns_false_when_platform_unload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should short-circuit when Home Assistant unload fails."""

    class _FailingConfigEntries:
        async def async_unload_platforms(
            self, _entry: object, _platforms: tuple[object, ...]
        ) -> bool:
            return False

        def async_loaded_entries(self, _domain: str) -> list[object]:
            return [object()]

    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(
        config_entries=_FailingConfigEntries(),
        data={"pawcontrol": {}},
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "get_runtime_data",
        lambda *_: None,
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is False


@pytest.mark.asyncio
async def test_async_unload_entry_handles_service_manager_shutdown_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should continue when service manager shutdown errors."""

    class _ConfigEntriesSingleLoaded:
        async def async_unload_platforms(
            self, _entry: object, _platforms: tuple[object, ...]
        ) -> bool:
            return True

        def async_loaded_entries(self, _domain: str) -> list[object]:
            return [object()]

    runtime_data = SimpleNamespace(dogs=[], entity_profile="standard")
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    service_manager = SimpleNamespace(
        async_shutdown=AsyncMock(side_effect=RuntimeError("shutdown boom"))
    )
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesSingleLoaded(),
        data={"pawcontrol": {"service_manager": service_manager}},
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_webhook",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unregister_entry_mqtt",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_unload_external_bindings",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "get_runtime_data",
        lambda *_: None,
        lambda *_: runtime_data,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_cleanup_runtime_data",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        lambda *_: None,
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True


@pytest.mark.asyncio
async def test_async_reload_entry_stops_when_unload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should return early and skip setup after unload failure."""
    entry = SimpleNamespace(entry_id="entry-id")
    hass = SimpleNamespace()
async def test_async_reload_entry_returns_when_unload_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should return early without setup if unload fails."""
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    setup_mock = AsyncMock()
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        AsyncMock(return_value=False),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        setup_mock,
    )

    await pawcontrol_init.async_reload_entry(hass, entry)

    setup_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_reload_entry_logs_duration_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful reload should execute setup and completion logging branch."""
    entry = SimpleNamespace(entry_id="entry-id")
    hass = SimpleNamespace()
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(return_value=True),
    )

    await pawcontrol_init.async_reload_entry(hass, entry)
    await pawcontrol_init.async_reload_entry(SimpleNamespace(), entry)

    setup_mock.assert_not_awaited()
