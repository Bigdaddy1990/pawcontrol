"""Comprehensive tests for Paw Control text platform.

Tests all text entities, batching logic, service integration,
state persistence, and availability conditions.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from custom_components.pawcontrol.const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.text import (
    PawControlAllergiesText,
    PawControlBehaviorNotesText,
    PawControlBreederInfoText,
    PawControlCurrentWalkLabelText,
    PawControlCustomLabelText,
    PawControlCustomMessageText,
    PawControlDogNotesText,
    PawControlEmergencyContactText,
    PawControlGroomingNotesText,
    PawControlHealthNotesText,
    PawControlInsuranceText,
    PawControlLocationDescriptionText,
    PawControlMedicationNotesText,
    PawControlMicrochipText,
    PawControlRegistrationText,
    PawControlTextBase,
    PawControlTrainingNotesText,
    PawControlVetNotesText,
    PawControlWalkNotesText,
    _async_add_entities_in_batches,
    async_setup_entry,
)
from homeassistant.components.text import TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


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
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                },
                {
                    CONF_DOG_ID: "simple_dog",
                    CONF_DOG_NAME: "Simple Dog",
                    "modules": {
                        MODULE_WALK: False,
                        MODULE_HEALTH: False,
                        MODULE_NOTIFICATIONS: False,
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

        # First dog with all modules: 2 base + 2 walk + 4 health + 2 notifications = 10
        # Second dog with no modules: 2 base = 2
        # Total: 12 entities
        assert total_entities == 12

    @pytest.mark.asyncio
    async def test_async_setup_entry_with_legacy_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ):
        """Test setup with legacy hass.data."""
        # Setup legacy data structure
        mock_entry.runtime_data = None
        hass.data[DOMAIN] = {"test_entry": {"coordinator": mock_coordinator}}

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
                    CONF_DOG_ID: "health_only_dog",
                    CONF_DOG_NAME: "Health Only Dog",
                    "modules": {MODULE_HEALTH: True},  # Only health enabled
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

        # Should have base texts (2) + health texts (4) = 6 entities
        assert total_entities == 6


class TestBatchingFunction:
    """Test the batching helper function."""

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_single_batch(self):
        """Test batching with entities that fit in single batch."""
        async_add_entities_func = AsyncMock()
        entities = [Mock() for _ in range(5)]

        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=8
        )

        # Should call once with all entities
        async_add_entities_func.assert_called_once_with(
            entities, update_before_add=False
        )

    @pytest.mark.asyncio
    async def test_async_add_entities_in_batches_multiple_batches(self):
        """Test batching with entities requiring multiple batches."""
        async_add_entities_func = AsyncMock()
        entities = [Mock() for _ in range(20)]

        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=8
        )

        # Should call 3 times (8 + 8 + 4)
        assert async_add_entities_func.call_count == 3

        # Verify batch sizes
        call_args = async_add_entities_func.call_args_list
        assert len(call_args[0][0][0]) == 8  # First batch
        assert len(call_args[1][0][0]) == 8  # Second batch
        assert len(call_args[2][0][0]) == 4  # Third batch

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
        entities = [Mock() for _ in range(12)]

        # Use very small delay for testing
        start_time = asyncio.get_event_loop().time()
        await _async_add_entities_in_batches(
            async_add_entities_func, entities, batch_size=6, delay_between_batches=0.01
        )
        end_time = asyncio.get_event_loop().time()

        # Should have taken at least one delay period
        assert end_time - start_time >= 0.01
        assert async_add_entities_func.call_count == 2


class TestPawControlTextBase:
    """Test the base text class."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.fixture
    def base_text(self, mock_coordinator):
        """Create a base text instance."""
        return PawControlTextBase(
            mock_coordinator,
            "test_dog",
            "Test Dog",
            "test_text",
            max_length=100,
            mode=TextMode.TEXT,
        )

    def test_text_initialization(self, base_text):
        """Test text initialization."""
        assert base_text._dog_id == "test_dog"
        assert base_text._dog_name == "Test Dog"
        assert base_text._text_type == "test_text"
        assert base_text._current_value == ""

        # Check attributes
        assert base_text._attr_unique_id == "pawcontrol_test_dog_test_text"
        assert base_text._attr_name == "Test Dog Test Text"
        assert base_text._attr_native_max == 100
        assert base_text._attr_mode == TextMode.TEXT

    def test_device_info(self, base_text):
        """Test device info configuration."""
        device_info = base_text._attr_device_info

        assert device_info["identifiers"] == {(DOMAIN, "test_dog")}
        assert device_info["name"] == "Test Dog"
        assert device_info["manufacturer"] == "Paw Control"
        assert device_info["model"] == "Smart Dog"
        assert "configuration_url" in device_info

    def test_native_value(self, base_text):
        """Test native value property."""
        assert base_text.native_value == ""

        # Change value
        base_text._current_value = "Test Value"
        assert base_text.native_value == "Test Value"

    def test_extra_state_attributes(self, base_text):
        """Test extra state attributes."""
        base_text._current_value = "Test Content"
        attrs = base_text.extra_state_attributes

        assert attrs[ATTR_DOG_ID] == "test_dog"
        assert attrs[ATTR_DOG_NAME] == "Test Dog"
        assert attrs["text_type"] == "test_text"
        assert attrs["character_count"] == 12

    @pytest.mark.asyncio
    async def test_async_added_to_hass_with_restore(self, base_text):
        """Test async_added_to_hass with state restoration."""
        # Mock last state
        mock_state = Mock()
        mock_state.state = "Restored Value"

        with patch.object(base_text, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state

            await base_text.async_added_to_hass()

            # Should restore the value
            assert base_text._current_value == "Restored Value"

    @pytest.mark.asyncio
    async def test_async_added_to_hass_no_restore(self, base_text):
        """Test async_added_to_hass with no previous state."""
        with patch.object(base_text, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = None

            await base_text.async_added_to_hass()

            # Should keep empty value
            assert base_text._current_value == ""

    @pytest.mark.asyncio
    async def test_async_added_to_hass_unknown_state(self, base_text):
        """Test async_added_to_hass with unknown previous state."""
        mock_state = Mock()
        mock_state.state = "unknown"

        with patch.object(base_text, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state

            await base_text.async_added_to_hass()

            # Should keep empty value
            assert base_text._current_value == ""

    @pytest.mark.asyncio
    async def test_async_set_value_normal(self, base_text):
        """Test setting normal value."""
        with patch.object(base_text, "async_write_ha_state") as mock_write:
            await base_text.async_set_value("Test Value")

            assert base_text._current_value == "Test Value"
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_set_value_too_long(self, base_text):
        """Test setting value that exceeds max length."""
        long_value = "A" * 150  # Longer than max_length of 100

        with patch.object(base_text, "async_write_ha_state") as mock_write:
            await base_text.async_set_value(long_value)

            # Should be truncated to max length
            assert base_text._current_value == "A" * 100
            assert len(base_text._current_value) == 100
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_set_value_empty(self, base_text):
        """Test setting empty value."""
        with patch.object(base_text, "async_write_ha_state") as mock_write:
            await base_text.async_set_value("")

            assert base_text._current_value == ""
            mock_write.assert_called_once()


class TestDogNotesText:
    """Test the dog notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def dog_notes_text(self, mock_coordinator):
        """Create a dog notes text."""
        return PawControlDogNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, dog_notes_text):
        """Test dog notes text initialization."""
        assert dog_notes_text._text_type == "notes"
        assert dog_notes_text._attr_native_max == 1000
        assert dog_notes_text._attr_mode == TextMode.TEXT
        assert dog_notes_text._attr_icon == "mdi:note-text"

    @pytest.mark.asyncio
    async def test_async_set_value_meaningful_content(self, dog_notes_text, mock_hass):
        """Test setting meaningful notes content."""
        dog_notes_text.hass = mock_hass
        meaningful_content = "Dog seems very happy today and played well in the park"

        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value(meaningful_content)

            # Should log health data for meaningful content
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: "test_dog",
                    "note": f"Notes updated: {meaningful_content[:100]}",
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_short_content(self, dog_notes_text, mock_hass):
        """Test setting short notes content."""
        dog_notes_text.hass = mock_hass
        short_content = "Good"

        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value(short_content)

            # Should not log health data for short content
            mock_hass.services.async_call.assert_not_called()


class TestCustomLabelText:
    """Test the custom label text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def custom_label_text(self, mock_coordinator):
        """Create a custom label text."""
        return PawControlCustomLabelText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, custom_label_text):
        """Test custom label text initialization."""
        assert custom_label_text._text_type == "custom_label"
        assert custom_label_text._attr_native_max == 50
        assert custom_label_text._attr_icon == "mdi:label"

    @pytest.mark.asyncio
    async def test_async_set_value(self, custom_label_text):
        """Test setting custom label value."""
        with patch.object(custom_label_text, "async_write_ha_state"):
            await custom_label_text.async_set_value("Good Boy")

            assert custom_label_text._current_value == "Good Boy"


class TestWalkNotesText:
    """Test the walk notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.get_dog_data.return_value = {"walk": {"walk_in_progress": True}}
        return coordinator

    @pytest.fixture
    def walk_notes_text(self, mock_coordinator):
        """Create a walk notes text."""
        return PawControlWalkNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, walk_notes_text):
        """Test walk notes text initialization."""
        assert walk_notes_text._text_type == "walk_notes"
        assert walk_notes_text._attr_native_max == 500
        assert walk_notes_text._attr_mode == TextMode.TEXT
        assert walk_notes_text._attr_icon == "mdi:walk"

    @pytest.mark.asyncio
    async def test_async_set_value_during_walk(self, walk_notes_text, mock_coordinator):
        """Test setting walk notes during active walk."""
        with patch.object(walk_notes_text, "async_write_ha_state"):
            await walk_notes_text.async_set_value("Great walk in the park")

            # Should call get_dog_data to check for active walk
            mock_coordinator.get_dog_data.assert_called_with("test_dog")

    @pytest.mark.asyncio
    async def test_async_set_value_no_active_walk(
        self, walk_notes_text, mock_coordinator
    ):
        """Test setting walk notes with no active walk."""
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": False}
        }

        with patch.object(walk_notes_text, "async_write_ha_state"):
            await walk_notes_text.async_set_value("Notes for future walk")

            # Should still set the value
            assert walk_notes_text._current_value == "Notes for future walk"


class TestCurrentWalkLabelText:
    """Test the current walk label text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        return coordinator

    @pytest.fixture
    def current_walk_label_text(self, mock_coordinator):
        """Create a current walk label text."""
        return PawControlCurrentWalkLabelText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, current_walk_label_text):
        """Test current walk label text initialization."""
        assert current_walk_label_text._text_type == "current_walk_label"
        assert current_walk_label_text._attr_native_max == 100
        assert current_walk_label_text._attr_icon == "mdi:tag"

    def test_available_walk_in_progress(
        self, current_walk_label_text, mock_coordinator
    ):
        """Test availability when walk is in progress."""
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": True}
        }

        assert current_walk_label_text.available is True

    def test_available_no_walk(self, current_walk_label_text, mock_coordinator):
        """Test availability when no walk is in progress."""
        mock_coordinator.get_dog_data.return_value = {
            "walk": {"walk_in_progress": False}
        }

        assert current_walk_label_text.available is False

    def test_available_no_dog_data(self, current_walk_label_text, mock_coordinator):
        """Test availability when no dog data."""
        mock_coordinator.get_dog_data.return_value = None

        assert current_walk_label_text.available is False


class TestHealthNotesText:
    """Test the health notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def health_notes_text(self, mock_coordinator):
        """Create a health notes text."""
        return PawControlHealthNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, health_notes_text):
        """Test health notes text initialization."""
        assert health_notes_text._text_type == "health_notes"
        assert health_notes_text._attr_native_max == 1000
        assert health_notes_text._attr_mode == TextMode.TEXT
        assert health_notes_text._attr_icon == "mdi:heart-pulse"

    @pytest.mark.asyncio
    async def test_async_set_value_with_content(self, health_notes_text, mock_hass):
        """Test setting health notes with content."""
        health_notes_text.hass = mock_hass
        health_content = "Dog has slight limp on left paw"

        with patch.object(health_notes_text, "async_write_ha_state"):
            await health_notes_text.async_set_value(health_content)

            # Should log health data
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: "test_dog",
                    "note": health_content,
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_empty_content(self, health_notes_text, mock_hass):
        """Test setting health notes with empty content."""
        health_notes_text.hass = mock_hass

        with patch.object(health_notes_text, "async_write_ha_state"):
            await health_notes_text.async_set_value("")

            # Should not log health data for empty content
            mock_hass.services.async_call.assert_not_called()


class TestMedicationNotesText:
    """Test the medication notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def medication_notes_text(self, mock_coordinator):
        """Create a medication notes text."""
        return PawControlMedicationNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, medication_notes_text):
        """Test medication notes text initialization."""
        assert medication_notes_text._text_type == "medication_notes"
        assert medication_notes_text._attr_native_max == 500
        assert medication_notes_text._attr_mode == TextMode.TEXT
        assert medication_notes_text._attr_icon == "mdi:pill"

    @pytest.mark.asyncio
    async def test_async_set_value_meaningful_medication(
        self, medication_notes_text, mock_hass
    ):
        """Test setting meaningful medication notes."""
        medication_notes_text.hass = mock_hass
        medication_content = "Gave arthritis medication 5mg"

        with patch.object(medication_notes_text, "async_write_ha_state"):
            await medication_notes_text.async_set_value(medication_content)

            # Should log medication
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_medication",
                {
                    ATTR_DOG_ID: "test_dog",
                    "medication_name": "Manual Entry",
                    "dose": medication_content,
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_short_content(
        self, medication_notes_text, mock_hass
    ):
        """Test setting short medication notes."""
        medication_notes_text.hass = mock_hass

        with patch.object(medication_notes_text, "async_write_ha_state"):
            await medication_notes_text.async_set_value("5mg")

            # Should not log medication for very short content
            mock_hass.services.async_call.assert_not_called()


class TestVetNotesText:
    """Test the vet notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def vet_notes_text(self, mock_coordinator):
        """Create a vet notes text."""
        return PawControlVetNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, vet_notes_text):
        """Test vet notes text initialization."""
        assert vet_notes_text._text_type == "vet_notes"
        assert vet_notes_text._attr_native_max == 1000
        assert vet_notes_text._attr_mode == TextMode.TEXT
        assert vet_notes_text._attr_icon == "mdi:medical-bag"

    @pytest.mark.asyncio
    async def test_async_set_value_with_content(self, vet_notes_text, mock_hass):
        """Test setting vet notes with content."""
        vet_notes_text.hass = mock_hass
        vet_content = "Annual checkup - all good, recommended dental cleaning"

        with patch.object(vet_notes_text, "async_write_ha_state"):
            await vet_notes_text.async_set_value(vet_content)

            # Should log health data with vet context
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: "test_dog",
                    "note": f"Vet notes: {vet_content}",
                },
            )


class TestGroomingNotesText:
    """Test the grooming notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def grooming_notes_text(self, mock_coordinator):
        """Create a grooming notes text."""
        return PawControlGroomingNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, grooming_notes_text):
        """Test grooming notes text initialization."""
        assert grooming_notes_text._text_type == "grooming_notes"
        assert grooming_notes_text._attr_native_max == 500
        assert grooming_notes_text._attr_mode == TextMode.TEXT
        assert grooming_notes_text._attr_icon == "mdi:content-cut"

    @pytest.mark.asyncio
    async def test_async_set_value_meaningful_content(
        self, grooming_notes_text, mock_hass
    ):
        """Test setting meaningful grooming notes."""
        grooming_notes_text.hass = mock_hass
        grooming_content = "Full grooming session - brushed, bathed, nails trimmed"

        with patch.object(grooming_notes_text, "async_write_ha_state"):
            await grooming_notes_text.async_set_value(grooming_content)

            # Should start grooming session for meaningful content
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "start_grooming",
                {
                    ATTR_DOG_ID: "test_dog",
                    "type": "brush",
                    "notes": grooming_content,
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_short_content(self, grooming_notes_text, mock_hass):
        """Test setting short grooming notes."""
        grooming_notes_text.hass = mock_hass

        with patch.object(grooming_notes_text, "async_write_ha_state"):
            await grooming_notes_text.async_set_value("Brushed")

            # Should not start grooming session for short content
            mock_hass.services.async_call.assert_not_called()


class TestCustomMessageText:
    """Test the custom message text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def custom_message_text(self, mock_coordinator):
        """Create a custom message text."""
        return PawControlCustomMessageText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, custom_message_text):
        """Test custom message text initialization."""
        assert custom_message_text._text_type == "custom_message"
        assert custom_message_text._attr_native_max == 300
        assert custom_message_text._attr_mode == TextMode.TEXT
        assert custom_message_text._attr_icon == "mdi:message-text"

    @pytest.mark.asyncio
    async def test_async_set_value_with_message(self, custom_message_text, mock_hass):
        """Test setting custom message."""
        custom_message_text.hass = mock_hass
        message = "Dog is at the park with friends"

        with patch.object(custom_message_text, "async_write_ha_state"):
            await custom_message_text.async_set_value(message)

            # Should send notification
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "notify_test",
                {
                    ATTR_DOG_ID: "test_dog",
                    "message": message,
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_empty_message(self, custom_message_text, mock_hass):
        """Test setting empty custom message."""
        custom_message_text.hass = mock_hass

        with patch.object(custom_message_text, "async_write_ha_state"):
            await custom_message_text.async_set_value("")

            # Should not send notification for empty message
            mock_hass.services.async_call.assert_not_called()


class TestEmergencyContactText:
    """Test the emergency contact text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def emergency_contact_text(self, mock_coordinator):
        """Create an emergency contact text."""
        return PawControlEmergencyContactText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, emergency_contact_text):
        """Test emergency contact text initialization."""
        assert emergency_contact_text._text_type == "emergency_contact"
        assert emergency_contact_text._attr_native_max == 200
        assert emergency_contact_text._attr_mode == TextMode.TEXT
        assert emergency_contact_text._attr_icon == "mdi:phone-alert"

    @pytest.mark.asyncio
    async def test_async_set_value(self, emergency_contact_text):
        """Test setting emergency contact value."""
        with patch.object(emergency_contact_text, "async_write_ha_state"):
            await emergency_contact_text.async_set_value("Emergency Vet: 555-1234")

            assert emergency_contact_text._current_value == "Emergency Vet: 555-1234"


class TestMicrochipText:
    """Test the microchip text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def microchip_text(self, mock_coordinator):
        """Create a microchip text."""
        return PawControlMicrochipText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, microchip_text):
        """Test microchip text initialization."""
        assert microchip_text._text_type == "microchip"
        assert microchip_text._attr_native_max == 20
        assert microchip_text._attr_mode == TextMode.PASSWORD  # Should be hidden
        assert microchip_text._attr_icon == "mdi:chip"

    @pytest.mark.asyncio
    async def test_async_set_value(self, microchip_text):
        """Test setting microchip value."""
        with patch.object(microchip_text, "async_write_ha_state"):
            await microchip_text.async_set_value("123456789012345")

            assert microchip_text._current_value == "123456789012345"


class TestAllergiesText:
    """Test the allergies text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def allergies_text(self, mock_coordinator):
        """Create an allergies text."""
        return PawControlAllergiesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, allergies_text):
        """Test allergies text initialization."""
        assert allergies_text._text_type == "allergies"
        assert allergies_text._attr_native_max == 500
        assert allergies_text._attr_mode == TextMode.TEXT
        assert allergies_text._attr_icon == "mdi:alert-circle"

    @pytest.mark.asyncio
    async def test_async_set_value_with_allergies(self, allergies_text, mock_hass):
        """Test setting allergies information."""
        allergies_text.hass = mock_hass
        allergies_content = "Allergic to chicken and beef - fish only diet"

        with patch.object(allergies_text, "async_write_ha_state"):
            await allergies_text.async_set_value(allergies_content)

            # Should log allergies as health data
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: "test_dog",
                    "note": f"Allergies/Restrictions updated: {allergies_content}",
                },
            )


class TestBehaviorNotesText:
    """Test the behavior notes text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        return Mock(spec=PawControlCoordinator)

    @pytest.fixture
    def mock_hass(self):
        """Create a mock hass instance."""
        hass = Mock()
        hass.services = Mock()
        hass.services.async_call = AsyncMock()
        return hass

    @pytest.fixture
    def behavior_notes_text(self, mock_coordinator):
        """Create a behavior notes text."""
        return PawControlBehaviorNotesText(mock_coordinator, "test_dog", "Test Dog")

    def test_initialization(self, behavior_notes_text):
        """Test behavior notes text initialization."""
        assert behavior_notes_text._text_type == "behavior_notes"
        assert behavior_notes_text._attr_native_max == 1000
        assert behavior_notes_text._attr_mode == TextMode.TEXT
        assert behavior_notes_text._attr_icon == "mdi:emoticon-happy"

    @pytest.mark.asyncio
    async def test_async_set_value_meaningful_behavior(
        self, behavior_notes_text, mock_hass
    ):
        """Test setting meaningful behavior notes."""
        behavior_notes_text.hass = mock_hass
        behavior_content = "Dog has been more anxious lately during thunderstorms"

        with patch.object(behavior_notes_text, "async_write_ha_state"):
            await behavior_notes_text.async_set_value(behavior_content)

            # Should log behavior changes as health data
            mock_hass.services.async_call.assert_called_once_with(
                DOMAIN,
                "log_health_data",
                {
                    ATTR_DOG_ID: "test_dog",
                    "note": f"Behavior notes: {behavior_content}",
                },
            )

    @pytest.mark.asyncio
    async def test_async_set_value_short_content(self, behavior_notes_text, mock_hass):
        """Test setting short behavior notes."""
        behavior_notes_text.hass = mock_hass

        with patch.object(behavior_notes_text, "async_write_ha_state"):
            await behavior_notes_text.async_set_value("Good")

            # Should not log health data for short content
            mock_hass.services.async_call.assert_not_called()


class TestLocationDescriptionText:
    """Test the location description text entity."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.get_dog_info.return_value = {"modules": {"gps": True}}
        return coordinator

    @pytest.fixture
    def location_description_text(self, mock_coordinator):
        """Create a location description text."""
        return PawControlLocationDescriptionText(
            mock_coordinator, "test_dog", "Test Dog"
        )

    def test_initialization(self, location_description_text):
        """Test location description text initialization."""
        assert location_description_text._text_type == "location_description"
        assert location_description_text._attr_native_max == 200
        assert location_description_text._attr_mode == TextMode.TEXT
        assert location_description_text._attr_icon == "mdi:map-marker-outline"

    def test_available_with_gps_module(
        self, location_description_text, mock_coordinator
    ):
        """Test availability when GPS module is enabled."""
        mock_coordinator.get_dog_data.return_value = {"test": "data"}

        assert location_description_text.available is True

    def test_available_without_gps_module(
        self, location_description_text, mock_coordinator
    ):
        """Test availability when GPS module is disabled."""
        mock_coordinator.get_dog_data.return_value = {"test": "data"}
        mock_coordinator.get_dog_info.return_value = {"modules": {"gps": False}}

        assert location_description_text.available is False

    def test_available_no_dog_info(self, location_description_text, mock_coordinator):
        """Test availability when no dog info."""
        mock_coordinator.get_dog_data.return_value = {"test": "data"}
        mock_coordinator.get_dog_info.return_value = None

        assert location_description_text.available is False

    def test_available_no_dog_data(self, location_description_text, mock_coordinator):
        """Test availability when no dog data."""
        mock_coordinator.get_dog_data.return_value = None

        assert location_description_text.available is False


class TestTextIntegration:
    """Test text integration scenarios."""

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
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
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

        # Should have 2 base + 2 walk + 4 health + 2 notifications = 10 entities
        assert total_entities == 10

    def test_text_uniqueness(self):
        """Test that texts have unique IDs."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create multiple texts for the same dog
        texts = [
            PawControlDogNotesText(coordinator, "test_dog", "Test Dog"),
            PawControlCustomLabelText(coordinator, "test_dog", "Test Dog"),
            PawControlWalkNotesText(coordinator, "test_dog", "Test Dog"),
            PawControlHealthNotesText(coordinator, "test_dog", "Test Dog"),
        ]

        unique_ids = [text._attr_unique_id for text in texts]

        # All unique IDs should be different
        assert len(unique_ids) == len(set(unique_ids))

    def test_text_device_grouping(self):
        """Test that texts are properly grouped by device."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Create texts for two different dogs
        dog1_text = PawControlDogNotesText(coordinator, "dog1", "Dog 1")
        dog2_text = PawControlDogNotesText(coordinator, "dog2", "Dog 2")

        # Check device info
        dog1_device = dog1_text._attr_device_info
        dog2_device = dog2_text._attr_device_info

        assert dog1_device["identifiers"] == {(DOMAIN, "dog1")}
        assert dog2_device["identifiers"] == {(DOMAIN, "dog2")}
        assert dog1_device["name"] == "Dog 1"
        assert dog2_device["name"] == "Dog 2"

    @pytest.mark.asyncio
    async def test_text_value_persistence(self):
        """Test text value persistence across restarts."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        dog_notes_text = PawControlDogNotesText(coordinator, "test_dog", "Test Dog")

        # Set a value
        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value("Important notes")

        assert dog_notes_text.native_value == "Important notes"

        # Simulate restart with state restoration
        mock_state = Mock()
        mock_state.state = "Restored notes"

        with patch.object(dog_notes_text, "async_get_last_state") as mock_get_state:
            mock_get_state.return_value = mock_state
            await dog_notes_text.async_added_to_hass()

        # Should restore the persisted value
        assert dog_notes_text.native_value == "Restored notes"


class TestTextErrorHandling:
    """Test text error handling scenarios."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True
        return coordinator

    @pytest.mark.asyncio
    async def test_text_max_length_edge_cases(self, mock_coordinator):
        """Test text max length handling at boundaries."""
        dog_notes_text = PawControlDogNotesText(
            mock_coordinator, "test_dog", "Test Dog"
        )

        # Test exact max length
        max_content = "A" * 1000  # Exact max length
        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value(max_content)

        assert dog_notes_text._current_value == max_content
        assert len(dog_notes_text._current_value) == 1000

        # Test over max length
        over_max_content = "A" * 1200  # Over max length
        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value(over_max_content)

        # Should be truncated
        assert len(dog_notes_text._current_value) == 1000
        assert dog_notes_text._current_value == "A" * 1000

    @pytest.mark.asyncio
    async def test_text_unicode_handling(self, mock_coordinator):
        """Test text handling with unicode characters."""
        dog_notes_text = PawControlDogNotesText(
            mock_coordinator, "test_dog", "Test Dog"
        )

        unicode_content = "Dog is très bien! 🐕 ❤️ 中文测试"
        with patch.object(dog_notes_text, "async_write_ha_state"):
            await dog_notes_text.async_set_value(unicode_content)

        assert dog_notes_text._current_value == unicode_content

    def test_text_character_count_accuracy(self, mock_coordinator):
        """Test character count accuracy in extra attributes."""
        dog_notes_text = PawControlDogNotesText(
            mock_coordinator, "test_dog", "Test Dog"
        )

        # Test various content lengths
        test_cases = ["", "Short", "Medium length content", "A" * 100]

        for content in test_cases:
            dog_notes_text._current_value = content
            attrs = dog_notes_text.extra_state_attributes

            assert attrs["character_count"] == len(content)

    @pytest.mark.asyncio
    async def test_service_call_failures(self, mock_coordinator):
        """Test behavior when service calls fail."""
        mock_hass = Mock()
        mock_hass.services = Mock()
        mock_hass.services.async_call = AsyncMock(
            side_effect=Exception("Service error")
        )

        health_notes_text = PawControlHealthNotesText(
            mock_coordinator, "test_dog", "Test Dog"
        )
        health_notes_text.hass = mock_hass

        # Should not raise exception even if service call fails
        with patch.object(health_notes_text, "async_write_ha_state"):
            await health_notes_text.async_set_value("Health notes")

        # Value should still be set
        assert health_notes_text._current_value == "Health notes"


class TestTextConstants:
    """Test text constants and configurations."""

    def test_text_mode_constants(self):
        """Test that text modes are properly set."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Most texts should use TEXT mode
        dog_notes = PawControlDogNotesText(coordinator, "test_dog", "Test Dog")
        assert dog_notes._attr_mode == TextMode.TEXT

        # Microchip should use PASSWORD mode for privacy
        microchip = PawControlMicrochipText(coordinator, "test_dog", "Test Dog")
        assert microchip._attr_mode == TextMode.PASSWORD

    def test_text_max_lengths_reasonable(self):
        """Test that max lengths are reasonable for content types."""
        coordinator = Mock(spec=PawControlCoordinator)

        # Short texts
        custom_label = PawControlCustomLabelText(coordinator, "test_dog", "Test Dog")
        assert custom_label._attr_native_max == 50

        # Medium texts
        walk_notes = PawControlWalkNotesText(coordinator, "test_dog", "Test Dog")
        assert walk_notes._attr_native_max == 500

        # Long texts
        dog_notes = PawControlDogNotesText(coordinator, "test_dog", "Test Dog")
        assert dog_notes._attr_native_max == 1000

        # Very short texts
        microchip = PawControlMicrochipText(coordinator, "test_dog", "Test Dog")
        assert microchip._attr_native_max == 20

    def test_text_icons_appropriate(self):
        """Test that text entities have appropriate icons."""
        coordinator = Mock(spec=PawControlCoordinator)

        icon_tests = [
            (PawControlDogNotesText, "mdi:note-text"),
            (PawControlCustomLabelText, "mdi:label"),
            (PawControlWalkNotesText, "mdi:walk"),
            (PawControlHealthNotesText, "mdi:heart-pulse"),
            (PawControlMedicationNotesText, "mdi:pill"),
            (PawControlVetNotesText, "mdi:medical-bag"),
            (PawControlGroomingNotesText, "mdi:content-cut"),
            (PawControlCustomMessageText, "mdi:message-text"),
            (PawControlEmergencyContactText, "mdi:phone-alert"),
            (PawControlMicrochipText, "mdi:chip"),
            (PawControlAllergiesText, "mdi:alert-circle"),
        ]

        for text_class, expected_icon in icon_tests:
            text_entity = text_class(coordinator, "test_dog", "Test Dog")
            assert text_entity._attr_icon == expected_icon


class TestTextPerformance:
    """Test text performance scenarios."""

    @pytest.mark.asyncio
    async def test_batching_performance_large_setup(self, hass: HomeAssistant):
        """Test batching performance with many dogs."""
        coordinator = Mock(spec=PawControlCoordinator)
        coordinator.available = True

        # Create many dogs to test batching
        dogs = []
        for i in range(8):  # 8 dogs with all modules
            dogs.append(
                {
                    CONF_DOG_ID: f"dog_{i}",
                    CONF_DOG_NAME: f"Dog {i}",
                    "modules": {
                        MODULE_WALK: True,
                        MODULE_HEALTH: True,
                        MODULE_NOTIFICATIONS: True,
                    },
                }
            )

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

        # Total entities should be 8 dogs * 10 entities each = 80
        total_entities = sum(
            len(call[0][0]) for call in async_add_entities.call_args_list
        )
        assert total_entities == 80

    def test_text_memory_efficiency(self):
        """Test that texts don't store unnecessary data."""
        coordinator = Mock(spec=PawControlCoordinator)

        dog_notes_text = PawControlDogNotesText(coordinator, "test_dog", "Test Dog")

        # Check that only essential attributes are stored
        essential_attrs = {
            "_dog_id",
            "_dog_name",
            "_text_type",
            "_current_value",
            "_attr_unique_id",
            "_attr_name",
            "_attr_native_max",
            "_attr_mode",
            "_attr_icon",
            "_attr_device_info",
        }

        # Get all attributes that don't start with '__'
        actual_attrs = {
            attr
            for attr in dir(dog_notes_text)
            if not attr.startswith("__") and hasattr(dog_notes_text, attr)
        }

        # Most attributes should be essential or inherited
        non_essential = actual_attrs - essential_attrs

        # Filter out inherited methods and properties
        non_essential = {
            attr
            for attr in non_essential
            if not callable(getattr(dog_notes_text, attr, None))
            and not attr.startswith("_attr_")
            and attr not in ["coordinator", "registry_entry", "platform", "hass"]
        }

        # Should have minimal non-essential attributes
        assert len(non_essential) < 10
