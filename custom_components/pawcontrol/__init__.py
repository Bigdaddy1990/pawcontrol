"""Core setup and platform initialization for the PawControl integration.

Optimized setup with enhanced error handling, performance monitoring,
and Platinum-level compliance for Home Assistant 2025.9.3+.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import bind_hass

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
from .exceptions import PawControlSetupError
from .feeding_manager import FeedingManager
from .health_calculator import HealthCalculator
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

# Available platforms - using Final for immutability
ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# Platform cache for performance optimization
_PLATFORM_CACHE: dict[str, list[Platform]] = {}


@bind_hass
def get_platforms_for_profile_and_modules(
    dogs_config: list[dict[str, Any]], profile: str
) -> list[Platform]:
    """Determine required platforms based on dogs, modules and profile.
    
    Optimized with caching and single-pass iteration for better performance.
    
    Args:
        dogs_config: List of dog configurations
        profile: Entity profile name
        
    Returns:
        List of required platforms
    """
    if not dogs_config:
        return [Platform.SENSOR, Platform.BUTTON]
    
    # Generate cache key for performance optimization
    cache_key = f"{len(dogs_config)}_{profile}_{hash(str(sorted(
        (dog.get(CONF_DOG_ID, ''), tuple(sorted(dog.get('modules', {}).items())))
        for dog in dogs_config
    )))}"
    
    if cache_key in _PLATFORM_CACHE:
        return _PLATFORM_CACHE[cache_key]
    
    # Pre-validate profile to avoid issues later
    from .entity_factory import ENTITY_PROFILES
    
    if profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        profile = "standard"
    
    # Single-pass collection of enabled modules using set operations
    enabled_modules: set[str] = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        enabled_modules.update(mod for mod, enabled in modules.items() if enabled)

    # Base platforms always included
    platforms: set[Platform] = {Platform.SENSOR, Platform.BUTTON}

    # Profile-specific platform determination with optimized logic
    if profile == "basic":
        if enabled_modules.intersection({MODULE_WALK, MODULE_GPS}):
            platforms.add(Platform.BINARY_SENSOR)
        if MODULE_NOTIFICATIONS in enabled_modules:
            platforms.add(Platform.SWITCH)
    else:
        # Standard/advanced profiles - more comprehensive platform support
        if MODULE_NOTIFICATIONS in enabled_modules or enabled_modules:
            platforms.add(Platform.SWITCH)

        if enabled_modules.intersection({MODULE_WALK, MODULE_GPS}):
            platforms.add(Platform.BINARY_SENSOR)

        if MODULE_FEEDING in enabled_modules:
            platforms.add(Platform.SELECT)

        if MODULE_GPS in enabled_modules:
            platforms.update({Platform.DEVICE_TRACKER, Platform.NUMBER})

        if MODULE_HEALTH in enabled_modules:
            platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

        # Profile-specific additions
        if profile == "advanced":
            platforms.add(Platform.DATETIME)
        elif profile == "gps_focus":
            platforms.add(Platform.NUMBER)
        elif profile == "health_focus":
            platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    result_platforms = list(platforms)
    _PLATFORM_CACHE[cache_key] = result_platforms
    return result_platforms


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml.
    
    Args:
        hass: Home Assistant instance
        config: Configuration from configuration.yaml
        
    Returns:
        True if setup successful
    """
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    Enhanced with comprehensive error handling and performance monitoring.

    Args:
        hass: Home Assistant instance
        entry: PawControl config entry with typed runtime data

    Returns:
        True if setup successful

    Raises:
        ConfigEntryNotReady: If setup prerequisites not met
    """
    _LOGGER.debug("Setting up Paw Control integration entry: %s", entry.entry_id)

    # Validate dogs configuration early with enhanced validation
    dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
    if not dogs_config:
        raise ConfigEntryNotReady("No dogs configured")
    
    # Enhanced validation for each dog configuration
    for dog in dogs_config:
        if not dog.get(CONF_DOG_ID):
            raise ConfigEntryNotReady(f"Invalid dog configuration: missing {CONF_DOG_ID}")
        # Additional validation
        if not isinstance(dog.get(CONF_DOG_ID), str) or not dog[CONF_DOG_ID].strip():
            raise ConfigEntryNotReady(f"Invalid dog ID: {dog.get(CONF_DOG_ID)}")

    # Determine and validate profile
    profile = entry.options.get("entity_profile", "standard")
    from .entity_factory import ENTITY_PROFILES, EntityFactory

    if profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        profile = "standard"

    # Calculate platforms once for reuse (cached)
    platforms = get_platforms_for_profile_and_modules(dogs_config, profile)
    
    # Initialize core components with proper error handling and session injection
    session = async_get_clientsession(hass)
    coordinator = PawControlCoordinator(hass, entry, session)
    data_manager = PawControlDataManager(hass, entry.entry_id)
    notification_manager = PawControlNotificationManager(hass, entry.entry_id)
    feeding_manager = FeedingManager()
    walk_manager = WalkManager()
    entity_factory = EntityFactory(coordinator)

    # Performance optimization: estimate entity count for monitoring
    total_estimated_entities = 0
    for dog in dogs_config:
        total_estimated_entities += entity_factory.estimate_entity_count(
            profile, dog.get("modules", {})
        )
    
    _LOGGER.debug(
        "Estimated %d entities for %d dogs with profile '%s'",
        total_estimated_entities,
        len(dogs_config),
        profile,
    )

    # FIX: Initialize all managers with proper error handling and sequential ordering
    initialized_managers: list[Any] = []
    try:
        # Initialize coordinator first (critical dependency)
        await coordinator.async_config_entry_first_refresh()
        initialized_managers.append(coordinator)
        
        # FIX: Initialize managers sequentially to avoid race conditions
        # Order matters: data_manager -> others (they may depend on data_manager)
        try:
            await asyncio.wait_for(data_manager.async_initialize(), timeout=10.0)
            initialized_managers.append(data_manager)
        except Exception as err:
            await _cleanup_managers(initialized_managers)
            raise ConfigEntryNotReady(f"Data manager initialization failed: {err}") from err
            
        try:
            await asyncio.wait_for(notification_manager.async_initialize(), timeout=10.0)
            initialized_managers.append(notification_manager)
        except Exception as err:
            await _cleanup_managers(initialized_managers)
            raise ConfigEntryNotReady(f"Notification manager initialization failed: {err}") from err
            
        try:
            await asyncio.wait_for(feeding_manager.async_initialize(dogs_config), timeout=10.0)
            initialized_managers.append(feeding_manager)
        except Exception as err:
            await _cleanup_managers(initialized_managers)
            raise ConfigEntryNotReady(f"Feeding manager initialization failed: {err}") from err
            
        try:
            await asyncio.wait_for(
                walk_manager.async_initialize([dog[CONF_DOG_ID] for dog in dogs_config]),
                timeout=10.0
            )
            initialized_managers.append(walk_manager)
        except Exception as err:
            await _cleanup_managers(initialized_managers)
            raise ConfigEntryNotReady(f"Walk manager initialization failed: {err}") from err

    except ConfigEntryNotReady:
        # Cleanup on initialization failure
        await _cleanup_managers(initialized_managers)
        raise

    # FIX: Set up platforms with comprehensive error handling and recovery
    try:
        await hass.config_entries.async_forward_entry_setups(entry, platforms)
    except Exception as err:
        # Cleanup managers if platform setup fails
        await _cleanup_managers(initialized_managers)
        if isinstance(err, ImportError):
            raise ConfigEntryNotReady(f"Platform import failed: {err}") from err
        elif isinstance(err, (ValueError, TypeError)):
            raise ConfigEntryNotReady(f"Platform setup failed: {err}") from err
        else:
            raise ConfigEntryNotReady(f"Unexpected platform setup error: {err}") from err

    # Initialize optional services (non-critical) with error isolation
    try:
        service_manager = PawControlServiceManager(hass)
        await async_setup_daily_reset_scheduler(hass, entry)
    except Exception as err:
        _LOGGER.warning("Failed to initialize optional services: %s", err)
        # Continue setup even if services fail

    # Store runtime data in typed ConfigEntry - Platinum compliance
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
    entry.runtime_data = runtime_data
    
    # Start background tasks for coordinator
    coordinator.async_start_background_tasks()
    
    _LOGGER.info(
        "PawControl setup completed: %d dogs, %d platforms, profile '%s'",
        len(dogs_config),
        len(platforms),
        profile,
    )
    
    return True


async def _cleanup_managers(managers: list[Any]) -> None:
    """Cleanup initialized managers on setup failure.
    
    Args:
        managers: List of manager instances to cleanup
    """
    cleanup_tasks = []
    for manager in reversed(managers):  # Cleanup in reverse order
        if hasattr(manager, "async_shutdown"):
            cleanup_tasks.append(manager.async_shutdown())
    
    if cleanup_tasks:
        # Run cleanup concurrently with individual error handling
        results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        for manager, result in zip(reversed(managers), results):
            if isinstance(result, Exception):
                _LOGGER.error(
                    "Failed to cleanup %s during setup failure: %s",
                    manager.__class__.__name__,
                    result,
                )


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Unload a config entry.

    Enhanced with better error handling and concurrent cleanup.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    runtime_data = entry.runtime_data
    
    # Get platform list for unloading
    if runtime_data:
        dogs = runtime_data.dogs
        profile = runtime_data.entity_profile
    else:
        dogs = entry.data.get(CONF_DOGS, [])
        profile = entry.options.get("entity_profile", "standard")
    
    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    # Unload platforms first with timeout
    try:
        unload_ok = await asyncio.wait_for(
            hass.config_entries.async_unload_platforms(entry, platforms),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        _LOGGER.error("Platform unload timeout after 30 seconds")
        unload_ok = False
    except Exception as err:
        _LOGGER.error("Failed to unload platforms: %s", err)
        unload_ok = False

    # Cleanup runtime data regardless of platform unload success
    if runtime_data:
        # Shutdown managers in reverse dependency order
        managers = [
            runtime_data.walk_manager,
            runtime_data.feeding_manager,
            runtime_data.notification_manager,
            runtime_data.data_manager,
            runtime_data.coordinator,
        ]
        
        # Filter managers that have shutdown capability
        shutdown_managers = [mgr for mgr in managers if hasattr(mgr, "async_shutdown")]
        
        # Shutdown with concurrent execution and individual error handling
        if shutdown_managers:
            shutdown_results = await asyncio.gather(
                *(manager.async_shutdown() for manager in shutdown_managers),
                return_exceptions=True,
            )
            
            # Log any shutdown errors but don't fail the unload
            for manager, result in zip(shutdown_managers, shutdown_results):
                if isinstance(result, Exception):
                    _LOGGER.error(
                        "Error shutting down %s: %s",
                        manager.__class__.__name__,
                        result,
                    )

    # Clear platform cache on unload
    _PLATFORM_CACHE.clear()

    _LOGGER.debug(
        "PawControl unload completed: success=%s, platforms=%d",
        unload_ok,
        len(platforms),
    )

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
