"""Edge case tests for PawControl switch platform.

Tests comprehensive edge cases, error scenarios, state management,
and performance characteristics of the switch platform.

Test Areas:
- State cache edge cases and TTL expiration
- Profile optimization with various module configurations
- Batching edge cases (empty, oversized, concurrent)
- Error handling and recovery scenarios
- Service integration failures
- Coordinator unavailability scenarios
- Switch type specific edge cases
- Performance under stress conditions
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.switch import (
    _async_add_entities_in_batches,
    async_setup_entry,
    OptimizedSwitchBase,
    PawControlMainPowerSwitch,
    PawControlDoNotDisturbSwitch,
    PawControlVisitorModeSwitch,
    PawControlModuleSwitch,
    PawControlFeatureSwitch,
    ProfileOptimizedSwitchFactory,
    BATCH_SIZE,
    BATCH_DELAY,
    MAX_CONCURRENT_BATCHES,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator for testing."""
    coordinator = MagicMock(spec=PawControlCoordinator)
    coordinator.available = True
    coordinator.config_entry = MagicMock()
    coordinator.get_dog_data.return_value = {
        "dog_info": {"dog_name": "TestDog", "dog_breed": "TestBreed"},
        "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
        "visitor_mode_active": False,
    }
    coordinator.async_request_selective_refresh = AsyncMock()
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


class TestStateCacheEdgeCases:
    """Test state cache edge cases and TTL behavior."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a base switch for testing."""
        return OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            switch_type="test_switch",
            icon="mdi:test",
            initial_state=False,
        )

    def test_cache_ttl_expiration(self, switch):
        """Test cache TTL expiration behavior."""
        # Mock time progression
        with patch("custom_components.pawcontrol.switch.dt_util") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.side_effect = [
                1000.0,  # Initial cache time
                1000.5,  # Within TTL (3 seconds)
                1004.0,  # Expired TTL
            ]
            
            # Set initial state and cache
            switch._is_on = True
            switch._update_cache(True)
            
            # First call - should use cache
            assert switch.is_on is True
            
            # Cache should still be valid
            assert switch.is_on is True
            
            # Cache should be expired, return stored state
            switch._is_on = False
            assert switch.is_on is False

    def test_cache_key_collision_resistance(self, switch):
        """Test cache handles similar keys correctly."""
        # Create switches with similar IDs
        switch1 = OptimizedSwitchBase(
            coordinator=switch.coordinator,
            dog_id="dog_1",
            dog_name="Dog 1",
            switch_type="power",
        )
        switch2 = OptimizedSwitchBase(
            coordinator=switch.coordinator,
            dog_id="dog_11",  # Similar ID that could cause collision
            dog_name="Dog 11",
            switch_type="ower",  # Similar type
        )
        
        # Set different states
        switch1._is_on = True
        switch1._update_cache(True)
        
        switch2._is_on = False
        switch2._update_cache(False)
        
        # Verify no cross-contamination
        assert switch1.is_on is True
        assert switch2.is_on is False

    def test_cache_memory_management(self, switch):
        """Test cache doesn't grow unbounded."""
        # Simulate many cache updates
        for i in range(1000):
            cache_key = f"dog_{i}_switch_{i}"
            switch._state_cache[cache_key] = (True, dt_util.utcnow().timestamp())
        
        # Verify cache has entries (implementation detail)
        assert len(switch._state_cache) > 0
        
        # Cache should handle large numbers of entries
        switch._update_cache(True)
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, switch):
        """Test cache thread safety with concurrent access."""
        async def toggle_switch():
            for _ in range(10):
                switch._is_on = not switch._is_on
                switch._update_cache(switch._is_on)
                await asyncio.sleep(0.001)
        
        # Run multiple concurrent operations
        await asyncio.gather(
            toggle_switch(),
            toggle_switch(),
            toggle_switch(),
        )
        
        # Cache should remain consistent
        cached_state = switch.is_on
        assert isinstance(cached_state, bool)


class TestProfileOptimizationEdgeCases:
    """Test profile optimization edge cases."""

    def test_empty_modules_configuration(self, mock_coordinator):
        """Test factory with no enabled modules."""
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            modules={}  # No modules enabled
        )
        
        # Should still create base switches
        assert len(switches) >= 2  # MainPower, DoNotDisturb
        switch_types = [s._switch_type for s in switches]
        assert "main_power" in switch_types
        assert "do_not_disturb" in switch_types

    def test_all_modules_disabled(self, mock_coordinator):
        """Test factory with all modules disabled."""
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            modules={
                MODULE_FEEDING: False,
                MODULE_GPS: False,
                MODULE_HEALTH: False,
                MODULE_WALK: False,
            }
        )
        
        # Should create base switches plus visitor mode (fallback)
        assert len(switches) >= 3
        switch_types = [s._switch_type for s in switches]
        assert "visitor_mode" in switch_types

    def test_unknown_module_handling(self, mock_coordinator):
        """Test factory gracefully handles unknown modules."""
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            modules={
                "unknown_module_1": True,
                "invalid_module": True,
                MODULE_FEEDING: True,
                "future_module": True,
            }
        )
        
        # Should create switches for known modules only
        switch_types = [s._switch_type for s in switches]
        
        # Known modules should be present
        assert "module_feeding" in switch_types
        
        # Unknown modules should be ignored gracefully
        unknown_switches = [s for s in switches if "unknown" in s._switch_type]
        assert len(unknown_switches) == 0

    def test_maximum_modules_enabled(self, mock_coordinator):
        """Test factory with all possible modules enabled."""
        all_modules = {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_WALK: True,
            "grooming": True,
            "medication": True,
            "training": True,
            "notifications": True,
            "visitor": True,
        }
        
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            modules=all_modules
        )
        
        # Should create many switches but stay reasonable
        assert len(switches) > 10  # Many switches
        assert len(switches) < 100  # Not excessive

    def test_module_configuration_edge_cases(self, mock_coordinator):
        """Test edge cases in module configuration."""
        # Test with None values
        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            modules={
                MODULE_FEEDING: None,  # None should be treated as False
                MODULE_GPS: True,
                MODULE_HEALTH: "",  # Empty string should be treated as False
                MODULE_WALK: 1,  # Truthy non-bool
            }
        )
        
        switch_types = [s._switch_type for s in switches]
        
        # Only GPS and WALK should be enabled
        assert "module_gps" in switch_types
        assert "module_walk" in switch_types
        assert "module_feeding" not in switch_types
        assert "module_health" not in switch_types


class TestBatchingEdgeCases:
    """Test entity batching edge cases."""

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
        
        entity = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="test",
            dog_name="Test",
            switch_type="test",
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
    async def test_oversized_batch(self, mock_coordinator):
        """Test batching with entities exceeding batch size."""
        add_entities_mock = Mock()
        
        # Create 25 entities (more than default batch size)
        entities = []
        for i in range(25):
            entity = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                switch_type="test",
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
    async def test_exact_batch_size_match(self, mock_coordinator):
        """Test batching when entity count exactly matches batch size."""
        add_entities_mock = Mock()
        
        # Create exactly 10 entities
        entities = []
        for i in range(10):
            entity = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                switch_type="test",
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
    async def test_batching_timing(self, mock_coordinator):
        """Test batching respects delay timing."""
        add_entities_mock = Mock()
        
        # Create entities requiring multiple batches
        entities = []
        for i in range(15):
            entity = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                switch_type="test",
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
    async def test_concurrent_batching_performance(self, mock_coordinator):
        """Test performance with concurrent batching operations."""
        add_entities_mock = Mock()
        
        async def batch_entities(entity_count: int):
            entities = []
            for i in range(entity_count):
                entity = OptimizedSwitchBase(
                    coordinator=mock_coordinator,
                    dog_id=f"dog_{i}",
                    dog_name=f"Dog {i}",
                    switch_type="test",
                )
                entities.append(entity)
            
            await _async_add_entities_in_batches(
                add_entities_mock,
                entities,
                batch_size=5,
                delay_between_batches=0.001,
            )
        
        # Run multiple batching operations concurrently
        start_time = dt_util.utcnow()
        
        await asyncio.gather(
            batch_entities(20),
            batch_entities(15),
            batch_entities(10),
        )
        
        end_time = dt_util.utcnow()
        
        # Should complete in reasonable time
        duration = (end_time - start_time).total_seconds()
        assert duration < 1.0  # Should complete quickly


class TestErrorHandlingEdgeCases:
    """Test error handling and recovery scenarios."""

    @pytest.fixture
    def switch(self, mock_coordinator):
        """Create a switch for error testing."""
        return PawControlMainPowerSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )

    @pytest.mark.asyncio
    async def test_turn_on_with_unavailable_coordinator(self, switch):
        """Test turn_on when coordinator is unavailable."""
        switch.coordinator.available = False
        
        # Should handle gracefully
        await switch.async_turn_on()
        
        # State should still be updated locally
        assert switch._is_on is True

    @pytest.mark.asyncio
    async def test_turn_off_with_service_failure(self, switch):
        """Test turn_off when underlying service fails."""
        # Mock service failure
        with patch.object(switch, '_async_set_state', side_effect=Exception("Service failed")):
            with pytest.raises(HomeAssistantError, match="Failed to turn off main_power"):
                await switch.async_turn_off()
        
        # State should not change on failure
        assert switch._is_on is False  # Initial state

    @pytest.mark.asyncio
    async def test_turn_on_with_partial_failure(self, switch):
        """Test turn_on with partial failure scenarios."""
        # Mock data manager unavailable
        switch.hass.data = {DOMAIN: {switch.coordinator.config_entry.entry_id: {}}}
        
        # Should handle missing data manager gracefully
        await switch.async_turn_on()
        assert switch._is_on is True

    @pytest.mark.asyncio
    async def test_state_restoration_with_invalid_data(self, switch):
        """Test state restoration with corrupted/invalid data."""
        # Mock corrupted state
        mock_state = Mock()
        mock_state.state = "invalid_state"  # Not "on" or "off"
        
        with patch.object(switch, 'async_get_last_state', return_value=mock_state):
            await switch.async_added_to_hass()
        
        # Should use default state
        assert switch._is_on is False

    @pytest.mark.asyncio
    async def test_state_restoration_with_none_state(self, switch):
        """Test state restoration when no previous state exists."""
        with patch.object(switch, 'async_get_last_state', return_value=None):
            await switch.async_added_to_hass()
        
        # Should use initial state
        assert switch._is_on is False

    def test_availability_with_missing_dog_data(self, switch):
        """Test availability when dog data is missing."""
        switch.coordinator.get_dog_data.return_value = None
        
        assert switch.available is False

    def test_availability_with_coordinator_unavailable(self, switch):
        """Test availability when coordinator is unavailable."""
        switch.coordinator.available = False
        
        assert switch.available is False

    def test_extra_attributes_with_missing_data(self, switch):
        """Test extra attributes when data is missing."""
        switch.coordinator.get_dog_data.return_value = None
        
        attrs = switch.extra_state_attributes
        
        # Should have basic attributes
        assert "dog_id" in attrs
        assert "dog_name" in attrs
        # Should not have module information
        assert "enabled_modules" not in attrs


class TestSwitchTypeSpecificEdgeCases:
    """Test specific edge cases for different switch types."""

    @pytest.mark.asyncio
    async def test_visitor_mode_switch_state_from_data(self, mock_coordinator):
        """Test visitor mode switch reads state from coordinator data."""
        switch = PawControlVisitorModeSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Test with visitor mode active in data
        mock_coordinator.get_dog_data.return_value = {
            "visitor_mode_active": True
        }
        
        assert switch.is_on is True
        
        # Test with visitor mode inactive
        mock_coordinator.get_dog_data.return_value = {
            "visitor_mode_active": False
        }
        
        assert switch.is_on is False

    @pytest.mark.asyncio
    async def test_visitor_mode_switch_missing_data(self, mock_coordinator):
        """Test visitor mode switch with missing data."""
        switch = PawControlVisitorModeSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Test with no data
        mock_coordinator.get_dog_data.return_value = None
        
        assert switch.is_on is False  # Should fall back to stored state

    @pytest.mark.asyncio
    async def test_module_switch_config_update_failure(self, mock_coordinator):
        """Test module switch when config update fails."""
        switch = PawControlModuleSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            module_id=MODULE_FEEDING,
            module_name="Feeding",
            icon="mdi:food",
            initial_state=True,
        )
        
        # Mock config entry update failure
        with patch.object(switch.hass.config_entries, 'async_update_entry', side_effect=Exception("Update failed")):
            await switch._async_set_state(False)
        
        # Should handle failure gracefully (logged but not raised)

    @pytest.mark.asyncio
    async def test_feature_switch_specific_handlers(self, mock_coordinator):
        """Test feature switch with specific feature handlers."""
        switch = PawControlFeatureSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            feature_id="gps_tracking",
            feature_name="GPS Tracking",
            icon="mdi:gps",
            module=MODULE_GPS,
        )
        
        # Mock missing data manager
        switch.hass.data = {DOMAIN: {switch.coordinator.config_entry.entry_id: {}}}
        
        # Should handle missing data manager gracefully
        await switch._async_set_state(True)

    def test_feature_switch_extra_attributes(self, mock_coordinator):
        """Test feature switch extra attributes."""
        switch = PawControlFeatureSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            feature_id="feeding_schedule",
            feature_name="Feeding Schedule",
            icon="mdi:calendar",
            module=MODULE_FEEDING,
        )
        
        attrs = switch.extra_state_attributes
        
        assert attrs["feature_id"] == "feeding_schedule"
        assert attrs["parent_module"] == MODULE_FEEDING
        assert attrs["feature_name"] == "Feeding Schedule"

    @pytest.mark.asyncio
    async def test_dnd_switch_missing_notification_manager(self, mock_coordinator):
        """Test DND switch when notification manager is missing."""
        switch = PawControlDoNotDisturbSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
        )
        
        # Mock missing notification manager
        switch.hass.data = {DOMAIN: {switch.coordinator.config_entry.entry_id: {}}}
        
        # Should handle gracefully
        await switch._async_set_state(True)


class TestAsyncSetupEntryEdgeCases:
    """Test async_setup_entry edge cases."""

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
        
        # Should create entities
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
    async def test_setup_performance_with_many_dogs(self, hass: HomeAssistant, mock_entry, mock_coordinator):
        """Test setup_entry performance with many dogs."""
        # Create many dogs to test performance
        many_dogs = []
        for i in range(50):  # 50 dogs
            many_dogs.append({
                CONF_DOG_ID: f"dog_{i}",
                CONF_DOG_NAME: f"Dog {i}",
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
        
        # Should use batching
        assert add_entities_mock.call_count > 1  # Multiple batches


class TestPerformanceAndStressScenarios:
    """Test performance characteristics and stress scenarios."""

    @pytest.mark.asyncio
    async def test_rapid_state_changes(self, mock_coordinator):
        """Test rapid state changes don't cause issues."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            switch_type="test",
        )
        
        # Rapid state changes
        for i in range(100):
            switch._is_on = i % 2 == 0
            switch._update_cache(switch._is_on)
            assert isinstance(switch.is_on, bool)

    @pytest.mark.asyncio
    async def test_concurrent_switch_operations(self, mock_coordinator):
        """Test concurrent switch operations."""
        switches = []
        for i in range(10):
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                switch_type="test",
            )
            switches.append(switch)
        
        async def toggle_switch(switch):
            for _ in range(10):
                await switch.async_turn_on()
                await asyncio.sleep(0.001)
                await switch.async_turn_off()
                await asyncio.sleep(0.001)
        
        # Run concurrent operations
        await asyncio.gather(*[toggle_switch(s) for s in switches])
        
        # All switches should be in a valid state
        for switch in switches:
            assert isinstance(switch.is_on, bool)

    def test_memory_usage_with_many_switches(self, mock_coordinator):
        """Test memory usage doesn't grow excessively with many switches."""
        switches = []
        
        # Create many switches
        for i in range(500):
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"dog_{i}",
                dog_name=f"Dog {i}",
                switch_type="test",
            )
            switches.append(switch)
        
        # Each switch should be independent
        for i, switch in enumerate(switches[:10]):  # Test first 10
            switch._is_on = i % 2 == 0
            switch._update_cache(switch._is_on)
        
        # Verify states are correct
        for i, switch in enumerate(switches[:10]):
            expected_state = i % 2 == 0
            assert switch.is_on == expected_state

    @pytest.mark.asyncio
    async def test_stress_test_profile_factory(self, mock_coordinator):
        """Stress test profile factory with complex configurations."""
        complex_modules = {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_WALK: True,
            "grooming": True,
            "medication": True,
            "training": True,
            "notifications": True,
        }
        
        # Create switches for many dogs with complex configurations
        all_switches = []
        for i in range(20):  # 20 dogs
            switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
                coordinator=mock_coordinator,
                dog_id=f"stress_dog_{i}",
                dog_name=f"Stress Dog {i}",
                modules=complex_modules,
            )
            all_switches.extend(switches)
        
        # Should create reasonable number of switches
        assert len(all_switches) > 40  # At least 2 per dog
        assert len(all_switches) < 1000  # Not excessive
        
        # All switches should be valid
        for switch in all_switches:
            assert hasattr(switch, '_dog_id')
            assert hasattr(switch, '_switch_type')
            assert hasattr(switch, 'unique_id')


if __name__ == "__main__":
    pytest.main([__file__])
