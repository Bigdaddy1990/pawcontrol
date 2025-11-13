from __future__ import annotations

from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from custom_components.pawcontrol.const import EVENT_GEOFENCE_ENTERED
from custom_components.pawcontrol.geofencing import (
    GeofenceType,
    PawControlGeofencing,
)
from custom_components.pawcontrol.types import (
    GeofenceStoragePayload,
    GeofenceZoneStoragePayload,
    GPSLocation,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.mark.integration
@pytest.mark.asyncio
async def test_geofencing_restores_zones_and_notifies_on_entry(
    hass: HomeAssistant,
) -> None:
    """Stored geofences should load with metadata and emit enter events."""

    geofencing = PawControlGeofencing(hass, "integration-entry")

    timestamp = dt_util.utcnow().isoformat()
    stored_zone: GeofenceZoneStoragePayload = {
        "id": "city_park",
        "name": "City Park",
        "type": GeofenceType.SAFE_ZONE.value,
        "latitude": 40.0005,
        "longitude": -105.0005,
        "radius": 120.0,
        "enabled": True,
        "alerts_enabled": True,
        "description": "Stored park zone",
        "created_at": timestamp,
        "updated_at": timestamp,
        "metadata": {
            "auto_created": False,
            "color": "#0099FF",
            "notes": "Play area",
            "tags": {"0": "city", "1": 42, "2": "run"},
        },
    }
    stored_payload: GeofenceStoragePayload = {
        "zones": {"city_park": stored_zone},
        "last_updated": timestamp,
    }
    await geofencing._store.async_save(stored_payload)

    notify = AsyncMock(return_value=None)
    geofencing.set_notification_manager(
        SimpleNamespace(async_send_notification=notify)
    )

    original_async_create_task = hass.async_create_task

    def _async_create_task(self: HomeAssistant, coro, *, name=None):
        return original_async_create_task(coro)

    hass.async_create_task = MethodType(_async_create_task, hass)

    events: list[dict[str, object]] = []
    hass.bus.async_listen(
        EVENT_GEOFENCE_ENTERED,
        lambda event: events.append(dict(event.data)),
    )

    await geofencing.async_initialize(
        dogs=["buddy"],
        enabled=True,
        use_home_location=False,
    )

    try:
        zone = geofencing.get_zone("city_park")
        assert zone is not None
        assert zone.metadata["notes"] == "Play area"
        assert zone.metadata["tags"] == ["city", "run"]
        assert zone.metadata["color"] == "#0099FF"

        location = GPSLocation(
            latitude=stored_zone["latitude"],
            longitude=stored_zone["longitude"],
            accuracy=3.5,
            altitude=0.0,
        )
        await geofencing.async_update_location("buddy", location)
        await hass.async_block_till_done()

        notify.assert_awaited_once()
        payload = notify.await_args.kwargs["data"]
        assert payload["zone_id"] == "city_park"
        assert payload["zone_type"] == GeofenceType.SAFE_ZONE.value
        assert payload["event_type"] == "entered"
        assert payload["distance_from_center_m"] == pytest.approx(0.0, abs=0.5)
        assert payload["accuracy"] == pytest.approx(3.5)

        assert events, "Expected a geofence enter event to be fired"
        event_data = events[0]
        assert event_data["zone_id"] == "city_park"
        assert event_data["zone_type"] == GeofenceType.SAFE_ZONE.value
        assert event_data["dog_id"] == "buddy"
    finally:
        hass.async_create_task = original_async_create_task
        await geofencing.async_cleanup()
        await hass.async_block_till_done()
