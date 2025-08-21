"""Notification management for Paw Control integration.

This module provides comprehensive notification handling including smart alerts,
priority management, quiet hours, and multiple delivery methods. It manages
all dog-related notifications and ensures users receive timely and relevant
information about their pets' needs and status.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    ATTR_DOG_ID,
    ATTR_DOG_NAME,
    DOMAIN,
    SERVICE_NOTIFY_TEST,
)
from .exceptions import NotificationError
from .utils import is_within_quiet_hours

_LOGGER = logging.getLogger(__name__)

# Type aliases
NotificationData = Dict[str, Any]
AlertConfig = Dict[str, Any]

# Notification priorities
PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_URGENT = "urgent"

# Notification types
NOTIFICATION_FEEDING = "feeding"
NOTIFICATION_WALK = "walk"
NOTIFICATION_HEALTH = "health"
NOTIFICATION_GPS = "gps"
NOTIFICATION_GROOMING = "grooming"
NOTIFICATION_SYSTEM = "system"

# Delivery methods
DELIVERY_PERSISTENT = "persistent"
DELIVERY_MOBILE_APP = "mobile_app"
DELIVERY_EMAIL = "email"
DELIVERY_TTS = "tts"
DELIVERY_WEBHOOK = "webhook"


class PawControlNotificationManager:
    """Manages all notifications for Paw Control integration.
    
    Handles smart notification scheduling, priority management, quiet hours,
    and multiple delivery methods to ensure users receive timely and relevant
    information about their dogs' needs and status.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize the notification manager.
        
        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id
        
        # Notification state tracking
        self._active_notifications: Dict[str, NotificationData] = {}
        self._notification_history: List[NotificationData] = []
        self._rate_limits: Dict[str, datetime] = {}
        self._suppressed_notifications: Set[str] = set()
        
        # Configuration
        self._global_enabled = True
        self._default_priority = PRIORITY_NORMAL
        self._quiet_hours_start = "22:00"
        self._quiet_hours_end = "08:00"
        self._delivery_methods = [DELIVERY_PERSISTENT]
        
        # Dog-specific settings
        self._dog_settings: Dict[str, AlertConfig] = {}
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

    async def async_initialize(self) -> None:
        """Initialize the notification manager."""
        _LOGGER.debug("Initializing notification manager for entry %s", self.entry_id)
        
        # Start periodic cleanup of old notifications
        self._cleanup_task = async_track_time_interval(
            self.hass,
            self._cleanup_old_notifications,
            timedelta(hours=1)
        )
        
        # Register services
        await self._register_services()
        
        _LOGGER.info("Notification manager initialized successfully")

    async def async_shutdown(self) -> None:
        """Shutdown the notification manager."""
        _LOGGER.debug("Shutting down notification manager")
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task()
        
        # Clear active notifications
        for notification_id in list(self._active_notifications.keys()):
            await self.async_dismiss_notification(notification_id)
        
        _LOGGER.info("Notification manager shutdown complete")

    async def async_send_notification(
        self,
        dog_id: str,
        notification_type: str,
        message: str,
        *,
        title: Optional[str] = None,
        priority: str = PRIORITY_NORMAL,
        data: Optional[Dict[str, Any]] = None,
        delivery_methods: Optional[List[str]] = None,
        force: bool = False,
    ) -> bool:
        """Send a notification for a specific dog.
        
        Args:
            dog_id: Dog identifier
            notification_type: Type of notification
            message: Notification message
            title: Optional notification title
            priority: Notification priority
            data: Additional notification data
            delivery_methods: Specific delivery methods to use
            force: Force sending even if rate limited or in quiet hours
            
        Returns:
            True if notification was sent successfully
        """
        try:
            # Check if notifications are globally enabled
            if not self._global_enabled and not force:
                _LOGGER.debug("Notifications globally disabled, skipping")
                return False
            
            # Check dog-specific settings
            dog_settings = self._dog_settings.get(dog_id, {})
            if not dog_settings.get("notifications_enabled", True) and not force:
                _LOGGER.debug("Notifications disabled for dog %s", dog_id)
                return False
            
            # Check notification type settings
            type_enabled = dog_settings.get(f"{notification_type}_alerts", True)
            if not type_enabled and not force:
                _LOGGER.debug("%s notifications disabled for dog %s", notification_type, dog_id)
                return False
            
            # Check quiet hours
            if not force and self._is_in_quiet_hours() and priority not in [PRIORITY_HIGH, PRIORITY_URGENT]:
                _LOGGER.debug("In quiet hours, suppressing %s priority notification", priority)
                return False
            
            # Check rate limiting
            rate_limit_key = f"{dog_id}_{notification_type}"
            if not force and self._is_rate_limited(rate_limit_key, priority):
                _LOGGER.debug("Rate limited notification for %s", rate_limit_key)
                return False
            
            # Generate notification ID
            notification_id = f"pawcontrol_{dog_id}_{notification_type}_{int(dt_util.utcnow().timestamp())}"
            
            # Get dog name for better messaging
            dog_name = await self._get_dog_name(dog_id)
            
            # Prepare notification data
            notification_data = {
                "id": notification_id,
                "dog_id": dog_id,
                "dog_name": dog_name,
                "type": notification_type,
                "priority": priority,
                "title": title or self._generate_title(dog_name, notification_type, priority),
                "message": message,
                "timestamp": dt_util.utcnow(),
                "data": data or {},
            }
            
            # Determine delivery methods
            methods = delivery_methods or self._get_delivery_methods(dog_id, notification_type, priority)
            
            # Send via each delivery method
            success = False
            for method in methods:
                if await self._send_via_method(method, notification_data):
                    success = True
            
            if success:
                # Track notification
                self._active_notifications[notification_id] = notification_data
                self._notification_history.append(notification_data)
                
                # Update rate limit
                self._rate_limits[rate_limit_key] = dt_util.utcnow()
                
                _LOGGER.info(
                    "Sent %s notification for dog %s: %s",
                    priority,
                    dog_name,
                    message
                )
            
            return success
            
        except Exception as err:
            _LOGGER.error("Failed to send notification: %s", err)
            raise NotificationError(notification_type, str(err)) from err

    async def async_send_feeding_reminder(
        self,
        dog_id: str,
        hours_since_last: float,
        next_feeding_due: Optional[str] = None
    ) -> bool:
        """Send a feeding reminder notification.
        
        Args:
            dog_id: Dog identifier
            hours_since_last: Hours since last feeding
            next_feeding_due: When next feeding is due
            
        Returns:
            True if notification was sent
        """
        dog_name = await self._get_dog_name(dog_id)
        
        # Determine priority based on how long it's been
        if hours_since_last > 12:
            priority = PRIORITY_HIGH
            message = f"{dog_name} hasn't been fed in {hours_since_last:.1f} hours! Please feed soon."
        elif hours_since_last > 8:
            priority = PRIORITY_NORMAL
            message = f"{dog_name} is due for feeding. Last fed {hours_since_last:.1f} hours ago."
        else:
            priority = PRIORITY_LOW
            message = f"Feeding reminder for {dog_name}."
        
        if next_feeding_due:
            message += f" Next feeding due: {next_feeding_due}"
        
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_FEEDING,
            message,
            priority=priority,
            data={
                "hours_since_last": hours_since_last,
                "next_feeding_due": next_feeding_due,
            }
        )

    async def async_send_walk_reminder(
        self,
        dog_id: str,
        hours_since_last: float,
        walks_today: int = 0
    ) -> bool:
        """Send a walk reminder notification.
        
        Args:
            dog_id: Dog identifier
            hours_since_last: Hours since last walk
            walks_today: Number of walks today
            
        Returns:
            True if notification was sent
        """
        dog_name = await self._get_dog_name(dog_id)
        
        # Determine priority and message based on context
        if hours_since_last > 12:
            priority = PRIORITY_HIGH
            message = f"{dog_name} needs a walk urgently! Last walk was {hours_since_last:.1f} hours ago."
        elif hours_since_last > 8:
            priority = PRIORITY_NORMAL
            message = f"{dog_name} is due for a walk. Last walk was {hours_since_last:.1f} hours ago."
        elif walks_today == 0:
            priority = PRIORITY_NORMAL
            message = f"{dog_name} hasn't been walked today yet."
        else:
            priority = PRIORITY_LOW
            message = f"Walk reminder for {dog_name}."
        
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_WALK,
            message,
            priority=priority,
            data={
                "hours_since_last": hours_since_last,
                "walks_today": walks_today,
            }
        )

    async def async_send_health_alert(
        self,
        dog_id: str,
        alert_type: str,
        details: str,
        severity: str = "medium"
    ) -> bool:
        """Send a health alert notification.
        
        Args:
            dog_id: Dog identifier
            alert_type: Type of health alert
            details: Alert details
            severity: Alert severity (low, medium, high, critical)
            
        Returns:
            True if notification was sent
        """
        dog_name = await self._get_dog_name(dog_id)
        
        # Map severity to priority
        severity_priority_map = {
            "low": PRIORITY_LOW,
            "medium": PRIORITY_NORMAL,
            "high": PRIORITY_HIGH,
            "critical": PRIORITY_URGENT,
        }
        priority = severity_priority_map.get(severity, PRIORITY_NORMAL)
        
        # Generate message based on alert type
        alert_messages = {
            "weight_change": f"{dog_name}'s weight has changed significantly.",
            "medication_due": f"Medication is due for {dog_name}.",
            "vet_checkup": f"Vet checkup is due for {dog_name}.",
            "activity_concern": f"Activity level concern for {dog_name}.",
            "health_status": f"Health status alert for {dog_name}.",
        }
        
        message = alert_messages.get(alert_type, f"Health alert for {dog_name}")
        if details:
            message += f" {details}"
        
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_HEALTH,
            message,
            priority=priority,
            data={
                "alert_type": alert_type,
                "severity": severity,
                "details": details,
            }
        )

    async def async_send_gps_alert(
        self,
        dog_id: str,
        alert_type: str,
        location_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send a GPS/location alert notification.
        
        Args:
            dog_id: Dog identifier
            alert_type: Type of GPS alert
            location_info: Location information
            
        Returns:
            True if notification was sent
        """
        dog_name = await self._get_dog_name(dog_id)
        
        # Generate message based on alert type
        if alert_type == "left_home":
            message = f"{dog_name} has left home."
            priority = PRIORITY_NORMAL
        elif alert_type == "arrived_home":
            message = f"{dog_name} has arrived home."
            priority = PRIORITY_LOW
        elif alert_type == "outside_safe_zone":
            message = f"{dog_name} is outside the safe zone!"
            priority = PRIORITY_HIGH
        elif alert_type == "gps_battery_low":
            message = f"GPS tracker battery is low for {dog_name}."
            priority = PRIORITY_NORMAL
        elif alert_type == "gps_signal_lost":
            message = f"GPS signal lost for {dog_name}."
            priority = PRIORITY_HIGH
        else:
            message = f"Location alert for {dog_name}."
            priority = PRIORITY_NORMAL
        
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_GPS,
            message,
            priority=priority,
            data={
                "alert_type": alert_type,
                "location_info": location_info or {},
            }
        )

    async def async_send_grooming_reminder(
        self,
        dog_id: str,
        grooming_type: str,
        days_overdue: int = 0
    ) -> bool:
        """Send a grooming reminder notification.
        
        Args:
            dog_id: Dog identifier
            grooming_type: Type of grooming needed
            days_overdue: Number of days overdue
            
        Returns:
            True if notification was sent
        """
        dog_name = await self._get_dog_name(dog_id)
        
        if days_overdue > 7:
            priority = PRIORITY_HIGH
            message = f"{dog_name} is {days_overdue} days overdue for {grooming_type}!"
        elif days_overdue > 0:
            priority = PRIORITY_NORMAL
            message = f"{dog_name} is {days_overdue} days overdue for {grooming_type}."
        else:
            priority = PRIORITY_LOW
            message = f"{dog_name} is due for {grooming_type}."
        
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_GROOMING,
            message,
            priority=priority,
            data={
                "grooming_type": grooming_type,
                "days_overdue": days_overdue,
            }
        )

    async def async_send_test_notification(
        self,
        dog_id: str,
        message: str = "Test notification",
        priority: str = PRIORITY_NORMAL
    ) -> bool:
        """Send a test notification.
        
        Args:
            dog_id: Dog identifier
            message: Test message
            priority: Notification priority
            
        Returns:
            True if notification was sent
        """
        return await self.async_send_notification(
            dog_id,
            NOTIFICATION_SYSTEM,
            message,
            title="Paw Control Test",
            priority=priority,
            force=True  # Always send test notifications
        )

    async def async_dismiss_notification(self, notification_id: str) -> bool:
        """Dismiss an active notification.
        
        Args:
            notification_id: Notification ID to dismiss
            
        Returns:
            True if notification was dismissed
        """
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
            _LOGGER.error("Failed to dismiss notification %s: %s", notification_id, err)
            return False

    async def async_configure_dog_notifications(
        self,
        dog_id: str,
        settings: AlertConfig
    ) -> None:
        """Configure notification settings for a specific dog.
        
        Args:
            dog_id: Dog identifier
            settings: Notification settings
        """
        self._dog_settings[dog_id] = settings
        _LOGGER.debug("Updated notification settings for dog %s", dog_id)

    async def async_set_global_settings(
        self,
        enabled: bool = True,
        default_priority: str = PRIORITY_NORMAL,
        quiet_hours_start: str = "22:00",
        quiet_hours_end: str = "08:00",
        delivery_methods: Optional[List[str]] = None
    ) -> None:
        """Set global notification settings.
        
        Args:
            enabled: Whether notifications are globally enabled
            default_priority: Default notification priority
            quiet_hours_start: Quiet hours start time
            quiet_hours_end: Quiet hours end time
            delivery_methods: Default delivery methods
        """
        self._global_enabled = enabled
        self._default_priority = default_priority
        self._quiet_hours_start = quiet_hours_start
        self._quiet_hours_end = quiet_hours_end
        
        if delivery_methods:
            self._delivery_methods = delivery_methods
        
        _LOGGER.debug("Updated global notification settings")

    def get_active_notifications(self, dog_id: Optional[str] = None) -> List[NotificationData]:
        """Get active notifications.
        
        Args:
            dog_id: Optional filter by dog ID
            
        Returns:
            List of active notifications
        """
        notifications = list(self._active_notifications.values())
        
        if dog_id:
            notifications = [n for n in notifications if n["dog_id"] == dog_id]
        
        return notifications

    def get_notification_history(
        self,
        dog_id: Optional[str] = None,
        limit: int = 50
    ) -> List[NotificationData]:
        """Get notification history.
        
        Args:
            dog_id: Optional filter by dog ID
            limit: Maximum number of notifications to return
            
        Returns:
            List of historical notifications
        """
        notifications = self._notification_history.copy()
        
        if dog_id:
            notifications = [n for n in notifications if n["dog_id"] == dog_id]
        
        # Sort by timestamp (most recent first) and apply limit
        notifications.sort(key=lambda x: x["timestamp"], reverse=True)
        return notifications[:limit]

    async def _get_dog_name(self, dog_id: str) -> str:
        """Get the display name for a dog.
        
        Args:
            dog_id: Dog identifier
            
        Returns:
            Dog display name
        """
        # Try to get dog name from coordinator or data manager
        try:
            entry_data = self.hass.data[DOMAIN][self.entry_id]
            coordinator = entry_data.get("coordinator")
            
            if coordinator:
                dog_data = coordinator.get_dog_data(dog_id)
                if dog_data and "dog_info" in dog_data:
                    return dog_data["dog_info"].get("dog_name", dog_id)
        except Exception:
            pass
        
        return dog_id

    def _generate_title(self, dog_name: str, notification_type: str, priority: str) -> str:
        """Generate a notification title.
        
        Args:
            dog_name: Dog name
            notification_type: Type of notification
            priority: Notification priority
            
        Returns:
            Generated title
        """
        priority_prefixes = {
            PRIORITY_URGENT: "🚨 URGENT",
            PRIORITY_HIGH: "⚠️ Important",
            PRIORITY_NORMAL: "🐕",
            PRIORITY_LOW: "ℹ️",
        }
        
        prefix = priority_prefixes.get(priority, "🐕")
        type_names = {
            NOTIFICATION_FEEDING: "Feeding",
            NOTIFICATION_WALK: "Walk",
            NOTIFICATION_HEALTH: "Health",
            NOTIFICATION_GPS: "Location",
            NOTIFICATION_GROOMING: "Grooming",
            NOTIFICATION_SYSTEM: "Paw Control",
        }
        
        type_name = type_names.get(notification_type, "Alert")
        return f"{prefix} {type_name} - {dog_name}"

    def _is_in_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours.
        
        Returns:
            True if in quiet hours
        """
        current_time = dt_util.now()
        return is_within_quiet_hours(
            current_time,
            self._quiet_hours_start,
            self._quiet_hours_end
        )

    def _is_rate_limited(self, rate_limit_key: str, priority: str) -> bool:
        """Check if a notification type is rate limited.
        
        Args:
            rate_limit_key: Rate limit key
            priority: Notification priority
            
        Returns:
            True if rate limited
        """
        # Urgent notifications are never rate limited
        if priority == PRIORITY_URGENT:
            return False
        
        if rate_limit_key not in self._rate_limits:
            return False
        
        last_sent = self._rate_limits[rate_limit_key]
        now = dt_util.utcnow()
        
        # Rate limit intervals based on priority
        intervals = {
            PRIORITY_HIGH: timedelta(minutes=15),
            PRIORITY_NORMAL: timedelta(hours=1),
            PRIORITY_LOW: timedelta(hours=4),
        }
        
        interval = intervals.get(priority, timedelta(hours=1))
        return now - last_sent < interval

    def _get_delivery_methods(
        self,
        dog_id: str,
        notification_type: str,
        priority: str
    ) -> List[str]:
        """Get delivery methods for a notification.
        
        Args:
            dog_id: Dog identifier
            notification_type: Type of notification
            priority: Notification priority
            
        Returns:
            List of delivery methods to use
        """
        # Start with default methods
        methods = self._delivery_methods.copy()
        
        # Get dog-specific overrides
        dog_settings = self._dog_settings.get(dog_id, {})
        dog_methods = dog_settings.get("delivery_methods")
        if dog_methods:
            methods = dog_methods
        
        # Priority-based method selection
        if priority == PRIORITY_URGENT:
            # Use all available methods for urgent notifications
            available_methods = [DELIVERY_PERSISTENT, DELIVERY_MOBILE_APP, DELIVERY_TTS]
            methods.extend([m for m in available_methods if m not in methods])
        
        return methods

    async def _send_via_method(
        self,
        method: str,
        notification_data: NotificationData
    ) -> bool:
        """Send notification via a specific delivery method.
        
        Args:
            method: Delivery method
            notification_data: Notification data
            
        Returns:
            True if sent successfully
        """
        try:
            if method == DELIVERY_PERSISTENT:
                return await self._send_persistent_notification(notification_data)
            elif method == DELIVERY_MOBILE_APP:
                return await self._send_mobile_app_notification(notification_data)
            elif method == DELIVERY_EMAIL:
                return await self._send_email_notification(notification_data)
            elif method == DELIVERY_TTS:
                return await self._send_tts_notification(notification_data)
            elif method == DELIVERY_WEBHOOK:
                return await self._send_webhook_notification(notification_data)
            else:
                _LOGGER.warning("Unknown delivery method: %s", method)
                return False
                
        except Exception as err:
            _LOGGER.error("Failed to send via %s: %s", method, err)
            return False

    async def _send_persistent_notification(self, data: NotificationData) -> bool:
        """Send a persistent notification.
        
        Args:
            data: Notification data
            
        Returns:
            True if sent successfully
        """
        try:
            persistent_notification.async_create(
                self.hass,
                data["message"],
                title=data["title"],
                notification_id=data["id"]
            )
            return True
        except Exception as err:
            _LOGGER.error("Failed to send persistent notification: %s", err)
            return False

    async def _send_mobile_app_notification(self, data: NotificationData) -> bool:
        """Send a mobile app notification.
        
        Args:
            data: Notification data
            
        Returns:
            True if sent successfully
        """
        try:
            # Check if mobile app notification service is available
            if not self.hass.services.has_service("notify", "mobile_app"):
                return False
            
            await self.hass.services.async_call(
                "notify",
                "mobile_app",
                {
                    "title": data["title"],
                    "message": data["message"],
                    "data": {
                        "tag": f"pawcontrol_{data['dog_id']}_{data['type']}",
                        "group": "pawcontrol",
                        "channel": "Paw Control",
                        "importance": "high" if data["priority"] in [PRIORITY_HIGH, PRIORITY_URGENT] else "normal",
                        **data["data"],
                    }
                }
            )
            return True
        except Exception as err:
            _LOGGER.error("Failed to send mobile app notification: %s", err)
            return False

    async def _send_email_notification(self, data: NotificationData) -> bool:
        """Send an email notification.
        
        Args:
            data: Notification data
            
        Returns:
            True if sent successfully
        """
        # Email notifications would require SMTP configuration
        # This is a placeholder implementation
        _LOGGER.debug("Email notification not implemented: %s", data["title"])
        return False

    async def _send_tts_notification(self, data: NotificationData) -> bool:
        """Send a TTS notification.
        
        Args:
            data: Notification data
            
        Returns:
            True if sent successfully
        """
        try:
            # Check if TTS service is available
            if not self.hass.services.has_service("tts", "speak"):
                return False
            
            # Only send urgent and high priority notifications via TTS
            if data["priority"] not in [PRIORITY_HIGH, PRIORITY_URGENT]:
                return False
            
            await self.hass.services.async_call(
                "tts",
                "speak",
                {
                    "message": f"Paw Control alert: {data['message']}",
                    "entity_id": "media_player.all",
                }
            )
            return True
        except Exception as err:
            _LOGGER.error("Failed to send TTS notification: %s", err)
            return False

    async def _send_webhook_notification(self, data: NotificationData) -> bool:
        """Send a webhook notification.
        
        Args:
            data: Notification data
            
        Returns:
            True if sent successfully
        """
        # Webhook notifications would require webhook configuration
        # This is a placeholder implementation
        _LOGGER.debug("Webhook notification not implemented: %s", data["title"])
        return False

    @callback
    async def _cleanup_old_notifications(self, now: datetime) -> None:
        """Clean up old notifications.
        
        Args:
            now: Current time
        """
        try:
            # Remove notifications older than 7 days from history
            cutoff = now - timedelta(days=7)
            self._notification_history = [
                n for n in self._notification_history
                if n["timestamp"] >= cutoff
            ]
            
            # Remove old rate limits
            old_rate_limits = [
                key for key, timestamp in self._rate_limits.items()
                if now - timestamp > timedelta(days=1)
            ]
            for key in old_rate_limits:
                del self._rate_limits[key]
            
            _LOGGER.debug("Cleaned up old notifications and rate limits")
            
        except Exception as err:
            _LOGGER.error("Error during notification cleanup: %s", err)

    async def _register_services(self) -> None:
        """Register notification-related services."""
        
        async def handle_test_notification(call) -> None:
            """Handle test notification service call."""
            dog_id = call.data.get(ATTR_DOG_ID)
            message = call.data.get("message", "Test notification")
            priority = call.data.get("priority", PRIORITY_NORMAL)
            
            if not dog_id:
                _LOGGER.error("Dog ID is required for test notification")
                return
            
            await self.async_send_test_notification(dog_id, message, priority)
        
        # Register the test notification service
        self.hass.services.async_register(
            DOMAIN,
            SERVICE_NOTIFY_TEST,
            handle_test_notification
        )
