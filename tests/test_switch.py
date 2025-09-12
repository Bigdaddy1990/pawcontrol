"""Comprehensive tests for PawControl switch platform with profile optimization."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_GROOMING,
    MODULE_HEALTH,
    MODULE_MEDICATION,
    MODULE_NOTIFICATIONS,
    MODULE_TRAINING,
    MODULE_VISITOR,
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
from homeassistant.components.switch import DOMAIN as SWITCH_DOMAIN
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util


class TestProfileOptimizedSwitchFactory:
    """Test the ProfileOptimizedSwitchFactory class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: False,
                    MODULE_HEALTH: True,
                },
                "visitor_mode_active": False,
            }
        )
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return coordinator

    def test_module_configs_definition(self):
        """Test that module configurations are properly defined."""
        assert len(ProfileOptimizedSwitchFactory.MODULE_CONFIGS) > 0

        for (
            module_id,
            module_name,
            icon,
        ) in ProfileOptimizedSwitchFactory.MODULE_CONFIGS:
            assert isinstance(module_id, str)
            assert isinstance(module_name, str)
            assert isinstance(icon, str)
            assert icon.startswith("mdi:")

    def test_feature_switches_definition(self):
        """Test that feature switches are properly defined."""
        feature_switches = ProfileOptimizedSwitchFactory.FEATURE_SWITCHES

        # Should have entries for key modules
        assert MODULE_FEEDING in feature_switches
        assert MODULE_GPS in feature_switches
        assert MODULE_HEALTH in feature_switches
        assert MODULE_NOTIFICATIONS in feature_switches

        # Each feature switch should have proper structure
        for switches in feature_switches.values():
            assert isinstance(switches, list)
            for switch_id, switch_name, icon in switches:
                assert isinstance(switch_id, str)
                assert isinstance(switch_name, str)
                assert isinstance(icon, str)
                assert icon.startswith("mdi:")

    def test_create_switches_for_dog_minimal_modules(self, mock_coordinator):
        """Test switch creation with minimal modules enabled."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            mock_coordinator, "test_dog", "Test Dog", modules
        )

        # Should create base switches + module switches + feature switches
        assert len(switches) > 2  # At least base switches

        # Should include base switches
        switch_types = [type(switch).__name__ for switch in switches]
        assert "PawControlMainPowerSwitch" in switch_types
        assert "PawControlDoNotDisturbSwitch" in switch_types

    def test_create_switches_for_dog_all_modules(self, mock_coordinator):
        """Test switch creation with all modules enabled."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: True,
            MODULE_GPS: True,
            MODULE_HEALTH: True,
            MODULE_NOTIFICATIONS: True,
            MODULE_GROOMING: True,
            MODULE_MEDICATION: True,
            MODULE_TRAINING: True,
        }

        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            mock_coordinator, "test_dog", "Test Dog", modules
        )

        # Should create many switches for all enabled modules
        assert len(switches) > 10

        # Should include module switches for enabled modules
        switch_types = [type(switch).__name__ for switch in switches]
        assert "PawControlModuleSwitch" in switch_types
        assert "PawControlFeatureSwitch" in switch_types

    def test_create_switches_for_dog_no_modules(self, mock_coordinator):
        """Test switch creation with no modules enabled."""
        modules = {
            MODULE_FEEDING: False,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }

        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            mock_coordinator, "test_dog", "Test Dog", modules
        )

        # Should still create base switches and visitor mode as fallback
        assert len(switches) >= 3  # main_power, do_not_disturb, visitor_mode

        switch_types = [type(switch).__name__ for switch in switches]
        assert "PawControlMainPowerSwitch" in switch_types
        assert "PawControlDoNotDisturbSwitch" in switch_types
        assert "PawControlVisitorModeSwitch" in switch_types

    def test_create_switches_only_enabled_modules(self, mock_coordinator):
        """Test that switches are only created for enabled modules."""
        modules = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,  # Disabled
            MODULE_GPS: True,
            MODULE_HEALTH: False,  # Disabled
        }

        switches = ProfileOptimizedSwitchFactory.create_switches_for_dog(
            mock_coordinator, "test_dog", "Test Dog", modules
        )

        # Check that only enabled modules have switches
        module_switches = [s for s in switches if isinstance(s, PawControlModuleSwitch)]
        feature_switches = [
            s for s in switches if isinstance(s, PawControlFeatureSwitch)
        ]

        # Should have module switches for enabled modules
        module_ids = [s._module_id for s in module_switches]
        assert MODULE_FEEDING in module_ids
        assert MODULE_GPS in module_ids
        assert MODULE_WALK not in module_ids
        assert MODULE_HEALTH not in module_ids

        # Feature switches should only be for enabled modules
        feature_modules = [s._module for s in feature_switches]
        assert MODULE_FEEDING in feature_modules or MODULE_GPS in feature_modules
        assert MODULE_WALK not in feature_modules
        assert MODULE_HEALTH not in feature_modules


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                    },
                }
            ]
        }
        entry.options = {}
        return entry

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
            }
        )
        return coordinator

    @pytest.fixture
    def mock_runtime_data(self, mock_coordinator):
        """Create mock runtime data."""
        return {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_runtime_data(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with runtime data."""
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create switch entities
        assert len(added_entities) > 0

        # All entities should be switch instances
        for entity in added_entities:
            assert isinstance(entity, OptimizedSwitchBase)

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_legacy_data(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test setup entry with legacy data storage."""
        # No runtime_data, use legacy storage
        mock_config_entry.runtime_data = None
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {"coordinator": mock_coordinator}
        }

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities from legacy data
        assert len(added_entities) > 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with no dogs configured."""
        mock_runtime_data["dogs"] = []
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should not create entities
        assert len(added_entities) == 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_multiple_dogs(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with multiple dogs."""
        mock_runtime_data["dogs"] = [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Dog 1",
                "modules": {MODULE_FEEDING: True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Dog 2",
                "modules": {MODULE_WALK: True},
            },
        ]
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities for both dogs
        assert len(added_entities) > 4  # At least 2 base switches per dog

        # Check that entities exist for both dogs
        dog_ids = {entity._dog_id for entity in added_entities}
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids

    @pytest.mark.asyncio
    async def test_async_setup_entry_profile_optimization(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test that setup entry applies profile optimization."""
        # Create many dogs to test optimization
        many_dogs = [
            {
                CONF_DOG_ID: f"dog{i}",
                CONF_DOG_NAME: f"Dog {i}",
                "modules": {MODULE_FEEDING: True, MODULE_GPS: True},
            }
            for i in range(5)
        ]
        mock_runtime_data["dogs"] = many_dogs
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        with patch(
            "custom_components.pawcontrol.switch._async_add_entities_in_batches"
        ) as mock_batch:
            mock_batch.side_effect = lambda async_add_func, entities: async_add_func(
                entities, False
            )

            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities and use batching
        assert len(added_entities) > 10
        mock_batch.assert_called_once()


class TestAsyncAddEntitiesInBatches:
    """Test the batch entity addition function."""

    @pytest.mark.asyncio
    async def test_add_entities_in_batches_small_list(self):
        """Test batch addition with small entity list."""
        entities = [Mock(spec=OptimizedSwitchBase) for _ in range(5)]
        added_entities = []

        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)

        await _async_add_entities_in_batches(mock_add_entities, entities, batch_size=10)

        # Should add all entities in one batch
        assert len(added_entities) == 5
        assert added_entities == entities

    @pytest.mark.asyncio
    async def test_add_entities_in_batches_large_list(self):
        """Test batch addition with large entity list."""
        entities = [Mock(spec=OptimizedSwitchBase) for _ in range(25)]
        added_entities = []
        batch_calls = []

        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)
            batch_calls.append(len(batch))

        with patch("asyncio.sleep") as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=10, delay_between_batches=0.001
            )

        # Should add all entities in multiple batches
        assert len(added_entities) == 25
        assert len(batch_calls) == 3  # 25 entities / 10 batch_size = 3 batches
        assert batch_calls == [10, 10, 5]  # Batch sizes

        # Should have sleep calls between batches (not after last batch)
        assert mock_sleep.call_count == 2

    @pytest.mark.asyncio
    async def test_add_entities_in_batches_empty_list(self):
        """Test batch addition with empty entity list."""
        entities = []
        added_entities = []

        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)

        await _async_add_entities_in_batches(mock_add_entities, entities)

        # Should handle empty list gracefully
        assert len(added_entities) == 0


class TestOptimizedSwitchBase:
    """Test the base switch class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "modules": {MODULE_FEEDING: True},
                "visitor_mode_active": False,
            }
        )
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return coordinator

    @pytest.fixture
    def switch_base(self, mock_coordinator):
        """Create a base switch instance."""
        return OptimizedSwitchBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_switch",
            device_class=SwitchDeviceClass.SWITCH,
            icon="mdi:test",
            initial_state=False,
        )

    def test_switch_base_initialization(self, switch_base):
        """Test base switch initialization."""
        assert switch_base._dog_id == "test_dog"
        assert switch_base._dog_name == "Test Dog"
        assert switch_base._switch_type == "test_switch"
        assert switch_base._attr_unique_id == "pawcontrol_test_dog_test_switch"
        assert switch_base._attr_name == "Test Dog Test Switch"
        assert switch_base._attr_device_class == SwitchDeviceClass.SWITCH
        assert switch_base._attr_icon == "mdi:test"
        assert switch_base._is_on is False

    def test_switch_base_device_info(self, switch_base):
        """Test device info generation."""
        device_info = switch_base._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"

    def test_switch_base_extra_state_attributes(self, switch_base):
        """Test extra state attributes."""
        attrs = switch_base.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "test_dog"
        assert attrs[ATTR_DOG_NAME] == "Test Dog"
        assert attrs["switch_type"] == "test_switch"
        assert attrs["profile_optimized"] is True
        assert "last_changed" in attrs

    def test_switch_base_is_on_property(self, switch_base):
        """Test is_on property with caching."""
        # Initial state
        assert switch_base.is_on is False

        # Change internal state
        switch_base._is_on = True
        assert switch_base.is_on is True

    def test_switch_base_caching(self, switch_base):
        """Test state caching mechanism."""
        # Get initial state (should populate cache)
        state1 = switch_base.is_on

        # Get state again within cache TTL (should use cache)
        state2 = switch_base.is_on
        assert state1 == state2

        # Cache should be populated
        cache_key = f"{switch_base._dog_id}_{switch_base._switch_type}"
        assert cache_key in switch_base._state_cache

    def test_switch_base_update_cache(self, switch_base):
        """Test cache update mechanism."""
        switch_base._update_cache(True)

        cache_key = f"{switch_base._dog_id}_{switch_base._switch_type}"
        assert cache_key in switch_base._state_cache

        cached_state, cache_time = switch_base._state_cache[cache_key]
        assert cached_state is True
        assert isinstance(cache_time, float)

    def test_switch_base_get_dog_data(self, switch_base, mock_coordinator):
        """Test dog data retrieval."""
        data = switch_base._get_dog_data()
        assert data is not None
        assert "modules" in data

        # Test with unavailable coordinator
        mock_coordinator.available = False
        data = switch_base._get_dog_data()
        assert data is None

    def test_switch_base_available_property(self, switch_base, mock_coordinator):
        """Test availability property."""
        # Should be available when coordinator is available and has data
        assert switch_base.available is True

        # Should be unavailable when coordinator is unavailable
        mock_coordinator.available = False
        assert switch_base.available is False

        # Should be unavailable when no dog data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        assert switch_base.available is False

    @pytest.mark.asyncio
    async def test_switch_base_async_added_to_hass(self, switch_base, hass):
        """Test async_added_to_hass with state restoration."""
        switch_base.hass = hass

        # Mock last state
        last_state = Mock()
        last_state.state = "on"

        with patch.object(switch_base, "async_get_last_state", return_value=last_state):
            await switch_base.async_added_to_hass()

        # Should restore state
        assert switch_base._is_on is True

    @pytest.mark.asyncio
    async def test_switch_base_async_added_to_hass_no_state(self, switch_base, hass):
        """Test async_added_to_hass without previous state."""
        switch_base.hass = hass

        with patch.object(switch_base, "async_get_last_state", return_value=None):
            await switch_base.async_added_to_hass()

        # Should keep initial state
        assert switch_base._is_on is False

    @pytest.mark.asyncio
    async def test_switch_base_async_turn_on(self, switch_base, hass):
        """Test turning switch on."""
        switch_base.hass = hass
        switch_base.async_write_ha_state = Mock()

        await switch_base.async_turn_on()

        assert switch_base._is_on is True
        assert switch_base._last_changed is not None
        switch_base.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_base_async_turn_off(self, switch_base, hass):
        """Test turning switch off."""
        switch_base.hass = hass
        switch_base.async_write_ha_state = Mock()
        switch_base._is_on = True  # Start in on state

        await switch_base.async_turn_off()

        assert switch_base._is_on is False
        assert switch_base._last_changed is not None
        switch_base.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_base_async_turn_on_error(self, switch_base, hass):
        """Test turning switch on with error."""
        switch_base.hass = hass

        # Mock _async_set_state to raise exception
        switch_base._async_set_state = AsyncMock(side_effect=Exception("Test error"))

        with pytest.raises(HomeAssistantError, match="Failed to turn on test_switch"):
            await switch_base.async_turn_on()

    @pytest.mark.asyncio
    async def test_switch_base_async_turn_off_error(self, switch_base, hass):
        """Test turning switch off with error."""
        switch_base.hass = hass

        # Mock _async_set_state to raise exception
        switch_base._async_set_state = AsyncMock(side_effect=Exception("Test error"))

        with pytest.raises(HomeAssistantError, match="Failed to turn off test_switch"):
            await switch_base.async_turn_off()


class TestSpecificSwitchClasses:
    """Test specific switch implementations."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(
            return_value={
                "modules": {MODULE_FEEDING: True},
                "visitor_mode_active": False,
            }
        )
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        coordinator.async_request_selective_refresh = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        hass.config_entries = Mock()
        hass.config_entries.async_update_entry = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data_manager": AsyncMock(),
                    "notifications": AsyncMock(),
                }
            }
        }
        return hass

    def test_main_power_switch_initialization(self, mock_coordinator):
        """Test main power switch initialization."""
        switch = PawControlMainPowerSwitch(mock_coordinator, "test_dog", "Test Dog")

        assert switch._switch_type == "main_power"
        assert switch._attr_device_class == SwitchDeviceClass.SWITCH
        assert switch._attr_icon == "mdi:power"
        assert switch._is_on is True  # Initial state

    @pytest.mark.asyncio
    async def test_main_power_switch_set_state(self, mock_coordinator, mock_hass):
        """Test main power switch state setting."""
        switch = PawControlMainPowerSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = mock_hass

        # Mock data manager
        data_manager = AsyncMock()
        mock_hass.data[DOMAIN]["test_entry"]["data_manager"] = data_manager

        await switch._async_set_state(False)

        # Should call data manager and request refresh
        data_manager.async_set_dog_power_state.assert_called_once_with(
            "test_dog", False
        )
        mock_coordinator.async_request_selective_refresh.assert_called_once_with(
            ["test_dog"], priority=10
        )

    def test_do_not_disturb_switch_initialization(self, mock_coordinator):
        """Test do not disturb switch initialization."""
        switch = PawControlDoNotDisturbSwitch(mock_coordinator, "test_dog", "Test Dog")

        assert switch._switch_type == "do_not_disturb"
        assert switch._attr_icon == "mdi:sleep"
        assert switch._is_on is False  # Initial state

    @pytest.mark.asyncio
    async def test_do_not_disturb_switch_set_state(self, mock_coordinator, mock_hass):
        """Test do not disturb switch state setting."""
        switch = PawControlDoNotDisturbSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = mock_hass

        # Mock notification manager with async_set_dnd_mode method
        notification_manager = AsyncMock()
        notification_manager.async_set_dnd_mode = AsyncMock()
        mock_hass.data[DOMAIN]["test_entry"]["notifications"] = notification_manager

        await switch._async_set_state(True)

        # Should call notification manager
        notification_manager.async_set_dnd_mode.assert_called_once_with(
            "test_dog", True
        )

    def test_visitor_mode_switch_initialization(self, mock_coordinator):
        """Test visitor mode switch initialization."""
        switch = PawControlVisitorModeSwitch(mock_coordinator, "test_dog", "Test Dog")

        assert switch._switch_type == "visitor_mode"
        assert switch._attr_icon == "mdi:account-group"
        assert switch._is_on is False  # Initial state

    def test_visitor_mode_switch_is_on_property(self, mock_coordinator):
        """Test visitor mode switch is_on property."""
        switch = PawControlVisitorModeSwitch(mock_coordinator, "test_dog", "Test Dog")

        # Should read from dog data
        assert switch.is_on is False

        # Update dog data
        mock_coordinator.get_dog_data.return_value = {"visitor_mode_active": True}
        assert switch.is_on is True

    @pytest.mark.asyncio
    async def test_visitor_mode_switch_set_state(self, mock_coordinator, mock_hass):
        """Test visitor mode switch state setting."""
        switch = PawControlVisitorModeSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = mock_hass

        await switch._async_set_state(True)

        # Should call set_visitor_mode service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "set_visitor_mode",
            {
                "dog_id": "test_dog",
                "enabled": True,
                "visitor_name": "Switch Toggle",
                "reduced_alerts": True,
            },
            blocking=False,
        )

    def test_module_switch_initialization(self, mock_coordinator):
        """Test module switch initialization."""
        switch = PawControlModuleSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            MODULE_FEEDING,
            "Feeding Tracking",
            "mdi:food",
            True,
        )

        assert switch._switch_type == f"module_{MODULE_FEEDING}"
        assert switch._module_id == MODULE_FEEDING
        assert switch._module_name == "Feeding Tracking"
        assert switch._attr_name == "Test Dog Feeding Tracking"
        assert switch._attr_entity_category == EntityCategory.CONFIG

    @pytest.mark.asyncio
    async def test_module_switch_set_state(self, mock_coordinator, mock_hass):
        """Test module switch state setting."""
        switch = PawControlModuleSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            MODULE_FEEDING,
            "Feeding Tracking",
            "mdi:food",
            True,
        )
        switch.hass = mock_hass

        # Mock config entry data
        mock_coordinator.config_entry.data = {
            "dogs": [{"dog_id": "test_dog", "modules": {MODULE_FEEDING: False}}]
        }

        await switch._async_set_state(True)

        # Should update config entry
        mock_hass.config_entries.async_update_entry.assert_called_once()
        mock_coordinator.async_request_selective_refresh.assert_called_once_with(
            ["test_dog"], priority=7
        )

    def test_feature_switch_initialization(self, mock_coordinator):
        """Test feature switch initialization."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "gps_tracking",
            "GPS Tracking",
            "mdi:gps",
            MODULE_GPS,
        )

        assert switch._switch_type == "gps_tracking"
        assert switch._feature_id == "gps_tracking"
        assert switch._feature_name == "GPS Tracking"
        assert switch._module == MODULE_GPS
        assert switch._attr_name == "Test Dog GPS Tracking"

    def test_feature_switch_extra_state_attributes(self, mock_coordinator):
        """Test feature switch extra state attributes."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "gps_tracking",
            "GPS Tracking",
            "mdi:gps",
            MODULE_GPS,
        )

        attrs = switch.extra_state_attributes
        assert attrs["feature_id"] == "gps_tracking"
        assert attrs["parent_module"] == MODULE_GPS
        assert attrs["feature_name"] == "GPS Tracking"

    @pytest.mark.asyncio
    async def test_feature_switch_set_gps_tracking(self, mock_coordinator, mock_hass):
        """Test feature switch GPS tracking handler."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "gps_tracking",
            "GPS Tracking",
            "mdi:gps",
            MODULE_GPS,
        )
        switch.hass = mock_hass

        # Mock data manager
        data_manager = AsyncMock()
        mock_hass.data[DOMAIN]["test_entry"]["data_manager"] = data_manager

        await switch._async_set_state(True)

        # Should call data manager for GPS tracking
        data_manager.async_set_gps_tracking.assert_called_once_with("test_dog", True)

    @pytest.mark.asyncio
    async def test_feature_switch_set_notifications(self, mock_coordinator, mock_hass):
        """Test feature switch notifications handler."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "notifications",
            "Notifications",
            "mdi:bell",
            MODULE_NOTIFICATIONS,
        )
        switch.hass = mock_hass

        await switch._async_set_state(True)

        # Should call configure_alerts service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "configure_alerts",
            {
                "dog_id": "test_dog",
                "feeding_alerts": True,
                "walk_alerts": True,
                "health_alerts": True,
                "gps_alerts": True,
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_feature_switch_set_feeding_schedule(
        self, mock_coordinator, mock_hass
    ):
        """Test feature switch feeding schedule handler."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "feeding_schedule",
            "Feeding Schedule",
            "mdi:calendar",
            MODULE_FEEDING,
        )
        switch.hass = mock_hass

        await switch._async_set_state(False)

        # Should call set_feeding_schedule service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "set_feeding_schedule",
            {
                "dog_id": "test_dog",
                "enabled": False,
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_feature_switch_set_health_monitoring(
        self, mock_coordinator, mock_hass
    ):
        """Test feature switch health monitoring handler."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "health_monitoring",
            "Health Monitoring",
            "mdi:heart",
            MODULE_HEALTH,
        )
        switch.hass = mock_hass

        await switch._async_set_state(True)

        # Should call configure_health_monitoring service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "configure_health_monitoring",
            {
                "dog_id": "test_dog",
                "enabled": True,
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_feature_switch_set_medication_reminders(
        self, mock_coordinator, mock_hass
    ):
        """Test feature switch medication reminders handler."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "medication_reminders",
            "Medication Reminders",
            "mdi:pill",
            MODULE_MEDICATION,
        )
        switch.hass = mock_hass

        await switch._async_set_state(True)

        # Should call configure_medication_reminders service
        mock_hass.services.async_call.assert_called_once_with(
            DOMAIN,
            "configure_medication_reminders",
            {
                "dog_id": "test_dog",
                "enabled": True,
            },
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_feature_switch_unknown_feature(self, mock_coordinator, mock_hass):
        """Test feature switch with unknown feature type."""
        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "unknown_feature",
            "Unknown Feature",
            "mdi:help",
            "unknown_module",
        )
        switch.hass = mock_hass

        # Should not raise exception for unknown feature
        await switch._async_set_state(True)


class TestSwitchErrorHandling:
    """Test switch error handling and edge cases."""

    @pytest.fixture
    def mock_coordinator_unavailable(self):
        """Create an unavailable coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = False
        coordinator.get_dog_data = Mock(return_value=None)
        return coordinator

    def test_switch_unavailable_coordinator(self, mock_coordinator_unavailable):
        """Test switch behavior with unavailable coordinator."""
        switch = PawControlMainPowerSwitch(
            mock_coordinator_unavailable, "test_dog", "Test Dog"
        )

        # Should be unavailable
        assert switch.available is False

    @pytest.mark.asyncio
    async def test_switch_main_power_error_handling(self, mock_coordinator):
        """Test main power switch error handling."""
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data_manager": None,  # No data manager
                }
            }
        }

        switch = PawControlMainPowerSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = hass

        # Should handle missing data manager gracefully
        await switch._async_set_state(True)

    @pytest.mark.asyncio
    async def test_switch_dnd_error_handling(self, mock_coordinator):
        """Test DND switch error handling."""
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "notifications": Mock(),  # No async_set_dnd_mode method
                }
            }
        }

        switch = PawControlDoNotDisturbSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = hass

        # Should handle missing method gracefully
        await switch._async_set_state(True)

    @pytest.mark.asyncio
    async def test_feature_switch_error_handling(self, mock_coordinator):
        """Test feature switch error handling."""
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data_manager": AsyncMock(),
                }
            }
        }

        # Mock data manager to raise exception
        data_manager = hass.data[DOMAIN]["test_entry"]["data_manager"]
        data_manager.async_set_gps_tracking = AsyncMock(
            side_effect=Exception("Test error")
        )

        switch = PawControlFeatureSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "gps_tracking",
            "GPS Tracking",
            "mdi:gps",
            MODULE_GPS,
        )
        switch.hass = hass

        # Should handle error gracefully (no exception raised)
        await switch._async_set_state(True)

    def test_switch_cache_edge_cases(self, mock_coordinator):
        """Test switch caching edge cases."""
        switch = PawControlMainPowerSwitch(mock_coordinator, "test_dog", "Test Dog")

        # Test cache with expired timestamp
        cache_key = f"{switch._dog_id}_{switch._switch_type}"
        old_timestamp = dt_util.utcnow().timestamp() - 10  # 10 seconds ago
        switch._state_cache[cache_key] = (True, old_timestamp)

        # Should refresh cache due to expired TTL

        # Cache should be updated with new timestamp
        _, new_timestamp = switch._state_cache[cache_key]
        assert new_timestamp > old_timestamp


class TestSwitchIntegration:
    """Test switch integration with other components."""

    @pytest.fixture
    def mock_hass_with_full_data(self):
        """Create a mock Home Assistant instance with full data."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        hass.config_entries = Mock()
        hass.config_entries.async_update_entry = Mock()

        # Mock components
        data_manager = AsyncMock()
        notification_manager = AsyncMock()
        notification_manager.async_set_dnd_mode = AsyncMock()

        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data_manager": data_manager,
                    "notifications": notification_manager,
                }
            }
        }
        return hass

    @pytest.mark.asyncio
    async def test_switch_coordinator_integration(self, mock_coordinator):
        """Test switch integration with coordinator."""
        switch = PawControlMainPowerSwitch(mock_coordinator, "test_dog", "Test Dog")

        # Mock hass with data manager
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "data_manager": AsyncMock(),
                }
            }
        }
        switch.hass = hass

        await switch._async_set_state(False)

        # Should request refresh from coordinator
        mock_coordinator.async_request_selective_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_service_integration(
        self, mock_coordinator, mock_hass_with_full_data
    ):
        """Test switch integration with Home Assistant services."""
        switch = PawControlVisitorModeSwitch(mock_coordinator, "test_dog", "Test Dog")
        switch.hass = mock_hass_with_full_data

        await switch._async_set_state(True)

        # Should call Home Assistant service
        mock_hass_with_full_data.services.async_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_config_entry_integration(self, mock_coordinator):
        """Test switch integration with config entry updates."""
        switch = PawControlModuleSwitch(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            MODULE_FEEDING,
            "Feeding Tracking",
            "mdi:food",
            True,
        )

        # Mock hass and config entry
        hass = Mock()
        hass.config_entries = Mock()
        hass.config_entries.async_update_entry = Mock()
        switch.hass = hass

        # Mock config entry data
        mock_coordinator.config_entry.data = {
            "dogs": [{"dog_id": "test_dog", "modules": {MODULE_FEEDING: False}}]
        }

        await switch._async_set_state(True)

        # Should update config entry
        hass.config_entries.async_update_entry.assert_called_once()


class TestSwitchConstants:
    """Test switch platform constants and configurations."""

    def test_batch_constants(self):
        """Test that batch constants are properly defined."""
        assert BATCH_SIZE > 0
        assert BATCH_DELAY >= 0
        assert MAX_CONCURRENT_BATCHES > 0

        # Batch size should be reasonable
        assert 5 <= BATCH_SIZE <= 50

        # Batch delay should be small for performance
        assert BATCH_DELAY < 0.1

    def test_module_configs_completeness(self):
        """Test that module configurations are complete."""
        factory = ProfileOptimizedSwitchFactory

        # Should have configs for key modules
        module_ids = [config[0] for config in factory.MODULE_CONFIGS]
        assert MODULE_FEEDING in module_ids
        assert MODULE_GPS in module_ids
        assert MODULE_HEALTH in module_ids
        assert MODULE_NOTIFICATIONS in module_ids

    def test_feature_switches_structure(self):
        """Test that feature switches have proper structure."""
        feature_switches = ProfileOptimizedSwitchFactory.FEATURE_SWITCHES

        for switches in feature_switches.values():
            assert isinstance(switches, list)
            assert len(switches) > 0

            for switch_config in switches:
                assert len(switch_config) == 3  # switch_id, name, icon
                switch_id, name, icon = switch_config
                assert isinstance(switch_id, str)
                assert isinstance(name, str)
                assert isinstance(icon, str)
                assert "_" in switch_id  # Should use snake_case
                assert icon.startswith("mdi:")
