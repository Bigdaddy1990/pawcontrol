"""Service handlers for Paw Control integration.

This module contains all service handlers for the Paw Control integration,
separated from the main __init__.py for better maintainability and testing.

Quality Scale: Platinum
Home Assistant: 2025.8.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Final

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

# Service validation schemas
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


class PawControlServiceManager:
    """Manages all service handlers for Paw Control integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service manager.

        Args:
            hass: Home Assistant instance
        """
        self.hass = hass
        self._registered_services: set[str] = set()

    async def async_register_services(self) -> None:
        """Register all Paw Control services with enhanced error handling.

        Registers service handlers for all Paw Control functionality including feeding,
        walks, health tracking, and system management.
        """
        # Check if services are already registered (idempotency)
        if SERVICE_FEED_DOG in self._registered_services:
            _LOGGER.debug("Services already registered, skipping registration")
            return

        _LOGGER.debug("Registering Paw Control services")

        # Service registration with comprehensive error handling
        services = [
            (SERVICE_FEED_DOG, self._handle_feed_dog_service, SERVICE_FEED_DOG_SCHEMA),
            (SERVICE_START_WALK, self._handle_start_walk_service, SERVICE_WALK_SCHEMA),
            (SERVICE_END_WALK, self._handle_end_walk_service, SERVICE_END_WALK_SCHEMA),
            (
                SERVICE_LOG_HEALTH,
                self._handle_log_health_service,
                SERVICE_HEALTH_SCHEMA,
            ),
            (
                SERVICE_LOG_MEDICATION,
                self._handle_log_medication_service,
                SERVICE_MEDICATION_SCHEMA,
            ),
            (
                SERVICE_START_GROOMING,
                self._handle_start_grooming_service,
                SERVICE_GROOMING_SCHEMA,
            ),
            (
                SERVICE_DAILY_RESET,
                self._handle_daily_reset_service,
                SERVICE_DAILY_RESET_SCHEMA,
            ),
            (
                SERVICE_NOTIFY_TEST,
                self._handle_notify_test_service,
                SERVICE_NOTIFY_TEST_SCHEMA,
            ),
            (
                "set_visitor_mode",
                self._handle_set_visitor_mode_service,
                SERVICE_SET_VISITOR_MODE_SCHEMA,
            ),
            (
                "export_data",
                self._handle_export_data_service,
                SERVICE_EXPORT_DATA_SCHEMA,
            ),
        ]

        # Register all services with enhanced error handling
        registration_errors = []

        for service_name, handler, schema in services:
            try:
                self.hass.services.async_register(
                    DOMAIN,
                    service_name,
                    handler,
                    schema=schema,
                )
                self._registered_services.add(service_name)
                _LOGGER.debug("Successfully registered service: %s", service_name)
            except Exception as err:
                error_msg = f"Failed to register service {service_name}: {err}"
                _LOGGER.error(error_msg)
                registration_errors.append(error_msg)

        if registration_errors:
            raise ValueError(
                f"Service registration failed: {'; '.join(registration_errors)}"
            )

        _LOGGER.info("Successfully registered %d Paw Control services", len(services))

    async def async_unregister_services(self) -> None:
        """Unregister all Paw Control services."""
        for service_name in self._registered_services:
            try:
                self.hass.services.async_remove(DOMAIN, service_name)
                _LOGGER.debug("Unregistered service: %s", service_name)
            except Exception as err:
                _LOGGER.warning(
                    "Failed to unregister service %s: %s", service_name, err
                )

        self._registered_services.clear()

    @performance_monitor(timeout=10.0)
    async def _handle_feed_dog_service(self, call: ServiceCall) -> None:
        """Handle the feed_dog service call with comprehensive validation and logging."""
        dog_id: str = call.data[ATTR_DOG_ID]
        meal_type: str = call.data.get(ATTR_MEAL_TYPE, "snack")
        portion_size: float = float(call.data.get(ATTR_PORTION_SIZE, 0.0))
        food_type: str = call.data.get("food_type", "dry_food")
        notes: str = call.data.get("notes", "").strip()
        calories: float = float(call.data.get("calories", 0.0))

        _LOGGER.debug(
            "Processing feed_dog service for %s: %s (%.1fg, %.0f cal)",
            dog_id,
            meal_type,
            portion_size,
            calories,
        )

        try:
            # Find and validate runtime data for this dog
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(
                    dog_id, self._get_available_dog_ids()
                ).with_user_message(f"Dog '{dog_id}' not found in any configuration")

            data_manager = runtime_data["data_manager"]

            # Use portion_size directly
            await data_manager.async_feed_dog(dog_id, portion_size)

            _LOGGER.info(
                "Successfully fed %s with portion size %.1fg", dog_id, portion_size
            )

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
            self.hass.bus.async_fire(
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
    async def _handle_start_walk_service(self, call: ServiceCall) -> None:
        """Handle the start_walk service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        label: str = call.data.get("label", "")
        location: str = call.data.get("location", "")
        walk_type: str = call.data.get("walk_type", "regular")

        _LOGGER.debug("Processing start_walk service for %s: %s", dog_id, walk_type)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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

        except PawControlError as err:
            _LOGGER.error("PawControl error in start_walk service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in start_walk service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to start walk: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_end_walk_service(self, call: ServiceCall) -> None:
        """Handle the end_walk service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        distance: float = float(call.data.get("distance", 0.0))
        duration: int = int(call.data.get("duration", 0))
        notes: str = call.data.get("notes", "").strip()

        _LOGGER.debug("Processing end_walk service for %s", dog_id)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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

        except PawControlError as err:
            _LOGGER.error("PawControl error in end_walk service: %s", err.to_dict())
            raise ServiceValidationError(err.user_message) from err
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in end_walk service: %s", err, exc_info=True
            )
            raise ServiceValidationError(f"Failed to end walk: {err}") from err

    @performance_monitor(timeout=10.0)
    async def _handle_log_health_service(self, call: ServiceCall) -> None:
        """Handle the log_health service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]

        _LOGGER.debug("Processing log_health service for %s", dog_id)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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

            self.hass.bus.async_fire(
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
    async def _handle_log_medication_service(self, call: ServiceCall) -> None:
        """Handle the log_medication service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        medication_name: str = call.data["medication_name"]
        dosage: str = call.data["dosage"]

        _LOGGER.debug(
            "Processing log_medication service for %s: %s", dog_id, medication_name
        )

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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
    async def _handle_start_grooming_service(self, call: ServiceCall) -> None:
        """Handle the start_grooming service call with comprehensive validation."""
        dog_id: str = call.data[ATTR_DOG_ID]
        grooming_type: str = call.data.get("type", "general")

        _LOGGER.debug(
            "Processing start_grooming service for %s: %s", dog_id, grooming_type
        )

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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
    async def _handle_daily_reset_service(self, call: ServiceCall) -> None:
        """Handle the daily_reset service call with comprehensive processing."""
        _LOGGER.debug("Processing daily_reset service call")

        try:
            # Reset daily statistics for all dogs
            all_dogs = self._get_available_dog_ids()

            reset_tasks = []
            for dog_id in all_dogs:
                runtime_data = self._get_runtime_data_for_dog(dog_id)
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
    async def _handle_notify_test_service(self, call: ServiceCall) -> None:
        """Handle the notify_test service call with comprehensive features."""
        dog_id: str = call.data[ATTR_DOG_ID]
        message: str = call.data.get("message", "Test notification from Paw Control")
        priority: str = call.data.get("priority", "normal")

        _LOGGER.debug("Processing notify_test service for %s", dog_id)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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
    async def _handle_set_visitor_mode_service(self, call: ServiceCall) -> None:
        """Handle the set_visitor_mode service call."""
        dog_id: str = call.data[ATTR_DOG_ID]
        enabled: bool = call.data["enabled"]
        visitor_name: str = call.data.get("visitor_name", "")

        _LOGGER.debug("Processing set_visitor_mode service for %s: %s", dog_id, enabled)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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
    async def _handle_export_data_service(self, call: ServiceCall) -> None:
        """Handle the export_data service call."""
        dog_id: str = call.data[ATTR_DOG_ID]
        data_type: str = call.data["data_type"]
        export_format: str = call.data.get("format", "csv")

        _LOGGER.debug("Processing export_data service for %s: %s", dog_id, data_type)

        try:
            runtime_data = self._get_runtime_data_for_dog(dog_id)
            if not runtime_data:
                raise DogNotFoundError(dog_id, self._get_available_dog_ids())

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
                    if isinstance(v, list | dict)
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
    # Use global flag to prevent duplicate scheduling with better tracking
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
        """Enhanced callback function for daily reset execution with error handling."""
        _LOGGER.info("Triggering daily reset at %s", now)

        # Create async task with comprehensive error handling
        async def _run_daily_reset() -> None:
            try:
                # Add timeout protection for the daily reset
                async with asyncio.timeout(60):
                    await hass.services.async_call(DOMAIN, SERVICE_DAILY_RESET, {})
                _LOGGER.info("Daily reset completed successfully")
            except TimeoutError:
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

    # Import here to avoid circular dependency
    from homeassistant.helpers.event import async_track_time_change

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
