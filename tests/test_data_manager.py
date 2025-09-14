"""Comprehensive tests for PawControl data manager.

Tests data storage, retrieval, and management functionality
for all data types to achieve 95%+ test coverage.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DATA_VERSION,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.data_manager import (
    DataValidationError,
    PawControlDataManager,
    StorageError,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util


@pytest.fixture
def data_manager(hass: HomeAssistant) -> PawControlDataManager:
    """Create a data manager for testing."""
    manager = PawControlDataManager(hass)
    manager._dogs = [
        {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
        {CONF_DOG_ID: "max", CONF_DOG_NAME: "Max"},
    ]
    return manager


@pytest.fixture
def mock_storage():
    """Create a mock storage."""
    storage = MagicMock()
    storage.async_load = AsyncMock(return_value=None)
    storage.async_save = AsyncMock()
    return storage


async def test_data_manager_initialization(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test data manager initialization."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

    # Verify storage was loaded
    mock_storage.async_load.assert_called_once()

    # Verify initial data structure
    assert "buddy" in data_manager._data
    assert "max" in data_manager._data
    assert "version" in data_manager._data
    assert data_manager._data["version"] == DATA_VERSION


async def test_data_manager_load_existing_data(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test loading existing data from storage."""
    existing_data = {
        "version": DATA_VERSION,
        "buddy": {
            MODULE_FEEDING: {
                "last_feeding": "2024-01-01T12:00:00",
                "total_feedings": 5,
            }
        },
        "max": {},
    }

    mock_storage.async_load.return_value = existing_data

    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

    # Verify data was loaded
    assert data_manager._data["buddy"][MODULE_FEEDING]["total_feedings"] == 5


async def test_data_manager_migrate_old_version(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test migrating data from old version."""
    old_data = {
        "version": 1,  # Old version
        "buddy": {"old_field": "value"},
    }

    mock_storage.async_load.return_value = old_data

    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

    # Verify version was updated
    assert data_manager._data["version"] == DATA_VERSION

    # Verify save was called with migrated data
    mock_storage.async_save.assert_called()


async def test_feed_dog(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test feeding a dog."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Feed the dog
        await data_manager.async_feed_dog("buddy", 250)

    # Verify feeding was recorded
    feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
    assert feeding_data["daily_portions"] == 1
    assert feeding_data["total_amount"] == 250
    assert "last_feeding" in feeding_data


async def test_feed_dog_multiple_times(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test feeding a dog multiple times."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Feed multiple times
        await data_manager.async_feed_dog("buddy", 200)
        await data_manager.async_feed_dog("buddy", 300)
        await data_manager.async_feed_dog("buddy", 250)

    # Verify cumulative data
    feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
    assert feeding_data["daily_portions"] == 3
    assert feeding_data["total_amount"] == 750


async def test_feed_invalid_dog(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test feeding an invalid dog ID."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        with pytest.raises(ValueError, match="Dog invalid_dog not found"):
            await data_manager.async_feed_dog("invalid_dog", 250)


async def test_log_feeding(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test logging feeding details."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Log feeding
        details = {
            "meal_type": "breakfast",
            "portion_size": 250,
            "food_type": "dry",
            "notes": "Regular feeding",
        }
        await data_manager.async_log_feeding("buddy", details)

    # Verify feeding was logged
    feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
    assert feeding_data["last_meal_type"] == "breakfast"
    assert feeding_data["last_portion_size"] == 250
    assert feeding_data["last_food_type"] == "dry"

    # Check history
    assert len(feeding_data["history"]) == 1
    assert feeding_data["history"][0]["meal_type"] == "breakfast"


async def test_start_walk(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test starting a walk."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Start walk
        walk_id = await data_manager.async_start_walk(
            "buddy",
            label="Morning walk",
            location="Park",
        )

    assert walk_id is not None
    assert walk_id.startswith("walk_")

    # Verify walk was started
    walk_data = data_manager._data["buddy"][MODULE_WALK]
    assert walk_data["current_walk"] is not None
    assert walk_data["current_walk"]["walk_id"] == walk_id
    assert walk_data["current_walk"]["label"] == "Morning walk"
    assert walk_data["current_walk"]["location"] == "Park"
    assert walk_data["walk_in_progress"] is True


async def test_start_walk_already_active(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test starting a walk when one is already active."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Start first walk
        await data_manager.async_start_walk("buddy")

        # Try to start another walk
        with pytest.raises(ValueError, match="Walk already in progress"):
            await data_manager.async_start_walk("buddy")


async def test_end_walk(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test ending a walk."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Start walk
        walk_id = await data_manager.async_start_walk("buddy")

        # End walk
        await data_manager.async_end_walk(
            "buddy",
            walk_id,
            distance=1500,
            duration=30,
            notes="Good walk",
        )

    # Verify walk was ended
    walk_data = data_manager._data["buddy"][MODULE_WALK]
    assert walk_data["current_walk"] is None
    assert walk_data["walk_in_progress"] is False
    assert walk_data["daily_walks"] == 1
    assert walk_data["total_distance"] == 1500
    assert walk_data["total_duration"] == 30

    # Check history
    assert len(walk_data["history"]) == 1
    assert walk_data["history"][0]["walk_id"] == walk_id
    assert walk_data["history"][0]["distance"] == 1500


async def test_end_walk_no_active(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test ending a walk when none is active."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        with pytest.raises(ValueError, match="No active walk"):
            await data_manager.async_end_walk("buddy", "walk_123")


async def test_end_walk_wrong_id(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test ending a walk with wrong ID."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Start walk
        await data_manager.async_start_walk("buddy")

        # Try to end with wrong ID
        with pytest.raises(ValueError, match="Walk ID mismatch"):
            await data_manager.async_end_walk("buddy", "wrong_id")


async def test_get_current_walk(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test getting current walk."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # No active walk
        current = await data_manager.async_get_current_walk("buddy")
        assert current is None

        # Start walk
        walk_id = await data_manager.async_start_walk("buddy", label="Test walk")

        # Get active walk
        current = await data_manager.async_get_current_walk("buddy")
        assert current is not None
        assert current["walk_id"] == walk_id
        assert current["label"] == "Test walk"


async def test_log_health(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test logging health data."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Log health data
        health_data = {
            "weight": 30.5,
            "temperature": 38.5,
            "mood": "happy",
            "activity_level": "high",
            "health_status": "good",
            "note": "Regular checkup",
        }
        await data_manager.async_log_health("buddy", health_data)

    # Verify health data was logged
    stored_data = data_manager._data["buddy"][MODULE_HEALTH]
    assert stored_data["weight"] == 30.5
    assert stored_data["temperature"] == 38.5
    assert stored_data["mood"] == "happy"
    assert stored_data["last_update"] is not None

    # Check history
    assert len(stored_data["history"]) == 1
    assert stored_data["history"][0]["weight"] == 30.5


async def test_log_medication(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test logging medication."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Log medication
        med_data = {
            "type": "medication",
            "medication_name": "Antibiotics",
            "dosage": "250mg",
            "notes": "Morning dose",
        }
        await data_manager.async_log_health("buddy", med_data)

    # Verify medication was logged
    health_data = data_manager._data["buddy"][MODULE_HEALTH]
    assert "medications" in health_data
    assert len(health_data["medications"]) == 1
    assert health_data["medications"][0]["name"] == "Antibiotics"


async def test_start_grooming(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test starting grooming."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Start grooming
        grooming_id = await data_manager.async_start_grooming(
            "buddy", {"type": "full_grooming", "notes": "Monthly grooming"}
        )

    assert grooming_id is not None
    assert grooming_id.startswith("grooming_")

    # Verify grooming was started
    health_data = data_manager._data["buddy"][MODULE_HEALTH]
    assert "grooming" in health_data
    assert health_data["grooming"]["last_grooming"] is not None


async def test_reset_dog_daily_stats(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test resetting daily statistics."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add some daily data
        await data_manager.async_feed_dog("buddy", 250)
        await data_manager.async_feed_dog("buddy", 300)
        walk_id = await data_manager.async_start_walk("buddy")
        await data_manager.async_end_walk("buddy", walk_id, distance=1000)

        # Reset daily stats
        await data_manager.async_reset_dog_daily_stats("buddy")

    # Verify stats were reset
    feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
    walk_data = data_manager._data["buddy"][MODULE_WALK]

    assert feeding_data["daily_portions"] == 0
    assert feeding_data["total_amount"] == 0
    assert walk_data["daily_walks"] == 0
    assert walk_data["total_distance"] == 0
    assert walk_data["total_duration"] == 0

    # History should be preserved
    assert len(feeding_data["history"]) > 0
    assert len(walk_data["history"]) > 0


async def test_get_dog_data(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test getting dog data."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add some data
        await data_manager.async_feed_dog("buddy", 250)

        # Get data
        data = await data_manager.async_get_dog_data("buddy")

    assert data is not None
    assert MODULE_FEEDING in data
    assert data[MODULE_FEEDING]["daily_portions"] == 1

    # Get data for invalid dog
    data = await data_manager.async_get_dog_data("invalid")
    assert data is None


async def test_get_module_data(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test getting module-specific data."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add feeding data
        await data_manager.async_feed_dog("buddy", 250)

        # Get module data
        feeding_data = await data_manager.async_get_module_data("buddy", MODULE_FEEDING)

    assert feeding_data is not None
    assert feeding_data["daily_portions"] == 1

    # Get data for invalid module
    data = await data_manager.async_get_module_data("buddy", "invalid_module")
    assert data == {}


async def test_save_data(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test saving data to storage."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Modify data
        await data_manager.async_feed_dog("buddy", 250)

        # Save should be called automatically
        assert mock_storage.async_save.called

        # Verify save data structure
        save_calls = mock_storage.async_save.call_args_list
        saved_data = save_calls[-1][0][0]  # Get last save call data

        assert "version" in saved_data
        assert "buddy" in saved_data
        assert MODULE_FEEDING in saved_data["buddy"]


async def test_save_data_error(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test handling save errors."""
    mock_storage.async_save.side_effect = Exception("Save failed")

    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Operation should still work even if save fails
        await data_manager.async_feed_dog("buddy", 250)

        # Data should be in memory
        feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
        assert feeding_data["daily_portions"] == 1


async def test_history_management(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test history management and cleanup."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add many history entries
        for i in range(150):  # More than max history
            await data_manager.async_log_feeding(
                "buddy", {"meal_type": f"meal_{i}", "portion_size": 250}
            )

    # Verify history is limited
    feeding_data = data_manager._data["buddy"][MODULE_FEEDING]
    assert len(feeding_data["history"]) <= 100  # Max history size

    # Verify most recent entries are kept
    assert feeding_data["history"][-1]["meal_type"] == "meal_149"


async def test_concurrent_operations(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test concurrent operations on data manager."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Simulate concurrent operations
        import asyncio

        async def feed_task():
            await data_manager.async_feed_dog("buddy", 100)

        async def walk_task():
            walk_id = await data_manager.async_start_walk("max")
            await data_manager.async_end_walk("max", walk_id)

        # Run tasks concurrently
        await asyncio.gather(
            feed_task(),
            walk_task(),
            feed_task(),
        )

    # Verify both operations succeeded
    buddy_data = data_manager._data["buddy"][MODULE_FEEDING]
    max_data = data_manager._data["max"][MODULE_WALK]

    assert buddy_data["daily_portions"] == 2
    assert max_data["daily_walks"] == 1


async def test_shutdown(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test data manager shutdown."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add data
        await data_manager.async_feed_dog("buddy", 250)

        # Shutdown
        await data_manager.async_shutdown()

    # Verify final save was called
    assert mock_storage.async_save.called

    # Verify data manager is marked as shut down
    assert data_manager._shutdown is True


async def test_validation_errors(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test data validation errors."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Test negative portion size
        with pytest.raises(ValueError, match="Invalid portion size"):
            await data_manager.async_feed_dog("buddy", -100)

        # Test invalid walk distance
        walk_id = await data_manager.async_start_walk("buddy")
        with pytest.raises(ValueError, match="Invalid distance"):
            await data_manager.async_end_walk("buddy", walk_id, distance=-500)

        # Test invalid duration
        with pytest.raises(ValueError, match="Invalid duration"):
            await data_manager.async_end_walk("buddy", walk_id, duration=-10)


async def test_statistics_calculation(
    hass: HomeAssistant,
    data_manager: PawControlDataManager,
    mock_storage,
) -> None:
    """Test statistics calculation."""
    with patch(
        "custom_components.pawcontrol.data_manager.Store", return_value=mock_storage
    ):
        await data_manager.async_initialize()

        # Add data for statistics
        await data_manager.async_feed_dog("buddy", 250)
        await data_manager.async_feed_dog("buddy", 300)
        await data_manager.async_feed_dog("max", 200)

        walk_id = await data_manager.async_start_walk("buddy")
        await data_manager.async_end_walk("buddy", walk_id, distance=1500, duration=30)

        # Get statistics
        stats = await data_manager.async_get_statistics()

    assert stats["total_dogs"] == 2
    assert stats["total_feedings"] == 3
    assert stats["total_walks"] == 1
    assert stats["total_food_amount"] == 750
    assert stats["total_walk_distance"] == 1500
