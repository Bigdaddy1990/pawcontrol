"""Door sensor integration for automatic walk detection.

Monitors door sensors and automatically detects when dogs go for walks
based on door state changes and configurable timing logic.

Quality Scale: Bronze target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CACHE_TIMESTAMP_FUTURE_THRESHOLD,
    CACHE_TIMESTAMP_STALE_THRESHOLD,
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_SETTINGS,
    EVENT_WALK_ENDED,
    EVENT_WALK_STARTED,
)
from .coordinator_support import CacheMonitorRegistrar
from .notifications import NotificationPriority, NotificationType
from .runtime_data import get_runtime_data
from .types import (
    DOG_ID_FIELD,
    DOG_NAME_FIELD,
    CacheDiagnosticsMetadata,
    CacheDiagnosticsSnapshot,
    DetectionStatistics,
    DetectionStatus,
    DetectionStatusEntry,
    DogConfigData,
)
from .utils import async_fire_event

if TYPE_CHECKING:
    from .data_manager import PawControlDataManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager

_LOGGER = logging.getLogger(__name__)

_UNSET: object = object()

# Door sensor configuration
DEFAULT_WALK_DETECTION_TIMEOUT = 300  # 5 minutes
DEFAULT_MINIMUM_WALK_DURATION = 180  # 3 minutes
DEFAULT_MAXIMUM_WALK_DURATION = 7200  # 2 hours
DEFAULT_DOOR_CLOSED_DELAY = 60  # 1 minute
DEFAULT_CONFIDENCE_THRESHOLD = 0.7


@dataclass(slots=True, frozen=True)
class DoorSensorSettingsConfig:
    """Normalised configuration values applied to door sensor tracking."""

    walk_detection_timeout: int = DEFAULT_WALK_DETECTION_TIMEOUT
    minimum_walk_duration: int = DEFAULT_MINIMUM_WALK_DURATION
    maximum_walk_duration: int = DEFAULT_MAXIMUM_WALK_DURATION
    door_closed_delay: int = DEFAULT_DOOR_CLOSED_DELAY
    require_confirmation: bool = True
    auto_end_walks: bool = True
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


DEFAULT_DOOR_SENSOR_SETTINGS = DoorSensorSettingsConfig()
DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD = asdict(DEFAULT_DOOR_SENSOR_SETTINGS)


def _coerce_int(
    value: Any,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Coerce ``value`` to an integer within optional bounds."""

    if isinstance(value, bool) or value is None:
        return default

    candidate: int
    if isinstance(value, int | float):
        candidate = int(value)
    elif isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            candidate = int(float(value))
        except ValueError:
            return default
    else:
        return default

    if minimum is not None and candidate < minimum:
        candidate = minimum
    if maximum is not None and candidate > maximum:
        candidate = maximum
    return candidate


def _coerce_float(
    value: Any,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Coerce ``value`` to a float within optional bounds."""

    if isinstance(value, bool) or value is None:
        return default

    candidate: float
    if isinstance(value, int | float):
        candidate = float(value)
    elif isinstance(value, str):
        value = value.strip()
        if not value:
            return default
        try:
            candidate = float(value)
        except ValueError:
            return default
    else:
        return default

    if minimum is not None and candidate < minimum:
        candidate = minimum
    if maximum is not None and candidate > maximum:
        candidate = maximum
    return candidate


def _coerce_bool(value: Any, *, default: bool) -> bool:
    """Normalise ``value`` to a boolean."""

    if isinstance(value, bool):
        return value

    if isinstance(value, int | float):
        # Treat numeric inputs as truthy when non-zero to support options payloads
        # that pass integers (for example, 0/1 toggles from legacy configs).
        return bool(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default

        lowered = stripped.lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False

        try:
            numeric = float(stripped)
        except ValueError:
            return default
        return bool(numeric)

    return default


def _settings_from_config(
    config: DoorSensorConfig | DoorSensorSettingsConfig | None,
) -> DoorSensorSettingsConfig:
    """Return a normalised settings snapshot for ``config``."""

    if isinstance(config, DoorSensorSettingsConfig):
        return config
    if config is None:
        return DEFAULT_DOOR_SENSOR_SETTINGS
    return DoorSensorSettingsConfig(
        walk_detection_timeout=config.walk_detection_timeout,
        minimum_walk_duration=config.minimum_walk_duration,
        maximum_walk_duration=config.maximum_walk_duration,
        door_closed_delay=config.door_closed_delay,
        require_confirmation=config.require_confirmation,
        auto_end_walks=config.auto_end_walks,
        confidence_threshold=config.confidence_threshold,
    )


def ensure_door_sensor_settings_config(
    overrides: Mapping[str, Any] | DoorSensorSettingsConfig | None,
    *,
    base: DoorSensorSettingsConfig | DoorSensorConfig | None = None,
) -> DoorSensorSettingsConfig:
    """Return a normalised ``DoorSensorSettingsConfig`` from ``overrides``."""

    base_settings = _settings_from_config(base)

    if overrides is None:
        return base_settings

    if isinstance(overrides, DoorSensorSettingsConfig):
        raw: Mapping[str, Any] = asdict(overrides)
    elif isinstance(overrides, Mapping):
        raw = overrides
    else:
        raise TypeError(
            "door sensor settings must be a mapping or DoorSensorSettingsConfig"
        )

    normalised: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(key, str):
            normalised[key.strip().lower()] = value

    def pick(*aliases: str) -> Any:
        for alias in aliases:
            alias_key = alias.lower()
            if alias_key in normalised:
                return normalised[alias_key]
        return None

    timeout = _coerce_int(
        pick("timeout", "walk_detection_timeout", "walk_timeout"),
        default=base_settings.walk_detection_timeout,
        minimum=30,
        maximum=21600,
    )
    minimum_duration = _coerce_int(
        pick(
            "minimum_walk_duration",
            "min_walk_duration",
            "minimum_duration",
            "min_duration",
        ),
        default=base_settings.minimum_walk_duration,
        minimum=60,
        maximum=21600,
    )
    maximum_duration = _coerce_int(
        pick(
            "maximum_walk_duration",
            "max_walk_duration",
            "maximum_duration",
            "max_duration",
        ),
        default=base_settings.maximum_walk_duration,
        minimum=minimum_duration,
        maximum=43200,
    )
    door_delay = _coerce_int(
        pick(
            "door_closed_delay", "door_closed_timeout", "close_delay", "close_timeout"
        ),
        default=base_settings.door_closed_delay,
        minimum=0,
        maximum=1800,
    )
    require_confirmation = _coerce_bool(
        pick("require_confirmation", "confirmation_required"),
        default=base_settings.require_confirmation,
    )
    auto_end_walks = _coerce_bool(
        pick("auto_end_walks", "auto_end_walk", "auto_close"),
        default=base_settings.auto_end_walks,
    )
    confidence_threshold = _coerce_float(
        pick("confidence_threshold", "confidence", "threshold"),
        default=base_settings.confidence_threshold,
        minimum=0.0,
        maximum=1.0,
    )

    return DoorSensorSettingsConfig(
        walk_detection_timeout=timeout,
        minimum_walk_duration=minimum_duration,
        maximum_walk_duration=maximum_duration,
        door_closed_delay=door_delay,
        require_confirmation=require_confirmation,
        auto_end_walks=auto_end_walks,
        confidence_threshold=confidence_threshold,
    )


def _settings_to_payload(settings: DoorSensorSettingsConfig) -> dict[str, Any]:
    """Return a serialisable payload for ``settings``."""

    return asdict(settings)


def _apply_settings_to_config(
    config: DoorSensorConfig, settings: DoorSensorSettingsConfig
) -> None:
    """Apply ``settings`` to ``config`` in-place."""

    config.walk_detection_timeout = settings.walk_detection_timeout
    config.minimum_walk_duration = settings.minimum_walk_duration
    config.maximum_walk_duration = settings.maximum_walk_duration
    config.door_closed_delay = settings.door_closed_delay
    config.require_confirmation = settings.require_confirmation
    config.auto_end_walks = settings.auto_end_walks
    config.confidence_threshold = settings.confidence_threshold


# Walk detection states
WALK_STATE_IDLE = "idle"
WALK_STATE_POTENTIAL = "potential"
WALK_STATE_ACTIVE = "active"
WALK_STATE_RETURNING = "returning"


def _serialize_datetime(value: datetime | None) -> str | None:
    """Serialize datetimes to ISO format for diagnostics."""

    if value is None:
        return None
    return dt_util.as_utc(value).isoformat()


def _classify_timestamp(value: datetime | None) -> tuple[str | None, int | None]:
    """Return anomaly classification for ``value`` if thresholds are crossed."""

    if value is None:
        return None, None

    delta = dt_util.utcnow() - dt_util.as_utc(value)
    age_seconds = int(delta.total_seconds())

    if delta < -CACHE_TIMESTAMP_FUTURE_THRESHOLD:
        return "future", age_seconds
    if delta > CACHE_TIMESTAMP_STALE_THRESHOLD:
        return "stale", age_seconds
    return None, age_seconds


class _DoorSensorManagerCacheMonitor:
    """Expose door sensor manager diagnostics to cache snapshots."""

    __slots__ = ("_manager",)

    def __init__(self, manager: DoorSensorManager) -> None:
        self._manager = manager

    def _build_payload(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], CacheDiagnosticsMetadata]:
        manager = self._manager
        configs = getattr(manager, "_sensor_configs", {})
        states = getattr(manager, "_detection_states", {})
        stats_payload = dict(getattr(manager, "_detection_stats", {}))
        manager_last_activity = getattr(manager, "_last_activity", None)

        per_dog: dict[str, dict[str, Any]] = {}
        active_detections = 0
        timestamp_anomalies: dict[str, str] = {}

        for dog_id, config in configs.items():
            if not isinstance(dog_id, str):
                continue

            state = states.get(dog_id)
            if state is not None and state.current_state != WALK_STATE_IDLE:
                active_detections += 1

            config_payload: dict[str, Any] = {
                "entity_id": config.entity_id,
                "enabled": config.enabled,
                "walk_detection_timeout": config.walk_detection_timeout,
                "minimum_walk_duration": config.minimum_walk_duration,
                "maximum_walk_duration": config.maximum_walk_duration,
                "door_closed_delay": config.door_closed_delay,
                "require_confirmation": config.require_confirmation,
                "auto_end_walks": config.auto_end_walks,
                "confidence_threshold": round(config.confidence_threshold, 3),
            }

            if state is not None:
                last_activity_source: datetime | None = state.door_closed_at
                if last_activity_source is None:
                    last_activity_source = state.door_opened_at
                if (
                    last_activity_source is None
                    and state.state_history
                    and isinstance(state.state_history[-1][0], datetime)
                ):
                    last_activity_source = state.state_history[-1][0]

                anomaly_reason, state_age = _classify_timestamp(last_activity_source)

                config_payload["state"] = {
                    "current_state": state.current_state,
                    "door_opened_at": _serialize_datetime(state.door_opened_at),
                    "door_closed_at": _serialize_datetime(state.door_closed_at),
                    "potential_walk_start": _serialize_datetime(
                        state.potential_walk_start
                    ),
                    "active_walk_id": state.active_walk_id,
                    "confidence_score": round(float(state.confidence_score), 3),
                    "last_door_state": state.last_door_state,
                    "consecutive_opens": state.consecutive_opens,
                    "state_history": [
                        {
                            "timestamp": _serialize_datetime(timestamp),
                            "state": event_state,
                        }
                        for timestamp, event_state in getattr(
                            state, "state_history", []
                        )
                        if isinstance(event_state, str)
                    ],
                }

                if state_age is not None:
                    config_payload["state"]["last_activity_age_seconds"] = state_age

                if anomaly_reason is not None:
                    timestamp_anomalies[dog_id] = anomaly_reason

            per_dog[dog_id] = config_payload

        stats: dict[str, Any] = {
            "configured_sensors": len(per_dog),
            "active_detections": active_detections,
        }
        stats.update({k: v for k, v in stats_payload.items() if k not in stats})

        manager_anomaly, manager_age = _classify_timestamp(manager_last_activity)
        if manager_age is not None:
            stats["last_activity_age_seconds"] = manager_age

        snapshot: dict[str, Any] = {
            "per_dog": per_dog,
            "detection_stats": stats_payload,
            "manager_last_activity": _serialize_datetime(manager_last_activity),
        }

        diagnostics: CacheDiagnosticsMetadata = {
            "per_dog": per_dog,
            "detection_stats": stats_payload,
            "cleanup_task_active": getattr(manager, "_cleanup_task", None) is not None,
            "manager_last_activity": _serialize_datetime(manager_last_activity),
        }

        if manager_age is not None:
            diagnostics["manager_last_activity_age_seconds"] = manager_age

        if manager_anomaly is not None:
            timestamp_anomalies["manager"] = manager_anomaly

        if timestamp_anomalies:
            diagnostics["timestamp_anomalies"] = timestamp_anomalies

        return stats, snapshot, diagnostics

    def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:
        stats, snapshot, diagnostics = self._build_payload()
        return CacheDiagnosticsSnapshot(
            stats=stats,
            snapshot=snapshot,
            diagnostics=diagnostics,
        )

    def get_stats(self) -> dict[str, Any]:
        stats, _snapshot, _diagnostics = self._build_payload()
        return stats

    def get_diagnostics(self) -> CacheDiagnosticsMetadata:
        _stats, _snapshot, diagnostics = self._build_payload()
        return diagnostics


@dataclass
class DoorSensorConfig:
    """Configuration for door sensor walk detection."""

    entity_id: str
    dog_id: str
    dog_name: str
    enabled: bool = True
    walk_detection_timeout: int = DEFAULT_WALK_DETECTION_TIMEOUT
    minimum_walk_duration: int = DEFAULT_MINIMUM_WALK_DURATION
    maximum_walk_duration: int = DEFAULT_MAXIMUM_WALK_DURATION
    door_closed_delay: int = DEFAULT_DOOR_CLOSED_DELAY
    require_confirmation: bool = True
    auto_end_walks: bool = True
    confidence_threshold: float = 0.7  # Confidence level for automatic detection


@dataclass
class WalkDetectionState:
    """State tracking for door sensor based walk detection."""

    dog_id: str
    current_state: str = WALK_STATE_IDLE
    door_opened_at: datetime | None = None
    door_closed_at: datetime | None = None
    potential_walk_start: datetime | None = None
    active_walk_id: str | None = None
    confidence_score: float = 0.0
    last_door_state: str | None = None
    consecutive_opens: int = 0
    state_history: list[tuple[datetime, str]] = field(default_factory=list)

    def add_state_event(self, state: str) -> None:
        """Add state change to history with cleanup."""
        now = dt_util.now()
        self.state_history.append((now, state))

        # Keep only last 10 events and events from last 24 hours
        cutoff = now - timedelta(hours=24)
        self.state_history = [
            (timestamp, event_state)
            for timestamp, event_state in self.state_history[-10:]
            if timestamp > cutoff
        ]

    def calculate_confidence(self) -> float:
        """Calculate confidence score based on door sensor patterns."""
        if len(self.state_history) < 2:
            return 0.0

        now = dt_util.now()
        recent_events = [
            (timestamp, event_state)
            for timestamp, event_state in self.state_history
            if (now - timestamp).total_seconds() < 600  # Last 10 minutes
        ]

        if len(recent_events) < 2:
            return 0.0

        confidence = 0.0

        # Pattern: Single open followed by closed (typical walk pattern)
        if len(recent_events) == 2:
            first_event = recent_events[0]
            second_event = recent_events[1]

            if first_event[1] == STATE_ON and second_event[1] == STATE_OFF:
                # Time between open and close
                duration = (second_event[0] - first_event[0]).total_seconds()

                # Optimal duration: 10-60 seconds (person and dog going out)
                if 10 <= duration <= 60:
                    confidence += 0.8
                elif duration <= 120:
                    confidence += 0.6
                else:
                    confidence += 0.3

        # Pattern: Multiple quick opens/closes (uncertainty)
        rapid_changes = len(
            [event for event in recent_events if (now - event[0]).total_seconds() < 120]
        )

        if rapid_changes > 4:
            confidence *= 0.5  # Reduce confidence for erratic patterns

        # Time of day bonus (common walk times)
        current_hour = now.hour
        if current_hour in [6, 7, 8, 17, 18, 19, 20]:  # Morning and evening
            confidence += 0.1
        elif current_hour in [12, 13]:  # Lunch time
            confidence += 0.05

        return min(confidence, 1.0)


class DoorSensorManager:
    """Manager for door sensor based walk detection."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize door sensor manager.

        Args:
            hass: Home Assistant instance
            entry_id: Configuration entry ID
        """
        self.hass = hass
        self.entry_id = entry_id

        # Configuration and state tracking
        self._sensor_configs: dict[str, DoorSensorConfig] = {}
        self._detection_states: dict[str, WalkDetectionState] = {}
        self._state_listeners: list[CALLBACK_TYPE] = []
        self._cleanup_task: asyncio.Task | None = None
        self._last_activity: datetime | None = None

        # Dependencies (injected during initialization)
        self._walk_manager: WalkManager | None = None
        self._notification_manager: PawControlNotificationManager | None = None
        self._data_manager: PawControlDataManager | None = None

        # Performance tracking
        self._detection_stats: DetectionStatistics = {
            "total_detections": 0,
            "successful_walks": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "average_confidence": 0.0,
        }

    def register_cache_monitors(
        self, registrar: CacheMonitorRegistrar, *, prefix: str = "door_sensor"
    ) -> None:
        """Register cache diagnostics for the door sensor manager."""

        if registrar is None:
            raise ValueError("registrar is required")

        _LOGGER.debug("Registering door sensor cache monitor with prefix %s", prefix)
        registrar.register_cache_monitor(
            f"{prefix}_cache", _DoorSensorManagerCacheMonitor(self)
        )

    def _ensure_data_manager(self) -> PawControlDataManager | None:
        """Return the active data manager when available."""

        if self._data_manager is not None:
            return self._data_manager

        runtime_data = get_runtime_data(self.hass, self.entry_id)
        if runtime_data is None:
            return None

        self._data_manager = runtime_data.data_manager
        return self._data_manager

    async def _async_persist_door_sensor(
        self,
        dog_id: str,
        *,
        sensor: object = _UNSET,
        settings: object = _UNSET,
    ) -> None:
        """Persist normalised door sensor overrides when they change."""

        data_manager = self._ensure_data_manager()
        if data_manager is None:
            return

        updates: dict[str, Any] = {}

        if sensor is not _UNSET:
            updates[CONF_DOOR_SENSOR] = sensor

        if settings is not _UNSET:
            if isinstance(settings, DoorSensorSettingsConfig):
                payload = _settings_to_payload(settings)
                if payload and payload != DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD:
                    updates[CONF_DOOR_SENSOR_SETTINGS] = payload
                else:
                    updates[CONF_DOOR_SENSOR_SETTINGS] = None
            else:
                updates[CONF_DOOR_SENSOR_SETTINGS] = settings

        if not updates:
            return

        try:
            await data_manager.async_update_dog_data(dog_id, updates)
        except Exception as err:  # pragma: no cover - defensive guard
            _LOGGER.error(
                "Failed to persist door sensor overrides for %s: %s", dog_id, err
            )

    @staticmethod
    def _settings_for_persistence(
        raw_settings: Any, normalised: DoorSensorSettingsConfig
    ) -> object:
        """Return payload to persist when ``raw_settings`` differs from ``normalised``."""

        desired_payload = _settings_to_payload(normalised)

        if isinstance(raw_settings, DoorSensorSettingsConfig):
            current_payload = _settings_to_payload(raw_settings)
        elif isinstance(raw_settings, Mapping):
            current_payload = dict(raw_settings)
        else:
            current_payload = None

        if (
            current_payload is None
            and desired_payload == DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD
        ):
            return _UNSET

        if current_payload == desired_payload:
            return _UNSET

        return normalised

    async def async_initialize(
        self,
        dogs: list[DogConfigData],
        walk_manager: WalkManager | None = None,
        notification_manager: PawControlNotificationManager | None = None,
        *,
        data_manager: PawControlDataManager | None = None,
    ) -> None:
        """Initialize door sensor monitoring for configured dogs.

        Args:
            dogs: List of dog configurations
            walk_manager: Walk manager instance
            notification_manager: Notification manager instance
        """
        self._walk_manager = walk_manager
        self._notification_manager = notification_manager
        if data_manager is not None:
            self._data_manager = data_manager
        else:
            self._ensure_data_manager()

        # Configure door sensors for each dog
        for dog in dogs:
            dog_id = dog[DOG_ID_FIELD]
            dog_name = dog[DOG_NAME_FIELD]

            # Check if door sensor is configured for this dog
            door_sensor = dog.get(CONF_DOOR_SENSOR)
            if not door_sensor:
                _LOGGER.debug("No door sensor configured for %s", dog_name)
                continue

            # Validate door sensor entity exists
            trimmed_sensor = door_sensor.strip()
            if not trimmed_sensor:
                _LOGGER.debug("Door sensor entry for %s is blank", dog_name)
                continue

            if not await self._validate_sensor_entity(trimmed_sensor):
                _LOGGER.warning(
                    "Door sensor %s for %s is not available", door_sensor, dog_name
                )
                continue

            # Create configuration
            config = DoorSensorConfig(
                entity_id=trimmed_sensor,
                dog_id=dog_id,
                dog_name=dog_name,
                enabled=True,
            )

            # Apply any custom settings from dog configuration
            settings_config = ensure_door_sensor_settings_config(
                dog.get(CONF_DOOR_SENSOR_SETTINGS),
                base=config,
            )
            _apply_settings_to_config(config, settings_config)

            persist_sensor = _UNSET
            stored_sensor = dog.get(CONF_DOOR_SENSOR)
            if isinstance(stored_sensor, str):
                trimmed_stored = stored_sensor.strip()
                if (
                    trimmed_stored != stored_sensor
                    or trimmed_stored != config.entity_id
                ):
                    persist_sensor = config.entity_id
            elif stored_sensor is not None:
                persist_sensor = config.entity_id

            await self._async_persist_door_sensor(
                dog_id,
                sensor=persist_sensor,
                settings=self._settings_for_persistence(
                    dog.get(CONF_DOOR_SENSOR_SETTINGS), settings_config
                ),
            )

            self._sensor_configs[dog_id] = config
            self._detection_states[dog_id] = WalkDetectionState(dog_id=dog_id)

            _LOGGER.info(
                "Configured door sensor %s for %s with walk detection",
                door_sensor,
                dog_name,
            )

        # Start monitoring door sensors
        if self._sensor_configs:
            await self._start_sensor_monitoring()
            _LOGGER.info(
                "Door sensor walk detection active for %d dogs",
                len(self._sensor_configs),
            )
        else:
            _LOGGER.info("No door sensors configured for walk detection")

    async def _validate_sensor_entity(self, entity_id: str) -> bool:
        """Validate that door sensor entity exists and is available.

        Args:
            entity_id: Entity ID to validate

        Returns:
            True if entity is valid and available
        """
        # Check entity registry
        registry = er.async_get(self.hass)
        registry_entry = registry.async_get(entity_id)

        if registry_entry and registry_entry.disabled_by:
            _LOGGER.warning("Door sensor %s is disabled", entity_id)
            return False

        # Check current state
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.warning("Door sensor %s state not available", entity_id)
            return False

        # Check if it's a binary sensor with appropriate device class
        if state.domain != "binary_sensor":
            _LOGGER.warning(
                "Door sensor %s is not a binary_sensor (domain: %s)",
                entity_id,
                state.domain,
            )
            return False

        return True

    async def _start_sensor_monitoring(self) -> None:
        """Start monitoring all configured door sensors."""
        # Get all sensor entity IDs
        sensor_entities = [config.entity_id for config in self._sensor_configs.values()]

        # Track state changes for all door sensors
        async def handle_state_change(
            event: Event[EventStateChangedData],
        ) -> None:
            await self._handle_door_state_change(event)

        # Register state change listener
        listener = async_track_state_change_event(
            self.hass, sensor_entities, handle_state_change
        )
        self._state_listeners.append(listener)

        # Start cleanup task
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_states())

        _LOGGER.debug("Started monitoring %d door sensors", len(sensor_entities))

    async def _handle_door_state_change(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Handle door sensor state changes.

        Args:
            event: State change event
        """
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data.get("old_state")

        if not new_state or not old_state:
            return

        # Find which dog this sensor belongs to
        dog_id = None
        config = None
        for dog_id, cfg in self._sensor_configs.items():  # noqa: B007
            if cfg.entity_id == entity_id:
                config = cfg
                break

        if not config or not config.enabled:
            return

        detection_state = self._detection_states[dog_id]

        # Update state tracking
        detection_state.last_door_state = new_state.state
        detection_state.add_state_event(new_state.state)
        self._last_activity = dt_util.utcnow()

        # Handle door opening
        if old_state.state == STATE_OFF and new_state.state == STATE_ON:
            await self._handle_door_opened(config, detection_state)

        # Handle door closing
        elif old_state.state == STATE_ON and new_state.state == STATE_OFF:
            await self._handle_door_closed(config, detection_state)

    async def _handle_door_opened(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Handle door opening event.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        now = dt_util.now()
        state.door_opened_at = now
        state.consecutive_opens += 1

        _LOGGER.debug(
            "Door opened for %s (consecutive: %d)",
            config.dog_name,
            state.consecutive_opens,
        )

        # If dog is already on a walk, this might be return home
        if state.current_state == WALK_STATE_ACTIVE:
            state.current_state = WALK_STATE_RETURNING
            _LOGGER.debug("%s may be returning from walk", config.dog_name)
            return

        # Start potential walk detection
        if state.current_state == WALK_STATE_IDLE:
            state.current_state = WALK_STATE_POTENTIAL
            state.potential_walk_start = now

            # Schedule walk detection timeout
            async def check_walk_timeout():
                await asyncio.sleep(config.walk_detection_timeout)
                await self._handle_walk_timeout(config, state)

            asyncio.create_task(check_walk_timeout())  # noqa: RUF006

    async def _handle_door_closed(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Handle door closing event.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        now = dt_util.now()
        state.door_closed_at = now

        _LOGGER.debug("Door closed for %s", config.dog_name)

        # Calculate confidence based on door patterns
        state.confidence_score = state.calculate_confidence()

        # Handle different states
        if state.current_state == WALK_STATE_POTENTIAL:
            # Door closed after potential walk start
            if state.confidence_score >= config.confidence_threshold:
                await self._initiate_walk_detection(config, state)
            else:
                # Low confidence, reset to idle
                state.current_state = WALK_STATE_IDLE
                _LOGGER.debug(
                    "Low confidence (%.2f) for %s, not starting walk detection",
                    state.confidence_score,
                    config.dog_name,
                )

        elif state.current_state == WALK_STATE_RETURNING:
            # Dog returning from walk
            await self._handle_walk_return(config, state)

    async def _initiate_walk_detection(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Initiate walk detection based on door sensor patterns.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        _LOGGER.info(
            "Initiating walk detection for %s (confidence: %.2f)",
            config.dog_name,
            state.confidence_score,
        )

        if config.require_confirmation:
            # Send confirmation request
            await self._send_walk_confirmation_request(config, state)
        else:
            # Start walk automatically
            await self._start_automatic_walk(config, state)

    async def _send_walk_confirmation_request(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Send walk confirmation request via notifications.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        if self._notification_manager is None:
            _LOGGER.warning("No notification manager available for confirmation")
            await self._start_automatic_walk(config, state)
            return

        title = f"🚪 Walk detected: {config.dog_name}"
        message = f"Did {config.dog_name} just go for a walk? Door activity detected with {state.confidence_score:.0%} confidence."

        # Send notification with action buttons
        await self._notification_manager.async_send_notification(
            notification_type=NotificationType.SYSTEM_INFO,
            title=title,
            message=message,
            dog_id=config.dog_id,
            priority=NotificationPriority.NORMAL,
            data={
                "confirmation_type": "walk_detection",
                "door_sensor": config.entity_id,
                "confidence": state.confidence_score,
                "actions": [
                    {
                        "action": f"confirm_walk_{config.dog_id}",
                        "title": "Yes, start walk tracking",
                    },
                    {
                        "action": f"deny_walk_{config.dog_id}",
                        "title": "No, false alarm",
                    },
                ],
            },
            expires_in=timedelta(minutes=10),
        )

        # Store notification ID for response handling
        state.current_state = WALK_STATE_POTENTIAL

        # Schedule automatic timeout if no response
        async def confirmation_timeout():
            await asyncio.sleep(600)  # 10 minutes
            if state.current_state == WALK_STATE_POTENTIAL:
                _LOGGER.info(
                    "Walk confirmation timeout for %s, starting automatically",
                    config.dog_name,
                )
                await self._start_automatic_walk(config, state)

        asyncio.create_task(confirmation_timeout())  # noqa: RUF006

    async def _start_automatic_walk(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Start automatic walk tracking.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        if self._walk_manager is None:
            _LOGGER.error("No walk manager available to start walk")
            state.current_state = WALK_STATE_IDLE
            return

        try:
            # Start walk via walk manager
            walk_id = await self._walk_manager.async_start_walk(
                dog_id=config.dog_id,
                walk_type="door_sensor",
                detection_confidence=state.confidence_score,
                door_sensor=config.entity_id,
            )

            state.active_walk_id = walk_id
            state.current_state = WALK_STATE_ACTIVE

            # Update stats
            self._detection_stats["total_detections"] += 1
            self._detection_stats["successful_walks"] += 1

            # Fire walk started event
            await async_fire_event(
                self.hass,
                EVENT_WALK_STARTED,
                {
                    "dog_id": config.dog_id,
                    "dog_name": config.dog_name,
                    "walk_id": walk_id,
                    "detection_method": "door_sensor",
                    "confidence": state.confidence_score,
                    "door_sensor": config.entity_id,
                },
            )

            _LOGGER.info(
                "Started automatic walk for %s (walk_id: %s, confidence: %.2f)",
                config.dog_name,
                walk_id,
                state.confidence_score,
            )

            # Schedule automatic walk ending if enabled
            if config.auto_end_walks:

                async def auto_end_walk():
                    await asyncio.sleep(config.maximum_walk_duration)
                    if state.current_state == WALK_STATE_ACTIVE:
                        await self._end_automatic_walk(config, state, "timeout")

                asyncio.create_task(auto_end_walk())  # noqa: RUF006

        except Exception as err:
            _LOGGER.error(
                "Failed to start automatic walk for %s: %s", config.dog_name, err
            )
            state.current_state = WALK_STATE_IDLE

    async def _handle_walk_return(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Handle dog returning from walk.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        if state.current_state != WALK_STATE_RETURNING or state.active_walk_id is None:
            return

        # Calculate walk duration
        if state.potential_walk_start:
            duration = (dt_util.now() - state.potential_walk_start).total_seconds()

            # Check if walk duration is reasonable
            if duration < config.minimum_walk_duration:
                _LOGGER.debug(
                    "Walk duration too short for %s (%.1f minutes), not ending",
                    config.dog_name,
                    duration / 60,
                )
                state.current_state = WALK_STATE_ACTIVE
                return

        # End the walk
        await self._end_automatic_walk(config, state, "door_return")

    async def _end_automatic_walk(
        self, config: DoorSensorConfig, state: WalkDetectionState, reason: str
    ) -> None:
        """End automatic walk tracking.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
            reason: Reason for ending walk
        """
        if state.active_walk_id is None or self._walk_manager is None:
            return

        try:
            # End walk via walk manager
            walk_data = await self._walk_manager.async_end_walk(
                dog_id=config.dog_id,
                notes=f"Automatically ended by door sensor detection ({reason})",
            )

            # Calculate final duration if available
            duration_minutes = 0
            if walk_data and "duration" in walk_data:
                duration_minutes = walk_data["duration"] / 60

            # Reset state
            state.current_state = WALK_STATE_IDLE
            walk_id = state.active_walk_id
            state.active_walk_id = None
            state.potential_walk_start = None
            state.consecutive_opens = 0

            # Fire walk ended event
            await async_fire_event(
                self.hass,
                EVENT_WALK_ENDED,
                {
                    "dog_id": config.dog_id,
                    "dog_name": config.dog_name,
                    "walk_id": walk_id,
                    "detection_method": "door_sensor",
                    "end_reason": reason,
                    "duration_minutes": duration_minutes,
                },
            )

            _LOGGER.info(
                "Ended automatic walk for %s (reason: %s, duration: %.1f minutes)",
                config.dog_name,
                reason,
                duration_minutes,
            )

            # Send completion notification
            if self._notification_manager is not None:
                await self._notification_manager.async_send_notification(
                    notification_type=NotificationType.SYSTEM_INFO,
                    title=f"🏠 {config.dog_name} returned",
                    message=f"{config.dog_name} finished their walk (duration: {duration_minutes:.0f} minutes)",
                    dog_id=config.dog_id,
                    priority=NotificationPriority.LOW,
                )

        except Exception as err:
            _LOGGER.error(
                "Failed to end automatic walk for %s: %s", config.dog_name, err
            )

    async def _handle_walk_timeout(
        self, config: DoorSensorConfig, state: WalkDetectionState
    ) -> None:
        """Handle walk detection timeout.

        Args:
            config: Door sensor configuration
            state: Detection state for this dog
        """
        # Only handle timeout if still in potential state
        if state.current_state != WALK_STATE_POTENTIAL:
            return

        _LOGGER.debug(
            "Walk detection timeout for %s (confidence: %.2f)",
            config.dog_name,
            state.confidence_score,
        )

        # Reset to idle state
        state.current_state = WALK_STATE_IDLE
        state.potential_walk_start = None

    async def _cleanup_expired_states(self) -> None:
        """Background task to clean up expired detection states."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour

                now = dt_util.now()
                cleaned = 0

                for state in self._detection_states.values():
                    # Clean old state history
                    old_count = len(state.state_history)
                    cutoff = now - timedelta(hours=24)
                    state.state_history = [
                        (timestamp, event_state)
                        for timestamp, event_state in state.state_history
                        if timestamp > cutoff
                    ]
                    cleaned += old_count - len(state.state_history)

                if cleaned > 0:
                    _LOGGER.debug("Cleaned %d old state history entries", cleaned)

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Error in door sensor cleanup task: %s", err)

    async def async_handle_walk_confirmation(
        self, dog_id: str, confirmed: bool
    ) -> None:
        """Handle walk confirmation response.

        Args:
            dog_id: Dog identifier
            confirmed: Whether walk was confirmed
        """
        config = self._sensor_configs.get(dog_id)
        state = self._detection_states.get(dog_id)

        if not config or not state or state.current_state != WALK_STATE_POTENTIAL:
            return

        if confirmed:
            await self._start_automatic_walk(config, state)
        else:
            # Mark as false positive
            self._detection_stats["false_positives"] += 1
            state.current_state = WALK_STATE_IDLE
            state.potential_walk_start = None

            _LOGGER.info("Walk detection denied for %s", config.dog_name)

    async def async_get_detection_status(self) -> DetectionStatus:
        """Get current detection status for all dogs.

        Returns:
            Detection status information
        """
        status: DetectionStatus = {
            "configured_dogs": len(self._sensor_configs),
            "active_detections": 0,
            "detection_states": {},
            "statistics": cast(DetectionStatistics, dict(self._detection_stats)),
        }

        for dog_id, state in self._detection_states.items():
            config = self._sensor_configs[dog_id]

            if state.current_state != WALK_STATE_IDLE:
                status["active_detections"] += 1

            detection_entry: DetectionStatusEntry = {
                "dog_name": config.dog_name,
                "door_sensor": config.entity_id,
                "current_state": state.current_state,
                "confidence_score": state.confidence_score,
                "active_walk_id": state.active_walk_id,
                "last_door_state": state.last_door_state,
                "recent_activity": len(state.state_history),
            }
            status["detection_states"][dog_id] = detection_entry

        return status

    async def async_update_dog_configuration(
        self,
        dog_id: str,
        door_sensor: str | None,
        settings: dict[str, Any] | None = None,
    ) -> bool:
        """Update door sensor configuration for a dog.

        Args:
            dog_id: Dog identifier
            door_sensor: New door sensor entity ID
            settings: Optional door sensor settings

        Returns:
            True if configuration was updated
        """
        trimmed_sensor: str | None = None
        removing = False

        if door_sensor is not None:
            trimmed_sensor = door_sensor.strip()
            if not trimmed_sensor:
                removing = True
            elif not await self._validate_sensor_entity(trimmed_sensor):
                _LOGGER.warning("Invalid door sensor entity: %s", door_sensor)
                return False
        elif settings is None:
            removing = True

        changed = False

        persist_sensor: object = _UNSET
        persist_settings: object = _UNSET

        if removing:
            if dog_id in self._sensor_configs:
                del self._sensor_configs[dog_id]
                self._detection_states.pop(dog_id, None)
                changed = True
                _LOGGER.info("Removed door sensor config for dog %s", dog_id)
                persist_sensor = None
                persist_settings = None
            else:
                _LOGGER.debug(
                    "Removal requested for unknown door sensor configuration: %s",
                    dog_id,
                )
        else:
            config = self._sensor_configs.get(dog_id)
            if not config:
                _LOGGER.warning("No door sensor configuration found for dog %s", dog_id)
                return False

            if trimmed_sensor and config.entity_id != trimmed_sensor:
                config.entity_id = trimmed_sensor
                changed = True
                persist_sensor = trimmed_sensor

            if settings is not None:
                before = _settings_from_config(config)
                normalised = ensure_door_sensor_settings_config(settings, base=before)
                if normalised != before:
                    _apply_settings_to_config(config, normalised)
                    changed = True
                    persist_settings = normalised

            if changed:
                _LOGGER.info("Updated door sensor config for %s", config.dog_name)
            else:
                _LOGGER.debug(
                    "Door sensor configuration for %s unchanged", config.dog_name
                )

        if changed:
            await self._async_persist_door_sensor(
                dog_id,
                sensor=persist_sensor,
                settings=persist_settings,
            )
            await self._stop_sensor_monitoring()
            if self._sensor_configs:
                await self._start_sensor_monitoring()

        return True

    async def _stop_sensor_monitoring(self) -> None:
        """Stop monitoring door sensors."""
        # Cancel all listeners
        for listener in self._state_listeners:
            listener()
        self._state_listeners.clear()

        # Cancel cleanup task
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            self._cleanup_task = None

    async def async_cleanup(self) -> None:
        """Clean up door sensor manager."""
        await self._stop_sensor_monitoring()

        # Clean up any active walks
        for state in self._detection_states.values():
            if state.active_walk_id is not None and self._walk_manager is not None:
                try:
                    await self._walk_manager.async_end_walk(
                        dog_id=state.dog_id,
                        notes="Walk ended due to system cleanup",
                    )
                except Exception as err:
                    _LOGGER.error("Error ending walk during cleanup: %s", err)

        self._sensor_configs.clear()
        self._detection_states.clear()

    def get_configured_sensors(self) -> dict[str, str]:
        """Get mapping of dog_id to door sensor entity_id.

        Returns:
            Dictionary mapping dog_id to sensor entity_id
        """
        return {
            dog_id: config.entity_id for dog_id, config in self._sensor_configs.items()
        }

    def is_dog_on_walk(self, dog_id: str) -> bool:
        """Check if dog is currently on a detected walk.

        Args:
            dog_id: Dog identifier

        Returns:
            True if dog is on a walk
        """
        state = self._detection_states.get(dog_id)
        return bool(
            state and state.current_state == WALK_STATE_ACTIVE and state.active_walk_id
        )
