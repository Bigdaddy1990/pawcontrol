"""Service schemas for Paw Control integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_DOG_ID,
    FOOD_BARF,
    FOOD_DRY,
    FOOD_TREAT,
    FOOD_WET,
    GROOMING_BATH,
    GROOMING_BRUSH,
    GROOMING_EARS,
    GROOMING_EYES,
    GROOMING_NAILS,
    GROOMING_TEETH,
    GROOMING_TRIM,
    INTENSITY_HIGH,
    INTENSITY_LOW,
    INTENSITY_MEDIUM,
    MEAL_BREAKFAST,
    MEAL_DINNER,
    MEAL_LUNCH,
    MEAL_SNACK,
)

# Service validation schemas
SERVICE_START_WALK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("source", default="manual"): vol.In(["manual", "gps", "door"]),
    }
)

SERVICE_END_WALK_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("reason", default="manual"): vol.In(["manual", "home", "idle"]),
    }
)

SERVICE_WALK_DOG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Required("duration_min"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=600)
        ),
        vol.Optional("distance_m", default=1000): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100000)
        ),
    }
)

SERVICE_FEED_DOG_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Required("meal_type"): vol.In(
            [MEAL_BREAKFAST, MEAL_LUNCH, MEAL_DINNER, MEAL_SNACK]
        ),
        vol.Optional("portion_g", default=200): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=1500)
        ),
        vol.Optional("food_type", default=FOOD_DRY): vol.In(
            [FOOD_DRY, FOOD_WET, FOOD_BARF, FOOD_TREAT]
        ),
    }
)

SERVICE_LOG_HEALTH_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("weight_kg"): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=100)
        ),
        vol.Optional("note", default=""): cv.string,
    }
)

SERVICE_LOG_MEDICATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Required("medication_name"): cv.string,
        vol.Required("dose"): cv.string,
    }
)

SERVICE_START_GROOMING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("type", default=GROOMING_BRUSH): vol.In(
            [
                GROOMING_BATH,
                GROOMING_BRUSH,
                GROOMING_TRIM,
                GROOMING_NAILS,
                GROOMING_EARS,
                GROOMING_TEETH,
                GROOMING_EYES,
            ]
        ),
        vol.Optional("notes", default=""): cv.string,
    }
)

SERVICE_PLAY_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("duration_min", default=15): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=240)
        ),
        vol.Optional("intensity", default=INTENSITY_MEDIUM): vol.In(
            [INTENSITY_LOW, INTENSITY_MEDIUM, INTENSITY_HIGH]
        ),
    }
)

SERVICE_TRAINING_SESSION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Required("topic"): cv.string,
        vol.Optional("duration_min", default=15): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=240)
        ),
        vol.Optional("notes", default=""): cv.string,
    }
)

SERVICE_TOGGLE_VISITOR_SCHEMA = vol.Schema(
    {
        vol.Required("enabled"): cv.boolean,
    }
)

SERVICE_EMERGENCY_MODE_SCHEMA = vol.Schema(
    {
        vol.Optional("level", default="info"): vol.In(["info", "warn", "critical"]),
        vol.Optional("note", default=""): cv.string,
    }
)

SERVICE_GENERATE_REPORT_SCHEMA = vol.Schema(
    {
        vol.Optional("scope", default="daily"): vol.In(["daily", "weekly", "custom"]),
        vol.Optional("target", default="notification"): vol.In(
            ["file", "notification"]
        ),
        vol.Optional("format", default="text"): vol.In(["text", "csv", "json", "pdf"]),
    }
)

SERVICE_EXPORT_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DOG_ID): cv.string,
        vol.Optional("from"): cv.date,
        vol.Optional("to"): cv.date,
        vol.Optional("format", default="csv"): vol.In(["csv", "json"]),
    }
)

SERVICE_NOTIFY_TEST_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DOG_ID): cv.string,
        vol.Optional("message"): cv.string,
    }
)


SERVICE_GPS_START_WALK_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): str,
        vol.Optional("dog_id"): str,
        vol.Optional("label"): str,
    }
)


SERVICE_GPS_END_WALK_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_GPS_POST_LOCATION_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): str,
        vol.Required("latitude"): vol.Coerce(float),
        vol.Required("longitude"): vol.Coerce(float),
        vol.Optional("accuracy_m", default=0): vol.Coerce(float),
        vol.Optional("speed_m_s"): vol.Coerce(float),
        vol.Optional("timestamp"): str,
        vol.Optional("dog_id"): str,
    }
)


SERVICE_GPS_PAUSE_TRACKING_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_GPS_RESUME_TRACKING_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_GPS_EXPORT_LAST_ROUTE_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_GPS_GENERATE_DIAGNOSTICS_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_GPS_RESET_STATS_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_ROUTE_HISTORY_LIST_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_ROUTE_HISTORY_PURGE_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("dog_id"): str}
)


SERVICE_ROUTE_HISTORY_EXPORT_RANGE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): str,
        vol.Optional("dog_id"): str,
        vol.Optional("date_from"): str,
        vol.Optional("date_to"): str,
    }
)


SERVICE_TOGGLE_GEOFENCE_ALERTS_SCHEMA = vol.Schema(
    {vol.Optional("config_entry_id"): str, vol.Optional("enabled", default=True): bool}
)


SERVICE_PURGE_ALL_STORAGE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): str,
    }
)

SERVICE_PRUNE_STALE_DEVICES_SCHEMA = vol.Schema(
    {vol.Optional("auto", default=False): bool}
)
