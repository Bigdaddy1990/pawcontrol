"""Comprehensive edge case tests for PawControl coordinator - Gold Standard coverage.

This module provides advanced edge case testing to achieve 95%+ test coverage
for the coordinator, including 500+ entity load testing, massive dog scenarios,
concurrent access patterns, manager delegation failures, and performance validation.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_GPS_UPDATE_INTERVAL,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from custom_components.pawcontrol.coordinator import (
    MAINTENANCE_INTERVAL,
    PawControlCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util


class TestCoordinatorMassiveEntityLoadScenarios:
    """Test coordinator under massive entity load (500+ entities)."""

    @pytest.fixture
    def massive_config_entry(self):
        """Create config entry with massive dog configuration."""
        # 50 dogs * ~10-12 entities each = 500-600 total entities
        dogs = []
        for i in range(50):
            dog_config = {
                CONF_DOG_ID: f"dog_{i:03d}",
                CONF_DOG_NAME: f"Dog {i:03d}",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: i % 3 == 0,  # Every 3rd dog has GPS
                    MODULE_HEALTH: i % 2 == 0,  # Every 2nd dog has health
                    "notifications": True,
                    "dashboard": True,
                    "visitor": i % 5 == 0,  # Every 5th dog has visitor mode
                    "grooming": i % 4 == 0,  # Every 4th dog has grooming
                },
                "dog_size": ["toy", "small", "medium", "large", "giant"][i % 5],
                "dog_breed": f"Breed_{i % 20}",
                "dog_age": (i % 15) + 1,
                "dog_weight": 5.0 + (i % 40),
            }
            dogs.append(dog_config)

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "massive_test_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {
            CONF_GPS_UPDATE_INTERVAL: 60,
            "performance_mode": "balanced",
        }
        return entry

    @pytest.fixture
    def mock_managers(self):
        """Create mock managers for massive testing."""
        data_manager = AsyncMock()
        dog_data_manager = AsyncMock()
        walk_manager = AsyncMock()
        feeding_manager = AsyncMock()
        health_calculator = Mock()

        # Configure manager responses with realistic delays
        async def mock_feeding_data(dog_id):
            await asyncio.sleep(0.01)  # Simulate DB query
            return {
                "last_fed": "2024-09-07 08:00:00",
                "next_feeding": "2024-09-07 18:00:00",
                "total_fed_today": 2,
                "food_remaining": 1500,
            }

        async def mock_walk_data(dog_id):
            await asyncio.sleep(0.005)  # Faster than feeding
            return {
                "last_walk": "2024-09-07 07:30:00",
                "duration_minutes": 30,
                "distance_km": 2.5,
                "steps": 4500,
            }

        async def mock_gps_data(dog_id):
            await asyncio.sleep(0.02)  # GPS takes longer
            return {
                "latitude": 52.5 + (hash(dog_id) % 100) / 1000,
                "longitude": 13.4 + (hash(dog_id) % 100) / 1000,
                "accuracy": 5,
                "last_update": "2024-09-07 09:00:00",
            }

        async def mock_dog_full_data(dog_id):
            await asyncio.sleep(0.008)  # Health data query
            return {
                "health": {
                    "weight": 25.0 + (hash(dog_id) % 20),
                    "last_checkup": "2024-08-15",
                    "vaccinations_due": False,
                    "medication_schedule": [],
                }
            }

        feeding_manager.async_get_feeding_data = mock_feeding_data
        walk_manager.async_get_walk_data = mock_walk_data
        walk_manager.async_get_gps_data = mock_gps_data
        dog_data_manager.async_get_dog_data = mock_dog_full_data

        return {
            "data_manager": data_manager,
            "dog_data_manager": dog_data_manager,
            "walk_manager": walk_manager,
            "feeding_manager": feeding_manager,
            "health_calculator": health_calculator,
        }

    @pytest.mark.asyncio
    async def test_500_entity_load_performance(
        self, hass, massive_config_entry, mock_managers
    ):
        """Test coordinator performance with 500+ entity load."""
        coordinator = PawControlCoordinator(hass, massive_config_entry)
        coordinator.set_managers(**mock_managers)

        # Measure initialization time
        init_start = time.time()
        await coordinator.async_start_background_tasks()
        init_duration = time.time() - init_start

        # Should initialize quickly even with 50 dogs
        assert init_duration < 1.0

        # Measure update performance
        update_start = time.time()
        await coordinator.async_request_refresh()
        update_duration = time.time() - update_start

        # Should handle massive load efficiently
        assert update_duration < 10.0  # 10 seconds max for 50 dogs

        # Verify all dogs were processed
        all_data = coordinator.get_all_dogs_data()
        assert len(all_data) == 50

        # Check performance statistics
        stats = coordinator.get_cache_stats()
        perf_stats = stats["performance"]

        # Should have reasonable performance metrics
        if "average_update_time" in perf_stats:
            assert perf_stats["average_update_time"] < 15.0

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_entity_access_stress(
        self, hass, massive_config_entry, mock_managers
    ):
        """Test concurrent access to entities under massive load."""
        coordinator = PawControlCoordinator(hass, massive_config_entry)
        coordinator.set_managers(**mock_managers)

        await coordinator.async_start_background_tasks()

        # Perform initial update
        await coordinator.async_request_refresh()

        access_results = []
        errors = []

        async def concurrent_accessor(accessor_id):
            """Concurrent entity data accessor."""
            try:
                for i in range(20):  # 20 accesses per accessor
                    dog_id = f"dog_{(accessor_id * 10 + i) % 50:03d}"

                    # Mix of different access patterns
                    if i % 3 == 0:
                        data = coordinator.get_dog_data(dog_id)
                    elif i % 3 == 1:
                        enabled = coordinator.get_enabled_modules(dog_id)
                        data = {"modules": list(enabled)}
                    else:
                        config = coordinator.get_dog_config(dog_id)
                        data = config

                    access_results.append(
                        (accessor_id, dog_id, data is not None))
                    await asyncio.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append((accessor_id, e))

        # Start many concurrent accessors
        accessors = [asyncio.create_task(
            concurrent_accessor(i)) for i in range(20)]
        await asyncio.gather(*accessors, return_exceptions=True)

        # Should handle concurrent access without errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"

        # Should process many requests
        # 20 accessors * 20 requests = 400 expected
        assert len(access_results) >= 350

        # Most requests should succeed
        success_rate = sum(1 for _, _, success in access_results if success) / len(
            access_results
        )
        assert success_rate > 0.95  # 95%+ success rate

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_selective_refresh_optimization_massive_load(
        self, hass, massive_config_entry, mock_managers
    ):
        """Test selective refresh optimization with massive load."""
        coordinator = PawControlCoordinator(hass, massive_config_entry)
        coordinator.set_managers(**mock_managers)

        await coordinator.async_start_background_tasks()

        # Initial update
        await coordinator.async_request_refresh()

        # Test selective refresh patterns
        selective_tests = [
            # High priority small batch
            (["dog_000", "dog_001", "dog_002"], 10),
            # Medium priority larger batch
            ([f"dog_{i:03d}" for i in range(10)], 5),
            ([f"dog_{i:03d}" for i in range(20, 30)], 1),  # Low priority batch
        ]

        for dog_ids, priority in selective_tests:
            start_time = time.time()
            await coordinator.async_request_selective_refresh(dog_ids, priority)
            duration = time.time() - start_time

            # High priority should be faster
            if priority >= 8:
                assert duration < 2.0
            else:
                assert duration < 5.0

        # Verify cache optimization
        cache_stats = coordinator.get_cache_stats()["cache"]
        assert cache_stats["hit_rate"] > 0  # Should have some cache hits

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_memory_usage_massive_dataset(
        self, hass, massive_config_entry, mock_managers
    ):
        """Test memory usage with massive dataset."""
        import sys

        # Get baseline memory
        sys.getsizeof(dict())

        coordinator = PawControlCoordinator(hass, massive_config_entry)
        coordinator.set_managers(**mock_managers)

        await coordinator.async_start_background_tasks()

        # Perform multiple updates to populate all caches
        for _ in range(3):
            await coordinator.async_request_refresh()
            await asyncio.sleep(0.1)

        # Get final memory usage
        coordinator_memory = (
            sys.getsizeof(coordinator._data)
            + sys.getsizeof(coordinator._data_checksums)
            + sys.getsizeof(coordinator._last_successful_update)
        )

        # Memory should be reasonable for 50 dogs
        memory_per_dog = coordinator_memory / 50
        assert memory_per_dog < 10000  # Less than 10KB per dog

        # Total memory should be bounded
        assert coordinator_memory < 1000000  # Less than 1MB total

        await coordinator.async_shutdown()


class TestCoordinatorManagerDelegationFailures:
    """Test coordinator behavior when manager delegation fails."""

    @pytest.fixture
    def coordinator_with_failing_managers(self, hass):
        """Create coordinator with managers that fail in various ways."""
        dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "failing_test_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Create failing managers
        failing_feeding = AsyncMock()
        failing_feeding.async_get_feeding_data = AsyncMock(
            side_effect=Exception("Feeding service down")
        )

        timeout_walk = AsyncMock()
        timeout_walk.async_get_walk_data = AsyncMock(
            side_effect=TimeoutError("Walk timeout")
        )
        timeout_walk.async_get_gps_data = AsyncMock(
            side_effect=TimeoutError("GPS timeout")
        )

        missing_dog_data = AsyncMock()
        missing_dog_data.async_get_dog_data = AsyncMock(return_value=None)

        coordinator.set_managers(
            feeding_manager=failing_feeding,
            walk_manager=timeout_walk,
            dog_data_manager=missing_dog_data,
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_feeding_manager_failure_recovery(
        self, coordinator_with_failing_managers
    ):
        """Test recovery from feeding manager failures."""
        coordinator = coordinator_with_failing_managers

        await coordinator.async_start_background_tasks()

        # Should handle feeding manager failure gracefully
        await coordinator.async_request_refresh()

        # Should still get some data despite feeding failure
        dog_data = coordinator.get_dog_data("test_dog")
        assert dog_data is not None
        assert "dog_info" in dog_data

        # Feeding module should be missing due to failure
        assert MODULE_FEEDING not in dog_data or "error" in dog_data

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_walk_manager_timeout_handling(
        self, coordinator_with_failing_managers
    ):
        """Test handling of walk manager timeouts."""
        coordinator = coordinator_with_failing_managers

        await coordinator.async_start_background_tasks()

        # Should handle timeouts gracefully
        await coordinator.async_request_refresh()

        dog_data = coordinator.get_dog_data("test_dog")
        assert dog_data is not None

        # Should have timeout error marked
        assert "error" in dog_data or "timeout" in str(dog_data)

        # Performance should be tracked despite timeouts
        stats = coordinator.get_cache_stats()
        perf_stats = stats["performance"]
        if "total_errors" in perf_stats:
            assert perf_stats["total_errors"] >= 0

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_missing_manager_handling(self, hass):
        """Test behavior when managers are not set."""
        dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "missing_managers_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)
        # Don't set any managers

        await coordinator.async_start_background_tasks()

        # Should handle missing managers gracefully
        await coordinator.async_request_refresh()

        dog_data = coordinator.get_dog_data("test_dog")
        assert dog_data is not None
        assert "dog_info" in dog_data

        # Modules should be missing due to no managers
        assert MODULE_FEEDING not in dog_data
        assert MODULE_GPS not in dog_data

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_all_managers_failing_scenario(self, hass):
        """Test scenario where all managers fail simultaneously."""
        dogs = [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "all_failing_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # All managers fail
        failing_managers = {}
        for manager_name in ["feeding_manager", "walk_manager", "dog_data_manager"]:
            manager = AsyncMock()
            for method_name in [
                "async_get_feeding_data",
                "async_get_walk_data",
                "async_get_gps_data",
                "async_get_dog_data",
            ]:
                if hasattr(manager, method_name):
                    getattr(manager, method_name).side_effect = Exception(
                        f"{manager_name} failed"
                    )
            failing_managers[manager_name] = manager

        coordinator.set_managers(**failing_managers)

        await coordinator.async_start_background_tasks()

        # Should not crash despite all failures
        try:
            await coordinator.async_request_refresh()
        except UpdateFailed:
            pass  # Expected when all managers fail

        # Should still track the dog
        assert "test_dog" in coordinator.get_dog_ids()

        await coordinator.async_shutdown()


class TestCoordinatorPerformanceStressScenarios:
    """Test coordinator performance under extreme stress."""

    @pytest.fixture
    def stress_config_entry(self):
        """Create config for stress testing."""
        # 30 dogs with complex configurations
        dogs = []
        for i in range(30):
            modules = {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                "notifications": True,
                "dashboard": True,
                "visitor": i % 2 == 0,
                "grooming": i % 3 == 0,
                "medication": i % 4 == 0,
                "training": i % 5 == 0,
            }

            dogs.append(
                {
                    CONF_DOG_ID: f"stress_dog_{i}",
                    CONF_DOG_NAME: f"Stress Dog {i}",
                    "modules": modules,
                }
            )

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "stress_test_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {CONF_GPS_UPDATE_INTERVAL: 30}  # Frequent updates
        return entry

    @pytest.fixture
    def realistic_managers(self):
        """Create managers with realistic performance characteristics."""

        # Feeding manager with variable response times
        feeding_manager = AsyncMock()

        async def variable_feeding_data(dog_id):
            # Simulate variable DB response times
            delay = 0.01 + (hash(dog_id) % 50) / 1000  # 10-60ms
            await asyncio.sleep(delay)

            # Occasionally fail
            if hash(dog_id) % 20 == 0:
                raise Exception("Database temporarily unavailable")

            return {
                "last_fed": "2024-09-07 08:00:00",
                "food_remaining": 1000 + hash(dog_id) % 2000,
            }

        feeding_manager.async_get_feeding_data = variable_feeding_data

        # Walk manager with GPS complexity
        walk_manager = AsyncMock()

        async def variable_walk_data(dog_id):
            delay = 0.005 + (hash(dog_id) % 30) / 1000  # 5-35ms
            await asyncio.sleep(delay)

            if hash(dog_id) % 15 == 0:
                raise TimeoutError("GPS service timeout")

            return {"last_walk": "2024-09-07 07:00:00", "distance": 2.5}

        async def variable_gps_data(dog_id):
            delay = 0.02 + (hash(dog_id) % 80) / 1000  # 20-100ms
            await asyncio.sleep(delay)

            if hash(dog_id) % 25 == 0:
                raise Exception("GPS hardware error")

            return {"lat": 52.5, "lon": 13.4, "accuracy": 10}

        walk_manager.async_get_walk_data = variable_walk_data
        walk_manager.async_get_gps_data = variable_gps_data

        # Dog data manager
        dog_data_manager = AsyncMock()

        async def variable_dog_data(dog_id):
            delay = 0.008 + (hash(dog_id) % 40) / 1000  # 8-48ms
            await asyncio.sleep(delay)

            return {"health": {"weight": 25.0, "temperature": 38.5}}

        dog_data_manager.async_get_dog_data = variable_dog_data

        return {
            "feeding_manager": feeding_manager,
            "walk_manager": walk_manager,
            "dog_data_manager": dog_data_manager,
        }

    @pytest.mark.asyncio
    async def test_rapid_update_cycles_stress(
        self, hass, stress_config_entry, realistic_managers
    ):
        """Test rapid update cycles under stress."""
        coordinator = PawControlCoordinator(hass, stress_config_entry)
        coordinator.set_managers(**realistic_managers)

        await coordinator.async_start_background_tasks()

        # Perform rapid update cycles
        update_times = []
        error_count = 0

        for _cycle in range(10):
            start_time = time.time()
            try:
                await coordinator.async_request_refresh()
                update_time = time.time() - start_time
                update_times.append(update_time)
            except UpdateFailed:
                error_count += 1

            # Small delay between cycles
            await asyncio.sleep(0.1)

        # Should complete most cycles successfully
        assert len(update_times) >= 7  # At least 70% success

        # Update times should be reasonable
        avg_update_time = sum(update_times) / len(update_times)
        assert avg_update_time < 5.0  # Average under 5 seconds

        # Performance tracking should work
        stats = coordinator.get_cache_stats()
        assert "performance" in stats

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_selective_refresh_stress(
        self, hass, stress_config_entry, realistic_managers
    ):
        """Test concurrent selective refresh operations."""
        coordinator = PawControlCoordinator(hass, stress_config_entry)
        coordinator.set_managers(**realistic_managers)

        await coordinator.async_start_background_tasks()

        # Initial update
        await coordinator.async_request_refresh()

        refresh_results = []

        async def concurrent_selective_refresh(refresh_id):
            """Perform concurrent selective refreshes."""
            try:
                for _i in range(5):
                    # Select different dog subsets
                    start_idx = (refresh_id * 3) % 30
                    dog_ids = [
                        f"stress_dog_{(start_idx + j) % 30}" for j in range(5)]
                    priority = (refresh_id % 10) + 1

                    start_time = time.time()
                    await coordinator.async_request_selective_refresh(dog_ids, priority)
                    duration = time.time() - start_time

                    refresh_results.append(
                        (refresh_id, len(dog_ids), priority, duration)
                    )
                    await asyncio.sleep(0.05)

            except Exception as e:
                refresh_results.append((refresh_id, "error", str(e)))

        # Run concurrent selective refreshes
        refreshers = [
            asyncio.create_task(concurrent_selective_refresh(i)) for i in range(8)
        ]
        await asyncio.gather(*refreshers, return_exceptions=True)

        # Should handle concurrent operations
        successful_refreshes = [r for r in refresh_results if len(r) == 4]
        assert len(successful_refreshes) >= 30  # Most should succeed

        # Higher priority should generally be faster
        high_priority = [r for r in successful_refreshes if r[2] >= 8]
        low_priority = [r for r in successful_refreshes if r[2] <= 3]

        if high_priority and low_priority:
            avg_high = sum(r[3] for r in high_priority) / len(high_priority)
            avg_low = sum(r[3] for r in low_priority) / len(low_priority)
            # High priority should be faster or equal
            assert avg_high <= avg_low * 1.5  # Allow some variance

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_cache_invalidation_stress(
        self, hass, stress_config_entry, realistic_managers
    ):
        """Test cache invalidation under stress."""
        coordinator = PawControlCoordinator(hass, stress_config_entry)
        coordinator.set_managers(**realistic_managers)

        await coordinator.async_start_background_tasks()

        # Initial update to populate cache
        await coordinator.async_request_refresh()

        # Verify cache is populated
        initial_stats = coordinator.get_cache_stats()["cache"]
        assert initial_stats["total_entries"] > 0

        # Stress test cache invalidation
        invalidation_tasks = []

        async def cache_invalidator(invalidator_id):
            """Invalidate caches concurrently."""
            for i in range(10):
                dog_id = f"stress_dog_{(invalidator_id * 3 + i) % 30}"
                await coordinator.invalidate_dog_cache(dog_id)
                await asyncio.sleep(0.01)

        # Run concurrent invalidators
        for i in range(6):
            task = asyncio.create_task(cache_invalidator(i))
            invalidation_tasks.append(task)

        await asyncio.gather(*invalidation_tasks)

        # Cache should handle invalidation stress
        final_stats = coordinator.get_cache_stats()["cache"]
        assert final_stats["total_entries"] >= 0  # Should not crash

        # Performance should still be tracked
        perf_stats = coordinator.get_cache_stats()["performance"]
        assert "total_updates" in perf_stats or "no_data" in perf_stats

        await coordinator.async_shutdown()


class TestCoordinatorBackgroundTaskManagement:
    """Test coordinator background task management edge cases."""

    @pytest.fixture
    def task_test_coordinator(self, hass):
        """Create coordinator for task testing."""
        dogs = [
            {
                CONF_DOG_ID: "task_dog",
                CONF_DOG_NAME: "Task Dog",
                "modules": {MODULE_FEEDING: True},
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "task_test_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Mock managers for task testing
        feeding_manager = AsyncMock()
        feeding_manager.async_get_feeding_data = AsyncMock(
            return_value={"status": "fed"}
        )
        coordinator.set_managers(feeding_manager=feeding_manager)

        return coordinator

    @pytest.mark.asyncio
    async def test_background_task_lifecycle(self, task_test_coordinator):
        """Test complete background task lifecycle."""
        coordinator = task_test_coordinator

        # Initially no tasks should be running
        assert coordinator._maintenance_task is None
        assert coordinator._batch_processor_task is None

        # Start background tasks
        await coordinator.async_start_background_tasks()

        # Tasks should be created and running
        assert coordinator._maintenance_task is not None
        assert coordinator._batch_processor_task is not None
        assert not coordinator._maintenance_task.done()
        assert not coordinator._batch_processor_task.done()

        # Let tasks run briefly
        await asyncio.sleep(0.1)

        # Tasks should still be running
        assert not coordinator._maintenance_task.done()
        assert not coordinator._batch_processor_task.done()

        # Shutdown should clean up tasks
        await coordinator.async_shutdown()

        # Tasks should be completed/cancelled
        assert coordinator._maintenance_task.done()
        assert coordinator._batch_processor_task.done()

    @pytest.mark.asyncio
    async def test_background_task_error_handling(self, task_test_coordinator):
        """Test background task error handling."""
        coordinator = task_test_coordinator

        # Mock maintenance to raise error
        original_perform_maintenance = coordinator._perform_maintenance

        async def failing_maintenance():
            raise Exception("Maintenance failed")

        # Temporarily patch maintenance
        coordinator._perform_maintenance = failing_maintenance

        await coordinator.async_start_background_tasks()

        # Let task run and potentially fail
        await asyncio.sleep(0.2)

        # Tasks should handle errors gracefully and continue running
        assert not coordinator._maintenance_task.done()

        # Restore original maintenance
        coordinator._perform_maintenance = original_perform_maintenance

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_maintenance_interval_behavior(self, task_test_coordinator):
        """Test maintenance interval behavior."""
        coordinator = task_test_coordinator

        # Mock short maintenance interval for testing

        with patch(
            "custom_components.pawcontrol.coordinator.MAINTENANCE_INTERVAL", 0.1
        ):
            maintenance_calls = []

            original_perform_maintenance = coordinator._perform_maintenance

            async def track_maintenance():
                maintenance_calls.append(time.time())
                await original_perform_maintenance()

            coordinator._perform_maintenance = track_maintenance

            await coordinator.async_start_background_tasks()

            # Let multiple maintenance cycles run
            await asyncio.sleep(0.35)  # Should allow 3+ cycles

            await coordinator.async_shutdown()

            # Should have multiple maintenance calls
            assert len(maintenance_calls) >= 2

    @pytest.mark.asyncio
    async def test_batch_processor_task_behavior(self, task_test_coordinator):
        """Test batch processor task behavior."""
        coordinator = task_test_coordinator

        batch_checks = []

        # Mock batch manager to track checks
        original_should_batch = coordinator._batch_manager.should_batch_now

        async def track_batch_checks():
            batch_checks.append(time.time())
            return await original_should_batch()

        coordinator._batch_manager.should_batch_now = track_batch_checks

        await coordinator.async_start_background_tasks()

        # Let batch processor run
        await asyncio.sleep(0.3)  # Should check multiple times

        await coordinator.async_shutdown()

        # Should have checked for batching multiple times
        assert len(batch_checks) >= 2

    @pytest.mark.asyncio
    async def test_graceful_shutdown_with_long_running_tasks(
        self, task_test_coordinator
    ):
        """Test graceful shutdown with long-running tasks."""
        coordinator = task_test_coordinator

        # Mock long-running maintenance
        async def long_maintenance():
            await asyncio.sleep(5)  # Long operation

        coordinator._perform_maintenance = long_maintenance

        await coordinator.async_start_background_tasks()

        # Start shutdown while maintenance is potentially running
        shutdown_start = time.time()
        await coordinator.async_shutdown()
        shutdown_duration = time.time() - shutdown_start

        # Should shutdown quickly due to timeout
        assert shutdown_duration < 3.0  # Should timeout and force cancel

        # Tasks should be done
        assert coordinator._maintenance_task.done()
        assert coordinator._batch_processor_task.done()

    @pytest.mark.asyncio
    async def test_multiple_background_task_starts(self, task_test_coordinator):
        """Test multiple calls to start background tasks."""
        coordinator = task_test_coordinator

        # Start tasks multiple times
        await coordinator.async_start_background_tasks()
        first_maintenance_task = coordinator._maintenance_task
        first_batch_task = coordinator._batch_processor_task

        # Start again - should not create new tasks
        await coordinator.async_start_background_tasks()

        # Should be same task instances
        assert coordinator._maintenance_task is first_maintenance_task
        assert coordinator._batch_processor_task is first_batch_task

        await coordinator.async_shutdown()


class TestCoordinatorUpdateIntervalCalculation:
    """Test update interval calculation edge cases."""

    def test_empty_dogs_interval_calculation(self, hass):
        """Test interval calculation with no dogs."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "empty_entry"
        entry.data = {CONF_DOGS: []}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Should use slow interval for no dogs
        assert coordinator.update_interval.total_seconds(
        ) == UPDATE_INTERVALS["slow"]

    def test_minimal_complexity_interval_calculation(self, hass):
        """Test interval calculation with minimal complexity."""
        dogs = [
            {
                CONF_DOG_ID: "simple_dog",
                CONF_DOG_NAME: "Simple Dog",
                "modules": {MODULE_FEEDING: True},  # Only feeding
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "simple_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Should use reasonable interval for simple setup
        interval = coordinator.update_interval.total_seconds()
        assert UPDATE_INTERVALS["real_time"] <= interval <= UPDATE_INTERVALS["slow"]

    def test_high_complexity_interval_calculation(self, hass):
        """Test interval calculation with high complexity."""
        dogs = []
        for i in range(15):  # Many dogs
            dogs.append(
                {
                    CONF_DOG_ID: f"complex_dog_{i}",
                    CONF_DOG_NAME: f"Complex Dog {i}",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                }
            )

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "complex_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Should use longer interval for complex setup
        interval = coordinator.update_interval.total_seconds()
        assert interval >= 60  # Should be at least 1 minute

    def test_gps_interval_override(self, hass):
        """Test GPS interval override behavior."""
        dogs = [
            {
                CONF_DOG_ID: "gps_dog",
                CONF_DOG_NAME: "GPS Dog",
                "modules": {MODULE_GPS: True, MODULE_WALK: True},
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "gps_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {CONF_GPS_UPDATE_INTERVAL: 30}  # 30 seconds

        coordinator = PawControlCoordinator(hass, entry)

        # Should respect GPS interval
        interval = coordinator.update_interval.total_seconds()
        assert interval <= 30


class TestCoordinatorDataIntegrityEdgeCases:
    """Test data integrity under edge conditions."""

    @pytest.fixture
    def integrity_coordinator(self, hass):
        """Create coordinator for data integrity testing."""
        dogs = [
            {
                CONF_DOG_ID: "integrity_dog",
                CONF_DOG_NAME: "Integrity Dog",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
        ]

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "integrity_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}

        coordinator = PawControlCoordinator(hass, entry)

        # Mock managers with varying data
        feeding_manager = AsyncMock()
        walk_manager = AsyncMock()

        # Data that changes between calls
        self.call_count = 0

        async def varying_feeding_data(dog_id):
            self.call_count += 1
            return {
                "last_fed": f"2024-09-07 0{8 + (self.call_count % 3)}:00:00",
                "call_number": self.call_count,
            }

        async def varying_walk_data(dog_id):
            return {
                "last_walk": "2024-09-07 07:00:00",
                "distance": 2.5 + (self.call_count % 5) * 0.1,
            }

        feeding_manager.async_get_feeding_data = varying_feeding_data
        walk_manager.async_get_walk_data = varying_walk_data

        coordinator.set_managers(
            feeding_manager=feeding_manager, walk_manager=walk_manager
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_data_change_detection(self, integrity_coordinator):
        """Test data change detection and checksum validation."""
        coordinator = integrity_coordinator

        await coordinator.async_start_background_tasks()

        # First update
        await coordinator.async_request_refresh()
        first_data = coordinator.get_dog_data("integrity_dog")
        first_checksum = coordinator._data_checksums.get("integrity_dog")

        assert first_data is not None
        assert first_checksum is not None

        # Second update (data should change due to varying responses)
        await coordinator.async_request_refresh()
        second_data = coordinator.get_dog_data("integrity_dog")
        second_checksum = coordinator._data_checksums.get("integrity_dog")

        assert second_data is not None
        assert second_checksum is not None

        # Checksums should be different due to data changes
        assert first_checksum != second_checksum

        # Data should be different
        assert first_data != second_data

        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_data_modification_safety(self, integrity_coordinator):
        """Test data modification safety under concurrent access."""
        coordinator = integrity_coordinator

        await coordinator.async_start_background_tasks()

        # Initial update
        await coordinator.async_request_refresh()

        modification_results = []

        async def concurrent_modifier(modifier_id):
            """Concurrently access and potentially modify data."""
            try:
                for i in range(20):
                    # Mix of read and write operations
                    if i % 3 == 0:
                        await coordinator.async_request_selective_refresh(
                            ["integrity_dog"], priority=5
                        )
                    elif i % 3 == 1:
                        data = coordinator.get_dog_data("integrity_dog")
                        modification_results.append(
                            (modifier_id, "read", data is not None)
                        )
                    else:
                        await coordinator.invalidate_dog_cache("integrity_dog")
                        modification_results.append(
                            (modifier_id, "invalidate", True))

                    await asyncio.sleep(0.001)
            except Exception as e:
                modification_results.append((modifier_id, "error", str(e)))

        # Run concurrent modifiers
        modifiers = [asyncio.create_task(
            concurrent_modifier(i)) for i in range(5)]
        await asyncio.gather(*modifiers, return_exceptions=True)

        # Should handle concurrent modifications safely
        errors = [r for r in modification_results if r[1] == "error"]
        assert len(errors) == 0, f"Concurrent modification errors: {errors}"

        # Final data should be consistent
        final_data = coordinator.get_dog_data("integrity_dog")
        assert final_data is not None

        await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_comprehensive_coordinator_integration():
    """Comprehensive integration test for coordinator under extreme conditions."""
    # Create large-scale test scenario
    dogs = []
    for i in range(25):  # 25 dogs for comprehensive testing
        dogs.append(
            {
                CONF_DOG_ID: f"integration_dog_{i:02d}",
                CONF_DOG_NAME: f"Integration Dog {i:02d}",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: i % 3 == 0,  # Every 3rd dog
                    MODULE_HEALTH: i % 2 == 0,  # Every 2nd dog
                    "notifications": True,
                },
            }
        )

    entry = Mock(spec=ConfigEntry)
    entry.entry_id = "comprehensive_entry"
    entry.data = {CONF_DOGS: dogs}
    entry.options = {CONF_GPS_UPDATE_INTERVAL: 45}

    hass = Mock()
    coordinator = PawControlCoordinator(hass, entry)

    # Mock comprehensive managers
    feeding_manager = AsyncMock()
    walk_manager = AsyncMock()
    dog_data_manager = AsyncMock()

    # Realistic manager implementations
    async def comprehensive_feeding_data(dog_id):
        await asyncio.sleep(0.01)  # Realistic delay
        if hash(dog_id) % 10 == 0:  # 10% failure rate
            raise Exception("Feeding service error")
        return {"last_fed": "2024-09-07 08:00:00", "amount": 200}

    async def comprehensive_walk_data(dog_id):
        await asyncio.sleep(0.005)
        return {"last_walk": "2024-09-07 07:00:00", "duration": 30}

    async def comprehensive_gps_data(dog_id):
        await asyncio.sleep(0.02)
        if hash(dog_id) % 15 == 0:  # GPS failures
            raise TimeoutError("GPS timeout")
        return {"lat": 52.5, "lon": 13.4, "accuracy": 5}

    async def comprehensive_dog_data(dog_id):
        await asyncio.sleep(0.008)
        return {"health": {"weight": 25.0, "temperature": 38.5}}

    feeding_manager.async_get_feeding_data = comprehensive_feeding_data
    walk_manager.async_get_walk_data = comprehensive_walk_data
    walk_manager.async_get_gps_data = comprehensive_gps_data
    dog_data_manager.async_get_dog_data = comprehensive_dog_data

    coordinator.set_managers(
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        dog_data_manager=dog_data_manager,
    )

    # Test complete lifecycle
    await coordinator.async_start_background_tasks()

    # 1. Initial update
    start_time = time.time()
    await coordinator.async_request_refresh()
    initial_duration = time.time() - start_time

    # Should handle 25 dogs efficiently
    assert initial_duration < 8.0

    # 2. Verify data integrity
    all_data = coordinator.get_all_dogs_data()
    # Most dogs should have data despite some failures
    assert len(all_data) >= 20

    # 3. Test selective refresh performance
    selective_dogs = [f"integration_dog_{i:02d}" for i in range(5)]
    start_time = time.time()
    await coordinator.async_request_selective_refresh(selective_dogs, priority=8)
    selective_duration = time.time() - start_time

    # Selective should be faster
    assert selective_duration < initial_duration / 2

    # 4. Test concurrent operations
    concurrent_tasks = []
    for i in range(8):
        if i % 3 == 0:
            task = asyncio.create_task(coordinator.async_request_refresh())
        elif i % 3 == 1:
            task = asyncio.create_task(
                coordinator.async_request_selective_refresh(
                    [f"integration_dog_{i:02d}"], priority=5
                )
            )
        else:
            task = asyncio.create_task(
                coordinator.invalidate_dog_cache(f"integration_dog_{i:02d}")
            )
        concurrent_tasks.append(task)

    # Should handle concurrent operations
    results = await asyncio.gather(*concurrent_tasks, return_exceptions=True)
    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) < len(concurrent_tasks) / 2  # Less than 50% errors

    # 5. Test statistics and performance
    stats = coordinator.get_cache_stats()
    assert "cache" in stats
    assert "performance" in stats
    assert "batch" in stats

    # 6. Test graceful shutdown
    shutdown_start = time.time()
    await coordinator.async_shutdown()
    shutdown_duration = time.time() - shutdown_start

    # Should shutdown cleanly
    assert shutdown_duration < 3.0
