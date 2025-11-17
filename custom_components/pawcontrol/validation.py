"""Comprehensive input validation framework for PawControl.

Provides validation utilities for all user inputs, service calls,
and configuration data with detailed error reporting.

Quality Scale: Platinum target
Home Assistant: 2025.9.3+
Python: 3.13+
"""

from __future__ import annotations

import re
from numbers import Real
from typing import Any, Final, cast

from . import compat
from .compat import bind_exception_alias, ensure_homeassistant_exception_symbols

ensure_homeassistant_exception_symbols()
ServiceValidationError: type[Exception] = cast(
    type[Exception], compat.ServiceValidationError
)
bind_exception_alias("ServiceValidationError")

# Validation constants
VALID_DOG_ID_PATTERN: Final[str] = r"^[a-zA-Z0-9_-]{1,50}$"
VALID_EMAIL_PATTERN: Final[str] = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
VALID_PHONE_PATTERN: Final[str] = r"^\+?[1-9]\d{1,14}$"

MIN_WEIGHT_KG: Final[float] = 0.5
MAX_WEIGHT_KG: Final[float] = 100.0

MIN_AGE_MONTHS: Final[int] = 1
MAX_AGE_MONTHS: Final[int] = 300  # 25 years

MIN_PORTION_GRAMS: Final[float] = 10.0
MAX_PORTION_GRAMS: Final[float] = 5000.0

MIN_LATITUDE: Final[float] = -90.0
MAX_LATITUDE: Final[float] = 90.0
MIN_LONGITUDE: Final[float] = -180.0
MAX_LONGITUDE: Final[float] = 180.0

MIN_ACCURACY_METERS: Final[float] = 0.0
MAX_ACCURACY_METERS: Final[float] = 1000.0

MIN_TEMPERATURE_CELSIUS: Final[float] = 35.0
MAX_TEMPERATURE_CELSIUS: Final[float] = 42.0

MIN_DURATION_MINUTES: Final[int] = 1
MAX_DURATION_MINUTES: Final[int] = 480

MIN_GEOFENCE_RADIUS: Final[float] = 5.0
MAX_GEOFENCE_RADIUS: Final[float] = 5000.0


class ValidationError(Exception):
    """Validation error with detailed context.

    Provides structured error information for debugging and user feedback.
    """

    def __init__(
        self,
        field: str,
        value: Any,
        constraint: str,
        suggestion: str | None = None,
    ) -> None:
        """Initialize validation error.

        Args:
            field: Field name that failed validation
            value: Value that was provided
            constraint: Description of the validation constraint
            suggestion: Optional suggestion for fixing the error
        """
        self.field = field
        self.value = value
        self.constraint = constraint
        self.suggestion = suggestion

        message = f"Validation failed for '{field}': {constraint}"
        if suggestion:
            message += f". {suggestion}"

        super().__init__(message)


def _coerce_float(field: str, value: Any) -> float:
    """Convert a value to float while providing helpful validation errors."""

    if isinstance(value, bool):
        raise ValidationError(
            field,
            value,
            "Must be numeric",
            "Use digits like 12.5 instead of true/false",
        )

    if isinstance(value, Real):
        return float(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(
                field,
                value,
                "Must be numeric",
                "Provide a number such as 12.5",
            )
        try:
            return float(stripped)
        except ValueError as err:
            raise ValidationError(
                field,
                value,
                "Must be numeric",
                "Use digits with an optional decimal, for example 12.5",
            ) from err

    raise ValidationError(
        field,
        value,
        "Must be numeric",
        f"Received {type(value).__name__}",
    )


def _coerce_int(field: str, value: Any) -> int:
    """Convert a value to int while validating fractional input."""

    if isinstance(value, bool):
        raise ValidationError(
            field,
            value,
            "Must be a whole number",
            "Provide digits like 15 instead of true/false",
        )

    if isinstance(value, int):
        return value

    if isinstance(value, Real):
        float_value = float(value)
        if float_value.is_integer():
            return int(float_value)
        raise ValidationError(
            field,
            value,
            "Must be a whole number",
            f"Received fractional value: {value}",
        )

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(
                field,
                value,
                "Must be a whole number",
                "Provide digits such as 15",
            )

        try:
            return int(stripped)
        except ValueError:
            try:
                float_value = float(stripped)
            except ValueError as err:
                raise ValidationError(
                    field,
                    value,
                    "Must be a whole number",
                    "Use digits without decimals, for example 15",
                ) from err

            if not float_value.is_integer():
                raise ValidationError(
                    field,
                    value,
                    "Must be a whole number",
                    f"Received fractional value: {float_value}",
                ) from None

            return int(float_value)

    raise ValidationError(
        field,
        value,
        "Must be a whole number",
        f"Received {type(value).__name__}",
    )


class InputValidator:
    """Comprehensive input validation for PawControl.

    Provides static methods for validating all types of user inputs
    with detailed error reporting and security checks.
    """

    @staticmethod
    def validate_dog_id(dog_id: Any, required: bool = True) -> str | None:
        """Validate and sanitize dog identifier.

        Args:
            dog_id: Dog identifier to validate
            required: Whether the field is required

        Returns:
            Validated dog ID or None if not required and empty

        Raises:
            ValidationError: If validation fails
        """
        if dog_id is None or dog_id == "":
            if required:
                raise ValidationError(
                    "dog_id",
                    dog_id,
                    "Dog ID is required",
                    "Provide a valid dog identifier",
                )
            return None

        if not isinstance(dog_id, str):
            raise ValidationError(
                "dog_id",
                dog_id,
                "Must be a string",
                f"Received {type(dog_id).__name__}",
            )

        dog_id = dog_id.strip()

        if not dog_id:
            if required:
                raise ValidationError(
                    "dog_id",
                    dog_id,
                    "Cannot be empty or whitespace only",
                    "Provide a valid identifier",
                )
            return None

        if len(dog_id) > 50:
            raise ValidationError(
                "dog_id",
                dog_id,
                "Maximum 50 characters",
                f"Current length: {len(dog_id)}",
            )

        if not re.match(VALID_DOG_ID_PATTERN, dog_id):
            raise ValidationError(
                "dog_id",
                dog_id,
                "Only alphanumeric characters, underscore, and hyphen allowed",
                "Use only: a-z, A-Z, 0-9, _, -",
            )

        return dog_id

    @staticmethod
    def validate_dog_name(name: Any, required: bool = True) -> str | None:
        """Validate dog name.

        Args:
            name: Dog name to validate
            required: Whether the field is required

        Returns:
            Validated name or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if name is None or name == "":
            if required:
                raise ValidationError(
                    "dog_name",
                    name,
                    "Dog name is required",
                    "Provide a display name for the dog",
                )
            return None

        if not isinstance(name, str):
            raise ValidationError(
                "dog_name", name, "Must be a string", f"Received {type(name).__name__}"
            )

        name = name.strip()

        if not name:
            if required:
                raise ValidationError(
                    "dog_name", name, "Cannot be empty", "Provide a display name"
                )
            return None

        if len(name) > 100:
            raise ValidationError(
                "dog_name",
                name,
                "Maximum 100 characters",
                f"Current length: {len(name)}",
            )

        return name

    @staticmethod
    def validate_weight(
        weight: Any,
        required: bool = True,
        min_kg: float = MIN_WEIGHT_KG,
        max_kg: float = MAX_WEIGHT_KG,
    ) -> float | None:
        """Validate dog weight in kilograms.

        Args:
            weight: Weight value to validate
            required: Whether the field is required
            min_kg: Minimum allowed weight
            max_kg: Maximum allowed weight

        Returns:
            Validated weight or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if weight is None:
            if required:
                raise ValidationError(
                    "weight",
                    weight,
                    "Weight is required",
                    "Provide dog weight in kilograms",
                )
            return None

        weight = _coerce_float("weight", weight)

        if weight <= 0:
            raise ValidationError(
                "weight", weight, "Must be positive", "Weight must be greater than 0"
            )

        if weight < min_kg:
            raise ValidationError(
                "weight",
                weight,
                f"Minimum weight is {min_kg} kg",
                f"Provided: {weight} kg",
            )

        if weight > max_kg:
            raise ValidationError(
                "weight",
                weight,
                f"Maximum weight is {max_kg} kg",
                f"Provided: {weight} kg - unusually large for a dog",
            )

        return weight

    @staticmethod
    def validate_age_months(
        age: Any,
        required: bool = False,
        min_months: int = MIN_AGE_MONTHS,
        max_months: int = MAX_AGE_MONTHS,
    ) -> int | None:
        """Validate dog age in months.

        Args:
            age: Age value to validate
            required: Whether the field is required
            min_months: Minimum allowed age
            max_months: Maximum allowed age

        Returns:
            Validated age or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if age is None:
            if required:
                raise ValidationError(
                    "age_months", age, "Age is required", "Provide dog age in months"
                )
            return None

        age = _coerce_int("age_months", age)

        if age < min_months:
            raise ValidationError(
                "age_months",
                age,
                f"Minimum age is {min_months} months",
                f"Provided: {age} months",
            )

        if age > max_months:
            raise ValidationError(
                "age_months",
                age,
                f"Maximum age is {max_months} months ({max_months // 12} years)",
                f"Provided: {age} months - unusually old",
            )

        return age

    @staticmethod
    def validate_gps_coordinates(
        latitude: Any,
        longitude: Any,
    ) -> tuple[float, float]:
        """Validate GPS coordinates.

        Args:
            latitude: Latitude value
            longitude: Longitude value

        Returns:
            Tuple of validated (latitude, longitude)

        Raises:
            ValidationError: If validation fails
        """
        if latitude is None:
            raise ValidationError(
                "latitude",
                latitude,
                "Latitude is required",
                "Provide GPS latitude coordinate",
            )

        if longitude is None:
            raise ValidationError(
                "longitude",
                longitude,
                "Longitude is required",
                "Provide GPS longitude coordinate",
            )

        latitude = _coerce_float("latitude", latitude)
        longitude = _coerce_float("longitude", longitude)

        if not MIN_LATITUDE <= latitude <= MAX_LATITUDE:
            raise ValidationError(
                "latitude",
                latitude,
                f"Must be between {MIN_LATITUDE} and {MAX_LATITUDE}",
                f"Provided: {latitude}",
            )

        if not MIN_LONGITUDE <= longitude <= MAX_LONGITUDE:
            raise ValidationError(
                "longitude",
                longitude,
                f"Must be between {MIN_LONGITUDE} and {MAX_LONGITUDE}",
                f"Provided: {longitude}",
            )

        return latitude, longitude

    @staticmethod
    def validate_gps_accuracy(
        accuracy: Any,
        required: bool = False,
    ) -> float | None:
        """Validate GPS accuracy in meters.

        Args:
            accuracy: Accuracy value
            required: Whether the field is required

        Returns:
            Validated accuracy or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if accuracy is None:
            if required:
                raise ValidationError(
                    "accuracy",
                    accuracy,
                    "GPS accuracy is required",
                    "Provide accuracy in meters",
                )
            return None

        accuracy = _coerce_float("accuracy", accuracy)

        if accuracy < MIN_ACCURACY_METERS:
            raise ValidationError(
                "accuracy",
                accuracy,
                f"Minimum accuracy is {MIN_ACCURACY_METERS} meters",
                f"Provided: {accuracy}",
            )

        if accuracy > MAX_ACCURACY_METERS:
            raise ValidationError(
                "accuracy",
                accuracy,
                f"Maximum accuracy is {MAX_ACCURACY_METERS} meters",
                f"Provided: {accuracy} - unusually inaccurate",
            )

        return accuracy

    @staticmethod
    def validate_portion_size(
        amount: Any,
        required: bool = True,
    ) -> float | None:
        """Validate food portion size in grams.

        Args:
            amount: Portion amount
            required: Whether the field is required

        Returns:
            Validated amount or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if amount is None:
            if required:
                raise ValidationError(
                    "amount",
                    amount,
                    "Portion amount is required",
                    "Provide amount in grams",
                )
            return None

        amount = _coerce_float("amount", amount)

        if amount <= 0:
            raise ValidationError(
                "amount",
                amount,
                "Must be positive",
                "Portion size must be greater than 0",
            )

        if amount < MIN_PORTION_GRAMS:
            raise ValidationError(
                "amount",
                amount,
                f"Minimum portion is {MIN_PORTION_GRAMS} grams",
                f"Provided: {amount} grams - unusually small",
            )

        if amount > MAX_PORTION_GRAMS:
            raise ValidationError(
                "amount",
                amount,
                f"Maximum portion is {MAX_PORTION_GRAMS} grams",
                f"Provided: {amount} grams - unusually large for one meal",
            )

        return amount

    @staticmethod
    def validate_temperature(
        temperature: Any,
        required: bool = False,
    ) -> float | None:
        """Validate body temperature in Celsius.

        Args:
            temperature: Temperature value
            required: Whether the field is required

        Returns:
            Validated temperature or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if temperature is None:
            if required:
                raise ValidationError(
                    "temperature",
                    temperature,
                    "Temperature is required",
                    "Provide body temperature in Celsius",
                )
            return None

        temperature = _coerce_float("temperature", temperature)

        if not MIN_TEMPERATURE_CELSIUS <= temperature <= MAX_TEMPERATURE_CELSIUS:
            raise ValidationError(
                "temperature",
                temperature,
                f"Normal range: {MIN_TEMPERATURE_CELSIUS}-{MAX_TEMPERATURE_CELSIUS}°C",
                f"Provided: {temperature}°C - seek veterinary attention if accurate",
            )

        return temperature

    @staticmethod
    def validate_text_input(
        text: Any,
        field_name: str,
        required: bool = False,
        max_length: int = 500,
        min_length: int = 0,
    ) -> str | None:
        """Validate and sanitize text input.

        Args:
            text: Text to validate
            field_name: Name of the field for error reporting
            required: Whether the field is required
            max_length: Maximum allowed length
            min_length: Minimum required length

        Returns:
            Sanitized text or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if text is None or text == "":
            if required:
                raise ValidationError(
                    field_name, text, f"{field_name} is required", "Provide text input"
                )
            return None

        if not isinstance(text, str):
            raise ValidationError(
                field_name, text, "Must be text", f"Received {type(text).__name__}"
            )

        text = text.strip()

        if not text and required:
            raise ValidationError(
                field_name,
                text,
                "Cannot be empty or whitespace",
                "Provide meaningful text",
            )

        if len(text) < min_length:
            raise ValidationError(
                field_name,
                text,
                f"Minimum length: {min_length} characters",
                f"Provided: {len(text)} characters",
            )

        if len(text) > max_length:
            raise ValidationError(
                field_name,
                text,
                f"Maximum length: {max_length} characters",
                f"Provided: {len(text)} characters",
            )

        # Remove control characters (except newlines)
        return "".join(char for char in text if ord(char) >= 32 or char == "\n")

    @staticmethod
    def validate_duration(
        duration: Any,
        required: bool = False,
        min_minutes: int = MIN_DURATION_MINUTES,
        max_minutes: int = MAX_DURATION_MINUTES,
    ) -> int | None:
        """Validate duration in minutes.

        Args:
            duration: Duration value
            required: Whether the field is required
            min_minutes: Minimum duration
            max_minutes: Maximum duration

        Returns:
            Validated duration or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if duration is None:
            if required:
                raise ValidationError(
                    "duration",
                    duration,
                    "Duration is required",
                    "Provide duration in minutes",
                )
            return None

        duration = _coerce_int("duration", duration)

        if duration < min_minutes:
            raise ValidationError(
                "duration",
                duration,
                f"Minimum duration: {min_minutes} minutes",
                f"Provided: {duration} minutes",
            )

        if duration > max_minutes:
            raise ValidationError(
                "duration",
                duration,
                f"Maximum duration: {max_minutes} minutes ({max_minutes // 60} hours)",
                f"Provided: {duration} minutes - unusually long",
            )

        return duration

    @staticmethod
    def validate_geofence_radius(
        radius: Any,
        required: bool = True,
    ) -> float | None:
        """Validate geofence radius in meters.

        Args:
            radius: Radius value
            required: Whether the field is required

        Returns:
            Validated radius or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if radius is None:
            if required:
                raise ValidationError(
                    "radius",
                    radius,
                    "Geofence radius is required",
                    "Provide radius in meters",
                )
            return None

        radius = _coerce_float("radius", radius)

        if radius <= 0:
            raise ValidationError(
                "radius", radius, "Must be positive", "Radius must be greater than 0"
            )

        if radius < MIN_GEOFENCE_RADIUS:
            raise ValidationError(
                "radius",
                radius,
                f"Minimum radius: {MIN_GEOFENCE_RADIUS} meters",
                f"Provided: {radius} meters - too small for reliable detection",
            )

        if radius > MAX_GEOFENCE_RADIUS:
            raise ValidationError(
                "radius",
                radius,
                f"Maximum radius: {MAX_GEOFENCE_RADIUS} meters ({MAX_GEOFENCE_RADIUS / 1000} km)",
                f"Provided: {radius} meters - unusually large",
            )

        return radius

    @staticmethod
    def validate_email(
        email: Any,
        required: bool = False,
    ) -> str | None:
        """Validate email address.

        Args:
            email: Email address to validate
            required: Whether the field is required

        Returns:
            Validated email or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if email is None or email == "":
            if required:
                raise ValidationError(
                    "email",
                    email,
                    "Email address is required",
                    "Provide valid email address",
                )
            return None

        if not isinstance(email, str):
            raise ValidationError(
                "email", email, "Must be text", f"Received {type(email).__name__}"
            )

        email = email.strip().lower()

        if not re.match(VALID_EMAIL_PATTERN, email):
            raise ValidationError(
                "email", email, "Invalid email format", "Use format: user@example.com"
            )

        if len(email) > 254:  # RFC 5321
            raise ValidationError(
                "email",
                email,
                "Email too long (max 254 characters)",
                f"Provided: {len(email)} characters",
            )

        return email

    @staticmethod
    def validate_enum_value(
        value: Any,
        field_name: str,
        valid_values: list[str] | set[str],
        required: bool = True,
    ) -> str | None:
        """Validate enum/choice value.

        Args:
            value: Value to validate
            field_name: Field name for error reporting
            valid_values: List/set of valid values
            required: Whether the field is required

        Returns:
            Validated value or None if not required

        Raises:
            ValidationError: If validation fails
        """
        if value is None or value == "":
            if required:
                raise ValidationError(
                    field_name,
                    value,
                    f"{field_name} is required",
                    f"Choose from: {', '.join(valid_values)}",
                )
            return None

        if not isinstance(value, str):
            value = str(value)

        value = value.strip().lower()

        # Case-insensitive matching
        valid_values_lower = {v.lower() for v in valid_values}

        if value not in valid_values_lower:
            raise ValidationError(
                field_name,
                value,
                "Invalid value",
                f"Valid options: {', '.join(sorted(valid_values))}",
            )

        # Return original case from valid_values
        for valid in valid_values:
            if valid.lower() == value:
                return valid

        return value


def convert_validation_error_to_service_error(
    error: ValidationError,
) -> Exception:
    """Convert ValidationError to Home Assistant ServiceValidationError.

    Args:
        error: ValidationError to convert

    Returns:
        ServiceValidationError for Home Assistant
    """
    return ServiceValidationError(str(error))
