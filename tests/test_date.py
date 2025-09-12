"""Tests for date platform of Paw Control integration.

This module provides comprehensive test coverage for all date entities
including core dog dates, health-related dates, feeding dates, and training dates.
Tests cover functionality, edge cases, error handling, and performance scenarios
to meet Home Assistant's Platinum quality standards.

Test Coverage:
- 14+ date entity classes across all modules
- Async setup with batching logic
- State restoration and persistence
- Date validation and error handling
- Extra state attributes and age calculations
- Module-specific date entity creation
- Integration scenarios and coordinator interaction
- Performance testing with large setups
- Performance monitor decorator integration
- Exception handling and edge cases
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
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
    MODULE_HEALTH,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.date import (
    PawControlAdoptionDate,
    PawControlBirthdateDate,
    PawControlDateBase,
    PawControlDewormingDate,
    PawControlDietEndDate,
    PawControlDietStartDate,
    PawControlLastGroomingDate,
    PawControlLastVetVisitDate,
    PawControlNextDewormingDate,
    PawControlNextGroomingDate,
    PawControlNextTrainingDate,
    PawControlNextVaccinationDate,
    PawControlNextVetAppointmentDate,
    PawControlTrainingStartDate,
    PawControlVaccinationDate,
    _async_add_entities_in_batches,
    async_setup_entry,
)
from custom_components.pawcontrol.exceptions import PawControlError, ValidationError
from homeassistant.components.date import DOMAIN as DATE_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreStateData
from homeassistant.util import dt as dt_util


class TestAsyncAddEntitiesInBatches:
    """Test the batching functionality for date entity registration."""

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
        entities = [Mock() for _ in range(30)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12, delay_between_batches=0.05
            )

        # Should be called 3 times (12 + 12 + 6)
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
        """Test batching performance with large date entity setup."""
        mock_add_entities = Mock()
        # Simulate 140 date entities (14 per dog * 10 dogs)
        entities = [Mock() for _ in range(140)]

        start_time = asyncio.get_event_loop().time()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=12
            )

        end_time = asyncio.get_event_loop().time()

        # Should complete quickly even with large entity count
        assert end_time - start_time < 1.0

        # Should be called 12 times (140 / 12 = 11.67 -> 12 batches)
        assert mock_add_entities.call_count == 12

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_custom_delay(self):
        """Test batching with custom delay between batches."""
        mock_add_entities = Mock()
        entities = [Mock() for _ in range(25)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await _async_add_entities_in_batches(
                mock_add_entities, entities, batch_size=10, delay_between_batches=0.2
            )

        # Should be called 3 times (10 + 10 + 5)
        assert mock_add_entities.call_count == 3

        # Check custom delay was used
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(0.2)


class TestAsyncSetupEntry:
    """Test the async setup entry function for date platform."""

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
                        MODULE_FEEDING: False,
                        MODULE_HEALTH: True,
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
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, mock_config_entry, mock_add_entities)

        # Should call batching function
        mock_batch_add.assert_called_once()

        # Get the entities that were passed to batching
        args, _kwargs = mock_batch_add.call_args
        entities = args[1]  # Second argument is the entities list

        # Dog1 has all modules: 2 core + 8 health + 2 feeding + 2 walk = 14 entities
        # Dog2 has limited modules: 2 core + 8 health = 10 entities
        # Total: 24 entities
        assert len(entities) == 24

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
                    "modules": {MODULE_HEALTH: True},
                }
            ]
        }
        entry.runtime_data = None

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        mock_batch_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_errors(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with configuration errors."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.data = {
            CONF_DOGS: [
                {
                    # Missing required keys to trigger error
                    "invalid_dog": "data"
                }
            ]
        }
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": entry.data[CONF_DOGS],
        }

        mock_add_entities = Mock()

        # Should not raise exception but continue with valid dogs
        with patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        mock_batch_add.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_coordinator_failure(self, hass: HomeAssistant):
        """Test setup entry when coordinator retrieval fails."""
        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.runtime_data = None

        # No coordinator in hass.data should raise PawControlError
        mock_add_entities = Mock()

        with pytest.raises(PawControlError) as exc_info:
            await async_setup_entry(hass, entry, mock_add_entities)

        assert exc_info.value.error_code == "platform_setup_error"
        assert "Date platform setup failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_async_setup_entry_no_dogs_configured(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with no dogs configured."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {"coordinator": mock_coordinator, "dogs": []}

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should still call batching function but with empty entity list
        mock_batch_add.assert_called_once()
        args, _kwargs = mock_batch_add.call_args
        entities = args[1]
        assert len(entities) == 0

    @pytest.mark.asyncio
    async def test_async_setup_entry_exception_during_setup(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry when exception occurs during setup."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {MODULE_HEALTH: True},
                }
            ],
        }

        mock_add_entities = Mock()

        # Mock exception during entity creation
        with (
            patch(
                "custom_components.pawcontrol.date.PawControlBirthdateDate",
                side_effect=Exception("Entity creation failed"),
            ),
            pytest.raises(PawControlError) as exc_info,
        ):
            await async_setup_entry(hass, entry, mock_add_entities)

        assert exc_info.value.error_code == "platform_setup_error"

    @pytest.mark.asyncio
    async def test_async_setup_entry_missing_coordinator_in_legacy_data(
        self, hass: HomeAssistant
    ):
        """Test setup entry when coordinator is missing from legacy data structure."""
        hass.data[DOMAIN] = {
            "test_entry": {}  # Missing coordinator
        }

        entry = Mock(spec=ConfigEntry)
        entry.entry_id = "test_entry"
        entry.runtime_data = None

        mock_add_entities = Mock()

        with pytest.raises(PawControlError):
            await async_setup_entry(hass, entry, mock_add_entities)

    @pytest.mark.asyncio
    async def test_async_setup_entry_partial_dog_configuration(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test setup entry with partially configured dogs."""
        entry = Mock(spec=ConfigEntry)
        entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": [
                {
                    CONF_DOG_ID: "dog1",
                    CONF_DOG_NAME: "Buddy",
                    "modules": {MODULE_FEEDING: True},  # Only feeding module
                },
                {
                    CONF_DOG_ID: "dog2",
                    CONF_DOG_NAME: "Max",
                    "modules": {},  # No modules enabled
                },
            ],
        }

        mock_add_entities = Mock()

        with patch(
            "custom_components.pawcontrol.date._async_add_entities_in_batches",
            new_callable=AsyncMock,
        ) as mock_batch_add:
            await async_setup_entry(hass, entry, mock_add_entities)

        # Should still call batching function
        mock_batch_add.assert_called_once()
        args, _kwargs = mock_batch_add.call_args
        entities = args[1]

        # Dog1: 2 core + 2 feeding = 4 entities
        # Dog2: 2 core = 2 entities
        # Total: 6 entities
        assert len(entities) == 6


class TestPawControlDateBase:
    """Test the base date entity class functionality."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def base_date_entity(self, mock_coordinator):
        """Create a base date entity for testing."""
        return PawControlDateBase(
            mock_coordinator, "dog1", "Buddy", "test_date", "mdi:calendar-test"
        )

    def test_base_date_entity_initialization(self, base_date_entity):
        """Test base date entity initialization."""
        assert base_date_entity._dog_id == "dog1"
        assert base_date_entity._dog_name == "Buddy"
        assert base_date_entity._date_type == "test_date"
        assert base_date_entity._attr_unique_id == "pawcontrol_dog1_test_date"
        assert base_date_entity._attr_name == "Buddy Test Date"
        assert base_date_entity._attr_icon == "mdi:calendar-test"

    def test_base_date_entity_device_info(self, base_date_entity):
        """Test device info configuration."""
        device_info = base_date_entity._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "dog1")}
        assert device_info["name"] == "Buddy"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog Management"
        assert device_info["sw_version"] == "2025.8.2"
        assert "configuration_url" in device_info
        assert device_info["suggested_area"] == "Pet Area"

    def test_native_value_default(self, base_date_entity):
        """Test native value when no value is set."""
        assert base_date_entity.native_value is None

    def test_native_value_with_value(self, base_date_entity):
        """Test native value when value is set."""
        test_date = date(2023, 6, 15)
        base_date_entity._current_value = test_date

        assert base_date_entity.native_value == test_date

    def test_extra_state_attributes_without_value(self, base_date_entity):
        """Test extra state attributes when no date value is set."""
        attrs = base_date_entity.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "dog1"
        assert attrs[ATTR_DOG_NAME] == "Buddy"
        assert attrs["date_type"] == "test_date"
        assert "days_from_today" not in attrs

    def test_extra_state_attributes_with_future_date(self, base_date_entity):
        """Test extra state attributes with future date."""
        today = dt_util.now().date()
        future_date = today + timedelta(days=30)
        base_date_entity._current_value = future_date

        attrs = base_date_entity.extra_state_attributes

        assert attrs["days_from_today"] == 30
        assert attrs["is_past"] is False
        assert attrs["is_today"] is False
        assert attrs["is_future"] is True
        assert attrs["iso_string"] == future_date.isoformat()

    def test_extra_state_attributes_with_past_date(self, base_date_entity):
        """Test extra state attributes with past date."""
        today = dt_util.now().date()
        past_date = today - timedelta(days=15)
        base_date_entity._current_value = past_date

        attrs = base_date_entity.extra_state_attributes

        assert attrs["days_from_today"] == -15
        assert attrs["is_past"] is True
        assert attrs["is_today"] is False
        assert attrs["is_future"] is False

    def test_extra_state_attributes_with_today(self, base_date_entity):
        """Test extra state attributes with today's date."""
        today = dt_util.now().date()
        base_date_entity._current_value = today

        attrs = base_date_entity.extra_state_attributes

        assert attrs["days_from_today"] == 0
        assert attrs["is_past"] is False
        assert attrs["is_today"] is True
        assert attrs["is_future"] is False

    def test_extra_state_attributes_birthdate_age_calculation(self, mock_coordinator):
        """Test age calculation for birthdate entity."""
        birthdate_entity = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")

        today = dt_util.now().date()
        # ~2 years and 1 month old
        birth_date = today - timedelta(days=365 * 2 + 30)
        birthdate_entity._current_value = birth_date

        attrs = birthdate_entity.extra_state_attributes

        assert "age_days" in attrs
        assert "age_years" in attrs
        assert "age_months" in attrs
        assert attrs["age_years"] > 2.0
        assert attrs["age_years"] < 2.2

    @pytest.mark.asyncio
    async def test_async_added_to_hass_without_previous_state(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test entity added to hass without previous state."""
        base_date_entity.hass = hass
        base_date_entity.entity_id = "date.buddy_test_date"

        with patch.object(base_date_entity, "async_get_last_state", return_value=None):
            await base_date_entity.async_added_to_hass()

        assert base_date_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_valid_previous_state(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test entity added to hass with valid previous state."""
        base_date_entity.hass = hass
        base_date_entity.entity_id = "date.buddy_test_date"

        mock_state = Mock()
        mock_state.state = "2023-06-15"

        with patch.object(
            base_date_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_date_entity.async_added_to_hass()

        assert base_date_entity._current_value == date(2023, 6, 15)

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_invalid_previous_state(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test entity added to hass with invalid previous state."""
        base_date_entity.hass = hass
        base_date_entity.entity_id = "date.buddy_test_date"

        mock_state = Mock()
        mock_state.state = "invalid-date-format"

        with patch.object(
            base_date_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_date_entity.async_added_to_hass()

        assert base_date_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_unknown_state(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test entity added to hass with unknown state."""
        base_date_entity.hass = hass
        base_date_entity.entity_id = "date.buddy_test_date"

        mock_state = Mock()
        mock_state.state = "unknown"

        with patch.object(
            base_date_entity, "async_get_last_state", return_value=mock_state
        ):
            await base_date_entity.async_added_to_hass()

        assert base_date_entity._current_value is None

    @pytest.mark.asyncio
    async def test_async_set_value_valid_date(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test setting valid date value."""
        base_date_entity.hass = hass
        test_date = date(2023, 7, 20)

        with patch.object(base_date_entity, "async_write_ha_state") as mock_write_state:  # noqa: SIM117
            with patch.object(
                base_date_entity, "_async_handle_date_set", new_callable=AsyncMock
            ) as mock_handle:
                await base_date_entity.async_set_value(test_date)

        assert base_date_entity._current_value == test_date
        mock_write_state.assert_called_once()
        mock_handle.assert_called_once_with(test_date)

    @pytest.mark.asyncio
    async def test_async_set_value_invalid_type(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test setting invalid value type."""
        base_date_entity.hass = hass

        with pytest.raises(ValidationError) as exc_info:
            await base_date_entity.async_set_value("not-a-date")

        assert exc_info.value.field == "date_value"
        assert "Value must be a date object" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_async_set_value_with_exception_in_handler(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test setting value when handler raises exception."""
        base_date_entity.hass = hass
        test_date = date(2023, 7, 20)

        with (
            patch.object(
                base_date_entity,
                "_async_handle_date_set",
                side_effect=Exception("Handler error"),
            ),
            pytest.raises(ValidationError) as exc_info,
        ):
            await base_date_entity.async_set_value(test_date)

        assert "Failed to set date: Handler error" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_async_set_value_with_performance_monitor(
        self, hass: HomeAssistant, base_date_entity
    ):
        """Test performance monitor decorator integration."""
        base_date_entity.hass = hass
        test_date = date(2023, 7, 20)

        with patch(
            "custom_components.pawcontrol.utils.performance_monitor"
        ) as mock_decorator:
            # Mock the decorator to return the original function
            mock_decorator.return_value = lambda func: func

            with patch.object(base_date_entity, "async_write_ha_state"):  # noqa: SIM117
                with patch.object(
                    base_date_entity, "_async_handle_date_set", new_callable=AsyncMock
                ):
                    await base_date_entity.async_set_value(test_date)

        # Performance monitor should have been called with timeout
        mock_decorator.assert_called_with(timeout=5.0)

    def test_handle_coordinator_update_with_data(
        self, base_date_entity, mock_coordinator
    ):
        """Test coordinator update with valid data."""
        test_date = date(2023, 8, 1)

        mock_coordinator.get_dog_data.return_value = {"test": "data"}

        with patch.object(
            base_date_entity, "_extract_date_from_dog_data", return_value=test_date
        ):
            base_date_entity._handle_coordinator_update()

        assert base_date_entity._current_value == test_date

    def test_handle_coordinator_update_no_data(
        self, base_date_entity, mock_coordinator
    ):
        """Test coordinator update without data."""
        mock_coordinator.get_dog_data.return_value = None

        original_value = base_date_entity._current_value
        base_date_entity._handle_coordinator_update()

        assert base_date_entity._current_value == original_value

    def test_handle_coordinator_update_same_date(
        self, base_date_entity, mock_coordinator
    ):
        """Test coordinator update with same date value."""
        test_date = date(2023, 8, 1)
        base_date_entity._current_value = test_date

        mock_coordinator.get_dog_data.return_value = {"test": "data"}

        with patch.object(
            base_date_entity, "_extract_date_from_dog_data", return_value=test_date
        ):
            base_date_entity._handle_coordinator_update()

        # Value should remain the same
        assert base_date_entity._current_value == test_date

    def test_handle_coordinator_update_with_exception(
        self, base_date_entity, mock_coordinator
    ):
        """Test coordinator update when extraction raises exception."""
        mock_coordinator.get_dog_data.side_effect = Exception("Coordinator error")

        # Should not raise exception
        base_date_entity._handle_coordinator_update()

    def test_extract_date_from_dog_data_default(self, base_date_entity):
        """Test default extract date implementation."""
        result = base_date_entity._extract_date_from_dog_data({"test": "data"})
        assert result is None


class TestPawControlBirthdateDate:
    """Test the birthdate date entity."""

    @pytest.fixture
    def birthdate_entity(self, mock_coordinator):
        """Create a birthdate entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlBirthdateDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_birthdate_entity_initialization(self, birthdate_entity):
        """Test birthdate entity initialization."""
        assert birthdate_entity._date_type == "birthdate"
        assert birthdate_entity._attr_icon == "mdi:cake"

    def test_extract_date_from_dog_data_valid(self, birthdate_entity):
        """Test extracting birthdate from valid dog data."""
        dog_data = {"profile": {"birthdate": "2020-05-15"}}

        result = birthdate_entity._extract_date_from_dog_data(dog_data)
        assert result == date(2020, 5, 15)

    def test_extract_date_from_dog_data_invalid_format(self, birthdate_entity):
        """Test extracting birthdate from invalid format."""
        dog_data = {"profile": {"birthdate": "invalid-date"}}

        result = birthdate_entity._extract_date_from_dog_data(dog_data)
        assert result is None

    def test_extract_date_from_dog_data_missing(self, birthdate_entity):
        """Test extracting birthdate when data is missing."""
        dog_data = {"profile": {}}

        result = birthdate_entity._extract_date_from_dog_data(dog_data)
        assert result is None

    def test_extract_date_from_dog_data_no_profile(self, birthdate_entity):
        """Test extracting birthdate when profile is missing."""
        dog_data = {}

        result = birthdate_entity._extract_date_from_dog_data(dog_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_async_handle_date_set_birthdate(self, birthdate_entity):
        """Test birthdate-specific handling when date is set."""
        test_date = date(2020, 5, 15)

        # Mock coordinator and data manager
        mock_data_manager = AsyncMock()

        mock_runtime_data = {"data_manager": mock_data_manager}

        birthdate_entity.coordinator.config_entry = Mock()
        birthdate_entity.coordinator.config_entry.runtime_data = mock_runtime_data

        await birthdate_entity._async_handle_date_set(test_date)

        # Should call data manager to update profile
        mock_data_manager.async_update_dog_profile.assert_called_once_with(
            "dog1", {"birthdate": "2020-05-15"}
        )

    @pytest.mark.asyncio
    async def test_async_handle_date_set_no_data_manager(self, birthdate_entity):
        """Test birthdate handling when no data manager available."""
        test_date = date(2020, 5, 15)

        birthdate_entity.coordinator.config_entry = Mock()
        birthdate_entity.coordinator.config_entry.runtime_data = None

        # Should not raise exception
        await birthdate_entity._async_handle_date_set(test_date)

    @pytest.mark.asyncio
    async def test_async_handle_date_set_data_manager_exception(self, birthdate_entity):
        """Test birthdate handling when data manager raises exception."""
        test_date = date(2020, 5, 15)

        mock_data_manager = AsyncMock()
        mock_data_manager.async_update_dog_profile.side_effect = Exception(
            "Update failed"
        )

        mock_runtime_data = {"data_manager": mock_data_manager}

        birthdate_entity.coordinator.config_entry = Mock()
        birthdate_entity.coordinator.config_entry.runtime_data = mock_runtime_data

        # Should not raise exception
        await birthdate_entity._async_handle_date_set(test_date)


class TestPawControlAdoptionDate:
    """Test the adoption date entity."""

    @pytest.fixture
    def adoption_entity(self, mock_coordinator):
        """Create an adoption date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlAdoptionDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_adoption_entity_initialization(self, adoption_entity):
        """Test adoption date entity initialization."""
        assert adoption_entity._date_type == "adoption_date"
        assert adoption_entity._attr_icon == "mdi:home-heart"

    def test_extract_date_from_dog_data_valid(self, adoption_entity):
        """Test extracting adoption date from valid dog data."""
        dog_data = {"profile": {"adoption_date": "2021-03-10"}}

        result = adoption_entity._extract_date_from_dog_data(dog_data)
        assert result == date(2021, 3, 10)

    @pytest.mark.asyncio
    async def test_async_handle_date_set_adoption(self, adoption_entity):
        """Test adoption-specific handling when date is set."""
        test_date = date(2021, 3, 10)

        # Should not raise exception (just logs)
        await adoption_entity._async_handle_date_set(test_date)


class TestPawControlLastVetVisitDate:
    """Test the last vet visit date entity."""

    @pytest.fixture
    def vet_visit_entity(self, mock_coordinator):
        """Create a last vet visit date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        coordinator.config_entry = Mock()
        return PawControlLastVetVisitDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_vet_visit_entity_initialization(self, vet_visit_entity):
        """Test vet visit entity initialization."""
        assert vet_visit_entity._date_type == "last_vet_visit"
        assert vet_visit_entity._attr_icon == "mdi:medical-bag"

    def test_extract_date_from_dog_data_datetime_string(self, vet_visit_entity):
        """Test extracting vet visit date from datetime string."""
        dog_data = {"health": {"last_vet_visit": "2023-05-15T10:30:00"}}

        result = vet_visit_entity._extract_date_from_dog_data(dog_data)
        assert result == date(2023, 5, 15)

    def test_extract_date_from_dog_data_date_string(self, vet_visit_entity):
        """Test extracting vet visit date from date string."""
        dog_data = {"health": {"last_vet_visit": "2023-05-15"}}

        result = vet_visit_entity._extract_date_from_dog_data(dog_data)
        assert result == date(2023, 5, 15)

    def test_extract_date_from_dog_data_invalid(self, vet_visit_entity):
        """Test extracting vet visit date from invalid data."""
        dog_data = {"health": {"last_vet_visit": "invalid-date"}}

        result = vet_visit_entity._extract_date_from_dog_data(dog_data)
        assert result is None

    @pytest.mark.asyncio
    async def test_async_handle_date_set_vet_visit(
        self, hass: HomeAssistant, vet_visit_entity
    ):
        """Test vet visit-specific handling when date is set."""
        vet_visit_entity.hass = hass
        test_date = date(2023, 5, 15)

        with patch.object(
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            await vet_visit_entity._async_handle_date_set(test_date)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Vet visit recorded for 2023-05-15",
                "health_status": "checked",
            },
        )

    @pytest.mark.asyncio
    async def test_async_handle_date_set_service_error(
        self, hass: HomeAssistant, vet_visit_entity
    ):
        """Test vet visit handling when service call fails."""
        vet_visit_entity.hass = hass
        test_date = date(2023, 5, 15)

        with patch.object(
            hass.services, "async_call", side_effect=Exception("Service error")
        ):
            # Should not raise exception
            await vet_visit_entity._async_handle_date_set(test_date)


class TestPawControlNextVetAppointmentDate:
    """Test the next vet appointment date entity."""

    @pytest.fixture
    def next_vet_entity(self, mock_coordinator):
        """Create a next vet appointment date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextVetAppointmentDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_next_vet_entity_initialization(self, next_vet_entity):
        """Test next vet appointment entity initialization."""
        assert next_vet_entity._date_type == "next_vet_appointment"
        assert next_vet_entity._attr_icon == "mdi:calendar-medical"

    @pytest.mark.asyncio
    async def test_async_handle_date_set_upcoming_appointment(self, next_vet_entity):
        """Test handling upcoming vet appointment."""
        today = dt_util.now().date()
        test_date = today + timedelta(days=3)

        # Should not raise exception (just logs)
        await next_vet_entity._async_handle_date_set(test_date)

    @pytest.mark.asyncio
    async def test_async_handle_date_set_far_future_appointment(self, next_vet_entity):
        """Test handling far future vet appointment."""
        today = dt_util.now().date()
        test_date = today + timedelta(days=30)

        # Should not raise exception (just logs)
        await next_vet_entity._async_handle_date_set(test_date)


class TestPawControlVaccinationDate:
    """Test the vaccination date entity."""

    @pytest.fixture
    def vaccination_entity(self, mock_coordinator):
        """Create a vaccination date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlVaccinationDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_vaccination_entity_initialization(self, vaccination_entity):
        """Test vaccination entity initialization."""
        assert vaccination_entity._date_type == "vaccination_date"
        assert vaccination_entity._attr_icon == "mdi:needle"

    @pytest.mark.asyncio
    async def test_async_handle_date_set_vaccination(
        self, hass: HomeAssistant, vaccination_entity
    ):
        """Test vaccination-specific handling when date is set."""
        vaccination_entity.hass = hass
        test_date = date(2023, 6, 20)

        with patch.object(
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            await vaccination_entity._async_handle_date_set(test_date)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Vaccination recorded for 2023-06-20",
                "health_status": "vaccinated",
            },
        )


class TestPawControlDewormingDate:
    """Test the deworming date entity."""

    @pytest.fixture
    def deworming_entity(self, mock_coordinator):
        """Create a deworming date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlDewormingDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_deworming_entity_initialization(self, deworming_entity):
        """Test deworming entity initialization."""
        assert deworming_entity._date_type == "deworming_date"
        assert deworming_entity._attr_icon == "mdi:pill"

    @pytest.mark.asyncio
    async def test_async_handle_date_set_deworming(
        self, hass: HomeAssistant, deworming_entity
    ):
        """Test deworming-specific handling when date is set."""
        deworming_entity.hass = hass
        test_date = date(2023, 7, 10)

        with patch.object(
            hass.services, "async_call", new_callable=AsyncMock
        ) as mock_service_call:
            await deworming_entity._async_handle_date_set(test_date)

        # Should call log_health_data service
        mock_service_call.assert_called_once_with(
            DOMAIN,
            "log_health_data",
            {
                ATTR_DOG_ID: "dog1",
                "note": "Deworming treatment recorded for 2023-07-10",
                "health_status": "treated",
            },
        )


class TestPawControlGroomingDate:
    """Test the grooming date entity."""

    @pytest.fixture
    def last_grooming_entity(self, mock_coordinator):
        """Create a last grooming date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlLastGroomingDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_grooming_entity(self, mock_coordinator):
        """Create a next grooming date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextGroomingDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_last_grooming_entity_initialization(self, last_grooming_entity):
        """Test last grooming entity initialization."""
        assert last_grooming_entity._date_type == "last_grooming"
        assert last_grooming_entity._attr_icon == "mdi:content-cut"

    def test_next_grooming_entity_initialization(self, next_grooming_entity):
        """Test next grooming entity initialization."""
        assert next_grooming_entity._date_type == "next_grooming"
        assert next_grooming_entity._attr_icon == "mdi:calendar-clock"

    def test_extract_date_from_dog_data_grooming(self, last_grooming_entity):
        """Test extracting grooming date from dog data."""
        dog_data = {"health": {"last_grooming": "2023-04-20T14:00:00"}}

        result = last_grooming_entity._extract_date_from_dog_data(dog_data)
        assert result == date(2023, 4, 20)


class TestPawControlDietDate:
    """Test the diet date entities."""

    @pytest.fixture
    def diet_start_entity(self, mock_coordinator):
        """Create a diet start date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlDietStartDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def diet_end_entity(self, mock_coordinator):
        """Create a diet end date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlDietEndDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_diet_start_entity_initialization(self, diet_start_entity):
        """Test diet start entity initialization."""
        assert diet_start_entity._date_type == "diet_start_date"
        assert diet_start_entity._attr_icon == "mdi:scale"

    def test_diet_end_entity_initialization(self, diet_end_entity):
        """Test diet end entity initialization."""
        assert diet_end_entity._date_type == "diet_end_date"
        assert diet_end_entity._attr_icon == "mdi:scale-off"

    @pytest.mark.asyncio
    async def test_async_handle_date_set_diet_start(self, diet_start_entity):
        """Test diet start-specific handling when date is set."""
        test_date = date(2023, 8, 1)

        # Should not raise exception (just logs)
        await diet_start_entity._async_handle_date_set(test_date)


class TestPawControlTrainingDate:
    """Test the training date entities."""

    @pytest.fixture
    def training_start_entity(self, mock_coordinator):
        """Create a training start date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlTrainingStartDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def next_training_entity(self, mock_coordinator):
        """Create a next training date entity for testing."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return PawControlNextTrainingDate(coordinator, "dog1", "Buddy")

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    def test_training_start_entity_initialization(self, training_start_entity):
        """Test training start entity initialization."""
        assert training_start_entity._date_type == "training_start_date"
        assert training_start_entity._attr_icon == "mdi:school"

    def test_next_training_entity_initialization(self, next_training_entity):
        """Test next training entity initialization."""
        assert next_training_entity._date_type == "next_training_date"
        assert next_training_entity._attr_icon == "mdi:calendar-star"

    @pytest.mark.asyncio
    async def test_async_handle_date_set_next_training(self, next_training_entity):
        """Test next training-specific handling when date is set."""
        today = dt_util.now().date()
        test_date = today + timedelta(days=5)

        # Should not raise exception (just logs)
        await next_training_entity._async_handle_date_set(test_date)


class TestDateEntityIntegrationScenarios:
    """Test date entity integration scenarios and edge cases."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    def test_coordinator_unavailable_affects_all_entities(self, mock_coordinator):
        """Test that coordinator unavailability affects all date entities."""
        mock_coordinator.available = False

        entities = [
            PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy"),
            PawControlAdoptionDate(mock_coordinator, "dog1", "Buddy"),
            PawControlLastVetVisitDate(mock_coordinator, "dog1", "Buddy"),
            PawControlVaccinationDate(mock_coordinator, "dog1", "Buddy"),
            PawControlDietStartDate(mock_coordinator, "dog1", "Buddy"),
        ]

        for entity in entities:
            assert entity.coordinator.available is False

    def test_multiple_dogs_unique_entities(self, mock_coordinator):
        """Test that multiple dogs create unique date entities."""
        dogs = [("dog1", "Buddy"), ("dog2", "Max"), ("dog3", "Luna")]

        entities = []
        for dog_id, dog_name in dogs:
            entities.append(PawControlBirthdateDate(mock_coordinator, dog_id, dog_name))
            entities.append(PawControlAdoptionDate(mock_coordinator, dog_id, dog_name))

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
        entity1 = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")
        entity2 = PawControlBirthdateDate(mock_coordinator, "dog2", "Max")

        date1 = date(2020, 5, 15)
        date2 = date(2019, 8, 22)

        entity1._current_value = date1
        entity2._current_value = date2

        # Entities should return different values
        assert entity1.native_value == date1
        assert entity2.native_value == date2

        # Attributes should be isolated
        attrs1 = entity1.extra_state_attributes
        attrs2 = entity2.extra_state_attributes

        assert attrs1[ATTR_DOG_ID] == "dog1"
        assert attrs2[ATTR_DOG_ID] == "dog2"
        assert attrs1[ATTR_DOG_NAME] == "Buddy"
        assert attrs2[ATTR_DOG_NAME] == "Max"

    def test_date_validation_edge_cases(self, mock_coordinator):
        """Test date validation with edge cases."""
        entity = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")

        # Test leap year
        leap_date = date(2020, 2, 29)
        entity._current_value = leap_date
        assert entity.native_value == leap_date

        # Test very old date
        old_date = date(1900, 1, 1)
        entity._current_value = old_date
        assert entity.native_value == old_date

        # Test far future date
        future_date = date(2100, 12, 31)
        entity._current_value = future_date
        assert entity.native_value == future_date

    @pytest.mark.asyncio
    async def test_performance_with_many_entities(self, mock_coordinator):
        """Test performance with large number of date entities."""
        import time

        start_time = time.time()

        entities = []
        for dog_num in range(10):
            dog_id = f"dog{dog_num}"
            dog_name = f"Dog{dog_num}"

            # Create all date entity types for this dog (14 entities per dog)
            entities.extend(
                [
                    PawControlBirthdateDate(mock_coordinator, dog_id, dog_name),
                    PawControlAdoptionDate(mock_coordinator, dog_id, dog_name),
                    PawControlLastVetVisitDate(mock_coordinator, dog_id, dog_name),
                    PawControlNextVetAppointmentDate(
                        mock_coordinator, dog_id, dog_name
                    ),
                    PawControlLastGroomingDate(mock_coordinator, dog_id, dog_name),
                    PawControlNextGroomingDate(mock_coordinator, dog_id, dog_name),
                    PawControlVaccinationDate(mock_coordinator, dog_id, dog_name),
                    PawControlNextVaccinationDate(mock_coordinator, dog_id, dog_name),
                    PawControlDewormingDate(mock_coordinator, dog_id, dog_name),
                    PawControlNextDewormingDate(mock_coordinator, dog_id, dog_name),
                    PawControlDietStartDate(mock_coordinator, dog_id, dog_name),
                    PawControlDietEndDate(mock_coordinator, dog_id, dog_name),
                    PawControlTrainingStartDate(mock_coordinator, dog_id, dog_name),
                    PawControlNextTrainingDate(mock_coordinator, dog_id, dog_name),
                ]
            )

        creation_time = time.time() - start_time

        # Should create 140 entities quickly (under 1 second)
        assert len(entities) == 140
        assert creation_time < 1.0

        # Test that all entities have unique IDs
        unique_ids = [entity._attr_unique_id for entity in entities]
        assert len(unique_ids) == len(set(unique_ids))

    def test_error_handling_malformed_coordinator_data(self, mock_coordinator):
        """Test error handling with malformed coordinator data."""
        # Mock malformed data that could cause exceptions
        mock_coordinator.get_dog_data.return_value = {
            "invalid_structure": "malformed",
            "health": {"last_vet_visit": "not-a-date"},
        }

        entity = PawControlLastVetVisitDate(mock_coordinator, "dog1", "Buddy")

        # Should not raise exception and return None for invalid data
        try:
            result = entity._extract_date_from_dog_data(mock_coordinator.get_dog_data())
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
        entity = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")
        entity.hass = hass
        entity.entity_id = "date.buddy_birthdate"

        # Test various state restoration scenarios
        test_cases = [
            ("2020-05-15", date(2020, 5, 15)),  # Valid date
            ("unknown", None),  # Unknown state
            ("unavailable", None),  # Unavailable state
            ("", None),  # Empty string
            ("invalid-format", None),  # Invalid format
        ]

        for state_value, expected_result in test_cases:
            mock_state = Mock()
            mock_state.state = state_value

            with patch.object(entity, "async_get_last_state", return_value=mock_state):
                entity._current_value = None  # Reset
                await entity.async_added_to_hass()

                assert entity._current_value == expected_result

    @pytest.mark.asyncio
    async def test_service_integration_comprehensive(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive service integration scenarios."""
        entities_with_services = [
            (
                PawControlLastVetVisitDate(mock_coordinator, "dog1", "Buddy"),
                "log_health_data",
            ),
            (
                PawControlVaccinationDate(mock_coordinator, "dog1", "Buddy"),
                "log_health_data",
            ),
            (
                PawControlDewormingDate(mock_coordinator, "dog1", "Buddy"),
                "log_health_data",
            ),
        ]

        for entity, expected_service in entities_with_services:
            entity.hass = hass
            test_date = date(2023, 6, 15)

            with patch.object(
                hass.services, "async_call", new_callable=AsyncMock
            ) as mock_service_call:
                await entity._async_handle_date_set(test_date)

            # Each entity should call its expected service
            mock_service_call.assert_called_once()
            args, _kwargs = mock_service_call.call_args
            assert args[0] == DOMAIN
            assert args[1] == expected_service

    @pytest.mark.asyncio
    async def test_exception_handling_in_async_set_value(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test comprehensive exception handling in async_set_value."""
        entity = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")
        entity.hass = hass

        # Test with None value
        with pytest.raises(ValidationError):
            await entity.async_set_value(None)

        # Test with string value
        with pytest.raises(ValidationError):
            await entity.async_set_value("2023-06-15")

        # Test with integer value
        with pytest.raises(ValidationError):
            await entity.async_set_value(20230615)

        # Test with datetime object (should fail for date entity)
        from datetime import datetime

        with pytest.raises(ValidationError):
            await entity.async_set_value(datetime(2023, 6, 15))

    def test_coordinator_data_extraction_edge_cases(self, mock_coordinator):
        """Test coordinator data extraction with various edge cases."""
        entity = PawControlLastVetVisitDate(mock_coordinator, "dog1", "Buddy")

        edge_cases = [
            ({}, None),  # Empty dict
            ({"health": {}}, None),  # Empty health dict
            ({"health": {"last_vet_visit": None}}, None),  # None value
            ({"health": {"last_vet_visit": ""}}, None),  # Empty string
            ({"health": {"other_field": "value"}}, None),  # Missing field
            ({"health": {"last_vet_visit": "2023-13-40"}}, None),  # Invalid date
            # Invalid leap year
            ({"health": {"last_vet_visit": "2023-02-29"}}, None),
        ]

        for dog_data, expected_result in edge_cases:
            result = entity._extract_date_from_dog_data(dog_data)
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_async_added_to_hass_exception_handling(
        self, hass: HomeAssistant, mock_coordinator
    ):
        """Test exception handling in async_added_to_hass."""
        entity = PawControlBirthdateDate(mock_coordinator, "dog1", "Buddy")
        entity.hass = hass
        entity.entity_id = "date.buddy_birthdate"

        # Mock async_get_last_state to raise exception
        with patch.object(
            entity, "async_get_last_state", side_effect=Exception("State error")
        ):
            # Should not raise exception
            await entity.async_added_to_hass()

        # Should still have None value
        assert entity._current_value is None
