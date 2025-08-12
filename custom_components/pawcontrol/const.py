"""Constants for the Paw Control integration."""

from typing import Final
from homeassistant.const import Platform

DOMAIN: Final[str] = "pawcontrol"

# Platforms supported by the integration
PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.DATETIME,
    Platform.SWITCH,
    Platform.DEVICE_TRACKER,
]

# Event types for Home Assistant bus
EVENT_WALK_STARTED: Final[str] = "pawcontrol_walk_started"
EVENT_WALK_ENDED: Final[str] = "pawcontrol_walk_ended"
EVENT_DOG_FED: Final[str] = "pawcontrol_dog_fed"
EVENT_MEDICATION_GIVEN: Final[str] = "pawcontrol_medication_given"
EVENT_GROOMING_DONE: Final[str] = "pawcontrol_grooming_done"
EVENT_TRAINING_SESSION: Final[str] = "pawcontrol_training_session"
EVENT_SAFE_ZONE_ENTERED: Final[str] = "pawcontrol_safe_zone_entered"
EVENT_SAFE_ZONE_LEFT: Final[str] = "pawcontrol_safe_zone_left"

# Event attributes
ATTR_DOG_ID: Final[str] = "dog_id"
ATTR_DOG_NAME: Final[str] = "dog_name"
ATTR_DURATION: Final[str] = "duration"
ATTR_DISTANCE: Final[str] = "distance"
ATTR_MEAL_TYPE: Final[str] = "meal_type"
ATTR_MEDICATION: Final[str] = "medication"

# Module keys used in options['modules']
MODULE_FEEDING: Final[str] = "feeding"
MODULE_GPS: Final[str] = "gps"
MODULE_HEALTH: Final[str] = "health"
MODULE_WALK: Final[str] = "walk"
MODULE_GROOMING: Final[str] = "grooming"
MODULE_TRAINING: Final[str] = "training"
MODULE_NOTIFICATIONS: Final[str] = "notifications"
MODULE_DASHBOARD: Final[str] = "dashboard"
MODULE_MEDICATION: Final[str] = "medication"

# Common config keys referenced across modules/options
CONF_DOGS = "dogs"
CONF_RESET_TIME = "reset_time"
CONF_DASHBOARD = "dashboard"
CONF_DEVICE_TRACKERS = "device_trackers"
CONF_EXPORT_FORMAT = "export_format"
CONF_EXPORT_PATH = "export_path"
CONF_REMINDER_REPEAT = "reminder_repeat"
CONF_SNOOZE_MIN = "snooze_min"
CONF_QUIET_START = "quiet_hours_start"
CONF_QUIET_END = "quiet_hours_end"
CONF_QUIET_HOURS = "quiet_hours"
CONF_NOTIFY_BACKENDS = "notify_backends"
CONF_NOTIFY_FALLBACK = "notify_fallback"
CONF_NOTIFICATIONS = "notifications"
CONF_SOURCES = "sources"
CONF_TYPE = "type"
CONF_DEVICE_ID = "device_id"
CONF_PLATFORM = "platform"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_VISITOR_MODE = "visitor_mode"
CONF_WEATHER = "weather"
CONF_CALENDAR = "calendar"
CONF_PERSON_ENTITIES = "person_entities"
CONF_EVENT_TYPE = "event_type"
CONF_EVENT_DATA = "event_data"
CONF_DOG_ID = "dog_id"
CONF_DOG_NAME = "dog_name"
CONF_DOG_WEIGHT = "dog_weight"
CONF_DOG_SIZE = "dog_size"
CONF_DOG_BREED = "dog_breed"
CONF_DOG_AGE = "dog_age"
CONF_DOG_MODULES = "dog_modules"
CONF_DOMAIN = "domain"
CONF_DOOR_SENSOR = "door_sensor"

# Defaults
DEFAULT_RESET_TIME: Final[str] = "23:59:00"
DEFAULT_REMINDER_REPEAT: Final[int] = 30
DEFAULT_SNOOZE_MIN: Final[int] = 15
DEFAULT_EXPORT_FORMAT: Final[str] = "csv"
DEFAULT_WALK_THRESHOLD_HOURS: Final[float] = 8.0

# Icons and labels (minimal safe defaults; extended sets may be merged elsewhere)
ICONS: Final[dict[str, str]] = {
    "feeding": "mdi:food-drumstick",
    "gps": "mdi:map-marker",
    "health": "mdi:medical-bag",
    "walk": "mdi:walk",
    "grooming": "mdi:shower",
    "training": "mdi:school",
    "medication": "mdi:pill",
    "dashboard": "mdi:view-dashboard",
    "notifications": "mdi:bell",
}

# Meal types mapping (used in UI/logic)
MEAL_TYPES: Final[dict[str, str]] = {
    "breakfast": "Frühstück",
    "lunch": "Mittag",
    "dinner": "Abend",
}

# Feeding types
FEEDING_TYPES: Final[dict[str, str]] = {
    "dry": "Trockenfutter",
    "wet": "Nassfutter",
    "barf": "BARF",
    "snack": "Snack",
}

# Health thresholds (example defaults)
HEALTH_THRESHOLDS: Final[dict[str, float]] = {
    "temperature_high": 39.2,
    "temperature_low": 37.2,
    "heart_rate_high": 140.0,
}

# Vaccination names & intervals (months)
VACCINATION_NAMES: Final[dict[str, str]] = {
    "rabies": "Tollwut",
    "distemper": "Staupe",
    "hepatitis": "Hepatitis",
    "parvovirus": "Parvovirose",
    "parainfluenza": "Parainfluenza",
    "leptospirosis": "Leptospirose",
    "bordetella": "Zwingerhusten",
}

VACCINATION_INTERVALS: Final[dict[str, int]] = {
    "rabies": 36,
    "distemper": 36,
    "hepatitis": 36,
    "parvovirus": 36,
    "parainfluenza": 12,
    "leptospirosis": 12,
    "bordetella": 12,
}

# Service names
SERVICE_GPS_START_WALK = "gps_start_walk"
SERVICE_GPS_END_WALK = "gps_end_walk"
SERVICE_GPS_GENERATE_DIAGNOSTICS = "gps_generate_diagnostics"
SERVICE_GPS_RESET_STATS = "gps_reset_stats"
SERVICE_GPS_EXPORT_LAST_ROUTE = "gps_export_last_route"
SERVICE_GPS_PAUSE_TRACKING = "gps_pause_tracking"
SERVICE_GPS_RESUME_TRACKING = "gps_resume_tracking"
SERVICE_GPS_POST_LOCATION = "gps_post_location"
SERVICE_GPS_LIST_WEBHOOKS = "gps_list_webhooks"
SERVICE_GPS_REGENERATE_WEBHOOKS = "gps_regenerate_webhooks"
SERVICE_TOGGLE_GEOFENCE_ALERTS = "toggle_geofence_alerts"
SERVICE_EXPORT_OPTIONS = "export_options"
SERVICE_IMPORT_OPTIONS = "import_options"
SERVICE_NOTIFY_TEST = "notify_test"
SERVICE_PURGE_ALL_STORAGE = "purge_all_storage"
SERVICE_ROUTE_HISTORY_LIST = "route_history_list"
SERVICE_ROUTE_HISTORY_PURGE = "route_history_purge"
SERVICE_ROUTE_HISTORY_EXPORT_RANGE = "route_history_export_range"
SERVICE_SEND_MEDICATION_REMINDER = "send_medication_reminder"

# Storage keys
STORAGE_KEY_GPS_SETTINGS = "gps_settings"
STORAGE_KEY_ROUTE_HISTORY = "route_history"
STORAGE_KEY_USER_SETTINGS = "user_settings"

# GPS and tracking constants
GPS_MIN_ACCURACY = 100  # meters
GPS_MAX_POINTS_PER_ROUTE = 10000
GPS_POINT_FILTER_DISTANCE = 5  # meters minimum between points

# Walk detection defaults
DEFAULT_MIN_WALK_DISTANCE_M = 100  # meters
DEFAULT_MIN_WALK_DURATION_MIN = 5  # minutes
DEFAULT_IDLE_TIMEOUT_MIN = 30  # minutes

# Safe zone defaults
DEFAULT_SAFE_ZONE_RADIUS = 50  # meters
MAX_SAFE_ZONE_RADIUS = 2000  # meters
MIN_SAFE_ZONE_RADIUS = 5  # meters

# Grooming defaults
DEFAULT_GROOMING_INTERVAL_DAYS = 30

# Notification defaults
DEFAULT_NOTIFICATION_SERVICE = "notify.notify"
