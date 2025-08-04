"""Utility functions for Paw Control integration."""
from __future__ import annotations

import re
import logging
from datetime import datetime, timedelta, timezone
from math import radians, sin, cos, sqrt, atan2, isfinite
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.util import slugify

from .const import (
    MIN_DOG_NAME_LENGTH,
    MAX_DOG_NAME_LENGTH,
    MIN_DOG_AGE,
    MAX_DOG_AGE,
    DOG_NAME_PATTERN,
    GPS_ACCURACY_THRESHOLDS,
    VALIDATION_RULES,
)
from .exceptions import InvalidCoordinates, DataValidationError

_LOGGER = logging.getLogger(__name__)


# Precompile dog name pattern for reuse
DOG_NAME_RE = re.compile(DOG_NAME_PATTERN)


def merge_entry_options(entry: ConfigEntry) -> dict[str, Any]:
    """Merge config entry data and options.

    Options take precedence over data. The returned dictionary is a new copy
    so callers can modify it without affecting the original entry.
    """

    return {**entry.data, **entry.options}


def register_services(
    hass: HomeAssistant,
    domain: str,
    services: Mapping[str, Callable[..., Any]],
) -> None:
    """Register multiple service handlers for ``domain``.

    ``services`` should be a mapping of service name to async handler function.
    The handlers are registered with Home Assistant using
    :func:`homeassistant.core.ServiceRegistry.async_register`.
    """

    for service, handler in services.items():
        hass.services.async_register(domain, service, handler)


async def call_service(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: Mapping[str, Any] | None = None,
    *,
    blocking: bool = True,
) -> None:
    """Wrapper around ``HomeAssistant`` service calls.

    This helper centralises :func:`homeassistant.core.ServiceRegistry.async_call`
    usage, providing a consistent interface for calling services throughout the
    integration.
    """

    await hass.services.async_call(domain, service, data or {}, blocking=blocking)


def validate_dog_name(name: str) -> bool:
    """Validate dog name format and constraints."""
    if not name or not isinstance(name, str):
        return False

    name = name.strip()

    # Check length
    if len(name) < MIN_DOG_NAME_LENGTH or len(name) > MAX_DOG_NAME_LENGTH:
        return False

    # Check for valid characters (letters, numbers, spaces, common punctuation)
    if not DOG_NAME_RE.match(name):
        return False

    # Must start with a letter
    if not name[0].isalpha():
        return False

    return True


def validate_weight(weight: float) -> bool:
    """Check that weight can be converted to a positive, finite float."""
    value = safe_float_convert(weight, default=float("nan"))
    return value > 0 and isfinite(value)


def validate_age(age: int) -> bool:
    """Validate dog age."""
    try:
        age = int(age)
        return MIN_DOG_AGE <= age <= MAX_DOG_AGE
    except (ValueError, TypeError):
        return False


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate GPS coordinates."""
    try:
        lat = float(latitude)
        lon = float(longitude)
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (ValueError, TypeError):
        return False


def validate_gps_accuracy(accuracy: float) -> bool:
    """Validate GPS accuracy value."""
    try:
        acc = float(accuracy)
        return 0 <= acc <= 1000  # Max 1000 meters
    except (ValueError, TypeError):
        return False


def calculate_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """Calculate distance between two GPS coordinates in meters using Haversine formula."""
    if not validate_coordinates(coord1[0], coord1[1]) or not validate_coordinates(coord2[0], coord2[1]):
        raise InvalidCoordinates("Invalid GPS coordinates provided")
    
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    # Earth's radius in meters
    r = 6371000
    
    return r * c


def format_duration(minutes: int) -> str:
    """Format duration in minutes to a human readable string."""
    if not isinstance(minutes, int) or minutes <= 0:
        return "0 min"

    hours, remainder = divmod(minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    if remainder == 0:
        return f"{hours}h"
    return f"{hours}h {remainder}min"


def format_distance(meters: float) -> str:
    """Format distance in meters to human readable string."""
    try:
        meters = float(meters)
    except (TypeError, ValueError):
        return "0m"

    # Reject NaN or infinite values and normalise negatives
    if not isfinite(meters) or meters < 0:
        meters = 0

    if meters < 1000:
        return f"{int(meters)}m"

    km = meters / 1000

    # Avoid showing trailing .0 for whole kilometers (e.g., 1000 -> "1km")
    if float(km).is_integer():
        return f"{int(km)}km"

    return f"{km:.1f}km"


def format_weight(kg: float) -> str:
    """Format weight to a human readable string.

    Ensures invalid, non-numeric or negative values are handled gracefully
    instead of raising errors or returning misleading results.
    """
    kg_value = safe_float_convert(kg)
    if not isfinite(kg_value) or kg_value < 0:
        kg_value = 0.0
    return f"{kg_value:.1f}kg"


def get_gps_accuracy_level(accuracy: float) -> str:
    """Get GPS accuracy level description."""
    if accuracy <= GPS_ACCURACY_THRESHOLDS["excellent"]:
        return "Ausgezeichnet"
    elif accuracy <= GPS_ACCURACY_THRESHOLDS["good"]:
        return "Gut"
    elif accuracy <= GPS_ACCURACY_THRESHOLDS["acceptable"]:
        return "Akzeptabel"
    else:
        return "Schlecht"


def calculate_dog_calories_per_day(weight_kg: float, activity_level: str = "normal") -> int:
    """Calculate daily calorie needs for a dog based on weight and activity level."""
    # Validate weight to avoid math errors with invalid or negative values
    if not validate_weight(weight_kg):
        return 0

    weight = float(weight_kg)

    # Base formula: RER = 70 * (weight in kg)^0.75
    rer = 70 * (weight ** 0.75)

    # Activity multipliers
    multipliers = {
        "very_low": 1.2,
        "low": 1.4,
        "normal": 1.6,
        "high": 1.8,
        "very_high": 2.0,
    }

    multiplier = multipliers.get(activity_level, 1.6)
    return int(rer * multiplier)


def calculate_ideal_walk_duration(weight_kg: float, age_years: float, activity_level: str = "normal") -> int:
    """Calculate ideal daily walk duration in minutes."""
    # Base time per kg (adult dog)
    base_minutes_per_kg = 2
    
    # Age adjustments
    if age_years < 1:  # Puppy
        age_multiplier = 0.5
    elif age_years > 8:  # Senior
        age_multiplier = 0.7
    else:  # Adult
        age_multiplier = 1.0
    
    # Activity level adjustments
    activity_multipliers = {
        "very_low": 0.5,
        "low": 0.7,
        "normal": 1.0,
        "high": 1.3,
        "very_high": 1.5
    }
    
    activity_multiplier = activity_multipliers.get(activity_level, 1.0)
    
    # Calculate
    base_time = weight_kg * base_minutes_per_kg
    adjusted_time = base_time * age_multiplier * activity_multiplier
    
    # Reasonable bounds
    return max(15, min(180, int(adjusted_time)))


def validate_service_data(data: Dict[str, Any], required_fields: List[str]) -> bool:
    """Validate service call data."""
    if not isinstance(data, dict):
        return False
    
    for field in required_fields:
        if field not in data:
            return False
    
    return True


def safe_float_convert(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int_convert(value: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def generate_entity_id(dog_name: str, entity_type: str, suffix: str) -> str:
    """Generate consistent entity ID."""
    dog_slug = slugify(dog_name)
    return f"{entity_type}.{dog_slug}_{suffix}"


def parse_coordinates_string(coord_string: str) -> Tuple[float, float]:
    """Parse coordinates from string format 'latitude,longitude'."""
    try:
        parts = coord_string.split(',')
        if len(parts) != 2:
            raise ValueError("Invalid coordinate format")
        
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        
        if not validate_coordinates(lat, lon):
            raise ValueError("Invalid coordinate values")
        
        return lat, lon
        
    except (ValueError, IndexError) as e:
        raise InvalidCoordinates(f"Could not parse coordinates '{coord_string}': {e}")


def format_coordinates(latitude: float, longitude: float, precision: int = 6) -> str:
    """Format coordinates to string."""
    return f"{latitude:.{precision}f},{longitude:.{precision}f}"


def calculate_speed_kmh(distance_m: float, time_seconds: float) -> float:
    """Calculate speed in km/h from distance in meters and time in seconds."""
    try:
        distance = float(distance_m)
        seconds = float(time_seconds)
    except (TypeError, ValueError):
        return 0.0

    if seconds <= 0 or distance < 0 or not isfinite(distance) or not isfinite(seconds):
        return 0.0

    # Convert to km/h
    speed_ms = distance / seconds
    speed_kmh = speed_ms * 3.6

    return round(speed_kmh, 1)


def estimate_calories_burned(distance_km: float, weight_kg: float, activity_intensity: str = "medium") -> int:
    """Estimate calories burned during activity."""
    # Base calories per km per kg
    base_cal_per_km_per_kg = 0.8
    
    # Intensity multipliers
    intensity_multipliers = {
        "low": 0.7,
        "medium": 1.0,
        "high": 1.4,
        "extreme": 1.8
    }
    
    multiplier = intensity_multipliers.get(activity_intensity, 1.0)
    calories = distance_km * weight_kg * base_cal_per_km_per_kg * multiplier
    
    return max(1, int(calories))


def time_since_last_activity(last_activity_time: str | datetime) -> timedelta:
    """Calculate time since last activity.

    Accepts ISO formatted strings or ``datetime`` objects. Any parsing errors
    result in a large ``timedelta`` so callers can treat unknown values
    consistently.
    """
    try:
        if not last_activity_time or last_activity_time in ["unknown", "unavailable"]:
            return timedelta(days=999)  # Very long time if unknown

        if isinstance(last_activity_time, datetime):
            last_time = last_activity_time
        else:
            last_time = datetime.fromisoformat(str(last_activity_time).replace("Z", "+00:00"))

        if last_time.tzinfo:
            now = datetime.now(timezone.utc)
            last_time = last_time.astimezone(timezone.utc)
        else:
            now = datetime.now()

        return now - last_time

    except (ValueError, TypeError):
        return timedelta(days=999)


def is_time_for_activity(last_activity_time: str, interval_hours: float) -> bool:
    """Check if enough time has passed for next activity."""
    time_since = time_since_last_activity(last_activity_time)
    return time_since >= timedelta(hours=interval_hours)


def get_activity_status_emoji(activity_type: str, completed: bool) -> str:
    """Get emoji for activity status."""
    activity_emojis = {
        "feeding": "🍽️",
        "walk": "🚶",
        "play": "🎾",
        "training": "🎓",
        "health": "🏥",
        "grooming": "✂️",
        "medication": "💊",
        "vet": "🩺"
    }
    
    emoji = activity_emojis.get(activity_type, "📝")
    status = "✅" if completed else "⏳"
    
    return f"{emoji} {status}"


def validate_data_against_rules(data: Dict[str, Any]) -> List[str]:
    """Validate data against defined validation rules."""
    errors = []
    
    for field, value in data.items():
        if field in VALIDATION_RULES:
            rule = VALIDATION_RULES[field]
            
            try:
                num_value = float(value)
                
                if num_value < rule["min"]:
                    errors.append(f"{field} must be at least {rule['min']} {rule['unit']}")
                elif num_value > rule["max"]:
                    errors.append(f"{field} must be at most {rule['max']} {rule['unit']}")
                    
            except (ValueError, TypeError):
                errors.append(f"{field} must be a valid number")
    
    return errors


def create_backup_filename(dog_name: str, backup_type: str = "full") -> str:
    """Create backup filename with timestamp."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dog_slug = slugify(dog_name)
    return f"paw_control_{dog_slug}_{backup_type}_{timestamp}.json"


def normalize_dog_name(name: str) -> str:
    """Normalize dog name for consistent use."""
    if not name:
        return ""
    
    # Remove extra whitespace and convert to title case
    normalized = " ".join(name.strip().split())
    return normalized.title()


def get_meal_time_category(hour: int) -> str:
    """Get meal category based on hour of day."""
    if 5 <= hour < 10:
        return "morning"
    elif 11 <= hour < 15:
        return "lunch"
    elif 17 <= hour < 21:
        return "evening"
    else:
        return "snack"


def calculate_dog_age_in_human_years(dog_age_years: float, size_category: str = "medium") -> int:
    """Calculate dog age in human equivalent years."""
    # Different aging rates by size
    if dog_age_years <= 2:
        # First 2 years are rapid aging
        human_years = dog_age_years * 10.5
    else:
        # After 2 years, aging rate depends on size
        size_multipliers = {
            "toy": 4,
            "small": 4.5,
            "medium": 5,
            "large": 5.5,
            "giant": 6
        }
        
        multiplier = size_multipliers.get(size_category, 5)
        human_years = 21 + (dog_age_years - 2) * multiplier
    
    return int(human_years)


def is_healthy_weight_for_breed(weight_kg: float, breed_size: str) -> bool:
    """Check if weight is healthy for breed size."""
    weight_ranges = {
        "toy": (1, 6),
        "small": (6, 12),
        "medium": (12, 27),
        "large": (27, 45),
        "giant": (45, 90)
    }
    
    if breed_size not in weight_ranges:
        return True  # Unknown breed, assume healthy
    
    min_weight, max_weight = weight_ranges[breed_size]
    return min_weight <= weight_kg <= max_weight


async def safe_service_call(hass: HomeAssistant, domain: str, service: str, data: dict) -> bool:
    """Make a safe service call with error handling."""
    try:
        entity_id = data.get("entity_id")
        
        # Check if service exists
        if not hass.services.has_service(domain, service):
            _LOGGER.debug("Service %s.%s not available", domain, service)
            return False
        
        # Check if entity exists (if specified)
        if entity_id and not hass.states.get(entity_id):
            _LOGGER.debug("Entity %s not found, skipping service call", entity_id)
            return False
        
        await hass.services.async_call(domain, service, data, blocking=True)
        return True
        
    except Exception as e:
        _LOGGER.debug("Service call %s.%s failed: %s", domain, service, e)
        return False


def extract_dog_name_from_entity_id(entity_id: str) -> str:
    """Extract dog name from entity_id."""
    try:
        # Remove domain prefix
        entity_name = entity_id.split(".", 1)[1] if "." in entity_id else entity_id
        
        # Extract dog name (first part before underscore)
        parts = entity_name.split("_")
        return parts[0] if parts else entity_name
        
    except (IndexError, AttributeError):
        return ""


def create_notification_id(dog_name: str, notification_type: str) -> str:
    """Create unique notification ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dog_slug = slugify(dog_name)
    return f"paw_control_{dog_slug}_{notification_type}_{timestamp}"


def format_time_ago(dt: datetime) -> str:
    """Format datetime as 'time ago' string."""
    now = datetime.now()
    diff = now - dt
    
    if diff.days > 0:
        return f"vor {diff.days} Tag{'en' if diff.days > 1 else ''}"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"vor {hours} Stunde{'n' if hours > 1 else ''}"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"vor {minutes} Minute{'n' if minutes > 1 else ''}"
    else:
        return "gerade eben"


def get_health_status_color(status: str) -> str:
    """Get color for health status."""
    status_colors = {
        "ausgezeichnet": "green",
        "sehr gut": "lightgreen",
        "gut": "green",
        "normal": "blue",
        "unwohl": "orange",
        "krank": "red",
        "notfall": "darkred"
    }
    
    return status_colors.get(status.lower(), "gray")


def calculate_feeding_amount_by_weight(weight_kg: float, meals_per_day: int = 2) -> int:
    """Calculate daily feeding amount in grams based on weight."""
    # Validate weight to avoid math errors with invalid or negative values
    if not validate_weight(weight_kg):
        return 0

    # Rough guideline: 2-3% of body weight per day
    daily_amount = float(weight_kg) * 25  # 2.5% in grams

    # Safely handle meal count; default to 1 if invalid to avoid division errors
    try:
        meals = int(meals_per_day)
    except (TypeError, ValueError):
        meals = 1

    if meals <= 0:
        meals = 1

    # Adjust for number of meals
    return int(daily_amount / meals)


def is_emergency_situation(health_data: Dict[str, Any]) -> bool:
    """Determine if health data indicates emergency situation."""
    emergency_indicators = [
        health_data.get("temperature", 0) > 41.0,  # High fever
        health_data.get("temperature", 0) < 37.0,  # Hypothermia
        health_data.get("heart_rate", 0) > 180,    # Tachycardia
        health_data.get("heart_rate", 0) < 50,     # Bradycardia
        "notfall" in str(health_data.get("health_status", "")).lower(),
        "emergency" in str(health_data.get("emergency_mode", "")).lower()
    ]
    
    return any(emergency_indicators)
