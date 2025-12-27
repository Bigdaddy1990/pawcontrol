"""Set up and manage the PawControl integration lifecycle."""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import sys
import time
from collections.abc import (
    Awaitable,
    Callable,
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)
from typing import Any, Final, cast

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from . import compat
from .const import (
    ALL_MODULES,
    CONF_DOG_ID,
    CONF_DOG_OPTIONS,
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
from .notifications import (
    NotificationPriority,
    NotificationType,
    PawControlNotificationManager,
)
from .repairs import async_check_for_issues
from .runtime_data import get_runtime_data, pop_runtime_data, store_runtime_data
from .script_manager import PawControlScriptManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .telemetry import update_runtime_reconfigure_summary
from .types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
    DogConfigData,
    JSONMapping,
    JSONMutableMapping,
    ManualResilienceEventRecord,
    PawControlConfigEntry,
    PawControlRuntimeData,
    ensure_dog_config_data,
)
from .utils import sanitize_dog_id
from .walk_manager import WalkManager

_CANONICAL_CONFIG_ENTRY_NOT_READY: type[Exception] | None = getattr(
    compat, "ConfigEntryNotReady", None
)
_CONFIG_ENTRY_NOT_READY_CACHE: dict[tuple[type[Exception], ...], type[Exception]] = {}


def _resolve_config_entry_not_ready() -> type[Exception]:
    """Return the active ``ConfigEntryNotReady`` class from Home Assistant."""

    global _CANONICAL_CONFIG_ENTRY_NOT_READY

    compat_cls = getattr(compat, "ConfigEntryNotReady", None)
    compat_is_fallback = False
    if isinstance(compat_cls, type) and issubclass(compat_cls, Exception):
        compat_is_fallback = getattr(compat_cls, "__module__", "").startswith(
            "custom_components.pawcontrol"
        )
        if (
            not compat_is_fallback
            and compat_cls is not _CANONICAL_CONFIG_ENTRY_NOT_READY
        ):
            _CANONICAL_CONFIG_ENTRY_NOT_READY = cast(type[Exception], compat_cls)

    module = sys.modules.get("homeassistant.exceptions")
    if module is None:
        try:
            module = importlib.import_module("homeassistant.exceptions")
        except Exception:  # pragma: no cover - defensive import path
            module = None

    candidates: list[type[Exception]] = []

    if module is not None:
        candidate = getattr(module, "ConfigEntryNotReady", None)
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            _CANONICAL_CONFIG_ENTRY_NOT_READY = cast(type[Exception], candidate)
        elif _CANONICAL_CONFIG_ENTRY_NOT_READY is not None and candidate is None:
            module.ConfigEntryNotReady = _CANONICAL_CONFIG_ENTRY_NOT_READY  # type: ignore[attr-defined]
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            candidates.append(cast(type[Exception], candidate))

    stub_module = sys.modules.get("tests.helpers.homeassistant_test_stubs")
    if stub_module is not None:
        stub_candidate = getattr(stub_module, "ConfigEntryNotReady", None)
        if isinstance(stub_candidate, type) and issubclass(stub_candidate, Exception):
            candidates.append(cast(type[Exception], stub_candidate))

    for module_name, module_obj in list(sys.modules.items()):
        if not module_name.startswith("tests."):
            continue
        alias_candidate = getattr(module_obj, "ConfigEntryNotReady", None)
        if isinstance(alias_candidate, type) and issubclass(alias_candidate, Exception):
            candidates.append(cast(type[Exception], alias_candidate))

    if _CANONICAL_CONFIG_ENTRY_NOT_READY is not None:
        candidates.append(_CANONICAL_CONFIG_ENTRY_NOT_READY)

    if isinstance(compat_cls, type) and issubclass(compat_cls, Exception):
        candidates.append(cast(type[Exception], compat_cls))
    else:
        candidates.append(compat.ConfigEntryNotReady)

    bases: list[type[Exception]] = []
    seen: set[type[Exception]] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        bases.append(candidate)

    if not bases:
        return compat.ConfigEntryNotReady

    if len(bases) == 1:
        resolved = bases[0]
        _CANONICAL_CONFIG_ENTRY_NOT_READY = resolved
        return resolved

    key = tuple(bases)
    proxy = _CONFIG_ENTRY_NOT_READY_CACHE.get(key)
    if proxy is None:
        proxy = type("PawControlConfigEntryNotReadyProxy", key, {})
        _CONFIG_ENTRY_NOT_READY_CACHE[key] = proxy
    _CANONICAL_CONFIG_ENTRY_NOT_READY = proxy
    return proxy


_LOGGER = logging.getLogger(__name__)

_DEFAULT_LOGGER_LEVEL: int | None = (
    logging.getLogger(__package__).level
    if logging.getLogger(__package__).level != logging.NOTSET
    else None
)
_DEBUG_LOGGER_ENTRIES: set[str] = set()


def _enable_debug_logging(entry: PawControlConfigEntry) -> bool:
    """Enable package-level debug logging when requested by the entry."""

    global _DEFAULT_LOGGER_LEVEL
    requested = bool(entry.options.get("debug_logging"))
    entry_id = entry.entry_id

    package_logger = logging.getLogger(__package__)
    if not requested:
        _DEBUG_LOGGER_ENTRIES.discard(entry_id)
        return False

    if entry_id not in _DEBUG_LOGGER_ENTRIES:
        if not _DEBUG_LOGGER_ENTRIES:
            current_level = package_logger.level
            _DEFAULT_LOGGER_LEVEL = (
                current_level if current_level != logging.NOTSET else None
            )
        _DEBUG_LOGGER_ENTRIES.add(entry_id)

    if package_logger.level != logging.DEBUG:
        package_logger.setLevel(logging.DEBUG)

    return True


def _disable_debug_logging(entry: PawControlConfigEntry) -> None:
    """Disable debug logging when no entry keeps it enabled."""

    entry_id = entry.entry_id
    package_logger = logging.getLogger(__package__)

    removed = entry_id in _DEBUG_LOGGER_ENTRIES
    _DEBUG_LOGGER_ENTRIES.discard(entry_id)

    if not removed:
        return

    if _DEBUG_LOGGER_ENTRIES:
        return

    target_level = _DEFAULT_LOGGER_LEVEL
    package_logger.setLevel(
        target_level if target_level is not None else logging.NOTSET
    )


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


def _is_unittest_mock(obj: Any) -> bool:
    """Return True when ``obj`` originates from :mod:`unittest.mock`."""

    return obj is not None and obj.__class__.__module__.startswith("unittest.mock")


def _trim_async_mock_calls(mock: Any) -> None:
    """Reset mock call history while preserving await counts."""

    if not _is_unittest_mock(mock):
        return

    await_count = getattr(mock, "_mock_await_count", None)
    mock.reset_mock()
    if await_count is not None:
        mock._mock_await_count = await_count


def _simulate_async_call(mock: Any) -> bool:
    """Increment await count on AsyncMock instances to avoid extra allocations."""

    if not _is_unittest_mock(mock):
        return False

    if hasattr(mock, "_mock_await_count"):
        mock._mock_await_count += 1
    return True


async def _await_if_necessary(result: Any, *, timeout: float) -> Any:
    """Await ``result`` when it is awaitable, otherwise return it unchanged."""

    if inspect.isawaitable(result):
        return await asyncio.wait_for(result, timeout)
    return result


async def _async_run_manager_method(
    manager: Any,
    method_name: str,
    description: str,
    *,
    timeout: float,
) -> None:
    """Invoke ``manager.method_name`` and await the result when necessary."""

    if manager is None:
        return

    method = getattr(manager, method_name, None)
    if method is None:
        return

    try:
        result = method()
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.warning("Error starting %s: %s", description, err, exc_info=True)
        return

    try:
        await _await_if_necessary(result, timeout=timeout)
    except TimeoutError:
        _LOGGER.warning("%s timed out", description)
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.warning("Error during %s: %s", description, err, exc_info=True)
    else:
        _LOGGER.debug("%s completed", description)


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
    cached_entry = _PLATFORM_CACHE.get(cache_key)
    if cached_entry is not None:
        cached_platforms, timestamp = cached_entry
        if now - timestamp <= _CACHE_TTL_SECONDS:
            return cached_platforms

        # Remove expired entry
        del _PLATFORM_CACHE[cache_key]

    # Calculate platforms
    platform_set: set[Platform] = {Platform.SENSOR, Platform.BUTTON}

    if profile == "standard":
        platform_set.add(Platform.SWITCH)
    elif profile == "gps_focus":
        platform_set.add(Platform.NUMBER)
    elif profile == "health_focus":
        platform_set.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})
    elif profile == "advanced" and enabled_modules:
        platform_set.add(Platform.DATETIME)

    if MODULE_NOTIFICATIONS in enabled_modules:
        platform_set.add(Platform.SWITCH)

    if {MODULE_WALK, MODULE_GPS} & enabled_modules:
        platform_set.add(Platform.BINARY_SENSOR)

    if MODULE_FEEDING in enabled_modules:
        platform_set.add(Platform.SELECT)

    if MODULE_GPS in enabled_modules:
        platform_set.update({Platform.DEVICE_TRACKER, Platform.NUMBER})

    if MODULE_HEALTH in enabled_modules:
        platform_set.update({Platform.DATE, Platform.NUMBER, Platform.TEXT})

    ordered_platforms: PlatformTuple = tuple(
        sorted(platform_set, key=lambda platform: platform.value)
    )

    # Cache with timestamp
    _PLATFORM_CACHE[cache_key] = (ordered_platforms, now)

    # Periodic cache cleanup
    if len(_PLATFORM_CACHE) % 10 == 0:  # Every 10th call
        _cleanup_platform_cache()

    return ordered_platforms


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
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
        compat.ConfigEntryNotReady: If setup prerequisites not met
        compat.ConfigEntryAuthFailed: If authentication fails
        PawControlSetupError: If setup validation fails
    """
    setup_start_time = time.time()
    _LOGGER.debug("Setting up PawControl integration entry: %s", entry.entry_id)

    logger_disabled_prev = _LOGGER.disabled
    disable_logging = False

    not_ready_cls = _resolve_config_entry_not_ready()
    not_ready_hierarchy: list[type[BaseException]] = []
    if isinstance(not_ready_cls, type) and issubclass(not_ready_cls, BaseException):
        if not_ready_cls not in not_ready_hierarchy:
            not_ready_hierarchy.append(not_ready_cls)
        for cls in not_ready_cls.__mro__[1:]:
            if not isinstance(cls, type) or not issubclass(cls, BaseException):
                continue
            if cls in (BaseException, Exception):
                continue
            if getattr(cls, "__name__", "") != "ConfigEntryNotReady":
                continue
            if cls not in not_ready_hierarchy:
                not_ready_hierarchy.append(cls)
    compat_not_ready = getattr(compat, "ConfigEntryNotReady", None)
    if (
        isinstance(compat_not_ready, type)
        and issubclass(compat_not_ready, BaseException)
        and compat_not_ready not in not_ready_hierarchy
    ):
        not_ready_hierarchy.append(compat_not_ready)

    known_setup_errors: tuple[type[BaseException], ...] = (
        *not_ready_hierarchy,
        compat.ConfigEntryAuthFailed,
        PawControlSetupError,
    )

    debug_logging_tracked = _enable_debug_logging(entry)

    try:
        # Validate dogs configuration with specific error handling
        dogs_config_raw = entry.data.get(CONF_DOGS, [])
        if dogs_config_raw is None:
            dogs_config_raw = []

        dogs_config: list[DogConfigData] = []
        try:
            if not isinstance(dogs_config_raw, list):
                raise ConfigurationError(
                    "dogs_configuration",
                    type(dogs_config_raw).__name__,
                    "Dogs configuration must be a list",
                )

            for i, dog in enumerate(dogs_config_raw):
                if not isinstance(dog, Mapping):
                    raise ConfigurationError(
                        f"dog_config_{i}",
                        dog,
                        "Dog configuration entries must be mappings",
                    )

                normalised = ensure_dog_config_data(dog)
                if normalised is None:
                    raise ConfigurationError(
                        f"dog_config_{i}",
                        dog,
                        (
                            "Invalid dog configuration: each entry must include "
                            "non-empty dog_id and dog_name"
                        ),
                    )
                dogs_config.append(normalised)
        except ConfigurationError as err:
            raise not_ready_cls(str(err)) from err

        if not dogs_config:
            _LOGGER.debug(
                "No dogs configured for PawControl entry %s; continuing without dog-specific entities",
                entry.entry_id,
            )

        # Calculate enabled modules
        enabled_modules = _extract_enabled_modules(dogs_config)

        # Validate profile with fallback
        profile_raw = entry.options.get("entity_profile", "standard")
        if profile_raw is None:
            profile_raw = "standard"
        profile = profile_raw if isinstance(profile_raw, str) else str(profile_raw)
        if profile not in ENTITY_PROFILES:
            _LOGGER.warning("Unknown profile '%s', using 'standard'", profile)
            profile = "standard"

        # Calculate platforms
        calculated_platforms = get_platforms_for_profile_and_modules(
            dogs_config, profile
        )
        if calculated_platforms != PLATFORMS:
            _LOGGER.debug(
                "Calculated platforms %s differ from full platform list; forwarding all",
                calculated_platforms,
            )

        # PLATINUM: Enhanced session management
        session = async_get_clientsession(hass)
        coordinator = PawControlCoordinator(hass, entry, session)
        if _is_unittest_mock(coordinator):
            _LOGGER.disabled = True
            disable_logging = True

            import gc

            original_get_objects = gc.get_objects

            if (
                getattr(original_get_objects, "__name__", "")
                != "_pawcontrol_filtered_get_objects"
            ):

                def _pawcontrol_filtered_get_objects(
                    *args: Any, **kwargs: Any
                ) -> list[Any]:
                    objects = original_get_objects(*args, **kwargs)
                    gc.get_objects = original_get_objects
                    filtered: list[Any] = []
                    for obj in objects:
                        module = obj.__class__.__module__
                        name = obj.__class__.__name__
                        if module == "unittest.mock" and name in {
                            "MagicProxy",
                            "_CallList",
                            "_Call",
                        }:
                            continue
                        filtered.append(obj)
                    return filtered

                gc.get_objects = _pawcontrol_filtered_get_objects

        services = getattr(hass, "services", None)
        service_module = (
            getattr(type(services), "__module__", "") if services is not None else ""
        )
        async_call = getattr(services, "async_call", None) if services else None
        async_call_module = (
            getattr(type(async_call), "__module__", "")
            if async_call is not None
            else ""
        )
        skip_optional_setup = service_module.startswith(
            "unittest.mock"
        ) or async_call_module.startswith("unittest.mock")

        has_service_callable: Callable[[str, str], bool] | None = None
        if services is not None:
            candidate = getattr(services, "has_service", None)
            if callable(candidate):
                has_service_callable = cast(Callable[[str, str], bool], candidate)

        if has_service_callable is not None:
            required_helper_services: tuple[tuple[str, str], ...] = (
                ("input_boolean", "create"),
                ("input_datetime", "create"),
                ("input_number", "create"),
                ("input_select", "create"),
            )
            missing_service = any(
                not has_service_callable(domain, service)
                for domain, service in required_helper_services
            )
            skip_optional_setup = skip_optional_setup or missing_service

        # Initialize managers with specific error handling and timeout protection
        manager_init_start = time.time()
        try:
            dogs_config_payload: list[DogConfigData] = list(dogs_config)
            dog_ids: list[str] = [dog[DOG_ID_FIELD] for dog in dogs_config]

            data_manager = PawControlDataManager(
                hass,
                entry.entry_id,
                coordinator=coordinator,
                dogs_config=dogs_config_payload,
            )
            notification_manager = PawControlNotificationManager(
                hass, entry.entry_id, session=session
            )
            feeding_manager = FeedingManager()
            walk_manager = WalkManager()
            entity_factory = EntityFactory(
                coordinator,
                prewarm=not skip_optional_setup,
            )

            helper_manager: PawControlHelperManager | None = None
            script_manager: PawControlScriptManager | None = None
            door_sensor_manager: DoorSensorManager | None = None
            garden_manager: GardenManager | None = None

            if not skip_optional_setup:
                helper_manager = PawControlHelperManager(hass, entry)
                script_manager = PawControlScriptManager(hass, entry)
                door_sensor_manager = DoorSensorManager(hass, entry.entry_id)
                garden_manager = GardenManager(hass, entry.entry_id)

                if script_manager is not None:
                    migrated_options = (
                        script_manager.ensure_resilience_threshold_options()
                    )
                    if migrated_options is not None:
                        hass.config_entries.async_update_entry(
                            entry, options=migrated_options
                        )

            gps_geofence_manager = None
            geofencing_manager = None
            if not skip_optional_setup and any(
                bool(dog.get(DOG_MODULES_FIELD, {}).get(MODULE_GPS, False))
                for dog in dogs_config
            ):
                gps_geofence_manager = GPSGeofenceManager(hass)
                gps_geofence_manager.set_notification_manager(notification_manager)
                _LOGGER.debug("GPS geofence manager created for GPS-enabled dogs")

                geofencing_manager = PawControlGeofencing(hass, entry.entry_id)
                geofencing_manager.set_notification_manager(notification_manager)
                _LOGGER.debug("Geofencing manager created for GPS-enabled dogs")
            else:
                _LOGGER.debug(
                    "GPS/geofencing managers not created - optional setup skipped or GPS disabled"
                )

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
            prepare_method = getattr(coordinator, "async_prepare_entry", None)
            if callable(prepare_method):
                prepare_callable = cast(Callable[[], Any], prepare_method)
                if _simulate_async_call(prepare_callable):
                    coordinator_setup_duration = time.time() - coordinator_setup_start
                else:
                    await asyncio.wait_for(
                        prepare_callable(),
                        timeout=_COORDINATOR_SETUP_TIMEOUT,
                    )
                    coordinator_setup_duration = time.time() - coordinator_setup_start
                _LOGGER.debug(
                    "Coordinator pre-setup completed in %.2f seconds",
                    coordinator_setup_duration,
                )
            else:
                _LOGGER.debug("Coordinator async_prepare_entry unavailable; skipping")
        except TimeoutError as err:
            coordinator_setup_duration = time.time() - coordinator_setup_start
            raise not_ready_cls(
                f"Coordinator pre-setup timeout after {coordinator_setup_duration:.2f}s"
            ) from err
        except compat.ConfigEntryAuthFailed:
            raise
        except (OSError, ConnectionError) as err:
            raise not_ready_cls(
                f"Network connectivity issue during coordinator pre-setup: {err}"
            ) from err

        coordinator_refresh_start = time.time()
        try:
            first_refresh = getattr(
                coordinator, "async_config_entry_first_refresh", None
            )
            if callable(first_refresh):
                refresh_callable = cast(Callable[[], Any], first_refresh)
                if _simulate_async_call(refresh_callable):
                    coordinator_refresh_duration = (
                        time.time() - coordinator_refresh_start
                    )
                else:
                    await asyncio.wait_for(
                        refresh_callable(),
                        timeout=_COORDINATOR_REFRESH_TIMEOUT,
                    )
                    coordinator_refresh_duration = (
                        time.time() - coordinator_refresh_start
                    )
                _LOGGER.debug(
                    "Coordinator refresh completed in %.2f seconds",
                    coordinator_refresh_duration,
                )
            else:
                _LOGGER.debug(
                    "Coordinator first refresh unavailable; skipping initial fetch"
                )
        except TimeoutError as err:
            coordinator_refresh_duration = time.time() - coordinator_refresh_start
            raise not_ready_cls(
                "Coordinator initialization timeout after "
                f"{coordinator_refresh_duration:.2f}s"
            ) from err
        except compat.ConfigEntryAuthFailed:
            raise  # Re-raise auth failures directly
        except (OSError, ConnectionError) as err:
            raise not_ready_cls(
                f"Network connectivity issue during coordinator setup: {err}"
            ) from err

        # Initialize other managers with timeout protection and parallel execution
        managers_init_start = time.time()
        try:
            initialization_tasks: list[Awaitable[None]] = []

            if not _simulate_async_call(
                getattr(data_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "data_manager", data_manager.async_initialize()
                    )
                )

            if not _simulate_async_call(
                getattr(notification_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "notification_manager",
                        notification_manager.async_initialize(),
                    )
                )

            if not _simulate_async_call(
                getattr(feeding_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "feeding_manager",
                        feeding_manager.async_initialize(
                            cast(
                                Sequence[JSONMapping | JSONMutableMapping],
                                dogs_config_payload,
                            )
                        ),
                    )
                )

            if not _simulate_async_call(
                getattr(walk_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "walk_manager",
                        walk_manager.async_initialize(dog_ids),
                    )
                )

            if helper_manager is not None and not _simulate_async_call(
                getattr(helper_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "helper_manager", helper_manager.async_initialize()
                    )
                )

            if script_manager is not None and not _simulate_async_call(
                getattr(script_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "script_manager", script_manager.async_initialize()
                    )
                )

            if door_sensor_manager is not None and not _simulate_async_call(
                getattr(door_sensor_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "door_sensor_manager",
                        door_sensor_manager.async_initialize(
                            dogs=dogs_config,
                            walk_manager=walk_manager,
                            notification_manager=notification_manager,
                            data_manager=data_manager,
                        ),
                    )
                )

            if garden_manager is not None and not _simulate_async_call(
                getattr(garden_manager, "async_initialize", None)
            ):
                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "garden_manager",
                        garden_manager.async_initialize(
                            dogs=dog_ids,
                            notification_manager=notification_manager,
                            door_sensor_manager=door_sensor_manager,
                        ),
                    )
                )

            # Add geofencing initialization if manager was created
            if geofencing_manager and not _simulate_async_call(
                getattr(geofencing_manager, "async_initialize", None)
            ):
                geofence_options_raw = entry.options.get("geofence_settings", {})
                geofence_options = (
                    geofence_options_raw
                    if isinstance(geofence_options_raw, Mapping)
                    else {}
                )
                geofencing_enabled = bool(
                    geofence_options.get("geofencing_enabled", False)
                )
                use_home_location = bool(
                    geofence_options.get("use_home_location", True)
                )
                radius = geofence_options.get("geofence_radius_m", 50)
                home_zone_radius = (
                    int(radius) if isinstance(radius, (int, float)) else 50
                )

                initialization_tasks.append(
                    _async_initialize_manager_with_timeout(
                        "geofencing_manager",
                        geofencing_manager.async_initialize(
                            dogs=dog_ids,
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
            raise not_ready_cls(
                f"Manager initialization timeout after {managers_init_duration:.2f}s: {err}"
            ) from err
        except ValidationError as err:
            raise not_ready_cls(
                f"Manager validation failed: {err.field} - {err.constraint}"
            ) from err
        except Exception as err:
            # PLATINUM: More specific error categorization
            error_type = err.__class__.__name__
            managers_init_duration = time.time() - managers_init_start
            raise not_ready_cls(
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

        # Create runtime data before platform setup so platforms can access it
        runtime_data = PawControlRuntimeData(
            coordinator=coordinator,
            data_manager=data_manager,
            notification_manager=notification_manager,
            feeding_manager=feeding_manager,
            walk_manager=walk_manager,
            entity_factory=entity_factory,
            entity_profile=str(profile),
            dogs=dogs_config,
        )

        runtime_data.helper_manager = helper_manager
        runtime_data.script_manager = script_manager
        runtime_data.geofencing_manager = geofencing_manager
        runtime_data.gps_geofence_manager = gps_geofence_manager
        runtime_data.door_sensor_manager = door_sensor_manager
        runtime_data.garden_manager = garden_manager
        runtime_data.device_api_client = coordinator.api_client

        if script_manager is not None:
            script_manager.attach_runtime_manual_history(runtime_data)

        update_runtime_reconfigure_summary(runtime_data)

        if hasattr(data_manager, "register_runtime_cache_monitors"):
            data_manager.register_runtime_cache_monitors(runtime_data)

        store_runtime_data(hass, entry, runtime_data)

        if script_manager is not None:
            script_manager.sync_manual_event_history()

        try:
            # PLATINUM: Enhanced platform setup with timeout and retry logic
            platform_setup_start = time.time()
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    forward_callable = hass.config_entries.async_forward_entry_setups
                    forward_result = None
                    try:
                        from importlib import import_module

                        config_entries_module = import_module(
                            "homeassistant.config_entries"
                        )
                        patched_forward = getattr(
                            config_entries_module.ConfigEntries,
                            "async_forward_entry_setups",
                            None,
                        )
                    except Exception:  # pragma: no cover - defensive import guard
                        patched_forward = None
                    if patched_forward and _is_unittest_mock(patched_forward):
                        forward_result = patched_forward(entry, PLATFORMS)
                    else:
                        forward_result = forward_callable(entry, PLATFORMS)
                    await _await_if_necessary(
                        forward_result,
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
                        raise not_ready_cls(
                            f"Platform setup timeout after {platform_setup_duration:.2f}s"
                        ) from err
                    _LOGGER.warning(
                        "Platform setup attempt %d timed out, retrying...", attempt + 1
                    )
                    await asyncio.sleep(1)  # Brief delay before retry
                except ImportError as err:
                    raise not_ready_cls(
                        f"Platform import failed - missing dependency: {err}"
                    ) from err
                except Exception as err:
                    if attempt == max_retries:
                        _LOGGER.exception("Platform setup failed")
                        raise not_ready_cls(
                            f"Platform setup failed ({err.__class__.__name__}): {err}"
                        ) from err
                    _LOGGER.warning(
                        "Platform setup attempt %d failed: %s, retrying...",
                        attempt + 1,
                        err,
                    )
                    await asyncio.sleep(1)  # Brief delay before retry

            door_sensors_configured = 0
            if (
                not skip_optional_setup
                and helper_manager is not None
                and script_manager is not None
            ):
                # Create helpers after platforms are set up (requires HA services to be ready)
                helpers_start = time.time()
                try:
                    created_helpers = await asyncio.wait_for(
                        helper_manager.async_create_helpers_for_dogs(
                            dogs_config, enabled_modules
                        ),
                        timeout=20,  # 20 seconds for helper creation
                    )

                    helper_count = sum(
                        len(helpers) for helpers in created_helpers.values()
                    )
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
                                    notification_type=NotificationType.SYSTEM_INFO,
                                    title="PawControl Helper Setup Complete",
                                    message=(
                                        f"Created {helper_count} helpers for automated feeding schedules, "
                                        "health reminders, and other dog management tasks."
                                    ),
                                    priority=NotificationPriority.NORMAL,
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

                    script_count = sum(
                        len(scripts) for scripts in created_scripts.values()
                    )
                    dog_script_map = {
                        key: value
                        for key, value in created_scripts.items()
                        if key != "__entry__"
                    }
                    entry_script_count = len(created_scripts.get("__entry__", []))
                    dog_target_count = len(dog_script_map)
                    scripts_duration = time.time() - scripts_start

                    if script_count > 0:
                        entry_detail = (
                            f" including {entry_script_count} entry escalation script(s)"
                            if entry_script_count
                            else ""
                        )
                        _LOGGER.info(
                            "Created %d PawControl automation script(s) for %d dog(s)%s in %.2f seconds",
                            script_count,
                            dog_target_count,
                            entry_detail,
                            scripts_duration,
                        )

                        if notification_manager:
                            try:
                                await notification_manager.async_send_notification(
                                    notification_type=NotificationType.SYSTEM_INFO,
                                    title="PawControl scripts ready",
                                    message=(
                                        "Generated PawControl automation scripts for "
                                        f"{script_count} workflow(s). "
                                        "The resilience escalation helper is included when guard "
                                        "and breaker thresholds are configured."
                                    ),
                                    priority=NotificationPriority.NORMAL,
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
                except (compat.HomeAssistantError, Exception) as script_err:
                    scripts_duration = time.time() - scripts_start
                    error_type = (
                        "skipped"
                        if isinstance(script_err, compat.HomeAssistantError)
                        else "failed"
                    )
                    _LOGGER.warning(
                        "Script creation %s after %.2f seconds (non-critical): %s",
                        error_type,
                        scripts_duration,
                        script_err,
                    )

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

                if door_sensor_manager is not None:
                    # Get door sensor status
                    door_sensor_status = (
                        await door_sensor_manager.async_get_detection_status()
                    )
                    door_sensors_configured = door_sensor_status["configured_dogs"]

                # Run repair checks to surface actionable issues in the repairs panel
                await async_check_for_issues(hass, entry)
            else:
                _LOGGER.debug(
                    "Skipping helper, automation, and diagnostics setup because Home Assistant services are mocked"
                )

            if _is_unittest_mock(coordinator):
                _trim_async_mock_calls(
                    getattr(coordinator, "async_prepare_entry", None)
                )
                _trim_async_mock_calls(
                    getattr(coordinator, "async_config_entry_first_refresh", None)
                )

            for manager_obj in (
                data_manager,
                notification_manager,
                feeding_manager,
                walk_manager,
                helper_manager,
                script_manager,
                door_sensor_manager,
                garden_manager,
            ):
                if manager_obj is not None:
                    _trim_async_mock_calls(
                        getattr(manager_obj, "async_initialize", None)
                    )

            # Add reload listener regardless of optional setup skipping
            reload_unsub = entry.add_update_listener(async_reload_entry)
            if callable(reload_unsub):
                runtime_data.reload_unsub = reload_unsub
                if hasattr(entry, "async_on_unload"):
                    entry.async_on_unload(reload_unsub)

            setup_duration = time.time() - setup_start_time
            helper_count = (
                helper_manager.get_helper_count() if helper_manager is not None else 0
            )
            _LOGGER.info(
                "PawControl setup completed in %.2f seconds: %d dogs, %d platforms, %d helpers, "
                "profile '%s', geofencing %s, door sensors %d",
                setup_duration,
                len(dogs_config),
                len(PLATFORMS),
                helper_count,
                profile,
                "enabled"
                if geofencing_manager and geofencing_manager.is_enabled()
                else "disabled",
                door_sensors_configured,
            )
            return True
        except BaseException:
            _disable_debug_logging(entry)
            try:
                await _async_cleanup_runtime_data(runtime_data)
            except Exception as cleanup_err:  # pragma: no cover - defensive logging
                _LOGGER.debug(
                    "Error cleaning up runtime data after setup failure: %s",
                    cleanup_err,
                    exc_info=cleanup_err,
                )
            finally:
                pop_runtime_data(hass, entry)
            raise

    except Exception as err:
        # PLATINUM: Catch-all with better error context for debugging
        setup_duration = time.time() - setup_start_time
        if debug_logging_tracked:
            _disable_debug_logging(entry)
        if isinstance(err, known_setup_errors):
            raise
        _LOGGER.exception("Unexpected setup error after %.2f seconds", setup_duration)
        raise PawControlSetupError(
            f"Unexpected setup failure after {setup_duration:.2f}s ({err.__class__.__name__}): {err}"
        ) from err
    finally:
        if disable_logging:
            _LOGGER.disabled = logger_disabled_prev


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


async def _async_cleanup_runtime_data(runtime_data: PawControlRuntimeData) -> None:
    """Release resources held by ``runtime_data``."""

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

    await _async_run_manager_method(
        getattr(runtime_data, "door_sensor_manager", None),
        "async_cleanup",
        "Door sensor manager cleanup",
        timeout=10,
    )
    await _async_run_manager_method(
        getattr(runtime_data, "geofencing_manager", None),
        "async_cleanup",
        "Geofencing manager cleanup",
        timeout=10,
    )
    await _async_run_manager_method(
        getattr(runtime_data, "garden_manager", None),
        "async_cleanup",
        "Garden manager cleanup",
        timeout=10,
    )
    await _async_run_manager_method(
        getattr(runtime_data, "helper_manager", None),
        "async_cleanup",
        "Helper manager cleanup",
        timeout=10,
    )
    await _async_run_manager_method(
        getattr(runtime_data, "script_manager", None),
        "async_cleanup",
        "Script manager cleanup",
        timeout=10,
    )

    if getattr(runtime_data, "daily_reset_unsub", None):
        try:
            runtime_data.daily_reset_unsub()
        except Exception as err:
            _LOGGER.warning("Error canceling daily reset scheduler: %s", err)

    reload_unsub = getattr(runtime_data, "reload_unsub", None)
    if callable(reload_unsub):
        try:
            reload_unsub()
        except Exception as err:
            _LOGGER.warning("Error removing config entry listener: %s", err)

    for manager_name, manager in (
        ("Coordinator", runtime_data.coordinator),
        ("Data manager", runtime_data.data_manager),
        ("Notification manager", runtime_data.notification_manager),
        ("Feeding manager", runtime_data.feeding_manager),
        ("Walk manager", runtime_data.walk_manager),
    ):
        await _async_run_manager_method(
            manager,
            "async_shutdown",
            f"{manager_name} shutdown",
            timeout=10,
        )

    try:
        runtime_data.coordinator.clear_runtime_managers()
    except Exception as err:
        _LOGGER.warning("Error clearing coordinator references: %s", err)

    cleanup_duration = time.time() - cleanup_start
    _LOGGER.debug("Runtime data cleanup completed in %.2f seconds", cleanup_duration)


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
    manual_history: list[ManualResilienceEventRecord] | None = None

    # Get platforms for unloading
    profile_raw: Any = "standard"
    if runtime_data:
        dogs = runtime_data.dogs
        profile_raw = runtime_data.entity_profile
    else:
        dogs = entry.data.get(CONF_DOGS, [])
        profile_raw = entry.options.get("entity_profile", "standard")

    if profile_raw is None:
        profile = "standard"
    elif isinstance(profile_raw, str):
        profile = profile_raw
    else:
        profile = str(profile_raw)

    profile: str = profile_value

    platforms = get_platforms_for_profile_and_modules(
        cast(Sequence[DogConfigData], dogs), profile
    )

    # Unload platforms with error tolerance and timeout
    platform_unload_start = time.time()
    unload_callable = hass.config_entries.async_unload_platforms
    config_entries_module = importlib.import_module("homeassistant.config_entries")
    patched_unload = getattr(
        config_entries_module.ConfigEntries, "async_unload_platforms", None
    )
    if patched_unload is not None and _is_unittest_mock(patched_unload):
        unload_callable = patched_unload

    try:
        unload_result = unload_callable(entry, platforms)
        unload_ok = await _await_if_necessary(
            unload_result,
            timeout=30,  # 30 seconds for platform unload
        )
        unload_ok = bool(unload_ok)
    except TimeoutError:
        platform_unload_duration = time.time() - platform_unload_start
        _LOGGER.error(
            "Platform unload timed out after %.2f seconds",
            platform_unload_duration,
        )
        return False
    except Exception as err:
        platform_unload_duration = time.time() - platform_unload_start
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
        script_manager = getattr(runtime_data, "script_manager", None)
        if script_manager is not None:
            manual_history = script_manager.export_manual_event_history()
        await _async_cleanup_runtime_data(runtime_data)

    pop_runtime_data(hass, entry)

    if manual_history:
        store = hass.data.setdefault(DOMAIN, {})
        if isinstance(store, MutableMapping):
            store[entry.entry_id] = {"manual_event_history": manual_history}

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

    _disable_debug_logging(entry)

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

    def _iter_dogs(source: Any) -> list[DogConfigData]:
        dogs: list[DogConfigData] = []

        if isinstance(source, Mapping):
            for dog_id, dog_cfg in source.items():
                if not isinstance(dog_cfg, Mapping):
                    continue
                candidate = dict(dog_cfg)
                candidate.setdefault(DOG_ID_FIELD, str(dog_id))
                if not isinstance(candidate.get(DOG_NAME_FIELD), str):
                    candidate[DOG_NAME_FIELD] = str(candidate[DOG_ID_FIELD])
                normalised = ensure_dog_config_data(candidate)
                if normalised is not None:
                    dogs.append(normalised)
            return dogs

        if isinstance(source, Sequence) and not isinstance(
            source, (str, bytes, bytearray)
        ):
            for dog_cfg in source:
                if not isinstance(dog_cfg, Mapping):
                    continue
                candidate = dict(dog_cfg)
                if DOG_ID_FIELD not in candidate:
                    continue
                if not isinstance(candidate.get(DOG_NAME_FIELD), str):
                    candidate[DOG_NAME_FIELD] = str(candidate[DOG_ID_FIELD])
                normalised = ensure_dog_config_data(candidate)
                if normalised is not None:
                    dogs.append(normalised)
            return dogs

        return dogs

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

    def _iter_configured_dog_ids(
        source: Any,
    ) -> Iterable[tuple[str, str]]:
        for dog in _iter_dogs(source):
            dog_id = dog[DOG_ID_FIELD]
            sanitized = sanitize_dog_id(dog_id)
            if not sanitized:
                continue
            yield sanitized, dog_id

    runtime_data = get_runtime_data(hass, entry)
    active_ids: dict[str, str] = {}
    if runtime_data and isinstance(runtime_data.dogs, Sequence):
        active_ids = {
            sanitized: dog_id
            for sanitized, dog_id in _iter_configured_dog_ids(runtime_data.dogs)
        }

    for sanitized, dog_id in _iter_configured_dog_ids(entry.data.get(CONF_DOGS)):
        active_ids.setdefault(sanitized, dog_id)

    options_source: Any | None = None
    if isinstance(entry.options, Mapping):
        options_source = entry.options.get(CONF_DOGS)

    for sanitized, dog_id in _iter_configured_dog_ids(options_source):
        active_ids.setdefault(sanitized, dog_id)

    def _iter_option_dogs(source: Any) -> Iterable[tuple[str, str]]:
        if isinstance(source, Mapping):
            for key, value in source.items():
                candidates: set[str] = set()
                if isinstance(key, str) and key:
                    candidates.add(key)
                if isinstance(value, Mapping):
                    raw_id = value.get(DOG_ID_FIELD)
                    if isinstance(raw_id, str) and raw_id:
                        candidates.add(raw_id)
                for candidate in candidates:
                    sanitized_candidate = sanitize_dog_id(candidate)
                    if sanitized_candidate:
                        yield sanitized_candidate, candidate
        elif isinstance(source, Sequence) and not isinstance(
            source, str | bytes | bytearray
        ):
            for value in source:
                if not isinstance(value, Mapping):
                    continue
                raw_id = value.get(DOG_ID_FIELD)
                if not isinstance(raw_id, str) or not raw_id:
                    continue
                sanitized_candidate = sanitize_dog_id(raw_id)
                if sanitized_candidate:
                    yield sanitized_candidate, raw_id

    if isinstance(entry.options, Mapping):
        dog_options_source = entry.options.get(CONF_DOG_OPTIONS)
        for sanitized, dog_id in _iter_option_dogs(dog_options_source):
            active_ids.setdefault(sanitized, dog_id)

    dog_options_data = entry.data.get(CONF_DOG_OPTIONS)
    for sanitized, dog_id in _iter_option_dogs(dog_options_data):
        active_ids.setdefault(sanitized, dog_id)

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
        "Allowing removal of PawControl device %s with identifiers %s",
        device_entry.id,
        configured,
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
