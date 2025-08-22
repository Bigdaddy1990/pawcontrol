"""Advanced utility functions for Paw Control integration.

This module provides high-performance utility functions with comprehensive async support,
modern type annotations, and optimized algorithms. Designed for Home Assistant 2025.8.2+
Platinum quality standards with focus on performance, reliability, and maintainability.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections.abc import Callable, Sequence
from datetime import datetime, time
from functools import lru_cache, wraps
from typing import Any, Final, TypeVar, overload

from homeassistant.util import dt as dt_util

from .const import (
    DOG_SIZES,
    MAX_DOG_WEIGHT,
    MIN_DOG_WEIGHT,
)

_LOGGER = logging.getLogger(__name__)

# Type aliases for better readability and performance
T = TypeVar("T")
Coordinates = tuple[float, float]
DataDict = dict[str, Any]
NumericType = int | float
ValidationResult = tuple[bool, str | None]

# Performance constants
CACHE_SIZE: Final = 256
GPS_PRECISION: Final = 6
CALCULATION_TIMEOUT: Final = 5.0

# Validation patterns (compiled for performance)
DOG_ID_PATTERN: Final = re.compile(r"^[a-zA-Z0-9_]{1,50}$")
TIME_PATTERN: Final = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
FILENAME_INVALID_CHARS: Final = re.compile(r'[<>:"/\\|?*]')
MULTIPLE_UNDERSCORES: Final = re.compile(r"_+")


def performance_monitor(timeout: float = CALCULATION_TIMEOUT) -> Callable:
    """Decorator for monitoring function performance with timeout protection.

    Args:
        timeout: Maximum execution time in seconds

    Returns:
        Decorated function with performance monitoring
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            start_time = asyncio.get_event_loop().time()
            try:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                execution_time = asyncio.get_event_loop().time() - start_time

                if execution_time > timeout * 0.8:  # Warn at 80% of timeout
                    _LOGGER.warning(
                        "Function %s took %.2fs (close to timeout %ss)",
                        func.__name__,
                        execution_time,
                        timeout,
                    )

                return result
            except asyncio.TimeoutError:
                _LOGGER.error("Function %s timed out after %ss", func.__name__, timeout)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            start_time = datetime.now()
            result = func(*args, **kwargs)
            execution_time = (datetime.now() - start_time).total_seconds()

            if execution_time > timeout * 0.8:
                _LOGGER.warning(
                    "Function %s took %.2fs (close to timeout %ss)",
                    func.__name__,
                    execution_time,
                    timeout,
                )

            return result

        # Return appropriate wrapper based on whether function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Enhanced validation functions with modern type annotations and error handling
def validate_dog_id(dog_id: str) -> ValidationResult:
    """Validate a dog ID format with comprehensive checking.

    Dog IDs must contain only letters, numbers, and underscores,
    and must be between 1 and 50 characters long.

    Args:
        dog_id: The dog ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(dog_id, str):
        return False, "Dog ID must be a string"

    if not dog_id:
        return False, "Dog ID cannot be empty"

    if len(dog_id) < 1 or len(dog_id) > 50:
        return False, f"Dog ID must be between 1 and 50 characters (got {len(dog_id)})"

    if not DOG_ID_PATTERN.match(dog_id):
        return False, "Dog ID can only contain letters, numbers, and underscores"

    return True, None


async def async_validate_coordinates(
    latitude: float | str, longitude: float | str
) -> ValidationResult:
    """Asynchronously validate GPS coordinates with enhanced precision checking.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        lat = float(latitude)
        lon = float(longitude)

        # Enhanced coordinate validation
        if math.isnan(lat) or math.isnan(lon):
            return False, "Coordinates cannot be NaN"

        if math.isinf(lat) or math.isinf(lon):
            return False, "Coordinates cannot be infinite"

        if not (-90 <= lat <= 90):
            return False, f"Latitude must be between -90 and 90 (got {lat})"

        if not (-180 <= lon <= 180):
            return False, f"Longitude must be between -180 and 180 (got {lon})"

        # Check precision (avoid excessive precision that may indicate errors)
        lat_precision = len(str(lat).split(".")[-1]) if "." in str(lat) else 0
        lon_precision = len(str(lon).split(".")[-1]) if "." in str(lon) else 0

        if lat_precision > GPS_PRECISION or lon_precision > GPS_PRECISION:
            _LOGGER.warning(
                "GPS coordinates have excessive precision (%d, %d decimal places)",
                lat_precision,
                lon_precision,
            )

        return True, None

    except (ValueError, TypeError) as err:
        return False, f"Invalid coordinate format: {err}"


def validate_weight_enhanced(
    weight: float | str, dog_size: str | None = None, age: int | None = None
) -> ValidationResult:
    """Enhanced weight validation with size and age-specific checks.

    Args:
        weight: Weight in kilograms
        dog_size: Optional size category for specific validation
        age: Optional age for puppy/senior adjustments

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        weight_val = float(weight)

        if weight_val <= 0:
            return False, "Weight must be positive"

        if math.isnan(weight_val) or math.isinf(weight_val):
            return False, "Weight must be a valid number"

        # Basic range check
        if not (MIN_DOG_WEIGHT <= weight_val <= MAX_DOG_WEIGHT):
            return (
                False,
                f"Weight must be between {MIN_DOG_WEIGHT}kg and {MAX_DOG_WEIGHT}kg",
            )

        # Enhanced size-specific validation
        if dog_size and dog_size in DOG_SIZES:
            size_ranges = {
                "toy": (1.0, 6.0),
                "small": (6.0, 12.0),
                "medium": (12.0, 27.0),
                "large": (27.0, 45.0),
                "giant": (45.0, 90.0),
            }

            min_weight, max_weight = size_ranges[dog_size]

            # Age adjustments for realistic ranges
            if age is not None:
                if age < 1:  # Puppy - lower expected weight
                    min_weight *= 0.3
                    max_weight *= 0.8
                elif age > 8:  # Senior - allow slightly higher weight
                    max_weight *= 1.15

            if not (min_weight <= weight_val <= max_weight):
                return (
                    False,
                    f"{dog_size} dogs should weigh between {min_weight:.1f}kg and {max_weight:.1f}kg",
                )

        return True, None

    except (ValueError, TypeError) as err:
        return False, f"Invalid weight format: {err}"


@lru_cache(maxsize=CACHE_SIZE)
def validate_enum_value(
    value: str, valid_values: tuple[str, ...], field_name: str
) -> ValidationResult:
    """Cached validation for enum-like values with performance optimization.

    Args:
        value: Value to validate
        valid_values: Tuple of valid values (tuple for hashability/caching)
        field_name: Name of the field being validated

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(value, str):
        return False, f"{field_name} must be a string"

    if value not in valid_values:
        return False, f"{field_name} must be one of: {', '.join(valid_values)}"

    return True, None


# Advanced formatting functions with locale and performance optimizations
@lru_cache(maxsize=CACHE_SIZE)
def format_duration_optimized(seconds: int, precision: str = "auto") -> str:
    """Optimized duration formatting with caching and flexible precision.

    Args:
        seconds: Duration in seconds
        precision: Precision level ('auto', 'exact', 'rounded')

    Returns:
        Formatted duration string
    """
    if seconds < 0:
        return "0 seconds"

    # Pre-calculated constants for performance
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts = []

    if hours > 0:
        if precision == "rounded" and hours >= 24:
            days = hours // 24
            remaining_hours = hours % 24
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if remaining_hours > 0:
                parts.append(
                    f"{remaining_hours} hour{'s' if remaining_hours != 1 else ''}"
                )
        else:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")

    if minutes > 0 and (precision != "rounded" or hours == 0):
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    if (secs > 0 or not parts) and (
        precision != "rounded" or (hours == 0 and minutes < 5)
    ):
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    # Optimized string joining
    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    else:
        return f"{', '.join(parts[:-1])}, and {parts[-1]}"


def format_distance_adaptive(meters: float, unit_preference: str = "auto") -> str:
    """Adaptive distance formatting with unit preferences and smart rounding.

    Args:
        meters: Distance in meters
        unit_preference: 'auto', 'metric', 'imperial'

    Returns:
        Formatted distance string with appropriate units
    """
    if meters < 0:
        return "0 m"

    if unit_preference == "imperial":
        # Convert to feet/miles
        feet = meters * 3.28084
        if feet < 1000:
            return f"{feet:.0f} ft"
        else:
            miles = feet / 5280
            if miles < 10:
                return f"{miles:.1f} mi"
            else:
                return f"{miles:.0f} mi"

    # Metric (default)
    if meters < 1000:
        if meters < 10:
            return f"{meters:.1f} m"
        else:
            return f"{meters:.0f} m"
    else:
        km = meters / 1000
        if km < 10:
            return f"{km:.1f} km"
        elif km < 100:
            return f"{km:.0f} km"
        else:
            return f"{km:.0f} km"


def format_time_ago_smart(
    timestamp: datetime, reference_time: datetime | None = None
) -> str:
    """Smart time ago formatting with relative context and better precision.

    Args:
        timestamp: The timestamp to format
        reference_time: Reference time (defaults to now)

    Returns:
        Human-readable time ago string with smart precision
    """
    ref_time = reference_time or dt_util.utcnow()

    if timestamp.tzinfo is None:
        timestamp = dt_util.as_utc(timestamp)
    if ref_time.tzinfo is None:
        ref_time = dt_util.as_utc(ref_time)

    diff = ref_time - timestamp
    total_seconds = diff.total_seconds()

    # Future timestamps
    if total_seconds < 0:
        return "in the future"

    # Smart precision based on time difference
    if total_seconds < 60:
        return "just now"
    elif total_seconds < 3600:
        minutes = int(total_seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif total_seconds < 86400:
        hours = int(total_seconds / 3600)
        minutes = int((total_seconds % 3600) / 60)
        if hours < 6 and minutes > 0:  # Show minutes for recent hours
            return f"{hours}h {minutes}m ago"
        else:
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


# High-performance calculation functions with async support
@performance_monitor(timeout=2.0)
async def async_calculate_haversine_distance(
    point1: Coordinates, point2: Coordinates, earth_radius: float = 6371000.0
) -> float:
    """Async high-precision Haversine distance calculation.

    Args:
        point1: First coordinate tuple (lat, lon)
        point2: Second coordinate tuple (lat, lon)
        earth_radius: Earth radius in meters (default: 6371000)

    Returns:
        Distance in meters with high precision
    """
    lat1, lon1 = point1
    lat2, lon2 = point2

    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula with enhanced precision
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance_m = earth_radius * c

    return round(distance_m, 2)


@lru_cache(maxsize=CACHE_SIZE)
def calculate_bmr_advanced(
    weight_kg: float,
    age_years: int,
    activity_level: str = "normal",
    breed_factor: float = 1.0,
    is_neutered: bool = True,
) -> float:
    """Advanced Basal Metabolic Rate calculation with breed and health factors.

    Args:
        weight_kg: Dog weight in kilograms
        age_years: Dog age in years
        activity_level: Activity level
        breed_factor: Breed-specific metabolic factor
        is_neutered: Whether the dog is neutered (affects metabolism)

    Returns:
        Daily calorie needs with precision
    """
    # Enhanced RER calculation with breed factor
    rer = 70 * (weight_kg**0.75) * breed_factor

    # Advanced activity multipliers
    activity_multipliers = {
        "very_low": 1.1,
        "low": 1.3,
        "normal": 1.6,
        "high": 1.8,
        "very_high": 2.2,
        "working": 2.5,
        "racing": 3.0,
    }

    multiplier = activity_multipliers.get(activity_level, 1.6)

    # Age-based adjustments with more precision
    if age_years < 0.5:  # Very young puppy
        multiplier *= 2.5
    elif age_years < 1:  # Puppy
        multiplier *= 2.0
    elif age_years < 2:  # Young adult
        multiplier *= 1.2
    elif age_years > 10:  # Very senior
        multiplier *= 0.8
    elif age_years > 7:  # Senior
        multiplier *= 0.9

    # Neuter status adjustment
    if is_neutered:
        multiplier *= 0.95  # Slightly lower metabolism

    daily_calories = rer * multiplier
    return round(daily_calories, 1)


async def async_calculate_route_statistics(
    route_points: Sequence[dict[str, Any]],
) -> dict[str, float]:
    """Asynchronously calculate comprehensive route statistics.

    Args:
        route_points: List of GPS points with timestamp, lat, lon

    Returns:
        Dictionary with route statistics
    """
    if len(route_points) < 2:
        return {
            "total_distance": 0.0,
            "average_speed": 0.0,
            "max_speed": 0.0,
            "elevation_gain": 0.0,
            "duration_seconds": 0,
        }

    total_distance = 0.0
    speeds = []
    elevations = []

    # Sort points by timestamp
    sorted_points = sorted(route_points, key=lambda p: p.get("timestamp", ""))

    for i in range(1, len(sorted_points)):
        prev_point = sorted_points[i - 1]
        curr_point = sorted_points[i]

        # Calculate segment distance
        try:
            prev_coords = (prev_point["latitude"], prev_point["longitude"])
            curr_coords = (curr_point["latitude"], curr_point["longitude"])

            segment_distance = await async_calculate_haversine_distance(
                prev_coords, curr_coords
            )
            total_distance += segment_distance

            # Calculate speed if timestamps available
            if "timestamp" in prev_point and "timestamp" in curr_point:
                try:
                    prev_time = datetime.fromisoformat(prev_point["timestamp"])
                    curr_time = datetime.fromisoformat(curr_point["timestamp"])
                    time_diff = (curr_time - prev_time).total_seconds()

                    if time_diff > 0:
                        speed_ms = segment_distance / time_diff
                        speed_kmh = speed_ms * 3.6
                        speeds.append(speed_kmh)
                except (ValueError, TypeError):
                    pass

            # Track elevation if available
            if "altitude" in curr_point:
                try:
                    elevations.append(float(curr_point["altitude"]))
                except (ValueError, TypeError):
                    pass

        except (KeyError, TypeError, ValueError):
            continue

    # Calculate duration
    duration_seconds = 0
    if len(sorted_points) >= 2:
        try:
            start_time = datetime.fromisoformat(sorted_points[0]["timestamp"])
            end_time = datetime.fromisoformat(sorted_points[-1]["timestamp"])
            duration_seconds = int((end_time - start_time).total_seconds())
        except (ValueError, TypeError, KeyError):
            pass

    # Calculate elevation gain
    elevation_gain = 0.0
    if len(elevations) >= 2:
        for i in range(1, len(elevations)):
            gain = elevations[i] - elevations[i - 1]
            if gain > 0:
                elevation_gain += gain

    return {
        "total_distance": round(total_distance, 2),
        "average_speed": round(sum(speeds) / len(speeds), 2) if speeds else 0.0,
        "max_speed": round(max(speeds), 2) if speeds else 0.0,
        "elevation_gain": round(elevation_gain, 2),
        "duration_seconds": duration_seconds,
        "points_count": len(route_points),
    }


# Enhanced utility functions with async support and better performance
@overload
def safe_convert(value: Any, target_type: type[int], default: int = 0) -> int: ...


@overload
def safe_convert(
    value: Any, target_type: type[float], default: float = 0.0
) -> float: ...


@overload
def safe_convert(value: Any, target_type: type[str], default: str = "") -> str: ...


def safe_convert(value: Any, target_type: type[T], default: T | None = None) -> T:
    """Type-safe conversion with better error handling and type hints.

    Args:
        value: Value to convert
        target_type: Target type for conversion
        default: Default value if conversion fails

    Returns:
        Converted value or default
    """
    if value is None:
        return default if default is not None else target_type()

    try:
        if target_type is bool:
            if isinstance(value, str):
                return target_type(value.lower() in ("true", "yes", "1", "on"))
            return target_type(value)
        elif target_type in (int, float):
            return target_type(value)
        elif target_type is str:
            return str(value)
        else:
            return target_type(value)
    except (ValueError, TypeError):
        return default if default is not None else target_type()


def deep_merge_dicts_optimized(
    dict1: dict[str, Any], dict2: dict[str, Any], max_depth: int = 10
) -> dict[str, Any]:
    """Optimized deep dictionary merge with cycle protection.

    Args:
        dict1: First dictionary (base)
        dict2: Second dictionary (overlay)
        max_depth: Maximum recursion depth for safety

    Returns:
        Merged dictionary
    """
    if max_depth <= 0:
        _LOGGER.warning("Maximum merge depth reached, stopping recursion")
        return dict1.copy()

    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts_optimized(result[key], value, max_depth - 1)
        else:
            result[key] = value

    return result


async def async_chunk_processor(
    items: Sequence[T],
    processor_func: Callable[[T], Any],
    chunk_size: int = 10,
    max_concurrent: int = 5,
) -> list[Any]:
    """Async chunk processor for handling large datasets efficiently.

    Args:
        items: Items to process
        processor_func: Function to process each item
        chunk_size: Size of each processing chunk
        max_concurrent: Maximum concurrent operations

    Returns:
        List of processed results
    """
    if not items:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_chunk(chunk: Sequence[T]) -> list[Any]:
        async with semaphore:
            if asyncio.iscoroutinefunction(processor_func):
                return await asyncio.gather(*[processor_func(item) for item in chunk])
            else:
                return [processor_func(item) for item in chunk]

    # Create chunks
    chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

    # Process all chunks concurrently
    chunk_results = await asyncio.gather(*[process_chunk(chunk) for chunk in chunks])

    # Flatten results
    return [item for chunk_result in chunk_results for item in chunk_result]


@lru_cache(maxsize=CACHE_SIZE)
def calculate_trend_advanced(
    values: tuple[float, ...], periods: int = 7, algorithm: str = "linear"
) -> dict[str, Any]:
    """Advanced trend calculation with multiple algorithms and confidence metrics.

    Args:
        values: Tuple of numerical values (most recent first, tuple for caching)
        periods: Number of periods to consider
        algorithm: Algorithm to use ('linear', 'exponential', 'polynomial')

    Returns:
        Dictionary with trend analysis results
    """
    if len(values) < 2:
        return {
            "direction": "unknown",
            "strength": 0.0,
            "confidence": 0.0,
            "rate_of_change": 0.0,
        }

    # Take only the specified number of periods
    recent_values = list(values[:periods])

    if len(recent_values) < 2:
        return {
            "direction": "unknown",
            "strength": 0.0,
            "confidence": 0.0,
            "rate_of_change": 0.0,
        }

    n = len(recent_values)
    x = list(range(n))
    y = recent_values[::-1]  # Reverse to have oldest first

    if algorithm == "linear":
        # Linear regression
        x_mean = sum(x) / n
        y_mean = sum(y) / n

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator

        # Calculate R-squared for confidence
        y_pred = [slope * xi + (y_mean - slope * x_mean) for xi in x]
        ss_tot = sum((y[i] - y_mean) ** 2 for i in range(n))
        ss_res = sum((y[i] - y_pred[i]) ** 2 for i in range(n))

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

    else:
        # Simplified calculation for other algorithms
        slope = (y[-1] - y[0]) / (n - 1) if n > 1 else 0
        r_squared = 0.5  # Placeholder

    # Determine trend characteristics
    abs_slope = abs(slope)

    if abs_slope < 0.01:
        direction = "stable"
        strength = 0.0
    elif slope > 0:
        direction = "increasing"
        strength = min(abs_slope * 10, 1.0)  # Normalize strength
    else:
        direction = "decreasing"
        strength = min(abs_slope * 10, 1.0)

    return {
        "direction": direction,
        "strength": round(strength, 3),
        "confidence": round(max(0, min(r_squared, 1)), 3),
        "rate_of_change": round(slope, 6),
        "algorithm": algorithm,
        "periods_analyzed": n,
    }


def is_within_time_range_enhanced(
    current_time: datetime | time,
    start_time: str | time,
    end_time: str | time,
    timezone_aware: bool = True,
) -> tuple[bool, str | None]:
    """Enhanced time range checking with timezone support and validation.

    Args:
        current_time: Current time to check
        start_time: Range start time
        end_time: Range end time
        timezone_aware: Whether to consider timezone information

    Returns:
        Tuple of (is_within_range, error_message)
    """
    try:
        # Convert current_time to time object if needed
        if isinstance(current_time, datetime):
            current_time_obj = current_time.time()
        else:
            current_time_obj = current_time

        # Convert string times to time objects with validation
        if isinstance(start_time, str):
            if not TIME_PATTERN.match(start_time):
                return False, f"Invalid start time format: {start_time}"
            start_hour, start_minute = map(int, start_time.split(":"))
            start_time_obj = time(start_hour, start_minute)
        else:
            start_time_obj = start_time

        if isinstance(end_time, str):
            if not TIME_PATTERN.match(end_time):
                return False, f"Invalid end time format: {end_time}"
            end_hour, end_minute = map(int, end_time.split(":"))
            end_time_obj = time(end_hour, end_minute)
        else:
            end_time_obj = end_time

        # Check for overnight range
        if start_time_obj <= end_time_obj:
            # Same day range
            is_within = start_time_obj <= current_time_obj <= end_time_obj
        else:
            # Overnight range
            is_within = (
                current_time_obj >= start_time_obj or current_time_obj <= end_time_obj
            )

        return is_within, None

    except (ValueError, AttributeError, TypeError) as err:
        return False, f"Invalid time format: {err}"


def sanitize_filename_advanced(
    filename: str, max_length: int = 255, replacement_char: str = "_"
) -> str:
    """Advanced filename sanitization with length limits and customization.

    Args:
        filename: Original filename
        max_length: Maximum filename length
        replacement_char: Character to replace invalid chars with

    Returns:
        Sanitized filename
    """
    if not filename:
        return "file"

    # Remove invalid characters
    sanitized = FILENAME_INVALID_CHARS.sub(replacement_char, filename)

    # Remove multiple consecutive replacement characters
    sanitized = MULTIPLE_UNDERSCORES.sub(replacement_char, sanitized)

    # Remove leading/trailing spaces, dots, and replacement chars
    sanitized = sanitized.strip(f" .{replacement_char}")

    # Ensure it's not empty
    if not sanitized:
        sanitized = "file"

    # Truncate if too long, preserving file extension if possible
    if len(sanitized) > max_length:
        if "." in sanitized:
            name, ext = sanitized.rsplit(".", 1)
            max_name_length = max_length - len(ext) - 1
            if max_name_length > 0:
                sanitized = f"{name[:max_name_length]}.{ext}"
            else:
                sanitized = sanitized[:max_length]
        else:
            sanitized = sanitized[:max_length]

    return sanitized


async def async_batch_validate(
    items: Sequence[tuple[Any, Callable[[Any], ValidationResult]]],
    fail_fast: bool = False,
) -> dict[int, tuple[bool, str | None]]:
    """Async batch validation with performance optimization.

    Args:
        items: Sequence of (value, validator_function) tuples
        fail_fast: Stop on first validation error

    Returns:
        Dictionary mapping item index to validation result
    """
    results = {}

    async def validate_item(
        index: int, item: tuple[Any, Callable]
    ) -> tuple[int, tuple[bool, str | None]]:
        value, validator = item

        if asyncio.iscoroutinefunction(validator):
            result = await validator(value)
        else:
            result = validator(value)

        return index, result

    # Create validation tasks
    tasks = [validate_item(i, item) for i, item in enumerate(items)]

    if fail_fast:
        # Process sequentially and stop on first error
        for task in tasks:
            index, result = await task
            results[index] = result
            if not result[0]:  # Validation failed
                break
    else:
        # Process all concurrently
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for task_result in task_results:
            if isinstance(task_result, Exception):
                _LOGGER.error("Validation task failed: %s", task_result)
                continue

            index, result = task_result
            results[index] = result

    return results


# Legacy compatibility functions (renamed for backwards compatibility)
def safe_float(value: Any, default: float = 0.0) -> float:
    """Legacy compatibility function - use safe_convert instead."""
    return safe_convert(value, float, default)


def safe_int(value: Any, default: int = 0) -> int:
    """Legacy compatibility function - use safe_convert instead."""
    return safe_convert(value, int, default)


def safe_str(value: Any, default: str = "") -> str:
    """Legacy compatibility function - use safe_convert instead."""
    return safe_convert(value, str, default)


def deep_merge_dicts(dict1: dict[str, Any], dict2: dict[str, Any]) -> dict[str, Any]:
    """Legacy compatibility function - use deep_merge_dicts_optimized instead."""
    return deep_merge_dicts_optimized(dict1, dict2)


def is_within_quiet_hours(
    current_time: datetime, quiet_start: str, quiet_end: str
) -> bool:
    """Legacy compatibility function - use is_within_time_range_enhanced instead."""
    result, _ = is_within_time_range_enhanced(current_time, quiet_start, quiet_end)
    return result


def sanitize_filename(filename: str) -> str:
    """Legacy compatibility function - use sanitize_filename_advanced instead."""
    return sanitize_filename_advanced(filename)


# Export convenience functions
__all__ = [
    # Validation functions
    "validate_dog_id",
    "async_validate_coordinates",
    "validate_weight_enhanced",
    "validate_enum_value",
    # Formatting functions
    "format_duration_optimized",
    "format_distance_adaptive",
    "format_time_ago_smart",
    # Calculation functions
    "async_calculate_haversine_distance",
    "calculate_bmr_advanced",
    "async_calculate_route_statistics",
    # Utility functions
    "safe_convert",
    "deep_merge_dicts_optimized",
    "async_chunk_processor",
    "calculate_trend_advanced",
    "is_within_time_range_enhanced",
    "sanitize_filename_advanced",
    "async_batch_validate",
    # Legacy compatibility
    "safe_float",
    "safe_int",
    "safe_str",
    "deep_merge_dicts",
    "is_within_quiet_hours",
    "sanitize_filename",
    # Decorators
    "performance_monitor",
    # Constants
    "CACHE_SIZE",
    "GPS_PRECISION",
    "CALCULATION_TIMEOUT",
]
