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
