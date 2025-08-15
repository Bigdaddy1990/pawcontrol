"""Test Paw Control setup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from custom_components.pawcontrol.const import DOMAIN

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("enable_custom_integrations"),
]

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_coordinator: Any,
    mock_notification_router: Any,
    mock_setup_sync: Any,
) -> None:
    """Test setting up the integration."""
    mock_config_entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pawcontrol.coordinator.PawControlCoordinator",
            return_value=mock_coordinator,
        ),
        patch(
            "custom_components.pawcontrol.helpers.notification_router.NotificationRouter",
            return_value=mock_notification_router,
        ),
        patch(
            "custom_components.pawcontrol.helpers.setup_sync.SetupSync",
            return_value=mock_setup_sync,
        ),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state.value == "loaded"
    assert DOMAIN in hass.data
    assert mock_config_entry.entry_id in hass.data[DOMAIN]
    assert mock_config_entry.runtime_data is not None


async def test_unload_entry(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test unloading the integration."""
    assert init_integration.state.value == "loaded"

    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert init_integration.state.value == "not_loaded"
    assert init_integration.entry_id not in hass.data.get(DOMAIN, {})


async def test_setup_entry_fails_on_exception(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test setup fails when coordinator raises exception."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.pawcontrol.coordinator.PawControlCoordinator.async_config_entry_first_refresh",
        side_effect=Exception("Test error"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state.value == "setup_retry"
