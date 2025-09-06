"""Comprehensive tests for PawControl select platform."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch
from typing import Any, Dict, List

import pytest
from homeassistant.components.select import DOMAIN as SELECT_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
                    CONF_DOG_SIZE: "medium",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                }
            ]
        }
        return entry

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(return_value={
            "dog_info": {"dog_breed": "Test Breed", "dog_age": 5},
            "modules": {MODULE_FEEDING: True, MODULE_WALK: True},
        })
        coordinator.get_module_data = Mock(return_value={})
        coordinator.async_refresh_dog = AsyncMock()
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
                    CONF_DOG_SIZE: "medium",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
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

        with patch("custom_components.pawcontrol.select._async_add_entities_in_batches") as mock_batch:
            mock_batch.side_effect = lambda async_add_func, entities, **kwargs: async_add_func(entities, False)
            
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create select entities
        assert len(added_entities) > 0
        
        # All entities should be select instances
        for entity in added_entities:
            assert isinstance(entity, PawControlSelectBase)
        
        # Should use batching
        mock_batch.assert_called_once()

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

        with patch("custom_components.pawcontrol.select._async_add_entities_in_batches") as mock_batch:
            mock_batch.side_effect = lambda async_add_func, entities, **kwargs: async_add_func(entities, False)
            
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
    async def test_async_setup_entry_module_filtering(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with selective module enabling."""
        # Only enable feeding module
        mock_runtime_data["dogs"][0]["modules"] = {
            MODULE_FEEDING: True,
            MODULE_WALK: False,
            MODULE_GPS: False,
            MODULE_HEALTH: False,
        }
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        with patch("custom_components.pawcontrol.select._async_add_entities_in_batches") as mock_batch:
            mock_batch.side_effect = lambda async_add_func, entities, **kwargs: async_add_func(entities, False)
            
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create base selects + feeding selects
        assert len(added_entities) > 3  # At least base selects

        # Check that only appropriate select types were created
        select_types = [type(entity).__name__ for entity in added_entities]
        
        # Should have base selects
        assert any("DogSize" in name for name in select_types)
        assert any("PerformanceMode" in name for name in select_types)
        
        # Should have feeding selects
        assert any("FoodType" in name for name in select_types)
        
        # Should not have walk, GPS, or health selects
        assert not any("WalkMode" in name for name in select_types)
        assert not any("GPSSource" in name for name in select_types)
        assert not any("HealthStatus" in name for name in select_types)

    @pytest.mark.asyncio
    async def test_async_setup_entry_multiple_dogs(
        self, hass: HomeAssistant, mock_config_entry, mock_runtime_data
    ):
        """Test setup entry with multiple dogs."""
        mock_runtime_data["dogs"] = [
            {
                CONF_DOG_ID: "dog1",
                CONF_DOG_NAME: "Dog 1",
                CONF_DOG_SIZE: "large",
                "modules": {MODULE_FEEDING: True},
            },
            {
                CONF_DOG_ID: "dog2",
                CONF_DOG_NAME: "Dog 2",
                CONF_DOG_SIZE: "small",
                "modules": {MODULE_WALK: True},
            },
        ]
        mock_config_entry.runtime_data = mock_runtime_data

        added_entities = []

        def mock_add_entities(entities, update_before_add=False):
            added_entities.extend(entities)

        with patch("custom_components.pawcontrol.select._async_add_entities_in_batches") as mock_batch:
            mock_batch.side_effect = lambda async_add_func, entities, **kwargs: async_add_func(entities, False)
            
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should create entities for both dogs
        assert len(added_entities) > 6  # At least 3 base selects per dog

        # Check that entities exist for both dogs
        dog_ids = {entity._dog_id for entity in added_entities}
        assert "dog1" in dog_ids
        assert "dog2" in dog_ids


class TestAsyncAddEntitiesInBatches:
    """Test the batch entity addition function."""

    @pytest.mark.asyncio
    async def test_add_entities_in_batches_small_list(self):
        """Test batch addition with small entity list."""
        entities = [Mock(spec=PawControlSelectBase) for _ in range(5)]
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
        entities = [Mock(spec=PawControlSelectBase) for _ in range(25)]
        added_entities = []
        batch_calls = []
        
        def mock_add_entities(batch, update_before_add=False):
            added_entities.extend(batch)
            batch_calls.append(len(batch))
        
        with patch("asyncio.sleep") as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=10, delay_between_batches=0.01
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


class TestCreateSelectFunctions:
    """Test the select creation helper functions."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_create_base_selects(self, mock_coordinator):
        """Test creation of base selects."""
        dog_config = {CONF_DOG_SIZE: "large"}
        
        selects = _create_base_selects(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )
        
        # Should create base selects
        assert len(selects) == 3
        
        select_types = [type(select).__name__ for select in selects]
        assert "PawControlDogSizeSelect" in select_types
        assert "PawControlPerformanceModeSelect" in select_types
        assert "PawControlNotificationPrioritySelect" in select_types

    def test_create_feeding_selects(self, mock_coordinator):
        """Test creation of feeding selects."""
        selects = _create_feeding_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create feeding selects
        assert len(selects) == 4
        
        select_types = [type(select).__name__ for select in selects]
        assert "PawControlFoodTypeSelect" in select_types
        assert "PawControlFeedingScheduleSelect" in select_types
        assert "PawControlDefaultMealTypeSelect" in select_types
        assert "PawControlFeedingModeSelect" in select_types

    def test_create_walk_selects(self, mock_coordinator):
        """Test creation of walk selects."""
        selects = _create_walk_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create walk selects
        assert len(selects) == 3
        
        select_types = [type(select).__name__ for select in selects]
        assert "PawControlWalkModeSelect" in select_types
        assert "PawControlWeatherPreferenceSelect" in select_types
        assert "PawControlWalkIntensitySelect" in select_types

    def test_create_gps_selects(self, mock_coordinator):
        """Test creation of GPS selects."""
        selects = _create_gps_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create GPS selects
        assert len(selects) == 3
        
        select_types = [type(select).__name__ for select in selects]
        assert "PawControlGPSSourceSelect" in select_types
        assert "PawControlTrackingModeSelect" in select_types
        assert "PawControlLocationAccuracySelect" in select_types

    def test_create_health_selects(self, mock_coordinator):
        """Test creation of health selects."""
        selects = _create_health_selects(mock_coordinator, "test_dog", "Test Dog")
        
        # Should create health selects
        assert len(selects) == 4
        
        select_types = [type(select).__name__ for select in selects]
        assert "PawControlHealthStatusSelect" in select_types
        assert "PawControlActivityLevelSelect" in select_types
        assert "PawControlMoodSelect" in select_types
        assert "PawControlGroomingTypeSelect" in select_types


class TestPawControlSelectBase:
    """Test the base select class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(return_value={
            "dog_info": {"dog_breed": "Test Breed", "dog_age": 5},
        })
        coordinator.get_module_data = Mock(return_value={})
        return coordinator

    @pytest.fixture
    def select_base(self, mock_coordinator):
        """Create a base select instance."""
        return PawControlSelectBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_select",
            options=["option1", "option2", "option3"],
            icon="mdi:test",
            initial_option="option1",
        )

    def test_select_base_initialization(self, select_base):
        """Test base select initialization."""
        assert select_base._dog_id == "test_dog"
        assert select_base._dog_name == "Test Dog"
        assert select_base._select_type == "test_select"
        assert select_base._attr_unique_id == "pawcontrol_test_dog_test_select"
        assert select_base._attr_name == "Test Dog Test Select"
        assert select_base._attr_options == ["option1", "option2", "option3"]
        assert select_base._attr_icon == "mdi:test"
        assert select_base._current_option == "option1"

    def test_select_base_device_info(self, select_base):
        """Test device info generation."""
        device_info = select_base._attr_device_info
        
        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"

    def test_select_base_current_option_property(self, select_base):
        """Test current_option property."""
        assert select_base.current_option == "option1"
        
        # Change option
        select_base._current_option = "option2"
        assert select_base.current_option == "option2"

    def test_select_base_extra_state_attributes(self, select_base):
        """Test extra state attributes."""
        attrs = select_base.extra_state_attributes
        
        assert attrs[ATTR_DOG_ID] == "test_dog"
        assert attrs[ATTR_DOG_NAME] == "Test Dog"
        assert attrs["select_type"] == "test_select"
        assert attrs["available_options"] == ["option1", "option2", "option3"]
        assert "last_changed" in attrs
        assert "dog_breed" in attrs

    def test_select_base_get_dog_data(self, select_base, mock_coordinator):
        """Test dog data retrieval."""
        data = select_base._get_dog_data()
        assert data is not None
        assert "dog_info" in data
        
        # Test with unavailable coordinator
        mock_coordinator.available = False
        data = select_base._get_dog_data()
        assert data is None

    def test_select_base_get_module_data(self, select_base, mock_coordinator):
        """Test module data retrieval."""
        mock_coordinator.get_module_data.return_value = {"test_data": "value"}
        
        data = select_base._get_module_data("test_module")
        assert data == {"test_data": "value"}
        
        mock_coordinator.get_module_data.assert_called_once_with("test_dog", "test_module")

    def test_select_base_available_property(self, select_base, mock_coordinator):
        """Test availability property."""
        # Should be available when coordinator is available and has data
        assert select_base.available is True
        
        # Should be unavailable when coordinator is unavailable
        mock_coordinator.available = False
        assert select_base.available is False
        
        # Should be unavailable when no dog data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        assert select_base.available is False

    @pytest.mark.asyncio
    async def test_select_base_async_added_to_hass(self, select_base, hass):
        """Test async_added_to_hass with state restoration."""
        select_base.hass = hass
        
        # Mock last state
        last_state = Mock()
        last_state.state = "option2"
        
        with patch.object(select_base, "async_get_last_state", return_value=last_state):
            await select_base.async_added_to_hass()
        
        # Should restore state
        assert select_base._current_option == "option2"

    @pytest.mark.asyncio
    async def test_select_base_async_added_to_hass_invalid_state(self, select_base, hass):
        """Test async_added_to_hass with invalid previous state."""
        select_base.hass = hass
        
        # Mock last state with invalid option
        last_state = Mock()
        last_state.state = "invalid_option"
        
        with patch.object(select_base, "async_get_last_state", return_value=last_state):
            await select_base.async_added_to_hass()
        
        # Should keep initial state
        assert select_base._current_option == "option1"

    @pytest.mark.asyncio
    async def test_select_base_async_added_to_hass_no_state(self, select_base, hass):
        """Test async_added_to_hass without previous state."""
        select_base.hass = hass
        
        with patch.object(select_base, "async_get_last_state", return_value=None):
            await select_base.async_added_to_hass()
        
        # Should keep initial state
        assert select_base._current_option == "option1"

    @pytest.mark.asyncio
    async def test_select_base_async_select_option_valid(self, select_base, hass):
        """Test selecting valid option."""
        select_base.hass = hass
        select_base.async_write_ha_state = Mock()
        
        await select_base.async_select_option("option2")
        
        assert select_base._current_option == "option2"
        select_base.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_base_async_select_option_invalid(self, select_base, hass):
        """Test selecting invalid option."""
        select_base.hass = hass
        
        with pytest.raises(HomeAssistantError, match="Invalid option 'invalid_option'"):
            await select_base.async_select_option("invalid_option")

    @pytest.mark.asyncio
    async def test_select_base_async_select_option_error(self, select_base, hass):
        """Test selecting option with error in implementation."""
        select_base.hass = hass
        
        # Mock _async_set_select_option to raise exception
        select_base._async_set_select_option = AsyncMock(side_effect=Exception("Test error"))
        
        with pytest.raises(HomeAssistantError, match="Failed to set test_select"):
            await select_base.async_select_option("option2")


class TestSpecificSelectClasses:
    """Test specific select implementations."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock(return_value={
            "dog_info": {"dog_breed": "Test Breed"},
        })
        coordinator.get_module_data = Mock(return_value={})
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_hass(self):
        """Create a mock Home Assistant instance."""
        hass = Mock()
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "notifications": Mock(),
                }
            }
        }
        return hass

    def test_dog_size_select_initialization(self, mock_coordinator):
        """Test dog size select initialization."""
        dog_config = {CONF_DOG_SIZE: "large"}
        
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )
        
        assert select._select_type == "size"
        assert select._attr_options == DOG_SIZES
        assert select._attr_icon == "mdi:dog"
        assert select._attr_entity_category == EntityCategory.CONFIG
        assert select._current_option == "large"

    def test_dog_size_select_get_size_info(self, mock_coordinator):
        """Test dog size select size info."""
        dog_config = {CONF_DOG_SIZE: "medium"}
        
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )
        
        size_info = select._get_size_info("medium")
        assert "weight_range" in size_info
        assert "exercise_needs" in size_info
        assert "food_portion" in size_info

    def test_dog_size_select_extra_state_attributes(self, mock_coordinator):
        """Test dog size select extra state attributes."""
        dog_config = {CONF_DOG_SIZE: "small"}
        
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )
        
        attrs = select.extra_state_attributes
        assert "weight_range" in attrs
        assert "exercise_needs" in attrs
        assert "food_portion" in attrs

    @pytest.mark.asyncio
    async def test_dog_size_select_set_option(self, mock_coordinator):
        """Test dog size select option setting."""
        dog_config = {CONF_DOG_SIZE: "medium"}
        
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )
        
        await select._async_set_select_option("large")
        
        # Should call coordinator refresh
        mock_coordinator.async_refresh_dog.assert_called_once_with("test_dog")

    def test_performance_mode_select_initialization(self, mock_coordinator):
        """Test performance mode select initialization."""
        select = PawControlPerformanceModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "performance_mode"
        assert select._attr_options == PERFORMANCE_MODES
        assert select._attr_icon == "mdi:speedometer"
        assert select._current_option == "balanced"

    def test_performance_mode_select_get_mode_info(self, mock_coordinator):
        """Test performance mode select mode info."""
        select = PawControlPerformanceModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        mode_info = select._get_performance_mode_info("full")
        assert "description" in mode_info
        assert "update_interval" in mode_info
        assert "battery_impact" in mode_info

    def test_notification_priority_select_initialization(self, mock_coordinator):
        """Test notification priority select initialization."""
        select = PawControlNotificationPrioritySelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "notification_priority"
        assert select._attr_options == NOTIFICATION_PRIORITIES
        assert select._attr_icon == "mdi:bell-ring"
        assert select._current_option == "normal"

    def test_food_type_select_initialization(self, mock_coordinator):
        """Test food type select initialization."""
        select = PawControlFoodTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "food_type"
        assert select._attr_options == FOOD_TYPES
        assert select._attr_icon == "mdi:food"
        assert select._current_option == "dry_food"

    def test_food_type_select_get_food_info(self, mock_coordinator):
        """Test food type select food info."""
        select = PawControlFoodTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        food_info = select._get_food_type_info("wet_food")
        assert "calories_per_gram" in food_info
        assert "moisture_content" in food_info
        assert "storage" in food_info
        assert "shelf_life" in food_info

    def test_feeding_schedule_select_initialization(self, mock_coordinator):
        """Test feeding schedule select initialization."""
        select = PawControlFeedingScheduleSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "feeding_schedule"
        assert select._attr_options == FEEDING_SCHEDULES
        assert select._attr_icon == "mdi:calendar-clock"
        assert select._current_option == "flexible"

    def test_default_meal_type_select_initialization(self, mock_coordinator):
        """Test default meal type select initialization."""
        select = PawControlDefaultMealTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "default_meal_type"
        assert select._attr_options == MEAL_TYPES
        assert select._attr_icon == "mdi:food-drumstick"
        assert select._current_option == "dinner"

    def test_feeding_mode_select_initialization(self, mock_coordinator):
        """Test feeding mode select initialization."""
        select = PawControlFeedingModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "feeding_mode"
        assert select._attr_options == ["manual", "scheduled", "automatic"]
        assert select._attr_icon == "mdi:cog"
        assert select._current_option == "manual"

    def test_walk_mode_select_initialization(self, mock_coordinator):
        """Test walk mode select initialization."""
        select = PawControlWalkModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "walk_mode"
        assert select._attr_options == WALK_MODES
        assert select._attr_icon == "mdi:walk"
        assert select._current_option == "automatic"

    def test_walk_mode_select_get_mode_info(self, mock_coordinator):
        """Test walk mode select mode info."""
        select = PawControlWalkModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        mode_info = select._get_walk_mode_info("hybrid")
        assert "description" in mode_info
        assert "gps_required" in mode_info
        assert "accuracy" in mode_info

    def test_weather_preference_select_initialization(self, mock_coordinator):
        """Test weather preference select initialization."""
        select = PawControlWeatherPreferenceSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "weather_preference"
        assert select._attr_options == WEATHER_CONDITIONS
        assert select._attr_icon == "mdi:weather-partly-cloudy"
        assert select._current_option == "any"

    def test_walk_intensity_select_initialization(self, mock_coordinator):
        """Test walk intensity select initialization."""
        select = PawControlWalkIntensitySelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "walk_intensity"
        assert select._attr_options == ["relaxed", "moderate", "vigorous", "mixed"]
        assert select._attr_icon == "mdi:run"
        assert select._current_option == "moderate"

    def test_gps_source_select_initialization(self, mock_coordinator):
        """Test GPS source select initialization."""
        select = PawControlGPSSourceSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "gps_source"
        assert select._attr_options == GPS_SOURCES
        assert select._attr_icon == "mdi:crosshairs-gps"
        assert select._attr_entity_category == EntityCategory.CONFIG
        assert select._current_option == "device_tracker"

    def test_gps_source_select_get_source_info(self, mock_coordinator):
        """Test GPS source select source info."""
        select = PawControlGPSSourceSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        source_info = select._get_gps_source_info("tractive")
        assert "accuracy" in source_info
        assert "update_frequency" in source_info
        assert "battery_usage" in source_info

    def test_tracking_mode_select_initialization(self, mock_coordinator):
        """Test tracking mode select initialization."""
        select = PawControlTrackingModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "tracking_mode"
        assert select._attr_options == TRACKING_MODES
        assert select._attr_icon == "mdi:map-marker"
        assert select._current_option == "interval"

    def test_location_accuracy_select_initialization(self, mock_coordinator):
        """Test location accuracy select initialization."""
        select = PawControlLocationAccuracySelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "location_accuracy"
        assert select._attr_options == ["low", "balanced", "high", "best"]
        assert select._attr_icon == "mdi:crosshairs"
        assert select._attr_entity_category == EntityCategory.CONFIG
        assert select._current_option == "balanced"

    def test_health_status_select_initialization(self, mock_coordinator):
        """Test health status select initialization."""
        select = PawControlHealthStatusSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "health_status"
        assert select._attr_options == HEALTH_STATUS_OPTIONS
        assert select._attr_icon == "mdi:heart-pulse"
        assert select._current_option == "good"

    def test_health_status_select_current_option_from_data(self, mock_coordinator):
        """Test health status select reads from data."""
        mock_coordinator.get_module_data.return_value = {"health_status": "excellent"}
        
        select = PawControlHealthStatusSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        # Should read from data
        assert select.current_option == "excellent"

    def test_activity_level_select_initialization(self, mock_coordinator):
        """Test activity level select initialization."""
        select = PawControlActivityLevelSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "activity_level"
        assert select._attr_options == ACTIVITY_LEVELS
        assert select._attr_icon == "mdi:run"
        assert select._current_option == "normal"

    def test_activity_level_select_current_option_from_data(self, mock_coordinator):
        """Test activity level select reads from data."""
        mock_coordinator.get_module_data.return_value = {"activity_level": "high"}
        
        select = PawControlActivityLevelSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        # Should read from data
        assert select.current_option == "high"

    def test_mood_select_initialization(self, mock_coordinator):
        """Test mood select initialization."""
        select = PawControlMoodSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "mood"
        assert select._attr_options == MOOD_OPTIONS
        assert select._attr_icon == "mdi:emoticon"
        assert select._current_option == "happy"

    def test_grooming_type_select_initialization(self, mock_coordinator):
        """Test grooming type select initialization."""
        select = PawControlGroomingTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        assert select._select_type == "grooming_type"
        assert select._attr_options == GROOMING_TYPES
        assert select._attr_icon == "mdi:content-cut"
        assert select._current_option == "brush"

    def test_grooming_type_select_get_grooming_info(self, mock_coordinator):
        """Test grooming type select grooming info."""
        select = PawControlGroomingTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        grooming_info = select._get_grooming_type_info("full_grooming")
        assert "frequency" in grooming_info
        assert "duration" in grooming_info
        assert "difficulty" in grooming_info

    def test_grooming_type_select_extra_state_attributes(self, mock_coordinator):
        """Test grooming type select extra state attributes."""
        select = PawControlGroomingTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        attrs = select.extra_state_attributes
        assert "frequency" in attrs
        assert "duration" in attrs
        assert "difficulty" in attrs


class TestSelectConstants:
    """Test select platform constants and option lists."""

    def test_walk_modes_defined(self):
        """Test that walk modes are properly defined."""
        assert len(WALK_MODES) == 3
        assert "automatic" in WALK_MODES
        assert "manual" in WALK_MODES
        assert "hybrid" in WALK_MODES

    def test_notification_priorities_defined(self):
        """Test that notification priorities are properly defined."""
        assert len(NOTIFICATION_PRIORITIES) == 4
        assert "low" in NOTIFICATION_PRIORITIES
        assert "normal" in NOTIFICATION_PRIORITIES
        assert "high" in NOTIFICATION_PRIORITIES
        assert "urgent" in NOTIFICATION_PRIORITIES

    def test_tracking_modes_defined(self):
        """Test that tracking modes are properly defined."""
        assert len(TRACKING_MODES) == 4
        assert "continuous" in TRACKING_MODES
        assert "interval" in TRACKING_MODES
        assert "on_demand" in TRACKING_MODES
        assert "battery_saver" in TRACKING_MODES

    def test_feeding_schedules_defined(self):
        """Test that feeding schedules are properly defined."""
        assert len(FEEDING_SCHEDULES) == 3
        assert "flexible" in FEEDING_SCHEDULES
        assert "strict" in FEEDING_SCHEDULES
        assert "custom" in FEEDING_SCHEDULES

    def test_grooming_types_defined(self):
        """Test that grooming types are properly defined."""
        assert len(GROOMING_TYPES) == 6
        assert "bath" in GROOMING_TYPES
        assert "brush" in GROOMING_TYPES
        assert "nails" in GROOMING_TYPES
        assert "teeth" in GROOMING_TYPES
        assert "trim" in GROOMING_TYPES
        assert "full_grooming" in GROOMING_TYPES

    def test_weather_conditions_defined(self):
        """Test that weather conditions are properly defined."""
        assert len(WEATHER_CONDITIONS) == 7
        assert "any" in WEATHER_CONDITIONS
        assert "sunny" in WEATHER_CONDITIONS
        assert "cloudy" in WEATHER_CONDITIONS
        assert "light_rain" in WEATHER_CONDITIONS
        assert "no_rain" in WEATHER_CONDITIONS
        assert "warm" in WEATHER_CONDITIONS
        assert "cool" in WEATHER_CONDITIONS


class TestSelectErrorHandling:
    """Test select error handling and edge cases."""

    @pytest.fixture
    def mock_coordinator_unavailable(self):
        """Create an unavailable coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = False
        coordinator.get_dog_data = Mock(return_value=None)
        return coordinator

    def test_select_unavailable_coordinator(self, mock_coordinator_unavailable):
        """Test select behavior with unavailable coordinator."""
        select = PawControlDogSizeSelect(
            mock_coordinator_unavailable, "test_dog", "Test Dog", {}
        )
        
        # Should be unavailable
        assert select.available is False

    def test_select_missing_dog_data(self, mock_coordinator_unavailable):
        """Test select behavior when dog data is missing."""
        select = PawControlFoodTypeSelect(
            mock_coordinator_unavailable, "test_dog", "Test Dog"
        )
        
        # Should handle missing data gracefully
        data = select._get_dog_data()
        assert data is None

    @pytest.mark.asyncio
    async def test_select_set_option_error_handling(self, mock_coordinator):
        """Test select option setting error handling."""
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", {}
        )
        
        # Mock coordinator to raise exception
        mock_coordinator.async_refresh_dog = AsyncMock(side_effect=Exception("Test error"))
        
        # Should not raise exception in base implementation
        await select._async_set_select_option("large")

    def test_select_get_info_methods_with_none(self, mock_coordinator):
        """Test info getter methods with None input."""
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", {}
        )
        
        # Should handle None gracefully
        size_info = select._get_size_info(None)
        assert size_info == {}

        food_select = PawControlFoodTypeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        food_info = food_select._get_food_type_info(None)
        assert food_info == {}

    def test_select_get_info_methods_with_unknown_value(self, mock_coordinator):
        """Test info getter methods with unknown values."""
        select = PawControlPerformanceModeSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        # Should handle unknown values gracefully
        mode_info = select._get_performance_mode_info("unknown_mode")
        assert mode_info == {}


class TestSelectIntegration:
    """Test select integration with other components."""

    @pytest.fixture
    def mock_hass_with_full_data(self):
        """Create a mock Home Assistant instance with full data."""
        hass = Mock()
        
        # Mock notification manager
        notification_manager = Mock()
        
        hass.data = {
            DOMAIN: {
                "test_entry": {
                    "notifications": notification_manager,
                }
            }
        }
        return hass

    @pytest.mark.asyncio
    async def test_select_coordinator_integration(self, mock_coordinator):
        """Test select integration with coordinator."""
        select = PawControlDogSizeSelect(
            mock_coordinator, "test_dog", "Test Dog", {}
        )
        
        await select._async_set_select_option("large")
        
        # Should call coordinator methods
        mock_coordinator.async_refresh_dog.assert_called_once_with("test_dog")

    @pytest.mark.asyncio
    async def test_select_notification_manager_integration(
        self, mock_coordinator, mock_hass_with_full_data
    ):
        """Test select integration with notification manager."""
        select = PawControlNotificationPrioritySelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        select.hass = mock_hass_with_full_data
        
        await select._async_set_select_option("high")
        
        # Should access notification manager from hass.data
        assert mock_hass_with_full_data.data[DOMAIN]["test_entry"]["notifications"] is not None

    def test_select_module_data_integration(self, mock_coordinator):
        """Test select integration with module data."""
        mock_coordinator.get_module_data.return_value = {"health_status": "excellent"}
        
        select = PawControlHealthStatusSelect(
            mock_coordinator, "test_dog", "Test Dog"
        )
        
        # Should read from module data
        assert select.current_option == "excellent"
        mock_coordinator.get_module_data.assert_called_with("test_dog", "health")

    def test_select_device_grouping(self, mock_coordinator):
        """Test that selects are properly grouped by device."""
        select1 = PawControlDogSizeSelect(
            mock_coordinator, "dog1", "Dog 1", {}
        )
        select2 = PawControlFoodTypeSelect(
            mock_coordinator, "dog1", "Dog 1"
        )
        select3 = PawControlDogSizeSelect(
            mock_coordinator, "dog2", "Dog 2", {}
        )
        
        # Same dog selects should have same device identifiers
        assert select1._attr_device_info["identifiers"] == select2._attr_device_info["identifiers"]
        
        # Different dog selects should have different device identifiers
        assert select1._attr_device_info["identifiers"] != select3._attr_device_info["identifiers"]
