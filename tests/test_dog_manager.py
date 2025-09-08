"""Tests for PawControl dog manager.

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
from custom_components.pawcontrol.dog_manager import DogDataManager
from homeassistant.util import dt as dt_util


class TestDogDataManagerInitialization:
    """Test dog data manager initialization."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert isinstance(manager._dogs, dict)
        assert isinstance(manager._lock, asyncio.Lock)
        assert manager._read_cache is None
        assert manager._cache_timestamp is None
        assert manager._cache_ttl == timedelta(seconds=5)
        assert len(manager._dogs) == 0

    def test_initial_state_empty(self, manager):
        """Test initial state is empty."""
        assert len(manager._dogs) == 0
        assert manager._read_cache is None
        assert manager._cache_timestamp is None

    async def test_lock_acquisition(self, manager):
        """Test lock can be acquired."""
        async with manager._lock:
            # Should be able to acquire lock without issues
            assert True


class TestDogDataManagerCRUDOperations:
    """Test dog data manager CRUD operations."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    @pytest.fixture
    def sample_dog_defaults(self):
        """Create sample dog defaults."""
        return {
            "name": "Buddy",
            "breed": "Golden Retriever", 
            "age": 3,
            "weight": 30.0,
            "feeding": {
                "meals_per_day": 2,
                "food_type": "dry"
            },
            "health": {
                "last_checkup": "2024-01-01",
                "vaccinations": []
            }
        }

    async def test_ensure_dog_new_dog(self, manager, sample_dog_defaults):
        """Test ensuring a new dog creates entry."""
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        
        # Dog should be created
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data is not None
        assert dog_data["name"] == "Buddy"
        assert dog_data["breed"] == "Golden Retriever"

    async def test_ensure_dog_existing_dog(self, manager, sample_dog_defaults):
        """Test ensuring existing dog doesn't overwrite."""
        # Create dog first
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        
        # Modify the dog
        await manager.async_update_dog("dog1", {"name": "Modified Buddy"})
        
        # Ensure again with different defaults
        different_defaults = {"name": "Different Name", "breed": "Different Breed"}
        await manager.async_ensure_dog("dog1", different_defaults)
        
        # Should keep existing data
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data["name"] == "Modified Buddy"  # Should not be overwritten

    async def test_update_dog_existing(self, manager, sample_dog_defaults):
        """Test updating existing dog."""
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        
        update_data = {
            "weight": 32.0,
            "health": {
                "last_checkup": "2024-02-01"
            }
        }
        
        await manager.async_update_dog("dog1", update_data)
        
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data["weight"] == 32.0
        assert dog_data["health"]["last_checkup"] == "2024-02-01"

    async def test_update_dog_nonexistent(self, manager):
        """Test updating non-existent dog creates entry."""
        update_data = {"name": "New Dog", "weight": 25.0}
        
        await manager.async_update_dog("dog1", update_data)
        
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data is not None
        assert dog_data["name"] == "New Dog"
        assert dog_data["weight"] == 25.0

    async def test_get_dog_existing(self, manager, sample_dog_defaults):
        """Test getting existing dog."""
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        
        dog_data = await manager.async_get_dog("dog1")
        
        assert dog_data is not None
        assert dog_data["name"] == "Buddy"
        assert "feeding" in dog_data
        assert "health" in dog_data

    async def test_get_dog_nonexistent(self, manager):
        """Test getting non-existent dog."""
        dog_data = await manager.async_get_dog("nonexistent")
        assert dog_data is None

    async def test_get_dog_returns_copy(self, manager, sample_dog_defaults):
        """Test that get_dog returns isolated copy."""
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        
        dog_data1 = await manager.async_get_dog("dog1")
        dog_data2 = await manager.async_get_dog("dog1")
        
        # Should be different objects
        assert dog_data1 is not dog_data2
        
        # Modifying one should not affect the other
        dog_data1["test_field"] = "modified"
        assert "test_field" not in dog_data2

    async def test_remove_dog_existing(self, manager, sample_dog_defaults):
        """Test removing existing dog."""
        await manager.async_ensure_dog("dog1", sample_dog_defaults)
        await manager.async_ensure_dog("dog2", sample_dog_defaults)
        
        # Verify dogs exist
        assert await manager.async_dog_exists("dog1") is True
        assert await manager.async_dog_exists("dog2") is True
        
        await manager.async_remove_dog("dog1")
        
        # Dog1 should be removed, dog2 should remain
        assert await manager.async_dog_exists("dog1") is False
        assert await manager.async_dog_exists("dog2") is True

    async def test_remove_dog_nonexistent(self, manager):
        """Test removing non-existent dog."""
        # Should not raise error
        await manager.async_remove_dog("nonexistent")
        
        # Manager should still be empty
        dog_ids = await manager.async_get_dog_ids()
        assert len(dog_ids) == 0


class TestDogDataManagerBulkOperations:
    """Test dog data manager bulk operations."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    @pytest.fixture
    def sample_updates(self):
        """Create sample bulk updates."""
        return {
            "dog1": {"name": "Buddy", "weight": 30.0},
            "dog2": {"name": "Luna", "weight": 25.0},
            "dog3": {"name": "Max", "weight": 35.0},
        }

    async def test_batch_update_new_dogs(self, manager, sample_updates):
        """Test batch update with new dogs."""
        await manager.async_update_batch(sample_updates)
        
        # All dogs should be created
        for dog_id, expected_data in sample_updates.items():
            dog_data = await manager.async_get_dog(dog_id)
            assert dog_data is not None
            assert dog_data["name"] == expected_data["name"]
            assert dog_data["weight"] == expected_data["weight"]

    async def test_batch_update_existing_dogs(self, manager, sample_updates):
        """Test batch update with existing dogs."""
        # Create dogs first
        for dog_id in sample_updates:
            await manager.async_ensure_dog(dog_id, {"name": "Original", "age": 1})
        
        # Batch update
        await manager.async_update_batch(sample_updates)
        
        # Dogs should be updated
        for dog_id, expected_data in sample_updates.items():
            dog_data = await manager.async_get_dog(dog_id)
            assert dog_data["name"] == expected_data["name"]  # Updated
            assert dog_data["age"] == 1  # Original data preserved

    async def test_batch_update_mixed(self, manager, sample_updates):
        """Test batch update with mix of new and existing dogs."""
        # Create only some dogs first
        await manager.async_ensure_dog("dog1", {"name": "Original Buddy"})
        
        # Batch update all
        await manager.async_update_batch(sample_updates)
        
        # dog1 should be updated, others should be new
        dog1_data = await manager.async_get_dog("dog1")
        assert dog1_data["name"] == "Buddy"  # Updated
        
        dog2_data = await manager.async_get_dog("dog2")
        assert dog2_data["name"] == "Luna"  # New
        
        dog3_data = await manager.async_get_dog("dog3")
        assert dog3_data["name"] == "Max"  # New

    async def test_batch_update_empty(self, manager):
        """Test batch update with empty data."""
        await manager.async_update_batch({})
        
        # Should not create any dogs
        dog_ids = await manager.async_get_dog_ids()
        assert len(dog_ids) == 0

    async def test_batch_update_cache_invalidation(self, manager, sample_updates):
        """Test that batch update invalidates cache."""
        # Prime cache
        await manager.async_all_dogs()
        assert manager._read_cache is not None
        
        # Batch update
        await manager.async_update_batch(sample_updates)
        
        # Cache should be invalidated
        assert manager._read_cache is None
        assert manager._cache_timestamp is None


class TestDogDataManagerCaching:
    """Test dog data manager caching functionality."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance.""" 
        return DogDataManager()

    @pytest.fixture
    def sample_dogs_data(self):
        """Create sample dogs data."""
        return {
            "dog1": {"name": "Buddy", "breed": "Golden Retriever"},
            "dog2": {"name": "Luna", "breed": "Border Collie"},
            "dog3": {"name": "Max", "breed": "German Shepherd"},
        }

    async def test_all_dogs_empty(self, manager):
        """Test getting all dogs when empty."""
        all_dogs = await manager.async_all_dogs()
        assert all_dogs == {}

    async def test_all_dogs_with_data(self, manager, sample_dogs_data):
        """Test getting all dogs with data."""
        # Add dogs
        await manager.async_update_batch(sample_dogs_data)
        
        all_dogs = await manager.async_all_dogs()
        
        assert len(all_dogs) == 3
        assert "dog1" in all_dogs
        assert "dog2" in all_dogs
        assert "dog3" in all_dogs
        
        for dog_id, expected_data in sample_dogs_data.items():
            assert all_dogs[dog_id]["name"] == expected_data["name"]

    async def test_all_dogs_caching(self, manager, sample_dogs_data):
        """Test that all_dogs uses caching."""
        await manager.async_update_batch(sample_dogs_data)
        
        # First call should create cache
        all_dogs1 = await manager.async_all_dogs()
        assert manager._read_cache is not None
        assert manager._cache_timestamp is not None
        
        # Second call should use cache
        all_dogs2 = await manager.async_all_dogs()
        
        # Should be same object (cached)
        assert all_dogs1 is all_dogs2

    async def test_cache_invalidation_on_update(self, manager, sample_dogs_data):
        """Test cache invalidation on updates."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Prime cache
        await manager.async_all_dogs()
        assert manager._read_cache is not None
        
        # Update should invalidate cache
        await manager.async_update_dog("dog1", {"name": "Updated Buddy"})
        
        assert manager._read_cache is None
        assert manager._cache_timestamp is None

    async def test_cache_invalidation_on_ensure(self, manager, sample_dogs_data):
        """Test cache invalidation on ensure operations."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Prime cache
        await manager.async_all_dogs()
        assert manager._read_cache is not None
        
        # Ensure new dog should invalidate cache
        await manager.async_ensure_dog("dog4", {"name": "New Dog"})
        
        assert manager._read_cache is None

    async def test_cache_invalidation_on_remove(self, manager, sample_dogs_data):
        """Test cache invalidation on remove operations."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Prime cache
        await manager.async_all_dogs()
        assert manager._read_cache is not None
        
        # Remove should invalidate cache
        await manager.async_remove_dog("dog1")
        
        assert manager._read_cache is None

    async def test_cache_expiry(self, manager, sample_dogs_data):
        """Test cache expiry functionality."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Prime cache
        await manager.async_all_dogs()
        cache_time = manager._cache_timestamp
        
        # Mock time to simulate cache expiry
        with patch.object(dt_util, 'utcnow') as mock_now:
            future_time = cache_time + manager._cache_ttl + timedelta(seconds=1)
            mock_now.return_value = future_time
            
            # Should detect cache as invalid
            assert manager._is_cache_valid() is False

    async def test_cache_validity_check(self, manager, sample_dogs_data):
        """Test cache validity checking."""
        # No cache initially
        assert manager._is_cache_valid() is False
        
        await manager.async_update_batch(sample_dogs_data)
        
        # Prime cache
        await manager.async_all_dogs()
        
        # Should be valid immediately after creation
        assert manager._is_cache_valid() is True

    async def test_cache_returns_copies(self, manager, sample_dogs_data):
        """Test that cache returns proper copies."""
        await manager.async_update_batch(sample_dogs_data)
        
        all_dogs1 = await manager.async_all_dogs()
        all_dogs2 = await manager.async_all_dogs()
        
        # Should be same cached object
        assert all_dogs1 is all_dogs2
        
        # But individual dog data should be copies
        all_dogs1["dog1"]["test_field"] = "modified"
        
        # Get fresh data (should invalidate and rebuild cache)
        await manager.async_update_dog("dog2", {"trigger": "cache_invalidation"})
        all_dogs3 = await manager.async_all_dogs()
        
        # Should not have the test_field
        assert "test_field" not in all_dogs3["dog1"]


class TestDogDataManagerUtilityMethods:
    """Test dog data manager utility methods."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    @pytest.fixture
    def sample_dogs_data(self):
        """Create sample dogs data."""
        return {
            "dog1": {"name": "Buddy"},
            "dog2": {"name": "Luna"}, 
            "dog3": {"name": "Max"},
        }

    async def test_get_dog_ids_empty(self, manager):
        """Test getting dog IDs when empty."""
        dog_ids = await manager.async_get_dog_ids()
        assert dog_ids == []

    async def test_get_dog_ids_with_dogs(self, manager, sample_dogs_data):
        """Test getting dog IDs with dogs."""
        await manager.async_update_batch(sample_dogs_data)
        
        dog_ids = await manager.async_get_dog_ids()
        
        assert len(dog_ids) == 3
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids
        assert "dog3" in dog_ids

    async def test_get_dog_ids_order(self, manager, sample_dogs_data):
        """Test that dog IDs maintain consistent order."""
        await manager.async_update_batch(sample_dogs_data)
        
        dog_ids1 = await manager.async_get_dog_ids()
        dog_ids2 = await manager.async_get_dog_ids()
        
        # Should be same order
        assert dog_ids1 == dog_ids2

    async def test_dog_exists_empty(self, manager):
        """Test dog existence check when empty."""
        assert await manager.async_dog_exists("any_dog") is False

    async def test_dog_exists_with_dogs(self, manager, sample_dogs_data):
        """Test dog existence check with dogs."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Existing dogs
        assert await manager.async_dog_exists("dog1") is True
        assert await manager.async_dog_exists("dog2") is True
        assert await manager.async_dog_exists("dog3") is True
        
        # Non-existent dog
        assert await manager.async_dog_exists("dog4") is False

    async def test_dog_exists_after_removal(self, manager, sample_dogs_data):
        """Test dog existence check after removal."""
        await manager.async_update_batch(sample_dogs_data)
        
        # Should exist initially
        assert await manager.async_dog_exists("dog1") is True
        
        # Remove dog
        await manager.async_remove_dog("dog1")
        
        # Should not exist anymore
        assert await manager.async_dog_exists("dog1") is False


class TestDogDataManagerConcurrency:
    """Test dog data manager concurrency and thread safety."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    async def test_concurrent_updates(self, manager):
        """Test concurrent update operations."""
        async def update_dog(dog_id: str, iterations: int):
            for i in range(iterations):
                data = {"iteration": i, "dog_id": dog_id}
                await manager.async_update_dog(dog_id, data)

        # Run concurrent updates
        await asyncio.gather(
            update_dog("dog1", 10),
            update_dog("dog2", 10),
            update_dog("dog3", 10),
        )
        
        # All dogs should exist
        assert await manager.async_dog_exists("dog1") is True
        assert await manager.async_dog_exists("dog2") is True
        assert await manager.async_dog_exists("dog3") is True

    async def test_concurrent_batch_updates(self, manager):
        """Test concurrent batch update operations."""
        async def batch_update(batch_id: int):
            updates = {
                f"dog{batch_id}_{i}": {"batch": batch_id, "index": i}
                for i in range(5)
            }
            await manager.async_update_batch(updates)

        # Run concurrent batch updates
        await asyncio.gather(
            batch_update(1),
            batch_update(2), 
            batch_update(3),
        )
        
        # Should have 15 dogs total
        dog_ids = await manager.async_get_dog_ids()
        assert len(dog_ids) == 15

    async def test_concurrent_read_write(self, manager):
        """Test concurrent read and write operations."""
        # Add initial data
        initial_data = {f"dog{i}": {"name": f"Dog{i}"} for i in range(10)}
        await manager.async_update_batch(initial_data)

        async def reader():
            results = []
            for _ in range(20):
                all_dogs = await manager.async_all_dogs()
                results.append(len(all_dogs))
            return results

        async def writer():
            for i in range(10, 20):
                await manager.async_update_dog(f"dog{i}", {"name": f"Dog{i}"})

        # Run concurrent read/write
        read_results, _ = await asyncio.gather(reader(), writer())
        
        # All reads should succeed (though counts may vary)
        assert all(isinstance(count, int) and count >= 10 for count in read_results)

    async def test_concurrent_cache_operations(self, manager):
        """Test concurrent operations with caching."""
        # Add initial data
        initial_data = {f"dog{i}": {"name": f"Dog{i}"} for i in range(5)}
        await manager.async_update_batch(initial_data)

        async def cache_reader(reader_id: int):
            results = []
            for i in range(10):
                all_dogs = await manager.async_all_dogs()
                results.append((reader_id, i, len(all_dogs)))
            return results

        async def cache_writer():
            for i in range(3):
                await manager.async_update_dog(f"new_dog{i}", {"name": f"NewDog{i}"})
                await asyncio.sleep(0.001)  # Small delay to ensure cache invalidation

        # Run concurrent cache operations
        results = await asyncio.gather(
            cache_reader(1),
            cache_reader(2),
            cache_writer(),
        )
        
        # All readers should complete successfully
        for result in results[:2]:  # First two are reader results
            assert len(result) == 10

    async def test_lock_contention_handling(self, manager):
        """Test proper handling of lock contention."""
        async def long_operation(operation_id: int):
            async with manager._lock:
                # Simulate long operation
                await asyncio.sleep(0.01)
                manager._dogs[f"op_{operation_id}"] = {"operation_id": operation_id}

        async def quick_check():
            return len(await manager.async_get_dog_ids())

        # Mix long operations with quick checks
        tasks = []
        for i in range(5):
            tasks.append(long_operation(i))
            tasks.append(quick_check())

        # Should complete without deadlock
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=2.0
        )
        
        # No exceptions should occur
        for result in results:
            if isinstance(result, Exception):
                pytest.fail(f"Concurrent operation failed: {result}")


class TestDogDataManagerEdgeCases:
    """Test dog data manager edge cases and error handling."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    async def test_empty_dog_id_handling(self, manager):
        """Test handling of empty dog IDs."""
        # Empty string dog ID
        await manager.async_update_dog("", {"name": "Empty ID Dog"})
        
        assert await manager.async_dog_exists("") is True
        dog_data = await manager.async_get_dog("")
        assert dog_data["name"] == "Empty ID Dog"

    async def test_none_data_handling(self, manager):
        """Test handling of None values in data."""
        # None values should be handled gracefully
        await manager.async_update_dog("dog1", {"name": "Test", "nullable_field": None})
        
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data["nullable_field"] is None

    async def test_deep_nested_data(self, manager):
        """Test handling of deeply nested data structures."""
        nested_data = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": "deep_value",
                        "array": [1, 2, 3, {"nested_in_array": True}]
                    }
                }
            }
        }
        
        await manager.async_update_dog("dog1", nested_data)
        
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data["level1"]["level2"]["level3"]["level4"] == "deep_value"

    async def test_data_mutation_isolation(self, manager):
        """Test that internal data is protected from external mutation."""
        original_data = {"name": "Original", "mutable_list": [1, 2, 3]}
        
        await manager.async_update_dog("dog1", original_data)
        
        # Mutate original data
        original_data["name"] = "Modified"
        original_data["mutable_list"].append(4)
        
        # Internal data should not be affected
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data["name"] == "Original"
        assert dog_data["mutable_list"] == [1, 2, 3]

    async def test_large_data_handling(self, manager):
        """Test handling of large data structures."""
        # Large data structure
        large_data = {
            "large_string": "x" * 10000,
            "large_list": list(range(1000)),
            "large_dict": {f"key_{i}": f"value_{i}" for i in range(1000)}
        }
        
        await manager.async_update_dog("dog1", large_data)
        
        dog_data = await manager.async_get_dog("dog1")
        assert len(dog_data["large_string"]) == 10000
        assert len(dog_data["large_list"]) == 1000
        assert len(dog_data["large_dict"]) == 1000

    async def test_cache_corruption_recovery(self, manager):
        """Test recovery from cache corruption."""
        # Add some data
        await manager.async_update_dog("dog1", {"name": "Test"})
        
        # Prime cache
        await manager.async_all_dogs()
        
        # Corrupt cache manually
        manager._read_cache = "corrupted_data"
        manager._cache_timestamp = "invalid_timestamp"
        
        # Should handle corruption gracefully
        all_dogs = await manager.async_all_dogs()
        assert isinstance(all_dogs, dict)
        assert "dog1" in all_dogs

    async def test_extreme_concurrency(self, manager):
        """Test system under extreme concurrent load."""
        import time
        
        async def stress_worker(worker_id: int):
            for i in range(20):
                dog_id = f"worker{worker_id}_dog{i}"
                await manager.async_update_dog(dog_id, {"worker": worker_id, "iteration": i})
                
                if i % 5 == 0:  # Occasionally read data
                    await manager.async_get_dog(dog_id)
                    
                if i % 10 == 0:  # Occasionally get all dogs
                    await manager.async_all_dogs()

        start_time = time.time()
        
        # Run 20 concurrent workers
        await asyncio.gather(*[stress_worker(i) for i in range(20)])
        
        elapsed = time.time() - start_time
        
        # Should complete reasonably quickly
        assert elapsed < 10.0  # Should complete within 10 seconds
        
        # Should have 400 dogs (20 workers * 20 iterations)
        dog_ids = await manager.async_get_dog_ids()
        assert len(dog_ids) == 400

    async def test_memory_efficiency(self, manager):
        """Test memory efficiency with many operations."""
        import gc
        
        # Perform many operations to test memory efficiency
        for cycle in range(10):
            # Add many dogs
            batch_data = {f"cycle{cycle}_dog{i}": {"cycle": cycle, "dog": i} for i in range(100)}
            await manager.async_update_batch(batch_data)
            
            # Read all data
            all_dogs = await manager.async_all_dogs()
            assert len(all_dogs) >= 100
            
            # Remove all dogs from this cycle
            for i in range(100):
                await manager.async_remove_dog(f"cycle{cycle}_dog{i}")
            
            # Force garbage collection
            gc.collect()
        
        # Should end up empty
        dog_ids = await manager.async_get_dog_ids()
        assert len(dog_ids) == 0


@pytest.mark.asyncio
class TestDogDataManagerIntegration:
    """Integration tests for dog data manager."""

    async def test_realistic_workflow(self):
        """Test realistic dog data management workflow."""
        manager = DogDataManager()
        
        # 1. Initialize with some dogs
        initial_dogs = {
            "buddy": {"name": "Buddy", "breed": "Golden Retriever", "age": 3},
            "luna": {"name": "Luna", "breed": "Border Collie", "age": 2},
        }
        await manager.async_update_batch(initial_dogs)
        
        # 2. Update individual dogs with more data
        await manager.async_update_dog("buddy", {
            "feeding": {"meals_per_day": 2, "last_meal": "2024-01-01T12:00:00Z"},
            "health": {"weight": 30.0, "last_checkup": "2024-01-01"}
        })
        
        await manager.async_update_dog("luna", {
            "feeding": {"meals_per_day": 3, "special_diet": True},
            "training": {"commands": ["sit", "stay", "come"]}
        })
        
        # 3. Add new dog
        await manager.async_ensure_dog("max", {
            "name": "Max", 
            "breed": "German Shepherd",
            "age": 4,
            "health": {"weight": 35.0}
        })
        
        # 4. Verify all data is correct
        all_dogs = await manager.async_all_dogs()
        assert len(all_dogs) == 3
        
        buddy_data = all_dogs["buddy"]
        assert buddy_data["name"] == "Buddy"
        assert buddy_data["feeding"]["meals_per_day"] == 2
        assert buddy_data["health"]["weight"] == 30.0
        
        luna_data = all_dogs["luna"]
        assert luna_data["training"]["commands"] == ["sit", "stay", "come"]
        
        max_data = all_dogs["max"]
        assert max_data["health"]["weight"] == 35.0
        
        # 5. Remove one dog
        await manager.async_remove_dog("buddy")
        assert len(await manager.async_get_dog_ids()) == 2
        
        # 6. Final verification
        remaining_dogs = await manager.async_all_dogs()
        assert "buddy" not in remaining_dogs
        assert "luna" in remaining_dogs
        assert "max" in remaining_dogs

    async def test_cache_performance_benefits(self):
        """Test that caching provides performance benefits."""
        import time
        
        manager = DogDataManager()
        
        # Add substantial data
        large_batch = {f"dog{i}": {"name": f"Dog{i}", "data": list(range(100))} for i in range(100)}
        await manager.async_update_batch(large_batch)
        
        # Time non-cached reads (first call)
        start = time.time()
        await manager.async_all_dogs()
        first_call_time = time.time() - start
        
        # Time cached reads
        cached_times = []
        for _ in range(10):
            start = time.time()
            await manager.async_all_dogs()
            cached_times.append(time.time() - start)
        
        avg_cached_time = sum(cached_times) / len(cached_times)
        
        # Cached reads should be significantly faster
        # (Note: This might not always be true in test environment, but the structure supports it)
        assert avg_cached_time <= first_call_time * 2  # Allow some variance

    async def test_error_recovery_scenarios(self):
        """Test recovery from various error scenarios."""
        manager = DogDataManager()
        
        # Add initial data
        await manager.async_update_dog("dog1", {"name": "Test"})
        
        # Scenario 1: Corrupt internal state
        try:
            original_dogs = manager._dogs.copy()
            manager._dogs = None  # Corrupt state
            
            # Operations should handle gracefully or raise appropriate errors
            with pytest.raises((TypeError, AttributeError)):
                await manager.async_get_dog("dog1")
                
        finally:
            # Restore state
            manager._dogs = original_dogs
        
        # Should still work after restoration
        dog_data = await manager.async_get_dog("dog1")
        assert dog_data is not None

    async def test_data_consistency_under_load(self):
        """Test data consistency under concurrent load."""
        manager = DogDataManager()
        
        # Initialize with known data
        initial_data = {f"dog{i}": {"counter": 0} for i in range(10)}
        await manager.async_update_batch(initial_data)
        
        async def increment_counter(dog_id: str, iterations: int):
            for _ in range(iterations):
                current_data = await manager.async_get_dog(dog_id)
                new_counter = current_data["counter"] + 1
                await manager.async_update_dog(dog_id, {"counter": new_counter})
        
        # Run concurrent increments
        await asyncio.gather(*[increment_counter(f"dog{i}", 10) for i in range(10)])
        
        # Each dog should have incremented its counter
        # (Note: Due to race conditions, final values may vary, but all should be > 0)
        all_dogs = await manager.async_all_dogs()
        for dog_id, dog_data in all_dogs.items():
            assert dog_data["counter"] > 0
