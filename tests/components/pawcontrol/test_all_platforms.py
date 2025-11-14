"""Comprehensive tests for PawControl platform entities.

Tests all platform implementations including sensors, binary sensors, switches,
buttons, and other entity types for complete coverage and quality assurance.

Quality Scale: Platinum target
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_MODULES,
    DOMAIN,
    MODULE_GROOMING,
)
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import (
    ConfigEntryDataPayload,
    CoordinatorDataPayload,
    CoordinatorDogData,
    CoordinatorModuleState,
    CoordinatorRuntimeManagers,
    DogConfigData,
    DogModulesConfig,
    PawControlRuntimeData,
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
def mock_config_entry_data() -> ConfigEntryDataPayload:
    """Create mock config entry data with comprehensive dog setup."""
    dog_modules: DogModulesConfig = {
        "feeding": True,
        "walk": True,
        "health": True,
        "gps": True,
        "garden": True,
        "notifications": True,
        "dashboard": True,
    }
    dog: DogConfigData = {
        CONF_DOG_ID: "test_dog",
        CONF_DOG_NAME: "Test Dog",
        "dog_breed": "Test Breed",
        "dog_age": 4,
        "dog_weight": 22.5,
        "dog_size": "medium",
        CONF_MODULES: dog_modules,
    }

    return ConfigEntryDataPayload(
        name="PawControl Platform Test",
        dogs=[dog],
        entity_profile="standard",
        setup_timestamp="2024-01-01T00:00:00+00:00",
    )


@pytest.fixture
def mock_coordinator() -> Mock:
    """Create comprehensive mock coordinator with realistic data."""
    coordinator = Mock()
    coordinator.available = True
    coordinator.config_entry = Mock()
    coordinator.config_entry.entry_id = "test_entry_id"

    # Mock comprehensive dog data
    last_garden_start = dt_util.utcnow() - timedelta(hours=2)
    last_garden_end = dt_util.utcnow() - timedelta(hours=1, minutes=10)
    dog_payload: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
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
                "health_emergency": True,
                "emergency_mode": {
                    "emergency_type": "diabetes",
                    "portion_adjustment": 0.85,
                    "activated_at": (dt_util.utcnow() - timedelta(hours=1)).isoformat(),
                    "expires_at": (dt_util.utcnow() + timedelta(hours=5)).isoformat(),
                    "status": "active",
                },
                "diet_validation_summary": {
                    "conflict_count": 1,
                    "warning_count": 2,
                    "total_diets": 3,
                    "compatibility_score": 82.5,
                    "compatibility_level": "good",
                    "diet_validation_adjustment": 0.925,
                    "adjustment_direction": "decrease",
                    "safety_factor": 0.8,
                    "percentage_adjustment": -7.5,
                    "adjustment_info": "Reduce portions slightly due to vet plan",
                    "has_adjustments": True,
                    "vet_consultation_state": "recommended",
                    "vet_consultation_recommended": True,
                    "consultation_urgency": "medium",
                    "conflicts": ["High-fat treat conflicts with diabetic plan"],
                    "warnings": ["Monitor hydration closely", "Avoid late snacks"],
                },
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
            "garden": {
                "status": "active",
                "time_today_minutes": 35.5,
                "sessions_today": 2,
                "poop_today": 1,
                "activities_today": 3,
                "activities_total": 12,
                "last_session": {
                    "session_id": "garden-session-123",
                    "start_time": last_garden_start.isoformat(),
                    "end_time": last_garden_end.isoformat(),
                    "duration_minutes": 50.0,
                    "activity_count": 4,
                    "poop_count": 1,
                    "status": "completed",
                    "weather_conditions": "Sunny with mild breeze",
                },
                "stats": {
                    "average_session_duration": 28.5,
                    "favorite_activities": [
                        {"activity": "sunbathing", "count": 4},
                        {"activity": "chasing butterflies", "count": 2},
                    ],
                    "weekly_summary": {
                        "session_count": 5,
                        "total_time_minutes": 140.0,
                        "poop_events": 3,
                        "average_duration": 28.0,
                        "updated": dt_util.utcnow().isoformat(),
                    },
                    "last_garden_visit": (
                        dt_util.utcnow() - timedelta(hours=3)
                    ).isoformat(),
                    "total_sessions": 12,
                    "total_time_minutes": 320.0,
                    "total_poop_count": 6,
                    "most_active_time_of_day": "evening",
                    "total_activities": 42,
                },
                "weather_summary": {
                    "conditions": ["Pleasant sunshine"],
                    "average_temperature": 23.5,
                },
                "pending_confirmations": [
                    {
                        "session_id": "garden-session-123",
                        "created": (
                            dt_util.utcnow() - timedelta(minutes=5)
                        ).isoformat(),
                        "expires": (
                            dt_util.utcnow() + timedelta(minutes=5)
                        ).isoformat(),
                    }
                ],
                "hours_since_last_session": 1.25,
            },
            "visitor_mode_active": False,
            "visitor_mode_started": None,
        },
    )
    coordinator.data = cast(
        CoordinatorDataPayload,
        {"test_dog": dog_payload},
    )

    def get_dog_data(dog_id: str) -> CoordinatorDogData | None:
        return cast(CoordinatorDogData | None, coordinator.data.get(dog_id))

    def get_module_data(dog_id: str, module: str) -> CoordinatorModuleState:
        dog_data = cast(CoordinatorDogData, coordinator.data.get(dog_id, {}))
        return cast(
            CoordinatorModuleState,
            dog_data.get(module, cast(CoordinatorModuleState, {})),
        )

    coordinator.get_dog_data = get_dog_data
    coordinator.get_module_data = get_module_data
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_request_selective_refresh = AsyncMock()
    garden_data = coordinator.data["test_dog"]["garden"]
    coordinator.garden_manager = SimpleNamespace(
        build_garden_snapshot=lambda dog_id: garden_data,
        is_dog_in_garden=lambda dog_id: garden_data.get("status") == "active",
        has_pending_confirmation=lambda dog_id: bool(
            garden_data.get("pending_confirmations")
        ),
    )
    coordinator.runtime_managers = CoordinatorRuntimeManagers(
        garden_manager=coordinator.garden_manager,
    )

    return coordinator


class TestSensorPlatform:
    """Test suite for sensor platform entities."""

    async def test_sensor_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: ConfigEntryDataPayload,
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
        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
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
        mock_config_entry_data: ConfigEntryDataPayload,
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
        mock_config_entry_data: ConfigEntryDataPayload,
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
        mock_config_entry_data: ConfigEntryDataPayload,
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
        mock_config_entry_data: ConfigEntryDataPayload,
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

    async def test_garden_sensors(self, mock_coordinator: Mock) -> None:
        """Test newly added garden tracking sensors."""
        from custom_components.pawcontrol.sensor import (
            PawControlGardenActivitiesCountSensor,
            PawControlGardenSessionsTodaySensor,
            PawControlGardenTimeTodaySensor,
            PawControlLastGardenSessionHoursSensor,
            PawControlLastGardenSessionSensor,
        )

        garden_time_sensor = PawControlGardenTimeTodaySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert garden_time_sensor.native_value == 35.5

        attrs = garden_time_sensor.extra_state_attributes
        assert attrs["garden_status"] == "active"
        pending = attrs["pending_confirmations"]
        assert isinstance(pending, list)
        assert pending
        assert pending[0]["session_id"] == "garden-session-123"
        assert "created" in pending[0]
        assert "expires" in pending[0]

        sessions_sensor = PawControlGardenSessionsTodaySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert sessions_sensor.native_value == 2

        last_session_sensor = PawControlLastGardenSessionSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        expected_end = dt_util.parse_datetime(
            mock_coordinator.data["test_dog"]["garden"]["last_session"]["end_time"]
        )
        assert last_session_sensor.native_value == expected_end

        activities_sensor = PawControlGardenActivitiesCountSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert activities_sensor.native_value == 12

        hours_sensor = PawControlLastGardenSessionHoursSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert hours_sensor.native_value == 1.25

    async def test_diet_validation_sensors(self, mock_coordinator: Mock) -> None:
        """Test diet validation metric sensors required by documentation."""
        from custom_components.pawcontrol.sensor import (
            PawControlDietCompatibilityScoreSensor,
            PawControlDietConflictCountSensor,
            PawControlDietValidationAdjustmentSensor,
            PawControlDietValidationStatusSensor,
            PawControlDietVetConsultationSensor,
            PawControlDietWarningCountSensor,
        )

        status_sensor = PawControlDietValidationStatusSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert status_sensor.native_value == "conflicts_detected"
        assert status_sensor.extra_state_attributes["diet_validation_available"] is True

        conflict_sensor = PawControlDietConflictCountSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert conflict_sensor.native_value == 1
        assert conflict_sensor.extra_state_attributes["conflicts"] == [
            "High-fat treat conflicts with diabetic plan"
        ]

        warning_sensor = PawControlDietWarningCountSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert warning_sensor.native_value == 2
        assert warning_sensor.extra_state_attributes["warnings"] == [
            "Monitor hydration closely",
            "Avoid late snacks",
        ]

        vet_sensor = PawControlDietVetConsultationSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert vet_sensor.native_value == "recommended"
        vet_attrs = vet_sensor.extra_state_attributes
        assert vet_attrs["vet_consultation_recommended"] is True
        assert vet_attrs["consultation_urgency"] == "medium"
        assert vet_attrs["has_conflicts"] is True

        adjustment_sensor = PawControlDietValidationAdjustmentSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert adjustment_sensor.native_value == 0.925
        adjustment_attrs = adjustment_sensor.extra_state_attributes
        assert adjustment_attrs["percentage_adjustment"] == -7.5
        assert adjustment_attrs["has_adjustments"] is True

        compatibility_sensor = PawControlDietCompatibilityScoreSensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert compatibility_sensor.native_value == 82.5
        assert (
            compatibility_sensor.extra_state_attributes["compatibility_level"] == "good"
        )


class TestBinarySensorPlatform:
    """Test suite for binary sensor platform entities."""

    async def test_binary_sensor_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: ConfigEntryDataPayload,
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

        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
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

        # All binary sensor entities should surface Home Assistant entity names
        # so they inherit the device's friendly name automatically.
        assert all(entity.has_entity_name for entity in entities)

        # Verify essential binary sensor entities were created
        entity_translation_keys = {entity.translation_key for entity in entities}
        assert "online" in entity_translation_keys
        assert "is_hungry" in entity_translation_keys
        assert "needs_walk" in entity_translation_keys

        # Every entity must expose a translation key so localized titles work.
        assert all(entity.translation_key for entity in entities)

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

    async def test_garden_binary_sensors(self, mock_coordinator: Mock) -> None:
        """Test garden-specific binary sensor entities."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlGardenPoopPendingBinarySensor,
            PawControlGardenSessionActiveBinarySensor,
            PawControlInGardenBinarySensor,
        )

        active_sensor = PawControlGardenSessionActiveBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert active_sensor.is_on is True

        in_garden_sensor = PawControlInGardenBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert in_garden_sensor.is_on is True

        poop_pending_sensor = PawControlGardenPoopPendingBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        assert poop_pending_sensor.is_on is True
        assert (
            poop_pending_sensor.extra_state_attributes["pending_confirmation_count"]
            == 1
        )

    async def test_health_emergency_binary_sensor(self, mock_coordinator: Mock) -> None:
        """Test health emergency binary sensor attributes and state."""
        from custom_components.pawcontrol.binary_sensor import (
            PawControlHealthEmergencyBinarySensor,
        )

        sensor = PawControlHealthEmergencyBinarySensor(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )

        assert sensor.is_on is True
        attrs = sensor.extra_state_attributes
        assert attrs["emergency_type"] == "diabetes"
        assert attrs["portion_adjustment"] == 0.85
        assert attrs["status"] == "active"

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
        mock_config_entry_data: ConfigEntryDataPayload,
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

        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
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

    async def test_grooming_switches_localize_labels(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Grooming switches should respect the Home Assistant language."""
        from custom_components.pawcontrol.switch import (
            PawControlFeatureSwitch,
            PawControlModuleSwitch,
        )

        mock_coordinator.hass.config.language = "de"

        grooming_module = PawControlModuleSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            module_id=MODULE_GROOMING,
            module_name="Grooming Tracking",
            icon="mdi:content-cut",
            initial_state=True,
        )

        assert grooming_module.name == "Test Dog Pflege-Tracking"

        grooming_schedule = PawControlFeatureSwitch(
            coordinator=mock_coordinator,
            dog_id="test_dog",
            dog_name="Test Dog",
            feature_id="grooming_schedule",
            feature_name="Grooming Schedule",
            icon="mdi:calendar",
            module=MODULE_GROOMING,
        )

        assert grooming_schedule.name == "Test Dog Pflegeplan"
        assert grooming_schedule.extra_state_attributes["feature_name"] == "Pflegeplan"


class TestButtonPlatform:
    """Test suite for button platform entities."""

    async def test_button_platform_setup(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: ConfigEntryDataPayload,
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

        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
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

    async def test_garden_buttons(
        self, hass: HomeAssistant, mock_coordinator: Mock
    ) -> None:
        """Test garden session control buttons trigger the expected services."""
        from custom_components.pawcontrol.button import (
            PawControlConfirmGardenPoopButton,
            PawControlEndGardenSessionButton,
            PawControlLogGardenActivityButton,
            PawControlStartGardenSessionButton,
        )

        garden_data = mock_coordinator.data["test_dog"]["garden"]

        # Start garden session button should call start service when idle
        garden_data["status"] = "idle"
        start_button = PawControlStartGardenSessionButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        start_button.hass = hass
        assert start_button.available is True
        with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
            await start_button.async_press()
        mock_call.assert_awaited_once_with(
            "pawcontrol",
            "start_garden_session",
            {"dog_id": "test_dog", "detection_method": "manual"},
            blocking=False,
        )

        # End garden session button should call end service when active
        garden_data["status"] = "active"
        end_button = PawControlEndGardenSessionButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        end_button.hass = hass
        assert end_button.available is True
        with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
            await end_button.async_press()
        mock_call.assert_awaited_once_with(
            "pawcontrol", "end_garden_session", {"dog_id": "test_dog"}, blocking=False
        )

        # Logging activity should call add activity service
        log_button = PawControlLogGardenActivityButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        log_button.hass = hass
        with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
            await log_button.async_press()
        mock_call.assert_awaited_once_with(
            "pawcontrol",
            "add_garden_activity",
            {
                "dog_id": "test_dog",
                "activity_type": "general",
                "notes": "Logged via garden activity button",
                "confirmed": True,
            },
            blocking=False,
        )

        # Confirm garden poop button should call confirmation service when pending
        confirm_button = PawControlConfirmGardenPoopButton(
            coordinator=mock_coordinator, dog_id="test_dog", dog_name="Test Dog"
        )
        confirm_button.hass = hass
        assert confirm_button.available is True
        with patch.object(hass.services, "async_call", AsyncMock()) as mock_call:
            await confirm_button.async_press()
        mock_call.assert_awaited_once_with(
            "pawcontrol",
            "confirm_garden_poop",
            {
                "dog_id": "test_dog",
                "confirmed": True,
                "quality": "normal",
                "size": "normal",
            },
            blocking=False,
        )


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
        mock_config_entry_data: ConfigEntryDataPayload,
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
        mock_config_entry_data: ConfigEntryDataPayload,
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

        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="standard",
                dogs=mock_config_entry_data[CONF_DOGS],
                script_manager=None,
            ),
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
        mock_config_entry_data: ConfigEntryDataPayload,
        mock_coordinator: Mock,
        pytestconfig: pytest.Config,
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
        store_runtime_data(
            hass,
            entry,
            PawControlRuntimeData(
                coordinator=mock_coordinator,
                data_manager=Mock(),
                notification_manager=Mock(),
                feeding_manager=Mock(),
                walk_manager=Mock(),
                entity_factory=Mock(),
                entity_profile="basic",
                dogs=many_dogs_config[CONF_DOGS],
                script_manager=None,
            ),
        )

        # Test sensor platform performance
        from custom_components.pawcontrol.sensor import async_setup_entry

        entities = []

        async def mock_add_entities(new_entities, update_before_add=True):
            entities.extend(new_entities)

        coverage_controller_loaded = pytestconfig.pluginmanager.hasplugin(
            "pawcontrol_cov_controller"
        )
        # The local coverage shim adds noticeable overhead on entity setup, so
        # allow higher thresholds when the plugin is active.
        setup_deadline = 1.0 if not coverage_controller_loaded else 2.5
        access_deadline = 0.1 if not coverage_controller_loaded else 0.35

        start_time = time.perf_counter()
        await async_setup_entry(hass, entry, mock_add_entities)
        end_time = time.perf_counter()

        setup_time = end_time - start_time

        # Should complete setup reasonably quickly even with many dogs
        assert setup_time < setup_deadline
        assert len(entities) > 0

        # Test entity state access performance
        start_time = time.perf_counter()
        for entity in entities[:20]:  # Test subset
            _ = entity.state
            _ = entity.available
            _ = entity.extra_state_attributes
        end_time = time.perf_counter()

        access_time = end_time - start_time
        assert access_time < access_deadline
