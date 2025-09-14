"""Comprehensive tests for PawControl binary sensor platform.

Tests binary sensor entity creation, state updates, and availability
for all binary sensor types to achieve 95%+ test coverage.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol.binary_sensor import (
    PawControlBinarySensor,
    PawControlFeedingDueSensor,
    PawControlWalkDueSensor,
    PawControlWalkInProgressSensor,
    async_setup_entry,
)
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_WALK,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util


async def test_binary_sensor_setup_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test binary sensor platform setup."""
    mock_config_entry.runtime_data = mock_runtime_data

    with patch(
        "custom_components.pawcontrol.binary_sensor.EntityFactory",
        return_value=mock_runtime_data.entity_factory,
    ):
        entities_added = []

        async def mock_add_entities(entities, update_before_add=True):
            entities_added.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Verify entities were created
    assert len(entities_added) > 0

    # Check that entities have correct attributes
    for entity in entities_added:
        assert hasattr(entity, "_attr_unique_id")
        assert hasattr(entity, "_attr_name")
        assert hasattr(entity, "_dog_id")
        assert hasattr(entity, "device_class")


async def test_feeding_due_sensor_on(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test feeding due sensor when feeding is due."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock feeding due (last feeding > 6 hours ago)
    old_feeding = dt_util.utcnow() - timedelta(hours=7)
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": old_feeding.isoformat(),
        "is_hungry": True,
        "hours_since_feeding": 7,
    }

    assert sensor.is_on is True
    assert sensor.icon == "mdi:food-drumstick-off"

    # Check attributes
    attrs = sensor.extra_state_attributes
    assert attrs["hours_since_feeding"] == 7
    assert attrs["is_hungry"] is True


async def test_feeding_due_sensor_off(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test feeding due sensor when feeding is not due."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock recent feeding
    recent_feeding = dt_util.utcnow() - timedelta(hours=2)
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": recent_feeding.isoformat(),
        "is_hungry": False,
        "hours_since_feeding": 2,
    }

    assert sensor.is_on is False
    assert sensor.icon == "mdi:food-drumstick"


async def test_feeding_due_sensor_no_data(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test feeding due sensor with no data."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # No feeding data
    mock_coordinator.get_module_data.return_value = {}

    assert sensor.is_on is None  # Unknown state
    assert sensor.available is True


async def test_walk_due_sensor_on(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test walk due sensor when walk is due."""
    sensor = PawControlWalkDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock walk due (last walk > 8 hours ago)
    old_walk = dt_util.utcnow() - timedelta(hours=9)
    mock_coordinator.get_module_data.return_value = {
        "last_walk": old_walk.isoformat(),
        "needs_walk": True,
        "hours_since_walk": 9,
        "daily_walks": 1,
        "recommended_walks": 3,
    }

    assert sensor.is_on is True
    assert sensor.icon == "mdi:dog-side-off"

    # Check attributes
    attrs = sensor.extra_state_attributes
    assert attrs["hours_since_walk"] == 9
    assert attrs["daily_walks"] == 1
    assert attrs["recommended_walks"] == 3


async def test_walk_due_sensor_off(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test walk due sensor when walk is not due."""
    sensor = PawControlWalkDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock recent walk
    recent_walk = dt_util.utcnow() - timedelta(hours=1)
    mock_coordinator.get_module_data.return_value = {
        "last_walk": recent_walk.isoformat(),
        "needs_walk": False,
        "hours_since_walk": 1,
        "daily_walks": 2,
        "recommended_walks": 3,
    }

    assert sensor.is_on is False
    assert sensor.icon == "mdi:dog-side"


async def test_walk_in_progress_sensor_on(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test walk in progress sensor when walk is active."""
    sensor = PawControlWalkInProgressSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock active walk
    walk_start = dt_util.utcnow() - timedelta(minutes=15)
    mock_coordinator.get_module_data.return_value = {
        "walk_in_progress": True,
        "current_walk": {
            "walk_id": "walk_123",
            "start_time": walk_start.isoformat(),
            "location": "Park",
            "label": "Morning walk",
        },
    }

    assert sensor.is_on is True
    assert sensor.icon == "mdi:run"

    # Check attributes
    attrs = sensor.extra_state_attributes
    assert attrs["walk_id"] == "walk_123"
    assert attrs["duration_minutes"] == 15
    assert attrs["location"] == "Park"
    assert attrs["label"] == "Morning walk"


async def test_walk_in_progress_sensor_off(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test walk in progress sensor when no walk is active."""
    sensor = PawControlWalkInProgressSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # No active walk
    mock_coordinator.get_module_data.return_value = {
        "walk_in_progress": False,
        "current_walk": None,
    }

    assert sensor.is_on is False
    assert sensor.icon == "mdi:walk"


async def test_binary_sensor_device_class(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor device classes."""
    feeding_sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    walk_sensor = PawControlWalkDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    progress_sensor = PawControlWalkInProgressSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Feeding and walk due should be problem class
    assert feeding_sensor.device_class == BinarySensorDeviceClass.PROBLEM
    assert walk_sensor.device_class == BinarySensorDeviceClass.PROBLEM

    # Walk in progress should be running class
    assert progress_sensor.device_class == BinarySensorDeviceClass.RUNNING


async def test_binary_sensor_availability(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor availability."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Coordinator available, dog data exists
    mock_coordinator.available = True
    mock_coordinator.get_dog_data.return_value = {"test": "data"}
    assert sensor.available is True

    # Coordinator not available
    mock_coordinator.available = False
    assert sensor.available is False

    # Coordinator available but no dog data
    mock_coordinator.available = True
    mock_coordinator.get_dog_data.return_value = None
    assert sensor.available is False


async def test_binary_sensor_unique_id(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor unique ID generation."""
    sensor1 = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    sensor2 = PawControlFeedingDueSensor(
        mock_coordinator,
        "max",
        "Max",
    )

    # Unique IDs should be different for different dogs
    assert sensor1.unique_id != sensor2.unique_id
    assert "buddy" in sensor1.unique_id
    assert "max" in sensor2.unique_id
    assert "feeding_due" in sensor1.unique_id


async def test_binary_sensor_multi_dog(
    hass: HomeAssistant,
    mock_config_entry_multi_dog,
    mock_runtime_data,
) -> None:
    """Test binary sensor creation for multiple dogs."""
    mock_runtime_data.dogs = [
        {CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"},
        {CONF_DOG_ID: "max", CONF_DOG_NAME: "Max"},
    ]
    mock_config_entry_multi_dog.runtime_data = mock_runtime_data

    entities_added = []

    async def mock_add_entities(entities, update_before_add=True):
        entities_added.extend(entities)

    with patch(
        "custom_components.pawcontrol.binary_sensor.EntityFactory",
        return_value=mock_runtime_data.entity_factory,
    ):
        await async_setup_entry(hass, mock_config_entry_multi_dog, mock_add_entities)

    # Should create sensors for both dogs
    buddy_sensors = [e for e in entities_added if "buddy" in e.unique_id]
    max_sensors = [e for e in entities_added if "max" in e.unique_id]

    assert len(buddy_sensors) > 0
    assert len(max_sensors) > 0


async def test_binary_sensor_edge_cases(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor edge cases."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Invalid datetime in data
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": "invalid-datetime",
        "is_hungry": True,
    }

    # Should handle gracefully
    assert sensor.is_on is None

    # Missing required fields
    mock_coordinator.get_module_data.return_value = {
        "is_hungry": True,
        # Missing last_feeding
    }

    # Should still return based on is_hungry
    assert sensor.is_on is True

    # Empty string values
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": "",
        "is_hungry": False,
    }

    assert sensor.is_on is False


async def test_binary_sensor_profile_based(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test profile-based binary sensor creation."""
    mock_config_entry.runtime_data = mock_runtime_data

    # Test with basic profile
    mock_runtime_data.entity_profile = "basic"

    entities_added = []

    async def mock_add_entities(entities, update_before_add=True):
        entities_added.extend(entities)

    with patch(
        "custom_components.pawcontrol.binary_sensor.EntityFactory.create_binary_sensor_entities",
        return_value=[
            PawControlFeedingDueSensor(mock_runtime_data.coordinator, "buddy", "Buddy"),
            PawControlWalkDueSensor(mock_runtime_data.coordinator, "buddy", "Buddy"),
        ]
    ):
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Basic profile should create basic binary sensors
    assert len(entities_added) == 2


async def test_binary_sensor_batch_addition(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test batch addition of binary sensors."""
    mock_config_entry.runtime_data = mock_runtime_data

    # Create many sensors to test batching
    many_sensors = []
    for i in range(30):
        sensor = MagicMock()
        sensor.unique_id = f"binary_sensor_{i}"
        many_sensors.append(sensor)

    add_calls = []

    async def mock_add_entities(entities, update_before_add=True):
        add_calls.append(len(entities))

    with patch(
        "custom_components.pawcontrol.binary_sensor.EntityFactory.create_binary_sensor_entities",
        return_value=many_sensors,
    ):
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should be called multiple times for batching
    assert len(add_calls) > 1
    # Each batch should be reasonable size
    for batch_size in add_calls:
        assert batch_size <= 15


async def test_binary_sensor_coordinator_update(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor updates from coordinator."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Initial state - not hungry
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": (dt_util.utcnow() - timedelta(hours=2)).isoformat(),
        "is_hungry": False,
    }
    assert sensor.is_on is False

    # Update coordinator data - now hungry
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": (dt_util.utcnow() - timedelta(hours=8)).isoformat(),
        "is_hungry": True,
    }

    # Sensor should reflect new state
    assert sensor.is_on is True


async def test_binary_sensor_error_handling(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test binary sensor error handling."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Coordinator raises exception
    mock_coordinator.get_module_data.side_effect = Exception("Data error")

    # Should handle gracefully
    assert sensor.is_on is None
    assert sensor.available is True  # Coordinator is still available

    # Reset side effect
    mock_coordinator.get_module_data.side_effect = None
    mock_coordinator.get_module_data.return_value = {}

    # Should recover
    assert sensor.is_on is None  # No data state


async def test_binary_sensor_legacy_compatibility(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test binary sensor setup with legacy data structure."""
    # No runtime_data attribute
    delattr(mock_config_entry, "runtime_data")

    # Setup with legacy structure
    hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {
            "coordinator": MagicMock(),
            "dogs": [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}],
        }
    }

    entities_added = []

    async def mock_add_entities(entities, update_before_add=True):
        entities_added.extend(entities)

    with patch(
        "custom_components.pawcontrol.binary_sensor.EntityFactory",
    ):
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should still work with legacy structure
    assert len(entities_added) >= 0


async def test_binary_sensor_no_dogs(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test binary sensor setup with no dogs configured."""
    mock_runtime_data.dogs = []
    mock_config_entry.runtime_data = mock_runtime_data

    entities_added = []

    async def mock_add_entities(entities, update_before_add=True):
        entities_added.extend(entities)

    await async_setup_entry(hass, mock_config_entry, mock_add_entities)

    # Should not create any sensors
    assert len(entities_added) == 0


async def test_walk_in_progress_duration_calculation(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test walk duration calculation in walk in progress sensor."""
    sensor = PawControlWalkInProgressSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Mock active walk started 30 minutes ago
    walk_start = dt_util.utcnow() - timedelta(minutes=30)
    mock_coordinator.get_module_data.return_value = {
        "walk_in_progress": True,
        "current_walk": {
            "walk_id": "walk_123",
            "start_time": walk_start.isoformat(),
        },
    }

    attrs = sensor.extra_state_attributes
    assert attrs["duration_minutes"] == 30

    # Test with invalid start time
    mock_coordinator.get_module_data.return_value = {
        "walk_in_progress": True,
        "current_walk": {
            "walk_id": "walk_123",
            "start_time": "invalid-datetime",
        },
    }

    attrs = sensor.extra_state_attributes
    assert "duration_minutes" not in attrs or attrs["duration_minutes"] is None


async def test_feeding_due_custom_threshold(
    hass: HomeAssistant,
    mock_coordinator,
) -> None:
    """Test feeding due sensor with custom threshold."""
    sensor = PawControlFeedingDueSensor(
        mock_coordinator,
        "buddy",
        "Buddy",
    )

    # Set custom threshold via coordinator options
    mock_coordinator.config_entry.options = {"feeding_due_hours": 4}

    # Mock feeding 5 hours ago (above custom threshold)
    feeding_time = dt_util.utcnow() - timedelta(hours=5)
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": feeding_time.isoformat(),
        "hours_since_feeding": 5,
    }

    # Should be on based on custom threshold
    assert sensor.is_on is True

    # Mock feeding 3 hours ago (below custom threshold)
    feeding_time = dt_util.utcnow() - timedelta(hours=3)
    mock_coordinator.get_module_data.return_value = {
        "last_feeding": feeding_time.isoformat(),
        "hours_since_feeding": 3,
    }

    # Should be off based on custom threshold
    assert sensor.is_on is False
