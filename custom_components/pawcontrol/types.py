"""Typed runtime data structures for Paw Control integration.

This module provides comprehensive type definitions for all data structures
used throughout the Paw Control integration, ensuring type safety and
better IDE support.

The types follow Home Assistant's Platinum standards with:
- Complete type annotations for all data structures
- Comprehensive documentation for each type
- Proper use of TypedDict for structured data
- Forward references to avoid circular imports
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, NotRequired, TypedDict

if TYPE_CHECKING:
    from .coordinator import PawControlCoordinator
    from .gps_handler import PawControlGPSHandler
    from .helpers.notification_router import NotificationRouter
    from .helpers.scheduler import PawControlScheduler
    from .helpers.setup_sync import SetupSync
    from .report_generator import ReportGenerator
    from .services import ServiceManager

# ==============================================================================
# RUNTIME DATA CONTAINER
# ==============================================================================

@dataclass
class PawRuntimeData:
    """Aggregated, typed runtime data stored on the config entry.
    
    This dataclass contains all the main components and services that make up
    a Paw Control integration instance. It provides type-safe access to all
    core functionality from platforms and other components.
    
    Attributes:
        coordinator: Main data coordinator for dog information
        gps_handler: GPS tracking and geofencing handler
        setup_sync: Helper for synchronizing setup across components
        report_generator: Service for generating reports and analytics
        services: Manager for Home Assistant services
        notification_router: Router for managing notifications
        scheduler: Optional scheduler for automated tasks
    """
    
    coordinator: PawControlCoordinator
    gps_handler: PawControlGPSHandler
    setup_sync: SetupSync
    report_generator: ReportGenerator
    services: ServiceManager
    notification_router: NotificationRouter
    scheduler: PawControlScheduler | None = None

# ==============================================================================
# DOG DATA STRUCTURE TYPES
# ==============================================================================

class DogInfoData(TypedDict):
    """Type definition for dog basic information."""
    name: str
    breed: str
    age: int
    weight: float
    size: Literal["small", "medium", "large", "xlarge"]

class WalkData(TypedDict):
    """Type definition for dog walk tracking data."""
    last_walk: str | None
    walk_in_progress: bool
    walk_start_time: str | None
    walk_duration_min: float
    walk_distance_m: float
    walks_today: int
    total_distance_today: float
    needs_walk: bool

class SafeZoneData(TypedDict):
    """Type definition for safe zone tracking data."""
    inside: bool | None
    last_ts: str
    enters: int
    leaves: int
    time_today_s: float

class FeedingCounters(TypedDict):
    """Type definition for daily feeding counters."""
    breakfast: int
    lunch: int
    dinner: int
    snack: int

class FeedingData(TypedDict):
    """Type definition for dog feeding tracking data."""
    last_feeding: str | None
    last_meal_type: str | None
    last_portion_g: int
    last_food_type: str | None
    feedings_today: FeedingCounters
    total_portions_today: int
    is_hungry: bool

class WeightTrendEntry(TypedDict):
    """Type definition for weight trend data points."""
    date: str
    weight: float

class HealthNoteEntry(TypedDict):
    """Type definition for health note entries."""
    date: str
    note: str

class VaccineStatus(TypedDict):
    """Type definition for vaccination status."""
    name: str
    last_date: str | None
    next_due: str | None
    is_overdue: bool

class HealthData(TypedDict):
    """Type definition for dog health tracking data."""
    weight_kg: float
    weight_trend: list[WeightTrendEntry]
    last_medication: str | None
    medication_name: str | None
    medication_dose: str | None
    medications_today: int
    next_medication_due: datetime | None
    vaccine_status: dict[str, VaccineStatus]
    last_vet_visit: str | None
    health_notes: list[HealthNoteEntry]

class GroomingHistoryEntry(TypedDict):
    """Type definition for grooming history entries."""
    date: str
    type: str
    notes: str

class GroomingData(TypedDict):
    """Type definition for dog grooming tracking data."""
    last_grooming: str | None
    grooming_type: str | None
    grooming_interval_days: int
    needs_grooming: bool
    grooming_history: list[GroomingHistoryEntry]

class TrainingHistoryEntry(TypedDict):
    """Type definition for training history entries."""
    date: str
    topic: str
    duration: int
    notes: str

class TrainingData(TypedDict):
    """Type definition for dog training tracking data."""
    last_training: str | None
    last_topic: str | None
    training_duration_min: int
    training_sessions_today: int
    training_history: list[TrainingHistoryEntry]

class ActivityData(TypedDict):
    """Type definition for dog activity tracking data."""
    last_play: str | None
    play_duration_today_min: int
    activity_level: Literal["low", "medium", "high"]
    calories_burned_today: float

class LocationData(TypedDict):
    """Type definition for dog location tracking data."""
    current_location: str
    last_gps_update: str | None
    is_home: bool
    distance_from_home: float
    enters_today: int
    leaves_today: int
    time_inside_today_min: float
    last_ts: str | None
    radius_m: int
    home_lat: float | None
    home_lon: float | None

class StatisticsData(TypedDict):
    """Type definition for dog statistics data."""
    poop_count_today: int
    last_poop: str | None
    last_action: str | None
    last_action_type: str | None

class DogData(TypedDict):
    """Complete type definition for individual dog data structure.
    
    This represents all the data tracked for a single dog, organized into
    logical categories for different aspects of care and monitoring.
    """
    info: DogInfoData
    walk: WalkData
    safe_zone: SafeZoneData
    feeding: FeedingData
    health: HealthData
    grooming: GroomingData
    training: TrainingData
    activity: ActivityData
    location: LocationData
    statistics: StatisticsData

# Coordinator data is a mapping of dog IDs to their data
CoordinatorData = dict[str, DogData]

# ==============================================================================
# CONFIGURATION TYPES
# ==============================================================================

class DogModulesConfig(TypedDict):
    """Type definition for dog module configuration."""
    feeding: bool
    gps: bool
    health: bool
    walk: bool
    grooming: bool
    training: bool
    notifications: bool
    dashboard: bool
    medication: bool

class DogConfig(TypedDict):
    """Type definition for individual dog configuration."""
    dog_id: str
    dog_name: str
    dog_breed: NotRequired[str]
    dog_age: NotRequired[int]
    dog_weight: NotRequired[float]
    dog_size: NotRequired[Literal["small", "medium", "large", "xlarge"]]
    dog_modules: NotRequired[DogModulesConfig]

class SourcesConfig(TypedDict, total=False):
    """Type definition for data sources configuration."""
    door_sensor: str
    person_entities: list[str]
    device_trackers: list[str]
    calendar: str
    weather: str

class QuietHoursConfig(TypedDict):
    """Type definition for quiet hours configuration."""
    quiet_start: str
    quiet_end: str

class NotificationsConfig(TypedDict, total=False):
    """Type definition for notifications configuration."""
    notify_fallback: str
    quiet_hours: QuietHoursConfig
    reminder_repeat: int
    snooze_min: int

class GeofenceConfig(TypedDict, total=False):
    """Type definition for geofence configuration."""
    lat: float
    lon: float
    radius_m: int
    enable_alerts: bool

class AdvancedConfig(TypedDict, total=False):
    """Type definition for advanced settings configuration."""
    route_history_limit: int
    enable_pawtracker_alias: bool
    diagnostic_sensors: bool
    debug_logging: bool
    api_timeout_seconds: int

class IntegrationConfig(TypedDict):
    """Type definition for complete integration configuration."""
    dogs: list[DogConfig]
    sources: NotRequired[SourcesConfig]
    notifications: NotRequired[NotificationsConfig]
    reset_time: NotRequired[str]
    export_path: NotRequired[str]
    export_format: NotRequired[Literal["csv", "json", "pdf"]]
    visitor_mode: NotRequired[bool]
    geofence: NotRequired[GeofenceConfig]
    advanced: NotRequired[AdvancedConfig]

# ==============================================================================
# GPS AND LOCATION TYPES
# ==============================================================================

class GPSCoordinate(TypedDict):
    """Type definition for GPS coordinate with metadata."""
    latitude: float
    longitude: float
    altitude: NotRequired[float]
    accuracy: NotRequired[float]
    timestamp: str
    source: NotRequired[str]

class RoutePoint(TypedDict):
    """Type definition for route tracking points."""
    latitude: float
    longitude: float
    altitude: NotRequired[float]
    accuracy: NotRequired[float]
    timestamp: str
    speed: NotRequired[float]
    bearing: NotRequired[float]

class Route(TypedDict):
    """Type definition for complete route data."""
    dog_id: str
    start_time: str
    end_time: str | None
    points: list[RoutePoint]
    total_distance: float
    duration_minutes: float
    is_active: bool

class GeofenceEvent(TypedDict):
    """Type definition for geofence events."""
    dog_id: str
    event_type: Literal["enter", "exit"]
    timestamp: str
    location: GPSCoordinate
    geofence_name: str

# ==============================================================================
# SERVICE CALL TYPES
# ==============================================================================

class ServiceCallData(TypedDict, total=False):
    """Base type for service call data."""
    dog_id: str

class WalkServiceData(ServiceCallData):
    """Type definition for walk-related service calls."""
    duration_min: NotRequired[int]
    distance_m: NotRequired[int]
    reason: NotRequired[str]
    source: NotRequired[str]

class FeedingServiceData(ServiceCallData):
    """Type definition for feeding service calls."""
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"]
    portion_g: int
    food_type: str

class HealthServiceData(ServiceCallData):
    """Type definition for health logging service calls."""
    weight_kg: NotRequired[float]
    note: NotRequired[str]
    temperature: NotRequired[float]
    heart_rate: NotRequired[int]

class MedicationServiceData(ServiceCallData):
    """Type definition for medication service calls."""
    medication_name: str
    dose: str
    notes: NotRequired[str]

class GroomingServiceData(ServiceCallData):
    """Type definition for grooming service calls."""
    grooming_type: Literal["bath", "brush", "ears", "eyes", "nails", "teeth", "trim"]
    notes: NotRequired[str]
    duration_min: NotRequired[int]

class TrainingServiceData(ServiceCallData):
    """Type definition for training service calls."""
    topic: str
    duration_min: int
    intensity: NotRequired[Literal["low", "medium", "high"]]
    notes: NotRequired[str]

class PlayServiceData(ServiceCallData):
    """Type definition for play session service calls."""
    duration_min: int
    intensity: Literal["low", "medium", "high"]
    activity_type: NotRequired[str]

class EmergencyServiceData(ServiceCallData):
    """Type definition for emergency mode service calls."""
    level: Literal["info", "warning", "critical"]
    note: str
    auto_notify: NotRequired[bool]

# ==============================================================================
# SENSOR AND ENTITY TYPES
# ==============================================================================

class SensorStateData(TypedDict, total=False):
    """Type definition for sensor state with attributes."""
    state: str | int | float | None
    attributes: dict[str, Any]
    last_updated: str
    unit_of_measurement: str
    device_class: str
    state_class: str

class EntityConfigData(TypedDict):
    """Type definition for entity configuration."""
    entity_id: str
    name: str
    icon: NotRequired[str]
    device_class: NotRequired[str]
    unit_of_measurement: NotRequired[str]
    enabled_by_default: NotRequired[bool]

# ==============================================================================
# NOTIFICATION AND EVENT TYPES
# ==============================================================================

class NotificationData(TypedDict):
    """Type definition for notification data."""
    title: str
    message: str
    target: NotRequired[str | list[str]]
    data: NotRequired[dict[str, Any]]
    priority: NotRequired[Literal["low", "normal", "high", "critical"]]

class EventData(TypedDict):
    """Type definition for Home Assistant events."""
    event_type: str
    data: dict[str, Any]
    time_fired: str
    origin: str

# ==============================================================================
# REPORT AND ANALYTICS TYPES
# ==============================================================================

class DailyStatistics(TypedDict):
    """Type definition for daily statistics."""
    date: str
    dog_id: str
    walks_count: int
    walk_distance_total: float
    walk_duration_total: float
    feedings_count: int
    calories_burned: float
    time_inside_minutes: float
    geofence_exits: int

class WeeklyReport(TypedDict):
    """Type definition for weekly reports."""
    week_start: str
    week_end: str
    dog_id: str
    daily_stats: list[DailyStatistics]
    averages: dict[str, float]
    trends: dict[str, Literal["increasing", "decreasing", "stable"]]

class HealthReport(TypedDict):
    """Type definition for health reports."""
    dog_id: str
    report_date: str
    weight_trend: list[WeightTrendEntry]
    vaccination_status: dict[str, VaccineStatus]
    medication_history: list[dict[str, Any]]
    health_notes: list[HealthNoteEntry]
    recommendations: list[str]

# ==============================================================================
# ERROR AND STATUS TYPES
# ==============================================================================

class ErrorInfo(TypedDict):
    """Type definition for error information."""
    error_code: str
    error_message: str
    timestamp: str
    component: str
    details: NotRequired[dict[str, Any]]

class ComponentStatus(TypedDict):
    """Type definition for component status."""
    component_name: str
    status: Literal["active", "inactive", "error", "unknown"]
    last_update: str
    error_info: NotRequired[ErrorInfo]

class SystemDiagnostics(TypedDict):
    """Type definition for system diagnostics."""
    integration_version: str
    home_assistant_version: str
    component_status: list[ComponentStatus]
    configuration_summary: dict[str, Any]
    performance_metrics: dict[str, float]
    errors: list[ErrorInfo]

# ==============================================================================
# STORAGE AND PERSISTENCE TYPES
# ==============================================================================

class StoredRoute(TypedDict):
    """Type definition for routes stored in persistent storage."""
    route_id: str
    dog_id: str
    start_time: str
    end_time: str
    points: list[RoutePoint]
    metadata: dict[str, Any]

class UserPreferences(TypedDict, total=False):
    """Type definition for user preferences storage."""
    default_dog_id: str
    preferred_units: Literal["metric", "imperial"]
    dashboard_layout: dict[str, Any]
    notification_preferences: dict[str, bool]
    theme_settings: dict[str, str]

class IntegrationData(TypedDict):
    """Type definition for all persistent integration data."""
    routes: list[StoredRoute]
    user_preferences: UserPreferences
    statistics_cache: dict[str, DailyStatistics]
    last_backup: NotRequired[str]

# ==============================================================================
# API AND WEBHOOK TYPES  
# ==============================================================================

class WebhookData(TypedDict):
    """Type definition for incoming webhook data."""
    dog_id: str
    event_type: str
    timestamp: str
    location: NotRequired[GPSCoordinate]
    sensor_data: NotRequired[dict[str, Any]]
    metadata: NotRequired[dict[str, Any]]

class APIResponse(TypedDict):
    """Type definition for API responses."""
    success: bool
    message: str
    data: NotRequired[dict[str, Any]]
    error_code: NotRequired[str]
    timestamp: str

# ==============================================================================
# UTILITY TYPE ALIASES
# ==============================================================================

# Common type aliases for better readability
DogID = str
EntityID = str
ServiceName = str
EventType = str
Timestamp = str
Coordinate = tuple[float, float]  # (latitude, longitude)
BoundingBox = tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)

# Optional configuration values
OptionalString = str | None
OptionalInt = int | None
OptionalFloat = float | None
OptionalBool = bool | None

# Collection types
DogList = list[DogConfig]
EntityList = list[EntityID]
ServiceCallDataType = (
    WalkServiceData | FeedingServiceData | HealthServiceData | 
    MedicationServiceData | GroomingServiceData | TrainingServiceData |
    PlayServiceData | EmergencyServiceData
)
