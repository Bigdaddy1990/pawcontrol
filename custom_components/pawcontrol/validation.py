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
from .exceptions import ValidationError as PawControlValidationError

ensure_homeassistant_exception_symbols()
ServiceValidationError: type[Exception] = cast(
  type[Exception],
  compat.ServiceValidationError,
)
bind_exception_alias("ServiceValidationError")

ValidationError = PawControlValidationError

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


class InputCoercionError(ValueError):
  """Raised when raw input cannot be coerced to the expected type."""

  def __init__(self, field: str, value: Any, message: str) -> None:
    super().__init__(message)
    self.field = field
    self.value = value
    self.message = message


def _is_empty(value: Any) -> bool:
  """Return True when a value should be treated as missing."""

  return value is None or (isinstance(value, str) and not value.strip())


def _coerce_float_with_constraint(
  field: str,
  value: Any,
  constraint: str,
) -> float:
  """Coerce a float while normalising validation constraints."""

  try:
    return coerce_float(field, value)
  except InputCoercionError as err:
    raise ValidationError(field, value, constraint) from err


def normalize_dog_id(raw_id: Any) -> str:
  """Normalize a dog identifier for flow and service validation."""

  if raw_id is None:
    return ""

  if not isinstance(raw_id, str):
    raise InputCoercionError("dog_id", raw_id, "Must be a string")

  dog_id_raw = raw_id.strip().lower()
  return re.sub(r"\s+", "_", dog_id_raw)


def coerce_float(field: str, value: Any) -> float:
  """Convert a value to float while raising typed coercion errors."""

  if isinstance(value, bool):
    raise InputCoercionError(field, value, "Must be numeric")

  if isinstance(value, Real):
    return float(value)

  if isinstance(value, str):
    stripped = value.strip()
    if not stripped:
      raise InputCoercionError(field, value, "Must be numeric")
    try:
      return float(stripped)
    except ValueError as err:
      raise InputCoercionError(
        field,
        value,
        "Must be numeric",
      ) from err

  raise InputCoercionError(
    field,
    value,
    "Must be numeric",
  )


def coerce_int(field: str, value: Any) -> int:
  """Convert a value to int while validating fractional input."""

  if isinstance(value, bool):
    raise InputCoercionError(field, value, "Must be a whole number")

  if isinstance(value, int):
    return value

  if isinstance(value, Real):
    float_value = float(value)
    if float_value.is_integer():
      return int(float_value)
    raise InputCoercionError(
      field,
      value,
      "Must be a whole number",
    )

  if isinstance(value, str):
    stripped = value.strip()
    if not stripped:
      raise InputCoercionError(
        field,
        value,
        "Must be a whole number",
      )

    try:
      return int(stripped)
    except ValueError:
      try:
        float_value = float(stripped)
      except ValueError as err:
        raise InputCoercionError(
          field,
          value,
          "Must be a whole number",
        ) from err

      if not float_value.is_integer():
        raise InputCoercionError(
          field,
          value,
          "Must be a whole number",
        ) from None

      return int(float_value)

  raise InputCoercionError(
    field,
    value,
    "Must be a whole number",
  )


def _coerce_float(field: str, value: Any) -> float:
  """Convert a value to float while providing helpful validation errors."""

  try:
    return coerce_float(field, value)
  except InputCoercionError as err:
    raise ValidationError(
      field,
      value,
      "Must be numeric",
    ) from err


def _coerce_int(field: str, value: Any) -> int:
  """Convert a value to int while validating fractional input."""

  try:
    return coerce_int(field, value)
  except InputCoercionError as err:
    raise ValidationError(
      field,
      value,
      "Must be a whole number",
    ) from err


def validate_dog_name(
  name: Any,
  *,
  required: bool = True,
  min_length: int = 1,
  max_length: int = 100,
) -> str | None:
  """Validate dog name input and return a trimmed value."""

  if name is None or name == "":
    if required:
      raise ValidationError(
        "dog_name",
        name,
        "Dog name is required",
      )
    return None

  if not isinstance(name, str):
    raise ValidationError(
      "dog_name",
      name,
      "Must be a string",
    )

  trimmed = name.strip()
  if not trimmed:
    if required:
      raise ValidationError(
        "dog_name",
        name,
        "Cannot be empty",
      )
    return None

  if len(trimmed) < min_length:
    raise ValidationError(
      "dog_name",
      trimmed,
      f"Minimum length is {min_length} characters",
      min_value=min_length,
    )

  if len(trimmed) > max_length:
    raise ValidationError(
      "dog_name",
      trimmed,
      f"Maximum length is {max_length} characters",
      max_value=max_length,
    )

  return trimmed


def validate_coordinate(
  value: Any,
  *,
  field: str,
  minimum: float,
  maximum: float,
  required: bool = True,
) -> float | None:
  """Validate a single coordinate within bounds."""

  if _is_empty(value):
    if required:
      raise ValidationError(
        field,
        value,
        "coordinate_required",
      )
    return None

  coordinate = _coerce_float_with_constraint(
    field,
    value,
    "coordinate_not_numeric",
  )
  if coordinate < minimum or coordinate > maximum:
    raise ValidationError(
      field,
      coordinate,
      "coordinate_out_of_range",
      min_value=minimum,
      max_value=maximum,
    )
  return coordinate


def validate_interval(
  value: Any,
  *,
  field: str,
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
) -> int:
  """Validate timer/interval values within bounds."""

  if value is None:
    if default is not None:
      return default
    if required:
      raise ValidationError(
        field,
        value,
        "Interval is required",
      )
    return minimum if clamp else 0

  interval = _coerce_int(field, value)
  if interval < minimum:
    if clamp:
      return minimum
    raise ValidationError(
      field,
      interval,
      f"Minimum interval is {minimum}",
      min_value=minimum,
      max_value=maximum,
    )
  if interval > maximum:
    if clamp:
      return maximum
    raise ValidationError(
      field,
      interval,
      f"Maximum interval is {maximum}",
      min_value=minimum,
      max_value=maximum,
    )
  return interval


def validate_float_range(
  value: Any,
  *,
  field: str,
  minimum: float,
  maximum: float,
  default: float | None = None,
  clamp: bool = False,
  required: bool = False,
) -> float:
  """Validate a floating-point range within bounds."""

  if value is None:
    if default is not None:
      return default
    if required:
      raise ValidationError(
        field,
        value,
        "Value is required",
      )
    return minimum if clamp else 0.0

  candidate = _coerce_float(field, value)
  if candidate < minimum:
    if clamp:
      return minimum
    raise ValidationError(
      field,
      candidate,
      f"Minimum value is {minimum}",
      min_value=minimum,
      max_value=maximum,
    )
  if candidate > maximum:
    if clamp:
      return maximum
    raise ValidationError(
      field,
      candidate,
      f"Maximum value is {maximum}",
      min_value=minimum,
      max_value=maximum,
    )
  return candidate


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
    return validate_dog_name(
      name,
      required=required,
      min_length=1,
      max_length=100,
    )

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
        "weight",
        weight,
        "Must be positive",
        "Weight must be greater than 0",
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
          "age_months",
          age,
          "Age is required",
          "Provide dog age in months",
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
    *,
    latitude_field: str = "latitude",
    longitude_field: str = "longitude",
  ) -> tuple[float, float]:
    """Validate GPS coordinates.

    Args:
        latitude: Latitude value
        longitude: Longitude value
        latitude_field: Field name for latitude validation
        longitude_field: Field name for longitude validation

    Returns:
        Tuple of validated (latitude, longitude)

    Raises:
        ValidationError: If validation fails
    """
    latitude = validate_coordinate(
      latitude,
      field=latitude_field,
      minimum=MIN_LATITUDE,
      maximum=MAX_LATITUDE,
    )
    longitude = validate_coordinate(
      longitude,
      field=longitude_field,
      minimum=MIN_LONGITUDE,
      maximum=MAX_LONGITUDE,
    )
    return cast(float, latitude), cast(float, longitude)

  @staticmethod
  def validate_gps_accuracy(
    accuracy: Any,
    required: bool = False,
    field: str = "accuracy",
    min_value: float = MIN_ACCURACY_METERS,
    max_value: float = MAX_ACCURACY_METERS,
  ) -> float | None:
    """Validate GPS accuracy in meters.

    Args:
        accuracy: Accuracy value
        required: Whether the field is required
        field: Field name for validation errors
        min_value: Minimum allowed accuracy
        max_value: Maximum allowed accuracy

    Returns:
        Validated accuracy or None if not required

    Raises:
        ValidationError: If validation fails
    """
    if _is_empty(accuracy):
      if required:
        raise ValidationError(
          field,
          accuracy,
          "gps_accuracy_required",
        )
      return None

    accuracy = _coerce_float_with_constraint(
      field,
      accuracy,
      "gps_accuracy_not_numeric",
    )

    if accuracy < min_value:
      raise ValidationError(
        field,
        accuracy,
        "gps_accuracy_out_of_range",
        min_value=min_value,
        max_value=max_value,
      )

    if accuracy > max_value:
      raise ValidationError(
        field,
        accuracy,
        "gps_accuracy_out_of_range",
        min_value=min_value,
        max_value=max_value,
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
          field_name,
          text,
          f"{field_name} is required",
          "Provide text input",
        )
      return None

    if not isinstance(text, str):
      raise ValidationError(
        field_name,
        text,
        "Must be text",
        f"Received {type(text).__name__}",
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
        )
      return None

    return validate_interval(
      duration,
      field="duration",
      minimum=min_minutes,
      maximum=max_minutes,
      required=required,
    )

  @staticmethod
  def validate_geofence_radius(
    radius: Any,
    required: bool = True,
    field: str = "radius",
    min_value: float = MIN_GEOFENCE_RADIUS,
    max_value: float = MAX_GEOFENCE_RADIUS,
  ) -> float | None:
    """Validate geofence radius in meters.

    Args:
        radius: Radius value
        required: Whether the field is required
        field: Field name for validation errors
        min_value: Minimum allowed radius
        max_value: Maximum allowed radius

    Returns:
        Validated radius or None if not required

    Raises:
        ValidationError: If validation fails
    """
    if _is_empty(radius):
      if required:
        raise ValidationError(
          field,
          radius,
          "geofence_radius_required",
        )
      return None

    radius = _coerce_float_with_constraint(
      field,
      radius,
      "geofence_radius_not_numeric",
    )

    if radius < min_value:
      raise ValidationError(
        field,
        radius,
        "geofence_radius_out_of_range",
        min_value=min_value,
        max_value=max_value,
      )

    if radius > max_value:
      raise ValidationError(
        field,
        radius,
        "geofence_radius_out_of_range",
        min_value=min_value,
        max_value=max_value,
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
        "email",
        email,
        "Must be text",
        f"Received {type(email).__name__}",
      )

    email = email.strip().lower()

    if not re.match(VALID_EMAIL_PATTERN, email):
      raise ValidationError(
        "email",
        email,
        "Invalid email format",
        "Use format: user@example.com",
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
