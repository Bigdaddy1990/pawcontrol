"""Type definitions for Paw Control integration.

This module provides comprehensive type definitions for all Paw Control
components, ensuring type safety and better IDE support across the integration.
Designed for Home Assistant 2025.8.2+ with Platinum quality standards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any, Dict, List, Optional, TypedDict, Union

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

# Type aliases for better readability
DogId = str
ConfigEntryId = str
EntityId = str
Timestamp = datetime
ServiceData = Dict[str, Any]
ConfigData = Dict[str, Any]


class DogConfigData(TypedDict, total=False):
    """Type definition for dog configuration data."""
    dog_id: str
    dog_name: str
    dog_breed: Optional[str]
    dog_age: Optional[int]
    dog_weight: Optional[float]
    dog_size: Optional[str]
    dog_color: Optional[str]
    microchip_id: Optional[str]
    vet_contact: Optional[str]
    emergency_contact: Optional[str]


class ModuleConfigData(TypedDict, total=False):
    """Type definition for module configuration data."""
    gps: bool
    feeding: bool
    health: bool
    walk: bool
    notifications: bool
    dashboard: bool
    visitor: bool


class SourceConfigData(TypedDict, total=False):
    """Type definition for source entity configuration."""
    door_sensor: Optional[str]
    person_entities: List[str]
    device_trackers: List[str]
    notify_fallback: Optional[str]
    calendar: Optional[str]
    weather: Optional[str]


class GPSConfigData(TypedDict, total=False):
    """Type definition for GPS configuration data."""
    gps_source: str
    gps_update_interval: int
    gps_accuracy_filter: int
    gps_distance_filter: int
    home_zone_radius: int
    auto_walk_detection: bool
    geofencing: bool
    geofence_zones: List[Dict[str, Any]]


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
    feeding_times: List[str]
    breakfast_time: Optional[str]
    lunch_time: Optional[str]
    dinner_time: Optional[str]
    snack_times: List[str]
    daily_food_amount: Optional[float]
    meals_per_day: int
    food_type: str


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
    dogs: List[DogConfigData]
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
    calories: Optional[float] = None


@dataclass
class WalkData:
    """Data structure for walk information."""
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[int] = None  # seconds
    distance: Optional[float] = None  # meters
    route: List[Dict[str, float]] = field(default_factory=list)
    label: str = ""
    location: str = ""
    notes: str = ""
    rating: int = 0
    started_by: str = ""
    ended_by: str = ""


@dataclass
class HealthData:
    """Data structure for health information."""
    timestamp: datetime
    weight: Optional[float] = None
    temperature: Optional[float] = None
    mood: str = ""
    activity_level: str = ""
    health_status: str = ""
    symptoms: str = ""
    medication: Optional[Dict[str, Any]] = None
    note: str = ""
    logged_by: str = ""


@dataclass
class GPSLocation:
    """Data structure for GPS location information."""
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = ""


@dataclass
class GeofenceZone:
    """Data structure for geofence zone definition."""
    name: str
    latitude: float
    longitude: float
    radius: float
    zone_type: str = "safe_zone"
    notifications: bool = True
    auto_actions: List[str] = field(default_factory=list)


@dataclass
class NotificationData:
    """Data structure for notification information."""
    title: str
    message: str
    priority: str = "normal"
    channel: str = "mobile"
    timestamp: datetime = field(default_factory=datetime.now)
    persistent: bool = False
    actions: List[Dict[str, str]] = field(default_factory=list)


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
    last_feeding_time: Optional[datetime] = None
    last_walk_time: Optional[datetime] = None


@dataclass
class DogProfile:
    """Complete dog profile data structure."""
    dog_id: str
    dog_name: str
    config: DogConfigData
    daily_stats: DailyStats
    current_walk: Optional[WalkData] = None
    last_location: Optional[GPSLocation] = None
    is_visitor_mode: bool = False


# Forward declarations to avoid circular imports
if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .data_manager import PawControlDataManager
    from .notifications import PawControlNotificationManager

class PawControlRuntimeData(TypedDict):
    """Runtime data structure for the integration."""
    coordinator: PawControlCoordinator
    data_manager: PawControlDataManager
    notification_manager: PawControlNotificationManager
    config_entry: ConfigEntry
    dogs: List[DogConfigData]


class EntityStateData(TypedDict, total=False):
    """Type definition for entity state data."""
    state: Union[str, int, float, bool, None]
    attributes: Dict[str, Any]
    last_updated: datetime
    context_id: Optional[str]


class ServiceCallData(TypedDict, total=False):
    """Type definition for service call data."""
    domain: str
    service: str
    service_data: ServiceData
    target: Optional[Dict[str, Any]]
    blocking: bool
    context: Optional[Any]


class DiagnosticsData(TypedDict):
    """Type definition for diagnostics data."""
    config_entry: Dict[str, Any]
    dogs: List[Dict[str, Any]]
    entities: List[Dict[str, Any]]
    services: List[str]
    statistics: Dict[str, Any]
    performance: Dict[str, Any]
    errors: List[Dict[str, Any]]


class RepairIssueData(TypedDict):
    """Type definition for repair issue data."""
    issue_id: str
    translation_key: str
    severity: str
    learn_more_url: Optional[str]
    translation_placeholders: Optional[Dict[str, str]]


# Type guards for runtime type checking
def is_dog_config_valid(config: Any) -> bool:
    """Type guard to validate dog configuration."""
    return (
        isinstance(config, dict) and
        "dog_id" in config and
        "dog_name" in config and
        isinstance(config["dog_id"], str) and
        isinstance(config["dog_name"], str) and
        len(config["dog_id"]) > 0 and
        len(config["dog_name"]) > 0
    )


def is_gps_location_valid(location: Any) -> bool:
    """Type guard to validate GPS location data."""
    return (
        isinstance(location, dict) and
        "latitude" in location and
        "longitude" in location and
        isinstance(location["latitude"], (int, float)) and
        isinstance(location["longitude"], (int, float)) and
        -90 <= location["latitude"] <= 90 and
        -180 <= location["longitude"] <= 180
    )


def is_feeding_data_valid(data: Any) -> bool:
    """Type guard to validate feeding data."""
    return (
        isinstance(data, dict) and
        "meal_type" in data and
        "portion_size" in data and
        isinstance(data["meal_type"], str) and
        isinstance(data["portion_size"], (int, float)) and
        data["portion_size"] >= 0
    )


# Import validation constants from const.py (single source of truth)
from .const import (
    MEAL_TYPES,
    FOOD_TYPES, 
    DOG_SIZES,
    HEALTH_STATUS_OPTIONS,
    MOOD_OPTIONS,
    ACTIVITY_LEVELS,
    GEOFENCE_TYPES,
    GPS_SOURCES,
)

# Convert to sets for type validation (faster lookups)
VALID_MEAL_TYPES = set(MEAL_TYPES)
VALID_FOOD_TYPES = set(FOOD_TYPES)
VALID_DOG_SIZES = set(DOG_SIZES)
VALID_HEALTH_STATUS = set(HEALTH_STATUS_OPTIONS)
VALID_MOOD_OPTIONS = set(MOOD_OPTIONS)
VALID_ACTIVITY_LEVELS = set(ACTIVITY_LEVELS)
VALID_GEOFENCE_TYPES = set(GEOFENCE_TYPES)
VALID_GPS_SOURCES = set(GPS_SOURCES)
VALID_NOTIFICATION_PRIORITIES = {"low", "normal", "high", "urgent"}

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
    context: Dict[str, Any] = field(default_factory=dict)


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
    last_known_location: Optional[GPSLocation] = None


@dataclass
class NotificationError(PawControlError):
    """Notification-related error."""
    notification_channel: str = ""
    retry_count: int = 0
