"""Unit tests for setup.manager_init helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed
from custom_components.pawcontrol.setup import manager_init


@pytest.mark.asyncio
async def test_async_initialize_coordinator_skips_when_optional_disabled() -> None:
    """Coordinator init should skip both setup calls when requested."""
    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    await manager_init._async_initialize_coordinator(
        coordinator, skip_optional_setup=True
    )

    coordinator.async_prepare_entry.assert_not_called()
    coordinator.async_config_entry_first_refresh.assert_not_called()


@pytest.mark.asyncio
async def test_async_initialize_coordinator_prepare_timeout_raises_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeout in prepare step should raise ConfigEntryNotReady."""
    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    async def _raise_timeout(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(manager_init.asyncio, "wait_for", _raise_timeout)

    with pytest.raises(ConfigEntryNotReady, match="pre-setup timeout"):
        await manager_init._async_initialize_coordinator(
            coordinator,
            skip_optional_setup=False,
        )


@pytest.mark.asyncio
async def test_async_initialize_coordinator_refresh_network_error_raises_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Network issues during first refresh should raise ConfigEntryNotReady."""
    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(side_effect=ConnectionError("boom")),
    )

    with pytest.raises(ConfigEntryNotReady, match="coordinator setup"):
        await manager_init._async_initialize_coordinator(
            coordinator,
            skip_optional_setup=False,
        )


@pytest.mark.asyncio
async def test_async_initialize_manager_with_timeout_handles_failures() -> None:
    """Manager wrapper should pass through timeout and generic exceptions."""
    with pytest.raises(TimeoutError):
        await manager_init._async_initialize_manager_with_timeout(
            "demo",
            AsyncMock(side_effect=TimeoutError)(),
        )

    with pytest.raises(ValueError, match="bad"):
        await manager_init._async_initialize_manager_with_timeout(
            "demo",
            AsyncMock(side_effect=ValueError("bad"))(),
        )


@pytest.mark.asyncio
async def test_async_create_optional_managers_skip_optional_setup() -> None:
    """Optional manager factory should return empty managers when skipped."""
    result = await manager_init._async_create_optional_managers(
        SimpleNamespace(),
        SimpleNamespace(entry_id="entry", options={}),
        [],
        {"notification_manager": object()},
        skip_optional_setup=True,
    )

    assert all(manager is None for manager in result.values())


@pytest.mark.asyncio
async def test_async_create_optional_managers_creates_gps_managers_and_migrates_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPS-enabled dogs should create GPS managers and migrate script options."""

    class _ScriptManager:
        def ensure_resilience_threshold_options(self):
            return {"entity_profile": "advanced"}

    class _GPSManager:
        def __init__(self, _hass):
            self.notification_manager = None

        def set_notification_manager(self, manager):
            self.notification_manager = manager

    class _GeofencingManager:
        def __init__(self, _hass, _entry_id):
            self.notification_manager = None

        def set_notification_manager(self, manager):
            self.notification_manager = manager

    monkeypatch.setattr(
        manager_init, "PawControlHelperManager", lambda _h, _e: object()
    )
    monkeypatch.setattr(
        manager_init, "PawControlScriptManager", lambda _h, _e: _ScriptManager()
    )
    monkeypatch.setattr(manager_init, "DoorSensorManager", lambda _h, _id: object())
    monkeypatch.setattr(manager_init, "GardenManager", lambda _h, _id: object())
    monkeypatch.setattr(manager_init, "WeatherHealthManager", lambda _h: object())
    monkeypatch.setattr(manager_init, "GPSGeofenceManager", _GPSManager)
    monkeypatch.setattr(manager_init, "PawControlGeofencing", _GeofencingManager)

    update_entry_mock = MagicMock()
    entry = SimpleNamespace(
        entry_id="entry-1",
        options={},
        data={},
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=update_entry_mock)
    )

    result = await manager_init._async_create_optional_managers(
        hass,
        entry,
        [{"dog_id": "buddy", "modules": {"gps": True}}],
        {"notification_manager": object()},
        skip_optional_setup=False,
    )

    assert result["gps_geofence_manager"] is not None
    assert result["geofencing_manager"] is not None
    update_entry_mock.assert_called_once_with(
        entry,
        options={"entity_profile": "advanced"},
    )


@pytest.mark.asyncio
async def test_async_initialize_coordinator_auth_failure_is_reraised() -> None:
    """Auth errors must not be wrapped as ConfigEntryNotReady."""
    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(side_effect=ConfigEntryAuthFailed("nope")),
        async_config_entry_first_refresh=AsyncMock(),
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await manager_init._async_initialize_coordinator(
            coordinator,
            skip_optional_setup=False,
        )


@pytest.mark.asyncio
async def test_async_initialize_geofencing_manager_prefers_per_dog_options() -> None:
    """Per-dog geofence options should override global defaults."""
    initialize = AsyncMock()
    geofencing_manager = SimpleNamespace(async_initialize=initialize)
    initialization_tasks: list = []
    entry = SimpleNamespace(
        options={
            "geofence_settings": {
                "geofencing_enabled": False,
                "use_home_location": True,
                "geofence_radius_m": 42,
            },
            "dog_options": {
                "buddy": {
                    "geofence_settings": {
                        "geofencing_enabled": True,
                        "use_home_location": False,
                        "geofence_radius_m": 175,
                    }
                }
            },
        }
    )

    await manager_init._async_initialize_geofencing_manager(
        geofencing_manager,
        ["buddy"],
        entry,
        initialization_tasks,
    )
    await asyncio.gather(*initialization_tasks)

    initialize.assert_awaited_once_with(
        dogs=["buddy"],
        enabled=True,
        use_home_location=False,
        home_zone_radius=175,
    )


def test_attach_managers_to_coordinator_shares_resilience_manager() -> None:
    """Attach helper should wire optional manager resilience references."""
    resilience_manager = object()
    coordinator = SimpleNamespace(
        resilience_manager=resilience_manager,
        attach_runtime_managers=MagicMock(),
    )
    gps_geofence_manager = SimpleNamespace(resilience_manager=None)
    notification_manager = SimpleNamespace(resilience_manager=None)
    weather_health_manager = SimpleNamespace(resilience_manager=None)
    core_managers = {
        "data_manager": object(),
        "feeding_manager": object(),
        "walk_manager": object(),
        "notification_manager": notification_manager,
    }
    optional_managers = {
        "gps_geofence_manager": gps_geofence_manager,
        "geofencing_manager": object(),
        "weather_health_manager": weather_health_manager,
        "garden_manager": object(),
    }

    manager_init._attach_managers_to_coordinator(
        coordinator,
        core_managers,
        optional_managers,
    )

    coordinator.attach_runtime_managers.assert_called_once()
    assert gps_geofence_manager.resilience_manager is resilience_manager
    assert notification_manager.resilience_manager is resilience_manager
    assert weather_health_manager.resilience_manager is resilience_manager


def test_create_runtime_data_syncs_script_history_and_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime data creation should sync script history and update telemetry."""
    script_manager = SimpleNamespace(
        attach_runtime_manual_history=MagicMock(),
        sync_manual_event_history=MagicMock(),
    )
    telemetry_update = MagicMock()
    monkeypatch.setattr(
        manager_init,
        "update_runtime_reconfigure_summary",
        telemetry_update,
    )

    runtime_data = manager_init._create_runtime_data(
        SimpleNamespace(data={"k": "v"}, options={"o": "p"}),
        SimpleNamespace(api_client=object()),
        {
            "data_manager": object(),
            "notification_manager": object(),
            "feeding_manager": object(),
            "walk_manager": object(),
            "entity_factory": object(),
        },
        {
            "helper_manager": object(),
            "script_manager": script_manager,
            "geofencing_manager": object(),
            "gps_geofence_manager": object(),
            "door_sensor_manager": object(),
            "garden_manager": object(),
            "weather_health_manager": object(),
        },
        [{"dog_id": "buddy", "dog_name": "Buddy"}],
        "standard",
    )

    script_manager.attach_runtime_manual_history.assert_called_once_with(runtime_data)
    script_manager.sync_manual_event_history.assert_called_once_with()
    telemetry_update.assert_called_once_with(runtime_data)


def test_register_runtime_monitors_calls_data_manager_hook() -> None:
    """Runtime monitor registration should call the cache monitor hook if present."""
    register_hook = MagicMock()
    runtime_data = SimpleNamespace(
        data_manager=SimpleNamespace(register_runtime_cache_monitors=register_hook)
    )

    manager_init._register_runtime_monitors(runtime_data)

    register_hook.assert_called_once_with(runtime_data)
