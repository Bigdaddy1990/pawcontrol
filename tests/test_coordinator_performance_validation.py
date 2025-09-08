"""Comprehensive coordinator performance validation tests for PawControl.

Tests coordinator performance under high entity loads (500+ entities) including:
- High entity load stress testing
- Memory management and leak detection
- Concurrent operations scalability
- Manager delegation efficiency under load
- Cache performance with large datasets
- Batch processing performance optimization
- Update time validation and SLA compliance
- Resource cleanup and garbage collection
- Performance regression detection
- Load balancing and throttling
- Large-scale data integrity validation
"""

from __future__ import annotations

import asyncio
import gc
import time
import tracemalloc
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    UPDATE_INTERVALS,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util


class TestCoordinatorHighEntityLoadValidation:
    """Test coordinator performance with high entity loads (500+ entities)."""

    @pytest.fixture
    def large_scale_config_entry(self):
        """Create config entry with 100+ dogs for large-scale testing."""
        dogs = []
        for i in range(100):
            dogs.append({
                CONF_DOG_ID: f"performance_dog_{i:03d}",
                CONF_DOG_NAME: f"Performance Dog {i}",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: i % 2 == 0,  # 50% have walk
                    MODULE_HEALTH: i % 3 == 0,  # 33% have health
                    MODULE_GPS: i % 4 == 0,  # 25% have GPS
                },
            })

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "large_scale_test"
        entry.data = {CONF_DOGS: dogs}
        entry.options = {}
        return entry

    @pytest.fixture
    def mock_high_performance_managers(self):
        """Create high-performance mock managers."""
        async def fast_feeding_response(dog_id: str):
            """Fast feeding response."""
            return {
                "dog_id": dog_id,
                "last_feeding": dt_util.utcnow().isoformat(),
                "meals_today": hash(dog_id) % 5,  # Deterministic but varied
                "calories_consumed": (hash(dog_id) % 800) + 200,
            }

        async def fast_walk_response(dog_id: str):
            """Fast walk response."""
            return {
                "dog_id": dog_id,
                "walk_in_progress": hash(dog_id) % 10 == 0,
                "walks_today": hash(dog_id) % 4,
                "total_distance": (hash(dog_id) % 5000) / 100.0,
            }

        async def fast_gps_response(dog_id: str):
            """Fast GPS response."""
            return {
                "dog_id": dog_id,
                "latitude": 52.5200 + (hash(dog_id) % 1000) / 10000.0,
                "longitude": 13.4050 + (hash(dog_id) % 1000) / 10000.0,
                "available": True,
                "accuracy": 5.0,
            }

        async def fast_health_response(dog_id: str):
            """Fast health response."""
            return {
                "health": {
                    "dog_id": dog_id,
                    "current_weight": 20.0 + (hash(dog_id) % 30),
                    "health_status": "good" if hash(dog_id) % 2 == 0 else "fair",
                    "last_checkup": dt_util.utcnow().isoformat(),
                }
            }

        managers = {
            "data_manager": AsyncMock(),
            "dog_data_manager": AsyncMock(),
            "walk_manager": AsyncMock(),
            "feeding_manager": AsyncMock(),
            "health_calculator": Mock(),
        }

        # Configure fast responses
        managers["feeding_manager"].async_get_feeding_data.side_effect = fast_feeding_response
        managers["walk_manager"].async_get_walk_data.side_effect = fast_walk_response
        managers["walk_manager"].async_get_gps_data.side_effect = fast_gps_response
        managers["dog_data_manager"].async_get_dog_data.side_effect = fast_health_response

        return managers

    @pytest.fixture
    def large_scale_coordinator(self, hass: HomeAssistant, large_scale_config_entry, mock_high_performance_managers):
        """Create coordinator with large-scale configuration."""
        coordinator = PawControlCoordinator(hass, large_scale_config_entry)
        coordinator.set_managers(**mock_high_performance_managers)
        return coordinator

    @pytest.mark.asyncio
    async def test_500_entity_load_performance(self, large_scale_coordinator):
        """Test coordinator performance with 500+ entity load."""
        # Verify we have 100 dogs configured
        assert len(large_scale_coordinator.dogs) == 100

        # Start performance tracking
        start_time = time.time()
        tracemalloc.start()

        # Perform full update (simulates 500+ entities)
        data = await large_scale_coordinator._async_update_data()

        # Stop tracking
        end_time = time.time()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Performance assertions
        update_duration = end_time - start_time
        assert update_duration < 10.0, f"Update took {update_duration:.2f}s, expected < 10s"

        # Memory assertions
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 100, f"Peak memory {peak_mb:.1f}MB, expected < 100MB"

        # Data integrity assertions
        assert len(data) == 100, f"Expected 100 dogs, got {len(data)}"

        # Verify each dog has proper data structure
        for dog_id, dog_data in data.items():
            assert "dog_info" in dog_data
            assert dog_data["dog_info"][CONF_DOG_ID] == dog_id

        # Performance statistics
        perf_stats = large_scale_coordinator._performance_monitor.get_stats()
        assert perf_stats["total_updates"] >= 1

    @pytest.mark.asyncio
    async def test_concurrent_high_load_operations(self, large_scale_coordinator):
        """Test concurrent operations under high load."""
        async def concurrent_update_operation(operation_id: int):
            """Perform concurrent update operation."""
            start_time = time.time()
            
            # Mix of operations
            if operation_id % 4 == 0:
                # Full update
                await large_scale_coordinator._async_update_data()
            elif operation_id % 4 == 1:
                # Selective refresh
                dog_ids = [f"performance_dog_{i:03d}" for i in range(operation_id % 10)]
                await large_scale_coordinator.async_request_selective_refresh(dog_ids, priority=5)
            elif operation_id % 4 == 2:
                # Cache operations
                await large_scale_coordinator._cache_manager.optimize_cache()
            else:
                # Statistics gathering
                large_scale_coordinator.get_cache_stats()

            duration = time.time() - start_time
            return operation_id, duration

        # Run 20 concurrent operations
        tasks = [concurrent_update_operation(i) for i in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Analyze results
        successful_operations = [r for r in results if not isinstance(r, Exception)]
        failed_operations = [r for r in results if isinstance(r, Exception)]

        # Should have high success rate
        success_rate = len(successful_operations) / len(results)
        assert success_rate >= 0.8, f"Success rate {success_rate:.1%}, expected >= 80%"

        # Check operation durations
        durations = [duration for _, duration in successful_operations]
        avg_duration = sum(durations) / len(durations) if durations else 0
        assert avg_duration < 5.0, f"Average duration {avg_duration:.2f}s, expected < 5s"

    @pytest.mark.asyncio
    async def test_manager_delegation_efficiency_under_load(self, large_scale_coordinator, mock_high_performance_managers):
        """Test manager delegation efficiency under high load."""
        # Record manager call counts before
        initial_calls = {}
        for manager_name, manager in mock_high_performance_managers.items():
            if hasattr(manager, "call_count"):
                initial_calls[manager_name] = manager.call_count

        # Perform multiple updates to stress manager delegation
        update_count = 10
        total_start_time = time.time()

        for i in range(update_count):
            # Selective updates to test delegation efficiency
            batch_size = 20  # Update 20 dogs at a time
            start_dog = (i * batch_size) % 100
            dog_ids = [f"performance_dog_{j:03d}" for j in range(start_dog, min(start_dog + batch_size, 100))]
            
            await large_scale_coordinator.async_request_selective_refresh(dog_ids, priority=7)
            
            # Small delay to allow processing
            await asyncio.sleep(0.1)

        total_duration = time.time() - total_start_time

        # Verify delegation efficiency
        assert total_duration < 15.0, f"Total delegation time {total_duration:.2f}s, expected < 15s"

        # Verify managers were called appropriately
        feeding_calls = mock_high_performance_managers["feeding_manager"].async_get_feeding_data.call_count
        walk_calls = mock_high_performance_managers["walk_manager"].async_get_walk_data.call_count

        # Should have made reasonable number of calls (not excessive)
        assert feeding_calls > 0, "Feeding manager should be called"
        assert feeding_calls <= 100 * update_count, "Feeding calls should be reasonable"

    @pytest.mark.asyncio
    async def test_cache_performance_with_large_dataset(self, large_scale_coordinator):
        """Test cache performance with large dataset."""
        cache_manager = large_scale_coordinator._cache_manager

        # Pre-populate cache with large dataset
        large_dataset_size = 500
        population_start = time.time()

        for i in range(large_dataset_size):
            key = f"large_dataset_key_{i}"
            data = {
                "dog_id": f"cache_dog_{i}",
                "data": "x" * 1000,  # 1KB per entry
                "timestamp": dt_util.utcnow().isoformat(),
                "metadata": {
                    "access_count": 0,
                    "priority": i % 10,
                    "nested_data": {"level1": {"level2": {"value": i}}},
                },
            }
            await cache_manager.set(key, data, ttl_seconds=3600)

        population_duration = time.time() - population_start
        assert population_duration < 5.0, f"Cache population took {population_duration:.2f}s, expected < 5s"

        # Test cache retrieval performance
        retrieval_start = time.time()
        
        retrieved_count = 0
        for i in range(0, large_dataset_size, 10):  # Sample every 10th entry
            key = f"large_dataset_key_{i}"
            data = await cache_manager.get(key)
            if data is not None:
                retrieved_count += 1

        retrieval_duration = time.time() - retrieval_start
        retrieval_rate = retrieved_count / retrieval_duration

        # Performance assertions
        assert retrieval_rate > 100, f"Retrieval rate {retrieval_rate:.1f} ops/s, expected > 100 ops/s"
        assert retrieved_count > 40, f"Retrieved {retrieved_count} entries, expected > 40"

        # Test cache statistics under load
        stats = cache_manager.get_stats()
        assert stats["total_entries"] > 0
        assert stats["hit_rate"] > 50  # Should have reasonable hit rate

        # Test cache optimization under load
        optimization_start = time.time()
        opt_result = await cache_manager.optimize_cache()
        optimization_duration = time.time() - optimization_start

        assert optimization_duration < 2.0, f"Optimization took {optimization_duration:.2f}s, expected < 2s"
        assert opt_result["optimization_completed"] is True

    @pytest.mark.asyncio
    async def test_batch_processing_performance_scaling(self, large_scale_coordinator):
        """Test batch processing performance and scaling."""
        batch_manager = large_scale_coordinator._batch_manager

        # Add large number of items to batch
        batch_size_test = 200
        addition_start = time.time()

        for i in range(batch_size_test):
            dog_id = f"batch_dog_{i:03d}"
            priority = 10 - (i % 10)  # Varying priorities
            await batch_manager.add_to_batch(dog_id, priority)

        addition_duration = time.time() - addition_start
        addition_rate = batch_size_test / addition_duration

        assert addition_rate > 500, f"Batch addition rate {addition_rate:.1f} ops/s, expected > 500 ops/s"

        # Test batch retrieval performance
        retrieval_tests = 10
        total_retrieval_time = 0

        for _ in range(retrieval_tests):
            retrieval_start = time.time()
            batch = await batch_manager.get_batch()
            retrieval_duration = time.time() - retrieval_start
            total_retrieval_time += retrieval_duration

            # Verify batch content
            assert len(batch) > 0, "Batch should not be empty"
            assert len(batch) <= batch_manager.max_batch_size

        avg_retrieval_time = total_retrieval_time / retrieval_tests
        assert avg_retrieval_time < 0.1, f"Average batch retrieval {avg_retrieval_time:.3f}s, expected < 0.1s"

        # Test batch optimization under load
        optimization_start = time.time()
        opt_result = await batch_manager.optimize_batching()
        optimization_duration = time.time() - optimization_start

        assert optimization_duration < 1.0, f"Batch optimization took {optimization_duration:.2f}s, expected < 1s"

    @pytest.mark.asyncio
    async def test_update_time_sla_compliance(self, large_scale_coordinator):
        """Test update time SLA compliance under various loads."""
        # Define SLA thresholds
        sla_thresholds = {
            "light_load": 2.0,    # < 2s for light load
            "medium_load": 5.0,   # < 5s for medium load  
            "heavy_load": 10.0,   # < 10s for heavy load
        }

        # Test light load (10 dogs)
        light_load_dogs = [f"performance_dog_{i:03d}" for i in range(10)]
        start_time = time.time()
        await large_scale_coordinator.async_request_selective_refresh(light_load_dogs, priority=8)
        light_duration = time.time() - start_time
        
        assert light_duration < sla_thresholds["light_load"], \
            f"Light load took {light_duration:.2f}s, SLA: {sla_thresholds['light_load']}s"

        # Test medium load (50 dogs)
        medium_load_dogs = [f"performance_dog_{i:03d}" for i in range(50)]
        start_time = time.time()
        await large_scale_coordinator.async_request_selective_refresh(medium_load_dogs, priority=6)
        medium_duration = time.time() - start_time

        assert medium_duration < sla_thresholds["medium_load"], \
            f"Medium load took {medium_duration:.2f}s, SLA: {sla_thresholds['medium_load']}s"

        # Test heavy load (all 100 dogs)
        start_time = time.time()
        data = await large_scale_coordinator._async_update_data()
        heavy_duration = time.time() - start_time

        assert heavy_duration < sla_thresholds["heavy_load"], \
            f"Heavy load took {heavy_duration:.2f}s, SLA: {sla_thresholds['heavy_load']}s"

        # Verify data integrity across all loads
        assert len(data) == 100, "Heavy load should process all dogs"


class TestCoordinatorMemoryManagementAndLeakDetection:
    """Test memory management and leak detection under sustained load."""

    @pytest.mark.asyncio
    async def test_memory_leak_detection_sustained_operations(self, large_scale_coordinator):
        """Test for memory leaks during sustained operations."""
        # Enable memory tracking
        tracemalloc.start()
        
        # Baseline memory measurement
        gc.collect()  # Force garbage collection
        baseline_current, baseline_peak = tracemalloc.get_traced_memory()

        # Perform sustained operations
        operation_cycles = 50
        memory_snapshots = []

        for cycle in range(operation_cycles):
            # Mix of operations that could cause leaks
            await large_scale_coordinator._async_update_data()
            
            # Cache operations
            await large_scale_coordinator._cache_manager.set(f"leak_test_{cycle}", {"cycle": cycle})
            await large_scale_coordinator._cache_manager.get(f"leak_test_{cycle}")
            
            # Batch operations
            await large_scale_coordinator._batch_manager.add_to_batch(f"leak_dog_{cycle}", 5)
            
            # Force garbage collection every 10 cycles
            if cycle % 10 == 0:
                gc.collect()
                current, peak = tracemalloc.get_traced_memory()
                memory_snapshots.append({
                    "cycle": cycle,
                    "current": current,
                    "peak": peak,
                    "time": time.time()
                })

        # Final memory measurement
        gc.collect()
        final_current, final_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Analyze memory growth
        memory_growth = final_current - baseline_current
        memory_growth_mb = memory_growth / 1024 / 1024

        # Memory growth should be reasonable (< 50MB after 50 cycles)
        assert memory_growth_mb < 50, f"Memory grew by {memory_growth_mb:.1f}MB, expected < 50MB"

        # Check for progressive memory growth (potential leak)
        if len(memory_snapshots) >= 3:
            first_snapshot = memory_snapshots[0]["current"]
            last_snapshot = memory_snapshots[-1]["current"]
            progressive_growth = (last_snapshot - first_snapshot) / 1024 / 1024

            # Progressive growth should be minimal
            assert progressive_growth < 30, f"Progressive growth {progressive_growth:.1f}MB, expected < 30MB"

    @pytest.mark.asyncio
    async def test_resource_cleanup_effectiveness(self, large_scale_coordinator):
        """Test effectiveness of resource cleanup under load."""
        # Create resources that need cleanup
        initial_cache_entries = 100
        for i in range(initial_cache_entries):
            await large_scale_coordinator._cache_manager.set(
                f"cleanup_test_{i}", 
                {"data": "x" * 1000}, 
                ttl_seconds=1  # Short TTL for testing
            )

        # Add batch items
        for i in range(50):
            await large_scale_coordinator._batch_manager.add_to_batch(f"cleanup_dog_{i}", 3)

        # Verify resources exist
        cache_stats_before = large_scale_coordinator._cache_manager.get_stats()
        assert cache_stats_before["total_entries"] == initial_cache_entries

        # Wait for TTL expiry
        await asyncio.sleep(1.2)

        # Trigger cleanup operations
        cleared_count = await large_scale_coordinator._cache_manager.clear_expired()
        await large_scale_coordinator._cache_manager.optimize_cache()
        await large_scale_coordinator._batch_manager.optimize_batching()

        # Verify cleanup effectiveness
        assert cleared_count >= initial_cache_entries, f"Cleared {cleared_count}, expected >= {initial_cache_entries}"

        cache_stats_after = large_scale_coordinator._cache_manager.get_stats()
        assert cache_stats_after["total_entries"] < cache_stats_before["total_entries"]

        # Test cleanup under concurrent load
        async def concurrent_resource_creation():
            """Create resources concurrently during cleanup."""
            for i in range(20):
                await large_scale_coordinator._cache_manager.set(f"concurrent_{i}", {"data": i})
                await asyncio.sleep(0.01)

        async def concurrent_cleanup():
            """Perform cleanup concurrently with resource creation."""
            await asyncio.sleep(0.05)  # Let some resources be created
            await large_scale_coordinator._cache_manager.optimize_cache()

        # Run concurrent operations
        await asyncio.gather(
            concurrent_resource_creation(),
            concurrent_cleanup(),
            return_exceptions=True
        )

        # Verify coordinator remains functional after concurrent cleanup
        final_stats = large_scale_coordinator.get_cache_stats()
        assert "cache" in final_stats
        assert final_stats["cache"]["total_entries"] >= 0

    @pytest.mark.asyncio
    async def test_garbage_collection_integration(self, large_scale_coordinator):
        """Test integration with Python garbage collection."""
        # Create objects that reference each other (potential circular references)
        circular_objects = []
        for i in range(100):
            obj_a = {"id": f"obj_a_{i}", "ref": None}
            obj_b = {"id": f"obj_b_{i}", "ref": obj_a}
            obj_a["ref"] = obj_b  # Circular reference
            
            circular_objects.append((obj_a, obj_b))
            
            # Store in cache to test garbage collection with cache
            await large_scale_coordinator._cache_manager.set(f"circular_{i}", obj_a)

        # Force garbage collection
        collected_before = gc.collect()

        # Clear references
        circular_objects.clear()

        # Update coordinator (should not hold references to cleared objects)
        await large_scale_coordinator._async_update_data()

        # Clear cache
        await large_scale_coordinator._cache_manager.clear()

        # Force garbage collection again
        collected_after = gc.collect()

        # Should have collected the circular references
        assert collected_after > 0, "Garbage collection should have found unreferenced objects"

        # Verify coordinator still functions properly
        cache_stats = large_scale_coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_large_object_handling_and_memory_efficiency(self, large_scale_coordinator):
        """Test handling of large objects and memory efficiency."""
        # Create large objects (simulating large dog datasets)
        large_object_size = 1000  # 1KB strings
        large_object_count = 100

        start_time = time.time()
        tracemalloc.start()

        for i in range(large_object_count):
            large_object = {
                "dog_id": f"large_dog_{i}",
                "large_data": "x" * large_object_size,
                "metadata": {
                    "created": dt_util.utcnow().isoformat(),
                    "size": large_object_size,
                    "nested": {
                        "level1": {"data": "y" * 100},
                        "level2": {"data": "z" * 100},
                        "level3": list(range(100)),
                    }
                }
            }
            
            # Store in coordinator's data structure
            large_scale_coordinator._data[f"large_dog_{i}"] = large_object
            
            # Also cache it
            await large_scale_coordinator._cache_manager.set(f"large_dog_{i}", large_object)

        creation_duration = time.time() - start_time
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Performance assertions for large object handling
        assert creation_duration < 5.0, f"Large object creation took {creation_duration:.2f}s, expected < 5s"

        peak_mb = peak / 1024 / 1024
        expected_min_mb = (large_object_size * large_object_count) / 1024 / 1024
        
        # Memory usage should be reasonable (not excessive overhead)
        assert peak_mb < expected_min_mb * 3, f"Peak memory {peak_mb:.1f}MB excessive for {expected_min_mb:.1f}MB data"

        # Test retrieval performance with large objects
        retrieval_start = time.time()
        
        for i in range(0, large_object_count, 10):  # Sample every 10th
            data = large_scale_coordinator.get_dog_data(f"large_dog_{i}")
            assert data is not None
            assert len(data["large_data"]) == large_object_size

        retrieval_duration = time.time() - retrieval_start
        retrieval_rate = (large_object_count // 10) / retrieval_duration

        assert retrieval_rate > 50, f"Large object retrieval rate {retrieval_rate:.1f} ops/s, expected > 50 ops/s"


class TestCoordinatorPerformanceRegressionDetection:
    """Test performance regression detection and monitoring."""

    @pytest.mark.asyncio
    async def test_performance_benchmarking_and_regression_detection(self, large_scale_coordinator):
        """Test performance benchmarking to detect regressions."""
        # Baseline performance benchmarks
        benchmarks = {
            "single_dog_update": 0.1,    # 100ms
            "batch_10_dogs": 0.5,        # 500ms
            "full_update_100_dogs": 3.0,  # 3s
            "cache_operation": 0.001,     # 1ms
            "optimization": 1.0,          # 1s
        }

        performance_results = {}

        # Benchmark single dog update
        start_time = time.time()
        await large_scale_coordinator._fetch_dog_data_delegated("performance_dog_001")
        performance_results["single_dog_update"] = time.time() - start_time

        # Benchmark batch update (10 dogs)
        dog_ids = [f"performance_dog_{i:03d}" for i in range(10)]
        start_time = time.time()
        await large_scale_coordinator.async_request_selective_refresh(dog_ids, priority=8)
        performance_results["batch_10_dogs"] = time.time() - start_time

        # Benchmark full update (100 dogs)
        start_time = time.time()
        await large_scale_coordinator._async_update_data()
        performance_results["full_update_100_dogs"] = time.time() - start_time

        # Benchmark cache operation
        start_time = time.time()
        await large_scale_coordinator._cache_manager.set("benchmark_key", {"test": "data"})
        await large_scale_coordinator._cache_manager.get("benchmark_key")
        performance_results["cache_operation"] = time.time() - start_time

        # Benchmark optimization
        start_time = time.time()
        await large_scale_coordinator._cache_manager.optimize_cache()
        performance_results["optimization"] = time.time() - start_time

        # Check for performance regressions
        regression_threshold = 2.0  # Allow 2x slowdown before flagging regression
        regressions = []

        for operation, duration in performance_results.items():
            expected = benchmarks[operation]
            if duration > expected * regression_threshold:
                regressions.append({
                    "operation": operation,
                    "duration": duration,
                    "expected": expected,
                    "slowdown": duration / expected
                })

        # Report any regressions
        assert len(regressions) == 0, f"Performance regressions detected: {regressions}"

        # Verify all operations completed within reasonable bounds
        for operation, duration in performance_results.items():
            assert duration < benchmarks[operation] * 5, \
                f"{operation} took {duration:.3f}s, expected < {benchmarks[operation] * 5:.3f}s"

    @pytest.mark.asyncio
    async def test_performance_monitoring_and_alerting(self, large_scale_coordinator):
        """Test performance monitoring and alerting system."""
        performance_monitor = large_scale_coordinator._performance_monitor

        # Simulate various performance scenarios
        scenarios = [
            {"duration": 0.1, "errors": 0, "name": "fast_update"},
            {"duration": 0.5, "errors": 0, "name": "normal_update"},
            {"duration": 2.0, "errors": 0, "name": "slow_update"},
            {"duration": 0.2, "errors": 1, "name": "error_update"},
            {"duration": 5.0, "errors": 0, "name": "very_slow_update"},
        ]

        # Record performance data
        for scenario in scenarios:
            performance_monitor.record_update(scenario["duration"], scenario["errors"])

        # Get performance statistics
        stats = performance_monitor.get_stats()

        # Verify monitoring captures the data
        assert stats["total_updates"] == len(scenarios)
        assert stats["total_errors"] == sum(s["errors"] for s in scenarios)

        # Test performance health scoring
        health_score = performance_monitor.get_performance_health_score()

        assert "health_level" in health_score
        assert "overall_score" in health_score
        assert "recommendations" in health_score
        assert health_score["overall_score"] >= 0
        assert health_score["overall_score"] <= 100

        # Test performance alerting for degradation
        # Simulate performance degradation
        for _ in range(10):
            performance_monitor.record_update(10.0, 1)  # Very slow with errors

        degraded_health = performance_monitor.get_performance_health_score()
        
        # Health score should reflect degradation
        assert degraded_health["overall_score"] < health_score["overall_score"]
        assert len(degraded_health["recommendations"]) > 0

    @pytest.mark.asyncio
    async def test_load_balancing_and_throttling_effectiveness(self, large_scale_coordinator):
        """Test load balancing and throttling mechanisms."""
        # Test batch manager load balancing
        batch_manager = large_scale_coordinator._batch_manager

        # Add many items with different priorities
        high_priority_count = 20
        medium_priority_count = 30
        low_priority_count = 50

        for i in range(high_priority_count):
            await batch_manager.add_to_batch(f"high_priority_{i}", 9)

        for i in range(medium_priority_count):
            await batch_manager.add_to_batch(f"medium_priority_{i}", 5)

        for i in range(low_priority_count):
            await batch_manager.add_to_batch(f"low_priority_{i}", 1)

        # Test load balancing in batch retrieval
        batches_retrieved = []
        for _ in range(10):  # Retrieve multiple batches
            batch = await batch_manager.get_batch()
            if batch:
                batches_retrieved.append(batch)

        # Verify priority ordering in batches
        high_priority_in_early_batches = 0
        for batch in batches_retrieved[:3]:  # Check first 3 batches
            high_priority_in_early_batches += sum(1 for item in batch if "high_priority" in item)

        # High priority items should appear in early batches
        assert high_priority_in_early_batches > 0, "High priority items should be processed first"

        # Test throttling under extreme load
        cache_manager = large_scale_coordinator._cache_manager

        # Rapid cache operations to test throttling
        rapid_operations_start = time.time()
        
        for i in range(200):  # Rapid-fire operations
            await cache_manager.set(f"throttle_test_{i}", {"rapid": i})
            if i % 10 == 0:
                await cache_manager.get(f"throttle_test_{i}")

        rapid_operations_duration = time.time() - rapid_operations_start

        # Operations should complete in reasonable time (throttling shouldn't cause excessive delays)
        operations_per_second = 200 / rapid_operations_duration
        assert operations_per_second > 100, f"Cache operations rate {operations_per_second:.1f} ops/s too slow"

        # Verify cache remains functional after rapid operations
        final_stats = cache_manager.get_stats()
        assert final_stats["total_entries"] > 0
        assert final_stats["hit_rate"] >= 0  # Should be valid percentage


class TestCoordinatorLargeScaleDataIntegrityValidation:
    """Test data integrity under large-scale operations."""

    @pytest.mark.asyncio
    async def test_data_consistency_across_concurrent_updates(self, large_scale_coordinator):
        """Test data consistency during concurrent updates."""
        # Pre-populate with initial data
        initial_data = {}
        for i in range(50):
            dog_id = f"consistency_dog_{i:03d}"
            initial_data[dog_id] = {
                "version": 0,
                "update_count": 0,
                "checksum": f"initial_{i}",
            }
            large_scale_coordinator._data[dog_id] = initial_data[dog_id]

        async def concurrent_updater(updater_id: int):
            """Perform concurrent updates."""
            updates_performed = 0
            for i in range(20):
                dog_id = f"consistency_dog_{(updater_id * 10 + i) % 50:03d}"
                
                # Read current data
                current_data = large_scale_coordinator.get_dog_data(dog_id)
                if current_data:
                    # Update data
                    updated_data = current_data.copy()
                    updated_data["version"] = current_data.get("version", 0) + 1
                    updated_data["update_count"] = current_data.get("update_count", 0) + 1
                    updated_data["updater"] = updater_id
                    updated_data["checksum"] = f"updated_{updater_id}_{i}"
                    
                    # Store updated data
                    large_scale_coordinator._data[dog_id] = updated_data
                    updates_performed += 1
                
                await asyncio.sleep(0.01)  # Small delay to create contention

            return updater_id, updates_performed

        # Run multiple concurrent updaters
        updaters = [concurrent_updater(i) for i in range(8)]
        results = await asyncio.gather(*updaters, return_exceptions=True)

        # Verify all updaters completed successfully
        successful_updaters = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_updaters) == 8, "All updaters should complete successfully"

        # Verify data integrity
        for dog_id, dog_data in large_scale_coordinator._data.items():
            if dog_id.startswith("consistency_dog_"):
                # Data should have valid version and update count
                assert "version" in dog_data
                assert "update_count" in dog_data
                assert dog_data["version"] >= 0
                assert dog_data["update_count"] >= 0
                
                # Checksums should be consistent
                assert "checksum" in dog_data
                assert dog_data["checksum"].startswith(("initial_", "updated_"))

    @pytest.mark.asyncio
    async def test_cache_coherency_under_high_load(self, large_scale_coordinator):
        """Test cache coherency under high load conditions."""
        cache_manager = large_scale_coordinator._cache_manager

        # Test data
        coherency_test_data = {}
        for i in range(100):
            key = f"coherency_key_{i}"
            data = {
                "id": i,
                "value": f"original_value_{i}",
                "timestamp": dt_util.utcnow().isoformat(),
                "metadata": {"source": "coherency_test"}
            }
            coherency_test_data[key] = data
            await cache_manager.set(key, data)

        async def cache_reader(reader_id: int):
            """Read from cache continuously."""
            reads_performed = 0
            inconsistencies = 0
            
            for i in range(50):
                key = f"coherency_key_{(reader_id * 10 + i) % 100}"
                cached_data = await cache_manager.get(key)
                
                if cached_data:
                    reads_performed += 1
                    # Verify data integrity
                    if "id" not in cached_data or "value" not in cached_data:
                        inconsistencies += 1
                
                await asyncio.sleep(0.001)

            return reader_id, reads_performed, inconsistencies

        async def cache_updater(updater_id: int):
            """Update cache entries continuously."""
            updates_performed = 0
            
            for i in range(30):
                key = f"coherency_key_{(updater_id * 15 + i) % 100}"
                
                # Get current data
                current_data = await cache_manager.get(key)
                if current_data:
                    # Update data
                    updated_data = current_data.copy()
                    updated_data["value"] = f"updated_by_{updater_id}_{i}"
                    updated_data["update_timestamp"] = dt_util.utcnow().isoformat()
                    
                    # Store updated data
                    await cache_manager.set(key, updated_data)
                    updates_performed += 1
                
                await asyncio.sleep(0.002)

            return updater_id, updates_performed

        # Run concurrent readers and updaters
        readers = [cache_reader(i) for i in range(5)]
        updaters = [cache_updater(i) for i in range(3)]
        
        all_tasks = readers + updaters
        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # Analyze results
        reader_results = results[:5]
        updater_results = results[5:]

        # Verify readers completed successfully
        total_reads = 0
        total_inconsistencies = 0
        
        for result in reader_results:
            if not isinstance(result, Exception):
                _, reads, inconsistencies = result
                total_reads += reads
                total_inconsistencies += inconsistencies

        # Verify updaters completed successfully
        total_updates = 0
        for result in updater_results:
            if not isinstance(result, Exception):
                _, updates = result
                total_updates += updates

        # Assertions
        assert total_reads > 0, "Readers should have performed reads"
        assert total_updates > 0, "Updaters should have performed updates"
        
        # Inconsistency rate should be very low
        inconsistency_rate = total_inconsistencies / total_reads if total_reads > 0 else 0
        assert inconsistency_rate < 0.01, f"Inconsistency rate {inconsistency_rate:.3f} too high"

        # Cache should remain functional
        final_stats = cache_manager.get_stats()
        assert final_stats["total_entries"] > 0

    @pytest.mark.asyncio
    async def test_coordinator_state_integrity_validation(self, large_scale_coordinator):
        """Test coordinator state integrity under stress."""
        # Perform stress operations that could corrupt state
        stress_operations = [
            "update_data",
            "selective_refresh",
            "cache_operations",
            "optimization",
            "statistics_gathering"
        ]

        async def stress_operation_worker(worker_id: int):
            """Perform stress operations."""
            operations_completed = []
            
            for i in range(100):
                operation = stress_operations[i % len(stress_operations)]
                
                try:
                    if operation == "update_data":
                        await large_scale_coordinator._async_update_data()
                    elif operation == "selective_refresh":
                        dog_ids = [f"performance_dog_{j:03d}" for j in range(worker_id, worker_id + 5)]
                        await large_scale_coordinator.async_request_selective_refresh(dog_ids, priority=5)
                    elif operation == "cache_operations":
                        await large_scale_coordinator._cache_manager.optimize_cache()
                    elif operation == "optimization":
                        await large_scale_coordinator._batch_manager.optimize_batching()
                    elif operation == "statistics_gathering":
                        large_scale_coordinator.get_cache_stats()
                    
                    operations_completed.append(operation)
                    
                except Exception as e:
                    # Track any errors but don't fail immediately
                    operations_completed.append(f"ERROR:{operation}:{str(e)}")
                
                await asyncio.sleep(0.01)

            return worker_id, operations_completed

        # Run multiple stress workers
        stress_workers = [stress_operation_worker(i) for i in range(6)]
        results = await asyncio.gather(*stress_workers, return_exceptions=True)

        # Analyze stress test results
        total_operations = 0
        total_errors = 0
        
        for result in results:
            if not isinstance(result, Exception):
                worker_id, operations = result
                total_operations += len(operations)
                total_errors += sum(1 for op in operations if op.startswith("ERROR:"))

        # Error rate should be minimal
        error_rate = total_errors / total_operations if total_operations > 0 else 0
        assert error_rate < 0.05, f"Error rate {error_rate:.3f} too high during stress test"

        # Verify coordinator state integrity after stress
        # Check basic functionality
        assert large_scale_coordinator.available is not None
        assert len(large_scale_coordinator.get_dog_ids()) > 0
        
        # Check cache integrity
        cache_stats = large_scale_coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] >= 0
        assert 0 <= cache_stats["hit_rate"] <= 100
        
        # Check performance monitor integrity
        perf_stats = large_scale_coordinator._performance_monitor.get_stats()
        assert perf_stats["total_updates"] >= 0
        
        # Verify coordinator can still perform basic operations
        test_data = await large_scale_coordinator._fetch_dog_data_delegated("performance_dog_001")
        assert test_data is not None
        assert "dog_info" in test_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
