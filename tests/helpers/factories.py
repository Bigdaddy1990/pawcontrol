"""Shared factories for frequently reused PawControl test payloads."""

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, Mock

from custom_components.pawcontrol.types import CoordinatorDogData


def build_api_client_mock(
    *,
    connected: bool = True,
    dog_data: Mapping[str, object] | None = None,
) -> Mock:
    """Build a reusable async API client mock with sensible defaults."""
    client = Mock()
    client.is_connected = connected
    client.async_get_dog_data = AsyncMock(return_value=dict(dog_data or {}))
    client.async_update_dog_data = AsyncMock(return_value=None)
    client.async_get_system_status = AsyncMock(return_value={"status": "ok"})
    return client


def build_coordinator_payload(
    *,
    dog_id: str = "test_dog",
    dog_name: str = "Buddy",
    status: str = "online",
    state: str = "resting",
    zone: str = "home",
    visitor_mode_active: bool = False,
) -> CoordinatorDogData:
    """Build a coordinator payload shape used by entity and coordinator tests."""
    return {
        "dog_info": {"dog_id": dog_id, "dog_name": dog_name},
        "status": status,
        "status_snapshot": {"state": state},
        "visitor_mode_active": visitor_mode_active,
        "gps": {"zone": zone},
        "feeding": {},
        "walk": {},
        "health": {},
    }


def build_coordinator_payload_variant(variant: str) -> CoordinatorDogData:
    """Return common coordinator payload variants for test matrices."""
    variants: dict[str, dict[str, Any]] = {
        "online_home": {},
        "offline": {"status": "offline", "state": "unknown"},
        "visitor_mode": {"visitor_mode_active": True},
        "outside_home": {"zone": "park", "state": "walking"},
    }
    if variant not in variants:
        msg = f"Unknown payload variant: {variant}"
        raise ValueError(msg)
    return build_coordinator_payload(**variants[variant])
