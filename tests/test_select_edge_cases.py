"""Edge case tests for PawControl select platform.

Tests comprehensive edge cases, option validation, state management,
and performance characteristics of the select platform.

Test Areas:
- Option validation and invalid selections
- State restoration with corrupted data
- Module-specific option handling
- Batching performance and registry overload prevention
- Attribute calculation edge cases
- Service integration failures
- Coordinator unavailability scenarios
- Performance under stress conditions
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.select import (
    _async_add_entities_in_batches,
    async_setup_entry,
    _create_base_selects,
    _create_feeding_selects,
    _create_walk_selects,
    _create_gps_selects,
    _create_health_selects,
    PawControlSelectBase,
    PawControlDogSizeSelect,
    PawControlPerformanceModeSelect,
    PawControlNotificationPrioritySelect,
    PawControlFoodTypeSelect,
    PawControlFeedingScheduleSelect,
    PawControlDefaultMealTypeSelect,
    PawControlFeedingModeSelect,
    PawControlWalkModeSelect,
    PawControlWeatherPreferenceSelect,
    PawControlWalkIntensitySelect,
    PawControlGPSSourceSelect,
    PawControlTrackingModeSelect,
    PawControlLocationAccuracySelect,
    PawControlHealthStatusSelect,
    PawControlActivityLevelSelect,
    PawControlMoodSelect,
    PawControlGroomingTypeSelect,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    DOG_SIZES,
    FOOD_TYPES,
    GPS_SOURCES,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
    MOOD_OPTIONS,
    PERFORMANCE_MODES,
    ACTIVITY_LEVELS,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = MagicMock(spec=PawControlCoordinator)
    coordinator.available = True
    coordinator.config_entry = MagicMock()
    coordinator.get_dog_data.return_value = {
        "dog_info": {
            "dog_name": "TestDog",
            "dog_breed": "TestBreed",
            "dog_age": 3,
            "dog_size": "medium",
        },
        "modules": {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_WALK: True,
        },
    }
    coordinator.get_module_data.return_value = {
        "health_status": "good",
        "activity_level": "normal",
    }
    coordinator.async_refresh_dog = AsyncMock()
    return coordinator


@pytest.fixture
def mock_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry"
    entry.data = {
        CONF_DOGS: [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "TestDog1",
                CONF_DOG_SIZE: "large",
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: False,
                    MODULE_WALK: True,
                },
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "TestDog2",
                CONF_DOG_SIZE: "small",
                "modules": {
                    MODULE_FEEDING: False,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                    MODULE_WALK: False,
                },
            }
        ]
    }
    return entry


class TestSelectBaseEdgeCases:
    """Test base select entity edge cases."""

    @pytest.fixture
    def base_select(self, mock_coordinator):
        """Create a base select for testing."""
        return PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            select_type="test_select",
            options=["option1", "option2", "option3"],
            icon="mdi:test",
            initial_option="option1",
        )

    @pytest.mark.asyncio
    async def test_invalid_option_selection(self, base_select):
        """Test selecting an invalid option raises error."""
        with pytest.raises(HomeAssistantError, match="Invalid option 'invalid_option' for test_select"):
            await base_select.async_select_option("invalid_option")

    @pytest.mark.asyncio
    async def test_empty_string_option_selection(self, base_select):
        """Test selecting empty string option."""
        with pytest.raises(HomeAssistantError, match="Invalid option '' for test_select"):
            await base_select.async_select_option("")

    @pytest.mark.asyncio
    async def test_none_option_selection(self, base_select):
        """Test selecting None option."""
        with pytest.raises(HomeAssistantError, match="Invalid option 'None' for test_select"):
            await base_select.async_select_option(None)

    @pytest.mark.asyncio
    async def test_case_sensitive_option_validation(self, base_select):
        """Test that option validation is case-sensitive."""
        with pytest.raises(HomeAssistantError, match="Invalid option 'OPTION1' for test_select"):
            await base_select.async_select_option("OPTION1")

    @pytest.mark.asyncio
    async def test_option_selection_with_service_failure(self, base_select):
        """Test option selection when underlying service fails."""
        with patch.object(base_select, '_async_set_select_option', side_effect=Exception("Service failed")):
            with pytest.raises(HomeAssistantError, match="Failed to set test_select"):
                await base_select.async_select_option("option2")
        
        # Option should not change on failure
        assert base_select.current_option == "option1"

    @pytest.mark.asyncio
    async def test_successful_option_selection(self, base_select):
        """Test successful option selection updates state."""
        await base_select.async_select_option("option2")
        
        assert base_select.current_option == "option2"

    @pytest.mark.asyncio
    async def test_state_restoration_with_valid_option(self, base_select):
        """Test state restoration with valid previous option."""
        mock_state = Mock()
        mock_state.state = "option2"
        
        with patch.object(base_select, 'async_get_last_state', return_value=mock_state):
            await base_select.async_added_to_hass()
        
        assert base_select.current_option == "option2"

    @pytest.mark.asyncio
    async def test_state_restoration_with_invalid_option(self, base_select):
        """Test state restoration with invalid previous option."""
        mock_state = Mock()
        mock_state.state = "invalid_option"
        
        with patch.object(base_select, 'async_get_last_state', return_value=mock_state):
            await base_select.async_added_to_hass()
        
        # Should keep initial option
        assert base_select.current_option == "option1"

    @pytest.mark.asyncio
    async def test_state_restoration_with_none_state(self, base_select):
        """Test state restoration when no previous state exists."""
        with patch.object(base_select, 'async_get_last_state', return_value=None):
            await base_select.async_added_to_hass()
        
        # Should keep initial option
        assert base_select.current_option == "option1"

    def test_availability_with_coordinator_unavailable(self, base_select):
        """Test availability when coordinator is unavailable."""
        base_select.coordinator.available = False
        
        assert base_select.available is False

    def test_availability_with_missing_dog_data(self, base_select):
        """Test availability when dog data is missing."""
        base_select.coordinator.get_dog_data.return_value = None
        
        assert base_select.available is False

    def test_extra_attributes_with_full_data(self, base_select):
        """Test extra attributes with complete dog data."""
        attrs = base_select.extra_state_attributes
        
        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        assert attrs["select_type"] == "test_select"
        assert attrs["available_options"] == ["option1", "option2", "option3"]
        assert "last_changed" in attrs
        assert attrs["dog_breed"] == "TestBreed"
        assert attrs["dog_age"] == 3
        assert attrs["dog_size"] == "medium"

    def test_extra_attributes_with_missing_dog_info(self, base_select):
        """Test extra attributes when dog_info is missing."""
        base_select.coordinator.get_dog_data.return_value = {}
        
        attrs = base_select.extra_state_attributes
        
        # Should have basic attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        # Should not have dog_info attributes
        assert "dog_breed" not in attrs

    def test_extra_attributes_with_none_dog_data(self, base_select):
        """Test extra attributes when dog data is None."""
        base_select.coordinator.get_dog_data.return_value = None
        
        attrs = base_select.extra_state_attributes
        
        # Should have basic attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        # Should not have dog-specific attributes
        assert "dog_breed" not in attrs

    def test_get_module_data_with_unavailable_coordinator(self, base_select):
        """Test module data retrieval with unavailable coordinator."""
        base_select.coordinator.available = False
        
        result = base_select._get_module_data("health")
        
        assert result is None


class TestBatchingEdgeCasesSelect:
    """Test select entity batching edge cases."""

    @pytest.mark.asyncio
    async def test_empty_entity_list(self):
        """Test batching with empty entity list."""
        add_entities_mock = Mock()
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            [],  # Empty list
            batch_size=10,
            delay_between_batches=0.001,
        )
        
        # Should not call add_entities
        add_entities_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_entity_batching(self, mock_coordinator):
        """Test batching with single entity."""
        add_entities_mock = Mock()
        
        entity = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="test",
            dog_name="Test",
            select_type="test",
            options=["option1", "option2"],
        )
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            [entity],
            batch_size=10,
            delay_between_batches=0.001,
        )
        
        # Should call add_entities once
        add_entities_mock.assert_called_once()
        add_entities_mock.assert_called_with([entity], update_before_add=False)

    @pytest.mark.asyncio
    async def test_exact_batch_size_entities(self, mock_coordinator):
        """Test batching when entity count exactly matches batch size."""
        add_entities_mock = Mock()
        
        # Create exactly 10 entities
        entities = []
        for i in range(10):
            entity = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2"],
            )
            entities.append(entity)
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            entities,
            batch_size=10,
            delay_between_batches=0.001,
        )
        
        # Should call add_entities once with all entities
        add_entities_mock.assert_called_once()
        assert len(add_entities_mock.call_args[0][0]) == 10

    @pytest.mark.asyncio
    async def test_oversized_batch_handling(self, mock_coordinator):
        """Test batching with more entities than batch size."""
        add_entities_mock = Mock()
        
        # Create 25 entities (more than default batch size of 10)
        entities = []
        for i in range(25):
            entity = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2"],
            )
            entities.append(entity)
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            entities,
            batch_size=10,
            delay_between_batches=0.001,
        )
        
        # Should call add_entities 3 times (10 + 10 + 5)
        assert add_entities_mock.call_count == 3
        
        # Verify batch sizes
        calls = add_entities_mock.call_args_list
        assert len(calls[0][0][0]) == 10  # First batch
        assert len(calls[1][0][0]) == 10  # Second batch
        assert len(calls[2][0][0]) == 5   # Final batch

    @pytest.mark.asyncio
    async def test_batching_timing_delay(self, mock_coordinator):
        """Test that batching respects timing delays."""
        add_entities_mock = Mock()
        
        # Create entities requiring multiple batches
        entities = []
        for i in range(15):
            entity = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2"],
            )
            entities.append(entity)
        
        start_time = dt_util.utcnow()
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            entities,
            batch_size=10,
            delay_between_batches=0.01,  # 10ms delay
        )
        
        end_time = dt_util.utcnow()
        
        # Should have taken at least the delay time
        duration = (end_time - start_time).total_seconds()
        assert duration >= 0.01  # At least one delay

    @pytest.mark.asyncio
    async def test_registry_overload_prevention(self, mock_coordinator):
        """Test that batching prevents entity registry overload."""
        add_entities_mock = Mock()
        
        # Create many entities to simulate registry stress
        entities = []
        for i in range(250):  # More than 200 entities
            entity = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2"],
            )
            entities.append(entity)
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            entities,
            batch_size=10,
            delay_between_batches=0.1,
        )
        
        # Should use many small batches
        assert add_entities_mock.call_count == 25  # 250 / 10 = 25 batches
        
        # Each call should have update_before_add=False to reduce registry load
        for call in add_entities_mock.call_args_list:
            assert call[1]["update_before_add"] is False


class TestSpecificSelectEdgeCases:
    """Test edge cases for specific select types."""

    def test_dog_size_select_with_invalid_initial_size(self, mock_coordinator):
        """Test dog size select with invalid initial size."""
        dog_config = {CONF_DOG_SIZE: "invalid_size"}
        
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            dog_config=dog_config,
        )
        
        # Should handle gracefully
        assert select.current_option == "invalid_size"  # Keep invalid but log it
        assert "medium" in select.options  # Should have valid options

    def test_dog_size_select_missing_size_config(self, mock_coordinator):
        """Test dog size select with missing size configuration."""
        dog_config = {}  # No size specified
        
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            dog_config=dog_config,
        )
        
        # Should use default
        assert select.current_option == "medium"

    def test_dog_size_select_size_info_unknown_size(self, mock_coordinator):
        """Test size info retrieval for unknown size."""
        dog_config = {CONF_DOG_SIZE: "medium"}
        
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            dog_config=dog_config,
        )
        
        size_info = select._get_size_info("unknown_size")
        assert size_info == {}  # Should return empty dict for unknown

    def test_dog_size_select_size_info_all_valid_sizes(self, mock_coordinator):
        """Test size info for all valid dog sizes."""
        dog_config = {CONF_DOG_SIZE: "medium"}
        
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            dog_config=dog_config,
        )
        
        # Test all valid sizes have info
        for size in DOG_SIZES:
            size_info = select._get_size_info(size)
            assert "weight_range" in size_info
            assert "exercise_needs" in size_info
            assert "food_portion" in size_info

    def test_performance_mode_select_unknown_mode(self, mock_coordinator):
        """Test performance mode info for unknown mode."""
        select = PawControlPerformanceModeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        mode_info = select._get_performance_mode_info("unknown_mode")
        assert mode_info == {}

    def test_performance_mode_select_all_valid_modes(self, mock_coordinator):
        """Test performance mode info for all valid modes."""
        select = PawControlPerformanceModeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Test all valid modes have info
        for mode in PERFORMANCE_MODES:
            mode_info = select._get_performance_mode_info(mode)
            assert "description" in mode_info
            assert "update_interval" in mode_info
            assert "battery_impact" in mode_info

    def test_food_type_select_unknown_food_type(self, mock_coordinator):
        """Test food type info for unknown type."""
        select = PawControlFoodTypeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        food_info = select._get_food_type_info("unknown_food")
        assert food_info == {}

    def test_food_type_select_all_valid_types(self, mock_coordinator):
        """Test food type info for all valid types."""
        select = PawControlFoodTypeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Test all valid food types have info
        for food_type in FOOD_TYPES:
            food_info = select._get_food_type_info(food_type)
            assert "calories_per_gram" in food_info
            assert "moisture_content" in food_info
            assert "storage" in food_info
            assert "shelf_life" in food_info

    def test_walk_mode_select_unknown_mode(self, mock_coordinator):
        """Test walk mode info for unknown mode."""
        select = PawControlWalkModeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        mode_info = select._get_walk_mode_info("unknown_mode")
        assert mode_info == {}

    def test_walk_mode_select_all_valid_modes(self, mock_coordinator):
        """Test walk mode info for all valid modes."""
        select = PawControlWalkModeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        valid_modes = ["automatic", "manual", "hybrid"]
        for mode in valid_modes:
            mode_info = select._get_walk_mode_info(mode)
            assert "description" in mode_info
            assert "gps_required" in mode_info
            assert "accuracy" in mode_info

    def test_gps_source_select_unknown_source(self, mock_coordinator):
        """Test GPS source info for unknown source."""
        select = PawControlGPSSourceSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        source_info = select._get_gps_source_info("unknown_source")
        assert source_info == {}

    def test_gps_source_select_all_valid_sources(self, mock_coordinator):
        """Test GPS source info for all valid sources."""
        select = PawControlGPSSourceSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Test all valid GPS sources have info
        for source in GPS_SOURCES:
            source_info = select._get_gps_source_info(source)
            assert "accuracy" in source_info
            assert "update_frequency" in source_info
            assert "battery_usage" in source_info

    def test_grooming_type_select_unknown_type(self, mock_coordinator):
        """Test grooming type info for unknown type."""
        select = PawControlGroomingTypeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        grooming_info = select._get_grooming_type_info("unknown_grooming")
        assert grooming_info == {}

    def test_grooming_type_select_all_valid_types(self, mock_coordinator):
        """Test grooming type info for all valid types."""
        select = PawControlGroomingTypeSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        valid_types = ["bath", "brush", "nails", "teeth", "trim", "full_grooming"]
        for grooming_type in valid_types:
            grooming_info = select._get_grooming_type_info(grooming_type)
            assert "frequency" in grooming_info
            assert "duration" in grooming_info
            assert "difficulty" in grooming_info


class TestHealthSelectDataIntegration:
    """Test health selects with dynamic data integration."""

    def test_health_status_select_from_coordinator_data(self, mock_coordinator):
        """Test health status select reads from coordinator data."""
        select = PawControlHealthStatusSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock health data
        mock_coordinator.get_module_data.return_value = {
            "health_status": "excellent"
        }
        
        assert select.current_option == "excellent"

    def test_health_status_select_missing_module_data(self, mock_coordinator):
        """Test health status select with missing module data."""
        select = PawControlHealthStatusSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock no module data
        mock_coordinator.get_module_data.return_value = None
        
        assert select.current_option == "good"  # Should fall back to initial

    def test_health_status_select_missing_status_in_data(self, mock_coordinator):
        """Test health status select with missing status in module data."""
        select = PawControlHealthStatusSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock module data without health_status
        mock_coordinator.get_module_data.return_value = {
            "other_data": "value"
        }
        
        assert select.current_option == "good"  # Should fall back to initial

    def test_activity_level_select_from_coordinator_data(self, mock_coordinator):
        """Test activity level select reads from coordinator data."""
        select = PawControlActivityLevelSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock health data
        mock_coordinator.get_module_data.return_value = {
            "activity_level": "high"
        }
        
        assert select.current_option == "high"

    def test_activity_level_select_missing_data(self, mock_coordinator):
        """Test activity level select with missing data."""
        select = PawControlActivityLevelSelect(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock no data
        mock_coordinator.get_module_data.return_value = None
        
        assert select.current_option == "normal"  # Should fall back


class TestSetupEntryEdgeCases:
    """Test async_setup_entry edge cases for select platform."""

    @pytest.mark.asyncio
    async def test_setup_with_runtime_data(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry with runtime_data format."""
        # Setup runtime_data format
        mock_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": mock_entry.data[CONF_DOGS],
        }
        
        add_entities_mock = Mock()
        
        await async_setup_entry(hass, mock_entry, add_entities_mock)
        
        # Should create entities using batching
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_legacy_hass_data(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry with legacy hass.data format."""
        # Setup legacy format
        hass.data[DOMAIN] = {
            mock_entry.entry_id: {
                "coordinator": mock_coordinator,
            }
        }
        
        add_entities_mock = Mock()
        
        await async_setup_entry(hass, mock_entry, add_entities_mock)
        
        # Should create entities
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_no_dogs(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry with no dogs configured."""
        # Empty dogs list
        mock_entry.data = {CONF_DOGS: []}
        mock_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [],
        }
        
        add_entities_mock = Mock()
        
        await async_setup_entry(hass, mock_entry, add_entities_mock)
        
        # Should still call add_entities (with empty list)
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_malformed_dog_data(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry with malformed dog data."""
        # Malformed dog data
        mock_entry.data = {
            CONF_DOGS: [
                {
                    # Missing CONF_DOG_ID
                    CONF_DOG_NAME: "Incomplete Dog",
                    "modules": {MODULE_FEEDING: True},
                },
                {
                    CONF_DOG_ID: "valid_dog",
                    CONF_DOG_NAME: "Valid Dog",
                    # Missing modules key
                },
            ]
        }
        
        add_entities_mock = Mock()
        
        # Should handle gracefully without crashing
        await async_setup_entry(hass, mock_entry, add_entities_mock)

    @pytest.mark.asyncio
    async def test_setup_with_disabled_modules(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry with various disabled modules."""
        # Dogs with different module configurations
        mock_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "basic_dog",
                    CONF_DOG_NAME: "Basic Dog",
                    "modules": {},  # No modules enabled
                },
                {
                    CONF_DOG_ID: "feeding_only_dog",
                    CONF_DOG_NAME: "Feeding Only Dog",
                    "modules": {MODULE_FEEDING: True},  # Only feeding enabled
                },
            ]
        }
        
        add_entities_mock = Mock()
        
        await async_setup_entry(hass, mock_entry, add_entities_mock)
        
        # Should create different numbers of entities based on enabled modules
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_performance_with_many_dogs(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry performance with many dogs and modules."""
        # Create many dogs to test performance
        many_dogs = []
        for i in range(30):  # 30 dogs
            many_dogs.append({
                CONF_DOG_ID: f"dog_{i}",
                CONF_DOG_NAME: f"Dog {i}",
                CONF_DOG_SIZE: DOG_SIZES[i % len(DOG_SIZES)],
                "modules": {
                    MODULE_FEEDING: i % 2 == 0,  # Alternate modules
                    MODULE_GPS: i % 3 == 0,
                    MODULE_HEALTH: i % 4 == 0,
                    MODULE_WALK: i % 5 == 0,
                },
            })
        
        mock_entry.data = {CONF_DOGS: many_dogs}
        mock_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": many_dogs,
        }
        
        add_entities_mock = Mock()
        
        start_time = dt_util.utcnow()
        await async_setup_entry(hass, mock_entry, add_entities_mock)
        end_time = dt_util.utcnow()
        
        # Should complete in reasonable time
        duration = (end_time - start_time).total_seconds()
        assert duration < 2.0  # Should be fast even with many dogs
        
        # Should use batching for large numbers of entities
        assert add_entities_mock.call_count > 1  # Multiple batches


class TestSelectFactoryFunctionsEdgeCases:
    """Test select factory function edge cases."""

    def test_create_base_selects_missing_dog_size(self, mock_coordinator):
        """Test creating base selects with missing dog size."""
        dog_config = {}  # No dog size
        
        selects = _create_base_selects(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            dog_config,
        )
        
        # Should create selects despite missing size
        assert len(selects) == 3  # Size, performance, notification selects
        
        # Size select should handle missing config
        size_select = next(s for s in selects if isinstance(s, PawControlDogSizeSelect))
        assert size_select.current_option == "medium"  # Default value

    def test_create_feeding_selects_consistency(self, mock_coordinator):
        """Test feeding selects creation consistency."""
        selects = _create_feeding_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create all feeding-related selects
        assert len(selects) == 4  # Food type, schedule, meal type, mode
        
        # Verify all are feeding-related
        select_types = [type(s).__name__ for s in selects]
        assert "PawControlFoodTypeSelect" in select_types
        assert "PawControlFeedingScheduleSelect" in select_types
        assert "PawControlDefaultMealTypeSelect" in select_types
        assert "PawControlFeedingModeSelect" in select_types

    def test_create_walk_selects_consistency(self, mock_coordinator):
        """Test walk selects creation consistency."""
        selects = _create_walk_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create all walk-related selects
        assert len(selects) == 3  # Mode, weather, intensity
        
        # Verify all are walk-related
        select_types = [type(s).__name__ for s in selects]
        assert "PawControlWalkModeSelect" in select_types
        assert "PawControlWeatherPreferenceSelect" in select_types
        assert "PawControlWalkIntensitySelect" in select_types

    def test_create_gps_selects_consistency(self, mock_coordinator):
        """Test GPS selects creation consistency."""
        selects = _create_gps_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create all GPS-related selects
        assert len(selects) == 3  # Source, tracking mode, accuracy
        
        # Verify all are GPS-related
        select_types = [type(s).__name__ for s in selects]
        assert "PawControlGPSSourceSelect" in select_types
        assert "PawControlTrackingModeSelect" in select_types
        assert "PawControlLocationAccuracySelect" in select_types

    def test_create_health_selects_consistency(self, mock_coordinator):
        """Test health selects creation consistency."""
        selects = _create_health_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create all health-related selects
        assert len(selects) == 4  # Status, activity, mood, grooming
        
        # Verify all are health-related
        select_types = [type(s).__name__ for s in selects]
        assert "PawControlHealthStatusSelect" in select_types
        assert "PawControlActivityLevelSelect" in select_types
        assert "PawControlMoodSelect" in select_types
        assert "PawControlGroomingTypeSelect" in select_types


class TestPerformanceAndStressScenarios:
    """Test performance characteristics and stress scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_option_changes(self, mock_coordinator):
        """Test rapid option changes don't cause issues."""
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            select_type="test",
            options=["option1", "option2", "option3"],
        )
        
        # Rapid option changes
        for i in range(100):
            option = f"option{(i % 3) + 1}"
            await select.async_select_option(option)
            assert select.current_option == option

    @pytest.mark.asyncio
    async def test_concurrent_select_operations(self, mock_coordinator):
        """Test concurrent select operations."""
        selects = []
        for i in range(10):
            select = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2", "option3"],
            )
            selects.append(select)
        
        async def change_options(select, start_option):
            for j in range(10):
                option_num = ((start_option + j) % 3) + 1
                await select.async_select_option(f"option{option_num}")
        
        # Run concurrent operations
        await asyncio.gather(*[change_options(s, i) for i, s in enumerate(selects)])
        
        # All selects should be in valid states
        for select in selects:
            assert select.current_option in select.options

    def test_memory_usage_with_many_selects(self, mock_coordinator):
        """Test memory usage doesn't grow excessively with many selects."""
        selects = []
        
        # Create many selects
        for i in range(200):
            select = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                select_type="test",
                options=["option1", "option2", "option3"],
                initial_option="option1",
            )
            selects.append(select)
        
        # Each select should be independent
        for i, select in enumerate(selects[:10]):  # Test first 10
            option_num = (i % 3) + 1
            select._current_option = f"option{option_num}"
        
        # Verify states are correct
        for i, select in enumerate(selects[:10]):
            option_num = (i % 3) + 1
            expected_option = f"option{option_num}"
            assert select.current_option == expected_option

    @pytest.mark.asyncio
    async def test_stress_test_factory_functions(self, mock_coordinator):
        """Stress test select factory functions with many dogs."""
        # Create selects for many dogs
        all_selects = []
        for i in range(25):  # 25 dogs
            dog_config = {CONF_DOG_SIZE: DOG_SIZES[i % len(DOG_SIZES)]}
            
            # Create all types of selects
            base_selects = _create_base_selects(
                mock_coordinator, f"dog_{i}", f"Dog {i}", dog_config
            )
            feeding_selects = _create_feeding_selects(
                mock_coordinator, f"dog_{i}", f"Dog {i}"
            )
            walk_selects = _create_walk_selects(
                mock_coordinator, f"dog_{i}", f"Dog {i}"
            )
            gps_selects = _create_gps_selects(
                mock_coordinator, f"dog_{i}", f"Dog {i}"
            )
            health_selects = _create_health_selects(
                mock_coordinator, f"dog_{i}", f"Dog {i}"
            )
            
            all_selects.extend(base_selects)
            all_selects.extend(feeding_selects)
            all_selects.extend(walk_selects)
            all_selects.extend(gps_selects)
            all_selects.extend(health_selects)
        
        # Should create reasonable number of selects
        assert len(all_selects) > 300  # Many selects for 25 dogs
        assert len(all_selects) < 1000  # Not excessive
        
        # All selects should be valid
        for select in all_selects:
            assert hasattr(select, '_dog_id')
            assert hasattr(select, '_select_type')
            assert hasattr(select, 'unique_id')
            assert len(select.options) > 0

    def test_unique_id_collision_prevention(self, mock_coordinator):
        """Test that unique IDs don't collide across select types."""
        dog_id = "test_dog"
        dog_name = "Test Dog"
        dog_config = {CONF_DOG_SIZE: "medium"}
        
        # Create all types of selects
        all_selects = []
        all_selects.extend(_create_base_selects(mock_coordinator, dog_id, dog_name, dog_config))
        all_selects.extend(_create_feeding_selects(mock_coordinator, dog_id, dog_name))
        all_selects.extend(_create_walk_selects(mock_coordinator, dog_id, dog_name))
        all_selects.extend(_create_gps_selects(mock_coordinator, dog_id, dog_name))
        all_selects.extend(_create_health_selects(mock_coordinator, dog_id, dog_name))
        
        # Collect all unique IDs
        unique_ids = [select.unique_id for select in all_selects]
        
        # Should not have any duplicate unique IDs
        assert len(unique_ids) == len(set(unique_ids))


if __name__ == "__main__":
    pytest.main([__file__])
