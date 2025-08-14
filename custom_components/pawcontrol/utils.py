"""Utility helpers for Paw Control (clean minimal set)."""

from __future__ import annotations

from contextlib import suppress
from math import atan2, cos, isfinite, radians, sin, sqrt
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from homeassistant.core import HomeAssistant


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return haversine distance in meters between two lat/lon points."""
    radius = 6_371_000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return radius * c


def calculate_speed_kmh(distance_m: float, duration_s: float) -> float:
    """Return speed in km/h given distance in meters and duration in seconds."""
    if duration_s <= 0:
        return 0.0
    # Use direct conversion from m/s to km/h for clarity
    return (distance_m / duration_s) * 3.6


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude values."""
    # bool is a subclass of int and should be rejected explicitly
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
) -> None:
    """Call a Home Assistant service safely."""
    with suppress(HomeAssistantError, ValueError):
        await hass.services.async_call(domain, service, data or {}, blocking=False)
