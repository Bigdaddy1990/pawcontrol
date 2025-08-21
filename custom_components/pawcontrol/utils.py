"""Utility functions for Paw Control integration.

This module provides common utility functions used throughout the Paw Control
integration including data validation, formatting, calculations, and helper
methods for various operations.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance

from .const import (
    DOG_SIZES,
    FOOD_TYPES,
    HEALTH_STATUS_OPTIONS,
    MAX_DOG_AGE,
    MAX_DOG_WEIGHT,
    MIN_DOG_AGE,
    MIN_DOG_WEIGHT,
    MOOD_OPTIONS,
)
from .exceptions import (
    InvalidCoordinatesError,
    InvalidWeightError,
    ValidationError,
)

_LOGGER = logging.getLogger(__name__)

# Type aliases
Coordinates = Tuple[float, float]
DataDict = Dict[str, Any]


def validate_dog_id(dog_id: str) -> bool:
    """Validate a dog ID format.
    
    Dog IDs must contain only letters, numbers, and underscores,
    and must be between 1 and 50 characters long.
    
    Args:
        dog_id: The dog ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not dog_id or not isinstance(dog_id, str):
        return False
    
    # Check length
    if not (1 <= len(dog_id) <= 50):
        return False
    
    # Check format: only letters, numbers, and underscores
    return bool(re.match(r'^[a-zA-Z0-9_]+$', dog_id))


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """Validate GPS coordinates.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        
    Returns:
        True if coordinates are valid
        
    Raises:
        InvalidCoordinatesError: If coordinates are invalid
    """
    try:
        lat = float(latitude)
        lon = float(longitude)
        
        if not (-90 <= lat <= 90):
            raise InvalidCoordinatesError(lat, lon)
        
        if not (-180 <= lon <= 180):
            raise InvalidCoordinatesError(lat, lon)
        
        return True
    except (ValueError, TypeError) as err:
        raise InvalidCoordinatesError(latitude, longitude) from err


def validate_weight(weight: float, dog_size: Optional[str] = None) -> bool:
    """Validate a dog's weight.
    
    Args:
        weight: Weight in kilograms
        dog_size: Optional size category for more specific validation
        
    Returns:
        True if weight is valid
        
    Raises:
        InvalidWeightError: If weight is invalid
    """
    try:
        weight_val = float(weight)
        
        if weight_val <= 0:
            raise InvalidWeightError(weight_val, MIN_DOG_WEIGHT, MAX_DOG_WEIGHT)
        
        # Basic range check
        if not (MIN_DOG_WEIGHT <= weight_val <= MAX_DOG_WEIGHT):
            raise InvalidWeightError(weight_val, MIN_DOG_WEIGHT, MAX_DOG_WEIGHT)
        
        # Size-specific validation if size is provided
        if dog_size:
            size_ranges = {
                "toy": (1, 6),
                "small": (6, 12),
                "medium": (12, 27),
                "large": (27, 45),
                "giant": (45, 90),
            }
            
            if dog_size in size_ranges:
                min_weight, max_weight = size_ranges[dog_size]
                if not (min_weight <= weight_val <= max_weight):
                    raise InvalidWeightError(weight_val, min_weight, max_weight)
        
        return True
    except (ValueError, TypeError) as err:
        raise InvalidWeightError(weight) from err


def validate_age(age: int) -> bool:
    """Validate a dog's age.
    
    Args:
        age: Age in years
        
    Returns:
        True if age is valid
        
    Raises:
        ValidationError: If age is invalid
    """
    try:
        age_val = int(age)
        
        if not (MIN_DOG_AGE <= age_val <= MAX_DOG_AGE):
            raise ValidationError(
                "age",
                str(age_val),
                f"must be between {MIN_DOG_AGE} and {MAX_DOG_AGE} years"
            )
        
        return True
    except (ValueError, TypeError) as err:
        raise ValidationError("age", str(age), "must be a valid integer") from err


def validate_dog_size(size: str) -> bool:
    """Validate a dog size category.
    
    Args:
        size: Size category
        
    Returns:
        True if size is valid
        
    Raises:
        ValidationError: If size is invalid
    """
    if size not in DOG_SIZES:
        raise ValidationError(
            "size",
            size,
            f"must be one of: {', '.join(DOG_SIZES)}"
        )
    
    return True


def validate_food_type(food_type: str) -> bool:
    """Validate a food type.
    
    Args:
        food_type: Food type to validate
        
    Returns:
        True if food type is valid
        
    Raises:
        ValidationError: If food type is invalid
    """
    if food_type not in FOOD_TYPES:
        raise ValidationError(
            "food_type",
            food_type,
            f"must be one of: {', '.join(FOOD_TYPES)}"
        )
    
    return True


def validate_health_status(status: str) -> bool:
    """Validate a health status.
    
    Args:
        status: Health status to validate
        
    Returns:
        True if status is valid
        
    Raises:
        ValidationError: If status is invalid
    """
    if status not in HEALTH_STATUS_OPTIONS:
        raise ValidationError(
            "health_status",
            status,
            f"must be one of: {', '.join(HEALTH_STATUS_OPTIONS)}"
        )
    
    return True


def validate_mood(mood: str) -> bool:
    """Validate a mood option.
    
    Args:
        mood: Mood to validate
        
    Returns:
        True if mood is valid
        
    Raises:
        ValidationError: If mood is invalid
    """
    if mood not in MOOD_OPTIONS:
        raise ValidationError(
            "mood",
            mood,
            f"must be one of: {', '.join(MOOD_OPTIONS)}"
        )
    
    return True


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string.
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted duration string
    """
    if seconds < 0:
        return "0 seconds"
    
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0 or not parts:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    else:
        return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def format_distance(meters: float) -> str:
    """Format distance in meters to human-readable string.
    
    Args:
        meters: Distance in meters
        
    Returns:
        Formatted distance string
    """
    if meters < 0:
        return "0 m"
    
    if meters < 1000:
        return f"{meters:.0f} m"
    else:
        km = meters / 1000
        if km < 10:
            return f"{km:.1f} km"
        else:
            return f"{km:.0f} km"


def format_weight(weight: float, unit: str = "kg") -> str:
    """Format weight with appropriate precision.
    
    Args:
        weight: Weight value
        unit: Unit of measurement
        
    Returns:
        Formatted weight string
    """
    if weight < 0:
        return f"0 {unit}"
    
    if weight < 10:
        return f"{weight:.1f} {unit}"
    else:
        return f"{weight:.0f} {unit}"


def format_time_ago(timestamp: datetime) -> str:
    """Format a timestamp as time ago string.
    
    Args:
        timestamp: The timestamp to format
        
    Returns:
        Human-readable time ago string
    """
    now = dt_util.utcnow()
    if timestamp.tzinfo is None:
        timestamp = dt_util.as_utc(timestamp)
    
    diff = now - timestamp
    
    if diff.total_seconds() < 60:
        return "just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif diff.days < 7:
        return f"{diff.days} day{'s' if diff.days != 1 else ''} ago"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif diff.days < 365:
        months = diff.days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = diff.days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"


def calculate_distance_between_points(
    point1: Coordinates, 
    point2: Coordinates
) -> float:
    """Calculate distance between two GPS coordinates.
    
    Args:
        point1: First coordinate tuple (lat, lon)
        point2: Second coordinate tuple (lat, lon)
        
    Returns:
        Distance in meters
    """
    lat1, lon1 = point1
    lat2, lon2 = point2
    
    # Use Home Assistant's distance calculation (returns km)
    dist_km = distance(lat1, lon1, lat2, lon2)
    return dist_km * 1000  # Convert to meters


def calculate_average_speed(distance_meters: float, duration_seconds: int) -> float:
    """Calculate average speed from distance and duration.
    
    Args:
        distance_meters: Distance traveled in meters
        duration_seconds: Duration in seconds
        
    Returns:
        Average speed in km/h
    """
    if duration_seconds <= 0:
        return 0.0
    
    # Convert to km/h
    speed_ms = distance_meters / duration_seconds
    speed_kmh = speed_ms * 3.6
    
    return round(speed_kmh, 2)


def calculate_calorie_needs(weight: float, age: int, activity_level: str = "normal") -> float:
    """Calculate daily calorie needs for a dog.
    
    Args:
        weight: Dog weight in kg
        age: Dog age in years
        activity_level: Activity level (low, normal, high)
        
    Returns:
        Daily calorie needs
    """
    # Base metabolic rate calculation
    # RER (Resting Energy Requirement) = 70 * (weight in kg)^0.75
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
    
    # Age adjustments
    if age < 1:  # Puppy
        multiplier *= 2.0
    elif age > 7:  # Senior
        multiplier *= 0.9
    
    daily_calories = rer * multiplier
    return round(daily_calories)


def calculate_ideal_weight_range(size: str, age: int) -> Tuple[float, float]:
    """Calculate ideal weight range for a dog based on size and age.
    
    Args:
        size: Dog size category
        age: Dog age in years
        
    Returns:
        Tuple of (min_weight, max_weight) in kg
    """
    # Base weight ranges by size
    base_ranges = {
        "toy": (2, 5),
        "small": (7, 11),
        "medium": (15, 25),
        "large": (30, 40),
        "giant": (50, 80),
    }
    
    if size not in base_ranges:
        return (10.0, 30.0)  # Default range
    
    min_weight, max_weight = base_ranges[size]
    
    # Age adjustments
    if age < 1:  # Puppy - lower range
        min_weight *= 0.7
        max_weight *= 0.8
    elif age > 7:  # Senior - slightly higher acceptable range
        max_weight *= 1.1
    
    return (round(min_weight, 1), round(max_weight, 1))


def calculate_walk_difficulty(distance: float, duration: int, elevation_gain: float = 0) -> str:
    """Calculate walk difficulty level.
    
    Args:
        distance: Walk distance in meters
        duration: Walk duration in seconds
        elevation_gain: Elevation gain in meters
        
    Returns:
        Difficulty level string
    """
    if duration <= 0:
        return "unknown"
    
    # Calculate metrics
    speed_kmh = calculate_average_speed(distance, duration)
    distance_km = distance / 1000
    duration_hours = duration / 3600
    
    # Base difficulty from distance and time
    difficulty_score = 0
    
    # Distance component
    if distance_km < 1:
        difficulty_score += 1
    elif distance_km < 3:
        difficulty_score += 2
    elif distance_km < 6:
        difficulty_score += 3
    else:
        difficulty_score += 4
    
    # Duration component
    if duration_hours < 0.5:
        difficulty_score += 1
    elif duration_hours < 1.5:
        difficulty_score += 2
    elif duration_hours < 3:
        difficulty_score += 3
    else:
        difficulty_score += 4
    
    # Speed component
    if speed_kmh > 8:  # Fast walking/jogging
        difficulty_score += 2
    elif speed_kmh > 5:  # Brisk walking
        difficulty_score += 1
    
    # Elevation component
    if elevation_gain > 100:
        difficulty_score += 2
    elif elevation_gain > 50:
        difficulty_score += 1
    
    # Classify difficulty
    if difficulty_score <= 3:
        return "easy"
    elif difficulty_score <= 6:
        return "moderate"
    elif difficulty_score <= 9:
        return "challenging"
    else:
        return "difficult"


def parse_meal_times(meal_times_str: str) -> List[str]:
    """Parse meal times string into list of time strings.
    
    Args:
        meal_times_str: Comma-separated meal times (HH:MM format)
        
    Returns:
        List of parsed time strings
        
    Raises:
        ValidationError: If time format is invalid
    """
    if not meal_times_str:
        return []
    
    times = []
    for time_str in meal_times_str.split(","):
        time_str = time_str.strip()
        
        # Validate time format (HH:MM)
        if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
            raise ValidationError(
                "meal_times",
                time_str,
                "must be in HH:MM format"
            )
        
        times.append(time_str)
    
    return sorted(times)


def generate_dog_id(dog_name: str) -> str:
    """Generate a unique dog ID from the dog name.
    
    Args:
        dog_name: Dog's name
        
    Returns:
        Generated dog ID
    """
    # Convert to lowercase and replace spaces/special chars with underscores
    dog_id = re.sub(r'[^a-zA-Z0-9]', '_', dog_name.lower())
    
    # Remove multiple consecutive underscores
    dog_id = re.sub(r'_+', '_', dog_id)
    
    # Remove leading/trailing underscores
    dog_id = dog_id.strip('_')
    
    # Ensure minimum length
    if len(dog_id) < 3:
        dog_id = f"dog_{dog_id}"
    
    # Truncate if too long
    if len(dog_id) > 50:
        dog_id = dog_id[:50].rstrip('_')
    
    return dog_id


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to float.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert a value to int.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Integer value or default
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """Safely convert a value to string.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        String value or default
    """
    try:
        if value is None:
            return default
        return str(value)
    except (ValueError, TypeError):
        return default


def deep_merge_dicts(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.
    
    Args:
        dict1: First dictionary
        dict2: Second dictionary (takes precedence)
        
    Returns:
        Merged dictionary
    """
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split a list into chunks of specified size.
    
    Args:
        lst: List to chunk
        chunk_size: Size of each chunk
        
    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def calculate_trend(values: List[float], periods: int = 7) -> str:
    """Calculate trend direction from a list of values.
    
    Args:
        values: List of numerical values (most recent first)
        periods: Number of periods to consider
        
    Returns:
        Trend direction: "increasing", "decreasing", "stable", or "unknown"
    """
    if len(values) < 2:
        return "unknown"
    
    # Take only the specified number of periods
    recent_values = values[:periods]
    
    if len(recent_values) < 2:
        return "unknown"
    
    # Calculate simple linear trend
    n = len(recent_values)
    x = list(range(n))
    y = recent_values[::-1]  # Reverse to have oldest first
    
    # Calculate slope using least squares
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi * xi for xi in x)
    
    if n * sum_x2 - sum_x * sum_x == 0:
        return "stable"
    
    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
    
    # Determine trend based on slope
    if abs(slope) < 0.01:  # Very small slope threshold
        return "stable"
    elif slope > 0:
        return "increasing"
    else:
        return "decreasing"


def is_within_quiet_hours(
    current_time: datetime,
    quiet_start: str,
    quiet_end: str
) -> bool:
    """Check if current time is within quiet hours.
    
    Args:
        current_time: Current datetime
        quiet_start: Quiet hours start time (HH:MM format)
        quiet_end: Quiet hours end time (HH:MM format)
        
    Returns:
        True if within quiet hours
    """
    try:
        start_hour, start_minute = map(int, quiet_start.split(':'))
        end_hour, end_minute = map(int, quiet_end.split(':'))
        
        current_minutes = current_time.hour * 60 + current_time.minute
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute
        
        if start_minutes <= end_minutes:
            # Same day range
            return start_minutes <= current_minutes <= end_minutes
        else:
            # Overnight range
            return current_minutes >= start_minutes or current_minutes <= end_minutes
    
    except (ValueError, AttributeError):
        return False


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename
    """
    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    
    # Ensure it's not empty
    if not sanitized:
        sanitized = "file"
    
    return sanitized


def get_size_category_from_weight(weight: float) -> str:
    """Determine size category from weight.
    
    Args:
        weight: Dog weight in kg
        
    Returns:
        Size category
    """
    if weight <= 6:
        return "toy"
    elif weight <= 12:
        return "small"
    elif weight <= 27:
        return "medium"
    elif weight <= 45:
        return "large"
    else:
        return "giant"


def format_percentage(value: float, precision: int = 1) -> str:
    """Format a value as percentage.
    
    Args:
        value: Value to format (0-100)
        precision: Decimal places
        
    Returns:
        Formatted percentage string
    """
    return f"{value:.{precision}f}%"


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp a value between min and max bounds.
    
    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        
    Returns:
        Clamped value
    """
    return max(min_value, min(value, max_value))
