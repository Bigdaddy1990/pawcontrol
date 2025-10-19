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

from asyncio import Task
from collections.abc import Callable, Iterator, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    Literal,
    NotRequired,
    Required,
    TypedDict,
    cast,
)

from .compat import ConfigEntry
from .const import (
    CONF_BREAKFAST_TIME,
    CONF_DAILY_FOOD_AMOUNT,
    CONF_DINNER_TIME,
    CONF_DOOR_SENSOR,
    CONF_DOOR_SENSOR_SETTINGS,
    CONF_FOOD_TYPE,
    CONF_LUNCH_TIME,
    CONF_MEALS_PER_DAY,
    CONF_QUIET_END,
    CONF_QUIET_HOURS,
    CONF_QUIET_START,
    CONF_REMINDER_REPEAT_MIN,
)

try:
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(UTC)

    dt_util = _DateTimeModule()

from .utils import is_number

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

# OPTIMIZE: Use literal constants for performance - frozensets provide O(1) lookups
# and are immutable, preventing accidental modification while ensuring fast validation

VALID_MEAL_TYPES: Final[frozenset[str]] = frozenset(
    ["breakfast", "lunch", "dinner", "snack"]
)
"""Valid meal types for feeding tracking.

This frozenset defines the acceptable meal types that can be recorded in the system.
Using frozenset provides O(1) lookup performance for validation while preventing
accidental modification of the valid values.
"""

VALID_FOOD_TYPES: Final[frozenset[str]] = frozenset(
    ["dry_food", "wet_food", "barf", "home_cooked", "mixed"]
)
"""Valid food types for feeding management.

Defines the types of food that can be tracked in feeding records. This includes
commercial food types and home-prepared options for comprehensive diet tracking.
"""

VALID_DOG_SIZES: Final[frozenset[str]] = frozenset(
    ["toy", "small", "medium", "large", "giant"]
)
"""Valid dog size categories for breed classification.

Size categories are used throughout the system for portion calculation, exercise
recommendations, and health monitoring. These align with standard veterinary
size classifications.
"""

VALID_HEALTH_STATUS: Final[frozenset[str]] = frozenset(
    ["excellent", "very_good", "good", "normal", "unwell", "sick"]
)
"""Valid health status levels for health monitoring.

These status levels provide a standardized way to track overall dog health,
from excellent condition to requiring medical attention.
"""

VALID_MOOD_OPTIONS: Final[frozenset[str]] = frozenset(
    ["happy", "neutral", "content", "normal", "sad", "angry", "anxious", "tired"]
)
"""Valid mood states for behavioral tracking.

Mood tracking helps identify patterns in behavior and potential health issues
that may affect a dog's emotional well-being.
"""

VALID_ACTIVITY_LEVELS: Final[frozenset[str]] = frozenset(
    ["very_low", "low", "normal", "high", "very_high"]
)
"""Valid activity levels for exercise and health monitoring.

Activity levels are used for calculating appropriate exercise needs, portion sizes,
and overall health assessments based on a dog's typical energy expenditure.
"""

VALID_GEOFENCE_TYPES: Final[frozenset[str]] = frozenset(
    ["safe_zone", "restricted_area", "point_of_interest"]
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
    ]
)
"""Valid GPS data sources for location tracking.

Supports multiple GPS input methods to accommodate different hardware setups
and integration scenarios with various tracking devices and services.
"""

VALID_NOTIFICATION_PRIORITIES: Final[frozenset[str]] = frozenset(
    ["low", "normal", "high", "urgent"]
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

MODULE_TOGGLE_FLOW_FLAGS: Final[tuple[tuple[str, ModuleToggleKey], ...]] = (
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

DEFAULT_FEEDING_SCHEDULE: Final[tuple[str, ...]] = ("10:00:00", "15:00:00", "20:00:00")


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


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Return a boolean flag while tolerating common string/int representations."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        return text in {"1", "true", "yes", "y", "on", "enabled"}
    return bool(value)


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


def _project_modules_mapping(config: Mapping[str, Any]) -> dict[str, bool]:
    """Return a stable ``dict[str, bool]`` projection for module toggles."""

    mapping: dict[str, bool] = {}
    for key_literal in MODULE_TOGGLE_KEYS:
        key = cast(str, key_literal)
        mapping[key] = bool(config.get(key_literal, False))
    return mapping


def dog_modules_projection_from_flow_input(
    user_input: Mapping[str, Any],
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
    user_input: Mapping[str, Any],
    *,
    existing: DogModulesConfig | None = None,
) -> DogModulesConfig:
    """Return a :class:`DogModulesConfig` built from config-flow toggles."""

    return dog_modules_projection_from_flow_input(user_input, existing=existing).config


def ensure_dog_modules_projection(
    data: Mapping[str, Any] | DogModulesProjection,
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
    data: Mapping[str, Any] | DogModulesProjection,
) -> DogModulesConfig:
    """Extract a :class:`DogModulesConfig` from supported module payloads."""

    return ensure_dog_modules_projection(data).config


def _is_modules_projection_like(value: Any) -> bool:
    """Return ``True`` when ``value`` resembles a modules projection payload."""

    if isinstance(value, DogModulesProjection):
        return True

    return hasattr(value, "config") and hasattr(value, "mapping")


def coerce_dog_modules_config(
    payload: Mapping[str, Any] | DogModulesProjection | None,
) -> DogModulesConfig:
    """Return a defensive ``DogModulesConfig`` copy tolerant of projections."""

    if _is_modules_projection_like(payload):
        config_attr = getattr(payload, "config", None)
        if isinstance(config_attr, Mapping):
            return cast(DogModulesConfig, dict(config_attr))

    if isinstance(payload, Mapping):
        config = ensure_dog_modules_config(payload)
        return cast(DogModulesConfig, dict(config))

    return cast(DogModulesConfig, {})


def ensure_dog_modules_mapping(
    data: Mapping[str, Any] | DogModulesProjection,
) -> dict[str, bool]:
    """Return a ``dict[str, bool]`` projection from ``data``."""

    return ensure_dog_modules_projection(data).mapping


def dog_feeding_config_from_flow(user_input: Mapping[str, Any]) -> DogFeedingConfig:
    """Build a :class:`DogFeedingConfig` structure from flow input data."""

    meals_per_day = max(1, _coerce_int(user_input.get(CONF_MEALS_PER_DAY), default=2))
    daily_amount = _coerce_float(user_input.get(CONF_DAILY_FOOD_AMOUNT), default=500.0)
    portion_size = daily_amount / meals_per_day if meals_per_day else 0.0

    feeding_config: dict[FeedingConfigKey, Any] = {
        "meals_per_day": meals_per_day,
        "daily_food_amount": daily_amount,
        "portion_size": portion_size,
        "food_type": _coerce_str(user_input.get(CONF_FOOD_TYPE), default="dry_food"),
        "feeding_schedule": _coerce_str(
            user_input.get("feeding_schedule"), default="flexible"
        ),
        "enable_reminders": _coerce_bool(
            user_input.get("enable_reminders"), default=True
        ),
        "reminder_minutes_before": _coerce_int(
            user_input.get("reminder_minutes_before"), default=15
        ),
    }

    if _coerce_bool(user_input.get("breakfast_enabled"), default=meals_per_day >= 1):
        feeding_config["breakfast_time"] = _coerce_str(
            user_input.get(CONF_BREAKFAST_TIME), default="07:00:00"
        )

    if _coerce_bool(user_input.get("lunch_enabled"), default=meals_per_day >= 3):
        feeding_config["lunch_time"] = _coerce_str(
            user_input.get(CONF_LUNCH_TIME), default="12:00:00"
        )

    if _coerce_bool(user_input.get("dinner_enabled"), default=meals_per_day >= 2):
        feeding_config["dinner_time"] = _coerce_str(
            user_input.get(CONF_DINNER_TIME), default="18:00:00"
        )

    if _coerce_bool(user_input.get("snacks_enabled"), default=False):
        feeding_config["snack_times"] = list(DEFAULT_FEEDING_SCHEDULE)

    return cast(DogFeedingConfig, feeding_config)


class DogGPSConfig(TypedDict, total=False):
    """GPS configuration captured during the dog setup flow."""

    gps_source: str
    gps_update_interval: int
    gps_accuracy_filter: float | int
    enable_geofencing: bool
    home_zone_radius: int | float


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


class NotificationOptions(TypedDict, total=False):
    """Structured notification preferences stored in config entry options."""

    quiet_hours: bool
    quiet_start: str
    quiet_end: str
    reminder_repeat_min: int
    priority_notifications: bool
    mobile_notifications: bool


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


def ensure_notification_options(
    value: Mapping[str, Any],
    /,
    *,
    defaults: Mapping[str, Any] | None = None,
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
            if lowered in {"true", "yes", "on", "1"}:
                return True
            if lowered in {"false", "no", "off", "0"}:
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
            interval = max(5, min(180, interval))
            return interval
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
    _apply("priority_notifications", NOTIFICATION_PRIORITY_FIELD, _coerce_bool)
    _apply("mobile_notifications", NOTIFICATION_MOBILE_FIELD, _coerce_bool)

    return options


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
    notification_threshold: Literal["low", "moderate", "high"]


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
    performance_mode: Literal["minimal", "balanced", "full"]


class DashboardOptions(TypedDict, total=False):
    """Dashboard rendering preferences for the integration."""

    show_statistics: bool
    show_alerts: bool
    compact_mode: bool
    show_maps: bool


class AdvancedOptions(TypedDict, total=False):
    """Advanced diagnostics and integration toggles stored on the entry."""

    performance_mode: Literal["minimal", "balanced", "full"]
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
    performance_mode: Literal["minimal", "balanced", "full"]
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


class ConfigFlowDiscoveryData(TypedDict, total=False):
    """Metadata captured from config flow discovery sources."""

    source: Literal["zeroconf", "dhcp", "usb", "bluetooth", "import", "reauth"]
    hostname: str
    host: str
    port: int
    ip: str
    macaddress: str
    properties: dict[str, Any]
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


class ConfigFlowGlobalSettings(TypedDict, total=False):
    """Global configuration captured during the setup flow."""

    performance_mode: Literal["minimal", "balanced", "full"]
    enable_analytics: bool
    enable_cloud_backup: bool
    data_retention_days: int
    debug_logging: bool


class DashboardSetupConfig(TypedDict, total=False):
    """Dashboard preferences collected during setup before persistence."""

    dashboard_enabled: bool
    dashboard_auto_create: bool
    dashboard_per_dog: bool
    dashboard_theme: str
    dashboard_mode: str
    dashboard_template: str
    show_statistics: bool
    show_maps: bool
    show_health_charts: bool
    show_feeding_schedule: bool
    show_alerts: bool
    compact_mode: bool
    auto_refresh: bool
    refresh_interval: int


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


class DogValidationResult(TypedDict):
    """Validation result payload for dog configuration forms."""

    valid: bool
    errors: dict[str, str]


class DogValidationCacheEntry(TypedDict):
    """Cached validation result metadata for config and options flows."""

    result: DogValidationResult | DogSetupStepInput | None
    cached_at: float
    state_signature: NotRequired[str]


class DogSetupStepInput(TypedDict, total=False):
    """Minimal dog setup fields collected during the primary form."""

    dog_id: str
    dog_name: str
    dog_breed: str | None
    dog_age: int | float | None
    dog_weight: float | int | None
    dog_size: str | None


class HelperManagerStats(TypedDict):
    """Summary statistics reported by the helper manager diagnostics."""

    helpers: int
    dogs: int
    managed_entities: int


class HelperManagerSnapshot(TypedDict):
    """Snapshot payload describing managed helper assignments."""

    per_dog: dict[str, int]
    entity_domains: dict[str, int]


DogValidationCache = dict[str, DogValidationCacheEntry]

Timestamp = datetime
"""Type alias for datetime objects used as timestamps.

Standardizes timestamp handling across the integration with proper timezone
awareness through Home Assistant's utility functions.
"""

ServiceData = dict[str, Any]
"""Type alias for Home Assistant service call data.

Represents the data payload structure used in Home Assistant service calls,
providing type hints for service-related functionality.
"""

ConfigData = dict[str, Any]
"""Type alias for general configuration data structures.

Used for various configuration contexts where a flexible dictionary structure
is needed with proper type hinting.
"""


class FeedingModulePayload(TypedDict, total=False):
    """Typed payload exposed by the feeding coordinator module."""

    status: Required[str]
    last_feeding: Any | None
    feedings_today: dict[str, Any]
    total_feedings_today: int
    daily_amount_consumed: float
    daily_portions: int
    feeding_schedule: list[Any]
    daily_calorie_target: float | None
    total_calories_today: float | None
    portion_adjustment_factor: float | None
    health_feeding_status: str
    medication_with_meals: bool
    health_aware_feeding: bool
    health_conditions: list[Any]
    daily_activity_level: str | None
    weight_goal: Any
    weight_goal_progress: Any
    health_emergency: bool
    emergency_mode: Any
    health_summary: dict[str, Any]
    message: NotRequired[str]


class WalkModulePayload(TypedDict, total=False):
    """Telemetry returned by the walk adapter."""

    status: Required[str]
    current_walk: dict[str, Any] | None
    last_walk: dict[str, Any] | None
    daily_walks: int
    total_distance: float
    message: NotRequired[str]


class GPSModulePayload(TypedDict, total=False):
    """GPS metrics surfaced through the GPS adapter."""

    status: Required[str]
    latitude: float | None
    longitude: float | None
    accuracy: float | None
    last_update: str | None
    source: str | None
    active_route: dict[str, Any] | None


class GeofencingModulePayload(TypedDict, total=False):
    """Structured geofence payload for coordinator consumers."""

    status: Required[str]
    zones_configured: int
    zone_status: dict[str, Any]
    current_location: dict[str, Any] | None
    safe_zone_breaches: int
    last_update: Any
    message: NotRequired[str]
    error: NotRequired[str]


class HealthModulePayload(TypedDict, total=False):
    """Combined health telemetry exposed by the health adapter."""

    status: Required[str]
    weight: float | None
    ideal_weight: float | None
    last_vet_visit: str | None
    medications: list[Any]
    health_alerts: list[Any]
    life_stage: str | None
    activity_level: str | None
    body_condition_score: float | int | None
    health_conditions: list[Any]
    emergency: dict[str, Any]
    medication: dict[str, Any]
    health_status: str | None
    daily_calorie_target: float | None
    total_calories_today: float | None
    weight_goal_progress: Any
    weight_goal: Any


class WeatherModulePayload(TypedDict, total=False):
    """Weather-driven health insights returned by the weather adapter."""

    status: Required[str]
    health_score: float | int | None
    alerts: list[Any]
    recommendations: list[Any]
    conditions: dict[str, Any]
    message: NotRequired[str]


class GardenModulePayload(TypedDict, total=False):
    """Garden telemetry surfaced to coordinators."""

    status: Required[str]
    message: NotRequired[str]
    sessions: list[Any]
    recent_activity: list[Any]
    stats: dict[str, Any]


ModuleAdapterPayload = (
    FeedingModulePayload
    | WalkModulePayload
    | GPSModulePayload
    | GeofencingModulePayload
    | HealthModulePayload
    | WeatherModulePayload
    | GardenModulePayload
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
    per_module: dict[str, Any]
    per_dog: dict[str, Any]
    per_dog_helpers: dict[str, Any]
    entity_domains: dict[str, int]
    errors: list[str]
    summary: dict[str, Any]
    snapshots: list[dict[str, Any]]
    created_entities: list[str]
    detection_stats: dict[str, Any]
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


@dataclass(slots=True)
class CacheDiagnosticsSnapshot(Mapping[str, Any]):
    """Structured diagnostics snapshot returned by cache monitors."""

    stats: dict[str, Any] | None = None
    diagnostics: CacheDiagnosticsMetadata | None = None
    snapshot: dict[str, Any] | None = None
    error: str | None = None
    repair_summary: CacheRepairAggregate | None = None

    def to_mapping(self) -> dict[str, Any]:
        """Return a mapping representation for downstream consumers."""

        payload: dict[str, Any] = {}
        if self.stats is not None:
            payload["stats"] = dict(self.stats)
        if self.diagnostics is not None:
            payload["diagnostics"] = dict(self.diagnostics)
        if self.snapshot is not None:
            payload["snapshot"] = dict(self.snapshot)
        if self.error is not None:
            payload["error"] = self.error
        if isinstance(self.repair_summary, CacheRepairAggregate):
            payload["repair_summary"] = self.repair_summary.to_mapping()
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CacheDiagnosticsSnapshot:
        """Create a snapshot payload from an arbitrary mapping."""

        stats = payload.get("stats")
        diagnostics = payload.get("diagnostics")
        snapshot = payload.get("snapshot")
        error = payload.get("error")
        repair_summary_payload = payload.get("repair_summary")

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

    def __getitem__(self, key: str) -> Any:
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
            payload["overall_hit_rate"] = round(self.overall_hit_rate, 2)
        return payload


@dataclass(slots=True)
class CacheRepairAggregate(Mapping[str, Any]):
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

    def to_mapping(self) -> dict[str, Any]:
        """Return a mapping representation for Home Assistant repairs."""

        payload: dict[str, Any] = {
            "total_caches": self.total_caches,
            "anomaly_count": self.anomaly_count,
            "severity": self.severity,
            "generated_at": self.generated_at,
        }
        if self.caches_with_errors:
            payload["caches_with_errors"] = list(self.caches_with_errors)
        if self.caches_with_expired_entries:
            payload["caches_with_expired_entries"] = list(
                self.caches_with_expired_entries
            )
        if self.caches_with_pending_expired_entries:
            payload["caches_with_pending_expired_entries"] = list(
                self.caches_with_pending_expired_entries
            )
        if self.caches_with_override_flags:
            payload["caches_with_override_flags"] = list(
                self.caches_with_override_flags
            )
        if self.caches_with_low_hit_rate:
            payload["caches_with_low_hit_rate"] = list(self.caches_with_low_hit_rate)
        if self.totals is not None:
            payload["totals"] = self.totals.as_dict()
        if self.issues:
            payload["issues"] = list(self.issues)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CacheRepairAggregate:
        """Return a :class:`CacheRepairAggregate` constructed from a mapping."""

        totals_payload = payload.get("totals")
        totals = None
        if isinstance(totals_payload, Mapping):
            overall_hit_rate_value = totals_payload.get("overall_hit_rate")
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
                entries=int(totals_payload.get("entries", 0) or 0),
                hits=int(totals_payload.get("hits", 0) or 0),
                misses=int(totals_payload.get("misses", 0) or 0),
                expired_entries=int(totals_payload.get("expired_entries", 0) or 0),
                expired_via_override=int(
                    totals_payload.get("expired_via_override", 0) or 0
                ),
                pending_expired_entries=int(
                    totals_payload.get("pending_expired_entries", 0) or 0
                ),
                pending_override_candidates=int(
                    totals_payload.get("pending_override_candidates", 0) or 0
                ),
                active_override_flags=int(
                    totals_payload.get("active_override_flags", 0) or 0
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

        issues_payload = payload.get("issues")
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
            total_caches=int(payload.get("total_caches", 0) or 0),
            anomaly_count=int(payload.get("anomaly_count", 0) or 0),
            severity=str(payload.get("severity", "unknown")),
            generated_at=str(payload.get("generated_at", "")),
            caches_with_errors=_string_list("caches_with_errors"),
            caches_with_expired_entries=_string_list("caches_with_expired_entries"),
            caches_with_pending_expired_entries=_string_list(
                "caches_with_pending_expired_entries"
            ),
            caches_with_override_flags=_string_list("caches_with_override_flags"),
            caches_with_low_hit_rate=_string_list("caches_with_low_hit_rate"),
            totals=totals,
            issues=issues,
        )

    def __getitem__(self, key: str) -> Any:
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
    metadata: NotRequired[dict[str, Any]]


class MaintenanceExecutionResult(TypedDict, total=False):
    """Structured payload appended after running maintenance utilities."""

    task: Required[str]
    status: Required[Literal["success", "error"]]
    recorded_at: Required[str]
    message: NotRequired[str]
    diagnostics: NotRequired[MaintenanceExecutionDiagnostics]
    details: NotRequired[dict[str, Any]]


class ServiceExecutionDiagnostics(TypedDict, total=False):
    """Diagnostics metadata captured while executing a service handler."""

    cache: NotRequired[CacheDiagnosticsCapture]
    metadata: NotRequired[dict[str, Any]]


class ServiceExecutionResult(TypedDict, total=False):
    """Structured payload appended to runtime stats after service execution."""

    service: Required[str]
    status: Required[Literal["success", "error"]]
    dog_id: NotRequired[str]
    message: NotRequired[str]
    diagnostics: NotRequired[ServiceExecutionDiagnostics]
    details: NotRequired[dict[str, Any]]


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


class CoordinatorRejectionMetrics(TypedDict):
    """Normalised rejection counters exposed via diagnostics payloads."""

    schema_version: Literal[2]
    rejected_call_count: int
    rejection_breaker_count: int
    rejection_rate: float | None
    last_rejection_time: float | None
    last_rejection_breaker_id: str | None
    last_rejection_breaker_name: str | None


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
    discovery_info: NotRequired[ConfigFlowDiscoveryData]
    gps_config: NotRequired[DogGPSConfig]
    feeding_config: NotRequired[DogFeedingConfig]
    health_config: NotRequired[DogHealthConfig]
    door_sensor: NotRequired[str | None]
    door_sensor_settings: NotRequired[dict[str, Any]]


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
DOG_FEEDING_CONFIG_FIELD: Final[Literal["feeding_config"]] = "feeding_config"
DOG_HEALTH_CONFIG_FIELD: Final[Literal["health_config"]] = "health_config"
DOG_GPS_CONFIG_FIELD: Final[Literal["gps_config"]] = "gps_config"


def ensure_dog_config_data(data: Mapping[str, Any]) -> DogConfigData | None:
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
    if _is_modules_projection_like(modules_payload) or isinstance(
        modules_payload, Mapping
    ):
        config[DOG_MODULES_FIELD] = coerce_dog_modules_config(modules_payload)

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
            config[CONF_DOOR_SENSOR] = trimmed_sensor

    normalised_settings = _normalise_door_sensor_settings_payload(
        data.get(CONF_DOOR_SENSOR_SETTINGS)
    )
    if normalised_settings is not None:
        config[CONF_DOOR_SENSOR_SETTINGS] = normalised_settings

    return config


RawDogConfig = Mapping[str, Any] | DogConfigData


def _normalise_door_sensor_settings_payload(
    payload: Any,
) -> dict[str, Any] | None:
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

    settings_payload = asdict(settings)
    if not settings_payload:
        return None

    if settings_payload == asdict(DEFAULT_DOOR_SENSOR_SETTINGS):
        return None

    return settings_payload


def ensure_dog_options_entry(
    value: Mapping[str, Any],
    /,
    *,
    dog_id: str | None = None,
) -> DogOptionsEntry:
    """Return a normalised :class:`DogOptionsEntry` built from ``value``."""

    entry: DogOptionsEntry = {}

    raw_dog_id = value.get(DOG_ID_FIELD)
    if isinstance(raw_dog_id, str) and raw_dog_id:
        entry["dog_id"] = raw_dog_id
    elif isinstance(dog_id, str) and dog_id:
        entry["dog_id"] = dog_id

    modules_payload = value.get(DOG_MODULES_FIELD)
    if _is_modules_projection_like(modules_payload) or isinstance(
        modules_payload, Mapping
    ):
        entry["modules"] = coerce_dog_modules_config(modules_payload)

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


@dataclass
class PawControlRuntimeData:
    """Comprehensive runtime data container for the PawControl integration.

    This dataclass contains all runtime components needed by the integration
    for Bronze-targeted type safety with ConfigEntry[PawControlRuntimeData].
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

    # Enhanced runtime tracking for Bronze-targeted monitoring
    performance_stats: dict[str, Any] = field(default_factory=dict)
    error_history: list[dict[str, Any]] = field(default_factory=list)
    # PLATINUM: Optional unsubscribe callbacks for scheduler and reload listener
    daily_reset_unsub: Any = field(default=None)
    reload_unsub: Callable[[], Any] | None = None

    def as_dict(self) -> dict[str, Any]:
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
            "entity_factory": self.entity_factory,
            "entity_profile": self.entity_profile,
            "dogs": self.dogs,
            "garden_manager": self.garden_manager,
            "geofencing_manager": self.geofencing_manager,
            "script_manager": self.script_manager,
            "gps_geofence_manager": self.gps_geofence_manager,
            "door_sensor_manager": self.door_sensor_manager,
            "helper_manager": self.helper_manager,
            "device_api_client": self.device_api_client,
            "performance_stats": self.performance_stats,
            "error_history": self.error_history,
            "background_monitor_task": self.background_monitor_task,
            "daily_reset_unsub": self.daily_reset_unsub,
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


# PLATINUM: Custom ConfigEntry type for PawControl integrations
type PawControlConfigEntry = ConfigEntry[PawControlRuntimeData]
"""Type alias for PawControl-specific config entries.

By parameterising ``ConfigEntry`` with :class:`PawControlRuntimeData` we provide
Home Assistant with the precise runtime payload type exposed by this
integration.  This keeps call sites expressive, improves type-checker feedback,
and remains compatible with forward-looking changes to Home Assistant's
``ConfigEntry`` generics.
"""


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
    def from_dict(cls, payload: Mapping[str, Any]) -> DailyStats:
        """Deserialize daily statistics from a dictionary structure."""

        raw_date = payload.get("date")
        date_value = cls._parse_datetime(raw_date) or dt_util.utcnow()
        return cls(
            date=date_value,
            feedings_count=int(payload.get("feedings_count", 0)),
            walks_count=int(payload.get("walks_count", 0)),
            health_logs_count=int(payload.get("health_logs_count", 0)),
            gps_updates_count=int(payload.get("gps_updates_count", 0)),
            total_food_amount=float(payload.get("total_food_amount", 0.0)),
            total_walk_distance=float(payload.get("total_walk_distance", 0.0)),
            total_walk_time=int(payload.get("total_walk_time", 0)),
            total_calories_burned=float(payload.get("total_calories_burned", 0.0)),
            last_feeding=cls._parse_datetime(payload.get("last_feeding")),
            last_walk=cls._parse_datetime(payload.get("last_walk")),
            last_health_event=cls._parse_datetime(payload.get("last_health_event")),
        )

    def as_dict(self) -> dict[str, Any]:
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
            "last_feeding": self.last_feeding.isoformat()
            if self.last_feeding
            else None,
            "last_walk": self.last_walk.isoformat() if self.last_walk else None,
            "last_health_event": self.last_health_event.isoformat()
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
    notes: str = ""
    logged_by: str = ""
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
            raise ValueError("Portion size cannot be negative")
        if self.calories is not None and self.calories < 0:
            raise ValueError("Calories cannot be negative")


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
    route: list[dict[str, float]] = field(default_factory=list)
    label: str = ""
    location: str = ""
    notes: str = ""
    rating: int = 0
    started_by: str = ""
    ended_by: str = ""
    weather: str = ""
    temperature: float | None = None

    def __post_init__(self) -> None:
        """Validate walk data after initialization.

        Ensures logical consistency in walk data including time relationships,
        rating constraints, and numerical validity.

        Raises:
            ValueError: If validation constraints are violated
        """
        if self.rating < 0 or self.rating > 10:
            raise ValueError("Rating must be between 0 and 10")
        if self.duration is not None and self.duration < 0:
            raise ValueError("Duration cannot be negative")
        if self.distance is not None and self.distance < 0:
            raise ValueError("Distance cannot be negative")
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("End time cannot be before start time")


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
    metrics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        dog_id: str,
        payload: Mapping[str, Any],
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
        event_data = dict(payload)
        event_timestamp = event_data.pop("timestamp", None) or timestamp
        if isinstance(event_timestamp, datetime):
            event_timestamp = event_timestamp.isoformat()

        return cls(dog_id=dog_id, timestamp=event_timestamp, metrics=event_data)

    @classmethod
    def from_storage(cls, dog_id: str, payload: Mapping[str, Any]) -> HealthEvent:
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

    def as_dict(self) -> dict[str, Any]:
        """Return a storage-friendly representation of the health event.

        Serializes the health event into a dictionary format suitable for
        persistent storage while preserving all event data and metadata.

        Returns:
            Dictionary representation suitable for storage
        """
        payload = dict(self.metrics)
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
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
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(
        cls,
        dog_id: str,
        payload: Mapping[str, Any],
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
        event_data = dict(payload)
        action = event_data.pop("action", None)
        session = event_data.pop("session_id", None)
        event_timestamp = event_data.pop("timestamp", None) or timestamp
        if isinstance(event_timestamp, datetime):
            event_timestamp = event_timestamp.isoformat()

        return cls(
            dog_id=dog_id,
            action=action,
            session_id=session,
            timestamp=event_timestamp,
            details=event_data,
        )

    @classmethod
    def from_storage(cls, dog_id: str, payload: Mapping[str, Any]) -> WalkEvent:
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

    def as_dict(self) -> dict[str, Any]:
        """Return a storage-friendly representation of the walk event.

        Serializes the walk event into a dictionary format optimized for
        persistent storage while maintaining session tracking capabilities.

        Returns:
            Dictionary representation suitable for storage and transmission
        """
        payload = dict(self.details)
        if self.action is not None:
            payload["action"] = self.action
        if self.session_id is not None:
            payload["session_id"] = self.session_id
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return payload

    def merge(self, payload: Mapping[str, Any], timestamp: str | None = None) -> None:
        """Merge incremental updates into the existing walk event.

        Allows for incremental updates to walk events during active sessions
        while preserving existing data and maintaining session continuity.

        Args:
            payload: New or updated event data
            timestamp: Optional timestamp for the update
        """
        updates = dict(payload)
        if "action" in updates:
            self.action = updates.pop("action")
        if "session_id" in updates:
            self.session_id = updates.pop("session_id")
        if "timestamp" in updates:
            raw_timestamp = updates.pop("timestamp")
            if isinstance(raw_timestamp, datetime):
                raw_timestamp = raw_timestamp.isoformat()
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
    mood: str = ""
    activity_level: str = ""
    health_status: str = ""
    symptoms: str = ""
    medication: dict[str, Any] | None = None
    note: str = ""
    logged_by: str = ""
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
            raise ValueError("Weight must be between 0 and 200 kg")
        if self.temperature is not None and (
            self.temperature < 35 or self.temperature > 45
        ):
            raise ValueError("Temperature must be between 35 and 45 degrees Celsius")
        if self.heart_rate is not None and (
            self.heart_rate < 50 or self.heart_rate > 250
        ):
            raise ValueError("Heart rate must be between 50 and 250 bpm")


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
    source: str = ""
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
            raise ValueError("Accuracy cannot be negative")
        if self.battery_level is not None and not (0 <= self.battery_level <= 100):
            raise ValueError("Battery level must be between 0 and 100")
        if self.signal_strength is not None and not (0 <= self.signal_strength <= 100):
            raise ValueError("Signal strength must be between 0 and 100")


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
        "toy": (1.0, 6.0),  # Chihuahua, Yorkshire Terrier
        "small": (4.0, 15.0),  # Jack Russell, Beagle
        "medium": (8.0, 30.0),  # Border Collie, Bulldog
        "large": (22.0, 50.0),  # Labrador, German Shepherd
        "giant": (35.0, 90.0),  # Great Dane, Saint Bernard
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
        "very_low": 1.2,  # Sedentary, minimal exercise
        "low": 1.4,  # Light exercise, short walks
        "normal": 1.6,  # Moderate exercise, regular walks
        "high": 1.8,  # Active exercise, long walks/runs
        "very_high": 2.0,  # Very active, working dogs, intense exercise
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
    required_fields = ["dog_id", "dog_name"]
    for required_field in required_fields:
        if (
            required_field not in config
            or not isinstance(config[required_field], str)
            or not config[required_field].strip()
        ):
            return False

    # Validate optional fields with proper type and range checking
    if "dog_age" in config and (
        not isinstance(config["dog_age"], int)
        or config["dog_age"] < 0
        or config["dog_age"] > 30
    ):
        return False

    if "dog_weight" in config and (
        not is_number(config["dog_weight"]) or float(config["dog_weight"]) <= 0
    ):
        return False

    if "dog_size" in config and config["dog_size"] not in VALID_DOG_SIZES:
        return False

    # Validate modules configuration if present
    if "modules" in config:
        modules = config["modules"]
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
    for coord, limits in [("latitude", (-90, 90)), ("longitude", (-180, 180))]:
        if coord not in location:
            return False
        value = location[coord]
        if not is_number(value):
            return False
        numeric_value = float(value)
        if not (limits[0] <= numeric_value <= limits[1]):
            return False

    # Validate optional fields with appropriate constraints
    if "accuracy" in location and (
        not is_number(location["accuracy"]) or float(location["accuracy"]) < 0
    ):
        return False

    if "battery_level" in location:
        battery = location["battery_level"]
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
    if "meal_type" not in data or data["meal_type"] not in VALID_MEAL_TYPES:
        return False

    if "portion_size" not in data:
        return False

    portion = data["portion_size"]
    if not is_number(portion) or float(portion) < 0:
        return False

    # Validate optional fields with appropriate constraints
    if "food_type" in data and data["food_type"] not in VALID_FOOD_TYPES:
        return False

    if "calories" in data:
        calories = data["calories"]
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
    if "mood" in data and data["mood"] and data["mood"] not in VALID_MOOD_OPTIONS:
        return False

    if (
        "activity_level" in data
        and data["activity_level"]
        and data["activity_level"] not in VALID_ACTIVITY_LEVELS
    ):
        return False

    if (
        "health_status" in data
        and data["health_status"]
        and data["health_status"] not in VALID_HEALTH_STATUS
    ):
        return False

    # Validate physiological measurements with veterinary standards
    if "weight" in data:
        weight = data["weight"]
        if weight is not None and (
            not is_number(weight) or float(weight) <= 0 or float(weight) > 200
        ):
            return False

    if "temperature" in data:
        temp = data["temperature"]
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
    required_fields = ["title", "message"]
    for required_field in required_fields:
        if (
            required_field not in data
            or not isinstance(data[required_field], str)
            or not data[required_field].strip()
        ):
            return False

    # Validate optional fields with frozenset lookups for performance
    if "priority" in data and data["priority"] not in VALID_NOTIFICATION_PRIORITIES:
        return False

    return not (
        "channel" in data and data["channel"] not in VALID_NOTIFICATION_CHANNELS
    )
