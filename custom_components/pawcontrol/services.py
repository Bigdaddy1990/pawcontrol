"""Home Assistant services for PawControl integration.

Comprehensive service definitions for all PawControl functionality including
feeding management, walk tracking, health monitoring, and notifications.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    CONF_RESET_TIME,
    DEFAULT_RESET_TIME,
    DOMAIN,
    SERVICE_DAILY_RESET,
)

_LOGGER = logging.getLogger(__name__)

# Service names
SERVICE_ADD_FEEDING = "add_feeding"
SERVICE_START_WALK = "start_walk"
SERVICE_END_WALK = "end_walk"
SERVICE_ADD_GPS_POINT = "add_gps_point"
SERVICE_UPDATE_HEALTH = "update_health"
SERVICE_SEND_NOTIFICATION = "send_notification"
SERVICE_ACKNOWLEDGE_NOTIFICATION = "acknowledge_notification"
SERVICE_CALCULATE_PORTION = "calculate_portion"
SERVICE_EXPORT_DATA = "export_data"
SERVICE_ANALYZE_PATTERNS = "analyze_patterns"
SERVICE_GENERATE_REPORT = "generate_report"

# Service schemas
SERVICE_ADD_FEEDING_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("amount"): vol.Coerce(float),
        vol.Optional("meal_type"): cv.string,
        vol.Optional("notes"): cv.string,
        vol.Optional("feeder"): cv.string,
        vol.Optional("scheduled", default=False): cv.boolean,
        vol.Optional("with_medication", default=False): cv.boolean,
        vol.Optional("medication_data"): vol.Schema(
            {
                vol.Optional("name"): cv.string,
                vol.Optional("dose"): cv.string,
                vol.Optional("time"): cv.string,
            }
        ),
    }
)

SERVICE_START_WALK_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Optional("walker"): cv.string,
        vol.Optional("weather"): vol.In(
            ["sunny", "cloudy", "rainy", "snowy", "windy", "hot", "cold"]
        ),
        vol.Optional("leash_used", default=True): cv.boolean,
    }
)

SERVICE_END_WALK_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Optional("notes"): cv.string,
        vol.Optional("dog_weight_kg"): vol.Coerce(float),
    }
)

SERVICE_ADD_GPS_POINT_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("latitude"): vol.Coerce(float),
        vol.Required("longitude"): vol.Coerce(float),
        vol.Optional("altitude"): vol.Coerce(float),
        vol.Optional("accuracy"): vol.Coerce(float),
    }
)

SERVICE_UPDATE_HEALTH_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Optional("weight"): vol.Coerce(float),
        vol.Optional("ideal_weight"): vol.Coerce(float),
        vol.Optional("age_months"): vol.Coerce(int),
        vol.Optional("activity_level"): vol.In(
            ["very_low", "low", "moderate", "high", "very_high"]
        ),
        vol.Optional("body_condition_score"): vol.Range(min=1, max=9),
        vol.Optional("health_conditions"): [cv.string],
        vol.Optional("weight_goal"): vol.In(["maintain", "lose", "gain"]),
    }
)

SERVICE_SEND_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("title"): cv.string,
        vol.Required("message"): cv.string,
        vol.Optional("dog_id"): cv.string,
        vol.Optional("notification_type"): vol.In(
            [
                "feeding_reminder",
                "feeding_overdue",
                "walk_reminder",
                "walk_overdue",
                "health_alert",
                "medication_reminder",
                "veterinary_appointment",
                "weight_check",
                "system_info",
                "system_warning",
                "system_error",
            ]
        ),
        vol.Optional("priority"): vol.In(["low", "normal", "high", "urgent"]),
        vol.Optional("channels"): [
            vol.In(
                [
                    "persistent",
                    "mobile",
                    "email",
                    "sms",
                    "webhook",
                    "tts",
                    "media_player",
                    "slack",
                    "discord",
                ]
            )
        ],
        vol.Optional("expires_in_hours"): vol.Coerce(int),
    }
)

SERVICE_ACKNOWLEDGE_NOTIFICATION_SCHEMA = vol.Schema(
    {
        vol.Required("notification_id"): cv.string,
    }
)

SERVICE_CALCULATE_PORTION_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("meal_type"): cv.string,
        vol.Optional("override_health_data"): vol.Schema(
            {
                vol.Optional("weight"): vol.Coerce(float),
                vol.Optional("activity_level"): cv.string,
                vol.Optional("health_conditions"): [cv.string],
            }
        ),
    }
)

SERVICE_EXPORT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("data_type"): vol.In(["feeding", "walks", "health", "all"]),
        vol.Optional("format"): vol.In(["json", "csv", "gpx"]),
        vol.Optional("days"): vol.Coerce(int),
    }
)

SERVICE_ANALYZE_PATTERNS_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("analysis_type"): vol.In(
            ["feeding", "walking", "health", "comprehensive"]
        ),
        vol.Optional("days", default=30): vol.Coerce(int),
    }
)

SERVICE_GENERATE_REPORT_SCHEMA = vol.Schema(
    {
        vol.Required("dog_id"): cv.string,
        vol.Required("report_type"): vol.In(
            ["health", "activity", "nutrition", "comprehensive"]
        ),
        vol.Optional("include_recommendations", default=True): cv.boolean,
        vol.Optional("days", default=30): vol.Coerce(int),
    }
)

SERVICE_DAILY_RESET_SCHEMA = vol.Schema({vol.Optional("entry_id"): cv.string})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up PawControl services.

    Args:
        hass: Home Assistant instance
    """

    async def add_feeding_service(call: ServiceCall) -> None:
        """Handle add feeding service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        dog_id = call.data["dog_id"]
        amount = call.data["amount"]
        meal_type = call.data.get("meal_type")
        notes = call.data.get("notes")
        feeder = call.data.get("feeder")
        scheduled = call.data.get("scheduled", False)
        with_medication = call.data.get("with_medication", False)
        medication_data = call.data.get("medication_data")

        try:
            if with_medication and medication_data:
                await coordinator.feeding_manager.async_add_feeding_with_medication(
                    dog_id=dog_id,
                    amount=amount,
                    meal_type=meal_type,
                    medication_data=medication_data,
                    notes=notes,
                    feeder=feeder,
                )
            else:
                await coordinator.feeding_manager.async_add_feeding(
                    dog_id=dog_id,
                    amount=amount,
                    meal_type=meal_type,
                    notes=notes,
                    feeder=feeder,
                    scheduled=scheduled,
                )

            # Trigger coordinator update
            await coordinator.async_request_refresh()

            _LOGGER.info(
                "Added feeding for %s: %.1fg %s", dog_id, amount, meal_type or "unknown"
            )

        except Exception as e:
            _LOGGER.error("Failed to add feeding for %s: %s", dog_id, e)
            raise

    async def start_walk_service(call: ServiceCall) -> None:
        """Handle start walk service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        dog_id = call.data["dog_id"]
        walker = call.data.get("walker")
        weather = call.data.get("weather")
        leash_used = call.data.get("leash_used", True)

        try:
            # Convert weather string to enum if provided
            weather_enum = None
            if weather:
                from .walk_manager import WeatherCondition

                weather_enum = WeatherCondition(weather)

            session_id = await coordinator.walk_manager.async_start_walk(
                dog_id=dog_id,
                walker=walker,
                weather=weather_enum,
                leash_used=leash_used,
            )

            _LOGGER.info("Started walk for %s (session: %s)", dog_id, session_id)

        except Exception as e:
            _LOGGER.error("Failed to start walk for %s: %s", dog_id, e)
            raise

    async def end_walk_service(call: ServiceCall) -> None:
        """Handle end walk service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        dog_id = call.data["dog_id"]
        notes = call.data.get("notes")
        dog_weight_kg = call.data.get("dog_weight_kg")

        try:
            walk_event = await coordinator.walk_manager.async_end_walk(
                dog_id=dog_id,
                notes=notes,
                dog_weight_kg=dog_weight_kg,
            )

            if walk_event:
                # Trigger coordinator update
                await coordinator.async_request_refresh()

                _LOGGER.info(
                    "Ended walk for %s: %.1f km in %d minutes",
                    dog_id,
                    walk_event.stats.distance_km,
                    walk_event.stats.duration_minutes,
                )
            else:
                _LOGGER.warning("No active walk found for %s", dog_id)

        except Exception as e:
            _LOGGER.error("Failed to end walk for %s: %s", dog_id, e)
            raise

    async def add_gps_point_service(call: ServiceCall) -> None:
        """Handle add GPS point service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        dog_id = call.data["dog_id"]
        latitude = call.data["latitude"]
        longitude = call.data["longitude"]
        altitude = call.data.get("altitude")
        accuracy = call.data.get("accuracy")

        try:
            success = await coordinator.walk_manager.async_add_gps_point(
                dog_id=dog_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                accuracy=accuracy,
            )

            if not success:
                _LOGGER.warning("Failed to add GPS point for %s", dog_id)

        except Exception as e:
            _LOGGER.error("Failed to add GPS point for %s: %s", dog_id, e)
            raise

    async def update_health_service(call: ServiceCall) -> None:
        """Handle update health service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        dog_id = call.data["dog_id"]
        health_data = {
            k: v for k, v in call.data.items() if k != "dog_id" and v is not None
        }

        try:
            success = await coordinator.feeding_manager.async_update_health_data(
                dog_id=dog_id,
                health_data=health_data,
            )

            if success:
                # Trigger coordinator update
                await coordinator.async_request_refresh()

                _LOGGER.info("Updated health data for %s: %s", dog_id, health_data)
            else:
                _LOGGER.warning("Failed to update health data for %s", dog_id)

        except Exception as e:
            _LOGGER.error("Failed to update health data for %s: %s", dog_id, e)
            raise

    async def send_notification_service(call: ServiceCall) -> None:
        """Handle send notification service call."""
        coordinator = hass.data[DOMAIN]["coordinator"]

        title = call.data["title"]
        message = call.data["message"]
        dog_id = call.data.get("dog_id")
        notification_type = call.data.get("notification_type", "system_info")
        priority = call.data.get("priority", "normal")
        channels = call.data.get("channels")
        expires_in_hours = call.data.get("expires_in_hours")

        try:
            # Convert string enums
            from .notifications import (
                NotificationChannel,
                NotificationPriority,
                NotificationType,
            )

            notification_type_enum = NotificationType(notification_type)
            priority_enum = NotificationPriority(priority)

            channel_enums = None
            if channels:
                channel_enums = [NotificationChannel(channel) for channel in channels]

            expires_in = None
            if expires_in_hours:
                expires_in = timedelta(hours=expires_in_hours)

            notification_id = (
                await coordinator.notification_manager.async_send_notification(
                    notification_type=notification_type_enum,
                    title=title,
                    message=message,
                    dog_id=dog_id,
                    priority=priority_enum,
                    expires_in=expires_in,
                    force_channels=channel_enums,
                )
            )

            _LOGGER.info("Sent notification %s: %s", notification_id, title)

        except Exception as e:
            _LOGGER.error("Failed to send notification: %s", e)
            raise

    async def daily_reset_service(call: ServiceCall) -> None:
        """Trigger a manual daily reset."""

        entry_id = call.data.get("entry_id")
        target_entry: ConfigEntry | None = None
        if entry_id:
            target_entry = hass.config_entries.async_get_entry(entry_id)

        if target_entry is None:
            entries = hass.config_entries.async_entries(DOMAIN)
            target_entry = entries[0] if entries else None

        if target_entry is None:
            _LOGGER.warning(
                "Daily reset requested but no PawControl entries are loaded"
            )
            return

        await _perform_daily_reset(hass, target_entry)

    # Register all services
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_FEEDING,
        add_feeding_service,
        schema=SERVICE_ADD_FEEDING_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_WALK,
        start_walk_service,
        schema=SERVICE_START_WALK_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_END_WALK,
        end_walk_service,
        schema=SERVICE_END_WALK_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_GPS_POINT,
        add_gps_point_service,
        schema=SERVICE_ADD_GPS_POINT_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_HEALTH,
        update_health_service,
        schema=SERVICE_UPDATE_HEALTH_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_NOTIFICATION,
        send_notification_service,
        schema=SERVICE_SEND_NOTIFICATION_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DAILY_RESET,
        daily_reset_service,
        schema=SERVICE_DAILY_RESET_SCHEMA,
    )

    _LOGGER.info("Registered PawControl services")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload PawControl services.

    Args:
        hass: Home Assistant instance
    """
    services_to_remove = [
        SERVICE_ADD_FEEDING,
        SERVICE_START_WALK,
        SERVICE_END_WALK,
        SERVICE_ADD_GPS_POINT,
        SERVICE_UPDATE_HEALTH,
        SERVICE_SEND_NOTIFICATION,
        SERVICE_ACKNOWLEDGE_NOTIFICATION,
        SERVICE_CALCULATE_PORTION,
        SERVICE_EXPORT_DATA,
        SERVICE_ANALYZE_PATTERNS,
        SERVICE_GENERATE_REPORT,
        SERVICE_DAILY_RESET,
    ]

    for service in services_to_remove:
        hass.services.async_remove(DOMAIN, service)

    _LOGGER.info("Unloaded PawControl services")


class PawControlServiceManager:
    """Manage registration of PawControl services."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the service manager and register services when needed."""

        self._hass = hass
        self._services_task: asyncio.Task | None = None

        domain_data = hass.data.setdefault(DOMAIN, {})
        existing: PawControlServiceManager | None = domain_data.get("service_manager")
        if existing is not None:
            self._services_task = existing._services_task
            return

        domain_data["service_manager"] = self

        if not hass.services.has_service(DOMAIN, SERVICE_ADD_FEEDING):
            self._services_task = hass.async_create_task(async_setup_services(hass))

    async def async_shutdown(self) -> None:
        """Unload registered services when the integration is removed."""

        if self._services_task and not self._services_task.done():
            with suppress(asyncio.CancelledError):
                await self._services_task

        await async_unload_services(self._hass)

        domain_data = self._hass.data.get(DOMAIN)
        if domain_data and domain_data.get("service_manager") is self:
            domain_data.pop("service_manager")


async def _perform_daily_reset(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Perform maintenance tasks for the daily reset."""

    runtime_data = getattr(entry, "runtime_data", None)
    if runtime_data is None:
        entry_store = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if isinstance(entry_store, dict):
            runtime_data = entry_store.get("runtime_data")

    if runtime_data is None:
        _LOGGER.debug(
            "Skipping daily reset for entry %s: runtime data unavailable",
            entry.entry_id,
        )
        return

    coordinator = runtime_data["coordinator"]
    walk_manager = runtime_data.get("walk_manager")
    notification_manager = runtime_data.get("notification_manager")

    try:
        if walk_manager and hasattr(walk_manager, "async_cleanup"):
            await walk_manager.async_cleanup()

        if notification_manager and hasattr(
            notification_manager, "async_cleanup_expired_notifications"
        ):
            await notification_manager.async_cleanup_expired_notifications()

        await coordinator.async_request_refresh()

        runtime_data.performance_stats.setdefault("daily_resets", 0)
        runtime_data.performance_stats["daily_resets"] = (
            runtime_data.performance_stats.get("daily_resets", 0) + 1
        )
        _LOGGER.debug("Daily reset completed for entry %s", entry.entry_id)
    except Exception as err:  # pragma: no cover - defensive logging
        _LOGGER.error("Daily reset failed for entry %s: %s", entry.entry_id, err)


async def async_setup_daily_reset_scheduler(
    hass: HomeAssistant, entry: ConfigEntry
) -> Callable[[], None] | None:
    """Schedule the daily reset based on the configured reset time."""

    reset_time_str = entry.options.get(CONF_RESET_TIME, DEFAULT_RESET_TIME)
    reset_time = dt_util.parse_time(reset_time_str)
    if reset_time is None:
        _LOGGER.warning(
            "Invalid reset time '%s', falling back to default '%s'",
            reset_time_str,
            DEFAULT_RESET_TIME,
        )
        reset_time = dt_util.parse_time(DEFAULT_RESET_TIME)

    if reset_time is None:
        return None

    domain_data = hass.data.setdefault(DOMAIN, {})
    existing = domain_data.get(entry.entry_id, {})
    if isinstance(existing, dict) and (unsub := existing.get("daily_reset_unsub")):
        try:
            unsub()
        except Exception as err:  # pragma: no cover - best effort cleanup
            _LOGGER.debug("Failed to cancel previous daily reset listener: %s", err)

    async def _async_run_reset() -> None:
        await _perform_daily_reset(hass, entry)

    @callback
    def _scheduled_reset(_: datetime | None = None) -> None:
        hass.async_create_task(_async_run_reset())

    unsubscribe = async_track_time_change(
        hass,
        _scheduled_reset,
        hour=reset_time.hour,
        minute=reset_time.minute,
        second=reset_time.second,
    )

    entry.async_on_unload(unsubscribe)
    return unsubscribe
