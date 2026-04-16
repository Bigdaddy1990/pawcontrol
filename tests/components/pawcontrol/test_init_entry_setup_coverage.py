"""Lifecycle coverage tests for PawControl config-entry orchestration."""

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pawcontrol_init = importlib.import_module("custom_components.pawcontrol")

from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    PawControlSetupError,
)


class _ConfigEntriesStub:
    def __init__(self, *, unload_ok: bool = True, loaded_entries: int = 2) -> None:
        self.unload_ok = unload_ok
        self.loaded_entries = loaded_entries

    async def async_unload_platforms(
        self, _entry: object, _platforms: tuple[object, ...]
    ) -> bool:
        return self.unload_ok

    def async_loaded_entries(self, _domain: str) -> list[object]:
        return [object() for _ in range(self.loaded_entries)]


class _MockApiNotReadyError(Exception):
    """Test-only API exception mapped to ConfigEntryNotReady."""


class _MockApiAuthError(Exception):
    """Test-only API exception mapped to ConfigEntryAuthFailed."""


@pytest.mark.asyncio
async def test_async_setup_entry_success_forwards_platform_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=lambda: None),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace()

    setup_platforms = AsyncMock()
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: True,
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
        setup_platforms,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        AsyncMock(),
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    setup_platforms.assert_awaited_once_with(hass, entry, runtime_data)


@pytest.mark.asyncio
async def test_async_setup_entry_optional_setup_starts_background_health_monitoring(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-mocked environments should run optional scheduler/task health setup."""
    start_background_tasks = Mock()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            async_start_background_tasks=start_background_tasks
        ),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(async_create_task=lambda coro: asyncio.create_task(coro))
    check_for_issues = AsyncMock()
    monitor_calls: list[object] = []

    async def _monitor(runtime: object) -> None:
        monitor_calls.append(runtime)

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
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
        AsyncMock(return_value="reset-token"),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        _monitor,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        check_for_issues,
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.daily_reset_unsub == "reset-token"
    start_background_tasks.assert_called_once_with()
    check_for_issues.assert_awaited_once_with(hass, entry)
    assert runtime_data.background_monitor_task is not None
    await runtime_data.background_monitor_task
    assert monitor_calls == [runtime_data]


@pytest.mark.asyncio
async def test_async_setup_entry_optional_daily_reset_failure_is_non_critical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional scheduler failures should not fail the overall setup."""
    start_background_tasks = Mock()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            async_start_background_tasks=start_background_tasks
        ),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(async_create_task=lambda coro: asyncio.create_task(coro))
    check_for_issues = AsyncMock()

    async def _monitor(_: object) -> None:
        return None

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
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
        AsyncMock(side_effect=RuntimeError("scheduler failed")),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        _monitor,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        check_for_issues,
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.daily_reset_unsub is None
    start_background_tasks.assert_called_once_with()
    check_for_issues.assert_awaited_once_with(hass, entry)
    assert runtime_data.background_monitor_task is not None
    await runtime_data.background_monitor_task


@pytest.mark.asyncio
async def test_async_setup_entry_optional_daily_reset_none_does_not_store_unsub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing unsubscribe callback should skip runtime storage gracefully."""
    start_background_tasks = Mock()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            async_start_background_tasks=start_background_tasks
        ),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(async_create_task=lambda coro: asyncio.create_task(coro))
    check_for_issues = AsyncMock()

    async def _monitor(_: object) -> None:
        return None

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
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
        AsyncMock(return_value=None),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        _monitor,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        check_for_issues,
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    assert runtime_data.daily_reset_unsub is None
    start_background_tasks.assert_called_once_with()
    check_for_issues.assert_awaited_once_with(hass, entry)
    assert runtime_data.background_monitor_task is not None
    await runtime_data.background_monitor_task


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_error", "expected_exc"),
    [
        (ConfigEntryNotReady("network timeout"), ConfigEntryNotReady),
        (ConfigEntryAuthFailed("token expired"), ConfigEntryAuthFailed),
    ],
)
async def test_async_setup_entry_propagates_known_failures(
    monkeypatch: pytest.MonkeyPatch,
    setup_error: Exception,
    expected_exc: type[Exception],
) -> None:
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=setup_error),
    )

    with pytest.raises(expected_exc):
        await pawcontrol_init.async_setup_entry(
            SimpleNamespace(), SimpleNamespace(entry_id="id", options={})
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("setup_error", "expected_exception"),
    [
        (ConfigEntryNotReady("retry"), ConfigEntryNotReady),
        (RuntimeError("boom"), PawControlSetupError),
    ],
)
async def test_async_setup_entry_disables_debug_logging_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    setup_error: Exception,
    expected_exception: type[Exception],
) -> None:
    """Any setup failure should restore logger level when debug logging was enabled."""
    disable_debug = Mock()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_enable_debug_logging",
        lambda _entry: True,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_disable_debug_logging",
        disable_debug,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=setup_error),
    )

    with pytest.raises(expected_exception):
        await pawcontrol_init.async_setup_entry(
            SimpleNamespace(), SimpleNamespace(entry_id="entry-id", options={})
        )

    disable_debug.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("api_error", "mapped_error"),
    [
        (_MockApiNotReadyError("api offline"), ConfigEntryNotReady),
        (_MockApiAuthError("invalid token"), ConfigEntryAuthFailed),
    ],
)
async def test_async_setup_entry_propagates_mock_api_mapped_exceptions(
    monkeypatch: pytest.MonkeyPatch,
    api_error: Exception,
    mapped_error: type[Exception],
) -> None:
    """Setup should preserve mapped setup exceptions from API bootstrap layers."""
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace()
    runtime_data = SimpleNamespace()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: True,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        AsyncMock(side_effect=api_error),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "store_runtime_data",
        lambda *_: runtime_data,
    )

    if mapped_error is ConfigEntryNotReady:
        monkeypatch.setitem(
            pawcontrol_init.async_setup_entry.__globals__,
            "async_initialize_managers",
            AsyncMock(side_effect=ConfigEntryNotReady(str(api_error))),
        )
    else:
        monkeypatch.setitem(
            pawcontrol_init.async_setup_entry.__globals__,
            "async_initialize_managers",
            AsyncMock(side_effect=ConfigEntryAuthFailed(str(api_error))),
        )

    with pytest.raises(mapped_error):
        await pawcontrol_init.async_setup_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_setup_entry_rolls_back_partial_initialization_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_data = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace()
    pop_calls: list[tuple[object, object]] = []

    unregister_webhook = AsyncMock()
    unregister_mqtt = AsyncMock()
    cleanup_runtime = AsyncMock()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: True,
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
        "pop_runtime_data",
        lambda *args: pop_calls.append(args),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_unregister_entry_webhook",
        unregister_webhook,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_unregister_entry_mqtt",
        unregister_mqtt,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_cleanup_runtime_data",
        cleanup_runtime,
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
        AsyncMock(side_effect=RuntimeError("platform failed")),
    )

    with pytest.raises(PawControlSetupError):
        await pawcontrol_init.async_setup_entry(hass, entry)

    unregister_mqtt.assert_awaited_once_with(hass, entry)
    unregister_webhook.assert_awaited_once_with(hass, entry)
    cleanup_runtime.assert_awaited_once_with(runtime_data)
    assert pop_calls == [(hass, entry)]


@pytest.mark.asyncio
async def test_async_unload_entry_cleans_runtime_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_data = SimpleNamespace(
        dogs=[{"modules": {"gps": True}}], entity_profile="gps_focus"
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True), data={"pawcontrol": {}}
    )
    pop_calls: list[tuple[object, object]] = []
    cleanup_runtime = AsyncMock()

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
        cleanup_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        lambda *args: pop_calls.append(args),
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    cleanup_runtime.assert_awaited_once_with(runtime_data)
    assert pop_calls == [(hass, entry)]


@pytest.mark.asyncio
async def test_async_unload_entry_runs_platform_cleanup_and_manager_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload must clean listeners/coordinator resources and remove entities."""
    async_unload_platforms = AsyncMock(return_value=True)
    runtime_data = SimpleNamespace(
        dogs=[{"modules": {"gps": True, "health": True}}],
        entity_profile="standard",
    )
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_unload_platforms=async_unload_platforms,
            async_loaded_entries=lambda _domain: [object(), object()],
        ),
        data={"pawcontrol": {}},
    )

    cleanup_runtime = AsyncMock()
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
        cleanup_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        lambda *_: None,
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    assert async_unload_platforms.await_count == 1
    cleanup_runtime.assert_awaited_once_with(runtime_data)


@pytest.mark.asyncio
async def test_async_reload_entry_is_idempotent_when_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = SimpleNamespace(entry_id="entry-id", data={}, options={})
    hass = SimpleNamespace()
    unload = AsyncMock(return_value=True)
    setup = AsyncMock(return_value=True)

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__, "async_unload_entry", unload
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__, "async_setup_entry", setup
    )

    assert await pawcontrol_init.async_reload_entry(hass, entry) is None
    assert await pawcontrol_init.async_reload_entry(hass, entry) is None
    assert unload.await_count == 2
    assert setup.await_count == 2


@pytest.mark.asyncio
async def test_options_update_listener_wrapper_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated options-update callbacks should always trigger safe reload."""
    from custom_components.pawcontrol.setup.cleanup import _async_reload_entry_wrapper

    hass = SimpleNamespace()
    entry = SimpleNamespace(entry_id="entry-id")
    reload_entry = AsyncMock(return_value=None)
    monkeypatch.setattr("custom_components.pawcontrol.async_reload_entry", reload_entry)

    update_listener = _async_reload_entry_wrapper(hass)
    await update_listener(hass, entry)
    await update_listener(hass, entry)

    assert reload_entry.await_count == 2


@pytest.mark.asyncio
async def test_setup_entry_success_forwards_platforms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful setup should initialize coordinator flow and forward platforms."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=lambda: None),
        helper_manager=SimpleNamespace(get_helper_count=lambda: 0),
        door_sensor_manager=SimpleNamespace(get_configured_dogs=lambda: []),
        geofencing_manager=SimpleNamespace(is_enabled=lambda: False),
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace()

    initialize_managers = AsyncMock(return_value=runtime_data)
    setup_platforms = AsyncMock()
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(return_value=([{"id": "dog-1"}], "standard", [])),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: True,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        initialize_managers,
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
        setup_platforms,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        AsyncMock(),
    )

    assert await pawcontrol_init.async_setup_entry(hass, entry) is True
    initialize_managers.assert_awaited_once()
    setup_platforms.assert_awaited_once_with(hass, entry, runtime_data)


@pytest.mark.asyncio
async def test_setup_entry_not_ready_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Temporary API bootstrap errors should propagate as not-ready."""
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryNotReady("api temporarily unavailable")),
    )

    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_setup_entry(
            SimpleNamespace(), SimpleNamespace(entry_id="id", options={})
        )


@pytest.mark.asyncio
async def test_setup_entry_auth_failed_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authentication bootstrap errors should propagate as auth failed."""
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryAuthFailed("invalid credentials")),
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await pawcontrol_init.async_setup_entry(
            SimpleNamespace(), SimpleNamespace(entry_id="id", options={})
        )


@pytest.mark.asyncio
async def test_unload_entry_success_cleans_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Successful unload should cleanup listeners/tasks/runtime resources."""
    runtime_data = SimpleNamespace(
        dogs=[{"modules": {"gps": True}}],
        entity_profile="standard",
    )
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=True),
        data={"pawcontrol": {}},
    )
    cleanup_runtime = AsyncMock()
    pop_runtime_data_calls: list[tuple[object, object]] = []

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
        cleanup_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        lambda *args: pop_runtime_data_calls.append(args),
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    cleanup_runtime.assert_awaited_once_with(runtime_data)
    assert pop_runtime_data_calls == [(hass, entry)]


@pytest.mark.asyncio
async def test_unload_entry_failure_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should fail robustly when platform unload reports an error."""
    entry = SimpleNamespace(entry_id="entry-id", options={}, data={})
    hass = SimpleNamespace(
        config_entries=_ConfigEntriesStub(unload_ok=False),
        data={"pawcontrol": {}},
    )
    cleanup_runtime = AsyncMock()

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
        lambda *_: SimpleNamespace(dogs=[], entity_profile="standard"),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_cleanup_runtime_data",
        cleanup_runtime,
    )

    assert await pawcontrol_init.async_unload_entry(hass, entry) is False
    cleanup_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_reload_entry_reinitializes_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should perform clean unload/setup re-initialization."""
    entry = SimpleNamespace(entry_id="entry-id", options={"profile": "advanced"})
    hass = SimpleNamespace()
    unload_entry = AsyncMock(return_value=True)
    setup_entry = AsyncMock(return_value=True)

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
    setup_entry.assert_awaited_once_with(hass, entry)
