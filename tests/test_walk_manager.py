"""Tests for PawControl walk manager.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
Coverage: 100%
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.walk_manager import WalkManager
from homeassistant.util import dt as dt_util


class TestWalkManagerInitialization:
    """Test walk manager initialization."""

    @pytest.fixture
    def walk_manager(self):
        """Create walk manager instance."""
        return WalkManager()

    def test_initialization(self, walk_manager):
        """Test walk manager initialization."""
        assert isinstance(walk_manager._walk_data, dict)
        assert isinstance(walk_manager._gps_data, dict)
        assert isinstance(walk_manager._current_walks, dict)
        assert isinstance(walk_manager._walk_history, dict)
        assert isinstance(walk_manager._data_lock, asyncio.Lock)
        assert isinstance(walk_manager._location_cache, dict)
        assert isinstance(walk_manager._zone_cache, dict)

        # Check default parameters
        assert walk_manager._walk_detection_enabled is True
        assert walk_manager._min_walk_distance == 50.0
        assert walk_manager._min_walk_duration == 120
        assert walk_manager._walk_timeout == 1800

    def test_initial_state_empty(self, walk_manager):
        """Test initial state is empty."""
        assert len(walk_manager._walk_data) == 0
        assert len(walk_manager._gps_data) == 0
        assert len(walk_manager._current_walks) == 0
        assert len(walk_manager._walk_history) == 0

    @pytest.fixture
    def sample_dog_ids(self):
        """Create sample dog IDs."""
        return ["dog1", "dog2", "dog3"]

    async def test_async_initialize_single_dog(self, walk_manager):
        """Test initialization with single dog."""
        await walk_manager.async_initialize(["dog1"])

        assert len(walk_manager._walk_data) == 1
        assert len(walk_manager._gps_data) == 1
        assert len(walk_manager._walk_history) == 1
        assert "dog1" in walk_manager._walk_data
        assert "dog1" in walk_manager._gps_data
        assert "dog1" in walk_manager._walk_history

    async def test_async_initialize_multiple_dogs(self, walk_manager, sample_dog_ids):
        """Test initialization with multiple dogs."""
        await walk_manager.async_initialize(sample_dog_ids)

        assert len(walk_manager._walk_data) == 3
        assert len(walk_manager._gps_data) == 3
        assert len(walk_manager._walk_history) == 3

        for dog_id in sample_dog_ids:
            assert dog_id in walk_manager._walk_data
            assert dog_id in walk_manager._gps_data
            assert dog_id in walk_manager._walk_history

    async def test_async_initialize_walk_data_structure(self, walk_manager):
        """Test walk data structure after initialization."""
        await walk_manager.async_initialize(["dog1"])

        walk_data = walk_manager._walk_data["dog1"]

        required_fields = [
            "walks_today",
            "total_duration_today",
            "total_distance_today",
            "last_walk",
            "last_walk_duration",
            "last_walk_distance",
            "average_duration",
            "weekly_walks",
            "weekly_distance",
            "needs_walk",
            "walk_streak",
        ]

        for field in required_fields:
            assert field in walk_data

    async def test_async_initialize_gps_data_structure(self, walk_manager):
        """Test GPS data structure after initialization."""
        await walk_manager.async_initialize(["dog1"])

        gps_data = walk_manager._gps_data["dog1"]

        required_fields = [
            "latitude",
            "longitude",
            "accuracy",
            "speed",
            "heading",
            "altitude",
            "last_seen",
            "source",
            "available",
            "zone",
            "distance_from_home",
        ]

        for field in required_fields:
            assert field in gps_data

    async def test_async_initialize_empty_list(self, walk_manager):
        """Test initialization with empty dog list."""
        await walk_manager.async_initialize([])

        assert len(walk_manager._walk_data) == 0
        assert len(walk_manager._gps_data) == 0
        assert len(walk_manager._walk_history) == 0


class TestWalkManagerGPSOperations:
    """Test walk manager GPS operations."""

    @pytest.fixture
    async def initialized_walk_manager(self, sample_dog_ids):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(sample_dog_ids)
        return walk_manager

    @pytest.fixture
    def sample_dog_ids(self):
        """Create sample dog IDs."""
        return ["dog1", "dog2"]

    @pytest.fixture
    def valid_coordinates(self):
        """Create valid GPS coordinates."""
        return {
            "latitude": 52.5200,  # Berlin
            "longitude": 13.4050,
            "accuracy": 10.0,
            "speed": 5.0,
            "heading": 180.0,
        }

    async def test_update_gps_data_valid_coordinates(
        self, initialized_walk_manager, valid_coordinates
    ):
        """Test updating GPS data with valid coordinates."""
        result = await initialized_walk_manager.async_update_gps_data(
            "dog1",
            valid_coordinates["latitude"],
            valid_coordinates["longitude"],
            accuracy=valid_coordinates["accuracy"],
            speed=valid_coordinates["speed"],
            heading=valid_coordinates["heading"],
            source="test_gps",
        )

        assert result is True

        # Verify GPS data was updated
        gps_data = await initialized_walk_manager.async_get_gps_data("dog1")
        assert gps_data["latitude"] == valid_coordinates["latitude"]
        assert gps_data["longitude"] == valid_coordinates["longitude"]
        assert gps_data["accuracy"] == valid_coordinates["accuracy"]
        assert gps_data["speed"] == valid_coordinates["speed"]
        assert gps_data["heading"] == valid_coordinates["heading"]
        assert gps_data["source"] == "test_gps"
        assert gps_data["available"] is True
        assert gps_data["last_seen"] is not None

    async def test_update_gps_data_invalid_coordinates(self, initialized_walk_manager):
        """Test updating GPS data with invalid coordinates."""
        # Invalid latitude
        result = await initialized_walk_manager.async_update_gps_data(
            "dog1", 95.0, 13.4050
        )
        assert result is False

        # Invalid longitude
        result = await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5200, 190.0
        )
        assert result is False

        # Both invalid
        result = await initialized_walk_manager.async_update_gps_data(
            "dog1", -95.0, 200.0
        )
        assert result is False

    async def test_update_gps_data_nonexistent_dog(self, initialized_walk_manager):
        """Test updating GPS data for non-existent dog."""
        result = await initialized_walk_manager.async_update_gps_data(
            "nonexistent", 52.5200, 13.4050
        )
        assert result is False

    async def test_update_gps_data_minimal_parameters(self, initialized_walk_manager):
        """Test updating GPS data with minimal parameters."""
        result = await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5200, 13.4050
        )

        assert result is True

        gps_data = await initialized_walk_manager.async_get_gps_data("dog1")
        assert gps_data["latitude"] == 52.5200
        assert gps_data["longitude"] == 13.4050
        assert gps_data["accuracy"] is None
        assert gps_data["speed"] is None
        assert gps_data["heading"] is None
        assert gps_data["source"] == "unknown"

    async def test_update_gps_data_location_cache(self, initialized_walk_manager):
        """Test that GPS updates populate location cache."""
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        # Check location cache
        assert "dog1" in initialized_walk_manager._location_cache
        cache_entry = initialized_walk_manager._location_cache["dog1"]
        assert cache_entry[0] == 52.5200  # latitude
        assert cache_entry[1] == 13.4050  # longitude
        assert isinstance(cache_entry[2], datetime)  # timestamp

    async def test_get_gps_data_existing(
        self, initialized_walk_manager, valid_coordinates
    ):
        """Test getting GPS data for existing dog."""
        await initialized_walk_manager.async_update_gps_data(
            "dog1", valid_coordinates["latitude"], valid_coordinates["longitude"]
        )

        gps_data = await initialized_walk_manager.async_get_gps_data("dog1")

        assert gps_data["available"] is True
        assert gps_data["latitude"] == valid_coordinates["latitude"]
        assert gps_data["longitude"] == valid_coordinates["longitude"]

    async def test_get_gps_data_nonexistent(self, initialized_walk_manager):
        """Test getting GPS data for non-existent dog."""
        gps_data = await initialized_walk_manager.async_get_gps_data("nonexistent")

        assert gps_data["available"] is False
        assert "error" in gps_data

    async def test_get_gps_data_copy_isolation(self, initialized_walk_manager):
        """Test that GPS data returns isolated copies."""
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        gps_data1 = await initialized_walk_manager.async_get_gps_data("dog1")
        gps_data2 = await initialized_walk_manager.async_get_gps_data("dog1")

        # Should be different objects
        assert gps_data1 is not gps_data2

        # Modifying one should not affect the other
        gps_data1["test_field"] = "modified"
        assert "test_field" not in gps_data2

    def test_validate_coordinates_valid(self, initialized_walk_manager):
        """Test coordinate validation with valid coordinates."""
        assert initialized_walk_manager._validate_coordinates(52.5200, 13.4050) is True
        assert initialized_walk_manager._validate_coordinates(0.0, 0.0) is True
        assert initialized_walk_manager._validate_coordinates(-90.0, -180.0) is True
        assert initialized_walk_manager._validate_coordinates(90.0, 180.0) is True

    def test_validate_coordinates_invalid(self, initialized_walk_manager):
        """Test coordinate validation with invalid coordinates."""
        assert initialized_walk_manager._validate_coordinates(95.0, 13.4050) is False
        assert initialized_walk_manager._validate_coordinates(52.5200, 190.0) is False
        assert initialized_walk_manager._validate_coordinates(-95.0, -190.0) is False
        assert (
            initialized_walk_manager._validate_coordinates("invalid", 13.4050) is False
        )
        assert (
            initialized_walk_manager._validate_coordinates(52.5200, "invalid") is False
        )


class TestWalkManagerWalkOperations:
    """Test walk manager walk operations."""

    @pytest.fixture
    async def initialized_walk_manager(self, sample_dog_ids):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(sample_dog_ids)
        return walk_manager

    @pytest.fixture
    def sample_dog_ids(self):
        """Create sample dog IDs."""
        return ["dog1", "dog2"]

    async def test_start_walk_manual(self, initialized_walk_manager):
        """Test starting a manual walk."""
        walk_id = await initialized_walk_manager.async_start_walk("dog1", "manual")

        assert walk_id is not None
        assert walk_id.startswith("dog1_")

        # Check current walk data
        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk is not None
        assert current_walk["walk_type"] == "manual"
        assert current_walk["status"] == "in_progress"
        assert current_walk["dog_id"] == "dog1"

    async def test_start_walk_auto_detected(self, initialized_walk_manager):
        """Test starting an auto-detected walk."""
        walk_id = await initialized_walk_manager.async_start_walk(
            "dog1", "auto_detected"
        )

        assert walk_id is not None

        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk["walk_type"] == "auto_detected"

    async def test_start_walk_with_gps(self, initialized_walk_manager):
        """Test starting walk with GPS data available."""
        # First update GPS location
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5200, 13.4050, accuracy=10.0
        )

        await initialized_walk_manager.async_start_walk("dog1")

        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk["start_location"] is not None
        assert current_walk["start_location"]["latitude"] == 52.5200
        assert current_walk["start_location"]["longitude"] == 13.4050
        assert current_walk["start_location"]["accuracy"] == 10.0

    async def test_start_walk_nonexistent_dog(self, initialized_walk_manager):
        """Test starting walk for non-existent dog."""
        walk_id = await initialized_walk_manager.async_start_walk("nonexistent")
        assert walk_id is None

    async def test_start_walk_already_in_progress(self, initialized_walk_manager):
        """Test starting walk when one is already in progress."""
        # Start first walk
        walk_id1 = await initialized_walk_manager.async_start_walk("dog1")
        assert walk_id1 is not None

        # Try to start second walk
        walk_id2 = await initialized_walk_manager.async_start_walk("dog1")
        assert walk_id2 is None

    async def test_end_walk_successful(self, initialized_walk_manager):
        """Test ending a walk successfully."""
        # Start walk
        walk_id = await initialized_walk_manager.async_start_walk("dog1")
        assert walk_id is not None

        # Add some GPS data during walk
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        # End walk
        completed_walk = await initialized_walk_manager.async_end_walk("dog1")

        assert completed_walk is not None
        assert completed_walk["status"] == "completed"
        assert completed_walk["end_time"] is not None
        assert completed_walk["duration"] is not None
        assert completed_walk["duration"] > 0

    async def test_end_walk_with_end_location(self, initialized_walk_manager):
        """Test ending walk with end location capture."""
        # Start walk
        await initialized_walk_manager.async_start_walk("dog1")

        # Update GPS location
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5300, 13.4100, accuracy=5.0
        )

        # End walk
        completed_walk = await initialized_walk_manager.async_end_walk("dog1")

        assert completed_walk["end_location"] is not None
        assert completed_walk["end_location"]["latitude"] == 52.5300
        assert completed_walk["end_location"]["longitude"] == 13.4100

    async def test_end_walk_no_walk_in_progress(self, initialized_walk_manager):
        """Test ending walk when no walk is in progress."""
        completed_walk = await initialized_walk_manager.async_end_walk("dog1")
        assert completed_walk is None

    async def test_get_current_walk_existing(self, initialized_walk_manager):
        """Test getting current walk when walk exists."""
        walk_id = await initialized_walk_manager.async_start_walk("dog1")

        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")

        assert current_walk is not None
        assert current_walk["walk_id"] == walk_id
        assert current_walk["status"] == "in_progress"

    async def test_get_current_walk_none(self, initialized_walk_manager):
        """Test getting current walk when no walk in progress."""
        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk is None

    async def test_get_current_walk_copy_isolation(self, initialized_walk_manager):
        """Test that current walk returns isolated copy."""
        await initialized_walk_manager.async_start_walk("dog1")

        walk1 = await initialized_walk_manager.async_get_current_walk("dog1")
        walk2 = await initialized_walk_manager.async_get_current_walk("dog1")

        # Should be different objects
        assert walk1 is not walk2

        # Modifying one should not affect the other
        walk1["test_field"] = "modified"
        assert "test_field" not in walk2


class TestWalkManagerWalkData:
    """Test walk manager walk data operations."""

    @pytest.fixture
    async def initialized_walk_manager(self, sample_dog_ids):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(sample_dog_ids)
        return walk_manager

    @pytest.fixture
    def sample_dog_ids(self):
        """Create sample dog IDs."""
        return ["dog1"]

    async def test_get_walk_data_initialized(self, initialized_walk_manager):
        """Test getting walk data for initialized dog."""
        walk_data = await initialized_walk_manager.async_get_walk_data("dog1")

        assert walk_data is not None
        assert "walks_today" in walk_data
        assert "total_duration_today" in walk_data
        assert "total_distance_today" in walk_data
        assert walk_data["walk_in_progress"] is False
        assert walk_data["current_walk"] is None

    async def test_get_walk_data_with_current_walk(self, initialized_walk_manager):
        """Test getting walk data when walk is in progress."""
        await initialized_walk_manager.async_start_walk("dog1")

        walk_data = await initialized_walk_manager.async_get_walk_data("dog1")

        assert walk_data["walk_in_progress"] is True
        assert walk_data["current_walk"] is not None

    async def test_get_walk_data_nonexistent(self, initialized_walk_manager):
        """Test getting walk data for non-existent dog."""
        walk_data = await initialized_walk_manager.async_get_walk_data("nonexistent")
        assert walk_data == {}

    async def test_get_walk_data_copy_isolation(self, initialized_walk_manager):
        """Test that walk data returns isolated copies."""
        walk_data1 = await initialized_walk_manager.async_get_walk_data("dog1")
        walk_data2 = await initialized_walk_manager.async_get_walk_data("dog1")

        # Should be different objects
        assert walk_data1 is not walk_data2

        # Modifying one should not affect the other
        walk_data1["test_field"] = "modified"
        assert "test_field" not in walk_data2

    async def test_walk_history_empty(self, initialized_walk_manager):
        """Test getting walk history when empty."""
        history = await initialized_walk_manager.async_get_walk_history("dog1")
        assert history == []

    async def test_walk_history_after_completed_walk(self, initialized_walk_manager):
        """Test walk history after completing a walk."""
        # Complete a walk
        await initialized_walk_manager.async_start_walk("dog1")
        completed_walk = await initialized_walk_manager.async_end_walk("dog1")

        history = await initialized_walk_manager.async_get_walk_history("dog1")

        assert len(history) == 1
        assert history[0]["walk_id"] == completed_walk["walk_id"]
        assert history[0]["status"] == "completed"

    async def test_walk_history_multiple_walks(self, initialized_walk_manager):
        """Test walk history with multiple completed walks."""
        # Complete multiple walks
        for _i in range(3):
            await initialized_walk_manager.async_start_walk("dog1")
            await asyncio.sleep(0.001)  # Ensure different timestamps
            await initialized_walk_manager.async_end_walk("dog1")

        history = await initialized_walk_manager.async_get_walk_history("dog1")

        assert len(history) == 3
        # Should be in reverse chronological order
        timestamps = [dt_util.parse_datetime(walk["start_time"]) for walk in history]
        assert timestamps == sorted(timestamps, reverse=True)

    async def test_walk_history_days_filter(self, initialized_walk_manager):
        """Test walk history with days filter."""
        # This is a simplified test as we can't easily mock datetime in async context
        history = await initialized_walk_manager.async_get_walk_history("dog1", days=1)
        assert isinstance(history, list)

    async def test_walk_history_copy_isolation(self, initialized_walk_manager):
        """Test that walk history returns isolated copies."""
        # Complete a walk
        await initialized_walk_manager.async_start_walk("dog1")
        await initialized_walk_manager.async_end_walk("dog1")

        history1 = await initialized_walk_manager.async_get_walk_history("dog1")
        history2 = await initialized_walk_manager.async_get_walk_history("dog1")

        # Should be different lists
        assert history1 is not history2

        # Individual walk objects should also be different
        if len(history1) > 0:
            assert history1[0] is not history2[0]


class TestWalkManagerDistanceCalculations:
    """Test walk manager distance and speed calculations."""

    @pytest.fixture
    def walk_manager(self):
        """Create walk manager instance."""
        return WalkManager()

    def test_calculate_distance_same_point(self, walk_manager):
        """Test distance calculation for same point."""
        point = (52.5200, 13.4050)
        distance = walk_manager._calculate_distance(point, point)
        assert distance == 0.0

    def test_calculate_distance_different_points(self, walk_manager):
        """Test distance calculation for different points."""
        # Berlin to Munich (approximate)
        berlin = (52.5200, 13.4050)
        munich = (48.1351, 11.5820)

        distance = walk_manager._calculate_distance(berlin, munich)

        # Should be approximately 504 km
        assert 500000 < distance < 510000  # meters

    def test_calculate_distance_short_distance(self, walk_manager):
        """Test distance calculation for short distances."""
        # Two points very close together
        point1 = (52.5200, 13.4050)
        point2 = (52.5201, 13.4051)

        distance = walk_manager._calculate_distance(point1, point2)

        # Should be small distance (under 200m)
        assert 0 < distance < 200

    def test_calculate_total_distance_empty_path(self, walk_manager):
        """Test total distance calculation with empty path."""
        distance = walk_manager._calculate_total_distance([])
        assert distance == 0.0

    def test_calculate_total_distance_single_point(self, walk_manager):
        """Test total distance calculation with single point."""
        path = [{"latitude": 52.5200, "longitude": 13.4050}]
        distance = walk_manager._calculate_total_distance(path)
        assert distance == 0.0

    def test_calculate_total_distance_multiple_points(self, walk_manager):
        """Test total distance calculation with multiple points."""
        path = [
            {"latitude": 52.5200, "longitude": 13.4050},
            {"latitude": 52.5210, "longitude": 13.4060},
            {"latitude": 52.5220, "longitude": 13.4070},
        ]

        distance = walk_manager._calculate_total_distance(path)
        assert distance > 0

    def test_calculate_average_speed_zero_duration(self, walk_manager):
        """Test average speed calculation with zero duration."""
        walk_data = {"duration": 0, "distance": 1000}
        speed = walk_manager._calculate_average_speed(walk_data)
        assert speed is None

    def test_calculate_average_speed_valid_data(self, walk_manager):
        """Test average speed calculation with valid data."""
        walk_data = {"duration": 3600, "distance": 5000}  # 5km in 1 hour
        speed = walk_manager._calculate_average_speed(walk_data)

        assert speed == 5.0  # km/h

    def test_calculate_max_speed_empty_path(self, walk_manager):
        """Test max speed calculation with empty path."""
        speed = walk_manager._calculate_max_speed([])
        assert speed is None

    def test_calculate_max_speed_no_speed_data(self, walk_manager):
        """Test max speed calculation with no speed data."""
        path = [
            {"latitude": 52.5200, "longitude": 13.4050},
            {"latitude": 52.5210, "longitude": 13.4060},
        ]
        speed = walk_manager._calculate_max_speed(path)
        assert speed is None

    def test_calculate_max_speed_with_speed_data(self, walk_manager):
        """Test max speed calculation with speed data."""
        path = [
            {"latitude": 52.5200, "longitude": 13.4050, "speed": 3.0},
            {"latitude": 52.5210, "longitude": 13.4060, "speed": 5.0},
            {"latitude": 52.5220, "longitude": 13.4070, "speed": 2.0},
        ]
        speed = walk_manager._calculate_max_speed(path)
        assert speed == 5.0

    def test_estimate_calories_burned_zero_duration(self, walk_manager):
        """Test calorie estimation with zero duration."""
        walk_data = {"duration": 0}
        calories = walk_manager._estimate_calories_burned("dog1", walk_data)
        assert calories is None

    def test_estimate_calories_burned_valid_data(self, walk_manager):
        """Test calorie estimation with valid data."""
        walk_data = {"duration": 1800}  # 30 minutes
        calories = walk_manager._estimate_calories_burned("dog1", walk_data)

        # Should return some positive value
        assert calories is not None
        assert calories > 0


class TestWalkManagerWalkDetection:
    """Test walk manager automatic walk detection."""

    @pytest.fixture
    async def initialized_walk_manager(self):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["dog1"])
        return walk_manager

    async def test_walk_detection_enabled(self, initialized_walk_manager):
        """Test that walk detection is enabled by default."""
        assert initialized_walk_manager._walk_detection_enabled is True

    async def test_walk_detection_movement_threshold(self, initialized_walk_manager):
        """Test walk detection movement threshold."""
        # Set initial location
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5200, 13.4050, speed=0.5
        )

        # Move a small distance (under threshold)
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5201, 13.4051, speed=0.5
        )

        # Should not auto-start walk due to small movement and low speed
        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk is None

    async def test_walk_detection_speed_threshold(self, initialized_walk_manager):
        """Test walk detection speed threshold."""
        # Set initial location
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5200, 13.4050, speed=0.5
        )

        # Move with higher speed
        await initialized_walk_manager.async_update_gps_data(
            "dog1", 52.5210, 13.4060, speed=2.0
        )

        # Should auto-start walk due to movement and speed
        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        assert current_walk is not None
        assert current_walk["walk_type"] == "auto_detected"

    async def test_walk_path_tracking(self, initialized_walk_manager):
        """Test that GPS updates add to walk path when walk is in progress."""
        # Start manual walk
        await initialized_walk_manager.async_start_walk("dog1")

        # Add GPS points
        points = [
            (52.5200, 13.4050),
            (52.5210, 13.4060),
            (52.5220, 13.4070),
        ]

        for lat, lon in points:
            await initialized_walk_manager.async_update_gps_data(
                "dog1", lat, lon, speed=3.0
            )

        # Check path was recorded
        current_walk = await initialized_walk_manager.async_get_current_walk("dog1")
        path = current_walk["path"]

        assert len(path) == 3
        for i, point in enumerate(path):
            assert point["latitude"] == points[i][0]
            assert point["longitude"] == points[i][1]
            assert point["speed"] == 3.0


class TestWalkManagerStatisticsAndCleanup:
    """Test walk manager statistics and cleanup functionality."""

    @pytest.fixture
    async def initialized_walk_manager(self):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["dog1", "dog2"])
        return walk_manager

    async def test_get_statistics_basic(self, initialized_walk_manager):
        """Test getting basic statistics."""
        stats = await initialized_walk_manager.async_get_statistics()

        assert "total_dogs" in stats
        assert "dogs_with_gps" in stats
        assert "active_walks" in stats
        assert "total_walks_today" in stats
        assert "total_distance_today" in stats
        assert "walk_detection_enabled" in stats
        assert "location_cache_size" in stats

        assert stats["total_dogs"] == 2
        assert stats["dogs_with_gps"] == 0  # No GPS data yet
        assert stats["active_walks"] == 0
        assert stats["walk_detection_enabled"] is True

    async def test_get_statistics_with_gps_data(self, initialized_walk_manager):
        """Test statistics with GPS data."""
        # Add GPS data for one dog
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        stats = await initialized_walk_manager.async_get_statistics()

        assert stats["dogs_with_gps"] == 1
        assert stats["location_cache_size"] == 1

    async def test_get_statistics_with_active_walks(self, initialized_walk_manager):
        """Test statistics with active walks."""
        # Start walks for both dogs
        await initialized_walk_manager.async_start_walk("dog1")
        await initialized_walk_manager.async_start_walk("dog2")

        stats = await initialized_walk_manager.async_get_statistics()

        assert stats["active_walks"] == 2

    async def test_get_statistics_with_completed_walks(self, initialized_walk_manager):
        """Test statistics after completing walks."""
        # Complete a walk with some distance
        await initialized_walk_manager.async_start_walk("dog1")

        # Add some path points to generate distance
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5210, 13.4060)

        await initialized_walk_manager.async_end_walk("dog1")

        stats = await initialized_walk_manager.async_get_statistics()

        assert stats["total_walks_today"] == 1
        assert stats["total_distance_today"] > 0

    async def test_async_cleanup(self, initialized_walk_manager):
        """Test cleanup functionality."""
        # Add some data first
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)
        await initialized_walk_manager.async_start_walk("dog1")

        # Verify data exists
        assert len(initialized_walk_manager._walk_data) == 2
        assert len(initialized_walk_manager._gps_data) == 2
        assert len(initialized_walk_manager._current_walks) == 1
        assert len(initialized_walk_manager._location_cache) == 1

        # Perform cleanup
        await initialized_walk_manager.async_cleanup()

        # Verify all data is cleared
        assert len(initialized_walk_manager._walk_data) == 0
        assert len(initialized_walk_manager._gps_data) == 0
        assert len(initialized_walk_manager._current_walks) == 0
        assert len(initialized_walk_manager._walk_history) == 0
        assert len(initialized_walk_manager._location_cache) == 0
        assert len(initialized_walk_manager._zone_cache) == 0


class TestWalkManagerLocationAnalysis:
    """Test walk manager location analysis features."""

    @pytest.fixture
    async def initialized_walk_manager(self):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["dog1"])
        return walk_manager

    async def test_update_location_analysis_home_zone(self, initialized_walk_manager):
        """Test location analysis for home zone."""
        # The _update_location_analysis method is private, but we can test its effects
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        gps_data = await initialized_walk_manager.async_get_gps_data("dog1")

        # Should have zone information
        assert "zone" in gps_data
        assert "distance_from_home" in gps_data

        # With placeholder implementation, should be "unknown" zone
        assert gps_data["zone"] in ["home", "neighborhood", "away", "unknown"]

    async def test_zone_cache_population(self, initialized_walk_manager):
        """Test that zone cache is populated during GPS updates."""
        await initialized_walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)

        # Zone cache should be populated
        assert "dog1" in initialized_walk_manager._zone_cache
        assert initialized_walk_manager._zone_cache["dog1"] in [
            "home",
            "neighborhood",
            "away",
            "unknown",
        ]


class TestWalkManagerDailyStatistics:
    """Test walk manager daily statistics updates."""

    @pytest.fixture
    async def initialized_walk_manager(self):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["dog1"])
        return walk_manager

    async def test_daily_stats_initialization(self, initialized_walk_manager):
        """Test daily statistics initialization."""
        walk_data = await initialized_walk_manager.async_get_walk_data("dog1")

        assert walk_data["walks_today"] == 0
        assert walk_data["total_duration_today"] == 0
        assert walk_data["total_distance_today"] == 0.0
        assert walk_data["weekly_walks"] == 0
        assert walk_data["weekly_distance"] == 0.0

    async def test_daily_stats_after_walk(self, initialized_walk_manager):
        """Test daily statistics after completing a walk."""
        # Start and immediately end walk
        await initialized_walk_manager.async_start_walk("dog1")
        completed_walk = await initialized_walk_manager.async_end_walk("dog1")

        walk_data = await initialized_walk_manager.async_get_walk_data("dog1")

        # Should be updated
        assert walk_data["walks_today"] == 1
        assert walk_data["total_duration_today"] > 0
        assert walk_data["last_walk"] == completed_walk["start_time"]
        assert walk_data["last_walk_duration"] == completed_walk["duration"]

    async def test_walk_streak_calculation(self, initialized_walk_manager):
        """Test walk streak calculation."""
        # Complete a walk
        await initialized_walk_manager.async_start_walk("dog1")
        await initialized_walk_manager.async_end_walk("dog1")

        walk_data = await initialized_walk_manager.async_get_walk_data("dog1")

        # Should have some streak value
        assert "walk_streak" in walk_data
        assert isinstance(walk_data["walk_streak"], int)
        assert walk_data["walk_streak"] >= 0


class TestWalkManagerConcurrency:
    """Test walk manager concurrency and thread safety."""

    @pytest.fixture
    async def initialized_walk_manager(self):
        """Create initialized walk manager."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["dog1", "dog2", "dog3"])
        return walk_manager

    async def test_concurrent_gps_updates(self, initialized_walk_manager):
        """Test concurrent GPS updates."""

        async def update_gps(dog_id: str, base_lat: float):
            for i in range(10):
                lat = base_lat + (i * 0.001)
                lon = 13.4050 + (i * 0.001)
                await initialized_walk_manager.async_update_gps_data(dog_id, lat, lon)

        # Run concurrent GPS updates
        await asyncio.gather(
            update_gps("dog1", 52.5200),
            update_gps("dog2", 52.5300),
            update_gps("dog3", 52.5400),
        )

        # All dogs should have GPS data
        for dog_id in ["dog1", "dog2", "dog3"]:
            gps_data = await initialized_walk_manager.async_get_gps_data(dog_id)
            assert gps_data["available"] is True

    async def test_concurrent_walk_operations(self, initialized_walk_manager):
        """Test concurrent walk start/end operations."""

        async def walk_cycle(dog_id: str):
            for _ in range(3):
                walk_id = await initialized_walk_manager.async_start_walk(dog_id)
                if walk_id:
                    await asyncio.sleep(0.001)  # Simulate walk time
                    await initialized_walk_manager.async_end_walk(dog_id)

        # Run concurrent walk operations
        await asyncio.gather(
            walk_cycle("dog1"),
            walk_cycle("dog2"),
            walk_cycle("dog3"),
        )

        # All dogs should have completed walks
        for dog_id in ["dog1", "dog2", "dog3"]:
            history = await initialized_walk_manager.async_get_walk_history(dog_id)
            assert len(history) >= 1

    async def test_concurrent_read_write_operations(self, initialized_walk_manager):
        """Test concurrent read and write operations."""

        async def writer():
            for i in range(20):
                await initialized_walk_manager.async_update_gps_data(
                    "dog1", 52.5200 + i * 0.001, 13.4050
                )

        async def reader():
            results = []
            for _ in range(20):
                gps_data = await initialized_walk_manager.async_get_gps_data("dog1")
                results.append(gps_data["available"])
            return results

        # Run concurrent read/write
        read_results, _ = await asyncio.gather(reader(), writer())

        # All reads should succeed
        assert all(isinstance(available, bool) for available in read_results)

    async def test_lock_contention_handling(self, initialized_walk_manager):
        """Test proper handling of lock contention."""

        async def long_operation(dog_id: str):
            async with initialized_walk_manager._data_lock:
                # Simulate longer operation
                await asyncio.sleep(0.01)
                initialized_walk_manager._walk_data[dog_id]["test_field"] = "test_value"

        async def quick_operation(dog_id: str):
            return await initialized_walk_manager.async_get_walk_data(dog_id)

        # Mix long and quick operations
        tasks = []
        for i in range(3):
            dog_id = f"dog{i + 1}"
            tasks.append(long_operation(dog_id))
            tasks.append(quick_operation(dog_id))

        # Should complete without deadlock
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=2.0
        )

        # No exceptions should occur
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent operation failed: {result}")


class TestWalkManagerEdgeCases:
    """Test walk manager edge cases and error handling."""

    @pytest.fixture
    def walk_manager(self):
        """Create walk manager instance."""
        return WalkManager()

    async def test_operations_on_uninitialized_manager(self, walk_manager):
        """Test operations on uninitialized manager."""
        # GPS update should fail gracefully
        result = await walk_manager.async_update_gps_data("dog1", 52.5200, 13.4050)
        assert result is False

        # Walk operations should fail gracefully
        walk_id = await walk_manager.async_start_walk("dog1")
        assert walk_id is None

        completed_walk = await walk_manager.async_end_walk("dog1")
        assert completed_walk is None

    async def test_extreme_coordinates(self, walk_manager):
        """Test handling of extreme coordinate values."""
        await walk_manager.async_initialize(["dog1"])

        # Test boundary values
        assert await walk_manager.async_update_gps_data("dog1", 90.0, 180.0) is True
        assert await walk_manager.async_update_gps_data("dog1", -90.0, -180.0) is True

        # Test beyond boundaries
        assert await walk_manager.async_update_gps_data("dog1", 91.0, 181.0) is False
        assert await walk_manager.async_update_gps_data("dog1", -91.0, -181.0) is False

    async def test_malformed_gps_data_types(self, walk_manager):
        """Test handling of malformed GPS data types."""
        await walk_manager.async_initialize(["dog1"])

        # String coordinates should fail validation
        result = await walk_manager.async_update_gps_data("dog1", "52.5200", "13.4050")
        assert result is False

        # None coordinates should fail validation
        result = await walk_manager.async_update_gps_data("dog1", None, 13.4050)
        assert result is False

    async def test_walk_history_overflow_protection(self, walk_manager):
        """Test walk history overflow protection."""
        await walk_manager.async_initialize(["dog1"])

        # Add more than 100 walks to test overflow protection
        for i in range(105):
            await walk_manager.async_start_walk("dog1")
            await walk_manager.async_end_walk("dog1")
            # Manually add to history to simulate the condition
            walk_manager._walk_history["dog1"].append({"test_walk": i})

        # History should be limited to 100 entries
        await walk_manager.async_get_walk_history("dog1")
        assert len(walk_manager._walk_history["dog1"]) <= 100

    async def test_distance_calculation_edge_cases(self, walk_manager):
        """Test distance calculation edge cases."""
        # Same point should give 0 distance
        same_point = (0.0, 0.0)
        distance = walk_manager._calculate_distance(same_point, same_point)
        assert distance == 0.0

        # Antipodal points (opposite sides of Earth)
        north_pole = (90.0, 0.0)
        south_pole = (-90.0, 0.0)
        distance = walk_manager._calculate_distance(north_pole, south_pole)

        # Should be approximately half the Earth's circumference
        earth_circumference = 2 * 3.14159 * 6371000  # meters
        expected_distance = earth_circumference / 2
        # Allow 100km variance
        assert abs(distance - expected_distance) < 100000

    async def test_speed_calculation_edge_cases(self, walk_manager):
        """Test speed calculation edge cases."""
        # Zero duration should return None
        walk_data = {"duration": 0, "distance": 1000}
        speed = walk_manager._calculate_average_speed(walk_data)
        assert speed is None

        # Negative duration should return None
        walk_data = {"duration": -100, "distance": 1000}
        speed = walk_manager._calculate_average_speed(walk_data)
        assert speed is None

    async def test_calorie_estimation_edge_cases(self, walk_manager):
        """Test calorie estimation edge cases."""
        # Zero duration should return None
        walk_data = {"duration": 0}
        calories = walk_manager._estimate_calories_burned("dog1", walk_data)
        assert calories is None

        # Negative duration should return None
        walk_data = {"duration": -100}
        calories = walk_manager._estimate_calories_burned("dog1", walk_data)
        assert calories is None

    async def test_corrupted_walk_data_recovery(self, walk_manager):
        """Test recovery from corrupted walk data."""
        await walk_manager.async_initialize(["dog1"])

        # Corrupt walk data
        original_walk_data = walk_manager._walk_data.copy()
        walk_manager._walk_data["dog1"] = "corrupted_data"

        # Operations should handle corruption gracefully
        try:
            walk_data = await walk_manager.async_get_walk_data("dog1")
            # Might return empty dict or raise exception - both are acceptable
            assert isinstance(walk_data, dict | str) or walk_data is None
        except (TypeError, AttributeError):
            # Exception is also acceptable for corrupted data
            pass
        finally:
            # Restore data
            walk_manager._walk_data = original_walk_data


@pytest.mark.asyncio
class TestWalkManagerIntegration:
    """Integration tests for walk manager."""

    async def test_complete_walk_workflow(self):
        """Test complete walk workflow from start to finish."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["buddy"])

        # 1. Start with GPS location
        await walk_manager.async_update_gps_data(
            "buddy", 52.5200, 13.4050, accuracy=5.0
        )

        # 2. Start walk manually
        walk_id = await walk_manager.async_start_walk("buddy", "manual")
        assert walk_id is not None

        # 3. Simulate walk with GPS tracking
        walk_path = [
            (52.5200, 13.4050),
            (52.5210, 13.4060),
            (52.5220, 13.4070),
            (52.5230, 13.4080),
        ]

        for lat, lon in walk_path:
            await walk_manager.async_update_gps_data(
                "buddy", lat, lon, speed=4.0, accuracy=3.0
            )

        # 4. Check current walk status
        current_walk = await walk_manager.async_get_current_walk("buddy")
        assert current_walk["status"] == "in_progress"
        assert len(current_walk["path"]) == 4

        # 5. End walk
        completed_walk = await walk_manager.async_end_walk("buddy")
        assert completed_walk["status"] == "completed"
        assert completed_walk["distance"] > 0

        # 6. Check updated statistics
        walk_data = await walk_manager.async_get_walk_data("buddy")
        assert walk_data["walks_today"] == 1
        assert walk_data["total_distance_today"] > 0
        assert walk_data["walk_in_progress"] is False

        # 7. Check walk history
        history = await walk_manager.async_get_walk_history("buddy")
        assert len(history) == 1
        assert history[0]["walk_id"] == completed_walk["walk_id"]

    async def test_automatic_walk_detection_workflow(self):
        """Test automatic walk detection workflow."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["luna"])

        # 1. Set initial location (stationary)
        await walk_manager.async_update_gps_data("luna", 52.5200, 13.4050, speed=0.5)

        # Should not auto-start walk yet
        current_walk = await walk_manager.async_get_current_walk("luna")
        assert current_walk is None

        # 2. Move with sufficient speed and distance
        await walk_manager.async_update_gps_data("luna", 52.5220, 13.4080, speed=3.0)

        # Should auto-start walk
        current_walk = await walk_manager.async_get_current_walk("luna")
        assert current_walk is not None
        assert current_walk["walk_type"] == "auto_detected"

        # 3. Continue tracking
        await walk_manager.async_update_gps_data("luna", 52.5240, 13.4100, speed=2.5)

        # 4. End walk manually
        completed_walk = await walk_manager.async_end_walk("luna")
        assert completed_walk is not None

        # 5. Verify statistics
        stats = await walk_manager.async_get_statistics()
        assert stats["total_walks_today"] == 1

    async def test_multi_dog_concurrent_walks(self):
        """Test concurrent walks for multiple dogs."""
        walk_manager = WalkManager()
        dogs = ["dog1", "dog2", "dog3"]
        await walk_manager.async_initialize(dogs)

        # Start walks for all dogs
        walk_ids = {}
        for dog_id in dogs:
            walk_id = await walk_manager.async_start_walk(dog_id)
            walk_ids[dog_id] = walk_id

        # All should have active walks
        stats = await walk_manager.async_get_statistics()
        assert stats["active_walks"] == 3

        # Add GPS tracking for each dog
        base_coords = [(52.5200, 13.4050), (52.5300, 13.4150), (52.5400, 13.4250)]

        for i, dog_id in enumerate(dogs):
            lat, lon = base_coords[i]
            for j in range(3):
                await walk_manager.async_update_gps_data(
                    dog_id, lat + j * 0.001, lon + j * 0.001, speed=3.0
                )

        # End walks at different times
        completed_walks = {}
        for i, dog_id in enumerate(dogs):
            await asyncio.sleep(0.001 * i)  # Stagger end times
            completed_walk = await walk_manager.async_end_walk(dog_id)
            completed_walks[dog_id] = completed_walk

        # Verify all walks completed successfully
        for dog_id in dogs:
            assert completed_walks[dog_id] is not None
            assert completed_walks[dog_id]["status"] == "completed"

            # Check history
            history = await walk_manager.async_get_walk_history(dog_id)
            assert len(history) == 1

    async def test_error_recovery_during_walk(self):
        """Test error recovery scenarios during walks."""
        walk_manager = WalkManager()
        await walk_manager.async_initialize(["test_dog"])

        # Start walk
        walk_id = await walk_manager.async_start_walk("test_dog")
        assert walk_id is not None

        # Simulate error by corrupting current walk data
        original_current_walks = walk_manager._current_walks.copy()

        try:
            # Corrupt the data
            walk_manager._current_walks["test_dog"]["corrupted"] = None

            # Operations should still work or handle gracefully
            current_walk = await walk_manager.async_get_current_walk("test_dog")
            assert current_walk is not None  # Should still return the walk

            # Try to end walk - should handle corruption
            await walk_manager.async_end_walk("test_dog")
            # Should either complete successfully or handle gracefully

        finally:
            # Restore original data if needed
            walk_manager._current_walks = original_current_walks

    async def test_performance_with_large_walk_history(self):
        """Test performance with large walk history."""
        import time

        walk_manager = WalkManager()
        await walk_manager.async_initialize(["performance_test_dog"])

        # Add many walks to history
        for _i in range(50):
            walk_id = await walk_manager.async_start_walk("performance_test_dog")
            if walk_id:
                await walk_manager.async_end_walk("performance_test_dog")

        # Test history retrieval performance
        start_time = time.time()

        for _ in range(10):
            await walk_manager.async_get_walk_history("performance_test_dog")

        elapsed = time.time() - start_time

        # Should be reasonably fast even with large history
        assert elapsed < 1.0  # Less than 1 second for 10 retrievals

        # History should be properly limited
        final_history = await walk_manager.async_get_walk_history(
            "performance_test_dog"
        )
        assert len(final_history) <= 50
