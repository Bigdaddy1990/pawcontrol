"""Validation helpers for Paw Control integration."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.exceptions import HomeAssistantError


class ValidationError(HomeAssistantError):
    """Validation error exception."""

    pass


def validate_dog_id(dog_id: str) -> str:
    """Validate and sanitize dog ID.

    Args:
        dog_id: The dog ID to validate

    Returns:
        Sanitized dog ID

    Raises:
        ValidationError: If dog ID is invalid
    """
    if not dog_id:
        raise ValidationError("Dog ID cannot be empty")

    # Convert to lowercase and replace spaces with underscores
    sanitized = dog_id.lower().strip().replace(" ", "_")

    # Allow only alphanumeric characters and underscores
    if not re.match(r"^[a-z0-9_]+$", sanitized):
        raise ValidationError(
            "Dog ID can only contain letters, numbers, and underscores"
        )

    # Ensure reasonable length
    if len(sanitized) < 1 or len(sanitized) > 50:
        raise ValidationError("Dog ID must be between 1 and 50 characters")

    return sanitized


def validate_dog_weight(weight: Any) -> float:
    """Validate dog weight.

    Args:
        weight: Weight value to validate

    Returns:
        Validated weight as float

    Raises:
        ValidationError: If weight is invalid
    """
    try:
        weight_float = float(weight)
    except (TypeError, ValueError):
        raise ValidationError("Weight must be a number")

    if weight_float <= 0 or weight_float > 200:
        raise ValidationError("Weight must be between 0.1 and 200 kg")

    return weight_float


def validate_dog_age(age: Any) -> int:
    """Validate dog age.

    Args:
        age: Age value to validate

    Returns:
        Validated age as integer

    Raises:
        ValidationError: If age is invalid
    """
    try:
        age_int = int(age)
    except (TypeError, ValueError):
        raise ValidationError("Age must be a whole number")

    if age_int < 0 or age_int > 30:
        raise ValidationError("Age must be between 0 and 30 years")

    return age_int


def validate_gps_coordinates(lat: Any, lon: Any) -> tuple[float, float]:
    """Validate GPS coordinates.

    Args:
        lat: Latitude value
        lon: Longitude value

    Returns:
        Tuple of (latitude, longitude) as floats

    Raises:
        ValidationError: If coordinates are invalid
    """
    try:
        lat_float = float(lat)
        lon_float = float(lon)
    except (TypeError, ValueError):
        raise ValidationError("GPS coordinates must be numbers")

    if not -90 <= lat_float <= 90:
        raise ValidationError(f"Invalid latitude: {lat_float}")

    if not -180 <= lon_float <= 180:
        raise ValidationError(f"Invalid longitude: {lon_float}")

    return lat_float, lon_float


def validate_gps_accuracy(accuracy: Any) -> float | None:
    """Validate GPS accuracy value.

    Args:
        accuracy: Accuracy value in meters

    Returns:
        Validated accuracy as float or None

    Raises:
        ValidationError: If accuracy is invalid
    """
    if accuracy is None:
        return None

    try:
        acc_float = float(accuracy)
    except (TypeError, ValueError):
        raise ValidationError("Accuracy must be a number")

    if acc_float < 0 or acc_float > 10000:
        raise ValidationError("Accuracy must be between 0 and 10000 meters")

    return acc_float


def validate_walk_duration(duration: Any) -> float:
    """Validate walk duration in minutes.

    Args:
        duration: Duration in minutes

    Returns:
        Validated duration as float

    Raises:
        ValidationError: If duration is invalid
    """
    try:
        duration_float = float(duration)
    except (TypeError, ValueError):
        raise ValidationError("Duration must be a number")

    if duration_float < 0 or duration_float > 1440:  # Max 24 hours
        raise ValidationError("Duration must be between 0 and 1440 minutes")

    return duration_float


def validate_distance(distance: Any) -> float:
    """Validate distance in meters.

    Args:
        distance: Distance in meters

    Returns:
        Validated distance as float

    Raises:
        ValidationError: If distance is invalid
    """
    try:
        distance_float = float(distance)
    except (TypeError, ValueError):
        raise ValidationError("Distance must be a number")

    if distance_float < 0 or distance_float > 100000:  # Max 100km
        raise ValidationError("Distance must be between 0 and 100000 meters")

    return distance_float


def validate_meal_type(meal_type: str) -> str:
    """Validate meal type.

    Args:
        meal_type: Type of meal

    Returns:
        Validated meal type

    Raises:
        ValidationError: If meal type is invalid
    """
    valid_meals = {"breakfast", "lunch", "dinner", "snack"}

    meal_lower = meal_type.lower().strip()

    if meal_lower not in valid_meals:
        raise ValidationError(
            f"Invalid meal type: {meal_type}. Must be one of: {', '.join(valid_meals)}"
        )

    return meal_lower


def validate_portion_size(portion: Any) -> int:
    """Validate portion size in grams.

    Args:
        portion: Portion size in grams

    Returns:
        Validated portion as integer

    Raises:
        ValidationError: If portion is invalid
    """
    try:
        portion_int = int(portion)
    except (TypeError, ValueError):
        raise ValidationError("Portion must be a whole number")

    if portion_int < 0 or portion_int > 5000:  # Max 5kg
        raise ValidationError("Portion must be between 0 and 5000 grams")

    return portion_int


def validate_medication_slot(slot: Any) -> int:
    """Validate medication slot number.

    Args:
        slot: Slot number

    Returns:
        Validated slot as integer

    Raises:
        ValidationError: If slot is invalid
    """
    try:
        slot_int = int(slot)
    except (TypeError, ValueError):
        raise ValidationError("Slot must be a number")

    if slot_int < 1 or slot_int > 3:
        raise ValidationError("Slot must be 1, 2, or 3")

    return slot_int


def validate_rating(rating: Any) -> int:
    """Validate rating value.

    Args:
        rating: Rating value

    Returns:
        Validated rating as integer

    Raises:
        ValidationError: If rating is invalid
    """
    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        raise ValidationError("Rating must be a whole number")

    if rating_int < 1 or rating_int > 5:
        raise ValidationError("Rating must be between 1 and 5")

    return rating_int


def sanitize_text_input(text: str, max_length: int = 500) -> str:
    """Sanitize text input.

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Remove any potentially harmful characters
    sanitized = str(text).strip()

    # Remove control characters
    sanitized = "".join(char for char in sanitized if ord(char) >= 32 or char == "\n")

    # Limit length
    return sanitized[:max_length]


def validate_time_string(time_str: str) -> str:
    """Validate time string format.

    Args:
        time_str: Time string in HH:MM:SS format

    Returns:
        Validated time string

    Raises:
        ValidationError: If time string is invalid
    """
    if not re.match(r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$", time_str):
        raise ValidationError(f"Invalid time format: {time_str}. Use HH:MM:SS")

    return time_str


def validate_export_format(format_str: str) -> str:
    """Validate export format.

    Args:
        format_str: Export format string

    Returns:
        Validated format

    Raises:
        ValidationError: If format is invalid
    """
    valid_formats = {"csv", "json", "pdf", "geojson", "gpx"}

    format_lower = format_str.lower().strip()

    if format_lower not in valid_formats:
        raise ValidationError(
            f"Invalid export format: {format_str}. Must be one of: {', '.join(valid_formats)}"
        )

    return format_lower


def validate_webhook_id(webhook_id: str) -> str:
    """Validate webhook ID format.

    Args:
        webhook_id: Webhook ID to validate

    Returns:
        Validated webhook ID

    Raises:
        ValidationError: If webhook ID is invalid
    """
    if not webhook_id:
        raise ValidationError("Webhook ID cannot be empty")

    # Basic validation for webhook ID format
    if not re.match(r"^[a-zA-Z0-9_\-]+$", webhook_id):
        raise ValidationError("Invalid webhook ID format")

    if len(webhook_id) < 10 or len(webhook_id) > 200:
        raise ValidationError("Webhook ID length invalid")

    return webhook_id
