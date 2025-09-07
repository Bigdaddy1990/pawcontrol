"""Comprehensive tests for Paw Control services module.

Tests all service handlers, schema validation, error handling,
caching functionality, and event integration.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
import voluptuous as vol
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_RESET_TIME,
    DEFAULT_RESET_TIME,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
)
from custom_components.pawcontrol.exceptions import (
    DogNotFoundError,
    PawControlError,
)
from custom_components.pawcontrol.services import (
    SERVICE_DAILY_RESET_SCHEMA,
    SERVICE_FEED_DOG_SCHEMA,
    SERVICE_GROOMING_SCHEMA,
    SERVICE_HEALTH_SCHEMA,
    SERVICE_MEDICATION_SCHEMA,
    SERVICE_NOTIFY_TEST_SCHEMA,
    SERVICE_WALK_SCHEMA,
    PawControlServiceManager,
    _build_dog_service_schema,
    _get_cached_schema,
    async_setup_daily_reset_scheduler,
    service_handler,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util.dt import utcnow


class TestSchemaFunctions:
    """Test schema utility functions."""

    def test_get_cached_schema_first_call(self):
        """Test cached schema creation on first call."""
        schema_id = "test_schema"
        
        def builder():
            return vol.Schema({"test": str})
        
        # Clear any existing cache
        from custom_components.pawcontrol.services import _SCHEMA_CACHE
        _SCHEMA_CACHE.clear()
        
        schema = _get_cached_schema(schema_id, builder)
        
        assert isinstance(schema, vol.Schema)
        assert schema_id in _SCHEMA_CACHE

    def test_get_cached_schema_subsequent_call(self):
        """Test cached schema retrieval on subsequent calls."""
        schema_id = "test_schema_2"
        
        def builder():
            return vol.Schema({"test": str})
        
        # First call
        schema1 = _get_cached_schema(schema_id, builder)
        
        # Second call should return same object
        schema2 = _get_cached_schema(schema_id, builder)
        
        assert schema1 is schema2

    def test_build_dog_service_schema_basic(self):
        """Test building basic dog service schema."""
        schema = _build_dog_service_schema()
        
        # Should have required dog_id
        assert vol.Required(ATTR_DOG_ID) in schema.schema

    def test_build_dog_service_schema_additional_fields(self):
        """Test building dog service schema with additional fields."""
        additional = {
            vol.Optional("test_field"): str,
            vol.Required("required_field"): int,
        }
        
        schema = _build_dog_service_schema(additional)
        
        # Should have all fields
        assert vol.Required(ATTR_DOG_ID) in schema.schema
        assert vol.Optional("test_field") in schema.schema
        assert vol.Required("required_field") in schema.schema

    def test_service_schemas_valid(self):
        """Test that all service schemas are valid."""
        schemas = [
            SERVICE_FEED_DOG_SCHEMA,
            SERVICE_WALK_SCHEMA,
            SERVICE_HEALTH_SCHEMA,
            SERVICE_MEDICATION_SCHEMA,
            SERVICE_GROOMING_SCHEMA,
            SERVICE_NOTIFY_TEST_SCHEMA,
            SERVICE_DAILY_RESET_SCHEMA,
        ]
        
        for schema in schemas:
            assert isinstance(schema, vol.Schema)

    def test_feed_dog_schema_validation(self):
        """Test feed dog schema validation."""
        # Valid data
        valid_data = {
            ATTR_DOG_ID: "test_dog",
            ATTR_MEAL_TYPE: "breakfast",
            ATTR_PORTION_SIZE: 150.0,
            "food_type": "dry_food",
            "notes": "Test feeding",
        }
        
        result = SERVICE_FEED_DOG_SCHEMA(valid_data)
        assert result[ATTR_DOG_ID] == "test_dog"
        assert result[ATTR_MEAL_TYPE] == "breakfast"
        assert result[ATTR_PORTION_SIZE] == 150.0

    def test_feed_dog_schema_defaults(self):
        """Test feed dog schema default values."""
        minimal_data = {ATTR_DOG_ID: "test_dog"}
        
        result = SERVICE_FEED_DOG_SCHEMA(minimal_data)
        assert result[ATTR_MEAL_TYPE] == "snack"
        assert result[ATTR_PORTION_SIZE] == 0.0
        assert result["food_type"] == "dry_food"
        assert result["notes"] == ""

    def test_feed_dog_schema_invalid(self):
        """Test feed dog schema validation with invalid data."""
        # Missing required field
        with pytest.raises(vol.Invalid):
            SERVICE_FEED_DOG_SCHEMA({})
        
        # Invalid meal type
        with pytest.raises(vol.Invalid):
            SERVICE_FEED_DOG_SCHEMA({
                ATTR_DOG_ID: "test_dog",
                ATTR_MEAL_TYPE: "invalid_meal",
            })
        
        # Invalid portion size
        with pytest.raises(vol.Invalid):
            SERVICE_FEED_DOG_SCHEMA({
                ATTR_DOG_ID: "test_dog",
                ATTR_PORTION_SIZE: -10.0,
            })

    def test_health_schema_validation(self):
        """Test health schema validation."""
        valid_data = {
            ATTR_DOG_ID: "test_dog",
            "weight": 25.5,
            "temperature": 38.5,
            "mood": "happy",
            "activity_level": "high",
            "health_status": "excellent",
            "note": "Dog seems healthy",
        }
        
        result = SERVICE_HEALTH_SCHEMA(valid_data)
        assert result[ATTR_DOG_ID] == "test_dog"
        assert result["weight"] == 25.5
        assert result["temperature"] == 38.5

    def test_medication_schema_validation(self):
        """Test medication schema validation."""
        valid_data = {
            ATTR_DOG_ID: "test_dog",
            "medication_name": "Flea Treatment",
            "dosage": "10mg",
            "notes": "Monthly treatment",
        }
        
        result = SERVICE_MEDICATION_SCHEMA(valid_data)
        assert result[ATTR_DOG_ID] == "test_dog"
        assert result["medication_name"] == "Flea Treatment"
        assert result["dosage"] == "10mg"


class TestServiceHandlerDecorator:
    """Test service handler decorator functionality."""

    @pytest.fixture
    def mock_service_manager(self):
        """Create mock service manager."""
        manager = Mock()
        manager._get_runtime_data_cached = Mock()
        manager._get_available_dog_ids = Mock(return_value=["test_dog", "other_dog"])
        return manager

    def test_service_handler_decorator_basic(self, mock_service_manager):
        """Test basic service handler decoration."""
        @service_handler(require_dog=True)
        async def test_handler(self, call, dog_id, runtime_data):  # noqa: F811
            return f"handled {dog_id}"
        
        # Verify decorator was applied
        assert hasattr(test_handler, "__wrapped__")

    @pytest.mark.asyncio
    async def test_service_handler_with_dog_success(self, mock_service_manager):
        """Test service handler with successful dog lookup."""
        mock_runtime_data = {"test": "data"}
        mock_service_manager._get_runtime_data_cached.return_value = mock_runtime_data
        
        @service_handler(require_dog=True)
        async def test_handler(self, call, dog_id, runtime_data):
            assert dog_id == "test_dog"
            assert runtime_data == mock_runtime_data
            return "success"
        
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        result = await test_handler(mock_service_manager, call)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_service_handler_missing_dog_id(self, mock_service_manager):
        """Test service handler with missing dog_id."""
        @service_handler(require_dog=True)
        async def test_handler(self, call, dog_id, runtime_data):
            return "success"
        
        call = Mock()  # noqa: F811
        call.data = {}
        
        with pytest.raises(ServiceValidationError, match="dog_id is required"):
            await test_handler(mock_service_manager, call)

    @pytest.mark.asyncio
    async def test_service_handler_dog_not_found(self, mock_service_manager):
        """Test service handler with dog not found."""
        mock_service_manager._get_runtime_data_cached.return_value = None
        
        @service_handler(require_dog=True)
        async def test_handler(self, call, dog_id, runtime_data):
            return "success"
        
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "nonexistent_dog"}
        
        with pytest.raises(ServiceValidationError):
            await test_handler(mock_service_manager, call)

    @pytest.mark.asyncio
    async def test_service_handler_no_dog_required(self, mock_service_manager):
        """Test service handler when dog is not required."""
        @service_handler(require_dog=False)
        async def test_handler(self, call):
            return "success"
        
        call = Mock()  # noqa: F811
        call.data = {}
        
        result = await test_handler(mock_service_manager, call)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_service_handler_timeout(self, mock_service_manager):
        """Test service handler timeout."""
        @service_handler(require_dog=False, timeout=0.1)
        async def test_handler(self, call):
            await asyncio.sleep(0.2)
            return "success"
        
        call = Mock()  # noqa: F811
        call.data = {}
        
        with pytest.raises(ServiceValidationError, match="timed out"):
            await test_handler(mock_service_manager, call)

    @pytest.mark.asyncio
    async def test_service_handler_paw_control_error(self, mock_service_manager):
        """Test service handler with PawControlError."""
        @service_handler(require_dog=False)
        async def test_handler(self, call):
            raise PawControlError("Test error", "TEST_CODE")
        
        call = Mock()  # noqa: F811
        call.data = {}
        
        with pytest.raises(ServiceValidationError):
            await test_handler(mock_service_manager, call)

    @pytest.mark.asyncio
    async def test_service_handler_unexpected_error(self, mock_service_manager):
        """Test service handler with unexpected error."""
        @service_handler(require_dog=False)
        async def test_handler(self, call):
            raise ValueError("Unexpected error")
        
        call = Mock()  # noqa: F811
        call.data = {}
        
        with pytest.raises(ServiceValidationError, match="Service failed"):
            await test_handler(mock_service_manager, call)


class TestPawControlServiceManager:
    """Test PawControlServiceManager class."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "coordinator": Mock(),
                    "data": Mock(),
                    "notifications": Mock(),
                }
            }
        }
        hass.services = Mock()
        hass.services.async_register = Mock()
        hass.services.async_remove = Mock()
        hass.bus = Mock()
        hass.bus.async_fire = Mock()
        return hass

    @pytest.fixture
    def service_manager(self, mock_hass):
        """Create service manager instance."""
        return PawControlServiceManager(mock_hass)

    def test_service_manager_initialization(self, service_manager, mock_hass):
        """Test service manager initialization."""
        assert service_manager.hass == mock_hass
        assert service_manager._registered_services == set()
        assert service_manager._runtime_cache == {}
        assert service_manager._base_ttl == 30.0

    @pytest.mark.asyncio
    async def test_async_register_services_success(self, service_manager):
        """Test successful service registration."""
        await service_manager.async_register_services()
        
        # Should register all services
        expected_services = len(service_manager._service_registry)
        assert len(service_manager._registered_services) == expected_services
        
        # Should call async_register for each service
        assert service_manager.hass.services.async_register.call_count == expected_services

    @pytest.mark.asyncio
    async def test_async_register_services_already_registered(self, service_manager):
        """Test service registration when already registered."""
        # Simulate already registered
        service_manager._registered_services.add("test_service")
        
        await service_manager.async_register_services()
        
        # Should not register again
        service_manager.hass.services.async_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_register_services_failure(self, service_manager):
        """Test service registration failure."""
        service_manager.hass.services.async_register.side_effect = Exception("Registration failed")
        
        with pytest.raises(Exception, match="Registration failed"):
            await service_manager.async_register_services()

    @pytest.mark.asyncio
    async def test_async_unregister_services(self, service_manager):
        """Test service unregistration."""
        # Simulate registered services
        service_manager._registered_services.update(["service1", "service2"])
        
        await service_manager.async_unregister_services()
        
        # Should unregister all services
        assert len(service_manager._registered_services) == 0
        assert service_manager.hass.services.async_remove.call_count == 2

    @pytest.mark.asyncio
    async def test_async_unregister_services_with_error(self, service_manager):
        """Test service unregistration with errors."""
        service_manager._registered_services.update(["service1", "service2"])
        service_manager.hass.services.async_remove.side_effect = Exception("Unregister failed")
        
        # Should not raise exception, just log warnings
        await service_manager.async_unregister_services()
        
        # Should still clear registered services
        assert len(service_manager._registered_services) == 0

    def test_get_runtime_data_cached_miss(self, service_manager):
        """Test cache miss scenario."""
        dog_id = "test_dog"
        
        with patch.object(service_manager, "_get_runtime_data_for_dog") as mock_get:
            mock_runtime_data = {"test": "data"}
            mock_get.return_value = mock_runtime_data
            
            result = service_manager._get_runtime_data_cached(dog_id)
            
            assert result == mock_runtime_data
            assert dog_id in service_manager._runtime_cache
            assert service_manager._cache_misses == 1

    def test_get_runtime_data_cached_hit(self, service_manager):
        """Test cache hit scenario."""
        dog_id = "test_dog"
        cached_data = {"cached": "data"}
        now = utcnow().timestamp()
        
        # Pre-populate cache
        service_manager._runtime_cache[dog_id] = (cached_data, now, 5)
        
        with patch.object(service_manager, "_get_runtime_data_for_dog") as mock_get:
            result = service_manager._get_runtime_data_cached(dog_id)
            
            assert result == cached_data
            assert service_manager._cache_hits == 1
            mock_get.assert_not_called()

    def test_get_runtime_data_cached_expired(self, service_manager):
        """Test expired cache entry."""
        dog_id = "test_dog"
        cached_data = {"cached": "data"}
        old_time = utcnow().timestamp() - 1000  # Very old
        
        # Pre-populate with expired entry
        service_manager._runtime_cache[dog_id] = (cached_data, old_time, 5)
        
        with patch.object(service_manager, "_get_runtime_data_for_dog") as mock_get:
            new_data = {"new": "data"}
            mock_get.return_value = new_data
            
            result = service_manager._get_runtime_data_cached(dog_id)
            
            assert result == new_data
            assert service_manager._cache_misses == 1

    def test_cleanup_cache(self, service_manager):
        """Test cache cleanup functionality."""
        now = utcnow().timestamp()
        old_time = now - 1000
        
        # Add entries with different ages
        service_manager._runtime_cache.update({
            "old_dog": ({"data": "old"}, old_time, 5),
            "new_dog": ({"data": "new"}, now, 5),
        })
        
        service_manager._cleanup_cache(now)
        
        # Old entry should be removed
        assert "old_dog" not in service_manager._runtime_cache
        assert "new_dog" in service_manager._runtime_cache

    def test_get_runtime_data_for_dog_success(self, service_manager):
        """Test getting runtime data for existing dog."""
        dog_id = "test_dog"
        
        # Mock coordinator with config entry
        mock_coordinator = Mock()
        mock_entry = Mock()
        mock_entry.data = {CONF_DOGS: [{CONF_DOG_ID: dog_id}]}
        mock_coordinator.config_entry = mock_entry
        
        # Set up runtime_data
        mock_runtime_data = {"dogs": [{CONF_DOG_ID: dog_id}]}
        mock_entry.runtime_data = mock_runtime_data
        
        service_manager.hass.data[DOMAIN]["test_entry"]["coordinator"] = mock_coordinator
        
        result = service_manager._get_runtime_data_for_dog(dog_id)
        
        assert result == mock_runtime_data

    def test_get_runtime_data_for_dog_not_found(self, service_manager):
        """Test getting runtime data for non-existent dog."""
        result = service_manager._get_runtime_data_for_dog("nonexistent_dog")
        assert result is None

    def test_get_available_dog_ids(self, service_manager):
        """Test getting available dog IDs."""
        mock_coordinator = Mock()
        mock_coordinator.get_dog_ids.return_value = ["dog1", "dog2"]
        
        service_manager.hass.data[DOMAIN]["test_entry"]["coordinator"] = mock_coordinator
        
        result = service_manager._get_available_dog_ids()
        assert "dog1" in result
        assert "dog2" in result

    def test_estimate_calories(self):
        """Test calorie estimation."""
        # Test dry food
        calories = PawControlServiceManager._estimate_calories(100.0, "dry_food")
        assert calories == 350.0
        
        # Test wet food
        calories = PawControlServiceManager._estimate_calories(200.0, "wet_food")
        assert calories == 170.0
        
        # Test unknown food type
        calories = PawControlServiceManager._estimate_calories(100.0, "unknown")
        assert calories == 200.0

    def test_get_cache_stats(self, service_manager):
        """Test cache statistics."""
        service_manager._cache_hits = 10
        service_manager._cache_misses = 5
        service_manager._registered_services.add("test_service")
        
        stats = service_manager.get_cache_stats()
        
        assert stats["cache_hits"] == 10
        assert stats["cache_misses"] == 5
        assert stats["hit_rate"] == 66.7
        assert stats["registered_services"] == 1


class TestServiceHandlers:
    """Test individual service handlers."""

    @pytest.fixture
    def service_manager(self, mock_hass):
        """Create service manager instance."""
        return PawControlServiceManager(mock_hass)

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {DOMAIN: {}}
        hass.bus = Mock()
        hass.bus.async_fire = Mock()
        return hass

    @pytest.fixture
    def mock_runtime_data(self):
        """Create mock runtime data."""
        data_manager = Mock()
        data_manager.async_feed_dog = AsyncMock()
        data_manager.async_log_feeding = AsyncMock()
        data_manager.async_start_walk = AsyncMock(return_value="walk_123")
        data_manager.async_get_current_walk = AsyncMock()
        data_manager.async_end_walk = AsyncMock()
        data_manager.async_log_health = AsyncMock()
        data_manager.async_start_grooming = AsyncMock(return_value="grooming_123")
        data_manager.async_reset_dog_daily_stats = AsyncMock()
        
        coordinator = Mock()
        coordinator.async_request_selective_refresh = AsyncMock()
        
        notification_manager = Mock()
        notification_manager.async_send_notification = AsyncMock()
        
        return {
            "data_manager": data_manager,
            "coordinator": coordinator,
            "notification_manager": notification_manager,
        }

    @pytest.mark.asyncio
    async def test_handle_feed_dog_service(self, service_manager, mock_runtime_data):
        """Test feed dog service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            ATTR_MEAL_TYPE: "breakfast",
            ATTR_PORTION_SIZE: 150.0,
            "food_type": "dry_food",
            "notes": "Test feeding",
        }
        
        await service_manager._handle_feed_dog_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify data manager calls
        mock_runtime_data["data_manager"].async_feed_dog.assert_called_once_with(
            "test_dog", 150.0
        )
        mock_runtime_data["data_manager"].async_log_feeding.assert_called_once()
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once()
        
        # Verify coordinator refresh
        mock_runtime_data["coordinator"].async_request_selective_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_feed_dog_service_with_calorie_estimation(
        self, service_manager, mock_runtime_data
    ):
        """Test feed dog service with calorie estimation."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            ATTR_PORTION_SIZE: 100.0,
            "food_type": "wet_food",
        }
        
        await service_manager._handle_feed_dog_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Should estimate calories for wet food
        feeding_call = mock_runtime_data["data_manager"].async_log_feeding.call_args[0][1]
        assert feeding_call["calories"] == 85.0  # 100g wet food

    @pytest.mark.asyncio
    async def test_handle_start_walk_service(self, service_manager, mock_runtime_data):
        """Test start walk service handler."""
        mock_runtime_data["data_manager"].async_get_current_walk.return_value = None
        
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "label": "Morning walk",
            "location": "Park",
            "walk_type": "exercise",
        }
        
        await service_manager._handle_start_walk_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify walk started
        mock_runtime_data["data_manager"].async_start_walk.assert_called_once()
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once_with(
            EVENT_WALK_STARTED, 
            {
                ATTR_DOG_ID: "test_dog",
                "walk_id": "walk_123",
                "start_time": mock_runtime_data["data_manager"].async_start_walk.call_args[0][0],
            }
        )

    @pytest.mark.asyncio
    async def test_handle_start_walk_service_already_walking(
        self, service_manager, mock_runtime_data
    ):
        """Test start walk service when walk already in progress."""
        mock_runtime_data["data_manager"].async_get_current_walk.return_value = {
            "walk_id": "existing_walk"
        }
        
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        with pytest.raises(ServiceValidationError, match="Walk already in progress"):
            await service_manager._handle_start_walk_service(
                call, "test_dog", mock_runtime_data
            )

    @pytest.mark.asyncio
    async def test_handle_end_walk_service(self, service_manager, mock_runtime_data):
        """Test end walk service handler."""
        mock_runtime_data["data_manager"].async_get_current_walk.return_value = {
            "walk_id": "walk_123"
        }
        
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "distance": 2000.0,
            "duration": 45,
            "notes": "Good walk",
        }
        
        await service_manager._handle_end_walk_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify walk ended
        mock_runtime_data["data_manager"].async_end_walk.assert_called_once()
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once_with(
            EVENT_WALK_ENDED,
            {
                ATTR_DOG_ID: "test_dog",
                "walk_id": "walk_123",
                "end_time": mock_runtime_data["data_manager"].async_end_walk.call_args[0][0],
                "distance": 2000.0,
                "duration": 45,
            }
        )

    @pytest.mark.asyncio
    async def test_handle_end_walk_service_no_active_walk(
        self, service_manager, mock_runtime_data
    ):
        """Test end walk service when no walk is active."""
        mock_runtime_data["data_manager"].async_get_current_walk.return_value = None
        
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        with pytest.raises(ServiceValidationError, match="No active walk"):
            await service_manager._handle_end_walk_service(
                call, "test_dog", mock_runtime_data
            )

    @pytest.mark.asyncio
    async def test_handle_log_health_service(self, service_manager, mock_runtime_data):
        """Test log health service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "weight": 25.5,
            "temperature": 38.5,
            "mood": "happy",
            "activity_level": "high",
            "health_status": "excellent",
            "note": "Dog seems healthy",
        }
        
        await service_manager._handle_log_health_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify health logged
        mock_runtime_data["data_manager"].async_log_health.assert_called_once()
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once_with(
            EVENT_HEALTH_LOGGED,
            {
                ATTR_DOG_ID: "test_dog",
                "timestamp": mock_runtime_data["data_manager"].async_log_health.call_args[0][0],
                "weight": 25.5,
                "temperature": 38.5,
                "mood": "happy",
                "activity_level": "high",
                "health_status": "excellent",
                "note": "Dog seems healthy",
            }
        )

    @pytest.mark.asyncio
    async def test_handle_log_medication_service(self, service_manager, mock_runtime_data):
        """Test log medication service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "medication_name": "Flea Treatment",
            "dosage": "10mg",
            "notes": "Monthly treatment",
        }
        
        await service_manager._handle_log_medication_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify medication logged
        mock_runtime_data["data_manager"].async_log_health.assert_called_once()
        logged_data = mock_runtime_data["data_manager"].async_log_health.call_args[0][1]
        assert logged_data["type"] == "medication"
        assert logged_data["medication_name"] == "Flea Treatment"

    @pytest.mark.asyncio
    async def test_handle_start_grooming_service(self, service_manager, mock_runtime_data):
        """Test start grooming service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "type": "bath",
            "notes": "Monthly bath",
        }
        
        await service_manager._handle_start_grooming_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify grooming started
        mock_runtime_data["data_manager"].async_start_grooming.assert_called_once_with(
            "test_dog", {"type": "bath", "notes": "Monthly bath"}
        )

    @pytest.mark.asyncio
    async def test_handle_daily_reset_service(self, service_manager, mock_runtime_data):
        """Test daily reset service handler."""
        # Mock dog IDs
        with patch.object(service_manager, "_get_available_dog_ids") as mock_get_dogs:
            mock_get_dogs.return_value = ["dog1", "dog2"]
            
            with patch.object(service_manager, "_get_runtime_data_cached") as mock_get_data:
                mock_get_data.return_value = mock_runtime_data
                
                call = Mock()
                call.data = {"force": False}
                
                await service_manager._handle_daily_reset_service(call)
                
                # Should reset stats for all dogs
                assert mock_runtime_data["data_manager"].async_reset_dog_daily_stats.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_daily_reset_service_specific_dogs(
        self, service_manager, mock_runtime_data
    ):
        """Test daily reset service for specific dogs."""
        with patch.object(service_manager, "_get_runtime_data_cached") as mock_get_data:
            mock_get_data.return_value = mock_runtime_data
            
            call = Mock()
            call.data = {"dog_ids": ["specific_dog"]}
            
            await service_manager._handle_daily_reset_service(call)
            
            # Should only reset specified dog
            mock_runtime_data["data_manager"].async_reset_dog_daily_stats.assert_called_once_with(
                "specific_dog"
            )

    @pytest.mark.asyncio
    async def test_handle_notify_test_service(self, service_manager, mock_runtime_data):
        """Test notify test service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "message": "Test notification",
            "priority": "high",
        }
        
        await service_manager._handle_notify_test_service(
            call, "test_dog", mock_runtime_data
        )
        
        # Verify notification sent
        mock_runtime_data["notification_manager"].async_send_notification.assert_called_once_with(
            "test_dog",
            "Test notification",
            priority="high",
            test_mode=True,
        )


class TestHealthAwareFeedingServices:
    """Test health-aware feeding service handlers."""

    @pytest.fixture
    def service_manager(self, mock_hass):
        """Create service manager instance."""
        return PawControlServiceManager(mock_hass)

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {DOMAIN: {}}
        hass.bus = Mock()
        hass.bus.async_fire = Mock()
        return hass

    @pytest.fixture
    def mock_runtime_data_with_feeding(self):
        """Create mock runtime data with feeding manager."""
        mock_config = Mock()
        mock_config.calculate_portion_size = Mock(return_value=200.0)
        mock_config.health_aware_portions = True
        mock_config.dog_weight = 25.0
        
        feeding_manager = Mock()
        feeding_manager._configs = {"test_dog": mock_config}
        feeding_manager._invalidate_cache = Mock()
        feeding_manager.async_add_feeding = AsyncMock()
        feeding_manager.async_add_feeding.return_value = Mock(time=utcnow())
        
        data_manager = Mock()
        data_manager.async_log_health = AsyncMock()
        
        coordinator = Mock()
        coordinator.async_request_selective_refresh = AsyncMock()
        
        return {
            "feeding_manager": feeding_manager,
            "data_manager": data_manager,
            "coordinator": coordinator,
        }

    @pytest.mark.asyncio
    async def test_handle_recalculate_health_portions(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test recalculate health portions service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "trigger_reason": "weight_change",
            "force_update": True,
        }
        
        await service_manager._handle_recalculate_health_portions(
            call, "test_dog", mock_runtime_data_with_feeding
        )
        
        # Verify cache was invalidated
        feeding_manager = mock_runtime_data_with_feeding["feeding_manager"]
        feeding_manager._invalidate_cache.assert_called_once_with("test_dog")
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once()
        event_args = service_manager.hass.bus.async_fire.call_args[0]
        assert "health_portions_recalculated" in event_args[0]

    @pytest.mark.asyncio
    async def test_handle_recalculate_health_portions_no_config(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test recalculate health portions with no config."""
        # Remove config
        mock_runtime_data_with_feeding["feeding_manager"]._configs = {}
        
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        with pytest.raises(ServiceValidationError, match="No feeding configuration"):
            await service_manager._handle_recalculate_health_portions(
                call, "test_dog", mock_runtime_data_with_feeding
            )

    @pytest.mark.asyncio
    async def test_handle_feed_health_aware(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test health-aware feeding service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "meal_type": "breakfast",
            "use_health_calculation": True,
            "notes": "Health-aware breakfast",
        }
        
        await service_manager._handle_feed_health_aware(
            call, "test_dog", mock_runtime_data_with_feeding
        )
        
        # Verify feeding was added
        feeding_manager = mock_runtime_data_with_feeding["feeding_manager"]
        feeding_manager.async_add_feeding.assert_called_once()
        
        # Verify event fired
        service_manager.hass.bus.async_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_feed_health_aware_manual_override(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test health-aware feeding with manual portion override."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "meal_type": "dinner",
            "override_portion": 300.0,
        }
        
        await service_manager._handle_feed_health_aware(
            call, "test_dog", mock_runtime_data_with_feeding
        )
        
        # Should use override portion
        feeding_call = mock_runtime_data_with_feeding["feeding_manager"].async_add_feeding.call_args
        assert feeding_call[1]["amount"] == 300.0

    @pytest.mark.asyncio
    async def test_handle_update_health_data(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test update health data service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "weight": 26.0,
            "activity_level": "high",
            "body_condition_score": 5,
        }
        
        await service_manager._handle_update_health_data(
            call, "test_dog", mock_runtime_data_with_feeding
        )
        
        # Verify health data logged
        data_manager = mock_runtime_data_with_feeding["data_manager"]
        data_manager.async_log_health.assert_called_once()
        
        # Verify feeding config updated
        config = mock_runtime_data_with_feeding["feeding_manager"]._configs["test_dog"]
        assert config.dog_weight == 26.0
        assert config.activity_level == "high"
        assert config.body_condition_score == 5

    @pytest.mark.asyncio
    async def test_handle_feed_with_medication(
        self, service_manager, mock_runtime_data_with_feeding
    ):
        """Test feed with medication service handler."""
        call = Mock()  # noqa: F811
        call.data = {
            ATTR_DOG_ID: "test_dog",
            "medication_name": "Joint Supplement",
            "dosage": "2 tablets",
            "auto_calculate_portion": True,
            "timing": "optimal",
        }
        
        await service_manager._handle_feed_with_medication(
            call, "test_dog", mock_runtime_data_with_feeding
        )
        
        # Verify feeding was added with reduced portion
        feeding_manager = mock_runtime_data_with_feeding["feeding_manager"]
        feeding_manager.async_add_feeding.assert_called_once()
        feeding_call = feeding_manager.async_add_feeding.call_args[1]
        assert feeding_call["amount"] == 60.0  # 30% of 200g normal portion
        
        # Verify medication logged in health data
        data_manager = mock_runtime_data_with_feeding["data_manager"]
        data_manager.async_log_health.assert_called_once()


class TestDailyResetScheduler:
    """Test daily reset scheduler functionality."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        hass.async_create_task = Mock()
        return hass

    @pytest.fixture
    def mock_entry(self):
        """Create mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.options = {CONF_RESET_TIME: "02:00:00"}
        return entry

    @pytest.mark.asyncio
    async def test_async_setup_daily_reset_scheduler_success(
        self, mock_hass, mock_entry
    ):
        """Test successful daily reset scheduler setup."""
        with patch("custom_components.pawcontrol.services.async_track_time") as mock_track:
            await async_setup_daily_reset_scheduler(mock_hass, mock_entry)
            
            # Should register time tracking
            mock_track.assert_called_once()
            call_args = mock_track.call_args
            assert call_args[0][0] == mock_hass  # hass
            assert callable(call_args[0][1])  # callback
            assert call_args[1]["hour"] == 2
            assert call_args[1]["minute"] == 0
            assert call_args[1]["second"] == 0

    @pytest.mark.asyncio
    async def test_async_setup_daily_reset_scheduler_default_time(
        self, mock_hass
    ):
        """Test daily reset scheduler with default time."""
        entry = Mock(spec=ConfigEntry)
        entry.options = {}  # No reset time specified
        
        with patch("custom_components.pawcontrol.services.async_track_time") as mock_track:
            await async_setup_daily_reset_scheduler(mock_hass, entry)
            
            # Should use default time
            call_args = mock_track.call_args[1]
            assert call_args["hour"] == 2  # DEFAULT_RESET_TIME is "02:00:00"
            assert call_args["minute"] == 0
            assert call_args["second"] == 0

    @pytest.mark.asyncio
    async def test_async_setup_daily_reset_scheduler_invalid_time(
        self, mock_hass, mock_entry
    ):
        """Test daily reset scheduler with invalid time format."""
        mock_entry.options = {CONF_RESET_TIME: "invalid_time"}
        
        # Should not raise exception, just log error
        await async_setup_daily_reset_scheduler(mock_hass, mock_entry)

    @pytest.mark.asyncio
    async def test_daily_reset_callback_execution(self, mock_hass, mock_entry):
        """Test that daily reset callback works correctly."""
        with patch("custom_components.pawcontrol.services.async_track_time") as mock_track:
            await async_setup_daily_reset_scheduler(mock_hass, mock_entry)
            
            # Get the callback function
            callback = mock_track.call_args[0][1]
            
            # Execute callback
            callback(None)
            
            # Should create task for daily reset service
            mock_hass.async_create_task.assert_called_once()


class TestServiceIntegration:
    """Test service integration scenarios."""

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "coordinator": Mock(),
                    "data": Mock(),
                    "notifications": Mock(),
                }
            }
        }
        hass.services = Mock()
        hass.services.async_register = Mock()
        hass.services.async_call = AsyncMock()
        hass.bus = Mock()
        hass.bus.async_fire = Mock()
        return hass

    @pytest.mark.asyncio
    async def test_full_service_lifecycle(self, mock_hass):
        """Test complete service lifecycle."""
        service_manager = PawControlServiceManager(mock_hass)
        
        # Register services
        await service_manager.async_register_services()
        
        # Verify all services registered
        expected_count = len(service_manager._service_registry)
        assert len(service_manager._registered_services) == expected_count
        
        # Unregister services
        await service_manager.async_unregister_services()
        
        # Verify all services unregistered
        assert len(service_manager._registered_services) == 0

    @pytest.mark.asyncio
    async def test_service_with_real_call_object(self, mock_hass):
        """Test service with realistic ServiceCall object."""
        service_manager = PawControlServiceManager(mock_hass)
        
        # Create realistic call object
        call = ServiceCall(  # noqa: F811
            domain=DOMAIN,
            service=SERVICE_FEED_DOG,
            data={
                ATTR_DOG_ID: "test_dog",
                ATTR_MEAL_TYPE: "breakfast",
                ATTR_PORTION_SIZE: 150.0,
            }
        )
        
        # Mock runtime data lookup
        mock_runtime_data = {
            "data_manager": Mock(),
            "coordinator": Mock(),
        }
        mock_runtime_data["data_manager"].async_feed_dog = AsyncMock()
        mock_runtime_data["data_manager"].async_log_feeding = AsyncMock()
        mock_runtime_data["coordinator"].async_request_selective_refresh = AsyncMock()
        
        with patch.object(service_manager, "_get_runtime_data_cached") as mock_get_data:
            mock_get_data.return_value = mock_runtime_data
            
            # Execute service
            await service_manager._handle_feed_dog_service(
                call, "test_dog", mock_runtime_data
            )
            
            # Should execute without errors
            mock_runtime_data["data_manager"].async_feed_dog.assert_called_once()

    def test_service_registry_completeness(self):
        """Test that service registry includes all expected services."""
        hass = Mock()
        service_manager = PawControlServiceManager(hass)
        
        expected_services = {
            SERVICE_FEED_DOG,
            SERVICE_START_WALK,
            SERVICE_END_WALK,
            SERVICE_LOG_HEALTH,
            SERVICE_LOG_MEDICATION,
            SERVICE_START_GROOMING,
            SERVICE_DAILY_RESET,
            SERVICE_NOTIFY_TEST,
            "recalculate_health_portions",
            "feed_health_aware",
            "update_health_data",
            "feed_with_medication",
        }
        
        registered_services = set(service_manager._service_registry.keys())
        
        # All expected services should be registered
        assert expected_services.issubset(registered_services)

    def test_service_schemas_completeness(self):
        """Test that all services have proper schemas."""
        hass = Mock()
        service_manager = PawControlServiceManager(hass)
        
        for service_name, (handler, schema, options) in service_manager._service_registry.items():
            # Each service should have a handler, schema, and options
            assert callable(handler)
            assert isinstance(schema, vol.Schema)
            assert isinstance(options, dict)
            assert "priority" in options
            assert "timeout" in options


class TestServiceErrorHandling:
    """Test comprehensive service error handling."""

    @pytest.fixture
    def service_manager(self, mock_hass):
        """Create service manager instance."""
        return PawControlServiceManager(mock_hass)

    @pytest.fixture
    def mock_hass(self):
        """Create mock Home Assistant instance."""
        hass = Mock(spec=HomeAssistant)
        hass.data = {DOMAIN: {}}
        hass.bus = Mock()
        return hass

    @pytest.mark.asyncio
    async def test_service_with_dog_not_found_error(self, service_manager):
        """Test service error when dog is not found."""
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "nonexistent_dog"}
        
        mock_runtime_data = None
        
        with patch.object(service_manager, "_get_runtime_data_cached") as mock_get_data:
            mock_get_data.return_value = mock_runtime_data
            
            with patch.object(service_manager, "_get_available_dog_ids") as mock_get_dogs:
                mock_get_dogs.return_value = ["dog1", "dog2"]
                
                with pytest.raises(ServiceValidationError):
                    await service_manager._handle_feed_dog_service(
                        call, "nonexistent_dog", mock_runtime_data
                    )

    @pytest.mark.asyncio
    async def test_service_with_data_manager_error(self, service_manager):
        """Test service error when data manager fails."""
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        mock_runtime_data = {
            "data_manager": Mock(),
            "coordinator": Mock(),
        }
        mock_runtime_data["data_manager"].async_feed_dog = AsyncMock(
            side_effect=Exception("Data manager error")
        )
        
        with pytest.raises(ServiceValidationError, match="Service failed"):
            await service_manager._handle_feed_dog_service(
                call, "test_dog", mock_runtime_data
            )

    @pytest.mark.asyncio
    async def test_service_with_missing_feeding_manager(self, service_manager):
        """Test health-aware service when feeding manager is missing."""
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        mock_runtime_data = {"coordinator": Mock()}  # No feeding_manager
        
        with pytest.raises(ServiceValidationError, match="Feeding manager not available"):
            await service_manager._handle_feed_health_aware(
                call, "test_dog", mock_runtime_data
            )

    @pytest.mark.asyncio
    async def test_service_cache_performance(self, service_manager):
        """Test service cache performance under load."""
        # Add many cache entries
        for i in range(100):
            dog_id = f"dog_{i}"
            service_manager._runtime_cache[dog_id] = (
                {"data": f"dog_{i}"},
                utcnow().timestamp(),
                5
            )
        
        # Cleanup should work efficiently
        now = utcnow().timestamp() + 1000  # Future time to expire all
        service_manager._cleanup_cache(now)
        
        # All entries should be cleaned up
        assert len(service_manager._runtime_cache) == 0

    def test_calorie_estimation_edge_cases(self):
        """Test calorie estimation with edge cases."""
        # Zero portion
        calories = PawControlServiceManager._estimate_calories(0.0, "dry_food")
        assert calories == 0.0
        
        # Very large portion
        calories = PawControlServiceManager._estimate_calories(10000.0, "dry_food")
        assert calories == 35000.0
        
        # Unknown food type defaults
        calories = PawControlServiceManager._estimate_calories(100.0, "exotic_food")
        assert calories == 200.0

    @pytest.mark.asyncio
    async def test_service_concurrent_access(self, service_manager):
        """Test service handling under concurrent access."""
        call = Mock()  # noqa: F811
        call.data = {ATTR_DOG_ID: "test_dog"}
        
        mock_runtime_data = {
            "data_manager": Mock(),
            "coordinator": Mock(),
        }
        mock_runtime_data["data_manager"].async_feed_dog = AsyncMock()
        mock_runtime_data["data_manager"].async_log_feeding = AsyncMock()
        mock_runtime_data["coordinator"].async_request_selective_refresh = AsyncMock()
        
        # Simulate concurrent calls
        tasks = []
        for _ in range(10):
            task = service_manager._handle_feed_dog_service(
                call, "test_dog", mock_runtime_data
            )
            tasks.append(task)
        
        # All should complete successfully
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # No exceptions should occur
        for result in results:
            assert not isinstance(result, Exception)


class TestServiceConstants:
    """Test service constants and configurations."""

    def test_calorie_table_completeness(self):
        """Test that calorie table includes all food types."""
        calorie_table = PawControlServiceManager._CALORIE_TABLE
        
        expected_food_types = [
            "dry_food",
            "wet_food", 
            "barf",
            "treat",
            "home_cooked",
        ]
        
        for food_type in expected_food_types:
            assert food_type in calorie_table
            assert isinstance(calorie_table[food_type], (int, float))
            assert calorie_table[food_type] > 0

    def test_service_timeouts_reasonable(self):
        """Test that service timeouts are reasonable."""
        hass = Mock()
        service_manager = PawControlServiceManager(hass)
        
        for service_name, (handler, schema, options) in service_manager._service_registry.items():
            timeout = options["timeout"]
            assert isinstance(timeout, (int, float))
            assert 0 < timeout <= 30  # Reasonable timeout range

    def test_service_priorities_valid(self):
        """Test that service priorities are valid."""
        hass = Mock()
        service_manager = PawControlServiceManager(hass)
        
        for service_name, (handler, schema, options) in service_manager._service_registry.items():
            priority = options["priority"]
            assert isinstance(priority, int)
            assert 1 <= priority <= 10  # Valid priority range
