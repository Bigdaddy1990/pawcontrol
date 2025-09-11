"""Performance benchmark tests for refactored coordinator architecture.

Validates that specialized managers improve performance and don't introduce regressions.
"""

import asyncio
import time
from statistics import mean, stdev
from unittest.mock import AsyncMock, Mock

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestCoordinatorPerformanceBenchmark:
    """Performance benchmarks for refactored coordinator."""

    @pytest.fixture
    def small_config(self):
        """Config with 1 dog for baseline testing."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "small_test"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog_1",
                    CONF_DOG_NAME: "Dog 1",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
            ]
        }
        entry.options = {}
        return entry

    @pytest.fixture
    def medium_config(self):
        """Config with 5 dogs for medium load testing."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "medium_test"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
                for i in range(1, 6)
            ]
        }
        entry.options = {}
        return entry

    @pytest.fixture
    def large_config(self):
        """Config with 20 dogs for stress testing."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "large_test"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
                for i in range(1, 21)
            ]
        }
        entry.options = {}
        return entry

    def create_fast_mock_managers(self):
        """Create mock managers with fast responses (10ms)."""
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()
        mock_dog_data_manager = AsyncMock()

        async def fast_feeding_response(dog_id):
            await asyncio.sleep(0.01)  # 10ms simulated work
            return {
                "last_feeding": "2025-01-15T10:00:00",
                "meals_today": 2,
                "health_aware_portion": 250.0,
            }

        async def fast_walk_response(dog_id):
            await asyncio.sleep(0.01)  # 10ms simulated work
            return {
                "walk_in_progress": False,
                "walks_today": 1,
            }

        async def fast_gps_response(dog_id):
            await asyncio.sleep(0.01)  # 10ms simulated work
            return {
                "latitude": 52.5200,
                "longitude": 13.4050,
                "available": True,
            }

        async def fast_health_response(dog_id):
            await asyncio.sleep(0.01)  # 10ms simulated work
            return {
                "health": {
                    "current_weight": 25.0,
                    "health_status": "good",
                }
            }

        mock_feeding_manager.async_get_feeding_data.side_effect = fast_feeding_response
        mock_walk_manager.async_get_walk_data.side_effect = fast_walk_response
        mock_walk_manager.async_get_gps_data.side_effect = fast_gps_response
        mock_dog_data_manager.async_get_dog_data.side_effect = fast_health_response

        return {
            "feeding_manager": mock_feeding_manager,
            "walk_manager": mock_walk_manager,
            "dog_data_manager": mock_dog_data_manager,
            "data_manager": AsyncMock(),
            "health_calculator": Mock(),
        }

    def create_slow_mock_managers(self):
        """Create mock managers with slower responses (100ms)."""
        mock_feeding_manager = AsyncMock()
        mock_walk_manager = AsyncMock()
        mock_dog_data_manager = AsyncMock()

        async def slow_feeding_response(dog_id):
            await asyncio.sleep(0.1)  # 100ms simulated work
            return {
                "last_feeding": "2025-01-15T10:00:00",
                "meals_today": 2,
                "health_aware_portion": 250.0,
            }

        async def slow_walk_response(dog_id):
            await asyncio.sleep(0.1)  # 100ms simulated work
            return {
                "walk_in_progress": False,
                "walks_today": 1,
            }

        async def slow_gps_response(dog_id):
            await asyncio.sleep(0.1)  # 100ms simulated work
            return {
                "latitude": 52.5200,
                "longitude": 13.4050,
                "available": True,
            }

        async def slow_health_response(dog_id):
            await asyncio.sleep(0.1)  # 100ms simulated work
            return {
                "health": {
                    "current_weight": 25.0,
                    "health_status": "good",
                }
            }

        mock_feeding_manager.async_get_feeding_data.side_effect = slow_feeding_response
        mock_walk_manager.async_get_walk_data.side_effect = slow_walk_response
        mock_walk_manager.async_get_gps_data.side_effect = slow_gps_response
        mock_dog_data_manager.async_get_dog_data.side_effect = slow_health_response

        return {
            "feeding_manager": mock_feeding_manager,
            "walk_manager": mock_walk_manager,
            "dog_data_manager": mock_dog_data_manager,
            "data_manager": AsyncMock(),
            "health_calculator": Mock(),
        }

    async def benchmark_coordinator_update(self, coordinator, iterations=10):
        """Benchmark coordinator update performance."""
        times = []

        for _ in range(iterations):
            start_time = time.perf_counter()
            await coordinator._async_update_data()
            end_time = time.perf_counter()
            times.append(end_time - start_time)

        return {
            "mean": mean(times),
            "min": min(times),
            "max": max(times),
            "stdev": stdev(times) if len(times) > 1 else 0,
            "times": times,
        }

    @pytest.mark.asyncio
    async def test_single_dog_update_performance(
        self, hass: HomeAssistant, small_config
    ):
        """Benchmark single dog update performance."""
        coordinator = PawControlCoordinator(hass, small_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Benchmark
        results = await self.benchmark_coordinator_update(coordinator, iterations=20)

        # Performance expectations for single dog with fast managers
        assert results["mean"] < 0.1, (
            f"Mean update time {results['mean']:.3f}s exceeds 100ms threshold"
        )
        assert results["max"] < 0.2, (
            f"Max update time {results['max']:.3f}s exceeds 200ms threshold"
        )

        print(
            f"Single dog performance: {results['mean']:.3f}s ± {results['stdev']:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_medium_load_update_performance(
        self, hass: HomeAssistant, medium_config
    ):
        """Benchmark medium load (5 dogs) update performance."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Benchmark
        results = await self.benchmark_coordinator_update(coordinator, iterations=15)

        # Performance expectations for 5 dogs - should scale well due to parallelization
        assert results["mean"] < 0.2, (
            f"Mean update time {results['mean']:.3f}s exceeds 200ms threshold"
        )
        assert results["max"] < 0.4, (
            f"Max update time {results['max']:.3f}s exceeds 400ms threshold"
        )

        print(
            f"Medium load (5 dogs) performance: {results['mean']:.3f}s ± {results['stdev']:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_large_load_update_performance(
        self, hass: HomeAssistant, large_config
    ):
        """Benchmark large load (20 dogs) update performance."""
        coordinator = PawControlCoordinator(hass, large_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Benchmark
        results = await self.benchmark_coordinator_update(coordinator, iterations=10)

        # Performance expectations for 20 dogs - parallel processing should keep this reasonable
        assert results["mean"] < 0.5, (
            f"Mean update time {results['mean']:.3f}s exceeds 500ms threshold"
        )
        assert results["max"] < 1.0, (
            f"Max update time {results['max']:.3f}s exceeds 1s threshold"
        )

        print(
            f"Large load (20 dogs) performance: {results['mean']:.3f}s ± {results['stdev']:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_parallelization_efficiency(self, hass: HomeAssistant, medium_config):
        """Test that parallelization provides performance benefits."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = (
            self.create_slow_mock_managers()
        )  # Use slower managers to see parallelization benefit
        coordinator.set_managers(**managers)

        # Benchmark parallel execution
        results = await self.benchmark_coordinator_update(coordinator, iterations=5)

        # With 5 dogs and 100ms per manager call (4 calls per dog = 400ms each)
        # Sequential would be: 5 dogs * 400ms = 2000ms
        # Parallel should be close to: max(400ms) = 400ms + overhead

        # Should be much faster than sequential execution
        assert results["mean"] < 1.0, (
            f"Parallel execution not efficient: {results['mean']:.3f}s"
        )

        # Should be closer to single-dog time than 5x single-dog time
        single_dog_equivalent = 0.4  # 4 managers * 100ms each
        assert results["mean"] < single_dog_equivalent * 2, (
            "Parallelization not providing benefit"
        )

        print(
            f"Parallelization test: {results['mean']:.3f}s (should be ~400ms, not 2000ms)"
        )

    @pytest.mark.asyncio
    async def test_cache_manager_performance_impact(
        self, hass: HomeAssistant, medium_config
    ):
        """Test cache manager performance impact."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # First update (cold cache)
        cold_start = time.perf_counter()
        await coordinator._async_update_data()
        cold_end = time.perf_counter()
        cold_time = cold_end - cold_start

        # Second update (should benefit from caching at coordinator level)
        warm_start = time.perf_counter()
        await coordinator._async_update_data()
        warm_end = time.perf_counter()
        warm_time = warm_end - warm_start

        # Cache operations should not significantly impact performance
        cache_overhead = warm_time / cold_time if cold_time > 0 else 1.0
        assert cache_overhead < 1.5, f"Cache overhead too high: {cache_overhead:.2f}x"

        # Verify cache is working
        cache_stats = coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] > 0, "Cache not being populated"

        print(
            f"Cache impact: cold={cold_time:.3f}s, warm={warm_time:.3f}s, overhead={cache_overhead:.2f}x"
        )

    @pytest.mark.asyncio
    async def test_performance_monitoring_overhead(
        self, hass: HomeAssistant, medium_config
    ):
        """Test that performance monitoring doesn't significantly impact performance."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Perform several updates to generate performance data
        results = await self.benchmark_coordinator_update(coordinator, iterations=20)

        # Check that monitoring is working
        perf_stats = coordinator._performance_monitor.get_stats()
        assert perf_stats["total_updates"] >= 20
        assert "average_update_time" in perf_stats

        # Monitoring overhead should be minimal
        assert results["mean"] < 0.3, (
            "Performance monitoring causing excessive overhead"
        )

        print(f"Monitoring overhead test: {results['mean']:.3f}s with full monitoring")

    @pytest.mark.asyncio
    async def test_batch_manager_performance_impact(
        self, hass: HomeAssistant, medium_config
    ):
        """Test batch manager performance impact."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Add dogs to batch for selective refresh
        dog_ids = [f"dog_{i}" for i in range(1, 6)]

        # Test selective refresh performance
        start_time = time.perf_counter()
        await coordinator.async_request_selective_refresh(dog_ids, priority=5)
        end_time = time.perf_counter()
        selective_time = end_time - start_time

        # Selective refresh should be fast
        assert selective_time < 0.1, (
            f"Selective refresh too slow: {selective_time:.3f}s"
        )

        # Test batch processing
        batch_start = time.perf_counter()
        batch = await coordinator._batch_manager.get_batch()
        batch_end = time.perf_counter()
        batch_time = batch_end - batch_start

        assert batch_time < 0.01, f"Batch processing too slow: {batch_time:.3f}s"
        assert len(batch) <= coordinator._batch_manager._max_batch_size

        print(
            f"Batch manager: selective_refresh={selective_time:.3f}s, batch_processing={batch_time:.3f}s"
        )

    @pytest.mark.asyncio
    async def test_memory_efficiency_under_load(
        self, hass: HomeAssistant, large_config
    ):
        """Test memory efficiency under load."""
        coordinator = PawControlCoordinator(hass, large_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Perform many updates to test memory management
        for i in range(50):
            await coordinator._async_update_data()

            # Check cache size doesn't grow unbounded
            cache_stats = coordinator._cache_manager.get_stats()
            assert cache_stats["total_entries"] <= cache_stats["max_size"]

            # Check performance data doesn't accumulate
            perf_stats = coordinator._performance_monitor.get_stats()
            assert perf_stats["total_updates"] == i + 1

            # No pending batches should accumulate
            batch_stats = coordinator._batch_manager.get_stats()
            assert batch_stats["pending_updates"] == 0

        print("Memory efficiency test: 50 updates completed without memory issues")

    @pytest.mark.asyncio
    async def test_error_handling_performance_impact(
        self, hass: HomeAssistant, medium_config
    ):
        """Test that error handling doesn't significantly impact performance."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()

        # Make one manager occasionally fail
        original_feeding_func = managers["feeding_manager"].async_get_feeding_data
        error_count = 0

        async def sometimes_fail(dog_id):
            nonlocal error_count
            error_count += 1
            if error_count % 3 == 0:  # Fail every 3rd call
                raise Exception("Simulated error")
            return await original_feeding_func(dog_id)

        managers["feeding_manager"].async_get_feeding_data = sometimes_fail
        coordinator.set_managers(**managers)

        # Benchmark with errors
        results = await self.benchmark_coordinator_update(coordinator, iterations=15)

        # Performance should still be reasonable despite errors
        assert results["mean"] < 0.5, (
            f"Error handling causing excessive overhead: {results['mean']:.3f}s"
        )

        # Check that some errors were handled
        perf_stats = coordinator._performance_monitor.get_stats()
        assert perf_stats["total_errors"] > 0, "No errors were recorded"

        print(
            f"Error handling test: {results['mean']:.3f}s with {perf_stats['total_errors']} errors"
        )

    def test_performance_comparison_summary(self):
        """Print performance summary for manual review."""
        print("\n" + "=" * 80)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 80)
        print("Target Performance Goals:")
        print("- Single dog update: < 100ms")
        print("- 5 dogs update: < 200ms")
        print("- 20 dogs update: < 500ms")
        print("- Parallelization efficiency: ~400ms for 5 dogs (not 2000ms)")
        print("- Cache overhead: < 1.5x")
        print("- Memory: Bounded growth")
        print("- Error handling: < 500ms with failures")
        print("=" * 80)
        print("All benchmarks should pass to validate refactoring success!")
        print("=" * 80)

    @pytest.mark.asyncio
    async def test_coordinator_initialization_performance(
        self, hass: HomeAssistant, large_config
    ):
        """Test coordinator initialization performance."""
        start_time = time.perf_counter()

        coordinator = PawControlCoordinator(hass, large_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        end_time = time.perf_counter()
        init_time = end_time - start_time

        # Initialization should be fast even for many dogs
        assert init_time < 0.1, f"Coordinator initialization too slow: {init_time:.3f}s"

        print(f"Initialization performance (20 dogs): {init_time:.3f}s")

    @pytest.mark.asyncio
    async def test_concurrent_access_performance(
        self, hass: HomeAssistant, medium_config
    ):
        """Test performance under concurrent access."""
        coordinator = PawControlCoordinator(hass, medium_config)
        managers = self.create_fast_mock_managers()
        coordinator.set_managers(**managers)

        # Simulate concurrent sensor access
        async def simulate_sensor_access():
            for _ in range(5):
                dog_data = coordinator.get_dog_data("dog_1")
                if dog_data:
                    # Simulate sensor attribute access
                    dog_data.get("feeding", {})
                    dog_data.get("health", {})
                await asyncio.sleep(0.001)  # Small delay

        # Run concurrent coordinator updates and sensor access
        start_time = time.perf_counter()

        update_task = asyncio.create_task(coordinator._async_update_data())
        sensor_tasks = [
            asyncio.create_task(simulate_sensor_access()) for _ in range(10)
        ]

        await asyncio.gather(update_task, *sensor_tasks)

        end_time = time.perf_counter()
        concurrent_time = end_time - start_time

        # Concurrent access should not cause significant slowdown
        assert concurrent_time < 1.0, (
            f"Concurrent access too slow: {concurrent_time:.3f}s"
        )

        print(f"Concurrent access performance: {concurrent_time:.3f}s")
