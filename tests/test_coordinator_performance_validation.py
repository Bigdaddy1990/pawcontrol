"""Comprehensive coordinator performance validation for PawControl.

Tests coordinator performance under high entity loads (500+ entities),
memory efficiency, batch processing optimization, cache performance,
and concurrent access patterns for Gold Standard compliance.

Test Areas:
- High entity load performance (500+ entities, 50+ dogs)
- Update cycle optimization and timing
- Memory usage and cache efficiency
- Batch processing performance
- Concurrent access and thread safety
- Background task performance
- Selective refresh efficiency
- Performance monitoring integration
- Manager delegation performance
- Resource cleanup and memory leaks
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Dict
from typing import List
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_GPS
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.coordinator import MAINTENANCE_INTERVAL
from custom_components.pawcontrol.coordinator import PawControlCoordinator


class TestHighEntityLoadPerformance:
    """Test coordinator performance under high entity loads."""

    @pytest.fixture
    async def large_scale_coordinator(
        self, hass: HomeAssistant
    ) -> PawControlCoordinator:
        """Create coordinator with large number of dogs (50+) for testing."""
        # Generate 50 dogs with all modules enabled
        dogs_config = []
        for i in range(50):
            dog_config = {
                CONF_DOG_ID: f"test_dog_{i:02d}",
                "name": f"Dog {i:02d}",
                "breed": "Test Breed",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
                "feeding": {
                    "meals_per_day": 2,
                    "food_types": ["dry", "wet"],
                    "portion_calculator": "weight_based",
                },
                "gps": {
                    "device_id": f"gps_device_{i:02d}",
                    "update_interval": 30,
                },
            }
            dogs_config.append(dog_config)

        # Create config entry
        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        # Create coordinator
        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock managers with realistic behavior
        mock_data_manager = AsyncMock()
        mock_dog_data_manager = AsyncMock()
        mock_walk_manager = AsyncMock()
        mock_feeding_manager = AsyncMock()
        mock_health_calculator = AsyncMock()

        # Configure manager mocks to return realistic data
        mock_feeding_manager.async_get_feeding_data.return_value = {
            "next_feeding": "2025-09-08T12:00:00Z",
            "last_feeding": "2025-09-08T08:00:00Z",
            "daily_portions": 2,
            "food_consumed": 500,  # grams
        }

        mock_walk_manager.async_get_walk_data.return_value = {
            "last_walk": "2025-09-08T10:00:00Z",
            "walk_duration": 1800,  # 30 minutes
            "distance": 2.5,  # km
            "steps": 3500,
        }

        mock_walk_manager.async_get_gps_data.return_value = {
            "latitude": 51.5074,
            "longitude": -0.1278,
            "accuracy": 5.0,
            "battery_level": 85,
            "last_update": "2025-09-08T11:30:00Z",
        }

        mock_dog_data_manager.async_get_dog_data.return_value = {
            "health": {
                "weight": 25.5,
                "temperature": 38.5,
                "heart_rate": 100,
                "last_checkup": "2025-08-01T00:00:00Z",
                "vaccinations": ["rabies", "dhpp"],
            }
        }

        coordinator.set_managers(
            data_manager=mock_data_manager,
            dog_data_manager=mock_dog_data_manager,
            walk_manager=mock_walk_manager,
            feeding_manager=mock_feeding_manager,
            health_calculator=mock_health_calculator,
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_high_entity_load_update_performance(
        self, large_scale_coordinator: PawControlCoordinator
    ):
        """Test update performance with 500+ entities (50 dogs × 10+ entities each)."""
        start_time = time.time()

        # Perform initial update
        await large_scale_coordinator.async_refresh()

        initial_update_time = time.time() - start_time

        # Verify all dogs were processed
        all_data = large_scale_coordinator.get_all_dogs_data()
        assert len(all_data) == 50  # All 50 dogs should have data

        # Verify data structure for each dog
        for i in range(50):
            dog_id = f"test_dog_{i:02d}"
            assert dog_id in all_data
            dog_data = all_data[dog_id]

            # Each dog should have all module data
            assert "dog_info" in dog_data
            assert MODULE_FEEDING in dog_data
            assert MODULE_WALK in dog_data
            assert MODULE_GPS in dog_data
            assert MODULE_HEALTH in dog_data

        # Performance assertions
        # Initial update should complete within reasonable time (< 5 seconds)
        assert initial_update_time < 5.0, (
            f"Initial update took {initial_update_time:.2f}s"
        )

        # Test subsequent updates (should be faster due to caching)
        start_time = time.time()
        await large_scale_coordinator.async_refresh()
        cached_update_time = time.time() - start_time

        # Cached updates should be significantly faster
        assert cached_update_time < initial_update_time / 2

        # Get performance statistics
        stats = large_scale_coordinator.get_cache_stats()
        assert stats["cache"]["hit_rate"] > 0  # Should have cache hits

    @pytest.mark.asyncio
    async def test_memory_usage_under_high_load(
        self, large_scale_coordinator: PawControlCoordinator
    ):
        """Test memory usage patterns under high entity load."""
        # Perform multiple update cycles to stress memory
        memory_stats = []

        for cycle in range(10):
            # Force full refresh
            await large_scale_coordinator.async_refresh()

            # Get memory-related statistics
            cache_stats = large_scale_coordinator.get_cache_stats()
            memory_stats.append(
                {
                    "cycle": cycle,
                    "cache_entries": cache_stats["cache"]["total_entries"],
                    "hit_rate": cache_stats["cache"]["hit_rate"],
                    "dogs_tracked": cache_stats["dogs_tracked"],
                }
            )

            # Simulate some time passing
            await asyncio.sleep(0.1)

        # Verify memory usage is stable
        final_entries = memory_stats[-1]["cache_entries"]
        initial_entries = memory_stats[0]["cache_entries"]

        # Cache should stabilize and not grow indefinitely
        assert final_entries <= initial_entries * 1.5  # Max 50% growth

        # Hit rate should improve over time
        final_hit_rate = memory_stats[-1]["hit_rate"]
        initial_hit_rate = memory_stats[0]["hit_rate"]
        assert final_hit_rate >= initial_hit_rate  # Should not degrade

    @pytest.mark.asyncio
    async def test_batch_processing_efficiency_high_load(
        self, large_scale_coordinator: PawControlCoordinator
    ):
        """Test batch processing efficiency with large numbers of dogs."""
        # Add multiple dogs to batch with different priorities
        dog_ids = [f"test_dog_{i:02d}" for i in range(50)]

        # Request selective refresh for all dogs with varying priorities
        high_priority_dogs = dog_ids[:10]  # First 10 dogs
        medium_priority_dogs = dog_ids[10:30]  # Next 20 dogs
        low_priority_dogs = dog_ids[30:]  # Remaining 20 dogs

        start_time = time.time()

        # Add dogs to batch processing queue
        await large_scale_coordinator.async_request_selective_refresh(
            high_priority_dogs, priority=9
        )
        await large_scale_coordinator.async_request_selective_refresh(
            medium_priority_dogs, priority=5
        )
        await large_scale_coordinator.async_request_selective_refresh(
            low_priority_dogs, priority=2
        )

        # High priority should trigger immediate refresh
        batch_processing_time = time.time() - start_time

        # Verify all dogs were processed
        all_data = large_scale_coordinator.get_all_dogs_data()
        processed_count = len(all_data)

        # Should process significant number of dogs efficiently
        assert processed_count >= 40  # At least 80% of dogs
        assert batch_processing_time < 3.0  # Should be fast with batching

        # Verify batch statistics
        batch_stats = large_scale_coordinator.get_cache_stats()["batch"]
        assert "total_processed" in batch_stats or "pending_count" in batch_stats

    @pytest.mark.asyncio
    async def test_concurrent_access_high_load(
        self, large_scale_coordinator: PawControlCoordinator
    ):
        """Test concurrent access patterns under high load."""

        # Define concurrent access patterns
        async def access_pattern_1():
            """Pattern 1: Frequent data requests."""
            access_count = 0
            for _ in range(50):
                dog_id = f"test_dog_{_ % 50:02d}"
                data = large_scale_coordinator.get_dog_data(dog_id)
                if data:
                    access_count += 1
                await asyncio.sleep(0.01)  # 10ms delay
            return access_count

        async def access_pattern_2():
            """Pattern 2: Cache invalidation requests."""
            invalidation_count = 0
            for i in range(25):
                dog_id = f"test_dog_{i:02d}"
                await large_scale_coordinator.invalidate_dog_cache(dog_id)
                invalidation_count += 1
                await asyncio.sleep(0.02)  # 20ms delay
            return invalidation_count

        async def access_pattern_3():
            """Pattern 3: Selective refresh requests."""
            refresh_count = 0
            for batch_start in range(0, 50, 10):
                batch_dogs = [
                    f"test_dog_{i:02d}"
                    for i in range(batch_start, min(batch_start + 10, 50))
                ]
                await large_scale_coordinator.async_request_selective_refresh(
                    batch_dogs, priority=6
                )
                refresh_count += len(batch_dogs)
                await asyncio.sleep(0.05)  # 50ms delay
            return refresh_count

        # Run concurrent access patterns
        start_time = time.time()
        results = await asyncio.gather(
            access_pattern_1(),
            access_pattern_2(),
            access_pattern_3(),
            return_exceptions=True,
        )
        concurrent_access_time = time.time() - start_time

        # Verify all patterns completed successfully
        access_count, invalidation_count, refresh_count = results
        assert isinstance(access_count, int) and access_count > 30
        assert isinstance(invalidation_count, int) and invalidation_count == 25
        assert isinstance(refresh_count, int) and refresh_count == 50

        # Performance should remain reasonable under concurrent load
        assert concurrent_access_time < 10.0

        # Coordinator should remain functional
        stats = large_scale_coordinator.get_update_statistics()
        assert stats["total_dogs"] == 50


class TestUpdateCycleOptimization:
    """Test update cycle optimization and timing."""

    @pytest.fixture
    async def optimization_coordinator(
        self, hass: HomeAssistant
    ) -> PawControlCoordinator:
        """Create coordinator for optimization testing."""
        # Create 30 dogs with mixed module configurations
        dogs_config = []
        for i in range(30):
            # Vary module configurations to test optimization
            modules = {
                MODULE_FEEDING: i % 3 == 0,  # Every 3rd dog
                MODULE_WALK: i % 2 == 0,  # Every 2nd dog
                MODULE_GPS: i % 4 == 0,  # Every 4th dog
                MODULE_HEALTH: i % 5 == 0,  # Every 5th dog
            }

            dog_config = {
                CONF_DOG_ID: f"opt_dog_{i:02d}",
                "name": f"Optimization Dog {i:02d}",
                "modules": modules,
            }
            dogs_config.append(dog_config)

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock managers with different response times
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()

        async def slow_feeding_data(dog_id):
            await asyncio.sleep(0.05)  # 50ms delay
            return {"status": "fed", "next_meal": "2025-09-08T15:00:00Z"}

        async def fast_walk_data(dog_id):
            await asyncio.sleep(0.01)  # 10ms delay
            return {"status": "walked", "distance": 1.5}

        mock_feeding_manager.async_get_feeding_data.side_effect = slow_feeding_data
        mock_walk_manager.async_get_walk_data.side_effect = fast_walk_data
        mock_walk_manager.async_get_gps_data.return_value = {
            "lat": 0, "lon": 0}

        coordinator.set_managers(
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_selective_update_optimization(
        self, optimization_coordinator: PawControlCoordinator
    ):
        """Test selective update optimization reduces unnecessary work."""
        # Perform full update to establish baseline
        start_time = time.time()
        await optimization_coordinator.async_refresh()
        full_update_time = time.time() - start_time

        # Get initial data checksums
        initial_stats = optimization_coordinator.get_cache_stats()
        initial_stats["dogs_tracked"]

        # Perform selective update (should be faster)
        selective_dogs = ["opt_dog_00", "opt_dog_05", "opt_dog_10"]
        start_time = time.time()
        await optimization_coordinator.async_request_selective_refresh(
            selective_dogs, priority=8
        )
        selective_update_time = time.time() - start_time

        # Selective updates should be significantly faster
        assert selective_update_time < full_update_time / 3

        # Verify only requested dogs were updated (cache invalidation)
        for dog_id in selective_dogs:
            data = optimization_coordinator.get_dog_data(dog_id)
            assert data is not None

        # Statistics should reflect optimization
        final_stats = optimization_coordinator.get_cache_stats()
        # Should have cache activity
        assert final_stats["cache"]["hit_rate"] >= 0

    @pytest.mark.asyncio
    async def test_update_interval_optimization(
        self, optimization_coordinator: PawControlCoordinator
    ):
        """Test update interval optimization based on module complexity."""
        # Get calculated update interval
        interval = optimization_coordinator.update_interval.total_seconds()

        # Should have reasonable interval for mixed module configuration
        assert 30 <= interval <= 120  # Between 30s and 2 minutes

        # Test with all GPS-enabled dogs (should have faster interval)
        for dog in optimization_coordinator.dogs:
            dog["modules"][MODULE_GPS] = True

        # Recalculate optimal interval
        new_interval = optimization_coordinator._calculate_optimal_update_interval()
        assert new_interval <= interval  # Should be faster with more GPS

    @pytest.mark.asyncio
    async def test_change_detection_optimization(
        self, optimization_coordinator: PawControlCoordinator
    ):
        """Test change detection prevents unnecessary updates."""
        # Perform initial update
        await optimization_coordinator.async_refresh()
        initial_checksums = optimization_coordinator._data_checksums.copy()

        # Mock managers to return identical data
        optimization_coordinator.feeding_manager.async_get_feeding_data.return_value = {
            "status": "fed",
            "next_meal": "2025-09-08T15:00:00Z",
        }

        # Perform update with identical data
        start_time = time.time()
        await optimization_coordinator.async_refresh()
        no_change_update_time = time.time() - start_time

        # Should be fast due to change detection
        assert no_change_update_time < 0.5

        # Checksums should remain the same
        final_checksums = optimization_coordinator._data_checksums
        unchanged_count = sum(
            1
            for dog_id in initial_checksums
            if initial_checksums.get(dog_id) == final_checksums.get(dog_id)
        )

        # Most dogs should have unchanged checksums
        assert unchanged_count >= len(initial_checksums) * 0.8


class TestBackgroundTaskPerformance:
    """Test background task performance and efficiency."""

    @pytest.fixture
    async def background_task_coordinator(
        self, hass: HomeAssistant
    ) -> PawControlCoordinator:
        """Create coordinator for background task testing."""
        dogs_config = [
            {
                CONF_DOG_ID: f"bg_dog_{i:02d}",
                "name": f"Background Dog {i:02d}",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
            for i in range(20)
        ]

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock managers
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()
        mock_feeding_manager.async_get_feeding_data.return_value = {
            "status": "ok"}
        mock_walk_manager.async_get_walk_data.return_value = {"status": "ok"}

        coordinator.set_managers(
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
        )

        return coordinator

    @pytest.mark.asyncio
    async def test_maintenance_task_performance(
        self, background_task_coordinator: PawControlCoordinator
    ):
        """Test maintenance task performance and efficiency."""
        # Start background tasks
        await background_task_coordinator.async_start_background_tasks()

        # Add data to cache to create maintenance work
        for i in range(50):
            await background_task_coordinator._cache_manager.set(
                f"maintenance_test_{i}",
                {"test": i},
                ttl_seconds=1,  # Short TTL for testing
            )

        # Wait for entries to expire
        await asyncio.sleep(1.2)

        # Trigger maintenance manually to test performance
        start_time = time.time()
        await background_task_coordinator._perform_maintenance()
        maintenance_time = time.time() - start_time

        # Maintenance should be fast
        assert maintenance_time < 0.5

        # Verify expired entries were cleared
        stats = background_task_coordinator._cache_manager.get_stats()
        assert stats["total_entries"] < 50  # Some entries should be cleared

        # Cleanup
        await background_task_coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_batch_processor_performance(
        self, background_task_coordinator: PawControlCoordinator
    ):
        """Test batch processor performance."""
        # Start background tasks
        await background_task_coordinator.async_start_background_tasks()

        # Add items to batch processing queue
        dog_ids = [f"bg_dog_{i:02d}" for i in range(20)]

        start_time = time.time()

        # Add dogs to processing queue
        for dog_id in dog_ids:
            await background_task_coordinator._batch_manager.add_to_batch(
                dog_id, priority=5
            )

        # Wait for batch processing
        await asyncio.sleep(0.2)

        batch_processing_time = time.time() - start_time

        # Should process efficiently
        assert batch_processing_time < 1.0

        # Verify batch statistics
        batch_stats = background_task_coordinator._batch_manager.get_stats()
        assert isinstance(batch_stats, dict)

        # Cleanup
        await background_task_coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_background_task_resource_usage(
        self, background_task_coordinator: PawControlCoordinator
    ):
        """Test background task resource usage patterns."""
        # Start background tasks
        await background_task_coordinator.async_start_background_tasks()

        # Monitor resource usage over time
        resource_measurements = []

        for measurement in range(5):
            # Get current statistics
            stats = background_task_coordinator.get_cache_stats()
            resource_measurements.append(
                {
                    "measurement": measurement,
                    "cache_entries": stats["cache"]["total_entries"],
                    "cache_hits": stats["cache"]["cache_hits"],
                    "dogs_tracked": stats["dogs_tracked"],
                }
            )

            # Simulate some activity
            await background_task_coordinator.async_refresh()
            await asyncio.sleep(0.1)

        # Verify resource usage is reasonable
        final_measurement = resource_measurements[-1]
        # Reasonable cache size
        assert final_measurement["cache_entries"] < 100
        assert final_measurement["dogs_tracked"] == 20  # All dogs tracked

        # Cleanup
        await background_task_coordinator.async_shutdown()


class TestPerformanceMonitoringIntegration:
    """Test performance monitoring integration."""

    @pytest.fixture
    async def monitored_coordinator(self, hass: HomeAssistant) -> PawControlCoordinator:
        """Create coordinator with performance monitoring."""
        dogs_config = [
            {
                CONF_DOG_ID: f"perf_dog_{i:02d}",
                "name": f"Performance Dog {i:02d}",
                "modules": {MODULE_FEEDING: True},
            }
            for i in range(15)
        ]

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock manager with variable performance
        mock_feeding_manager = AsyncMock()

        async def variable_performance_feeding(dog_id):
            # Simulate variable response times
            if "05" in dog_id:
                await asyncio.sleep(0.1)  # Slow response
            else:
                await asyncio.sleep(0.01)  # Fast response
            return {"status": "fed"}

        mock_feeding_manager.async_get_feeding_data.side_effect = (
            variable_performance_feeding
        )

        coordinator.set_managers(feeding_manager=mock_feeding_manager)
        return coordinator

    @pytest.mark.asyncio
    async def test_performance_metrics_collection(
        self, monitored_coordinator: PawControlCoordinator
    ):
        """Test performance metrics collection and reporting."""
        # Perform multiple updates to generate metrics
        for _ in range(5):
            await monitored_coordinator.async_refresh()
            await asyncio.sleep(0.1)

        # Get performance statistics
        perf_stats = monitored_coordinator._performance_monitor.get_stats()

        # Verify metrics are collected
        assert "updates_count" in perf_stats or "total_updates" in perf_stats
        assert "average_duration" in perf_stats or "avg_duration" in perf_stats

        # Get comprehensive statistics
        all_stats = monitored_coordinator.get_cache_stats()
        assert "performance" in all_stats
        assert "cache" in all_stats

    @pytest.mark.asyncio
    async def test_performance_alerting_under_load(
        self, monitored_coordinator: PawControlCoordinator
    ):
        """Test performance alerting mechanisms under load."""
        # Simulate performance degradation
        with patch.object(
            monitored_coordinator.feeding_manager,
            "async_get_feeding_data",
            side_effect=AsyncMock(side_effect=lambda x: asyncio.sleep(0.2)),
        ):
            start_time = time.time()

            try:
                await monitored_coordinator.async_refresh()
            except UpdateFailed:
                # Expected due to slow performance
                pass

            slow_update_time = time.time() - start_time

        # Should detect performance issues
        assert slow_update_time > 0.15  # Should be slow

        # Performance monitor should record the issue
        perf_stats = monitored_coordinator._performance_monitor.get_stats()
        assert isinstance(perf_stats, dict)

    @pytest.mark.asyncio
    async def test_performance_optimization_feedback(
        self, monitored_coordinator: PawControlCoordinator
    ):
        """Test performance optimization based on monitoring feedback."""
        # Perform baseline updates
        baseline_times = []
        for _ in range(3):
            start_time = time.time()
            await monitored_coordinator.async_refresh()
            baseline_times.append(time.time() - start_time)

        # Get performance statistics
        stats = monitored_coordinator.get_cache_stats()
        initial_hit_rate = stats["cache"]["hit_rate"]

        # Perform more updates (should improve cache performance)
        for _ in range(5):
            await monitored_coordinator.async_refresh()

        # Get updated statistics
        final_stats = monitored_coordinator.get_cache_stats()
        final_hit_rate = final_stats["cache"]["hit_rate"]

        # Cache performance should improve
        assert final_hit_rate >= initial_hit_rate


class TestResourceCleanupAndMemoryLeaks:
    """Test resource cleanup and memory leak prevention."""

    @pytest.mark.asyncio
    async def test_coordinator_lifecycle_cleanup(self, hass: HomeAssistant):
        """Test complete coordinator lifecycle and cleanup."""
        # Create multiple coordinators to test cleanup
        coordinators = []

        for coord_id in range(5):
            dogs_config = [
                {
                    CONF_DOG_ID: f"cleanup_dog_{coord_id}_{i}",
                    "name": f"Cleanup Dog {i}",
                    "modules": {MODULE_FEEDING: True},
                }
                for i in range(10)
            ]

            config_entry = MagicMock(spec=ConfigEntry)
            config_entry.data = {CONF_DOGS: dogs_config}
            config_entry.options = {}

            coordinator = PawControlCoordinator(hass, config_entry)

            # Mock manager
            mock_feeding_manager = AsyncMock()
            mock_feeding_manager.async_get_feeding_data.return_value = {
                "status": "ok"}
            coordinator.set_managers(feeding_manager=mock_feeding_manager)

            coordinators.append(coordinator)

        # Start all coordinators
        for coordinator in coordinators:
            await coordinator.async_start_background_tasks()
            await coordinator.async_refresh()

        # Verify all are running
        for coordinator in coordinators:
            assert coordinator.available
            stats = coordinator.get_cache_stats()
            assert stats["dogs_tracked"] == 10

        # Shutdown all coordinators
        for coordinator in coordinators:
            await coordinator.async_shutdown()

        # Verify cleanup
        for coordinator in coordinators:
            assert len(coordinator._data) == 0
            assert len(coordinator._data_checksums) == 0
            assert len(coordinator._last_successful_update) == 0

    @pytest.mark.asyncio
    async def test_memory_leak_detection_over_time(self, hass: HomeAssistant):
        """Test memory leak detection over extended operation."""
        dogs_config = [
            {
                CONF_DOG_ID: f"leak_test_dog_{i:02d}",
                "name": f"Leak Test Dog {i:02d}",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
            for i in range(25)
        ]

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock managers
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()
        mock_feeding_manager.async_get_feeding_data.return_value = {
            "status": "ok"}
        mock_walk_manager.async_get_walk_data.return_value = {"status": "ok"}

        coordinator.set_managers(
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
        )

        # Track memory usage over multiple cycles
        memory_snapshots = []

        for cycle in range(20):
            # Perform operations
            await coordinator.async_refresh()

            # Request selective refreshes
            dog_subset = [
                f"leak_test_dog_{i:02d}" for i in range(cycle % 5, 25, 5)]
            await coordinator.async_request_selective_refresh(dog_subset, priority=7)

            # Invalidate some caches
            for i in range(3):
                await coordinator.invalidate_dog_cache(f"leak_test_dog_{i:02d}")

            # Take memory snapshot
            stats = coordinator.get_cache_stats()
            memory_snapshots.append(
                {
                    "cycle": cycle,
                    "cache_entries": stats["cache"]["total_entries"],
                    "dogs_tracked": stats["dogs_tracked"],
                    "cache_hits": stats["cache"]["cache_hits"],
                    "cache_misses": stats["cache"]["cache_misses"],
                }
            )

            # Small delay
            await asyncio.sleep(0.05)

        # Analyze for memory leaks
        # Cache entries should not grow indefinitely
        max_cache_entries = max(snap["cache_entries"]
                                for snap in memory_snapshots)
        min_cache_entries = min(snap["cache_entries"]
                                for snap in memory_snapshots)

        # Should not have unbounded growth
        assert max_cache_entries < min_cache_entries * 3  # Max 3x growth

        # Dogs tracked should remain stable
        dogs_tracked_values = [snap["dogs_tracked"]
                               for snap in memory_snapshots[-5:]]
        # Should remain constant
        assert all(val == 25 for val in dogs_tracked_values)

        # Cleanup
        await coordinator.async_shutdown()

        # Verify complete cleanup
        final_stats = coordinator.get_cache_stats()
        assert final_stats["cache"]["total_entries"] == 0
        assert final_stats["dogs_tracked"] == 0


class TestStressTestingAndEdgeCases:
    """Test stress scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_extreme_concurrent_load(self, hass: HomeAssistant):
        """Test coordinator under extreme concurrent load."""
        # Create large coordinator
        dogs_config = [
            {
                CONF_DOG_ID: f"stress_dog_{i:03d}",
                "name": f"Stress Dog {i:03d}",
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
            for i in range(100)  # 100 dogs for stress testing
        ]

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock managers with realistic delays
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()

        async def feeding_with_delay(dog_id):
            await asyncio.sleep(0.01)  # 10ms delay
            return {"status": "fed", "dog_id": dog_id}

        async def walk_with_delay(dog_id):
            await asyncio.sleep(0.015)  # 15ms delay
            return {"status": "walked", "dog_id": dog_id}

        mock_feeding_manager.async_get_feeding_data.side_effect = feeding_with_delay
        mock_walk_manager.async_get_walk_data.side_effect = walk_with_delay

        coordinator.set_managers(
            feeding_manager=mock_feeding_manager,
            walk_manager=mock_walk_manager,
        )

        # Define stress test patterns
        async def stress_pattern_1():
            """Continuous refresh requests."""
            for _ in range(20):
                await coordinator.async_refresh()
                await asyncio.sleep(0.05)
            return "refresh_completed"

        async def stress_pattern_2():
            """Rapid selective refresh requests."""
            for batch in range(10):
                dog_subset = [
                    f"stress_dog_{i:03d}" for i in range(batch * 10, (batch + 1) * 10)
                ]
                await coordinator.async_request_selective_refresh(
                    dog_subset, priority=8
                )
                await asyncio.sleep(0.02)
            return "selective_completed"

        async def stress_pattern_3():
            """Cache invalidation stress."""
            for i in range(50):
                await coordinator.invalidate_dog_cache(f"stress_dog_{i:03d}")
                await asyncio.sleep(0.01)
            return "invalidation_completed"

        # Run all stress patterns concurrently
        start_time = time.time()
        results = await asyncio.gather(
            stress_pattern_1(),
            stress_pattern_2(),
            stress_pattern_3(),
            return_exceptions=True,
        )
        stress_test_duration = time.time() - start_time

        # All patterns should complete successfully
        assert all(isinstance(result, str) for result in results)

        # Should complete within reasonable time even under extreme load
        assert stress_test_duration < 15.0  # Max 15 seconds

        # Coordinator should remain functional
        final_stats = coordinator.get_update_statistics()
        assert final_stats["total_dogs"] == 100

        # Cache should still be functional
        cache_stats = coordinator.get_cache_stats()
        assert cache_stats["cache"]["total_entries"] > 0

        # Cleanup
        await coordinator.async_shutdown()

    @pytest.mark.asyncio
    async def test_error_handling_under_load(self, hass: HomeAssistant):
        """Test error handling under high load conditions."""
        dogs_config = [
            {
                CONF_DOG_ID: f"error_dog_{i:02d}",
                "name": f"Error Dog {i:02d}",
                "modules": {MODULE_FEEDING: True},
            }
            for i in range(30)
        ]

        config_entry = MagicMock(spec=ConfigEntry)
        config_entry.data = {CONF_DOGS: dogs_config}
        config_entry.options = {}

        coordinator = PawControlCoordinator(hass, config_entry)

        # Mock manager with intermittent failures
        mock_feeding_manager = AsyncMock()

        async def unreliable_feeding_data(dog_id):
            # Simulate intermittent failures
            if "error_dog_05" in dog_id or "error_dog_15" in dog_id:
                raise Exception(f"Simulated failure for {dog_id}")
            await asyncio.sleep(0.01)
            return {"status": "fed", "dog_id": dog_id}

        mock_feeding_manager.async_get_feeding_data.side_effect = (
            unreliable_feeding_data
        )

        coordinator.set_managers(feeding_manager=mock_feeding_manager)

        # Test error handling during high load
        successful_updates = 0
        failed_updates = 0

        for update_cycle in range(10):
            try:
                await coordinator.async_refresh()
                successful_updates += 1
            except UpdateFailed:
                failed_updates += 1

            # Continue with selective refreshes even after failures
            try:
                dog_subset = [f"error_dog_{i:02d}" for i in range(
                    update_cycle, 30, 10)]
                await coordinator.async_request_selective_refresh(
                    dog_subset, priority=6
                )
            except Exception:
                pass  # Continue despite errors

        # Should have some successful updates despite errors
        assert successful_updates > 0

        # Should continue functioning despite failures
        stats = coordinator.get_update_statistics()
        assert stats["total_dogs"] == 30

        # Cleanup
        await coordinator.async_shutdown()


if __name__ == "__main__":
    pytest.main([__file__])
