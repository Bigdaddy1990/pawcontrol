"""Shared validation helpers for flows and services."""

from __future__ import annotations

from typing import Any, cast

from .const import CONF_DOG_NAME
from .exceptions import ServiceValidationError, ValidationError
from .validation import validate_coordinate, validate_dog_name, validate_interval


def normalise_existing_names(existing_names: set[str] | None) -> set[str]:
  """Return a lowercased set of existing names for comparisons."""

  return {
    name.strip().lower()
    for name in (existing_names or set())
    if isinstance(name, str) and name.strip()
  }


def validate_unique_dog_name(
  raw_name: Any,
  *,
  existing_names: set[str] | None = None,
  field: str = CONF_DOG_NAME,
  required: bool = True,
) -> str | None:
  """Validate a dog name and check for duplicates."""

  dog_name = validate_dog_name(raw_name, field=field, required=required)
  if dog_name is None:
    return None

  if dog_name.lower() in normalise_existing_names(existing_names):
    raise ValidationError(field, raw_name, "dog_name_already_exists")

  return dog_name


def validate_coordinate_pair(
  latitude: Any,
  longitude: Any,
  *,
  latitude_field: str = "latitude",
  longitude_field: str = "longitude",
) -> tuple[float, float]:
  """Validate GPS coordinates and return them as floats."""

  lat = validate_coordinate(
    latitude,
    field=latitude_field,
    minimum=-90.0,
    maximum=90.0,
  )
  lon = validate_coordinate(
    longitude,
    field=longitude_field,
    minimum=-180.0,
    maximum=180.0,
  )
  return cast(float, lat), cast(float, lon)


def format_coordinate_validation_error(error: ValidationError) -> str:
  """Format coordinate validation errors for service responses."""

  field = error.field.replace("_", " ")
  constraint = error.constraint
  if constraint == "coordinate_required":
    return f"{field} is required"
  if constraint == "coordinate_not_numeric":
    return f"{field} must be a number"
  if constraint == "coordinate_out_of_range":
    if error.min_value is not None and error.max_value is not None:
      return f"{field} must be between {error.min_value} and {error.max_value}"
    return f"{field} is out of range"
  return f"{field} is invalid"


def validate_service_coordinates(
  latitude: Any,
  longitude: Any,
  *,
  latitude_field: str = "latitude",
  longitude_field: str = "longitude",
) -> tuple[float, float]:
  """Validate service GPS coordinates and raise service validation errors."""

  try:
    return validate_coordinate_pair(
      latitude,
      longitude,
      latitude_field=latitude_field,
      longitude_field=longitude_field,
    )
  except ValidationError as err:
    raise ServiceValidationError(
      format_coordinate_validation_error(err),
    ) from err


def safe_validate_interval(
  value: Any,
  *,
  default: int,
  minimum: int,
  maximum: int,
  field: str,
  clamp: bool = True,
  required: bool = False,
) -> int:
  """Validate an interval value and fall back to a default on errors."""

  try:
    return validate_interval(
      value,
      field=field,
      minimum=minimum,
      maximum=maximum,
      default=default,
      clamp=clamp,
      required=required,
    )
  except ValidationError:
    return default
