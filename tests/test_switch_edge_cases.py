"""Comprehensive edge case tests for PawControl switch platform.

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
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceNotFound
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.switch import (
    ProfileOptimizedSwitchFactory,
    OptimizedSwitchBase,
    PawControlMainPowerSwitch,
    PawControlDoNotDisturbSwitch,
    PawControlVisitorModeSwitch,
    PawControlModuleSwitch,
    PawControlFeatureSwitch,
    async_setup_entry,
    _async_add_entities_in_batches,
    BATCH_SIZE,
    BATCH_DELAY,
    MAX_CONCURRENT_BATCHES,
)
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
    MODULE_GROOMING,
    MODULE_MEDICATION,
    MODULE_TRAINING,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator


class TestSwitchEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.fixture
    def mock_coordinator_unstable(self):
        """Create a coordinator that becomes unavailable intermittently."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator._available_state = True
        
        def toggle_availability():
            coordinator._available_state = not coordinator._available_state
            return coordinator._available_state
        
        coordinator.available = property(lambda self: toggle_availability())
        coordinator.get_dog_data = Mock(return_value={"modules": {MODULE_FEEDING: True}})
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        coordinator.async_request_selective_refresh = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_coordinator_corrupted_data(self):
        """Create a coordinator returning corrupted/invalid data."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        
        # Return various types of corrupted data
        corrupted_data_sequence = [
            None,  # Missing data
            {"modules": None},  # Null modules
            {"modules": "invalid_type"},  # Wrong type
            {"modules": {}},  # Empty modules
            {"modules": {MODULE_FEEDING: "not_bool"}},  # Wrong value type
            {"visitor_mode_active": "not_bool"},  # Wrong visitor mode type
            {},  # Missing keys
        ]
        
        coordinator.get_dog_data = Mock(side_effect=corrupted_data_sequence * 10)
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return coordinator

    def test_switch_with_unicode_dog_names(self, mock_coordinator_unstable):
        """Test switch creation with unicode and special characters in dog names."""
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
        ]
        
        for dog_name in unicode_names:
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, "test_dog", dog_name
            )
            
            # Should handle all unicode gracefully
            assert switch._dog_name == dog_name
            assert isinstance(switch._attr_name, str)
            assert switch._attr_unique_id.startswith("pawcontrol_")

    def test_switch_with_extremely_long_identifiers(self, mock_coordinator_unstable):
        """Test switches with very long dog IDs and names."""
        long_dog_id = "a" * 1000  # Very long ID
        long_dog_name = "B" * 500  # Very long name
        
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, long_dog_id, long_dog_name
        )
        
        assert switch._dog_id == long_dog_id
        assert switch._dog_name == long_dog_name
        # Unique ID should be created without issues
        assert len(switch._attr_unique_id) > 1000

    def test_switch_cache_race_condition(self, mock_coordinator_unstable):
        """Test cache behavior under race conditions."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Simulate concurrent cache access
        def access_cache():
            for _ in range(100):
                switch.is_on  # Read state
                switch._update_cache(not switch._is_on)  # Update cache
                time.sleep(0.001)  # Small delay
        
        threads = [threading.Thread(target=access_cache) for _ in range(5)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Cache should remain intact
        assert isinstance(switch._state_cache, dict)

    def test_switch_cache_memory_pressure(self, mock_coordinator_unstable):
        """Test cache behavior under memory pressure."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Fill cache with many entries
        for i in range(10000):
            cache_key = f"dog_{i}_switch_type"
            switch._state_cache[cache_key] = (True, time.time())
        
        # Should handle large cache
        original_state = switch.is_on
        
        # Force garbage collection
        gc.collect()
        
        # Should still work
        assert switch.is_on == original_state

    @pytest.mark.asyncio
    async def test_switch_corrupted_data_handling(self, mock_coordinator_corrupted_data):
        """Test switch behavior with corrupted coordinator data."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_corrupted_data, "test_dog", "Test Dog"
        )
        
        # Should handle all corrupted data gracefully
        for _ in range(7):  # Test all corrupted data types
            try:
                dog_data = switch._get_dog_data()
                # Should either return valid data or None
                assert dog_data is None or isinstance(dog_data, dict)
                
                # Extra state attributes should not crash
                attrs = switch.extra_state_attributes
                assert isinstance(attrs, dict)
                
                # Availability should be deterministic
                available = switch.available
                assert isinstance(available, bool)
                
            except Exception as e:
                pytest.fail(f"Switch should handle corrupted data gracefully: {e}")

    @pytest.mark.asyncio
    async def test_switch_coordinator_timeout(self, mock_coordinator_unstable):
        """Test switch behavior when coordinator operations timeout."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Mock coordinator methods to timeout
        mock_coordinator_unstable.async_request_selective_refresh = AsyncMock(
            side_effect=asyncio.TimeoutError("Coordinator timeout")
        )
        
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {"data_manager": AsyncMock()}
            }
        }
        switch.hass = hass
        
        # Should handle timeout gracefully
        await switch._async_set_state(True)
        # Should not raise exception despite timeout

    @pytest.mark.asyncio
    async def test_switch_service_call_failures(self, mock_coordinator_unstable):
        """Test switch behavior when Home Assistant service calls fail."""
        switch = PawControlVisitorModeSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        hass = Mock()
        hass.services = Mock()
        
        # Test various service call failures
        service_errors = [
            ServiceNotFound("Service not found"),
            HomeAssistantError("Service error"),
            asyncio.TimeoutError("Service timeout"),
            Exception("Unexpected error"),
        ]
        
        for error in service_errors:
            hass.services.async_call = AsyncMock(side_effect=error)
            switch.hass = hass
            
            # Should handle service failures gracefully
            await switch._async_set_state(True)
            # Should not propagate exception

    @pytest.mark.asyncio
    async def test_switch_config_entry_corruption(self, mock_coordinator_unstable):
        """Test switch behavior with corrupted config entry data."""
        switch = PawControlModuleSwitch(
            mock_coordinator_unstable,
            "test_dog",
            "Test Dog",
            MODULE_FEEDING,
            "Feeding Tracking",
            "mdi:food",
            True,
        )
        
        hass = Mock()
        hass.config_entries = Mock()
        hass.config_entries.async_update_entry = Mock(side_effect=Exception("Config corruption"))
        switch.hass = hass
        
        # Various corrupted config data scenarios
        corrupted_configs = [
            None,  # No data
            {},  # Empty data
            {"dogs": None},  # Null dogs
            {"dogs": "invalid"},  # Wrong type
            {"dogs": []},  # Empty dogs list
            {"dogs": [{}]},  # Dog without required fields
            {"dogs": [{"dog_id": "different_dog"}]},  # Wrong dog
        ]
        
        for config_data in corrupted_configs:
            mock_coordinator_unstable.config_entry.data = config_data
            
            # Should handle config corruption gracefully
            await switch._async_set_state(True)
            # Should not crash despite corruption

    def test_switch_device_info_edge_cases(self, mock_coordinator_unstable):
        """Test device info generation with edge case inputs."""
        edge_case_inputs = [
            ("", ""),  # Empty strings
            (None, None),  # None values
            ("dog\nwith\nnewlines", "Name\nWith\nLines"),
            ("dog/with/slashes", "Name/With/Slashes"),
            ("dog with spaces", "Name With Spaces"),
        ]
        
        for dog_id, dog_name in edge_case_inputs:
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, dog_id, dog_name
            )
            
            device_info = switch._attr_device_info
            
            # Should always generate valid device info
            assert isinstance(device_info, dict)
            assert "identifiers" in device_info
            assert "name" in device_info
            assert "manufacturer" in device_info

    @pytest.mark.asyncio
    async def test_switch_state_persistence_edge_cases(self, hass):
        """Test state restoration with edge case stored states."""
        switch = PawControlMainPowerSwitch(
            Mock(), "test_dog", "Test Dog"
        )
        switch.hass = hass
        
        # Test various stored state scenarios
        edge_case_states = [
            None,  # No previous state
            Mock(state="invalid"),  # Invalid state value
            Mock(state=None),  # None state
            Mock(state=""),  # Empty state
            Mock(state="unknown"),  # Unknown state
        ]
        
        for mock_state in edge_case_states:
            with patch.object(switch, "async_get_last_state", return_value=mock_state):
                await switch.async_added_to_hass()
                
                # Should handle all edge cases gracefully
                assert isinstance(switch._is_on, bool)

    @pytest.mark.asyncio
    async def test_feature_switch_unknown_features(self, mock_coordinator_unstable):
        """Test feature switches with unknown/invalid feature types."""
        unknown_features = [
            "nonexistent_feature",
            "",  # Empty feature
            None,  # None feature
            "feature_with_unicode_🎯",
            "feature/with/slashes",
            "feature with spaces",
            "UPPERCASE_FEATURE",
        ]
        
        hass = Mock()
        hass.data = {DOMAIN: {"test_entry": {"data_manager": AsyncMock()}}}
        
        for feature_id in unknown_features:
            switch = PawControlFeatureSwitch(
                mock_coordinator_unstable,
                "test_dog",
                "Test Dog",
                feature_id,
                "Unknown Feature",
                "mdi:help",
                "unknown_module",
            )
            switch.hass = hass
            
            # Should handle unknown features gracefully
            await switch._async_set_state(True)
            # Should not crash for unknown features

    @pytest.mark.asyncio
    async def test_batch_addition_memory_stress(self):
        """Test batch entity addition under memory stress."""
        # Create many entities to stress test batching
        entities = [Mock(spec=OptimizedSwitchBase) for _ in range(1000)]
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

    @pytest.mark.asyncio
    async def test_concurrent_switch_operations(self, mock_coordinator_unstable):
        """Test concurrent switch state operations."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        hass = Mock()
        hass.data = {DOMAIN: {"test_entry": {"data_manager": AsyncMock()}}}
        switch.hass = hass
        switch.async_write_ha_state = Mock()
        
        # Create many concurrent operations
        async def toggle_switch():
            for _ in range(50):
                await switch.async_turn_on()
                await asyncio.sleep(0.001)
                await switch.async_turn_off()
                await asyncio.sleep(0.001)
        
        # Run multiple concurrent toggles
        tasks = [toggle_switch() for _ in range(5)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent operations without corruption
        assert isinstance(switch._is_on, bool)

    def test_switch_factory_stress_test(self, mock_coordinator_unstable):
        """Test ProfileOptimizedSwitchFactory under stress conditions."""
        # Test with maximum modules and complex configurations
        max_modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_NOTIFICATIONS: True,
            MODULE_VISITOR: True,
            MODULE_GROOMING: True,
            MODULE_MEDICATION: True,
            MODULE_TRAINING: True,
        }
        
        # Create switches for many dogs simultaneously
        all_switches = []
        for i in range(100):  # Stress test with 100 dogs
            switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
                mock_coordinator_unstable, f"dog_{i}", f"Dog {i}", max_modules
            )
            all_switches.extend(switches)
        
        # Should create many switches without issues
        assert len(all_switches) > 1000  # Should create many switches
        
        # All switches should be valid
        for switch in all_switches[:10]:  # Check first 10
            assert isinstance(switch, OptimizedSwitchBase)
            assert hasattr(switch, '_dog_id')
            assert hasattr(switch, '_dog_name')

    @pytest.mark.asyncio
    async def test_switch_cleanup_on_exception(self, mock_coordinator_unstable):
        """Test switch cleanup when exceptions occur during operations."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Mock hass.data to cause exceptions
        hass = Mock()
        hass.data = {DOMAIN: {"wrong_entry": {}}}  # Wrong entry ID
        switch.hass = hass
        
        original_cache_size = len(switch._state_cache)
        
        # Operations should fail but not corrupt state
        await switch._async_set_state(True)
        
        # Cache should remain intact
        assert len(switch._state_cache) >= original_cache_size

    def test_switch_attribute_access_edge_cases(self, mock_coordinator_unstable):
        """Test switch attribute access with missing/corrupted attributes."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Corrupt internal attributes
        original_dog_id = switch._dog_id
        switch._dog_id = None
        
        # Should handle corrupted attributes gracefully
        try:
            attrs = switch.extra_state_attributes
            assert isinstance(attrs, dict)
        except Exception:
            pytest.fail("Should handle corrupted attributes gracefully")
        finally:
            # Restore for cleanup
            switch._dog_id = original_dog_id

    @pytest.mark.asyncio
    async def test_switch_hass_unavailable_scenarios(self, mock_coordinator_unstable):
        """Test switch behavior when Home Assistant is unavailable/shutting down."""
        switch = PawControlMainPowerSwitch(
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
            switch.hass = hass_state
            
            # Should handle unavailable hass gracefully
            await switch._async_set_state(True)
            # Should not crash

    def test_switch_entity_category_edge_cases(self, mock_coordinator_unstable):
        """Test switch entity category assignment with edge cases."""
        # Test with all possible entity categories
        categories = [
            None,
            EntityCategory.CONFIG,
            EntityCategory.DIAGNOSTIC,
        ]
        
        for category in categories:
            switch = OptimizedSwitchBase(
                mock_coordinator_unstable,
                "test_dog",
                "Test Dog",
                "test_switch",
                entity_category=category,
            )
            
            assert switch._attr_entity_category == category

    @pytest.mark.asyncio
    async def test_switch_performance_degradation(self, mock_coordinator_unstable):
        """Test switch performance under degraded conditions."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Simulate slow coordinator
        slow_coordinator = Mock(spec=PawControlCoordinator)
        slow_coordinator.available = True
        slow_coordinator.get_dog_data = Mock(
            side_effect=lambda: time.sleep(0.1) or {"modules": {}}
        )
        switch.coordinator = slow_coordinator
        
        start_time = time.time()
        
        # Multiple operations should still complete
        for _ in range(5):
            switch.is_on  # This should use caching to improve performance
        
        end_time = time.time()
        
        # Should complete reasonably quickly due to caching
        assert end_time - start_time < 1.0  # Less than 1 second total

    @pytest.mark.asyncio
    async def test_switch_resource_exhaustion(self, mock_coordinator_unstable):
        """Test switch behavior under resource exhaustion."""
        switches = []
        
        # Create many switches to exhaust resources
        try:
            for i in range(10000):
                switch = PawControlMainPowerSwitch(
                    mock_coordinator_unstable, f"dog_{i}", f"Dog {i}"
                )
                switches.append(switch)
        except MemoryError:
            # Expected under extreme conditions
            pass
        
        # Should have created some switches
        assert len(switches) > 0
        
        # First switch should still be functional
        if switches:
            assert switches[0]._dog_id == "dog_0"

    def test_switch_with_malformed_modules(self, mock_coordinator_unstable):
        """Test switch creation with malformed module configurations."""
        malformed_modules = [
            None,  # None modules
            "not_a_dict",  # Wrong type
            [],  # List instead of dict
            {None: True},  # None key
            {"": True},  # Empty key
            {MODULE_FEEDING: None},  # None value
            {MODULE_FEEDING: "not_bool"},  # Wrong value type
            {MODULE_FEEDING: []},  # List value
        ]
        
        for modules in malformed_modules:
            try:
                switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
                    mock_coordinator_unstable, "test_dog", "Test Dog", modules
                )
                
                # Should create at least base switches
                assert len(switches) >= 2
                
                # All switches should be valid
                for switch in switches:
                    assert isinstance(switch, OptimizedSwitchBase)
                    
            except Exception as e:
                pytest.fail(f"Should handle malformed modules gracefully: {e}")


class TestSwitchPerformanceEdgeCases:
    """Test performance-related edge cases."""

    @pytest.mark.asyncio
    async def test_rapid_state_changes(self, mock_coordinator_unstable):
        """Test switch behavior with rapid state changes."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        hass = Mock()
        hass.data = {DOMAIN: {"test_entry": {"data_manager": AsyncMock()}}}
        switch.hass = hass
        switch.async_write_ha_state = Mock()
        
        # Rapid state changes
        for _ in range(1000):
            await switch.async_turn_on()
            await switch.async_turn_off()
        
        # Should remain consistent
        assert isinstance(switch._is_on, bool)

    def test_cache_performance_edge_cases(self, mock_coordinator_unstable):
        """Test cache performance under edge conditions."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Test cache with expired entries
        now = dt_util.utcnow().timestamp()
        old_time = now - 3600  # 1 hour ago
        
        # Fill cache with old entries
        for i in range(1000):
            cache_key = f"old_entry_{i}"
            switch._state_cache[cache_key] = (True, old_time)
        
        # New access should still work efficiently
        start_time = time.time()
        for _ in range(100):
            switch.is_on
        end_time = time.time()
        
        # Should complete quickly despite large cache
        assert end_time - start_time < 1.0

    @pytest.mark.asyncio
    async def test_batch_addition_extreme_conditions(self):
        """Test batch addition under extreme conditions."""
        # Test with extreme batch parameters
        entities = [Mock(spec=OptimizedSwitchBase) for _ in range(10)]
        added_entities = []
        
        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)
        
        # Test with zero delay and single entity batches
        await _async_add_entities_in_batches(
            mock_add_entities, entities, batch_size=1, delay_between_batches=0
        )
        
        assert len(added_entities) == 10

    def test_memory_usage_optimization(self, mock_coordinator_unstable):
        """Test memory usage patterns of switches."""
        import sys
        
        # Create switches and measure memory impact
        switches = []
        initial_objects = len(gc.get_objects())
        
        for i in range(100):
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, f"dog_{i}", f"Dog {i}"
            )
            switches.append(switch)
        
        final_objects = len(gc.get_objects())
        
        # Clean up
        switches.clear()
        gc.collect()
        
        cleanup_objects = len(gc.get_objects())
        
        # Memory should be reasonable and cleanable
        objects_created = final_objects - initial_objects
        objects_cleaned = final_objects - cleanup_objects
        
        assert objects_created > 0  # Should create objects
        assert objects_cleaned > 0  # Should clean up objects


class TestSwitchSecurityEdgeCases:
    """Test security-related edge cases."""

    def test_switch_input_sanitization(self, mock_coordinator_unstable):
        """Test switch behavior with potentially malicious inputs."""
        malicious_inputs = [
            "'; DROP TABLE dogs; --",  # SQL injection attempt
            "<script>alert('xss')</script>",  # XSS attempt
            "../../../etc/passwd",  # Path traversal
            "\x00\x01\x02",  # Control characters
            "A" * 100000,  # Extremely long input
        ]
        
        for malicious_input in malicious_inputs:
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, malicious_input, malicious_input
            )
            
            # Should handle malicious inputs safely
            assert switch._dog_id == malicious_input
            assert switch._dog_name == malicious_input
            
            # Should not cause system issues
            device_info = switch._attr_device_info
            assert isinstance(device_info, dict)

    @pytest.mark.asyncio
    async def test_switch_service_call_injection(self, mock_coordinator_unstable):
        """Test switch resistance to service call injection."""
        switch = PawControlVisitorModeSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        hass = Mock()
        service_calls = []
        
        def capture_service_call(domain, service, data, **kwargs):
            service_calls.append((domain, service, data))
        
        hass.services = Mock()
        hass.services.async_call = AsyncMock(side_effect=capture_service_call)
        switch.hass = hass
        
        await switch._async_set_state(True)
        
        # Should only make expected service calls
        assert len(service_calls) == 1
        domain, service, data = service_calls[0]
        assert domain == DOMAIN
        assert service == "set_visitor_mode"
        assert isinstance(data, dict)

    def test_switch_data_isolation(self, mock_coordinator_unstable):
        """Test that switch data is properly isolated between instances."""
        switch1 = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "dog1", "Dog 1"
        )
        switch2 = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "dog2", "Dog 2"
        )
        
        # Modify one switch's cache
        switch1._update_cache(True)
        
        # Other switch should be unaffected
        switch2._update_cache(False)
        
        # Caches should be independent
        cache1_keys = set(switch1._state_cache.keys())
        cache2_keys = set(switch2._state_cache.keys())
        
        # Should have different cache keys
        assert cache1_keys != cache2_keys


class TestSwitchCompatibilityEdgeCases:
    """Test compatibility edge cases with different HA versions and configurations."""

    def test_switch_with_missing_attributes(self, mock_coordinator_unstable):
        """Test switch behavior when Home Assistant attributes are missing."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        # Remove some attributes to simulate version differences
        if hasattr(switch, '_attr_should_poll'):
            delattr(switch, '_attr_should_poll')
        
        # Should still function
        assert switch._dog_id == "test_dog"
        
        # Device info should still be generated
        device_info = switch._attr_device_info
        assert isinstance(device_info, dict)

    def test_switch_with_legacy_device_info_format(self, mock_coordinator_unstable):
        """Test switch device info with legacy format compatibility."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unstable, "test_dog", "Test Dog"
        )
        
        device_info = switch._attr_device_info
        
        # Should have all required fields for compatibility
        required_fields = ["identifiers", "name", "manufacturer", "model"]
        for field in required_fields:
            assert field in device_info
        
        # Identifiers should be in correct format
        assert isinstance(device_info["identifiers"], set)
        assert len(device_info["identifiers"]) > 0

    @pytest.mark.asyncio
    async def test_switch_with_unavailable_config_entry(self, mock_coordinator_unstable):
        """Test switch behavior when config entry becomes unavailable."""
        switch = PawControlModuleSwitch(
            mock_coordinator_unstable,
            "test_dog",
            "Test Dog",
            MODULE_FEEDING,
            "Feeding",
            "mdi:food",
            True,
        )
        
        # Simulate config entry becoming None
        mock_coordinator_unstable.config_entry = None
        
        hass = Mock()
        hass.config_entries = Mock()
        switch.hass = hass
        
        # Should handle missing config entry gracefully
        await switch._async_set_state(True)

    def test_switch_unique_id_collision_handling(self, mock_coordinator_unstable):
        """Test switch behavior with potential unique ID collisions."""
        # Create switches that might have similar unique IDs
        switches = []
        
        similar_ids = [
            ("dog_1", "Dog 1"),
            ("dog_1", "Dog 1 "),  # Trailing space
            ("dog-1", "Dog-1"),   # Different separator
            ("dog1", "Dog1"),     # No separator
        ]
        
        for dog_id, dog_name in similar_ids:
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, dog_id, dog_name
            )
            switches.append(switch)
        
        # All switches should have unique IDs
        unique_ids = [switch._attr_unique_id for switch in switches]
        assert len(set(unique_ids)) == len(unique_ids)

    def test_switch_entity_naming_edge_cases(self, mock_coordinator_unstable):
        """Test switch entity naming with edge case characters."""
        problematic_names = [
            "Dog.With.Dots",
            "Dog-With-Dashes",
            "Dog_With_Underscores",
            "Dog With Spaces",
            "Dog123Numbers",
            "123NumbersFirst",
        ]
        
        for dog_name in problematic_names:
            switch = PawControlMainPowerSwitch(
                mock_coordinator_unstable, "test_dog", dog_name
            )
            
            # Entity name should be generated
            assert isinstance(switch._attr_name, str)
            assert len(switch._attr_name) > 0
