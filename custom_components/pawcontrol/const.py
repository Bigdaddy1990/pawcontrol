"""Optimized constants for the Paw Control integration.

OPTIMIZED for HA 2025.9.1+ with enhanced performance patterns:
- Frozen sets for O(1) lookups
- Tuples for immutable sequences
- Streamlined exports
- Memory-efficient data structures

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# OPTIMIZED: Storage versions for data persistence
STORAGE_VERSION: Final = 1
DASHBOARD_STORAGE_VERSION: Final = 1

# OPTIMIZED: Core integration identifiers
DOMAIN: Final = "pawcontrol"

# OPTIMIZED: Platforms as tuple for immutability and better performance
PLATFORMS: Final = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.DEVICE_TRACKER,
    Platform.DATE,
    Platform.DATETIME,
)

# OPTIMIZED: Core configuration constants - grouped for better locality
CONF_NAME: Final = "name"
CONF_DOGS: Final = "dogs"
CONF_DOG_ID: Final = "dog_id"
CONF_DOG_NAME: Final = "dog_name"
CONF_DOG_BREED: Final = "dog_breed"
CONF_DOG_AGE: Final = "dog_age"
CONF_DOG_WEIGHT: Final = "dog_weight"
CONF_DOG_SIZE: Final = "dog_size"
CONF_DOG_COLOR: Final = "dog_color"

# OPTIMIZED: Module configuration as frozenset for fast lookups
CONF_MODULES: Final = "modules"
MODULE_GPS: Final = "gps"
MODULE_FEEDING: Final = "feeding"
MODULE_HEALTH: Final = "health"
MODULE_WALK: Final = "walk"
MODULE_NOTIFICATIONS: Final = "notifications"
MODULE_DASHBOARD: Final = "dashboard"
MODULE_VISITOR: Final = "visitor"
MODULE_GROOMING: Final = "grooming"
MODULE_MEDICATION: Final = "medication"
MODULE_TRAINING: Final = "training"

# OPTIMIZED: All modules as frozenset for O(1) membership testing
ALL_MODULES: Final = frozenset(
    [
        MODULE_GPS,
        MODULE_FEEDING,
        MODULE_HEALTH,
        MODULE_WALK,
        MODULE_NOTIFICATIONS,
        MODULE_DASHBOARD,
        MODULE_VISITOR,
        MODULE_GROOMING,
        MODULE_MEDICATION,
        MODULE_TRAINING,
    ]
)

# OPTIMIZED: Source entities configuration
CONF_SOURCES: Final = "sources"
CONF_DOOR_SENSOR: Final = "door_sensor"
CONF_PERSON_ENTITIES: Final = "person_entities"
CONF_DEVICE_TRACKERS: Final = "device_trackers"
CONF_NOTIFY_FALLBACK: Final = "notify_fallback"
CONF_CALENDAR: Final = "calendar"
CONF_WEATHER: Final = "weather"

# OPTIMIZED: GPS configuration constants
CONF_GPS_SOURCE: Final = "gps_source"
CONF_GPS_UPDATE_INTERVAL: Final = "gps_update_interval"
CONF_GPS_ACCURACY_FILTER: Final = "gps_accuracy_filter"
CONF_GPS_DISTANCE_FILTER: Final = "gps_distance_filter"
CONF_HOME_ZONE_RADIUS: Final = "home_zone_radius"
CONF_AUTO_WALK_DETECTION: Final = "auto_walk_detection"
CONF_GEOFENCING: Final = "geofencing"
CONF_GEOFENCE_ZONES: Final = "geofence_zones"

# OPTIMIZED: Notification configuration
CONF_NOTIFICATIONS: Final = "notifications"
CONF_QUIET_HOURS: Final = "quiet_hours"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_REMINDER_REPEAT_MIN: Final = "reminder_repeat_min"
CONF_SNOOZE_MIN: Final = "snooze_min"
CONF_PRIORITY_NOTIFICATIONS: Final = "priority_notifications"

# OPTIMIZED: Feeding configuration
CONF_FEEDING_TIMES: Final = "feeding_times"
CONF_BREAKFAST_TIME: Final = "breakfast_time"
CONF_LUNCH_TIME: Final = "lunch_time"
CONF_DINNER_TIME: Final = "dinner_time"
CONF_SNACK_TIMES: Final = "snack_times"
CONF_DAILY_FOOD_AMOUNT: Final = "daily_food_amount"
CONF_MEALS_PER_DAY: Final = "meals_per_day"
CONF_FOOD_TYPE: Final = "food_type"
CONF_SPECIAL_DIET: Final = "special_diet"
CONF_FEEDING_SCHEDULE_TYPE: Final = "feeding_schedule_type"
CONF_PORTION_CALCULATION: Final = "portion_calculation"
CONF_MEDICATION_WITH_MEALS: Final = "medication_with_meals"

# OPTIMIZED: Health configuration
CONF_HEALTH_TRACKING: Final = "health_tracking"
CONF_WEIGHT_TRACKING: Final = "weight_tracking"
CONF_MEDICATION_REMINDERS: Final = "medication_reminders"
CONF_VET_REMINDERS: Final = "vet_reminders"
CONF_GROOMING_INTERVAL: Final = "grooming_interval"

# OPTIMIZED: System configuration
CONF_RESET_TIME: Final = "reset_time"
CONF_DASHBOARD_MODE: Final = "dashboard_mode"
CONF_DATA_RETENTION_DAYS: Final = "data_retention_days"
CONF_AUTO_BACKUP: Final = "auto_backup"

# OPTIMIZED: Default values as immutable constants
DEFAULT_RESET_TIME: Final = "23:59:00"
DEFAULT_GPS_UPDATE_INTERVAL: Final = 60
DEFAULT_GPS_ACCURACY_FILTER: Final = 100
DEFAULT_GPS_DISTANCE_FILTER: Final = 10
DEFAULT_HOME_ZONE_RADIUS: Final = 50
DEFAULT_REMINDER_REPEAT_MIN: Final = 30
DEFAULT_SNOOZE_MIN: Final = 15
DEFAULT_DATA_RETENTION_DAYS: Final = 90
DEFAULT_GROOMING_INTERVAL: Final = 28

# OPTIMIZED: Food types as tuple for immutability
FOOD_TYPES: Final = ("dry_food", "wet_food", "barf", "home_cooked", "mixed")

# OPTIMIZED: Special diet options as tuple
SPECIAL_DIET_OPTIONS: Final = (
    "grain_free",
    "hypoallergenic",
    "low_fat",
    "senior_formula",
    "puppy_formula",
    "weight_control",
    "sensitive_stomach",
    "organic",
    "raw_diet",
    "prescription",
    "diabetic",
    "kidney_support",
    "dental_care",
    "joint_support",
)

# OPTIMIZED: Schedule types as tuple
FEEDING_SCHEDULE_TYPES: Final = ("flexible", "strict", "custom")
MEAL_TYPES: Final = ("breakfast", "lunch", "dinner", "snack")

# OPTIMIZED: Dog sizes as tuple with enhanced metadata
DOG_SIZES: Final = ("toy", "small", "medium", "large", "giant")

# OPTIMIZED: Size-weight mapping for validation (frozenset for fast lookup)
DOG_SIZE_WEIGHT_RANGES: Final = {
    "toy": (1.0, 6.0),
    "small": (4.0, 15.0),
    "medium": (8.0, 30.0),
    "large": (22.0, 50.0),
    "giant": (35.0, 90.0),
}

# OPTIMIZED: GPS sources as tuple
GPS_SOURCES: Final = (
    "manual",
    "device_tracker",
    "person_entity",
    "smartphone",
    "tractive",
    "webhook",
    "mqtt",
)

# OPTIMIZED: Status options as tuples
HEALTH_STATUS_OPTIONS: Final = (
    "excellent",
    "very_good",
    "good",
    "normal",
    "unwell",
    "sick",
)

MOOD_OPTIONS: Final = ("happy", "neutral", "sad", "angry", "anxious", "tired")

ACTIVITY_LEVELS: Final = ("very_low", "low", "normal", "high", "very_high")

# OPTIMIZED: Dashboard configuration
DASHBOARD_MODES: Final = ("full", "cards", "minimal")
DASHBOARD_MODE_SELECTOR_OPTIONS: Final = [
    {
        "value": "full",
        "label": "Full - Complete dashboard with all features",
    },
    {
        "value": "cards",
        "label": "Cards - Organized card-based layout",
    },
    {
        "value": "minimal",
        "label": "Minimal - Essential information only",
    },
]

CONF_DASHBOARD_ENABLED: Final = "dashboard_enabled"
CONF_DASHBOARD_AUTO_CREATE: Final = "dashboard_auto_create"
CONF_DASHBOARD_THEME: Final = "dashboard_theme"
CONF_DASHBOARD_CARDS: Final = "dashboard_cards"
CONF_DASHBOARD_VIEWS: Final = "dashboard_views"
CONF_DASHBOARD_PER_DOG: Final = "dashboard_per_dog"

# OPTIMIZED: Dashboard defaults
DEFAULT_DASHBOARD_ENABLED: Final = True
DEFAULT_DASHBOARD_AUTO_CREATE: Final = True
DEFAULT_DASHBOARD_THEME: Final = "default"
DEFAULT_DASHBOARD_MODE: Final = "full"

# OPTIMIZED: Performance modes as tuple
PERFORMANCE_MODES: Final = ("minimal", "balanced", "full")

# OPTIMIZED: Service names - grouped by functionality
SERVICE_FEED_DOG: Final = "feed_dog"
SERVICE_START_WALK: Final = "start_walk"
SERVICE_END_WALK: Final = "end_walk"
SERVICE_LOG_POOP: Final = "log_poop"
SERVICE_LOG_HEALTH: Final = "log_health_data"
SERVICE_LOG_MEDICATION: Final = "log_medication"
SERVICE_START_GROOMING: Final = "start_grooming"
SERVICE_TOGGLE_VISITOR_MODE: Final = "toggle_visitor_mode"
SERVICE_NOTIFY_TEST: Final = "notify_test"
SERVICE_DAILY_RESET: Final = "daily_reset"
SERVICE_GENERATE_REPORT: Final = "generate_report"
SERVICE_GPS_START_WALK: Final = "gps_start_walk"
SERVICE_GPS_END_WALK: Final = "gps_end_walk"
SERVICE_GPS_POST_LOCATION: Final = "gps_post_location"
SERVICE_GPS_EXPORT_ROUTE: Final = "gps_export_last_route"

# OPTIMIZED: Core services as frozenset for fast lookup
CORE_SERVICES: Final = frozenset(
    [
        SERVICE_FEED_DOG,
        SERVICE_START_WALK,
        SERVICE_END_WALK,
        SERVICE_LOG_HEALTH,
        SERVICE_NOTIFY_TEST,
    ]
)

# OPTIMIZED: Entity and event identifiers
ENTITY_ID_FORMAT: Final = "pawcontrol_{dog_id}_{entity_type}_{purpose}"

# OPTIMIZED: Event types as constants
EVENT_WALK_STARTED: Final = "pawcontrol_walk_started"
EVENT_WALK_ENDED: Final = "pawcontrol_walk_ended"
EVENT_FEEDING_LOGGED: Final = "pawcontrol_feeding_logged"
EVENT_HEALTH_LOGGED: Final = "pawcontrol_health_logged"
EVENT_GEOFENCE_ENTERED: Final = "pawcontrol_geofence_entered"
EVENT_GEOFENCE_LEFT: Final = "pawcontrol_geofence_left"

# OPTIMIZED: State attributes - grouped by category
ATTR_DOG_ID: Final = "dog_id"
ATTR_DOG_NAME: Final = "dog_name"
ATTR_TIMESTAMP: Final = "timestamp"

# Feeding attributes
ATTR_MEAL_TYPE: Final = "meal_type"
ATTR_PORTION_SIZE: Final = "portion_size"

# Walk/GPS attributes
ATTR_WALK_DURATION: Final = "walk_duration"
ATTR_WALK_DISTANCE: Final = "walk_distance"
ATTR_GPS_ACCURACY: Final = "gps_accuracy"
ATTR_ZONE_NAME: Final = "zone_name"

# Health attributes
ATTR_HEALTH_STATUS: Final = "health_status"
ATTR_WEIGHT: Final = "weight"
ATTR_MEDICATION_NAME: Final = "medication_name"
ATTR_DOSE: Final = "dose"

# OPTIMIZED: Time constants as immutable values
SECONDS_IN_HOUR: Final = 3600
SECONDS_IN_DAY: Final = 86400
MINUTES_IN_HOUR: Final = 60

# OPTIMIZED: Type definitions as tuples
GEOFENCE_TYPES: Final = ("safe_zone", "restricted_area", "point_of_interest")
NOTIFICATION_CHANNELS: Final = ("mobile", "persistent", "email", "slack")

# OPTIMIZED: Update intervals with better performance tiers
UPDATE_INTERVALS: Final = {
    "minimal": 300,  # 5 minutes - power saving
    "balanced": 120,  # 2 minutes - balanced
    "frequent": 60,  # 1 minute - responsive
    "real_time": 30,  # 30 seconds - high performance
}

# OPTIMIZED: Data file names as constants
DATA_FILE_WALKS: Final = "walks.json"
DATA_FILE_FEEDINGS: Final = "feedings.json"
DATA_FILE_HEALTH: Final = "health.json"
DATA_FILE_ROUTES: Final = "routes.json"
DATA_FILE_STATS: Final = "statistics.json"

# OPTIMIZED: Validation limits as immutable constants
MIN_DOG_NAME_LENGTH: Final = 2
MAX_DOG_NAME_LENGTH: Final = 30
MIN_DOG_WEIGHT: Final = 0.5
MAX_DOG_WEIGHT: Final = 200.0
MIN_DOG_AGE: Final = 0
MAX_DOG_AGE: Final = 30
MIN_GEOFENCE_RADIUS: Final = 10
MAX_GEOFENCE_RADIUS: Final = 10000

# OPTIMIZED: Error codes as constants
ERROR_DOG_NOT_FOUND: Final = "dog_not_found"
ERROR_INVALID_CONFIG: Final = "invalid_config"
ERROR_GPS_UNAVAILABLE: Final = "gps_unavailable"
ERROR_NOTIFICATION_FAILED: Final = "notification_failed"
ERROR_SERVICE_UNAVAILABLE: Final = "service_unavailable"

# OPTIMIZED: Performance thresholds for monitoring
PERFORMANCE_THRESHOLDS: Final = {
    "update_timeout": 30.0,  # seconds
    "cache_hit_rate_min": 70.0,  # percentage
    "memory_usage_max": 100.0,  # MB
    "response_time_max": 2.0,  # seconds
}

# OPTIMIZED: Streamlined exports - only frequently used constants
__all__ = (
    # Core essentials
    "DOMAIN",
    "PLATFORMS",
    "ALL_MODULES",
    # Configuration keys (most commonly used)
    "CONF_DOGS",
    "CONF_DOG_ID",
    "CONF_DOG_NAME",
    "CONF_MODULES",
    # Module identifiers
    "MODULE_GPS",
    "MODULE_FEEDING",
    "MODULE_HEALTH",
    "MODULE_WALK",
    "MODULE_NOTIFICATIONS",
    "MODULE_DASHBOARD",
    "MODULE_VISITOR",
    # Validation constants
    "FOOD_TYPES",
    "DOG_SIZES",
    "DOG_SIZE_WEIGHT_RANGES",
    "HEALTH_STATUS_OPTIONS",
    "ACTIVITY_LEVELS",
    # Service identifiers
    "SERVICE_FEED_DOG",
    "SERVICE_START_WALK",
    "SERVICE_LOG_HEALTH",
    "CORE_SERVICES",
    # Event types
    "EVENT_WALK_STARTED",
    "EVENT_FEEDING_LOGGED",
    "EVENT_HEALTH_LOGGED",
    # Performance constants
    "UPDATE_INTERVALS",
    "PERFORMANCE_THRESHOLDS",
    # Limits and defaults
    "MIN_DOG_WEIGHT",
    "MAX_DOG_WEIGHT",
    "DEFAULT_GPS_UPDATE_INTERVAL",
    # Dashboard configuration
    "CONF_DASHBOARD_ENABLED",
    "DEFAULT_DASHBOARD_ENABLED",
)
