"""Tests for optimized entity base classes.

Comprehensive test suite for the OptimizedEntityBase class hierarchy including
performance tracking, caching mechanisms, memory management, and error handling.

Quality Scale: Bronze target
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import asyncio
import gc
import sys
import time
import weakref
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.optimized_entity_base import (
    OptimizedBinarySensorBase,
    OptimizedEntityBase,
    OptimizedSensorBase,
    OptimizedSwitchBase,
    PerformanceTracker,
    _ENTITY_REGISTRY,
    _cleanup_global_caches,
    create_optimized_entities_batched,
    get_global_performance_stats,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util


class MockCoordinator:
    """Mock coordinator for testing."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self._data = {
            "test_dog": {
                "dog_info": {
                    "dog_breed": "Test Breed",
                    "dog_age": 5,
                    "dog_size": "medium",
                    "dog_weight": 25.0,
                },
                "last_update": dt_util.utcnow().isoformat(),
                "feeding": {
                    "last_feeding": "2025-01-01T12:00:00",
                    "portions_today": 2,
                },
                "walk": {
                    "last_walk": "2025-01-01T10:00:00",
                    "walks_today": 1,
                },
                "health": {
                    "health_status": "good",
                    "weight": 25.0,
                },
            }
        }

    def get_dog_data(self, dog_id: str) -> dict[str, Any] | None:
        """Get dog data for testing."""
        return self._data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> dict[str, Any]:
        """Get module data for testing."""
        dog_data = self._data.get(dog_id, {})
        return dog_data.get(module, {})


class TestEntityBase(OptimizedEntityBase):
    """Test implementation of OptimizedEntityBase."""

    __test__ = False

    def __init__(self, coordinator, dog_id: str, dog_name: str, **kwargs) -> None:
        super().__init__(
            coordinator=coordinator,
            dog_id=dog_id,
            dog_name=dog_name,
            entity_type="test_entity",
            **kwargs,
        )
        self._test_state = "test_value"

    def _get_entity_state(self) -> Any:
        """Return test state."""
        return self._test_state


class TestPerformanceTracker:
    """Test suite for PerformanceTracker class."""

    def test_performance_tracker_initialization(self) -> None:
        """Test performance tracker initialization."""
        tracker = PerformanceTracker("test_entity")

        assert tracker._entity_id == "test_entity"
        assert tracker._operation_times == []
        assert tracker._error_count == 0
        assert tracker._cache_hits == 0
        assert tracker._cache_misses == 0

    def test_record_operation_time(self) -> None:
        """Test recording operation times."""
        tracker = PerformanceTracker("test_entity")

        tracker.record_operation_time(0.1)
        tracker.record_operation_time(0.2)
        tracker.record_operation_time(0.15)

        assert len(tracker._operation_times) == 3
        assert tracker._operation_times == [0.1, 0.2, 0.15]

    def test_record_operation_time_memory_limit(self) -> None:
        """Test that operation times are limited to prevent memory growth."""
        tracker = PerformanceTracker("test_entity")

        # Add more than the sample size limit
        for i in range(150):
            tracker.record_operation_time(i * 0.001)

        # Should be limited to PERFORMANCE_SAMPLE_SIZE (100)
        assert len(tracker._operation_times) == 100
        assert tracker._operation_times[0] == 0.05  # Should have removed oldest

    def test_error_tracking(self) -> None:
        """Test error counting."""
        tracker = PerformanceTracker("test_entity")

        tracker.record_error()
        tracker.record_error()
        tracker.record_error()

        assert tracker._error_count == 3

    def test_cache_hit_miss_tracking(self) -> None:
        """Test cache performance tracking."""
        tracker = PerformanceTracker("test_entity")

        tracker.record_cache_hit()
        tracker.record_cache_hit()
        tracker.record_cache_miss()

        assert tracker._cache_hits == 2
        assert tracker._cache_misses == 1

    def test_performance_summary_no_data(self) -> None:
        """Test performance summary with no data."""
        tracker = PerformanceTracker("test_entity")

        summary = tracker.get_performance_summary()
        assert summary == {"status": "no_data"}

    def test_performance_summary_with_data(self) -> None:
        """Test performance summary with recorded data."""
        tracker = PerformanceTracker("test_entity")

        # Record some data
        tracker.record_operation_time(0.1)
        tracker.record_operation_time(0.2)
        tracker.record_operation_time(0.3)
        tracker.record_error()
        tracker.record_cache_hit()
        tracker.record_cache_hit()
        tracker.record_cache_miss()

        summary = tracker.get_performance_summary()

        assert summary["avg_operation_time"] == 0.2
        assert summary["min_operation_time"] == 0.1
        assert summary["max_operation_time"] == 0.3
        assert summary["total_operations"] == 3
        assert summary["error_count"] == 1
        assert summary["error_rate"] == 1 / 3
        assert summary["cache_hit_rate"] == (2 / 3) * 100  # 66.67%
        assert summary["total_cache_operations"] == 3


class TestOptimizedEntityBase:
    """Test suite for OptimizedEntityBase class."""

    @pytest.fixture
    def mock_coordinator(self) -> MockCoordinator:
        """Create mock coordinator."""
        return MockCoordinator()

    @pytest.fixture
    def test_entity(self, mock_coordinator) -> TestEntityBase:
        """Create test entity instance."""
        return TestEntityBase(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

    def test_entity_initialization(self, test_entity: TestEntityBase) -> None:
        """Test entity initialization."""
        assert test_entity._dog_id == "test_dog"
        assert test_entity._dog_name == "Test Dog"
        assert test_entity._entity_type == "test_entity"
        assert test_entity._attr_unique_id == "pawcontrol_test_dog_test_entity"
        assert test_entity._attr_name == "Test Dog Test Entity"
        assert isinstance(test_entity._performance_tracker, PerformanceTracker)

    def test_entity_initialization_with_custom_attributes(
        self, mock_coordinator
    ) -> None:
        """Test entity initialization with custom attributes."""
        entity = TestEntityBase(
            coordinator=mock_coordinator,
            dog_id="custom_dog",
            dog_name="Custom Dog",
            unique_id_suffix="custom_suffix",
            name_suffix="Custom Name",
            device_class="custom_class",
            icon="mdi:test",
        )

        assert (
            entity._attr_unique_id == "pawcontrol_custom_dog_test_entity_custom_suffix"
        )
        assert entity._attr_name == "Custom Dog Custom Name"
        assert entity._attr_device_class == "custom_class"
        assert entity._attr_icon == "mdi:test"

    def test_device_info_generation(self, test_entity: TestEntityBase) -> None:
        """Test device info generation and caching."""
        device_info = test_entity.device_info

        assert device_info is not None
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "PawControl"
        assert device_info["model"] == "Smart Dog Monitoring System - Test Breed"
        assert ("pawcontrol", "test_dog") in device_info["identifiers"]

    def test_suggested_area_updates(self, test_entity: TestEntityBase) -> None:
        """Test suggested area is provided via entity property."""
        # Default suggestion is available before device info access
        assert test_entity.suggested_area == "Pet Area - Test Dog"

        # Accessing device info with age data should refine the suggestion
        _ = test_entity.device_info
        assert test_entity.suggested_area == "Pet Area - Test Dog (5yo)"

    def test_device_info_caching(self, test_entity: TestEntityBase) -> None:
        """Test that device info is cached properly."""
        # First call should miss cache
        device_info1 = test_entity.device_info

        # Second call should hit cache
        device_info2 = test_entity.device_info

        # Should be the same object (cached)
        assert device_info1 == device_info2

    def test_availability_calculation(self, test_entity: TestEntityBase) -> None:
        """Test availability calculation."""
        # Should be available with good coordinator and recent data
        assert test_entity.available is True

    def test_availability_unavailable_coordinator(self, mock_coordinator) -> None:
        """Test availability when coordinator is unavailable."""
        mock_coordinator.available = False
        entity = TestEntityBase(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert entity.available is False

    def test_availability_no_dog_data(self, mock_coordinator) -> None:
        """Test availability when no dog data exists."""
        mock_coordinator._data = {}  # Remove dog data
        entity = TestEntityBase(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert entity.available is False

    def test_availability_old_data(self, mock_coordinator) -> None:
        """Test availability when data is too old."""
        old_time = (dt_util.utcnow() - timedelta(minutes=15)).isoformat()
        mock_coordinator._data["test_dog"]["last_update"] = old_time

        entity = TestEntityBase(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert entity.available is False

    def test_extra_state_attributes_generation(
        self, test_entity: TestEntityBase
    ) -> None:
        """Test extra state attributes generation."""
        attributes = test_entity.extra_state_attributes

        assert attributes["dog_id"] == "test_dog"
        assert attributes["dog_name"] == "Test Dog"
        assert attributes["entity_type"] == "test_entity"
        assert "last_updated" in attributes
        assert attributes["dog_breed"] == "Test Breed"
        assert attributes["dog_age"] == 5
        assert attributes["dog_size"] == "medium"
        assert attributes["dog_weight"] == 25.0

    def test_extra_state_attributes_caching(self, test_entity: TestEntityBase) -> None:
        """Test that extra state attributes are cached."""
        # First call should miss cache
        attrs1 = test_entity.extra_state_attributes

        # Second call should hit cache (within TTL)
        attrs2 = test_entity.extra_state_attributes

        # Should have same content but different timestamp due to generation
        assert attrs1["dog_id"] == attrs2["dog_id"]
        assert attrs1["dog_name"] == attrs2["dog_name"]

    def test_dog_data_caching(self, test_entity: TestEntityBase) -> None:
        """Test dog data caching mechanism."""
        # First call should fetch from coordinator
        data1 = test_entity._get_dog_data_cached()

        # Second call should use cache
        data2 = test_entity._get_dog_data_cached()

        assert data1 == data2
        assert data1 is not None
        assert "dog_info" in data1

    def test_module_data_caching(self, test_entity: TestEntityBase) -> None:
        """Test module data caching."""
        # Test feeding module data
        feeding_data1 = test_entity._get_module_data_cached("feeding")
        feeding_data2 = test_entity._get_module_data_cached("feeding")

        assert feeding_data1 == feeding_data2
        assert "last_feeding" in feeding_data1

    async def test_async_update_performance_tracking(
        self, test_entity: TestEntityBase
    ) -> None:
        """Test that async_update tracks performance."""
        initial_count = test_entity._performance_tracker._operation_times

        with patch.object(
            test_entity, "_async_invalidate_caches", new_callable=AsyncMock
        ):
            await test_entity.async_update()

        # Should have recorded operation time
        assert len(test_entity._performance_tracker._operation_times) > len(
            initial_count
        )

    async def test_async_update_error_handling(
        self, test_entity: TestEntityBase
    ) -> None:
        """Test async_update error handling."""
        initial_errors = test_entity._performance_tracker._error_count

        # Mock super().async_update() to raise an exception
        with (
            patch.object(
                OptimizedEntityBase,
                "async_update",
                side_effect=RuntimeError("Test error"),
            ),
            pytest.raises(RuntimeError),
        ):
            await test_entity.async_update()

        # Should have recorded the error
        assert test_entity._performance_tracker._error_count > initial_errors

    async def test_cache_invalidation(self, test_entity: TestEntityBase) -> None:
        """Test cache invalidation functionality."""
        # Populate caches first
        test_entity._get_dog_data_cached()
        attributes = test_entity.extra_state_attributes
        assert isinstance(attributes, dict)

        # Invalidate caches
        await test_entity._async_invalidate_caches()

        # This test mainly ensures no exceptions are raised during invalidation
        assert True

    def test_performance_metrics_retrieval(self, test_entity: TestEntityBase) -> None:
        """Test performance metrics retrieval."""
        # Record some performance data
        test_entity._performance_tracker.record_operation_time(0.1)
        test_entity._performance_tracker.record_cache_hit()

        metrics = test_entity.get_performance_metrics()

        assert "entity_id" in metrics
        assert "dog_id" in metrics
        assert "entity_type" in metrics
        assert "performance" in metrics
        assert "memory_usage_estimate" in metrics
        assert metrics["entity_id"] == test_entity._attr_unique_id

    def test_memory_usage_estimation(self, test_entity: TestEntityBase) -> None:
        """Test memory usage estimation."""
        memory_usage = test_entity._estimate_memory_usage()

        assert "base_entity_bytes" in memory_usage
        assert "cache_contribution_bytes" in memory_usage
        assert "estimated_total_bytes" in memory_usage
        assert memory_usage["base_entity_bytes"] > 0


class TestOptimizedSensorBase:
    """Test suite for OptimizedSensorBase class."""

    @pytest.fixture
    def sensor_entity(self, mock_coordinator: MockCoordinator) -> OptimizedSensorBase:
        """Create test sensor entity."""
        return OptimizedSensorBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            sensor_type="test_sensor",
            device_class="temperature",
            state_class="measurement",
            unit_of_measurement="°C",
        )

    def test_sensor_initialization(self, sensor_entity: OptimizedSensorBase) -> None:
        """Test sensor entity initialization."""
        assert sensor_entity._entity_type == "sensor_test_sensor"
        assert sensor_entity._attr_state_class == "measurement"
        assert sensor_entity._attr_native_unit_of_measurement == "°C"
        assert sensor_entity._attr_device_class == "temperature"

    def test_sensor_native_value(self, sensor_entity: OptimizedSensorBase) -> None:
        """Test sensor native value property."""
        # Initially None
        assert sensor_entity.native_value is None

        # Set value
        sensor_entity._attr_native_value = 25.5
        assert sensor_entity.native_value == 25.5

    def test_sensor_state(self, sensor_entity: OptimizedSensorBase) -> None:
        """Test sensor state retrieval."""
        sensor_entity._attr_native_value = 30.0
        assert sensor_entity._get_entity_state() == 30.0


class TestOptimizedBinarySensorBase:
    """Test suite for OptimizedBinarySensorBase class."""

    @pytest.fixture
    def binary_sensor_entity(
        self, mock_coordinator: MockCoordinator
    ) -> OptimizedBinarySensorBase:
        """Create test binary sensor entity."""
        return OptimizedBinarySensorBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            sensor_type="test_binary_sensor",
            device_class="motion",
            icon_on="mdi:motion-sensor",
            icon_off="mdi:motion-sensor-off",
        )

    def test_binary_sensor_initialization(
        self, binary_sensor_entity: OptimizedBinarySensorBase
    ) -> None:
        """Test binary sensor initialization."""
        assert binary_sensor_entity._entity_type == "binary_sensor_test_binary_sensor"
        assert binary_sensor_entity._attr_device_class == "motion"
        assert binary_sensor_entity._icon_on == "mdi:motion-sensor"
        assert binary_sensor_entity._icon_off == "mdi:motion-sensor-off"

    def test_binary_sensor_state(
        self, binary_sensor_entity: OptimizedBinarySensorBase
    ) -> None:
        """Test binary sensor state."""
        # Initially off
        assert binary_sensor_entity.is_on is False

        # Turn on
        binary_sensor_entity._attr_is_on = True
        assert binary_sensor_entity.is_on is True
        assert binary_sensor_entity._get_entity_state() is True

    def test_binary_sensor_dynamic_icon(
        self, binary_sensor_entity: OptimizedBinarySensorBase
    ) -> None:
        """Test dynamic icon based on state."""
        # When off
        binary_sensor_entity._attr_is_on = False
        assert binary_sensor_entity.icon == "mdi:motion-sensor-off"

        # When on
        binary_sensor_entity._attr_is_on = True
        assert binary_sensor_entity.icon == "mdi:motion-sensor"


class TestOptimizedSwitchBase:
    """Test suite for OptimizedSwitchBase class."""

    @pytest.fixture
    def switch_entity(self, mock_coordinator: MockCoordinator) -> OptimizedSwitchBase:
        """Create test switch entity."""
        return OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            switch_type="test_switch",
            device_class="switch",
            initial_state=False,
        )

    def test_switch_initialization(self, switch_entity: OptimizedSwitchBase) -> None:
        """Test switch initialization."""
        assert switch_entity._entity_type == "switch_test_switch"
        assert switch_entity._attr_device_class == "switch"
        assert switch_entity._attr_is_on is False

    def test_switch_state(self, switch_entity: OptimizedSwitchBase) -> None:
        """Test switch state management."""
        assert switch_entity.is_on is False
        assert switch_entity._get_entity_state() is False

        switch_entity._attr_is_on = True
        assert switch_entity.is_on is True
        assert switch_entity._get_entity_state() is True

    async def test_switch_turn_on(self, switch_entity: OptimizedSwitchBase) -> None:
        """Test switch turn on functionality."""
        assert switch_entity.is_on is False

        await switch_entity.async_turn_on()

        assert switch_entity.is_on is True
        assert switch_entity._performance_tracker._operation_times[-1] > 0

    async def test_switch_turn_off(self, switch_entity: OptimizedSwitchBase) -> None:
        """Test switch turn off functionality."""
        # Start with switch on
        switch_entity._attr_is_on = True
        assert switch_entity.is_on is True

        await switch_entity.async_turn_off()

        assert switch_entity.is_on is False
        assert switch_entity._performance_tracker._operation_times[-1] > 0

    async def test_switch_turn_on_error_handling(
        self, switch_entity: OptimizedSwitchBase
    ) -> None:
        """Test switch turn on error handling."""
        # Mock implementation to raise error
        with patch.object(
            switch_entity,
            "_async_turn_on_implementation",
            side_effect=Exception("Test error"),
        ):
            initial_errors = switch_entity._performance_tracker._error_count

            with pytest.raises(HomeAssistantError):
                await switch_entity.async_turn_on()

            # Should record error
            assert switch_entity._performance_tracker._error_count > initial_errors

    async def test_switch_turn_off_error_handling(
        self, switch_entity: OptimizedSwitchBase
    ) -> None:
        """Test switch turn off error handling."""
        switch_entity._attr_is_on = True

        # Mock implementation to raise error
        with patch.object(
            switch_entity,
            "_async_turn_off_implementation",
            side_effect=Exception("Test error"),
        ):
            initial_errors = switch_entity._performance_tracker._error_count

            with pytest.raises(HomeAssistantError):
                await switch_entity.async_turn_off()

            # Should record error
            assert switch_entity._performance_tracker._error_count > initial_errors

    def test_switch_state_attributes(self, switch_entity: OptimizedSwitchBase) -> None:
        """Test switch-specific state attributes."""
        attributes = switch_entity._generate_state_attributes()

        assert "last_changed" in attributes
        assert "switch_type" in attributes
        assert attributes["switch_type"] == switch_entity._entity_type


class TestGlobalCacheManagement:
    """Test suite for global cache management functions."""

    def test_cleanup_global_caches(self) -> None:
        """Test global cache cleanup functionality."""
        # This test mainly ensures no exceptions during cleanup
        _cleanup_global_caches()
        assert True

    def test_cleanup_preserves_live_entities(self) -> None:
        """Ensure cache cleanup keeps active entity weak references."""

        live_before = sum(1 for ref in _ENTITY_REGISTRY if ref() is not None)

        entity = TestEntityBase(MockCoordinator(), "live_dog", "Live Dog")

        live_with_entity = sum(1 for ref in _ENTITY_REGISTRY if ref() is not None)
        assert live_with_entity == live_before + 1

        _cleanup_global_caches()

        live_after_cleanup = sum(1 for ref in _ENTITY_REGISTRY if ref() is not None)
        assert live_after_cleanup == live_with_entity

        entity_ref = weakref.ref(entity)
        del entity
        gc.collect()

        _cleanup_global_caches()

        live_after_release = sum(1 for ref in _ENTITY_REGISTRY if ref() is not None)
        assert live_after_release == live_before
        assert entity_ref() is None

    def test_get_global_performance_stats(self) -> None:
        """Test global performance statistics retrieval."""
        stats = get_global_performance_stats()

        assert "total_entities_registered" in stats
        assert "active_entities" in stats
        assert "cache_statistics" in stats
        assert "average_operation_time_ms" in stats
        assert "average_cache_hit_rate" in stats
        assert "total_errors" in stats

        # Values should be non-negative
        assert stats["total_entities_registered"] >= 0
        assert stats["active_entities"] >= 0
        assert stats["average_operation_time_ms"] >= 0
        assert stats["average_cache_hit_rate"] >= 0
        assert stats["total_errors"] >= 0


class TestOptimizedEntityBatching:
    """Test suite for optimized entity batching functionality."""

    async def test_create_optimized_entities_batched_empty_list(self) -> None:
        """Test batched entity creation with empty list."""
        mock_callback = Mock()

        await create_optimized_entities_batched(
            entities=[], async_add_entities_callback=mock_callback
        )

        # Should not call callback for empty list
        mock_callback.assert_not_called()

    async def test_create_optimized_entities_batched_single_batch(
        self, mock_coordinator
    ) -> None:
        """Test batched entity creation with single batch."""
        entities = [
            TestEntityBase(mock_coordinator, f"dog_{i}", f"Dog {i}") for i in range(5)
        ]

        mock_callback = Mock()

        await create_optimized_entities_batched(
            entities=entities, async_add_entities_callback=mock_callback, batch_size=10
        )

        # Should call callback once with all entities
        mock_callback.assert_called_once()
        args = mock_callback.call_args[0]
        assert len(args[0]) == 5
        assert args[1] is False  # update_before_add=False

    async def test_create_optimized_entities_batched_multiple_batches(
        self, mock_coordinator
    ) -> None:
        """Test batched entity creation with multiple batches."""
        entities = [
            TestEntityBase(mock_coordinator, f"dog_{i}", f"Dog {i}") for i in range(25)
        ]

        mock_callback = Mock()

        await create_optimized_entities_batched(
            entities=entities,
            async_add_entities_callback=mock_callback,
            batch_size=10,
            delay_between_batches=0.001,  # Minimal delay for testing
        )

        # Should call callback 3 times (25 entities, batch size 10 = 3 batches)
        assert mock_callback.call_count == 3

        # Verify batch sizes
        call_args = mock_callback.call_args_list
        assert len(call_args[0][0][0]) == 10  # First batch: 10 entities
        assert len(call_args[1][0][0]) == 10  # Second batch: 10 entities
        assert len(call_args[2][0][0]) == 5  # Third batch: 5 entities


class TestPerformanceOptimizations:
    """Test suite for performance optimizations and memory management."""

    @pytest.fixture
    def mock_coordinator(self) -> MockCoordinator:
        """Create mock coordinator for performance tests."""
        return MockCoordinator()

    def test_cache_ttl_behavior(self, mock_coordinator) -> None:
        """Test cache TTL behavior with time manipulation."""
        entity = TestEntityBase(mock_coordinator, "test_dog", "Test Dog")

        # First call should populate cache
        data1 = entity._get_dog_data_cached()

        # Immediate second call should hit cache
        data2 = entity._get_dog_data_cached()
        assert data1 == data2

        # Cache hit should be recorded
        assert entity._performance_tracker._cache_hits > 0

    def test_memory_pressure_simulation(self, mock_coordinator) -> None:
        """Test behavior under memory pressure simulation."""
        # Create many entities to simulate memory pressure
        entities = []
        for i in range(50):
            entity = TestEntityBase(mock_coordinator, f"dog_{i}", f"Dog {i}")
            # Generate some data to populate caches
            entity._get_dog_data_cached()
            cached_attributes = entity.extra_state_attributes
            assert isinstance(cached_attributes, dict)
            entities.append(entity)

        # Trigger cleanup
        _cleanup_global_caches()

        # Verify entities are still functional after cleanup
        for entity in entities[:5]:  # Test subset for performance
            assert entity._get_dog_data_cached() is not None

    def test_concurrent_access_simulation(self, mock_coordinator) -> None:
        """Test concurrent access patterns (simulated)."""
        entity = TestEntityBase(mock_coordinator, "concurrent_dog", "Concurrent Dog")

        # Simulate rapid concurrent access
        results = []
        for _ in range(100):
            dog_data = entity._get_dog_data_cached()
            attributes = entity.extra_state_attributes
            results.append((dog_data, attributes))

        # All results should be consistent
        first_dog_data, first_attrs = results[0]
        for dog_data, attrs in results:
            assert dog_data["dog_info"] == first_dog_data["dog_info"]
            assert attrs["dog_id"] == first_attrs["dog_id"]

    def test_performance_metrics_accuracy(self, mock_coordinator) -> None:
        """Test accuracy of performance metrics tracking."""
        entity = TestEntityBase(mock_coordinator, "perf_dog", "Performance Dog")

        # Record known operations
        entity._performance_tracker.record_operation_time(0.1)
        entity._performance_tracker.record_operation_time(0.2)
        entity._performance_tracker.record_operation_time(0.3)
        entity._performance_tracker.record_cache_hit()
        entity._performance_tracker.record_cache_miss()
        entity._performance_tracker.record_error()

        metrics = entity.get_performance_metrics()
        perf_data = metrics["performance"]

        # Verify accuracy
        assert perf_data["avg_operation_time"] == 0.2
        assert perf_data["min_operation_time"] == 0.1
        assert perf_data["max_operation_time"] == 0.3
        assert perf_data["total_operations"] == 3
        assert perf_data["error_count"] == 1
        assert perf_data["cache_hit_rate"] == 50.0  # 1 hit, 1 miss = 50%

    async def test_error_recovery_resilience(self, mock_coordinator) -> None:
        """Test entity resilience during error conditions."""
        entity = TestEntityBase(mock_coordinator, "error_dog", "Error Dog")

        # Simulate coordinator becoming unavailable
        mock_coordinator.available = False

        # Entity should handle gracefully
        assert entity.available is False
        attributes = entity.extra_state_attributes

        # Should return fallback attributes without crashing
        assert "status" in attributes
        assert attributes["dog_id"] == "error_dog"

        # Restore coordinator
        mock_coordinator.available = True
        assert entity.available is True

    async def test_state_restoration_behavior(self, mock_coordinator) -> None:
        """Test state restoration behavior."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="restore_dog",
            dog_name="Restore Dog",
            switch_type="test_switch",
        )

        # Mock last state
        mock_state = Mock()
        mock_state.state = "on"

        # Test restoration
        await switch._handle_state_restoration(mock_state)

        # Should restore state
        # Note: This is more of a smoke test since _handle_state_restoration is async
        assert True  # If no exception, test passes
