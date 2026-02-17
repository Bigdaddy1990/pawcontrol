"""Test data factories for PawControl integration tests.

This module provides factory functions for creating test data, config entries,
and mock objects used across the test suite.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.pawcontrol.const import (
    CONF_API_ENDPOINT,
    CONF_API_TOKEN,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_WALK,
)

# Domain constants
TEST_ENTRY_ID = "test_entry_id"
TEST_UNIQUE_ID = "test_unique_id"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_INTERVAL = "update_interval"


def create_mock_hass() -> HomeAssistant:
    """Create a mock Home Assistant instance.

    Returns:
        Mock HomeAssistant instance

    Examples:
        >>> hass = create_mock_hass()
        >>> assert hass.data is not None
    """  # noqa: E111
    hass = MagicMock(spec=HomeAssistant)  # noqa: E111
    hass.data = {}  # noqa: E111
    hass.states = MagicMock()  # noqa: E111
    hass.config_entries = MagicMock()  # noqa: E111
    hass.services = MagicMock()  # noqa: E111
    return hass  # noqa: E111


def create_test_config_entry(
    hass: HomeAssistant | None = None,
    *,
    entry_id: str | None = None,
    unique_id: str | None = None,
    title: str = "Test PawControl",
    data: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> ConfigEntry:
    """Create a test config entry.

    Args:
        hass: Home Assistant instance
        entry_id: Entry ID (generates UUID if None)
        unique_id: Unique ID
        title: Entry title
        data: Entry data
        options: Entry options

    Returns:
        ConfigEntry instance

    Examples:
        >>> entry = create_test_config_entry()
        >>> assert entry.domain == DOMAIN
    """  # noqa: E111
    if entry_id is None:  # noqa: E111
        entry_id = str(uuid.uuid4())

    if data is None:  # noqa: E111
        data = create_test_entry_data()

    if options is None:  # noqa: E111
        options = create_test_entry_options()

    entry = ConfigEntry(  # noqa: E111
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title=title,
        data=data,
        options=options,
        source="user",
        unique_id=unique_id or TEST_UNIQUE_ID,
        entry_id=entry_id,
    )

    return entry  # noqa: E111


def create_test_entry_data(
    *,
    api_endpoint: str = "https://api.pawcontrol.test",
    api_token: str = "test_token_12345",
    username: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Create test config entry data.

    Args:
        api_endpoint: API endpoint URL
        api_token: API token
        username: Optional username
        password: Optional password

    Returns:
        Configuration data dictionary

    Examples:
        >>> data = create_test_entry_data()
        >>> assert CONF_API_ENDPOINT in data
    """  # noqa: E111
    data: dict[str, Any] = {  # noqa: E111
        CONF_API_ENDPOINT: api_endpoint,
        CONF_API_TOKEN: api_token,
    }

    if username is not None:  # noqa: E111
        data[CONF_USERNAME] = username

    if password is not None:  # noqa: E111
        data[CONF_PASSWORD] = password

    return data  # noqa: E111


def create_test_entry_options(
    *,
    update_interval: int = 120,
    dogs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create test config entry options.

    Args:
        update_interval: Update interval in seconds
        dogs: Dog configurations

    Returns:
        Options dictionary

    Examples:
        >>> options = create_test_entry_options()
        >>> assert CONF_UPDATE_INTERVAL in options
    """  # noqa: E111
    if dogs is None:  # noqa: E111
        dogs = create_test_dogs_config()

    return {  # noqa: E111
        CONF_UPDATE_INTERVAL: update_interval,
        CONF_DOGS: dogs,
    }


def create_test_dogs_config(
    *,
    count: int = 2,
    prefix: str = "dog",
) -> dict[str, dict[str, Any]]:
    """Create test dog configurations.

    Args:
        count: Number of dogs to create
        prefix: Name prefix for dogs

    Returns:
        Dictionary of dog configurations

    Examples:
        >>> dogs = create_test_dogs_config(count=3)
        >>> assert len(dogs) == 3
    """  # noqa: E111
    dogs: dict[str, dict[str, Any]] = {}  # noqa: E111

    for i in range(count):  # noqa: E111
        dog_id = f"{prefix}_{i + 1}"
        dogs[dog_id] = {
            "name": f"{prefix.title()} {i + 1}",
            "breed": "Test Breed",
            "weight": 10.0 + i * 5,
            "age": 2 + i,
            "modules": [MODULE_GPS, MODULE_WALK, MODULE_FEEDING],
        }

    return dogs  # noqa: E111


def create_test_dog_data(
    *,
    dog_id: str = "test_dog",
    name: str = "Test Dog",
    breed: str = "Test Breed",
    weight: float = 15.0,
    age: int = 3,
    modules: list[str] | None = None,
) -> dict[str, Any]:
    """Create test data for a single dog.

    Args:
        dog_id: Dog identifier
        name: Dog name
        breed: Dog breed
        weight: Dog weight in kg
        age: Dog age in years
        modules: Enabled modules

    Returns:
        Dog data dictionary

    Examples:
        >>> data = create_test_dog_data(dog_id="buddy")
        >>> assert data["name"] == "Test Dog"
    """  # noqa: E111
    if modules is None:  # noqa: E111
        modules = [MODULE_GPS, MODULE_WALK, MODULE_FEEDING]

    return {  # noqa: E111
        "dog_id": dog_id,
        "name": name,
        "breed": breed,
        "weight": weight,
        "age": age,
        "modules": modules,
    }


def create_test_coordinator_data(
    *,
    dog_ids: list[str] | None = None,
    include_gps: bool = True,
    include_walk: bool = True,
    include_feeding: bool = True,
) -> dict[str, dict[str, Any]]:
    """Create test coordinator data.

    Args:
        dog_ids: List of dog IDs
        include_gps: Include GPS module data
        include_walk: Include walk module data
        include_feeding: Include feeding module data

    Returns:
        Coordinator data dictionary

    Examples:
        >>> data = create_test_coordinator_data(dog_ids=["buddy", "max"])
        >>> assert "buddy" in data
        >>> assert "max" in data
    """  # noqa: E111
    if dog_ids is None:  # noqa: E111
        dog_ids = ["dog_1", "dog_2"]

    data: dict[str, dict[str, Any]] = {}  # noqa: E111

    for dog_id in dog_ids:  # noqa: E111
        dog_data: dict[str, Any] = {}

        if include_gps:
            dog_data[MODULE_GPS] = create_test_gps_data()  # noqa: E111

        if include_walk:
            dog_data[MODULE_WALK] = create_test_walk_data()  # noqa: E111

        if include_feeding:
            dog_data[MODULE_FEEDING] = create_test_feeding_data()  # noqa: E111

        data[dog_id] = dog_data

    return data  # noqa: E111


def create_test_gps_data(
    *,
    latitude: float = 45.5231,
    longitude: float = -122.6765,
    accuracy: float = 10.0,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Create test GPS module data.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        accuracy: GPS accuracy in meters
        timestamp: GPS timestamp

    Returns:
        GPS data dictionary

    Examples:
        >>> data = create_test_gps_data(latitude=40.0, longitude=-120.0)
        >>> assert data["latitude"] == 40.0
    """  # noqa: E111
    if timestamp is None:  # noqa: E111
        timestamp = datetime.now()

    return {  # noqa: E111
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy,
        "timestamp": timestamp.isoformat(),
        "available": True,
    }


def create_test_walk_data(
    *,
    active: bool = False,
    distance: float = 0.0,
    duration: int = 0,
    start_time: datetime | None = None,
) -> dict[str, Any]:
    """Create test walk module data.

    Args:
        active: Whether walk is active
        distance: Distance in kilometers
        duration: Duration in seconds
        start_time: Walk start time

    Returns:
        Walk data dictionary

    Examples:
        >>> data = create_test_walk_data(active=True, distance=2.5)
        >>> assert data["walk_in_progress"] == True
    """  # noqa: E111
    if start_time is None and active:  # noqa: E111
        start_time = datetime.now() - timedelta(seconds=duration)

    return {  # noqa: E111
        "walk_in_progress": active,
        "distance": distance,
        "duration": duration,
        "start_time": start_time.isoformat() if start_time else None,
    }


def create_test_feeding_data(
    *,
    last_meal_time: datetime | None = None,
    meals_today: int = 2,
    total_calories: float = 800.0,
) -> dict[str, Any]:
    """Create test feeding module data.

    Args:
        last_meal_time: Last meal timestamp
        meals_today: Number of meals today
        total_calories: Total calories consumed today

    Returns:
        Feeding data dictionary

    Examples:
        >>> data = create_test_feeding_data(meals_today=3)
        >>> assert data["meals_today"] == 3
    """  # noqa: E111
    if last_meal_time is None:  # noqa: E111
        last_meal_time = datetime.now() - timedelta(hours=3)

    return {  # noqa: E111
        "last_meal_time": last_meal_time.isoformat(),
        "meals_today": meals_today,
        "total_calories": total_calories,
    }


def create_mock_coordinator(
    hass: HomeAssistant | None = None,
    *,
    data: dict[str, Any] | None = None,
    last_update_success: bool = True,
) -> DataUpdateCoordinator:
    """Create a mock coordinator.

    Args:
        hass: Home Assistant instance
        data: Coordinator data
        last_update_success: Last update success status

    Returns:
        Mock DataUpdateCoordinator

    Examples:
        >>> coordinator = create_mock_coordinator()
        >>> assert coordinator.last_update_success == True
    """  # noqa: E111
    if hass is None:  # noqa: E111
        hass = create_mock_hass()

    if data is None:  # noqa: E111
        data = create_test_coordinator_data()

    coordinator = MagicMock(spec=DataUpdateCoordinator)  # noqa: E111
    coordinator.hass = hass  # noqa: E111
    coordinator.data = data  # noqa: E111
    coordinator.last_update_success = last_update_success  # noqa: E111
    coordinator.async_request_refresh = AsyncMock()  # noqa: E111

    return coordinator  # noqa: E111


def create_mock_api_client(
    *,
    connected: bool = True,
    dog_data: dict[str, Any] | None = None,
) -> MagicMock:
    """Create a mock API client.

    Args:
        connected: Connection status
        dog_data: Dog data to return

    Returns:
        Mock API client

    Examples:
        >>> client = create_mock_api_client()
        >>> assert client.is_connected == True
    """  # noqa: E111
    client = MagicMock()  # noqa: E111
    client.is_connected = connected  # noqa: E111
    client.async_get_dog_data = AsyncMock(return_value=dog_data or {})  # noqa: E111
    client.async_update_dog_data = AsyncMock()  # noqa: E111
    return client  # noqa: E111


# Test data generators


def generate_test_gps_coordinates(
    count: int = 10,
    *,
    center_lat: float = 45.5231,
    center_lon: float = -122.6765,
    radius_km: float = 10.0,
) -> list[tuple[float, float]]:
    """Generate random GPS coordinates near a center point.

    Args:
        count: Number of coordinates to generate
        center_lat: Center latitude
        center_lon: Center longitude
        radius_km: Radius in kilometers

    Returns:
        List of (latitude, longitude) tuples

    Examples:
        >>> coords = generate_test_gps_coordinates(count=5)
        >>> assert len(coords) == 5
    """  # noqa: E111
    import random  # noqa: E111

    coords: list[tuple[float, float]] = []  # noqa: E111

    for _ in range(count):  # noqa: E111
        # Simple random offset (not geographically accurate, but good for testing)
        lat_offset = random.uniform(-radius_km / 111, radius_km / 111)
        lon_offset = random.uniform(-radius_km / 111, radius_km / 111)

        lat = center_lat + lat_offset
        lon = center_lon + lon_offset

        coords.append((lat, lon))

    return coords  # noqa: E111


def generate_test_timestamps(
    count: int = 10,
    *,
    start: datetime | None = None,
    interval_seconds: int = 300,
) -> list[datetime]:
    """Generate test timestamps at regular intervals.

    Args:
        count: Number of timestamps
        start: Start datetime
        interval_seconds: Interval between timestamps

    Returns:
        List of datetime objects

    Examples:
        >>> timestamps = generate_test_timestamps(count=5)
        >>> assert len(timestamps) == 5
    """  # noqa: E111
    if start is None:  # noqa: E111
        start = datetime.now() - timedelta(seconds=interval_seconds * count)

    timestamps: list[datetime] = []  # noqa: E111
    current = start  # noqa: E111

    for _ in range(count):  # noqa: E111
        timestamps.append(current)
        current += timedelta(seconds=interval_seconds)

    return timestamps  # noqa: E111


# Assertion helpers


def assert_valid_gps_data(data: dict[str, Any]) -> None:
    """Assert GPS data is valid.

    Args:
        data: GPS data dictionary

    Raises:
        AssertionError: If data is invalid

    Examples:
        >>> data = create_test_gps_data()
        >>> assert_valid_gps_data(data)
    """  # noqa: E111
    assert "latitude" in data  # noqa: E111
    assert "longitude" in data  # noqa: E111
    assert "accuracy" in data  # noqa: E111
    assert "timestamp" in data  # noqa: E111

    assert -90 <= data["latitude"] <= 90  # noqa: E111
    assert -180 <= data["longitude"] <= 180  # noqa: E111
    assert data["accuracy"] > 0  # noqa: E111


def assert_valid_walk_data(data: dict[str, Any]) -> None:
    """Assert walk data is valid.

    Args:
        data: Walk data dictionary

    Raises:
        AssertionError: If data is invalid

    Examples:
        >>> data = create_test_walk_data()
        >>> assert_valid_walk_data(data)
    """  # noqa: E111
    assert "walk_in_progress" in data  # noqa: E111
    assert "distance" in data  # noqa: E111
    assert "duration" in data  # noqa: E111

    assert isinstance(data["walk_in_progress"], bool)  # noqa: E111
    assert data["distance"] >= 0  # noqa: E111
    assert data["duration"] >= 0  # noqa: E111


def assert_coordinator_data_valid(data: dict[str, dict[str, Any]]) -> None:
    """Assert coordinator data structure is valid.

    Args:
        data: Coordinator data

    Raises:
        AssertionError: If data structure is invalid

    Examples:
        >>> data = create_test_coordinator_data()
        >>> assert_coordinator_data_valid(data)
    """  # noqa: E111
    assert isinstance(data, dict)  # noqa: E111

    for dog_id, dog_data in data.items():  # noqa: E111
        assert isinstance(dog_id, str)
        assert isinstance(dog_data, dict)

        # Check module data if present
        if MODULE_GPS in dog_data:
            assert_valid_gps_data(dog_data[MODULE_GPS])  # noqa: E111

        if MODULE_WALK in dog_data:
            assert_valid_walk_data(dog_data[MODULE_WALK])  # noqa: E111
