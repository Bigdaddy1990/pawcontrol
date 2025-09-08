"""Tests for PawControl batch manager.

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
from custom_components.pawcontrol.batch_manager import (
    FORCE_BATCH_INTERVAL,
    MAX_BATCH_SIZE,
    BatchManager,
)
from homeassistant.util import dt as dt_util


class TestBatchManager:
    """Test batch manager core functionality."""

    @pytest.fixture
    def batch_manager(self):
        """Create batch manager instance."""
        return BatchManager()

    @pytest.fixture
    def custom_batch_manager(self):
        """Create batch manager with custom size."""
        return BatchManager(max_batch_size=20)

    async def test_initialization(self, batch_manager):
        """Test batch manager initialization."""
        assert batch_manager._max_batch_size == MAX_BATCH_SIZE
        assert len(batch_manager._pending_updates) == 0
        assert batch_manager._last_batch_time is not None
        assert isinstance(batch_manager._update_lock, asyncio.Lock)

    async def test_custom_initialization(self, custom_batch_manager):
        """Test batch manager with custom size."""
        assert custom_batch_manager._max_batch_size == 20

    async def test_add_to_batch_single(self, batch_manager):
        """Test adding single dog to batch."""
        await batch_manager.add_to_batch("dog1", priority=1)
        
        assert await batch_manager.get_pending_count() == 1
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 1

    async def test_add_to_batch_multiple(self, batch_manager):
        """Test adding multiple dogs to batch."""
        await batch_manager.add_to_batch("dog1", priority=1)
        await batch_manager.add_to_batch("dog2", priority=3)
        await batch_manager.add_to_batch("dog3", priority=2)
        
        assert await batch_manager.get_pending_count() == 3
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 1
        assert pending["dog2"] == 3
        assert pending["dog3"] == 2

    async def test_add_to_batch_priority_update(self, batch_manager):
        """Test priority update when adding existing dog."""
        await batch_manager.add_to_batch("dog1", priority=1)
        await batch_manager.add_to_batch("dog1", priority=5)
        
        assert await batch_manager.get_pending_count() == 1
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 5

    async def test_add_to_batch_priority_keep_higher(self, batch_manager):
        """Test keeping higher priority when adding existing dog."""
        await batch_manager.add_to_batch("dog1", priority=5)
        await batch_manager.add_to_batch("dog1", priority=2)
        
        assert await batch_manager.get_pending_count() == 1
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 5

    async def test_add_to_batch_default_priority(self, batch_manager):
        """Test adding with default priority."""
        await batch_manager.add_to_batch("dog1")
        
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 0

    async def test_get_batch_priority_order(self, batch_manager):
        """Test getting batch in priority order."""
        await batch_manager.add_to_batch("dog1", priority=1)
        await batch_manager.add_to_batch("dog2", priority=5)
        await batch_manager.add_to_batch("dog3", priority=3)
        
        batch = await batch_manager.get_batch()
        
        # Should be in descending priority order
        assert batch == ["dog2", "dog3", "dog1"]
        assert await batch_manager.get_pending_count() == 0

    async def test_get_batch_max_size_limit(self, batch_manager):
        """Test batch size limitation."""
        # Add more dogs than max batch size
        for i in range(20):
            await batch_manager.add_to_batch(f"dog{i}", priority=i)
        
        batch = await batch_manager.get_batch()
        
        assert len(batch) == MAX_BATCH_SIZE
        assert await batch_manager.get_pending_count() == 20 - MAX_BATCH_SIZE

    async def test_get_batch_empty(self, batch_manager):
        """Test getting batch when empty."""
        batch = await batch_manager.get_batch()
        assert batch == []

    async def test_has_pending_true(self, batch_manager):
        """Test has_pending when updates exist."""
        await batch_manager.add_to_batch("dog1")
        assert await batch_manager.has_pending() is True

    async def test_has_pending_false(self, batch_manager):
        """Test has_pending when no updates."""
        assert await batch_manager.has_pending() is False

    async def test_should_batch_now_full_batch(self, batch_manager):
        """Test should_batch_now when batch is full."""
        # Fill to max batch size
        for i in range(MAX_BATCH_SIZE):
            await batch_manager.add_to_batch(f"dog{i}")
        
        assert await batch_manager.should_batch_now() is True

    async def test_should_batch_now_timeout(self, batch_manager):
        """Test should_batch_now after timeout."""
        await batch_manager.add_to_batch("dog1")
        
        # Mock time to simulate timeout
        with patch.object(dt_util, 'utcnow') as mock_now:
            future_time = batch_manager._last_batch_time + timedelta(seconds=FORCE_BATCH_INTERVAL + 1)
            mock_now.return_value = future_time
            
            assert await batch_manager.should_batch_now() is True

    async def test_should_batch_now_no_timeout(self, batch_manager):
        """Test should_batch_now before timeout."""
        await batch_manager.add_to_batch("dog1")
        assert await batch_manager.should_batch_now() is False

    async def test_should_batch_now_empty(self, batch_manager):
        """Test should_batch_now when empty."""
        assert await batch_manager.should_batch_now() is False

    async def test_should_batch_now_custom_interval(self, batch_manager):
        """Test should_batch_now with custom interval."""
        await batch_manager.add_to_batch("dog1")
        
        # Should not batch with longer interval
        assert await batch_manager.should_batch_now(3600) is False

    async def test_clear_pending(self, batch_manager):
        """Test clearing all pending updates."""
        await batch_manager.add_to_batch("dog1")
        await batch_manager.add_to_batch("dog2")
        await batch_manager.add_to_batch("dog3")
        
        count = await batch_manager.clear_pending()
        
        assert count == 3
        assert await batch_manager.get_pending_count() == 0
        assert await batch_manager.has_pending() is False

    async def test_clear_pending_empty(self, batch_manager):
        """Test clearing when already empty."""
        count = await batch_manager.clear_pending()
        assert count == 0

    async def test_remove_from_batch_existing(self, batch_manager):
        """Test removing existing dog from batch."""
        await batch_manager.add_to_batch("dog1")
        await batch_manager.add_to_batch("dog2")
        
        result = await batch_manager.remove_from_batch("dog1")
        
        assert result is True
        assert await batch_manager.get_pending_count() == 1
        pending = await batch_manager.get_pending_with_priorities()
        assert "dog1" not in pending
        assert "dog2" in pending

    async def test_remove_from_batch_nonexistent(self, batch_manager):
        """Test removing non-existent dog from batch."""
        await batch_manager.add_to_batch("dog1")
        
        result = await batch_manager.remove_from_batch("dog2")
        
        assert result is False
        assert await batch_manager.get_pending_count() == 1

    async def test_update_priority_existing(self, batch_manager):
        """Test updating priority for existing dog."""
        await batch_manager.add_to_batch("dog1", priority=1)
        
        result = await batch_manager.update_priority("dog1", 10)
        
        assert result is True
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 10

    async def test_update_priority_nonexistent(self, batch_manager):
        """Test updating priority for non-existent dog."""
        result = await batch_manager.update_priority("dog1", 10)
        assert result is False

    async def test_get_stats_empty(self, batch_manager):
        """Test getting stats when empty."""
        stats = batch_manager.get_stats()
        
        assert stats["max_batch_size"] == MAX_BATCH_SIZE
        assert stats["pending_updates"] == 0
        assert stats["force_interval"] == FORCE_BATCH_INTERVAL
        assert stats["pending_breakdown"] == {}
        assert "last_batch_seconds_ago" in stats

    async def test_get_stats_with_pending(self, batch_manager):
        """Test getting stats with pending updates."""
        await batch_manager.add_to_batch("dog1", priority=1)
        await batch_manager.add_to_batch("dog2", priority=3)
        
        stats = batch_manager.get_stats()
        
        assert stats["pending_updates"] == 2
        assert stats["pending_breakdown"] == {"dog1": 1, "dog2": 3}

    async def test_get_next_batch_time_empty(self, batch_manager):
        """Test next batch time when empty."""
        next_time = await batch_manager.get_next_batch_time()
        
        # Should be far in future when no pending updates
        assert next_time > dt_util.utcnow() + timedelta(minutes=30)

    async def test_get_next_batch_time_full_batch(self, batch_manager):
        """Test next batch time when batch is full."""
        # Fill to max batch size
        for i in range(MAX_BATCH_SIZE):
            await batch_manager.add_to_batch(f"dog{i}")
        
        next_time = await batch_manager.get_next_batch_time()
        
        # Should be immediate when batch is full
        assert next_time <= dt_util.utcnow() + timedelta(seconds=1)

    async def test_get_next_batch_time_partial_batch(self, batch_manager):
        """Test next batch time with partial batch."""
        await batch_manager.add_to_batch("dog1")
        
        next_time = await batch_manager.get_next_batch_time()
        expected_time = batch_manager._last_batch_time + timedelta(seconds=FORCE_BATCH_INTERVAL)
        
        # Should be based on force interval
        assert abs((next_time - expected_time).total_seconds()) < 1


class TestBatchManagerOptimization:
    """Test batch manager optimization features."""

    @pytest.fixture
    def batch_manager(self):
        """Create batch manager instance."""
        return BatchManager()

    async def test_optimize_batching_high_load(self, batch_manager):
        """Test optimization with high load."""
        # Add many pending updates
        for i in range(35):
            await batch_manager.add_to_batch(f"dog{i}")
        
        result = await batch_manager.optimize_batching()
        
        assert result["optimization_performed"] is True
        assert result["new_batch_size"] > result["old_batch_size"]
        assert result["current_load"] == 35
        assert "high load" in result["recommendation"].lower()

    async def test_optimize_batching_low_load(self, batch_manager):
        """Test optimization with low load."""
        # Add few pending updates
        for i in range(3):
            await batch_manager.add_to_batch(f"dog{i}")
        
        result = await batch_manager.optimize_batching()
        
        assert result["optimization_performed"] is True
        assert result["new_batch_size"] < result["old_batch_size"]
        assert result["current_load"] == 3
        assert "low load" in result["recommendation"].lower()

    async def test_optimize_batching_normal_load(self, batch_manager):
        """Test optimization with normal load."""
        # Add normal amount of pending updates
        for i in range(15):
            await batch_manager.add_to_batch(f"dog{i}")
        
        result = await batch_manager.optimize_batching()
        
        assert result["current_load"] == 15
        assert "normal load" in result["recommendation"].lower()

    async def test_optimize_batching_no_load(self, batch_manager):
        """Test optimization with no load."""
        result = await batch_manager.optimize_batching()
        
        assert result["current_load"] == 0
        assert "no load" in result["recommendation"].lower()

    async def test_optimize_batching_limits(self, batch_manager):
        """Test optimization respects limits."""
        # Start with minimum size
        batch_manager._max_batch_size = 10
        
        # Add very few updates to force decrease
        await batch_manager.optimize_batching()
        
        # Should not go below 10
        assert batch_manager._max_batch_size >= 10

    async def test_load_recommendation_very_high(self, batch_manager):
        """Test load recommendation for very high load."""
        recommendation = batch_manager._get_load_recommendation(60)
        assert "very high load" in recommendation.lower()

    async def test_load_recommendation_high(self, batch_manager):
        """Test load recommendation for high load."""
        recommendation = batch_manager._get_load_recommendation(25)
        assert "high load" in recommendation.lower()

    async def test_load_recommendation_normal(self, batch_manager):
        """Test load recommendation for normal load."""
        recommendation = batch_manager._get_load_recommendation(15)
        assert "normal load" in recommendation.lower()

    async def test_load_recommendation_low(self, batch_manager):
        """Test load recommendation for low load."""
        recommendation = batch_manager._get_load_recommendation(5)
        assert "low load" in recommendation.lower()

    async def test_load_recommendation_none(self, batch_manager):
        """Test load recommendation for no load."""
        recommendation = batch_manager._get_load_recommendation(0)
        assert "no load" in recommendation.lower()


class TestBatchManagerConcurrency:
    """Test batch manager concurrency and thread safety."""

    @pytest.fixture
    def batch_manager(self):
        """Create batch manager instance."""
        return BatchManager()

    async def test_concurrent_add_to_batch(self, batch_manager):
        """Test concurrent add_to_batch operations."""
        async def add_dogs(start_id: int, count: int):
            for i in range(count):
                await batch_manager.add_to_batch(f"dog{start_id + i}", priority=i)

        # Run concurrent adds
        await asyncio.gather(
            add_dogs(0, 10),
            add_dogs(10, 10),
            add_dogs(20, 10),
        )
        
        assert await batch_manager.get_pending_count() == 30

    async def test_concurrent_get_batch(self, batch_manager):
        """Test concurrent get_batch operations."""
        # Add some dogs
        for i in range(10):
            await batch_manager.add_to_batch(f"dog{i}", priority=i)
        
        # Get batches concurrently
        batch1, batch2 = await asyncio.gather(
            batch_manager.get_batch(),
            batch_manager.get_batch(),
        )
        
        # Only one should get the batch, other should be empty
        total_dogs = len(batch1) + len(batch2)
        assert total_dogs == 10
        assert len(batch1) == 10 and len(batch2) == 0 or len(batch1) == 0 and len(batch2) == 10

    async def test_concurrent_mixed_operations(self, batch_manager):
        """Test mixed concurrent operations."""
        async def add_operation():
            for i in range(5):
                await batch_manager.add_to_batch(f"add_{i}")

        async def remove_operation():
            for i in range(3):
                await batch_manager.remove_from_batch(f"add_{i}")

        async def get_operation():
            return await batch_manager.get_batch()

        # Add initial dogs
        for i in range(5):
            await batch_manager.add_to_batch(f"initial_{i}")

        # Run mixed operations
        results = await asyncio.gather(
            add_operation(),
            remove_operation(),
            get_operation(),
            return_exceptions=True
        )
        
        # Should not raise exceptions
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent operation failed: {result}")

    async def test_lock_acquisition_timeout(self, batch_manager):
        """Test that operations don't deadlock."""
        # This is more of a smoke test to ensure no obvious deadlocks
        async def long_operation():
            async with batch_manager._update_lock:
                await asyncio.sleep(0.01)  # Simulate work
                await batch_manager.add_to_batch("test_dog")

        async def quick_operation():
            await batch_manager.has_pending()

        # Should complete without hanging
        await asyncio.wait_for(
            asyncio.gather(long_operation(), quick_operation()),
            timeout=1.0
        )


class TestBatchManagerEdgeCases:
    """Test batch manager edge cases and error handling."""

    @pytest.fixture
    def batch_manager(self):
        """Create batch manager instance."""
        return BatchManager()

    async def test_empty_dog_id(self, batch_manager):
        """Test handling empty dog ID."""
        await batch_manager.add_to_batch("", priority=1)
        
        assert await batch_manager.get_pending_count() == 1
        pending = await batch_manager.get_pending_with_priorities()
        assert "" in pending

    async def test_none_dog_id(self, batch_manager):
        """Test handling None dog ID."""
        # This would normally be a type error, but test robustness
        with pytest.raises(TypeError):
            await batch_manager.add_to_batch(None, priority=1)

    async def test_negative_priority(self, batch_manager):
        """Test negative priority handling."""
        await batch_manager.add_to_batch("dog1", priority=-5)
        
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == -5

    async def test_very_high_priority(self, batch_manager):
        """Test very high priority handling."""
        await batch_manager.add_to_batch("dog1", priority=999999)
        
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 999999

    async def test_zero_max_batch_size(self):
        """Test zero max batch size."""
        batch_manager = BatchManager(max_batch_size=0)
        await batch_manager.add_to_batch("dog1")
        
        batch = await batch_manager.get_batch()
        assert batch == []  # Should handle gracefully

    async def test_negative_max_batch_size(self):
        """Test negative max batch size."""
        batch_manager = BatchManager(max_batch_size=-1)
        await batch_manager.add_to_batch("dog1")
        
        batch = await batch_manager.get_batch()
        assert batch == []  # Should handle gracefully

    async def test_huge_batch_size(self):
        """Test very large batch size."""
        batch_manager = BatchManager(max_batch_size=10000)
        
        # Add many dogs
        for i in range(1000):
            await batch_manager.add_to_batch(f"dog{i}")
        
        batch = await batch_manager.get_batch()
        assert len(batch) == 1000  # Should handle large batches

    async def test_stats_calculation_edge_cases(self, batch_manager):
        """Test stats calculation with edge cases."""
        # Test with very recent batch
        with patch.object(batch_manager, '_last_batch_time', dt_util.utcnow()):
            stats = batch_manager.get_stats()
            assert stats["last_batch_seconds_ago"] >= 0
            assert stats["last_batch_seconds_ago"] < 1

    async def test_rapid_priority_updates(self, batch_manager):
        """Test rapid priority updates on same dog."""
        await batch_manager.add_to_batch("dog1", priority=1)
        
        for priority in range(2, 100):
            await batch_manager.add_to_batch("dog1", priority=priority)
        
        pending = await batch_manager.get_pending_with_priorities()
        assert pending["dog1"] == 99

    async def test_batch_time_calculation_edge_cases(self, batch_manager):
        """Test edge cases in batch time calculations."""
        # Test with future last_batch_time (should not happen but test robustness)
        future_time = dt_util.utcnow() + timedelta(hours=1)
        
        with patch.object(batch_manager, '_last_batch_time', future_time):
            # Should handle gracefully without errors
            result = await batch_manager.should_batch_now()
            assert isinstance(result, bool)
            
            next_time = await batch_manager.get_next_batch_time()
            assert isinstance(next_time, datetime)


class TestBatchManagerPerformance:
    """Test batch manager performance characteristics."""

    @pytest.fixture
    def batch_manager(self):
        """Create batch manager instance."""
        return BatchManager()

    async def test_large_scale_operations(self, batch_manager):
        """Test performance with large number of operations."""
        import time
        
        start_time = time.time()
        
        # Add large number of dogs
        for i in range(1000):
            await batch_manager.add_to_batch(f"dog{i}", priority=i % 10)
        
        add_time = time.time() - start_time
        
        start_time = time.time()
        
        # Get multiple batches
        total_retrieved = 0
        while await batch_manager.has_pending():
            batch = await batch_manager.get_batch()
            total_retrieved += len(batch)
        
        get_time = time.time() - start_time
        
        assert total_retrieved == 1000
        # Performance assertions (should be fast)
        assert add_time < 1.0  # Adding 1000 items should take < 1 second
        assert get_time < 1.0   # Getting all batches should take < 1 second

    async def test_memory_usage_stability(self, batch_manager):
        """Test that memory usage remains stable."""
        import gc
        
        # Perform many operations to test for memory leaks
        for cycle in range(10):
            # Add many dogs
            for i in range(100):
                await batch_manager.add_to_batch(f"cycle{cycle}_dog{i}")
            
            # Remove them all
            while await batch_manager.has_pending():
                await batch_manager.get_batch()
            
            # Force garbage collection
            gc.collect()
        
        # Should complete without memory issues
        assert await batch_manager.get_pending_count() == 0

    async def test_concurrent_performance(self, batch_manager):
        """Test performance under concurrent load."""
        import time
        
        async def worker(worker_id: int):
            for i in range(50):
                await batch_manager.add_to_batch(f"worker{worker_id}_dog{i}")
                if i % 10 == 0:
                    await batch_manager.get_batch()
        
        start_time = time.time()
        
        # Run 10 concurrent workers
        await asyncio.gather(*[worker(i) for i in range(10)])
        
        elapsed = time.time() - start_time
        
        # Should complete reasonably quickly under concurrent load
        assert elapsed < 5.0  # 10 workers should complete in < 5 seconds


@pytest.mark.asyncio
class TestBatchManagerIntegration:
    """Integration tests for batch manager."""

    async def test_realistic_workflow(self):
        """Test realistic batch manager workflow."""
        batch_manager = BatchManager(max_batch_size=5)
        
        # Simulate realistic usage pattern
        # 1. Add some high priority updates
        await batch_manager.add_to_batch("emergency_dog", priority=10)
        await batch_manager.add_to_batch("sick_dog", priority=8)
        
        # 2. Add regular updates
        for i in range(10):
            await batch_manager.add_to_batch(f"regular_dog_{i}", priority=1)
        
        # 3. Process first batch (should get high priority first)
        batch1 = await batch_manager.get_batch()
        assert "emergency_dog" in batch1
        assert "sick_dog" in batch1
        assert len(batch1) == 5
        
        # 4. Add more urgent update
        await batch_manager.add_to_batch("new_emergency", priority=15)
        
        # 5. Process second batch (should get new emergency first)
        batch2 = await batch_manager.get_batch()
        assert "new_emergency" in batch2[0]  # Should be first due to highest priority
        
        # 6. Continue until all processed
        remaining = []
        while await batch_manager.has_pending():
            batch = await batch_manager.get_batch()
            remaining.extend(batch)
        
        # All dogs should be processed
        total_processed = len(batch1) + len(batch2) + len(remaining)
        assert total_processed == 13  # 2 + 10 + 1

    async def test_optimization_during_operation(self):
        """Test optimization during normal operation."""
        batch_manager = BatchManager()
        
        # Start with normal load
        for i in range(10):
            await batch_manager.add_to_batch(f"dog{i}")
        
        # Check optimization
        result1 = await batch_manager.optimize_batching()
        old_size = result1["new_batch_size"]
        
        # Increase load significantly
        for i in range(40):
            await batch_manager.add_to_batch(f"heavy_dog{i}")
        
        # Should optimize for higher load
        result2 = await batch_manager.optimize_batching()
        new_size = result2["new_batch_size"]
        
        assert new_size > old_size  # Should increase batch size for higher load
        
        # Process all with optimized settings
        total_processed = 0
        while await batch_manager.has_pending():
            batch = await batch_manager.get_batch()
            total_processed += len(batch)
        
        assert total_processed == 50  # All dogs processed

    async def test_error_recovery(self):
        """Test error recovery scenarios."""
        batch_manager = BatchManager()
        
        # Add some dogs
        for i in range(5):
            await batch_manager.add_to_batch(f"dog{i}")
        
        # Simulate error during batch processing
        try:
            # Force an error by manipulating internal state
            original_pending = batch_manager._pending_updates.copy()
            batch_manager._pending_updates = None  # This would cause an error
            
            with pytest.raises((TypeError, AttributeError)):
                await batch_manager.get_batch()
                
        finally:
            # Restore state
            batch_manager._pending_updates = original_pending
        
        # Should still be able to operate
        assert await batch_manager.has_pending() is True
        batch = await batch_manager.get_batch()
        assert len(batch) == 5
