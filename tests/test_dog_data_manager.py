"""Tests for PawControl dog data manager.

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
from custom_components.pawcontrol.const import CONF_DOG_ID, CONF_DOG_NAME
from custom_components.pawcontrol.dog_data_manager import DogDataManager
from custom_components.pawcontrol.types import DogConfigData
from homeassistant.util import dt as dt_util


class TestDogDataManagerInitialization:
    """Test dog data manager initialization and setup."""

    @pytest.fixture
    def manager(self):
        """Create dog data manager instance."""
        return DogDataManager()

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": False,
                    "gps": True,
                },
                "breed": "Golden Retriever",
                "weight": 30.0,
            },
            {
                CONF_DOG_ID: "dog2", 
                CONF_DOG_NAME: "Luna",
                "modules": {
                    "feeding": True,
                    "walk": False,
                    "health": True,
                    "gps": False,
                },
                "breed": "Border Collie",
                "weight": 25.0,
            },
        ]

    def test_initialization(self, manager):
        """Test manager initialization."""
        assert isinstance(manager._dogs_data, dict)
        assert isinstance(manager._dogs_config, list)
        assert isinstance(manager._data_lock, asyncio.Lock)
        assert isinstance(manager._last_updated, dict)
        assert isinstance(manager._validation_cache, dict)
        assert isinstance(manager._cache_expiry, dict)
        assert len(manager._dogs_data) == 0
        assert len(manager._dogs_config) == 0

    async def test_async_initialize_single_dog(self, manager, sample_dogs_config):
        """Test initialization with single dog."""
        single_dog = [sample_dogs_config[0]]
        
        await manager.async_initialize(single_dog)
        
        assert len(manager._dogs_config) == 1
        assert len(manager._dogs_data) == 1
        assert "dog1" in manager._dogs_data
        
        dog_data = manager._dogs_data["dog1"]
        assert dog_data["dog_info"] == single_dog[0]
        assert "feeding" in dog_data
        assert "walk" in dog_data
        assert "health" in dog_data
        assert "gps" in dog_data
        assert "created_at" in dog_data
        assert "last_updated" in dog_data

    async def test_async_initialize_multiple_dogs(self, manager, sample_dogs_config):
        """Test initialization with multiple dogs."""
        await manager.async_initialize(sample_dogs_config)
        
        assert len(manager._dogs_config) == 2
        assert len(manager._dogs_data) == 2
        assert "dog1" in manager._dogs_data
        assert "dog2" in manager._dogs_data
        
        # Check both dogs have complete data structure
        for dog_id in ["dog1", "dog2"]:
            dog_data = manager._dogs_data[dog_id]
            required_keys = ["dog_info", "feeding", "walk", "health", "gps", "created_at", "last_updated"]
            for key in required_keys:
                assert key in dog_data

    async def test_async_initialize_empty_config(self, manager):
        """Test initialization with empty configuration."""
        await manager.async_initialize([])
        
        assert len(manager._dogs_config) == 0
        assert len(manager._dogs_data) == 0

    async def test_async_initialize_timestamp_format(self, manager, sample_dogs_config):
        """Test initialization creates valid timestamps."""
        await manager.async_initialize(sample_dogs_config)
        
        for dog_id in ["dog1", "dog2"]:
            dog_data = manager._dogs_data[dog_id]
            
            # Check timestamp format
            created_at = dog_data["created_at"]
            last_updated = dog_data["last_updated"]
            
            # Should be ISO format strings
            assert isinstance(created_at, str)
            assert isinstance(last_updated, str)
            
            # Should be parseable
            dt_util.parse_datetime(created_at)
            dt_util.parse_datetime(last_updated)
            
            # Should have corresponding datetime in _last_updated
            assert dog_id in manager._last_updated
            assert isinstance(manager._last_updated[dog_id], datetime)


class TestDogDataManagerDataAccess:
    """Test dog data manager data access methods."""

    @pytest.fixture
    async def initialized_manager(self, sample_dogs_config):
        """Create initialized manager."""
        manager = DogDataManager()
        await manager.async_initialize(sample_dogs_config)
        return manager

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "modules": {"feeding": True, "walk": True, "health": False, "gps": True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Luna", 
                "modules": {"feeding": True, "walk": False, "health": True, "gps": False},
            },
        ]

    async def test_async_get_dog_data_existing(self, initialized_manager):
        """Test getting data for existing dog."""
        dog_data = await initialized_manager.async_get_dog_data("dog1")
        
        assert dog_data is not None
        assert dog_data["dog_info"][CONF_DOG_ID] == "dog1"
        assert dog_data["dog_info"][CONF_DOG_NAME] == "Buddy"
        assert "feeding" in dog_data
        assert "walk" in dog_data
        assert "health" in dog_data
        assert "gps" in dog_data

    async def test_async_get_dog_data_nonexistent(self, initialized_manager):
        """Test getting data for non-existent dog."""
        dog_data = await initialized_manager.async_get_dog_data("nonexistent")
        assert dog_data is None

    async def test_async_get_dog_data_copy_isolation(self, initialized_manager):
        """Test that returned data is isolated copy."""
        dog_data1 = await initialized_manager.async_get_dog_data("dog1")
        dog_data2 = await initialized_manager.async_get_dog_data("dog1")
        
        # Should be different objects
        assert dog_data1 is not dog_data2
        
        # Modifying one should not affect the other
        dog_data1["feeding"]["test"] = "modified"
        assert "test" not in dog_data2["feeding"]

    async def test_async_update_dog_data_existing_dog(self, initialized_manager):
        """Test updating data for existing dog."""
        update_data = {
            "last_feeding": "2024-01-01T12:00:00Z",
            "meals_today": 2,
            "food_type": "dry"
        }
        
        result = await initialized_manager.async_update_dog_data("dog1", "feeding", update_data)
        
        assert result is True
        
        # Verify data was updated
        dog_data = await initialized_manager.async_get_dog_data("dog1")
        feeding_data = dog_data["feeding"]
        assert feeding_data["last_feeding"] == "2024-01-01T12:00:00Z"
        assert feeding_data["meals_today"] == 2
        assert feeding_data["food_type"] == "dry"

    async def test_async_update_dog_data_nonexistent_dog(self, initialized_manager):
        """Test updating data for non-existent dog."""
        update_data = {"test": "value"}
        
        result = await initialized_manager.async_update_dog_data("nonexistent", "feeding", update_data)
        
        assert result is False

    async def test_async_update_dog_data_timestamp_update(self, initialized_manager):
        """Test that updating data updates timestamps."""
        # Get initial timestamp
        initial_data = await initialized_manager.async_get_dog_data("dog1")
        initial_timestamp = initial_data["last_updated"]
        
        # Wait a bit to ensure timestamp difference
        await asyncio.sleep(0.01)
        
        # Update data
        update_data = {"test": "value"}
        await initialized_manager.async_update_dog_data("dog1", "feeding", update_data)
        
        # Check timestamp was updated
        updated_data = await initialized_manager.async_get_dog_data("dog1")
        updated_timestamp = updated_data["last_updated"]
        
        assert updated_timestamp != initial_timestamp

    async def test_async_update_dog_data_isolation(self, initialized_manager):
        """Test that update data is copied, not referenced."""
        update_data = {"shared_data": {"nested": "value"}}
        
        await initialized_manager.async_update_dog_data("dog1", "feeding", update_data)
        
        # Modify original data
        update_data["shared_data"]["nested"] = "modified"
        
        # Check stored data was not affected
        dog_data = await initialized_manager.async_get_dog_data("dog1")
        assert dog_data["feeding"]["shared_data"]["nested"] == "value"

    async def test_async_get_all_dogs_data(self, initialized_manager):
        """Test getting all dogs data."""
        all_data = await initialized_manager.async_get_all_dogs_data()
        
        assert len(all_data) == 2
        assert "dog1" in all_data
        assert "dog2" in all_data
        
        # Check data structure
        for dog_id, dog_data in all_data.items():
            assert "dog_info" in dog_data
            assert dog_data["dog_info"][CONF_DOG_ID] == dog_id

    async def test_async_get_all_dogs_data_copy_isolation(self, initialized_manager):
        """Test that all dogs data returns isolated copies."""
        all_data1 = await initialized_manager.async_get_all_dogs_data()
        all_data2 = await initialized_manager.async_get_all_dogs_data()
        
        # Should be different objects
        assert all_data1 is not all_data2
        
        # Modifying one should not affect the other
        all_data1["dog1"]["feeding"]["test"] = "modified"
        assert "test" not in all_data2["dog1"]["feeding"]


class TestDogDataManagerConfiguration:
    """Test dog data manager configuration access methods."""

    @pytest.fixture
    async def initialized_manager(self, sample_dogs_config):
        """Create initialized manager."""
        manager = DogDataManager()
        await manager.async_initialize(sample_dogs_config)
        return manager

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "modules": {"feeding": True, "walk": True, "health": False, "gps": True},
                "breed": "Golden Retriever",
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Luna",
                "modules": {"feeding": True, "walk": False, "health": True, "gps": False},
                "breed": "Border Collie",
            },
        ]

    def test_get_dog_config_existing(self, initialized_manager):
        """Test getting configuration for existing dog."""
        config = initialized_manager.get_dog_config("dog1")
        
        assert config is not None
        assert config[CONF_DOG_ID] == "dog1"
        assert config[CONF_DOG_NAME] == "Buddy"
        assert config["breed"] == "Golden Retriever"

    def test_get_dog_config_nonexistent(self, initialized_manager):
        """Test getting configuration for non-existent dog."""
        config = initialized_manager.get_dog_config("nonexistent")
        assert config is None

    def test_get_all_dog_configs(self, initialized_manager):
        """Test getting all dog configurations."""
        configs = initialized_manager.get_all_dog_configs()
        
        assert len(configs) == 2
        dog_ids = [config[CONF_DOG_ID] for config in configs]
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids

    def test_get_all_dog_configs_copy_isolation(self, initialized_manager):
        """Test that configuration list is isolated copy."""
        configs1 = initialized_manager.get_all_dog_configs()
        configs2 = initialized_manager.get_all_dog_configs()
        
        # Should be different lists
        assert configs1 is not configs2
        
        # Modifying one should not affect the other
        configs1[0]["test_field"] = "modified"
        assert "test_field" not in configs2[0]

    def test_get_dog_ids(self, initialized_manager):
        """Test getting list of dog IDs."""
        dog_ids = initialized_manager.get_dog_ids()
        
        assert len(dog_ids) == 2
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids

    def test_get_enabled_modules(self, initialized_manager):
        """Test getting enabled modules for dogs."""
        # Dog1 has feeding, walk, gps enabled (health disabled)
        modules1 = initialized_manager.get_enabled_modules("dog1")
        assert "feeding" in modules1
        assert "walk" in modules1
        assert "gps" in modules1
        assert "health" not in modules1
        
        # Dog2 has feeding, health enabled (walk, gps disabled)
        modules2 = initialized_manager.get_enabled_modules("dog2")
        assert "feeding" in modules2
        assert "health" in modules2
        assert "walk" not in modules2
        assert "gps" not in modules2

    def test_get_enabled_modules_nonexistent(self, initialized_manager):
        """Test getting enabled modules for non-existent dog."""
        modules = initialized_manager.get_enabled_modules("nonexistent")
        assert modules == set()

    def test_get_enabled_modules_no_modules_config(self):
        """Test getting enabled modules when no modules config exists."""
        manager = DogDataManager()
        config_without_modules = [{CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test"}]
        manager._dogs_config = config_without_modules
        
        modules = manager.get_enabled_modules("dog1")
        assert modules == set()

    def test_is_module_enabled(self, initialized_manager):
        """Test checking if specific module is enabled."""
        # Dog1 tests
        assert initialized_manager.is_module_enabled("dog1", "feeding") is True
        assert initialized_manager.is_module_enabled("dog1", "walk") is True
        assert initialized_manager.is_module_enabled("dog1", "health") is False
        assert initialized_manager.is_module_enabled("dog1", "gps") is True
        
        # Dog2 tests
        assert initialized_manager.is_module_enabled("dog2", "feeding") is True
        assert initialized_manager.is_module_enabled("dog2", "walk") is False
        assert initialized_manager.is_module_enabled("dog2", "health") is True
        assert initialized_manager.is_module_enabled("dog2", "gps") is False

    def test_is_module_enabled_nonexistent_dog(self, initialized_manager):
        """Test checking module for non-existent dog."""
        assert initialized_manager.is_module_enabled("nonexistent", "feeding") is False

    def test_is_module_enabled_nonexistent_module(self, initialized_manager):
        """Test checking non-existent module."""
        assert initialized_manager.is_module_enabled("dog1", "nonexistent") is False


class TestDogDataManagerValidation:
    """Test dog data manager validation functionality."""

    @pytest.fixture
    async def initialized_manager(self, sample_dogs_config):
        """Create initialized manager."""
        manager = DogDataManager()
        await manager.async_initialize(sample_dogs_config)
        return manager

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "modules": {"feeding": True, "walk": True, "health": True, "gps": True},
            }
        ]

    @pytest.fixture
    def valid_dog_data(self):
        """Create valid dog data for testing."""
        return {
            "dog_info": {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "breed": "Golden Retriever",
            },
            "feeding": {
                "last_feeding": "2024-01-01T12:00:00Z",
                "meals_today": 2,
            },
            "walk": {
                "walk_in_progress": False,
                "walks_today": 1,
            },
            "health": {
                "current_weight": 25.5,
            },
            "gps": {
                "latitude": 52.5200,
                "longitude": 13.4050,
            },
            "created_at": "2024-01-01T10:00:00Z",
            "last_updated": "2024-01-01T12:00:00Z",
        }

    async def test_validate_dog_data_valid(self, initialized_manager, valid_dog_data):
        """Test validation of valid dog data."""
        result = await initialized_manager.async_validate_dog_data("dog1", valid_dog_data)
        
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert isinstance(result["warnings"], list)
        assert "validated_at" in result

    async def test_validate_dog_data_missing_required_fields(self, initialized_manager):
        """Test validation with missing required fields."""
        invalid_data = {"feeding": {"meals_today": 2}}
        
        result = await initialized_manager.async_validate_dog_data("dog1", invalid_data)
        
        assert result["valid"] is False
        assert any("Missing required field: dog_info" in error for error in result["errors"])

    async def test_validate_dog_data_invalid_dog_info(self, initialized_manager):
        """Test validation with invalid dog_info structure."""
        invalid_data = {
            "dog_info": "not a dict",
            "feeding": {},
        }
        
        result = await initialized_manager.async_validate_dog_data("dog1", invalid_data)
        
        assert result["valid"] is False
        assert any("dog_info must be a dictionary" in error for error in result["errors"])

    async def test_validate_dog_data_missing_dog_info_fields(self, initialized_manager):
        """Test validation with missing dog_info fields."""
        invalid_data = {
            "dog_info": {
                CONF_DOG_ID: "dog1",
                # Missing CONF_DOG_NAME
            },
            "feeding": {},
        }
        
        result = await initialized_manager.async_validate_dog_data("dog1", invalid_data)
        
        assert result["valid"] is False
        assert any(f"Missing required dog_info field: {CONF_DOG_NAME}" in error for error in result["errors"])

    async def test_validate_dog_data_empty_dog_info_fields(self, initialized_manager):
        """Test validation with empty dog_info fields."""
        invalid_data = {
            "dog_info": {
                CONF_DOG_ID: "",
                CONF_DOG_NAME: "Buddy",
            },
            "feeding": {},
        }
        
        result = await initialized_manager.async_validate_dog_data("dog1", invalid_data)
        
        assert result["valid"] is False
        assert any(f"Empty required dog_info field: {CONF_DOG_ID}" in error for error in result["errors"])

    async def test_validate_dog_data_nonexistent_dog(self, initialized_manager, valid_dog_data):
        """Test validation for non-existent dog."""
        result = await initialized_manager.async_validate_dog_data("nonexistent", valid_dog_data)
        
        assert result["valid"] is False
        assert any("Dog configuration not found" in error for error in result["errors"])

    async def test_validate_dog_data_unexpected_fields(self, initialized_manager, valid_dog_data):
        """Test validation with unexpected fields."""
        valid_dog_data["unexpected_field"] = "unexpected_value"
        
        result = await initialized_manager.async_validate_dog_data("dog1", valid_dog_data)
        
        # Should still be valid but with warnings
        assert result["valid"] is True
        assert any("Unexpected data field: unexpected_field" in warning for warning in result["warnings"])

    async def test_validate_dog_data_invalid_timestamps(self, initialized_manager, valid_dog_data):
        """Test validation with invalid timestamps."""
        valid_dog_data["created_at"] = "invalid_timestamp"
        
        result = await initialized_manager.async_validate_dog_data("dog1", valid_dog_data)
        
        assert result["valid"] is False
        assert any("Invalid timestamp format in created_at" in error for error in result["errors"])

    async def test_validate_dog_data_caching(self, initialized_manager, valid_dog_data):
        """Test validation result caching."""
        # First validation
        result1 = await initialized_manager.async_validate_dog_data("dog1", valid_dog_data)
        
        # Second validation with same data should use cache
        result2 = await initialized_manager.async_validate_dog_data("dog1", valid_dog_data)
        
        assert result1["validated_at"] == result2["validated_at"]

    async def test_validate_module_data_feeding(self, initialized_manager):
        """Test validation of feeding module data."""
        # Valid feeding data
        feeding_data = {
            "last_feeding": "2024-01-01T12:00:00Z",
            "meals_today": 3,
        }
        errors = await initialized_manager._validate_module_data("feeding", feeding_data)
        assert len(errors) == 0
        
        # Invalid feeding data
        invalid_feeding = {
            "last_feeding": "invalid_timestamp",
            "meals_today": 15,  # Too many meals
        }
        errors = await initialized_manager._validate_module_data("feeding", invalid_feeding)
        assert len(errors) >= 2
        assert any("Invalid last_feeding timestamp" in error for error in errors)
        assert any("meals_today must be between 0 and 10" in error for error in errors)

    async def test_validate_module_data_walk(self, initialized_manager):
        """Test validation of walk module data."""
        # Valid walk data
        walk_data = {
            "walk_in_progress": True,
            "walks_today": 3,
        }
        errors = await initialized_manager._validate_module_data("walk", walk_data)
        assert len(errors) == 0
        
        # Invalid walk data
        invalid_walk = {
            "walk_in_progress": "not_boolean",
            "walks_today": 25,  # Too many walks
        }
        errors = await initialized_manager._validate_module_data("walk", invalid_walk)
        assert len(errors) >= 2
        assert any("walk_in_progress must be boolean" in error for error in errors)
        assert any("walks_today must be between 0 and 20" in error for error in errors)

    async def test_validate_module_data_health(self, initialized_manager):
        """Test validation of health module data."""
        # Valid health data
        health_data = {"current_weight": 25.5}
        errors = await initialized_manager._validate_module_data("health", health_data)
        assert len(errors) == 0
        
        # Invalid health data
        invalid_health = {"current_weight": 200}  # Too heavy
        errors = await initialized_manager._validate_module_data("health", invalid_health)
        assert len(errors) >= 1
        assert any("current_weight must be between 0 and 150 kg" in error for error in errors)

    async def test_validate_module_data_gps(self, initialized_manager):
        """Test validation of GPS module data."""
        # Valid GPS data
        gps_data = {
            "latitude": 52.5200,
            "longitude": 13.4050,
        }
        errors = await initialized_manager._validate_module_data("gps", gps_data)
        assert len(errors) == 0
        
        # Invalid GPS data
        invalid_gps = {
            "latitude": 95.0,  # Invalid latitude
            "longitude": 200.0,  # Invalid longitude
        }
        errors = await initialized_manager._validate_module_data("gps", invalid_gps)
        assert len(errors) >= 2
        assert any("latitude must be between -90 and 90" in error for error in errors)
        assert any("longitude must be between -180 and 180" in error for error in errors)

    async def test_validate_module_data_non_dict(self, initialized_manager):
        """Test validation of non-dict module data."""
        errors = await initialized_manager._validate_module_data("feeding", "not_a_dict")
        assert len(errors) == 1
        assert "feeding data must be a dictionary" in errors[0]

    def test_is_valid_timestamp(self, initialized_manager):
        """Test timestamp validation."""
        # Valid timestamps
        assert initialized_manager._is_valid_timestamp(datetime.now()) is True
        assert initialized_manager._is_valid_timestamp("2024-01-01T12:00:00Z") is True
        assert initialized_manager._is_valid_timestamp("2024-01-01T12:00:00+02:00") is True
        
        # Invalid timestamps
        assert initialized_manager._is_valid_timestamp("invalid") is False
        assert initialized_manager._is_valid_timestamp(12345) is False
        assert initialized_manager._is_valid_timestamp(None) is False

    async def test_clean_validation_cache(self, initialized_manager):
        """Test validation cache cleanup."""
        # Add expired cache entries
        now = dt_util.now()
        expired_time = now - timedelta(minutes=10)
        
        initialized_manager._validation_cache["expired_key"] = {"test": "data"}
        initialized_manager._cache_expiry["expired_key"] = expired_time
        
        initialized_manager._validation_cache["valid_key"] = {"test": "data"}
        initialized_manager._cache_expiry["valid_key"] = now + timedelta(minutes=10)
        
        await initialized_manager._clean_validation_cache()
        
        # Expired entry should be removed
        assert "expired_key" not in initialized_manager._validation_cache
        assert "expired_key" not in initialized_manager._cache_expiry
        
        # Valid entry should remain
        assert "valid_key" in initialized_manager._validation_cache
        assert "valid_key" in initialized_manager._cache_expiry


class TestDogDataManagerStatisticsAndCleanup:
    """Test dog data manager statistics and cleanup functionality."""

    @pytest.fixture
    async def initialized_manager(self, sample_dogs_config):
        """Create initialized manager."""
        manager = DogDataManager()
        await manager.async_initialize(sample_dogs_config)
        return manager

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Buddy",
                "modules": {"feeding": True, "walk": True, "health": True, "gps": True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Luna",
                "modules": {"feeding": True, "walk": False, "health": True, "gps": False},
            },
        ]

    async def test_async_get_data_statistics_basic(self, initialized_manager):
        """Test getting basic data statistics."""
        stats = await initialized_manager.async_get_data_statistics()
        
        assert stats["total_dogs"] == 2
        assert "total_data_points" in stats
        assert "module_data_counts" in stats
        assert "recent_updates" in stats
        assert "validation_cache_size" in stats
        assert "last_updated_times" in stats
        
        # Check module counts structure
        module_counts = stats["module_data_counts"]
        assert "feeding" in module_counts
        assert "walk" in module_counts
        assert "health" in module_counts
        assert "gps" in module_counts

    async def test_async_get_data_statistics_with_updates(self, initialized_manager):
        """Test statistics after data updates."""
        # Add some data
        feeding_data = {"meals_today": 2, "last_feeding": "2024-01-01T12:00:00Z"}
        walk_data = {"walks_today": 1, "walk_in_progress": False}
        
        await initialized_manager.async_update_dog_data("dog1", "feeding", feeding_data)
        await initialized_manager.async_update_dog_data("dog1", "walk", walk_data)
        
        stats = await initialized_manager.async_get_data_statistics()
        
        assert stats["total_dogs"] == 2
        assert stats["recent_updates"] >= 1  # Should have recent updates
        assert stats["module_data_counts"]["feeding"] >= 2  # Should count the data points
        assert stats["module_data_counts"]["walk"] >= 2

    async def test_async_get_data_statistics_recent_updates(self, initialized_manager):
        """Test recent updates counting in statistics."""
        # Update data recently (within 5 minutes)
        await initialized_manager.async_update_dog_data("dog1", "feeding", {"test": "data"})
        
        stats = await initialized_manager.async_get_data_statistics()
        
        # Should show recent update
        assert stats["recent_updates"] >= 1

    async def test_async_get_data_statistics_last_updated_times(self, initialized_manager):
        """Test last updated times in statistics."""
        stats = await initialized_manager.async_get_data_statistics()
        
        # Should have last updated times (limited to first 5)
        last_updated = stats["last_updated_times"]
        assert len(last_updated) <= 5
        
        # Each should be valid timestamp
        for dog_id, timestamp in last_updated.items():
            assert dog_id in ["dog1", "dog2"]
            dt_util.parse_datetime(timestamp)  # Should not raise

    async def test_async_cleanup(self, initialized_manager):
        """Test cleanup functionality."""
        # Verify data exists before cleanup
        assert len(initialized_manager._dogs_data) == 2
        assert len(initialized_manager._dogs_config) == 2
        assert len(initialized_manager._last_updated) == 2
        
        # Add some cache data
        initialized_manager._validation_cache["test"] = {"data": "value"}
        initialized_manager._cache_expiry["test"] = dt_util.now()
        
        # Perform cleanup
        await initialized_manager.async_cleanup()
        
        # Verify all data is cleared
        assert len(initialized_manager._dogs_data) == 0
        assert len(initialized_manager._dogs_config) == 0
        assert len(initialized_manager._last_updated) == 0
        assert len(initialized_manager._validation_cache) == 0
        assert len(initialized_manager._cache_expiry) == 0

    async def test_async_cleanup_multiple_calls(self, initialized_manager):
        """Test multiple cleanup calls."""
        # First cleanup
        await initialized_manager.async_cleanup()
        
        # Second cleanup should not raise errors
        await initialized_manager.async_cleanup()
        
        # Everything should still be empty
        assert len(initialized_manager._dogs_data) == 0
        assert len(initialized_manager._dogs_config) == 0


class TestDogDataManagerConcurrency:
    """Test dog data manager concurrency and thread safety."""

    @pytest.fixture
    async def initialized_manager(self, sample_dogs_config):
        """Create initialized manager."""
        manager = DogDataManager()
        await manager.async_initialize(sample_dogs_config)
        return manager

    @pytest.fixture
    def sample_dogs_config(self):
        """Create sample dogs configuration."""
        return [{CONF_DOG_ID: f"dog{i}", CONF_DOG_NAME: f"Dog{i}", "modules": {"feeding": True}} for i in range(5)]

    async def test_concurrent_data_updates(self, initialized_manager):
        """Test concurrent data updates."""
        async def update_dog_data(dog_id: str, iteration: int):
            for i in range(10):
                data = {"iteration": iteration, "update": i, "timestamp": dt_util.now().isoformat()}
                await initialized_manager.async_update_dog_data(dog_id, "feeding", data)

        # Run concurrent updates
        await asyncio.gather(*[update_dog_data(f"dog{i}", i) for i in range(5)])
        
        # Verify all dogs have data
        for i in range(5):
            dog_data = await initialized_manager.async_get_dog_data(f"dog{i}")
            assert dog_data is not None
            assert "feeding" in dog_data
            assert "iteration" in dog_data["feeding"]

    async def test_concurrent_read_write(self, initialized_manager):
        """Test concurrent read and write operations."""
        async def writer():
            for i in range(20):
                await initialized_manager.async_update_dog_data("dog0", "feeding", {"write_count": i})

        async def reader():
            results = []
            for i in range(20):
                data = await initialized_manager.async_get_dog_data("dog0")
                results.append(data)
            return results

        # Run concurrent read/write
        write_task = asyncio.create_task(writer())
        read_results = await asyncio.gather(*[reader() for _ in range(3)])
        await write_task
        
        # All reads should succeed
        for results in read_results:
            assert len(results) == 20
            for result in results:
                assert result is not None

    async def test_concurrent_validation(self, initialized_manager):
        """Test concurrent validation operations."""
        test_data = {
            "dog_info": {CONF_DOG_ID: "dog0", CONF_DOG_NAME: "Test"},
            "feeding": {"meals_today": 2},
        }

        async def validate_data(iteration: int):
            results = []
            for i in range(10):
                result = await initialized_manager.async_validate_dog_data("dog0", test_data)
                results.append(result)
            return results

        # Run concurrent validations
        validation_results = await asyncio.gather(*[validate_data(i) for i in range(3)])
        
        # All validations should succeed
        for results in validation_results:
            for result in results:
                assert result["valid"] is True

    async def test_lock_contention_handling(self, initialized_manager):
        """Test that lock contention is handled properly."""
        async def long_operation(dog_id: str):
            async with initialized_manager._data_lock:
                # Simulate longer operation
                await asyncio.sleep(0.01)
                data = {"operation": "long", "timestamp": dt_util.now().isoformat()}
                initialized_manager._dogs_data[dog_id]["feeding"] = data

        async def quick_operation(dog_id: str):
            result = await initialized_manager.async_get_dog_data(dog_id)
            return result is not None

        # Mix long and quick operations
        tasks = []
        for i in range(5):
            tasks.append(long_operation(f"dog{i}"))
            tasks.append(quick_operation(f"dog{i}"))

        # Should complete without deadlock
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5.0)
        
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

    async def test_operations_on_uninitialized_manager(self, manager):
        """Test operations on uninitialized manager."""
        # Should handle gracefully
        dog_data = await manager.async_get_dog_data("dog1")
        assert dog_data is None
        
        result = await manager.async_update_dog_data("dog1", "feeding", {"test": "data"})
        assert result is False
        
        all_data = await manager.async_get_all_dogs_data()
        assert all_data == {}

    async def test_malformed_config_data(self, manager):
        """Test handling of malformed configuration data."""
        malformed_config = [
            {"missing_dog_id": "value"},  # Missing required CONF_DOG_ID
            {CONF_DOG_ID: "dog2", "missing_name": "value"},  # Missing CONF_DOG_NAME
        ]
        
        # Should not crash during initialization
        await manager.async_initialize(malformed_config)
        
        # Should handle missing fields gracefully
        config = manager.get_dog_config("dog2")
        assert config is not None

    async def test_empty_module_updates(self, manager):
        """Test updates with empty or None data."""
        config = [{CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test", "modules": {"feeding": True}}]
        await manager.async_initialize(config)
        
        # Empty dict update
        result = await manager.async_update_dog_data("dog1", "feeding", {})
        assert result is True
        
        # None values in update (should be handled gracefully)
        result = await manager.async_update_dog_data("dog1", "feeding", {"test": None})
        assert result is True

    def test_config_access_edge_cases(self, manager):
        """Test configuration access edge cases."""
        # Empty config
        manager._dogs_config = []
        
        assert manager.get_dog_config("any") is None
        assert manager.get_all_dog_configs() == []
        assert manager.get_dog_ids() == []
        assert manager.get_enabled_modules("any") == set()

    async def test_validation_edge_cases(self, manager):
        """Test validation edge cases."""
        config = [{CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test"}]
        await manager.async_initialize(config)
        
        # Empty data validation
        result = await manager.async_validate_dog_data("dog1", {})
        assert result["valid"] is False
        
        # Very large data validation
        large_data = {
            "dog_info": {CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test"},
            "large_field": "x" * 10000,  # Large string
        }
        result = await manager.async_validate_dog_data("dog1", large_data)
        # Should handle without crashing

    async def test_cache_edge_cases(self, manager):
        """Test validation cache edge cases."""
        config = [{CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test"}]
        await manager.async_initialize(config)
        
        # Manually corrupt cache for edge case testing
        manager._validation_cache["corrupt"] = None
        manager._cache_expiry["corrupt"] = "not_a_datetime"
        
        # Should handle corruption gracefully
        await manager._clean_validation_cache()

    async def test_statistics_edge_cases(self, manager):
        """Test statistics calculation edge cases."""
        # Empty manager
        stats = await manager.async_get_data_statistics()
        assert stats["total_dogs"] == 0
        assert stats["total_data_points"] == 0
        assert stats["recent_updates"] == 0
        
        # Manager with dogs but no data
        config = [{CONF_DOG_ID: "dog1", CONF_DOG_NAME: "Test"}]
        await manager.async_initialize(config)
        
        stats = await manager.async_get_data_statistics()
        assert stats["total_dogs"] == 1
        assert isinstance(stats["total_data_points"], int)
