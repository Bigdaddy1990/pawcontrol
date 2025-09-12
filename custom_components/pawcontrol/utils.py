"""Optimized utility functions for Paw Control integration.

OPTIMIZED for HA 2025.9.1+ with enhanced performance patterns:
- Reduced memory allocation
- Faster async operations
- Streamlined imports
- Better type safety
- Enhanced error handling

Quality Scale: Platinum
Home Assistant: 2025.9.1+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import re
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, time
from functools import lru_cache, wraps
from typing import Any, TypeVar, overload

from homeassistant.util import dt as dt_util

from .const import DOG_SIZE_WEIGHT_RANGES, DOMAIN, MAX_DOG_WEIGHT, MIN_DOG_WEIGHT

_LOGGER = logging.getLogger(__name__)

# OPTIMIZED: Type aliases for better performance
T = TypeVar("T")
Coordinates = tuple[float, float]
ValidationResult = tuple[bool, str | None]
NumericType = int | float

# OPTIMIZED: Performance constants
CACHE_SIZE = 128  # Reduced from 256 for better memory efficiency
GPS_PRECISION = 6
CALCULATION_TIMEOUT = 3.0  # Reduced from 5.0 for faster responses

# OPTIMIZED: Pre-compiled patterns for better performance
DOG_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,50}$")
TIME_PATTERN = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
FILENAME_INVALID_CHARS = re.compile(r'[<>:"/\\|?*]')
MULTIPLE_UNDERSCORES = re.compile(r"_+")


def _format_hours_minutes(total_seconds: float) -> str:
    """Format hours with optional minutes for time-ago strings."""

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if minutes:
        return f"{hours}h {minutes}m ago"
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


# Thresholds for time-ago formatting
_TIME_AGO_THRESHOLDS: list[tuple[float, Callable[[float], str]]] = [
    (60, lambda s: "just now"),
    (
        3600,
        lambda s: f"{int(s / 60)} minute{'s' if int(s / 60) != 1 else ''} ago",
    ),
    (86400, _format_hours_minutes),
    (
        604800,
        lambda s: f"{int(s / 86400)} day{'s' if int(s / 86400) != 1 else ''} ago",
    ),
    (
        2592000,
        lambda s: f"{int(s / 604800)} week{'s' if int(s / 604800) != 1 else ''} ago",
    ),
    (
        31536000,
        lambda s: f"{int(s / 2592000)} month{'s' if int(s / 2592000) != 1 else ''} ago",
    ),
]


def performance_monitor(timeout: float = CALCULATION_TIMEOUT) -> Callable:
    """OPTIMIZED: Performance monitoring decorator with reduced overhead.

    Args:
        timeout: Maximum execution time in seconds

    Returns:
        Decorated function with performance monitoring
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except TimeoutError:
                _LOGGER.error("Function %s timed out after %ss",
                              func.__name__, timeout)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            return func(*args, **kwargs)

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


# OPTIMIZED: Validation functions with enhanced performance
def validate_dog_id(dog_id: str) -> ValidationResult:
    """OPTIMIZED: Fast dog ID validation with pattern matching.

    Args:
        dog_id: The dog ID to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(dog_id, str):
        return False, "Dog ID must be a string"

    if not dog_id:
        return False, "Dog ID cannot be empty"

    if not (1 <= len(dog_id) <= 50):
        return False, "Dog ID must be between 1 and 50 characters"

    if not DOG_ID_PATTERN.match(dog_id):
        return False, "Dog ID can only contain letters, numbers, and underscores"

    return True, None


async def async_validate_coordinates(
    latitude: NumericType, longitude: NumericType
) -> ValidationResult:
    """OPTIMIZED: Fast coordinate validation with range checks.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        lat, lon = float(latitude), float(longitude)

        if math.isnan(lat) or math.isnan(lon):
            return False, "Coordinates cannot be NaN"

        if math.isinf(lat) or math.isinf(lon):
            return False, "Coordinates cannot be infinite"

        if not (-90 <= lat <= 90):
            return False, "Latitude must be between -90 and 90"

        if not (-180 <= lon <= 180):
            return False, "Longitude must be between -180 and 180"

        return True, None

    except (ValueError, TypeError) as err:
        return False, f"Invalid coordinate format: {err}"


def validate_weight_enhanced(
    weight: NumericType, dog_size: str | None = None, age: int | None = None
) -> ValidationResult:
    """OPTIMIZED: Enhanced weight validation with size/age checks."""

    try:
        weight_val = float(weight)
    except (ValueError, TypeError) as err:
        return False, f"Invalid weight format: {err}"

    if not math.isfinite(weight_val):
        return False, "Weight must be a valid number"

    if weight_val <= 0:
        return False, "Weight must be positive"

    if not (MIN_DOG_WEIGHT <= weight_val <= MAX_DOG_WEIGHT):
        return False, f"Weight must be between {MIN_DOG_WEIGHT}-{MAX_DOG_WEIGHT}kg"

    if dog_size and dog_size in DOG_SIZE_WEIGHT_RANGES:
        return _validate_weight_for_size(weight_val, dog_size, age)

    return True, None


def _validate_weight_for_size(
    weight_val: float, dog_size: str, age: int | None
) -> ValidationResult:
    """Validate weight against size-specific ranges."""

    min_weight, max_weight = DOG_SIZE_WEIGHT_RANGES[dog_size]
    adjusted_min = min_weight
    adjusted_max = max_weight

    if age is not None:
        if age < 1:  # Puppy
            adjusted_min = min_weight * 0.3
            adjusted_max = max_weight * 0.8
        elif age > 8:  # Senior
            adjusted_max = max_weight * 1.15

    if adjusted_min <= weight_val <= adjusted_max:
        return True, None

    return (
        False,
        f"{dog_size} dogs should weigh between {adjusted_min:.1f} and {adjusted_max:.1f}kg",
    )


@lru_cache(maxsize=CACHE_SIZE)
def validate_enum_value(
    value: str, valid_values: tuple[str, ...], field_name: str
) -> ValidationResult:
    """OPTIMIZED: Cached enum validation for frequent lookups.

    Args:
        value: Value to validate
        valid_values: Tuple of valid values
        field_name: Field name for error messages

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(value, str):
        return False, f"{field_name} must be a string"

    if value not in valid_values:
        return False, f"{field_name} must be one of: {', '.join(valid_values)}"

    return True, None


async def async_batch_validate(
    items: Iterable[
        tuple[
            Any,
            Callable[[Any], ValidationResult]
            | Callable[[Any], Awaitable[ValidationResult]],
        ]
    ],
    *,
    fail_fast: bool = False,
) -> list[ValidationResult]:
    """Validate a batch of items, optionally stopping on first failure."""

    results: list[ValidationResult] = []
    for value, validator in items:
        result = validator(value)
        if inspect.isawaitable(result):
            result = await result
        results.append(result)
        if fail_fast and not result[0]:
            break
    return results


# OPTIMIZED: Formatting functions with better performance
@lru_cache(maxsize=CACHE_SIZE)
def format_duration_optimized(seconds: int, precision: str = "auto") -> str:
    """OPTIMIZED: Fast duration formatting with intelligent precision."""

    if seconds <= 0:
        return "0 seconds"

    if precision == "rounded":
        return _format_duration_rounded(seconds)

    return _format_duration_precise(seconds)


def _format_duration_rounded(seconds: int) -> str:
    """Format duration using rounded precision."""

    units = [
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    for name, unit_seconds in units:
        value = seconds // unit_seconds
        if value:
            unit_name = name if value == 1 else f"{name}s"
            return f"{value} {unit_name}"
    return "0 seconds"


def _format_duration_precise(seconds: int) -> str:
    """Format duration with full precision."""

    units = [
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
        ("second", 1),
    ]
    parts: list[str] = []
    remaining = seconds
    for name, unit_seconds in units:
        value, remaining = divmod(remaining, unit_seconds)
        if value:
            unit_name = name if value == 1 else f"{name}s"
            parts.append(f"{value} {unit_name}")

    if not parts:
        return "0 seconds"

    if len(parts) == 1:
        return parts[0]

    return f"{parts[0]} and {parts[1]}"


def format_distance_adaptive(meters: float, unit_preference: str = "auto") -> str:
    """OPTIMIZED: Adaptive distance formatting with smart units.

    Args:
        meters: Distance in meters
        unit_preference: 'auto', 'metric', 'imperial'

    Returns:
        Formatted distance string
    """
    if meters <= 0:
        return "0 m"

    if unit_preference == "imperial":
        feet = meters * 3.28084
        if feet < 1000:
            return f"{feet:.0f} ft"
        miles = feet / 5280
        return f"{miles:.1f} mi" if miles < 10 else f"{miles:.0f} mi"

    # OPTIMIZED: Metric with fewer conditions
    if meters < 1000:
        return f"{meters:.1f} m" if meters < 10 else f"{meters:.0f} m"

    km = meters / 1000
    return f"{km:.1f} km" if km < 10 else f"{km:.0f} km"


def format_time_ago_smart(
    timestamp: datetime, reference_time: datetime | None = None
) -> str:
    """OPTIMIZED: Smart time ago formatting with reduced complexity.

    Args:
        timestamp: The timestamp to format
        reference_time: Reference time (defaults to now)

    Returns:
        Human-readable time ago string
    """
    ref_time = reference_time or dt_util.utcnow()

    # OPTIMIZED: Ensure UTC timezone
    if timestamp.tzinfo is None:
        timestamp = dt_util.as_utc(timestamp)
    if ref_time.tzinfo is None:
        ref_time = dt_util.as_utc(ref_time)

    total_seconds = (ref_time - timestamp).total_seconds()

    if total_seconds < 0:
        return "in the future"

    for limit, formatter in _TIME_AGO_THRESHOLDS:
        if total_seconds < limit:
            return formatter(total_seconds)
    years = int(total_seconds / 31536000)
    return f"{years} year{'s' if years != 1 else ''} ago"


# OPTIMIZED: Calculation functions with enhanced performance
@performance_monitor(timeout=2.0)
async def async_calculate_haversine_distance(
    point1: Coordinates, point2: Coordinates, earth_radius: float = 6371000.0
) -> float:
    """OPTIMIZED: Fast Haversine distance calculation.

    Args:
        point1: First coordinate (lat, lon)
        point2: Second coordinate (lat, lon)
        earth_radius: Earth radius in meters

    Returns:
        Distance in meters
    """
    lat1, lon1 = point1
    lat2, lon2 = point2

    # OPTIMIZED: Convert to radians in single operation
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    delta_lat, delta_lon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)

    # OPTIMIZED: Haversine formula
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) *
        math.sin(delta_lon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return round(earth_radius * c, 2)


@lru_cache(maxsize=CACHE_SIZE)
def calculate_bmr_advanced(
    weight_kg: float,
    age_years: int,
    activity_level: str = "normal",
    breed_factor: float = 1.0,
    is_neutered: bool = True,
) -> float:
    """OPTIMIZED: Fast BMR calculation with caching.

    Args:
        weight_kg: Dog weight in kg
        age_years: Dog age in years
        activity_level: Activity level
        breed_factor: Breed metabolic factor
        is_neutered: Neutered status

    Returns:
        Daily calorie needs
    """
    # OPTIMIZED: Pre-calculated activity multipliers
    activity_multipliers = {
        "very_low": 1.1,
        "low": 1.3,
        "normal": 1.6,
        "high": 1.8,
        "very_high": 2.2,
        "working": 2.5,
        "racing": 3.0,
    }

    # OPTIMIZED: Fast RER calculation
    rer = 70 * (weight_kg**0.75) * breed_factor
    multiplier = activity_multipliers.get(activity_level, 1.6)

    # OPTIMIZED: Age adjustments with lookup table
    if age_years < 0.5:
        multiplier *= 2.5
    elif age_years < 1:
        multiplier *= 2.0
    elif age_years < 2:
        multiplier *= 1.2
    elif age_years > 10:
        multiplier *= 0.8
    elif age_years > 7:
        multiplier *= 0.9

    if is_neutered:
        multiplier *= 0.95

    return round(rer * multiplier, 1)


# OPTIMIZED: Utility functions with better performance
@overload
def safe_convert(
    value: Any, target_type: type[int], default: int = 0) -> int: ...


@overload
def safe_convert(
    value: Any, target_type: type[float], default: float = 0.0
) -> float: ...


@overload
def safe_convert(
    value: Any, target_type: type[str], default: str = "") -> str: ...


def safe_convert(value: Any, target_type: type[T], default: T | None = None) -> T:
    """OPTIMIZED: Type-safe conversion with fast path for common types.

    Args:
        value: Value to convert
        target_type: Target type
        default: Default value if conversion fails

    Returns:
        Converted value or default
    """
    if value is None:
        return default if default is not None else target_type()

    # OPTIMIZED: Fast path for already correct types
    if isinstance(value, target_type):
        return value

    try:
        # OPTIMIZED: Specialized conversions
        if target_type is bool:
            if isinstance(value, str):
                return target_type(value.lower() in ("true", "yes", "1", "on"))
            return target_type(value)

        return target_type(value)

    except (ValueError, TypeError):
        return default if default is not None else target_type()


def deep_merge_dicts_optimized(
    dict1: dict[str, Any], dict2: dict[str, Any], max_depth: int = 5
) -> dict[str, Any]:
    """OPTIMIZED: Fast dictionary merge with reduced depth limit.

    Args:
        dict1: Base dictionary
        dict2: Overlay dictionary
        max_depth: Maximum recursion depth

    Returns:
        Merged dictionary
    """
    if max_depth <= 0:
        return dict1.copy()

    result = dict1.copy()

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts_optimized(
                result[key], value, max_depth - 1)
        else:
            result[key] = value

    return result


def deep_merge_dicts(
    dict1: dict[str, Any], dict2: dict[str, Any], max_depth: int = 5
) -> dict[str, Any]:
    """Backward compatible wrapper for ``deep_merge_dicts_optimized``.

    Maintains the original public API while delegating to the optimized
    implementation. This allows legacy imports (``deep_merge_dicts``) to
    continue working after the refactor that introduced
    ``deep_merge_dicts_optimized``.
    """

    return deep_merge_dicts_optimized(dict1, dict2, max_depth)


@lru_cache(maxsize=CACHE_SIZE)
def calculate_trend_advanced(
    values: tuple[float, ...], periods: int = 7
) -> dict[str, Any]:
    """OPTIMIZED: Fast trend calculation with linear regression."""

    if len(values) < 2:
        return {"direction": "unknown", "strength": 0.0, "confidence": 0.0}

    recent = list(values[:periods])
    if len(recent) < 2:
        return {"direction": "unknown", "strength": 0.0, "confidence": 0.0}

    slope, r_squared = _linear_regression(recent[::-1])
    direction, strength = _trend_from_slope(slope)

    return {
        "direction": direction,
        "strength": strength,
        "confidence": r_squared,
        "periods_analyzed": len(recent),
    }


def _linear_regression(values: list[float]) -> tuple[float, float]:
    """Return slope and r-squared for given values."""

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    slope = numerator / denominator if denominator else 0

    y_pred = [slope * i + (y_mean - slope * x_mean) for i in range(n)]
    ss_tot = sum((v - y_mean) ** 2 for v in values)
    ss_res = sum((v - p) ** 2 for v, p in zip(values, y_pred, strict=False))
    r_squared = 1 - (ss_res / ss_tot) if ss_tot else 0

    return slope, round(max(0, min(r_squared, 1)), 3)


def _trend_from_slope(slope: float) -> tuple[str, float]:
    """Determine trend direction and strength from slope."""

    abs_slope = abs(slope)
    if abs_slope < 0.01:
        return "stable", 0.0

    direction = "increasing" if slope > 0 else "decreasing"
    strength = round(min(abs_slope * 10, 1.0), 3)
    return direction, strength


def is_within_time_range_enhanced(
    current_time: datetime | time, start_time: str | time, end_time: str | time
) -> tuple[bool, str | None]:
    """OPTIMIZED: Fast time range checking.

    Args:
        current_time: Time to check
        start_time: Range start
        end_time: Range end

    Returns:
        Tuple of (is_within_range, error_message)
    """
    try:
        # OPTIMIZED: Convert to time objects efficiently
        current_time_obj = (
            current_time.time() if isinstance(current_time, datetime) else current_time
        )

        # OPTIMIZED: Handle string times with validation
        if isinstance(start_time, str):
            if not TIME_PATTERN.match(start_time):
                return False, f"Invalid start time: {start_time}"
            start_hour, start_minute = map(int, start_time.split(":"))
            start_time_obj = time(start_hour, start_minute)
        else:
            start_time_obj = start_time

        if isinstance(end_time, str):
            if not TIME_PATTERN.match(end_time):
                return False, f"Invalid end time: {end_time}"
            end_hour, end_minute = map(int, end_time.split(":"))
            end_time_obj = time(end_hour, end_minute)
        else:
            end_time_obj = end_time

        # OPTIMIZED: Fast range check
        if start_time_obj <= end_time_obj:
            is_within = start_time_obj <= current_time_obj <= end_time_obj
        else:
            is_within = (
                current_time_obj >= start_time_obj or current_time_obj <= end_time_obj
            )

        return is_within, None

    except (ValueError, AttributeError, TypeError) as err:
        return False, f"Invalid time format: {err}"


def sanitize_filename_advanced(
    filename: str, max_length: int = 255, replacement_char: str = "_"
) -> str:
    """OPTIMIZED: Fast filename sanitization.

    Args:
        filename: Original filename
        max_length: Maximum length
        replacement_char: Replacement character

    Returns:
        Sanitized filename
    """
    if not filename:
        return "file"

    # OPTIMIZED: Single pass sanitization
    sanitized = FILENAME_INVALID_CHARS.sub(replacement_char, filename)
    sanitized = MULTIPLE_UNDERSCORES.sub(replacement_char, sanitized)
    sanitized = sanitized.strip(f" .{replacement_char}")

    if not sanitized:
        sanitized = "file"

    # OPTIMIZED: Length truncation with extension preservation
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


# OPTIMIZED: Device info generation helper
def create_device_info(dog_id: str, dog_name: str) -> dict[str, Any]:
    """OPTIMIZED: Generate consistent device info with configuration URL."""
    return {
        "identifiers": {(DOMAIN, dog_id)},
        "name": dog_name,
        "manufacturer": "Paw Control",
        "model": "Smart Dog Monitoring",
        "sw_version": "1.0.0",
        "configuration_url": "https://github.com/bigdaddy1990/pawcontrol",
    }


def is_within_quiet_hours(now: datetime, start: str | time, end: str | time) -> bool:
    """Return True if current time is within the quiet hours range."""
    # Convert string times to time objects if necessary
    if isinstance(start, str):
        start = datetime.strptime(start, "%H:%M").time()
    if isinstance(end, str):
        end = datetime.strptime(end, "%H:%M").time()

    if start <= end:
        return start <= now.time() <= end
    return now.time() >= start or now.time() <= end


# OPTIMIZED: Legacy compatibility with deprecation paths
def safe_float(value: Any, default: float = 0.0) -> float:
    """Legacy compatibility - use safe_convert instead."""
    return safe_convert(value, float, default)


def safe_int(value: Any, default: int = 0) -> int:
    """Legacy compatibility - use safe_convert instead."""
    return safe_convert(value, int, default)


def safe_str(value: Any, default: str = "") -> str:
    """Legacy compatibility - use safe_convert instead."""
    return safe_convert(value, str, default)


# OPTIMIZED: Streamlined exports - only essential functions
__all__ = (
    "async_batch_validate",
    # Calculations
    "async_calculate_haversine_distance",
    "async_validate_coordinates",
    "calculate_bmr_advanced",
    "calculate_trend_advanced",
    # Utilities
    "create_device_info",
    "deep_merge_dicts",
    "deep_merge_dicts_optimized",
    "format_distance_adaptive",
    # Formatting
    "format_duration_optimized",
    "format_time_ago_smart",
    "is_within_quiet_hours",
    "is_within_time_range_enhanced",
    # Performance
    "performance_monitor",
    "safe_convert",
    # Legacy (deprecated)
    "safe_float",
    "safe_int",
    "safe_str",
    "sanitize_filename_advanced",
    # Core validation
    "validate_dog_id",
    "validate_enum_value",
    "validate_weight_enhanced",
)
