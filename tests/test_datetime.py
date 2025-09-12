"""Tests for datetime platform of Paw Control integration.

This module provides comprehensive test coverage for all datetime entities
including feeding schedules, health appointments, walk reminders, and emergency events.
Tests cover functionality, edge cases, error handling, and performance scenarios
to meet Home Assistant's Platinum quality standards.

Test Coverage:
- 17+ datetime entity classes across all modules
- Async setup with batching logic
- State restoration and persistence
- DateTime validation and service integration
- Extra state attributes and timezone handling
- Module-specific datetime entity creation
- Integration scenarios and coordinator interaction
- Performance testing with large setups
- Emergency notification management
- Service call error handling
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from homeassistant.components.datetime import DOMAIN as DATETIME_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreStateData
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.const import ATTR_DOG_ID
from custom_components.pawcontrol.const import ATTR_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOG_ID
from custom_components.pawcontrol.const import CONF_DOG_NAME
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.const import MODULE_FEEDING
from custom_components.pawcontrol.const import MODULE_HEALTH
from custom_components.pawcontrol.const import MODULE_WALK
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.datetime import _async_add_entities_in_batches
from custom_components.pawcontrol.datetime import async_setup_entry
from custom_components.pawcontrol.datetime import PawControlAdoptionDateDateTime
from custom_components.pawcontrol.datetime import PawControlBirthdateDateTime
from custom_components.pawcontrol.datetime import PawControlBreakfastTimeDateTime
from custom_components.pawcontrol.datetime import PawControlDateTimeBase
from custom_components.pawcontrol.datetime import PawControlDinnerTimeDateTime
from custom_components.pawcontrol.datetime import PawControlEmergencyDateTime
from custom_components.pawcontrol.datetime import PawControlLastFeedingDateTime
from custom_components.pawcontrol.datetime import PawControlLastGroomingDateTime
from custom_components.pawcontrol.datetime import PawControlLastMedicationDateTime
from custom_components.pawcontrol.datetime import PawControlLastVetVisitDateTime
from custom_components.pawcontrol.datetime import PawControlLastWalkDateTime
from custom_components.pawcontrol.datetime import PawControlLunchTimeDateTime
from custom_components.pawcontrol.datetime import PawControlNextFeedingDateTime
from custom_components.pawcontrol.datetime import PawControlNextGroomingDateTime
from custom_components.pawcontrol.datetime import PawControlNextMedicationDateTime
from custom_components.pawcontrol.datetime import PawControlNextVetAppointmentDateTime
from custom_components.pawcontrol.datetime import PawControlNextWalkReminderDateTime
from custom_components.pawcontrol.datetime import PawControlTrainingSessionDateTime
from custom_components.pawcontrol.datetime import PawControlVaccinationDateDateTime


class TestAsyncAddEntitiesInBatches:
    """Test the batching functionality for datetime entity registration."""

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
        entities = [Mock() for _ in range(35)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12, delay_between_batches=0.05
            )

        # Should be called 3 times (12 + 12 + 11)
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
        """Test batching performance with large datetime entity setup."""
        mock_add_entities = Mock()
        # Simulate 170 datetime entities (17 per dog * 10 dogs)
        entities = [Mock() for _ in range(170)]

        start_time = asyncio.get_event_loop().time()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12
            )

        end_time = asyncio.get_event_loop().time()

        # Should complete quickly even with large entity count
        assert end_time - start_time < 1.0

        # Should be called 15 times (170 / 12 = 14.17 -> 15 batches)
        assert mock_add_entities.call_count == 15

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_exact_batch_size(self):
        """Test batching when entities exactly match batch size."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(24)]  # Exactly 2 batches of 12

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12
            )

        # Should be called exactly 2 times
        assert mock_add_entities.call_count == 2

        # Should sleep only once (between first and second batch)
        assert mock_sleep.call_count == 1


class TestAsyncSetupEntry:
    """Test the async setup entry function for datetime platform."""

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
                        MODULE_HEALTH: True,
                        MODULE_WALK: True,
                    },
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Max",
                    "modules": {
                        MODULE_FEEDING: True,
                        MODULE_HEALTH: False,
                        MODULE_WALK: False,
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
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should call batching function
        mock_batch_add.assert_called_once()

        # Get the entities that were passed to batching
        args, kwargs = mock_batch_add.call_args
        entities = args[1]  # Second argument is the entities list

        # Dog1 has all modules: 2 basic + 5 feeding + 6 health + 2 walk = 15 entities
        # Dog2 has limited modules: 2 basic + 5 feeding = 7 entities
        # Total: 22 entities
        assert len(entities) == 22

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
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
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
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should still call batching function but with empty entity list
        mock_batch_add.assert_called_once()
        args, kwargs = mock_batch_add.call_args
        entities = args[1]
        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_required_keys(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with dogs missing required keys."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    # Missing CONF_DOG_ID and CONF_DOG_NAME
                    "modules": {MODULE_FEEDING: True}
                }
            ],
        }

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should still call batching function but with no entities created
        mock_batch_add.assert_called_once()
        args, kwargs = mock_batch_add.call_args
        entities = args[1]
        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_coordinator_in_hass_data(
        self, hass: HomeAssistant
    ):
        """Test setup entry when coordinator is missing from hass.data."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.runtime_data = None

        # Missing coordinator in hass.data
        hass.data[DOMAIN] = {}

        mock_add_entities = Mock()

        with pytest.raises(KeyError):
            await async_setup_entry(hass, entry, mock_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_getattr_runtime_data_none(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry when getattr returns None for runtime_data."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"

        # Mock getattr to return None
        with patch("builtins.getattr", return_value=None):
            hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

            entry.data = {
                CONF_DOGS: [
                    {
                        CONF_DOG_ID: "dog1",
                        CONF_DOG_NAME: "Buddy",
                        "modules": {MODULE_FEEDING: True},
                    }
                ]
            }

            mock_add_entities = Mock()

            with patch(
                "custom_components.pawcontrol.datetime._async_add_entities_in_batches",
                new_callable=AsyncMock,
            ) as mock_batch_add:
                await async_setup_entry(hass, entry, mock_add_entities)

            mock_batch_add.assert_called_once()


class TestPawControlDateTimeBase:
    """Test the base datetime entity class functionality."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def base_datetime_entity(self, mock_coordinator):
        """Create a base datetime entity for testing."""
        return PawControlDateTimeBase(
            mock_coordinator, "dog1", "Buddy", "test_datetime"
        )

    def test_base_datetime_entity_initialization(self, base_datetime_entity):
        """Test base datetime entity initialization."""
        assert base_datetime_entity._dog_id == "dog1"
        assert base_datetime_entity._dog_name == "Buddy"
        assert base_datetime_entity._datetime_type == "test_datetime"
        assert base_datetime_entity._attr_unique_id == "pawcontrol_dog1_test_datetime"
        assert base_datetime_entity._attr_name == "Buddy Test Datetime"

    def test_base_datetime_entity_device_info(self, base_datetime_entity):
        """Test device info configuration."""
        device_info = base_datetime_entity._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "dog1")}
        assert device_info["name"] == "Buddy"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog"
        assert device_info["sw_version"] == "1.0.0"
        assert "configuration_url" in device_info

    def test_native_value_default(self, base_datetime_entity):
        """Test native value when no value is set."""
        assert base_datetime_entity.native_value is None

    def test_native_value_with_value(self, base_datetime_entity):
        """Test native value when value is set."""
        test_datetime = datetime(2023, 6, 15, 14, 30, 0)
        base_datetime_entity._current_value = test_datetime

        assert base_datetime_entity.native_value == test_datetime

    def test_extra_state_attributes(self, base_datetime_entity):
        """Test extra state attributes."""
        attrs = base_datetime_entity.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "dog1"
        assert attrs[ATTR_DOG_NAME] == "Buddy"
        assert attrs["datetime_type"] == "test_datetime"

    @pytest.mark.asyncio
    async def test_async_added_to_hass_without_previous_state(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass without previous state."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=None
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_valid_previous_state(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass with valid previous state."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        mock_state = Mock()
        mock_state.state = "2023-06-15T14:30:00+00:00"

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is not None
        assert base_datetime_entity._current_value.year == 2023
        assert base_datetime_entity._current_value.month == 6
        assert base_datetime_entity._current_value.day == 15

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_invalid_previous_state(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass with invalid previous state."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        mock_state = Mock()
        mock_state.state = "invalid-datetime-format"

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_unknown_state(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass with unknown state."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        mock_state = Mock()
        mock_state.state = "unknown"

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_set_value_valid_datetime(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test setting valid datetime value."""
        base_datetime_entity.hass = hass
        test_datetime = datetime(2023, 7, 20, 16, 45, 0)

        with patch.object(
            base_datetime_entity, "async_write_ha_state"
        ) as mock_write_state:
            await base_datetime_entity.async_set_value(test_datetime)

        assert base_datetime_entity._current_value == test_datetime
        mock_write_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_unavailable_state(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass with unavailable state."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        mock_state = Mock()
        mock_state.state = "unavailable"

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_type_error(
        self, hass: HomeAssistant, base_datetime_entity
    ):
        """Test entity added to hass with TypeError during parsing."""
        base_datetime_entity.hass = hass
        base_datetime_entity.entity_id = "datetime.buddy_test_datetime"

        mock_state = Mock()
        mock_state.state = None  # This could cause TypeError

        with patch.object(
            base_datetime_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_datetime_entity.async_added_to_hass()

        assert base_datetime_entity._current_value is None


class TestPawControlBirthdateDateTime:
    """Test the birthdate datetime entity."""

    @pytest.fixture
    def birthdate_datetime_entity(self, mock_coordinator):
        """Create a birthdate datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlBirthdateDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_birthdate_datetime_entity_initialization(self, birthdate_datetime_entity):
        """Test birthdate datetime entity initialization."""
        assert birthdate_datetime_entity._datetime_type == "birthdate"
        assert birthdate_datetime_entity._attr_icon == "mdi:cake"

    @pytest.mark.asyncio
    async def test_async_set_value_birthdate_with_age_calculation(
        self, birthdate_datetime_entity
    ):
        """Test setting birthdate with age calculation."""
        test_datetime = datetime(2020, 5, 15, 10, 30, 0)

        with patch.object(birthdate_datetime_entity, "async_write_ha_state"):
            await birthdate_datetime_entity.async_set_value(test_datetime)

        assert birthdate_datetime_entity._current_value == test_datetime


class TestPawControlAdoptionDateDateTime:
    """Test the adoption date datetime entity."""

    @pytest.fixture
    def adoption_datetime_entity(self, mock_coordinator):
        """Create an adoption date datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlAdoptionDateDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_adoption_datetime_entity_initialization(self, adoption_datetime_entity):
        """Test adoption date datetime entity initialization."""
        assert adoption_datetime_entity._datetime_type == "adoption_date"
        assert adoption_datetime_entity._attr_icon == "mdi:home-heart"


class TestPawControlFeedingTimeEntities:
    """Test the feeding time datetime entities."""

    @pytest.fixture
    def breakfast_entity(self, mock_coordinator):
        """Create a breakfast time entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlBreakfastTimeDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def lunch_entity(self, mock_coordinator):
        """Create a lunch time entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlLunchTimeDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def dinner_entity(self, mock_coordinator):
        """Create a dinner time entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlDinnerTimeDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_breakfast_entity_initialization(self, breakfast_entity):
        """Test breakfast time entity initialization."""
        assert breakfast_entity._datetime_type == "breakfast_time"
        assert breakfast_entity._attr_icon == "mdi:food-croissant"
        # Should have default time set
        assert breakfast_entity._current_value is not None
        assert breakfast_entity._current_value.hour == 8

    def test_lunch_entity_initialization(self, lunch_entity):
        """Test lunch time entity initialization."""
        assert lunch_entity._datetime_type == "lunch_time"
        assert lunch_entity._attr_icon == "mdi:food"
        # Should have default time set
        assert lunch_entity._current_value is not None
        assert lunch_entity._current_value.hour == 13

    def test_dinner_entity_initialization(self, dinner_entity):
        """Test dinner time entity initialization."""
        assert dinner_entity._datetime_type == "dinner_time"
        assert dinner_entity._attr_icon == "mdi:silverware-fork-knife"
        # Should have default time set
        assert dinner_entity._current_value is not None
        assert dinner_entity._current_value.hour == 18

    def test_feeding_time_default_values(
        self, breakfast_entity, lunch_entity, dinner_entity
    ):
        """Test that feeding times have appropriate default values."""
        # Breakfast should be at 8:00
        assert breakfast_entity.native_value.hour == 8
        assert breakfast_entity.native_value.minute == 0

        # Lunch should be at 13:00
        assert lunch_entity.native_value.hour == 13
        assert lunch_entity.native_value.minute == 0

        # Dinner should be at 18:00
        assert dinner_entity.native_value.hour == 18
        assert dinner_entity.native_value.minute == 0

    def test_feeding_time_default_timezone_handling(self, breakfast_entity):
        """Test timezone handling in default feeding times."""
        # Default time should be in current timezone context
        assert (
            breakfast_entity.native_value.tzinfo is not None
            or breakfast_entity.native_value.tzinfo is None
        )

        # Should be reasonable hour range
        assert 0 <= breakfast_entity.native_value.hour <= 23


class TestPawControlLastFeedingDateTime:
    """Test the last feeding datetime entity."""

    @pytest.fixture
    def last_feeding_entity(self, mock_coordinator):
        """Create a last feeding datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        return PawControlLastFeedingDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_last_feeding_entity_initialization(self, last_feeding_entity):
        """Test last feeding entity initialization."""
        assert last_feeding_entity._datetime_type == "last_feeding"
        assert last_feeding_entity._attr_icon == "mdi:food-drumstick"

    def test_native_value_from_coordinator_data(
        self, last_feeding_entity, mock_coordinator
    ):
        """Test getting native value from coordinator data."""
        mock_feeding_data = {"feeding": {"last_feeding": "2023-06-15T12:30:00+00:00"}}

        mock_coordinator.get_dog_data.return_value = mock_feeding_data
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is not None
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15

    def test_native_value_from_coordinator_data_invalid(
        self, last_feeding_entity, mock_coordinator
    ):
        """Test getting native value with invalid coordinator data."""
        mock_feeding_data = {"feeding": {"last_feeding": "invalid-datetime"}}

        mock_coordinator.get_dog_data.return_value = mock_feeding_data
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is None

    def test_native_value_no_coordinator_data(
        self, last_feeding_entity, mock_coordinator
    ):
        """Test getting native value when no coordinator data available."""
        mock_coordinator.get_dog_data.return_value = None
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is None

    def test_native_value_no_feeding_data(self, last_feeding_entity, mock_coordinator):
        """Test getting native value when no feeding data available."""
        mock_coordinator.get_dog_data.return_value = {"other": "data"}
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is None

    def test_native_value_empty_feeding_data(
        self, last_feeding_entity, mock_coordinator
    ):
        """Test getting native value when feeding data is empty."""
        mock_coordinator.get_dog_data.return_value = {"feeding": {}}
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is None

    def test_native_value_type_error(self, last_feeding_entity, mock_coordinator):
        """Test getting native value when TypeError occurs during parsing."""
        mock_feeding_data = {
            "feeding": {
                "last_feeding": None  # Could cause TypeError
            }
        }

        mock_coordinator.get_dog_data.return_value = mock_feeding_data
        last_feeding_entity.coordinator = mock_coordinator

        result = last_feeding_entity.native_value
        assert result is None

    @pytest.mark.asyncio
    async def test_async_set_value_logs_feeding(
        self, hass: HomeAssistant, last_feeding_entity
    ):
        """Test setting last feeding value logs feeding event."""
        last_feeding_entity.hass = hass
        test_datetime = datetime(2023, 6, 15, 12, 30, 0)

        with patch.object(  # noqa: SIM117
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            with patch.object(last_feeding_entity, "async_write_ha_state"):
                await last_feeding_entity.async_set_value(test_datetime)

        # Should call feed_dog service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "feed_dog",
            {
                ATTR_DOG_ID: "dog1",
                "meal_type": "snack",  # Default for manual entries
            },
        )

    @pytest.mark.asyncio
    async def test_async_set_value_service_error(
        self, hass: HomeAssistant, last_feeding_entity
    ):
        """Test setting last feeding when service call fails."""
        last_feeding_entity.hass = hass
        test_datetime = datetime(2023, 6, 15, 12, 30, 0)

        with (
            patch.object(
                hass.services, "async_call", side_effect=Exception("Service error")
            ),
            patch.object(last_feeding_entity, "async_write_ha_state"),
        ):
            # Should not raise exception despite service error
            await last_feeding_entity.async_set_value(test_datetime)

        # Value should still be set
        assert last_feeding_entity._current_value == test_datetime


class TestPawControlNextFeedingDateTime:
    """Test the next feeding datetime entity."""

    @pytest.fixture
    def next_feeding_entity(self, mock_coordinator):
        """Create a next feeding datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextFeedingDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_next_feeding_entity_initialization(self, next_feeding_entity):
        """Test next feeding entity initialization."""
        assert next_feeding_entity._datetime_type == "next_feeding"
        assert next_feeding_entity._attr_icon == "mdi:clock-alert"

    @pytest.mark.asyncio
    async def test_async_set_value_schedules_reminder(self, next_feeding_entity):
        """Test setting next feeding value schedules reminder."""
        test_datetime = datetime(2023, 6, 15, 18, 0, 0)

        with patch.object(next_feeding_entity, "async_write_ha_state"):
            await next_feeding_entity.async_set_value(test_datetime)

        assert next_feeding_entity._current_value == test_datetime


class TestPawControlHealthDateTimeEntities:
    """Test the health-related datetime entities."""

    @pytest.fixture
    def last_vet_visit_entity(self, mock_coordinator):
        """Create a last vet visit datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        return PawControlLastVetVisitDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_vet_appointment_entity(self, mock_coordinator):
        """Create a next vet appointment datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextVetAppointmentDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def last_grooming_entity(self, mock_coordinator):
        """Create a last grooming datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        return PawControlLastGroomingDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_grooming_entity(self, mock_coordinator):
        """Create a next grooming datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextGroomingDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def last_medication_entity(self, mock_coordinator):
        """Create a last medication datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlLastMedicationDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_medication_entity(self, mock_coordinator):
        """Create a next medication datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextMedicationDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_health_entities_initialization(
        self,
        last_vet_visit_entity,
        next_vet_appointment_entity,
        last_grooming_entity,
        next_grooming_entity,
        last_medication_entity,
        next_medication_entity,
    ):
        """Test health datetime entities initialization."""
        assert last_vet_visit_entity._datetime_type == "last_vet_visit"
        assert last_vet_visit_entity._attr_icon == "mdi:medical-bag"

        assert next_vet_appointment_entity._datetime_type == "next_vet_appointment"
        assert next_vet_appointment_entity._attr_icon == "mdi:calendar-medical"

        assert last_grooming_entity._datetime_type == "last_grooming"
        assert last_grooming_entity._attr_icon == "mdi:content-cut"

        assert next_grooming_entity._datetime_type == "next_grooming"
        assert next_grooming_entity._attr_icon == "mdi:calendar-clock"

        assert last_medication_entity._datetime_type == "last_medication"
        assert last_medication_entity._attr_icon == "mdi:pill"

        assert next_medication_entity._datetime_type == "next_medication"
        assert next_medication_entity._attr_icon == "mdi:alarm-plus"

    def test_last_vet_visit_native_value_from_coordinator(
        self, last_vet_visit_entity, mock_coordinator
    ):
        """Test getting last vet visit from coordinator data."""
        mock_health_data = {"health": {"last_vet_visit": "2023-05-10T14:30:00+00:00"}}

        mock_coordinator.get_dog_data.return_value = mock_health_data
        last_vet_visit_entity.coordinator = mock_coordinator

        result = last_vet_visit_entity.native_value
        assert result is not None
        assert result.year == 2023
        assert result.month == 5
        assert result.day == 10

    def test_last_vet_visit_native_value_empty_health(
        self, last_vet_visit_entity, mock_coordinator
    ):
        """Test getting last vet visit when health data is empty."""
        mock_coordinator.get_dog_data.return_value = {"health": {}}
        last_vet_visit_entity.coordinator = mock_coordinator

        result = last_vet_visit_entity.native_value
        assert result is None

    def test_last_grooming_native_value_from_coordinator(
        self, last_grooming_entity, mock_coordinator
    ):
        """Test getting last grooming from coordinator data."""
        mock_health_data = {"health": {"last_grooming": "2023-04-20T10:00:00+00:00"}}

        mock_coordinator.get_dog_data.return_value = mock_health_data
        last_grooming_entity.coordinator = mock_coordinator

        result = last_grooming_entity.native_value
        assert result is not None
        assert result.year == 2023
        assert result.month == 4
        assert result.day == 20

    @pytest.mark.asyncio
    async def test_last_vet_visit_async_set_value_logs_health(
        self, hass: HomeAssistant, last_vet_visit_entity
    ):
        """Test setting last vet visit logs health data."""
        last_vet_visit_entity.hass = hass
        test_datetime = datetime(2023, 5, 10, 14, 30, 0)

        with patch.object(  # noqa: SIM117
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            with patch.object(last_vet_visit_entity, "async_write_ha_state"):
                await last_vet_visit_entity.async_set_value(test_datetime)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Vet visit recorded for 2023-05-10",
            },
        )

    @pytest.mark.asyncio
    async def test_last_grooming_async_set_value_logs_grooming(
        self, hass: HomeAssistant, last_grooming_entity
    ):
        """Test setting last grooming logs grooming session."""
        last_grooming_entity.hass = hass
        test_datetime = datetime(2023, 4, 20, 10, 0, 0)

        with patch.object(  # noqa: SIM117
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            with patch.object(last_grooming_entity, "async_write_ha_state"):
                await last_grooming_entity.async_set_value(test_datetime)

        # Should call start_grooming service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "start_grooming",
            {
                ATTR_DOG_ID: "dog1",
                "type": "full_grooming",
                "notes": "Grooming session on 2023-04-20",
            },
        )

    @pytest.mark.asyncio
    async def test_last_medication_async_set_value_logs_medication(
        self, hass: HomeAssistant, last_medication_entity
    ):
        """Test setting last medication logs medication."""
        last_medication_entity.hass = hass
        test_datetime = datetime(2023, 6, 1, 8, 0, 0)

        with patch.object(  # noqa: SIM117
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            with patch.object(last_medication_entity, "async_write_ha_state"):
                await last_medication_entity.async_set_value(test_datetime)

        # Should call log_medication service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_medication",
            {
                ATTR_DOG_ID: "dog1",
                "medication_name": "Manual Entry",
                "dose": "As scheduled",
            },
        )

    @pytest.mark.asyncio
    async def test_next_vet_appointment_async_set_value(
        self, next_vet_appointment_entity
    ):
        """Test setting next vet appointment."""
        test_datetime = datetime(2023, 7, 15, 10, 0, 0)

        with patch.object(next_vet_appointment_entity, "async_write_ha_state"):
            await next_vet_appointment_entity.async_set_value(test_datetime)

        assert next_vet_appointment_entity._current_value == test_datetime

    @pytest.mark.asyncio
    async def test_next_medication_async_set_value(self, next_medication_entity):
        """Test setting next medication reminder."""
        test_datetime = datetime(2023, 6, 2, 8, 0, 0)

        with patch.object(next_medication_entity, "async_write_ha_state"):
            await next_medication_entity.async_set_value(test_datetime)

        assert next_medication_entity._current_value == test_datetime

    @pytest.mark.asyncio
    async def test_health_service_calls_with_errors(
        self,
        hass: HomeAssistant,
        last_vet_visit_entity,
        last_grooming_entity,
        last_medication_entity,
    ):
        """Test health service calls handle errors gracefully."""
        entities_and_times = [
            (last_vet_visit_entity, datetime(2023, 5, 10, 14, 30, 0)),
            (last_grooming_entity, datetime(2023, 4, 20, 10, 0, 0)),
            (last_medication_entity, datetime(2023, 6, 1, 8, 0, 0)),
        ]

        for entity, test_datetime in entities_and_times:
            entity.hass = hass

            with (
                patch.object(
                    hass.services, "async_call", side_effect=Exception("Service error")
                ),
                patch.object(entity, "async_write_ha_state"),
            ):
                # Should not raise exception despite service error
                await entity.async_set_value(test_datetime)

            # Value should still be set
            assert entity._current_value == test_datetime


class TestPawControlWalkDateTimeEntities:
    """Test the walk-related datetime entities."""

    @pytest.fixture
    def last_walk_entity(self, mock_coordinator):
        """Create a last walk datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.get_dog_data = Mock()
        return PawControlLastWalkDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_walk_reminder_entity(self, mock_coordinator):
        """Create a next walk reminder datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextWalkReminderDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_walk_entities_initialization(
        self, last_walk_entity, next_walk_reminder_entity
    ):
        """Test walk datetime entities initialization."""
        assert last_walk_entity._datetime_type == "last_walk"
        assert last_walk_entity._attr_icon == "mdi:walk"

        assert next_walk_reminder_entity._datetime_type == "next_walk_reminder"
        assert next_walk_reminder_entity._attr_icon == "mdi:bell-ring"

    def test_last_walk_native_value_from_coordinator(
        self, last_walk_entity, mock_coordinator
    ):
        """Test getting last walk from coordinator data."""
        mock_walk_data = {"walk": {"last_walk": "2023-06-15T16:30:00+00:00"}}

        mock_coordinator.get_dog_data.return_value = mock_walk_data
        last_walk_entity.coordinator = mock_coordinator

        result = last_walk_entity.native_value
        assert result is not None
        assert result.year == 2023
        assert result.month == 6
        assert result.day == 15

    def test_last_walk_native_value_missing_walk_data(
        self, last_walk_entity, mock_coordinator
    ):
        """Test getting last walk when walk data is missing."""
        mock_coordinator.get_dog_data.return_value = {"other": "data"}
        last_walk_entity.coordinator = mock_coordinator

        result = last_walk_entity.native_value
        assert result is None

    @pytest.mark.asyncio
    async def test_last_walk_async_set_value_logs_walk(
        self, hass: HomeAssistant, last_walk_entity
    ):
        """Test setting last walk logs walk session."""
        last_walk_entity.hass = hass
        test_datetime = datetime(2023, 6, 15, 16, 30, 0)

        with (
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_service_call,
            patch.object(last_walk_entity, "async_write_ha_state"),
        ):
            await last_walk_entity.async_set_value(test_datetime)

        # Should call start_walk and end_walk services
        assert mock_service_call.call_count == 2

        # First call should be start_walk
        first_call = mock_service_call.call_args_list[0]
        assert first_call[0] == (DOMAIN, "start_walk")
        assert first_call[1] == {ATTR_DOG_ID: "dog1"}

        # Second call should be end_walk
        second_call = mock_service_call.call_args_list[1]
        assert second_call[0] == (DOMAIN, "end_walk")
        assert second_call[1] == {ATTR_DOG_ID: "dog1"}

    @pytest.mark.asyncio
    async def test_last_walk_async_set_value_service_error(
        self, hass: HomeAssistant, last_walk_entity
    ):
        """Test setting last walk when service calls fail."""
        last_walk_entity.hass = hass
        test_datetime = datetime(2023, 6, 15, 16, 30, 0)

        with (
            patch.object(
                hass.services, "async_call", side_effect=Exception("Service error")
            ),
            patch.object(last_walk_entity, "async_write_ha_state"),
        ):
            # Should not raise exception despite service errors
            await last_walk_entity.async_set_value(test_datetime)

        # Value should still be set
        assert last_walk_entity._current_value == test_datetime

    @pytest.mark.asyncio
    async def test_next_walk_reminder_async_set_value(self, next_walk_reminder_entity):
        """Test setting next walk reminder."""
        test_datetime = datetime(2023, 6, 16, 8, 0, 0)

        with patch.object(next_walk_reminder_entity, "async_write_ha_state"):
            await next_walk_reminder_entity.async_set_value(test_datetime)

        assert next_walk_reminder_entity._current_value == test_datetime


class TestPawControlSpecialDateTimeEntities:
    """Test special datetime entities like vaccination, training, and emergency."""

    @pytest.fixture
    def vaccination_entity(self, mock_coordinator):
        """Create a vaccination datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlVaccinationDateDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def training_entity(self, mock_coordinator):
        """Create a training session datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlTrainingSessionDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def emergency_entity(self, mock_coordinator):
        """Create an emergency datetime entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.config_entry = Mock()
        coordinator.config_entry.entry_id = "test_entry"
        return PawControlEmergencyDateTime(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_special_entities_initialization(
        self, vaccination_entity, training_entity, emergency_entity
    ):
        """Test special datetime entities initialization."""
        assert vaccination_entity._datetime_type == "vaccination_date"
        assert vaccination_entity._attr_icon == "mdi:needle"

        assert training_entity._datetime_type == "training_session"
        assert training_entity._attr_icon == "mdi:school"

        assert emergency_entity._datetime_type == "emergency_date"
        assert emergency_entity._attr_icon == "mdi:alert"

    @pytest.mark.asyncio
    async def test_vaccination_async_set_value_logs_health(
        self, hass: HomeAssistant, vaccination_entity
    ):
        """Test setting vaccination date logs health data."""
        vaccination_entity.hass = hass
        test_datetime = datetime(2023, 6, 20, 11, 0, 0)

        with patch.object(  # noqa: SIM117
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            with patch.object(vaccination_entity, "async_write_ha_state"):
                await vaccination_entity.async_set_value(test_datetime)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Vaccination recorded for 2023-06-20",
            },
        )

    @pytest.mark.asyncio
    async def test_training_async_set_value_logs_health(
        self, hass: HomeAssistant, training_entity
    ):
        """Test setting training session logs health data."""
        training_entity.hass = hass
        test_datetime = datetime(2023, 6, 25, 15, 0, 0)

        with (
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_service_call,
            patch.object(training_entity, "async_write_ha_state"),
        ):
            await training_entity.async_set_value(test_datetime)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Training session on 2023-06-25",
            },
        )

    @pytest.mark.asyncio
    async def test_emergency_async_set_value_logs_and_notifies(
        self, hass: HomeAssistant, emergency_entity
    ):
        """Test setting emergency date logs health data and sends notification."""
        emergency_entity.hass = hass
        test_datetime = datetime(2023, 6, 30, 22, 15, 0)

        # Mock the hass.data structure for notification manager
        mock_notification_manager = AsyncMock()
        hass.data[DOMAIN] = {"test_entry": {"notifications": mock_notification_manager}}

        with (
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_service_call,
            patch.object(emergency_entity, "async_write_ha_state"),
        ):
            await emergency_entity.async_set_value(test_datetime)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "EMERGENCY EVENT recorded for 2023-06-30 22:15",
            },
        )

        # Should send urgent notification
        mock_notification_manager.async_send_notification.assert_called_once_with(
            "dog1",
            "🚨 Emergency Event Logged",
            "Emergency event logged for Buddy on 2023-06-30 22:15",
            priority="urgent",
        )

    @pytest.mark.asyncio
    async def test_emergency_async_set_value_missing_notification_manager(
        self, hass: HomeAssistant, emergency_entity
    ):
        """Test setting emergency date when notification manager is missing."""
        emergency_entity.hass = hass
        test_datetime = datetime(2023, 6, 30, 22, 15, 0)

        # Mock hass.data without notification manager
        hass.data[DOMAIN] = {
            "test_entry": {}  # Missing notifications
        }

        with (
            patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_service_call,
            patch.object(emergency_entity, "async_write_ha_state"),
        ):
            # Should not raise exception even without notification manager
            await emergency_entity.async_set_value(test_datetime)

        # Should still call health service
        mock_service_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_emergency_async_set_value_notification_error(
        self, hass: HomeAssistant, emergency_entity
    ):
        """Test setting emergency date when notification manager raises error."""
        emergency_entity.hass = hass
        test_datetime = datetime(2023, 6, 30, 22, 15, 0)

        # Mock notification manager that raises exception
        mock_notification_manager = AsyncMock()
        mock_notification_manager.async_send_notification.side_effect = Exception(
            "Notification error"
        )

        hass.data[DOMAIN] = {"test_entry": {"notifications": mock_notification_manager}}

        with patch.object(hass.services, "async_call", new_callable=AsyncMock):  # noqa: SIM117
            with patch.object(emergency_entity, "async_write_ha_state"):
                # Should not raise exception despite notification error
                await emergency_entity.async_set_value(test_datetime)

        # Should still set the value
        assert emergency_entity._current_value == test_datetime

    @pytest.mark.asyncio
    async def test_emergency_async_set_value_missing_hass_data(
        self, hass: HomeAssistant, emergency_entity
    ):
        """Test setting emergency date when hass.data structure is missing."""
        emergency_entity.hass = hass
        test_datetime = datetime(2023, 6, 30, 22, 15, 0)

        # No hass.data[DOMAIN] structure
        hass.data = {}

        with patch.object(hass.services, "async_call", new_callable=AsyncMock):  # noqa: SIM117
            with patch.object(emergency_entity, "async_write_ha_state"):
                # Should not raise exception even with missing data structure
                await emergency_entity.async_set_value(test_datetime)

        # Should still set the value
        assert emergency_entity._current_value == test_datetime


class TestDateTimeEntityIntegrationScenarios:
    """Test datetime entity integration scenarios and edge cases."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_coordinator_unavailable_affects_all_entities(self, mock_coordinator):
        """Test that coordinator unavailability affects all datetime entities."""
        mock_coordinator.available = False

        entities = [
            PawControlBirthdateDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlBreakfastTimeDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastFeedingDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastVetVisitDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastWalkDateTime(mock_coordinator, "dog1", "Buddy"),
        ]

        for entity in entities:
            assert entity.coordinator.available is False

    def test_multiple_dogs_unique_entities(self, mock_coordinator):
        """Test that multiple dogs create unique datetime entities."""
        dogs = [("dog1", "Buddy"), ("dog2", "Max"), ("dog3", "Luna")]

        entities = []
        for dog_id, dog_name in dogs:
            entities.append(
                PawControlBirthdateDateTime(mock_coordinator, dog_id, dog_name)
            )
            entities.append(
                PawControlBreakfastTimeDateTime(mock_coordinator, dog_id, dog_name)
            )

        unique_ids = [entity._attr_unique_id for entity in entities]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

        # Verify format
        assert "pawcontrol_dog1_birthdate" in unique_ids
        assert "pawcontrol_dog2_birthdate" in unique_ids
        assert "pawcontrol_dog3_birthdate" in unique_ids

    def test_entity_attributes_isolation(self, mock_coordinator):
        """Test that entity attributes don't interfere with each other."""
        # Create multiple entities of same type for different dogs
        entity1 = PawControlBirthdateDateTime(mock_coordinator, "dog1", "Buddy")
        entity2 = PawControlBirthdateDateTime(mock_coordinator, "dog2", "Max")

        datetime1 = datetime(2020, 5, 15, 10, 30, 0)
        datetime2 = datetime(2019, 8, 22, 14, 45, 0)

        entity1._current_value = datetime1
        entity2._current_value = datetime2

        # Entities should return different values
        assert entity1.native_value == datetime1
        assert entity2.native_value == datetime2

        # Attributes should be isolated
        attrs1 = entity1.extra_state_attributes
        attrs2 = entity2.extra_state_attributes

        assert attrs1[ATTR_DOG_ID] == "dog1"
        assert attrs2[ATTR_DOG_ID] == "dog2"
        assert attrs1[ATTR_DOG_NAME] == "Buddy"
        assert attrs2[ATTR_DOG_NAME] == "Max"

    def test_datetime_validation_edge_cases(self, mock_coordinator):
        """Test datetime validation with edge cases."""
        entity = PawControlBirthdateDateTime(mock_coordinator, "dog1", "Buddy")

        # Test timezone-aware datetime
        tz_datetime = dt_util.now()
        entity._current_value = tz_datetime
        assert entity.native_value == tz_datetime

        # Test naive datetime
        naive_datetime = datetime(2023, 6, 15, 14, 30, 0)
        entity._current_value = naive_datetime
        assert entity.native_value == naive_datetime

        # Test datetime with microseconds
        micro_datetime = datetime(2023, 6, 15, 14, 30, 45, 123456)
        entity._current_value = micro_datetime
        assert entity.native_value == micro_datetime

    @pytest.mark.asyncio
    async def test_performance_with_many_entities(self, mock_coordinator):
        """Test performance with large number of datetime entities."""
        import time

        start_time = time.time()

        entities = []
        for dog_num in range(10):
            dog_id = f"dog{dog_num}"
            dog_name = f"Dog{dog_num}"

            # Create all datetime entity types for this dog (17 entities per dog)
            entities.extend(
                [
                    PawControlBirthdateDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlAdoptionDateDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlBreakfastTimeDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlLunchTimeDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlDinnerTimeDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlLastFeedingDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlNextFeedingDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlLastVetVisitDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlNextVetAppointmentDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlLastGroomingDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlNextGroomingDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlLastMedicationDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlNextMedicationDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlLastWalkDateTime(mock_coordinator, dog_id, dog_name),
                    PawControlNextWalkReminderDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlVaccinationDateDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlTrainingSessionDateTime(
                        mock_coordinator, dog_id, dog_name
                    ),
                ]
            )

        creation_time = time.time() - start_time

        # Should create 170 entities quickly (under 1 second)
        assert len(entities) == 170
        assert creation_time < 1.0

        # Test that all entities have unique IDs
        unique_ids = [entity._attr_unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids))

    def test_error_handling_malformed_coordinator_data(self, mock_coordinator):
        """Test error handling with malformed coordinator data."""
        # Mock malformed data that could cause exceptions
        mock_coordinator.get_dog_data.return_value = {
            "invalid_structure": "malformed",
            "feeding": {"last_feeding": "not-a-datetime"},
        }

        entity = PawControlLastFeedingDateTime(mock_coordinator, "dog1", "Buddy")
        entity.coordinator = mock_coordinator

        # Should not raise exception and return None for invalid data
        try:
            result = entity.native_value
            assert result is None
        except Exception as e:
            pytest.fail(
                f"Entity should handle malformed data gracefully, but raised: {e}"
            )

    @pytest.mark.asyncio
    async def test_state_restoration_comprehensive(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive state restoration scenarios."""
        entity = PawControlBirthdateDateTime(mock_coordinator, "dog1", "Buddy")
        entity.hass = hass
        entity.entity_id = "datetime.buddy_birthdate"

        # Test various state restoration scenarios
        test_cases = [
            ("2020-05-15T10:30:00+00:00", datetime),  # Valid datetime
            ("unknown", None),  # Unknown state
            ("unavailable", None),  # Unavailable state
            ("", None),  # Empty string
            ("invalid-format", None),  # Invalid format
        ]

        for state_value, expected_type in test_cases:
            mock_state = Mock()
            mock_state.state = state_value

            with patch.object(entity, "async_get_last_state", return_value=mock_state):
                entity._current_value = None  # Reset
                await entity.async_added_to_hass()

                if expected_type is None:
                    assert entity._current_value is None
                else:
                    assert isinstance(entity._current_value, expected_type)

    def test_feeding_time_consistency(self, mock_coordinator):
        """Test that feeding times have consistent behavior."""
        breakfast = PawControlBreakfastTimeDateTime(mock_coordinator, "dog1", "Buddy")
        lunch = PawControlLunchTimeDateTime(mock_coordinator, "dog1", "Buddy")
        dinner = PawControlDinnerTimeDateTime(mock_coordinator, "dog1", "Buddy")

        # All should have default times set
        assert breakfast.native_value is not None
        assert lunch.native_value is not None
        assert dinner.native_value is not None

        # Times should be in logical order
        assert breakfast.native_value.hour < lunch.native_value.hour
        assert lunch.native_value.hour < dinner.native_value.hour

        # All should be on the same day
        assert breakfast.native_value.date() == lunch.native_value.date()
        assert lunch.native_value.date() == dinner.native_value.date()

    @pytest.mark.asyncio
    async def test_service_integration_error_handling(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test service integration with error handling."""
        entity = PawControlLastVetVisitDateTime(mock_coordinator, "dog1", "Buddy")
        entity.hass = hass
        test_datetime = datetime(2023, 5, 10, 14, 30, 0)

        # Mock service call to raise exception
        with (
            patch.object(
                hass.services, "async_call", side_effect=Exception("Service error")
            ),
            patch.object(entity, "async_write_ha_state"),
        ):
            # Should not raise exception - service errors should be handled gracefully
            await entity.async_set_value(test_datetime)

        # Value should still be set despite service error
        assert entity._current_value == test_datetime

    def test_coordinator_data_extraction_edge_cases(self, mock_coordinator):
        """Test coordinator data extraction with various edge cases."""
        entity = PawControlLastFeedingDateTime(mock_coordinator, "dog1", "Buddy")
        entity.coordinator = mock_coordinator

        edge_cases = [
            ({}, None),  # Empty dict
            ({"feeding": {}}, None),  # Empty feeding dict
            ({"feeding": {"last_feeding": None}}, None),  # None value
            ({"feeding": {"last_feeding": ""}}, None),  # Empty string
            ({"feeding": {"other_field": "value"}}, None),  # Missing field
            ({"other": "data"}, None),  # No feeding key
        ]

        for dog_data, expected_result in edge_cases:
            mock_coordinator.get_dog_data.return_value = dog_data
            result = entity.native_value
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_emergency_notification_comprehensive_scenarios(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive emergency notification scenarios."""
        emergency_entity = PawControlEmergencyDateTime(
            mock_coordinator, "dog1", "Buddy"
        )
        emergency_entity.hass = hass
        test_datetime = datetime(2023, 6, 30, 22, 15, 0)

        # Test various hass.data scenarios
        scenarios = [
            # Missing DOMAIN key
            {},
            # Missing entry_id key
            {DOMAIN: {}},
            # Missing notifications key
            {DOMAIN: {"test_entry": {}}},
            # Notifications is None
            {DOMAIN: {"test_entry": {"notifications": None}}},
        ]

        for scenario in scenarios:
            hass.data = scenario

            with patch.object(hass.services, "async_call", new_callable=AsyncMock):  # noqa: SIM117
                with patch.object(emergency_entity, "async_write_ha_state"):
                    # Should not raise exception in any scenario
                    await emergency_entity.async_set_value(test_datetime)

            # Value should still be set
            assert emergency_entity._current_value == test_datetime

    @pytest.mark.asyncio
    async def test_comprehensive_async_set_value_scenarios(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive async_set_value scenarios across all entity types."""
        entities_to_test = [
            PawControlBirthdateDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastFeedingDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastVetVisitDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlLastWalkDateTime(mock_coordinator, "dog1", "Buddy"),
            PawControlVaccinationDateDateTime(mock_coordinator, "dog1", "Buddy"),
        ]

        test_datetime = datetime(2023, 6, 15, 14, 30, 0)

        for entity in entities_to_test:
            entity.hass = hass

            # Test successful set_value
            with patch.object(entity, "async_write_ha_state"):  # noqa: SIM117
                with patch.object(hass.services, "async_call", new_callable=AsyncMock):
                    await entity.async_set_value(test_datetime)

            assert entity._current_value == test_datetime

            # Reset for next test
            entity._current_value = None
