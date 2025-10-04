"""Custom exceptions for Paw Control integration.

This module defines custom exception classes for specific error conditions
that can occur during Paw Control operations. These exceptions provide
clear error messaging, structured error information, and proper error handling
throughout the integration.

Quality Scale: Platinum
Home Assistant: 2025.8.2+
Python: 3.12+
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any, Final

try:
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.util import dt as dt_util
except ModuleNotFoundError:  # pragma: no cover - compatibility shim for tests

    class HomeAssistantError(Exception):
        """Fallback error used when Home Assistant isn't installed."""

    class _DateTimeModule:
        @staticmethod
        def utcnow() -> datetime:
            return datetime.now(datetime.timezone.utc)

    dt_util = _DateTimeModule()

from .types import GPSLocation


class ErrorSeverity(Enum):
    """Error severity levels for better error handling and user experience."""

    LOW = "low"  # Minor issues, degraded functionality
    MEDIUM = "medium"  # Significant issues, some features unavailable
    HIGH = "high"  # Major issues, core functionality affected
    CRITICAL = "critical"  # System-breaking issues, immediate attention needed


class ErrorCategory(Enum):
    """Error categories for better organization and handling."""

    CONFIGURATION = "configuration"  # Configuration and setup errors
    DATA = "data"  # Data validation and processing errors
    NETWORK = "network"  # Network and connectivity errors
    GPS = "gps"  # GPS and location errors
    AUTHENTICATION = "authentication"  # Authentication and authorization errors
    RATE_LIMIT = "rate_limit"  # Rate limiting errors
    STORAGE = "storage"  # Storage and persistence errors
    VALIDATION = "validation"  # Input validation errors
    BUSINESS_LOGIC = "business_logic"  # Business logic violations
    SYSTEM = "system"  # System and resource errors


class PawControlError(HomeAssistantError):
    """Base exception for all Paw Control related errors with enhanced features.

    This base class provides structured error information, contextual data,
    and recovery suggestions for better error handling and user experience.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        context: dict[str, Any] | None = None,
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
        self.context = context or {}
        self.recovery_suggestions = recovery_suggestions or []
        self.user_message = user_message or message
        self.technical_details = technical_details
        self.timestamp = timestamp or dt_util.utcnow()
        self.stack_trace = traceback.format_stack()

    def to_dict(self) -> dict[str, Any]:
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

    def add_context(self, key: str, value: Any) -> PawControlError:
        """Add context information to the exception.

        Args:
            key: Context key
            value: Context value

        Returns:
            Self for method chaining
        """
        self.context[key] = value
        return self

    def add_recovery_suggestion(self, suggestion: str) -> PawControlError:
        """Add a recovery suggestion to the exception.

        Args:
            suggestion: Recovery suggestion text

        Returns:
            Self for method chaining
        """
        self.recovery_suggestions.append(suggestion)
        return self

    def with_user_message(self, message: str) -> PawControlError:
        """Set user-friendly error message.

        Args:
            message: User-friendly message

        Returns:
            Self for method chaining
        """
        self.user_message = message
        return self


class ConfigurationError(PawControlError):
    """Exception raised for configuration-related errors."""

    def __init__(
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
            message = (
                f"Invalid configuration for '{setting}' (value: {value}): {reason}"
            )
        elif value is not None:
            message = f"Invalid configuration for '{setting}': {value}"
        elif reason:
            message = f"Invalid configuration for '{setting}': {reason}"
        else:
            message = f"Invalid configuration for '{setting}'"

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
    """Exception raised when integration setup fails."""

    def __init__(self, message: str, error_code: str = "setup_failed") -> None:
        """Initialize setup error."""
        super().__init__(
            message,
            error_code=error_code,
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.CONFIGURATION,
        )


class DogNotFoundError(PawControlError):
    """Exception raised when a dog with the specified ID is not found."""

    def __init__(self, dog_id: str, available_dogs: list[str] | None = None) -> None:
        """Initialize dog not found error.

        Args:
            dog_id: The dog ID that was not found
            available_dogs: List of available dog IDs
        """
        message = f"Dog with ID '{dog_id}' not found"

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
    """Base class for GPS-related errors."""

    def __init__(
        self,
        message: str,
        dog_id: str | None = None,
        location: GPSLocation | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize GPS error.

        Args:
            message: Error message
            dog_id: Dog ID associated with GPS error
            location: GPS location data if available
            **kwargs: Additional arguments for parent class
        """
        extra_context = kwargs.pop("context", {})
        context = {
            "dog_id": dog_id,
            "location": location.__dict__ if location else None,
            **extra_context,
        }
        super().__init__(
            message,
            category=ErrorCategory.GPS,
            context=context,
            **kwargs,
        )

        self.dog_id = dog_id
        self.location = location


class InvalidCoordinatesError(GPSError):
    """Exception raised when invalid GPS coordinates are provided."""

    def __init__(
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
            message = f"Invalid GPS coordinates: ({latitude}, {longitude})"
            details = (
                "Latitude must be between -90 and 90, longitude between -180 and 180"
            )
        else:
            message = "Invalid GPS coordinates provided"
            details = "GPS coordinates are missing or malformed"

        super().__init__(
            message,
            dog_id=dog_id,
            error_code="invalid_coordinates",
            severity=ErrorSeverity.MEDIUM,
            context={
                "latitude": latitude,
                "longitude": longitude,
                "latitude_valid": -90 <= latitude <= 90
                if latitude is not None
                else False,
                "longitude_valid": -180 <= longitude <= 180
                if longitude is not None
                else False,
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
    """Exception raised when GPS data is not available."""

    def __init__(
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
            message = f"GPS data is not available for dog '{dog_id}': {reason}"
        else:
            message = f"GPS data is not available for dog '{dog_id}'"

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
    """Base class for walk-related errors."""

    def __init__(
        self,
        message: str,
        dog_id: str,
        walk_id: str | None = None,
        *,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize walk error.

        Args:
            message: Error message
            dog_id: Dog ID
            walk_id: Walk ID if applicable
            **kwargs: Additional arguments for parent class
        """
        base_context = {"dog_id": dog_id, "walk_id": walk_id}
        if context:
            base_context.update(context)
        super().__init__(
            message,
            category=ErrorCategory.BUSINESS_LOGIC,
            context=base_context,
            **kwargs,
        )

        self.dog_id = dog_id
        self.walk_id = walk_id


class WalkNotInProgressError(WalkError):
    """Exception raised when trying to end a walk that isn't in progress."""

    def __init__(self, dog_id: str, last_walk_time: datetime | None = None) -> None:
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
                "last_walk_time": last_walk_time.isoformat()
                if last_walk_time
                else None,
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
    """Exception raised when trying to start a walk that's already in progress."""

    def __init__(
        self,
        dog_id: str,
        walk_id: str,
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
    """Exception raised when data validation fails."""

    def __init__(
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
            message = f"Validation failed for '{field}' (value: {value}): {constraint}"
        elif value is not None:
            message = f"Validation failed for '{field}': invalid value {value}"
        elif constraint:
            message = f"Validation failed for '{field}': {constraint}"
        else:
            message = f"Validation failed for '{field}'"

        # Build recovery suggestions based on constraints
        suggestions = [f"Check the value for '{field}'"]
        if min_value is not None:
            suggestions.append(f"Value must be at least {min_value}")
        if max_value is not None:
            suggestions.append(f"Value must be at most {max_value}")
        if valid_values:
            suggestions.append(f"Valid values: {', '.join(map(str, valid_values))}")

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


class InvalidMealTypeError(ValidationError):
    """Exception raised when an invalid meal type is specified."""

    def __init__(self, meal_type: str, valid_types: list[str] | None = None) -> None:
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
    """Exception raised when an invalid weight value is provided."""

    def __init__(
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
            constraint = f"Weight must be between {min_weight}kg and {max_weight}kg"
        elif min_weight is not None:
            constraint = f"Weight must be at least {min_weight}kg"
        elif max_weight is not None:
            constraint = f"Weight must be at most {max_weight}kg"

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
    """Exception raised when storage operations fail."""

    def __init__(
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
            message = f"Storage {operation} failed: {reason}"
        else:
            message = f"Storage {operation} failed"

        suggestions = []
        if retry_possible:
            suggestions.append("Retry the operation")
        suggestions.extend(
            [
                "Check available disk space",
                "Verify file permissions",
                "Ensure storage directory exists",
            ]
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
    """Exception raised when rate limits are exceeded."""

    def __init__(
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
            message = f"Rate limit exceeded for {action} ({limit}). Retry after {retry_after} seconds"
        elif limit:
            message = f"Rate limit exceeded for {action} ({limit})"
        elif retry_after:
            message = (
                f"Rate limit exceeded for {action}. Retry after {retry_after} seconds"
            )
        else:
            message = f"Rate limit exceeded for {action}"

        suggestions = []
        if retry_after:
            suggestions.append(f"Wait {retry_after} seconds before retrying")
        suggestions.extend(
            [
                "Reduce the frequency of requests",
                "Check if rate limiting can be adjusted",
                "Consider implementing request batching",
            ]
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
    """Exception raised when network operations fail."""

    def __init__(
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
            suggestions.append("Try the operation again later")

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


class NotificationError(PawControlError):
    """Exception raised when notification sending fails."""

    def __init__(
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
            message = f"Failed to send {notification_type} notification: {reason}"
        else:
            message = f"Failed to send {notification_type} notification"

        suggestions = []
        if fallback_available:
            suggestions.append("Fallback notification method will be used")
        suggestions.extend(
            [
                "Check notification service configuration",
                "Verify network connectivity",
                "Test notification channels manually",
            ]
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
    """Exception raised when data export fails."""

    def __init__(
        self,
        export_type: str,
        reason: str | None = None,
        format_type: str = "json",
        partial_export: bool = False,
    ) -> None:
        """Initialize data export error."""
        message = f"Failed to export {export_type} data"
        if reason:
            message += f": {reason}"

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
    """Exception raised when data import fails."""

    def __init__(
        self,
        import_type: str,
        reason: str | None = None,
        line_number: int | None = None,
        recoverable: bool = True,
    ) -> None:
        """Initialize data import error."""
        message = f"Failed to import {import_type} data"
        if reason:
            message += f": {reason}"
        if line_number:
            message += f" at line {line_number}"

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
    "data_export_failed": DataExportError,
    "data_import_failed": DataImportError,
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
    """
    if error_code not in EXCEPTION_MAP:
        raise KeyError(f"Unknown error code: {error_code}")

    return EXCEPTION_MAP[error_code]


def raise_from_error_code(
    error_code: str,
    message: str,
    **kwargs: Any,
) -> None:
    """Raise an exception based on an error code.

    Args:
        error_code: The error code to raise
        message: The error message
        **kwargs: Additional arguments for the exception

    Raises:
        PawControlError: The appropriate exception for the error code
    """
    exception_class = EXCEPTION_MAP.get(error_code, PawControlError)
    raise exception_class(message, error_code=error_code, **kwargs)


def handle_exception_gracefully(
    func: Callable[..., Any],
    default_return: Any = None,
    log_errors: bool = True,
    reraise_critical: bool = True,
) -> Callable[..., Any]:
    """Decorator for graceful exception handling with logging.

    Args:
        func: Function to wrap
        default_return: Default return value on error
        log_errors: Whether to log exceptions
        reraise_critical: Whether to reraise critical errors

    Returns:
        Callable that wraps ``func`` and handles exceptions gracefully
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except PawControlError as e:
            if log_errors:
                import logging

                logger = logging.getLogger(__name__)
                logger.error("PawControl error in %s: %s", func.__name__, e.to_dict())

            if reraise_critical and e.severity == ErrorSeverity.CRITICAL:
                raise

            return default_return
        except Exception:
            if log_errors:
                import logging

                logger = logging.getLogger(__name__)
                logger.exception("Unexpected error in %s", func.__name__)

            if reraise_critical:
                raise

            return default_return

    return wrapper


def create_error_context(
    dog_id: str | None = None,
    operation: str | None = None,
    **additional_context: Any,
) -> dict[str, Any]:
    """Create standardized error context dictionary.

    Args:
        dog_id: Dog ID if applicable
        operation: Operation being performed
        **additional_context: Additional context data

    Returns:
        Structured error context dictionary
    """
    context = {
        "timestamp": dt_util.utcnow().isoformat(),
        "dog_id": dog_id,
        "operation": operation,
    }

    context.update(additional_context)
    return {k: v for k, v in context.items() if v is not None}
