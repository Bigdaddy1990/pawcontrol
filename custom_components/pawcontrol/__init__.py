"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DOG_ID,
    CONF_DOGS,
    DOMAIN,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
    PLATFORMS,
)
from .coordinator import PawControlCoordinator
from .data_manager import PawControlDataManager
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .exceptions import PawControlSetupError
from .feeding_manager import FeedingManager
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# OPTIMIZED: Efficient platform determination cache with better hash strategy
_PLATFORM_CACHE: dict[str, frozenset[Platform]] = {}


def get_platforms_for_profile_and_modules(
    dogs_config: list[DogConfigData], profile: str
) -> frozenset[Platform]:
    """Determine required platforms based on dogs, modules and profile.

    Args:
        dogs_config: List of dog configurations
        profile: Entity profile name

    Returns:
        Frozenset of required platforms
    """
    if not dogs_config:
        return frozenset([Platform.BUTTON, Platform.SENSOR])

    # OPTIMIZED: Create efficient cache key with better hash strategy
    modules_hash = frozenset().union(*(
        frozenset(m for m, enabled in dog.get("modules", {}).items() if enabled)
        for dog in dogs_config
    ))
    cache_key = f"{len(dogs_config)}_{profile}_{hash(modules_hash)}"
    
    if cache_key in _PLATFORM_CACHE:
        return _PLATFORM_CACHE[cache_key]

    # Calculate platforms
    platforms = {Platform.SENSOR, Platform.BUTTON}
    
    # Check enabled modules across all dogs
    all_enabled_modules = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        all_enabled_modules.update(m for m, enabled in modules.items() if enabled)

    # Add platforms based on enabled modules
    if MODULE_NOTIFICATIONS in all_enabled_modules:
        platforms.add(Platform.SWITCH)
    
    if any(m in all_enabled_modules for m in [MODULE_WALK, MODULE_GPS]):
        platforms.add(Platform.BINARY_SENSOR)
    
    if MODULE_FEEDING in all_enabled_modules:
        platforms.add(Platform.SELECT)
    
    if MODULE_GPS in all_enabled_modules:
        platforms.update({Platform.DEVICE_TRACKER, Platform.NUMBER})
    
    if MODULE_HEALTH in all_enabled_modules:
        platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    # Profile-specific additions
    if profile == "advanced" and all_enabled_modules:
        platforms.add(Platform.DATETIME)

    result = frozenset(platforms)
    _PLATFORM_CACHE[cache_key] = result
    return result


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the PawControl integration from configuration.yaml."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    # Register integration-level services
    if "service_manager" not in domain_data:
        domain_data["service_manager"] = PawControlServiceManager(hass)
        _LOGGER.debug("Registered PawControl services")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Set up PawControl from a config entry.

    Args:
        hass: Home Assistant instance
        entry: PawControl config entry with typed runtime data

    Returns:
        True if setup successful

    Raises:
        ConfigEntryNotReady: If setup prerequisites not met
        ConfigEntryAuthFailed: If authentication fails
    """
    _LOGGER.debug("Setting up PawControl integration entry: %s", entry.entry_id)

    # Validate dogs configuration
    dogs_config_raw = entry.data.get(CONF_DOGS, [])
    if not dogs_config_raw:
        raise ConfigEntryNotReady("No dogs configured")

    if not isinstance(dogs_config_raw, list):
        raise PawControlSetupError("Invalid dogs configuration format")

    dogs_config: list[DogConfigData] = []
    for dog in dogs_config_raw:
        if not isinstance(dog, dict) or not dog.get(CONF_DOG_ID):
            raise ConfigEntryNotReady("Invalid dog configuration")
        dogs_config.append(dog)

    # Validate profile
    profile = entry.options.get("entity_profile", "standard")
    if profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        profile = "standard"

    # Calculate platforms
    platforms = get_platforms_for_profile_and_modules(dogs_config, profile)

    # Initialize core components
    session = async_get_clientsession(hass)
    coordinator = PawControlCoordinator(hass, entry, session)
    data_manager = PawControlDataManager(hass, entry.entry_id)
    notification_manager = PawControlNotificationManager(hass, entry.entry_id)
    feeding_manager = FeedingManager()
    walk_manager = WalkManager()
    entity_factory = EntityFactory(coordinator)

    # Initialize managers
    try:
        await coordinator.async_config_entry_first_refresh()
        
        # Initialize other managers
        await asyncio.gather(
            data_manager.async_initialize(),
            notification_manager.async_initialize(),
            feeding_manager.async_initialize([dict(dog) for dog in dogs_config]),
            walk_manager.async_initialize([dog[CONF_DOG_ID] for dog in dogs_config]),
        )
    except asyncio.TimeoutError as err:
        raise ConfigEntryNotReady(f"Manager initialization timeout: {err}") from err
    except ConfigEntryAuthFailed:
        raise  # Re-raise auth failures
    except (ConnectionError, OSError) as err:
        raise ConfigEntryNotReady(f"Connection failed during setup: {err}") from err
    except Exception as err:
        # PLATINUM: Only broad exception in setup for robustness
        _LOGGER.exception("Unexpected error during manager initialization")
        raise ConfigEntryNotReady(f"Manager initialization failed: {err}") from err

    # Attach runtime managers
    coordinator.attach_runtime_managers(
        data_manager=data_manager,
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        notification_manager=notification_manager,
    )

    # Setup platforms
    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
    except Exception as err:
        _LOGGER.exception("Platform setup failed")
        raise ConfigEntryNotReady(f"Platform setup failed: {err}") from err

    # Create runtime data
    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=data_manager,
        notification_manager=notification_manager,
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        entity_factory=entity_factory,
        entity_profile=profile,
        dogs=dogs_config,
    )

    # Store runtime data (PLATINUM: Only store in ConfigEntry.runtime_data)
    entry.runtime_data = runtime_data

    # Setup daily reset scheduler (optional)
    try:
        reset_unsub = await async_setup_daily_reset_scheduler(hass, entry)
        if reset_unsub:
            runtime_data.daily_reset_unsub = reset_unsub
    except Exception as err:
        _LOGGER.warning("Failed to setup daily reset scheduler: %s", err)

    # Start background tasks
    coordinator.async_start_background_tasks()

    # Add reload listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "PawControl setup completed: %d dogs, %d platforms, profile '%s'",
        len(dogs_config),
        len(platforms),
        profile,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    runtime_data = entry.runtime_data

    # Get platforms for unloading
    if runtime_data:
        dogs = runtime_data.dogs
        profile = runtime_data.entity_profile
    else:
        dogs = entry.data.get(CONF_DOGS, [])
        profile = entry.options.get("entity_profile", "standard")

    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)

    # Cleanup runtime data
    if runtime_data:
        # Shutdown daily reset scheduler
        if hasattr(runtime_data, 'daily_reset_unsub') and runtime_data.daily_reset_unsub:
            runtime_data.daily_reset_unsub()

        # Shutdown managers with specific exception handling
        shutdown_tasks = []
        for manager_name, manager in [
            ("coordinator", runtime_data.coordinator),
            ("data_manager", runtime_data.data_manager),
            ("notification_manager", runtime_data.notification_manager),
            ("feeding_manager", runtime_data.feeding_manager),
            ("walk_manager", runtime_data.walk_manager),
        ]:
            if hasattr(manager, 'async_shutdown'):
                shutdown_tasks.append(manager.async_shutdown())
        
        if shutdown_tasks:
            shutdown_results = await asyncio.gather(
                *shutdown_tasks, return_exceptions=True
            )
            
            for result in shutdown_results:
                if isinstance(result, Exception):
                    _LOGGER.warning("Error during manager shutdown: %s", result)

        # Clear coordinator references
        runtime_data.coordinator.clear_runtime_managers()

    # Clear caches
    _PLATFORM_CACHE.clear()

    # Cleanup service manager if no more entries
    domain_data = hass.data.get(DOMAIN, {})
    service_manager = domain_data.get("service_manager")
    if service_manager and hasattr(service_manager, '_tracked_entries'):
        service_manager._tracked_entries.discard(entry.entry_id)
        if not service_manager._tracked_entries:
            try:
                await service_manager.async_shutdown()
            except Exception as err:
                _LOGGER.warning("Error shutting down service manager: %s", err)
            finally:
                domain_data.pop("service_manager", None)

    _LOGGER.info("PawControl unload completed: success=%s", unload_ok)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.debug("Reloading PawControl integration entry: %s", entry.entry_id)
    
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
