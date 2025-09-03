"""Service handlers for Paw Control integration.

This module contains all service handlers for the Paw Control integration,
optimized for performance with consolidated error handling and caching.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Any, Callable, Final

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVITY_LEVELS,
    ATTR_DOG_ID,
    ATTR_MEAL_TYPE,
    ATTR_PORTION_SIZE,
    CONF_DOG_ID,
    CONF_DOGS,
    CONF_RESET_TIME,
    DEFAULT_RESET_TIME,
    DOMAIN,
    EVENT_FEEDING_LOGGED,
    EVENT_HEALTH_LOGGED,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
    FOOD_TYPES,
    HEALTH_STATUS_OPTIONS,
    MEAL_TYPES,
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
from .exceptions import DogNotFoundError, PawControlError
from .types import PawControlRuntimeData
from .utils import performance_monitor

_LOGGER = logging.getLogger(__name__)

# OPTIMIZATION: Schema builder for common patterns
def _build_dog_service_schema(
    additional_fields: dict[vol.Marker, Any] | None = None
) -> vol.Schema:
    """Build service schema with dog_id and optional additional fields."""
    base_schema = {
        vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50))
    }
    if additional_fields:
        base_schema.update(additional_fields)
    return vol.Schema(base_schema)

# OPTIMIZATION: Consolidated service schemas with builder pattern
SERVICE_FEED_DOG_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional(ATTR_MEAL_TYPE, default="snack"): vol.In(MEAL_TYPES),
    vol.Optional(ATTR_PORTION_SIZE, default=0.0): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=10000.0)
    ),
    vol.Optional("food_type", default="dry_food"): vol.In(FOOD_TYPES),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
    vol.Optional("calories"): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=5000.0)
    ),
})

SERVICE_WALK_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional("label", default=""): vol.All(cv.string, vol.Length(max=100)),
    vol.Optional("location", default=""): vol.All(cv.string, vol.Length(max=200)),
    vol.Optional("walk_type", default="regular"): vol.In(
        ["regular", "training", "exercise", "socialization", "bathroom", "adventure"]
    ),
})

SERVICE_END_WALK_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional("distance", default=0.0): vol.All(
        vol.Coerce(float), vol.Range(min=0.0, max=50000.0)
    ),
    vol.Optional("duration", default=0): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=28800)
    ),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_HEALTH_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional("weight"): vol.All(
        vol.Coerce(float), vol.Range(min=0.1, max=200.0)
    ),
    vol.Optional("temperature"): vol.All(
        vol.Coerce(float), vol.Range(min=35.0, max=42.0)
    ),
    vol.Optional("mood", default=""): vol.In([""] + list(MOOD_OPTIONS)),
    vol.Optional("activity_level", default=""): vol.In([""] + list(ACTIVITY_LEVELS)),
    vol.Optional("health_status", default=""): vol.In([""] + list(HEALTH_STATUS_OPTIONS)),
    vol.Optional("note", default=""): vol.All(cv.string, vol.Length(max=1000)),
})

SERVICE_MEDICATION_SCHEMA: Final = _build_dog_service_schema({
    vol.Required("medication_name"): vol.All(cv.string, vol.Length(min=1, max=100)),
    vol.Required("dosage"): vol.All(cv.string, vol.Length(min=1, max=50)),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_GROOMING_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional("type", default="general"): vol.In(
        ["bath", "brush", "nails", "teeth", "ears", "trim", "full_grooming", "general"]
    ),
    vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
})

SERVICE_NOTIFY_TEST_SCHEMA: Final = _build_dog_service_schema({
    vol.Optional("message", default="Test notification"): vol.All(
        cv.string, vol.Length(min=1, max=200)
    ),
    vol.Optional("priority", default="normal"): vol.In(
        ["low", "normal", "high", "urgent"]
    ),
})

SERVICE_DAILY_RESET_SCHEMA: Final = vol.Schema({
    vol.Optional("force", default=False): cv.boolean,
    vol.Optional("dog_ids"): vol.All(cv.ensure_list, [cv.string]),
})


# OPTIMIZATION: Service handler decorator for consistent error handling
def service_handler(require_dog: bool = True):
    """Decorator for service handlers with unified error handling and validation."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(self, call: ServiceCall) -> None:
            dog_id = call.data.get(ATTR_DOG_ID) if require_dog else None
            
            try:
                if require_dog:
                    if not dog_id:
                        raise ServiceValidationError("dog_id is required")
                    
                    # OPTIMIZATION: Use cached runtime data lookup
                    runtime_data = self._get_runtime_data_cached(dog_id)
                    if not runtime_data:
                        raise DogNotFoundError(dog_id, self._get_available_dog_ids())
                    
                    # Call handler with runtime data
                    await func(self, call, dog_id, runtime_data)
                else:
                    # Call handler without dog validation
                    await func(self, call)
                    
            except PawControlError as err:
                _LOGGER.error("PawControl error in %s: %s", func.__name__, err.to_dict())
                raise ServiceValidationError(err.user_message) from err
            except ServiceValidationError:
                raise
            except Exception as err:
                _LOGGER.error(
                    "Unexpected error in %s: %s", func.__name__, err, exc_info=True
                )
                raise ServiceValidationError(f"Service failed: {err}") from err
        
        return wrapper
    return decorator


class PawControlServiceManager:
    """Optimized service manager for Paw Control integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._registered_services: set[str] = set()
        # OPTIMIZATION: Runtime data cache
        self._runtime_cache: dict[str, tuple[PawControlRuntimeData, float]] = {}
        self._cache_ttl = 60.0  # 1 minute cache

    async def async_register_services(self) -> None:
        """Register all Paw Control services with batch registration."""
        
        # Check if services are already registered
        if SERVICE_FEED_DOG in self._registered_services:
            _LOGGER.debug("Services already registered, skipping registration")
            return

        _LOGGER.debug("Registering Paw Control services")

        # OPTIMIZATION: Batch service registration
        services = {
            SERVICE_FEED_DOG: (self._handle_feed_dog_service, SERVICE_FEED_DOG_SCHEMA),
            SERVICE_START_WALK: (self._handle_start_walk_service, SERVICE_WALK_SCHEMA),
            SERVICE_END_WALK: (self._handle_end_walk_service, SERVICE_END_WALK_SCHEMA),
            SERVICE_LOG_HEALTH: (self._handle_log_health_service, SERVICE_HEALTH_SCHEMA),
            SERVICE_LOG_MEDICATION: (self._handle_log_medication_service, SERVICE_MEDICATION_SCHEMA),
            SERVICE_START_GROOMING: (self._handle_start_grooming_service, SERVICE_GROOMING_SCHEMA),
            SERVICE_DAILY_RESET: (self._handle_daily_reset_service, SERVICE_DAILY_RESET_SCHEMA),
            SERVICE_NOTIFY_TEST: (self._handle_notify_test_service, SERVICE_NOTIFY_TEST_SCHEMA),
        }

        # Register all services at once
        try:
            for service_name, (handler, schema) in services.items():
                self.hass.services.async_register(
                    DOMAIN,
                    service_name,
                    handler,
                    schema=schema,
                )
                self._registered_services.add(service_name)
                
            _LOGGER.info("Successfully registered %d Paw Control services", len(services))
            
        except Exception as err:
            _LOGGER.error("Failed to register services: %s", err)
            # Cleanup any partially registered services
            await self.async_unregister_services()
            raise

    async def async_unregister_services(self) -> None:
        """Unregister all Paw Control services."""
        for service_name in self._registered_services.copy():
            try:
                self.hass.services.async_remove(DOMAIN, service_name)
                self._registered_services.discard(service_name)
                _LOGGER.debug("Unregistered service: %s", service_name)
            except Exception as err:
                _LOGGER.warning(
                    "Failed to unregister service %s: %s", service_name, err
                )

        # Clear cache on unregister
        self._runtime_cache.clear()

    # OPTIMIZATION: Cached runtime data lookup
    def _get_runtime_data_cached(self, dog_id: str) -> PawControlRuntimeData | None:
        """Get runtime data with caching to reduce lookups."""
        now = dt_util.utcnow().timestamp()
        
        # Check cache
        if dog_id in self._runtime_cache:
            cached_data, cache_time = self._runtime_cache[dog_id]
            if now - cache_time < self._cache_ttl:
                return cached_data
        
        # Cache miss, do full lookup
        runtime_data = self._get_runtime_data_for_dog(dog_id)
        if runtime_data:
            self._runtime_cache[dog_id] = (runtime_data, now)
        
        return runtime_data

    # OPTIMIZATION: Calorie estimation extracted to separate method
    @staticmethod
    def _estimate_calories(portion_size: float, food_type: str) -> float:
        """Estimate calories based on portion size and food type."""
        calorie_estimates = {
            "dry_food": 350,  # per 100g
            "wet_food": 85,
            "barf": 150,
            "treat": 400,
            "home_cooked": 120,
        }
        return round((portion_size / 100) * calorie_estimates.get(food_type, 200), 1)

    @service_handler(require_dog=True)
    @performance_monitor(timeout=10.0)
    async def _handle_feed_dog_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the feed_dog service call."""
        meal_type: str = call.data.get(ATTR_MEAL_TYPE, "snack")
        portion_size: float = float(call.data.get(ATTR_PORTION_SIZE, 0.0))
        food_type: str = call.data.get("food_type", "dry_food")
        calories: float = float(call.data.get("calories", 0.0))

        _LOGGER.debug(
            "Processing feed_dog service for %s: %s (%.1fg)",
            dog_id,
            meal_type,
            portion_size,
        )

        data_manager = runtime_data["data_manager"]
        await data_manager.async_feed_dog(dog_id, portion_size)

        # Prepare feeding data
        feeding_data = {
            "meal_type": meal_type,
            "portion_size": portion_size,
            "food_type": food_type,
            "calories": calories or (
                self._estimate_calories(portion_size, food_type) if portion_size > 0 else 0
            ),
            "calories_estimated": calories == 0 and portion_size > 0,
            "logged_by": "service_call",
            "timestamp": dt_util.utcnow(),
        }

        await data_manager.async_log_feeding(dog_id, feeding_data)

        # Fire event
        self.hass.bus.async_fire(
            EVENT_FEEDING_LOGGED,
            {
                ATTR_DOG_ID: dog_id,
                ATTR_MEAL_TYPE: meal_type,
                ATTR_PORTION_SIZE: portion_size,
                "calories": feeding_data["calories"],
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        _LOGGER.info(
            "Successfully logged feeding for %s: %s (%.1fg, %.0f cal)",
            dog_id,
            meal_type,
            portion_size,
            feeding_data["calories"],
        )

    @service_handler(require_dog=True)
    @performance_monitor(timeout=10.0)
    async def _handle_start_walk_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the start_walk service call."""
        walk_type: str = call.data.get("walk_type", "regular")

        _LOGGER.debug("Processing start_walk service for %s: %s", dog_id, walk_type)

        data_manager = runtime_data["data_manager"]
        
        walk_data = {
            "label": call.data.get("label", ""),
            "location": call.data.get("location", ""),
            "walk_type": walk_type,
            "started_by": "service_call",
        }

        walk_id = await data_manager.async_start_walk(dog_id, walk_data)

        self.hass.bus.async_fire(
            EVENT_WALK_STARTED,
            {
                ATTR_DOG_ID: dog_id,
                "walk_id": walk_id,
                "walk_type": walk_type,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        _LOGGER.info("Successfully started walk %s for %s", walk_id, dog_id)

    @service_handler(require_dog=True)
    async def _handle_end_walk_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the end_walk service call."""
        distance: float = float(call.data.get("distance", 0.0))
        duration: int = int(call.data.get("duration", 0))

        _LOGGER.debug("Processing end_walk service for %s", dog_id)

        data_manager = runtime_data["data_manager"]
        
        walk_data = {
            "distance": distance,
            "duration_minutes": duration,
            "notes": call.data.get("notes", "").strip(),
            "ended_by": "service_call",
        }

        await data_manager.async_end_walk(dog_id, walk_data)

        self.hass.bus.async_fire(
            EVENT_WALK_ENDED,
            {
                ATTR_DOG_ID: dog_id,
                "duration_minutes": duration,
                "distance": distance,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        _LOGGER.info("Successfully ended walk for %s", dog_id)

    @service_handler(require_dog=True)
    async def _handle_log_health_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the log_health service call."""
        _LOGGER.debug("Processing log_health service for %s", dog_id)

        data_manager = runtime_data["data_manager"]
        
        # Collect only non-empty health data
        health_data = {
            k: v for k, v in {
                "weight": call.data.get("weight"),
                "temperature": call.data.get("temperature"),
                "mood": call.data.get("mood", ""),
                "activity_level": call.data.get("activity_level", ""),
                "health_status": call.data.get("health_status", ""),
                "note": call.data.get("note", ""),
                "logged_by": "service_call",
            }.items() if v is not None and v != ""
        }

        await data_manager.async_log_health(dog_id, health_data)

        self.hass.bus.async_fire(
            EVENT_HEALTH_LOGGED,
            {
                ATTR_DOG_ID: dog_id,
                "data_types": list(health_data.keys()),
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

        _LOGGER.info("Successfully logged health data for %s", dog_id)

    @service_handler(require_dog=True)
    async def _handle_log_medication_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the log_medication service call."""
        medication_name: str = call.data["medication_name"]
        dosage: str = call.data["dosage"]

        _LOGGER.debug(
            "Processing log_medication service for %s: %s", dog_id, medication_name
        )

        data_manager = runtime_data["data_manager"]
        
        medication_data = {
            "type": "medication",
            "medication_name": medication_name,
            "dosage": dosage,
            "administration_time": dt_util.utcnow(),
            "notes": call.data.get("notes", ""),
            "logged_by": "service_call",
        }

        await data_manager.async_log_health(dog_id, medication_data)

        _LOGGER.info(
            "Successfully logged medication %s for %s", medication_name, dog_id
        )

    @service_handler(require_dog=True)
    async def _handle_start_grooming_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the start_grooming service call."""
        grooming_type: str = call.data.get("type", "general")

        _LOGGER.debug(
            "Processing start_grooming service for %s: %s", dog_id, grooming_type
        )

        data_manager = runtime_data["data_manager"]
        
        grooming_data = {
            "type": grooming_type,
            "notes": call.data.get("notes", ""),
            "started_by": "service_call",
        }

        grooming_id = await data_manager.async_start_grooming(dog_id, grooming_data)

        _LOGGER.info("Successfully started grooming %s for %s", grooming_id, dog_id)

    @service_handler(require_dog=False)
    async def _handle_daily_reset_service(self, call: ServiceCall) -> None:
        """Handle the daily_reset service call."""
        _LOGGER.debug("Processing daily_reset service call")

        # Reset daily statistics for all dogs
        all_dogs = self._get_available_dog_ids()
        
        # OPTIMIZATION: Batch reset with asyncio.gather
        reset_tasks = []
        for dog_id in all_dogs:
            runtime_data = self._get_runtime_data_cached(dog_id)
            if runtime_data:
                data_manager = runtime_data["data_manager"]
                reset_tasks.append(data_manager.async_reset_dog_daily_stats(dog_id))

        if reset_tasks:
            results = await asyncio.gather(*reset_tasks, return_exceptions=True)
            failures = sum(1 for r in results if isinstance(r, Exception))
            if failures:
                _LOGGER.warning(
                    "Daily reset completed with %d failures out of %d dogs",
                    failures,
                    len(all_dogs)
                )
            else:
                _LOGGER.info(
                    "Daily reset completed successfully for %d dogs", len(all_dogs)
                )

    @service_handler(require_dog=True)
    async def _handle_notify_test_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle the notify_test service call."""
        message: str = call.data.get("message", "Test notification from Paw Control")
        priority: str = call.data.get("priority", "normal")

        _LOGGER.debug("Processing notify_test service for %s", dog_id)

        notification_manager = runtime_data["notification_manager"]
        
        success = await notification_manager.async_send_test_notification(
            dog_id, message, priority
        )

        if success:
            _LOGGER.info("Successfully sent test notification for %s", dog_id)
        else:
            _LOGGER.warning("Failed to send test notification for %s", dog_id)

    def _get_runtime_data_for_dog(self, dog_id: str) -> PawControlRuntimeData | None:
        """Find the runtime data that contains a specific dog.

        Args:
            dog_id: Unique identifier of the dog to find

        Returns:
            Runtime data dictionary containing the dog, or None if not found
        """
        # Search through all config entries for the dog
        for config_entry in self.hass.config_entries.async_entries(DOMAIN):
            # Try modern runtime_data first
            runtime_data = getattr(config_entry, "runtime_data", None)

            if runtime_data:
                dogs = runtime_data.get("dogs", [])
                for dog in dogs:
                    if dog.get(CONF_DOG_ID) == dog_id:
                        return runtime_data

            # Fallback to legacy data storage
            legacy_data = self.hass.data[DOMAIN].get(config_entry.entry_id, {})
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

    def _get_available_dog_ids(self) -> list[str]:
        """Get list of all available dog IDs across all config entries.

        Returns:
            List of available dog IDs
        """
        dog_ids = []

        for config_entry in self.hass.config_entries.async_entries(DOMAIN):
            # Try modern runtime_data first
            runtime_data = getattr(config_entry, "runtime_data", None)

            if runtime_data:
                dogs = runtime_data.get("dogs", [])
                dog_ids.extend(
                    dog.get(CONF_DOG_ID) for dog in dogs if dog.get(CONF_DOG_ID)
                )
            else:
                # Fallback to legacy data
                dogs = config_entry.data.get(CONF_DOGS, [])
                dog_ids.extend(
                    dog.get(CONF_DOG_ID) for dog in dogs if dog.get(CONF_DOG_ID)
                )

        return dog_ids


async def async_setup_daily_reset_scheduler(hass: HomeAssistant, entry: Any) -> None:
    """Set up the daily reset scheduler with enhanced error handling.

    Args:
        hass: Home Assistant instance
        entry: Config entry containing reset time configuration
    """
    # Use global flag to prevent duplicate scheduling
    domain_data = hass.data.setdefault(DOMAIN, {})
    scheduler_key = "_daily_reset_scheduled"

    if domain_data.get(scheduler_key):
        _LOGGER.debug("Daily reset scheduler already configured")
        return

    reset_time_str: str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)

    try:
        reset_time_obj = dt_util.parse_time(reset_time_str)
        if not reset_time_obj:
            raise ValueError(f"Invalid time format: {reset_time_str}")
    except ValueError:
        _LOGGER.warning(
            "Invalid reset time format '%s', using default %s",
            reset_time_str,
            DEFAULT_RESET_TIME,
        )
        reset_time_obj = dt_util.parse_time(DEFAULT_RESET_TIME)

    @callback
    def _daily_reset_callback(now) -> None:
        """Enhanced callback function for daily reset execution."""
        _LOGGER.info("Triggering daily reset at %s", now)

        # Create async task with timeout protection
        async def _run_daily_reset() -> None:
            try:
                async with asyncio.timeout(60):
                    await hass.services.async_call(DOMAIN, SERVICE_DAILY_RESET, {})
                _LOGGER.info("Daily reset completed successfully")
            except asyncio.TimeoutError:
                _LOGGER.error("Daily reset timed out after 60 seconds")
            except Exception as err:
                _LOGGER.error("Daily reset task failed: %s", err, exc_info=True)

        # Create task with name for better debugging
        hass.async_create_task(
            _run_daily_reset(),
            name=f"paw_control_daily_reset_{now.strftime('%Y%m%d_%H%M')}",
        )

    # Import here to avoid circular dependency
    from homeassistant.helpers.event import async_track_time_change

    # Schedule the daily reset
    remove_listener = async_track_time_change(
        hass,
        _daily_reset_callback,
        hour=reset_time_obj.hour,
        minute=reset_time_obj.minute,
        second=reset_time_obj.second,
    )

    # Store the remove listener function for cleanup
    domain_data["_reset_listener_remove"] = remove_listener
    domain_data[scheduler_key] = True

    _LOGGER.info(
        "Daily reset scheduled for %02d:%02d:%02d",
        reset_time_obj.hour,
        reset_time_obj.minute,
        reset_time_obj.second,
    )
