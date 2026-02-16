"""Error handling and validation decorators for PawControl.

This module provides comprehensive decorator utilities for automatic error handling,
input validation, and exception mapping to repair issues.

Quality Scale: Platinum target
Home Assistant: 2025.9.0+
Python: 3.13+
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import functools
import inspect
import logging
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar, cast

from homeassistant.helpers import issue_registry

from .exceptions import (
  DogNotFoundError,
  ErrorCategory,
  ErrorSeverity,
  FlowValidationError,
  GPSError,
  InvalidCoordinatesError,
  NetworkError,
  PawControlError,
  RateLimitError,
  StorageError,
  ValidationError,
  WalkError,
)

if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant  # noqa: E111


_LOGGER = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")
R = TypeVar("R")


# Validation decorators


def validate_dog_exists(
  dog_id_param: str = "dog_id",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to validate that a dog exists before executing a function.

  Args:
      dog_id_param: Name of the parameter containing the dog ID

  Returns:
      Decorator function

  Examples:
      >>> @validate_dog_exists()
      ... async def get_dog_status(self, dog_id: str):
      ...   # dog_id is guaranteed to exist
      ...   return self.coordinator.data[dog_id]
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      bound = inspect.signature(func).bind_partial(*args, **kwargs)  # noqa: E111
      dog_id = bound.arguments.get(dog_id_param)  # noqa: E111

      if dog_id is None:  # noqa: E111
        raise ValidationError(
          field=dog_id_param,
          constraint="Dog ID is required",
        )

      # Get coordinator from self (first arg)  # noqa: E114
      if not args:  # noqa: E111
        raise PawControlError(
          "Decorator requires instance method with coordinator access",
        )

      instance = args[0]  # noqa: E111
      if not hasattr(instance, "coordinator"):  # noqa: E111
        raise PawControlError(
          "Instance must have coordinator attribute for validation",
        )

      coordinator = instance.coordinator  # noqa: E111
      if dog_id not in coordinator.data:  # noqa: E111
        available_dogs = list(coordinator.data.keys())
        raise DogNotFoundError(dog_id, available_dogs)

      return func(*args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


def validate_gps_coordinates(
  latitude_param: str = "latitude",
  longitude_param: str = "longitude",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to validate GPS coordinates.

  Args:
      latitude_param: Name of latitude parameter
      longitude_param: Name of longitude parameter

  Returns:
      Decorator function

  Examples:
      >>> @validate_gps_coordinates()
      ... def set_location(self, latitude: float, longitude: float):
      ...   # Coordinates are guaranteed valid
      ...   self.location = (latitude, longitude)
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      bound = inspect.signature(func).bind_partial(*args, **kwargs)  # noqa: E111
      latitude = bound.arguments.get(latitude_param)  # noqa: E111
      longitude = bound.arguments.get(longitude_param)  # noqa: E111

      if latitude is None or longitude is None:  # noqa: E111
        raise InvalidCoordinatesError()

      # Validate ranges  # noqa: E114
      if not isinstance(latitude, (int, float)) or not isinstance(  # noqa: E111
        longitude,
        (int, float),
      ):
        raise InvalidCoordinatesError(latitude, longitude)

      if not -90 <= latitude <= 90:  # noqa: E111
        raise InvalidCoordinatesError(latitude, longitude)

      if not -180 <= longitude <= 180:  # noqa: E111
        raise InvalidCoordinatesError(latitude, longitude)

      return func(*args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


def validate_range(
  param: str,
  min_value: float | int,
  max_value: float | int,
  *,
  field_name: str | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to validate that a parameter is within a specific range.

  Args:
      param: Parameter name to validate
      min_value: Minimum allowed value (inclusive)
      max_value: Maximum allowed value (inclusive)
      field_name: Display name for error messages

  Returns:
      Decorator function

  Examples:
      >>> @validate_range("weight", 0.5, 100.0, field_name="dog weight")
      ... def set_weight(self, weight: float):
      ...   self.weight = weight
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      bound = inspect.signature(func).bind_partial(*args, **kwargs)  # noqa: E111
      value = bound.arguments.get(param)  # noqa: E111

      if value is None:  # noqa: E111
        raise ValidationError(
          field=field_name or param,
          constraint="Value is required",
        )

      if not isinstance(value, (int, float)):  # noqa: E111
        raise ValidationError(
          field=field_name or param,
          value=value,
          constraint="Must be numeric",
        )

      if value < min_value or value > max_value:  # noqa: E111
        raise ValidationError(
          field=field_name or param,
          value=value,
          constraint=f"Must be between {min_value} and {max_value}",
          min_value=min_value,
          max_value=max_value,
        )

      return func(*args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


# Error handling decorators


def handle_errors(
  log_errors: bool = True,
  reraise_critical: bool = True,
  reraise_validation_errors: bool = True,
  default_return: Any = None,
  error_category: ErrorCategory | None = None,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator for comprehensive error handling.

  Args:
      log_errors: Whether to log caught exceptions
      reraise_critical: Whether to reraise critical severity errors
      default_return: Default return value on error
      error_category: Category to assign to generic exceptions

  Returns:
      Decorator function

  Examples:
      >>> @handle_errors(log_errors=True, reraise_critical=True)
      ... async def fetch_data(self):
      ...   # Errors are logged and critical ones re-raised
      ...   return await self.api.get_data()
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      try:  # noqa: E111
        result = func(*args, **kwargs)
        if isinstance(result, Awaitable):
          return await result  # noqa: E111
        return result
      except PawControlError as e:  # noqa: E111
        if log_errors:
          _LOGGER.error(  # noqa: E111
            "%s failed with %s: %s",
            func.__name__,
            e.__class__.__name__,
            e.to_dict(),
          )

        if (reraise_critical and e.severity == ErrorSeverity.CRITICAL) or (
          reraise_validation_errors
          and isinstance(
            e,
            ValidationError | DogNotFoundError | InvalidCoordinatesError,
          )
        ):
          raise  # noqa: E111

        return cast(T, default_return)
      except Exception as e:  # noqa: E111
        if log_errors:
          _LOGGER.exception(  # noqa: E111
            "Unexpected error in %s: %s",
            func.__name__,
            e,
          )

        # Wrap in PawControlError for consistency
        error = PawControlError(
          str(e),
          error_code="unexpected_error",
          severity=ErrorSeverity.HIGH,
          category=error_category or ErrorCategory.SYSTEM,
          context={"original_exception": type(e).__name__},
        )

        if reraise_critical:
          raise error from e  # noqa: E111

        return cast(T, default_return)

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      try:  # noqa: E111
        return func(*args, **kwargs)
      except PawControlError as e:  # noqa: E111
        if log_errors:
          _LOGGER.error(  # noqa: E111
            "%s failed with %s: %s",
            func.__name__,
            e.__class__.__name__,
            e.to_dict(),
          )

        if (reraise_critical and e.severity == ErrorSeverity.CRITICAL) or (
          reraise_validation_errors
          and isinstance(
            e,
            ValidationError | DogNotFoundError | InvalidCoordinatesError,
          )
        ):
          raise  # noqa: E111

        return cast(T, default_return)
      except Exception as e:  # noqa: E111
        if log_errors:
          _LOGGER.exception(  # noqa: E111
            "Unexpected error in %s: %s",
            func.__name__,
            e,
          )

        error = PawControlError(
          str(e),
          error_code="unexpected_error",
          severity=ErrorSeverity.HIGH,
          category=error_category or ErrorCategory.SYSTEM,
          context={"original_exception": type(e).__name__},
        )

        if reraise_critical:
          raise error from e  # noqa: E111

        return cast(T, default_return)

    # Return async wrapper if function is async
    if inspect.iscoroutinefunction(func):
      return cast(Callable[P, T], async_wrapper)  # noqa: E111
    return cast(Callable[P, T], sync_wrapper)

  return decorator  # noqa: E111


def map_to_repair_issue(
  issue_id: str,
  *,
  severity: str = "warning",
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to map exceptions to Home Assistant repair issues.

  Args:
      issue_id: Repair issue identifier
      severity: Issue severity (warning, error, critical)

  Returns:
      Decorator function

  Examples:
      >>> @map_to_repair_issue("gps_unavailable", severity="warning")
      ... async def get_location(self):
      ...   # GPSUnavailableError creates repair issue
      ...   return await self.gps.get_location()
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      try:  # noqa: E111
        result = func(*args, **kwargs)
        if isinstance(result, Awaitable):
          return await result  # noqa: E111
        return result
      except PawControlError as e:  # noqa: E111
        # Get hass instance from args
        hass: HomeAssistant | None = None
        if args:
          instance = args[0]  # noqa: E111
          if hasattr(instance, "hass"):  # noqa: E111
            hass = instance.hass
          elif hasattr(instance, "coordinator"):  # noqa: E111
            hass = instance.coordinator.hass

        if hass is not None:
          # Create repair issue  # noqa: E114

          issue_registry.async_create_issue(  # noqa: E111
            hass,
            "pawcontrol",
            issue_id,
            is_fixable=True,
            severity=severity,
            translation_key=issue_id,
            translation_placeholders={
              "error": str(e),
              "error_code": e.error_code,
            },
          )

        raise

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      try:  # noqa: E111
        return func(*args, **kwargs)
      except PawControlError as e:  # noqa: E111
        hass: HomeAssistant | None = None
        if args:
          instance = args[0]  # noqa: E111
          if hasattr(instance, "hass"):  # noqa: E111
            hass = instance.hass
          elif hasattr(instance, "coordinator"):  # noqa: E111
            hass = instance.coordinator.hass

        if hass is not None:
          issue_registry.async_create_issue(  # noqa: E111
            hass,
            "pawcontrol",
            issue_id,
            is_fixable=True,
            severity=severity,
            translation_key=issue_id,
            translation_placeholders={
              "error": str(e),
              "error_code": e.error_code,
            },
          )

        raise

    if inspect.iscoroutinefunction(func):
      return cast(Callable[P, T], async_wrapper)  # noqa: E111
    return cast(Callable[P, T], sync_wrapper)

  return decorator  # noqa: E111


def retry_on_error(
  *,
  max_attempts: int = 3,
  delay: float = 1.0,
  backoff: float = 2.0,
  exceptions: tuple[type[Exception], ...] = (NetworkError, RateLimitError),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to retry a function on specific exceptions.

  Args:
      max_attempts: Maximum number of retry attempts
      delay: Initial delay between retries in seconds
      backoff: Backoff multiplier for delay
      exceptions: Tuple of exception types to retry on

  Returns:
      Decorator function

  Examples:
      >>> @retry_on_error(max_attempts=3, delay=1.0)
      ... async def fetch_api_data(self):
      ...   # Retries up to 3 times on network errors
      ...   return await self.api.fetch()
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      current_delay = delay  # noqa: E111
      last_exception: Exception | None = None  # noqa: E111

      for attempt in range(max_attempts):  # noqa: E111
        try:
          result = func(*args, **kwargs)  # noqa: E111
          if isinstance(result, Awaitable):  # noqa: E111
            return await result
          return result  # noqa: E111
        except exceptions as e:
          last_exception = e  # noqa: E111
          if attempt < max_attempts - 1:  # noqa: E111
            _LOGGER.warning(
              "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
              func.__name__,
              attempt + 1,
              max_attempts,
              e,
              current_delay,
            )
            await asyncio.sleep(current_delay)
            current_delay *= backoff
          else:  # noqa: E111
            _LOGGER.error(
              "%s failed after %d attempts: %s",
              func.__name__,
              max_attempts,
              e,
            )

      if last_exception:  # noqa: E111
        raise last_exception

      return cast(T, None)  # noqa: E111

    @functools.wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      current_delay = delay  # noqa: E111
      last_exception: Exception | None = None  # noqa: E111

      for attempt in range(max_attempts):  # noqa: E111
        try:
          return func(*args, **kwargs)  # noqa: E111
        except exceptions as e:
          last_exception = e  # noqa: E111
          if attempt < max_attempts - 1:  # noqa: E111
            _LOGGER.warning(
              "%s failed (attempt %d/%d): %s. Retrying in %.1fs...",
              func.__name__,
              attempt + 1,
              max_attempts,
              e,
              current_delay,
            )
            import time

            time.sleep(current_delay)
            current_delay *= backoff
          else:  # noqa: E111
            _LOGGER.error(
              "%s failed after %d attempts: %s",
              func.__name__,
              max_attempts,
              e,
            )

      if last_exception:  # noqa: E111
        raise last_exception

      return cast(T, None)  # noqa: E111

    if inspect.iscoroutinefunction(func):
      return cast(Callable[P, T], async_wrapper)  # noqa: E111
    return cast(Callable[P, T], sync_wrapper)

  return decorator  # noqa: E111


def require_coordinator(func: Callable[..., Any]) -> Callable[..., Any]:
  """Ensure decorated instance methods expose ``self.coordinator``."""  # noqa: E111

  @functools.wraps(func)  # noqa: E111
  def wrapper(*args: Any, **kwargs: Any) -> Any:  # noqa: E111
    if not args:
      raise PawControlError("Decorator requires an instance method")  # noqa: E111

    instance = args[0]
    coordinator = getattr(instance, "coordinator", None)
    if coordinator is None:
      raise PawControlError("Coordinator is required for this operation")  # noqa: E111

    return func(*args, **kwargs)

  return wrapper  # noqa: E111


def require_coordinator_data(
  *,
  allow_partial: bool = False,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Decorator to ensure coordinator data is available.

  Args:
      allow_partial: Whether to allow partial data

  Returns:
      Decorator function

  Examples:
      >>> @require_coordinator_data()
      ... def get_all_dogs(self):
      ...   # coordinator.data is guaranteed to be populated
      ...   return list(self.coordinator.data.keys())
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
      if not args:  # noqa: E111
        raise PawControlError(
          "Decorator requires instance method with coordinator access",
        )

      instance = args[0]  # noqa: E111
      if not hasattr(instance, "coordinator"):  # noqa: E111
        raise PawControlError(
          "Instance must have coordinator attribute",
        )

      coordinator = instance.coordinator  # noqa: E111
      if not coordinator.data:  # noqa: E111
        raise PawControlError(
          "Coordinator data not available",
          error_code="coordinator_data_unavailable",
          severity=ErrorSeverity.HIGH,
          category=ErrorCategory.DATA,
          recovery_suggestions=[
            "Wait for initial data fetch to complete",
            "Check coordinator update status",
            "Verify integration is properly configured",
          ],
        )

      if not allow_partial and not coordinator.last_update_success:  # noqa: E111
        raise PawControlError(
          "Coordinator last update failed",
          error_code="coordinator_update_failed",
          severity=ErrorSeverity.MEDIUM,
          category=ErrorCategory.DATA,
        )

      return func(*args, **kwargs)  # noqa: E111

    return wrapper

  return decorator  # noqa: E111


# Combined decorators for common patterns


def validate_and_handle(
  *,
  dog_id_param: str | None = None,
  gps_coords: bool = False,
  log_errors: bool = True,
  reraise_critical: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
  """Combined validation and error handling decorator.

  Args:
      dog_id_param: Parameter name for dog ID validation
      gps_coords: Whether to validate GPS coordinates
      log_errors: Whether to log errors
      reraise_critical: Whether to reraise critical errors

  Returns:
      Decorator function

  Examples:
      >>> @validate_and_handle(dog_id_param="dog_id", gps_coords=True)
      ... async def update_location(
      ...   self, dog_id: str, latitude: float, longitude: float
      ... ):
      ...   # Dog exists, coordinates valid, errors handled
      ...   await self.api.update_location(dog_id, latitude, longitude)
  """  # noqa: E111

  def decorator(func: Callable[P, T]) -> Callable[P, T]:  # noqa: E111
    # Apply decorators in order
    decorated = func

    if dog_id_param:
      decorated = validate_dog_exists(dog_id_param)(decorated)  # noqa: E111

    if gps_coords:
      decorated = validate_gps_coordinates()(decorated)  # noqa: E111

    decorated = handle_errors(
      log_errors=log_errors,
      reraise_critical=reraise_critical,
    )(decorated)

    return decorated

  return decorator  # noqa: E111


# Exception mapping utilities


EXCEPTION_TO_REPAIR_ISSUE: dict[type[PawControlError], str] = {
  DogNotFoundError: "dog_not_found",
  InvalidCoordinatesError: "invalid_gps_coordinates",
  GPSError: "gps_error",
  WalkError: "walk_error",
  StorageError: "storage_error",
  NetworkError: "network_error",
  RateLimitError: "rate_limit_exceeded",
  FlowValidationError: "configuration_validation_failed",
}


def get_repair_issue_id(exception: PawControlError) -> str | None:
  """Get repair issue ID for an exception.

  Args:
      exception: Exception instance

  Returns:
      Repair issue ID or None

  Examples:
      >>> error = DogNotFoundError("buddy")
      >>> get_repair_issue_id(error)
      'dog_not_found'
  """  # noqa: E111
  for exc_type, issue_id in EXCEPTION_TO_REPAIR_ISSUE.items():  # noqa: E111
    if isinstance(exception, exc_type):
      return issue_id  # noqa: E111
  return None  # noqa: E111


async def create_repair_issue_from_exception(
  hass: HomeAssistant,
  exception: PawControlError,
  *,
  is_fixable: bool = True,
) -> None:
  """Create a repair issue from an exception.

  Args:
      hass: Home Assistant instance
      exception: Exception to create repair issue from
      is_fixable: Whether the issue is fixable by the user
  """  # noqa: E111
  issue_id = get_repair_issue_id(exception)  # noqa: E111
  if not issue_id:  # noqa: E111
    issue_id = f"error_{exception.error_code}"

  severity_map = {  # noqa: E111
    ErrorSeverity.LOW: issue_registry.IssueSeverity.WARNING,
    ErrorSeverity.MEDIUM: issue_registry.IssueSeverity.WARNING,
    ErrorSeverity.HIGH: issue_registry.IssueSeverity.ERROR,
    ErrorSeverity.CRITICAL: issue_registry.IssueSeverity.CRITICAL,
  }

  issue_registry.async_create_issue(  # noqa: E111
    hass,
    "pawcontrol",
    issue_id,
    is_fixable=is_fixable,
    severity=severity_map.get(exception.severity, issue_registry.IssueSeverity.WARNING),
    translation_key=issue_id,
    translation_placeholders={
      "error": exception.user_message,
      "error_code": exception.error_code,
      "details": exception.technical_details or "",
      "suggestions": ", ".join(exception.recovery_suggestions),
    },
  )
