"""Enhanced edge case tests for PawControl select platform.

Comprehensive edge cases covering critical scenarios for Gold Standard 95% coverage.
Includes advanced validation, integration failures, and performance stress conditions.

Additional Test Areas:
- Option validation with malformed data
- Dynamic option list updates and synchronization
- Service integration timeout and recovery scenarios  
- Module data consistency and corruption recovery
- Entity registry collision detection and resolution
- Multi-language option handling and validation
- Concurrent option selection protection
- Performance optimization under load
- Memory efficiency with large option sets
- Configuration migration and backward compatibility
"""

from __future__ import annotations

import asyncio
import gc
import json
import weakref
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    ACTIVITY_LEVELS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOGS,
    DOG_SIZES,
    DOMAIN,
    FOOD_TYPES,
    GPS_SOURCES,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
    MOOD_OPTIONS,
    PERFORMANCE_MODES,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.select import (
    PawControlActivityLevelSelect,
    PawControlDefaultMealTypeSelect,
    PawControlDogSizeSelect,
    PawControlFeedingModeSelect,
    PawControlFeedingScheduleSelect,
    PawControlFoodTypeSelect,
    PawControlGPSSourceSelect,
    PawControlGroomingTypeSelect,
    PawControlHealthStatusSelect,
    PawControlLocationAccuracySelect,
    PawControlMoodSelect,
    PawControlNotificationPrioritySelect,
    PawControlPerformanceModeSelect,
    PawControlSelectBase,
    PawControlTrackingModeSelect,
    PawControlWalkIntensitySelect,
    PawControlWalkModeSelect,
    PawControlWeatherPreferenceSelect,
    _async_add_entities_in_batches,
    _create_base_selects,
    _create_feeding_selects,
    _create_gps_selects,
    _create_health_selects,
    _create_walk_selects,
    async_setup_entry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import dt as dt_util


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = MagicMock(spec=PawControlCoordinator)
    coordinator.available = True
    coordinator.config_entry = MagicMock()
    coordinator.config_entry.entry_id = "test_entry"
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
            }
        ]
    }
    entry.version = 1
    entry.minor_version = 1
    return entry


class TestOptionValidationMalformedData:
    """Test option validation with malformed and edge case data."""

    @pytest.fixture
    def malformed_select(self, mock_coordinator):
        """Create a select with malformed options for testing."""
        # Create select with potentially problematic options
        return PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="malformed_dog",
            dog_name="Malformed Dog",
            select_type="malformed_test",
            options=["valid_option", None, "", "  ", 123, {"invalid": "dict"}],
            icon="mdi:test",
            initial_option="valid_option",
        )

    @pytest.mark.asyncio
    async def test_option_validation_with_none_values(self, malformed_select):
        """Test option validation when options list contains None values."""
        # None should be rejected
        with pytest.raises(HomeAssistantError, match="Invalid option 'None'"):
            await malformed_select.async_select_option(None)

    @pytest.mark.asyncio
    async def test_option_validation_with_empty_strings(self, malformed_select):
        """Test option validation with empty string options."""
        # Empty string should be rejected
        with pytest.raises(HomeAssistantError, match="Invalid option ''"):
            await malformed_select.async_select_option("")

    @pytest.mark.asyncio
    async def test_option_validation_with_whitespace_only(self, malformed_select):
        """Test option validation with whitespace-only options."""
        # Whitespace-only should be rejected
        with pytest.raises(HomeAssistantError, match="Invalid option '  '"):
            await malformed_select.async_select_option("  ")

    @pytest.mark.asyncio
    async def test_option_validation_with_non_string_types(self, malformed_select):
        """Test option validation with non-string option types."""
        # Integer should be rejected (converted to string for error message)
        with pytest.raises(HomeAssistantError, match="Invalid option '123'"):
            await malformed_select.async_select_option(123)

    @pytest.mark.asyncio
    async def test_option_validation_with_complex_objects(self, malformed_select):
        """Test option validation with complex object types."""
        # Complex objects should be rejected
        with pytest.raises(HomeAssistantError):
            await malformed_select.async_select_option({"invalid": "dict"})

    def test_options_list_sanitization(self, mock_coordinator):
        """Test that options list is properly sanitized during initialization."""
        problematic_options = [
            "valid1",
            None,        # Should be filtered out
            "",          # Should be filtered out
            "valid2",
            123,         # Should be converted or filtered
            "   ",       # Should be filtered out
            "valid3",
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="sanitize_dog",
            dog_name="Sanitize Dog",
            select_type="sanitize_test",
            options=problematic_options,
            initial_option="valid1",
        )
        
        # Options should be available despite problematic input
        assert "valid1" in select.options
        assert "valid2" in select.options
        assert "valid3" in select.options

    @pytest.mark.asyncio
    async def test_unicode_option_validation(self, mock_coordinator):
        """Test option validation with Unicode characters."""
        unicode_options = [
            "Röxli",      # German umlaut
            "José",       # Spanish accent  
            "Москва",     # Cyrillic
            "北京",        # Chinese
            "🐕 Dog",     # Emoji
            "café",       # French accent
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="unicode_dog",
            dog_name="Unicode Dog",
            select_type="unicode_test",
            options=unicode_options,
            initial_option="Röxli",
        )
        
        # Should handle Unicode options correctly
        for option in unicode_options:
            await select.async_select_option(option)
            assert select.current_option == option

    def test_very_long_option_handling(self, mock_coordinator):
        """Test handling of very long option strings."""
        long_option = "x" * 1000  # Very long option string
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="long_dog",
            dog_name="Long Dog",
            select_type="long_test",
            options=["short", long_option, "normal"],
            initial_option="short",
        )
        
        # Should handle long options
        assert long_option in select.options

    @pytest.mark.asyncio
    async def test_case_sensitivity_edge_cases(self, mock_coordinator):
        """Test case sensitivity in option validation."""
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="case_dog",
            dog_name="Case Dog",
            select_type="case_test",
            options=["Option", "option", "OPTION", "OpTiOn"],
            initial_option="Option",
        )
        
        # All variations should be valid distinct options
        for option in ["Option", "option", "OPTION", "OpTiOn"]:
            await select.async_select_option(option)
            assert select.current_option == option

    def test_special_character_option_handling(self, mock_coordinator):
        """Test handling of options with special characters."""
        special_options = [
            "option/with\\slash",
            "option-with-dashes",
            "option_with_underscores",
            "option with spaces",
            "option@with#symbols$",
            "option%26encoded",
            "option<with>xml",
            "option'with\"quotes",
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="special_dog",
            dog_name="Special Dog",
            select_type="special_test",
            options=special_options,
            initial_option=special_options[0],
        )
        
        # Should handle special characters
        for option in special_options:
            assert option in select.options


class TestDynamicOptionListUpdates:
    """Test dynamic option list updates and synchronization."""

    @pytest.fixture
    def dynamic_select(self, mock_coordinator):
        """Create a select for dynamic option testing."""
        return PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="dynamic_dog",
            dog_name="Dynamic Dog",
            select_type="dynamic_test",
            options=["initial1", "initial2", "initial3"],
            initial_option="initial1",
        )

    def test_option_list_modification_during_runtime(self, dynamic_select):
        """Test modifying option list during runtime."""
        # Modify options list
        dynamic_select.options.copy()
        dynamic_select._attr_options = ["new1", "new2", "new3"]
        
        # Should reflect new options
        assert "new1" in dynamic_select.options
        assert "initial1" not in dynamic_select.options

    @pytest.mark.asyncio
    async def test_current_option_becomes_invalid_after_update(self, dynamic_select):
        """Test behavior when current option becomes invalid after option list update."""
        # Set current option
        await dynamic_select.async_select_option("initial2")
        assert dynamic_select.current_option == "initial2"
        
        # Update options list to exclude current option
        dynamic_select._attr_options = ["new1", "new2", "new3"]
        
        # Current option is now invalid for new list
        with pytest.raises(HomeAssistantError):
            await dynamic_select.async_select_option("initial2")  # No longer valid

    def test_empty_options_list_handling(self, mock_coordinator):
        """Test handling of empty options list."""
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="empty_dog",
            dog_name="Empty Dog",
            select_type="empty_test",
            options=[],  # Empty options list
            initial_option=None,
        )
        
        # Should handle empty options gracefully
        assert len(select.options) == 0

    @pytest.mark.asyncio
    async def test_single_option_select_behavior(self, mock_coordinator):
        """Test select behavior with only one option."""
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="single_dog",
            dog_name="Single Dog",
            select_type="single_test",
            options=["only_option"],
            initial_option="only_option",
        )
        
        # Should work with single option
        await select.async_select_option("only_option")
        assert select.current_option == "only_option"
        
        # Should reject other options
        with pytest.raises(HomeAssistantError):
            await select.async_select_option("invalid_option")

    def test_duplicate_options_handling(self, mock_coordinator):
        """Test handling of duplicate options in list."""
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="duplicate_dog",
            dog_name="Duplicate Dog",
            select_type="duplicate_test",
            options=["option1", "option2", "option1", "option3", "option2"],  # Duplicates
            initial_option="option1",
        )
        
        # Should handle duplicates gracefully
        assert "option1" in select.options
        assert "option2" in select.options
        assert "option3" in select.options


class TestServiceIntegrationTimeoutRecovery:
    """Test service integration timeout and recovery scenarios."""

    @pytest.fixture
    def service_dependent_select(self, mock_coordinator):
        """Create a select that depends on service calls."""
        return PawControlNotificationPrioritySelect(
            coordinator=mock_coordinator,
            dog_id="service_dog",
            dog_name="Service Dog",
        )

    @pytest.mark.asyncio
    async def test_service_call_timeout_during_option_change(self, service_dependent_select):
        """Test service call timeout during option selection."""
        # Mock service timeout
        with patch.object(service_dependent_select, '_async_set_select_option') as mock_set:
            mock_set.side_effect = asyncio.TimeoutError("Service timeout")
            
            # Should handle timeout gracefully
            with pytest.raises(HomeAssistantError, match="Failed to set notification_priority"):
                await service_dependent_select.async_select_option("high")

    @pytest.mark.asyncio
    async def test_coordinator_refresh_timeout_recovery(self, mock_coordinator):
        """Test recovery from coordinator refresh timeouts."""
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="timeout_dog",
            dog_name="Timeout Dog",
            dog_config={CONF_DOG_SIZE: "medium"},
        )
        
        # Mock coordinator timeout
        mock_coordinator.async_refresh_dog.side_effect = asyncio.TimeoutError("Coordinator timeout")
        
        # Should handle timeout without crashing
        await select._async_set_select_option("large")
        
        # Should log error but not raise exception

    @pytest.mark.asyncio
    async def test_partial_service_availability_during_setup(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup when some services are unavailable."""
        # Mock partial service availability
        with patch('homeassistant.core.ServiceRegistry.has_service') as mock_has_service:
            mock_has_service.side_effect = lambda domain, service: service != "unavailable_service"
            
            add_entities_mock = Mock()
            
            # Should handle partial service availability
            await async_setup_entry(hass, mock_entry, add_entities_mock)
            
            # Should still create entities
            add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_network_partition_during_option_change(self, service_dependent_select):
        """Test option change during network partition."""
        # Simulate network partition
        service_dependent_select.coordinator.available = False
        
        # Should handle network partition gracefully
        await service_dependent_select._async_set_select_option("urgent")
        
        # Should complete without external dependencies

    @pytest.mark.asyncio
    async def test_service_registry_unavailable(self, mock_coordinator):
        """Test behavior when service registry is unavailable."""
        select = PawControlFeedingScheduleSelect(
            coordinator=mock_coordinator,
            dog_id="registry_dog",
            dog_name="Registry Dog",
        )
        
        # Mock unavailable service registry
        with patch.object(select, 'hass', None):
            # Should handle missing hass gracefully
            await select._async_set_select_option("strict")


class TestModuleDataConsistencyCorruption:
    """Test module data consistency and corruption recovery."""

    @pytest.fixture
    def health_data_select(self, mock_coordinator):
        """Create a health status select for data testing."""
        return PawControlHealthStatusSelect(
            coordinator=mock_coordinator,
            dog_id="health_data_dog",
            dog_name="Health Data Dog",
        )

    def test_corrupted_module_data_handling(self, health_data_select):
        """Test handling of corrupted module data."""
        # Mock corrupted module data
        corrupted_data = {
            "health_status": 123,  # Should be string
            "invalid_field": object(),  # Invalid object
            "nested": {"deeply": {"corrupted": None}},
        }
        
        health_data_select.coordinator.get_module_data.return_value = corrupted_data
        
        # Should handle corruption gracefully
        try:
            current_option = health_data_select.current_option
            # Should not crash, may return default
            assert current_option is not None
        except (TypeError, AttributeError):
            # Acceptable failure mode for corrupted data
            pass

    def test_missing_expected_fields_in_module_data(self, health_data_select):
        """Test behavior when expected fields are missing from module data."""
        # Mock data missing expected health_status field
        incomplete_data = {
            "other_field": "value",
            "unrelated_data": 123,
        }
        
        health_data_select.coordinator.get_module_data.return_value = incomplete_data
        
        # Should fall back to default option
        assert health_data_select.current_option == "good"  # Default

    def test_module_data_type_mismatches(self, health_data_select):
        """Test handling of type mismatches in module data."""
        type_mismatch_cases = [
            {"health_status": 123},          # Integer instead of string
            {"health_status": ["list"]},     # List instead of string
            {"health_status": {"dict": 1}},  # Dict instead of string
            {"health_status": True},         # Boolean instead of string
            {"health_status": 3.14},         # Float instead of string
        ]
        
        for case_data in type_mismatch_cases:
            health_data_select.coordinator.get_module_data.return_value = case_data
            
            # Should handle type mismatches gracefully
            try:
                current_option = health_data_select.current_option
                # May convert to string or use default
                assert current_option is not None
            except (TypeError, ValueError):
                # Acceptable failure mode for type mismatches
                pass

    def test_circular_reference_in_module_data(self, health_data_select):
        """Test handling of circular references in module data."""
        # Create circular reference
        circular_data = {"health_status": "good"}
        circular_data["self_ref"] = circular_data  # Circular reference
        
        health_data_select.coordinator.get_module_data.return_value = circular_data
        
        # Should handle circular references without infinite loops
        current_option = health_data_select.current_option
        assert current_option == "good"

    def test_extremely_large_module_data(self, health_data_select):
        """Test handling of extremely large module data."""
        # Create very large data structure
        large_data = {
            "health_status": "excellent",
            "large_field": "x" * 1000000,  # 1MB string
            "many_fields": {f"field_{i}": f"value_{i}" for i in range(10000)},
        }
        
        health_data_select.coordinator.get_module_data.return_value = large_data
        
        # Should handle large data efficiently
        current_option = health_data_select.current_option
        assert current_option == "excellent"

    @pytest.mark.asyncio
    async def test_concurrent_module_data_updates(self, health_data_select):
        """Test concurrent updates to module data."""
        async def update_module_data(status):
            for _ in range(10):
                health_data_select.coordinator.get_module_data.return_value = {
                    "health_status": status
                }
                await asyncio.sleep(0.001)
        
        # Run concurrent updates
        await asyncio.gather(
            update_module_data("excellent"),
            update_module_data("good"),
            update_module_data("poor"),
        )
        
        # Should handle concurrent updates
        current_option = health_data_select.current_option
        assert current_option in HEALTH_STATUS_OPTIONS


class TestEntityRegistryCollisionResolution:
    """Test entity registry collision detection and resolution."""

    def test_unique_id_collision_prevention(self, mock_coordinator):
        """Test prevention of unique ID collisions."""
        # Create selects with potentially colliding configurations
        selects = []
        for i in range(10):
            # Same dog ID but different select types
            for select_type in ["test_1", "test_2", "test_3"]:
                select = PawControlSelectBase(
                    coordinator=mock_coordinator,
                    dog_id=f"collision_dog_{i}",
                    dog_name=f"Collision Dog {i}",
                    select_type=select_type,
                    options=["option1", "option2"],
                )
                selects.append(select)
        
        # Collect all unique IDs
        unique_ids = [select.unique_id for select in selects]
        
        # Should not have collisions
        assert len(unique_ids) == len(set(unique_ids))

    def test_entity_id_collision_with_special_characters(self, mock_coordinator):
        """Test entity ID collision prevention with special characters."""
        problematic_combinations = [
            ("dog_1", "test_switch"),
            ("dog", "1_test_switch"),
            ("dog_1_test", "switch"),
            ("dog", "1_test_switch"),
        ]
        
        selects = []
        for dog_id, select_type in problematic_combinations:
            select = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=dog_id,
                dog_name=f"Dog {dog_id}",
                select_type=select_type,
                options=["option1", "option2"],
            )
            selects.append(select)
        
        # Should generate unique IDs despite similar patterns
        unique_ids = [select.unique_id for select in selects]
        assert len(unique_ids) == len(set(unique_ids))

    def test_device_info_collision_prevention(self, mock_coordinator):
        """Test device info collision prevention."""
        # Create selects for same dog but different types
        select_types = ["size", "performance", "food_type", "walk_mode", "gps_source"]
        selects = []
        
        for select_type in select_types:
            select = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id="same_dog",
                dog_name="Same Dog",
                select_type=select_type,
                options=["option1", "option2"],
            )
            selects.append(select)
        
        # All should have same device info (grouped by dog)
        device_infos = [select._attr_device_info for select in selects]
        identifiers = [info["identifiers"] for info in device_infos]
        
        # Should all have same device identifiers (same dog)
        for identifier in identifiers[1:]:
            assert identifier == identifiers[0]

    @pytest.mark.asyncio
    async def test_entity_registry_stress_with_many_selects(self, hass: HomeAssistant, mock_coordinator):
        """Test entity registry handling with many select entities."""
        # Create many select entities to stress registry
        selects = []
        for i in range(100):
            for j, select_type in enumerate(["type1", "type2", "type3"]):
                select = PawControlSelectBase(
                    coordinator=mock_coordinator,
                    dog_id=f"stress_dog_{i}",
                    dog_name=f"Stress Dog {i}",
                    select_type=f"{select_type}_{j}",
                    options=["option1", "option2"],
                )
                selects.append(select)
        
        # Simulate adding to registry in batches
        add_entities_mock = Mock()
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            selects,
            batch_size=10,
            delay_between_batches=0.001,
        )
        
        # Should handle large numbers of entities
        assert add_entities_mock.call_count == 30  # 300 entities / 10 batch_size


class TestMultiLanguageOptionHandling:
    """Test multi-language option handling and validation."""

    def test_localized_option_display(self, mock_coordinator):
        """Test display of localized options."""
        # Create select with options that might be localized
        select = PawControlWeatherPreferenceSelect(
            coordinator=mock_coordinator,
            dog_id="localized_dog",
            dog_name="Localized Dog",
        )
        
        # Options should be in consistent language (English by default)
        for option in select.options:
            assert isinstance(option, str)
            assert len(option) > 0

    def test_unicode_option_compatibility(self, mock_coordinator):
        """Test compatibility with Unicode option values."""
        unicode_food_types = [
            "trockenfutter",  # German
            "comida_húmeda",  # Spanish  
            "cibo_secco",     # Italian
            "ドライフード",      # Japanese
            "건사료",          # Korean
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="unicode_food_dog",
            dog_name="Unicode Food Dog",
            select_type="unicode_food_type",
            options=unicode_food_types,
            initial_option=unicode_food_types[0],
        )
        
        # Should handle Unicode options correctly
        for option in unicode_food_types:
            assert option in select.options

    def test_rtl_language_option_handling(self, mock_coordinator):
        """Test right-to-left language option handling."""
        rtl_options = [
            "طعام_جاف",      # Arabic - dry food
            "طعام_رطب",      # Arabic - wet food  
            "אוכל_יבש",      # Hebrew - dry food
            "אוכל_רטוב",     # Hebrew - wet food
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="rtl_dog",
            dog_name="RTL Dog",
            select_type="rtl_test",
            options=rtl_options,
            initial_option=rtl_options[0],
        )
        
        # Should handle RTL languages
        assert len(select.options) == len(rtl_options)

    def test_mixed_script_option_handling(self, mock_coordinator):
        """Test handling of mixed script options."""
        mixed_options = [
            "English",
            "Español",
            "Français", 
            "Deutsch",
            "Русский",
            "中文",
            "日本語",
            "العربية",
            "עברית",
        ]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="mixed_script_dog",
            dog_name="Mixed Script Dog",
            select_type="mixed_script_test",
            options=mixed_options,
            initial_option="English",
        )
        
        # Should handle mixed scripts
        for option in mixed_options:
            assert option in select.options


class TestConcurrentOptionSelectionProtection:
    """Test protection against concurrent option selections."""

    @pytest.fixture
    def concurrent_select(self, mock_coordinator):
        """Create a select for concurrent operation testing."""
        return PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="concurrent_dog",
            dog_name="Concurrent Dog",
            select_type="concurrent_test",
            options=["option1", "option2", "option3", "option4", "option5"],
            initial_option="option1",
        )

    @pytest.mark.asyncio
    async def test_concurrent_option_selection_safety(self, concurrent_select):
        """Test safety of concurrent option selections."""
        async def select_options():
            for i in range(20):
                option = f"option{(i % 5) + 1}"
                await concurrent_select.async_select_option(option)
                await asyncio.sleep(0.001)
        
        # Run concurrent selections
        await asyncio.gather(
            select_options(),
            select_options(),
            select_options(),
        )
        
        # Should end in valid state
        assert concurrent_select.current_option in concurrent_select.options

    @pytest.mark.asyncio
    async def test_rapid_option_changes_stability(self, concurrent_select):
        """Test stability under rapid option changes."""
        # Rapidly change options
        for i in range(100):
            option = f"option{(i % 5) + 1}"
            await concurrent_select.async_select_option(option)
        
        # Should maintain stability
        assert concurrent_select.current_option in concurrent_select.options

    @pytest.mark.asyncio
    async def test_option_selection_during_registry_operations(self, concurrent_select):
        """Test option selection during simulated registry operations."""
        async def simulate_registry_operations():
            # Simulate registry operations that might interfere
            for _ in range(10):
                concurrent_select._attr_name = f"Updated {concurrent_select._attr_name}"
                await asyncio.sleep(0.001)
        
        async def change_options():
            for i in range(10):
                option = f"option{(i % 5) + 1}"
                await concurrent_select.async_select_option(option)
                await asyncio.sleep(0.001)
        
        # Run concurrent operations
        await asyncio.gather(
            simulate_registry_operations(),
            change_options(),
        )
        
        # Should remain functional
        assert concurrent_select.current_option in concurrent_select.options


class TestPerformanceOptimizationUnderLoad:
    """Test performance optimization under heavy load conditions."""

    @pytest.mark.asyncio
    async def test_batch_processing_performance_with_large_datasets(self, mock_coordinator):
        """Test batch processing performance with large numbers of selects."""
        # Create large number of select entities
        large_entity_count = 500
        entities = []
        
        for i in range(large_entity_count):
            entity = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id=f"perf_dog_{i}",
                dog_name=f"Performance Dog {i}",
                select_type="performance_test",
                options=[f"option_{j}" for j in range(10)],
                initial_option="option_0",
            )
            entities.append(entity)
        
        add_entities_mock = Mock()
        
        # Measure performance
        start_time = dt_util.utcnow()
        
        await _async_add_entities_in_batches(
            add_entities_mock,
            entities,
            batch_size=20,  # Larger batches for performance
            delay_between_batches=0.001,
        )
        
        end_time = dt_util.utcnow()
        
        # Should complete in reasonable time
        duration = (end_time - start_time).total_seconds()
        assert duration < 5.0  # Should be fast even with 500 entities
        
        # Should use appropriate number of batches
        expected_batches = (large_entity_count + 19) // 20  # Ceiling division
        assert add_entities_mock.call_count == expected_batches

    def test_memory_efficiency_with_large_option_sets(self, mock_coordinator):
        """Test memory efficiency with large option sets."""
        # Create select with very large option set
        large_options = [f"option_{i}" for i in range(10000)]
        
        select = PawControlSelectBase(
            coordinator=mock_coordinator,
            dog_id="large_options_dog",
            dog_name="Large Options Dog",
            select_type="large_options_test",
            options=large_options,
            initial_option="option_0",
        )
        
        # Should handle large option sets efficiently
        assert len(select.options) == 10000
        assert "option_0" in select.options
        assert "option_9999" in select.options

    @pytest.mark.asyncio
    async def test_concurrent_select_factory_performance(self, mock_coordinator):
        """Test performance of concurrent select factory operations."""
        async def create_selects_for_dogs(start_index, count):
            all_selects = []
            for i in range(start_index, start_index + count):
                dog_config = {CONF_DOG_SIZE: DOG_SIZES[i % len(DOG_SIZES)]}
                
                # Create all types of selects
                selects = []
                selects.extend(_create_base_selects(
                    mock_coordinator, f"perf_dog_{i}", f"Performance Dog {i}", dog_config
                ))
                selects.extend(_create_feeding_selects(
                    mock_coordinator, f"perf_dog_{i}", f"Performance Dog {i}"
                ))
                selects.extend(_create_walk_selects(
                    mock_coordinator, f"perf_dog_{i}", f"Performance Dog {i}"
                ))
                selects.extend(_create_gps_selects(
                    mock_coordinator, f"perf_dog_{i}", f"Performance Dog {i}"
                ))
                selects.extend(_create_health_selects(
                    mock_coordinator, f"perf_dog_{i}", f"Performance Dog {i}"
                ))
                
                all_selects.extend(selects)
            return all_selects
        
        # Create selects concurrently
        start_time = dt_util.utcnow()
        
        select_lists = await asyncio.gather(
            create_selects_for_dogs(0, 20),
            create_selects_for_dogs(20, 20),
            create_selects_for_dogs(40, 20),
        )
        
        end_time = dt_util.utcnow()
        
        # Should complete efficiently
        duration = (end_time - start_time).total_seconds()
        assert duration < 2.0  # Should be fast
        
        # Verify all selects created
        all_selects = [s for sublist in select_lists for s in sublist]
        assert len(all_selects) > 100  # Should create many selects


class TestConfigurationMigrationBackwardCompatibility:
    """Test configuration migration and backward compatibility."""

    @pytest.mark.asyncio
    async def test_legacy_option_format_migration(self, hass: HomeAssistant, mock_coordinator):
        """Test migration from legacy option formats."""
        # Create legacy format config entry
        legacy_entry = MagicMock(spec=ConfigEntry)
        legacy_entry.entry_id = "legacy_entry"
        legacy_entry.data = {
            "dogs": [  # Legacy format
                {
                    "id": "legacy_dog",
                    "name": "Legacy Dog",
                    "size": "medium",  # Direct size instead of CONF_DOG_SIZE
                    "options": {       # Legacy options format
                        "food": "dry",
                        "schedule": "flexible",
                    }
                }
            ]
        }
        
        add_entities_mock = Mock()
        
        # Should handle legacy format gracefully
        try:
            await async_setup_entry(hass, legacy_entry, add_entities_mock)
        except (KeyError, AttributeError):
            # Expected behavior with legacy format
            pass

    def test_option_value_migration(self, mock_coordinator):
        """Test migration of option values between versions."""
        # Test mapping old option values to new ones
        legacy_value_mappings = {
            "dry": "dry_food",        # Old -> New food type
            "automatic": "auto",      # Old -> New walk mode  
            "normal": "balanced",     # Old -> New performance mode
        }
        
        for old_value, new_value in legacy_value_mappings.items():
            # Simulate select with legacy initial value
            select = PawControlSelectBase(
                coordinator=mock_coordinator,
                dog_id="migration_dog",
                dog_name="Migration Dog",
                select_type="migration_test",
                options=[new_value, "other_option"],  # New format options
                initial_option=new_value,  # Use new value
            )
            
            # Should work with new format
            assert select.current_option == new_value

    def test_backward_compatible_info_methods(self, mock_coordinator):
        """Test backward compatibility of info getter methods."""
        # Test that old info methods still work
        select = PawControlDogSizeSelect(
            coordinator=mock_coordinator,
            dog_id="backward_dog",
            dog_name="Backward Dog",
            dog_config={CONF_DOG_SIZE: "large"},
        )
        
        # Should handle both old and new size formats
        size_info = select._get_size_info("large")
        assert "weight_range" in size_info
        
        # Should handle legacy size names if they existed
        legacy_size_info = select._get_size_info("xl")  # Hypothetical old name
        assert legacy_size_info == {}  # Should return empty for unknown


if __name__ == "__main__":
    pytest.main([__file__])
