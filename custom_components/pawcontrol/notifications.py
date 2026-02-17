"""Advanced notification system for the PawControl integration.

Comprehensive notification management with batch processing, person entity
integration, and performance optimizations for Platinum quality compliance.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import partial
import inspect
import json
import logging
import time
from typing import TYPE_CHECKING, Any, TypedDict, TypeVar, cast
from uuid import uuid4

from aiohttp import ClientError, ClientSession, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .coordinator_support import CacheMonitorRegistrar
from .coordinator_tasks import default_rejection_metrics
from .dashboard_shared import unwrap_async_result
from .feeding_translations import async_build_feeding_compliance_notification
from .http_client import ensure_shared_client_session
from .person_entity_manager import (  # type: ignore[attr-defined]
    PersonEntityConfigInput,
    PersonEntityManager,
)
from .resilience import CircuitBreakerConfig, ResilienceManager
from .runtime_data import get_runtime_data
from .telemetry import ensure_runtime_performance_stats
from .types import (
    CoordinatorRejectionMetrics,
    JSONMutableMapping,
    PersonEntityStats,
    PersonNotificationContext,
)
from .utils import (
    ErrorContext,
    async_call_hass_service_if_available,
    build_error_context,
)
from .webhook_security import WebhookAuthenticator, WebhookSecurityError


def _dt_now() -> datetime:
    """Return the current time using the active Home Assistant dt helper."""  # noqa: E111

    try:  # noqa: E111
        from homeassistant.util import dt as dt_util_module
    except ImportError:  # noqa: E111
        return datetime.now()
    return dt_util_module.now()  # noqa: E111


if TYPE_CHECKING:
    from .feeding_manager import FeedingComplianceResult  # noqa: E111

_LOGGER = logging.getLogger(__name__)

# OPTIMIZE: Enhanced notification constants
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30
NOTIFICATION_EXPIRE_HOURS = 24
BATCH_PROCESSING_SIZE = 10
CACHE_CLEANUP_INTERVAL = 3600  # 1 hour
QUIET_TIME_CACHE_TTL = 300  # 5 minutes
CONFIG_CACHE_SIZE_LIMIT = 100
RATE_LIMIT_RETENTION_SECONDS = 7 * 24 * 3600


class NotificationType(Enum):
    """Types of notifications with priority hints."""  # noqa: E111

    FEEDING_REMINDER = "feeding_reminder"  # noqa: E111
    FEEDING_OVERDUE = "feeding_overdue"  # noqa: E111
    WALK_REMINDER = "walk_reminder"  # noqa: E111
    WALK_OVERDUE = "walk_overdue"  # noqa: E111
    HEALTH_ALERT = "health_alert"  # noqa: E111
    MEDICATION_REMINDER = "medication_reminder"  # noqa: E111
    VETERINARY_APPOINTMENT = "veterinary_appointment"  # noqa: E111
    WEIGHT_CHECK = "weight_check"  # noqa: E111
    SYSTEM_INFO = "system_info"  # noqa: E111
    SYSTEM_WARNING = "system_warning"  # noqa: E111
    SYSTEM_ERROR = "system_error"  # noqa: E111
    GEOFENCE_ALERT = "geofence_alert"  # OPTIMIZE: Added geofence alerts  # noqa: E111
    BATTERY_LOW = "battery_low"  # OPTIMIZE: Added battery alerts  # noqa: E111
    FEEDING_COMPLIANCE = "feeding_compliance"  # noqa: E111
    REPORT_READY = "report_ready"  # noqa: E111


class NotificationPriority(Enum):
    """Notification priority levels with numeric values for comparison."""  # noqa: E111

    LOW = "low"  # noqa: E111
    NORMAL = "normal"  # noqa: E111
    HIGH = "high"  # noqa: E111
    URGENT = "urgent"  # noqa: E111

    @property  # noqa: E111
    def value_numeric(self) -> int:  # noqa: E111
        """Get numeric value for priority comparison."""
        mapping = {
            "low": 1,
            "normal": 2,
            "high": 3,
            "urgent": 4,
        }
        return mapping[self.value]


class NotificationChannel(Enum):
    """Available notification channels."""  # noqa: E111

    PERSISTENT = "persistent"  # Home Assistant persistent notifications  # noqa: E111
    MOBILE = "mobile"  # Mobile app notifications  # noqa: E111
    EMAIL = "email"  # Email notifications  # noqa: E111
    SMS = "sms"  # SMS notifications  # noqa: E111
    WEBHOOK = "webhook"  # Custom webhook  # noqa: E111
    TTS = "tts"  # Text-to-speech  # noqa: E111
    MEDIA_PLAYER = "media_player"  # Media player announcements  # noqa: E111
    SLACK = "slack"  # OPTIMIZE: Added Slack notifications  # noqa: E111
    DISCORD = "discord"  # OPTIMIZE: Added Discord notifications  # noqa: E111


class NotificationQuietHoursConfig(TypedDict, total=False):
    """Raw quiet-hours payload accepted by the notification manager."""  # noqa: E111

    start: int  # noqa: E111
    end: int  # noqa: E111


class NotificationCustomSettings(TypedDict, total=False):
    """Channel-specific overrides applied during notification delivery."""  # noqa: E111

    mobile_service: str  # noqa: E111
    mobile_services: list[str]  # noqa: E111
    webhook_url: str  # noqa: E111
    webhook_secret: str  # noqa: E111
    webhook_header_prefix: str  # noqa: E111
    webhook_algorithm: str  # noqa: E111
    webhook_tolerance_seconds: int | float | str  # noqa: E111
    webhook_timeout: int | float | str  # noqa: E111
    tts_service: str  # noqa: E111
    tts_entity: str  # noqa: E111
    media_player_entity: str  # noqa: E111
    slack_service: str  # noqa: E111
    slack_channel: str  # noqa: E111
    discord_service: str  # noqa: E111
    discord_channel: str | None  # noqa: E111


class NotificationRateLimitConfig(TypedDict, total=False):
    """Per-channel rate limit definitions in minutes."""  # noqa: E111

    persistent_limit_minutes: int  # noqa: E111
    mobile_limit_minutes: int  # noqa: E111
    email_limit_minutes: int  # noqa: E111
    sms_limit_minutes: int  # noqa: E111
    webhook_limit_minutes: int  # noqa: E111
    tts_limit_minutes: int  # noqa: E111
    media_player_limit_minutes: int  # noqa: E111
    slack_limit_minutes: int  # noqa: E111
    discord_limit_minutes: int  # noqa: E111


type NotificationTemplateOverrides = dict[str, str]
"""Template override mapping keyed by template identifier."""


type NotificationTemplateData = JSONMutableMapping
"""JSON-compatible mapping injected into notification templates."""


type NotificationSendAttempts = dict[str, int]
"""Channel-specific delivery attempt counters."""


type NotificationServicePayload = JSONMutableMapping
"""Service call payload passed to Home Assistant notify integrations."""


def _empty_custom_settings() -> NotificationCustomSettings:
    """Return a freshly typed custom settings mapping."""  # noqa: E111

    return cast(NotificationCustomSettings, {})  # noqa: E111


def _empty_rate_limit_config() -> NotificationRateLimitConfig:
    """Return a freshly typed rate-limit configuration mapping."""  # noqa: E111

    return cast(NotificationRateLimitConfig, {})  # noqa: E111


class NotificationEventSerialized(TypedDict):
    """Serialized notification payload stored for diagnostics."""  # noqa: E111

    id: str  # noqa: E111
    dog_id: str | None  # noqa: E111
    notification_type: str  # noqa: E111
    priority: str  # noqa: E111
    title: str  # noqa: E111
    message: str  # noqa: E111
    created_at: str  # noqa: E111
    expires_at: str | None  # noqa: E111
    channels: list[str]  # noqa: E111
    data: NotificationTemplateData  # noqa: E111
    sent_to: list[str]  # noqa: E111
    failed_channels: list[str]  # noqa: E111
    retry_count: int  # noqa: E111
    acknowledged: bool  # noqa: E111
    acknowledged_at: str | None  # noqa: E111
    grouped_with: list[str]  # noqa: E111
    template_used: str | None  # noqa: E111
    send_attempts: NotificationSendAttempts  # noqa: E111
    targeted_persons: list[str]  # noqa: E111
    notification_services: list[str]  # noqa: E111
    failed_notification_services: list[str]  # noqa: E111


@dataclass
class NotificationDeliveryStatus:
    """Snapshot of delivery status for a notification service."""  # noqa: E111

    last_success_at: datetime | None = None  # noqa: E111
    last_failure_at: datetime | None = None  # noqa: E111
    consecutive_failures: int = 0  # noqa: E111
    total_failures: int = 0  # noqa: E111
    total_successes: int = 0  # noqa: E111
    last_error: str | None = None  # noqa: E111
    last_error_reason: str | None = None  # noqa: E111


class NotificationDeliveryDiagnostics(TypedDict):
    """Diagnostics payload for notification delivery outcomes."""  # noqa: E111

    total_services: int  # noqa: E111
    failed_services: list[str]  # noqa: E111
    services: dict[str, JSONMutableMapping]  # noqa: E111


class NotificationWebhookPayload(TypedDict):
    """Payload dispatched to webhook listeners."""  # noqa: E111

    id: str  # noqa: E111
    title: str  # noqa: E111
    message: str  # noqa: E111
    dog_id: str | None  # noqa: E111
    priority: str  # noqa: E111
    priority_numeric: int  # noqa: E111
    channels: list[str]  # noqa: E111
    created_at: str  # noqa: E111
    expires_at: str | None  # noqa: E111
    data: NotificationTemplateData  # noqa: E111
    targeted_persons: list[str]  # noqa: E111


class PersonDiscoveryResult(TypedDict):
    """Result payload returned by person discovery routines."""  # noqa: E111

    previous_count: int  # noqa: E111
    current_count: int  # noqa: E111
    persons_added: int  # noqa: E111
    persons_removed: int  # noqa: E111
    home_persons: int  # noqa: E111
    away_persons: int  # noqa: E111
    discovery_time: str  # noqa: E111


class PersonDiscoveryError(TypedDict):
    """Fallback payload returned when discovery is unavailable."""  # noqa: E111

    error: str  # noqa: E111


@dataclass
class NotificationConfig:
    """Enhanced configuration for notification delivery."""  # noqa: E111

    enabled: bool = True  # noqa: E111
    channels: list[NotificationChannel] = field(  # noqa: E111
        default_factory=lambda: [NotificationChannel.PERSISTENT],
    )
    priority_threshold: NotificationPriority = NotificationPriority.NORMAL  # noqa: E111
    quiet_hours: tuple[int, int] | None = None  # (start_hour, end_hour)  # noqa: E111
    retry_failed: bool = True  # noqa: E111
    custom_settings: NotificationCustomSettings = field(  # noqa: E111
        default_factory=_empty_custom_settings,
    )
    rate_limit: NotificationRateLimitConfig = field(  # noqa: E111
        default_factory=_empty_rate_limit_config,
    )  # OPTIMIZE: Added rate limiting
    batch_enabled: bool = True  # OPTIMIZE: Allow batching per config  # noqa: E111
    template_overrides: NotificationTemplateOverrides = field(  # noqa: E111
        default_factory=dict,
    )  # OPTIMIZE: Custom templates
    # NEW: Person entity targeting  # noqa: E114
    use_person_entities: bool = True  # Dynamic person targeting  # noqa: E111
    include_away_persons: bool = False  # Send to away persons  # noqa: E111
    fallback_to_static: bool = True  # Fallback if no persons found  # noqa: E111


@dataclass
class NotificationEvent:
    """Enhanced individual notification event."""  # noqa: E111

    id: str  # noqa: E111
    dog_id: str | None  # noqa: E111
    notification_type: NotificationType  # noqa: E111
    priority: NotificationPriority  # noqa: E111
    title: str  # noqa: E111
    message: str  # noqa: E111
    created_at: datetime  # noqa: E111
    expires_at: datetime | None = None  # noqa: E111
    channels: list[NotificationChannel] = field(default_factory=list)  # noqa: E111
    data: NotificationTemplateData = field(default_factory=dict)  # noqa: E111
    sent_to: list[NotificationChannel] = field(default_factory=list)  # noqa: E111
    failed_channels: list[NotificationChannel] = field(default_factory=list)  # noqa: E111
    retry_count: int = 0  # noqa: E111
    acknowledged: bool = False  # noqa: E111
    acknowledged_at: datetime | None = None  # noqa: E111

    # OPTIMIZE: Enhanced metadata  # noqa: E114
    grouped_with: list[str] = field(  # noqa: E111
        default_factory=list,
    )  # For batched notifications
    template_used: str | None = None  # noqa: E111
    send_attempts: NotificationSendAttempts = field(  # noqa: E111
        default_factory=dict,
    )  # Per-channel attempts

    # NEW: Person targeting metadata  # noqa: E114
    targeted_persons: list[str] = field(  # noqa: E111
        default_factory=list,
    )  # Person entity IDs
    notification_services: list[str] = field(  # noqa: E111
        default_factory=list,
    )  # Actual services used
    failed_notification_services: list[str] = field(default_factory=list)  # noqa: E111

    def to_dict(self) -> NotificationEventSerialized:  # noqa: E111
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
            "acknowledged_at": self.acknowledged_at.isoformat()
            if self.acknowledged_at
            else None,
            "grouped_with": self.grouped_with,
            "template_used": self.template_used,
            "send_attempts": self.send_attempts,
            "targeted_persons": self.targeted_persons,
            "notification_services": self.notification_services,
            "failed_notification_services": self.failed_notification_services,
        }

    def can_be_batched_with(self, other: NotificationEvent) -> bool:  # noqa: E111
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


type NotificationChannelHandler = Callable[[NotificationEvent], Awaitable[None]]
"""Callable signature for a channel-specific delivery handler."""


class NotificationCacheDiagnosticsMetadata(TypedDict):
    """Internal diagnostics metadata maintained by :class:`NotificationCache`."""  # noqa: E111

    cleanup_runs: int  # noqa: E111
    last_cleanup: datetime | None  # noqa: E111
    last_removed_entries: int  # noqa: E111


class NotificationCacheDiagnostics(TypedDict):
    """Diagnostics payload surfaced through coordinator snapshots."""  # noqa: E111

    cleanup_runs: int  # noqa: E111
    last_cleanup: str | None  # noqa: E111
    last_removed_entries: int  # noqa: E111
    lru_order: list[str]  # noqa: E111
    quiet_time_keys: list[str]  # noqa: E111
    person_targeting_keys: list[str]  # noqa: E111
    rate_limit_keys: dict[str, int]  # noqa: E111


class NotificationCacheStats(TypedDict):
    """Primary statistics exported by :class:`NotificationCache`."""  # noqa: E111

    config_entries: int  # noqa: E111
    quiet_time_entries: int  # noqa: E111
    rate_limit_entries: int  # noqa: E111
    person_targeting_entries: int  # noqa: E111
    cache_utilization: float  # noqa: E111


class NotificationCacheSnapshot(TypedDict):
    """Snapshot consumed by cache monitor diagnostics."""  # noqa: E111

    stats: NotificationCacheStats  # noqa: E111
    diagnostics: NotificationCacheDiagnostics  # noqa: E111


class NotificationPerformanceMetrics(TypedDict):
    """Structured performance metrics tracked by the manager."""  # noqa: E111

    notifications_sent: int  # noqa: E111
    notifications_failed: int  # noqa: E111
    batch_operations: int  # noqa: E111
    cache_hits: int  # noqa: E111
    cache_misses: int  # noqa: E111
    rate_limit_blocks: int  # noqa: E111
    average_delivery_time_ms: float  # noqa: E111
    person_targeted_notifications: int  # noqa: E111
    static_fallback_notifications: int  # noqa: E111
    config_updates: int  # noqa: E111
    retry_reschedules: int  # noqa: E111
    retry_successes: int  # noqa: E111


class NotificationManagerStats(TypedDict):
    """Telemetry payload returned by ``async_get_performance_statistics``."""  # noqa: E111

    total_notifications: int  # noqa: E111
    active_notifications: int  # noqa: E111
    configured_dogs: int  # noqa: E111
    type_distribution: dict[str, int]  # noqa: E111
    priority_distribution: dict[str, int]  # noqa: E111
    performance_metrics: NotificationPerformanceMetrics  # noqa: E111
    cache_stats: NotificationCacheStats  # noqa: E111
    batch_queue_size: int  # noqa: E111
    pending_batches: int  # noqa: E111
    available_channels: list[str]  # noqa: E111
    handlers_registered: int  # noqa: E111
    person_entity_stats: PersonEntityStats | None  # noqa: E111


class WebhookSecurityStatus(TypedDict):
    """Aggregated HMAC webhook security information."""  # noqa: E111

    configured: bool  # noqa: E111
    secure: bool  # noqa: E111
    hmac_ready: bool  # noqa: E111
    insecure_configs: tuple[str, ...]  # noqa: E111


class NotificationConfigInput(TypedDict, total=False):
    """Raw configuration payload accepted by ``async_initialize``."""  # noqa: E111

    enabled: bool  # noqa: E111
    channels: list[str]  # noqa: E111
    priority_threshold: str  # noqa: E111
    quiet_hours: NotificationQuietHoursConfig  # noqa: E111
    retry_failed: bool  # noqa: E111
    custom_settings: NotificationCustomSettings  # noqa: E111
    rate_limit: NotificationRateLimitConfig  # noqa: E111
    batch_enabled: bool  # noqa: E111
    template_overrides: NotificationTemplateOverrides  # noqa: E111
    use_person_entities: bool  # noqa: E111
    include_away_persons: bool  # noqa: E111
    fallback_to_static: bool  # noqa: E111


type NotificationConfigInputMap = Mapping[str, NotificationConfigInput]
"""Mapping of configuration identifiers to raw notification payloads."""


ConfigT = TypeVar("ConfigT", bound=NotificationConfig)


class NotificationCache[ConfigT: NotificationConfig]:
    """OPTIMIZE: Advanced caching system for notification configurations and state."""  # noqa: E111

    def __init__(self, max_size: int = CONFIG_CACHE_SIZE_LIMIT) -> None:  # noqa: E111
        """Initialize notification cache.

        Args:
            max_size: Maximum cache entries
        """
        self._config_cache: dict[str, tuple[ConfigT, float, datetime]] = {}
        self._quiet_time_cache: dict[str, tuple[bool, float, datetime]] = {}
        self._rate_limit_cache: dict[str, dict[str, tuple[float, datetime]]] = {}
        self._person_targeting_cache: dict[
            str,
            # NEW
            tuple[list[str], float, datetime],
        ] = {}
        self._max_size = max_size
        self._access_order: deque[str] = deque()
        self._diagnostics: NotificationCacheDiagnosticsMetadata = {
            "cleanup_runs": 0,
            "last_cleanup": None,
            "last_removed_entries": 0,
        }

    def get_config(self, config_key: str) -> ConfigT | None:  # noqa: E111
        """Get cached configuration.

        Args:
            config_key: Configuration key

        Returns:
            Cached configuration or None
        """
        if config_key in self._config_cache:
            config, _monotonic, _timestamp = self._config_cache[config_key]  # noqa: E111
            # Update access order for LRU  # noqa: E114
            if config_key in self._access_order:  # noqa: E111
                self._access_order.remove(config_key)
            self._access_order.append(config_key)  # noqa: E111
            return config  # noqa: E111
        return None

    def set_config(self, config_key: str, config: ConfigT) -> None:  # noqa: E111
        """Set configuration with LRU eviction.

        Args:
            config_key: Configuration key
            config: Configuration to cache
        """
        # Evict oldest if at capacity
        if (
            len(self._config_cache) >= self._max_size
            and config_key not in self._config_cache
        ):
            oldest = self._access_order.popleft()  # noqa: E111
            del self._config_cache[oldest]  # noqa: E111

        now = _dt_now()
        self._config_cache[config_key] = (config, time.monotonic(), now)

        # Update access order
        if config_key in self._access_order:
            self._access_order.remove(config_key)  # noqa: E111
        self._access_order.append(config_key)

    def get_person_targeting_cache(  # noqa: E111
        self,
        cache_key: str,
        ttl_seconds: int = 180,
    ) -> list[str] | None:
        """Get cached person targeting results.

        Args:
            cache_key: Cache key for targeting
            ttl_seconds: Time to live in seconds

        Returns:
            Cached targeting list or None
        """
        if cache_key in self._person_targeting_cache:
            targets, cache_monotonic, _timestamp = self._person_targeting_cache[
                cache_key
            ]  # noqa: E111
            if time.monotonic() - cache_monotonic < ttl_seconds:  # noqa: E111
                return targets
        return None

    def set_person_targeting_cache(self, cache_key: str, targets: list[str]) -> None:  # noqa: E111
        """Cache person targeting results.

        Args:
            cache_key: Cache key
            targets: Target services list
        """
        now = _dt_now()
        self._person_targeting_cache[cache_key] = (targets, time.monotonic(), now)

    def is_quiet_time_cached(self, config_key: str) -> tuple[bool, bool]:  # noqa: E111
        """Check if quiet time status is cached.

        Args:
            config_key: Configuration key

        Returns:
            Tuple of (is_cached, is_quiet_time)
        """
        if config_key in self._quiet_time_cache:
            cached_value = self._quiet_time_cache[config_key]  # noqa: E111
            if len(cached_value) == 2:  # noqa: E111
                is_quiet, cache_reference = cached_value
            else:  # noqa: E111
                is_quiet, cache_reference, _timestamp = cached_value
            cache_monotonic = self._quiet_cache_monotonic(cache_reference)  # noqa: E111
            now_reference = (  # noqa: E111
                _dt_now().timestamp()
                if isinstance(cache_reference, datetime)
                else time.monotonic()
            )
            if now_reference - cache_monotonic < QUIET_TIME_CACHE_TTL:  # noqa: E111
                return True, is_quiet
        return False, False

    def set_quiet_time_cache(self, config_key: str, is_quiet: bool) -> None:  # noqa: E111
        """Cache quiet time status.

        Args:
            config_key: Configuration key
            is_quiet: Whether it's currently quiet time
        """
        now = _dt_now()
        self._quiet_time_cache[config_key] = (is_quiet, time.monotonic(), now)

    @staticmethod  # noqa: E111
    def _quiet_cache_monotonic(value: object) -> float:  # noqa: E111
        """Convert quiet-cache timestamp payloads to monotonic-like seconds."""

        if isinstance(value, datetime):
            return value.timestamp()  # noqa: E111
        if isinstance(value, int | float):
            return float(value)  # noqa: E111
        return 0.0

    def check_rate_limit(  # noqa: E111
        self,
        config_key: str,
        channel: str,
        limit_minutes: int,
    ) -> bool:
        """Check if rate limit allows sending.

        Args:
            config_key: Configuration key
            channel: Notification channel
            limit_minutes: Rate limit in minutes

        Returns:
            True if sending is allowed
        """
        now_monotonic = time.monotonic()
        now = _dt_now()

        if config_key not in self._rate_limit_cache:
            self._rate_limit_cache[config_key] = {}  # noqa: E111

        channel_cache = self._rate_limit_cache[config_key]

        if channel in channel_cache:
            last_sent_monotonic, _timestamp = channel_cache[channel]  # noqa: E111
            if now_monotonic - last_sent_monotonic < limit_minutes * 60:  # noqa: E111
                return False

        # Update rate limit cache
        channel_cache[channel] = (now_monotonic, now)
        return True

    def cleanup_expired(self) -> int:  # noqa: E111
        """Clean up expired cache entries.

        Returns:
            Number of entries cleaned up
        """
        now_monotonic = time.monotonic()
        now = _dt_now()
        cleaned = 0

        # Clean quiet time cache
        expired_quiet_keys = [
            key
            for key, entry in self._quiet_time_cache.items()
            if (
                (
                    _dt_now().timestamp() - self._quiet_cache_monotonic(entry[1])
                    if len(entry) >= 2 and isinstance(entry[1], datetime)
                    else now_monotonic
                    - self._quiet_cache_monotonic(entry[1] if len(entry) >= 2 else 0.0)
                )
                > QUIET_TIME_CACHE_TTL
            )
        ]
        for key in expired_quiet_keys:
            del self._quiet_time_cache[key]  # noqa: E111
            cleaned += 1  # noqa: E111

        # Clean person targeting cache (5 minute TTL)
        expired_person_keys = [
            key
            for key, (
                _,
                cache_monotonic,
                _timestamp,
            ) in self._person_targeting_cache.items()
            if now_monotonic - cache_monotonic > 300
        ]
        for key in expired_person_keys:
            del self._person_targeting_cache[key]  # noqa: E111
            cleaned += 1  # noqa: E111

        # Clean rate limit cache (older than 24 hours)
        for channels in self._rate_limit_cache.values():
            expired_channels = [  # noqa: E111
                channel
                for channel, (last_sent_monotonic, _timestamp) in channels.items()
                if now_monotonic - last_sent_monotonic > 86400
            ]
            for channel in expired_channels:  # noqa: E111
                del channels[channel]
                cleaned += 1

        self._diagnostics["cleanup_runs"] += 1
        self._diagnostics["last_cleanup"] = now
        self._diagnostics["last_removed_entries"] = cleaned
        return cleaned

    def get_stats(self) -> NotificationCacheStats:  # noqa: E111
        """Get cache statistics."""
        max_size = self._max_size
        cache_utilization = (
            (len(self._config_cache) / max_size * 100) if max_size > 0 else 0.0
        )

        stats: NotificationCacheStats = {
            "config_entries": len(self._config_cache),
            "quiet_time_entries": len(self._quiet_time_cache),
            "rate_limit_entries": sum(
                len(channels) for channels in self._rate_limit_cache.values()
            ),
            "person_targeting_entries": len(self._person_targeting_cache),
            "cache_utilization": cache_utilization,
        }
        return stats

    def get_diagnostics(self) -> NotificationCacheDiagnostics:  # noqa: E111
        """Return diagnostics metadata consumed by coordinator snapshots."""

        metadata = self._diagnostics
        last_cleanup = metadata["last_cleanup"]

        diagnostics: NotificationCacheDiagnostics = {
            "cleanup_runs": metadata["cleanup_runs"],
            "last_cleanup": last_cleanup.isoformat() if last_cleanup else None,
            "last_removed_entries": metadata["last_removed_entries"],
            "lru_order": list(self._access_order),
            "quiet_time_keys": list(self._quiet_time_cache),
            "person_targeting_keys": list(self._person_targeting_cache),
            "rate_limit_keys": {
                key: len(channels) for key, channels in self._rate_limit_cache.items()
            },
        }
        return diagnostics

    def coordinator_snapshot(self) -> NotificationCacheSnapshot:  # noqa: E111
        """Return a coordinator-friendly snapshot of cache telemetry."""

        snapshot: NotificationCacheSnapshot = {
            "stats": self.get_stats(),
            "diagnostics": self.get_diagnostics(),
        }
        return snapshot


class PawControlNotificationManager:
    """Advanced notification management system with performance optimizations.

    OPTIMIZE: Enhanced with batch processing, advanced caching, rate limiting,
    person entity integration, and comprehensive performance monitoring for Platinum-targeted quality.
    """  # noqa: E111, E501

    def __init__(  # noqa: E111
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        session: ClientSession,
    ) -> None:
        """Initialize advanced notification manager.

        Args:
            hass: Home Assistant instance
            entry_id: Config entry ID for namespacing
            session: Home Assistant managed session for outbound calls
        """
        self._hass = hass
        self._entry_id = entry_id
        self._notifications: dict[str, NotificationEvent] = {}
        self._configs: dict[str, NotificationConfig] = {}
        self._handlers: dict[NotificationChannel, NotificationChannelHandler] = {}
        self._lock = asyncio.Lock()
        self._session = ensure_shared_client_session(
            session,
            owner="PawControlNotificationManager",
        )

        # NEW: Person entity manager for dynamic targeting
        self._person_manager: PersonEntityManager | None = None

        # RESILIENCE: Initialize resilience manager for notification channels
        self.resilience_manager = ResilienceManager(hass)
        self._channel_circuit_config = CircuitBreakerConfig(
            failure_threshold=5,  # More tolerance for notifications
            success_threshold=3,  # Need more successes to close
            timeout_seconds=120.0,  # Longer timeout for notifications
        )

        # OPTIMIZE: Enhanced background tasks
        self._retry_task: asyncio.Task[None] | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._batch_task: asyncio.Task[None] | None = None

        # Lightweight runtime state
        self._rate_limit_last_sent: dict[str, dict[str, float]] = {}
        self._batch_queue: deque[NotificationEvent] = deque()
        self._pending_batches: dict[str, list[NotificationEvent]] = {}
        self._delivery_status: dict[str, NotificationDeliveryStatus] = {}

        # OPTIMIZE: Performance monitoring
        self._performance_metrics: NotificationPerformanceMetrics = {
            "notifications_sent": 0,
            "notifications_failed": 0,
            "batch_operations": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "rate_limit_blocks": 0,
            "average_delivery_time_ms": 0.0,
            "person_targeted_notifications": 0,  # NEW
            "static_fallback_notifications": 0,  # NEW
            "config_updates": 0,  # NEW: track configuration changes
            "retry_reschedules": 0,  # NEW: background retry attempts
            "retry_successes": 0,  # NEW: successful retry deliveries
        }
        self._cache: NotificationCache[NotificationConfig] = NotificationCache()
        self._cache_monitor_registrar: CacheMonitorRegistrar | None = None

        # OPTIMIZE: Template system for customizable notifications
        self._templates: dict[str, str] = {
            "feeding_reminder": "🍽️ {title}\n{message}",
            "walk_reminder": "🚶 {title}\n{message}",
            "health_alert": "⚕️ {title}\n{message}",
            "batch_summary": "📋 {count} notifications for {dog_name}:\n{summary}",
            # NEW
            "person_targeted": "👤 {title} (Targeted: {person_names})\n{message}",
        }

        # Setup default handlers
        self._setup_default_handlers()

    @property  # noqa: E111
    def session(self) -> ClientSession:  # noqa: E111
        """Return the shared aiohttp session used for webhooks."""

        return self._session

    def get_performance_metrics(self) -> NotificationPerformanceMetrics:  # noqa: E111
        """Return a shallow copy of the performance metrics payload."""

        metrics: NotificationPerformanceMetrics = {
            **self._performance_metrics,
        }
        return metrics

    def get_delivery_status_snapshot(self) -> NotificationDeliveryDiagnostics:  # noqa: E111
        """Return a diagnostics payload for notification delivery status."""

        services: dict[str, JSONMutableMapping] = {}
        failed_services: list[str] = []

        for service_name, status in self._delivery_status.items():
            payload: JSONMutableMapping = {  # noqa: E111
                "last_success_at": status.last_success_at.isoformat()
                if status.last_success_at
                else None,
                "last_failure_at": status.last_failure_at.isoformat()
                if status.last_failure_at
                else None,
                "consecutive_failures": status.consecutive_failures,
                "total_failures": status.total_failures,
                "total_successes": status.total_successes,
                "last_error": status.last_error,
                "last_error_reason": status.last_error_reason,
            }
            services[service_name] = payload  # noqa: E111
            if status.consecutive_failures > 0:  # noqa: E111
                failed_services.append(service_name)

        return {
            "total_services": len(services),
            "failed_services": failed_services,
            "services": services,
        }

    def _record_delivery_success(self, service_name: str) -> None:  # noqa: E111
        """Persist a successful delivery outcome for diagnostics."""

        status = self._delivery_status.setdefault(
            service_name,
            NotificationDeliveryStatus(),
        )
        status.last_success_at = dt_util.now()
        status.total_successes += 1
        status.consecutive_failures = 0
        status.last_error = None
        status.last_error_reason = None

    def _record_delivery_failure(  # noqa: E111
        self,
        service_name: str,
        *,
        reason: str,
        error: Exception | None = None,
    ) -> None:
        """Persist a failed delivery outcome for diagnostics."""

        error_context = build_error_context(reason, error)
        status = self._delivery_status.setdefault(
            service_name,
            NotificationDeliveryStatus(),
        )
        status.last_failure_at = dt_util.now()
        status.total_failures += 1
        status.consecutive_failures += 1
        status.last_error_reason = error_context.classification
        status.last_error = error_context.message
        self._record_delivery_failure_rejection_metrics(error_context)

    def _record_delivery_failure_rejection_metrics(  # noqa: E111
        self,
        error_context: ErrorContext,
    ) -> None:
        """Store delivery failure reasons in shared rejection metrics."""

        runtime_data = get_runtime_data(self._hass, self._entry_id)
        if runtime_data is None:
            return  # noqa: E111

        performance_stats = ensure_runtime_performance_stats(runtime_data)
        rejection_metrics_raw = performance_stats.get("rejection_metrics")
        if isinstance(rejection_metrics_raw, MutableMapping):
            rejection_metrics = cast(CoordinatorRejectionMetrics, rejection_metrics_raw)  # noqa: E111
        else:
            rejection_metrics = default_rejection_metrics()  # noqa: E111
            performance_stats["rejection_metrics"] = rejection_metrics  # noqa: E111

        reason_text = error_context.classification.strip() or "unknown"

        failure_reasons_raw = rejection_metrics.get("failure_reasons")
        if isinstance(failure_reasons_raw, MutableMapping):
            failure_reasons = cast(MutableMapping[str, int], failure_reasons_raw)  # noqa: E111
        else:
            failure_reasons = {}  # noqa: E111
            rejection_metrics["failure_reasons"] = failure_reasons  # noqa: E111

        failure_reasons[reason_text] = int(failure_reasons.get(reason_text, 0) or 0) + 1
        rejection_metrics["last_failure_reason"] = reason_text

    def _notify_service_available(self, service_name: str) -> bool:  # noqa: E111
        """Return True when a notify service is registered."""

        services = getattr(self._hass, "services", None)
        async_services = getattr(services, "async_services", None)
        if not callable(async_services):
            return False  # noqa: E111

        domain_services = async_services().get("notify", {})
        return service_name in domain_services

    def _setup_default_handlers(self) -> None:  # noqa: E111
        """Setup default notification handlers with error handling."""
        handlers = {
            NotificationChannel.PERSISTENT: self._send_persistent_notification,
            NotificationChannel.MOBILE: self._send_mobile_notification,
            NotificationChannel.TTS: self._send_tts_notification,
            NotificationChannel.MEDIA_PLAYER: self._send_media_player_notification,
            NotificationChannel.SLACK: self._send_slack_notification,
            NotificationChannel.DISCORD: self._send_discord_notification,
            NotificationChannel.WEBHOOK: self._send_webhook_notification,
        }

        # Wrap handlers with error handling and performance monitoring
        for channel, handler in handlers.items():
            self._handlers[channel] = self._wrap_handler_with_monitoring(  # noqa: E111
                handler,
                channel,
            )

    def _wrap_handler_with_monitoring(  # noqa: E111
        self,
        handler: NotificationChannelHandler,
        channel: NotificationChannel,
    ) -> NotificationChannelHandler:
        """Wrap handler with performance monitoring.

        Args:
            handler: Original handler function
            channel: Notification channel

        Returns:
            Wrapped handler with monitoring
        """

        async def wrapped_handler(notification: NotificationEvent) -> None:
            start_time = dt_util.now()  # noqa: E111
            try:  # noqa: E111
                await handler(notification)
                self._performance_metrics["notifications_sent"] += 1
            except Exception as err:  # noqa: E111
                self._performance_metrics["notifications_failed"] += 1
                _LOGGER.error(
                    "Handler for %s failed on notification %s: %s",
                    channel.value,
                    notification.id,
                    err,
                )
                raise
            finally:  # noqa: E111
                # Update average delivery time
                delivery_time_ms = (dt_util.now() - start_time).total_seconds() * 1000
                current_avg = self._performance_metrics["average_delivery_time_ms"]
                total_sent = self._performance_metrics["notifications_sent"]

                if total_sent > 0:
                    new_avg = (
                        current_avg * (total_sent - 1) + delivery_time_ms
                    ) / total_sent  # noqa: E111
                    self._performance_metrics["average_delivery_time_ms"] = new_avg  # noqa: E111

        return wrapped_handler

    async def async_initialize(  # noqa: E111
        self,
        notification_configs: NotificationConfigInputMap | None = None,
        person_entity_config: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize notification configurations with enhanced validation.

        Args:
            notification_configs: Configuration for each dog/system
            person_entity_config: Configuration for person entity integration
        """
        async with self._lock:
            configs: NotificationConfigInputMap = (  # noqa: E111
                {}
                if notification_configs is None
                else dict(
                    notification_configs,
                )
            )

            for config_id, config_data in configs.items():  # noqa: E111
                try:
                    # Parse channels with validation  # noqa: E114
                    channels: list[NotificationChannel] = []  # noqa: E111
                    raw_channels = config_data.get("channels", ["persistent"])  # noqa: E111
                    for channel_str in cast(Sequence[str], raw_channels):  # noqa: E111
                        try:
                            channels.append(NotificationChannel(channel_str))  # noqa: E111
                        except ValueError:
                            _LOGGER.warning(  # noqa: E111
                                "Invalid notification channel: %s",
                                channel_str,
                            )

                    # Parse priority threshold  # noqa: E114
                    priority_threshold = NotificationPriority(  # noqa: E111
                        config_data.get("priority_threshold", "normal"),
                    )

                    # Parse quiet hours  # noqa: E114
                    quiet_hours = None  # noqa: E111
                    if "quiet_hours" in config_data:  # noqa: E111
                        quiet_config = config_data["quiet_hours"]
                        quiet_start = quiet_config.get("start", 22)
                        quiet_end = quiet_config.get("end", 7)
                        quiet_hours = (quiet_start, quiet_end)

                    # Parse rate limits  # noqa: E114
                    rate_limit: NotificationRateLimitConfig  # noqa: E111
                    if "rate_limit" in config_data:  # noqa: E111
                        rate_limit = config_data["rate_limit"]
                    else:  # noqa: E111
                        rate_limit = _empty_rate_limit_config()

                    # Parse template overrides  # noqa: E114
                    if "template_overrides" in config_data:  # noqa: E111
                        template_overrides = config_data["template_overrides"]
                    else:  # noqa: E111
                        template_overrides = {}

                    if "custom_settings" in config_data:  # noqa: E111
                        custom_settings = config_data["custom_settings"]
                    else:  # noqa: E111
                        custom_settings = _empty_custom_settings()

                    config = NotificationConfig(  # noqa: E111
                        enabled=config_data.get("enabled", True),
                        channels=channels,
                        priority_threshold=priority_threshold,
                        quiet_hours=quiet_hours,
                        retry_failed=config_data.get("retry_failed", True),
                        custom_settings=custom_settings,
                        rate_limit=rate_limit,
                        batch_enabled=config_data.get("batch_enabled", True),
                        template_overrides=template_overrides,
                        # NEW: Person entity settings
                        use_person_entities=config_data.get(
                            "use_person_entities",
                            True,
                        ),
                        include_away_persons=config_data.get(
                            "include_away_persons",
                            False,
                        ),
                        fallback_to_static=config_data.get(
                            "fallback_to_static",
                            True,
                        ),
                    )

                    self._configs[config_id] = config  # noqa: E111

                except Exception as err:
                    _LOGGER.error(  # noqa: E111
                        "Failed to parse config for %s: %s",
                        config_id,
                        err,
                    )

        # NEW: Initialize person entity manager
        await self._initialize_person_manager(person_entity_config)

        # Start background tasks
        await self._start_background_tasks()

    async def _initialize_person_manager(  # noqa: E111
        self,
        config: Mapping[str, object] | None = None,
    ) -> None:
        """Initialize person entity manager for dynamic targeting.

        Args:
            config: Person entity configuration
        """
        try:
            self._person_manager = PersonEntityManager(  # noqa: E111
                self._hass,
                self._entry_id,
            )

            # Use provided config or defaults  # noqa: E114
            person_config: PersonEntityConfigInput  # noqa: E111
            if config is None:  # noqa: E111
                person_config = {
                    "enabled": True,
                    "auto_discovery": True,
                    "discovery_interval": 300,
                    "include_away_persons": False,
                    "fallback_to_static": True,
                }
            else:  # noqa: E111
                person_config = cast(PersonEntityConfigInput, dict(config))

            await self._person_manager.async_initialize(person_config)  # noqa: E111
            self._register_person_cache_monitor()  # noqa: E111

            _LOGGER.info(  # noqa: E111
                "Person entity manager initialized for notification targeting",
            )

        except Exception as err:
            _LOGGER.error(  # noqa: E111
                "Failed to initialize person entity manager: %s",
                err,
            )
            self._person_manager = None  # noqa: E111

    async def _start_background_tasks(self) -> None:  # noqa: E111
        """Start background processing tasks."""
        # Start retry task
        if self._retry_task is None:
            self._retry_task = asyncio.create_task(  # noqa: E111
                self._retry_failed_notifications(),
            )

        # Start cleanup task
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(  # noqa: E111
                self._cleanup_expired_notifications(),
            )

        # Start batch processing task
        if self._batch_task is None:
            self._batch_task = asyncio.create_task(  # noqa: E111
                self._process_batch_notifications(),
            )

    async def async_set_priority_threshold(  # noqa: E111
        self,
        dog_id: str,
        priority: NotificationPriority,
    ) -> None:
        """Set the default notification priority threshold for a dog."""

        config_key = dog_id or "system"

        async with self._lock:
            config = self._configs.get(config_key)  # noqa: E111
            if config is None:  # noqa: E111
                config = NotificationConfig()

            if config.priority_threshold == priority:  # noqa: E111
                # Ensure cache stays in sync even when value is unchanged
                return

            config.priority_threshold = priority  # noqa: E111
            self._configs[config_key] = config  # noqa: E111
            self._performance_metrics["config_updates"] += 1  # noqa: E111

        _LOGGER.info(
            "Updated notification priority for %s to %s",
            config_key,
            priority.value,
        )

    async def async_send_notification(  # noqa: E111
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        dog_id: str | None = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        data: NotificationTemplateData | None = None,
        expires_in: timedelta | None = None,
        force_channels: list[NotificationChannel] | None = None,
        allow_batching: bool = True,
        override_person_targeting: bool = False,
    ) -> str:
        """Send a notification with advanced processing.

        OPTIMIZE: Enhanced with batching, caching, rate limiting, templates, and person targeting.

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
            override_person_targeting: Skip person targeting and use static config

        Returns:
            Notification ID
        """  # noqa: E501
        async with self._lock:
            # Generate notification ID  # noqa: E114
            notification_id = f"{notification_type.value}_{uuid4().hex}"  # noqa: E111

            # Determine configuration to use  # noqa: E114
            config_key = dog_id if dog_id else "system"  # noqa: E111
            config = await self._get_config_cached(config_key)  # noqa: E111

            # Check if notifications are enabled  # noqa: E114
            if not config.enabled:  # noqa: E111
                _LOGGER.debug("Notifications disabled for %s", config_key)
                return notification_id

            # Check priority threshold with optimized comparison  # noqa: E114
            if priority.value_numeric < config.priority_threshold.value_numeric:  # noqa: E111
                _LOGGER.debug(
                    "Notification priority %s below threshold %s",
                    priority.value,
                    config.priority_threshold.value,
                )
                return notification_id

            # OPTIMIZE: Check quiet hours with caching  # noqa: E114
            if await self._is_quiet_time_cached(config_key, config, priority):  # noqa: E111
                _LOGGER.debug("Notification suppressed due to quiet hours")
                return notification_id

            # NEW: Determine notification targets using person entities  # noqa: E114
            channels = force_channels if force_channels else config.channels  # noqa: E111
            targeted_persons = []  # noqa: E111
            notification_services = []  # noqa: E111

            if (  # noqa: E111
                not override_person_targeting
                and config.use_person_entities
                and self._person_manager
                and NotificationChannel.MOBILE in channels
            ):
                # Use person entity targeting
                person_targets = await self._get_person_notification_targets(
                    config_key,
                    config,
                )
                if person_targets:
                    notification_services.extend(person_targets)  # noqa: E111
                    targeted_persons = [  # noqa: E111
                        person.entity_id
                        for person in (
                            self._person_manager.get_home_persons()
                            if not config.include_away_persons
                            else self._person_manager.get_all_persons()
                        )
                    ]
                    self._performance_metrics["person_targeted_notifications"] += 1  # noqa: E111

                    _LOGGER.debug(  # noqa: E111
                        "Person targeting: %d services for %d persons",
                        len(person_targets),
                        len(targeted_persons),
                    )
                elif config.fallback_to_static:
                    # Fallback to static configuration  # noqa: E114
                    notification_services.extend(  # noqa: E111
                        config.custom_settings.get(
                            "mobile_services",
                            ["mobile_app"],
                        ),
                    )
                    self._performance_metrics["static_fallback_notifications"] += 1  # noqa: E111

                    _LOGGER.debug(  # noqa: E111
                        "Using static fallback for mobile notifications",
                    )

            # OPTIMIZE: Check rate limits  # noqa: E114
            allowed_channels = []  # noqa: E111
            for channel in channels:  # noqa: E111
                rate_limit_key = f"{channel.value}_limit_minutes"
                limit_minutes = cast(
                    int,
                    config.rate_limit.get(rate_limit_key, 0),
                )

                if limit_minutes == 0 or self._check_rate_limit(
                    config_key,
                    channel.value,
                    limit_minutes,
                ):
                    allowed_channels.append(channel)  # noqa: E111
                else:
                    self._performance_metrics["rate_limit_blocks"] += 1  # noqa: E111
                    _LOGGER.debug(  # noqa: E111
                        "Rate limit blocked %s for %s",
                        channel.value,
                        config_key,
                    )

            if not allowed_channels:  # noqa: E111
                _LOGGER.warning("All channels rate limited for %s", config_key)
                return notification_id

            # Apply template if available with person context  # noqa: E114
            template_data: NotificationTemplateData = (  # noqa: E111
                cast(NotificationTemplateData, dict(data))
                if data is not None
                else cast(NotificationTemplateData, {})
            )
            if targeted_persons and self._person_manager:  # noqa: E111
                person_context = self._person_manager.get_notification_context()
                if isinstance(person_context, Mapping):
                    template_data.update(  # noqa: E111
                        cast(NotificationTemplateData, dict(person_context)),
                    )
                    home_names = person_context.get("home_person_names")  # noqa: E111
                    if isinstance(home_names, Sequence) and not isinstance(  # noqa: E111
                        home_names,
                        str | bytes,
                    ):
                        template_data["person_names"] = ", ".join(
                            name for name in home_names if isinstance(name, str)
                        )

            formatted_title, formatted_message = self._apply_template(  # noqa: E111
                notification_type,
                title,
                message,
                config,
                template_data,
            )

            # Calculate expiration  # noqa: E114
            expires_at = None  # noqa: E111
            if expires_in:  # noqa: E111
                expires_at = dt_util.now() + expires_in
            elif notification_type in [  # noqa: E111
                NotificationType.FEEDING_REMINDER,
                NotificationType.WALK_REMINDER,
                NotificationType.MEDICATION_REMINDER,
            ]:
                # Auto-expire reminders after 24 hours
                expires_at = dt_util.now() + timedelta(hours=NOTIFICATION_EXPIRE_HOURS)

            # Create notification event  # noqa: E114
            notification = NotificationEvent(  # noqa: E111
                id=notification_id,
                dog_id=dog_id,
                notification_type=notification_type,
                priority=priority,
                title=formatted_title,
                message=formatted_message,
                created_at=dt_util.now(),
                expires_at=expires_at,
                channels=allowed_channels,
                data=template_data,
                template_used=self._get_template_name(notification_type),
                targeted_persons=targeted_persons,
                notification_services=notification_services,
            )

            # Store notification  # noqa: E114
            self._notifications[notification_id] = notification  # noqa: E111

            # OPTIMIZE: Handle batching for eligible notifications  # noqa: E114
            if (
                allow_batching
                and config.batch_enabled
                and self._should_batch(notification)
            ):  # noqa: E111
                await self._add_to_batch_queue(notification)
                _LOGGER.debug(
                    "Added notification %s to batch queue",
                    notification_id,
                )
            else:  # noqa: E111
                # Send immediately
                await self._send_to_channels(notification)
                _LOGGER.info(
                    "Sent notification %s: %s (%s) [%d targets]",
                    notification_id,
                    formatted_title,
                    priority.value,
                    len(notification_services)
                    if notification_services
                    else len(allowed_channels),
                )

            return notification_id  # noqa: E111

    async def _get_person_notification_targets(  # noqa: E111
        self,
        config_key: str,
        config: NotificationConfig,
    ) -> list[str]:
        """Get notification targets based on person entities.

        Args:
            config_key: Configuration key forwarded to person manager lookups
            config: Notification configuration

        Returns:
            List of notification service names
        """
        if not self._person_manager:
            return []  # noqa: E111

        return self._person_manager.get_notification_targets(
            include_away=config.include_away_persons,
            cache_key=f"person_targets_{config_key}_{config.include_away_persons}",
        )

    async def _get_config_cached(self, config_key: str) -> NotificationConfig:  # noqa: E111
        """Get configuration directly from in-memory config state."""

        cached = self._cache.get_config(config_key)
        if cached is not None:
            self._performance_metrics["cache_hits"] += 1  # noqa: E111
            return cached  # noqa: E111

        config = self._configs.get(config_key)
        if config is None:
            self._performance_metrics["cache_misses"] += 1  # noqa: E111
            return NotificationConfig()  # noqa: E111

        self._cache.set_config(config_key, config)
        self._performance_metrics["cache_misses"] += 1
        return config

    async def _is_quiet_time_cached(  # noqa: E111
        self,
        config_key: str,
        config: NotificationConfig,
        priority: NotificationPriority,
    ) -> bool:
        """Check if it's currently quiet time for the provided configuration.

        Args:
            config_key: Configuration key (kept for API compatibility)
            config: Notification configuration
            priority: Notification priority

        Returns:
            True if in quiet time and should suppress notification
        """
        # Urgent notifications always go through
        if priority == NotificationPriority.URGENT:
            return False  # noqa: E111

        if not config.quiet_hours:
            return False  # noqa: E111

        is_cached, cached_value = self._cache.is_quiet_time_cached(config_key)
        if is_cached:
            return cached_value  # noqa: E111

        # Calculate quiet time status
        now = _dt_now()
        current_hour = now.hour
        start_hour, end_hour = config.quiet_hours

        # Handle quiet hours that cross midnight
        if start_hour > end_hour:  # e.g., 22:00 to 07:00
            is_quiet = current_hour >= start_hour or current_hour < end_hour  # noqa: E111
        else:  # e.g., 01:00 to 06:00
            is_quiet = start_hour <= current_hour < end_hour  # noqa: E111

        self._cache.set_quiet_time_cache(config_key, is_quiet)
        return is_quiet

    def _check_rate_limit(  # noqa: E111
        self,
        config_key: str,
        channel: str,
        limit_minutes: int,
    ) -> bool:
        """Return True when the notification is allowed by rate limit."""

        now = time.monotonic()
        channel_state = self._rate_limit_last_sent.setdefault(config_key, {})
        last_sent = channel_state.get(channel)
        window = float(limit_minutes) * 60.0
        if last_sent is not None and now - last_sent < window:
            return False  # noqa: E111

        channel_state[channel] = now

        cutoff = now - RATE_LIMIT_RETENTION_SECONDS
        stale_channels = [
            channel_name
            for channel_name, timestamp in channel_state.items()
            if timestamp < cutoff
        ]
        for channel_name in stale_channels:
            del channel_state[channel_name]  # noqa: E111

        stale_configs = [
            key for key, state in self._rate_limit_last_sent.items() if not state
        ]
        for key in stale_configs:
            del self._rate_limit_last_sent[key]  # noqa: E111

        return True

    def _apply_template(  # noqa: E111
        self,
        notification_type: NotificationType,
        title: str,
        message: str,
        config: NotificationConfig,
        data: NotificationTemplateData,
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
            self._templates.get(template_name),
        )

        if not template:
            return title, message  # noqa: E111

        try:
            # Prepare template variables  # noqa: E114
            template_vars = {  # noqa: E111
                "title": title,
                "message": message,
                **data,
            }

            formatted = template.format(**template_vars)  # noqa: E111

            # Split back into title and message if template contains both  # noqa: E114
            if "\n" in formatted:  # noqa: E111
                parts = formatted.split("\n", 1)
                return parts[0], parts[1]
            return formatted, message  # noqa: E111

        except (KeyError, ValueError) as err:
            _LOGGER.warning(  # noqa: E111
                "Template formatting failed for %s: %s",
                template_name,
                err,
            )
            return title, message  # noqa: E111

    def _get_template_name(self, notification_type: NotificationType) -> str:  # noqa: E111
        """Get template name for notification type.

        Args:
            notification_type: Notification type

        Returns:
            Template name
        """
        return notification_type.value

    def _should_batch(self, notification: NotificationEvent) -> bool:  # noqa: E111
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

    async def _add_to_batch_queue(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Add notification to batch queue.

        Args:
            notification: Notification to batch
        """
        self._batch_queue.append(notification)

        # Add to pending batches by dog
        if notification.dog_id:
            batch_key = f"{notification.dog_id}_{notification.notification_type.value}"  # noqa: E111
            if batch_key not in self._pending_batches:  # noqa: E111
                self._pending_batches[batch_key] = []
            self._pending_batches[batch_key].append(notification)  # noqa: E111

    async def _process_batch_notifications(self) -> None:  # noqa: E111
        """Background task to process batch notifications.

        OPTIMIZE: Process notifications in batches for better user experience.
        """
        while True:
            try:  # noqa: E111
                await asyncio.sleep(60)  # Process batches every minute

                async with self._lock:
                    if not self._pending_batches:  # noqa: E111
                        continue

                    # Process each batch  # noqa: E114
                    batches_to_send = {}  # noqa: E111
                    for batch_key, notifications in list(self._pending_batches.items()):  # noqa: E111
                        if len(notifications) >= BATCH_PROCESSING_SIZE:
                            batches_to_send[batch_key] = notifications[
                                :BATCH_PROCESSING_SIZE
                            ]  # noqa: E111
                            # Remove processed notifications  # noqa: E114
                            del self._pending_batches[batch_key]  # noqa: E111
                        elif notifications:
                            # Check if oldest notification is older than 5 minutes  # noqa: E114
                            oldest = min(  # noqa: E111
                                notifications,
                                key=lambda n: n.created_at,
                            )
                            age = (dt_util.now() - oldest.created_at).total_seconds()  # noqa: E111
                            if age > 300:  # 5 minutes  # noqa: E111
                                batches_to_send[batch_key] = notifications
                                del self._pending_batches[batch_key]

                    # Send batches  # noqa: E114
                    for notifications in batches_to_send.values():  # noqa: E111
                        await self._send_batch(notifications)
                        self._performance_metrics["batch_operations"] += 1

            except asyncio.CancelledError:  # noqa: E111
                break
            except Exception as err:  # noqa: E111
                _LOGGER.error("Batch processing error: %s", err)

    async def _send_batch(self, notifications: list[NotificationEvent]) -> None:  # noqa: E111
        """Send a batch of notifications.

        Args:
            notifications: List of notifications to send as batch
        """
        if not notifications:
            return  # noqa: E111

        # Group notifications and create batch notification
        dog_id = notifications[0].dog_id
        dog_name = dog_id.replace("_", " ").title() if dog_id else "System"

        # Create summary
        summary_lines = [f"• {notification.title}" for notification in notifications]

        # Create batch notification
        batch_title = f"📋 {len(notifications)} notifications for {dog_name}"
        batch_message = "\n".join(summary_lines)

        # Find common channels
        common_channels = set(notifications[0].channels)
        for notification in notifications[1:]:
            common_channels &= set(notification.channels)  # noqa: E111

        if not common_channels:
            # Fall back to individual sends if no common channels  # noqa: E114
            for notification in notifications:  # noqa: E111
                await self._send_to_channels(notification)
            return  # noqa: E111

        # Merge targeted persons and services
        all_targeted_persons = []
        all_notification_services = []
        for notification in notifications:
            all_targeted_persons.extend(notification.targeted_persons)  # noqa: E111
            all_notification_services.extend(  # noqa: E111
                notification.notification_services,
            )

        # Remove duplicates while preserving order
        unique_persons = list(dict.fromkeys(all_targeted_persons))
        unique_services = list(dict.fromkeys(all_notification_services))

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
            targeted_persons=unique_persons,
            notification_services=unique_services,
        )

        # Mark individual notifications as grouped
        for notification in notifications:
            notification.grouped_with.append(batch_id)  # noqa: E111

        # Send batch notification
        await self._send_to_channels(batch_notification)

        _LOGGER.info(
            "Sent batch notification with %d individual notifications for %s [%d targets]",
            len(notifications),
            dog_name,
            len(unique_services),
        )

    async def _send_to_channels(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send notification to all configured channels with enhanced error handling.

        OPTIMIZE: Parallel channel sending with individual error handling.

        Args:
            notification: Notification to send
        """
        # Send to all channels in parallel
        send_tasks: list[Awaitable[None]] = []
        task_channels: list[NotificationChannel] = []
        for channel in notification.channels:
            handler = self._handlers.get(channel)  # noqa: E111
            if handler:  # noqa: E111
                task_channels.append(channel)
                send_tasks.append(
                    self._send_to_channel_safe(notification, channel, handler),
                )
            else:  # noqa: E111
                _LOGGER.warning("No handler for channel %s", channel.value)
                notification.failed_channels.append(channel)

        if send_tasks:
            # Execute all sends in parallel  # noqa: E114
            results = await asyncio.gather(*send_tasks, return_exceptions=True)  # noqa: E111

            # Process results using shared gather guard  # noqa: E114
            for channel, result in zip(task_channels, results, strict=True):  # noqa: E111
                _unwrap_async_result(
                    result,
                    context=(
                        f"Failed to send notification {notification.id} to channel {channel.value}"
                    ),
                    level=logging.ERROR,
                )

    async def _send_to_channel_safe(  # noqa: E111
        self,
        notification: NotificationEvent,
        channel: NotificationChannel,
        handler: NotificationChannelHandler,
    ) -> None:
        """Send to a single channel with error handling and circuit breaker.

        Args:
            notification: Notification to send
            channel: Target channel
            handler: Channel handler function
        """
        try:
            # RESILIENCE: Wrap handler call with circuit breaker  # noqa: E114
            circuit_name = f"notification_channel_{channel.value}"  # noqa: E111
            await self.resilience_manager.execute_with_resilience(  # noqa: E111
                handler,
                notification,
                circuit_breaker_name=circuit_name,
            )
            notification.sent_to.append(channel)  # noqa: E111

            # Track send attempts  # noqa: E114
            channel_key = channel.value  # noqa: E111
            notification.send_attempts[channel_key] = (  # noqa: E111
                notification.send_attempts.get(channel_key, 0) + 1
            )

            if (  # noqa: E111
                channel == NotificationChannel.MOBILE
                and notification.failed_notification_services
                and channel not in notification.failed_channels
            ):
                notification.failed_channels.append(channel)
                _LOGGER.info(
                    "Mobile notification %s had failed services: %s",
                    notification.id,
                    ", ".join(notification.failed_notification_services),
                )

        except Exception:
            if channel not in notification.failed_channels:  # noqa: E111
                notification.failed_channels.append(channel)
            raise  # noqa: E111

    def _build_webhook_payload(  # noqa: E111
        self,
        notification: NotificationEvent,
    ) -> NotificationWebhookPayload:
        """Build a structured payload for webhook delivery."""

        return {
            "id": notification.id,
            "title": notification.title,
            "message": notification.message,
            "dog_id": notification.dog_id,
            "priority": notification.priority.value,
            "priority_numeric": notification.priority.value_numeric,
            "channels": [channel.value for channel in notification.channels],
            "created_at": notification.created_at.isoformat(),
            "expires_at": notification.expires_at.isoformat()
            if notification.expires_at
            else None,
            "data": notification.data,
            "targeted_persons": notification.targeted_persons,
        }

    async def _send_webhook_notification(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send notification payload to a configured webhook endpoint."""

        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)
        webhook_url = config.custom_settings.get("webhook_url")
        if not webhook_url:
            raise WebhookSecurityError(  # noqa: E111
                f"Webhook channel requested without webhook_url for {config_key}",
            )

        payload = self._build_webhook_payload(notification)
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        secret = config.custom_settings.get("webhook_secret")
        header_prefix = config.custom_settings.get(
            "webhook_header_prefix",
            "X-PawControl",
        )

        if secret:
            algorithm = config.custom_settings.get(  # noqa: E111
                "webhook_algorithm",
                "sha256",
            )
            timestamp = int(time.time())  # noqa: E111
            authenticator = WebhookAuthenticator(  # noqa: E111
                secret=secret,
                algorithm=str(algorithm),
            )
            signature, signed_timestamp = authenticator.generate_signature(  # noqa: E111
                payload_bytes,
                timestamp=timestamp,
            )
            headers[f"{header_prefix}-Signature"] = signature  # noqa: E111
            headers[f"{header_prefix}-Timestamp"] = str(signed_timestamp)  # noqa: E111

        timeout_seconds = float(
            config.custom_settings.get("webhook_timeout", 10),
        )

        async def _maybe_await(value: Any) -> Any:
            if inspect.isawaitable(value):  # noqa: E111
                return await value
            return value  # noqa: E111

        async def _response_status(response: Any) -> int:
            raw_status = await _maybe_await(getattr(response, "status", None))  # noqa: E111
            if raw_status is None:  # noqa: E111
                raise WebhookSecurityError(
                    "Webhook delivery failed: missing status",
                )
            try:  # noqa: E111
                return int(raw_status)
            except (  # noqa: E111
                TypeError,
                ValueError,
            ) as err:  # pragma: no cover - defensive guard
                raise WebhookSecurityError(
                    f"Webhook delivery failed: invalid status {raw_status!r}",
                ) from err

        async def _response_text(response: Any) -> str:
            text_attr = getattr(response, "text", None)  # noqa: E111
            if text_attr is None:  # noqa: E111
                return ""
            text_result = text_attr() if callable(text_attr) else text_attr  # noqa: E111
            text_payload = await _maybe_await(text_result)  # noqa: E111
            return "" if text_payload is None else str(text_payload)  # noqa: E111

        async def _validate_response(response: Any) -> None:
            status_code = await _response_status(response)  # noqa: E111
            if status_code >= 400:  # noqa: E111
                body = await _response_text(response)
                raise WebhookSecurityError(
                    f"Webhook delivery failed with status {status_code}: {body[:200]}",
                )

        async def _finalize_response(response: Any) -> None:
            release = getattr(response, "release", None)  # noqa: E111
            if callable(release):  # noqa: E111
                try:
                    release_result = release()  # noqa: E111
                except Exception as err:  # pragma: no cover - defensive guard
                    _LOGGER.debug("Webhook response release failed: %s", err)  # noqa: E111
                else:
                    if inspect.isawaitable(release_result):  # noqa: E111
                        try:
                            await release_result  # noqa: E111
                        except Exception as err:  # pragma: no cover - defensive guard
                            _LOGGER.debug(  # noqa: E111
                                "Webhook response release await failed: %s",
                                err,
                            )

            close = getattr(response, "close", None)  # noqa: E111
            if callable(close):  # noqa: E111
                try:
                    close_result = close()  # noqa: E111
                except Exception as err:  # pragma: no cover - defensive guard
                    _LOGGER.debug("Webhook response close failed: %s", err)  # noqa: E111
                else:
                    if inspect.isawaitable(close_result):  # noqa: E111
                        try:
                            await close_result  # noqa: E111
                        except Exception as err:  # pragma: no cover - defensive guard
                            _LOGGER.debug(  # noqa: E111
                                "Webhook response close await failed: %s",
                                err,
                            )

        async def _deliver_webhook(call_result: Any) -> None:
            candidate = call_result  # noqa: E111
            while True:  # noqa: E111
                if hasattr(candidate, "__aenter__"):
                    response: Any | None = None  # noqa: E111
                    try:  # noqa: E111
                        async with candidate as context_response:
                            response = await _maybe_await(context_response)  # noqa: E111
                            await _validate_response(response)  # noqa: E111
                    finally:  # noqa: E111
                        if response is not None:
                            await _finalize_response(response)  # noqa: E111
                    return  # noqa: E111
                if inspect.isawaitable(candidate):
                    candidate = await candidate  # noqa: E111
                    continue  # noqa: E111
                try:
                    await _validate_response(candidate)  # noqa: E111
                finally:
                    await _finalize_response(candidate)  # noqa: E111
                return

        try:
            post_call = self._session.post(  # noqa: E111
                webhook_url,
                data=payload_bytes,
                headers=headers,
                timeout=ClientTimeout(total=timeout_seconds),
            )
            await _deliver_webhook(post_call)  # noqa: E111
        except (TimeoutError, ClientError) as err:
            raise WebhookSecurityError(  # noqa: E111
                f"Webhook delivery failed: {err}",
            ) from err

    # OPTIMIZE: Enhanced notification handlers with better error handling and features  # noqa: E114, E501
    async def _send_persistent_notification(  # noqa: E111
        self,
        notification: NotificationEvent,
    ) -> None:
        """Send persistent notification in Home Assistant."""
        service_data: NotificationServicePayload = {
            "notification_id": f"{self._entry_id}_{notification.id}",
            "title": notification.title,
            "message": notification.message,
        }

        await async_call_hass_service_if_available(
            self._hass,
            "persistent_notification",
            "create",
            service_data,
            description=f"notification {notification.id}",
            logger=_LOGGER,
        )

    async def _send_mobile_notification(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send mobile app notification with enhanced features and person targeting."""
        failed_services: list[str] = []
        # NEW: Use person-targeted services if available
        if notification.notification_services:
            # Send to each targeted service  # noqa: E114
            for service_name in notification.notification_services:  # noqa: E111
                try:
                    if not self._notify_service_available(service_name):  # noqa: E111
                        _LOGGER.warning(
                            "Notify service %s is not registered; skipping delivery",
                            service_name,
                        )
                        failed_services.append(service_name)
                        self._record_delivery_failure(
                            service_name,
                            reason="missing_notify_service",
                        )
                        continue

                    service_data: NotificationServicePayload = {  # noqa: E111
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

                    # Add actions for interactive notifications  # noqa: E114
                    if notification.notification_type in [  # noqa: E111
                        NotificationType.FEEDING_REMINDER,
                        NotificationType.WALK_REMINDER,
                        NotificationType.MEDICATION_REMINDER,
                    ]:
                        data_payload = service_data.get("data")
                        actions_target: JSONMutableMapping
                        if isinstance(data_payload, MutableMapping):
                            actions_target = cast(  # noqa: E111
                                JSONMutableMapping,
                                data_payload,
                            )
                        else:
                            actions_target = cast(JSONMutableMapping, {})  # noqa: E111
                            service_data["data"] = actions_target  # noqa: E111

                        actions_target["actions"] = [
                            {
                                "action": f"acknowledge_{notification.id}",
                                "title": "✅ Mark as done",
                                "icon": "sli:check",
                            },
                            {
                                "action": f"snooze_{notification.id}",
                                "title": "⏰ Snooze 15 min",
                                "icon": "sli:clock",
                            },
                        ]

                    guard_result = await async_call_hass_service_if_available(  # noqa: E111
                        self._hass,
                        "notify",
                        service_name,
                        service_data,
                        description=(
                            f"mobile notification {notification.id} for {service_name}"
                        ),
                        logger=_LOGGER,
                    )

                    if guard_result.executed:  # noqa: E111
                        self._record_delivery_success(service_name)
                    else:  # noqa: E111
                        failed_services.append(service_name)
                        self._record_delivery_failure(
                            service_name,
                            reason=guard_result.reason or "service_not_executed",
                        )

                    _LOGGER.debug(  # noqa: E111
                        "Sent mobile notification to %s",
                        service_name,
                    )

                except Exception as err:
                    _LOGGER.error(  # noqa: E111
                        "Failed to send to service %s: %s",
                        service_name,
                        err,
                    )
                    failed_services.append(service_name)  # noqa: E111
                    self._record_delivery_failure(  # noqa: E111
                        service_name,
                        reason="exception",
                        error=err,
                    )

        else:
            # Fallback to original behavior  # noqa: E114
            config_key = notification.dog_id if notification.dog_id else "system"  # noqa: E111
            config = await self._get_config_cached(config_key)  # noqa: E111

            mobile_service = config.custom_settings.get(  # noqa: E111
                "mobile_service",
                "mobile_app",
            )
            if not self._notify_service_available(mobile_service):  # noqa: E111
                _LOGGER.warning(
                    "Notify service %s is not registered; skipping delivery",
                    mobile_service,
                )
                failed_services.append(mobile_service)
                self._record_delivery_failure(
                    mobile_service,
                    reason="missing_notify_service",
                )
            else:  # noqa: E111
                fallback_service_data: NotificationServicePayload = {
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
                    fallback_data = fallback_service_data.get("data")  # noqa: E111
                    fallback_target: JSONMutableMapping  # noqa: E111
                    if isinstance(fallback_data, MutableMapping):  # noqa: E111
                        fallback_target = cast(
                            JSONMutableMapping,
                            fallback_data,
                        )
                    else:  # noqa: E111
                        fallback_target = cast(JSONMutableMapping, {})
                        fallback_service_data["data"] = fallback_target

                    fallback_target["actions"] = [  # noqa: E111
                        {
                            "action": f"acknowledge_{notification.id}",
                            "title": "✅ Mark as done",
                            "icon": "sli:check",
                        },
                        {
                            "action": f"snooze_{notification.id}",
                            "title": "⏰ Snooze 15 min",
                            "icon": "sli:clock",
                        },
                    ]

                guard_result = await async_call_hass_service_if_available(
                    self._hass,
                    "notify",
                    mobile_service,
                    fallback_service_data,
                    description=(
                        f"fallback notification {notification.id} for {mobile_service}"
                    ),
                    logger=_LOGGER,
                )
                if guard_result.executed:
                    self._record_delivery_success(mobile_service)  # noqa: E111
                else:
                    failed_services.append(mobile_service)  # noqa: E111
                    self._record_delivery_failure(  # noqa: E111
                        mobile_service,
                        reason=guard_result.reason or "service_not_executed",
                    )

        if failed_services:
            notification.failed_notification_services = list(  # noqa: E111
                dict.fromkeys(failed_services),
            )
        else:
            notification.failed_notification_services.clear()  # noqa: E111

    async def _send_tts_notification(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send text-to-speech notification."""
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)

        tts_service = config.custom_settings.get(
            "tts_service",
            "google_translate_say",
        )
        tts_entity = config.custom_settings.get(
            "tts_entity",
            "media_player.living_room",
        )

        # Combine title and message for TTS
        tts_message = f"{notification.title}. {notification.message}"

        await async_call_hass_service_if_available(
            self._hass,
            "tts",
            tts_service,
            {
                "message": tts_message,
                "entity_id": tts_entity,
            },
            description=f"tts notification {notification.id}",
            logger=_LOGGER,
        )

    async def _send_media_player_notification(  # noqa: E111
        self,
        notification: NotificationEvent,
    ) -> None:
        """Send notification via media player."""
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)

        media_player = config.custom_settings.get("media_player_entity")
        if not media_player:
            raise ValueError("No media player entity configured")  # noqa: E111

        announcement = f"PawControl Alert: {notification.title}. {notification.message}"

        await async_call_hass_service_if_available(
            self._hass,
            "media_player",
            "play_media",
            {
                "entity_id": media_player,
                "media_content_id": f"media-source://tts/tts.google_translate_say?message={announcement}",
                "media_content_type": "music",
            },
            description=(
                f"media player announcement {notification.id} on {media_player}"
            ),
            logger=_LOGGER,
        )

    async def _send_slack_notification(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send Slack notification.

        OPTIMIZE: New Slack integration for team notifications.
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)

        slack_service = config.custom_settings.get("slack_service", "slack")

        service_data: NotificationServicePayload = {
            "title": notification.title,
            "message": notification.message,
            "target": config.custom_settings.get("slack_channel", "#pawcontrol"),
            "data": {
                "icon": ":dog:" if notification.dog_id else ":gear:",
                "username": "PawControl",
            },
        }

        await async_call_hass_service_if_available(
            self._hass,
            "notify",
            slack_service,
            service_data,
            description=f"slack notification {notification.id}",
            logger=_LOGGER,
        )

    async def _send_discord_notification(self, notification: NotificationEvent) -> None:  # noqa: E111
        """Send Discord notification.

        OPTIMIZE: New Discord integration for community notifications.
        """
        config_key = notification.dog_id if notification.dog_id else "system"
        config = await self._get_config_cached(config_key)

        discord_service = config.custom_settings.get(
            "discord_service",
            "discord",
        )

        service_data: NotificationServicePayload = {
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

        await async_call_hass_service_if_available(
            self._hass,
            "notify",
            discord_service,
            service_data,
            description=f"discord notification {notification.id}",
            logger=_LOGGER,
        )

    def _get_color_for_priority(self, priority: NotificationPriority) -> int:  # noqa: E111
        """Get Discord embed color for priority.

        Args:
            priority: Notification priority

        Returns:
            Discord color code
        """
        colors = {
            NotificationPriority.LOW: 0x95A5A6,  # Gray
            NotificationPriority.NORMAL: 0x3498DB,  # Blue
            NotificationPriority.HIGH: 0xF39C12,  # Orange
            NotificationPriority.URGENT: 0xE74C3C,  # Red
        }
        return colors.get(priority, 0x3498DB)

    # OPTIMIZE: Enhanced cleanup and maintenance  # noqa: E114
    async def _cleanup_expired_notifications(self) -> None:  # noqa: E111
        """Background task to clean up expired notifications and cache."""
        while True:
            try:  # noqa: E111
                await asyncio.sleep(CACHE_CLEANUP_INTERVAL)

                async with self._lock:
                    # Clean expired notifications  # noqa: E114
                    expired_count = await self.async_cleanup_expired_notifications()  # noqa: E111

                    if expired_count > 0:  # noqa: E111
                        _LOGGER.debug(
                            "Cleanup: %d expired notifications", expired_count
                        )

            except asyncio.CancelledError:  # noqa: E111
                break
            except Exception as err:  # noqa: E111
                _LOGGER.error("Cleanup task error: %s", err)

    async def async_cleanup_expired_notifications(self) -> int:  # noqa: E111
        """Clean up expired notifications with enhanced logic.

        Returns:
            Number of notifications cleaned up
        """
        now = dt_util.utcnow()
        expired_ids = []

        for notification_id, notification in self._notifications.items():
            # Remove if expired or very old acknowledged notifications  # noqa: E114
            expires_at = notification.expires_at  # noqa: E111
            if expires_at and expires_at.tzinfo is None:  # noqa: E111
                expires_at = dt_util.as_utc(expires_at)

            acknowledged_at = notification.acknowledged_at  # noqa: E111
            if acknowledged_at is not None:  # noqa: E111
                acknowledged_at = dt_util.as_utc(acknowledged_at)

            if (expires_at and expires_at < now) or (  # noqa: E111
                notification.acknowledged
                and acknowledged_at
                and (now - acknowledged_at).days > 7
            ):
                expired_ids.append(notification_id)

        # Batch remove expired notifications
        for notification_id in expired_ids:
            del self._notifications[notification_id]  # noqa: E111

        if expired_ids:
            _LOGGER.debug(  # noqa: E111
                "Cleaned up %d expired notifications",
                len(expired_ids),
            )

        return len(expired_ids)

    # Keep existing public interface methods with optimizations  # noqa: E114
    async def async_acknowledge_notification(self, notification_id: str) -> bool:  # noqa: E111
        """Acknowledge a notification with enhanced cleanup."""
        async with self._lock:
            notification = self._notifications.get(notification_id)  # noqa: E111
            if not notification:  # noqa: E111
                return False

            notification.acknowledged = True  # noqa: E111
            notification.acknowledged_at = dt_util.now()  # noqa: E111

            # Dismiss persistent notification if it exists  # noqa: E114
            if NotificationChannel.PERSISTENT in notification.sent_to:  # noqa: E111
                try:
                    executed = await async_call_hass_service_if_available(  # noqa: E111
                        self._hass,
                        "persistent_notification",
                        "dismiss",
                        {"notification_id": f"{self._entry_id}_{notification_id}"},
                        description=f"dismiss notification {notification_id}",
                        logger=_LOGGER,
                    )
                    if not executed:  # noqa: E111
                        return True
                except Exception as err:
                    _LOGGER.warning(  # noqa: E111
                        "Failed to dismiss persistent notification: %s",
                        err,
                    )

            _LOGGER.info("Acknowledged notification %s", notification_id)  # noqa: E111
            return True  # noqa: E111

    def _cache_stats_snapshot(self) -> NotificationCacheStats:  # noqa: E111
        """Return lightweight runtime stats for notification state maps.

        Quiet-time entries track configured notification profiles, while
        person-targeting entries are sourced from ``PersonEntityManager`` cache
        diagnostics when available.
        """

        rate_limit_entries = sum(
            len(channel_map) for channel_map in self._rate_limit_last_sent.values()
        )
        person_targeting_entries = 0
        if self._person_manager is not None:
            person_targeting_entries = int(  # noqa: E111
                self._person_manager.get_statistics()["cache"]["cache_entries"]
            )

        quiet_time_entries = len(self._configs)
        total_entries = (
            rate_limit_entries + quiet_time_entries + person_targeting_entries
        )
        max_size = max(len(self._configs), 1)
        utilization = min(total_entries / max_size, 1.0)
        return {
            "config_entries": len(self._configs),
            "quiet_time_entries": quiet_time_entries,
            "person_targeting_entries": person_targeting_entries,
            "rate_limit_entries": rate_limit_entries,
            "cache_utilization": round(utilization, 2),
        }

    async def async_get_performance_statistics(self) -> NotificationManagerStats:  # noqa: E111
        """Get comprehensive performance statistics.

        OPTIMIZE: New method for monitoring system performance.

        Returns:
            Performance statistics
        """
        async with self._lock:
            total_notifications = len(self._notifications)  # noqa: E111
            active_notifications = len(  # noqa: E111
                [
                    n
                    for n in self._notifications.values()
                    if not n.acknowledged
                    and (not n.expires_at or n.expires_at > dt_util.now())
                ],
            )

            # Calculate type and priority distribution  # noqa: E114
            type_counts: dict[str, int] = {}  # noqa: E111
            priority_counts: dict[str, int] = {}  # noqa: E111

            for notification in self._notifications.values():  # noqa: E111
                ntype = notification.notification_type.value
                type_counts[ntype] = type_counts.get(ntype, 0) + 1

                priority = notification.priority.value
                priority_counts[priority] = (
                    priority_counts.get(
                        priority,
                        0,
                    )
                    + 1
                )

            # NEW: Person targeting statistics  # noqa: E114
            person_stats: PersonEntityStats | None = None  # noqa: E111
            if self._person_manager:  # noqa: E111
                person_stats = self._person_manager.get_statistics()

            stats: NotificationManagerStats = {  # noqa: E111
                # Basic stats
                "total_notifications": total_notifications,
                "active_notifications": active_notifications,
                "configured_dogs": len([k for k in self._configs if k != "system"]),
                "type_distribution": type_counts,
                "priority_distribution": priority_counts,
                # Performance metrics
                "performance_metrics": self.get_performance_metrics(),
                "cache_stats": self._cache_stats_snapshot(),
                "batch_queue_size": len(self._batch_queue),
                "pending_batches": len(self._pending_batches),
                # Handler stats
                "available_channels": [channel.value for channel in self._handlers],
                "handlers_registered": len(self._handlers),
                # NEW: Person targeting stats
                "person_entity_stats": person_stats,
            }
            return stats  # noqa: E111

    def register_cache_monitors(self, registrar: CacheMonitorRegistrar) -> None:  # noqa: E111
        """Register notification-centric caches with the provided registrar."""

        self._cache_monitor_registrar = registrar
        registrar.register_cache_monitor(
            "notification_cache",
            self._cache,
        )
        self._register_person_cache_monitor()

    def _register_person_cache_monitor(self) -> None:  # noqa: E111
        """Register the person entity targeting cache when available."""

        if self._cache_monitor_registrar is None or self._person_manager is None:
            return  # noqa: E111

        self._person_manager.register_cache_monitors(
            self._cache_monitor_registrar,
            prefix="person_entity",
        )

    def webhook_security_status(self) -> WebhookSecurityStatus:  # noqa: E111
        """Return aggregated HMAC webhook security information."""

        webhook_configs: list[str] = []
        insecure_configs: list[str] = []

        for config_key, config in self._configs.items():
            if NotificationChannel.WEBHOOK not in config.channels:  # noqa: E111
                continue

            webhook_configs.append(config_key)  # noqa: E111
            secret = config.custom_settings.get("webhook_secret")  # noqa: E111
            if not isinstance(secret, str) or not secret.strip():  # noqa: E111
                insecure_configs.append(config_key)

        configured = bool(webhook_configs)
        secure = configured and not insecure_configs

        return {
            "configured": configured,
            "secure": secure,
            "hmac_ready": secure,
            "insecure_configs": tuple(insecure_configs),
        }

    async def async_shutdown(self) -> None:  # noqa: E111
        """Enhanced shutdown with comprehensive cleanup."""
        # Cancel all background tasks
        tasks_to_cancel = [
            self._retry_task,
            self._cleanup_task,
            self._batch_task,
        ]

        for task in tasks_to_cancel:
            if task and not task.done():  # noqa: E111
                task.cancel()

        # Wait for tasks to complete
        active_tasks = [task for task in tasks_to_cancel if task is not None]
        current_loop = asyncio.get_running_loop()
        same_loop_tasks = [
            task
            for task in active_tasks
            if getattr(task, "get_loop", lambda: current_loop)() is current_loop
        ]
        if same_loop_tasks:
            await asyncio.gather(*same_loop_tasks, return_exceptions=True)  # noqa: E111

        # Shutdown person manager
        if self._person_manager:
            await self._person_manager.async_shutdown()  # noqa: E111

        # Process any remaining batches
        async with self._lock:
            for notifications in self._pending_batches.values():  # noqa: E111
                for notification in notifications:
                    await self._send_to_channels(notification)  # noqa: E111

        # Clear all data
        self._notifications.clear()
        self._configs.clear()
        self._handlers.clear()
        self._batch_queue.clear()
        self._pending_batches.clear()

    # Keep existing methods for backward compatibility  # noqa: E114
    async def _retry_failed_notifications(self) -> None:  # noqa: E111
        """Background task to retry failed notifications."""
        while True:
            try:  # noqa: E111
                await asyncio.sleep(RETRY_DELAY_SECONDS)

                async with self._lock:
                    now = dt_util.now()  # noqa: E111
                    retry_notifications = []  # noqa: E111

                    for notification in self._notifications.values():  # noqa: E111
                        if (
                            (notification.expires_at and notification.expires_at < now)
                            or notification.acknowledged
                            or (
                                not notification.failed_channels
                                and not notification.failed_notification_services
                            )
                            or notification.retry_count >= MAX_RETRY_ATTEMPTS
                        ):
                            continue  # noqa: E111

                        time_since_creation = now - notification.created_at
                        if time_since_creation.total_seconds() > RETRY_DELAY_SECONDS:
                            retry_notifications.append(notification)  # noqa: E111

                    for notification in retry_notifications:  # noqa: E111
                        if not notification.failed_channels and (
                            not notification.failed_notification_services
                        ):
                            continue  # noqa: E111

                        _LOGGER.info(
                            "Retrying notification %s (attempt %d)",
                            notification.id,
                            notification.retry_count + 1,
                        )

                        failed_services = list(
                            notification.failed_notification_services,
                        )
                        if failed_services:
                            notification.notification_services = failed_services  # noqa: E111
                        notification.failed_notification_services.clear()

                        failed_channels = notification.failed_channels.copy()
                        if not failed_channels and failed_services:
                            failed_channels = [NotificationChannel.MOBILE]  # noqa: E111
                        notification.failed_channels.clear()
                        notification.channels = failed_channels
                        notification.retry_count += 1
                        self._performance_metrics["retry_reschedules"] += 1

                        await self._send_to_channels(notification)

                        if not notification.failed_channels:
                            self._performance_metrics["retry_successes"] += 1  # noqa: E111

            except asyncio.CancelledError:  # noqa: E111
                break
            except Exception as err:  # noqa: E111
                _LOGGER.error("Error in retry task: %s", err)

    async def async_send_feeding_compliance_summary(  # noqa: E111
        self,
        *,
        dog_id: str,
        dog_name: str | None,
        compliance: FeedingComplianceResult,
    ) -> str | None:
        """Send structured compliance telemetry when feeding gaps appear."""

        display_name = dog_name or dog_id

        language = getattr(
            getattr(self._hass, "config", None),
            "language",
            None,
        )

        if compliance["status"] != "completed":
            no_data = compliance  # noqa: E111
            no_data_payload = cast(JSONMutableMapping, dict(no_data))  # noqa: E111
            title, message = await async_build_feeding_compliance_notification(  # noqa: E111
                self._hass,
                language,
                display_name=display_name,
                compliance=no_data_payload,
            )

            return await self.async_send_notification(  # noqa: E111
                notification_type=NotificationType.FEEDING_COMPLIANCE,
                title=title,
                message=message or "",
                dog_id=dog_id,
                priority=NotificationPriority.HIGH,
                data={
                    "dog_id": dog_id,
                    "dog_name": dog_name,
                    "compliance": no_data_payload,
                },
                allow_batching=False,
            )

        completed = compliance
        has_issues = bool(
            completed["days_with_issues"]
            or completed["compliance_issues"]
            or completed["missed_meals"]
            or completed["compliance_score"] < 100,
        )

        if not has_issues:
            return None  # noqa: E111

        priority = NotificationPriority.HIGH
        if completed["compliance_score"] < 70:
            priority = NotificationPriority.URGENT  # noqa: E111
        elif completed["compliance_score"] >= 90:
            priority = NotificationPriority.NORMAL  # noqa: E111

        completed_payload = cast(JSONMutableMapping, dict(completed))
        issues = completed.get("compliance_issues") or []
        missed_meals = completed.get("missed_meals") or []

        title, message = await async_build_feeding_compliance_notification(
            self._hass,
            language,
            display_name=display_name,
            compliance=completed_payload,
        )

        issues_payload = [cast(JSONMutableMapping, dict(issue)) for issue in issues]
        missed_meals_payload = [
            cast(JSONMutableMapping, dict(entry)) for entry in missed_meals
        ]

        return await self.async_send_notification(
            notification_type=NotificationType.FEEDING_COMPLIANCE,
            title=title,
            message=message or "",
            dog_id=dog_id,
            priority=priority,
            data={
                "dog_id": dog_id,
                "dog_name": dog_name,
                "compliance": completed_payload,
                "issues": issues_payload,
                "missed_meals": missed_meals_payload,
            },
            allow_batching=False,
        )

    # Additional convenience methods for specific notification types  # noqa: E114
    async def async_send_feeding_reminder(  # noqa: E111
        self,
        dog_id: str,
        meal_type: str,
        scheduled_time: str,
        portion_size: float | None = None,
    ) -> str:
        """Send feeding reminder notification."""
        title = f"🍽️ {meal_type.title()} Time for {dog_id.title()}"
        message = f"It's time for {dog_id}'s {meal_type}"

        if portion_size:
            message += f" ({portion_size}g)"  # noqa: E111
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

    async def async_send_walk_reminder(  # noqa: E111
        self,
        dog_id: str,
        last_walk_hours: float | None = None,
    ) -> str:
        """Send walk reminder notification."""
        title = f"🚶 Walk Time for {dog_id.title()}"

        if last_walk_hours:
            message = (  # noqa: E111
                f"{dog_id} hasn't been walked in {last_walk_hours:.1f} hours. Time for a walk!"
            )
        else:
            message = f"It's time to take {dog_id} for a walk!"  # noqa: E111

        return await self.async_send_notification(
            notification_type=NotificationType.WALK_REMINDER,
            title=title,
            message=message,
            dog_id=dog_id,
            priority=NotificationPriority.NORMAL,
            data={"last_walk_hours": last_walk_hours},
        )

    async def async_send_health_alert(  # noqa: E111
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

    # NEW: Person entity management methods  # noqa: E114
    async def async_update_person_entity_config(  # noqa: E111
        self,
        config: Mapping[str, object],
    ) -> bool:
        """Update person entity configuration.

        Args:
            config: New person entity configuration

        Returns:
            True if update was successful
        """
        if self._person_manager:
            person_config = cast(PersonEntityConfigInput, dict(config))  # noqa: E111
            return await self._person_manager.async_update_config(person_config)  # noqa: E111
        return False

    async def async_force_person_discovery(  # noqa: E111
        self,
    ) -> PersonDiscoveryResult | PersonDiscoveryError:
        """Force person entity discovery.

        Returns:
            Discovery results
        """
        if self._person_manager:
            return await self._person_manager.async_force_discovery()  # noqa: E111
        return {"error": "Person manager not available"}

    def get_person_notification_context(self) -> PersonNotificationContext:  # noqa: E111
        """Get current person notification context.

        Returns:
            Person context for notifications
        """
        if self._person_manager:
            return self._person_manager.get_notification_context()  # noqa: E111
        return {
            "persons_home": 0,
            "persons_away": 0,
            "home_person_names": [],
            "away_person_names": [],
            "total_persons": 0,
            "has_anyone_home": False,
            "everyone_away": False,
        }


_unwrap_async_result = partial(unwrap_async_result, logger=_LOGGER)
