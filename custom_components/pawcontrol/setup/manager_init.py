"""Manager initialization for PawControl.

Extracted from __init__.py to isolate complex manager setup logic.
Handles coordinator, data manager, notification manager, and all optional managers.
"""

import asyncio
from collections.abc import Mapping, Sequence
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..const import CONF_DOG_OPTIONS, MODULE_GPS
from ..coordinator import PawControlCoordinator
from ..data_manager import PawControlDataManager
from ..door_sensor_manager import DoorSensorManager
from ..entity_factory import EntityFactory
from ..exceptions import ConfigEntryAuthFailed
from ..feeding_manager import FeedingManager
from ..garden_manager import GardenManager
from ..geofencing import PawControlGeofencing
from ..gps_manager import GPSGeofenceManager
from ..helper_manager import PawControlHelperManager
from ..notifications import PawControlNotificationManager
from ..script_manager import PawControlScriptManager
from ..telemetry import update_runtime_reconfigure_summary
from ..types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    ConfigEntryDataPayload,
    ConfigEntryOptionsPayload,
    DogConfigData,
    JSONLikeMapping,
    PawControlRuntimeData,
)
from ..walk_manager import WalkManager

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from ..types import PawControlConfigEntry
_LOGGER = logging.getLogger(__name__)

# Timeouts for manager initialization
_MANAGER_INIT_TIMEOUT: int = 30  # seconds per manager
_COORDINATOR_SETUP_TIMEOUT: int = 15  # seconds for coordinator pre-setup
_COORDINATOR_REFRESH_TIMEOUT: int = 45  # seconds for first refresh


async def async_initialize_managers(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    dogs_config: list[DogConfigData],
    profile: str,
    skip_optional_setup: bool = False,
) -> PawControlRuntimeData:
    """Initialize all managers and create runtime data.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        dogs_config: Validated dogs configuration
        profile: Entity profile name
        skip_optional_setup: Skip optional manager initialization

    Returns:
        Initialized runtime data

    Raises:
        ConfigEntryNotReady: If initialization fails
        ConfigEntryAuthFailed: If authentication fails
        ValidationError: If validation fails
    """
    # Create session and coordinator  # noqa: E114
    session = async_get_clientsession(hass)
    coordinator = PawControlCoordinator(hass, entry, session)
    # Initialize coordinator  # noqa: E114
    await _async_initialize_coordinator(coordinator, skip_optional_setup)
    # Create core managers  # noqa: E114
    core_managers = await _async_create_core_managers(
        hass,
        entry,
        coordinator,
        dogs_config,
        session,
    )

    # Create optional managers  # noqa: E114
    optional_managers = await _async_create_optional_managers(
        hass,
        entry,
        dogs_config,
        core_managers,
        skip_optional_setup,
    )

    # Initialize all managers in parallel  # noqa: E114
    await _async_initialize_all_managers(
        core_managers,
        optional_managers,
        dogs_config,
        entry,
    )

    # Attach managers to coordinator  # noqa: E114
    _attach_managers_to_coordinator(coordinator, core_managers, optional_managers)
    # Create runtime data  # noqa: E114
    runtime_data = _create_runtime_data(
        entry,
        coordinator,
        core_managers,
        optional_managers,
        dogs_config,
        profile,
    )

    # Register runtime monitors  # noqa: E114
    _register_runtime_monitors(runtime_data)
    _LOGGER.debug("Manager initialization completed successfully")
    return runtime_data
async def _async_initialize_coordinator(
    coordinator: PawControlCoordinator,
    skip_optional_setup: bool,
) -> None:
    """Initialize and refresh coordinator.

    Args:
        coordinator: Coordinator to initialize
        skip_optional_setup: Skip initialization if mocked

    Raises:
        ConfigEntryNotReady: If initialization fails
        ConfigEntryAuthFailed: If authentication fails
    """
    # Pre-setup coordinator  # noqa: E114
    coordinator_setup_start = time.monotonic()
    try:
        prepare_method = getattr(coordinator, "async_prepare_entry", None)
        if callable(prepare_method) and not skip_optional_setup:
            await asyncio.wait_for(
                prepare_method(),
                timeout=_COORDINATOR_SETUP_TIMEOUT,
            )
            coordinator_setup_duration = time.monotonic() - coordinator_setup_start
            _LOGGER.debug(
                "Coordinator pre-setup completed in %.2f seconds",
                coordinator_setup_duration,
            )
    except TimeoutError as err:
        coordinator_setup_duration = time.monotonic() - coordinator_setup_start
        raise ConfigEntryNotReady(
            f"Coordinator pre-setup timeout after {coordinator_setup_duration:.2f}s",
        ) from err
    except ConfigEntryAuthFailed:
        raise
    except (OSError, ConnectionError) as err:
        raise ConfigEntryNotReady(
            f"Network connectivity issue during coordinator pre-setup: {err}",
        ) from err

    # First refresh  # noqa: E114
    coordinator_refresh_start = time.monotonic()
    try:
        first_refresh = getattr(
            coordinator,
            "async_config_entry_first_refresh",
            None,
        )
        if callable(first_refresh) and not skip_optional_setup:
            await asyncio.wait_for(
                first_refresh(),
                timeout=_COORDINATOR_REFRESH_TIMEOUT,
            )
            coordinator_refresh_duration = time.monotonic() - coordinator_refresh_start
            _LOGGER.debug(
                "Coordinator refresh completed in %.2f seconds",
                coordinator_refresh_duration,
            )
    except TimeoutError as err:
        coordinator_refresh_duration = time.monotonic() - coordinator_refresh_start
        raise ConfigEntryNotReady(
            f"Coordinator initialization timeout after {coordinator_refresh_duration:.2f}s",
        ) from err
    except ConfigEntryAuthFailed:
        raise
    except (OSError, ConnectionError) as err:
        raise ConfigEntryNotReady(
            f"Network connectivity issue during coordinator setup: {err}",
        ) from err


async def _async_create_core_managers(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    coordinator: PawControlCoordinator,
    dogs_config: list[DogConfigData],
    session: Any,
) -> dict[str, Any]:
    """Create core managers.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        coordinator: Initialized coordinator
        dogs_config: Dogs configuration
        session: HTTP session

    Returns:
        Dictionary of core managers
    """
    dogs_config_payload: list[DogConfigData] = list(dogs_config)
    dog_ids: list[str] = [dog[DOG_ID_FIELD] for dog in dogs_config]
    data_manager = PawControlDataManager(
        hass,
        entry.entry_id,
        coordinator=coordinator,
        dogs_config=dogs_config_payload,
    )

    notification_manager = PawControlNotificationManager(
        hass,
        entry.entry_id,
        session=session,
    )

    feeding_manager = FeedingManager(hass)
    walk_manager = WalkManager()
    entity_factory = EntityFactory(coordinator, prewarm=True)
    return {
        "data_manager": data_manager,
        "notification_manager": notification_manager,
        "feeding_manager": feeding_manager,
        "walk_manager": walk_manager,
        "entity_factory": entity_factory,
        "dog_ids": dog_ids,
    }


async def _async_create_optional_managers(
    hass: HomeAssistant,
    entry: PawControlConfigEntry,
    dogs_config: list[DogConfigData],
    core_managers: dict[str, Any],
    skip_optional_setup: bool,
) -> dict[str, Any]:
    """Create optional managers.

    Args:
        hass: Home Assistant instance
        entry: Config entry
        dogs_config: Dogs configuration
        core_managers: Dictionary of core managers
        skip_optional_setup: Skip optional manager creation

    Returns:
        Dictionary of optional managers
    """
    optional_managers: dict[str, Any] = {
        "helper_manager": None,
        "script_manager": None,
        "door_sensor_manager": None,
        "garden_manager": None,
        "gps_geofence_manager": None,
        "geofencing_manager": None,
    }

    if skip_optional_setup:
        _LOGGER.debug("Skipping optional manager creation")
        return optional_managers

    # Create standard optional managers  # noqa: E114
    optional_managers["helper_manager"] = PawControlHelperManager(hass, entry)
    optional_managers["script_manager"] = PawControlScriptManager(hass, entry)
    optional_managers["door_sensor_manager"] = DoorSensorManager(hass, entry.entry_id)
    optional_managers["garden_manager"] = GardenManager(hass, entry.entry_id)
    # Migrate script manager options if needed  # noqa: E114
    script_manager = optional_managers["script_manager"]
    if script_manager is not None:
        migrated_options = script_manager.ensure_resilience_threshold_options()
        if migrated_options is not None:
            hass.config_entries.async_update_entry(entry, options=migrated_options)
    # Create GPS managers if GPS is enabled  # noqa: E114
    gps_enabled = any(
        bool(dog.get(DOG_MODULES_FIELD, {}).get(MODULE_GPS, False))
        for dog in dogs_config
    )

    if gps_enabled:
        notification_manager = core_managers["notification_manager"]

        gps_geofence_manager = GPSGeofenceManager(hass)
        gps_geofence_manager.set_notification_manager(notification_manager)
        optional_managers["gps_geofence_manager"] = gps_geofence_manager

        geofencing_manager = PawControlGeofencing(hass, entry.entry_id)
        geofencing_manager.set_notification_manager(notification_manager)
        optional_managers["geofencing_manager"] = geofencing_manager

        _LOGGER.debug("GPS/geofencing managers created for GPS-enabled dogs")
    else:
        _LOGGER.debug("GPS/geofencing managers not created - GPS disabled")

    return optional_managers
async def _async_initialize_all_managers(
    core_managers: dict[str, Any],
    optional_managers: dict[str, Any],
    dogs_config: list[DogConfigData],
    entry: PawControlConfigEntry,
) -> None:
    """Initialize all managers in parallel.

    Args:
        core_managers: Dictionary of core managers
        optional_managers: Dictionary of optional managers
        dogs_config: Dogs configuration
        entry: Config entry

    Raises:
        TimeoutError: If initialization times out
        ValidationError: If validation fails
    """
    initialization_tasks: list[asyncio.Task[None]] = []
    dog_ids = core_managers["dog_ids"]
    # Initialize core managers  # noqa: E114
    data_manager = core_managers["data_manager"]
    notification_manager = core_managers["notification_manager"]
    feeding_manager = core_managers["feeding_manager"]
    walk_manager = core_managers["walk_manager"]
    initialization_tasks.append(
        asyncio.create_task(
            _async_initialize_manager_with_timeout(
                "data_manager",
                data_manager.async_initialize(),
            ),
        ),
    )

    initialization_tasks.append(
        asyncio.create_task(
            _async_initialize_manager_with_timeout(
                "notification_manager",
                notification_manager.async_initialize(),
            ),
        ),
    )

    initialization_tasks.append(
        asyncio.create_task(
            _async_initialize_manager_with_timeout(
                "feeding_manager",
                feeding_manager.async_initialize(
                    cast(Sequence[JSONLikeMapping], dogs_config),
                ),
            ),
        ),
    )

    initialization_tasks.append(
        asyncio.create_task(
            _async_initialize_manager_with_timeout(
                "walk_manager",
                walk_manager.async_initialize(dog_ids),
            ),
        ),
    )

    # Initialize optional managers  # noqa: E114
    for manager_name, manager in optional_managers.items():
        if manager is None:
            continue
        if manager_name == "door_sensor_manager":
            initialization_tasks.append(
                asyncio.create_task(
                    _async_initialize_manager_with_timeout(
                        manager_name,
                        manager.async_initialize(
                            dogs=dogs_config,
                            walk_manager=walk_manager,
                            notification_manager=notification_manager,
                            data_manager=data_manager,
                        ),
                    ),
                ),
            )
        elif manager_name == "garden_manager":
            door_sensor_manager = optional_managers.get("door_sensor_manager")
            initialization_tasks.append(
                asyncio.create_task(
                    _async_initialize_manager_with_timeout(
                        manager_name,
                        manager.async_initialize(
                            dogs=dog_ids,
                            notification_manager=notification_manager,
                            door_sensor_manager=door_sensor_manager,
                        ),
                    ),
                ),
            )
        elif manager_name == "geofencing_manager":
            await _async_initialize_geofencing_manager(
                manager,
                dog_ids,
                entry,
                initialization_tasks,
            )
        elif hasattr(manager, "async_initialize"):
            initialization_tasks.append(
                asyncio.create_task(
                    _async_initialize_manager_with_timeout(
                        manager_name,
                        manager.async_initialize(),
                    ),
                ),
            )

    # Wait for all initializations  # noqa: E114
    await asyncio.gather(*initialization_tasks, return_exceptions=False)
async def _async_initialize_geofencing_manager(
    geofencing_manager: Any,
    dog_ids: list[str],
    entry: PawControlConfigEntry,
    initialization_tasks: list[asyncio.Task[None]],
) -> None:
    """Initialize geofencing manager with configuration.

    Args:
        geofencing_manager: Geofencing manager instance
        dog_ids: List of dog IDs
        entry: Config entry
        initialization_tasks: List to append initialization task to
    """
    geofence_options_raw = entry.options.get("geofence_settings", {})
    geofence_options = (
        geofence_options_raw if isinstance(geofence_options_raw, Mapping) else {}
    )

    dog_options_raw = entry.options.get(CONF_DOG_OPTIONS, {})
    dog_options = dog_options_raw if isinstance(dog_options_raw, Mapping) else {}
    per_dog_geofence_settings: list[Mapping[str, object]] = []
    for dog_id in dog_ids:
        entry_payload = dog_options.get(dog_id)
        if not isinstance(entry_payload, Mapping):
            continue
        geofence_payload = entry_payload.get("geofence_settings")
        if isinstance(geofence_payload, Mapping):
            per_dog_geofence_settings.append(
                cast(Mapping[str, object], geofence_payload)
            )
    geofencing_enabled = any(
        settings.get("geofencing_enabled", False)
        for settings in per_dog_geofence_settings
    ) or bool(geofence_options.get("geofencing_enabled", False))

    use_home_location = (
        any(
            settings.get("use_home_location", True)
            for settings in per_dog_geofence_settings
        )
        if per_dog_geofence_settings
        else bool(geofence_options.get("use_home_location", True))
    )

    radius_candidates: list[float] = []
    for settings in per_dog_geofence_settings:
        radius_value = settings.get("geofence_radius_m")
        if isinstance(radius_value, int | float):
            radius_candidates.append(float(radius_value))
    if radius_candidates:
        home_zone_radius = int(max(radius_candidates))
    else:
        radius = geofence_options.get("geofence_radius_m", 50)
        home_zone_radius = int(radius) if isinstance(radius, int | float) else 50

    initialization_tasks.append(
        asyncio.create_task(
            _async_initialize_manager_with_timeout(
                "geofencing_manager",
                geofencing_manager.async_initialize(
                    dogs=dog_ids,
                    enabled=geofencing_enabled,
                    use_home_location=use_home_location,
                    home_zone_radius=home_zone_radius,
                ),
            ),
        ),
    )


async def _async_initialize_manager_with_timeout(
    manager_name: str,
    coro: Any,
    timeout: int = _MANAGER_INIT_TIMEOUT,
) -> None:
    """Initialize a manager with timeout and error handling.

    Args:
        manager_name: Name of the manager for logging
        coro: Coroutine to await
        timeout: Timeout in seconds

    Raises:
        TimeoutError: If initialization times out
        Exception: If initialization fails
    """
    start_time = time.monotonic()
    try:
        await asyncio.wait_for(coro, timeout=timeout)
        duration = time.monotonic() - start_time
        _LOGGER.debug("Initialized %s in %.2f seconds", manager_name, duration)
    except TimeoutError:
        duration = time.monotonic() - start_time
        _LOGGER.error(
            "Manager %s initialization timed out after %.2f seconds",
            manager_name,
            duration,
        )
        raise
    except Exception as err:
        duration = time.monotonic() - start_time
        _LOGGER.error(
            "Manager %s initialization failed after %.2f seconds: %s",
            manager_name,
            duration,
            err,
        )
        raise


def _attach_managers_to_coordinator(
    coordinator: PawControlCoordinator,
    core_managers: dict[str, Any],
    optional_managers: dict[str, Any],
) -> None:
    """Attach runtime managers to coordinator.

    Args:
        coordinator: Coordinator instance
        core_managers: Core managers dict
        optional_managers: Optional managers dict
    """
    coordinator.attach_runtime_managers(
        data_manager=core_managers["data_manager"],
        feeding_manager=core_managers["feeding_manager"],
        walk_manager=core_managers["walk_manager"],
        notification_manager=core_managers["notification_manager"],
        gps_geofence_manager=optional_managers.get("gps_geofence_manager"),
        geofencing_manager=optional_managers.get("geofencing_manager"),
        garden_manager=optional_managers.get("garden_manager"),
    )

    # Share resilience manager  # noqa: E114
    gps_geofence_manager = optional_managers.get("gps_geofence_manager")
    if gps_geofence_manager:
        gps_geofence_manager.resilience_manager = coordinator.resilience_manager
        _LOGGER.debug("Shared ResilienceManager with GPS manager")

    notification_manager = core_managers["notification_manager"]
    if notification_manager:
        notification_manager.resilience_manager = coordinator.resilience_manager
        _LOGGER.debug("Shared ResilienceManager with Notification manager")


def _create_runtime_data(
    entry: PawControlConfigEntry,
    coordinator: PawControlCoordinator,
    core_managers: dict[str, Any],
    optional_managers: dict[str, Any],
    dogs_config: list[DogConfigData],
    profile: str,
) -> PawControlRuntimeData:
    """Create runtime data structure.

    Args:
        entry: Config entry
        coordinator: Coordinator instance
        core_managers: Core managers dict
        optional_managers: Optional managers dict
        dogs_config: Dogs configuration
        profile: Entity profile

    Returns:
        Populated runtime data
    """
    runtime_data = PawControlRuntimeData(
        coordinator=coordinator,
        data_manager=core_managers["data_manager"],
        notification_manager=core_managers["notification_manager"],
        feeding_manager=core_managers["feeding_manager"],
        walk_manager=core_managers["walk_manager"],
        entity_factory=core_managers["entity_factory"],
        entity_profile=str(profile),
        dogs=dogs_config,
        config_entry_data=cast(ConfigEntryDataPayload, entry.data),
        config_entry_options=cast(ConfigEntryOptionsPayload, entry.options),
    )

    runtime_data.helper_manager = optional_managers.get("helper_manager")
    runtime_data.script_manager = optional_managers.get("script_manager")
    runtime_data.geofencing_manager = optional_managers.get("geofencing_manager")
    runtime_data.gps_geofence_manager = optional_managers.get("gps_geofence_manager")
    runtime_data.door_sensor_manager = optional_managers.get("door_sensor_manager")
    runtime_data.garden_manager = optional_managers.get("garden_manager")
    runtime_data.device_api_client = coordinator.api_client
    # Attach runtime data to script manager  # noqa: E114
    script_manager = optional_managers.get("script_manager")
    if script_manager is not None:
        script_manager.attach_runtime_manual_history(runtime_data)
        script_manager.sync_manual_event_history()

    # Update telemetry  # noqa: E114
    update_runtime_reconfigure_summary(runtime_data)
    return runtime_data
def _register_runtime_monitors(runtime_data: PawControlRuntimeData) -> None:
    """Register runtime cache monitors.

    Args:
        runtime_data: Runtime data
    """
    data_manager = runtime_data.data_manager
    if hasattr(data_manager, "register_runtime_cache_monitors"):
        data_manager.register_runtime_cache_monitors(runtime_data)
