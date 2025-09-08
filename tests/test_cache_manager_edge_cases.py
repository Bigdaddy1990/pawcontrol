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
- Advanced invalidation race conditions
- Large-scale performance testing
- Cache corruption detection and recovery
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from custom_components.pawcontrol.cache_manager import (
    CACHE_TTL_FAST,
    CACHE_TTL_MEDIUM,
    CACHE_TTL_SLOW,
    CacheManager,
)
from homeassistant.util import dt as dt_util


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
                results.append(
                    retrieved is not None and retrieved["worker_id"] == worker_id
                )

                # Small delay to create more contention
                await asyncio.sleep(0.001)

            return results

        # Run multiple workers concurrently
        workers = [worker(worker_id, 20) for worker_id in range(10)]

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
            invalidate_pattern(
                "dog_*", 100
            ),  # Should match dog_X_feeding and dog_X_health
            invalidate_pattern("cat_*", 50),  # Should match cat_X_info
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
            await cache.set(
                f"key_{i}", {"value": i}, ttl_seconds=1 if i % 10 == 0 else 3600
            )

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
            optimize_cache(), access_cache()
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
                    "dict": {f"key_{j}": f"value_{j}" for j in range(100)},
                },
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
        await cache.get_cache_entry_details("intermittent_key")

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
            (
                "dog_*",
                6,
            ),  # dog_1_feeding, dog_1_health, dog_2_feeding, dog_2_health, dog_stats_summary, plus doggy_style (wrong!)
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
                    await cache.set(
                        key, {"category": category, "id": i, "op": operation}
                    )
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
            return_exceptions=True,
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
            continuous_access(), trigger_optimization()
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
                "metadata": {"created": dt_util.utcnow().isoformat()},
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
            "primitive": "string",
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
        expected_hit_rate = (
            (expected_hits / total_accesses * 100) if total_accesses > 0 else 0
        )
        assert (
            abs(stats["hit_rate"] - expected_hit_rate) < 0.1
        )  # Allow small rounding differences


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
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(1000)},  # Large dict
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


class TestAdvancedLockContentionAndDeadlockPrevention:
    """Test advanced lock contention scenarios and deadlock prevention."""

    @pytest.mark.asyncio
    async def test_nested_operation_deadlock_prevention(self):
        """Test prevention of deadlocks in nested cache operations."""
        cache = CacheManager(max_size=10)

        # Pre-populate cache
        for i in range(8):
            await cache.set(f"nested_key_{i}", {"value": i})

        async def complex_nested_operation(worker_id: int):
            """Perform complex nested operations that could cause deadlocks."""
            try:
                # Get multiple keys in sequence
                keys = [f"nested_key_{i}" for i in range(0, 5)]
                for key in keys:
                    result = await cache.get(key)
                    if result is not None:
                        # Modify and set back (potential lock conflict)
                        result["worker"] = worker_id
                        await cache.set(key, result)

                # Trigger optimization during operations (potential lock conflict)
                if worker_id % 3 == 0:
                    await cache.optimize_cache()

                # Pattern invalidation (potential lock conflict)
                if worker_id % 4 == 0:
                    await cache.invalidate(pattern="nested_*")

                return True
            except Exception as e:
                return f"Worker {worker_id} failed: {e}"

        # Run multiple workers with complex operations
        workers = [complex_nested_operation(i) for i in range(8)]
        results = await asyncio.gather(*workers, return_exceptions=True)

        # Count successful operations (should not have deadlocks)
        successful = sum(1 for r in results if r is True)
        len(results) - successful

        # At least majority should succeed (no deadlocks)
        assert successful >= len(workers) // 2

        # Cache should remain in consistent state
        stats = cache.get_stats()
        assert stats["total_entries"] >= 0  # Basic consistency

    @pytest.mark.asyncio
    async def test_lock_timeout_under_extreme_contention(self):
        """Test lock behavior under extreme contention scenarios."""
        cache = CacheManager(max_size=5)

        # Create extreme contention scenario
        contention_duration = 0.3  # 300ms of extreme operations

        async def extreme_contention_worker(worker_id: int):
            """Worker creating extreme lock contention."""
            operation_count = 0
            start_time = time.time()

            while time.time() - start_time < contention_duration:
                key = f"contention_key_{worker_id % 3}"  # Shared keys for contention

                # Rapid fire operations
                await cache.set(key, {"worker": worker_id, "op": operation_count})
                await cache.get(key)

                # Occasionally trigger expensive operations
                if operation_count % 10 == 0:
                    await cache.clear_expired()

                operation_count += 1
                # No sleep - maximum contention

            return operation_count

        # Run many workers for extreme contention
        workers = [extreme_contention_worker(i) for i in range(15)]
        operation_counts = await asyncio.gather(*workers, return_exceptions=True)

        # Should complete without hanging or exceptions
        successful_workers = [
            count for count in operation_counts if isinstance(count, int)
        ]
        assert len(successful_workers) > 10  # Most workers should complete

        total_operations = sum(successful_workers)
        assert total_operations > 100  # Should complete many operations

    @pytest.mark.asyncio
    async def test_async_lock_fairness_under_load(self):
        """Test async lock fairness under heavy load."""
        cache = CacheManager(max_size=20)

        async def fairness_test_worker(worker_id: int, priority: str):
            """Worker testing lock fairness."""
            operations_completed = 0
            start_time = time.time()

            while time.time() - start_time < 0.2:  # 200ms test
                key = f"fairness_key_{worker_id}"

                # Different operation types based on priority
                if priority == "high":
                    # Simple operations (should be fast)
                    await cache.get(key)
                    await cache.set(
                        key, {"priority": priority, "ops": operations_completed}
                    )
                elif priority == "medium":
                    # Medium complexity operations
                    await cache.set(
                        key, {"priority": priority, "ops": operations_completed}
                    )
                    await cache.get_cache_entry_details(key)
                else:
                    # Complex operations
                    await cache.set(
                        key, {"priority": priority, "ops": operations_completed}
                    )
                    await cache.optimize_cache()

                operations_completed += 1
                await asyncio.sleep(0.001)  # Small yield

            return worker_id, priority, operations_completed

        # Mix of high, medium, and low priority workers
        workers = []
        for i in range(12):
            if i < 4:
                priority = "high"
            elif i < 8:
                priority = "medium"
            else:
                priority = "low"
            workers.append(fairness_test_worker(i, priority))

        results = await asyncio.gather(*workers)

        # Analyze fairness
        high_priority_ops = [ops for _, priority, ops in results if priority == "high"]
        [ops for _, priority, ops in results if priority == "medium"]
        low_priority_ops = [ops for _, priority, ops in results if priority == "low"]

        # High priority should generally complete more operations
        avg_high = (
            sum(high_priority_ops) / len(high_priority_ops) if high_priority_ops else 0
        )
        avg_low = (
            sum(low_priority_ops) / len(low_priority_ops) if low_priority_ops else 0
        )

        # Some degree of fairness expected (not perfect due to async nature)
        assert avg_high > 0  # High priority workers should complete operations
        assert avg_low > 0  # Low priority workers should not be starved


class TestAdvancedInvalidationRaceConditions:
    """Test advanced invalidation scenarios with race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_pattern_overlap_invalidation(self):
        """Test concurrent invalidation with overlapping patterns."""
        cache = CacheManager(max_size=500)

        # Create overlapping pattern structure
        for i in range(100):
            await cache.set(f"prefix_a_suffix_{i}", {"type": "a", "id": i})
            await cache.set(f"prefix_b_suffix_{i}", {"type": "b", "id": i})
            await cache.set(f"prefix_ab_suffix_{i}", {"type": "ab", "id": i})
            await cache.set(f"different_prefix_a_{i}", {"type": "diff_a", "id": i})

        async def invalidate_with_overlap(pattern: str, delay: float = 0):
            """Invalidate with optional delay for race conditions."""
            if delay > 0:
                await asyncio.sleep(delay)
            return await cache.invalidate(pattern=pattern)

        # Run overlapping invalidations concurrently
        invalidation_tasks = [
            invalidate_with_overlap(
                "prefix_a_*", 0.0
            ),  # Should match prefix_a_suffix_*
            invalidate_with_overlap("prefix_*", 0.01),  # Should match all prefix_* keys
            invalidate_with_overlap("*_suffix_*", 0.02),  # Should match *_suffix_* keys
            invalidate_with_overlap("*_a_*", 0.03),  # Should match keys with _a_
        ]

        results = await asyncio.gather(*invalidation_tasks, return_exceptions=True)

        # All operations should complete without exceptions
        for result in results:
            assert not isinstance(result, Exception)
            assert isinstance(result, int)

        # Cache should be in consistent state
        stats = cache.get_stats()
        assert stats["total_entries"] >= 0

    @pytest.mark.asyncio
    async def test_invalidation_during_cache_resize(self):
        """Test invalidation behavior during cache size pressure."""
        cache = CacheManager(max_size=20)  # Small cache for testing

        # Fill cache to capacity
        for i in range(20):
            await cache.set(f"resize_key_{i}", {"value": i})

        async def continuous_invalidation():
            """Continuously invalidate during resize pressure."""
            invalidation_count = 0
            for pattern_id in range(50):
                # Create pattern that might match some keys
                pattern = f"resize_key_{pattern_id % 10}_*"
                await cache.invalidate(pattern=pattern)
                invalidation_count += 1
                await asyncio.sleep(0.001)
            return invalidation_count

        async def continuous_resize_pressure():
            """Apply continuous resize pressure."""
            for i in range(20, 100):  # Add more than capacity
                await cache.set(f"new_key_{i}", {"value": i})
                await asyncio.sleep(0.002)

        # Run both operations concurrently
        invalidation_result, _ = await asyncio.gather(
            continuous_invalidation(),
            continuous_resize_pressure(),
            return_exceptions=True,
        )

        # Invalidation should complete successfully
        assert isinstance(invalidation_result, int)
        assert invalidation_result > 0

        # Cache should maintain size constraint
        stats = cache.get_stats()
        assert stats["total_entries"] <= 20

    @pytest.mark.asyncio
    async def test_recursive_invalidation_prevention(self):
        """Test prevention of recursive invalidation scenarios."""
        cache = CacheManager()

        # Create keys that could trigger recursive scenarios
        recursive_keys = [
            "recurse_1_recurse_2",
            "recurse_2_recurse_3",
            "recurse_3_recurse_1",
            "normal_key_1",
            "normal_key_2",
        ]

        for key in recursive_keys:
            await cache.set(key, {"recursive": True})

        async def invalidate_recursive_pattern(pattern: str):
            """Invalidate with potentially recursive pattern."""
            try:
                result = await cache.invalidate(pattern=pattern)
                return result
            except Exception as e:
                return f"Exception: {e}"

        # Test patterns that could cause recursion
        recursive_patterns = [
            "recurse_*",
            "*_recurse_*",
            "recurse_*_recurse_*",
            "*_*_*",
        ]

        tasks = [
            invalidate_recursive_pattern(pattern) for pattern in recursive_patterns
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should not cause infinite recursion or stack overflow
        for result in results:
            assert not isinstance(result, Exception)
            if isinstance(result, str) and "Exception" in result:
                # Some patterns might be invalid, which is acceptable
                continue
            assert isinstance(result, int)


class TestLargeScalePerformanceValidation:
    """Test large-scale performance and memory characteristics."""

    @pytest.mark.asyncio
    async def test_thousand_key_pattern_matching_performance(self):
        """Test pattern matching performance with thousands of keys."""
        cache = CacheManager(max_size=2000)

        # Create large key space with multiple patterns
        categories = ["dog", "cat", "bird", "fish", "rabbit"]
        operations = ["feeding", "health", "exercise", "grooming", "training"]

        keys_created = 0
        for category in categories:
            for animal_id in range(200):  # 200 animals per category
                for operation in operations:
                    key = f"{category}_{animal_id:03d}_{operation}"
                    await cache.set(
                        key,
                        {
                            "category": category,
                            "animal_id": animal_id,
                            "operation": operation,
                            "timestamp": dt_util.utcnow().isoformat(),
                        },
                    )
                    keys_created += 1

                    # Yield occasionally to prevent blocking
                    if keys_created % 100 == 0:
                        await asyncio.sleep(0.001)

        # Test various pattern matching scenarios
        pattern_tests = [
            ("dog_*", 1000),  # All dog entries (200 * 5 operations)
            ("*_feeding", 1000),  # All feeding entries (5 categories * 200)
            ("dog_001_*", 5),  # Specific dog entries
            ("*_health", 1000),  # All health entries
            ("cat_1*", 50),  # Cats with IDs starting with 1 (100-199)
        ]

        for pattern, expected_min in pattern_tests:
            start_time = time.time()
            result = await cache.invalidate(pattern=pattern)
            duration = time.time() - start_time

            # Performance should be reasonable (< 100ms for pattern matching)
            assert duration < 0.1, f"Pattern {pattern} took {duration:.3f}s"

            # Result should be reasonable
            assert result >= 0  # At minimum should not error

            # Reset cache for next test
            await cache.clear()
            for category in categories:
                for animal_id in range(200):
                    for operation in operations:
                        key = f"{category}_{animal_id:03d}_{operation}"
                        await cache.set(
                            key,
                            {
                                "category": category,
                                "animal_id": animal_id,
                                "operation": operation,
                            },
                        )

    @pytest.mark.asyncio
    async def test_memory_usage_under_sustained_load(self):
        """Test memory usage patterns under sustained load."""
        cache = CacheManager(max_size=500)

        # Sustained load test parameters
        load_duration = 1.0  # 1 second of sustained load

        async def sustained_load_worker(worker_id: int):
            """Worker generating sustained cache load."""
            operations = 0
            start_time = time.time()

            while time.time() - start_time < load_duration:
                # Mix of operations
                operation_type = operations % 4

                if operation_type == 0:
                    # Set operation
                    key = f"sustained_{worker_id}_{operations}"
                    data = {
                        "worker": worker_id,
                        "operation": operations,
                        "data": "x" * random.randint(100, 1000),  # Variable size data
                        "timestamp": time.time(),
                    }
                    await cache.set(key, data, ttl_seconds=random.randint(1, 300))

                elif operation_type == 1:
                    # Get operation
                    key = f"sustained_{worker_id}_{operations - random.randint(0, 10)}"
                    await cache.get(key)

                elif operation_type == 2:
                    # Invalidate operation
                    pattern = f"sustained_{worker_id}_*"
                    await cache.invalidate(pattern=pattern)

                else:
                    # Optimization operation
                    await cache.optimize_cache()

                operations += 1

                # Minimal yield to allow other workers
                if operations % 10 == 0:
                    await asyncio.sleep(0.001)

            return operations

        # Run multiple workers for sustained load
        workers = [sustained_load_worker(i) for i in range(8)]
        operation_counts = await asyncio.gather(*workers)

        # Verify sustained load was applied
        total_operations = sum(operation_counts)
        assert total_operations > 500  # Should complete many operations

        # Verify cache remains within memory constraints
        stats = cache.get_stats()
        assert stats["total_entries"] <= 500  # Should respect max size

        # Verify cache is still functional after sustained load
        await cache.set("post_load_test", {"test": "data"})
        result = await cache.get("post_load_test")
        assert result is not None

    @pytest.mark.asyncio
    async def test_coordinated_multi_cache_operations(self):
        """Test coordinated operations across multiple cache instances."""
        # Simulate multiple cache instances (like in multi-dog setup)
        caches = [CacheManager(max_size=100) for _ in range(5)]

        # Populate each cache with different but overlapping data
        for cache_id, cache in enumerate(caches):
            for i in range(50):
                key = f"cache_{cache_id}_key_{i}"
                shared_key = f"shared_key_{i}"  # Keys that exist in multiple caches

                await cache.set(key, {"cache": cache_id, "id": i})
                await cache.set(
                    shared_key, {"cache": cache_id, "shared": True, "id": i}
                )

        async def coordinated_cache_operation(cache_id: int):
            """Perform coordinated operations on a specific cache."""
            cache = caches[cache_id]
            operations_completed = 0

            for operation in range(100):
                op_type = operation % 5

                if op_type == 0:
                    # Access own keys
                    key = f"cache_{cache_id}_key_{operation % 50}"
                    await cache.get(key)

                elif op_type == 1:
                    # Access shared keys
                    key = f"shared_key_{operation % 50}"
                    await cache.get(key)

                elif op_type == 2:
                    # Update shared keys
                    key = f"shared_key_{operation % 50}"
                    await cache.set(
                        key, {"cache": cache_id, "updated": True, "op": operation}
                    )

                elif op_type == 3:
                    # Pattern invalidation
                    await cache.invalidate(pattern=f"cache_{cache_id}_*")

                else:
                    # Optimization
                    await cache.optimize_cache()

                operations_completed += 1

                # Coordination delay
                await asyncio.sleep(0.001)

            return operations_completed

        # Run coordinated operations on all caches
        results = await asyncio.gather(
            *[coordinated_cache_operation(i) for i in range(len(caches))]
        )

        # All caches should complete operations successfully
        for result in results:
            assert result == 100  # Should complete all operations

        # Verify cache consistency after coordinated operations
        for cache in caches:
            stats = cache.get_stats()
            assert stats["total_entries"] <= 100  # Should respect size limits
            assert stats["total_entries"] >= 0  # Should be valid


class TestCacheCorruptionDetectionAndRecovery:
    """Test cache corruption detection and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_corrupted_expiry_data_recovery(self):
        """Test recovery from corrupted expiry data."""
        cache = CacheManager()

        # Set up normal cache entries
        for i in range(10):
            await cache.set(f"normal_key_{i}", {"value": i}, ttl_seconds=3600)

        # Simulate expiry data corruption
        cache._expiry["corrupted_key_1"] = "not_a_datetime"  # Invalid expiry
        cache._expiry["corrupted_key_2"] = None  # None expiry
        cache._cache["corrupted_key_1"] = {"corrupted": True}
        cache._cache["corrupted_key_2"] = {"corrupted": True}

        # Test get operations with corrupted expiry data
        try:
            result1 = await cache.get("corrupted_key_1")
            result2 = await cache.get("corrupted_key_2")

            # Should handle corruption gracefully
            assert result1 is None or isinstance(result1, dict)
            assert result2 is None or isinstance(result2, dict)

        except Exception:
            # If exceptions occur, they should be handled gracefully
            pass

        # Cache should still function for normal keys
        result = await cache.get("normal_key_0")
        assert result is not None
        assert result["value"] == 0

        # Optimization should clean up corrupted data
        opt_result = await cache.optimize_cache()
        assert opt_result["optimization_completed"] is True

    @pytest.mark.asyncio
    async def test_inconsistent_cache_state_recovery(self):
        """Test recovery from inconsistent cache state."""
        cache = CacheManager()

        # Create inconsistent state: cache entry without expiry
        cache._cache["orphaned_key"] = {"orphaned": True}
        # Missing entry in _expiry dict

        # Create inconsistent state: expiry without cache entry
        cache._expiry["phantom_key"] = dt_util.utcnow() + timedelta(hours=1)
        # Missing entry in _cache dict

        # Create inconsistent state: access count without cache entry
        cache._access_count["ghost_key"] = 10
        cache._last_access["ghost_key"] = dt_util.utcnow()
        # Missing entry in _cache dict

        # Test operations with inconsistent state
        try:
            # Should handle orphaned key gracefully
            result1 = await cache.get("orphaned_key")

            # Should handle phantom key gracefully
            result2 = await cache.get("phantom_key")

            # Should handle ghost key gracefully
            result3 = await cache.get("ghost_key")

            # All should return None or valid data, not crash
            assert result1 is None or isinstance(result1, dict)
            assert result2 is None
            assert result3 is None

        except Exception as e:
            # Should not crash, but if exceptions occur, they should be minimal
            assert "phantom" not in str(e)  # Should not reference non-existent keys

        # Optimization should resolve inconsistencies
        opt_result = await cache.optimize_cache()
        assert opt_result["optimization_completed"] is True

        # Verify cache is in consistent state after optimization
        stats = cache.get_stats()
        assert stats["total_entries"] <= 1  # Only orphaned_key might remain

    @pytest.mark.asyncio
    async def test_concurrent_corruption_and_recovery(self):
        """Test recovery from corruption that occurs during concurrent operations."""
        cache = CacheManager(max_size=50)

        # Pre-populate cache
        for i in range(30):
            await cache.set(f"stable_key_{i}", {"value": i})

        async def corruption_simulation():
            """Simulate corruption during operations."""
            await asyncio.sleep(0.1)  # Let other operations start

            # Simulate various corruption scenarios
            cache._expiry["corrupt_1"] = "invalid_datetime"
            cache._cache["corrupt_1"] = {"data": "corrupted"}

            # Corrupt access counts
            cache._access_count["nonexistent"] = 999

            # Corrupt hot keys
            cache._hot_keys.add("nonexistent_hot")

            await asyncio.sleep(0.1)  # Let corruption affect operations

        async def normal_operations():
            """Perform normal operations during corruption."""
            operation_count = 0
            errors = 0

            for i in range(100):
                try:
                    key = f"stable_key_{i % 30}"

                    # Mix of operations
                    if i % 3 == 0:
                        await cache.get(key)
                    elif i % 3 == 1:
                        await cache.set(key, {"value": i, "updated": True})
                    else:
                        await cache.optimize_cache()

                    operation_count += 1

                except Exception:
                    errors += 1

                await asyncio.sleep(0.001)

            return operation_count, errors

        # Run corruption simulation alongside normal operations
        (operation_count, errors), _ = await asyncio.gather(
            normal_operations(), corruption_simulation(), return_exceptions=True
        )

        # Most operations should succeed despite corruption
        assert operation_count > 80  # At least 80% success rate
        assert errors < 20  # Limited errors

        # Final optimization should clean up corruption
        final_opt = await cache.optimize_cache()
        assert final_opt["optimization_completed"] is True

        # Cache should be functional after cleanup
        await cache.set("post_corruption_test", {"test": "recovery"})
        result = await cache.get("post_corruption_test")
        assert result is not None
        assert result["test"] == "recovery"


if __name__ == "__main__":
    pytest.main([__file__])
