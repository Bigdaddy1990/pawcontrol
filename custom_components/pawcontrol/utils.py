"""Utility functions for PawControl integration."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2
from typing import Any

from homeassistant.util import dt as dt_util

from .const import (
    MIN_DOG_NAME_LENGTH,
    MAX_DOG_NAME_LENGTH,
    MIN_DOG_WEIGHT,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MAX_DOG_AGE,
    MIN_TEMPERATURE,
    MAX_TEMPERATURE,
    SIZE_TOY,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_GIANT,
    EARTH_RADIUS_M,
    ALL_MODULES,
)


_LOGGER = logging.getLogger(__name__)


# Validation Functions
def validate_dog_name(name: str) -> bool:
    """Validate dog name.

    Leading and trailing whitespace is ignored so that names entered with
    accidental spaces are still considered valid. Non-string inputs are
    rejected early.
    """
    if not isinstance(name, str):
        return False

    name = name.strip()
    if not name or len(name) < MIN_DOG_NAME_LENGTH or len(name) > MAX_DOG_NAME_LENGTH:
        return False

    # Allow letters, numbers, spaces, hyphens, underscores, and umlauts
    pattern = r"^[a-zA-ZäöüÄÖÜß0-9\s\-_.]+$"
    return bool(re.match(pattern, name))


def validate_weight(weight: float) -> bool:
    """Validate dog weight."""
    try:
        weight = float(weight)
        return MIN_DOG_WEIGHT <= weight <= MAX_DOG_WEIGHT
    except (ValueError, TypeError):
        return False


def validate_age(age: float) -> bool:
    """Validate dog age."""
    try:
        age = float(age)
        return MIN_DOG_AGE <= age <= MAX_DOG_AGE
    except (ValueError, TypeError):
        return False


def validate_temperature(temp: float) -> bool:
    """Validate dog temperature."""
    try:
        temp = float(temp)
        return MIN_TEMPERATURE <= temp <= MAX_TEMPERATURE
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
    """Validate GPS accuracy."""
    try:
        acc = float(accuracy)
        return 0 <= acc <= 1000  # meters
    except (ValueError, TypeError):
        return False


# Configuration Utilities
def filter_invalid_modules(modules: dict[str, Any]) -> dict[str, Any]:
    """Remove unknown modules from configuration.

    Returns a new dictionary containing only modules defined in
    :const:`ALL_MODULES`. Unknown modules are logged and discarded to avoid
    setup errors when the configuration was manually edited or imported from
    an older version.
    """
    if not isinstance(modules, dict):
        return {}

    valid: dict[str, Any] = {}
    for module_id, config in modules.items():
        if module_id in ALL_MODULES:
            valid[module_id] = config
        else:
            _LOGGER.warning("Unknown module '%s' removed from configuration", module_id)

    return valid


# Calculation Functions
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two GPS coordinates using Haversine formula."""
    try:
        if not validate_coordinates(lat1, lon1) or not validate_coordinates(lat2, lon2):
            return 0.0

        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return EARTH_RADIUS_M * c
    except (ValueError, TypeError):
        return 0.0


def calculate_speed_kmh(distance_m: float, time_minutes: float) -> float:
    """Calculate speed in km/h from distance and time."""
    try:
        if time_minutes <= 0:
            return 0.0
        
        # Convert to km/h
        distance_km = distance_m / 1000
        time_hours = time_minutes / 60
        
        return distance_km / time_hours
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def calculate_dog_calories_per_day(weight_kg: float, activity_level: str = "Normal") -> float:
    """Calculate daily calorie needs for a dog."""
    try:
        weight = float(weight_kg)
        
        # Base metabolic rate (RER = 70 * weight^0.75)
        rer = 70 * (weight ** 0.75)
        
        # Activity multipliers
        multipliers = {
            "Sehr niedrig": 1.2,  # Neutered adult, inactive
            "Niedrig": 1.4,       # Neutered adult, typical
            "Normal": 1.6,        # Intact adult, typical
            "Hoch": 2.0,          # Light work
            "Sehr hoch": 3.0,     # Heavy work
        }
        
        multiplier = multipliers.get(activity_level, 1.6)
        
        return round(rer * multiplier)
    except (ValueError, TypeError):
        return 0.0


def calculate_ideal_walk_duration(
    weight_kg: float,
    age_years: float,
    activity_level: str = "Normal"
) -> int:
    """Calculate ideal daily walk duration in minutes."""
    try:
        weight = float(weight_kg)
        age = float(age_years)
        
        # Base duration based on size
        if weight < 5:  # Toy
            base_duration = 30
        elif weight < 10:  # Small
            base_duration = 45
        elif weight < 25:  # Medium
            base_duration = 60
        elif weight < 45:  # Large
            base_duration = 75
        else:  # Giant
            base_duration = 60  # Giant breeds need less intense exercise
        
        # Age adjustment
        if age < 1:  # Puppy
            age_factor = 0.5
        elif age < 2:  # Young
            age_factor = 0.8
        elif age < 7:  # Adult
            age_factor = 1.0
        elif age < 10:  # Senior
            age_factor = 0.8
        else:  # Elderly
            age_factor = 0.6
        
        # Activity level adjustment
        activity_factors = {
            "Sehr niedrig": 0.6,
            "Niedrig": 0.8,
            "Normal": 1.0,
            "Hoch": 1.3,
            "Sehr hoch": 1.6,
        }
        
        activity_factor = activity_factors.get(activity_level, 1.0)
        
        return int(base_duration * age_factor * activity_factor)
    except (ValueError, TypeError):
        return 30


def calculate_dog_age_in_human_years(age_years: float, size: str = SIZE_MEDIUM) -> float:
    """Calculate dog age in human years."""
    try:
        age = float(age_years)
        
        # Different conversion rates based on size
        # Small dogs age slower, large dogs age faster
        if age <= 2:
            # First two years are roughly the same for all sizes
            human_age = age * 12.5
        else:
            # After 2 years, size matters more
            size_multipliers = {
                SIZE_TOY: 4.0,
                SIZE_SMALL: 4.5,
                SIZE_MEDIUM: 5.0,
                SIZE_LARGE: 5.5,
                SIZE_GIANT: 6.0,
            }
            
            multiplier = size_multipliers.get(size, 5.0)
            human_age = 25 + ((age - 2) * multiplier)
        
        return round(human_age, 1)
    except (ValueError, TypeError):
        return 0.0


def estimate_calories_burned(
    weight_kg: float,
    activity_type: str,
    duration_minutes: int,
    intensity: str = "Normal"
) -> float:
    """Estimate calories burned during activity."""
    try:
        weight = float(weight_kg)
        duration = float(duration_minutes)
        
        # MET values for different activities
        met_values = {
            "walk": {"Niedrig": 2.0, "Normal": 3.0, "Hoch": 4.0},
            "run": {"Niedrig": 5.0, "Normal": 7.0, "Hoch": 9.0},
            "play": {"Niedrig": 3.0, "Normal": 4.5, "Hoch": 6.0},
            "swim": {"Niedrig": 4.0, "Normal": 6.0, "Hoch": 8.0},
            "training": {"Niedrig": 2.5, "Normal": 3.5, "Hoch": 4.5},
        }
        
        activity_mets = met_values.get(activity_type, met_values["walk"])
        met = activity_mets.get(intensity, activity_mets["Normal"])
        
        # Calories = MET * weight * time(hours)
        calories = met * weight * (duration / 60)
        
        return round(calories)
    except (ValueError, TypeError, KeyError):
        return 0.0


# Formatting Functions
def format_duration(minutes: int) -> str:
    """Format duration from minutes to readable string."""
    try:
        minutes = int(minutes)
        if minutes < 60:
            return f"{minutes} min"
        
        hours = minutes // 60
        remaining_minutes = minutes % 60
        
        if remaining_minutes == 0:
            return f"{hours}h"
        return f"{hours}h {remaining_minutes}min"
    except (ValueError, TypeError):
        return "0 min"


def format_distance(meters: float) -> str:
    """Format distance from meters to readable string."""
    try:
        meters = float(meters)
        if meters < 1000:
            return f"{int(meters)}m"
        
        km = meters / 1000
        return f"{km:.1f}km"
    except (ValueError, TypeError):
        return "0m"


def format_weight(kg: float) -> str:
    """Format weight to readable string."""
    try:
        kg = float(kg)
        return f"{kg:.1f}kg"
    except (ValueError, TypeError):
        return "0kg"


def format_temperature(celsius: float) -> str:
    """Format temperature to readable string."""
    try:
        celsius = float(celsius)
        return f"{celsius:.1f}°C"
    except (ValueError, TypeError):
        return "0°C"


def format_time_ago(dt: datetime | None) -> str:
    """Format datetime to 'time ago' string."""
    if not dt:
        return "Nie"
    
    try:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        
        now = dt_util.now()
        diff = now - dt
        
        if diff.days > 365:
            years = diff.days // 365
            return f"vor {years} Jahr{'en' if years > 1 else ''}"
        elif diff.days > 30:
            months = diff.days // 30
            return f"vor {months} Monat{'en' if months > 1 else ''}"
        elif diff.days > 0:
            return f"vor {diff.days} Tag{'en' if diff.days > 1 else ''}"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"vor {hours} Stunde{'n' if hours > 1 else ''}"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"vor {minutes} Minute{'n' if minutes > 1 else ''}"
        else:
            return "Gerade eben"
    except Exception:
        return "Unbekannt"


# Helper Functions
def get_size_by_weight(weight_kg: float) -> str:
    """Get size category based on weight."""
    try:
        weight = float(weight_kg)
        if weight < 5:
            return SIZE_TOY
        elif weight < 10:
            return SIZE_SMALL
        elif weight < 25:
            return SIZE_MEDIUM
        elif weight < 45:
            return SIZE_LARGE
        else:
            return SIZE_GIANT
    except (ValueError, TypeError):
        return SIZE_MEDIUM


def get_meal_type_by_time(hour: int | None = None) -> str:
    """Get meal type based on current time."""
    if hour is None:
        hour = dt_util.now().hour
    
    if 5 <= hour < 11:
        return "breakfast"
    elif 11 <= hour < 15:
        return "lunch"
    elif 15 <= hour < 21:
        return "dinner"
    else:
        return "snack"


def is_feeding_time(feeding_times: dict[str, str], tolerance_minutes: int = 30) -> tuple[bool, str | None]:
    """Check if current time is near a feeding time."""
    now = dt_util.now()
    current_time = now.strftime("%H:%M")
    
    for meal_type, meal_time in feeding_times.items():
        if not meal_time:
            continue
        
        try:
            # Parse meal time
            meal_hour, meal_minute = map(int, meal_time.split(":"))
            meal_datetime = now.replace(hour=meal_hour, minute=meal_minute, second=0, microsecond=0)
            
            # Check if within tolerance
            time_diff = abs((now - meal_datetime).total_seconds() / 60)
            if time_diff <= tolerance_minutes:
                return True, meal_type
        except (ValueError, AttributeError):
            continue
    
    return False, None


def is_walk_needed(last_walk: datetime | str | None, hours_threshold: int = 8) -> bool:
    """Check if dog needs a walk based on last walk time."""
    if not last_walk:
        return True
    
    try:
        if isinstance(last_walk, str):
            last_walk = datetime.fromisoformat(last_walk)
        
        hours_since = (dt_util.now() - last_walk).total_seconds() / 3600
        return hours_since >= hours_threshold
    except Exception:
        return True


def is_emergency_situation(health_data: dict[str, Any]) -> bool:
    """Check if current health data indicates an emergency."""
    # Temperature check
    temp = health_data.get("temperature", 38.5)
    if temp < 37.0 or temp > 41.0:
        return True
    
    # Heart rate check (assuming normal is 60-140 for dogs)
    heart_rate = health_data.get("heart_rate", 80)
    if heart_rate < 50 or heart_rate > 180:
        return True
    
    # Respiratory rate check (normal is 10-30)
    respiratory = health_data.get("respiratory_rate", 20)
    if respiratory < 8 or respiratory > 40:
        return True
    
    # Check for critical symptoms
    symptoms = health_data.get("symptoms", [])
    critical_symptoms = [
        "kollaps", "bewusstlos", "krampf", "blutung",
        "atemnot", "vergiftung", "unfall"
    ]
    
    for symptom in symptoms:
        if any(critical in symptom.lower() for critical in critical_symptoms):
            return True
    
    return False


def calculate_feeding_amount_by_weight(weight_kg: float, meals_per_day: int = 2) -> float:
    """Calculate recommended feeding amount per meal based on weight."""
    try:
        weight = float(weight_kg)
        meals = int(meals_per_day)
        
        # Daily amount is typically 2-3% of body weight
        # Using 2.5% as average
        daily_amount = weight * 1000 * 0.025  # in grams
        
        # Divide by number of meals
        per_meal = daily_amount / meals
        
        return round(per_meal, 0)
    except (ValueError, TypeError, ZeroDivisionError):
        return 200.0  # Default amount


def get_activity_status_emoji(activity_type: str, status: str = "active") -> str:
    """Get emoji for activity type and status."""
    emojis = {
        "walk": {"active": "🚶", "completed": "✅", "needed": "⏰"},
        "feeding": {"active": "🍽️", "completed": "✅", "needed": "🔔"},
        "play": {"active": "🎾", "completed": "✅", "needed": "🎮"},
        "training": {"active": "🎯", "completed": "✅", "needed": "📚"},
        "grooming": {"active": "✂️", "completed": "✅", "needed": "🧹"},
        "sleep": {"active": "😴", "completed": "🌙", "needed": "🛏️"},
        "health": {"active": "🏥", "completed": "✅", "needed": "⚕️"},
        "emergency": {"active": "🚨", "completed": "✅", "needed": "⚠️"},
    }
    
    activity_emojis = emojis.get(activity_type, {})
    return activity_emojis.get(status, "📝")


def sanitize_entity_id(name: str | None) -> str:
    """Sanitize a name for use in entity IDs."""
    # Ensure we have a string to work with
    if not isinstance(name, str):
        name = str(name) if name is not None else ""

    # Convert to lowercase
    name = name.lower()

    # Replace spaces and special characters with underscores
    name = re.sub(r"[^a-z0-9]+", "_", name)

    # Remove leading/trailing underscores
    name = name.strip("_")

    # Replace multiple underscores with single
    name = re.sub(r"_+", "_", name)

    return name or "unknown"


def parse_time_string(time_str: str) -> tuple[int, int] | None:
    """Parse time string (HH:MM) to hour and minute."""
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            hour = int(parts[0])
            minute = int(parts[1])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return hour, minute
    except (ValueError, AttributeError):
        pass
    return None


def is_night_time(hour: int | None = None) -> bool:
    """Check if it's night time (between 22:00 and 06:00)."""
    if hour is None:
        hour = dt_util.now().hour
    return hour >= 22 or hour < 6


def get_next_scheduled_time(schedule_times: list[str]) -> str | None:
    """Get the next scheduled time from a list of time strings."""
    if not schedule_times:
        return None
    
    now = dt_util.now()
    current_time = now.strftime("%H:%M")
    
    # Sort times
    sorted_times = sorted(schedule_times)
    
    # Find next time today
    for time_str in sorted_times:
        if time_str > current_time:
            return time_str
    
    # If no time today, return first time tomorrow
    return sorted_times[0] if sorted_times else None


def calculate_body_condition_score(weight_kg: float, ideal_weight_kg: float) -> int:
    """Calculate body condition score (1-9 scale) based on weight."""
    try:
        weight = float(weight_kg)
        ideal = float(ideal_weight_kg)
        
        if ideal <= 0:
            return 5  # Default to ideal if no ideal weight
        
        # Calculate percentage difference
        diff_percent = ((weight - ideal) / ideal) * 100
        
        # Map to BCS scale
        if diff_percent < -20:
            return 1  # Emaciated
        elif diff_percent < -15:
            return 2  # Very thin
        elif diff_percent < -10:
            return 3  # Thin
        elif diff_percent < -5:
            return 4  # Underweight
        elif diff_percent < 5:
            return 5  # Ideal
        elif diff_percent < 10:
            return 6  # Overweight
        elif diff_percent < 20:
            return 7  # Heavy
        elif diff_percent < 30:
            return 8  # Obese
        else:
            return 9  # Morbidly obese
    except (ValueError, TypeError, ZeroDivisionError):
        return 5  # Default to ideal


def get_weather_emoji(weather: str) -> str:
    """Get emoji for weather condition."""
    weather_emojis = {
        "sunny": "☀️",
        "partly_cloudy": "⛅",
        "cloudy": "☁️",
        "rainy": "🌧️",
        "snowy": "❄️",
        "stormy": "⛈️",
        "windy": "💨",
        "foggy": "🌫️",
        "hot": "🌡️",
        "cold": "🥶",
    }
    
    return weather_emojis.get(weather.lower(), "🌤️")


def calculate_water_intake(weight_kg: float, activity_level: str = "Normal") -> float:
    """Calculate daily water intake in ml."""
    try:
        weight = float(weight_kg)
        
        # Base water need: 50-60ml per kg
        base_water = weight * 55
        
        # Activity adjustment
        activity_multipliers = {
            "Sehr niedrig": 0.8,
            "Niedrig": 0.9,
            "Normal": 1.0,
            "Hoch": 1.2,
            "Sehr hoch": 1.4,
        }
        
        multiplier = activity_multipliers.get(activity_level, 1.0)
        
        return round(base_water * multiplier)
    except (ValueError, TypeError):
        return 500.0  # Default


def is_valid_email(email: str | None) -> bool:
    """Validate email address."""
    if not isinstance(email, str):
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def is_valid_phone(phone: str | None) -> bool:
    """Validate phone number (basic international format)."""
    if not isinstance(phone, str):
        return False

    # Remove spaces and dashes
    phone = re.sub(r"[\s\-]", "", phone)

    # Check if it's a valid phone number pattern
    pattern = r"^[+]?[0-9]{8,15}$"
    return bool(re.match(pattern, phone))
