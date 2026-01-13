"""Helpers for constructing centralized dog status snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from .types import DogStatusSnapshot, JSONMapping, JSONMutableMapping

_DEFAULT_SAFE_ZONES: frozenset[str] = frozenset(
    {"home", "park", "vet", "friend_house"}
)


def build_dog_status_snapshot(
    dog_id: str, dog_data: Mapping[str, object]
) -> DogStatusSnapshot:
    """Return the centralized status snapshot for a dog."""

    feeding_data = _coerce_mapping(dog_data.get("feeding"))
    walk_data = _coerce_mapping(dog_data.get("walk"))
    gps_data = _coerce_mapping(dog_data.get("gps"))

    on_walk = bool(walk_data.get("walk_in_progress", False))
    needs_walk = bool(walk_data.get("needs_walk", False))
    is_hungry = bool(feeding_data.get("is_hungry", False))

    zone = _coerce_zone_name(gps_data.get("zone"))
    geofence_status = _coerce_mapping(gps_data.get("geofence_status"))
    in_safe_zone = _resolve_safe_zone(geofence_status, zone)
    is_home = zone == "home"

    state = _derive_status_state(
        on_walk=on_walk,
        is_home=is_home,
        is_hungry=is_hungry,
        needs_walk=needs_walk,
        zone=zone,
    )

    return {
        "dog_id": dog_id,
        "state": state,
        "zone": zone,
        "is_home": is_home,
        "in_safe_zone": in_safe_zone,
        "on_walk": on_walk,
        "needs_walk": needs_walk,
        "is_hungry": is_hungry,
    }


def _coerce_mapping(value: object | None) -> JSONMutableMapping:
    """Return ``value`` as a mutable mapping when possible."""

    if isinstance(value, Mapping):
        return cast(JSONMutableMapping, value)
    return cast(JSONMutableMapping, {})


def _coerce_zone_name(value: object | None) -> str | None:
    """Return a normalized zone name."""

    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _resolve_safe_zone(
    geofence_status: JSONMapping, zone: str | None
) -> bool:
    """Determine safe-zone membership from geofence and zone data."""

    if geofence_status:
        candidate = geofence_status.get("in_safe_zone")
        if isinstance(candidate, bool):
            return candidate
        if isinstance(candidate, (int, float)):
            return bool(candidate)
    if zone is None:
        return True
    return zone in _DEFAULT_SAFE_ZONES


def _derive_status_state(
    *,
    on_walk: bool,
    is_home: bool,
    is_hungry: bool,
    needs_walk: bool,
    zone: str | None,
) -> str:
    """Return the string status state for the dog."""

    if on_walk:
        return "walking"
    if is_home:
        if is_hungry:
            return "hungry"
        if needs_walk:
            return "needs_walk"
        return "home"
    if zone:
        return f"at_{zone}"
    return "away"
