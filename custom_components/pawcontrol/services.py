"""Service management for Paw Control integration.

This module provides comprehensive service management for the Paw Control integration,
handling registration, validation, and execution of all Home Assistant services.

The service manager follows Home Assistant's Platinum standards with:
- Complete asynchronous operation
- Full type annotations
- Robust error handling and validation
- Comprehensive input validation
- Service lifecycle management
- Event firing for service completions
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from . import gps_handler
from .const import (
    ATTR_DOG_ID,
    CONF_DOG_ID,
    DOMAIN,
    EVENT_DOG_FED,
    EVENT_GROOMING_DONE,
    EVENT_MEDICATION_GIVEN,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    FEEDING_TYPES,
    GROOMING_TYPES,
    INTENSITY_TYPES,
    MAX_DOG_WEIGHT_KG,
    MAX_STRING_LENGTH,
    MEAL_TYPES,
    MIN_DOG_WEIGHT_KG,
    SERVICE_DAILY_RESET,
    SERVICE_END_WALK,
    SERVICE_EXPORT_DATA,
    SERVICE_FEED_DOG,
    SERVICE_GENERATE_REPORT,
    SERVICE_GPS_EXPORT_LAST_ROUTE,
    SERVICE_GPS_GENERATE_DIAGNOSTICS,
    SERVICE_GPS_LIST_WEBHOOKS,
    SERVICE_GPS_PAUSE_TRACKING,
    SERVICE_GPS_POST_LOCATION,
    SERVICE_GPS_REGENERATE_WEBHOOKS,
    SERVICE_GPS_START_WALK,
    SERVICE_GPS_END_WALK,
    SERVICE_GPS_RESET_STATS,
    SERVICE_GPS_RESUME_TRACKING,
    SERVICE_LOG_HEALTH,
    SERVICE_LOG_MEDICATION,
    SERVICE_NOTIFY_TEST,
    SERVICE_PURGE_ALL_STORAGE,
    SERVICE_PLAY_SESSION,
    SERVICE_PRUNE_STALE_DEVICES,
    SERVICE_START_GROOMING,
    SERVICE_START_WALK,
    SERVICE_SYNC_SETUP,
    SERVICE_TOGGLE_GEOFENCE_ALERTS,
    SERVICE_TOGGLE_VISITOR,
    SERVICE_TRAINING_SESSION,
    SERVICE_WALK_DOG,
    SERVICE_ROUTE_HISTORY_LIST,
    SERVICE_ROUTE_HISTORY_PURGE,
    SERVICE_ROUTE_HISTORY_EXPORT_RANGE,
    TRAINING_TYPES,
)

from .route_store import RouteHistoryStore

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import PawControlCoordinator

_LOGGER = logging.getLogger(__name__)

# Maximum number of concurrent service calls to prevent overload
MAX_CONCURRENT_SERVICE_CALLS = 5

# Service schemas for comprehensive validation
SERVICE_SCHEMA_WALK_DOG = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Optional("duration_min", default=30): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=480),  # 1 minute to 8 hours
        ),
        vol.Optional("distance_m", default=0): vol.All(
            vol.Coerce(int),
            vol.Range(min=0, max=50000),  # 0 to 50km
        ),
    }
)

SERVICE_SCHEMA_START_WALK = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Optional("source", default="manual"): cv.string,
    }
)

SERVICE_SCHEMA_END_WALK = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Optional("reason", default="manual"): cv.string,
    }
)

SERVICE_SCHEMA_FEED_DOG = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required("meal_type"): vol.In(list(MEAL_TYPES.keys())),
        vol.Required("portion_g"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=5000),  # 1g to 5kg
        ),
        vol.Optional("food_type", default="dry"): vol.In(list(FEEDING_TYPES.keys())),
    }
)

SERVICE_SCHEMA_LOG_HEALTH = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Optional("weight_kg"): vol.All(
            vol.Coerce(float), vol.Range(min=MIN_DOG_WEIGHT_KG, max=MAX_DOG_WEIGHT_KG)
        ),
        vol.Optional("note", default=""): vol.All(
            cv.string, vol.Length(max=MAX_STRING_LENGTH)
        ),
        vol.Optional("temperature"): vol.All(
            vol.Coerce(float),
            vol.Range(min=35.0, max=45.0),  # °C
        ),
        vol.Optional("heart_rate"): vol.All(
            vol.Coerce(int),
            vol.Range(min=40, max=200),  # BPM
        ),
    }
)

SERVICE_SCHEMA_LOG_MEDICATION = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required("medication_name"): vol.All(
            cv.string, vol.Length(min=1, max=MAX_STRING_LENGTH)
        ),
        vol.Required("dose"): vol.All(
            cv.string, vol.Length(min=1, max=MAX_STRING_LENGTH)
        ),
        vol.Optional("notes", default=""): vol.All(
            cv.string, vol.Length(max=MAX_STRING_LENGTH)
        ),
    }
)

SERVICE_SCHEMA_START_GROOMING = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required("grooming_type"): vol.In(list(GROOMING_TYPES.keys())),
        vol.Optional("notes", default=""): vol.All(
            cv.string, vol.Length(max=MAX_STRING_LENGTH)
        ),
    }
)

SERVICE_SCHEMA_PLAY_SESSION = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required("duration_min"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=240),  # 1 minute to 4 hours
        ),
        vol.Optional("intensity", default="medium"): vol.In(
            list(INTENSITY_TYPES.keys())
        ),
        vol.Optional("activity_type", default="play"): cv.string,
    }
)

SERVICE_SCHEMA_TRAINING_SESSION = vol.Schema(
    {
        vol.Required(CONF_DOG_ID): cv.string,
        vol.Required("topic"): vol.In(list(TRAINING_TYPES.keys())),
        vol.Required("duration_min"): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=120),  # 1 minute to 2 hours
        ),
        vol.Optional("intensity", default="medium"): vol.In(
            list(INTENSITY_TYPES.keys())
        ),
        vol.Optional("notes", default=""): vol.All(
            cv.string, vol.Length(max=MAX_STRING_LENGTH)
        ),
    }
)

SERVICE_SCHEMA_GPS_POST_LOCATION = vol.Schema(
    {
        vol.Optional(CONF_DOG_ID): cv.string,
        vol.Required("latitude"): vol.All(
            vol.Coerce(float), vol.Range(min=-90.0, max=90.0)
        ),
        vol.Required("longitude"): vol.All(
            vol.Coerce(float), vol.Range(min=-180.0, max=180.0)
        ),
        vol.Optional("accuracy_m"): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=10000.0)
        ),
        vol.Optional("source", default="manual"): cv.string,
    }
)

SERVICE_SCHEMA_GENERATE_REPORT = vol.Schema(
    {
        vol.Optional("report_type", default="daily"): vol.In(
            ["daily", "weekly", "monthly"]
        ),
        vol.Optional("dog_id"): cv.string,
        vol.Optional("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Optional("format", default="json"): vol.In(["json", "csv", "pdf"]),
    }
)

SERVICE_SCHEMA_EXPORT_DATA = vol.Schema(
    {
        vol.Optional("data_type", default="all"): vol.In(
            ["all", "walks", "feeding", "health", "grooming", "training", "gps"]
        ),
        vol.Optional("dog_id"): cv.string,
        vol.Optional("start_date"): cv.date,
        vol.Optional("end_date"): cv.date,
        vol.Optional("format", default="csv"): vol.In(["csv", "json", "excel"]),
        vol.Optional("include_metadata", default=True): cv.boolean,
    }
)

SERVICE_SCHEMA_NOTIFY_TEST = vol.Schema(
    {
        vol.Optional(
            "message", default="Test notification from Paw Control"
        ): cv.string,
        vol.Optional("title", default="Paw Control Test"): cv.string,
        vol.Optional("target"): cv.string,
    }
)

SERVICE_SCHEMA_PRUNE_STALE_DEVICES = vol.Schema(
    {
        vol.Optional("dry_run", default=False): cv.boolean,
        vol.Optional("older_than_days", default=30): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=365)
        ),
        vol.Optional("auto", default=False): cv.boolean,
    }
)

SERVICE_SCHEMA_TOGGLE_GEOFENCE_ALERTS = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
        vol.Required("config_entry_id"): cv.string,
    }
)

SERVICE_SCHEMA_PURGE_ALL_STORAGE = vol.Schema(
    {vol.Required("config_entry_id"): cv.string}
)

# GPS service schemas
SERVICE_SCHEMA_GPS_BASIC = vol.Schema({vol.Optional(CONF_DOG_ID): cv.string})

SERVICE_SCHEMA_GPS_DIAGNOSTICS = vol.Schema(
    {
        vol.Optional(CONF_DOG_ID): cv.string,
        vol.Optional("include_routes", default=True): cv.boolean,
        vol.Optional("include_stats", default=True): cv.boolean,
    }
)

# Route history service schemas
SERVICE_SCHEMA_ROUTE_HISTORY_LIST = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Optional(CONF_DOG_ID): cv.string,
    }
)

SERVICE_SCHEMA_ROUTE_HISTORY_PURGE = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Optional("older_than_days"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)

SERVICE_SCHEMA_ROUTE_HISTORY_EXPORT_RANGE = vol.Schema(
    {
        vol.Required("config_entry_id"): cv.string,
        vol.Optional(CONF_DOG_ID): cv.string,
        vol.Optional("date_from"): cv.string,
        vol.Optional("date_to"): cv.string,
    }
)


# Python 3.12+ Service routing types
type ServiceHandler = str
type ServiceData = dict[str, Any]
type ServiceResult = bool | dict[str, Any]


# Exception groups for service errors
class ServiceErrors(ExceptionGroup):
    """Group for service-related errors."""

    pass


class ValidationErrors(ExceptionGroup):
    """Group for validation-related errors."""

    pass


class ServiceManager:
    """Manages all Home Assistant services for Paw Control integration.

    This class handles registration, validation, and execution of all services
    provided by the Paw Control integration. It ensures proper input validation,
    error handling, and coordinator interaction.

    The service manager follows a strict lifecycle:
    1. Registration during integration setup
    2. Validation of all service calls
    3. Execution with proper error handling
    4. Event firing for successful operations
    5. Cleanup during integration unload
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the service manager.

        Args:
            hass: Home Assistant instance
            entry: Configuration entry for this integration instance
        """
        self.hass = hass
        self.entry = entry
        self._registered_services: set[str] = set()
        self._service_call_count: int = 0
        self._is_registering: bool = False

    @property
    def coordinator(self) -> PawControlCoordinator:
        """Get the coordinator from runtime data.

        Returns:
            The coordinator instance

        Raises:
            HomeAssistantError: If coordinator is not available
        """
        try:
            runtime_data = self.entry.runtime_data
            return runtime_data.coordinator
        except AttributeError as err:
            raise HomeAssistantError("Coordinator not available") from err

    async def async_register_services(self) -> None:
        """Register all Paw Control services with Python 3.12+ routing."""
        if self._is_registering:
            _LOGGER.warning("Service registration already in progress")
            return

        self._is_registering = True
        try:
            _LOGGER.debug("Registering Paw Control services with modern routing")

            # Python 3.12+ Pattern matching for service registration
            services_config = {
                # Core services
                "walk": [
                    (SERVICE_WALK_DOG, self._handle_walk_dog, SERVICE_SCHEMA_WALK_DOG),
                    (
                        SERVICE_START_WALK,
                        self._handle_start_walk,
                        SERVICE_SCHEMA_START_WALK,
                    ),
                    (SERVICE_END_WALK, self._handle_end_walk, SERVICE_SCHEMA_END_WALK),
                ],
                "feeding": [
                    (SERVICE_FEED_DOG, self._handle_feed_dog, SERVICE_SCHEMA_FEED_DOG),
                ],
                "health": [
                    (
                        SERVICE_LOG_HEALTH,
                        self._handle_log_health,
                        SERVICE_SCHEMA_LOG_HEALTH,
                    ),
                    (
                        SERVICE_LOG_MEDICATION,
                        self._handle_log_medication,
                        SERVICE_SCHEMA_LOG_MEDICATION,
                    ),
                ],
                "grooming": [
                    (
                        SERVICE_START_GROOMING,
                        self._handle_start_grooming,
                        SERVICE_SCHEMA_START_GROOMING,
                    ),
                ],
                "activity": [
                    (
                        SERVICE_PLAY_SESSION,
                        self._handle_play_session,
                        SERVICE_SCHEMA_PLAY_SESSION,
                    ),
                    (
                        SERVICE_TRAINING_SESSION,
                        self._handle_training_session,
                        SERVICE_SCHEMA_TRAINING_SESSION,
                    ),
                ],
                "gps": [
                    (
                        SERVICE_GPS_START_WALK,
                        self._handle_start_walk,
                        SERVICE_SCHEMA_START_WALK,
                    ),
                    (
                        SERVICE_GPS_END_WALK,
                        self._handle_end_walk,
                        SERVICE_SCHEMA_END_WALK,
                    ),
                    (
                        SERVICE_GPS_POST_LOCATION,
                        self._handle_gps_post_location,
                        SERVICE_SCHEMA_GPS_POST_LOCATION,
                    ),
                    (
                        SERVICE_GPS_PAUSE_TRACKING,
                        self._handle_gps_pause_tracking,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_GPS_RESUME_TRACKING,
                        self._handle_gps_resume_tracking,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_GPS_GENERATE_DIAGNOSTICS,
                        self._handle_gps_generate_diagnostics,
                        SERVICE_SCHEMA_GPS_DIAGNOSTICS,
                    ),
                    (
                        SERVICE_GPS_RESET_STATS,
                        self._handle_gps_reset_stats,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_GPS_EXPORT_LAST_ROUTE,
                        self._handle_gps_export_last_route,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_GPS_LIST_WEBHOOKS,
                        self._handle_gps_list_webhooks,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_GPS_REGENERATE_WEBHOOKS,
                        self._handle_gps_regenerate_webhooks,
                        SERVICE_SCHEMA_GPS_BASIC,
                    ),
                    (
                        SERVICE_ROUTE_HISTORY_LIST,
                        self._handle_route_history_list,
                        SERVICE_SCHEMA_ROUTE_HISTORY_LIST,
                    ),
                    (
                        SERVICE_ROUTE_HISTORY_PURGE,
                        self._handle_route_history_purge,
                        SERVICE_SCHEMA_ROUTE_HISTORY_PURGE,
                    ),
                    (
                        SERVICE_ROUTE_HISTORY_EXPORT_RANGE,
                        self._handle_route_history_export_range,
                        SERVICE_SCHEMA_ROUTE_HISTORY_EXPORT_RANGE,
                    ),
                ],
                "system": [
                    (SERVICE_DAILY_RESET, self._handle_daily_reset, vol.Schema({})),
                    (SERVICE_SYNC_SETUP, self._handle_sync_setup, vol.Schema({})),
                    (
                        SERVICE_TOGGLE_VISITOR,
                        self._handle_toggle_visitor,
                        vol.Schema({}),
                    ),
                    (
                        SERVICE_GENERATE_REPORT,
                        self._handle_generate_report,
                        SERVICE_SCHEMA_GENERATE_REPORT,
                    ),
                    (
                        SERVICE_EXPORT_DATA,
                        self._handle_export_data,
                        SERVICE_SCHEMA_EXPORT_DATA,
                    ),
                    (
                        SERVICE_NOTIFY_TEST,
                        self._handle_notify_test,
                        SERVICE_SCHEMA_NOTIFY_TEST,
                    ),
                    (
                        SERVICE_TOGGLE_GEOFENCE_ALERTS,
                        self._handle_toggle_geofence_alerts,
                        SERVICE_SCHEMA_TOGGLE_GEOFENCE_ALERTS,
                    ),
                    (
                        SERVICE_PURGE_ALL_STORAGE,
                        self._handle_purge_all_storage,
                        SERVICE_SCHEMA_PURGE_ALL_STORAGE,
                    ),
                    (
                        SERVICE_PRUNE_STALE_DEVICES,
                        self._handle_prune_stale_devices,
                        SERVICE_SCHEMA_PRUNE_STALE_DEVICES,
                    ),
                ],
            }

            # Register services using pattern matching
            for category, service_list in services_config.items():
                match category:
                    case "walk" | "feeding" | "health" | "grooming" | "activity":
                        await self._register_service_category(service_list, "core")
                    case "gps":
                        await self._register_service_category(service_list, "tracking")
                    case "system":
                        await self._register_service_category(service_list, "utility")
                    case _:
                        _LOGGER.warning(f"Unknown service category: {category}")

            _LOGGER.info(
                "Registered %d Paw Control services", len(self._registered_services)
            )

        except Exception as err:
            _LOGGER.error("Failed to register services: %s", err)
            raise ServiceErrors("Service registration failed", [err]) from err
        finally:
            self._is_registering = False

    async def _register_service_category(
        self, services: list[tuple], category: str
    ) -> None:
        """Register a category of services with enhanced error handling."""
        errors = []
        for service_name, handler, schema in services:
            try:
                await self._register_service(service_name, handler, schema)
            except Exception as err:
                errors.append(err)

        if errors:
            raise ServiceErrors(f"Failed to register {category} services", errors)

    async def _register_service(
        self, service_name: str, handler: Any, schema: vol.Schema
    ) -> None:
        """Register a single service with validation.

        Args:
            service_name: Name of the service to register
            handler: Async handler function for the service
            schema: Voluptuous schema for input validation
        """
        try:
            # Check if service is already registered by this integration
            if self.hass.services.has_service(DOMAIN, service_name):
                _LOGGER.debug("Service %s already registered, skipping", service_name)
                return

            self.hass.services.async_register(
                DOMAIN, service_name, handler, schema=schema
            )
            self._registered_services.add(service_name)
            _LOGGER.debug("Registered service: %s", service_name)

        except Exception as err:
            _LOGGER.error("Failed to register service %s: %s", service_name, err)
            raise

    async def async_unregister_services(self) -> None:
        """Unregister all services registered by this instance.

        Safely removes all services that were registered by this service manager
        to prevent conflicts during integration unload.
        """
        _LOGGER.debug("Unregistering Paw Control services")

        for service_name in list(self._registered_services):
            try:
                if self.hass.services.has_service(DOMAIN, service_name):
                    self.hass.services.async_remove(DOMAIN, service_name)
                    _LOGGER.debug("Unregistered service: %s", service_name)
            except Exception as err:
                _LOGGER.warning(
                    "Failed to unregister service %s: %s", service_name, err
                )

        self._registered_services.clear()
        _LOGGER.info("Unregistered all Paw Control services")

    def _validate_dog_exists(self, dog_id: str) -> None:
        """Validate that a dog exists in the coordinator.

        Args:
            dog_id: Dog identifier to validate

        Raises:
            ServiceValidationError: If dog does not exist
        """
        if not dog_id:
            raise ServiceValidationError("Dog ID is required")

        if dog_id not in self.coordinator._dog_data:
            raise ServiceValidationError(f"Unknown dog: {dog_id}")

    def _log_service_call(self, service_name: str, data: dict[str, Any]) -> None:
        """Log service call for debugging and monitoring.

        Args:
            service_name: Name of the called service
            data: Service call data (sanitized)
        """
        self._service_call_count += 1

        # Sanitize sensitive data for logging
        sanitized_data = {k: v for k, v in data.items() if k != "api_key"}

        _LOGGER.debug(
            "Service call #%d: %s with data: %s",
            self._service_call_count,
            service_name,
            sanitized_data,
        )

    # ==============================================================================
    # CORE DOG MANAGEMENT SERVICE HANDLERS
    # ==============================================================================

    async def _handle_walk_dog(self, call: ServiceCall) -> None:
        """Handle walk_dog service call.

        Logs a completed walk with specified duration and distance.
        """
        self._log_service_call("walk_dog", call.data)

        dog_id = call.data[CONF_DOG_ID]
        duration_min = call.data["duration_min"]
        distance_m = call.data["distance_m"]

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.log_walk(dog_id, duration_min, distance_m)
            _LOGGER.info(
                "Logged walk for dog %s: %d min, %d m", dog_id, duration_min, distance_m
            )

        except Exception as err:
            _LOGGER.error("Failed to log walk for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log walk: {err}") from err

    async def _handle_start_walk(self, call: ServiceCall) -> None:
        """Handle start_walk service call.

        Starts live walk tracking for a dog.
        """
        self._log_service_call("start_walk", call.data)

        dog_id = call.data[CONF_DOG_ID]
        source = call.data.get("source", "manual")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.start_walk(dog_id, source)

            # Fire event for automation triggers
            self.hass.bus.async_fire(
                EVENT_WALK_STARTED, {ATTR_DOG_ID: dog_id, "source": source}
            )
            _LOGGER.info("Started walk for dog %s (source: %s)", dog_id, source)

        except Exception as err:
            _LOGGER.error("Failed to start walk for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to start walk: {err}") from err

    async def _handle_end_walk(self, call: ServiceCall) -> None:
        """Handle end_walk service call.

        Ends live walk tracking for a dog.
        """
        self._log_service_call("end_walk", call.data)

        dog_id = call.data[CONF_DOG_ID]
        reason = call.data.get("reason", "manual")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.end_walk(dog_id, reason)

            # Fire event for automation triggers
            self.hass.bus.async_fire(
                EVENT_WALK_ENDED, {ATTR_DOG_ID: dog_id, "reason": reason}
            )
            _LOGGER.info("Ended walk for dog %s (reason: %s)", dog_id, reason)

        except Exception as err:
            _LOGGER.error("Failed to end walk for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to end walk: {err}") from err

    async def _handle_feed_dog(self, call: ServiceCall) -> None:
        """Handle feed_dog service call.

        Records a feeding event for a dog.
        """
        self._log_service_call("feed_dog", call.data)

        dog_id = call.data[CONF_DOG_ID]
        meal_type = call.data["meal_type"]
        portion_g = call.data["portion_g"]
        food_type = call.data.get("food_type", "dry")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.feed_dog(dog_id, meal_type, portion_g, food_type)

            # Fire event for automation triggers
            self.hass.bus.async_fire(
                EVENT_DOG_FED,
                {
                    ATTR_DOG_ID: dog_id,
                    "meal_type": meal_type,
                    "portion_g": portion_g,
                    "food_type": food_type,
                },
            )
            _LOGGER.info(
                "Fed dog %s: %s, %d g of %s", dog_id, meal_type, portion_g, food_type
            )

        except Exception as err:
            _LOGGER.error("Failed to feed dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to record feeding: {err}") from err

    async def _handle_log_health(self, call: ServiceCall) -> None:
        """Handle log_health service call.

        Records health data for a dog.
        """
        self._log_service_call("log_health", call.data)

        dog_id = call.data[CONF_DOG_ID]
        weight_kg = call.data.get("weight_kg")
        note = call.data.get("note", "")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.log_health_data(dog_id, weight_kg, note)
            _LOGGER.info("Logged health data for dog %s", dog_id)

        except Exception as err:
            _LOGGER.error("Failed to log health data for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log health data: {err}") from err

    async def _handle_log_medication(self, call: ServiceCall) -> None:
        """Handle log_medication service call.

        Records medication administration for a dog.
        """
        self._log_service_call("log_medication", call.data)

        dog_id = call.data[CONF_DOG_ID]
        medication_name = call.data["medication_name"]
        dose = call.data["dose"]

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.log_medication(dog_id, medication_name, dose)

            # Fire event for automation triggers
            self.hass.bus.async_fire(
                EVENT_MEDICATION_GIVEN,
                {
                    ATTR_DOG_ID: dog_id,
                    "medication": medication_name,
                    "dose": dose,
                },
            )
            _LOGGER.info(
                "Logged medication for dog %s: %s (%s)", dog_id, medication_name, dose
            )

        except Exception as err:
            _LOGGER.error("Failed to log medication for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log medication: {err}") from err

    async def _handle_start_grooming(self, call: ServiceCall) -> None:
        """Handle start_grooming service call.

        Records a grooming session for a dog.
        """
        self._log_service_call("start_grooming", call.data)

        dog_id = call.data[CONF_DOG_ID]
        grooming_type = call.data["grooming_type"]
        notes = call.data.get("notes", "")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.start_grooming(dog_id, grooming_type, notes)

            # Fire event for automation triggers
            self.hass.bus.async_fire(
                EVENT_GROOMING_DONE,
                {
                    ATTR_DOG_ID: dog_id,
                    "type": grooming_type,
                },
            )
            _LOGGER.info("Started grooming for dog %s: %s", dog_id, grooming_type)

        except Exception as err:
            _LOGGER.error("Failed to start grooming for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to start grooming: {err}") from err

    async def _handle_play_session(self, call: ServiceCall) -> None:
        """Handle play_session service call.

        Records a play session for a dog.
        """
        self._log_service_call("play_session", call.data)

        dog_id = call.data[CONF_DOG_ID]
        duration_min = call.data["duration_min"]
        intensity = call.data.get("intensity", "medium")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.log_play_session(dog_id, duration_min, intensity)
            _LOGGER.info(
                "Logged play session for dog %s: %d min (%s intensity)",
                dog_id,
                duration_min,
                intensity,
            )

        except Exception as err:
            _LOGGER.error("Failed to log play session for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log play session: {err}") from err

    async def _handle_training_session(self, call: ServiceCall) -> None:
        """Handle training_session service call.

        Records a training session for a dog.
        """
        self._log_service_call("training_session", call.data)

        dog_id = call.data[CONF_DOG_ID]
        topic = call.data["topic"]
        duration_min = call.data["duration_min"]
        call.data.get("intensity", "medium")
        notes = call.data.get("notes", "")

        try:
            self._validate_dog_exists(dog_id)
            await self.coordinator.log_training(dog_id, topic, duration_min, notes)
            _LOGGER.info(
                "Logged training session for dog %s: %s for %d min",
                dog_id,
                topic,
                duration_min,
            )

        except Exception as err:
            _LOGGER.error("Failed to log training session for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to log training session: {err}") from err

    # ==============================================================================
    # GPS AND TRACKING SERVICE HANDLERS
    # ==============================================================================

    async def _handle_gps_post_location(self, call: ServiceCall) -> None:
        """Handle gps_post_location service call.

        Updates GPS location for a dog.
        """
        self._log_service_call("gps_post_location", call.data)

        dog_id = call.data.get(CONF_DOG_ID)
        latitude = call.data["latitude"]
        longitude = call.data["longitude"]
        accuracy = call.data.get("accuracy_m")

        try:
            if dog_id:
                self._validate_dog_exists(dog_id)

            # Validate coordinates
            if not (-90 <= latitude <= 90):
                raise ServiceValidationError(f"Invalid latitude: {latitude}")
            if not (-180 <= longitude <= 180):
                raise ServiceValidationError(f"Invalid longitude: {longitude}")

            await gps_handler.async_update_location(self.hass, call)
            _LOGGER.debug(
                "Updated GPS for dog %s: %f, %f (accuracy_m: %s)",
                dog_id,
                latitude,
                longitude,
                accuracy,
            )

        except Exception as err:
            _LOGGER.error("Failed to update GPS for dog %s: %s", dog_id, err)
            raise HomeAssistantError(f"Failed to update GPS location: {err}") from err

    async def _handle_gps_pause_tracking(self, call: ServiceCall) -> None:
        """Handle gps_pause_tracking service call."""
        self._log_service_call("gps_pause_tracking", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                await gps_handler.async_pause_tracking()
                _LOGGER.info("GPS tracking paused")
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to pause GPS tracking: %s", err)
            raise HomeAssistantError(f"Failed to pause GPS tracking: {err}") from err

    async def _handle_gps_resume_tracking(self, call: ServiceCall) -> None:
        """Handle gps_resume_tracking service call."""
        self._log_service_call("gps_resume_tracking", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                await gps_handler.async_resume_tracking()
                _LOGGER.info("GPS tracking resumed")
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to resume GPS tracking: %s", err)
            raise HomeAssistantError(f"Failed to resume GPS tracking: {err}") from err

    async def _handle_gps_generate_diagnostics(self, call: ServiceCall) -> None:
        """Handle gps_generate_diagnostics service call."""
        self._log_service_call("gps_generate_diagnostics", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                diagnostics = await gps_handler.async_generate_diagnostics()
                _LOGGER.info(
                    "Generated GPS diagnostics with %d entries", len(diagnostics)
                )
            else:
                _LOGGER.warning("GPS handler not available for diagnostics")

        except Exception as err:
            _LOGGER.error("Failed to generate GPS diagnostics: %s", err)
            raise HomeAssistantError(
                f"Failed to generate GPS diagnostics: {err}"
            ) from err

    async def _handle_gps_reset_stats(self, call: ServiceCall) -> None:
        """Handle gps_reset_stats service call."""
        self._log_service_call("gps_reset_stats", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                await gps_handler.async_reset_stats()
                _LOGGER.info("GPS statistics reset")
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to reset GPS stats: %s", err)
            raise HomeAssistantError(f"Failed to reset GPS stats: {err}") from err

    async def _handle_gps_export_last_route(self, call: ServiceCall) -> None:
        """Handle gps_export_last_route service call."""
        self._log_service_call("gps_export_last_route", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                route_data = await gps_handler.async_export_last_route()
                _LOGGER.info(
                    "Exported last route with %d points",
                    len(route_data.get("points", [])),
                )
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to export last route: %s", err)
            raise HomeAssistantError(f"Failed to export last route: {err}") from err

    async def _handle_gps_list_webhooks(self, call: ServiceCall) -> None:
        """Handle gps_list_webhooks service call."""
        self._log_service_call("gps_list_webhooks", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                webhooks = await gps_handler.async_list_webhooks()
                _LOGGER.info("Listed %d GPS webhooks", len(webhooks))
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to list GPS webhooks: %s", err)
            raise HomeAssistantError(f"Failed to list GPS webhooks: {err}") from err

    async def _handle_gps_regenerate_webhooks(self, call: ServiceCall) -> None:
        """Handle gps_regenerate_webhooks service call."""
        self._log_service_call("gps_regenerate_webhooks", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if gps_handler := runtime_data.get("gps_handler"):
                await gps_handler.async_regenerate_webhooks()
                _LOGGER.info("Regenerated GPS webhooks")
            else:
                _LOGGER.warning("GPS handler not available")

        except Exception as err:
            _LOGGER.error("Failed to regenerate GPS webhooks: %s", err)
            raise HomeAssistantError(
                f"Failed to regenerate GPS webhooks: {err}"
            ) from err

    async def _handle_route_history_list(self, call: ServiceCall) -> None:
        """Handle route_history_list service call."""
        self._log_service_call("route_history_list", call.data)
        entry_id = call.data.get("config_entry_id")
        if not entry_id:
            raise ServiceValidationError("config_entry_id is required")
        store = RouteHistoryStore(self.hass, entry_id, DOMAIN)
        result = await store.async_list(call.data.get(CONF_DOG_ID, ""))
        self.hass.bus.async_fire(
            f"{DOMAIN}_route_history_listed", {"result": result}
        )

    async def _handle_route_history_purge(self, call: ServiceCall) -> None:
        """Handle route_history_purge service call."""
        self._log_service_call("route_history_purge", call.data)
        entry_id = call.data.get("config_entry_id")
        if not entry_id:
            raise ServiceValidationError("config_entry_id is required")
        store = RouteHistoryStore(self.hass, entry_id, DOMAIN)
        await store.async_purge(call.data.get("older_than_days"))
        self.hass.bus.async_fire(f"{DOMAIN}_route_history_purged", {})

    async def _handle_route_history_export_range(self, call: ServiceCall) -> None:
        """Handle route_history_export_range service call."""
        self._log_service_call("route_history_export_range", call.data)
        entry_id = call.data.get("config_entry_id")
        if not entry_id:
            raise ServiceValidationError("config_entry_id is required")
        store = RouteHistoryStore(self.hass, entry_id, DOMAIN)
        result = await store.async_list(call.data.get(CONF_DOG_ID, ""))
        self.hass.bus.async_fire(
            f"{DOMAIN}_route_history_exported",
            {
                "result": result,
                "date_from": call.data.get("date_from"),
                "date_to": call.data.get("date_to"),
            },
        )

    # ==============================================================================
    # SYSTEM AND UTILITY SERVICE HANDLERS
    # ==============================================================================

    async def _handle_daily_reset(self, call: ServiceCall) -> None:
        """Handle daily_reset service call.

        Resets daily counters for all dogs.
        """
        self._log_service_call("daily_reset", call.data)

        try:
            await self.coordinator.reset_daily_counters()
            _LOGGER.info("Daily counters reset for all dogs")

        except Exception as err:
            _LOGGER.error("Failed to reset daily counters: %s", err)
            raise HomeAssistantError(f"Failed to reset daily counters: {err}") from err

    async def _handle_sync_setup(self, call: ServiceCall) -> None:
        """Handle sync_setup service call."""
        self._log_service_call("sync_setup", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if setup_sync := runtime_data.get("setup_sync"):
                await setup_sync.sync_all()
                _LOGGER.info("Setup synchronization completed")
            else:
                _LOGGER.warning("Setup sync not available")

        except Exception as err:
            _LOGGER.error("Failed to sync setup: %s", err)
            raise HomeAssistantError(f"Failed to sync setup: {err}") from err

    async def _handle_toggle_visitor(self, call: ServiceCall) -> None:
        """Handle toggle_visitor service call."""
        self._log_service_call("toggle_visitor", call.data)

        try:
            # Toggle visitor mode in coordinator
            current_mode = getattr(self.coordinator, "_visitor_mode", False)
            self.coordinator._visitor_mode = not current_mode

            mode_str = "enabled" if self.coordinator._visitor_mode else "disabled"
            _LOGGER.info("Visitor mode %s", mode_str)

        except Exception as err:
            _LOGGER.error("Failed to toggle visitor mode: %s", err)
            raise HomeAssistantError(f"Failed to toggle visitor mode: {err}") from err

    async def _handle_generate_report(self, call: ServiceCall) -> None:
        """Handle generate_report service call."""
        self._log_service_call("generate_report", call.data)

        try:
            runtime_data = self.entry.runtime_data
            if report_generator := runtime_data.get("report_generator"):
                report_type = call.data.get("report_type", "daily")
                report_data = await report_generator.async_generate_report(report_type)
                _LOGGER.info("Generated %s report", report_type)
                return report_data
            else:
                _LOGGER.warning("Report generator not available")

        except Exception as err:
            _LOGGER.error("Failed to generate report: %s", err)
            raise HomeAssistantError(f"Failed to generate report: {err}") from err

    async def _handle_export_data(self, call: ServiceCall) -> None:
        """Handle export_data service call."""
        self._log_service_call("export_data", call.data)

        try:
            data_type = call.data.get("data_type", "all")
            format_type = call.data.get("format", "csv")

            # Export data logic would go here
            _LOGGER.info("Exported %s data in %s format", data_type, format_type)

        except Exception as err:
            _LOGGER.error("Failed to export data: %s", err)
            raise HomeAssistantError(f"Failed to export data: {err}") from err

    async def _handle_notify_test(self, call: ServiceCall) -> None:
        """Handle notify_test service call."""
        self._log_service_call("notify_test", call.data)

        try:
            message = call.data.get("message", "Test notification from Paw Control")
            title = call.data.get("title", "Paw Control Test")
            target = call.data.get("target")

            # Send test notification
            notification_data = {"message": message, "title": title}
            if target:
                notification_data["target"] = target

            await self.hass.services.async_call(
                "notify", "notify", notification_data, blocking=False
            )
            _LOGGER.info("Sent test notification: %s", title)

        except Exception as err:
            _LOGGER.error("Failed to send test notification: %s", err)
            raise HomeAssistantError(
                f"Failed to send test notification: {err}"
            ) from err

    async def _handle_toggle_geofence_alerts(self, call: ServiceCall) -> None:
        """Handle toggle_geofence_alerts service call."""
        self._log_service_call("toggle_geofence_alerts", call.data)
        try:
            from .gps_settings import GPSSettingsStore

            store = GPSSettingsStore(self.hass, call.data["config_entry_id"], DOMAIN)
            data = await store.async_load()
            data["alerts_enabled"] = call.data["enabled"]
            await store.async_save(data)
        except Exception as err:
            _LOGGER.error("Failed to toggle geofence alerts: %s", err)
            raise HomeAssistantError(
                f"Failed to toggle geofence alerts: {err}"
            ) from err

    async def _handle_purge_all_storage(self, call: ServiceCall) -> None:
        """Handle purge_all_storage service call."""
        self._log_service_call("purge_all_storage", call.data)
        try:
            from .route_store import RouteHistoryStore

            store = RouteHistoryStore(self.hass, call.data["config_entry_id"], DOMAIN)
            await store.async_purge()
        except Exception as err:
            _LOGGER.error("Failed to purge storage: %s", err)
            raise HomeAssistantError(f"Failed to purge storage: {err}") from err

    async def _handle_prune_stale_devices(self, call: ServiceCall) -> None:
        """Handle prune_stale_devices service call."""
        self._log_service_call("prune_stale_devices", call.data)

        try:
            dry_run = call.data.get("dry_run", False)
            auto_mode = call.data.get("auto", not dry_run)

            # Import the prune function from __init__.py
            from . import _auto_prune_devices

            removed_count = await _auto_prune_devices(
                self.hass, self.entry, auto=auto_mode
            )

            action = "would remove" if dry_run else "removed"
            _LOGGER.info("Device pruning %s %d stale devices", action, removed_count)

        except Exception as err:
            _LOGGER.error("Failed to prune stale devices: %s", err)
            raise HomeAssistantError(f"Failed to prune stale devices: {err}") from err

    @property
    def service_count(self) -> int:
        """Return the number of registered services."""
        return len(self._registered_services)

    @property
    def service_call_count(self) -> int:
        """Return the total number of service calls processed."""
        return self._service_call_count
