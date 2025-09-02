"""Constants for the Paw Control integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# Storage version for data persistence
STORAGE_VERSION: Final = 1
DASHBOARD_STORAGE_VERSION: Final = 1

# Integration domain
DOMAIN: Final = "pawcontrol"

# Supported platforms for this integration
PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.DATE,
    Platform.DATETIME,
]

# Config flow constants
CONF_NAME: Final = "name"  # Integration instance name
CONF_DOGS: Final = "dogs"
CONF_DOG_ID: Final = "dog_id"
CONF_DOG_NAME: Final = "dog_name"
CONF_DOG_BREED: Final = "dog_breed"
CONF_DOG_AGE: Final = "dog_age"
CONF_DOG_WEIGHT: Final = "dog_weight"
CONF_DOG_SIZE: Final = "dog_size"
CONF_DOG_COLOR: Final = "dog_color"

# Module configuration
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

# Source entities
CONF_SOURCES: Final = "sources"
CONF_DOOR_SENSOR: Final = "door_sensor"
CONF_PERSON_ENTITIES: Final = "person_entities"
CONF_DEVICE_TRACKERS: Final = "device_trackers"
CONF_NOTIFY_FALLBACK: Final = "notify_fallback"
CONF_CALENDAR: Final = "calendar"
CONF_WEATHER: Final = "weather"

# GPS configuration
CONF_GPS_SOURCE: Final = "gps_source"
CONF_GPS_UPDATE_INTERVAL: Final = "gps_update_interval"
CONF_GPS_ACCURACY_FILTER: Final = "gps_accuracy_filter"
CONF_GPS_DISTANCE_FILTER: Final = "gps_distance_filter"
CONF_HOME_ZONE_RADIUS: Final = "home_zone_radius"
CONF_AUTO_WALK_DETECTION: Final = "auto_walk_detection"
CONF_GEOFENCING: Final = "geofencing"
CONF_GEOFENCE_ZONES: Final = "geofence_zones"

# Notification configuration
CONF_NOTIFICATIONS: Final = "notifications"
CONF_QUIET_HOURS: Final = "quiet_hours"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_REMINDER_REPEAT_MIN: Final = "reminder_repeat_min"
CONF_SNOOZE_MIN: Final = "snooze_min"
CONF_PRIORITY_NOTIFICATIONS: Final = "priority_notifications"

# Feeding configuration
CONF_FEEDING_TIMES: Final = "feeding_times"
CONF_BREAKFAST_TIME: Final = "breakfast_time"
CONF_LUNCH_TIME: Final = "lunch_time"
CONF_DINNER_TIME: Final = "dinner_time"
CONF_SNACK_TIMES: Final = "snack_times"
CONF_DAILY_FOOD_AMOUNT: Final = "daily_food_amount"
CONF_MEALS_PER_DAY: Final = "meals_per_day"
CONF_FOOD_TYPE: Final = "food_type"

# Health configuration
CONF_HEALTH_TRACKING: Final = "health_tracking"
CONF_WEIGHT_TRACKING: Final = "weight_tracking"
CONF_MEDICATION_REMINDERS: Final = "medication_reminders"
CONF_VET_REMINDERS: Final = "vet_reminders"
CONF_GROOMING_INTERVAL: Final = "grooming_interval"

# System configuration
CONF_RESET_TIME: Final = "reset_time"
CONF_DASHBOARD_MODE: Final = "dashboard_mode"
CONF_DATA_RETENTION_DAYS: Final = "data_retention_days"
CONF_AUTO_BACKUP: Final = "auto_backup"

# Default values
DEFAULT_RESET_TIME: Final = "23:59:00"
DEFAULT_GPS_UPDATE_INTERVAL: Final = 60
DEFAULT_GPS_ACCURACY_FILTER: Final = 100
DEFAULT_GPS_DISTANCE_FILTER: Final = 10
DEFAULT_HOME_ZONE_RADIUS: Final = 50
DEFAULT_REMINDER_REPEAT_MIN: Final = 30
DEFAULT_SNOOZE_MIN: Final = 15
DEFAULT_DATA_RETENTION_DAYS: Final = 90
DEFAULT_GROOMING_INTERVAL: Final = 28  # days

# Feeding types
FOOD_TYPES: Final = ["dry_food", "wet_food", "barf", "home_cooked", "mixed"]

# Meal types
MEAL_TYPES: Final = ["breakfast", "lunch", "dinner", "snack"]

# Dog sizes with realistic weight ranges (overlapping for breed variations)
DOG_SIZES: Final = [
    "toy",  # 1-6kg: Chihuahua, Yorkshire Terrier
    "small",  # 4-15kg: Beagle, Cocker Spaniel (overlap with toy/medium)
    "medium",  # 8-30kg: Border Collie, Labrador (overlap with small/large)
    "large",  # 22-50kg: German Shepherd, Golden Retriever (overlap with medium/giant)
    "giant",  # 35-90kg: Great Dane, Saint Bernard (overlap with large)
]

# GPS sources
GPS_SOURCES: Final = [
    "manual",
    "device_tracker",
    "person_entity",
    "smartphone",
    "tractive",
    "webhook",
    "mqtt",
]

# Health status options
HEALTH_STATUS_OPTIONS: Final = [
    "excellent",
    "very_good",
    "good",
    "normal",
    "unwell",
    "sick",
]

# Mood options
MOOD_OPTIONS: Final = ["happy", "neutral", "sad", "angry", "anxious", "tired"]

# Activity levels
ACTIVITY_LEVELS: Final = ["very_low", "low", "normal", "high", "very_high"]

# Dashboard modes
DASHBOARD_MODES: Final = ["full", "cards", "minimal"]

# Dashboard configuration
CONF_DASHBOARD_ENABLED: Final = "dashboard_enabled"
CONF_DASHBOARD_AUTO_CREATE: Final = "dashboard_auto_create"
CONF_DASHBOARD_THEME: Final = "dashboard_theme"
CONF_DASHBOARD_CARDS: Final = "dashboard_cards"
CONF_DASHBOARD_VIEWS: Final = "dashboard_views"
CONF_DASHBOARD_PER_DOG: Final = "dashboard_per_dog"

# Dashboard defaults
DEFAULT_DASHBOARD_ENABLED: Final = True
DEFAULT_DASHBOARD_AUTO_CREATE: Final = True
DEFAULT_DASHBOARD_THEME: Final = "default"
DEFAULT_DASHBOARD_MODE: Final = "full"

# Performance modes
PERFORMANCE_MODES: Final = ["minimal", "balanced", "full"]

# Service names
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

# Entity ID templates
ENTITY_ID_FORMAT: Final = "pawcontrol_{dog_id}_{entity_type}_{purpose}"

# Event types
EVENT_WALK_STARTED: Final = "pawcontrol_walk_started"
EVENT_WALK_ENDED: Final = "pawcontrol_walk_ended"
EVENT_FEEDING_LOGGED: Final = "pawcontrol_feeding_logged"
EVENT_HEALTH_LOGGED: Final = "pawcontrol_health_logged"
EVENT_GEOFENCE_ENTERED: Final = "pawcontrol_geofence_entered"
EVENT_GEOFENCE_LEFT: Final = "pawcontrol_geofence_left"

# State attributes
ATTR_DOG_ID: Final = "dog_id"
ATTR_DOG_NAME: Final = "dog_name"
ATTR_TIMESTAMP: Final = "timestamp"
ATTR_MEAL_TYPE: Final = "meal_type"
ATTR_PORTION_SIZE: Final = "portion_size"
ATTR_WALK_DURATION: Final = "walk_duration"
ATTR_WALK_DISTANCE: Final = "walk_distance"
ATTR_GPS_ACCURACY: Final = "gps_accuracy"
ATTR_ZONE_NAME: Final = "zone_name"
ATTR_HEALTH_STATUS: Final = "health_status"
ATTR_WEIGHT: Final = "weight"
ATTR_MEDICATION_NAME: Final = "medication_name"
ATTR_DOSE: Final = "dose"

# Time constants
SECONDS_IN_HOUR: Final = 3600
SECONDS_IN_DAY: Final = 86400
MINUTES_IN_HOUR: Final = 60

# Geofence types
GEOFENCE_TYPES: Final = ["safe_zone", "restricted_area", "point_of_interest"]

# Notification channels
NOTIFICATION_CHANNELS: Final = ["mobile", "persistent", "email", "slack"]

# Update intervals (seconds)
UPDATE_INTERVALS: Final = {
    "minimal": 300,  # 5 minutes
    "balanced": 120,  # 2 minutes
    "frequent": 60,  # 1 minute
    "real_time": 30,  # 30 seconds
}

# Data file names
DATA_FILE_WALKS: Final = "walks.json"
DATA_FILE_FEEDINGS: Final = "feedings.json"
DATA_FILE_HEALTH: Final = "health.json"
DATA_FILE_ROUTES: Final = "routes.json"
DATA_FILE_STATS: Final = "statistics.json"

# Minimum requirements
MIN_DOG_NAME_LENGTH: Final = 2
MAX_DOG_NAME_LENGTH: Final = 30
MIN_DOG_WEIGHT: Final = 0.5  # kg
MAX_DOG_WEIGHT: Final = 200.0  # kg
MIN_DOG_AGE: Final = 0
MAX_DOG_AGE: Final = 30
MIN_GEOFENCE_RADIUS: Final = 10  # meters
MAX_GEOFENCE_RADIUS: Final = 10000  # meters

# Error codes
ERROR_DOG_NOT_FOUND: Final = "dog_not_found"
ERROR_INVALID_CONFIG: Final = "invalid_config"
ERROR_GPS_UNAVAILABLE: Final = "gps_unavailable"
ERROR_NOTIFICATION_FAILED: Final = "notification_failed"
ERROR_SERVICE_UNAVAILABLE: Final = "service_unavailable"

# Export validation constants for use in other modules
__all__ = [
    # Core constants
    "DOMAIN",
    "PLATFORMS",
    "STORAGE_VERSION",
    # Configuration keys
    "CONF_NAME",
    "CONF_DOGS",
    "CONF_DOG_ID",
    "CONF_DOG_NAME",
    "CONF_DOG_BREED",
    "CONF_DOG_AGE",
    "CONF_DOG_WEIGHT",
    "CONF_DOG_SIZE",
    "CONF_DOG_COLOR",
    # Module constants
    "MODULE_GPS",
    "MODULE_FEEDING",
    "MODULE_HEALTH",
    "MODULE_WALK",
    "MODULE_NOTIFICATIONS",
    "MODULE_DASHBOARD",
    "MODULE_VISITOR",
    "MODULE_GROOMING",
    "MODULE_MEDICATION",
    "MODULE_TRAINING",
    # Validation lists (primary source)
    "MEAL_TYPES",
    "FOOD_TYPES",
    "DOG_SIZES",
    "GPS_SOURCES",
    "HEALTH_STATUS_OPTIONS",
    "MOOD_OPTIONS",
    "ACTIVITY_LEVELS",
    "DASHBOARD_MODES",
    "DASHBOARD_STORAGE_VERSION",
    "CONF_DASHBOARD_ENABLED",
    "CONF_DASHBOARD_AUTO_CREATE",
    "CONF_DASHBOARD_THEME",
    "DEFAULT_DASHBOARD_ENABLED",
    "DEFAULT_DASHBOARD_AUTO_CREATE",
    "PERFORMANCE_MODES",
    "GEOFENCE_TYPES",
    # Service names
    "SERVICE_FEED_DOG",
    "SERVICE_START_WALK",
    "SERVICE_END_WALK",
    "SERVICE_LOG_HEALTH",
    "SERVICE_LOG_MEDICATION",
    "SERVICE_START_GROOMING",
    "SERVICE_NOTIFY_TEST",
    "SERVICE_DAILY_RESET",
    # Event types
    "EVENT_WALK_STARTED",
    "EVENT_WALK_ENDED",
    "EVENT_FEEDING_LOGGED",
    "EVENT_HEALTH_LOGGED",
    "EVENT_GEOFENCE_ENTERED",
    "EVENT_GEOFENCE_LEFT",
    # Attribute keys
    "ATTR_DOG_ID",
    "ATTR_DOG_NAME",
    "ATTR_MEAL_TYPE",
    "ATTR_PORTION_SIZE",
    "ATTR_WALK_DURATION",
    "ATTR_WALK_DISTANCE",
    "ATTR_HEALTH_STATUS",
    # Default values
    "DEFAULT_RESET_TIME",
    "DEFAULT_GPS_UPDATE_INTERVAL",
    "DEFAULT_GPS_ACCURACY_FILTER",
    "DEFAULT_DATA_RETENTION_DAYS",
    # Limits
    "MIN_DOG_WEIGHT",
    "MAX_DOG_WEIGHT",
    "MIN_DOG_AGE",
    "MAX_DOG_AGE",
    "MIN_DOG_NAME_LENGTH",
    "MAX_DOG_NAME_LENGTH",
    # Update intervals
    "UPDATE_INTERVALS",
]
