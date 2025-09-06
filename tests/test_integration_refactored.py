"""Integration test for refactored coordinator with specialized managers.

Validates that entities can properly access data through the refactored coordinator
with manager delegation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.sensor import (
    PawControlDietValidationStatusSensor,
    PawControlHealthAwarePortionSensor,
    PawControlLastFeedingSensor,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestRefactoredCoordinatorIntegration:
    """Integration tests for refactored coordinator with entity creation."""

    @pytest.fixture
    def mock_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "integration_test_dog",
                    CONF_DOG_NAME: "Integration Test Dog",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_GPS: True,
                    },
                }
            ]
        }
        entry.options = {}
        return entry

    @pytest.fixture
    def coordinator_with_managers(self, hass: HomeAssistant, mock_entry):
        """Create coordinator with properly mocked managers."""
        coordinator = PawControlCoordinator(hass, mock_entry)
        
        # Create mock managers with realistic responses
        mock_feeding_manager = AsyncMock()
        mock_feeding_manager.async_get_feeding_data.return_value = {
            "last_feeding": "2025-01-15T10:00:00",
            "last_feeding_hours": 2.5,
            "meals_today": 2,
            "total_feedings_today": 2,
            "daily_amount_consumed": 300.0,
            "daily_amount_target": 500.0,
            "schedule_adherence": 95.0,
            "feedings_today": {
                "breakfast": 1,
                "lunch": 0,
                "dinner": 1,
                "snack": 0
            },
            "next_feeding": "2025-01-15T18:00:00",
            "next_feeding_type": "dinner",
            "config": {
                "meals_per_day": 2,
                "food_type": "dry_food",
                "schedule_type": "flexible"
            },
            # Health-aware feeding data
            "health_aware_portion": 250.0,
            "daily_calorie_requirement": 800.0,
            "portion_adjustment_factor": 1.1,
            "breakfast_portion": 275.0,
            "dinner_portion": 225.0,
            # Diet validation data
            "diet_validation_summary": {
                "has_adjustments": True,
                "adjustment_info": "Adjusted for weight management",
                "conflict_count": 0,
                "warning_count": 1,
                "vet_consultation_recommended": False
            },
            "special_diet_info": {
                "has_special_diet": True,
                "requirements": ["weight_control", "senior_formula"],
                "priority_level": "normal",
                "total_requirements": 2
            }
        }
        
        mock_walk_manager = AsyncMock()
        mock_walk_manager.async_get_walk_data.return_value = {
            "walk_in_progress": False,
            "current_walk": None,
            "walks_today": 2,
            "total_duration_today": 45,
            "daily_distance": 1500.0,
            "last_walk": "2025-01-15T08:00:00",
            "last_walk_hours": 4.0,
            "last_walk_duration": 25,
            "weekly_walks": 8,
            "average_duration": 22.5
        }
        mock_walk_manager.async_get_gps_data.return_value = {
            "latitude": 52.5200,
            "longitude": 13.4050,
            "accuracy": 5.0,
            "available": True,
            "zone": "home",
            "distance_from_home": 0.0,
            "current_speed": 0.0,
            "last_seen": "2025-01-15T12:00:00",
            "source": "device_tracker"
        }
        
        mock_dog_data_manager = AsyncMock()
        mock_dog_data_manager.async_get_dog_data.return_value = {
            "health": {
                "current_weight": 25.5,
                "ideal_weight": 24.0,
                "weight_goal": "lose",
                "health_status": "good",
                "body_condition_score": 6,
                "life_stage": "adult",
                "activity_level": "moderate",
                "age_months": 48,
                "last_vet_visit": "2024-12-01T10:00:00",
                "days_since_grooming": 14,
                "medication_due": "no"
            }
        }
        
        mock_data_manager = AsyncMock()
        mock_health_calculator = Mock()
        
        # Inject managers
        coordinator.set_managers(
            data_manager=mock_data_manager,
            dog_data_manager=mock_dog_data_manager,
            walk_manager=mock_walk_manager,
            feeding_manager=mock_feeding_manager,
            health_calculator=mock_health_calculator
        )
        
        return coordinator

    @pytest.mark.asyncio
    async def test_coordinator_data_structure_compatibility(self, coordinator_with_managers):
        """Test that refactored coordinator returns expected data structure."""
        coordinator = coordinator_with_managers
        
        # Trigger data update to populate coordinator._data
        await coordinator._async_update_data()
        
        # Get dog data through public interface
        dog_data = coordinator.get_dog_data("integration_test_dog")
        
        # Verify expected data structure
        assert dog_data is not None
        assert "dog_info" in dog_data
        assert dog_data["dog_info"][CONF_DOG_ID] == "integration_test_dog"
        
        # Verify module data is present
        assert MODULE_FEEDING in dog_data
        assert MODULE_WALK in dog_data
        assert MODULE_GPS in dog_data
        assert MODULE_HEALTH in dog_data
        
        # Verify feeding data structure
        feeding_data = dog_data[MODULE_FEEDING]
        assert "last_feeding" in feeding_data
        assert "meals_today" in feeding_data
        assert "health_aware_portion" in feeding_data
        assert "diet_validation_summary" in feeding_data
        
        # Verify health data structure
        health_data = dog_data[MODULE_HEALTH]
        assert "current_weight" in health_data
        assert "health_status" in health_data

    @pytest.mark.asyncio
    async def test_sensor_integration_with_refactored_coordinator(self, hass, coordinator_with_managers):
        """Test that sensors work with refactored coordinator."""
        coordinator = coordinator_with_managers
        
        # Populate coordinator data
        await coordinator._async_update_data()
        
        # Create sensor instances
        last_feeding_sensor = PawControlLastFeedingSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        diet_validation_sensor = PawControlDietValidationStatusSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        health_aware_portion_sensor = PawControlHealthAwarePortionSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        # Test sensor values
        assert last_feeding_sensor.available is True
        
        # Test last feeding sensor
        last_feeding_value = last_feeding_sensor.native_value
        assert last_feeding_value is not None
        assert isinstance(last_feeding_value, datetime)
        
        # Test diet validation sensor
        diet_status = diet_validation_sensor.native_value
        assert diet_status in ["no_data", "no_validation", "conflicts_detected", "warnings_present", "validated_safe"]
        
        # Test health-aware portion sensor
        portion_value = health_aware_portion_sensor.native_value
        assert portion_value is not None
        assert isinstance(portion_value, float)
        assert portion_value > 0

    @pytest.mark.asyncio
    async def test_sensor_attributes_with_refactored_coordinator(self, hass, coordinator_with_managers):
        """Test that sensor attributes work with refactored coordinator."""
        coordinator = coordinator_with_managers
        
        # Populate coordinator data
        await coordinator._async_update_data()
        
        # Create diet validation sensor
        diet_sensor = PawControlDietValidationStatusSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        # Test extra state attributes
        attributes = diet_sensor.extra_state_attributes
        
        # Verify base attributes are present
        assert CONF_DOG_ID in attributes
        assert CONF_DOG_NAME in attributes
        assert attributes[CONF_DOG_ID] == "integration_test_dog"
        
        # Verify diet-specific attributes
        assert "has_special_diet" in attributes
        assert "special_diets" in attributes
        assert "validation_applied" in attributes

    @pytest.mark.asyncio
    async def test_manager_timeout_handling_in_integration(self, hass, coordinator_with_managers):
        """Test that sensor integration handles manager timeouts gracefully."""
        coordinator = coordinator_with_managers
        
        # Make feeding manager timeout
        async def timeout_response(*args, **kwargs):
            import asyncio
            await asyncio.sleep(10)  # Longer than expected timeout
            return {"should_not_reach": True}
        
        coordinator.feeding_manager.async_get_feeding_data = timeout_response
        
        # This should handle timeout gracefully and not crash
        await coordinator._async_update_data()
        
        # Create sensor
        sensor = PawControlLastFeedingSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        # Sensor should handle missing/incomplete data gracefully
        # This should not raise an exception
        sensor_value = sensor.native_value
        
        # Value might be None due to timeout, but should not crash
        assert sensor_value is None or isinstance(sensor_value, datetime)

    @pytest.mark.asyncio
    async def test_cache_manager_integration_with_sensors(self, hass, coordinator_with_managers):
        """Test that cache manager works properly with sensor data access."""
        coordinator = coordinator_with_managers
        
        # First update should populate cache
        await coordinator._async_update_data()
        
        # Check cache was populated
        cache_stats = coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] > 0
        
        # Create sensor and access data (should use cached data)
        sensor = PawControlHealthAwarePortionSensor(
            coordinator, "integration_test_dog", "Integration Test Dog"
        )
        
        first_value = sensor.native_value
        
        # Second access should be faster due to caching
        second_value = sensor.native_value
        
        # Values should be consistent
        assert first_value == second_value
        
        # Cache hit rate should improve
        updated_cache_stats = coordinator._cache_manager.get_stats()
        assert updated_cache_stats["cache_hits"] >= cache_stats["cache_hits"]

    @pytest.mark.asyncio
    async def test_performance_monitoring_with_sensor_updates(self, hass, coordinator_with_managers):
        """Test that performance monitoring works with sensor data updates."""
        coordinator = coordinator_with_managers
        
        # Perform several updates to generate performance data
        for _ in range(5):
            await coordinator._async_update_data()
        
        # Check performance stats
        perf_stats = coordinator._performance_monitor.get_stats()
        
        assert perf_stats["total_updates"] >= 5
        assert "average_update_time" in perf_stats
        assert "p95" in perf_stats
        
        # Performance should be reasonable
        assert perf_stats["average_update_time"] < 5.0  # Less than 5 seconds

    @pytest.mark.asyncio
    async def test_batch_manager_integration_with_selective_refresh(self, hass, coordinator_with_managers):
        """Test batch manager integration with selective refresh requests."""
        coordinator = coordinator_with_managers
        
        # Request selective refresh
        await coordinator.async_request_selective_refresh(
            ["integration_test_dog"], priority=8
        )
        
        # Check batch manager state
        batch_stats = coordinator._batch_manager.get_stats()
        
        # Should have processed high-priority request
        assert "max_batch_size" in batch_stats
        
        # Cache should be invalidated for the dog
        cached_data = await coordinator._cache_manager.get("dog_integration_test_dog")
        assert cached_data is None  # Should be invalidated

    @pytest.mark.asyncio
    async def test_complete_sensor_platform_compatibility(self, hass, coordinator_with_managers):
        """Test complete sensor platform works with refactored coordinator."""
        coordinator = coordinator_with_managers
        
        # Populate data
        await coordinator._async_update_data()
        
        # Test multiple sensor types to ensure broad compatibility
        sensors = [
            PawControlLastFeedingSensor(coordinator, "integration_test_dog", "Test Dog"),
            PawControlDietValidationStatusSensor(coordinator, "integration_test_dog", "Test Dog"),
            PawControlHealthAwarePortionSensor(coordinator, "integration_test_dog", "Test Dog"),
        ]
        
        # All sensors should be available
        for sensor in sensors:
            assert sensor.available is True
            
            # All should have valid state
            state = sensor.native_value
            assert state is not None
            
            # All should have attributes
            attributes = sensor.extra_state_attributes
            assert isinstance(attributes, dict)
            assert len(attributes) > 0
            
            # Base attributes should be present
            assert CONF_DOG_ID in attributes
            assert CONF_DOG_NAME in attributes

    @pytest.mark.asyncio
    async def test_error_recovery_in_integration(self, hass, coordinator_with_managers):
        """Test error recovery in integration scenarios."""
        coordinator = coordinator_with_managers
        
        # Make one manager fail
        coordinator.feeding_manager.async_get_feeding_data.side_effect = Exception("Manager error")
        
        # Update should handle error gracefully
        await coordinator._async_update_data()
        
        # Sensor should handle missing feeding data
        PawControlLastFeedingSensor(
            coordinator, "integration_test_dog", "Test Dog"
        )
        
        # Should not crash, might return None
        # Value might be None due to error, but should not raise exception
        
        # Other modules should still work
        dog_data = coordinator.get_dog_data("integration_test_dog")
        assert dog_data is not None
        assert MODULE_WALK in dog_data  # Other managers should still work

    def test_coordinator_public_interface_unchanged(self, hass, coordinator_with_managers):
        """Test that public coordinator interface remains unchanged after refactoring."""
        coordinator = coordinator_with_managers
        
        # Test all public methods still exist and work
        assert hasattr(coordinator, "get_dog_config")
        assert hasattr(coordinator, "get_enabled_modules")
        assert hasattr(coordinator, "is_module_enabled")
        assert hasattr(coordinator, "get_dog_ids")
        assert hasattr(coordinator, "get_dog_data")
        assert hasattr(coordinator, "get_all_dogs_data")
        assert hasattr(coordinator, "available")
        
        # Test methods return expected types
        config = coordinator.get_dog_config("integration_test_dog")
        assert isinstance(config, dict)
        
        modules = coordinator.get_enabled_modules("integration_test_dog")
        assert isinstance(modules, set)
        
        is_enabled = coordinator.is_module_enabled("integration_test_dog", MODULE_FEEDING)
        assert isinstance(is_enabled, bool)
        
        dog_ids = coordinator.get_dog_ids()
        assert isinstance(dog_ids, list)
        
        all_data = coordinator.get_all_dogs_data()
        assert isinstance(all_data, dict)
        
        available = coordinator.available
        assert isinstance(available, bool)

    @pytest.mark.asyncio
    async def test_memory_efficiency_with_managers(self, hass, coordinator_with_managers):
        """Test that refactored coordinator is memory efficient."""
        coordinator = coordinator_with_managers
        
        # Perform multiple updates
        for _ in range(10):
            await coordinator._async_update_data()
        
        # Check cache size remains reasonable
        cache_stats = coordinator._cache_manager.get_stats()
        assert cache_stats["total_entries"] <= cache_stats["max_size"]
        
        # Check performance data doesn't grow unbounded
        perf_stats = coordinator._performance_monitor.get_stats()
        assert perf_stats["total_updates"] == 10
        
        # Batch manager should not accumulate pending items
        batch_stats = coordinator._batch_manager.get_stats()
        assert batch_stats["pending_updates"] == 0  # Should be processed
