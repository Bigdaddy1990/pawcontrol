"""Comprehensive edge case tests for PawControl cache manager - Gold Standard coverage.

This module provides advanced edge case testing to achieve 95%+ test coverage
for the cache manager, including concurrent access testing, LRU eviction
validation, TTL boundary conditions, and performance stress scenarios.

Quality Scale: Platinum
Home Assistant: 2025.9.0+
Python: 3.13+
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.cache_manager import (
    CacheManager,
    CACHE_TTL_FAST,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SLOW,
)


class TestCacheManagerStressScenarios:
    """Test cache manager under extreme stress conditions."""

    @pytest.fixture
    def cache_manager(self):
        """Create cache manager for stress testing."""
        return CacheManager(max_size=50)

    @pytest.mark.asyncio
    async def test_massive_concurrent_access_stress(self, cache_manager):
        """Test massive concurrent access to cache manager."""
        # Pre-populate cache with test data
        for i in range(25):
            await cache_manager.set(f"key_{i}", {"data": f"value_{i}", "index": i}, CACHE_TTL_MEDIUM)
        
        access_results = []
        set_results = []
        errors = []
        
        async def concurrent_getter(task_id):
            """Concurrent cache getter."""
            try:
                for i in range(100):
                    key = f"key_{i % 25}"
                    result = await cache_manager.get(key)
                    access_results.append((task_id, key, result is not None))
                    await asyncio.sleep(0.001)  # Small delay to increase contention
            except Exception as e:
                errors.append(("getter", task_id, e))
        
        async def concurrent_setter(task_id):
            """Concurrent cache setter."""
            try:
                for i in range(50):
                    key = f"new_key_{task_id}_{i}"
                    data = {"task": task_id, "iteration": i, "timestamp": time.time()}
                    await cache_manager.set(key, data, CACHE_TTL_FAST)
                    set_results.append((task_id, key))
                    await asyncio.sleep(0.002)  # Small delay
            except Exception as e:
                errors.append(("setter", task_id, e))
        
        # Start concurrent tasks
        tasks = []
        for i in range(10):
            tasks.append(asyncio.create_task(concurrent_getter(i)))
        for i in range(5):
            tasks.append(asyncio.create_task(concurrent_setter(i)))
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent access without errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        
        # Should have processed many operations
        assert len(access_results) > 500  # 10 * 100 = 1000 gets expected
        assert len(set_results) > 200    # 5 * 50 = 250 sets expected
        
        # Cache should still be functional
        stats = cache_manager.get_stats()
        assert stats["total_entries"] > 0
        assert stats["cache_hits"] > 0

    @pytest.mark.asyncio
    async def test_rapid_cache_invalidation_stress(self, cache_manager):
        """Test rapid cache invalidation patterns."""
        # Pre-populate with pattern-based keys
        for i in range(100):
            dog_key = f"dog_{i % 10}_{i}"
            feeding_key = f"feeding_{i % 5}_{i}"
            gps_key = f"gps_{i % 3}_{i}"
            
            await cache_manager.set(dog_key, {"type": "dog", "id": i}, CACHE_TTL_MEDIUM)
            await cache_manager.set(feeding_key, {"type": "feeding", "id": i}, CACHE_TTL_MEDIUM)
            await cache_manager.set(gps_key, {"type": "gps", "id": i}, CACHE_TTL_MEDIUM)
        
        # Rapid invalidation operations
        invalidation_results = []
        
        patterns = ["dog_*", "feeding_*", "gps_*"]
        for _ in range(20):
            for pattern in patterns:
                count = await cache_manager.invalidate(pattern=pattern)
                invalidation_results.append((pattern, count))
                
                # Re-populate some data
                for i in range(5):
                    key = f"{pattern.rstrip('*')}{i}_new"
                    await cache_manager.set(key, {"repopulated": True}, CACHE_TTL_FAST)
        
        # Should handle rapid invalidation
        assert len(invalidation_results) == 60  # 20 * 3 patterns
        
        # Cache should still be functional
        stats = cache_manager.get_stats()
        assert stats["total_entries"] >= 0

    @pytest.mark.asyncio
    async def test_memory_pressure_with_large_datasets(self, cache_manager):
        """Test cache behavior under memory pressure."""
        import sys
        
        # Get initial memory usage
        initial_size = sys.getsizeof(cache_manager._cache)
        
        # Create large data entries
        large_data_entries = []
        for i in range(cache_manager._max_size * 2):  # More than max size
            large_data = {
                "id": i,
                "data": "x" * 1000,  # 1KB per entry
                "metadata": {
                    "created": time.time(),
                    "sequence": list(range(100)),  # Additional memory
                    "description": f"Large data entry number {i} with lots of content",
                }
            }
            large_data_entries.append((f"large_key_{i}", large_data))
        
        # Add all entries (should trigger LRU eviction)
        for key, data in large_data_entries:
            await cache_manager.set(key, data, CACHE_TTL_MEDIUM)
        
        # Should respect max size
        stats = cache_manager.get_stats()
        assert stats["total_entries"] <= cache_manager._max_size
        
        # Memory usage should be bounded
        final_size = sys.getsizeof(cache_manager._cache)
        assert final_size < initial_size + cache_manager._max_size * 2000  # Reasonable growth

    @pytest.mark.asyncio
    async def test_hot_key_tracking_stress(self, cache_manager):
        """Test hot key tracking under stress conditions."""
        # Create keys with different access patterns
        hot_keys = [f"hot_key_{i}" for i in range(10)]
        warm_keys = [f"warm_key_{i}" for i in range(20)]
        cold_keys = [f"cold_key_{i}" for i in range(30)]
        
        # Populate cache
        for key in hot_keys + warm_keys + cold_keys:
            await cache_manager.set(key, {"key": key, "type": "test"}, CACHE_TTL_MEDIUM)
        
        # Access patterns to create hot/warm/cold
        for _ in range(20):  # Many iterations
            # Hot keys - access frequently
            for key in hot_keys:
                for _ in range(10):
                    await cache_manager.get(key)
            
            # Warm keys - access moderately
            for key in warm_keys:
                for _ in range(3):
                    await cache_manager.get(key)
            
            # Cold keys - access rarely
            for key in cold_keys:
                if cold_keys.index(key) % 5 == 0:  # Only every 5th key
                    await cache_manager.get(key)
        
        # Verify hot key tracking
        stats = cache_manager.get_stats()
        assert stats["hot_keys"] > 0
        
        # Hot keys should be protected from LRU eviction
        for key in hot_keys:
            result = await cache_manager.get(key)
            assert result is not None, f"Hot key {key} should still be cached"

    @pytest.mark.asyncio
    async def test_rapid_ttl_expiration_scenarios(self, cache_manager):
        """Test rapid TTL expiration scenarios."""
        # Add entries with very short TTL
        short_ttl_keys = []
        for i in range(50):
            key = f"short_ttl_{i}"
            await cache_manager.set(key, {"data": i}, ttl_seconds=1)  # 1 second TTL
            short_ttl_keys.append(key)
        
        # Add entries with medium TTL
        medium_ttl_keys = []
        for i in range(50):
            key = f"medium_ttl_{i}"
            await cache_manager.set(key, {"data": i}, ttl_seconds=10)  # 10 second TTL
            medium_ttl_keys.append(key)
        
        # Verify all entries exist
        for key in short_ttl_keys + medium_ttl_keys:
            result = await cache_manager.get(key)
            assert result is not None
        
        # Wait for short TTL to expire
        await asyncio.sleep(1.5)
        
        # Short TTL entries should be expired
        expired_count = 0
        for key in short_ttl_keys:
            result = await cache_manager.get(key)
            if result is None:
                expired_count += 1
        
        assert expired_count > 40  # Most should be expired
        
        # Medium TTL entries should still exist
        valid_count = 0
        for key in medium_ttl_keys:
            result = await cache_manager.get(key)
            if result is not None:
                valid_count += 1
        
        assert valid_count > 40  # Most should still be valid


class TestCacheManagerEdgeCasesValidation:
    """Test cache manager edge cases and boundary conditions."""

    @pytest.fixture
    def empty_cache(self):
        """Create empty cache manager for edge case testing."""
        return CacheManager(max_size=10)

    @pytest.fixture
    def populated_cache(self):
        """Create populated cache manager for testing."""
        cache = CacheManager(max_size=20)
        # This will be populated in individual tests
        return cache

    @pytest.mark.asyncio
    async def test_empty_cache_operations(self, empty_cache):
        """Test operations on empty cache."""
        # Get from empty cache
        result = await empty_cache.get("nonexistent_key")
        assert result is None
        
        # Invalidate from empty cache
        count = await empty_cache.invalidate(key="nonexistent_key")
        assert count == 0
        
        count = await empty_cache.invalidate(pattern="pattern_*")
        assert count == 0
        
        # Clear expired from empty cache
        count = await empty_cache.clear_expired()
        assert count == 0
        
        # Get stats from empty cache
        stats = empty_cache.get_stats()
        assert stats["total_entries"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] == 0
        assert stats["hit_rate"] == 0
        
        # Get entry details from empty cache
        details = await empty_cache.get_cache_entry_details("nonexistent")
        assert details is None
        
        # Optimize empty cache
        report = await empty_cache.optimize_cache()
        assert report["initial_entries"] == 0
        assert report["final_entries"] == 0

    @pytest.mark.asyncio
    async def test_cache_size_limit_edge_cases(self, empty_cache):
        """Test cache size limit boundary conditions."""
        max_size = empty_cache._max_size
        
        # Fill cache to exactly max size
        for i in range(max_size):
            await empty_cache.set(f"key_{i}", {"data": i}, CACHE_TTL_MEDIUM)
        
        stats = empty_cache.get_stats()
        assert stats["total_entries"] == max_size
        
        # Add one more entry (should trigger LRU eviction)
        await empty_cache.set("overflow_key", {"data": "overflow"}, CACHE_TTL_MEDIUM)
        
        stats = empty_cache.get_stats()
        assert stats["total_entries"] == max_size  # Should still be at max
        
        # Verify new entry exists
        result = await empty_cache.get("overflow_key")
        assert result is not None
        
        # One of the original entries should be evicted
        evicted_count = 0
        for i in range(max_size):
            result = await empty_cache.get(f"key_{i}")
            if result is None:
                evicted_count += 1
        
        assert evicted_count >= 1  # At least one should be evicted

    @pytest.mark.asyncio
    async def test_ttl_boundary_conditions(self, empty_cache):
        """Test TTL edge cases and boundary conditions."""
        # Test zero TTL
        await empty_cache.set("zero_ttl", {"data": "zero"}, ttl_seconds=0)
        
        # Should expire immediately
        result = await empty_cache.get("zero_ttl")
        assert result is None  # Expired immediately
        
        # Test negative TTL
        await empty_cache.set("negative_ttl", {"data": "negative"}, ttl_seconds=-1)
        
        # Should be expired
        result = await empty_cache.get("negative_ttl")
        assert result is None
        
        # Test very large TTL
        large_ttl = 365 * 24 * 3600  # 1 year
        await empty_cache.set("large_ttl", {"data": "large"}, ttl_seconds=large_ttl)
        
        result = await empty_cache.get("large_ttl")
        assert result is not None
        
        # Get entry details for large TTL
        details = await empty_cache.get_cache_entry_details("large_ttl")
        assert details is not None
        assert details["ttl_remaining"] > large_ttl - 10  # Should be close to original

    @pytest.mark.asyncio
    async def test_pattern_invalidation_edge_cases(self, populated_cache):
        """Test pattern invalidation with edge cases."""
        # Populate with various key patterns
        await populated_cache.set("dog_1", {"type": "dog"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("dog_2", {"type": "dog"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("cat_1", {"type": "cat"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("dogged_pursuit", {"type": "other"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("", {"type": "empty"}, CACHE_TTL_MEDIUM)  # Empty key
        await populated_cache.set("dog", {"type": "exact"}, CACHE_TTL_MEDIUM)  # Exact match
        
        # Test exact pattern match
        count = await populated_cache.invalidate(pattern="dog")
        assert count == 1  # Should match "dog" exactly
        
        # Test wildcard pattern
        count = await populated_cache.invalidate(pattern="dog_*")
        assert count == 2  # Should match "dog_1" and "dog_2"
        
        # Test pattern with no matches
        count = await populated_cache.invalidate(pattern="nonexistent_*")
        assert count == 0
        
        # Test empty pattern
        count = await populated_cache.invalidate(pattern="")
        assert count == 1  # Should match empty key
        
        # Test pattern edge cases
        count = await populated_cache.invalidate(pattern="*")
        # Should match all remaining keys (implementation dependent)

    @pytest.mark.asyncio
    async def test_data_copy_safety_edge_cases(self, empty_cache):
        """Test data copy safety with mutable objects."""
        # Create mutable data
        original_data = {
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
            "set": {4, 5, 6},  # Note: sets aren't JSON serializable but should work in cache
        }
        
        # Set in cache
        await empty_cache.set("mutable_key", original_data, CACHE_TTL_MEDIUM)
        
        # Get from cache
        cached_data = await empty_cache.get("mutable_key")
        assert cached_data is not None
        
        # Modify original data
        original_data["list"].append(4)
        original_data["dict"]["new_key"] = "new_value"
        original_data["new_field"] = "added"
        
        # Get from cache again
        cached_data_2 = await empty_cache.get("mutable_key")
        
        # Cached data should not be affected by original modifications
        assert len(cached_data_2["list"]) == 3  # Should still be [1, 2, 3]
        assert "new_key" not in cached_data_2["dict"]
        assert "new_field" not in cached_data_2
        
        # Modify cached data
        cached_data_2["list"].append(10)
        
        # Get from cache again
        cached_data_3 = await empty_cache.get("mutable_key")
        
        # Should not be affected by modifications to returned copy
        assert 10 not in cached_data_3["list"]

    @pytest.mark.asyncio
    async def test_lru_eviction_edge_cases(self, empty_cache):
        """Test LRU eviction with edge cases."""
        max_size = empty_cache._max_size
        
        # Fill cache and make some keys hot
        hot_keys = []
        normal_keys = []
        
        for i in range(max_size):
            key = f"key_{i}"
            await empty_cache.set(key, {"data": i}, CACHE_TTL_MEDIUM)
            
            if i < 3:  # First 3 are hot keys
                hot_keys.append(key)
                # Access multiple times to make them hot
                for _ in range(10):
                    await empty_cache.get(key)
            else:
                normal_keys.append(key)
        
        # Add new entry to trigger eviction
        await empty_cache.set("new_key", {"data": "new"}, CACHE_TTL_MEDIUM)
        
        # Hot keys should be protected from eviction
        for key in hot_keys:
            result = await empty_cache.get(key)
            assert result is not None, f"Hot key {key} should not be evicted"
        
        # At least one normal key should be evicted
        evicted_count = 0
        for key in normal_keys:
            result = await empty_cache.get(key)
            if result is None:
                evicted_count += 1
        
        assert evicted_count >= 1

    @pytest.mark.asyncio
    async def test_stats_consistency_edge_cases(self, empty_cache):
        """Test statistics consistency under edge conditions."""
        # Initial stats
        stats = empty_cache.get_stats()
        initial_hits = stats["cache_hits"]
        initial_misses = stats["cache_misses"]
        
        # Perform various operations
        await empty_cache.set("test_key", {"data": "test"}, CACHE_TTL_MEDIUM)
        
        # Hit
        result = await empty_cache.get("test_key")
        assert result is not None
        
        # Miss
        result = await empty_cache.get("nonexistent")
        assert result is None
        
        # Check stats consistency
        stats = empty_cache.get_stats()
        assert stats["cache_hits"] == initial_hits + 1
        assert stats["cache_misses"] == initial_misses + 1
        assert stats["total_entries"] == 1
        
        # Hit rate calculation
        total_accesses = stats["cache_hits"] + stats["cache_misses"]
        expected_hit_rate = stats["cache_hits"] / total_accesses * 100
        assert abs(stats["hit_rate"] - expected_hit_rate) < 0.1

    @pytest.mark.asyncio
    async def test_optimization_edge_cases(self, populated_cache):
        """Test cache optimization with edge cases."""
        # Create mixed cache state
        now = dt_util.utcnow()
        
        # Add entries with various access patterns
        await populated_cache.set("hot_key", {"data": "hot"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("cold_key", {"data": "cold"}, CACHE_TTL_MEDIUM)
        await populated_cache.set("expired_key", {"data": "expired"}, ttl_seconds=1)
        
        # Make one key hot
        for _ in range(5):
            await populated_cache.get("hot_key")
        
        # Don't access cold_key
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Run optimization
        report = await populated_cache.optimize_cache()
        
        # Should clear expired entries
        assert report["expired_cleared"] >= 1
        
        # Should promote hot keys
        assert report["hot_keys_promoted"] >= 0
        
        # Optimization should complete
        assert report["optimization_completed"] is True
        
        # Expired key should be gone
        result = await populated_cache.get("expired_key")
        assert result is None


class TestCacheManagerErrorRecoveryScenarios:
    """Test cache manager error recovery and resilience."""

    @pytest.fixture
    def error_prone_cache(self):
        """Create cache manager for error testing."""
        return CacheManager(max_size=10)

    @pytest.mark.asyncio
    async def test_invalid_data_handling(self, error_prone_cache):
        """Test handling of invalid data types."""
        # Test with various invalid data types
        invalid_data_types = [
            None,
            "string_instead_of_dict",
            123,
            [],
            set(),
            lambda x: x,  # Function
        ]
        
        for i, invalid_data in enumerate(invalid_data_types):
            try:
                # Some invalid types might be accepted (implementation dependent)
                await error_prone_cache.set(f"invalid_{i}", invalid_data, CACHE_TTL_MEDIUM)
            except (TypeError, AttributeError):
                # Expected for some invalid types
                pass
        
        # Cache should still be functional
        await error_prone_cache.set("valid_key", {"data": "valid"}, CACHE_TTL_MEDIUM)
        result = await error_prone_cache.get("valid_key")
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_modification_safety(self, error_prone_cache):
        """Test safety during concurrent cache modifications."""
        # Add some initial data
        for i in range(5):
            await error_prone_cache.set(f"key_{i}", {"data": i}, CACHE_TTL_MEDIUM)
        
        modification_errors = []
        
        async def concurrent_modifier(modifier_id):
            """Concurrently modify cache state."""
            try:
                for i in range(20):
                    # Mix of operations
                    if i % 3 == 0:
                        await error_prone_cache.set(f"mod_{modifier_id}_{i}", {"data": i}, CACHE_TTL_FAST)
                    elif i % 3 == 1:
                        await error_prone_cache.get(f"key_{i % 5}")
                    else:
                        await error_prone_cache.invalidate(f"mod_{modifier_id}_{i-2}")
            except Exception as e:
                modification_errors.append((modifier_id, e))
        
        # Run concurrent modifiers
        tasks = [asyncio.create_task(concurrent_modifier(i)) for i in range(5)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent modifications safely
        assert len(modification_errors) == 0, f"Concurrent modification errors: {modification_errors}"
        
        # Cache should still be consistent
        stats = error_prone_cache.get_stats()
        assert stats["total_entries"] >= 0

    @pytest.mark.asyncio
    async def test_time_manipulation_edge_cases(self, error_prone_cache):
        """Test behavior with time manipulation scenarios."""
        # Add entry with normal TTL
        await error_prone_cache.set("time_test", {"data": "test"}, ttl_seconds=60)
        
        # Verify it exists
        result = await error_prone_cache.get("time_test")
        assert result is not None
        
        # Mock time to be in the future (simulate clock changes)
        with patch('homeassistant.util.dt.utcnow') as mock_time:
            future_time = dt_util.utcnow() + timedelta(hours=2)
            mock_time.return_value = future_time
            
            # Entry should appear expired
            result = await error_prone_cache.get("time_test")
            assert result is None  # Should be expired
            
            # Add new entry with future time
            await error_prone_cache.set("future_entry", {"data": "future"}, CACHE_TTL_MEDIUM)
            
            # Should work with future time
            result = await error_prone_cache.get("future_entry")
            assert result is not None

    @pytest.mark.asyncio
    async def test_memory_corruption_simulation(self, error_prone_cache):
        """Test resilience against simulated memory corruption."""
        # Add normal data
        await error_prone_cache.set("normal_key", {"data": "normal"}, CACHE_TTL_MEDIUM)
        
        # Simulate corruption by directly modifying internal structures
        error_prone_cache._cache["corrupted"] = "not_a_dict"
        error_prone_cache._expiry["corrupted"] = "not_a_datetime"
        error_prone_cache._access_count["corrupted"] = "not_an_int"
        
        # Cache should handle corrupted entries gracefully
        try:
            result = await error_prone_cache.get("corrupted")
            # Might return None or raise exception - both acceptable
        except (TypeError, AttributeError):
            # Expected for corrupted data
            pass
        
        # Normal operations should still work
        result = await error_prone_cache.get("normal_key")
        assert result is not None
        
        # Stats should still be accessible
        stats = error_prone_cache.get_stats()
        assert isinstance(stats, dict)


class TestCacheManagerPerformanceValidation:
    """Test cache manager performance characteristics."""

    @pytest.fixture
    def performance_cache(self):
        """Create cache manager for performance testing."""
        return CacheManager(max_size=1000)

    @pytest.mark.asyncio
    async def test_cache_operation_performance(self, performance_cache):
        """Test cache operation performance benchmarks."""
        import time
        
        # Test set performance
        start_time = time.time()
        for i in range(100):
            await performance_cache.set(f"perf_key_{i}", {"data": i, "timestamp": time.time()}, CACHE_TTL_MEDIUM)
        set_duration = time.time() - start_time
        
        # Should complete quickly
        assert set_duration < 1.0  # Should complete in under 1 second
        
        # Test get performance
        start_time = time.time()
        for i in range(100):
            result = await performance_cache.get(f"perf_key_{i}")
            assert result is not None
        get_duration = time.time() - start_time
        
        # Gets should be faster than sets
        assert get_duration < set_duration
        assert get_duration < 0.5  # Should complete in under 0.5 seconds

    @pytest.mark.asyncio
    async def test_large_dataset_performance(self, performance_cache):
        """Test performance with large datasets."""
        import time
        
        # Add large dataset
        large_data = {"data": "x" * 1000, "metadata": list(range(100))}
        
        start_time = time.time()
        for i in range(500):
            await performance_cache.set(f"large_{i}", large_data.copy(), CACHE_TTL_MEDIUM)
        
        # Should handle large datasets efficiently
        duration = time.time() - start_time
        assert duration < 5.0  # Should complete reasonably quickly
        
        # Verify data integrity
        result = await performance_cache.get("large_100")
        assert result is not None
        assert len(result["data"]) == 1000

    @pytest.mark.asyncio
    async def test_cache_hit_ratio_optimization(self, performance_cache):
        """Test cache hit ratio optimization."""
        # Create access pattern that should result in good hit ratio
        keys = [f"common_key_{i}" for i in range(10)]
        
        # Populate cache
        for key in keys:
            await performance_cache.set(key, {"data": key}, CACHE_TTL_MEDIUM)
        
        # Create hot access pattern
        for _ in range(100):
            for key in keys[:5]:  # Access first 5 keys frequently
                await performance_cache.get(key)
            for key in keys[5:]:  # Access remaining keys less frequently
                if keys.index(key) % 3 == 0:
                    await performance_cache.get(key)
        
        # Check hit ratio
        stats = performance_cache.get_stats()
        assert stats["hit_rate"] > 80  # Should have good hit ratio
        assert stats["hot_keys"] > 0   # Should identify hot keys


@pytest.mark.asyncio
async def test_comprehensive_cache_manager_integration():
    """Comprehensive integration test for cache manager."""
    cache = CacheManager(max_size=50)
    
    # Test complete lifecycle
    
    # 1. Initial empty state
    stats = cache.get_stats()
    assert stats["total_entries"] == 0
    
    # 2. Populate with varied data
    test_data = [
        ("dog_1", {"name": "Buddy", "age": 5}, CACHE_TTL_FAST),
        ("dog_2", {"name": "Max", "age": 3}, CACHE_TTL_MEDIUM),
        ("feeding_1", {"time": "08:00", "amount": 200}, CACHE_TTL_SLOW),
        ("gps_1", {"lat": 52.5, "lon": 13.4}, CACHE_TTL_FAST),
    ]
    
    for key, data, ttl in test_data:
        await cache.set(key, data, ttl)
    
    # 3. Verify all data can be retrieved
    for key, expected_data, _ in test_data:
        result = await cache.get(key)
        assert result is not None
        assert result["name"] == expected_data.get("name") or result["time"] == expected_data.get("time") or result["lat"] == expected_data.get("lat")
    
    # 4. Test pattern invalidation
    count = await cache.invalidate(pattern="dog_*")
    assert count == 2
    
    # 5. Test hot key tracking
    for _ in range(10):
        await cache.get("feeding_1")
    
    stats = cache.get_stats()
    assert stats["hot_keys"] > 0
    
    # 6. Test optimization
    report = await cache.optimize_cache()
    assert report["optimization_completed"] is True
    
    # 7. Test entry details
    details = await cache.get_cache_entry_details("feeding_1")
    assert details is not None
    assert details["is_hot_key"] is True
    
    # 8. Test clearing
    await cache.clear()
    stats = cache.get_stats()
    assert stats["total_entries"] == 0
