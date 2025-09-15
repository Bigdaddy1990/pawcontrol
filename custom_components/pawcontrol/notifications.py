"""Notification system for PawControl integration.

Comprehensive notification management for feeding reminders, health alerts,
walk notifications, and system events.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Notification constants
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30
NOTIFICATION_EXPIRE_HOURS = 24


class NotificationType(Enum):
    """Types of notifications."""
    
    FEEDING_REMINDER = "feeding_reminder"
    FEEDING_OVERDUE = "feeding_overdue"
    WALK_REMINDER = "walk_reminder"
    WALK_OVERDUE = "walk_overdue"
    HEALTH_ALERT = "health_alert"
    MEDICATION_REMINDER = "medication_reminder"
    VETERINARY_APPOINTMENT = "veterinary_appointment"
    WEIGHT_CHECK = "weight_check"
    SYSTEM_INFO = "system_info"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"


class NotificationPriority(Enum):
    """Notification priority levels."""
    
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(Enum):
    """Available notification channels."""
    
    PERSISTENT = "persistent"  # Home Assistant persistent notifications
    MOBILE = "mobile"          # Mobile app notifications
    EMAIL = "email"            # Email notifications
    SMS = "sms"               # SMS notifications
    WEBHOOK = "webhook"        # Custom webhook
    TTS = "tts"               # Text-to-speech
    MEDIA_PLAYER = "media_player"  # Media player announcements


@dataclass
class NotificationConfig:
    """Configuration for notification delivery."""
    
    enabled: bool = True
    channels: list[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.PERSISTENT])
    priority_threshold: NotificationPriority = NotificationPriority.NORMAL
    quiet_hours: tuple[int, int] | None = None  # (start_hour, end_hour)
    retry_failed: bool = True
    custom_settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class NotificationEvent:
    """Individual notification event."""
    
    id: str
    dog_id: str | None
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    message: str
    created_at: datetime
    expires_at: datetime | None = None
    channels: list[NotificationChannel] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    sent_to: list[NotificationChannel] = field(default_factory=list)
    failed_channels: list[NotificationChannel] = field(default_factory=list)
    retry_count: int = 0
    acknowledged: bool = False
    acknowledged_at: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "notification_type": self.notification_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "channels": [channel.value for channel in self.channels],
            "data": self.data,
            "sent_to": [channel.value for channel in self.sent_to],
            "failed_channels": [channel.value for channel in self.failed_channels],
            "retry_count": self.retry_count,
            "acknowledged": self.acknowledged,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


class NotificationManager:
    """Comprehensive notification management system."""
    
    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize notification manager.
        
        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._notifications: dict[str, NotificationEvent] = {}
        self._configs: dict[str, NotificationConfig] = {}
        self._handlers: dict[NotificationChannel, Callable] = {}
        self._lock = asyncio.Lock()
        self._retry_task: asyncio.Task | None = None
        
        # Setup default handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Setup default notification handlers."""
        self._handlers[NotificationChannel.PERSISTENT] = self._send_persistent_notification
        self._handlers[NotificationChannel.MOBILE] = self._send_mobile_notification
        self._handlers[NotificationChannel.TTS] = self._send_tts_notification
        self._handlers[NotificationChannel.MEDIA_PLAYER] = self._send_media_player_notification
    
    async def async_initialize(self, notification_configs: dict[str, dict[str, Any]]) -> None:
        """Initialize notification configurations.
        
        Args:
            notification_configs: Configuration for each dog/system
        """
        async with self._lock:
            for config_id, config_data in notification_configs.items():
                channels = [
                    NotificationChannel(channel) 
                    for channel in config_data.get("channels", ["persistent"])
                ]
                
                priority_threshold = NotificationPriority(
                    config_data.get("priority_threshold", "normal")
                )
                
                quiet_hours = None
                if "quiet_hours" in config_data:
                    quiet_start = config_data["quiet_hours"].get("start", 22)
                    quiet_end = config_data["quiet_hours"].get("end", 7)
                    quiet_hours = (quiet_start, quiet_end)
                
                self._configs[config_id] = NotificationConfig(
                    enabled=config_data.get("enabled", True),
                    channels=channels,
                    priority_threshold=priority_threshold,
                    quiet_hours=quiet_hours,
                    retry_failed=config_data.get("retry_failed", True),
                    custom_settings=config_data.get("custom_settings", {}),
                )
        
        # Start retry task
        if self._retry_task is None:
            self._retry_task = asyncio.create_task(self._retry_failed_notifications())
    
    async def async_send_notification(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        dog_id: str | None = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        data: dict[str, Any] | None = None,
        expires_in: timedelta | None = None,
        force_channels: list[NotificationChannel] | None = None,
    ) -> str:
        """Send a notification.
        
        Args:
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            dog_id: Optional dog identifier
            priority: Notification priority
            data: Optional additional data
            expires_in: Optional expiration time
            force_channels: Optional forced channels (bypasses config)
            
        Returns:
            Notification ID
        """
        async with self._lock:
            # Generate notification ID
            notification_id = f"{notification_type.value}_{int(dt_util.now().timestamp())}"
            
            # Determine configuration to use
            config_key = dog_id if dog_id else "system"
            config = self._configs.get(config_key, NotificationConfig())
            
            # Check if notifications are enabled
            if not config.enabled:
                _LOGGER.debug("Notifications disabled for %s", config_key)
                return notification_id
            
            # Check priority threshold
            priority_values = {
                NotificationPriority.LOW: 1,
                NotificationPriority.NORMAL: 2,
                NotificationPriority.HIGH: 3,
                NotificationPriority.URGENT: 4,
            }
            
            if priority_values[priority] < priority_values[config.priority_threshold]:
                _LOGGER.debug(
                    "Notification priority %s below threshold %s",
                    priority.value,
                    config.priority_threshold.value,
                )
                return notification_id
            
            # Check quiet hours
            if self._is_quiet_time(config, priority):
                _LOGGER.debug("Notification suppressed due to quiet hours")
                return notification_id
            
            # Determine channels
            channels = force_channels if force_channels else config.channels
            
            # Calculate expiration
            expires_at = None
            if expires_in:
                expires_at = dt_util.now() + expires_in
            elif notification_type in [
                NotificationType.FEEDING_REMINDER,
                NotificationType.WALK_REMINDER,
                NotificationType.MEDICATION_REMINDER,
            ]:
                # Auto-expire reminders after 24 hours
                expires_at = dt_util.now() + timedelta(hours=NOTIFICATION_EXPIRE_HOURS)
            
            # Create notification event
            notification = NotificationEvent(
                id=notification_id,
                dog_id=dog_id,
                notification_type=notification_type,
                priority=priority,
                title=title,
                message=message,
                created_at=dt_util.now(),
                expires_at=expires_at,
                channels=channels,
                data=data or {},
            )
            
            # Store notification
            self._notifications[notification_id] = notification
            
            # Send notification
            await self._send_to_channels(notification)
            
            _LOGGER.info(
                "Sent notification %s: %s (%s)",
                notification_id,
                title,
                priority.value,
            )
            
            return notification_id
    
    def _is_quiet_time(
        self, 
        config: NotificationConfig, 
        priority: NotificationPriority
    ) -> bool:
        """Check if it's currently quiet time.
        
        Args:
            config: Notification configuration
            priority: Notification priority
            
        Returns:
            True if in quiet time and should suppress notification
        """
        # Urgent notifications always go through
        if priority == NotificationPriority.URGENT:
            return False
        
        if not config.quiet_hours:
            return False
        
        now = dt_util.now()
        current_hour = now.hour
        start_hour, end_hour = config.quiet_hours
        
        # Handle quiet hours that cross midnight
        if start_hour > end_hour:  # e.g., 22:00 to 07:00
            return current_hour >= start_hour or current_hour < end_hour
        else:  # e.g., 01:00 to 06:00
            return start_hour <= current_hour < end_hour
    
    async def _send_to_channels(self, notification: NotificationEvent) -> None:
        """Send notification to all configured channels.
        
        Args:
            notification: Notification to send
        """
        for channel in notification.channels:
            try:
                handler = self._handlers.get(channel)
                if handler:
                    await handler(notification)
                    notification.sent_to.append(channel)
                else:
                    _LOGGER.warning("No handler for channel %s", channel.value)
                    notification.failed_channels.append(channel)
            
            except Exception as e:
                _LOGGER.error(
                    "Failed to send notification %s to channel %s: %s",
                    notification.id,
                    channel.value,
                    e,
                )
                notification.failed_channels.append(channel)
    
    async def _send_persistent_notification(self, notification: NotificationEvent) -> None:
        """Send persistent notification in Home Assistant.
        
        Args:
            notification: Notification to send
        """
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": notification.id,
                "title": notification.title,
                "message": notification.message,
            },
        )
    
    async def _send_mobile_notification(self, notification: NotificationEvent) -> None:
        """Send mobile app notification.
        
        Args:
            notification: Notification to send
        """
        # Get mobile app service name from config
        config_key = notification.dog_id if notification.dog_id else "system"
        config = self._configs.get(config_key, NotificationConfig())
        
        mobile_service = config.custom_settings.get("mobile_service", "notify.mobile_app")
        
        service_data = {
            "title": notification.title,
            "message": notification.message,
            "data": {
                "notification_id": notification.id,
                "priority": notification.priority.value,
                "dog_id": notification.dog_id,
                **notification.data,
            },
        }
        
        # Add actions for interactive notifications
        if notification.notification_type in [
            NotificationType.FEEDING_REMINDER,
            NotificationType.WALK_REMINDER,
        ]:
            service_data["data"]["actions"] = [
                {
                    "action": f"acknowledge_{notification.id}",
                    "title": "Mark as Done",
                    "icon": "sli:check",
                },
                {
                    "action": f"snooze_{notification.id}",
                    "title": "Snooze 15min",
                    "icon": "sli:clock",
                },
            ]
        
        await self._hass.services.async_call(
            "notify",
            mobile_service.replace("notify.", ""),
            service_data,
        )
    
    async def _send_tts_notification(self, notification: NotificationEvent) -> None:
        """Send text-to-speech notification.
        
        Args:
            notification: Notification to send
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = self._configs.get(config_key, NotificationConfig())
        
        tts_service = config.custom_settings.get("tts_service", "tts.google_translate_say")
        
        # Combine title and message for TTS
        tts_message = f"{notification.title}. {notification.message}"
        
        await self._hass.services.async_call(
            "tts",
            tts_service.replace("tts.", ""),
            {
                "message": tts_message,
                "entity_id": config.custom_settings.get("tts_entity", "media_player.living_room"),
            },
        )
    
    async def _send_media_player_notification(self, notification: NotificationEvent) -> None:
        """Send notification via media player.
        
        Args:
            notification: Notification to send
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = self._configs.get(config_key, NotificationConfig())
        
        media_player = config.custom_settings.get("media_player_entity")
        if not media_player:
            raise ValueError("No media player entity configured")
        
        # Create announcement message
        announcement = f"PawControl Alert: {notification.title}. {notification.message}"
        
        await self._hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": media_player,
                "media_content_id": f"media-source://tts/tts.google_translate_say?message={announcement}",
                "media_content_type": "music",
            },
        )
    
    async def async_acknowledge_notification(self, notification_id: str) -> bool:
        """Acknowledge a notification.
        
        Args:
            notification_id: ID of notification to acknowledge
            
        Returns:
            True if acknowledgment successful
        """
        async with self._lock:
            notification = self._notifications.get(notification_id)
            if not notification:
                return False
            
            notification.acknowledged = True
            notification.acknowledged_at = dt_util.now()
            
            # Dismiss persistent notification if it exists
            if NotificationChannel.PERSISTENT in notification.sent_to:
                try:
                    await self._hass.services.async_call(
                        "persistent_notification",
                        "dismiss",
                        {"notification_id": notification_id},
                    )
                except Exception as e:
                    _LOGGER.warning("Failed to dismiss persistent notification: %s", e)
            
            _LOGGER.info("Acknowledged notification %s", notification_id)
            return True
    
    async def async_snooze_notification(
        self, 
        notification_id: str, 
        snooze_duration: timedelta = timedelta(minutes=15)
    ) -> bool:
        """Snooze a notification for specified duration.
        
        Args:
            notification_id: ID of notification to snooze
            snooze_duration: How long to snooze for
            
        Returns:
            True if snooze successful
        """
        async with self._lock:
            notification = self._notifications.get(notification_id)
            if not notification:
                return False
            
            # Acknowledge current notification
            await self.async_acknowledge_notification(notification_id)
            
            # Create new notification with snooze delay
            new_notification_id = await self.async_send_notification(
                notification_type=notification.notification_type,
                title=f"⏰ {notification.title}",
                message=notification.message,
                dog_id=notification.dog_id,
                priority=notification.priority,
                data=notification.data,
            )
            
            _LOGGER.info(
                "Snoozed notification %s for %s minutes as %s",
                notification_id,
                snooze_duration.total_seconds() / 60,
                new_notification_id,
            )
            
            return True
    
    async def async_get_active_notifications(
        self, 
        dog_id: str | None = None,
        include_acknowledged: bool = False,
    ) -> list[NotificationEvent]:
        """Get active notifications.
        
        Args:
            dog_id: Optional dog filter
            include_acknowledged: Whether to include acknowledged notifications
            
        Returns:
            List of active notifications
        """
        async with self._lock:
            now = dt_util.now()
            notifications = []
            
            for notification in self._notifications.values():
                # Check expiration
                if notification.expires_at and notification.expires_at < now:
                    continue
                
                # Check acknowledgment
                if not include_acknowledged and notification.acknowledged:
                    continue
                
                # Check dog filter
                if dog_id is not None and notification.dog_id != dog_id:
                    continue
                
                notifications.append(notification)
            
            # Sort by priority and creation time
            priority_values = {
                NotificationPriority.URGENT: 4,
                NotificationPriority.HIGH: 3,
                NotificationPriority.NORMAL: 2,
                NotificationPriority.LOW: 1,
            }
            
            notifications.sort(
                key=lambda n: (priority_values[n.priority], n.created_at),
                reverse=True,
            )
            
            return notifications
    
    async def async_cleanup_expired_notifications(self) -> int:
        """Clean up expired notifications.
        
        Returns:
            Number of notifications cleaned up
        """
        async with self._lock:
            now = dt_util.now()
            expired_ids = []
            
            for notification_id, notification in self._notifications.items():
                if notification.expires_at and notification.expires_at < now:
                    expired_ids.append(notification_id)
            
            for notification_id in expired_ids:
                del self._notifications[notification_id]
            
            if expired_ids:
                _LOGGER.info("Cleaned up %d expired notifications", len(expired_ids))
            
            return len(expired_ids)
    
    async def _retry_failed_notifications(self) -> None:
        """Background task to retry failed notifications."""
        while True:
            try:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                
                async with self._lock:
                    now = dt_util.now()
                    retry_notifications = []
                    
                    for notification in self._notifications.values():
                        # Skip if expired, acknowledged, or no failures
                        if (
                            (notification.expires_at and notification.expires_at < now)
                            or notification.acknowledged
                            or not notification.failed_channels
                            or notification.retry_count >= MAX_RETRY_ATTEMPTS
                        ):
                            continue
                        
                        # Check if enough time has passed since last attempt
                        time_since_creation = now - notification.created_at
                        if time_since_creation.total_seconds() > RETRY_DELAY_SECONDS:
                            retry_notifications.append(notification)
                    
                    # Retry failed notifications
                    for notification in retry_notifications:
                        if notification.failed_channels:
                            _LOGGER.info(
                                "Retrying notification %s (attempt %d)",
                                notification.id,
                                notification.retry_count + 1,
                            )
                            
                            # Reset failed channels and retry
                            failed_channels = notification.failed_channels.copy()
                            notification.failed_channels.clear()
                            notification.channels = failed_channels
                            notification.retry_count += 1
                            
                            await self._send_to_channels(notification)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error("Error in retry task: %s", e)
    
    async def async_send_feeding_reminder(
        self, 
        dog_id: str, 
        meal_type: str, 
        scheduled_time: str,
        portion_size: float | None = None,
    ) -> str:
        """Send feeding reminder notification.
        
        Args:
            dog_id: Dog identifier
            meal_type: Type of meal
            scheduled_time: Scheduled feeding time
            portion_size: Optional portion size
            
        Returns:
            Notification ID
        """
        title = f"🍽️ {meal_type.title()} Time for {dog_id.title()}"
        
        message = f"It's time for {dog_id}'s {meal_type}"
        if portion_size:
            message += f" ({portion_size}g)"
        message += f" scheduled for {scheduled_time}."
        
        return await self.async_send_notification(
            notification_type=NotificationType.FEEDING_REMINDER,
            title=title,
            message=message,
            dog_id=dog_id,
            priority=NotificationPriority.NORMAL,
            data={
                "meal_type": meal_type,
                "scheduled_time": scheduled_time,
                "portion_size": portion_size,
            },
        )
    
    async def async_send_walk_reminder(
        self, 
        dog_id: str, 
        last_walk_hours: float | None = None,
    ) -> str:
        """Send walk reminder notification.
        
        Args:
            dog_id: Dog identifier
            last_walk_hours: Hours since last walk
            
        Returns:
            Notification ID
        """
        title = f"🚶 Walk Time for {dog_id.title()}"
        
        if last_walk_hours:
            message = f"{dog_id} hasn't been walked in {last_walk_hours:.1f} hours. Time for a walk!"
        else:
            message = f"It's time to take {dog_id} for a walk!"
        
        return await self.async_send_notification(
            notification_type=NotificationType.WALK_REMINDER,
            title=title,
            message=message,
            dog_id=dog_id,
            priority=NotificationPriority.NORMAL,
            data={
                "last_walk_hours": last_walk_hours,
            },
        )
    
    async def async_send_health_alert(
        self, 
        dog_id: str, 
        alert_type: str, 
        details: str,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> str:
        """Send health alert notification.
        
        Args:
            dog_id: Dog identifier
            alert_type: Type of health alert
            details: Alert details
            priority: Alert priority
            
        Returns:
            Notification ID
        """
        title = f"⚕️ Health Alert: {dog_id.title()}"
        message = f"{alert_type}: {details}"
        
        return await self.async_send_notification(
            notification_type=NotificationType.HEALTH_ALERT,
            title=title,
            message=message,
            dog_id=dog_id,
            priority=priority,
            data={
                "alert_type": alert_type,
                "details": details,
            },
        )
    
    async def async_register_handler(
        self, 
        channel: NotificationChannel, 
        handler: Callable[[NotificationEvent], None]
    ) -> None:
        """Register custom notification handler.
        
        Args:
            channel: Notification channel
            handler: Async handler function
        """
        async with self._lock:
            self._handlers[channel] = handler
            _LOGGER.info("Registered handler for channel %s", channel.value)
    
    async def async_get_notification_statistics(self) -> dict[str, Any]:
        """Get notification statistics.
        
        Returns:
            Statistics dictionary
        """
        async with self._lock:
            now = dt_util.now()
            total_notifications = len(self._notifications)
            active_notifications = 0
            acknowledged_notifications = 0
            expired_notifications = 0
            
            type_counts = {}
            priority_counts = {}
            
            for notification in self._notifications.values():
                # Count by status
                if notification.expires_at and notification.expires_at < now:
                    expired_notifications += 1
                elif notification.acknowledged:
                    acknowledged_notifications += 1
                else:
                    active_notifications += 1
                
                # Count by type
                ntype = notification.notification_type.value
                type_counts[ntype] = type_counts.get(ntype, 0) + 1
                
                # Count by priority
                priority = notification.priority.value
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            return {
                "total_notifications": total_notifications,
                "active_notifications": active_notifications,
                "acknowledged_notifications": acknowledged_notifications,
                "expired_notifications": expired_notifications,
                "type_distribution": type_counts,
                "priority_distribution": priority_counts,
                "configured_dogs": len([k for k in self._configs.keys() if k != "system"]),
            }
    
    async def async_shutdown(self) -> None:
        """Clean shutdown of notification manager."""
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        
        # Clear all data
        self._notifications.clear()
        self._configs.clear()
        self._handlers.clear()
