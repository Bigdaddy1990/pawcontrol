"""Tests for platform selection helpers."""

import asyncio
from collections.abc import Mapping
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
import pytest

import custom_components.pawcontrol as pawcontrol_init
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.exceptions import (
    ConfigEntryAuthFailed,
    PawControlSetupError,
)
from custom_components.pawcontrol.types import DogConfigData


def _build_dog_config(
    modules: Mapping[str, bool],
    *,
    dog_id: str = "buddy",
    dog_name: str = "Buddy",
) -> DogConfigData:
    return {
        "dog_id": dog_id,
        "dog_name": dog_name,
        "modules": dict(modules),
    }


def _expected_platforms(*platforms: Platform) -> tuple[Platform, ...]:
    return tuple(sorted(platforms, key=lambda platform: platform.value))


@pytest.fixture(autouse=True)
def _clear_platform_cache() -> None:
    pawcontrol_init._PLATFORM_CACHE.clear()
    yield
    pawcontrol_init._PLATFORM_CACHE.clear()


@pytest.fixture(autouse=True)
def _reset_debug_logging_state() -> None:
    logger = logging.getLogger(pawcontrol_init.__package__)
    original_level = logger.level
    original_default = pawcontrol_init._DEFAULT_LOGGER_LEVEL
    pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()
    yield
    pawcontrol_init._DEBUG_LOGGER_ENTRIES.clear()
    pawcontrol_init._DEFAULT_LOGGER_LEVEL = original_default
    logger.setLevel(original_level)


@pytest.mark.parametrize(
    ("profile", "modules", "expected"),
    [
        (
            "standard",
            {MODULE_GPS: True, MODULE_FEEDING: True},
            _expected_platforms(
                Platform.SENSOR,
                Platform.BUTTON,
                Platform.SWITCH,
                Platform.DEVICE_TRACKER,
                Platform.NUMBER,
                Platform.SELECT,
                Platform.BINARY_SENSOR,
            ),
        ),
        (
            "standard",
            {MODULE_GPS: True, "unknown_module": True},
            _expected_platforms(
                Platform.SENSOR,
                Platform.BUTTON,
                Platform.SWITCH,
                Platform.DEVICE_TRACKER,
                Platform.NUMBER,
                Platform.BINARY_SENSOR,
            ),
        ),
        (
            "gps_focus",
            {MODULE_WALK: True, MODULE_NOTIFICATIONS: True},
            _expected_platforms(
                Platform.SENSOR,
                Platform.BUTTON,
                Platform.NUMBER,
                Platform.SWITCH,
                Platform.BINARY_SENSOR,
            ),
        ),
        (
            "health_focus",
            {MODULE_HEALTH: True},
            _expected_platforms(
                Platform.SENSOR,
                Platform.BUTTON,
                Platform.DATE,
                Platform.NUMBER,
                Platform.TEXT,
            ),
        ),
        (
            "advanced",
            {MODULE_GPS: True, MODULE_HEALTH: True},
            _expected_platforms(
                Platform.SENSOR,
                Platform.BUTTON,
                Platform.DATETIME,
                Platform.DEVICE_TRACKER,
                Platform.NUMBER,
                Platform.BINARY_SENSOR,
                Platform.DATE,
                Platform.TEXT,
            ),
        ),
    ],
)
def test_get_platforms_for_profile_and_modules(
    profile: str,
    modules: Mapping[str, bool],
    expected: tuple[Platform, ...],
) -> None:
    dogs = [_build_dog_config(modules)]

    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        dogs,
        profile,
    )

    assert platforms == expected


def test_get_platforms_cache_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    dogs = [_build_dog_config({MODULE_GPS: True})]
    profile = "standard"
    cache_key = (1, profile, frozenset({MODULE_GPS}))

    now_holder: dict[str, float] = {"now": 0.0}

    def _now() -> float:
        return now_holder["now"]

    monkeypatch.setattr(pawcontrol_init.time, "time", _now)

    first_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        dogs,
        profile,
    )

    cached_platforms, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]
    assert cached_platforms == first_platforms
    assert cached_timestamp == 0.0

    now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS - 1
    second_platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        dogs,
        profile,
    )

    assert second_platforms == first_platforms
    _, cached_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]
    assert cached_timestamp == 0.0

    now_holder["now"] = pawcontrol_init._CACHE_TTL_SECONDS + 1
    pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)
    _, refreshed_timestamp = pawcontrol_init._PLATFORM_CACHE[cache_key]

    assert refreshed_timestamp == now_holder["now"]


def test_get_platforms_cache_key_ignores_unknown_modules() -> None:
    dogs = [_build_dog_config({MODULE_GPS: True, "unknown_module": True})]
    profile = "standard"

    pawcontrol_init.get_platforms_for_profile_and_modules(dogs, profile)

    assert pawcontrol_init._PLATFORM_CACHE
    assert list(pawcontrol_init._PLATFORM_CACHE) == [
        (1, profile, frozenset({MODULE_GPS}))
    ]


def test_get_platforms_for_empty_dogs_config() -> None:
    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        [],
        "standard",
    )

    assert platforms == pawcontrol_init._DEFAULT_PLATFORMS


def test_get_platforms_for_multiple_dogs() -> None:
    dogs = [
        _build_dog_config({MODULE_GPS: True}, dog_id="buddy"),
        _build_dog_config({MODULE_HEALTH: True}, dog_id="lady"),
    ]
    profile = "standard"

    platforms = pawcontrol_init.get_platforms_for_profile_and_modules(
        dogs,
        profile,
    )

    expected = _expected_platforms(
        Platform.SENSOR,
        Platform.BUTTON,
        Platform.SWITCH,
        Platform.DEVICE_TRACKER,
        Platform.NUMBER,
        Platform.DATE,
        Platform.TEXT,
        Platform.BINARY_SENSOR,
    )

    assert platforms == expected


def test_platform_cache_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    max_size = pawcontrol_init._MAX_CACHE_SIZE
    ttl = pawcontrol_init._CACHE_TTL_SECONDS
    now = 1000.0

    monkeypatch.setattr(pawcontrol_init.time, "monotonic", lambda: now)

    for idx in range(max_size + 5):
        timestamp = now - ttl - 1 if idx < 2 else now - ttl + idx
        cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
        pawcontrol_init._PLATFORM_CACHE[cache_key] = (
            (Platform.SENSOR,),
            timestamp,
        )

    pawcontrol_init._cleanup_platform_cache()

    expired_key_one = (0, "standard", frozenset({"module_0"}))
    expired_key_two = (1, "standard", frozenset({"module_1"}))

    assert expired_key_one not in pawcontrol_init._PLATFORM_CACHE
    assert expired_key_two not in pawcontrol_init._PLATFORM_CACHE
    assert len(pawcontrol_init._PLATFORM_CACHE) == max_size
    for idx in range(2, 5):
        cache_key = (idx, "standard", frozenset({f"module_{idx}"}))
        assert cache_key not in pawcontrol_init._PLATFORM_CACHE


def test_platform_cache_cleanup_short_circuits_below_half_capacity() -> None:
    half_capacity = pawcontrol_init._MAX_CACHE_SIZE // 2
    cache_key = (1, "standard", frozenset({MODULE_GPS}))
    pawcontrol_init._PLATFORM_CACHE[cache_key] = ((Platform.SENSOR,), 0.0)

    assert len(pawcontrol_init._PLATFORM_CACHE) < half_capacity
    pawcontrol_init._cleanup_platform_cache()
    assert cache_key in pawcontrol_init._PLATFORM_CACHE


def test_platform_cache_cleanup_uses_wall_clock_for_large_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now_wall = 2_000_000_000.0
    now_monotonic = 1_000.0
    ttl = pawcontrol_init._CACHE_TTL_SECONDS

    monkeypatch.setattr(pawcontrol_init.time, "time", lambda: now_wall)
    monkeypatch.setattr(pawcontrol_init.time, "monotonic", lambda: now_monotonic)

    for idx in range(pawcontrol_init._MAX_CACHE_SIZE // 2):
        key = (idx, "standard", frozenset({f"module_{idx}"}))
        pawcontrol_init._PLATFORM_CACHE[key] = ((Platform.SENSOR,), now_monotonic)

    wall_expired_key = (9999, "standard", frozenset({"wall_expired"}))
    pawcontrol_init._PLATFORM_CACHE[wall_expired_key] = (
        (Platform.SWITCH,),
        now_wall - ttl - 1,
    )

    pawcontrol_init._cleanup_platform_cache()

    assert wall_expired_key not in pawcontrol_init._PLATFORM_CACHE


def test_enable_and_disable_debug_logging_restores_logger_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_logger = Mock()
    package_logger.level = logging.INFO

    monkeypatch.setattr(
        pawcontrol_init.logging, "getLogger", lambda *_args: package_logger
    )

    entry = SimpleNamespace(entry_id="entry-debug", options={"debug_logging": True})

    assert pawcontrol_init._enable_debug_logging(entry) is True
    assert package_logger.setLevel.call_args_list[0].args == (logging.DEBUG,)

    pawcontrol_init._disable_debug_logging(entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.INFO,)


def test_disable_debug_logging_keeps_debug_when_other_entries_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_logger = Mock()
    package_logger.level = logging.WARNING

    monkeypatch.setattr(
        pawcontrol_init.logging, "getLogger", lambda *_args: package_logger
    )

    first_entry = SimpleNamespace(entry_id="entry-1", options={"debug_logging": True})
    second_entry = SimpleNamespace(entry_id="entry-2", options={"debug_logging": True})

    assert pawcontrol_init._enable_debug_logging(first_entry) is True
    assert pawcontrol_init._enable_debug_logging(second_entry) is True

    pawcontrol_init._disable_debug_logging(first_entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.DEBUG,)

    pawcontrol_init._disable_debug_logging(second_entry)
    assert package_logger.setLevel.call_args_list[-1].args == (logging.WARNING,)


@pytest.mark.asyncio
async def test_async_unload_entry_clears_platform_cache(
    hass: HomeAssistant,
) -> None:
    dogs = [_build_dog_config({MODULE_HEALTH: True})]
    entry = ConfigEntry(
        domain="pawcontrol",
        data={"dogs": dogs},
        options={"entity_profile": "health_focus"},
        title="Test Entry",
    )

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_get_entry = Mock(return_value=entry)

    pawcontrol_init._PLATFORM_CACHE[(1, "health_focus", frozenset({MODULE_HEALTH}))] = (
        (Platform.SENSOR,),
        0.0,
    )

    assert pawcontrol_init._PLATFORM_CACHE

    result = await pawcontrol_init.async_unload_entry(hass, entry)
    assert result is True
    assert pawcontrol_init._PLATFORM_CACHE == {}


@pytest.mark.asyncio
async def test_async_unload_entry_returns_false_when_platform_unload_fails(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unload should abort early when a platform refuses to unload."""
    entry = ConfigEntry(domain="pawcontrol", title="Unload fail")
    runtime_data = SimpleNamespace(dogs=[], entity_profile="standard")

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
    cleanup_runtime = AsyncMock()
    pop_runtime = Mock()
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_cleanup_runtime_data",
        cleanup_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        pop_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "get_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

    assert await pawcontrol_init.async_unload_entry(hass, entry) is False

    cleanup_runtime.assert_not_awaited()
    pop_runtime.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("shutdown_side_effect", "expected_log"),
    [
        (TimeoutError(), "Service manager shutdown timed out"),
        (RuntimeError("boom"), "Error shutting down service manager: boom"),
    ],
)
async def test_async_unload_entry_handles_service_manager_shutdown_errors(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    shutdown_side_effect: Exception,
    expected_log: str,
) -> None:
    """Service manager shutdown failures should be logged but not fail unload."""
    entry = ConfigEntry(domain="pawcontrol", title="Unload with service manager")
    service_manager = SimpleNamespace(
        async_shutdown=AsyncMock(side_effect=shutdown_side_effect)
    )
    runtime_data = SimpleNamespace(dogs=[], entity_profile="standard")

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
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "async_cleanup_runtime_data",
        AsyncMock(),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_unload_entry.__globals__,
        "pop_runtime_data",
        Mock(),
    )

    hass.data[pawcontrol_init.DOMAIN] = {"service_manager": service_manager}
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_loaded_entries = Mock(return_value=[entry])

    assert await pawcontrol_init.async_unload_entry(hass, entry) is True
    assert expected_log in caplog.text


def test_should_skip_optional_setup_handles_missing_or_mocked_services() -> None:
    """Skip optional setup when service registry is unavailable or mocked."""
    assert pawcontrol_init._should_skip_optional_setup(SimpleNamespace(services=None))

    class _MockServices:
        __module__ = "unittest.mock"

        async def async_call(self) -> None:
            return None

    mock_services = _MockServices()
    assert pawcontrol_init._should_skip_optional_setup(
        SimpleNamespace(services=mock_services)
    )

    class _RealServices:
        async def async_call(self) -> None:
            return None

    assert (
        pawcontrol_init._should_skip_optional_setup(
            SimpleNamespace(services=_RealServices())
        )
        is False
    )


@pytest.mark.asyncio
async def test_async_reload_entry_returns_when_unload_fails(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should stop if unloading the existing entry fails."""
    entry = ConfigEntry(domain="pawcontrol", title="Reload")
    unload_mock = AsyncMock(return_value=False)
    setup_mock = AsyncMock()

    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        unload_mock,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        setup_mock,
    )

    await pawcontrol_init.async_reload_entry(hass, entry)

    unload_mock.assert_awaited_once_with(hass, entry)
    setup_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_reload_entry_reraises_not_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should propagate ConfigEntryNotReady for retry scheduling."""
    entry = ConfigEntry(domain="pawcontrol", title="Reload")
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=ConfigEntryNotReady("not ready")),
    )

    with pytest.raises(ConfigEntryNotReady):
        await pawcontrol_init.async_reload_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_reload_entry_reraises_auth_failures(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should re-raise authentication failures from setup."""
    entry = ConfigEntry(domain="pawcontrol", title="Reload")
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=ConfigEntryAuthFailed("auth boom")),
    )

    with pytest.raises(ConfigEntryAuthFailed, match="auth boom"):
        await pawcontrol_init.async_reload_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_reload_entry_reraises_generic_errors(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload should re-raise unexpected errors from setup."""
    entry = ConfigEntry(domain="pawcontrol", title="Reload")
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_unload_entry",
        AsyncMock(return_value=True),
    )
    monkeypatch.setitem(
        pawcontrol_init.async_reload_entry.__globals__,
        "async_setup_entry",
        AsyncMock(side_effect=RuntimeError("setup crashed")),
    )

    with pytest.raises(RuntimeError, match="setup crashed"):
        await pawcontrol_init.async_reload_entry(hass, entry)


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_restarts_stopped_garden_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background monitor should restart completed garden background tasks."""
    sleep_mock = AsyncMock(side_effect=[None, asyncio.CancelledError()])
    monkeypatch.setattr(pawcontrol_init.asyncio, "sleep", sleep_mock)

    cleanup_restart = AsyncMock()
    stats_restart = AsyncMock()
    garden_manager = SimpleNamespace(
        _cleanup_task=SimpleNamespace(done=lambda: True),
        _stats_update_task=SimpleNamespace(done=lambda: True),
        async_start_cleanup_task=cleanup_restart,
        async_start_stats_update_task=stats_restart,
    )
    runtime_data = SimpleNamespace(garden_manager=garden_manager)

    await pawcontrol_init._async_monitor_background_tasks(runtime_data)

    cleanup_restart.assert_awaited_once_with()
    stats_restart.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_monitor_background_tasks_logs_loop_errors_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unexpected monitor errors should be logged, then the task should continue."""
    sleep_mock = AsyncMock(side_effect=[RuntimeError("boom"), asyncio.CancelledError()])
    monkeypatch.setattr(pawcontrol_init.asyncio, "sleep", sleep_mock)

    await pawcontrol_init._async_monitor_background_tasks(SimpleNamespace())

    assert "Error in background task monitoring: boom" in caplog.text


@pytest.mark.asyncio
async def test_async_setup_entry_runs_setup_pipeline_and_starts_optional_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup entry should orchestrate setup modules and optional background tasks."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=Mock()),
        helper_manager=None,
        door_sensor_manager=None,
        geofencing_manager=None,
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    dogs_config = [_build_dog_config({MODULE_GPS: True})]
    entry = SimpleNamespace(entry_id="entry-setup", options={"debug_logging": False})

    validate_entry = AsyncMock(return_value=(dogs_config, "standard", frozenset()))
    initialize_managers = AsyncMock(return_value=runtime_data)
    register_webhook = AsyncMock()
    register_mqtt = AsyncMock()
    setup_platforms = AsyncMock()
    register_cleanup = AsyncMock()
    setup_daily_reset = AsyncMock(return_value="daily-unsub")
    check_issues = AsyncMock()
    store_runtime = Mock()
    monitor_marker = object()

    async def _monitor_stub(_runtime_data: object) -> None:
        return None

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        validate_entry,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_should_skip_optional_setup",
        lambda _hass: False,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_initialize_managers",
        initialize_managers,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "store_runtime_data",
        store_runtime,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_webhook",
        register_webhook,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_entry_mqtt",
        register_mqtt,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_platforms",
        setup_platforms,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_register_cleanup",
        register_cleanup,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_setup_daily_reset_scheduler",
        setup_daily_reset,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        check_issues,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_async_monitor_background_tasks",
        _monitor_stub,
    )

    def _create_task(coro: object) -> object:
        coro.close()
        return monitor_marker

    hass = SimpleNamespace(async_create_task=_create_task)
    assert await pawcontrol_init.async_setup_entry(hass, entry) is True

    validate_entry.assert_awaited_once_with(entry)
    initialize_managers.assert_awaited_once_with(
        hass,
        entry,
        dogs_config,
        "standard",
        False,
    )
    store_runtime.assert_called_once_with(hass, entry, runtime_data)
    register_webhook.assert_awaited_once_with(hass, entry)
    register_mqtt.assert_awaited_once_with(hass, entry)
    setup_platforms.assert_awaited_once_with(hass, entry, runtime_data)
    register_cleanup.assert_awaited_once_with(hass, entry, runtime_data)
    setup_daily_reset.assert_awaited_once_with(hass, entry)
    check_issues.assert_awaited_once_with(hass, entry)
    runtime_data.coordinator.async_start_background_tasks.assert_called_once_with()
    assert runtime_data.daily_reset_unsub == "daily-unsub"
    assert runtime_data.background_monitor_task is monitor_marker


@pytest.mark.asyncio
async def test_async_setup_entry_wraps_unexpected_setup_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected setup failures should be wrapped in PawControlSetupError."""
    disable_logging = Mock()
    entry = SimpleNamespace(entry_id="entry-setup", options={"debug_logging": True})

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_enable_debug_logging",
        lambda _entry: True,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_disable_debug_logging",
        disable_logging,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=RuntimeError("boom")),
    )

    with pytest.raises(PawControlSetupError, match="RuntimeError"):
        await pawcontrol_init.async_setup_entry(SimpleNamespace(), entry)

    disable_logging.assert_called_once_with(entry)


@pytest.mark.asyncio
async def test_async_setup_registers_service_manager_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration setup should create service manager once per domain."""
    created: list[object] = []

    class _ServiceManager:
        def __init__(self, hass: object) -> None:
            self.hass = hass
            created.append(self)

    monkeypatch.setitem(
        pawcontrol_init.async_setup.__globals__,
        "PawControlServiceManager",
        _ServiceManager,
    )
    hass = SimpleNamespace(data={})

    assert await pawcontrol_init.async_setup(hass, {}) is True
    first_manager = hass.data[pawcontrol_init.DOMAIN]["service_manager"]

    assert await pawcontrol_init.async_setup(hass, {}) is True
    assert hass.data[pawcontrol_init.DOMAIN]["service_manager"] is first_manager
    assert len(created) == 1


@pytest.mark.asyncio
async def test_async_setup_entry_skips_optional_tasks_in_mock_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional setup should be skipped when Home Assistant services are mocked."""
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(async_start_background_tasks=Mock()),
        helper_manager=None,
        door_sensor_manager=None,
        geofencing_manager=None,
        daily_reset_unsub=None,
        background_monitor_task=None,
    )
    dogs_config = [_build_dog_config({MODULE_GPS: True})]
    entry = SimpleNamespace(entry_id="entry-skip-optional", options={})

    validate_entry = AsyncMock(return_value=(dogs_config, "standard", frozenset()))
    initialize_managers = AsyncMock(return_value=runtime_data)
    setup_daily_reset = AsyncMock()
    check_issues = AsyncMock()

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        validate_entry,
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
        Mock(),
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
        setup_daily_reset,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_check_for_issues",
        check_issues,
    )

    hass = SimpleNamespace(async_create_task=Mock())
    assert await pawcontrol_init.async_setup_entry(hass, entry) is True

    initialize_managers.assert_awaited_once_with(
        hass,
        entry,
        dogs_config,
        "standard",
        True,
    )
    setup_daily_reset.assert_not_called()
    check_issues.assert_not_called()
    runtime_data.coordinator.async_start_background_tasks.assert_not_called()
    hass.async_create_task.assert_not_called()


@pytest.mark.asyncio
async def test_async_setup_entry_propagates_auth_failure_and_disables_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auth/setup prerequisite errors should be re-raised without wrapping."""
    disable_logging = Mock()
    entry = SimpleNamespace(entry_id="entry-auth", options={"debug_logging": True})

    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_enable_debug_logging",
        lambda _entry: True,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "_disable_debug_logging",
        disable_logging,
    )
    monkeypatch.setitem(
        pawcontrol_init.async_setup_entry.__globals__,
        "async_validate_entry_config",
        AsyncMock(side_effect=ConfigEntryAuthFailed("auth failed")),
    )

    with pytest.raises(ConfigEntryAuthFailed, match="auth failed"):
        await pawcontrol_init.async_setup_entry(SimpleNamespace(), entry)

    disable_logging.assert_called_once_with(entry)
