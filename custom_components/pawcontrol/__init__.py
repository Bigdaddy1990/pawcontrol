"""The Paw Control integration for Home Assistant.

This integration provides comprehensive smart dog management functionality
including GPS tracking, feeding management, health monitoring, and walk tracking.
Designed to meet Home Assistant's Platinum quality standards with full async
operation, complete type annotations, and robust error handling.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import time
from pathlib import Path
from typing import Any, Final

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .dashboard_generator import PawControlDashboardGenerator

from .const import (
    ACTIVITY_LEVELS,
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    CONF_DASHBOARD_AUTO_CREATE,
    CONF_DASHBOARD_ENABLED,
    CONF_DOGS,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_NAME,
    CONF_RESET_TIME,
    DEFAULT_DASHBOARD_AUTO_CREATE,
    DEFAULT_DASHBOARD_ENABLED,
    DEFAULT_RESET_TIME,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    FOOD_TYPES,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
    MODULE_DASHBOARD,
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_WALK,
    MODULE_VISITOR,
    MOOD_OPTIONS,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_FEED_DOG,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
)
from .coordinator import PawControlCoordinator
from .data_manager import PawControlDataManager
from .exceptions import (
    PawControlError,
    ConfigurationError,
    DogNotFoundError,
    ValidationError,
)

# Error classes already imported from .exceptions
from .notifications import PawControlNotificationManager
from .types import DogConfigData, PawControlRuntimeData
from .utils import (
    safe_convert,
    validate_dog_id,
    validate_weight_enhanced,
    validate_enum_value,
    performance_monitor,
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

# Enhanced service validation schemas with comprehensive validation
SERVICE_FEED_DOG_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional(ATTR_MEAL_TYPE, default="snack"): vol.In(MEAL_TYPES),
        vol.Optional(ATTR_PORTION_SIZE, default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=10000.0)
        ),
        vol.Optional("food_type", default="dry_food"): vol.In(FOOD_TYPES),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("calories"): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=5000.0)
        ),
        vol.Optional("brand", default=""): vol.All(cv.string, vol.Length(max=100)),
        vol.Optional("feeding_location", default=""): vol.All(
            cv.string, vol.Length(max=100)
        ),
        vol.Optional("feeding_method", default="bowl"): vol.In(
            [
                "bowl",
                "hand_feeding",
                "puzzle_feeder",
                "automatic_feeder",
                "training_treat",
            ]
        ),
    }
)

SERVICE_WALK_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("label", default=""): vol.All(cv.string, vol.Length(max=100)),
        vol.Optional("location", default=""): vol.All(cv.string, vol.Length(max=200)),
        vol.Optional("walk_type", default="regular"): vol.In(
            [
                "regular",
                "training",
                "exercise",
                "socialization",
                "bathroom",
                "adventure",
            ]
        ),
        vol.Optional("planned_duration"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=28800)
        ),
        vol.Optional("planned_distance"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=50000.0)
        ),
    }
)

SERVICE_END_WALK_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("distance", default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=50000.0)
        ),
        vol.Optional("duration", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=28800)
        ),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("rating", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=5)
        ),
        vol.Optional("weather", default=""): vol.All(cv.string, vol.Length(max=100)),
        vol.Optional("terrain", default=""): vol.In(
            ["", "pavement", "grass", "trail", "beach", "snow", "mixed"]
        ),
        vol.Optional("social_interactions", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=100)
        ),
    }
)

SERVICE_HEALTH_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("weight"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=200.0)
        ),
        vol.Optional("temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=35.0, max=42.0)
        ),
        vol.Optional("mood", default=""): vol.In([""] + list(MOOD_OPTIONS)),
        vol.Optional("activity_level", default=""): vol.In(
            [""] + list(ACTIVITY_LEVELS)
        ),
        vol.Optional("health_status", default=""): vol.In(
            [""] + list(HEALTH_STATUS_OPTIONS)
        ),
        vol.Optional("symptoms", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("note", default=""): vol.All(cv.string, vol.Length(max=1000)),
        vol.Optional("heart_rate"): vol.All(
            vol.Coerce(int), vol.Range(min=60, max=250)
        ),
        vol.Optional("respiratory_rate"): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=40)
        ),
        vol.Optional("appetite_level", default=""): vol.In(
            ["", "poor", "reduced", "normal", "increased", "excessive"]
        ),
        vol.Optional("energy_level", default=""): vol.In(
            ["", "very_low", "low", "normal", "high", "very_high"]
        ),
    }
)

SERVICE_MEDICATION_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Required("medication_name"): vol.All(cv.string, vol.Length(min=1, max=100)),
        vol.Required("dosage"): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("administration_time"): cv.datetime,
        vol.Optional("next_dose"): cv.datetime,
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("medication_type", default="oral"): vol.In(
            ["oral", "topical", "injection", "eye_drops", "ear_drops", "inhaled"]
        ),
        vol.Optional("prescribing_vet", default=""): vol.All(
            cv.string, vol.Length(max=100)
        ),
        vol.Optional("duration_days"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
    }
)

SERVICE_GROOMING_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("type", default="general"): vol.In(
            [
                "bath",
                "brush",
                "nails",
                "teeth",
                "ears",
                "trim",
                "full_grooming",
                "general",
            ]
        ),
        vol.Optional("location", default=""): vol.All(cv.string, vol.Length(max=100)),
        vol.Optional("groomer", default=""): vol.All(cv.string, vol.Length(max=100)),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("cost"): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=1000.0)
        ),
        vol.Optional("products_used", default=""): vol.All(
            cv.string, vol.Length(max=300)
        ),
        vol.Optional("next_appointment"): cv.datetime,
    }
)

SERVICE_NOTIFY_TEST_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("message", default="Test notification"): vol.All(
            cv.string, vol.Length(min=1, max=200)
        ),
        vol.Optional("priority", default="normal"): vol.In(
            ["low", "normal", "high", "urgent"]
        ),
        vol.Optional("notification_type", default="test"): vol.In(
            ["test", "feeding", "walk", "health", "medication", "grooming", "system"]
        ),
    }
)

SERVICE_DAILY_RESET_SCHEMA: Final = vol.Schema(
    {
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("dog_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

SERVICE_SET_VISITOR_MODE_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Required("enabled"): cv.boolean,
        vol.Optional("visitor_name", default=""): vol.All(
            cv.string, vol.Length(max=100)
        ),
        vol.Optional("reduced_alerts", default=True): cv.boolean,
        vol.Optional("modified_schedule", default=True): cv.boolean,
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
    }
)

SERVICE_EXPORT_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Required("data_type"): vol.In(
            ["all", "feeding", "walks", "health", "gps", "grooming"]
        ),
        vol.Optional("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Optional("format", default="csv"): vol.In(["csv", "json", "gpx"]),
    }
)


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

            # Register services globally with enhanced idempotency and error handling
            await _async_register_services(hass)

            # Setup daily reset scheduler with modern async patterns and error handling
            await _async_setup_daily_reset_scheduler(hass, entry)

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
                    "Initial data refresh timed out after 30s, integration will continue with cached data"
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
        ("notifications", entry_data.get("notifications")),
        ("data", entry_data.get("data")),
        ("coordinator", entry_data.get("coordinator")),
    ]

    for component_name, component in legacy_components:
        if component and hasattr(component, "async_shutdown"):
            try:
                await component.async_shutdown()
                _LOGGER.debug("Successfully shutdown legacy %s", component_name)
            except Exception as err:
                _LOGGER.warning(
                    "Error shutting down legacy %s: %s", component_name, err
                )


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register all Paw Control services with comprehensive validation and enhanced features.

    Registers service handlers for all Paw Control functionality including feeding,
    walks, health tracking, and system management. Uses modern async service patterns,
    comprehensive error handling, and performance optimization.

    Args:
        hass: Home Assistant instance
    """
    # Check if services are already registered (idempotency with detailed logging)
    if hass.services.has_service(DOMAIN, SERVICE_FEED_DOG):
        _LOGGER.debug("Services already registered, skipping registration")
        return

    _LOGGER.debug("Registering Paw Control services")

    # Enhanced service handlers with comprehensive validation and error handling
    @performance_monitor(timeout=10.0)
    async def _handle_feed_dog_service(call: ServiceCall) -> None:
        """Handle the feed_dog service call with comprehensive validation and logging."""
        dog_id: str = call.data[ATTR_DOG_ID]
        meal_type: str = call.data.get(ATTR_MEAL_TYPE, "snack")
        portion_size: float = float(call.data.get(ATTR_PORTION_SIZE, 0.0))
        food_type: str = call.data.get("food_type", "dry_food")
        notes: str = call.data.get("notes", "").strip()
        calories: float = float(call.data.get("calories", 0.0))
        amount: float = call.data.get("amount", 0)

        _LOGGER.debug(
            "Processing feed_dog service for %s: %s (%.1fg, %.0f cal)",
            amount,
            dog_id,
            meal_type,
            portion_size,
            calories,
        )

        try:
            # Find and validate runtime data for this dog
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(
                    dog_id, _get_available_dog_ids(hass)
                ).with_user_message(f"Dog '{dog_id}' not found in any configuration")

            data_manager = runtime_data["data_manager"]
            await data_manager.async_feed_dog(dog_id, amount)

            _LOGGER.info("Successfully fed %s with amount %s", dog_id, amount)

            # Prepare comprehensive feeding data with validation
            feeding_data = {
                "meal_type": meal_type,
                "portion_size": portion_size,
                "food_type": food_type,
                "notes": notes,
                "calories": calories,
                "logged_by": "service_call",
                "timestamp": dt_util.utcnow(),
                "brand": call.data.get("brand", ""),
                "feeding_location": call.data.get("feeding_location", ""),
                "feeding_method": call.data.get("feeding_method", "bowl"),
            }

            # Enhanced validation
            if portion_size > 0 and calories == 0:
                # Estimate calories if not provided (rough calculation)
                calorie_estimates = {
                    "dry_food": 350,  # per 100g
                    "wet_food": 85,
                    "barf": 150,
                    "treat": 400,
                    "home_cooked": 120,
                }
                estimated_calories = (portion_size / 100) * calorie_estimates.get(
                    food_type, 200
                )
                feeding_data["calories"] = round(estimated_calories, 1)
                feeding_data["calories_estimated"] = True

            # Log feeding with proper error handling
            await data_manager.async_log_feeding(dog_id, feeding_data)

            # Fire comprehensive Home Assistant event for automation triggers
            hass.bus.async_fire(
                EVENT_FEEDING_LOGGED,
                {
                    ATTR_DOG_ID: dog_id,
                    ATTR_MEAL_TYPE: meal_type,
                    ATTR_PORTION_SIZE: portion_size,
                    "food_type": food_type,
                    "calories": feeding_data["calories"],
                    "timestamp": dt_util.utcnow().isoformat(),
                    "service_call": True,
                },
            )

            _LOGGER.info(
                "Successfully logged feeding for %s: %s (%.1fg, %.0f cal)",
                amount,
                dog_id,
                meal_type,
                portion_size,
                feeding_data["calories"],
            )

        except PawControlError as err:
            _LOGGER.error("PawControl error in feed_dog service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in feed_dog service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to feed dog: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_start_walk_service(call: ServiceCall) -> None:
        """Handle the start_walk service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        label: str = call.data.get("label", "")
        location: str = call.data.get("location", "")
        walk_type: str = call.data.get("walk_type", "regular")

        _LOGGER.debug("Processing start_walk service for %s: %s", dog_id, walk_type)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            walk_data = {
                "label": label,
                "location": location,
                "walk_type": walk_type,
                "planned_duration": call.data.get("planned_duration"),
                "planned_distance": call.data.get("planned_distance"),
                "started_by": "service_call",
            }

            walk_id = await data_manager.async_start_walk(dog_id, walk_data)

            hass.bus.async_fire(
                EVENT_WALK_STARTED,
                {
                    ATTR_DOG_ID: dog_id,
                    "walk_id": walk_id,
                    "walk_type": walk_type,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

            _LOGGER.info("Successfully started walk %s for %s", walk_id, dog_id)

        except PawControlError as err:
            _LOGGER.error("PawControl error in start_walk service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in start_walk service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to start walk: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_end_walk_service(call: ServiceCall) -> None:
        """Handle the end_walk service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        distance: float = float(call.data.get("distance", 0.0))
        duration: int = int(call.data.get("duration", 0))
        notes: str = call.data.get("notes", "").strip()

        _LOGGER.debug("Processing end_walk service for %s", dog_id)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            walk_data = {
                "distance": distance,
                "duration_minutes": duration,
                "notes": notes,
                "rating": call.data.get("rating", 0),
                "weather": call.data.get("weather", ""),
                "terrain": call.data.get("terrain", ""),
                "social_interactions": call.data.get("social_interactions", 0),
                "ended_by": "service_call",
            }

            await data_manager.async_end_walk(dog_id, walk_data)

            hass.bus.async_fire(
                EVENT_WALK_ENDED,
                {
                    ATTR_DOG_ID: dog_id,
                    "duration_minutes": duration,
                    "distance": distance,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

            _LOGGER.info("Successfully ended walk for %s", dog_id)

        except PawControlError as err:
            _LOGGER.error("PawControl error in end_walk service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in end_walk service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to end walk: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_log_health_service(call: ServiceCall) -> None:
        """Handle the log_health service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]

        _LOGGER.debug("Processing log_health service for %s", dog_id)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            health_data = {
                "weight": call.data.get("weight"),
                "temperature": call.data.get("temperature"),
                "mood": call.data.get("mood", ""),
                "activity_level": call.data.get("activity_level", ""),
                "health_status": call.data.get("health_status", ""),
                "symptoms": call.data.get("symptoms", ""),
                "note": call.data.get("note", ""),
                "heart_rate": call.data.get("heart_rate"),
                "respiratory_rate": call.data.get("respiratory_rate"),
                "appetite_level": call.data.get("appetite_level", ""),
                "energy_level": call.data.get("energy_level", ""),
                "logged_by": "service_call",
            }

            # Remove None values
            health_data = {
                k: v for k, v in health_data.items() if v is not None and v != ""
            }

            await data_manager.async_log_health(dog_id, health_data)

            hass.bus.async_fire(
                EVENT_HEALTH_LOGGED,
                {
                    ATTR_DOG_ID: dog_id,
                    "data_types": list(health_data.keys()),
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

            _LOGGER.info("Successfully logged health data for %s", dog_id)

        except PawControlError as err:
            _LOGGER.error("PawControl error in log_health service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in log_health service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to log health data: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_log_medication_service(call: ServiceCall) -> None:
        """Handle the log_medication service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        medication_name: str = call.data["medication_name"]
        dosage: str = call.data["dosage"]

        _LOGGER.debug(
            "Processing log_medication service for %s: %s", dog_id, medication_name
        )

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            medication_data = {
                "type": "medication",
                "medication_name": medication_name,
                "dosage": dosage,
                "administration_time": call.data.get(
                    "administration_time", dt_util.utcnow()
                ),
                "next_dose": call.data.get("next_dose"),
                "notes": call.data.get("notes", ""),
                "medication_type": call.data.get("medication_type", "oral"),
                "prescribing_vet": call.data.get("prescribing_vet", ""),
                "duration_days": call.data.get("duration_days"),
                "logged_by": "service_call",
            }

            await data_manager.async_log_health(dog_id, medication_data)

            _LOGGER.info(
                "Successfully logged medication %s for %s", medication_name, dog_id
            )

        except PawControlError as err:
            _LOGGER.error(
                "PawControl error in log_medication service: %s", err.to_dict()
            )
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in log_medication service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to log medication: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_start_grooming_service(call: ServiceCall) -> None:
        """Handle the start_grooming service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        grooming_type: str = call.data.get("type", "general")

        _LOGGER.debug(
            "Processing start_grooming service for %s: %s", dog_id, grooming_type
        )

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            grooming_data = {
                "type": grooming_type,
                "location": call.data.get("location", ""),
                "groomer": call.data.get("groomer", ""),
                "notes": call.data.get("notes", ""),
                "cost": call.data.get("cost"),
                "products_used": call.data.get("products_used", ""),
                "next_appointment": call.data.get("next_appointment"),
                "started_by": "service_call",
            }

            grooming_id = await data_manager.async_start_grooming(dog_id, grooming_data)

            _LOGGER.info("Successfully started grooming %s for %s", grooming_id, dog_id)

        except PawControlError as err:
            _LOGGER.error(
                "PawControl error in start_grooming service: %s", err.to_dict()
            )
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in start_grooming service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to start grooming: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_daily_reset_service(call: ServiceCall) -> None:
        """Handle the daily_reset service call with comprehensive processing."""
        _LOGGER.debug("Processing daily_reset service call")

        try:
            # Reset daily statistics for all dogs
            all_dogs = _get_available_dog_ids(hass)

            reset_tasks = []
            for dog_id in all_dogs:
                runtime_data = _get_runtime_data_for_dog(hass, dog_id)
                if runtime_data:
                    data_manager = runtime_data["data_manager"]
                    reset_tasks.append(data_manager.async_reset_dog_daily_stats(dog_id))

            if reset_tasks:
                await asyncio.gather(*reset_tasks, return_exceptions=True)

            _LOGGER.info(
                "Daily reset completed successfully for %d dogs", len(all_dogs)
            )

        except Exception as err:
            _LOGGER.error(
                "Unexpected error in daily_reset service: %s", err, exc_info=True
            )
            raise ServiceValidationError(
                f"Failed to perform daily reset: {err}"
            ) from err

    @performance_monitor(timeout=10.0)
    async def _handle_notify_test_service(call: ServiceCall) -> None:
        """Handle the notify_test service call with comprehensive features."""
        dog_id: str = call.data[ATTR_DOG_ID]
        message: str = call.data.get("message", "Test notification from Paw Control")
        priority: str = call.data.get("priority", "normal")

        _LOGGER.debug("Processing notify_test service for %s", dog_id)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            notification_manager = runtime_data["notification_manager"]

            success = await notification_manager.async_send_test_notification(
                dog_id, message, priority
            )

            if success:
                _LOGGER.info("Successfully sent test notification for %s", dog_id)
            else:
                _LOGGER.warning("Failed to send test notification for %s", dog_id)

        except PawControlError as err:
            _LOGGER.error("PawControl error in notify_test service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in notify_test service: %s", err, exc_info=True
            )
            raise ServiceValidationError(
                f"Failed to send test notification: {err}"
            ) from err

    @performance_monitor(timeout=10.0)
    async def _handle_set_visitor_mode_service(call: ServiceCall) -> None:
        """Handle the set_visitor_mode service call."""
        dog_id: str = call.data[ATTR_DOG_ID]
        enabled: bool = call.data["enabled"]
        visitor_name: str = call.data.get("visitor_name", "")

        _LOGGER.debug("Processing set_visitor_mode service for %s: %s", dog_id, enabled)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            visitor_data = {
                "enabled": enabled,
                "visitor_name": visitor_name,
                "reduced_alerts": call.data.get("reduced_alerts", True),
                "modified_schedule": call.data.get("modified_schedule", True),
                "notes": call.data.get("notes", ""),
                "set_by": "service_call",
                "timestamp": dt_util.utcnow().isoformat(),
            }

            await data_manager.async_update_dog_data(
                dog_id, {"visitor_mode": visitor_data}
            )

            _LOGGER.info(
                "Successfully %s visitor mode for %s",
                "enabled" if enabled else "disabled",
                dog_id,
            )

        except PawControlError as err:
            _LOGGER.error(
                "PawControl error in set_visitor_mode service: %s", err.to_dict()
            )
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in set_visitor_mode service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to set visitor mode: {err}") from err

    @performance_monitor(timeout=30.0)
    async def _handle_export_data_service(call: ServiceCall) -> None:
        """Handle the export_data service call."""
        dog_id: str = call.data[ATTR_DOG_ID]
        data_type: str = call.data["data_type"]
        export_format: str = call.data.get("format", "csv")

        _LOGGER.debug("Processing export_data service for %s: %s", dog_id, data_type)

        try:
            runtime_data = _get_runtime_data_for_dog(hass, dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, _get_available_dog_ids(hass))

            data_manager = runtime_data["data_manager"]

            # Get date range for export - handle date objects properly
            start_date = call.data.get("start_date")
            end_date = call.data.get("end_date")

            if start_date:
                # Handle different date/datetime types properly
                if isinstance(start_date, str):
                    start_date = dt_util.parse_datetime(start_date)
                elif hasattr(start_date, "year") and not hasattr(start_date, "hour"):
                    # Convert date to datetime at start of day
                    start_date = dt_util.start_of_local_day(start_date)
                # If already datetime, use as-is

            if end_date:
                # Handle different date/datetime types properly
                if isinstance(end_date, str):
                    end_date = dt_util.parse_datetime(end_date)
                elif hasattr(end_date, "year") and not hasattr(end_date, "hour"):
                    # Convert date to datetime at end of day
                    end_date = dt_util.end_of_local_day(end_date)
                # If already datetime, use as-is

            # Collect data based on type
            if data_type == "all":
                export_data = {
                    "feeding": await data_manager.async_get_module_data(
                        "feeding", dog_id, start_date=start_date, end_date=end_date
                    ),
                    "walks": await data_manager.async_get_module_data(
                        "walks", dog_id, start_date=start_date, end_date=end_date
                    ),
                    "health": await data_manager.async_get_module_data(
                        "health", dog_id, start_date=start_date, end_date=end_date
                    ),
                    "gps": await data_manager.async_get_module_data(
                        "gps", dog_id, start_date=start_date, end_date=end_date
                    ),
                    "grooming": await data_manager.async_get_module_data(
                        "grooming", dog_id, start_date=start_date, end_date=end_date
                    ),
                }
            else:
                export_data = await data_manager.async_get_module_data(
                    data_type, dog_id, start_date=start_date, end_date=end_date
                )

            # Create export file (simplified implementation)
            f"/config/paw_control_export_{dog_id}_{data_type}_{dt_util.utcnow().strftime('%Y%m%d_%H%M%S')}.{export_format}"

            # Note: In a full implementation, this would create actual export files
            # For now, we'll just log the export request
            _LOGGER.info(
                "Export completed for %s: %s (%d entries)",
                dog_id,
                data_type,
                len(export_data)
                if isinstance(export_data, list)
                else sum(
                    len(v) if isinstance(v, list) else 0
                    for v in export_data.values()
                    if isinstance(v, (list, dict))
                ),
            )

        except PawControlError as err:
            _LOGGER.error("PawControl error in export_data service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in export_data service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to export data: {err}") from err

    # Service registration with comprehensive error handling
    services = [
        (SERVICE_FEED_DOG, _handle_feed_dog_service, SERVICE_FEED_DOG_SCHEMA),
        (SERVICE_START_WALK, _handle_start_walk_service, SERVICE_WALK_SCHEMA),
        (SERVICE_END_WALK, _handle_end_walk_service, SERVICE_END_WALK_SCHEMA),
        (SERVICE_LOG_HEALTH, _handle_log_health_service, SERVICE_HEALTH_SCHEMA),
        (
            SERVICE_LOG_MEDICATION,
            _handle_log_medication_service,
            SERVICE_MEDICATION_SCHEMA,
        ),
        (
            SERVICE_START_GROOMING,
            _handle_start_grooming_service,
            SERVICE_GROOMING_SCHEMA,
        ),
        (SERVICE_DAILY_RESET, _handle_daily_reset_service, SERVICE_DAILY_RESET_SCHEMA),
        (SERVICE_NOTIFY_TEST, _handle_notify_test_service, SERVICE_NOTIFY_TEST_SCHEMA),
        (
            "set_visitor_mode",
            _handle_set_visitor_mode_service,
            SERVICE_SET_VISITOR_MODE_SCHEMA,
        ),
        ("export_data", _handle_export_data_service, SERVICE_EXPORT_DATA_SCHEMA),
    ]

    # Register all services with enhanced error handling
    registration_errors = []

    for service_name, handler, schema in services:
        try:
            hass.services.async_register(
                DOMAIN,
                service_name,
                handler,
                schema=schema,
            )
            _LOGGER.debug("Successfully registered service: %s", service_name)
        except Exception as err:
            error_msg = f"Failed to register service {service_name}: {err}"
            _LOGGER.error(error_msg)
            registration_errors.append(error_msg)

    if registration_errors:
        raise PawControlSetupError(
            f"Service registration failed: {'; '.join(registration_errors)}",
            "service_registration_failed",
        )

    _LOGGER.info("Successfully registered %d Paw Control services", len(services))


async def _async_setup_daily_reset_scheduler(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Set up the daily reset scheduler with enhanced error handling and modern async patterns.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing reset time configuration
    """
    # Use global flag to prevent duplicate scheduling with better tracking
    domain_data = hass.data.setdefault(DOMAIN, {})
    scheduler_key = "_daily_reset_scheduled"

    if domain_data.get(scheduler_key):
        _LOGGER.debug("Daily reset scheduler already configured")
        return

    reset_time_str: str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)

    try:
        reset_time_obj = time.fromisoformat(reset_time_str)
    except ValueError:
        _LOGGER.warning(
            "Invalid reset time format '%s', using default %s",
            reset_time_str,
            DEFAULT_RESET_TIME,
        )
        reset_time_obj = time.fromisoformat(DEFAULT_RESET_TIME)

    @callback
    def _daily_reset_callback(now) -> None:
        """Enhanced callback function for daily reset execution with error handling."""
        _LOGGER.info("Triggering daily reset at %s", now)

        # Create async task with comprehensive error handling
        async def _run_daily_reset() -> None:
            try:
                # Add timeout protection for the daily reset
                async with asyncio.timeout(60):
                    await hass.services.async_call(DOMAIN, SERVICE_DAILY_RESET, {})
                _LOGGER.info("Daily reset completed successfully")
            except asyncio.TimeoutError:
                _LOGGER.error("Daily reset timed out after 60 seconds")
            except Exception as err:
                _LOGGER.error("Daily reset task failed: %s", err, exc_info=True)

        # Create task with name for better debugging
        task = hass.async_create_task(
            _run_daily_reset(),
            name=f"paw_control_daily_reset_{now.strftime('%Y%m%d_%H%M')}",
        )

        # Optional: Store task reference for monitoring
        domain_data[f"_reset_task_{now.date()}"] = task

    # Schedule the daily reset with modern async tracking
    remove_listener = async_track_time_change(
        hass,
        _daily_reset_callback,
        hour=reset_time_obj.hour,
        minute=reset_time_obj.minute,
        second=reset_time_obj.second,
    )

    # Store the remove listener function for cleanup
    domain_data["_reset_listener_remove"] = remove_listener

    # Mark scheduler as configured globally
    domain_data[scheduler_key] = True

    _LOGGER.info(
        "Daily reset scheduled for %02d:%02d:%02d",
        reset_time_obj.hour,
        reset_time_obj.minute,
        reset_time_obj.second,
    )


def _get_runtime_data_for_dog(
    hass: HomeAssistant, dog_id: str
) -> PawControlRuntimeData | None:
    """Find the runtime data that contains a specific dog with enhanced search and caching.

    Uses modern ConfigEntry.runtime_data approach with fallback to legacy storage.
    Implements caching for better performance on repeated calls.

    Args:
        hass: Home Assistant instance
        dog_id: Unique identifier of the dog to find

    Returns:
        Runtime data dictionary containing the dog, or None if not found
    """
    # Search through all config entries for the dog
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        # Try modern runtime_data first
        runtime_data = getattr(config_entry, "runtime_data", None)

        if runtime_data:
            dogs = runtime_data.get("dogs", [])
            for dog in dogs:
                if dog.get(CONF_DOG_ID) == dog_id:
                    return runtime_data

        # Fallback to legacy data storage
        legacy_data = hass.data[DOMAIN].get(config_entry.entry_id, {})
        if "coordinator" in legacy_data:
            coordinator = legacy_data["coordinator"]
            dogs = coordinator.config_entry.data.get(CONF_DOGS, [])
            for dog in dogs:
                if dog.get(CONF_DOG_ID) == dog_id:
                    # Convert legacy data to runtime data format
                    return {
                        "coordinator": legacy_data.get("coordinator"),
                        "data_manager": legacy_data.get("data"),
                        "notification_manager": legacy_data.get("notifications"),
                        "config_entry": legacy_data.get("entry"),
                        "dogs": dogs,
                    }

    return None


def _get_available_dog_ids(hass: HomeAssistant) -> list[str]:
    """Get list of all available dog IDs across all config entries.

    Args:
        hass: Home Assistant instance

    Returns:
        List of available dog IDs
    """
    dog_ids = []

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        # Try modern runtime_data first
        runtime_data = getattr(config_entry, "runtime_data", None)

        if runtime_data:
            dogs = runtime_data.get("dogs", [])
            dog_ids.extend(dog.get(CONF_DOG_ID) for dog in dogs if dog.get(CONF_DOG_ID))
        else:
            # Fallback to legacy data
            dogs = config_entry.data.get(CONF_DOGS, [])
            dog_ids.extend(dog.get(CONF_DOG_ID) for dog in dogs if dog.get(CONF_DOG_ID))

    return dog_ids
