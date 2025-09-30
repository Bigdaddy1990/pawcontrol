"""Global test configuration for PawControl tests.

Provides comprehensive fixtures for testing all PawControl components
with proper mocking and Home Assistant integration.

Quality Scale: Platinum
Python: 3.13+
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest

_REQUIRED_MODULES = (
    "homeassistant",
    "pytest_homeassistant_custom_component",
)

_missing = [
    module for module in _REQUIRED_MODULES if importlib.util.find_spec(module) is None
]

if _missing:
    # Only the Home Assistant integration tests require the optional
    # dependencies.  Unit tests targeting pure python helpers should still run
    # to provide meaningful coverage for CI.
    collect_ignore_glob = [
        "components/*",
    ]

    def pytest_addoption(parser):
        """Register pytest-asyncio compatibility option when dependencies are absent."""
        parser.addini(
            "asyncio_mode",
            "pytest-asyncio compatibility shim for missing dependency",
            default="auto",
        )

    print(
        "Home Assistant test dependencies are unavailable - integration tests under "
        "tests/components are skipped.",
        file=sys.stderr,
    )

else:
    import pytest_homeassistant_custom_component

    pytest_plugins = ("pytest_homeassistant_custom_component",)


# ==============================================================================
# ENHANCED FIXTURES FOR PAWCONTROL TESTING
# ==============================================================================


@pytest.fixture
def mock_dog_config() -> dict[str, Any]:
    """Standard dog configuration for testing.

    Returns:
        Complete dog configuration dictionary
    """
    return {
        "dog_id": "test_dog",
        "dog_name": "Buddy",
        "breed": "Golden Retriever",
        "weight": 30.0,
        "ideal_weight": 28.0,
        "age_months": 48,
        "activity_level": "moderate",
        "health_conditions": [],
        "weight_goal": "maintain",
        "modules": {
            "feeding": True,
            "walk": True,
            "gps": True,
            "health": True,
            "notifications": True,
            "weather": True,
        },
        "feeding_config": {
            "meals_per_day": 2,
            "feeding_times": ["08:00", "18:00"],
            "food_type": "dry",
            "food_brand": "Test Brand",
            "calories_per_100g": 350,
        },
    }


@pytest.fixture
def mock_multi_dog_config(mock_dog_config: dict[str, Any]) -> list[dict[str, Any]]:
    """Multiple dog configurations for testing.

    Args:
        mock_dog_config: Base dog configuration

    Returns:
        List of dog configurations
    """
    dog1 = mock_dog_config.copy()
    dog1["dog_id"] = "buddy"
    dog1["dog_name"] = "Buddy"
    dog1["weight"] = 30.0

    dog2 = mock_dog_config.copy()
    dog2["dog_id"] = "max"
    dog2["dog_name"] = "Max"
    dog2["weight"] = 15.0
    dog2["breed"] = "Beagle"
    dog2["activity_level"] = "high"

    return [dog1, dog2]


@pytest.fixture
def mock_config_entry(mock_dog_config: dict[str, Any]):
    """Mock Home Assistant config entry.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Mock ConfigEntry object
    """
    from homeassistant.config_entries import ConfigEntry

    entry = Mock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.domain = "pawcontrol"
    entry.title = "Test PawControl"
    entry.data = {
        "dogs": [mock_dog_config],
    }
    entry.options = {
        "entity_profile": "standard",
        "external_integrations": False,
        "update_interval": 120,
    }
    entry.version = 1
    entry.minor_version = 0
    entry.state = "loaded"

    return entry


@pytest.fixture
async def mock_hass() -> AsyncGenerator[Any]:
    """Mock Home Assistant instance with proper async support.

    Yields:
        Mock HomeAssistant instance
    """
    from homeassistant.core import HomeAssistant

    hass = Mock(spec=HomeAssistant)
    hass.data = {}
    hass.states = Mock()
    hass.services = Mock()
    hass.bus = Mock()
    hass.config_entries = Mock()
    hass.config = Mock()
    hass.config.latitude = 52.5200
    hass.config.longitude = 13.4050

    # Mock async methods
    hass.async_create_task = AsyncMock()
    hass.services.async_call = AsyncMock()
    hass.bus.async_fire = AsyncMock()

    yield hass


@pytest.fixture
def mock_session():
    """Mock aiohttp ClientSession for API calls.

    Returns:
        Mock ClientSession
    """
    session = Mock()
    session.get = AsyncMock()
    session.post = AsyncMock()
    session.close = AsyncMock()

    return session


@pytest.fixture
async def mock_resilience_manager(mock_hass):
    """Mock ResilienceManager for testing without actual resilience logic.

    Args:
        mock_hass: Mock Home Assistant instance

    Returns:
        Mock ResilienceManager with passthrough execution
    """
    from custom_components.pawcontrol.resilience import ResilienceManager

    manager = Mock(spec=ResilienceManager)

    # Make execute_with_resilience pass through to the actual function
    async def passthrough_execution(func, *args, **kwargs):
        """Execute function without resilience for testing."""
        if len(args) > 0:
            return await func(*args)
        return await func()

    manager.execute_with_resilience = AsyncMock(side_effect=passthrough_execution)
    manager.get_all_circuit_breakers = Mock(return_value={})

    return manager


@pytest.fixture
async def mock_coordinator(
    mock_hass, mock_config_entry, mock_session, mock_resilience_manager
):
    """Mock PawControlCoordinator with all managers.

    Args:
        mock_hass: Mock Home Assistant
        mock_config_entry: Mock config entry
        mock_session: Mock aiohttp session
        mock_resilience_manager: Mock resilience manager

    Returns:
        Mock coordinator instance
    """
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    with patch.object(
        PawControlCoordinator, "resilience_manager", new_callable=PropertyMock
    ) as mock_rm:
        mock_rm.return_value = mock_resilience_manager

        coordinator = PawControlCoordinator(mock_hass, mock_config_entry, mock_session)

        # Set initial data
        coordinator.data = {
            "test_dog": {
                "dog_info": mock_config_entry.data["dogs"][0],
                "status": "online",
                "last_update": datetime.now().isoformat(),
                "feeding": {},
                "walk": {},
                "gps": {},
                "health": {},
            }
        }

        coordinator.last_update_success = True

        yield coordinator


@pytest.fixture
async def mock_feeding_manager(mock_dog_config):
    """Mock FeedingManager for testing.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Initialized FeedingManager
    """
    from custom_components.pawcontrol.feeding_manager import FeedingManager

    manager = FeedingManager()
    await manager.async_initialize([mock_dog_config])

    return manager


@pytest.fixture
async def mock_walk_manager(mock_dog_config):
    """Mock WalkManager for testing.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Initialized WalkManager
    """
    from custom_components.pawcontrol.walk_manager import WalkManager

    manager = WalkManager()
    await manager.async_initialize([mock_dog_config["dog_id"]])

    return manager


@pytest.fixture
async def mock_gps_manager(mock_hass, mock_resilience_manager):
    """Mock GPSGeofenceManager for testing.

    Args:
        mock_hass: Mock Home Assistant
        mock_resilience_manager: Mock resilience manager

    Returns:
        Initialized GPSGeofenceManager
    """
    from custom_components.pawcontrol.gps_manager import GPSGeofenceManager

    manager = GPSGeofenceManager(mock_hass)
    manager.resilience_manager = mock_resilience_manager

    return manager


@pytest.fixture
async def mock_notification_manager(mock_hass, mock_resilience_manager):
    """Mock PawControlNotificationManager for testing.

    Args:
        mock_hass: Mock Home Assistant
        mock_resilience_manager: Mock resilience manager

    Returns:
        Initialized NotificationManager
    """
    from custom_components.pawcontrol.notifications import PawControlNotificationManager

    manager = PawControlNotificationManager(mock_hass, "test_entry")
    manager.resilience_manager = mock_resilience_manager

    await manager.async_initialize()

    return manager


@pytest.fixture
async def mock_data_manager(mock_hass):
    """Mock PawControlDataManager for testing.

    Args:
        mock_hass: Mock Home Assistant

    Returns:
        Initialized DataManager
    """
    from custom_components.pawcontrol.data_manager import PawControlDataManager

    manager = PawControlDataManager(mock_hass, "test_entry")
    await manager.async_initialize()

    return manager


@pytest.fixture
def mock_gps_point():
    """Mock GPS point for testing.

    Returns:
        GPSPoint instance
    """
    from custom_components.pawcontrol.gps_manager import GPSPoint, LocationSource

    return GPSPoint(
        latitude=52.5200,
        longitude=13.4050,
        timestamp=datetime.now(),
        altitude=100.0,
        accuracy=10.0,
        source=LocationSource.DEVICE_TRACKER,
    )


@pytest.fixture
def mock_walk_route(mock_gps_point):
    """Mock walk route for testing.

    Args:
        mock_gps_point: GPS point fixture

    Returns:
        WalkRoute instance
    """
    from custom_components.pawcontrol.gps_manager import GPSPoint, WalkRoute

    route = WalkRoute(
        dog_id="test_dog",
        start_time=datetime.now() - timedelta(hours=1),
        end_time=datetime.now(),
    )

    # Add some GPS points
    for i in range(10):
        point = GPSPoint(
            latitude=52.5200 + (i * 0.001),
            longitude=13.4050 + (i * 0.001),
            timestamp=datetime.now() - timedelta(minutes=60 - i * 6),
            accuracy=10.0,
        )
        route.gps_points.append(point)

    route.total_distance_meters = 1500.0
    route.total_duration_seconds = 3600.0

    return route


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


@pytest.fixture
def assert_valid_dog_data():
    """Helper to assert valid dog data structure.

    Returns:
        Validation function
    """

    def _assert(data: dict[str, Any]) -> None:
        """Validate dog data structure."""
        assert "dog_info" in data
        assert "status" in data
        assert data["status"] in ["online", "offline", "unknown"]

        if "feeding" in data:
            assert isinstance(data["feeding"], dict)

        if "walk" in data:
            assert isinstance(data["walk"], dict)

        if "gps" in data:
            assert isinstance(data["gps"], dict)

    return _assert


@pytest.fixture
def create_feeding_event():
    """Helper to create feeding events.

    Returns:
        Factory function for feeding events
    """

    def _create(
        dog_id: str = "test_dog",
        amount: float = 200.0,
        meal_type: str = "breakfast",
        timestamp: datetime | None = None,
    ) -> dict[str, Any]:
        """Create feeding event data."""
        return {
            "dog_id": dog_id,
            "amount": amount,
            "meal_type": meal_type,
            "timestamp": timestamp or datetime.now(),
            "notes": None,
            "feeder": None,
            "scheduled": False,
        }

    return _create


@pytest.fixture
def create_walk_event():
    """Helper to create walk events.

    Returns:
        Factory function for walk events
    """

    def _create(
        dog_id: str = "test_dog",
        duration_minutes: float = 30.0,
        distance_meters: float = 1500.0,
        walker: str | None = None,
    ) -> dict[str, Any]:
        """Create walk event data."""
        return {
            "dog_id": dog_id,
            "start_time": datetime.now() - timedelta(minutes=duration_minutes),
            "end_time": datetime.now(),
            "duration_minutes": duration_minutes,
            "distance_meters": distance_meters,
            "walker": walker,
            "weather": None,
            "leash_used": True,
        }

    return _create


# ==============================================================================
# PYTEST CONFIGURATION
# ==============================================================================


def pytest_configure(config):
    """Configure pytest with custom markers.

    Args:
        config: Pytest configuration object
    """
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require Home Assistant"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that require Home Assistant"
    )
    config.addinivalue_line("markers", "slow: Slow running tests (> 1 second)")
    config.addinivalue_line("markers", "load: Load testing tests")


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically.

    Args:
        config: Pytest configuration
        items: Test items collected
    """
    for item in items:
        # Auto-mark integration tests
        if "components" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Auto-mark unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
