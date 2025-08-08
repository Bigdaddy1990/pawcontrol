"""Constants for PawControl integration."""
from __future__ import annotations

from typing import Final

# Domain
DOMAIN: Final = "pawcontrol"
VERSION: Final = "1.0.0"

# Config Keys - Basic
CONF_DOG_NAME: Final = "dog_name"
CONF_DOG_BREED: Final = "dog_breed"
CONF_DOG_AGE: Final = "dog_age"
CONF_DOG_WEIGHT: Final = "dog_weight"
CONF_DOG_SIZE: Final = "dog_size"
CONF_DOGS: Final = "dogs"
CONF_MODULES: Final = "modules"

# Module IDs
MODULE_FEEDING: Final = "feeding"
MODULE_GPS: Final = "gps"
MODULE_HEALTH: Final = "health"
MODULE_NOTIFICATIONS: Final = "notifications"
MODULE_AUTOMATION: Final = "automation"
MODULE_DASHBOARD: Final = "dashboard"
MODULE_WALK: Final = "walk"
MODULE_TRAINING: Final = "training"
MODULE_GROOMING: Final = "grooming"
MODULE_VISITOR: Final = "visitor"

ALL_MODULES: Final = [
    MODULE_FEEDING,
    MODULE_GPS,
    MODULE_HEALTH,
    MODULE_NOTIFICATIONS,
    MODULE_AUTOMATION,
    MODULE_DASHBOARD,
    MODULE_WALK,
    MODULE_TRAINING,
    MODULE_GROOMING,
    MODULE_VISITOR,
]

# Module Display Names
MODULE_NAMES: Final = {
    MODULE_FEEDING: "🍽️ Fütterung",
    MODULE_GPS: "📍 GPS-Tracking",
    MODULE_HEALTH: "🏥 Gesundheit",
    MODULE_NOTIFICATIONS: "🔔 Benachrichtigungen",
    MODULE_AUTOMATION: "🤖 Automatisierung",
    MODULE_DASHBOARD: "📊 Dashboard",
    MODULE_WALK: "🚶 Spaziergänge",
    MODULE_TRAINING: "🎾 Training",
    MODULE_GROOMING: "✂️ Pflege",
    MODULE_VISITOR: "👥 Besuchermodus",
}

# Feeding Module
CONF_FEEDING_ENABLED: Final = "feeding_enabled"
CONF_FEEDING_TIMES: Final = "feeding_times"
CONF_FEEDING_BREAKFAST: Final = "breakfast_time"
CONF_FEEDING_LUNCH: Final = "lunch_time"
CONF_FEEDING_DINNER: Final = "dinner_time"
CONF_FEEDING_AMOUNT: Final = "daily_food_amount"
CONF_FEEDING_TYPE: Final = "food_type"
CONF_FEEDING_REMINDERS: Final = "feeding_reminders"

# GPS Module
CONF_GPS_ENABLED: Final = "gps_enabled"
CONF_GPS_SOURCE: Final = "gps_source"
CONF_GPS_UPDATE_INTERVAL: Final = "gps_update_interval"
CONF_GPS_GEOFENCE: Final = "geofence_radius"
CONF_GPS_AUTO_WALK: Final = "auto_walk_detection"

# Health Module
CONF_HEALTH_ENABLED: Final = "health_enabled"
CONF_HEALTH_TEMPERATURE: Final = "track_temperature"
CONF_HEALTH_WEIGHT: Final = "track_weight"
CONF_HEALTH_VET_CONTACT: Final = "vet_contact"
CONF_HEALTH_MEDICATION: Final = "medication_tracking"

# Walk Module
CONF_WALK_ENABLED: Final = "walk_enabled"
CONF_WALK_DURATION: Final = "default_walk_duration"
CONF_WALK_REMINDERS: Final = "walk_reminders"
CONF_WALK_TRACKING: Final = "walk_tracking"

# Notification Module
CONF_NOTIFICATIONS_ENABLED: Final = "notifications_enabled"
CONF_NOTIFICATIONS_TYPE: Final = "notification_type"
CONF_NOTIFICATIONS_TARGETS: Final = "notification_targets"

# Dashboard Module
CONF_DASHBOARD_ENABLED: Final = "dashboard_enabled"
CONF_DASHBOARD_NAME: Final = "dashboard_name"
CONF_DASHBOARD_PATH: Final = "dashboard_path"

# Size Categories
SIZE_TOY: Final = "Toy"
SIZE_SMALL: Final = "Klein"
SIZE_MEDIUM: Final = "Mittel"
SIZE_LARGE: Final = "Groß"
SIZE_GIANT: Final = "Riesig"

SIZE_OPTIONS: Final = [SIZE_TOY, SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_GIANT]

# Health Status Options
HEALTH_EXCELLENT: Final = "Ausgezeichnet"
HEALTH_VERY_GOOD: Final = "Sehr gut"
HEALTH_GOOD: Final = "Gut"
HEALTH_NORMAL: Final = "Normal"
HEALTH_UNWELL: Final = "Unwohl"
HEALTH_SICK: Final = "Krank"

HEALTH_STATUS_OPTIONS: Final = [
    HEALTH_EXCELLENT,
    HEALTH_VERY_GOOD,
    HEALTH_GOOD,
    HEALTH_NORMAL,
    HEALTH_UNWELL,
    HEALTH_SICK,
]

# Mood Options
MOOD_HAPPY: Final = "😊 Fröhlich"
MOOD_NEUTRAL: Final = "😐 Neutral"
MOOD_SAD: Final = "😟 Traurig"
MOOD_ANGRY: Final = "😠 Ärgerlich"
MOOD_ANXIOUS: Final = "😰 Ängstlich"
MOOD_TIRED: Final = "😴 Müde"

MOOD_OPTIONS: Final = [
    MOOD_HAPPY,
    MOOD_NEUTRAL,
    MOOD_SAD,
    MOOD_ANGRY,
    MOOD_ANXIOUS,
    MOOD_TIRED,
]

# Activity Levels
ACTIVITY_VERY_LOW: Final = "Sehr niedrig"
ACTIVITY_LOW: Final = "Niedrig"
ACTIVITY_NORMAL: Final = "Normal"
ACTIVITY_HIGH: Final = "Hoch"
ACTIVITY_VERY_HIGH: Final = "Sehr hoch"

ACTIVITY_LEVELS: Final = [
    ACTIVITY_VERY_LOW,
    ACTIVITY_LOW,
    ACTIVITY_NORMAL,
    ACTIVITY_HIGH,
    ACTIVITY_VERY_HIGH,
]

# Food Types
FOOD_DRY: Final = "Trockenfutter"
FOOD_WET: Final = "Nassfutter"
FOOD_BARF: Final = "BARF"
FOOD_HOMEMADE: Final = "Selbstgekocht"
FOOD_MIXED: Final = "Gemischt"

FOOD_TYPES: Final = [FOOD_DRY, FOOD_WET, FOOD_BARF, FOOD_HOMEMADE, FOOD_MIXED]

# GPS Sources
GPS_MANUAL: Final = "Manual"
GPS_DEVICE_TRACKER: Final = "Device Tracker"
GPS_PERSON: Final = "Person Entity"
GPS_SMARTPHONE: Final = "Smartphone"
GPS_TRACTIVE: Final = "Tractive"

GPS_SOURCES: Final = [GPS_MANUAL, GPS_DEVICE_TRACKER, GPS_PERSON, GPS_SMARTPHONE, GPS_TRACTIVE]

# Walk Types
WALK_SHORT: Final = "Kurz"
WALK_NORMAL: Final = "Normal"
WALK_LONG: Final = "Lang"
WALK_TRAINING: Final = "Training"
WALK_FREE: Final = "Freilauf"

WALK_TYPES: Final = [WALK_SHORT, WALK_NORMAL, WALK_LONG, WALK_TRAINING, WALK_FREE]

# Notification Types
NOTIFY_PERSISTENT: Final = "Persistent"
NOTIFY_MOBILE: Final = "Mobile App"
NOTIFY_BOTH: Final = "Both"

NOTIFICATION_TYPES: Final = [NOTIFY_PERSISTENT, NOTIFY_MOBILE, NOTIFY_BOTH]

# Default Values
DEFAULT_UPDATE_INTERVAL: Final = 300  # 5 minutes
DEFAULT_WALK_DURATION: Final = 30  # minutes
DEFAULT_GEOFENCE_RADIUS: Final = 50  # meters
DEFAULT_FOOD_AMOUNT: Final = 500  # grams

# Icons
ICON_DOG: Final = "mdi:dog"
ICON_FOOD: Final = "mdi:food-drumstick"
ICON_WALK: Final = "mdi:dog-service"
ICON_HEALTH: Final = "mdi:medical-bag"
ICON_GPS: Final = "mdi:map-marker"
ICON_NOTIFICATION: Final = "mdi:bell"
ICON_AUTOMATION: Final = "mdi:robot"
ICON_DASHBOARD: Final = "mdi:view-dashboard"
ICON_TRAINING: Final = "mdi:whistle"
ICON_GROOMING: Final = "mdi:content-cut"
ICON_VISITOR: Final = "mdi:account-group"
ICON_EMERGENCY: Final = "mdi:alert-octagon"
ICON_MEDICATION: Final = "mdi:pill"
ICON_VET: Final = "mdi:hospital-box"
ICON_WEIGHT: Final = "mdi:weight-kilogram"
ICON_TEMPERATURE: Final = "mdi:thermometer"
ICON_CALENDAR: Final = "mdi:calendar"
ICON_CLOCK: Final = "mdi:clock"
ICON_COUNTER: Final = "mdi:counter"
ICON_NOTE: Final = "mdi:note-text"

# Attributes
ATTR_DOG_NAME: Final = "dog_name"
ATTR_MODULE: Final = "module"
ATTR_LAST_UPDATE: Final = "last_update"
ATTR_STATUS: Final = "status"
ATTR_MESSAGE: Final = "message"
ATTR_LOCATION: Final = "location"
ATTR_DISTANCE: Final = "distance"
ATTR_DURATION: Final = "duration"
ATTR_CALORIES: Final = "calories"

# Services
SERVICE_FEED_DOG: Final = "feed_dog"
SERVICE_START_WALK: Final = "start_walk"
SERVICE_END_WALK: Final = "end_walk"
SERVICE_LOG_HEALTH: Final = "log_health"
SERVICE_UPDATE_GPS: Final = "update_gps"
SERVICE_SET_MOOD: Final = "set_mood"
SERVICE_LOG_MEDICATION: Final = "log_medication"
SERVICE_EMERGENCY: Final = "emergency"
SERVICE_RESET_DATA: Final = "reset_data"

# Entity ID Patterns
ENTITY_ID_FORMAT: Final = "{domain}.{dog_name}_{entity_type}"
HELPER_ID_FORMAT: Final = "input_{type}.pawcontrol_{dog_name}_{entity}"

# Validation
MIN_DOG_NAME_LENGTH: Final = 2
MAX_DOG_NAME_LENGTH: Final = 30
MIN_DOG_AGE: Final = 0
MAX_DOG_AGE: Final = 25
MIN_DOG_WEIGHT: Final = 0.5
MAX_DOG_WEIGHT: Final = 100
MIN_TEMPERATURE: Final = 35.0
MAX_TEMPERATURE: Final = 42.0

# GPS Constants
EARTH_RADIUS_M: Final = 6_371_000  # Earth's radius in meters
GPS_ACCURACY_EXCELLENT: Final = 5  # meters
GPS_ACCURACY_GOOD: Final = 15
GPS_ACCURACY_ACCEPTABLE: Final = 50
GPS_ACCURACY_POOR: Final = 100

MOVEMENT_THRESHOLD: Final = 3.0  # meters
STATIONARY_TIME: Final = 300  # seconds
MIN_WALK_DURATION: Final = 300  # 5 minutes
MIN_WALK_DISTANCE: Final = 10  # meters

# Error Messages
ERROR_NO_DOGS: Final = "Keine Hunde konfiguriert"
ERROR_INVALID_NAME: Final = "Ungültiger Hundename"
ERROR_INVALID_WEIGHT: Final = "Ungültiges Gewicht"
ERROR_INVALID_AGE: Final = "Ungültiges Alter"
ERROR_MODULE_FAILED: Final = "Modul konnte nicht initialisiert werden"
ERROR_SERVICE_FAILED: Final = "Service-Aufruf fehlgeschlagen"
