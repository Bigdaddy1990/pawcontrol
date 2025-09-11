"""Test configuration and fixtures for Paw Control integration."""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from types import MappingProxyType
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

import sitecustomize
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import DOMAIN

# Manually load required pytest plugins
pytest_plugins = ["pytest_cov", "pytest_asyncio"]

# Ensure custom Home Assistant stubs are loaded


@pytest.fixture
def event_loop():
    """Create a new event loop for each test."""
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def hass(event_loop):
    """Return a minimal HomeAssistant instance."""
    instance = HomeAssistant(config_dir=None)  # config_dir added
    instance.loop = event_loop
    return instance


@pytest.fixture
def mock_config_entry():
    """Return a mock config entry using the proper import."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    return MockConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Test Paw Control",
        data={
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "dog_breed": "Test Breed",
                    "dog_age": 5,
                    "dog_weight": 25.0,
                    "dog_size": "medium",
                    "modules": {
                        "feeding": True,
                        "walk": True,
                        "health": True,
                        "gps": False,
                    },
                }
            ]
        },
        options={},
        entry_id="test_entry_id",
        source="test",
        unique_id="test_unique_id",
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
    )


@pytest.fixture
def mock_dog_config():
    """Return mock dog configuration."""
    return {
        CONF_DOG_ID: "test_dog",
        CONF_DOG_NAME: "Test Dog",
        "dog_breed": "Golden Retriever",
        "dog_age": 5,
        "dog_weight": 25.0,
        "dog_size": "medium",
        "dog_color": "golden",
        "modules": {
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": True,
        },
    }


@pytest.fixture
def mock_coordinator():
    """Return a mock coordinator."""
    coordinator = Mock()
    coordinator.data = {
        "test_dog": {
            "dog_info": {"dog_id": "test_dog", "dog_name": "Test Dog"},
            "feeding": {"last_feeding": None, "total_feedings_today": 0},
            "walk": {"walk_in_progress": False, "walks_today": 0},
            "health": {"current_weight": 25.0, "health_status": "good"},
            "gps": {"latitude": None, "longitude": None},
        }
    }
    coordinator.async_config_entry_first_refresh = AsyncMock()
    coordinator.async_refresh = AsyncMock()
    coordinator.async_update_listeners = Mock()
    coordinator.get_module_data = Mock(return_value={})
    return coordinator


@pytest.fixture
def mock_data_manager():
    """Return a mock data manager."""
    data_manager = AsyncMock()
    data_manager.async_initialize.return_value = None
    data_manager.async_shutdown.return_value = None
    data_manager.async_get_dog_data.return_value = {"test": "data"}
    data_manager.async_log_feeding.return_value = None
    data_manager.async_start_walk.return_value = "walk_123"
    data_manager.async_end_walk.return_value = None
    data_manager.async_log_health.return_value = None
    return data_manager


@pytest.fixture
def mock_notification_manager():
    """Return a mock notification manager."""
    notification_manager = AsyncMock()
    notification_manager.async_initialize.return_value = None
    notification_manager.async_shutdown.return_value = None
    notification_manager.async_send_test_notification.return_value = True
    return notification_manager


@pytest.fixture
def mock_runtime_data(
    mock_coordinator, mock_data_manager, mock_notification_manager, mock_config_entry
):
    """Return mock runtime data."""
    return {
        "coordinator": mock_coordinator,
        "data_manager": mock_data_manager,
        "notification_manager": mock_notification_manager,
        "config_entry": mock_config_entry,
        "dogs": [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
            }
        ],
    }


@pytest.fixture
def mock_hass_data(mock_runtime_data):
    """Return mock hass.data structure."""
    return {DOMAIN: {"test_entry_id": mock_runtime_data}}


@pytest.fixture
def mock_gps_data():
    """Return mock GPS data."""
    return {
        "latitude": 52.5200,
        "longitude": 13.4050,
        "accuracy": 10.0,
        "timestamp": dt_util.utcnow().isoformat(),
        "source": "test",
    }


@pytest.fixture
def mock_feeding_data():
    """Return mock feeding data."""
    return {
        "meal_type": "breakfast",
        "portion_size": 200.0,
        "food_type": "dry_food",
        "notes": "Test feeding",
        "calories": 300.0,
    }


@pytest.fixture
def mock_walk_data():
    """Return mock walk data."""
    return {
        "label": "Morning walk",
        "location": "Park",
        "walk_type": "regular",
        "planned_duration": 30,
        "planned_distance": 2000.0,
    }


@pytest.fixture
def mock_health_data():
    """Return mock health data."""
    return {
        "weight": 25.5,
        "temperature": 38.5,
        "mood": "happy",
        "activity_level": "normal",
        "health_status": "good",
        "note": "Test health check",
    }


@pytest.fixture
def mock_datetime():
    """Return a fixed datetime for testing."""
    return datetime(2025, 1, 15, 12, 0, 0)


@pytest.fixture
def setup_integration(hass: HomeAssistant, mock_config_entry):
    """Set up the integration with mocked dependencies."""

    async def _setup():
        # Mock the coordinator, data manager, and notification manager
        with (
            patch("custom_components.pawcontrol.PawControlCoordinator"),
            patch("custom_components.pawcontrol.PawControlDataManager"),
            patch("custom_components.pawcontrol.PawControlNotificationManager"),
        ):
            # Add the config entry
            mock_config_entry.add_to_hass(hass)

            # Import and setup the integration
            from custom_components.pawcontrol import async_setup_entry

            result = await async_setup_entry(hass, mock_config_entry)
            await hass.async_block_till_done()

            return result

    return _setup
