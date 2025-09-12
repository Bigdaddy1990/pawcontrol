"""Tests for the refactored Paw Control coordinator with specialized managers."""
from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timedelta
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import CONF_GPS_UPDATE_INTERVAL
from custom_components.pawcontrol.const import DEFAULT_GPS_UPDATE_INTERVAL
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.const import UPDATE_INTERVALS
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.exceptions import DogNotFoundError
from custom_components.pawcontrol.exceptions import GPSUnavailableError


class TestRefactoredPawControlCoordinator:
    """Test the refactored PawControl coordinator with specialized managers."""

    @pytest.fixture
    def mock_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
            ]
        }
        entry.options = {CONF_GPS_UPDATE_INTERVAL: 60}
        return entry

    @pytest.fixture
    def mock_managers(self):
        """Create mock managers for testing."""
        return {
            "data_manager": AsyncMock(),
            "dog_data_manager": AsyncMock(),
            "walk_manager": AsyncMock(),
            "feeding_manager": AsyncMock(),
            "health_calculator": Mock(),
        }

    @pytest.fixture
    def coordinator(self, hass: HomeAssistant, mock_entry, mock_managers):
        """Create a coordinator instance with mocked managers."""
        coordinator = PawControlCoordinator(hass, mock_entry)

        # Inject mock managers
        coordinator.set_managers(
            data_manager=mock_managers["data_manager"],
            dog_data_manager=mock_managers["dog_data_manager"],
            walk_manager=mock_managers["walk_manager"],
            feeding_manager=mock_managers["feeding_manager"],
            health_calculator=mock_managers["health_calculator"],
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_coordinator_initialization(self, hass: HomeAssistant, mock_entry):
        """Test coordinator initialization."""
        coordinator = PawControlCoordinator(hass, mock_entry)

        assert coordinator.hass == hass
        assert coordinator.config_entry == mock_entry
        assert coordinator.name == "PawControl Data"
        assert coordinator.update_interval.total_seconds() == 60
        assert isinstance(coordinator._dogs_config, list)
        assert len(coordinator._dogs_config) == 1
        assert coordinator._dogs_config[0][CONF_DOG_ID] == "test_dog"

        # Check that specialized managers are properly initialized
        assert coordinator._cache_manager is not None
        assert coordinator._batch_manager is not None
        assert coordinator._performance_monitor is not None

    @pytest.mark.asyncio
    async def test_manager_injection(self, coordinator, mock_managers):
        """Test that managers are properly injected."""
        assert coordinator._data_manager == mock_managers["data_manager"]
        assert coordinator.dog_data_manager == mock_managers["dog_data_manager"]
        assert coordinator.walk_manager == mock_managers["walk_manager"]
        assert coordinator.feeding_manager == mock_managers["feeding_manager"]
        assert coordinator.health_calculator == mock_managers["health_calculator"]

    @pytest.mark.asyncio
    async def test_fetch_dog_data_delegated_all_modules(
        self, coordinator, mock_managers
    ):
        """Test fetching data delegates to specialized managers for all modules."""
        # Setup mock responses
        mock_managers["feeding_manager"].async_get_feeding_data.return_value = {
            "last_feeding": "2025-01-15T10:00:00",
            "meals_today": 2,
        }

        mock_managers["walk_manager"].async_get_walk_data.return_value = {
            "walk_in_progress": False,
            "walks_today": 1,
        }

        mock_managers["walk_manager"].async_get_gps_data.return_value = {
            "latitude": 52.5200,
            "longitude": 13.4050,
            "available": True,
        }

        mock_managers["dog_data_manager"].async_get_dog_data.return_value = {
            "health": {"current_weight": 25.0, "health_status": "good"}
        }

        # Execute the delegated fetch
        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Verify all manager methods were called
        mock_managers["feeding_manager"].async_get_feeding_data.assert_called_once_with(
            "test_dog"
        )
        mock_managers["walk_manager"].async_get_walk_data.assert_called_once_with(
            "test_dog"
        )
        mock_managers["walk_manager"].async_get_gps_data.assert_called_once_with(
            "test_dog"
        )
        mock_managers["dog_data_manager"].async_get_dog_data.assert_called_once_with(
            "test_dog"
        )

        # Verify data structure
        assert "dog_info" in data
        assert data["dog_info"][CONF_DOG_ID] == "test_dog"
        assert data[MODULE_FEEDING]["meals_today"] == 2
        assert data[MODULE_WALK]["walks_today"] == 1
        assert data[MODULE_GPS]["available"] is True
        assert data[MODULE_HEALTH]["current_weight"] == 25.0

    @pytest.mark.asyncio
    async def test_fetch_dog_data_selective_modules(self, coordinator, mock_managers):
        """Test fetching data for dog with only some modules enabled."""
        # Modify dog config to only have feeding enabled
        coordinator._dogs_config[0]["modules"] = {MODULE_FEEDING: True}

        mock_managers["feeding_manager"].async_get_feeding_data.return_value = {
            "meals_today": 3
        }

        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Only feeding manager should be called
        mock_managers["feeding_manager"].async_get_feeding_data.assert_called_once()
        mock_managers["walk_manager"].async_get_walk_data.assert_not_called()
        mock_managers["walk_manager"].async_get_gps_data.assert_not_called()

        # Only feeding data should be present
        assert MODULE_FEEDING in data
        assert MODULE_WALK not in data
        assert MODULE_GPS not in data
        assert MODULE_HEALTH not in data

    @pytest.mark.asyncio
    async def test_cache_manager_integration(self, coordinator):
        """Test integration with CacheManager."""
        # Test cache set and get
        await coordinator._cache_manager.set("test_key", {"test": "data"})
        cached_data = await coordinator._cache_manager.get("test_key")

        assert cached_data["test"] == "data"

        # Test cache stats
        stats = coordinator._cache_manager.get_stats()
        assert "total_entries" in stats
        assert "hit_rate" in stats

    @pytest.mark.asyncio
    async def test_batch_manager_integration(self, coordinator):
        """Test integration with BatchManager."""
        # Add dogs to batch
        await coordinator._batch_manager.add_to_batch("test_dog", priority=5)
        await coordinator._batch_manager.add_to_batch("another_dog", priority=8)

        # Check pending count
        assert await coordinator._batch_manager.has_pending()

        # Get batch (should be priority ordered)
        batch = await coordinator._batch_manager.get_batch()
        assert "another_dog" in batch  # Higher priority should be first

        # Test batch stats
        stats = coordinator._batch_manager.get_stats()
        assert "max_batch_size" in stats

    @pytest.mark.asyncio
    async def test_performance_monitor_integration(self, coordinator):
        """Test integration with PerformanceMonitor."""
        # Record some performance data
        coordinator._performance_monitor.record_update(0.5, 0)  # 500ms, no errors
        coordinator._performance_monitor.record_update(1.2, 1)  # 1.2s, 1 error

        # Get performance stats
        stats = coordinator._performance_monitor.get_stats()
        assert "average_update_time" in stats
        assert "error_rate" in stats
        assert stats["total_updates"] == 2

    @pytest.mark.asyncio
    async def test_async_update_data_with_managers(self, coordinator, mock_managers):
        """Test data update using manager delegation."""
        # Setup feeding manager mock
        mock_managers["feeding_manager"].async_get_feeding_data.return_value = {
            "last_feeding": None,
            "meals_today": 0,
        }

        # Setup walk manager mocks
        mock_managers["walk_manager"].async_get_walk_data.return_value = {
            "walk_in_progress": False
        }
        mock_managers["walk_manager"].async_get_gps_data.return_value = {
            "available": False
        }

        # Setup dog data manager mock
        mock_managers["dog_data_manager"].async_get_dog_data.return_value = {
            "health": {}
        }

        # Execute update
        data = await coordinator._async_update_data()

        # Verify data structure and manager calls
        assert "test_dog" in data
        mock_managers["feeding_manager"].async_get_feeding_data.assert_called_with(
            "test_dog"
        )

    @pytest.mark.asyncio
    async def test_async_request_selective_refresh(self, coordinator):
        """Test selective refresh using BatchManager and CacheManager."""
        # Request refresh for specific dogs
        await coordinator.async_request_selective_refresh(["test_dog"], priority=8)

        # Verify cache was invalidated
        cached_data = await coordinator._cache_manager.get("dog_test_dog")
        assert cached_data is None  # Should be invalidated

        # Verify batch was updated
        assert await coordinator._batch_manager.has_pending()

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, coordinator):
        """Test cache invalidation functionality."""
        # Set cache data
        await coordinator._cache_manager.set("dog_test_dog", {"cached": True})

        # Invalidate cache for dog
        await coordinator.invalidate_dog_cache("test_dog")

        # Verify cache was cleared
        cached_data = await coordinator._cache_manager.get("dog_test_dog")
        assert cached_data is None

    @pytest.mark.asyncio
    async def test_background_tasks_startup(self, coordinator):
        """Test background tasks startup."""
        # Start background tasks
        await coordinator.async_start_background_tasks()

        # Verify tasks were created
        assert coordinator._maintenance_task is not None
        assert coordinator._batch_processor_task is not None
        assert not coordinator._maintenance_task.done()
        assert not coordinator._batch_processor_task.done()

    @pytest.mark.asyncio
    async def test_comprehensive_statistics(self, coordinator):
        """Test comprehensive statistics from all managers."""
        # Record some performance data
        coordinator._performance_monitor.record_update(0.5, 0)

        # Add some cache data
        await coordinator._cache_manager.set("test_key", {"test": "data"})

        # Add batch data
        await coordinator._batch_manager.add_to_batch("test_dog", 5)

        # Get comprehensive stats
        stats = coordinator.get_cache_stats()

        assert "cache" in stats
        assert "performance" in stats
        assert "batch" in stats
        assert stats["cache"]["total_entries"] >= 1
        assert stats["performance"]["total_updates"] >= 1

    @pytest.mark.asyncio
    async def test_manager_timeout_handling(self, coordinator, mock_managers):
        """Test timeout handling in manager delegation."""

        # Setup feeding manager to timeout
        async def slow_response():
            await asyncio.sleep(5)  # Longer than timeout
            return {"slow": "data"}

        mock_managers["feeding_manager"].async_get_feeding_data = slow_response

        # Mock other managers to return quickly
        mock_managers["walk_manager"].async_get_walk_data.return_value = {"quick": True}
        mock_managers["walk_manager"].async_get_gps_data.return_value = {
            "available": False
        }
        mock_managers["dog_data_manager"].async_get_dog_data.return_value = {
            "health": {}
        }

        # Execute fetch with timeout handling
        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Should handle timeout gracefully
        assert "dog_info" in data
        # Feeding data might be empty due to timeout, but should not crash

    @pytest.mark.asyncio
    async def test_error_handling_in_managers(self, coordinator, mock_managers):
        """Test error handling when managers raise exceptions."""
        # Setup feeding manager to raise exception
        mock_managers["feeding_manager"].async_get_feeding_data.side_effect = Exception(
            "Manager error"
        )

        # Other managers work normally
        mock_managers["walk_manager"].async_get_walk_data.return_value = {"walks": 0}
        mock_managers["walk_manager"].async_get_gps_data.return_value = {
            "available": False
        }
        mock_managers["dog_data_manager"].async_get_dog_data.return_value = {
            "health": {}
        }

        # Should handle manager errors gracefully
        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Should still have basic structure
        assert "dog_info" in data
        # Other modules should still work
        assert data[MODULE_WALK]["walks"] == 0

    @pytest.mark.asyncio
    async def test_shutdown_with_managers(self, coordinator):
        """Test shutdown cleans up all manager resources."""
        # Start background tasks
        await coordinator.async_start_background_tasks()

        # Add some data to managers
        await coordinator._cache_manager.set("test", {"data": True})
        await coordinator._batch_manager.add_to_batch("test_dog", 5)

        # Shutdown coordinator
        await coordinator.async_shutdown()

        # Verify cleanup
        assert coordinator._maintenance_task.done()
        assert coordinator._batch_processor_task.done()

        # Verify manager cleanup
        cache_stats = coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] == 0  # Cache should be cleared

    @pytest.mark.asyncio
    async def test_cache_optimization(self, coordinator):
        """Test cache optimization features."""
        # Add data with different access patterns
        await coordinator._cache_manager.set("hot_key", {"data": 1})
        await coordinator._cache_manager.set("cold_key", {"data": 2})

        # Access hot key multiple times
        for _ in range(10):
            await coordinator._cache_manager.get("hot_key")

        # Access cold key once
        await coordinator._cache_manager.get("cold_key")

        # Run optimization
        optimization_report = await coordinator._cache_manager.optimize_cache()

        assert optimization_report["optimization_completed"] is True
        assert "hot_keys_promoted" in optimization_report

    @pytest.mark.asyncio
    async def test_batch_optimization(self, coordinator):
        """Test batch optimization based on load."""
        # Add many pending updates to trigger optimization
        for i in range(50):
            await coordinator._batch_manager.add_to_batch(f"dog_{i}", 1)

        # Run optimization
        optimization_report = await coordinator._batch_manager.optimize_batching()

        assert "optimization_performed" in optimization_report
        assert "current_load" in optimization_report
        assert optimization_report["current_load"] == 50

    @pytest.mark.asyncio
    async def test_performance_health_score(self, coordinator):
        """Test performance health score calculation."""
        # Record good performance
        for _ in range(10):
            coordinator._performance_monitor.record_update(0.1, 0)  # Fast, no errors

        health_score = coordinator._performance_monitor.get_performance_health_score()

        assert health_score["health_level"] == "excellent"
        assert health_score["overall_score"] >= 90
        assert "recommendations" in health_score

    @pytest.mark.asyncio
    async def test_get_dog_config_methods(self, coordinator):
        """Test basic dog configuration methods still work."""
        # Test get_dog_config
        config = coordinator.get_dog_config("test_dog")
        assert config is not None
        assert config[CONF_DOG_ID] == "test_dog"

        # Test get_enabled_modules
        modules = coordinator.get_enabled_modules("test_dog")
        expected_modules = {MODULE_FEEDING, MODULE_WALK, MODULE_HEALTH, MODULE_GPS}
        assert modules == expected_modules

        # Test is_module_enabled
        assert coordinator.is_module_enabled("test_dog", MODULE_GPS) is True
        assert coordinator.is_module_enabled("test_dog", "nonexistent_module") is False

        # Test get_dog_ids
        dog_ids = coordinator.get_dog_ids()
        assert dog_ids == ["test_dog"]

    @pytest.mark.asyncio
    async def test_multiple_dogs_with_managers(self, coordinator, mock_managers):
        """Test coordinator handles multiple dogs with manager delegation."""
        # Add another dog
        coordinator._dogs_config.append(
            {
                CONF_DOG_ID: "second_dog",
                CONF_DOG_NAME: "Second Dog",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
        )

        # Setup manager responses for both dogs
        async def mock_feeding_response(dog_id):
            return {"dog_id": dog_id, "meals": 1 if dog_id == "test_dog" else 2}

        async def mock_walk_response(dog_id):
            return {"dog_id": dog_id, "walks": 1}

        mock_managers[
            "feeding_manager"
        ].async_get_feeding_data.side_effect = mock_feeding_response
        mock_managers[
            "walk_manager"
        ].async_get_walk_data.side_effect = mock_walk_response
        mock_managers["walk_manager"].async_get_gps_data.return_value = {
            "available": False
        }
        mock_managers["dog_data_manager"].async_get_dog_data.return_value = {
            "health": {}
        }

        # Update data for both dogs
        data = await coordinator._async_update_data()

        # Verify both dogs processed
        assert "test_dog" in data
        assert "second_dog" in data

        # Verify manager called for both dogs
        assert mock_managers["feeding_manager"].async_get_feeding_data.call_count == 2

    def test_coordinator_properties(self, coordinator):
        """Test coordinator properties and public interface."""
        # Test available property
        assert hasattr(coordinator, "available")

        # Test get_update_statistics
        stats = coordinator.get_update_statistics()
        assert "total_dogs" in stats
        assert "update_interval_seconds" in stats
        assert stats["total_dogs"] == 1

        # Test get_dog_data (should be empty initially)
        dog_data = coordinator.get_dog_data("test_dog")
        assert dog_data is None  # No data updated yet

        # Test get_all_dogs_data
        all_data = coordinator.get_all_dogs_data()
        assert isinstance(all_data, dict)

    @pytest.mark.asyncio
    async def test_manager_health_integration(self, coordinator, mock_managers):
        """Test health manager integration with feeding calculations."""
        # Setup health calculator mock
        mock_managers["health_calculator"].calculate_daily_calories.return_value = 800

        # Setup feeding manager with health awareness
        mock_managers["feeding_manager"].async_get_feeding_data.return_value = {
            "daily_calories": 800,
            "portion_size": 200,
            "health_aware": True,
        }

        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Verify health-aware feeding data
        feeding_data = data.get(MODULE_FEEDING, {})
        assert "health_aware" in feeding_data
        assert feeding_data["daily_calories"] == 800

    @pytest.mark.asyncio
    async def test_coordinator_resilience(self, coordinator, mock_managers):
        """Test coordinator resilience to manager failures."""
        # Make all managers fail
        for manager in mock_managers.values():
            if hasattr(manager, "async_get_feeding_data"):
                manager.async_get_feeding_data.side_effect = Exception("Manager failed")
            if hasattr(manager, "async_get_walk_data"):
                manager.async_get_walk_data.side_effect = Exception("Manager failed")
            if hasattr(manager, "async_get_gps_data"):
                manager.async_get_gps_data.side_effect = Exception("Manager failed")
            if hasattr(manager, "async_get_dog_data"):
                manager.async_get_dog_data.side_effect = Exception("Manager failed")

        # Coordinator should still provide basic structure
        data = await coordinator._fetch_dog_data_delegated("test_dog")

        # Should at least have dog_info
        assert "dog_info" in data
        assert data["dog_info"][CONF_DOG_ID] == "test_dog"

    @pytest.mark.asyncio
    async def test_update_interval_calculation_with_complexity(
        self, hass: HomeAssistant
    ):
        """Test update interval calculation considers module complexity."""
        # Test with high complexity (many GPS dogs)
        entry_complex = Mock(spec=ConfigEntry)
        entry_complex.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: f"gps_dog_{i}",
                    "modules": {
                        MODULE_GPS: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                    },
                }
                for i in range(5)
            ]
        }
        entry_complex.options = {}

        coordinator_complex = PawControlCoordinator(hass, entry_complex)

        # Should have longer interval due to complexity
        assert (
            coordinator_complex.update_interval.total_seconds()
            >= UPDATE_INTERVALS["frequent"]
        )

        # Test with low complexity (feeding only)
        entry_simple = Mock(spec=ConfigEntry)
        entry_simple.data = {
            CONF_DOGS: [{CONF_DOG_ID: "simple_dog", "modules": {MODULE_FEEDING: True}}]
        }
        entry_simple.options = {}

        coordinator_simple = PawControlCoordinator(hass, entry_simple)

        # Should have standard interval
        assert (
            coordinator_simple.update_interval.total_seconds()
            == UPDATE_INTERVALS["frequent"]
        )
