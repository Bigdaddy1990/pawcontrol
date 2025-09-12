"""Ultra-optimized service handlers for PawControl.

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, Final

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
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

# OPTIMIZATION: Schema cache for faster validation
_SCHEMA_CACHE: dict[str, vol.Schema] = {}

# Constant mapping for health data fields to feeding manager attributes
_HEALTH_DATA_FIELD_MAP: Final[dict[str, str]] = {
    "weight": "dog_weight",
    "ideal_weight": "ideal_weight",
    "body_condition_score": "body_condition_score",
    "age_months": "age_months",
    "activity_level": "activity_level",
    "health_conditions": "health_conditions",
    "weight_goal": "weight_goal",
    "spayed_neutered": "spayed_neutered",
}


def _get_cached_schema(schema_id: str, builder: Callable[[], vol.Schema]) -> vol.Schema:
    """Get cached schema or build new one.

    Args:
        schema_id: Schema identifier
        builder: Function to build schema

    Returns:
        Cached or newly built schema
    """
    if schema_id not in _SCHEMA_CACHE:
        _SCHEMA_CACHE[schema_id] = builder()
    return _SCHEMA_CACHE[schema_id]


# OPTIMIZATION: Schema builders with caching
def _build_dog_service_schema(
    additional_fields: dict[vol.Marker, Any] | None = None,
) -> vol.Schema:
    """Build service schema with dog_id and optional fields."""
    base = {vol.Required(ATTR_DOG_ID): vol.All(cv.string, vol.Length(min=1, max=50))}
    if additional_fields:
        base.update(additional_fields)
    return vol.Schema(base)


# Service schemas with lazy loading
SERVICE_FEED_DOG_SCHEMA: Final = _build_dog_service_schema(
    {
        vol.Optional(ATTR_MEAL_TYPE, default="snack"): vol.In(MEAL_TYPES),
        vol.Optional(ATTR_PORTION_SIZE, default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=10000.0)
        ),
        vol.Optional("food_type", default="dry_food"): vol.In(FOOD_TYPES),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
        vol.Optional("calories"): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=5000.0)
        ),
    }
)

SERVICE_WALK_SCHEMA: Final = _build_dog_service_schema(
    {
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
    }
)

SERVICE_END_WALK_SCHEMA: Final = _build_dog_service_schema(
    {
        vol.Optional("distance", default=0.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=50000.0)
        ),
        vol.Optional("duration", default=0): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=28800)
        ),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
    }
)

SERVICE_HEALTH_SCHEMA: Final = _build_dog_service_schema(
    {
        vol.Optional("weight"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=200.0)
        ),
        vol.Optional("temperature"): vol.All(
            vol.Coerce(float), vol.Range(min=35.0, max=42.0)
        ),
        vol.Optional("mood", default=""): vol.In(["", *list(MOOD_OPTIONS)]),
        vol.Optional("activity_level", default=""): vol.In(
            ["", *list(ACTIVITY_LEVELS)]
        ),
        vol.Optional("health_status", default=""): vol.In(
            ["", *list(HEALTH_STATUS_OPTIONS)]
        ),
        vol.Optional("note", default=""): vol.All(cv.string, vol.Length(max=1000)),
    }
)

SERVICE_MEDICATION_SCHEMA: Final = _build_dog_service_schema(
    {
        vol.Required("medication_name"): vol.All(cv.string, vol.Length(min=1, max=100)),
        vol.Required("dosage"): vol.All(cv.string, vol.Length(min=1, max=50)),
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
    }
)

SERVICE_GROOMING_SCHEMA: Final = _build_dog_service_schema(
    {
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
        vol.Optional("notes", default=""): vol.All(cv.string, vol.Length(max=500)),
    }
)

SERVICE_NOTIFY_TEST_SCHEMA: Final = _build_dog_service_schema(
    {
        vol.Optional("message", default="Test notification"): vol.All(
            cv.string, vol.Length(min=1, max=200)
        ),
        vol.Optional("priority", default="normal"): vol.In(
            ["low", "normal", "high", "urgent"]
        ),
    }
)

SERVICE_DAILY_RESET_SCHEMA: Final = vol.Schema(
    {
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("dog_ids"): vol.All(cv.ensure_list, [cv.string]),
    }
)

# Health-Aware Feeding Service Schemas
SERVICE_RECALCULATE_HEALTH_PORTIONS_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("trigger_reason", default="manual"): cv.string,
        vol.Optional("force_update", default=False): cv.boolean,
    }
)

SERVICE_FEED_HEALTH_AWARE_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Required("meal_type"): vol.In(["breakfast", "lunch", "dinner", "snack"]),
        vol.Optional("use_health_calculation", default=True): cv.boolean,
        vol.Optional("override_portion"): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=2000)
        ),
        vol.Optional("notes", default=""): cv.string,
    }
)

SERVICE_UPDATE_HEALTH_DATA_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("weight"): vol.All(vol.Coerce(float), vol.Range(min=0.1, max=200)),
        vol.Optional("ideal_weight"): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=200)
        ),
        vol.Optional("body_condition_score"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=9)
        ),
        vol.Optional("age_months"): vol.All(vol.Coerce(int), vol.Range(min=1, max=300)),
        vol.Optional("activity_level"): vol.In(
            ["very_low", "low", "moderate", "high", "very_high"]
        ),
        vol.Optional("health_conditions"): [cv.string],
        vol.Optional("weight_goal"): vol.In(["maintain", "lose", "gain"]),
        vol.Optional("spayed_neutered"): cv.boolean,
    }
)

SERVICE_FEED_WITH_MEDICATION_SCHEMA: Final = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("medication_name"): cv.string,
        vol.Optional("dosage"): cv.string,
        vol.Optional("auto_calculate_portion", default=True): cv.boolean,
        vol.Optional("medication_timing", default="optimal"): vol.In(
            ["optimal", "immediate", "delayed"]
        ),
        vol.Optional("notes", default=""): cv.string,
    }
)


# OPTIMIZATION: Enhanced service handler with priority caching
def service_handler(
    require_dog: bool = True, cache_priority: int = 5, timeout: float = 10.0
):
    """Decorator for service handlers with caching and error handling.

    Args:
        require_dog: Whether dog_id is required
        cache_priority: Cache priority (1-10, higher = longer TTL)
        timeout: Service timeout in seconds
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        @performance_monitor(timeout=timeout)
        async def wrapper(self, call: ServiceCall) -> None:
            dog_id = call.data.get(ATTR_DOG_ID) if require_dog else None

            try:
                if require_dog:
                    if not dog_id:
                        raise ServiceValidationError("dog_id is required")

                    # Get runtime data with dynamic cache
                    runtime_data = self._get_runtime_data_cached(
                        dog_id, priority=cache_priority
                    )
                    if not runtime_data:
                        raise DogNotFoundError(dog_id, self._get_available_dog_ids())

                    await func(self, call, dog_id, runtime_data)
                else:
                    await func(self, call)

            except PawControlError as err:
                _LOGGER.error("Service error in %s: %s", func.__name__, err.to_dict())
                raise ServiceValidationError(err.user_message) from err
            except ServiceValidationError:
                raise
            except TimeoutError as err:
                _LOGGER.error("Service %s timed out after %ss", func.__name__, timeout)
                raise ServiceValidationError(
                    f"Service timed out after {timeout}s"
                ) from err
            except Exception as err:
                _LOGGER.error("Unexpected error in %s: %s", func.__name__, err)
                raise ServiceValidationError(f"Service failed: {err}") from err

        return wrapper

    return decorator


class PawControlServiceManager:
    """Ultra-optimized service manager with dynamic caching."""

    # OPTIMIZATION: Calorie lookup table
    _CALORIE_TABLE = {  # noqa: RUF012
        "dry_food": 350,
        "wet_food": 85,
        "barf": 150,
        "treat": 400,
        "home_cooked": 120,
    }

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize service manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._registered_services: set[str] = set()

        # OPTIMIZATION: Dynamic cache with priority-based TTL
        self._runtime_cache: dict[str, tuple[PawControlRuntimeData, float, int]] = {}
        self._base_ttl = 30.0  # Base TTL in seconds
        self._cache_hits = 0
        self._cache_misses = 0

        # OPTIMIZATION: Service registry for batch registration
        self._service_registry = {
            SERVICE_FEED_DOG: (
                self._handle_feed_dog_service,
                SERVICE_FEED_DOG_SCHEMA,
                {"priority": 8, "timeout": 5.0},
            ),
            SERVICE_START_WALK: (
                self._handle_start_walk_service,
                SERVICE_WALK_SCHEMA,
                {"priority": 7, "timeout": 5.0},
            ),
            SERVICE_END_WALK: (
                self._handle_end_walk_service,
                SERVICE_END_WALK_SCHEMA,
                {"priority": 7, "timeout": 5.0},
            ),
            SERVICE_LOG_HEALTH: (
                self._handle_log_health_service,
                SERVICE_HEALTH_SCHEMA,
                {"priority": 5, "timeout": 5.0},
            ),
            SERVICE_LOG_MEDICATION: (
                self._handle_log_medication_service,
                SERVICE_MEDICATION_SCHEMA,
                {"priority": 6, "timeout": 5.0},
            ),
            SERVICE_START_GROOMING: (
                self._handle_start_grooming_service,
                SERVICE_GROOMING_SCHEMA,
                {"priority": 4, "timeout": 5.0},
            ),
            SERVICE_DAILY_RESET: (
                self._handle_daily_reset_service,
                SERVICE_DAILY_RESET_SCHEMA,
                {"priority": 3, "timeout": 10.0},
            ),
            SERVICE_NOTIFY_TEST: (
                self._handle_notify_test_service,
                SERVICE_NOTIFY_TEST_SCHEMA,
                {"priority": 2, "timeout": 3.0},
            ),
            # Health-Aware Feeding Services
            "recalculate_health_portions": (
                self._handle_recalculate_health_portions,
                SERVICE_RECALCULATE_HEALTH_PORTIONS_SCHEMA,
                {"priority": 7, "timeout": 10.0},
            ),
            "feed_health_aware": (
                self._handle_feed_health_aware,
                SERVICE_FEED_HEALTH_AWARE_SCHEMA,
                {"priority": 8, "timeout": 8.0},
            ),
            "update_health_data": (
                self._handle_update_health_data,
                SERVICE_UPDATE_HEALTH_DATA_SCHEMA,
                {"priority": 6, "timeout": 5.0},
            ),
            "feed_with_medication": (
                self._handle_feed_with_medication,
                SERVICE_FEED_WITH_MEDICATION_SCHEMA,
                {"priority": 9, "timeout": 8.0},
            ),
        }

    async def async_register_services(self) -> None:
        """Register all services with batch optimization."""

        if self._registered_services:
            _LOGGER.debug("Services already registered")
            return

        _LOGGER.debug("Registering PawControl services")

        # OPTIMIZATION: Batch registration
        try:
            for service_name, (handler, schema, _) in self._service_registry.items():
                # Register service without blocking
                self.hass.services.async_register(
                    DOMAIN,
                    service_name,
                    handler,
                    schema=schema,
                )
                self._registered_services.add(service_name)

            _LOGGER.info("Registered %d services", len(self._registered_services))

        except Exception as err:
            _LOGGER.error("Service registration failed: %s", err)
            await self.async_unregister_services()
            raise

    async def async_unregister_services(self) -> None:
        """Unregister all services."""
        for service_name in self._registered_services.copy():
            try:
                self.hass.services.async_remove(DOMAIN, service_name)
                self._registered_services.discard(service_name)
            except Exception as err:
                _LOGGER.warning("Failed to unregister %s: %s", service_name, err)

        # Clear caches
        self._runtime_cache.clear()
        _LOGGER.debug("Unregistered all services")

    def _get_runtime_data_cached(
        self, dog_id: str, priority: int = 5
    ) -> PawControlRuntimeData | None:
        """Get runtime data with priority-based caching.

        Args:
            dog_id: Dog identifier
            priority: Cache priority (1-10, higher = longer TTL)

        Returns:
            Runtime data or None
        """
        now = dt_util.utcnow().timestamp()

        # Check cache
        if dog_id in self._runtime_cache:
            cached_data, cache_time, cache_priority = self._runtime_cache[dog_id]

            # Dynamic TTL based on priority
            ttl = self._base_ttl * (1 + cache_priority / 10)

            if now - cache_time < ttl:
                self._cache_hits += 1
                return cached_data

        # Cache miss
        self._cache_misses += 1
        runtime_data = self._get_runtime_data_for_dog(dog_id)

        if runtime_data:
            self._runtime_cache[dog_id] = (runtime_data, now, priority)

            # OPTIMIZATION: Clean old cache entries periodically
            if len(self._runtime_cache) > 20:
                self._cleanup_cache(now)

        return runtime_data

    def _cleanup_cache(self, now: float) -> None:
        """Clean expired cache entries."""
        expired_keys = []

        for key, (_, cache_time, priority) in self._runtime_cache.items():
            ttl = self._base_ttl * (1 + priority / 10)
            if now - cache_time > ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self._runtime_cache[key]

    def _get_runtime_data_for_dog(self, dog_id: str) -> PawControlRuntimeData | None:
        """Get runtime data for a specific dog.

        Args:
            dog_id: Dog identifier

        Returns:
            Runtime data or None
        """
        # Find the correct entry for this dog
        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict):  # noqa: SIM102
                # Check modern runtime_data first
                if coordinator := entry_data.get("coordinator"):  # noqa: SIM102
                    if hasattr(coordinator, "config_entry"):
                        entry = coordinator.config_entry

                        # Check runtime_data
                        if runtime_data := getattr(entry, "runtime_data", None):
                            dogs = runtime_data.get("dogs", [])
                            if any(d.get(CONF_DOG_ID) == dog_id for d in dogs):
                                return runtime_data

                        # Check entry data
                        dogs = entry.data.get(CONF_DOGS, [])
                        if any(d.get(CONF_DOG_ID) == dog_id for d in dogs):
                            # Build runtime data from components
                            return {
                                "coordinator": coordinator,
                                "data_manager": entry_data.get("data"),
                                "notification_manager": entry_data.get("notifications"),
                                "config_entry": entry,
                                "dogs": dogs,
                            }

        return None

    def _get_available_dog_ids(self) -> list[str]:
        """Get all available dog IDs.

        Returns:
            List of dog IDs
        """
        dog_ids = []

        for entry_data in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(entry_data, dict):  # noqa: SIM102
                if coordinator := entry_data.get("coordinator"):  # noqa: SIM102
                    if hasattr(coordinator, "get_dog_ids"):
                        dog_ids.extend(coordinator.get_dog_ids())

        return list(set(dog_ids))

    @staticmethod
    def _estimate_calories(portion_size: float, food_type: str) -> float:
        """Estimate calories with lookup table.

        Args:
            portion_size: Portion in grams
            food_type: Type of food

        Returns:
            Estimated calories
        """
        calories_per_100g = PawControlServiceManager._CALORIE_TABLE.get(food_type, 200)
        return round((portion_size / 100) * calories_per_100g, 1)

    # Service handlers with optimized decorators
    @service_handler(require_dog=True, cache_priority=8, timeout=5.0)
    async def _handle_feed_dog_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle feed_dog service."""
        meal_type = call.data.get(ATTR_MEAL_TYPE, "snack")
        portion_size = float(call.data.get(ATTR_PORTION_SIZE, 0.0))
        food_type = call.data.get("food_type", "dry_food")
        calories = float(call.data.get("calories", 0.0))

        data_manager = runtime_data["data_manager"]
        await data_manager.async_feed_dog(dog_id, portion_size)

        # Prepare feeding data
        feeding_data = {
            "meal_type": meal_type,
            "portion_size": portion_size,
            "food_type": food_type,
            "calories": calories
            or (
                self._estimate_calories(portion_size, food_type)
                if portion_size > 0
                else 0
            ),
            "logged_by": "service_call",
            "timestamp": dt_util.utcnow(),
        }

        await data_manager.async_log_feeding(dog_id, feeding_data)

        # Fire event asynchronously
        self.hass.bus.async_fire(
            EVENT_FEEDING_LOGGED,
            {
                ATTR_DOG_ID: dog_id,
                ATTR_MEAL_TYPE: meal_type,
                ATTR_PORTION_SIZE: portion_size,
                "calories": feeding_data["calories"],
            },
        )

        # Invalidate cache for this dog with priority
        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=8)

    @service_handler(require_dog=True, cache_priority=7, timeout=5.0)
    async def _handle_start_walk_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle start_walk service."""
        data_manager = runtime_data["data_manager"]
        coordinator = runtime_data["coordinator"]

        # Check for active walk
        current_walk = await data_manager.async_get_current_walk(dog_id)
        if current_walk:
            raise ServiceValidationError(
                f"Walk already in progress for {dog_id} (ID: {current_walk.get('walk_id')})"
            )

        walk_data = {
            "label": call.data.get("label", ""),
            "location": call.data.get("location", ""),
            "walk_type": call.data.get("walk_type", "regular"),
        }

        walk_id = await data_manager.async_start_walk(dog_id, walk_data)

        self.hass.bus.async_fire(
            EVENT_WALK_STARTED,
            {
                ATTR_DOG_ID: dog_id,
                "walk_id": walk_id,
                "start_time": dt_util.utcnow().isoformat(),
            },
        )

        await coordinator.async_request_selective_refresh([dog_id], priority=9)

    @service_handler(require_dog=True, cache_priority=7, timeout=5.0)
    async def _handle_end_walk_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle end_walk service."""
        data_manager = runtime_data["data_manager"]
        coordinator = runtime_data["coordinator"]

        # Check for active walk
        current_walk = await data_manager.async_get_current_walk(dog_id)
        if not current_walk:
            raise ServiceValidationError(f"No active walk for {dog_id}")

        walk_data = {
            "distance": call.data.get("distance", 0.0),
            "duration": call.data.get("duration", 0),
            "notes": call.data.get("notes", ""),
        }

        await data_manager.async_end_walk(dog_id, walk_data)

        self.hass.bus.async_fire(
            EVENT_WALK_ENDED,
            {
                ATTR_DOG_ID: dog_id,
                "walk_id": current_walk.get("walk_id"),
                "end_time": dt_util.utcnow().isoformat(),
                "distance": walk_data["distance"],
                "duration": walk_data["duration"],
            },
        )

        await coordinator.async_request_selective_refresh([dog_id], priority=9)

    @service_handler(require_dog=True, cache_priority=5, timeout=5.0)
    async def _handle_log_health_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle log_health service."""
        health_data = {
            key: value
            for key, value in {
                "weight": call.data.get("weight"),
                "temperature": call.data.get("temperature"),
                "mood": call.data.get("mood"),
                "activity_level": call.data.get("activity_level"),
                "health_status": call.data.get("health_status"),
                "note": call.data.get("note"),
            }.items()
            if value
        }

        data_manager = runtime_data["data_manager"]
        await data_manager.async_log_health(dog_id, health_data)

        self.hass.bus.async_fire(
            EVENT_HEALTH_LOGGED,
            {
                ATTR_DOG_ID: dog_id,
                "timestamp": dt_util.utcnow().isoformat(),
                **health_data,
            },
        )

        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=6)

    @service_handler(require_dog=True, cache_priority=6, timeout=5.0)
    async def _handle_log_medication_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle log_medication service."""
        medication_data = {
            "medication_name": call.data["medication_name"],
            "dosage": call.data["dosage"],
            "notes": call.data.get("notes", ""),
            "timestamp": dt_util.utcnow().isoformat(),
        }

        data_manager = runtime_data["data_manager"]
        await data_manager.async_log_health(
            dog_id,
            {
                "type": "medication",
                **medication_data,
            },
        )

    @service_handler(require_dog=True, cache_priority=4, timeout=5.0)
    async def _handle_start_grooming_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle start_grooming service."""
        grooming_data = {
            "type": call.data.get("type", "general"),
            "notes": call.data.get("notes", ""),
        }

        data_manager = runtime_data["data_manager"]
        grooming_id = await data_manager.async_start_grooming(dog_id, grooming_data)

        _LOGGER.info("Started grooming session %s for %s", grooming_id, dog_id)

    @service_handler(require_dog=False, cache_priority=3, timeout=10.0)
    async def _handle_daily_reset_service(self, call: ServiceCall) -> None:
        """Handle daily_reset service."""
        call.data.get("force", False)
        dog_ids = call.data.get("dog_ids", [])

        # Get all entries if no specific dogs
        if not dog_ids:
            dog_ids = self._get_available_dog_ids()

        # Reset each dog's stats
        reset_count = 0
        for dog_id in dog_ids:
            runtime_data = self._get_runtime_data_cached(dog_id, priority=1)
            if runtime_data:
                data_manager = runtime_data["data_manager"]
                await data_manager.async_reset_dog_daily_stats(dog_id)
                reset_count += 1

        _LOGGER.info("Reset daily stats for %d dogs", reset_count)

    @service_handler(require_dog=True, cache_priority=2, timeout=3.0)
    async def _handle_notify_test_service(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle notify_test service."""
        message = call.data.get("message", f"Test notification for {dog_id}")
        priority = call.data.get("priority", "normal")

        notification_manager = runtime_data.get("notification_manager")
        if notification_manager:
            await notification_manager.async_send_notification(
                dog_id,
                message,
                priority=priority,
                test_mode=True,
            )

        _LOGGER.info("Sent test notification for %s", dog_id)

    # Health-Aware Feeding Service Handlers
    @service_handler(require_dog=True, cache_priority=7, timeout=10.0)
    async def _handle_recalculate_health_portions(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle recalculate_health_portions service."""
        trigger_reason = call.data.get("trigger_reason", "manual")
        call.data.get("force_update", False)

        # Get feeding manager
        feeding_manager = runtime_data.get("feeding_manager")
        if not feeding_manager:
            raise ServiceValidationError("Feeding manager not available")

        try:
            # Update config with health-aware recalculation
            config = feeding_manager._configs.get(dog_id)
            if not config:
                raise ServiceValidationError("No feeding configuration found")

            # Trigger portion recalculation
            old_portion = config.calculate_portion_size()

            # Force recalculation by clearing cache
            feeding_manager._invalidate_cache(dog_id)

            # Get new portion
            new_portion = config.calculate_portion_size()

            # Fire event for successful recalculation
            self.hass.bus.async_fire(
                f"{DOMAIN}_health_portions_recalculated",
                {
                    ATTR_DOG_ID: dog_id,
                    "trigger_reason": trigger_reason,
                    "old_portion": old_portion,
                    "new_portion": new_portion,
                    "timestamp": dt_util.utcnow().isoformat(),
                },
            )

            _LOGGER.info(
                "Recalculated health portions for %s: %sg -> %sg (reason: %s)",
                dog_id,
                old_portion,
                new_portion,
                trigger_reason,
            )

        except Exception as err:
            _LOGGER.error("Health portion recalculation failed for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Recalculation failed: {err}") from err

        # Update coordinator with high priority
        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=9)

    @service_handler(require_dog=True, cache_priority=8, timeout=8.0)
    async def _handle_feed_health_aware(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle feed_health_aware service."""
        meal_type = call.data["meal_type"]
        use_health_calc = call.data.get("use_health_calculation", True)
        override_portion = call.data.get("override_portion")
        notes = call.data.get("notes", "")

        feeding_manager = runtime_data.get("feeding_manager")
        if not feeding_manager:
            raise ServiceValidationError("Feeding manager not available")

        try:
            # Calculate portion size
            if override_portion is not None:
                portion_size = override_portion
                calculation_method = "manual_override"
            elif use_health_calc:
                # Use health-aware calculation
                config = feeding_manager._configs.get(dog_id)
                if config and config.health_aware_portions:
                    from .feeding_manager import MealType

                    try:
                        meal_enum = MealType(meal_type)
                        portion_size = config.calculate_portion_size(meal_enum)
                        calculation_method = "health_aware"
                    except ValueError:
                        portion_size = config.calculate_portion_size()
                        calculation_method = "health_aware_fallback"
                else:
                    raise ServiceValidationError("Health-aware feeding not configured")
            else:
                # Use standard calculation
                config = feeding_manager._configs.get(dog_id)
                if config:
                    portion_size = config.calculate_portion_size()
                    calculation_method = "standard"
                else:
                    raise ServiceValidationError("No feeding configuration found")

            # Add feeding event with health calculation info
            combined_notes = f"Health-aware feeding ({calculation_method})"
            if notes:
                combined_notes += f" - {notes}"

            feeding_event = await feeding_manager.async_add_feeding(
                dog_id=dog_id,
                amount=portion_size,
                meal_type=meal_type,
                notes=combined_notes,
                feeder="health_aware_service",
                scheduled=True,
            )

            # Fire enhanced event
            self.hass.bus.async_fire(
                f"{DOMAIN}_health_aware_feeding_logged",
                {
                    ATTR_DOG_ID: dog_id,
                    "meal_type": meal_type,
                    "portion_size": portion_size,
                    "calculation_method": calculation_method,
                    "health_calculation_used": use_health_calc,
                    "timestamp": feeding_event.time.isoformat(),
                },
            )

            _LOGGER.info(
                "Health-aware feeding logged for %s: %s (%sg, %s)",
                dog_id,
                meal_type,
                portion_size,
                calculation_method,
            )

        except Exception as err:
            _LOGGER.error("Health-aware feeding failed for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Health-aware feeding failed: {err}") from err

        # Update coordinator
        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=8)

    @service_handler(require_dog=True, cache_priority=6, timeout=5.0)
    async def _handle_update_health_data(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle update_health_data service."""
        health_data = {
            key: value
            for key, value in call.data.items()
            if key != ATTR_DOG_ID and value is not None
        }

        if not health_data:
            raise ServiceValidationError("No health data provided")

        # Update data manager if available
        data_manager = runtime_data.get("data_manager")
        if data_manager:
            await data_manager.async_log_health(
                dog_id,
                {
                    "type": "health_data_update",
                    "updated_fields": list(health_data.keys()),
                    **health_data,
                },
            )

        # Update feeding manager config if available
        feeding_manager = runtime_data.get("feeding_manager")
        if feeding_manager:
            config = feeding_manager._configs.get(dog_id)
            if config:
                for field, attr in _HEALTH_DATA_FIELD_MAP.items():
                    if field in health_data:
                        setattr(config, attr, health_data[field])

                feeding_manager._invalidate_cache(dog_id)

            self._update_feeding_config(feeding_manager, dog_id, health_data)

        # Fire event
        self._fire_health_update_event(dog_id, list(health_data.keys()))

        _LOGGER.info(
            "Updated health data for %s: %s", dog_id, ", ".join(health_data.keys())
        )

        # Update coordinator
        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=7)

    def _update_feeding_config(
        self,
        feeding_manager: Any,
        dog_id: str,
        health_data: dict[str, Any],
    ) -> None:
        """Update feeding manager configuration with health data."""
        config = feeding_manager._configs.get(dog_id)
        if not config:
            return

        for key, attr in _HEALTH_DATA_FIELD_MAP.items():
            if key in health_data:
                setattr(config, attr, health_data[key])

        feeding_manager._invalidate_cache(dog_id)

    def _fire_health_update_event(self, dog_id: str, updated: list[str]) -> None:
        """Fire health data updated event."""
        self.hass.bus.async_fire(
            f"{DOMAIN}_health_data_updated",
            {
                ATTR_DOG_ID: dog_id,
                "updated_fields": updated,
                "timestamp": dt_util.utcnow().isoformat(),
            },
        )

    @service_handler(require_dog=True, cache_priority=9, timeout=8.0)
    async def _handle_feed_with_medication(
        self, call: ServiceCall, dog_id: str, runtime_data: PawControlRuntimeData
    ) -> None:
        """Handle feed_with_medication service."""
        medication_name = call.data.get("medication_name", "Scheduled Medication")
        dosage = call.data.get("dosage", "As prescribed")
        auto_calculate = call.data.get("auto_calculate_portion", True)
        timing = call.data.get("medication_timing", "optimal")
        notes = call.data.get("notes", "")

        feeding_manager = runtime_data.get("feeding_manager")
        if not feeding_manager:
            raise ServiceValidationError("Feeding manager not available")

        try:
            # Calculate appropriate portion for medication
            config = feeding_manager._configs.get(dog_id)
            if not config:
                raise ServiceValidationError("No feeding configuration found")

            if auto_calculate:
                # Use smaller portion for medication timing
                portion_size = (
                    config.calculate_portion_size() * 0.3
                )  # 30% of normal portion
            else:
                portion_size = (
                    config.calculate_portion_size() * 0.5
                )  # 50% of normal portion

            # Prepare medication data
            medication_data = {
                "name": medication_name,
                "dose": dosage,
                "time": timing,
                "administered_at": dt_util.utcnow().isoformat(),
            }

            # Create combined notes
            med_notes = f"Medication: {medication_name} ({dosage}) - {timing} timing"
            if notes:
                med_notes += f" - {notes}"

            # Add feeding event
            feeding_event = await feeding_manager.async_add_feeding(
                dog_id=dog_id,
                amount=portion_size,
                meal_type="snack",  # Medication meals are typically small
                notes=med_notes,
                feeder="medication_service",
                scheduled=True,
            )

            # Log medication in health data
            data_manager = runtime_data.get("data_manager")
            if data_manager:
                await data_manager.async_log_health(
                    dog_id,
                    {
                        "type": "medication",
                        "medication_name": medication_name,
                        "dosage": dosage,
                        "given_with_food": True,
                        "food_amount": portion_size,
                        **medication_data,
                    },
                )

            # Fire medication feeding event
            self.hass.bus.async_fire(
                f"{DOMAIN}_medication_feeding_logged",
                {
                    ATTR_DOG_ID: dog_id,
                    "medication_name": medication_name,
                    "dosage": dosage,
                    "portion_size": portion_size,
                    "timing": timing,
                    "timestamp": feeding_event.time.isoformat(),
                },
            )

            _LOGGER.info(
                "Medication feeding logged for %s: %s (%s)",
                dog_id,
                medication_name,
                dosage,
            )

        except Exception as err:
            _LOGGER.error("Medication feeding failed for %s: %s", dog_id, err)
            raise ServiceValidationError(f"Medication feeding failed: {err}") from err

        # Update coordinator with high priority
        coordinator = runtime_data["coordinator"]
        await coordinator.async_request_selective_refresh([dog_id], priority=9)

    def get_cache_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics
        """
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (
            (self._cache_hits / total_requests * 100) if total_requests > 0 else 0
        )

        return {
            "cache_entries": len(self._runtime_cache),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": round(hit_rate, 1),
            "registered_services": len(self._registered_services),
        }


async def async_setup_daily_reset_scheduler(
    hass: HomeAssistant,
    entry: ConfigEntry,  # noqa: F821
) -> None:
    """Setup daily reset scheduler with optimized timing.

    Args:
        hass: Home Assistant instance
        entry: Config entry
    """
    reset_time_str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)

    try:
        # Parse reset time
        hour, minute, second = map(int, reset_time_str.split(":"))

        # Schedule daily reset
        @callback
        def daily_reset(_) -> None:
            """Perform daily reset."""
            hass.async_create_task(
                hass.services.async_call(
                    DOMAIN,
                    SERVICE_DAILY_RESET,
                    {"force": False},
                    blocking=False,
                )
            )

        # Register time trigger with correct import
        async_track_time_change(
            hass,
            daily_reset,
            hour=hour,
            minute=minute,
            second=second,
        )

        _LOGGER.info("Daily reset scheduled at %s", reset_time_str)

    except Exception as err:
        _LOGGER.error("Failed to setup daily reset: %s", err)
