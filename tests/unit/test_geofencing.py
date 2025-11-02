"""Typed storage and notification coverage for the geofencing subsystem."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.pawcontrol.geofencing import (
    GeofenceEvent,
    GeofenceType,
    GeofenceZone,
    PawControlGeofencing,
    calculate_distance,
)
from custom_components.pawcontrol.types import GeofenceZoneMetadata, GPSLocation


@pytest.mark.unit
def test_geofence_zone_storage_roundtrip() -> None:
    """Geofence zone payloads should round-trip through typed storage."""

    metadata: GeofenceZoneMetadata = {
        "auto_created": True,
        "color": "#00FFAA",
        "notes": "Back garden",
    }
    zone = GeofenceZone(
        id="garden",
        name="Garden",
        type=GeofenceType.SAFE_ZONE,
        latitude=52.52,
        longitude=13.405,
        radius=25.0,
        metadata=metadata,
    )

    payload = zone.to_storage_payload()
    assert payload["metadata"]["auto_created"] is True
    assert payload["metadata"]["color"] == "#00FFAA"

    restored = GeofenceZone.from_storage_payload(payload)
    assert restored.metadata["notes"] == "Back garden"
    assert restored.metadata["auto_created"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_save_data_persists_typed_metadata(mock_hass) -> None:
    """Persisted data should include the typed zone metadata."""

    geofencing = PawControlGeofencing(mock_hass, "entry")
    store = MagicMock()
    store.async_save = AsyncMock()
    store.async_load = AsyncMock(return_value=None)
    geofencing._store = store

    geofencing._zones["garden"] = GeofenceZone(
        id="garden",
        name="Garden",
        type=GeofenceType.SAFE_ZONE,
        latitude=52.52,
        longitude=13.405,
        radius=25.0,
        metadata={"notes": "Typed"},
    )

    await geofencing._save_data()

    store.async_save.assert_awaited_once()
    payload = store.async_save.await_args.args[0]
    assert payload["zones"]["garden"]["metadata"]["notes"] == "Typed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notify_zone_event_uses_typed_payload(mock_hass) -> None:
    """Notification payloads should expose the typed geofence structure."""

    geofencing = PawControlGeofencing(mock_hass, "entry")
    notify = AsyncMock()
    manager = SimpleNamespace(async_send_notification=notify)
    geofencing.set_notification_manager(manager)

    zone = GeofenceZone(
        id="restricted",
        name="Restricted",
        type=GeofenceType.RESTRICTED_AREA,
        latitude=40.7128,
        longitude=-74.0060,
        radius=35.0,
    )
    location = GPSLocation(latitude=40.7130, longitude=-74.0055, accuracy=5.0)

    await geofencing._notify_zone_event(
        "doggo", zone, GeofenceEvent.ENTERED, location
    )

    notify.assert_awaited_once()
    payload = notify.await_args.kwargs["data"]

    assert payload["zone_id"] == "restricted"
    assert payload["event_type"] == GeofenceEvent.ENTERED.value
    assert payload["latitude"] == pytest.approx(location.latitude)
    expected_distance = calculate_distance(
        zone.latitude, zone.longitude, location.latitude, location.longitude
    )
    assert payload["distance_from_center_m"] == pytest.approx(
        expected_distance, abs=0.01
    )
    assert payload["accuracy"] == 5.0
