"""Comprehensive tests for PawControl number platform.

Tests all number entities including base numbers, feeding numbers, walk numbers,
GPS numbers, and health numbers. Validates proper functionality, state persistence,
value validation, and device grouping for Gold Standard compliance.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_WEIGHT,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.number import (
    PawControlActivityGoalNumber,
    PawControlCalorieTargetNumber,
    PawControlDailyFoodAmountNumber,
    PawControlDailyWalkTargetNumber,
    PawControlDogAgeNumber,
    PawControlDogWeightNumber,
    PawControlFeedingReminderHoursNumber,
    PawControlGeofenceRadiusNumber,
    PawControlGPSAccuracyThresholdNumber,
    PawControlGPSBatteryThresholdNumber,
    PawControlGPSUpdateIntervalNumber,
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
    async_setup_entry,
)
from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfMass,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback


class TestNumberPlatformSetup:
    """Test number platform setup and configuration."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "dog_info": {
                "dog_weight": 25.0,
                "dog_age": 5,
                "dog_breed": "Golden Retriever",
                "dog_size": "large",
            }
        }
        coordinator.get_module_data.return_value = {}
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "test_dog_1",
                    CONF_DOG_NAME: "Test Dog 1",
                    CONF_DOG_WEIGHT: 20.0,
                    CONF_DOG_AGE: 3,
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                },
                {
                    CONF_DOG_ID: "test_dog_2",
                    CONF_DOG_NAME: "Test Dog 2",
                    CONF_DOG_WEIGHT: 35.0,
                    CONF_DOG_AGE: 7,
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: False,
                        MODULE_GPS: False,
                        MODULE_HEALTH: True,
                    },
                },
            ]
        }
        entry.runtime_data = None
        return entry

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_all_entities(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test that async_setup_entry creates all expected number entities."""
        # Mock the coordinator retrieval
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {"coordinator": mock_coordinator}
        }

        entities_added = []

        def mock_add_entities(entities, update_before_add=True):
            entities_added.extend(entities)

        # Call async_setup_entry
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Verify entities were created
        assert len(entities_added) > 0

        # Count entities by type
        entity_types = {}
        for entity in entities_added:
            entity_type = entity.__class__.__name__
            entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

        # Verify expected entity counts
        # Dog 1: all modules enabled = 3 base + 5 feeding + 5 walk + 5 gps + 5 health = 23
        # Dog 2: feeding + health only = 3 base + 5 feeding + 5 health = 13
        # Total: 36 entities
        expected_total = 36
        assert len(entities_added) == expected_total

        # Verify base entities for both dogs
        assert entity_types.get("PawControlDogWeightNumber", 0) == 2
        assert entity_types.get("PawControlDogAgeNumber", 0) == 2
        assert entity_types.get("PawControlActivityGoalNumber", 0) == 2

        # Verify feeding entities for both dogs
        assert entity_types.get("PawControlDailyFoodAmountNumber", 0) == 2
        assert entity_types.get("PawControlFeedingReminderHoursNumber", 0) == 2

        # Verify walk entities only for dog 1
        assert entity_types.get("PawControlDailyWalkTargetNumber", 0) == 1
        assert entity_types.get("PawControlWalkDurationTargetNumber", 0) == 1

        # Verify GPS entities only for dog 1
        assert entity_types.get("PawControlGPSAccuracyThresholdNumber", 0) == 1
        assert entity_types.get("PawControlGPSUpdateIntervalNumber", 0) == 1

        # Verify health entities for both dogs
        assert entity_types.get("PawControlTargetWeightNumber", 0) == 2
        assert entity_types.get("PawControlHealthScoreThresholdNumber", 0) == 2

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_runtime_data(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test async_setup_entry with runtime_data configuration."""
        # Set up runtime_data
        mock_config_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": mock_config_entry.data[CONF_DOGS],
        }

        entities_added = []

        def mock_add_entities(entities, update_before_add=True):
            entities_added.extend(entities)

        # Call async_setup_entry
        await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Verify entities were created
        assert len(entities_added) == 36  # Same as previous test

    @pytest.mark.asyncio
    async def test_async_setup_entry_batched_loading(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test that entities are added in batches."""
        hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {"coordinator": mock_coordinator}
        }

        add_calls = []

        def mock_add_entities(entities, update_before_add=True):
            add_calls.append((len(entities), update_before_add))

        with patch("custom_components.pawcontrol.number.asyncio.sleep") as mock_sleep:
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Verify batching occurred
        assert len(add_calls) > 1  # Should be multiple batches

        # Verify batch sizes are reasonable (≤12 entities per batch)
        for batch_size, update_flag in add_calls:
            assert batch_size <= 12
            assert update_flag is False  # Should disable update_before_add

        # Verify sleep was called between batches
        assert mock_sleep.call_count >= 1


class TestPawControlNumberBase:
    """Test base number entity functionality."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator for base tests."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {
            "dog_info": {
                "dog_weight": 25.0,
                "dog_age": 5,
                "dog_breed": "Golden Retriever",
                "dog_size": "large",
            }
        }
        coordinator.get_module_data.return_value = {"test": "data"}
        return coordinator

    @pytest.fixture
    def base_number(self, mock_coordinator):
        """Create a base number entity for testing."""
        return PawControlNumberBase(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            number_type="test_number",
            native_min_value=0,
            native_max_value=100,
            native_step=1,
            initial_value=50,
        )

    def test_base_number_initialization(self, base_number, mock_coordinator):
        """Test base number entity initialization."""
        assert base_number._dog_id == "test_dog"
        assert base_number._dog_name == "Test Dog"
        assert base_number._number_type == "test_number"
        assert base_number._value == 50

        # Verify entity attributes
        assert base_number.unique_id == "pawcontrol_test_dog_test_number"
        assert base_number.name == "Test Dog Test Number"
        assert base_number.native_min_value == 0
        assert base_number.native_max_value == 100
        assert base_number.native_step == 1

        # Verify device info
        assert base_number.device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert base_number.device_info["name"] == "Test Dog"

    def test_base_number_native_value(self, base_number):
        """Test native_value property."""
        assert base_number.native_value == 50

        base_number._value = 75
        assert base_number.native_value == 75

    def test_base_number_extra_state_attributes(self, base_number):
        """Test extra_state_attributes property."""
        attrs = base_number.extra_state_attributes

        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        assert attrs["number_type"] == "test_number"
        assert attrs["min_value"] == 0
        assert attrs["max_value"] == 100
        assert attrs["step"] == 1
        assert "last_changed" in attrs

        # Verify dog-specific attributes
        assert attrs["dog_breed"] == "Golden Retriever"
        assert attrs["dog_age"] == 5
        assert attrs["dog_size"] == "large"

    def test_base_number_available(self, base_number, mock_coordinator):
        """Test available property."""
        # Should be available when coordinator is available and dog data exists
        assert base_number.available is True

        # Should be unavailable when coordinator is unavailable
        mock_coordinator.available = False
        assert base_number.available is False

        # Should be unavailable when dog data is None
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        assert base_number.available is False

    @pytest.mark.asyncio
    async def test_base_number_async_added_to_hass(self, hass, base_number):
        """Test async_added_to_hass method."""
        # Mock restore state
        mock_state = MagicMock()
        mock_state.state = "75.5"

        with patch.object(base_number, "async_get_last_state", return_value=mock_state):
            await base_number.async_added_to_hass()

        # Verify value was restored
        assert base_number._value == 75.5

    @pytest.mark.asyncio
    async def test_base_number_async_added_to_hass_invalid_state(
        self, hass, base_number
    ):
        """Test async_added_to_hass with invalid state."""
        # Mock restore state with invalid value
        mock_state = MagicMock()
        mock_state.state = "invalid"

        with patch.object(base_number, "async_get_last_state", return_value=mock_state):
            await base_number.async_added_to_hass()

        # Verify value remained as initial value
        assert base_number._value == 50

    @pytest.mark.asyncio
    async def test_base_number_async_set_native_value_valid(self, base_number):
        """Test setting valid native value."""
        with patch.object(base_number, "async_write_ha_state") as mock_write_state:
            await base_number.async_set_native_value(75)

        assert base_number._value == 75
        mock_write_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_base_number_async_set_native_value_invalid(self, base_number):
        """Test setting invalid native value."""
        with pytest.raises(HomeAssistantError):
            await base_number.async_set_native_value(150)  # Outside range

        with pytest.raises(HomeAssistantError):
            await base_number.async_set_native_value(-10)  # Outside range

        # Verify value didn't change
        assert base_number._value == 50


class TestDogWeightNumber:
    """Test dog weight number entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {"dog_weight": 25.0}}
        coordinator.get_module_data.return_value = {
            "weight_trend": "increasing",
            "weight_change_percent": 5.2,
            "last_weight_date": "2025-09-01",
            "target_weight": 24.0,
        }
        coordinator.async_refresh_dog = AsyncMock()
        return coordinator

    @pytest.fixture
    def weight_number(self, mock_coordinator):
        """Create a dog weight number entity."""
        dog_config = {
            CONF_DOG_WEIGHT: 25.0,
            CONF_DOG_AGE: 5,
        }
        return PawControlDogWeightNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

    def test_weight_number_initialization(self, weight_number):
        """Test weight number initialization."""
        assert weight_number._number_type == "weight"
        assert weight_number.device_class.value == "weight"
        assert weight_number.native_unit_of_measurement == UnitOfMass.KILOGRAMS
        assert weight_number.native_value == 25.0
        assert weight_number.icon == "mdi:scale"

    def test_weight_number_extra_state_attributes(self, weight_number):
        """Test weight number extra state attributes."""
        attrs = weight_number.extra_state_attributes

        # Verify base attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["number_type"] == "weight"

        # Verify weight-specific attributes
        assert attrs["weight_trend"] == "increasing"
        assert attrs["weight_change_percent"] == 5.2
        assert attrs["last_weight_date"] == "2025-09-01"
        assert attrs["target_weight"] == 24.0

    @pytest.mark.asyncio
    async def test_weight_number_set_value(self, weight_number, mock_coordinator):
        """Test setting weight value."""
        with patch.object(weight_number, "async_write_ha_state"):
            await weight_number.async_set_native_value(26.5)

        assert weight_number.native_value == 26.5
        mock_coordinator.async_refresh_dog.assert_called_once_with("test_dog")


class TestDogAgeNumber:
    """Test dog age number entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator with config entry."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"profile": {CONF_DOG_AGE: 5}}

        # Mock config entry with runtime_data
        config_entry = MagicMock()
        config_entry.runtime_data = {
            "data_manager": MagicMock(spec_set=["async_update_dog_data"])
        }
        config_entry.runtime_data["data_manager"].async_update_dog_data = AsyncMock()
        coordinator.config_entry = config_entry

        return coordinator

    @pytest.fixture
    def age_number(self, mock_coordinator):
        """Create a dog age number entity."""
        dog_config = {CONF_DOG_AGE: 5, CONF_DOG_WEIGHT: 25.0}
        return PawControlDogAgeNumber(
            mock_coordinator, "test_dog", "Test Dog", dog_config
        )

    def test_age_number_initialization(self, age_number):
        """Test age number initialization."""
        assert age_number._number_type == "age"
        assert age_number.native_unit_of_measurement == "years"
        assert age_number.native_value == 5
        assert age_number.icon == "mdi:calendar"
        assert age_number.entity_category.value == "config"

    @pytest.mark.asyncio
    async def test_age_number_set_value(self, age_number, mock_coordinator):
        """Test setting age value."""
        data_manager = mock_coordinator.config_entry.runtime_data["data_manager"]

        with patch.object(age_number, "async_write_ha_state"):
            await age_number.async_set_native_value(6.0)

        assert age_number.native_value == 6.0

        # Verify data manager was called to persist the change
        data_manager.async_update_dog_data.assert_called_once_with(
            "test_dog", {"profile": {CONF_DOG_AGE: 6}}
        )

    @pytest.mark.asyncio
    async def test_age_number_set_value_no_data_manager(
        self, age_number, mock_coordinator
    ):
        """Test setting age value when data manager is not available."""
        # Remove data manager
        mock_coordinator.config_entry.runtime_data = None

        with patch.object(age_number, "async_write_ha_state"):
            await age_number.async_set_native_value(7.0)

        # Should still work, just without persistence
        assert age_number.native_value == 7.0


class TestActivityGoalNumber:
    """Test activity goal number entity."""

    @pytest.fixture
    def activity_goal_number(self, mock_coordinator):
        """Create an activity goal number entity."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}

        return PawControlActivityGoalNumber(coordinator, "test_dog", "Test Dog")

    def test_activity_goal_initialization(self, activity_goal_number):
        """Test activity goal number initialization."""
        assert activity_goal_number._number_type == "activity_goal"
        assert activity_goal_number.native_unit_of_measurement == PERCENTAGE
        assert activity_goal_number.native_value == 100  # DEFAULT_ACTIVITY_GOAL
        assert activity_goal_number.icon == "mdi:target"
        assert activity_goal_number.native_min_value == 50
        assert activity_goal_number.native_max_value == 200


class TestFeedingNumbers:
    """Test feeding-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {"dog_weight": 20.0}}
        return coordinator

    def test_daily_food_amount_number(self, mock_coordinator):
        """Test daily food amount number entity."""
        number = PawControlDailyFoodAmountNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "daily_food_amount"
        assert number.native_unit_of_measurement == "g"
        assert number.native_value == 300
        assert number.icon == "mdi:food"
        assert number.native_min_value == 50
        assert number.native_max_value == 2000

        # Test recommended amount calculation
        attrs = number.extra_state_attributes
        expected_recommended = 20.0 * 22.5  # 450g
        assert attrs["recommended_amount"] == expected_recommended

    def test_feeding_reminder_hours_number(self, mock_coordinator):
        """Test feeding reminder hours number entity."""
        number = PawControlFeedingReminderHoursNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "feeding_reminder_hours"
        assert number.native_unit_of_measurement == UnitOfTime.HOURS
        assert number.native_value == 8  # DEFAULT_FEEDING_REMINDER_HOURS
        assert number.icon == "mdi:clock-alert"

    def test_meals_per_day_number(self, mock_coordinator):
        """Test meals per day number entity."""
        number = PawControlMealsPerDayNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "meals_per_day"
        assert number.native_value == 2
        assert number.icon == "mdi:numeric"
        assert number.native_min_value == 1
        assert number.native_max_value == 6

    def test_portion_size_number(self, mock_coordinator):
        """Test portion size number entity."""
        number = PawControlPortionSizeNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "portion_size"
        assert number.native_unit_of_measurement == "g"
        assert number.native_value == 150
        assert number.icon == "mdi:food-variant"

    def test_calorie_target_number(self, mock_coordinator):
        """Test calorie target number entity."""
        number = PawControlCalorieTargetNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "calorie_target"
        assert number.native_unit_of_measurement == "kcal"
        assert number.native_value == 800
        assert number.icon == "mdi:fire"


class TestWalkNumbers:
    """Test walk-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}
        return coordinator

    def test_daily_walk_target_number(self, mock_coordinator):
        """Test daily walk target number entity."""
        number = PawControlDailyWalkTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "daily_walk_target"
        assert number.native_value == 3
        assert number.icon == "mdi:walk"
        assert number.native_min_value == 1
        assert number.native_max_value == 10

    def test_walk_duration_target_number(self, mock_coordinator):
        """Test walk duration target number entity."""
        number = PawControlWalkDurationTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_duration_target"
        assert number.native_unit_of_measurement == UnitOfTime.MINUTES
        assert number.native_value == 60  # DEFAULT_WALK_DURATION_TARGET
        assert number.icon == "mdi:timer"

    def test_walk_distance_target_number(self, mock_coordinator):
        """Test walk distance target number entity."""
        number = PawControlWalkDistanceTargetNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_distance_target"
        assert number.native_unit_of_measurement == UnitOfLength.METERS
        assert number.native_value == 2000
        assert number.icon == "mdi:map-marker-distance"

    def test_walk_reminder_hours_number(self, mock_coordinator):
        """Test walk reminder hours number entity."""
        number = PawControlWalkReminderHoursNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "walk_reminder_hours"
        assert number.native_unit_of_measurement == UnitOfTime.HOURS
        assert number.native_value == 8
        assert number.icon == "mdi:clock-alert"

    def test_max_walk_speed_number(self, mock_coordinator):
        """Test max walk speed number entity."""
        number = PawControlMaxWalkSpeedNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "max_walk_speed"
        assert number.native_unit_of_measurement == UnitOfSpeed.KILOMETERS_PER_HOUR
        assert number.native_value == 15
        assert number.icon == "mdi:speedometer"


class TestGPSNumbers:
    """Test GPS-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}
        return coordinator

    def test_gps_accuracy_threshold_number(self, mock_coordinator):
        """Test GPS accuracy threshold number entity."""
        number = PawControlGPSAccuracyThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_accuracy_threshold"
        assert number.native_unit_of_measurement == UnitOfLength.METERS
        assert number.native_value == 50  # DEFAULT_GPS_ACCURACY_THRESHOLD
        assert number.icon == "mdi:crosshairs-gps"
        assert number.entity_category.value == "config"

    def test_gps_update_interval_number(self, mock_coordinator):
        """Test GPS update interval number entity."""
        number = PawControlGPSUpdateIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_update_interval"
        assert number.native_unit_of_measurement == UnitOfTime.SECONDS
        assert number.native_value == 60
        assert number.icon == "mdi:update"

    def test_geofence_radius_number(self, mock_coordinator):
        """Test geofence radius number entity."""
        number = PawControlGeofenceRadiusNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "geofence_radius"
        assert number.native_unit_of_measurement == UnitOfLength.METERS
        assert number.native_value == 100
        assert number.icon == "mdi:map-marker-circle"

    def test_location_update_distance_number(self, mock_coordinator):
        """Test location update distance number entity."""
        number = PawControlLocationUpdateDistanceNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "location_update_distance"
        assert number.native_unit_of_measurement == UnitOfLength.METERS
        assert number.native_value == 10
        assert number.icon == "mdi:map-marker-path"

    def test_gps_battery_threshold_number(self, mock_coordinator):
        """Test GPS battery threshold number entity."""
        number = PawControlGPSBatteryThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "gps_battery_threshold"
        assert number.native_unit_of_measurement == PERCENTAGE
        assert number.native_value == 20
        assert number.icon == "mdi:battery-alert"


class TestHealthNumbers:
    """Test health-related number entities."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}
        return coordinator

    def test_target_weight_number(self, mock_coordinator):
        """Test target weight number entity."""
        number = PawControlTargetWeightNumber(mock_coordinator, "test_dog", "Test Dog")

        assert number._number_type == "target_weight"
        assert number.device_class.value == "weight"
        assert number.native_unit_of_measurement == UnitOfMass.KILOGRAMS
        assert number.native_value == 20.0
        assert number.icon == "mdi:target"

    def test_weight_change_threshold_number(self, mock_coordinator):
        """Test weight change threshold number entity."""
        number = PawControlWeightChangeThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "weight_change_threshold"
        assert number.native_unit_of_measurement == PERCENTAGE
        assert number.native_value == 10
        assert number.icon == "mdi:scale-unbalanced"

    def test_grooming_interval_number(self, mock_coordinator):
        """Test grooming interval number entity."""
        number = PawControlGroomingIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "grooming_interval"
        assert number.native_unit_of_measurement == UnitOfTime.DAYS
        assert number.native_value == 28
        assert number.icon == "mdi:content-cut"

    def test_vet_checkup_interval_number(self, mock_coordinator):
        """Test vet checkup interval number entity."""
        number = PawControlVetCheckupIntervalNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "vet_checkup_interval"
        assert number.native_unit_of_measurement == "months"
        assert number.native_value == 12
        assert number.icon == "mdi:medical-bag"

    def test_health_score_threshold_number(self, mock_coordinator):
        """Test health score threshold number entity."""
        number = PawControlHealthScoreThresholdNumber(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert number._number_type == "health_score_threshold"
        assert number.native_unit_of_measurement == PERCENTAGE
        assert number.native_value == 70
        assert number.icon == "mdi:heart-pulse"


class TestNumberEntityEdgeCases:
    """Test edge cases and error handling for number entities."""

    @pytest.fixture
    def mock_coordinator_unavailable(self):
        """Create an unavailable mock coordinator."""
        coordinator = MagicMock()
        coordinator.available = False
        coordinator.get_dog_data.return_value = None
        return coordinator

    @pytest.fixture
    def basic_number(self, mock_coordinator_unavailable):
        """Create a basic number entity for edge case testing."""
        return PawControlNumberBase(
            coordinator=mock_coordinator_unavailable,
            dog_id="test_dog",
            dog_name="Test Dog",
            number_type="test_number",
            initial_value=50,
        )

    def test_number_unavailable_coordinator(self, basic_number):
        """Test number entity with unavailable coordinator."""
        assert basic_number.available is False

    def test_number_extra_attributes_no_dog_data(self, basic_number):
        """Test extra_state_attributes when dog data is unavailable."""
        attrs = basic_number.extra_state_attributes

        # Should still have basic attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["number_type"] == "test_number"

        # Dog-specific attributes should be absent or empty
        assert attrs.get("dog_breed", "") == ""
        assert attrs.get("dog_age") is None

    @pytest.mark.asyncio
    async def test_number_set_value_with_exception(self, basic_number):
        """Test setting value when _async_set_number_value raises exception."""

        async def failing_set_value(value):
            raise Exception("Test exception")

        basic_number._async_set_number_value = failing_set_value

        with pytest.raises(HomeAssistantError):
            await basic_number.async_set_native_value(75)

        # Value should not change after exception
        assert basic_number.native_value == 50

    @pytest.mark.asyncio
    async def test_restore_state_edge_cases(self, hass, basic_number):
        """Test state restoration edge cases."""
        # Test with None state
        with patch.object(basic_number, "async_get_last_state", return_value=None):
            await basic_number.async_added_to_hass()
        assert basic_number.native_value == 50  # Should remain initial value

        # Test with unknown state
        mock_state = MagicMock()
        mock_state.state = "unknown"
        with patch.object(
            basic_number, "async_get_last_state", return_value=mock_state
        ):
            await basic_number.async_added_to_hass()
        assert basic_number.native_value == 50  # Should remain initial value

        # Test with unavailable state
        mock_state.state = "unavailable"
        with patch.object(
            basic_number, "async_get_last_state", return_value=mock_state
        ):
            await basic_number.async_added_to_hass()
        assert basic_number.native_value == 50  # Should remain initial value


class TestNumberEntityIntegration:
    """Test integration scenarios for number entities."""

    @pytest.mark.asyncio
    async def test_multiple_numbers_same_dog(self, hass):
        """Test multiple number entities for the same dog."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {"dog_weight": 25.0}}

        # Create multiple numbers for same dog
        weight_number = PawControlDogWeightNumber(
            coordinator, "test_dog", "Test Dog", {CONF_DOG_WEIGHT: 25.0}
        )
        age_number = PawControlDogAgeNumber(
            coordinator, "test_dog", "Test Dog", {CONF_DOG_AGE: 5}
        )

        # Verify unique IDs are different
        assert weight_number.unique_id != age_number.unique_id
        assert "weight" in weight_number.unique_id
        assert "age" in age_number.unique_id

        # Verify device info is same (same dog)
        assert weight_number.device_info == age_number.device_info

    @pytest.mark.asyncio
    async def test_number_persistence_and_restoration(self, hass):
        """Test number value persistence and restoration."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}

        # Create number entity
        number = PawControlActivityGoalNumber(coordinator, "test_dog", "Test Dog")

        # Simulate setting a value
        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(150)
        assert number.native_value == 150

        # Simulate restart - create new entity and restore state
        number2 = PawControlActivityGoalNumber(coordinator, "test_dog", "Test Dog")

        # Mock restored state
        mock_state = MagicMock()
        mock_state.state = "150"

        with patch.object(number2, "async_get_last_state", return_value=mock_state):
            await number2.async_added_to_hass()

        # Verify value was restored
        assert number2.native_value == 150

    @pytest.mark.asyncio
    async def test_number_validation_boundary_values(self):
        """Test number validation at boundary values."""
        coordinator = MagicMock()
        coordinator.available = True
        coordinator.get_dog_data.return_value = {"dog_info": {}}

        number = PawControlActivityGoalNumber(coordinator, "test_dog", "Test Dog")

        # Test minimum boundary
        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(50)  # Min value
        assert number.native_value == 50

        # Test maximum boundary
        with patch.object(number, "async_write_ha_state"):
            await number.async_set_native_value(200)  # Max value
        assert number.native_value == 200

        # Test below minimum
        with pytest.raises(HomeAssistantError):
            await number.async_set_native_value(49)

        # Test above maximum
        with pytest.raises(HomeAssistantError):
            await number.async_set_native_value(201)


if __name__ == "__main__":
    pytest.main([__file__])
