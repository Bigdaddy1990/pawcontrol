"""Test PawControl entities."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from custom_components.pawcontrol.compat import EntityCategory
from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME, DOMAIN
from custom_components.pawcontrol.entity import (
    PawControlBinarySensorEntity,
    PawControlEntity,
    PawControlSensorEntity,
)

if TYPE_CHECKING:
    pass

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator._dog_data = {
        "test_dog": {
            "walk": {"walks_today": 3, "total_distance_today": 5000},
            "feeding": {"total_portions_today": 400},
            "health": {"weight_kg": 25.5},
        }
    }
    coordinator.get_dog_data = lambda dog_id: coordinator._dog_data.get(dog_id, {})
    return coordinator


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = {
        "dogs": [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Buddy",
                "breed": "Labrador",
                "age": 5,
                "weight": 25.5,
            }
        ]
    }
    return entry


def test_pawcontrol_entity_base(mock_coordinator, mock_entry):
    """Test PawControlEntity base class."""
    entity = PawControlEntity(
        mock_coordinator,
        mock_entry,
        "test_dog",
        "test_sensor",
        "test_translation",
    )

    # Test attributes
    assert entity.unique_id == "test_entry_test_dog_test_sensor"
    assert entity.dog_id == "test_dog"
    assert entity.dog_name == "Buddy"
    assert entity._attr_has_entity_name is True
    assert entity._attr_translation_key == "test_translation"

    # Test device info
    device_info = entity.device_info
    assert device_info.identifiers == {(DOMAIN, "test_dog")}
    assert "Buddy" in device_info.name
    assert device_info.manufacturer == "Paw Control"

    # Test availability
    assert entity.available is True

    # Test dog data access
    assert entity.dog_data == mock_coordinator._dog_data["test_dog"]


def test_pawcontrol_entity_unavailable(mock_coordinator, mock_entry):
    """Test entity unavailability when dog not in coordinator."""
    entity = PawControlEntity(
        mock_coordinator,
        mock_entry,
        "unknown_dog",
        "test_sensor",
    )

    # Should be unavailable for unknown dog
    assert entity.available is False


def test_pawcontrol_sensor_entity(mock_coordinator, mock_entry):
    """Test PawControlSensorEntity with attributes."""
    entity = PawControlSensorEntity(
        mock_coordinator,
        mock_entry,
        "test_dog",
        "weight",
        translation_key="weight",
        device_class="weight",
        state_class="measurement",
        unit_of_measurement="kg",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    # Test sensor-specific attributes
    assert entity._attr_device_class == "weight"
    assert entity._attr_state_class == "measurement"
    assert entity._attr_native_unit_of_measurement == "kg"
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC


def test_pawcontrol_binary_sensor_entity(mock_coordinator, mock_entry):
    """Test PawControlBinarySensorEntity with attributes."""
    entity = PawControlBinarySensorEntity(
        mock_coordinator,
        mock_entry,
        "test_dog",
        "needs_walk",
        translation_key="needs_walk",
        device_class="problem",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    # Test binary sensor-specific attributes
    assert entity._attr_device_class == "problem"
    assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC


def test_entity_translation_key_default(mock_coordinator, mock_entry):
    """Test that translation key defaults to entity key if not provided."""
    entity = PawControlEntity(
        mock_coordinator,
        mock_entry,
        "test_dog",
        "my_entity_key",
        None,  # No translation key provided
    )

    # Should use entity_key as translation_key
    assert entity._attr_translation_key == "my_entity_key"


def test_entity_dog_config_retrieval(mock_coordinator, mock_entry):
    """Test dog configuration retrieval from entry options."""
    entity = PawControlEntity(
        mock_coordinator,
        mock_entry,
        "test_dog",
        "test_sensor",
    )

    dog_config = entity._get_dog_config()
    assert dog_config[CONF_DOG_ID] == "test_dog"
    assert dog_config[CONF_DOG_NAME] == "Buddy"
    assert dog_config["breed"] == "Labrador"
    assert dog_config["age"] == 5


def test_entity_dog_config_not_found(mock_coordinator, mock_entry):
    """Test dog configuration when dog not in options."""
    entity = PawControlEntity(
        mock_coordinator,
        mock_entry,
        "unknown_dog",
        "test_sensor",
    )

    dog_config = entity._get_dog_config()
    assert dog_config == {}
    assert entity.dog_name == "unknown_dog"  # Falls back to dog_id
