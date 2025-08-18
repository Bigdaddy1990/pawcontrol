"""Utility helpers for Paw Control (clean minimal set)."""

from __future__ import annotations

from math import atan2, cos, isfinite, pi, radians, sin, sqrt
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
    # Early exit to skip trigonometric calculations when coordinates are identical
    if lat1 == lat2 and lon1 == lon2:
        return 0.0

    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)

    s_dphi = sin(dphi / 2.0)
    s_dlam = sin(dlambda / 2.0)

    a = s_dphi * s_dphi + cos(phi1) * cos(phi2) * s_dlam * s_dlam

    # Clamp against numerical out-of-range values
    if a <= 0.0:
        return 0.0
    if a >= 1.0:
        # Antipodal case → half of Earth's circumference
        return pi * EARTH_RADIUS_M

    a = min(1.0, max(0.0, a))
    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    return EARTH_RADIUS_M * c


    def calculate_speed_kmh(distance_m: float, duration_s: float) -> float:
        """Return speed in km/h given distance in meters and duration in seconds.

        Args:
            distance_m: Distance in meters (must be non-negative)
            duration_s: Duration in seconds (must be positive and finite)

        Returns:
            Speed in km/h (0.0 for invalid inputs)
        """
        if not isfinite(duration_s) or duration_s <= _EPS_TIME_S:
            return 0.0
        if not isfinite(distance_m) or distance_m < 0:
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
    except Exception:
        return False
