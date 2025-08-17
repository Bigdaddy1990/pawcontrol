"""Exception classes for Paw Control integration.

This module provides comprehensive exception handling for the Paw Control integration,
following Home Assistant's Platinum standards with proper error hierarchy, detailed
messages, and support for error recovery and debugging.

All exceptions include proper type annotations, comprehensive documentation,
and support for structured error data to facilitate debugging and monitoring.
"""

from __future__ import annotations

from typing import Any


class PawControlError(Exception):
    """Base exception for all Paw Control integration errors.

    This serves as the root exception class for all errors originating
    from the Paw Control integration. It provides a common interface
    for error handling and supports structured error data.

    Attributes:
        error_code: A unique code identifying the type of error
        details: Additional structured data about the error
        recoverable: Whether the error condition might be temporary
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        recoverable: bool = False,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message
            error_code: Optional unique error code for categorization
            details: Optional structured data about the error
            recoverable: Whether this error might be temporary
        """
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}
        self.recoverable = recoverable

    def __str__(self) -> str:
        """Return a detailed string representation of the error."""
        result = super().__str__()
        if self.error_code:
            result = f"[{self.error_code}] {result}"
        return result


class ConfigurationError(PawControlError):
    """Raised when there are configuration-related errors.

    This exception indicates problems with the integration configuration,
    such as invalid settings, missing required parameters, or incompatible
    option combinations.
    """

    def __init__(
        self,
        message: str,
        *,
        config_section: str | None = None,
        invalid_value: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize configuration error.

        Args:
            message: Human-readable error message
            config_section: The configuration section containing the error
            invalid_value: The specific value that caused the error
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, **kwargs)
        self.config_section = config_section
        self.invalid_value = invalid_value


class DogNotFoundError(PawControlError):
    """Raised when an operation references a non-existent dog.

    This exception is thrown when attempting to perform operations
    on a dog that is not configured in the integration.
    """

    def __init__(self, dog_id: str, **kwargs: Any) -> None:
        """Initialize dog not found error.

        Args:
            dog_id: The ID of the dog that was not found
            **kwargs: Additional arguments passed to parent class
        """
        message = f"Dog with ID '{dog_id}' not found"
        super().__init__(
            message,
            error_code="DOG_NOT_FOUND",
            details={"dog_id": dog_id},
            **kwargs,
        )
        self.dog_id = dog_id


class DataValidationError(PawControlError):
    """Raised when input data fails validation.

    This exception indicates that user-provided data does not meet
    the required format, type, or constraint requirements.
    """

    def __init__(
        self,
        message: str,
        *,
        field_name: str | None = None,
        expected_type: str | None = None,
        actual_value: Any = None,
        constraint: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize data validation error.

        Args:
            message: Human-readable error message
            field_name: Name of the field that failed validation
            expected_type: The expected data type
            actual_value: The value that failed validation
            constraint: Description of the constraint that was violated
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details={
                "field_name": field_name,
                "expected_type": expected_type,
                "actual_value": actual_value,
                "constraint": constraint,
            },
            **kwargs,
        )
        self.field_name = field_name
        self.expected_type = expected_type
        self.actual_value = actual_value
        self.constraint = constraint


# ==============================================================================
# GPS AND LOCATION EXCEPTIONS
# ==============================================================================


class GPSError(PawControlError):
    """Base exception for GPS-related errors.

    This serves as the parent class for all GPS and location-related
    errors in the integration.
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        """Initialize GPS error.

        Args:
            message: Human-readable error message
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(message, error_code="GPS_ERROR", **kwargs)


class InvalidCoordinatesError(GPSError):
    """Raised when invalid GPS coordinates are provided.

    This exception is thrown when latitude or longitude values
    are outside their valid ranges or are not numeric.
    """

    def __init__(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize invalid coordinates error.

        Args:
            latitude: The invalid latitude value, if any
            longitude: The invalid longitude value, if any
            **kwargs: Additional arguments passed to parent class
        """
        parts = []
        if latitude is not None:  # noqa: SIM102
            if not isinstance(latitude, int | float) or not -90 <= latitude <= 90:
                parts.append(f"latitude {latitude} (must be -90 to 90)")
        if longitude is not None:  # noqa: SIM102
            if not isinstance(longitude, int | float) or not -180 <= longitude <= 180:
                parts.append(f"longitude {longitude} (must be -180 to 180)")

        if parts:
            message = f"Invalid coordinates: {', '.join(parts)}"
        else:
            message = "Invalid coordinates provided"

        super().__init__(
            message,
            error_code="INVALID_COORDINATES",
            details={"latitude": latitude, "longitude": longitude},
            **kwargs,
        )
        self.latitude = latitude
        self.longitude = longitude


class GPSProviderError(GPSError):
    """Raised when there are errors with GPS data providers.

    This exception indicates problems communicating with or receiving
    data from GPS data sources like device trackers or external APIs.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_name: str | None = None,
        provider_error: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize GPS provider error.

        Args:
            message: Human-readable error message
            provider_name: Name of the GPS provider that failed
            provider_error: The underlying exception from the provider
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="GPS_PROVIDER_ERROR",
            details={
                "provider_name": provider_name,
                "provider_error": str(provider_error) if provider_error else None,
            },
            recoverable=True,  # Provider errors are often temporary
            **kwargs,
        )
        self.provider_name = provider_name
        self.provider_error = provider_error


class GeofenceError(GPSError):
    """Raised when there are errors with geofence operations.

    This exception indicates problems with geofence configuration,
    calculation, or state management.
    """

    def __init__(
        self,
        message: str,
        *,
        geofence_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize geofence error.

        Args:
            message: Human-readable error message
            geofence_name: Name of the geofence that caused the error
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="GEOFENCE_ERROR",
            details={"geofence_name": geofence_name},
            **kwargs,
        )
        self.geofence_name = geofence_name


# ==============================================================================
# COORDINATOR AND DATA EXCEPTIONS
# ==============================================================================


class CoordinatorError(PawControlError):
    """Raised when there are errors with the data coordinator.

    This exception indicates problems with data coordination,
    state management, or data synchronization.
    """

    def __init__(
        self,
        message: str,
        *,
        coordinator_state: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize coordinator error.

        Args:
            message: Human-readable error message
            coordinator_state: Current state of the coordinator
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="COORDINATOR_ERROR",
            details={"coordinator_state": coordinator_state},
            recoverable=True,  # Coordinator errors are often recoverable
            **kwargs,
        )
        self.coordinator_state = coordinator_state


class DataConsistencyError(CoordinatorError):
    """Raised when data consistency checks fail.

    This exception indicates that the internal data state is
    inconsistent or corrupted in some way.
    """

    def __init__(
        self,
        message: str,
        *,
        inconsistency_type: str | None = None,
        affected_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize data consistency error.

        Args:
            message: Human-readable error message
            inconsistency_type: Type of inconsistency detected
            affected_data: Data that is affected by the inconsistency
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="DATA_CONSISTENCY_ERROR",
            details={
                "inconsistency_type": inconsistency_type,
                "affected_data": affected_data,
            },
            **kwargs,
        )
        self.inconsistency_type = inconsistency_type
        self.affected_data = affected_data or {}


# ==============================================================================
# SERVICE AND API EXCEPTIONS
# ==============================================================================


class ServiceError(PawControlError):
    """Raised when there are errors with service operations.

    This exception indicates problems with Home Assistant service
    calls or service registration.
    """

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        service_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize service error.

        Args:
            message: Human-readable error message
            service_name: Name of the service that failed
            service_data: Data passed to the service call
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="SERVICE_ERROR",
            details={
                "service_name": service_name,
                "service_data": service_data,
            },
            **kwargs,
        )
        self.service_name = service_name
        self.service_data = service_data or {}


class NotificationError(PawControlError):
    """Raised when there are errors with notification delivery.

    This exception indicates problems sending notifications
    through Home Assistant's notification system.
    """

    def __init__(
        self,
        message: str,
        *,
        notification_target: str | None = None,
        notification_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize notification error.

        Args:
            message: Human-readable error message
            notification_target: Target that failed to receive notification
            notification_type: Type of notification that failed
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="NOTIFICATION_ERROR",
            details={
                "notification_target": notification_target,
                "notification_type": notification_type,
            },
            recoverable=True,  # Notification errors are often temporary
            **kwargs,
        )
        self.notification_target = notification_target
        self.notification_type = notification_type


# ==============================================================================
# DEVICE AND HARDWARE EXCEPTIONS
# ==============================================================================


class DeviceError(PawControlError):
    """Raised when there are errors with device operations.

    This exception indicates problems with device discovery,
    communication, or management.
    """

    def __init__(
        self,
        message: str,
        *,
        device_id: str | None = None,
        device_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize device error.

        Args:
            message: Human-readable error message
            device_id: ID of the device that caused the error
            device_type: Type of device that caused the error
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="DEVICE_ERROR",
            details={
                "device_id": device_id,
                "device_type": device_type,
            },
            **kwargs,
        )
        self.device_id = device_id
        self.device_type = device_type


class HardwareNotFoundError(DeviceError):
    """Raised when expected hardware is not found.

    This exception indicates that required hardware (like GPS trackers
    or sensors) could not be discovered or connected.
    """

    def __init__(
        self,
        hardware_type: str,
        *,
        expected_location: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize hardware not found error.

        Args:
            hardware_type: Type of hardware that was not found
            expected_location: Where the hardware was expected to be found
            **kwargs: Additional arguments passed to parent class
        """
        message = f"Required hardware not found: {hardware_type}"
        if expected_location:
            message += f" (expected at {expected_location})"

        super().__init__(
            message,
            error_code="HARDWARE_NOT_FOUND",
            details={
                "hardware_type": hardware_type,
                "expected_location": expected_location,
            },
            **kwargs,
        )
        self.hardware_type = hardware_type
        self.expected_location = expected_location


# ==============================================================================
# STORAGE AND PERSISTENCE EXCEPTIONS
# ==============================================================================


class StorageError(PawControlError):
    """Raised when there are errors with data storage operations.

    This exception indicates problems reading from or writing to
    persistent storage systems.
    """

    def __init__(
        self,
        message: str,
        *,
        storage_type: str | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize storage error.

        Args:
            message: Human-readable error message
            storage_type: Type of storage that failed
            operation: The operation that failed (read, write, delete, etc.)
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="STORAGE_ERROR",
            details={
                "storage_type": storage_type,
                "operation": operation,
            },
            recoverable=True,  # Storage errors might be temporary
            **kwargs,
        )
        self.storage_type = storage_type
        self.operation = operation


# ==============================================================================
# INTEGRATION LIFECYCLE EXCEPTIONS
# ==============================================================================


class SetupError(PawControlError):
    """Raised when there are errors during integration setup.

    This exception indicates problems during the initialization
    or setup phase of the integration.
    """

    def __init__(
        self,
        message: str,
        *,
        setup_phase: str | None = None,
        component: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize setup error.

        Args:
            message: Human-readable error message
            setup_phase: The setup phase that failed
            component: The component that failed to set up
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="SETUP_ERROR",
            details={
                "setup_phase": setup_phase,
                "component": component,
            },
            **kwargs,
        )
        self.setup_phase = setup_phase
        self.component = component


class MigrationError(PawControlError):
    """Raised when there are errors during data migration.

    This exception indicates problems migrating data from older
    versions of the integration.
    """

    def __init__(
        self,
        message: str,
        *,
        from_version: str | None = None,
        to_version: str | None = None,
        migration_step: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize migration error.

        Args:
            message: Human-readable error message
            from_version: Version migrating from
            to_version: Version migrating to
            migration_step: The migration step that failed
            **kwargs: Additional arguments passed to parent class
        """
        super().__init__(
            message,
            error_code="MIGRATION_ERROR",
            details={
                "from_version": from_version,
                "to_version": to_version,
                "migration_step": migration_step,
            },
            **kwargs,
        )
        self.from_version = from_version
        self.to_version = to_version
        self.migration_step = migration_step


# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================


def wrap_exception(
    func_name: str,
    original_exception: Exception,
    *,
    error_code: str | None = None,
    recoverable: bool = False,
    additional_details: dict[str, Any] | None = None,
) -> PawControlError:
    """Wrap a generic exception in a PawControlError.

    This utility function converts generic exceptions into the
    integration's structured exception hierarchy.

    Args:
        func_name: Name of the function where the error occurred
        original_exception: The original exception to wrap
        error_code: Optional error code to assign
        recoverable: Whether the error might be temporary
        additional_details: Additional structured data about the error

    Returns:
        A PawControlError wrapping the original exception
    """
    message = f"Error in {func_name}: {original_exception}"

    details = {"original_exception": str(original_exception)}
    if additional_details:
        details.update(additional_details)

    return PawControlError(
        message,
        error_code=error_code or "WRAPPED_EXCEPTION",
        details=details,
        recoverable=recoverable,
    )


def create_validation_error(
    field_name: str,
    value: Any,
    constraint: str,
    expected_type: str | None = None,
) -> DataValidationError:
    """Create a standardized validation error.

    This utility function creates consistent validation error messages
    and structured data for field validation failures.

    Args:
        field_name: Name of the field that failed validation
        value: The value that failed validation
        constraint: Description of the constraint that was violated
        expected_type: The expected data type, if applicable

    Returns:
        A DataValidationError with standardized formatting
    """
    if expected_type:
        message = f"Field '{field_name}' failed validation: expected {expected_type}, got {type(value).__name__} ({value}). Constraint: {constraint}"
    else:
        message = (
            f"Field '{field_name}' failed validation: {constraint}. Value: {value}"
        )

    return DataValidationError(
        message,
        field_name=field_name,
        expected_type=expected_type,
        actual_value=value,
        constraint=constraint,
    )


# Maintain backward compatibility with old exception names
GPSProviderError = GPSProviderError  # Already correctly named
InvalidCoordinates = InvalidCoordinatesError  # For backward compatibility
