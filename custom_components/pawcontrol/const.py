"""Constants for the Paw Control integration.

This module defines all constants used throughout the Paw Control integration,
including configuration keys, default values, service names, event types,
and various thresholds and limits.

Constants are organized by category and follow Home Assistant's Platinum
standards with complete type annotations and comprehensive documentation.
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# Integration domain identifier
DOMAIN: Final[str] = "pawcontrol"

# Integration version for internal tracking
INTEGRATION_VERSION: Final[str] = "1.3.0"

# ==============================================================================
# PLATFORMS
# ==============================================================================

# All platforms supported by this integration
PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.DATETIME,
    Platform.DEVICE_TRACKER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

# Default parallel updates for platforms that require serial execution
PARALLEL_UPDATES: Final[int] = 0

# ==============================================================================
# GEOGRAPHIC AND MEASUREMENT CONSTANTS
# ==============================================================================

# Earth radius in meters used for haversine distance calculations
EARTH_RADIUS_M: Final[float] = 6_371_000.0

# GPS accuracy and movement thresholds
GPS_MIN_ACCURACY: Final[int] = 100  # meters - minimum acceptable GPS accuracy
GPS_MAX_POINTS_PER_ROUTE: Final[int] = 10_000  # maximum GPS points stored per route
GPS_POINT_FILTER_DISTANCE: Final[int] = (
    5  # meters - minimum distance between stored points
)
GPS_MINIMUM_MOVEMENT_THRESHOLD_M: Final[int] = (
    5  # meters - minimum movement to register update
)

# Walk detection and tracking thresholds
DEFAULT_MIN_WALK_DISTANCE_M: Final[int] = (
    100  # meters - minimum distance to count as walk
)
DEFAULT_MIN_WALK_DURATION_MIN: Final[int] = (
    5  # minutes - minimum duration to count as walk
)
DEFAULT_IDLE_TIMEOUT_MIN: Final[int] = 30  # minutes - time before auto-ending walk
WALK_DISTANCE_UPDATE_THRESHOLD_M: Final[int] = (
    10  # meters - minimum change for UI update
)
DOOR_OPEN_TIMEOUT_SECONDS: Final[int] = (
    120  # seconds - max time between door open and walk start
)

# Geofencing and safe zone parameters
DEFAULT_SAFE_ZONE_RADIUS: Final[int] = 50  # meters - default geofence radius
MAX_SAFE_ZONE_RADIUS: Final[int] = 2_000  # meters - maximum allowed geofence radius
MIN_SAFE_ZONE_RADIUS: Final[int] = 5  # meters - minimum allowed geofence radius
MIN_SIGNIFICANT_DISTANCE_M: Final[float] = (
    1.0  # meters - minimum distance change for processing
)

# ==============================================================================
# DOG HEALTH AND ACTIVITY CONSTANTS
# ==============================================================================

# Weight and size limits for validation
DEFAULT_DOG_WEIGHT_KG: Final[float] = 20.0  # kg - default weight if not specified
MAX_DOG_WEIGHT_KG: Final[float] = 200.0  # kg - maximum reasonable dog weight
MIN_DOG_WEIGHT_KG: Final[float] = 0.5  # kg - minimum reasonable dog weight
MIN_MEANINGFUL_WEIGHT: Final[float] = 0.1  # kg - minimum weight for sensor display

# Calorie calculation constants (based on veterinary guidelines)
CALORIES_PER_KM_PER_KG: Final[float] = 1.5  # calories burned per km per kg body weight
CALORIES_PER_MIN_PLAY_PER_KG: Final[float] = (
    0.25  # calories burned per minute play per kg
)

# Activity and care defaults
DEFAULT_WALK_THRESHOLD_HOURS: Final[float] = 8.0  # hours - time before dog needs walk
DEFAULT_GROOMING_INTERVAL_DAYS: Final[int] = 30  # days - default grooming interval
DEFAULT_MEDICATION_REMINDER_HOURS: Final[int] = (
    12  # hours - between medication reminders
)

# Health monitoring thresholds (normal ranges for dogs)
HEALTH_THRESHOLDS: Final[dict[str, float]] = {
    "temperature_high": 39.2,  # °C - upper normal limit
    "temperature_low": 37.2,  # °C - lower normal limit
    "heart_rate_high": 140.0,  # bpm - upper normal limit for medium dogs
    "heart_rate_low": 60.0,  # bpm - lower normal limit for medium dogs
    "respiratory_rate_high": 40.0,  # breaths/min - upper normal limit
    "respiratory_rate_low": 10.0,  # breaths/min - lower normal limit
}

# ==============================================================================
# MODULE IDENTIFIERS
# ==============================================================================

# Module keys used in dog configuration and feature toggles
MODULE_FEEDING: Final[str] = "feeding"
MODULE_GPS: Final[str] = "gps"
MODULE_HEALTH: Final[str] = "health"
MODULE_WALK: Final[str] = "walk"
MODULE_GROOMING: Final[str] = "grooming"
MODULE_TRAINING: Final[str] = "training"
MODULE_NOTIFICATIONS: Final[str] = "notifications"
MODULE_DASHBOARD: Final[str] = "dashboard"
MODULE_MEDICATION: Final[str] = "medication"

# ==============================================================================
# EVENTS AND ATTRIBUTES
# ==============================================================================

# Home Assistant bus event types fired by this integration
EVENT_WALK_STARTED: Final[str] = "pawcontrol_walk_started"
EVENT_WALK_ENDED: Final[str] = "pawcontrol_walk_ended"
EVENT_DOG_FED: Final[str] = "pawcontrol_dog_fed"
EVENT_MEDICATION_GIVEN: Final[str] = "pawcontrol_medication_given"
EVENT_GROOMING_DONE: Final[str] = "pawcontrol_grooming_done"
EVENT_TRAINING_SESSION: Final[str] = "pawcontrol_training_session"
EVENT_SAFE_ZONE_ENTERED: Final[str] = "pawcontrol_safe_zone_entered"
EVENT_SAFE_ZONE_LEFT: Final[str] = "pawcontrol_safe_zone_left"
EVENT_DAILY_RESET: Final[str] = "pawcontrol_daily_reset"

# Event attribute keys for structured data
ATTR_DOG_ID: Final[str] = "dog_id"
ATTR_DOG_NAME: Final[str] = "dog_name"
ATTR_DURATION: Final[str] = "duration"
ATTR_DISTANCE: Final[str] = "distance"
ATTR_MEAL_TYPE: Final[str] = "meal_type"
ATTR_MEDICATION: Final[str] = "medication"
ATTR_GROOMING_TYPE: Final[str] = "grooming_type"
ATTR_TRAINING_TOPIC: Final[str] = "training_topic"
ATTR_REASON: Final[str] = "reason"
ATTR_SOURCE: Final[str] = "source"

# ==============================================================================
# CONFIGURATION KEYS
# ==============================================================================

# Primary configuration sections
CONF_DOGS: Final[str] = "dogs"
CONF_SOURCES: Final[str] = "sources"
CONF_NOTIFICATIONS: Final[str] = "notifications"
CONF_MODULES: Final[str] = "modules"

# Dog configuration keys
CONF_DOG_ID: Final[str] = "dog_id"
CONF_DOG_NAME: Final[str] = "dog_name"
CONF_DOG_WEIGHT: Final[str] = "dog_weight"
CONF_DOG_SIZE: Final[str] = "dog_size"
CONF_DOG_BREED: Final[str] = "dog_breed"
CONF_DOG_AGE: Final[str] = "dog_age"
CONF_DOG_MODULES: Final[str] = "dog_modules"

# Data source configuration keys
CONF_DEVICE_TRACKERS: Final[str] = "device_trackers"
CONF_PERSON_ENTITIES: Final[str] = "person_entities"
CONF_DOOR_SENSOR: Final[str] = "door_sensor"
CONF_WEATHER: Final[str] = "weather"
CONF_CALENDAR: Final[str] = "calendar"

# Notification configuration keys
CONF_NOTIFY_BACKENDS: Final[str] = "notify_backends"
CONF_NOTIFY_FALLBACK: Final[str] = "notify_fallback"
CONF_QUIET_HOURS: Final[str] = "quiet_hours"
CONF_QUIET_START: Final[str] = "quiet_start"
CONF_QUIET_END: Final[str] = "quiet_end"
CONF_REMINDER_REPEAT: Final[str] = "reminder_repeat"
CONF_SNOOZE_MIN: Final[str] = "snooze_min"

# System configuration keys
CONF_RESET_TIME: Final[str] = "reset_time"
CONF_EXPORT_FORMAT: Final[str] = "export_format"
CONF_EXPORT_PATH: Final[str] = "export_path"
CONF_VISITOR_MODE: Final[str] = "visitor_mode"
CONF_DASHBOARD: Final[str] = "dashboard"

# Generic configuration keys
CONF_TYPE: Final[str] = "type"
CONF_DEVICE_ID: Final[str] = "device_id"
CONF_PLATFORM: Final[str] = "platform"
CONF_USERNAME: Final[str] = "username"
CONF_PASSWORD: Final[str] = "password"
CONF_DOMAIN: Final[str] = "domain"
CONF_EVENT_TYPE: Final[str] = "event_type"
CONF_EVENT_DATA: Final[str] = "event_data"
CONF_DISCOVERY_INFO: Final[str] = "discovery_info"

# ==============================================================================
# DEFAULT VALUES
# ==============================================================================

# System defaults
DEFAULT_RESET_TIME: Final[str] = "23:59:00"
DEFAULT_EXPORT_FORMAT: Final[str] = "csv"
DEFAULT_NOTIFICATION_SERVICE: Final[str] = "notify.notify"

# Notification defaults
DEFAULT_REMINDER_REPEAT: Final[int] = 30  # minutes
DEFAULT_SNOOZE_MIN: Final[int] = 15  # minutes

# ==============================================================================
# SERVICE IDENTIFIERS
# ==============================================================================

# Core services for dog management
SERVICE_START_WALK: Final[str] = "start_walk"
SERVICE_END_WALK: Final[str] = "end_walk"
SERVICE_WALK_DOG: Final[str] = "walk_dog"
SERVICE_FEED_DOG: Final[str] = "feed_dog"
SERVICE_LOG_HEALTH: Final[str] = "log_health"
SERVICE_LOG_MEDICATION: Final[str] = "log_medication"
SERVICE_START_GROOMING: Final[str] = "start_grooming"
SERVICE_PLAY_SESSION: Final[str] = "play_session"
SERVICE_TRAINING_SESSION: Final[str] = "training_session"

# GPS and tracking services
SERVICE_GPS_START_WALK: Final[str] = "gps_start_walk"
SERVICE_GPS_END_WALK: Final[str] = "gps_end_walk"
SERVICE_GPS_GENERATE_DIAGNOSTICS: Final[str] = "gps_generate_diagnostics"
SERVICE_GPS_RESET_STATS: Final[str] = "gps_reset_stats"
SERVICE_GPS_EXPORT_LAST_ROUTE: Final[str] = "gps_export_last_route"
SERVICE_GPS_PAUSE_TRACKING: Final[str] = "gps_pause_tracking"
SERVICE_GPS_RESUME_TRACKING: Final[str] = "gps_resume_tracking"
SERVICE_GPS_POST_LOCATION: Final[str] = "gps_post_location"
SERVICE_GPS_LIST_WEBHOOKS: Final[str] = "gps_list_webhooks"
SERVICE_GPS_REGENERATE_WEBHOOKS: Final[str] = "gps_regenerate_webhooks"

# System and utility services
SERVICE_DAILY_RESET: Final[str] = "daily_reset"
SERVICE_SYNC_SETUP: Final[str] = "sync_setup"
SERVICE_TOGGLE_VISITOR: Final[str] = "toggle_visitor"
SERVICE_EMERGENCY_MODE: Final[str] = "emergency_mode"
SERVICE_GENERATE_REPORT: Final[str] = "generate_report"
SERVICE_EXPORT_DATA: Final[str] = "export_data"
SERVICE_TOGGLE_GEOFENCE_ALERTS: Final[str] = "toggle_geofence_alerts"
SERVICE_EXPORT_OPTIONS: Final[str] = "export_options"
SERVICE_IMPORT_OPTIONS: Final[str] = "import_options"
SERVICE_NOTIFY_TEST: Final[str] = "notify_test"
SERVICE_PURGE_ALL_STORAGE: Final[str] = "purge_all_storage"
SERVICE_PRUNE_STALE_DEVICES: Final[str] = "prune_stale_devices"

# Route and history services
SERVICE_ROUTE_HISTORY_LIST: Final[str] = "route_history_list"
SERVICE_ROUTE_HISTORY_PURGE: Final[str] = "route_history_purge"
SERVICE_ROUTE_HISTORY_EXPORT_RANGE: Final[str] = "route_history_export_range"

# Medication services
SERVICE_SEND_MEDICATION_REMINDER: Final[str] = "send_medication_reminder"

# Service aliases for compatibility
SERVICE_PLAY_WITH_DOG: Final[str] = "play_session"
SERVICE_START_TRAINING: Final[str] = "training_session"

# ==============================================================================
# STORAGE KEYS
# ==============================================================================

# Storage keys for persistent data
STORAGE_KEY_GPS_SETTINGS: Final[str] = "gps_settings"
STORAGE_KEY_ROUTE_HISTORY: Final[str] = "route_history"
STORAGE_KEY_USER_SETTINGS: Final[str] = "user_settings"

# ==============================================================================
# MEAL AND FEEDING CONSTANTS
# ==============================================================================

# Meal type identifiers
MEAL_BREAKFAST: Final[str] = "breakfast"
MEAL_LUNCH: Final[str] = "lunch"
MEAL_DINNER: Final[str] = "dinner"
MEAL_SNACK: Final[str] = "snack"

# Food type identifiers
FOOD_DRY: Final[str] = "dry"
FOOD_WET: Final[str] = "wet"
FOOD_BARF: Final[str] = "barf"
FOOD_TREAT: Final[str] = "treat"

# Meal types with German translations for UI
MEAL_TYPES: Final[dict[str, str]] = {
    MEAL_BREAKFAST: "Frühstück",
    MEAL_LUNCH: "Mittag",
    MEAL_DINNER: "Abend",
    MEAL_SNACK: "Snack",
}

# Feeding types with German translations for UI
FEEDING_TYPES: Final[dict[str, str]] = {
    FOOD_DRY: "Trockenfutter",
    FOOD_WET: "Nassfutter",
    FOOD_BARF: "BARF",
    FOOD_TREAT: "Leckerli",
}

# ==============================================================================
# GROOMING CONSTANTS
# ==============================================================================

# Grooming task type identifiers
GROOMING_BATH: Final[str] = "bath"
GROOMING_BRUSH: Final[str] = "brush"
GROOMING_EARS: Final[str] = "ears"
GROOMING_EYES: Final[str] = "eyes"
GROOMING_NAILS: Final[str] = "nails"
GROOMING_TEETH: Final[str] = "teeth"
GROOMING_TRIM: Final[str] = "trim"

# Grooming types with German translations for UI
GROOMING_TYPES: Final[dict[str, str]] = {
    GROOMING_BATH: "Baden",
    GROOMING_BRUSH: "Bürsten",
    GROOMING_EARS: "Ohren reinigen",
    GROOMING_EYES: "Augen reinigen",
    GROOMING_NAILS: "Krallen schneiden",
    GROOMING_TEETH: "Zähne putzen",
    GROOMING_TRIM: "Fell schneiden",
}

# ==============================================================================
# ACTIVITY AND TRAINING CONSTANTS
# ==============================================================================

# Activity intensity levels
INTENSITY_LOW: Final[str] = "low"
INTENSITY_MEDIUM: Final[str] = "medium"
INTENSITY_HIGH: Final[str] = "high"

# Activity intensity with German translations for UI
INTENSITY_TYPES: Final[dict[str, str]] = {
    INTENSITY_LOW: "Niedrig",
    INTENSITY_MEDIUM: "Mittel",
    INTENSITY_HIGH: "Hoch",
}

# Training categories
TRAINING_BASIC: Final[str] = "basic"
TRAINING_TRICKS: Final[str] = "tricks"
TRAINING_AGILITY: Final[str] = "agility"
TRAINING_BEHAVIORAL: Final[str] = "behavioral"

# Training types with German translations for UI
TRAINING_TYPES: Final[dict[str, str]] = {
    TRAINING_BASIC: "Grundgehorsam",
    TRAINING_TRICKS: "Tricks",
    TRAINING_AGILITY: "Agility",
    TRAINING_BEHAVIORAL: "Verhaltenskorrektur",
}

# ==============================================================================
# HEALTH AND VACCINATION CONSTANTS
# ==============================================================================

# Vaccination identifiers and German names
VACCINATION_NAMES: Final[dict[str, str]] = {
    "rabies": "Tollwut",
    "distemper": "Staupe",
    "hepatitis": "Hepatitis",
    "parvovirus": "Parvovirose",
    "parainfluenza": "Parainfluenza",
    "leptospirosis": "Leptospirose",
    "bordetella": "Zwingerhusten",
    "lyme": "Borreliose",
}

# Vaccination intervals in months
VACCINATION_INTERVALS: Final[dict[str, int]] = {
    "rabies": 36,  # 3 years
    "distemper": 36,  # 3 years
    "hepatitis": 36,  # 3 years
    "parvovirus": 36,  # 3 years
    "parainfluenza": 12,  # 1 year
    "leptospirosis": 12,  # 1 year
    "bordetella": 12,  # 1 year
    "lyme": 12,  # 1 year
}

# Medical condition categories
CONDITION_CHRONIC: Final[str] = "chronic"
CONDITION_ACUTE: Final[str] = "acute"
CONDITION_PREVENTIVE: Final[str] = "preventive"

# ==============================================================================
# UI ICONS AND VISUAL ELEMENTS
# ==============================================================================

# Material Design Icons for different categories - optimized for better UX
ICONS: Final[dict[str, str]] = {
    # Core dog care activities
    "feeding": "mdi:food-drumstick",
    "walk": "mdi:dog-side",
    "health": "mdi:medical-bag",
    "grooming": "mdi:content-cut",
    "training": "mdi:school-outline",
    "medication": "mdi:pill",
    # Tracking and monitoring
    "gps": "mdi:crosshairs-gps",
    "location": "mdi:map-marker-radius",
    "activity": "mdi:run-fast",
    "statistics": "mdi:chart-line-variant",
    # System and interface
    "dashboard": "mdi:view-dashboard-outline",
    "notifications": "mdi:bell-outline",
    "emergency": "mdi:alert-circle",
    "visitor": "mdi:account-group",
    "settings": "mdi:cog-outline",
    # Data management
    "export": "mdi:database-export",
    "import": "mdi:database-import",
    # Status indicators
    "online": "mdi:check-circle",
    "offline": "mdi:alert-circle-outline",
    "warning": "mdi:alert-triangle",
    "error": "mdi:close-circle",
}

# Device class mappings for sensors
DEVICE_CLASSES: Final[dict[str, str]] = {
    "weight": "weight",
    "distance": "distance",
    "duration": "duration",
    "temperature": "temperature",
    "timestamp": "timestamp",
    "energy": "energy",
}

# Unit of measurement mappings
UNITS: Final[dict[str, str]] = {
    "weight": "kg",
    "distance": "m",
    "duration": "min",
    "temperature": "°C",
    "calories": "kcal",
    "speed": "km/h",
    "count": "",
}

# ==============================================================================
# DOG SIZE AND BREED CATEGORIES
# ==============================================================================

# Dog size categories
SIZE_SMALL: Final[str] = "small"
SIZE_MEDIUM: Final[str] = "medium"
SIZE_LARGE: Final[str] = "large"
SIZE_XLARGE: Final[str] = "xlarge"

# Size categories with weight ranges (kg) and German translations
DOG_SIZES: Final[dict[str, dict[str, str | tuple[float, float]]]] = {
    SIZE_SMALL: {"name": "Klein", "weight_range": (0.5, 10.0)},
    SIZE_MEDIUM: {"name": "Mittel", "weight_range": (10.0, 25.0)},
    SIZE_LARGE: {"name": "Groß", "weight_range": (25.0, 45.0)},
    SIZE_XLARGE: {"name": "Sehr groß", "weight_range": (45.0, 200.0)},
}

# ==============================================================================
# ERROR AND STATUS CODES
# ==============================================================================

# Error codes for various failure conditions - comprehensive coverage
ERROR_DOG_NOT_FOUND: Final[str] = "dog_not_found"
ERROR_INVALID_CONFIG: Final[str] = "invalid_config"
ERROR_GPS_UNAVAILABLE: Final[str] = "gps_unavailable"
ERROR_SENSOR_OFFLINE: Final[str] = "sensor_offline"
ERROR_NETWORK_ERROR: Final[str] = "network_error"
ERROR_PERMISSION_DENIED: Final[str] = "permission_denied"
ERROR_COORDINATOR_UNAVAILABLE: Final[str] = "coordinator_unavailable"
ERROR_INVALID_COORDINATES: Final[str] = "invalid_coordinates"
ERROR_DEVICE_NOT_READY: Final[str] = "device_not_ready"

# Status indicators
STATUS_ACTIVE: Final[str] = "active"
STATUS_INACTIVE: Final[str] = "inactive"
STATUS_ERROR: Final[str] = "error"
STATUS_UNKNOWN: Final[str] = "unknown"
STATUS_INITIALIZING: Final[str] = "initializing"
STATUS_READY: Final[str] = "ready"

# ==============================================================================
# COORDINATE AND PRECISION CONSTANTS
# ==============================================================================

# Coordinate precision for storage and display
COORDINATE_PRECISION: Final[int] = 6  # decimal places
DISTANCE_PRECISION: Final[int] = 1  # decimal places for distances
WEIGHT_PRECISION: Final[int] = 1  # decimal places for weights
DURATION_PRECISION: Final[int] = 1  # decimal places for durations

# ==============================================================================
# LIMITS AND VALIDATION CONSTANTS
# ==============================================================================

# Maximum values for various inputs - optimized for performance and UX
MAX_DOGS_PER_INTEGRATION: Final[int] = 10
MAX_ROUTE_POINTS: Final[int] = 10_000
MAX_HISTORY_DAYS: Final[int] = 365
MAX_STRING_LENGTH: Final[int] = 255
MAX_NOTE_LENGTH: Final[int] = 1000
MAX_CONCURRENT_UPDATES: Final[int] = 3  # Prevent coordinator overload

# Minimum values for validation
MIN_UPDATE_INTERVAL_SECONDS: Final[int] = 30
MIN_GEOFENCE_RADIUS_M: Final[int] = 5
MIN_DOG_AGE_YEARS: Final[int] = 0
MAX_DOG_AGE_YEARS: Final[int] = 30
MIN_MEANINGFUL_DISTANCE_M: Final[float] = 1.0  # For filtering noise
MIN_MEANINGFUL_DURATION_S: Final[float] = 1.0  # For filtering noise

# Time limits in seconds - performance optimized
CACHE_DURATION_SECONDS: Final[int] = 300  # 5 minutes
SESSION_TIMEOUT_SECONDS: Final[int] = 3600  # 1 hour
RETRY_DELAY_SECONDS: Final[int] = 60  # 1 minute
COORDINATOR_REFRESH_THROTTLE_SECONDS: Final[int] = 5  # Prevent spam
ENTITY_UPDATE_DEBOUNCE_SECONDS: Final[float] = 0.5  # Debounce entity updates
