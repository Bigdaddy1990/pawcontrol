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

# FIX: Import constants properly to avoid circular imports
if TYPE_CHECKING:
    from .const import (
        ACTIVITY_LEVELS,
        DOG_SIZES,
        FOOD_TYPES,
        GEOFENCE_TYPES,
        GPS_SOURCES,
        HEALTH_STATUS_OPTIONS,
        MEAL_TYPES,
        MOOD_OPTIONS,
    )
else:
    # Runtime imports to avoid circular dependency issues
    try:
        from .const import (
            ACTIVITY_LEVELS,
            DOG_SIZES,
            FOOD_TYPES,
            GEOFENCE_TYPES,
            GPS_SOURCES,
            HEALTH_STATUS_OPTIONS,
            MEAL_TYPES,
            MOOD_OPTIONS,
        )
    except ImportError:
        # Fallback definitions if constants not available
        MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack")
        FOOD_TYPES = ("dry_food", "wet_food", "barf", "home_cooked", "mixed")
        DOG_SIZES = ("toy", "small", "medium", "large", "giant")
        HEALTH_STATUS_OPTIONS = ("excellent", "very_good", "good", "normal", "unwell", "sick")
        MOOD_OPTIONS = ("happy", "neutral", "sad", "angry", "anxious", "tired")
        ACTIVITY_LEVELS = ("very_low", "low", "normal", "high", "very_high")
        GEOFENCE_TYPES = ("safe_zone", "restricted_area", "point_of_interest")
        GPS_SOURCES = ("manual", "device_tracker", "person_entity", "smartphone", "tractive", "webhook", "mqtt")

# Type aliases for better readability
DogId = str
ConfigEntryId = str
EntityId = str
Timestamp = datetime
ServiceData = dict[str, Any]
ConfigData = dict[str, Any]

# Performance-optimized validation sets (created once)
VALID_MEAL_TYPES: frozenset[str] = frozenset(MEAL_TYPES)
VALID_FOOD_TYPES: frozenset[str] = frozenset(FOOD_TYPES)
VALID_DOG_SIZES: frozenset[str] = frozenset(DOG_SIZES)
VALID_HEALTH_STATUS: frozenset[str] = frozenset(HEALTH_STATUS_OPTIONS)
VALID_MOOD_OPTIONS: frozenset[str] = frozenset(MOOD_OPTIONS)
VALID_ACTIVITY_LEVELS: frozenset[str] = frozenset(ACTIVITY_LEVELS)
VALID_GEOFENCE_TYPES: frozenset[str] = frozenset(GEOFENCE_TYPES)
VALID_GPS_SOURCES: frozenset[str] = frozenset(GPS_SOURCES)
VALID_NOTIFICATION_PRIORITIES: frozenset[str] = frozenset(["low", "normal", "high", "urgent"])


class DogConfigData(TypedDict):
    """Type definition for dog configuration data.
    
    Uses Required[] for mandatory fields and optional for others.
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
    discovery_info: dict[str, Any] | None  # FIX: Added discovery info support


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


class HealthConfigData(TypedDict, total=False):
    """Type definition for health tracking configuration."""

    health_tracking: bool
    weight_tracking: bool
    medication_reminders: bool
    vet_reminders: bool
    grooming_interval: int


class SystemConfigData(TypedDict, total=False):
    """Type definition for system configuration."""

    reset_time: str
    dashboard_mode: str
    data_retention_days: int
    auto_backup: bool
    performance_mode: str


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
    """Data structure for feeding information."""

    meal_type: str
    portion_size: float
    food_type: str
    timestamp: datetime
    notes: str = ""
    logged_by: str = ""
    calories: float | None = None
    
    def __post_init__(self) -> None:
        """Validate data after initialization."""
        if self.meal_type not in VALID_MEAL_TYPES:
            raise ValueError(f"Invalid meal type: {self.meal_type}")
        if self.food_type not in VALID_FOOD_TYPES:
            raise ValueError(f"Invalid food type: {self.food_type}")
        if self.portion_size < 0:
            raise ValueError("Portion size cannot be negative")


@dataclass
class WalkData:
    """Data structure for walk information."""

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
    
    def __post_init__(self) -> None:
        """Validate data after initialization."""
        if self.rating < 0 or self.rating > 10:
            raise ValueError("Rating must be between 0 and 10")
        if self.duration is not None and self.duration < 0:
            raise ValueError("Duration cannot be negative")
        if self.distance is not None and self.distance < 0:
            raise ValueError("Distance cannot be negative")


@dataclass
class HealthData:
    """Data structure for health information."""

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


@dataclass
class GPSLocation:
    """Data structure for GPS location information."""

    latitude: float
    longitude: float
    accuracy: float | None = None
    altitude: float | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""
    
    def __post_init__(self) -> None:
        """Validate GPS coordinates."""
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Invalid latitude: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Invalid longitude: {self.longitude}")
        if self.accuracy is not None and self.accuracy < 0:
            raise ValueError("Accuracy cannot be negative")


@dataclass
class GeofenceZone:
    """Data structure for geofence zone definition."""

    name: str
    latitude: float
    longitude: float
    radius: float
    zone_type: str = "safe_zone"
    notifications: bool = True
    auto_actions: list[str] = field(default_factory=list)
    
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


@dataclass
class NotificationData:
    """Data structure for notification information."""

    title: str
    message: str
    priority: str = "normal"
    channel: str = "mobile"
    timestamp: datetime = field(default_factory=datetime.now)
    persistent: bool = False
    actions: list[dict[str, str]] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate notification data."""
        if self.priority not in VALID_NOTIFICATION_PRIORITIES:
            raise ValueError(f"Invalid priority: {self.priority}")
        if not self.title.strip():
            raise ValueError("Title cannot be empty")
        if not self.message.strip():
            raise ValueError("Message cannot be empty")


@dataclass
class DailyStats:
    """Data structure for daily statistics."""

    date: datetime
    feedings_count: int = 0
    total_food_amount: float = 0.0
    walks_count: int = 0
    total_walk_time: int = 0  # seconds
    total_walk_distance: float = 0.0  # meters
    health_logs_count: int = 0
    last_feeding_time: datetime | None = None
    last_walk_time: datetime | None = None
    
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


@dataclass
class DogProfile:
    """Complete dog profile data structure."""

    dog_id: str
    dog_name: str
    config: DogConfigData
    daily_stats: DailyStats
    current_walk: WalkData | None = None
    last_location: GPSLocation | None = None
    is_visitor_mode: bool = False
    
    def __post_init__(self) -> None:
        """Validate dog profile."""
        if not self.dog_id.strip():
            raise ValueError("Dog ID cannot be empty")
        if not self.dog_name.strip():
            raise ValueError("Dog name cannot be empty")


# Forward declarations to avoid circular imports
if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .data_manager import PawControlDataManager
    from .entity_factory import EntityFactory
    from .feeding_manager import FeedingManager
    from .notifications import PawControlNotificationManager
    from .walk_manager import WalkManager


@dataclass
class PawControlRuntimeData:
    """Runtime data for PawControl integration.

    This dataclass contains all runtime components needed by the integration.
    Used for Platinum-level type safety with ConfigEntry[PawControlRuntimeData].
    """

    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    feeding_manager: FeedingManager
    walk_manager: WalkManager
    entity_factory: EntityFactory
    entity_profile: str
    dogs: list[DogConfigData]


# Custom ConfigEntry type for Platinum compliance
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
    """Type definition for diagnostics data."""

    config_entry: dict[str, Any]
    dogs: list[dict[str, Any]]
    entities: list[dict[str, Any]]
    services: list[str]
    statistics: dict[str, Any]
    performance: dict[str, Any]
    errors: list[dict[str, Any]]


class RepairIssueData(TypedDict):
    """Type definition for repair issue data."""

    issue_id: str
    translation_key: str
    severity: str
    learn_more_url: str | None
    translation_placeholders: dict[str, str] | None


# Enhanced type guards for runtime type checking
def is_dog_config_valid(config: Any) -> bool:
    """Type guard to validate dog configuration.
    
    Args:
        config: Configuration to validate
        
    Returns:
        True if configuration is valid
    """
    if not isinstance(config, dict):
        return False
        
    # Check required fields
    required_fields = ["dog_id", "dog_name"]
    for field in required_fields:
        if field not in config or not isinstance(config[field], str) or not config[field].strip():
            return False
    
    # Validate optional fields
    if "dog_age" in config:
        if not isinstance(config["dog_age"], int) or config["dog_age"] < 0 or config["dog_age"] > 30:
            return False
            
    if "dog_weight" in config:
        if not isinstance(config["dog_weight"], (int, float)) or config["dog_weight"] <= 0:
            return False
            
    if "dog_size" in config:
        if config["dog_size"] not in VALID_DOG_SIZES:
            return False
    
    return True


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
        if not isinstance(value, (int, float)):
            return False
        if not (limits[0] <= value <= limits[1]):
            return False
    
    # Validate optional fields
    if "accuracy" in location:
        if not isinstance(location["accuracy"], (int, float)) or location["accuracy"] < 0:
            return False
            
    return True


def is_feeding_data_valid(data: Any) -> bool:
    """Type guard to validate feeding data.
    
    Args:
        data: Feeding data to validate
        
    Returns:
        True if data is valid
    """
    if not isinstance(data, dict):
        return False
        
    # Check required fields
    if "meal_type" not in data or data["meal_type"] not in VALID_MEAL_TYPES:
        return False
        
    if "portion_size" not in data:
        return False
    portion = data["portion_size"]
    if not isinstance(portion, (int, float)) or portion < 0:
        return False
        
    # Validate optional fields
    if "food_type" in data and data["food_type"] not in VALID_FOOD_TYPES:
        return False
        
    return True


def is_health_data_valid(data: Any) -> bool:
    """Type guard to validate health data.
    
    Args:
        data: Health data to validate
        
    Returns:
        True if data is valid
    """
    if not isinstance(data, dict):
        return False
        
    # Validate optional fields
    if "mood" in data and data["mood"] and data["mood"] not in VALID_MOOD_OPTIONS:
        return False
        
    if "activity_level" in data and data["activity_level"] and data["activity_level"] not in VALID_ACTIVITY_LEVELS:
        return False
        
    if "health_status" in data and data["health_status"] and data["health_status"] not in VALID_HEALTH_STATUS:
        return False
        
    if "weight" in data:
        weight = data["weight"]
        if weight is not None and (not isinstance(weight, (int, float)) or weight <= 0 or weight > 200):
            return False
    
    return True


# Performance optimization types
class PerformanceConfig(TypedDict):
    """Performance configuration options."""

    update_interval: int
    batch_size: int
    cache_timeout: int
    max_retries: int
    request_timeout: float


class CacheEntry(TypedDict):
    """Cache entry structure."""

    data: Any
    timestamp: datetime
    ttl: int  # seconds
    hit_count: int


# Error types for better error handling
@dataclass
class PawControlError:
    """Base error data structure."""

    code: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfigurationError(PawControlError):
    """Configuration-related error."""

    config_section: str = ""
    suggested_fix: str = ""


@dataclass
class DataError(PawControlError):
    """Data-related error."""

    data_type: str = ""
    validation_error: str = ""


@dataclass
class GPSError(PawControlError):
    """GPS-related error."""

    location_source: str = ""
    last_known_location: GPSLocation | None = None


@dataclass
class NotificationError(PawControlError):
    """Notification-related error."""

    notification_channel: str = ""
    retry_count: int = 0