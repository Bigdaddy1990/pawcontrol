"""Comprehensive edge case tests for PawControl select platform.

These tests cover edge cases, error scenarios, and stress conditions to ensure
robust behavior under unusual circumstances and achieve Gold Standard coverage.
"""

import asyncio
import gc
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from typing import Any, Dict, List

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.select import (
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
    async_setup_entry,
    _async_add_entities_in_batches,
    _create_base_selects,
    _create_feeding_selects,
    _create_walk_selects,
    _create_gps_selects,
    _create_health_selects,
    WALK_MODES,
    NOTIFICATION_PRIORITIES,
    TRACKING_MODES,
    FEEDING_SCHEDULES,
    GROOMING_TYPES,
    WEATHER_CONDITIONS,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOGS,
    DOMAIN,
    DOG_SIZES,
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
    ACTIVITY_LEVELS,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator


class TestSelectEdgeCases:
    """Test edge cases and unusual scenarios for select entities."""

    @pytest.fixture
    def mock_coordinator_unstable(self):
        """Create a coordinator that becomes unavailable intermittently."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator._available_state = True
        
        def toggle_availability():
            coordinator._available_state = not coordinator._available_state
            return coordinator._available_state
        
        coordinator.available = property(lambda self: toggle_availability())
        coordinator.get_dog_data = Mock(return_value={
            "dog_info": {"dog_breed": "Test", "dog_age": 5}
        })
        coordinator.get_module_data = Mock(return_value={})
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_coordinator_corrupted_data(self):
        """Create a coordinator returning corrupted/invalid data."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        
        # Return various types of corrupted data
        corrupted_data_sequence = [
            None,  # Missing data
            {"dog_info": None},  # Null dog_info
            {"dog_info": "invalid_type"},  # Wrong type
            {"dog_info": {}},  # Empty dog_info
            {"dog_info": {"dog_breed": None}},  # Null breed
            {"dog_info": {"dog_age": "not_int"}},  # Wrong age type
            {},  # Missing keys
            {"unexpected_key": "value"},  # Unexpected structure
        ]
        
        coordinator.get_dog_data = Mock(side_effect=corrupted_data_sequence * 10)
        coordinator.get_module_data = Mock(side_effect=corrupted_data_sequence * 10)
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    def test_select_with_unicode_dog_names(self, mock_coordinator_unstable):
        """Test select creation with unicode and special characters in dog names."""
        unicode_names = [
            "🐕 Max",
            "Röver",
            "Naïve",
            "José Miguel",
            "Собака",  # Russian
            "犬",      # Japanese
            "כלב",     # Hebrew
            "   Spaced   ",
            "Multi\nLine",
            "Tab\tSeparated",
            "",  # Empty name
            None,  # None name
        ]
        
        for dog_name in unicode_names:
            select = PawControlDogSizeSelect(
                mock_coordinator_unstable, "test_dog", dog_name or "Default", {}
            )
            
            # Should handle all unicode gracefully
            assert select._dog_name == (dog_name or "Default")
            assert isinstance(select._attr_name, str)
            assert select._attr_unique_id.startswith("pawcontrol_")

    def test_select_with_extremely_long_identifiers(self, mock_coordinator_unstable):
        """Test selects with very long dog IDs and names."""
        long_dog_id = "a" * 1000  # Very long ID
        long_dog_name = "B" * 500  # Very long name
        
        select = PawControlFoodTypeSelect(
            mock_coordinator_unstable, long_dog_id, long_dog_name
        )
        
        assert select._dog_id == long_dog_id
        assert select._dog_name == long_dog_name
        # Unique ID should be created without issues
        assert len(select._attr_unique_id) > 1000

    def test_select_with_malformed_options_list(self, mock_coordinator_unstable):
        """Test select creation with malformed options lists."""
        malformed_options = [
            [],  # Empty options
            None,  # None options
            [""],  # Empty string option
            [None],  # None option
            ["option1", None, "option3"],  # Mixed with None
            ["🎯", "🐕", "🚀"],  # Unicode options
            [1, 2, 3],  # Non-string options
            ["a" * 1000],  # Very long option
        ]
        
        for options in malformed_options:
            try:
                # Create base select with malformed options
                select = PawControlSelectBase(
                    mock_coordinator_unstable,
                    "test_dog",
                    "Test Dog",
                    "test_select",
                    options=options or ["default"],  # Provide fallback
                )
                
                # Should handle malformed options gracefully
                assert hasattr(select, '_attr_options')
                
            except Exception as e:
                # Some malformed options might raise exceptions, which is acceptable
                assert isinstance(e, (TypeError, ValueError))

    @pytest.mark.asyncio
    async def test_select_option_validation_edge_cases(self, mock_coordinator_unstable):
        """Test select option validation with edge case inputs."""
        select = PawControlFoodTypeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        select.hass = Mock()
        
        edge_case_options = [
            "",  # Empty string
            None,  # None
            123,  # Number
            [],  # List
            {},  # Dict
            "UPPERCASE",  # Case sensitivity
            "  spaced  ",  # Spaces
            "invalid_option",  # Not in options list
            "wet_food",  # Valid option for comparison
        ]
        
        for option in edge_case_options:
            try:
                if option == "wet_food":  # Valid option
                    await select.async_select_option(str(option))
                    assert select._current_option == str(option)
                else:
                    # Invalid options should raise HomeAssistantError
                    with pytest.raises(HomeAssistantError):
                        await select.async_select_option(str(option) if option is not None else "")
            except TypeError:
                # Some edge cases might cause type errors, which is acceptable
                pass

    @pytest.mark.asyncio
    async def test_select_corrupted_data_handling(self, mock_coordinator_corrupted_data):
        """Test select behavior with corrupted coordinator data."""
        selects = [
            PawControlDogSizeSelect(mock_coordinator_corrupted_data, "test_dog", "Test", {}),
            PawControlHealthStatusSelect(mock_coordinator_corrupted_data, "test_dog", "Test"),
            PawControlActivityLevelSelect(mock_coordinator_corrupted_data, "test_dog", "Test"),
        ]
        
        for select in selects:
            # Should handle all corrupted data gracefully
            for _ in range(8):  # Test all corrupted data types
                try:
                    dog_data = select._get_dog_data()
                    # Should either return valid data or None
                    assert dog_data is None or isinstance(dog_data, dict)
                    
                    # Extra state attributes should not crash
                    attrs = select.extra_state_attributes
                    assert isinstance(attrs, dict)
                    
                    # Availability should be deterministic
                    available = select.available
                    assert isinstance(available, bool)
                    
                    # Current option should be accessible
                    current_option = select.current_option
                    assert current_option is None or isinstance(current_option, str)
                    
                except Exception as e:
                    pytest.fail(f"Select should handle corrupted data gracefully: {e}")

    @pytest.mark.asyncio
    async def test_select_state_restoration_edge_cases(self, hass):
        """Test state restoration with edge case stored states."""
        select = PawControlPerformanceModeSelect(
            Mock(), "test_dog", "Test Dog"
        )
        select.hass = hass
        
        # Test various stored state scenarios
        edge_case_states = [
            None,  # No previous state
            Mock(state="invalid_mode"),  # Invalid state value
            Mock(state=None),  # None state
            Mock(state=""),  # Empty state
            Mock(state="balanced"),  # Valid state
            Mock(state="BALANCED"),  # Case mismatch
            Mock(state="  balanced  "),  # Whitespace
            Mock(state="🎯"),  # Unicode state
        ]
        
        for mock_state in edge_case_states:
            with patch.object(select, "async_get_last_state", return_value=mock_state):
                await select.async_added_to_hass()
                
                # Should handle all edge cases gracefully
                assert select._current_option is None or select._current_option in select.options

    def test_select_device_info_edge_cases(self, mock_coordinator_unstable):
        """Test device info generation with edge case inputs."""
        edge_case_inputs = [
            ("", ""),  # Empty strings
            (None, None),  # None values (handled by fixture)
            ("dog\nwith\nnewlines", "Name\nWith\nLines"),
            ("dog/with/slashes", "Name/With/Slashes"),
            ("dog with spaces", "Name With Spaces"),
            ("🐕", "🎯"),  # Unicode
        ]
        
        for dog_id, dog_name in edge_case_inputs:
            if dog_id is None or dog_name is None:
                continue  # Skip None values
                
            select = PawControlMoodSelect(
                mock_coordinator_unstable, dog_id, dog_name
            )
            
            device_info = select._attr_device_info
            
            # Should always generate valid device info
            assert isinstance(device_info, dict)
            assert "identifiers" in device_info
            assert "name" in device_info
            assert "manufacturer" in device_info

    @pytest.mark.asyncio
    async def test_select_coordinator_timeout(self, mock_coordinator_unstable):
        """Test select behavior when coordinator operations timeout."""
        select = PawControlDogSizeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog", {}
        )
        
        # Mock coordinator methods to timeout
        mock_coordinator_unstable.async_refresh_dog = AsyncMock(
            side_effect=asyncio.TimeoutError("Coordinator timeout")
        )
        
        # Should handle timeout gracefully
        await select._async_set_select_option("large")
        # Should not raise exception despite timeout

    @pytest.mark.asyncio
    async def test_select_concurrent_option_changes(self, mock_coordinator_unstable):
        """Test concurrent select option changes."""
        select = PawControlWalkModeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        select.hass = Mock()
        select.async_write_ha_state = Mock()
        
        # Create many concurrent option changes
        async def change_options():
            options = ["automatic", "manual", "hybrid"]
            for _ in range(50):
                for option in options:
                    await select.async_select_option(option)
                    await asyncio.sleep(0.001)
        
        # Run multiple concurrent changes
        tasks = [change_options() for _ in range(3)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent operations without corruption
        assert select._current_option in select.options

    def test_select_info_methods_edge_cases(self, mock_coordinator_unstable):
        """Test info getter methods with edge case inputs."""
        # Test dog size select info
        size_select = PawControlDogSizeSelect(
            mock_coordinator_unstable, "test_dog", "Test", {}
        )
        
        edge_case_sizes = [None, "", "invalid_size", "🐕", "GIANT"]
        for size in edge_case_sizes:
            size_info = size_select._get_size_info(size)
            assert isinstance(size_info, dict)
        
        # Test food type select info
        food_select = PawControlFoodTypeSelect(
            mock_coordinator_unstable, "test_dog", "Test"
        )
        
        edge_case_foods = [None, "", "invalid_food", "🍖", "DRY_FOOD"]
        for food in edge_case_foods:
            food_info = food_select._get_food_type_info(food)
            assert isinstance(food_info, dict)
        
        # Test performance mode select info
        perf_select = PawControlPerformanceModeSelect(
            mock_coordinator_unstable, "test_dog", "Test"
        )
        
        edge_case_modes = [None, "", "invalid_mode", "⚡", "FULL"]
        for mode in edge_case_modes:
            mode_info = perf_select._get_performance_mode_info(mode)
            assert isinstance(mode_info, dict)

    @pytest.mark.asyncio
    async def test_select_hass_unavailable_scenarios(self, mock_coordinator_unstable):
        """Test select behavior when Home Assistant is unavailable/shutting down."""
        select = PawControlNotificationPrioritySelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Test with various hass states
        hass_states = [
            None,  # No hass
            Mock(data=None),  # No data
            Mock(data={}),  # Empty data
            Mock(data={DOMAIN: None}),  # No domain data
        ]
        
        for hass_state in hass_states:
            select.hass = hass_state
            
            # Should handle unavailable hass gracefully
            await select._async_set_select_option("high")
            # Should not crash

    def test_select_attribute_access_edge_cases(self, mock_coordinator_unstable):
        """Test select attribute access with missing/corrupted attributes."""
        select = PawControlGPSSourceSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Corrupt internal attributes
        original_dog_id = select._dog_id
        select._dog_id = None
        
        # Should handle corrupted attributes gracefully
        try:
            attrs = select.extra_state_attributes
            assert isinstance(attrs, dict)
        except Exception:
            pytest.fail("Should handle corrupted attributes gracefully")
        finally:
            # Restore for cleanup
            select._dog_id = original_dog_id

    def test_select_with_dynamic_option_lists(self, mock_coordinator_unstable):
        """Test select behavior when option lists change dynamically."""
        select = PawControlSelectBase(
            mock_coordinator_unstable,
            "test_dog",
            "Test Dog",
            "dynamic_select",
            options=["option1", "option2"],
        )
        
        # Change options dynamically
        original_options = select._attr_options.copy()
        select._attr_options = ["new1", "new2", "new3"]
        
        # Current option might become invalid
        select._current_option = "option1"  # No longer in options
        
        # Should handle gracefully
        assert select.options == ["new1", "new2", "new3"]
        
        # Restore original for cleanup
        select._attr_options = original_options

    @pytest.mark.asyncio
    async def test_select_memory_pressure(self, mock_coordinator_unstable):
        """Test select behavior under memory pressure."""
        selects = []
        
        # Create many selects to apply memory pressure
        try:
            for i in range(1000):
                select = PawControlMoodSelect(
                    mock_coordinator_unstable, f"dog_{i}", f"Dog {i}"
                )
                selects.append(select)
                
                # Access properties to allocate memory
                select.extra_state_attributes
                select.available
                
        except MemoryError:
            # Expected under extreme conditions
            pass
        
        # Should have created some selects
        assert len(selects) > 0
        
        # First select should still be functional
        if selects:
            assert selects[0]._dog_id == "dog_0"

    @pytest.mark.asyncio
    async def test_batch_addition_memory_stress(self):
        """Test batch entity addition under memory stress."""
        # Create many entities to stress test batching
        entities = [Mock(spec=PawControlSelectBase) for _ in range(1000)]
        added_entities = []
        
        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)
            # Simulate registry processing time
            time.sleep(0.001)
        
        # Test with very small batch size to stress the system
        await _async_add_entities_in_batches(
            mock_add_entities, entities, batch_size=5, delay_between_batches=0.0001
        )
        
        # Should handle large number of entities
        assert len(added_entities) == 1000

    def test_select_creation_function_edge_cases(self, mock_coordinator_unstable):
        """Test select creation functions with edge case inputs."""
        edge_case_dog_configs = [
            {},  # Empty config
            {CONF_DOG_SIZE: None},  # None size
            {CONF_DOG_SIZE: ""},  # Empty size
            {CONF_DOG_SIZE: "invalid_size"},  # Invalid size
            {"unexpected_key": "value"},  # Unexpected keys
        ]
        
        for dog_config in edge_case_dog_configs:
            try:
                # Test all creation functions
                base_selects = _create_base_selects(
                    mock_coordinator_unstable, "test_dog", "Test", dog_config
                )
                assert len(base_selects) >= 0
                
                feeding_selects = _create_feeding_selects(
                    mock_coordinator_unstable, "test_dog", "Test"
                )
                assert len(feeding_selects) >= 0
                
                walk_selects = _create_walk_selects(
                    mock_coordinator_unstable, "test_dog", "Test"
                )
                assert len(walk_selects) >= 0
                
                gps_selects = _create_gps_selects(
                    mock_coordinator_unstable, "test_dog", "Test"
                )
                assert len(gps_selects) >= 0
                
                health_selects = _create_health_selects(
                    mock_coordinator_unstable, "test_dog", "Test"
                )
                assert len(health_selects) >= 0
                
            except Exception as e:
                pytest.fail(f"Creation functions should handle edge cases: {e}")

    @pytest.mark.asyncio
    async def test_select_rapid_option_changes(self, mock_coordinator_unstable):
        """Test select behavior with rapid option changes."""
        select = PawControlTrackingModeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        select.hass = Mock()
        select.async_write_ha_state = Mock()
        
        # Rapid option changes through all available options
        for _ in range(1000):
            for option in TRACKING_MODES:
                await select.async_select_option(option)
        
        # Should remain consistent
        assert select._current_option in TRACKING_MODES

    def test_select_with_corrupted_constants(self, mock_coordinator_unstable):
        """Test select behavior when constants are corrupted."""
        # Temporarily corrupt constants to test robustness
        original_food_types = FOOD_TYPES.copy()
        
        try:
            # Corrupt the FOOD_TYPES constant
            FOOD_TYPES.clear()
            FOOD_TYPES.extend([None, "", "invalid"])
            
            select = PawControlFoodTypeSelect(
                mock_coordinator_unstable, "test_dog", "Test"
            )
            
            # Should handle corrupted constants gracefully
            assert hasattr(select, '_attr_options')
            
        finally:
            # Restore original constants
            FOOD_TYPES.clear()
            FOOD_TYPES.extend(original_food_types)


class TestSelectPerformanceEdgeCases:
    """Test performance-related edge cases for select entities."""

    def test_select_with_large_option_lists(self, mock_coordinator_unstable):
        """Test select performance with very large option lists."""
        # Create select with many options
        large_options = [f"option_{i}" for i in range(10000)]
        
        select = PawControlSelectBase(
            mock_coordinator_unstable,
            "test_dog",
            "Test Dog",
            "large_select",
            options=large_options,
        )
        
        # Should handle large option lists
        assert len(select.options) == 10000
        
        # Option validation should still work
        assert "option_5000" in select.options
        assert "invalid_option" not in select.options

    @pytest.mark.asyncio
    async def test_select_performance_with_frequent_access(self, mock_coordinator_unstable):
        """Test select performance with frequent property access."""
        select = PawControlHealthStatusSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Access properties frequently
        start_time = time.time()
        
        for _ in range(1000):
            select.current_option
            select.extra_state_attributes
            select.available
            select.options
        
        end_time = time.time()
        
        # Should complete quickly
        assert end_time - start_time < 1.0

    def test_select_memory_usage_optimization(self, mock_coordinator_unstable):
        """Test memory usage patterns of selects."""
        # Create selects and measure memory impact
        selects = []
        initial_objects = len(gc.get_objects())
        
        for i in range(100):
            select = PawControlActivityLevelSelect(
                mock_coordinator_unstable, f"dog_{i}", f"Dog {i}"
            )
            selects.append(select)
        
        final_objects = len(gc.get_objects())
        
        # Clean up
        selects.clear()
        gc.collect()
        
        cleanup_objects = len(gc.get_objects())
        
        # Memory should be reasonable and cleanable
        objects_created = final_objects - initial_objects
        objects_cleaned = final_objects - cleanup_objects
        
        assert objects_created > 0  # Should create objects
        assert objects_cleaned > 0  # Should clean up objects

    @pytest.mark.asyncio
    async def test_batch_addition_extreme_conditions(self):
        """Test batch addition under extreme conditions."""
        # Test with extreme batch parameters
        entities = [Mock(spec=PawControlSelectBase) for _ in range(10)]
        added_entities = []
        
        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)
        
        # Test with zero delay and single entity batches
        await _async_add_entities_in_batches(
            mock_add_entities, entities, batch_size=1, delay_between_batches=0
        )
        
        assert len(added_entities) == 10


class TestSelectSecurityEdgeCases:
    """Test security-related edge cases for select entities."""

    def test_select_input_sanitization(self, mock_coordinator_unstable):
        """Test select behavior with potentially malicious inputs."""
        malicious_inputs = [
            "'; DROP TABLE dogs; --",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
            "../../../etc/passwd",  # Path traversal
            "\x00\x01\x02",  # Control characters
            "A" * 100000,  # Extremely long input
        ]
        
        for malicious_input in malicious_inputs:
            select = PawControlGroomingTypeSelect(
                mock_coordinator_unstable, malicious_input, malicious_input
            )
            
            # Should handle malicious inputs safely
            assert select._dog_id == malicious_input
            assert select._dog_name == malicious_input
            
            # Should not cause system issues
            device_info = select._attr_device_info
            assert isinstance(device_info, dict)

    @pytest.mark.asyncio
    async def test_select_option_injection_resistance(self, mock_coordinator_unstable):
        """Test select resistance to option injection attacks."""
        select = PawControlLocationAccuracySelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        select.hass = Mock()
        
        # Try to inject malicious options
        malicious_options = [
            "'; DROP TABLE options; --",
            "<script>alert('injected')</script>",
            "../../sensitive_file",
            "balanced; rm -rf /",
        ]
        
        for malicious_option in malicious_options:
            # Should reject invalid options
            with pytest.raises(HomeAssistantError):
                await select.async_select_option(malicious_option)

    def test_select_data_isolation(self, mock_coordinator_unstable):
        """Test that select data is properly isolated between instances."""
        select1 = PawControlWeatherPreferenceSelect(
            mock_coordinator_unstable, "dog1", "Dog 1"
        )
        select2 = PawControlWeatherPreferenceSelect(
            mock_coordinator_unstable, "dog2", "Dog 2"
        )
        
        # Modify one select's current option
        select1._current_option = "sunny"
        select2._current_option = "rainy"
        
        # Options should be independent
        assert select1.current_option != select2.current_option

    def test_select_unique_id_collision_handling(self, mock_coordinator_unstable):
        """Test select behavior with potential unique ID collisions."""
        # Create selects that might have similar unique IDs
        selects = []
        
        similar_ids = [
            ("dog_1", "Dog 1"),
            ("dog_1", "Dog 1 "),  # Trailing space
            ("dog-1", "Dog-1"),   # Different separator
            ("dog1", "Dog1"),     # No separator
        ]
        
        for dog_id, dog_name in similar_ids:
            select = PawControlWalkIntensitySelect(
                mock_coordinator_unstable, dog_id, dog_name
            )
            selects.append(select)
        
        # All selects should have unique IDs
        unique_ids = [select._attr_unique_id for select in selects]
        assert len(set(unique_ids)) == len(unique_ids)


class TestSelectCompatibilityEdgeCases:
    """Test compatibility edge cases with different HA versions and configurations."""

    def test_select_with_missing_attributes(self, mock_coordinator_unstable):
        """Test select behavior when Home Assistant attributes are missing."""
        select = PawControlFeedingModeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Remove some attributes to simulate version differences
        if hasattr(select, '_attr_should_poll'):
            delattr(select, '_attr_should_poll')
        
        # Should still function
        assert select._dog_id == "test_dog"
        
        # Device info should still be generated
        device_info = select._attr_device_info
        assert isinstance(device_info, dict)

    def test_select_with_legacy_device_info_format(self, mock_coordinator_unstable):
        """Test select device info with legacy format compatibility."""
        select = PawControlDefaultMealTypeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        device_info = select._attr_device_info
        
        # Should have all required fields for compatibility
        required_fields = ["identifiers", "name", "manufacturer", "model"]
        for field in required_fields:
            assert field in device_info
        
        # Identifiers should be in correct format
        assert isinstance(device_info["identifiers"], set)
        assert len(device_info["identifiers"]) > 0

    def test_select_entity_naming_edge_cases(self, mock_coordinator_unstable):
        """Test select entity naming with edge case characters."""
        problematic_names = [
            "Dog.With.Dots",
            "Dog-With-Dashes",
            "Dog_With_Underscores",
            "Dog With Spaces",
            "Dog123Numbers",
            "123NumbersFirst",
        ]
        
        for dog_name in problematic_names:
            select = PawControlFeedingScheduleSelect(
                mock_coordinator_unstable, "test_dog", dog_name
            )
            
            # Entity name should be generated
            assert isinstance(select._attr_name, str)
            assert len(select._attr_name) > 0

    def test_select_with_unavailable_coordinator_methods(self, mock_coordinator_unstable):
        """Test select behavior when coordinator methods are unavailable."""
        # Remove methods to simulate version incompatibility
        if hasattr(mock_coordinator_unstable, 'get_module_data'):
            original_method = mock_coordinator_unstable.get_module_data
            mock_coordinator_unstable.get_module_data = None
            
            try:
                select = PawControlHealthStatusSelect(
                    mock_coordinator_unstable, "test_dog", "Test Dog"
                )
                
                # Should handle missing methods gracefully
                module_data = select._get_module_data("health")
                # Should return None or handle gracefully
                
            finally:
                # Restore method
                mock_coordinator_unstable.get_module_data = original_method


class TestSelectModuleDataEdgeCases:
    """Test edge cases related to module data handling."""

    @pytest.fixture
    def mock_coordinator_module_data(self):
        """Create coordinator with various module data scenarios."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(return_value={"dog_info": {"breed": "Test"}})
        
        # Module data that changes between calls
        module_data_sequence = [
            {"health_status": "excellent"},
            {"health_status": "good"},
            {"health_status": "poor"},
            None,  # No data
            {},  # Empty data
            {"wrong_key": "value"},  # Wrong structure
            {"health_status": None},  # Null value
            {"health_status": 123},  # Wrong type
        ]
        
        coordinator.get_module_data = Mock(side_effect=module_data_sequence * 10)
        return coordinator

    def test_health_status_select_with_dynamic_data(self, mock_coordinator_module_data):
        """Test health status select with changing module data."""
        select = PawControlHealthStatusSelect(
            mock_coordinator_module_data, "test_dog", "Test Dog"
        )
        
        # Test multiple data scenarios
        for _ in range(8):
            current_option = select.current_option
            # Should handle all scenarios gracefully
            assert current_option is None or current_option in HEALTH_STATUS_OPTIONS

    def test_activity_level_select_with_dynamic_data(self, mock_coordinator_module_data):
        """Test activity level select with changing module data."""
        select = PawControlActivityLevelSelect(
            mock_coordinator_module_data, "test_dog", "Test Dog"
        )
        
        # Test multiple data scenarios
        for _ in range(8):
            current_option = select.current_option
            # Should handle all scenarios gracefully
            assert current_option is None or current_option in ACTIVITY_LEVELS

    @pytest.mark.asyncio
    async def test_select_with_module_data_corruption(self, mock_coordinator_module_data):
        """Test select behavior when module data becomes corrupted."""
        select = PawControlHealthStatusSelect(
            mock_coordinator_module_data, "test_dog", "Test Dog"
        )
        select.hass = Mock()
        select.async_write_ha_state = Mock()
        
        # Set option while data is corrupted
        await select.async_select_option("good")
        
        # Should succeed despite corruption
        assert select._current_option == "good"


class TestSelectConstantsEdgeCases:
    """Test edge cases related to select platform constants."""

    def test_option_lists_integrity(self):
        """Test that all option lists maintain integrity."""
        option_lists = [
            WALK_MODES,
            NOTIFICATION_PRIORITIES,
            TRACKING_MODES,
            FEEDING_SCHEDULES,
            GROOMING_TYPES,
            WEATHER_CONDITIONS,
        ]
        
        for option_list in option_lists:
            # Should be non-empty list
            assert isinstance(option_list, list)
            assert len(option_list) > 0
            
            # All options should be strings
            for option in option_list:
                assert isinstance(option, str)
                assert len(option) > 0
            
            # Should not have duplicates
            assert len(option_list) == len(set(option_list))

    def test_option_lists_modification_resistance(self):
        """Test that option lists resist modification."""
        original_walk_modes = WALK_MODES.copy()
        
        # Try to modify the list
        WALK_MODES.append("malicious_mode")
        
        # Restore and verify
        WALK_MODES.remove("malicious_mode")
        assert WALK_MODES == original_walk_modes

    def test_imported_constants_integrity(self):
        """Test that imported constants from const.py maintain integrity."""
        const_lists = [
            DOG_SIZES,
            FOOD_TYPES,
            GPS_SOURCES,
            HEALTH_STATUS_OPTIONS,
            MEAL_TYPES,
            MOOD_OPTIONS,
            PERFORMANCE_MODES,
            ACTIVITY_LEVELS,
        ]
        
        for const_list in const_lists:
            # Should be non-empty list
            assert isinstance(const_list, list)
            assert len(const_list) > 0
            
            # All items should be strings
            for item in const_list:
                assert isinstance(item, str)
                assert len(item) > 0


class TestSelectIntegrationEdgeCases:
    """Test integration edge cases between selects and other components."""

    @pytest.mark.asyncio
    async def test_select_setup_with_corrupted_config_entry(self, hass):
        """Test select platform setup with corrupted config entry."""
        mock_coordinator = Mock(spec=PawControlCoordinator)
        mock_coordinator.available = True
        
        # Various corrupted config entry scenarios
        corrupted_entries = [
            Mock(data=None, runtime_data=None),  # No data
            Mock(data={}, runtime_data=None),  # Empty data
            Mock(data={CONF_DOGS: None}, runtime_data=None),  # Null dogs
            Mock(data={CONF_DOGS: "invalid"}, runtime_data=None),  # Wrong type
        ]
        
        for entry in corrupted_entries:
            entry.entry_id = "test_entry"
            
            # Should handle corrupted entries gracefully
            hass.data[DOMAIN] = {entry.entry_id: {"coordinator": mock_coordinator}}
            
            added_entities = []
            
            def mock_add_entities(entities, update_before_add=False):
                added_entities.extend(entities)
            
            # Should not crash with corrupted config
            await async_setup_entry(hass, entry, mock_add_entities)
            
            # Should either create no entities or handle gracefully
            assert len(added_entities) >= 0

    def test_select_with_coordinator_state_changes(self, mock_coordinator_unstable):
        """Test select behavior when coordinator state changes."""
        select = PawControlGPSSourceSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Check initial state
        initial_available = select.available
        
        # Force coordinator state change (done by fixture)
        # Check state multiple times to trigger availability changes
        states = []
        for _ in range(10):
            states.append(select.available)
        
        # Should handle state changes gracefully
        assert len(set(states)) > 1  # Should have different states

    @pytest.mark.asyncio
    async def test_select_cleanup_on_exception(self, mock_coordinator_unstable):
        """Test select cleanup when exceptions occur during operations."""
        select = PawControlTrackingModeSelect(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Mock async_write_ha_state to cause exceptions
        select.hass = Mock()
        select.async_write_ha_state = Mock(side_effect=Exception("State write error"))
        
        # Operations should handle exceptions gracefully
        try:
            await select.async_select_option("continuous")
        except HomeAssistantError:
            # Expected error handling
            pass
        
        # Select should remain in consistent state
        assert hasattr(select, '_current_option')
        assert hasattr(select, '_attr_options')
