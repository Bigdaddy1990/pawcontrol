"""Validation helpers shared across config and options flows.

This module provides a stable API for input validation within config and options
flows. It wraps core validation logic from the `validation` module, offering
a clear and consistent interface for flow steps to use. By centralizing these
wrappers, it decouples the flows from the direct implementation of the
validators, improving maintainability.
"""

from __future__ import annotations

from typing import Any

from .const import CONF_DOG_NAME
from .exceptions import ValidationError
from .validation import (
  InputValidator,
  validate_dog_name,
  validate_interval,
  validate_time_window,
)


def validate_flow_dog_name(
  name: Any,
  *,
  field: str = CONF_DOG_NAME,
  required: bool = True,
) -> str | None:
  """Validate dog names submitted through config or options flows."""

  return validate_dog_name(name, field=field, required=required)


def validate_flow_gps_coordinates(
  latitude: Any,
  longitude: Any,
  *,
  latitude_field: str = "latitude",
  longitude_field: str = "longitude",
) -> tuple[float, float]:
  """Validate GPS coordinates for flow submission."""

  return InputValidator.validate_gps_coordinates(
    latitude,
    longitude,
    latitude_field=latitude_field,
    longitude_field=longitude_field,
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
  """Validate timer/interval values submitted via flows."""

  return validate_interval(
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
  """Validate a start/end time window for flow inputs."""

  return validate_time_window(
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
  "validate_flow_gps_coordinates",
  "validate_flow_time_window",
  "validate_flow_timer_interval",
]
