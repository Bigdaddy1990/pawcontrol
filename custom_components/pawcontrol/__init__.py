"""Set up and manage the PawControl integration lifecycle.

REFACTORED VERSION - Manager initialization and setup logic extracted to setup/ modules.
This module now focuses on orchestration and entry point management.

Original: 1660+ lines
Refactored: ~300 lines (80% reduction)
"""

import asyncio
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
import logging  # BUG FIX: removed unused `import importlib` (ruff F401)
import time
from typing import Any, Final, cast

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.typing import ConfigType

from .const import CONF_DOG_ID, CONF_DOG_OPTIONS, CONF_DOGS, DOMAIN, PLATFORMS
from .exceptions import ConfigEntryAuthFailed, PawControlSetupError
from .external_bindings import (
    async_setup_external_bindings,
    async_unload_external_bindings,
)
from .migrations import async_migrate_entry
from .mqtt_push import async_register_entry_mqtt, async_unregister_entry_mqtt
from .repairs import async_check_for_issues
from .runtime_data import get_runtime_data, pop_runtime_data, store_runtime_data
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .setup import (
    async_cleanup_runtime_data,
    async_initialize_managers,
    async_register_cleanup,
    async_setup_platforms,
    async_validate_entry_config,
)
from .types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    DogConfigData,
    ManualResilienceEventRecord,
    PawControlConfigEntry,
    PawControlRuntimeData,
    ensure_dog_config_data,
)
from .utils import sanitize_dog_id
from .webhooks import async_register_entry_webhook, async_unregister_entry_webhook

_LOGGER = logging.getLogger(__name__)

# Debug logging management
_DEFAULT_LOGGER_LEVEL: int | None = (
    logging.getLogger(__package__).level
    if logging.getLogger(__package__).level != logging.NOTSET
    else None
)
_DEBUG_LOGGER_ENTRIES: set[str] = set()

ALL_PLATFORMS: Final[tuple[Platform, ...]] = PLATFORMS

# PawControl is configured exclusively via the UI/config entries (no YAML setup).
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_CACHE_TTL_SECONDS: Final[int] = 300
_MAX_CACHE_SIZE: Final[int] = 128
_DEFAULT_PLATFORMS: Final[tuple[Platform, ...]] = tuple(
    sorted(
        {
            Platform.BUTTON,
            Platform.SENSOR,
            Platform.SWITCH,
        },
        key=lambda platform: platform.value,
    ),
)
_PLATFORM_CACHE: dict[
    tuple[int, str, frozenset[str]],
    tuple[tuple[Platform, ...], float],
] = {}

_MODULE_PLATFORM_MAP: Final[dict[str, set[Platform]]] = {
    "gps": {Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.NUMBER},
    "feeding": {Platform.BINARY_SENSOR, Platform.SELECT},
    "health": {Platform.DATE, Platform.TEXT},
    "walk": {Platform.NUMBER},
    "notifications": {Platform.SWITCH},
}

_PROFILE_BASE_PLATFORMS: Final[dict[str, set[Platform]]] = {
    "standard": {Platform.BUTTON, Platform.SENSOR, Platform.SWITCH},
    "gps_focus": {
        Platform.BINARY_SENSOR,
        Platform.BUTTON,
        Platform.NUMBER,
        Platform.SENSOR,
        Platform.SWITCH,
    },
    "health_focus": {
        Platform.BUTTON,
        Platform.DATE,
        Platform.NUMBER,
        Platform.SENSOR,
        Platform.TEXT,
    },
    "advanced": {
        Platform.BUTTON,
        Platform.DATETIME,
        Platform.SENSOR,
    },
}


def _cleanup_platform_cache() -> None:
    """Drop expired cache entries and cap cache size."""
    now_monotonic = time.monotonic()
    now_wall = time.time()

    def _is_expired(timestamp: float) -> bool:
        reference = now_wall if timestamp > 1_000_000.0 else now_monotonic
        return reference - timestamp > _CACHE_TTL_SECONDS

    expired_keys = [
        key for key, (_, timestamp) in _PLATFORM_CACHE.items() if _is_expired(timestamp)
    ]
    for key in expired_keys:
        _PLATFORM_CACHE.pop(key, None)

    while len(_PLATFORM_CACHE) > _MAX_CACHE_SIZE:
        oldest_key = min(
            _PLATFORM_CACHE.items(),
            key=lambda item: item[1][1],
        )[0]
        _PLATFORM_CACHE.pop(oldest_key, None)


def get_platforms_for_profile_and_modules(
    dogs: Sequence[DogConfigData],
    profile: str,
) -> tuple[Platform, ...]:
    """Return enabled Home Assistant platforms for the configured profile."""
    if not dogs:
        return _DEFAULT_PLATFORMS

    active_modules: set[str] = set()
    for dog in dogs:
        modules = dog.get("modules")
        if not isinstance(modules, Mapping):
            continue
        for module_name, enabled in modules.items():
            if enabled and module_name in _MODULE_PLATFORM_MAP:
                active_modules.add(module_name)

    cache_key = (len(dogs), profile, frozenset(active_modules))
    # Platform cache reads and eviction use the same wall-clock source so tests
    # and runtime expiry logic stay aligned.
    now = time.time()
    cached = _PLATFORM_CACHE.get(cache_key)
    if cached and now - cached[1] <= _CACHE_TTL_SECONDS:
        return cached[0]

    _cleanup_platform_cache()
    platforms = set(_PROFILE_BASE_PLATFORMS.get(profile, _DEFAULT_PLATFORMS))
    for module_name in active_modules:
        platforms.update(_MODULE_PLATFORM_MAP[module_name])

    resolved = tuple(sorted(platforms, key=lambda platform: platform.value))
    _PLATFORM_CACHE[cache_key] = (resolved, now)
    return resolved


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
        target_level if target_level is not None else logging.NOTSET,
    )


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
) -> bool:
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
    setup_start_time = time.monotonic()
    _LOGGER.debug("Setting up PawControl integration entry: %s", entry.entry_id)
    debug_logging_tracked = _enable_debug_logging(entry)
    try:
        # Validate configuration
        dogs_config, profile, enabled_modules = await async_validate_entry_config(entry)

        # Check if services are available (detect mock environment)
        skip_optional_setup = _should_skip_optional_setup(hass)

        # Initialize all managers
        runtime_data = await async_initialize_managers(
            hass,
            entry,
            dogs_config,
            profile,
            skip_optional_setup,
        )

        # Store runtime data
        store_runtime_data(hass, entry, runtime_data)

        # Register webhook and MQTT
        await async_register_entry_webhook(hass, entry)
        await async_register_entry_mqtt(hass, entry)

        # Set up platforms
        await async_setup_platforms(hass, entry, runtime_data)

        # Register cleanup handlers
        await async_register_cleanup(hass, entry, runtime_data)

        # Setup daily reset scheduler (non-critical)
        if not skip_optional_setup:
            try:
                reset_unsub = await async_setup_daily_reset_scheduler(hass, entry)
                if reset_unsub:
                    runtime_data.daily_reset_unsub = reset_unsub
            except Exception as err:
                _LOGGER.warning(
                    "Failed to setup daily reset scheduler (non-critical): %s",
                    err,
                )

        # Start background tasks
        if not skip_optional_setup:
            runtime_data.coordinator.async_start_background_tasks()
            # Start background task health monitoring
            monitor_task = hass.async_create_task(
                _async_monitor_background_tasks(runtime_data),
            )
            runtime_data.background_monitor_task = monitor_task
        # Run repair checks
        if not skip_optional_setup:
            await async_check_for_issues(hass, entry)
        # Log setup completion
        setup_duration = time.monotonic() - setup_start_time
        helper_count = (
            runtime_data.helper_manager.get_helper_count()
            if runtime_data.helper_manager is not None
            else 0
        )
        door_sensors_configured = (
            len(runtime_data.door_sensor_manager.get_configured_dogs())
            if runtime_data.door_sensor_manager is not None
            else 0
        )

        _LOGGER.info(
            "PawControl setup completed in %.2f seconds: %d dogs, %d platforms, %d helpers, "  # noqa: E501
            "profile '%s', geofencing %s, door sensors %d",
            setup_duration,
            len(dogs_config),
            len(PLATFORMS),
            helper_count,
            profile,
            "enabled"
            if runtime_data.geofencing_manager
            and runtime_data.geofencing_manager.is_enabled()
            else "disabled",
            door_sensors_configured,
        )
        return True

    except (
        ConfigEntryNotReady,
        ConfigEntryAuthFailed,
        PawControlSetupError,
    ):
        if debug_logging_tracked:
            _disable_debug_logging(entry)
        raise

    except Exception as err:
        setup_duration = time.monotonic() - setup_start_time
        if debug_logging_tracked:
            _disable_debug_logging(entry)
        _LOGGER.exception("Unexpected setup error after %.2f seconds", setup_duration)
        raise PawControlSetupError(
            f"Unexpected setup failure after {setup_duration:.2f}s "
            f"({err.__class__.__name__}): {err}",
        ) from err


def _should_skip_optional_setup(hass: HomeAssistant) -> bool:
    """Check if optional setup should be skipped (mock environment).

    Args:
        hass: Home Assistant instance

    Returns:
        True if optional setup should be skipped
    """
    services = getattr(hass, "services", None)
    if services is None:
        return True

    service_module = getattr(type(services), "__module__", "")
    async_call = getattr(services, "async_call", None)
    async_call_module = (
        getattr(type(async_call), "__module__", "") if async_call is not None else ""
    )

    return service_module.startswith("unittest.mock") or async_call_module.startswith(
        "unittest.mock",
    )


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

                # Check if cleanup task is still running and restart if dead.
                if (
                    hasattr(garden_manager, "_cleanup_task")
                    and garden_manager._cleanup_task is not None
                    and garden_manager._cleanup_task.done()
                ):
                    _LOGGER.warning(
                        "Garden manager cleanup task has stopped; attempting restart",
                    )
                    restart_fn = getattr(
                        garden_manager, "async_start_cleanup_task", None
                    )
                    if callable(restart_fn):
                        try:
                            await restart_fn()
                        except Exception as restart_err:
                            _LOGGER.error(
                                "Failed to restart garden cleanup task: %s", restart_err
                            )

                # Check if stats update task is still running and restart if dead.
                if (
                    hasattr(garden_manager, "_stats_update_task")
                    and garden_manager._stats_update_task is not None
                    and garden_manager._stats_update_task.done()
                ):
                    _LOGGER.warning(
                        "Garden manager stats update task has stopped; "
                        "attempting restart",
                    )
                    restart_fn = getattr(
                        garden_manager, "async_start_stats_update_task", None
                    )
                    if callable(restart_fn):
                        try:
                            await restart_fn()
                        except Exception as restart_err:
                            _LOGGER.error(
                                "Failed to restart garden stats task: %s", restart_err
                            )

            _LOGGER.debug("Background task health check completed")
        except asyncio.CancelledError:
            _LOGGER.debug("Background task monitoring cancelled")
            break
        except Exception as err:
            _LOGGER.error("Error in background task monitoring: %s", err)


async def async_unload_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload successful
    """
    unload_start_time = time.monotonic()
    # Unregister external integrations
    await async_unregister_entry_webhook(hass, entry)
    await async_unregister_entry_mqtt(hass, entry)
    await async_unload_external_bindings(hass, entry)
    # Get runtime data
    runtime_data = get_runtime_data(hass, entry)
    # Get dogs config for platform determination

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        _LOGGER.error("One or more platforms failed to unload cleanly")
        return False

    # Cleanup runtime data
    if runtime_data:
        await async_cleanup_runtime_data(runtime_data)

    # Remove from runtime storage
    pop_runtime_data(hass, entry)
    # Platform selection cache depends on active dog modules/profile snapshots.  # noqa: E501
    _PLATFORM_CACHE.clear()
    # Cleanup service manager if last entry
    domain_data = hass.data.get(DOMAIN, {})
    service_manager = domain_data.get("service_manager")
    if service_manager:
        loaded_entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if len(loaded_entries) <= 1:
            try:
                await asyncio.wait_for(service_manager.async_shutdown(), timeout=10)
            except TimeoutError:
                _LOGGER.warning("Service manager shutdown timed out")
            except Exception as err:
                _LOGGER.warning("Error shutting down service manager: %s", err)

    _disable_debug_logging(entry)
    unload_duration = time.monotonic() - unload_start_time
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
            source,
            str | bytes | bytearray,
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
            "Device %s is not managed by PawControl; skipping removal",
            device_entry.id,
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

    # Check options
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
            source,
            str | bytes | bytearray,
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
            "Refusing to remove PawControl device %s because dogs %s are still configured",  # noqa: E501
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


async def async_reload_entry(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
) -> None:
    """Reload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    reload_start_time = time.monotonic()
    _LOGGER.debug("Reloading PawControl integration entry: %s", entry.entry_id)
    unload_ok = await async_unload_entry(hass, entry)
    if not unload_ok:
        _LOGGER.warning(
            "Reload aborted because unload failed for entry %s",
            entry.entry_id,
        )
        return

    try:
        await async_setup_entry(hass, entry)
    except Exception as err:
        _LOGGER.error(
            "PawControl reload failed during setup for entry %s: %s (%s)",
            entry.entry_id,
            err,
            err.__class__.__name__,
        )
        raise
    reload_duration = time.monotonic() - reload_start_time
    _LOGGER.info(
        "PawControl reload completed in %.2f seconds",
        reload_duration,
    )
