"""Global test configuration for PawControl tests.

Provides comprehensive fixtures for testing all PawControl components with
proper mocking and Home Assistant integration.

Quality scale: Platinum - fixtures mirror Home Assistant behaviour while
remaining lightweight enough to run the full suite (unit, integration,
diagnostics, repairs) in constrained CI environments with >=95 % coverage.
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from importlib import import_module
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

if find_spec("aiohttp") is not None:
    ClientSession = import_module("aiohttp").ClientSession
else:

    class ClientSession:  # pragma: no cover - exercised only in minimal envs
        """Fallback type used when aiohttp is unavailable during test bootstrap."""


from tests.helpers.homeassistant_test_stubs import (
    HomeAssistant as StubHomeAssistant,
    install_homeassistant_stubs,
)

install_homeassistant_stubs()

from custom_components.pawcontrol import compat as pawcontrol_compat

pawcontrol_compat.ensure_homeassistant_config_entry_symbols()
pawcontrol_compat.ensure_homeassistant_exception_symbols()

from homeassistant.config_entries import ConfigEntry

from custom_components.pawcontrol.feeding_manager import FeedingBatchEntry
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    FeedingManagerDogSetupPayload,
    JSONMutableMapping,
)
from tests.helpers import typed_deepcopy
from tests.helpers.factories import (
    build_api_client_mock,
    build_coordinator_payload,
    build_coordinator_payload_variant,
)

if TYPE_CHECKING:
    from custom_components.pawcontrol.feeding_manager import FeedingManager
    from custom_components.pawcontrol.walk_manager import WalkManager


pytest_plugins = (
    "pytest_homeassistant_custom_component",
    "pytest_asyncio",
    "tests.plugins.asyncio_stub",
    "tests.plugins.coverage_shim",
)


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    runner_loop = asyncio.new_event_loop()
    try:
        return runner_loop.run_until_complete(coro)
    finally:
        runner_loop.close()


@pytest.fixture
def hass() -> StubHomeAssistant:
    """Return a minimal Home Assistant test instance."""
    return StubHomeAssistant()


# ==============================================================================
# ENHANCED FIXTURES FOR PAWCONTROL TESTING
# ==============================================================================


@pytest.fixture
def mock_dog_config() -> FeedingManagerDogSetupPayload:
    """Standard dog configuration for testing.

    Returns:
        Complete dog configuration mapping for FeedingManager
    """
    config: FeedingManagerDogSetupPayload = {
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
    return config


@pytest.fixture
def mock_multi_dog_config(
    mock_dog_config: FeedingManagerDogSetupPayload,
) -> list[FeedingManagerDogSetupPayload]:
    """Multiple dog configurations for testing.

    Args:
        mock_dog_config: Base dog configuration

    Returns:
        List of dog configuration payloads
    """
    dog1 = typed_deepcopy(mock_dog_config)
    dog1["dog_id"] = "buddy"
    dog1["dog_name"] = "Buddy"
    dog1["weight"] = 30.0

    dog2 = typed_deepcopy(mock_dog_config)
    dog2["dog_id"] = "max"
    dog2["dog_name"] = "Max"
    dog2["weight"] = 15.0
    dog2["breed"] = "Beagle"
    dog2["activity_level"] = "high"

    return [dog1, dog2]


@pytest.fixture
def mock_config_entry(mock_dog_config: FeedingManagerDogSetupPayload) -> ConfigEntry:
    """Mock Home Assistant config entry.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Mock ConfigEntry object
    """
    entry = ConfigEntry(
        domain="pawcontrol",
        data={"dogs": [mock_dog_config]},
        options={
            "entity_profile": "standard",
            "external_integrations": False,
            "update_interval": 120,
        },
        title="Test PawControl",
    )

    entry.version = 1
    entry.minor_version = 0
    entry.state = "loaded"

    return entry


@pytest.fixture
def config_entry_factory(
    mock_dog_config: FeedingManagerDogSetupPayload,
) -> Callable[..., ConfigEntry]:
    """Return a reusable ConfigEntry factory for tests."""

    def _factory(
        *,
        data: Mapping[str, object] | None = None,
        options: Mapping[str, object] | None = None,
        title: str = "Test PawControl",
        entry_id: str = "test-entry-id",
    ) -> ConfigEntry:
        entry = ConfigEntry(
            entry_id=entry_id,
            domain="pawcontrol",
            data=dict(data or {"dogs": [typed_deepcopy(mock_dog_config)]}),
            options=dict(
                options
                or {
                    "entity_profile": "standard",
                    "external_integrations": False,
                    "update_interval": 120,
                }
            ),
            title=title,
        )
        entry.version = 1
        entry.minor_version = 0
        entry.state = "loaded"
        return entry

    return _factory


@pytest.fixture
def mock_hass() -> Any:
    """Mock Home Assistant instance with proper async support."""
    from homeassistant.core import HomeAssistant

    hass = Mock(spec=HomeAssistant)
    hass.data = {}
    hass.states = Mock()
    hass.services = Mock()
    hass.bus = Mock()
    hass.config_entries = Mock()
    hass.config_entries.async_update_entry = Mock()
    hass.config = Mock()
    hass.config.latitude = 52.5200
    hass.config.longitude = 13.4050

    # Mock async methods
    hass.async_create_task = AsyncMock()
    hass.services.async_call = AsyncMock()
    hass.bus.async_fire = AsyncMock()

    return hass


class _MockClientSession(Mock):
    """Test double that mimics :class:`aiohttp.ClientSession` semantics."""

    def __init__(self) -> None:
        super().__init__(spec=ClientSession)
        self.closed = False

        async def _close() -> None:
            self.closed = True

        self.close = AsyncMock(side_effect=_close)
        self.request = AsyncMock(name="request")
        self.get = AsyncMock(side_effect=self.request, name="get")

        self.put = AsyncMock(side_effect=self.request, name="put")
        self.patch = AsyncMock(side_effect=self.request, name="patch")
        self.delete = AsyncMock(side_effect=self.request, name="delete")
        self.head = AsyncMock(side_effect=self.request, name="head")
        self.options = AsyncMock(side_effect=self.request, name="options")

        def _context_response(*args: Any, **kwargs: Any) -> AsyncMock:
            """Return an async context manager for ``session.post`` usage."""
            response = Mock()
            response.status = kwargs.get("status", 200)
            response.text = AsyncMock(return_value=kwargs.get("text", ""))
            response.json = AsyncMock(return_value=kwargs.get("json", {}))

            response.read = AsyncMock(return_value=kwargs.get("body", b""))

            response_cm = AsyncMock()
            response_cm.__aenter__.return_value = response
            response_cm.__aexit__.return_value = False
            response_cm.call_args = (args, kwargs)
            return response_cm

        self.post = AsyncMock(side_effect=_context_response, name="post")

        async def _ws_connect(*args: Any, **kwargs: Any) -> AsyncMock:
            """Return an async context manager for websocket usage."""
            websocket = AsyncMock()
            websocket.closed = False
            websocket.close = AsyncMock(name="close")
            websocket.send_json = AsyncMock(name="send_json")
            websocket.send_str = AsyncMock(name="send_str")
            websocket.send_bytes = AsyncMock(name="send_bytes")
            websocket.receive_json = AsyncMock(
                return_value=kwargs.get("receive_json", {}),
                name="receive_json",
            )
            websocket.receive_str = AsyncMock(
                return_value=kwargs.get("receive_str", ""),
                name="receive_str",
            )
            websocket.receive_bytes = AsyncMock(
                return_value=kwargs.get("receive_bytes", b""),
                name="receive_bytes",
            )

            ws_cm = AsyncMock()
            ws_cm.__aenter__.return_value = websocket
            ws_cm.__aexit__.return_value = False
            ws_cm.call_args = (args, kwargs)
            return ws_cm

        self.ws_connect = AsyncMock(side_effect=_ws_connect, name="ws_connect")


@pytest.fixture
def session_factory() -> Callable[..., _MockClientSession]:
    """Return a factory that creates aiohttp session doubles."""

    def _factory(*, closed: bool = False) -> _MockClientSession:
        session = _MockClientSession()
        session.closed = closed
        return session

    return _factory


@pytest.fixture
def mock_session(
    session_factory: Callable[..., _MockClientSession],
) -> _MockClientSession:
    """Return a reusable aiohttp session double for HTTP entry points."""
    return session_factory()


@pytest.fixture
def mock_api_client_factory() -> Callable[..., Mock]:
    """Return a reusable async API client mock factory."""

    def _factory(
        *,
        connected: bool = True,
        dog_data: Mapping[str, object] | None = None,
    ) -> Mock:
        return build_api_client_mock(connected=connected, dog_data=dog_data)

    return _factory


@pytest.fixture
def mock_api_client(mock_api_client_factory: Callable[..., Mock]) -> Mock:
    """Return a default API client mock."""
    return mock_api_client_factory()


@pytest.fixture
def coordinator_payload_factory() -> Callable[..., CoordinatorDogData]:
    """Return a factory for coordinator dog payloads used across entity tests."""

    def _factory(
        *,
        dog_id: str = "test_dog",
        dog_name: str = "Buddy",
        status: str = "online",
        state: str = "resting",
        zone: str = "home",
        visitor_mode_active: bool = False,
    ) -> CoordinatorDogData:
        return build_coordinator_payload(
            dog_id=dog_id,
            dog_name=dog_name,
            status=status,
            state=state,
            zone=zone,
            visitor_mode_active=visitor_mode_active,
        )

    return _factory


@pytest.fixture
def coordinator_payload_variants() -> Mapping[str, CoordinatorDogData]:
    """Return standard coordinator payload variants for parameterized tests."""
    return {
        variant: build_coordinator_payload_variant(variant)
        for variant in ("online_home", "offline", "visitor_mode", "outside_home")
    }


@pytest.fixture
def assert_entity_basics() -> Callable[[Any], None]:
    """Return shared assertions for PawControl entity baseline checks."""

    def _assert(entity: Any) -> None:
        assert isinstance(entity.available, bool)
        assert entity.unique_id is not None
        assert isinstance(entity.name, str | None)
        assert isinstance(entity.extra_state_attributes, Mapping)
        assert entity.device_info is not None

    return _assert


@pytest.fixture
def assert_flow_abort_reason() -> Callable[[Mapping[str, object], str], None]:
    """Return shared assertions for config-flow abort payloads."""

    def _assert(result: Mapping[str, object], expected_reason: str) -> None:
        assert result.get("type") == "abort"
        assert result.get("reason") == expected_reason

    return _assert


@pytest.fixture
def assert_service_error_handling() -> Callable[
    [type[Exception], str, Callable[[], object] | Callable[[], Awaitable[object]]],
    Awaitable[None],
]:
    """Return helper asserting sync/async callables raise expected service errors."""

    async def _assert(
        expected_exception: type[Exception],
        message_match: str,
        action: Callable[[], object] | Callable[[], Awaitable[object]],
    ) -> None:
        with pytest.raises(expected_exception, match=message_match):
            outcome = action()
            if asyncio.iscoroutine(outcome):
                await outcome
            elif isinstance(outcome, Exception):
                raise outcome

    return _assert


@pytest.fixture
def mock_resilience_manager(mock_hass):
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

    manager.execute_with_resilience = AsyncMock(
        side_effect=passthrough_execution,
    )
    manager.get_all_circuit_breakers = Mock(return_value={})

    return manager


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
    """
    from custom_components.pawcontrol.coordinator import PawControlCoordinator

    coordinator = PawControlCoordinator(
        mock_hass,
        mock_config_entry,
        mock_session,
    )
    coordinator.resilience_manager = mock_resilience_manager

    coordinator.data = {
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

    coordinator.last_update_success = True

    yield coordinator


@pytest.fixture
def entity_factory(mock_coordinator: Any) -> Any:
    """Return an EntityFactory bound to the shared coordinator fixture."""
    from custom_components.pawcontrol.entity_factory import EntityFactory

    return EntityFactory(mock_coordinator)


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
    """
    from custom_components.pawcontrol.feeding_manager import FeedingManager

    manager = FeedingManager(mock_hass)
    _run_async(manager.async_initialize([mock_dog_config]))

    return manager


@pytest.fixture
def mock_walk_manager(
    mock_dog_config: FeedingManagerDogSetupPayload,
) -> WalkManager:
    """Mock WalkManager for testing.

    Args:
        mock_dog_config: Dog configuration

    Returns:
        Initialized WalkManager
    """
    from custom_components.pawcontrol.walk_manager import WalkManager

    manager = WalkManager()
    _run_async(manager.async_initialize([mock_dog_config["dog_id"]]))

    return manager


@pytest.fixture
def mock_gps_manager(mock_hass, mock_resilience_manager):
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
def mock_notification_manager(mock_hass, mock_resilience_manager, mock_session):
    """Mock PawControlNotificationManager for testing.

    Args:
        mock_hass: Mock Home Assistant
        mock_resilience_manager: Mock resilience manager

    Returns:
        Initialized NotificationManager
    """
    from custom_components.pawcontrol.notifications import PawControlNotificationManager

    manager = PawControlNotificationManager(
        mock_hass,
        "test_entry",
        session=mock_session,
    )
    manager.resilience_manager = mock_resilience_manager

    _run_async(manager.async_initialize())

    return manager


@pytest.fixture
def mock_data_manager(mock_hass):
    """Mock PawControlDataManager for testing.

    Args:
        mock_hass: Mock Home Assistant

    Returns:
        Initialized DataManager
    """
    from custom_components.pawcontrol.data_manager import PawControlDataManager

    manager = PawControlDataManager(mock_hass, "test_entry")
    _run_async(manager.async_initialize())

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
    """
    from custom_components.pawcontrol.gps_manager import GPSPoint, WalkRoute

    route = WalkRoute(
        dog_id="test_dog",
        start_time=datetime.now(UTC) - timedelta(hours=1),
        end_time=datetime.now(UTC),
    )

    # Add some GPS points
    for i in range(10):
        point = GPSPoint(
            latitude=52.5200 + (i * 0.001),
            longitude=13.4050 + (i * 0.001),
            timestamp=datetime.now(UTC) - timedelta(minutes=60 - i * 6),
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

    def _assert(data: CoordinatorDogData) -> None:
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
def create_feeding_event() -> Callable[..., FeedingBatchEntry]:
    """Helper to create feeding events.

    Returns:
        Factory function for feeding events
    """

    def _create(
        dog_id: str = "test_dog",
        amount: float = 200.0,
        meal_type: str = "breakfast",
        timestamp: datetime | None = None,
    ) -> FeedingBatchEntry:
        """Create feeding event data."""
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

    return _create


# ==============================================================================
# PYTEST CONFIGURATION
# ==============================================================================


def pytest_configure(config) -> None:
    """Configure pytest with custom markers.

    Args:
        config: Pytest configuration object
    """
    config.addinivalue_line(
        "markers",
        "unit: Unit tests that don't require Home Assistant",
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests that require Home Assistant",
    )
    config.addinivalue_line("markers", "slow: Slow running tests (> 1 second)")
    config.addinivalue_line("markers", "load: Load testing tests")


def pytest_collection_modifyitems(config, items) -> None:
    """Modify test collection to add markers automatically.

    Args:
        config: Pytest configuration
        items: Test items collected
    """
    for item in items:
        # Auto-mark integration tests
        if "components" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

        # Auto-mark unit tests
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
