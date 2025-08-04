"""Konstanten für Paw Control - KORRIGIERT."""

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
DEFAULT_HEALTH_STATUS = "gut"
DEFAULT_GPS_LOCATION = "unknown"

# Entity-ID-Präfixe
SENSOR_PREFIX = "sensor"
INPUT_BOOLEAN_PREFIX = "input_boolean"
INPUT_NUMBER_PREFIX = "input_number"
INPUT_TEXT_PREFIX = "input_text"
COUNTER_PREFIX = "counter"

# Service-Namen
SERVICE_FEED_DOG = "feed_dog"
SERVICE_START_WALK = "start_walk"
SERVICE_LOG_HEALTH = "log_health"
SERVICE_SEND_NOTIFICATION = "send_notification"
SERVICE_LOG_ACTIVITY = "log_activity"
SERVICE_SET_WEIGHT = "set_weight"

# Service parameter keys
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

# Module-Flags für Optionen
ALL_MODULE_FLAGS = [
    CONF_GPS_ENABLE,
    CONF_NOTIFICATIONS_ENABLED,
    CONF_HEALTH_MODULE,
    CONF_WALK_MODULE,
    CONF_CREATE_DASHBOARD,
]

# Validierungslimits
MIN_DOG_NAME_LENGTH = 2
MAX_DOG_NAME_LENGTH = 30
MIN_DOG_WEIGHT = 0.5
MAX_DOG_WEIGHT = 100.0
MIN_DOG_AGE = 0
MAX_DOG_AGE = 25

# Name-Pattern für Hunde
DOG_NAME_PATTERN = r"^[a-zA-ZäöüÄÖÜß0-9\s\-_.]+$"

# GPS-Konfiguration
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

# Icon-Mapping
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

# Fütterungstypen
FEEDING_TYPES = ["morning", "lunch", "evening", "snack"]
MEAL_TYPES = {
    "morning": "Frühstück",
    "lunch": "Mittag",
    "evening": "Abend",
    "snack": "Snack",
}

# Status-Texte
STATUS_MESSAGES = {
    "ok": "Alles ok",
    "needs_food": "Fütterung ausstehend",
    "needs_walk": "Spaziergang ausstehend",
}

# FEHLENDE KONSTANTEN HINZUGEFÜGT:

# Gesundheitsstatus-Optionen
HEALTH_STATUS_OPTIONS = [
    "Ausgezeichnet",
    "Sehr gut", 
    "Gut",
    "Normal",
    "Unwohl",
    "Krank",
    "Notfall"
]

# Stimmungsoptionen
MOOD_OPTIONS = [
    "😊 Glücklich",
    "😐 Neutral", 
    "😟 Traurig",
    "😴 Müde",
    "😠 Ärgerlich",
    "😰 Ängstlich",
    "🤗 Aufgeregt"
]

# Energielevel-Optionen
ENERGY_LEVEL_OPTIONS = [
    "Sehr niedrig",
    "Niedrig",
    "Normal",
    "Hoch", 
    "Sehr hoch"
]

# Aktivitätslevel
ACTIVITY_LEVELS = [
    "Sehr ruhig",
    "Ruhig",
    "Normal",
    "Aktiv",
    "Sehr aktiv"
]

# Größenkategorien
SIZE_CATEGORIES = [
    "Toy (< 3kg)",
    "Klein (3-10kg)",
    "Mittel (10-25kg)",
    "Groß (25-45kg)",
    "Riesig (> 45kg)"
]

# Notfall-Level
EMERGENCY_LEVELS = [
    "Normal",
    "Aufmerksamkeit",
    "Warnung",
    "Kritisch",
    "Notfall"
]

# Spaziergang-Typen
WALK_TYPES = [
    "Kurzer Spaziergang",
    "Normaler Spaziergang", 
    "Langer Spaziergang",
    "Jogging",
    "Hundepark",
    "Training",
    "Freilauf"
]

# Validierungsregeln
VALIDATION_RULES = {
    "weight": {"min": MIN_DOG_WEIGHT, "max": MAX_DOG_WEIGHT, "unit": "kg"},
    "age": {"min": MIN_DOG_AGE, "max": MAX_DOG_AGE, "unit": "years"},
}

# Standard-Entity-Blueprints
ENTITIES = {
    "input_boolean": {
        "feeding_morning": {"name": "Frühstück gegeben", "icon": "mdi:food"},
        "feeding_lunch": {"name": "Mittagessen gegeben", "icon": "mdi:food"},
        "feeding_evening": {"name": "Abendessen gegeben", "icon": "mdi:food"},
        "feeding_snack": {"name": "Snack gegeben", "icon": "mdi:food"},
        "walk_in_progress": {"name": "Spaziergang läuft", "icon": "mdi:walk"},
        "outside": {"name": "War draußen", "icon": "mdi:dog-side"},
        "walked_today": {"name": "Heute spazieren gegangen", "icon": "mdi:walk"},
        "medication_given": {"name": "Medikament gegeben", "icon": "mdi:pill"},
        "emergency_mode": {"name": "Notfallmodus", "icon": "mdi:alert"},
        "visitor_mode_input": {"name": "Besuchsmodus", "icon": "mdi:account-group"},
        "gps_tracking_enabled": {"name": "GPS-Tracking aktiv", "icon": "mdi:crosshairs-gps"},
        "auto_walk_detection": {"name": "Automatische Spaziergang-Erkennung", "icon": "mdi:walk"},
    },
    "counter": {
        "walk_count": {"name": "Spaziergänge", "initial": 0, "step": 1, "icon": "mdi:walk"},
        "feeding_morning_count": {"name": "Frühstücks-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
        "feeding_lunch_count": {"name": "Mittagessens-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
        "feeding_evening_count": {"name": "Abendessens-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
        "feeding_snack_count": {"name": "Snack-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
        "outside_count": {"name": "Draußen-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
        "medication_count": {"name": "Medikamenten-Zähler", "initial": 0, "step": 1, "icon": "mdi:counter"},
    },
    "input_text": {
        "notes": {"name": "Notizen", "max": 255, "icon": "mdi:note-text"},
        "current_location": {"name": "Aktuelle Position", "max": 100, "icon": "mdi:map-marker"},
        "gps_tracker_status": {"name": "GPS-Tracker Status", "max": 500, "icon": "mdi:crosshairs-gps"},
        "home_coordinates": {"name": "Heimkoordinaten", "max": 50, "icon": "mdi:home"},
        "visitor_name": {"name": "Besuchername", "max": 100, "icon": "mdi:account"},
        "daily_notes": {"name": "Tagesnotizen", "max": 1000, "icon": "mdi:calendar-text"},
        "activity_history": {"name": "Aktivitätsverlauf", "max": 2000, "icon": "mdi:history"},
    },
    "input_datetime": {
        "last_walk": {"name": "Letzter Spaziergang", "has_date": True, "has_time": True, "icon": "mdi:walk"},
        "last_feeding_morning": {"name": "Letztes Frühstück", "has_date": True, "has_time": True, "icon": "mdi:food"},
        "last_feeding_lunch": {"name": "Letztes Mittagessen", "has_date": True, "has_time": True, "icon": "mdi:food"},
        "last_feeding_evening": {"name": "Letztes Abendessen", "has_date": True, "has_time": True, "icon": "mdi:food"},
        "last_feeding_snack": {"name": "Letzter Snack", "has_date": True, "has_time": True, "icon": "mdi:food"},
        "last_outside": {"name": "Zuletzt draußen", "has_date": True, "has_time": True, "icon": "mdi:dog-side"},
        "feeding_morning_time": {"name": "Frühstückszeit", "has_time": True, "icon": "mdi:clock"},
        "feeding_lunch_time": {"name": "Mittagszeit", "has_time": True, "icon": "mdi:clock"},
        "feeding_evening_time": {"name": "Abendzeit", "has_time": True, "icon": "mdi:clock"},
        "last_activity": {"name": "Letzte Aktivität", "has_date": True, "has_time": True, "icon": "mdi:clock"},
        "visitor_start": {"name": "Besuch Start", "has_date": True, "has_time": True, "icon": "mdi:clock-start"},
        "visitor_end": {"name": "Besuch Ende", "has_date": True, "has_time": True, "icon": "mdi:clock-end"},
    },
    "input_number": {
        "weight": {"name": "Gewicht", "min": MIN_DOG_WEIGHT, "max": MAX_DOG_WEIGHT, "step": 0.1, "unit": "kg", "icon": "mdi:weight"},
        "gps_signal_strength": {"name": "GPS-Signalstärke", "min": 0, "max": 100, "step": 1, "unit": "%", "icon": "mdi:signal"},
        "gps_battery_level": {"name": "GPS-Batterie", "min": 0, "max": 100, "step": 1, "unit": "%", "icon": "mdi:battery"},
        "home_distance": {"name": "Entfernung zu Hause", "min": 0, "max": 10000, "step": 1, "unit": "m", "icon": "mdi:map-marker-distance"},
        "current_walk_distance": {"name": "Aktuelle Spaziergang-Distanz", "min": 0, "max": 100, "step": 0.01, "unit": "km", "icon": "mdi:map-marker-path"},
        "current_walk_duration": {"name": "Aktuelle Spaziergang-Dauer", "min": 0, "max": 1440, "step": 1, "unit": "min", "icon": "mdi:timer"},
        "current_walk_speed": {"name": "Aktuelle Geschwindigkeit", "min": 0, "max": 50, "step": 0.1, "unit": "km/h", "icon": "mdi:speedometer"},
        "daily_walk_duration": {"name": "Tägliche Spaziergang-Dauer", "min": 0, "max": 1440, "step": 1, "unit": "min", "icon": "mdi:timer"},
        "geofence_radius": {"name": "Geofence-Radius", "min": 10, "max": 1000, "step": 10, "unit": "m", "icon": "mdi:map-marker-radius"},
    },
    "input_select": {
        "health_status": {"name": "Gesundheitsstatus", "options": HEALTH_STATUS_OPTIONS, "icon": "mdi:heart"},
        "mood": {"name": "Stimmung", "options": MOOD_OPTIONS, "icon": "mdi:emoticon"},
        "energy_level": {"name": "Energielevel", "options": ENERGY_LEVEL_OPTIONS, "icon": "mdi:battery"},
        "activity_level": {"name": "Aktivitätslevel", "options": ACTIVITY_LEVELS, "icon": "mdi:run"},
        "emergency_level": {"name": "Notfall-Level", "options": EMERGENCY_LEVELS, "icon": "mdi:alert"},
    },
}
