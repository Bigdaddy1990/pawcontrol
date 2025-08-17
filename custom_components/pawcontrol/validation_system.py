"""Comprehensive validation and error handling system for Paw Control options flow.

This module provides robust validation, error handling, and data sanitization
for all configuration options in the Paw Control integration.

Key features:
- Input validation with detailed error messages
- Data sanitization and normalization
- Schema validation with custom validators
- Error recovery and fallback mechanisms
- Comprehensive logging for debugging
"""

from __future__ import annotations

import logging
import re
from datetime import time
from typing import Any, Dict, List, Union, Callable
import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import (
    # Dog constants
    MIN_DOG_AGE_YEARS,
    MAX_DOG_AGE_YEARS,
    MIN_DOG_WEIGHT_KG,
    MAX_DOG_WEIGHT_KG,
    SIZE_SMALL,
    SIZE_MEDIUM,
    SIZE_LARGE,
    SIZE_XLARGE,
    # GPS constants
    GPS_MIN_ACCURACY,
    GPS_POINT_FILTER_DISTANCE,
    # Geofence constants
    MIN_SAFE_ZONE_RADIUS,
    MAX_SAFE_ZONE_RADIUS,
    # System constants
    DEFAULT_REMINDER_REPEAT,
    DEFAULT_SNOOZE_MIN,
)

_LOGGER = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom validation error with detailed context."""

    def __init__(self, message: str, field: str | None = None, value: Any = None):
        """Initialize validation error."""
        self.message = message
        self.field = field
        self.value = value
        super().__init__(message)


class ConfigValidator:
    """Comprehensive configuration validator for Paw Control."""

    # Regular expressions for validation
    DOG_ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
    TIME_PATTERN = re.compile(r"^([01]?[0-9]|2[0-3]):[0-5][0-9](?::[0-5][0-9])?$")
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

    @staticmethod
    def validate_dog_id(dog_id: str) -> str:
        """Validate and normalize dog ID.

        Args:
            dog_id: The dog ID to validate

        Returns:
            Normalized dog ID

        Raises:
            ValidationError: If dog ID is invalid
        """
        if not dog_id or not isinstance(dog_id, str):
            raise ValidationError("Dog ID cannot be empty", "dog_id", dog_id)

        # Normalize: strip, lowercase, replace spaces with underscores
        normalized = dog_id.strip().lower().replace(" ", "_").replace("-", "_")

        # Remove invalid characters
        normalized = re.sub(r"[^a-z0-9_]", "", normalized)

        if not normalized:
            raise ValidationError(
                "Dog ID contains no valid characters", "dog_id", dog_id
            )

        if len(normalized) < 2:
            raise ValidationError(
                "Dog ID must be at least 2 characters long", "dog_id", normalized
            )

        if len(normalized) > 32:
            raise ValidationError(
                "Dog ID must be at most 32 characters long", "dog_id", normalized
            )

        if not ConfigValidator.DOG_ID_PATTERN.match(normalized):
            raise ValidationError(
                "Dog ID can only contain letters, numbers, and underscores",
                "dog_id",
                normalized,
            )

        # Must not start with underscore or number
        if normalized[0] in "_0123456789":
            raise ValidationError(
                "Dog ID must start with a letter", "dog_id", normalized
            )

        return normalized

    @staticmethod
    def validate_dog_name(name: str) -> str:
        """Validate and normalize dog name.

        Args:
            name: The dog name to validate

        Returns:
            Normalized dog name

        Raises:
            ValidationError: If dog name is invalid
        """
        if not name or not isinstance(name, str):
            raise ValidationError("Dog name cannot be empty", "dog_name", name)

        # Normalize: strip and title case
        normalized = name.strip()

        if not normalized:
            raise ValidationError(
                "Dog name cannot be empty after trimming", "dog_name", name
            )

        if len(normalized) < 1:
            raise ValidationError(
                "Dog name must be at least 1 character long", "dog_name", normalized
            )

        if len(normalized) > 50:
            raise ValidationError(
                "Dog name must be at most 50 characters long", "dog_name", normalized
            )

        # Check for invalid characters (allow letters, numbers, spaces, hyphens, apostrophes)
        if not re.match(r"^[a-zA-Z0-9\s\-']+$", normalized):
            raise ValidationError(
                "Dog name can only contain letters, numbers, spaces, hyphens, and apostrophes",
                "dog_name",
                normalized,
            )

        return normalized

    @staticmethod
    def validate_dog_age(age: Union[int, float, str]) -> int:
        """Validate dog age.

        Args:
            age: The age to validate

        Returns:
            Validated age as integer

        Raises:
            ValidationError: If age is invalid
        """
        try:
            age_int = int(float(age))
        except (ValueError, TypeError):
            raise ValidationError("Age must be a valid number", "dog_age", age)

        if age_int < MIN_DOG_AGE_YEARS:
            raise ValidationError(
                f"Age cannot be less than {MIN_DOG_AGE_YEARS} years", "dog_age", age_int
            )

        if age_int > MAX_DOG_AGE_YEARS:
            raise ValidationError(
                f"Age cannot be more than {MAX_DOG_AGE_YEARS} years", "dog_age", age_int
            )

        return age_int

    @staticmethod
    def validate_dog_weight(weight: Union[int, float, str]) -> float:
        """Validate dog weight.

        Args:
            weight: The weight to validate

        Returns:
            Validated weight as float

        Raises:
            ValidationError: If weight is invalid
        """
        try:
            weight_float = float(weight)
        except (ValueError, TypeError):
            raise ValidationError("Weight must be a valid number", "dog_weight", weight)

        if weight_float < MIN_DOG_WEIGHT_KG:
            raise ValidationError(
                f"Weight cannot be less than {MIN_DOG_WEIGHT_KG} kg",
                "dog_weight",
                weight_float,
            )

        if weight_float > MAX_DOG_WEIGHT_KG:
            raise ValidationError(
                f"Weight cannot be more than {MAX_DOG_WEIGHT_KG} kg",
                "dog_weight",
                weight_float,
            )

        return round(weight_float, 1)

    @staticmethod
    def validate_dog_size(size: str) -> str:
        """Validate dog size.

        Args:
            size: The size to validate

        Returns:
            Validated size

        Raises:
            ValidationError: If size is invalid
        """
        valid_sizes = [SIZE_SMALL, SIZE_MEDIUM, SIZE_LARGE, SIZE_XLARGE]

        if size not in valid_sizes:
            raise ValidationError(
                f"Size must be one of: {', '.join(valid_sizes)}", "dog_size", size
            )

        return size

    @staticmethod
    def validate_time_string(time_str: str) -> str:
        """Validate time string format.

        Args:
            time_str: Time string to validate (HH:MM or HH:MM:SS)

        Returns:
            Validated time string

        Raises:
            ValidationError: If time format is invalid
        """
        if not isinstance(time_str, str):
            raise ValidationError("Time must be a string", "time", time_str)

        if not ConfigValidator.TIME_PATTERN.match(time_str):
            raise ValidationError(
                "Time must be in HH:MM or HH:MM:SS format", "time", time_str
            )

        try:
            # Try to parse the time to ensure it's valid
            parts = time_str.split(":")
            hour, minute = int(parts[0]), int(parts[1])
            second = int(parts[2]) if len(parts) > 2 else 0
            time(hour, minute, second)  # This will raise ValueError if invalid
        except ValueError:
            raise ValidationError("Invalid time values", "time", time_str)

        return time_str

    @staticmethod
    def validate_coordinates(
        lat: Union[float, str], lon: Union[float, str]
    ) -> tuple[float, float]:
        """Validate GPS coordinates.

        Args:
            lat: Latitude to validate
            lon: Longitude to validate

        Returns:
            Tuple of validated (latitude, longitude)

        Raises:
            ValidationError: If coordinates are invalid
        """
        try:
            lat_float = float(lat)
            lon_float = float(lon)
        except (ValueError, TypeError):
            raise ValidationError(
                "Coordinates must be valid numbers", "coordinates", (lat, lon)
            )

        if not (-90 <= lat_float <= 90):
            raise ValidationError(
                "Latitude must be between -90 and 90", "latitude", lat_float
            )

        if not (-180 <= lon_float <= 180):
            raise ValidationError(
                "Longitude must be between -180 and 180", "longitude", lon_float
            )

        return round(lat_float, 6), round(lon_float, 6)

    @staticmethod
    def validate_radius(radius: Union[int, float, str]) -> int:
        """Validate geofence radius.

        Args:
            radius: Radius in meters to validate

        Returns:
            Validated radius as integer

        Raises:
            ValidationError: If radius is invalid
        """
        try:
            radius_int = int(float(radius))
        except (ValueError, TypeError):
            raise ValidationError("Radius must be a valid number", "radius", radius)

        if radius_int < MIN_SAFE_ZONE_RADIUS:
            raise ValidationError(
                f"Radius cannot be less than {MIN_SAFE_ZONE_RADIUS} meters",
                "radius",
                radius_int,
            )

        if radius_int > MAX_SAFE_ZONE_RADIUS:
            raise ValidationError(
                f"Radius cannot be more than {MAX_SAFE_ZONE_RADIUS} meters",
                "radius",
                radius_int,
            )

        return radius_int

    @staticmethod
    def validate_notification_channels(channels: List[str]) -> List[str]:
        """Validate notification channels.

        Args:
            channels: List of notification channels

        Returns:
            Validated list of channels

        Raises:
            ValidationError: If channels are invalid
        """
        valid_channels = ["mobile", "persistent", "email", "slack", "discord"]

        if not isinstance(channels, list):
            raise ValidationError(
                "Notification channels must be a list",
                "notification_channels",
                channels,
            )

        if not channels:
            raise ValidationError(
                "At least one notification channel must be selected",
                "notification_channels",
                channels,
            )

        invalid_channels = [ch for ch in channels if ch not in valid_channels]
        if invalid_channels:
            raise ValidationError(
                f"Invalid notification channels: {', '.join(invalid_channels)}",
                "notification_channels",
                invalid_channels,
            )

        return list(set(channels))  # Remove duplicates

    @staticmethod
    def validate_entity_id(entity_id: str) -> str:
        """Validate Home Assistant entity ID format.

        Args:
            entity_id: Entity ID to validate

        Returns:
            Validated entity ID

        Raises:
            ValidationError: If entity ID format is invalid
        """
        if not isinstance(entity_id, str):
            raise ValidationError("Entity ID must be a string", "entity_id", entity_id)

        # Home Assistant entity ID pattern: domain.object_id
        entity_pattern = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")

        if not entity_pattern.match(entity_id):
            raise ValidationError(
                "Entity ID must be in format 'domain.object_id'", "entity_id", entity_id
            )

        return entity_id

    @staticmethod
    def validate_file_path(path: str) -> str:
        """Validate file path.

        Args:
            path: File path to validate

        Returns:
            Validated file path

        Raises:
            ValidationError: If path is invalid
        """
        if not isinstance(path, str):
            raise ValidationError("Path must be a string", "path", path)

        path = path.strip()

        if not path:
            return ""  # Empty path is allowed (uses default)

        # Check for dangerous path components
        dangerous_patterns = ["..", "~", "$"]
        for pattern in dangerous_patterns:
            if pattern in path:
                raise ValidationError(f"Path cannot contain '{pattern}'", "path", path)

        return path


class SchemaBuilder:
    """Build validation schemas for different configuration sections."""

    @staticmethod
    def dog_config_schema(existing_dog: Dict[str, Any] | None = None) -> vol.Schema:
        """Build schema for dog configuration.

        Args:
            existing_dog: Existing dog data for defaults

        Returns:
            Validation schema
        """
        defaults = existing_dog or {}
        modules = defaults.get("modules", {})

        return vol.Schema(
            {
                vol.Required(
                    "dog_id", default=defaults.get("dog_id", "")
                ): ConfigValidator.validate_dog_id,
                vol.Required(
                    "dog_name", default=defaults.get("dog_name", "")
                ): ConfigValidator.validate_dog_name,
                vol.Optional(
                    "dog_breed", default=defaults.get("dog_breed", "")
                ): cv.string,
                vol.Optional(
                    "dog_age", default=defaults.get("dog_age", 1)
                ): ConfigValidator.validate_dog_age,
                vol.Optional(
                    "dog_weight", default=defaults.get("dog_weight", 20.0)
                ): ConfigValidator.validate_dog_weight,
                vol.Optional(
                    "dog_size", default=defaults.get("dog_size", SIZE_MEDIUM)
                ): ConfigValidator.validate_dog_size,
                # Module configurations
                vol.Optional(
                    "module_walk", default=modules.get("walk", True)
                ): cv.boolean,
                vol.Optional(
                    "module_feeding", default=modules.get("feeding", True)
                ): cv.boolean,
                vol.Optional(
                    "module_health", default=modules.get("health", True)
                ): cv.boolean,
                vol.Optional(
                    "module_gps", default=modules.get("gps", True)
                ): cv.boolean,
                vol.Optional(
                    "module_notifications", default=modules.get("notifications", True)
                ): cv.boolean,
                vol.Optional(
                    "module_dashboard", default=modules.get("dashboard", True)
                ): cv.boolean,
                vol.Optional(
                    "module_grooming", default=modules.get("grooming", True)
                ): cv.boolean,
                vol.Optional(
                    "module_medication", default=modules.get("medication", True)
                ): cv.boolean,
                vol.Optional(
                    "module_training", default=modules.get("training", True)
                ): cv.boolean,
            }
        )

    @staticmethod
    def gps_config_schema(existing_config: Dict[str, Any] | None = None) -> vol.Schema:
        """Build schema for GPS configuration."""
        defaults = existing_config or {}

        return vol.Schema(
            {
                vol.Optional(
                    "gps_enabled", default=defaults.get("enabled", True)
                ): cv.boolean,
                vol.Optional(
                    "gps_accuracy_filter",
                    default=defaults.get("accuracy_filter", GPS_MIN_ACCURACY),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=1000)),
                vol.Optional(
                    "gps_distance_filter",
                    default=defaults.get("distance_filter", GPS_POINT_FILTER_DISTANCE),
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                vol.Optional(
                    "gps_update_interval", default=defaults.get("update_interval", 30)
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                vol.Optional(
                    "auto_start_walk", default=defaults.get("auto_start_walk", False)
                ): cv.boolean,
                vol.Optional(
                    "auto_end_walk", default=defaults.get("auto_end_walk", True)
                ): cv.boolean,
                vol.Optional(
                    "route_recording", default=defaults.get("route_recording", True)
                ): cv.boolean,
                vol.Optional(
                    "route_history_days", default=defaults.get("route_history_days", 90)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
            }
        )

    @staticmethod
    def geofence_config_schema(
        existing_config: Dict[str, Any] | None = None,
        home_lat: float = 0.0,
        home_lon: float = 0.0,
    ) -> vol.Schema:
        """Build schema for geofence configuration."""
        defaults = existing_config or {}

        def validate_geofence_coords(value):
            """Custom validator for geofence coordinates."""
            if isinstance(value, dict):
                lat = value.get("geofence_lat", home_lat)
                lon = value.get("geofence_lon", home_lon)
            else:
                lat = lon = value
            return ConfigValidator.validate_coordinates(lat, lon)

        return vol.Schema(
            {
                vol.Optional(
                    "geofencing_enabled",
                    default=defaults.get("geofencing_enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "geofence_lat", default=defaults.get("geofence_lat", home_lat)
                ): vol.Coerce(float),
                vol.Optional(
                    "geofence_lon", default=defaults.get("geofence_lon", home_lon)
                ): vol.Coerce(float),
                vol.Optional(
                    "geofence_radius_m", default=defaults.get("geofence_radius_m", 150)
                ): ConfigValidator.validate_radius,
                vol.Optional(
                    "geofence_alerts_enabled",
                    default=defaults.get("geofence_alerts_enabled", True),
                ): cv.boolean,
                vol.Optional(
                    "use_home_location",
                    default=defaults.get("use_home_location", False),
                ): cv.boolean,
                vol.Optional(
                    "multiple_zones", default=defaults.get("multiple_zones", False)
                ): cv.boolean,
                vol.Optional(
                    "zone_detection_mode",
                    default=defaults.get("zone_detection_mode", "home_assistant"),
                ): vol.In(["home_assistant", "custom", "both"]),
            }
        )

    @staticmethod
    def notification_config_schema(
        existing_config: Dict[str, Any] | None = None,
    ) -> vol.Schema:
        """Build schema for notification configuration."""
        defaults = existing_config or {}

        return vol.Schema(
            {
                vol.Optional(
                    "notifications_enabled", default=defaults.get("enabled", True)
                ): cv.boolean,
                vol.Optional(
                    "quiet_hours_enabled",
                    default=defaults.get("quiet_hours_enabled", False),
                ): cv.boolean,
                vol.Optional(
                    "quiet_start", default=defaults.get("quiet_start", "22:00")
                ): ConfigValidator.validate_time_string,
                vol.Optional(
                    "quiet_end", default=defaults.get("quiet_end", "07:00")
                ): ConfigValidator.validate_time_string,
                vol.Optional(
                    "reminder_repeat_min",
                    default=defaults.get(
                        "reminder_repeat_min", DEFAULT_REMINDER_REPEAT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                vol.Optional(
                    "snooze_min", default=defaults.get("snooze_min", DEFAULT_SNOOZE_MIN)
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=60)),
                vol.Optional(
                    "priority_notifications",
                    default=defaults.get("priority_notifications", True),
                ): cv.boolean,
                vol.Optional(
                    "summary_notifications",
                    default=defaults.get("summary_notifications", True),
                ): cv.boolean,
                vol.Optional(
                    "notification_channels",
                    default=defaults.get(
                        "notification_channels", ["mobile", "persistent"]
                    ),
                ): ConfigValidator.validate_notification_channels,
            }
        )


class ErrorHandler:
    """Handle and format validation errors for user display."""

    ERROR_TRANSLATIONS = {
        "dog_id": {
            "empty": "invalid_dog_id",
            "invalid_characters": "invalid_dog_id",
            "too_short": "invalid_dog_id",
            "too_long": "invalid_dog_id",
            "starts_invalid": "invalid_dog_id",
        },
        "dog_name": {
            "empty": "invalid_dog_name",
            "too_short": "invalid_dog_name",
            "too_long": "invalid_dog_name",
            "invalid_characters": "invalid_dog_name",
        },
        "dog_age": {
            "invalid_number": "invalid_age",
            "out_of_range": "invalid_age",
        },
        "dog_weight": {
            "invalid_number": "invalid_weight",
            "out_of_range": "invalid_weight",
        },
        "coordinates": {
            "invalid_number": "invalid_coordinates",
            "out_of_range": "invalid_coordinates",
        },
        "time": {
            "invalid_format": "invalid_time",
            "invalid_values": "invalid_time",
        },
        "notification_channels": {
            "empty": "invalid_notifications",
            "invalid": "invalid_notifications",
        },
    }

    @classmethod
    def format_validation_error(cls, error: ValidationError) -> str:
        """Format validation error for Home Assistant error display.

        Args:
            error: The validation error to format

        Returns:
            Error key for translation
        """
        if error.field:
            field_errors = cls.ERROR_TRANSLATIONS.get(error.field, {})

            # Try to match specific error patterns
            error_msg = error.message.lower()

            if "empty" in error_msg or "cannot be empty" in error_msg:
                return field_errors.get("empty", "invalid_input")
            elif "invalid" in error_msg or "cannot contain" in error_msg:
                return field_errors.get("invalid_characters", "invalid_input")
            elif "too short" in error_msg or "at least" in error_msg:
                return field_errors.get("too_short", "invalid_input")
            elif "too long" in error_msg or "at most" in error_msg:
                return field_errors.get("too_long", "invalid_input")
            elif "range" in error_msg or "between" in error_msg:
                return field_errors.get("out_of_range", "invalid_input")
            elif "format" in error_msg:
                return field_errors.get("invalid_format", "invalid_input")
            else:
                return "invalid_input"

        return "invalid_input"

    @classmethod
    def validate_and_handle_errors(
        cls, data: Dict[str, Any], schema: vol.Schema
    ) -> tuple[Dict[str, Any], Dict[str, str]]:
        """Validate data and return results with formatted errors.

        Args:
            data: Data to validate
            schema: Validation schema

        Returns:
            Tuple of (validated_data, errors_dict)
        """
        errors = {}
        validated_data = {}

        try:
            validated_data = schema(data)
        except vol.MultipleInvalid as ex:
            for error in ex.errors:
                field_path = (
                    ".".join(str(p) for p in error.path) if error.path else "base"
                )

                if isinstance(error, vol.Invalid):
                    if hasattr(error, "msg"):
                        errors[field_path] = error.msg
                    else:
                        errors[field_path] = str(error)
                else:
                    errors[field_path] = str(error)
        except vol.Invalid as ex:
            errors["base"] = str(ex)
        except ValidationError as ex:
            error_key = cls.format_validation_error(ex)
            field = ex.field or "base"
            errors[field] = error_key
        except Exception as ex:
            _LOGGER.error("Unexpected validation error: %s", ex)
            errors["base"] = "validation_failed"

        return validated_data, errors


class DataSanitizer:
    """Sanitize and normalize configuration data."""

    @staticmethod
    def sanitize_dog_config(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize dog configuration data.

        Args:
            data: Raw dog configuration data

        Returns:
            Sanitized configuration data
        """
        sanitized = {}

        # Sanitize basic fields
        if "dog_id" in data:
            try:
                sanitized["dog_id"] = ConfigValidator.validate_dog_id(data["dog_id"])
            except ValidationError:
                pass  # Will be caught by schema validation

        if "dog_name" in data:
            try:
                sanitized["dog_name"] = ConfigValidator.validate_dog_name(
                    data["dog_name"]
                )
            except ValidationError:
                pass

        # Copy other fields as-is for schema validation
        for key in ["dog_breed", "dog_age", "dog_weight", "dog_size"]:
            if key in data:
                sanitized[key] = data[key]

        # Copy module settings
        for key in data:
            if key.startswith("module_"):
                sanitized[key] = bool(data[key])

        return sanitized

    @staticmethod
    def sanitize_time_settings(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize time-related settings.

        Args:
            data: Raw time configuration data

        Returns:
            Sanitized time data
        """
        sanitized = dict(data)

        # Sanitize time fields
        time_fields = ["quiet_start", "quiet_end", "reset_time"]
        for field in time_fields:
            if field in sanitized and sanitized[field]:
                # Ensure proper time format
                time_str = str(sanitized[field]).strip()
                if len(time_str) == 5 and time_str.count(":") == 1:
                    time_str += ":00"  # Add seconds if missing
                sanitized[field] = time_str

        return sanitized

    @staticmethod
    def sanitize_numeric_ranges(data: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize numeric range values.

        Args:
            data: Raw numeric data

        Returns:
            Sanitized numeric data
        """
        sanitized = dict(data)

        # Define range constraints
        ranges = {
            "gps_accuracy_filter": (1, 1000),
            "gps_distance_filter": (1, 100),
            "gps_update_interval": (10, 300),
            "geofence_radius_m": (MIN_SAFE_ZONE_RADIUS, MAX_SAFE_ZONE_RADIUS),
            "reminder_repeat_min": (5, 120),
            "snooze_min": (5, 60),
            "data_retention_days": (30, 1095),
        }

        for field, (min_val, max_val) in ranges.items():
            if field in sanitized:
                try:
                    value = float(sanitized[field])
                    sanitized[field] = max(min_val, min(max_val, int(value)))
                except (ValueError, TypeError):
                    pass  # Will be caught by schema validation

        return sanitized


def create_comprehensive_validator() -> Callable[
    [Dict[str, Any], str], tuple[Dict[str, Any], Dict[str, str]]
]:
    """Create a comprehensive validator function for all config sections.

    Returns:
        Validator function that takes (data, section_type) and returns (validated_data, errors)
    """

    def validate_config_section(
        data: Dict[str, Any], section_type: str
    ) -> tuple[Dict[str, Any], Dict[str, str]]:
        """Validate a configuration section.

        Args:
            data: Configuration data to validate
            section_type: Type of configuration section

        Returns:
            Tuple of (validated_data, errors_dict)
        """
        try:
            # Sanitize data first
            if section_type == "dog":
                sanitized_data = DataSanitizer.sanitize_dog_config(data)
                schema = SchemaBuilder.dog_config_schema()
            elif section_type == "gps":
                sanitized_data = DataSanitizer.sanitize_numeric_ranges(data)
                schema = SchemaBuilder.gps_config_schema()
            elif section_type == "geofence":
                sanitized_data = DataSanitizer.sanitize_numeric_ranges(data)
                schema = SchemaBuilder.geofence_config_schema()
            elif section_type == "notifications":
                sanitized_data = DataSanitizer.sanitize_time_settings(data)
                schema = SchemaBuilder.notification_config_schema()
            else:
                # Default: minimal sanitization
                sanitized_data = data
                schema = vol.Schema(dict)  # Accept anything

            # Validate with schema
            return ErrorHandler.validate_and_handle_errors(sanitized_data, schema)

        except Exception as ex:
            _LOGGER.error("Validation failed for section %s: %s", section_type, ex)
            return {}, {"base": "validation_failed"}

    return validate_config_section
