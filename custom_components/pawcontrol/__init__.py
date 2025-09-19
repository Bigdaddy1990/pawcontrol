"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any, Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ALL_MODULES,
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_MODULES,
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
from .door_sensor_manager import DoorSensorManager
from .entity_factory import ENTITY_PROFILES, EntityFactory
from .exceptions import (
    ConfigurationError,
    PawControlSetupError,
    ValidationError,
)
from .feeding_manager import FeedingManager
from .geofencing import PawControlGeofencing
from .helper_manager import PawControlHelperManager
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# OPTIMIZED: Efficient platform determination cache with better hash strategy
type PlatformCacheKey = tuple[int, str, frozenset[str]]
type PlatformTuple = tuple[Platform, ...]

_DEFAULT_PLATFORMS: Final[PlatformTuple] = (
    Platform.BUTTON,
    Platform.SENSOR,
)
_PLATFORM_CACHE: dict[PlatformCacheKey, PlatformTuple] = {}


def _extract_enabled_modules(dogs_config: Sequence[DogConfigData]) -> frozenset[str]:
    """Return the set of enabled modules across all configured dogs.
    
    Args:
        dogs_config: List of dog configuration data
        
    Returns:
        Set of enabled module names
    """
    enabled_modules: set[str] = set()
    unknown_modules: set[str] = set()

    for dog in dogs_config:
        modules_config = dog.get(CONF_MODULES)
        if modules_config is None:
            continue

        if not isinstance(modules_config, Mapping):
            _LOGGER.warning(
                "Ignoring modules for dog %s because configuration is not a mapping",
                dog.get(CONF_DOG_ID, "<unknown>"),
            )
            continue

        for module_name, enabled in modules_config.items():
            if not enabled:
                continue

            if module_name not in ALL_MODULES:
                unknown_modules.add(module_name)
                continue

            enabled_modules.add(module_name)

    if unknown_modules:
        _LOGGER.warning(
            "Ignoring unknown PawControl modules: %s",
            ", ".join(sorted(unknown_modules)),
        )

    return frozenset(enabled_modules)


def get_platforms_for_profile_and_modules(
    dogs_config: Sequence[DogConfigData], profile: str
) -> PlatformTuple:
    """Determine required platforms based on dogs, modules and profile.

    Args:
        dogs_config: List of dog configurations
        profile: Entity profile name

    Returns:
        Tuple of required platforms sorted by their enum value for determinism.
    """
    if not dogs_config:
        return _DEFAULT_PLATFORMS

    enabled_modules = _extract_enabled_modules(dogs_config)
    cache_key: PlatformCacheKey = (len(dogs_config), profile, enabled_modules)

    if cache_key in _PLATFORM_CACHE:
        return _PLATFORM_CACHE[cache_key]

    platforms: set[Platform] = {Platform.SENSOR, Platform.BUTTON}

    if MODULE_NOTIFICATIONS in enabled_modules:
        platforms.add(Platform.SWITCH)

    if {MODULE_WALK, MODULE_GPS} & enabled_modules:
        platforms.add(Platform.BINARY_SENSOR)

    if MODULE_FEEDING in enabled_modules:
        platforms.add(Platform.SELECT)

    if MODULE_GPS in enabled_modules:
        platforms.update({Platform.DEVICE_TRACKER, Platform.NUMBER})

    if MODULE_HEALTH in enabled_modules:
        platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    if profile == "advanced" and enabled_modules:
        platforms.add(Platform.DATETIME)

    ordered_platforms: PlatformTuple = tuple(
        sorted(platforms, key=lambda platform: platform.value)
    )
    _PLATFORM_CACHE[cache_key] = ordered_platforms
    return ordered_platforms


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the PawControl integration from configuration.yaml.
    
    Args:
        hass: Home Assistant instance
        config: Configuration dictionary
        
    Returns:
        True if setup successful
    """
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
        PawControlSetupError: If setup validation fails
    """
    _LOGGER.debug("Setting up PawControl integration entry: %s", entry.entry_id)

    try:
        # Validate dogs configuration with specific error handling
        dogs_config_raw = entry.data.get(CONF_DOGS, [])
        if not dogs_config_raw:
            raise ConfigurationError(
                "dogs_configuration", 
                dogs_config_raw, 
                "No dogs configured in integration setup"
            )

        if not isinstance(dogs_config_raw, list):
            raise ConfigurationError(
                "dogs_configuration",
                type(dogs_config_raw).__name__,
                "Dogs configuration must be a list"
            )

        # PLATINUM: Validate each dog config with specific errors
        dogs_config: list[DogConfigData] = []
        for i, dog in enumerate(dogs_config_raw):
            if not isinstance(dog, dict) or not dog.get(CONF_DOG_ID):
                raise ConfigurationError(
                    f"dog_config_{i}",
                    dog,
                    f"Invalid dog configuration at index {i}: missing or invalid dog_id"
                )
            dogs_config.append(dog)

        # Calculate enabled modules
        enabled_modules = _extract_enabled_modules(dogs_config)

        # Validate profile with fallback
        profile = entry.options.get("entity_profile", "standard")
        if profile not in ENTITY_PROFILES:
            _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
            profile = "standard"

        # Calculate platforms
        platforms = get_platforms_for_profile_and_modules(dogs_config, profile)

        # PLATINUM: Enhanced session management
        session = async_get_clientsession(hass)
        coordinator = PawControlCoordinator(hass, entry, session)
        
        # Initialize managers with specific error handling
        try:
            data_manager = PawControlDataManager(hass, entry.entry_id)
            notification_manager = PawControlNotificationManager(hass, entry.entry_id)
            feeding_manager = FeedingManager()
            walk_manager = WalkManager()
            entity_factory = EntityFactory(coordinator)
            helper_manager = PawControlHelperManager(hass, entry.entry_id)
            door_sensor_manager = DoorSensorManager(hass, entry.entry_id)
            
            # Initialize geofencing manager if GPS module is enabled for any dog
            geofencing_manager = None
            if any(dog.get("modules", {}).get(MODULE_GPS, False) for dog in dogs_config):
                geofencing_manager = PawControlGeofencing(hass, entry.entry_id)
                _LOGGER.debug("Geofencing manager created for GPS-enabled dogs")
            else:
                _LOGGER.debug("Geofencing manager not created - no GPS modules enabled")
                
        except Exception as err:
            raise PawControlSetupError(
                f"Manager initialization failed: {err.__class__.__name__}: {err}"
            ) from err

        # PLATINUM: Specific timeout and connection error handling
        try:
            await coordinator.async_config_entry_first_refresh()
        except asyncio.TimeoutError as err:
            raise ConfigEntryNotReady(
                f"Coordinator initialization timeout after {err.args}"
            ) from err
        except ConfigEntryAuthFailed:
            raise  # Re-raise auth failures directly
        except (OSError, ConnectionError) as err:
            raise ConfigEntryNotReady(
                f"Network connectivity issue during coordinator setup: {err}"
            ) from err

        # Initialize other managers with specific error handling
        try:
            initialization_tasks = [
                data_manager.async_initialize(),
                notification_manager.async_initialize(),
                feeding_manager.async_initialize([dict(dog) for dog in dogs_config]),
                walk_manager.async_initialize([dog[CONF_DOG_ID] for dog in dogs_config]),
                helper_manager.async_initialize(),
                door_sensor_manager.async_initialize(
                    dogs=dogs_config,
                    walk_manager=walk_manager,
                    notification_manager=notification_manager,
                ),
            ]
            
            # Add geofencing initialization if manager was created
            if geofencing_manager:
                geofence_options = entry.options.get("geofence_settings", {})
                geofencing_enabled = geofence_options.get("geofencing_enabled", False)
                use_home_location = geofence_options.get("use_home_location", True)
                home_zone_radius = geofence_options.get("geofence_radius_m", 50)
                
                initialization_tasks.append(
                    geofencing_manager.async_initialize(
                        dogs=[dog[CONF_DOG_ID] for dog in dogs_config],
                        enabled=geofencing_enabled,
                        use_home_location=use_home_location,
                        home_zone_radius=home_zone_radius,
                    )
                )
                
            await asyncio.gather(*initialization_tasks, return_exceptions=False)
            
        except asyncio.TimeoutError as err:
            raise ConfigEntryNotReady(
                f"Manager initialization timeout: {err}"
            ) from err
        except ValidationError as err:
            raise ConfigEntryNotReady(
                f"Manager validation failed: {err.field} - {err.constraint}"
            ) from err
        except Exception as err:
            # PLATINUM: More specific error categorization
            error_type = err.__class__.__name__
            raise ConfigEntryNotReady(
                f"Manager initialization failed ({error_type}): {err}"
            ) from err

        # Attach runtime managers
        coordinator.attach_runtime_managers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            notification_manager=notification_manager,
            geofencing_manager=geofencing_manager,
        )

        # PLATINUM: Enhanced platform setup with specific error handling
        try:
            await hass.config_entries.async_forward_entry_setups(entry, platforms)
        except ImportError as err:
            raise ConfigEntryNotReady(
                f"Platform import failed - missing dependency: {err}"
            ) from err
        except Exception as err:
            _LOGGER.exception("Platform setup failed")
            raise ConfigEntryNotReady(
                f"Platform setup failed ({err.__class__.__name__}): {err}"
            ) from err

        # Create helpers after platforms are set up (requires HA services to be ready)
        try:
            created_helpers = await helper_manager.async_create_helpers_for_dogs(
                dogs_config, enabled_modules
            )
            
            helper_count = sum(len(helpers) for helpers in created_helpers.values())
            if helper_count > 0:
                _LOGGER.info(
                    "Created %d Home Assistant helpers for %d dogs", 
                    helper_count, 
                    len(dogs_config)
                )
                
                # Send notification about helper creation
                if notification_manager:
                    try:
                        await notification_manager.async_send_notification(
                            notification_type="system_info",
                            title="PawControl Helper Setup Complete",
                            message=f"Created {helper_count} helpers for automated feeding schedules, "
                                  f"health reminders, and other dog management tasks.",
                            priority="normal",
                        )
                    except Exception as notification_err:
                        _LOGGER.debug(
                            "Helper creation notification failed (non-critical): %s", 
                            notification_err
                        )
                        
        except Exception as helper_err:
            # Helper creation failure is non-critical for integration setup
            _LOGGER.warning(
                "Helper creation failed (non-critical): %s. "
                "You can manually create input_boolean and input_datetime helpers if needed.", 
                helper_err
            )

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
        
        # Add optional managers to runtime data
        runtime_data.helper_manager = helper_manager
        runtime_data.geofencing_manager = geofencing_manager
        runtime_data.door_sensor_manager = door_sensor_manager

        # PLATINUM: Store runtime data only in ConfigEntry.runtime_data
        entry.runtime_data = runtime_data

        # Setup daily reset scheduler with error tolerance
        try:
            reset_unsub = await async_setup_daily_reset_scheduler(hass, entry)
            if reset_unsub:
                runtime_data.daily_reset_unsub = reset_unsub
        except Exception as err:
            _LOGGER.warning(
                "Failed to setup daily reset scheduler (non-critical): %s", err
            )

        # Start background tasks
        coordinator.async_start_background_tasks()

        # Add reload listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        # Get door sensor status
        door_sensor_status = await door_sensor_manager.async_get_detection_status()
        door_sensors_configured = door_sensor_status["configured_dogs"]

        _LOGGER.info(
            "PawControl setup completed: %d dogs, %d platforms, %d helpers, profile '%s', "
            "geofencing %s, door sensors %d",
            len(dogs_config),
            len(platforms),
            helper_manager.get_helper_count(),
            profile,
            "enabled" if geofencing_manager and geofencing_manager.is_enabled() else "disabled",
            door_sensors_configured,
        )

        return True

    except (ConfigEntryNotReady, ConfigEntryAuthFailed, PawControlSetupError):
        # Re-raise expected exceptions without modification
        raise
    except Exception as err:
        # PLATINUM: Catch-all with better error context for debugging
        _LOGGER.exception("Unexpected setup error")
        raise PawControlSetupError(
            f"Unexpected setup failure ({err.__class__.__name__}): {err}"
        ) from err


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

    # Unload platforms with error tolerance
    try:
        unload_ok = await hass.config_entries.async_unload_platforms(entry, platforms)
    except Exception as err:
        _LOGGER.error("Error unloading platforms: %s", err)
        unload_ok = False

    # Cleanup runtime data with enhanced error handling
    if runtime_data:
        # Cleanup door sensor manager
        if hasattr(runtime_data, "door_sensor_manager") and runtime_data.door_sensor_manager:
            try:
                await runtime_data.door_sensor_manager.async_cleanup()
                _LOGGER.debug("Door sensor manager cleanup completed")
            except Exception as err:
                _LOGGER.warning("Error during door sensor manager cleanup: %s", err)

        # Cleanup geofencing manager
        if hasattr(runtime_data, "geofencing_manager") and runtime_data.geofencing_manager:
            try:
                await runtime_data.geofencing_manager.async_cleanup()
                _LOGGER.debug("Geofencing manager cleanup completed")
            except Exception as err:
                _LOGGER.warning("Error during geofencing manager cleanup: %s", err)
        
        # Cleanup helper manager
        if hasattr(runtime_data, "helper_manager") and runtime_data.helper_manager:
            try:
                await runtime_data.helper_manager.async_cleanup()
                _LOGGER.debug("Helper manager cleanup completed")
            except Exception as err:
                _LOGGER.warning("Error during helper manager cleanup: %s", err)

        # Shutdown daily reset scheduler
        if (
            hasattr(runtime_data, "daily_reset_unsub")
            and runtime_data.daily_reset_unsub
        ):
            try:
                runtime_data.daily_reset_unsub()
            except Exception as err:
                _LOGGER.warning("Error canceling daily reset scheduler: %s", err)

        # PLATINUM: Enhanced manager shutdown with specific error handling
        managers_to_shutdown = [
            ("coordinator", runtime_data.coordinator),
            ("data_manager", runtime_data.data_manager),
            ("notification_manager", runtime_data.notification_manager),
            ("feeding_manager", runtime_data.feeding_manager),
            ("walk_manager", runtime_data.walk_manager),
        ]

        shutdown_tasks = []
        for manager_name, manager in managers_to_shutdown:
            if hasattr(manager, "async_shutdown"):
                shutdown_tasks.append((manager_name, manager.async_shutdown()))

        if shutdown_tasks:
            shutdown_results = await asyncio.gather(
                *[task for _, task in shutdown_tasks], return_exceptions=True
            )

            for (manager_name, _), result in zip(shutdown_tasks, shutdown_results, strict=False):
                if isinstance(result, Exception):
                    _LOGGER.warning(
                        "Error during %s shutdown: %s (%s)", 
                        manager_name, 
                        result,
                        result.__class__.__name__
                    )

        # Clear coordinator references
        try:
            runtime_data.coordinator.clear_runtime_managers()
        except Exception as err:
            _LOGGER.warning("Error clearing coordinator references: %s", err)

    # Clear caches
    _PLATFORM_CACHE.clear()

    # PLATINUM: Enhanced service manager cleanup
    domain_data = hass.data.get(DOMAIN, {})
    service_manager = domain_data.get("service_manager")
    if service_manager and hasattr(service_manager, "_tracked_entries"):
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
