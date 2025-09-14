"""Comprehensive tests for PawControl initialization.

Tests setup, unload, reload, and error handling during initialization
to achieve 95%+ test coverage.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.pawcontrol import (
    async_reload_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
    get_platforms_for_profile_and_modules,
)
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
)
from custom_components.pawcontrol.exceptions import PawControlSetupError


async def test_async_setup(hass: HomeAssistant) -> None:
    """Test the async_setup function."""
    config = {}
    
    result = await async_setup(hass, config)
    
    assert result is True
    assert DOMAIN in hass.data
    assert hass.data[DOMAIN] == {}


async def test_async_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
    mock_data_manager,
    mock_notification_manager,
    mock_feeding_manager,
    mock_walk_manager,
    mock_entity_factory,
) -> None:
    """Test successful setup of a config entry."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
        return_value=mock_data_manager,
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
        return_value=mock_notification_manager,
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
        return_value=mock_feeding_manager,
    ), patch(
        "custom_components.pawcontrol.WalkManager",
        return_value=mock_walk_manager,
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
        return_value=mock_entity_factory,
    ), patch(
        "custom_components.pawcontrol.PawControlServiceManager",
    ), patch(
        "custom_components.pawcontrol.async_setup_daily_reset_scheduler",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=True,
    ):
        result = await async_setup_entry(hass, mock_config_entry)
    
    assert result is True
    assert hasattr(mock_config_entry, "runtime_data")
    assert mock_config_entry.runtime_data is not None
    
    # Verify all managers were initialized
    mock_coordinator.async_config_entry_first_refresh.assert_called_once()
    mock_data_manager.async_initialize.assert_called_once()
    mock_notification_manager.async_initialize.assert_called_once()
    mock_feeding_manager.async_initialize.assert_called_once()
    mock_walk_manager.async_initialize.assert_called_once()


async def test_async_setup_entry_no_dogs(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup fails when no dogs are configured."""
    mock_config_entry.data = {CONF_DOGS: []}
    mock_config_entry.add_to_hass(hass)
    
    with pytest.raises(ConfigEntryNotReady, match="No dogs configured"):
        await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_invalid_dog(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test setup fails with invalid dog configuration."""
    mock_config_entry.data = {
        CONF_DOGS: [
            {"dog_name": "No ID"}  # Missing dog_id
        ]
    }
    mock_config_entry.add_to_hass(hass)
    
    with pytest.raises(ConfigEntryNotReady, match="Invalid dog configuration"):
        await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_timeout_error(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
) -> None:
    """Test setup handles timeout errors."""
    mock_config_entry.add_to_hass(hass)
    
    mock_coordinator.async_config_entry_first_refresh.side_effect = asyncio.TimeoutError()
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
    ), patch(
        "custom_components.pawcontrol.WalkManager",
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
    ):
        with pytest.raises(ConfigEntryNotReady, match="Timeout during initialization"):
            await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_value_error(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
    mock_data_manager,
) -> None:
    """Test setup handles value errors."""
    mock_config_entry.add_to_hass(hass)
    
    mock_data_manager.async_initialize.side_effect = ValueError("Invalid value")
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
        return_value=mock_data_manager,
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
    ), patch(
        "custom_components.pawcontrol.WalkManager",
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
    ):
        with pytest.raises(ConfigEntryNotReady, match="Invalid configuration"):
            await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_setup_error(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
) -> None:
    """Test setup handles PawControlSetupError."""
    mock_config_entry.add_to_hass(hass)
    
    mock_coordinator.async_config_entry_first_refresh.side_effect = PawControlSetupError(
        "Setup failed"
    )
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
    ), patch(
        "custom_components.pawcontrol.WalkManager",
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
    ):
        with pytest.raises(ConfigEntryNotReady, match="Setup error"):
            await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_platform_import_error(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
    mock_data_manager,
    mock_notification_manager,
    mock_feeding_manager,
    mock_walk_manager,
    mock_entity_factory,
) -> None:
    """Test setup handles platform import errors."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
        return_value=mock_data_manager,
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
        return_value=mock_notification_manager,
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
        return_value=mock_feeding_manager,
    ), patch(
        "custom_components.pawcontrol.WalkManager",
        return_value=mock_walk_manager,
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
        return_value=mock_entity_factory,
    ), patch(
        "custom_components.pawcontrol.PawControlServiceManager",
    ), patch(
        "custom_components.pawcontrol.async_setup_daily_reset_scheduler",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        side_effect=ImportError("Platform not found"),
    ):
        with pytest.raises(ConfigEntryNotReady, match="Platform import failed"):
            await async_setup_entry(hass, mock_config_entry)


async def test_async_setup_entry_unknown_profile(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
    mock_data_manager,
    mock_notification_manager,
    mock_feeding_manager,
    mock_walk_manager,
    mock_entity_factory,
) -> None:
    """Test setup with unknown entity profile."""
    mock_config_entry.options = {"entity_profile": "unknown_profile"}
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ), patch(
        "custom_components.pawcontrol.PawControlDataManager",
        return_value=mock_data_manager,
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
        return_value=mock_notification_manager,
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
        return_value=mock_feeding_manager,
    ), patch(
        "custom_components.pawcontrol.WalkManager",
        return_value=mock_walk_manager,
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
        return_value=mock_entity_factory,
    ), patch(
        "custom_components.pawcontrol.PawControlServiceManager",
    ), patch(
        "custom_components.pawcontrol.async_setup_daily_reset_scheduler",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=True,
    ):
        result = await async_setup_entry(hass, mock_config_entry)
    
    assert result is True
    # Should default to "standard" profile
    assert mock_config_entry.runtime_data.entity_profile == "standard"


async def test_async_unload_entry_success(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test successful unload of a config entry."""
    mock_config_entry.runtime_data = mock_runtime_data
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        result = await async_unload_entry(hass, mock_config_entry)
    
    assert result is True
    
    # Verify all managers were shut down
    mock_runtime_data.coordinator.async_shutdown.assert_called_once()
    mock_runtime_data.data_manager.async_shutdown.assert_called_once()
    mock_runtime_data.notification_manager.async_shutdown.assert_called_once()
    mock_runtime_data.feeding_manager.async_shutdown.assert_called_once()
    mock_runtime_data.walk_manager.async_shutdown.assert_called_once()


async def test_async_unload_entry_platform_error(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test unload handles platform unload errors."""
    mock_config_entry.runtime_data = mock_runtime_data
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        side_effect=ValueError("Unload failed"),
    ):
        result = await async_unload_entry(hass, mock_config_entry)
    
    assert result is False


async def test_async_unload_entry_no_runtime_data(
    hass: HomeAssistant,
    mock_config_entry,
) -> None:
    """Test unload when runtime_data is not set."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        result = await async_unload_entry(hass, mock_config_entry)
    
    assert result is True


async def test_async_unload_entry_partial_managers(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test unload with some managers missing shutdown method."""
    # Remove async_shutdown from some managers
    delattr(mock_runtime_data.feeding_manager, "async_shutdown")
    
    mock_config_entry.runtime_data = mock_runtime_data
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=True,
    ):
        result = await async_unload_entry(hass, mock_config_entry)
    
    assert result is True
    
    # Only managers with async_shutdown should be called
    mock_runtime_data.coordinator.async_shutdown.assert_called_once()
    mock_runtime_data.data_manager.async_shutdown.assert_called_once()


async def test_async_reload_entry(
    hass: HomeAssistant,
    mock_config_entry,
    mock_runtime_data,
) -> None:
    """Test reload of a config entry."""
    mock_config_entry.runtime_data = mock_runtime_data
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.pawcontrol.async_unload_entry",
        return_value=True,
    ) as mock_unload, patch(
        "custom_components.pawcontrol.async_setup_entry",
        return_value=True,
    ) as mock_setup:
        await async_reload_entry(hass, mock_config_entry)
    
    mock_unload.assert_called_once_with(hass, mock_config_entry)
    mock_setup.assert_called_once_with(hass, mock_config_entry)


def test_get_platforms_for_profile_and_modules_basic() -> None:
    """Test platform selection for basic profile."""
    dogs_config = [
        {
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            }
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "basic")
    
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms
    assert Platform.BINARY_SENSOR in platforms
    assert Platform.SWITCH in platforms
    # Basic profile should not have advanced platforms
    assert Platform.SELECT not in platforms
    assert Platform.DATE not in platforms


def test_get_platforms_for_profile_and_modules_standard() -> None:
    """Test platform selection for standard profile."""
    dogs_config = [
        {
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            }
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "standard")
    
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms
    assert Platform.BINARY_SENSOR in platforms
    assert Platform.SWITCH in platforms
    assert Platform.SELECT in platforms
    assert Platform.DEVICE_TRACKER in platforms
    assert Platform.NUMBER in platforms
    assert Platform.DATE in platforms
    assert Platform.TEXT in platforms


def test_get_platforms_for_profile_and_modules_advanced() -> None:
    """Test platform selection for advanced profile."""
    dogs_config = [
        {
            "modules": {
                MODULE_FEEDING: True,
                MODULE_WALK: True,
                MODULE_GPS: True,
                MODULE_HEALTH: True,
                MODULE_NOTIFICATIONS: True,
            }
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "advanced")
    
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms
    assert Platform.BINARY_SENSOR in platforms
    assert Platform.SWITCH in platforms
    assert Platform.SELECT in platforms
    assert Platform.DEVICE_TRACKER in platforms
    assert Platform.NUMBER in platforms
    assert Platform.DATE in platforms
    assert Platform.TEXT in platforms
    assert Platform.DATETIME in platforms  # Advanced adds datetime


def test_get_platforms_for_profile_and_modules_gps_focus() -> None:
    """Test platform selection for GPS-focused profile."""
    dogs_config = [
        {
            "modules": {
                MODULE_GPS: True,
            }
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "gps_focus")
    
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms
    assert Platform.BINARY_SENSOR in platforms
    assert Platform.DEVICE_TRACKER in platforms
    assert Platform.NUMBER in platforms  # GPS focus adds number


def test_get_platforms_for_profile_and_modules_health_focus() -> None:
    """Test platform selection for health-focused profile."""
    dogs_config = [
        {
            "modules": {
                MODULE_HEALTH: True,
            }
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "health_focus")
    
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms
    assert Platform.DATE in platforms
    assert Platform.NUMBER in platforms
    assert Platform.TEXT in platforms


def test_get_platforms_for_profile_and_modules_no_modules() -> None:
    """Test platform selection with no modules enabled."""
    dogs_config = [
        {
            "modules": {}
        }
    ]
    
    platforms = get_platforms_for_profile_and_modules(dogs_config, "standard")
    
    # Should have at least sensor and button
    assert Platform.SENSOR in platforms
    assert Platform.BUTTON in platforms


async def test_websession_injection(
    hass: HomeAssistant,
    mock_config_entry,
    mock_coordinator,
    mock_data_manager,
    mock_notification_manager,
    mock_feeding_manager,
    mock_walk_manager,
    mock_entity_factory,
) -> None:
    """Test WebSession injection for Platinum compliance."""
    mock_config_entry.add_to_hass(hass)
    
    with patch(
        "custom_components.pawcontrol.async_get_clientsession",
    ) as mock_get_session, patch(
        "custom_components.pawcontrol.PawControlCoordinator",
        return_value=mock_coordinator,
    ) as mock_coord_class, patch(
        "custom_components.pawcontrol.PawControlDataManager",
        return_value=mock_data_manager,
    ), patch(
        "custom_components.pawcontrol.PawControlNotificationManager",
        return_value=mock_notification_manager,
    ), patch(
        "custom_components.pawcontrol.FeedingManager",
        return_value=mock_feeding_manager,
    ), patch(
        "custom_components.pawcontrol.WalkManager",
        return_value=mock_walk_manager,
    ), patch(
        "custom_components.pawcontrol.entity_factory.EntityFactory",
        return_value=mock_entity_factory,
    ), patch(
        "custom_components.pawcontrol.PawControlServiceManager",
    ), patch(
        "custom_components.pawcontrol.async_setup_daily_reset_scheduler",
        return_value=None,
    ), patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        return_value=True,
    ):
        result = await async_setup_entry(hass, mock_config_entry)
    
    assert result is True
    
    # Verify WebSession was obtained
    mock_get_session.assert_called_once_with(hass)
    
    # Verify coordinator was created with session
    mock_coord_class.assert_called_once()
    call_args = mock_coord_class.call_args
    assert len(call_args[0]) == 3  # hass, entry, session
