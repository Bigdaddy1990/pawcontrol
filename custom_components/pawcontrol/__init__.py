"""PawControl - Comprehensive Dog Management for Home Assistant."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_DOGS,
    CONF_DOG_NAME,
    CONF_MODULES,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_AUTOMATION,
    MODULE_DASHBOARD,
    ALL_MODULES,
)
from .coordinator import PawControlCoordinator
from .modules import ModuleManager
from .services import async_register_services, async_unregister_services
from .setup_manager import PawControlSetupManager

_LOGGER = logging.getLogger(__name__)

# Platforms that will be set up
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.TEXT,
    Platform.DATETIME,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PawControl from a config entry."""
    _LOGGER.info("Setting up PawControl integration")
    
    # Store domain data
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    # Use the new setup manager for complete system setup
    setup_manager = PawControlSetupManager(hass, entry)
    success = await setup_manager.async_setup_complete_system()
    
    if not success:
        _LOGGER.error("Failed to complete PawControl setup")
        return False
    
    # Store setup manager for later use
    if "setup_managers" not in hass.data[DOMAIN]:
        hass.data[DOMAIN]["setup_managers"] = {}
    hass.data[DOMAIN]["setup_managers"][entry.entry_id] = setup_manager
    
    # Create coordinator for each dog
    dogs_data = entry.data.get(CONF_DOGS, [])
    entry_data = {}
    
    for dog_config in dogs_data:
        dog_name = dog_config.get(CONF_DOG_NAME)
        if not dog_name:
            continue
            
        _LOGGER.info(f"Initializing coordinator for dog: {dog_name}")
        
        # Create coordinator for this dog
        coordinator = PawControlCoordinator(hass, entry, dog_config)
        
        # Store in entry data (module_manager removed to prevent double setup)
        entry_data[dog_name] = {
            "coordinator": coordinator,
            "config": dog_config,
        }
        
        # Perform initial data fetch
        await coordinator.async_config_entry_first_refresh()
    
    # Store entry data
    hass.data[DOMAIN][entry.entry_id] = entry_data
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_register_services(hass)
    
    # Listen for config updates
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    _LOGGER.info("PawControl setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading PawControl integration")
    
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Get setup manager if exists
        setup_manager = None
        if DOMAIN in hass.data and "setup_managers" in hass.data[DOMAIN]:
            setup_manager = hass.data[DOMAIN]["setup_managers"].get(entry.entry_id)
        
        # Cleanup each dog using setup manager
        if setup_manager:
            dogs_data = entry.data.get(CONF_DOGS, [])
            for dog_config in dogs_data:
                dog_name = dog_config.get(CONF_DOG_NAME)
                if dog_name:
                    await setup_manager.async_cleanup_dog(dog_name)
            
            # Remove setup manager
            del hass.data[DOMAIN]["setup_managers"][entry.entry_id]
        
        # Get entry data
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        
        # Clean up each dog's data (fallback if no setup manager)
        for dog_name, dog_data in entry_data.items():
            _LOGGER.info(f"Cleaning up data for dog: {dog_name}")
            
            # Module cleanup is now handled by setup_manager
            
            # Clean up coordinator
            coordinator = dog_data.get("coordinator")
            if coordinator and hasattr(coordinator, "async_shutdown"):
                await coordinator.async_shutdown()
        
        # Unregister services if no more entries
        if not hass.data[DOMAIN] or (len(hass.data[DOMAIN]) == 1 and "setup_managers" in hass.data[DOMAIN]):
            await async_unregister_services(hass)
            if not hass.data[DOMAIN] or not any(k != "setup_managers" for k in hass.data[DOMAIN]):
                hass.data.pop(DOMAIN, None)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.info("Reloading PawControl configuration")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.info(f"Migrating PawControl from version {config_entry.version}")
    
    if config_entry.version == 1:
        # Future migration logic here
        pass
    
    return True
