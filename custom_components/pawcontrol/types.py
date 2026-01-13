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
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import logging
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
    cast,
)

from .compat import ConfigEntry
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
    from .service_guard import (
        ServiceGuardMetricsSnapshot,
        ServiceGuardResultHistory,
        ServiceGuardSummary,
    )

try:
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(UTC)

    dt_util = _DateTimeModule()

type JSONPrimitive = None | bool | int | float | str
"""Primitive JSON-compatible values."""

type JSONValue = JSONPrimitive | Sequence['JSONValue'] | Mapping[str, 'JSONValue']
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

type JSONMutableSequence = list[JSONValue]
"""Mutable sequence containing JSON-compatible payload entries."""

type JSONDateValue = JSONValue | datetime
"""JSON-compatible value extended with ``datetime`` for legacy payloads."""

type JSONDateMapping = Mapping[str, JSONDateValue]
"""Mapping that tolerates ``datetime`` values during legacy hydration."""

type VisitorModeSettingsPayload = JSONMutableMapping
"""Mutable payload persisted for visitor-mode configuration."""

from .utils import is_number  # noqa: E402

type ErrorContext = JSONMutableMapping
"""Structured context payload attached to :class:`PawControlError` instances."""


def ensure_json_mapping(
    data: Mapping[str, object] | JSONMutableMapping | None,
) -> JSONMutableMapping:
    """Return a JSON-compatible mutable mapping cloned from ``data``."""

    if not data:
        return {}

    return {str(key): cast(JSONValue, value) for key, value in data.items()}


def _coerce_iso_timestamp(value: Any) -> str | None:
    """Return an ISO-formatted timestamp string when possible."""

    if isinstance(value, datetime):
        return dt_util.as_utc(value).isoformat()
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def _coerce_float_value(value: Any) -> float | None:
    """Return a float when ``value`` is numeric."""

    if isinstance(value, bool):
        return None
    if isinstance(value, float | int):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


class ErrorPayload(TypedDict):
    """Serialized representation of :class:`PawControlError` instances."""

    error_code: str
    message: str
    user_message: str
    severity: str
    category: str
    context: ErrorContext
    recovery_suggestions: list[str]
    technical_details: str | None
    timestamp: str
    exception_type: str


type GPXAttributeValue = JSONPrimitive
"""Primitive attribute value allowed in GPX attribute mappings."""

type GPXAttributeMap = Mapping[str, GPXAttributeValue]
"""Mapping for GPX/XML attribute rendering."""

type EntityAttributePayload[T: JSONValue] = dict[str, T]
"""Generic JSON-compatible attribute payload keyed by entity attribute name."""

type EntityAttributeMutableMapping = EntityAttributePayload[JSONValue]
"""Mutable attribute payload used when exporting Home Assistant entity state."""

type NumberExtraAttributes = EntityAttributeMutableMapping
"""Extra state attributes exposed by PawControl number entities."""

type SelectExtraAttributes = EntityAttributeMutableMapping
"""Extra state attributes exposed by PawControl select entities."""

type PersonEntityAttributePayload = JSONMutableMapping
"""Mutable attribute payload stored alongside discovered person entities."""


class TextEntityExtraAttributes(TypedDict, total=False):
    """Extra attributes exposed by PawControl text entities."""

    dog_id: str
    dog_name: str
    text_type: str
    character_count: int
    last_updated: str | None
    last_updated_context_id: str | None
    last_updated_parent_id: str | None
    last_updated_user_id: str | None


class DogTextSnapshot(TypedDict, total=False):
    """Stored text values associated with a PawControl dog configuration."""

    notes: NotRequired[str]
    custom_label: NotRequired[str]
    walk_notes: NotRequired[str]
    current_walk_label: NotRequired[str]
    health_notes: NotRequired[str]
    medication_notes: NotRequired[str]
    vet_notes: NotRequired[str]
    grooming_notes: NotRequired[str]
    custom_message: NotRequired[str]
    emergency_contact: NotRequired[str]
    microchip: NotRequired[str]
    breeder_info: NotRequired[str]
    registration: NotRequired[str]
    insurance_info: NotRequired[str]
    allergies: NotRequired[str]
    training_notes: NotRequired[str]
    behavior_notes: NotRequired[str]
    location_description: NotRequired[str]


class DogTextMetadataEntry(TypedDict, total=False):
    """Metadata captured for an individual PawControl text value."""

    last_updated: str
    context_id: str | None
    parent_id: str | None
    user_id: str | None


class DogTextMetadataSnapshot(TypedDict, total=False):
    """Stored metadata associated with PawControl dog text values."""

    notes: NotRequired[DogTextMetadataEntry]
    custom_label: NotRequired[DogTextMetadataEntry]
    walk_notes: NotRequired[DogTextMetadataEntry]
    current_walk_label: NotRequired[DogTextMetadataEntry]
    health_notes: NotRequired[DogTextMetadataEntry]
    medication_notes: NotRequired[DogTextMetadataEntry]
    vet_notes: NotRequired[DogTextMetadataEntry]
    grooming_notes: NotRequired[DogTextMetadataEntry]
    custom_message: NotRequired[DogTextMetadataEntry]
    emergency_contact: NotRequired[DogTextMetadataEntry]
    microchip: NotRequired[DogTextMetadataEntry]
    breeder_info: NotRequired[DogTextMetadataEntry]
    registration: NotRequired[DogTextMetadataEntry]
    insurance_info: NotRequired[DogTextMetadataEntry]
    allergies: NotRequired[DogTextMetadataEntry]
    training_notes: NotRequired[DogTextMetadataEntry]
    behavior_notes: NotRequired[DogTextMetadataEntry]
    location_description: NotRequired[DogTextMetadataEntry]


class ButtonExtraAttributes(TypedDict, total=False):
    """Extra state attributes exposed by PawControl button entities."""

    dog_id: Required[str]
    dog_name: Required[str]
    button_type: Required[str]
    last_pressed: str | None
    action_description: NotRequired[str]
    last_updated: NotRequired[str | None]


class BinarySensorAttributes(TypedDict, total=False):
    """Extra state attributes exposed by PawControl binary sensor entities."""

    dog_id: Required[str]
    dog_name: Required[str]
    sensor_type: Required[str]
    last_update: Required[str]
    last_updated: NotRequired[str | None]
    dog_breed: NotRequired[str | None]
    dog_age: NotRequired[int | float | None]
    dog_size: NotRequired[str | None]
    dog_weight: NotRequired[float | None]
    status: NotRequired[str]
    system_health: NotRequired[str]
    enabled_modules: NotRequired[list[str]]
    attention_reasons: NotRequired[list[str]]
    urgency_level: NotRequired[str]
    recommended_actions: NotRequired[list[str]]
    recommended_action: NotRequired[str]
    visitor_mode_started: NotRequired[str | None]
    visitor_name: NotRequired[str | None]
    modified_notifications: NotRequired[bool]
    reduced_alerts: NotRequired[bool]
    last_feeding: NotRequired[str | None]
    last_feeding_hours: NotRequired[int | float | None]
    next_feeding_due: NotRequired[str | None]
    hunger_level: NotRequired[str]
    walk_start_time: NotRequired[str | None]
    walk_duration: NotRequired[int | float | None]
    walk_distance: NotRequired[int | float | None]
    estimated_remaining: NotRequired[int | None]
    last_walk: NotRequired[str | None]
    last_walk_hours: NotRequired[int | float | None]
    walks_today: NotRequired[int]
    garden_status: NotRequired[str]
    sessions_today: NotRequired[int]
    pending_confirmations: NotRequired[list[GardenConfirmationSnapshot]]
    pending_confirmation_count: NotRequired[int]
    current_zone: NotRequired[str]
    distance_from_home: NotRequired[float | None]
    last_seen: NotRequired[str | None]
    accuracy: NotRequired[float | int | None]
    health_alerts: NotRequired[HealthAlertList]
    health_status: NotRequired[str | None]
    alert_count: NotRequired[int]
    current_activity_level: NotRequired[str]
    concern_reason: NotRequired[str]
    portion_adjustment_factor: NotRequired[float | None]
    health_conditions: NotRequired[list[str]]
    emergency_type: NotRequired[str | None]
    portion_adjustment: NotRequired[int | float | str | None]
    activated_at: NotRequired[str | None]
    expires_at: NotRequired[str | None]


class ActivityLevelSensorAttributes(TypedDict, total=False):
    """Extra attributes reported by the activity level sensor."""

    walks_today: int
    total_walk_minutes_today: float
    last_walk_hours_ago: float | None
    health_activity_level: str | None
    activity_source: str


class CaloriesBurnedSensorAttributes(TypedDict, total=False):
    """Extra attributes reported by the calories burned sensor."""

    dog_weight_kg: float
    walk_minutes_today: float
    walk_distance_meters_today: float
    activity_level: str
    calories_per_minute: float
    calories_per_100m: float


class LastFeedingHoursAttributes(TypedDict, total=False):
    """Extra attributes reported by the last feeding hours sensor."""

    last_feeding_time: str | float | int | None
    feedings_today: int
    is_overdue: bool
    next_feeding_due: str | None


class TotalWalkDistanceAttributes(TypedDict, total=False):
    """Extra attributes reported by the total walk distance sensor."""

    total_walks: int
    total_distance_meters: float
    average_distance_per_walk_km: float
    distance_this_week_km: float
    distance_this_month_km: float


class WalksThisWeekAttributes(TypedDict, total=False):
    """Extra attributes reported by the walks this week sensor."""

    walks_today: int
    total_duration_this_week_minutes: float
    total_distance_this_week_meters: float
    average_walks_per_day: float
    days_this_week: int
    distance_this_week_km: float


class DateExtraAttributes(TypedDict, total=False):
    """Extra state attributes exposed by PawControl date entities."""

    dog_id: Required[str]
    dog_name: Required[str]
    date_type: Required[str]
    days_from_today: NotRequired[int]
    is_past: NotRequired[bool]
    is_today: NotRequired[bool]
    is_future: NotRequired[bool]
    iso_string: NotRequired[str]
    age_days: NotRequired[int]
    age_years: NotRequired[float]
    age_months: NotRequired[float]


class TrackingModePreset(TypedDict, total=False):
    """Configuration preset applied when selecting a GPS tracking mode."""

    update_interval_seconds: int
    auto_start_walk: bool
    track_route: bool
    route_smoothing: bool


class LocationAccuracyConfig(TypedDict, total=False):
    """Configuration payload applied when selecting a GPS accuracy profile."""

    gps_accuracy_threshold: float
    min_distance_for_point: float
    route_smoothing: bool


class DogSizeInfo(TypedDict, total=False):
    """Additional metadata exposed by the dog size select entity."""

    weight_range: str
    exercise_needs: str
    food_portion: str


class PerformanceModeInfo(TypedDict, total=False):
    """Metadata describing a performance mode option."""

    description: str
    update_interval: str
    battery_impact: str


class FoodTypeInfo(TypedDict, total=False):
    """Metadata describing a feeding option exposed by selects."""

    calories_per_gram: float
    moisture_content: str
    storage: str
    shelf_life: str


class WalkModeInfo(TypedDict, total=False):
    """Descriptive metadata for walk mode select options."""

    description: str
    gps_required: bool
    accuracy: str


class GPSSourceInfo(TypedDict, total=False):
    """Metadata describing a configured GPS telemetry source."""

    accuracy: str
    update_frequency: str
    battery_usage: str


class GroomingTypeInfo(TypedDict, total=False):
    """Metadata describing a grooming routine selection."""

    frequency: str
    duration: str
    difficulty: str


type MetadataPayload[T: JSONValue] = dict[str, T]
"""Generic JSON-compatible mapping used for diagnostics metadata sections."""

type MaintenanceMetadataPayload = MetadataPayload[JSONValue]
"""JSON-compatible metadata payload captured during maintenance routines."""

type ServiceDetailsPayload = MaintenanceMetadataPayload
"""Normalised service details payload stored alongside execution results."""

type StorageNamespaceKey = Literal[
    'walks',
    'feedings',
    'health',
    'routes',
    'statistics',
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
    from .coordinator import PawControlCoordinator
    from .data_manager import PawControlDataManager
    from .device_api import PawControlDeviceClient
    from .door_sensor_manager import DoorSensorManager
    from .entity_factory import EntityFactory
    from .feeding_manager import FeedingComplianceResult, FeedingManager
    from .garden_manager import GardenManager
    from .geofencing import PawControlGeofencing
    from .gps_manager import GPSGeofenceManager
    from .helper_manager import PawControlHelperManager
    from .notifications import PawControlNotificationManager
    from .script_manager import PawControlScriptManager
    from .walk_manager import WalkManager
    from .weather_manager import WeatherHealthManager

# OPTIMIZE: Use literal constants for performance - frozensets provide O(1) lookups
# and are immutable, preventing accidental modification while ensuring fast validation

VALID_MEAL_TYPES: Final[frozenset[str]] = frozenset(
    ['breakfast', 'lunch', 'dinner', 'snack']
)
"""Valid meal types for feeding tracking.

This frozenset defines the acceptable meal types that can be recorded in the system.
Using frozenset provides O(1) lookup performance for validation while preventing
accidental modification of the valid values.
"""

VALID_FOOD_TYPES: Final[frozenset[str]] = frozenset(
    ['dry_food', 'wet_food', 'barf', 'home_cooked', 'mixed']
)
"""Valid food types for feeding management.

Defines the types of food that can be tracked in feeding records. This includes
commercial food types and home-prepared options for comprehensive diet tracking.
"""

VALID_DOG_SIZES: Final[frozenset[str]] = frozenset(
    ['toy', 'small', 'medium', 'large', 'giant']
)
"""Valid dog size categories for breed classification.

Size categories are used throughout the system for portion calculation, exercise
recommendations, and health monitoring. These align with standard veterinary
size classifications.
"""

VALID_HEALTH_STATUS: Final[frozenset[str]] = frozenset(
    ['excellent', 'very_good', 'good', 'normal', 'unwell', 'sick']
)
"""Valid health status levels for health monitoring.

These status levels provide a standardized way to track overall dog health,
from excellent condition to requiring medical attention.
"""

VALID_MOOD_OPTIONS: Final[frozenset[str]] = frozenset(
    ['happy', 'neutral', 'content', 'normal', 'sad', 'angry', 'anxious', 'tired']
)
"""Valid mood states for behavioral tracking.

Mood tracking helps identify patterns in behavior and potential health issues
that may affect a dog's emotional well-being.
"""

VALID_ACTIVITY_LEVELS: Final[frozenset[str]] = frozenset(
    ['very_low', 'low', 'normal', 'high', 'very_high']
)
"""Valid activity levels for exercise and health monitoring.

Activity levels are used for calculating appropriate exercise needs, portion sizes,
and overall health assessments based on a dog's typical energy expenditure.
"""

VALID_GEOFENCE_TYPES: Final[frozenset[str]] = frozenset(
    ['safe_zone', 'restricted_area', 'point_of_interest']
)
"""Valid geofence zone types for GPS tracking.

Different zone types trigger different behaviors in the system, from safety
notifications to activity logging when dogs enter or leave specific areas.
"""

VALID_GPS_SOURCES: Final[frozenset[str]] = frozenset(
    [
        'manual',
        'device_tracker',
        'person_entity',
        'smartphone',
        'tractive',
        'webhook',
        'mqtt',
    ]
)
"""Valid GPS data sources for location tracking.

Supports multiple GPS input methods to accommodate different hardware setups
and integration scenarios with various tracking devices and services.
"""

type NotificationPriority = Literal['low', 'normal', 'high', 'urgent']
"""Supported notification priority values.

The alias is reused across the helper and notification managers so every queue,
options flow, and service call enforces the Home Assistant priority contract
without falling back to loosely typed strings.
"""

VALID_NOTIFICATION_PRIORITIES: Final[frozenset[NotificationPriority]] = frozenset(
    ['low', 'normal', 'high', 'urgent']
)
"""Valid notification priority levels for alert management.

Priority levels determine notification delivery methods, timing, and persistence
to ensure important alerts are appropriately escalated.
"""

VALID_NOTIFICATION_CHANNELS: Final[frozenset[str]] = frozenset(
    [
        'mobile',
        'persistent',
        'email',
        'sms',
        'webhook',
        'tts',
        'media_player',
        'slack',
        'discord',
    ]
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
    """Normalised configuration values applied to door sensor tracking."""

    walk_detection_timeout: int = DEFAULT_WALK_DETECTION_TIMEOUT
    minimum_walk_duration: int = DEFAULT_MINIMUM_WALK_DURATION
    maximum_walk_duration: int = DEFAULT_MAXIMUM_WALK_DURATION
    door_closed_delay: int = DEFAULT_DOOR_CLOSED_DELAY
    require_confirmation: bool = True
    auto_end_walks: bool = True
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD


DEFAULT_DOOR_SENSOR_SETTINGS = DoorSensorSettingsConfig()

type DoorSensorOverrideScalar = bool | int | float | str | None
"""Scalar values accepted when overriding door sensor settings."""

type DoorSensorSettingsMapping = Mapping[str, DoorSensorOverrideScalar]
"""Mapping of setting names to override scalars."""


class DoorSensorSettingsOverrides(TypedDict, total=False):
    """User-provided overrides for :class:`DoorSensorSettingsConfig`."""

    timeout: DoorSensorOverrideScalar
    walk_detection_timeout: DoorSensorOverrideScalar
    walk_timeout: DoorSensorOverrideScalar
    minimum_walk_duration: DoorSensorOverrideScalar
    min_walk_duration: DoorSensorOverrideScalar
    minimum_duration: DoorSensorOverrideScalar
    min_duration: DoorSensorOverrideScalar
    maximum_walk_duration: DoorSensorOverrideScalar
    max_walk_duration: DoorSensorOverrideScalar
    maximum_duration: DoorSensorOverrideScalar
    max_duration: DoorSensorOverrideScalar
    door_closed_delay: DoorSensorOverrideScalar
    door_closed_timeout: DoorSensorOverrideScalar
    close_delay: DoorSensorOverrideScalar
    close_timeout: DoorSensorOverrideScalar
    require_confirmation: DoorSensorOverrideScalar
    confirmation_required: DoorSensorOverrideScalar
    auto_end_walks: DoorSensorOverrideScalar
    auto_end_walk: DoorSensorOverrideScalar
    auto_close: DoorSensorOverrideScalar
    confidence_threshold: DoorSensorOverrideScalar
    confidence: DoorSensorOverrideScalar
    threshold: DoorSensorOverrideScalar


class DoorSensorSettingsPayload(TypedDict):
    """Serialised payload representing normalised door sensor settings."""

    walk_detection_timeout: int
    minimum_walk_duration: int
    maximum_walk_duration: int
    door_closed_delay: int
    require_confirmation: bool
    auto_end_walks: bool
    confidence_threshold: float


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
    """Structured description of diet compatibility conflicts or warnings."""

    type: str
    diets: list[str]
    message: str


class DietValidationResult(TypedDict):
    """Result payload returned by diet validation helpers."""

    valid: bool
    conflicts: list[DietCompatibilityIssue]
    warnings: list[DietCompatibilityIssue]
    recommended_vet_consultation: bool
    total_diets: int


class FeedingGoalSettings(TypedDict, total=False):
    """Targeted feeding goals that influence portion adjustments."""

    weight_goal: Literal['maintain', 'lose', 'gain']
    weight_loss_rate: Literal['aggressive', 'moderate', 'gradual']


class HealthMetricsOverride(TypedDict, total=False):
    """Runtime override values when building :class:`HealthMetrics`."""

    weight: float | int
    ideal_weight: float | int
    age_months: int
    health_conditions: list[str]


class FeedingHistoryEvent(TypedDict, total=False):
    """Normalised feeding event used for history analysis."""

    time: datetime
    amount: float | int
    meal_type: str | None


FeedingHistoryStatus = Literal[
    'no_data',
    'insufficient_data',
    'no_recent_data',
    'no_health_data',
    'good',
    'overfeeding',
    'slight_overfeeding',
    'underfeeding',
    'slight_underfeeding',
]
"""Status values returned by ``analyze_feeding_history``."""


class FeedingHealthContext(TypedDict, total=False):
    """Contextual health information attached to feeding analysis."""

    weight_goal: str | None
    body_condition_score: float | int | None
    life_stage: str | None
    activity_level: str | None
    health_conditions: list[str] | None
    special_diet: list[str] | None


class FeedingHistoryAnalysis(TypedDict, total=False):
    """Structured payload returned by feeding history analysis."""

    status: FeedingHistoryStatus
    recommendation: str
    message: str
    avg_daily_calories: float
    target_calories: float
    calorie_variance_percent: float
    avg_daily_meals: float
    recommendations: list[str]
    analysis_period_days: int
    health_context: FeedingHealthContext


class HealthFeedingInsights(TypedDict, total=False):
    """Feeding-specific recommendations appended to health reports."""

    daily_calorie_target: float | None
    portion_adjustment_factor: float
    recommended_meals_per_day: int
    food_type_recommendation: str | None


HealthReportStatus = Literal[
    'excellent',
    'good',
    'needs_attention',
    'concerning',
    'managing_condition',
]
"""Overall status levels surfaced by comprehensive health reports."""


class HealthReport(TypedDict, total=False):
    """Comprehensive health report exported by the feeding manager."""

    timestamp: str
    overall_status: HealthReportStatus
    recommendations: list[str]
    health_score: int
    areas_of_concern: list[str]
    positive_indicators: list[str]
    feeding_insights: HealthFeedingInsights
    recent_feeding_performance: FeedingHistoryAnalysis


class DogVaccinationRecord(TypedDict, total=False):
    """Details about a specific vaccination."""

    date: str | None
    next_due: str | None


class DogMedicationEntry(TypedDict, total=False):
    """Medication reminder entry captured during configuration."""

    name: str
    dosage: str
    frequency: str
    time: str
    notes: str
    with_meals: bool


class DogHealthConfig(TypedDict, total=False):
    """Extended health configuration captured during setup."""

    vet_name: str
    vet_phone: str
    last_vet_visit: str | None
    next_checkup: str | None
    weight_tracking: bool
    ideal_weight: float | None
    body_condition_score: int
    activity_level: str
    weight_goal: str
    spayed_neutered: bool
    health_conditions: list[str]
    special_diet_requirements: list[str]
    vaccinations: dict[str, DogVaccinationRecord]
    medications: list[DogMedicationEntry]


class DogModulesConfig(TypedDict, total=False):
    """Per-dog module enablement settings."""

    feeding: bool
    walk: bool
    health: bool
    gps: bool
    garden: bool
    notifications: bool
    dashboard: bool
    visitor: bool
    grooming: bool
    medication: bool
    training: bool
    weather: bool


class HealthMedicationReminder(TypedDict, total=False):
    """Reminder entry describing an active medication schedule."""

    name: str
    dosage: str | None
    frequency: str | None
    next_dose: str | None
    notes: str | None
    with_meals: bool | None


class HealthAlertEntry(TypedDict, total=False):
    """Structured alert surfaced by the health enhancement routines."""

    type: str
    message: str
    severity: Literal['low', 'medium', 'high', 'critical']
    action_required: bool
    details: JSONLikeMapping | None


class HealthUpcomingCareEntry(TypedDict, total=False):
    """Scheduled or due-soon care entry tracked for a dog."""

    type: str
    message: str
    due_date: str | None
    priority: Literal['low', 'medium', 'high']
    details: str | JSONLikeMapping | None


type HealthAlertList = list[HealthAlertEntry]
type HealthUpcomingCareQueue = list[HealthUpcomingCareEntry]
type HealthMedicationQueue = list[HealthMedicationReminder]


class HealthStatusSnapshot(TypedDict, total=False):
    """Current health status summary exported to diagnostics consumers."""

    overall_score: int
    priority_alerts: HealthAlertList
    upcoming_care: HealthUpcomingCareQueue
    recommendations: list[str]
    last_updated: str


class HealthAppointmentRecommendation(TypedDict):
    """Recommendation for the next veterinary appointment."""

    next_appointment_date: str
    appointment_type: str
    reason: str
    urgency: Literal['low', 'normal', 'high']
    days_until: int


ModuleToggleKey = Literal[
    'feeding',
    'walk',
    'health',
    'gps',
    'garden',
    'notifications',
    'dashboard',
    'visitor',
    'grooming',
    'medication',
    'training',
]

ModuleToggleFlowFlag = Literal[
    'enable_feeding',
    'enable_walk',
    'enable_health',
    'enable_gps',
    'enable_garden',
    'enable_notifications',
    'enable_dashboard',
    'enable_visitor',
    'enable_grooming',
    'enable_medication',
    'enable_training',
]

type ModuleToggleMapping = Mapping[ModuleToggleKey, JSONValue]
"""Mapping of module toggle keys to JSON-compatible values."""

MODULE_TOGGLE_KEYS: Final[tuple[ModuleToggleKey, ...]] = (
    'feeding',
    'walk',
    'health',
    'gps',
    'garden',
    'notifications',
    'dashboard',
    'visitor',
    'grooming',
    'medication',
    'training',
)

MODULE_TOGGLE_FLOW_FLAGS: Final[
    tuple[tuple[ModuleToggleFlowFlag, ModuleToggleKey], ...]
] = (
    ('enable_feeding', 'feeding'),
    ('enable_walk', 'walk'),
    ('enable_health', 'health'),
    ('enable_gps', 'gps'),
    ('enable_garden', 'garden'),
    ('enable_notifications', 'notifications'),
    ('enable_dashboard', 'dashboard'),
    ('enable_visitor', 'visitor'),
    ('enable_grooming', 'grooming'),
    ('enable_medication', 'medication'),
    ('enable_training', 'training'),
)

MODULE_TOGGLE_FLAG_BY_KEY: Final[dict[ModuleToggleKey, ModuleToggleFlowFlag]] = {
    module: flag for flag, module in MODULE_TOGGLE_FLOW_FLAGS
}


class DogModuleSelectionInput(TypedDict, total=False):
    """Raw module toggle payload collected during per-dog setup."""

    enable_feeding: bool
    enable_walk: bool
    enable_health: bool
    enable_gps: bool
    enable_garden: bool
    enable_notifications: bool
    enable_dashboard: bool
    enable_visitor: bool
    enable_grooming: bool
    enable_medication: bool
    enable_training: bool


FeedingConfigKey = Literal[
    'meals_per_day',
    'daily_food_amount',
    'portion_size',
    'food_type',
    'feeding_schedule',
    'enable_reminders',
    'reminder_minutes_before',
    'breakfast_time',
    'lunch_time',
    'dinner_time',
    'snack_times',
]

DEFAULT_FEEDING_SCHEDULE: Final[tuple[str, ...]] = ('10:00:00', '15:00:00', '20:00:00')


@dataclass(slots=True)
class DogModulesProjection:
    """Expose both typed and plain module toggle representations."""

    config: DogModulesConfig
    mapping: dict[str, bool]

    def as_config(self) -> DogModulesConfig:
        """Return a ``DogModulesConfig`` copy suitable for storage."""

        return cast(DogModulesConfig, dict(self.config))

    def as_mapping(self) -> dict[str, bool]:
        """Return a plain mapping for platform factories."""

        return dict(self.mapping)


def _record_bool_coercion(
    value: Any, *, default: bool, result: bool, reason: str
) -> None:
    """Record bool coercion telemetry for diagnostics consumers."""

    try:
        from .telemetry import record_bool_coercion_event
    except Exception:  # pragma: no cover - telemetry import guarded for safety
        return

    try:
        record_bool_coercion_event(
            value=value, default=default, result=result, reason=reason
        )
    except Exception:  # pragma: no cover - telemetry failures must not break coercion
        return


class BoolCoercionSample(TypedDict):
    """Snapshot of an individual boolean coercion event."""

    value_type: str
    value_repr: str
    default: bool
    result: bool
    reason: str


class BoolCoercionMetrics(TypedDict, total=False):
    """Aggregated metrics describing bool coercion behaviour."""

    total: int
    defaulted: int
    fallback: int
    reset_count: int
    type_counts: dict[str, int]
    reason_counts: dict[str, int]
    samples: list[BoolCoercionSample]
    first_seen: str | None
    last_seen: str | None
    active_window_seconds: float | None
    last_reset: str | None
    last_reason: str | None
    last_value_type: str | None
    last_value_repr: str | None
    last_result: bool | None
    last_default: bool | None


class BoolCoercionSummary(TypedDict):
    """Condensed snapshot for coordinator observability exports."""

    recorded: bool
    total: int
    defaulted: int
    fallback: int
    reset_count: int
    first_seen: str | None
    last_seen: str | None
    last_reset: str | None
    active_window_seconds: float | None
    last_reason: str | None
    last_value_type: str | None
    last_value_repr: str | None
    last_result: bool | None
    last_default: bool | None
    reason_counts: dict[str, int]
    type_counts: dict[str, int]
    samples: list[BoolCoercionSample]


class BoolCoercionDiagnosticsPayload(TypedDict, total=False):
    """Diagnostics payload combining bool coercion summary and metrics."""

    recorded: bool
    summary: BoolCoercionSummary
    metrics: BoolCoercionMetrics


_TRUTHY_BOOL_STRINGS: Final[frozenset[str]] = frozenset(
    {'1', 'true', 'yes', 'y', 'on', 'enabled'}
)
_FALSY_BOOL_STRINGS: Final[frozenset[str]] = frozenset(
    {'0', 'false', 'no', 'n', 'off', 'disabled'}
)


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Return a boolean flag while tolerating common string/int representations."""

    if value is None:
        _record_bool_coercion(value, default=default, result=default, reason='none')
        return default
    if isinstance(value, bool):
        result = value
        _record_bool_coercion(
            value,
            default=default,
            result=result,
            reason='native_true' if result else 'native_false',
        )
        return result
    if isinstance(value, int | float):
        result = value != 0
        _record_bool_coercion(
            value,
            default=default,
            result=result,
            reason='numeric_nonzero' if result else 'numeric_zero',
        )
        return result
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            _record_bool_coercion(
                value, default=default, result=default, reason='blank_string'
            )
            return default
        if text in _TRUTHY_BOOL_STRINGS:
            _record_bool_coercion(
                value, default=default, result=True, reason='truthy_string'
            )
            return True
        if text in _FALSY_BOOL_STRINGS:
            _record_bool_coercion(
                value, default=default, result=False, reason='falsy_string'
            )
            return False

        result = False
        _record_bool_coercion(
            value,
            default=default,
            result=result,
            reason='unknown_string',
        )
        return result

    result = bool(value)
    _record_bool_coercion(value, default=default, result=result, reason='fallback')
    return result


def _coerce_int(value: Any, *, default: int) -> int:
    """Return an integer, falling back to ``default`` when conversion fails."""

    if isinstance(value, bool):
        return 1 if value else default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _coerce_float(value: Any, *, default: float) -> float:
    """Return a float, tolerating numeric strings and integers."""

    if isinstance(value, bool):
        return 1.0 if value else default
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _coerce_str(value: Any, *, default: str) -> str:
    """Return a trimmed string value or the provided default."""

    if isinstance(value, str):
        text = value.strip()
        return text or default
    return default


PerformanceMode = Literal['minimal', 'balanced', 'full']
DashboardMode = Literal['full', 'cards', 'minimal']

type ConfigFlowPlaceholderValue = bool | int | float | str
type ConfigFlowPlaceholders = Mapping[str, ConfigFlowPlaceholderValue]
type MutableConfigFlowPlaceholders = dict[str, ConfigFlowPlaceholderValue]
"""Accepted performance mode values for coordinator tuning."""


def clone_placeholders(
    template: ConfigFlowPlaceholders,
) -> MutableConfigFlowPlaceholders:
    """Return a mutable copy of an immutable placeholder template."""

    return dict(template)


def freeze_placeholders(
    placeholders: MutableConfigFlowPlaceholders,
) -> ConfigFlowPlaceholders:
    """Return an immutable placeholder mapping."""

    return cast(ConfigFlowPlaceholders, MappingProxyType(dict(placeholders)))


PERFORMANCE_MODE_VALUES: Final[frozenset[PerformanceMode]] = frozenset(
    ('minimal', 'balanced', 'full')
)
"""Canonical performance mode options for the integration."""


PERFORMANCE_MODE_ALIASES: Final[Mapping[str, PerformanceMode]] = MappingProxyType(
    {'standard': 'balanced'}
)
"""Backward-compatible aliases mapped to canonical performance modes."""


def _coerce_clamped_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    """Return an integer constrained to the provided inclusive bounds."""

    candidate = _coerce_int(value, default=default)
    if candidate < minimum:
        return minimum
    if candidate > maximum:
        return maximum
    return candidate


def normalize_performance_mode(
    value: Any,
    *,
    current: str | None = None,
    fallback: PerformanceMode = 'balanced',
) -> PerformanceMode:
    """Return a supported performance mode string."""

    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in PERFORMANCE_MODE_VALUES:
            return cast(PerformanceMode, candidate)
        alias = PERFORMANCE_MODE_ALIASES.get(candidate)
        if alias is not None:
            return alias

    if isinstance(current, str):
        existing = current.strip().lower()
        if existing in PERFORMANCE_MODE_VALUES:
            return cast(PerformanceMode, existing)
        alias = PERFORMANCE_MODE_ALIASES.get(existing)
        if alias is not None:
            return alias

    return fallback


def ensure_advanced_options(
    source: JSONLikeMapping,
    *,
    defaults: JSONLikeMapping | None = None,
) -> AdvancedOptions:
    """Normalise advanced options payloads for config entry storage."""

    baseline = defaults or {}

    retention_default = _coerce_int(baseline.get('data_retention_days'), default=90)
    debug_default = _coerce_bool(baseline.get('debug_logging'), default=False)
    backup_default = _coerce_bool(baseline.get('auto_backup'), default=False)
    experimental_default = _coerce_bool(
        baseline.get('experimental_features'), default=False
    )
    integrations_default = _coerce_bool(
        baseline.get(CONF_EXTERNAL_INTEGRATIONS), default=False
    )
    endpoint_default = _coerce_str(baseline.get(CONF_API_ENDPOINT), default='')
    token_default = _coerce_str(baseline.get(CONF_API_TOKEN), default='')

    advanced: AdvancedOptions = {
        'performance_mode': normalize_performance_mode(
            source.get('performance_mode'),
            current=cast(str | None, baseline.get('performance_mode')),
        ),
        'debug_logging': _coerce_bool(
            source.get('debug_logging'), default=debug_default
        ),
        'data_retention_days': _coerce_clamped_int(
            source.get('data_retention_days'),
            default=retention_default,
            minimum=30,
            maximum=365,
        ),
        'auto_backup': _coerce_bool(source.get('auto_backup'), default=backup_default),
        'experimental_features': _coerce_bool(
            source.get('experimental_features'), default=experimental_default
        ),
        'external_integrations': _coerce_bool(
            source.get(CONF_EXTERNAL_INTEGRATIONS), default=integrations_default
        ),
        'api_endpoint': _coerce_str(
            source.get(CONF_API_ENDPOINT), default=endpoint_default
        ),
        'api_token': _coerce_str(source.get(CONF_API_TOKEN), default=token_default),
    }

    return advanced


def _project_modules_mapping(
    config: ModuleToggleMapping | DogModulesConfig,
) -> dict[str, bool]:
    """Return a stable ``dict[str, bool]`` projection for module toggles."""

    mapping: dict[str, bool] = {}
    for key_literal in MODULE_TOGGLE_KEYS:
        key = cast(str, key_literal)
        mapping[key] = bool(config.get(key_literal, False))
    return mapping


def dog_modules_projection_from_flow_input(
    user_input: Mapping[str, object],
    *,
    existing: DogModulesConfig | None = None,
) -> DogModulesProjection:
    """Return module toggle projections built from config-flow toggles."""

    modules: dict[ModuleToggleKey, bool] = {}

    if existing:
        for key in MODULE_TOGGLE_KEYS:
            flag = existing.get(key)
            if isinstance(flag, bool):
                modules[key] = flag

    for flow_flag, module_key in MODULE_TOGGLE_FLOW_FLAGS:
        modules[module_key] = _coerce_bool(
            user_input.get(flow_flag), default=modules.get(module_key, False)
        )

    config: DogModulesConfig = {}
    for key in MODULE_TOGGLE_KEYS:
        if key in modules:
            config[key] = modules[key]
    mapping = _project_modules_mapping(config)
    return DogModulesProjection(config=config, mapping=mapping)


def dog_modules_from_flow_input(
    user_input: Mapping[str, object],
    *,
    existing: DogModulesConfig | None = None,
) -> DogModulesConfig:
    """Return a :class:`DogModulesConfig` built from config-flow toggles."""

    return dog_modules_projection_from_flow_input(user_input, existing=existing).config


def ensure_dog_modules_projection(
    data: ConfigFlowUserInput | DogModulesProjection,
) -> DogModulesProjection:
    """Extract module toggle projections from ``data``.

    ``data`` may already be a :class:`DogModulesProjection`, a mapping containing a
    ``modules`` key, or a raw mapping of module toggle flags. The helper normalises
    all variants into the projection structure used throughout the integration so
    downstream consumers can rely on a consistent schema when static typing is
    enforced.
    """

    if isinstance(data, DogModulesProjection):
        return data

    modules: dict[ModuleToggleKey, bool] = {}
    modules_raw = data.get(DOG_MODULES_FIELD)
    candidate = modules_raw if isinstance(modules_raw, Mapping) else data

    for key in MODULE_TOGGLE_KEYS:
        value = candidate.get(key)
        if value is not None:
            modules[key] = _coerce_bool(value)

    config: DogModulesConfig = {}
    for key in MODULE_TOGGLE_KEYS:
        if key in modules:
            config[key] = modules[key]
    mapping = _project_modules_mapping(config)
    return DogModulesProjection(config=config, mapping=mapping)


def ensure_dog_modules_config(
    data: Mapping[str, object] | DogModulesProjection,
) -> DogModulesConfig:
    """Extract a :class:`DogModulesConfig` from supported module payloads."""

    return ensure_dog_modules_projection(data).config


def _is_modules_projection_like(value: Any) -> bool:
    """Return ``True`` when ``value`` resembles a modules projection payload."""

    if isinstance(value, DogModulesProjection):
        return True

    return hasattr(value, 'config') and hasattr(value, 'mapping')


def coerce_dog_modules_config(
    payload: ConfigFlowUserInput | DogModulesProjection | DogModulesConfig | None,
) -> DogModulesConfig:
    """Return a defensive ``DogModulesConfig`` copy tolerant of projections."""

    if _is_modules_projection_like(payload):
        config_attr = getattr(payload, 'config', None)
        if isinstance(config_attr, Mapping):
            return cast(DogModulesConfig, dict(config_attr))

    if isinstance(payload, Mapping):
        config = ensure_dog_modules_config(payload)
        return cast(DogModulesConfig, dict(config))

    return cast(DogModulesConfig, {})


def ensure_dog_modules_mapping(
    data: Mapping[str, object] | DogModulesProjection,
) -> DogModulesMapping:
    """Return a ``DogModulesMapping`` projection from ``data``."""

    return ensure_dog_modules_projection(data).mapping


def dog_feeding_config_from_flow(user_input: DogFeedingStepInput) -> DogFeedingConfig:
    """Build a :class:`DogFeedingConfig` structure from flow input data."""

    meals_per_day = max(1, _coerce_int(user_input.get(CONF_MEALS_PER_DAY), default=2))
    daily_amount = _coerce_float(user_input.get(CONF_DAILY_FOOD_AMOUNT), default=500.0)
    portion_size = daily_amount / meals_per_day if meals_per_day else 0.0

    feeding_config: DogFeedingConfig = {
        'meals_per_day': meals_per_day,
        'daily_food_amount': daily_amount,
        'portion_size': portion_size,
        'food_type': _coerce_str(user_input.get(CONF_FOOD_TYPE), default='dry_food'),
        'feeding_schedule': _coerce_str(
            user_input.get('feeding_schedule'), default='flexible'
        ),
        'enable_reminders': _coerce_bool(
            user_input.get('enable_reminders'), default=True
        ),
        'reminder_minutes_before': _coerce_int(
            user_input.get('reminder_minutes_before'), default=15
        ),
    }

    if _coerce_bool(user_input.get('breakfast_enabled'), default=meals_per_day >= 1):
        feeding_config['breakfast_time'] = _coerce_str(
            user_input.get(CONF_BREAKFAST_TIME), default='07:00:00'
        )

    if _coerce_bool(user_input.get('lunch_enabled'), default=meals_per_day >= 3):
        feeding_config['lunch_time'] = _coerce_str(
            user_input.get(CONF_LUNCH_TIME), default='12:00:00'
        )

    if _coerce_bool(user_input.get('dinner_enabled'), default=meals_per_day >= 2):
        feeding_config['dinner_time'] = _coerce_str(
            user_input.get(CONF_DINNER_TIME), default='18:00:00'
        )

    if _coerce_bool(user_input.get('snacks_enabled'), default=False):
        feeding_config['snack_times'] = list(DEFAULT_FEEDING_SCHEDULE)

    return feeding_config


class DogGPSConfig(TypedDict, total=False):
    """GPS configuration captured during the dog setup flow."""

    gps_source: str
    gps_update_interval: int
    gps_accuracy_filter: float | int
    enable_geofencing: bool
    home_zone_radius: int | float


class DogGPSStepInput(TypedDict, total=False):
    """Raw GPS form payload provided during per-dog configuration."""

    gps_source: str
    gps_update_interval: int
    gps_accuracy_filter: float | int
    enable_geofencing: bool
    home_zone_radius: float | int


class GeofenceSettingsInput(TypedDict, total=False):
    """Options flow payload captured while editing geofencing settings."""

    geofencing_enabled: bool
    use_home_location: bool
    geofence_lat: float | int | str | None
    geofence_lon: float | int | str | None
    geofence_radius_m: float | int | str | None
    geofence_alerts_enabled: bool
    safe_zone_alerts: bool
    restricted_zone_alerts: bool
    zone_entry_notifications: bool
    zone_exit_notifications: bool


class DogFeedingStepInput(TypedDict, total=False):
    """Form payload captured during the per-dog feeding configuration step."""

    meals_per_day: int | float | str | None
    daily_food_amount: float | int | str | None
    food_type: str | None
    feeding_schedule: str | None
    breakfast_enabled: bool
    breakfast_time: str | None
    lunch_enabled: bool
    lunch_time: str | None
    dinner_enabled: bool
    dinner_time: str | None
    snacks_enabled: bool
    enable_reminders: bool
    reminder_minutes_before: int | float | str | None


class DogHealthStepInput(TypedDict, total=False):
    """Health configuration form payload recorded for a single dog."""

    vet_name: str | None
    vet_phone: str | None
    last_vet_visit: str | None
    next_checkup: str | None
    weight_tracking: bool
    ideal_weight: float | int | str | None
    body_condition_score: int | str | None
    activity_level: str | None
    weight_goal: str | None
    spayed_neutered: bool
    health_aware_portions: bool
    other_health_conditions: str | None
    has_diabetes: bool
    has_kidney_disease: bool
    has_heart_disease: bool
    has_arthritis: bool
    has_allergies: bool
    has_digestive_issues: bool
    grain_free: bool
    hypoallergenic: bool
    low_fat: bool
    senior_formula: bool
    puppy_formula: bool
    weight_control: bool
    sensitive_stomach: bool
    organic: bool
    raw_diet: bool
    prescription: bool
    diabetic: bool
    kidney_support: bool
    dental_care: bool
    joint_support: bool
    rabies_vaccination: str | None
    rabies_next: str | None
    dhpp_vaccination: str | None
    dhpp_next: str | None
    bordetella_vaccination: str | None
    bordetella_next: str | None
    medication_1_name: str | None
    medication_1_dosage: str | None
    medication_1_frequency: str | None
    medication_1_time: str | None
    medication_1_notes: str | None
    medication_1_with_meals: bool
    medication_2_name: str | None
    medication_2_dosage: str | None
    medication_2_frequency: str | None
    medication_2_time: str | None
    medication_2_notes: str | None
    medication_2_with_meals: bool


class DogFeedingConfig(TypedDict, total=False):
    """Feeding configuration captured during setup."""

    meals_per_day: int
    daily_food_amount: float | int
    food_type: str
    feeding_schedule: str
    breakfast_time: str
    lunch_time: str
    dinner_time: str
    snack_times: list[str]
    enable_reminders: bool
    reminder_minutes_before: int
    portion_size: float | int
    health_aware_portions: bool
    dog_weight: float | int | None
    ideal_weight: float | int | None
    age_months: int | None
    breed_size: str
    activity_level: str
    body_condition_score: int
    health_conditions: list[str]
    weight_goal: str
    spayed_neutered: bool
    special_diet: list[str]
    diet_validation: DietValidationResult
    medication_with_meals: bool


class GeofenceOptions(TypedDict, total=False):
    """Options structure describing geofencing configuration for a profile."""

    geofencing_enabled: bool
    use_home_location: bool
    geofence_lat: float | None
    geofence_lon: float | None
    geofence_radius_m: int
    geofence_alerts_enabled: bool
    safe_zone_alerts: bool
    restricted_zone_alerts: bool
    zone_entry_notifications: bool
    zone_exit_notifications: bool


GeofenceOptionsField = Literal[
    'geofencing_enabled',
    'use_home_location',
    'geofence_lat',
    'geofence_lon',
    'geofence_radius_m',
    'geofence_alerts_enabled',
    'safe_zone_alerts',
    'restricted_zone_alerts',
    'zone_entry_notifications',
    'zone_exit_notifications',
]
GEOFENCE_ENABLED_FIELD: Final[GeofenceOptionsField] = 'geofencing_enabled'
GEOFENCE_USE_HOME_FIELD: Final[GeofenceOptionsField] = 'use_home_location'
GEOFENCE_LAT_FIELD: Final[GeofenceOptionsField] = 'geofence_lat'
GEOFENCE_LON_FIELD: Final[GeofenceOptionsField] = 'geofence_lon'
GEOFENCE_RADIUS_FIELD: Final[GeofenceOptionsField] = 'geofence_radius_m'
GEOFENCE_ALERTS_FIELD: Final[GeofenceOptionsField] = 'geofence_alerts_enabled'
GEOFENCE_SAFE_ZONE_FIELD: Final[GeofenceOptionsField] = 'safe_zone_alerts'
GEOFENCE_RESTRICTED_ZONE_FIELD: Final[GeofenceOptionsField] = 'restricted_zone_alerts'
GEOFENCE_ZONE_ENTRY_FIELD: Final[GeofenceOptionsField] = 'zone_entry_notifications'
GEOFENCE_ZONE_EXIT_FIELD: Final[GeofenceOptionsField] = 'zone_exit_notifications'


class NotificationOptions(TypedDict, total=False):
    """Structured notification preferences stored in config entry options."""

    quiet_hours: bool
    quiet_start: str
    quiet_end: str
    reminder_repeat_min: int
    priority_notifications: bool
    mobile_notifications: bool


NotificationOptionsField = Literal[
    'quiet_hours',
    'quiet_start',
    'quiet_end',
    'reminder_repeat_min',
    'priority_notifications',
    'mobile_notifications',
]
NOTIFICATION_QUIET_HOURS_FIELD: Final[NotificationOptionsField] = 'quiet_hours'
NOTIFICATION_QUIET_START_FIELD: Final[NotificationOptionsField] = 'quiet_start'
NOTIFICATION_QUIET_END_FIELD: Final[NotificationOptionsField] = 'quiet_end'
NOTIFICATION_REMINDER_REPEAT_FIELD: Final[NotificationOptionsField] = (
    'reminder_repeat_min'
)
NOTIFICATION_PRIORITY_FIELD: Final[NotificationOptionsField] = 'priority_notifications'
NOTIFICATION_MOBILE_FIELD: Final[NotificationOptionsField] = 'mobile_notifications'


type NotificationOptionsInput = NotificationSettingsInput | JSONMapping
"""Mapping accepted by :func:`ensure_notification_options`."""


DEFAULT_NOTIFICATION_OPTIONS: Final[NotificationOptionsInput] = MappingProxyType(
    {
        NOTIFICATION_QUIET_HOURS_FIELD: True,
        NOTIFICATION_QUIET_START_FIELD: '22:00:00',
        NOTIFICATION_QUIET_END_FIELD: '07:00:00',
        NOTIFICATION_REMINDER_REPEAT_FIELD: DEFAULT_REMINDER_REPEAT_MIN,
        NOTIFICATION_PRIORITY_FIELD: True,
        NOTIFICATION_MOBILE_FIELD: True,
    }
)


class NotificationSettingsInput(TypedDict, total=False):
    """UI payload captured when editing notification options."""

    quiet_hours: bool
    quiet_start: str | None
    quiet_end: str | None
    reminder_repeat_min: int | float | str | None
    priority_notifications: bool
    mobile_notifications: bool


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
    """

    options: NotificationOptions = {}

    def _coerce_bool(candidate: Any) -> bool | None:
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, int | float):
            return bool(candidate)
        if isinstance(candidate, str):
            lowered = candidate.strip().lower()
            if lowered in {'true', 'yes', 'on', '1'}:
                return True
            if lowered in {'false', 'no', 'off', '0'}:
                return False
        return None

    def _coerce_time(candidate: Any) -> str | None:
        if isinstance(candidate, str):
            trimmed = candidate.strip()
            if trimmed:
                return trimmed
        return None

    def _coerce_interval(candidate: Any) -> int | None:
        working = candidate
        if isinstance(working, str):
            working = working.strip()
            if not working:
                return None
            try:
                working = int(working)
            except ValueError:
                return None
        if isinstance(working, int | float):
            interval = int(working)
            return max(5, min(180, interval))
        return None

    def _apply(
        source_key: str,
        target_key: NotificationOptionsField,
        converter: Callable[[Any], Any | None],
    ) -> None:
        if defaults is not None:
            default_value = converter(defaults.get(source_key))
            if default_value is not None:
                options[target_key] = default_value
        override = converter(value.get(source_key))
        if override is not None:
            options[target_key] = override

    _apply(CONF_QUIET_HOURS, NOTIFICATION_QUIET_HOURS_FIELD, _coerce_bool)
    _apply(CONF_QUIET_START, NOTIFICATION_QUIET_START_FIELD, _coerce_time)
    _apply(CONF_QUIET_END, NOTIFICATION_QUIET_END_FIELD, _coerce_time)
    _apply(
        CONF_REMINDER_REPEAT_MIN, NOTIFICATION_REMINDER_REPEAT_FIELD, _coerce_interval
    )
    _apply('priority_notifications', NOTIFICATION_PRIORITY_FIELD, _coerce_bool)
    _apply('mobile_notifications', NOTIFICATION_MOBILE_FIELD, _coerce_bool)

    return options


NotificationThreshold = Literal['low', 'moderate', 'high']


class WeatherOptions(TypedDict, total=False):
    """Typed weather monitoring preferences stored in config entry options."""

    weather_entity: str | None
    weather_health_monitoring: bool
    weather_alerts: bool
    weather_update_interval: int
    temperature_alerts: bool
    uv_alerts: bool
    humidity_alerts: bool
    wind_alerts: bool
    storm_alerts: bool
    breed_specific_recommendations: bool
    health_condition_adjustments: bool
    auto_activity_adjustments: bool
    notification_threshold: NotificationThreshold


class FeedingOptions(TypedDict, total=False):
    """Typed feeding configuration stored in config entry options."""

    default_meals_per_day: int
    feeding_reminders: bool
    portion_tracking: bool
    calorie_tracking: bool
    auto_schedule: bool


class HealthOptions(TypedDict, total=False):
    """Typed health configuration stored in config entry options."""

    weight_tracking: bool
    medication_reminders: bool
    vet_reminders: bool
    grooming_reminders: bool
    health_alerts: bool


class SystemOptions(TypedDict, total=False):
    """System-wide maintenance preferences persisted in options."""

    data_retention_days: int
    auto_backup: bool
    performance_mode: PerformanceMode
    enable_analytics: bool
    enable_cloud_backup: bool
    resilience_skip_threshold: int
    resilience_breaker_threshold: int
    manual_check_event: str | None
    manual_guard_event: str | None
    manual_breaker_event: str | None


class DashboardOptions(TypedDict, total=False):
    """Dashboard rendering preferences for the integration."""

    show_statistics: bool
    show_alerts: bool
    compact_mode: bool
    show_maps: bool


class DashboardRendererOptions(DashboardOptions, total=False):
    """Extended dashboard options consumed by the async renderer."""

    show_settings: bool
    show_activity_summary: bool
    dashboard_url: str
    theme: str
    title: str
    icon: str
    url: str
    layout: str
    show_in_sidebar: bool
    show_activity_graph: bool
    show_breed_advice: bool
    show_weather_forecast: bool


type DashboardCardOptions = DashboardRendererOptions
"""Card generator options forwarded from the dashboard renderer."""


class DashboardCardPerformanceStats(TypedDict):
    """Performance counters tracked while generating dashboard cards."""

    validations_count: int
    cache_hits: int
    cache_misses: int
    generation_time_total: float
    errors_handled: int


class DashboardCardGlobalPerformanceStats(TypedDict):
    """Static performance characteristics for dashboard card generation."""

    validation_cache_size: int
    cache_threshold: float
    max_concurrent_validations: int
    validation_timeout: float
    card_generation_timeout: float


class TemplateCacheStats(TypedDict):
    """Statistics returned by the in-memory dashboard template cache."""

    hits: int
    misses: int
    hit_rate: float
    cached_items: int
    evictions: int
    max_size: int


class TemplateCacheDiagnosticsMetadata(TypedDict):
    """Metadata describing the template cache configuration."""

    cached_keys: list[str]
    ttl_seconds: int
    max_size: int
    evictions: int


class TemplateCacheSnapshot(TypedDict):
    """Complete snapshot exported for diagnostics and telemetry."""

    stats: TemplateCacheStats
    metadata: TemplateCacheDiagnosticsMetadata


class CardModConfig(TypedDict, total=False):
    """Styling payload supported by card-mod aware templates."""

    style: str


type LovelaceCardValue = (
    JSONPrimitive
    | Sequence['LovelaceCardValue']
    | Mapping[str, 'LovelaceCardValue']
    | CardModConfig
)
"""Valid value stored inside a Lovelace card configuration."""


type LovelaceCardConfig = dict[str, LovelaceCardValue]
"""Mutable Lovelace card configuration payload."""


class LovelaceViewConfig(TypedDict, total=False):
    """Typed Lovelace view configuration produced by the renderer."""

    title: str
    path: str
    icon: str
    theme: NotRequired[str]
    cards: list[LovelaceCardConfig]
    badges: NotRequired[list[str]]
    type: NotRequired[str]


class DashboardRenderResult(TypedDict):
    """Typed dashboard payload emitted by the async renderer."""

    views: list[LovelaceViewConfig]


class DashboardRenderJobConfig(TypedDict, total=False):
    """Payload stored on queued render jobs."""

    dogs: Sequence[DogConfigData]
    dog: DogConfigData
    coordinator_statistics: CoordinatorStatisticsPayload | JSONMapping
    service_execution_metrics: CoordinatorRejectionMetrics | JSONMapping
    service_guard_metrics: HelperManagerGuardMetrics | JSONMapping


class DashboardRendererStatistics(TypedDict):
    """Summary statistics describing renderer state."""

    active_jobs: int
    total_jobs_processed: int
    template_cache: TemplateCacheStats


class SwitchExtraAttributes(TypedDict, total=False):
    """Common state attributes exposed by optimized switches."""

    dog_id: str
    dog_name: str
    switch_type: str
    last_changed: str
    profile_optimized: bool
    enabled_modules: list[str]
    total_modules: int


class SwitchFeatureAttributes(SwitchExtraAttributes, total=False):
    """Additional metadata surfaced by feature-level switches."""

    feature_id: str
    parent_module: str
    feature_name: str


class AdvancedOptions(TypedDict, total=False):
    """Advanced diagnostics and integration toggles stored on the entry."""

    performance_mode: PerformanceMode
    debug_logging: bool
    data_retention_days: int
    auto_backup: bool
    experimental_features: bool
    external_integrations: bool
    api_endpoint: str
    api_token: str


class PerformanceOptions(TypedDict, total=False):
    """Performance tuning parameters applied through the options flow."""

    entity_profile: str
    performance_mode: PerformanceMode
    batch_size: int
    cache_ttl: int
    selective_refresh: bool


class GPSOptions(TypedDict, total=False):
    """Global GPS configuration stored in the options flow."""

    gps_enabled: bool
    gps_update_interval: int
    gps_accuracy_filter: float
    gps_distance_filter: float
    route_recording: bool
    route_history_days: int
    auto_track_walks: bool


class DogOptionsEntry(TypedDict, total=False):
    """Per-dog overrides captured via the options flow."""

    dog_id: str
    modules: DogModulesConfig
    notifications: NotificationOptions
    gps_settings: GPSOptions
    geofence_settings: GeofenceOptions
    feeding_settings: FeedingOptions
    health_settings: HealthOptions


type DogOptionsMap = dict[str, DogOptionsEntry]


class PawControlOptionsData(PerformanceOptions, total=False):
    """Complete options mapping persisted on :class:`ConfigEntry` objects."""

    geofence_settings: GeofenceOptions
    notifications: NotificationOptions
    weather_settings: WeatherOptions
    feeding_settings: FeedingOptions
    health_settings: HealthOptions
    system_settings: SystemOptions
    dashboard_settings: DashboardOptions
    advanced_settings: AdvancedOptions
    gps_settings: GPSOptions
    gps_update_interval: int
    gps_distance_filter: float
    gps_accuracy_filter: float
    external_integrations: bool
    api_endpoint: str
    api_token: str
    weather_entity: str | None
    reset_time: str
    data_retention_days: int
    modules: DogModulesConfig
    dog_options: DogOptionsMap
    dogs: list[DogConfigData]
    import_source: str
    last_reauth: NotRequired[str]
    reauth_health_issues: NotRequired[list[str]]
    reauth_health_warnings: NotRequired[list[str]]
    last_reauth_summary: NotRequired[str]
    enable_analytics: bool
    enable_cloud_backup: bool
    debug_logging: bool


ConfigFlowDiscoverySource = Literal[
    'zeroconf',
    'dhcp',
    'usb',
    'bluetooth',
    'import',
    'reauth',
    'unknown',
]


type ConfigFlowDiscoveryPropertyValue = bool | int | float | str | bytes | Sequence[str]


type ConfigFlowDiscoveryProperties = dict[str, ConfigFlowDiscoveryPropertyValue]


type ConfigFlowInputMapping = Mapping[str, JSONValue]
"""Generic mapping accepted by config flow steps for user input payloads."""


class ConfigFlowImportData(TypedDict):
    """Config entry data payload produced when importing YAML configuration."""

    name: str
    dogs: list[DogConfigData]
    entity_profile: str
    import_warnings: list[str]
    import_timestamp: str


class ConfigFlowImportOptions(TypedDict):
    """Config entry options payload produced when importing YAML configuration."""

    entity_profile: str
    dashboard_enabled: bool
    dashboard_auto_create: bool
    import_source: Literal['configuration_yaml']


class ConfigFlowImportResult(TypedDict):
    """Structured result returned by enhanced config-flow import validation."""

    data: ConfigFlowImportData
    options: ConfigFlowImportOptions


class ConfigFlowDiscoveryData(TypedDict, total=False):
    """Metadata captured from config flow discovery sources."""

    source: ConfigFlowDiscoverySource
    hostname: str
    host: str
    port: int
    ip: str
    macaddress: str
    properties: ConfigFlowDiscoveryProperties
    type: str
    name: str
    description: str
    manufacturer: str
    vid: str
    pid: str
    serial_number: str
    device: str
    address: str
    service_uuids: list[str]
    last_seen: str


type ConfigFlowDiscoveryComparison = ConfigFlowDiscoveryData
"""Normalized discovery payload used for change comparison in config flows."""


type DiscoveryUpdateValue = ConfigFlowDiscoveryData | str
"""Allowed value types stored in discovery update payloads."""


class DiscoveryUpdatePayload(TypedDict, total=False):
    """Updates persisted on config entries when discovery metadata changes."""

    discovery_info: ConfigFlowDiscoveryData
    host: str
    device: str
    address: str


class DiscoveryConfirmInput(TypedDict, total=False):
    """Form payload submitted when the user confirms discovery."""

    confirm: bool


class ProfileSelectionInput(TypedDict, total=False):
    """User input captured when selecting an entity profile."""

    entity_profile: str


class ProfileSelectorOption(TypedDict):
    """Selector option exposed when rendering profile choices."""

    value: str
    label: str


class EntityProfileOptionsInput(ProfileSelectionInput, total=False):
    """Options flow payload for selecting an entity profile."""

    preview_estimate: bool


class IntegrationNameValidationResult(TypedDict):
    """Validation response for integration name checks during setup."""

    valid: bool
    errors: dict[str, str]


class ConfigFlowGlobalSettings(TypedDict, total=False):
    """Global configuration captured during the setup flow."""

    performance_mode: PerformanceMode
    enable_analytics: bool
    enable_cloud_backup: bool
    data_retention_days: int
    debug_logging: bool


class FinalSetupValidationResult(TypedDict):
    """Outcome returned by the final setup validation pass."""

    valid: bool
    errors: list[str]
    estimated_entities: int


class ConfigEntryDataPayload(TypedDict, total=False):
    """Config entry data stored when onboarding PawControl."""

    name: Required[str]
    dogs: Required[list[DogConfigData]]
    entity_profile: Required[str]
    setup_timestamp: Required[str]
    discovery_info: NotRequired[ConfigFlowDiscoveryData]


class ConfigEntryOptionsPayload(PawControlOptionsData, total=False):
    """Options mapping persisted alongside PawControl config entries."""

    dashboard_enabled: bool
    dashboard_auto_create: bool
    performance_monitoring: bool
    last_reconfigure: NotRequired[str]
    previous_profile: NotRequired[str]
    reconfigure_telemetry: NotRequired[ReconfigureTelemetry]
    dashboard_mode: DashboardMode
    manual_guard_event: str | None
    manual_breaker_event: str | None
    manual_check_event: str | None


class ModuleConfigurationStepInput(TypedDict, total=False):
    """User-provided values collected during the module setup step."""

    performance_mode: PerformanceMode
    enable_analytics: bool
    enable_cloud_backup: bool
    data_retention_days: int
    debug_logging: bool
    enable_notifications: bool
    enable_dashboard: bool
    auto_backup: bool


class ModuleConfigurationSnapshot(TypedDict):
    """Persisted view of the global module configuration toggles."""

    enable_notifications: bool
    enable_dashboard: bool
    performance_mode: PerformanceMode
    data_retention_days: int
    auto_backup: bool
    debug_logging: bool


class DashboardSetupConfig(TypedDict, total=False):
    """Dashboard preferences collected during setup before persistence."""

    dashboard_enabled: bool
    dashboard_auto_create: bool
    dashboard_per_dog: bool
    dashboard_theme: str
    dashboard_mode: DashboardMode
    dashboard_template: str
    show_statistics: bool
    show_maps: bool
    show_health_charts: bool
    show_feeding_schedule: bool
    show_alerts: bool
    compact_mode: bool
    auto_refresh: bool
    refresh_interval: int


class DashboardConfigurationStepInput(TypedDict, total=False):
    """Raw dashboard configuration payload received from the UI step."""

    auto_create_dashboard: bool
    create_per_dog_dashboards: bool
    dashboard_theme: str
    dashboard_template: str
    dashboard_mode: DashboardMode
    show_statistics: bool
    show_maps: bool
    show_health_charts: bool
    show_feeding_schedule: bool
    show_alerts: bool
    compact_mode: bool
    auto_refresh: bool
    refresh_interval: int


class AddAnotherDogInput(TypedDict, total=False):
    """Payload for yes/no "add another dog" prompts in flows."""

    add_another: bool


type OptionsMainMenuAction = Literal[
    'entity_profiles',
    'manage_dogs',
    'performance_settings',
    'gps_settings',
    'geofence_settings',
    'weather_settings',
    'notifications',
    'feeding_settings',
    'health_settings',
    'system_settings',
    'dashboard_settings',
    'advanced_settings',
    'import_export',
]
"""Supported menu actions for the options flow root menu."""


class OptionsMainMenuInput(TypedDict, total=False):
    """Menu selection payload for the options flow root."""

    action: OptionsMainMenuAction


type OptionsMenuAction = Literal[
    'add_dog',
    'edit_dog',
    'remove_dog',
    'configure_modules',
    'configure_door_sensor',
    'back',
]
"""Supported menu actions for the options flow dog management step."""


class OptionsMenuInput(TypedDict, total=False):
    """Menu selection payload for the dog management options menu."""

    action: OptionsMenuAction


class OptionsDogSelectionInput(TypedDict, total=False):
    """Payload used when selecting a dog in the options flow."""

    dog_id: str


class OptionsDogRemovalInput(OptionsDogSelectionInput, total=False):
    """Payload used when confirming dog removal in the options flow."""

    confirm_remove: bool


class OptionsDogEditInput(TypedDict, total=False):
    """Payload for editing dog metadata in the options flow."""

    dog_name: str
    dog_breed: str
    dog_age: int | float | str | None
    dog_weight: int | float | str | None
    dog_size: str | None


class OptionsProfilePreviewInput(TypedDict, total=False):
    """Payload used for profile preview interactions in the options flow."""

    profile: str
    apply_profile: bool


class OptionsPerformanceSettingsInput(TypedDict, total=False):
    """Payload for performance settings in the options flow."""

    entity_profile: str
    performance_mode: PerformanceMode
    batch_size: int | float | str | None
    cache_ttl: int | float | str | None
    selective_refresh: bool


class OptionsDogModulesInput(TypedDict, total=False):
    """Payload for per-dog module configuration in the options flow."""

    module_feeding: bool
    module_walk: bool
    module_gps: bool
    module_garden: bool
    module_health: bool
    module_notifications: bool
    module_dashboard: bool
    module_visitor: bool
    module_grooming: bool
    module_medication: bool
    module_training: bool


class OptionsDoorSensorInput(TypedDict, total=False):
    """Payload for configuring door sensor overrides in the options flow."""

    door_sensor: str | None
    walk_detection_timeout: int | float | str | None
    minimum_walk_duration: int | float | str | None
    maximum_walk_duration: int | float | str | None
    door_closed_delay: int | float | str | None
    require_confirmation: bool | int | float | str | None
    auto_end_walks: bool | int | float | str | None
    confidence_threshold: int | float | str | None


class OptionsGeofenceInput(TypedDict, total=False):
    """Payload for geofencing configuration in the options flow."""

    geofence_enabled: bool
    geofence_use_home: bool
    geofence_lat: float | int | str | None
    geofence_lon: float | int | str | None
    geofence_radius: int | float | str | None
    geofence_alerts: bool
    geofence_safe_zone: bool
    geofence_restricted_zone: bool
    geofence_zone_entry: bool
    geofence_zone_exit: bool


class OptionsGPSSettingsInput(TypedDict, total=False):
    """Payload for GPS settings in the options flow."""

    gps_enabled: bool
    gps_update_interval: int | float | str | None
    gps_accuracy_filter: int | float | str | None
    gps_distance_filter: int | float | str | None
    route_recording: bool
    route_history_days: int | float | str | None
    auto_track_walks: bool


class OptionsWeatherSettingsInput(TypedDict, total=False):
    """Payload for weather settings in the options flow."""

    weather_entity: str | None
    weather_health_monitoring: bool
    weather_alerts: bool
    weather_update_interval: int | float | str | None
    temperature_alerts: bool
    uv_alerts: bool
    humidity_alerts: bool
    wind_alerts: bool
    storm_alerts: bool
    breed_specific_recommendations: bool
    health_condition_adjustments: bool
    auto_activity_adjustments: bool
    notification_threshold: str | None


class OptionsFeedingSettingsInput(TypedDict, total=False):
    """Payload for feeding settings in the options flow."""

    meals_per_day: int | float | str | None
    feeding_reminders: bool
    portion_tracking: bool
    calorie_tracking: bool
    auto_schedule: bool


class OptionsHealthSettingsInput(TypedDict, total=False):
    """Payload for health settings in the options flow."""

    weight_tracking: bool
    medication_reminders: bool
    vet_reminders: bool
    grooming_reminders: bool
    health_alerts: bool


class OptionsSystemSettingsInput(TypedDict, total=False):
    """Payload for system settings in the options flow."""

    data_retention_days: int | float | str | None
    auto_backup: bool
    performance_mode: PerformanceMode
    enable_analytics: bool
    enable_cloud_backup: bool
    resilience_skip_threshold: int | float | str | None
    resilience_breaker_threshold: int | float | str | None
    manual_check_event: str | None
    manual_guard_event: str | None
    manual_breaker_event: str | None
    reset_time: str | None


class OptionsDashboardSettingsInput(TypedDict, total=False):
    """Payload for dashboard settings in the options flow."""

    dashboard_mode: DashboardMode
    show_statistics: bool
    show_alerts: bool
    compact_mode: bool
    show_maps: bool


class OptionsAdvancedSettingsInput(TypedDict, total=False):
    """Payload for advanced settings in the options flow."""

    performance_mode: PerformanceMode
    debug_logging: bool
    data_retention_days: int | float | str | None
    auto_backup: bool
    experimental_features: bool
    external_integrations: bool
    api_endpoint: str
    api_token: str


class OptionsImportExportInput(TypedDict, total=False):
    """Payload for import/export selection in the options flow."""

    action: Literal['export', 'import']


class OptionsExportDisplayInput(TypedDict, total=False):
    """Payload for export display steps in the options flow."""

    export_blob: str


class OptionsImportPayloadInput(TypedDict, total=False):
    """Payload for importing exported options data."""

    payload: str


class ConfigFlowOperationMetrics(TypedDict):
    """Aggregated metrics collected for a single config-flow operation."""

    avg_time: float
    max_time: float
    count: int


type ConfigFlowOperationMetricsMap = dict[str, ConfigFlowOperationMetrics]


class ConfigFlowPerformanceStats(TypedDict):
    """Snapshot describing config-flow performance diagnostics."""

    operations: ConfigFlowOperationMetricsMap
    validations: dict[str, int]


class FeedingSizeDefaults(TypedDict):
    """Default feeding configuration derived from the selected dog size."""

    meals_per_day: int
    daily_food_amount: int
    feeding_times: list[str]
    portion_size: int


type FeedingSizeDefaultsMap = dict[str, FeedingSizeDefaults]


class FeedingSetupConfig(TypedDict, total=False):
    """Feeding defaults gathered while configuring modules during setup."""

    default_daily_food_amount: float | int
    default_meals_per_day: int
    default_food_type: str
    default_special_diet: list[str]
    default_feeding_schedule_type: str
    auto_portion_calculation: bool
    medication_with_meals: bool
    feeding_reminders: bool
    portion_tolerance: int


class FeedingConfigurationStepInput(TypedDict, total=False):
    """Raw feeding configuration payload received from the UI step."""

    daily_food_amount: float | int
    meals_per_day: int
    food_type: str
    special_diet: list[str]
    feeding_schedule_type: str
    portion_calculation: bool
    medication_with_meals: bool
    feeding_reminders: bool
    portion_tolerance: int


class ModuleConfigurationPlaceholders(TypedDict):
    """Placeholders exposed while rendering the module configuration form."""

    dog_count: int
    module_summary: str
    total_modules: int
    gps_dogs: int
    health_dogs: int


class AddDogCapacityPlaceholders(TypedDict):
    """Placeholders rendered when summarising configured dogs."""

    dog_count: int
    max_dogs: int
    current_dogs: str
    remaining_spots: int


class DogModulesSuggestionPlaceholders(TypedDict):
    """Placeholders exposed while recommending per-dog modules."""

    dog_name: str
    dog_size: str
    dog_age: int


class AddDogSummaryPlaceholders(TypedDict):
    """Placeholders rendered on the main add-dog form."""

    dogs_configured: str
    max_dogs: str
    discovery_hint: str


class DogModulesSmartDefaultsPlaceholders(TypedDict):
    """Placeholders surfaced alongside smart module defaults."""

    dog_name: str
    dogs_configured: str
    smart_defaults: str


class AddAnotherDogPlaceholders(TypedDict):
    """Placeholders shown when asking to add another dog."""

    dogs_configured: str
    dogs_list: str
    can_add_more: str
    max_dogs: str
    performance_note: str


class AddAnotherDogSummaryPlaceholders(TypedDict):
    """Placeholders shown when summarising configured dogs."""

    dogs_list: str
    dog_count: str
    max_dogs: int
    remaining_spots: int
    at_limit: str


class DashboardConfigurationPlaceholders(TypedDict):
    """Placeholders used when rendering the dashboard configuration form."""

    dog_count: int
    dashboard_info: str
    features: str


class FeedingConfigurationPlaceholders(TypedDict):
    """Placeholders used when rendering the feeding configuration form."""

    dog_count: int
    feeding_summary: str


class DogGPSPlaceholders(TypedDict):
    """Placeholders surfaced in the per-dog GPS configuration step."""

    dog_name: str


class DogFeedingPlaceholders(TypedDict):
    """Placeholders rendered alongside the per-dog feeding configuration."""

    dog_name: str
    dog_weight: str
    suggested_amount: str
    portion_info: str


class DogHealthPlaceholders(TypedDict):
    """Placeholders rendered alongside the per-dog health configuration."""

    dog_name: str
    dog_age: str
    dog_weight: str
    suggested_ideal_weight: str
    suggested_activity: str
    medication_enabled: str
    bcs_info: str
    special_diet_count: str
    health_diet_info: str


class ModuleSetupSummaryPlaceholders(TypedDict):
    """Placeholders rendered when summarising enabled modules."""

    total_dogs: str
    gps_dogs: str
    health_dogs: str
    suggested_performance: str
    complexity_info: str
    next_step_info: str


class ExternalEntitiesPlaceholders(TypedDict):
    """Placeholders rendered while configuring external entities."""

    gps_enabled: bool
    visitor_enabled: bool
    dog_count: int


class ExternalEntitySelectorOption(TypedDict):
    """Selectable option exposed while configuring external entities."""

    value: str
    label: str


class ExternalEntityConfig(TypedDict, total=False):
    """External entity mappings selected throughout the setup flow."""

    gps_source: str
    door_sensor: str
    notify_fallback: str


class ModuleConfigurationSummary(TypedDict):
    """Aggregated per-module counts used while configuring dashboards."""

    total: int
    gps_dogs: int
    health_dogs: int
    feeding_dogs: int
    counts: dict[str, int]
    description: str


class OptionsExportPayload(TypedDict, total=False):
    """Structured payload captured by the options import/export tools."""

    version: Literal[1]
    options: PawControlOptionsData
    dogs: list[DogConfigData]
    created_at: str


class ReauthHealthSummary(TypedDict, total=False):
    """Normalised health snapshot gathered during reauthentication."""

    healthy: bool
    issues: list[str]
    warnings: list[str]
    validated_dogs: int
    total_dogs: int
    invalid_modules: NotRequired[int]
    dogs_count: NotRequired[int]
    valid_dogs: NotRequired[int]
    profile: NotRequired[str]
    estimated_entities: NotRequired[int]


class ReauthDataUpdates(TypedDict, total=False):
    """Data fields persisted on the config entry after reauth."""

    reauth_timestamp: str
    reauth_version: int
    health_status: bool
    health_validated_dogs: int
    health_total_dogs: int


class ReauthOptionsUpdates(TypedDict, total=False):
    """Options fields updated after a successful reauth."""

    last_reauth: str
    reauth_health_issues: list[str]
    reauth_health_warnings: list[str]
    last_reauth_summary: str


class ReauthConfirmInput(TypedDict, total=False):
    """Schema-constrained payload submitted by the reauth confirmation form."""

    confirm: bool


class ReauthPlaceholders(TypedDict):
    """Description placeholders rendered on the reauth confirm form."""

    integration_name: str
    dogs_count: str
    current_profile: str
    health_status: str


class ReconfigureProfileInput(TypedDict):
    """Schema-constrained payload submitted by the reconfigure form."""

    entity_profile: str


class ReconfigureCompatibilityResult(TypedDict):
    """Result of validating a profile change against existing dog configs."""

    compatible: bool
    warnings: list[str]


class ReconfigureDataUpdates(TypedDict, total=False):
    """Config entry data persisted after a successful reconfigure."""

    entity_profile: str
    reconfigure_timestamp: str
    reconfigure_version: int


class ReconfigureTelemetry(TypedDict, total=False):
    """Structured telemetry recorded for reconfigure operations."""

    requested_profile: str
    previous_profile: str
    dogs_count: int
    estimated_entities: int
    timestamp: str
    version: int
    compatibility_warnings: NotRequired[list[str]]
    health_summary: NotRequired[ReauthHealthSummary]
    valid_dogs: NotRequired[int]
    merge_notes: NotRequired[list[str]]


class ReconfigureTelemetrySummary(TypedDict, total=False):
    """Condensed view of reconfigure telemetry for diagnostics pipelines."""

    timestamp: str
    requested_profile: str
    previous_profile: str
    dogs_count: int
    estimated_entities: int
    version: int
    warnings: list[str]
    warning_count: int
    healthy: bool
    health_issues: list[str]
    health_issue_count: int
    health_warnings: list[str]
    health_warning_count: int
    merge_notes: list[str]
    merge_note_count: int


class ReconfigureOptionsUpdates(TypedDict, total=False):
    """Config entry options updated after a successful reconfigure."""

    entity_profile: str
    last_reconfigure: str
    previous_profile: str
    reconfigure_telemetry: ReconfigureTelemetry


class ReconfigureFormPlaceholders(TypedDict, total=False):
    """Description placeholders displayed on the reconfigure form."""

    current_profile: str
    profiles_info: str
    dogs_count: str
    compatibility_info: str
    estimated_entities: str
    error_details: str
    last_reconfigure: str
    reconfigure_requested_profile: str
    reconfigure_previous_profile: str
    reconfigure_dogs: str
    reconfigure_entities: str
    reconfigure_health: str
    reconfigure_warnings: str
    reconfigure_valid_dogs: str
    reconfigure_invalid_dogs: str
    reconfigure_merge_notes: str


class DogValidationResult(TypedDict):
    """Validation result payload for dog configuration forms."""

    valid: bool
    errors: dict[str, str]
    validated_input: NotRequired[DogSetupStepInput]


class DogValidationCacheEntry(TypedDict):
    """Cached validation result metadata for config and options flows."""

    result: DogValidationResult | DogSetupStepInput | None
    cached_at: float
    state_signature: NotRequired[str]


class DogSetupStepInput(TypedDict, total=False):
    """Minimal dog setup fields collected during the primary form."""

    dog_id: Required[str]
    dog_name: Required[str]
    dog_breed: str | None
    dog_age: int | float | None
    dog_weight: float | int | None
    dog_size: str | None
    weight: float | int | str | None


MODULE_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dog_count': 0,
            'module_summary': '',
            'total_modules': 0,
            'gps_dogs': 0,
            'health_dogs': 0,
        }
    ),
)
ADD_DOG_CAPACITY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dog_count': 0,
            'max_dogs': 0,
            'current_dogs': '',
            'remaining_spots': 0,
        }
    ),
)
DOG_MODULES_SUGGESTION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {'dog_name': '', 'dog_size': '', 'dog_age': 0},
    ),
)
ADD_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dogs_configured': '',
            'max_dogs': '',
            'discovery_hint': '',
        }
    ),
)
DOG_MODULES_SMART_DEFAULTS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dog_name': '',
            'dogs_configured': '',
            'smart_defaults': '',
        }
    ),
)
ADD_ANOTHER_DOG_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dogs_configured': '',
            'dogs_list': '',
            'can_add_more': '',
            'max_dogs': '',
            'performance_note': '',
        }
    ),
)
ADD_ANOTHER_DOG_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dogs_list': '',
            'dog_count': '',
            'max_dogs': 0,
            'remaining_spots': 0,
            'at_limit': '',
        }
    ),
)
DASHBOARD_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {'dog_count': 0, 'dashboard_info': '', 'features': ''},
    ),
)
FEEDING_CONFIGURATION_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType({'dog_count': 0, 'feeding_summary': ''}),
)
DOG_GPS_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType({'dog_name': ''}),
)
DOG_FEEDING_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dog_name': '',
            'dog_weight': '',
            'suggested_amount': '',
        }
    ),
)
DOG_HEALTH_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'dog_name': '',
            'dog_age': '',
            'dog_weight': '',
            'suggested_ideal_weight': '',
            'suggested_activity': '',
            'bcs_info': '',
            'special_diet_count': '',
            'diet_compatibility_info': '',
        }
    ),
)
MODULE_SETUP_SUMMARY_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'total_dogs': '',
            'gps_dogs': '',
            'health_dogs': '',
            'suggested_performance': '',
            'complexity_info': '',
            'next_step_info': '',
        }
    ),
)
EXTERNAL_ENTITIES_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType({'gps_enabled': False, 'visitor_enabled': False, 'dog_count': 0}),
)
REAUTH_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'integration_name': '',
            'dogs_count': '',
            'current_profile': '',
            'health_status': '',
        }
    ),
)
RECONFIGURE_FORM_PLACEHOLDERS_TEMPLATE: Final[ConfigFlowPlaceholders] = cast(
    ConfigFlowPlaceholders,
    MappingProxyType(
        {
            'current_profile': '',
            'profiles_info': '',
            'dogs_count': '',
            'compatibility_info': '',
            'estimated_entities': '',
            'error_details': '',
            'last_reconfigure': '',
            'reconfigure_requested_profile': '',
            'reconfigure_previous_profile': '',
            'reconfigure_dogs': '',
            'reconfigure_entities': '',
            'reconfigure_health': '',
            'reconfigure_warnings': '',
            'reconfigure_valid_dogs': '',
            'reconfigure_invalid_dogs': '',
            'reconfigure_merge_notes': '',
        }
    ),
)


class InputBooleanCreateServiceData(TypedDict, total=False):
    """Service payload accepted by ``input_boolean.create``."""

    name: Required[str]
    initial: NotRequired[bool]
    icon: NotRequired[str | None]


class InputDatetimeCreateServiceData(TypedDict, total=False):
    """Service payload accepted by ``input_datetime.create``."""

    name: Required[str]
    has_date: Required[bool]
    has_time: Required[bool]
    initial: NotRequired[str]


class InputNumberCreateServiceData(TypedDict, total=False):
    """Service payload accepted by ``input_number.create``."""

    name: Required[str]
    min: Required[int | float]
    max: Required[int | float]
    step: Required[int | float]
    mode: Required[str]
    initial: NotRequired[int | float]
    icon: NotRequired[str]
    unit_of_measurement: NotRequired[str]


class InputSelectCreateServiceData(TypedDict, total=False):
    """Service payload accepted by ``input_select.create``."""

    name: Required[str]
    options: Required[list[str]]
    initial: NotRequired[str]
    icon: NotRequired[str]


class HelperEntityMetadata(TypedDict, total=False):
    """Metadata captured for helpers created by the helper manager."""

    domain: str
    name: str
    icon: str | None
    initial: bool | int | float | str | None
    has_date: bool
    has_time: bool
    options: list[str]
    min: int | float
    max: int | float
    step: int | float
    mode: str
    unit_of_measurement: str | None


type HelperEntityMetadataMapping = dict[str, HelperEntityMetadata]
"""Mapping of entity identifiers to helper metadata payloads."""


type DogHelperAssignments = dict[str, list[str]]
"""Mapping of dog identifiers to the helpers provisioned for them."""


class HelperManagerStats(TypedDict):
    """Summary statistics reported by the helper manager diagnostics."""

    helpers: int
    dogs: int
    managed_entities: int


class HelperManagerSnapshot(TypedDict):
    """Snapshot payload describing managed helper assignments."""

    per_dog: dict[str, int]
    entity_domains: dict[str, int]


class HelperManagerGuardMetrics(TypedDict):
    """Aggregated guard telemetry captured by the helper manager."""

    executed: int
    skipped: int
    reasons: dict[str, int]
    last_results: ServiceGuardResultHistory


EntityFactoryGuardEvent = Literal['expand', 'contract', 'stable', 'disabled', 'unknown']
EntityFactoryGuardStabilityTrend = Literal[
    'improving',
    'steady',
    'regressing',
    'unknown',
]
"""Event labels recorded whenever the entity factory runtime guard recalibrates."""


class EntityFactoryGuardMetrics(TypedDict, total=False):
    """Runtime guard telemetry captured by the entity factory."""

    schema_version: Literal[1]
    runtime_floor: float
    baseline_floor: float
    max_floor: float
    runtime_floor_delta: float
    peak_runtime_floor: float
    lowest_runtime_floor: float
    last_floor_change: float
    last_floor_change_ratio: float
    last_actual_duration: float
    last_duration_ratio: float
    last_event: EntityFactoryGuardEvent
    last_updated: str
    samples: int
    stable_samples: int
    expansions: int
    contractions: int
    last_expansion_duration: float
    last_contraction_duration: float
    enforce_min_runtime: bool
    average_duration: float
    max_duration: float
    min_duration: float
    stable_ratio: float
    expansion_ratio: float
    contraction_ratio: float
    volatility_ratio: float
    consecutive_stable_samples: int
    longest_stable_run: int
    duration_span: float
    jitter_ratio: float
    recent_durations: list[float]
    recent_average_duration: float
    recent_max_duration: float
    recent_min_duration: float
    recent_duration_span: float
    recent_jitter_ratio: float
    recent_samples: int
    recent_events: list[EntityFactoryGuardEvent]
    recent_stable_samples: int
    recent_stable_ratio: float
    stability_trend: EntityFactoryGuardStabilityTrend


class EntityFactoryGuardMetricsSnapshot(TypedDict, total=False):
    """Normalised guard telemetry exposed via diagnostics surfaces."""

    runtime_floor_ms: float
    baseline_floor_ms: float
    max_floor_ms: float
    runtime_floor_delta_ms: float
    peak_runtime_floor_ms: float
    lowest_runtime_floor_ms: float
    last_floor_change_ms: float
    last_actual_duration_ms: float
    last_duration_ratio: float
    last_floor_change_ratio: float
    last_event: EntityFactoryGuardEvent
    last_updated: str
    samples: int
    stable_samples: int
    expansions: int
    contractions: int
    last_expansion_duration_ms: float
    last_contraction_duration_ms: float
    average_duration_ms: float
    max_duration_ms: float
    min_duration_ms: float
    duration_span_ms: float
    jitter_ratio: float
    recent_average_duration_ms: float
    recent_max_duration_ms: float
    recent_min_duration_ms: float
    recent_duration_span_ms: float
    recent_jitter_ratio: float
    stable_ratio: float
    expansion_ratio: float
    contraction_ratio: float
    volatility_ratio: float
    consecutive_stable_samples: int
    longest_stable_run: int
    recent_samples: int
    recent_events: list[EntityFactoryGuardEvent]
    recent_stable_samples: int
    recent_stable_ratio: float
    stability_trend: EntityFactoryGuardStabilityTrend


class PersonEntityConfigInput(TypedDict, total=False):
    """Configuration payload accepted by :class:`PersonEntityManager`."""

    enabled: bool
    auto_discovery: bool
    discovery_interval: int
    cache_ttl: int
    include_away_persons: bool
    fallback_to_static: bool
    static_notification_targets: list[str]
    excluded_entities: list[str]
    notification_mapping: dict[str, str]
    priority_persons: list[str]


class PersonEntityCounters(TypedDict):
    """Low-level person manager counters used for cache statistics."""

    persons_discovered: int
    notifications_targeted: int
    cache_hits: int
    cache_misses: int
    discovery_runs: int


class PersonEntityConfigStats(TypedDict):
    """Normalised configuration snapshot for the person entity manager."""

    enabled: bool
    auto_discovery: bool
    discovery_interval: int
    include_away_persons: bool
    fallback_to_static: bool


class PersonEntityStateStats(TypedDict):
    """Runtime discovery metrics surfaced by the person entity manager."""

    total_persons: int
    home_persons: int
    away_persons: int
    last_discovery: str
    uptime_seconds: float


class PersonEntityCacheStats(TypedDict):
    """Cache health metrics for person notification targeting."""

    cache_entries: int
    hit_rate: float


class PersonEntityStats(PersonEntityCounters):
    """Coordinator statistics payload exported by the person entity manager."""

    config: PersonEntityConfigStats
    current_state: PersonEntityStateStats
    cache: PersonEntityCacheStats


class PersonNotificationCacheEntry(TypedDict, total=False):
    """Snapshot of cached notification targets for a specific context."""

    targets: tuple[str, ...]
    generated_at: str | None
    age_seconds: float | None
    stale: bool


class PersonNotificationContext(TypedDict):
    """Aggregated notification context surfaced to diagnostics panels."""

    persons_home: int
    persons_away: int
    home_person_names: list[str]
    away_person_names: list[str]
    total_persons: int
    has_anyone_home: bool
    everyone_away: bool


class PersonEntityDiscoveryResult(TypedDict):
    """Discovery summary returned by ``PersonEntityManager.async_force_discovery``."""

    previous_count: int
    current_count: int
    persons_added: int
    persons_removed: int
    home_persons: int
    away_persons: int
    discovery_time: str


class PersonEntityValidationResult(TypedDict):
    """Validation payload produced by ``PersonEntityManager.async_validate_configuration``."""

    valid: bool
    issues: list[str]
    recommendations: list[str]
    persons_configured: int
    notification_targets_available: int


class QueuedNotificationPayload(TypedDict, total=False):
    """Notification entry stored in helper queues before delivery."""

    dog_id: Required[str]
    title: Required[str]
    message: Required[str]
    priority: Required[NotificationPriority]
    data: NotRequired[JSONMutableMapping]
    timestamp: Required[str]


class NotificationQueueStats(TypedDict):
    """Queue utilisation metrics for the notification manager."""

    normal_queue_size: int
    high_priority_queue_size: int
    total_queued: int
    max_queue_size: int


class PersonEntitySnapshotEntry(TypedDict, total=False):
    """Snapshot payload exported for each discovered person entity."""

    entity_id: str
    name: str
    friendly_name: str
    state: str
    is_home: bool
    last_updated: str
    mobile_device_id: str | None
    notification_service: str | None


class PersonEntityStorageEntry(PersonEntitySnapshotEntry, total=False):
    """Persistent storage payload for discovered person entities."""

    attributes: PersonEntityAttributePayload


class PersonEntitySnapshot(TypedDict):
    """Coordinator snapshot payload returned by the person entity manager."""

    persons: dict[str, PersonEntitySnapshotEntry]
    notification_context: PersonNotificationContext


class ScriptManagerDogScripts(TypedDict):
    """Snapshot of generated scripts for a single dog."""

    count: int
    scripts: list[str]


class ScriptManagerStats(TypedDict, total=False):
    """Summary metrics surfaced by the script manager cache monitor."""

    scripts: int
    dogs: int
    entry_scripts: int
    last_generated_age_seconds: int


class ScriptManagerSnapshot(TypedDict, total=False):
    """Detailed coordinator snapshot payload for the script manager."""

    created_entities: list[str]
    per_dog: dict[str, ScriptManagerDogScripts]
    entry_scripts: list[str]
    last_generated: str | None


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
    """Schedule configuration associated with the feeding telemetry."""

    meals_per_day: int
    food_type: str | None
    schedule_type: str | None


class FeedingEventRecord(TypedDict, total=False):
    """Serialized feeding event stored in manager telemetry."""

    time: Required[str]
    amount: Required[float]
    meal_type: str | None
    portion_size: float | None
    food_type: str | None
    notes: str | None
    feeder: str | None
    scheduled: Required[bool]
    skipped: Required[bool]
    with_medication: Required[bool]
    medication_name: str | None
    medication_dose: str | None
    medication_time: str | None


class FeedingMissedMeal(TypedDict):
    """Scheduled meal that was not completed within the expected window."""

    meal_type: str
    scheduled_time: str


class FeedingManagerDogSetupPayload(TypedDict, total=False):
    """Normalized dog payload consumed by ``FeedingManager.async_initialize``."""

    dog_id: Required[str]
    weight: Required[float | int | str]
    dog_name: NotRequired[str | None]
    ideal_weight: NotRequired[float | int | str | None]
    age_months: NotRequired[int | float | None]
    activity_level: NotRequired[str | None]
    health_conditions: NotRequired[Iterable[str] | None]
    weight_goal: NotRequired[str | None]
    special_diet: NotRequired[Iterable[str] | str | None]
    feeding_config: NotRequired[JSONMutableMapping | JSONMapping]
    breed: NotRequired[str | None]
    modules: NotRequired[Mapping[str, bool]]


class FeedingDailyStats(TypedDict):
    """Daily feeding counters exposed alongside the active snapshot."""

    total_fed_today: float
    meals_today: int
    remaining_calories: float | None


class FeedingEmergencyState(TypedDict, total=False):
    """State metadata tracked while emergency feeding mode is active."""

    active: Required[bool]
    status: Required[str]
    emergency_type: Required[str]
    portion_adjustment: Required[float]
    duration_days: Required[int]
    activated_at: Required[str]
    expires_at: str | None
    resolved_at: NotRequired[str]
    food_type_recommendation: str | None


type FeedingHealthStatus = Literal[
    'insufficient_data',
    'emergency',
    'underfed',
    'overfed',
    'on_track',
    'monitoring',
    'unknown',
]
"""Possible health status indicators emitted by the feeding manager."""


class FeedingHealthSummary(TypedDict, total=False):
    """Structured health context calculated for a dog's feeding plan."""

    health_aware_enabled: bool
    current_weight: float | None
    ideal_weight: float | None
    life_stage: str | None
    activity_level: str | None
    body_condition_score: float | int | None
    daily_calorie_requirement: float | None
    calories_per_gram: float
    health_conditions: list[str]
    special_diet: list[str]
    weight_goal: str | None
    diet_validation_applied: bool


class FeedingDietValidationSummary(TypedDict, total=False):
    """Summary describing diet validation adjustments and conflicts."""

    has_adjustments: bool
    adjustment_info: str
    conflict_count: int
    warning_count: int
    vet_consultation_recommended: bool
    vet_consultation_state: str
    consultation_urgency: str
    total_diets: int
    diet_validation_adjustment: float
    percentage_adjustment: float
    adjustment_direction: str
    safety_factor: str
    compatibility_score: int
    compatibility_level: str
    conflicts: NotRequired[list[JSONMapping]]
    warnings: NotRequired[list[JSONMapping]]


class FeedingSnapshot(TypedDict, total=False):
    """Primary feeding telemetry snapshot returned by the manager."""

    status: Required[Literal['ready', 'no_data']]
    last_feeding: str | None
    last_feeding_type: str | None
    last_feeding_hours: float | None
    last_feeding_amount: float | None
    feedings_today: Required[dict[str, int]]
    total_feedings_today: Required[int]
    daily_amount_consumed: Required[float]
    daily_amount_target: Required[float]
    daily_target: Required[float]
    daily_amount_percentage: Required[int]
    schedule_adherence: Required[int]
    next_feeding: str | None
    next_feeding_type: str | None
    missed_feedings: Required[list[FeedingMissedMeal]]
    feedings: Required[list[FeedingEventRecord]]
    feeding_schedule: NotRequired[list[JSONMapping]]
    daily_portions: NotRequired[int]
    daily_stats: Required[FeedingDailyStats]
    calories_per_gram: NotRequired[float]
    daily_calorie_target: NotRequired[float]
    total_calories_today: NotRequired[float]
    calorie_goal_progress: NotRequired[float]
    portion_adjustment_factor: NotRequired[float]
    diet_validation_summary: NotRequired[FeedingDietValidationSummary | None]
    health_conditions: NotRequired[list[str]]
    daily_activity_level: NotRequired[str | None]
    health_summary: NotRequired[FeedingHealthSummary]
    medication_with_meals: Required[bool]
    health_aware_feeding: Required[bool]
    weight_goal: Required[str | None]
    weight_goal_progress: NotRequired[float]
    emergency_mode: Required[FeedingEmergencyState | None]
    health_emergency: Required[bool]
    health_feeding_status: Required[FeedingHealthStatus]
    config: NotRequired[FeedingScheduleSnapshot]


class FeedingStatisticsSnapshot(TypedDict):
    """Historical feeding statistics exported by the manager."""

    period_days: int
    total_feedings: int
    average_daily_feedings: float
    average_daily_amount: float
    most_common_meal: str | None
    schedule_adherence: int
    daily_target_met_percentage: int


class FeedingModulePayload(FeedingSnapshot, total=False):
    """Typed payload exposed by the feeding coordinator module."""

    message: NotRequired[str]


class FeedingModuleTelemetry(FeedingModulePayload):
    """Extended feeding module telemetry used by diagnostics consumers."""


type FeedingSnapshotCache = dict[str, FeedingSnapshot]
"""Cache of per-dog feeding snapshots keyed by dog identifier."""


type FeedingStatisticsCache = dict[str, FeedingStatisticsSnapshot]
"""Cache of historical feeding statistics keyed by cache key."""


class GPSRoutePoint(TypedDict, total=False):
    """Individual GPS sample collected during live tracking."""

    latitude: Required[float]
    longitude: Required[float]
    timestamp: Required[datetime | str]
    accuracy: Required[float | int]
    altitude: float | None
    speed: float | None
    heading: float | None


class GPSLocationSample(TypedDict):
    """Validated GPS location sample with prioritisation metadata."""

    latitude: float
    longitude: float
    accuracy: int
    timestamp: datetime
    source: str
    priority: int
    altitude: float | None
    speed: float | None
    heading: float | None


class GPSRouteSnapshot(TypedDict, total=False):
    """Snapshot of an active or historical GPS route."""

    id: Required[str]
    name: Required[str]
    active: Required[bool]
    start_time: Required[datetime | str]
    end_time: datetime | str | None
    duration: float | int | None
    distance: float | None
    points: list[GPSRoutePoint]
    point_count: int
    last_point_time: datetime | str | None


class GPSCompletedRouteSnapshot(GPSRouteSnapshot, total=False):
    """Snapshot returned when a GPS route recording completes."""

    dog_id: Required[str]
    dog_name: Required[str]


class GeofenceZoneMetadata(TypedDict, total=False):
    """Additional attributes persisted alongside configured geofence zones."""

    auto_created: bool
    color: str | None
    created_by: str | None
    notes: str | None
    tags: list[str]


class GeofenceZoneStoragePayload(TypedDict, total=False):
    """Serialized representation of a stored :class:`GeofenceZone`."""

    id: Required[str]
    name: Required[str]
    type: Required[str]
    latitude: Required[float]
    longitude: Required[float]
    radius: Required[float]
    enabled: bool
    alerts_enabled: bool
    description: str
    created_at: str
    updated_at: str
    metadata: GeofenceZoneMetadata


class GeofenceStoragePayload(TypedDict, total=False):
    """Top-level storage payload tracked by :class:`PawControlGeofencing`."""

    zones: dict[str, GeofenceZoneStoragePayload]
    last_updated: str


class GeofenceNotificationPayload(TypedDict, total=False):
    """Notification payload emitted for geofence enter/exit events."""

    zone_id: Required[str]
    zone_name: Required[str]
    zone_type: Required[str]
    event_type: Required[str]
    radius: Required[float]
    latitude: float
    longitude: float
    distance_from_center_m: float
    accuracy: float | int | None


class GPSGeofenceLocationSnapshot(TypedDict, total=False):
    """Current GPS location exported in geofence status snapshots."""

    latitude: Required[float]
    longitude: Required[float]
    timestamp: Required[str]
    accuracy: float | int | None


class GPSGeofenceZoneStatusSnapshot(TypedDict):
    """Status details for an individual configured geofence zone."""

    inside: bool
    zone_type: str
    radius_meters: float
    distance_to_center: float
    notifications_enabled: bool


class GPSGeofenceStatusSnapshot(TypedDict):
    """Full geofence snapshot surfaced to diagnostics and dashboards."""

    dog_id: str
    zones_configured: int
    current_location: GPSGeofenceLocationSnapshot | None
    zone_status: dict[str, GPSGeofenceZoneStatusSnapshot]
    safe_zone_breaches: int
    last_update: str | None


class GPSTrackingConfigInput(TypedDict, total=False):
    """Mutable configuration payload accepted by the GPS manager."""

    enabled: bool
    auto_start_walk: bool
    track_route: bool
    safety_alerts: bool
    geofence_notifications: bool
    auto_detect_home: bool
    gps_accuracy_threshold: float | int
    update_interval_seconds: int | float
    min_distance_for_point: float | int
    route_smoothing: bool
    configured_at: datetime | str | None


class GeofenceNotificationCoordinates(TypedDict):
    """Latitude and longitude payload bundled with geofence notifications."""

    latitude: float
    longitude: float


class GeofenceEventPayload(TypedDict, total=False):
    """Event data fired on the Home Assistant event bus for geofence changes."""

    dog_id: Required[str]
    zone: Required[str]
    zone_type: Required[str]
    event: Required[str]
    distance_meters: Required[float]
    timestamp: Required[str]
    latitude: Required[float]
    longitude: Required[float]
    duration_seconds: int


class GeofenceNotificationData(TypedDict, total=False):
    """Structured data payload passed to notification templates for geofences."""

    zone: Required[str]
    zone_type: Required[str]
    event: Required[str]
    distance_meters: Required[float]
    coordinates: Required[GeofenceNotificationCoordinates]
    duration_seconds: int


class GPSTelemetryPayload(TypedDict, total=False):
    """Live GPS telemetry exposed to coordinators and diagnostics."""

    latitude: float | None
    longitude: float | None
    accuracy: float | int | None
    altitude: float | None
    speed: float | None
    heading: float | None
    source: str | None
    last_seen: datetime | str | None
    last_update: str | None
    battery: float | int | None
    zone: str | None
    satellites: int | None
    distance_from_home: float | None
    geofence_status: JSONMutableMapping | None
    walk_info: JSONMutableMapping | None
    current_route: GPSRouteSnapshot | None
    active_route: JSONMutableMapping | None


class GPSModulePayload(GPSTelemetryPayload, total=False):
    """GPS metrics surfaced through the GPS adapter."""

    status: Required[str]


class GPSManagerStats(TypedDict):
    """Counters maintained by :class:`GPSGeofenceManager` for telemetry."""

    gps_points_processed: int
    routes_completed: int
    geofence_events: int
    last_update: datetime


class GPSManagerStatisticsSnapshot(GPSManagerStats):
    """Aggregated GPS statistics exposed via coordinator diagnostics."""

    dogs_configured: int
    active_tracking_sessions: int
    total_routes_stored: int
    geofence_zones_configured: int


class GPSTrackerRouteAttributes(TypedDict, total=False):
    """Route metadata surfaced as device tracker state attributes."""

    route_active: bool
    route_points: int
    route_distance: float | None
    route_duration: float | int | None
    route_start_time: str | None


class GPSTrackerGeofenceAttributes(TypedDict, total=False):
    """Geofence attributes exposed on the GPS tracker entity."""

    in_safe_zone: bool
    zone_name: str | None
    zone_distance: float | None


class GPSTrackerWalkAttributes(TypedDict, total=False):
    """Walk linkage metadata exposed on the GPS tracker entity."""

    walk_active: bool
    walk_id: str | None
    walk_start_time: str | None


class GPSTrackerExtraAttributes(
    GPSTrackerRouteAttributes,
    GPSTrackerGeofenceAttributes,
    GPSTrackerWalkAttributes,
    total=False,
):
    """Complete set of extra attributes returned by the GPS tracker entity."""

    dog_id: Required[str]
    dog_name: Required[str]
    tracker_type: Required[str]
    altitude: float | None
    speed: float | None
    heading: float | None
    satellites: int | None
    location_source: str
    last_seen: str | None
    distance_from_home: float | None


def _normalise_route_point(point: Mapping[str, object]) -> GPSRoutePoint | None:
    """Return a JSON-safe GPS route point."""

    latitude = _coerce_float_value(point.get('latitude'))
    longitude = _coerce_float_value(point.get('longitude'))
    if latitude is None or longitude is None:
        return None

    payload: GPSRoutePoint = {
        'latitude': latitude,
        'longitude': longitude,
    }

    timestamp = _coerce_iso_timestamp(point.get('timestamp'))
    payload['timestamp'] = timestamp or dt_util.utcnow().isoformat()

    altitude = _coerce_float_value(point.get('altitude'))
    if altitude is not None:
        payload['altitude'] = altitude

    accuracy = _coerce_float_value(point.get('accuracy'))
    if accuracy is not None:
        payload['accuracy'] = accuracy

    speed = _coerce_float_value(point.get('speed'))
    if speed is not None:
        payload['speed'] = speed

    heading = _coerce_float_value(point.get('heading'))
    if heading is not None:
        payload['heading'] = heading

    return payload


def ensure_gps_route_snapshot(
    payload: Mapping[str, JSONValue] | JSONMutableMapping | None,
) -> GPSRouteSnapshot | None:
    """Normalise a route snapshot mapping into a JSON-safe structure."""

    if payload is None or not isinstance(payload, Mapping):
        return None

    base = ensure_json_mapping(payload)
    points_raw = base.get('points')
    points: list[GPSRoutePoint] = []
    if isinstance(points_raw, Sequence) and not isinstance(points_raw, (str, bytes)):
        for point in points_raw:
            if isinstance(point, Mapping):
                normalised = _normalise_route_point(point)
                if normalised is not None:
                    points.append(normalised)

    start_time = _coerce_iso_timestamp(base.get('start_time'))
    end_time = _coerce_iso_timestamp(base.get('end_time'))
    last_point_time = _coerce_iso_timestamp(base.get('last_point_time'))

    snapshot: GPSRouteSnapshot = {
        'active': bool(base.get('active', False)),
        'id': str(base.get('id') or ''),
        'name': str(base.get('name') or base.get('id') or 'GPS Route'),
        'start_time': start_time or None,
        'points': points,
        'point_count': len(points),
    }

    if end_time is not None:
        snapshot['end_time'] = end_time
    if last_point_time is not None:
        snapshot['last_point_time'] = last_point_time

    distance = _coerce_float_value(base.get('distance'))
    if distance is not None:
        snapshot['distance'] = distance

    duration = _coerce_float_value(base.get('duration'))
    if duration is not None:
        snapshot['duration'] = duration

    return snapshot


def ensure_gps_payload(
    payload: Mapping[str, object] | JSONMutableMapping | None,
) -> GPSModulePayload | None:
    """Return a normalised :class:`GPSModulePayload`."""

    if payload is None or not isinstance(payload, Mapping):
        return None

    gps_payload: GPSModulePayload = ensure_json_mapping(payload)
    if not gps_payload:
        return None
    last_seen = _coerce_iso_timestamp(gps_payload.get('last_seen'))
    if last_seen is not None or 'last_seen' in gps_payload:
        gps_payload['last_seen'] = last_seen

    last_update = _coerce_iso_timestamp(gps_payload.get('last_update'))
    if last_update is not None or 'last_update' in gps_payload:
        gps_payload['last_update'] = last_update

    for payload_field in (
        'latitude',
        'longitude',
        'accuracy',
        'altitude',
        'speed',
        'heading',
        'battery',
        'distance_from_home',
    ):
        if payload_field not in gps_payload:
            continue
        gps_payload[payload_field] = _coerce_float_value(gps_payload.get(payload_field))

    satellites = gps_payload.get('satellites')
    if satellites is None and 'satellites' in gps_payload:
        gps_payload['satellites'] = None
    elif satellites is not None:
        try:
            gps_payload['satellites'] = int(satellites)
        except (TypeError, ValueError):
            _LOGGER.warning(
                'Invalid satellites value %s for GPS payload; setting to None',
                satellites,
            )
            gps_payload['satellites'] = None

    current_route_snapshot = ensure_gps_route_snapshot(
        cast(
            Mapping[str, JSONValue] | JSONMutableMapping | None,
            payload.get('current_route'),
        )
    )
    if current_route_snapshot is not None:
        gps_payload['current_route'] = current_route_snapshot
    elif 'current_route' in gps_payload:
        gps_payload.pop('current_route', None)

    route_active_payload = payload.get('active_route')
    if isinstance(route_active_payload, Mapping):
        active_route = ensure_gps_route_snapshot(
            cast(Mapping[str, JSONValue], route_active_payload)
        )
        if active_route is not None:
            gps_payload['active_route'] = active_route

    status = payload.get('status')
    gps_payload['status'] = str(status) if status is not None else 'unknown'

    return gps_payload


class GPSRouteExportJSONPoint(TypedDict, total=False):
    """GPS point exported in JSON route downloads."""

    latitude: Required[float]
    longitude: Required[float]
    timestamp: Required[str]
    altitude: float | None
    accuracy: float | int | None
    source: str | None


class GPSRouteExportJSONEvent(TypedDict, total=False):
    """Geofence event metadata included in JSON route exports."""

    event_type: Required[str]
    zone_name: Required[str]
    timestamp: Required[str]
    distance_from_center: float | None
    severity: str | None


class GPSRouteExportJSONRoute(TypedDict, total=False):
    """Route details serialised in JSON exports."""

    start_time: Required[str]
    end_time: str | None
    duration_minutes: float | None
    distance_km: float | None
    avg_speed_kmh: float | None
    route_quality: str
    gps_points: list[GPSRouteExportJSONPoint]
    geofence_events: list[GPSRouteExportJSONEvent]


class GPSRouteExportJSONContent(TypedDict):
    """Top-level JSON payload returned when exporting GPS routes."""

    dog_id: str
    export_timestamp: str
    routes: list[GPSRouteExportJSONRoute]


class GPSRouteExportBasePayload(TypedDict):
    """Base fields shared across all GPS route export payloads."""

    filename: str
    routes_count: int


class GPSRouteExportGPXPayload(GPSRouteExportBasePayload):
    """Payload returned when exporting GPS routes in GPX format."""

    format: Literal['gpx']
    content: str


class GPSRouteExportCSVPayload(GPSRouteExportBasePayload):
    """Payload returned when exporting GPS routes in CSV format."""

    format: Literal['csv']
    content: str


class GPSRouteExportJSONPayload(GPSRouteExportBasePayload):
    """Payload returned when exporting GPS routes in JSON format."""

    format: Literal['json']
    content: GPSRouteExportJSONContent


type GPSRouteExportPayload = (
    GPSRouteExportGPXPayload | GPSRouteExportCSVPayload | GPSRouteExportJSONPayload
)


@dataclass(slots=True)
class GPSRouteBuffer[TPoint: GPSRoutePoint]:
    """Typed buffer that stores route samples for GPS tracking."""

    _points: list[TPoint] = field(default_factory=list)

    def append(self, point: TPoint) -> None:
        """Append a new GPS sample to the buffer."""

        self._points.append(point)

    def prune(self, *, cutoff: datetime, max_points: int) -> None:
        """Drop samples older than ``cutoff`` while enforcing ``max_points``."""

        filtered_points: list[TPoint] = []
        for point in self._points:
            timestamp = point.get('timestamp')
            if isinstance(timestamp, datetime) and timestamp > cutoff:
                filtered_points.append(point)

        self._points = filtered_points
        if len(self._points) > max_points:
            self._points = self._points[-max_points:]

    def snapshot(self, *, limit: int | None = None) -> list[TPoint]:
        """Return a shallow copy of the most recent samples."""

        if limit is None:
            return list(self._points)
        if limit <= 0:
            return []
        return list(self._points[-limit:])

    def view(self) -> Sequence[TPoint]:
        """Return a read-only view over the buffered route samples."""

        return self._points

    def clear(self) -> None:
        """Remove all buffered samples."""

        self._points.clear()

    def __len__(self) -> int:
        """Return the number of buffered samples."""

        return len(self._points)

    def __bool__(self) -> bool:  # pragma: no cover - delegated to __len__
        """Return ``True`` when the buffer contains samples."""

        return bool(self._points)

    def __iter__(self) -> Iterator[TPoint]:
        """Iterate over buffered samples in chronological order."""

        return iter(self._points)


class GeofencingModulePayload(TypedDict, total=False):
    """Structured geofence payload for coordinator consumers."""

    status: Required[str]
    zones_configured: int
    zone_status: dict[str, GPSGeofenceZoneStatusSnapshot]
    current_location: GPSGeofenceLocationSnapshot | None
    safe_zone_breaches: int
    last_update: str | None
    message: NotRequired[str]
    error: NotRequired[str]


class HealthModulePayload(TypedDict, total=False):
    """Combined health telemetry exposed by the health adapter."""

    status: Required[str]
    weight: float | None
    ideal_weight: float | None
    last_vet_visit: str | None
    medications: HealthMedicationQueue
    health_alerts: HealthAlertList
    life_stage: str | None
    activity_level: str | None
    body_condition_score: float | int | None
    health_conditions: list[str]
    emergency: JSONMutableMapping
    medication: JSONMutableMapping
    health_status: str | None
    daily_calorie_target: float | None
    total_calories_today: float | None
    weight_goal_progress: Any
    weight_goal: Any


class WeatherConditionsPayload(TypedDict, total=False):
    """Current weather snapshot consumed by dashboard entities."""

    temperature_c: float | None
    humidity_percent: float | None
    uv_index: float | None
    wind_speed_kmh: float | None
    condition: str | None
    last_updated: str


class WeatherAlertPayload(TypedDict, total=False):
    """Serialized weather alert returned by the adapter."""

    type: Required[str]
    severity: Required[str]
    title: Required[str]
    message: Required[str]
    recommendations: list[str]
    duration_hours: int | None
    affected_breeds: list[str]
    age_considerations: list[str]


type WeatherModuleStatus = Literal['ready', 'disabled', 'error']


class WeatherModulePayload(TypedDict, total=False):
    """Weather-driven health insights returned by the weather adapter."""

    status: Required[WeatherModuleStatus]
    health_score: float | int | None
    alerts: list[WeatherAlertPayload]
    recommendations: list[str]
    conditions: WeatherConditionsPayload
    message: NotRequired[str]


class GardenFavoriteActivity(TypedDict):
    """Tracked activity that contributes to garden statistics."""

    activity: str
    count: int


class GardenWeeklySummary(TypedDict, total=False):
    """Rolling weekly garden performance summary."""

    session_count: int
    total_time_minutes: float
    poop_events: int
    average_duration: float
    updated: str


class GardenStatsSnapshot(TypedDict, total=False):
    """Structured garden statistics payload."""

    total_sessions: int
    total_time_minutes: float
    total_poop_count: int
    average_session_duration: float
    most_active_time_of_day: str | None
    favorite_activities: list[GardenFavoriteActivity]
    weekly_summary: GardenWeeklySummary
    last_garden_visit: str | None
    total_activities: int


class GardenConfirmationSnapshot(TypedDict, total=False):
    """Metadata describing pending garden confirmations."""

    session_id: str | None
    created: str | None
    expires: str | None


class GardenWeatherSummary(TypedDict, total=False):
    """Summary of weather observations collected during garden sessions."""

    conditions: list[str]
    average_temperature: float | None


class GardenSessionSnapshot(TypedDict, total=False):
    """Serializable snapshot describing a garden session."""

    session_id: str
    start_time: str
    end_time: str | None
    duration_minutes: float
    activity_count: int
    poop_count: int
    status: str
    weather_conditions: str | None
    temperature: float | None
    notes: str | None


class GardenActiveSessionSnapshot(TypedDict, total=False):
    """Runtime view of an active garden session."""

    session_id: str
    start_time: str
    duration_minutes: float
    activity_count: int
    poop_count: int


class GardenModulePayload(TypedDict, total=False):
    """Garden telemetry surfaced to coordinators."""

    status: Required[str]
    message: NotRequired[str]
    sessions_today: int
    time_today_minutes: float
    poop_today: int
    activities_today: int
    activities_total: int
    active_session: GardenActiveSessionSnapshot | None
    last_session: GardenSessionSnapshot | None
    hours_since_last_session: float | None
    stats: GardenStatsSnapshot
    pending_confirmations: list[GardenConfirmationSnapshot]
    weather_summary: GardenWeatherSummary | None


class WalkRoutePoint(TypedDict, total=False):
    """Normalised GPS sample recorded during a walk."""

    latitude: float
    longitude: float
    timestamp: str
    accuracy: NotRequired[float | None]
    altitude: NotRequired[float | None]
    speed: NotRequired[float | None]
    heading: NotRequired[float | None]
    source: NotRequired[str | None]
    battery_level: NotRequired[int | None]
    signal_strength: NotRequired[int | None]


class GPSCacheStats(TypedDict):
    """Statistics tracked by the GPS cache for diagnostics."""

    hits: int
    misses: int
    hit_rate: float
    cached_locations: int
    distance_cache_entries: int
    evictions: int
    max_size: int


class GPSCacheDiagnosticsMetadata(TypedDict):
    """Metadata describing cache configuration and contents."""

    cached_dogs: list[str]
    max_size: int
    distance_cache_entries: int
    evictions: int


class GPSCacheSnapshot(TypedDict):
    """Combined telemetry exported by the GPS cache."""

    stats: GPSCacheStats
    metadata: GPSCacheDiagnosticsMetadata


class WalkLocationSnapshot(TypedDict, total=False):
    """Snapshot describing a recorded walk location."""

    latitude: float
    longitude: float
    timestamp: str
    accuracy: NotRequired[float | None]
    altitude: NotRequired[float | None]
    source: NotRequired[str | None]
    battery_level: NotRequired[int | None]
    signal_strength: NotRequired[int | None]


class WalkPerformanceCounters(TypedDict):
    """Performance counters captured by the walk manager."""

    gps_updates: int
    distance_calculations: int
    cache_hits: int
    cache_misses: int
    memory_cleanups: int
    gpx_exports: int
    export_errors: int


class WalkSessionSnapshot(TypedDict, total=False):
    """Structured walk session metadata used for diagnostics and history."""

    walk_id: str
    dog_id: str
    walk_type: str
    start_time: str
    walker: str | None
    leash_used: bool
    weather: str | None
    track_route: bool
    safety_alerts: bool
    start_location: WalkLocationSnapshot | None
    end_time: str | None
    duration: float | None
    distance: float | None
    end_location: WalkLocationSnapshot | None
    status: str
    average_speed: float | None
    max_speed: float | None
    calories_burned: float | None
    elevation_gain: float | None
    path: list[WalkRoutePoint]
    notes: str | None
    dog_weight_kg: float | None
    detection_confidence: float | None
    door_sensor: str | None
    detection_metadata: JSONMutableMapping | None
    save_route: bool | None
    path_optimization_applied: bool | None
    current_distance: float | None
    current_duration: float | None
    elapsed_duration: NotRequired[float]


class WalkStatisticsSnapshot(TypedDict, total=False):
    """Aggregated walk statistics tracked per dog."""

    status: str
    message: str
    walks_today: Required[int]
    total_duration_today: Required[float]
    total_distance_today: Required[float]
    last_walk: str | None
    last_walk_duration: float | None
    last_walk_distance: float | None
    average_duration: float | None
    average_distance: float | None
    weekly_walks: Required[int]
    weekly_distance: Required[float]
    needs_walk: Required[bool]
    walk_streak: Required[int]
    energy_level: Required[str]
    walk_in_progress: bool
    current_walk: WalkSessionSnapshot | None


class WalkModulePayload(WalkStatisticsSnapshot, total=False):
    """Telemetry returned by the walk adapter."""

    daily_walks: NotRequired[int]
    total_distance: NotRequired[float]


class WalkModuleTelemetry(WalkModulePayload, total=False):
    """Extended walk telemetry with historical and lifetime statistics."""

    total_distance_lifetime: NotRequired[float]
    total_walks_lifetime: NotRequired[int]
    distance_this_week: NotRequired[float]
    distance_this_month: NotRequired[float]
    total_duration_this_week: NotRequired[float]
    walks_this_week: NotRequired[int]
    walks_history: NotRequired[list[WalkSessionSnapshot]]
    daily_walk_counts: NotRequired[dict[str, int]]
    weekly_walk_target: NotRequired[int]
    walks_yesterday: NotRequired[int]


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
    """Latest GPS status exported by the walk manager."""

    latitude: float | None
    longitude: float | None
    accuracy: float | None
    altitude: float | None
    speed: float | None
    heading: float | None
    last_seen: str | None
    source: str | None
    available: Required[bool]
    zone: Required[str]
    distance_from_home: float | None
    signal_strength: int | None
    battery_level: int | None
    accuracy_threshold: float | None
    update_interval: float | int | None
    automatic_config: JSONMutableMapping | None
    error: str


class WalkRouteBounds(TypedDict):
    """Bounding box describing the extents of exported walk routes."""

    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class WalkDailyStatistics(TypedDict):
    """Aggregated walk statistics for the active day."""

    total_walks_today: int
    total_duration_today: float
    total_distance_today: float
    average_duration: float | None
    average_distance: float | None
    energy_level: str


class WalkWeeklyStatistics(TypedDict):
    """Aggregated walk statistics for the active week."""

    total_walks_this_week: int
    total_distance_this_week: float
    walk_streak: int


type WalkRouteExportFormat = Literal['gpx', 'json', 'csv']
"""Supported export formats for walk routes."""


type WalkDetectionMetadata = Mapping[str, JSONValue]
"""Immutable walk detection metadata forwarded by auto-detection sources."""

type WalkDetectionMutableMetadata = dict[str, JSONValue]
"""Mutable walk detection metadata payload stored during active sessions."""


class WalkRouteExportMetadata(TypedDict):
    """Metadata describing the exported walk routes."""

    creator: str
    version: str
    generated_by: str
    bounds: WalkRouteBounds


class WalkRouteExportPayload(TypedDict, total=False):
    """Serialized walk route export payload returned to callers."""

    dog_id: str
    export_timestamp: str
    format: WalkRouteExportFormat
    walks_count: int
    total_distance_meters: float
    total_duration_seconds: float
    total_gps_points: int
    walks: list[WalkSessionSnapshot]
    export_metadata: WalkRouteExportMetadata
    file_extension: NotRequired[str]
    mime_type: NotRequired[str]
    gpx_data: NotRequired[str]
    json_data: NotRequired[str]
    csv_data: NotRequired[str]


class WalkManagerDogSnapshot(TypedDict):
    """Composite snapshot exposed to diagnostics for each dog."""

    active_walk: WalkSessionSnapshot | None
    history: list[WalkSessionSnapshot]
    stats: WalkStatisticsSnapshot
    gps: WalkGPSSnapshot


class WalkOverviewSnapshot(WalkManagerDogSnapshot, total=False):
    """Composite snapshot returned by :func:`WalkManager.get_walk_data`."""

    statistics: Required[WalkStatisticsSnapshot]


class WalkPerformanceSnapshot(TypedDict):
    """Structured snapshot of walk manager performance telemetry."""

    total_dogs: int
    dogs_with_gps: int
    active_walks: int
    total_walks_today: int
    total_distance_today: float
    walk_detection_enabled: bool
    performance_metrics: WalkPerformanceCounters
    cache_stats: GPSCacheStats
    statistics_cache_entries: int
    location_analysis_queue_size: int
    average_path_length: float


@dataclass(slots=True)
class ModuleCacheMetrics:
    """Cache metrics exposed by coordinator module adapters."""

    entries: int = 0
    hits: int = 0
    misses: int = 0

    @property
    def hit_rate(self) -> float:
        """Return the cache hit rate as a percentage."""

        total = self.hits + self.misses
        if total <= 0:
            return 0.0
        return (self.hits / total) * 100.0


@dataclass(slots=True)
class CoordinatorModuleTask:
    """Wrapper describing a coroutine used to fetch module payloads."""

    module: CoordinatorTypedModuleName
    coroutine: Awaitable[ModuleAdapterPayload]


@dataclass(slots=True)
class CoordinatorRuntimeManagers:
    """Typed container describing runtime manager dependencies."""

    data_manager: PawControlDataManager | None = None
    feeding_manager: FeedingManager | None = None
    walk_manager: WalkManager | None = None
    notification_manager: PawControlNotificationManager | None = None
    gps_geofence_manager: GPSGeofenceManager | None = None
    geofencing_manager: PawControlGeofencing | None = None
    weather_health_manager: WeatherHealthManager | None = None
    garden_manager: GardenManager | None = None

    @classmethod
    def attribute_names(cls) -> tuple[str, ...]:
        """Return the coordinator attribute names mirrored by this container."""

        return (
            'data_manager',
            'feeding_manager',
            'garden_manager',
            'geofencing_manager',
            'gps_geofence_manager',
            'notification_manager',
            'walk_manager',
            'weather_health_manager',
        )


class CacheDiagnosticsMetadata(TypedDict, total=False):
    """Metadata surfaced by cache diagnostics providers."""

    cleanup_invocations: int
    last_cleanup: datetime | str | None
    last_override_ttl: int | float | None
    last_expired_count: int
    expired_entries: int
    expired_via_override: int
    pending_expired_entries: int
    pending_override_candidates: int
    active_override_flags: int
    active_override_entries: int
    tracked_entries: int
    per_module: JSONMutableMapping
    per_dog: JSONMutableMapping
    entry_scripts: list[str]
    per_dog_helpers: dict[str, int]
    entity_domains: dict[str, int]
    errors: list[str]
    summary: JSONMutableMapping
    snapshots: list[JSONMutableMapping]
    created_entities: list[str]
    detection_stats: JSONMutableMapping
    cleanup_task_active: bool
    cleanup_listeners: int
    daily_reset_configured: bool
    namespace: str
    storage_path: str
    timestamp_anomalies: dict[str, str]
    last_generated: str | None
    manager_last_generated_age_seconds: int | float
    manager_last_activity: str | None
    manager_last_activity_age_seconds: int | float
    service_guard_metrics: HelperManagerGuardMetrics


class PersonEntityDiagnostics(CacheDiagnosticsMetadata, total=False):
    """Diagnostics payload enriched with person manager cache metadata."""

    cache_entries: dict[str, PersonNotificationCacheEntry]
    discovery_task_state: Literal['not_started', 'running', 'completed', 'cancelled']
    listener_count: int


class CacheDiagnosticsPayload(TypedDict, total=False):
    """Structured mapping exported by :class:`CacheDiagnosticsSnapshot`."""

    stats: JSONMutableMapping
    diagnostics: CacheDiagnosticsMetadata
    snapshot: JSONMutableMapping
    error: str
    repair_summary: JSONMutableMapping


@dataclass(slots=True)
class CacheDiagnosticsSnapshot(Mapping[str, JSONValue]):
    """Structured diagnostics snapshot returned by cache monitors."""

    stats: JSONLikeMapping | None = None
    diagnostics: CacheDiagnosticsMetadata | None = None
    snapshot: JSONLikeMapping | None = None
    error: str | None = None
    repair_summary: CacheRepairAggregate | None = None

    def to_mapping(self) -> JSONMutableMapping:
        """Return a mapping representation for downstream consumers."""

        payload: JSONMutableMapping = {}
        if self.stats is not None:
            payload['stats'] = cast(JSONValue, dict(self.stats))
        if self.diagnostics is not None:
            payload['diagnostics'] = cast(JSONValue, dict(self.diagnostics))
        if self.snapshot is not None:
            payload['snapshot'] = cast(JSONValue, dict(self.snapshot))
        if self.error is not None:
            payload['error'] = self.error
        if isinstance(self.repair_summary, CacheRepairAggregate):
            payload['repair_summary'] = cast(
                JSONValue, self.repair_summary.to_mapping()
            )
        return payload

    @classmethod
    def from_mapping(cls, payload: JSONMapping) -> CacheDiagnosticsSnapshot:
        """Create a snapshot payload from an arbitrary mapping."""

        stats = payload.get('stats')
        diagnostics = payload.get('diagnostics')
        snapshot = payload.get('snapshot')
        error = payload.get('error')
        repair_summary_payload = payload.get('repair_summary')

        repair_summary: CacheRepairAggregate | None
        if isinstance(repair_summary_payload, CacheRepairAggregate):
            repair_summary = repair_summary_payload
        elif isinstance(repair_summary_payload, Mapping):
            try:
                repair_summary = CacheRepairAggregate.from_mapping(
                    repair_summary_payload
                )
            except Exception:  # pragma: no cover - defensive fallback
                repair_summary = None
        else:
            repair_summary = None

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
            error=cast(str | None, error if isinstance(error, str) else None),
            repair_summary=repair_summary,
        )

    def __getitem__(self, key: str) -> JSONValue:
        """Return the value associated with ``key`` from the mapping view."""
        return self.to_mapping()[key]

    def __iter__(self) -> Iterator[str]:
        """Yield cache diagnostic mapping keys in iteration order."""
        return iter(self.to_mapping())

    def __len__(self) -> int:
        """Return the number of items exposed by the mapping view."""
        return len(self.to_mapping())


CacheDiagnosticsMap = dict[str, CacheDiagnosticsSnapshot]
"""Mapping from cache identifiers to diagnostics snapshots."""


class DataStatisticsPayload(TypedDict):
    """Diagnostics payload returned by data statistics collectors."""

    data_manager_available: bool
    metrics: JSONMutableMapping


class RecentErrorEntry(TypedDict):
    """Placeholder entry returned when detailed error history is unavailable."""

    note: str
    suggestion: str
    entry_id: str


class DebugInformationPayload(TypedDict):
    """Static debug metadata exported by diagnostics handlers."""

    debug_logging_enabled: bool
    integration_version: str
    quality_scale: str
    supported_features: list[str]
    documentation_url: str
    issue_tracker: str
    entry_id: str
    ha_version: str


class ModuleUsageBreakdown(TypedDict):
    """Aggregated module usage counters used in diagnostics exports."""

    counts: dict[str, int]
    percentages: dict[str, float]
    most_used_module: str | None
    least_used_module: str | None


class CacheRepairIssue(TypedDict, total=False):
    """Per-cache anomaly metadata forwarded to Home Assistant repairs."""

    cache: Required[str]
    entries: NotRequired[int]
    hits: NotRequired[int]
    misses: NotRequired[int]
    hit_rate: NotRequired[float]
    expired_entries: NotRequired[int]
    expired_via_override: NotRequired[int]
    pending_expired_entries: NotRequired[int]
    pending_override_candidates: NotRequired[int]
    active_override_flags: NotRequired[int]
    errors: NotRequired[list[str]]
    timestamp_anomalies: NotRequired[dict[str, str]]


@dataclass(slots=True)
class CacheRepairTotals:
    """Summarised cache counters shared across diagnostics and repairs."""

    entries: int = 0
    hits: int = 0
    misses: int = 0
    expired_entries: int = 0
    expired_via_override: int = 0
    pending_expired_entries: int = 0
    pending_override_candidates: int = 0
    active_override_flags: int = 0
    overall_hit_rate: float | None = None

    def as_dict(self) -> dict[str, int | float]:
        """Return a JSON-serialisable view of the totals."""

        payload: dict[str, int | float] = {
            'entries': self.entries,
            'hits': self.hits,
            'misses': self.misses,
            'expired_entries': self.expired_entries,
            'expired_via_override': self.expired_via_override,
            'pending_expired_entries': self.pending_expired_entries,
            'pending_override_candidates': self.pending_override_candidates,
            'active_override_flags': self.active_override_flags,
        }
        if self.overall_hit_rate is not None:
            payload['overall_hit_rate'] = round(self.overall_hit_rate, 2)
        return payload


@dataclass(slots=True)
class CacheRepairAggregate(Mapping[str, JSONValue]):
    """Aggregated cache health metrics surfaced through repairs issues."""

    total_caches: int
    anomaly_count: int
    severity: str
    generated_at: str
    caches_with_errors: list[str] | None = None
    caches_with_expired_entries: list[str] | None = None
    caches_with_pending_expired_entries: list[str] | None = None
    caches_with_override_flags: list[str] | None = None
    caches_with_low_hit_rate: list[str] | None = None
    totals: CacheRepairTotals | None = None
    issues: list[CacheRepairIssue] | None = None

    def to_mapping(self) -> JSONMutableMapping:
        """Return a mapping representation for Home Assistant repairs."""

        payload: JSONMutableMapping = {
            'total_caches': self.total_caches,
            'anomaly_count': self.anomaly_count,
            'severity': self.severity,
            'generated_at': self.generated_at,
        }
        if self.caches_with_errors:
            payload['caches_with_errors'] = list(self.caches_with_errors)
        if self.caches_with_expired_entries:
            payload['caches_with_expired_entries'] = list(
                self.caches_with_expired_entries
            )
        if self.caches_with_pending_expired_entries:
            payload['caches_with_pending_expired_entries'] = list(
                self.caches_with_pending_expired_entries
            )
        if self.caches_with_override_flags:
            payload['caches_with_override_flags'] = list(
                self.caches_with_override_flags
            )
        if self.caches_with_low_hit_rate:
            payload['caches_with_low_hit_rate'] = list(self.caches_with_low_hit_rate)
        if self.totals is not None:
            payload['totals'] = self.totals.as_dict()
        if self.issues:
            payload['issues'] = [
                cast(JSONMutableMapping, dict(issue)) for issue in self.issues
            ]
        return payload

    @classmethod
    def from_mapping(cls, payload: JSONMapping) -> CacheRepairAggregate:
        """Return a :class:`CacheRepairAggregate` constructed from a mapping."""

        def _coerce_int(value: JSONValue | object) -> int:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                try:
                    return int(float(value))
                except ValueError:
                    return 0
            return 0

        totals_payload = payload.get('totals')
        totals = None
        if isinstance(totals_payload, Mapping):
            overall_hit_rate_value = totals_payload.get('overall_hit_rate')
            overall_hit_rate: float | None
            if isinstance(overall_hit_rate_value, int | float):
                overall_hit_rate = float(overall_hit_rate_value)
            elif isinstance(overall_hit_rate_value, str):
                try:
                    overall_hit_rate = float(overall_hit_rate_value)
                except ValueError:
                    overall_hit_rate = None
            else:
                overall_hit_rate = None

            totals = CacheRepairTotals(
                entries=_coerce_int(totals_payload.get('entries')),
                hits=_coerce_int(totals_payload.get('hits')),
                misses=_coerce_int(totals_payload.get('misses')),
                expired_entries=_coerce_int(totals_payload.get('expired_entries')),
                expired_via_override=_coerce_int(
                    totals_payload.get('expired_via_override')
                ),
                pending_expired_entries=_coerce_int(
                    totals_payload.get('pending_expired_entries')
                ),
                pending_override_candidates=_coerce_int(
                    totals_payload.get('pending_override_candidates')
                ),
                active_override_flags=_coerce_int(
                    totals_payload.get('active_override_flags')
                ),
                overall_hit_rate=overall_hit_rate,
            )

        def _string_list(field: str) -> list[str] | None:
            value = payload.get(field)
            if isinstance(value, list):
                return [str(item) for item in value if isinstance(item, str)]
            if isinstance(value, tuple | set | frozenset):
                return [str(item) for item in value if isinstance(item, str)]
            return None

        issues_payload = payload.get('issues')
        issues: list[CacheRepairIssue] | None = None
        if isinstance(issues_payload, list):
            filtered = [
                cast(CacheRepairIssue, dict(issue))
                for issue in issues_payload
                if isinstance(issue, Mapping)
            ]
            if filtered:
                issues = filtered

        return cls(
            total_caches=_coerce_int(payload.get('total_caches')),
            anomaly_count=_coerce_int(payload.get('anomaly_count')),
            severity=str(payload.get('severity', 'unknown')),
            generated_at=str(payload.get('generated_at', '')),
            caches_with_errors=_string_list('caches_with_errors'),
            caches_with_expired_entries=_string_list('caches_with_expired_entries'),
            caches_with_pending_expired_entries=_string_list(
                'caches_with_pending_expired_entries'
            ),
            caches_with_override_flags=_string_list('caches_with_override_flags'),
            caches_with_low_hit_rate=_string_list('caches_with_low_hit_rate'),
            totals=totals,
            issues=issues,
        )

    def __getitem__(self, key: str) -> JSONValue:
        """Return the value associated with ``key`` from the mapping view."""
        return self.to_mapping()[key]

    def __iter__(self) -> Iterator[str]:
        """Yield cache repair aggregate keys in iteration order."""
        return iter(self.to_mapping())

    def __len__(self) -> int:
        """Return the number of items exposed by the mapping view."""
        return len(self.to_mapping())


class CacheDiagnosticsCapture(TypedDict, total=False):
    """Snapshot captured by services during maintenance routines."""

    snapshots: Required[CacheDiagnosticsMap]
    repair_summary: NotRequired[CacheRepairAggregate]


class MaintenanceExecutionDiagnostics(TypedDict, total=False):
    """Diagnostics metadata captured by maintenance utilities."""

    cache: NotRequired[CacheDiagnosticsCapture]
    metadata: NotRequired[MaintenanceMetadataPayload]


class MaintenanceExecutionResult(TypedDict, total=False):
    """Structured payload appended after running maintenance utilities."""

    task: Required[str]
    status: Required[Literal['success', 'error']]
    recorded_at: Required[str]
    message: NotRequired[str]
    diagnostics: NotRequired[MaintenanceExecutionDiagnostics]
    details: NotRequired[MaintenanceMetadataPayload]


class ServiceExecutionDiagnostics(TypedDict, total=False):
    """Diagnostics metadata captured while executing a service handler."""

    cache: NotRequired[CacheDiagnosticsCapture]
    metadata: NotRequired[MaintenanceMetadataPayload]
    guard: NotRequired[ServiceGuardSummary]
    resilience_summary: NotRequired[CoordinatorResilienceSummary]
    rejection_metrics: NotRequired[CoordinatorRejectionMetrics]


class ServiceExecutionResult(TypedDict, total=False):
    """Structured payload appended to runtime stats after service execution."""

    service: Required[str]
    status: Required[Literal['success', 'error']]
    dog_id: NotRequired[str]
    message: NotRequired[str]
    diagnostics: NotRequired[ServiceExecutionDiagnostics]
    details: NotRequired[ServiceDetailsPayload]
    guard: NotRequired[ServiceGuardSummary]


class ServiceCallLatencyTelemetry(TypedDict, total=False):
    """Latency summary for Home Assistant service calls."""

    samples: int
    average_ms: float
    minimum_ms: float
    maximum_ms: float
    last_ms: float


class ServiceCallTelemetryEntry(TypedDict, total=False):
    """Aggregated telemetry for a subset of service calls."""

    total_calls: int
    success_calls: int
    error_calls: int
    error_rate: float
    latency_ms: ServiceCallLatencyTelemetry


class ServiceCallTelemetry(ServiceCallTelemetryEntry, total=False):
    """Aggregated telemetry for all service calls, grouped by service."""

    per_service: dict[str, ServiceCallTelemetryEntry]


ManualResiliencePreferenceKey = Literal[
    'manual_check_event',
    'manual_guard_event',
    'manual_breaker_event',
]


class ManualResilienceEventSource(TypedDict, total=False):
    """Metadata describing a tracked manual resilience escalation event."""

    preference_key: ManualResiliencePreferenceKey
    configured_role: Literal['check', 'guard', 'breaker']
    listener_sources: tuple[str, ...]
    source_tags: list[str]
    primary_source: str


class ManualResilienceEventRecord(TypedDict, total=False):
    """Captured metadata for a manual resilience event before serialisation."""

    event_type: str
    preference_key: ManualResiliencePreferenceKey | None
    configured_role: Literal['check', 'guard', 'breaker'] | None
    time_fired: datetime | None
    received_at: datetime | None
    context_id: str | None
    user_id: str | None
    origin: str | None
    data: JSONMutableMapping | None
    sources: Sequence[str]
    source_tags: list[str]
    primary_source: str
    reasons: list[str]
    recorded_at: datetime | None
    recorded_age_seconds: int | None


class ManualResilienceEventSnapshot(TypedDict, total=False):
    """Serialised telemetry for the last manual resilience trigger."""

    event_type: str | None
    category: Literal['check', 'guard', 'breaker', 'unknown']
    matched_preference: ManualResiliencePreferenceKey | None
    time_fired: str | None
    time_fired_age_seconds: int | None
    received_at: str | None
    received_age_seconds: int | None
    recorded_at: str | None
    recorded_age_seconds: int | None
    origin: str | None
    context_id: str | None
    user_id: str | None
    data: JSONMutableMapping | None
    sources: list[str] | None
    reasons: list[str]


class ResilienceEscalationFieldEntry(TypedDict, total=False):
    """Active and default field values for resilience escalation scripts."""

    default: JSONValue | None
    active: JSONValue | None


class ResilienceEscalationFollowupEntry(ResilienceEscalationFieldEntry, total=False):
    """Follow-up script metadata with configuration state."""

    configured: bool


type ResilienceEscalationThresholds = dict[str, ResilienceEscalationFieldEntry]
"""Mapping of resilience escalation thresholds keyed by identifier."""


type ResilienceEscalationFields = dict[str, ResilienceEscalationFieldEntry]
"""Mapping of resilience escalation field defaults keyed by field name."""


class ResilienceEscalationSnapshot(TypedDict, total=False):
    """Snapshot describing the resilience escalation helper state."""

    available: bool
    state_available: bool
    entity_id: str | None
    object_id: str | None
    alias: str | None
    description: str | None
    last_generated: str | None
    last_generated_age_seconds: int | None
    last_generated_status: str | None
    last_triggered: str | None
    last_triggered_age_seconds: int | None
    thresholds: ResilienceEscalationThresholds
    fields: ResilienceEscalationFields
    followup_script: ResilienceEscalationFollowupEntry
    statistics_entity_id: ResilienceEscalationFieldEntry
    escalation_service: ResilienceEscalationFieldEntry
    manual_events: JSONMutableMapping


class ManualResilienceAutomationEntry(TypedDict, total=False):
    """Metadata describing automation listeners for manual resilience events."""

    config_entry_id: str | None
    title: str | None
    manual_guard_event: str | None
    manual_breaker_event: str | None
    manual_check_event: str | None
    configured_guard: bool
    configured_breaker: bool
    configured_check: bool


class ManualResilienceListenerMetadata(TypedDict, total=False):
    """Aggregated listener metadata for manual resilience events."""

    sources: list[str]
    source_tags: list[str]
    primary_source: str | None


class ManualResilienceEventCounters(TypedDict):
    """Aggregated counters for manual resilience event activity."""

    total: int
    by_event: dict[str, int]
    by_reason: dict[str, int]


class ManualResilienceEventsTelemetry(TypedDict, total=False):
    """Telemetry payload embedded in resilience diagnostics snapshots."""

    available: Required[bool]
    automations: list[ManualResilienceAutomationEntry]
    configured_guard_events: list[str]
    configured_breaker_events: list[str]
    configured_check_events: list[str]
    system_guard_event: str | None
    system_breaker_event: str | None
    listener_events: dict[str, list[str]]
    listener_sources: dict[str, list[str]]
    listener_metadata: dict[str, ManualResilienceListenerMetadata]
    preferred_events: dict[ManualResiliencePreferenceKey, str | None]
    preferred_guard_event: str | None
    preferred_breaker_event: str | None
    preferred_check_event: str | None
    active_listeners: list[str]
    last_event: Required[ManualResilienceEventSnapshot | None]
    last_trigger: ManualResilienceEventSnapshot | None
    event_history: Required[list[ManualResilienceEventSnapshot]]
    event_counters: ManualResilienceEventCounters


class ManualResilienceSystemSettingsSnapshot(TypedDict, total=False):
    """Normalised resilience system settings derived from config entry options."""

    manual_check_event: str | None
    manual_guard_event: str | None
    manual_breaker_event: str | None
    resilience_skip_threshold: int
    resilience_breaker_threshold: int


class ManualResilienceOptionsSnapshot(TypedDict, total=False):
    """Normalised config-entry options impacting manual resilience behaviour."""

    manual_check_event: str | None
    manual_guard_event: str | None
    manual_breaker_event: str | None
    resilience_skip_threshold: int
    resilience_breaker_threshold: int
    manual_event_history_size: int
    system_settings: ManualResilienceSystemSettingsSnapshot


type ManualResilienceEventSelection = dict[ManualResiliencePreferenceKey, str | None]
"""Preferred manual resilience events pushed to automation blueprints."""


class ServiceContextMetadata(TypedDict, total=False):
    """Service context identifiers captured for telemetry."""

    context_id: str | None
    parent_id: str | None
    user_id: str | None


class FeedingComplianceEventPayload(TypedDict, total=False):
    """Structured event payload emitted after running feeding compliance checks."""

    dog_id: str
    dog_name: str | None
    days_to_check: int
    notify_on_issues: bool
    notification_sent: bool
    result: FeedingComplianceResult
    notification_id: NotRequired[str]
    context_id: NotRequired[str]
    parent_id: NotRequired[str]
    user_id: NotRequired[str | None]
    localized_summary: NotRequired[FeedingComplianceLocalizedSummary]


type FeedingComplianceDisplayMapping = Mapping[str, object]
"""Mapping-compatible compliance payload accepted by translation helpers."""


class FeedingComplianceLocalizedSummary(TypedDict):
    """Localised representation of a feeding compliance result."""

    title: str
    message: str | None
    score_line: str | None
    missed_meals: list[str]
    issues: list[str]
    recommendations: list[str]


class CoordinatorRepairsSummary(TypedDict, total=False):
    """Condensed repairs telemetry surfaced alongside coordinator statistics."""

    severity: str
    anomaly_count: int
    total_caches: int
    generated_at: str
    issues: int
    caches_with_errors: NotRequired[int]
    caches_with_expired_entries: NotRequired[int]
    caches_with_pending_expired_entries: NotRequired[int]
    caches_with_override_flags: NotRequired[int]
    caches_with_low_hit_rate: NotRequired[int]


class CoordinatorUpdateCounts(TypedDict):
    """Aggregated update counters exposed by coordinator diagnostics."""

    total: int
    successful: int
    failed: int


class CoordinatorPerformanceMetrics(TypedDict):
    """Performance metrics captured for coordinator statistics panels."""

    success_rate: float
    cache_entries: int
    cache_hit_rate: float
    consecutive_errors: int
    last_update: Any
    update_interval: float
    api_calls: int
    rejected_call_count: NotRequired[int]
    rejection_breaker_count: NotRequired[int]
    rejection_rate: NotRequired[float | None]
    last_rejection_time: NotRequired[float | None]
    last_rejection_breaker_id: NotRequired[str | None]
    last_rejection_breaker_name: NotRequired[str | None]
    open_breaker_count: NotRequired[int]
    half_open_breaker_count: NotRequired[int]
    unknown_breaker_count: NotRequired[int]
    open_breakers: NotRequired[list[str]]
    open_breaker_ids: NotRequired[list[str]]
    half_open_breakers: NotRequired[list[str]]
    half_open_breaker_ids: NotRequired[list[str]]
    unknown_breakers: NotRequired[list[str]]
    unknown_breaker_ids: NotRequired[list[str]]
    rejection_breaker_ids: NotRequired[list[str]]
    rejection_breakers: NotRequired[list[str]]


class CoordinatorHealthIndicators(TypedDict, total=False):
    """Health indicator flags surfaced alongside coordinator statistics."""

    consecutive_errors: int
    stability_window_ok: bool


class EntityBudgetSummary(TypedDict):
    """Aggregate entity budget metrics exposed via diagnostics."""

    active_dogs: int
    total_capacity: int
    total_allocated: int
    total_remaining: int
    average_utilization: float
    peak_utilization: float
    denied_requests: int


class AdaptivePollingDiagnostics(TypedDict):
    """Runtime diagnostics captured from the adaptive polling controller."""

    target_cycle_ms: float
    current_interval_ms: float
    average_cycle_ms: float
    history_samples: int
    error_streak: int
    entity_saturation: float
    idle_interval_ms: float
    idle_grace_ms: float


class SetupFlagPanelEntry(TypedDict):
    """Single setup flag entry used by the diagnostics panel."""

    key: str
    label: str
    label_default: str
    label_translation_key: str
    enabled: bool
    source: str
    source_label: str
    source_label_default: str
    source_label_translation_key: str


type SetupFlagSourceBreakdown = dict[str, int]
"""Aggregated setup-flag counts keyed by their source identifier."""


type SetupFlagSourceLabels = dict[str, str]
"""Mapping of setup-flag sources to the human-readable label."""


class SetupFlagsPanelPayload(TypedDict):
    """Structured payload rendered by the setup flag diagnostics panel."""

    title: str
    title_translation_key: str
    title_default: str
    description: str
    description_translation_key: str
    description_default: str
    flags: list[SetupFlagPanelEntry]
    enabled_count: int
    disabled_count: int
    source_breakdown: SetupFlagSourceBreakdown
    source_labels: SetupFlagSourceLabels
    source_labels_default: SetupFlagSourceLabels
    source_label_translation_keys: SetupFlagSourceLabels
    language: str


class CoordinatorRuntimeCycleSnapshot(TypedDict):
    """Snapshot exported for a single coordinator update cycle."""

    dog_count: int
    errors: int
    success_rate: float
    duration_ms: float
    next_interval_s: float
    error_ratio: float
    success: bool


class PerformanceMonitorCountersSnapshot(TypedDict):
    """Rolling counters surfaced by the performance monitor."""

    operations: int
    errors: int
    cache_hits: int
    cache_misses: int
    avg_operation_time: float
    last_cleanup: str | None


class PerformanceMonitorSnapshot(PerformanceMonitorCountersSnapshot):
    """Derived metrics exposed by the performance monitor."""

    cache_hit_rate: float
    error_rate: float
    recent_operations: int


class OptimizedEntityMemoryConfig(TypedDict):
    """Memory optimisation tuning options for optimized entity caches."""

    max_cache_entries: int
    cache_cleanup_threshold: float
    weak_ref_cleanup_interval: int
    performance_sample_size: int


class OptimizedEntityCacheStats(TypedDict):
    """Cache statistics aggregated across optimized entities."""

    state_cache_size: int
    attributes_cache_size: int
    availability_cache_size: int


class OptimizedEntityGlobalPerformanceStats(TypedDict):
    """Global performance snapshot returned by :func:`get_global_performance_stats`."""

    total_entities_registered: int
    active_entities: int
    cache_statistics: OptimizedEntityCacheStats
    average_operation_time_ms: float
    average_cache_hit_rate: float
    total_errors: int
    entities_with_performance_data: int


class OptimizedEntityPerformanceSummary(TypedDict, total=False):
    """Per-entity performance metrics recorded by :class:`PerformanceTracker`."""

    status: str
    avg_operation_time: float
    min_operation_time: float
    max_operation_time: float
    total_operations: int
    error_count: int
    error_rate: float
    cache_hit_rate: float
    total_cache_operations: int


class OptimizedEntityMemoryEstimate(TypedDict):
    """Approximate memory usage reported by optimized entities."""

    base_entity_bytes: int
    cache_contribution_bytes: int
    estimated_total_bytes: int


class OptimizedEntityPerformanceMetrics(TypedDict):
    """Composite telemetry returned by :meth:`OptimizedEntityBase.get_performance_metrics`."""

    entity_id: str
    dog_id: str
    entity_type: str
    initialization_time: str
    uptime_seconds: float
    performance: OptimizedEntityPerformanceSummary
    memory_usage_estimate: OptimizedEntityMemoryEstimate


class WebhookSecurityStatus(TypedDict, total=False):
    """Webhook security posture exported via coordinator diagnostics."""

    configured: bool
    secure: bool
    hmac_ready: bool
    insecure_configs: tuple[str, ...]
    error: NotRequired[str]


class CoordinatorPerformanceSnapshotCounts(TypedDict):
    """Update counter payload surfaced via performance diagnostics."""

    total: int
    successful: int
    failed: int


class CoordinatorPerformanceSnapshotMetrics(TypedDict, total=False):
    """Performance telemetry attached to coordinator diagnostics snapshots."""

    last_update: str | None
    last_update_success: bool
    success_rate: float
    consecutive_errors: int
    update_interval_s: float
    current_cycle_ms: float | None
    rejected_call_count: int
    rejection_breaker_count: int
    rejection_rate: float | None
    last_rejection_time: float | None
    last_rejection_breaker_id: str | None
    last_rejection_breaker_name: str | None
    open_breaker_count: int
    half_open_breaker_count: int
    unknown_breaker_count: int
    open_breakers: list[str]
    open_breaker_ids: list[str]
    half_open_breakers: list[str]
    half_open_breaker_ids: list[str]
    unknown_breakers: list[str]
    unknown_breaker_ids: list[str]
    rejection_breaker_ids: list[str]
    rejection_breakers: list[str]


class CoordinatorPerformanceSnapshot(TypedDict, total=False):
    """Composite payload returned by performance snapshot helpers."""

    update_counts: CoordinatorPerformanceSnapshotCounts
    performance_metrics: CoordinatorPerformanceSnapshotMetrics
    adaptive_polling: AdaptivePollingDiagnostics
    entity_budget: EntityBudgetSummary
    webhook_security: WebhookSecurityStatus
    resilience_summary: CoordinatorResilienceSummary
    rejection_metrics: CoordinatorRejectionMetrics
    bool_coercion: BoolCoercionSummary
    resilience: CoordinatorResilienceDiagnostics
    service_execution: CoordinatorServiceExecutionSummary
    last_cycle: CoordinatorRuntimeCycleSnapshot


CoordinatorSecurityAdaptiveCheck = TypedDict(
    'CoordinatorSecurityAdaptiveCheck',
    {
        'pass': Required[bool],
        'current_ms': Required[float],
        'target_ms': Required[float],
        'threshold_ms': Required[float],
        'reason': NotRequired[str],
    },
    total=False,
)


CoordinatorSecurityEntityCheck = TypedDict(
    'CoordinatorSecurityEntityCheck',
    {
        'pass': Required[bool],
        'summary': Required[EntityBudgetSummary],
        'threshold_percent': Required[float],
        'reason': NotRequired[str],
    },
    total=False,
)


CoordinatorSecurityWebhookCheck = TypedDict(
    'CoordinatorSecurityWebhookCheck',
    {
        'pass': Required[bool],
        'configured': Required[bool],
        'secure': Required[bool],
        'hmac_ready': Required[bool],
        'insecure_configs': Required[tuple[str, ...]],
        'error': NotRequired[str],
        'reason': NotRequired[str],
    },
    total=False,
)


class CoordinatorSecurityChecks(TypedDict):
    """Collection of security check results surfaced to diagnostics."""

    adaptive_polling: CoordinatorSecurityAdaptiveCheck
    entity_budget: CoordinatorSecurityEntityCheck
    webhooks: CoordinatorSecurityWebhookCheck


class CoordinatorSecurityScorecard(TypedDict):
    """Aggregated security score surfaced via diagnostics endpoints."""

    status: Literal['pass', 'fail']
    checks: CoordinatorSecurityChecks


class CircuitBreakerStatsPayload(TypedDict, total=False):
    """Circuit breaker statistics forwarded to diagnostics panels."""

    breaker_id: str
    state: str
    failure_count: int
    success_count: int
    last_failure_time: float | None
    last_state_change: float | None
    last_success_time: float
    last_rejection_time: float | None
    total_calls: int
    total_failures: int
    total_successes: int
    rejected_calls: int


class CircuitBreakerStateSummary(TypedDict):
    """Aggregated state counters across all circuit breakers."""

    closed: int
    open: int
    half_open: int
    unknown: int
    other: int


class CoordinatorResilienceSummary(TypedDict):
    """Condensed view of coordinator resilience health."""

    total_breakers: int
    states: CircuitBreakerStateSummary
    failure_count: int
    success_count: int
    total_calls: int
    total_failures: int
    total_successes: int
    rejected_call_count: int
    last_failure_time: float | None
    last_state_change: float | None
    last_success_time: float | None
    last_rejection_time: float | None
    recovery_latency: float | None
    recovery_breaker_id: str | None
    recovery_breaker_name: NotRequired[str | None]
    last_rejection_breaker_id: NotRequired[str | None]
    last_rejection_breaker_name: NotRequired[str | None]
    rejection_rate: float | None
    open_breaker_count: int
    half_open_breaker_count: int
    unknown_breaker_count: int
    open_breakers: list[str]
    open_breaker_ids: list[str]
    half_open_breakers: list[str]
    half_open_breaker_ids: list[str]
    unknown_breakers: list[str]
    unknown_breaker_ids: list[str]
    rejection_breaker_count: int
    rejection_breakers: list[str]
    rejection_breaker_ids: list[str]


class CoordinatorResilienceDiagnostics(TypedDict, total=False):
    """Structured resilience payload surfaced through coordinator statistics."""

    breakers: dict[str, CircuitBreakerStatsPayload]
    summary: CoordinatorResilienceSummary


class CoordinatorStatisticsPayload(TypedDict):
    """Structured payload returned by :class:`CoordinatorMetrics.update_statistics`."""

    update_counts: CoordinatorUpdateCounts
    performance_metrics: CoordinatorPerformanceMetrics
    health_indicators: CoordinatorHealthIndicators
    repairs: NotRequired[CoordinatorRepairsSummary]
    reconfigure: NotRequired[ReconfigureTelemetrySummary]
    entity_budget: NotRequired[EntityBudgetSummary]
    adaptive_polling: NotRequired[AdaptivePollingDiagnostics]
    resilience: NotRequired[CoordinatorResilienceDiagnostics]
    rejection_metrics: NotRequired[CoordinatorRejectionMetrics]
    runtime_store: NotRequired[CoordinatorRuntimeStoreSummary]


class CoordinatorRuntimeContext(TypedDict):
    """Context metadata included in runtime statistics snapshots."""

    total_dogs: int
    last_update: Any
    update_interval: float


class CoordinatorErrorSummary(TypedDict):
    """Error summary included with coordinator runtime statistics."""

    consecutive_errors: int
    error_rate: float
    rejection_rate: NotRequired[float | None]
    rejected_call_count: NotRequired[int]
    rejection_breaker_count: NotRequired[int]
    open_breaker_count: NotRequired[int]
    half_open_breaker_count: NotRequired[int]
    unknown_breaker_count: NotRequired[int]
    open_breakers: NotRequired[list[str]]
    open_breaker_ids: NotRequired[list[str]]
    half_open_breakers: NotRequired[list[str]]
    half_open_breaker_ids: NotRequired[list[str]]
    unknown_breakers: NotRequired[list[str]]
    unknown_breaker_ids: NotRequired[list[str]]
    rejection_breaker_ids: NotRequired[list[str]]
    rejection_breakers: NotRequired[list[str]]


class CoordinatorServiceExecutionSummary(TypedDict, total=False):
    """Aggregated service execution telemetry surfaced via runtime statistics."""

    guard_metrics: HelperManagerGuardMetrics
    entity_factory_guard: EntityFactoryGuardMetricsSnapshot
    rejection_metrics: CoordinatorRejectionMetrics


class CoordinatorCachePerformance(TypedDict):
    """Cache performance counters surfaced during runtime diagnostics."""

    hits: int
    misses: int
    entries: int
    hit_rate: float


class CoordinatorRuntimeStatisticsPayload(TypedDict):
    """Payload returned by :class:`CoordinatorMetrics.runtime_statistics`."""

    update_counts: CoordinatorUpdateCounts
    context: CoordinatorRuntimeContext
    error_summary: CoordinatorErrorSummary
    cache_performance: CoordinatorCachePerformance
    repairs: NotRequired[CoordinatorRepairsSummary]
    reconfigure: NotRequired[ReconfigureTelemetrySummary]
    entity_budget: NotRequired[EntityBudgetSummary]
    adaptive_polling: NotRequired[AdaptivePollingDiagnostics]
    resilience: NotRequired[CoordinatorResilienceDiagnostics]
    rejection_metrics: NotRequired[CoordinatorRejectionMetrics]
    bool_coercion: NotRequired[BoolCoercionSummary]
    service_execution: NotRequired[CoordinatorServiceExecutionSummary]
    runtime_store: NotRequired[CoordinatorRuntimeStoreSummary]


class CoordinatorModuleErrorPayload(TypedDict, total=False):
    """Fallback payload recorded when a module cannot provide telemetry."""

    status: Required[str]
    reason: NotRequired[str]
    message: NotRequired[str]


CoordinatorModuleState = ModuleAdapterPayload | CoordinatorModuleErrorPayload


CoordinatorTypedModuleName = Literal[
    'feeding',
    'garden',
    'geofencing',
    'gps',
    'health',
    'walk',
    'weather',
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
    """Device metadata mapping used by :class:`PawControlDeviceLinkMixin`."""

    manufacturer: str
    model: str
    sw_version: str | None
    configuration_url: str | None
    breed: str | None
    microchip_id: str | None
    serial_number: str | None
    hw_version: str | None
    suggested_area: str | None
    extra_identifiers: Sequence[tuple[str, str]]


class CoordinatorDogData(TypedDict, total=False):
    """Runtime payload stored by the coordinator for a single dog."""

    dog_info: DogConfigData
    status: str
    status_snapshot: NotRequired[DogStatusSnapshot]
    last_update: str | None
    gps: NotRequired[CoordinatorModuleState]
    geofencing: NotRequired[CoordinatorModuleState]
    feeding: NotRequired[CoordinatorModuleState]
    walk: NotRequired[CoordinatorModuleState]
    health: NotRequired[CoordinatorModuleState]
    weather: NotRequired[CoordinatorModuleState]
    garden: NotRequired[CoordinatorModuleState]
    profile: NotRequired[DogProfileSnapshot]
    notifications: NotRequired[JSONMutableMapping]
    dashboard: NotRequired[JSONMutableMapping]
    visitor: NotRequired[JSONMutableMapping]
    grooming: NotRequired[JSONMutableMapping]
    medication: NotRequired[JSONMutableMapping]
    training: NotRequired[JSONMutableMapping]
    text_values: NotRequired[DogTextSnapshot]


class DogStatusSnapshot(TypedDict, total=False):
    """Centralized status snapshot for a dog."""

    dog_id: str
    state: str
    zone: str | None
    is_home: bool
    in_safe_zone: bool
    on_walk: bool
    needs_walk: bool
    is_hungry: bool


CoordinatorDataPayload = dict[str, CoordinatorDogData]


class CoordinatorRejectionMetrics(TypedDict):
    """Normalised rejection counters exposed via diagnostics payloads."""

    schema_version: Literal[3]
    rejected_call_count: int
    rejection_breaker_count: int
    rejection_rate: float | None
    last_rejection_time: float | None
    last_rejection_breaker_id: str | None
    last_rejection_breaker_name: str | None
    open_breaker_count: int
    half_open_breaker_count: int
    unknown_breaker_count: int
    open_breakers: list[str]
    open_breaker_ids: list[str]
    half_open_breakers: list[str]
    half_open_breaker_ids: list[str]
    unknown_breakers: list[str]
    unknown_breaker_ids: list[str]
    rejection_breaker_ids: list[str]
    rejection_breakers: list[str]


type RejectionMetricsTarget = (
    CoordinatorRejectionMetrics | CoordinatorPerformanceMetrics | JSONMutableMapping
)
"""Mutable mapping that can receive rejection metric updates."""


type RejectionMetricsSource = (
    CoordinatorRejectionMetrics | CoordinatorResilienceSummary | JSONMapping
)
"""Mapping payload that exposes coordinator rejection metrics."""


class SystemHealthThresholdDetail(TypedDict, total=False):
    """Threshold details exposed through the system health endpoint."""

    count: int
    ratio: float
    percentage: float


class SystemHealthThresholdSummary(TypedDict, total=False):
    """Source metadata for guard and breaker threshold indicators."""

    source: Required[str]
    source_key: str | None
    warning: SystemHealthThresholdDetail
    critical: SystemHealthThresholdDetail


class SystemHealthGuardReasonEntry(TypedDict):
    """Top guard skip reason surfaced through system health."""

    reason: str
    count: int


type SystemHealthIndicatorLevel = Literal['critical', 'warning', 'normal']


class SystemHealthIndicatorPayload(TypedDict, total=False):
    """Indicator payload summarising guard/breaker health."""

    level: Required[SystemHealthIndicatorLevel]
    color: Required[Literal['red', 'amber', 'green']]
    message: Required[str]
    metric_type: Required[str]
    context: str
    metric: float | int
    threshold: float | int
    threshold_type: str
    threshold_source: str


class SystemHealthGuardSummary(TypedDict):
    """Aggregated guard statistics returned by system health."""

    executed: int
    skipped: int
    total_calls: int
    skip_ratio: float
    skip_percentage: float
    has_skips: bool
    reasons: dict[str, int]
    top_reasons: list[SystemHealthGuardReasonEntry]
    thresholds: SystemHealthThresholdSummary
    indicator: SystemHealthIndicatorPayload


class SystemHealthBreakerOverview(TypedDict):
    """Breaker metrics surfaced through the system health endpoint."""

    status: Literal['open', 'recovering', 'monitoring', 'healthy']
    open_breaker_count: int
    half_open_breaker_count: int
    unknown_breaker_count: int
    rejection_rate: float
    last_rejection_breaker_id: str | None
    last_rejection_breaker_name: str | None
    last_rejection_time: float | None
    open_breakers: list[str]
    half_open_breakers: list[str]
    unknown_breakers: list[str]
    thresholds: SystemHealthThresholdSummary
    indicator: SystemHealthIndicatorPayload


class SystemHealthServiceStatus(TypedDict):
    """Composite indicator status for guard and breaker telemetry."""

    guard: SystemHealthIndicatorPayload
    breaker: SystemHealthIndicatorPayload
    overall: SystemHealthIndicatorPayload


type SystemHealthRemainingQuota = Literal['unknown', 'untracked', 'unlimited'] | int


class SystemHealthServiceExecutionSnapshot(TypedDict):
    """Structured service execution payload for system health diagnostics."""

    guard_metrics: HelperManagerGuardMetrics
    guard_summary: SystemHealthGuardSummary
    entity_factory_guard: EntityFactoryGuardMetricsSnapshot
    rejection_metrics: CoordinatorRejectionMetrics
    breaker_overview: SystemHealthBreakerOverview
    status: SystemHealthServiceStatus
    manual_events: ManualResilienceEventsTelemetry


class SystemHealthInfoPayload(TypedDict):
    """Top-level system health payload exposed by the integration."""

    can_reach_backend: bool
    remaining_quota: SystemHealthRemainingQuota
    service_execution: SystemHealthServiceExecutionSnapshot
    runtime_store: RuntimeStoreCompatibilitySnapshot


class DogProfileSnapshot(TypedDict, total=False):
    """Profile metadata exposed through coordinator dog snapshots."""

    birthdate: str | None
    adoption_date: str | None
    diet_start_date: str | None
    diet_end_date: str | None
    training_start_date: str | None
    next_training_date: str | None
    dog_age: int | None
    dog_weight: float | None
    dog_size: str | None
    entity_profile: str | None


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
    """

    # Required fields - must be present for valid configuration
    dog_id: Required[str]
    dog_name: Required[str]

    # Optional fields with comprehensive coverage for dog characteristics
    dog_breed: NotRequired[str | None]
    dog_age: NotRequired[int | None]
    dog_weight: NotRequired[float | None]
    dog_size: NotRequired[str | None]
    dog_color: NotRequired[str | None]
    microchip_id: NotRequired[str | None]
    vet_contact: NotRequired[str | None]
    emergency_contact: NotRequired[str | None]
    modules: NotRequired[DogModulesConfig]
    dog_image: NotRequired[str | None]
    discovery_info: NotRequired[ConfigFlowDiscoveryData]
    gps_config: NotRequired[DogGPSConfig]
    feeding_config: NotRequired[DogFeedingConfig]
    health_config: NotRequired[DogHealthConfig]
    door_sensor: NotRequired[str | None]
    door_sensor_settings: NotRequired[DoorSensorSettingsPayload | None]
    text_values: NotRequired[DogTextSnapshot]
    text_metadata: NotRequired[DogTextMetadataSnapshot]


# TypedDict key literals for dog configuration structures.
DOG_ID_FIELD: Final[Literal['dog_id']] = 'dog_id'
DOG_NAME_FIELD: Final[Literal['dog_name']] = 'dog_name'
DOG_BREED_FIELD: Final[Literal['dog_breed']] = 'dog_breed'
DOG_AGE_FIELD: Final[Literal['dog_age']] = 'dog_age'
DOG_WEIGHT_FIELD: Final[Literal['dog_weight']] = 'dog_weight'
DOG_SIZE_FIELD: Final[Literal['dog_size']] = 'dog_size'
DOG_MODULES_FIELD: Final[Literal['modules']] = 'modules'
DOG_DISCOVERY_FIELD: Final[Literal['discovery_info']] = 'discovery_info'
DOG_COLOR_FIELD: Final[Literal['dog_color']] = 'dog_color'
DOG_MICROCHIP_ID_FIELD: Final[Literal['microchip_id']] = 'microchip_id'
DOG_VET_CONTACT_FIELD: Final[Literal['vet_contact']] = 'vet_contact'
DOG_EMERGENCY_CONTACT_FIELD: Final[Literal['emergency_contact']] = 'emergency_contact'
DOG_FEEDING_CONFIG_FIELD: Final[Literal['feeding_config']] = 'feeding_config'
DOG_HEALTH_CONFIG_FIELD: Final[Literal['health_config']] = 'health_config'
DOG_GPS_CONFIG_FIELD: Final[Literal['gps_config']] = 'gps_config'
DOG_IMAGE_FIELD: Final[Literal['dog_image']] = 'dog_image'
DOG_TEXT_VALUES_FIELD: Final[Literal['text_values']] = 'text_values'
DOG_TEXT_METADATA_FIELD: Final[Literal['text_metadata']] = 'text_metadata'
WALK_IN_PROGRESS_FIELD: Final[Literal['walk_in_progress']] = 'walk_in_progress'
VISITOR_MODE_ACTIVE_FIELD: Final[Literal['visitor_mode_active']] = 'visitor_mode_active'

# Text snapshot keys maintained for text entity persistence.
TextSnapshotKey = Literal[
    'notes',
    'custom_label',
    'walk_notes',
    'current_walk_label',
    'health_notes',
    'medication_notes',
    'vet_notes',
    'grooming_notes',
    'custom_message',
    'emergency_contact',
    'microchip',
    'breeder_info',
    'registration',
    'insurance_info',
    'allergies',
    'training_notes',
    'behavior_notes',
    'location_description',
]

_DOG_TEXT_SNAPSHOT_KEYS: Final[tuple[TextSnapshotKey, ...]] = (
    'notes',
    'custom_label',
    'walk_notes',
    'current_walk_label',
    'health_notes',
    'medication_notes',
    'vet_notes',
    'grooming_notes',
    'custom_message',
    'emergency_contact',
    'microchip',
    'breeder_info',
    'registration',
    'insurance_info',
    'allergies',
    'training_notes',
    'behavior_notes',
    'location_description',
)


def ensure_dog_text_snapshot(
    payload: Mapping[str, JSONValue],
) -> DogTextSnapshot | None:
    """Return a normalised :class:`DogTextSnapshot` built from ``payload``."""

    snapshot: dict[str, str] = {}
    for key in _DOG_TEXT_SNAPSHOT_KEYS:
        raw_value = payload.get(key)
        if isinstance(raw_value, str):
            snapshot[key] = raw_value

    if not snapshot:
        return None

    return cast(DogTextSnapshot, snapshot)


def _normalise_text_metadata_entry(
    raw_value: object | None,
) -> DogTextMetadataEntry | None:
    """Return a typed metadata entry built from ``raw_value`` when possible."""

    if isinstance(raw_value, Mapping):
        entry: dict[str, str | None] = {}
        last_updated = raw_value.get('last_updated')
        if isinstance(last_updated, str) and last_updated:
            entry['last_updated'] = last_updated

        context_id = raw_value.get('context_id')
        if isinstance(context_id, str) and context_id:
            entry['context_id'] = context_id

        parent_id = raw_value.get('parent_id')
        if isinstance(parent_id, str) and parent_id:
            entry['parent_id'] = parent_id

        user_id = raw_value.get('user_id')
        if isinstance(user_id, str) and user_id:
            entry['user_id'] = user_id

        if not entry:
            return None

        return cast(DogTextMetadataEntry, entry)

    if isinstance(raw_value, str) and raw_value:
        return cast(DogTextMetadataEntry, {'last_updated': raw_value})

    return None


def ensure_dog_text_metadata_snapshot(
    payload: Mapping[str, JSONValue],
) -> DogTextMetadataSnapshot | None:
    """Return a normalised :class:`DogTextMetadataSnapshot` from ``payload``."""

    metadata: dict[str, DogTextMetadataEntry] = {}
    for key in _DOG_TEXT_SNAPSHOT_KEYS:
        raw_value = payload.get(key)
        entry = _normalise_text_metadata_entry(raw_value)
        if entry is not None:
            metadata[key] = entry

    if not metadata:
        return None

    return cast(DogTextMetadataSnapshot, metadata)


# Field literals for external entity configuration helpers.
GPS_SOURCE_FIELD: Final[Literal['gps_source']] = 'gps_source'
DOOR_SENSOR_FIELD: Final[Literal['door_sensor']] = 'door_sensor'
NOTIFY_FALLBACK_FIELD: Final[Literal['notify_fallback']] = 'notify_fallback'

# Field literals for dashboard setup preferences.
DASHBOARD_ENABLED_FIELD: Final[Literal['dashboard_enabled']] = 'dashboard_enabled'
DASHBOARD_AUTO_CREATE_FIELD: Final[Literal['dashboard_auto_create']] = (
    'dashboard_auto_create'
)
DASHBOARD_PER_DOG_FIELD: Final[Literal['dashboard_per_dog']] = 'dashboard_per_dog'
DASHBOARD_THEME_FIELD: Final[Literal['dashboard_theme']] = 'dashboard_theme'
DASHBOARD_MODE_FIELD: Final[Literal['dashboard_mode']] = 'dashboard_mode'
SHOW_STATISTICS_FIELD: Final[Literal['show_statistics']] = 'show_statistics'
SHOW_MAPS_FIELD: Final[Literal['show_maps']] = 'show_maps'
SHOW_HEALTH_CHARTS_FIELD: Final[Literal['show_health_charts']] = 'show_health_charts'
SHOW_FEEDING_SCHEDULE_FIELD: Final[Literal['show_feeding_schedule']] = (
    'show_feeding_schedule'
)
SHOW_ALERTS_FIELD: Final[Literal['show_alerts']] = 'show_alerts'
COMPACT_MODE_FIELD: Final[Literal['compact_mode']] = 'compact_mode'
AUTO_REFRESH_FIELD: Final[Literal['auto_refresh']] = 'auto_refresh'


def ensure_dog_config_data(data: Mapping[str, JSONValue]) -> DogConfigData | None:
    """Return a ``DogConfigData`` structure extracted from ``data`` mappings."""

    dog_id = data.get(DOG_ID_FIELD)
    dog_name = data.get(DOG_NAME_FIELD)

    if not isinstance(dog_id, str) or not dog_id:
        return None
    if not isinstance(dog_name, str) or not dog_name:
        return None

    config: DogConfigData = {
        DOG_ID_FIELD: dog_id,
        DOG_NAME_FIELD: dog_name,
    }

    breed = data.get(DOG_BREED_FIELD)
    if isinstance(breed, str):
        config[DOG_BREED_FIELD] = breed

    age = data.get(DOG_AGE_FIELD)
    if isinstance(age, int):
        config[DOG_AGE_FIELD] = age

    weight = data.get(DOG_WEIGHT_FIELD)
    if isinstance(weight, int | float):
        config[DOG_WEIGHT_FIELD] = float(weight)

    size = data.get(DOG_SIZE_FIELD)
    if isinstance(size, str):
        config[DOG_SIZE_FIELD] = size

    color = data.get(DOG_COLOR_FIELD)
    if isinstance(color, str) and color:
        config[DOG_COLOR_FIELD] = color

    microchip_id = data.get(DOG_MICROCHIP_ID_FIELD)
    if isinstance(microchip_id, str) and microchip_id:
        config[DOG_MICROCHIP_ID_FIELD] = microchip_id

    vet_contact = data.get(DOG_VET_CONTACT_FIELD)
    if isinstance(vet_contact, str) and vet_contact:
        config[DOG_VET_CONTACT_FIELD] = vet_contact

    emergency_contact = data.get(DOG_EMERGENCY_CONTACT_FIELD)
    if isinstance(emergency_contact, str) and emergency_contact:
        config[DOG_EMERGENCY_CONTACT_FIELD] = emergency_contact

    modules_payload = data.get(DOG_MODULES_FIELD)
    if _is_modules_projection_like(modules_payload):
        config[DOG_MODULES_FIELD] = coerce_dog_modules_config(
            cast(DogModulesProjection, modules_payload)
        )
    elif isinstance(modules_payload, Mapping):
        config[DOG_MODULES_FIELD] = coerce_dog_modules_config(
            cast(Mapping[str, object], modules_payload)
        )

    discovery_info = data.get(DOG_DISCOVERY_FIELD)
    if isinstance(discovery_info, Mapping):
        config[DOG_DISCOVERY_FIELD] = cast(
            ConfigFlowDiscoveryData,
            dict(discovery_info),
        )

    gps_config = data.get(DOG_GPS_CONFIG_FIELD)
    if isinstance(gps_config, Mapping):
        config[DOG_GPS_CONFIG_FIELD] = cast(DogGPSConfig, dict(gps_config))

    feeding_config = data.get(DOG_FEEDING_CONFIG_FIELD)
    if isinstance(feeding_config, Mapping):
        config[DOG_FEEDING_CONFIG_FIELD] = cast(
            DogFeedingConfig,
            dict(feeding_config),
        )

    health_config = data.get(DOG_HEALTH_CONFIG_FIELD)
    if isinstance(health_config, Mapping):
        config[DOG_HEALTH_CONFIG_FIELD] = cast(
            DogHealthConfig,
            dict(health_config),
        )

    door_sensor = data.get(CONF_DOOR_SENSOR)
    if isinstance(door_sensor, str):
        trimmed_sensor = door_sensor.strip()
        if trimmed_sensor:
            config['door_sensor'] = trimmed_sensor

    normalised_settings = _normalise_door_sensor_settings_payload(
        data.get(CONF_DOOR_SENSOR_SETTINGS)
    )
    if normalised_settings is not None:
        config['door_sensor_settings'] = normalised_settings

    text_payload = data.get(DOG_TEXT_VALUES_FIELD)
    if isinstance(text_payload, Mapping):
        snapshot = ensure_dog_text_snapshot(text_payload)
        if snapshot is not None:
            config[DOG_TEXT_VALUES_FIELD] = snapshot

    text_metadata_payload = data.get(DOG_TEXT_METADATA_FIELD)
    if isinstance(text_metadata_payload, Mapping):
        metadata_snapshot = ensure_dog_text_metadata_snapshot(text_metadata_payload)
        if metadata_snapshot is not None:
            config[DOG_TEXT_METADATA_FIELD] = metadata_snapshot

    return config


RawDogConfig = JSONMapping | DogConfigData


def _normalise_door_sensor_settings_payload(
    payload: Any,
) -> DoorSensorSettingsPayload | None:
    """Return a stored payload for door sensor overrides when available."""

    if payload is None:
        return None

    from .door_sensor_manager import ensure_door_sensor_settings_config

    if isinstance(payload, DoorSensorSettingsConfig):
        settings = payload
    elif isinstance(payload, Mapping):
        settings = ensure_door_sensor_settings_config(payload)
    else:
        return None

    settings_payload = cast(DoorSensorSettingsPayload, asdict(settings))
    if not settings_payload:
        return None

    if settings_payload == cast(
        DoorSensorSettingsPayload, asdict(DEFAULT_DOOR_SENSOR_SETTINGS)
    ):
        return None

    return settings_payload


def ensure_dog_options_entry(
    value: JSONLikeMapping,
    /,
    *,
    dog_id: str | None = None,
) -> DogOptionsEntry:
    """Return a normalised :class:`DogOptionsEntry` built from ``value``."""

    entry: DogOptionsEntry = {}

    raw_dog_id = value.get(DOG_ID_FIELD)
    if isinstance(raw_dog_id, str) and raw_dog_id:
        entry['dog_id'] = raw_dog_id
    elif isinstance(dog_id, str) and dog_id:
        entry['dog_id'] = dog_id

    modules_payload = value.get(DOG_MODULES_FIELD)
    if _is_modules_projection_like(modules_payload):
        entry['modules'] = coerce_dog_modules_config(
            cast(DogModulesProjection, modules_payload)
        )
    elif isinstance(modules_payload, Mapping):
        entry['modules'] = coerce_dog_modules_config(
            cast(Mapping[str, object], modules_payload)
        )

    notifications_payload = value.get(CONF_NOTIFICATIONS)
    if isinstance(notifications_payload, Mapping):
        entry['notifications'] = ensure_notification_options(
            cast(NotificationOptionsInput, dict(notifications_payload)),
            defaults=DEFAULT_NOTIFICATION_OPTIONS,
        )

    gps_payload = value.get(CONF_GPS_SETTINGS)
    if isinstance(gps_payload, Mapping):
        entry['gps_settings'] = cast(GPSOptions, dict(gps_payload))

    geofence_payload = value.get('geofence_settings')
    if isinstance(geofence_payload, Mapping):
        entry['geofence_settings'] = cast(GeofenceOptions, dict(geofence_payload))

    feeding_payload = value.get('feeding_settings')
    if isinstance(feeding_payload, Mapping):
        entry['feeding_settings'] = cast(FeedingOptions, dict(feeding_payload))

    health_payload = value.get('health_settings')
    if isinstance(health_payload, Mapping):
        entry['health_settings'] = cast(HealthOptions, dict(health_payload))

    return entry


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
    """

    total_detections: int
    successful_walks: int
    false_positives: int
    false_negatives: int
    average_confidence: float


class DetectionStatusEntry(TypedDict):
    """Status information for an individual dog's detection state."""

    dog_name: str
    door_sensor: str
    current_state: str
    confidence_score: float
    active_walk_id: str | None
    last_door_state: str | None
    recent_activity: int


class DetectionStatus(TypedDict):
    """Structured detection status payload for diagnostics endpoints."""

    configured_dogs: int
    active_detections: int
    detection_states: dict[str, DetectionStatusEntry]
    statistics: DetectionStatistics


class DoorSensorStateHistoryEntry(TypedDict):
    """Serialised state transition captured by the door sensor manager."""

    timestamp: str | None
    state: str


class DoorSensorStateSnapshot(TypedDict, total=False):
    """Detailed walk detection state exported in cache diagnostics."""

    current_state: str
    door_opened_at: str | None
    door_closed_at: str | None
    potential_walk_start: str | None
    active_walk_id: str | None
    confidence_score: float
    last_door_state: str | None
    consecutive_opens: int
    state_history: list[DoorSensorStateHistoryEntry]
    last_activity_age_seconds: int


class DoorSensorDogSnapshot(TypedDict, total=False):
    """Per-dog configuration snapshot for diagnostics exports."""

    entity_id: str
    enabled: bool
    walk_detection_timeout: int
    minimum_walk_duration: int
    maximum_walk_duration: int
    door_closed_delay: int
    require_confirmation: bool
    auto_end_walks: bool
    confidence_threshold: float
    state: DoorSensorStateSnapshot


type DoorSensorConfigUpdateValue = DoorSensorSettingsPayload | str | None
"""Union of values persisted alongside door sensor configuration updates."""

type DoorSensorConfigUpdate = dict[str, DoorSensorConfigUpdateValue]
"""Mutable payload pushed to the data manager during door sensor updates."""


class DoorSensorManagerStats(DetectionStatistics, total=False):
    """Aggregated statistics surfaced alongside detection telemetry."""

    configured_sensors: int
    active_detections: int
    last_activity_age_seconds: int


class DoorSensorManagerSnapshot(TypedDict):
    """Coordinator snapshot payload returned by the door sensor cache monitor."""

    per_dog: dict[str, DoorSensorDogSnapshot]
    detection_stats: DetectionStatistics
    manager_last_activity: str | None


class StorageNamespaceDogSummary(TypedDict, total=False):
    """Aggregated state persisted for a single storage namespace entry."""

    entries: int
    payload_type: str
    timestamp: str | None
    timestamp_age_seconds: int
    timestamp_issue: str


class StorageNamespaceStats(TypedDict):
    """Summary metrics for coordinator storage namespace diagnostics."""

    namespace: str
    dogs: int
    entries: int


class StorageNamespaceSnapshot(TypedDict):
    """Structured snapshot returned by storage namespace monitors."""

    namespace: str
    per_dog: dict[str, StorageNamespaceDogSummary]


class DataManagerMetricsSnapshot(TypedDict):
    """Metrics exposed by :class:`PawControlDataManager`."""

    dogs: int
    storage_path: str
    cache_diagnostics: CacheDiagnosticsMap


class EntityBudgetSnapshotEntry(TypedDict, total=False):
    """Serialised budget snapshot exported for coordinator diagnostics."""

    dog_id: str
    profile: str
    capacity: int | float
    base_allocation: int | float
    dynamic_allocation: int | float
    requested_entities: tuple[str, ...]
    denied_requests: tuple[str, ...]
    recorded_at: str | None


class EntityBudgetStats(TypedDict):
    """Summary metrics for entity budget tracker diagnostics."""

    tracked_dogs: int
    saturation_percent: float


class EntityBudgetDiagnostics(TypedDict):
    """Structured diagnostics payload for entity budget telemetry."""

    summary: JSONMutableMapping
    snapshots: list[EntityBudgetSnapshotEntry]


class RuntimeErrorHistoryEntry(TypedDict, total=False):
    """Structured runtime error metadata stored for diagnostics."""

    timestamp: Required[str]
    source: Required[str]
    dog_id: NotRequired[str]
    door_sensor: NotRequired[str | None]
    error: NotRequired[str]
    context: NotRequired[ErrorContext | None]


type RuntimeErrorHistory = list[RuntimeErrorHistoryEntry]


class DoorSensorPersistenceFailure(TypedDict, total=False):
    """Telemetry entry captured when door sensor persistence fails."""

    dog_id: Required[str]
    recorded_at: Required[str]
    dog_name: NotRequired[str | None]
    door_sensor: NotRequired[str | None]
    settings: NotRequired[DoorSensorSettingsPayload | None]
    error: NotRequired[str]


class DoorSensorFailureSummary(TypedDict, total=False):
    """Aggregated telemetry for door sensor persistence failures per dog."""

    dog_id: Required[str]
    failure_count: Required[int]
    last_failure: Required[DoorSensorPersistenceFailure]
    dog_name: NotRequired[str | None]


class PerformanceTrackerBucket(TypedDict, total=False):
    """Execution metrics recorded by :func:`performance_tracker`."""

    runs: int
    failures: int
    durations_ms: list[float]
    average_ms: float
    last_run: str | None
    last_error: str | None


class RuntimePerformanceStats(TypedDict, total=False):
    """Mutable runtime telemetry stored on :class:`PawControlRuntimeData`."""

    bool_coercion_summary: BoolCoercionSummary
    reconfigure_summary: ReconfigureTelemetrySummary
    resilience_summary: CoordinatorResilienceSummary
    resilience_diagnostics: CoordinatorResilienceDiagnostics
    door_sensor_failures: list[DoorSensorPersistenceFailure]
    door_sensor_failure_count: int
    last_door_sensor_failure: DoorSensorPersistenceFailure
    door_sensor_failure_summary: dict[str, DoorSensorFailureSummary]
    runtime_store_health: RuntimeStoreHealthHistory
    service_guard_metrics: ServiceGuardMetricsSnapshot
    entity_factory_guard_metrics: EntityFactoryGuardMetrics
    rejection_metrics: CoordinatorRejectionMetrics
    service_results: list[ServiceExecutionResult]
    last_service_result: ServiceExecutionResult
    service_call_telemetry: ServiceCallTelemetry
    maintenance_results: list[MaintenanceExecutionResult]
    last_maintenance_result: MaintenanceExecutionResult
    last_cache_diagnostics: CacheDiagnosticsCapture
    daily_resets: int
    performance_buckets: dict[str, PerformanceTrackerBucket]


def empty_runtime_performance_stats() -> RuntimePerformanceStats:
    """Return an empty runtime performance stats mapping for dataclass defaults."""

    return cast(RuntimePerformanceStats, {})


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
    """

    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]
    background_monitor_task: Task[None] | None = None
    garden_manager: GardenManager | None = None
    geofencing_manager: PawControlGeofencing | None = None
    helper_manager: PawControlHelperManager | None = None
    script_manager: PawControlScriptManager | None = None
    gps_geofence_manager: GPSGeofenceManager | None = None
    door_sensor_manager: DoorSensorManager | None = None
    device_api_client: PawControlDeviceClient | None = None

    # Enhanced runtime tracking for Platinum-targeted monitoring
    performance_stats: RuntimePerformanceStats = field(
        default_factory=empty_runtime_performance_stats
    )
    error_history: RuntimeErrorHistory = field(default_factory=list)
    manual_event_history: deque[ManualResilienceEventRecord] = field(
        default_factory=lambda: deque(maxlen=5)
    )
    # PLATINUM: Optional unsubscribe callbacks for scheduler and reload listener
    daily_reset_unsub: Any = field(default=None)
    reload_unsub: Callable[[], Any] | None = None
    schema_created_version: int = DOMAIN_RUNTIME_STORE_VERSION
    schema_version: int = DOMAIN_RUNTIME_STORE_VERSION
    _runtime_managers_cache: CoordinatorRuntimeManagers | None = field(
        default=None, init=False, repr=False
    )

    @property
    def runtime_managers(self) -> CoordinatorRuntimeManagers:
        """Return the runtime manager container associated with this entry."""

        cached = self._runtime_managers_cache
        if cached is not None:
            return cached

        coordinator_managers = getattr(self.coordinator, 'runtime_managers', None)
        if isinstance(coordinator_managers, CoordinatorRuntimeManagers):
            self._runtime_managers_cache = coordinator_managers
            return coordinator_managers

        container = CoordinatorRuntimeManagers(
            data_manager=getattr(self, 'data_manager', None),
            feeding_manager=getattr(self, 'feeding_manager', None),
            walk_manager=getattr(self, 'walk_manager', None),
            notification_manager=getattr(self, 'notification_manager', None),
            gps_geofence_manager=getattr(self, 'gps_geofence_manager', None),
            geofencing_manager=getattr(self, 'geofencing_manager', None),
            weather_health_manager=getattr(self, 'weather_health_manager', None),
            garden_manager=getattr(self, 'garden_manager', None),
        )
        self._runtime_managers_cache = container
        return container

    def as_dict(self) -> PawControlRuntimeDataExport:
        """Return a dictionary representation of the runtime data.

        Provides dictionary access to all runtime components for scenarios
        where dictionary-style access is more convenient than direct
        attribute access.

        Returns:
            Dictionary mapping component names to runtime instances
        """
        return {
            'coordinator': self.coordinator,
            'data_manager': self.data_manager,
            'notification_manager': self.notification_manager,
            'feeding_manager': self.feeding_manager,
            'walk_manager': self.walk_manager,
            'runtime_managers': self.runtime_managers,
            'entity_factory': self.entity_factory,
            'entity_profile': self.entity_profile,
            'dogs': self.dogs,
            'garden_manager': self.garden_manager,
            'geofencing_manager': self.geofencing_manager,
            'script_manager': self.script_manager,
            'gps_geofence_manager': self.gps_geofence_manager,
            'door_sensor_manager': self.door_sensor_manager,
            'helper_manager': self.helper_manager,
            'device_api_client': self.device_api_client,
            'performance_stats': self.performance_stats,
            'error_history': self.error_history,
            'manual_event_history': list(self.manual_event_history),
            'background_monitor_task': self.background_monitor_task,
            'daily_reset_unsub': self.daily_reset_unsub,
            'schema_created_version': self.schema_created_version,
            'schema_version': self.schema_version,
        }

    def __getitem__(self, key: str) -> Any:
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
            return getattr(self, key)
        raise KeyError(key) from None

    def get(self, key: str, default: Any | None = None) -> Any | None:
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
    """Serialized representation of legacy runtime store entries."""

    runtime_data: PawControlRuntimeData
    version: int
    created_version: int


@dataclass(slots=True)
class DomainRuntimeStoreEntry:
    """Container persisting runtime data within ``hass.data`` namespaces."""

    runtime_data: PawControlRuntimeData
    version: int = DOMAIN_RUNTIME_STORE_VERSION
    created_version: int = DOMAIN_RUNTIME_STORE_VERSION

    CURRENT_VERSION: ClassVar[int] = DOMAIN_RUNTIME_STORE_VERSION
    MINIMUM_COMPATIBLE_VERSION: ClassVar[int] = (
        DOMAIN_RUNTIME_STORE_MINIMUM_COMPATIBLE_VERSION
    )

    def unwrap(self) -> PawControlRuntimeData:
        """Return the stored runtime payload."""

        return self.runtime_data

    def ensure_current(self) -> DomainRuntimeStoreEntry:
        """Return an entry stamped with the current schema version."""

        if self.version == self.CURRENT_VERSION:
            return self
        return DomainRuntimeStoreEntry(
            runtime_data=self.runtime_data,
            version=self.CURRENT_VERSION,
            created_version=self.created_version,
        )

    def is_future_version(self) -> bool:
        """Return ``True`` when the entry was produced by a newer schema."""

        return (
            self.version > self.CURRENT_VERSION
            or self.created_version > self.CURRENT_VERSION
        )

    def is_legacy_version(self) -> bool:
        """Return ``True`` when the entry predates the compatibility window."""

        return self.created_version < self.MINIMUM_COMPATIBLE_VERSION


type DomainRuntimeStore = MutableMapping[str, DomainRuntimeStoreEntry]


RuntimeStoreEntryStatus = Literal[
    'missing',
    'unstamped',
    'current',
    'upgrade_pending',
    'legacy_upgrade_required',
    'future_incompatible',
]
"""Status values describing compatibility of runtime store entries."""


RuntimeStoreOverallStatus = Literal[
    'missing',
    'current',
    'detached_entry',
    'detached_store',
    'diverged',
    'needs_migration',
    'future_incompatible',
]
"""High-level compatibility summary for runtime store state."""


class RuntimeStoreEntrySnapshot(TypedDict, total=False):
    """Snapshot describing a single runtime store representation."""

    available: bool
    version: int | None
    created_version: int | None
    status: RuntimeStoreEntryStatus


class RuntimeStoreCompatibilitySnapshot(TypedDict):
    """Composite compatibility summary for runtime store metadata."""

    entry_id: str
    status: RuntimeStoreOverallStatus
    current_version: int
    minimum_compatible_version: int
    entry: RuntimeStoreEntrySnapshot
    store: RuntimeStoreEntrySnapshot
    divergence_detected: bool


RuntimeStoreHealthLevel = Literal['ok', 'watch', 'action_required']
"""Risk level derived from runtime store compatibility checks."""


class RuntimeStoreAssessmentEvent(TypedDict, total=False):
    """Timeline entry capturing individual runtime store assessments."""

    timestamp: str
    level: RuntimeStoreHealthLevel
    previous_level: RuntimeStoreHealthLevel | None
    status: RuntimeStoreOverallStatus
    entry_status: RuntimeStoreEntryStatus | None
    store_status: RuntimeStoreEntryStatus | None
    reason: str
    recommended_action: str | None
    divergence_detected: bool
    divergence_rate: float | None
    checks: int
    divergence_events: int
    level_streak: int
    escalations: int
    deescalations: int
    level_changed: bool
    current_level_duration_seconds: float | None


class RuntimeStoreAssessmentTimelineSegment(TypedDict, total=False):
    """Contiguous period derived from runtime store assessment events."""

    start: str
    end: str | None
    level: RuntimeStoreHealthLevel
    status: RuntimeStoreOverallStatus | None
    entry_status: RuntimeStoreEntryStatus | None
    store_status: RuntimeStoreEntryStatus | None
    reason: str | None
    recommended_action: str | None
    divergence_detected: bool | None
    divergence_rate: float | None
    checks: int | None
    divergence_events: int | None
    duration_seconds: float | None


class RuntimeStoreLevelDurationPercentiles(TypedDict, total=False):
    """Percentile distribution for runtime store level durations."""

    p75: float
    p90: float
    p95: float


class RuntimeStoreLevelDurationAlert(TypedDict, total=False):
    """Alert produced when duration percentiles exceed guard limits."""

    level: RuntimeStoreHealthLevel
    percentile_label: str
    percentile_rank: float
    percentile_seconds: float
    guard_limit_seconds: float
    severity: str
    recommended_action: str | None


class RuntimeStoreAssessmentTimelineSummary(TypedDict, total=False):
    """Derived statistics for the runtime store assessment timeline."""

    total_events: int
    level_changes: int
    level_change_rate: float | None
    level_counts: dict[RuntimeStoreHealthLevel, int]
    status_counts: dict[RuntimeStoreOverallStatus, int]
    reason_counts: dict[str, int]
    distinct_reasons: int
    first_event_timestamp: str | None
    last_event_timestamp: str | None
    last_level: RuntimeStoreHealthLevel | None
    last_status: RuntimeStoreOverallStatus | None
    last_reason: str | None
    last_recommended_action: str | None
    last_divergence_detected: bool | None
    last_divergence_rate: float | None
    last_level_duration_seconds: float | None
    timeline_window_seconds: float | None
    timeline_window_days: float | None
    events_per_day: float | None
    most_common_reason: str | None
    most_common_level: RuntimeStoreHealthLevel | None
    most_common_status: RuntimeStoreOverallStatus | None
    average_divergence_rate: float | None
    max_divergence_rate: float | None
    level_duration_peaks: dict[RuntimeStoreHealthLevel, float]
    level_duration_latest: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_totals: dict[RuntimeStoreHealthLevel, float]
    level_duration_samples: dict[RuntimeStoreHealthLevel, int]
    level_duration_averages: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_minimums: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_medians: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_standard_deviations: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_percentiles: dict[
        RuntimeStoreHealthLevel, RuntimeStoreLevelDurationPercentiles
    ]
    level_duration_alert_thresholds: dict[RuntimeStoreHealthLevel, float | None]
    level_duration_guard_alerts: list[RuntimeStoreLevelDurationAlert]


class RuntimeStoreHealthHistory(TypedDict, total=False):
    """Rolling history of runtime store compatibility checks."""

    schema_version: int
    checks: int
    status_counts: dict[RuntimeStoreOverallStatus, int]
    divergence_events: int
    last_checked: str | None
    last_status: RuntimeStoreOverallStatus | None
    last_entry_status: RuntimeStoreEntryStatus | None
    last_store_status: RuntimeStoreEntryStatus | None
    last_entry_version: int | None
    last_store_version: int | None
    last_entry_created_version: int | None
    last_store_created_version: int | None
    divergence_detected: bool
    assessment_last_level: RuntimeStoreHealthLevel | None
    assessment_last_level_change: str | None
    assessment_level_streak: int
    assessment_escalations: int
    assessment_deescalations: int
    assessment_level_durations: dict[RuntimeStoreHealthLevel, float]
    assessment_current_level_duration_seconds: float | None
    assessment_events: list[RuntimeStoreAssessmentEvent]
    assessment: RuntimeStoreHealthAssessment
    assessment_timeline_segments: list[RuntimeStoreAssessmentTimelineSegment]
    assessment_timeline_summary: RuntimeStoreAssessmentTimelineSummary


class RuntimeStoreHealthAssessment(TypedDict, total=False):
    """Risk assessment based on runtime store history and current snapshot."""

    level: RuntimeStoreHealthLevel
    previous_level: RuntimeStoreHealthLevel | None
    reason: str
    recommended_action: str | None
    divergence_rate: float | None
    checks: int
    divergence_events: int
    last_status: RuntimeStoreOverallStatus | None
    last_entry_status: RuntimeStoreEntryStatus | None
    last_store_status: RuntimeStoreEntryStatus | None
    last_checked: str | None
    divergence_detected: bool
    level_streak: int
    last_level_change: str | None
    escalations: int
    deescalations: int
    level_durations: dict[RuntimeStoreHealthLevel, float]
    current_level_duration_seconds: float | None
    events: list[RuntimeStoreAssessmentEvent]
    timeline_summary: RuntimeStoreAssessmentTimelineSummary
    timeline_segments: list[RuntimeStoreAssessmentTimelineSegment]


class CoordinatorRuntimeStoreSummary(TypedDict, total=False):
    """Runtime store snapshot surfaced through coordinator diagnostics."""

    snapshot: RuntimeStoreCompatibilitySnapshot
    history: RuntimeStoreHealthHistory
    assessment: RuntimeStoreHealthAssessment


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
    """Serialized representation of :class:`DailyStats` records."""

    date: str
    feedings_count: int
    walks_count: int
    health_logs_count: int
    gps_updates_count: int
    total_food_amount: float
    total_walk_distance: float
    total_walk_time: int
    total_calories_burned: float
    last_feeding: str | None
    last_walk: str | None
    last_health_event: str | None


class PawControlRuntimeDataExport(TypedDict):
    """Dictionary-style runtime data export returned by ``as_dict``."""

    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    runtime_managers: CoordinatorRuntimeManagers
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]
    garden_manager: GardenManager | None
    geofencing_manager: PawControlGeofencing | None
    script_manager: PawControlScriptManager | None
    gps_geofence_manager: GPSGeofenceManager | None
    door_sensor_manager: DoorSensorManager | None
    helper_manager: PawControlHelperManager | None
    device_api_client: PawControlDeviceClient | None
    performance_stats: RuntimePerformanceStats
    error_history: RuntimeErrorHistory
    manual_event_history: list[ManualResilienceEventRecord]
    background_monitor_task: Task[None] | None
    daily_reset_unsub: Any
    schema_created_version: int
    schema_version: int


@dataclass
class DailyStats:
    """Aggregated per-day statistics for a dog.

    The data manager stores a ``DailyStats`` instance for each dog so that
    frequently accessed aggregate metrics such as the total number of feedings
    or walks can be retrieved without scanning the full history on every
    update.  The class mirrors the behaviour of the Home Assistant integration
    by providing helpers for serialization and incremental updates.
    """

    date: datetime
    feedings_count: int = 0
    walks_count: int = 0
    health_logs_count: int = 0
    gps_updates_count: int = 0
    total_food_amount: float = 0.0
    total_walk_distance: float = 0.0
    total_walk_time: int = 0
    total_calories_burned: float = 0.0
    last_feeding: datetime | None = None
    last_walk: datetime | None = None
    last_health_event: datetime | None = None

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        """Convert ISO formatted values into timezone aware ``datetime`` objects."""

        if value is None:
            return None
        if isinstance(value, datetime):
            return dt_util.as_utc(value)
        if isinstance(value, str):
            parsed = dt_util.parse_datetime(value)
            if parsed is not None:
                return dt_util.as_utc(parsed)
        return None

    @classmethod
    def from_dict(cls, payload: JSONDateMapping) -> DailyStats:
        """Deserialize daily statistics from a dictionary structure."""

        raw_date = payload.get('date')
        date_value = cls._parse_datetime(raw_date) or dt_util.utcnow()

        def _coerce_int(value: JSONDateValue | None, *, default: int = 0) -> int:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    return default
                try:
                    return int(float(stripped))
                except ValueError:
                    return default
            return default

        def _coerce_float(
            value: JSONDateValue | None, *, default: float = 0.0
        ) -> float:
            if isinstance(value, bool):
                return float(value)
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    return default
                try:
                    return float(stripped)
                except ValueError:
                    return default
            return default

        return cls(
            date=date_value,
            feedings_count=_coerce_int(payload.get('feedings_count')),
            walks_count=_coerce_int(payload.get('walks_count')),
            health_logs_count=_coerce_int(payload.get('health_logs_count')),
            gps_updates_count=_coerce_int(payload.get('gps_updates_count')),
            total_food_amount=_coerce_float(payload.get('total_food_amount')),
            total_walk_distance=_coerce_float(payload.get('total_walk_distance')),
            total_walk_time=_coerce_int(payload.get('total_walk_time')),
            total_calories_burned=_coerce_float(payload.get('total_calories_burned')),
            last_feeding=cls._parse_datetime(payload.get('last_feeding')),
            last_walk=cls._parse_datetime(payload.get('last_walk')),
            last_health_event=cls._parse_datetime(payload.get('last_health_event')),
        )

    def as_dict(self) -> DailyStatsPayload:
        """Serialize the statistics for storage."""

        return {
            'date': dt_util.as_utc(self.date).isoformat(),
            'feedings_count': self.feedings_count,
            'walks_count': self.walks_count,
            'health_logs_count': self.health_logs_count,
            'gps_updates_count': self.gps_updates_count,
            'total_food_amount': self.total_food_amount,
            'total_walk_distance': self.total_walk_distance,
            'total_walk_time': self.total_walk_time,
            'total_calories_burned': self.total_calories_burned,
            'last_feeding': self.last_feeding.isoformat()
            if self.last_feeding
            else None,
            'last_walk': self.last_walk.isoformat() if self.last_walk else None,
            'last_health_event': self.last_health_event.isoformat()
            if self.last_health_event
            else None,
        }

    def reset(self, *, preserve_date: bool = True) -> None:
        """Reset all counters, optionally keeping the current date."""

        if not preserve_date:
            self.date = dt_util.utcnow()
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

    def register_feeding(self, portion_size: float, timestamp: datetime | None) -> None:
        """Record a feeding event in the aggregate counters."""

        self.feedings_count += 1
        if portion_size > 0:
            self.total_food_amount += portion_size
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_feeding = parsed

    def register_walk(
        self,
        duration: int | None,
        distance: float | None,
        timestamp: datetime | None,
    ) -> None:
        """Record a walk event in the aggregate counters."""

        self.walks_count += 1
        if duration:
            self.total_walk_time += int(duration)
        if distance:
            self.total_walk_distance += float(distance)
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_walk = parsed

    def register_health_event(self, timestamp: datetime | None) -> None:
        """Record a health log entry in the aggregate counters."""

        self.health_logs_count += 1
        parsed = self._parse_datetime(timestamp)
        if parsed is not None:
            self.last_health_event = parsed

    def register_gps_update(self) -> None:
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
    """

    meal_type: str
    portion_size: float
    food_type: str
    timestamp: datetime
    notes: str = ''
    logged_by: str = ''
    calories: float | None = None
    automatic: bool = False

    def __post_init__(self) -> None:
        """Validate feeding data after initialization.

        Performs comprehensive validation including meal type validation,
        food type validation, and numerical constraint checking to ensure
        data integrity throughout the system.

        Raises:
            ValueError: If any validation constraint is violated
        """
        if self.meal_type not in VALID_MEAL_TYPES:
            raise ValueError(f"Invalid meal type: {self.meal_type}")
        if self.food_type not in VALID_FOOD_TYPES:
            raise ValueError(f"Invalid food type: {self.food_type}")
        if self.portion_size < 0:
            raise ValueError('Portion size cannot be negative')
        if self.calories is not None and self.calories < 0:
            raise ValueError('Calories cannot be negative')


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
    """

    start_time: datetime
    end_time: datetime | None = None
    duration: int | None = None  # seconds
    distance: float | None = None  # meters
    route: list[WalkRoutePoint] = field(default_factory=list)
    label: str = ''
    location: str = ''
    notes: str = ''
    rating: int = 0
    started_by: str = ''
    ended_by: str = ''
    weather: str = ''
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Validate walk data after initialization.

        Ensures logical consistency in walk data including time relationships,
        rating constraints, and numerical validity.

        Raises:
            ValueError: If validation constraints are violated
        """
        if self.rating < 0 or self.rating > 10:
            raise ValueError('Rating must be between 0 and 10')
        if self.duration is not None and self.duration < 0:
            raise ValueError('Duration cannot be negative')
        if self.distance is not None and self.distance < 0:
            raise ValueError('Distance cannot be negative')
        if self.end_time and self.end_time < self.start_time:
            raise ValueError('End time cannot be before start time')


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
    """

    dog_id: str
    timestamp: str | None = None
    metrics: JSONMutableMapping = field(default_factory=dict)

    @classmethod
    def from_raw(
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
        event_data.pop('timestamp', None)
        raw_timestamp = payload.get('timestamp')
        event_timestamp = raw_timestamp if isinstance(raw_timestamp, str) else None
        if isinstance(raw_timestamp, datetime):
            event_timestamp = raw_timestamp.isoformat()
        if event_timestamp is None:
            event_timestamp = timestamp

        return cls(dog_id=dog_id, timestamp=event_timestamp, metrics=event_data)

    @classmethod
    def from_storage(cls, dog_id: str, payload: JSONDateMapping) -> HealthEvent:
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

    def as_dict(self) -> JSONMutableMapping:
        """Return a storage-friendly representation of the health event.

        Serializes the health event into a dictionary format suitable for
        persistent storage while preserving all event data and metadata.

        Returns:
            Dictionary representation suitable for storage
        """
        payload = cast(JSONMutableMapping, dict(self.metrics))
        if self.timestamp is not None:
            payload['timestamp'] = self.timestamp
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
    """

    dog_id: str
    action: str | None = None
    session_id: str | None = None
    timestamp: str | None = None
    details: JSONMutableMapping = field(default_factory=dict)

    @classmethod
    def from_raw(
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
        raw_timestamp = event_data.pop('timestamp', None)
        timestamp_value = raw_timestamp if isinstance(raw_timestamp, str) else None
        if isinstance(raw_timestamp, datetime):
            timestamp_value = raw_timestamp.isoformat()
        raw_action = event_data.pop('action', None)
        action = raw_action if isinstance(raw_action, str) else None
        raw_session = event_data.pop('session_id', None)
        session = raw_session if isinstance(raw_session, str) else None
        event_timestamp = timestamp_value if timestamp_value is not None else timestamp

        return cls(
            dog_id=dog_id,
            action=action,
            session_id=session,
            timestamp=event_timestamp,
            details=event_data,
        )

    @classmethod
    def from_storage(cls, dog_id: str, payload: JSONDateMapping) -> WalkEvent:
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

    def as_dict(self) -> JSONMutableMapping:
        """Return a storage-friendly representation of the walk event.

        Serializes the walk event into a dictionary format optimized for
        persistent storage while maintaining session tracking capabilities.

        Returns:
            Dictionary representation suitable for storage and transmission
        """
        payload = cast(JSONMutableMapping, dict(self.details))
        if self.action is not None:
            payload['action'] = self.action
        if self.session_id is not None:
            payload['session_id'] = self.session_id
        if self.timestamp is not None:
            payload['timestamp'] = self.timestamp
        return payload

    def merge(self, payload: JSONDateMapping, timestamp: str | None = None) -> None:
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
        if 'action' in updates:
            raw_action = updates.pop('action')
            if isinstance(raw_action, str):
                self.action = raw_action
        if 'session_id' in updates:
            raw_session = updates.pop('session_id')
            if isinstance(raw_session, str):
                self.session_id = raw_session
        if 'timestamp' in updates:
            raw_timestamp = updates.pop('timestamp')
            if isinstance(raw_timestamp, str):
                self.timestamp = raw_timestamp
        elif timestamp and self.timestamp is None:
            self.timestamp = timestamp

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
    """

    timestamp: datetime
    weight: float | None = None
    temperature: float | None = None
    mood: str = ''
    activity_level: str = ''
    health_status: str = ''
    symptoms: str = ''
    medication: JSONMutableMapping | None = None
    note: str = ''
    logged_by: str = ''
    heart_rate: int | None = None
    respiratory_rate: int | None = None

    def __post_init__(self) -> None:
        """Validate health data against veterinary standards.

        Performs comprehensive validation of all health parameters against
        veterinary standards and physiological constraints to ensure data
        quality for health analysis and trend tracking.

        Raises:
            ValueError: If any parameter is outside acceptable ranges
        """
        if self.mood and self.mood not in VALID_MOOD_OPTIONS:
            raise ValueError(f"Invalid mood: {self.mood}")
        if self.activity_level and self.activity_level not in VALID_ACTIVITY_LEVELS:
            raise ValueError(f"Invalid activity level: {self.activity_level}")
        if self.health_status and self.health_status not in VALID_HEALTH_STATUS:
            raise ValueError(f"Invalid health status: {self.health_status}")
        if self.weight is not None and (self.weight <= 0 or self.weight > 200):
            raise ValueError('Weight must be between 0 and 200 kg')
        if self.temperature is not None and (
            self.temperature < 35 or self.temperature > 45
        ):
            raise ValueError('Temperature must be between 35 and 45 degrees Celsius')
        if self.heart_rate is not None and (
            self.heart_rate < 50 or self.heart_rate > 250
        ):
            raise ValueError('Heart rate must be between 50 and 250 bpm')


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
    """

    latitude: float
    longitude: float
    accuracy: float | None = None
    altitude: float | None = None
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    source: str = ''
    battery_level: int | None = None
    signal_strength: int | None = None

    def __post_init__(self) -> None:
        """Validate GPS coordinates and device parameters.

        Ensures GPS coordinates are within valid Earth coordinate ranges and
        device parameters are within acceptable bounds for reliable tracking.

        Raises:
            ValueError: If coordinates or parameters are invalid
        """
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.accuracy is not None and self.accuracy < 0:
            raise ValueError('Accuracy cannot be negative')
        if self.battery_level is not None and not (0 <= self.battery_level <= 100):
            raise ValueError('Battery level must be between 0 and 100')
        if self.signal_strength is not None and not (0 <= self.signal_strength <= 100):
            raise ValueError('Signal strength must be between 0 and 100')


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
    """
    return f"pawcontrol_{dog_id}_{module}_{entity_type}".lower()


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
    """
    size_ranges = {
        'toy': (1.0, 6.0),  # Chihuahua, Yorkshire Terrier
        'small': (4.0, 15.0),  # Jack Russell, Beagle
        'medium': (8.0, 30.0),  # Border Collie, Bulldog
        'large': (22.0, 50.0),  # Labrador, German Shepherd
        'giant': (35.0, 90.0),  # Great Dane, Saint Bernard
    }

    if size not in size_ranges:
        return True  # Unknown size category, skip validation

    min_weight, max_weight = size_ranges[size]
    return min_weight <= weight <= max_weight


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
    """
    import math

    # Base metabolic rate: 70 * (weight in kg)^0.75
    base_calories = 70 * math.pow(weight, 0.75)

    # Activity level multipliers based on veterinary guidelines
    activity_multipliers = {
        'very_low': 1.2,  # Sedentary, minimal exercise
        'low': 1.4,  # Light exercise, short walks
        'normal': 1.6,  # Moderate exercise, regular walks
        'high': 1.8,  # Active exercise, long walks/runs
        'very_high': 2.0,  # Very active, working dogs, intense exercise
    }

    multiplier = activity_multipliers.get(activity_level, 1.6)

    # Age-based adjustments for metabolic differences
    if age < 1:
        # Puppies have higher metabolic needs for growth
        multiplier *= 2.0
    elif age > 7:
        # Senior dogs typically have lower metabolic needs
        multiplier *= 0.9

    return int(base_calories * multiplier)


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
    """
    if not isinstance(config, dict):
        return False

    # Validate required fields with type and content checking
    required_fields = ['dog_id', 'dog_name']
    for required_field in required_fields:
        if (
            required_field not in config
            or not isinstance(config[required_field], str)
            or not config[required_field].strip()
        ):
            return False

    # Validate optional fields with proper type and range checking
    if 'dog_age' in config and (
        not isinstance(config['dog_age'], int)
        or config['dog_age'] < 0
        or config['dog_age'] > 30
    ):
        return False

    if 'dog_weight' in config and (
        not is_number(config['dog_weight']) or float(config['dog_weight']) <= 0
    ):
        return False

    if 'dog_size' in config and config['dog_size'] not in VALID_DOG_SIZES:
        return False

    # Validate modules configuration if present
    if 'modules' in config:
        modules = config['modules']
        if not isinstance(modules, dict):
            return False
        if any(not isinstance(enabled, bool) for enabled in modules.values()):
            return False

    return True


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
    """
    if not isinstance(location, dict):
        return False

    # Validate required coordinates with Earth bounds checking
    for coord, limits in [('latitude', (-90, 90)), ('longitude', (-180, 180))]:
        if coord not in location:
            return False
        value = location[coord]
        if not is_number(value):
            return False
        numeric_value = float(value)
        if not (limits[0] <= numeric_value <= limits[1]):
            return False

    # Validate optional fields with appropriate constraints
    if 'accuracy' in location and (
        not is_number(location['accuracy']) or float(location['accuracy']) < 0
    ):
        return False

    if 'battery_level' in location:
        battery = location['battery_level']
        if battery is not None and (
            not isinstance(battery, int) or not (0 <= battery <= 100)
        ):
            return False

    return True


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
    """
    if not isinstance(data, dict):
        return False

    # Validate required fields with frozenset lookup for performance
    if 'meal_type' not in data or data['meal_type'] not in VALID_MEAL_TYPES:
        return False

    if 'portion_size' not in data:
        return False

    portion = data['portion_size']
    if not is_number(portion) or float(portion) < 0:
        return False

    # Validate optional fields with appropriate constraints
    if 'food_type' in data and data['food_type'] not in VALID_FOOD_TYPES:
        return False

    if 'calories' in data:
        calories = data['calories']
        if calories is not None and (not is_number(calories) or float(calories) < 0):
            return False

    return True


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
    """
    if not isinstance(data, dict):
        return False

    # Validate optional fields with frozenset lookups for performance
    if 'mood' in data and data['mood'] and data['mood'] not in VALID_MOOD_OPTIONS:
        return False

    if (
        'activity_level' in data
        and data['activity_level']
        and data['activity_level'] not in VALID_ACTIVITY_LEVELS
    ):
        return False

    if (
        'health_status' in data
        and data['health_status']
        and data['health_status'] not in VALID_HEALTH_STATUS
    ):
        return False

    # Validate physiological measurements with veterinary standards
    if 'weight' in data:
        weight = data['weight']
        if weight is not None and (
            not is_number(weight) or float(weight) <= 0 or float(weight) > 200
        ):
            return False

    if 'temperature' in data:
        temp = data['temperature']
        if temp is not None and (
            not is_number(temp) or float(temp) < 35 or float(temp) > 45
        ):
            return False

    return True


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
    """
    if not isinstance(data, dict):
        return False

    # Validate required content fields
    required_fields = ['title', 'message']
    for required_field in required_fields:
        if (
            required_field not in data
            or not isinstance(data[required_field], str)
            or not data[required_field].strip()
        ):
            return False

    # Validate optional fields with frozenset lookups for performance
    if 'priority' in data and data['priority'] not in VALID_NOTIFICATION_PRIORITIES:
        return False

    return not (
        'channel' in data and data['channel'] not in VALID_NOTIFICATION_CHANNELS
    )


# geminivorschlag:
class DogModule(TypedDict):
    id: str
    name: str
    enabled: bool


class DogConfig(TypedDict):
    dog_id: str
    dog_name: str
    modules: DogModulesConfig
    # Add other fields as needed


# Immutable constant for Reauth placeholders
REAUTH_PLACEHOLDERS: Final = MappingProxyType(
    {
        'integration_name': 'PawControl',
        'dogs_count': '0',
        'current_profile': 'standard',
        'health_status': 'Unknown',
    }
)
