"""Custom exceptions for Paw Control integration.

This module defines custom exception classes for specific error conditions
that can occur during Paw Control operations. These exceptions provide
clear error messaging and proper error handling throughout the integration.
"""
from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class PawControlError(HomeAssistantError):
    """Base exception for all Paw Control related errors."""

    def __init__(self, message: str, error_code: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            message: Human-readable error message
            error_code: Optional error code for programmatic handling
        """
        super().__init__(message)
        self.error_code = error_code


class DogNotFoundError(PawControlError):
    """Exception raised when a dog with the specified ID is not found."""

    def __init__(self, dog_id: str) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID that was not found
        """
        super().__init__(
            f"Dog with ID '{dog_id}' not found",
            error_code="dog_not_found"
        )
        self.dog_id = dog_id


class InvalidCoordinatesError(PawControlError):
    """Exception raised when invalid GPS coordinates are provided."""

    def __init__(self, latitude: float | None = None, longitude: float | None = None) -> None:
        """Initialize the exception.
        
        Args:
            latitude: The invalid latitude value
            longitude: The invalid longitude value
        """
        if latitude is not None and longitude is not None:
            message = f"Invalid GPS coordinates: ({latitude}, {longitude})"
        else:
            message = "Invalid GPS coordinates provided"
        
        super().__init__(message, error_code="invalid_coordinates")
        self.latitude = latitude
        self.longitude = longitude


class WalkNotInProgressError(PawControlError):
    """Exception raised when trying to end a walk that isn't in progress."""

    def __init__(self, dog_id: str) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID for which no walk is in progress
        """
        super().__init__(
            f"No walk is currently in progress for dog '{dog_id}'",
            error_code="walk_not_in_progress"
        )
        self.dog_id = dog_id


class WalkAlreadyInProgressError(PawControlError):
    """Exception raised when trying to start a walk that's already in progress."""

    def __init__(self, dog_id: str) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID for which a walk is already in progress
        """
        super().__init__(
            f"A walk is already in progress for dog '{dog_id}'",
            error_code="walk_already_in_progress"
        )
        self.dog_id = dog_id


class InvalidMealTypeError(PawControlError):
    """Exception raised when an invalid meal type is specified."""

    def __init__(self, meal_type: str, valid_types: list[str] | None = None) -> None:
        """Initialize the exception.
        
        Args:
            meal_type: The invalid meal type
            valid_types: List of valid meal types
        """
        if valid_types:
            message = f"Invalid meal type '{meal_type}'. Valid types: {', '.join(valid_types)}"
        else:
            message = f"Invalid meal type '{meal_type}'"
        
        super().__init__(message, error_code="invalid_meal_type")
        self.meal_type = meal_type
        self.valid_types = valid_types


class InvalidWeightError(PawControlError):
    """Exception raised when an invalid weight value is provided."""

    def __init__(self, weight: float, min_weight: float | None = None, max_weight: float | None = None) -> None:
        """Initialize the exception.
        
        Args:
            weight: The invalid weight value
            min_weight: Minimum allowed weight
            max_weight: Maximum allowed weight
        """
        if min_weight is not None and max_weight is not None:
            message = f"Invalid weight {weight}kg. Must be between {min_weight}kg and {max_weight}kg"
        elif min_weight is not None:
            message = f"Invalid weight {weight}kg. Must be at least {min_weight}kg"
        elif max_weight is not None:
            message = f"Invalid weight {weight}kg. Must be at most {max_weight}kg"
        else:
            message = f"Invalid weight {weight}kg. Weight must be a positive number"
        
        super().__init__(message, error_code="invalid_weight")
        self.weight = weight
        self.min_weight = min_weight
        self.max_weight = max_weight


class GroomingNotInProgressError(PawControlError):
    """Exception raised when trying to end grooming that isn't in progress."""

    def __init__(self, dog_id: str) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID for which no grooming is in progress
        """
        super().__init__(
            f"No grooming session is currently in progress for dog '{dog_id}'",
            error_code="grooming_not_in_progress"
        )
        self.dog_id = dog_id


class InvalidDateRangeError(PawControlError):
    """Exception raised when an invalid date range is specified."""

    def __init__(self, start_date: str | None = None, end_date: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            start_date: The start date string
            end_date: The end date string
        """
        if start_date and end_date:
            message = f"Invalid date range: {start_date} to {end_date}"
        else:
            message = "Invalid date range specified"
        
        super().__init__(message, error_code="invalid_date_range")
        self.start_date = start_date
        self.end_date = end_date


class DataExportError(PawControlError):
    """Exception raised when data export fails."""

    def __init__(self, export_type: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            export_type: The type of data being exported
            reason: Optional reason for the failure
        """
        if reason:
            message = f"Failed to export {export_type} data: {reason}"
        else:
            message = f"Failed to export {export_type} data"
        
        super().__init__(message, error_code="data_export_failed")
        self.export_type = export_type
        self.reason = reason


class DataImportError(PawControlError):
    """Exception raised when data import fails."""

    def __init__(self, import_type: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            import_type: The type of data being imported
            reason: Optional reason for the failure
        """
        if reason:
            message = f"Failed to import {import_type} data: {reason}"
        else:
            message = f"Failed to import {import_type} data"
        
        super().__init__(message, error_code="data_import_failed")
        self.import_type = import_type
        self.reason = reason


class NotificationError(PawControlError):
    """Exception raised when notification sending fails."""

    def __init__(self, notification_type: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            notification_type: The type of notification
            reason: Optional reason for the failure
        """
        if reason:
            message = f"Failed to send {notification_type} notification: {reason}"
        else:
            message = f"Failed to send {notification_type} notification"
        
        super().__init__(message, error_code="notification_send_failed")
        self.notification_type = notification_type
        self.reason = reason


class GPSUnavailableError(PawControlError):
    """Exception raised when GPS data is not available."""

    def __init__(self, dog_id: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID for which GPS is unavailable
            reason: Optional reason why GPS is unavailable
        """
        if reason:
            message = f"GPS data is not available for dog '{dog_id}': {reason}"
        else:
            message = f"GPS data is not available for dog '{dog_id}'"
        
        super().__init__(message, error_code="gps_unavailable")
        self.dog_id = dog_id
        self.reason = reason


class ModuleNotEnabledError(PawControlError):
    """Exception raised when a required module is not enabled."""

    def __init__(self, dog_id: str, module: str, action: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            dog_id: The dog ID for which the module is not enabled
            module: The module that is not enabled
            action: Optional action that required the module
        """
        if action:
            message = f"Cannot {action} for dog '{dog_id}': {module} module is not enabled"
        else:
            message = f"The {module} module is not enabled for dog '{dog_id}'"
        
        super().__init__(message, error_code="module_not_enabled")
        self.dog_id = dog_id
        self.module = module
        self.action = action


class ConfigurationError(PawControlError):
    """Exception raised when there's a configuration error."""

    def __init__(self, setting: str, value: str | None = None, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            setting: The configuration setting that's invalid
            value: The invalid value
            reason: Optional reason why the configuration is invalid
        """
        if value and reason:
            message = f"Invalid configuration for '{setting}' (value: {value}): {reason}"
        elif value:
            message = f"Invalid configuration for '{setting}': {value}"
        elif reason:
            message = f"Invalid configuration for '{setting}': {reason}"
        else:
            message = f"Invalid configuration for '{setting}'"
        
        super().__init__(message, error_code="configuration_error")
        self.setting = setting
        self.value = value
        self.reason = reason


class ServiceUnavailableError(PawControlError):
    """Exception raised when an external service is unavailable."""

    def __init__(self, service: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            service: The service that is unavailable
            reason: Optional reason why the service is unavailable
        """
        if reason:
            message = f"Service '{service}' is unavailable: {reason}"
        else:
            message = f"Service '{service}' is unavailable"
        
        super().__init__(message, error_code="service_unavailable")
        self.service = service
        self.reason = reason


class ValidationError(PawControlError):
    """Exception raised when data validation fails."""

    def __init__(self, field: str, value: str | None = None, constraint: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            field: The field that failed validation
            value: The invalid value
            constraint: The validation constraint that was violated
        """
        if value and constraint:
            message = f"Validation failed for '{field}' (value: {value}): {constraint}"
        elif value:
            message = f"Validation failed for '{field}': invalid value {value}"
        elif constraint:
            message = f"Validation failed for '{field}': {constraint}"
        else:
            message = f"Validation failed for '{field}'"
        
        super().__init__(message, error_code="validation_error")
        self.field = field
        self.value = value
        self.constraint = constraint


class RateLimitError(PawControlError):
    """Exception raised when rate limits are exceeded."""

    def __init__(self, action: str, limit: str | None = None, retry_after: int | None = None) -> None:
        """Initialize the exception.
        
        Args:
            action: The action that was rate limited
            limit: Description of the rate limit
            retry_after: Seconds until retry is allowed
        """
        if limit and retry_after:
            message = f"Rate limit exceeded for {action} ({limit}). Retry after {retry_after} seconds"
        elif limit:
            message = f"Rate limit exceeded for {action} ({limit})"
        elif retry_after:
            message = f"Rate limit exceeded for {action}. Retry after {retry_after} seconds"
        else:
            message = f"Rate limit exceeded for {action}"
        
        super().__init__(message, error_code="rate_limit_exceeded")
        self.action = action
        self.limit = limit
        self.retry_after = retry_after


class StorageError(PawControlError):
    """Exception raised when storage operations fail."""

    def __init__(self, operation: str, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            operation: The storage operation that failed
            reason: Optional reason for the failure
        """
        if reason:
            message = f"Storage {operation} failed: {reason}"
        else:
            message = f"Storage {operation} failed"
        
        super().__init__(message, error_code="storage_error")
        self.operation = operation
        self.reason = reason


class AuthenticationError(PawControlError):
    """Exception raised when authentication fails."""

    def __init__(self, service: str | None = None, reason: str | None = None) -> None:
        """Initialize the exception.
        
        Args:
            service: The service that failed authentication
            reason: Optional reason for the failure
        """
        if service and reason:
            message = f"Authentication failed for {service}: {reason}"
        elif service:
            message = f"Authentication failed for {service}"
        elif reason:
            message = f"Authentication failed: {reason}"
        else:
            message = "Authentication failed"
        
        super().__init__(message, error_code="authentication_failed")
        self.service = service
        self.reason = reason


# Exception mapping for easy lookup
EXCEPTION_MAP = {
    "dog_not_found": DogNotFoundError,
    "invalid_coordinates": InvalidCoordinatesError,
    "walk_not_in_progress": WalkNotInProgressError,
    "walk_already_in_progress": WalkAlreadyInProgressError,
    "invalid_meal_type": InvalidMealTypeError,
    "invalid_weight": InvalidWeightError,
    "grooming_not_in_progress": GroomingNotInProgressError,
    "invalid_date_range": InvalidDateRangeError,
    "data_export_failed": DataExportError,
    "data_import_failed": DataImportError,
    "notification_send_failed": NotificationError,
    "gps_unavailable": GPSUnavailableError,
    "module_not_enabled": ModuleNotEnabledError,
    "configuration_error": ConfigurationError,
    "service_unavailable": ServiceUnavailableError,
    "validation_error": ValidationError,
    "rate_limit_exceeded": RateLimitError,
    "storage_error": StorageError,
    "authentication_failed": AuthenticationError,
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
    return EXCEPTION_MAP[error_code]


def raise_from_error_code(error_code: str, message: str) -> None:
    """Raise an exception based on an error code.
    
    Args:
        error_code: The error code to raise
        message: The error message
        
    Raises:
        PawControlError: The appropriate exception for the error code
    """
    exception_class = EXCEPTION_MAP.get(error_code, PawControlError)
    raise exception_class(message, error_code)
