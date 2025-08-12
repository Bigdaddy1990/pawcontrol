"""Utility helpers for Paw Control (clean minimal set)."""
from __future__ import annotations

from math import atan2, cos, radians, sin, sqrt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return haversine distance in meters between two lat/lon points."""
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    c = 2*atan2(sqrt(a), sqrt(1-a))
    return R * c

def calculate_speed_kmh(distance_m: float, duration_s: float) -> float:
    if duration_s <= 0:
        return 0.0
    return (distance_m / 1000.0) / (duration_s / 3600.0)

def validate_coordinates(lat: float, lon: float) -> bool:
    return (
        isinstance(lat, int | float)
        and isinstance(lon, int | float)
        and -90.0 <= lat <= 90.0
        and -180.0 <= lon <= 180.0
    )

def format_coordinates(lat: float, lon: float) -> str:
    return f"{lat:.6f},{lon:.6f}"

async def safe_service_call(
    hass: HomeAssistant,
    domain: str,
    service: str,
    data: dict[str, Any] | None = None,
) -> None:
    try:
        await hass.services.async_call(domain, service, data or {}, blocking=False)
    except Exception:  # noqa: BLE001
        # Swallow errors to avoid cascading failures from optional notifications etc.
        return
