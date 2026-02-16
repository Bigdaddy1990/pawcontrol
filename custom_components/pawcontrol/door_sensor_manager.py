"""Door sensor integration for automatic walk detection.

Monitors door sensors and automatically detects when dogs go for walks
based on door state changes and configurable timing logic.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Final, cast

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import (
  CALLBACK_TYPE,
  Event,
  EventStateChangedData,
  HomeAssistant,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
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
  DEFAULT_CONFIDENCE_THRESHOLD,
  DEFAULT_DOOR_CLOSED_DELAY,
  DEFAULT_DOOR_SENSOR_SETTINGS,
  DEFAULT_MAXIMUM_WALK_DURATION,
  DEFAULT_MINIMUM_WALK_DURATION,
  DEFAULT_WALK_DETECTION_TIMEOUT,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  CacheDiagnosticsMetadata,
  CacheDiagnosticsSnapshot,
  DetectionStatistics,
  DetectionStatus,
  DetectionStatusEntry,
  DogConfigData,
  DoorSensorConfigUpdate,
  DoorSensorDogSnapshot,
  DoorSensorManagerSnapshot,
  DoorSensorManagerStats,
  DoorSensorOverrideScalar,
  DoorSensorSettingsConfig,
  DoorSensorSettingsInput,
  DoorSensorSettingsPayload,
  DoorSensorStateHistoryEntry,
  DoorSensorStateSnapshot,
  JSONLikeMapping,
  JSONMutableMapping,
)
from .utils import async_fire_event

if TYPE_CHECKING:
  from .data_manager import PawControlDataManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111
  from .walk_manager import WalkManager  # noqa: E111

_LOGGER = logging.getLogger(__name__)

_UNSET: object = object()


def _coerce_int(
  value: DoorSensorOverrideScalar,
  *,
  default: int,
  minimum: int | None = None,
  maximum: int | None = None,
) -> int:
  """Coerce ``value`` to an integer within optional bounds."""  # noqa: E111

  if isinstance(value, bool) or value is None:  # noqa: E111
    return default

  candidate: int  # noqa: E111
  if isinstance(value, int | float):  # noqa: E111
    candidate = int(value)
  elif isinstance(value, str):  # noqa: E111
    stripped = value.strip()
    if not stripped:
      return default  # noqa: E111
    try:
      candidate = int(float(stripped))  # noqa: E111
    except ValueError:
      return default  # noqa: E111
  else:  # noqa: E111
    return default

  if minimum is not None and candidate < minimum:  # noqa: E111
    candidate = minimum
  if maximum is not None and candidate > maximum:  # noqa: E111
    candidate = maximum
  return candidate  # noqa: E111


def _coerce_float(
  value: DoorSensorOverrideScalar,
  *,
  default: float,
  minimum: float | None = None,
  maximum: float | None = None,
) -> float:
  """Coerce ``value`` to a float within optional bounds."""  # noqa: E111

  if isinstance(value, bool) or value is None:  # noqa: E111
    return default

  candidate: float  # noqa: E111
  if isinstance(value, int | float):  # noqa: E111
    candidate = float(value)
  elif isinstance(value, str):  # noqa: E111
    stripped = value.strip()
    if not stripped:
      return default  # noqa: E111
    try:
      candidate = float(stripped)  # noqa: E111
    except ValueError:
      return default  # noqa: E111
  else:  # noqa: E111
    return default

  if minimum is not None and candidate < minimum:  # noqa: E111
    candidate = minimum
  if maximum is not None and candidate > maximum:  # noqa: E111
    candidate = maximum
  return candidate  # noqa: E111


def _coerce_bool(value: DoorSensorOverrideScalar, *, default: bool) -> bool:
  """Normalise ``value`` to a boolean."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return value

  if isinstance(value, int | float):  # noqa: E111
    # Treat numeric inputs as truthy when non-zero to support options payloads
    # that pass integers (for example, 0/1 toggles from legacy configs).
    return bool(value)

  if isinstance(value, str):  # noqa: E111
    stripped = value.strip()
    if not stripped:
      return default  # noqa: E111

    lowered = stripped.lower()
    if lowered in {"true", "1", "yes", "on"}:
      return True  # noqa: E111
    if lowered in {"false", "0", "no", "off"}:
      return False  # noqa: E111

    try:
      numeric = float(stripped)  # noqa: E111
    except ValueError:
      return default  # noqa: E111
    return bool(numeric)

  return default  # noqa: E111


def _settings_from_config(
  config: DoorSensorConfig | DoorSensorSettingsConfig | None,
) -> DoorSensorSettingsConfig:
  """Return a normalised settings snapshot for ``config``."""  # noqa: E111

  if isinstance(config, DoorSensorSettingsConfig):  # noqa: E111
    return config
  if config is None:  # noqa: E111
    return DEFAULT_DOOR_SENSOR_SETTINGS
  return DoorSensorSettingsConfig(  # noqa: E111
    walk_detection_timeout=config.walk_detection_timeout,
    minimum_walk_duration=config.minimum_walk_duration,
    maximum_walk_duration=config.maximum_walk_duration,
    door_closed_delay=config.door_closed_delay,
    require_confirmation=config.require_confirmation,
    auto_end_walks=config.auto_end_walks,
    confidence_threshold=config.confidence_threshold,
  )


def ensure_door_sensor_settings_config(
  overrides: DoorSensorSettingsInput | None,
  *,
  base: DoorSensorSettingsConfig | DoorSensorConfig | None = None,
) -> DoorSensorSettingsConfig:
  """Return a normalised ``DoorSensorSettingsConfig`` from ``overrides``."""  # noqa: E111

  base_settings = _settings_from_config(base)  # noqa: E111

  if overrides is None:  # noqa: E111
    return base_settings

  raw_items: list[tuple[str, DoorSensorOverrideScalar]]  # noqa: E111
  if isinstance(overrides, DoorSensorSettingsConfig):  # noqa: E111
    raw_items = [
      (key, cast(DoorSensorOverrideScalar, value))
      for key, value in _settings_to_payload(overrides).items()
    ]
  elif isinstance(overrides, Mapping):  # noqa: E111
    raw_items = [
      (key, cast(DoorSensorOverrideScalar, value))
      for key, value in overrides.items()
      if isinstance(key, str)
    ]
  else:  # noqa: E111
    raise TypeError(
      "door sensor settings must be a mapping or DoorSensorSettingsConfig",
    )

  normalised: dict[str, DoorSensorOverrideScalar] = {}  # noqa: E111
  for key, value in raw_items:  # noqa: E111
    normalised[key.strip().lower()] = value

  def pick(*aliases: str) -> DoorSensorOverrideScalar:  # noqa: E111
    for alias in aliases:
      alias_key = alias.lower()  # noqa: E111
      if alias_key in normalised:  # noqa: E111
        return normalised[alias_key]
    return None

  timeout = _coerce_int(  # noqa: E111
    pick("timeout", "walk_detection_timeout", "walk_timeout"),
    default=base_settings.walk_detection_timeout,
    minimum=30,
    maximum=21600,
  )
  minimum_duration = _coerce_int(  # noqa: E111
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
  maximum_duration = _coerce_int(  # noqa: E111
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
  door_delay = _coerce_int(  # noqa: E111
    pick(
      "door_closed_delay",
      "door_closed_timeout",
      "close_delay",
      "close_timeout",
    ),
    default=base_settings.door_closed_delay,
    minimum=0,
    maximum=1800,
  )
  require_confirmation = _coerce_bool(  # noqa: E111
    pick("require_confirmation", "confirmation_required"),
    default=base_settings.require_confirmation,
  )
  auto_end_walks = _coerce_bool(  # noqa: E111
    pick("auto_end_walks", "auto_end_walk", "auto_close"),
    default=base_settings.auto_end_walks,
  )
  confidence_threshold = _coerce_float(  # noqa: E111
    pick("confidence_threshold", "confidence", "threshold"),
    default=base_settings.confidence_threshold,
    minimum=0.0,
    maximum=1.0,
  )

  return DoorSensorSettingsConfig(  # noqa: E111
    walk_detection_timeout=timeout,
    minimum_walk_duration=minimum_duration,
    maximum_walk_duration=maximum_duration,
    door_closed_delay=door_delay,
    require_confirmation=require_confirmation,
    auto_end_walks=auto_end_walks,
    confidence_threshold=confidence_threshold,
  )


def _settings_to_payload(
  settings: DoorSensorSettingsConfig,
) -> DoorSensorSettingsPayload:
  """Return a serialisable payload for ``settings``."""  # noqa: E111

  payload: DoorSensorSettingsPayload = {  # noqa: E111
    "walk_detection_timeout": settings.walk_detection_timeout,
    "minimum_walk_duration": settings.minimum_walk_duration,
    "maximum_walk_duration": settings.maximum_walk_duration,
    "door_closed_delay": settings.door_closed_delay,
    "require_confirmation": settings.require_confirmation,
    "auto_end_walks": settings.auto_end_walks,
    "confidence_threshold": settings.confidence_threshold,
  }
  return payload  # noqa: E111


DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD: Final[DoorSensorSettingsPayload] = (
  _settings_to_payload(DEFAULT_DOOR_SENSOR_SETTINGS)
)


def _apply_settings_to_config(
  config: DoorSensorConfig,
  settings: DoorSensorSettingsConfig,
) -> None:
  """Apply ``settings`` to ``config`` in-place."""  # noqa: E111

  config.walk_detection_timeout = settings.walk_detection_timeout  # noqa: E111
  config.minimum_walk_duration = settings.minimum_walk_duration  # noqa: E111
  config.maximum_walk_duration = settings.maximum_walk_duration  # noqa: E111
  config.door_closed_delay = settings.door_closed_delay  # noqa: E111
  config.require_confirmation = settings.require_confirmation  # noqa: E111
  config.auto_end_walks = settings.auto_end_walks  # noqa: E111
  config.confidence_threshold = settings.confidence_threshold  # noqa: E111


# Walk detection states
WALK_STATE_IDLE = "idle"
WALK_STATE_POTENTIAL = "potential"
WALK_STATE_ACTIVE = "active"
WALK_STATE_RETURNING = "returning"


def _serialize_datetime(value: datetime | None) -> str | None:
  """Serialize datetimes to ISO format for diagnostics."""  # noqa: E111

  if value is None:  # noqa: E111
    return None
  return dt_util.as_utc(value).isoformat()  # noqa: E111


def _classify_timestamp(value: datetime | None) -> tuple[str | None, int | None]:
  """Return anomaly classification for ``value`` if thresholds are crossed."""  # noqa: E111

  if value is None:  # noqa: E111
    return None, None

  delta = dt_util.utcnow() - dt_util.as_utc(value)  # noqa: E111
  age_seconds = int(delta.total_seconds())  # noqa: E111

  if delta < -CACHE_TIMESTAMP_FUTURE_THRESHOLD:  # noqa: E111
    return "future", age_seconds
  if delta > CACHE_TIMESTAMP_STALE_THRESHOLD:  # noqa: E111
    return "stale", age_seconds
  return None, age_seconds  # noqa: E111


class _DoorSensorManagerCacheMonitor:
  """Expose door sensor manager diagnostics to cache snapshots."""  # noqa: E111

  __slots__ = ("_manager",)  # noqa: E111

  def __init__(self, manager: DoorSensorManager) -> None:  # noqa: E111
    self._manager = manager

  def _build_payload(  # noqa: E111
    self,
  ) -> tuple[
    DoorSensorManagerStats,
    DoorSensorManagerSnapshot,
    CacheDiagnosticsMetadata,
  ]:
    manager = self._manager
    configs = getattr(manager, "_sensor_configs", {})
    states = getattr(manager, "_detection_states", {})
    stats_payload = dict(getattr(manager, "_detection_stats", {}))
    manager_last_activity = getattr(manager, "_last_activity", None)

    per_dog: dict[str, DoorSensorDogSnapshot] = {}
    active_detections = 0
    timestamp_anomalies: dict[str, str] = {}

    for dog_id, config in configs.items():
      if not isinstance(dog_id, str):  # noqa: E111
        continue

      state = states.get(dog_id)  # noqa: E111
      if state is not None and state.current_state != WALK_STATE_IDLE:  # noqa: E111
        active_detections += 1

      config_payload: DoorSensorDogSnapshot = {  # noqa: E111
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

      if state is not None:  # noqa: E111
        last_activity_source: datetime | None = state.door_closed_at
        if last_activity_source is None:
          last_activity_source = state.door_opened_at  # noqa: E111
        if (
          last_activity_source is None
          and state.state_history
          and isinstance(state.state_history[-1][0], datetime)
        ):
          last_activity_source = state.state_history[-1][0]  # noqa: E111

        anomaly_reason, state_age = _classify_timestamp(
          last_activity_source,
        )

        state_history: list[DoorSensorStateHistoryEntry] = [
          {
            "timestamp": _serialize_datetime(timestamp),
            "state": event_state,
          }
          for timestamp, event_state in getattr(state, "state_history", [])
          if isinstance(event_state, str)
        ]

        state_payload: DoorSensorStateSnapshot = {
          "current_state": state.current_state,
          "door_opened_at": _serialize_datetime(state.door_opened_at),
          "door_closed_at": _serialize_datetime(state.door_closed_at),
          "potential_walk_start": _serialize_datetime(
            state.potential_walk_start,
          ),
          "active_walk_id": state.active_walk_id,
          "confidence_score": round(float(state.confidence_score), 3),
          "last_door_state": state.last_door_state,
          "consecutive_opens": state.consecutive_opens,
          "state_history": state_history,
        }

        if state_age is not None:
          state_payload["last_activity_age_seconds"] = state_age  # noqa: E111

        if anomaly_reason is not None:
          timestamp_anomalies[dog_id] = anomaly_reason  # noqa: E111

        config_payload["state"] = state_payload
      per_dog[dog_id] = config_payload  # noqa: E111

    stats_payload_typed = cast(DetectionStatistics, dict(stats_payload))
    stats: DoorSensorManagerStats = {
      **stats_payload_typed,
      "configured_sensors": len(per_dog),
      "active_detections": active_detections,
    }

    manager_anomaly, manager_age = _classify_timestamp(
      manager_last_activity,
    )
    if manager_age is not None:
      stats["last_activity_age_seconds"] = manager_age  # noqa: E111

    snapshot: DoorSensorManagerSnapshot = {
      "per_dog": per_dog,
      "detection_stats": stats_payload_typed,
      "manager_last_activity": _serialize_datetime(manager_last_activity),
    }

    per_dog_payload = cast(JSONMutableMapping, per_dog)
    diagnostics: CacheDiagnosticsMetadata = {
      "per_dog": per_dog_payload,
      "detection_stats": stats_payload,
      "cleanup_task_active": getattr(manager, "_cleanup_task", None) is not None,
      "manager_last_activity": _serialize_datetime(manager_last_activity),
    }

    if manager_age is not None:
      diagnostics["manager_last_activity_age_seconds"] = manager_age  # noqa: E111

    if manager_anomaly is not None:
      timestamp_anomalies["manager"] = manager_anomaly  # noqa: E111

    if timestamp_anomalies:
      diagnostics["timestamp_anomalies"] = timestamp_anomalies  # noqa: E111

    return stats, snapshot, diagnostics

  def coordinator_snapshot(self) -> CacheDiagnosticsSnapshot:  # noqa: E111
    stats, snapshot, diagnostics = self._build_payload()
    return CacheDiagnosticsSnapshot(
      stats=cast(JSONMutableMapping, dict(stats)),
      snapshot=cast(JSONMutableMapping, dict(snapshot)),
      diagnostics=diagnostics,
    )

  def get_stats(self) -> JSONMutableMapping:  # noqa: E111
    stats, _snapshot, _diagnostics = self._build_payload()
    return cast(JSONMutableMapping, dict(stats))

  def get_diagnostics(self) -> CacheDiagnosticsMetadata:  # noqa: E111
    _stats, _snapshot, diagnostics = self._build_payload()
    return diagnostics


@dataclass
class DoorSensorConfig:
  """Configuration for door sensor walk detection."""  # noqa: E111

  entity_id: str  # noqa: E111
  dog_id: str  # noqa: E111
  dog_name: str  # noqa: E111
  enabled: bool = True  # noqa: E111
  walk_detection_timeout: int = DEFAULT_WALK_DETECTION_TIMEOUT  # noqa: E111
  minimum_walk_duration: int = DEFAULT_MINIMUM_WALK_DURATION  # noqa: E111
  maximum_walk_duration: int = DEFAULT_MAXIMUM_WALK_DURATION  # noqa: E111
  door_closed_delay: int = DEFAULT_DOOR_CLOSED_DELAY  # noqa: E111
  require_confirmation: bool = True  # noqa: E111
  auto_end_walks: bool = True  # noqa: E111
  confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD  # noqa: E111


@dataclass
class WalkDetectionState:
  """State tracking for door sensor based walk detection."""  # noqa: E111

  dog_id: str  # noqa: E111
  current_state: str = WALK_STATE_IDLE  # noqa: E111
  door_opened_at: datetime | None = None  # noqa: E111
  door_closed_at: datetime | None = None  # noqa: E111
  potential_walk_start: datetime | None = None  # noqa: E111
  active_walk_id: str | None = None  # noqa: E111
  confidence_score: float = 0.0  # noqa: E111
  last_door_state: str | None = None  # noqa: E111
  consecutive_opens: int = 0  # noqa: E111
  state_history: list[tuple[datetime, str]] = field(default_factory=list)  # noqa: E111

  def add_state_event(self, state: str) -> None:  # noqa: E111
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

  def calculate_confidence(self) -> float:  # noqa: E111
    """Calculate confidence score based on door sensor patterns."""
    if len(self.state_history) < 2:
      return 0.0  # noqa: E111

    now = dt_util.now()
    recent_events = [
      (timestamp, event_state)
      for timestamp, event_state in self.state_history
      if (now - timestamp).total_seconds() < 600  # Last 10 minutes
    ]

    if len(recent_events) < 2:
      return 0.0  # noqa: E111

    confidence = 0.0

    # Pattern: Single open followed by closed (typical walk pattern)
    if len(recent_events) == 2:
      first_event = recent_events[0]  # noqa: E111
      second_event = recent_events[1]  # noqa: E111

      if first_event[1] == STATE_ON and second_event[1] == STATE_OFF:  # noqa: E111
        # Time between open and close
        duration = (second_event[0] - first_event[0]).total_seconds()

        # Optimal duration: 10-60 seconds (person and dog going out)
        if 10 <= duration <= 60:
          confidence += 0.8  # noqa: E111
        elif duration <= 120:
          confidence += 0.6  # noqa: E111
        else:
          confidence += 0.3  # noqa: E111

    # Pattern: Multiple quick opens/closes (uncertainty)
    rapid_changes = len(
      [event for event in recent_events if (now - event[0]).total_seconds() < 120],
    )

    if rapid_changes > 4:
      confidence *= 0.5  # Reduce confidence for erratic patterns  # noqa: E111

    # Time of day bonus (common walk times)
    current_hour = now.hour
    if current_hour in [6, 7, 8, 17, 18, 19, 20]:  # Morning and evening
      confidence += 0.1  # noqa: E111
    elif current_hour in [12, 13]:  # Lunch time
      confidence += 0.05  # noqa: E111

    return min(confidence, 1.0)


class DoorSensorManager:
  """Manager for door sensor based walk detection."""  # noqa: E111

  def __init__(self, hass: HomeAssistant, entry_id: str) -> None:  # noqa: E111
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
    self._background_tasks: set[asyncio.Task[object]] = set()
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

  def _track_background_task(self, task: asyncio.Task[object]) -> None:  # noqa: E111
    """Track a background task for lifecycle management.

    Storing a reference prevents tasks from being garbage collected early and
    makes it possible to cancel them during unload/cleanup if needed.
    """
    self._background_tasks.add(task)
    task.add_done_callback(self._background_tasks.discard)

  def register_cache_monitors(  # noqa: E111
    self,
    registrar: CacheMonitorRegistrar,
    *,
    prefix: str = "door_sensor",
  ) -> None:
    """Register cache diagnostics for the door sensor manager."""

    if registrar is None:
      raise ValueError("registrar is required")  # noqa: E111

    _LOGGER.debug(
      "Registering door sensor cache monitor with prefix %s",
      prefix,
    )
    registrar.register_cache_monitor(
      f"{prefix}_cache",
      _DoorSensorManagerCacheMonitor(self),
    )

  def _ensure_data_manager(self) -> PawControlDataManager | None:  # noqa: E111
    """Return the active data manager when available."""

    if self._data_manager is not None:
      return self._data_manager  # noqa: E111

    runtime_data = get_runtime_data(self.hass, self.entry_id)
    if runtime_data is None:
      return None  # noqa: E111

    self._data_manager = runtime_data.data_manager
    return self._data_manager

  async def _async_persist_door_sensor(  # noqa: E111
    self,
    dog_id: str,
    *,
    sensor: object = _UNSET,
    settings: object = _UNSET,
  ) -> None:
    """Persist normalised door sensor overrides when they change."""

    data_manager = self._ensure_data_manager()
    if data_manager is None:
      _LOGGER.error(  # noqa: E111
        "Data manager unavailable, cannot persist door sensor changes for %s",
        dog_id,
      )
      return  # noqa: E111

    updates: DoorSensorConfigUpdate = {}

    if sensor is not _UNSET:
      updates[CONF_DOOR_SENSOR] = cast(str | None, sensor)  # noqa: E111

    if settings is not _UNSET:
      if isinstance(settings, DoorSensorSettingsConfig):  # noqa: E111
        payload = _settings_to_payload(settings)
        if payload and payload != DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD:
          updates[CONF_DOOR_SENSOR_SETTINGS] = payload  # noqa: E111
        else:
          updates[CONF_DOOR_SENSOR_SETTINGS] = None  # noqa: E111
      elif settings is None:  # noqa: E111
        updates[CONF_DOOR_SENSOR_SETTINGS] = None
      else:  # noqa: E111
        updates[CONF_DOOR_SENSOR_SETTINGS] = cast(
          DoorSensorSettingsPayload | None,
          settings,
        )

    if not updates:
      return  # noqa: E111

    update_payload = cast(JSONLikeMapping, updates)

    try:
      await data_manager.async_update_dog_data(dog_id, update_payload)  # noqa: E111
    except Exception as err:  # pragma: no cover - defensive guard
      _LOGGER.error(  # noqa: E111
        "Failed to persist door sensor overrides for %s: %s",
        dog_id,
        err,
      )

  @staticmethod  # noqa: E111
  def _settings_for_persistence(  # noqa: E111
    raw_settings: object,
    normalised: DoorSensorSettingsConfig,
  ) -> object:
    """Return payload to persist when ``raw_settings`` differs from ``normalised``."""

    desired_payload = _settings_to_payload(normalised)

    current_payload: DoorSensorSettingsPayload | None
    if isinstance(raw_settings, DoorSensorSettingsConfig):
      current_payload = _settings_to_payload(raw_settings)  # noqa: E111
    elif isinstance(raw_settings, Mapping):
      current_payload = cast(  # noqa: E111
        DoorSensorSettingsPayload | None,
        {key: value for key, value in raw_settings.items() if isinstance(key, str)},
      )
    else:
      current_payload = None  # noqa: E111

    if (
      current_payload is None
      and desired_payload == DEFAULT_DOOR_SENSOR_SETTINGS_PAYLOAD
    ):
      return _UNSET  # noqa: E111

    if current_payload == desired_payload:
      return _UNSET  # noqa: E111

    return normalised

  async def async_initialize(  # noqa: E111
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
      self._data_manager = data_manager  # noqa: E111
    else:
      self._ensure_data_manager()  # noqa: E111

    # Configure door sensors for each dog
    for dog in dogs:
      dog_id = dog[DOG_ID_FIELD]  # noqa: E111
      dog_name = dog[DOG_NAME_FIELD]  # noqa: E111

      # Check if door sensor is configured for this dog  # noqa: E114
      door_sensor = dog.get(CONF_DOOR_SENSOR)  # noqa: E111
      if not door_sensor:  # noqa: E111
        _LOGGER.debug("No door sensor configured for %s", dog_name)
        continue

      if not isinstance(door_sensor, str):  # noqa: E111
        _LOGGER.debug(
          "Door sensor entry for %s is not a string: %s",
          dog_name,
          door_sensor,
        )
        continue

      # Validate door sensor entity exists  # noqa: E114
      trimmed_sensor = door_sensor.strip()  # noqa: E111
      if not trimmed_sensor:  # noqa: E111
        _LOGGER.debug("Door sensor entry for %s is blank", dog_name)
        continue

      if not await self._validate_sensor_entity(trimmed_sensor):  # noqa: E111
        _LOGGER.warning(
          "Door sensor %s for %s is not available",
          door_sensor,
          dog_name,
        )
        continue

      # Create configuration  # noqa: E114
      config = DoorSensorConfig(  # noqa: E111
        entity_id=trimmed_sensor,
        dog_id=dog_id,
        dog_name=dog_name,
        enabled=True,
      )

      raw_settings = dog.get(CONF_DOOR_SENSOR_SETTINGS)  # noqa: E111
      if not isinstance(raw_settings, DoorSensorSettingsConfig | Mapping):  # noqa: E111
        raw_settings = None

      # Apply any custom settings from dog configuration  # noqa: E114
      settings_config = ensure_door_sensor_settings_config(  # noqa: E111
        raw_settings,
        base=config,
      )
      _apply_settings_to_config(config, settings_config)  # noqa: E111

      persist_sensor = _UNSET  # noqa: E111
      stored_sensor = dog.get(CONF_DOOR_SENSOR)  # noqa: E111
      if isinstance(stored_sensor, str):  # noqa: E111
        trimmed_stored = stored_sensor.strip()
        if trimmed_stored != stored_sensor or trimmed_stored != config.entity_id:
          persist_sensor = config.entity_id  # noqa: E111
      elif stored_sensor is not None:  # noqa: E111
        persist_sensor = config.entity_id

      await self._async_persist_door_sensor(  # noqa: E111
        dog_id,
        sensor=persist_sensor,
        settings=self._settings_for_persistence(
          raw_settings,
          settings_config,
        ),
      )

      self._sensor_configs[dog_id] = config  # noqa: E111
      self._detection_states[dog_id] = WalkDetectionState(dog_id=dog_id)  # noqa: E111

      _LOGGER.info(  # noqa: E111
        "Configured door sensor %s for %s with walk detection",
        door_sensor,
        dog_name,
      )

    # Start monitoring door sensors
    if self._sensor_configs:
      await self._start_sensor_monitoring()  # noqa: E111
      _LOGGER.info(  # noqa: E111
        "Door sensor walk detection active for %d dogs",
        len(self._sensor_configs),
      )
    else:
      _LOGGER.info("No door sensors configured for walk detection")  # noqa: E111

  async def _validate_sensor_entity(self, entity_id: str) -> bool:  # noqa: E111
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
      _LOGGER.warning("Door sensor %s is disabled", entity_id)  # noqa: E111
      return False  # noqa: E111

    # Check current state
    state = self.hass.states.get(entity_id)
    if state is None:
      _LOGGER.warning("Door sensor %s state not available", entity_id)  # noqa: E111
      return False  # noqa: E111

    # Check if it's a binary sensor with appropriate device class
    if state.domain != "binary_sensor":
      _LOGGER.warning(  # noqa: E111
        "Door sensor %s is not a binary_sensor (domain: %s)",
        entity_id,
        state.domain,
      )
      return False  # noqa: E111

    return True

  async def _start_sensor_monitoring(self) -> None:  # noqa: E111
    """Start monitoring all configured door sensors."""
    # Get all sensor entity IDs
    sensor_entities = [config.entity_id for config in self._sensor_configs.values()]

    # Track state changes for all door sensors
    async def handle_state_change(
      event: Event[EventStateChangedData],
    ) -> None:
      await self._handle_door_state_change(event)  # noqa: E111

    # Register state change listener
    listener = async_track_state_change_event(
      self.hass,
      sensor_entities,
      handle_state_change,
    )
    self._state_listeners.append(listener)

    # Start cleanup task
    if not self._cleanup_task:
      self._cleanup_task = asyncio.create_task(  # noqa: E111
        self._cleanup_expired_states(),
      )

    _LOGGER.debug(
      "Started monitoring %d door sensors",
      len(sensor_entities),
    )

  async def _handle_door_state_change(  # noqa: E111
    self,
    event: Event[EventStateChangedData],
  ) -> None:
    """Handle door sensor state changes.

    Args:
        event: State change event
    """
    entity_id = event.data["entity_id"]
    new_state = event.data["new_state"]
    old_state = event.data.get("old_state")

    if not new_state or not old_state:
      return  # noqa: E111

    # Find which dog this sensor belongs to
    dog_id: str | None = None
    config = None
    for cfg in self._sensor_configs.values():
      if cfg.entity_id == entity_id:  # noqa: E111
        config = cfg
        break

    if dog_id is None or not config or not config.enabled:
      return  # noqa: E111

    detection_state = self._detection_states[dog_id]

    # Update state tracking
    detection_state.last_door_state = new_state.state
    detection_state.add_state_event(new_state.state)
    self._last_activity = dt_util.utcnow()

    # Handle door opening
    if old_state.state == STATE_OFF and new_state.state == STATE_ON:
      await self._handle_door_opened(config, detection_state)  # noqa: E111

    # Handle door closing
    elif old_state.state == STATE_ON and new_state.state == STATE_OFF:
      await self._handle_door_closed(config, detection_state)  # noqa: E111

  async def _handle_door_opened(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
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
      state.current_state = WALK_STATE_RETURNING  # noqa: E111
      _LOGGER.debug("%s may be returning from walk", config.dog_name)  # noqa: E111
      return  # noqa: E111

    # Start potential walk detection
    if state.current_state == WALK_STATE_IDLE:
      state.current_state = WALK_STATE_POTENTIAL  # noqa: E111
      state.potential_walk_start = now  # noqa: E111

      # Schedule walk detection timeout  # noqa: E114
      async def check_walk_timeout() -> None:  # noqa: E111
        await asyncio.sleep(config.walk_detection_timeout)
        await self._handle_walk_timeout(config, state)

      self._track_background_task(  # noqa: E111
        asyncio.create_task(
          check_walk_timeout(),
          name="pawcontrol_check_walk_timeout",
        ),
      )

  async def _handle_door_closed(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
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
      # Door closed after potential walk start  # noqa: E114
      if state.confidence_score >= config.confidence_threshold:  # noqa: E111
        await self._initiate_walk_detection(config, state)
      else:  # noqa: E111
        # Low confidence, reset to idle
        state.current_state = WALK_STATE_IDLE
        _LOGGER.debug(
          "Low confidence (%.2f) for %s, not starting walk detection",
          state.confidence_score,
          config.dog_name,
        )

    elif state.current_state == WALK_STATE_RETURNING:
      # Dog returning from walk  # noqa: E114
      await self._handle_walk_return(config, state)  # noqa: E111

  async def _initiate_walk_detection(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
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
      # Send confirmation request  # noqa: E114
      await self._send_walk_confirmation_request(config, state)  # noqa: E111
    else:
      # Start walk automatically  # noqa: E114
      await self._start_automatic_walk(config, state)  # noqa: E111

  async def _send_walk_confirmation_request(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
  ) -> None:
    """Send walk confirmation request via notifications.

    Args:
        config: Door sensor configuration
        state: Detection state for this dog
    """
    if self._notification_manager is None:
      _LOGGER.warning(  # noqa: E111
        "No notification manager available for confirmation",
      )
      await self._start_automatic_walk(config, state)  # noqa: E111
      return  # noqa: E111

    title = f"🚶 Walk detected: {config.dog_name}"
    message = (
      f"Did {config.dog_name} just go for a walk? "
      f"Door activity detected with {state.confidence_score:.0%} confidence. "
      "No response switches to automatic tracking in 10 minutes."
    )

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
            "title": "✅ Start walk tracking",
          },
          {
            "action": f"deny_walk_{config.dog_id}",
            "title": "❌ False alarm",
          },
        ],
      },
      expires_in=timedelta(minutes=10),
    )

    # Store notification ID for response handling
    state.current_state = WALK_STATE_POTENTIAL

    # Schedule automatic timeout if no response
    async def confirmation_timeout() -> None:
      await asyncio.sleep(600)  # 10 minutes  # noqa: E111
      if state.current_state == WALK_STATE_POTENTIAL:  # noqa: E111
        _LOGGER.info(
          "Walk confirmation timeout for %s, starting automatically",
          config.dog_name,
        )
        await self._start_automatic_walk(config, state)

    self._track_background_task(
      asyncio.create_task(
        confirmation_timeout(),
        name="pawcontrol_confirmation_timeout",
      ),
    )

  async def _start_automatic_walk(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
  ) -> None:
    """Start automatic walk tracking.

    Args:
        config: Door sensor configuration
        state: Detection state for this dog
    """
    if self._walk_manager is None:
      _LOGGER.error("No walk manager available to start walk")  # noqa: E111
      state.current_state = WALK_STATE_IDLE  # noqa: E111
      return  # noqa: E111

    try:
      # Start walk via walk manager  # noqa: E114
      walk_id = await self._walk_manager.async_start_walk(  # noqa: E111
        dog_id=config.dog_id,
        walk_type="door_sensor",
        detection_confidence=state.confidence_score,
        door_sensor=config.entity_id,
      )

      state.active_walk_id = walk_id  # noqa: E111
      state.current_state = WALK_STATE_ACTIVE  # noqa: E111

      # Update stats  # noqa: E114
      self._detection_stats["total_detections"] += 1  # noqa: E111
      self._detection_stats["successful_walks"] += 1  # noqa: E111

      # Fire walk started event  # noqa: E114
      await async_fire_event(  # noqa: E111
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

      _LOGGER.info(  # noqa: E111
        "Started automatic walk for %s (walk_id: %s, confidence: %.2f)",
        config.dog_name,
        walk_id,
        state.confidence_score,
      )

      # Schedule automatic walk ending if enabled  # noqa: E114
      if config.auto_end_walks:  # noqa: E111

        async def auto_end_walk() -> None:
          await asyncio.sleep(config.maximum_walk_duration)  # noqa: E111
          if state.current_state == WALK_STATE_ACTIVE:  # noqa: E111
            await self._end_automatic_walk(config, state, "timeout")

        self._track_background_task(
          asyncio.create_task(
            auto_end_walk(),
            name="pawcontrol_auto_end_walk",
          ),
        )
    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to start automatic walk for %s: %s",
        config.dog_name,
        err,
      )
      state.current_state = WALK_STATE_IDLE  # noqa: E111

  async def _handle_walk_return(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
  ) -> None:
    """Handle dog returning from walk.

    Args:
        config: Door sensor configuration
        state: Detection state for this dog
    """
    if state.current_state != WALK_STATE_RETURNING or state.active_walk_id is None:
      return  # noqa: E111

    # Calculate walk duration
    if state.potential_walk_start:
      duration = (dt_util.now() - state.potential_walk_start).total_seconds()  # noqa: E111

      # Check if walk duration is reasonable  # noqa: E114
      if duration < config.minimum_walk_duration:  # noqa: E111
        _LOGGER.debug(
          "Walk duration too short for %s (%.1f minutes), not ending",
          config.dog_name,
          duration / 60,
        )
        state.current_state = WALK_STATE_ACTIVE
        return

    # End the walk
    await self._end_automatic_walk(config, state, "door_return")

  async def _end_automatic_walk(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
    reason: str,
  ) -> None:
    """End automatic walk tracking.

    Args:
        config: Door sensor configuration
        state: Detection state for this dog
        reason: Reason for ending walk
    """
    if state.active_walk_id is None or self._walk_manager is None:
      return  # noqa: E111

    try:
      # End walk via walk manager  # noqa: E114
      walk_data = await self._walk_manager.async_end_walk(  # noqa: E111
        dog_id=config.dog_id,
        notes=f"Automatically ended by door sensor detection ({reason})",
      )

      # Calculate final duration if available  # noqa: E114
      duration_minutes = 0.0  # noqa: E111
      if walk_data:  # noqa: E111
        duration_raw = walk_data.get("duration")
        if isinstance(duration_raw, int | float):
          duration_minutes = float(duration_raw) / 60.0  # noqa: E111

      # Reset state  # noqa: E114
      state.current_state = WALK_STATE_IDLE  # noqa: E111
      walk_id = state.active_walk_id  # noqa: E111
      state.active_walk_id = None  # noqa: E111
      state.potential_walk_start = None  # noqa: E111
      state.consecutive_opens = 0  # noqa: E111

      # Fire walk ended event  # noqa: E114
      await async_fire_event(  # noqa: E111
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

      _LOGGER.info(  # noqa: E111
        "Ended automatic walk for %s (reason: %s, duration: %.1f minutes)",
        config.dog_name,
        reason,
        duration_minutes,
      )

      # Send completion notification  # noqa: E114
      if self._notification_manager is not None:  # noqa: E111
        await self._notification_manager.async_send_notification(
          notification_type=NotificationType.SYSTEM_INFO,
          title=f"🏠 {config.dog_name} returned",
          message=f"{config.dog_name} finished their walk (duration: {duration_minutes:.0f} minutes)",  # noqa: E501
          dog_id=config.dog_id,
          priority=NotificationPriority.LOW,
        )

    except Exception as err:
      _LOGGER.error(  # noqa: E111
        "Failed to end automatic walk for %s: %s",
        config.dog_name,
        err,
      )

  async def _handle_walk_timeout(  # noqa: E111
    self,
    config: DoorSensorConfig,
    state: WalkDetectionState,
  ) -> None:
    """Handle walk detection timeout.

    Args:
        config: Door sensor configuration
        state: Detection state for this dog
    """
    # Only handle timeout if still in potential state
    if state.current_state != WALK_STATE_POTENTIAL:
      return  # noqa: E111

    _LOGGER.debug(
      "Walk detection timeout for %s (confidence: %.2f)",
      config.dog_name,
      state.confidence_score,
    )

    # Reset to idle state
    state.current_state = WALK_STATE_IDLE
    state.potential_walk_start = None

  async def _cleanup_expired_states(self) -> None:  # noqa: E111
    """Background task to clean up expired detection states."""
    while True:
      try:  # noqa: E111
        await asyncio.sleep(3600)  # Run every hour

        now = dt_util.now()
        cleaned = 0

        for state in self._detection_states.values():
          # Clean old state history  # noqa: E114
          old_count = len(state.state_history)  # noqa: E111
          cutoff = now - timedelta(hours=24)  # noqa: E111
          state.state_history = [  # noqa: E111
            (timestamp, event_state)
            for timestamp, event_state in state.state_history
            if timestamp > cutoff
          ]
          cleaned += old_count - len(state.state_history)  # noqa: E111

        if cleaned > 0:
          _LOGGER.debug(  # noqa: E111
            "Cleaned %d old state history entries",
            cleaned,
          )

      except asyncio.CancelledError:  # noqa: E111
        break
      except Exception as err:  # noqa: E111
        _LOGGER.error("Error in door sensor cleanup task: %s", err)

  async def async_handle_walk_confirmation(  # noqa: E111
    self,
    dog_id: str,
    confirmed: bool,
  ) -> None:
    """Handle walk confirmation response.

    Args:
        dog_id: Dog identifier
        confirmed: Whether walk was confirmed
    """
    config = self._sensor_configs.get(dog_id)
    state = self._detection_states.get(dog_id)

    if not config or not state or state.current_state != WALK_STATE_POTENTIAL:
      return  # noqa: E111

    if confirmed:
      await self._start_automatic_walk(config, state)  # noqa: E111
    else:
      # Mark as false positive  # noqa: E114
      self._detection_stats["false_positives"] += 1  # noqa: E111
      state.current_state = WALK_STATE_IDLE  # noqa: E111
      state.potential_walk_start = None  # noqa: E111

      _LOGGER.info("Walk detection denied for %s", config.dog_name)  # noqa: E111

  async def async_get_detection_status(self) -> DetectionStatus:  # noqa: E111
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
      config = self._sensor_configs[dog_id]  # noqa: E111

      if state.current_state != WALK_STATE_IDLE:  # noqa: E111
        status["active_detections"] += 1

      detection_entry: DetectionStatusEntry = {  # noqa: E111
        "dog_name": config.dog_name,
        "door_sensor": config.entity_id,
        "current_state": state.current_state,
        "confidence_score": state.confidence_score,
        "active_walk_id": state.active_walk_id,
        "last_door_state": state.last_door_state,
        "recent_activity": len(state.state_history),
      }
      status["detection_states"][dog_id] = detection_entry  # noqa: E111

    return status

  async def async_update_dog_configuration(  # noqa: E111
    self,
    dog_id: str,
    door_sensor: str | None,
    settings: DoorSensorSettingsInput | None = None,
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
      trimmed_sensor = door_sensor.strip()  # noqa: E111
      if not trimmed_sensor:  # noqa: E111
        removing = True
      elif not await self._validate_sensor_entity(trimmed_sensor):  # noqa: E111
        _LOGGER.warning("Invalid door sensor entity: %s", door_sensor)
        return False
    elif settings is None:
      removing = True  # noqa: E111

    changed = False

    persist_sensor: object = _UNSET
    persist_settings: object = _UNSET

    if removing:
      if dog_id in self._sensor_configs:  # noqa: E111
        del self._sensor_configs[dog_id]
        self._detection_states.pop(dog_id, None)
        changed = True
        _LOGGER.info("Removed door sensor config for dog %s", dog_id)
        persist_sensor = None
        persist_settings = None
      else:  # noqa: E111
        _LOGGER.debug(
          "Removal requested for unknown door sensor configuration: %s",
          dog_id,
        )
    else:
      config = self._sensor_configs.get(dog_id)  # noqa: E111
      if not config:  # noqa: E111
        _LOGGER.warning(
          "No door sensor configuration found for dog %s",
          dog_id,
        )
        return False

      if trimmed_sensor and config.entity_id != trimmed_sensor:  # noqa: E111
        config.entity_id = trimmed_sensor
        changed = True
        persist_sensor = trimmed_sensor

      if settings is not None:  # noqa: E111
        before = _settings_from_config(config)
        normalised = ensure_door_sensor_settings_config(
          settings,
          base=before,
        )
        if normalised != before:
          _apply_settings_to_config(config, normalised)  # noqa: E111
          changed = True  # noqa: E111
          persist_settings = normalised  # noqa: E111

      if changed:  # noqa: E111
        _LOGGER.info(
          "Updated door sensor config for %s",
          config.dog_name,
        )
      else:  # noqa: E111
        _LOGGER.debug(
          "Door sensor configuration for %s unchanged",
          config.dog_name,
        )

    if changed:
      await self._async_persist_door_sensor(  # noqa: E111
        dog_id,
        sensor=persist_sensor,
        settings=persist_settings,
      )
      await self._stop_sensor_monitoring()  # noqa: E111
      if self._sensor_configs:  # noqa: E111
        await self._start_sensor_monitoring()

    return True

  async def _stop_sensor_monitoring(self) -> None:  # noqa: E111
    """Stop monitoring door sensors."""
    # Cancel all listeners
    for listener in self._state_listeners:
      listener()  # noqa: E111
    self._state_listeners.clear()

    # Cancel cleanup task
    if self._cleanup_task and not self._cleanup_task.done():
      self._cleanup_task.cancel()  # noqa: E111
      self._cleanup_task = None  # noqa: E111

  async def async_cleanup(self) -> None:  # noqa: E111
    """Clean up door sensor manager."""
    await self._stop_sensor_monitoring()

    # Clean up any active walks
    for state in self._detection_states.values():
      if state.active_walk_id is not None and self._walk_manager is not None:  # noqa: E111
        try:
          await self._walk_manager.async_end_walk(  # noqa: E111
            dog_id=state.dog_id,
            notes="Walk ended due to system cleanup",
          )
        except Exception as err:
          _LOGGER.error("Error ending walk during cleanup: %s", err)  # noqa: E111

    self._sensor_configs.clear()
    self._detection_states.clear()

  def get_configured_sensors(self) -> dict[str, str]:  # noqa: E111
    """Get mapping of dog_id to door sensor entity_id.

    Returns:
        Dictionary mapping dog_id to sensor entity_id
    """
    return {dog_id: config.entity_id for dog_id, config in self._sensor_configs.items()}

  def is_dog_on_walk(self, dog_id: str) -> bool:  # noqa: E111
    """Check if dog is currently on a detected walk.

    Args:
        dog_id: Dog identifier

    Returns:
        True if dog is on a walk
    """
    state = self._detection_states.get(dog_id)
    return bool(
      state and state.current_state == WALK_STATE_ACTIVE and state.active_walk_id,
    )
