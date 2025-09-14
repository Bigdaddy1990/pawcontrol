"""Fixtures for PawControl integration tests.

Provides comprehensive test fixtures for achieving 95%+ test coverage
as required for Platinum quality scale compliance.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Final
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.types import (
    DogConfigData,
    PawControlConfigEntry,
    PawControlRuntimeData,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

pytest_plugins = "pytest_homeassistant_custom_component"

# Test constants
TEST_DOG_ID: Final = "buddy"
TEST_DOG_NAME: Final = "Buddy"
TEST_DOG_ID_2: Final = "max"
TEST_DOG_NAME_2: Final = "Max"


@pytest.fixture
def mock_setup_entry() -> AsyncMock:
    """Return a mocked setup entry."""
    return AsyncMock(return_value=True)


@pytest.fixture
def mock_config_entry() -> ConfigEntry:
    """Return a mock config entry."""
    return ConfigEntry(
        domain=DOMAIN,
        title="Paw Control (standard)",
        data={
            CONF_NAME: "Paw Control",
            CONF_DOGS: [
                {
                    CONF_DOG_ID: TEST_DOG_ID,
                    CONF_DOG_NAME: TEST_DOG_NAME,
                    CONF_DOG_BREED: "Golden Retriever",
                    CONF_DOG_AGE: 3,
                    CONF_DOG_WEIGHT: 30.5,
                    CONF_DOG_SIZE: "large",
                    CONF_MODULES: {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                }
            ],
            "entity_profile": "standard",
        },
        options={
            "entity_profile": "standard",
            "dashboard_enabled": True,
            "dashboard_auto_create": True,
        },
        entry_id="test_entry_id",
        version=1,
        minor_version=2,
        unique_id="paw_control",
    )


@pytest.fixture
def mock_config_entry_multi_dog() -> ConfigEntry:
    """Return a mock config entry with multiple dogs."""
    return ConfigEntry(
        domain=DOMAIN,
        title="Paw Control (advanced)",
        data={
            CONF_NAME: "Paw Control",
            CONF_DOGS: [
                {
                    CONF_DOG_ID: TEST_DOG_ID,
                    CONF_DOG_NAME: TEST_DOG_NAME,
                    CONF_DOG_BREED: "Golden Retriever",
                    CONF_DOG_AGE: 3,
                    CONF_DOG_WEIGHT: 30.5,
                    CONF_DOG_SIZE: "large",
                    CONF_MODULES: {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                },
                {
                    CONF_DOG_ID: TEST_DOG_ID_2,
                    CONF_DOG_NAME: TEST_DOG_NAME_2,
                    CONF_DOG_BREED: "German Shepherd",
                    CONF_DOG_AGE: 5,
                    CONF_DOG_WEIGHT: 35.0,
                    CONF_DOG_SIZE: "large",
                    CONF_MODULES: {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                },
            ],
            "entity_profile": "advanced",
        },
        options={
            "entity_profile": "advanced",
            "dashboard_enabled": True,
            "dashboard_auto_create": False,
        },
        entry_id="test_entry_multi",
        version=1,
        minor_version=2,
        unique_id="paw_control_multi",
    )


@pytest.fixture
def mock_coordinator():
    """Return a mock coordinator."""
    coordinator = MagicMock()
    coordinator.available = True
    coordinator.last_update_success = True
    coordinator.config_entry = MagicMock()
    coordinator.session = MagicMock()

    # Mock data methods
    coordinator.get_dog_data = MagicMock(
        return_value={
            "dog_info": {
                CONF_DOG_ID: TEST_DOG_ID,
                CONF_DOG_NAME: TEST_DOG_NAME,
                CONF_DOG_BREED: "Golden Retriever",
            },
            MODULE_FEEDING: {
                "last_feeding": "2024-01-01T12:00:00",
                "next_feeding": "2024-01-01T18:00:00",
                "daily_portions": 2,
                "is_hungry": False,
            },
            MODULE_WALK: {
                "last_walk": "2024-01-01T14:00:00",
                "current_walk": None,
                "daily_walks": 2,
                "walk_in_progress": False,
            },
            MODULE_GPS: {
                "latitude": 52.520008,
                "longitude": 13.404954,
                "accuracy": 10,
                "zone": "home",
            },
            MODULE_HEALTH: {
                "weight": 30.5,
                "health_status": "good",
                "health_alerts": [],
            },
        }
    )

    coordinator.get_dog_config = MagicMock(
        return_value={
            CONF_DOG_ID: TEST_DOG_ID,
            CONF_DOG_NAME: TEST_DOG_NAME,
            CONF_DOG_BREED: "Golden Retriever",
            CONF_DOG_AGE: 3,
            CONF_DOG_WEIGHT: 30.5,
            CONF_DOG_SIZE: "large",
            CONF_MODULES: {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            },
        }
    )

    coordinator.get_module_data = MagicMock(
        side_effect=lambda dog_id, module: coordinator.get_dog_data(dog_id).get(
            module, {}
        )
    )

    coordinator.get_dog_ids = MagicMock(return_value=[TEST_DOG_ID])
    coordinator.get_enabled_modules = MagicMock(
        return_value={MODULE_FEEDING, MODULE_WALK, MODULE_GPS, MODULE_HEALTH}
    )
    coordinator.is_module_enabled = MagicMock(return_value=True)
    coordinator.async_request_selective_refresh = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_shutdown = AsyncMock()

    return coordinator


@pytest.fixture
def mock_data_manager():
    """Return a mock data manager."""
    manager = MagicMock()
    manager.async_initialize = AsyncMock()
    manager.async_shutdown = AsyncMock()
    manager.async_feed_dog = AsyncMock()
    manager.async_log_feeding = AsyncMock()
    manager.async_start_walk = AsyncMock(return_value="walk_123")
    manager.async_end_walk = AsyncMock()
    manager.async_get_current_walk = AsyncMock(return_value=None)
    manager.async_log_health = AsyncMock()
    manager.async_start_grooming = AsyncMock(return_value="grooming_456")
    manager.async_reset_dog_daily_stats = AsyncMock()

    return manager


@pytest.fixture
def mock_notification_manager():
    """Return a mock notification manager."""
    manager = MagicMock()
    manager.async_initialize = AsyncMock()
    manager.async_shutdown = AsyncMock()
    manager.async_send_notification = AsyncMock()

    return manager


@pytest.fixture
def mock_feeding_manager():
    """Return a mock feeding manager."""
    manager = MagicMock()
    manager.async_initialize = AsyncMock()
    manager.async_shutdown = AsyncMock()
    manager.async_add_feeding = AsyncMock(return_value=MagicMock(time=datetime.now()))
    manager._configs = {
        TEST_DOG_ID: MagicMock(
            calculate_portion_size=MagicMock(return_value=250.0),
            health_aware_portions=True,
        )
    }
    manager._invalidate_cache = MagicMock()

    return manager


@pytest.fixture
def mock_walk_manager():
    """Return a mock walk manager."""
    manager = MagicMock()
    manager.async_initialize = AsyncMock()
    manager.async_shutdown = AsyncMock()

    return manager


@pytest.fixture
def mock_entity_factory():
    """Return a mock entity factory."""
    factory = MagicMock()
    factory.estimate_entity_count = MagicMock()

    return factory


@pytest.fixture
def mock_runtime_data(
    mock_coordinator,
    mock_data_manager,
    mock_notification_manager,
    mock_feeding_manager,
    mock_walk_manager,
    mock_entity_factory,
):
    """Return mock runtime data."""
    return PawControlRuntimeData(
        coordinator=mock_coordinator,
        data_manager=mock_data_manager,
        notification_manager=mock_notification_manager,
        feeding_manager=mock_feeding_manager,
        walk_manager=mock_walk_manager,
        entity_factory=mock_entity_factory,
        entity_profile="standard",
        dogs=[
            {
                CONF_DOG_ID: TEST_DOG_ID,
                CONF_DOG_NAME: TEST_DOG_NAME,
                CONF_DOG_BREED: "Golden Retriever",
                CONF_DOG_AGE: 3,
                CONF_DOG_WEIGHT: 30.5,
                CONF_DOG_SIZE: "large",
            }
        ],
    )


@pytest.fixture
def mock_websession():
    """Return a mock websession."""
    session = MagicMock()
    session.get = AsyncMock()
    session.post = AsyncMock()
    return session


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: ConfigEntry,
    mock_runtime_data: PawControlRuntimeData,
):
    """Set up the PawControl integration for testing."""
    mock_config_entry.add_to_hass(hass)

    # Set runtime data
    mock_config_entry.runtime_data = mock_runtime_data

    # Mock the setup
    with patch(
        "custom_components.pawcontrol.async_setup_entry",
        return_value=True,
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    return mock_config_entry


@pytest.fixture
def mock_health_calculator():
    """Return a mock health calculator."""
    calculator = MagicMock()
    calculator.calculate_health_score = MagicMock(return_value=85)
    calculator.get_recommendations = MagicMock(
        return_value=["More exercise", "Check weight"]
    )

    return calculator


@pytest.fixture
def error_fixture():
    """Return various error scenarios for testing."""
    return {
        "connection_error": ConnectionError("Failed to connect"),
        "timeout_error": TimeoutError("Request timed out"),
        "value_error": ValueError("Invalid value"),
        "key_error": KeyError("Missing key"),
        "api_error": Exception("API error"),
    }


@pytest.fixture
def mock_device_registry():
    """Return a mock device registry."""
    registry = MagicMock()
    registry.async_get_device = MagicMock(
        return_value=MagicMock(
            id="device_123",
            identifiers={(DOMAIN, TEST_DOG_ID)},
            name=TEST_DOG_NAME,
        )
    )
    return registry


@pytest.fixture
def mock_entity_registry():
    """Return a mock entity registry."""
    registry = MagicMock()
    registry.async_get = MagicMock(return_value=None)
    registry.async_get_entity_id = MagicMock(return_value=None)
    return registry


@pytest.fixture
def mock_service_call():
    """Return a mock service call."""
    call = MagicMock()
    call.data = {
        "dog_id": TEST_DOG_ID,
        "meal_type": "breakfast",
        "portion_size": 250,
    }
    return call


@pytest.fixture
def time_fixture():
    """Return various time fixtures for testing."""
    now = dt_util.utcnow()
    return {
        "now": now,
        "yesterday": now - timedelta(days=1),
        "tomorrow": now + timedelta(days=1),
        "last_week": now - timedelta(weeks=1),
        "next_week": now + timedelta(weeks=1),
    }


@pytest.fixture
def dog_data_fixture():
    """Return various dog data scenarios."""
    return {
        "valid_dog": {
            CONF_DOG_ID: "test_dog",
            CONF_DOG_NAME: "Test Dog",
            CONF_DOG_BREED: "Test Breed",
            CONF_DOG_AGE: 5,
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_SIZE: "medium",
        },
        "minimal_dog": {
            CONF_DOG_ID: "min_dog",
            CONF_DOG_NAME: "Min Dog",
        },
        "invalid_dog": {
            CONF_DOG_NAME: "No ID Dog",  # Missing dog_id
        },
    }
