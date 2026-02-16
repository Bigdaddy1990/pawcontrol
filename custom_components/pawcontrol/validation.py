"""Comprehensive input validation framework for PawControl.

Provides validation utilities for all user inputs, service calls,
and configuration data with detailed error reporting.

Quality Scale: Platinum target
P26.1.1++
Python: 3.13+
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import time as dt_time
from enum import Enum
from numbers import Real
import re
from typing import TYPE_CHECKING, Any, Final, TypeVar, cast

from homeassistant.exceptions import ServiceValidationError

from .const import (
  CONF_DOG_NAME,
  CONF_GPS_SOURCE,
  CONF_NOTIFY_FALLBACK,
  MAX_DOG_NAME_LENGTH,
  MIN_DOG_NAME_LENGTH,
)

if TYPE_CHECKING:
  from homeassistant.core import HomeAssistant  # noqa: E111


class PawControlValidationError(ServiceValidationError):
  """Base validation error for PawControl."""


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

MIN_GEOFENCE_RADIUS: Final[float] = 10.0
MAX_GEOFENCE_RADIUS: Final[float] = 10000.0

TNotificationTarget = TypeVar("TNotificationTarget", bound=Enum)


class InputCoercionError(ValueError):
  """Raised when raw input cannot be coerced to the expected type."""  # noqa: E111

  def __init__(self, field: str, value: Any, message: str) -> None:  # noqa: E111
    super().__init__(message)
    self.field = field
    self.value = value
    self.message = message


def _is_empty(value: Any) -> bool:
  """Return True when a value should be treated as missing."""  # noqa: E111

  return value is None or (isinstance(value, str) and not value.strip())  # noqa: E111


@dataclass(frozen=True, slots=True)
class NotificationTargets[TNotificationTarget: Enum]:
  """Typed result for notification target validation."""  # noqa: E111

  targets: list[TNotificationTarget]  # noqa: E111
  invalid: list[str]  # noqa: E111


def _coerce_float_with_constraint(
  field: str,
  value: Any,
  constraint: str,
) -> float:
  """Coerce a float while normalising validation constraints."""  # noqa: E111

  try:  # noqa: E111
    return coerce_float(field, value)
  except InputCoercionError as err:  # noqa: E111
    raise ValidationError(field, value, constraint) from err


def normalize_dog_id(raw_id: Any) -> str:
  """Normalize a dog identifier for flow and service validation."""  # noqa: E111

  if raw_id is None:  # noqa: E111
    return ""

  if not isinstance(raw_id, str):  # noqa: E111
    raise InputCoercionError("dog_id", raw_id, "Must be a string")

  dog_id_raw = raw_id.strip().lower()  # noqa: E111
  return re.sub(r"\s+", "_", dog_id_raw)  # noqa: E111


def _parse_time_string(
  field: str,
  value: Any,
  invalid_constraint: str,
) -> str | None:
  """Parse and normalize time strings for validation."""  # noqa: E111

  if value is None:  # noqa: E111
    return None

  if isinstance(value, dt_time):  # noqa: E111
    return value.isoformat()

  if not isinstance(value, str):  # noqa: E111
    raise ValidationError(field, value, invalid_constraint)

  trimmed = value.strip()  # noqa: E111
  if not trimmed:  # noqa: E111
    return None

  try:  # noqa: E111
    parsed = dt_time.fromisoformat(trimmed)
  except ValueError as err:  # noqa: E111
    raise ValidationError(field, value, invalid_constraint) from err

  return parsed.isoformat()  # noqa: E111


def coerce_float(field: str, value: Any) -> float:
  """Convert a value to float while raising typed coercion errors."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    raise InputCoercionError(field, value, "Must be numeric")

  if isinstance(value, Real):  # noqa: E111
    return float(value)

  if isinstance(value, str):  # noqa: E111
    stripped = value.strip()
    if not stripped:
      raise InputCoercionError(field, value, "Must be numeric")  # noqa: E111
    try:
      return float(stripped)  # noqa: E111
    except ValueError as err:
      raise InputCoercionError(  # noqa: E111
        field,
        value,
        "Must be numeric",
      ) from err

  raise InputCoercionError(  # noqa: E111
    field,
    value,
    "Must be numeric",
  )


def coerce_int(field: str, value: Any) -> int:
  """Convert a value to int while validating fractional input."""  # noqa: E111

  if isinstance(value, bool):  # noqa: E111
    raise InputCoercionError(field, value, "Must be a whole number")

  if isinstance(value, int):  # noqa: E111
    return value

  if isinstance(value, Real):  # noqa: E111
    float_value = float(value)
    if float_value.is_integer():
      return int(float_value)  # noqa: E111
    raise InputCoercionError(
      field,
      value,
      "Must be a whole number",
    )

  if isinstance(value, str):  # noqa: E111
    stripped = value.strip()
    if not stripped:
      raise InputCoercionError(  # noqa: E111
        field,
        value,
        "Must be a whole number",
      )

    try:
      return int(stripped)  # noqa: E111
    except ValueError:
      try:  # noqa: E111
        float_value = float(stripped)
      except ValueError as err:  # noqa: E111
        raise InputCoercionError(
          field,
          value,
          "Must be a whole number",
        ) from err

      if not float_value.is_integer():  # noqa: E111
        raise InputCoercionError(
          field,
          value,
          "Must be a whole number",
        ) from None

      return int(float_value)  # noqa: E111

  raise InputCoercionError(  # noqa: E111
    field,
    value,
    "Must be a whole number",
  )


def _coerce_float(field: str, value: Any) -> float:
  """Convert a value to float while providing helpful validation errors."""  # noqa: E111

  try:  # noqa: E111
    return coerce_float(field, value)
  except InputCoercionError as err:  # noqa: E111
    raise ValidationError(
      field,
      value,
      "Must be numeric",
    ) from err


def _coerce_int(field: str, value: Any) -> int:
  """Convert a value to int while validating fractional input."""  # noqa: E111

  try:  # noqa: E111
    return coerce_int(field, value)
  except InputCoercionError as err:  # noqa: E111
    raise ValidationError(
      field,
      value,
      "Must be a whole number",
    ) from err


def validate_notification_targets[TNotificationTarget: Enum](
  raw_targets: Any,
  *,
  enum_type: type[TNotificationTarget],
) -> NotificationTargets[TNotificationTarget]:
  """Validate notification targets against the provided enum type."""  # noqa: E111

  if raw_targets is None:  # noqa: E111
    return NotificationTargets(targets=[], invalid=[])

  candidate_targets: Iterable[Any]  # noqa: E111
  if isinstance(raw_targets, enum_type | str):  # noqa: E111
    candidate_targets = [raw_targets]
  elif isinstance(raw_targets, Iterable) and not isinstance(  # noqa: E111
    raw_targets,
    str | bytes | bytearray,
  ):
    candidate_targets = raw_targets
  else:  # noqa: E111
    candidate_targets = [raw_targets]

  targets: list[TNotificationTarget] = []  # noqa: E111
  invalid: list[str] = []  # noqa: E111
  seen: set[TNotificationTarget] = set()  # noqa: E111
  for candidate in candidate_targets:  # noqa: E111
    try:
      target = enum_type(candidate)  # noqa: E111
    except ValueError:
      invalid.append(str(candidate))  # noqa: E111
      continue  # noqa: E111
    except TypeError:
      invalid.append(str(candidate))  # noqa: E111
      continue  # noqa: E111

    if target in seen:
      continue  # noqa: E111

    seen.add(target)
    targets.append(target)

  return NotificationTargets(targets=targets, invalid=invalid)  # noqa: E111


def validate_time_window(
  start: Any,
  end: Any,
  *,
  start_field: str,
  end_field: str,
  default_start: str | None = None,
  default_end: str | None = None,
  invalid_start_constraint: str = "invalid_time_format",
  invalid_end_constraint: str = "invalid_time_format",
  required_start_constraint: str = "time_required",
  required_end_constraint: str = "time_required",
) -> tuple[str, str]:
  """Validate a start/end time window."""  # noqa: E111

  start_time = _parse_time_string(start_field, start, invalid_start_constraint)  # noqa: E111
  end_time = _parse_time_string(end_field, end, invalid_end_constraint)  # noqa: E111

  if start_time is None:  # noqa: E111
    start_time = _parse_time_string(
      start_field,
      default_start,
      invalid_start_constraint,
    )
  if end_time is None:  # noqa: E111
    end_time = _parse_time_string(
      end_field,
      default_end,
      invalid_end_constraint,
    )

  if start_time is None:  # noqa: E111
    raise ValidationError(start_field, start, required_start_constraint)
  if end_time is None:  # noqa: E111
    raise ValidationError(end_field, end, required_end_constraint)

  return start_time, end_time  # noqa: E111


def validate_dog_name(
  name: Any,
  *,
  field: str = CONF_DOG_NAME,
  required: bool = True,
  min_length: int = MIN_DOG_NAME_LENGTH,
  max_length: int = MAX_DOG_NAME_LENGTH,
) -> str | None:
  """Validate dog name input and return a trimmed value."""  # noqa: E111

  if name is None or name == "":  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        field,
        name,
        "dog_name_required",
      )
    return None

  if not isinstance(name, str):  # noqa: E111
    raise ValidationError(
      field,
      name,
      "dog_name_invalid",
    )

  trimmed = name.strip()  # noqa: E111
  if len(trimmed) > max_length:  # noqa: E111
    raise ValidationError(
      field,
      name,
      "dog_name_too_long",
      max_value=max_length,
    )

  if not trimmed:  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        field,
        name,
        "dog_name_required",
      )
    return None

  if len(trimmed) < min_length:  # noqa: E111
    raise ValidationError(
      field,
      trimmed,
      "dog_name_too_short",
      min_value=min_length,
    )

  if len(trimmed) > max_length:  # noqa: E111
    raise ValidationError(
      field,
      trimmed,
      "dog_name_too_long",
      max_value=max_length,
    )

  return trimmed  # noqa: E111


def validate_name(
  raw_name: Any,
  *,
  field: str = CONF_DOG_NAME,
  min_length: int = MIN_DOG_NAME_LENGTH,
  max_length: int = MAX_DOG_NAME_LENGTH,
) -> str:
  """Validate and normalize a name string."""  # noqa: E111

  if not isinstance(raw_name, str):  # noqa: E111
    raise ValidationError(field, raw_name, "name_invalid_type")

  name = raw_name.strip()  # noqa: E111
  if not name:  # noqa: E111
    raise ValidationError(field, raw_name, "name_required")
  if len(name) < min_length:  # noqa: E111
    raise ValidationError(
      field,
      name,
      "name_too_short",
      min_value=min_length,
    )
  if len(name) > max_length:  # noqa: E111
    raise ValidationError(
      field,
      name,
      "name_too_long",
      max_value=max_length,
    )
  return name  # noqa: E111


def validate_coordinate(
  value: Any,
  *,
  field: str,
  minimum: float,
  maximum: float,
  required: bool = True,
) -> float | None:
  """Validate a single coordinate within bounds."""  # noqa: E111

  if _is_empty(value):  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        field,
        value,
        "coordinate_required",
      )
    return None

  coordinate = _coerce_float_with_constraint(  # noqa: E111
    field,
    value,
    "coordinate_not_numeric",
  )
  if coordinate < minimum or coordinate > maximum:  # noqa: E111
    raise ValidationError(
      field,
      coordinate,
      "coordinate_out_of_range",
      min_value=minimum,
      max_value=maximum,
    )
  return coordinate  # noqa: E111


def validate_gps_source(
  hass: HomeAssistant,
  gps_source: Any,
  *,
  field: str = CONF_GPS_SOURCE,
  allow_manual: bool = True,
) -> str:
  """Validate a GPS source entity or manual selection."""  # noqa: E111

  if not isinstance(gps_source, str):  # noqa: E111
    raise ValidationError(field, gps_source, "gps_source_required")

  candidate = gps_source.strip()  # noqa: E111
  if not candidate:  # noqa: E111
    raise ValidationError(field, gps_source, "gps_source_required")

  if allow_manual and candidate == "manual":  # noqa: E111
    return candidate

  if candidate in {"webhook", "mqtt"}:  # noqa: E111
    return candidate

  state = hass.states.get(candidate)  # noqa: E111
  if state is None:  # noqa: E111
    raise ValidationError(field, candidate, "gps_source_not_found")
  if state.state in {"unknown", "unavailable"}:  # noqa: E111
    raise ValidationError(field, candidate, "gps_source_unavailable")

  return candidate  # noqa: E111


def validate_notify_service(
  hass: HomeAssistant,
  notify_service: Any,
  *,
  field: str = CONF_NOTIFY_FALLBACK,
) -> str:
  """Validate notification service selection."""  # noqa: E111

  if not isinstance(notify_service, str):  # noqa: E111
    raise ValidationError(field, notify_service, "notify_service_invalid")
  candidate = notify_service.strip()  # noqa: E111
  if not candidate:  # noqa: E111
    raise ValidationError(field, notify_service, "notify_service_invalid")

  service_parts = candidate.split(".", 1)  # noqa: E111
  if len(service_parts) != 2 or service_parts[0] != "notify":  # noqa: E111
    raise ValidationError(field, candidate, "notify_service_invalid")

  services = hass.services.async_services().get("notify", {})  # noqa: E111
  if service_parts[1] not in services:  # noqa: E111
    raise ValidationError(field, candidate, "notify_service_not_found")

  return candidate  # noqa: E111


def validate_gps_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
  """Compatibility helper that raises ``InvalidCoordinatesError``.

  Uses a local exception import to avoid module import-order cycles.
  """  # noqa: E111

  try:  # noqa: E111
    return InputValidator.validate_gps_coordinates(latitude, longitude)
  except ValidationError as err:  # noqa: E111
    from .exceptions import InvalidCoordinatesError

    raise InvalidCoordinatesError(latitude, longitude) from err


def validate_entity_id(entity_id: Any, *, field: str = "entity_id") -> str:
  """Validate Home Assistant entity IDs in ``domain.object_id`` format."""  # noqa: E111

  if not isinstance(entity_id, str):  # noqa: E111
    raise ValidationError(field, entity_id, "Invalid entity_id format")

  candidate = entity_id.strip()  # noqa: E111
  parts = candidate.split(".")  # noqa: E111
  if len(parts) != 2 or not parts[0] or not parts[1]:  # noqa: E111
    raise ValidationError(field, entity_id, "Invalid entity_id format")

  if not re.fullmatch(r"[a-z_]+", parts[0]):  # noqa: E111
    raise ValidationError(field, entity_id, "Invalid entity_id format")

  if not re.fullmatch(r"[\w]+", parts[1], flags=re.UNICODE):  # noqa: E111
    raise ValidationError(field, entity_id, "Invalid entity_id format")

  return candidate  # noqa: E111


def validate_sensor_entity_id(
  hass: HomeAssistant,
  entity_id: Any,
  *,
  field: str,
  required: bool = False,
  domain: str | None = None,
  device_classes: set[str] | None = None,
  required_constraint: str = "sensor_required",
  not_found_constraint: str = "sensor_not_found",
) -> str | None:
  """Validate a sensor entity ID selection."""  # noqa: E111

  if _is_empty(entity_id):  # noqa: E111
    if required:
      raise ValidationError(field, entity_id, required_constraint)  # noqa: E111
    return None

  if not isinstance(entity_id, str):  # noqa: E111
    raise ValidationError(field, entity_id, not_found_constraint)

  candidate = entity_id.strip()  # noqa: E111
  if not candidate:  # noqa: E111
    if required:
      raise ValidationError(field, entity_id, required_constraint)  # noqa: E111
    return None

  if domain:  # noqa: E111
    domain_part = candidate.split(".", 1)[0]
    if domain_part != domain:
      raise ValidationError(field, candidate, not_found_constraint)  # noqa: E111

  state = hass.states.get(candidate)  # noqa: E111
  if state is None or state.state in {"unknown", "unavailable"}:  # noqa: E111
    raise ValidationError(field, candidate, not_found_constraint)

  if device_classes:  # noqa: E111
    device_class = state.attributes.get("device_class")
    if device_class not in device_classes:
      raise ValidationError(field, candidate, not_found_constraint)  # noqa: E111

  return candidate  # noqa: E111


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
  """Validate timer/interval values within bounds."""  # noqa: E111

  if value is None:  # noqa: E111
    if default is not None:
      return default  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        field,
        value,
        "Interval is required",
      )
    return minimum if clamp else 0

  interval = _coerce_int(field, value)  # noqa: E111
  if interval < minimum:  # noqa: E111
    if clamp:
      return minimum  # noqa: E111
    raise ValidationError(
      field,
      interval,
      f"Minimum interval is {minimum}",
      min_value=minimum,
      max_value=maximum,
    )
  if interval > maximum:  # noqa: E111
    if clamp:
      return maximum  # noqa: E111
    raise ValidationError(
      field,
      interval,
      f"Maximum interval is {maximum}",
      min_value=minimum,
      max_value=maximum,
    )
  return interval  # noqa: E111


def validate_gps_update_interval(
  value: Any,
  *,
  field: str = "gps_update_interval",
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
) -> int | None:
  """Validate GPS update intervals in seconds."""  # noqa: E111

  return validate_gps_interval(  # noqa: E111
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    default=default,
    clamp=clamp,
    required=required,
  )


def validate_gps_interval(
  value: Any,
  *,
  field: str = "gps_update_interval",
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
) -> int | None:
  """Validate GPS update intervals in seconds."""  # noqa: E111

  return validate_int_range(  # noqa: E111
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    default=default,
    clamp=clamp,
    required=required,
    required_constraint="gps_update_interval_required",
    not_numeric_constraint="gps_update_interval_not_numeric",
    out_of_range_constraint="gps_update_interval_out_of_range",
  )


def validate_expires_in_hours(
  value: Any,
  *,
  field: str = "expires_in_hours",
  minimum: float = 0.0,
  maximum: float | None = None,
  required: bool = False,
) -> float | None:
  """Validate notification expiry overrides in hours."""  # noqa: E111

  if _is_empty(value):  # noqa: E111
    if required:
      raise ValidationError(field, value, "expires_in_hours_required")  # noqa: E111
    return None

  try:  # noqa: E111
    hours = coerce_float(field, value)
  except InputCoercionError as err:  # noqa: E111
    raise ValidationError(field, value, "expires_in_hours_not_numeric") from err

  if hours <= minimum:  # noqa: E111
    raise ValidationError(
      field,
      hours,
      "expires_in_hours_out_of_range",
      min_value=minimum,
      max_value=maximum,
    )

  if maximum is not None and hours > maximum:  # noqa: E111
    raise ValidationError(
      field,
      hours,
      "expires_in_hours_out_of_range",
      min_value=minimum,
      max_value=maximum,
    )

  return hours  # noqa: E111


def validate_gps_accuracy_value(
  accuracy: Any,
  *,
  required: bool = False,
  field: str = "accuracy",
  min_value: float = MIN_ACCURACY_METERS,
  max_value: float = MAX_ACCURACY_METERS,
  default: float | None = None,
  clamp: bool = False,
) -> float | None:
  """Validate GPS accuracy values."""  # noqa: E111

  if _is_empty(accuracy):  # noqa: E111
    if default is not None:
      return default  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        field,
        accuracy,
        "gps_accuracy_required",
      )
    return None

  accuracy = _coerce_float_with_constraint(  # noqa: E111
    field,
    accuracy,
    "gps_accuracy_not_numeric",
  )

  if accuracy < min_value:  # noqa: E111
    if clamp:
      return min_value  # noqa: E111
    raise ValidationError(
      field,
      accuracy,
      "gps_accuracy_out_of_range",
      min_value=min_value,
      max_value=max_value,
    )

  if accuracy > max_value:  # noqa: E111
    if clamp:
      return max_value  # noqa: E111
    raise ValidationError(
      field,
      accuracy,
      "gps_accuracy_out_of_range",
      min_value=min_value,
      max_value=max_value,
    )

  return accuracy  # noqa: E111


def validate_float_range(
  value: Any,
  minimum: float,
  maximum: float,
  *,
  field: str = "value",
  field_name: str | None = None,
  default: float | None = None,
  clamp: bool = False,
  required: bool = False,
) -> float:
  """Validate a floating-point range within bounds."""  # noqa: E111

  resolved_field = field_name or field or "value"  # noqa: E111

  if value is None:  # noqa: E111
    if default is not None:
      return default  # noqa: E111
    if required:
      raise ValidationError(  # noqa: E111
        resolved_field,
        value,
        "Value is required",
      )
    return minimum if clamp else 0.0

  candidate = _coerce_float(resolved_field, value)  # noqa: E111
  if candidate < minimum:  # noqa: E111
    if clamp:
      return minimum  # noqa: E111
    raise ValidationError(
      resolved_field,
      candidate,
      f"Minimum value is {minimum}",
      min_value=minimum,
      max_value=maximum,
    )
  if candidate > maximum:  # noqa: E111
    if clamp:
      return maximum  # noqa: E111
    raise ValidationError(
      resolved_field,
      candidate,
      f"Maximum value is {maximum}",
      min_value=minimum,
      max_value=maximum,
    )
  return candidate  # noqa: E111


def validate_int_range(
  value: Any,
  *,
  field: str,
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
  required_constraint: str = "value_required",
  not_numeric_constraint: str = "value_not_numeric",
  out_of_range_constraint: str = "value_out_of_range",
) -> int | None:
  """Validate an integer range within bounds."""  # noqa: E111

  if _is_empty(value):  # noqa: E111
    if default is not None:
      return default  # noqa: E111
    if required:
      raise ValidationError(field, value, required_constraint)  # noqa: E111
    return None

  try:  # noqa: E111
    interval = coerce_int(field, value)
  except InputCoercionError as err:  # noqa: E111
    raise ValidationError(field, value, not_numeric_constraint) from err

  if interval < minimum:  # noqa: E111
    if clamp:
      return minimum  # noqa: E111
    raise ValidationError(
      field,
      interval,
      out_of_range_constraint,
      min_value=minimum,
      max_value=maximum,
    )
  if interval > maximum:  # noqa: E111
    if clamp:
      return maximum  # noqa: E111
    raise ValidationError(
      field,
      interval,
      out_of_range_constraint,
      min_value=minimum,
      max_value=maximum,
    )
  return interval  # noqa: E111


def clamp_int_range(
  value: Any,
  *,
  field: str,
  minimum: int,
  maximum: int,
  default: int,
) -> int:
  """Coerce and clamp integer input to the provided bounds."""  # noqa: E111

  try:  # noqa: E111
    validated = validate_int_range(
      value,
      field=field,
      minimum=minimum,
      maximum=maximum,
      default=default,
      clamp=True,
    )
    return default if validated is None else validated
  except ValidationError:  # noqa: E111
    return default


def clamp_float_range(
  value: Any,
  *,
  field: str,
  minimum: float,
  maximum: float,
  default: float,
) -> float:
  """Coerce and clamp float input to the provided bounds."""  # noqa: E111

  try:  # noqa: E111
    return validate_float_range(
      value,
      field=field,
      minimum=minimum,
      maximum=maximum,
      default=default,
      clamp=True,
    )
  except ValidationError:  # noqa: E111
    return default


class InputValidator:
  """Comprehensive input validation for PawControl.

  Provides static methods for validating all types of user inputs
  with detailed error reporting and security checks.
  """  # noqa: E111

  @staticmethod  # noqa: E111
  def validate_dog_id(dog_id: Any, required: bool = True) -> str | None:  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "dog_id",
          dog_id,
          "Dog ID is required",
          "Provide a valid dog identifier",
        )
      return None  # noqa: E111

    if not isinstance(dog_id, str):
      raise ValidationError(  # noqa: E111
        "dog_id",
        dog_id,
        "Must be a string",
        f"Received {type(dog_id).__name__}",
      )

    dog_id = dog_id.strip()

    if not dog_id:
      if required:  # noqa: E111
        raise ValidationError(
          "dog_id",
          dog_id,
          "Cannot be empty or whitespace only",
          "Provide a valid identifier",
        )
      return None  # noqa: E111

    if len(dog_id) > 50:
      raise ValidationError(  # noqa: E111
        "dog_id",
        dog_id,
        "Maximum 50 characters",
        f"Current length: {len(dog_id)}",
      )

    if not re.match(VALID_DOG_ID_PATTERN, dog_id):
      raise ValidationError(  # noqa: E111
        "dog_id",
        dog_id,
        "Only alphanumeric characters, underscore, and hyphen allowed",
        "Use only: a-z, A-Z, 0-9, _, -",
      )

    return dog_id

  @staticmethod  # noqa: E111
  def validate_dog_name(name: Any, required: bool = True) -> str | None:  # noqa: E111
    """Validate dog name.

    Args:
        name: Dog name to validate
        required: Whether the field is required

    Returns:
        Validated name or None if not required

    Raises:
        ValidationError: If validation fails
    """
    return validate_dog_name(name, required=required)

  @staticmethod  # noqa: E111
  def validate_weight(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "weight",
          weight,
          "Weight is required",
          "Provide dog weight in kilograms",
        )
      return None  # noqa: E111

    weight = _coerce_float("weight", weight)

    if weight <= 0:
      raise ValidationError(  # noqa: E111
        "weight",
        weight,
        "Must be positive",
        "Weight must be greater than 0",
      )

    if weight < min_kg:
      raise ValidationError(  # noqa: E111
        "weight",
        weight,
        f"Minimum weight is {min_kg} kg",
        f"Provided: {weight} kg",
      )

    if weight > max_kg:
      raise ValidationError(  # noqa: E111
        "weight",
        weight,
        f"Maximum weight is {max_kg} kg",
        f"Provided: {weight} kg - unusually large for a dog",
      )

    return weight

  @staticmethod  # noqa: E111
  def validate_age_months(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "age_months",
          age,
          "Age is required",
          "Provide dog age in months",
        )
      return None  # noqa: E111

    age = _coerce_int("age_months", age)

    if age < min_months:
      raise ValidationError(  # noqa: E111
        "age_months",
        age,
        f"Minimum age is {min_months} months",
        f"Provided: {age} months",
      )

    if age > max_months:
      raise ValidationError(  # noqa: E111
        "age_months",
        age,
        f"Maximum age is {max_months} months ({max_months // 12} years)",
        f"Provided: {age} months - unusually old",
      )

    return age

  @staticmethod  # noqa: E111
  def validate_gps_coordinates(  # noqa: E111
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

  @staticmethod  # noqa: E111
  def validate_gps_accuracy(  # noqa: E111
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
    return validate_gps_accuracy_value(
      accuracy,
      required=required,
      field=field,
      min_value=min_value,
      max_value=max_value,
    )

  @staticmethod  # noqa: E111
  def validate_portion_size(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "amount",
          amount,
          "Portion amount is required",
          "Provide amount in grams",
        )
      return None  # noqa: E111

    amount = _coerce_float("amount", amount)

    if amount <= 0:
      raise ValidationError(  # noqa: E111
        "amount",
        amount,
        "Must be positive",
        "Portion size must be greater than 0",
      )

    if amount < MIN_PORTION_GRAMS:
      raise ValidationError(  # noqa: E111
        "amount",
        amount,
        f"Minimum portion is {MIN_PORTION_GRAMS} grams",
        f"Provided: {amount} grams - unusually small",
      )

    if amount > MAX_PORTION_GRAMS:
      raise ValidationError(  # noqa: E111
        "amount",
        amount,
        f"Maximum portion is {MAX_PORTION_GRAMS} grams",
        f"Provided: {amount} grams - unusually large for one meal",
      )

    return amount

  @staticmethod  # noqa: E111
  def validate_temperature(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "temperature",
          temperature,
          "Temperature is required",
          "Provide body temperature in Celsius",
        )
      return None  # noqa: E111

    temperature = _coerce_float("temperature", temperature)

    if not MIN_TEMPERATURE_CELSIUS <= temperature <= MAX_TEMPERATURE_CELSIUS:
      raise ValidationError(  # noqa: E111
        "temperature",
        temperature,
        f"Normal range: {MIN_TEMPERATURE_CELSIUS}-{MAX_TEMPERATURE_CELSIUS}°C",
        f"Provided: {temperature}°C - seek veterinary attention if accurate",
      )

    return temperature

  @staticmethod  # noqa: E111
  def validate_text_input(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          field_name,
          text,
          f"{field_name} is required",
          "Provide text input",
        )
      return None  # noqa: E111

    if not isinstance(text, str):
      raise ValidationError(  # noqa: E111
        field_name,
        text,
        "Must be text",
        f"Received {type(text).__name__}",
      )

    text = text.strip()

    if not text and required:
      raise ValidationError(  # noqa: E111
        field_name,
        text,
        "Cannot be empty or whitespace",
        "Provide meaningful text",
      )

    if len(text) < min_length:
      raise ValidationError(  # noqa: E111
        field_name,
        text,
        f"Minimum length: {min_length} characters",
        f"Provided: {len(text)} characters",
      )

    if len(text) > max_length:
      raise ValidationError(  # noqa: E111
        field_name,
        text,
        f"Maximum length: {max_length} characters",
        f"Provided: {len(text)} characters",
      )

    # Remove control characters (except newlines)
    return "".join(char for char in text if ord(char) >= 32 or char == "\n")

  @staticmethod  # noqa: E111
  def validate_duration(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "duration",
          duration,
          "Duration is required",
        )
      return None  # noqa: E111

    return validate_interval(
      duration,
      field="duration",
      minimum=min_minutes,
      maximum=max_minutes,
      required=required,
    )

  @staticmethod  # noqa: E111
  def validate_geofence_radius(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          field,
          radius,
          "geofence_radius_required",
        )
      return None  # noqa: E111

    radius = _coerce_float_with_constraint(
      field,
      radius,
      "geofence_radius_not_numeric",
    )

    if radius < min_value:
      raise ValidationError(  # noqa: E111
        field,
        radius,
        "geofence_radius_out_of_range",
        min_value=min_value,
        max_value=max_value,
      )

    if radius > max_value:
      raise ValidationError(  # noqa: E111
        field,
        radius,
        "geofence_radius_out_of_range",
        min_value=min_value,
        max_value=max_value,
      )

    return radius

  @staticmethod  # noqa: E111
  def validate_email(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          "email",
          email,
          "Email address is required",
          "Provide valid email address",
        )
      return None  # noqa: E111

    if not isinstance(email, str):
      raise ValidationError(  # noqa: E111
        "email",
        email,
        "Must be text",
        f"Received {type(email).__name__}",
      )

    email = email.strip().lower()

    if not re.match(VALID_EMAIL_PATTERN, email):
      raise ValidationError(  # noqa: E111
        "email",
        email,
        "Invalid email format",
        "Use format: user@example.com",
      )

    if len(email) > 254:  # RFC 5321
      raise ValidationError(  # noqa: E111
        "email",
        email,
        "Email too long (max 254 characters)",
        f"Provided: {len(email)} characters",
      )

    return email

  @staticmethod  # noqa: E111
  def validate_enum_value(  # noqa: E111
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
      if required:  # noqa: E111
        raise ValidationError(
          field_name,
          value,
          f"{field_name} is required",
          f"Choose from: {', '.join(valid_values)}",
        )
      return None  # noqa: E111

    if not isinstance(value, str):
      value = str(value)  # noqa: E111

    value = value.strip().lower()

    # Case-insensitive matching
    valid_values_lower = {v.lower() for v in valid_values}

    if value not in valid_values_lower:
      raise ValidationError(  # noqa: E111
        field_name,
        value,
        "Invalid value",
        f"Valid options: {', '.join(sorted(valid_values))}",
      )

    # Return original case from valid_values
    for valid in valid_values:
      if valid.lower() == value:  # noqa: E111
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
  """  # noqa: E111
  return ServiceValidationError(str(error))  # noqa: E111
