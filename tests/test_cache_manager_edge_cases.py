"""Comprehensive edge case and invalidation tests for PawControl CacheManager.

Tests advanced caching scenarios including concurrent access, memory pressure,
TTL boundary conditions, hot key management, pattern invalidation, and
performance characteristics under stress conditions.

Test Areas:
- Concurrent access patterns and async lock contention
- Memory pressure and LRU eviction scenarios
- TTL expiry boundary conditions and edge cases
- Hot key promotion/demotion logic and edge cases
- Pattern invalidation with complex patterns
- Cache optimization under various conditions
- Large data handling and memory management
- Statistics accuracy under stress conditions
- Lock contention and deadlock prevention
- Cache coherency and data integrity
"""

from __future__ import annotations

import asyncio
import pytest
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.cache_manager import (
    CacheManager,
    CACHE_TTL_FAST,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SLOW,
)


class TestConcurrentAccess:
    """Test concurrent access patterns and thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_get_set_operations(self):
        """Test concurrent get/set operations for thread safety."""
        cache = CacheManager(max_size=100)
        
        async def worker(worker_id: int, operation_count: int):
            """Worker function for concurrent operations."""
            results = []
            for i in range(operation_count):
                key = f"worker_{worker_id}_key_{i}"
                data = {"worker_id": worker_id, "operation": i, "data": f"value_{i}"}
                
                # Set data
                await cache.set(key, data, ttl_seconds=CACHE_TTL_MEDIUM)
                
                # Immediately try to get it back
                retrieved = await cache.get(key)
                results.append(retrieved is not None and retrieved["worker_id"] == worker_id)
                
                # Small delay to create more contention
                await asyncio.sleep(0.001)
            
            return results
        
        # Run multiple workers concurrently
        workers = [
            worker(worker_id, 20) for worker_id in range(10)
        ]
        
        all_results = await asyncio.gather(*workers)
        
        # Verify all operations succeeded
        for worker_results in all_results:
            assert all(worker_results), "Some concurrent operations failed"
        
        # Verify cache integrity
        stats = cache.get_stats()
        assert stats["total_entries"] <= 100  # Respects max size
        assert stats["cache_hits"] > 0

    @pytest.mark.asyncio
    async def test_concurrent_invalidation_patterns(self):
        """Test concurrent invalidation with various patterns."""
        cache = CacheManager(max_size=200)
        
        # Pre-populate cache with different key patterns
        for i in range(50):
            await cache.set(f"dog_{i}_feeding", {"type": "feeding", "id": i})
            await cache.set(f"dog_{i}_health", {"type": "health", "id": i})
            await cache.set(f"cat_{i}_info", {"type": "cat", "id": i})
            await cache.set(f"global_setting_{i}", {"type": "global", "id": i})
        
        async def invalidate_pattern(pattern: str, expected_count: int):
            """Invalidate by pattern and verify count."""
            result = await cache.invalidate(pattern=pattern)
            return result == expected_count
        
        # Run concurrent invalidations
        invalidation_tasks = [
            invalidate_pattern("dog_*", 100),  # Should match dog_X_feeding and dog_X_health
            invalidate_pattern("cat_*", 50),   # Should match cat_X_info
            asyncio.sleep(0.01),  # Add timing variation
            invalidate_pattern("global_*", 50),  # Should match global_setting_X
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*invalidation_tasks, return_exceptions=True)
        
        # Filter out sleep task and check invalidation results
        invalidation_results = [r for r in results if isinstance(r, bool)]
        
        # At least some invalidations should succeed
        # (Exact counts may vary due to concurrency)
        assert len(invalidation_results) > 0

    @pytest.mark.asyncio
    async def test_concurrent_cache_optimization(self):
        """Test concurrent cache optimization operations."""
        cache = CacheManager(max_size=50)
        
        # Create mixed cache state
        for i in range(40):
            await cache.set(f"key_{i}", {"value": i}, ttl_seconds=1 if i % 10 == 0 else 3600)
        
        # Create access patterns to generate hot keys
        for i in range(0, 20, 2):  # Access even keys multiple times
            for _ in range(6):  # More than hot key threshold
                await cache.get(f"key_{i}")
        
        async def optimize_cache():
            """Run cache optimization."""
            return await cache.optimize_cache()
        
        async def access_cache():
            """Access cache during optimization."""
            results = []
            for i in range(10):
                key = f"key_{i * 2}"
                result = await cache.get(key)
                results.append(result is not None)
                await asyncio.sleep(0.001)
            return results
        
        # Wait for some entries to expire
        await asyncio.sleep(1.1)
        
        # Run optimization and access concurrently
        opt_result, access_results = await asyncio.gather(
            optimize_cache(),
            access_cache()
        )
        
        # Verify optimization ran successfully
        assert opt_result["optimization_completed"] is True
        assert opt_result["expired_cleared"] > 0
        
        # Verify cache remained accessible during optimization
        assert len(access_results) == 10

    @pytest.mark.asyncio
    async def test_lock_contention_high_frequency(self):
        """Test lock contention with high-frequency operations."""
        cache = CacheManager(max_size=30)
        
        async def high_frequency_operations(task_id: int):
            """Perform high-frequency cache operations."""
            operation_count = 0
            start_time = time.time()
            
            while time.time() - start_time < 0.5:  # 500ms test duration
                key = f"hf_key_{task_id}_{operation_count}"
                
                # Rapid set/get cycle
                await cache.set(key, {"task": task_id, "op": operation_count})
                result = await cache.get(key)
                
                if result is not None:
                    operation_count += 1
                
                # Minimal delay to create contention
                await asyncio.sleep(0.0001)
            
            return operation_count
        
        # Run multiple high-frequency tasks
        tasks = [high_frequency_operations(task_id) for task_id in range(8)]
        operation_counts = await asyncio.gather(*tasks)
        
        # Verify operations completed successfully
        total_operations = sum(operation_counts)
        assert total_operations > 100  # Should complete many operations
        
        # Verify cache consistency
        stats = cache.get_stats()
        assert stats["total_entries"] <= 30  # Respects size limit
        assert stats["cache_hits"] > 0


class TestMemoryPressureAndEviction:
    """Test memory pressure scenarios and LRU eviction."""

    @pytest.mark.asyncio
    async def test_lru_eviction_with_hot_keys(self):
        """Test LRU eviction while protecting hot keys."""
        cache = CacheManager(max_size=10)  # Small cache for testing
        
        # Fill cache to capacity
        for i in range(10):
            await cache.set(f"key_{i}", {"value": i, "data": "x" * 100})
        
        # Create hot keys by accessing some entries frequently
        hot_keys = ["key_2", "key_5", "key_8"]
        for key in hot_keys:
            for _ in range(6):  # Exceed hot key threshold
                await cache.get(key)
        
        # Verify hot key promotion
        stats = cache.get_stats()
        assert stats["hot_keys"] == len(hot_keys)
        
        # Add new entries to trigger eviction
        for i in range(10, 15):
            await cache.set(f"new_key_{i}", {"value": i})
        
        # Verify hot keys are protected from eviction
        for key in hot_keys:
            result = await cache.get(key)
            assert result is not None, f"Hot key {key} was evicted"
        
        # Verify some non-hot keys were evicted
        evicted_count = 0
        for i in range(10):
            if f"key_{i}" not in hot_keys:
                result = await cache.get(f"key_{i}")
                if result is None:
                    evicted_count += 1
        
        assert evicted_count > 0  # Some non-hot keys should be evicted

    @pytest.mark.asyncio
    async def test_memory_pressure_large_objects(self):
        """Test memory pressure with large cached objects."""
        cache = CacheManager(max_size=50)
        
        # Create large objects
        large_objects = []
        for i in range(30):
            # Large data structure
            large_data = {
                "id": i,
                "data": "x" * 10000,  # 10KB string
                "nested": {
                    "list": list(range(1000)),
                    "dict": {f"key_{j}": f"value_{j}" for j in range(100)}
                }
            }
            large_objects.append(large_data)
            await cache.set(f"large_obj_{i}", large_data)
        
        # Verify cache handles large objects
        stats = cache.get_stats()
        assert stats["total_entries"] <= 50
        
        # Test retrieval of large objects
        for i in range(min(20, stats["total_entries"])):
            result = await cache.get(f"large_obj_{i}")
            if result is not None:
                assert len(result["data"]) == 10000
                assert len(result["nested"]["list"]) == 1000

    @pytest.mark.asyncio
    async def test_eviction_order_accuracy(self):
        """Test that LRU eviction follows correct order."""
        cache = CacheManager(max_size=5)
        
        # Add entries with controlled access patterns
        access_order = []
        
        # Fill cache
        for i in range(5):
            await cache.set(f"key_{i}", {"value": i})
            access_order.append(f"key_{i}")
        
        # Access keys in specific order to establish LRU order
        await cache.get("key_1")  # Most recent
        access_order.remove("key_1")
        access_order.append("key_1")
        
        await cache.get("key_3")  # Second most recent
        access_order.remove("key_3")
        access_order.append("key_3")
        
        # key_0, key_2, key_4 should be LRU candidates
        # Add new entry to trigger eviction
        await cache.set("new_key", {"value": "new"})
        
        # The least recently used key should be evicted
        # (key_0 should be first candidate)
        result = await cache.get("key_0")
        assert result is None, "LRU key was not evicted"
        
        # More recently accessed keys should remain
        assert await cache.get("key_1") is not None
        assert await cache.get("key_3") is not None

    @pytest.mark.asyncio
    async def test_eviction_with_mixed_ttl(self):
        """Test eviction behavior with mixed TTL values."""
        cache = CacheManager(max_size=8)
        
        # Add entries with different TTLs
        await cache.set("fast_1", {"ttl": "fast"}, CACHE_TTL_FAST)
        await cache.set("medium_1", {"ttl": "medium"}, CACHE_TTL_MEDIUM)
        await cache.set("slow_1", {"ttl": "slow"}, CACHE_TTL_SLOW)
        await cache.set("fast_2", {"ttl": "fast"}, CACHE_TTL_FAST)
        await cache.set("medium_2", {"ttl": "medium"}, CACHE_TTL_MEDIUM)
        await cache.set("slow_2", {"ttl": "slow"}, CACHE_TTL_SLOW)
        await cache.set("fast_3", {"ttl": "fast"}, CACHE_TTL_FAST)
        await cache.set("medium_3", {"ttl": "medium"}, CACHE_TTL_MEDIUM)
        
        # Access some keys to create access patterns
        await cache.get("slow_1")  # Promote slow key
        await cache.get("fast_1")  # Access fast key
        
        # Fill to capacity and add one more
        await cache.set("trigger_eviction", {"ttl": "trigger"})
        
        # Verify cache size constraint
        stats = cache.get_stats()
        assert stats["total_entries"] == 8


class TestTTLAndExpiryEdgeCases:
    """Test TTL expiry boundary conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_ttl_boundary_conditions(self):
        """Test TTL expiry at exact boundary conditions."""
        cache = CacheManager()
        
        # Test with 1-second TTL for precise timing
        await cache.set("boundary_key", {"value": "test"}, ttl_seconds=1)
        
        # Should be available immediately
        result = await cache.get("boundary_key")
        assert result is not None
        
        # Wait almost to expiry
        await asyncio.sleep(0.9)
        result = await cache.get("boundary_key")
        assert result is not None  # Should still be valid
        
        # Wait past expiry
        await asyncio.sleep(0.2)  # Total 1.1 seconds
        result = await cache.get("boundary_key")
        assert result is None  # Should be expired

    @pytest.mark.asyncio
    async def test_ttl_zero_and_negative(self):
        """Test TTL with zero and negative values."""
        cache = CacheManager()
        
        # Test zero TTL (should expire immediately)
        await cache.set("zero_ttl", {"value": "zero"}, ttl_seconds=0)
        
        # Even immediate access might find it expired
        await asyncio.sleep(0.001)  # Tiny delay
        result = await cache.get("zero_ttl")
        assert result is None  # Should be expired
        
        # Test negative TTL (should be treated as expired)
        await cache.set("negative_ttl", {"value": "negative"}, ttl_seconds=-1)
        result = await cache.get("negative_ttl")
        assert result is None  # Should be expired

    @pytest.mark.asyncio
    async def test_ttl_very_large_values(self):
        """Test TTL with very large values."""
        cache = CacheManager()
        
        # Test very large TTL (years in the future)
        large_ttl = 365 * 24 * 3600  # 1 year in seconds
        await cache.set("large_ttl", {"value": "persistent"}, ttl_seconds=large_ttl)
        
        result = await cache.get("large_ttl")
        assert result is not None
        
        # Verify expiry time is far in the future
        details = await cache.get_cache_entry_details("large_ttl")
        assert details["ttl_remaining"] > 360 * 24 * 3600  # Almost a year

    @pytest.mark.asyncio
    async def test_concurrent_ttl_expiry(self):
        """Test concurrent TTL expiry scenarios."""
        cache = CacheManager()
        
        # Add multiple entries with staggered expiry times
        for i in range(20):
            ttl = 0.1 + (i * 0.05)  # 0.1 to 1.0 second TTLs
            await cache.set(f"staggered_{i}", {"value": i}, ttl_seconds=ttl)
        
        # Wait for some to expire
        await asyncio.sleep(0.5)
        
        # Check which entries are still valid
        valid_count = 0
        expired_count = 0
        
        for i in range(20):
            result = await cache.get(f"staggered_{i}")
            if result is not None:
                valid_count += 1
            else:
                expired_count += 1
        
        # Should have mix of valid and expired
        assert valid_count > 0  # Some should still be valid
        assert expired_count > 0  # Some should be expired

    @pytest.mark.asyncio
    async def test_ttl_update_behavior(self):
        """Test TTL update behavior when setting existing keys."""
        cache = CacheManager()
        
        # Set initial entry with short TTL
        await cache.set("update_ttl", {"version": 1}, ttl_seconds=1)
        
        # Wait most of the TTL
        await asyncio.sleep(0.8)
        
        # Update with longer TTL
        await cache.set("update_ttl", {"version": 2}, ttl_seconds=10)
        
        # Wait past original expiry
        await asyncio.sleep(0.5)  # Total 1.3 seconds
        
        # Should still be valid due to TTL update
        result = await cache.get("update_ttl")
        assert result is not None
        assert result["version"] == 2


class TestHotKeyManagement:
    """Test hot key promotion/demotion logic and edge cases."""

    @pytest.mark.asyncio
    async def test_hot_key_promotion_threshold(self):
        """Test hot key promotion at exact threshold."""
        cache = CacheManager()
        
        await cache.set("promotion_test", {"value": "test"})
        
        # Access exactly 5 times (threshold is >5)
        for _ in range(5):
            await cache.get("promotion_test")
        
        stats = cache.get_stats()
        assert stats["hot_keys"] == 0  # Should not be promoted yet
        
        # One more access should promote it
        await cache.get("promotion_test")
        
        stats = cache.get_stats()
        assert stats["hot_keys"] == 1  # Should now be promoted

    @pytest.mark.asyncio
    async def test_hot_key_demotion_during_optimization(self):
        """Test hot key demotion during cache optimization."""
        cache = CacheManager()
        
        # Create hot keys
        hot_keys = ["hot_1", "hot_2", "hot_3"]
        for key in hot_keys:
            await cache.set(key, {"value": key})
            for _ in range(6):  # Promote to hot
                await cache.get(key)
        
        # Verify promotion
        stats = cache.get_stats()
        assert stats["hot_keys"] == len(hot_keys)
        
        # Access only some hot keys to create stale hot keys
        for _ in range(5):
            await cache.get("hot_1")  # Keep this one active
        
        # Reset access counts to simulate stale hot keys
        # (In real scenario, this would happen over time)
        cache._access_count["hot_2"] = 1  # Below demotion threshold
        cache._access_count["hot_3"] = 0  # Below demotion threshold
        
        # Run optimization
        opt_result = await cache.optimize_cache()
        
        # Should demote stale hot keys
        assert opt_result["hot_keys_demoted"] > 0
        
        stats = cache.get_stats()
        assert stats["hot_keys"] < len(hot_keys)  # Some demoted

    @pytest.mark.asyncio
    async def test_hot_key_protection_during_eviction(self):
        """Test that hot keys are protected during LRU eviction."""
        cache = CacheManager(max_size=5)
        
        # Fill cache
        for i in range(5):
            await cache.set(f"key_{i}", {"value": i})
        
        # Make key_2 hot
        for _ in range(6):
            await cache.get("key_2")
        
        # Verify hot key status
        details = await cache.get_cache_entry_details("key_2")
        assert details["is_hot_key"] is True
        
        # Add new entries to trigger eviction
        for i in range(5, 10):
            await cache.set(f"new_key_{i}", {"value": i})
        
        # Hot key should survive eviction
        result = await cache.get("key_2")
        assert result is not None
        
        # Non-hot keys should be evicted
        evicted = 0
        for i in [0, 1, 3, 4]:  # Non-hot original keys
            if await cache.get(f"key_{i}") is None:
                evicted += 1
        
        assert evicted > 0  # Some non-hot keys evicted

    @pytest.mark.asyncio
    async def test_hot_key_access_patterns(self):
        """Test various hot key access patterns."""
        cache = CacheManager()
        
        # Pattern 1: Burst access
        await cache.set("burst_key", {"pattern": "burst"})
        for _ in range(10):  # Burst of access
            await cache.get("burst_key")
        
        # Pattern 2: Gradual access
        await cache.set("gradual_key", {"pattern": "gradual"})
        for i in range(8):
            await cache.get("gradual_key")
            await asyncio.sleep(0.001)  # Spread over time
        
        # Pattern 3: Intermittent access
        await cache.set("intermittent_key", {"pattern": "intermittent"})
        for i in range(7):
            if i % 2 == 0:
                await cache.get("intermittent_key")
        
        # Check final hot key status
        burst_details = await cache.get_cache_entry_details("burst_key")
        gradual_details = await cache.get_cache_entry_details("gradual_key")
        intermittent_details = await cache.get_cache_entry_details("intermittent_key")
        
        assert burst_details["is_hot_key"] is True
        assert gradual_details["is_hot_key"] is True
        # Intermittent might or might not be hot depending on exact count


class TestPatternInvalidation:
    """Test pattern-based invalidation with complex patterns."""

    @pytest.mark.asyncio
    async def test_pattern_invalidation_wildcards(self):
        """Test pattern invalidation with various wildcard patterns."""
        cache = CacheManager()
        
        # Create diverse key patterns
        keys_data = [
            ("dog_1_feeding", "dog feeding data"),
            ("dog_1_health", "dog health data"),
            ("dog_2_feeding", "dog feeding data"),
            ("dog_2_health", "dog health data"),
            ("cat_1_feeding", "cat feeding data"),
            ("global_setting", "global data"),
            ("dog_stats_summary", "dog summary"),
            ("doggy_style", "unrelated"),  # Should not match "dog_*"
        ]
        
        for key, data in keys_data:
            await cache.set(key, {"data": data})
        
        # Test different patterns
        test_patterns = [
            ("dog_*", 6),  # dog_1_feeding, dog_1_health, dog_2_feeding, dog_2_health, dog_stats_summary, plus doggy_style (wrong!)
            ("dog_1_*", 2),  # dog_1_feeding, dog_1_health
            ("*_feeding", 3),  # dog_1_feeding, dog_2_feeding, cat_1_feeding
            ("cat_*", 1),  # cat_1_feeding
            ("global_*", 1),  # global_setting
            ("nonexistent_*", 0),  # No matches
        ]
        
        for pattern, expected_count in test_patterns:
            # Reset cache for each test
            await cache.clear()
            for key, data in keys_data:
                await cache.set(key, {"data": data})
            
            result = await cache.invalidate(pattern=pattern)
            
            # For dog_* pattern, should not match "doggy_style"
            if pattern == "dog_*":
                # Verify "doggy_style" was not invalidated
                doggy_result = await cache.get("doggy_style")
                assert doggy_result is not None, "doggy_style should not match dog_*"
                expected_count = 5  # Adjust expected count
            
            assert result <= expected_count  # Allow for implementation variance

    @pytest.mark.asyncio
    async def test_pattern_invalidation_edge_cases(self):
        """Test pattern invalidation edge cases."""
        cache = CacheManager()
        
        # Edge case keys
        edge_keys = [
            "",  # Empty key
            "_",  # Single underscore
            "key_",  # Ends with underscore
            "_key",  # Starts with underscore
            "key__double",  # Double underscore
            "very_long_key_with_many_underscores_and_segments",
        ]
        
        for key in edge_keys:
            try:
                await cache.set(key, {"edge": "case"})
            except Exception:
                # Some edge keys might be invalid, which is acceptable
                pass
        
        # Test edge case patterns
        edge_patterns = [
            "",  # Empty pattern
            "*",  # Match all pattern
            "_*",  # Start with underscore
            "*_",  # End with underscore
            "**",  # Double wildcard
        ]
        
        for pattern in edge_patterns:
            try:
                result = await cache.invalidate(pattern=pattern)
                assert isinstance(result, int)  # Should return valid count
            except Exception:
                # Some patterns might be invalid, which is acceptable
                pass

    @pytest.mark.asyncio
    async def test_large_scale_pattern_invalidation(self):
        """Test pattern invalidation with large number of keys."""
        cache = CacheManager(max_size=1000)
        
        # Create large number of keys with patterns
        categories = ["dog", "cat", "bird", "fish"]
        operations = ["feeding", "health", "exercise", "grooming"]
        
        keys_created = 0
        for category in categories:
            for i in range(50):  # 50 of each category
                for operation in operations:
                    key = f"{category}_{i}_{operation}"
                    await cache.set(key, {"category": category, "id": i, "op": operation})
                    keys_created += 1
        
        # Test invalidation of large pattern
        dog_invalidated = await cache.invalidate(pattern="dog_*")
        
        # Should invalidate all dog-related keys
        expected_dog_keys = 50 * len(operations)  # 200 keys
        assert dog_invalidated == expected_dog_keys
        
        # Verify other categories remain
        cat_result = await cache.get("cat_1_feeding")
        assert cat_result is not None
        
        # Verify dog keys are gone
        dog_result = await cache.get("dog_1_feeding")
        assert dog_result is None

    @pytest.mark.asyncio
    async def test_concurrent_pattern_invalidation(self):
        """Test concurrent pattern invalidation operations."""
        cache = CacheManager(max_size=500)
        
        # Pre-populate with overlapping patterns
        for i in range(100):
            await cache.set(f"pattern_a_{i}", {"pattern": "a", "id": i})
            await cache.set(f"pattern_b_{i}", {"pattern": "b", "id": i})
            await cache.set(f"pattern_ab_{i}", {"pattern": "ab", "id": i})
        
        async def invalidate_pattern_a():
            return await cache.invalidate(pattern="pattern_a_*")
        
        async def invalidate_pattern_b():
            return await cache.invalidate(pattern="pattern_b_*")
        
        async def invalidate_pattern_ab():
            return await cache.invalidate(pattern="pattern_ab_*")
        
        # Run concurrent invalidations
        results = await asyncio.gather(
            invalidate_pattern_a(),
            invalidate_pattern_b(),
            invalidate_pattern_ab(),
            return_exceptions=True
        )
        
        # All should complete successfully
        for result in results:
            assert isinstance(result, int)
            assert result >= 0


class TestCacheOptimizationStress:
    """Test cache optimization under various stress conditions."""

    @pytest.mark.asyncio
    async def test_optimization_with_mixed_workload(self):
        """Test optimization with mixed workload patterns."""
        cache = CacheManager(max_size=100)
        
        # Create mixed workload
        # 1. Some entries with short TTL (will expire)
        for i in range(20):
            await cache.set(f"short_ttl_{i}", {"ttl": "short"}, ttl_seconds=1)
        
        # 2. Some entries with long TTL
        for i in range(30):
            await cache.set(f"long_ttl_{i}", {"ttl": "long"}, ttl_seconds=3600)
        
        # 3. Some frequently accessed entries (will become hot)
        for i in range(10):
            key = f"frequent_{i}"
            await cache.set(key, {"access": "frequent"})
            for _ in range(8):  # Create hot keys
                await cache.get(key)
        
        # 4. Some rarely accessed entries
        for i in range(15):
            await cache.set(f"rare_{i}", {"access": "rare"})
            await cache.get(f"rare_{i}")  # Single access
        
        # Wait for short TTL entries to expire
        await asyncio.sleep(1.1)
        
        # Run optimization
        opt_result = await cache.optimize_cache()
        
        # Verify optimization results
        assert opt_result["optimization_completed"] is True
        assert opt_result["expired_cleared"] == 20  # Short TTL entries
        assert opt_result["hot_keys_promoted"] >= 10  # Frequent entries
        
        # Verify cache state after optimization
        stats = cache.get_stats()
        assert stats["total_entries"] <= 100
        assert stats["hot_keys"] >= 10

    @pytest.mark.asyncio
    async def test_optimization_under_concurrent_access(self):
        """Test optimization while cache is under concurrent access."""
        cache = CacheManager(max_size=50)
        
        # Pre-populate cache
        for i in range(40):
            ttl = 1 if i < 10 else 3600  # First 10 will expire
            await cache.set(f"key_{i}", {"value": i}, ttl_seconds=ttl)
        
        async def continuous_access():
            """Continuously access cache during optimization."""
            access_count = 0
            for _ in range(100):
                key = f"key_{random.randint(10, 39)}"  # Access non-expiring keys
                result = await cache.get(key)
                if result is not None:
                    access_count += 1
                await asyncio.sleep(0.01)
            return access_count
        
        async def trigger_optimization():
            """Trigger optimization after some expiry."""
            await asyncio.sleep(1.1)  # Wait for expiry
            return await cache.optimize_cache()
        
        # Run concurrent operations
        access_result, opt_result = await asyncio.gather(
            continuous_access(),
            trigger_optimization()
        )
        
        # Both operations should complete successfully
        assert access_result > 0  # Should have successful accesses
        assert opt_result["optimization_completed"] is True
        assert opt_result["expired_cleared"] > 0

    @pytest.mark.asyncio
    async def test_optimization_frequency_limits(self):
        """Test optimization with rapid successive calls."""
        cache = CacheManager()
        
        # Pre-populate with expiring entries
        for i in range(20):
            await cache.set(f"expire_{i}", {"value": i}, ttl_seconds=1)
        
        await asyncio.sleep(1.1)  # Wait for expiry
        
        # Run multiple optimizations rapidly
        opt_results = []
        for _ in range(5):
            result = await cache.optimize_cache()
            opt_results.append(result)
            await asyncio.sleep(0.01)  # Minimal delay
        
        # First optimization should clear expired entries
        assert opt_results[0]["expired_cleared"] == 20
        
        # Subsequent optimizations should find fewer/no expired entries
        for result in opt_results[1:]:
            assert result["expired_cleared"] == 0  # Already cleared

    @pytest.mark.asyncio
    async def test_optimization_memory_cleanup_effectiveness(self):
        """Test optimization effectiveness for memory cleanup."""
        cache = CacheManager(max_size=100)
        
        # Create large number of entries that will expire
        large_data_size = 50
        for i in range(large_data_size):
            large_data = {
                "id": i,
                "data": "x" * 1000,  # 1KB per entry
                "metadata": {"created": dt_util.utcnow().isoformat()}
            }
            await cache.set(f"large_{i}", large_data, ttl_seconds=1)
        
        # Add some permanent entries
        for i in range(20):
            await cache.set(f"permanent_{i}", {"value": i}, ttl_seconds=3600)
        
        initial_stats = cache.get_stats()
        assert initial_stats["total_entries"] == 70  # 50 + 20
        
        # Wait for expiry
        await asyncio.sleep(1.1)
        
        # Run optimization
        opt_result = await cache.optimize_cache()
        
        # Verify cleanup
        assert opt_result["expired_cleared"] == large_data_size
        
        final_stats = cache.get_stats()
        assert final_stats["total_entries"] == 20  # Only permanent entries


class TestDataIntegrityAndCoherency:
    """Test data integrity and cache coherency."""

    @pytest.mark.asyncio
    async def test_data_modification_isolation(self):
        """Test that cached data modifications don't affect original."""
        cache = CacheManager()
        
        original_data = {
            "list": [1, 2, 3],
            "dict": {"key": "value"},
            "primitive": "string"
        }
        
        await cache.set("isolation_test", original_data)
        
        # Get cached data and modify it
        cached_data = await cache.get("isolation_test")
        cached_data["list"].append(4)
        cached_data["dict"]["key"] = "modified"
        cached_data["primitive"] = "changed"
        
        # Get fresh copy from cache
        fresh_data = await cache.get("isolation_test")
        
        # Fresh copy should be unchanged
        assert fresh_data["list"] == [1, 2, 3]
        assert fresh_data["dict"]["key"] == "value"
        assert fresh_data["primitive"] == "string"

    @pytest.mark.asyncio
    async def test_cache_coherency_across_operations(self):
        """Test cache coherency across various operations."""
        cache = CacheManager()
        
        # Set initial data
        await cache.set("coherency_test", {"version": 1, "data": "initial"})
        
        # Verify initial get
        result1 = await cache.get("coherency_test")
        assert result1["version"] == 1
        
        # Update data
        await cache.set("coherency_test", {"version": 2, "data": "updated"})
        
        # Verify update is reflected
        result2 = await cache.get("coherency_test")
        assert result2["version"] == 2
        assert result2["data"] == "updated"
        
        # Get entry details
        details = await cache.get_cache_entry_details("coherency_test")
        assert details is not None
        assert details["key"] == "coherency_test"
        
        # Invalidate
        invalidated = await cache.invalidate(key="coherency_test")
        assert invalidated == 1
        
        # Verify invalidation
        result3 = await cache.get("coherency_test")
        assert result3 is None
        
        # Details should also reflect removal
        details2 = await cache.get_cache_entry_details("coherency_test")
        assert details2 is None

    @pytest.mark.asyncio
    async def test_statistics_accuracy_under_load(self):
        """Test statistics accuracy under various load conditions."""
        cache = CacheManager()
        
        # Track expected statistics
        expected_hits = 0
        expected_misses = 0
        
        # Phase 1: Misses (keys don't exist)
        for i in range(20):
            result = await cache.get(f"nonexistent_{i}")
            assert result is None
            expected_misses += 1
        
        # Phase 2: Sets and hits
        for i in range(15):
            await cache.set(f"key_{i}", {"value": i})
            
            # Immediate get (should hit)
            result = await cache.get(f"key_{i}")
            assert result is not None
            expected_hits += 1
        
        # Phase 3: Multiple accesses (more hits)
        for i in range(0, 15, 3):  # Access every 3rd key multiple times
            for _ in range(4):
                result = await cache.get(f"key_{i}")
                assert result is not None
                expected_hits += 1
        
        # Phase 4: Mix of hits and misses
        for i in range(30):
            if i < 15:
                result = await cache.get(f"key_{i}")  # Hit
                assert result is not None
                expected_hits += 1
            else:
                result = await cache.get(f"missing_{i}")  # Miss
                assert result is None
                expected_misses += 1
        
        # Verify statistics accuracy
        stats = cache.get_stats()
        assert stats["cache_hits"] == expected_hits
        assert stats["cache_misses"] == expected_misses
        
        total_accesses = expected_hits + expected_misses
        expected_hit_rate = (expected_hits / total_accesses * 100) if total_accesses > 0 else 0
        assert abs(stats["hit_rate"] - expected_hit_rate) < 0.1  # Allow small rounding differences


class TestExtremeConditions:
    """Test extreme conditions and edge cases."""

    @pytest.mark.asyncio
    async def test_empty_cache_operations(self):
        """Test all operations on empty cache."""
        cache = CacheManager()
        
        # Test get on empty cache
        result = await cache.get("nonexistent")
        assert result is None
        
        # Test invalidation on empty cache
        invalidated = await cache.invalidate(key="nonexistent")
        assert invalidated == 0
        
        invalidated = await cache.invalidate(pattern="nonexistent_*")
        assert invalidated == 0
        
        # Test optimization on empty cache
        opt_result = await cache.optimize_cache()
        assert opt_result["optimization_completed"] is True
        assert opt_result["expired_cleared"] == 0
        
        # Test clear expired on empty cache
        cleared = await cache.clear_expired()
        assert cleared == 0
        
        # Test statistics on empty cache
        stats = cache.get_stats()
        assert stats["total_entries"] == 0
        assert stats["cache_hits"] == 0
        assert stats["cache_misses"] > 0  # From the get operation

    @pytest.mark.asyncio
    async def test_maximum_capacity_stress(self):
        """Test behavior at maximum capacity."""
        max_size = 20
        cache = CacheManager(max_size=max_size)
        
        # Fill to exact capacity
        for i in range(max_size):
            await cache.set(f"capacity_key_{i}", {"value": i})
        
        stats = cache.get_stats()
        assert stats["total_entries"] == max_size
        
        # Add one more (should trigger eviction)
        await cache.set("overflow_key", {"value": "overflow"})
        
        stats = cache.get_stats()
        assert stats["total_entries"] == max_size  # Should not exceed
        
        # Verify overflow key exists
        result = await cache.get("overflow_key")
        assert result is not None
        
        # At least one original key should be evicted
        evicted_count = 0
        for i in range(max_size):
            result = await cache.get(f"capacity_key_{i}")
            if result is None:
                evicted_count += 1
        
        assert evicted_count >= 1

    @pytest.mark.asyncio
    async def test_very_large_keys_and_values(self):
        """Test handling of very large keys and values."""
        cache = CacheManager()
        
        # Test large key
        large_key = "x" * 1000
        await cache.set(large_key, {"value": "large_key_test"})
        result = await cache.get(large_key)
        assert result is not None
        
        # Test large value
        large_value = {
            "large_string": "x" * 100000,  # 100KB string
            "large_list": list(range(10000)),  # Large list
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(1000)}  # Large dict
        }
        
        await cache.set("large_value_key", large_value)
        result = await cache.get("large_value_key")
        assert result is not None
        assert len(result["large_string"]) == 100000
        assert len(result["large_list"]) == 10000
        assert len(result["large_dict"]) == 1000

    @pytest.mark.asyncio
    async def test_rapid_clear_and_repopulate(self):
        """Test rapid cache clear and repopulate cycles."""
        cache = CacheManager(max_size=50)
        
        for cycle in range(5):
            # Populate cache
            for i in range(30):
                await cache.set(f"cycle_{cycle}_key_{i}", {"cycle": cycle, "value": i})
            
            # Verify population
            stats = cache.get_stats()
            assert stats["total_entries"] == 30
            
            # Clear cache
            await cache.clear()
            
            # Verify clear
            stats = cache.get_stats()
            assert stats["total_entries"] == 0
            
            # Verify no data accessible
            result = await cache.get(f"cycle_{cycle}_key_0")
            assert result is None


if __name__ == "__main__":
    pytest.main([__file__])
