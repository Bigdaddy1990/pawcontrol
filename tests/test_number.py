"""Comprehensive tests for Paw Control number platform.

Tests all number entities, batching logic, state persistence,
value validation, and error handling scenarios.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    DOMAIN,
    MAX_DOG_AGE,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_WEIGHT,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.number import (
    DEFAULT_ACTIVITY_GOAL,
    DEFAULT_FEEDING_REMINDER_HOURS,
    DEFAULT_GPS_ACCURACY_THRESHOLD,
    DEFAULT_WALK_DURATION_TARGET,
    PawControlActivityGoalNumber,
    PawControlCalorieTargetNumber,
    PawControlDailyFoodAmountNumber,
    PawControlDailyWalkTargetNumber,
    PawControlDogAgeNumber,
    PawControlDogWeightNumber,
    PawControlFeedingReminderHoursNumber,
    PawControlGPSAccuracyThresholdNumber,
    PawControlGPSBatteryThresholdNumber,
    PawControlGPSUpdateIntervalNumber,
    PawControlGeofenceRadiusNumber,
    PawControlGroomingIntervalNumber,
    PawControlHealthScoreThresholdNumber,
    PawControlLocationUpdateDistanceNumber,
    PawControlMaxWalkSpeedNumber,
    PawControlMealsPerDayNumber,
    PawControlNumberBase,
    PawControlPortionSizeNumber,
    PawControlTargetWeightNumber,
    PawControlVetCheckupIntervalNumber,
    PawControlWalkDistanceTargetNumber,
    PawControlWalkDurationTargetNumber,
    PawControlWalkReminderHoursNumber,
    PawControlWeightChangeThresholdNumber,
    _async_add_entities_in_batches,
    _create_base_numbers,
    _create_feeding_numbers,
    _create_gps_numbers,
    _create_health_numbers,
    _create_walk_numbers,
    async_setup_entry,
)
from homeassistant.components.number import NumberDeviceClass, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory


class TestAsyncSetupEntry:
    """Test the async_setup_entry function."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def mock_entry(self):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog",
                    CONF_DOG_NAME: "Test Dog",
                    CONF_DOG_WEIGHT: 25.0,
                    CONF_DOG_AGE: 5,
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                },
                {
                    CONF_DOG_ID: "simple_dog",
                    CONF_DOG_NAME: "Simple Dog",
                    CONF_DOG_WEIGHT: 15.0,
                    CONF_DOG_AGE: 3,
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: False,
                        MODULE_GPS: False,
                        MODULE_HEALTH: False,
                    },
                },
            ]
        }
        return entry

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_runtime_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test setup with runtime_data."""
        # Setup runtime_data
        mock_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": mock_entry.data[CONF_DOGS],
        }

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should have called async_add_entities
        async_add_entities.assert_called()
        
        # Verify entities were created
        call_args = async_add_entities.call_args_list
        total_entities = sum(len(call[0][0]) for call in call_args)
        
        # First dog with all modules: 3 base + 5 feeding + 5 walk + 5 gps + 5 health = 23
        # Second dog with only feeding: 3 base + 5 feeding = 8
        # Total: 31 entities
        assert total_entities >= 30  # Should have many entities

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_legacy_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test setup with legacy hass.data."""
        # Setup legacy data structure
        mock_entry.runtime_data = None
        hass.data[DOMAIN] = {
            "test_entry": {"coordinator": mock_coordinator}
        }

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Should have called async_add_entities
        async_add_entities.assert_called()

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup with no dogs configured."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {CONF_DOGS: []}
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [],
        }

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        # Should still call async_add_entities but with empty list
        async_add_entities.assert_called_once_with([], update_before_add=False)

    @pytest.mark.asyncio
    async def test_async_setup_entry_selective_modules(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup with selective module enablement."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "feeding_only_dog",
                    CONF_DOG_NAME: "Feeding Only Dog",
                    CONF_DOG_WEIGHT: 20.0,
                    CONF_DOG_AGE: 4,
                    "modules": {MODULE_FEEDING: True},  # Only feeding enabled
                }
            ]
        }
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": entry.data[CONF_DOGS],
        }

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        # Count total entities across all batches
        total_entities = sum(
            len(call[0][0]) for call in async_add_entities.call_args_list
        )
        
        # Should have base numbers (3) + feeding numbers (5) = 8 entities
        assert total_entities == 8


class TestBatchingFunction:
    """Test the batching helper function."""

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_single_batch(self):
        """Test batching with entities that fit in single batch."""
        async_add_entities_func = AsyncMock()
        entities = [Mock() for _ in range(5)]

        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=12
        )

        # Should call once with all entities
        async_add_entities_func.assert_called_once_with(entities, update_before_add=False)

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_multiple_batches(self):
        """Test batching with entities requiring multiple batches."""
        async_add_entities_func = AsyncMock()
        entities = [Mock() for _ in range(25)]

        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=10
        )

        # Should call 3 times (10 + 10 + 5)
        assert async_add_entities_func.call_count == 3
        
        # Verify batch sizes
        call_args = async_add_entities_func.call_args_list
        assert len(call_args[0][0][0]) == 10  # First batch
        assert len(call_args[1][0][0]) == 10  # Second batch
        assert len(call_args[2][0][0]) == 5   # Third batch

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_empty_list(self):
        """Test batching with empty entity list."""
        async_add_entities_func = AsyncMock()
        entities = []

        await _async_add_entities_in_batches(async_add_entities_func, entities)

        # Should not call the function
        async_add_entities_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_with_delay(self):
        """Test that delay is applied between batches."""
        async_add_entities_func = AsyncMock()
        entities = [Mock() for _ in range(15)]

        # Use very small delay for testing
        start_time = asyncio.get_event_loop().time()
        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=8, delay_between_batches=0.01
        )
        end_time = asyncio.get_event_loop().time()

        # Should have taken at least one delay period
        assert end_time - start_time >= 0.01
        assert async_add_entities_func.call_count == 2


class TestCreationFunctions:
    """Test number entity creation functions."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_create_base_numbers(self, mock_coordinator):
        """Test creating base numbers."""
        dog_config = {
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_AGE: 5,
        }

        numbers = _create_base_numbers(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

        assert len(numbers) == 3
        assert isinstance(numbers[0], PawControlDogWeightNumber)
        assert isinstance(numbers[1], PawControlDogAgeNumber)
        assert isinstance(numbers[2], PawControlActivityGoalNumber)

        # Verify all have correct dog info
        for number in numbers:
            assert number._dog_id == "test_dog"
            assert number._dog_name == "Test Dog"

    def test_create_feeding_numbers(self, mock_coordinator):
        """Test creating feeding numbers."""
        numbers = _create_feeding_numbers(mock_coordinator, "test_dog", "Test Dog")

        assert len(numbers) == 5
        expected_types = [
            PawControlDailyFoodAmountNumber,
            PawControlFeedingReminderHoursNumber,
            PawControlMealsPerDayNumber,
            PawControlPortionSizeNumber,
            PawControlCalorieTargetNumber,
        ]

        for i, expected_type in enumerate(expected_types):
            assert isinstance(numbers[i], expected_type)

    def test_create_walk_numbers(self, mock_coordinator):
        """Test creating walk numbers."""
        numbers = _create_walk_numbers(mock_coordinator, "test_dog", "Test Dog")

        assert len(numbers) == 5
        expected_types = [
            PawControlDailyWalkTargetNumber,
            PawControlWalkDurationTargetNumber,
            PawControlWalkDistanceTargetNumber,
            PawControlWalkReminderHoursNumber,
            PawControlMaxWalkSpeedNumber,
        ]

        for i, expected_type in enumerate(expected_types):
            assert isinstance(numbers[i], expected_type)

    def test_create_gps_numbers(self, mock_coordinator):
        """Test creating GPS numbers."""
        numbers = _create_gps_numbers(mock_coordinator, "test_dog", "Test Dog")

        assert len(numbers) == 5
        expected_types = [
            PawControlGPSAccuracyThresholdNumber,
            PawControlGPSUpdateIntervalNumber,
            PawControlGeofenceRadiusNumber,
            PawControlLocationUpdateDistanceNumber,
            PawControlGPSBatteryThresholdNumber,
        ]

        for i, expected_type in enumerate(expected_types):
            assert isinstance(numbers[i], expected_type)

    def test_create_health_numbers(self, mock_coordinator):
        """Test creating health numbers."""
        numbers = _create_health_numbers(mock_coordinator, "test_dog", "Test Dog")

        assert len(numbers) == 5
        expected_types = [
            PawControlTargetWeightNumber,
            PawControlWeightChangeThresholdNumber,
            PawControlGroomingIntervalNumber,
            PawControlVetCheckupIntervalNumber,
            PawControlHealthScoreThresholdNumber,
        ]

        for i, expected_type in enumerate(expected_types):
            assert isinstance(numbers[i], expected_type)


class TestPawControlNumberBase:
    """Test the base number class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "dog_info": {
                "dog_breed": "Golden Retriever",
                "dog_age": 5,
                "dog_size": "large",
                "dog_weight": 30.0,
            }
        }
        return coordinator

    @pytest.fixture
    def base_number(self, mock_coordinator):
        """Create a base number instance."""
        return PawControlNumberBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_number",
            device_class=NumberDeviceClass.WEIGHT,
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfMass.KILOGRAMS,
            native_min_value=1.0,
            native_max_value=100.0,
            native_step=0.1,
            icon="mdi:test",
            entity_category=EntityCategory.CONFIG,
            initial_value=25.0,
        )

    def test_number_initialization(self, base_number):
        """Test number initialization."""
        assert base_number._dog_id == "test_dog"
        assert base_number._dog_name == "Test Dog"
        assert base_number._number_type == "test_number"
        assert base_number._value == 25.0

        # Check attributes
        assert base_number._attr_unique_id == "pawcontrol_test_dog_test_number"
        assert base_number._attr_name == "Test Dog Test Number"
        assert base_number._attr_device_class == NumberDeviceClass.WEIGHT
        assert base_number._attr_mode == NumberMode.BOX
        assert base_number._attr_native_unit_of_measurement == UnitOfMass.KILOGRAMS
        assert base_number._attr_native_min_value == 1.0
        assert base_number._attr_native_max_value == 100.0
        assert base_number._attr_native_step == 0.1
        assert base_number._attr_icon == "mdi:test"
        assert base_number._attr_entity_category == EntityCategory.CONFIG

    def test_device_info(self, base_number):
        """Test device info configuration."""
        device_info = base_number._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"
        assert "configuration_url" in device_info

    def test_native_value(self, base_number):
        """Test native value property."""
        assert base_number.native_value == 25.0

        # Change value
        base_number._value = 30.0
        assert base_number.native_value == 30.0

    def test_extra_state_attributes(self, base_number):
        """Test extra state attributes."""
        attrs = base_number.extra_state_attributes

        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        assert attrs["number_type"] == "test_number"
        assert attrs["min_value"] == 1.0
        assert attrs["max_value"] == 100.0
        assert attrs["step"] == 0.1
        assert "last_changed" in attrs

        # Dog info should be included
        assert attrs["dog_breed"] == "Golden Retriever"
        assert attrs["dog_age"] == 5
        assert attrs["dog_size"] == "large"

    def test_extra_state_attributes_no_dog_data(self, mock_coordinator):
        """Test extra state attributes when no dog data available."""
        mock_coordinator.get_dog_data.return_value = None

        number = PawControlNumberBase(
            mock_coordinator, "test_dog", "Test Dog", "test_number"
        )

        attrs = number.extra_state_attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        # Dog info should not be present
        assert "dog_breed" not in attrs

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_restore(self, base_number):
        """Test async_added_to_hass with state restoration."""
        # Mock last state
        mock_state = Mock()
        mock_state.state = "35.5"

        with patch.object(base_number, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state

            await base_number.async_added_to_hass()

            # Should restore the value
            assert base_number._value == 35.5

    @pytest.mark.asyncio
    async def test_async_added_to_hass_invalid_restore(self, base_number):
        """Test async_added_to_hass with invalid restore state."""
        # Mock invalid last state
        mock_state = Mock()
        mock_state.state = "invalid_number"

        with patch.object(base_number, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state

            await base_number.async_added_to_hass()

            # Should keep original value
            assert base_number._value == 25.0

    @pytest.mark.asyncio
    async def test_async_added_to_hass_no_restore(self, base_number):
        """Test async_added_to_hass with no previous state."""
        with patch.object(base_number, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = None

            await base_number.async_added_to_hass()

            # Should keep original value
            assert base_number._value == 25.0

    @pytest.mark.asyncio
    async def test_async_set_native_value_valid(self, base_number):
        """Test setting valid native value."""
        with patch.object(base_number, "_async_set_number_value") as mock_set, \
             patch.object(base_number, "async_write_ha_state") as mock_write:
            
            await base_number.async_set_native_value(50.0)

            mock_set.assert_called_once_with(50.0)
            assert base_number._value == 50.0
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_set_native_value_too_low(self, base_number):
        """Test setting value below minimum."""
        with pytest.raises(HomeAssistantError, match="Value .* is outside allowed range"):
            await base_number.async_set_native_value(0.5)  # Below minimum of 1.0

    @pytest.mark.asyncio
    async def test_async_set_native_value_too_high(self, base_number):
        """Test setting value above maximum."""
        with pytest.raises(HomeAssistantError, match="Value .* is outside allowed range"):
            await base_number.async_set_native_value(150.0)  # Above maximum of 100.0

    @pytest.mark.asyncio
    async def test_async_set_native_value_implementation_error(self, base_number):
        """Test error in implementation method."""
        with patch.object(base_number, "_async_set_number_value") as mock_set:
            mock_set.side_effect = Exception("Implementation error")

            with pytest.raises(HomeAssistantError, match="Failed to set test_number"):
                await base_number.async_set_native_value(50.0)

    def test_get_dog_data(self, base_number, mock_coordinator):
        """Test getting dog data."""
        result = base_number._get_dog_data()

        mock_coordinator.get_dog_data.assert_called_once_with("test_dog")
        assert result is not None
        assert "dog_info" in result

    def test_get_dog_data_coordinator_unavailable(self, base_number, mock_coordinator):
        """Test getting dog data when coordinator unavailable."""
        mock_coordinator.available = False

        result = base_number._get_dog_data()

        assert result is None
        mock_coordinator.get_dog_data.assert_not_called()

    def test_get_module_data(self, base_number, mock_coordinator):
        """Test getting module data."""
        mock_coordinator.get_module_data.return_value = {"test": "data"}

        result = base_number._get_module_data("feeding")

        mock_coordinator.get_module_data.assert_called_once_with("test_dog", "feeding")
        assert result == {"test": "data"}

    def test_available_property(self, base_number, mock_coordinator):
        """Test number availability."""
        # Coordinator available and dog data exists
        assert base_number.available is True

        # Coordinator unavailable
        mock_coordinator.available = False
        assert base_number.available is False

        # Coordinator available but no dog data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        assert base_number.available is False


class TestDogWeightNumber:
    """Test the dog weight number entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    @pytest.fixture
    def weight_number(self, mock_coordinator):
        """Create a dog weight number."""
        dog_config = {CONF_DOG_WEIGHT: 25.0}
        return PawControlDogWeightNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

    def test_initialization(self, weight_number):
        """Test weight number initialization."""
        assert weight_number._number_type == "weight"
        assert weight_number._attr_device_class == NumberDeviceClass.WEIGHT
        assert weight_number._attr_mode == NumberMode.BOX
        assert weight_number._attr_native_unit_of_measurement == UnitOfMass.KILOGRAMS
        assert weight_number._attr_native_min_value == MIN_DOG_WEIGHT
        assert weight_number._attr_native_max_value == MAX_DOG_WEIGHT
        assert weight_number._attr_native_step == 0.1
        assert weight_number._attr_icon == "mdi:scale"
        assert weight_number._value == 25.0

    @pytest.mark.asyncio
    async def test_async_set_number_value(self, weight_number, mock_coordinator):
        """Test setting weight value."""
        await weight_number._async_set_number_value(30.0)

        # Should trigger dog refresh
        mock_coordinator.async_refresh_dog.assert_called_once_with("test_dog")

    def test_extra_state_attributes_with_health_data(self, weight_number, mock_coordinator):
        """Test extra state attributes with health data."""
        # Mock health module data
        mock_coordinator.get_module_data.return_value = {
            "weight_trend": "increasing",
            "weight_change_percent": 5.2,
            "last_weight_date": "2025-01-15",
            "target_weight": 27.0,
        }

        attrs = weight_number.extra_state_attributes

        assert attrs["weight_trend"] == "increasing"
        assert attrs["weight_change_percent"] == 5.2
        assert attrs["last_weight_date"] == "2025-01-15"
        assert attrs["target_weight"] == 27.0

    def test_extra_state_attributes_no_health_data(self, weight_number, mock_coordinator):
        """Test extra state attributes without health data."""
        mock_coordinator.get_module_data.return_value = None

        attrs = weight_number.extra_state_attributes

        # Should not have health-specific attributes
        assert "weight_trend" not in attrs
        assert "weight_change_percent" not in attrs


class TestDogAgeNumber:
    """Test the dog age number entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator with config entry."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        
        # Mock config entry with runtime_data
        mock_entry = Mock()
        mock_data_manager = Mock()
        mock_data_manager.async_update_dog_data = AsyncMock()
        
        mock_entry.runtime_data = {"data_manager": mock_data_manager}
        coordinator.config_entry = mock_entry
        
        return coordinator

    @pytest.fixture
    def age_number(self, mock_coordinator):
        """Create a dog age number."""
        dog_config = {CONF_DOG_AGE: 5}
        return PawControlDogAgeNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

    def test_initialization(self, age_number):
        """Test age number initialization."""
        assert age_number._number_type == "age"
        assert age_number._attr_mode == NumberMode.BOX
        assert age_number._attr_native_unit_of_measurement == "years"
        assert age_number._attr_native_min_value == MIN_DOG_AGE
        assert age_number._attr_native_max_value == MAX_DOG_AGE
        assert age_number._attr_native_step == 1
        assert age_number._attr_icon == "mdi:calendar"
        assert age_number._attr_entity_category == EntityCategory.CONFIG
        assert age_number._value == 5

    @pytest.mark.asyncio
    async def test_async_set_number_value_with_data_manager(self, age_number, mock_coordinator):
        """Test setting age value with data manager."""
        # Mock dog data
        mock_coordinator.get_dog_data.return_value = {"profile": {}}

        await age_number._async_set_number_value(6.0)

        # Should update data manager
        data_manager = mock_coordinator.config_entry.runtime_data["data_manager"]
        data_manager.async_update_dog_data.assert_called_once_with(
            "test_dog", {"profile": {CONF_DOG_AGE: 6}}
        )

    @pytest.mark.asyncio
    async def test_async_set_number_value_no_data_manager(self, mock_coordinator):
        """Test setting age value without data manager."""
        # Remove data manager from runtime_data
        mock_coordinator.config_entry.runtime_data = {}
        
        dog_config = {CONF_DOG_AGE: 5}
        age_number = PawControlDogAgeNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

        # Mock dog data
        mock_coordinator.get_dog_data.return_value = {"profile": {}}

        # Should not raise error
        await age_number._async_set_number_value(6.0)

    @pytest.mark.asyncio
    async def test_async_set_number_value_data_manager_error(self, age_number, mock_coordinator):
        """Test setting age value with data manager error."""
        # Mock dog data
        mock_coordinator.get_dog_data.return_value = {"profile": {}}
        
        # Make data manager throw error
        data_manager = mock_coordinator.config_entry.runtime_data["data_manager"]
        data_manager.async_update_dog_data.side_effect = Exception("Database error")

        # Should not raise error (best effort)
        await age_number._async_set_number_value(6.0)


class TestActivityGoalNumber:
    """Test the activity goal number entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def activity_number(self, mock_coordinator):
        """Create an activity goal number."""
        return PawControlActivityGoalNumber(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, activity_number):
        """Test activity goal number initialization."""
        assert activity_number._number_type == "activity_goal"
        assert activity_number._attr_mode == NumberMode.SLIDER
        assert activity_number._attr_native_unit_of_measurement == PERCENTAGE
        assert activity_number._attr_native_min_value == 50
        assert activity_number._attr_native_max_value == 200
        assert activity_number._attr_native_step == 5
        assert activity_number._attr_icon == "mdi:target"
        assert activity_number._value == DEFAULT_ACTIVITY_GOAL

    @pytest.mark.asyncio
    async def test_async_set_number_value(self, activity_number):
        """Test setting activity goal value."""
        # Should not raise error
        await activity_number._async_set_number_value(150.0)


class TestFeedingNumbers:
    """Test feeding-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "dog_info": {"dog_weight": 25.0}
        }
        return coordinator

    def test_daily_food_amount_number(self, mock_coordinator):
        """Test daily food amount number."""
        number = PawControlDailyFoodAmountNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "daily_food_amount"
        assert number._attr_mode == NumberMode.BOX
        assert number._attr_native_unit_of_measurement == "g"
        assert number._attr_native_min_value == 50
        assert number._attr_native_max_value == 2000
        assert number._attr_icon == "mdi:food"

    def test_daily_food_amount_extra_attributes(self, mock_coordinator):
        """Test daily food amount extra attributes."""
        number = PawControlDailyFoodAmountNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )
        number._value = 500.0

        attrs = number.extra_state_attributes

        assert "recommended_amount" in attrs
        assert "current_vs_recommended" in attrs
        
        # Should calculate based on 25kg weight
        expected_recommended = 25.0 * 22.5  # 562.5g
        assert attrs["recommended_amount"] == expected_recommended

    def test_daily_food_amount_calculate_recommended(self, mock_coordinator):
        """Test recommended amount calculation."""
        number = PawControlDailyFoodAmountNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        # Test calculation
        recommended = number._calculate_recommended_amount(20.0)
        assert recommended == 450.0  # 20 * 22.5

    def test_feeding_reminder_hours_number(self, mock_coordinator):
        """Test feeding reminder hours number."""
        number = PawControlFeedingReminderHoursNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "feeding_reminder_hours"
        assert number._attr_native_unit_of_measurement == UnitOfTime.HOURS
        assert number._attr_native_min_value == 2
        assert number._attr_native_max_value == 24
        assert number._value == DEFAULT_FEEDING_REMINDER_HOURS

    def test_meals_per_day_number(self, mock_coordinator):
        """Test meals per day number."""
        number = PawControlMealsPerDayNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "meals_per_day"
        assert number._attr_native_min_value == 1
        assert number._attr_native_max_value == 6
        assert number._attr_icon == "mdi:numeric"

    def test_portion_size_number(self, mock_coordinator):
        """Test portion size number."""
        number = PawControlPortionSizeNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "portion_size"
        assert number._attr_native_unit_of_measurement == "g"
        assert number._attr_native_step == 5
        assert number._attr_icon == "mdi:food-variant"

    def test_calorie_target_number(self, mock_coordinator):
        """Test calorie target number."""
        number = PawControlCalorieTargetNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "calorie_target"
        assert number._attr_native_unit_of_measurement == "kcal"
        assert number._attr_native_min_value == 200
        assert number._attr_native_max_value == 3000
        assert number._attr_icon == "mdi:fire"


class TestWalkNumbers:
    """Test walk-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_daily_walk_target_number(self, mock_coordinator):
        """Test daily walk target number."""
        number = PawControlDailyWalkTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "daily_walk_target"
        assert number._attr_native_min_value == 1
        assert number._attr_native_max_value == 10
        assert number._attr_icon == "mdi:walk"

    def test_walk_duration_target_number(self, mock_coordinator):
        """Test walk duration target number."""
        number = PawControlWalkDurationTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_duration_target"
        assert number._attr_native_unit_of_measurement == UnitOfTime.MINUTES
        assert number._attr_native_min_value == 10
        assert number._attr_native_max_value == 180
        assert number._value == DEFAULT_WALK_DURATION_TARGET

    def test_walk_distance_target_number(self, mock_coordinator):
        """Test walk distance target number."""
        number = PawControlWalkDistanceTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_distance_target"
        assert number._attr_native_unit_of_measurement == UnitOfLength.METERS
        assert number._attr_native_step == 100
        assert number._attr_icon == "mdi:map-marker-distance"

    def test_walk_reminder_hours_number(self, mock_coordinator):
        """Test walk reminder hours number."""
        number = PawControlWalkReminderHoursNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_reminder_hours"
        assert number._attr_native_unit_of_measurement == UnitOfTime.HOURS
        assert number._attr_icon == "mdi:clock-alert"

    def test_max_walk_speed_number(self, mock_coordinator):
        """Test max walk speed number."""
        number = PawControlMaxWalkSpeedNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "max_walk_speed"
        assert number._attr_native_unit_of_measurement == "km/h"
        assert number._attr_native_min_value == 2
        assert number._attr_native_max_value == 30
        assert number._attr_icon == "mdi:speedometer"


class TestGPSNumbers:
    """Test GPS-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_gps_accuracy_threshold_number(self, mock_coordinator):
        """Test GPS accuracy threshold number."""
        number = PawControlGPSAccuracyThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_accuracy_threshold"
        assert number._attr_native_unit_of_measurement == UnitOfLength.METERS
        assert number._attr_native_min_value == 5
        assert number._attr_native_max_value == 500
        assert number._attr_entity_category == EntityCategory.CONFIG
        assert number._value == DEFAULT_GPS_ACCURACY_THRESHOLD

    def test_gps_update_interval_number(self, mock_coordinator):
        """Test GPS update interval number."""
        number = PawControlGPSUpdateIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_update_interval"
        assert number._attr_native_unit_of_measurement == UnitOfTime.SECONDS
        assert number._attr_native_step == 30
        assert number._attr_entity_category == EntityCategory.CONFIG

    def test_geofence_radius_number(self, mock_coordinator):
        """Test geofence radius number."""
        number = PawControlGeofenceRadiusNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "geofence_radius"
        assert number._attr_native_unit_of_measurement == UnitOfLength.METERS
        assert number._attr_native_step == 10
        assert number._attr_icon == "mdi:map-marker-circle"

    def test_location_update_distance_number(self, mock_coordinator):
        """Test location update distance number."""
        number = PawControlLocationUpdateDistanceNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "location_update_distance"
        assert number._attr_native_unit_of_measurement == UnitOfLength.METERS
        assert number._attr_native_max_value == 100
        assert number._attr_entity_category == EntityCategory.CONFIG

    def test_gps_battery_threshold_number(self, mock_coordinator):
        """Test GPS battery threshold number."""
        number = PawControlGPSBatteryThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_battery_threshold"
        assert number._attr_mode == NumberMode.SLIDER
        assert number._attr_native_unit_of_measurement == PERCENTAGE
        assert number._attr_icon == "mdi:battery-alert"


class TestHealthNumbers:
    """Test health-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_target_weight_number(self, mock_coordinator):
        """Test target weight number."""
        number = PawControlTargetWeightNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "target_weight"
        assert number._attr_device_class == NumberDeviceClass.WEIGHT
        assert number._attr_native_unit_of_measurement == UnitOfMass.KILOGRAMS
        assert number._attr_native_min_value == MIN_DOG_WEIGHT
        assert number._attr_native_max_value == MAX_DOG_WEIGHT

    def test_weight_change_threshold_number(self, mock_coordinator):
        """Test weight change threshold number."""
        number = PawControlWeightChangeThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "weight_change_threshold"
        assert number._attr_mode == NumberMode.SLIDER
        assert number._attr_native_unit_of_measurement == PERCENTAGE
        assert number._attr_icon == "mdi:scale-unbalanced"

    def test_grooming_interval_number(self, mock_coordinator):
        """Test grooming interval number."""
        number = PawControlGroomingIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "grooming_interval"
        assert number._attr_native_unit_of_measurement == UnitOfTime.DAYS
        assert number._attr_native_step == 7
        assert number._attr_icon == "mdi:content-cut"

    def test_vet_checkup_interval_number(self, mock_coordinator):
        """Test vet checkup interval number."""
        number = PawControlVetCheckupIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "vet_checkup_interval"
        assert number._attr_native_unit_of_measurement == "months"
        assert number._attr_native_step == 3
        assert number._attr_icon == "mdi:medical-bag"

    def test_health_score_threshold_number(self, mock_coordinator):
        """Test health score threshold number."""
        number = PawControlHealthScoreThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "health_score_threshold"
        assert number._attr_mode == NumberMode.SLIDER
        assert number._attr_native_unit_of_measurement == PERCENTAGE
        assert number._attr_icon == "mdi:heart-pulse"


class TestNumberIntegration:
    """Test number integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_setup_with_all_modules(self, hass: HomeAssistant):
        """Test complete setup with all modules enabled."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "full_featured_dog",
                    CONF_DOG_NAME: "Full Featured Dog",
                    CONF_DOG_WEIGHT: 30.0,
                    CONF_DOG_AGE: 6,
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                }
            ]
        }
        entry.runtime_data = {
            "coordinator": coordinator,
            "dogs": entry.data[CONF_DOGS],
        }

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        # Count total entities across all batches
        total_entities = sum(
            len(call[0][0]) for call in async_add_entities.call_args_list
        )

        # Should have 3 base + 5 feeding + 5 walk + 5 gps + 5 health = 23 entities
        assert total_entities == 23

    def test_number_uniqueness(self):
        """Test that numbers have unique IDs."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create multiple numbers for the same dog
        numbers = []
        dog_config = {CONF_DOG_WEIGHT: 25.0, CONF_DOG_AGE: 5}
        numbers.extend(_create_base_numbers(coordinator, "test_dog", "Test Dog", dog_config))
        numbers.extend(_create_feeding_numbers(coordinator, "test_dog", "Test Dog"))
        numbers.extend(_create_walk_numbers(coordinator, "test_dog", "Test Dog"))

        unique_ids = [number._attr_unique_id for number in numbers]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

    def test_number_device_grouping(self):
        """Test that numbers are properly grouped by device."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create numbers for two different dogs
        dog1_config = {CONF_DOG_WEIGHT: 25.0, CONF_DOG_AGE: 5}
        dog2_config = {CONF_DOG_WEIGHT: 15.0, CONF_DOG_AGE: 3}
        
        dog1_numbers = _create_base_numbers(coordinator, "dog1", "Dog 1", dog1_config)
        dog2_numbers = _create_base_numbers(coordinator, "dog2", "Dog 2", dog2_config)

        # Check device info
        dog1_device = dog1_numbers[0]._attr_device_info
        dog2_device = dog2_numbers[0]._attr_device_info

        assert dog1_device["identifiers"] == {(DOMAIN, "dog1")}
        assert dog2_device["identifiers"] == {(DOMAIN, "dog2")}
        assert dog1_device["name"] == "Dog 1"
        assert dog2_device["name"] == "Dog 2"

    @pytest.mark.asyncio
    async def test_number_value_persistence(self):
        """Test number value persistence across restarts."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        dog_config = {CONF_DOG_WEIGHT: 25.0}
        weight_number = PawControlDogWeightNumber(
            coordinator, "test_dog", "Test Dog", dog_config
        )

        # Set a value
        with patch.object(weight_number, "async_write_ha_state"):
            await weight_number.async_set_native_value(30.0)

        assert weight_number.native_value == 30.0

        # Simulate restart with state restoration
        mock_state = Mock()
        mock_state.state = "35.0"

        with patch.object(weight_number, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state
            await weight_number.async_added_to_hass()

        # Should restore the persisted value
        assert weight_number.native_value == 35.0


class TestNumberErrorHandling:
    """Test number error handling scenarios."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_number_with_coordinator_unavailable(self, mock_coordinator):
        """Test number availability when coordinator is unavailable."""
        mock_coordinator.available = False

        dog_config = {CONF_DOG_WEIGHT: 25.0}
        weight_number = PawControlDogWeightNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

        assert weight_number.available is False

    def test_number_with_dog_data_none(self, mock_coordinator):
        """Test number availability when dog data is None."""
        mock_coordinator.get_dog_data.return_value = None

        dog_config = {CONF_DOG_WEIGHT: 25.0}
        weight_number = PawControlDogWeightNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

        assert weight_number.available is False

    @pytest.mark.asyncio
    async def test_number_value_validation_edge_cases(self, mock_coordinator):
        """Test number value validation at boundaries."""
        dog_config = {CONF_DOG_WEIGHT: 25.0}
        weight_number = PawControlDogWeightNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

        # Test exact boundaries
        with patch.object(weight_number, "async_write_ha_state"):
            # Minimum value should work
            await weight_number.async_set_native_value(MIN_DOG_WEIGHT)
            assert weight_number.native_value == MIN_DOG_WEIGHT

            # Maximum value should work
            await weight_number.async_set_native_value(MAX_DOG_WEIGHT)
            assert weight_number.native_value == MAX_DOG_WEIGHT

        # Just outside boundaries should fail
        with pytest.raises(HomeAssistantError):
            await weight_number.async_set_native_value(MIN_DOG_WEIGHT - 0.1)

        with pytest.raises(HomeAssistantError):
            await weight_number.async_set_native_value(MAX_DOG_WEIGHT + 0.1)

    @pytest.mark.asyncio
    async def test_setup_with_malformed_dog_config(self, hass: HomeAssistant):
        """Test setup with malformed dog configuration."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "malformed_dog",
                    CONF_DOG_NAME: "Malformed Dog",
                    # Missing weight and age
                    "modules": {MODULE_FEEDING: True},
                }
            ]
        }
        entry.runtime_data = {
            "coordinator": coordinator,
            "dogs": entry.data[CONF_DOGS],
        }

        async_add_entities = AsyncMock()

        # Should not raise exception, should use defaults
        await async_setup_entry(hass, entry, async_add_entities)

        # Should still create entities
        async_add_entities.assert_called()


class TestNumberConstants:
    """Test number constants and defaults."""

    def test_default_values_reasonable(self):
        """Test that default values are reasonable."""
        assert 0 < DEFAULT_ACTIVITY_GOAL <= 200
        assert 0 < DEFAULT_FEEDING_REMINDER_HOURS <= 24
        assert 0 < DEFAULT_GPS_ACCURACY_THRESHOLD <= 500
        assert 0 < DEFAULT_WALK_DURATION_TARGET <= 180

    def test_weight_limits_valid(self):
        """Test that weight limits are valid."""
        assert MIN_DOG_WEIGHT > 0
        assert MAX_DOG_WEIGHT > MIN_DOG_WEIGHT
        assert MIN_DOG_WEIGHT <= 1.0  # Small dogs
        assert MAX_DOG_WEIGHT >= 100.0  # Large dogs

    def test_age_limits_valid(self):
        """Test that age limits are valid."""
        assert MIN_DOG_AGE >= 0
        assert MAX_DOG_AGE > MIN_DOG_AGE
        assert MAX_DOG_AGE >= 20  # Dogs can live 20+ years


class TestNumberPerformance:
    """Test number performance scenarios."""

    @pytest.mark.asyncio
    async def test_batching_performance_large_setup(self, hass: HomeAssistant):
        """Test batching performance with many dogs."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        # Create many dogs to test batching
        dogs = []
        for i in range(10):  # 10 dogs with all modules
            dogs.append({
                CONF_DOG_ID: f"dog_{i}",
                CONF_DOG_NAME: f"Dog {i}",
                CONF_DOG_WEIGHT: 20.0 + i,
                CONF_DOG_AGE: 3 + (i % 5),
                "modules": {
                    MODULE_FEEDING: True,
                    MODULE_WALK: True,
                    MODULE_GPS: True,
                    MODULE_HEALTH: True,
                },
            })

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {CONF_DOGS: dogs}
        entry.runtime_data = {
            "coordinator": coordinator,
            "dogs": dogs,
        }

        async_add_entities = AsyncMock()

        # Should complete without timeout
        await async_setup_entry(hass, entry, async_add_entities)

        # Should have made multiple batched calls
        assert async_add_entities.call_count > 1

        # Total entities should be 10 dogs * 23 entities each = 230
        total_entities = sum(
            len(call[0][0]) for call in async_add_entities.call_args_list
        )
        assert total_entities == 230

    def test_number_memory_efficiency(self):
        """Test that numbers don't store unnecessary data."""
        coordinator = Mock(spec=PawControlCoordinator)
        
        dog_config = {CONF_DOG_WEIGHT: 25.0}
        weight_number = PawControlDogWeightNumber(
            coordinator, "test_dog", "Test Dog", dog_config
        )

        # Check that only essential attributes are stored
        essential_attrs = {
            '_dog_id', '_dog_name', '_number_type', '_value',
            '_attr_unique_id', '_attr_name', '_attr_device_class',
            '_attr_mode', '_attr_native_unit_of_measurement',
            '_attr_native_min_value', '_attr_native_max_value',
            '_attr_native_step', '_attr_icon', '_attr_entity_category',
            '_attr_device_info'
        }

        # Get all attributes that don't start with '__'
        actual_attrs = {
            attr for attr in dir(weight_number) 
            if not attr.startswith('__') and hasattr(weight_number, attr)
        }

        # Most attributes should be essential or inherited
        non_essential = actual_attrs - essential_attrs
        
        # Filter out inherited methods and properties
        non_essential = {
            attr for attr in non_essential 
            if not callable(getattr(weight_number, attr, None))
            and not attr.startswith('_attr_')
            and attr not in ['coordinator', 'registry_entry', 'platform', 'hass']
        }

        # Should have minimal non-essential attributes
        assert len(non_essential) < 10
