from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import cast
from unittest.mock import MagicMock

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.binary_sensor import (
    PawControlGardenPoopPendingBinarySensor,
    PawControlGeofenceAlertBinarySensor,
    PawControlHealthAwareFeedingBinarySensor,
    PawControlHealthEmergencyBinarySensor,
    PawControlIsHomeBinarySensor,
    PawControlIsHungryBinarySensor,
    PawControlOnlineBinarySensor,
    PawControlWalkInProgressBinarySensor,
)
from custom_components.pawcontrol.const import (
    MODULE_FEEDING,
    MODULE_GARDEN,
    MODULE_GPS,
    MODULE_WALK,
)
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.types import (
    CoordinatorDataPayload,
    CoordinatorDogData,
    FeedingModulePayload,
    GardenModulePayload,
    GPSModulePayload,
    PawControlConfigEntry,
    WalkModulePayload,
)
from homeassistant.util import dt as dt_util


@dataclass
class _DummyConfigEntry:
    entry_id: str


class _DummyCoordinator:
    """Minimal coordinator double for binary sensor tests."""

    def __init__(self, dog_id: str, enabled: Mapping[str, frozenset[str]]) -> None:
        self.data: CoordinatorDataPayload = cast(CoordinatorDataPayload, {})
        self._enabled_modules = enabled
        self.config_entry = cast(PawControlConfigEntry, _DummyConfigEntry("entry"))
        self.last_update_success = True
        self.runtime_managers = MagicMock()
        self.runtime_managers.garden_manager = None

    def async_add_listener(self, _callback):  # pragma: no cover - coordinator protocol
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - protocol
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return self._enabled_modules.get(dog_id, frozenset())

    @property
    def available(self) -> bool:
        return True


@pytest.fixture
def coordinator() -> _DummyCoordinator:
    """Return a coordinator double with default configuration."""

    enabled = {
        "dog-1": frozenset({MODULE_FEEDING, MODULE_WALK, MODULE_GPS, MODULE_GARDEN})
    }
    return _DummyCoordinator("dog-1", enabled)


@pytest.mark.asyncio
async def test_online_binary_sensor_attributes_typed(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Ensure the online binary sensor exports typed attributes."""

    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {
                "dog_id": "dog-1",
                "dog_name": "Buddy",
                "dog_breed": "Labrador",
            },
            "status": "online",
            "last_update": dt_util.utcnow().isoformat(),
        },
    )

    sensor = PawControlOnlineBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    attrs = sensor.extra_state_attributes
    assert attrs["sensor_type"] == "online"
    assert attrs["dog_name"] == "Buddy"
    assert attrs["status"] == "online"
    assert attrs["system_health"] == "healthy"
    assert attrs["enabled_modules"] == sorted(
        [MODULE_FEEDING, MODULE_WALK, MODULE_GPS, MODULE_GARDEN]
    )


@pytest.mark.asyncio
async def test_is_hungry_binary_sensor_uses_typed_feeding_payload(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Verify the hungry sensor derives hunger level from the typed feeding payload."""

    feeding_payload = cast(
        FeedingModulePayload,
        {
            "status": "ready",
            "is_hungry": True,
            "last_feeding_hours": 9.0,
            "next_feeding_due": "2024-04-01T18:00:00+00:00",
            "feedings_today": {"breakfast": 1},
            "total_feedings_today": 1,
            "daily_amount_consumed": 150.0,
            "daily_amount_target": 300.0,
            "daily_target": 300.0,
            "daily_amount_percentage": 50,
            "schedule_adherence": 90,
            "missed_feedings": [],
            "feedings": [],
            "daily_stats": {
                "total_feedings": 1,
                "average_daily_feedings": 1.0,
                "average_daily_amount": 150.0,
                "most_common_meal": "breakfast",
                "schedule_adherence": 90,
                "daily_target_met_percentage": 0,
            },
            "medication_with_meals": False,
            "health_aware_feeding": False,
            "weight_goal": None,
            "emergency_mode": None,
            "health_emergency": False,
            "health_feeding_status": "balanced",
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {
                "dog_id": "dog-1",
                "dog_name": "Buddy",
            },
            MODULE_FEEDING: feeding_payload,
        },
    )

    sensor = PawControlIsHungryBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["hunger_level"] == "hungry"
    assert attrs["last_feeding_hours"] == pytest.approx(9.0)


@pytest.mark.asyncio
async def test_walk_in_progress_binary_sensor_attributes(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Ensure walk progress metadata is exported with typed payloads."""

    walk_payload = cast(
        WalkModulePayload,
        {
            "status": "active",
            "walk_in_progress": True,
            "current_walk_start": "2024-04-01T10:00:00+00:00",
            "current_walk_duration": 12.5,
            "current_walk_distance": 1.2,
            "average_walk_duration": 30.0,
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_WALK: walk_payload,
        },
    )

    sensor = PawControlWalkInProgressBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["walk_start_time"] == "2024-04-01T10:00:00+00:00"
    assert attrs["walk_duration"] == pytest.approx(12.5)
    assert attrs["walk_distance"] == pytest.approx(1.2)
    assert attrs["estimated_remaining"] == 17


@pytest.mark.asyncio
async def test_is_home_binary_sensor_serializes_gps_payload(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Verify GPS payload coercion preserves typed extras."""

    last_seen_dt = dt_util.utcnow() - timedelta(minutes=2)
    gps_payload = cast(
        GPSModulePayload,
        {
            "status": "tracking",
            "zone": "home",
            "accuracy": 12.0,
            "distance_from_home": 0.3,
            "last_seen": last_seen_dt,
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_GPS: gps_payload,
        },
    )

    sensor = PawControlIsHomeBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["current_zone"] == "home"
    assert attrs["distance_from_home"] == pytest.approx(0.3)
    assert attrs["accuracy"] == pytest.approx(12.0)
    assert attrs["last_seen"] == last_seen_dt.isoformat()


@pytest.mark.asyncio
async def test_geofence_alert_sensor_requires_boolean_payload(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Ensure the geofence alert sensor only toggles for strict booleans."""

    invalid_payload = cast(
        GPSModulePayload,
        {
            "status": "tracking",
            "zone": "yard",
            "geofence_alert": "false",
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_GPS: invalid_payload,
        },
    )

    sensor = PawControlGeofenceAlertBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is False
    attrs = sensor.extra_state_attributes
    assert attrs["sensor_type"] == "geofence_alert"

    valid_payload = cast(
        GPSModulePayload,
        {
            "status": "tracking",
            "zone": "vet",
            "geofence_alert": True,
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_GPS: valid_payload,
        },
    )

    sensor_valid = PawControlGeofenceAlertBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor_valid.hass = hass

    assert sensor_valid.is_on is True


@pytest.mark.asyncio
async def test_health_aware_feeding_sensor_typed_attributes(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Ensure health aware feeding extras remain typed."""

    feeding_payload = cast(
        FeedingModulePayload,
        {
            "status": "ready",
            "health_aware_feeding": True,
            "portion_adjustment_factor": 1.1,
            "health_conditions": ["diabetes"],
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_FEEDING: feeding_payload,
        },
    )

    sensor = PawControlHealthAwareFeedingBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["portion_adjustment_factor"] == pytest.approx(1.1)
    assert attrs["health_conditions"] == ["diabetes"]


@pytest.mark.asyncio
async def test_health_emergency_sensor_sanitises_payload(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Verify the health emergency sensor normalises invalid payloads."""

    invalid_payload = cast(
        FeedingModulePayload,
        {
            "status": "ready",
            "health_emergency": "true",
            "emergency_mode": {
                "emergency_type": 42,
                "portion_adjustment": "increase",
                "activated_at": 12,
                "expires_at": {"unexpected": "value"},
                "status": None,
            },
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_FEEDING: invalid_payload,
        },
    )

    sensor = PawControlHealthEmergencyBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is False
    attrs = sensor.extra_state_attributes
    assert "emergency_type" not in attrs
    assert "portion_adjustment" not in attrs
    assert "activated_at" not in attrs
    assert "expires_at" not in attrs
    assert "status" not in attrs

    valid_payload = cast(
        FeedingModulePayload,
        {
            "status": "ready",
            "health_emergency": True,
            "emergency_mode": {
                "emergency_type": "medical",
                "portion_adjustment": 0.75,
                "activated_at": "2024-04-01T08:30:00+00:00",
                "expires_at": None,
                "status": "active",
            },
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_FEEDING: valid_payload,
        },
    )

    sensor_valid = PawControlHealthEmergencyBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor_valid.hass = hass

    assert sensor_valid.is_on is True
    valid_attrs = sensor_valid.extra_state_attributes
    assert valid_attrs["emergency_type"] == "medical"
    assert valid_attrs["portion_adjustment"] == pytest.approx(0.75)
    assert valid_attrs["activated_at"] == "2024-04-01T08:30:00+00:00"
    assert valid_attrs["expires_at"] is None
    assert valid_attrs["status"] == "active"


@pytest.mark.asyncio
async def test_garden_pending_confirmation_sensor_attributes(
    hass, coordinator: _DummyCoordinator
) -> None:
    """Ensure pending confirmations propagate typed metadata."""

    confirmation = {
        "session_id": "session-1",
        "created": dt_util.utcnow().isoformat(),
        "expires": (dt_util.utcnow() + timedelta(hours=1)).isoformat(),
    }
    garden_payload = cast(
        GardenModulePayload,
        {
            "status": "ready",
            "pending_confirmations": [confirmation],
        },
    )
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
            MODULE_GARDEN: garden_payload,
        },
    )

    sensor = PawControlGardenPoopPendingBinarySensor(
        cast(PawControlCoordinator, coordinator), "dog-1", "Buddy"
    )
    sensor.hass = hass

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert attrs["pending_confirmations"] == [confirmation]
    assert attrs["pending_confirmation_count"] == 1
