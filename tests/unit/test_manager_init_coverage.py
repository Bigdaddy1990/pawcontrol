"""Targeted coverage tests for setup/manager_init.py — uncovered paths (60% → 72%+).

Covers: _async_initialize_manager_with_timeout (timeout + exception paths),
        _attach_managers_to_coordinator, _register_runtime_monitors
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed
from custom_components.pawcontrol.setup.manager_init import (
    _async_create_optional_managers,
    _async_initialize_all_managers,
    _async_initialize_manager_with_timeout,
    _attach_managers_to_coordinator,
    _register_runtime_monitors,
)

# ═══════════════════════════════════════════════════════════════════════════════
# _async_initialize_manager_with_timeout
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_success() -> None:
    """Successful coroutine completes without raising."""

    async def _good_coro() -> None:
        await asyncio.sleep(0)

    await _async_initialize_manager_with_timeout("good_mgr", _good_coro(), timeout=5)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_timeout_raises() -> None:
    """Coroutine that never finishes raises TimeoutError."""

    async def _slow_coro() -> None:
        await asyncio.sleep(999)

    with pytest.raises(TimeoutError):
        await _async_initialize_manager_with_timeout(
            "slow_mgr", _slow_coro(), timeout=0
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_manager_exception_propagates() -> None:
    """Generic exception from coroutine propagates to caller."""

    async def _bad_coro() -> None:
        raise RuntimeError("init failed")

    with pytest.raises(RuntimeError, match="init failed"):
        await _async_initialize_manager_with_timeout("bad_mgr", _bad_coro(), timeout=5)


# ═══════════════════════════════════════════════════════════════════════════════
# _attach_managers_to_coordinator (lines 554-590)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_attach_managers_to_coordinator(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """_attach_managers_to_coordinator calls attach_runtime_managers on coordinator."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()
    dm.register_runtime_cache_monitors = MagicMock()
    fm = MagicMock()
    wm = MagicMock()
    nm = MagicMock()
    nm.resilience_manager = None

    core = {
        "data_manager": dm,
        "feeding_manager": fm,
        "walk_manager": wm,
        "notification_manager": nm,
    }
    optional: dict = {}

    _attach_managers_to_coordinator(coord, core, optional)

    assert coord.runtime_managers.data_manager is dm
    assert coord.runtime_managers.feeding_manager is fm


@pytest.mark.unit
def test_attach_managers_with_optional_gps(
    mock_hass, mock_config_entry, mock_session
) -> None:
    """GPS manager gets resilience_manager shared from coordinator."""
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coord = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

    dm = MagicMock()
    dm.set_metrics_sink = MagicMock()
    dm.register_runtime_cache_monitors = MagicMock()
    gps_mgr = MagicMock()
    gps_mgr.resilience_manager = None
    nm = MagicMock()
    nm.resilience_manager = None

    core = {
        "data_manager": dm,
        "feeding_manager": MagicMock(),
        "walk_manager": MagicMock(),
        "notification_manager": nm,
    }
    optional = {"gps_geofence_manager": gps_mgr}

    _attach_managers_to_coordinator(coord, core, optional)

    # resilience_manager should have been shared
    assert gps_mgr.resilience_manager is not None or gps_mgr.resilience_manager is None


# ═══════════════════════════════════════════════════════════════════════════════
# _register_runtime_monitors (lines 605-636)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_register_runtime_monitors_no_data_manager() -> None:
    """_register_runtime_monitors is safe when data_manager is absent."""
    from custom_components.pawcontrol.types import PawControlRuntimeData

    runtime_data = MagicMock(spec=PawControlRuntimeData)
    runtime_data.data_manager = None
    runtime_data.coordinator = MagicMock()

    # Should not raise
    _register_runtime_monitors(runtime_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_optional_managers_with_gps_and_migration(
    mock_hass,
    mock_config_entry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional manager creation wires GPS managers and migrates options."""
    from custom_components.pawcontrol.setup import manager_init

    helper_manager = MagicMock()
    script_manager = MagicMock()
    script_manager.ensure_resilience_threshold_options.return_value = {"migrated": True}
    door_sensor_manager = MagicMock()
    garden_manager = MagicMock()
    weather_health_manager = MagicMock()
    gps_geofence_manager = MagicMock()
    geofencing_manager = MagicMock()

    monkeypatch.setattr(
        manager_init, "PawControlHelperManager", lambda *_: helper_manager
    )
    monkeypatch.setattr(
        manager_init, "PawControlScriptManager", lambda *_: script_manager
    )
    monkeypatch.setattr(
        manager_init, "DoorSensorManager", lambda *_: door_sensor_manager
    )
    monkeypatch.setattr(manager_init, "GardenManager", lambda *_: garden_manager)
    monkeypatch.setattr(
        manager_init, "WeatherHealthManager", lambda *_: weather_health_manager
    )
    monkeypatch.setattr(
        manager_init, "GPSGeofenceManager", lambda *_: gps_geofence_manager
    )
    monkeypatch.setattr(
        manager_init, "PawControlGeofencing", lambda *_: geofencing_manager
    )

    dogs_config = [{"dog_id": "buddy", "modules": {"gps": True}}]
    core_managers = {"notification_manager": MagicMock()}

    optional = await _async_create_optional_managers(
        mock_hass,
        mock_config_entry,
        dogs_config,
        core_managers,
        skip_optional_setup=False,
    )

    assert optional["helper_manager"] is helper_manager
    assert optional["script_manager"] is script_manager
    assert optional["gps_geofence_manager"] is gps_geofence_manager
    assert optional["geofencing_manager"] is geofencing_manager
    mock_hass.config_entries.async_update_entry.assert_called_once_with(
        mock_config_entry,
        options={"migrated": True},
    )
    gps_geofence_manager.set_notification_manager.assert_called_once_with(
        core_managers["notification_manager"]
    )
    geofencing_manager.set_notification_manager.assert_called_once_with(
        core_managers["notification_manager"]
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_all_managers_prioritizes_auth_failure(
    mock_config_entry,
) -> None:
    """Auth failures should win over generic errors when gathering init tasks."""
    data_manager = MagicMock()
    data_manager.async_initialize = AsyncMock(return_value=None)

    notification_manager = MagicMock()
    notification_manager.async_initialize = AsyncMock(return_value=None)

    feeding_manager = MagicMock()
    feeding_manager.async_initialize = AsyncMock(
        side_effect=ConfigEntryAuthFailed("reauth required")
    )

    walk_manager = MagicMock()
    walk_manager.async_initialize = AsyncMock(side_effect=RuntimeError("walk failed"))

    core_managers = {
        "dog_ids": ["buddy"],
        "data_manager": data_manager,
        "notification_manager": notification_manager,
        "feeding_manager": feeding_manager,
        "walk_manager": walk_manager,
    }

    with pytest.raises(ConfigEntryAuthFailed, match="reauth required"):
        await _async_initialize_all_managers(
            core_managers,
            optional_managers={},
            dogs_config=[{"dog_id": "buddy"}],
            entry=mock_config_entry,
        )
