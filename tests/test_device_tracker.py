"""Tests for device tracker platform of Paw Control integration.

This module provides comprehensive test coverage for GPS device tracker entities
including location tracking, zone detection, battery monitoring, movement analysis,
and all edge cases to meet Home Assistant's Platinum quality standards.

Test Coverage:
- GPS location tracking and accuracy
- Zone detection and transitions
- Battery monitoring and status
- Movement analysis and speed detection
- Location history and distance calculations
- State restoration and persistence
- Batching functionality for entity registration
- Event firing for zone changes
- Walk integration and status
- Manual location updates
- Error handling and edge cases
- Performance testing with large setups
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_GPS,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.device_tracker import (
    DEFAULT_GPS_ACCURACY,
    HOME_ZONE_RADIUS,
    LOCATION_UPDATE_THRESHOLD,
    MAX_GPS_AGE,
    PawControlDeviceTracker,
    _async_add_entities_in_batches,
    async_setup_entry,
)
from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_HOME,
    STATE_NOT_HOME,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreStateData
from homeassistant.util import dt as dt_util


class TestAsyncAddEntitiesInBatches:
    """Test the batching functionality for device tracker entity registration."""

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_single_batch(self):
        """Test batching with entities that fit in a single batch."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(5)]

        await _async_add_entities_in_batches(mock_add_entities, entities, batch_size=8)

        # Should be called once with all entities
        mock_add_entities.assert_called_once_with(entities, update_before_add=False)

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_multiple_batches(self):
        """Test batching with entities that require multiple batches."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(20)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=8, delay_between_batches=0.05
            )

        # Should be called 3 times (8 + 8 + 4)
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
    async def test_async_add_entities_in_batches_custom_parameters(self):
        """Test batching with custom batch size and delay."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(15)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=6, delay_between_batches=0.2
            )

        # Should be called 3 times (6 + 6 + 3)
        assert mock_add_entities.call_count == 3

        # Check custom delay was used
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.2)

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_performance_large_setup(self):
        """Test batching performance with large GPS tracker setup."""
        mock_add_entities = Mock()
        # Simulate 40 GPS tracker entities (4 per dog * 10 dogs)
        entities = [Mock() for _ in range(40)]

        start_time = asyncio.get_event_loop().time()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=8
            )

        end_time = asyncio.get_event_loop().time()

        # Should complete quickly even with large entity count
        assert end_time - start_time < 1.0

        # Should be called 5 times (40 / 8 = 5 batches)
        assert mock_add_entities.call_count == 5


class TestAsyncSetupEntry:
    """Test the async setup entry function for device tracker platform."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def mock_config_entry_with_gps(self, mock_coordinator):
        """Create a mock config entry with GPS-enabled dogs."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {
                        MODULE_GPS: True,
                    },
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Max",
                    "modules": {
                        MODULE_GPS: True,
                    },
                },
                {
                    CONF_DOG_ID: "dog3",
                    CONF_DOG_NAME: "Luna",
                    "modules": {
                        MODULE_GPS: False,  # GPS disabled
                    },
                },
            ]
        }
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": entry.data[CONF_DOGS],
        }
        return entry

    @pytest.fixture
    def mock_config_entry_no_gps(self, mock_coordinator):
        """Create a mock config entry with no GPS-enabled dogs."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {},  # No GPS module
                }
            ]
        }
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": entry.data[CONF_DOGS],
        }
        return entry

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_gps_dogs(
        self, hass: HomeAssistant, mock_config_entry_with_gps, mock_coordinator
    ):
        """Test setup entry with GPS-enabled dogs."""
        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.device_tracker._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, mock_config_entry_with_gps, mock_add_entities)

        # Should call batching function
        mock_batch_add.assert_called_once()

        # Get the entities that were passed to batching
        args, kwargs = mock_batch_add.call_args
        entities = args[1]  # Second argument is the entities list

        # Only 2 dogs have GPS enabled, so should create 2 entities
        assert len(entities) == 2

        # Verify entity types
        for entity in entities:
            assert isinstance(entity, PawControlDeviceTracker)

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_gps_dogs(
        self, hass: HomeAssistant, mock_config_entry_no_gps, mock_coordinator
    ):
        """Test setup entry with no GPS-enabled dogs."""
        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.device_tracker._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, mock_config_entry_no_gps, mock_add_entities)

        # Should not call batching function since no entities created
        mock_batch_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_setup_entry_legacy_data_structure(
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
                    "modules": {MODULE_GPS: True},
                }
            ]
        }
        entry.runtime_data = None

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.device_tracker._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        mock_batch_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_empty_dogs_list(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with empty dogs list."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {"coordinator": mock_coordinator, "dogs": []}

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.device_tracker._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should not call batching function with empty dogs list
        mock_batch_add.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_coordinator_data(
        self, hass: HomeAssistant
    ):
        """Test setup entry when coordinator data is missing."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.runtime_data = None

        # No coordinator in hass.data
        hass.data[DOMAIN] = {}

        mock_add_entities = Mock()

        with pytest.raises(KeyError):
            await async_setup_entry(hass, entry, mock_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_required_dog_keys(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with dogs missing required keys."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    # Missing CONF_DOG_ID and CONF_DOG_NAME
                    "modules": {MODULE_GPS: True}
                }
            ],
        }

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.device_tracker._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should not call batching function due to missing keys
        mock_batch_add.assert_not_called()


class TestPawControlDeviceTracker:
    """Test the main device tracker entity functionality."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        coordinator.get_module_data = Mock()
        return coordinator

    @pytest.fixture
    def device_tracker(self, mock_coordinator):
        """Create a device tracker entity for testing."""
        return PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_gps_data(self):
        """Create mock GPS data."""
        return {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "accuracy": 5.0,
            "battery_level": 85,
            "last_seen": "2023-06-15T12:30:00",
            "source": "gps_collar",
            "heading": 90.0,
            "speed": 2.5,
            "altitude": 50.0,
            "distance_from_home": 1500,
        }

    def test_device_tracker_initialization(self, device_tracker):
        """Test device tracker initialization."""
        assert device_tracker._dog_id == "dog1"
        assert device_tracker._dog_name == "Buddy"
        assert device_tracker._attr_unique_id == "pawcontrol_dog1_gps"
        assert device_tracker._attr_name == "Buddy GPS"
        assert device_tracker._attr_icon == "mdi:dog"

    def test_device_tracker_device_info(self, device_tracker):
        """Test device info configuration."""
        device_info = device_tracker._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "dog1")}
        assert device_info["name"] == "Buddy"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog GPS Tracker"
        assert device_info["sw_version"] == "1.0.0"
        assert "configuration_url" in device_info

    def test_source_type(self, device_tracker):
        """Test source type property."""
        assert device_tracker.source_type == SourceType.GPS

    def test_latitude_from_gps_data(
        self, device_tracker, mock_coordinator, mock_gps_data
    ):
        """Test latitude property from GPS data."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.latitude == 37.7749

    def test_latitude_from_restored_data(self, device_tracker, mock_coordinator):
        """Test latitude property from restored data when no GPS data."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {"latitude": 37.7749}

        assert device_tracker.latitude == 37.7749

    def test_latitude_none_when_no_data(self, device_tracker, mock_coordinator):
        """Test latitude property returns None when no data available."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.latitude is None

    def test_longitude_from_gps_data(
        self, device_tracker, mock_coordinator, mock_gps_data
    ):
        """Test longitude property from GPS data."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.longitude == -122.4194

    def test_longitude_from_restored_data(self, device_tracker, mock_coordinator):
        """Test longitude property from restored data when no GPS data."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {"longitude": -122.4194}

        assert device_tracker.longitude == -122.4194

    def test_longitude_none_when_no_data(self, device_tracker, mock_coordinator):
        """Test longitude property returns None when no data available."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.longitude is None

    def test_location_accuracy_from_gps_data(
        self, device_tracker, mock_coordinator, mock_gps_data
    ):
        """Test location accuracy from GPS data."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.location_accuracy == 5

    def test_location_accuracy_from_restored_data(
        self, device_tracker, mock_coordinator
    ):
        """Test location accuracy from restored data."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {"gps_accuracy": 10}

        assert device_tracker.location_accuracy == 10

    def test_location_accuracy_default(self, device_tracker, mock_coordinator):
        """Test location accuracy returns default when no data available."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.location_accuracy == DEFAULT_GPS_ACCURACY

    def test_battery_level_from_gps_data(
        self, device_tracker, mock_coordinator, mock_gps_data
    ):
        """Test battery level from GPS data."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.battery_level == 85

    def test_battery_level_from_restored_data(self, device_tracker, mock_coordinator):
        """Test battery level from restored data."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {"battery_level": 65}

        assert device_tracker.battery_level == 65

    def test_battery_level_none_when_no_data(self, device_tracker, mock_coordinator):
        """Test battery level returns None when no data available."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.battery_level is None

    def test_location_name_home(
        self, device_tracker, mock_coordinator, mock_gps_data, hass: HomeAssistant
    ):
        """Test location name when dog is at home."""
        device_tracker.hass = hass
        hass.config.latitude = 37.7749
        hass.config.longitude = -122.4194

        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.location_name == STATE_HOME

    def test_location_name_not_home(
        self, device_tracker, mock_coordinator, mock_gps_data, hass: HomeAssistant
    ):
        """Test location name when dog is not at home."""
        device_tracker.hass = hass
        hass.config.latitude = 40.7128  # Far from dog location
        hass.config.longitude = -74.0060

        # Mock zone entities as empty
        with patch.object(hass.states, "async_all", return_value=[]):
            mock_coordinator.get_module_data.return_value = mock_gps_data
            device_tracker.coordinator = mock_coordinator

            assert device_tracker.location_name == STATE_NOT_HOME

    def test_location_name_no_coordinates(self, device_tracker, mock_coordinator):
        """Test location name when no coordinates available."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.location_name is None

    def test_determine_zone_from_coordinates_in_zone(
        self, device_tracker, hass: HomeAssistant
    ):
        """Test zone determination when dog is in a configured zone."""
        device_tracker.hass = hass

        # Mock zone state
        mock_zone_state = Mock()
        mock_zone_state.attributes = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "radius": 100,
            "friendly_name": "Dog Park",
        }
        mock_zone_state.entity_id = "zone.dog_park"

        with patch.object(hass.states, "async_all", return_value=[mock_zone_state]):
            zone_name = device_tracker._determine_zone_from_coordinates(
                37.7749, -122.4194
            )
            assert zone_name == "Dog Park"

    def test_determine_zone_from_coordinates_not_in_zone(
        self, device_tracker, hass: HomeAssistant
    ):
        """Test zone determination when dog is not in any zone."""
        device_tracker.hass = hass

        # Mock zone state far away
        mock_zone_state = Mock()
        mock_zone_state.attributes = {
            "latitude": 40.7128,  # Far from test coordinates
            "longitude": -74.0060,
            "radius": 100,
            "friendly_name": "Dog Park",
        }
        mock_zone_state.entity_id = "zone.dog_park"

        with patch.object(hass.states, "async_all", return_value=[mock_zone_state]):
            zone_name = device_tracker._determine_zone_from_coordinates(
                37.7749, -122.4194
            )
            assert zone_name is None

    def test_determine_zone_from_coordinates_missing_attributes(
        self, device_tracker, hass: HomeAssistant
    ):
        """Test zone determination with missing zone attributes."""
        device_tracker.hass = hass

        # Mock zone state with missing attributes
        mock_zone_state = Mock()
        mock_zone_state.attributes = {"friendly_name": "Dog Park"}  # Missing lat/lon
        mock_zone_state.entity_id = "zone.dog_park"

        with patch.object(hass.states, "async_all", return_value=[mock_zone_state]):
            zone_name = device_tracker._determine_zone_from_coordinates(
                37.7749, -122.4194
            )
            assert zone_name is None

    def test_extra_state_attributes_with_gps_data(
        self, device_tracker, mock_coordinator, mock_gps_data
    ):
        """Test extra state attributes with GPS data."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        attrs = device_tracker.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "dog1"
        assert attrs[ATTR_DOG_NAME] == "Buddy"
        assert attrs["tracker_type"] == "gps"
        assert attrs[ATTR_GPS_ACCURACY] == 5
        assert attrs["last_seen"] == "2023-06-15T12:30:00"
        assert attrs["source"] == "gps_collar"
        assert attrs["heading"] == 90.0
        assert attrs["speed"] == 2.5
        assert attrs["altitude"] == 50.0
        assert attrs[ATTR_BATTERY_LEVEL] == 85
        assert attrs["distance_from_home"] == 1500

    def test_extra_state_attributes_without_gps_data(
        self, device_tracker, mock_coordinator
    ):
        """Test extra state attributes without GPS data."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator

        attrs = device_tracker.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "dog1"
        assert attrs[ATTR_DOG_NAME] == "Buddy"
        assert attrs["tracker_type"] == "gps"
        # GPS-specific attributes should not be present
        assert ATTR_GPS_ACCURACY not in attrs
        assert "last_seen" not in attrs

    def test_get_battery_status_variations(self, device_tracker):
        """Test battery status descriptions for different levels."""
        # Test critical battery
        device_tracker._current_battery_level = 3
        assert device_tracker._get_battery_status() == "critical"

        # Test low battery
        device_tracker._current_battery_level = 10
        assert device_tracker._get_battery_status() == "low"

        # Test medium battery
        device_tracker._current_battery_level = 25
        assert device_tracker._get_battery_status() == "medium"

        # Test good battery
        device_tracker._current_battery_level = 80
        assert device_tracker._get_battery_status() == "good"

    def test_get_battery_status_none(self, device_tracker):
        """Test battery status when battery level is None."""
        with patch.object(device_tracker, "battery_level", None):
            assert device_tracker._get_battery_status() == "unknown"

    def test_is_currently_moving_with_speed(self, device_tracker, mock_gps_data):
        """Test movement detection using speed data."""
        # Test moving
        mock_gps_data["speed"] = 5.0
        assert device_tracker._is_currently_moving(mock_gps_data) is True

        # Test stationary
        mock_gps_data["speed"] = 0.5
        assert device_tracker._is_currently_moving(mock_gps_data) is False

    def test_is_currently_moving_with_location_change(
        self, device_tracker, mock_gps_data
    ):
        """Test movement detection using location change."""
        # Set up previous location
        device_tracker._last_known_location = (37.7749, -122.4194)

        # Test significant location change (moving)
        mock_gps_data["speed"] = None  # No speed data
        mock_gps_data["latitude"] = 37.7750  # Small change in latitude
        mock_gps_data["longitude"] = -122.4194

        # Mock the distance calculation to return a value above threshold
        with patch(
            "custom_components.pawcontrol.device_tracker.distance", return_value=0.015
        ):  # 15 meters
            assert device_tracker._is_currently_moving(mock_gps_data) is True

    def test_is_currently_moving_no_previous_location(
        self, device_tracker, mock_gps_data
    ):
        """Test movement detection without previous location."""
        device_tracker._last_known_location = None
        mock_gps_data["speed"] = None

        assert device_tracker._is_currently_moving(mock_gps_data) is False

    def test_get_movement_status_variations(self, device_tracker, mock_gps_data):
        """Test movement status descriptions."""
        # Test running
        mock_gps_data["speed"] = 15.0
        with patch.object(device_tracker, "_is_currently_moving", return_value=True):
            assert device_tracker._get_movement_status(mock_gps_data) == "running"

        # Test walking
        mock_gps_data["speed"] = 5.0
        with patch.object(device_tracker, "_is_currently_moving", return_value=True):
            assert device_tracker._get_movement_status(mock_gps_data) == "walking"

        # Test moving slowly
        mock_gps_data["speed"] = 2.0
        with patch.object(device_tracker, "_is_currently_moving", return_value=True):
            assert device_tracker._get_movement_status(mock_gps_data) == "moving_slowly"

        # Test stationary
        with patch.object(device_tracker, "_is_currently_moving", return_value=False):
            assert device_tracker._get_movement_status(mock_gps_data) == "stationary"

    def test_assess_gps_signal_quality_variations(self, device_tracker):
        """Test GPS signal quality assessment."""
        # Test excellent signal
        assert device_tracker._assess_gps_signal_quality({"accuracy": 3}) == "excellent"

        # Test good signal
        assert device_tracker._assess_gps_signal_quality({"accuracy": 10}) == "good"

        # Test fair signal
        assert device_tracker._assess_gps_signal_quality({"accuracy": 30}) == "fair"

        # Test poor signal
        assert device_tracker._assess_gps_signal_quality({"accuracy": 100}) == "poor"

        # Test unknown signal
        assert (
            device_tracker._assess_gps_signal_quality({"accuracy": None}) == "unknown"
        )

    def test_assess_data_freshness_variations(self, device_tracker):
        """Test data freshness assessment."""
        now = dt_util.utcnow()

        # Test current data
        current_time = now.isoformat()
        assert (
            device_tracker._assess_data_freshness({"last_seen": current_time})
            == "current"
        )

        # Test recent data
        recent_time = (now - timedelta(minutes=3)).isoformat()
        assert (
            device_tracker._assess_data_freshness({"last_seen": recent_time})
            == "recent"
        )

        # Test stale data
        stale_time = (now - timedelta(minutes=10)).isoformat()
        assert (
            device_tracker._assess_data_freshness({"last_seen": stale_time}) == "stale"
        )

        # Test old data
        old_time = (now - timedelta(minutes=30)).isoformat()
        assert device_tracker._assess_data_freshness({"last_seen": old_time}) == "old"

        # Test missing data
        assert device_tracker._assess_data_freshness({"last_seen": None}) == "unknown"

        # Test invalid date format
        assert (
            device_tracker._assess_data_freshness({"last_seen": "invalid-date"})
            == "unknown"
        )

    def test_get_tracking_status_variations(self, device_tracker):
        """Test tracking status assessment."""
        # Test no location
        with patch.object(
            device_tracker, "_assess_gps_signal_quality", return_value="good"
        ):
            with patch.object(
                device_tracker, "_assess_data_freshness", return_value="current"
            ):
                with patch.object(
                    device_tracker, "_get_battery_status", return_value="good"
                ):
                    status = device_tracker._get_tracking_status(
                        {"latitude": None, "longitude": None}
                    )
                    assert status == "no_location"

        # Test active tracking
        with patch.object(
            device_tracker, "_assess_gps_signal_quality", return_value="excellent"
        ):
            with patch.object(
                device_tracker, "_assess_data_freshness", return_value="current"
            ):
                with patch.object(
                    device_tracker, "_get_battery_status", return_value="good"
                ):
                    status = device_tracker._get_tracking_status(
                        {"latitude": 37.7749, "longitude": -122.4194}
                    )
                    assert status == "tracking_active"

        # Test tracking with low battery
        with patch.object(
            device_tracker, "_assess_gps_signal_quality", return_value="good"
        ):
            with patch.object(
                device_tracker, "_assess_data_freshness", return_value="current"
            ):
                with patch.object(
                    device_tracker, "_get_battery_status", return_value="low"
                ):
                    status = device_tracker._get_tracking_status(
                        {"latitude": 37.7749, "longitude": -122.4194}
                    )
                    assert status == "tracking_battery_low"

        # Test tracking with critical battery
        with patch.object(
            device_tracker, "_assess_gps_signal_quality", return_value="good"
        ):
            with patch.object(
                device_tracker, "_assess_data_freshness", return_value="current"
            ):
                with patch.object(
                    device_tracker, "_get_battery_status", return_value="critical"
                ):
                    status = device_tracker._get_tracking_status(
                        {"latitude": 37.7749, "longitude": -122.4194}
                    )
                    assert status == "tracking_battery_critical"

        # Test degraded tracking
        with patch.object(
            device_tracker, "_assess_gps_signal_quality", return_value="poor"
        ):
            with patch.object(
                device_tracker, "_assess_data_freshness", return_value="stale"
            ):
                with patch.object(
                    device_tracker, "_get_battery_status", return_value="good"
                ):
                    status = device_tracker._get_tracking_status(
                        {"latitude": 37.7749, "longitude": -122.4194}
                    )
                    assert status == "tracking_degraded"

    def test_available_with_recent_gps_data(self, device_tracker, mock_coordinator):
        """Test availability with recent GPS data."""
        mock_coordinator.available = True
        recent_time = dt_util.utcnow().isoformat()
        mock_coordinator.get_module_data.return_value = {"last_seen": recent_time}
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.available is True

    def test_available_with_old_gps_data(self, device_tracker, mock_coordinator):
        """Test availability with old GPS data."""
        mock_coordinator.available = True
        old_time = (dt_util.utcnow() - timedelta(hours=1)).isoformat()
        mock_coordinator.get_module_data.return_value = {"last_seen": old_time}
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.available is False

    def test_available_with_coordinates_fallback(
        self, device_tracker, mock_coordinator
    ):
        """Test availability fallback to coordinates."""
        mock_coordinator.available = True
        mock_coordinator.get_module_data.return_value = None  # No GPS data
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {"latitude": 37.7749, "longitude": -122.4194}

        assert device_tracker.available is True

    def test_available_coordinator_unavailable(self, device_tracker, mock_coordinator):
        """Test availability when coordinator is unavailable."""
        mock_coordinator.available = False
        device_tracker.coordinator = mock_coordinator

        assert device_tracker.available is False

    def test_available_invalid_last_seen_format(self, device_tracker, mock_coordinator):
        """Test availability with invalid last_seen format."""
        mock_coordinator.available = True
        mock_coordinator.get_module_data.return_value = {"last_seen": "invalid-date"}
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        assert device_tracker.available is False

    @pytest.mark.asyncio
    async def test_async_added_to_hass_without_previous_state(
        self, hass: HomeAssistant, device_tracker
    ):
        """Test entity added to hass without previous state."""
        device_tracker.hass = hass
        device_tracker.entity_id = "device_tracker.buddy_gps"

        with patch.object(device_tracker, "async_get_last_state", return_value=None):
            await device_tracker.async_added_to_hass()

        assert device_tracker._restored_data == {}

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_previous_state(
        self, hass: HomeAssistant, device_tracker
    ):
        """Test entity added to hass with previous state."""
        device_tracker.hass = hass
        device_tracker.entity_id = "device_tracker.buddy_gps"

        mock_state = Mock()
        mock_state.attributes = {
            ATTR_LATITUDE: 37.7749,
            ATTR_LONGITUDE: -122.4194,
            ATTR_GPS_ACCURACY: 10,
            ATTR_BATTERY_LEVEL: 75,
            "source_type": "gps",
            "last_seen": "2023-06-15T12:30:00",
        }

        with patch.object(
            device_tracker, "async_get_last_state", return_value=mock_state
        ):
            await device_tracker.async_added_to_hass()

        expected_data = {
            "latitude": 37.7749,
            "longitude": -122.4194,
            "gps_accuracy": 10,
            "battery_level": 75,
            "source_type": "gps",
            "last_seen": "2023-06-15T12:30:00",
        }

        assert device_tracker._restored_data == expected_data
        assert device_tracker._last_known_location == (37.7749, -122.4194)

    def test_handle_coordinator_update_with_location_change(
        self, device_tracker, mock_coordinator, hass: HomeAssistant
    ):
        """Test coordinator update with significant location change."""
        device_tracker.hass = hass
        device_tracker.coordinator = mock_coordinator
        device_tracker._last_known_location = (37.7749, -122.4194)

        new_gps_data = {
            "latitude": 37.7750,  # Slight change
            "longitude": -122.4195,
            "accuracy": 5,
            "speed": 2.0,
        }

        mock_coordinator.get_module_data.return_value = new_gps_data

        with patch(
            "custom_components.pawcontrol.device_tracker.distance", return_value=0.015
        ):  # 15 meters
            with patch.object(
                device_tracker, "_update_location_history"
            ) as mock_update_history:
                device_tracker._handle_coordinator_update()

        # Should update location history due to significant change
        mock_update_history.assert_called_once()

    def test_handle_coordinator_update_insignificant_change(
        self, device_tracker, mock_coordinator, hass: HomeAssistant
    ):
        """Test coordinator update with insignificant location change."""
        device_tracker.hass = hass
        device_tracker.coordinator = mock_coordinator
        device_tracker._last_known_location = (37.7749, -122.4194)

        new_gps_data = {
            "latitude": 37.7749,  # Same location
            "longitude": -122.4194,
            "accuracy": 5,
            "speed": 0.0,
        }

        mock_coordinator.get_module_data.return_value = new_gps_data

        with patch(
            "custom_components.pawcontrol.device_tracker.distance", return_value=0.005
        ):  # 5 meters
            with patch.object(
                device_tracker, "_update_location_history"
            ) as mock_update_history:
                device_tracker._handle_coordinator_update()

        # Should not update location history due to insignificant change
        mock_update_history.assert_not_called()

    def test_handle_coordinator_update_first_location(
        self, device_tracker, mock_coordinator, hass: HomeAssistant
    ):
        """Test coordinator update with first location."""
        device_tracker.hass = hass
        device_tracker.coordinator = mock_coordinator
        device_tracker._last_known_location = None  # No previous location

        new_gps_data = {"latitude": 37.7749, "longitude": -122.4194, "accuracy": 5}

        mock_coordinator.get_module_data.return_value = new_gps_data

        with patch.object(
            device_tracker, "_update_location_history"
        ) as mock_update_history:
            device_tracker._handle_coordinator_update()

        # Should update location history for first location
        mock_update_history.assert_called_once()
        assert device_tracker._last_known_location == (37.7749, -122.4194)

    def test_handle_coordinator_update_zone_change(
        self, device_tracker, mock_coordinator, hass: HomeAssistant
    ):
        """Test coordinator update with zone change."""
        device_tracker.hass = hass
        device_tracker.coordinator = mock_coordinator
        device_tracker._current_zone = STATE_HOME

        new_gps_data = {"latitude": 37.7749, "longitude": -122.4194}

        mock_coordinator.get_module_data.return_value = new_gps_data

        with patch.object(device_tracker, "location_name", STATE_NOT_HOME):
            with patch.object(
                device_tracker, "_handle_zone_change"
            ) as mock_zone_change:
                device_tracker._handle_coordinator_update()

        # Should handle zone change
        mock_zone_change.assert_called_once_with(STATE_HOME, STATE_NOT_HOME)
        assert device_tracker._current_zone == STATE_NOT_HOME

    def test_update_location_history(self, device_tracker):
        """Test location history update."""
        location = (37.7749, -122.4194)
        gps_data = {"accuracy": 5, "speed": 2.0}

        with patch.object(device_tracker, "location_name", "Dog Park"):
            device_tracker._update_location_history(location, gps_data)

        assert len(device_tracker._location_history) == 1
        entry = device_tracker._location_history[0]

        assert entry["latitude"] == 37.7749
        assert entry["longitude"] == -122.4194
        assert entry["accuracy"] == 5
        assert entry["speed"] == 2.0
        assert entry["zone"] == "Dog Park"
        assert "timestamp" in entry

    def test_update_location_history_limit(self, device_tracker):
        """Test location history respects size limit."""
        # Fill history beyond limit
        for i in range(105):
            location = (37.7749 + i * 0.001, -122.4194)
            gps_data = {"accuracy": 5}
            device_tracker._update_location_history(location, gps_data)

        # Should keep only last 100 entries
        assert len(device_tracker._location_history) == 100

    def test_handle_zone_change_arrived_home(self, device_tracker, hass: HomeAssistant):
        """Test zone change event when arriving home."""
        device_tracker.hass = hass

        with patch.object(hass.bus, "async_fire") as mock_fire:
            device_tracker._handle_zone_change(STATE_NOT_HOME, STATE_HOME)

        # Should fire arrived home event
        assert mock_fire.call_count == 2  # One specific + one general event

        # Check arrived home event
        arrived_call = mock_fire.call_args_list[0]
        assert arrived_call[0][0] == "pawcontrol_dog_arrived_home"
        event_data = arrived_call[0][1]
        assert event_data[ATTR_DOG_ID] == "dog1"
        assert event_data[ATTR_DOG_NAME] == "Buddy"
        assert event_data["previous_zone"] == STATE_NOT_HOME

    def test_handle_zone_change_left_home(self, device_tracker, hass: HomeAssistant):
        """Test zone change event when leaving home."""
        device_tracker.hass = hass

        with patch.object(hass.bus, "async_fire") as mock_fire:
            device_tracker._handle_zone_change(STATE_HOME, "Dog Park")

        # Should fire left home event
        assert mock_fire.call_count == 2  # One specific + one general event

        # Check left home event
        left_call = mock_fire.call_args_list[0]
        assert left_call[0][0] == "pawcontrol_dog_left_home"
        event_data = left_call[0][1]
        assert event_data[ATTR_DOG_ID] == "dog1"
        assert event_data[ATTR_DOG_NAME] == "Buddy"
        assert event_data["new_zone"] == "Dog Park"

    def test_handle_zone_change_same_zone(self, device_tracker, hass: HomeAssistant):
        """Test zone change with same zone (no event)."""
        device_tracker.hass = hass

        with patch.object(hass.bus, "async_fire") as mock_fire:
            device_tracker._handle_zone_change(STATE_HOME, STATE_HOME)

        # Should not fire any events for same zone
        mock_fire.assert_not_called()

    def test_get_gps_data(self, device_tracker, mock_coordinator):
        """Test getting GPS data from coordinator."""
        mock_gps_data = {"latitude": 37.7749, "longitude": -122.4194}
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        result = device_tracker._get_gps_data()

        assert result == mock_gps_data
        mock_coordinator.get_module_data.assert_called_once_with("dog1", "gps")

    def test_get_walk_data(self, device_tracker, mock_coordinator):
        """Test getting walk data from coordinator."""
        mock_walk_data = {"walk_in_progress": True, "current_walk_distance": 500}
        mock_coordinator.get_module_data.return_value = mock_walk_data
        device_tracker.coordinator = mock_coordinator

        result = device_tracker._get_walk_data()

        assert result == mock_walk_data
        mock_coordinator.get_module_data.assert_called_once_with("dog1", "walk")

    def test_get_dog_data(self, device_tracker, mock_coordinator):
        """Test getting dog data from coordinator."""
        mock_dog_data = {"dog_info": {"dog_breed": "Golden Retriever", "dog_age": 5}}
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = mock_dog_data
        device_tracker.coordinator = mock_coordinator

        result = device_tracker._get_dog_data()

        assert result == mock_dog_data
        mock_coordinator.get_dog_data.assert_called_once_with("dog1")

    def test_get_dog_data_coordinator_unavailable(
        self, device_tracker, mock_coordinator
    ):
        """Test getting dog data when coordinator is unavailable."""
        mock_coordinator.available = False
        device_tracker.coordinator = mock_coordinator

        result = device_tracker._get_dog_data()

        assert result is None

    @pytest.mark.asyncio
    async def test_async_update_location_valid_coordinates(
        self, device_tracker, mock_coordinator
    ):
        """Test manual location update with valid coordinates."""
        device_tracker.coordinator = mock_coordinator
        mock_coordinator.async_refresh_dog = AsyncMock()

        await device_tracker.async_update_location(37.7749, -122.4194, 5.0)

        # Should trigger coordinator refresh
        mock_coordinator.async_refresh_dog.assert_called_once_with("dog1")

    @pytest.mark.asyncio
    async def test_async_update_location_invalid_coordinates(self, device_tracker):
        """Test manual location update with invalid coordinates."""
        # Test invalid latitude
        with pytest.raises(ValueError, match="Invalid coordinates provided"):
            await device_tracker.async_update_location(95.0, -122.4194)

        # Test invalid longitude
        with pytest.raises(ValueError, match="Invalid coordinates provided"):
            await device_tracker.async_update_location(37.7749, 185.0)

    def test_get_location_history_recent(self, device_tracker):
        """Test getting recent location history."""
        # Add some history entries
        now = dt_util.utcnow()

        # Recent entry (1 hour ago)
        recent_entry = {
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        # Old entry (25 hours ago)
        old_entry = {
            "timestamp": (now - timedelta(hours=25)).isoformat(),
            "latitude": 37.7750,
            "longitude": -122.4195,
        }

        device_tracker._location_history = [old_entry, recent_entry]

        # Get last 24 hours
        recent_history = device_tracker.get_location_history(24)

        # Should only return recent entry
        assert len(recent_history) == 1
        assert recent_history[0] == recent_entry

    def test_get_location_history_empty(self, device_tracker):
        """Test getting location history when empty."""
        device_tracker._location_history = []

        history = device_tracker.get_location_history(24)

        assert history == []

    def test_calculate_distance_traveled_with_history(self, device_tracker):
        """Test distance calculation with location history."""
        # Mock location history with known coordinates
        device_tracker._location_history = [
            {
                "timestamp": (dt_util.utcnow() - timedelta(hours=2)).isoformat(),
                "latitude": 37.7749,
                "longitude": -122.4194,
            },
            {
                "timestamp": (dt_util.utcnow() - timedelta(hours=1)).isoformat(),
                "latitude": 37.7750,  # Slight movement
                "longitude": -122.4195,
            },
        ]

        with patch(
            "custom_components.pawcontrol.device_tracker.distance", return_value=0.1
        ):  # 0.1 km
            distance_traveled = device_tracker.calculate_distance_traveled(24)

        # Should return distance in meters (0.1 km = 100 meters)
        assert distance_traveled == 100.0

    def test_calculate_distance_traveled_insufficient_history(self, device_tracker):
        """Test distance calculation with insufficient history."""
        # Only one entry
        device_tracker._location_history = [
            {
                "timestamp": dt_util.utcnow().isoformat(),
                "latitude": 37.7749,
                "longitude": -122.4194,
            }
        ]

        distance_traveled = device_tracker.calculate_distance_traveled(24)

        # Should return 0 for insufficient data
        assert distance_traveled == 0.0

    def test_state_attributes(self, device_tracker, mock_coordinator, mock_gps_data):
        """Test state attributes property."""
        mock_coordinator.get_module_data.return_value = mock_gps_data
        device_tracker.coordinator = mock_coordinator

        attrs = device_tracker.state_attributes

        # Should include coordinate information
        assert attrs[ATTR_LATITUDE] == 37.7749
        assert attrs[ATTR_LONGITUDE] == -122.4194
        assert attrs[ATTR_GPS_ACCURACY] == 5
        assert attrs["source_type"] == SourceType.GPS

    def test_state_attributes_no_coordinates(self, device_tracker, mock_coordinator):
        """Test state attributes without coordinates."""
        mock_coordinator.get_module_data.return_value = None
        device_tracker.coordinator = mock_coordinator
        device_tracker._restored_data = {}

        attrs = device_tracker.state_attributes

        # Should not include coordinate information when not available
        assert ATTR_LATITUDE not in attrs
        assert ATTR_LONGITUDE not in attrs
        assert attrs["source_type"] == SourceType.GPS

    def test_extra_state_attributes_with_walk_data(
        self, device_tracker, mock_coordinator
    ):
        """Test extra state attributes with walk integration data."""
        mock_gps_data = {"latitude": 37.7749, "longitude": -122.4194}
        mock_walk_data = {
            "walk_in_progress": True,
            "current_walk_distance": 1500,
            "current_walk_duration": "00:30:00",
        }

        def mock_get_module_data(dog_id, module):
            if module == "gps":
                return mock_gps_data
            elif module == "walk":
                return mock_walk_data
            return None

        mock_coordinator.get_module_data.side_effect = mock_get_module_data
        device_tracker.coordinator = mock_coordinator

        attrs = device_tracker.extra_state_attributes

        assert attrs["walk_in_progress"] is True
        assert attrs["current_walk_distance"] == 1500
        assert attrs["current_walk_duration"] == "00:30:00"

    def test_extra_state_attributes_with_dog_info(
        self, device_tracker, mock_coordinator
    ):
        """Test extra state attributes with dog information."""
        mock_gps_data = {"latitude": 37.7749, "longitude": -122.4194}
        mock_dog_data = {
            "dog_info": {
                "dog_breed": "Golden Retriever",
                "dog_age": 5,
                "dog_size": "Large",
            }
        }

        mock_coordinator.get_module_data.return_value = mock_gps_data
        mock_coordinator.available = True
        mock_coordinator.get_dog_data.return_value = mock_dog_data
        device_tracker.coordinator = mock_coordinator

        attrs = device_tracker.extra_state_attributes

        assert attrs["dog_breed"] == "Golden Retriever"
        assert attrs["dog_age"] == 5
        assert attrs["dog_size"] == "Large"


class TestDeviceTrackerIntegrationScenarios:
    """Test device tracker integration scenarios and edge cases."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        coordinator.get_module_data = Mock()
        return coordinator

    def test_multiple_dogs_unique_trackers(self, mock_coordinator):
        """Test that multiple dogs create unique device trackers."""
        dogs = [("dog1", "Buddy"), ("dog2", "Max"), ("dog3", "Luna")]

        trackers = []
        for dog_id, dog_name in dogs:
            trackers.append(PawControlDeviceTracker(mock_coordinator, dog_id, dog_name))

        unique_ids = [tracker._attr_unique_id for tracker in trackers]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

        # Verify format
        assert "pawcontrol_dog1_gps" in unique_ids
        assert "pawcontrol_dog2_gps" in unique_ids
        assert "pawcontrol_dog3_gps" in unique_ids

    def test_coordinator_unavailable_affects_all_trackers(self, mock_coordinator):
        """Test that coordinator unavailability affects all device trackers."""
        mock_coordinator.available = False

        trackers = [
            PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy"),
            PawControlDeviceTracker(mock_coordinator, "dog2", "Max"),
            PawControlDeviceTracker(mock_coordinator, "dog3", "Luna"),
        ]

        for tracker in trackers:
            assert tracker.available is False

    def test_tracker_isolation_between_dogs(self, mock_coordinator):
        """Test that tracker data is properly isolated between dogs."""
        # Create trackers for different dogs
        tracker1 = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker2 = PawControlDeviceTracker(mock_coordinator, "dog2", "Max")

        # Set up different GPS data for each dog
        def mock_get_module_data(dog_id, module):
            if dog_id == "dog1" and module == "gps":
                return {
                    "latitude": 37.7749,
                    "longitude": -122.4194,
                    "battery_level": 85,
                }
            elif dog_id == "dog2" and module == "gps":
                return {"latitude": 40.7128, "longitude": -74.0060, "battery_level": 45}
            return None

        mock_coordinator.get_module_data.side_effect = mock_get_module_data
        tracker1.coordinator = mock_coordinator
        tracker2.coordinator = mock_coordinator

        # Trackers should return different data
        assert tracker1.latitude == 37.7749
        assert tracker2.latitude == 40.7128
        assert tracker1.battery_level == 85
        assert tracker2.battery_level == 45

    @pytest.mark.asyncio
    async def test_performance_with_many_trackers(self, mock_coordinator):
        """Test performance with large number of device trackers."""
        import time

        start_time = time.time()

        trackers = []
        for dog_num in range(50):  # Create 50 GPS trackers
            dog_id = f"dog{dog_num}"
            dog_name = f"Dog{dog_num}"
            trackers.append(PawControlDeviceTracker(mock_coordinator, dog_id, dog_name))

        creation_time = time.time() - start_time

        # Should create 50 trackers quickly (under 1 second)
        assert len(trackers) == 50
        assert creation_time < 1.0

        # Test that all trackers have unique IDs
        unique_ids = [tracker._attr_unique_id for tracker in trackers]
        assert len(unique_ids) == len(set(unique_ids))

    def test_gps_data_edge_cases(self, mock_coordinator):
        """Test GPS data handling with various edge cases."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.coordinator = mock_coordinator

        edge_cases = [
            ({}, None, None),  # Empty GPS data
            ({"latitude": None, "longitude": None}, None, None),  # None coordinates
            (
                {"latitude": "invalid", "longitude": "invalid"},
                None,
                None,
            ),  # Invalid types
            (
                {"latitude": 91.0, "longitude": -122.4194},
                91.0,
                -122.4194,
            ),  # Out of range lat
            (
                {"latitude": 37.7749, "longitude": 181.0},
                37.7749,
                181.0,
            ),  # Out of range lon
        ]

        for gps_data, expected_lat, expected_lon in edge_cases:
            mock_coordinator.get_module_data.return_value = gps_data

            # Should handle gracefully
            try:
                lat = tracker.latitude
                lon = tracker.longitude
                assert lat == expected_lat
                assert lon == expected_lon
            except Exception as e:
                pytest.fail(f"GPS data edge case should be handled gracefully: {e}")

    def test_zone_detection_comprehensive(self, mock_coordinator, hass: HomeAssistant):
        """Test comprehensive zone detection scenarios."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.hass = hass
        tracker.coordinator = mock_coordinator

        # Test home zone detection
        hass.config.latitude = 37.7749
        hass.config.longitude = -122.4194

        # Mock GPS data at home
        mock_coordinator.get_module_data.return_value = {
            "latitude": 37.7749,  # Exact home coordinates
            "longitude": -122.4194,
        }

        assert tracker.location_name == STATE_HOME

        # Test custom zone detection
        mock_zone_state = Mock()
        mock_zone_state.attributes = {
            "latitude": 37.7750,
            "longitude": -122.4195,
            "radius": 50,
            "friendly_name": "Dog Park",
        }
        mock_zone_state.entity_id = "zone.dog_park"

        with patch.object(hass.states, "async_all", return_value=[mock_zone_state]):
            # Mock GPS data in custom zone
            mock_coordinator.get_module_data.return_value = {
                "latitude": 37.7750,
                "longitude": -122.4195,
            }

            # Should detect custom zone over home
            assert tracker.location_name == "Dog Park"

    def test_battery_monitoring_comprehensive(self, mock_coordinator):
        """Test comprehensive battery monitoring scenarios."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.coordinator = mock_coordinator

        battery_scenarios = [
            (100, "good"),
            (50, "good"),
            (30, "good"),
            (25, "medium"),
            (15, "low"),
            (10, "low"),
            (5, "critical"),
            (0, "critical"),
            (None, "unknown"),
        ]

        for battery_level, expected_status in battery_scenarios:
            mock_coordinator.get_module_data.return_value = {
                "battery_level": battery_level
            }

            # Mock the battery_level property
            with patch.object(tracker, "battery_level", battery_level):
                status = tracker._get_battery_status()
                assert status == expected_status

    def test_movement_detection_comprehensive(self, mock_coordinator):
        """Test comprehensive movement detection scenarios."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")

        movement_scenarios = [
            ({"speed": 0.5}, False),  # Stationary
            ({"speed": 1.5}, True),  # Moving slowly
            ({"speed": 5.0}, True),  # Walking
            ({"speed": 15.0}, True),  # Running
            ({"speed": None}, False),  # No speed data
        ]

        for gps_data, expected_moving in movement_scenarios:
            result = tracker._is_currently_moving(gps_data)
            assert result == expected_moving

    @pytest.mark.asyncio
    async def test_location_history_management(self, mock_coordinator):
        """Test location history management with real-time updates."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")

        # Simulate multiple location updates
        locations = [
            (37.7749, -122.4194),
            (37.7750, -122.4195),
            (37.7751, -122.4196),
            (37.7752, -122.4197),
        ]

        for i, (lat, lon) in enumerate(locations):
            gps_data = {
                "latitude": lat,
                "longitude": lon,
                "accuracy": 5,
                "speed": 2.0 if i > 0 else 0.0,
            }

            tracker._update_location_history((lat, lon), gps_data)

        # Should have all entries
        assert len(tracker._location_history) == 4

        # Verify chronological order
        for i, entry in enumerate(tracker._location_history):
            expected_lat, expected_lon = locations[i]
            assert entry["latitude"] == expected_lat
            assert entry["longitude"] == expected_lon

    def test_error_handling_malformed_data(self, mock_coordinator):
        """Test error handling with malformed GPS data."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.coordinator = mock_coordinator

        malformed_data_cases = [
            {"latitude": "not_a_number", "longitude": -122.4194},
            {"latitude": 37.7749, "longitude": "not_a_number"},
            {"battery_level": "not_a_number"},
            {"accuracy": "not_a_number"},
            {"speed": "not_a_number"},
            {"last_seen": "invalid_date_format"},
        ]

        for malformed_data in malformed_data_cases:
            mock_coordinator.get_module_data.return_value = malformed_data

            # Should handle malformed data gracefully without crashing
            try:
                _ = tracker.latitude
                _ = tracker.longitude
                _ = tracker.battery_level
                _ = tracker.location_accuracy
                _ = tracker.available
                _ = tracker.extra_state_attributes
            except Exception as e:
                pytest.fail(f"Should handle malformed data gracefully: {e}")

    @pytest.mark.asyncio
    async def test_zone_change_event_comprehensive(
        self, mock_coordinator, hass: HomeAssistant
    ):
        """Test comprehensive zone change event scenarios."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.hass = hass

        zone_transitions = [
            (None, STATE_HOME, "pawcontrol_dog_arrived_home"),
            (STATE_HOME, STATE_NOT_HOME, "pawcontrol_dog_left_home"),
            (STATE_NOT_HOME, "Dog Park", "pawcontrol_dog_zone_change"),
            ("Dog Park", "Vet Clinic", "pawcontrol_dog_zone_change"),
            ("Vet Clinic", STATE_HOME, "pawcontrol_dog_arrived_home"),
        ]

        for old_zone, new_zone, expected_event in zone_transitions:
            with patch.object(hass.bus, "async_fire") as mock_fire:
                tracker._handle_zone_change(old_zone, new_zone)

            # Should fire appropriate events
            if expected_event in [
                "pawcontrol_dog_arrived_home",
                "pawcontrol_dog_left_home",
            ]:
                assert mock_fire.call_count == 2  # Specific + general event
                assert mock_fire.call_args_list[0][0][0] == expected_event
            else:
                assert mock_fire.call_count == 1  # Only general event
                assert mock_fire.call_args_list[0][0][0] == "pawcontrol_dog_zone_change"

    def test_distance_calculation_accuracy(self, mock_coordinator):
        """Test distance calculation accuracy with known coordinates."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")

        # Use known coordinates with calculable distance
        # Golden Gate Bridge to Alcatraz Island (approximately 2.4 km)
        golden_gate = (37.8199, -122.4783)
        alcatraz = (37.8267, -122.4230)

        # Mock location history
        now = dt_util.utcnow()
        tracker._location_history = [
            {
                "timestamp": (now - timedelta(hours=1)).isoformat(),
                "latitude": golden_gate[0],
                "longitude": golden_gate[1],
            },
            {
                "timestamp": now.isoformat(),
                "latitude": alcatraz[0],
                "longitude": alcatraz[1],
            },
        ]

        # Calculate distance (should be approximately 2400 meters)
        distance = tracker.calculate_distance_traveled(24)

        # Allow some tolerance for calculation differences
        assert 2300 <= distance <= 2500  # Approximately 2.4 km ± 100m

    @pytest.mark.asyncio
    async def test_state_restoration_comprehensive(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive state restoration scenarios."""
        tracker = PawControlDeviceTracker(mock_coordinator, "dog1", "Buddy")
        tracker.hass = hass
        tracker.entity_id = "device_tracker.buddy_gps"

        # Test various restoration scenarios
        restoration_cases = [
            # Complete state
            {
                ATTR_LATITUDE: 37.7749,
                ATTR_LONGITUDE: -122.4194,
                ATTR_GPS_ACCURACY: 10,
                ATTR_BATTERY_LEVEL: 75,
                "source_type": "gps",
                "last_seen": "2023-06-15T12:30:00",
            },
            # Partial state
            {
                ATTR_LATITUDE: 37.7749,
                ATTR_LONGITUDE: -122.4194,
            },
            # Empty state
            {},
        ]

        for case_attrs in restoration_cases:
            mock_state = Mock()
            mock_state.attributes = case_attrs

            with patch.object(tracker, "async_get_last_state", return_value=mock_state):
                await tracker.async_added_to_hass()

            # Should restore available data without crashing
            if ATTR_LATITUDE in case_attrs and ATTR_LONGITUDE in case_attrs:
                assert tracker._last_known_location == (
                    case_attrs[ATTR_LATITUDE],
                    case_attrs[ATTR_LONGITUDE],
                )

            # Reset for next test
            tracker._restored_data = {}
            tracker._last_known_location = None
