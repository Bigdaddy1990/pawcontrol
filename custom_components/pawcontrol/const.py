"""Constants for the Paw Control integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN = "pawcontrol"

# Platforms the integration implements. Home Assistant now validates that these
# values are instances of the ``Platform`` enum; using raw strings would cause
# setup and unload to fail.  Typing the list helps static checkers catch any
# accidental regression back to string values.
PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.SWITCH,
]

# Configuration
CONF_DOGS = "dogs"
CONF_DOG_ID = "dog_id"
CONF_DOG_NAME = "name"
CONF_DOG_BREED = "breed"
CONF_DOG_AGE = "age"
CONF_DOG_WEIGHT = "weight"
CONF_DOG_SIZE = "size"
CONF_DOG_MODULES = "modules"

# Modules
MODULE_WALK = "walk"
MODULE_FEEDING = "feeding"
MODULE_HEALTH = "health"
MODULE_GPS = "gps"
MODULE_NOTIFICATIONS = "notifications"
MODULE_DASHBOARD = "dashboard"
MODULE_GROOMING = "grooming"
MODULE_MEDICATION = "medication"
MODULE_TRAINING = "training"

# Sources
CONF_SOURCES = "sources"
CONF_DOOR_SENSOR = "door_sensor"
CONF_PERSON_ENTITIES = "person_entities"
CONF_DEVICE_TRACKERS = "device_trackers"
CONF_NOTIFY_FALLBACK = "notify_fallback"
CONF_CALENDAR = "calendar"
CONF_WEATHER = "weather"

# Notifications
CONF_NOTIFICATIONS = "notifications"
CONF_QUIET_HOURS = "quiet_hours"
CONF_QUIET_START = "start"
CONF_QUIET_END = "end"
CONF_REMINDER_REPEAT = "reminder_repeat_min"
CONF_SNOOZE_MIN = "snooze_min"

# System
CONF_RESET_TIME = "reset_time"
CONF_EXPORT_PATH = "export_path"
CONF_EXPORT_FORMAT = "export_format"
CONF_VISITOR_MODE = "visitor_mode"
CONF_EMERGENCY_MODE = "emergency_mode"

# Defaults
DEFAULT_RESET_TIME = "23:59:00"
DEFAULT_REPORT_TIME = "23:55:00"
DEFAULT_REMINDER_REPEAT = 30
DEFAULT_SNOOZE_MIN = 15
DEFAULT_EXPORT_FORMAT = "csv"
DEFAULT_WALK_THRESHOLD_HOURS = 8
DEFAULT_GROOMING_INTERVAL_DAYS = 30
DEFAULT_MIN_WALK_DISTANCE_M = 10
DEFAULT_MIN_WALK_DURATION_MIN = 5
DEFAULT_IDLE_TIMEOUT_MIN = 30

# Attributes
ATTR_DOG_ID = "dog_id"
ATTR_DOG_NAME = "dog_name"
ATTR_LAST_WALK = "last_walk"
ATTR_LAST_FEEDING = "last_feeding"
ATTR_LAST_GROOMING = "last_grooming"
ATTR_LAST_MEDICATION = "last_medication"
ATTR_WALK_DURATION = "walk_duration_min"
ATTR_WALK_DISTANCE = "walk_distance_m"
ATTR_MEAL_TYPE = "meal_type"
ATTR_FOOD_TYPE = "food_type"
ATTR_PORTION_G = "portion_g"
ATTR_MEDICATION_NAME = "medication_name"
ATTR_GROOMING_TYPE = "grooming_type"
ATTR_NOTES = "notes"

# Events
EVENT_DAILY_RESET = f"{DOMAIN}_daily_reset"
EVENT_WALK_STARTED = f"{DOMAIN}_walk_started"
EVENT_WALK_ENDED = f"{DOMAIN}_walk_ended"
EVENT_DOG_FED = f"{DOMAIN}_dog_fed"
EVENT_MEDICATION_GIVEN = f"{DOMAIN}_medication_given"
EVENT_GROOMING_DONE = f"{DOMAIN}_grooming_done"

# Services
SERVICE_START_WALK = "start_walk"
SERVICE_END_WALK = "end_walk"
SERVICE_WALK_DOG = "walk_dog"
SERVICE_FEED_DOG = "feed_dog"
SERVICE_LOG_HEALTH = "log_health_data"
SERVICE_LOG_MEDICATION = "log_medication"
SERVICE_START_GROOMING = "start_grooming_session"
SERVICE_PLAY_WITH_DOG = "play_with_dog"
SERVICE_START_TRAINING = "start_training_session"
SERVICE_TOGGLE_VISITOR = "toggle_visitor_mode"
SERVICE_EMERGENCY_MODE = "activate_emergency_mode"
SERVICE_DAILY_RESET = "daily_reset"
SERVICE_GENERATE_REPORT = "generate_report"
SERVICE_EXPORT_DATA = "export_health_data"
SERVICE_SYNC_SETUP = "sync_setup"
SERVICE_NOTIFY_TEST = "notify_test"

# Meal types
MEAL_BREAKFAST = "breakfast"
MEAL_LUNCH = "lunch"
MEAL_DINNER = "dinner"
MEAL_SNACK = "snack"

# Food types
FOOD_DRY = "dry"
FOOD_WET = "wet"
FOOD_BARF = "barf"
FOOD_TREAT = "treat"

# Grooming types
GROOMING_BATH = "bath"
GROOMING_BRUSH = "brush"
GROOMING_TRIM = "trim"
GROOMING_NAILS = "nails"
GROOMING_EARS = "ears"
GROOMING_TEETH = "teeth"
GROOMING_EYES = "eyes"

# Activity intensity
INTENSITY_LOW = "low"
INTENSITY_MEDIUM = "medium"
INTENSITY_HIGH = "high"

# Dog sizes
SIZE_SMALL = "small"
SIZE_MEDIUM = "medium"
SIZE_LARGE = "large"
SIZE_XLARGE = "xlarge"
