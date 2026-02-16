"""Custom exceptions for Paw Control integration.

This module defines custom exception classes for specific error conditions
that can occur during Paw Control operations. These exceptions provide
clear error messaging, structured error information, and proper error handling
throughout the integration.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from enum import Enum
import traceback
from typing import Any, Final, ParamSpec, TypedDict, TypeVar, Unpack, cast

from homeassistant.exceptions import (
  ConfigEntryAuthFailed as _AuthFailedType,
  HomeAssistantError as HomeAssistantErrorType,
  ServiceValidationError as _ServiceValidationErrorType,
)
from homeassistant.helpers.update_coordinator import (
  CoordinatorUpdateFailed as _UpdateFailedType,
)
from homeassistant.util import dt as dt_util

from .types import ErrorContext, ErrorPayload, GPSLocation, JSONValue

P = ParamSpec("P")
T = TypeVar("T")

ConfigEntryAuthFailed = _AuthFailedType
HomeAssistantError = HomeAssistantErrorType
ServiceValidationError = _ServiceValidationErrorType
UpdateFailed = _UpdateFailedType
CoordinatorUpdateFailed = _UpdateFailedType


class ErrorSeverity(Enum):
  """Error severity levels for better error handling and user experience."""  # noqa: E111

  LOW = "low"  # Minor issues, degraded functionality  # noqa: E111
  MEDIUM = "medium"  # Significant issues, some features unavailable  # noqa: E111
  HIGH = "high"  # Major issues, core functionality affected  # noqa: E111
  CRITICAL = (  # noqa: E111
    "critical"  # System-breaking issues, immediate attention needed
  )


class ErrorCategory(Enum):
  """Error categories for better organization and handling."""  # noqa: E111

  CONFIGURATION = "configuration"  # Configuration and setup errors  # noqa: E111
  DATA = "data"  # Data validation and processing errors  # noqa: E111
  NETWORK = "network"  # Network and connectivity errors  # noqa: E111
  GPS = "gps"  # GPS and location errors  # noqa: E111
  AUTHENTICATION = (  # noqa: E111
    "authentication"  # Authentication and authorization errors
  )
  RATE_LIMIT = "rate_limit"  # Rate limiting errors  # noqa: E111
  STORAGE = "storage"  # Storage and persistence errors  # noqa: E111
  VALIDATION = "validation"  # Input validation errors  # noqa: E111
  BUSINESS_LOGIC = "business_logic"  # Business logic violations  # noqa: E111
  SYSTEM = "system"  # System and resource errors  # noqa: E111


class PawControlErrorKwargs(TypedDict, total=False):
  """Optional keyword arguments supported by PawControl error helpers."""  # noqa: E111

  severity: ErrorSeverity  # noqa: E111
  recovery_suggestions: list[str]  # noqa: E111
  user_message: str  # noqa: E111
  technical_details: str | None  # noqa: E111
  timestamp: datetime  # noqa: E111


def _serialise_json_value(value: object) -> JSONValue:
  """Convert arbitrary objects to JSON-compatible values for error payloads."""  # noqa: E111

  if value is None or isinstance(value, bool | int | float | str):  # noqa: E111
    return cast(JSONValue, value)

  if isinstance(value, datetime):  # noqa: E111
    return value.isoformat()

  if isinstance(value, Mapping):  # noqa: E111
    serialised_mapping: dict[str, JSONValue] = {}
    for key, mapping_value in value.items():
      serialised_mapping[str(key)] = _serialise_json_value(mapping_value)  # noqa: E111
    return serialised_mapping

  if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):  # noqa: E111
    return [_serialise_json_value(item) for item in value]

  return str(value)  # noqa: E111


def _ensure_error_context(context: Mapping[str, object] | None) -> ErrorContext:
  """Normalise error context payloads to JSON-compatible dictionaries."""  # noqa: E111

  if not context:  # noqa: E111
    return {}

  normalised: ErrorContext = {}  # noqa: E111
  for key, value in context.items():  # noqa: E111
    serialised = _serialise_json_value(value)
    if serialised is not None:
      normalised[str(key)] = serialised  # noqa: E111

  return normalised  # noqa: E111


class PawControlError(HomeAssistantErrorType):
  """Base exception for all Paw Control related errors with enhanced features.

  This base class provides structured error information, contextual data,
  and recovery suggestions for better error handling and user experience.
  """  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    error_code: str | None = None,
    severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    category: ErrorCategory = ErrorCategory.SYSTEM,
    context: Mapping[str, object] | None = None,
    recovery_suggestions: list[str] | None = None,
    user_message: str | None = None,
    technical_details: str | None = None,
    timestamp: datetime | None = None,
  ) -> None:
    """Initialize the enhanced Paw Control exception.

    Args:
        message: Human-readable error message for developers
        error_code: Unique error code for programmatic handling
        severity: Error severity level
        category: Error category for organization
        context: Additional context data for debugging
        recovery_suggestions: List of suggested recovery actions
        user_message: User-friendly error message
        technical_details: Technical details for debugging
        timestamp: When the error occurred
    """
    super().__init__(message)

    self.error_code = error_code or self.__class__.__name__.lower()
    self.severity = severity
    self.category = category
    self.context = _ensure_error_context(context)
    self.recovery_suggestions = list(recovery_suggestions or [])
    self.user_message = user_message or message
    self.technical_details = technical_details
    self.timestamp = timestamp or dt_util.utcnow()
    self.stack_trace = traceback.format_stack()

  def to_dict(self) -> ErrorPayload:  # noqa: E111
    """Convert exception to dictionary for serialization.

    Returns:
        Dictionary representation of the exception
    """
    return {
      "error_code": self.error_code,
      "message": str(self),
      "user_message": self.user_message,
      "severity": self.severity.value,
      "category": self.category.value,
      "context": self.context,
      "recovery_suggestions": self.recovery_suggestions,
      "technical_details": self.technical_details,
      "timestamp": self.timestamp.isoformat(),
      "exception_type": self.__class__.__name__,
    }

  def add_context(self, key: str, value: object) -> PawControlError:  # noqa: E111
    """Add context information to the exception.

    Args:
        key: Context key
        value: Context value

    Returns:
        Self for method chaining
    """
    self.context[str(key)] = _serialise_json_value(value)
    return self

  def add_recovery_suggestion(self, suggestion: str) -> PawControlError:  # noqa: E111
    """Add a recovery suggestion to the exception.

    Args:
        suggestion: Recovery suggestion text

    Returns:
        Self for method chaining
    """
    self.recovery_suggestions.append(suggestion)
    return self

  def with_user_message(self, message: str) -> PawControlError:  # noqa: E111
    """Set user-friendly error message.

    Args:
        message: User-friendly message

    Returns:
        Self for method chaining
    """
    self.user_message = message
    return self


class ConfigurationError(PawControlError):
  """Exception raised for configuration-related errors."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    setting: str,
    value: Any = None,
    reason: str | None = None,
    expected_type: type | None = None,
    valid_values: list[Any] | None = None,
  ) -> None:
    """Initialize configuration error.

    Args:
        setting: The configuration setting that's invalid
        value: The invalid value
        reason: Reason why the configuration is invalid
        expected_type: Expected data type
        valid_values: List of valid values
    """
    if value is not None and reason:
      message = f"Invalid configuration for '{setting}' (value: {value}): {reason}"  # noqa: E111
    elif value is not None:
      message = f"Invalid configuration for '{setting}': {value}"  # noqa: E111
    elif reason:
      message = f"Invalid configuration for '{setting}': {reason}"  # noqa: E111
    else:
      message = f"Invalid configuration for '{setting}'"  # noqa: E111

    super().__init__(
      message,
      error_code="configuration_error",
      severity=ErrorSeverity.HIGH,
      category=ErrorCategory.CONFIGURATION,
      context={
        "setting": setting,
        "value": value,
        "expected_type": expected_type.__name__ if expected_type else None,
        "valid_values": valid_values,
      },
      recovery_suggestions=[
        "Check the integration configuration in Home Assistant",
        "Verify the setting value is within acceptable range",
        "Restart Home Assistant after configuration changes",
      ],
    )

    self.setting = setting
    self.value = value
    self.expected_type = expected_type
    self.valid_values = valid_values


class PawControlSetupError(PawControlError):
  """Exception raised when integration setup fails."""  # noqa: E111

  def __init__(self, message: str, error_code: str = "setup_failed") -> None:  # noqa: E111
    """Initialize setup error."""
    super().__init__(
      message,
      error_code=error_code,
      severity=ErrorSeverity.CRITICAL,
      category=ErrorCategory.CONFIGURATION,
    )


class ReauthRequiredError(PawControlError):
  """Exception raised when reauthentication is required."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    context: Mapping[str, object] | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code="reauth_required",
      severity=ErrorSeverity.HIGH,
      category=ErrorCategory.AUTHENTICATION,
      context=context,
      recovery_suggestions=["Restart the reauthentication flow in Home Assistant"],
      user_message="Reauthentication is required for Paw Control.",
    )


class ReconfigureRequiredError(PawControlError):
  """Exception raised when reconfiguration is required."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    context: Mapping[str, object] | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code="reconfigure_required",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.CONFIGURATION,
      context=context,
      recovery_suggestions=["Start the reconfigure flow in Home Assistant"],
      user_message="Reconfiguration is required for Paw Control.",
    )


class RepairRequiredError(PawControlError):
  """Exception raised when a repairs flow should be surfaced."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    context: Mapping[str, object] | None = None,
  ) -> None:
    super().__init__(
      message,
      error_code="repair_required",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.SYSTEM,
      context=context,
      recovery_suggestions=["Review the Repairs panel in Home Assistant"],
      user_message="A repair action is required for Paw Control.",
    )


class DogNotFoundError(PawControlError):
  """Exception raised when a dog with the specified ID is not found."""  # noqa: E111

  def __init__(self, dog_id: str, available_dogs: list[str] | None = None) -> None:  # noqa: E111
    """Initialize dog not found error.

    Args:
        dog_id: The dog ID that was not found
        available_dogs: List of available dog IDs
    """
    message = f"Dog with ID '{dog_id}' not found"
    if available_dogs:
      message += f" (available: {', '.join(available_dogs)})"  # noqa: E111

    super().__init__(
      message,
      error_code="dog_not_found",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.DATA,
      context={
        "dog_id": dog_id,
        "available_dogs": available_dogs or [],
      },
      recovery_suggestions=[
        "Check if the dog ID is spelled correctly",
        "Verify the dog is configured in the integration",
        f"Available dogs: {', '.join(available_dogs) if available_dogs else 'None'}",
      ],
      user_message=f"The dog '{dog_id}' was not found. Please check the dog ID.",
    )

    self.dog_id = dog_id
    self.available_dogs = available_dogs or []


class GPSError(PawControlError):
  """Base class for GPS-related errors."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    dog_id: str | None = None,
    location: GPSLocation | None = None,
    *,
    error_code: str | None = None,
    context: Mapping[str, object] | None = None,
    **kwargs: Unpack[PawControlErrorKwargs],
  ) -> None:
    """Initialize GPS error.

    Args:
        message: Error message
        dog_id: Dog ID associated with GPS error
        location: GPS location data if available
        **kwargs: Additional arguments for parent class
    """
    location_context: ErrorContext | None = (
      _ensure_error_context(
        cast(Mapping[str, object], location.__dict__),
      )
      if location
      else None
    )
    context_payload: dict[str, object] = {"dog_id": dog_id}
    if location_context is not None:
      context_payload["location"] = location_context  # noqa: E111
    if context:
      context_payload.update(context)  # noqa: E111
    super().__init__(
      message,
      error_code=error_code,
      category=ErrorCategory.GPS,
      context=context_payload,
      **kwargs,
    )

    self.dog_id = dog_id
    self.location = location


class InvalidCoordinatesError(GPSError):
  """Exception raised when invalid GPS coordinates are provided."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    latitude: float | None = None,
    longitude: float | None = None,
    dog_id: str | None = None,
  ) -> None:
    """Initialize invalid coordinates error.

    Args:
        latitude: The invalid latitude value
        longitude: The invalid longitude value
        dog_id: Dog ID if applicable
    """
    if latitude is not None and longitude is not None:
      message = f"Invalid GPS coordinates: ({latitude}, {longitude})"  # noqa: E111
      details = "Latitude must be between -90 and 90, longitude between -180 and 180"  # noqa: E111
    else:
      message = "Invalid GPS coordinates provided"  # noqa: E111
      details = "GPS coordinates are missing or malformed"  # noqa: E111

    super().__init__(
      message,
      dog_id=dog_id,
      error_code="invalid_coordinates",
      severity=ErrorSeverity.MEDIUM,
      context={
        "latitude": latitude,
        "longitude": longitude,
        "latitude_valid": -90 <= latitude <= 90 if latitude is not None else False,
        "longitude_valid": -180 <= longitude <= 180 if longitude is not None else False,
      },
      recovery_suggestions=[
        "Verify GPS coordinates are in decimal degrees format",
        "Check that latitude is between -90 and 90",
        "Check that longitude is between -180 and 180",
        "Ensure GPS device is functioning properly",
      ],
      technical_details=details,
    )

    self.latitude = latitude
    self.longitude = longitude


class GPSUnavailableError(GPSError):
  """Exception raised when GPS data is not available."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    dog_id: str,
    reason: str | None = None,
    last_known_location: GPSLocation | None = None,
  ) -> None:
    """Initialize GPS unavailable error.

    Args:
        dog_id: The dog ID for which GPS is unavailable
        reason: Reason why GPS is unavailable
        last_known_location: Last known GPS location if available
    """
    if reason:
      message = f"GPS data is not available for dog '{dog_id}': {reason}"  # noqa: E111
    else:
      message = f"GPS data is not available for dog '{dog_id}'"  # noqa: E111

    super().__init__(
      message,
      dog_id=dog_id,
      location=last_known_location,
      error_code="gps_unavailable",
      severity=ErrorSeverity.LOW,
      recovery_suggestions=[
        "Check if GPS tracking is enabled for this dog",
        "Verify GPS device battery and connectivity",
        "Ensure GPS module is configured correctly",
        "Wait for GPS signal to stabilize if outdoors",
      ],
      user_message=f"GPS location for {dog_id} is currently unavailable",
    )

    self.reason = reason
    self.last_known_location = last_known_location


class WalkError(PawControlError):
  """Base class for walk-related errors."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    dog_id: str,
    walk_id: str | None = None,
    *,
    error_code: str | None = None,
    context: Mapping[str, object] | None = None,
    **kwargs: Unpack[PawControlErrorKwargs],
  ) -> None:
    """Initialize walk error.

    Args:
        message: Error message
        dog_id: Dog ID
        walk_id: Walk ID if applicable
        **kwargs: Additional arguments for parent class
    """
    base_context: dict[str, object] = {
      "dog_id": dog_id,
      "walk_id": walk_id,
    }
    if context:
      base_context.update(context)  # noqa: E111
    super().__init__(
      message,
      error_code=error_code,
      category=ErrorCategory.BUSINESS_LOGIC,
      context=base_context,
      **kwargs,
    )

    self.dog_id = dog_id
    self.walk_id = walk_id


class WalkNotInProgressError(WalkError):
  """Exception raised when trying to end a walk that isn't in progress."""  # noqa: E111

  def __init__(self, dog_id: str, last_walk_time: datetime | None = None) -> None:  # noqa: E111
    """Initialize walk not in progress error.

    Args:
        dog_id: The dog ID for which no walk is in progress
        last_walk_time: Time of last completed walk
    """
    message = f"No walk is currently in progress for dog '{dog_id}'"

    super().__init__(
      message,
      dog_id=dog_id,
      error_code="walk_not_in_progress",
      severity=ErrorSeverity.LOW,
      context={
        "last_walk_time": last_walk_time.isoformat() if last_walk_time else None,
      },
      recovery_suggestions=[
        "Start a new walk before trying to end one",
        "Check if a walk was already ended",
        "Verify the correct dog ID is being used",
      ],
      user_message=f"No walk is currently active for {dog_id}",
    )

    self.last_walk_time = last_walk_time


class WalkAlreadyInProgressError(WalkError):
  """Exception raised when trying to start a walk that's already in progress."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    dog_id: str,
    walk_id: str | None = None,
    start_time: datetime | None = None,
  ) -> None:
    """Initialize walk already in progress error.

    Args:
        dog_id: The dog ID for which a walk is already in progress
        walk_id: The current walk ID
        start_time: When the current walk started
    """
    message = f"A walk is already in progress for dog '{dog_id}'"

    super().__init__(
      message,
      dog_id=dog_id,
      walk_id=walk_id,
      error_code="walk_already_in_progress",
      severity=ErrorSeverity.LOW,
      context={
        "current_walk_id": walk_id,
        "start_time": start_time.isoformat() if start_time else None,
      },
      recovery_suggestions=[
        "End the current walk before starting a new one",
        "Continue tracking the current walk",
        "Check if the walk was started accidentally",
      ],
      user_message=f"A walk for {dog_id} is already in progress",
    )

    self.start_time = start_time


class ValidationError(PawControlError):
  """Exception raised when data validation fails."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    field: str,
    value: Any = None,
    constraint: str | None = None,
    min_value: Any = None,
    max_value: Any = None,
    valid_values: list[Any] | None = None,
  ) -> None:
    """Initialize validation error.

    Args:
        field: The field that failed validation
        value: The invalid value
        constraint: The validation constraint that was violated
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        valid_values: List of valid values
    """
    if value is not None and constraint:
      message = f"Validation failed for '{field}' (value: {value}): {constraint}"  # noqa: E111
    elif value is not None:
      message = f"Validation failed for '{field}': invalid value {value}"  # noqa: E111
    elif constraint:
      message = f"Validation failed for '{field}': {constraint}"  # noqa: E111
    else:
      message = f"Validation failed for '{field}'"  # noqa: E111

    # Build recovery suggestions based on constraints
    suggestions = [f"Check the value for '{field}'"]
    if min_value is not None:
      suggestions.append(f"Value must be at least {min_value}")  # noqa: E111
    if max_value is not None:
      suggestions.append(f"Value must be at most {max_value}")  # noqa: E111
    if valid_values:
      suggestions.append(  # noqa: E111
        f"Valid values: {', '.join(map(str, valid_values))}",
      )

    super().__init__(
      message,
      error_code="validation_error",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.VALIDATION,
      context={
        "field": field,
        "value": value,
        "constraint": constraint,
        "min_value": min_value,
        "max_value": max_value,
        "valid_values": valid_values,
      },
      recovery_suggestions=suggestions,
      user_message=f"Invalid value for {field.replace('_', ' ')}",
    )

    self.field = field
    self.value = value
    self.constraint = constraint
    self.min_value = min_value
    self.max_value = max_value
    self.valid_values = valid_values


class FlowValidationError(PawControlError):
  """Exception raised when configuration or options flow validation fails."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    *,
    field_errors: Mapping[str, str] | None = None,
    base_errors: Sequence[str] | None = None,
  ) -> None:
    """Initialize flow validation error.

    Args:
        field_errors: Field-specific errors keyed by schema field name
        base_errors: Base-level errors for form-level issues
    """
    field_errors = dict(field_errors or {})
    base_errors = list(base_errors or [])

    message_parts: list[str] = []
    message_parts.extend(field_errors.values())
    message_parts.extend(base_errors)
    message = "; ".join(message_parts) or "Flow validation failed"

    super().__init__(
      message,
      error_code="flow_validation_error",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.VALIDATION,
      context={
        "field_errors": field_errors,
        "base_errors": base_errors,
      },
      recovery_suggestions=[
        "Review the highlighted fields and correct any invalid values",
      ],
      user_message="Please review the form and correct the highlighted fields.",
    )

    self.field_errors = field_errors
    self.base_errors = base_errors

  def as_form_errors(self) -> dict[str, str]:  # noqa: E111
    """Return errors in the format expected by Home Assistant forms."""

    if self.field_errors:
      return dict(self.field_errors)  # noqa: E111

    if self.base_errors:
      return {"base": self.base_errors[0]}  # noqa: E111

    return {"base": "validation_error"}


class InvalidMealTypeError(ValidationError):
  """Exception raised when an invalid meal type is specified."""  # noqa: E111

  def __init__(self, meal_type: str, valid_types: list[str] | None = None) -> None:  # noqa: E111
    """Initialize invalid meal type error.

    Args:
        meal_type: The invalid meal type
        valid_types: List of valid meal types
    """
    super().__init__(
      field="meal_type",
      value=meal_type,
      constraint="Must be a valid meal type",
      valid_values=valid_types,
    )

    self.meal_type = meal_type
    self.valid_types = valid_types or []


class InvalidWeightError(ValidationError):
  """Exception raised when an invalid weight value is provided."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    weight: float,
    min_weight: float | None = None,
    max_weight: float | None = None,
  ) -> None:
    """Initialize invalid weight error.

    Args:
        weight: The invalid weight value
        min_weight: Minimum allowed weight
        max_weight: Maximum allowed weight
    """
    constraint = "Weight must be a positive number"
    if min_weight is not None and max_weight is not None:
      constraint = f"Weight must be between {min_weight}kg and {max_weight}kg"  # noqa: E111
    elif min_weight is not None:
      constraint = f"Weight must be at least {min_weight}kg"  # noqa: E111
    elif max_weight is not None:
      constraint = f"Weight must be at most {max_weight}kg"  # noqa: E111

    super().__init__(
      field="weight",
      value=weight,
      constraint=constraint,
      min_value=min_weight,
      max_value=max_weight,
    )

    self.weight = weight
    self.min_weight = min_weight
    self.max_weight = max_weight


class StorageError(PawControlError):
  """Exception raised when storage operations fail."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    operation: str,
    reason: str | None = None,
    storage_type: str = "file",
    retry_possible: bool = True,
  ) -> None:
    """Initialize storage error.

    Args:
        operation: The storage operation that failed
        reason: Reason for the failure
        storage_type: Type of storage (file, database, etc.)
        retry_possible: Whether the operation can be retried
    """
    if reason:
      message = f"Storage {operation} failed: {reason}"  # noqa: E111
    else:
      message = f"Storage {operation} failed"  # noqa: E111

    suggestions = []
    if retry_possible:
      suggestions.append("Retry the operation")  # noqa: E111
    suggestions.extend(
      [
        "Check available disk space",
        "Verify file permissions",
        "Ensure storage directory exists",
      ],
    )

    super().__init__(
      message,
      error_code="storage_error",
      severity=ErrorSeverity.HIGH,
      category=ErrorCategory.STORAGE,
      context={
        "operation": operation,
        "storage_type": storage_type,
        "retry_possible": retry_possible,
      },
      recovery_suggestions=suggestions,
      user_message="Data storage operation failed",
    )

    self.operation = operation
    self.storage_type = storage_type
    self.retry_possible = retry_possible


class RateLimitError(PawControlError):
  """Exception raised when rate limits are exceeded."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    action: str,
    limit: str | None = None,
    retry_after: int | None = None,
    current_count: int | None = None,
    max_count: int | None = None,
  ) -> None:
    """Initialize rate limit error.

    Args:
        action: The action that was rate limited
        limit: Description of the rate limit
        retry_after: Seconds until retry is allowed
        current_count: Current request count
        max_count: Maximum allowed requests
    """
    if limit and retry_after:
      message = (  # noqa: E111
        f"Rate limit exceeded for {action} ({limit}). Retry after {retry_after} seconds"
      )
    elif limit:
      message = f"Rate limit exceeded for {action} ({limit})"  # noqa: E111
    elif retry_after:
      message = f"Rate limit exceeded for {action}. Retry after {retry_after} seconds"  # noqa: E111
    else:
      message = f"Rate limit exceeded for {action}"  # noqa: E111

    suggestions = []
    if retry_after:
      suggestions.append(f"Wait {retry_after} seconds before retrying")  # noqa: E111
    suggestions.extend(
      [
        "Reduce the frequency of requests",
        "Check if rate limiting can be adjusted",
        "Consider implementing request batching",
      ],
    )

    super().__init__(
      message,
      error_code="rate_limit_exceeded",
      severity=ErrorSeverity.LOW,
      category=ErrorCategory.RATE_LIMIT,
      context={
        "action": action,
        "limit": limit,
        "retry_after": retry_after,
        "current_count": current_count,
        "max_count": max_count,
      },
      recovery_suggestions=suggestions,
      user_message="Too many requests. Please wait before trying again.",
    )

    self.action = action
    self.limit = limit
    self.retry_after = retry_after
    self.current_count = current_count
    self.max_count = max_count


class NetworkError(PawControlError):
  """Exception raised when network operations fail."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    endpoint: str | None = None,
    operation: str | None = None,
    retryable: bool = True,
  ) -> None:
    """Initialize network error."""

    suggestions = [
      "Check your internet connection",
      "Verify the PawControl service is reachable",
    ]
    if retryable:
      suggestions.append("Try the operation again later")  # noqa: E111

    super().__init__(
      message,
      error_code="network_error",
      severity=ErrorSeverity.MEDIUM if retryable else ErrorSeverity.HIGH,
      category=ErrorCategory.NETWORK,
      context={
        "endpoint": endpoint,
        "operation": operation,
        "retryable": retryable,
      },
      recovery_suggestions=suggestions,
      user_message="Network communication with PawControl failed",
    )

    self.endpoint = endpoint
    self.operation = operation
    self.retryable = retryable


class ServiceUnavailableError(NetworkError):
  """Exception raised when an upstream PawControl service is unavailable."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    message: str,
    *,
    service_name: str | None = None,
    endpoint: str | None = None,
    operation: str | None = None,
  ) -> None:
    """Initialize service unavailable error."""

    super().__init__(
      message,
      endpoint=endpoint,
      operation=operation,
      retryable=True,
    )
    self.error_code = "service_unavailable"
    self.user_message = "PawControl service is temporarily unavailable"
    if service_name is not None:
      self.context["service_name"] = service_name  # noqa: E111
    self.service_name = service_name


class AuthenticationError(PawControlError):
  """Exception raised when authentication validation fails."""  # noqa: E111

  def __init__(self, message: str, *, service: str | None = None) -> None:  # noqa: E111
    """Initialize authentication error."""

    super().__init__(
      message,
      error_code="authentication_error",
      severity=ErrorSeverity.HIGH,
      category=ErrorCategory.AUTHENTICATION,
      context={"service": service},
      recovery_suggestions=[
        "Verify credentials and shared secrets",
        "Reauthenticate the integration",
      ],
      user_message="Authentication with PawControl failed",
    )
    self.service = service


class NotificationError(PawControlError):
  """Exception raised when notification sending fails."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    notification_type: str,
    reason: str | None = None,
    channel: str | None = None,
    fallback_available: bool = False,
  ) -> None:
    """Initialize notification error.

    Args:
        notification_type: The type of notification
        reason: Reason for the failure
        channel: Notification channel that failed
        fallback_available: Whether fallback notification is available
    """
    if reason:
      message = f"Failed to send {notification_type} notification: {reason}"  # noqa: E111
    else:
      message = f"Failed to send {notification_type} notification"  # noqa: E111

    suggestions = []
    if fallback_available:
      suggestions.append("Fallback notification method will be used")  # noqa: E111
    suggestions.extend(
      [
        "Check notification service configuration",
        "Verify network connectivity",
        "Test notification channels manually",
      ],
    )

    super().__init__(
      message,
      error_code="notification_send_failed",
      severity=ErrorSeverity.LOW if fallback_available else ErrorSeverity.MEDIUM,
      category=ErrorCategory.NETWORK,
      context={
        "notification_type": notification_type,
        "channel": channel,
        "fallback_available": fallback_available,
      },
      recovery_suggestions=suggestions,
      user_message="Notification could not be sent",
    )

    self.notification_type = notification_type
    self.channel = channel
    self.fallback_available = fallback_available


# Additional specialized exceptions following the same pattern...


class DataExportError(PawControlError):
  """Exception raised when data export fails."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    export_type: str,
    reason: str | None = None,
    format_type: str = "json",
    partial_export: bool = False,
  ) -> None:
    """Initialize data export error."""
    message = f"Failed to export {export_type} data"
    if reason:
      message += f": {reason}"  # noqa: E111

    super().__init__(
      message,
      error_code="data_export_failed",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.DATA,
      context={
        "export_type": export_type,
        "format_type": format_type,
        "partial_export": partial_export,
      },
      recovery_suggestions=[
        "Try exporting in a different format",
        "Check available disk space",
        "Verify export permissions",
      ],
    )


class DataImportError(PawControlError):
  """Exception raised when data import fails."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    import_type: str,
    reason: str | None = None,
    line_number: int | None = None,
    recoverable: bool = True,
  ) -> None:
    """Initialize data import error."""
    message = f"Failed to import {import_type} data"
    if reason:
      message += f": {reason}"  # noqa: E111
    if line_number:
      message += f" at line {line_number}"  # noqa: E111

    super().__init__(
      message,
      error_code="data_import_failed",
      severity=ErrorSeverity.MEDIUM,
      category=ErrorCategory.DATA,
      context={
        "import_type": import_type,
        "line_number": line_number,
        "recoverable": recoverable,
      },
    )


# Exception mapping with enhanced lookup capabilities
EXCEPTION_MAP: Final[dict[str, type[PawControlError]]] = {
  "configuration_error": ConfigurationError,
  "dog_not_found": DogNotFoundError,
  "invalid_coordinates": InvalidCoordinatesError,
  "gps_unavailable": GPSUnavailableError,
  "walk_not_in_progress": WalkNotInProgressError,
  "walk_already_in_progress": WalkAlreadyInProgressError,
  "validation_error": ValidationError,
  "invalid_meal_type": InvalidMealTypeError,
  "invalid_weight": InvalidWeightError,
  "storage_error": StorageError,
  "rate_limit_exceeded": RateLimitError,
  "notification_send_failed": NotificationError,
  "network_error": NetworkError,
  "authentication_error": AuthenticationError,
  "service_unavailable": ServiceUnavailableError,
  "data_export_failed": DataExportError,
  "data_import_failed": DataImportError,
  "reauth_required": ReauthRequiredError,
  "reconfigure_required": ReconfigureRequiredError,
  "repair_required": RepairRequiredError,
  "setup_failed": PawControlSetupError,
}


def get_exception_class(error_code: str) -> type[PawControlError]:
  """Get the exception class for a given error code.

  Args:
      error_code: The error code to look up

  Returns:
      The corresponding exception class

  Raises:
      KeyError: If the error code is not found
  """  # noqa: E111
  if error_code not in EXCEPTION_MAP:  # noqa: E111
    raise KeyError(f"Unknown error code: {error_code}")

  return EXCEPTION_MAP[error_code]  # noqa: E111


def raise_from_error_code(
  error_code: str,
  message: str,
  *,
  context: Mapping[str, object] | None = None,
  category: ErrorCategory | None = None,
  **kwargs: Unpack[PawControlErrorKwargs],
) -> None:
  """Raise an exception based on an error code.

  Args:
      error_code: The error code to raise
      message: The error message
      **kwargs: Additional arguments for the exception

  Raises:
      PawControlError: The appropriate exception for the error code
  """  # noqa: E111
  exception_class = EXCEPTION_MAP.get(error_code, PawControlError)  # noqa: E111
  if category is not None and context is not None:  # noqa: E111
    raise exception_class(
      message,
      error_code=error_code,
      category=category,
      context=context,
      **kwargs,
    )
  if category is not None:  # noqa: E111
    raise exception_class(
      message,
      error_code=error_code,
      category=category,
      **kwargs,
    )
  if context is not None:  # noqa: E111
    raise exception_class(
      message,
      error_code=error_code,
      context=context,
      **kwargs,
    )
  raise exception_class(message, error_code=error_code, **kwargs)  # noqa: E111


def handle_exception_gracefully[**P, T](
  func: Callable[P, T],
  default_return: T | None = None,
  *,
  log_errors: bool = True,
  reraise_critical: bool = True,
) -> Callable[P, T | None]:
  """Decorator for graceful exception handling with logging.

  Args:
      func: Function to wrap
      default_return: Default return value on error
      log_errors: Whether to log exceptions
      reraise_critical: Whether to reraise critical errors

  Returns:
      Callable that wraps ``func`` and handles exceptions gracefully
  """  # noqa: E111

  def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:  # noqa: E111
    try:
      return func(*args, **kwargs)  # noqa: E111
    except PawControlError as e:
      if log_errors:  # noqa: E111
        import logging

        logger = logging.getLogger(__name__)
        logger.error(
          "PawControl error in %s: %s",
          func.__name__,
          e.to_dict(),
        )

      if reraise_critical and e.severity == ErrorSeverity.CRITICAL:  # noqa: E111
        raise

      return default_return  # noqa: E111
    except Exception:
      if log_errors:  # noqa: E111
        import logging

        logger = logging.getLogger(__name__)
        logger.exception("Unexpected error in %s", func.__name__)

      if reraise_critical:  # noqa: E111
        raise

      return default_return  # noqa: E111

  return wrapper  # noqa: E111


def create_error_context(
  dog_id: str | None = None,
  operation: str | None = None,
  **additional_context: object,
) -> ErrorContext:
  """Create standardized error context dictionary.

  Args:
      dog_id: Dog ID if applicable
      operation: Operation being performed
      **additional_context: Additional context data

  Returns:
      Structured error context dictionary
  """  # noqa: E111
  context: ErrorContext = {"timestamp": dt_util.utcnow().isoformat()}  # noqa: E111

  if dog_id is not None:  # noqa: E111
    context["dog_id"] = dog_id
  if operation is not None:  # noqa: E111
    context["operation"] = operation

  for key, value in additional_context.items():  # noqa: E111
    serialised = _serialise_json_value(value)
    if serialised is not None:
      context[str(key)] = serialised  # noqa: E111

  return context  # noqa: E111
