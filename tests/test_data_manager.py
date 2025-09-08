"""Tests for the Paw Control data manager module."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch

import pytest
from custom_components.pawcontrol.const import (
    DEFAULT_DATA_RETENTION_DAYS,
    DOMAIN,
    STORAGE_VERSION,
)
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.exceptions import StorageError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util


class TestPawControlDataManager:
    """Test the Paw Control data manager."""

    @pytest.fixture
    def data_manager(self, hass: HomeAssistant):
        """Create a data manager instance."""
        return PawControlDataManager(hass, "test_entry")

    @pytest.fixture
    def mock_store(self):
        """Create a mock store."""
        store = Mock(spec=Store)
        store.async_load = AsyncMock(return_value={})
        store.async_save = AsyncMock()
        return store

    @pytest.mark.asyncio
    async def test_data_manager_initialization(self, hass: HomeAssistant):
        """Test data manager initialization."""
        data_manager = PawControlDataManager(hass, "test_entry")

        assert data_manager.hass == hass
        assert data_manager.entry_id == "test_entry"
        assert isinstance(data_manager._stores, dict)
        assert len(data_manager._stores) > 0
        assert "dogs" in data_manager._stores
        assert "feeding" in data_manager._stores
        assert "walks" in data_manager._stores
        assert "health" in data_manager._stores
        assert "gps" in data_manager._stores

    @pytest.mark.asyncio
    async def test_async_initialize_success(self, data_manager, mock_store):
        """Test successful initialization."""
        # Mock all stores
        for store_name in data_manager._stores:
            data_manager._stores[store_name] = mock_store

        with (
            patch.object(data_manager, "_load_initial_data") as mock_load,
            patch.object(data_manager, "_initialize_statistics") as mock_init_stats,
            patch("asyncio.create_task") as mock_create_task,
        ):
            await data_manager.async_initialize()

            mock_load.assert_called_once()
            mock_init_stats.assert_called_once()
            assert mock_create_task.call_count == 2  # cleanup and backup tasks

    @pytest.mark.asyncio
    async def test_async_initialize_failure(self, data_manager):
        """Test initialization failure."""
        with patch.object(
            data_manager, "_load_initial_data", side_effect=Exception("Load failed")
        ):
            with pytest.raises(StorageError, match="Load failed"):
                await data_manager.async_initialize()

    @pytest.mark.asyncio
    async def test_async_shutdown_success(self, data_manager):
        """Test successful shutdown."""
        # Mock background tasks
        cleanup_task = AsyncMock()
        backup_task = AsyncMock()
        data_manager._cleanup_task = cleanup_task
        data_manager._backup_task = backup_task

        with patch.object(data_manager, "_flush_cache_to_storage") as mock_flush:
            await data_manager.async_shutdown()

            cleanup_task.cancel.assert_called_once()
            backup_task.cancel.assert_called_once()
            mock_flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_shutdown_with_cancelled_tasks(self, data_manager):
        """Test shutdown with cancelled tasks."""
        # Mock tasks that are already cancelled
        cleanup_task = AsyncMock()
        cleanup_task.cancel.side_effect = asyncio.CancelledError()
        data_manager._cleanup_task = cleanup_task
        data_manager._backup_task = None

        # Should not raise exception
        await data_manager.async_shutdown()
        cleanup_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_initial_data_success(self, data_manager, mock_store):
        """Test successful initial data loading."""
        mock_store.async_load.side_effect = [
            {"dog1": {"name": "Dog 1"}},  # dogs store
            {"dog1": [{"meal": "breakfast"}]},  # feeding store
        ]

        data_manager._stores["dogs"] = mock_store
        data_manager._stores["feeding"] = mock_store

        await data_manager._load_initial_data()

        # Verify stores were loaded
        assert mock_store.async_load.call_count >= 2

    @pytest.mark.asyncio
    async def test_load_initial_data_empty_stores(self, data_manager, mock_store):
        """Test loading initial data with empty stores."""
        mock_store.async_load.return_value = None

        data_manager._stores["dogs"] = mock_store
        data_manager._stores["feeding"] = mock_store

        await data_manager._load_initial_data()

        # Should handle None return values gracefully
        assert mock_store.async_load.call_count >= 2

    @pytest.mark.asyncio
    async def test_async_get_dog_data_found(self, data_manager):
        """Test getting dog data when dog exists."""
        dog_data = {"dog_id": "test_dog", "name": "Test Dog"}

        with patch.object(
            data_manager, "_get_cache", return_value={"test_dog": dog_data}
        ):
            result = await data_manager.async_get_dog_data("test_dog")

            assert result == dog_data

    @pytest.mark.asyncio
    async def test_async_get_dog_data_not_found(self, data_manager):
        """Test getting dog data when dog doesn't exist."""
        with patch.object(data_manager, "_get_cache", return_value={}):
            result = await data_manager.async_get_dog_data("nonexistent_dog")

            assert result is None

    @pytest.mark.asyncio
    async def test_async_set_dog_data(self, data_manager, mock_store):
        """Test setting dog data."""
        data_manager._stores["dogs"] = mock_store

        dog_data = {"dog_id": "test_dog", "name": "Test Dog"}

        with (
            patch.object(data_manager, "_get_cache", return_value={}),
            patch.object(data_manager, "_set_cache") as mock_set_cache,
        ):
            await data_manager.async_set_dog_data("test_dog", dog_data)

            mock_set_cache.assert_called()
            mock_store.async_save.assert_called_once()
            assert data_manager._metrics["operations_count"] > 0

    @pytest.mark.asyncio
    async def test_async_update_dog_data(self, data_manager):
        """Test updating dog data."""
        existing_data = {"name": "Old Name", "age": 5}
        updates = {"age": 6, "weight": 25.0}

        with (
            patch.object(
                data_manager, "async_get_dog_data", return_value=existing_data
            ),
            patch.object(data_manager, "async_set_dog_data") as mock_set,
        ):
            await data_manager.async_update_dog_data("test_dog", updates)

            # Verify merged data was set
            mock_set.assert_called_once()
            call_args = mock_set.call_args[0]
            assert call_args[0] == "test_dog"
            merged_data = call_args[1]
            assert merged_data["name"] == "Old Name"  # Preserved
            assert merged_data["age"] == 6  # Updated
            assert merged_data["weight"] == 25.0  # Added

    @pytest.mark.asyncio
    async def test_async_delete_dog_data(self, data_manager, mock_store):
        """Test deleting dog data."""
        data_manager._stores["dogs"] = mock_store

        with (
            patch.object(
                data_manager,
                "_get_cache",
                return_value={"test_dog": {}, "other_dog": {}},
            ),
            patch.object(data_manager, "_set_cache") as mock_set_cache,
            patch.object(
                data_manager, "_delete_dog_from_all_modules"
            ) as mock_delete_modules,
        ):
            await data_manager.async_delete_dog_data("test_dog")

            mock_delete_modules.assert_called_once_with("test_dog")
            mock_store.async_save.assert_called_once()

            # Verify dog was removed from cache
            saved_data = mock_set_cache.call_args[0][1]
            assert "test_dog" not in saved_data
            assert "other_dog" in saved_data

    @pytest.mark.asyncio
    async def test_async_get_all_dogs(self, data_manager):
        """Test getting all dogs data."""
        dogs_data = {
            "dog1": {"name": "Dog 1"},
            "dog2": {"name": "Dog 2"},
        }

        with patch.object(data_manager, "_get_cache", return_value=dogs_data):
            result = await data_manager.async_get_all_dogs()

            assert result == dogs_data
            assert result is not dogs_data  # Should be a copy

    @pytest.mark.asyncio
    async def test_async_log_feeding(self, data_manager):
        """Test logging feeding data."""
        meal_data = {
            "meal_type": "breakfast",
            "portion_size": 200.0,
            "food_type": "dry_food",
        }

        with (
            patch.object(data_manager, "_append_to_module_data") as mock_append,
            patch.object(data_manager, "async_update_dog_data") as mock_update,
            patch("homeassistant.util.dt.utcnow") as mock_now,
        ):
            mock_now.return_value = datetime(2025, 1, 15, 10, 0, 0)

            await data_manager.async_log_feeding("test_dog", meal_data)

            # Verify feeding entry was created
            mock_append.assert_called_once()
            call_args = mock_append.call_args[0]
            assert call_args[0] == "feeding"
            assert call_args[1] == "test_dog"

            feeding_entry = call_args[2]
            assert "feeding_id" in feeding_entry
            assert feeding_entry["dog_id"] == "test_dog"
            assert feeding_entry["meal_type"] == "breakfast"

            # Verify dog data was updated
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_log_feeding_error(self, data_manager):
        """Test logging feeding data with error."""
        meal_data = {"meal_type": "breakfast"}

        with patch.object(
            data_manager,
            "_append_to_module_data",
            side_effect=Exception("Storage error"),
        ):
            with pytest.raises(Exception, match="Storage error"):
                await data_manager.async_log_feeding("test_dog", meal_data)

            assert data_manager._metrics["errors_count"] > 0

    @pytest.mark.asyncio
    async def test_async_get_feeding_history(self, data_manager):
        """Test getting feeding history."""
        feeding_data = [
            {"timestamp": "2025-01-15T10:00:00", "meal_type": "breakfast"},
            {"timestamp": "2025-01-14T18:00:00", "meal_type": "dinner"},
        ]

        with patch.object(
            data_manager, "async_get_module_data", return_value=feeding_data
        ) as mock_get:
            result = await data_manager.async_get_feeding_history("test_dog", 7)

            assert result == feeding_data
            mock_get.assert_called_once_with(
                "feeding",
                "test_dog",
                start_date=pytest.approx(
                    datetime.now() - timedelta(days=7), abs=timedelta(seconds=1)
                ),
            )

    @pytest.mark.asyncio
    async def test_async_start_walk(self, data_manager):
        """Test starting a walk."""
        walk_data = {
            "label": "Morning walk",
            "location": "Park",
            "walk_type": "regular",
        }

        with (
            patch.object(data_manager, "_append_to_module_data") as mock_append,
            patch.object(data_manager, "async_update_dog_data") as mock_update,
            patch("homeassistant.util.dt.utcnow") as mock_now,
        ):
            mock_now.return_value = datetime(2025, 1, 15, 9, 0, 0)

            walk_id = await data_manager.async_start_walk("test_dog", walk_data)

            # Verify walk ID format
            assert walk_id.startswith("walk_test_dog_")

            # Verify walk entry was created
            mock_append.assert_called_once()
            call_args = mock_append.call_args[0]
            assert call_args[0] == "walks"
            assert call_args[1] == "test_dog"

            walk_entry = call_args[2]
            assert walk_entry["walk_id"] == walk_id
            assert walk_entry["status"] == "in_progress"
            assert walk_entry["label"] == "Morning walk"

            # Verify dog data was updated
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_end_walk_success(self, data_manager):
        """Test ending a walk successfully."""
        dog_data = {
            "walk": {
                "walk_in_progress": True,
                "current_walk_id": "walk_123",
                "current_walk_start": "2025-01-15T09:00:00",
            }
        }

        walk_data = {
            "distance": 2000.0,
            "duration_minutes": 30,
            "notes": "Good walk",
        }

        with (
            patch.object(data_manager, "async_get_dog_data", return_value=dog_data),
            patch.object(data_manager, "_update_module_entry") as mock_update_entry,
            patch.object(data_manager, "async_update_dog_data") as mock_update_dog,
            patch("homeassistant.util.dt.utcnow") as mock_now,
        ):
            mock_now.return_value = datetime(2025, 1, 15, 9, 30, 0)

            await data_manager.async_end_walk("test_dog", walk_data)

            # Verify walk entry was updated
            mock_update_entry.assert_called_once()
            call_args = mock_update_entry.call_args[0]
            assert call_args[0] == "walks"
            assert call_args[1] == "test_dog"
            assert call_args[2] == "walk_123"

            walk_updates = call_args[3]
            assert walk_updates["status"] == "completed"
            assert walk_updates["distance"] == 2000.0
            assert walk_updates["duration_minutes"] == 30

            # Verify dog data was updated
            mock_update_dog.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_end_walk_no_active_walk(self, data_manager):
        """Test ending walk when no walk is active."""
        dog_data = {"walk": {"walk_in_progress": False}}

        with patch.object(data_manager, "async_get_dog_data", return_value=dog_data):
            # Should not raise exception, just log warning
            await data_manager.async_end_walk("test_dog")

    @pytest.mark.asyncio
    async def test_async_get_current_walk(self, data_manager):
        """Test getting current walk."""
        dog_data = {
            "walk": {
                "walk_in_progress": True,
                "current_walk_id": "walk_123",
            }
        }

        walks_data = [
            {"walk_id": "walk_123", "status": "in_progress"},
            {"walk_id": "walk_122", "status": "completed"},
        ]

        with (
            patch.object(data_manager, "async_get_dog_data", return_value=dog_data),
            patch.object(
                data_manager, "async_get_module_data", return_value=walks_data
            ),
        ):
            result = await data_manager.async_get_current_walk("test_dog")

            assert result["walk_id"] == "walk_123"
            assert result["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_async_get_current_walk_none(self, data_manager):
        """Test getting current walk when none active."""
        dog_data = {"walk": {"walk_in_progress": False}}

        with patch.object(data_manager, "async_get_dog_data", return_value=dog_data):
            result = await data_manager.async_get_current_walk("test_dog")

            assert result is None

    @pytest.mark.asyncio
    async def test_async_log_health(self, data_manager):
        """Test logging health data."""
        health_data = {
            "weight": 25.5,
            "temperature": 38.5,
            "mood": "happy",
            "health_status": "good",
        }

        with (
            patch.object(data_manager, "_append_to_module_data") as mock_append,
            patch.object(data_manager, "async_update_dog_data") as mock_update,
        ):
            await data_manager.async_log_health("test_dog", health_data)

            # Verify health entry was created
            mock_append.assert_called_once()
            call_args = mock_append.call_args[0]
            assert call_args[0] == "health"
            assert call_args[1] == "test_dog"

            health_entry = call_args[2]
            assert "health_id" in health_entry
            assert health_entry["weight"] == 25.5
            assert health_entry["mood"] == "happy"

            # Verify dog data was updated with health info
            mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_log_gps(self, data_manager):
        """Test logging GPS data."""
        gps_data = {
            "latitude": 52.5200,
            "longitude": 13.4050,
            "accuracy": 10.0,
            "source": "device_tracker",
        }

        current_walk = {
            "walk_id": "walk_123",
            "route_points": [{"lat": 52.0, "lon": 13.0}],
        }

        with (
            patch.object(data_manager, "_append_to_module_data") as mock_append,
            patch.object(data_manager, "async_update_dog_data") as mock_update,
            patch.object(
                data_manager, "async_get_current_walk", return_value=current_walk
            ),
            patch.object(data_manager, "_update_module_entry") as mock_update_walk,
        ):
            await data_manager.async_log_gps("test_dog", gps_data)

            # Verify GPS entry was created
            mock_append.assert_called_once()

            # Verify dog GPS data was updated
            mock_update.assert_called_once()

            # Verify walk route was updated
            mock_update_walk.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_log_gps_no_current_walk(self, data_manager):
        """Test logging GPS data when no walk is active."""
        gps_data = {
            "latitude": 52.5200,
            "longitude": 13.4050,
        }

        with (
            patch.object(data_manager, "_append_to_module_data"),
            patch.object(data_manager, "async_update_dog_data"),
            patch.object(data_manager, "async_get_current_walk", return_value=None),
            patch.object(data_manager, "_update_module_entry") as mock_update_walk,
        ):
            await data_manager.async_log_gps("test_dog", gps_data)

            # Walk route should not be updated
            mock_update_walk.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_start_grooming(self, data_manager):
        """Test starting grooming session."""
        grooming_data = {
            "type": "full_grooming",
            "location": "Pet Salon",
            "groomer": "Jane Doe",
        }

        with (
            patch.object(data_manager, "_append_to_module_data") as mock_append,
            patch.object(data_manager, "async_update_dog_data"),
        ):
            grooming_id = await data_manager.async_start_grooming(
                "test_dog", grooming_data
            )

            assert grooming_id.startswith("grooming_test_dog_")

            # Verify grooming entry was created
            mock_append.assert_called_once()
            call_args = mock_append.call_args[0]
            assert call_args[0] == "grooming"

            grooming_entry = call_args[2]
            assert grooming_entry["status"] == "in_progress"
            assert grooming_entry["type"] == "full_grooming"

    @pytest.mark.asyncio
    async def test_async_get_module_data(self, data_manager):
        """Test getting module data."""
        module_data = [
            {"timestamp": "2025-01-15T10:00:00", "data": "entry1"},
            {"timestamp": "2025-01-14T10:00:00", "data": "entry2"},
            {"timestamp": "2025-01-13T10:00:00", "data": "entry3"},
        ]

        with (
            patch.object(data_manager, "_get_cache", return_value=module_data),
            patch.object(data_manager, "_ensure_cache_fresh"),
        ):
            # Test with limit
            result = await data_manager.async_get_module_data(
                "feeding", "test_dog", limit=2
            )
            assert len(result) == 2
            assert result[0]["data"] == "entry1"  # Most recent first

            # Test with date filter
            start_date = datetime(2025, 1, 14, 0, 0, 0)
            result = await data_manager.async_get_module_data(
                "feeding", "test_dog", start_date=start_date
            )
            assert len(result) == 2  # Should exclude entry3

            # Test with end date
            end_date = datetime(2025, 1, 14, 12, 0, 0)
            result = await data_manager.async_get_module_data(
                "feeding", "test_dog", end_date=end_date
            )
            assert len(result) == 2  # Should exclude entry1

    @pytest.mark.asyncio
    async def test_async_get_module_data_cache_miss(self, data_manager, mock_store):
        """Test getting module data with cache miss."""
        store_data = {"test_dog": [{"data": "from_store"}]}
        mock_store.async_load.return_value = store_data
        data_manager._stores["feeding"] = mock_store

        with (
            patch.object(
                data_manager, "_get_cache", side_effect=[[], store_data["test_dog"]]
            ),
            patch.object(data_manager, "_set_cache") as mock_set_cache,
            patch.object(data_manager, "_ensure_cache_fresh"),
        ):
            result = await data_manager.async_get_module_data("feeding", "test_dog")

            mock_store.async_load.assert_called_once()
            mock_set_cache.assert_called_once()
            assert data_manager._metrics["cache_misses"] > 0
            assert result[0]["data"] == "from_store"

    @pytest.mark.asyncio
    async def test_async_reset_dog_daily_stats(self, data_manager):
        """Test resetting daily statistics."""
        with patch.object(data_manager, "async_update_dog_data") as mock_update:
            await data_manager.async_reset_dog_daily_stats("test_dog")

            mock_update.assert_called_once()
            call_args = mock_update.call_args[0]
            assert call_args[0] == "test_dog"

            reset_data = call_args[1]
            assert "feeding" in reset_data
            assert "walk" in reset_data
            assert "health" in reset_data
            assert "last_reset" in reset_data

            # Verify feeding stats reset
            assert reset_data["feeding"]["daily_food_consumed"] == 0
            assert reset_data["feeding"]["meals_today"] == 0

    @pytest.mark.asyncio
    async def test_async_reset_all_dogs_stats(self, data_manager):
        """Test resetting stats for all dogs."""
        dogs_data = {
            "dog1": {"name": "Dog 1"},
            "dog2": {"name": "Dog 2"},
        }

        with (
            patch.object(data_manager, "async_get_all_dogs", return_value=dogs_data),
            patch.object(data_manager, "_reset_single_dog_stats") as mock_reset,
        ):
            await data_manager.async_reset_dog_daily_stats("all")

            assert mock_reset.call_count == 2
            mock_reset.assert_any_call("dog1")
            mock_reset.assert_any_call("dog2")

    @pytest.mark.asyncio
    async def test_async_cleanup_old_data(self, data_manager):
        """Test cleaning up old data."""
        with patch.object(
            data_manager, "_cleanup_module_data", return_value=5
        ) as mock_cleanup:
            result = await data_manager.async_cleanup_old_data(30)

            # Should cleanup all modules
            expected_modules = ["feeding", "walks", "health", "gps", "grooming"]
            assert mock_cleanup.call_count == len(expected_modules)

            # Verify cleanup stats
            assert isinstance(result, dict)
            for module in expected_modules:
                assert module in result
                assert result[module] == 5

    @pytest.mark.asyncio
    async def test_cleanup_module_data(self, data_manager, mock_store):
        """Test cleaning up data from specific module."""
        old_data = {
            "test_dog": [
                {"timestamp": "2025-01-15T10:00:00", "data": "recent"},
                {"timestamp": "2024-12-01T10:00:00", "data": "old"},
                {"timestamp": "invalid_timestamp", "data": "invalid"},
            ]
        }

        mock_store.async_load.return_value = old_data
        data_manager._stores["feeding"] = mock_store

        cutoff_date = datetime(2025, 1, 1, 0, 0, 0)

        with patch.object(data_manager, "_set_cache"):
            deleted_count = await data_manager._cleanup_module_data(
                "feeding", cutoff_date
            )

            assert deleted_count == 1  # Only the old entry should be deleted

            # Verify data was saved
            mock_store.async_save.assert_called_once()
            saved_data = mock_store.async_save.call_args[0][0]

            # Should keep recent and invalid timestamp entries
            assert len(saved_data["test_dog"]) == 2
            assert any(entry["data"] == "recent" for entry in saved_data["test_dog"])
            assert any(entry["data"] == "invalid" for entry in saved_data["test_dog"])

    @pytest.mark.asyncio
    async def test_append_to_module_data(self, data_manager, mock_store):
        """Test appending entry to module data."""
        existing_data = {"test_dog": [{"old": "entry"}]}
        mock_store.async_load.return_value = existing_data
        data_manager._stores["feeding"] = mock_store

        new_entry = {"new": "entry"}

        with patch.object(data_manager, "_set_cache") as mock_set_cache:
            await data_manager._append_to_module_data("feeding", "test_dog", new_entry)

            # Verify data was updated and saved
            mock_store.async_save.assert_called_once()
            saved_data = mock_store.async_save.call_args[0][0]

            assert len(saved_data["test_dog"]) == 2
            assert saved_data["test_dog"][1] == new_entry

            # Verify cache was updated
            mock_set_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_append_to_module_data_new_dog(self, data_manager, mock_store):
        """Test appending entry for new dog."""
        mock_store.async_load.return_value = {}
        data_manager._stores["feeding"] = mock_store

        new_entry = {"first": "entry"}

        await data_manager._append_to_module_data("feeding", "new_dog", new_entry)

        # Verify new dog entry was created
        saved_data = mock_store.async_save.call_args[0][0]
        assert "new_dog" in saved_data
        assert saved_data["new_dog"] == [new_entry]

    @pytest.mark.asyncio
    async def test_update_module_entry(self, data_manager, mock_store):
        """Test updating specific module entry."""
        existing_data = {
            "test_dog": [
                {"feeding_id": "feed_123", "status": "completed"},
                {"feeding_id": "feed_124", "status": "in_progress"},
            ]
        }
        mock_store.async_load.return_value = existing_data
        data_manager._stores["feeding"] = mock_store

        updates = {"status": "completed", "notes": "Finished"}

        await data_manager._update_module_entry(
            "feeding", "test_dog", "feed_124", updates
        )

        # Verify correct entry was updated
        saved_data = mock_store.async_save.call_args[0][0]
        updated_entry = saved_data["test_dog"][1]
        assert updated_entry["feeding_id"] == "feed_124"
        assert updated_entry["status"] == "completed"
        assert updated_entry["notes"] == "Finished"

    @pytest.mark.asyncio
    async def test_cache_management(self, data_manager):
        """Test cache management functionality."""
        # Test setting and getting cache
        await data_manager._set_cache("test_key", {"test": "data"})
        result = await data_manager._get_cache("test_key")
        assert result == {"test": "data"}

        # Test default value
        result = await data_manager._get_cache("nonexistent_key", "default")
        assert result == "default"

        # Test cache freshness
        data_manager._cache_ttl = timedelta(seconds=1)
        await asyncio.sleep(1.1)  # Wait for cache to expire

        await data_manager._ensure_cache_fresh("test_key")
        # Cache should be cleared after expiration
        result = await data_manager._get_cache("test_key", "not_found")
        assert result == "not_found"

    @pytest.mark.asyncio
    async def test_delete_dog_from_all_modules(self, data_manager):
        """Test deleting dog from all module stores."""
        modules = ["feeding", "walks", "health", "gps", "grooming"]

        # Mock stores for all modules
        for module in modules:
            mock_store = Mock(spec=Store)
            mock_store.async_load.return_value = {"test_dog": [], "other_dog": []}
            mock_store.async_save = AsyncMock()
            data_manager._stores[module] = mock_store

        await data_manager._delete_dog_from_all_modules("test_dog")

        # Verify dog was removed from all modules
        for module in modules:
            store = data_manager._stores[module]
            store.async_save.assert_called_once()
            saved_data = store.async_save.call_args[0][0]
            assert "test_dog" not in saved_data
            assert "other_dog" in saved_data

    @pytest.mark.asyncio
    async def test_periodic_cleanup_task(self, data_manager):
        """Test periodic cleanup task."""
        cleanup_call_count = 0

        async def mock_cleanup():
            nonlocal cleanup_call_count
            cleanup_call_count += 1
            if cleanup_call_count >= 2:
                # Cancel the task after 2 calls
                data_manager._cleanup_task.cancel()

        with (
            patch.object(
                data_manager, "async_cleanup_old_data", side_effect=mock_cleanup
            ),
            patch("asyncio.sleep", side_effect=[None, None, asyncio.CancelledError()]),
        ):
            try:
                await data_manager._periodic_cleanup()
            except asyncio.CancelledError:
                pass

            assert cleanup_call_count >= 1

    @pytest.mark.asyncio
    async def test_create_backup(self, data_manager):
        """Test creating data backup."""
        dogs_data = {"test_dog": {"name": "Test Dog"}}

        with (
            patch.object(data_manager, "async_get_all_dogs", return_value=dogs_data),
            patch.object(data_manager, "async_get_module_data", return_value=[]),
            patch.object(data_manager, "_export_json") as mock_export,
            patch("pathlib.Path.mkdir") as mock_mkdir,
        ):
            await data_manager._create_backup()

            mock_mkdir.assert_called_once()
            mock_export.assert_called_once()

            # Verify backup data structure
            backup_data = mock_export.call_args[0][1]
            assert "backup_info" in backup_data
            assert "dogs" in backup_data
            assert backup_data["dogs"] == dogs_data

    @pytest.mark.asyncio
    async def test_export_json(self, data_manager, tmp_path):
        """Test JSON export functionality."""
        test_data = {"test": "data", "number": 123}
        test_path = tmp_path / "test.json"

        mock_file = mock_open()

        with patch("aiofiles.open", mock_file):
            await data_manager._export_json(test_path, test_data)

            # Verify file was written with correct JSON data
            mock_file.assert_called_once_with(test_path, "w", encoding="utf-8")
            written_data = "".join(
                call.args[0] for call in mock_file().write.call_args_list
            )
            parsed_data = json.loads(written_data)
            assert parsed_data == test_data

    def test_get_metrics(self, data_manager):
        """Test getting performance metrics."""
        # Set some test metrics
        data_manager._metrics["operations_count"] = 100
        data_manager._metrics["cache_hits"] = 80
        data_manager._metrics["cache_misses"] = 20
        data_manager._cache = {"key1": "value1", "key2": "value2"}

        metrics = data_manager.get_metrics()

        assert metrics["operations_count"] == 100
        assert metrics["cache_hits"] == 80
        assert metrics["cache_misses"] == 20
        assert metrics["cache_size"] == 2
        assert metrics["cache_hit_rate"] == 80.0  # 80 / (80 + 20) * 100

    def test_get_metrics_no_cache_activity(self, data_manager):
        """Test metrics when no cache activity."""
        data_manager._metrics["cache_hits"] = 0
        data_manager._metrics["cache_misses"] = 0

        metrics = data_manager.get_metrics()

        assert metrics["cache_hit_rate"] == 0.0  # Should handle division by zero

    @pytest.mark.asyncio
    async def test_error_handling_and_metrics(self, data_manager):
        """Test error handling increments error metrics."""
        initial_errors = data_manager._metrics["errors_count"]

        with patch.object(
            data_manager, "_append_to_module_data", side_effect=Exception("Test error")
        ):
            with pytest.raises(Exception):
                await data_manager.async_log_feeding(
                    "test_dog", {"meal_type": "breakfast"}
                )

        assert data_manager._metrics["errors_count"] == initial_errors + 1

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, data_manager):
        """Test concurrent data operations."""
        # Test multiple concurrent operations
        tasks = []

        for i in range(10):
            task = data_manager.async_log_feeding(
                f"dog_{i}", {"meal_type": "breakfast"}
            )
            tasks.append(task)

        with (
            patch.object(data_manager, "_append_to_module_data"),
            patch.object(data_manager, "async_update_dog_data"),
        ):
            # All operations should complete without errors
            await asyncio.gather(*tasks)

        # Verify operations were counted
        assert data_manager._metrics["operations_count"] >= 10

    @pytest.mark.asyncio
    async def test_memory_efficient_operations(self, data_manager):
        """Test memory-efficient handling of large datasets."""
        # Test with large data set
        large_data = [{"entry": i, "data": "x" * 1000} for i in range(1000)]

        with patch.object(data_manager, "_get_cache", return_value=large_data):
            # Test that operations handle large data efficiently
            result = await data_manager.async_get_module_data(
                "feeding", "test_dog", limit=10
            )

            # Should only return requested amount
            assert len(result) == 10

            # Should be sorted by timestamp (most recent first)
            assert result == large_data[:10]
