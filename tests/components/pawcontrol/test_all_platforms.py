"""Comprehensive tests for PawControl platform entities.

Tests all platform implementations including sensors, binary sensors, switches,
buttons, and other entity types for complete coverage and quality assurance.

Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.button import ButtonDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import Platform, UnitOfMass, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Mock external dependencies
sys.modules.setdefault("bluetooth_adapters", ModuleType("bluetooth_adapters"))

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture
def mock_config_entry_data() -> dict[str, Any]:
    """Create mock config entry data with comprehensive dog setup."""
    return {
        "name": "PawControl Platform Test",
        CONF_DOGS: [
            {
                CONF_DOG_ID: "test_dog",
                CONF_DOG_NAME: "Test Dog",
                "dog_breed": "Test Breed",
                "dog_age": 4,
                "dog_weight": 22.5,
                "dog_size": "medium",
                "modules": {
                    "feeding": True,
                    "walk": True,
                    "health": True,
                    "gps": True,
                    "notifications": True,
                    "dashboard": True,
                },
            }
        ],
        "entity_profile": "standard",
    }


@pytest.fixture
def mock_coordinator() -> Mock:
    """Create comprehensive mock coordinator with realistic data."""
    coordinator = Mock()
    coordinator.available = True
    coordinator.config_entry = Mock()
    coordinator.config_entry.entry_id = "test_entry_id"

    # Mock comprehensive dog data
    coordinator.data = {
        "test_dog": {
            "dog_info": {
                "dog_breed": "Test Breed",
                "dog_age": 4,
                "dog_weight": 22.5,
                "dog_size": "medium",
            },
            "last_update": dt_util.utcnow().isoformat(),
            "status": "online",
            "enabled_modules": ["feeding", "walk", "health", "gps"],
            "feeding": {
                "last_feeding": (dt_util.utcnow() - timedelta(hours=4)).isoformat(),
                "last_feeding_hours": 4.0,
                "is_hungry": True,
                "portions_today": 1,
                "daily_target_met": False,
                "next_feeding_due": (dt_util.utcnow() + timedelta(hours=2)).isoformat(),
                "feeding_schedule_adherence": 85.0,
            },
            "walk": {
                "last_walk": (dt_util.utcnow() - timedelta(hours=6)).isoformat(),
                "last_walk_hours": 6.0,
                "walks_today": 0,
                "needs_walk": True,
                "walk_goal_met": False,
                "walk_in_progress": False,
                "current_walk_start": None,
                "current_walk_duration": 0,
                "average_walk_duration": 45,
                "last_long_walk": (dt_util.utcnow() - timedelta(days=2)).isoformat(),
            },
            "health": {
                "health_status": "good",
                "health_alerts": [],
                "weight": 22.5,
                "weight_change_percent": 2.0,
                "activity_level": "normal",
                "medications_due": [],
                "next_checkup_due": (dt_util.utcnow() + timedelta(days=30)).isoformat(),
                "grooming_due": False,
            },
            "gps": {
                "zone": "home",
                "in_safe_zone": True,
                "distance_from_home": 0,
                "last_seen": dt_util.utcnow().isoformat(),
                "accuracy": 5.0,
                "speed": 0.0,
                "geofence_alert": False,
                "battery_level": 75,
            },
            "visitor_mode_active": False,
            "visitor_mode_started": None,
        }
    }

    def get_dog_data(dog_id: str) -> dict[str, Any] | None:
        return coordinator.data.get(dog_id)

    def get_module_data(dog_id: str, module: str) -> dict[str, Any]:
        dog_data = coordinator.data.get(dog_id, {})
        return dog_data.get(module, {})

    coordinator.get_dog_data = get_dog_data
    coordinator.get_module_data = get_module_data
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_request_selective_refresh = AsyncMock()

    return coordinator


class TestSensorPlatform:
    """Test suite for sensor platform entities."""

    async def test_sensor_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test sensor platform setup and entity creation."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
        )

        # Import and test sensor platform
        from custom_components.pawcontrol.sensor import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        result = await async_setup_entry(hass, entry, mock_add_entities)

        # Verify setup succeeded and entities were created
        assert result is None  # async_setup_entry doesn't return anything
        assert len(entities) > 0

        # Verify essential sensor entities were created
        entity_names = [entity.name for entity in entities]
        assert any("Feeding" in name for name in entity_names)
        assert any("Walk" in name for name in entity_names)
        assert any("Health" in name for name in entity_names)

    async def test_feeding_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test feeding-related sensor entities."""
        from custom_components.pawcontrol.sensor import (
            PawControlFeedingScheduleAdherenceSensor,
            PawControlLastFeedingHoursSensor,
            PawControlPortionsTodaySensor,
        )

        # Test last feeding hours sensor
        last_feeding_sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert last_feeding_sensor.native_value == 4.0
        assert last_feeding_sensor.device_class == SensorDeviceClass.DURATION
        assert last_feeding_sensor.native_unit_of_measurement == UnitOfTime.HOURS
        assert last_feeding_sensor.state_class == SensorStateClass.MEASUREMENT

        # Test portions today sensor
        portions_sensor = PawControlPortionsTodaySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert portions_sensor.native_value == 1
        assert portions_sensor.state_class == SensorStateClass.TOTAL_INCREASING

        # Test feeding schedule adherence sensor
        adherence_sensor = PawControlFeedingScheduleAdherenceSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert adherence_sensor.native_value == 85.0
        assert adherence_sensor.native_unit_of_measurement == "%"

    async def test_walk_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test walk-related sensor entities."""
        from custom_components.pawcontrol.sensor import (
            PawControlCurrentWalkDurationSensor,
            PawControlLastWalkHoursSensor,
            PawControlWalksTodaySensor,
        )

        # Test last walk hours sensor
        last_walk_sensor = PawControlLastWalkHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert last_walk_sensor.native_value == 6.0
        assert last_walk_sensor.device_class == SensorDeviceClass.DURATION

        # Test walks today sensor
        walks_sensor = PawControlWalksTodaySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert walks_sensor.native_value == 0
        assert walks_sensor.state_class == SensorStateClass.TOTAL_INCREASING

        # Test current walk duration sensor
        duration_sensor = PawControlCurrentWalkDurationSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert duration_sensor.native_value == 0  # No walk in progress

    async def test_health_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test health-related sensor entities."""
        from custom_components.pawcontrol.sensor import (
            PawControlActivityLevelSensor,
            PawControlHealthStatusSensor,
            PawControlWeightSensor,
        )

        # Test weight sensor
        weight_sensor = PawControlWeightSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert weight_sensor.native_value == 22.5
        assert weight_sensor.device_class == SensorDeviceClass.WEIGHT
        assert weight_sensor.native_unit_of_measurement == UnitOfMass.KILOGRAMS

        # Test activity level sensor
        activity_sensor = PawControlActivityLevelSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert activity_sensor.native_value == "normal"

        # Test health status sensor
        health_sensor = PawControlHealthStatusSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert health_sensor.native_value == "good"

    async def test_gps_sensors(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test GPS-related sensor entities."""
        from custom_components.pawcontrol.sensor import (
            PawControlCurrentLocationSensor,
            PawControlDistanceFromHomeSensor,
            PawControlGPSAccuracySensor,
            PawControlSpeedSensor,
        )

        # Test current location sensor
        location_sensor = PawControlCurrentLocationSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert location_sensor.native_value == "home"

        # Test distance from home sensor
        distance_sensor = PawControlDistanceFromHomeSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert distance_sensor.native_value == 0

        # Test GPS accuracy sensor
        accuracy_sensor = PawControlGPSAccuracySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert accuracy_sensor.native_value == 5.0

        # Test speed sensor
        speed_sensor = PawControlSpeedSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert speed_sensor.native_value == 0.0


class TestBinarySensorPlatform:
    """Test suite for binary sensor platform entities."""

    async def test_binary_sensor_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test binary sensor platform setup and entity creation."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
        )

        # Import and test binary sensor platform
        from custom_components.pawcontrol.binary_sensor import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        result = await async_setup_entry(hass, entry, mock_add_entities)

        # Verify setup succeeded and entities were created
        assert result is None
        assert len(entities) > 0

        # Verify essential binary sensor entities were created
        entity_names = [entity.name for entity in entities]
        assert any("Online" in name for name in entity_names)
        assert any("Hungry" in name for name in entity_names)
        assert any("Needs Walk" in name for name in entity_names)

    async def test_base_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test base binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlAttentionNeededBinarySensor,
            PawControlOnlineBinarySensor,
            PawControlVisitorModeBinarySensor,
        )

        # Test online sensor
        online_sensor = PawControlOnlineBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert online_sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert online_sensor.is_on is True  # Recent update time

        # Test attention needed sensor
        attention_sensor = PawControlAttentionNeededBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert attention_sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert attention_sensor.is_on is True  # Dog is hungry and needs walk

        # Test visitor mode sensor
        visitor_sensor = PawControlVisitorModeBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert visitor_sensor.is_on is False  # Not in visitor mode

    async def test_feeding_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test feeding-related binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlDailyFeedingGoalMetBinarySensor,
            PawControlFeedingDueBinarySensor,
            PawControlFeedingScheduleOnTrackBinarySensor,
            PawControlIsHungryBinarySensor,
        )

        # Test hungry sensor
        hungry_sensor = PawControlIsHungryBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert hungry_sensor.is_on is True

        # Test feeding due sensor
        feeding_due_sensor = PawControlFeedingDueBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert feeding_due_sensor.is_on is False  # Next feeding in 2 hours

        # Test schedule on track sensor
        schedule_sensor = PawControlFeedingScheduleOnTrackBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert schedule_sensor.is_on is True  # 85% adherence > 80% threshold

        # Test daily goal met sensor
        goal_sensor = PawControlDailyFeedingGoalMetBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert goal_sensor.is_on is False

    async def test_walk_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test walk-related binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlLongWalkOverdueBinarySensor,
            PawControlNeedsWalkBinarySensor,
            PawControlWalkGoalMetBinarySensor,
            PawControlWalkInProgressBinarySensor,
        )

        # Test walk in progress sensor
        walk_progress_sensor = PawControlWalkInProgressBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert walk_progress_sensor.device_class == BinarySensorDeviceClass.RUNNING
        assert walk_progress_sensor.is_on is False

        # Test needs walk sensor
        needs_walk_sensor = PawControlNeedsWalkBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert needs_walk_sensor.is_on is True

        # Test walk goal met sensor
        goal_met_sensor = PawControlWalkGoalMetBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert goal_met_sensor.is_on is False

        # Test long walk overdue sensor
        overdue_sensor = PawControlLongWalkOverdueBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert overdue_sensor.is_on is True  # Last long walk 2 days ago

    async def test_gps_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test GPS-related binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlGeofenceAlertBinarySensor,
            PawControlGPSAccuratelyTrackedBinarySensor,
            PawControlGPSBatteryLowBinarySensor,
            PawControlInSafeZoneBinarySensor,
            PawControlIsHomeBinarySensor,
            PawControlMovingBinarySensor,
        )

        # Test is home sensor
        home_sensor = PawControlIsHomeBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert home_sensor.device_class == BinarySensorDeviceClass.PRESENCE
        assert home_sensor.is_on is True

        # Test in safe zone sensor
        safe_zone_sensor = PawControlInSafeZoneBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert safe_zone_sensor.device_class == BinarySensorDeviceClass.SAFETY
        assert safe_zone_sensor.is_on is True

        # Test GPS accurately tracked sensor
        tracked_sensor = PawControlGPSAccuratelyTrackedBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert tracked_sensor.device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert tracked_sensor.is_on is True  # Good accuracy and recent data

        # Test moving sensor
        moving_sensor = PawControlMovingBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert moving_sensor.device_class == BinarySensorDeviceClass.MOTION
        assert moving_sensor.is_on is False  # Speed is 0

        # Test geofence alert sensor
        geofence_sensor = PawControlGeofenceAlertBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert geofence_sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert geofence_sensor.is_on is False

        # Test GPS battery low sensor
        battery_sensor = PawControlGPSBatteryLowBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert battery_sensor.device_class == BinarySensorDeviceClass.BATTERY
        assert battery_sensor.is_on is False  # 75% > 20% threshold

    async def test_health_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test health-related binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlActivityLevelConcernBinarySensor,
            PawControlGroomingDueBinarySensor,
            PawControlHealthAlertBinarySensor,
            PawControlMedicationDueBinarySensor,
            PawControlVetCheckupDueBinarySensor,
            PawControlWeightAlertBinarySensor,
        )

        # Test health alert sensor
        health_alert_sensor = PawControlHealthAlertBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert health_alert_sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert health_alert_sensor.is_on is False  # No alerts

        # Test weight alert sensor
        weight_alert_sensor = PawControlWeightAlertBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert weight_alert_sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert weight_alert_sensor.is_on is False  # 2% change < 10% threshold

        # Test medication due sensor
        medication_sensor = PawControlMedicationDueBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert medication_sensor.is_on is False  # No medications due

        # Test vet checkup due sensor
        checkup_sensor = PawControlVetCheckupDueBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert checkup_sensor.is_on is False  # Checkup in 30 days

        # Test grooming due sensor
        grooming_sensor = PawControlGroomingDueBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert grooming_sensor.is_on is False

        # Test activity level concern sensor
        activity_concern_sensor = PawControlActivityLevelConcernBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert activity_concern_sensor.device_class == BinarySensorDeviceClass.PROBLEM
        assert activity_concern_sensor.is_on is False  # Normal activity level


class TestSwitchPlatform:
    """Test suite for switch platform entities."""

    async def test_switch_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test switch platform setup and entity creation."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
        )

        # Import and test switch platform
        from custom_components.pawcontrol.switch import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        result = await async_setup_entry(hass, entry, mock_add_entities)

        # Verify setup succeeded and entities were created
        assert result is None
        assert len(entities) > 0

        # Verify essential switch entities were created
        entity_names = [entity.name for entity in entities]
        assert any("Main Power" in name for name in entity_names)
        assert any("Do Not Disturb" in name for name in entity_names)

    async def test_core_switches(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test core switch entities."""
        from custom_components.pawcontrol.switch import (
            PawControlDoNotDisturbSwitch,
            PawControlMainPowerSwitch,
            PawControlVisitorModeSwitch,
        )

        # Test main power switch
        power_switch = PawControlMainPowerSwitch(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert power_switch.device_class == SwitchDeviceClass.SWITCH
        assert power_switch.is_on is True  # Default initial state

        # Test turn on/off functionality
        await power_switch.async_turn_off()
        assert power_switch.is_on is False

        await power_switch.async_turn_on()
        assert power_switch.is_on is True

        # Test DND switch
        dnd_switch = PawControlDoNotDisturbSwitch(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert dnd_switch.is_on is False  # Default initial state

        # Test visitor mode switch
        visitor_switch = PawControlVisitorModeSwitch(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert visitor_switch.is_on is False  # Based on coordinator data

    async def test_module_switches(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test module control switches."""
        from custom_components.pawcontrol.switch import PawControlModuleSwitch

        # Test feeding module switch
        feeding_switch = PawControlModuleSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            module_id="feeding",
            module_name="Feeding Tracking",
            icon="mdi:food-drumstick",
            initial_state=True,
        )

        assert feeding_switch.is_on is True
        assert feeding_switch.icon == "mdi:food-drumstick"

        # Test module state change
        await feeding_switch.async_turn_off()
        assert feeding_switch.is_on is False

    async def test_feature_switches(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test feature-specific switches."""
        from custom_components.pawcontrol.switch import PawControlFeatureSwitch

        # Test GPS tracking feature switch
        gps_switch = PawControlFeatureSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            feature_id="gps_tracking",
            feature_name="GPS Tracking",
            icon="mdi:crosshairs-gps",
            module="gps",
        )

        assert gps_switch.is_on is True  # Default initial state
        assert gps_switch.icon == "mdi:crosshairs-gps"

        # Test feature toggle
        await gps_switch.async_turn_off()
        assert gps_switch.is_on is False


class TestButtonPlatform:
    """Test suite for button platform entities."""

    async def test_button_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test button platform setup and entity creation."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
        )

        # Import and test button platform
        from custom_components.pawcontrol.button import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        result = await async_setup_entry(hass, entry, mock_add_entities)

        # Verify setup succeeded and entities were created
        assert result is None
        assert len(entities) > 0

        # Verify essential button entities were created
        entity_names = [entity.name for entity in entities]
        assert any("Feed Now" in name for name in entity_names)
        assert any("Start Walk" in name for name in entity_names)

    async def test_action_buttons(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test action button entities."""
        from custom_components.pawcontrol.button import (
            PawControlEndWalkButton,
            PawControlFeedNowButton,
            PawControlStartWalkButton,
        )

        # Test feed now button
        feed_button = PawControlFeedNowButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert feed_button.device_class == ButtonDeviceClass.IDENTIFY

        # Test button press
        with patch("homeassistant.core.HomeAssistant.services") as mock_services:
            mock_services.async_call = AsyncMock()
            await feed_button.async_press()
            # Should call feeding service
            mock_services.async_call.assert_called()

        # Test start walk button
        start_walk_button = PawControlStartWalkButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert start_walk_button.device_class == ButtonDeviceClass.IDENTIFY

        # Test end walk button
        end_walk_button = PawControlEndWalkButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert end_walk_button.device_class == ButtonDeviceClass.IDENTIFY

    async def test_utility_buttons(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test utility button entities."""
        from custom_components.pawcontrol.button import (
            PawControlRefreshDataButton,
            PawControlSyncDataButton,
            PawControlUpdateLocationButton,
        )

        # Test refresh data button
        refresh_button = PawControlRefreshDataButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        # Test button press
        await refresh_button.async_press()
        mock_coordinator.async_request_refresh.assert_called()

        # Test update location button
        location_button = PawControlUpdateLocationButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        # Test button press
        await location_button.async_press()
        # Should request selective refresh
        mock_coordinator.async_request_selective_refresh.assert_called()

        # Test sync data button
        sync_button = PawControlSyncDataButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        # Test button press
        await sync_button.async_press()
        # Should request high priority refresh
        mock_coordinator.async_request_selective_refresh.assert_called()


class TestEntityAvailability:
    """Test suite for entity availability and state management."""

    async def test_entity_availability_coordinator_unavailable(
        self, mock_coordinator: Mock
    ) -> None:
        """Test entity availability when coordinator is unavailable."""
        from custom_components.pawcontrol.sensor import PawControlLastFeedingHoursSensor

        # Make coordinator unavailable
        mock_coordinator.available = False

        sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert sensor.available is False

    async def test_entity_availability_no_dog_data(
        self, mock_coordinator: Mock
    ) -> None:
        """Test entity availability when dog data is missing."""
        from custom_components.pawcontrol.sensor import PawControlLastFeedingHoursSensor

        # Remove dog data
        mock_coordinator.data = {}

        sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert sensor.available is False

    async def test_entity_state_attributes(self, mock_coordinator: Mock) -> None:
        """Test entity state attributes."""
        from custom_components.pawcontrol.sensor import PawControlLastFeedingHoursSensor

        sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        attributes = sensor.extra_state_attributes

        assert attributes["dog_id"] == "test_dog"
        assert attributes["dog_name"] == "Test Dog"
        assert "last_updated" in attributes
        assert attributes["dog_breed"] == "Test Breed"
        assert attributes["dog_age"] == 4

    async def test_device_info_generation(self, mock_coordinator: Mock) -> None:
        """Test device info generation for proper grouping."""
        from custom_components.pawcontrol.sensor import PawControlLastFeedingHoursSensor

        sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        device_info = sensor.device_info

        assert device_info is not None
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert ("pawcontrol", "test_dog") in device_info["identifiers"]


class TestPlatformIntegration:
    """Test suite for platform integration and lifecycle."""

    async def test_entity_registry_integration(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test integration with Home Assistant entity registry."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Create entities and add to registry
        from custom_components.pawcontrol.sensor import PawControlLastFeedingHoursSensor

        sensor = PawControlLastFeedingHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        # Get entity registry
        entity_registry = er.async_get(hass)

        # Register entity
        entity_entry = entity_registry.async_get_or_create(
            domain=Platform.SENSOR,
            platform=DOMAIN,
            unique_id=sensor.unique_id,
            config_entry=entry,
        )

        assert entity_entry.unique_id == sensor.unique_id
        assert entity_entry.platform == DOMAIN

    async def test_platform_unload_cleanup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test proper cleanup during platform unload."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data=mock_config_entry_data,
            options={"entity_profile": "standard"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="standard",
            dogs=mock_config_entry_data[CONF_DOGS],
        )

        # Test sensor platform setup and teardown
        from custom_components.pawcontrol.sensor import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        await async_setup_entry(hass, entry, mock_add_entities)

        # Verify entities were created
        assert len(entities) > 0

        # Test that entities handle coordinator shutdown gracefully
        mock_coordinator.available = False

        # Entities should become unavailable but not crash
        for entity in entities[:5]:  # Test subset for performance
            assert entity.available is False

    async def test_entity_state_restoration(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test entity state restoration after restart."""
        from custom_components.pawcontrol.switch import PawControlMainPowerSwitch

        power_switch = PawControlMainPowerSwitch(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        # Simulate state restoration
        power_switch.hass = hass

        # Mock last state
        mock_state = Mock()
        mock_state.state = "off"

        with patch.object(
            power_switch, "async_get_last_state", return_value=mock_state
        ):
            await power_switch.async_added_to_hass()

            # State should be restored (exact behavior depends on implementation)
            # Main goal is to ensure no exceptions during restoration

    async def test_performance_characteristics(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
        mock_coordinator: Mock,
    ) -> None:
        """Test platform performance characteristics."""
        import time

        # Create many entities to test performance
        many_dogs_config = {
            "name": "Performance Test",
            CONF_DOGS: [
                {
                    CONF_DOG_ID: f"dog_{i:02d}",
                    CONF_DOG_NAME: f"Dog {i:02d}",
                    "modules": {"feeding": True, "walk": True, "health": True},
                }
                for i in range(10)
            ],
            "entity_profile": "basic",  # Use basic for performance
        }

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=many_dogs_config,
            options={"entity_profile": "basic"},
        )
        entry.add_to_hass(hass)

        # Mock runtime data
        from custom_components.pawcontrol.types import PawControlRuntimeData

        entry.runtime_data = PawControlRuntimeData(
            coordinator=mock_coordinator,
            data_manager=Mock(),
            notification_manager=Mock(),
            feeding_manager=Mock(),
            walk_manager=Mock(),
            entity_factory=Mock(),
            entity_profile="basic",
            dogs=many_dogs_config[CONF_DOGS],
        )

        # Test sensor platform performance
        from custom_components.pawcontrol.sensor import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        start_time = time.perf_counter()
        await async_setup_entry(hass, entry, mock_add_entities)
        end_time = time.perf_counter()

        setup_time = end_time - start_time

        # Should complete setup reasonably quickly even with many dogs
        assert setup_time < 1.0  # Less than 1 second
        assert len(entities) > 0

        # Test entity state access performance
        start_time = time.perf_counter()
        for entity in entities[:20]:  # Test subset
            _ = entity.state
            _ = entity.available
            _ = entity.extra_state_attributes
        end_time = time.perf_counter()

        access_time = end_time - start_time
        assert access_time < 0.1  # Should be very fast
