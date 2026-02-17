"""Unit tests for the PawControl GPS device tracker entity."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import json

import pytest

from custom_components.pawcontrol.device_tracker import PawControlGPSTracker
from custom_components.pawcontrol.types import GPSModulePayload


class DummyCoordinator:
    """Lightweight coordinator stub exposing the tracker access surface."""  # noqa: E111

    available = True  # noqa: E111

    def __init__(self, dog_data: Mapping[str, object] | None) -> None:  # noqa: E111
        self._dog_data = dog_data
        self.config_entry = None

    def get_dog_data(self, dog_id: str) -> Mapping[str, object] | None:  # noqa: E111
        return self._dog_data


def _build_tracker(payload: GPSModulePayload | None) -> PawControlGPSTracker:
    coordinator = DummyCoordinator({"gps": payload} if payload is not None else {})  # noqa: E111
    tracker = PawControlGPSTracker(coordinator, "dog-1", "Maple")  # noqa: E111
    return tracker  # noqa: E111


def test_extra_state_attributes_coerce_runtime_payload() -> None:
    """Ensure GPS telemetry is exported as JSON-safe, typed attributes."""  # noqa: E111

    now = datetime.now(tz=UTC)  # noqa: E111
    payload: GPSModulePayload = {  # noqa: E111
        "status": "tracking",
        "altitude": 12.5,
        "speed": 4.2,
        "heading": 270,
        "satellites": 8,
        "source": "gps",
        "last_seen": now,
        "distance_from_home": 123.4,
        "current_route": {
            "id": "route-1",
            "name": "Morning Walk",
            "active": True,
            "start_time": now - timedelta(minutes=5),
            "duration": 300.0,
            "distance": 560.0,
            "points": [
                {"latitude": 40.0, "longitude": -74.0},
                {"latitude": 40.1, "longitude": -74.1},
                {"latitude": 40.2, "longitude": -74.2},
            ],
        },
        "geofence_status": {
            "in_safe_zone": True,
            "zone_name": "Backyard",
            "distance_to_boundary": 4.5,
        },
        "walk_info": {
            "active": True,
            "walk_id": "walk-1",
            "start_time": now - timedelta(minutes=10),
        },
    }

    tracker = _build_tracker(payload)  # noqa: E111
    attrs = tracker.extra_state_attributes  # noqa: E111

    assert attrs["dog_id"] == "dog-1"  # noqa: E111
    assert attrs["tracker_type"] == "gps"  # noqa: E111
    assert attrs["route_active"] is True  # noqa: E111
    assert attrs["route_points"] == 3  # noqa: E111
    assert attrs["zone_name"] == "Backyard"  # noqa: E111
    assert attrs["walk_id"] == "walk-1"  # noqa: E111
    assert isinstance(attrs["last_seen"], str)  # noqa: E111
    assert attrs["route_start_time"] is not None  # noqa: E111
    assert isinstance(attrs["distance_from_home"], float)  # noqa: E111
    json.dumps(attrs)  # noqa: E111


@pytest.mark.asyncio
async def test_async_export_route_json_builds_typed_payload() -> None:
    """The JSON route exporter should emit the typed export payload."""  # noqa: E111

    now = datetime.now(tz=UTC)  # noqa: E111
    tracker = _build_tracker({"status": "tracking"})  # noqa: E111

    tracker._route_points.append(  # type: ignore[attr-defined]  # noqa: E111
        {
            "latitude": 40.1,
            "longitude": -74.5,
            "timestamp": now - timedelta(minutes=2),
            "accuracy": 5,
        }
    )
    tracker._route_points.append(  # type: ignore[attr-defined]  # noqa: E111
        {
            "latitude": 40.2,
            "longitude": -74.6,
            "timestamp": now,
            "accuracy": 4,
        }
    )

    payload = await tracker.async_export_route("json")  # noqa: E111
    assert payload is not None  # noqa: E111
    assert payload["format"] == "json"  # noqa: E111
    assert payload["routes_count"] == 1  # noqa: E111

    route = payload["content"]["routes"][0]  # noqa: E111
    assert route["route_quality"] == "basic"  # noqa: E111
    assert route["duration_minutes"] is not None  # noqa: E111
    assert route["gps_points"][0]["timestamp"].endswith("Z") is False  # noqa: E111


@pytest.mark.asyncio
async def test_async_export_route_handles_invalid_format() -> None:
    """Unsupported export formats should return ``None`` without raising."""  # noqa: E111

    tracker = _build_tracker({"status": "tracking"})  # noqa: E111
    tracker._route_points.append(  # type: ignore[attr-defined]  # noqa: E111
        {
            "latitude": 40.0,
            "longitude": -74.0,
            "timestamp": datetime.now(tz=UTC),
            "accuracy": 3,
        }
    )

    assert await tracker.async_export_route("unsupported") is None  # noqa: E111
