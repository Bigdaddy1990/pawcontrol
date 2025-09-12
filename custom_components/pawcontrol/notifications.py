"""Notification management for Paw Control integration.

This module provides comprehensive notification handling including smart alerts,
priority management, quiet hours, and multiple delivery methods. It manages
all dog-related notifications and ensures users receive timely and relevant
information about their pets' needs and status.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
)
from .exceptions import NotificationError
from .utils import is_within_quiet_hours

if TYPE_CHECKING:
    from datetime import datetime

_LOGGER = logging.getLogger(__name__)

# Notification priorities with modern enum-like constants
PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_URGENT = "urgent"

# Notification types with comprehensive coverage
NOTIFICATION_FEEDING = "feeding"
NOTIFICATION_WALK = "walk"
NOTIFICATION_HEALTH = "health"
NOTIFICATION_GPS = "gps"
NOTIFICATION_GROOMING = "grooming"
NOTIFICATION_SYSTEM = "system"
NOTIFICATION_SAFETY = "safety"
NOTIFICATION_MEDICATION = "medication"

# Delivery methods with modern support
DELIVERY_PERSISTENT = "persistent"
DELIVERY_MOBILE_APP = "mobile_app"
DELIVERY_EMAIL = "email"
DELIVERY_TTS = "tts"
DELIVERY_WEBHOOK = "webhook"
DELIVERY_SLACK = "slack"
DELIVERY_DISCORD = "discord"

# Rate limiting intervals by priority
RATE_LIMIT_INTERVALS = {
    PRIORITY_URGENT: timedelta(minutes=0),  # No rate limiting
    PRIORITY_HIGH: timedelta(minutes=15),
    PRIORITY_NORMAL: timedelta(hours=1),
    PRIORITY_LOW: timedelta(hours=4),
}

# Maximum history retention
MAX_HISTORY_DAYS = 30
MAX_HISTORY_COUNT = 1000


class PawControlNotificationManager:
    """Advanced notification management for Paw Control integration.

    Provides intelligent notification handling with priority management,
    rate limiting, quiet hours, multiple delivery methods, and comprehensive
    tracking. Designed for optimal user experience and system performance.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the notification manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Modern async-safe state management
        self._active_notifications: dict[str, dict[str, Any]] = {}
        self._notification_history: list[dict[str, Any]] = []
        self._rate_limits: dict[str, datetime] = {}
        self._suppressed_notifications: set[str] = set()

        # Configuration with sensible defaults
        self._config: dict[str, Any] = {
            "global_enabled": True,
            "default_priority": PRIORITY_NORMAL,
            "quiet_hours_enabled": False,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "08:00",
            "delivery_methods": [DELIVERY_PERSISTENT],
            "rate_limiting_enabled": True,
            "summary_notifications": False,
            "smart_grouping": True,
        }

        # Dog-specific settings
        self._dog_settings: dict[str, dict[str, Any]] = {}

        # Background tasks
        self._cleanup_task: asyncio.Task | None = None
        self._summary_task: asyncio.Task | None = None

        # Performance metrics
        self._metrics: dict[str, Any] = {
            "notifications_sent": 0,
            "notifications_suppressed": 0,
            "delivery_failures": 0,
            "rate_limited_count": 0,
        }

        # Async locks for thread safety
        self._lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Initialize the notification manager with modern async patterns.

        Raises:
            NotificationError: If initialization fails
        """
        _LOGGER.debug(
            "Initializing notification manager for entry %s", self.entry_id)

        try:
            # Load configuration from config entry
            await self._load_configuration()

            # Start background tasks
            await self._start_background_tasks()

            # Register services
            await self._register_services()

            _LOGGER.info("Notification manager initialized successfully")

        except Exception as err:
            _LOGGER.error(
                "Failed to initialize notification manager: %s", err, exc_info=True
            )
            raise NotificationError("initialization", str(err)) from err

    async def async_shutdown(self) -> None:
        """Shutdown the notification manager gracefully."""
        _LOGGER.debug("Shutting down notification manager")

        try:
            # Cancel background tasks
            if self._cleanup_task:
                self._cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._cleanup_task

            if self._summary_task:
                self._summary_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._summary_task

            # Dismiss all active notifications
            async with self._lock:
                for notification_id in list(self._active_notifications.keys()):
                    await self._dismiss_notification_internal(notification_id)

            _LOGGER.info("Notification manager shutdown complete")

        except Exception as err:
            _LOGGER.error(
                "Error during notification manager shutdown: %s", err)

    async def async_send_notification(
        self,
        dog_id: str,
        notification_type: str,
        message: str,
        *,
        title: str | None = None,
        priority: str = PRIORITY_NORMAL,
        data: dict[str, Any] | None = None,
        delivery_methods: list[str] | None = None,
        force: bool = False,
        actions: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Send a notification for a specific dog with comprehensive options.

        Args:
            dog_id: Dog identifier
            notification_type: Type of notification
            message: Notification message
            title: Optional notification title
            priority: Notification priority
            data: Additional notification data
            delivery_methods: Specific delivery methods to use
            force: Force sending even if rate limited or in quiet hours
            actions: Interactive actions for supported platforms

        Returns:
            True if notification was sent successfully

        Raises:
            NotificationError: If sending fails critically
        """
        async with self._lock:
            try:
                # Early validation
                if not self._validate_notification_params(
                    dog_id, notification_type, priority
                ):
                    return False

                # Check global and dog-specific enablement
                if not await self._is_notification_enabled(
                    dog_id, notification_type, force
                ):
                    return False

                # Check quiet hours and rate limiting
                if not force:
                    if await self._should_suppress_notification(
                        dog_id, notification_type, priority
                    ):
                        self._metrics["notifications_suppressed"] += 1
                        return False

                # Generate unique notification ID
                notification_id = self._generate_notification_id(
                    dog_id, notification_type
                )

                # Get dog information
                dog_name = await self._get_dog_name(dog_id)

                # Prepare comprehensive notification data
                notification_data = {
                    "id": notification_id,
                    "dog_id": dog_id,
                    "dog_name": dog_name,
                    "type": notification_type,
                    "priority": priority,
                    "title": title
                    or self._generate_title(dog_name, notification_type, priority),
                    "message": message,
                    "timestamp": dt_util.utcnow(),
                    "data": data or {},
                    "actions": actions or [],
                    "delivery_status": {},
                }

                # Determine delivery methods
                methods = delivery_methods or await self._get_delivery_methods(
                    dog_id, notification_type, priority
                )

                # Send via each delivery method with parallel processing
                delivery_tasks = [
                    self._send_via_method(method, notification_data)
                    for method in methods
                ]

                results = await asyncio.gather(*delivery_tasks, return_exceptions=True)

                # Process delivery results
                successful_deliveries = []
                for method, result in zip(methods, results, strict=False):
                    if isinstance(result, Exception):
                        _LOGGER.error(
                            "Delivery failed for %s: %s", method, result)
                        notification_data["delivery_status"][method] = "failed"
                        self._metrics["delivery_failures"] += 1
                    elif result:
                        successful_deliveries.append(method)
                        notification_data["delivery_status"][method] = "success"
                    else:
                        notification_data["delivery_status"][method] = "skipped"

                success = len(successful_deliveries) > 0

                if success:
                    # Track notification
                    self._active_notifications[notification_id] = notification_data
                    self._notification_history.append(notification_data)

                    # Update rate limiting
                    if self._config["rate_limiting_enabled"]:
                        rate_key = f"{dog_id}_{notification_type}"
                        self._rate_limits[rate_key] = dt_util.utcnow()

                    # Update metrics
                    self._metrics["notifications_sent"] += 1

                    _LOGGER.info(
                        "Sent %s notification for %s via %s: %s",
                        priority,
                        dog_name,
                        ", ".join(successful_deliveries),
                        message,
                    )
                else:
                    _LOGGER.warning(
                        "Failed to send notification for %s via any method", dog_name
                    )

                return success

            except Exception as err:
                _LOGGER.error(
                    "Critical error sending notification: %s", err, exc_info=True
                )
                raise NotificationError(notification_type, str(err)) from err

    async def async_send_test_notification(
        self,
        dog_id: str,
        message: str = "Test notification from Paw Control",
        priority: str = PRIORITY_NORMAL,
    ) -> bool:
        """Send a test notification with comprehensive feature demonstration.

        Args:
            dog_id: Dog identifier
            message: Test message
            priority: Notification priority

        Returns:
            True if notification was sent
        """
        actions = [
            {
                "action": "test_response",
                "title": "Test Response",
                "data": {"dog_id": dog_id, "test": True},
            }
        ]

        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_SYSTEM,
            message,
            title="🧪 Paw Control Test",
            priority=priority,
            actions=actions,
            force=True,  # Always send test notifications
            data={
                "test_timestamp": dt_util.utcnow().isoformat(),
                "test_features": [
                    "priority_handling",
                    "delivery_methods",
                    "interactive_actions",
                    "rich_data",
                ],
            },
        )

    # Private helper methods
    def _get_runtime_data(self) -> dict[str, Any] | None:
        """Get runtime data for the integration using modern HA 2025.8+ approach.

        Returns:
            Runtime data dictionary or None if not available
        """
        try:
            # Try modern runtime_data approach first
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.entry_id == self.entry_id:
                    runtime_data = getattr(entry, "runtime_data", None)
                    if runtime_data:
                        return {
                            "coordinator": runtime_data.get("coordinator"),
                            "data_manager": runtime_data.get("data_manager"),
                            "notifications": runtime_data.get("notification_manager"),
                            "entry": runtime_data.get("config_entry"),
                            "config_entry": runtime_data.get("config_entry"),
                        }

            # Fallback to legacy data storage
            entry_data = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})
            return entry_data if entry_data else None

        except Exception as err:
            _LOGGER.debug("Failed to get runtime data: %s", err)
            return None

    async def _load_configuration(self) -> None:
        """Load configuration from config entry options."""
        try:
            runtime_data = self._get_runtime_data()
            if runtime_data:
                config_entry = runtime_data.get(
                    "entry"
                )  # Use 'entry' instead of 'config_entry'
                if (
                    config_entry
                    and hasattr(config_entry, "options")
                    and config_entry.options
                ):
                    notifications_config = config_entry.options.get(
                        "notifications", {})
                    self._config.update(notifications_config)
                    _LOGGER.debug(
                        "Loaded notification configuration: %s", notifications_config
                    )
        except Exception as err:
            _LOGGER.warning(
                "Failed to load notification configuration: %s", err)

    async def _start_background_tasks(self) -> None:
        """Start background tasks for cleanup and summaries."""
        # Cleanup task every hour
        self._cleanup_task = asyncio.create_task(self._background_cleanup())

        # Summary task if enabled
        if self._config.get("summary_notifications", False):
            self._summary_task = asyncio.create_task(
                self._background_summary())

    async def _background_cleanup(self) -> None:
        """Background task for periodic cleanup."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in background cleanup: %s", err)

    async def _background_summary(self) -> None:
        """Background task for daily summaries."""
        while True:
            try:
                # Wait until 8 AM for daily summary
                now = dt_util.now()
                next_summary = now.replace(
                    hour=8, minute=0, second=0, microsecond=0)
                if next_summary <= now:
                    next_summary += timedelta(days=1)

                wait_seconds = (next_summary - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                # Send daily summary
                await self.async_send_summary_notification("daily")

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in background summary: %s", err)

    async def _cleanup_old_data(self) -> None:
        """Clean up old notifications and rate limits."""
        async with self._lock:
            try:
                now = dt_util.utcnow()

                # Clean notification history
                cutoff = now - timedelta(days=MAX_HISTORY_DAYS)
                original_count = len(self._notification_history)
                self._notification_history = [
                    n for n in self._notification_history if n["timestamp"] >= cutoff
                ]

                # Limit history size
                if len(self._notification_history) > MAX_HISTORY_COUNT:
                    self._notification_history = self._notification_history[
                        -MAX_HISTORY_COUNT:
                    ]

                # Clean rate limits
                old_rate_limits = [
                    key
                    for key, timestamp in self._rate_limits.items()
                    if now - timestamp > timedelta(days=1)
                ]
                for key in old_rate_limits:
                    del self._rate_limits[key]

                # Clean suppressed notifications
                self._suppressed_notifications.clear()

                cleaned_count = original_count - \
                    len(self._notification_history)
                if cleaned_count > 0:
                    _LOGGER.debug(
                        "Cleaned up %d old notifications", cleaned_count)

            except Exception as err:
                _LOGGER.error("Error during cleanup: %s", err)

    def _validate_notification_params(
        self, dog_id: str, notification_type: str, priority: str
    ) -> bool:
        """Validate notification parameters."""
        if not dog_id or not notification_type:
            _LOGGER.error("Dog ID and notification type are required")
            return False

        valid_priorities = {
            PRIORITY_LOW,
            PRIORITY_NORMAL,
            PRIORITY_HIGH,
            PRIORITY_URGENT,
        }
        if priority not in valid_priorities:
            _LOGGER.error("Invalid priority: %s", priority)
            return False

        return True

    async def _is_notification_enabled(
        self, dog_id: str, notification_type: str, force: bool
    ) -> bool:
        """Check if notifications are enabled for dog and type."""
        if force:
            return True

        # Global enablement
        if not self._config.get("global_enabled", True):
            _LOGGER.debug("Notifications globally disabled")
            return False

        # Dog-specific enablement
        dog_settings = self._dog_settings.get(dog_id, {})
        if not dog_settings.get("notifications_enabled", True):
            _LOGGER.debug("Notifications disabled for dog %s", dog_id)
            return False

        # Type-specific enablement
        type_key = f"{notification_type}_alerts"
        if not dog_settings.get(type_key, True):
            _LOGGER.debug(
                "%s notifications disabled for dog %s", notification_type, dog_id
            )
            return False

        return True

    async def _should_suppress_notification(
        self, dog_id: str, notification_type: str, priority: str
    ) -> bool:
        """Check if notification should be suppressed."""
        # Check quiet hours (urgent notifications always go through)
        if priority != PRIORITY_URGENT and self._is_in_quiet_hours():
            _LOGGER.debug(
                "In quiet hours, suppressing %s priority notification", priority
            )
            return True

        # Check rate limiting
        if self._config.get("rate_limiting_enabled", True) and self._is_rate_limited(
            dog_id, notification_type, priority
        ):
            _LOGGER.debug(
                "Rate limited notification for %s_%s", dog_id, notification_type
            )
            self._metrics["rate_limited_count"] += 1
            return True

        return False

    def _is_in_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours."""
        if not self._config.get("quiet_hours_enabled", False):
            return False

        return is_within_quiet_hours(
            dt_util.now(),
            self._config.get("quiet_hours_start", "22:00"),
            self._config.get("quiet_hours_end", "08:00"),
        )

    def _is_rate_limited(
        self, dog_id: str, notification_type: str, priority: str
    ) -> bool:
        """Check if notification is rate limited."""
        if priority == PRIORITY_URGENT:
            return False  # Urgent notifications bypass rate limiting

        rate_key = f"{dog_id}_{notification_type}"
        if rate_key not in self._rate_limits:
            return False

        last_sent = self._rate_limits[rate_key]
        now = dt_util.utcnow()
        interval = RATE_LIMIT_INTERVALS.get(priority, timedelta(hours=1))

        return now - last_sent < interval

    def _generate_notification_id(self, dog_id: str, notification_type: str) -> str:
        """Generate a unique notification ID."""
        timestamp = int(dt_util.utcnow().timestamp())
        return f"pawcontrol_{dog_id}_{notification_type}_{timestamp}"

    async def _get_dog_name(self, dog_id: str) -> str:
        """Get the display name for a dog with fallback."""
        try:
            runtime_data = self._get_runtime_data()
            if runtime_data:
                coordinator = runtime_data.get("coordinator")
                if coordinator:
                    dog_data = coordinator.get_dog_data(dog_id)
                    if dog_data and "dog_info" in dog_data:
                        return dog_data["dog_info"].get("dog_name", dog_id)
        except Exception as err:
            _LOGGER.debug("Could not get dog name for %s: %s", dog_id, err)

        return dog_id.replace("_", " ").title()

    def _generate_title(
        self, dog_name: str, notification_type: str, priority: str
    ) -> str:
        """Generate a notification title with emojis and context."""
        priority_prefixes = {
            PRIORITY_URGENT: "🚨 URGENT",
            PRIORITY_HIGH: "⚠️ Important",
            PRIORITY_NORMAL: "🐕",
            PRIORITY_LOW: "ℹ️",
        }

        type_names = {
            NOTIFICATION_FEEDING: "Feeding",
            NOTIFICATION_WALK: "Walk",
            NOTIFICATION_HEALTH: "Health",
            NOTIFICATION_GPS: "Location",
            NOTIFICATION_GROOMING: "Grooming",
            NOTIFICATION_SAFETY: "Safety",
            NOTIFICATION_MEDICATION: "Medication",
            NOTIFICATION_SYSTEM: "Paw Control",
        }

        prefix = priority_prefixes.get(priority, "🐕")
        type_name = type_names.get(notification_type, "Alert")

        return f"{prefix} {type_name} - {dog_name}"

    async def _get_delivery_methods(
        self, dog_id: str, notification_type: str, priority: str
    ) -> list[str]:
        """Get appropriate delivery methods for notification."""
        # Start with configured default methods
        methods = self._config.get(
            "delivery_methods", [DELIVERY_PERSISTENT]).copy()

        # Get dog-specific overrides
        dog_settings = self._dog_settings.get(dog_id, {})
        dog_methods = dog_settings.get("delivery_methods")
        if dog_methods:
            methods = dog_methods.copy()

        # Priority-based method enhancement
        if priority == PRIORITY_URGENT:
            # Add all available methods for urgent notifications
            urgent_methods = [DELIVERY_PERSISTENT,
                              DELIVERY_MOBILE_APP, DELIVERY_TTS]
            for method in urgent_methods:
                if method not in methods:
                    methods.append(method)
        elif priority == PRIORITY_HIGH:
            # Ensure mobile app notification for high priority
            if DELIVERY_MOBILE_APP not in methods:
                methods.append(DELIVERY_MOBILE_APP)

        return methods

    async def _send_via_method(
        self, method: str, notification_data: dict[str, Any]
    ) -> bool:
        """Send notification via specific delivery method."""
        try:
            if method == DELIVERY_PERSISTENT:
                return await self._send_persistent_notification(notification_data)
            elif method == DELIVERY_MOBILE_APP:
                return await self._send_mobile_app_notification(notification_data)
            else:
                _LOGGER.warning("Unknown delivery method: %s", method)
                return False

        except Exception as err:
            _LOGGER.error("Failed to send via %s: %s", method, err)
            return False

    async def _send_persistent_notification(self, data: dict[str, Any]) -> bool:
        """Send persistent notification with enhanced features."""
        try:
            persistent_notification.async_create(
                self.hass,
                data["message"],
                title=data["title"],
                notification_id=data["id"],
            )
            return True
        except Exception as err:
            _LOGGER.error("Failed to send persistent notification: %s", err)
            return False

    async def _send_mobile_app_notification(self, data: dict[str, Any]) -> bool:
        """Send mobile app notification with interactive features."""
        try:
            # Check for mobile app notification services
            mobile_services = [
                service
                for service in self.hass.services.async_services().get("notify", {})
                if service.startswith("mobile_app_")
            ]

            if not mobile_services:
                return False

            # Prepare notification data with interactive actions
            notification_data = {
                "title": data["title"],
                "message": data["message"],
                "data": {
                    "tag": f"pawcontrol_{data['dog_id']}_{data['type']}",
                    "group": "pawcontrol",
                    "channel": "Paw Control",
                    "importance": "high"
                    if data["priority"] in [PRIORITY_HIGH, PRIORITY_URGENT]
                    else "normal",
                    "notification_icon": "mdi:dog",
                    "actions": data.get("actions", []),
                    **data["data"],
                },
            }

            # Send to all mobile app services
            for service in mobile_services:
                await self.hass.services.async_call(
                    "notify", service, notification_data
                )

            return True

        except Exception as err:
            _LOGGER.error("Failed to send mobile app notification: %s", err)
            return False

    async def _dismiss_notification_internal(self, notification_id: str) -> bool:
        """Internal method to dismiss notification."""
        if notification_id not in self._active_notifications:
            return False

        try:
            # Remove from persistent notifications
            persistent_notification.async_dismiss(self.hass, notification_id)

            # Remove from active notifications
            del self._active_notifications[notification_id]

            _LOGGER.debug("Dismissed notification %s", notification_id)
            return True

        except Exception as err:
            _LOGGER.error("Failed to dismiss notification %s: %s",
                          notification_id, err)
            return False

    async def async_set_dnd_mode(self, dog_id: str, enabled: bool) -> bool:
        """Set do not disturb mode for a specific dog.

        Args:
            dog_id: Dog identifier
            enabled: Whether to enable DND mode

        Returns:
            True if DND mode was set successfully
        """
        try:
            async with self._lock:
                # Get or create dog settings
                if dog_id not in self._dog_settings:
                    self._dog_settings[dog_id] = {}

                # Update DND settings
                self._dog_settings[dog_id].update(
                    {
                        "dnd_enabled": enabled,
                        "dnd_set_at": dt_util.utcnow().isoformat(),
                        "notifications_enabled": not enabled,  # Inverse of DND
                        "feeding_alerts": not enabled,
                        "walk_alerts": not enabled,
                        "health_alerts": True,  # Always keep health alerts
                        "gps_alerts": not enabled,
                    }
                )

                _LOGGER.info(
                    "Do not disturb mode %s for dog %s",
                    "enabled" if enabled else "disabled",
                    dog_id,
                )

                return True

        except Exception as err:
            _LOGGER.error("Failed to set DND mode for %s: %s", dog_id, err)
            return False

    async def async_send_summary_notification(
        self,
        timeframe: str = "daily",
        dogs: list[str] | None = None,
    ) -> bool:
        """Send a summary notification with activity overview."""
        try:
            async with self._lock:
                now = dt_util.utcnow()
                if timeframe == "weekly":
                    start = now - timedelta(days=7)
                    title = "\ud83d\udcc8 Weekly Summary"
                else:
                    start = now - timedelta(days=1)
                    title = "\ud83d\udcca Daily Summary"

                history = [
                    n
                    for n in self._notification_history
                    if n["timestamp"] >= start and (not dogs or n["dog_id"] in dogs)
                ]

                if not history:
                    return False

                counts: dict[str, int] = {}
                for item in history:
                    name = item.get("dog_name", item["dog_id"])
                    counts[name] = counts.get(name, 0) + 1

                message = ", ".join(
                    f"{name}: {count}" for name, count in counts.items()
                )

            return await self.async_send_notification(
                "summary",
                NOTIFICATION_SYSTEM,
                message,
                title=title,
                priority=PRIORITY_LOW,
                force=True,
                data={"timeframe": timeframe, "counts": counts},
            )

        except Exception as err:
            _LOGGER.error("Failed to send summary notification: %s", err)
            return False

    async def _register_services(self) -> None:
        """Register notification-related services."""
        # Note: SERVICE_NOTIFY_TEST is now registered in init.py to avoid conflicts
        # Register summary notification service
        if self.hass.services.has_service(DOMAIN, "send_summary"):
            return

        async def _handle_send_summary(call: ServiceCall) -> None:
            timeframe = call.data.get("timeframe", "daily")
            dogs = call.data.get("dogs")
            await self.async_send_summary_notification(timeframe, dogs)

        self.hass.services.async_register(
            DOMAIN, "send_summary", _handle_send_summary)
