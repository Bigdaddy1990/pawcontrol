"""Tests for binary sensor platform of Paw Control integration.

This module provides comprehensive test coverage for all binary sensor entities
including status indicators, alerts, and automated detection sensors. Tests
cover functionality, edge cases, error handling, and performance scenarios
to meet Home Assistant's Platinum quality standards.

Test Coverage:
- 23+ binary sensor entity classes
- Async setup with batching logic
- State calculation and availability
- Extra state attributes and device info
- Module-specific sensor creation
- Error handling and edge cases
- Performance testing with large setups
- Integration scenarios and coordinator interaction
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.binary_sensor import (
    PawControlActivityLevelConcernBinarySensor,
    PawControlAttentionNeededBinarySensor,
    PawControlBinarySensorBase,
    PawControlDailyFeedingGoalMetBinarySensor,
    PawControlFeedingDueBinarySensor,
    PawControlFeedingScheduleOnTrackBinarySensor,
    PawControlGeofenceAlertBinarySensor,
    PawControlGPSAccuratelyTrackedBinarySensor,
    PawControlGPSBatteryLowBinarySensor,
    PawControlGroomingDueBinarySensor,
    PawControlHealthAlertBinarySensor,
    PawControlInSafeZoneBinarySensor,
    PawControlIsHomeBinarySensor,
    PawControlIsHungryBinarySensor,
    PawControlLongWalkOverdueBinarySensor,
    PawControlMedicationDueBinarySensor,
    PawControlMovingBinarySensor,
    PawControlNeedsWalkBinarySensor,
    PawControlOnlineBinarySensor,
    PawControlVetCheckupDueBinarySensor,
    PawControlVisitorModeBinarySensor,
    PawControlWalkGoalMetBinarySensor,
    PawControlWalkInProgressBinarySensor,
    PawControlWeightAlertBinarySensor,
    _async_add_entities_in_batches,
    _create_base_binary_sensors,
    _create_feeding_binary_sensors,
    _create_gps_binary_sensors,
    _create_health_binary_sensors,
    _create_walk_binary_sensors,
    async_setup_entry,
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
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from homeassistant.components.binary_sensor import (
    DOMAIN as BINARY_SENSOR_DOMAIN,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util


class TestAsyncAddEntitiesInBatches:
    """Test the batching functionality for entity registration."""

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_single_batch(self):
        """Test batching with entities that fit in a single batch."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(10)]

        await _async_add_entities_in_batches(mock_add_entities, entities, batch_size=15)

        # Should be called once with all entities
        mock_add_entities.assert_called_once_with(entities, update_before_add=False)

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_multiple_batches(self):
        """Test batching with entities that require multiple batches."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(25)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=10, delay_between_batches=0.05
            )

        # Should be called 3 times (10 + 10 + 5)
        assert mock_add_entities.call_count == 3

        # Check that sleep was called between batches (2 times for 3 batches)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.05)

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_empty_list(self):
        """Test batching with empty entity list."""
        mock_add_entities = Mock()
        entities = []

        await _async_add_entities_in_batches(mock_add_entities, entities)

        # Should not be called with empty list
        mock_add_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_performance_large_setup(self):
        """Test batching performance with large entity setup (simulating 10 dogs)."""
        mock_add_entities = Mock()
        # Simulate 230 binary sensor entities (23 per dog * 10 dogs)
        entities = [Mock() for _ in range(230)]

        start_time = asyncio.get_event_loop().time()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12
            )

        end_time = asyncio.get_event_loop().time()

        # Should complete quickly even with large entity count
        assert end_time - start_time < 1.0

        # Should be called 20 times (230 / 12 = 19.17 -> 20 batches)
        assert mock_add_entities.call_count == 20


class TestAsyncSetupEntry:
    """Test the async setup entry function for binary sensor platform."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def mock_config_entry(self, mock_coordinator):
        """Create a mock config entry."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: True,
                        MODULE_GPS: True,
                        MODULE_HEALTH: True,
                    },
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Max",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_WALK: False,
                        MODULE_GPS: True,
                        MODULE_HEALTH: False,
                    },
                },
            ]
        }
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": entry.data[CONF_DOGS],
        }
        return entry

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_runtime_data(
        self, hass: HomeAssistant, mock_config_entry, mock_coordinator
    ):
        """Test setup entry using runtime_data structure."""
        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.binary_sensor._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should call batching function
        mock_batch_add.assert_called_once()

        # Get the entities that were passed to batching
        args, kwargs = mock_batch_add.call_args
        entities = args[1]  # Second argument is the entities list

        # Dog1 has all modules: 3 base + 4 feeding + 4 walk + 6 gps + 6 health = 23 entities
        # Dog2 has limited modules: 3 base + 4 feeding + 6 gps = 13 entities
        # Total: 36 entities
        assert len(entities) == 36

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_legacy_data_structure(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry using legacy data structure in hass.data."""
        hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {MODULE_FEEDING: True},
                }
            ]
        }
        entry.runtime_data = None

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.binary_sensor._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        mock_batch_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs_configured(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with no dogs configured."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {"coordinator": mock_coordinator, "dogs": []}

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.binary_sensor._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should still call batching function but with empty entity list
        mock_batch_add.assert_called_once()
        args, kwargs = mock_batch_add.call_args
        entities = args[1]
        assert len(entities) == 0


class TestEntityCreationFunctions:
    """Test the entity creation helper functions."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_create_base_binary_sensors(self, mock_coordinator):
        """Test creation of base binary sensors."""
        entities = _create_base_binary_sensors(mock_coordinator, "dog1", "Buddy")

        assert len(entities) == 3
        assert isinstance(entities[0], PawControlOnlineBinarySensor)
        assert isinstance(entities[1], PawControlAttentionNeededBinarySensor)
        assert isinstance(entities[2], PawControlVisitorModeBinarySensor)

    def test_create_feeding_binary_sensors(self, mock_coordinator):
        """Test creation of feeding binary sensors."""
        entities = _create_feeding_binary_sensors(mock_coordinator, "dog1", "Buddy")

        assert len(entities) == 4
        assert isinstance(entities[0], PawControlIsHungryBinarySensor)
        assert isinstance(entities[1], PawControlFeedingDueBinarySensor)
        assert isinstance(entities[2], PawControlFeedingScheduleOnTrackBinarySensor)
        assert isinstance(entities[3], PawControlDailyFeedingGoalMetBinarySensor)

    def test_create_walk_binary_sensors(self, mock_coordinator):
        """Test creation of walk binary sensors."""
        entities = _create_walk_binary_sensors(mock_coordinator, "dog1", "Buddy")

        assert len(entities) == 4
        assert isinstance(entities[0], PawControlWalkInProgressBinarySensor)
        assert isinstance(entities[1], PawControlNeedsWalkBinarySensor)
        assert isinstance(entities[2], PawControlWalkGoalMetBinarySensor)
        assert isinstance(entities[3], PawControlLongWalkOverdueBinarySensor)

    def test_create_gps_binary_sensors(self, mock_coordinator):
        """Test creation of GPS binary sensors."""
        entities = _create_gps_binary_sensors(mock_coordinator, "dog1", "Buddy")

        assert len(entities) == 6
        assert isinstance(entities[0], PawControlIsHomeBinarySensor)
        assert isinstance(entities[1], PawControlInSafeZoneBinarySensor)
        assert isinstance(entities[2], PawControlGPSAccuratelyTrackedBinarySensor)
        assert isinstance(entities[3], PawControlMovingBinarySensor)
        assert isinstance(entities[4], PawControlGeofenceAlertBinarySensor)
        assert isinstance(entities[5], PawControlGPSBatteryLowBinarySensor)

    def test_create_health_binary_sensors(self, mock_coordinator):
        """Test creation of health binary sensors."""
        entities = _create_health_binary_sensors(mock_coordinator, "dog1", "Buddy")

        assert len(entities) == 6
        assert isinstance(entities[0], PawControlHealthAlertBinarySensor)
        assert isinstance(entities[1], PawControlWeightAlertBinarySensor)
        assert isinstance(entities[2], PawControlMedicationDueBinarySensor)
        assert isinstance(entities[3], PawControlVetCheckupDueBinarySensor)
        assert isinstance(entities[4], PawControlGroomingDueBinarySensor)
        assert isinstance(entities[5], PawControlActivityLevelConcernBinarySensor)


class TestPawControlBinarySensorBase:
    """Test the base binary sensor class functionality."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def base_sensor(self, mock_coordinator):
        """Create a base binary sensor for testing."""
        return PawControlBinarySensorBase(
            mock_coordinator,
            "dog1",
            "Buddy",
            "test_sensor",
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            icon_on="mdi:check",
            icon_off="mdi:close",
            entity_category=EntityCategory.DIAGNOSTIC,
        )

    def test_base_sensor_initialization(self, base_sensor):
        """Test base sensor initialization."""
        assert base_sensor._dog_id == "dog1"
        assert base_sensor._dog_name == "Buddy"
        assert base_sensor._sensor_type == "test_sensor"
        assert base_sensor._attr_unique_id == "pawcontrol_dog1_test_sensor"
        assert base_sensor._attr_name == "Buddy Test Sensor"
        assert base_sensor._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert base_sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_base_sensor_device_info(self, base_sensor):
        """Test device info configuration."""
        device_info = base_sensor._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "dog1")}
        assert device_info["name"] == "Buddy"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Monitoring"
        assert device_info["sw_version"] == "1.0.0"
        assert "configuration_url" in device_info

    def test_base_sensor_icon_on_state(self, base_sensor):
        """Test icon when sensor is on."""
        with patch.object(base_sensor, "is_on", True):
            assert base_sensor.icon == "mdi:check"

    def test_base_sensor_icon_off_state(self, base_sensor):
        """Test icon when sensor is off."""
        with patch.object(base_sensor, "is_on", False):
            assert base_sensor.icon == "mdi:close"

    def test_base_sensor_icon_fallback(self, mock_coordinator):
        """Test icon fallback when no specific icons set."""
        sensor = PawControlBinarySensorBase(
            mock_coordinator, "dog1", "Buddy", "test_sensor"
        )

        with patch.object(sensor, "is_on", True):
            assert sensor.icon == "mdi:information-outline"

    def test_base_sensor_extra_state_attributes(self, base_sensor):
        """Test base extra state attributes."""
        mock_dog_data = {
            "dog_info": {
                "dog_breed": "Golden Retriever",
                "dog_age": 3,
                "dog_size": "large",
                "dog_weight": 30.5,
            }
        }

        with patch.object(base_sensor, "_get_dog_data", return_value=mock_dog_data):
            attrs = base_sensor.extra_state_attributes

            assert attrs[ATTR_DOG_ID] == "dog1"
            assert attrs[ATTR_DOG_NAME] == "Buddy"
            assert attrs["sensor_type"] == "test_sensor"
            assert attrs["dog_breed"] == "Golden Retriever"
            assert attrs["dog_age"] == 3
            assert attrs["dog_size"] == "large"
            assert attrs["dog_weight"] == 30.5
            assert "last_update" in attrs

    def test_base_sensor_extra_state_attributes_no_dog_data(self, base_sensor):
        """Test extra state attributes when no dog data available."""
        with patch.object(base_sensor, "_get_dog_data", return_value=None):
            attrs = base_sensor.extra_state_attributes

            assert attrs[ATTR_DOG_ID] == "dog1"
            assert attrs[ATTR_DOG_NAME] == "Buddy"
            assert attrs["sensor_type"] == "test_sensor"
            assert "dog_breed" not in attrs

    def test_base_sensor_get_dog_data(self, base_sensor, mock_coordinator):
        """Test getting dog data from coordinator."""
        mock_coordinator.get_dog_data.return_value = {"test": "data"}

        result = base_sensor._get_dog_data()

        mock_coordinator.get_dog_data.assert_called_once_with("dog1")
        assert result == {"test": "data"}

    def test_base_sensor_get_dog_data_coordinator_unavailable(
        self, base_sensor, mock_coordinator
    ):
        """Test getting dog data when coordinator unavailable."""
        mock_coordinator.available = False

        result = base_sensor._get_dog_data()

        assert result is None

    def test_base_sensor_get_module_data(self, base_sensor, mock_coordinator):
        """Test getting module data from coordinator."""
        mock_coordinator.get_module_data.return_value = {"feeding": "data"}

        result = base_sensor._get_module_data("feeding")

        mock_coordinator.get_module_data.assert_called_once_with("dog1", "feeding")
        assert result == {"feeding": "data"}

    def test_base_sensor_available_coordinator_available_with_dog_data(
        self, base_sensor, mock_coordinator
    ):
        """Test sensor availability when coordinator available and dog data exists."""
        mock_coordinator.available = True

        with patch.object(base_sensor, "_get_dog_data", return_value={"test": "data"}):
            assert base_sensor.available is True

    def test_base_sensor_available_coordinator_unavailable(
        self, base_sensor, mock_coordinator
    ):
        """Test sensor availability when coordinator unavailable."""
        mock_coordinator.available = False

        assert base_sensor.available is False

    def test_base_sensor_available_no_dog_data(self, base_sensor, mock_coordinator):
        """Test sensor availability when no dog data available."""
        mock_coordinator.available = True

        with patch.object(base_sensor, "_get_dog_data", return_value=None):
            assert base_sensor.available is False


class TestPawControlOnlineBinarySensor:
    """Test the online status binary sensor."""

    @pytest.fixture
    def online_sensor(self, mock_coordinator):
        """Create an online binary sensor for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlOnlineBinarySensor(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_online_sensor_initialization(self, online_sensor):
        """Test online sensor initialization."""
        assert online_sensor._sensor_type == "online"
        assert online_sensor._attr_device_class == BinarySensorDeviceClass.CONNECTIVITY
        assert online_sensor._icon_on == "mdi:check-network"
        assert online_sensor._icon_off == "mdi:close-network"

    def test_is_on_recent_update(self, online_sensor):
        """Test is_on when dog has recent update."""
        recent_time = (dt_util.utcnow() - timedelta(minutes=5)).isoformat()
        mock_dog_data = {"last_update": recent_time}

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert online_sensor.is_on is True

    def test_is_on_old_update(self, online_sensor):
        """Test is_on when dog has old update."""
        old_time = (dt_util.utcnow() - timedelta(minutes=15)).isoformat()
        mock_dog_data = {"last_update": old_time}

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert online_sensor.is_on is False

    def test_is_on_no_update_time(self, online_sensor):
        """Test is_on when no update time available."""
        mock_dog_data = {"last_update": None}

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert online_sensor.is_on is False

    def test_is_on_invalid_update_time(self, online_sensor):
        """Test is_on with invalid update time format."""
        mock_dog_data = {"last_update": "invalid-time-format"}

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert online_sensor.is_on is False

    def test_is_on_no_dog_data(self, online_sensor):
        """Test is_on when no dog data available."""
        with patch.object(online_sensor, "_get_dog_data", return_value=None):
            assert online_sensor.is_on is False

    def test_extra_state_attributes(self, online_sensor):
        """Test extra state attributes for online sensor."""
        mock_dog_data = {
            "last_update": "2023-01-01T12:00:00",
            "status": "healthy",
            "enabled_modules": ["feeding", "walk", "gps"],
        }

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            with patch.object(online_sensor, "is_on", True):
                attrs = online_sensor.extra_state_attributes

                assert attrs["last_update"] == "2023-01-01T12:00:00"
                assert attrs["status"] == "healthy"
                assert attrs["enabled_modules"] == ["feeding", "walk", "gps"]
                assert attrs["system_health"] == "healthy"

    def test_extra_state_attributes_offline(self, online_sensor):
        """Test extra state attributes when system is offline."""
        mock_dog_data = {"last_update": "2023-01-01T12:00:00", "status": "offline"}

        with patch.object(online_sensor, "_get_dog_data", return_value=mock_dog_data):
            with patch.object(online_sensor, "is_on", False):
                attrs = online_sensor.extra_state_attributes

                assert attrs["system_health"] == "disconnected"


class TestPawControlAttentionNeededBinarySensor:
    """Test the attention needed binary sensor."""

    @pytest.fixture
    def attention_sensor(self, mock_coordinator):
        """Create an attention needed binary sensor for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlAttentionNeededBinarySensor(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_attention_sensor_initialization(self, attention_sensor):
        """Test attention sensor initialization."""
        assert attention_sensor._sensor_type == "attention_needed"
        assert attention_sensor._attr_device_class == BinarySensorDeviceClass.PROBLEM
        assert attention_sensor._icon_on == "mdi:alert-circle"
        assert attention_sensor._icon_off == "mdi:check-circle"

    def test_is_on_critically_hungry(self, attention_sensor):
        """Test is_on when dog is critically hungry."""
        mock_dog_data = {
            "feeding": {"is_hungry": True, "last_feeding_hours": 15},
            "walk": {},
            "health": {},
            "gps": {},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is True
            assert "critically_hungry" in attention_sensor._attention_reasons

    def test_is_on_urgent_walk_needed(self, attention_sensor):
        """Test is_on when urgent walk is needed."""
        mock_dog_data = {
            "feeding": {},
            "walk": {"needs_walk": True, "last_walk_hours": 15},
            "health": {},
            "gps": {},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is True
            assert "urgent_walk_needed" in attention_sensor._attention_reasons

    def test_is_on_health_alert(self, attention_sensor):
        """Test is_on when health alert is present."""
        mock_dog_data = {
            "feeding": {},
            "walk": {},
            "health": {"health_alerts": ["high_temperature", "low_activity"]},
            "gps": {},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is True
            assert "health_alert" in attention_sensor._attention_reasons

    def test_is_on_outside_safe_zone(self, attention_sensor):
        """Test is_on when dog is outside safe zone."""
        mock_dog_data = {
            "feeding": {},
            "walk": {},
            "health": {},
            "gps": {"in_safe_zone": False},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is True
            assert "outside_safe_zone" in attention_sensor._attention_reasons

    def test_is_on_multiple_issues(self, attention_sensor):
        """Test is_on with multiple attention reasons."""
        mock_dog_data = {
            "feeding": {"is_hungry": True, "last_feeding_hours": 8},
            "walk": {"needs_walk": True, "last_walk_hours": 8},
            "health": {},
            "gps": {},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is True
            assert len(attention_sensor._attention_reasons) == 2

    def test_is_on_no_issues(self, attention_sensor):
        """Test is_on when no attention is needed."""
        mock_dog_data = {
            "feeding": {"is_hungry": False},
            "walk": {"needs_walk": False},
            "health": {"health_alerts": []},
            "gps": {"in_safe_zone": True},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            assert attention_sensor.is_on is False
            assert attention_sensor._attention_reasons == []

    def test_calculate_urgency_level_high(self, attention_sensor):
        """Test urgency level calculation for high urgency."""
        attention_sensor._attention_reasons = ["critically_hungry", "health_alert"]

        urgency = attention_sensor._calculate_urgency_level()

        assert urgency == "high"

    def test_calculate_urgency_level_medium(self, attention_sensor):
        """Test urgency level calculation for medium urgency."""
        attention_sensor._attention_reasons = [
            "hungry",
            "urgent_walk_needed",
            "outside_safe_zone",
        ]

        urgency = attention_sensor._calculate_urgency_level()

        assert urgency == "medium"

    def test_calculate_urgency_level_low(self, attention_sensor):
        """Test urgency level calculation for low urgency."""
        attention_sensor._attention_reasons = ["hungry"]

        urgency = attention_sensor._calculate_urgency_level()

        assert urgency == "low"

    def test_calculate_urgency_level_none(self, attention_sensor):
        """Test urgency level calculation for no urgency."""
        attention_sensor._attention_reasons = []

        urgency = attention_sensor._calculate_urgency_level()

        assert urgency == "none"

    def test_get_recommended_actions(self, attention_sensor):
        """Test recommended actions generation."""
        attention_sensor._attention_reasons = [
            "critically_hungry",
            "urgent_walk_needed",
            "health_alert",
        ]

        actions = attention_sensor._get_recommended_actions()

        assert "Feed immediately" in actions
        assert "Take for walk immediately" in actions
        assert "Check health status" in actions

    def test_extra_state_attributes_with_attention(self, attention_sensor):
        """Test extra state attributes when attention is needed."""
        mock_dog_data = {
            "feeding": {"is_hungry": True},
            "walk": {},
            "health": {},
            "gps": {},
        }

        with patch.object(
            attention_sensor, "_get_dog_data", return_value=mock_dog_data
        ):
            # Trigger is_on to set _attention_reasons
            _ = attention_sensor.is_on
            attrs = attention_sensor.extra_state_attributes

            assert "attention_reasons" in attrs
            assert "urgency_level" in attrs
            assert "recommended_actions" in attrs


class TestPawControlVisitorModeBinarySensor:
    """Test the visitor mode binary sensor."""

    @pytest.fixture
    def visitor_sensor(self, mock_coordinator):
        """Create a visitor mode binary sensor for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlVisitorModeBinarySensor(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_visitor_sensor_initialization(self, visitor_sensor):
        """Test visitor mode sensor initialization."""
        assert visitor_sensor._sensor_type == "visitor_mode"
        assert visitor_sensor._icon_on == "mdi:account-group"
        assert visitor_sensor._icon_off == "mdi:home"

    def test_is_on_visitor_mode_active(self, visitor_sensor):
        """Test is_on when visitor mode is active."""
        mock_dog_data = {"visitor_mode_active": True}

        with patch.object(visitor_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert visitor_sensor.is_on is True

    def test_is_on_visitor_mode_inactive(self, visitor_sensor):
        """Test is_on when visitor mode is inactive."""
        mock_dog_data = {"visitor_mode_active": False}

        with patch.object(visitor_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert visitor_sensor.is_on is False

    def test_is_on_no_visitor_mode_data(self, visitor_sensor):
        """Test is_on when no visitor mode data available."""
        mock_dog_data = {}

        with patch.object(visitor_sensor, "_get_dog_data", return_value=mock_dog_data):
            assert visitor_sensor.is_on is False

    def test_extra_state_attributes(self, visitor_sensor):
        """Test extra state attributes for visitor mode."""
        mock_dog_data = {
            "visitor_mode_started": "2023-01-01T10:00:00",
            "visitor_name": "Alice",
            "visitor_mode_settings": {
                "modified_notifications": True,
                "reduced_alerts": True,
            },
        }

        with patch.object(visitor_sensor, "_get_dog_data", return_value=mock_dog_data):
            attrs = visitor_sensor.extra_state_attributes

            assert attrs["visitor_mode_started"] == "2023-01-01T10:00:00"
            assert attrs["visitor_name"] == "Alice"
            assert attrs["modified_notifications"] is True
            assert attrs["reduced_alerts"] is True


# Feeding Binary Sensors Tests
class TestPawControlIsHungryBinarySensor:
    """Test the is hungry binary sensor."""

    @pytest.fixture
    def hungry_sensor(self, mock_coordinator):
        """Create an is hungry binary sensor for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_module_data = Mock()
        return PawControlIsHungryBinarySensor(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_hungry_sensor_initialization(self, hungry_sensor):
        """Test hungry sensor initialization."""
        assert hungry_sensor._sensor_type == "is_hungry"
        assert hungry_sensor._icon_on == "mdi:food-drumstick-off"
        assert hungry_sensor._icon_off == "mdi:food-drumstick"

    def test_is_on_hungry(self, hungry_sensor):
        """Test is_on when dog is hungry."""
        mock_feeding_data = {"is_hungry": True}

        with patch.object(
            hungry_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert hungry_sensor.is_on is True

    def test_is_on_not_hungry(self, hungry_sensor):
        """Test is_on when dog is not hungry."""
        mock_feeding_data = {"is_hungry": False}

        with patch.object(
            hungry_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert hungry_sensor.is_on is False

    def test_is_on_no_feeding_data(self, hungry_sensor):
        """Test is_on when no feeding data available."""
        with patch.object(hungry_sensor, "_get_module_data", return_value=None):
            assert hungry_sensor.is_on is False

    def test_calculate_hunger_level_very_hungry(self, hungry_sensor):
        """Test hunger level calculation for very hungry state."""
        feeding_data = {"last_feeding_hours": 15}

        hunger_level = hungry_sensor._calculate_hunger_level(feeding_data)

        assert hunger_level == "very_hungry"

    def test_calculate_hunger_level_hungry(self, hungry_sensor):
        """Test hunger level calculation for hungry state."""
        feeding_data = {"last_feeding_hours": 10}

        hunger_level = hungry_sensor._calculate_hunger_level(feeding_data)

        assert hunger_level == "hungry"

    def test_calculate_hunger_level_somewhat_hungry(self, hungry_sensor):
        """Test hunger level calculation for somewhat hungry state."""
        feeding_data = {"last_feeding_hours": 7}

        hunger_level = hungry_sensor._calculate_hunger_level(feeding_data)

        assert hunger_level == "somewhat_hungry"

    def test_calculate_hunger_level_satisfied(self, hungry_sensor):
        """Test hunger level calculation for satisfied state."""
        feeding_data = {"last_feeding_hours": 3}

        hunger_level = hungry_sensor._calculate_hunger_level(feeding_data)

        assert hunger_level == "satisfied"

    def test_calculate_hunger_level_no_data(self, hungry_sensor):
        """Test hunger level calculation with no data."""
        feeding_data = {}

        hunger_level = hungry_sensor._calculate_hunger_level(feeding_data)

        assert hunger_level == STATE_UNKNOWN

    def test_extra_state_attributes(self, hungry_sensor):
        """Test extra state attributes for hungry sensor."""
        mock_feeding_data = {
            "last_feeding": "2023-01-01T08:00:00",
            "last_feeding_hours": 8,
            "next_feeding_due": "2023-01-01T18:00:00",
        }

        with patch.object(
            hungry_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            attrs = hungry_sensor.extra_state_attributes

            assert attrs["last_feeding"] == "2023-01-01T08:00:00"
            assert attrs["last_feeding_hours"] == 8
            assert attrs["next_feeding_due"] == "2023-01-01T18:00:00"
            assert attrs["hunger_level"] == "hungry"


class TestPawControlFeedingDueBinarySensor:
    """Test the feeding due binary sensor."""

    @pytest.fixture
    def feeding_due_sensor(self, mock_coordinator):
        """Create a feeding due binary sensor for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlFeedingDueBinarySensor(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_feeding_due_sensor_initialization(self, feeding_due_sensor):
        """Test feeding due sensor initialization."""
        assert feeding_due_sensor._sensor_type == "feeding_due"
        assert feeding_due_sensor._icon_on == "mdi:clock-alert"
        assert feeding_due_sensor._icon_off == "mdi:clock-check"

    def test_is_on_feeding_due(self, feeding_due_sensor):
        """Test is_on when feeding is due."""
        past_time = (dt_util.utcnow() - timedelta(minutes=30)).isoformat()
        mock_feeding_data = {"next_feeding_due": past_time}

        with patch.object(
            feeding_due_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert feeding_due_sensor.is_on is True

    def test_is_on_feeding_not_due(self, feeding_due_sensor):
        """Test is_on when feeding is not yet due."""
        future_time = (dt_util.utcnow() + timedelta(minutes=30)).isoformat()
        mock_feeding_data = {"next_feeding_due": future_time}

        with patch.object(
            feeding_due_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert feeding_due_sensor.is_on is False

    def test_is_on_no_due_time(self, feeding_due_sensor):
        """Test is_on when no due time available."""
        mock_feeding_data = {"next_feeding_due": None}

        with patch.object(
            feeding_due_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert feeding_due_sensor.is_on is False

    def test_is_on_invalid_due_time(self, feeding_due_sensor):
        """Test is_on with invalid due time format."""
        mock_feeding_data = {"next_feeding_due": "invalid-time"}

        with patch.object(
            feeding_due_sensor, "_get_module_data", return_value=mock_feeding_data
        ):
            assert feeding_due_sensor.is_on is False


# Integration scenarios and edge cases
class TestBinarySensorIntegrationScenarios:
    """Test binary sensor integration scenarios and edge cases."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_coordinator_unavailable_affects_all_sensors(self, mock_coordinator):
        """Test that coordinator unavailability affects all sensors."""
        mock_coordinator.available = False

        sensors = [
            PawControlOnlineBinarySensor(mock_coordinator, "dog1", "Buddy"),
            PawControlIsHungryBinarySensor(mock_coordinator, "dog1", "Buddy"),
            PawControlWalkInProgressBinarySensor(mock_coordinator, "dog1", "Buddy"),
            PawControlIsHomeBinarySensor(mock_coordinator, "dog1", "Buddy"),
            PawControlHealthAlertBinarySensor(mock_coordinator, "dog1", "Buddy"),
        ]

        for sensor in sensors:
            assert sensor.available is False

    def test_multiple_dogs_unique_entities(self, mock_coordinator):
        """Test that multiple dogs create unique entities."""
        dogs = [("dog1", "Buddy"), ("dog2", "Max"), ("dog3", "Luna")]

        sensors = []
        for dog_id, dog_name in dogs:
            sensors.append(
                PawControlOnlineBinarySensor(mock_coordinator, dog_id, dog_name)
            )
            sensors.append(
                PawControlIsHungryBinarySensor(mock_coordinator, dog_id, dog_name)
            )

        unique_ids = [sensor._attr_unique_id for sensor in sensors]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

        # Verify format
        assert "pawcontrol_dog1_online" in unique_ids
        assert "pawcontrol_dog2_online" in unique_ids
        assert "pawcontrol_dog3_online" in unique_ids

    def test_sensor_state_consistency_across_modules(self, mock_coordinator):
        """Test state consistency across related sensors."""
        # Setup walk in progress scenario
        mock_coordinator.get_module_data.side_effect = lambda dog_id, module: {
            "walk": {"walk_in_progress": True, "needs_walk": False},
            "gps": {"speed": 5.0, "zone": "park"},
        }.get(module, {})

        walk_progress_sensor = PawControlWalkInProgressBinarySensor(
            mock_coordinator, "dog1", "Buddy"
        )
        needs_walk_sensor = PawControlNeedsWalkBinarySensor(
            mock_coordinator, "dog1", "Buddy"
        )
        moving_sensor = PawControlMovingBinarySensor(mock_coordinator, "dog1", "Buddy")
        is_home_sensor = PawControlIsHomeBinarySensor(mock_coordinator, "dog1", "Buddy")

        # Walk in progress should be True
        assert walk_progress_sensor.is_on is True
        # Needs walk should be False (already walking)
        assert needs_walk_sensor.is_on is False
        # Moving should be True (speed > 1)
        assert moving_sensor.is_on is True
        # Not at home (in park)
        assert is_home_sensor.is_on is False

    def test_error_handling_malformed_data(self, mock_coordinator):
        """Test error handling with malformed data."""
        # Mock malformed data that could cause exceptions
        mock_coordinator.get_module_data.return_value = {
            "invalid_key": "invalid_value",
            "nested": {"malformed": None},
        }

        sensor = PawControlIsHungryBinarySensor(mock_coordinator, "dog1", "Buddy")

        # Should not raise exception and return False for missing data
        try:
            result = sensor.is_on
            assert result is False
        except Exception as e:
            pytest.fail(
                f"Sensor should handle malformed data gracefully, but raised: {e}"
            )

    @pytest.mark.asyncio
    async def test_performance_with_many_sensors(self, mock_coordinator):
        """Test performance with large number of sensors."""
        # Simulate 10 dogs with all modules enabled (230 binary sensors total)
        import time

        start_time = time.time()

        sensors = []
        for dog_num in range(10):
            dog_id = f"dog{dog_num}"
            dog_name = f"Dog{dog_num}"

            # Create all sensor types for this dog
            sensors.extend(
                [
                    # Base sensors (3)
                    PawControlOnlineBinarySensor(mock_coordinator, dog_id, dog_name),
                    PawControlAttentionNeededBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlVisitorModeBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    # Feeding sensors (4)
                    PawControlIsHungryBinarySensor(mock_coordinator, dog_id, dog_name),
                    PawControlFeedingDueBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlFeedingScheduleOnTrackBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlDailyFeedingGoalMetBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    # Walk sensors (4)
                    PawControlWalkInProgressBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlNeedsWalkBinarySensor(mock_coordinator, dog_id, dog_name),
                    PawControlWalkGoalMetBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlLongWalkOverdueBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    # GPS sensors (6)
                    PawControlIsHomeBinarySensor(mock_coordinator, dog_id, dog_name),
                    PawControlInSafeZoneBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlGPSAccuratelyTrackedBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlMovingBinarySensor(mock_coordinator, dog_id, dog_name),
                    PawControlGeofenceAlertBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlGPSBatteryLowBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    # Health sensors (6)
                    PawControlHealthAlertBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlWeightAlertBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlMedicationDueBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlVetCheckupDueBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlGroomingDueBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlActivityLevelConcernBinarySensor(
                        mock_coordinator, dog_id, dog_name
                    ),
                ]
            )

        creation_time = time.time() - start_time

        # Should create 230 sensors quickly (under 1 second)
        assert len(sensors) == 230
        assert creation_time < 1.0

        # Test that all sensors have unique IDs
        unique_ids = [sensor._attr_unique_id for sensor in sensors]
        assert len(unique_ids) == len(set(unique_ids))

    def test_sensor_attributes_isolation(self, mock_coordinator):
        """Test that sensor attributes don't interfere with each other."""
        # Create multiple sensors of same type for different dogs
        sensor1 = PawControlIsHungryBinarySensor(mock_coordinator, "dog1", "Buddy")
        sensor2 = PawControlIsHungryBinarySensor(mock_coordinator, "dog2", "Max")

        # Mock different data for each dog
        def mock_get_module_data(dog_id, module):
            if dog_id == "dog1":
                return {"is_hungry": True, "last_feeding_hours": 8}
            elif dog_id == "dog2":
                return {"is_hungry": False, "last_feeding_hours": 2}
            return {}

        mock_coordinator.get_module_data.side_effect = mock_get_module_data

        # Sensors should return different states
        assert sensor1.is_on is True
        assert sensor2.is_on is False

        # Attributes should be isolated
        attrs1 = sensor1.extra_state_attributes
        attrs2 = sensor2.extra_state_attributes

        assert attrs1[ATTR_DOG_ID] == "dog1"
        assert attrs2[ATTR_DOG_ID] == "dog2"
        assert attrs1["hunger_level"] == "hungry"
        assert attrs2["hunger_level"] == "satisfied"
