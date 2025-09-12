"""Tests for the Paw Control sensor platform."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

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
from custom_components.pawcontrol.sensor import (
    PawControlActivityScoreSensor,
    PawControlAverageWalkDurationSensor,
    PawControlCurrentSpeedSensor,
    PawControlCurrentZoneSensor,
    PawControlDailyCaloriesSensor,
    PawControlDistanceFromHomeSensor,
    PawControlDogStatusSensor,
    PawControlFeedingCountTodaySensor,
    PawControlFeedingScheduleAdherenceSensor,
    PawControlGPSAccuracySensor,
    PawControlGPSBatteryLevelSensor,
    PawControlHealthStatusSensor,
    PawControlLastActionSensor,
    PawControlLastFeedingSensor,
    PawControlLastVetVisitSensor,
    PawControlLastWalkDistanceSensor,
    PawControlLastWalkDurationSensor,
    PawControlLastWalkSensor,
    PawControlSensorBase,
    PawControlTotalDistanceTodaySensor,
    PawControlTotalFeedingsTodaySensor,
    PawControlTotalWalkTimeTodaySensor,
    PawControlWalkCountTodaySensor,
    PawControlWeeklyWalkCountSensor,
    PawControlWeightSensor,
    PawControlWeightTrendSensor,
    async_setup_entry,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


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
    async def test_async_setup_entry_success(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test successful sensor setup."""
        hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, mock_entry, async_add_entities)

        # Verify entities were added
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]

        # Should have base sensors for both dogs + module sensors for test_dog
        assert len(entities) > 6  # At least base sensors for 2 dogs

        # Check entity types
        entity_names = [entity._attr_name for entity in entities]
        assert any("Test Dog" in name for name in entity_names)
        assert any("Simple Dog" in name for name in entity_names)

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup with no dogs configured."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {CONF_DOGS: []}

        hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        # Should still call async_add_entities but with empty list
        async_add_entities.assert_called_once()
        entities = async_add_entities.call_args[0][0]
        assert len(entities) == 0

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
                    "modules": {MODULE_FEEDING: True},  # Only feeding enabled
                }
            ]
        }

        hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        entities = async_add_entities.call_args[0][0]

        # Should have base sensors + feeding sensors, but no walk/GPS/health sensors
        entity_types = [entity._sensor_type for entity in entities]
        assert any("feeding" in sensor_type for sensor_type in entity_types)
        assert not any("walk" in sensor_type for sensor_type in entity_types)
        assert not any("gps" in sensor_type for sensor_type in entity_types)


class TestPawControlSensorBase:
    """Test the base sensor class."""

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
    def base_sensor(self, mock_coordinator):
        """Create a base sensor instance."""
        return PawControlSensorBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_sensor",
            device_class=SensorDeviceClass.TIMESTAMP,
            state_class=SensorStateClass.MEASUREMENT,
            unit_of_measurement=UnitOfTime.SECONDS,
            icon="mdi:test",
        )

    def test_sensor_initialization(self, base_sensor):
        """Test sensor initialization."""
        assert base_sensor._dog_id == "test_dog"
        assert base_sensor._dog_name == "Test Dog"
        assert base_sensor._sensor_type == "test_sensor"
        assert base_sensor._attr_unique_id == "pawcontrol_test_dog_test_sensor"
        assert base_sensor._attr_name == "Test Dog Test Sensor"
        assert base_sensor._attr_device_class == SensorDeviceClass.TIMESTAMP
        assert base_sensor._attr_state_class == SensorStateClass.MEASUREMENT
        assert base_sensor._attr_native_unit_of_measurement == UnitOfTime.SECONDS
        assert base_sensor._attr_icon == "mdi:test"

    def test_device_info(self, base_sensor):
        """Test device info configuration."""
        device_info = base_sensor._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"

    def test_extra_state_attributes(self, base_sensor):
        """Test extra state attributes."""
        attrs = base_sensor.extra_state_attributes

        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        assert attrs["sensor_type"] == "test_sensor"
        assert "last_update" in attrs
        assert attrs["dog_breed"] == "Golden Retriever"
        assert attrs["dog_age"] == 5
        assert attrs["dog_size"] == "large"
        assert attrs["dog_weight"] == 30.0

    def test_extra_state_attributes_no_dog_data(self, mock_coordinator):
        """Test extra state attributes when no dog data available."""
        mock_coordinator.get_dog_data.return_value = None

        sensor = PawControlSensorBase(
            mock_coordinator, "test_dog", "Test Dog", "test_sensor"
        )

        attrs = sensor.extra_state_attributes
        assert attrs["dog_id"] == "test_dog"
        assert attrs["dog_name"] == "Test Dog"
        # Dog info should not be present
        assert "dog_breed" not in attrs

    def test_get_dog_data(self, base_sensor, mock_coordinator):
        """Test getting dog data."""
        result = base_sensor._get_dog_data()

        mock_coordinator.get_dog_data.assert_called_once_with("test_dog")
        assert result is not None
        assert "dog_info" in result

    def test_get_dog_data_coordinator_unavailable(self, base_sensor, mock_coordinator):
        """Test getting dog data when coordinator unavailable."""
        mock_coordinator.available = False

        result = base_sensor._get_dog_data()

        assert result is None
        mock_coordinator.get_dog_data.assert_not_called()

    def test_get_module_data(self, base_sensor, mock_coordinator):
        """Test getting module data."""
        mock_coordinator.get_module_data.return_value = {"test": "data"}

        result = base_sensor._get_module_data("feeding")

        mock_coordinator.get_module_data.assert_called_once_with("test_dog", "feeding")
        assert result == {"test": "data"}

    def test_available_property(self, base_sensor, mock_coordinator):
        """Test sensor availability."""
        # Coordinator available and dog data exists
        assert base_sensor.available is True

        # Coordinator unavailable
        mock_coordinator.available = False
        assert base_sensor.available is False

        # Coordinator available but no dog data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = None
        assert base_sensor.available is False


class TestLastActionSensor:
    """Test the last action sensor."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def last_action_sensor(self, mock_coordinator):
        """Create a last action sensor."""
        return PawControlLastActionSensor(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, last_action_sensor):
        """Test sensor initialization."""
        assert last_action_sensor._sensor_type == "last_action"
        assert last_action_sensor._attr_device_class == SensorDeviceClass.TIMESTAMP
        assert last_action_sensor._attr_icon == "mdi:clock-outline"

    def test_native_value_with_data(self, last_action_sensor, mock_coordinator):
        """Test native value with activity data."""
        dog_data = {
            "feeding": {"last_feeding": "2025-01-15T10:00:00"},
            "walk": {"last_walk": "2025-01-15T11:00:00"},
            "health": {"last_health_entry": "2025-01-15T09:00:00"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = last_action_sensor.native_value

        # Should return the most recent timestamp (walk at 11:00)
        expected = datetime(2025, 1, 15, 11, 0, 0)
        assert result == expected

    def test_native_value_no_data(self, last_action_sensor, mock_coordinator):
        """Test native value with no activity data."""
        mock_coordinator.get_dog_data.return_value = {}

        result = last_action_sensor.native_value

        assert result is None

    def test_native_value_invalid_timestamps(
        self, last_action_sensor, mock_coordinator
    ):
        """Test native value with invalid timestamps."""
        dog_data = {
            "feeding": {"last_feeding": "invalid_timestamp"},
            "walk": {"last_walk": "2025-01-15T11:00:00"},
            "health": {"last_health_entry": None},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = last_action_sensor.native_value

        # Should return the valid timestamp
        expected = datetime(2025, 1, 15, 11, 0, 0)
        assert result == expected

    def test_extra_state_attributes(self, last_action_sensor, mock_coordinator):
        """Test extra state attributes."""
        dog_data = {
            "feeding": {
                "last_feeding": "2025-01-15T10:00:00",
                "total_feedings_today": 2,
            },
            "walk": {
                "last_walk": "2025-01-15T11:00:00",
                "walks_today": 1,
            },
            "health": {"last_health_entry": "2025-01-15T09:00:00"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        attrs = last_action_sensor.extra_state_attributes

        assert attrs["last_feeding"] == "2025-01-15T10:00:00"
        assert attrs["last_walk"] == "2025-01-15T11:00:00"
        assert attrs["last_health_entry"] == "2025-01-15T09:00:00"
        assert "activity_summary" in attrs

    def test_generate_activity_summary(self, last_action_sensor):
        """Test activity summary generation."""
        dog_data = {
            "feeding": {"total_feedings_today": 3},
            "walk": {"walks_today": 2},
        }

        summary = last_action_sensor._generate_activity_summary(dog_data)

        assert "3 feedings" in summary
        assert "2 walks" in summary

    def test_generate_activity_summary_no_activities(self, last_action_sensor):
        """Test activity summary with no activities."""
        dog_data = {
            "feeding": {"total_feedings_today": 0},
            "walk": {"walks_today": 0},
        }

        summary = last_action_sensor._generate_activity_summary(dog_data)

        assert summary == "No activities today"


class TestDogStatusSensor:
    """Test the dog status sensor."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def status_sensor(self, mock_coordinator):
        """Create a dog status sensor."""
        return PawControlDogStatusSensor(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, status_sensor):
        """Test sensor initialization."""
        assert status_sensor._sensor_type == "status"
        assert status_sensor._attr_icon == "mdi:dog"

    def test_native_value_walking(self, status_sensor, mock_coordinator):
        """Test status when dog is walking."""
        dog_data = {
            "walk": {"walk_in_progress": True},
            "feeding": {},
            "gps": {},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "walking"

    def test_native_value_home_hungry(self, status_sensor, mock_coordinator):
        """Test status when dog is home and hungry."""
        dog_data = {
            "walk": {"walk_in_progress": False},
            "feeding": {"is_hungry": True},
            "gps": {"zone": "home"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "hungry"

    def test_native_value_needs_walk(self, status_sensor, mock_coordinator):
        """Test status when dog needs walk."""
        dog_data = {
            "walk": {"walk_in_progress": False, "needs_walk": True},
            "feeding": {"is_hungry": False},
            "gps": {"zone": "home"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "needs_walk"

    def test_native_value_home_content(self, status_sensor, mock_coordinator):
        """Test status when dog is home and content."""
        dog_data = {
            "walk": {"walk_in_progress": False, "needs_walk": False},
            "feeding": {"is_hungry": False},
            "gps": {"zone": "home"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "home"

    def test_native_value_at_park(self, status_sensor, mock_coordinator):
        """Test status when dog is at a specific zone."""
        dog_data = {
            "walk": {"walk_in_progress": False},
            "feeding": {},
            "gps": {"zone": "park"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "at_park"

    def test_native_value_away(self, status_sensor, mock_coordinator):
        """Test status when dog is away."""
        dog_data = {
            "walk": {"walk_in_progress": False},
            "feeding": {},
            "gps": {"zone": "unknown"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = status_sensor.native_value

        assert result == "away"

    def test_native_value_no_data(self, status_sensor, mock_coordinator):
        """Test status with no data."""
        mock_coordinator.get_dog_data.return_value = None

        result = status_sensor.native_value

        assert result == "unknown"


class TestActivityScoreSensor:
    """Test the activity score sensor."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def activity_sensor(self, mock_coordinator):
        """Create an activity score sensor."""
        return PawControlActivityScoreSensor(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, activity_sensor):
        """Test sensor initialization."""
        assert activity_sensor._sensor_type == "activity_score"
        assert activity_sensor._attr_state_class == SensorStateClass.MEASUREMENT
        assert activity_sensor._attr_native_unit_of_measurement == PERCENTAGE
        assert activity_sensor._attr_icon == "mdi:chart-line"

    def test_native_value_high_activity(self, activity_sensor, mock_coordinator):
        """Test activity score with high activity."""
        dog_data = {
            "walk": {
                "walks_today": 3,
                "total_duration_today": 120,  # 2 hours
            },
            "feeding": {
                "feeding_schedule_adherence": 95.0,
                "daily_target_met": True,
            },
            "gps": {"last_seen": "2025-01-15T11:00:00"},
            "health": {"health_status": "excellent"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        with patch(
            "homeassistant.util.dt.utcnow", return_value=datetime(2025, 1, 15, 12, 0, 0)
        ):
            result = activity_sensor.native_value

        assert result is not None
        assert isinstance(result, float)
        assert 80 <= result <= 100  # Should be high score

    def test_native_value_low_activity(self, activity_sensor, mock_coordinator):
        """Test activity score with low activity."""
        dog_data = {
            "walk": {
                "walks_today": 0,
                "total_duration_today": 0,
            },
            "feeding": {
                "feeding_schedule_adherence": 50.0,
                "daily_target_met": False,
            },
            "gps": {},
            "health": {"health_status": "unwell"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        result = activity_sensor.native_value

        assert result is not None
        assert isinstance(result, float)
        assert 0 <= result <= 50  # Should be low score

    def test_native_value_no_data(self, activity_sensor, mock_coordinator):
        """Test activity score with no data."""
        mock_coordinator.get_dog_data.return_value = None

        result = activity_sensor.native_value

        assert result is None

    def test_calculate_walk_score(self, activity_sensor):
        """Test walk score calculation."""
        # High activity
        walk_data = {"walks_today": 3, "total_duration_today": 150}
        score = activity_sensor._calculate_walk_score(walk_data)
        assert score >= 75

        # No activity
        walk_data = {"walks_today": 0, "total_duration_today": 0}
        score = activity_sensor._calculate_walk_score(walk_data)
        assert score == 0

        # Moderate activity
        walk_data = {"walks_today": 1, "total_duration_today": 60}
        score = activity_sensor._calculate_walk_score(walk_data)
        assert 25 <= score <= 50

    def test_calculate_feeding_score(self, activity_sensor):
        """Test feeding score calculation."""
        # Perfect adherence with target met
        feeding_data = {"feeding_schedule_adherence": 90, "daily_target_met": True}
        score = activity_sensor._calculate_feeding_score(feeding_data)
        assert score == 100  # 90 + 20 = 110, capped at 100

        # Good adherence without target met
        feeding_data = {"feeding_schedule_adherence": 80, "daily_target_met": False}
        score = activity_sensor._calculate_feeding_score(feeding_data)
        assert score == 80

    def test_calculate_gps_score(self, activity_sensor):
        """Test GPS score calculation."""
        # Recent GPS data
        gps_data = {"last_seen": "2025-01-15T11:00:00"}

        with patch(
            "homeassistant.util.dt.utcnow",
            return_value=datetime(2025, 1, 15, 11, 30, 0),
        ):
            score = activity_sensor._calculate_gps_score(gps_data)

        assert score >= 90  # Recent data should have high score

        # Old GPS data
        gps_data = {"last_seen": "2025-01-14T11:00:00"}

        with patch(
            "homeassistant.util.dt.utcnow",
            return_value=datetime(2025, 1, 15, 11, 30, 0),
        ):
            score = activity_sensor._calculate_gps_score(gps_data)

        assert score < 50  # Old data should have low score

        # No GPS data
        gps_data = {}
        score = activity_sensor._calculate_gps_score(gps_data)
        assert score == 0

    def test_calculate_health_score(self, activity_sensor):
        """Test health score calculation."""
        # Excellent health
        health_data = {"health_status": "excellent"}
        score = activity_sensor._calculate_health_score(health_data)
        assert score == 100

        # Good health
        health_data = {"health_status": "good"}
        score = activity_sensor._calculate_health_score(health_data)
        assert score == 80

        # Poor health
        health_data = {"health_status": "sick"}
        score = activity_sensor._calculate_health_score(health_data)
        assert score == 20

        # Unknown health status
        health_data = {"health_status": "unknown"}
        score = activity_sensor._calculate_health_score(health_data)
        assert score == 70  # Default

    def test_generate_score_explanation(self, activity_sensor):
        """Test score explanation generation."""
        dog_data = {
            "walk": {"walks_today": 0},
            "feeding": {"daily_target_met": True},
        }

        explanation = activity_sensor._generate_score_explanation(dog_data)

        assert "No walks today" in explanation
        assert "Feeding goals met" in explanation

    def test_extra_state_attributes(self, activity_sensor, mock_coordinator):
        """Test extra state attributes."""
        dog_data = {
            "walk": {"walks_today": 2},
            "feeding": {"feeding_schedule_adherence": 90},
            "gps": {"last_seen": "2025-01-15T11:00:00"},
            "health": {"health_status": "good"},
        }
        mock_coordinator.get_dog_data.return_value = dog_data

        attrs = activity_sensor.extra_state_attributes

        assert "walk_score" in attrs
        assert "feeding_score" in attrs
        assert "gps_score" in attrs
        assert "health_score" in attrs
        assert "score_explanation" in attrs


class TestFeedingSensors:
    """Test feeding-related sensors."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_module_data.return_value = {
            "last_feeding": "2025-01-15T10:00:00",
            "last_feeding_type": "breakfast",
            "total_feedings_today": 3,
            "feeding_schedule_adherence": 95.0,
            "feedings_today": {
                "breakfast": 1,
                "lunch": 1,
                "dinner": 1,
                "snack": 0,
            },
        }
        return coordinator

    def test_last_feeding_sensor(self, mock_coordinator):
        """Test last feeding sensor."""
        sensor = PawControlLastFeedingSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._sensor_type == "last_feeding"
        assert sensor._attr_device_class == SensorDeviceClass.TIMESTAMP
        assert sensor._attr_icon == "mdi:food-drumstick"

        result = sensor.native_value
        expected = datetime(2025, 1, 15, 10, 0, 0)
        assert result == expected

    def test_feeding_count_today_sensor(self, mock_coordinator):
        """Test feeding count today sensor for specific meal type."""
        sensor = PawControlFeedingCountTodaySensor(
            mock_coordinator, "test_dog", "Test Dog", "breakfast"
        )

        assert sensor._sensor_type == "feeding_count_today_breakfast"
        assert sensor._meal_type == "breakfast"
        assert sensor._attr_name == "Test Dog Breakfast Count Today"

        result = sensor.native_value
        assert result == 1

    def test_total_feedings_today_sensor(self, mock_coordinator):
        """Test total feedings today sensor."""
        sensor = PawControlTotalFeedingsTodaySensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._sensor_type == "total_feedings_today"
        assert sensor._attr_state_class == SensorStateClass.TOTAL_INCREASING

        result = sensor.native_value
        assert result == 3

    def test_daily_calories_sensor(self, mock_coordinator):
        """Test daily calories sensor."""
        sensor = PawControlDailyCaloriesSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._sensor_type == "daily_calories"
        assert sensor._attr_native_unit_of_measurement == UnitOfEnergy.KILO_CALORIE

        result = sensor.native_value
        assert result == 600.0  # 3 feedings * 200 calories

    def test_feeding_schedule_adherence_sensor(self, mock_coordinator):
        """Test feeding schedule adherence sensor."""
        sensor = PawControlFeedingScheduleAdherenceSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._sensor_type == "feeding_schedule_adherence"
        assert sensor._attr_native_unit_of_measurement == PERCENTAGE

        result = sensor.native_value
        assert result == 95.0


class TestWalkSensors:
    """Test walk-related sensors."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_module_data.return_value = {
            "last_walk": "2025-01-15T09:00:00",
            "last_walk_duration": 45.0,
            "last_walk_distance": 2000.0,
            "walks_today": 2,
            "total_duration_today": 90.0,
            "weekly_walk_count": 14,
            "weekly_duration": 630.0,
        }
        return coordinator

    def test_last_walk_sensor(self, mock_coordinator):
        """Test last walk sensor."""
        sensor = PawControlLastWalkSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._sensor_type == "last_walk"
        assert sensor._attr_device_class == SensorDeviceClass.TIMESTAMP

        result = sensor.native_value
        expected = datetime(2025, 1, 15, 9, 0, 0)
        assert result == expected

    def test_last_walk_duration_sensor(self, mock_coordinator):
        """Test last walk duration sensor."""
        sensor = PawControlLastWalkDurationSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._attr_native_unit_of_measurement == UnitOfTime.MINUTES

        result = sensor.native_value
        assert result == 45.0

    def test_last_walk_distance_sensor(self, mock_coordinator):
        """Test last walk distance sensor."""
        sensor = PawControlLastWalkDistanceSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._attr_native_unit_of_measurement == "m"
        assert sensor._attr_icon == "mdi:map-marker-path"

        result = sensor.native_value
        assert result == 2000.0

    def test_walk_count_today_sensor(self, mock_coordinator):
        """Test walk count today sensor."""
        sensor = PawControlWalkCountTodaySensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        result = sensor.native_value
        assert result == 2

    def test_total_walk_time_today_sensor(self, mock_coordinator):
        """Test total walk time today sensor."""
        sensor = PawControlTotalWalkTimeTodaySensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        result = sensor.native_value
        assert result == 90.0

    def test_weekly_walk_count_sensor(self, mock_coordinator):
        """Test weekly walk count sensor."""
        sensor = PawControlWeeklyWalkCountSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        result = sensor.native_value
        assert result == 14

    def test_average_walk_duration_sensor(self, mock_coordinator):
        """Test average walk duration sensor."""
        sensor = PawControlAverageWalkDurationSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        result = sensor.native_value
        assert result == 45.0  # 630 / 14 = 45


class TestGPSSensors:
    """Test GPS-related sensors."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_module_data.return_value = {
            "speed": 5.2,
            "distance_from_home": 150.0,
            "accuracy": 8.0,
            "zone": "park",
            "battery_level": 85,
        }
        return coordinator

    def test_current_speed_sensor(self, mock_coordinator):
        """Test current speed sensor."""
        sensor = PawControlCurrentSpeedSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._attr_device_class == SensorDeviceClass.SPEED
        assert (
            sensor._attr_native_unit_of_measurement == UnitOfSpeed.KILOMETERS_PER_HOUR
        )

        result = sensor.native_value
        assert result == 5.2

    def test_distance_from_home_sensor(self, mock_coordinator):
        """Test distance from home sensor."""
        sensor = PawControlDistanceFromHomeSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._attr_device_class == SensorDeviceClass.DISTANCE
        assert sensor._attr_native_unit_of_measurement == UnitOfLength.METERS

        result = sensor.native_value
        assert result == 150.0

    def test_gps_accuracy_sensor(self, mock_coordinator):
        """Test GPS accuracy sensor."""
        sensor = PawControlGPSAccuracySensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._attr_device_class == SensorDeviceClass.DISTANCE
        assert sensor._attr_native_unit_of_measurement == UnitOfLength.METERS

        result = sensor.native_value
        assert result == 8.0

    def test_current_zone_sensor(self, mock_coordinator):
        """Test current zone sensor."""
        sensor = PawControlCurrentZoneSensor(mock_coordinator, "test_dog", "Test Dog")

        result = sensor.native_value
        assert result == "park"

    def test_gps_battery_level_sensor(self, mock_coordinator):
        """Test GPS battery level sensor."""
        sensor = PawControlGPSBatteryLevelSensor(
            mock_coordinator, "test_dog", "Test Dog"
        )

        assert sensor._attr_device_class == SensorDeviceClass.BATTERY
        assert sensor._attr_native_unit_of_measurement == PERCENTAGE

        result = sensor.native_value
        assert result == 85


class TestHealthSensors:
    """Test health-related sensors."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_module_data.return_value = {
            "current_weight": 28.5,
            "weight_trend": "increasing",
            "activity_level": "high",
            "last_vet_visit": "2024-12-15T10:00:00",
            "last_grooming": "2025-01-01T14:00:00",
            "health_status": "excellent",
            "medications_due": ["Flea treatment", "Heartworm"],
            "active_medications": ["Daily vitamin", "Joint supplement"],
        }
        return coordinator

    def test_weight_sensor(self, mock_coordinator):
        """Test weight sensor."""
        sensor = PawControlWeightSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._attr_device_class == SensorDeviceClass.WEIGHT
        assert sensor._attr_native_unit_of_measurement == UnitOfMass.KILOGRAMS

        result = sensor.native_value
        assert result == 28.5

    def test_weight_trend_sensor(self, mock_coordinator):
        """Test weight trend sensor."""
        sensor = PawControlWeightTrendSensor(mock_coordinator, "test_dog", "Test Dog")

        result = sensor.native_value
        assert result == "increasing"

    def test_last_vet_visit_sensor(self, mock_coordinator):
        """Test last vet visit sensor."""
        sensor = PawControlLastVetVisitSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor._attr_device_class == SensorDeviceClass.TIMESTAMP

        result = sensor.native_value
        expected = datetime(2024, 12, 15, 10, 0, 0)
        assert result == expected

    def test_health_status_sensor(self, mock_coordinator):
        """Test health status sensor."""
        sensor = PawControlHealthStatusSensor(mock_coordinator, "test_dog", "Test Dog")

        result = sensor.native_value
        assert result == "excellent"


class TestSensorErrorHandling:
    """Test sensor error handling scenarios."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_sensor_with_module_data_none(self, mock_coordinator):
        """Test sensor behavior when module data returns None."""
        mock_coordinator.get_module_data.return_value = None

        sensor = PawControlLastFeedingSensor(mock_coordinator, "test_dog", "Test Dog")

        result = sensor.native_value
        assert result is None

    def test_sensor_with_invalid_timestamp(self, mock_coordinator):
        """Test sensor behavior with invalid timestamp."""
        mock_coordinator.get_module_data.return_value = {
            "last_feeding": "invalid_timestamp"
        }

        sensor = PawControlLastFeedingSensor(mock_coordinator, "test_dog", "Test Dog")

        result = sensor.native_value
        assert result is None

    def test_sensor_with_missing_fields(self, mock_coordinator):
        """Test sensor behavior with missing fields."""
        mock_coordinator.get_module_data.return_value = {}

        # Test feeding sensor
        feeding_sensor = PawControlTotalFeedingsTodaySensor(
            mock_coordinator, "test_dog", "Test Dog"
        )
        assert feeding_sensor.native_value == 0

        # Test walk sensor
        walk_sensor = PawControlWalkCountTodaySensor(
            mock_coordinator, "test_dog", "Test Dog"
        )
        assert walk_sensor.native_value == 0

    def test_sensor_with_coordinator_unavailable(self, mock_coordinator):
        """Test sensor availability when coordinator is unavailable."""
        mock_coordinator.available = False

        sensor = PawControlLastFeedingSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor.available is False

    def test_sensor_with_dog_data_none(self, mock_coordinator):
        """Test sensor availability when dog data is None."""
        mock_coordinator.get_dog_data.return_value = None

        sensor = PawControlLastFeedingSensor(mock_coordinator, "test_dog", "Test Dog")

        assert sensor.available is False


class TestSensorIntegration:
    """Test sensor integration scenarios."""

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
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                }
            ]
        }

        hass.data[DOMAIN] = {"test_entry": {"coordinator": coordinator}}

        async_add_entities = AsyncMock()

        await async_setup_entry(hass, entry, async_add_entities)

        entities = async_add_entities.call_args[0][0]

        # Should have many entities for all modules
        assert len(entities) >= 25  # Base + all module sensors

        # Verify we have sensors from each module
        sensor_types = [entity._sensor_type for entity in entities]

        # Base sensors
        assert any("last_action" in sensor_type for sensor_type in sensor_types)
        assert any("status" in sensor_type for sensor_type in sensor_types)
        assert any("activity_score" in sensor_type for sensor_type in sensor_types)

        # Feeding sensors
        assert any("feeding" in sensor_type for sensor_type in sensor_types)

        # Walk sensors
        assert any("walk" in sensor_type for sensor_type in sensor_types)

        # GPS sensors
        assert any(
            "gps" in sensor_type or "distance" in sensor_type or "speed" in sensor_type
            for sensor_type in sensor_types
        )

        # Health sensors
        assert any(
            "weight" in sensor_type or "health" in sensor_type
            for sensor_type in sensor_types
        )

    def test_sensor_uniqueness(self):
        """Test that sensors have unique IDs."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create multiple sensors for the same dog - test actual sensor classes
        sensors = [
            PawControlLastActionSensor(coordinator, "test_dog", "Test Dog"),
            PawControlDogStatusSensor(coordinator, "test_dog", "Test Dog"),
            PawControlActivityScoreSensor(coordinator, "test_dog", "Test Dog"),
            PawControlLastFeedingSensor(coordinator, "test_dog", "Test Dog"),
            PawControlLastWalkSensor(coordinator, "test_dog", "Test Dog"),
        ]

        unique_ids = [sensor._attr_unique_id for sensor in sensors]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

    def test_sensor_device_grouping(self):
        """Test that sensors are properly grouped by device."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create sensors for two different dogs
        dog1_sensor = PawControlLastActionSensor(coordinator, "dog1", "Dog 1")
        dog2_sensor = PawControlLastActionSensor(coordinator, "dog2", "Dog 2")

        # Check device info
        dog1_device = dog1_sensor._attr_device_info
        dog2_device = dog2_sensor._attr_device_info

        assert dog1_device["identifiers"] == {(DOMAIN, "dog1")}
        assert dog2_device["identifiers"] == {(DOMAIN, "dog2")}
        assert dog1_device["name"] == "Dog 1"
        assert dog2_device["name"] == "Dog 2"
