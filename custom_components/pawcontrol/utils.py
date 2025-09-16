"""Utility functions for PawControl integration.

Provides common utility functions, data validation, type conversion,
and helper methods used throughout the integration.

Quality Scale: Platinum
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, time, timedelta
from typing import Any, TypeVar

from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

# Type variables for generic functions
T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


def deep_merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries.

    Args:
        base: Base dictionary to merge into
        updates: Updates to apply

    Returns:
        New dictionary with merged values
    """
    result = base.copy()

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def safe_get_nested(
    data: dict[str, Any], path: str, default: Any = None, separator: str = "."
) -> Any:
    """Safely get nested dictionary value using dot notation.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "dog.health.weight")
        default: Default value if path not found
        separator: Path separator character

    Returns:
        Value at path or default
    """
    try:
        keys = path.split(separator)
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default

        return current
    except (AttributeError, KeyError, TypeError):
        return default


def safe_set_nested(
    data: dict[str, Any], path: str, value: Any, separator: str = "."
) -> dict[str, Any]:
    """Safely set nested dictionary value using dot notation.

    Args:
        data: Dictionary to update
        path: Dot-separated path
        value: Value to set
        separator: Path separator character

    Returns:
        Updated dictionary
    """
    keys = path.split(separator)
    current = data

    # Navigate to parent of target key
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    # Set the final value
    current[keys[-1]] = value
    return data


def validate_time_string(time_str: str | None) -> time | None:
    """Validate and parse time string.

    Args:
        time_str: Time string in HH:MM or HH:MM:SS format

    Returns:
        Parsed time object or None if invalid
    """
    if not time_str:
        return None

    try:
        # Support both HH:MM and HH:MM:SS formats
        if re.match(r"^\d{1,2}:\d{2}$", time_str):
            hour, minute = map(int, time_str.split(":"))
            return time(hour, minute)
        elif re.match(r"^\d{1,2}:\d{2}:\d{2}$", time_str):
            hour, minute, second = map(int, time_str.split(":"))
            return time(hour, minute, second)
    except (ValueError, AttributeError):
        pass

    return None


def validate_email(email: str | None) -> bool:
    """Validate email address format.

    Args:
        email: Email address to validate

    Returns:
        True if valid email format
    """
    if not email:
        return False

    # Simple but effective email regex
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def sanitize_dog_id(dog_id: str) -> str:
    """Sanitize dog ID for use as entity identifier.

    Args:
        dog_id: Raw dog ID

    Returns:
        Sanitized dog ID suitable for entity IDs
    """
    # Convert to lowercase and replace invalid characters
    sanitized = re.sub(r"[^a-z0-9_]", "_", dog_id.lower())

    # Ensure it starts with a letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = f"dog_{sanitized}"

    # Remove consecutive underscores
    sanitized = re.sub(r"_+", "_", sanitized)

    # Remove leading/trailing underscores
    return sanitized.strip("_")


def format_duration(seconds: int | float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"
    else:
        hours = int(seconds // 3600)
        remaining_minutes = int((seconds % 3600) // 60)
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"


def format_distance(meters: float, unit: str = "metric") -> str:
    """Format distance with appropriate units.

    Args:
        meters: Distance in meters
        unit: Unit system ("metric" or "imperial")

    Returns:
        Formatted distance string
    """
    if unit == "imperial":
        feet = meters * 3.28084
        if feet < 5280:
            return f"{int(feet)} ft"
        else:
            miles = feet / 5280
            return f"{miles:.1f} mi"
    else:
        if meters < 1000:
            return f"{int(meters)} m"
        else:
            kilometers = meters / 1000
            return f"{kilometers:.1f} km"


def calculate_age_from_months(age_months: int) -> dict[str, int]:
    """Calculate years and months from total months.

    Args:
        age_months: Total age in months

    Returns:
        Dictionary with years and months
    """
    years = age_months // 12
    months = age_months % 12

    return {
        "years": years,
        "months": months,
        "total_months": age_months,
    }


def parse_weight(weight_input: str | float | int) -> float | None:
    """Parse weight input in various formats.

    Args:
        weight_input: Weight as string, float, or int

    Returns:
        Weight in kilograms or None if invalid
    """
    if isinstance(weight_input, int | float):
        return float(weight_input) if weight_input > 0 else None

    if not isinstance(weight_input, str):
        return None

    # Remove whitespace and convert to lowercase
    weight_str = weight_input.strip().lower()

    # Handle common weight formats
    if "kg" in weight_str:
        try:
            return float(weight_str.replace("kg", "").strip())
        except ValueError:
            pass
    elif "lb" in weight_str or "lbs" in weight_str:
        try:
            # Convert pounds to kilograms
            lbs = float(weight_str.replace("lbs", "").replace("lb", "").strip())
            return lbs * 0.453592
        except ValueError:
            pass
    else:
        # Try parsing as plain number (assume kg)
        try:
            return float(weight_str)
        except ValueError:
            pass

    return None


def generate_entity_id(domain: str, dog_id: str, entity_type: str) -> str:
    """Generate entity ID following Home Assistant conventions.

    Args:
        domain: Integration domain
        dog_id: Dog identifier
        entity_type: Type of entity

    Returns:
        Generated entity ID
    """
    sanitized_dog_id = sanitize_dog_id(dog_id)
    sanitized_type = re.sub(r"[^a-z0-9_]", "_", entity_type.lower())

    return f"{domain}.{sanitized_dog_id}_{sanitized_type}"


def calculate_bmi_equivalent(weight_kg: float, breed_size: str) -> float | None:
    """Calculate BMI equivalent for dogs based on breed size.

    Args:
        weight_kg: Weight in kilograms
        breed_size: Size category ("toy", "small", "medium", "large", "giant")

    Returns:
        BMI equivalent or None if invalid
    """
    # Standard weight ranges for breed sizes (kg)
    size_ranges = {
        "toy": (1.0, 6.0),
        "small": (4.0, 15.0),
        "medium": (8.0, 30.0),
        "large": (22.0, 50.0),
        "giant": (35.0, 90.0),
    }

    if breed_size not in size_ranges:
        return None

    min_weight, max_weight = size_ranges[breed_size]

    # Calculate relative position within breed size range
    if weight_kg <= min_weight:
        return 15.0  # Underweight
    elif weight_kg >= max_weight:
        return 30.0  # Overweight
    else:
        # Linear interpolation between 18.5 (normal low) and 25 (normal high)
        ratio = (weight_kg - min_weight) / (max_weight - min_weight)
        return 18.5 + (ratio * 6.5)  # 18.5 to 25


def validate_portion_size(
    portion: float, daily_amount: float, meals_per_day: int = 2
) -> dict[str, Any]:
    """Validate portion size against daily requirements.

    Args:
        portion: Portion size in grams
        daily_amount: Total daily food amount
        meals_per_day: Number of meals per day

    Returns:
        Validation result with warnings and recommendations
    """
    result = {
        "valid": True,
        "warnings": [],
        "recommendations": [],
        "percentage_of_daily": 0.0,
    }

    if daily_amount > 0:
        percentage = (portion / daily_amount) * 100
        result["percentage_of_daily"] = percentage

        expected_percentage = 100 / meals_per_day

        # Check for extremely large portions
        if percentage > 70:
            result["valid"] = False
            result["warnings"].append("Portion exceeds 70% of daily requirement")
            result["recommendations"].append("Consider reducing portion size")
        elif percentage > expected_percentage * 1.5:
            result["warnings"].append(
                "Portion is larger than typical for meal frequency"
            )
            result["recommendations"].append("Verify portion calculation")

        # Check for extremely small portions
        elif percentage < 5:
            result["warnings"].append(
                "Portion is very small compared to daily requirement"
            )
            result["recommendations"].append(
                "Consider increasing portion or meal frequency"
            )

    return result


def chunk_list[T](items: Sequence[T], chunk_size: int) -> list[list[T]]:
    """Split a list into chunks of specified size.

    Args:
        items: List to chunk
        chunk_size: Maximum size of each chunk

    Returns:
        List of chunks
    """
    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive")

    return [list(items[i : i + chunk_size]) for i in range(0, len(items), chunk_size)]


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers with default for division by zero.

    Args:
        numerator: Number to divide
        denominator: Number to divide by
        default: Default value if denominator is zero

    Returns:
        Division result or default
    """
    try:
        return numerator / denominator if denominator != 0 else default
    except (TypeError, ZeroDivisionError):
        return default


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp value between minimum and maximum.

    Args:
        value: Value to clamp
        min_value: Minimum allowed value
        max_value: Maximum allowed value

    Returns:
        Clamped value
    """
    return max(min_value, min(value, max_value))


def is_dict_subset(subset: Mapping[K, V], superset: Mapping[K, V]) -> bool:
    """Check if one dictionary is a subset of another.

    Args:
        subset: Dictionary to check if it's a subset
        superset: Dictionary to check against

    Returns:
        True if subset is contained in superset
    """
    try:
        return all(
            key in superset and superset[key] == value for key, value in subset.items()
        )
    except (AttributeError, TypeError):
        return False


def flatten_dict(
    data: dict[str, Any], separator: str = ".", prefix: str = ""
) -> dict[str, Any]:
    """Flatten nested dictionary using dot notation.

    Args:
        data: Dictionary to flatten
        separator: Separator for keys
        prefix: Prefix for keys

    Returns:
        Flattened dictionary
    """
    flattened = {}

    for key, value in data.items():
        new_key = f"{prefix}{separator}{key}" if prefix else key

        if isinstance(value, dict):
            flattened.update(flatten_dict(value, separator, new_key))
        else:
            flattened[new_key] = value

    return flattened


def unflatten_dict(data: dict[str, Any], separator: str = ".") -> dict[str, Any]:
    """Unflatten dictionary from dot notation.

    Args:
        data: Flattened dictionary
        separator: Key separator

    Returns:
        Nested dictionary
    """
    result = {}

    for key, value in data.items():
        safe_set_nested(result, key, value, separator)

    return result


def extract_numbers(text: str) -> list[float]:
    """Extract all numbers from text string.

    Args:
        text: Text to extract numbers from

    Returns:
        List of extracted numbers
    """
    pattern = r"-?\d+(?:\.\d+)?"
    matches = re.findall(pattern, text)

    try:
        return [float(match) for match in matches]
    except ValueError:
        return []


def generate_unique_id(*parts: str) -> str:
    """Generate unique ID from multiple parts.

    Args:
        *parts: Parts to combine into unique ID

    Returns:
        Generated unique ID
    """
    # Sanitize each part and join with underscores
    sanitized_parts = []
    for part in parts:
        if part:
            sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", str(part))
            sanitized = re.sub(r"_+", "_", sanitized).strip("_")
            if sanitized:
                sanitized_parts.append(sanitized.lower())

    return "_".join(sanitized_parts) if sanitized_parts else "unknown"


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Decorator for retrying functions on exception.

    Args:
        max_retries: Maximum number of retries
        delay: Initial delay between retries
        backoff_factor: Factor to multiply delay by each retry
        exceptions: Exception types to retry on

    Returns:
        Decorator function
    """

    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "Attempt %d failed for %s: %s. Retrying in %.1fs",
                            attempt + 1,
                            func.__name__,
                            e,
                            current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        _LOGGER.error(
                            "All %d attempts failed for %s",
                            max_retries + 1,
                            func.__name__,
                        )

            raise last_exception

        def sync_wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        _LOGGER.debug(
                            "Attempt %d failed for %s: %s. Retrying in %.1fs",
                            attempt + 1,
                            func.__name__,
                            e,
                            current_delay,
                        )
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        _LOGGER.error(
                            "All %d attempts failed for %s",
                            max_retries + 1,
                            func.__name__,
                        )

            raise last_exception

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator


def calculate_time_until(target_time: time) -> timedelta:
    """Calculate time until next occurrence of target time.

    Args:
        target_time: Target time of day

    Returns:
        Time delta until next occurrence
    """
    now = dt_util.now()
    today = now.date()

    # Try today first
    target_datetime = datetime.combine(today, target_time)
    target_datetime = dt_util.as_local(target_datetime)

    if target_datetime > now:
        return target_datetime - now
    else:
        # Must be tomorrow
        tomorrow = today + timedelta(days=1)
        target_datetime = datetime.combine(tomorrow, target_time)
        target_datetime = dt_util.as_local(target_datetime)
        return target_datetime - now


def format_relative_time(dt: datetime) -> str:
    """Format datetime as relative time string.

    Args:
        dt: Datetime to format

    Returns:
        Relative time string
    """
    now = dt_util.now()

    # Make both timezone-aware for comparison
    if dt.tzinfo is None:
        dt = dt_util.as_local(dt)
    if now.tzinfo is None:
        now = dt_util.as_local(now)

    delta = now - dt

    if delta.total_seconds() < 60:
        return "just now"
    elif delta.total_seconds() < 3600:
        minutes = int(delta.total_seconds() / 60)
        return f"{minutes}m ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    elif delta.days == 1:
        return "yesterday"
    elif delta.days < 7:
        return f"{delta.days} days ago"
    elif delta.days < 30:
        weeks = delta.days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    else:
        months = delta.days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"


def merge_configurations(
    base_config: dict[str, Any],
    user_config: dict[str, Any],
    protected_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Merge user configuration with base configuration.

    Args:
        base_config: Base configuration with defaults
        user_config: User-provided configuration
        protected_keys: Keys that cannot be overridden

    Returns:
        Merged configuration
    """
    protected_keys = protected_keys or set()
    merged = base_config.copy()

    for key, value in user_config.items():
        if key in protected_keys:
            _LOGGER.warning("Ignoring protected configuration key: %s", key)
            continue

        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = merge_configurations(merged[key], value, protected_keys)
        else:
            merged[key] = value

    return merged


def validate_configuration_schema(
    config: dict[str, Any],
    required_keys: set[str],
    optional_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Validate configuration against schema.

    Args:
        config: Configuration to validate
        required_keys: Required configuration keys
        optional_keys: Optional configuration keys

    Returns:
        Validation result with missing/unknown keys
    """
    optional_keys = optional_keys or set()
    all_valid_keys = required_keys | optional_keys

    missing_keys = required_keys - config.keys()
    unknown_keys = config.keys() - all_valid_keys

    return {
        "valid": len(missing_keys) == 0,
        "missing_keys": list(missing_keys),
        "unknown_keys": list(unknown_keys),
        "has_all_required": len(missing_keys) == 0,
        "has_unknown": len(unknown_keys) > 0,
    }


def convert_units(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between different units.

    Args:
        value: Value to convert
        from_unit: Source unit
        to_unit: Target unit

    Returns:
        Converted value

    Raises:
        ValueError: If unit conversion not supported
    """
    # Weight conversions
    weight_conversions = {
        ("kg", "lb"): lambda x: x * 2.20462,
        ("lb", "kg"): lambda x: x * 0.453592,
        ("g", "kg"): lambda x: x / 1000,
        ("kg", "g"): lambda x: x * 1000,
        ("oz", "g"): lambda x: x * 28.3495,
        ("g", "oz"): lambda x: x / 28.3495,
    }

    # Distance conversions
    distance_conversions = {
        ("m", "ft"): lambda x: x * 3.28084,
        ("ft", "m"): lambda x: x / 3.28084,
        ("km", "mi"): lambda x: x * 0.621371,
        ("mi", "km"): lambda x: x / 0.621371,
        ("m", "km"): lambda x: x / 1000,
        ("km", "m"): lambda x: x * 1000,
    }

    # Temperature conversions
    temp_conversions = {
        ("c", "f"): lambda x: (x * 9 / 5) + 32,
        ("f", "c"): lambda x: (x - 32) * 5 / 9,
    }

    # Combine all conversions
    all_conversions = {
        **weight_conversions,
        **distance_conversions,
        **temp_conversions,
    }

    # Normalize unit names
    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    # Handle same unit
    if from_unit == to_unit:
        return value

    # Look up conversion
    conversion_key = (from_unit, to_unit)
    if conversion_key in all_conversions:
        return all_conversions[conversion_key](value)

    raise ValueError(f"Conversion from {from_unit} to {to_unit} not supported")
