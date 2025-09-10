"""The Paw Control integration for Home Assistant with complete manager support.

UPDATED: Restored critical manager initialization for services compatibility.
Maintains simplified coordinator while enabling full functionality.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DOGS,
    DOMAIN,
    PLATFORMS,
)
from .types import DogConfigData

_LOGGER = logging.getLogger(__name__)

# This integration can only be configured via the UI
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Available platforms
ALL_PLATFORMS: Final[list[Platform]] = PLATFORMS


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing integration configuration

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If setup cannot be completed
    """
    _LOGGER.info("Setting up Paw Control integration entry: %s", entry.entry_id)

    try:
        # Import core components
        from .coordinator import PawControlCoordinator

        # Import critical managers for services
        from .data_manager import DataManager
        from .entity_factory import ENTITY_PROFILES, EntityFactory
        from .feeding_manager import FeedingManager
        from .walk_manager import WalkManager

    except ImportError as err:
        _LOGGER.error("Failed to import required modules: %s", err)
        raise ConfigEntryNotReady(f"Import error: {err}") from err

    # Validate configuration
    dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
    if not dogs_config:
        raise ConfigEntryNotReady("No dogs configured")

    # Get entity profile
    entity_profile = entry.options.get("entity_profile", "standard")
    if entity_profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", entity_profile)
        entity_profile = "standard"

    try:
        # Initialize coordinator
        coordinator = PawControlCoordinator(hass, entry)

        # Initialize entity factory
        entity_factory = EntityFactory(coordinator)

        # Initialize critical managers for services compatibility
        data_manager = DataManager()
        feeding_manager = FeedingManager()
        walk_manager = WalkManager()

        # Initialize managers with dog configurations
        dog_ids = [dog.get("dog_id") for dog in dogs_config if dog.get("dog_id")]

        await data_manager.async_initialize(dogs_config)
        await feeding_manager.async_initialize(dogs_config)
        await walk_manager.async_initialize(dog_ids)

        # Perform initial data refresh
        await coordinator.async_config_entry_first_refresh()

        # Store runtime data with all managers for services compatibility
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "entity_factory": entity_factory,
            "data_manager": data_manager,
            "feeding_manager": feeding_manager,
            "walk_manager": walk_manager,
            "entry": entry,
            "entity_profile": entity_profile,
            "dogs": dogs_config,
        }

        # Determine needed platforms based on configuration
        needed_platforms = _get_needed_platforms(dogs_config)

        # Setup platforms
        await hass.config_entries.async_forward_entry_setups(entry, needed_platforms)

        _LOGGER.info(
            "Paw Control setup completed: %d dogs, %d platforms, profile: %s",
            len(dogs_config),
            len(needed_platforms),
            entity_profile,
        )

        return True

    except Exception as err:
        _LOGGER.error("Setup failed: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Setup error: {err}") from err


def _get_needed_platforms(dogs_config: list[DogConfigData]) -> list[Platform]:
    """Determine needed platforms based on dog configuration.

    Args:
        dogs_config: List of dog configurations

    Returns:
        List of required platforms
    """
    # Always include core platforms
    platforms = [Platform.SENSOR, Platform.BUTTON]

    # Check what modules are enabled across all dogs
    enabled_modules = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        enabled_modules.update(name for name, enabled in modules.items() if enabled)

    # Add platforms based on enabled modules
    if "feeding" in enabled_modules:
        platforms.extend([Platform.SELECT, Platform.DATETIME, Platform.TEXT])

    if "walk" in enabled_modules:
        platforms.extend([Platform.BINARY_SENSOR, Platform.NUMBER])

    if "gps" in enabled_modules:
        platforms.extend([Platform.DEVICE_TRACKER, Platform.NUMBER])

    if "health" in enabled_modules:
        platforms.extend([Platform.DATE, Platform.TEXT])

    if "notifications" in enabled_modules:
        platforms.extend([Platform.SWITCH])

    # Remove duplicates and return
    return list(set(platforms))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    _LOGGER.info("Unloading Paw Control integration: %s", entry.entry_id)

    # Get stored data
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    dogs_config = entry_data.get("dogs", [])

    # Cleanup managers
    try:
        if data_manager := entry_data.get("data_manager"):
            await data_manager.async_cleanup()
        if feeding_manager := entry_data.get("feeding_manager"):
            await feeding_manager.async_shutdown()
        if walk_manager := entry_data.get("walk_manager"):
            await walk_manager.async_cleanup()
    except Exception as err:
        _LOGGER.warning("Manager cleanup error: %s", err)

    # Determine loaded platforms
    loaded_platforms = (
        _get_needed_platforms(dogs_config) if dogs_config else ALL_PLATFORMS
    )

    # Unload platforms
    unload_success = await hass.config_entries.async_unload_platforms(
        entry, loaded_platforms
    )

    if unload_success:
        # Clean up stored data
        hass.data[DOMAIN].pop(entry.entry_id, None)
        _LOGGER.info("Paw Control integration unloaded successfully")

    return unload_success


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.info("Reloading Paw Control integration: %s", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
