"""Constants for the Paw Control integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final[str] = "pawcontrol"

# Average Earth radius in meters used for distance calculations
EARTH_RADIUS_M: Final[float] = 6_371_000.0

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

# Food type constants
FOOD_DRY: Final[str] = "dry"
FOOD_WET: Final[str] = "wet"
FOOD_BARF: Final[str] = "barf"
FOOD_TREAT: Final[str] = "treat"

# Grooming task constants
GROOMING_BATH: Final[str] = "bath"
GROOMING_BRUSH: Final[str] = "brush"
GROOMING_EARS: Final[str] = "ears"
GROOMING_EYES: Final[str] = "eyes"
GROOMING_NAILS: Final[str] = "nails"
GROOMING_TEETH: Final[str] = "teeth"
GROOMING_TRIM: Final[str] = "trim"

# Training intensity constants
INTENSITY_LOW: Final[str] = "low"
INTENSITY_MEDIUM: Final[str] = "medium"
INTENSITY_HIGH: Final[str] = "high"

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

# Meal constants
MEAL_BREAKFAST: Final[str] = "breakfast"
MEAL_LUNCH: Final[str] = "lunch"
MEAL_DINNER: Final[str] = "dinner"
MEAL_SNACK: Final[str] = "snack"

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
GPS_MINIMUM_MOVEMENT_THRESHOLD_M = 5  # Minimum movement to register location update

# Walk detection defaults
DEFAULT_MIN_WALK_DISTANCE_M = 100  # meters
DEFAULT_MIN_WALK_DURATION_MIN = 5  # minutes
DEFAULT_IDLE_TIMEOUT_MIN = 30  # minutes
WALK_DISTANCE_UPDATE_THRESHOLD_M = 10  # meters - minimum change to trigger UI update
DOOR_OPEN_TIMEOUT_SECONDS = 120  # seconds - max time between door open and walk start

# Safe zone defaults
DEFAULT_SAFE_ZONE_RADIUS = 50  # meters
MAX_SAFE_ZONE_RADIUS = 2000  # meters
MIN_SAFE_ZONE_RADIUS = 5  # meters

# Grooming defaults
DEFAULT_GROOMING_INTERVAL_DAYS = 30

# Health defaults
DEFAULT_DOG_WEIGHT_KG = 20  # Default weight if not specified
MAX_DOG_WEIGHT_KG = 200  # Maximum reasonable dog weight
MIN_DOG_WEIGHT_KG = 0.5  # Minimum reasonable dog weight
CALORIES_PER_KM_PER_KG = 1.5  # Calories burned per km per kg of body weight
CALORIES_PER_MIN_PLAY_PER_KG = 0.25  # Calories burned per minute of play per kg

# Notification defaults
DEFAULT_NOTIFICATION_SERVICE = "notify.notify"

# Added to align with __init__.py service registrations
SERVICE_DAILY_RESET: Final[str] = "daily_reset"
SERVICE_SYNC_SETUP: Final[str] = "sync_setup"
SERVICE_START_WALK: Final[str] = "start_walk"
SERVICE_END_WALK: Final[str] = "end_walk"
SERVICE_WALK_DOG: Final[str] = "walk_dog"
SERVICE_FEED_DOG: Final[str] = "feed_dog"
SERVICE_LOG_HEALTH: Final[str] = "log_health"
SERVICE_LOG_MEDICATION: Final[str] = "log_medication"
SERVICE_START_GROOMING: Final[str] = "start_grooming"
SERVICE_PLAY_SESSION: Final[str] = "play_session"
SERVICE_TRAINING_SESSION: Final[str] = "training_session"
SERVICE_TOGGLE_VISITOR: Final[str] = "toggle_visitor"
SERVICE_EMERGENCY_MODE: Final[str] = "emergency_mode"
SERVICE_GENERATE_REPORT: Final[str] = "generate_report"
SERVICE_EXPORT_DATA: Final[str] = "export_data"

# Added event and alias for consistency
EVENT_DAILY_RESET: Final[str] = "pawcontrol_daily_reset"
SERVICE_PLAY_WITH_DOG: Final[str] = "play_session"  # alias to match schema

# Added additional service name aliases
SERVICE_START_TRAINING: Final[str] = "training_session"
SERVICE_TRAINING_SESSION: Final[str] = "training_session"
SERVICE_START_GROOMING: Final[str] = "start_grooming"
