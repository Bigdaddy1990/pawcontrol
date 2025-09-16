"""Advanced notification system for PawControl integration.

Comprehensive notification management with batch processing, advanced caching,
and performance optimizations for Platinum quality compliance.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# OPTIMIZE: Enhanced notification constants
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30
NOTIFICATION_EXPIRE_HOURS = 24
BATCH_PROCESSING_SIZE = 10
CACHE_CLEANUP_INTERVAL = 3600  # 1 hour
QUIET_TIME_CACHE_TTL = 300  # 5 minutes
CONFIG_CACHE_SIZE_LIMIT = 100


class NotificationType(Enum):
    """Types of notifications with priority hints."""
    
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
    GEOFENCE_ALERT = "geofence_alert"  # OPTIMIZE: Added geofence alerts
    BATTERY_LOW = "battery_low"         # OPTIMIZE: Added battery alerts


class NotificationPriority(Enum):
    """Notification priority levels with numeric values for comparison."""
    
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"

    @property
    def value_numeric(self) -> int:
        """Get numeric value for priority comparison."""
        mapping = {
            "low": 1,
            "normal": 2, 
            "high": 3,
            "urgent": 4,
        }
        return mapping[self.value]


class NotificationChannel(Enum):
    """Available notification channels."""
    
    PERSISTENT = "persistent"  # Home Assistant persistent notifications
    MOBILE = "mobile"          # Mobile app notifications
    EMAIL = "email"            # Email notifications
    SMS = "sms"               # SMS notifications
    WEBHOOK = "webhook"        # Custom webhook
    TTS = "tts"               # Text-to-speech
    MEDIA_PLAYER = "media_player"  # Media player announcements
    SLACK = "slack"            # OPTIMIZE: Added Slack notifications
    DISCORD = "discord"        # OPTIMIZE: Added Discord notifications


@dataclass
class NotificationConfig:
    """Enhanced configuration for notification delivery."""
    
    enabled: bool = True
    channels: list[NotificationChannel] = field(default_factory=lambda: [NotificationChannel.PERSISTENT])
    priority_threshold: NotificationPriority = NotificationPriority.NORMAL
    quiet_hours: tuple[int, int] | None = None  # (start_hour, end_hour)
    retry_failed: bool = True
    custom_settings: dict[str, Any] = field(default_factory=dict)
    rate_limit: dict[str, int] = field(default_factory=dict)  # OPTIMIZE: Added rate limiting
    batch_enabled: bool = True  # OPTIMIZE: Allow batching per config
    template_overrides: dict[str, str] = field(default_factory=dict)  # OPTIMIZE: Custom templates


@dataclass
class NotificationEvent:
    """Enhanced individual notification event."""
    
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
    
    # OPTIMIZE: Enhanced metadata
    grouped_with: list[str] = field(default_factory=list)  # For batched notifications
    template_used: str | None = None
    send_attempts: dict[str, int] = field(default_factory=dict)  # Per-channel attempts
    
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
            "grouped_with": self.grouped_with,
            "template_used": self.template_used,
            "send_attempts": self.send_attempts,
        }

    def can_be_batched_with(self, other: NotificationEvent) -> bool:
        """Check if this notification can be batched with another.
        
        Args:
            other: Other notification event
            
        Returns:
            True if notifications can be batched
        """
        return (
            self.dog_id == other.dog_id
            and self.notification_type == other.notification_type
            and self.priority == other.priority
            and not self.acknowledged
            and not other.acknowledged
        )


class NotificationCache:
    """OPTIMIZE: Advanced caching system for notification configurations and state."""

    def __init__(self, max_size: int = CONFIG_CACHE_SIZE_LIMIT) -> None:
        """Initialize notification cache.
        
        Args:
            max_size: Maximum cache entries
        """
        self._config_cache: dict[str, tuple[NotificationConfig, datetime]] = {}
        self._quiet_time_cache: dict[str, tuple[bool, datetime]] = {}
        self._rate_limit_cache: dict[str, dict[str, datetime]] = {}
        self._max_size = max_size
        self._access_order: deque[str] = deque()

    def get_config(self, config_key: str) -> NotificationConfig | None:
        """Get cached configuration.
        
        Args:
            config_key: Configuration key
            
        Returns:
            Cached configuration or None
        """
        if config_key in self._config_cache:
            config, _timestamp = self._config_cache[config_key]
            # Update access order for LRU
            if config_key in self._access_order:
                self._access_order.remove(config_key)
            self._access_order.append(config_key)
            return config
        return None

    def set_config(self, config_key: str, config: NotificationConfig) -> None:
        """Set configuration with LRU eviction.
        
        Args:
            config_key: Configuration key
            config: Configuration to cache
        """
        # Evict oldest if at capacity
        if len(self._config_cache) >= self._max_size and config_key not in self._config_cache:
            oldest = self._access_order.popleft()
            del self._config_cache[oldest]

        self._config_cache[config_key] = (config, dt_util.now())
        
        # Update access order
        if config_key in self._access_order:
            self._access_order.remove(config_key)
        self._access_order.append(config_key)

    def is_quiet_time_cached(self, config_key: str) -> tuple[bool, bool]:
        """Check if quiet time status is cached.
        
        Args:
            config_key: Configuration key
            
        Returns:
            Tuple of (is_cached, is_quiet_time)
        """
        if config_key in self._quiet_time_cache:
            is_quiet, cache_time = self._quiet_time_cache[config_key]
            if (dt_util.now() - cache_time).total_seconds() < QUIET_TIME_CACHE_TTL:
                return True, is_quiet
        return False, False

    def set_quiet_time_cache(self, config_key: str, is_quiet: bool) -> None:
        """Cache quiet time status.
        
        Args:
            config_key: Configuration key
            is_quiet: Whether it's currently quiet time
        """
        self._quiet_time_cache[config_key] = (is_quiet, dt_util.now())

    def check_rate_limit(self, config_key: str, channel: str, limit_minutes: int) -> bool:
        """Check if rate limit allows sending.
        
        Args:
            config_key: Configuration key
            channel: Notification channel
            limit_minutes: Rate limit in minutes
            
        Returns:
            True if sending is allowed
        """
        now = dt_util.now()
        rate_key = f"{config_key}_{channel}"
        
        if config_key not in self._rate_limit_cache:
            self._rate_limit_cache[config_key] = {}
        
        channel_cache = self._rate_limit_cache[config_key]
        
        if channel in channel_cache:
            last_sent = channel_cache[channel]
            if (now - last_sent).total_seconds() < limit_minutes * 60:
                return False
        
        # Update rate limit cache
        channel_cache[channel] = now
        return True

    def cleanup_expired(self) -> int:
        """Clean up expired cache entries.
        
        Returns:
            Number of entries cleaned up
        """
        now = dt_util.now()
        cleaned = 0
        
        # Clean quiet time cache
        expired_quiet_keys = [
            key for key, (_, cache_time) in self._quiet_time_cache.items()
            if (now - cache_time).total_seconds() > QUIET_TIME_CACHE_TTL
        ]
        for key in expired_quiet_keys:
            del self._quiet_time_cache[key]
            cleaned += 1
        
        # Clean rate limit cache (older than 24 hours)
        for config_key, channels in self._rate_limit_cache.items():
            expired_channels = [
                channel for channel, last_sent in channels.items()
                if (now - last_sent).total_seconds() > 86400
            ]
            for channel in expired_channels:
                del channels[channel]
                cleaned += 1
        
        return cleaned

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return {
            "config_entries": len(self._config_cache),
            "quiet_time_entries": len(self._quiet_time_cache),
            "rate_limit_entries": sum(len(channels) for channels in self._rate_limit_cache.values()),
            "cache_utilization": len(self._config_cache) / self._max_size * 100,
        }


class PawControlNotificationManager:
    """Advanced notification management system with performance optimizations.
    
    OPTIMIZE: Enhanced with batch processing, advanced caching, rate limiting,
    and comprehensive performance monitoring for Platinum-level quality.
    """
    
    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize advanced notification manager.
        
        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for namespacing
        """
        self._hass = hass
        self._entry_id = entry_id
        self._notifications: dict[str, NotificationEvent] = {}
        self._configs: dict[str, NotificationConfig] = {}
        self._handlers: dict[NotificationChannel, Callable] = {}
        self._lock = asyncio.Lock()
        
        # OPTIMIZE: Enhanced background tasks
        self._retry_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._batch_task: asyncio.Task | None = None
        
        # OPTIMIZE: Advanced caching and batching
        self._cache = NotificationCache()
        self._batch_queue: deque[NotificationEvent] = deque()
        self._pending_batches: dict[str, list[NotificationEvent]] = {}
        
        # OPTIMIZE: Performance monitoring
        self._performance_metrics = {
            "notifications_sent": 0,
            "notifications_failed": 0,
            "batch_operations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_blocks": 0,
            "average_delivery_time_ms": 0.0,
        }
        
        # OPTIMIZE: Template system for customizable notifications
        self._templates: dict[str, str] = {
            "feeding_reminder": "🍽️ {title}\n{message}",
            "walk_reminder": "🚶 {title}\n{message}",
            "health_alert": "⚕️ {title}\n{message}",
            "batch_summary": "📋 {count} notifications for {dog_name}:\n{summary}",
        }
        
        # Setup default handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Setup default notification handlers with error handling."""
        handlers = {
            NotificationChannel.PERSISTENT: self._send_persistent_notification,
            NotificationChannel.MOBILE: self._send_mobile_notification,
            NotificationChannel.TTS: self._send_tts_notification,
            NotificationChannel.MEDIA_PLAYER: self._send_media_player_notification,
            NotificationChannel.SLACK: self._send_slack_notification,
            NotificationChannel.DISCORD: self._send_discord_notification,
        }
        
        # Wrap handlers with error handling and performance monitoring
        for channel, handler in handlers.items():
            self._handlers[channel] = self._wrap_handler_with_monitoring(handler, channel)
    
    def _wrap_handler_with_monitoring(
        self, handler: Callable, channel: NotificationChannel
    ) -> Callable:
        """Wrap handler with performance monitoring.
        
        Args:
            handler: Original handler function
            channel: Notification channel
            
        Returns:
            Wrapped handler with monitoring
        """
        async def wrapped_handler(notification: NotificationEvent) -> None:
            start_time = dt_util.now()
            try:
                await handler(notification)
                self._performance_metrics["notifications_sent"] += 1
            except Exception as err:
                self._performance_metrics["notifications_failed"] += 1
                _LOGGER.error(
                    "Handler for %s failed on notification %s: %s",
                    channel.value, notification.id, err
                )
                raise
            finally:
                # Update average delivery time
                delivery_time_ms = (dt_util.now() - start_time).total_seconds() * 1000
                current_avg = self._performance_metrics["average_delivery_time_ms"]
                total_sent = self._performance_metrics["notifications_sent"]
                
                if total_sent > 0:
                    new_avg = (current_avg * (total_sent - 1) + delivery_time_ms) / total_sent
                    self._performance_metrics["average_delivery_time_ms"] = new_avg

        return wrapped_handler
    
    async def async_initialize(self, notification_configs: dict[str, dict[str, Any]] | None = None) -> None:
        """Initialize notification configurations with enhanced validation.
        
        Args:
            notification_configs: Configuration for each dog/system
        """
        async with self._lock:
            configs = notification_configs or {}
            
            for config_id, config_data in configs.items():
                try:
                    # Parse channels with validation
                    channels = []
                    for channel_str in config_data.get("channels", ["persistent"]):
                        try:
                            channels.append(NotificationChannel(channel_str))
                        except ValueError:
                            _LOGGER.warning("Invalid notification channel: %s", channel_str)
                    
                    # Parse priority threshold
                    priority_threshold = NotificationPriority(
                        config_data.get("priority_threshold", "normal")
                    )
                    
                    # Parse quiet hours
                    quiet_hours = None
                    if "quiet_hours" in config_data:
                        quiet_start = config_data["quiet_hours"].get("start", 22)
                        quiet_end = config_data["quiet_hours"].get("end", 7)
                        quiet_hours = (quiet_start, quiet_end)
                    
                    # Parse rate limits
                    rate_limit = config_data.get("rate_limit", {})
                    
                    # Parse template overrides
                    template_overrides = config_data.get("template_overrides", {})
                    
                    config = NotificationConfig(
                        enabled=config_data.get("enabled", True),
                        channels=channels,
                        priority_threshold=priority_threshold,
                        quiet_hours=quiet_hours,
                        retry_failed=config_data.get("retry_failed", True),
                        custom_settings=config_data.get("custom_settings", {}),
                        rate_limit=rate_limit,
                        batch_enabled=config_data.get("batch_enabled", True),
                        template_overrides=template_overrides,
                    )
                    
                    self._configs[config_id] = config
                    self._cache.set_config(config_id, config)
                    
                except Exception as err:
                    _LOGGER.error("Failed to parse config for %s: %s", config_id, err)
        
        # Start background tasks
        await self._start_background_tasks()
    
    async def _start_background_tasks(self) -> None:
        """Start background processing tasks."""
        # Start retry task
        if self._retry_task is None:
            self._retry_task = asyncio.create_task(self._retry_failed_notifications())
        
        # Start cleanup task
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_notifications())
        
        # Start batch processing task
        if self._batch_task is None:
            self._batch_task = asyncio.create_task(self._process_batch_notifications())
    
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
        allow_batching: bool = True,
    ) -> str:
        """Send a notification with advanced processing.
        
        OPTIMIZE: Enhanced with batching, caching, rate limiting, and templates.
        
        Args:
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            dog_id: Optional dog identifier
            priority: Notification priority
            data: Optional additional data
            expires_in: Optional expiration time
            force_channels: Optional forced channels (bypasses config)
            allow_batching: Whether this notification can be batched
            
        Returns:
            Notification ID
        """
        async with self._lock:
            # Generate notification ID
            notification_id = f"{notification_type.value}_{int(dt_util.now().timestamp())}"
            
            # Determine configuration to use
            config_key = dog_id if dog_id else "system"
            config = await self._get_config_cached(config_key)
            
            # Check if notifications are enabled
            if not config.enabled:
                _LOGGER.debug("Notifications disabled for %s", config_key)
                return notification_id
            
            # Check priority threshold with optimized comparison
            if priority.value_numeric < config.priority_threshold.value_numeric:
                _LOGGER.debug(
                    "Notification priority %s below threshold %s",
                    priority.value,
                    config.priority_threshold.value,
                )
                return notification_id
            
            # OPTIMIZE: Check quiet hours with caching
            if await self._is_quiet_time_cached(config_key, config, priority):
                _LOGGER.debug("Notification suppressed due to quiet hours")
                return notification_id
            
            # OPTIMIZE: Check rate limits
            channels = force_channels if force_channels else config.channels
            allowed_channels = []
            for channel in channels:
                rate_limit_key = f"{channel.value}_limit_minutes"
                limit_minutes = config.rate_limit.get(rate_limit_key, 0)
                
                if limit_minutes == 0 or self._cache.check_rate_limit(config_key, channel.value, limit_minutes):
                    allowed_channels.append(channel)
                else:
                    self._performance_metrics["rate_limit_blocks"] += 1
                    _LOGGER.debug("Rate limit blocked %s for %s", channel.value, config_key)
            
            if not allowed_channels:
                _LOGGER.warning("All channels rate limited for %s", config_key)
                return notification_id
            
            # Apply template if available
            formatted_title, formatted_message = self._apply_template(
                notification_type, title, message, config, data or {}
            )
            
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
                title=formatted_title,
                message=formatted_message,
                created_at=dt_util.now(),
                expires_at=expires_at,
                channels=allowed_channels,
                data=data or {},
                template_used=self._get_template_name(notification_type),
            )
            
            # Store notification
            self._notifications[notification_id] = notification
            
            # OPTIMIZE: Handle batching for eligible notifications
            if allow_batching and config.batch_enabled and self._should_batch(notification):
                await self._add_to_batch_queue(notification)
                _LOGGER.debug("Added notification %s to batch queue", notification_id)
            else:
                # Send immediately
                await self._send_to_channels(notification)
                _LOGGER.info(
                    "Sent notification %s: %s (%s)",
                    notification_id,
                    formatted_title,
                    priority.value,
                )
            
            return notification_id

    async def _get_config_cached(self, config_key: str) -> NotificationConfig:
        """Get configuration with caching.
        
        Args:
            config_key: Configuration key
            
        Returns:
            Notification configuration
        """
        # Check cache first
        cached_config = self._cache.get_config(config_key)
        if cached_config:
            self._performance_metrics["cache_hits"] += 1
            return cached_config
        
        # Get from configs
        config = self._configs.get(config_key, NotificationConfig())
        self._cache.set_config(config_key, config)
        self._performance_metrics["cache_misses"] += 1
        
        return config

    async def _is_quiet_time_cached(
        self, 
        config_key: str,
        config: NotificationConfig, 
        priority: NotificationPriority
    ) -> bool:
        """Check if it's currently quiet time with caching.
        
        OPTIMIZE: Cache quiet time calculations to reduce repeated computations.
        
        Args:
            config_key: Configuration key for caching
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
        
        # Check cache first
        is_cached, is_quiet = self._cache.is_quiet_time_cached(config_key)
        if is_cached:
            return is_quiet
        
        # Calculate quiet time status
        now = dt_util.now()
        current_hour = now.hour
        start_hour, end_hour = config.quiet_hours
        
        # Handle quiet hours that cross midnight
        if start_hour > end_hour:  # e.g., 22:00 to 07:00
            is_quiet = current_hour >= start_hour or current_hour < end_hour
        else:  # e.g., 01:00 to 06:00
            is_quiet = start_hour <= current_hour < end_hour
        
        # Cache result
        self._cache.set_quiet_time_cache(config_key, is_quiet)
        
        return is_quiet

    def _apply_template(
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        config: NotificationConfig,
        data: dict[str, Any],
    ) -> tuple[str, str]:
        """Apply template formatting to notification.
        
        Args:
            notification_type: Type of notification
            title: Original title
            message: Original message
            config: Notification configuration
            data: Additional data for templating
            
        Returns:
            Tuple of (formatted_title, formatted_message)
        """
        template_name = self._get_template_name(notification_type)
        
        # Check for config override first
        template = config.template_overrides.get(
            template_name,
            self._templates.get(template_name)
        )
        
        if not template:
            return title, message
        
        try:
            # Prepare template variables
            template_vars = {
                "title": title,
                "message": message,
                **data,
            }
            
            formatted = template.format(**template_vars)
            
            # Split back into title and message if template contains both
            if "\n" in formatted:
                parts = formatted.split("\n", 1)
                return parts[0], parts[1]
            else:
                return formatted, message
                
        except (KeyError, ValueError) as err:
            _LOGGER.warning("Template formatting failed for %s: %s", template_name, err)
            return title, message

    def _get_template_name(self, notification_type: NotificationType) -> str:
        """Get template name for notification type.
        
        Args:
            notification_type: Notification type
            
        Returns:
            Template name
        """
        return notification_type.value

    def _should_batch(self, notification: NotificationEvent) -> bool:
        """Determine if notification should be batched.
        
        Args:
            notification: Notification event
            
        Returns:
            True if notification should be batched
        """
        # Only batch certain types of notifications
        batchable_types = {
            NotificationType.FEEDING_REMINDER,
            NotificationType.WALK_REMINDER,
            NotificationType.HEALTH_ALERT,
        }
        
        return (
            notification.notification_type in batchable_types
            and notification.priority != NotificationPriority.URGENT
            and notification.dog_id is not None
        )

    async def _add_to_batch_queue(self, notification: NotificationEvent) -> None:
        """Add notification to batch queue.
        
        Args:
            notification: Notification to batch
        """
        self._batch_queue.append(notification)
        
        # Add to pending batches by dog
        if notification.dog_id:
            batch_key = f"{notification.dog_id}_{notification.notification_type.value}"
            if batch_key not in self._pending_batches:
                self._pending_batches[batch_key] = []
            self._pending_batches[batch_key].append(notification)

    async def _process_batch_notifications(self) -> None:
        """Background task to process batch notifications.
        
        OPTIMIZE: Process notifications in batches for better user experience.
        """
        while True:
            try:
                await asyncio.sleep(60)  # Process batches every minute
                
                async with self._lock:
                    if not self._pending_batches:
                        continue
                    
                    # Process each batch
                    batches_to_send = {}
                    for batch_key, notifications in self._pending_batches.items():
                        if len(notifications) >= BATCH_PROCESSING_SIZE:
                            batches_to_send[batch_key] = notifications[:BATCH_PROCESSING_SIZE]
                            # Remove processed notifications
                            del self._pending_batches[batch_key]
                        elif notifications:
                            # Check if oldest notification is older than 5 minutes
                            oldest = min(notifications, key=lambda n: n.created_at)
                            age = (dt_util.now() - oldest.created_at).total_seconds()
                            if age > 300:  # 5 minutes
                                batches_to_send[batch_key] = notifications
                                del self._pending_batches[batch_key]
                    
                    # Send batches
                    for batch_key, notifications in batches_to_send.items():
                        await self._send_batch(notifications)
                        self._performance_metrics["batch_operations"] += 1
            
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Batch processing error: %s", err)

    async def _send_batch(self, notifications: list[NotificationEvent]) -> None:
        """Send a batch of notifications.
        
        Args:
            notifications: List of notifications to send as batch
        """
        if not notifications:
            return
        
        # Group notifications and create batch notification
        dog_id = notifications[0].dog_id
        dog_name = dog_id.replace("_", " ").title() if dog_id else "System"
        
        # Create summary
        summary_lines = []
        for notification in notifications:
            summary_lines.append(f"• {notification.title}")
        
        # Create batch notification
        batch_title = f"📋 {len(notifications)} notifications for {dog_name}"
        batch_message = "\n".join(summary_lines)
        
        # Find common channels
        common_channels = set(notifications[0].channels)
        for notification in notifications[1:]:
            common_channels &= set(notification.channels)
        
        if not common_channels:
            # Fall back to individual sends if no common channels
            for notification in notifications:
                await self._send_to_channels(notification)
            return
        
        # Create batch notification event
        batch_id = f"batch_{int(dt_util.now().timestamp())}"
        batch_notification = NotificationEvent(
            id=batch_id,
            dog_id=dog_id,
            notification_type=NotificationType.SYSTEM_INFO,
            priority=notifications[0].priority,
            title=batch_title,
            message=batch_message,
            created_at=dt_util.now(),
            channels=list(common_channels),
            data={
                "batch_count": len(notifications),
                "individual_ids": [n.id for n in notifications],
            },
        )
        
        # Mark individual notifications as grouped
        for notification in notifications:
            notification.grouped_with.append(batch_id)
        
        # Send batch notification
        await self._send_to_channels(batch_notification)
        
        _LOGGER.info(
            "Sent batch notification with %d individual notifications for %s",
            len(notifications),
            dog_name,
        )

    async def _send_to_channels(self, notification: NotificationEvent) -> None:
        """Send notification to all configured channels with enhanced error handling.
        
        OPTIMIZE: Parallel channel sending with individual error handling.
        
        Args:
            notification: Notification to send
        """
        # Send to all channels in parallel
        send_tasks = []
        for channel in notification.channels:
            handler = self._handlers.get(channel)
            if handler:
                send_tasks.append(self._send_to_channel_safe(notification, channel, handler))
            else:
                _LOGGER.warning("No handler for channel %s", channel.value)
                notification.failed_channels.append(channel)
        
        if send_tasks:
            # Execute all sends in parallel
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    channel = notification.channels[i]
                    _LOGGER.error(
                        "Failed to send notification %s to channel %s: %s",
                        notification.id, channel.value, result
                    )

    async def _send_to_channel_safe(
        self,
        notification: NotificationEvent,
        channel: NotificationChannel,
        handler: Callable,
    ) -> None:
        """Send to a single channel with error handling.
        
        Args:
            notification: Notification to send
            channel: Target channel
            handler: Channel handler function
        """
        try:
            await handler(notification)
            notification.sent_to.append(channel)
            
            # Track send attempts
            channel_key = channel.value
            notification.send_attempts[channel_key] = notification.send_attempts.get(channel_key, 0) + 1
            
        except Exception as err:
            notification.failed_channels.append(channel)
            _LOGGER.error(
                "Failed to send notification %s to channel %s: %s",
                notification.id, channel.value, err
            )

    # OPTIMIZE: Enhanced notification handlers with better error handling and features
    async def _send_persistent_notification(self, notification: NotificationEvent) -> None:
        """Send persistent notification in Home Assistant."""
        service_data = {
            "notification_id": f"{self._entry_id}_{notification.id}",
            "title": notification.title,
            "message": notification.message,
        }
        
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            service_data,
        )

    async def _send_mobile_notification(self, notification: NotificationEvent) -> None:
        """Send mobile app notification with enhanced features."""
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        
        mobile_service = config.custom_settings.get("mobile_service", "mobile_app")
        
        service_data = {
            "title": notification.title,
            "message": notification.message,
            "data": {
                "notification_id": notification.id,
                "priority": notification.priority.value,
                "dog_id": notification.dog_id,
                "entry_id": self._entry_id,
                **notification.data,
            },
        }
        
        # Add actions for interactive notifications
        if notification.notification_type in [
            NotificationType.FEEDING_REMINDER,
            NotificationType.WALK_REMINDER,
            NotificationType.MEDICATION_REMINDER,
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
            mobile_service,
            service_data,
        )

    async def _send_tts_notification(self, notification: NotificationEvent) -> None:
        """Send text-to-speech notification."""
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        
        tts_service = config.custom_settings.get("tts_service", "google_translate_say")
        tts_entity = config.custom_settings.get("tts_entity", "media_player.living_room")
        
        # Combine title and message for TTS
        tts_message = f"{notification.title}. {notification.message}"
        
        await self._hass.services.async_call(
            "tts",
            tts_service,
            {
                "message": tts_message,
                "entity_id": tts_entity,
            },
        )

    async def _send_media_player_notification(self, notification: NotificationEvent) -> None:
        """Send notification via media player."""
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        
        media_player = config.custom_settings.get("media_player_entity")
        if not media_player:
            raise ValueError("No media player entity configured")
        
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

    async def _send_slack_notification(self, notification: NotificationEvent) -> None:
        """Send Slack notification.
        
        OPTIMIZE: New Slack integration for team notifications.
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        
        slack_service = config.custom_settings.get("slack_service", "slack")
        
        service_data = {
            "title": notification.title,
            "message": notification.message,
            "target": config.custom_settings.get("slack_channel", "#pawcontrol"),
            "data": {
                "icon": ":dog:" if notification.dog_id else ":gear:",
                "username": "PawControl",
            },
        }
        
        await self._hass.services.async_call(
            "notify",
            slack_service,
            service_data,
        )

    async def _send_discord_notification(self, notification: NotificationEvent) -> None:
        """Send Discord notification.
        
        OPTIMIZE: New Discord integration for community notifications.
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        
        discord_service = config.custom_settings.get("discord_service", "discord")
        
        service_data = {
            "title": notification.title,
            "message": notification.message,
            "target": config.custom_settings.get("discord_channel"),
            "data": {
                "embed": {
                    "color": self._get_color_for_priority(notification.priority),
                    "author": {
                        "name": "PawControl",
                        "icon_url": "https://example.com/pawcontrol-icon.png",
                    },
                },
            },
        }
        
        await self._hass.services.async_call(
            "notify",
            discord_service,
            service_data,
        )

    def _get_color_for_priority(self, priority: NotificationPriority) -> int:
        """Get Discord embed color for priority.
        
        Args:
            priority: Notification priority
            
        Returns:
            Discord color code
        """
        colors = {
            NotificationPriority.LOW: 0x95a5a6,      # Gray
            NotificationPriority.NORMAL: 0x3498db,   # Blue
            NotificationPriority.HIGH: 0xf39c12,     # Orange
            NotificationPriority.URGENT: 0xe74c3c,   # Red
        }
        return colors.get(priority, 0x3498db)

    # OPTIMIZE: Enhanced cleanup and maintenance
    async def _cleanup_expired_notifications(self) -> None:
        """Background task to clean up expired notifications and cache."""
        while True:
            try:
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
                
                async with self._lock:
                    # Clean expired notifications
                    expired_count = await self.async_cleanup_expired_notifications()
                    
                    # Clean cache
                    cache_cleaned = self._cache.cleanup_expired()
                    
                    if expired_count > 0 or cache_cleaned > 0:
                        _LOGGER.debug(
                            "Cleanup: %d expired notifications, %d cache entries",
                            expired_count, cache_cleaned
                        )
            
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Cleanup task error: %s", err)

    async def async_cleanup_expired_notifications(self) -> int:
        """Clean up expired notifications with enhanced logic.
        
        Returns:
            Number of notifications cleaned up
        """
        now = dt_util.now()
        expired_ids = []
        
        for notification_id, notification in self._notifications.items():
            # Remove if expired or very old acknowledged notifications
            if (
                (notification.expires_at and notification.expires_at < now)
                or (notification.acknowledged and 
                    notification.acknowledged_at and
                    (now - notification.acknowledged_at).days > 7)
            ):
                expired_ids.append(notification_id)
        
        # Batch remove expired notifications
        for notification_id in expired_ids:
            del self._notifications[notification_id]
        
        if expired_ids:
            _LOGGER.debug("Cleaned up %d expired notifications", len(expired_ids))
        
        return len(expired_ids)

    # Keep existing public interface methods with optimizations
    async def async_acknowledge_notification(self, notification_id: str) -> bool:
        """Acknowledge a notification with enhanced cleanup."""
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
                        {"notification_id": f"{self._entry_id}_{notification_id}"},
                    )
                except Exception as err:
                    _LOGGER.warning("Failed to dismiss persistent notification: %s", err)
            
            _LOGGER.info("Acknowledged notification %s", notification_id)
            return True

    async def async_get_performance_statistics(self) -> dict[str, Any]:
        """Get comprehensive performance statistics.
        
        OPTIMIZE: New method for monitoring system performance.
        
        Returns:
            Performance statistics
        """
        async with self._lock:
            total_notifications = len(self._notifications)
            active_notifications = len([
                n for n in self._notifications.values()
                if not n.acknowledged and (
                    not n.expires_at or n.expires_at > dt_util.now()
                )
            ])
            
            # Calculate type and priority distribution
            type_counts = {}
            priority_counts = {}
            
            for notification in self._notifications.values():
                ntype = notification.notification_type.value
                type_counts[ntype] = type_counts.get(ntype, 0) + 1
                
                priority = notification.priority.value
                priority_counts[priority] = priority_counts.get(priority, 0) + 1
            
            return {
                # Basic stats
                "total_notifications": total_notifications,
                "active_notifications": active_notifications,
                "configured_dogs": len([k for k in self._configs.keys() if k != "system"]),
                "type_distribution": type_counts,
                "priority_distribution": priority_counts,
                
                # Performance metrics
                "performance_metrics": self._performance_metrics.copy(),
                "cache_stats": self._cache.get_stats(),
                "batch_queue_size": len(self._batch_queue),
                "pending_batches": len(self._pending_batches),
                
                # Handler stats
                "available_channels": [channel.value for channel in self._handlers.keys()],
                "handlers_registered": len(self._handlers),
            }

    async def async_shutdown(self) -> None:
        """Enhanced shutdown with comprehensive cleanup."""
        # Cancel all background tasks
        tasks_to_cancel = [
            self._retry_task,
            self._cleanup_task,
            self._batch_task,
        ]
        
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*[t for t in tasks_to_cancel if t], return_exceptions=True)
        
        # Process any remaining batches
        async with self._lock:
            for notifications in self._pending_batches.values():
                for notification in notifications:
                    await self._send_to_channels(notification)
        
        # Clear all data
        self._notifications.clear()
        self._configs.clear()
        self._handlers.clear()
        self._batch_queue.clear()
        self._pending_batches.clear()

    # Keep existing methods for backward compatibility
    async def _retry_failed_notifications(self) -> None:
        """Background task to retry failed notifications."""
        while True:
            try:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
                
                async with self._lock:
                    now = dt_util.now()
                    retry_notifications = []
                    
                    for notification in self._notifications.values():
                        if (
                            (notification.expires_at and notification.expires_at < now)
                            or notification.acknowledged
                            or not notification.failed_channels
                            or notification.retry_count >= MAX_RETRY_ATTEMPTS
                        ):
                            continue
                        
                        time_since_creation = now - notification.created_at
                        if time_since_creation.total_seconds() > RETRY_DELAY_SECONDS:
                            retry_notifications.append(notification)
                    
                    for notification in retry_notifications:
                        if notification.failed_channels:
                            _LOGGER.info(
                                "Retrying notification %s (attempt %d)",
                                notification.id,
                                notification.retry_count + 1,
                            )
                            
                            failed_channels = notification.failed_channels.copy()
                            notification.failed_channels.clear()
                            notification.channels = failed_channels
                            notification.retry_count += 1
                            
                            await self._send_to_channels(notification)
            
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in retry task: %s", err)

    # Additional convenience methods for specific notification types
    async def async_send_feeding_reminder(
        self, dog_id: str, meal_type: str, scheduled_time: str, portion_size: float | None = None
    ) -> str:
        """Send feeding reminder notification."""
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
        self, dog_id: str, last_walk_hours: float | None = None
    ) -> str:
        """Send walk reminder notification."""
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
            data={"last_walk_hours": last_walk_hours},
        )

    async def async_send_health_alert(
        self, 
        dog_id: str, 
        alert_type: str, 
        details: str,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ) -> str:
        """Send health alert notification."""
        title = f"⚕️ Health Alert: {dog_id.title()}"
        message = f"{alert_type}: {details}"
        
        return await self.async_send_notification(
            notification_type=NotificationType.HEALTH_ALERT,
            title=title,
            message=message,
            dog_id=dog_id,
            priority=priority,
            data={"alert_type": alert_type, "details": details},
        )
