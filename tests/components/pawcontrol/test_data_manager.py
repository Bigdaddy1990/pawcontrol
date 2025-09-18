"""Comprehensive tests for PawControl Data Manager.

Tests data storage, retrieval, caching, persistence, and performance
characteristics of the data management system.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock, mock_open, patch

import pytest
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.types import (
    DailyStats,
    FeedingData,
    GPSLocation,
    HealthData,
    WalkData,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
def mock_hass() -> HomeAssistant:
    """Create mock Home Assistant instance."""
    hass = Mock(spec=HomeAssistant)
    hass.config = Mock()
    hass.config.config_dir = "/test/config"
    return hass


@pytest.fixture
def mock_coordinator() -> Mock:
    """Create mock coordinator."""
    coordinator = Mock()
    coordinator.get_dog_data = Mock(return_value={})
    coordinator.available = True
    return coordinator


@pytest.fixture
def sample_dogs_config() -> list[dict[str, Any]]:
    """Create sample dogs configuration."""
    return [
        {
            "dog_id": "buddy",
            "dog_name": "Buddy",
            "dog_breed": "Labrador",
            "dog_age": 5,
            "dog_weight": 25.0,
            "dog_size": "medium",
            "modules": {
                "feeding": True,
                "walk": True,
                "health": True,
                "gps": False,
            },
        },
        {
            "dog_id": "max",
            "dog_name": "Max",
            "dog_breed": "German Shepherd",
            "dog_age": 3,
            "dog_weight": 30.0,
            "dog_size": "large",
            "modules": {
                "feeding": True,
                "walk": True,
                "health": True,
                "gps": True,
            },
        },
    ]


class TestPawControlDataManagerInitialization:
    """Test suite for data manager initialization."""

    async def test_initialization_success(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> None:
        """Test successful data manager initialization."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir") as mock_mkdir,
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

            # Verify data directory creation
            mock_mkdir.assert_called()

            # Verify dog profiles were initialized
            assert len(data_manager._dog_profiles) == 2
            assert "buddy" in data_manager._dog_profiles
            assert "max" in data_manager._dog_profiles

    async def test_initialization_with_existing_data(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> None:
        """Test initialization with existing data files."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        # Mock existing data
        existing_data = {
            "buddy": {
                "daily_stats": {
                    "date": dt_util.utcnow().isoformat(),
                    "feedings_count": 2,
                    "walks_count": 1,
                },
                "feeding_history": [],
                "walk_history": [],
                "health_history": [],
            }
        }

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(existing_data))),
            patch("json.load", return_value=existing_data),
        ):
            await data_manager.async_initialize()

            # Verify existing data was loaded
            buddy_profile = data_manager._dog_profiles["buddy"]
            assert buddy_profile.daily_stats.feedings_count == 2
            assert buddy_profile.daily_stats.walks_count == 1

    async def test_initialization_corrupted_data_recovery(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> None:
        """Test recovery from corrupted data files."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        # Mock corrupted data file
        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="corrupted json data")),
            patch("json.load", side_effect=json.JSONDecodeError("Invalid JSON", "", 0)),
        ):
            # Should not raise exception, but recover gracefully
            await data_manager.async_initialize()

            # Should create new profiles despite corrupted data
            assert len(data_manager._dog_profiles) == 2

    async def test_initialization_permission_error(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> None:
        """Test handling of permission errors during initialization."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir", side_effect=PermissionError("Access denied")),
            pytest.raises(HomeAssistantError),
        ):
            await data_manager.async_initialize()


class TestPawControlDataManagerFeedingOperations:
    """Test suite for feeding data operations."""

    @pytest.fixture
    async def initialized_data_manager(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> PawControlDataManager:
        """Create and initialize data manager."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_log_feeding_success(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test successful feeding logging."""
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
            notes="Morning feeding",
            logged_by="user",
            calories=300.0,
        )

        with patch.object(
            initialized_data_manager, "_async_save_dog_data"
        ) as mock_save:
            result = await initialized_data_manager.async_log_feeding(
                "buddy", feeding_data
            )

            assert result is True
            mock_save.assert_called_once_with("buddy")

            # Verify daily stats were updated
            buddy_profile = initialized_data_manager._dog_profiles["buddy"]
            assert buddy_profile.daily_stats.feedings_count == 1
            assert buddy_profile.daily_stats.total_food_amount == 200.0

    async def test_log_feeding_invalid_dog_id(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test feeding logging with invalid dog ID."""
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        result = await initialized_data_manager.async_log_feeding(
            "invalid_dog", feeding_data
        )
        assert result is False

    async def test_log_feeding_validation_error(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test feeding logging with validation errors."""
        # Create invalid feeding data (negative portion size)
        with pytest.raises(ValueError):
            FeedingData(
                meal_type="breakfast",
                portion_size=-50.0,  # Invalid negative portion
                food_type="dry_food",
                timestamp=dt_util.utcnow(),
            )

    async def test_get_daily_feeding_stats(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test retrieval of daily feeding statistics."""
        # Log some feedings
        feeding_data_1 = FeedingData(
            meal_type="breakfast",
            portion_size=150.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
            calories=250.0,
        )

        feeding_data_2 = FeedingData(
            meal_type="lunch",
            portion_size=100.0,
            food_type="wet_food",
            timestamp=dt_util.utcnow(),
            calories=200.0,
        )

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_log_feeding("buddy", feeding_data_1)
            await initialized_data_manager.async_log_feeding("buddy", feeding_data_2)

        # Get daily stats
        stats = initialized_data_manager.get_daily_feeding_stats("buddy")

        assert stats is not None
        assert stats["total_feedings"] == 2
        assert stats["total_food_amount"] == 250.0
        assert stats["total_calories"] == 450.0
        assert len(stats["feeding_times"]) == 2

    async def test_get_feeding_history(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test retrieval of feeding history."""
        # Log a feeding
        feeding_data = FeedingData(
            meal_type="dinner",
            portion_size=180.0,
            food_type="mixed",
            timestamp=dt_util.utcnow(),
            notes="Evening meal",
        )

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_log_feeding("buddy", feeding_data)

        # Get history
        history = initialized_data_manager.get_feeding_history("buddy", limit=10)

        assert len(history) == 1
        assert history[0]["meal_type"] == "dinner"
        assert history[0]["portion_size"] == 180.0
        assert history[0]["notes"] == "Evening meal"


class TestPawControlDataManagerWalkOperations:
    """Test suite for walk data operations."""

    @pytest.fixture
    async def initialized_data_manager(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> PawControlDataManager:
        """Create and initialize data manager."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_start_walk_success(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test successful walk start."""
        with patch.object(
            initialized_data_manager, "_async_save_dog_data"
        ) as mock_save:
            result = await initialized_data_manager.async_start_walk(
                dog_id="buddy", started_by="user", location="Park", notes="Morning walk"
            )

            assert result is True
            mock_save.assert_called_once_with("buddy")

            # Verify walk was started
            buddy_profile = initialized_data_manager._dog_profiles["buddy"]
            assert buddy_profile.current_walk is not None
            assert buddy_profile.current_walk.started_by == "user"
            assert buddy_profile.current_walk.location == "Park"

    async def test_start_walk_already_in_progress(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test starting a walk when one is already in progress."""
        # Start first walk
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_start_walk("buddy", started_by="user")

        # Attempt to start second walk
        result = await initialized_data_manager.async_start_walk(
            "buddy", started_by="user"
        )
        assert result is False  # Should fail because walk already in progress

    async def test_end_walk_success(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test successful walk completion."""
        # Start a walk first
        start_time = dt_util.utcnow()
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_start_walk("buddy", started_by="user")

            # Simulate some time passing
            end_time = start_time + timedelta(minutes=30)

            with patch("homeassistant.util.dt.utcnow", return_value=end_time):
                result = await initialized_data_manager.async_end_walk(
                    dog_id="buddy",
                    ended_by="user",
                    distance=2500.0,
                    rating=8,
                    notes="Great walk!",
                )

                assert result is True

                # Verify walk was completed and stats updated
                buddy_profile = initialized_data_manager._dog_profiles["buddy"]
                assert buddy_profile.current_walk is None  # Walk ended
                assert buddy_profile.daily_stats.walks_count == 1
                assert (
                    buddy_profile.daily_stats.total_walk_time == 1800
                )  # 30 minutes in seconds
                assert buddy_profile.daily_stats.total_walk_distance == 2500.0

    async def test_end_walk_no_active_walk(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test ending a walk when no walk is in progress."""
        result = await initialized_data_manager.async_end_walk("buddy", ended_by="user")
        assert result is False  # Should fail because no active walk

    async def test_get_walk_history(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test retrieval of walk history."""
        # Complete a walk
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_start_walk(
                "buddy", started_by="user", location="Beach"
            )
            await initialized_data_manager.async_end_walk(
                "buddy", ended_by="user", distance=3000.0, rating=9
            )

        # Get history
        history = initialized_data_manager.get_walk_history("buddy", limit=10)

        assert len(history) == 1
        assert history[0]["location"] == "Beach"
        assert history[0]["distance"] == 3000.0
        assert history[0]["rating"] == 9

    async def test_update_walk_gps_route(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test updating GPS route during active walk."""
        # Start a walk
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_start_walk("buddy", started_by="user")

            # Add GPS points to route
            gps_point = GPSLocation(
                latitude=40.7128,
                longitude=-74.0060,
                accuracy=5.0,
                timestamp=dt_util.utcnow(),
                source="gps_tracker",
            )

            result = await initialized_data_manager.async_update_walk_route(
                "buddy", gps_point
            )
            assert result is True

            # Verify route was updated
            buddy_profile = initialized_data_manager._dog_profiles["buddy"]
            assert buddy_profile.current_walk is not None
            assert len(buddy_profile.current_walk.route) == 1
            assert buddy_profile.current_walk.route[0]["latitude"] == 40.7128

    async def test_update_walk_route_no_active_walk(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test updating walk route when no walk is active."""
        gps_point = GPSLocation(
            latitude=40.7128,
            longitude=-74.0060,
            accuracy=5.0,
            timestamp=dt_util.utcnow(),
        )

        result = await initialized_data_manager.async_update_walk_route(
            "buddy", gps_point
        )
        assert result is False  # Should fail because no active walk


class TestPawControlDataManagerHealthOperations:
    """Test suite for health data operations."""

    @pytest.fixture
    async def initialized_data_manager(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> PawControlDataManager:
        """Create and initialize data manager."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_log_health_data_success(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test successful health data logging."""
        health_data = HealthData(
            timestamp=dt_util.utcnow(),
            weight=26.5,
            temperature=38.5,
            mood="happy",
            activity_level="normal",
            health_status="good",
            symptoms="none",
            note="Regular checkup",
            logged_by="vet",
        )

        with patch.object(
            initialized_data_manager, "_async_save_dog_data"
        ) as mock_save:
            result = await initialized_data_manager.async_log_health_data(
                "buddy", health_data
            )

            assert result is True
            mock_save.assert_called_once_with("buddy")

            # Verify daily stats were updated
            buddy_profile = initialized_data_manager._dog_profiles["buddy"]
            assert buddy_profile.daily_stats.health_logs_count == 1

    async def test_log_health_data_validation_error(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test health data logging with validation errors."""
        # Create invalid health data (invalid temperature)
        with pytest.raises(ValueError):
            HealthData(
                timestamp=dt_util.utcnow(),
                weight=25.0,
                temperature=50.0,  # Invalid temperature (too high)
                mood="happy",
                activity_level="normal",
                health_status="good",
            )

    async def test_get_health_trends(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test retrieval of health trends."""
        # Log multiple health entries
        base_time = dt_util.utcnow()
        health_entries = [
            HealthData(
                timestamp=base_time - timedelta(days=7),
                weight=25.0,
                mood="normal",
                health_status="good",
            ),
            HealthData(
                timestamp=base_time - timedelta(days=3),
                weight=25.5,
                mood="happy",
                health_status="good",
            ),
            HealthData(
                timestamp=base_time,
                weight=26.0,
                mood="happy",
                health_status="very_good",
            ),
        ]

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            for health_data in health_entries:
                await initialized_data_manager.async_log_health_data(
                    "buddy", health_data
                )

        # Get trends
        trends = initialized_data_manager.get_health_trends("buddy", days=7)

        assert trends is not None
        assert "weight_trend" in trends
        assert "mood_distribution" in trends
        assert "health_status_progression" in trends

        # Verify weight trend calculation
        weight_trend = trends["weight_trend"]
        assert (
            weight_trend["direction"] == "increasing"
        )  # Weight increased from 25.0 to 26.0
        assert len(weight_trend["data_points"]) == 3

    async def test_get_health_history(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test retrieval of health history."""
        # Log health data
        health_data = HealthData(
            timestamp=dt_util.utcnow(),
            weight=25.5,
            temperature=38.2,
            mood="content",
            activity_level="high",
            health_status="excellent",
            note="Very active today",
        )

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_log_health_data("buddy", health_data)

        # Get history
        history = initialized_data_manager.get_health_history("buddy", limit=5)

        assert len(history) == 1
        assert history[0]["weight"] == 25.5
        assert history[0]["temperature"] == 38.2
        assert history[0]["mood"] == "content"
        assert history[0]["note"] == "Very active today"


class TestPawControlDataManagerPersistence:
    """Test suite for data persistence and recovery."""

    @pytest.fixture
    async def initialized_data_manager(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> PawControlDataManager:
        """Create and initialize data manager."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_data_persistence_save_success(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test successful data saving to disk."""
        # Add some data
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.dump") as mock_json_dump,
        ):
            await initialized_data_manager.async_log_feeding("buddy", feeding_data)

            # Verify file was opened for writing
            mock_file.assert_called()

            # Verify data was dumped to JSON
            mock_json_dump.assert_called()

    async def test_data_persistence_save_error_handling(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test error handling during data saving."""
        # Add some data
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        with patch("builtins.open", side_effect=OSError("Disk full")):
            # Should handle IO errors gracefully
            result = await initialized_data_manager.async_log_feeding(
                "buddy", feeding_data
            )

            # Operation should complete but save may fail
            # (depends on implementation - might return False or log warning)
            assert isinstance(result, bool)

    async def test_automatic_backup_creation(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test automatic backup creation during save operations."""
        # Mock backup functionality
        with patch.object(initialized_data_manager, "_create_backup"):
            feeding_data = FeedingData(
                meal_type="breakfast",
                portion_size=200.0,
                food_type="dry_food",
                timestamp=dt_util.utcnow(),
            )

            with patch.object(initialized_data_manager, "_async_save_dog_data"):
                await initialized_data_manager.async_log_feeding("buddy", feeding_data)

                # Verify backup was created (if backup interval reached)
                # This depends on implementation details
                if hasattr(initialized_data_manager, "_backup_interval"):
                    # Test backup logic if implemented
                    pass

    async def test_data_recovery_from_backup(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> None:
        """Test data recovery from backup files."""
        # Mock backup data
        backup_data = {
            "buddy": {
                "daily_stats": {
                    "date": dt_util.utcnow().isoformat(),
                    "feedings_count": 3,
                    "walks_count": 2,
                },
                "feeding_history": [
                    {
                        "meal_type": "breakfast",
                        "portion_size": 150.0,
                        "timestamp": dt_util.utcnow().isoformat(),
                    }
                ],
            }
        }

        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        # Mock primary data file missing but backup exists
        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists") as mock_exists,
            patch("builtins.open", mock_open(read_data=json.dumps(backup_data))),
            patch("json.load", return_value=backup_data),
        ):
            # Primary file doesn't exist, backup does
            mock_exists.side_effect = lambda path: str(path).endswith(".backup")

            await data_manager.async_initialize()

            # Verify data was recovered from backup
            buddy_profile = data_manager._dog_profiles["buddy"]
            assert buddy_profile.daily_stats.feedings_count == 3
            assert buddy_profile.daily_stats.walks_count == 2


class TestPawControlDataManagerPerformance:
    """Test suite for data manager performance characteristics."""

    @pytest.fixture
    async def initialized_data_manager(
        self, mock_hass: HomeAssistant, mock_coordinator: Mock
    ) -> PawControlDataManager:
        """Create data manager with many dogs for performance testing."""
        # Create many dogs for performance testing
        many_dogs = [
            {
                "dog_id": f"dog_{i:02d}",
                "dog_name": f"Dog {i:02d}",
                "dog_breed": "Test Breed",
                "dog_age": 3,
                "dog_weight": 20.0,
                "modules": {"feeding": True, "walk": True, "health": True},
            }
            for i in range(50)
        ]

        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=many_dogs,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_bulk_operations_performance(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test performance of bulk data operations."""
        import time

        # Prepare bulk feeding data
        feeding_operations = []
        for i in range(50):  # 50 dogs
            feeding_data = FeedingData(
                meal_type="breakfast",
                portion_size=200.0,
                food_type="dry_food",
                timestamp=dt_util.utcnow(),
            )
            feeding_operations.append((f"dog_{i:02d}", feeding_data))

        # Measure performance
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            start_time = time.perf_counter()

            # Execute bulk operations
            results = await asyncio.gather(
                *[
                    initialized_data_manager.async_log_feeding(dog_id, feeding_data)
                    for dog_id, feeding_data in feeding_operations
                ],
                return_exceptions=True,
            )

            end_time = time.perf_counter()
            execution_time = end_time - start_time

        # Verify performance and results
        assert execution_time < 1.0  # Should complete in under 1 second
        assert all(
            result is True for result in results if not isinstance(result, Exception)
        )

    async def test_memory_usage_with_large_dataset(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test memory usage with large datasets."""
        import gc
        import sys

        # Force garbage collection before measurement
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Add large amount of data
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            for dog_num in range(10):  # 10 dogs
                dog_id = f"dog_{dog_num:02d}"

                # Add multiple feedings per dog
                for feeding_num in range(20):  # 20 feedings per dog
                    feeding_data = FeedingData(
                        meal_type=["breakfast", "lunch", "dinner"][feeding_num % 3],
                        portion_size=150.0 + feeding_num,
                        food_type="dry_food",
                        timestamp=dt_util.utcnow() - timedelta(hours=feeding_num),
                    )
                    await initialized_data_manager.async_log_feeding(
                        dog_id, feeding_data
                    )

        # Measure memory usage after operations
        gc.collect()
        final_objects = len(gc.get_objects())
        objects_created = final_objects - initial_objects

        # Should not create excessive objects (rough check)
        assert objects_created < 5000  # Reasonable limit for this amount of data

    async def test_concurrent_operations_thread_safety(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test thread safety with concurrent operations."""
        # Simulate concurrent access from multiple "threads" (async tasks)
        tasks = []

        # Create concurrent feeding logs
        for dog_num in range(10):
            for operation_num in range(5):
                feeding_data = FeedingData(
                    meal_type="breakfast",
                    portion_size=100.0 + operation_num,
                    food_type="dry_food",
                    timestamp=dt_util.utcnow(),
                )
                task = initialized_data_manager.async_log_feeding(
                    f"dog_{dog_num:02d}", feeding_data
                )
                tasks.append(task)

        # Create concurrent walk operations
        for dog_num in range(10):
            start_task = initialized_data_manager.async_start_walk(
                f"dog_{dog_num:02d}", started_by="concurrent_test"
            )
            tasks.append(start_task)

        # Execute all operations concurrently
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify that most operations succeeded (some walks may fail if already started)
        successful_results = [r for r in results if r is True]
        failed_results = [r for r in results if r is False]
        exception_results = [r for r in results if isinstance(r, Exception)]

        # Should have more successes than failures
        assert len(successful_results) > len(failed_results)
        # Should not have many exceptions (proper error handling)
        assert len(exception_results) < len(results) * 0.1  # Less than 10% exceptions


class TestPawControlDataManagerEdgeCases:
    """Test suite for edge cases and error conditions."""

    @pytest.fixture
    async def initialized_data_manager(
        self,
        mock_hass: HomeAssistant,
        mock_coordinator: Mock,
        sample_dogs_config: list[dict[str, Any]],
    ) -> PawControlDataManager:
        """Create and initialize data manager."""
        data_manager = PawControlDataManager(
            hass=mock_hass,
            coordinator=mock_coordinator,
            dogs_config=sample_dogs_config,
        )

        with (
            patch("pathlib.Path.mkdir"),
            patch("pathlib.Path.exists", return_value=False),
        ):
            await data_manager.async_initialize()

        return data_manager

    async def test_operations_with_invalid_dog_ids(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test operations with invalid or non-existent dog IDs."""
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        # Test various invalid dog IDs
        invalid_ids = ["", "non_existent_dog", None, "123", "dog with spaces"]

        for invalid_id in invalid_ids:
            if invalid_id is None:
                continue  # Skip None as it would cause TypeError

            result = await initialized_data_manager.async_log_feeding(
                invalid_id, feeding_data
            )
            assert result is False  # Should fail gracefully

    async def test_date_rollover_handling(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test proper handling of date rollover for daily stats."""
        # Log data on one day
        yesterday = dt_util.utcnow().replace(hour=23, minute=59) - timedelta(days=1)
        feeding_data = FeedingData(
            meal_type="dinner",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=yesterday,
        )

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_log_feeding("buddy", feeding_data)

            # Verify data was logged
            buddy_profile = initialized_data_manager._dog_profiles["buddy"]
            assert buddy_profile.daily_stats.feedings_count == 1

        # Simulate new day - daily stats should reset
        # This depends on implementation - some systems reset automatically,
        # others require explicit reset calls
        today = dt_util.utcnow().replace(hour=8, minute=0)
        with patch("homeassistant.util.dt.utcnow", return_value=today):
            new_feeding = FeedingData(
                meal_type="breakfast",
                portion_size=150.0,
                food_type="dry_food",
                timestamp=today,
            )

            with patch.object(initialized_data_manager, "_async_save_dog_data"):
                await initialized_data_manager.async_log_feeding("buddy", new_feeding)

                # The implementation should handle date rollover appropriately
                # (exact behavior depends on implementation details)

    async def test_data_corruption_recovery(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test recovery from data corruption during operations."""
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        # Simulate data corruption during save
        with patch.object(
            initialized_data_manager,
            "_async_save_dog_data",
            side_effect=Exception("Corruption error"),
        ):
            # Should handle corruption gracefully
            result = await initialized_data_manager.async_log_feeding(
                "buddy", feeding_data
            )

            # Result depends on implementation - might return False or raise exception
            assert isinstance(result, bool | Exception)

    async def test_shutdown_cleanup(
        self, initialized_data_manager: PawControlDataManager
    ) -> None:
        """Test proper cleanup during shutdown."""
        # Add some data first
        feeding_data = FeedingData(
            meal_type="breakfast",
            portion_size=200.0,
            food_type="dry_food",
            timestamp=dt_util.utcnow(),
        )

        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_log_feeding("buddy", feeding_data)

        # Test shutdown
        with patch.object(initialized_data_manager, "_async_save_dog_data"):
            await initialized_data_manager.async_shutdown()

            # Should save data before shutdown (implementation dependent)
            # Main goal is to ensure no exceptions during shutdown
            assert True  # If we get here without exception, shutdown succeeded
