"""Centralized validators for config and options flows."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    CONF_DOG_NAME,
    CONF_GPS_SOURCE,
    MAX_DOG_NAME_LENGTH,
    MIN_DOG_NAME_LENGTH,
    MAX_GEOFENCE_RADIUS,
    MIN_GEOFENCE_RADIUS,
)
from .exceptions import ValidationError


def _coerce_int(field: str, value: Any) -> int:
    if isinstance(value, bool):
        raise ValidationError(field, value, "timer_not_numeric")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValidationError(field, value, "timer_not_numeric")
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(field, value, "timer_not_numeric")
        try:
            return int(stripped)
        except ValueError as err:
            raise ValidationError(field, value, "timer_not_numeric") from err
    raise ValidationError(field, value, "timer_not_numeric")


def _coerce_float(field: str, value: Any) -> float:
    if isinstance(value, bool):
        raise ValidationError(field, value, "radius_not_numeric")
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValidationError(field, value, "radius_not_numeric")
        try:
            return float(stripped)
        except ValueError as err:
            raise ValidationError(field, value, "radius_not_numeric") from err
    raise ValidationError(field, value, "radius_not_numeric")


def validate_name(
    raw_name: Any,
    *,
    field: str = CONF_DOG_NAME,
    min_length: int = MIN_DOG_NAME_LENGTH,
    max_length: int = MAX_DOG_NAME_LENGTH,
) -> str:
    """Validate and normalize a name string."""

    if not isinstance(raw_name, str):
        raise ValidationError(field, raw_name, "name_invalid_type")

    name = raw_name.strip()
    if not name:
        raise ValidationError(field, raw_name, "name_required")
    if len(name) < min_length:
        raise ValidationError(
            field,
            name,
            "name_too_short",
            min_value=min_length,
        )
    if len(name) > max_length:
        raise ValidationError(
            field,
            name,
            "name_too_long",
            max_value=max_length,
        )
    return name


def validate_timer(
    value: Any,
    *,
    field: str,
    min_value: int,
    max_value: int,
) -> int:
    """Validate a numeric timer input and return an integer value."""

    timer_value = _coerce_int(field, value)
    if timer_value < min_value or timer_value > max_value:
        raise ValidationError(
            field,
            timer_value,
            "timer_out_of_range",
            min_value=min_value,
            max_value=max_value,
        )
    return timer_value


def validate_radius(
    value: Any,
    *,
    field: str,
    min_value: int = MIN_GEOFENCE_RADIUS,
    max_value: int = MAX_GEOFENCE_RADIUS,
) -> float:
    """Validate a radius input in meters and return a numeric value."""

    radius_value = _coerce_float(field, value)
    if radius_value < min_value or radius_value > max_value:
        raise ValidationError(
            field,
            radius_value,
            "radius_out_of_range",
            min_value=min_value,
            max_value=max_value,
        )
    return radius_value


def validate_gps_source(
    hass: HomeAssistant,
    gps_source: Any,
    *,
    field: str = CONF_GPS_SOURCE,
    allow_manual: bool = True,
) -> str:
    """Validate a GPS source entity or manual selection."""

    if not isinstance(gps_source, str):
        raise ValidationError(field, gps_source, "gps_source_required")

    candidate = gps_source.strip()
    if not candidate:
        raise ValidationError(field, gps_source, "gps_source_required")

    if allow_manual and candidate == "manual":
        return candidate

    state = hass.states.get(candidate)
    if state is None:
        raise ValidationError(field, candidate, "gps_source_not_found")
    if state.state in {"unknown", "unavailable"}:
        raise ValidationError(field, candidate, "gps_source_unavailable")

    return candidate
