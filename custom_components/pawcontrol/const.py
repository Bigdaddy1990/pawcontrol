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
from homeassistant.helpers import selector

# OPTIMIZED: Storage versions for data persistence
STORAGE_VERSION: Final[int] = 1
DASHBOARD_STORAGE_VERSION: Final[int] = 1

# OPTIMIZED: Core integration identifiers
DOMAIN: Final[str] = "pawcontrol"

# OPTIMIZED: Platforms as tuple for immutability and better performance
PLATFORMS: Final[tuple[Platform, ...]] = (
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

# OPTIMIZED: Supported device categories as tuple for immutability
DEVICE_CATEGORIES: Final[tuple[str, ...]] = (
    "gps_tracker",
    "smart_feeder",
    "activity_monitor",
    "health_device",
    "smart_collar",
    "treat_dispenser",
    "water_fountain",
    "camera",
    "door_sensor",
)

# OPTIMIZED: Core configuration constants - grouped for better locality
CONF_NAME: Final[str] = "name"
CONF_DOGS: Final[str] = "dogs"
CONF_DOG_ID: Final[str] = "dog_id"
CONF_DOG_NAME: Final[str] = "dog_name"
CONF_DOG_BREED: Final[str] = "dog_breed"
CONF_DOG_AGE: Final[str] = "dog_age"
CONF_DOG_WEIGHT: Final[str] = "dog_weight"
CONF_DOG_SIZE: Final[str] = "dog_size"
CONF_DOG_COLOR: Final[str] = "dog_color"

# OPTIMIZED: Module configuration as frozenset for fast lookups
CONF_MODULES: Final[str] = "modules"
MODULE_GPS: Final[str] = "gps"
MODULE_FEEDING: Final[str] = "feeding"
MODULE_HEALTH: Final[str] = "health"
MODULE_WALK: Final[str] = "walk"
MODULE_NOTIFICATIONS: Final[str] = "notifications"
MODULE_DASHBOARD: Final[str] = "dashboard"
MODULE_VISITOR: Final[str] = "visitor"
MODULE_GROOMING: Final[str] = "grooming"
MODULE_MEDICATION: Final[str] = "medication"
MODULE_TRAINING: Final[str] = "training"

# OPTIMIZED: All modules as frozenset for O(1) membership testing
ALL_MODULES: Final[frozenset[str]] = frozenset(
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
CONF_SOURCES: Final[str] = "sources"
CONF_DOOR_SENSOR: Final[str] = "door_sensor"
CONF_PERSON_ENTITIES: Final[str] = "person_entities"
CONF_DEVICE_TRACKERS: Final[str] = "device_trackers"
CONF_NOTIFY_FALLBACK: Final[str] = "notify_fallback"
CONF_CALENDAR: Final[str] = "calendar"
CONF_WEATHER: Final[str] = "weather"

# OPTIMIZED: GPS configuration constants
CONF_GPS_SOURCE: Final[str] = "gps_source"
CONF_GPS_UPDATE_INTERVAL: Final[str] = "gps_update_interval"
CONF_GPS_ACCURACY_FILTER: Final[str] = "gps_accuracy_filter"
CONF_GPS_DISTANCE_FILTER: Final[str] = "gps_distance_filter"
CONF_HOME_ZONE_RADIUS: Final[str] = "home_zone_radius"
CONF_AUTO_WALK_DETECTION: Final[str] = "auto_walk_detection"
CONF_GEOFENCING: Final[str] = "geofencing"
CONF_GEOFENCE_ZONES: Final[str] = "geofence_zones"

# OPTIMIZED: Notification configuration
CONF_NOTIFICATIONS: Final[str] = "notifications"
CONF_QUIET_HOURS: Final[str] = "quiet_hours"
CONF_QUIET_START: Final[str] = "quiet_start"
CONF_QUIET_END: Final[str] = "quiet_end"
CONF_REMINDER_REPEAT_MIN: Final[str] = "reminder_repeat_min"
CONF_SNOOZE_MIN: Final[str] = "snooze_min"
CONF_PRIORITY_NOTIFICATIONS: Final[str] = "priority_notifications"

# OPTIMIZED: Feeding configuration
CONF_FEEDING_TIMES: Final[str] = "feeding_times"
CONF_BREAKFAST_TIME: Final[str] = "breakfast_time"
CONF_LUNCH_TIME: Final[str] = "lunch_time"
CONF_DINNER_TIME: Final[str] = "dinner_time"
CONF_SNACK_TIMES: Final[str] = "snack_times"
CONF_DAILY_FOOD_AMOUNT: Final[str] = "daily_food_amount"
CONF_MEALS_PER_DAY: Final[str] = "meals_per_day"
CONF_FOOD_TYPE: Final[str] = "food_type"
CONF_SPECIAL_DIET: Final[str] = "special_diet"
CONF_FEEDING_SCHEDULE_TYPE: Final[str] = "feeding_schedule_type"
CONF_PORTION_CALCULATION: Final[str] = "portion_calculation"
CONF_MEDICATION_WITH_MEALS: Final[str] = "medication_with_meals"

# OPTIMIZED: Health configuration
CONF_HEALTH_TRACKING: Final[str] = "health_tracking"
CONF_WEIGHT_TRACKING: Final[str] = "weight_tracking"
CONF_MEDICATION_REMINDERS: Final[str] = "medication_reminders"
CONF_VET_REMINDERS: Final[str] = "vet_reminders"
CONF_GROOMING_INTERVAL: Final[str] = "grooming_interval"

# OPTIMIZED: System configuration
CONF_RESET_TIME: Final[str] = "reset_time"
CONF_DASHBOARD_MODE: Final[str] = "dashboard_mode"
CONF_DATA_RETENTION_DAYS: Final[str] = "data_retention_days"
CONF_AUTO_BACKUP: Final[str] = "auto_backup"
CONF_EXTERNAL_INTEGRATIONS: Final[str] = "external_integrations"

# OPTIMIZED: Default values as immutable constants
DEFAULT_RESET_TIME: Final[str] = "23:59:00"
DEFAULT_GPS_UPDATE_INTERVAL: Final[int] = 60
DEFAULT_GPS_ACCURACY_FILTER: Final[int] = 100
DEFAULT_GPS_DISTANCE_FILTER: Final[int] = 10
DEFAULT_HOME_ZONE_RADIUS: Final[int] = 50
DEFAULT_REMINDER_REPEAT_MIN: Final[int] = 30
DEFAULT_SNOOZE_MIN: Final[int] = 15
DEFAULT_DATA_RETENTION_DAYS: Final[int] = 90
DEFAULT_GROOMING_INTERVAL: Final[int] = 28

# OPTIMIZED: Reusable selector configurations
GPS_UPDATE_INTERVAL_SELECTOR: Final[selector.NumberSelector] = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=30,
        max=600,
        step=10,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="seconds",
    )
)

GPS_ACCURACY_FILTER_SELECTOR: Final[selector.NumberSelector] = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=5,
        max=500,
        step=5,
        mode=selector.NumberSelectorMode.BOX,
        unit_of_measurement="meters",
    )
)

# OPTIMIZED: Food types as tuple for immutability (better performance than list)
FOOD_TYPES: Final[tuple[str, ...]] = (
    "dry_food",
    "wet_food",
    "barf",
    "home_cooked",
    "mixed",
)

# OPTIMIZED: Special diet options as tuple
SPECIAL_DIET_OPTIONS: Final[tuple[str, ...]] = (
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

# OPTIMIZED: Schedule types as tuple for better performance
FEEDING_SCHEDULE_TYPES: Final[tuple[str, ...]] = ("flexible", "strict", "custom")

# OPTIMIZED: Meal types as tuple
MEAL_TYPES: Final[tuple[str, ...]] = ("breakfast", "lunch", "dinner", "snack")

# OPTIMIZED: Dog sizes as tuple for consistency and performance
DOG_SIZES: Final[tuple[str, ...]] = ("toy", "small", "medium", "large", "giant")

# OPTIMIZED: Size-weight mapping for validation (frozenset for fast lookup)
DOG_SIZE_WEIGHT_RANGES: Final[dict[str, tuple[float, float]]] = {
    "toy": (1.0, 6.0),
    "small": (4.0, 15.0),
    "medium": (8.0, 30.0),
    "large": (22.0, 50.0),
    "giant": (35.0, 90.0),
}

# OPTIMIZED: GPS sources as tuple
GPS_SOURCES: Final[tuple[str, ...]] = (
    "manual",
    "device_tracker",
    "person_entity",
    "smartphone",
    "tractive",
    "webhook",
    "mqtt",
)

# OPTIMIZED: Status and mood options as tuples
HEALTH_STATUS_OPTIONS: Final[tuple[str, ...]] = (
    "excellent",
    "very_good",
    "good",
    "normal",
    "unwell",
    "sick",
)

MOOD_OPTIONS: Final[tuple[str, ...]] = (
    "happy",
    "neutral",
    "sad",
    "angry",
    "anxious",
    "tired",
)

ACTIVITY_LEVELS: Final[tuple[str, ...]] = (
    "very_low",
    "low",
    "normal",
    "high",
    "very_high",
)

# OPTIMIZED: Dashboard configuration
DASHBOARD_MODES: Final[tuple[str, ...]] = ("full", "cards", "minimal")

DASHBOARD_MODE_SELECTOR_OPTIONS: Final[tuple[dict[str, str], ...]] = (
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
)

CONF_DASHBOARD_ENABLED: Final[str] = "dashboard_enabled"
CONF_DASHBOARD_AUTO_CREATE: Final[str] = "dashboard_auto_create"
CONF_DASHBOARD_THEME: Final[str] = "dashboard_theme"
CONF_DASHBOARD_CARDS: Final[str] = "dashboard_cards"
CONF_DASHBOARD_VIEWS: Final[str] = "dashboard_views"
CONF_DASHBOARD_PER_DOG: Final[str] = "dashboard_per_dog"

# OPTIMIZED: Dashboard defaults
DEFAULT_DASHBOARD_ENABLED: Final[bool] = True
DEFAULT_DASHBOARD_AUTO_CREATE: Final[bool] = True
DEFAULT_DASHBOARD_THEME: Final[str] = "default"
DEFAULT_DASHBOARD_MODE: Final[str] = "full"

# OPTIMIZED: Performance modes as tuple
PERFORMANCE_MODES: Final[tuple[str, ...]] = ("minimal", "standard", "full")

# OPTIMIZED: Service names - grouped by functionality
SERVICE_FEED_DOG: Final[str] = "feed_dog"
SERVICE_START_WALK: Final[str] = "start_walk"
SERVICE_END_WALK: Final[str] = "end_walk"
SERVICE_LOG_POOP: Final[str] = "log_poop"
SERVICE_LOG_HEALTH: Final[str] = "log_health_data"
SERVICE_LOG_MEDICATION: Final[str] = "log_medication"
SERVICE_START_GROOMING: Final[str] = "start_grooming"
SERVICE_TOGGLE_VISITOR_MODE: Final[str] = "toggle_visitor_mode"
SERVICE_NOTIFY_TEST: Final[str] = "notify_test"
SERVICE_DAILY_RESET: Final[str] = "daily_reset"
SERVICE_GENERATE_REPORT: Final[str] = "generate_report"
SERVICE_GPS_START_WALK: Final[str] = "gps_start_walk"
SERVICE_GPS_END_WALK: Final[str] = "gps_end_walk"
SERVICE_GPS_POST_LOCATION: Final[str] = "gps_post_location"
SERVICE_GPS_EXPORT_ROUTE: Final[str] = "gps_export_last_route"

# OPTIMIZED: Automation services from docs/automations_health_feeding.md
SERVICE_RECALCULATE_HEALTH_PORTIONS: Final[str] = "recalculate_health_portions"
SERVICE_ADJUST_CALORIES_FOR_ACTIVITY: Final[str] = "adjust_calories_for_activity"
SERVICE_ACTIVATE_DIABETIC_FEEDING_MODE: Final[str] = "activate_diabetic_feeding_mode"
SERVICE_FEED_WITH_MEDICATION: Final[str] = "feed_with_medication"
SERVICE_GENERATE_WEEKLY_HEALTH_REPORT: Final[str] = "generate_weekly_health_report"
SERVICE_ACTIVATE_EMERGENCY_FEEDING_MODE: Final[str] = "activate_emergency_feeding_mode"
SERVICE_START_DIET_TRANSITION: Final[str] = "start_diet_transition"
SERVICE_CHECK_FEEDING_COMPLIANCE: Final[str] = "check_feeding_compliance"
SERVICE_ADJUST_DAILY_PORTIONS: Final[str] = "adjust_daily_portions"
SERVICE_ADD_HEALTH_SNACK: Final[str] = "add_health_snack"

# OPTIMIZED: Core services as frozenset for fast lookup
CORE_SERVICES: Final[frozenset[str]] = frozenset(
    [
        SERVICE_FEED_DOG,
        SERVICE_START_WALK,
        SERVICE_END_WALK,
        SERVICE_LOG_HEALTH,
        SERVICE_NOTIFY_TEST,
    ]
)

# OPTIMIZED: Entity and event identifiers
ENTITY_ID_FORMAT: Final[str] = "pawcontrol_{dog_id}_{entity_type}_{purpose}"

# OPTIMIZED: Event types as constants
EVENT_WALK_STARTED: Final[str] = "pawcontrol_walk_started"
EVENT_WALK_ENDED: Final[str] = "pawcontrol_walk_ended"
EVENT_FEEDING_LOGGED: Final[str] = "pawcontrol_feeding_logged"
EVENT_HEALTH_LOGGED: Final[str] = "pawcontrol_health_logged"
EVENT_GEOFENCE_ENTERED: Final[str] = "pawcontrol_geofence_entered"
EVENT_GEOFENCE_LEFT: Final[str] = "pawcontrol_geofence_left"
EVENT_GARDEN_ENTERED: Final[str] = "pawcontrol_garden_entered"
EVENT_GARDEN_LEFT: Final[str] = "pawcontrol_garden_left"

# OPTIMIZED: State attributes - grouped by category
ATTR_DOG_ID: Final[str] = "dog_id"
ATTR_DOG_NAME: Final[str] = "dog_name"
ATTR_TIMESTAMP: Final[str] = "timestamp"

# Feeding attributes
ATTR_MEAL_TYPE: Final[str] = "meal_type"
ATTR_PORTION_SIZE: Final[str] = "portion_size"

# Walk/GPS attributes
ATTR_WALK_DURATION: Final[str] = "walk_duration"
ATTR_WALK_DISTANCE: Final[str] = "walk_distance"
ATTR_GPS_ACCURACY: Final[str] = "gps_accuracy"
ATTR_ZONE_NAME: Final[str] = "zone_name"

# Health attributes
ATTR_HEALTH_STATUS: Final[str] = "health_status"
ATTR_WEIGHT: Final[str] = "weight"
ATTR_MEDICATION_NAME: Final[str] = "medication_name"
ATTR_DOSE: Final[str] = "dose"

# OPTIMIZED: Time constants as immutable values
SECONDS_IN_HOUR: Final[int] = 3600
SECONDS_IN_DAY: Final[int] = 86400
MINUTES_IN_HOUR: Final[int] = 60

# OPTIMIZED: Type definitions as tuples
GEOFENCE_TYPES: Final[tuple[str, ...]] = (
    "safe_zone",
    "restricted_area",
    "point_of_interest",
)
NOTIFICATION_CHANNELS: Final[tuple[str, ...]] = (
    "persistent",
    "mobile",
    "email",
    "sms",
    "webhook",
    "tts",
    "media_player",
    "slack",
    "discord",
)

# PLATINUM: Update intervals with consistent key naming throughout codebase
UPDATE_INTERVALS: Final[dict[str, int]] = {
    "minimal": 300,  # 5 minutes - power saving
    "standard": 120,  # 2 minutes - balanced (FIXED: consistent key)
    "frequent": 60,  # 1 minute - responsive
    "real_time": 30,  # 30 seconds - high performance
}

# OPTIMIZED: Data file names as constants
DATA_FILE_WALKS: Final[str] = "walks.json"
DATA_FILE_FEEDINGS: Final[str] = "feedings.json"
DATA_FILE_HEALTH: Final[str] = "health.json"
DATA_FILE_ROUTES: Final[str] = "routes.json"
DATA_FILE_STATS: Final[str] = "statistics.json"

# OPTIMIZED: Validation limits as immutable constants
MIN_DOG_NAME_LENGTH: Final[int] = 2
MAX_DOG_NAME_LENGTH: Final[int] = 30
MIN_DOG_WEIGHT: Final[float] = 0.5
MAX_DOG_WEIGHT: Final[float] = 200.0
MIN_DOG_AGE: Final[int] = 0
MAX_DOG_AGE: Final[int] = 30
MIN_GEOFENCE_RADIUS: Final[int] = 10
MAX_GEOFENCE_RADIUS: Final[int] = 10000

# OPTIMIZED: Error codes as constants
ERROR_DOG_NOT_FOUND: Final[str] = "dog_not_found"
ERROR_INVALID_CONFIG: Final[str] = "invalid_config"
ERROR_GPS_UNAVAILABLE: Final[str] = "gps_unavailable"
ERROR_NOTIFICATION_FAILED: Final[str] = "notification_failed"
ERROR_SERVICE_UNAVAILABLE: Final[str] = "service_unavailable"

# OPTIMIZED: Performance thresholds for monitoring
PERFORMANCE_THRESHOLDS: Final[dict[str, float]] = {
    "update_timeout": 30.0,  # seconds
    "cache_hit_rate_min": 70.0,  # percentage
    "memory_usage_max": 100.0,  # MB
    "response_time_max": 2.0,  # seconds
}

# OPTIMIZED: Streamlined exports - only frequently used constants
__all__ = (
    "ACTIVITY_LEVELS",
    "ALL_MODULES",
    # Dashboard configuration
    "CONF_DASHBOARD_ENABLED",
    # Configuration keys (most commonly used)
    "CONF_DOGS",
    "CONF_DOG_ID",
    "CONF_DOG_NAME",
    "CONF_MODULES",
    "CORE_SERVICES",
    "DEFAULT_DASHBOARD_ENABLED",
    "DEFAULT_GPS_UPDATE_INTERVAL",
    "DOG_SIZES",
    "DOG_SIZE_WEIGHT_RANGES",
    # Core essentials
    "DOMAIN",
    "EVENT_FEEDING_LOGGED",
    "EVENT_HEALTH_LOGGED",
    # Event types
    "EVENT_WALK_STARTED",
    # Validation constants
    "FOOD_TYPES",
    "HEALTH_STATUS_OPTIONS",
    "MAX_DOG_WEIGHT",
    # Limits and defaults
    "MIN_DOG_WEIGHT",
    "MODULE_DASHBOARD",
    "MODULE_FEEDING",
    # Module identifiers
    "MODULE_GPS",
    "MODULE_HEALTH",
    "MODULE_NOTIFICATIONS",
    "MODULE_VISITOR",
    "MODULE_WALK",
    "PERFORMANCE_THRESHOLDS",
    "PLATFORMS",
    # Service identifiers
    "SERVICE_FEED_DOG",
    "SERVICE_LOG_HEALTH",
    "SERVICE_START_WALK",
    # Performance constants
    "UPDATE_INTERVALS",
)
