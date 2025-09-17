"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Final, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

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
from .health_calculator import HealthCalculator
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlConfigEntry, PawControlRuntimeData
from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

# Available platforms - using Final for immutability
ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# OPTIMIZE: Platform cache with size limits and better management
_PLATFORM_CACHE: dict[str, tuple[Platform, ...]] = {}
_PLATFORM_CACHE_SIZE_LIMIT = 100

# Entity count cache for deterministic entity estimation
_ENTITY_COUNT_CACHE: dict[str, int] = {}
_ENTITY_COUNT_CACHE_SIZE_LIMIT = 128

# OPTIMIZE: Manager initialization timeout and retry settings
MANAGER_INIT_TIMEOUT = 30.0  # seconds
MAX_MANAGER_RETRIES = 2


def get_platforms_for_profile_and_modules(
    dogs_config: list[DogConfigData], profile: str
) -> tuple[Platform, ...]:
    """Determine required platforms based on dogs, modules and profile.

    OPTIMIZE: Enhanced with caching, single-pass iteration, and early validation.

    Args:
        dogs_config: List of dog configurations
        profile: Entity profile name

    Returns:
        Tuple of required platforms sorted for deterministic setup ordering
    """
    if not dogs_config:
        return (Platform.BUTTON, Platform.SENSOR)

    signature_source: list[tuple[str, tuple[tuple[str, bool], ...]]] = []
    enabled_modules: set[str] = set()
    for dog in dogs_config:
        modules = dog.get("modules", {})
        if isinstance(modules, Mapping):
            module_items = tuple(
                sorted((module, bool(enabled)) for module, enabled in modules.items())
            )
            enabled_modules.update(
                module for module, enabled in module_items if enabled
            )
        else:
            module_items = ()

        dog_id = str(dog.get(CONF_DOG_ID, ""))
        signature_source.append((dog_id, module_items))

    dogs_signature = hash(str(sorted(signature_source)))

    normalized_profile = profile
    if normalized_profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        normalized_profile = "standard"

    cache_key = f"{len(dogs_config)}_{normalized_profile}_{dogs_signature}"

    if cache_key in _PLATFORM_CACHE:
        return _PLATFORM_CACHE[cache_key]

    if len(_PLATFORM_CACHE) >= _PLATFORM_CACHE_SIZE_LIMIT:
        oldest_keys = list(_PLATFORM_CACHE.keys())[: _PLATFORM_CACHE_SIZE_LIMIT // 2]
        for key in oldest_keys:
            _PLATFORM_CACHE.pop(key, None)
        _LOGGER.debug("Cleared platform cache: removed %d entries", len(oldest_keys))

    # Base platforms always included
    platforms: set[Platform] = {Platform.SENSOR, Platform.BUTTON}

    # OPTIMIZE: Profile-specific platform determination with optimized logic
    if normalized_profile == "basic":
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
        if normalized_profile == "advanced" and enabled_modules:
            platforms.add(Platform.DATETIME)
        elif normalized_profile == "gps_focus":
            platforms.add(Platform.NUMBER)
        elif normalized_profile == "health_focus":
            platforms.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    result_platforms = tuple(sorted(platforms, key=lambda item: item.value))
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
    domain_data = hass.data.setdefault(DOMAIN, {})

    # Register integration-level services at startup so they are available
    # before any config entries are loaded. The service manager stores itself
    # in domain data and avoids double registration automatically.
    try:
        if "service_manager" not in domain_data:
            domain_data["service_manager"] = PawControlServiceManager(hass)
            _LOGGER.debug("Registered PawControl services during async_setup")
    except asyncio.CancelledError:  # pragma: no cover - defensive logging
        raise
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.warning("Failed to register PawControl services: %s", err)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Set up Paw Control from a config entry.

    OPTIMIZE: Enhanced with parallel manager initialization, comprehensive error handling,
    and performance monitoring for Platinum compliance.

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
    from .types import is_dog_config_valid

    dogs_config_raw = entry.data.get(CONF_DOGS, [])
    if not dogs_config_raw:
        raise ConfigEntryNotReady("No dogs configured")

    if not isinstance(dogs_config_raw, list) or not all(
        is_dog_config_valid(dog) for dog in dogs_config_raw
    ):
        _LOGGER.error("Invalid dog configuration detected in entry %s", entry.entry_id)
        raise PawControlSetupError(
            "Invalid dog configuration. Please remove and re-add the integration."
        )
    dogs_config = cast(list[DogConfigData], dogs_config_raw)

    # Enhanced validation for each dog configuration
    for dog in dogs_config:
        if not dog.get(CONF_DOG_ID):
            raise ConfigEntryNotReady(
                f"Invalid dog configuration: missing {CONF_DOG_ID}"
            )
        # Additional validation
        if not isinstance(dog.get(CONF_DOG_ID), str) or not dog[CONF_DOG_ID].strip():
            raise ConfigEntryNotReady(f"Invalid dog ID: {dog.get(CONF_DOG_ID)}")

    # Determine and validate profile
    profile = entry.options.get("entity_profile", "standard")
    if profile not in ENTITY_PROFILES:
        _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
        profile = "standard"

    # OPTIMIZE: Calculate platforms once for reuse with caching
    platforms = get_platforms_for_profile_and_modules(dogs_config, profile)

    # OPTIMIZE: Initialize core components with proper error handling and session injection
    session = async_get_clientsession(hass)
    coordinator = PawControlCoordinator(hass, entry, session)
    data_manager = PawControlDataManager(hass, entry.entry_id)
    notification_manager = PawControlNotificationManager(hass, entry.entry_id)
    feeding_manager = FeedingManager()
    walk_manager = WalkManager()
    entity_factory = EntityFactory(coordinator)

    # OPTIMIZE: Efficient entity count estimation with caching
    total_estimated_entities = _calculate_entity_count_cached(
        dogs_config, profile, entity_factory
    )

    _LOGGER.debug(
        "Estimated %d entities for %d dogs with profile '%s'",
        total_estimated_entities,
        len(dogs_config),
        profile,
    )

    # OPTIMIZE: Parallel manager initialization with error isolation
    initialized_managers: list[Any] = []
    try:
        # Initialize coordinator first (critical dependency)
        await asyncio.wait_for(
            coordinator.async_config_entry_first_refresh(), timeout=MANAGER_INIT_TIMEOUT
        )
        initialized_managers.append(coordinator)

        # OPTIMIZE: Initialize remaining managers in parallel with controlled concurrency
        manager_tasks = [
            (
                "data_manager",
                _initialize_manager_with_retry(
                    data_manager.async_initialize, "Data manager", MAX_MANAGER_RETRIES
                ),
            ),
            (
                "notification_manager",
                _initialize_manager_with_retry(
                    notification_manager.async_initialize,
                    "Notification manager",
                    MAX_MANAGER_RETRIES,
                ),
            ),
            (
                "feeding_manager",
                _initialize_manager_with_retry(
                    lambda: feeding_manager.async_initialize(dogs_config),
                    "Feeding manager",
                    MAX_MANAGER_RETRIES,
                ),
            ),
            (
                "walk_manager",
                _initialize_manager_with_retry(
                    lambda: walk_manager.async_initialize(
                        [dog[CONF_DOG_ID] for dog in dogs_config]
                    ),
                    "Walk manager",
                    MAX_MANAGER_RETRIES,
                ),
            ),
        ]

        # Execute manager initialization concurrently
        results = await asyncio.gather(
            *(task for _, task in manager_tasks),
            return_exceptions=True,
        )

        # Process results and collect successfully initialized managers
        managers = [data_manager, notification_manager, feeding_manager, walk_manager]
        for i, (manager_name, result) in enumerate(
            zip([name for name, _ in manager_tasks], results, strict=False)
        ):
            if isinstance(result, Exception):
                await _cleanup_managers(initialized_managers)
                raise ConfigEntryNotReady(
                    f"{manager_name.replace('_', ' ').title()} initialization failed: {result}"
                ) from result
            else:
                initialized_managers.append(managers[i])
                _LOGGER.debug(
                    "%s initialized successfully",
                    manager_name.replace("_", " ").title(),
                )

    except (TimeoutError, ConfigEntryNotReady):
        # Cleanup on initialization failure
        await _cleanup_managers(initialized_managers)
        raise
    except asyncio.CancelledError:
        await _cleanup_managers(initialized_managers)
        raise
    except Exception as err:
        # Cleanup on unexpected failure
        await _cleanup_managers(initialized_managers)
        raise ConfigEntryNotReady(f"Manager initialization failed: {err}") from err

    # Attach runtime managers to the coordinator for service access
    coordinator.attach_runtime_managers(
        data_manager=data_manager,
        feeding_manager=feeding_manager,
        walk_manager=walk_manager,
        notification_manager=notification_manager,
    )

    # OPTIMIZE: Set up platforms with comprehensive error handling and recovery
    try:
        await asyncio.wait_for(
            hass.config_entries.async_forward_entry_setups(entry, platforms),
            timeout=60.0,  # Allow more time for platform setup
        )
    except TimeoutError as err:
        await _cleanup_managers(initialized_managers)
        raise ConfigEntryNotReady("Platform setup timeout after 60 seconds") from err
    except asyncio.CancelledError:
        await _cleanup_managers(initialized_managers)
        raise
    except Exception as err:
        # Cleanup managers if platform setup fails
        await _cleanup_managers(initialized_managers)
        if isinstance(err, ImportError):
            raise ConfigEntryNotReady(f"Platform import failed: {err}") from err
        elif isinstance(err, ValueError | TypeError):
            raise ConfigEntryNotReady(f"Platform setup failed: {err}") from err
        else:
            raise ConfigEntryNotReady(
                f"Unexpected platform setup error: {err}"
            ) from err

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

    # OPTIMIZE: Add performance and error tracking
    runtime_data.performance_stats = {
        "setup_duration_ms": 0,  # Will be calculated by caller
        "estimated_entities": total_estimated_entities,
        "platforms_count": len(platforms),
        "managers_initialized": len(initialized_managers),
    }

    entry.runtime_data = runtime_data

    domain_data = hass.data.setdefault(DOMAIN, {})
    entry_data = {
        "coordinator": coordinator,
        "data_manager": data_manager,
        "notification_manager": notification_manager,
        "feeding_manager": feeding_manager,
        "walk_manager": walk_manager,
        "entity_factory": entity_factory,
        "dogs": dogs_config,
        "entity_profile": profile,
        "runtime_data": runtime_data,
    }
    domain_data[entry.entry_id] = entry_data
    domain_data["coordinator"] = coordinator
    domain_data["data_manager"] = data_manager
    domain_data["notification_manager"] = notification_manager
    domain_data["feeding_manager"] = feeding_manager
    domain_data["walk_manager"] = walk_manager
    domain_data["entity_factory"] = entity_factory
    domain_data["dogs"] = dogs_config
    domain_data["entity_profile"] = profile
    domain_data["runtime_data"] = runtime_data

    service_manager = domain_data.get("service_manager")
    if service_manager is not None:
        entry_data["service_manager"] = service_manager
    else:  # pragma: no cover - legacy fallback
        _LOGGER.debug("Service manager not registered yet; services unavailable")

    # Schedule optional daily maintenance tasks. Failure to schedule should
    # not abort the overall setup because the integration can operate without
    # the automated reset.
    try:
        reset_unsub = await async_setup_daily_reset_scheduler(hass, entry)
        if reset_unsub is not None:
            entry_data["daily_reset_unsub"] = reset_unsub
        _LOGGER.debug("Optional daily reset scheduler initialized successfully")
    except asyncio.CancelledError:
        raise
    except Exception as err:
        _LOGGER.warning("Failed to initialize daily reset scheduler: %s", err)
        # Continue setup even if scheduler fails

    # Start background tasks for coordinator
    coordinator.async_start_background_tasks()

    # Reload the integration when options change so coordinator picks up
    # new performance or external integration settings immediately.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    _LOGGER.info(
        "PawControl setup completed: %d dogs, %d platforms, profile '%s', %d entities estimated",
        len(dogs_config),
        len(platforms),
        profile,
        total_estimated_entities,
    )

    return True


async def _initialize_manager_with_retry(
    init_func: Callable[[], Awaitable[Any]],
    manager_name: str,
    max_retries: int,
) -> None:
    """Initialize manager with retry logic.

    OPTIMIZE: New function for robust manager initialization with exponential backoff.

    Args:
        init_func: Manager initialization function
        manager_name: Name for logging
        max_retries: Maximum retry attempts

    Raises:
        Exception: If all retries fail
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            await asyncio.wait_for(init_func(), timeout=MANAGER_INIT_TIMEOUT)
            if attempt > 0:
                _LOGGER.info(
                    "%s initialized successfully after %d attempts",
                    manager_name,
                    attempt + 1,
                )
            return
        except asyncio.CancelledError:
            raise
        except Exception as err:
            last_exception = err
            if attempt < max_retries:
                wait_time = 2**attempt  # Exponential backoff
                _LOGGER.warning(
                    "%s initialization failed (attempt %d/%d), retrying in %ds: %s",
                    manager_name,
                    attempt + 1,
                    max_retries + 1,
                    wait_time,
                    err,
                )
                await asyncio.sleep(wait_time)
            else:
                _LOGGER.error(
                    "%s initialization failed after %d attempts: %s",
                    manager_name,
                    max_retries + 1,
                    err,
                )

    raise last_exception or Exception(f"{manager_name} initialization failed")


def _calculate_entity_count_cached(
    dogs_config: list[DogConfigData], profile: str, entity_factory: EntityFactory
) -> int:
    """Calculate entity count with caching for performance.

    OPTIMIZE: Cached entity count calculation to avoid repeated expensive operations.

    Args:
        dogs_config: List of dog configurations
        profile: Entity profile
        entity_factory: Entity factory instance

    Returns:
        Estimated total entity count
    """
    # Create cache key
    normalized_signatures: list[tuple[str, tuple[tuple[str, bool], ...]]] = []

    for dog in dogs_config:
        raw_modules = dog.get("modules")
        if isinstance(raw_modules, Mapping):
            modules = {
                str(module): bool(enabled) for module, enabled in raw_modules.items()
            }
        else:
            modules = {}
            if raw_modules not in (None, {}):
                _LOGGER.debug(
                    "Ignoring non-mapping modules for dog %s during entity estimation (%s)",
                    dog.get(CONF_DOG_ID, "unknown"),
                    type(raw_modules).__name__,
                )

        normalized_signatures.append(
            (
                str(dog.get(CONF_DOG_ID, "")),
                tuple(sorted(modules.items())),
            )
        )

    dogs_signature = hash(str(sorted(normalized_signatures)))
    cache_key = f"entities_{len(dogs_config)}_{profile}_{dogs_signature}"

    if cache_key in _ENTITY_COUNT_CACHE:
        return _ENTITY_COUNT_CACHE[cache_key]

    # Calculate and cache result
    total = 0
    for _, modules in normalized_signatures:
        module_dict = dict(modules)
        total += entity_factory.estimate_entity_count(profile, module_dict)

    # Cache with size limit
    if len(_ENTITY_COUNT_CACHE) >= _ENTITY_COUNT_CACHE_SIZE_LIMIT:
        oldest_keys = list(_ENTITY_COUNT_CACHE.keys())[
            : _ENTITY_COUNT_CACHE_SIZE_LIMIT // 2
        ]
        for key in oldest_keys:
            _ENTITY_COUNT_CACHE.pop(key, None)

    _ENTITY_COUNT_CACHE[cache_key] = total
    return total


async def _cleanup_managers(managers: list[Any]) -> None:
    """Cleanup initialized managers on setup failure.

    OPTIMIZE: Enhanced cleanup with timeout protection and parallel execution.

    Args:
        managers: List of manager instances to cleanup
    """
    if not managers:
        return

    cleanup_tasks: list[Awaitable[None]] = []
    for manager in reversed(managers):  # Cleanup in reverse order
        if hasattr(manager, "async_shutdown"):
            # Wrap each cleanup in timeout protection
            async def safe_shutdown(mgr: Any) -> None:
                """Shut down a manager instance with timeout protection."""

                try:
                    await asyncio.wait_for(mgr.async_shutdown(), timeout=10.0)
                except TimeoutError:
                    _LOGGER.warning(
                        "Manager %s shutdown timeout", mgr.__class__.__name__
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.error(
                        "Manager %s shutdown error: %s", mgr.__class__.__name__, err
                    )

            cleanup_tasks.append(safe_shutdown(manager))

    if cleanup_tasks:
        # OPTIMIZE: Run cleanup concurrently with overall timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*cleanup_tasks, return_exceptions=True),
                timeout=30.0,  # Overall cleanup timeout
            )
        except TimeoutError:
            _LOGGER.error("Manager cleanup timeout after 30 seconds")


async def async_unload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> bool:
    """Unload a config entry.

    OPTIMIZE: Enhanced with better error handling, parallel cleanup, and timeout protection.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    domain_data = hass.data.get(DOMAIN)
    runtime_data = entry.runtime_data
    coordinator_ref: PawControlCoordinator | None = None

    # Get platform list for unloading
    if runtime_data:
        dogs = runtime_data.dogs
        profile = runtime_data.entity_profile
        coordinator_ref = runtime_data.coordinator
    else:
        dogs = entry.data.get(CONF_DOGS, [])
        profile = entry.options.get("entity_profile", "standard")
        if domain_data is not None:
            entry_store = domain_data.get(entry.entry_id)
            if isinstance(entry_store, dict):
                stored_runtime = entry_store.get("runtime_data")
                if isinstance(stored_runtime, PawControlRuntimeData):
                    coordinator_ref = stored_runtime.coordinator

            if coordinator_ref is None:
                candidate = domain_data.get("coordinator")
                if isinstance(candidate, PawControlCoordinator):
                    coordinator_ref = candidate

    platforms = get_platforms_for_profile_and_modules(dogs, profile)

    # OPTIMIZE: Unload platforms first with timeout and better error handling
    unload_ok = False
    try:
        unload_ok = await asyncio.wait_for(
            hass.config_entries.async_unload_platforms(entry, platforms),
            timeout=60.0,  # Allow more time for platform unload
        )
        if unload_ok:
            _LOGGER.debug("Platforms unloaded successfully")
        else:
            _LOGGER.warning("Some platforms failed to unload")
    except TimeoutError:
        _LOGGER.error("Platform unload timeout after 60 seconds")
        unload_ok = False
    except asyncio.CancelledError:
        raise
    except Exception as err:
        _LOGGER.error("Failed to unload platforms: %s", err)
        unload_ok = False

    # OPTIMIZE: Cleanup runtime data with parallel execution and timeout protection
    if runtime_data:
        # Shutdown managers in reverse dependency order
        managers = [
            runtime_data.walk_manager,
            runtime_data.feeding_manager,
            runtime_data.notification_manager,
            runtime_data.data_manager,
            runtime_data.coordinator,
        ]

        # Filter managers that have shutdown capability and create timeout-protected tasks
        shutdown_tasks: list[Awaitable[tuple[str, Exception | None]]] = []
        for manager in managers:
            if hasattr(manager, "async_shutdown"):

                async def safe_manager_shutdown(
                    mgr: Any,
                ) -> tuple[str, Exception | None]:
                    """Shut down a manager and report the result."""

                    try:
                        await asyncio.wait_for(mgr.async_shutdown(), timeout=15.0)
                        return mgr.__class__.__name__, None
                    except asyncio.CancelledError:
                        raise
                    except Exception as err:
                        return mgr.__class__.__name__, err

                shutdown_tasks.append(safe_manager_shutdown(manager))

        # Execute shutdown tasks with overall timeout
        if shutdown_tasks:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=45.0,  # Overall shutdown timeout
                )

                # Log results
                for result in results:
                    if isinstance(result, Exception):
                        _LOGGER.error("Manager shutdown exception: %s", result)
                    else:
                        manager_name, error = result
                        if error:
                            _LOGGER.error(
                                "Error shutting down %s: %s", manager_name, error
                            )
                        else:
                            _LOGGER.debug("%s shutdown successfully", manager_name)

            except TimeoutError:
                _LOGGER.error("Manager shutdown timeout after 45 seconds")

        entry.runtime_data = None

    if coordinator_ref is not None:
        coordinator_ref.clear_runtime_managers()

    # OPTIMIZE: Clear platform cache on unload with better management
    global _PLATFORM_CACHE
    _PLATFORM_CACHE.clear()

    _ENTITY_COUNT_CACHE.clear()

    if domain_data is not None:
        entry_store = domain_data.pop(entry.entry_id, None)
        if entry_store and (unsub := entry_store.get("daily_reset_unsub")):
            try:
                unsub()
            except Exception as err:  # pragma: no cover - best effort cleanup
                _LOGGER.debug("Error unsubscribing daily reset listener: %s", err)

        manager = domain_data.get("service_manager")
        if not any(
            isinstance(value, dict) for value in domain_data.values()
        ) and isinstance(manager, PawControlServiceManager):
            await manager.async_shutdown()

        for key in (
            "coordinator",
            "data_manager",
            "notification_manager",
            "feeding_manager",
            "walk_manager",
            "entity_factory",
            "dogs",
            "entity_profile",
            "runtime_data",
        ):
            domain_data.pop(key, None)

    _LOGGER.info(
        "PawControl unload completed: success=%s, platforms=%d, dogs=%d",
        unload_ok,
        len(platforms),
        len(dogs),
    )

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: PawControlConfigEntry) -> None:
    """Reload a config entry.

    OPTIMIZE: Enhanced reload with better state management and error handling.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.debug("Reloading PawControl integration entry: %s", entry.entry_id)

    # OPTIMIZE: Store current state for recovery if needed
    current_state = {
        "dogs_count": len(entry.data.get(CONF_DOGS, [])),
        "profile": entry.options.get("entity_profile", "standard"),
    }

    try:
        await async_unload_entry(hass, entry)
        await async_setup_entry(hass, entry)
        _LOGGER.info(
            "PawControl reload successful: %d dogs, profile '%s'",
            current_state["dogs_count"],
            current_state["profile"],
        )
    except asyncio.CancelledError:
        raise
    except Exception as err:
        _LOGGER.error("PawControl reload failed: %s", err)
        # Clear any partial state
        global _PLATFORM_CACHE
        _PLATFORM_CACHE.clear()
        _ENTITY_COUNT_CACHE.clear()
        raise
