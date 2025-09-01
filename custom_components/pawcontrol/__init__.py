"""The Paw Control integration for Home Assistant.

This integration provides comprehensive smart dog management functionality
including GPS tracking, feeding management, health monitoring, and walk tracking.
Designed to meet Home Assistant's Platinum quality standards with full async
operation, complete type annotations, and robust error handling.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_DASHBOARD_AUTO_CREATE,
    CONF_DASHBOARD_ENABLED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_NAME,
    DEFAULT_DASHBOARD_AUTO_CREATE,
    DEFAULT_DASHBOARD_ENABLED,
    DOMAIN,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_VISITOR,
    MODULE_WALK,
)
from .coordinator import PawControlCoordinator
from .dashboard_generator import PawControlDashboardGenerator
from .data_manager import PawControlDataManager
from .exceptions import ConfigurationError
from .notifications import PawControlNotificationManager
from .services import PawControlServiceManager, async_setup_daily_reset_scheduler
from .types import DogConfigData, PawControlRuntimeData
from .utils import (
    performance_monitor,
    safe_convert,
    validate_dog_id,
    validate_enum_value,
    validate_weight_enhanced,
)

_LOGGER = logging.getLogger(__name__)

# This integration can only be configured via the UI
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Ordered platform loading for optimal dependency resolution
# Legacy: All platforms (kept for reference and fallback)
ALL_PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.DEVICE_TRACKER,
    Platform.DATE,
    Platform.DATETIME,
]


def get_platforms_for_modules(dogs: list[DogConfigData]) -> list[Platform]:
    """Ermittelt nur die benötigten Plattformen basierend auf aktivierten Modulen.

    This feature solves the Entity Registry problem through intelligent
    platform loading. Only enabled modules load the corresponding
    platforms, which improves performance and prevents unnecessary entities.

    Args:
        dogs: Liste der konfigurierten Hunde mit ihren Modulen

    Returns:
        Liste der benötigten Plattformen in optimaler Ladereihenfolge
    """

    # Module-zu-Platform-Mapping basierend auf Funktionalität
    MODULE_PLATFORM_MAP = {
        MODULE_GPS: {
            Platform.DEVICE_TRACKER,  # GPS Position Tracking
            Platform.SENSOR,  # GPS Status, Accuracy, Distance
        },
        MODULE_FEEDING: {
            Platform.SENSOR,  # Feeding Stats, Last Fed
            Platform.BUTTON,  # Feed Dog Button
            Platform.SELECT,  # Meal Type Selection
            Platform.DATETIME,  # Last Feeding Time
        },
        MODULE_HEALTH: {
            Platform.SENSOR,  # Health Status, Weight Trends
            Platform.NUMBER,  # Weight Input, Temperature
            Platform.DATE,  # Last Vet Visit, Next Checkup
        },
        MODULE_WALK: {
            Platform.SENSOR,  # Walk Stats, Duration, Distance
            Platform.BUTTON,  # Start/End Walk Buttons
            Platform.BINARY_SENSOR,  # Currently Walking Status
        },
        MODULE_NOTIFICATIONS: {
            Platform.SWITCH,  # Notification Enable/Disable
            Platform.SELECT,  # Notification Priority Level
        },
        MODULE_DASHBOARD: {
            Platform.SENSOR,  # Dashboard Summary Stats
            Platform.TEXT,  # Dashboard Status Messages
        },
        MODULE_VISITOR: {
            Platform.SWITCH,  # Visitor Mode On/Off
            Platform.BINARY_SENSOR,  # Visitor Present Status
        },
    }

    # Core Plattformen die IMMER benötigt werden
    required_platforms = {
        Platform.SENSOR,  # Basis-Sensoren für jeden Hund
        Platform.BUTTON,  # Basis-Buttons (Daily Reset etc.)
    }

    # Sammle alle aktivierten Module aus allen Hunden
    enabled_modules = set()
    for dog in dogs:
        dog_modules = dog.get("modules", {})
        for module_name, is_enabled in dog_modules.items():
            if is_enabled:
                enabled_modules.add(module_name)

    # Ermittle benötigte Plattformen basierend auf aktivierten Modulen
    needed_platforms = required_platforms.copy()

    for module in enabled_modules:
        module_platforms = MODULE_PLATFORM_MAP.get(module, set())
        needed_platforms.update(module_platforms)

    # Konvertiere zu sortierter Liste für optimale Ladereihenfolge
    platform_order = [
        Platform.SENSOR,  # Basis-Sensoren zuerst
        Platform.BINARY_SENSOR,  # Binäre Sensoren
        Platform.BUTTON,  # Buttons
        Platform.SWITCH,  # Switches
        Platform.NUMBER,  # Zahlen-Eingaben
        Platform.SELECT,  # Auswahl-Felder
        Platform.TEXT,  # Text-Felder
        Platform.DEVICE_TRACKER,  # Device Tracker
        Platform.DATE,  # Datum-Felder
        Platform.DATETIME,  # DateTime-Felder
    ]

    # Filtere und sortiere nach optimaler Reihenfolge
    platforms_list = [p for p in platform_order if p in needed_platforms]

    # Log für Debugging
    _LOGGER.info(
        "Modulares Platform Loading: %d Module aktiv (%s), %d/%d Plattformen geladen: %s",
        len(enabled_modules),
        ", ".join(sorted(enabled_modules)),
        len(platforms_list),
        len(ALL_PLATFORMS),
        [p.value for p in platforms_list],
    )

    return platforms_list


# OPTIMIZATION: Rate limiting für Entity Registry Updates
_PLATFORM_SETUP_LOCK = asyncio.Lock()
_PLATFORM_SETUP_DELAY = 0.1  # 100ms zwischen Platform-Setups bei mehreren Hunden


# Enhanced error handling with detailed context
class PawControlSetupError(HomeAssistantError):
    """Exception raised when Paw Control setup fails."""

    def __init__(self, message: str, error_code: str = "setup_failed") -> None:
        super().__init__(message)
        self.error_code = error_code


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Paw Control integration from configuration.yaml.

    This function handles legacy YAML configuration setup. Since Paw Control
    is designed to be configured via the UI, this function only initializes
    the domain data storage and returns True.

    Args:
        hass: Home Assistant instance
        config: Configuration dictionary from configuration.yaml

    Returns:
        True if setup was successful
    """
    # Initialize domain data storage for runtime data with type safety
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}

    _LOGGER.debug("Paw Control integration legacy setup completed")
    return True


@performance_monitor(timeout=60.0)
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Paw Control from a config entry with enhanced error handling.

    This function performs the complete setup of the Paw Control integration,
    including initialization of all core components, platform setup, service
    registration, and initial data refresh. Uses modern ConfigEntry.runtime_data
    for efficient data storage and comprehensive error handling.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing integration configuration

    Returns:
        True if setup was successful

    Raises:
        ConfigEntryNotReady: If setup cannot be completed due to temporary issues
        ConfigEntryAuthFailed: If authentication fails
        PawControlSetupError: If setup fails due to configuration issues
    """
    _LOGGER.info("Setting up Paw Control integration entry: %s", entry.entry_id)

    # Enhanced setup context manager for proper cleanup
    @asynccontextmanager
    async def setup_context():
        runtime_data: PawControlRuntimeData | None = None
        try:
            yield
        except Exception:
            # Cleanup on error
            if runtime_data:
                await _async_cleanup_runtime_data(hass, entry, runtime_data)
            raise

    async with setup_context():
        try:
            # Validate configuration early with comprehensive checks
            dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])

            if not dogs_config:
                raise ConfigurationError(
                    setting="dogs", reason="No dogs configured in entry"
                ).add_recovery_suggestion(
                    "Add at least one dog via the integration configuration"
                )

            # Enhanced dog configuration validation
            await _async_validate_dogs_configuration(dogs_config)

            # Initialize core components with optimized timeouts for faster setup
            async with asyncio.timeout(15):  # Reduced from 45s to 15s for faster setup
                # Initialize coordinator with enhanced configuration
                coordinator = PawControlCoordinator(hass, entry)

                # Initialize data manager with async context and validation
                data_manager = PawControlDataManager(hass, entry.entry_id)
                await data_manager.async_initialize()

                # Initialize notification manager with full async support
                notification_manager = PawControlNotificationManager(
                    hass, entry.entry_id
                )
                await notification_manager.async_initialize()

            # Create modern runtime data object with comprehensive metadata
            runtime_data: PawControlRuntimeData = {
                "coordinator": coordinator,
                "data_manager": data_manager,
                "notification_manager": notification_manager,
                "config_entry": entry,
                "dogs": dogs_config,
            }

            # Store using modern runtime_data API for optimal performance
            entry.runtime_data = runtime_data

            # Maintain backward compatibility storage with deprecation warning
            hass.data.setdefault(DOMAIN, {})
            hass.data[DOMAIN][entry.entry_id] = {
                "coordinator": coordinator,
                "data": data_manager,
                "notifications": notification_manager,
                "dashboard_generator": None,  # Will be initialized after platforms
                "entry": entry,
            }

            # Setup platforms using modulares Loading für optimale Performance und Entity Registry
            try:
                # ✅ LÖSUNG: Modulares Platform Loading basierend auf aktivierten Modulen
                needed_platforms = get_platforms_for_modules(dogs_config)

                # Fallback auf alle Plattformen falls keine Module konfiguriert (Safety)
                if not needed_platforms:
                    _LOGGER.warning(
                        "Keine Module aktiviert, verwende Fallback auf alle Plattformen"
                    )
                    needed_platforms = ALL_PLATFORMS

                # FIX: Rate-limited platform setup to prevent Entity Registry flooding
                async with _PLATFORM_SETUP_LOCK:
                    # Bei mehreren Hunden: Gestaffelte Platform-Initialisierung
                    if len(dogs_config) > 2:
                        # Teile Platforms in kleinere Gruppen auf
                        platform_groups = [
                            needed_platforms[i : i + 3]
                            for i in range(0, len(needed_platforms), 3)
                        ]

                        for group_idx, platform_group in enumerate(platform_groups):
                            async with asyncio.timeout(15):  # Timeout pro Gruppe
                                await hass.config_entries.async_forward_entry_setups(
                                    entry, platform_group
                                )

                            # Verzögerung zwischen Gruppen bei vielen Hunden
                            if group_idx < len(platform_groups) - 1:
                                await asyncio.sleep(_PLATFORM_SETUP_DELAY)
                    else:
                        # Wenige Hunde: Normal setup
                        async with asyncio.timeout(30):
                            await hass.config_entries.async_forward_entry_setups(
                                entry, needed_platforms
                            )

                _LOGGER.info(
                    "Modulares Setup erfolgreich: %d von %d Plattformen für %d Hunde (%.0f%% optimiert)",
                    len(needed_platforms),
                    len(ALL_PLATFORMS),
                    len(dogs_config),
                    (1 - len(needed_platforms) / len(ALL_PLATFORMS)) * 100,
                )
            except asyncio.TimeoutError:
                _LOGGER.error("Platform setup timed out after 30 seconds")
                await _async_cleanup_runtime_data(hass, entry, runtime_data)
                raise ConfigEntryNotReady("Platform setup timed out") from None
            except Exception as err:
                _LOGGER.error("Failed to setup platforms: %s", err, exc_info=True)
                # Clean up on platform setup failure
                await _async_cleanup_runtime_data(hass, entry, runtime_data)
                raise ConfigEntryNotReady(f"Platform setup failed: {err}") from err

            # Register services using the new service manager
            service_manager = PawControlServiceManager(hass)
            await service_manager.async_register_services()

            # Store service manager in runtime data for cleanup
            runtime_data["service_manager"] = service_manager
            hass.data[DOMAIN][entry.entry_id]["service_manager"] = service_manager

            # Setup daily reset scheduler with modern async patterns and error handling
            await async_setup_daily_reset_scheduler(hass, entry)

            # Setup dashboard if enabled
            if entry.options.get(CONF_DASHBOARD_ENABLED, DEFAULT_DASHBOARD_ENABLED):
                try:
                    dashboard_generator = PawControlDashboardGenerator(hass, entry)
                    await dashboard_generator.async_initialize()

                    if entry.options.get(
                        CONF_DASHBOARD_AUTO_CREATE, DEFAULT_DASHBOARD_AUTO_CREATE
                    ):
                        dashboard_url = await dashboard_generator.async_create_dashboard(
                            dogs_config,
                            options={
                                "title": f"🐕 {entry.data.get(CONF_NAME, 'Paw Control')}",
                                "theme": entry.options.get(
                                    "dashboard_theme", "default"
                                ),
                                "mode": entry.options.get("dashboard_mode", "full"),
                            },
                        )
                        _LOGGER.info("Created dashboard at: %s", dashboard_url)

                        # Create individual dog dashboards if configured
                        if entry.options.get("dashboard_per_dog", False):
                            for dog in dogs_config:
                                dog_url = await dashboard_generator.async_create_dog_dashboard(
                                    dog
                                )
                                _LOGGER.info(
                                    "Created dog dashboard for %s at: %s",
                                    dog[CONF_DOG_NAME],
                                    dog_url,
                                )

                    # Update runtime data with dashboard generator
                    runtime_data["dashboard_generator"] = dashboard_generator
                    hass.data[DOMAIN][entry.entry_id]["dashboard_generator"] = (
                        dashboard_generator
                    )

                except Exception as err:
                    _LOGGER.error("Failed to setup dashboard: %s", err)
                    # Dashboard failure is non-critical, continue setup

            # Perform initial data refresh with shorter timeout for faster setup
            try:
                async with asyncio.timeout(10):  # Reduced from 30s to 10s
                    await coordinator.async_config_entry_first_refresh()
                _LOGGER.debug("Initial data refresh completed successfully")
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Initial data refresh timed out after 10s, integration will continue with cached data"
                )
            except Exception as err:
                _LOGGER.warning(
                    "Initial data refresh failed: %s, continuing setup", err
                )
                # Continue setup even if initial refresh fails

            # Setup complete - log comprehensive status
            _LOGGER.info(
                "Paw Control integration setup completed successfully: "
                "%d dogs, %d/%d platforms loaded (modulares Loading), entry_id=%s",
                len(dogs_config),
                len(needed_platforms),
                len(ALL_PLATFORMS),
                entry.entry_id,
            )

            return True

        except ConfigEntryNotReady:
            raise
        except ConfigurationError as err:
            _LOGGER.error("Configuration error during setup: %s", err.to_dict())
            raise ConfigEntryNotReady(f"Configuration error: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error during setup: %s", err, exc_info=True)
            raise ConfigEntryNotReady(f"Setup failed: {err}") from err


async def _async_validate_dogs_configuration(dogs_config: list[DogConfigData]) -> None:
    """Validate dogs configuration with comprehensive checks.

    Args:
        dogs_config: List of dog configurations to validate

    Raises:
        ConfigurationError: If validation fails
    """
    seen_dog_ids = set()
    seen_dog_names = set()

    for i, dog in enumerate(dogs_config):
        dog_id = dog.get(CONF_DOG_ID)
        dog_name = dog.get(CONF_DOG_NAME)

        # Validate required fields
        if not dog_id:
            raise ConfigurationError(
                setting=f"dogs[{i}].dog_id", reason="Dog ID is required"
            )

        if not dog_name:
            raise ConfigurationError(
                setting=f"dogs[{i}].dog_name", reason="Dog name is required"
            )

        # Validate dog ID format
        is_valid, error_msg = validate_dog_id(dog_id)
        if not is_valid:
            raise ConfigurationError(
                setting=f"dogs[{i}].dog_id", value=dog_id, reason=error_msg
            )

        # Check for duplicates
        if dog_id in seen_dog_ids:
            raise ConfigurationError(
                setting=f"dogs[{i}].dog_id",
                value=dog_id,
                reason="Duplicate dog ID found",
            )

        if dog_name in seen_dog_names:
            raise ConfigurationError(
                setting=f"dogs[{i}].dog_name",
                value=dog_name,
                reason="Duplicate dog name found",
            )

        seen_dog_ids.add(dog_id)
        seen_dog_names.add(dog_name)

        # Validate optional fields with enhanced checking
        if "dog_weight" in dog and dog["dog_weight"] is not None:
            dog_size = dog.get("dog_size")
            dog_age = dog.get("dog_age")

            is_valid, error_msg = validate_weight_enhanced(
                dog["dog_weight"], dog_size, dog_age
            )
            if not is_valid:
                raise ConfigurationError(
                    setting=f"dogs[{i}].dog_weight",
                    value=dog["dog_weight"],
                    reason=error_msg,
                )

        # Validate age if provided
        if "dog_age" in dog and dog["dog_age"] is not None:
            age = safe_convert(dog["dog_age"], int, 0)
            if age < 0 or age > 30:
                raise ConfigurationError(
                    setting=f"dogs[{i}].dog_age",
                    value=age,
                    reason="Dog age must be between 0 and 30 years",
                )

        # Validate size if provided
        if "dog_size" in dog and dog["dog_size"]:
            is_valid, error_msg = validate_enum_value(
                dog["dog_size"],
                ("toy", "small", "medium", "large", "giant"),
                "dog_size",
            )
            if not is_valid:
                raise ConfigurationError(
                    setting=f"dogs[{i}].dog_size",
                    value=dog["dog_size"],
                    reason=error_msg,
                )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Paw Control config entry with comprehensive cleanup.

    Performs clean shutdown of all integration components including platform
    unloading, service cleanup, and proper resource disposal with timeout protection.

    Args:
        hass: Home Assistant instance
        entry: Config entry to unload

    Returns:
        True if unload was successful
    """
    _LOGGER.info("Unloading Paw Control integration entry: %s", entry.entry_id)

    try:
        # Ermittle die aktuell geladenen Plattformen basierend auf Konfiguration
        dogs_config: list[DogConfigData] = entry.data.get(CONF_DOGS, [])
        loaded_platforms = (
            get_platforms_for_modules(dogs_config) if dogs_config else ALL_PLATFORMS
        )

        # Unload alle aktuell geladenen Plattformen mit timeout protection
        async with asyncio.timeout(30):
            unload_success = await hass.config_entries.async_unload_platforms(
                entry, loaded_platforms
            )

        if unload_success:
            # Get runtime data using modern approach with fallback
            runtime_data = getattr(entry, "runtime_data", None)

            if runtime_data:
                await _async_cleanup_runtime_data(hass, entry, runtime_data)
            else:
                # Fallback to legacy data cleanup
                entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
                await _async_cleanup_legacy_entry_data(entry_data)

            # Remove entry data from both storage locations
            hass.data[DOMAIN].pop(entry.entry_id, None)

            # Clean up runtime data reference
            if hasattr(entry, "runtime_data"):
                delattr(entry, "runtime_data")

            _LOGGER.info("Paw Control integration unloaded successfully")
        else:
            _LOGGER.error("Failed to unload Paw Control platforms")

        return unload_success

    except asyncio.TimeoutError:
        _LOGGER.error("Timeout during platform unloading")
        return False
    except Exception as err:
        _LOGGER.error("Error during unload: %s", err, exc_info=True)
        return False


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a Paw Control config entry with enhanced error handling.

    Performs a complete reload of the integration by unloading and then
    setting up the entry again. Useful for configuration changes.

    Args:
        hass: Home Assistant instance
        entry: Config entry to reload
    """
    _LOGGER.info("Reloading Paw Control integration entry: %s", entry.entry_id)

    try:
        await async_unload_entry(hass, entry)
        await async_setup_entry(hass, entry)
        _LOGGER.info("Paw Control integration reloaded successfully")
    except Exception as err:
        _LOGGER.error("Failed to reload integration: %s", err, exc_info=True)
        raise


async def _async_cleanup_runtime_data(
    hass: HomeAssistant, entry: ConfigEntry, runtime_data: PawControlRuntimeData
) -> None:
    """Clean up runtime data components with proper async shutdown and timeout protection.

    Args:
        hass: Home Assistant instance
        entry: Config entry being cleaned up
        runtime_data: Runtime data to clean up
    """
    _LOGGER.debug("Cleaning up runtime data for entry %s", entry.entry_id)

    # Define component shutdown order (reverse dependency order)
    shutdown_tasks = []

    # Service manager cleanup
    service_manager = runtime_data.get("service_manager")
    if service_manager and hasattr(service_manager, "async_unregister_services"):
        shutdown_tasks.append(
            _async_shutdown_component(
                "service_manager", service_manager.async_unregister_services()
            )
        )

    # Dashboard generator cleanup
    dashboard_generator = runtime_data.get("dashboard_generator")
    if dashboard_generator and hasattr(dashboard_generator, "async_cleanup"):
        shutdown_tasks.append(
            _async_shutdown_component(
                "dashboard_generator", dashboard_generator.async_cleanup()
            )
        )

    # Notification manager cleanup
    notification_manager = runtime_data.get("notification_manager")
    if notification_manager and hasattr(notification_manager, "async_shutdown"):
        shutdown_tasks.append(
            _async_shutdown_component(
                "notification_manager", notification_manager.async_shutdown()
            )
        )

    # Data manager cleanup
    data_manager = runtime_data.get("data_manager")
    if data_manager and hasattr(data_manager, "async_shutdown"):
        shutdown_tasks.append(
            _async_shutdown_component("data_manager", data_manager.async_shutdown())
        )

    # Coordinator cleanup
    coordinator = runtime_data.get("coordinator")
    if coordinator and hasattr(coordinator, "async_shutdown"):
        shutdown_tasks.append(
            _async_shutdown_component("coordinator", coordinator.async_shutdown())
        )

    # Execute all shutdowns concurrently with timeout
    if shutdown_tasks:
        try:
            async with asyncio.timeout(20):
                await asyncio.gather(*shutdown_tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            _LOGGER.warning("Component cleanup timed out")


async def _async_shutdown_component(component_name: str, shutdown_coro) -> None:
    """Shutdown a single component with error handling.

    Args:
        component_name: Name of the component for logging
        shutdown_coro: Shutdown coroutine to execute
    """
    try:
        await shutdown_coro
        _LOGGER.debug("Successfully shutdown %s", component_name)
    except Exception as err:
        _LOGGER.warning("Error shutting down %s: %s", component_name, err)


async def _async_cleanup_legacy_entry_data(entry_data: dict[str, Any]) -> None:
    """Clean up legacy entry data format with proper error handling.

    Args:
        entry_data: Legacy entry data dictionary
    """
    _LOGGER.debug("Cleaning up legacy entry data")

    # Define legacy component names and their shutdown methods
    legacy_components = [
        ("service_manager", entry_data.get("service_manager")),
        ("notifications", entry_data.get("notifications")),
        ("data", entry_data.get("data")),
        ("coordinator", entry_data.get("coordinator")),
    ]

    for component_name, component in legacy_components:
        if component:
            if hasattr(component, "async_unregister_services"):
                try:
                    await component.async_unregister_services()
                    _LOGGER.debug(
                        "Successfully unregistered services for %s", component_name
                    )
                except Exception as err:
                    _LOGGER.warning(
                        "Error unregistering services for %s: %s", component_name, err
                    )
            elif hasattr(component, "async_shutdown"):
                try:
                    await component.async_shutdown()
                    _LOGGER.debug("Successfully shutdown legacy %s", component_name)
                except Exception as err:
                    _LOGGER.warning(
                        "Error shutting down legacy %s: %s", component_name, err
                    )
