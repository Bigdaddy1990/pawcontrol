"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping, Sequence
from typing import Any, Final

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

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
from .garden_manager import GardenManager
from .geofencing import PawControlGeofencing
from .gps_manager import GPSGeofenceManager
from .helper_manager import PawControlHelperManager
from .notifications import PawControlNotificationManager
from .repairs import async_check_for_issues
from .runtime_data import get_runtime_data, pop_runtime_data, store_runtime_data
from .script_manager import PawControlScriptManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .utils import sanitize_dog_id
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# PawControl is configured exclusively via the UI/config entries
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# OPTIMIZED: Enhanced platform determination cache with TTL and monitoring
type PlatformCacheKey = tuple[int, str, frozenset[str]]
type PlatformTuple = tuple[Platform, ...]
type CacheEntry = tuple[PlatformTuple, float]  # (platforms, timestamp)

_DEFAULT_PLATFORMS: Final[PlatformTuple] = (
    Platform.BUTTON,
    Platform.SENSOR,
)

# Performance optimizations
_PLATFORM_CACHE: dict[PlatformCacheKey, CacheEntry] = {}
_CACHE_TTL_SECONDS: Final[int] = 3600  # 1 hour cache TTL
_MAX_CACHE_SIZE: Final[int] = 100  # Prevent unbounded memory growth
_MANAGER_INIT_TIMEOUT: Final[int] = 30  # 30 seconds per manager
_COORDINATOR_REFRESH_TIMEOUT: Final[int] = 45  # 45 seconds for coordinator
_COORDINATOR_SETUP_TIMEOUT: Final[int] = 15  # 15 seconds for coordinator pre-setup


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


def _cleanup_platform_cache() -> None:
    """Clean up expired cache entries to prevent memory growth."""
    now = time.time()
    expired_keys = [
        key
        for key, (_, timestamp) in _PLATFORM_CACHE.items()
        if now - timestamp > _CACHE_TTL_SECONDS
    ]

    for key in expired_keys:
        del _PLATFORM_CACHE[key]

    # Enforce maximum cache size
    if len(_PLATFORM_CACHE) > _MAX_CACHE_SIZE:
        # Remove oldest entries
        sorted_entries = sorted(
            _PLATFORM_CACHE.items(),
            key=lambda x: x[1][1],  # Sort by timestamp
        )
        excess_count = len(_PLATFORM_CACHE) - _MAX_CACHE_SIZE
        for key, _ in sorted_entries[:excess_count]:
            del _PLATFORM_CACHE[key]

    if expired_keys:
        _LOGGER.debug("Cleaned up %d expired platform cache entries", len(expired_keys))


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
    now = time.time()

    # Check cache with TTL
    if cache_key in _PLATFORM_CACHE:
        platforms, timestamp = _PLATFORM_CACHE[cache_key]
        if now - timestamp <= _CACHE_TTL_SECONDS:
            return platforms
        else:
            # Remove expired entry
            del _PLATFORM_CACHE[cache_key]

    # Calculate platforms
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

    # Cache with timestamp
    _PLATFORM_CACHE[cache_key] = (ordered_platforms, now)

    # Periodic cache cleanup
    if len(_PLATFORM_CACHE) % 10 == 0:  # Every 10th call
        _cleanup_platform_cache()

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


async def _async_initialize_manager_with_timeout(
    manager_name: str, coro: Any, timeout: int = _MANAGER_INIT_TIMEOUT
) -> None:
    """Initialize a manager with timeout and proper error handling.

    Args:
        manager_name: Name of the manager for logging
        coro: Coroutine to await
        timeout: Timeout in seconds

    Raises:
        asyncio.TimeoutError: If initialization times out
        Exception: If initialization fails
    """
    start_time = time.time()
    try:
        await asyncio.wait_for(coro, timeout=timeout)
        duration = time.time() - start_time
        _LOGGER.debug("Initialized %s in %.2f seconds", manager_name, duration)
    except TimeoutError:
        duration = time.time() - start_time
        _LOGGER.error(
            "Manager %s initialization timed out after %.2f seconds",
            manager_name,
            duration,
        )
        raise
    except Exception as err:
        duration = time.time() - start_time
        _LOGGER.error(
            "Manager %s initialization failed after %.2f seconds: %s",
            manager_name,
            duration,
            err,
        )
        raise


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
    setup_start_time = time.time()
    _LOGGER.debug("Setting up PawControl integration entry: %s", entry.entry_id)

    try:
        # Validate dogs configuration with specific error handling
        dogs_config_raw = entry.data.get(CONF_DOGS, [])
        if not dogs_config_raw:
            raise ConfigurationError(
                "dogs_configuration",
                dogs_config_raw,
                "No dogs configured in integration setup",
            )

        if not isinstance(dogs_config_raw, list):
            raise ConfigurationError(
                "dogs_configuration",
                type(dogs_config_raw).__name__,
                "Dogs configuration must be a list",
            )

        # PLATINUM: Validate each dog config with specific errors
        dogs_config: list[DogConfigData] = []
        for i, dog in enumerate(dogs_config_raw):
            if not isinstance(dog, dict) or not dog.get(CONF_DOG_ID):
                raise ConfigurationError(
                    f"dog_config_{i}",
                    dog,
                    f"Invalid dog configuration at index {i}: missing or invalid dog_id",
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

        # Initialize managers with specific error handling and timeout protection
        manager_init_start = time.time()
        try:
            data_manager = PawControlDataManager(hass, entry.entry_id)
            notification_manager = PawControlNotificationManager(
                hass, entry.entry_id, session=session
            )
            feeding_manager = FeedingManager()
            walk_manager = WalkManager()
            entity_factory = EntityFactory(coordinator)
            helper_manager = PawControlHelperManager(hass, entry)
            script_manager = PawControlScriptManager(hass, entry)
            door_sensor_manager = DoorSensorManager(hass, entry.entry_id)
            garden_manager = GardenManager(hass, entry.entry_id)

            gps_geofence_manager = None
            if any(
                dog.get("modules", {}).get(MODULE_GPS, False) for dog in dogs_config
            ):
                gps_geofence_manager = GPSGeofenceManager(hass)
                gps_geofence_manager.set_notification_manager(notification_manager)
                _LOGGER.debug("GPS geofence manager created for GPS-enabled dogs")
            else:
                _LOGGER.debug(
                    "GPS geofence manager not created - no GPS modules enabled"
                )

            # Initialize geofencing manager if GPS module is enabled for any dog
            geofencing_manager = None
            if any(
                dog.get("modules", {}).get(MODULE_GPS, False) for dog in dogs_config
            ):
                geofencing_manager = PawControlGeofencing(hass, entry.entry_id)
                geofencing_manager.set_notification_manager(notification_manager)
                _LOGGER.debug("Geofencing manager created for GPS-enabled dogs")
            else:
                _LOGGER.debug("Geofencing manager not created - no GPS modules enabled")

        except Exception as err:
            raise PawControlSetupError(
                f"Manager initialization failed: {err.__class__.__name__}: {err}"
            ) from err

        manager_init_duration = time.time() - manager_init_start
        _LOGGER.debug(
            "Manager creation completed in %.2f seconds", manager_init_duration
        )

        # PLATINUM: Enhanced coordinator pre-setup and refresh with timeouts
        coordinator_setup_start = time.time()
        try:
            await asyncio.wait_for(
                coordinator.async_prepare_entry(),
                timeout=_COORDINATOR_SETUP_TIMEOUT,
            )
            coordinator_setup_duration = time.time() - coordinator_setup_start
            _LOGGER.debug(
                "Coordinator pre-setup completed in %.2f seconds",
                coordinator_setup_duration,
            )
        except TimeoutError as err:
            coordinator_setup_duration = time.time() - coordinator_setup_start
            raise ConfigEntryNotReady(
                f"Coordinator pre-setup timeout after {coordinator_setup_duration:.2f}s"
            ) from err
        except ConfigEntryAuthFailed:
            raise
        except (OSError, ConnectionError) as err:
            raise ConfigEntryNotReady(
                f"Network connectivity issue during coordinator pre-setup: {err}"
            ) from err

        coordinator_refresh_start = time.time()
        try:
            await asyncio.wait_for(
                coordinator.async_config_entry_first_refresh(),
                timeout=_COORDINATOR_REFRESH_TIMEOUT,
            )
            coordinator_refresh_duration = time.time() - coordinator_refresh_start
            _LOGGER.debug(
                "Coordinator refresh completed in %.2f seconds",
                coordinator_refresh_duration,
            )
        except TimeoutError as err:
            coordinator_refresh_duration = time.time() - coordinator_refresh_start
            raise ConfigEntryNotReady(
                "Coordinator initialization timeout after "
                f"{coordinator_refresh_duration:.2f}s"
            ) from err
        except ConfigEntryAuthFailed:
            raise  # Re-raise auth failures directly
        except (OSError, ConnectionError) as err:
            raise ConfigEntryNotReady(
                f"Network connectivity issue during coordinator setup: {err}"
            ) from err

        # Initialize other managers with timeout protection and parallel execution
        managers_init_start = time.time()
        try:
            initialization_tasks = [
                _async_initialize_manager_with_timeout(
                    "data_manager", data_manager.async_initialize()
                ),
                _async_initialize_manager_with_timeout(
                    "notification_manager", notification_manager.async_initialize()
                ),
                _async_initialize_manager_with_timeout(
                    "feeding_manager",
                    feeding_manager.async_initialize(
                        [dict(dog) for dog in dogs_config]
                    ),
                ),
                _async_initialize_manager_with_timeout(
                    "walk_manager",
                    walk_manager.async_initialize(
                        [dog[CONF_DOG_ID] for dog in dogs_config]
                    ),
                ),
                _async_initialize_manager_with_timeout(
                    "helper_manager", helper_manager.async_initialize()
                ),
                _async_initialize_manager_with_timeout(
                    "script_manager", script_manager.async_initialize()
                ),
                _async_initialize_manager_with_timeout(
                    "door_sensor_manager",
                    door_sensor_manager.async_initialize(
                        dogs=dogs_config,
                        walk_manager=walk_manager,
                        notification_manager=notification_manager,
                    ),
                ),
                _async_initialize_manager_with_timeout(
                    "garden_manager",
                    garden_manager.async_initialize(
                        dogs=[dog[CONF_DOG_ID] for dog in dogs_config],
                        notification_manager=notification_manager,
                        door_sensor_manager=door_sensor_manager,
                    ),
                ),
            ]

            # Add geofencing initialization if manager was created
            if geofencing_manager:
                geofence_options = entry.options.get("geofence_settings", {})
                geofencing_enabled = geofence_options.get("geofencing_enabled", False)
                use_home_location = geofence_options.get("use_home_location", True)
                home_zone_radius = geofence_options.get("geofence_radius_m", 50)

                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "geofencing_manager",
                        geofencing_manager.async_initialize(
                            dogs=[dog[CONF_DOG_ID] for dog in dogs_config],
                            enabled=geofencing_enabled,
                            use_home_location=use_home_location,
                            home_zone_radius=home_zone_radius,
                        ),
                    )
                )

            await asyncio.gather(*initialization_tasks, return_exceptions=False)

            managers_init_duration = time.time() - managers_init_start
            _LOGGER.debug(
                "All managers initialized in %.2f seconds", managers_init_duration
            )

        except TimeoutError as err:
            managers_init_duration = time.time() - managers_init_start
            raise ConfigEntryNotReady(
                f"Manager initialization timeout after {managers_init_duration:.2f}s: {err}"
            ) from err
        except ValidationError as err:
            raise ConfigEntryNotReady(
                f"Manager validation failed: {err.field} - {err.constraint}"
            ) from err
        except Exception as err:
            # PLATINUM: More specific error categorization
            error_type = err.__class__.__name__
            managers_init_duration = time.time() - managers_init_start
            raise ConfigEntryNotReady(
                f"Manager initialization failed after {managers_init_duration:.2f}s ({error_type}): {err}"
            ) from err

        # RESILIENCE: Share coordinator's ResilienceManager with other managers
        # This ensures centralized monitoring and consistent circuit breaker behavior
        if gps_geofence_manager:
            gps_geofence_manager.resilience_manager = coordinator.resilience_manager
            _LOGGER.debug("Shared ResilienceManager with GPS manager")

        if notification_manager:
            notification_manager.resilience_manager = coordinator.resilience_manager
            _LOGGER.debug("Shared ResilienceManager with Notification manager")

        # Attach runtime managers
        coordinator.attach_runtime_managers(
            data_manager=data_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            notification_manager=notification_manager,
            gps_geofence_manager=gps_geofence_manager,
            geofencing_manager=geofencing_manager,
            garden_manager=garden_manager,
        )

        # PLATINUM: Enhanced platform setup with timeout and retry logic
        platform_setup_start = time.time()
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                await asyncio.wait_for(
                    hass.config_entries.async_forward_entry_setups(entry, platforms),
                    timeout=30,  # 30 seconds for platform setup
                )
                platform_setup_duration = time.time() - platform_setup_start
                _LOGGER.debug(
                    "Platform setup completed in %.2f seconds (attempt %d)",
                    platform_setup_duration,
                    attempt + 1,
                )
                break
            except TimeoutError as err:
                if attempt == max_retries:
                    platform_setup_duration = time.time() - platform_setup_start
                    raise ConfigEntryNotReady(
                        f"Platform setup timeout after {platform_setup_duration:.2f}s"
                    ) from err
                _LOGGER.warning(
                    "Platform setup attempt %d timed out, retrying...", attempt + 1
                )
                await asyncio.sleep(1)  # Brief delay before retry
            except ImportError as err:
                raise ConfigEntryNotReady(
                    f"Platform import failed - missing dependency: {err}"
                ) from err
            except Exception as err:
                if attempt == max_retries:
                    _LOGGER.exception("Platform setup failed")
                    raise ConfigEntryNotReady(
                        f"Platform setup failed ({err.__class__.__name__}): {err}"
                    ) from err
                _LOGGER.warning(
                    "Platform setup attempt %d failed: %s, retrying...",
                    attempt + 1,
                    err,
                )
                await asyncio.sleep(1)  # Brief delay before retry

        # Create helpers after platforms are set up (requires HA services to be ready)
        helpers_start = time.time()
        try:
            created_helpers = await asyncio.wait_for(
                helper_manager.async_create_helpers_for_dogs(
                    dogs_config, enabled_modules
                ),
                timeout=20,  # 20 seconds for helper creation
            )

            helper_count = sum(len(helpers) for helpers in created_helpers.values())
            helpers_duration = time.time() - helpers_start

            if helper_count > 0:
                _LOGGER.info(
                    "Created %d Home Assistant helpers for %d dogs in %.2f seconds",
                    helper_count,
                    len(dogs_config),
                    helpers_duration,
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
                            notification_err,
                        )

        except TimeoutError:
            # Helper creation timeout is non-critical
            helpers_duration = time.time() - helpers_start
            _LOGGER.warning(
                "Helper creation timed out after %.2f seconds (non-critical). "
                "You can manually create input_boolean and input_datetime helpers if needed.",
                helpers_duration,
            )
        except Exception as helper_err:
            # Helper creation failure is non-critical for integration setup
            helpers_duration = time.time() - helpers_start
            _LOGGER.warning(
                "Helper creation failed after %.2f seconds (non-critical): %s. "
                "You can manually create input_boolean and input_datetime helpers if needed.",
                helpers_duration,
                helper_err,
            )

        # Generate automation scripts promised by the public documentation
        scripts_start = time.time()
        try:
            created_scripts = await asyncio.wait_for(
                script_manager.async_generate_scripts_for_dogs(
                    dogs_config, enabled_modules
                ),
                timeout=20,
            )

            script_count = sum(len(scripts) for scripts in created_scripts.values())
            scripts_duration = time.time() - scripts_start

            if script_count > 0:
                _LOGGER.info(
                    "Created %d PawControl automation scripts for %d dogs in %.2f seconds",
                    script_count,
                    len(created_scripts),
                    scripts_duration,
                )

                if notification_manager:
                    try:
                        await notification_manager.async_send_notification(
                            notification_type="system_info",
                            title="PawControl scripts ready",
                            message=(
                                "Generated PawControl confirmation, reset, and setup scripts "
                                f"for {script_count} automation step(s)."
                            ),
                            priority="normal",
                        )
                    except Exception as notification_err:
                        _LOGGER.debug(
                            "Script creation notification failed (non-critical): %s",
                            notification_err,
                        )

        except TimeoutError:
            scripts_duration = time.time() - scripts_start
            _LOGGER.warning(
                "Script creation timed out after %.2f seconds (non-critical). "
                "You can create the scripts manually from Home Assistant's script editor.",
                scripts_duration,
            )
        except (HomeAssistantError, Exception) as script_err:
            scripts_duration = time.time() - scripts_start
            error_type = (
                "skipped" if isinstance(script_err, HomeAssistantError) else "failed"
            )
            _LOGGER.warning(
                "Script creation %s after %.2f seconds (non-critical): %s",
                error_type,
                scripts_duration,
                script_err,
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
        runtime_data.script_manager = script_manager
        runtime_data.geofencing_manager = geofencing_manager
        runtime_data.gps_geofence_manager = gps_geofence_manager
        runtime_data.door_sensor_manager = door_sensor_manager
        runtime_data.garden_manager = garden_manager
        runtime_data.device_api_client = coordinator.api_client

        # Store runtime data using the legacy hass.data pattern for compatibility
        store_runtime_data(hass, entry, runtime_data)

        # Setup daily reset scheduler with error tolerance
        try:
            reset_unsub = await async_setup_daily_reset_scheduler(hass, entry)
            if reset_unsub:
                runtime_data.daily_reset_unsub = reset_unsub
        except Exception as err:
            _LOGGER.warning(
                "Failed to setup daily reset scheduler (non-critical): %s", err
            )

        # Start background tasks with health monitoring
        coordinator.async_start_background_tasks()

        # Start background task health monitoring
        monitor_task = hass.async_create_task(
            _async_monitor_background_tasks(runtime_data)
        )
        runtime_data.background_monitor_task = monitor_task

        # Add reload listener
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))

        # Get door sensor status
        door_sensor_status = await door_sensor_manager.async_get_detection_status()
        door_sensors_configured = door_sensor_status["configured_dogs"]

        # Run repair checks to surface actionable issues in the repairs panel
        await async_check_for_issues(hass, entry)

        setup_duration = time.time() - setup_start_time
        _LOGGER.info(
            "PawControl setup completed in %.2f seconds: %d dogs, %d platforms, %d helpers, "
            "profile '%s', geofencing %s, door sensors %d",
            setup_duration,
            len(dogs_config),
            len(platforms),
            helper_manager.get_helper_count(),
            profile,
            "enabled"
            if geofencing_manager and geofencing_manager.is_enabled()
            else "disabled",
            door_sensors_configured,
        )

        return True

    except (ConfigEntryNotReady, ConfigEntryAuthFailed, PawControlSetupError):
        # Re-raise expected exceptions without modification
        raise
    except Exception as err:
        # PLATINUM: Catch-all with better error context for debugging
        setup_duration = time.time() - setup_start_time
        _LOGGER.exception("Unexpected setup error after %.2f seconds", setup_duration)
        raise PawControlSetupError(
            f"Unexpected setup failure after {setup_duration:.2f}s ({err.__class__.__name__}): {err}"
        ) from err


async def _async_monitor_background_tasks(runtime_data: PawControlRuntimeData) -> None:
    """Monitor background tasks and restart if needed.

    Args:
        runtime_data: Runtime data containing managers
    """
    monitoring_interval = 300  # 5 minutes

    while True:
        try:
            await asyncio.sleep(monitoring_interval)

            # Check garden manager background tasks
            if hasattr(runtime_data, "garden_manager") and runtime_data.garden_manager:
                garden_manager = runtime_data.garden_manager

                # Check if cleanup task is still running
                if (
                    hasattr(garden_manager, "_cleanup_task")
                    and garden_manager._cleanup_task
                    and garden_manager._cleanup_task.done()
                ):
                    _LOGGER.warning(
                        "Garden manager cleanup task died, attempting restart"
                    )
                    # Task would be restarted by the manager's internal logic

                # Check if stats update task is still running
                if (
                    hasattr(garden_manager, "_stats_update_task")
                    and garden_manager._stats_update_task
                    and garden_manager._stats_update_task.done()
                ):
                    _LOGGER.warning(
                        "Garden manager stats update task died, attempting restart"
                    )
                    # Task would be restarted by the manager's internal logic

            # Log task health status periodically
            _LOGGER.debug("Background task health check completed")

        except asyncio.CancelledError:
            _LOGGER.debug("Background task monitoring cancelled")
            break
        except Exception as err:
            _LOGGER.error("Error in background task monitoring: %s", err)
            # Continue monitoring despite errors


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    unload_start_time = time.time()
    runtime_data = get_runtime_data(hass, entry)

    # Get platforms for unloading
    if runtime_data:
        dogs = runtime_data.dogs
        profile = runtime_data.entity_profile
    else:
        dogs = entry.data.get(CONF_DOGS, [])
        profile = entry.options.get("entity_profile", "standard")

    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    # Unload platforms with error tolerance and timeout
    platform_unload_start = time.time()
    try:
        unload_ok = await asyncio.wait_for(
            hass.config_entries.async_unload_platforms(entry, platforms),
            timeout=30,  # 30 seconds for platform unload
        )
    except (TimeoutError, Exception) as err:
        platform_unload_duration = time.time() - platform_unload_start
        if isinstance(err, TimeoutError):
            _LOGGER.error(
                "Platform unload timed out after %.2f seconds",
                platform_unload_duration,
            )
        else:
            _LOGGER.error(
                "Error unloading platforms after %.2f seconds: %s",
                platform_unload_duration,
                err,
            )
        return False

    platform_unload_duration = time.time() - platform_unload_start
    _LOGGER.debug("Platform unload completed in %.2f seconds", platform_unload_duration)

    if not unload_ok:
        _LOGGER.error("One or more platforms failed to unload cleanly")
        return False

    # Cleanup runtime data with enhanced error handling and timeouts
    if runtime_data:
        monitor_task = getattr(runtime_data, "background_monitor_task", None)
        if monitor_task:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                _LOGGER.debug("Background monitor task cancelled")
            except Exception as err:  # pragma: no cover - defensive logging
                _LOGGER.warning("Error while awaiting background monitor task: %s", err)
            finally:
                runtime_data.background_monitor_task = None

        cleanup_start = time.time()

        # Define manager cleanup tasks with timeouts
        cleanup_tasks = []

        # Cleanup door sensor manager
        if (
            hasattr(runtime_data, "door_sensor_manager")
            and runtime_data.door_sensor_manager
        ):
            cleanup_tasks.append(
                (
                    "door_sensor_manager",
                    runtime_data.door_sensor_manager.async_cleanup(),
                )
            )

        # Cleanup geofencing manager
        if (
            hasattr(runtime_data, "geofencing_manager")
            and runtime_data.geofencing_manager
        ):
            cleanup_tasks.append(
                ("geofencing_manager", runtime_data.geofencing_manager.async_cleanup())
            )

        # Cleanup garden manager
        if hasattr(runtime_data, "garden_manager") and runtime_data.garden_manager:
            cleanup_tasks.append(
                ("garden_manager", runtime_data.garden_manager.async_cleanup())
            )

        # Cleanup helper manager
        if hasattr(runtime_data, "helper_manager") and runtime_data.helper_manager:
            cleanup_tasks.append(
                ("helper_manager", runtime_data.helper_manager.async_cleanup())
            )

        if hasattr(runtime_data, "script_manager") and runtime_data.script_manager:
            cleanup_tasks.append(
                ("script_manager", runtime_data.script_manager.async_cleanup())
            )

        # Execute cleanup tasks with individual timeouts
        for manager_name, cleanup_coro in cleanup_tasks:
            try:
                await asyncio.wait_for(
                    cleanup_coro, timeout=10
                )  # 10 seconds per manager
                _LOGGER.debug(
                    "%s cleanup completed", manager_name.replace("_", " ").title()
                )
            except TimeoutError:
                _LOGGER.warning(
                    "%s cleanup timed out", manager_name.replace("_", " ").title()
                )
            except Exception as err:
                _LOGGER.warning(
                    "Error during %s cleanup: %s", manager_name.replace("_", " "), err
                )

        # Shutdown daily reset scheduler
        if (
            hasattr(runtime_data, "daily_reset_unsub")
            and runtime_data.daily_reset_unsub
        ):
            try:
                runtime_data.daily_reset_unsub()
            except Exception as err:
                _LOGGER.warning("Error canceling daily reset scheduler: %s", err)

        # PLATINUM: Enhanced manager shutdown with individual timeouts
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
                # Wrap each shutdown in a timeout
                shutdown_tasks.append(
                    (
                        manager_name,
                        asyncio.wait_for(manager.async_shutdown(), timeout=10),
                    )
                )

        if shutdown_tasks:
            shutdown_results = await asyncio.gather(
                *[task for _, task in shutdown_tasks], return_exceptions=True
            )

            for (manager_name, _), result in zip(
                shutdown_tasks, shutdown_results, strict=False
            ):
                if isinstance(result, Exception):
                    if isinstance(result, asyncio.TimeoutError):
                        _LOGGER.warning(
                            "%s shutdown timed out",
                            manager_name.replace("_", " ").title(),
                        )
                    else:
                        _LOGGER.warning(
                            "Error during %s shutdown: %s (%s)",
                            manager_name.replace("_", " "),
                            result,
                            result.__class__.__name__,
                        )

        # Clear coordinator references
        try:
            runtime_data.coordinator.clear_runtime_managers()
        except Exception as err:
            _LOGGER.warning("Error clearing coordinator references: %s", err)

        cleanup_duration = time.time() - cleanup_start
        _LOGGER.debug(
            "Runtime data cleanup completed in %.2f seconds", cleanup_duration
        )

    pop_runtime_data(hass, entry)

    # Clear caches with size reporting
    cache_size = len(_PLATFORM_CACHE)
    _PLATFORM_CACHE.clear()
    if cache_size > 0:
        _LOGGER.debug("Cleared platform cache with %d entries", cache_size)

    # PLATINUM: Enhanced service manager cleanup
    domain_data = hass.data.get(DOMAIN, {})
    service_manager = domain_data.get("service_manager")
    if service_manager:
        loaded_entries = hass.config_entries.async_loaded_entries(DOMAIN)
        # This function is called while the entry is still considered loaded.
        # So if there's only one loaded entry, it must be this one.
        if len(loaded_entries) <= 1:
            try:
                await asyncio.wait_for(service_manager.async_shutdown(), timeout=10)
            except TimeoutError:
                _LOGGER.warning("Service manager shutdown timed out")
            except Exception as err:
                _LOGGER.warning("Error shutting down service manager: %s", err)

    unload_duration = time.time() - unload_start_time
    _LOGGER.info(
        "PawControl unload completed in %.2f seconds: success=%s",
        unload_duration,
        unload_ok,
    )
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    device_entry: DeviceEntry,
) -> bool:
    """Determine whether a stale PawControl device can be removed."""

    def _iter_dogs(source: Any) -> list[Mapping[str, Any]]:
        if isinstance(source, Mapping):
            dogs: list[Mapping[str, Any]] = []
            for dog_id, dog_cfg in source.items():
                if isinstance(dog_cfg, Mapping):
                    dog_data = dict(dog_cfg)
                    dog_data.setdefault(CONF_DOG_ID, str(dog_id))
                    dogs.append(dog_data)
            return dogs

        if isinstance(source, Sequence) and not isinstance(source, (str, bytes, bytearray)):
            return [dog for dog in source if isinstance(dog, Mapping)]

        return []

    identifiers = {
        identifier
        for identifier in device_entry.identifiers
        if isinstance(identifier, tuple)
        and len(identifier) == 2
        and identifier[0] == DOMAIN
    }

    if not identifiers:
        _LOGGER.debug(
            "Device %s is not managed by PawControl; skipping removal", device_entry.id
        )
        return False

    active_ids: dict[str, str] = {}

    runtime_data = get_runtime_data(hass, entry)
    if runtime_data and isinstance(runtime_data.dogs, Sequence):
        for dog in runtime_data.dogs:
            if isinstance(dog, Mapping):
                dog_id = dog.get(CONF_DOG_ID)
                if isinstance(dog_id, str):
                    active_ids[sanitize_dog_id(dog_id)] = dog_id

    entry_dogs = _iter_dogs(entry.data.get(CONF_DOGS))
    for dog in entry_dogs:
        dog_id = dog.get(CONF_DOG_ID)
        if isinstance(dog_id, str):
            active_ids.setdefault(sanitize_dog_id(dog_id), dog_id)

    configured = {identifier[1] for identifier in identifiers}

    still_present = configured & set(active_ids)
    if still_present:
        _LOGGER.debug(
            "Refusing to remove PawControl device %s because dogs %s are still configured",
            device_entry.id,
            ", ".join(sorted(active_ids[dog] for dog in still_present)),
        )
        return False

    _LOGGER.debug(
        "Allowing removal of PawControl device %s with identifiers %s", device_entry.id, configured
    )
    return True


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    reload_start_time = time.time()
    _LOGGER.debug("Reloading PawControl integration entry: %s", entry.entry_id)

    unload_ok = await async_unload_entry(hass, entry)
    if not unload_ok:
        _LOGGER.warning(
            "Reload aborted because unload failed for entry %s", entry.entry_id
        )
        return

    await async_setup_entry(hass, entry)

    reload_duration = time.time() - reload_start_time
    _LOGGER.info("PawControl reload completed in %.2f seconds", reload_duration)
