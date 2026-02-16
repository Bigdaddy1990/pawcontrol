"""Validation helpers shared across config and options flows.

This module defines the stable API for input validation inside config and
options flows. It wraps the core routines in `validation` so flow steps can rely
on a consistent interface without coupling to the underlying implementation.
Centralizing these wrappers keeps flow modules lean and improves maintainability
as validation behavior evolves.
"""

from __future__ import annotations

from typing import Any

from .const import CONF_DOG_NAME
from .exceptions import ValidationError
from .validation import (
  InputValidator,
  validate_dog_name,
  validate_gps_interval,
  validate_interval,
  validate_time_window,
)


def validate_flow_dog_name(
  name: Any,
  *,
  field: str = CONF_DOG_NAME,
  required: bool = True,
) -> str | None:
  """Validate dog names submitted through config or options flows."""  # noqa: E111

  return validate_dog_name(name, field=field, required=required)  # noqa: E111


def validate_flow_gps_coordinates(
  latitude: Any,
  longitude: Any,
  *,
  latitude_field: str = "latitude",
  longitude_field: str = "longitude",
) -> tuple[float, float]:
  """Validate GPS coordinates for flow submission."""  # noqa: E111

  return InputValidator.validate_gps_coordinates(  # noqa: E111
    latitude,
    longitude,
    latitude_field=latitude_field,
    longitude_field=longitude_field,
  )


def validate_flow_gps_accuracy(
  value: Any,
  *,
  field: str,
  min_value: float,
  max_value: float,
  required: bool = True,
) -> float | None:
  """Validate GPS accuracy settings submitted via flows."""  # noqa: E111

  return InputValidator.validate_gps_accuracy(  # noqa: E111
    value,
    field=field,
    min_value=min_value,
    max_value=max_value,
    required=required,
  )


def validate_flow_geofence_radius(
  value: Any,
  *,
  field: str,
  min_value: float,
  max_value: float,
  required: bool = True,
) -> float | None:
  """Validate geofence radius settings submitted via flows."""  # noqa: E111

  return InputValidator.validate_geofence_radius(  # noqa: E111
    value,
    field=field,
    min_value=min_value,
    max_value=max_value,
    required=required,
  )


def validate_flow_gps_interval(
  value: Any,
  *,
  field: str,
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
) -> int | None:
  """Validate GPS update intervals submitted via flows."""  # noqa: E111

  return validate_gps_interval(  # noqa: E111
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    default=default,
    clamp=clamp,
    required=required,
  )


def validate_flow_timer_interval(
  value: Any,
  *,
  field: str,
  minimum: int,
  maximum: int,
  default: int | None = None,
  clamp: bool = False,
  required: bool = False,
) -> int:
  """Validate timer/interval values submitted via flows."""  # noqa: E111

  return validate_interval(  # noqa: E111
    value,
    field=field,
    minimum=minimum,
    maximum=maximum,
    default=default,
    clamp=clamp,
    required=required,
  )


def validate_flow_time_window(
  start: Any,
  end: Any,
  *,
  start_field: str,
  end_field: str,
  default_start: str | None = None,
  default_end: str | None = None,
) -> tuple[str, str]:
  """Validate a start/end time window for flow inputs."""  # noqa: E111

  return validate_time_window(  # noqa: E111
    start,
    end,
    start_field=start_field,
    end_field=end_field,
    default_start=default_start,
    default_end=default_end,
  )


__all__ = [
  "ValidationError",
  "validate_flow_dog_name",
  "validate_flow_geofence_radius",
  "validate_flow_gps_accuracy",
  "validate_flow_gps_coordinates",
  "validate_flow_gps_interval",
  "validate_flow_time_window",
  "validate_flow_timer_interval",
  "validate_flow_gps_coordinates",
  "validate_flow_timer_interval",
  "validate_flow_time_window",
]
