"""Utility helpers for Paw Control (clean minimal set)."""

from __future__ import annotations

import logging
from math import atan2, cos, degrees, isfinite, pi, radians, sin, sqrt
from typing import TYPE_CHECKING, Any, Final

from .const import EARTH_RADIUS_M

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant

# Small epsilon for time/comparison operations to avoid division by near-zero
_EPS_TIME_S: Final[float] = 1e-9


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return haversine distance in meters between two lat/lon points.

    Includes clamping to prevent floating point rounding errors.
    """
    # Return 0 for any non‑finite coordinate values
    if not all(isfinite(val) for val in (lat1, lon1, lat2, lon2)):
        return 0.0

    # Early exit to skip trigonometric calculations when coordinates are identical
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)

    s_dphi = sin(dphi / 2.0)
    s_dlam = sin(dlambda / 2.0)

    a = s_dphi * s_dphi + cos(phi1) * cos(phi2) * s_dlam * s_dlam

    # Clamp against numerical out-of-range values instead of returning early.
    # Returning 0 for tiny negative values would incorrectly report no
    # distance for very close points.  Instead, clamp and handle the edge
    # cases after clamping.
    a = max(0.0, min(1.0, a))

    if a == 0.0:
        return 0.0
    if a == 1.0:
        # Antipodal case → half of Earth's circumference
        return pi * EARTH_RADIUS_M

    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial bearing in degrees from point ``A`` to ``B``.

    The result is normalized to the range ``[0, 360)``.  Non‑finite inputs or
    identical coordinates result in ``0``.
    """

    if not all(isfinite(val) for val in (lat1, lon1, lat2, lon2)):
        return 0.0
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1, phi2 = radians(lat1), radians(lat2)
    dlambda = radians(lon2 - lon1)

    x = sin(dlambda) * cos(phi2)
    y = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dlambda)
    bearing = atan2(x, y)
    return (degrees(bearing) + 360.0) % 360.0


def calculate_speed_kmh(distance_m: float, duration_s: float) -> float:
    """Return speed in km/h given distance in meters and duration in seconds."""
    if not isfinite(duration_s) or duration_s <= _EPS_TIME_S:
        return 0.0
    if not isfinite(distance_m) or distance_m < 0.0:
        return 0.0
    # Convert m/s to km/h
    return (distance_m / duration_s) * 3.6


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude values."""
    # Explicitly reject bool, since bool is a subclass of int in Python
    if isinstance(lat, bool) or isinstance(lon, bool):
        return False

    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False

    if not (isfinite(lat_f) and isfinite(lon_f)):
        return False

    return -90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0


def format_coordinates(lat: float, lon: float) -> str:
    """Format coordinates for display."""
    return f"{lat:.6f},{lon:.6f}"


async def safe_service_call(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: Mapping[str, Any] | None = None,
    *,
    blocking: bool = False,
) -> bool:
    """Call a Home Assistant service safely.

    Returns True/False instead of silently swallowing exceptions.
    """
    try:
        await hass.services.async_call(domain, service, data or {}, blocking=blocking)
        return True
    except Exception as err:  # pragma: no cover - broad for safety
        logging.getLogger(__name__).debug(
            "Service call %s.%s failed: %s", domain, service, err
        )
        return False
