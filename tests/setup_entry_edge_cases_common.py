"""Common tests for async_setup_entry edge cases."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
)
from homeassistant.core import HomeAssistant


class SetupEntryEdgeCaseTests:
    """Mixin providing async_setup_entry edge case tests."""

    setup_entry = None  # to be set by subclasses

    @pytest.mark.asyncio
    async def test_setup_with_runtime_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ) -> None:
        """Test setup_entry with runtime_data format."""
        mock_entry.runtime_data = {
            "coordinator": mock_coordinator,
            "dogs": mock_entry.data[CONF_DOGS],
        }
        add_entities_mock = Mock()
        await self.setup_entry(hass, mock_entry, add_entities_mock)
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_legacy_hass_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ) -> None:
        """Test setup_entry with legacy hass.data format."""
        hass.data[DOMAIN] = {mock_entry.entry_id: {"coordinator": mock_coordinator}}
        add_entities_mock = Mock()
        await self.setup_entry(hass, mock_entry, add_entities_mock)
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_no_dogs(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ) -> None:
        """Test setup_entry with no dogs configured."""
        mock_entry.data = {CONF_DOGS: []}
        mock_entry.runtime_data = {"coordinator": mock_coordinator, "dogs": []}
        add_entities_mock = Mock()
        await self.setup_entry(hass, mock_entry, add_entities_mock)
        add_entities_mock.assert_called()

    @pytest.mark.asyncio
    async def test_setup_with_malformed_dog_data(
        self, hass: HomeAssistant, mock_entry, mock_coordinator
    ) -> None:
        """Test setup_entry with malformed dog data."""
        mock_entry.data = {
            CONF_DOGS: [
                {
                    CONF_DOG_NAME: "Incomplete Dog",
                    "modules": {MODULE_FEEDING: True},
                },
                {
                    CONF_DOG_ID: "valid_dog",
                    CONF_DOG_NAME: "Valid Dog",
                },
            ]
        }
        add_entities_mock = Mock()
        await self.setup_entry(hass, mock_entry, add_entities_mock)
