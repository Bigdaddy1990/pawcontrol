"""Helpers for constructing centralized dog status snapshots."""

from collections.abc import Mapping
from typing import cast

from .types import DogStatusSnapshot, JSONMapping, JSONMutableMapping

_DEFAULT_SAFE_ZONES: frozenset[str] = frozenset(
    {"home", "park", "vet", "friend_house"},
)


def build_dog_status_snapshot(
    dog_id: str,
    dog_data: Mapping[str, object],
) -> DogStatusSnapshot:
    """Return the centralized status snapshot for a dog."""  # noqa: E111

    feeding_data = _coerce_mapping(dog_data.get("feeding"))  # noqa: E111
    walk_data = _coerce_mapping(dog_data.get("walk"))  # noqa: E111
    gps_data = _coerce_mapping(dog_data.get("gps"))  # noqa: E111

    on_walk = bool(walk_data.get("walk_in_progress", False))  # noqa: E111
    needs_walk = bool(walk_data.get("needs_walk", False))  # noqa: E111
    is_hungry = bool(feeding_data.get("is_hungry", False))  # noqa: E111

    zone = _coerce_zone_name(gps_data.get("zone"))  # noqa: E111
    geofence_status = _coerce_mapping(gps_data.get("geofence_status"))  # noqa: E111
    in_safe_zone = _resolve_safe_zone(geofence_status, zone)  # noqa: E111
    is_home = zone == "home"  # noqa: E111

    state = _derive_status_state(  # noqa: E111
        on_walk=on_walk,
        is_home=is_home,
        is_hungry=is_hungry,
        needs_walk=needs_walk,
        zone=zone,
    )

    return {  # noqa: E111
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
    """Return ``value`` as a mutable mapping when possible."""  # noqa: E111

    if isinstance(value, Mapping):  # noqa: E111
        return cast(JSONMutableMapping, value)
    return cast(JSONMutableMapping, {})  # noqa: E111


def _coerce_zone_name(value: object | None) -> str | None:
    """Return a normalized zone name."""  # noqa: E111

    if isinstance(value, str):  # noqa: E111
        normalized = value.strip()
        if normalized:
            return normalized  # noqa: E111
    return None  # noqa: E111


def _resolve_safe_zone(geofence_status: JSONMapping, zone: str | None) -> bool:
    """Determine safe-zone membership from geofence and zone data."""  # noqa: E111

    if geofence_status:  # noqa: E111
        candidate = geofence_status.get("in_safe_zone")
        if isinstance(candidate, bool):
            return candidate  # noqa: E111
        if isinstance(candidate, int | float):
            return bool(candidate)  # noqa: E111
    if zone is None:  # noqa: E111
        return True
    return zone in _DEFAULT_SAFE_ZONES  # noqa: E111


def _derive_status_state(
    *,
    on_walk: bool,
    is_home: bool,
    is_hungry: bool,
    needs_walk: bool,
    zone: str | None,
) -> str:
    """Return the string status state for the dog."""  # noqa: E111

    if on_walk:  # noqa: E111
        return "walking"
    if is_home:  # noqa: E111
        if is_hungry:
            return "hungry"  # noqa: E111
        if needs_walk:
            return "needs_walk"  # noqa: E111
        return "home"
    if zone:  # noqa: E111
        return f"at_{zone}"
    return "away"  # noqa: E111
