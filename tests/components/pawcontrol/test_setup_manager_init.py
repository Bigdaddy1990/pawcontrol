"""Tests for setup manager initialization helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.exceptions import ConfigEntryNotReady
import pytest

from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed


@pytest.mark.asyncio
async def test_async_initialize_coordinator_skips_optional_setup() -> None:
    """Coordinator prep and refresh should be skipped in optional-setup mode."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    await manager_init._async_initialize_coordinator(coordinator, True)

    coordinator.async_prepare_entry.assert_not_awaited()
    coordinator.async_config_entry_first_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_initialize_coordinator_runs_prepare_and_refresh() -> None:
    """Coordinator setup should await both prepare and first refresh callbacks."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    await manager_init._async_initialize_coordinator(coordinator, False)

    coordinator.async_prepare_entry.assert_awaited_once()
    coordinator.async_config_entry_first_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_initialize_coordinator_raises_not_ready_on_prepare_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare-stage timeout should bubble as ConfigEntryNotReady."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )
    monkeypatch.setattr(
        manager_init.asyncio,
        "wait_for",
        AsyncMock(side_effect=TimeoutError),
    )

    with pytest.raises(ConfigEntryNotReady, match="Coordinator pre-setup timeout"):
        await manager_init._async_initialize_coordinator(coordinator, False)


@pytest.mark.asyncio
async def test_async_initialize_coordinator_runs_prepare_and_refresh() -> None:
    """Coordinator setup should await prepare and first refresh when available."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    await manager_init._async_initialize_coordinator(coordinator, False)

    coordinator.async_prepare_entry.assert_awaited_once_with()
    coordinator.async_config_entry_first_refresh.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_async_initialize_coordinator_raises_not_ready_on_refresh_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Refresh-stage timeout should bubble as ConfigEntryNotReady."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(),
    )

    async def _wait_for_with_refresh_timeout(
        awaitable: object,
        timeout: int,
    ) -> object:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        if timeout == manager_init._COORDINATOR_REFRESH_TIMEOUT:
            raise TimeoutError
        return None

    monkeypatch.setattr(
        manager_init.asyncio,
        "wait_for",
        AsyncMock(side_effect=_wait_for_with_refresh_timeout),
    )

    with pytest.raises(
        ConfigEntryNotReady,
        match="Coordinator initialization timeout",
    ):
        await manager_init._async_initialize_coordinator(coordinator, False)
async def test_async_create_optional_managers_returns_defaults_when_skipped() -> None:
    """Optional manager setup should return an empty registry when skipped."""
    from custom_components.pawcontrol.setup import manager_init

    managers = await manager_init._async_create_optional_managers(
        hass=object(),
        entry=SimpleNamespace(entry_id="entry-1"),
        dogs_config=[{"dog_id": "buddy", "modules": {"gps": True}}],
        core_managers={"notification_manager": object()},
        skip_optional_setup=True,
    )

    assert managers == {
        "helper_manager": None,
        "script_manager": None,
        "door_sensor_manager": None,
        "garden_manager": None,
        "gps_geofence_manager": None,
        "geofencing_manager": None,
        "weather_health_manager": None,
    }


@pytest.mark.asyncio
async def test_async_create_optional_managers_updates_options_and_gps_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional setup should migrate script options and wire GPS managers."""
    from custom_components.pawcontrol.setup import manager_init

    script_manager = SimpleNamespace(
        ensure_resilience_threshold_options=MagicMock(return_value={"migrated": True}),
    )
    gps_geofence_manager = SimpleNamespace(set_notification_manager=MagicMock())
    geofencing_manager = SimpleNamespace(set_notification_manager=MagicMock())

    monkeypatch.setattr(manager_init, "PawControlHelperManager", lambda *_: object())
    monkeypatch.setattr(
        manager_init, "PawControlScriptManager", lambda *_: script_manager
    )
    monkeypatch.setattr(manager_init, "DoorSensorManager", lambda *_: object())
    monkeypatch.setattr(manager_init, "GardenManager", lambda *_: object())
    monkeypatch.setattr(manager_init, "WeatherHealthManager", lambda *_: object())
    monkeypatch.setattr(
        manager_init, "GPSGeofenceManager", lambda *_: gps_geofence_manager
    )
    monkeypatch.setattr(
        manager_init, "PawControlGeofencing", lambda *_: geofencing_manager
    )

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=MagicMock())
    )
    entry = SimpleNamespace(entry_id="entry-1")
    dogs_config = [{"dog_id": "buddy", "modules": {"gps": True}}]
    notification_manager = object()

    optional_managers = await manager_init._async_create_optional_managers(
        hass,
        entry,
        dogs_config,
        {"notification_manager": notification_manager},
        skip_optional_setup=False,
    )

    assert optional_managers["script_manager"] is script_manager
    hass.config_entries.async_update_entry.assert_called_once_with(
        entry,
        options={"migrated": True},
    )
    gps_geofence_manager.set_notification_manager.assert_called_once_with(
        notification_manager,
    )
    geofencing_manager.set_notification_manager.assert_called_once_with(
        notification_manager,
    )


@pytest.mark.asyncio
async def test_async_create_core_managers_returns_expected_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Core manager creation should preserve dog order and wire constructor args."""
    from custom_components.pawcontrol.setup import manager_init

    created: dict[str, object] = {}

    def _build_data_manager(
        hass: object,
        entry_id: str,
        *,
        coordinator: object,
        dogs_config: list[dict[str, object]],
    ) -> object:
        instance = SimpleNamespace(
            hass=hass,
            entry_id=entry_id,
            coordinator=coordinator,
            dogs_config=dogs_config,
        )
        created["data_manager"] = instance
        return instance

    def _build_notification_manager(
        hass: object,
        entry_id: str,
        *,
        session: object,
    ) -> object:
        instance = SimpleNamespace(hass=hass, entry_id=entry_id, session=session)
        created["notification_manager"] = instance
        return instance

    monkeypatch.setattr(manager_init, "PawControlDataManager", _build_data_manager)
    monkeypatch.setattr(
        manager_init,
        "PawControlNotificationManager",
        _build_notification_manager,
    )
    monkeypatch.setattr(manager_init, "FeedingManager", lambda hass: ("feeding", hass))
    monkeypatch.setattr(manager_init, "WalkManager", lambda: "walk-manager")
    monkeypatch.setattr(
        manager_init,
        "EntityFactory",
        lambda coordinator, prewarm: ("entity-factory", coordinator, prewarm),
    )

    hass = object()
    entry = SimpleNamespace(entry_id="entry-1")
    coordinator = object()
    session = object()
    dogs_config = [{"dog_id": "buddy"}, {"dog_id": "max"}]

    managers = await manager_init._async_create_core_managers(
        hass,
        entry,
        coordinator,
        dogs_config,
        session,
    )

    assert managers["dog_ids"] == ["buddy", "max"]
    assert managers["data_manager"] is created["data_manager"]
    assert managers["notification_manager"] is created["notification_manager"]
    assert managers["feeding_manager"] == ("feeding", hass)
    assert managers["walk_manager"] == "walk-manager"
    assert managers["entity_factory"] == ("entity-factory", coordinator, True)


@pytest.mark.asyncio
async def test_async_create_optional_managers_skips_gps_managers_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPS/geofencing managers should not be created if all dogs disable GPS."""
    from custom_components.pawcontrol.setup import manager_init

    script_manager = SimpleNamespace(
        ensure_resilience_threshold_options=MagicMock(return_value=None),
    )
    helper_manager = object()
    door_sensor_manager = object()
    garden_manager = object()
    weather_health_manager = object()

    monkeypatch.setattr(
        manager_init,
        "PawControlHelperManager",
        lambda *_: helper_manager,
    )
    monkeypatch.setattr(
        manager_init,
        "PawControlScriptManager",
        lambda *_: script_manager,
    )
    monkeypatch.setattr(
        manager_init,
        "DoorSensorManager",
        lambda *_: door_sensor_manager,
    )
    monkeypatch.setattr(manager_init, "GardenManager", lambda *_: garden_manager)
    monkeypatch.setattr(
        manager_init,
        "WeatherHealthManager",
        lambda *_: weather_health_manager,
    )

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=MagicMock())
    )
    entry = SimpleNamespace(entry_id="entry-1")

    managers = await manager_init._async_create_optional_managers(
        hass,
        entry,
        [{"dog_id": "buddy", "modules": {"gps": False}}],
        {"notification_manager": object()},
        skip_optional_setup=False,
    )

    assert managers["helper_manager"] is helper_manager
    assert managers["script_manager"] is script_manager
    assert managers["door_sensor_manager"] is door_sensor_manager
    assert managers["garden_manager"] is garden_manager
    assert managers["weather_health_manager"] is weather_health_manager
    assert managers["gps_geofence_manager"] is None
    assert managers["geofencing_manager"] is None
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_create_optional_managers_skip_optional_returns_defaults() -> None:
    """Skipping optional setup should return empty optional manager slots."""
    from custom_components.pawcontrol.setup import manager_init

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=MagicMock())
    )
    entry = SimpleNamespace(entry_id="entry-1")

    managers = await manager_init._async_create_optional_managers(
        hass,
        entry,
        [{"dog_id": "buddy", "modules": {"gps": True}}],
        {"notification_manager": object()},
        skip_optional_setup=True,
    )

    assert managers == {
        "helper_manager": None,
        "script_manager": None,
        "door_sensor_manager": None,
        "garden_manager": None,
        "gps_geofence_manager": None,
        "geofencing_manager": None,
        "weather_health_manager": None,
    }
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_initialize_geofencing_manager_uses_per_dog_overrides() -> None:
    """Per-dog geofencing options should drive manager initialization payload."""
    from custom_components.pawcontrol.setup import manager_init

    geofencing_manager = SimpleNamespace(async_initialize=AsyncMock())
    initialization_tasks: list[asyncio.Task[None]] = []
    entry = SimpleNamespace(
        options={
            "geofence_settings": {"geofencing_enabled": False, "geofence_radius_m": 10},
            "dog_options": {
                "buddy": {
                    "geofence_settings": {
                        "geofencing_enabled": True,
                        "use_home_location": False,
                        "geofence_radius_m": 65,
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

    geofencing_manager.async_initialize.assert_awaited_once_with(
        dogs=["buddy"],
        enabled=True,
        use_home_location=False,
        home_zone_radius=65,
    )


@pytest.mark.asyncio
async def test_async_initialize_geofencing_manager_ignores_invalid_per_dog_payloads(
) -> None:
    """Global geofence options should be used when per-dog payloads are invalid."""
    from custom_components.pawcontrol.setup import manager_init

    geofencing_manager = SimpleNamespace(async_initialize=AsyncMock())
    initialization_tasks: list[asyncio.Task[None]] = []
    entry = SimpleNamespace(
        options={
            "geofence_settings": {
                "geofencing_enabled": True,
                "use_home_location": False,
                "geofence_radius_m": 33,
            },
            "dog_options": {
                "buddy": "invalid-payload",
                "max": {"geofence_settings": "invalid-payload"},
            },
        }
    )

    await manager_init._async_initialize_geofencing_manager(
        geofencing_manager,
        ["buddy", "max"],
        entry,
        initialization_tasks,
    )
    await asyncio.gather(*initialization_tasks)

    geofencing_manager.async_initialize.assert_awaited_once_with(
        dogs=["buddy", "max"],
        enabled=True,
        use_home_location=False,
        home_zone_radius=33,
    )


@pytest.mark.asyncio
async def test_async_initialize_coordinator_wraps_network_refresh_errors() -> None:
    """Refresh OSErrors should be surfaced as ConfigEntryNotReady."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(side_effect=OSError("offline")),
    )

    with pytest.raises(
        ConfigEntryNotReady,
        match="Network connectivity issue during coordinator setup",
    ):
        await manager_init._async_initialize_coordinator(coordinator, False)


@pytest.mark.asyncio
async def test_async_initialize_coordinator_reraises_auth_failures() -> None:
    """Auth failures should not be wrapped by ConfigEntryNotReady."""
    from custom_components.pawcontrol.setup import manager_init

    prepare_coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(side_effect=ConfigEntryAuthFailed("prepare")),
        async_config_entry_first_refresh=AsyncMock(),
    )
    refresh_coordinator = SimpleNamespace(
        async_prepare_entry=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(
            side_effect=ConfigEntryAuthFailed("refresh")
        ),
    )

    with pytest.raises(ConfigEntryAuthFailed, match="prepare"):
        await manager_init._async_initialize_coordinator(prepare_coordinator, False)

    with pytest.raises(ConfigEntryAuthFailed, match="refresh"):
        await manager_init._async_initialize_coordinator(refresh_coordinator, False)


@pytest.mark.asyncio
async def test_async_initialize_all_managers_prioritizes_auth_failures() -> None:
    """Auth failures should be raised even when earlier managers fail differently."""
    from custom_components.pawcontrol.setup import manager_init

    auth_failed = ConfigEntryAuthFailed("reauth required")
    core_managers = {
        "dog_ids": ["buddy"],
        "data_manager": SimpleNamespace(
            async_initialize=AsyncMock(side_effect=RuntimeError("boom"))
        ),
        "notification_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "feeding_manager": SimpleNamespace(
            async_initialize=AsyncMock(side_effect=auth_failed)
        ),
        "walk_manager": SimpleNamespace(async_initialize=AsyncMock()),
    }
    optional_managers = {
        "helper_manager": None,
        "script_manager": None,
        "door_sensor_manager": None,
        "garden_manager": None,
        "gps_geofence_manager": None,
        "geofencing_manager": None,
        "weather_health_manager": None,
    }
    entry = SimpleNamespace(options={})

    with pytest.raises(ConfigEntryAuthFailed, match="reauth required"):
        await manager_init._async_initialize_all_managers(
            core_managers,
            optional_managers,
            [{"dog_id": "buddy"}],
            entry,
        )


@pytest.mark.asyncio
async def test_async_initialize_manager_with_timeout_propagates_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager init helper should re-raise timeout errors from wait_for."""
    from custom_components.pawcontrol.setup import manager_init

    async def _never_called() -> None:
        return None

    async def _raise_timeout(coro: object, timeout: int) -> None:
        close = getattr(coro, "close", None)
        if callable(close):
            close()
        raise TimeoutError

    monkeypatch.setattr(
        manager_init.asyncio,
        "wait_for",
        AsyncMock(side_effect=_raise_timeout),
    )

    with pytest.raises(TimeoutError):
        await manager_init._async_initialize_manager_with_timeout(
            "test_manager",
            _never_called(),
        )


@pytest.mark.asyncio
async def test_async_initialize_all_managers_raises_first_non_auth_exception() -> None:
    """Initialization should raise the first non-auth failure with no auth error."""
    from custom_components.pawcontrol.setup import manager_init

    failure = RuntimeError("manager boom")
    core_managers = {
        "dog_ids": ["buddy"],
        "data_manager": SimpleNamespace(
            async_initialize=AsyncMock(side_effect=failure)
        ),
        "notification_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "feeding_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "walk_manager": SimpleNamespace(async_initialize=AsyncMock()),
    }
    optional_managers = {
        "helper_manager": None,
        "script_manager": None,
        "door_sensor_manager": None,
        "garden_manager": None,
        "gps_geofence_manager": None,
        "geofencing_manager": None,
        "weather_health_manager": None,
    }

    with pytest.raises(RuntimeError, match="manager boom"):
        await manager_init._async_initialize_all_managers(
            core_managers,
            optional_managers,
            [{"dog_id": "buddy"}],
            SimpleNamespace(options={}),
        )


@pytest.mark.asyncio
async def test_async_initialize_all_managers_initializes_optional_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Door, garden, geofencing, and generic optional managers should initialize."""
    from custom_components.pawcontrol.setup import manager_init

    door_sensor_manager = SimpleNamespace(async_initialize=AsyncMock())
    garden_manager = SimpleNamespace(async_initialize=AsyncMock())
    helper_manager = SimpleNamespace(async_initialize=AsyncMock())
    geofencing_manager = SimpleNamespace(async_initialize=AsyncMock())
    initialize_geofence = AsyncMock()
    monkeypatch.setattr(
        manager_init,
        "_async_initialize_geofencing_manager",
        initialize_geofence,
    )

    core_managers = {
        "dog_ids": ["buddy"],
        "data_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "notification_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "feeding_manager": SimpleNamespace(async_initialize=AsyncMock()),
        "walk_manager": SimpleNamespace(async_initialize=AsyncMock()),
    }
    optional_managers = {
        "helper_manager": helper_manager,
        "script_manager": None,
        "door_sensor_manager": door_sensor_manager,
        "garden_manager": garden_manager,
        "gps_geofence_manager": None,
        "geofencing_manager": geofencing_manager,
        "weather_health_manager": None,
    }
    dogs_config = [{"dog_id": "buddy"}]
    entry = SimpleNamespace(options={})

    await manager_init._async_initialize_all_managers(
        core_managers,
        optional_managers,
        dogs_config,
        entry,
    )

    door_sensor_manager.async_initialize.assert_awaited_once_with(
        dogs=dogs_config,
        walk_manager=core_managers["walk_manager"],
        notification_manager=core_managers["notification_manager"],
        data_manager=core_managers["data_manager"],
    )
    garden_manager.async_initialize.assert_awaited_once_with(
        dogs=["buddy"],
        notification_manager=core_managers["notification_manager"],
        door_sensor_manager=door_sensor_manager,
    )
    helper_manager.async_initialize.assert_awaited_once_with()
    initialize_geofence.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_data_creation_and_monitor_registration() -> None:
    """Runtime helpers should wire managers, telemetry, and monitor registration."""
    from custom_components.pawcontrol.setup import manager_init

    coordinator = SimpleNamespace(
        api_client=object(),
        resilience_manager=object(),
        attach_runtime_managers=MagicMock(),
    )
    script_manager = SimpleNamespace(
        attach_runtime_manual_history=MagicMock(),
        sync_manual_event_history=MagicMock(),
    )
    data_manager = SimpleNamespace(register_runtime_cache_monitors=MagicMock())
    notification_manager = SimpleNamespace()
    weather_health_manager = SimpleNamespace()
    gps_geofence_manager = SimpleNamespace()

    core_managers = {
        "data_manager": data_manager,
        "notification_manager": notification_manager,
        "feeding_manager": object(),
        "walk_manager": object(),
        "entity_factory": object(),
        "dog_ids": ["buddy"],
    }
    optional_managers = {
        "helper_manager": object(),
        "script_manager": script_manager,
        "door_sensor_manager": object(),
        "garden_manager": object(),
        "gps_geofence_manager": gps_geofence_manager,
        "geofencing_manager": object(),
        "weather_health_manager": weather_health_manager,
    }
    entry = SimpleNamespace(
        data={"token": "abc"},
        options={"flag": True},
    )

    manager_init._attach_managers_to_coordinator(
        coordinator,
        core_managers,
        optional_managers,
    )
    assert gps_geofence_manager.resilience_manager is coordinator.resilience_manager
    assert notification_manager.resilience_manager is coordinator.resilience_manager
    assert weather_health_manager.resilience_manager is coordinator.resilience_manager

    runtime_data = manager_init._create_runtime_data(
        entry,
        coordinator,
        core_managers,
        optional_managers,
        [{"dog_id": "buddy"}],
        "default",
    )

    script_manager.attach_runtime_manual_history.assert_called_once_with(runtime_data)
    script_manager.sync_manual_event_history.assert_called_once_with()

    manager_init._register_runtime_monitors(runtime_data)
    data_manager.register_runtime_cache_monitors.assert_called_once_with(runtime_data)
