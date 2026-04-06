"""Extra coverage tests for PawControl integration setup/unload orchestration."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
async def test_async_setup_entry_stores_daily_reset_unsubscriber(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful scheduler setup should populate runtime reset unsubscribe hook."""

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
    unsub = lambda: None
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(async_create_task=lambda coro: asyncio.create_task(coro))

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
        AsyncMock(return_value=unsub),
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
    assert runtime_data.daily_reset_unsub is unsub
    runtime_data.background_monitor_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runtime_data.background_monitor_task


@pytest.mark.asyncio
async def test_async_setup_entry_disables_debug_for_not_ready_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected setup failures should disable debug logging before re-raising."""
    entry = SimpleNamespace(entry_id="entry-id", options={"debug_logging": True})
    hass = SimpleNamespace()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryNotReady("retry")),
    )

    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_setup_entry(hass, entry)

    assert "entry-id" not in pawcontrol_init._DEBUG_LOGGER_ENTRIES


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
