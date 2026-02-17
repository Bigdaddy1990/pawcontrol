"""Global test configuration for PawControl tests.

Provides comprehensive fixtures for testing all PawControl components with
proper mocking and Home Assistant integration.

Quality scale: Platinum - fixtures mirror Home Assistant behaviour while
remaining lightweight enough to run the full suite (unit, integration,
diagnostics, repairs) in constrained CI environments with >=95 % coverage.
"""

# ruff: noqa: E111

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

from aiohttp import ClientSession
import pytest

from tests.helpers.homeassistant_test_stubs import (
    HomeAssistant as StubHomeAssistant,
    install_homeassistant_stubs,
)

install_homeassistant_stubs()

from custom_components.pawcontrol import compat as pawcontrol_compat

pawcontrol_compat.ensure_homeassistant_config_entry_symbols()
pawcontrol_compat.ensure_homeassistant_exception_symbols()

from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    FeedingManagerDogSetupPayload,
    JSONMutableMapping,
)
from tests.helpers import typed_deepcopy

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry  # noqa: E111

    from custom_components.pawcontrol.feeding_manager import (  # noqa: E111
        FeedingBatchEntry,
        FeedingManager,
    )
    from custom_components.pawcontrol.walk_manager import WalkManager  # noqa: E111


pytest_plugins = (
    "pytest_homeassistant_custom_component",
    "pytest_asyncio",
    "tests.plugins.asyncio_stub",
)


def _run_async(coro):
    try:  # noqa: E111
        asyncio.get_running_loop()
    except RuntimeError:  # noqa: E111
        return asyncio.run(coro)
    runner_loop = asyncio.new_event_loop()  # noqa: E111
    try:  # noqa: E111
        return runner_loop.run_until_complete(coro)
    finally:  # noqa: E111
        runner_loop.close()


@pytest.fixture
def hass() -> StubHomeAssistant:
    """Return a minimal Home Assistant test instance."""  # noqa: E111

    return StubHomeAssistant()  # noqa: E111


# ==============================================================================
# ENHANCED FIXTURES FOR PAWCONTROL TESTING
# ==============================================================================


@pytest.fixture
def mock_dog_config() -> FeedingManagerDogSetupPayload:
    """Standard dog configuration for testing.

    Returns:
        Complete dog configuration mapping for FeedingManager
    """  # noqa: E111
    config: FeedingManagerDogSetupPayload = {  # noqa: E111
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
    return config  # noqa: E111


@pytest.fixture
def mock_multi_dog_config(
    mock_dog_config: FeedingManagerDogSetupPayload,
) -> list[FeedingManagerDogSetupPayload]:
    """Multiple dog configurations for testing.

    Args:
        mock_dog_config: Base dog configuration

    Returns:
        List of dog configuration payloads
    """  # noqa: E111
    dog1 = typed_deepcopy(mock_dog_config)  # noqa: E111
    dog1["dog_id"] = "buddy"  # noqa: E111
    dog1["dog_name"] = "Buddy"  # noqa: E111
    dog1["weight"] = 30.0  # noqa: E111

    dog2 = typed_deepcopy(mock_dog_config)  # noqa: E111
    dog2["dog_id"] = "max"  # noqa: E111
    dog2["dog_name"] = "Max"  # noqa: E111
    dog2["weight"] = 15.0  # noqa: E111
    dog2["breed"] = "Beagle"  # noqa: E111
    dog2["activity_level"] = "high"  # noqa: E111

    return [dog1, dog2]  # noqa: E111


@pytest.fixture
def mock_config_entry(mock_dog_config: FeedingManagerDogSetupPayload) -> ConfigEntry:
    """Mock Home Assistant config entry.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Mock ConfigEntry object
    """  # noqa: E111
    from homeassistant.config_entries import ConfigEntry  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        domain="pawcontrol",
        data={"dogs": [mock_dog_config]},
        options={
            "entity_profile": "standard",
            "external_integrations": False,
            "update_interval": 120,
        },
        title="Test PawControl",
    )

    entry.version = 1  # noqa: E111
    entry.minor_version = 0  # noqa: E111
    entry.state = "loaded"  # noqa: E111

    return entry  # noqa: E111


@pytest.fixture
def mock_hass() -> Any:
    """Mock Home Assistant instance with proper async support."""  # noqa: E111
    from homeassistant.core import HomeAssistant  # noqa: E111

    hass = Mock(spec=HomeAssistant)  # noqa: E111
    hass.data = {}  # noqa: E111
    hass.states = Mock()  # noqa: E111
    hass.services = Mock()  # noqa: E111
    hass.bus = Mock()  # noqa: E111
    hass.config_entries = Mock()  # noqa: E111
    hass.config_entries.async_update_entry = Mock()  # noqa: E111
    hass.config = Mock()  # noqa: E111
    hass.config.latitude = 52.5200  # noqa: E111
    hass.config.longitude = 13.4050  # noqa: E111

    # Mock async methods  # noqa: E114
    hass.async_create_task = AsyncMock()  # noqa: E111
    hass.services.async_call = AsyncMock()  # noqa: E111
    hass.bus.async_fire = AsyncMock()  # noqa: E111

    return hass  # noqa: E111


class _MockClientSession(Mock):
    """Test double that mimics :class:`aiohttp.ClientSession` semantics."""  # noqa: E111

    def __init__(self) -> None:  # noqa: E111
        super().__init__(spec=ClientSession)
        self.closed = False

        async def _close() -> None:
            self.closed = True  # noqa: E111

        self.close = AsyncMock(side_effect=_close)
        self.request = AsyncMock(name="request")
        self.get = AsyncMock(side_effect=self.request, name="get")

        self.put = AsyncMock(side_effect=self.request, name="put")
        self.patch = AsyncMock(side_effect=self.request, name="patch")
        self.delete = AsyncMock(side_effect=self.request, name="delete")
        self.head = AsyncMock(side_effect=self.request, name="head")
        self.options = AsyncMock(side_effect=self.request, name="options")

        def _context_response(*args: Any, **kwargs: Any) -> AsyncMock:
            """Return an async context manager for ``session.post`` usage."""  # noqa: E111

            response = Mock()  # noqa: E111
            response.status = kwargs.get("status", 200)  # noqa: E111
            response.text = AsyncMock(return_value=kwargs.get("text", ""))  # noqa: E111
            response.json = AsyncMock(return_value=kwargs.get("json", {}))  # noqa: E111

            response.read = AsyncMock(return_value=kwargs.get("body", b""))  # noqa: E111

            response_cm = AsyncMock()  # noqa: E111
            response_cm.__aenter__.return_value = response  # noqa: E111
            response_cm.__aexit__.return_value = False  # noqa: E111
            response_cm.call_args = (args, kwargs)  # noqa: E111
            return response_cm  # noqa: E111

        self.post = AsyncMock(side_effect=_context_response, name="post")

        async def _ws_connect(*args: Any, **kwargs: Any) -> AsyncMock:
            """Return an async context manager for websocket usage."""  # noqa: E111

            websocket = AsyncMock()  # noqa: E111
            websocket.closed = False  # noqa: E111
            websocket.close = AsyncMock(name="close")  # noqa: E111
            websocket.send_json = AsyncMock(name="send_json")  # noqa: E111
            websocket.send_str = AsyncMock(name="send_str")  # noqa: E111
            websocket.send_bytes = AsyncMock(name="send_bytes")  # noqa: E111
            websocket.receive_json = AsyncMock(  # noqa: E111
                return_value=kwargs.get("receive_json", {}),
                name="receive_json",
            )
            websocket.receive_str = AsyncMock(  # noqa: E111
                return_value=kwargs.get("receive_str", ""),
                name="receive_str",
            )
            websocket.receive_bytes = AsyncMock(  # noqa: E111
                return_value=kwargs.get("receive_bytes", b""),
                name="receive_bytes",
            )

            ws_cm = AsyncMock()  # noqa: E111
            ws_cm.__aenter__.return_value = websocket  # noqa: E111
            ws_cm.__aexit__.return_value = False  # noqa: E111
            ws_cm.call_args = (args, kwargs)  # noqa: E111
            return ws_cm  # noqa: E111

        self.ws_connect = AsyncMock(side_effect=_ws_connect, name="ws_connect")


@pytest.fixture
def session_factory() -> Callable[..., _MockClientSession]:
    """Return a factory that creates aiohttp session doubles."""  # noqa: E111

    def _factory(*, closed: bool = False) -> _MockClientSession:  # noqa: E111
        session = _MockClientSession()
        session.closed = closed
        return session

    return _factory  # noqa: E111


@pytest.fixture
def mock_session(
    session_factory: Callable[..., _MockClientSession],
) -> _MockClientSession:
    """Return a reusable aiohttp session double for HTTP entry points."""  # noqa: E111

    return session_factory()  # noqa: E111


@pytest.fixture
def mock_resilience_manager(mock_hass):
    """Mock ResilienceManager for testing without actual resilience logic.

    Args:
        mock_hass: Mock Home Assistant instance

    Returns:
        Mock ResilienceManager with passthrough execution
    """  # noqa: E111
    from custom_components.pawcontrol.resilience import ResilienceManager  # noqa: E111

    manager = Mock(spec=ResilienceManager)  # noqa: E111

    # Make execute_with_resilience pass through to the actual function  # noqa: E114
    async def passthrough_execution(func, *args, **kwargs):  # noqa: E111
        """Execute function without resilience for testing."""
        if len(args) > 0:
            return await func(*args)  # noqa: E111
        return await func()

    manager.execute_with_resilience = AsyncMock(  # noqa: E111
        side_effect=passthrough_execution,
    )
    manager.get_all_circuit_breakers = Mock(return_value={})  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_coordinator(
    mock_hass,
    mock_config_entry,
    mock_session,
    mock_resilience_manager,
):
    """Mock PawControlCoordinator with all managers.

    Args:
        mock_hass: Mock Home Assistant
        mock_config_entry: Mock config entry
        mock_session: Mock aiohttp session
        mock_resilience_manager: Mock resilience manager

    Returns:
        Mock coordinator instance
    """  # noqa: E111
    from custom_components.pawcontrol.coordinator import (
        PawControlCoordinator,  # noqa: E111
    )

    coordinator = PawControlCoordinator(  # noqa: E111
        mock_hass,
        mock_config_entry,
        mock_session,
    )
    coordinator.resilience_manager = mock_resilience_manager  # noqa: E111

    coordinator.data = {  # noqa: E111
        "test_dog": {
            "dog_info": mock_config_entry.data["dogs"][0],
            "status": "online",
            "last_update": datetime.now(UTC).isoformat(),
            "feeding": {},
            "walk": {},
            "gps": {},
            "health": {},
        },
    }

    coordinator.last_update_success = True  # noqa: E111

    yield coordinator  # noqa: E111


@pytest.fixture
def mock_feeding_manager(
    mock_dog_config: FeedingManagerDogSetupPayload,
    mock_hass: object,
) -> FeedingManager:
    """Mock FeedingManager for testing.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Initialized FeedingManager
    """  # noqa: E111
    from custom_components.pawcontrol.feeding_manager import FeedingManager  # noqa: E111

    manager = FeedingManager(mock_hass)  # noqa: E111
    _run_async(manager.async_initialize([mock_dog_config]))  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_walk_manager(
    mock_dog_config: FeedingManagerDogSetupPayload,
) -> WalkManager:
    """Mock WalkManager for testing.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Initialized WalkManager
    """  # noqa: E111
    from custom_components.pawcontrol.walk_manager import WalkManager  # noqa: E111

    manager = WalkManager()  # noqa: E111
    _run_async(manager.async_initialize([mock_dog_config["dog_id"]]))  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_gps_manager(mock_hass, mock_resilience_manager):
    """Mock GPSGeofenceManager for testing.

    Args:
        mock_hass: Mock Home Assistant
        mock_resilience_manager: Mock resilience manager

    Returns:
        Initialized GPSGeofenceManager
    """  # noqa: E111
    from custom_components.pawcontrol.gps_manager import GPSGeofenceManager  # noqa: E111

    manager = GPSGeofenceManager(mock_hass)  # noqa: E111
    manager.resilience_manager = mock_resilience_manager  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_notification_manager(mock_hass, mock_resilience_manager, mock_session):
    """Mock PawControlNotificationManager for testing.

    Args:
        mock_hass: Mock Home Assistant
        mock_resilience_manager: Mock resilience manager

    Returns:
        Initialized NotificationManager
    """  # noqa: E111
    from custom_components.pawcontrol.notifications import (
        PawControlNotificationManager,  # noqa: E111
    )

    manager = PawControlNotificationManager(  # noqa: E111
        mock_hass,
        "test_entry",
        session=mock_session,
    )
    manager.resilience_manager = mock_resilience_manager  # noqa: E111

    _run_async(manager.async_initialize())  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_data_manager(mock_hass):
    """Mock PawControlDataManager for testing.

    Args:
        mock_hass: Mock Home Assistant

    Returns:
        Initialized DataManager
    """  # noqa: E111
    from custom_components.pawcontrol.data_manager import (
        PawControlDataManager,  # noqa: E111
    )

    manager = PawControlDataManager(mock_hass, "test_entry")  # noqa: E111
    _run_async(manager.async_initialize())  # noqa: E111

    return manager  # noqa: E111


@pytest.fixture
def mock_gps_point():
    """Mock GPS point for testing.

    Returns:
        GPSPoint instance
    """  # noqa: E111
    from custom_components.pawcontrol.gps_manager import (  # noqa: E111
        GPSPoint,
        LocationSource,
    )

    return GPSPoint(  # noqa: E111
        latitude=52.5200,
        longitude=13.4050,
        timestamp=datetime.now(UTC),
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
    """  # noqa: E111
    from custom_components.pawcontrol.gps_manager import GPSPoint, WalkRoute  # noqa: E111

    route = WalkRoute(  # noqa: E111
        dog_id="test_dog",
        start_time=datetime.now(UTC) - timedelta(hours=1),
        end_time=datetime.now(UTC),
    )

    # Add some GPS points  # noqa: E114
    for i in range(10):  # noqa: E111
        point = GPSPoint(
            latitude=52.5200 + (i * 0.001),
            longitude=13.4050 + (i * 0.001),
            timestamp=datetime.now(UTC) - timedelta(minutes=60 - i * 6),
            accuracy=10.0,
        )
        route.gps_points.append(point)

    route.total_distance_meters = 1500.0  # noqa: E111
    route.total_duration_seconds = 3600.0  # noqa: E111

    return route  # noqa: E111


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


@pytest.fixture
def assert_valid_dog_data():
    """Helper to assert valid dog data structure.

    Returns:
        Validation function
    """  # noqa: E111

    def _assert(data: CoordinatorDogData) -> None:  # noqa: E111
        """Validate dog data structure."""
        assert "dog_info" in data
        assert "status" in data
        assert data["status"] in ["online", "offline", "unknown"]

        if "feeding" in data:
            assert isinstance(data["feeding"], dict)  # noqa: E111

        if "walk" in data:
            assert isinstance(data["walk"], dict)  # noqa: E111

        if "gps" in data:
            assert isinstance(data["gps"], dict)  # noqa: E111

    return _assert  # noqa: E111


@pytest.fixture
def create_feeding_event() -> Callable[..., FeedingBatchEntry]:
    """Helper to create feeding events.

    Returns:
        Factory function for feeding events
    """  # noqa: E111

    def _create(  # noqa: E111
        dog_id: str = "test_dog",
        amount: float = 200.0,
        meal_type: str = "breakfast",
        timestamp: datetime | None = None,
    ) -> FeedingBatchEntry:
        """Create feeding event data."""
        from custom_components.pawcontrol.feeding_manager import FeedingBatchEntry

        event: FeedingBatchEntry = {
            "dog_id": dog_id,
            "amount": amount,
            "meal_type": meal_type,
            "timestamp": timestamp or datetime.now(UTC),
            "notes": None,
            "feeder": None,
            "scheduled": False,
            "with_medication": False,
            "medication_name": None,
            "medication_dose": None,
            "medication_time": None,
        }
        return event

    return _create  # noqa: E111


@pytest.fixture
def create_walk_event():
    """Helper to create walk events.

    Returns:
        Factory function for walk events
    """  # noqa: E111

    def _create(  # noqa: E111
        dog_id: str = "test_dog",
        duration_minutes: float = 30.0,
        distance_meters: float = 1500.0,
        walker: str | None = None,
    ) -> JSONMutableMapping:
        """Create walk event data."""
        end_time = datetime.now(UTC)
        start_time = end_time - timedelta(minutes=duration_minutes)

        event: JSONMutableMapping = {
            "dog_id": dog_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": duration_minutes,
            "distance_meters": distance_meters,
            "walker": walker,
            "weather": None,
            "leash_used": True,
        }
        return event

    return _create  # noqa: E111


# ==============================================================================
# PYTEST CONFIGURATION
# ==============================================================================


def pytest_configure(config) -> None:
    """Configure pytest with custom markers.

    Args:
        config: Pytest configuration object
    """  # noqa: E111
    config.addinivalue_line(  # noqa: E111
        "markers",
        "unit: Unit tests that don't require Home Assistant",
    )
    config.addinivalue_line(  # noqa: E111
        "markers",
        "integration: Integration tests that require Home Assistant",
    )
    config.addinivalue_line("markers", "slow: Slow running tests (> 1 second)")  # noqa: E111
    config.addinivalue_line("markers", "load: Load testing tests")  # noqa: E111


def pytest_collection_modifyitems(config, items) -> None:
    """Modify test collection to add markers automatically.

    Args:
        config: Pytest configuration
        items: Test items collected
    """  # noqa: E111
    for item in items:  # noqa: E111
        # Auto-mark integration tests
        if "components" in str(item.fspath):
            item.add_marker(pytest.mark.integration)  # noqa: E111

        # Auto-mark unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)  # noqa: E111
