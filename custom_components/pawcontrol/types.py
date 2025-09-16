"""Type definitions for Paw Control integration.

This module provides comprehensive type definitions for all Paw Control
components, ensuring type safety and better IDE support across the integration.
Designed for Home Assistant 2025.9.3+ with Platinum quality standards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Required, TypedDict

from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

# OPTIMIZE: Resolve circular imports with proper conditional imports
if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .data_manager import PawControlDataManager
    from .entity_factory import EntityFactory
    from .feeding_manager import FeedingManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager

# OPTIMIZE: Use literal constants instead of runtime imports to avoid circular dependencies
VALID_MEAL_TYPES: frozenset[str] = frozenset(["breakfast", "lunch", "dinner", "snack"])
VALID_FOOD_TYPES: frozenset[str] = frozenset(
    ["dry_food", "wet_food", "barf", "home_cooked", "mixed"]
)
VALID_DOG_SIZES: frozenset[str] = frozenset(
    ["toy", "small", "medium", "large", "giant"]
)
VALID_HEALTH_STATUS: frozenset[str] = frozenset(
    ["excellent", "very_good", "good", "normal", "unwell", "sick"]
)
VALID_MOOD_OPTIONS: frozenset[str] = frozenset(
    ["happy", "neutral", "sad", "angry", "anxious", "tired"]
)
VALID_ACTIVITY_LEVELS: frozenset[str] = frozenset(
    ["very_low", "low", "normal", "high", "very_high"]
)
VALID_GEOFENCE_TYPES: frozenset[str] = frozenset(
    ["safe_zone", "restricted_area", "point_of_interest"]
)
VALID_GPS_SOURCES: frozenset[str] = frozenset(
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
VALID_NOTIFICATION_PRIORITIES: frozenset[str] = frozenset(
    ["low", "normal", "high", "urgent"]
)
VALID_NOTIFICATION_CHANNELS: frozenset[str] = frozenset(
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

# Type aliases for better readability and performance
DogId = str
ConfigEntryId = str
EntityId = str
Timestamp = datetime
ServiceData = dict[str, Any]
ConfigData = dict[str, Any]


class DogConfigData(TypedDict):
    """Type definition for dog configuration data.

    OPTIMIZE: Uses Required[] for mandatory fields and optional for others.
    Added discovery_info field support for device discovery integration.
    """

    # Required fields
    dog_id: Required[str]
    dog_name: Required[str]

    # Optional fields with defaults
    dog_breed: str | None
    dog_age: int | None
    dog_weight: float | None
    dog_size: str | None
    dog_color: str | None
    microchip_id: str | None
    vet_contact: str | None
    emergency_contact: str | None
    modules: dict[str, bool]  # Module configuration
    discovery_info: dict[str, Any] | None  # OPTIMIZE: Added discovery info support


class ModuleConfigData(TypedDict, total=False):
    """Type definition for module configuration data."""

    gps: bool
    feeding: bool
    health: bool
    walk: bool
    notifications: bool
    dashboard: bool
    visitor: bool
    grooming: bool
    medication: bool
    training: bool


class SourceConfigData(TypedDict, total=False):
    """Type definition for source entity configuration."""

    door_sensor: str | None
    person_entities: list[str]
    device_trackers: list[str]
    notify_fallback: str | None
    calendar: str | None
    weather: str | None


class GPSConfigData(TypedDict, total=False):
    """Type definition for GPS configuration data."""

    gps_source: str
    gps_update_interval: int
    gps_accuracy_filter: int
    gps_distance_filter: int
    home_zone_radius: int
    auto_walk_detection: bool
    geofencing: bool
    geofence_zones: list[dict[str, Any]]


class NotificationConfigData(TypedDict, total=False):
    """Type definition for notification configuration."""

    quiet_hours: bool
    quiet_start: str
    quiet_end: str
    reminder_repeat_min: int
    snooze_min: int
    priority_notifications: bool
    mobile_notifications: bool
    persistent_notifications: bool
    channels: list[str]  # OPTIMIZE: Added configurable notification channels


class FeedingConfigData(TypedDict, total=False):
    """Type definition for feeding configuration."""

    feeding_times: list[str]
    breakfast_time: str | None
    lunch_time: str | None
    dinner_time: str | None
    snack_times: list[str]
    daily_food_amount: float | None
    meals_per_day: int
    food_type: str
    special_diet: str | None
    portion_calculation: str
    automatic_feeding: bool  # OPTIMIZE: Added automatic feeding support


class HealthConfigData(TypedDict, total=False):
    """Type definition for health tracking configuration."""

    health_tracking: bool
    weight_tracking: bool
    medication_reminders: bool
    vet_reminders: bool
    grooming_interval: int
    symptom_monitoring: bool  # OPTIMIZE: Added symptom monitoring


class SystemConfigData(TypedDict, total=False):
    """Type definition for system configuration."""

    reset_time: str
    dashboard_mode: str
    data_retention_days: int
    auto_backup: bool
    performance_mode: str
    debug_logging: bool  # OPTIMIZE: Added debug logging configuration


class PawControlConfigData(TypedDict, total=False):
    """Complete configuration data structure."""

    dogs: list[DogConfigData]
    modules: ModuleConfigData
    sources: SourceConfigData
    gps: GPSConfigData
    notifications: NotificationConfigData
    feeding: FeedingConfigData
    health: HealthConfigData
    system: SystemConfigData


@dataclass
class FeedingData:
    """Data structure for feeding information with validation."""

    meal_type: str
    portion_size: float
    food_type: str
    timestamp: datetime
    notes: str = ""
    logged_by: str = ""
    calories: float | None = None
    automatic: bool = False  # OPTIMIZE: Track automatic vs manual feeding

    def __post_init__(self) -> None:
        """Validate data after initialization."""
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
    """Data structure for walk information with enhanced validation."""

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
    weather: str = ""  # OPTIMIZE: Added weather tracking
    temperature: float | None = None  # OPTIMIZE: Added temperature tracking

    def __post_init__(self) -> None:
        """Validate data after initialization."""
        if self.rating < 0 or self.rating > 10:
            raise ValueError("Rating must be between 0 and 10")
        if self.duration is not None and self.duration < 0:
            raise ValueError("Duration cannot be negative")
        if self.distance is not None and self.distance < 0:
            raise ValueError("Distance cannot be negative")
        if self.end_time and self.end_time < self.start_time:
            raise ValueError("End time cannot be before start time")


@dataclass
class HealthData:
    """Data structure for health information with comprehensive validation."""

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
    heart_rate: int | None = None  # OPTIMIZE: Added heart rate tracking
    respiratory_rate: int | None = None  # OPTIMIZE: Added respiratory rate

    def __post_init__(self) -> None:
        """Validate data after initialization."""
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
    """Data structure for GPS location information with validation."""

    latitude: float
    longitude: float
    accuracy: float | None = None
    altitude: float | None = None
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    source: str = ""
    battery_level: int | None = None  # OPTIMIZE: Added battery level for GPS devices
    signal_strength: int | None = None  # OPTIMIZE: Added signal strength

    def __post_init__(self) -> None:
        """Validate GPS coordinates."""
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


@dataclass
class GeofenceZone:
    """Data structure for geofence zone definition with validation."""

    name: str
    latitude: float
    longitude: float
    radius: float
    zone_type: str = "safe_zone"
    notifications: bool = True
    auto_actions: list[str] = field(default_factory=list)
    priority: int = 1  # OPTIMIZE: Added priority for zone overlaps

    def __post_init__(self) -> None:
        """Validate geofence parameters."""
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.radius <= 0:
            raise ValueError("Radius must be positive")
        if self.zone_type not in VALID_GEOFENCE_TYPES:
            raise ValueError(f"Invalid zone type: {self.zone_type}")
        if not (1 <= self.priority <= 10):
            raise ValueError("Priority must be between 1 and 10")


@dataclass
class NotificationData:
    """Data structure for notification information with enhanced validation."""

    title: str
    message: str
    priority: str = "normal"
    channel: str = "mobile"
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    persistent: bool = False
    actions: list[dict[str, str]] = field(default_factory=list)
    dog_id: str = ""  # OPTIMIZE: Added dog association
    module: str = ""  # OPTIMIZE: Added source module tracking

    def __post_init__(self) -> None:
        """Validate notification data."""
        if self.priority not in VALID_NOTIFICATION_PRIORITIES:
            raise ValueError(f"Invalid priority: {self.priority}")
        if self.channel not in VALID_NOTIFICATION_CHANNELS:
            raise ValueError(f"Invalid channel: {self.channel}")
        if not self.title.strip():
            raise ValueError("Title cannot be empty")
        if not self.message.strip():
            raise ValueError("Message cannot be empty")


@dataclass
class MedicationData:
    """Data structure for medication information.

    OPTIMIZE: New comprehensive medication tracking structure.
    """

    name: str
    dosage: str
    frequency: str  # e.g., "2x daily", "once weekly"
    start_date: datetime
    end_date: datetime | None = None
    administered_by: str = ""
    notes: str = ""
    side_effects: list[str] = field(default_factory=list)
    effectiveness_rating: int | None = None  # 1-10 scale

    def __post_init__(self) -> None:
        """Validate medication data."""
        if not self.name.strip():
            raise ValueError("Medication name cannot be empty")
        if not self.dosage.strip():
            raise ValueError("Dosage cannot be empty")
        if not self.frequency.strip():
            raise ValueError("Frequency cannot be empty")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        if self.effectiveness_rating is not None and not (
            1 <= self.effectiveness_rating <= 10
        ):
            raise ValueError("Effectiveness rating must be between 1 and 10")


@dataclass
class DailyStats:
    """Data structure for daily statistics with enhanced metrics."""

    date: datetime
    feedings_count: int = 0
    total_food_amount: float = 0.0
    walks_count: int = 0
    total_walk_time: int = 0  # seconds
    total_walk_distance: float = 0.0  # meters
    health_logs_count: int = 0
    last_feeding_time: datetime | None = None
    last_walk_time: datetime | None = None
    medication_doses: int = 0  # OPTIMIZE: Added medication tracking
    grooming_sessions: int = 0  # OPTIMIZE: Added grooming tracking

    def __post_init__(self) -> None:
        """Validate statistics data."""
        if self.feedings_count < 0:
            raise ValueError("Feedings count cannot be negative")
        if self.total_food_amount < 0:
            raise ValueError("Total food amount cannot be negative")
        if self.walks_count < 0:
            raise ValueError("Walks count cannot be negative")
        if self.total_walk_time < 0:
            raise ValueError("Total walk time cannot be negative")
        if self.total_walk_distance < 0:
            raise ValueError("Total walk distance cannot be negative")
        if self.medication_doses < 0:
            raise ValueError("Medication doses cannot be negative")
        if self.grooming_sessions < 0:
            raise ValueError("Grooming sessions cannot be negative")


@dataclass
class DogProfile:
    """Complete dog profile data structure with enhanced features."""

    dog_id: str
    dog_name: str
    config: DogConfigData
    daily_stats: DailyStats
    current_walk: WalkData | None = None
    last_location: GPSLocation | None = None
    is_visitor_mode: bool = False
    health_alerts: list[str] = field(
        default_factory=list
    )  # OPTIMIZE: Added health alerts

    def __post_init__(self) -> None:
        """Validate dog profile."""
        if not self.dog_id.strip():
            raise ValueError("Dog ID cannot be empty")
        if not self.dog_name.strip():
            raise ValueError("Dog name cannot be empty")


@dataclass
class PawControlRuntimeData:
    """Runtime data for PawControl integration.

    OPTIMIZE: This dataclass contains all runtime components needed by the integration.
    Used for Platinum-level type safety with ConfigEntry[PawControlRuntimeData].
    Enhanced with performance monitoring and error tracking.
    """

    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]

    # OPTIMIZE: Added performance and error tracking
    performance_stats: dict[str, Any] = field(default_factory=dict)
    error_history: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary-like representation of the runtime data."""

        return {
            "coordinator": self.coordinator,
            "data_manager": self.data_manager,
            "notification_manager": self.notification_manager,
            "feeding_manager": self.feeding_manager,
            "walk_manager": self.walk_manager,
            "entity_factory": self.entity_factory,
            "entity_profile": self.entity_profile,
            "dogs": self.dogs,
            "performance_stats": self.performance_stats,
            "error_history": self.error_history,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access for backward compatibility."""

        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key) from None

    def get(self, key: str, default: Any | None = None) -> Any | None:
        """Return an attribute using dictionary-style access."""

        return getattr(self, key, default)


# OPTIMIZE: Custom ConfigEntry type for Platinum compliance
type PawControlConfigEntry = ConfigEntry[PawControlRuntimeData]


class EntityStateData(TypedDict, total=False):
    """Type definition for entity state data."""

    state: str | int | float | bool | None
    attributes: dict[str, Any]
    last_updated: datetime
    context_id: str | None


class ServiceCallData(TypedDict, total=False):
    """Type definition for service call data."""

    domain: str
    service: str
    service_data: ServiceData
    target: dict[str, Any] | None
    blocking: bool
    context: Any | None


class DiagnosticsData(TypedDict):
    """Type definition for diagnostics data with enhanced structure."""

    config_entry: dict[str, Any]
    dogs: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    services: list[str]
    statistics: dict[str, Any]
    performance: dict[str, Any]
    errors: list[dict[str, Any]]
    system_info: dict[str, Any]  # OPTIMIZE: Added system information


class RepairIssueData(TypedDict):
    """Type definition for repair issue data."""

    issue_id: str
    translation_key: str
    severity: str
    learn_more_url: str | None
    translation_placeholders: dict[str, str] | None


# OPTIMIZE: Enhanced type guards for runtime type checking with better performance
def is_dog_config_valid(config: Any) -> bool:
    """Type guard to validate dog configuration.

    OPTIMIZE: Uses frozenset membership for O(1) validation performance.

    Args:
        config: Configuration to validate

    Returns:
        True if configuration is valid
    """
    if not isinstance(config, dict):
        return False

    # Check required fields
    required_fields = ["dog_id", "dog_name"]
    for required_field in required_fields:
        if (
            required_field not in config
            or not isinstance(config[required_field], str)
            or not config[required_field].strip()
        ):
            return False

    # Validate optional fields with frozenset lookups for performance
    if "dog_age" in config and (
        not isinstance(config["dog_age"], int)
        or config["dog_age"] < 0
        or config["dog_age"] > 30
    ):
        return False

    if "dog_weight" in config and (
        not isinstance(config["dog_weight"], int | float) or config["dog_weight"] <= 0
    ):
        return False

    if "dog_size" in config and config["dog_size"] not in VALID_DOG_SIZES:
        return False

    # Validate modules if present
    return not ("modules" in config and not isinstance(config["modules"], dict))


def is_gps_location_valid(location: Any) -> bool:
    """Type guard to validate GPS location data.

    Args:
        location: Location data to validate

    Returns:
        True if location is valid
    """
    if not isinstance(location, dict):
        return False

    # Check required coordinates
    for coord, limits in [("latitude", (-90, 90)), ("longitude", (-180, 180))]:
        if coord not in location:
            return False
        value = location[coord]
        if not isinstance(value, int | float):
            return False
        if not (limits[0] <= value <= limits[1]):
            return False

    # Validate optional fields
    if "accuracy" in location and (
        not isinstance(location["accuracy"], int | float) or location["accuracy"] < 0
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
    """Type guard to validate feeding data with frozenset performance optimization.

    Args:
        data: Feeding data to validate

    Returns:
        True if data is valid
    """
    if not isinstance(data, dict):
        return False

    # Check required fields with frozenset lookup
    if "meal_type" not in data or data["meal_type"] not in VALID_MEAL_TYPES:
        return False

    if "portion_size" not in data:
        return False
    portion = data["portion_size"]
    if not isinstance(portion, int | float) or portion < 0:
        return False

    # Validate optional fields with frozenset lookup
    if "food_type" in data and data["food_type"] not in VALID_FOOD_TYPES:
        return False

    if "calories" in data:
        calories = data["calories"]
        if calories is not None and (
            not isinstance(calories, int | float) or calories < 0
        ):
            return False

    return True


def is_health_data_valid(data: Any) -> bool:
    """Type guard to validate health data with frozenset performance optimization.

    Args:
        data: Health data to validate

    Returns:
        True if data is valid
    """
    if not isinstance(data, dict):
        return False

    # Validate optional fields with frozenset lookups
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

    if "weight" in data:
        weight = data["weight"]
        if weight is not None and (
            not isinstance(weight, int | float) or weight <= 0 or weight > 200
        ):
            return False

    if "temperature" in data:
        temp = data["temperature"]
        if temp is not None and (
            not isinstance(temp, int | float) or temp < 35 or temp > 45
        ):
            return False

    return True


def is_notification_data_valid(data: Any) -> bool:
    """Type guard to validate notification data.

    OPTIMIZE: New validation function with frozenset performance.

    Args:
        data: Notification data to validate

    Returns:
        True if data is valid
    """
    if not isinstance(data, dict):
        return False

    required_fields = ["title", "message"]
    for required_field in required_fields:
        if (
            required_field not in data
            or not isinstance(data[required_field], str)
            or not data[required_field].strip()
        ):
            return False

    if "priority" in data and data["priority"] not in VALID_NOTIFICATION_PRIORITIES:
        return False

    return not (
        "channel" in data and data["channel"] not in VALID_NOTIFICATION_CHANNELS
    )


# Performance optimization types
class PerformanceConfig(TypedDict):
    """Performance configuration options."""

    update_interval: int
    batch_size: int
    cache_timeout: int
    max_retries: int
    request_timeout: float
    memory_limit_mb: int  # OPTIMIZE: Added memory limit


class CacheEntry(TypedDict):
    """Cache entry structure with enhanced metadata."""

    data: Any
    timestamp: datetime
    ttl: int  # seconds
    hit_count: int
    size_bytes: int  # OPTIMIZE: Added size tracking


# OPTIMIZE: Enhanced error types for better error handling
@dataclass
class PawControlError:
    """Base error data structure."""

    code: str
    message: str
    timestamp: datetime = field(default_factory=dt_util.utcnow)
    context: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"  # OPTIMIZE: Added severity levels

    def __post_init__(self) -> None:
        """Validate error data."""
        valid_severities = {"debug", "info", "warning", "error", "critical"}
        if self.severity not in valid_severities:
            self.severity = "error"


@dataclass
class ConfigurationError(PawControlError):
    """Configuration-related error."""

    config_section: str = ""
    suggested_fix: str = ""
    field_name: str = ""  # OPTIMIZE: Added specific field tracking


@dataclass
class DataError(PawControlError):
    """Data-related error."""

    data_type: str = ""
    validation_error: str = ""
    field_path: str = ""  # OPTIMIZE: Added field path for nested data


@dataclass
class GPSError(PawControlError):
    """GPS-related error."""

    location_source: str = ""
    last_known_location: GPSLocation | None = None
    device_id: str = ""  # OPTIMIZE: Added device identification


@dataclass
class NotificationError(PawControlError):
    """Notification-related error."""

    notification_channel: str = ""
    retry_count: int = 0
    target_device: str = ""  # OPTIMIZE: Added target device tracking


# OPTIMIZE: Integration health monitoring types
@dataclass
class HealthMetrics:
    """Health metrics for monitoring integration performance."""

    uptime_seconds: int
    total_entities: int
    active_dogs: int
    update_frequency: float
    error_rate: float
    memory_usage_mb: float
    api_response_time_ms: float

    def __post_init__(self) -> None:
        """Validate health metrics."""
        if self.uptime_seconds < 0:
            raise ValueError("Uptime cannot be negative")
        if self.error_rate < 0 or self.error_rate > 1:
            raise ValueError("Error rate must be between 0 and 1")
        if self.memory_usage_mb < 0:
            raise ValueError("Memory usage cannot be negative")


# OPTIMIZE: Add utility functions for common operations
def create_entity_id(dog_id: str, entity_type: str, module: str) -> str:
    """Create standardized entity ID.

    Args:
        dog_id: Dog identifier
        entity_type: Type of entity
        module: Module name

    Returns:
        Formatted entity ID
    """
    return f"pawcontrol_{dog_id}_{module}_{entity_type}".lower()


def validate_dog_weight_for_size(weight: float, size: str) -> bool:
    """Validate if weight is appropriate for dog size.

    Args:
        weight: Dog weight in kg
        size: Dog size category

    Returns:
        True if weight is appropriate for size
    """
    size_ranges = {
        "toy": (1.0, 6.0),
        "small": (4.0, 15.0),
        "medium": (8.0, 30.0),
        "large": (22.0, 50.0),
        "giant": (35.0, 90.0),
    }

    if size not in size_ranges:
        return True  # Unknown size, skip validation

    min_weight, max_weight = size_ranges[size]
    return min_weight <= weight <= max_weight


def calculate_daily_calories(weight: float, activity_level: str, age: int) -> int:
    """Calculate recommended daily calories for a dog.

    OPTIMIZE: New utility function for feeding management.

    Args:
        weight: Dog weight in kg
        activity_level: Activity level string
        age: Dog age in years

    Returns:
        Recommended daily calories
    """
    # Base calories = 70 * (weight in kg)^0.75
    import math

    base_calories = 70 * math.pow(weight, 0.75)

    # Activity multipliers
    activity_multipliers = {
        "very_low": 1.2,
        "low": 1.4,
        "normal": 1.6,
        "high": 1.8,
        "very_high": 2.0,
    }

    multiplier = activity_multipliers.get(activity_level, 1.6)

    # Age adjustment (puppies and seniors need different amounts)
    if age < 1:
        multiplier *= 2.0  # Puppies need more calories
    elif age > 7:
        multiplier *= 0.9  # Seniors need fewer calories

    return int(base_calories * multiplier)
