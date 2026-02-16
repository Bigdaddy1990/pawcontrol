"""Type definitions for the PawControl integration.

This module provides comprehensive type definitions, data structures, and validation
functions for the PawControl Home Assistant integration. It implements strict type safety,
performance-optimized validation, and comprehensive data modeling for all aspects
of dog care management.

The module is designed for Platinum-targeted quality with:
- Comprehensive type definitions using TypedDict and dataclasses
- Performance-optimized validation with frozenset lookups
- Extensive error handling and data validation
- Memory-efficient data structures using __slots__ where appropriate
- Complete documentation for all public APIs

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""  # noqa: E501

from asyncio import Task
from collections import deque
from collections.abc import (
  Awaitable,
  Callable,
  Iterable,
  Iterator,
  Mapping,
  MutableMapping,
  Sequence,
)
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import logging
from types import MappingProxyType
from typing import (
  TYPE_CHECKING,
  Any,
  ClassVar,
  Final,
  Literal,
  NotRequired,
  Required,
  TypedDict,
  TypeVar,
  cast,
)

from homeassistant.config_entries import ConfigEntry

from .const import (
  CONF_API_ENDPOINT,
  CONF_API_TOKEN,
  CONF_BREAKFAST_TIME,
  CONF_DAILY_FOOD_AMOUNT,
  CONF_DINNER_TIME,
  CONF_DOOR_SENSOR,
  CONF_DOOR_SENSOR_SETTINGS,
  CONF_EXTERNAL_INTEGRATIONS,
  CONF_FOOD_TYPE,
  CONF_GPS_SETTINGS,
  CONF_LUNCH_TIME,
  CONF_MEALS_PER_DAY,
  CONF_NOTIFICATIONS,
  CONF_QUIET_END,
  CONF_QUIET_HOURS,
  CONF_QUIET_START,
  CONF_REMINDER_REPEAT_MIN,
  DEFAULT_REMINDER_REPEAT_MIN,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
  from .service_guard import (  # noqa: E111
    ServiceGuardMetricsSnapshot,
    ServiceGuardResultHistory,
    ServiceGuardSummary,
  )

try:
  from homeassistant.util import dt as dt_util  # noqa: E111
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

  class _DateTimeModule:  # noqa: E111
    @staticmethod
    def utcnow() -> datetime:
      return datetime.now(UTC)  # noqa: E111

  dt_util = _DateTimeModule()  # noqa: E111

type JSONPrimitive = None | bool | int | float | str
"""Primitive JSON-compatible values."""

type JSONValue = JSONPrimitive | Sequence["JSONValue"] | Mapping[str, "JSONValue"]
"""Recursive JSON-compatible value used for diagnostics payloads."""

type JSONMapping = Mapping[str, JSONValue]
"""Mapping view for JSON-compatible payloads."""

type JSONMutableMapping = dict[str, JSONValue]
"""Mutable mapping containing JSON-compatible payloads."""

type JSONLikeMapping = JSONMapping | JSONMutableMapping
"""Union covering immutable and mutable JSON-compatible mappings."""

type ConfigFlowUserInput = Mapping[str, JSONValue] | JSONMutableMapping
"""Config flow user input payload accepted by setup and options steps."""

type FlowInputMapping = Mapping[str, JSONValue]
"""Typed mapping used for config and options flow payloads."""

type OptionsFlowUserInput = Mapping[str, JSONValue] | JSONMutableMapping
"""Options flow user input payload accepted by setup and options steps."""

type OptionsFlowInputMapping = Mapping[str, JSONValue]
"""Typed mapping used for options flow payloads."""

type JSONMutableSequence = list[JSONValue]
"""Mutable sequence containing JSON-compatible payload entries."""

type JSONDateValue = JSONValue | datetime
"""JSON-compatible value extended with ``datetime`` for legacy payloads."""

type JSONDateMapping = Mapping[str, JSONDateValue]
"""Mapping that tolerates ``datetime`` values during legacy hydration."""

type JSONDateMutableMapping = dict[str, JSONDateValue]
"""Mutable mapping that tolerates ``datetime`` values during legacy hydration."""

type VisitorModeSettingsPayload = JSONMutableMapping
"""Mutable payload persisted for visitor-mode configuration."""

from .utils import is_number  # noqa: E402

type ErrorContext = JSONMutableMapping
"""Structured context payload attached to :class:`PawControlError` instances."""


class DeviceAutomationMetadata(TypedDict):
  """Metadata payload for device automation entries."""  # noqa: E111

  secondary: bool  # noqa: E111


class DeviceActionPayload(TypedDict):
  """Payload returned for device action discovery."""  # noqa: E111

  device_id: str  # noqa: E111
  domain: str  # noqa: E111
  metadata: DeviceAutomationMetadata  # noqa: E111
  type: str  # noqa: E111


class DeviceConditionPayload(TypedDict):
  """Payload returned for device condition discovery."""  # noqa: E111

  condition: str  # noqa: E111
  device_id: str  # noqa: E111
  domain: str  # noqa: E111
  metadata: DeviceAutomationMetadata  # noqa: E111
  type: str  # noqa: E111
  entity_id: str  # noqa: E111


DeviceTriggerPayload = TypedDict(
  "DeviceTriggerPayload",
  {
    "platform": Required[str],
    "device_id": Required[str],
    "domain": Required[str],
    "metadata": Required[DeviceAutomationMetadata],
    "type": Required[str],
    "entity_id": Required[str],
    "from": NotRequired[str],
    "to": NotRequired[str],
  },
)
"""Payload returned for device trigger discovery."""


def ensure_json_mapping(
  data: Mapping[str, object] | JSONMutableMapping | None,
) -> JSONMutableMapping:
  """Return a JSON-compatible mutable mapping cloned from ``data``."""  # noqa: E111

  if not data:  # noqa: E111
    return {}

  return {str(key): cast(JSONValue, value) for key, value in data.items()}  # noqa: E111


def _coerce_iso_timestamp(value: Any) -> str | None:
  """Return an ISO-formatted timestamp string when possible."""  # noqa: E111

  if isinstance(value, datetime):  # noqa: E111
    return dt_util.as_utc(value).isoformat()
  if isinstance(value, str):  # noqa: E111
    text = value.strip()
    return text or None
  return None  # noqa: E111


def _coerce_float_value(value: Any) -> float | None:
  """Return a float when ``value`` is numeric."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return None
  if isinstance(value, float | int):  # noqa: E111
    return float(value)
  if isinstance(value, str):  # noqa: E111
    try:
      return float(value.strip())  # noqa: E111
    except ValueError:
      return None  # noqa: E111
  return None  # noqa: E111


class ErrorPayload(TypedDict):
  """Serialized representation of :class:`PawControlError` instances."""  # noqa: E111

  error_code: str  # noqa: E111
  message: str  # noqa: E111
  user_message: str  # noqa: E111
  severity: str  # noqa: E111
  category: str  # noqa: E111
  context: ErrorContext  # noqa: E111
  recovery_suggestions: list[str]  # noqa: E111
  technical_details: str | None  # noqa: E111
  timestamp: str  # noqa: E111
  exception_type: str  # noqa: E111


type GPXAttributeValue = JSONPrimitive
"""Primitive attribute value allowed in GPX attribute mappings."""

type GPXAttributeMap = Mapping[str, GPXAttributeValue]
"""Mapping for GPX/XML attribute rendering."""

type EntityAttributePayload[T: JSONValue] = dict[str, T]
"""Generic JSON-compatible attribute payload keyed by entity attribute name."""

type EntityAttributeMutableMapping = EntityAttributePayload[JSONValue]
"""Mutable attribute payload used when exporting Home Assistant entity state."""

type EntityAttributeDateMapping = Mapping[str, JSONDateValue]
"""Attribute mapping that allows ``datetime`` values before normalization."""

type EntityAttributeDateMutableMapping = dict[str, JSONDateValue]
"""Mutable attribute payload that allows ``datetime`` values before normalization."""

type NumberExtraAttributes = EntityAttributeMutableMapping
"""Extra state attributes exposed by PawControl number entities."""

type SelectExtraAttributes = EntityAttributeMutableMapping
"""Extra state attributes exposed by PawControl select entities."""

type PersonEntityAttributePayload = JSONMutableMapping
"""Mutable attribute payload stored alongside discovered person entities."""


class TextEntityExtraAttributes(TypedDict, total=False):
  """Extra attributes exposed by PawControl text entities."""  # noqa: E111

  dog_id: str  # noqa: E111
  dog_name: str  # noqa: E111
  text_type: str  # noqa: E111
  character_count: int  # noqa: E111
  last_updated: str | None  # noqa: E111
  last_updated_context_id: str | None  # noqa: E111
  last_updated_parent_id: str | None  # noqa: E111
  last_updated_user_id: str | None  # noqa: E111


class DogTextSnapshot(TypedDict, total=False):
  """Stored text values associated with a PawControl dog configuration."""  # noqa: E111

  notes: NotRequired[str]  # noqa: E111
  custom_label: NotRequired[str]  # noqa: E111
  walk_notes: NotRequired[str]  # noqa: E111
  current_walk_label: NotRequired[str]  # noqa: E111
  health_notes: NotRequired[str]  # noqa: E111
  medication_notes: NotRequired[str]  # noqa: E111
  vet_notes: NotRequired[str]  # noqa: E111
  grooming_notes: NotRequired[str]  # noqa: E111
  custom_message: NotRequired[str]  # noqa: E111
  emergency_contact: NotRequired[str]  # noqa: E111
  microchip: NotRequired[str]  # noqa: E111
  breeder_info: NotRequired[str]  # noqa: E111
  registration: NotRequired[str]  # noqa: E111
  insurance_info: NotRequired[str]  # noqa: E111
  allergies: NotRequired[str]  # noqa: E111
  training_notes: NotRequired[str]  # noqa: E111
  behavior_notes: NotRequired[str]  # noqa: E111
  location_description: NotRequired[str]  # noqa: E111


class DogTextMetadataEntry(TypedDict, total=False):
  """Metadata captured for an individual PawControl text value."""  # noqa: E111

  last_updated: str  # noqa: E111
  context_id: str | None  # noqa: E111
  parent_id: str | None  # noqa: E111
  user_id: str | None  # noqa: E111


class DogTextMetadataSnapshot(TypedDict, total=False):
  """Stored metadata associated with PawControl dog text values."""  # noqa: E111

  notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  custom_label: NotRequired[DogTextMetadataEntry]  # noqa: E111
  walk_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  current_walk_label: NotRequired[DogTextMetadataEntry]  # noqa: E111
  health_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  medication_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  vet_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  grooming_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  custom_message: NotRequired[DogTextMetadataEntry]  # noqa: E111
  emergency_contact: NotRequired[DogTextMetadataEntry]  # noqa: E111
  microchip: NotRequired[DogTextMetadataEntry]  # noqa: E111
  breeder_info: NotRequired[DogTextMetadataEntry]  # noqa: E111
  registration: NotRequired[DogTextMetadataEntry]  # noqa: E111
  insurance_info: NotRequired[DogTextMetadataEntry]  # noqa: E111
  allergies: NotRequired[DogTextMetadataEntry]  # noqa: E111
  training_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  behavior_notes: NotRequired[DogTextMetadataEntry]  # noqa: E111
  location_description: NotRequired[DogTextMetadataEntry]  # noqa: E111


class ButtonExtraAttributes(TypedDict, total=False):
  """Extra state attributes exposed by PawControl button entities."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111
  button_type: Required[str]  # noqa: E111
  last_pressed: str | None  # noqa: E111
  action_description: NotRequired[str]  # noqa: E111
  last_updated: NotRequired[str | None]  # noqa: E111


class BinarySensorAttributes(TypedDict, total=False):
  """Extra state attributes exposed by PawControl binary sensor entities."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111
  sensor_type: Required[str]  # noqa: E111
  last_update: Required[str]  # noqa: E111
  last_updated: NotRequired[str | None]  # noqa: E111
  dog_breed: NotRequired[str | None]  # noqa: E111
  dog_age: NotRequired[int | float | None]  # noqa: E111
  dog_size: NotRequired[str | None]  # noqa: E111
  dog_weight: NotRequired[float | None]  # noqa: E111
  status: NotRequired[str]  # noqa: E111
  system_health: NotRequired[str]  # noqa: E111
  enabled_modules: NotRequired[list[str]]  # noqa: E111
  attention_reasons: NotRequired[list[str]]  # noqa: E111
  urgency_level: NotRequired[str]  # noqa: E111
  recommended_actions: NotRequired[list[str]]  # noqa: E111
  recommended_action: NotRequired[str]  # noqa: E111
  visitor_mode_started: NotRequired[str | None]  # noqa: E111
  visitor_name: NotRequired[str | None]  # noqa: E111
  modified_notifications: NotRequired[bool]  # noqa: E111
  reduced_alerts: NotRequired[bool]  # noqa: E111
  last_feeding: NotRequired[str | None]  # noqa: E111
  last_feeding_hours: NotRequired[int | float | None]  # noqa: E111
  next_feeding_due: NotRequired[str | None]  # noqa: E111
  hunger_level: NotRequired[str]  # noqa: E111
  walk_start_time: NotRequired[str | None]  # noqa: E111
  walk_duration: NotRequired[int | float | None]  # noqa: E111
  walk_distance: NotRequired[int | float | None]  # noqa: E111
  estimated_remaining: NotRequired[int | None]  # noqa: E111
  last_walk: NotRequired[str | None]  # noqa: E111
  last_walk_hours: NotRequired[int | float | None]  # noqa: E111
  walks_today: NotRequired[int]  # noqa: E111
  garden_status: NotRequired[str]  # noqa: E111
  sessions_today: NotRequired[int]  # noqa: E111
  pending_confirmations: NotRequired[list[GardenConfirmationSnapshot]]  # noqa: E111
  pending_confirmation_count: NotRequired[int]  # noqa: E111
  current_zone: NotRequired[str]  # noqa: E111
  distance_from_home: NotRequired[float | None]  # noqa: E111
  last_seen: NotRequired[str | None]  # noqa: E111
  accuracy: NotRequired[float | int | None]  # noqa: E111
  health_alerts: NotRequired[HealthAlertList]  # noqa: E111
  health_status: NotRequired[str | None]  # noqa: E111
  alert_count: NotRequired[int]  # noqa: E111
  current_activity_level: NotRequired[str]  # noqa: E111
  concern_reason: NotRequired[str]  # noqa: E111
  portion_adjustment_factor: NotRequired[float | None]  # noqa: E111
  health_conditions: NotRequired[list[str]]  # noqa: E111
  emergency_type: NotRequired[str | None]  # noqa: E111
  portion_adjustment: NotRequired[int | float | str | None]  # noqa: E111
  activated_at: NotRequired[str | None]  # noqa: E111
  expires_at: NotRequired[str | None]  # noqa: E111


class ActivityLevelSensorAttributes(TypedDict, total=False):
  """Extra attributes reported by the activity level sensor."""  # noqa: E111

  walks_today: int  # noqa: E111
  total_walk_minutes_today: float  # noqa: E111
  last_walk_hours_ago: float | None  # noqa: E111
  health_activity_level: str | None  # noqa: E111
  activity_source: str  # noqa: E111


class CaloriesBurnedSensorAttributes(TypedDict, total=False):
  """Extra attributes reported by the calories burned sensor."""  # noqa: E111

  dog_weight_kg: float  # noqa: E111
  walk_minutes_today: float  # noqa: E111
  walk_distance_meters_today: float  # noqa: E111
  activity_level: str  # noqa: E111
  calories_per_minute: float  # noqa: E111
  calories_per_100m: float  # noqa: E111


class LastFeedingHoursAttributes(TypedDict, total=False):
  """Extra attributes reported by the last feeding hours sensor."""  # noqa: E111

  last_feeding_time: str | float | int | None  # noqa: E111
  feedings_today: int  # noqa: E111
  is_overdue: bool  # noqa: E111
  next_feeding_due: str | None  # noqa: E111


class TotalWalkDistanceAttributes(TypedDict, total=False):
  """Extra attributes reported by the total walk distance sensor."""  # noqa: E111

  total_walks: int  # noqa: E111
  total_distance_meters: float  # noqa: E111
  average_distance_per_walk_km: float  # noqa: E111
  distance_this_week_km: float  # noqa: E111
  distance_this_month_km: float  # noqa: E111


class WalksThisWeekAttributes(TypedDict, total=False):
  """Extra attributes reported by the walks this week sensor."""  # noqa: E111

  walks_today: int  # noqa: E111
  total_duration_this_week_minutes: float  # noqa: E111
  total_distance_this_week_meters: float  # noqa: E111
  average_walks_per_day: float  # noqa: E111
  days_this_week: int  # noqa: E111
  distance_this_week_km: float  # noqa: E111


class DateExtraAttributes(TypedDict, total=False):
  """Extra state attributes exposed by PawControl date entities."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111
  date_type: Required[str]  # noqa: E111
  days_from_today: NotRequired[int]  # noqa: E111
  is_past: NotRequired[bool]  # noqa: E111
  is_today: NotRequired[bool]  # noqa: E111
  is_future: NotRequired[bool]  # noqa: E111
  iso_string: NotRequired[str]  # noqa: E111
  age_days: NotRequired[int]  # noqa: E111
  age_years: NotRequired[float]  # noqa: E111
  age_months: NotRequired[float]  # noqa: E111


class TrackingModePreset(TypedDict, total=False):
  """Configuration preset applied when selecting a GPS tracking mode."""  # noqa: E111

  update_interval_seconds: int  # noqa: E111
  auto_start_walk: bool  # noqa: E111
  track_route: bool  # noqa: E111
  route_smoothing: bool  # noqa: E111


class LocationAccuracyConfig(TypedDict, total=False):
  """Configuration payload applied when selecting a GPS accuracy profile."""  # noqa: E111

  gps_accuracy_threshold: float  # noqa: E111
  min_distance_for_point: float  # noqa: E111
  route_smoothing: bool  # noqa: E111


class DogSizeInfo(TypedDict, total=False):
  """Additional metadata exposed by the dog size select entity."""  # noqa: E111

  weight_range: str  # noqa: E111
  exercise_needs: str  # noqa: E111
  food_portion: str  # noqa: E111


class PerformanceModeInfo(TypedDict, total=False):
  """Metadata describing a performance mode option."""  # noqa: E111

  description: str  # noqa: E111
  update_interval: str  # noqa: E111
  battery_impact: str  # noqa: E111


class FoodTypeInfo(TypedDict, total=False):
  """Metadata describing a feeding option exposed by selects."""  # noqa: E111

  calories_per_gram: float  # noqa: E111
  moisture_content: str  # noqa: E111
  storage: str  # noqa: E111
  shelf_life: str  # noqa: E111


class WalkModeInfo(TypedDict, total=False):
  """Descriptive metadata for walk mode select options."""  # noqa: E111

  description: str  # noqa: E111
  gps_required: bool  # noqa: E111
  accuracy: str  # noqa: E111


class GPSSourceInfo(TypedDict, total=False):
  """Metadata describing a configured GPS telemetry source."""  # noqa: E111

  accuracy: str  # noqa: E111
  update_frequency: str  # noqa: E111
  battery_usage: str  # noqa: E111


class GroomingTypeInfo(TypedDict, total=False):
  """Metadata describing a grooming routine selection."""  # noqa: E111

  frequency: str  # noqa: E111
  duration: str  # noqa: E111
  difficulty: str  # noqa: E111


TrackingModeKey = Literal["continuous", "interval", "on_demand", "battery_saver"]
LocationAccuracyKey = Literal["low", "balanced", "high", "best"]
DogSizeKey = Literal["toy", "small", "medium", "large", "giant"]
PerformanceModeKey = Literal["minimal", "balanced", "full"]
FoodTypeKey = Literal["dry_food", "wet_food", "barf", "home_cooked", "mixed"]
WalkModeKey = Literal["automatic", "manual", "hybrid"]
GPSSourceKey = Literal[
  "manual",
  "device_tracker",
  "person_entity",
  "gps_logger",
  "ble_beacon",
  "smartphone",
  "tractive",
  "webhook",
  "mqtt",
]
GroomingTypeKey = Literal["bath", "brush", "nails", "teeth", "trim", "full_grooming"]
FeedingScheduleKey = Literal["flexible", "strict", "custom"]
NotificationPriorityKey = Literal["low", "normal", "high", "urgent"]
WeatherConditionKey = Literal[
  "any",
  "sunny",
  "cloudy",
  "light_rain",
  "no_rain",
  "warm",
  "cool",
]
ActivityLevelKey = Literal["very_low", "low", "normal", "high", "very_high"]
HealthStatusKey = Literal[
  "excellent",
  "very_good",
  "good",
  "normal",
  "unwell",
  "sick",
]
MoodKey = Literal["happy", "neutral", "sad", "angry", "anxious", "tired"]
MealTypeKey = Literal["breakfast", "lunch", "dinner", "snack"]

type MetadataPayload[T: JSONValue] = dict[str, T]
"""Generic JSON-compatible mapping used for diagnostics metadata sections."""

type MaintenanceMetadataPayload = MetadataPayload[JSONValue]
"""JSON-compatible metadata payload captured during maintenance routines."""

type ServiceDetailsPayload = MaintenanceMetadataPayload
"""Normalised service details payload stored alongside execution results."""

type StorageNamespaceKey = Literal[
  "walks",
  "feedings",
  "health",
  "routes",
  "statistics",
]
"""Supported storage namespaces handled by :class:`PawControlDataStorage`."""

type StorageNamespacePayload = dict[str, JSONValue]
"""Serialized payload persisted for a single storage namespace."""

type StorageNamespaceState = dict[StorageNamespaceKey, StorageNamespacePayload]
"""Combined storage state keyed by namespace identifier."""

type StorageCacheValue = StorageNamespaceState | StorageNamespacePayload | None
"""Union of cache payloads tracked by :class:`PawControlDataStorage`."""

type HealthHistoryEntry = JSONMutableMapping
"""Health history entry stored in runtime storage queues."""

type HealthNamespaceMutable = dict[str, list[HealthHistoryEntry] | JSONValue]
"""Mutable mapping of per-dog health history payloads."""

type WalkHistoryEntry = JSONMutableMapping
"""Walk history entry captured during runtime processing."""

type WalkNamespaceValue = JSONValue | list[WalkHistoryEntry] | None
"""Allowed value types persisted inside a walk namespace entry."""

type WalkNamespaceMutableEntry = dict[str, WalkNamespaceValue]
"""Mutable walk namespace payload for a single dog identifier."""

type WalkNamespaceMutable = dict[str, WalkNamespaceMutableEntry | JSONValue]
"""Runtime mapping of walk namespace entries keyed by dog identifier."""

type WalkStartPayload = Mapping[str, JSONValue]
"""Structured payload accepted when starting an immediate walk."""

# OPTIMIZE: Resolve circular imports with proper conditional imports
if TYPE_CHECKING:
  from .coordinator import PawControlCoordinator  # noqa: E111
  from .data_manager import PawControlDataManager  # noqa: E111
  from .device_api import PawControlDeviceClient  # noqa: E111
  from .door_sensor_manager import DoorSensorManager  # noqa: E111
  from .entity_factory import EntityFactory  # noqa: E111
  from .feeding_manager import FeedingComplianceResult, FeedingManager  # noqa: E111
  from .garden_manager import GardenManager  # noqa: E111
  from .geofencing import PawControlGeofencing  # noqa: E111
  from .gps_manager import GPSGeofenceManager  # noqa: E111
  from .helper_manager import PawControlHelperManager  # noqa: E111
  from .notifications import PawControlNotificationManager  # noqa: E111
  from .script_manager import PawControlScriptManager  # noqa: E111
  from .walk_manager import WalkManager  # noqa: E111
  from .weather_manager import WeatherHealthManager  # noqa: E111

# OPTIMIZE: Use literal constants for performance - frozensets provide O(1) lookups
# and are immutable, preventing accidental modification while ensuring fast validation

VALID_MEAL_TYPES: Final[frozenset[str]] = frozenset(
  ["breakfast", "lunch", "dinner", "snack"],
)
"""Valid meal types for feeding tracking.

This frozenset defines the acceptable meal types that can be recorded in the system.
Using frozenset provides O(1) lookup performance for validation while preventing
accidental modification of the valid values.
"""

VALID_FOOD_TYPES: Final[frozenset[str]] = frozenset(
  ["dry_food", "wet_food", "barf", "home_cooked", "mixed"],
)
"""Valid food types for feeding management.

Defines the types of food that can be tracked in feeding records. This includes
commercial food types and home-prepared options for comprehensive diet tracking.
"""

VALID_DOG_SIZES: Final[frozenset[str]] = frozenset(
  ["toy", "small", "medium", "large", "giant"],
)
"""Valid dog size categories for breed classification.

Size categories are used throughout the system for portion calculation, exercise
recommendations, and health monitoring. These align with standard veterinary
size classifications.
"""

VALID_HEALTH_STATUS: Final[frozenset[str]] = frozenset(
  ["excellent", "very_good", "good", "normal", "unwell", "sick"],
)
"""Valid health status levels for health monitoring.

These status levels provide a standardized way to track overall dog health,
from excellent condition to requiring medical attention.
"""

VALID_MOOD_OPTIONS: Final[frozenset[str]] = frozenset(
  ["happy", "neutral", "content", "normal", "sad", "angry", "anxious", "tired"],
)
"""Valid mood states for behavioral tracking.

Mood tracking helps identify patterns in behavior and potential health issues
that may affect a dog's emotional well-being.
"""

VALID_ACTIVITY_LEVELS: Final[frozenset[str]] = frozenset(
  ["very_low", "low", "normal", "high", "very_high"],
)
"""Valid activity levels for exercise and health monitoring.

Activity levels are used for calculating appropriate exercise needs, portion sizes,
and overall health assessments based on a dog's typical energy expenditure.
"""

VALID_GEOFENCE_TYPES: Final[frozenset[str]] = frozenset(
  ["safe_zone", "restricted_area", "point_of_interest"],
)
"""Valid geofence zone types for GPS tracking.

Different zone types trigger different behaviors in the system, from safety
notifications to activity logging when dogs enter or leave specific areas.
"""

VALID_GPS_SOURCES: Final[frozenset[str]] = frozenset(
  [
    "manual",
    "device_tracker",
    "person_entity",
    "smartphone",
    "tractive",
    "webhook",
    "mqtt",
  ],
)
"""Valid GPS data sources for location tracking.

Supports multiple GPS input methods to accommodate different hardware setups
and integration scenarios with various tracking devices and services.
"""

type NotificationPriority = Literal["low", "normal", "high", "urgent"]
"""Supported notification priority values.

The alias is reused across the helper and notification managers so every queue,
options flow, and service call enforces the Home Assistant priority contract
without falling back to loosely typed strings.
"""

VALID_NOTIFICATION_PRIORITIES: Final[frozenset[NotificationPriority]] = frozenset(
  ["low", "normal", "high", "urgent"],
)
"""Valid notification priority levels for alert management.

Priority levels determine notification delivery methods, timing, and persistence
to ensure important alerts are appropriately escalated.
"""

VALID_NOTIFICATION_CHANNELS: Final[frozenset[str]] = frozenset(
  [
    "mobile",
    "persistent",
    "email",
    "sms",
    "webhook",
    "tts",
    "media_player",
    "slack",
    "discord",
  ],
)
"""Valid notification delivery channels for flexible alert routing.

Multiple channel support ensures notifications can reach users through their
preferred communication methods and backup channels for critical alerts.
"""

# Door sensor configuration defaults shared across the integration.
DEFAULT_WALK_DETECTION_TIMEOUT: Final[int] = 300  # 5 minutes
DEFAULT_MINIMUM_WALK_DURATION: Final[int] = 180  # 3 minutes
DEFAULT_MAXIMUM_WALK_DURATION: Final[int] = 7200  # 2 hours
DEFAULT_DOOR_CLOSED_DELAY: Final[int] = 60  # 1 minute
DEFAULT_CONFIDENCE_THRESHOLD: Final[float] = 0.7


@dataclass(slots=True, frozen=True)
class DoorSensorSettingsConfig:
  """Normalised configuration values applied to door sensor tracking."""  # noqa: E111

  walk_detection_timeout: int = DEFAULT_WALK_DETECTION_TIMEOUT  # noqa: E111
  minimum_walk_duration: int = DEFAULT_MINIMUM_WALK_DURATION  # noqa: E111
  maximum_walk_duration: int = DEFAULT_MAXIMUM_WALK_DURATION  # noqa: E111
  door_closed_delay: int = DEFAULT_DOOR_CLOSED_DELAY  # noqa: E111
  require_confirmation: bool = True  # noqa: E111
  auto_end_walks: bool = True  # noqa: E111
  confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD  # noqa: E111


DEFAULT_DOOR_SENSOR_SETTINGS = DoorSensorSettingsConfig()

type DoorSensorOverrideScalar = bool | int | float | str | None
"""Scalar values accepted when overriding door sensor settings."""

type DoorSensorSettingsMapping = Mapping[str, DoorSensorOverrideScalar]
"""Mapping of setting names to override scalars."""


class DoorSensorSettingsOverrides(TypedDict, total=False):
  """User-provided overrides for :class:`DoorSensorSettingsConfig`."""  # noqa: E111

  timeout: DoorSensorOverrideScalar  # noqa: E111
  walk_detection_timeout: DoorSensorOverrideScalar  # noqa: E111
  walk_timeout: DoorSensorOverrideScalar  # noqa: E111
  minimum_walk_duration: DoorSensorOverrideScalar  # noqa: E111
  min_walk_duration: DoorSensorOverrideScalar  # noqa: E111
  minimum_duration: DoorSensorOverrideScalar  # noqa: E111
  min_duration: DoorSensorOverrideScalar  # noqa: E111
  maximum_walk_duration: DoorSensorOverrideScalar  # noqa: E111
  max_walk_duration: DoorSensorOverrideScalar  # noqa: E111
  maximum_duration: DoorSensorOverrideScalar  # noqa: E111
  max_duration: DoorSensorOverrideScalar  # noqa: E111
  door_closed_delay: DoorSensorOverrideScalar  # noqa: E111
  door_closed_timeout: DoorSensorOverrideScalar  # noqa: E111
  close_delay: DoorSensorOverrideScalar  # noqa: E111
  close_timeout: DoorSensorOverrideScalar  # noqa: E111
  require_confirmation: DoorSensorOverrideScalar  # noqa: E111
  confirmation_required: DoorSensorOverrideScalar  # noqa: E111
  auto_end_walks: DoorSensorOverrideScalar  # noqa: E111
  auto_end_walk: DoorSensorOverrideScalar  # noqa: E111
  auto_close: DoorSensorOverrideScalar  # noqa: E111
  confidence_threshold: DoorSensorOverrideScalar  # noqa: E111
  confidence: DoorSensorOverrideScalar  # noqa: E111
  threshold: DoorSensorOverrideScalar  # noqa: E111


class DoorSensorSettingsPayload(TypedDict):
  """Serialised payload representing normalised door sensor settings."""  # noqa: E111

  walk_detection_timeout: int  # noqa: E111
  minimum_walk_duration: int  # noqa: E111
  maximum_walk_duration: int  # noqa: E111
  door_closed_delay: int  # noqa: E111
  require_confirmation: bool  # noqa: E111
  auto_end_walks: bool  # noqa: E111
  confidence_threshold: float  # noqa: E111


type DoorSensorSettingsInput = (
  DoorSensorSettingsConfig | DoorSensorSettingsOverrides | DoorSensorSettingsMapping
)
"""Accepted inputs when normalising door sensor settings."""

# Type aliases for improved code readability and maintainability
DogId = str
"""Type alias for dog identifier strings.

Used throughout the codebase to clearly identify parameters and return values
that represent dog identifiers, improving code readability and type safety.
"""

ConfigEntryId = str
"""Type alias for Home Assistant config entry identifiers.

Represents unique identifiers for integration configuration entries within
the Home Assistant configuration system.
"""

EntityId = str
"""Type alias for Home Assistant entity identifiers.

Standard entity ID format following Home Assistant conventions for entity
identification across the platform.
"""


class DietCompatibilityIssue(TypedDict):
  """Structured description of diet compatibility conflicts or warnings."""  # noqa: E111

  type: str  # noqa: E111
  diets: list[str]  # noqa: E111
  message: str  # noqa: E111


class DietValidationResult(TypedDict):
  """Result payload returned by diet validation helpers."""  # noqa: E111

  valid: bool  # noqa: E111
  conflicts: list[DietCompatibilityIssue]  # noqa: E111
  warnings: list[DietCompatibilityIssue]  # noqa: E111
  recommended_vet_consultation: bool  # noqa: E111
  total_diets: int  # noqa: E111


class FeedingGoalSettings(TypedDict, total=False):
  """Targeted feeding goals that influence portion adjustments."""  # noqa: E111

  weight_goal: Literal["maintain", "lose", "gain"]  # noqa: E111
  weight_loss_rate: Literal["aggressive", "moderate", "gradual"]  # noqa: E111


class HealthMetricsOverride(TypedDict, total=False):
  """Runtime override values when building :class:`HealthMetrics`."""  # noqa: E111

  weight: float | int  # noqa: E111
  ideal_weight: float | int  # noqa: E111
  age_months: int  # noqa: E111
  health_conditions: list[str]  # noqa: E111


class FeedingHistoryEvent(TypedDict, total=False):
  """Normalised feeding event used for history analysis."""  # noqa: E111

  time: datetime  # noqa: E111
  amount: float | int  # noqa: E111
  meal_type: str | None  # noqa: E111


FeedingHistoryStatus = Literal[
  "no_data",
  "insufficient_data",
  "no_recent_data",
  "no_health_data",
  "good",
  "overfeeding",
  "slight_overfeeding",
  "underfeeding",
  "slight_underfeeding",
]
"""Status values returned by ``analyze_feeding_history``."""


class FeedingHealthContext(TypedDict, total=False):
  """Contextual health information attached to feeding analysis."""  # noqa: E111

  weight_goal: str | None  # noqa: E111
  body_condition_score: float | int | None  # noqa: E111
  life_stage: str | None  # noqa: E111
  activity_level: str | None  # noqa: E111
  health_conditions: list[str] | None  # noqa: E111
  special_diet: list[str] | None  # noqa: E111


class FeedingHistoryAnalysis(TypedDict, total=False):
  """Structured payload returned by feeding history analysis."""  # noqa: E111

  status: FeedingHistoryStatus  # noqa: E111
  recommendation: str  # noqa: E111
  message: str  # noqa: E111
  avg_daily_calories: float  # noqa: E111
  target_calories: float  # noqa: E111
  calorie_variance_percent: float  # noqa: E111
  avg_daily_meals: float  # noqa: E111
  recommendations: list[str]  # noqa: E111
  analysis_period_days: int  # noqa: E111
  health_context: FeedingHealthContext  # noqa: E111


class HealthFeedingInsights(TypedDict, total=False):
  """Feeding-specific recommendations appended to health reports."""  # noqa: E111

  daily_calorie_target: float | None  # noqa: E111
  portion_adjustment_factor: float  # noqa: E111
  recommended_meals_per_day: int  # noqa: E111
  food_type_recommendation: str | None  # noqa: E111


HealthReportStatus = Literal[
  "excellent",
  "good",
  "needs_attention",
  "concerning",
  "managing_condition",
]
"""Overall status levels surfaced by comprehensive health reports."""


class HealthReport(TypedDict, total=False):
  """Comprehensive health report exported by the feeding manager."""  # noqa: E111

  timestamp: str  # noqa: E111
  overall_status: HealthReportStatus  # noqa: E111
  recommendations: list[str]  # noqa: E111
  health_score: int  # noqa: E111
  areas_of_concern: list[str]  # noqa: E111
  positive_indicators: list[str]  # noqa: E111
  feeding_insights: HealthFeedingInsights  # noqa: E111
  recent_feeding_performance: FeedingHistoryAnalysis  # noqa: E111


class DogVaccinationRecord(TypedDict, total=False):
  """Details about a specific vaccination."""  # noqa: E111

  date: str | None  # noqa: E111
  next_due: str | None  # noqa: E111


class DogMedicationEntry(TypedDict, total=False):
  """Medication reminder entry captured during configuration."""  # noqa: E111

  name: str  # noqa: E111
  dosage: str  # noqa: E111
  frequency: str  # noqa: E111
  time: str  # noqa: E111
  notes: str  # noqa: E111
  with_meals: bool  # noqa: E111


class DogHealthConfig(TypedDict, total=False):
  """Extended health configuration captured during setup."""  # noqa: E111

  vet_name: str  # noqa: E111
  vet_phone: str  # noqa: E111
  last_vet_visit: str | None  # noqa: E111
  next_checkup: str | None  # noqa: E111
  weight_tracking: bool  # noqa: E111
  ideal_weight: float | None  # noqa: E111
  body_condition_score: int  # noqa: E111
  activity_level: str  # noqa: E111
  weight_goal: str  # noqa: E111
  spayed_neutered: bool  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  special_diet_requirements: list[str]  # noqa: E111
  vaccinations: dict[str, DogVaccinationRecord]  # noqa: E111
  medications: list[DogMedicationEntry]  # noqa: E111


class DogModulesConfig(TypedDict, total=False):
  """Per-dog module enablement settings."""  # noqa: E111

  feeding: bool  # noqa: E111
  walk: bool  # noqa: E111
  health: bool  # noqa: E111
  gps: bool  # noqa: E111
  garden: bool  # noqa: E111
  notifications: bool  # noqa: E111
  dashboard: bool  # noqa: E111
  visitor: bool  # noqa: E111
  grooming: bool  # noqa: E111
  medication: bool  # noqa: E111
  training: bool  # noqa: E111
  weather: bool  # noqa: E111


class HealthMedicationReminder(TypedDict, total=False):
  """Reminder entry describing an active medication schedule."""  # noqa: E111

  name: str  # noqa: E111
  dosage: str | None  # noqa: E111
  frequency: str | None  # noqa: E111
  next_dose: str | None  # noqa: E111
  notes: str | None  # noqa: E111
  with_meals: bool | None  # noqa: E111


class HealthAlertEntry(TypedDict, total=False):
  """Structured alert surfaced by the health enhancement routines."""  # noqa: E111

  type: str  # noqa: E111
  message: str  # noqa: E111
  severity: Literal["low", "medium", "high", "critical"]  # noqa: E111
  action_required: bool  # noqa: E111
  details: JSONLikeMapping | None  # noqa: E111


class HealthUpcomingCareEntry(TypedDict, total=False):
  """Scheduled or due-soon care entry tracked for a dog."""  # noqa: E111

  type: str  # noqa: E111
  message: str  # noqa: E111
  due_date: str | None  # noqa: E111
  priority: Literal["low", "medium", "high"]  # noqa: E111
  details: str | JSONLikeMapping | None  # noqa: E111


type HealthAlertList = list[HealthAlertEntry]
type HealthUpcomingCareQueue = list[HealthUpcomingCareEntry]
type HealthMedicationQueue = list[HealthMedicationReminder]


class HealthStatusSnapshot(TypedDict, total=False):
  """Current health status summary exported to diagnostics consumers."""  # noqa: E111

  overall_score: int  # noqa: E111
  priority_alerts: HealthAlertList  # noqa: E111
  upcoming_care: HealthUpcomingCareQueue  # noqa: E111
  recommendations: list[str]  # noqa: E111
  last_updated: str  # noqa: E111


class HealthAppointmentRecommendation(TypedDict):
  """Recommendation for the next veterinary appointment."""  # noqa: E111

  next_appointment_date: str  # noqa: E111
  appointment_type: str  # noqa: E111
  reason: str  # noqa: E111
  urgency: Literal["low", "normal", "high"]  # noqa: E111
  days_until: int  # noqa: E111


ModuleToggleKey = Literal[
  "feeding",
  "walk",
  "health",
  "gps",
  "garden",
  "notifications",
  "dashboard",
  "visitor",
  "grooming",
  "medication",
  "training",
]

ModuleToggleFlowFlag = Literal[
  "enable_feeding",
  "enable_walk",
  "enable_health",
  "enable_gps",
  "enable_garden",
  "enable_notifications",
  "enable_dashboard",
  "enable_visitor",
  "enable_grooming",
  "enable_medication",
  "enable_training",
]

type ModuleToggleMapping = Mapping[ModuleToggleKey, JSONValue]
"""Mapping of module toggle keys to JSON-compatible values."""

MODULE_TOGGLE_KEYS: Final[tuple[ModuleToggleKey, ...]] = (
  "feeding",
  "walk",
  "health",
  "gps",
  "garden",
  "notifications",
  "dashboard",
  "visitor",
  "grooming",
  "medication",
  "training",
)

MODULE_TOGGLE_FLOW_FLAGS: Final[
  tuple[tuple[ModuleToggleFlowFlag, ModuleToggleKey], ...]
] = (
  ("enable_feeding", "feeding"),
  ("enable_walk", "walk"),
  ("enable_health", "health"),
  ("enable_gps", "gps"),
  ("enable_garden", "garden"),
  ("enable_notifications", "notifications"),
  ("enable_dashboard", "dashboard"),
  ("enable_visitor", "visitor"),
  ("enable_grooming", "grooming"),
  ("enable_medication", "medication"),
  ("enable_training", "training"),
)

MODULE_TOGGLE_FLAG_BY_KEY: Final[dict[ModuleToggleKey, ModuleToggleFlowFlag]] = {
  module: flag for flag, module in MODULE_TOGGLE_FLOW_FLAGS
}


class DogModuleSelectionInput(TypedDict):
  """Raw module toggle payload collected during per-dog setup."""  # noqa: E111

  enable_feeding: NotRequired[bool]  # noqa: E111
  enable_walk: NotRequired[bool]  # noqa: E111
  enable_health: NotRequired[bool]  # noqa: E111
  enable_gps: NotRequired[bool]  # noqa: E111
  enable_garden: NotRequired[bool]  # noqa: E111
  enable_notifications: NotRequired[bool]  # noqa: E111
  enable_dashboard: NotRequired[bool]  # noqa: E111
  enable_visitor: NotRequired[bool]  # noqa: E111
  enable_grooming: NotRequired[bool]  # noqa: E111
  enable_medication: NotRequired[bool]  # noqa: E111
  enable_training: NotRequired[bool]  # noqa: E111


FeedingConfigKey = Literal[
  "meals_per_day",
  "daily_food_amount",
  "portion_size",
  "food_type",
  "feeding_schedule",
  "enable_reminders",
  "reminder_minutes_before",
  "breakfast_time",
  "lunch_time",
  "dinner_time",
  "snack_times",
]

DEFAULT_FEEDING_SCHEDULE: Final[tuple[str, ...]] = (
  "10:00:00",
  "15:00:00",
  "20:00:00",
)


@dataclass(slots=True)
class DogModulesProjection:
  """Expose both typed and plain module toggle representations."""  # noqa: E111

  config: DogModulesConfig  # noqa: E111
  mapping: dict[str, bool]  # noqa: E111

  def as_config(self) -> DogModulesConfig:  # noqa: E111
    """Return a ``DogModulesConfig`` copy suitable for storage."""

    return cast(DogModulesConfig, dict(self.config))

  def as_mapping(self) -> dict[str, bool]:  # noqa: E111
    """Return a plain mapping for platform factories."""

    return dict(self.mapping)


def _record_bool_coercion(
  value: Any,
  *,
  default: bool,
  result: bool,
  reason: str,
) -> None:
  """Record bool coercion telemetry for diagnostics consumers."""  # noqa: E111

  try:  # noqa: E111
    from .telemetry import record_bool_coercion_event
  except (  # noqa: E111
    Exception
  ):  # pragma: no cover - telemetry import guarded for safety
    return

  try:  # noqa: E111
    record_bool_coercion_event(
      value=value,
      default=default,
      result=result,
      reason=reason,
    )
  except (  # noqa: E111
    Exception
  ):  # pragma: no cover - telemetry failures must not break coercion
    return


class BoolCoercionSample(TypedDict):
  """Snapshot of an individual boolean coercion event."""  # noqa: E111

  value_type: str  # noqa: E111
  value_repr: str  # noqa: E111
  default: bool  # noqa: E111
  result: bool  # noqa: E111
  reason: str  # noqa: E111


class BoolCoercionMetrics(TypedDict, total=False):
  """Aggregated metrics describing bool coercion behaviour."""  # noqa: E111

  total: int  # noqa: E111
  defaulted: int  # noqa: E111
  fallback: int  # noqa: E111
  reset_count: int  # noqa: E111
  type_counts: dict[str, int]  # noqa: E111
  reason_counts: dict[str, int]  # noqa: E111
  samples: list[BoolCoercionSample]  # noqa: E111
  first_seen: str | None  # noqa: E111
  last_seen: str | None  # noqa: E111
  active_window_seconds: float | None  # noqa: E111
  last_reset: str | None  # noqa: E111
  last_reason: str | None  # noqa: E111
  last_value_type: str | None  # noqa: E111
  last_value_repr: str | None  # noqa: E111
  last_result: bool | None  # noqa: E111
  last_default: bool | None  # noqa: E111


class BoolCoercionSummary(TypedDict):
  """Condensed snapshot for coordinator observability exports."""  # noqa: E111

  recorded: bool  # noqa: E111
  total: int  # noqa: E111
  defaulted: int  # noqa: E111
  fallback: int  # noqa: E111
  reset_count: int  # noqa: E111
  first_seen: str | None  # noqa: E111
  last_seen: str | None  # noqa: E111
  last_reset: str | None  # noqa: E111
  active_window_seconds: float | None  # noqa: E111
  last_reason: str | None  # noqa: E111
  last_value_type: str | None  # noqa: E111
  last_value_repr: str | None  # noqa: E111
  last_result: bool | None  # noqa: E111
  last_default: bool | None  # noqa: E111
  reason_counts: dict[str, int]  # noqa: E111
  type_counts: dict[str, int]  # noqa: E111
  samples: list[BoolCoercionSample]  # noqa: E111


class BoolCoercionDiagnosticsPayload(TypedDict, total=False):
  """Diagnostics payload combining bool coercion summary and metrics."""  # noqa: E111

  recorded: bool  # noqa: E111
  summary: BoolCoercionSummary  # noqa: E111
  metrics: BoolCoercionMetrics  # noqa: E111


_TRUTHY_BOOL_STRINGS: Final[frozenset[str]] = frozenset(
  {"1", "true", "yes", "y", "on", "enabled"},
)
_FALSY_BOOL_STRINGS: Final[frozenset[str]] = frozenset(
  {"0", "false", "no", "n", "off", "disabled"},
)


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
  """Return a boolean flag while tolerating common string/int representations."""  # noqa: E111

  if value is None:  # noqa: E111
    _record_bool_coercion(
      value,
      default=default,
      result=default,
      reason="none",
    )
    return default
  if isinstance(value, bool):  # noqa: E111
    result = value
    _record_bool_coercion(
      value,
      default=default,
      result=result,
      reason="native_true" if result else "native_false",
    )
    return result
  if isinstance(value, int | float):  # noqa: E111
    result = value != 0
    _record_bool_coercion(
      value,
      default=default,
      result=result,
      reason="numeric_nonzero" if result else "numeric_zero",
    )
    return result
  if isinstance(value, str):  # noqa: E111
    text = value.strip().lower()
    if not text:
      _record_bool_coercion(  # noqa: E111
        value,
        default=default,
        result=default,
        reason="blank_string",
      )
      return default  # noqa: E111
    if text in _TRUTHY_BOOL_STRINGS:
      _record_bool_coercion(  # noqa: E111
        value,
        default=default,
        result=True,
        reason="truthy_string",
      )
      return True  # noqa: E111
    if text in _FALSY_BOOL_STRINGS:
      _record_bool_coercion(  # noqa: E111
        value,
        default=default,
        result=False,
        reason="falsy_string",
      )
      return False  # noqa: E111

    result = False
    _record_bool_coercion(
      value,
      default=default,
      result=result,
      reason="unknown_string",
    )
    return result

  result = bool(value)  # noqa: E111
  _record_bool_coercion(  # noqa: E111
    value,
    default=default,
    result=result,
    reason="fallback",
  )
  return result  # noqa: E111


def _coerce_int(value: Any, *, default: int) -> int:
  """Return an integer, falling back to ``default`` when conversion fails."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return 1 if value else default
  if isinstance(value, int):  # noqa: E111
    return value
  if isinstance(value, float):  # noqa: E111
    return int(value)
  if isinstance(value, str):  # noqa: E111
    try:
      return int(value.strip())  # noqa: E111
    except ValueError:
      return default  # noqa: E111
  return default  # noqa: E111


def _coerce_float(value: Any, *, default: float) -> float:
  """Return a float, tolerating numeric strings and integers."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    return 1.0 if value else default
  if isinstance(value, float):  # noqa: E111
    return value
  if isinstance(value, int):  # noqa: E111
    return float(value)
  if isinstance(value, str):  # noqa: E111
    try:
      return float(value.strip())  # noqa: E111
    except ValueError:
      return default  # noqa: E111
  return default  # noqa: E111


def _coerce_str(value: Any, *, default: str) -> str:
  """Return a trimmed string value or the provided default."""  # noqa: E111

  if isinstance(value, str):  # noqa: E111
    text = value.strip()
    return text or default
  return default  # noqa: E111


PerformanceMode = Literal["minimal", "balanced", "full"]
DashboardMode = Literal["full", "cards", "minimal"]

type ConfigFlowPlaceholderValue = bool | int | float | str
type ConfigFlowPlaceholders = Mapping[str, ConfigFlowPlaceholderValue]
type MutableConfigFlowPlaceholders = dict[str, ConfigFlowPlaceholderValue]
"""Accepted performance mode values for coordinator tuning."""


def clone_placeholders(
  template: ConfigFlowPlaceholders,
) -> MutableConfigFlowPlaceholders:
  """Return a mutable copy of an immutable placeholder template."""  # noqa: E111

  return dict(template)  # noqa: E111


def freeze_placeholders(
  placeholders: MutableConfigFlowPlaceholders,
) -> ConfigFlowPlaceholders:
  """Return an immutable placeholder mapping."""  # noqa: E111

  return cast(ConfigFlowPlaceholders, MappingProxyType(dict(placeholders)))  # noqa: E111


PERFORMANCE_MODE_VALUES: Final[frozenset[PerformanceMode]] = frozenset(
  ("minimal", "balanced", "full"),
)
"""Canonical performance mode options for the integration."""


PERFORMANCE_MODE_ALIASES: Final[Mapping[str, PerformanceMode]] = MappingProxyType(
  {"standard": "balanced"},
)
"""Backward-compatible aliases mapped to canonical performance modes."""


def _coerce_clamped_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
  """Return an integer constrained to the provided inclusive bounds."""  # noqa: E111

  candidate = _coerce_int(value, default=default)  # noqa: E111
  if candidate < minimum:  # noqa: E111
    return minimum
  if candidate > maximum:  # noqa: E111
    return maximum
  return candidate  # noqa: E111


def normalize_performance_mode(
  value: Any,
  *,
  current: str | None = None,
  fallback: PerformanceMode = "balanced",
) -> PerformanceMode:
  """Return a supported performance mode string."""  # noqa: E111

  if isinstance(value, str):  # noqa: E111
    candidate = value.strip().lower()
    if candidate in PERFORMANCE_MODE_VALUES:
      return cast(PerformanceMode, candidate)  # noqa: E111
    alias = PERFORMANCE_MODE_ALIASES.get(candidate)
    if alias is not None:
      return alias  # noqa: E111

  if isinstance(current, str):  # noqa: E111
    existing = current.strip().lower()
    if existing in PERFORMANCE_MODE_VALUES:
      return cast(PerformanceMode, existing)  # noqa: E111
    alias = PERFORMANCE_MODE_ALIASES.get(existing)
    if alias is not None:
      return alias  # noqa: E111

  return fallback  # noqa: E111


def ensure_advanced_options(
  source: JSONLikeMapping,
  *,
  defaults: JSONLikeMapping | None = None,
) -> AdvancedOptions:
  """Normalise advanced options payloads for config entry storage."""  # noqa: E111

  baseline = defaults or {}  # noqa: E111

  retention_default = _coerce_int(  # noqa: E111
    baseline.get("data_retention_days"),
    default=90,
  )
  debug_default = _coerce_bool(baseline.get("debug_logging"), default=False)  # noqa: E111
  backup_default = _coerce_bool(baseline.get("auto_backup"), default=False)  # noqa: E111
  experimental_default = _coerce_bool(  # noqa: E111
    baseline.get("experimental_features"),
    default=False,
  )
  integrations_default = _coerce_bool(  # noqa: E111
    baseline.get(CONF_EXTERNAL_INTEGRATIONS),
    default=False,
  )
  endpoint_default = _coerce_str(baseline.get(CONF_API_ENDPOINT), default="")  # noqa: E111
  token_default = _coerce_str(baseline.get(CONF_API_TOKEN), default="")  # noqa: E111

  advanced: AdvancedOptions = {  # noqa: E111
    "performance_mode": normalize_performance_mode(
      source.get("performance_mode"),
      current=cast(str | None, baseline.get("performance_mode")),
    ),
    "debug_logging": _coerce_bool(
      source.get("debug_logging"),
      default=debug_default,
    ),
    "data_retention_days": _coerce_clamped_int(
      source.get("data_retention_days"),
      default=retention_default,
      minimum=30,
      maximum=365,
    ),
    "auto_backup": _coerce_bool(source.get("auto_backup"), default=backup_default),
    "experimental_features": _coerce_bool(
      source.get("experimental_features"),
      default=experimental_default,
    ),
    "external_integrations": _coerce_bool(
      source.get(CONF_EXTERNAL_INTEGRATIONS),
      default=integrations_default,
    ),
    "api_endpoint": _coerce_str(
      source.get(CONF_API_ENDPOINT),
      default=endpoint_default,
    ),
    "api_token": _coerce_str(source.get(CONF_API_TOKEN), default=token_default),
  }

  return advanced  # noqa: E111


def _project_modules_mapping(
  config: ModuleToggleMapping | DogModulesConfig,
) -> dict[str, bool]:
  """Return a stable ``dict[str, bool]`` projection for module toggles."""  # noqa: E111

  mapping: dict[str, bool] = {}  # noqa: E111
  for key_literal in MODULE_TOGGLE_KEYS:  # noqa: E111
    key = cast(str, key_literal)
    mapping[key] = bool(config.get(key_literal, False))
  return mapping  # noqa: E111


def dog_modules_projection_from_flow_input(
  user_input: Mapping[str, object],
  *,
  existing: DogModulesConfig | None = None,
) -> DogModulesProjection:
  """Return module toggle projections built from config-flow toggles."""  # noqa: E111

  modules: dict[ModuleToggleKey, bool] = {}  # noqa: E111

  if existing:  # noqa: E111
    for key in MODULE_TOGGLE_KEYS:
      flag = existing.get(key)  # noqa: E111
      if isinstance(flag, bool):  # noqa: E111
        modules[key] = flag

  for flow_flag, module_key in MODULE_TOGGLE_FLOW_FLAGS:  # noqa: E111
    modules[module_key] = _coerce_bool(
      user_input.get(flow_flag),
      default=modules.get(module_key, False),
    )

  config: DogModulesConfig = {}  # noqa: E111
  for key in MODULE_TOGGLE_KEYS:  # noqa: E111
    if key in modules:
      config[key] = modules[key]  # noqa: E111
  mapping = _project_modules_mapping(config)  # noqa: E111
  return DogModulesProjection(config=config, mapping=mapping)  # noqa: E111


def dog_modules_from_flow_input(
  user_input: Mapping[str, object],
  *,
  existing: DogModulesConfig | None = None,
) -> DogModulesConfig:
  """Return a :class:`DogModulesConfig` built from config-flow toggles."""  # noqa: E111

  return dog_modules_projection_from_flow_input(user_input, existing=existing).config  # noqa: E111


def ensure_dog_modules_projection(
  data: Mapping[str, object] | ConfigFlowUserInput | DogModulesProjection,
) -> DogModulesProjection:
  """Extract module toggle projections from ``data``.

  ``data`` may already be a :class:`DogModulesProjection`, a mapping containing a
  ``modules`` key, or a raw mapping of module toggle flags. The helper normalises
  all variants into the projection structure used throughout the integration so
  downstream consumers can rely on a consistent schema when static typing is
  enforced.
  """  # noqa: E111

  if isinstance(data, DogModulesProjection):  # noqa: E111
    return data

  modules: dict[ModuleToggleKey, bool] = {}  # noqa: E111
  modules_raw = data.get(DOG_MODULES_FIELD)  # noqa: E111
  candidate = modules_raw if isinstance(modules_raw, Mapping) else data  # noqa: E111

  for key in MODULE_TOGGLE_KEYS:  # noqa: E111
    value = candidate.get(key)
    if value is not None:
      modules[key] = _coerce_bool(value)  # noqa: E111

  config: DogModulesConfig = {}  # noqa: E111
  for key in MODULE_TOGGLE_KEYS:  # noqa: E111
    if key in modules:
      config[key] = modules[key]  # noqa: E111
  mapping = _project_modules_mapping(config)  # noqa: E111
  return DogModulesProjection(config=config, mapping=mapping)  # noqa: E111


def ensure_dog_modules_config(
  data: Mapping[str, object] | ConfigFlowUserInput | DogModulesProjection,
) -> DogModulesConfig:
  """Extract a :class:`DogModulesConfig` from supported module payloads."""  # noqa: E111

  return ensure_dog_modules_projection(data).config  # noqa: E111


def _is_modules_projection_like(value: Any) -> bool:
  """Return ``True`` when ``value`` resembles a modules projection payload."""  # noqa: E111

  if isinstance(value, DogModulesProjection):  # noqa: E111
    return True

  return hasattr(value, "config") and hasattr(value, "mapping")  # noqa: E111


def coerce_dog_modules_config(
  payload: Mapping[str, object]
  | ConfigFlowUserInput
  | DogModulesProjection
  | DogModulesConfig
  | None,
) -> DogModulesConfig:
  """Return a defensive ``DogModulesConfig`` copy tolerant of projections."""  # noqa: E111

  if _is_modules_projection_like(payload):  # noqa: E111
    config_attr = getattr(payload, "config", None)
    if isinstance(config_attr, Mapping):
      return cast(DogModulesConfig, dict(config_attr))  # noqa: E111

  if isinstance(payload, Mapping):  # noqa: E111
    config = ensure_dog_modules_config(payload)
    return cast(DogModulesConfig, dict(config))

  return cast(DogModulesConfig, {})  # noqa: E111


def ensure_dog_modules_mapping(
  data: Mapping[str, object] | DogModulesProjection,
) -> DogModulesMapping:
  """Return a ``DogModulesMapping`` projection from ``data``."""  # noqa: E111

  return ensure_dog_modules_projection(data).mapping  # noqa: E111


def dog_feeding_config_from_flow(user_input: DogFeedingStepInput) -> DogFeedingConfig:
  """Build a :class:`DogFeedingConfig` structure from flow input data."""  # noqa: E111

  meals_per_day = max(  # noqa: E111
    1,
    _coerce_int(
      user_input.get(CONF_MEALS_PER_DAY),
      default=2,
    ),
  )
  daily_amount = _coerce_float(  # noqa: E111
    user_input.get(
      CONF_DAILY_FOOD_AMOUNT,
    ),
    default=500.0,
  )
  portion_size = daily_amount / meals_per_day if meals_per_day else 0.0  # noqa: E111

  feeding_config: DogFeedingConfig = {  # noqa: E111
    "meals_per_day": meals_per_day,
    "daily_food_amount": daily_amount,
    "portion_size": portion_size,
    "food_type": _coerce_str(user_input.get(CONF_FOOD_TYPE), default="dry_food"),
    "feeding_schedule": _coerce_str(
      user_input.get("feeding_schedule"),
      default="flexible",
    ),
    "enable_reminders": _coerce_bool(
      user_input.get("enable_reminders"),
      default=True,
    ),
    "reminder_minutes_before": _coerce_int(
      user_input.get("reminder_minutes_before"),
      default=15,
    ),
  }

  if _coerce_bool(user_input.get("breakfast_enabled"), default=meals_per_day >= 1):  # noqa: E111
    feeding_config["breakfast_time"] = _coerce_str(
      user_input.get(CONF_BREAKFAST_TIME),
      default="07:00:00",
    )

  if _coerce_bool(user_input.get("lunch_enabled"), default=meals_per_day >= 3):  # noqa: E111
    feeding_config["lunch_time"] = _coerce_str(
      user_input.get(CONF_LUNCH_TIME),
      default="12:00:00",
    )

  if _coerce_bool(user_input.get("dinner_enabled"), default=meals_per_day >= 2):  # noqa: E111
    feeding_config["dinner_time"] = _coerce_str(
      user_input.get(CONF_DINNER_TIME),
      default="18:00:00",
    )

  if _coerce_bool(user_input.get("snacks_enabled"), default=False):  # noqa: E111
    feeding_config["snack_times"] = list(DEFAULT_FEEDING_SCHEDULE)

  return feeding_config  # noqa: E111


class DogGPSConfig(TypedDict, total=False):
  """GPS configuration captured during the dog setup flow."""  # noqa: E111

  gps_source: str  # noqa: E111
  gps_update_interval: int  # noqa: E111
  gps_accuracy_filter: float | int  # noqa: E111
  enable_geofencing: bool  # noqa: E111
  home_zone_radius: int | float  # noqa: E111


class DogWalkConfig(TypedDict, total=False):
  """Walk configuration captured during the dog setup flow."""  # noqa: E111

  daily_walk_target: int  # noqa: E111
  walk_duration_target: int  # noqa: E111
  walk_distance_target: int  # noqa: E111
  reminder_hours: int  # noqa: E111
  max_walk_speed: float | int  # noqa: E111


class DogGPSStepInput(TypedDict, total=False):
  """Raw GPS form payload provided during per-dog configuration."""  # noqa: E111

  gps_source: str  # noqa: E111
  gps_update_interval: int  # noqa: E111
  gps_accuracy_filter: float | int  # noqa: E111
  enable_geofencing: bool  # noqa: E111
  home_zone_radius: float | int  # noqa: E111


class GeofenceSettingsInput(TypedDict, total=False):
  """Options flow payload captured while editing geofencing settings."""  # noqa: E111

  geofencing_enabled: bool  # noqa: E111
  use_home_location: bool  # noqa: E111
  geofence_lat: float | int | str | None  # noqa: E111
  geofence_lon: float | int | str | None  # noqa: E111
  geofence_radius_m: float | int | str | None  # noqa: E111
  geofence_alerts_enabled: bool  # noqa: E111
  safe_zone_alerts: bool  # noqa: E111
  restricted_zone_alerts: bool  # noqa: E111
  zone_entry_notifications: bool  # noqa: E111
  zone_exit_notifications: bool  # noqa: E111


class DogFeedingStepInput(TypedDict, total=False):
  """Form payload captured during the per-dog feeding configuration step."""  # noqa: E111

  meals_per_day: int | float | str | None  # noqa: E111
  daily_food_amount: float | int | str | None  # noqa: E111
  food_type: str | None  # noqa: E111
  feeding_schedule: str | None  # noqa: E111
  breakfast_enabled: bool  # noqa: E111
  breakfast_time: str | None  # noqa: E111
  lunch_enabled: bool  # noqa: E111
  lunch_time: str | None  # noqa: E111
  dinner_enabled: bool  # noqa: E111
  dinner_time: str | None  # noqa: E111
  snacks_enabled: bool  # noqa: E111
  enable_reminders: bool  # noqa: E111
  reminder_minutes_before: int | float | str | None  # noqa: E111


class DogHealthStepInput(TypedDict, total=False):
  """Health configuration form payload recorded for a single dog."""  # noqa: E111

  vet_name: str | None  # noqa: E111
  vet_phone: str | None  # noqa: E111
  last_vet_visit: str | None  # noqa: E111
  next_checkup: str | None  # noqa: E111
  weight_tracking: bool  # noqa: E111
  ideal_weight: float | int | str | None  # noqa: E111
  body_condition_score: int | str | None  # noqa: E111
  activity_level: str | None  # noqa: E111
  weight_goal: str | None  # noqa: E111
  spayed_neutered: bool  # noqa: E111
  health_aware_portions: bool  # noqa: E111
  other_health_conditions: str | None  # noqa: E111
  has_diabetes: bool  # noqa: E111
  has_kidney_disease: bool  # noqa: E111
  has_heart_disease: bool  # noqa: E111
  has_arthritis: bool  # noqa: E111
  has_allergies: bool  # noqa: E111
  has_digestive_issues: bool  # noqa: E111
  grain_free: bool  # noqa: E111
  hypoallergenic: bool  # noqa: E111
  low_fat: bool  # noqa: E111
  senior_formula: bool  # noqa: E111
  puppy_formula: bool  # noqa: E111
  weight_control: bool  # noqa: E111
  sensitive_stomach: bool  # noqa: E111
  organic: bool  # noqa: E111
  raw_diet: bool  # noqa: E111
  prescription: bool  # noqa: E111
  diabetic: bool  # noqa: E111
  kidney_support: bool  # noqa: E111
  dental_care: bool  # noqa: E111
  joint_support: bool  # noqa: E111
  rabies_vaccination: str | None  # noqa: E111
  rabies_next: str | None  # noqa: E111
  dhpp_vaccination: str | None  # noqa: E111
  dhpp_next: str | None  # noqa: E111
  bordetella_vaccination: str | None  # noqa: E111
  bordetella_next: str | None  # noqa: E111
  medication_1_name: str | None  # noqa: E111
  medication_1_dosage: str | None  # noqa: E111
  medication_1_frequency: str | None  # noqa: E111
  medication_1_time: str | None  # noqa: E111
  medication_1_notes: str | None  # noqa: E111
  medication_1_with_meals: bool  # noqa: E111
  medication_2_name: str | None  # noqa: E111
  medication_2_dosage: str | None  # noqa: E111
  medication_2_frequency: str | None  # noqa: E111
  medication_2_time: str | None  # noqa: E111
  medication_2_notes: str | None  # noqa: E111
  medication_2_with_meals: bool  # noqa: E111


class DogFeedingConfig(TypedDict, total=False):
  """Feeding configuration captured during setup."""  # noqa: E111

  meals_per_day: int  # noqa: E111
  daily_food_amount: float | int  # noqa: E111
  food_type: str  # noqa: E111
  feeding_schedule: str  # noqa: E111
  breakfast_time: str  # noqa: E111
  lunch_time: str  # noqa: E111
  dinner_time: str  # noqa: E111
  snack_times: list[str]  # noqa: E111
  enable_reminders: bool  # noqa: E111
  reminder_minutes_before: int  # noqa: E111
  portion_size: float | int  # noqa: E111
  health_aware_portions: bool  # noqa: E111
  dog_weight: float | int | None  # noqa: E111
  ideal_weight: float | int | None  # noqa: E111
  age_months: int | None  # noqa: E111
  breed_size: str  # noqa: E111
  activity_level: str  # noqa: E111
  body_condition_score: int  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  weight_goal: str  # noqa: E111
  spayed_neutered: bool  # noqa: E111
  special_diet: list[str]  # noqa: E111
  diet_validation: DietValidationResult  # noqa: E111
  medication_with_meals: bool  # noqa: E111


class GeofenceOptions(TypedDict, total=False):
  """Options structure describing geofencing configuration for a profile."""  # noqa: E111

  geofencing_enabled: bool  # noqa: E111
  use_home_location: bool  # noqa: E111
  geofence_lat: float | None  # noqa: E111
  geofence_lon: float | None  # noqa: E111
  geofence_radius_m: int  # noqa: E111
  geofence_alerts_enabled: bool  # noqa: E111
  safe_zone_alerts: bool  # noqa: E111
  restricted_zone_alerts: bool  # noqa: E111
  zone_entry_notifications: bool  # noqa: E111
  zone_exit_notifications: bool  # noqa: E111


GeofenceOptionsField = Literal[
  "geofencing_enabled",
  "use_home_location",
  "geofence_lat",
  "geofence_lon",
  "geofence_radius_m",
  "geofence_alerts_enabled",
  "safe_zone_alerts",
  "restricted_zone_alerts",
  "zone_entry_notifications",
  "zone_exit_notifications",
]
GEOFENCE_ENABLED_FIELD: Final[GeofenceOptionsField] = "geofencing_enabled"
GEOFENCE_USE_HOME_FIELD: Final[GeofenceOptionsField] = "use_home_location"
GEOFENCE_LAT_FIELD: Final[GeofenceOptionsField] = "geofence_lat"
GEOFENCE_LON_FIELD: Final[GeofenceOptionsField] = "geofence_lon"
GEOFENCE_RADIUS_FIELD: Final[GeofenceOptionsField] = "geofence_radius_m"
GEOFENCE_ALERTS_FIELD: Final[GeofenceOptionsField] = "geofence_alerts_enabled"
GEOFENCE_SAFE_ZONE_FIELD: Final[GeofenceOptionsField] = "safe_zone_alerts"
GEOFENCE_RESTRICTED_ZONE_FIELD: Final[GeofenceOptionsField] = "restricted_zone_alerts"
GEOFENCE_ZONE_ENTRY_FIELD: Final[GeofenceOptionsField] = "zone_entry_notifications"
GEOFENCE_ZONE_EXIT_FIELD: Final[GeofenceOptionsField] = "zone_exit_notifications"


class NotificationOptions(TypedDict, total=False):
  """Structured notification preferences stored in config entry options."""  # noqa: E111

  quiet_hours: bool  # noqa: E111
  quiet_start: str  # noqa: E111
  quiet_end: str  # noqa: E111
  reminder_repeat_min: int  # noqa: E111
  priority_notifications: bool  # noqa: E111
  mobile_notifications: bool  # noqa: E111


NotificationOptionsField = Literal[
  "quiet_hours",
  "quiet_start",
  "quiet_end",
  "reminder_repeat_min",
  "priority_notifications",
  "mobile_notifications",
]
NOTIFICATION_QUIET_HOURS_FIELD: Final[NotificationOptionsField] = "quiet_hours"
NOTIFICATION_QUIET_START_FIELD: Final[NotificationOptionsField] = "quiet_start"
NOTIFICATION_QUIET_END_FIELD: Final[NotificationOptionsField] = "quiet_end"
NOTIFICATION_REMINDER_REPEAT_FIELD: Final[NotificationOptionsField] = (
  "reminder_repeat_min"
)
NOTIFICATION_PRIORITY_FIELD: Final[NotificationOptionsField] = "priority_notifications"
NOTIFICATION_MOBILE_FIELD: Final[NotificationOptionsField] = "mobile_notifications"


type NotificationOptionsInput = NotificationSettingsInput | JSONMapping
"""Mapping accepted by :func:`ensure_notification_options`."""


DEFAULT_NOTIFICATION_OPTIONS: Final[NotificationOptionsInput] = MappingProxyType(
  {
    NOTIFICATION_QUIET_HOURS_FIELD: True,
    NOTIFICATION_QUIET_START_FIELD: "22:00:00",
    NOTIFICATION_QUIET_END_FIELD: "07:00:00",
    NOTIFICATION_REMINDER_REPEAT_FIELD: DEFAULT_REMINDER_REPEAT_MIN,
    NOTIFICATION_PRIORITY_FIELD: True,
    NOTIFICATION_MOBILE_FIELD: True,
  },
)


class NotificationSettingsInput(TypedDict, total=False):
  """UI payload captured when editing notification options."""  # noqa: E111

  quiet_hours: bool  # noqa: E111
  quiet_start: str | None  # noqa: E111
  quiet_end: str | None  # noqa: E111
  reminder_repeat_min: int | float | str | None  # noqa: E111
  priority_notifications: bool  # noqa: E111
  mobile_notifications: bool  # noqa: E111


def ensure_notification_options(
  value: NotificationOptionsInput,
  /,
  *,
  defaults: NotificationOptionsInput | None = None,
) -> NotificationOptions:
  """Normalise a mapping into :class:`NotificationOptions`.

  The options flow historically stored quiet-hour fields as loose mappings that
  could drift to strings or numbers. This helper coerces supported values,
  clamps reminder intervals to the selector range, and overlays optional
  defaults so downstream callers always receive a typed payload.
  """  # noqa: E111

  options: NotificationOptions = {}  # noqa: E111

  def _coerce_bool(candidate: Any) -> bool | None:  # noqa: E111
    if isinstance(candidate, bool):
      return candidate  # noqa: E111
    if isinstance(candidate, int | float):
      return bool(candidate)  # noqa: E111
    if isinstance(candidate, str):
      lowered = candidate.strip().lower()  # noqa: E111
      if lowered in {"true", "yes", "on", "1"}:  # noqa: E111
        return True
      if lowered in {"false", "no", "off", "0"}:  # noqa: E111
        return False
    return None

  def _coerce_time(candidate: Any) -> str | None:  # noqa: E111
    if isinstance(candidate, str):
      trimmed = candidate.strip()  # noqa: E111
      if trimmed:  # noqa: E111
        return trimmed
    return None

  def _coerce_interval(candidate: Any) -> int | None:  # noqa: E111
    working = candidate
    if isinstance(working, str):
      working = working.strip()  # noqa: E111
      if not working:  # noqa: E111
        return None
      try:  # noqa: E111
        working = int(working)
      except ValueError:  # noqa: E111
        return None
    if isinstance(working, int | float):
      interval = int(working)  # noqa: E111
      return max(5, min(180, interval))  # noqa: E111
    return None

  def _apply(  # noqa: E111
    source_key: str,
    target_key: NotificationOptionsField,
    converter: Callable[[Any], Any | None],
  ) -> None:
    if defaults is not None:
      default_value = converter(defaults.get(source_key))  # noqa: E111
      if default_value is not None:  # noqa: E111
        options[target_key] = default_value
    override = converter(value.get(source_key))
    if override is not None:
      options[target_key] = override  # noqa: E111

  _apply(CONF_QUIET_HOURS, NOTIFICATION_QUIET_HOURS_FIELD, _coerce_bool)  # noqa: E111
  _apply(CONF_QUIET_START, NOTIFICATION_QUIET_START_FIELD, _coerce_time)  # noqa: E111
  _apply(CONF_QUIET_END, NOTIFICATION_QUIET_END_FIELD, _coerce_time)  # noqa: E111
  _apply(  # noqa: E111
    CONF_REMINDER_REPEAT_MIN,
    NOTIFICATION_REMINDER_REPEAT_FIELD,
    _coerce_interval,
  )
  _apply("priority_notifications", NOTIFICATION_PRIORITY_FIELD, _coerce_bool)  # noqa: E111
  _apply("mobile_notifications", NOTIFICATION_MOBILE_FIELD, _coerce_bool)  # noqa: E111

  return options  # noqa: E111


NotificationThreshold = Literal["low", "moderate", "high"]


class WeatherOptions(TypedDict, total=False):
  """Typed weather monitoring preferences stored in config entry options."""  # noqa: E111

  weather_entity: str | None  # noqa: E111
  weather_health_monitoring: bool  # noqa: E111
  weather_alerts: bool  # noqa: E111
  weather_update_interval: int  # noqa: E111
  temperature_alerts: bool  # noqa: E111
  uv_alerts: bool  # noqa: E111
  humidity_alerts: bool  # noqa: E111
  wind_alerts: bool  # noqa: E111
  storm_alerts: bool  # noqa: E111
  breed_specific_recommendations: bool  # noqa: E111
  health_condition_adjustments: bool  # noqa: E111
  auto_activity_adjustments: bool  # noqa: E111
  notification_threshold: NotificationThreshold  # noqa: E111


class FeedingOptions(TypedDict, total=False):
  """Typed feeding configuration stored in config entry options."""  # noqa: E111

  default_meals_per_day: int  # noqa: E111
  feeding_reminders: bool  # noqa: E111
  portion_tracking: bool  # noqa: E111
  calorie_tracking: bool  # noqa: E111
  auto_schedule: bool  # noqa: E111


class HealthOptions(TypedDict, total=False):
  """Typed health configuration stored in config entry options."""  # noqa: E111

  weight_tracking: bool  # noqa: E111
  medication_reminders: bool  # noqa: E111
  vet_reminders: bool  # noqa: E111
  grooming_reminders: bool  # noqa: E111
  health_alerts: bool  # noqa: E111


class SystemOptions(TypedDict, total=False):
  """System-wide maintenance preferences persisted in options."""  # noqa: E111

  data_retention_days: int  # noqa: E111
  auto_backup: bool  # noqa: E111
  performance_mode: PerformanceMode  # noqa: E111
  enable_analytics: bool  # noqa: E111
  enable_cloud_backup: bool  # noqa: E111
  resilience_skip_threshold: int  # noqa: E111
  resilience_breaker_threshold: int  # noqa: E111
  manual_check_event: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111


class DashboardOptions(TypedDict, total=False):
  """Dashboard rendering preferences for the integration."""  # noqa: E111

  show_statistics: bool  # noqa: E111
  show_alerts: bool  # noqa: E111
  compact_mode: bool  # noqa: E111
  show_maps: bool  # noqa: E111


class DashboardRendererOptions(DashboardOptions, total=False):
  """Extended dashboard options consumed by the async renderer."""  # noqa: E111

  show_settings: bool  # noqa: E111
  show_activity_summary: bool  # noqa: E111
  dashboard_url: str  # noqa: E111
  theme: str  # noqa: E111
  title: str  # noqa: E111
  icon: str  # noqa: E111
  url: str  # noqa: E111
  layout: str  # noqa: E111
  show_in_sidebar: bool  # noqa: E111
  show_activity_graph: bool  # noqa: E111
  show_breed_advice: bool  # noqa: E111
  show_weather_forecast: bool  # noqa: E111


type DashboardCardOptions = DashboardRendererOptions
"""Card generator options forwarded from the dashboard renderer."""


class DashboardCardPerformanceStats(TypedDict):
  """Performance counters tracked while generating dashboard cards."""  # noqa: E111

  validations_count: int  # noqa: E111
  cache_hits: int  # noqa: E111
  cache_misses: int  # noqa: E111
  generation_time_total: float  # noqa: E111
  errors_handled: int  # noqa: E111


class DashboardCardGlobalPerformanceStats(TypedDict):
  """Static performance characteristics for dashboard card generation."""  # noqa: E111

  validation_cache_size: int  # noqa: E111
  cache_threshold: float  # noqa: E111
  max_concurrent_validations: int  # noqa: E111
  validation_timeout: float  # noqa: E111
  card_generation_timeout: float  # noqa: E111


class TemplateCacheStats(TypedDict):
  """Statistics returned by the in-memory dashboard template cache."""  # noqa: E111

  hits: int  # noqa: E111
  misses: int  # noqa: E111
  hit_rate: float  # noqa: E111
  cached_items: int  # noqa: E111
  evictions: int  # noqa: E111
  max_size: int  # noqa: E111


class TemplateCacheDiagnosticsMetadata(TypedDict):
  """Metadata describing the template cache configuration."""  # noqa: E111

  cached_keys: list[str]  # noqa: E111
  ttl_seconds: int  # noqa: E111
  max_size: int  # noqa: E111
  evictions: int  # noqa: E111


class TemplateCacheSnapshot(TypedDict):
  """Complete snapshot exported for diagnostics and telemetry."""  # noqa: E111

  stats: TemplateCacheStats  # noqa: E111
  metadata: TemplateCacheDiagnosticsMetadata  # noqa: E111


class CardModConfig(TypedDict, total=False):
  """Styling payload supported by card-mod aware templates."""  # noqa: E111

  style: str  # noqa: E111


type LovelaceCardValue = (
  JSONPrimitive
  | Sequence["LovelaceCardValue"]
  | Mapping[str, "LovelaceCardValue"]
  | CardModConfig
)
"""Valid value stored inside a Lovelace card configuration."""


type LovelaceCardConfig = dict[str, LovelaceCardValue]
"""Mutable Lovelace card configuration payload."""


class LovelaceViewConfig(TypedDict, total=False):
  """Typed Lovelace view configuration produced by the renderer."""  # noqa: E111

  title: str  # noqa: E111
  path: str  # noqa: E111
  icon: str  # noqa: E111
  theme: NotRequired[str]  # noqa: E111
  cards: list[LovelaceCardConfig]  # noqa: E111
  badges: NotRequired[list[str]]  # noqa: E111
  type: NotRequired[str]  # noqa: E111


class DashboardRenderResult(TypedDict):
  """Typed dashboard payload emitted by the async renderer."""  # noqa: E111

  views: list[LovelaceViewConfig]  # noqa: E111


class DashboardRenderJobConfig(TypedDict, total=False):
  """Payload stored on queued render jobs."""  # noqa: E111

  dogs: Sequence[DogConfigData]  # noqa: E111
  dog: DogConfigData  # noqa: E111
  coordinator_statistics: CoordinatorStatisticsPayload | JSONMapping  # noqa: E111
  service_execution_metrics: CoordinatorRejectionMetrics | JSONMapping  # noqa: E111
  service_guard_metrics: HelperManagerGuardMetrics | JSONMapping  # noqa: E111


class DashboardRendererStatistics(TypedDict):
  """Summary statistics describing renderer state."""  # noqa: E111

  active_jobs: int  # noqa: E111
  total_jobs_processed: int  # noqa: E111
  template_cache: TemplateCacheStats  # noqa: E111


class SwitchExtraAttributes(TypedDict, total=False):
  """Common state attributes exposed by optimized switches."""  # noqa: E111

  dog_id: str  # noqa: E111
  dog_name: str  # noqa: E111
  switch_type: str  # noqa: E111
  last_changed: str  # noqa: E111
  profile_optimized: bool  # noqa: E111
  enabled_modules: list[str]  # noqa: E111
  total_modules: int  # noqa: E111


class SwitchFeatureAttributes(SwitchExtraAttributes, total=False):
  """Additional metadata surfaced by feature-level switches."""  # noqa: E111

  feature_id: str  # noqa: E111
  parent_module: str  # noqa: E111
  feature_name: str  # noqa: E111


class AdvancedOptions(TypedDict, total=False):
  """Advanced diagnostics and integration toggles stored on the entry."""  # noqa: E111

  performance_mode: PerformanceMode  # noqa: E111
  debug_logging: bool  # noqa: E111
  data_retention_days: int  # noqa: E111
  auto_backup: bool  # noqa: E111
  experimental_features: bool  # noqa: E111
  external_integrations: bool  # noqa: E111
  api_endpoint: str  # noqa: E111
  api_token: str  # noqa: E111


class PerformanceOptions(TypedDict, total=False):
  """Performance tuning parameters applied through the options flow."""  # noqa: E111

  entity_profile: str  # noqa: E111
  performance_mode: PerformanceMode  # noqa: E111
  batch_size: int  # noqa: E111
  cache_ttl: int  # noqa: E111
  selective_refresh: bool  # noqa: E111


class GPSOptions(TypedDict, total=False):
  """Global GPS configuration stored in the options flow."""  # noqa: E111

  gps_enabled: bool  # noqa: E111
  gps_update_interval: int  # noqa: E111
  gps_accuracy_filter: float  # noqa: E111
  gps_distance_filter: float  # noqa: E111
  route_recording: bool  # noqa: E111
  route_history_days: int  # noqa: E111
  auto_track_walks: bool  # noqa: E111


GPS_SETTINGS_FIELD: Final[Literal["gps_settings"]] = "gps_settings"
GPSOptionsField = Literal[
  "gps_enabled",
  "gps_update_interval",
  "gps_accuracy_filter",
  "gps_distance_filter",
  "route_recording",
  "route_history_days",
  "auto_track_walks",
]
GPS_ENABLED_FIELD: Final[GPSOptionsField] = "gps_enabled"
GPS_UPDATE_INTERVAL_FIELD: Final[GPSOptionsField] = "gps_update_interval"
GPS_ACCURACY_FILTER_FIELD: Final[GPSOptionsField] = "gps_accuracy_filter"
GPS_DISTANCE_FILTER_FIELD: Final[GPSOptionsField] = "gps_distance_filter"
ROUTE_RECORDING_FIELD: Final[GPSOptionsField] = "route_recording"
ROUTE_HISTORY_DAYS_FIELD: Final[GPSOptionsField] = "route_history_days"
AUTO_TRACK_WALKS_FIELD: Final[GPSOptionsField] = "auto_track_walks"


class DogOptionsEntry(TypedDict, total=False):
  """Per-dog overrides captured via the options flow."""  # noqa: E111

  dog_id: str  # noqa: E111
  modules: DogModulesConfig  # noqa: E111
  notifications: NotificationOptions  # noqa: E111
  gps_settings: GPSOptions  # noqa: E111
  geofence_settings: GeofenceOptions  # noqa: E111
  feeding_settings: FeedingOptions  # noqa: E111
  health_settings: HealthOptions  # noqa: E111


type DogOptionsMap = dict[str, DogOptionsEntry]


class PawControlOptionsData(PerformanceOptions, total=False):
  """Complete options mapping persisted on :class:`ConfigEntry` objects."""  # noqa: E111

  geofence_settings: GeofenceOptions  # noqa: E111
  notifications: NotificationOptions  # noqa: E111
  weather_settings: WeatherOptions  # noqa: E111
  feeding_settings: FeedingOptions  # noqa: E111
  health_settings: HealthOptions  # noqa: E111
  system_settings: SystemOptions  # noqa: E111
  dashboard_settings: DashboardOptions  # noqa: E111
  advanced_settings: AdvancedOptions  # noqa: E111
  gps_settings: GPSOptions  # noqa: E111
  gps_update_interval: int  # noqa: E111
  gps_distance_filter: float  # noqa: E111
  gps_accuracy_filter: float  # noqa: E111
  external_integrations: bool  # noqa: E111
  api_endpoint: str  # noqa: E111
  api_token: str  # noqa: E111
  weather_entity: str | None  # noqa: E111
  reset_time: str  # noqa: E111
  data_retention_days: int  # noqa: E111
  modules: DogModulesConfig  # noqa: E111
  dog_options: DogOptionsMap  # noqa: E111
  dogs: list[DogConfigData]  # noqa: E111
  import_source: str  # noqa: E111
  last_reauth: NotRequired[str]  # noqa: E111
  reauth_health_issues: NotRequired[list[str]]  # noqa: E111
  reauth_health_warnings: NotRequired[list[str]]  # noqa: E111
  last_reauth_summary: NotRequired[str]  # noqa: E111
  enable_analytics: bool  # noqa: E111
  enable_cloud_backup: bool  # noqa: E111
  debug_logging: bool  # noqa: E111


ConfigFlowDiscoverySource = Literal[
  "zeroconf",
  "dhcp",
  "usb",
  "bluetooth",
  "import",
  "reauth",
  "unknown",
]


type ConfigFlowDiscoveryPropertyValue = bool | int | float | str | bytes | Sequence[str]


type ConfigFlowDiscoveryProperties = dict[
  str,
  ConfigFlowDiscoveryPropertyValue,
]


type ConfigFlowInputMapping = Mapping[str, JSONValue]
"""Generic mapping accepted by config flow steps for user input payloads."""


class ConfigFlowImportData(TypedDict):
  """Config entry data payload produced when importing YAML configuration."""  # noqa: E111

  name: str  # noqa: E111
  dogs: list[DogConfigData]  # noqa: E111
  entity_profile: str  # noqa: E111
  import_warnings: list[str]  # noqa: E111
  import_timestamp: str  # noqa: E111


class ConfigFlowImportOptions(TypedDict):
  """Config entry options payload produced when importing YAML configuration."""  # noqa: E111

  entity_profile: str  # noqa: E111
  dashboard_enabled: bool  # noqa: E111
  dashboard_auto_create: bool  # noqa: E111
  import_source: Literal["configuration_yaml"]  # noqa: E111


class ConfigFlowImportResult(TypedDict):
  """Structured result returned by enhanced config-flow import validation."""  # noqa: E111

  data: ConfigFlowImportData  # noqa: E111
  options: ConfigFlowImportOptions  # noqa: E111


class ConfigFlowDiscoveryData(TypedDict, total=False):
  """Metadata captured from config flow discovery sources."""  # noqa: E111

  source: ConfigFlowDiscoverySource  # noqa: E111
  hostname: str  # noqa: E111
  host: str  # noqa: E111
  port: int  # noqa: E111
  ip: str  # noqa: E111
  macaddress: str  # noqa: E111
  properties: ConfigFlowDiscoveryProperties  # noqa: E111
  type: str  # noqa: E111
  name: str  # noqa: E111
  description: str  # noqa: E111
  manufacturer: str  # noqa: E111
  vid: str  # noqa: E111
  pid: str  # noqa: E111
  serial_number: str  # noqa: E111
  device: str  # noqa: E111
  address: str  # noqa: E111
  service_uuids: list[str]  # noqa: E111
  last_seen: str  # noqa: E111


type ConfigFlowDiscoveryComparison = ConfigFlowDiscoveryData
"""Normalized discovery payload used for change comparison in config flows."""


type DiscoveryUpdateValue = ConfigFlowDiscoveryData | str
"""Allowed value types stored in discovery update payloads."""


class DiscoveryUpdatePayload(TypedDict, total=False):
  """Updates persisted on config entries when discovery metadata changes."""  # noqa: E111

  discovery_info: ConfigFlowDiscoveryData  # noqa: E111
  host: str  # noqa: E111
  device: str  # noqa: E111
  address: str  # noqa: E111


class DiscoveryConfirmInput(TypedDict):
  """Form payload submitted when the user confirms discovery."""  # noqa: E111

  confirm: bool  # noqa: E111


class ProfileSelectionInput(TypedDict):
  """User input captured when selecting an entity profile."""  # noqa: E111

  entity_profile: str  # noqa: E111


class ProfileSelectorOption(TypedDict):
  """Selector option exposed when rendering profile choices."""  # noqa: E111

  value: str  # noqa: E111
  label: str  # noqa: E111


class EntityProfileOptionsInput(ProfileSelectionInput):
  """Options flow payload for selecting an entity profile."""  # noqa: E111

  preview_estimate: NotRequired[bool]  # noqa: E111


class IntegrationNameValidationResult(TypedDict):
  """Validation response for integration name checks during setup."""  # noqa: E111

  valid: bool  # noqa: E111
  errors: dict[str, str]  # noqa: E111


class ConfigFlowGlobalSettings(TypedDict, total=False):
  """Global configuration captured during the setup flow."""  # noqa: E111

  performance_mode: PerformanceMode  # noqa: E111
  enable_analytics: bool  # noqa: E111
  enable_cloud_backup: bool  # noqa: E111
  data_retention_days: int  # noqa: E111
  debug_logging: bool  # noqa: E111


class FinalSetupValidationResult(TypedDict):
  """Outcome returned by the final setup validation pass."""  # noqa: E111

  valid: bool  # noqa: E111
  errors: list[str]  # noqa: E111
  estimated_entities: int  # noqa: E111


class ConfigEntryDataPayload(TypedDict, total=False):
  """Config entry data stored when onboarding PawControl."""  # noqa: E111

  name: Required[str]  # noqa: E111
  dogs: Required[list[DogConfigData]]  # noqa: E111
  entity_profile: Required[str]  # noqa: E111
  setup_timestamp: Required[str]  # noqa: E111
  discovery_info: NotRequired[ConfigFlowDiscoveryData]  # noqa: E111
  external_entities: NotRequired[ExternalEntityConfig]  # noqa: E111


class ConfigEntryOptionsPayload(PawControlOptionsData, total=False):
  """Options mapping persisted alongside PawControl config entries."""  # noqa: E111

  dashboard_enabled: bool  # noqa: E111
  dashboard_auto_create: bool  # noqa: E111
  performance_monitoring: bool  # noqa: E111
  last_reconfigure: NotRequired[str]  # noqa: E111
  previous_profile: NotRequired[str]  # noqa: E111
  reconfigure_telemetry: NotRequired[ReconfigureTelemetry]  # noqa: E111
  dashboard_mode: DashboardMode  # noqa: E111
  resilience_skip_threshold: int | float | str | None  # noqa: E111
  resilience_breaker_threshold: int | float | str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111
  manual_check_event: str | None  # noqa: E111


class ModuleConfigurationStepInput(TypedDict, total=False):
  """User-provided values collected during the module setup step."""  # noqa: E111

  performance_mode: PerformanceMode  # noqa: E111
  enable_analytics: bool  # noqa: E111
  enable_cloud_backup: bool  # noqa: E111
  data_retention_days: int  # noqa: E111
  debug_logging: bool  # noqa: E111
  enable_notifications: bool  # noqa: E111
  enable_dashboard: bool  # noqa: E111
  auto_backup: bool  # noqa: E111


class ModuleConfigurationSnapshot(TypedDict):
  """Persisted view of the global module configuration toggles."""  # noqa: E111

  enable_notifications: bool  # noqa: E111
  enable_dashboard: bool  # noqa: E111
  performance_mode: PerformanceMode  # noqa: E111
  data_retention_days: int  # noqa: E111
  auto_backup: bool  # noqa: E111
  debug_logging: bool  # noqa: E111


class DashboardSetupConfig(TypedDict, total=False):
  """Dashboard preferences collected during setup before persistence."""  # noqa: E111

  dashboard_enabled: bool  # noqa: E111
  dashboard_auto_create: bool  # noqa: E111
  dashboard_per_dog: bool  # noqa: E111
  dashboard_theme: str  # noqa: E111
  dashboard_mode: DashboardMode  # noqa: E111
  dashboard_template: str  # noqa: E111
  show_statistics: bool  # noqa: E111
  show_maps: bool  # noqa: E111
  show_health_charts: bool  # noqa: E111
  show_feeding_schedule: bool  # noqa: E111
  show_alerts: bool  # noqa: E111
  compact_mode: bool  # noqa: E111
  auto_refresh: bool  # noqa: E111
  refresh_interval: int  # noqa: E111


class DashboardConfigurationStepInput(TypedDict):
  """Raw dashboard configuration payload received from the UI step."""  # noqa: E111

  auto_create_dashboard: NotRequired[bool]  # noqa: E111
  create_per_dog_dashboards: NotRequired[bool]  # noqa: E111
  dashboard_theme: NotRequired[str]  # noqa: E111
  dashboard_template: NotRequired[str]  # noqa: E111
  dashboard_mode: NotRequired[DashboardMode]  # noqa: E111
  show_statistics: NotRequired[bool]  # noqa: E111
  show_maps: NotRequired[bool]  # noqa: E111
  show_health_charts: NotRequired[bool]  # noqa: E111
  show_feeding_schedule: NotRequired[bool]  # noqa: E111
  show_alerts: NotRequired[bool]  # noqa: E111
  compact_mode: NotRequired[bool]  # noqa: E111
  auto_refresh: NotRequired[bool]  # noqa: E111
  refresh_interval: NotRequired[int]  # noqa: E111


class AddAnotherDogInput(TypedDict):
  """Payload for yes/no "add another dog" prompts in flows."""  # noqa: E111

  add_another: NotRequired[bool]  # noqa: E111


ManualEventField = Literal[
  "manual_check_event",
  "manual_guard_event",
  "manual_breaker_event",
]

ManualEventSource = Literal[
  "default",
  "system_settings",
  "options",
  "config_entry",
  "blueprint",
  "disabled",
]


class ManualEventDefaults(TypedDict):
  """Manual event defaults for system settings flows."""  # noqa: E111

  manual_check_event: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111


class ManualEventSchemaDefaults(TypedDict):
  """Stringified manual event defaults used in form schemas."""  # noqa: E111

  manual_check_event: str  # noqa: E111
  manual_guard_event: str  # noqa: E111
  manual_breaker_event: str  # noqa: E111


class ManualEventOption(TypedDict, total=False):
  """Select option payload for manual event configuration choices."""  # noqa: E111

  value: Required[str]  # noqa: E111
  label: Required[str]  # noqa: E111
  description: NotRequired[str]  # noqa: E111
  badge: NotRequired[str]  # noqa: E111
  help_text: NotRequired[str]  # noqa: E111
  metadata_sources: NotRequired[list[str]]  # noqa: E111
  metadata_primary_source: NotRequired[str]  # noqa: E111


type OptionsMainMenuAction = Literal[
  "entity_profiles",
  "manage_dogs",
  "performance_settings",
  "gps_settings",
  "push_settings",
  "geofence_settings",
  "weather_settings",
  "notifications",
  "feeding_settings",
  "health_settings",
  "system_settings",
  "dashboard_settings",
  "advanced_settings",
  "import_export",
]
"""Supported menu actions for the options flow root menu."""


PUSH_SETTINGS_MENU_ACTION: Final[OptionsMainMenuAction] = "push_settings"


class OptionsMainMenuInput(TypedDict):
  """Menu selection payload for the options flow root."""  # noqa: E111

  action: OptionsMainMenuAction  # noqa: E111


type OptionsMenuAction = Literal[
  "add_dog",
  "edit_dog",
  "remove_dog",
  "configure_modules",
  "configure_door_sensor",
  "back",
]
"""Supported menu actions for the options flow dog management step."""


class OptionsMenuInput(TypedDict):
  """Menu selection payload for the dog management options menu."""  # noqa: E111

  action: OptionsMenuAction  # noqa: E111


class OptionsDogSelectionInput(TypedDict):
  """Payload used when selecting a dog in the options flow."""  # noqa: E111

  dog_id: str  # noqa: E111


class OptionsDogRemovalInput(OptionsDogSelectionInput):
  """Payload used when confirming dog removal in the options flow."""  # noqa: E111

  confirm_remove: bool  # noqa: E111


class OptionsDogEditInput(TypedDict):
  """Payload for editing dog metadata in the options flow."""  # noqa: E111

  dog_name: NotRequired[str]  # noqa: E111
  dog_breed: NotRequired[str]  # noqa: E111
  dog_age: NotRequired[int | float | str | None]  # noqa: E111
  dog_weight: NotRequired[int | float | str | None]  # noqa: E111
  dog_size: NotRequired[str | None]  # noqa: E111


class OptionsProfilePreviewInput(TypedDict):
  """Payload used for profile preview interactions in the options flow."""  # noqa: E111

  profile: str  # noqa: E111
  apply_profile: NotRequired[bool]  # noqa: E111


class OptionsPerformanceSettingsInput(TypedDict, total=False):
  """Payload for performance settings in the options flow."""  # noqa: E111

  entity_profile: str  # noqa: E111
  performance_mode: PerformanceMode  # noqa: E111
  batch_size: int | float | str | None  # noqa: E111
  cache_ttl: int | float | str | None  # noqa: E111
  selective_refresh: bool  # noqa: E111


class OptionsDogModulesInput(TypedDict, total=False):
  """Payload for per-dog module configuration in the options flow."""  # noqa: E111

  module_feeding: bool  # noqa: E111
  module_walk: bool  # noqa: E111
  module_gps: bool  # noqa: E111
  module_garden: bool  # noqa: E111
  module_health: bool  # noqa: E111
  module_notifications: bool  # noqa: E111
  module_dashboard: bool  # noqa: E111
  module_visitor: bool  # noqa: E111
  module_grooming: bool  # noqa: E111
  module_medication: bool  # noqa: E111
  module_training: bool  # noqa: E111


class OptionsDoorSensorInput(TypedDict, total=False):
  """Payload for configuring door sensor overrides in the options flow."""  # noqa: E111

  door_sensor: str | None  # noqa: E111
  walk_detection_timeout: int | float | str | None  # noqa: E111
  minimum_walk_duration: int | float | str | None  # noqa: E111
  maximum_walk_duration: int | float | str | None  # noqa: E111
  door_closed_delay: int | float | str | None  # noqa: E111
  require_confirmation: bool | int | float | str | None  # noqa: E111
  auto_end_walks: bool | int | float | str | None  # noqa: E111
  confidence_threshold: int | float | str | None  # noqa: E111


class OptionsGeofenceInput(TypedDict, total=False):
  """Payload for geofencing configuration in the options flow."""  # noqa: E111

  geofence_enabled: bool  # noqa: E111
  geofence_use_home: bool  # noqa: E111
  geofence_lat: float | int | str | None  # noqa: E111
  geofence_lon: float | int | str | None  # noqa: E111
  geofence_radius: int | float | str | None  # noqa: E111
  geofence_alerts: bool  # noqa: E111
  geofence_safe_zone: bool  # noqa: E111
  geofence_restricted_zone: bool  # noqa: E111
  geofence_zone_entry: bool  # noqa: E111
  geofence_zone_exit: bool  # noqa: E111


class OptionsGPSSettingsInput(TypedDict, total=False):
  """Payload for GPS settings in the options flow."""  # noqa: E111

  gps_enabled: bool  # noqa: E111
  gps_update_interval: int | float | str | None  # noqa: E111
  gps_accuracy_filter: int | float | str | None  # noqa: E111
  gps_distance_filter: int | float | str | None  # noqa: E111
  route_recording: bool  # noqa: E111
  route_history_days: int | float | str | None  # noqa: E111
  auto_track_walks: bool  # noqa: E111


class OptionsWeatherSettingsInput(TypedDict, total=False):
  """Payload for weather settings in the options flow."""  # noqa: E111

  weather_entity: str | None  # noqa: E111
  weather_health_monitoring: bool  # noqa: E111
  weather_alerts: bool  # noqa: E111
  weather_update_interval: int | float | str | None  # noqa: E111
  temperature_alerts: bool  # noqa: E111
  uv_alerts: bool  # noqa: E111
  humidity_alerts: bool  # noqa: E111
  wind_alerts: bool  # noqa: E111
  storm_alerts: bool  # noqa: E111
  breed_specific_recommendations: bool  # noqa: E111
  health_condition_adjustments: bool  # noqa: E111
  auto_activity_adjustments: bool  # noqa: E111
  notification_threshold: str | None  # noqa: E111


class OptionsFeedingSettingsInput(TypedDict, total=False):
  """Payload for feeding settings in the options flow."""  # noqa: E111

  meals_per_day: int | float | str | None  # noqa: E111
  feeding_reminders: bool  # noqa: E111
  portion_tracking: bool  # noqa: E111
  calorie_tracking: bool  # noqa: E111
  auto_schedule: bool  # noqa: E111


class OptionsHealthSettingsInput(TypedDict, total=False):
  """Payload for health settings in the options flow."""  # noqa: E111

  weight_tracking: bool  # noqa: E111
  medication_reminders: bool  # noqa: E111
  vet_reminders: bool  # noqa: E111
  grooming_reminders: bool  # noqa: E111
  health_alerts: bool  # noqa: E111


class OptionsSystemSettingsInput(TypedDict, total=False):
  """Payload for system settings in the options flow."""  # noqa: E111

  data_retention_days: int | float | str | None  # noqa: E111
  auto_backup: bool  # noqa: E111
  performance_mode: PerformanceMode  # noqa: E111
  enable_analytics: bool  # noqa: E111
  enable_cloud_backup: bool  # noqa: E111
  resilience_skip_threshold: int | float | str | None  # noqa: E111
  resilience_breaker_threshold: int | float | str | None  # noqa: E111
  manual_check_event: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111
  reset_time: str | None  # noqa: E111


class OptionsDashboardSettingsInput(TypedDict, total=False):
  """Payload for dashboard settings in the options flow."""  # noqa: E111

  dashboard_mode: DashboardMode  # noqa: E111
  show_statistics: bool  # noqa: E111
  show_alerts: bool  # noqa: E111
  compact_mode: bool  # noqa: E111
  show_maps: bool  # noqa: E111


class OptionsAdvancedSettingsInput(TypedDict, total=False):
  """Payload for advanced settings in the options flow."""  # noqa: E111

  performance_mode: PerformanceMode  # noqa: E111
  debug_logging: bool  # noqa: E111
  data_retention_days: int | float | str | None  # noqa: E111
  auto_backup: bool  # noqa: E111
  experimental_features: bool  # noqa: E111
  external_integrations: bool  # noqa: E111
  api_endpoint: str  # noqa: E111
  api_token: str  # noqa: E111


class PushSettingsInput(TypedDict, total=False):
  """Payload for push ingestion settings in the options flow."""  # noqa: E111

  webhook_enabled: bool  # noqa: E111
  webhook_require_signature: bool  # noqa: E111
  webhook_secret: str | None  # noqa: E111
  mqtt_enabled: bool  # noqa: E111
  mqtt_topic: str | None  # noqa: E111
  push_payload_max_bytes: int | float | str | None  # noqa: E111
  push_nonce_ttl_seconds: int | float | str | None  # noqa: E111
  push_rate_limit_webhook_per_minute: int | float | str | None  # noqa: E111
  push_rate_limit_mqtt_per_minute: int | float | str | None  # noqa: E111
  push_rate_limit_entity_per_minute: int | float | str | None  # noqa: E111


class OptionsImportExportInput(TypedDict, total=False):
  """Payload for import/export selection in the options flow."""  # noqa: E111

  action: Literal["export", "import"]  # noqa: E111


class OptionsExportDisplayInput(TypedDict, total=False):
  """Payload for export display steps in the options flow."""  # noqa: E111

  export_blob: str  # noqa: E111


class OptionsImportPayloadInput(TypedDict, total=False):
  """Payload for importing exported options data."""  # noqa: E111

  payload: str  # noqa: E111


class ConfigFlowOperationMetrics(TypedDict):
  """Aggregated metrics collected for a single config-flow operation."""  # noqa: E111

  avg_time: float  # noqa: E111
  max_time: float  # noqa: E111
  count: int  # noqa: E111


type ConfigFlowOperationMetricsMap = dict[str, ConfigFlowOperationMetrics]


class ConfigFlowPerformanceStats(TypedDict):
  """Snapshot describing config-flow performance diagnostics."""  # noqa: E111

  operations: ConfigFlowOperationMetricsMap  # noqa: E111
  validations: dict[str, int]  # noqa: E111


class FeedingSizeDefaults(TypedDict):
  """Default feeding configuration derived from the selected dog size."""  # noqa: E111

  meals_per_day: int  # noqa: E111
  daily_food_amount: int  # noqa: E111
  feeding_times: list[str]  # noqa: E111
  portion_size: int  # noqa: E111


type FeedingSizeDefaultsMap = dict[str, FeedingSizeDefaults]


class FeedingSetupConfig(TypedDict, total=False):
  """Feeding defaults gathered while configuring modules during setup."""  # noqa: E111

  default_daily_food_amount: float | int  # noqa: E111
  default_meals_per_day: int  # noqa: E111
  default_food_type: str  # noqa: E111
  default_special_diet: list[str]  # noqa: E111
  default_feeding_schedule_type: str  # noqa: E111
  auto_portion_calculation: bool  # noqa: E111
  medication_with_meals: bool  # noqa: E111
  feeding_reminders: bool  # noqa: E111
  portion_tolerance: int  # noqa: E111


class FeedingConfigurationStepInput(TypedDict, total=False):
  """Raw feeding configuration payload received from the UI step."""  # noqa: E111

  daily_food_amount: float | int  # noqa: E111
  meals_per_day: int  # noqa: E111
  food_type: str  # noqa: E111
  special_diet: list[str]  # noqa: E111
  feeding_schedule_type: str  # noqa: E111
  portion_calculation: bool  # noqa: E111
  medication_with_meals: bool  # noqa: E111
  feeding_reminders: bool  # noqa: E111
  portion_tolerance: int  # noqa: E111


class ModuleConfigurationPlaceholders(TypedDict):
  """Placeholders exposed while rendering the module configuration form."""  # noqa: E111

  dog_count: int  # noqa: E111
  module_summary: str  # noqa: E111
  total_modules: int  # noqa: E111
  gps_dogs: int  # noqa: E111
  health_dogs: int  # noqa: E111


class AddDogCapacityPlaceholders(TypedDict):
  """Placeholders rendered when summarising configured dogs."""  # noqa: E111

  dog_count: int  # noqa: E111
  max_dogs: int  # noqa: E111
  current_dogs: str  # noqa: E111
  remaining_spots: int  # noqa: E111


class DogModulesSuggestionPlaceholders(TypedDict):
  """Placeholders exposed while recommending per-dog modules."""  # noqa: E111

  dog_name: str  # noqa: E111
  dog_size: str  # noqa: E111
  dog_age: int  # noqa: E111


class AddDogSummaryPlaceholders(TypedDict):
  """Placeholders rendered on the main add-dog form."""  # noqa: E111

  dogs_configured: str  # noqa: E111
  max_dogs: str  # noqa: E111
  discovery_hint: str  # noqa: E111


class DogModulesSmartDefaultsPlaceholders(TypedDict):
  """Placeholders surfaced alongside smart module defaults."""  # noqa: E111

  dog_name: str  # noqa: E111
  dogs_configured: str  # noqa: E111
  smart_defaults: str  # noqa: E111


class AddAnotherDogPlaceholders(TypedDict):
  """Placeholders shown when asking to add another dog."""  # noqa: E111

  dogs_configured: str  # noqa: E111
  dogs_list: str  # noqa: E111
  can_add_more: str  # noqa: E111
  max_dogs: str  # noqa: E111
  performance_note: str  # noqa: E111


class AddAnotherDogSummaryPlaceholders(TypedDict):
  """Placeholders shown when summarising configured dogs."""  # noqa: E111

  dogs_list: str  # noqa: E111
  dog_count: str  # noqa: E111
  max_dogs: int  # noqa: E111
  remaining_spots: int  # noqa: E111
  at_limit: str  # noqa: E111


class DashboardConfigurationPlaceholders(TypedDict):
  """Placeholders used when rendering the dashboard configuration form."""  # noqa: E111

  dog_count: int  # noqa: E111
  dashboard_info: str  # noqa: E111
  features: str  # noqa: E111


class FeedingConfigurationPlaceholders(TypedDict):
  """Placeholders used when rendering the feeding configuration form."""  # noqa: E111

  dog_count: int  # noqa: E111
  feeding_summary: str  # noqa: E111


class DogGPSPlaceholders(TypedDict):
  """Placeholders surfaced in the per-dog GPS configuration step."""  # noqa: E111

  dog_name: str  # noqa: E111


class DogFeedingPlaceholders(TypedDict):
  """Placeholders rendered alongside the per-dog feeding configuration."""  # noqa: E111

  dog_name: str  # noqa: E111
  dog_weight: str  # noqa: E111
  suggested_amount: str  # noqa: E111
  portion_info: str  # noqa: E111


class DogHealthPlaceholders(TypedDict):
  """Placeholders rendered alongside the per-dog health configuration."""  # noqa: E111

  dog_name: str  # noqa: E111
  dog_age: str  # noqa: E111
  dog_weight: str  # noqa: E111
  suggested_ideal_weight: str  # noqa: E111
  suggested_activity: str  # noqa: E111
  medication_enabled: str  # noqa: E111
  bcs_info: str  # noqa: E111
  special_diet_count: str  # noqa: E111
  health_diet_info: str  # noqa: E111


class ModuleSetupSummaryPlaceholders(TypedDict):
  """Placeholders rendered when summarising enabled modules."""  # noqa: E111

  total_dogs: str  # noqa: E111
  gps_dogs: str  # noqa: E111
  health_dogs: str  # noqa: E111
  suggested_performance: str  # noqa: E111
  complexity_info: str  # noqa: E111
  next_step_info: str  # noqa: E111


class ExternalEntitiesPlaceholders(TypedDict):
  """Placeholders rendered while configuring external entities."""  # noqa: E111

  gps_enabled: bool  # noqa: E111
  visitor_enabled: bool  # noqa: E111
  dog_count: int  # noqa: E111


class ExternalEntitySelectorOption(TypedDict):
  """Selectable option exposed while configuring external entities."""  # noqa: E111

  value: str  # noqa: E111
  label: str  # noqa: E111


class ExternalEntityConfig(TypedDict, total=False):
  """External entity mappings selected throughout the setup flow."""  # noqa: E111

  gps_source: str  # noqa: E111
  door_sensor: str  # noqa: E111
  notify_fallback: str  # noqa: E111


class ModuleConfigurationSummary(TypedDict):
  """Aggregated per-module counts used while configuring dashboards."""  # noqa: E111

  total: int  # noqa: E111
  gps_dogs: int  # noqa: E111
  health_dogs: int  # noqa: E111
  feeding_dogs: int  # noqa: E111
  counts: dict[str, int]  # noqa: E111
  description: str  # noqa: E111


class OptionsExportPayload(TypedDict, total=False):
  """Structured payload captured by the options import/export tools."""  # noqa: E111

  version: Literal[1]  # noqa: E111
  options: PawControlOptionsData  # noqa: E111
  dogs: list[DogConfigData]  # noqa: E111
  created_at: str  # noqa: E111


class ReauthHealthSummary(TypedDict, total=False):
  """Normalised health snapshot gathered during reauthentication."""  # noqa: E111

  healthy: bool  # noqa: E111
  issues: list[str]  # noqa: E111
  warnings: list[str]  # noqa: E111
  validated_dogs: int  # noqa: E111
  total_dogs: int  # noqa: E111
  invalid_modules: NotRequired[int]  # noqa: E111
  dogs_count: NotRequired[int]  # noqa: E111
  valid_dogs: NotRequired[int]  # noqa: E111
  profile: NotRequired[str]  # noqa: E111
  estimated_entities: NotRequired[int]  # noqa: E111


class ReauthDataUpdates(TypedDict, total=False):
  """Data fields persisted on the config entry after reauth."""  # noqa: E111

  reauth_timestamp: str  # noqa: E111
  reauth_version: int  # noqa: E111
  health_status: bool  # noqa: E111
  health_validated_dogs: int  # noqa: E111
  health_total_dogs: int  # noqa: E111


class ReauthOptionsUpdates(TypedDict, total=False):
  """Options fields updated after a successful reauth."""  # noqa: E111

  last_reauth: str  # noqa: E111
  reauth_health_issues: list[str]  # noqa: E111
  reauth_health_warnings: list[str]  # noqa: E111
  last_reauth_summary: str  # noqa: E111


class ReauthConfirmInput(TypedDict):
  """Schema-constrained payload submitted by the reauth confirmation form."""  # noqa: E111

  confirm: bool  # noqa: E111


class ReauthPlaceholders(TypedDict):
  """Description placeholders rendered on the reauth confirm form."""  # noqa: E111

  integration_name: str  # noqa: E111
  dogs_count: str  # noqa: E111
  current_profile: str  # noqa: E111
  health_status: str  # noqa: E111


class ReconfigureProfileInput(TypedDict):
  """Schema-constrained payload submitted by the reconfigure form."""  # noqa: E111

  entity_profile: str  # noqa: E111


class ReconfigureCompatibilityResult(TypedDict):
  """Result of validating a profile change against existing dog configs."""  # noqa: E111

  compatible: bool  # noqa: E111
  warnings: list[str]  # noqa: E111


class ReconfigureDataUpdates(TypedDict, total=False):
  """Config entry data persisted after a successful reconfigure."""  # noqa: E111

  entity_profile: str  # noqa: E111
  reconfigure_timestamp: str  # noqa: E111
  reconfigure_version: int  # noqa: E111


class ReconfigureTelemetry(TypedDict, total=False):
  """Structured telemetry recorded for reconfigure operations."""  # noqa: E111

  requested_profile: str  # noqa: E111
  previous_profile: str  # noqa: E111
  dogs_count: int  # noqa: E111
  estimated_entities: int  # noqa: E111
  timestamp: str  # noqa: E111
  version: int  # noqa: E111
  compatibility_warnings: NotRequired[list[str]]  # noqa: E111
  health_summary: NotRequired[ReauthHealthSummary]  # noqa: E111
  valid_dogs: NotRequired[int]  # noqa: E111
  merge_notes: NotRequired[list[str]]  # noqa: E111


class ReconfigureTelemetrySummary(TypedDict, total=False):
  """Condensed view of reconfigure telemetry for diagnostics pipelines."""  # noqa: E111

  timestamp: str  # noqa: E111
  requested_profile: str  # noqa: E111
  previous_profile: str  # noqa: E111
  dogs_count: int  # noqa: E111
  estimated_entities: int  # noqa: E111
  version: int  # noqa: E111
  warnings: list[str]  # noqa: E111
  warning_count: int  # noqa: E111
  healthy: bool  # noqa: E111
  health_issues: list[str]  # noqa: E111
  health_issue_count: int  # noqa: E111
  health_warnings: list[str]  # noqa: E111
  health_warning_count: int  # noqa: E111
  merge_notes: list[str]  # noqa: E111
  merge_note_count: int  # noqa: E111


class ReconfigureOptionsUpdates(TypedDict, total=False):
  """Config entry options updated after a successful reconfigure."""  # noqa: E111

  entity_profile: str  # noqa: E111
  last_reconfigure: str  # noqa: E111
  previous_profile: str  # noqa: E111
  reconfigure_telemetry: ReconfigureTelemetry  # noqa: E111


class ReconfigureFormPlaceholders(TypedDict, total=False):
  """Description placeholders displayed on the reconfigure form."""  # noqa: E111

  current_profile: str  # noqa: E111
  profiles_info: str  # noqa: E111
  dogs_count: str  # noqa: E111
  compatibility_info: str  # noqa: E111
  estimated_entities: str  # noqa: E111
  error_details: str  # noqa: E111
  last_reconfigure: str  # noqa: E111
  reconfigure_requested_profile: str  # noqa: E111
  reconfigure_previous_profile: str  # noqa: E111
  reconfigure_dogs: str  # noqa: E111
  reconfigure_entities: str  # noqa: E111
  reconfigure_health: str  # noqa: E111
  reconfigure_warnings: str  # noqa: E111
  reconfigure_valid_dogs: str  # noqa: E111
  reconfigure_invalid_dogs: str  # noqa: E111
  reconfigure_merge_notes: str  # noqa: E111


class DogValidationResult(TypedDict):
  """Validation result payload for dog configuration forms."""  # noqa: E111

  valid: bool  # noqa: E111
  errors: dict[str, str]  # noqa: E111
  validated_input: NotRequired[DogSetupStepInput]  # noqa: E111


class DogValidationCacheEntry(TypedDict):
  """Cached validation result metadata for config and options flows."""  # noqa: E111

  result: DogValidationResult | DogSetupStepInput | None  # noqa: E111
  cached_at: float  # noqa: E111
  state_signature: NotRequired[str]  # noqa: E111


class DogSetupStepInput(TypedDict):
  """Minimal dog setup fields collected during the primary form."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111
  dog_breed: NotRequired[str | None]  # noqa: E111
  dog_age: NotRequired[int | float | None]  # noqa: E111
  dog_weight: NotRequired[float | int | None]  # noqa: E111
  dog_size: NotRequired[str | None]  # noqa: E111
  weight: NotRequired[float | int | str | None]  # noqa: E111


MODULE_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dog_count": 0,
      "module_summary": "",
      "total_modules": 0,
      "gps_dogs": 0,
      "health_dogs": 0,
    },
  ),
)
ADD_DOG_CAPACITY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dog_count": 0,
      "max_dogs": 0,
      "current_dogs": "",
      "remaining_spots": 0,
    },
  ),
)
DOG_MODULES_SUGGESTION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {"dog_name": "", "dog_size": "", "dog_age": 0},
  ),
)
ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dogs_configured": "",
      "max_dogs": "",
      "discovery_hint": "",
    },
  ),
)
DOG_MODULES_SMART_DEFAULTS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dog_name": "",
      "dogs_configured": "",
      "smart_defaults": "",
    },
  ),
)
ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dogs_configured": "",
      "dogs_list": "",
      "can_add_more": "",
      "max_dogs": "",
      "performance_note": "",
    },
  ),
)
ADD_ANOTHER_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dogs_list": "",
      "dog_count": "",
      "max_dogs": 0,
      "remaining_spots": 0,
      "at_limit": "",
    },
  ),
)
DASHBOARD_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {"dog_count": 0, "dashboard_info": "", "features": ""},
  ),
)
FEEDING_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType({"dog_count": 0, "feeding_summary": ""}),
)
DOG_GPS_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType({"dog_name": ""}),
)
DOG_FEEDING_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dog_name": "",
      "dog_weight": "",
      "suggested_amount": "",
      "portion_info": "",
    },
  ),
)
DOG_HEALTH_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "dog_name": "",
      "dog_age": "",
      "dog_weight": "",
      "suggested_ideal_weight": "",
      "suggested_activity": "",
      "medication_enabled": "",
      "bcs_info": "",
      "special_diet_count": "",
      "health_diet_info": "",
    },
  ),
)
MODULE_SETUP_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "total_dogs": "",
      "gps_dogs": "",
      "health_dogs": "",
      "suggested_performance": "",
      "complexity_info": "",
      "next_step_info": "",
    },
  ),
)
EXTERNAL_ENTITIES_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {"gps_enabled": False, "visitor_enabled": False, "dog_count": 0},
  ),
)
REAUTH_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "integration_name": "",
      "dogs_count": "",
      "current_profile": "",
      "health_status": "",
    },
  ),
)
RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
  ConfigFlowPlaceholders,
  MappingProxyType(
    {
      "current_profile": "",
      "profiles_info": "",
      "dogs_count": "",
      "compatibility_info": "",
      "estimated_entities": "",
      "error_details": "",
      "last_reconfigure": "",
      "reconfigure_requested_profile": "",
      "reconfigure_previous_profile": "",
      "reconfigure_dogs": "",
      "reconfigure_entities": "",
      "reconfigure_health": "",
      "reconfigure_warnings": "",
      "reconfigure_valid_dogs": "",
      "reconfigure_invalid_dogs": "",
      "reconfigure_merge_notes": "",
    },
  ),
)


class InputBooleanCreateServiceData(TypedDict, total=False):
  """Service payload accepted by ``input_boolean.create``."""  # noqa: E111

  name: Required[str]  # noqa: E111
  initial: NotRequired[bool]  # noqa: E111
  icon: NotRequired[str | None]  # noqa: E111


class InputDatetimeCreateServiceData(TypedDict, total=False):
  """Service payload accepted by ``input_datetime.create``."""  # noqa: E111

  name: Required[str]  # noqa: E111
  has_date: Required[bool]  # noqa: E111
  has_time: Required[bool]  # noqa: E111
  initial: NotRequired[str]  # noqa: E111


class InputNumberCreateServiceData(TypedDict, total=False):
  """Service payload accepted by ``input_number.create``."""  # noqa: E111

  name: Required[str]  # noqa: E111
  min: Required[int | float]  # noqa: E111
  max: Required[int | float]  # noqa: E111
  step: Required[int | float]  # noqa: E111
  mode: Required[str]  # noqa: E111
  initial: NotRequired[int | float]  # noqa: E111
  icon: NotRequired[str]  # noqa: E111
  unit_of_measurement: NotRequired[str]  # noqa: E111


class InputSelectCreateServiceData(TypedDict, total=False):
  """Service payload accepted by ``input_select.create``."""  # noqa: E111

  name: Required[str]  # noqa: E111
  options: Required[list[str]]  # noqa: E111
  initial: NotRequired[str]  # noqa: E111
  icon: NotRequired[str]  # noqa: E111


class HelperEntityMetadata(TypedDict, total=False):
  """Metadata captured for helpers created by the helper manager."""  # noqa: E111

  domain: str  # noqa: E111
  name: str  # noqa: E111
  icon: str | None  # noqa: E111
  initial: bool | int | float | str | None  # noqa: E111
  has_date: bool  # noqa: E111
  has_time: bool  # noqa: E111
  options: list[str]  # noqa: E111
  min: int | float  # noqa: E111
  max: int | float  # noqa: E111
  step: int | float  # noqa: E111
  mode: str  # noqa: E111
  unit_of_measurement: str | None  # noqa: E111


type HelperEntityMetadataMapping = dict[str, HelperEntityMetadata]
"""Mapping of entity identifiers to helper metadata payloads."""


type DogHelperAssignments = dict[str, list[str]]
"""Mapping of dog identifiers to the helpers provisioned for them."""


class HelperManagerStats(TypedDict):
  """Summary statistics reported by the helper manager diagnostics."""  # noqa: E111

  helpers: int  # noqa: E111
  dogs: int  # noqa: E111
  managed_entities: int  # noqa: E111


class HelperManagerSnapshot(TypedDict):
  """Snapshot payload describing managed helper assignments."""  # noqa: E111

  per_dog: dict[str, int]  # noqa: E111
  entity_domains: dict[str, int]  # noqa: E111


class HelperManagerGuardMetrics(TypedDict):
  """Aggregated guard telemetry captured by the helper manager."""  # noqa: E111

  executed: int  # noqa: E111
  skipped: int  # noqa: E111
  reasons: dict[str, int]  # noqa: E111
  last_results: ServiceGuardResultHistory  # noqa: E111


EntityFactoryGuardEvent = Literal[
  "expand",
  "contract",
  "stable",
  "disabled",
  "unknown",
]
EntityFactoryGuardStabilityTrend = Literal[
  "improving",
  "steady",
  "regressing",
  "unknown",
]
"""Event labels recorded whenever the entity factory runtime guard recalibrates."""


class EntityFactoryGuardMetrics(TypedDict, total=False):
  """Runtime guard telemetry captured by the entity factory."""  # noqa: E111

  schema_version: Literal[1]  # noqa: E111
  runtime_floor: float  # noqa: E111
  baseline_floor: float  # noqa: E111
  max_floor: float  # noqa: E111
  runtime_floor_delta: float  # noqa: E111
  peak_runtime_floor: float  # noqa: E111
  lowest_runtime_floor: float  # noqa: E111
  last_floor_change: float  # noqa: E111
  last_floor_change_ratio: float  # noqa: E111
  last_actual_duration: float  # noqa: E111
  last_duration_ratio: float  # noqa: E111
  last_event: EntityFactoryGuardEvent  # noqa: E111
  last_updated: str  # noqa: E111
  samples: int  # noqa: E111
  stable_samples: int  # noqa: E111
  expansions: int  # noqa: E111
  contractions: int  # noqa: E111
  last_expansion_duration: float  # noqa: E111
  last_contraction_duration: float  # noqa: E111
  enforce_min_runtime: bool  # noqa: E111
  average_duration: float  # noqa: E111
  max_duration: float  # noqa: E111
  min_duration: float  # noqa: E111
  stable_ratio: float  # noqa: E111
  expansion_ratio: float  # noqa: E111
  contraction_ratio: float  # noqa: E111
  volatility_ratio: float  # noqa: E111
  consecutive_stable_samples: int  # noqa: E111
  longest_stable_run: int  # noqa: E111
  duration_span: float  # noqa: E111
  jitter_ratio: float  # noqa: E111
  recent_durations: list[float]  # noqa: E111
  recent_average_duration: float  # noqa: E111
  recent_max_duration: float  # noqa: E111
  recent_min_duration: float  # noqa: E111
  recent_duration_span: float  # noqa: E111
  recent_jitter_ratio: float  # noqa: E111
  recent_samples: int  # noqa: E111
  recent_events: list[EntityFactoryGuardEvent]  # noqa: E111
  recent_stable_samples: int  # noqa: E111
  recent_stable_ratio: float  # noqa: E111
  stability_trend: EntityFactoryGuardStabilityTrend  # noqa: E111


class EntityFactoryGuardMetricsSnapshot(TypedDict, total=False):
  """Normalised guard telemetry exposed via diagnostics surfaces."""  # noqa: E111

  runtime_floor_ms: float  # noqa: E111
  baseline_floor_ms: float  # noqa: E111
  max_floor_ms: float  # noqa: E111
  runtime_floor_delta_ms: float  # noqa: E111
  peak_runtime_floor_ms: float  # noqa: E111
  lowest_runtime_floor_ms: float  # noqa: E111
  last_floor_change_ms: float  # noqa: E111
  last_actual_duration_ms: float  # noqa: E111
  last_duration_ratio: float  # noqa: E111
  last_floor_change_ratio: float  # noqa: E111
  last_event: EntityFactoryGuardEvent  # noqa: E111
  last_updated: str  # noqa: E111
  samples: int  # noqa: E111
  stable_samples: int  # noqa: E111
  expansions: int  # noqa: E111
  contractions: int  # noqa: E111
  last_expansion_duration_ms: float  # noqa: E111
  last_contraction_duration_ms: float  # noqa: E111
  average_duration_ms: float  # noqa: E111
  max_duration_ms: float  # noqa: E111
  min_duration_ms: float  # noqa: E111
  duration_span_ms: float  # noqa: E111
  jitter_ratio: float  # noqa: E111
  recent_average_duration_ms: float  # noqa: E111
  recent_max_duration_ms: float  # noqa: E111
  recent_min_duration_ms: float  # noqa: E111
  recent_duration_span_ms: float  # noqa: E111
  recent_jitter_ratio: float  # noqa: E111
  stable_ratio: float  # noqa: E111
  expansion_ratio: float  # noqa: E111
  contraction_ratio: float  # noqa: E111
  volatility_ratio: float  # noqa: E111
  consecutive_stable_samples: int  # noqa: E111
  longest_stable_run: int  # noqa: E111
  recent_samples: int  # noqa: E111
  recent_events: list[EntityFactoryGuardEvent]  # noqa: E111
  recent_stable_samples: int  # noqa: E111
  recent_stable_ratio: float  # noqa: E111
  stability_trend: EntityFactoryGuardStabilityTrend  # noqa: E111


class PersonEntityConfigInput(TypedDict, total=False):
  """Configuration payload accepted by :class:`PersonEntityManager`."""  # noqa: E111

  enabled: bool  # noqa: E111
  auto_discovery: bool  # noqa: E111
  discovery_interval: int  # noqa: E111
  cache_ttl: int  # noqa: E111
  include_away_persons: bool  # noqa: E111
  fallback_to_static: bool  # noqa: E111
  static_notification_targets: list[str]  # noqa: E111
  excluded_entities: list[str]  # noqa: E111
  notification_mapping: dict[str, str]  # noqa: E111
  priority_persons: list[str]  # noqa: E111


class PersonEntityCounters(TypedDict):
  """Low-level person manager counters used for cache statistics."""  # noqa: E111

  persons_discovered: int  # noqa: E111
  notifications_targeted: int  # noqa: E111
  cache_hits: int  # noqa: E111
  cache_misses: int  # noqa: E111
  discovery_runs: int  # noqa: E111


class PersonEntityConfigStats(TypedDict):
  """Normalised configuration snapshot for the person entity manager."""  # noqa: E111

  enabled: bool  # noqa: E111
  auto_discovery: bool  # noqa: E111
  discovery_interval: int  # noqa: E111
  include_away_persons: bool  # noqa: E111
  fallback_to_static: bool  # noqa: E111


class PersonEntityStateStats(TypedDict):
  """Runtime discovery metrics surfaced by the person entity manager."""  # noqa: E111

  total_persons: int  # noqa: E111
  home_persons: int  # noqa: E111
  away_persons: int  # noqa: E111
  last_discovery: str  # noqa: E111
  uptime_seconds: float  # noqa: E111


class PersonEntityCacheStats(TypedDict):
  """Cache health metrics for person notification targeting."""  # noqa: E111

  cache_entries: int  # noqa: E111
  hit_rate: float  # noqa: E111


class PersonEntityStats(PersonEntityCounters):
  """Coordinator statistics payload exported by the person entity manager."""  # noqa: E111

  config: PersonEntityConfigStats  # noqa: E111
  current_state: PersonEntityStateStats  # noqa: E111
  cache: PersonEntityCacheStats  # noqa: E111


class PersonNotificationCacheEntry(TypedDict, total=False):
  """Snapshot of cached notification targets for a specific context."""  # noqa: E111

  targets: tuple[str, ...]  # noqa: E111
  generated_at: str | None  # noqa: E111
  age_seconds: float | None  # noqa: E111
  stale: bool  # noqa: E111


class PersonNotificationContext(TypedDict):
  """Aggregated notification context surfaced to diagnostics panels."""  # noqa: E111

  persons_home: int  # noqa: E111
  persons_away: int  # noqa: E111
  home_person_names: list[str]  # noqa: E111
  away_person_names: list[str]  # noqa: E111
  total_persons: int  # noqa: E111
  has_anyone_home: bool  # noqa: E111
  everyone_away: bool  # noqa: E111


class PersonEntityDiscoveryResult(TypedDict):
  """Discovery summary returned by ``PersonEntityManager.async_force_discovery``."""  # noqa: E111

  previous_count: int  # noqa: E111
  current_count: int  # noqa: E111
  persons_added: int  # noqa: E111
  persons_removed: int  # noqa: E111
  home_persons: int  # noqa: E111
  away_persons: int  # noqa: E111
  discovery_time: str  # noqa: E111


class PersonEntityValidationResult(TypedDict):
  """Validation payload produced by ``PersonEntityManager.async_validate_configuration``."""  # noqa: E111, E501

  valid: bool  # noqa: E111
  issues: list[str]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  persons_configured: int  # noqa: E111
  notification_targets_available: int  # noqa: E111


class QueuedNotificationPayload(TypedDict, total=False):
  """Notification entry stored in helper queues before delivery."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  title: Required[str]  # noqa: E111
  message: Required[str]  # noqa: E111
  priority: Required[NotificationPriority]  # noqa: E111
  data: NotRequired[JSONMutableMapping]  # noqa: E111
  timestamp: Required[str]  # noqa: E111


class NotificationQueueStats(TypedDict):
  """Queue utilisation metrics for the notification manager."""  # noqa: E111

  normal_queue_size: int  # noqa: E111
  high_priority_queue_size: int  # noqa: E111
  total_queued: int  # noqa: E111
  max_queue_size: int  # noqa: E111


class PersonEntitySnapshotEntry(TypedDict, total=False):
  """Snapshot payload exported for each discovered person entity."""  # noqa: E111

  entity_id: str  # noqa: E111
  name: str  # noqa: E111
  friendly_name: str  # noqa: E111
  state: str  # noqa: E111
  is_home: bool  # noqa: E111
  last_updated: str  # noqa: E111
  mobile_device_id: str | None  # noqa: E111
  notification_service: str | None  # noqa: E111


class PersonEntityStorageEntry(PersonEntitySnapshotEntry, total=False):
  """Persistent storage payload for discovered person entities."""  # noqa: E111

  attributes: PersonEntityAttributePayload  # noqa: E111


class PersonEntitySnapshot(TypedDict):
  """Coordinator snapshot payload returned by the person entity manager."""  # noqa: E111

  persons: dict[str, PersonEntitySnapshotEntry]  # noqa: E111
  notification_context: PersonNotificationContext  # noqa: E111


class ScriptManagerDogScripts(TypedDict):
  """Snapshot of generated scripts for a single dog."""  # noqa: E111

  count: int  # noqa: E111
  scripts: list[str]  # noqa: E111


class ScriptManagerStats(TypedDict, total=False):
  """Summary metrics surfaced by the script manager cache monitor."""  # noqa: E111

  scripts: int  # noqa: E111
  dogs: int  # noqa: E111
  entry_scripts: int  # noqa: E111
  last_generated_age_seconds: int  # noqa: E111


class ScriptManagerSnapshot(TypedDict, total=False):
  """Detailed coordinator snapshot payload for the script manager."""  # noqa: E111

  created_entities: list[str]  # noqa: E111
  per_dog: dict[str, ScriptManagerDogScripts]  # noqa: E111
  entry_scripts: list[str]  # noqa: E111
  last_generated: str | None  # noqa: E111


DogValidationCache = dict[str, DogValidationCacheEntry]

Timestamp = datetime
"""Type alias for datetime objects used as timestamps.

Standardizes timestamp handling across the integration with proper timezone
awareness through Home Assistant's utility functions.
"""

type ServiceData = JSONMutableMapping
"""Mutable service data payload used when invoking Home Assistant services."""

type ConfigData = JSONMutableMapping
"""Generic mutable configuration payload consumed by PawControl helpers."""


class FeedingScheduleSnapshot(TypedDict, total=False):
  """Schedule configuration associated with the feeding telemetry."""  # noqa: E111

  meals_per_day: int  # noqa: E111
  food_type: str | None  # noqa: E111
  schedule_type: str | None  # noqa: E111


class FeedingEventRecord(TypedDict, total=False):
  """Serialized feeding event stored in manager telemetry."""  # noqa: E111

  time: Required[str]  # noqa: E111
  amount: Required[float]  # noqa: E111
  meal_type: str | None  # noqa: E111
  portion_size: float | None  # noqa: E111
  food_type: str | None  # noqa: E111
  notes: str | None  # noqa: E111
  feeder: str | None  # noqa: E111
  scheduled: Required[bool]  # noqa: E111
  skipped: Required[bool]  # noqa: E111
  with_medication: Required[bool]  # noqa: E111
  medication_name: str | None  # noqa: E111
  medication_dose: str | None  # noqa: E111
  medication_time: str | None  # noqa: E111


class FeedingMissedMeal(TypedDict):
  """Scheduled meal that was not completed within the expected window."""  # noqa: E111

  meal_type: str  # noqa: E111
  scheduled_time: str  # noqa: E111


class FeedingManagerDogSetupPayload(TypedDict, total=False):
  """Normalized dog payload consumed by ``FeedingManager.async_initialize``."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  weight: Required[float | int | str]  # noqa: E111
  dog_name: NotRequired[str | None]  # noqa: E111
  ideal_weight: NotRequired[float | int | str | None]  # noqa: E111
  age_months: NotRequired[int | float | None]  # noqa: E111
  activity_level: NotRequired[str | None]  # noqa: E111
  health_conditions: NotRequired[Iterable[str] | None]  # noqa: E111
  weight_goal: NotRequired[str | None]  # noqa: E111
  special_diet: NotRequired[Iterable[str] | str | None]  # noqa: E111
  feeding_config: NotRequired[JSONMutableMapping | JSONMapping]  # noqa: E111
  breed: NotRequired[str | None]  # noqa: E111
  modules: NotRequired[Mapping[str, bool]]  # noqa: E111


class FeedingDailyStats(TypedDict):
  """Daily feeding counters exposed alongside the active snapshot."""  # noqa: E111

  total_fed_today: float  # noqa: E111
  meals_today: int  # noqa: E111
  remaining_calories: float | None  # noqa: E111


class FeedingEmergencyState(TypedDict, total=False):
  """State metadata tracked while emergency feeding mode is active."""  # noqa: E111

  active: Required[bool]  # noqa: E111
  status: Required[str]  # noqa: E111
  emergency_type: Required[str]  # noqa: E111
  portion_adjustment: Required[float]  # noqa: E111
  duration_days: Required[int]  # noqa: E111
  activated_at: Required[str]  # noqa: E111
  expires_at: str | None  # noqa: E111
  resolved_at: NotRequired[str]  # noqa: E111
  food_type_recommendation: str | None  # noqa: E111


type FeedingHealthStatus = Literal[
  "insufficient_data",
  "emergency",
  "underfed",
  "overfed",
  "on_track",
  "monitoring",
  "unknown",
]
"""Possible health status indicators emitted by the feeding manager."""


class FeedingHealthSummary(TypedDict, total=False):
  """Structured health context calculated for a dog's feeding plan."""  # noqa: E111

  health_aware_enabled: bool  # noqa: E111
  current_weight: float | None  # noqa: E111
  ideal_weight: float | None  # noqa: E111
  life_stage: str | None  # noqa: E111
  activity_level: str | None  # noqa: E111
  body_condition_score: float | int | None  # noqa: E111
  daily_calorie_requirement: float | None  # noqa: E111
  calories_per_gram: float  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  special_diet: list[str]  # noqa: E111
  weight_goal: str | None  # noqa: E111
  diet_validation_applied: bool  # noqa: E111


class FeedingDietValidationSummary(TypedDict, total=False):
  """Summary describing diet validation adjustments and conflicts."""  # noqa: E111

  has_adjustments: bool  # noqa: E111
  adjustment_info: str  # noqa: E111
  conflict_count: int  # noqa: E111
  warning_count: int  # noqa: E111
  vet_consultation_recommended: bool  # noqa: E111
  vet_consultation_state: str  # noqa: E111
  consultation_urgency: str  # noqa: E111
  total_diets: int  # noqa: E111
  diet_validation_adjustment: float  # noqa: E111
  percentage_adjustment: float  # noqa: E111
  adjustment_direction: str  # noqa: E111
  safety_factor: str  # noqa: E111
  compatibility_score: int  # noqa: E111
  compatibility_level: str  # noqa: E111
  conflicts: NotRequired[list[JSONMapping]]  # noqa: E111
  warnings: NotRequired[list[JSONMapping]]  # noqa: E111


class FeedingSnapshot(TypedDict, total=False):
  """Primary feeding telemetry snapshot returned by the manager."""  # noqa: E111

  status: Required[Literal["ready", "no_data"]]  # noqa: E111
  last_feeding: str | None  # noqa: E111
  last_feeding_type: str | None  # noqa: E111
  last_feeding_hours: float | None  # noqa: E111
  last_feeding_amount: float | None  # noqa: E111
  feedings_today: Required[dict[str, int]]  # noqa: E111
  total_feedings_today: Required[int]  # noqa: E111
  daily_amount_consumed: Required[float]  # noqa: E111
  daily_amount_target: Required[float]  # noqa: E111
  daily_target: Required[float]  # noqa: E111
  daily_amount_percentage: Required[int]  # noqa: E111
  schedule_adherence: Required[int]  # noqa: E111
  next_feeding: str | None  # noqa: E111
  next_feeding_type: str | None  # noqa: E111
  missed_feedings: Required[list[FeedingMissedMeal]]  # noqa: E111
  feedings: Required[list[FeedingEventRecord]]  # noqa: E111
  feeding_schedule: NotRequired[list[JSONMapping]]  # noqa: E111
  daily_portions: NotRequired[int]  # noqa: E111
  daily_stats: Required[FeedingDailyStats]  # noqa: E111
  calories_per_gram: NotRequired[float]  # noqa: E111
  daily_calorie_target: NotRequired[float]  # noqa: E111
  total_calories_today: NotRequired[float]  # noqa: E111
  calorie_goal_progress: NotRequired[float]  # noqa: E111
  portion_adjustment_factor: NotRequired[float]  # noqa: E111
  diet_validation_summary: NotRequired[FeedingDietValidationSummary | None]  # noqa: E111
  health_conditions: NotRequired[list[str]]  # noqa: E111
  daily_activity_level: NotRequired[str | None]  # noqa: E111
  health_summary: NotRequired[FeedingHealthSummary]  # noqa: E111
  medication_with_meals: Required[bool]  # noqa: E111
  health_aware_feeding: Required[bool]  # noqa: E111
  weight_goal: Required[str | None]  # noqa: E111
  weight_goal_progress: NotRequired[float]  # noqa: E111
  emergency_mode: Required[FeedingEmergencyState | None]  # noqa: E111
  health_emergency: Required[bool]  # noqa: E111
  health_feeding_status: Required[FeedingHealthStatus]  # noqa: E111
  config: NotRequired[FeedingScheduleSnapshot]  # noqa: E111


class FeedingStatisticsSnapshot(TypedDict):
  """Historical feeding statistics exported by the manager."""  # noqa: E111

  period_days: int  # noqa: E111
  total_feedings: int  # noqa: E111
  average_daily_feedings: float  # noqa: E111
  average_daily_amount: float  # noqa: E111
  most_common_meal: str | None  # noqa: E111
  schedule_adherence: int  # noqa: E111
  daily_target_met_percentage: int  # noqa: E111


class FeedingModulePayload(FeedingSnapshot, total=False):
  """Typed payload exposed by the feeding coordinator module."""  # noqa: E111

  message: NotRequired[str]  # noqa: E111


class FeedingModuleTelemetry(FeedingModulePayload):
  """Extended feeding module telemetry used by diagnostics consumers."""  # noqa: E111


type FeedingSnapshotCache = dict[str, FeedingSnapshot]
"""Cache of per-dog feeding snapshots keyed by dog identifier."""


type FeedingStatisticsCache = dict[str, FeedingStatisticsSnapshot]
"""Cache of historical feeding statistics keyed by cache key."""


class GPSRoutePoint(TypedDict, total=False):
  """Individual GPS sample collected during live tracking."""  # noqa: E111

  latitude: Required[float]  # noqa: E111
  longitude: Required[float]  # noqa: E111
  timestamp: Required[datetime | str]  # noqa: E111
  accuracy: NotRequired[float | int]  # noqa: E111
  altitude: float | None  # noqa: E111
  speed: float | None  # noqa: E111
  heading: float | None  # noqa: E111


class GPSLocationSample(TypedDict):
  """Validated GPS location sample with prioritisation metadata."""  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  accuracy: int  # noqa: E111
  timestamp: datetime  # noqa: E111
  source: str  # noqa: E111
  priority: int  # noqa: E111
  altitude: float | None  # noqa: E111
  speed: float | None  # noqa: E111
  heading: float | None  # noqa: E111


class GPSRouteSnapshot(TypedDict, total=False):
  """Snapshot of an active or historical GPS route."""  # noqa: E111

  id: Required[str]  # noqa: E111
  name: Required[str]  # noqa: E111
  active: Required[bool]  # noqa: E111
  start_time: Required[datetime | str]  # noqa: E111
  end_time: datetime | str | None  # noqa: E111
  duration: float | int | None  # noqa: E111
  distance: float | None  # noqa: E111
  points: list[GPSRoutePoint]  # noqa: E111
  point_count: int  # noqa: E111
  last_point_time: datetime | str | None  # noqa: E111


class GPSCompletedRouteSnapshot(GPSRouteSnapshot, total=False):
  """Snapshot returned when a GPS route recording completes."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111


class GeofenceZoneMetadata(TypedDict, total=False):
  """Additional attributes persisted alongside configured geofence zones."""  # noqa: E111

  auto_created: bool  # noqa: E111
  color: str | None  # noqa: E111
  created_by: str | None  # noqa: E111
  notes: str | None  # noqa: E111
  tags: list[str]  # noqa: E111


class GeofenceZoneStoragePayload(TypedDict, total=False):
  """Serialized representation of a stored :class:`GeofenceZone`."""  # noqa: E111

  id: Required[str]  # noqa: E111
  name: Required[str]  # noqa: E111
  type: Required[str]  # noqa: E111
  latitude: Required[float]  # noqa: E111
  longitude: Required[float]  # noqa: E111
  radius: Required[float]  # noqa: E111
  enabled: bool  # noqa: E111
  alerts_enabled: bool  # noqa: E111
  description: str  # noqa: E111
  created_at: str  # noqa: E111
  updated_at: str  # noqa: E111
  metadata: GeofenceZoneMetadata  # noqa: E111


class GeofenceStoragePayload(TypedDict, total=False):
  """Top-level storage payload tracked by :class:`PawControlGeofencing`."""  # noqa: E111

  zones: dict[str, GeofenceZoneStoragePayload]  # noqa: E111
  last_updated: str  # noqa: E111


class GeofenceNotificationPayload(TypedDict, total=False):
  """Notification payload emitted for geofence enter/exit events."""  # noqa: E111

  zone_id: Required[str]  # noqa: E111
  zone_name: Required[str]  # noqa: E111
  zone_type: Required[str]  # noqa: E111
  event_type: Required[str]  # noqa: E111
  radius: Required[float]  # noqa: E111
  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  distance_from_center_m: float  # noqa: E111
  accuracy: float | int | None  # noqa: E111


class GPSGeofenceLocationSnapshot(TypedDict, total=False):
  """Current GPS location exported in geofence status snapshots."""  # noqa: E111

  latitude: Required[float]  # noqa: E111
  longitude: Required[float]  # noqa: E111
  timestamp: Required[str]  # noqa: E111
  accuracy: float | int | None  # noqa: E111


class GPSGeofenceZoneStatusSnapshot(TypedDict):
  """Status details for an individual configured geofence zone."""  # noqa: E111

  inside: bool  # noqa: E111
  zone_type: str  # noqa: E111
  radius_meters: float  # noqa: E111
  distance_to_center: float  # noqa: E111
  notifications_enabled: bool  # noqa: E111


class GPSGeofenceStatusSnapshot(TypedDict):
  """Full geofence snapshot surfaced to diagnostics and dashboards."""  # noqa: E111

  dog_id: str  # noqa: E111
  zones_configured: int  # noqa: E111
  current_location: GPSGeofenceLocationSnapshot | None  # noqa: E111
  zone_status: dict[str, GPSGeofenceZoneStatusSnapshot]  # noqa: E111
  safe_zone_breaches: int  # noqa: E111
  last_update: str | None  # noqa: E111


class GPSTrackingConfigInput(TypedDict, total=False):
  """Mutable configuration payload accepted by the GPS manager."""  # noqa: E111

  enabled: bool  # noqa: E111
  auto_start_walk: bool  # noqa: E111
  track_route: bool  # noqa: E111
  safety_alerts: bool  # noqa: E111
  geofence_notifications: bool  # noqa: E111
  auto_detect_home: bool  # noqa: E111
  gps_accuracy_threshold: float | int  # noqa: E111
  update_interval_seconds: int | float  # noqa: E111
  min_distance_for_point: float | int  # noqa: E111
  route_smoothing: bool  # noqa: E111
  configured_at: datetime | str | None  # noqa: E111


class GeofenceNotificationCoordinates(TypedDict):
  """Latitude and longitude payload bundled with geofence notifications."""  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111


class GeofenceEventPayload(TypedDict, total=False):
  """Event data fired on the Home Assistant event bus for geofence changes."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  zone: Required[str]  # noqa: E111
  zone_type: Required[str]  # noqa: E111
  event: Required[str]  # noqa: E111
  distance_meters: Required[float]  # noqa: E111
  timestamp: Required[str]  # noqa: E111
  latitude: Required[float]  # noqa: E111
  longitude: Required[float]  # noqa: E111
  duration_seconds: int  # noqa: E111


class GeofenceNotificationData(TypedDict, total=False):
  """Structured data payload passed to notification templates for geofences."""  # noqa: E111

  zone: Required[str]  # noqa: E111
  zone_type: Required[str]  # noqa: E111
  event: Required[str]  # noqa: E111
  distance_meters: Required[float]  # noqa: E111
  coordinates: Required[GeofenceNotificationCoordinates]  # noqa: E111
  duration_seconds: int  # noqa: E111


class GPSTelemetryPayload(TypedDict, total=False):
  """Live GPS telemetry exposed to coordinators and diagnostics."""  # noqa: E111

  latitude: float | None  # noqa: E111
  longitude: float | None  # noqa: E111
  accuracy: float | int | None  # noqa: E111
  altitude: float | None  # noqa: E111
  speed: float | None  # noqa: E111
  heading: float | None  # noqa: E111
  source: str | None  # noqa: E111
  last_seen: datetime | str | None  # noqa: E111
  last_update: str | None  # noqa: E111
  battery: float | int | None  # noqa: E111
  zone: str | None  # noqa: E111
  satellites: int | None  # noqa: E111
  distance_from_home: float | None  # noqa: E111
  geofence_status: JSONMutableMapping | None  # noqa: E111
  walk_info: JSONMutableMapping | None  # noqa: E111
  current_route: GPSRouteSnapshot | None  # noqa: E111
  active_route: GPSRouteSnapshot | JSONMutableMapping | None  # noqa: E111


class GPSModulePayload(GPSTelemetryPayload, total=False):
  """GPS metrics surfaced through the GPS adapter."""  # noqa: E111

  status: Required[str]  # noqa: E111


class GPSManagerStats(TypedDict):
  """Counters maintained by :class:`GPSGeofenceManager` for telemetry."""  # noqa: E111

  gps_points_processed: int  # noqa: E111
  routes_completed: int  # noqa: E111
  geofence_events: int  # noqa: E111
  last_update: datetime  # noqa: E111


class GPSManagerStatisticsSnapshot(GPSManagerStats):
  """Aggregated GPS statistics exposed via coordinator diagnostics."""  # noqa: E111

  dogs_configured: int  # noqa: E111
  active_tracking_sessions: int  # noqa: E111
  total_routes_stored: int  # noqa: E111
  geofence_zones_configured: int  # noqa: E111


class GPSTrackerRouteAttributes(TypedDict, total=False):
  """Route metadata surfaced as device tracker state attributes."""  # noqa: E111

  route_active: bool  # noqa: E111
  route_points: int  # noqa: E111
  route_distance: float | None  # noqa: E111
  route_duration: float | int | None  # noqa: E111
  route_start_time: str | None  # noqa: E111


class GPSTrackerGeofenceAttributes(TypedDict, total=False):
  """Geofence attributes exposed on the GPS tracker entity."""  # noqa: E111

  in_safe_zone: bool  # noqa: E111
  zone_name: str | None  # noqa: E111
  zone_distance: float | None  # noqa: E111


class GPSTrackerWalkAttributes(TypedDict, total=False):
  """Walk linkage metadata exposed on the GPS tracker entity."""  # noqa: E111

  walk_active: bool  # noqa: E111
  walk_id: str | None  # noqa: E111
  walk_start_time: str | None  # noqa: E111


class GPSTrackerExtraAttributes(
  GPSTrackerRouteAttributes,
  GPSTrackerGeofenceAttributes,
  GPSTrackerWalkAttributes,
  total=False,
):
  """Complete set of extra attributes returned by the GPS tracker entity."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111
  tracker_type: Required[str]  # noqa: E111
  altitude: float | None  # noqa: E111
  speed: float | None  # noqa: E111
  heading: float | None  # noqa: E111
  satellites: int | None  # noqa: E111
  location_source: str  # noqa: E111
  last_seen: str | None  # noqa: E111
  distance_from_home: float | None  # noqa: E111


def _normalise_route_point(point: Mapping[str, object]) -> GPSRoutePoint | None:
  """Return a JSON-safe GPS route point."""  # noqa: E111

  latitude = _coerce_float_value(point.get("latitude"))  # noqa: E111
  longitude = _coerce_float_value(point.get("longitude"))  # noqa: E111
  if latitude is None or longitude is None:  # noqa: E111
    return None

  timestamp = (  # noqa: E111
    _coerce_iso_timestamp(point.get("timestamp")) or dt_util.utcnow().isoformat()
  )
  payload: GPSRoutePoint = {  # noqa: E111
    "latitude": latitude,
    "longitude": longitude,
    "timestamp": timestamp,
  }

  altitude = _coerce_float_value(point.get("altitude"))  # noqa: E111
  if altitude is not None:  # noqa: E111
    payload["altitude"] = altitude

  accuracy = _coerce_float_value(point.get("accuracy"))  # noqa: E111
  if accuracy is not None:  # noqa: E111
    payload["accuracy"] = accuracy

  speed = _coerce_float_value(point.get("speed"))  # noqa: E111
  if speed is not None:  # noqa: E111
    payload["speed"] = speed

  heading = _coerce_float_value(point.get("heading"))  # noqa: E111
  if heading is not None:  # noqa: E111
    payload["heading"] = heading

  return payload  # noqa: E111


def ensure_gps_route_snapshot(
  payload: Mapping[str, JSONValue] | JSONMutableMapping | None,
) -> GPSRouteSnapshot | None:
  """Normalise a route snapshot mapping into a JSON-safe structure."""  # noqa: E111

  if payload is None or not isinstance(payload, Mapping):  # noqa: E111
    return None

  base = ensure_json_mapping(payload)  # noqa: E111
  points_raw = base.get("points")  # noqa: E111
  points: list[GPSRoutePoint] = []  # noqa: E111
  if isinstance(points_raw, Sequence) and not isinstance(points_raw, str | bytes):  # noqa: E111
    for point in points_raw:
      if isinstance(point, Mapping):  # noqa: E111
        normalised = _normalise_route_point(point)
        if normalised is not None:
          points.append(normalised)  # noqa: E111
      else:  # noqa: E111
        # Skip non-mapping points to avoid corrupting the route data.
        pass

  start_time = (  # noqa: E111
    _coerce_iso_timestamp(base.get("start_time")) or dt_util.utcnow().isoformat()
  )
  end_time = _coerce_iso_timestamp(base.get("end_time"))  # noqa: E111
  last_point_time = _coerce_iso_timestamp(base.get("last_point_time"))  # noqa: E111

  snapshot: GPSRouteSnapshot = {  # noqa: E111
    "active": bool(base.get("active", False)),
    "id": str(base.get("id") or ""),
    "name": str(base.get("name") or base.get("id") or "GPS Route"),
    "start_time": start_time,
    "points": points,
    "point_count": len(points),
  }

  if end_time is not None:  # noqa: E111
    snapshot["end_time"] = end_time
  if last_point_time is not None:  # noqa: E111
    snapshot["last_point_time"] = last_point_time

  distance = _coerce_float_value(base.get("distance"))  # noqa: E111
  if distance is not None:  # noqa: E111
    snapshot["distance"] = distance

  duration = _coerce_float_value(base.get("duration"))  # noqa: E111
  if duration is not None:  # noqa: E111
    snapshot["duration"] = duration

  return snapshot  # noqa: E111


def ensure_gps_payload(
  payload: Mapping[str, object] | JSONMutableMapping | None,
) -> GPSModulePayload | None:
  """Return a normalised :class:`GPSModulePayload`."""  # noqa: E111

  if payload is None or not isinstance(payload, Mapping):  # noqa: E111
    return None

  gps_payload = cast(GPSModulePayload, ensure_json_mapping(payload))  # noqa: E111
  if not gps_payload:  # noqa: E111
    return None
  last_seen = _coerce_iso_timestamp(gps_payload.get("last_seen"))  # noqa: E111
  if last_seen is not None or "last_seen" in gps_payload:  # noqa: E111
    gps_payload["last_seen"] = last_seen

  last_update = _coerce_iso_timestamp(gps_payload.get("last_update"))  # noqa: E111
  if last_update is not None or "last_update" in gps_payload:  # noqa: E111
    gps_payload["last_update"] = last_update

  for payload_field in (  # noqa: E111
    "latitude",
    "longitude",
    "accuracy",
    "altitude",
    "speed",
    "heading",
    "battery",
    "distance_from_home",
  ):
    if payload_field not in gps_payload:
      continue  # noqa: E111
    gps_payload[payload_field] = _coerce_float_value(
      gps_payload.get(payload_field),
    )

  satellites = gps_payload.get("satellites")  # noqa: E111
  if satellites is None and "satellites" in gps_payload:  # noqa: E111
    gps_payload["satellites"] = None
  elif satellites is not None:  # noqa: E111
    try:
      gps_payload["satellites"] = int(satellites)  # noqa: E111
    except ValueError:
      _LOGGER.warning(  # noqa: E111
        "Invalid satellites value %s for GPS payload; setting to None",
        satellites,
      )
      gps_payload["satellites"] = None  # noqa: E111
    except TypeError:
      _LOGGER.warning(  # noqa: E111
        "Invalid satellites value %s for GPS payload; setting to None",
        satellites,
      )
      gps_payload["satellites"] = None  # noqa: E111

  current_route_snapshot = ensure_gps_route_snapshot(  # noqa: E111
    cast(
      Mapping[str, JSONValue] | JSONMutableMapping | None,
      payload.get("current_route"),
    ),
  )
  if current_route_snapshot is not None:  # noqa: E111
    gps_payload["current_route"] = current_route_snapshot
  elif "current_route" in gps_payload:  # noqa: E111
    gps_payload.pop("current_route", None)

  route_active_payload = payload.get("active_route")  # noqa: E111
  if isinstance(route_active_payload, Mapping):  # noqa: E111
    active_route = ensure_gps_route_snapshot(
      cast(Mapping[str, JSONValue], route_active_payload),
    )
    if active_route is not None:
      gps_payload["active_route"] = active_route  # noqa: E111

  status = payload.get("status")  # noqa: E111
  gps_payload["status"] = str(status) if status is not None else "unknown"  # noqa: E111

  return gps_payload  # noqa: E111


class GPSRouteExportJSONPoint(TypedDict, total=False):
  """GPS point exported in JSON route downloads."""  # noqa: E111

  latitude: Required[float]  # noqa: E111
  longitude: Required[float]  # noqa: E111
  timestamp: Required[str]  # noqa: E111
  altitude: float | None  # noqa: E111
  accuracy: float | int | None  # noqa: E111
  source: str | None  # noqa: E111


class GPSRouteExportJSONEvent(TypedDict, total=False):
  """Geofence event metadata included in JSON route exports."""  # noqa: E111

  event_type: Required[str]  # noqa: E111
  zone_name: Required[str]  # noqa: E111
  timestamp: Required[str]  # noqa: E111
  distance_from_center: float | None  # noqa: E111
  severity: str | None  # noqa: E111


class GPSRouteExportJSONRoute(TypedDict, total=False):
  """Route details serialised in JSON exports."""  # noqa: E111

  start_time: Required[str]  # noqa: E111
  end_time: str | None  # noqa: E111
  duration_minutes: float | None  # noqa: E111
  distance_km: float | None  # noqa: E111
  avg_speed_kmh: float | None  # noqa: E111
  route_quality: str  # noqa: E111
  gps_points: list[GPSRouteExportJSONPoint]  # noqa: E111
  geofence_events: list[GPSRouteExportJSONEvent]  # noqa: E111


class GPSRouteExportJSONContent(TypedDict):
  """Top-level JSON payload returned when exporting GPS routes."""  # noqa: E111

  dog_id: str  # noqa: E111
  export_timestamp: str  # noqa: E111
  routes: list[GPSRouteExportJSONRoute]  # noqa: E111


class GPSRouteExportBasePayload(TypedDict):
  """Base fields shared across all GPS route export payloads."""  # noqa: E111

  filename: str  # noqa: E111
  routes_count: int  # noqa: E111


class GPSRouteExportGPXPayload(GPSRouteExportBasePayload):
  """Payload returned when exporting GPS routes in GPX format."""  # noqa: E111

  format: Literal["gpx"]  # noqa: E111
  content: str  # noqa: E111


class GPSRouteExportCSVPayload(GPSRouteExportBasePayload):
  """Payload returned when exporting GPS routes in CSV format."""  # noqa: E111

  format: Literal["csv"]  # noqa: E111
  content: str  # noqa: E111


class GPSRouteExportJSONPayload(GPSRouteExportBasePayload):
  """Payload returned when exporting GPS routes in JSON format."""  # noqa: E111

  format: Literal["json"]  # noqa: E111
  content: GPSRouteExportJSONContent  # noqa: E111


type GPSRouteExportPayload = (
  GPSRouteExportGPXPayload | GPSRouteExportCSVPayload | GPSRouteExportJSONPayload
)


TPoint = TypeVar("TPoint", bound=GPSRoutePoint)


@dataclass(slots=True)
class GPSRouteBuffer[TPoint: GPSRoutePoint]:
  """Typed buffer that stores route samples for GPS tracking."""  # noqa: E111

  _points: list[TPoint] = field(default_factory=list)  # noqa: E111

  def append(self, point: TPoint) -> None:  # noqa: E111
    """Append a new GPS sample to the buffer."""

    self._points.append(point)

  def prune(self, *, cutoff: datetime, max_points: int) -> None:  # noqa: E111
    """Drop samples older than ``cutoff`` while enforcing ``max_points``."""

    filtered_points: list[TPoint] = []
    for point in self._points:
      timestamp = point.get("timestamp")  # noqa: E111
      if isinstance(timestamp, datetime) and timestamp > cutoff:  # noqa: E111
        filtered_points.append(point)

    self._points = filtered_points
    if len(self._points) > max_points:
      self._points = self._points[-max_points:]  # noqa: E111

  def snapshot(self, *, limit: int | None = None) -> list[TPoint]:  # noqa: E111
    """Return a shallow copy of the most recent samples."""

    if limit is None:
      return list(self._points)  # noqa: E111
    if limit <= 0:
      return []  # noqa: E111
    return list(self._points[-limit:])

  def view(self) -> Sequence[TPoint]:  # noqa: E111
    """Return a read-only view over the buffered route samples."""

    return self._points

  def clear(self) -> None:  # noqa: E111
    """Remove all buffered samples."""

    self._points.clear()

  def __len__(self) -> int:  # noqa: E111
    """Return the number of buffered samples."""

    return len(self._points)

  def __bool__(self) -> bool:  # pragma: no cover - delegated to __len__  # noqa: E111
    """Return ``True`` when the buffer contains samples."""

    return bool(self._points)

  def __iter__(self) -> Iterator[TPoint]:  # noqa: E111
    """Iterate over buffered samples in chronological order."""

    return iter(self._points)


class GeofencingModulePayload(TypedDict, total=False):
  """Structured geofence payload for coordinator consumers."""  # noqa: E111

  status: Required[str]  # noqa: E111
  zones_configured: int  # noqa: E111
  zone_status: dict[str, GPSGeofenceZoneStatusSnapshot]  # noqa: E111
  current_location: GPSGeofenceLocationSnapshot | None  # noqa: E111
  safe_zone_breaches: int  # noqa: E111
  last_update: str | None  # noqa: E111
  message: NotRequired[str]  # noqa: E111
  error: NotRequired[str]  # noqa: E111


class HealthModulePayload(TypedDict, total=False):
  """Combined health telemetry exposed by the health adapter."""  # noqa: E111

  status: Required[str]  # noqa: E111
  weight: float | None  # noqa: E111
  ideal_weight: float | None  # noqa: E111
  last_vet_visit: str | None  # noqa: E111
  medications: HealthMedicationQueue  # noqa: E111
  health_alerts: HealthAlertList  # noqa: E111
  life_stage: str | None  # noqa: E111
  activity_level: str | None  # noqa: E111
  body_condition_score: float | int | None  # noqa: E111
  health_conditions: list[str]  # noqa: E111
  emergency: JSONMutableMapping  # noqa: E111
  medication: JSONMutableMapping  # noqa: E111
  health_status: str | None  # noqa: E111
  daily_calorie_target: float | None  # noqa: E111
  total_calories_today: float | None  # noqa: E111
  weight_goal_progress: Any  # noqa: E111
  weight_goal: Any  # noqa: E111


class WeatherConditionsPayload(TypedDict, total=False):
  """Current weather snapshot consumed by dashboard entities."""  # noqa: E111

  temperature_c: float | None  # noqa: E111
  humidity_percent: float | None  # noqa: E111
  uv_index: float | None  # noqa: E111
  wind_speed_kmh: float | None  # noqa: E111
  condition: str | None  # noqa: E111
  last_updated: str  # noqa: E111


class WeatherAlertPayload(TypedDict, total=False):
  """Serialized weather alert returned by the adapter."""  # noqa: E111

  type: Required[str]  # noqa: E111
  severity: Required[str]  # noqa: E111
  title: Required[str]  # noqa: E111
  message: Required[str]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  duration_hours: int | None  # noqa: E111
  affected_breeds: list[str]  # noqa: E111
  age_considerations: list[str]  # noqa: E111


type WeatherModuleStatus = Literal["ready", "disabled", "error"]


class WeatherModulePayload(TypedDict, total=False):
  """Weather-driven health insights returned by the weather adapter."""  # noqa: E111

  status: Required[WeatherModuleStatus]  # noqa: E111
  health_score: float | int | None  # noqa: E111
  alerts: list[WeatherAlertPayload]  # noqa: E111
  recommendations: list[str]  # noqa: E111
  conditions: WeatherConditionsPayload  # noqa: E111
  message: NotRequired[str]  # noqa: E111


class GardenFavoriteActivity(TypedDict):
  """Tracked activity that contributes to garden statistics."""  # noqa: E111

  activity: str  # noqa: E111
  count: int  # noqa: E111


class GardenWeeklySummary(TypedDict, total=False):
  """Rolling weekly garden performance summary."""  # noqa: E111

  session_count: int  # noqa: E111
  total_time_minutes: float  # noqa: E111
  poop_events: int  # noqa: E111
  average_duration: float  # noqa: E111
  updated: str  # noqa: E111


class GardenStatsSnapshot(TypedDict, total=False):
  """Structured garden statistics payload."""  # noqa: E111

  total_sessions: int  # noqa: E111
  total_time_minutes: float  # noqa: E111
  total_poop_count: int  # noqa: E111
  average_session_duration: float  # noqa: E111
  most_active_time_of_day: str | None  # noqa: E111
  favorite_activities: list[GardenFavoriteActivity]  # noqa: E111
  weekly_summary: GardenWeeklySummary  # noqa: E111
  last_garden_visit: str | None  # noqa: E111
  total_activities: int  # noqa: E111


class GardenConfirmationSnapshot(TypedDict, total=False):
  """Metadata describing pending garden confirmations."""  # noqa: E111

  session_id: str | None  # noqa: E111
  created: str | None  # noqa: E111
  expires: str | None  # noqa: E111


class GardenWeatherSummary(TypedDict, total=False):
  """Summary of weather observations collected during garden sessions."""  # noqa: E111

  conditions: list[str]  # noqa: E111
  average_temperature: float | None  # noqa: E111


class GardenSessionSnapshot(TypedDict, total=False):
  """Serializable snapshot describing a garden session."""  # noqa: E111

  session_id: str  # noqa: E111
  start_time: str  # noqa: E111
  end_time: str | None  # noqa: E111
  duration_minutes: float  # noqa: E111
  activity_count: int  # noqa: E111
  poop_count: int  # noqa: E111
  status: str  # noqa: E111
  weather_conditions: str | None  # noqa: E111
  temperature: float | None  # noqa: E111
  notes: str | None  # noqa: E111


class GardenActiveSessionSnapshot(TypedDict, total=False):
  """Runtime view of an active garden session."""  # noqa: E111

  session_id: str  # noqa: E111
  start_time: str  # noqa: E111
  duration_minutes: float  # noqa: E111
  activity_count: int  # noqa: E111
  poop_count: int  # noqa: E111


class GardenModulePayload(TypedDict, total=False):
  """Garden telemetry surfaced to coordinators."""  # noqa: E111

  status: Required[str]  # noqa: E111
  message: NotRequired[str]  # noqa: E111
  sessions_today: int  # noqa: E111
  time_today_minutes: float  # noqa: E111
  poop_today: int  # noqa: E111
  activities_today: int  # noqa: E111
  activities_total: int  # noqa: E111
  active_session: GardenActiveSessionSnapshot | None  # noqa: E111
  last_session: GardenSessionSnapshot | None  # noqa: E111
  hours_since_last_session: float | None  # noqa: E111
  stats: GardenStatsSnapshot  # noqa: E111
  pending_confirmations: list[GardenConfirmationSnapshot]  # noqa: E111
  weather_summary: GardenWeatherSummary | None  # noqa: E111


class WalkRoutePoint(TypedDict, total=False):
  """Normalised GPS sample recorded during a walk."""  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  timestamp: str  # noqa: E111
  accuracy: NotRequired[float | None]  # noqa: E111
  altitude: NotRequired[float | None]  # noqa: E111
  speed: NotRequired[float | None]  # noqa: E111
  heading: NotRequired[float | None]  # noqa: E111
  source: NotRequired[str | None]  # noqa: E111
  battery_level: NotRequired[int | None]  # noqa: E111
  signal_strength: NotRequired[int | None]  # noqa: E111


class GPSCacheStats(TypedDict):
  """Statistics tracked by the GPS cache for diagnostics."""  # noqa: E111

  hits: int  # noqa: E111
  misses: int  # noqa: E111
  hit_rate: float  # noqa: E111
  cached_locations: int  # noqa: E111
  distance_cache_entries: int  # noqa: E111
  evictions: int  # noqa: E111
  max_size: int  # noqa: E111


class GPSCacheDiagnosticsMetadata(TypedDict):
  """Metadata describing cache configuration and contents."""  # noqa: E111

  cached_dogs: list[str]  # noqa: E111
  max_size: int  # noqa: E111
  distance_cache_entries: int  # noqa: E111
  evictions: int  # noqa: E111


class GPSCacheSnapshot(TypedDict):
  """Combined telemetry exported by the GPS cache."""  # noqa: E111

  stats: GPSCacheStats  # noqa: E111
  metadata: GPSCacheDiagnosticsMetadata  # noqa: E111


class WalkLocationSnapshot(TypedDict, total=False):
  """Snapshot describing a recorded walk location."""  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  timestamp: str  # noqa: E111
  accuracy: NotRequired[float | None]  # noqa: E111
  altitude: NotRequired[float | None]  # noqa: E111
  source: NotRequired[str | None]  # noqa: E111
  battery_level: NotRequired[int | None]  # noqa: E111
  signal_strength: NotRequired[int | None]  # noqa: E111


class WalkPerformanceCounters(TypedDict):
  """Performance counters captured by the walk manager."""  # noqa: E111

  gps_updates: int  # noqa: E111
  distance_calculations: int  # noqa: E111
  cache_hits: int  # noqa: E111
  cache_misses: int  # noqa: E111
  memory_cleanups: int  # noqa: E111
  gpx_exports: int  # noqa: E111
  export_errors: int  # noqa: E111


class WalkSessionSnapshot(TypedDict, total=False):
  """Structured walk session metadata used for diagnostics and history."""  # noqa: E111

  walk_id: str  # noqa: E111
  dog_id: str  # noqa: E111
  walk_type: str  # noqa: E111
  start_time: str  # noqa: E111
  walker: str | None  # noqa: E111
  leash_used: bool  # noqa: E111
  weather: str | None  # noqa: E111
  track_route: bool  # noqa: E111
  safety_alerts: bool  # noqa: E111
  start_location: WalkLocationSnapshot | None  # noqa: E111
  end_time: str | None  # noqa: E111
  duration: float | None  # noqa: E111
  distance: float | None  # noqa: E111
  end_location: WalkLocationSnapshot | None  # noqa: E111
  status: str  # noqa: E111
  average_speed: float | None  # noqa: E111
  max_speed: float | None  # noqa: E111
  calories_burned: float | None  # noqa: E111
  elevation_gain: float | None  # noqa: E111
  path: list[WalkRoutePoint]  # noqa: E111
  notes: str | None  # noqa: E111
  dog_weight_kg: float | None  # noqa: E111
  detection_confidence: float | None  # noqa: E111
  door_sensor: str | None  # noqa: E111
  detection_metadata: JSONMutableMapping | None  # noqa: E111
  save_route: bool | None  # noqa: E111
  path_optimization_applied: bool | None  # noqa: E111
  current_distance: float | None  # noqa: E111
  current_duration: float | None  # noqa: E111
  elapsed_duration: NotRequired[float]  # noqa: E111


class WalkStatisticsSnapshot(TypedDict, total=False):
  """Aggregated walk statistics tracked per dog."""  # noqa: E111

  status: str  # noqa: E111
  message: str  # noqa: E111
  walks_today: Required[int]  # noqa: E111
  total_duration_today: Required[float]  # noqa: E111
  total_distance_today: Required[float]  # noqa: E111
  last_walk: str | None  # noqa: E111
  last_walk_duration: float | None  # noqa: E111
  last_walk_distance: float | None  # noqa: E111
  average_duration: float | None  # noqa: E111
  average_distance: float | None  # noqa: E111
  weekly_walks: Required[int]  # noqa: E111
  weekly_distance: Required[float]  # noqa: E111
  needs_walk: Required[bool]  # noqa: E111
  walk_streak: Required[int]  # noqa: E111
  energy_level: Required[str]  # noqa: E111
  walk_in_progress: bool  # noqa: E111
  current_walk: WalkSessionSnapshot | None  # noqa: E111


class WalkModulePayload(WalkStatisticsSnapshot, total=False):
  """Telemetry returned by the walk adapter."""  # noqa: E111

  daily_walks: NotRequired[int]  # noqa: E111
  total_distance: NotRequired[float]  # noqa: E111


class WalkModuleTelemetry(WalkModulePayload, total=False):
  """Extended walk telemetry with historical and lifetime statistics."""  # noqa: E111

  total_distance_lifetime: NotRequired[float]  # noqa: E111
  total_walks_lifetime: NotRequired[int]  # noqa: E111
  distance_this_week: NotRequired[float]  # noqa: E111
  distance_this_month: NotRequired[float]  # noqa: E111
  total_duration_this_week: NotRequired[float]  # noqa: E111
  walks_this_week: NotRequired[int]  # noqa: E111
  walks_history: NotRequired[list[WalkSessionSnapshot]]  # noqa: E111
  daily_walk_counts: NotRequired[dict[str, int]]  # noqa: E111
  weekly_walk_target: NotRequired[int]  # noqa: E111
  walks_yesterday: NotRequired[int]  # noqa: E111


ModuleAdapterPayload = (
  FeedingModulePayload
  | WalkModulePayload
  | GPSModulePayload
  | GeofencingModulePayload
  | HealthModulePayload
  | WeatherModulePayload
  | GardenModulePayload
)

type DogModulesMapping = Mapping[str, bool]


class WalkGPSSnapshot(TypedDict, total=False):
  """Latest GPS status exported by the walk manager."""  # noqa: E111

  latitude: float | None  # noqa: E111
  longitude: float | None  # noqa: E111
  accuracy: float | None  # noqa: E111
  altitude: float | None  # noqa: E111
  speed: float | None  # noqa: E111
  heading: float | None  # noqa: E111
  last_seen: str | None  # noqa: E111
  source: str | None  # noqa: E111
  available: Required[bool]  # noqa: E111
  zone: Required[str]  # noqa: E111
  distance_from_home: float | None  # noqa: E111
  signal_strength: int | None  # noqa: E111
  battery_level: int | None  # noqa: E111
  accuracy_threshold: float | None  # noqa: E111
  update_interval: float | int | None  # noqa: E111
  automatic_config: JSONMutableMapping | None  # noqa: E111
  error: str  # noqa: E111


class WalkRouteBounds(TypedDict):
  """Bounding box describing the extents of exported walk routes."""  # noqa: E111

  min_lat: float  # noqa: E111
  max_lat: float  # noqa: E111
  min_lon: float  # noqa: E111
  max_lon: float  # noqa: E111


class WalkDailyStatistics(TypedDict):
  """Aggregated walk statistics for the active day."""  # noqa: E111

  total_walks_today: int  # noqa: E111
  total_duration_today: float  # noqa: E111
  total_distance_today: float  # noqa: E111
  average_duration: float | None  # noqa: E111
  average_distance: float | None  # noqa: E111
  energy_level: str  # noqa: E111


class WalkWeeklyStatistics(TypedDict):
  """Aggregated walk statistics for the active week."""  # noqa: E111

  total_walks_this_week: int  # noqa: E111
  total_distance_this_week: float  # noqa: E111
  walk_streak: int  # noqa: E111


type WalkRouteExportFormat = Literal["gpx", "json", "csv"]
"""Supported export formats for walk routes."""


type WalkDetectionMetadata = Mapping[str, JSONValue]
"""Immutable walk detection metadata forwarded by auto-detection sources."""

type WalkDetectionMutableMetadata = dict[str, JSONValue]
"""Mutable walk detection metadata payload stored during active sessions."""


class WalkRouteExportMetadata(TypedDict):
  """Metadata describing the exported walk routes."""  # noqa: E111

  creator: str  # noqa: E111
  version: str  # noqa: E111
  generated_by: str  # noqa: E111
  bounds: WalkRouteBounds  # noqa: E111


class WalkRouteExportPayload(TypedDict, total=False):
  """Serialized walk route export payload returned to callers."""  # noqa: E111

  dog_id: str  # noqa: E111
  export_timestamp: str  # noqa: E111
  format: WalkRouteExportFormat  # noqa: E111
  walks_count: int  # noqa: E111
  total_distance_meters: float  # noqa: E111
  total_duration_seconds: float  # noqa: E111
  total_gps_points: int  # noqa: E111
  walks: list[WalkSessionSnapshot] | list[JSONMutableMapping]  # noqa: E111
  export_metadata: WalkRouteExportMetadata  # noqa: E111
  file_extension: NotRequired[str]  # noqa: E111
  mime_type: NotRequired[str]  # noqa: E111
  gpx_data: NotRequired[str]  # noqa: E111
  json_data: NotRequired[str]  # noqa: E111
  csv_data: NotRequired[str]  # noqa: E111


class WalkManagerDogSnapshot(TypedDict):
  """Composite snapshot exposed to diagnostics for each dog."""  # noqa: E111

  active_walk: WalkSessionSnapshot | None  # noqa: E111
  history: list[WalkSessionSnapshot]  # noqa: E111
  stats: WalkStatisticsSnapshot  # noqa: E111
  gps: WalkGPSSnapshot  # noqa: E111


class WalkOverviewSnapshot(WalkManagerDogSnapshot, total=False):
  """Composite snapshot returned by :func:`WalkManager.get_walk_data`."""  # noqa: E111

  statistics: Required[WalkStatisticsSnapshot]  # noqa: E111


class WalkPerformanceSnapshot(TypedDict):
  """Structured snapshot of walk manager performance telemetry."""  # noqa: E111

  total_dogs: int  # noqa: E111
  dogs_with_gps: int  # noqa: E111
  active_walks: int  # noqa: E111
  total_walks_today: int  # noqa: E111
  total_distance_today: float  # noqa: E111
  walk_detection_enabled: bool  # noqa: E111
  performance_metrics: WalkPerformanceCounters  # noqa: E111
  cache_stats: GPSCacheStats  # noqa: E111
  statistics_cache_entries: int  # noqa: E111
  location_analysis_queue_size: int  # noqa: E111
  average_path_length: float  # noqa: E111


@dataclass(slots=True)
class ModuleCacheMetrics:
  """Cache metrics exposed by coordinator module adapters."""  # noqa: E111

  entries: int = 0  # noqa: E111
  hits: int = 0  # noqa: E111
  misses: int = 0  # noqa: E111

  @property  # noqa: E111
  def hit_rate(self) -> float:  # noqa: E111
    """Return the cache hit rate as a percentage."""

    total = self.hits + self.misses
    if total <= 0:
      return 0.0  # noqa: E111
    return (self.hits / total) * 100.0


@dataclass(slots=True)
class CoordinatorModuleTask:
  """Wrapper describing a coroutine used to fetch module payloads."""  # noqa: E111

  module: CoordinatorTypedModuleName  # noqa: E111
  coroutine: Awaitable[ModuleAdapterPayload]  # noqa: E111


@dataclass(slots=True)
class CoordinatorRuntimeManagers:
  """Typed container describing runtime manager dependencies."""  # noqa: E111

  data_manager: PawControlDataManager | None = None  # noqa: E111
  feeding_manager: FeedingManager | None = None  # noqa: E111
  walk_manager: WalkManager | None = None  # noqa: E111
  notification_manager: PawControlNotificationManager | None = None  # noqa: E111
  gps_geofence_manager: GPSGeofenceManager | None = None  # noqa: E111
  geofencing_manager: PawControlGeofencing | None = None  # noqa: E111
  weather_health_manager: WeatherHealthManager | None = None  # noqa: E111
  garden_manager: GardenManager | None = None  # noqa: E111

  @classmethod  # noqa: E111
  def attribute_names(cls) -> tuple[str, ...]:  # noqa: E111
    """Return the coordinator attribute names mirrored by this container."""

    return (
      "data_manager",
      "feeding_manager",
      "garden_manager",
      "geofencing_manager",
      "gps_geofence_manager",
      "notification_manager",
      "walk_manager",
      "weather_health_manager",
    )


class CacheDiagnosticsMetadata(TypedDict, total=False):
  """Metadata surfaced by cache diagnostics providers."""  # noqa: E111

  cleanup_invocations: int  # noqa: E111
  last_cleanup: datetime | str | None  # noqa: E111
  last_override_ttl: int | float | None  # noqa: E111
  last_expired_count: int  # noqa: E111
  expired_entries: int  # noqa: E111
  expired_via_override: int  # noqa: E111
  pending_expired_entries: int  # noqa: E111
  pending_override_candidates: int  # noqa: E111
  active_override_flags: int  # noqa: E111
  active_override_entries: int  # noqa: E111
  tracked_entries: int  # noqa: E111
  per_module: JSONMutableMapping  # noqa: E111
  per_dog: JSONMutableMapping  # noqa: E111
  entry_scripts: list[str]  # noqa: E111
  per_dog_helpers: dict[str, int]  # noqa: E111
  entity_domains: dict[str, int]  # noqa: E111
  errors: list[str]  # noqa: E111
  summary: JSONMutableMapping  # noqa: E111
  snapshots: list[JSONMutableMapping]  # noqa: E111
  created_entities: list[str]  # noqa: E111
  detection_stats: JSONMutableMapping  # noqa: E111
  cleanup_task_active: bool  # noqa: E111
  cleanup_listeners: int  # noqa: E111
  daily_reset_configured: bool  # noqa: E111
  namespace: str  # noqa: E111
  storage_path: str  # noqa: E111
  timestamp_anomalies: dict[str, str]  # noqa: E111
  last_generated: str | None  # noqa: E111
  manager_last_generated_age_seconds: int | float  # noqa: E111
  manager_last_activity: str | None  # noqa: E111
  manager_last_activity_age_seconds: int | float  # noqa: E111
  service_guard_metrics: HelperManagerGuardMetrics  # noqa: E111


class PersonEntityDiagnostics(CacheDiagnosticsMetadata, total=False):
  """Diagnostics payload enriched with person manager cache metadata."""  # noqa: E111

  cache_entries: dict[str, PersonNotificationCacheEntry]  # noqa: E111
  discovery_task_state: Literal[  # noqa: E111
    "not_started",
    "running",
    "completed",
    "cancelled",
  ]
  listener_count: int  # noqa: E111


class CacheDiagnosticsPayload(TypedDict, total=False):
  """Structured mapping exported by :class:`CacheDiagnosticsSnapshot`."""  # noqa: E111

  stats: JSONMutableMapping  # noqa: E111
  diagnostics: CacheDiagnosticsMetadata  # noqa: E111
  snapshot: JSONMutableMapping  # noqa: E111
  error: str  # noqa: E111
  repair_summary: JSONMutableMapping  # noqa: E111


@dataclass(slots=True)
class CacheDiagnosticsSnapshot(Mapping[str, JSONValue]):
  """Structured diagnostics snapshot returned by cache monitors."""  # noqa: E111

  stats: JSONLikeMapping | None = None  # noqa: E111
  diagnostics: CacheDiagnosticsMetadata | None = None  # noqa: E111
  snapshot: JSONLikeMapping | None = None  # noqa: E111
  error: str | None = None  # noqa: E111
  repair_summary: CacheRepairAggregate | None = None  # noqa: E111

  def to_mapping(self) -> JSONMutableMapping:  # noqa: E111
    """Return a mapping representation for downstream consumers."""

    payload: JSONMutableMapping = {}
    if self.stats is not None:
      payload["stats"] = cast(JSONValue, dict(self.stats))  # noqa: E111
    if self.diagnostics is not None:
      payload["diagnostics"] = cast(JSONValue, dict(self.diagnostics))  # noqa: E111
    if self.snapshot is not None:
      payload["snapshot"] = cast(JSONValue, dict(self.snapshot))  # noqa: E111
    if self.error is not None:
      payload["error"] = self.error  # noqa: E111
    if isinstance(self.repair_summary, CacheRepairAggregate):
      payload["repair_summary"] = cast(  # noqa: E111
        JSONValue,
        self.repair_summary.to_mapping(),
      )
    return payload

  @classmethod  # noqa: E111
  def from_mapping(cls, payload: JSONMapping) -> CacheDiagnosticsSnapshot:  # noqa: E111
    """Create a snapshot payload from an arbitrary mapping."""

    stats = payload.get("stats")
    diagnostics = payload.get("diagnostics")
    snapshot = payload.get("snapshot")
    error = payload.get("error")
    repair_summary_payload = payload.get("repair_summary")

    repair_summary: CacheRepairAggregate | None
    if isinstance(repair_summary_payload, CacheRepairAggregate):
      repair_summary = repair_summary_payload  # noqa: E111
    elif isinstance(repair_summary_payload, Mapping):
      try:  # noqa: E111
        repair_summary = CacheRepairAggregate.from_mapping(
          repair_summary_payload,
        )
      except Exception:  # pragma: no cover - defensive fallback  # noqa: E111
        repair_summary = None
    else:
      repair_summary = None  # noqa: E111

    return cls(
      stats=dict(stats) if isinstance(stats, Mapping) else None,
      diagnostics=cast(
        CacheDiagnosticsMetadata | None,
        dict(diagnostics)
        if isinstance(diagnostics, Mapping)
        else diagnostics
        if isinstance(diagnostics, dict)
        else None,
      ),
      snapshot=dict(snapshot) if isinstance(snapshot, Mapping) else None,
      error=error if isinstance(error, str) else None,
      repair_summary=repair_summary,
    )

  def __getitem__(self, key: str) -> JSONValue:  # noqa: E111
    """Return the value associated with ``key`` from the mapping view."""
    return self.to_mapping()[key]

  def __iter__(self) -> Iterator[str]:  # noqa: E111
    """Yield cache diagnostic mapping keys in iteration order."""
    return iter(self.to_mapping())

  def __len__(self) -> int:  # noqa: E111
    """Return the number of items exposed by the mapping view."""
    return len(self.to_mapping())


CacheDiagnosticsMap = dict[str, CacheDiagnosticsSnapshot]
"""Mapping from cache identifiers to diagnostics snapshots."""


class DataStatisticsPayload(TypedDict):
  """Diagnostics payload returned by data statistics collectors."""  # noqa: E111

  data_manager_available: bool  # noqa: E111
  metrics: JSONMutableMapping  # noqa: E111


class RecentErrorEntry(TypedDict):
  """Placeholder entry returned when detailed error history is unavailable."""  # noqa: E111

  note: str  # noqa: E111
  suggestion: str  # noqa: E111
  entry_id: str  # noqa: E111


class DebugInformationPayload(TypedDict):
  """Static debug metadata exported by diagnostics handlers."""  # noqa: E111

  debug_logging_enabled: bool  # noqa: E111
  integration_version: str  # noqa: E111
  quality_scale: str  # noqa: E111
  supported_features: list[str]  # noqa: E111
  documentation_url: str  # noqa: E111
  issue_tracker: str  # noqa: E111
  entry_id: str  # noqa: E111
  ha_version: str  # noqa: E111


class ModuleUsageBreakdown(TypedDict):
  """Aggregated module usage counters used in diagnostics exports."""  # noqa: E111

  counts: dict[str, int]  # noqa: E111
  percentages: dict[str, float]  # noqa: E111
  most_used_module: str | None  # noqa: E111
  least_used_module: str | None  # noqa: E111


class CacheRepairIssue(TypedDict, total=False):
  """Per-cache anomaly metadata forwarded to Home Assistant repairs."""  # noqa: E111

  cache: Required[str]  # noqa: E111
  entries: NotRequired[int]  # noqa: E111
  hits: NotRequired[int]  # noqa: E111
  misses: NotRequired[int]  # noqa: E111
  hit_rate: NotRequired[float]  # noqa: E111
  expired_entries: NotRequired[int]  # noqa: E111
  expired_via_override: NotRequired[int]  # noqa: E111
  pending_expired_entries: NotRequired[int]  # noqa: E111
  pending_override_candidates: NotRequired[int]  # noqa: E111
  active_override_flags: NotRequired[int]  # noqa: E111
  errors: NotRequired[list[str]]  # noqa: E111
  timestamp_anomalies: NotRequired[dict[str, str]]  # noqa: E111


@dataclass(slots=True)
class CacheRepairTotals:
  """Summarised cache counters shared across diagnostics and repairs."""  # noqa: E111

  entries: int = 0  # noqa: E111
  hits: int = 0  # noqa: E111
  misses: int = 0  # noqa: E111
  expired_entries: int = 0  # noqa: E111
  expired_via_override: int = 0  # noqa: E111
  pending_expired_entries: int = 0  # noqa: E111
  pending_override_candidates: int = 0  # noqa: E111
  active_override_flags: int = 0  # noqa: E111
  overall_hit_rate: float | None = None  # noqa: E111

  def as_dict(self) -> dict[str, int | float]:  # noqa: E111
    """Return a JSON-serialisable view of the totals."""

    payload: dict[str, int | float] = {
      "entries": self.entries,
      "hits": self.hits,
      "misses": self.misses,
      "expired_entries": self.expired_entries,
      "expired_via_override": self.expired_via_override,
      "pending_expired_entries": self.pending_expired_entries,
      "pending_override_candidates": self.pending_override_candidates,
      "active_override_flags": self.active_override_flags,
    }
    if self.overall_hit_rate is not None:
      payload["overall_hit_rate"] = round(self.overall_hit_rate, 2)  # noqa: E111
    return payload


@dataclass(slots=True)
class CacheRepairAggregate(Mapping[str, JSONValue]):
  """Aggregated cache health metrics surfaced through repairs issues."""  # noqa: E111

  total_caches: int  # noqa: E111
  anomaly_count: int  # noqa: E111
  severity: str  # noqa: E111
  generated_at: str  # noqa: E111
  caches_with_errors: list[str] | None = None  # noqa: E111
  caches_with_expired_entries: list[str] | None = None  # noqa: E111
  caches_with_pending_expired_entries: list[str] | None = None  # noqa: E111
  caches_with_override_flags: list[str] | None = None  # noqa: E111
  caches_with_low_hit_rate: list[str] | None = None  # noqa: E111
  totals: CacheRepairTotals | None = None  # noqa: E111
  issues: list[CacheRepairIssue] | None = None  # noqa: E111

  def to_mapping(self) -> JSONMutableMapping:  # noqa: E111
    """Return a mapping representation for Home Assistant repairs."""

    payload: JSONMutableMapping = {
      "total_caches": self.total_caches,
      "anomaly_count": self.anomaly_count,
      "severity": self.severity,
      "generated_at": self.generated_at,
    }
    if self.caches_with_errors:
      payload["caches_with_errors"] = list(self.caches_with_errors)  # noqa: E111
    if self.caches_with_expired_entries:
      payload["caches_with_expired_entries"] = list(  # noqa: E111
        self.caches_with_expired_entries,
      )
    if self.caches_with_pending_expired_entries:
      payload["caches_with_pending_expired_entries"] = list(  # noqa: E111
        self.caches_with_pending_expired_entries,
      )
    if self.caches_with_override_flags:
      payload["caches_with_override_flags"] = list(  # noqa: E111
        self.caches_with_override_flags,
      )
    if self.caches_with_low_hit_rate:
      payload["caches_with_low_hit_rate"] = list(  # noqa: E111
        self.caches_with_low_hit_rate,
      )
    if self.totals is not None:
      payload["totals"] = self.totals.as_dict()  # noqa: E111
    if self.issues:
      payload["issues"] = [  # noqa: E111
        cast(JSONMutableMapping, dict(issue)) for issue in self.issues
      ]
    return payload

  @classmethod  # noqa: E111
  def from_mapping(cls, payload: JSONMapping) -> CacheRepairAggregate:  # noqa: E111
    """Return a :class:`CacheRepairAggregate` constructed from a mapping."""

    def _coerce_int(value: JSONValue | object) -> int:
      if isinstance(value, bool):  # noqa: E111
        return int(value)
      if isinstance(value, int):  # noqa: E111
        return value
      if isinstance(value, float):  # noqa: E111
        return int(value)
      if isinstance(value, str):  # noqa: E111
        try:
          return int(float(value))  # noqa: E111
        except ValueError:
          return 0  # noqa: E111
      return 0  # noqa: E111

    totals_payload = payload.get("totals")
    totals = None
    if isinstance(totals_payload, Mapping):
      overall_hit_rate_value = totals_payload.get("overall_hit_rate")  # noqa: E111
      overall_hit_rate: float | None  # noqa: E111
      if isinstance(overall_hit_rate_value, int | float):  # noqa: E111
        overall_hit_rate = float(overall_hit_rate_value)
      elif isinstance(overall_hit_rate_value, str):  # noqa: E111
        try:
          overall_hit_rate = float(overall_hit_rate_value)  # noqa: E111
        except ValueError:
          overall_hit_rate = None  # noqa: E111
      else:  # noqa: E111
        overall_hit_rate = None

      totals = CacheRepairTotals(  # noqa: E111
        entries=_coerce_int(totals_payload.get("entries")),
        hits=_coerce_int(totals_payload.get("hits")),
        misses=_coerce_int(totals_payload.get("misses")),
        expired_entries=_coerce_int(
          totals_payload.get("expired_entries"),
        ),
        expired_via_override=_coerce_int(
          totals_payload.get("expired_via_override"),
        ),
        pending_expired_entries=_coerce_int(
          totals_payload.get("pending_expired_entries"),
        ),
        pending_override_candidates=_coerce_int(
          totals_payload.get("pending_override_candidates"),
        ),
        active_override_flags=_coerce_int(
          totals_payload.get("active_override_flags"),
        ),
        overall_hit_rate=overall_hit_rate,
      )

    def _string_list(field: str) -> list[str] | None:
      value = payload.get(field)  # noqa: E111
      if isinstance(value, list):  # noqa: E111
        return [str(item) for item in value if isinstance(item, str)]
      if isinstance(value, tuple | set | frozenset):  # noqa: E111
        return [str(item) for item in value if isinstance(item, str)]
      return None  # noqa: E111

    issues_payload = payload.get("issues")
    issues: list[CacheRepairIssue] | None = None
    if isinstance(issues_payload, list):
      filtered = [  # noqa: E111
        cast(CacheRepairIssue, dict(issue))
        for issue in issues_payload
        if isinstance(issue, Mapping)
      ]
      if filtered:  # noqa: E111
        issues = filtered

    return cls(
      total_caches=_coerce_int(payload.get("total_caches")),
      anomaly_count=_coerce_int(payload.get("anomaly_count")),
      severity=str(payload.get("severity", "unknown")),
      generated_at=str(payload.get("generated_at", "")),
      caches_with_errors=_string_list("caches_with_errors"),
      caches_with_expired_entries=_string_list(
        "caches_with_expired_entries",
      ),
      caches_with_pending_expired_entries=_string_list(
        "caches_with_pending_expired_entries",
      ),
      caches_with_override_flags=_string_list(
        "caches_with_override_flags",
      ),
      caches_with_low_hit_rate=_string_list("caches_with_low_hit_rate"),
      totals=totals,
      issues=issues,
    )

  def __getitem__(self, key: str) -> JSONValue:  # noqa: E111
    """Return the value associated with ``key`` from the mapping view."""
    return self.to_mapping()[key]

  def __iter__(self) -> Iterator[str]:  # noqa: E111
    """Yield cache repair aggregate keys in iteration order."""
    return iter(self.to_mapping())

  def __len__(self) -> int:  # noqa: E111
    """Return the number of items exposed by the mapping view."""
    return len(self.to_mapping())


class CacheDiagnosticsCapture(TypedDict, total=False):
  """Snapshot captured by services during maintenance routines."""  # noqa: E111

  snapshots: Required[CacheDiagnosticsMap]  # noqa: E111
  repair_summary: NotRequired[CacheRepairAggregate]  # noqa: E111


class MaintenanceExecutionDiagnostics(TypedDict, total=False):
  """Diagnostics metadata captured by maintenance utilities."""  # noqa: E111

  cache: NotRequired[CacheDiagnosticsCapture]  # noqa: E111
  metadata: NotRequired[MaintenanceMetadataPayload]  # noqa: E111


class MaintenanceExecutionResult(TypedDict, total=False):
  """Structured payload appended after running maintenance utilities."""  # noqa: E111

  task: Required[str]  # noqa: E111
  status: Required[Literal["success", "error"]]  # noqa: E111
  recorded_at: Required[str]  # noqa: E111
  message: NotRequired[str]  # noqa: E111
  diagnostics: NotRequired[MaintenanceExecutionDiagnostics]  # noqa: E111
  details: NotRequired[MaintenanceMetadataPayload]  # noqa: E111


class ServiceExecutionDiagnostics(TypedDict, total=False):
  """Diagnostics metadata captured while executing a service handler."""  # noqa: E111

  cache: NotRequired[CacheDiagnosticsCapture]  # noqa: E111
  metadata: NotRequired[MaintenanceMetadataPayload]  # noqa: E111
  guard: NotRequired[ServiceGuardSummary]  # noqa: E111
  resilience_summary: NotRequired[CoordinatorResilienceSummary]  # noqa: E111
  rejection_metrics: NotRequired[CoordinatorRejectionMetrics]  # noqa: E111


class ServiceExecutionResult(TypedDict, total=False):
  """Structured payload appended to runtime stats after service execution."""  # noqa: E111

  service: Required[str]  # noqa: E111
  status: Required[Literal["success", "error"]]  # noqa: E111
  dog_id: NotRequired[str]  # noqa: E111
  message: NotRequired[str]  # noqa: E111
  diagnostics: NotRequired[ServiceExecutionDiagnostics]  # noqa: E111
  details: NotRequired[ServiceDetailsPayload]  # noqa: E111
  guard: NotRequired[ServiceGuardSummary]  # noqa: E111


class ServiceCallLatencyTelemetry(TypedDict, total=False):
  """Latency summary for Home Assistant service calls."""  # noqa: E111

  samples: int  # noqa: E111
  average_ms: float  # noqa: E111
  minimum_ms: float  # noqa: E111
  maximum_ms: float  # noqa: E111
  last_ms: float  # noqa: E111


class ServiceCallTelemetryEntry(TypedDict, total=False):
  """Aggregated telemetry for a subset of service calls."""  # noqa: E111

  total_calls: int  # noqa: E111
  success_calls: int  # noqa: E111
  error_calls: int  # noqa: E111
  error_rate: float  # noqa: E111
  latency_ms: ServiceCallLatencyTelemetry  # noqa: E111


class ServiceCallTelemetry(ServiceCallTelemetryEntry, total=False):
  """Aggregated telemetry for all service calls, grouped by service."""  # noqa: E111

  per_service: dict[str, ServiceCallTelemetryEntry]  # noqa: E111


ManualResiliencePreferenceKey = Literal[
  "manual_check_event",
  "manual_guard_event",
  "manual_breaker_event",
]


class ManualResilienceEventSource(TypedDict, total=False):
  """Metadata describing a tracked manual resilience escalation event."""  # noqa: E111

  preference_key: ManualResiliencePreferenceKey  # noqa: E111
  configured_role: Literal["check", "guard", "breaker"]  # noqa: E111
  listener_sources: tuple[str, ...]  # noqa: E111
  source_tags: list[str]  # noqa: E111
  primary_source: str  # noqa: E111


class ManualResilienceEventRecord(TypedDict, total=False):
  """Captured metadata for a manual resilience event before serialisation."""  # noqa: E111

  event_type: str  # noqa: E111
  preference_key: ManualResiliencePreferenceKey | None  # noqa: E111
  configured_role: Literal["check", "guard", "breaker"] | None  # noqa: E111
  time_fired: datetime | None  # noqa: E111
  received_at: datetime | None  # noqa: E111
  context_id: str | None  # noqa: E111
  user_id: str | None  # noqa: E111
  origin: str | None  # noqa: E111
  data: JSONMutableMapping | None  # noqa: E111
  sources: Sequence[str]  # noqa: E111
  source_tags: list[str]  # noqa: E111
  primary_source: str  # noqa: E111
  reasons: list[str]  # noqa: E111
  recorded_at: datetime | None  # noqa: E111
  recorded_age_seconds: int | None  # noqa: E111


class ManualResilienceEventSnapshot(TypedDict, total=False):
  """Serialised telemetry for the last manual resilience trigger."""  # noqa: E111

  event_type: str | None  # noqa: E111
  category: Literal["check", "guard", "breaker", "unknown"]  # noqa: E111
  matched_preference: ManualResiliencePreferenceKey | None  # noqa: E111
  time_fired: str | None  # noqa: E111
  time_fired_age_seconds: int | None  # noqa: E111
  received_at: str | None  # noqa: E111
  received_age_seconds: int | None  # noqa: E111
  recorded_at: str | None  # noqa: E111
  recorded_age_seconds: int | None  # noqa: E111
  origin: str | None  # noqa: E111
  context_id: str | None  # noqa: E111
  user_id: str | None  # noqa: E111
  data: JSONMutableMapping | None  # noqa: E111
  sources: list[str] | None  # noqa: E111
  reasons: list[str]  # noqa: E111


class ResilienceEscalationFieldEntry(TypedDict, total=False):
  """Active and default field values for resilience escalation scripts."""  # noqa: E111

  default: JSONValue | None  # noqa: E111
  active: JSONValue | None  # noqa: E111


class ResilienceEscalationFollowupEntry(ResilienceEscalationFieldEntry, total=False):
  """Follow-up script metadata with configuration state."""  # noqa: E111

  configured: bool  # noqa: E111


type ResilienceEscalationThresholds = dict[str, ResilienceEscalationFieldEntry]
"""Mapping of resilience escalation thresholds keyed by identifier."""


type ResilienceEscalationFields = dict[str, ResilienceEscalationFieldEntry]
"""Mapping of resilience escalation field defaults keyed by field name."""


class ResilienceEscalationSnapshot(TypedDict, total=False):
  """Snapshot describing the resilience escalation helper state."""  # noqa: E111

  available: bool  # noqa: E111
  state_available: bool  # noqa: E111
  entity_id: str | None  # noqa: E111
  object_id: str | None  # noqa: E111
  alias: str | None  # noqa: E111
  description: str | None  # noqa: E111
  last_generated: str | None  # noqa: E111
  last_generated_age_seconds: int | None  # noqa: E111
  last_generated_status: str | None  # noqa: E111
  last_triggered: str | None  # noqa: E111
  last_triggered_age_seconds: int | None  # noqa: E111
  thresholds: ResilienceEscalationThresholds  # noqa: E111
  fields: ResilienceEscalationFields  # noqa: E111
  followup_script: ResilienceEscalationFollowupEntry  # noqa: E111
  statistics_entity_id: ResilienceEscalationFieldEntry  # noqa: E111
  escalation_service: ResilienceEscalationFieldEntry  # noqa: E111
  manual_events: JSONMutableMapping  # noqa: E111


class ManualResilienceAutomationEntry(TypedDict, total=False):
  """Metadata describing automation listeners for manual resilience events."""  # noqa: E111

  config_entry_id: str | None  # noqa: E111
  title: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111
  manual_check_event: str | None  # noqa: E111
  configured_guard: bool  # noqa: E111
  configured_breaker: bool  # noqa: E111
  configured_check: bool  # noqa: E111


class ManualResilienceListenerMetadata(TypedDict, total=False):
  """Aggregated listener metadata for manual resilience events."""  # noqa: E111

  sources: list[str]  # noqa: E111
  source_tags: list[str]  # noqa: E111
  primary_source: str | None  # noqa: E111


class ManualResilienceEventCounters(TypedDict):
  """Aggregated counters for manual resilience event activity."""  # noqa: E111

  total: int  # noqa: E111
  by_event: dict[str, int]  # noqa: E111
  by_reason: dict[str, int]  # noqa: E111


class ManualResilienceEventsTelemetry(TypedDict, total=False):
  """Telemetry payload embedded in resilience diagnostics snapshots."""  # noqa: E111

  available: Required[bool]  # noqa: E111
  automations: list[ManualResilienceAutomationEntry]  # noqa: E111
  configured_guard_events: list[str]  # noqa: E111
  configured_breaker_events: list[str]  # noqa: E111
  configured_check_events: list[str]  # noqa: E111
  system_guard_event: str | None  # noqa: E111
  system_breaker_event: str | None  # noqa: E111
  listener_events: dict[str, list[str]]  # noqa: E111
  listener_sources: dict[str, list[str]]  # noqa: E111
  listener_metadata: dict[str, ManualResilienceListenerMetadata]  # noqa: E111
  preferred_events: dict[ManualResiliencePreferenceKey, str | None]  # noqa: E111
  preferred_guard_event: str | None  # noqa: E111
  preferred_breaker_event: str | None  # noqa: E111
  preferred_check_event: str | None  # noqa: E111
  active_listeners: list[str]  # noqa: E111
  last_event: Required[ManualResilienceEventSnapshot | None]  # noqa: E111
  last_trigger: ManualResilienceEventSnapshot | None  # noqa: E111
  event_history: Required[list[ManualResilienceEventSnapshot]]  # noqa: E111
  event_counters: ManualResilienceEventCounters  # noqa: E111


class ManualResilienceSystemSettingsSnapshot(TypedDict, total=False):
  """Normalised resilience system settings derived from config entry options."""  # noqa: E111

  manual_check_event: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111
  resilience_skip_threshold: int  # noqa: E111
  resilience_breaker_threshold: int  # noqa: E111


class ManualResilienceOptionsSnapshot(TypedDict, total=False):
  """Normalised config-entry options impacting manual resilience behaviour."""  # noqa: E111

  manual_check_event: str | None  # noqa: E111
  manual_guard_event: str | None  # noqa: E111
  manual_breaker_event: str | None  # noqa: E111
  resilience_skip_threshold: int  # noqa: E111
  resilience_breaker_threshold: int  # noqa: E111
  manual_event_history_size: int  # noqa: E111
  system_settings: ManualResilienceSystemSettingsSnapshot  # noqa: E111


type ManualResilienceEventSelection = dict[ManualResiliencePreferenceKey, str | None]
"""Preferred manual resilience events pushed to automation blueprints."""


class ServiceContextMetadata(TypedDict, total=False):
  """Service context identifiers captured for telemetry."""  # noqa: E111

  context_id: str | None  # noqa: E111
  parent_id: str | None  # noqa: E111
  user_id: str | None  # noqa: E111


class FeedingComplianceEventPayload(TypedDict, total=False):
  """Structured event payload emitted after running feeding compliance checks."""  # noqa: E111

  dog_id: str  # noqa: E111
  dog_name: str | None  # noqa: E111
  days_to_check: int  # noqa: E111
  notify_on_issues: bool  # noqa: E111
  notification_sent: bool  # noqa: E111
  result: FeedingComplianceResult  # noqa: E111
  notification_id: NotRequired[str]  # noqa: E111
  context_id: NotRequired[str]  # noqa: E111
  parent_id: NotRequired[str]  # noqa: E111
  user_id: NotRequired[str | None]  # noqa: E111
  localized_summary: NotRequired[FeedingComplianceLocalizedSummary]  # noqa: E111


type FeedingComplianceDisplayMapping = Mapping[str, object]
"""Mapping-compatible compliance payload accepted by translation helpers."""


class FeedingComplianceLocalizedSummary(TypedDict):
  """Localised representation of a feeding compliance result."""  # noqa: E111

  title: str  # noqa: E111
  message: str | None  # noqa: E111
  score_line: str | None  # noqa: E111
  missed_meals: list[str]  # noqa: E111
  issues: list[str]  # noqa: E111
  recommendations: list[str]  # noqa: E111


class CoordinatorRepairsSummary(TypedDict, total=False):
  """Condensed repairs telemetry surfaced alongside coordinator statistics."""  # noqa: E111

  severity: str  # noqa: E111
  anomaly_count: int  # noqa: E111
  total_caches: int  # noqa: E111
  generated_at: str  # noqa: E111
  issues: int  # noqa: E111
  caches_with_errors: NotRequired[int]  # noqa: E111
  caches_with_expired_entries: NotRequired[int]  # noqa: E111
  caches_with_pending_expired_entries: NotRequired[int]  # noqa: E111
  caches_with_override_flags: NotRequired[int]  # noqa: E111
  caches_with_low_hit_rate: NotRequired[int]  # noqa: E111


class CoordinatorUpdateCounts(TypedDict):
  """Aggregated update counters exposed by coordinator diagnostics."""  # noqa: E111

  total: int  # noqa: E111
  successful: int  # noqa: E111
  failed: int  # noqa: E111


class CoordinatorPerformanceMetrics(TypedDict):
  """Performance metrics captured for coordinator statistics panels."""  # noqa: E111

  success_rate: float  # noqa: E111
  cache_entries: int  # noqa: E111
  cache_hit_rate: float  # noqa: E111
  consecutive_errors: int  # noqa: E111
  last_update: Any  # noqa: E111
  update_interval: float  # noqa: E111
  api_calls: int  # noqa: E111
  rejected_call_count: NotRequired[int]  # noqa: E111
  rejection_breaker_count: NotRequired[int]  # noqa: E111
  rejection_rate: NotRequired[float | None]  # noqa: E111
  last_rejection_time: NotRequired[float | None]  # noqa: E111
  last_rejection_breaker_id: NotRequired[str | None]  # noqa: E111
  last_rejection_breaker_name: NotRequired[str | None]  # noqa: E111
  open_breaker_count: NotRequired[int]  # noqa: E111
  half_open_breaker_count: NotRequired[int]  # noqa: E111
  unknown_breaker_count: NotRequired[int]  # noqa: E111
  open_breakers: NotRequired[list[str]]  # noqa: E111
  open_breaker_ids: NotRequired[list[str]]  # noqa: E111
  half_open_breakers: NotRequired[list[str]]  # noqa: E111
  half_open_breaker_ids: NotRequired[list[str]]  # noqa: E111
  unknown_breakers: NotRequired[list[str]]  # noqa: E111
  unknown_breaker_ids: NotRequired[list[str]]  # noqa: E111
  rejection_breaker_ids: NotRequired[list[str]]  # noqa: E111
  rejection_breakers: NotRequired[list[str]]  # noqa: E111


class CoordinatorHealthIndicators(TypedDict, total=False):
  """Health indicator flags surfaced alongside coordinator statistics."""  # noqa: E111

  consecutive_errors: int  # noqa: E111
  stability_window_ok: bool  # noqa: E111


class EntityBudgetSummary(TypedDict):
  """Aggregate entity budget metrics exposed via diagnostics."""  # noqa: E111

  active_dogs: int  # noqa: E111
  total_capacity: int  # noqa: E111
  total_allocated: int  # noqa: E111
  total_remaining: int  # noqa: E111
  average_utilization: float  # noqa: E111
  peak_utilization: float  # noqa: E111
  denied_requests: int  # noqa: E111


class AdaptivePollingDiagnostics(TypedDict):
  """Runtime diagnostics captured from the adaptive polling controller."""  # noqa: E111

  target_cycle_ms: float  # noqa: E111
  current_interval_ms: float  # noqa: E111
  average_cycle_ms: float  # noqa: E111
  history_samples: int  # noqa: E111
  error_streak: int  # noqa: E111
  entity_saturation: float  # noqa: E111
  idle_interval_ms: float  # noqa: E111
  idle_grace_ms: float  # noqa: E111


class SetupFlagPanelEntry(TypedDict):
  """Single setup flag entry used by the diagnostics panel."""  # noqa: E111

  key: str  # noqa: E111
  label: str  # noqa: E111
  label_default: str  # noqa: E111
  label_translation_key: str  # noqa: E111
  enabled: bool  # noqa: E111
  source: str  # noqa: E111
  source_label: str  # noqa: E111
  source_label_default: str  # noqa: E111
  source_label_translation_key: str  # noqa: E111


type SetupFlagSourceBreakdown = dict[str, int]
"""Aggregated setup-flag counts keyed by their source identifier."""


type SetupFlagSourceLabels = dict[str, str]
"""Mapping of setup-flag sources to the human-readable label."""


class SetupFlagsPanelPayload(TypedDict):
  """Structured payload rendered by the setup flag diagnostics panel."""  # noqa: E111

  title: str  # noqa: E111
  title_translation_key: str  # noqa: E111
  title_default: str  # noqa: E111
  description: str  # noqa: E111
  description_translation_key: str  # noqa: E111
  description_default: str  # noqa: E111
  flags: list[SetupFlagPanelEntry]  # noqa: E111
  enabled_count: int  # noqa: E111
  disabled_count: int  # noqa: E111
  source_breakdown: SetupFlagSourceBreakdown  # noqa: E111
  source_labels: SetupFlagSourceLabels  # noqa: E111
  source_labels_default: SetupFlagSourceLabels  # noqa: E111
  source_label_translation_keys: SetupFlagSourceLabels  # noqa: E111
  language: str  # noqa: E111


class CoordinatorRuntimeCycleSnapshot(TypedDict):
  """Snapshot exported for a single coordinator update cycle."""  # noqa: E111

  dog_count: int  # noqa: E111
  errors: int  # noqa: E111
  success_rate: float  # noqa: E111
  duration_ms: float  # noqa: E111
  next_interval_s: float  # noqa: E111
  error_ratio: float  # noqa: E111
  success: bool  # noqa: E111


class PerformanceMonitorCountersSnapshot(TypedDict):
  """Rolling counters surfaced by the performance monitor."""  # noqa: E111

  operations: int  # noqa: E111
  errors: int  # noqa: E111
  cache_hits: int  # noqa: E111
  cache_misses: int  # noqa: E111
  avg_operation_time: float  # noqa: E111
  last_cleanup: str | None  # noqa: E111


class PerformanceMonitorSnapshot(PerformanceMonitorCountersSnapshot):
  """Derived metrics exposed by the performance monitor."""  # noqa: E111

  cache_hit_rate: float  # noqa: E111
  error_rate: float  # noqa: E111
  recent_operations: int  # noqa: E111


class OptimizedEntityMemoryConfig(TypedDict):
  """Memory optimisation tuning options for optimized entity caches."""  # noqa: E111

  max_cache_entries: int  # noqa: E111
  cache_cleanup_threshold: float  # noqa: E111
  weak_ref_cleanup_interval: int  # noqa: E111
  performance_sample_size: int  # noqa: E111


class OptimizedEntityCacheStats(TypedDict):
  """Cache statistics aggregated across optimized entities."""  # noqa: E111

  state_cache_size: int  # noqa: E111
  attributes_cache_size: int  # noqa: E111
  availability_cache_size: int  # noqa: E111


class OptimizedEntityGlobalPerformanceStats(TypedDict):
  """Global performance snapshot returned by :func:`get_global_performance_stats`."""  # noqa: E111

  total_entities_registered: int  # noqa: E111
  active_entities: int  # noqa: E111
  cache_statistics: OptimizedEntityCacheStats  # noqa: E111
  average_operation_time_ms: float  # noqa: E111
  average_cache_hit_rate: float  # noqa: E111
  total_errors: int  # noqa: E111
  entities_with_performance_data: int  # noqa: E111


class OptimizedEntityPerformanceSummary(TypedDict, total=False):
  """Per-entity performance metrics recorded by :class:`PerformanceTracker`."""  # noqa: E111

  status: str  # noqa: E111
  avg_operation_time: float  # noqa: E111
  min_operation_time: float  # noqa: E111
  max_operation_time: float  # noqa: E111
  total_operations: int  # noqa: E111
  error_count: int  # noqa: E111
  error_rate: float  # noqa: E111
  cache_hit_rate: float  # noqa: E111
  total_cache_operations: int  # noqa: E111


class OptimizedEntityMemoryEstimate(TypedDict):
  """Approximate memory usage reported by optimized entities."""  # noqa: E111

  base_entity_bytes: int  # noqa: E111
  cache_contribution_bytes: int  # noqa: E111
  estimated_total_bytes: int  # noqa: E111


class OptimizedEntityPerformanceMetrics(TypedDict):
  """Composite telemetry returned by :meth:`OptimizedEntityBase.get_performance_metrics`."""  # noqa: E111, E501

  entity_id: str  # noqa: E111
  dog_id: str  # noqa: E111
  entity_type: str  # noqa: E111
  initialization_time: str  # noqa: E111
  uptime_seconds: float  # noqa: E111
  performance: OptimizedEntityPerformanceSummary  # noqa: E111
  memory_usage_estimate: OptimizedEntityMemoryEstimate  # noqa: E111


class WebhookSecurityStatus(TypedDict, total=False):
  """Webhook security posture exported via coordinator diagnostics."""  # noqa: E111

  configured: bool  # noqa: E111
  secure: bool  # noqa: E111
  hmac_ready: bool  # noqa: E111
  insecure_configs: tuple[str, ...]  # noqa: E111
  error: NotRequired[str]  # noqa: E111


class CoordinatorPerformanceSnapshotCounts(TypedDict):
  """Update counter payload surfaced via performance diagnostics."""  # noqa: E111

  total: int  # noqa: E111
  successful: int  # noqa: E111
  failed: int  # noqa: E111


class CoordinatorPerformanceSnapshotMetrics(TypedDict, total=False):
  """Performance telemetry attached to coordinator diagnostics snapshots."""  # noqa: E111

  last_update: str | None  # noqa: E111
  last_update_success: bool  # noqa: E111
  success_rate: float  # noqa: E111
  consecutive_errors: int  # noqa: E111
  update_interval_s: float  # noqa: E111
  current_cycle_ms: float | None  # noqa: E111
  rejected_call_count: int  # noqa: E111
  rejection_breaker_count: int  # noqa: E111
  rejection_rate: float | None  # noqa: E111
  last_rejection_time: float | None  # noqa: E111
  last_rejection_breaker_id: str | None  # noqa: E111
  last_rejection_breaker_name: str | None  # noqa: E111
  open_breaker_count: int  # noqa: E111
  half_open_breaker_count: int  # noqa: E111
  unknown_breaker_count: int  # noqa: E111
  open_breakers: list[str]  # noqa: E111
  open_breaker_ids: list[str]  # noqa: E111
  half_open_breakers: list[str]  # noqa: E111
  half_open_breaker_ids: list[str]  # noqa: E111
  unknown_breakers: list[str]  # noqa: E111
  unknown_breaker_ids: list[str]  # noqa: E111
  rejection_breaker_ids: list[str]  # noqa: E111
  rejection_breakers: list[str]  # noqa: E111


class CoordinatorPerformanceSnapshot(TypedDict, total=False):
  """Composite payload returned by performance snapshot helpers."""  # noqa: E111

  update_counts: CoordinatorPerformanceSnapshotCounts  # noqa: E111
  performance_metrics: CoordinatorPerformanceSnapshotMetrics  # noqa: E111
  adaptive_polling: AdaptivePollingDiagnostics  # noqa: E111
  entity_budget: EntityBudgetSummary  # noqa: E111
  webhook_security: WebhookSecurityStatus  # noqa: E111
  resilience_summary: CoordinatorResilienceSummary  # noqa: E111
  rejection_metrics: CoordinatorRejectionMetrics  # noqa: E111
  bool_coercion: BoolCoercionSummary  # noqa: E111
  resilience: CoordinatorResilienceDiagnostics  # noqa: E111
  service_execution: CoordinatorServiceExecutionSummary  # noqa: E111
  last_cycle: CoordinatorRuntimeCycleSnapshot  # noqa: E111


CoordinatorSecurityAdaptiveCheck = TypedDict(
  "CoordinatorSecurityAdaptiveCheck",
  {
    "pass": Required[bool],
    "current_ms": Required[float],
    "target_ms": Required[float],
    "threshold_ms": Required[float],
    "reason": NotRequired[str],
  },
  total=False,
)


CoordinatorSecurityEntityCheck = TypedDict(
  "CoordinatorSecurityEntityCheck",
  {
    "pass": Required[bool],
    "summary": Required[EntityBudgetSummary],
    "threshold_percent": Required[float],
    "reason": NotRequired[str],
  },
  total=False,
)


CoordinatorSecurityWebhookCheck = TypedDict(
  "CoordinatorSecurityWebhookCheck",
  {
    "pass": Required[bool],
    "configured": Required[bool],
    "secure": Required[bool],
    "hmac_ready": Required[bool],
    "insecure_configs": Required[tuple[str, ...]],
    "error": NotRequired[str],
    "reason": NotRequired[str],
  },
  total=False,
)


class CoordinatorSecurityChecks(TypedDict):
  """Collection of security check results surfaced to diagnostics."""  # noqa: E111

  adaptive_polling: CoordinatorSecurityAdaptiveCheck  # noqa: E111
  entity_budget: CoordinatorSecurityEntityCheck  # noqa: E111
  webhooks: CoordinatorSecurityWebhookCheck  # noqa: E111


class CoordinatorSecurityScorecard(TypedDict):
  """Aggregated security score surfaced via diagnostics endpoints."""  # noqa: E111

  status: Literal["pass", "fail"]  # noqa: E111
  checks: CoordinatorSecurityChecks  # noqa: E111


class CircuitBreakerStatsPayload(TypedDict, total=False):
  """Circuit breaker statistics forwarded to diagnostics panels."""  # noqa: E111

  breaker_id: str  # noqa: E111
  state: str  # noqa: E111
  failure_count: int  # noqa: E111
  success_count: int  # noqa: E111
  last_failure_time: float | None  # noqa: E111
  last_state_change: float | None  # noqa: E111
  last_success_time: float  # noqa: E111
  last_rejection_time: float | None  # noqa: E111
  total_calls: int  # noqa: E111
  total_failures: int  # noqa: E111
  total_successes: int  # noqa: E111
  rejected_calls: int  # noqa: E111


class CircuitBreakerStateSummary(TypedDict):
  """Aggregated state counters across all circuit breakers."""  # noqa: E111

  closed: int  # noqa: E111
  open: int  # noqa: E111
  half_open: int  # noqa: E111
  unknown: int  # noqa: E111
  other: int  # noqa: E111


class CoordinatorResilienceSummary(TypedDict):
  """Condensed view of coordinator resilience health."""  # noqa: E111

  total_breakers: int  # noqa: E111
  states: CircuitBreakerStateSummary  # noqa: E111
  failure_count: int  # noqa: E111
  success_count: int  # noqa: E111
  total_calls: int  # noqa: E111
  total_failures: int  # noqa: E111
  total_successes: int  # noqa: E111
  rejected_call_count: int  # noqa: E111
  last_failure_time: float | None  # noqa: E111
  last_state_change: float | None  # noqa: E111
  last_success_time: float | None  # noqa: E111
  last_rejection_time: float | None  # noqa: E111
  recovery_latency: float | None  # noqa: E111
  recovery_breaker_id: str | None  # noqa: E111
  recovery_breaker_name: NotRequired[str | None]  # noqa: E111
  last_rejection_breaker_id: NotRequired[str | None]  # noqa: E111
  last_rejection_breaker_name: NotRequired[str | None]  # noqa: E111
  rejection_rate: float | None  # noqa: E111
  open_breaker_count: int  # noqa: E111
  half_open_breaker_count: int  # noqa: E111
  unknown_breaker_count: int  # noqa: E111
  open_breakers: list[str]  # noqa: E111
  open_breaker_ids: list[str]  # noqa: E111
  half_open_breakers: list[str]  # noqa: E111
  half_open_breaker_ids: list[str]  # noqa: E111
  unknown_breakers: list[str]  # noqa: E111
  unknown_breaker_ids: list[str]  # noqa: E111
  rejection_breaker_count: int  # noqa: E111
  rejection_breakers: list[str]  # noqa: E111
  rejection_breaker_ids: list[str]  # noqa: E111


class CoordinatorResilienceDiagnostics(TypedDict, total=False):
  """Structured resilience payload surfaced through coordinator statistics."""  # noqa: E111

  breakers: dict[str, CircuitBreakerStatsPayload]  # noqa: E111
  summary: CoordinatorResilienceSummary  # noqa: E111


class CoordinatorStatisticsPayload(TypedDict):
  """Structured payload returned by :class:`CoordinatorMetrics.update_statistics`."""  # noqa: E111

  update_counts: CoordinatorUpdateCounts  # noqa: E111
  performance_metrics: CoordinatorPerformanceMetrics  # noqa: E111
  health_indicators: CoordinatorHealthIndicators  # noqa: E111
  repairs: NotRequired[CoordinatorRepairsSummary]  # noqa: E111
  reconfigure: NotRequired[ReconfigureTelemetrySummary]  # noqa: E111
  entity_budget: NotRequired[EntityBudgetSummary]  # noqa: E111
  adaptive_polling: NotRequired[AdaptivePollingDiagnostics]  # noqa: E111
  resilience: NotRequired[CoordinatorResilienceDiagnostics]  # noqa: E111
  rejection_metrics: NotRequired[CoordinatorRejectionMetrics]  # noqa: E111
  runtime_store: NotRequired[CoordinatorRuntimeStoreSummary]  # noqa: E111


class CoordinatorRuntimeContext(TypedDict):
  """Context metadata included in runtime statistics snapshots."""  # noqa: E111

  total_dogs: int  # noqa: E111
  last_update: Any  # noqa: E111
  update_interval: float  # noqa: E111


class CoordinatorErrorSummary(TypedDict):
  """Error summary included with coordinator runtime statistics."""  # noqa: E111

  consecutive_errors: int  # noqa: E111
  error_rate: float  # noqa: E111
  rejection_rate: NotRequired[float | None]  # noqa: E111
  rejected_call_count: NotRequired[int]  # noqa: E111
  rejection_breaker_count: NotRequired[int]  # noqa: E111
  open_breaker_count: NotRequired[int]  # noqa: E111
  half_open_breaker_count: NotRequired[int]  # noqa: E111
  unknown_breaker_count: NotRequired[int]  # noqa: E111
  open_breakers: NotRequired[list[str]]  # noqa: E111
  open_breaker_ids: NotRequired[list[str]]  # noqa: E111
  half_open_breakers: NotRequired[list[str]]  # noqa: E111
  half_open_breaker_ids: NotRequired[list[str]]  # noqa: E111
  unknown_breakers: NotRequired[list[str]]  # noqa: E111
  unknown_breaker_ids: NotRequired[list[str]]  # noqa: E111
  rejection_breaker_ids: NotRequired[list[str]]  # noqa: E111
  rejection_breakers: NotRequired[list[str]]  # noqa: E111


class CoordinatorServiceExecutionSummary(TypedDict, total=False):
  """Aggregated service execution telemetry surfaced via runtime statistics."""  # noqa: E111

  guard_metrics: HelperManagerGuardMetrics  # noqa: E111
  entity_factory_guard: EntityFactoryGuardMetricsSnapshot  # noqa: E111
  rejection_metrics: CoordinatorRejectionMetrics  # noqa: E111


class CoordinatorCachePerformance(TypedDict):
  """Cache performance counters surfaced during runtime diagnostics."""  # noqa: E111

  hits: int  # noqa: E111
  misses: int  # noqa: E111
  entries: int  # noqa: E111
  hit_rate: float  # noqa: E111


class CoordinatorRuntimeStatisticsPayload(TypedDict):
  """Payload returned by :class:`CoordinatorMetrics.runtime_statistics`."""  # noqa: E111

  update_counts: CoordinatorUpdateCounts  # noqa: E111
  context: CoordinatorRuntimeContext  # noqa: E111
  error_summary: CoordinatorErrorSummary  # noqa: E111
  cache_performance: CoordinatorCachePerformance  # noqa: E111
  repairs: NotRequired[CoordinatorRepairsSummary]  # noqa: E111
  reconfigure: NotRequired[ReconfigureTelemetrySummary]  # noqa: E111
  entity_budget: NotRequired[EntityBudgetSummary]  # noqa: E111
  adaptive_polling: NotRequired[AdaptivePollingDiagnostics]  # noqa: E111
  resilience: NotRequired[CoordinatorResilienceDiagnostics]  # noqa: E111
  rejection_metrics: NotRequired[CoordinatorRejectionMetrics]  # noqa: E111
  bool_coercion: NotRequired[BoolCoercionSummary]  # noqa: E111
  service_execution: NotRequired[CoordinatorServiceExecutionSummary]  # noqa: E111
  runtime_store: NotRequired[CoordinatorRuntimeStoreSummary]  # noqa: E111


class CoordinatorModuleErrorPayload(TypedDict, total=False):
  """Fallback payload recorded when a module cannot provide telemetry."""  # noqa: E111

  status: Required[str]  # noqa: E111
  reason: NotRequired[str]  # noqa: E111
  message: NotRequired[str]  # noqa: E111
  error: NotRequired[str]  # noqa: E111
  error_type: NotRequired[str]  # noqa: E111
  retry_after: NotRequired[int | float | None]  # noqa: E111


CoordinatorModuleState = ModuleAdapterPayload | CoordinatorModuleErrorPayload


CoordinatorTypedModuleName = Literal[
  "feeding",
  "garden",
  "geofencing",
  "gps",
  "health",
  "walk",
  "weather",
]


type CoordinatorUntypedModuleState = JSONMutableMapping
"""Fallback module payload used when adapters expose open-ended mappings."""


type CoordinatorModuleLookupResult = (
  CoordinatorModuleState | CoordinatorUntypedModuleState
)
"""Result payload returned when accessing coordinator module snapshots."""


type OptimizedEntityStateCachePayload = (
  CoordinatorDogData | CoordinatorModuleState | CoordinatorUntypedModuleState
)
"""Union of cache payloads stored by :mod:`optimized_entity_base`."""


type OptimizedEntityAttributesPayload = JSONMutableMapping
"""Mutable attribute payload generated by optimized entities."""


class DeviceLinkDetails(TypedDict, total=False):
  """Device metadata mapping used by :class:`PawControlDeviceLinkMixin`."""  # noqa: E111

  manufacturer: str  # noqa: E111
  model: str  # noqa: E111
  sw_version: str | None  # noqa: E111
  configuration_url: str | None  # noqa: E111
  breed: str | None  # noqa: E111
  microchip_id: str | None  # noqa: E111
  serial_number: str | None  # noqa: E111
  hw_version: str | None  # noqa: E111
  suggested_area: str | None  # noqa: E111
  extra_identifiers: Sequence[tuple[str, str]]  # noqa: E111


class CoordinatorDogData(TypedDict, total=False):
  """Runtime payload stored by the coordinator for a single dog."""  # noqa: E111

  dog_info: DogConfigData  # noqa: E111
  status: str  # noqa: E111
  status_snapshot: NotRequired[DogStatusSnapshot]  # noqa: E111
  last_update: str | None  # noqa: E111
  gps: NotRequired[CoordinatorModuleState]  # noqa: E111
  geofencing: NotRequired[CoordinatorModuleState]  # noqa: E111
  feeding: NotRequired[CoordinatorModuleState]  # noqa: E111
  walk: NotRequired[CoordinatorModuleState]  # noqa: E111
  health: NotRequired[CoordinatorModuleState]  # noqa: E111
  weather: NotRequired[CoordinatorModuleState]  # noqa: E111
  garden: NotRequired[CoordinatorModuleState]  # noqa: E111
  profile: NotRequired[DogProfileSnapshot]  # noqa: E111
  notifications: NotRequired[JSONMutableMapping]  # noqa: E111
  dashboard: NotRequired[JSONMutableMapping]  # noqa: E111
  visitor: NotRequired[JSONMutableMapping]  # noqa: E111
  grooming: NotRequired[JSONMutableMapping]  # noqa: E111
  medication: NotRequired[JSONMutableMapping]  # noqa: E111
  training: NotRequired[JSONMutableMapping]  # noqa: E111
  text_values: NotRequired[DogTextSnapshot]  # noqa: E111


class DogStatusSnapshot(TypedDict, total=False):
  """Centralized status snapshot for a dog."""  # noqa: E111

  dog_id: str  # noqa: E111
  state: str  # noqa: E111
  zone: str | None  # noqa: E111
  is_home: bool  # noqa: E111
  in_safe_zone: bool  # noqa: E111
  on_walk: bool  # noqa: E111
  needs_walk: bool  # noqa: E111
  is_hungry: bool  # noqa: E111


CoordinatorDataPayload = dict[str, CoordinatorDogData]


class CoordinatorRejectionMetrics(TypedDict):
  """Normalised rejection counters exposed via diagnostics payloads."""  # noqa: E111

  schema_version: Literal[4]  # noqa: E111
  rejected_call_count: int  # noqa: E111
  rejection_breaker_count: int  # noqa: E111
  rejection_rate: float | None  # noqa: E111
  last_rejection_time: float | None  # noqa: E111
  last_rejection_breaker_id: str | None  # noqa: E111
  last_rejection_breaker_name: str | None  # noqa: E111
  last_failure_reason: str | None  # noqa: E111
  failure_reasons: dict[str, int]  # noqa: E111
  open_breaker_count: int  # noqa: E111
  half_open_breaker_count: int  # noqa: E111
  unknown_breaker_count: int  # noqa: E111
  open_breakers: list[str]  # noqa: E111
  open_breaker_ids: list[str]  # noqa: E111
  half_open_breakers: list[str]  # noqa: E111
  half_open_breaker_ids: list[str]  # noqa: E111
  unknown_breakers: list[str]  # noqa: E111
  unknown_breaker_ids: list[str]  # noqa: E111
  rejection_breaker_ids: list[str]  # noqa: E111
  rejection_breakers: list[str]  # noqa: E111


type RejectionMetricsTarget = (
  CoordinatorRejectionMetrics | CoordinatorPerformanceMetrics | JSONMutableMapping
)
"""Mutable mapping that can receive rejection metric updates."""


type RejectionMetricsSource = (
  CoordinatorRejectionMetrics | CoordinatorResilienceSummary | JSONMapping
)
"""Mapping payload that exposes coordinator rejection metrics."""


class SystemHealthThresholdDetail(TypedDict, total=False):
  """Threshold details exposed through the system health endpoint."""  # noqa: E111

  count: int  # noqa: E111
  ratio: float  # noqa: E111
  percentage: float  # noqa: E111


class SystemHealthThresholdSummary(TypedDict, total=False):
  """Source metadata for guard and breaker threshold indicators."""  # noqa: E111

  source: Required[str]  # noqa: E111
  source_key: str | None  # noqa: E111
  warning: SystemHealthThresholdDetail  # noqa: E111
  critical: SystemHealthThresholdDetail  # noqa: E111


class SystemHealthGuardReasonEntry(TypedDict):
  """Top guard skip reason surfaced through system health."""  # noqa: E111

  reason: str  # noqa: E111
  count: int  # noqa: E111


type SystemHealthIndicatorLevel = Literal["critical", "warning", "normal"]


class SystemHealthIndicatorPayload(TypedDict, total=False):
  """Indicator payload summarising guard/breaker health."""  # noqa: E111

  level: Required[SystemHealthIndicatorLevel]  # noqa: E111
  color: Required[Literal["red", "amber", "green"]]  # noqa: E111
  message: Required[str]  # noqa: E111
  metric_type: Required[str]  # noqa: E111
  context: str  # noqa: E111
  metric: float | int  # noqa: E111
  threshold: float | int  # noqa: E111
  threshold_type: str  # noqa: E111
  threshold_source: str  # noqa: E111


class SystemHealthGuardSummary(TypedDict):
  """Aggregated guard statistics returned by system health."""  # noqa: E111

  executed: int  # noqa: E111
  skipped: int  # noqa: E111
  total_calls: int  # noqa: E111
  skip_ratio: float  # noqa: E111
  skip_percentage: float  # noqa: E111
  has_skips: bool  # noqa: E111
  reasons: dict[str, int]  # noqa: E111
  top_reasons: list[SystemHealthGuardReasonEntry]  # noqa: E111
  thresholds: SystemHealthThresholdSummary  # noqa: E111
  indicator: SystemHealthIndicatorPayload  # noqa: E111


class SystemHealthBreakerOverview(TypedDict):
  """Breaker metrics surfaced through the system health endpoint."""  # noqa: E111

  status: Literal["open", "recovering", "monitoring", "healthy"]  # noqa: E111
  open_breaker_count: int  # noqa: E111
  half_open_breaker_count: int  # noqa: E111
  unknown_breaker_count: int  # noqa: E111
  rejection_rate: float  # noqa: E111
  last_rejection_breaker_id: str | None  # noqa: E111
  last_rejection_breaker_name: str | None  # noqa: E111
  last_rejection_time: float | None  # noqa: E111
  open_breakers: list[str]  # noqa: E111
  half_open_breakers: list[str]  # noqa: E111
  unknown_breakers: list[str]  # noqa: E111
  thresholds: SystemHealthThresholdSummary  # noqa: E111
  indicator: SystemHealthIndicatorPayload  # noqa: E111


class SystemHealthServiceStatus(TypedDict):
  """Composite indicator status for guard and breaker telemetry."""  # noqa: E111

  guard: SystemHealthIndicatorPayload  # noqa: E111
  breaker: SystemHealthIndicatorPayload  # noqa: E111
  overall: SystemHealthIndicatorPayload  # noqa: E111


type SystemHealthRemainingQuota = (
  Literal[
    "unknown",
    "untracked",
    "unlimited",
  ]
  | int
)


class SystemHealthServiceExecutionSnapshot(TypedDict):
  """Structured service execution payload for system health diagnostics."""  # noqa: E111

  guard_metrics: HelperManagerGuardMetrics  # noqa: E111
  guard_summary: SystemHealthGuardSummary  # noqa: E111
  entity_factory_guard: EntityFactoryGuardMetricsSnapshot  # noqa: E111
  rejection_metrics: CoordinatorRejectionMetrics  # noqa: E111
  breaker_overview: SystemHealthBreakerOverview  # noqa: E111
  status: SystemHealthServiceStatus  # noqa: E111
  manual_events: ManualResilienceEventsTelemetry  # noqa: E111


class SystemHealthInfoPayload(TypedDict):
  """Top-level system health payload exposed by the integration."""  # noqa: E111

  can_reach_backend: bool  # noqa: E111
  remaining_quota: SystemHealthRemainingQuota  # noqa: E111
  service_execution: SystemHealthServiceExecutionSnapshot  # noqa: E111
  runtime_store: RuntimeStoreCompatibilitySnapshot  # noqa: E111


class DogProfileSnapshot(TypedDict, total=False):
  """Profile metadata exposed through coordinator dog snapshots."""  # noqa: E111

  birthdate: str | None  # noqa: E111
  adoption_date: str | None  # noqa: E111
  diet_start_date: str | None  # noqa: E111
  diet_end_date: str | None  # noqa: E111
  training_start_date: str | None  # noqa: E111
  next_training_date: str | None  # noqa: E111
  dog_age: int | None  # noqa: E111
  dog_weight: float | None  # noqa: E111
  dog_size: str | None  # noqa: E111
  entity_profile: str | None  # noqa: E111


class DogConfigData(TypedDict, total=False):
  """Type definition for comprehensive dog configuration data.

  This TypedDict defines the complete structure for dog configuration including
  required identification fields and optional characteristics. The structure
  supports device discovery integration and comprehensive dog profiling.

  The design uses Required[] for mandatory fields to ensure type safety while
  maintaining flexibility for optional characteristics that may not be known
  at configuration time.

  Attributes:
      dog_id: Unique identifier for the dog (required, must be URL-safe)
      dog_name: Display name for the dog (required, user-friendly)
      dog_breed: Breed information (optional, for breed-specific features)
      dog_age: Age in years (optional, affects health and feeding calculations)
      dog_weight: Weight in kilograms (optional, used for portion calculations)
      dog_size: Size category from VALID_DOG_SIZES (optional, affects recommendations)
      dog_color: Color description (optional, for identification)
      microchip_id: Microchip identifier (optional, for veterinary records)
      vet_contact: Veterinary contact information (optional, emergency use)
      emergency_contact: Emergency contact details (optional, critical situations)
      modules: Module enablement configuration (affects available features)
      discovery_info: Device discovery metadata (optional, for hardware integration)
  """  # noqa: E111

  # Required fields - must be present for valid configuration  # noqa: E114
  dog_id: Required[str]  # noqa: E111
  dog_name: Required[str]  # noqa: E111

  # Optional fields with comprehensive coverage for dog characteristics  # noqa: E114
  dog_breed: NotRequired[str | None]  # noqa: E111
  dog_age: NotRequired[int | None]  # noqa: E111
  dog_weight: NotRequired[float | None]  # noqa: E111
  dog_size: NotRequired[str | None]  # noqa: E111
  dog_color: NotRequired[str | None]  # noqa: E111
  microchip_id: NotRequired[str | None]  # noqa: E111
  vet_contact: NotRequired[str | None]  # noqa: E111
  emergency_contact: NotRequired[str | None]  # noqa: E111
  modules: NotRequired[DogModulesConfig]  # noqa: E111
  dog_image: NotRequired[str | None]  # noqa: E111
  discovery_info: NotRequired[ConfigFlowDiscoveryData]  # noqa: E111
  gps_config: NotRequired[DogGPSConfig]  # noqa: E111
  walk_config: NotRequired[DogWalkConfig]  # noqa: E111
  feeding_config: NotRequired[DogFeedingConfig]  # noqa: E111
  health_config: NotRequired[DogHealthConfig]  # noqa: E111
  feeding: NotRequired[JSONMutableMapping]  # noqa: E111
  walk: NotRequired[JSONMutableMapping]  # noqa: E111
  door_sensor: NotRequired[str | None]  # noqa: E111
  door_sensor_settings: NotRequired[DoorSensorSettingsPayload | None]  # noqa: E111
  text_values: NotRequired[DogTextSnapshot]  # noqa: E111
  text_metadata: NotRequired[DogTextMetadataSnapshot]  # noqa: E111


# TypedDict key literals for dog configuration structures.
DOG_ID_FIELD: Final[Literal["dog_id"]] = "dog_id"
DOG_NAME_FIELD: Final[Literal["dog_name"]] = "dog_name"
DOG_BREED_FIELD: Final[Literal["dog_breed"]] = "dog_breed"
DOG_AGE_FIELD: Final[Literal["dog_age"]] = "dog_age"
DOG_WEIGHT_FIELD: Final[Literal["dog_weight"]] = "dog_weight"
DOG_SIZE_FIELD: Final[Literal["dog_size"]] = "dog_size"
DOG_MODULES_FIELD: Final[Literal["modules"]] = "modules"
DOG_DISCOVERY_FIELD: Final[Literal["discovery_info"]] = "discovery_info"
DOG_COLOR_FIELD: Final[Literal["dog_color"]] = "dog_color"
DOG_MICROCHIP_ID_FIELD: Final[Literal["microchip_id"]] = "microchip_id"
DOG_VET_CONTACT_FIELD: Final[Literal["vet_contact"]] = "vet_contact"
DOG_EMERGENCY_CONTACT_FIELD: Final[Literal["emergency_contact"]] = "emergency_contact"
DOG_OPTIONS_FIELD: Final[Literal["dog_options"]] = "dog_options"
DOG_FEEDING_CONFIG_FIELD: Final[Literal["feeding_config"]] = "feeding_config"
DOG_HEALTH_CONFIG_FIELD: Final[Literal["health_config"]] = "health_config"
DOG_GPS_CONFIG_FIELD: Final[Literal["gps_config"]] = "gps_config"
DOG_WALK_CONFIG_FIELD: Final[Literal["walk_config"]] = "walk_config"
DOG_IMAGE_FIELD: Final[Literal["dog_image"]] = "dog_image"
DOG_TEXT_VALUES_FIELD: Final[Literal["text_values"]] = "text_values"
DOG_TEXT_METADATA_FIELD: Final[Literal["text_metadata"]] = "text_metadata"
WALK_IN_PROGRESS_FIELD: Final[Literal["walk_in_progress"]] = "walk_in_progress"
VISITOR_MODE_ACTIVE_FIELD: Final[Literal["visitor_mode_active"]] = "visitor_mode_active"

# Text snapshot keys maintained for text entity persistence.
TextSnapshotKey = Literal[
  "notes",
  "custom_label",
  "walk_notes",
  "current_walk_label",
  "health_notes",
  "medication_notes",
  "vet_notes",
  "grooming_notes",
  "custom_message",
  "emergency_contact",
  "microchip",
  "breeder_info",
  "registration",
  "insurance_info",
  "allergies",
  "training_notes",
  "behavior_notes",
  "location_description",
]

_DOG_TEXT_SNAPSHOT_KEYS: Final[tuple[TextSnapshotKey, ...]] = (
  "notes",
  "custom_label",
  "walk_notes",
  "current_walk_label",
  "health_notes",
  "medication_notes",
  "vet_notes",
  "grooming_notes",
  "custom_message",
  "emergency_contact",
  "microchip",
  "breeder_info",
  "registration",
  "insurance_info",
  "allergies",
  "training_notes",
  "behavior_notes",
  "location_description",
)


def ensure_dog_text_snapshot(
  payload: Mapping[str, JSONValue],
) -> DogTextSnapshot | None:
  """Return a normalised :class:`DogTextSnapshot` built from ``payload``."""  # noqa: E111

  snapshot: dict[str, str] = {}  # noqa: E111
  for key in _DOG_TEXT_SNAPSHOT_KEYS:  # noqa: E111
    raw_value = payload.get(key)
    if isinstance(raw_value, str):
      snapshot[key] = raw_value  # noqa: E111

  if not snapshot:  # noqa: E111
    return None

  return cast(DogTextSnapshot, snapshot)  # noqa: E111


def _normalise_text_metadata_entry(
  raw_value: object | None,
) -> DogTextMetadataEntry | None:
  """Return a typed metadata entry built from ``raw_value`` when possible."""  # noqa: E111

  if isinstance(raw_value, Mapping):  # noqa: E111
    entry: dict[str, str | None] = {}
    last_updated = raw_value.get("last_updated")
    if isinstance(last_updated, str) and last_updated:
      entry["last_updated"] = last_updated  # noqa: E111

    context_id = raw_value.get("context_id")
    if isinstance(context_id, str) and context_id:
      entry["context_id"] = context_id  # noqa: E111

    parent_id = raw_value.get("parent_id")
    if isinstance(parent_id, str) and parent_id:
      entry["parent_id"] = parent_id  # noqa: E111

    user_id = raw_value.get("user_id")
    if isinstance(user_id, str) and user_id:
      entry["user_id"] = user_id  # noqa: E111

    if not entry:
      return None  # noqa: E111

    return cast(DogTextMetadataEntry, entry)

  if isinstance(raw_value, str) and raw_value:  # noqa: E111
    return cast(DogTextMetadataEntry, {"last_updated": raw_value})

  return None  # noqa: E111


def ensure_dog_text_metadata_snapshot(
  payload: Mapping[str, JSONValue],
) -> DogTextMetadataSnapshot | None:
  """Return a normalised :class:`DogTextMetadataSnapshot` from ``payload``."""  # noqa: E111

  metadata: dict[str, DogTextMetadataEntry] = {}  # noqa: E111
  for key in _DOG_TEXT_SNAPSHOT_KEYS:  # noqa: E111
    raw_value = payload.get(key)
    entry = _normalise_text_metadata_entry(raw_value)
    if entry is not None:
      metadata[key] = entry  # noqa: E111

  if not metadata:  # noqa: E111
    return None

  return cast(DogTextMetadataSnapshot, metadata)  # noqa: E111


# Field literals for external entity configuration helpers.
GPS_SOURCE_FIELD: Final[Literal["gps_source"]] = "gps_source"
DOOR_SENSOR_FIELD: Final[Literal["door_sensor"]] = "door_sensor"
NOTIFY_FALLBACK_FIELD: Final[Literal["notify_fallback"]] = "notify_fallback"

# Field literals for dashboard setup preferences.
DASHBOARD_ENABLED_FIELD: Final[Literal["dashboard_enabled"]] = "dashboard_enabled"
DASHBOARD_AUTO_CREATE_FIELD: Final[Literal["dashboard_auto_create"]] = (
  "dashboard_auto_create"
)
DASHBOARD_PER_DOG_FIELD: Final[Literal["dashboard_per_dog"]] = "dashboard_per_dog"
DASHBOARD_THEME_FIELD: Final[Literal["dashboard_theme"]] = "dashboard_theme"
DASHBOARD_MODE_FIELD: Final[Literal["dashboard_mode"]] = "dashboard_mode"
SHOW_STATISTICS_FIELD: Final[Literal["show_statistics"]] = "show_statistics"
SHOW_MAPS_FIELD: Final[Literal["show_maps"]] = "show_maps"
SHOW_HEALTH_CHARTS_FIELD: Final[Literal["show_health_charts"]] = "show_health_charts"
SHOW_FEEDING_SCHEDULE_FIELD: Final[Literal["show_feeding_schedule"]] = (
  "show_feeding_schedule"
)
SHOW_ALERTS_FIELD: Final[Literal["show_alerts"]] = "show_alerts"
COMPACT_MODE_FIELD: Final[Literal["compact_mode"]] = "compact_mode"
AUTO_REFRESH_FIELD: Final[Literal["auto_refresh"]] = "auto_refresh"


def ensure_dog_config_data(data: Mapping[str, JSONValue]) -> DogConfigData | None:
  """Return a ``DogConfigData`` structure extracted from ``data`` mappings."""  # noqa: E111

  dog_id = data.get(DOG_ID_FIELD)  # noqa: E111
  dog_name = data.get(DOG_NAME_FIELD)  # noqa: E111

  if not isinstance(dog_id, str) or not dog_id:  # noqa: E111
    return None
  if not isinstance(dog_name, str) or not dog_name:  # noqa: E111
    return None

  config: DogConfigData = {  # noqa: E111
    DOG_ID_FIELD: dog_id,
    DOG_NAME_FIELD: dog_name,
  }

  breed = data.get(DOG_BREED_FIELD)  # noqa: E111
  if isinstance(breed, str):  # noqa: E111
    config[DOG_BREED_FIELD] = breed

  age = data.get(DOG_AGE_FIELD)  # noqa: E111
  if isinstance(age, int):  # noqa: E111
    config[DOG_AGE_FIELD] = age

  weight = data.get(DOG_WEIGHT_FIELD)  # noqa: E111
  if isinstance(weight, int | float):  # noqa: E111
    config[DOG_WEIGHT_FIELD] = float(weight)

  size = data.get(DOG_SIZE_FIELD)  # noqa: E111
  if isinstance(size, str):  # noqa: E111
    config[DOG_SIZE_FIELD] = size

  color = data.get(DOG_COLOR_FIELD)  # noqa: E111
  if isinstance(color, str) and color:  # noqa: E111
    config[DOG_COLOR_FIELD] = color

  microchip_id = data.get(DOG_MICROCHIP_ID_FIELD)  # noqa: E111
  if isinstance(microchip_id, str) and microchip_id:  # noqa: E111
    config[DOG_MICROCHIP_ID_FIELD] = microchip_id

  vet_contact = data.get(DOG_VET_CONTACT_FIELD)  # noqa: E111
  if isinstance(vet_contact, str) and vet_contact:  # noqa: E111
    config[DOG_VET_CONTACT_FIELD] = vet_contact

  emergency_contact = data.get(DOG_EMERGENCY_CONTACT_FIELD)  # noqa: E111
  if isinstance(emergency_contact, str) and emergency_contact:  # noqa: E111
    config[DOG_EMERGENCY_CONTACT_FIELD] = emergency_contact

  modules_payload = data.get(DOG_MODULES_FIELD)  # noqa: E111
  if _is_modules_projection_like(modules_payload):  # noqa: E111
    config[DOG_MODULES_FIELD] = coerce_dog_modules_config(
      cast(DogModulesProjection, modules_payload),
    )
  elif isinstance(modules_payload, Mapping):  # noqa: E111
    config[DOG_MODULES_FIELD] = coerce_dog_modules_config(
      cast(Mapping[str, object], modules_payload),
    )

  discovery_info = data.get(DOG_DISCOVERY_FIELD)  # noqa: E111
  if isinstance(discovery_info, Mapping):  # noqa: E111
    config[DOG_DISCOVERY_FIELD] = cast(
      ConfigFlowDiscoveryData,
      dict(discovery_info),
    )

  gps_config = data.get(DOG_GPS_CONFIG_FIELD)  # noqa: E111
  if isinstance(gps_config, Mapping):  # noqa: E111
    config[DOG_GPS_CONFIG_FIELD] = cast(DogGPSConfig, dict(gps_config))

  walk_config = data.get(DOG_WALK_CONFIG_FIELD)  # noqa: E111
  if isinstance(walk_config, Mapping):  # noqa: E111
    config[DOG_WALK_CONFIG_FIELD] = cast(DogWalkConfig, dict(walk_config))

  feeding_config = data.get(DOG_FEEDING_CONFIG_FIELD)  # noqa: E111
  if isinstance(feeding_config, Mapping):  # noqa: E111
    config[DOG_FEEDING_CONFIG_FIELD] = cast(
      DogFeedingConfig,
      dict(feeding_config),
    )

  health_config = data.get(DOG_HEALTH_CONFIG_FIELD)  # noqa: E111
  if isinstance(health_config, Mapping):  # noqa: E111
    config[DOG_HEALTH_CONFIG_FIELD] = cast(
      DogHealthConfig,
      dict(health_config),
    )

  feeding_module = data.get("feeding")  # noqa: E111
  if isinstance(feeding_module, Mapping):  # noqa: E111
    config["feeding"] = ensure_json_mapping(feeding_module)

  walk_module = data.get("walk")  # noqa: E111
  if isinstance(walk_module, Mapping):  # noqa: E111
    config["walk"] = ensure_json_mapping(walk_module)

  door_sensor = data.get(CONF_DOOR_SENSOR)  # noqa: E111
  if isinstance(door_sensor, str):  # noqa: E111
    trimmed_sensor = door_sensor.strip()
    if trimmed_sensor:
      config["door_sensor"] = trimmed_sensor  # noqa: E111

  normalised_settings = _normalise_door_sensor_settings_payload(  # noqa: E111
    data.get(CONF_DOOR_SENSOR_SETTINGS),
  )
  if normalised_settings is not None:  # noqa: E111
    config["door_sensor_settings"] = normalised_settings

  text_payload = data.get(DOG_TEXT_VALUES_FIELD)  # noqa: E111
  if isinstance(text_payload, Mapping):  # noqa: E111
    snapshot = ensure_dog_text_snapshot(text_payload)
    if snapshot is not None:
      config[DOG_TEXT_VALUES_FIELD] = snapshot  # noqa: E111

  text_metadata_payload = data.get(DOG_TEXT_METADATA_FIELD)  # noqa: E111
  if isinstance(text_metadata_payload, Mapping):  # noqa: E111
    metadata_snapshot = ensure_dog_text_metadata_snapshot(
      text_metadata_payload,
    )
    if metadata_snapshot is not None:
      config[DOG_TEXT_METADATA_FIELD] = metadata_snapshot  # noqa: E111

  return config  # noqa: E111


RawDogConfig = JSONMapping | DogConfigData


def _normalise_door_sensor_settings_payload(
  payload: Any,
) -> DoorSensorSettingsPayload | None:
  """Return a stored payload for door sensor overrides when available."""  # noqa: E111

  if payload is None:  # noqa: E111
    return None

  from .door_sensor_manager import ensure_door_sensor_settings_config  # noqa: E111

  if isinstance(payload, DoorSensorSettingsConfig):  # noqa: E111
    settings = payload
  elif isinstance(payload, Mapping):  # noqa: E111
    settings = ensure_door_sensor_settings_config(payload)
  else:  # noqa: E111
    return None

  settings_payload = cast(DoorSensorSettingsPayload, asdict(settings))  # noqa: E111
  if not settings_payload:  # noqa: E111
    return None

  if settings_payload == cast(  # noqa: E111
    DoorSensorSettingsPayload,
    asdict(DEFAULT_DOOR_SENSOR_SETTINGS),
  ):
    return None

  return settings_payload  # noqa: E111


def ensure_dog_options_entry(
  value: JSONLikeMapping,
  /,
  *,
  dog_id: str | None = None,
) -> DogOptionsEntry:
  """Return a normalised :class:`DogOptionsEntry` built from ``value``."""  # noqa: E111

  entry: DogOptionsEntry = {}  # noqa: E111

  raw_dog_id = value.get(DOG_ID_FIELD)  # noqa: E111
  if isinstance(raw_dog_id, str) and raw_dog_id:  # noqa: E111
    entry["dog_id"] = raw_dog_id
  elif isinstance(dog_id, str) and dog_id:  # noqa: E111
    entry["dog_id"] = dog_id

  modules_payload = value.get(DOG_MODULES_FIELD)  # noqa: E111
  if _is_modules_projection_like(modules_payload):  # noqa: E111
    entry["modules"] = coerce_dog_modules_config(
      cast(DogModulesProjection, modules_payload),
    )
  elif isinstance(modules_payload, Mapping):  # noqa: E111
    entry["modules"] = coerce_dog_modules_config(
      cast(Mapping[str, object], modules_payload),
    )

  notifications_payload = value.get(CONF_NOTIFICATIONS)  # noqa: E111
  if isinstance(notifications_payload, Mapping):  # noqa: E111
    entry["notifications"] = ensure_notification_options(
      cast(NotificationOptionsInput, dict(notifications_payload)),
      defaults=DEFAULT_NOTIFICATION_OPTIONS,
    )

  gps_payload = value.get(CONF_GPS_SETTINGS)  # noqa: E111
  if isinstance(gps_payload, Mapping):  # noqa: E111
    entry["gps_settings"] = cast(GPSOptions, dict(gps_payload))

  geofence_payload = value.get("geofence_settings")  # noqa: E111
  if isinstance(geofence_payload, Mapping):  # noqa: E111
    entry["geofence_settings"] = cast(
      GeofenceOptions,
      dict(geofence_payload),
    )

  feeding_payload = value.get("feeding_settings")  # noqa: E111
  if isinstance(feeding_payload, Mapping):  # noqa: E111
    entry["feeding_settings"] = cast(FeedingOptions, dict(feeding_payload))

  health_payload = value.get("health_settings")  # noqa: E111
  if isinstance(health_payload, Mapping):  # noqa: E111
    entry["health_settings"] = cast(HealthOptions, dict(health_payload))

  return entry  # noqa: E111


class DetectionStatistics(TypedDict):
  """Aggregated statistics for door sensor walk detection diagnostics.

  This structure mirrors the runtime statistics tracked by the
  ``DoorSensorManager`` and is used for diagnostic payloads that surface
  detection performance information through Home Assistant's diagnostics and
  logging facilities.

  Attributes:
      total_detections: Total number of detection events processed.
      successful_walks: Number of detections that resulted in confirmed walks.
      false_positives: Count of detections that were dismissed as false alarms.
      false_negatives: Number of missed walks detected through manual review.
      average_confidence: Rolling average confidence score for detections.
  """  # noqa: E111

  total_detections: int  # noqa: E111
  successful_walks: int  # noqa: E111
  false_positives: int  # noqa: E111
  false_negatives: int  # noqa: E111
  average_confidence: float  # noqa: E111


class DetectionStatusEntry(TypedDict):
  """Status information for an individual dog's detection state."""  # noqa: E111

  dog_name: str  # noqa: E111
  door_sensor: str  # noqa: E111
  current_state: str  # noqa: E111
  confidence_score: float  # noqa: E111
  active_walk_id: str | None  # noqa: E111
  last_door_state: str | None  # noqa: E111
  recent_activity: int  # noqa: E111


class DetectionStatus(TypedDict):
  """Structured detection status payload for diagnostics endpoints."""  # noqa: E111

  configured_dogs: int  # noqa: E111
  active_detections: int  # noqa: E111
  detection_states: dict[str, DetectionStatusEntry]  # noqa: E111
  statistics: DetectionStatistics  # noqa: E111


class DoorSensorStateHistoryEntry(TypedDict):
  """Serialised state transition captured by the door sensor manager."""  # noqa: E111

  timestamp: str | None  # noqa: E111
  state: str  # noqa: E111


class DoorSensorStateSnapshot(TypedDict, total=False):
  """Detailed walk detection state exported in cache diagnostics."""  # noqa: E111

  current_state: str  # noqa: E111
  door_opened_at: str | None  # noqa: E111
  door_closed_at: str | None  # noqa: E111
  potential_walk_start: str | None  # noqa: E111
  active_walk_id: str | None  # noqa: E111
  confidence_score: float  # noqa: E111
  last_door_state: str | None  # noqa: E111
  consecutive_opens: int  # noqa: E111
  state_history: list[DoorSensorStateHistoryEntry]  # noqa: E111
  last_activity_age_seconds: int  # noqa: E111


class DoorSensorDogSnapshot(TypedDict, total=False):
  """Per-dog configuration snapshot for diagnostics exports."""  # noqa: E111

  entity_id: str  # noqa: E111
  enabled: bool  # noqa: E111
  walk_detection_timeout: int  # noqa: E111
  minimum_walk_duration: int  # noqa: E111
  maximum_walk_duration: int  # noqa: E111
  door_closed_delay: int  # noqa: E111
  require_confirmation: bool  # noqa: E111
  auto_end_walks: bool  # noqa: E111
  confidence_threshold: float  # noqa: E111
  state: DoorSensorStateSnapshot  # noqa: E111


type DoorSensorConfigUpdateValue = DoorSensorSettingsPayload | str | None
"""Union of values persisted alongside door sensor configuration updates."""

type DoorSensorConfigUpdate = dict[str, DoorSensorConfigUpdateValue]
"""Mutable payload pushed to the data manager during door sensor updates."""


class DoorSensorManagerStats(DetectionStatistics, total=False):
  """Aggregated statistics surfaced alongside detection telemetry."""  # noqa: E111

  configured_sensors: int  # noqa: E111
  active_detections: int  # noqa: E111
  last_activity_age_seconds: int  # noqa: E111


class DoorSensorManagerSnapshot(TypedDict):
  """Coordinator snapshot payload returned by the door sensor cache monitor."""  # noqa: E111

  per_dog: dict[str, DoorSensorDogSnapshot]  # noqa: E111
  detection_stats: DetectionStatistics  # noqa: E111
  manager_last_activity: str | None  # noqa: E111


class StorageNamespaceDogSummary(TypedDict, total=False):
  """Aggregated state persisted for a single storage namespace entry."""  # noqa: E111

  entries: int  # noqa: E111
  payload_type: str  # noqa: E111
  timestamp: str | None  # noqa: E111
  timestamp_age_seconds: int  # noqa: E111
  timestamp_issue: str  # noqa: E111


class StorageNamespaceStats(TypedDict):
  """Summary metrics for coordinator storage namespace diagnostics."""  # noqa: E111

  namespace: str  # noqa: E111
  dogs: int  # noqa: E111
  entries: int  # noqa: E111


class StorageNamespaceSnapshot(TypedDict):
  """Structured snapshot returned by storage namespace monitors."""  # noqa: E111

  namespace: str  # noqa: E111
  per_dog: dict[str, StorageNamespaceDogSummary]  # noqa: E111


class DataManagerMetricsSnapshot(TypedDict):
  """Metrics exposed by :class:`PawControlDataManager`."""  # noqa: E111

  dogs: int  # noqa: E111
  storage_path: str  # noqa: E111
  cache_diagnostics: CacheDiagnosticsMap  # noqa: E111


class EntityBudgetSnapshotEntry(TypedDict, total=False):
  """Serialised budget snapshot exported for coordinator diagnostics."""  # noqa: E111

  dog_id: str  # noqa: E111
  profile: str  # noqa: E111
  capacity: int | float  # noqa: E111
  base_allocation: int | float  # noqa: E111
  dynamic_allocation: int | float  # noqa: E111
  requested_entities: tuple[str, ...]  # noqa: E111
  denied_requests: tuple[str, ...]  # noqa: E111
  recorded_at: str | None  # noqa: E111


class EntityBudgetStats(TypedDict):
  """Summary metrics for entity budget tracker diagnostics."""  # noqa: E111

  tracked_dogs: int  # noqa: E111
  saturation_percent: float  # noqa: E111


class EntityBudgetDiagnostics(TypedDict):
  """Structured diagnostics payload for entity budget telemetry."""  # noqa: E111

  summary: JSONMutableMapping  # noqa: E111
  snapshots: list[EntityBudgetSnapshotEntry]  # noqa: E111


class RuntimeErrorHistoryEntry(TypedDict, total=False):
  """Structured runtime error metadata stored for diagnostics."""  # noqa: E111

  timestamp: Required[str]  # noqa: E111
  source: Required[str]  # noqa: E111
  dog_id: NotRequired[str]  # noqa: E111
  door_sensor: NotRequired[str | None]  # noqa: E111
  error: NotRequired[str]  # noqa: E111
  context: NotRequired[ErrorContext | None]  # noqa: E111


type RuntimeErrorHistory = list[RuntimeErrorHistoryEntry]


class DoorSensorPersistenceFailure(TypedDict, total=False):
  """Telemetry entry captured when door sensor persistence fails."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  recorded_at: Required[str]  # noqa: E111
  dog_name: NotRequired[str | None]  # noqa: E111
  door_sensor: NotRequired[str | None]  # noqa: E111
  settings: NotRequired[DoorSensorSettingsPayload | None]  # noqa: E111
  error: NotRequired[str]  # noqa: E111


class DoorSensorFailureSummary(TypedDict, total=False):
  """Aggregated telemetry for door sensor persistence failures per dog."""  # noqa: E111

  dog_id: Required[str]  # noqa: E111
  failure_count: Required[int]  # noqa: E111
  last_failure: Required[DoorSensorPersistenceFailure]  # noqa: E111
  dog_name: NotRequired[str | None]  # noqa: E111


class PerformanceTrackerBucket(TypedDict, total=False):
  """Execution metrics recorded by :func:`performance_tracker`."""  # noqa: E111

  runs: int  # noqa: E111
  failures: int  # noqa: E111
  durations_ms: list[float]  # noqa: E111
  average_ms: float  # noqa: E111
  last_run: str | None  # noqa: E111
  last_error: str | None  # noqa: E111


class RuntimePerformanceStats(TypedDict, total=False):
  """Mutable runtime telemetry stored on :class:`PawControlRuntimeData`."""  # noqa: E111

  bool_coercion_summary: BoolCoercionSummary  # noqa: E111
  reconfigure_summary: ReconfigureTelemetrySummary  # noqa: E111
  resilience_summary: CoordinatorResilienceSummary  # noqa: E111
  resilience_diagnostics: CoordinatorResilienceDiagnostics  # noqa: E111
  door_sensor_failures: list[DoorSensorPersistenceFailure]  # noqa: E111
  door_sensor_failure_count: int  # noqa: E111
  last_door_sensor_failure: DoorSensorPersistenceFailure  # noqa: E111
  door_sensor_failure_summary: dict[str, DoorSensorFailureSummary]  # noqa: E111
  runtime_store_health: RuntimeStoreHealthHistory  # noqa: E111
  service_guard_metrics: ServiceGuardMetricsSnapshot  # noqa: E111
  entity_factory_guard_metrics: EntityFactoryGuardMetrics  # noqa: E111
  rejection_metrics: CoordinatorRejectionMetrics  # noqa: E111
  service_results: list[ServiceExecutionResult]  # noqa: E111
  last_service_result: ServiceExecutionResult  # noqa: E111
  service_call_telemetry: ServiceCallTelemetry  # noqa: E111
  maintenance_results: list[MaintenanceExecutionResult]  # noqa: E111
  last_maintenance_result: MaintenanceExecutionResult  # noqa: E111
  last_cache_diagnostics: CacheDiagnosticsCapture  # noqa: E111
  daily_resets: int  # noqa: E111
  performance_buckets: dict[str, PerformanceTrackerBucket]  # noqa: E111


def empty_runtime_performance_stats() -> RuntimePerformanceStats:
  """Return an empty runtime performance stats mapping for dataclass defaults."""  # noqa: E111

  return cast(RuntimePerformanceStats, {})  # noqa: E111


DOMAIN_RUNTIME_STORE_VERSION: Final[int] = 2
"""Current schema version for domain runtime store entries."""

DOMAIN_RUNTIME_STORE_MINIMUM_COMPATIBLE_VERSION: Final[int] = 1
"""Lowest supported schema version for domain runtime store entries."""


@dataclass
class PawControlRuntimeData:
  """Comprehensive runtime data container for the PawControl integration.

  This dataclass contains all runtime components needed by the integration
  for Platinum-targeted type safety with ConfigEntry[PawControlRuntimeData].
  Enhanced with performance monitoring, error tracking, and comprehensive
  component lifecycle management.

  This structure is the central coordination point for all integration
  components and provides type-safe access to all runtime services.

  Attributes:
      coordinator: Data coordination and update management service
      data_manager: Persistent data storage and retrieval service
      notification_manager: Notification delivery and management service
      feeding_manager: Feeding schedule and nutrition tracking service
      walk_manager: Walk tracking and exercise monitoring service
      entity_factory: Entity creation and lifecycle management service
      entity_profile: Active entity profile configuration
      dogs: List of all configured dogs with their settings
      performance_stats: Runtime performance monitoring data
      error_history: Historical error tracking for diagnostics
      helper_manager: Home Assistant helper creation and management service
      geofencing_manager: Geofencing and GPS zone monitoring service
      garden_manager: Garden care automation service
      daily_reset_unsub: Callback used to cancel the scheduled daily reset
      background_monitor_task: Background health monitoring task handle

  Note:
      This class implements both dataclass and dictionary-like access
      patterns for maximum flexibility in integration usage scenarios.
  """  # noqa: E111

  coordinator: PawControlCoordinator  # noqa: E111
  data_manager: PawControlDataManager  # noqa: E111
  notification_manager: PawControlNotificationManager  # noqa: E111
  feeding_manager: FeedingManager  # noqa: E111
  walk_manager: WalkManager  # noqa: E111
  entity_factory: EntityFactory  # noqa: E111
  entity_profile: str  # noqa: E111
  dogs: list[DogConfigData]  # noqa: E111
  config_entry_data: ConfigEntryDataPayload | None = None  # noqa: E111
  config_entry_options: ConfigEntryOptionsPayload | None = None  # noqa: E111
  background_monitor_task: Task[None] | None = None  # noqa: E111
  garden_manager: GardenManager | None = None  # noqa: E111
  geofencing_manager: PawControlGeofencing | None = None  # noqa: E111
  helper_manager: PawControlHelperManager | None = None  # noqa: E111
  script_manager: PawControlScriptManager | None = None  # noqa: E111
  gps_geofence_manager: GPSGeofenceManager | None = None  # noqa: E111
  door_sensor_manager: DoorSensorManager | None = None  # noqa: E111
  device_api_client: PawControlDeviceClient | None = None  # noqa: E111

  # Enhanced runtime tracking for Platinum-targeted monitoring  # noqa: E114
  performance_stats: RuntimePerformanceStats = field(  # noqa: E111
    default_factory=empty_runtime_performance_stats,
  )
  error_history: RuntimeErrorHistory = field(default_factory=list)  # noqa: E111
  manual_event_history: deque[ManualResilienceEventRecord] = field(  # noqa: E111
    default_factory=lambda: deque(maxlen=5),
  )
  # PLATINUM: Optional unsubscribe callbacks for scheduler and reload listener  # noqa: E114, E501
  daily_reset_unsub: Any = field(default=None)  # noqa: E111
  reload_unsub: Callable[[], Any] | None = None  # noqa: E111
  schema_created_version: int = DOMAIN_RUNTIME_STORE_VERSION  # noqa: E111
  schema_version: int = DOMAIN_RUNTIME_STORE_VERSION  # noqa: E111
  _runtime_managers_cache: CoordinatorRuntimeManagers | None = field(  # noqa: E111
    default=None,
    init=False,
    repr=False,
  )

  @property  # noqa: E111
  def runtime_managers(self) -> CoordinatorRuntimeManagers:  # noqa: E111
    """Return the runtime manager container associated with this entry."""

    cached = self._runtime_managers_cache
    if cached is not None:
      return cached  # noqa: E111

    coordinator_managers = getattr(
      self.coordinator,
      "runtime_managers",
      None,
    )
    if isinstance(coordinator_managers, CoordinatorRuntimeManagers):
      self._runtime_managers_cache = coordinator_managers  # noqa: E111
      return coordinator_managers  # noqa: E111

    container = CoordinatorRuntimeManagers(
      data_manager=getattr(self, "data_manager", None),
      feeding_manager=getattr(self, "feeding_manager", None),
      walk_manager=getattr(self, "walk_manager", None),
      notification_manager=getattr(self, "notification_manager", None),
      gps_geofence_manager=getattr(self, "gps_geofence_manager", None),
      geofencing_manager=getattr(self, "geofencing_manager", None),
      weather_health_manager=getattr(
        self,
        "weather_health_manager",
        None,
      ),
      garden_manager=getattr(self, "garden_manager", None),
    )
    self._runtime_managers_cache = container
    return container

  def as_dict(self) -> PawControlRuntimeDataExport:  # noqa: E111
    """Return a dictionary representation of the runtime data.

    Provides dictionary access to all runtime components for scenarios
    where dictionary-style access is more convenient than direct
    attribute access.

    Returns:
        Dictionary mapping component names to runtime instances
    """
    return {
      "coordinator": self.coordinator,
      "data_manager": self.data_manager,
      "notification_manager": self.notification_manager,
      "feeding_manager": self.feeding_manager,
      "walk_manager": self.walk_manager,
      "runtime_managers": self.runtime_managers,
      "entity_factory": self.entity_factory,
      "entity_profile": self.entity_profile,
      "dogs": self.dogs,
      "config_entry_data": self.config_entry_data,
      "config_entry_options": self.config_entry_options,
      "garden_manager": self.garden_manager,
      "geofencing_manager": self.geofencing_manager,
      "script_manager": self.script_manager,
      "gps_geofence_manager": self.gps_geofence_manager,
      "door_sensor_manager": self.door_sensor_manager,
      "helper_manager": self.helper_manager,
      "device_api_client": self.device_api_client,
      "performance_stats": self.performance_stats,
      "error_history": self.error_history,
      "manual_event_history": list(self.manual_event_history),
      "background_monitor_task": self.background_monitor_task,
      "daily_reset_unsub": self.daily_reset_unsub,
      "schema_created_version": self.schema_created_version,
      "schema_version": self.schema_version,
    }

  def __getitem__(self, key: str) -> Any:  # noqa: E111
    """Allow dictionary-style access for backward compatibility.

    Provides backward compatibility for code that expects dictionary-style
    access to runtime data while maintaining type safety.

    Args:
        key: Attribute name to retrieve

    Returns:
        The requested attribute value

    Raises:
        KeyError: If the requested key does not exist
    """
    if hasattr(self, key):
      return getattr(self, key)  # noqa: E111
    raise KeyError(key) from None

  def get(self, key: str, default: Any | None = None) -> Any | None:  # noqa: E111
    """Return an attribute using dictionary-style access with default.

    Provides safe dictionary-style access with default value support
    for robust runtime data access patterns.

    Args:
        key: Attribute name to retrieve
        default: Default value if attribute does not exist

    Returns:
        The requested attribute value or default
    """
    return getattr(self, key, default)


class LegacyDomainRuntimeStoreEntry(TypedDict, total=False):
  """Serialized representation of legacy runtime store entries."""  # noqa: E111

  runtime_data: PawControlRuntimeData  # noqa: E111
  version: int  # noqa: E111
  created_version: int  # noqa: E111


@dataclass(slots=True)
class DomainRuntimeStoreEntry:
  """Container persisting runtime data within ``hass.data`` namespaces."""  # noqa: E111

  runtime_data: PawControlRuntimeData  # noqa: E111
  version: int = DOMAIN_RUNTIME_STORE_VERSION  # noqa: E111
  created_version: int = DOMAIN_RUNTIME_STORE_VERSION  # noqa: E111

  CURRENT_VERSION: ClassVar[int] = DOMAIN_RUNTIME_STORE_VERSION  # noqa: E111
  MINIMUM_COMPATIBLE_VERSION: ClassVar[int] = (  # noqa: E111
    DOMAIN_RUNTIME_STORE_MINIMUM_COMPATIBLE_VERSION
  )

  def unwrap(self) -> PawControlRuntimeData:  # noqa: E111
    """Return the stored runtime payload."""

    return self.runtime_data

  def ensure_current(self) -> DomainRuntimeStoreEntry:  # noqa: E111
    """Return an entry stamped with the current schema version."""

    if self.version == self.CURRENT_VERSION:
      return self  # noqa: E111
    return DomainRuntimeStoreEntry(
      runtime_data=self.runtime_data,
      version=self.CURRENT_VERSION,
      created_version=self.created_version,
    )

  def is_future_version(self) -> bool:  # noqa: E111
    """Return ``True`` when the entry was produced by a newer schema."""

    return (
      self.version > self.CURRENT_VERSION or self.created_version > self.CURRENT_VERSION
    )

  def is_legacy_version(self) -> bool:  # noqa: E111
    """Return ``True`` when the entry predates the compatibility window."""

    return self.created_version < self.MINIMUM_COMPATIBLE_VERSION


type DomainRuntimeStore = MutableMapping[str, DomainRuntimeStoreEntry]


RuntimeStoreEntryStatus = Literal[
  "missing",
  "unstamped",
  "current",
  "upgrade_pending",
  "legacy_upgrade_required",
  "future_incompatible",
]
"""Status values describing compatibility of runtime store entries."""


RuntimeStoreOverallStatus = Literal[
  "missing",
  "current",
  "detached_entry",
  "detached_store",
  "diverged",
  "needs_migration",
  "future_incompatible",
]
"""High-level compatibility summary for runtime store state."""


class RuntimeStoreEntrySnapshot(TypedDict, total=False):
  """Snapshot describing a single runtime store representation."""  # noqa: E111

  available: bool  # noqa: E111
  version: int | None  # noqa: E111
  created_version: int | None  # noqa: E111
  status: RuntimeStoreEntryStatus  # noqa: E111


class RuntimeStoreCompatibilitySnapshot(TypedDict):
  """Composite compatibility summary for runtime store metadata."""  # noqa: E111

  entry_id: str  # noqa: E111
  status: RuntimeStoreOverallStatus  # noqa: E111
  current_version: int  # noqa: E111
  minimum_compatible_version: int  # noqa: E111
  entry: RuntimeStoreEntrySnapshot  # noqa: E111
  store: RuntimeStoreEntrySnapshot  # noqa: E111
  divergence_detected: bool  # noqa: E111


RuntimeStoreHealthLevel = Literal["ok", "watch", "action_required"]
"""Risk level derived from runtime store compatibility checks."""


class RuntimeStoreAssessmentEvent(TypedDict, total=False):
  """Timeline entry capturing individual runtime store assessments."""  # noqa: E111

  timestamp: str  # noqa: E111
  level: RuntimeStoreHealthLevel  # noqa: E111
  previous_level: RuntimeStoreHealthLevel | None  # noqa: E111
  status: RuntimeStoreOverallStatus  # noqa: E111
  entry_status: RuntimeStoreEntryStatus | None  # noqa: E111
  store_status: RuntimeStoreEntryStatus | None  # noqa: E111
  reason: str  # noqa: E111
  recommended_action: str | None  # noqa: E111
  divergence_detected: bool  # noqa: E111
  divergence_rate: float | None  # noqa: E111
  checks: int  # noqa: E111
  divergence_events: int  # noqa: E111
  level_streak: int  # noqa: E111
  escalations: int  # noqa: E111
  deescalations: int  # noqa: E111
  level_changed: bool  # noqa: E111
  current_level_duration_seconds: float | None  # noqa: E111


class RuntimeStoreAssessmentTimelineSegment(TypedDict, total=False):
  """Contiguous period derived from runtime store assessment events."""  # noqa: E111

  start: str  # noqa: E111
  end: str | None  # noqa: E111
  level: RuntimeStoreHealthLevel  # noqa: E111
  status: RuntimeStoreOverallStatus | None  # noqa: E111
  entry_status: RuntimeStoreEntryStatus | None  # noqa: E111
  store_status: RuntimeStoreEntryStatus | None  # noqa: E111
  reason: str | None  # noqa: E111
  recommended_action: str | None  # noqa: E111
  divergence_detected: bool | None  # noqa: E111
  divergence_rate: float | None  # noqa: E111
  checks: int | None  # noqa: E111
  divergence_events: int | None  # noqa: E111
  duration_seconds: float | None  # noqa: E111


class RuntimeStoreLevelDurationPercentiles(TypedDict, total=False):
  """Percentile distribution for runtime store level durations."""  # noqa: E111

  p75: float  # noqa: E111
  p90: float  # noqa: E111
  p95: float  # noqa: E111


class RuntimeStoreLevelDurationAlert(TypedDict, total=False):
  """Alert produced when duration percentiles exceed guard limits."""  # noqa: E111

  level: RuntimeStoreHealthLevel  # noqa: E111
  percentile_label: str  # noqa: E111
  percentile_rank: float  # noqa: E111
  percentile_seconds: float  # noqa: E111
  guard_limit_seconds: float  # noqa: E111
  severity: str  # noqa: E111
  recommended_action: str | None  # noqa: E111


class RuntimeStoreAssessmentTimelineSummary(TypedDict, total=False):
  """Derived statistics for the runtime store assessment timeline."""  # noqa: E111

  total_events: int  # noqa: E111
  level_changes: int  # noqa: E111
  level_change_rate: float | None  # noqa: E111
  level_counts: dict[RuntimeStoreHealthLevel, int]  # noqa: E111
  status_counts: dict[RuntimeStoreOverallStatus, int]  # noqa: E111
  reason_counts: dict[str, int]  # noqa: E111
  distinct_reasons: int  # noqa: E111
  first_event_timestamp: str | None  # noqa: E111
  last_event_timestamp: str | None  # noqa: E111
  last_level: RuntimeStoreHealthLevel | None  # noqa: E111
  last_status: RuntimeStoreOverallStatus | None  # noqa: E111
  last_reason: str | None  # noqa: E111
  last_recommended_action: str | None  # noqa: E111
  last_divergence_detected: bool | None  # noqa: E111
  last_divergence_rate: float | None  # noqa: E111
  last_level_duration_seconds: float | None  # noqa: E111
  timeline_window_seconds: float | None  # noqa: E111
  timeline_window_days: float | None  # noqa: E111
  events_per_day: float | None  # noqa: E111
  most_common_reason: str | None  # noqa: E111
  most_common_level: RuntimeStoreHealthLevel | None  # noqa: E111
  most_common_status: RuntimeStoreOverallStatus | None  # noqa: E111
  average_divergence_rate: float | None  # noqa: E111
  max_divergence_rate: float | None  # noqa: E111
  level_duration_peaks: dict[RuntimeStoreHealthLevel, float]  # noqa: E111
  level_duration_latest: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_totals: dict[RuntimeStoreHealthLevel, float]  # noqa: E111
  level_duration_samples: dict[RuntimeStoreHealthLevel, int]  # noqa: E111
  level_duration_averages: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_minimums: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_medians: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_standard_deviations: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_percentiles: dict[  # noqa: E111
    RuntimeStoreHealthLevel,
    RuntimeStoreLevelDurationPercentiles,
  ]
  level_duration_alert_thresholds: dict[RuntimeStoreHealthLevel, float | None]  # noqa: E111
  level_duration_guard_alerts: list[RuntimeStoreLevelDurationAlert]  # noqa: E111


class RuntimeStoreHealthHistory(TypedDict, total=False):
  """Rolling history of runtime store compatibility checks."""  # noqa: E111

  schema_version: int  # noqa: E111
  checks: int  # noqa: E111
  status_counts: dict[RuntimeStoreOverallStatus, int]  # noqa: E111
  divergence_events: int  # noqa: E111
  last_checked: str | None  # noqa: E111
  last_status: RuntimeStoreOverallStatus | None  # noqa: E111
  last_entry_status: RuntimeStoreEntryStatus | None  # noqa: E111
  last_store_status: RuntimeStoreEntryStatus | None  # noqa: E111
  last_entry_version: int | None  # noqa: E111
  last_store_version: int | None  # noqa: E111
  last_entry_created_version: int | None  # noqa: E111
  last_store_created_version: int | None  # noqa: E111
  divergence_detected: bool  # noqa: E111
  assessment_last_level: RuntimeStoreHealthLevel | None  # noqa: E111
  assessment_last_level_change: str | None  # noqa: E111
  assessment_level_streak: int  # noqa: E111
  assessment_escalations: int  # noqa: E111
  assessment_deescalations: int  # noqa: E111
  assessment_level_durations: dict[RuntimeStoreHealthLevel, float]  # noqa: E111
  assessment_current_level_duration_seconds: float | None  # noqa: E111
  assessment_events: list[RuntimeStoreAssessmentEvent]  # noqa: E111
  assessment: RuntimeStoreHealthAssessment  # noqa: E111
  assessment_timeline_segments: list[RuntimeStoreAssessmentTimelineSegment]  # noqa: E111
  assessment_timeline_summary: RuntimeStoreAssessmentTimelineSummary  # noqa: E111


class RuntimeStoreHealthAssessment(TypedDict, total=False):
  """Risk assessment based on runtime store history and current snapshot."""  # noqa: E111

  level: RuntimeStoreHealthLevel  # noqa: E111
  previous_level: RuntimeStoreHealthLevel | None  # noqa: E111
  reason: str  # noqa: E111
  recommended_action: str | None  # noqa: E111
  divergence_rate: float | None  # noqa: E111
  checks: int  # noqa: E111
  divergence_events: int  # noqa: E111
  last_status: RuntimeStoreOverallStatus | None  # noqa: E111
  last_entry_status: RuntimeStoreEntryStatus | None  # noqa: E111
  last_store_status: RuntimeStoreEntryStatus | None  # noqa: E111
  last_checked: str | None  # noqa: E111
  divergence_detected: bool  # noqa: E111
  level_streak: int  # noqa: E111
  last_level_change: str | None  # noqa: E111
  escalations: int  # noqa: E111
  deescalations: int  # noqa: E111
  level_durations: dict[RuntimeStoreHealthLevel, float]  # noqa: E111
  current_level_duration_seconds: float | None  # noqa: E111
  events: list[RuntimeStoreAssessmentEvent]  # noqa: E111
  timeline_summary: RuntimeStoreAssessmentTimelineSummary  # noqa: E111
  timeline_segments: list[RuntimeStoreAssessmentTimelineSegment]  # noqa: E111


class CoordinatorRuntimeStoreSummary(TypedDict, total=False):
  """Runtime store snapshot surfaced through coordinator diagnostics."""  # noqa: E111

  snapshot: RuntimeStoreCompatibilitySnapshot  # noqa: E111
  history: RuntimeStoreHealthHistory  # noqa: E111
  assessment: RuntimeStoreHealthAssessment  # noqa: E111


# PLATINUM: Custom ConfigEntry type for PawControl integrations
type PawControlConfigEntry = ConfigEntry[PawControlRuntimeData]
"""Type alias for PawControl-specific config entries.

By parameterising ``ConfigEntry`` with :class:`PawControlRuntimeData` we provide
Home Assistant with the precise runtime payload type exposed by this
integration.  This keeps call sites expressive, improves type-checker feedback,
and remains compatible with forward-looking changes to Home Assistant's
``ConfigEntry`` generics.
"""


class DailyStatsPayload(TypedDict, total=False):
  """Serialized representation of :class:`DailyStats` records."""  # noqa: E111

  date: str  # noqa: E111
  feedings_count: int  # noqa: E111
  walks_count: int  # noqa: E111
  health_logs_count: int  # noqa: E111
  gps_updates_count: int  # noqa: E111
  total_food_amount: float  # noqa: E111
  total_walk_distance: float  # noqa: E111
  total_walk_time: int  # noqa: E111
  total_calories_burned: float  # noqa: E111
  last_feeding: str | None  # noqa: E111
  last_walk: str | None  # noqa: E111
  last_health_event: str | None  # noqa: E111


class PawControlRuntimeDataExport(TypedDict):
  """Dictionary-style runtime data export returned by ``as_dict``."""  # noqa: E111

  coordinator: PawControlCoordinator  # noqa: E111
  data_manager: PawControlDataManager  # noqa: E111
  notification_manager: PawControlNotificationManager  # noqa: E111
  feeding_manager: FeedingManager  # noqa: E111
  walk_manager: WalkManager  # noqa: E111
  runtime_managers: CoordinatorRuntimeManagers  # noqa: E111
  entity_factory: EntityFactory  # noqa: E111
  entity_profile: str  # noqa: E111
  dogs: list[DogConfigData]  # noqa: E111
  config_entry_data: ConfigEntryDataPayload | None  # noqa: E111
  config_entry_options: ConfigEntryOptionsPayload | None  # noqa: E111
  garden_manager: GardenManager | None  # noqa: E111
  geofencing_manager: PawControlGeofencing | None  # noqa: E111
  script_manager: PawControlScriptManager | None  # noqa: E111
  gps_geofence_manager: GPSGeofenceManager | None  # noqa: E111
  door_sensor_manager: DoorSensorManager | None  # noqa: E111
  helper_manager: PawControlHelperManager | None  # noqa: E111
  device_api_client: PawControlDeviceClient | None  # noqa: E111
  performance_stats: RuntimePerformanceStats  # noqa: E111
  error_history: RuntimeErrorHistory  # noqa: E111
  manual_event_history: list[ManualResilienceEventRecord]  # noqa: E111
  background_monitor_task: Task[None] | None  # noqa: E111
  daily_reset_unsub: Any  # noqa: E111
  schema_created_version: int  # noqa: E111
  schema_version: int  # noqa: E111


@dataclass
class DailyStats:
  """Aggregated per-day statistics for a dog.

  The data manager stores a ``DailyStats`` instance for each dog so that
  frequently accessed aggregate metrics such as the total number of feedings
  or walks can be retrieved without scanning the full history on every
  update.  The class mirrors the behaviour of the Home Assistant integration
  by providing helpers for serialization and incremental updates.
  """  # noqa: E111

  date: datetime  # noqa: E111
  feedings_count: int = 0  # noqa: E111
  walks_count: int = 0  # noqa: E111
  health_logs_count: int = 0  # noqa: E111
  gps_updates_count: int = 0  # noqa: E111
  total_food_amount: float = 0.0  # noqa: E111
  total_walk_distance: float = 0.0  # noqa: E111
  total_walk_time: int = 0  # noqa: E111
  total_calories_burned: float = 0.0  # noqa: E111
  last_feeding: datetime | None = None  # noqa: E111
  last_walk: datetime | None = None  # noqa: E111
  last_health_event: datetime | None = None  # noqa: E111

  @staticmethod  # noqa: E111
  def _parse_datetime(value: Any) -> datetime | None:  # noqa: E111
    """Convert ISO formatted values into timezone aware ``datetime`` objects."""

    if value is None:
      return None  # noqa: E111
    if isinstance(value, datetime):
      return dt_util.as_utc(value)  # noqa: E111
    if isinstance(value, str):
      parsed = dt_util.parse_datetime(value)  # noqa: E111
      if parsed is not None:  # noqa: E111
        return dt_util.as_utc(parsed)
    return None

  @classmethod  # noqa: E111
  def from_dict(cls, payload: JSONDateMapping) -> DailyStats:  # noqa: E111
    """Deserialize daily statistics from a dictionary structure."""

    raw_date = payload.get("date")
    date_value = cls._parse_datetime(raw_date) or dt_util.utcnow()

    def _coerce_int(value: JSONDateValue | None, *, default: int = 0) -> int:
      if isinstance(value, bool):  # noqa: E111
        return int(value)
      if isinstance(value, int):  # noqa: E111
        return value
      if isinstance(value, float):  # noqa: E111
        return int(value)
      if isinstance(value, str):  # noqa: E111
        stripped = value.strip()
        if not stripped:
          return default  # noqa: E111
        try:
          return int(float(stripped))  # noqa: E111
        except ValueError:
          return default  # noqa: E111
      return default  # noqa: E111

    def _coerce_float(
      value: JSONDateValue | None,
      *,
      default: float = 0.0,
    ) -> float:
      if isinstance(value, bool):  # noqa: E111
        return float(value)
      if isinstance(value, int | float):  # noqa: E111
        return float(value)
      if isinstance(value, str):  # noqa: E111
        stripped = value.strip()
        if not stripped:
          return default  # noqa: E111
        try:
          return float(stripped)  # noqa: E111
        except ValueError:
          return default  # noqa: E111
      return default  # noqa: E111

    return cls(
      date=date_value,
      feedings_count=_coerce_int(payload.get("feedings_count")),
      walks_count=_coerce_int(payload.get("walks_count")),
      health_logs_count=_coerce_int(payload.get("health_logs_count")),
      gps_updates_count=_coerce_int(payload.get("gps_updates_count")),
      total_food_amount=_coerce_float(payload.get("total_food_amount")),
      total_walk_distance=_coerce_float(
        payload.get("total_walk_distance"),
      ),
      total_walk_time=_coerce_int(payload.get("total_walk_time")),
      total_calories_burned=_coerce_float(
        payload.get("total_calories_burned"),
      ),
      last_feeding=cls._parse_datetime(payload.get("last_feeding")),
      last_walk=cls._parse_datetime(payload.get("last_walk")),
      last_health_event=cls._parse_datetime(
        payload.get("last_health_event"),
      ),
    )

  def as_dict(self) -> DailyStatsPayload:  # noqa: E111
    """Serialize the statistics for storage."""

    return {
      "date": dt_util.as_utc(self.date).isoformat(),
      "feedings_count": self.feedings_count,
      "walks_count": self.walks_count,
      "health_logs_count": self.health_logs_count,
      "gps_updates_count": self.gps_updates_count,
      "total_food_amount": self.total_food_amount,
      "total_walk_distance": self.total_walk_distance,
      "total_walk_time": self.total_walk_time,
      "total_calories_burned": self.total_calories_burned,
      "last_feeding": self.last_feeding.isoformat() if self.last_feeding else None,
      "last_walk": self.last_walk.isoformat() if self.last_walk else None,
      "last_health_event": self.last_health_event.isoformat()
      if self.last_health_event
      else None,
    }

  def reset(self, *, preserve_date: bool = True) -> None:  # noqa: E111
    """Reset all counters, optionally keeping the current date."""

    if not preserve_date:
      self.date = dt_util.utcnow()  # noqa: E111
    self.feedings_count = 0
    self.walks_count = 0
    self.health_logs_count = 0
    self.gps_updates_count = 0
    self.total_food_amount = 0.0
    self.total_walk_distance = 0.0
    self.total_walk_time = 0
    self.total_calories_burned = 0.0
    self.last_feeding = None
    self.last_walk = None
    self.last_health_event = None

  def register_feeding(self, portion_size: float, timestamp: datetime | None) -> None:  # noqa: E111
    """Record a feeding event in the aggregate counters."""

    self.feedings_count += 1
    if portion_size > 0:
      self.total_food_amount += portion_size  # noqa: E111
    parsed = self._parse_datetime(timestamp)
    if parsed is not None:
      self.last_feeding = parsed  # noqa: E111

  def register_walk(  # noqa: E111
    self,
    duration: int | None,
    distance: float | None,
    timestamp: datetime | None,
  ) -> None:
    """Record a walk event in the aggregate counters."""

    self.walks_count += 1
    if duration:
      self.total_walk_time += int(duration)  # noqa: E111
    if distance:
      self.total_walk_distance += float(distance)  # noqa: E111
    parsed = self._parse_datetime(timestamp)
    if parsed is not None:
      self.last_walk = parsed  # noqa: E111

  def register_health_event(self, timestamp: datetime | None) -> None:  # noqa: E111
    """Record a health log entry in the aggregate counters."""

    self.health_logs_count += 1
    parsed = self._parse_datetime(timestamp)
    if parsed is not None:
      self.last_health_event = parsed  # noqa: E111

  def register_gps_update(self) -> None:  # noqa: E111
    """Increase the GPS update counter for the day."""

    self.gps_updates_count += 1


@dataclass
class FeedingData:
  """Data structure for individual feeding records with comprehensive validation.

  Represents a single feeding event with complete nutritional and contextual
  information. Includes automatic validation to ensure data integrity and
  consistency across the system.

  Attributes:
      meal_type: Type of meal from VALID_MEAL_TYPES
      portion_size: Amount of food in grams
      food_type: Type of food from VALID_FOOD_TYPES
      timestamp: When the feeding occurred
      notes: Optional notes about the feeding
      logged_by: Person who logged the feeding
      calories: Caloric content if known (optional)
      automatic: Whether feeding was logged automatically by a device

  Raises:
      ValueError: If any validation constraints are violated
  """  # noqa: E111

  meal_type: str  # noqa: E111
  portion_size: float  # noqa: E111
  food_type: str  # noqa: E111
  timestamp: datetime  # noqa: E111
  notes: str = ""  # noqa: E111
  logged_by: str = ""  # noqa: E111
  calories: float | None = None  # noqa: E111
  automatic: bool = False  # noqa: E111

  def __post_init__(self) -> None:  # noqa: E111
    """Validate feeding data after initialization.

    Performs comprehensive validation including meal type validation,
    food type validation, and numerical constraint checking to ensure
    data integrity throughout the system.

    Raises:
        ValueError: If any validation constraint is violated
    """
    if self.meal_type not in VALID_MEAL_TYPES:
      raise ValueError(f"Invalid meal type: {self.meal_type}")  # noqa: E111
    if self.food_type not in VALID_FOOD_TYPES:
      raise ValueError(f"Invalid food type: {self.food_type}")  # noqa: E111
    if self.portion_size < 0:
      raise ValueError("Portion size cannot be negative")  # noqa: E111
    if self.calories is not None and self.calories < 0:
      raise ValueError("Calories cannot be negative")  # noqa: E111


@dataclass
class WalkData:
  """Data structure for walk tracking with comprehensive route and environmental data.

  Represents a complete walk session including timing, route information,
  environmental conditions, and subjective assessment. Supports both
  active walk tracking and historical walk analysis.

  Attributes:
      start_time: Walk start timestamp
      end_time: Walk end timestamp (None for active walks)
      duration: Walk duration in seconds (calculated or manual)
      distance: Walk distance in meters (GPS or manual)
      route: List of GPS coordinates defining the walk path
      label: User-assigned label for the walk
      location: General location description
      notes: Additional notes about the walk
      rating: Walk quality rating (0-10 scale)
      started_by: Person who started the walk
      ended_by: Person who ended the walk
      weather: Weather conditions during the walk
      temperature: Temperature in Celsius during the walk

  Raises:
      ValueError: If validation constraints are violated
  """  # noqa: E111

  start_time: datetime  # noqa: E111
  end_time: datetime | None = None  # noqa: E111
  duration: int | None = None  # seconds  # noqa: E111
  distance: float | None = None  # meters  # noqa: E111
  route: list[WalkRoutePoint] = field(default_factory=list)  # noqa: E111
  label: str = ""  # noqa: E111
  location: str = ""  # noqa: E111
  notes: str = ""  # noqa: E111
  rating: int = 0  # noqa: E111
  started_by: str = ""  # noqa: E111
  ended_by: str = ""  # noqa: E111
  weather: str = ""  # noqa: E111
  temperature: float | None = None  # noqa: E111

  def __post_init__(self) -> None:  # noqa: E111
    """Validate walk data after initialization.

    Ensures logical consistency in walk data including time relationships,
    rating constraints, and numerical validity.

    Raises:
        ValueError: If validation constraints are violated
    """
    if self.rating < 0 or self.rating > 10:
      raise ValueError("Rating must be between 0 and 10")  # noqa: E111
    if self.duration is not None and self.duration < 0:
      raise ValueError("Duration cannot be negative")  # noqa: E111
    if self.distance is not None and self.distance < 0:
      raise ValueError("Distance cannot be negative")  # noqa: E111
    if self.end_time and self.end_time < self.start_time:
      raise ValueError("End time cannot be before start time")  # noqa: E111


@dataclass(slots=True)
class HealthEvent:
  """Structured health event for efficient storage and retrieval.

  Optimized data structure using __slots__ for memory efficiency in health
  event storage. Designed for high-frequency health data collection with
  minimal memory footprint and fast serialization.

  Attributes:
      dog_id: Identifier of the dog this event relates to
      timestamp: ISO format timestamp string for efficient storage
      metrics: Dictionary of health metrics and measurements

  Note:
      Uses __slots__ for memory optimization when storing large numbers
      of health events in historical data.
  """  # noqa: E111

  dog_id: str  # noqa: E111
  timestamp: str | None = None  # noqa: E111
  metrics: JSONMutableMapping = field(default_factory=dict)  # noqa: E111

  @classmethod  # noqa: E111
  def from_raw(  # noqa: E111
    cls,
    dog_id: str,
    payload: JSONDateMapping,
    timestamp: str | None = None,
  ) -> HealthEvent:
    """Create a health event from raw payload data.

    Factory method for creating HealthEvent instances from various data
    sources including API responses, user input, and stored data.

    Args:
        dog_id: Identifier of the dog
        payload: Raw event data with metrics and optional timestamp
        timestamp: Override timestamp if not in payload

    Returns:
        Initialized HealthEvent instance with validated data
    """
    event_data = cast(
      JSONMutableMapping,
      {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in payload.items()
      },
    )
    event_data.pop("timestamp", None)
    raw_timestamp = payload.get("timestamp")
    event_timestamp = (
      raw_timestamp
      if isinstance(
        raw_timestamp,
        str,
      )
      else None
    )
    if isinstance(raw_timestamp, datetime):
      event_timestamp = raw_timestamp.isoformat()  # noqa: E111
    if event_timestamp is None:
      event_timestamp = timestamp  # noqa: E111

    return cls(dog_id=dog_id, timestamp=event_timestamp, metrics=event_data)

  @classmethod  # noqa: E111
  def from_storage(cls, dog_id: str, payload: JSONDateMapping) -> HealthEvent:  # noqa: E111
    """Create a health event from stored data.

    Factory method specifically for deserializing health events from
    persistent storage with proper data structure restoration.

    Args:
        dog_id: Identifier of the dog
        payload: Stored event data

    Returns:
        Restored HealthEvent instance
    """
    return cls.from_raw(dog_id, payload)

  def as_dict(self) -> JSONMutableMapping:  # noqa: E111
    """Return a storage-friendly representation of the health event.

    Serializes the health event into a dictionary format suitable for
    persistent storage while preserving all event data and metadata.

    Returns:
        Dictionary representation suitable for storage
    """
    payload = cast(JSONMutableMapping, dict(self.metrics))
    if self.timestamp is not None:
      payload["timestamp"] = self.timestamp  # noqa: E111
    return payload


@dataclass(slots=True)
class WalkEvent:
  """Structured walk event for efficient walk session tracking.

  Memory-optimized structure using __slots__ for tracking walk events
  and session state changes. Supports both real-time walk tracking
  and historical walk analysis with efficient storage characteristics.

  Attributes:
      dog_id: Identifier of the dog this walk event relates to
      action: Action type (start, pause, resume, end, etc.)
      session_id: Unique identifier for the walk session
      timestamp: ISO format timestamp for efficient storage
      details: Dictionary of event-specific details and metadata

  Note:
      Uses __slots__ for memory optimization when tracking numerous
      walk events and session state changes.
  """  # noqa: E111

  dog_id: str  # noqa: E111
  action: str | None = None  # noqa: E111
  session_id: str | None = None  # noqa: E111
  timestamp: str | None = None  # noqa: E111
  details: JSONMutableMapping = field(default_factory=dict)  # noqa: E111

  @classmethod  # noqa: E111
  def from_raw(  # noqa: E111
    cls,
    dog_id: str,
    payload: JSONDateMapping,
    timestamp: str | None = None,
  ) -> WalkEvent:
    """Create a walk event from raw payload data.

    Factory method for creating WalkEvent instances from various sources
    including real-time walk tracking, user actions, and API data.

    Args:
        dog_id: Identifier of the dog
        payload: Raw event data with action and details
        timestamp: Override timestamp if not in payload

    Returns:
        Initialized WalkEvent instance with validated structure
    """
    event_data = cast(
      JSONMutableMapping,
      {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in payload.items()
      },
    )
    raw_timestamp = event_data.pop("timestamp", None)
    timestamp_value = (
      raw_timestamp
      if isinstance(
        raw_timestamp,
        str,
      )
      else None
    )
    if isinstance(raw_timestamp, datetime):
      timestamp_value = raw_timestamp.isoformat()  # noqa: E111
    raw_action = event_data.pop("action", None)
    action = raw_action if isinstance(raw_action, str) else None
    raw_session = event_data.pop("session_id", None)
    session = raw_session if isinstance(raw_session, str) else None
    event_timestamp = timestamp_value if timestamp_value is not None else timestamp

    return cls(
      dog_id=dog_id,
      action=action,
      session_id=session,
      timestamp=event_timestamp,
      details=event_data,
    )

  @classmethod  # noqa: E111
  def from_storage(cls, dog_id: str, payload: JSONDateMapping) -> WalkEvent:  # noqa: E111
    """Create a walk event from stored data.

    Factory method for deserializing walk events from persistent storage
    with proper data structure and session state restoration.

    Args:
        dog_id: Identifier of the dog
        payload: Stored event data with complete session information

    Returns:
        Restored WalkEvent instance with session data
    """
    return cls.from_raw(dog_id, payload)

  def as_dict(self) -> JSONMutableMapping:  # noqa: E111
    """Return a storage-friendly representation of the walk event.

    Serializes the walk event into a dictionary format optimized for
    persistent storage while maintaining session tracking capabilities.

    Returns:
        Dictionary representation suitable for storage and transmission
    """
    payload = cast(JSONMutableMapping, dict(self.details))
    if self.action is not None:
      payload["action"] = self.action  # noqa: E111
    if self.session_id is not None:
      payload["session_id"] = self.session_id  # noqa: E111
    if self.timestamp is not None:
      payload["timestamp"] = self.timestamp  # noqa: E111
    return payload

  def merge(self, payload: JSONDateMapping, timestamp: str | None = None) -> None:  # noqa: E111
    """Merge incremental updates into the existing walk event.

    Allows for incremental updates to walk events during active sessions
    while preserving existing data and maintaining session continuity.

    Args:
        payload: New or updated event data
        timestamp: Optional timestamp for the update
    """
    updates = {
      key: value.isoformat() if isinstance(value, datetime) else value
      for key, value in payload.items()
    }
    if "action" in updates:
      raw_action = updates.pop("action")  # noqa: E111
      if isinstance(raw_action, str):  # noqa: E111
        self.action = raw_action
    if "session_id" in updates:
      raw_session = updates.pop("session_id")  # noqa: E111
      if isinstance(raw_session, str):  # noqa: E111
        self.session_id = raw_session
    if "timestamp" in updates:
      raw_timestamp = updates.pop("timestamp")  # noqa: E111
      if isinstance(raw_timestamp, str):  # noqa: E111
        self.timestamp = raw_timestamp
    elif timestamp and self.timestamp is None:
      self.timestamp = timestamp  # noqa: E111

    self.details.update(updates)


@dataclass
class HealthData:
  """Comprehensive health data structure with veterinary-grade validation.

  Represents a complete health assessment including physical measurements,
  behavioral observations, and medical context. Designed for integration
  with veterinary records and health trend analysis.

  Attributes:
      timestamp: When the health assessment was recorded
      weight: Dog weight in kilograms
      temperature: Body temperature in Celsius
      mood: Behavioral mood from VALID_MOOD_OPTIONS
      activity_level: Energy level from VALID_ACTIVITY_LEVELS
      health_status: Overall health from VALID_HEALTH_STATUS
      symptoms: Description of any observed symptoms
      medication: Current medication information
      note: Additional health notes or observations
      logged_by: Person who recorded the health data
      heart_rate: Heart rate in beats per minute (if measured)
      respiratory_rate: Breathing rate per minute (if measured)

  Raises:
      ValueError: If any health parameter is outside valid ranges
  """  # noqa: E111

  timestamp: datetime  # noqa: E111
  weight: float | None = None  # noqa: E111
  temperature: float | None = None  # noqa: E111
  mood: str = ""  # noqa: E111
  activity_level: str = ""  # noqa: E111
  health_status: str = ""  # noqa: E111
  symptoms: str = ""  # noqa: E111
  medication: JSONMutableMapping | None = None  # noqa: E111
  note: str = ""  # noqa: E111
  logged_by: str = ""  # noqa: E111
  heart_rate: int | None = None  # noqa: E111
  respiratory_rate: int | None = None  # noqa: E111

  def __post_init__(self) -> None:  # noqa: E111
    """Validate health data against veterinary standards.

    Performs comprehensive validation of all health parameters against
    veterinary standards and physiological constraints to ensure data
    quality for health analysis and trend tracking.

    Raises:
        ValueError: If any parameter is outside acceptable ranges
    """
    if self.mood and self.mood not in VALID_MOOD_OPTIONS:
      raise ValueError(f"Invalid mood: {self.mood}")  # noqa: E111
    if self.activity_level and self.activity_level not in VALID_ACTIVITY_LEVELS:
      raise ValueError(f"Invalid activity level: {self.activity_level}")  # noqa: E111
    if self.health_status and self.health_status not in VALID_HEALTH_STATUS:
      raise ValueError(f"Invalid health status: {self.health_status}")  # noqa: E111
    if self.weight is not None and (self.weight <= 0 or self.weight > 200):
      raise ValueError("Weight must be between 0 and 200 kg")  # noqa: E111
    if self.temperature is not None and (
      self.temperature < 35 or self.temperature > 45
    ):
      raise ValueError(  # noqa: E111
        "Temperature must be between 35 and 45 degrees Celsius",
      )
    if self.heart_rate is not None and (self.heart_rate < 50 or self.heart_rate > 250):
      raise ValueError("Heart rate must be between 50 and 250 bpm")  # noqa: E111


@dataclass
class GPSLocation:
  """Precision GPS location data with comprehensive metadata and validation.

  Represents a complete GPS location record including accuracy information,
  device status, and signal quality metrics. Designed for high-precision
  tracking applications with comprehensive validation.

  Attributes:
      latitude: Latitude coordinate in decimal degrees
      longitude: Longitude coordinate in decimal degrees
      accuracy: GPS accuracy estimate in meters
      altitude: Altitude above sea level in meters
      timestamp: When the location was recorded
      source: Source of the GPS data (device, service, etc.)
      battery_level: GPS device battery percentage (0-100)
      signal_strength: GPS signal strength percentage (0-100)

  Raises:
      ValueError: If coordinates or other parameters are invalid
  """  # noqa: E111

  latitude: float  # noqa: E111
  longitude: float  # noqa: E111
  accuracy: float | None = None  # noqa: E111
  altitude: float | None = None  # noqa: E111
  timestamp: datetime = field(default_factory=dt_util.utcnow)  # noqa: E111
  source: str = ""  # noqa: E111
  battery_level: int | None = None  # noqa: E111
  signal_strength: int | None = None  # noqa: E111

  def __post_init__(self) -> None:  # noqa: E111
    """Validate GPS coordinates and device parameters.

    Ensures GPS coordinates are within valid Earth coordinate ranges and
    device parameters are within acceptable bounds for reliable tracking.

    Raises:
        ValueError: If coordinates or parameters are invalid
    """
    if not (-90 <= self.latitude <= 90):
      raise ValueError(f"Invalid latitude: {self.latitude}")  # noqa: E111
    if not (-180 <= self.longitude <= 180):
      raise ValueError(f"Invalid longitude: {self.longitude}")  # noqa: E111
    if self.accuracy is not None and self.accuracy < 0:
      raise ValueError("Accuracy cannot be negative")  # noqa: E111
    if self.battery_level is not None and not (0 <= self.battery_level <= 100):
      raise ValueError("Battery level must be between 0 and 100")  # noqa: E111
    if self.signal_strength is not None and not (0 <= self.signal_strength <= 100):
      raise ValueError("Signal strength must be between 0 and 100")  # noqa: E111


# OPTIMIZE: Utility functions for common operations with comprehensive documentation


def create_entity_id(dog_id: str, entity_type: str, module: str) -> str:
  """Create standardized entity ID following Home Assistant conventions.

  Generates entity IDs that follow Home Assistant naming conventions and
  PawControl-specific patterns for consistent entity identification across
  the integration. The format ensures uniqueness and readability.

  Args:
      dog_id: Unique dog identifier (must be URL-safe)
      entity_type: Type of entity (sensor, button, switch, etc.)
      module: Module name that owns the entity (feeding, walk, health, etc.)

  Returns:
      Formatted entity ID in the pattern: pawcontrol_{dog_id}_{module}_{entity_type}

  Example:
      >>> create_entity_id("buddy", "sensor", "feeding")
      'pawcontrol_buddy_feeding_sensor'
  """  # noqa: E111
  return f"pawcontrol_{dog_id}_{module}_{entity_type}".lower()  # noqa: E111


def validate_dog_weight_for_size(weight: float, size: str) -> bool:
  """Validate if a dog's weight is appropriate for its size category.

  Performs veterinary-based validation to ensure weight measurements are
  reasonable for the specified dog size category. This helps identify
  data entry errors and potential health concerns.

  Args:
      weight: Dog weight in kilograms
      size: Dog size category from VALID_DOG_SIZES

  Returns:
      True if weight is within acceptable range for the size category,
      False if weight appears inappropriate for the size

  Example:
      >>> validate_dog_weight_for_size(25.0, "medium")
      True
      >>> validate_dog_weight_for_size(50.0, "toy")
      False

  Note:
      Size ranges are based on veterinary standards and allow for
      some overlap between categories to accommodate breed variations.
  """  # noqa: E111
  size_ranges = {  # noqa: E111
    "toy": (1.0, 6.0),  # Chihuahua, Yorkshire Terrier
    "small": (4.0, 15.0),  # Jack Russell, Beagle
    "medium": (8.0, 30.0),  # Border Collie, Bulldog
    "large": (22.0, 50.0),  # Labrador, German Shepherd
    "giant": (35.0, 90.0),  # Great Dane, Saint Bernard
  }

  if size not in size_ranges:  # noqa: E111
    return True  # Unknown size category, skip validation

  min_weight, max_weight = size_ranges[size]  # noqa: E111
  return min_weight <= weight <= max_weight  # noqa: E111


def calculate_daily_calories(weight: float, activity_level: str, age: int) -> int:
  """Calculate recommended daily caloric intake for a dog.

  Uses veterinary nutritional guidelines to calculate appropriate daily
  caloric intake based on the dog's weight, activity level, and age.
  The calculation considers metabolic changes with age and activity
  requirements for optimal health maintenance.

  Args:
      weight: Dog weight in kilograms
      activity_level: Activity level from VALID_ACTIVITY_LEVELS
      age: Dog age in years

  Returns:
      Recommended daily calories as an integer

  Example:
      >>> calculate_daily_calories(20.0, "normal", 5)
      892

  Note:
      Calculation uses the formula: 70 * (weight in kg)^0.75 * activity_multiplier
      with age-based adjustments for puppies and senior dogs. Always consult
      with a veterinarian for specific dietary recommendations.
  """  # noqa: E111
  import math  # noqa: E111

  # Base metabolic rate: 70 * (weight in kg)^0.75  # noqa: E114
  base_calories = 70 * math.pow(weight, 0.75)  # noqa: E111

  # Activity level multipliers based on veterinary guidelines  # noqa: E114
  activity_multipliers = {  # noqa: E111
    "very_low": 1.2,  # Sedentary, minimal exercise
    "low": 1.4,  # Light exercise, short walks
    "normal": 1.6,  # Moderate exercise, regular walks
    "high": 1.8,  # Active exercise, long walks/runs
    "very_high": 2.0,  # Very active, working dogs, intense exercise
  }

  multiplier = activity_multipliers.get(activity_level, 1.6)  # noqa: E111

  # Age-based adjustments for metabolic differences  # noqa: E114
  if age < 1:  # noqa: E111
    # Puppies have higher metabolic needs for growth
    multiplier *= 2.0
  elif age > 7:  # noqa: E111
    # Senior dogs typically have lower metabolic needs
    multiplier *= 0.9

  return int(base_calories * multiplier)  # noqa: E111


# OPTIMIZE: Enhanced type guards for runtime validation with O(1) performance


def is_dog_config_valid(config: Any) -> bool:
  """Comprehensive type guard to validate dog configuration data.

  Performs thorough validation of dog configuration including required
  fields, data types, and value constraints. Uses frozenset lookups
  for O(1) validation performance on enumerated values.

  Args:
      config: Configuration data to validate (any type accepted)

  Returns:
      True if configuration is valid and complete, False otherwise

  Example:
      >>> config = {"dog_id": "buddy", "dog_name": "Buddy", "dog_age": 5}
      >>> is_dog_config_valid(config)
      True

  Note:
      This function is used throughout the integration to ensure data
      integrity and should be called whenever dog configuration data
      is received from external sources or user input.
  """  # noqa: E111
  if not isinstance(config, Mapping):  # noqa: E111
    return False
  try:  # noqa: E111
    from .exceptions import FlowValidationError
    from .flow_validation import validate_dog_config_payload

    validate_dog_config_payload(
      ensure_json_mapping(cast(Mapping[str, object], config)),
      existing_ids=None,
      existing_names=None,
    )
  except FlowValidationError:  # noqa: E111
    return False
  return True  # noqa: E111


def is_gps_location_valid(location: Any) -> bool:
  """Validate GPS location data for accuracy and completeness.

  Performs comprehensive validation of GPS location data including
  coordinate ranges, accuracy values, and device status parameters
  to ensure location data integrity and usability.

  Args:
      location: Location data to validate (any type accepted)

  Returns:
      True if location data is valid and usable, False otherwise

  Example:
      >>> location = {"latitude": 52.5, "longitude": 13.4, "accuracy": 5.0}
      >>> is_gps_location_valid(location)
      True

  Note:
      Validation includes Earth coordinate bounds, non-negative accuracy
      values, and reasonable battery/signal strength ranges for
      GPS tracking devices.
  """  # noqa: E111
  if not isinstance(location, dict):  # noqa: E111
    return False

  # Validate required coordinates with Earth bounds checking  # noqa: E114
  for coord, limits in [("latitude", (-90, 90)), ("longitude", (-180, 180))]:  # noqa: E111
    if coord not in location:
      return False  # noqa: E111
    value = location[coord]
    if not is_number(value):
      return False  # noqa: E111
    numeric_value = float(value)
    if not (limits[0] <= numeric_value <= limits[1]):
      return False  # noqa: E111

  # Validate optional fields with appropriate constraints  # noqa: E114
  if "accuracy" in location and (  # noqa: E111
    not is_number(location["accuracy"]) or float(location["accuracy"]) < 0
  ):
    return False

  if "battery_level" in location:  # noqa: E111
    battery = location["battery_level"]
    if battery is not None and (
      not isinstance(battery, int) or not (0 <= battery <= 100)
    ):
      return False  # noqa: E111

  return True  # noqa: E111


def is_feeding_data_valid(data: Any) -> bool:
  """Validate feeding data for nutritional tracking accuracy.

  Performs comprehensive validation of feeding record data including
  meal type validation, portion size constraints, and optional
  nutritional information to ensure feeding data integrity.

  Args:
      data: Feeding data to validate (any type accepted)

  Returns:
      True if feeding data is valid and complete, False otherwise

  Example:
      >>> feeding = {"meal_type": "breakfast", "portion_size": 200.0}
      >>> is_feeding_data_valid(feeding)
      True

  Note:
      Uses frozenset lookup for O(1) meal type validation performance.
      Validates portion sizes as non-negative and calorie information
      if provided.
  """  # noqa: E111
  if not isinstance(data, dict):  # noqa: E111
    return False

  # Validate required fields with frozenset lookup for performance  # noqa: E114
  if "meal_type" not in data or data["meal_type"] not in VALID_MEAL_TYPES:  # noqa: E111
    return False

  if "portion_size" not in data:  # noqa: E111
    return False

  portion = data["portion_size"]  # noqa: E111
  if not is_number(portion) or float(portion) < 0:  # noqa: E111
    return False

  # Validate optional fields with appropriate constraints  # noqa: E114
  if "food_type" in data and data["food_type"] not in VALID_FOOD_TYPES:  # noqa: E111
    return False

  if "calories" in data:  # noqa: E111
    calories = data["calories"]
    if calories is not None and (not is_number(calories) or float(calories) < 0):
      return False  # noqa: E111

  return True  # noqa: E111


def is_health_data_valid(data: Any) -> bool:
  """Validate health data against veterinary standards and constraints.

  Performs comprehensive validation of health assessment data including
  mood states, activity levels, health status, and physiological
  measurements to ensure medical data accuracy and reliability.

  Args:
      data: Health data to validate (any type accepted)

  Returns:
      True if health data is valid and within acceptable ranges, False otherwise

  Example:
      >>> health = {"weight": 25.0, "mood": "happy", "temperature": 38.5}
      >>> is_health_data_valid(health)
      True

  Note:
      Validation includes veterinary-standard ranges for temperature,
      weight, and other physiological measurements to ensure data
      accuracy for health trend analysis.
  """  # noqa: E111
  if not isinstance(data, dict):  # noqa: E111
    return False

  # Validate optional fields with frozenset lookups for performance  # noqa: E114
  if "mood" in data and data["mood"] and data["mood"] not in VALID_MOOD_OPTIONS:  # noqa: E111
    return False

  if (  # noqa: E111
    "activity_level" in data
    and data["activity_level"]
    and data["activity_level"] not in VALID_ACTIVITY_LEVELS
  ):
    return False

  if (  # noqa: E111
    "health_status" in data
    and data["health_status"]
    and data["health_status"] not in VALID_HEALTH_STATUS
  ):
    return False

  # Validate physiological measurements with veterinary standards  # noqa: E114
  if "weight" in data:  # noqa: E111
    weight = data["weight"]
    if weight is not None and (
      not is_number(weight) or float(weight) <= 0 or float(weight) > 200
    ):
      return False  # noqa: E111

  if "temperature" in data:  # noqa: E111
    temp = data["temperature"]
    if temp is not None and (
      not is_number(temp) or float(temp) < 35 or float(temp) > 45
    ):
      return False  # noqa: E111

  return True  # noqa: E111


def is_notification_data_valid(data: Any) -> bool:
  """Validate notification data for reliable delivery and display.

  Performs comprehensive validation of notification data including
  required content fields, priority levels, delivery channels, and
  formatting requirements to ensure successful notification delivery.

  Args:
      data: Notification data to validate (any type accepted)

  Returns:
      True if notification data is valid and deliverable, False otherwise

  Example:
      >>> notification = {"title": "Walk Time", "message": "Buddy needs a walk!"}
      >>> is_notification_data_valid(notification)
      True

  Note:
      Uses frozenset lookups for O(1) priority and channel validation.
      Ensures title and message content is present and non-empty for
      successful notification display across all channels.
  """  # noqa: E111
  if not isinstance(data, dict):  # noqa: E111
    return False

  # Validate required content fields  # noqa: E114
  required_fields = ["title", "message"]  # noqa: E111
  for required_field in required_fields:  # noqa: E111
    if (
      required_field not in data
      or not isinstance(data[required_field], str)
      or not data[required_field].strip()
    ):
      return False  # noqa: E111

  # Validate optional fields with frozenset lookups for performance  # noqa: E114
  if "priority" in data and data["priority"] not in VALID_NOTIFICATION_PRIORITIES:  # noqa: E111
    return False

  return not ("channel" in data and data["channel"] not in VALID_NOTIFICATION_CHANNELS)  # noqa: E111


# geminivorschlag:
class DogModule(TypedDict):
  id: str  # noqa: E111
  name: str  # noqa: E111
  enabled: bool  # noqa: E111


class DogConfig(TypedDict):
  dog_id: str  # noqa: E111
  dog_name: str  # noqa: E111
  modules: DogModulesConfig  # noqa: E111
  # Add other fields as needed  # noqa: E114


# Immutable constant for Reauth placeholders
REAUTH_PLACEHOLDERS: Final = MappingProxyType(
  {
    "integration_name": "PawControl",
    "dogs_count": "0",
    "current_profile": "standard",
    "health_status": "Unknown",
  },
)
