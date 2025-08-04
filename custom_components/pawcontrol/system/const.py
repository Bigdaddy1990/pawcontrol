"""Konstanten für Paw Control."""

DOMAIN = "pawcontrol"

# Konfigurations-Keys (ConfigFlow, Options, Helper etc.)
CONF_DOG_NAME = "dog_name"
CONF_DOG_BREED = "dog_breed"
CONF_DOG_AGE = "dog_age"
CONF_DOG_WEIGHT = "dog_weight"
CONF_FEEDING_TIMES = "feeding_times"
CONF_WALK_DURATION = "walk_duration"
CONF_VET_CONTACT = "vet_contact"
CONF_GPS_ENABLE = "gps_enable"
CONF_NOTIFICATIONS_ENABLED = "notifications_enabled"
CONF_HEALTH_MODULE = "health_module"
CONF_WALK_MODULE = "walk_module"
CONF_CREATE_DASHBOARD = "create_dashboard"

# Sensors, States, Helper
ATTR_LAST_FED = "last_fed"
ATTR_LAST_WALK = "last_walk"
ATTR_HEALTH_STATUS = "health_status"
ATTR_GPS_LOCATION = "gps_location"
ATTR_FEEDING_COUNTER = "feeding_counter"
ATTR_WALK_COUNTER = "walk_counter"
ATTR_PUSH_TARGET = "push_target"
ATTR_PERSON_ID = "person_id"
ATTR_ACTION = "action"
ATTR_TIMESTAMP = "timestamp"
ATTR_DEVICE_TRACKER = "device_tracker"
ATTR_MEDICATION = "medication"
ATTR_SYMPTOMS = "symptoms"
ATTR_WEIGHT_HISTORY = "weight_history"
ATTR_ACTIVITY_LOG = "activity_log"
ATTR_LAST_EVENT = "last_event"
ATTR_DASHBOARD_VIEW = "dashboard_view"
ATTR_EVENT_TYPE = "event_type"
ATTR_EVENT_DETAIL = "event_detail"
ATTR_DOG_NAME = "dog_name"
ATTR_LAST_UPDATED = "last_updated"

# Standardwerte
DEFAULT_FEEDING_TIMES = []
DEFAULT_WALK_DURATION = 30
DEFAULT_HEALTH_STATUS = "ok"
DEFAULT_GPS_LOCATION = "unknown"

# Weitere interne Konstanten (z. B. Entity-ID-Präfixe)
SENSOR_PREFIX = "sensor"
INPUT_BOOLEAN_PREFIX = "input_boolean"
INPUT_NUMBER_PREFIX = "input_number"
INPUT_TEXT_PREFIX = "input_text"
COUNTER_PREFIX = "counter"

# Beispiel-Service-Namen
SERVICE_FEED_DOG = "feed_dog"
SERVICE_START_WALK = "start_walk"
SERVICE_LOG_HEALTH = "log_health"
SERVICE_SEND_NOTIFICATION = "send_notification"
SERVICE_LOG_ACTIVITY = "log_activity"
SERVICE_SET_WEIGHT = "set_weight"

# Service parameter keys used in service calls
SERVICE_FOOD_TYPE = "meal_type"
SERVICE_FOOD_AMOUNT = "amount"
SERVICE_DURATION = "duration"
SERVICE_WEIGHT = "weight"
SERVICE_TEMPERATURE = "temperature"
SERVICE_ENERGY_LEVEL = "energy_level"
SERVICE_SYMPTOMS = "symptoms"
SERVICE_NOTES = "notes"
SERVICE_MOOD = "mood"
SERVICE_VET_DATE = "vet_date"

# Für die optionale Modularisierung: Alle Feature-Flags zentral gesammelt
ALL_MODULE_FLAGS = [
    CONF_GPS_ENABLE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_HEALTH_MODULE,
    CONF_WALK_MODULE,
    CONF_CREATE_DASHBOARD,
]

# -----------------------------------------------------------------------------
# Additional configuration and validation constants
# -----------------------------------------------------------------------------

# Dog profile validation limits
MIN_DOG_NAME_LENGTH = 2
MAX_DOG_NAME_LENGTH = 30
MIN_DOG_WEIGHT = 0.5
MAX_DOG_WEIGHT = 100.0
MIN_DOG_AGE = 0
MAX_DOG_AGE = 25

# Allowed characters for dog names
DOG_NAME_PATTERN = r"^[a-zA-ZäöüÄÖÜß0-9\s\-_.]+$"

# GPS related defaults
GPS_ACCURACY_THRESHOLDS = {
    "excellent": 5,
    "good": 15,
    "acceptable": 50,
}

DEFAULT_HOME_COORDINATES = (0.0, 0.0)

GPS_CONFIG = {
    "movement_threshold": 3.0,
    "stationary_time": 300,
    "walk_detection_distance": 10.0,
    "min_walk_duration": 5,
    "home_zone_radius": 50,
}

GEOFENCE_MIN_RADIUS = 10
GEOFENCE_MAX_RADIUS = 10000

# Icon mapping used across the integration
ICONS = {
    "automation": "mdi:robot",
    "battery": "mdi:battery",
    "emergency": "mdi:alert",
    "evening": "mdi:weather-night",
    "food": "mdi:food",
    "gps": "mdi:crosshairs-gps",
    "grooming": "mdi:scissors-cutting",
    "health": "mdi:heart",
    "home": "mdi:home",
    "location": "mdi:map-marker",
    "lunch": "mdi:food",
    "medication": "mdi:pill",
    "mood": "mdi:emoticon",
    "morning": "mdi:weather-sunny",
    "outside": "mdi:dog-side",
    "play": "mdi:tennis-ball",
    "poop": "mdi:dog-side",
    "settings": "mdi:cog",
    "signal": "mdi:signal",
    "statistics": "mdi:chart-bar",
    "status": "mdi:information",
    "temperature": "mdi:thermometer",
    "training": "mdi:school",
    "vet": "mdi:stethoscope",
    "visitor": "mdi:account-group",
    "walk": "mdi:walk",
    "weight": "mdi:weight",
}

# Feeding and meal definitions
FEEDING_TYPES = ["morning", "lunch", "evening", "snack"]
MEAL_TYPES = {
    "morning": "Frühstück",
    "lunch": "Mittag",
    "evening": "Abend",
    "snack": "Snack",
}

# Status texts used by automations and scripts
STATUS_MESSAGES = {
    "ok": "Alles ok",
    "needs_food": "Fütterung ausstehend",
    "needs_walk": "Spaziergang ausstehend",
}

# Generic validation rules for numeric service data
VALIDATION_RULES = {
    "weight": {"min": MIN_DOG_WEIGHT, "max": MAX_DOG_WEIGHT, "unit": "kg"},
    "age": {"min": MIN_DOG_AGE, "max": MAX_DOG_AGE, "unit": "years"},
}

# Default entity blueprint used when creating helper entities
ENTITIES = {
    "input_boolean": {
        "feeding_morning": {"name": "Frühstück gegeben", "icon": "mdi:food"},
        "feeding_lunch": {"name": "Mittagessen gegeben", "icon": "mdi:food"},
        "feeding_evening": {"name": "Abendessen gegeben", "icon": "mdi:food"},
        "feeding_snack": {"name": "Snack gegeben", "icon": "mdi:food"},
        "walk_in_progress": {"name": "Spaziergang läuft", "icon": "mdi:walk"},
    },
    "counter": {
        "walk_count": {"name": "Spaziergänge", "initial": 0, "step": 1, "icon": "mdi:walk"},
        "feeding_morning_count": {
            "name": "Frühstücks-Zähler",
            "initial": 0,
            "step": 1,
            "icon": "mdi:counter",
        },
        "feeding_lunch_count": {
            "name": "Mittagessens-Zähler",
            "initial": 0,
            "step": 1,
            "icon": "mdi:counter",
        },
        "feeding_evening_count": {
            "name": "Abendessens-Zähler",
            "initial": 0,
            "step": 1,
            "icon": "mdi:counter",
        },
        "feeding_snack_count": {
            "name": "Snack-Zähler",
            "initial": 0,
            "step": 1,
            "icon": "mdi:counter",
        },
    },
    "input_text": {
        "notes": {"name": "Notizen", "max": 255, "icon": "mdi:note-text"},
    },
    "input_datetime": {
        "last_walk": {
            "name": "Letzter Spaziergang",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:walk",
        },
        "last_feeding_morning": {
            "name": "Letztes Frühstück",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:food",
        },
        "last_feeding_lunch": {
            "name": "Letztes Mittagessen",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:food",
        },
        "last_feeding_evening": {
            "name": "Letztes Abendessen",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:food",
        },
        "last_feeding_snack": {
            "name": "Letzter Snack",
            "has_date": True,
            "has_time": True,
            "icon": "mdi:food",
        },
    },
    "input_number": {
        "weight": {
            "name": "Gewicht",
            "min": MIN_DOG_WEIGHT,
            "max": MAX_DOG_WEIGHT,
            "step": 0.1,
            "unit": "kg",
            "icon": "mdi:weight",
        },
    },
    "input_select": {
        "health_status": {
            "name": "Gesundheitsstatus",
            "options": ["gut", "mittel", "schlecht"],
            "icon": "mdi:heart",
        },
    },
}
