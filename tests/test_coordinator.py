"""Comprehensive tests for PawControl coordinator.

Tests data update coordinator functionality including error handling,
caching, and module-specific data fetching.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed


async def test_coordinator_initialization(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test coordinator initialization."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    assert coordinator.config_entry == mock_config_entry
    assert coordinator.session == mock_websession
    assert coordinator.dogs == mock_config_entry.data[CONF_DOGS]
    assert coordinator.name == "PawControl Data"
    assert coordinator.update_interval == timedelta(seconds=UPDATE_INTERVALS["minimal"])


async def test_coordinator_update_interval_calculation(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test update interval calculation based on modules."""
    # Test with GPS module enabled
    config_with_gps = mock_config_entry
    config_with_gps.data[CONF_DOGS][0]["modules"][MODULE_GPS] = True

    coordinator = PawControlCoordinator(hass, config_with_gps, mock_websession)

    # Should use frequent interval for GPS
    assert coordinator.update_interval == timedelta(
        seconds=UPDATE_INTERVALS["frequent"]
    )


async def test_coordinator_update_interval_with_options(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test update interval with GPS options."""
    config_with_gps = mock_config_entry
    config_with_gps.data[CONF_DOGS][0]["modules"][MODULE_GPS] = True
    config_with_gps.options[CONF_GPS_UPDATE_INTERVAL] = 30

    coordinator = PawControlCoordinator(hass, config_with_gps, mock_websession)

    # Should use custom GPS interval
    assert coordinator.update_interval == timedelta(seconds=30)


async def test_coordinator_update_data_success(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test successful data update."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Mock fetch methods
    with patch.object(coordinator, "_fetch_dog_data", return_value={"test": "data"}):
        result = await coordinator._async_update_data()

    assert "buddy" in result
    assert result["buddy"] == {"test": "data"}


async def test_coordinator_update_data_partial_failure(
    hass: HomeAssistant, mock_config_entry_multi_dog, mock_websession
) -> None:
    """Test partial failure during data update."""
    coordinator = PawControlCoordinator(
        hass, mock_config_entry_multi_dog, mock_websession
    )

    # Mock fetch to fail for one dog
    async def mock_fetch(dog_id):
        if dog_id == "buddy":
            return {"test": "data"}
        else:
            raise ValueError("Failed to fetch")

    with patch.object(coordinator, "_fetch_dog_data", side_effect=mock_fetch):
        result = await coordinator._async_update_data()

    # Should have data for successful dog
    assert "buddy" in result
    assert result["buddy"] == {"test": "data"}
    # Failed dog should have empty dict
    assert "max" in result
    assert result["max"] == {}


async def test_coordinator_update_data_all_failure(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test all dogs failing during data update."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Mock all fetches to fail
    with (
        patch.object(coordinator, "_fetch_dog_data", side_effect=ValueError("Failed")),
        pytest.raises(UpdateFailed, match="All dogs failed to update"),
    ):
        await coordinator._async_update_data()


async def test_coordinator_fetch_dog_data(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test fetching data for a single dog."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Mock module data methods
    with (
        patch.object(
            coordinator, "_get_feeding_data", return_value={"feeding": "data"}
        ),
        patch.object(coordinator, "_get_walk_data", return_value={"walk": "data"}),
        patch.object(coordinator, "_get_gps_data", return_value={"gps": "data"}),
        patch.object(coordinator, "_get_health_data", return_value={"health": "data"}),
    ):
        result = await coordinator._fetch_dog_data("buddy")

    assert "dog_info" in result
    assert MODULE_FEEDING in result
    assert MODULE_WALK in result
    assert MODULE_GPS in result
    assert MODULE_HEALTH in result


async def test_coordinator_fetch_dog_data_invalid(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test fetching data for invalid dog."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    with pytest.raises(ValueError, match="Dog invalid_dog not found"):
        await coordinator._fetch_dog_data("invalid_dog")


async def test_coordinator_get_feeding_data(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test getting feeding data."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    result = await coordinator._get_feeding_data("buddy")

    assert "last_feeding" in result
    assert "next_feeding" in result
    assert "daily_portions" in result
    assert result["status"] == "unknown"


async def test_coordinator_get_walk_data(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test getting walk data."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    result = await coordinator._get_walk_data("buddy")

    assert "current_walk" in result
    assert "last_walk" in result
    assert "daily_walks" in result
    assert "total_distance" in result
    assert result["status"] == "unknown"


async def test_coordinator_get_gps_data(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test getting GPS data."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    result = await coordinator._get_gps_data("buddy")

    assert "latitude" in result
    assert "longitude" in result
    assert "accuracy" in result
    assert "last_update" in result
    assert result["status"] == "unknown"


async def test_coordinator_get_health_data(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test getting health data."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    result = await coordinator._get_health_data("buddy")

    assert "weight" in result
    assert "last_vet_visit" in result
    assert "medications" in result
    assert result["status"] == "unknown"


async def test_coordinator_public_methods(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test public interface methods."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Test get_dog_config
    config = coordinator.get_dog_config("buddy")
    assert config is not None
    assert config[CONF_DOG_ID] == "buddy"

    # Test get_dog_config for invalid dog
    config = coordinator.get_dog_config("invalid")
    assert config is None

    # Test get_enabled_modules
    modules = coordinator.get_enabled_modules("buddy")
    assert MODULE_FEEDING in modules
    assert MODULE_WALK in modules

    # Test is_module_enabled
    assert coordinator.is_module_enabled("buddy", MODULE_FEEDING) is True
    assert coordinator.is_module_enabled("buddy", "invalid_module") is False
    assert coordinator.is_module_enabled("invalid_dog", MODULE_FEEDING) is False

    # Test get_dog_ids
    dog_ids = coordinator.get_dog_ids()
    assert "buddy" in dog_ids


async def test_coordinator_data_methods(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test data access methods."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Set some test data
    coordinator._data = {
        "buddy": {
            MODULE_FEEDING: {"test": "feeding_data"},
            MODULE_WALK: {"test": "walk_data"},
        }
    }

    # Test get_dog_data
    dog_data = coordinator.get_dog_data("buddy")
    assert dog_data is not None
    assert MODULE_FEEDING in dog_data

    # Test get_dog_data for invalid dog
    dog_data = coordinator.get_dog_data("invalid")
    assert dog_data is None

    # Test get_all_dogs_data
    all_data = coordinator.get_all_dogs_data()
    assert "buddy" in all_data
    assert all_data["buddy"][MODULE_FEEDING]["test"] == "feeding_data"

    # Test get_module_data
    module_data = coordinator.get_module_data("buddy", MODULE_FEEDING)
    assert module_data["test"] == "feeding_data"

    # Test get_module_data for invalid
    module_data = coordinator.get_module_data("invalid", MODULE_FEEDING)
    assert module_data == {}


async def test_coordinator_availability(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test coordinator availability."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Initially not available
    assert coordinator.available is False

    # Set last_update_success
    coordinator.last_update_success = True
    assert coordinator.available is True

    coordinator.last_update_success = False
    assert coordinator.available is False


async def test_coordinator_update_statistics(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test update statistics."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)
    coordinator._data = {"buddy": {}, "max": {}}

    stats = coordinator.get_update_statistics()

    assert stats["total_dogs"] == 1  # Only one dog in mock_config_entry
    assert stats["last_update_success"] is False
    assert stats["update_interval_seconds"] == UPDATE_INTERVALS["minimal"]
    assert stats["dogs_tracked"] == 2


async def test_coordinator_background_tasks(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test background maintenance tasks."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Mock the maintenance loop
    with patch.object(coordinator, "_maintenance_loop", new_callable=AsyncMock):
        await coordinator.async_start_background_tasks()

        # Verify task was created
        assert hasattr(coordinator, "_maintenance_task")
        assert coordinator._maintenance_task is not None


async def test_coordinator_shutdown(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test coordinator shutdown."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Create a mock task
    mock_task = MagicMock()
    mock_task.cancel = MagicMock()
    coordinator._maintenance_task = mock_task

    await coordinator.async_shutdown()

    # Verify task was cancelled
    mock_task.cancel.assert_called_once()


async def test_coordinator_maintenance_loop(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test maintenance loop execution."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Mock perform_maintenance
    with patch.object(
        coordinator, "_perform_maintenance", new_callable=AsyncMock
    ) as mock_maint:
        # Run maintenance loop for one iteration
        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):  # noqa: SIM117
            with contextlib.suppress(asyncio.CancelledError):
                await coordinator._maintenance_loop()

        # Verify maintenance was called
        mock_maint.assert_called()


async def test_coordinator_module_complexity_calculation(
    hass: HomeAssistant, mock_config_entry_multi_dog, mock_websession
) -> None:
    """Test update interval calculation based on module complexity."""
    # Create config with many modules
    config = mock_config_entry_multi_dog
    for dog in config.data[CONF_DOGS]:
        dog["modules"] = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: False,  # No GPS to avoid GPS interval
            MODULE_HEALTH: True,
            MODULE_NOTIFICATIONS: True,  # noqa: F821
            "extra1": True,
            "extra2": True,
            "extra3": True,
        }

    coordinator = PawControlCoordinator(hass, config, mock_websession)

    # Should use normal interval for high module count
    assert coordinator.update_interval == timedelta(seconds=UPDATE_INTERVALS["normal"])


async def test_coordinator_no_dogs(hass: HomeAssistant, mock_websession) -> None:
    """Test coordinator with no dogs configured."""
    config_entry = MagicMock()
    config_entry.data = {CONF_DOGS: []}
    config_entry.options = {}

    coordinator = PawControlCoordinator(hass, config_entry, mock_websession)

    # Should use minimal interval
    assert coordinator.update_interval == timedelta(seconds=UPDATE_INTERVALS["minimal"])

    # Update should return empty dict
    result = await coordinator._async_update_data()
    assert result == {}


async def test_coordinator_error_recovery(
    hass: HomeAssistant, mock_config_entry, mock_websession
) -> None:
    """Test coordinator error recovery with cached data."""
    coordinator = PawControlCoordinator(hass, mock_config_entry, mock_websession)

    # Set initial data
    coordinator._data = {"buddy": {"cached": "data"}}

    # Mock fetch to fail
    with patch.object(coordinator, "_fetch_dog_data", side_effect=Exception("Error")):
        result = await coordinator._async_update_data()

    # Should return cached data on error
    assert result["buddy"] == {"cached": "data"}
