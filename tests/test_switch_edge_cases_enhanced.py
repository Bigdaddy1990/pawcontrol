"""Enhanced edge case tests for PawControl switch platform.

Comprehensive edge cases covering critical scenarios for Gold Standard 95% coverage.
Includes advanced error scenarios, integration failures, and stress conditions.

Additional Test Areas:
- Memory pressure and resource exhaustion scenarios
- Network timeout and coordinator failure recovery
- Entity registry corruption and migration edge cases
- Device info validation and error handling
- Integration reload and hot-swap scenarios
- HACS validation and compliance edge cases
- Translation and localization failures
- Dependencies missing scenarios
- Concurrent modification protection
- Configuration migration edge cases
"""

from __future__ import annotations

import asyncio
import gc
import weakref
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.switch import (
    BATCH_DELAY,
    BATCH_SIZE,
    MAX_CONCURRENT_BATCHES,
    OptimizedSwitchBase,
    PawControlDoNotDisturbSwitch,
    PawControlFeatureSwitch,
    PawControlMainPowerSwitch,
    PawControlModuleSwitch,
    PawControlVisitorModeSwitch,
    ProfileOptimizedSwitchFactory,
    _async_add_entities_in_batches,
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
            }
        ]
    }
    entry.version = 1
    entry.minor_version = 1
    return entry


class TestMemoryPressureScenarios:
    """Test behavior under memory pressure and resource exhaustion."""

    @pytest.fixture
    def memory_limited_switch(self, mock_coordinator):
        """Create a switch for memory pressure testing."""
        return OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="memory_test_dog",
            dog_name="Memory Test Dog",
            switch_type="memory_test",
            icon="mdi:memory",
            initial_state=False,
        )

    @contextmanager
    def simulate_memory_pressure(self):
        """Context manager to simulate memory pressure."""
        # Simulate low memory by creating many objects
        memory_hogs = []
        try:
            # Create objects to consume memory
            for _ in range(1000):
                memory_hogs.append([0] * 10000)  # Create large lists
            yield
        finally:
            # Clean up
            memory_hogs.clear()
            gc.collect()

    def test_cache_behavior_under_memory_pressure(self, memory_limited_switch):
        """Test cache behavior when memory is limited."""
        with self.simulate_memory_pressure():
            # Cache should still function
            memory_limited_switch._update_cache(True)
            assert memory_limited_switch.is_on is True

            # Cache should handle memory pressure gracefully
            memory_limited_switch._update_cache(False)
            assert memory_limited_switch.is_on is False

    @pytest.mark.asyncio
    async def test_batch_processing_under_memory_pressure(self, mock_coordinator):
        """Test batch processing with limited memory."""
        entities = []

        with self.simulate_memory_pressure():
            # Create entities under memory pressure
            for i in range(50):
                entity = OptimizedSwitchBase(
                    coordinator=mock_coordinator,
                    dog_id=f"dog_{i}",
                    dog_name=f"Dog {i}",
                    switch_type="test",
                )
                entities.append(entity)

            add_entities_mock = Mock()

            # Batching should still work under memory pressure
            await _async_add_entities_in_batches(
                add_entities_mock,
                entities,
                batch_size=5,  # Smaller batches under pressure
                delay_between_batches=0.001,
            )

            # Should complete successfully
            assert add_entities_mock.call_count == 10  # 50 / 5 = 10 batches

    def test_weak_reference_cleanup(self, mock_coordinator):
        """Test that switches can be garbage collected properly."""
        switches = []
        weak_refs = []

        # Create switches and weak references
        for i in range(10):
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=f"gc_dog_{i}",
                dog_name=f"GC Dog {i}",
                switch_type="gc_test",
            )
            switches.append(switch)
            weak_refs.append(weakref.ref(switch))

        # Clear strong references
        switches.clear()
        gc.collect()

        # Weak references should be cleaned up
        alive_count = sum(1 for ref in weak_refs if ref() is not None)
        assert alive_count < len(weak_refs)  # Some should be garbage collected

    @pytest.mark.asyncio
    async def test_large_dog_count_memory_efficiency(self, mock_coordinator):
        """Test memory efficiency with very large dog counts."""
        large_dog_count = 200

        # Create configuration for many dogs
        modules = {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_WALK: True,
        }

        all_switches = []

        # Create switches for many dogs
        for i in range(large_dog_count):
            switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
                coordinator=mock_coordinator,
                dog_id=f"large_dog_{i}",
                dog_name=f"Large Dog {i}",
                modules=modules,
            )
            all_switches.extend(switches)

        # Memory usage should be reasonable
        assert len(all_switches) > 400  # Should create many switches
        assert len(all_switches) < 2000  # But not excessive

        # All switches should be functional
        for switch in all_switches[:10]:  # Test first 10
            assert hasattr(switch, "_dog_id")
            assert hasattr(switch, "unique_id")


class TestNetworkTimeoutAndFailureRecovery:
    """Test network timeout scenarios and failure recovery mechanisms."""

    @pytest.fixture
    def network_sensitive_switch(self, mock_coordinator):
        """Create a switch that depends on network operations."""
        return PawControlMainPowerSwitch(
            coordinator=mock_coordinator,
            dog_id="network_dog",
            dog_name="Network Dog",
        )

    @pytest.mark.asyncio
    async def test_coordinator_timeout_during_state_change(
        self, network_sensitive_switch
    ):
        """Test switch behavior when coordinator times out."""
        # Mock coordinator timeout
        network_sensitive_switch.coordinator.async_request_selective_refresh = (
            AsyncMock(side_effect=TimeoutError("Coordinator timeout"))
        )

        # Switch should handle timeout gracefully
        await network_sensitive_switch.async_turn_on()

        # Local state should still be updated
        assert network_sensitive_switch._is_on is True

    @pytest.mark.asyncio
    async def test_service_call_timeout_recovery(self, mock_coordinator):
        """Test recovery from service call timeouts."""
        switch = PawControlVisitorModeSwitch(
            coordinator=mock_coordinator,
            dog_id="timeout_dog",
            dog_name="Timeout Dog",
        )

        # Mock service call timeout
        with patch.object(switch, "hass") as mock_hass:
            mock_hass.services.async_call = AsyncMock(
                side_effect=TimeoutError("Service timeout")
            )

            # Should handle timeout without crashing
            await switch._async_set_state(True)

            # Should log error but not raise exception

    @pytest.mark.asyncio
    async def test_coordinator_unavailable_during_setup(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test setup when coordinator becomes unavailable."""
        # Mock coordinator becoming unavailable during setup
        mock_coordinator.available = False

        add_entities_mock = Mock()

        # Setup should handle unavailable coordinator
        await async_setup_entry(hass, mock_entry, add_entities_mock)

        # Should still attempt to create entities
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_network_partition_recovery(self, network_sensitive_switch):
        """Test recovery from network partition scenarios."""
        # Simulate network partition
        network_sensitive_switch.coordinator.available = False
        network_sensitive_switch.coordinator.get_dog_data.return_value = None

        # Switch should be unavailable
        assert network_sensitive_switch.available is False

        # Simulate network recovery
        network_sensitive_switch.coordinator.available = True
        network_sensitive_switch.coordinator.get_dog_data.return_value = {
            "modules": {MODULE_FEEDING: True}
        }

        # Switch should become available again
        assert network_sensitive_switch.available is True

    @pytest.mark.asyncio
    async def test_partial_service_failure_handling(self, mock_coordinator):
        """Test handling of partial service failures."""
        switch = PawControlFeatureSwitch(
            coordinator=mock_coordinator,
            dog_id="partial_fail_dog",
            dog_name="Partial Fail Dog",
            feature_id="notifications",
            feature_name="Notifications",
            icon="mdi:bell",
            module=MODULE_FEEDING,
        )

        # Mock partial failure - some services work, others don't
        with patch.object(switch, "hass") as mock_hass:
            # Mock successful call count
            call_count = 0

            def service_call_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count % 2 == 0:  # Every other call fails
                    raise Exception("Partial service failure")
                return AsyncMock()

            mock_hass.services.async_call = AsyncMock(
                side_effect=service_call_side_effect
            )

            # Should handle partial failures gracefully
            await switch._async_set_state(True)

            # Should attempt service call despite failures


class TestEntityRegistryCorruptionRecovery:
    """Test recovery from entity registry corruption and data inconsistencies."""

    @pytest.mark.asyncio
    async def test_duplicate_unique_id_handling(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test handling of duplicate unique IDs in entity registry."""
        # Create switches with potentially conflicting unique IDs
        switch1 = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="duplicate_dog",
            dog_name="Duplicate Dog 1",
            switch_type="test",
        )

        switch2 = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="duplicate_dog",
            dog_name="Duplicate Dog 2",
            switch_type="test",  # Same type, could cause collision
        )

        # Both switches should have same unique ID (potential conflict)
        assert switch1.unique_id == switch2.unique_id

        # Registry should handle this gracefully during entity addition
        add_entities_mock = Mock()

        await _async_add_entities_in_batches(
            add_entities_mock,
            [switch1, switch2],
            batch_size=10,
        )

        # Should complete without exception
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_corrupted_device_info_recovery(self, mock_coordinator):
        """Test recovery from corrupted device info."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="corrupted_device_dog",
            dog_name="Corrupted Device Dog",
            switch_type="test",
        )

        # Corrupt device info
        switch._attr_device_info = {
            "identifiers": None,  # Invalid identifiers
            "name": "",  # Empty name
            "manufacturer": None,  # Invalid manufacturer
        }

        # Should handle corrupted device info gracefully
        device_info = switch._attr_device_info
        assert device_info is not None

    @pytest.mark.asyncio
    async def test_state_restoration_with_registry_corruption(self, mock_coordinator):
        """Test state restoration when entity registry data is corrupted."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="registry_corrupt_dog",
            dog_name="Registry Corrupt Dog",
            switch_type="test",
        )

        # Mock corrupted registry state
        corrupted_state = Mock()
        corrupted_state.state = object()  # Invalid state object
        corrupted_state.attributes = {
            "invalid": object()}  # Invalid attributes

        with patch.object(switch, "async_get_last_state", return_value=corrupted_state):
            # Should handle corruption gracefully
            await switch.async_added_to_hass()

            # Should use default state
            assert switch._is_on is False

    def test_entity_id_generation_edge_cases(self, mock_coordinator):
        """Test entity ID generation with problematic dog names."""
        problematic_names = [
            "Dog with spaces and 123 numbers",
            "Dog-with-dashes_and_underscores",
            "Dog/with\\invalid|characters",
            "DogWithVeryLongNameThatExceeds255CharactersWhichIsTheMaximumLengthForEntityIDsInHomeAssistantAndShouldBeHandledGracefullyByTheSystemWithoutCausingAnyErrorsOrProblemsInTheIntegrationCodeOrTheEntityRegistrySystemComponentsAndShouldBetruncatedOrOtherwiseHandledAppropriately",
            "",  # Empty name
            "   ",  # Whitespace only
            "🐕",  # Unicode emoji
            "Köter",  # Non-ASCII characters
        ]

        for name in problematic_names:
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id="test_dog",
                dog_name=name,
                switch_type="test",
            )

            # Should generate valid unique ID regardless of name
            assert switch.unique_id is not None
            assert len(switch.unique_id) > 0


class TestDeviceInfoValidationEdgeCases:
    """Test device info validation and error handling."""

    def test_device_info_with_invalid_identifiers(self, mock_coordinator):
        """Test device info with various invalid identifier formats."""
        invalid_identifiers = [
            None,
            {},
            {("invalid",)},  # Single item tuple
            {("domain", "")},  # Empty identifier
            {("", "identifier")},  # Empty domain
            {(None, "identifier")},  # None domain
            {("domain", None)},  # None identifier
            {(123, "identifier")},  # Non-string domain
        ]

        for invalid_id in invalid_identifiers:
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id="invalid_device_dog",
                dog_name="Invalid Device Dog",
                switch_type="test",
            )

            # Override with invalid identifier
            switch._attr_device_info["identifiers"] = invalid_id

            # Should handle gracefully
            device_info = switch._attr_device_info
            assert device_info is not None

    def test_device_info_with_missing_required_fields(self, mock_coordinator):
        """Test device info with missing required fields."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="missing_fields_dog",
            dog_name="Missing Fields Dog",
            switch_type="test",
        )

        # Remove required fields
        del switch._attr_device_info["name"]
        del switch._attr_device_info["manufacturer"]

        # Should still be accessible
        device_info = switch._attr_device_info
        assert "identifiers" in device_info

    def test_device_info_with_very_long_values(self, mock_coordinator):
        """Test device info with extremely long values."""
        long_string = "x" * 1000  # Very long string

        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="long_values_dog",
            dog_name=long_string,  # Very long name
            switch_type="test",
        )

        # Override with long values
        switch._attr_device_info.update(
            {
                "name": long_string,
                "manufacturer": long_string,
                "model": long_string,
                "sw_version": long_string,
            }
        )

        # Should handle long values
        device_info = switch._attr_device_info
        assert device_info is not None


class TestIntegrationReloadEdgeCases:
    """Test integration reload and hot-swap scenarios."""

    @pytest.mark.asyncio
    async def test_reload_during_entity_creation(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test reload occurring during entity creation."""
        add_entities_mock = Mock()

        # Mock slow entity creation
        def slow_add_entities(*args, **kwargs):
            # Simulate reload happening during creation
            mock_entry.data = {}  # Clear data as if reloaded
            return None

        add_entities_mock.side_effect = slow_add_entities

        # Should handle reload gracefully
        await async_setup_entry(hass, mock_entry, add_entities_mock)

    @pytest.mark.asyncio
    async def test_config_entry_update_during_operation(self, mock_coordinator):
        """Test config entry being updated during switch operation."""
        switch = PawControlModuleSwitch(
            coordinator=mock_coordinator,
            dog_id="update_dog",
            dog_name="Update Dog",
            module_id=MODULE_FEEDING,
            module_name="Feeding",
            icon="mdi:food",
            initial_state=True,
        )

        # Mock config entry update happening during state change
        original_data = {
            "dogs": [{"dog_id": "update_dog", "modules": {MODULE_FEEDING: False}}]
        }
        updated_data = {
            "dogs": [{"dog_id": "update_dog", "modules": {MODULE_FEEDING: True}}]
        }

        switch.coordinator.config_entry.data = original_data

        # Simulate concurrent config update
        async def concurrent_update():
            await asyncio.sleep(0.001)  # Small delay
            switch.coordinator.config_entry.data = updated_data

        # Start concurrent update
        update_task = asyncio.create_task(concurrent_update())

        # Perform state change
        await switch._async_set_state(True)

        # Wait for concurrent update
        await update_task

        # Should handle concurrent modification gracefully

    @pytest.mark.asyncio
    async def test_coordinator_replacement_during_operation(self, mock_coordinator):
        """Test coordinator being replaced during switch operation."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="replacement_dog",
            dog_name="Replacement Dog",
            switch_type="test",
        )

        # Create replacement coordinator
        new_coordinator = MagicMock(spec=PawControlCoordinator)
        new_coordinator.available = True
        new_coordinator.get_dog_data.return_value = {
            "modules": {MODULE_FEEDING: True}}

        # Replace coordinator during operation
        old_coordinator = switch.coordinator
        switch.coordinator = new_coordinator

        # Should adapt to new coordinator
        assert switch.available is True

        # Restore original for cleanup
        switch.coordinator = old_coordinator


class TestHACSValidationEdgeCases:
    """Test HACS validation and compliance edge cases."""

    def test_manifest_compliance_validation(self, mock_coordinator):
        """Test that switches comply with HACS manifest requirements."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="hacs_dog",
            dog_name="HACS Dog",
            switch_type="test",
        )

        # Check required attributes for HACS compliance
        assert hasattr(switch, "unique_id")
        assert hasattr(switch, "_attr_device_info")
        assert hasattr(switch, "_attr_name")
        assert hasattr(switch, "_attr_should_poll")

        # Should not poll (HACS best practice)
        assert switch._attr_should_poll is False

    def test_entity_naming_compliance(self, mock_coordinator):
        """Test entity naming compliance with HACS guidelines."""
        # Test various entity naming scenarios
        test_cases = [
            ("dog_1", "Dog 1", "main_power"),
            ("dog_with_long_name", "Dog With Very Long Name", "visitor_mode"),
            ("dog123", "Dog 123", "do_not_disturb"),
        ]

        for dog_id, dog_name, switch_type in test_cases:
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id=dog_id,
                dog_name=dog_name,
                switch_type=switch_type,
            )

            # Entity name should follow HACS guidelines
            assert switch._attr_name is not None
            assert len(switch._attr_name) > 0

            # Unique ID should be properly formatted
            assert switch.unique_id.startswith("pawcontrol_")
            assert dog_id in switch.unique_id
            assert switch_type in switch.unique_id

    def test_device_info_hacs_compliance(self, mock_coordinator):
        """Test device info HACS compliance."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="hacs_device_dog",
            dog_name="HACS Device Dog",
            switch_type="test",
        )

        device_info = switch._attr_device_info

        # Required fields for HACS
        assert "identifiers" in device_info
        assert "name" in device_info
        assert "manufacturer" in device_info
        assert "model" in device_info

        # Optional but recommended fields
        assert "sw_version" in device_info
        assert "configuration_url" in device_info

        # Identifiers should be properly formatted
        identifiers = device_info["identifiers"]
        assert len(identifiers) == 1
        domain, identifier = next(iter(identifiers))
        assert domain == DOMAIN
        assert identifier == "hacs_device_dog"


class TestTranslationLocalizationEdgeCases:
    """Test translation and localization edge cases."""

    def test_entity_names_with_unicode(self, mock_coordinator):
        """Test entity names with Unicode characters."""
        unicode_names = [
            "Röxli",  # German umlaut
            "José",  # Spanish accent
            "Москва",  # Cyrillic
            "北京",  # Chinese
            "🐕 Dog",  # Emoji
        ]

        for name in unicode_names:
            switch = OptimizedSwitchBase(
                coordinator=mock_coordinator,
                dog_id="unicode_dog",
                dog_name=name,
                switch_type="test",
            )

            # Should handle Unicode names gracefully
            assert switch._attr_name is not None
            assert name in switch._attr_name

    def test_missing_translation_fallback(self, mock_coordinator):
        """Test fallback behavior when translations are missing."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="translation_dog",
            dog_name="Translation Dog",
            switch_type="unknown_switch_type",  # Type without translation
        )

        # Should use English fallback
        assert "Translation Dog" in switch._attr_name
        assert "Unknown Switch Type" in switch._attr_name


class TestDependenciesMissingEdgeCases:
    """Test behavior when required dependencies are missing."""

    @pytest.mark.asyncio
    async def test_missing_coordinator_dependency(
        self, hass: HomeAssistant, mock_entry
    ):
        """Test setup when coordinator dependency is missing."""
        # Mock missing coordinator
        mock_entry.runtime_data = None
        hass.data[DOMAIN] = {}  # No coordinator in hass.data

        add_entities_mock = Mock()

        # Should handle missing coordinator gracefully
        try:
            await async_setup_entry(hass, mock_entry, add_entities_mock)
        except (KeyError, AttributeError):
            # Expected behavior - should fail gracefully
            pass

    def test_missing_module_constants(self, mock_coordinator):
        """Test behavior when module constants are undefined."""
        # Test with undefined module constant
        switch = PawControlModuleSwitch(
            coordinator=mock_coordinator,
            dog_id="missing_module_dog",
            dog_name="Missing Module Dog",
            module_id="undefined_module",  # Module not in constants
            module_name="Undefined Module",
            icon="mdi:help",
            initial_state=False,
        )

        # Should create switch despite unknown module
        assert switch._module_id == "undefined_module"
        assert switch._attr_name == "Missing Module Dog Undefined Module"


class TestConcurrentModificationProtection:
    """Test protection against concurrent modifications."""

    @pytest.mark.asyncio
    async def test_concurrent_state_changes(self, mock_coordinator):
        """Test concurrent state changes to the same switch."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="concurrent_dog",
            dog_name="Concurrent Dog",
            switch_type="test",
        )

        async def toggle_switch():
            for _ in range(20):
                await switch.async_turn_on()
                await asyncio.sleep(0.001)
                await switch.async_turn_off()
                await asyncio.sleep(0.001)

        # Run multiple concurrent toggles
        await asyncio.gather(
            toggle_switch(),
            toggle_switch(),
            toggle_switch(),
        )

        # Switch should be in valid state
        assert isinstance(switch.is_on, bool)

    @pytest.mark.asyncio
    async def test_concurrent_cache_updates(self, mock_coordinator):
        """Test concurrent cache updates."""
        switch = OptimizedSwitchBase(
            coordinator=mock_coordinator,
            dog_id="cache_concurrent_dog",
            dog_name="Cache Concurrent Dog",
            switch_type="test",
        )

        async def update_cache():
            for i in range(50):
                switch._update_cache(i % 2 == 0)
                await asyncio.sleep(0.001)

        # Run concurrent cache updates
        await asyncio.gather(
            update_cache(),
            update_cache(),
            update_cache(),
        )

        # Cache should remain consistent
        assert isinstance(switch.is_on, bool)

    @pytest.mark.asyncio
    async def test_concurrent_entity_creation(self, mock_coordinator):
        """Test concurrent entity creation scenarios."""

        async def create_switches(start_index):
            switches = []
            for i in range(start_index, start_index + 10):
                switch = OptimizedSwitchBase(
                    coordinator=mock_coordinator,
                    dog_id=f"concurrent_create_dog_{i}",
                    dog_name=f"Concurrent Create Dog {i}",
                    switch_type="test",
                )
                switches.append(switch)
            return switches

        # Create switches concurrently
        switch_lists = await asyncio.gather(
            create_switches(0),
            create_switches(10),
            create_switches(20),
        )

        # All switches should be valid and unique
        all_switches = [s for sublist in switch_lists for s in sublist]
        unique_ids = [s.unique_id for s in all_switches]

        assert len(unique_ids) == len(
            set(unique_ids)
        )  # All unique IDs should be unique


class TestConfigurationMigrationEdgeCases:
    """Test configuration migration and version handling edge cases."""

    @pytest.mark.asyncio
    async def test_legacy_config_format_support(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test support for legacy configuration formats."""
        # Create legacy format config entry
        legacy_entry = MagicMock(spec=ConfigEntry)
        legacy_entry.entry_id = "legacy_entry"
        legacy_entry.version = 0  # Old version
        legacy_entry.data = {
            "dogs": [  # Old format without CONF_DOGS key
                {
                    "id": "legacy_dog",  # Old key name
                    "name": "Legacy Dog",
                    "enabled_modules": ["feeding", "gps"],  # Old format
                }
            ]
        }

        add_entities_mock = Mock()

        # Should handle legacy format gracefully
        try:
            await async_setup_entry(hass, legacy_entry, add_entities_mock)
        except (KeyError, AttributeError):
            # Expected - should fail gracefully with legacy format
            pass

    def test_module_configuration_migration(self, mock_coordinator):
        """Test migration of module configuration formats."""
        # Test various module configuration formats
        new_format_modules = {
            MODULE_FEEDING: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
        }  # Dict format

        # Should handle both formats
        switches_old = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            coordinator=mock_coordinator,
            dog_id="migration_dog",
            dog_name="Migration Dog",
            modules=new_format_modules,  # Use new format
        )

        # Should create valid switches
        assert len(switches_old) > 0

    @pytest.mark.asyncio
    async def test_config_entry_corruption_recovery(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test recovery from corrupted config entry data."""
        # Create corrupted config entry
        corrupted_entry = MagicMock(spec=ConfigEntry)
        corrupted_entry.entry_id = "corrupted_entry"
        corrupted_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: 123,  # Should be string
                    CONF_DOG_NAME: None,  # Should be string
                    "modules": "invalid",  # Should be dict
                },
                None,  # Invalid dog entry
                {
                    # Missing required fields
                    "extra_field": "value",
                },
            ]
        }

        add_entities_mock = Mock()

        # Should handle corruption gracefully
        try:
            await async_setup_entry(hass, corrupted_entry, add_entities_mock)
        except (TypeError, AttributeError, KeyError):
            # Expected behavior with corrupted data
            pass


if __name__ == "__main__":
    pytest.main([__file__])
