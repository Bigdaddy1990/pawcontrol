"""Entity state/property matrix tests for PawControl platforms."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("aiohttp")

from homeassistant.const import STATE_HOME, STATE_NOT_HOME, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.binary_sensor import PawControlOnlineBinarySensor
from custom_components.pawcontrol.device_tracker import PawControlGPSTracker
from custom_components.pawcontrol.select import PawControlHealthStatusSelect
from custom_components.pawcontrol.sensor import PawControlDogStatusSensor
from custom_components.pawcontrol.switch import PawControlVisitorModeSwitch
from custom_components.pawcontrol.types import CoordinatorDogData, JSONMutableMapping


@dataclass
class _DummyEntry:
    entry_id: str


class _CoordinatorDouble:
    """Coordinator test double for entity property/state tests."""

    def __init__(self, *, data: dict[str, CoordinatorDogData]) -> None:
        self.data = data
        self.config_entry = _DummyEntry("entry-1")
        self.available = True
        self.last_update_success = True
        self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
        self.last_exception: Exception | None = None

    def async_add_listener(self, _callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - protocol
        return None

    async def async_refresh_dog(self, _dog_id: str) -> None:  # pragma: no cover
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> JSONMutableMapping:
        dog_data = self.data.get(dog_id)
        if not isinstance(dog_data, Mapping):
            return cast(JSONMutableMapping, {})
        module_data = dog_data.get(module)
        if isinstance(module_data, Mapping):
            return cast(JSONMutableMapping, dict(module_data))
        return cast(JSONMutableMapping, {})

    def get_enabled_modules(self, _dog_id: str) -> frozenset[str]:
        return frozenset({"feeding", "walk", "gps", "health"})


_DOG_ID = "dog-1"
_DOG_NAME = "Buddy"


def _coordinator_from_payload(
    payload: Mapping[str, object] | None,
) -> _CoordinatorDouble:
    data: dict[str, CoordinatorDogData] = {}
    if payload is not None:
        data[_DOG_ID] = cast(CoordinatorDogData, dict(payload))
    return _CoordinatorDouble(data=data)


@pytest.mark.parametrize(
    (
        "factory",
        "state_accessor",
        "normal_payload",
        "boundary_payload",
        "missing_payload",
    ),
    [
        (
            lambda coordinator: PawControlDogStatusSensor(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            lambda entity: entity.native_value,
            {
                "status_snapshot": {"state": "calm"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {
                "walk": {"walk_in_progress": True},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {},
        ),
        (
            lambda coordinator: PawControlOnlineBinarySensor(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            lambda entity: entity.is_on,
            {
                "last_update": dt_util.utcnow().isoformat(),
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {
                "last_update": (dt_util.utcnow() - timedelta(minutes=15)).isoformat(),
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {},
        ),
        (
            lambda coordinator: PawControlHealthStatusSelect(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            lambda entity: entity.current_option,
            {
                "health": {"health_status": "excellent"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {
                "health": {"health_status": ""},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {},
        ),
        (
            lambda coordinator: PawControlVisitorModeSwitch(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            lambda entity: entity.is_on,
            {
                "visitor_mode_active": True,
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {
                "visitor_mode_active": False,
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {},
        ),
        (
            lambda coordinator: PawControlGPSTracker(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            lambda entity: entity.state,
            {
                "gps": {"zone": "park", "latitude": 48.1, "longitude": 11.5},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {
                "gps": {"zone": "unknown"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            {},
        ),
    ],
)
def test_entity_properties_cover_normal_boundary_and_missing_api_fields(
    factory: Callable[[_CoordinatorDouble], Any],
    state_accessor: Callable[[Any], object],
    normal_payload: Mapping[str, object],
    boundary_payload: Mapping[str, object],
    missing_payload: Mapping[str, object],
    assert_entity_basics: Callable[[Any], None],
) -> None:
    """Each entity class should expose stable core properties across data variants."""
    for payload in (normal_payload, boundary_payload, missing_payload):
        coordinator = _coordinator_from_payload(payload)
        entity = factory(coordinator)

        # state/native_value/is_on accessor should never crash
        state_accessor(entity)
        assert_entity_basics(entity)


@pytest.mark.parametrize(
    ("zone", "expected_state"),
    [
        ("home", STATE_HOME),
        ("park", "park"),
        ("unknown", STATE_NOT_HOME),
        (None, STATE_NOT_HOME),
    ],
)
def test_device_tracker_zone_mapping_parametrized(
    zone: str | None,
    expected_state: str,
) -> None:
    """GPS zone mapping should map API values to Home Assistant tracker states."""
    coordinator = _coordinator_from_payload(
        {
            "gps": {"zone": zone},
            "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
        },
    )
    entity = PawControlGPSTracker(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.state == expected_state


def test_device_tracker_zone_mapping_missing_dog_returns_unknown_state() -> None:
    """Missing dog payload should map to unknown without raising exceptions."""
    coordinator = _coordinator_from_payload(None)
    entity = PawControlGPSTracker(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "status_snapshot": {"state": "resting"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "resting",
        ),
        (
            {
                "walk": {"walk_in_progress": True},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "walking",
        ),
        (
            {
                "feeding": {"is_hungry": True},
                "gps": {"zone": "home"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "hungry",
        ),
        (
            {
                "walk": {"needs_walk": True},
                "gps": {"zone": "home"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "needs_walk",
        ),
        (
            {
                "gps": {"zone": "forest"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "at_forest",
        ),
        (
            {
                "gps": {"zone": "unknown"},
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            "at_unknown",
        ),
    ],
)
def test_dog_status_sensor_mapping_table_parametrized(
    payload: Mapping[str, object],
    expected: str,
) -> None:
    """Dog status mapping should translate API payload variants to HA states."""
    coordinator = _coordinator_from_payload(payload)
    entity = PawControlDogStatusSensor(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.native_value == expected


@pytest.mark.parametrize(
    "payload",
    [
        {"dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME}},
        {
            "gps": {"zone": object()},
            "feeding": {"is_hungry": None},
            "walk": {"needs_walk": None, "walk_in_progress": None},
            "status_snapshot": None,
            "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
        },
    ],
)
def test_sensor_and_tracker_none_or_unknown_values_do_not_crash(
    payload: Mapping[str, object],
) -> None:
    """None or unknown payload values should not crash entity state access."""
    coordinator = _coordinator_from_payload(payload)
    status_entity = PawControlDogStatusSensor(
        cast(Any, coordinator), _DOG_ID, _DOG_NAME
    )
    tracker_entity = PawControlGPSTracker(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    # Accessing these properties is the assertion: no crash and deterministic fallback.
    assert isinstance(status_entity.native_value, str)
    assert tracker_entity.state is not None


def test_state_changes_reflect_after_coordinator_data_updates() -> None:
    """Coordinator payload changes should be reflected by entities immediately."""
    coordinator = _coordinator_from_payload(
        {
            "status_snapshot": {"state": "resting"},
            "health": {"health_status": "good"},
            "visitor_mode_active": False,
            "gps": {"zone": "home"},
            "last_update": dt_util.utcnow().isoformat(),
            "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
        },
    )

    status_entity = PawControlDogStatusSensor(
        cast(Any, coordinator), _DOG_ID, _DOG_NAME
    )
    health_select = PawControlHealthStatusSelect(
        cast(Any, coordinator), _DOG_ID, _DOG_NAME
    )
    visitor_switch = PawControlVisitorModeSwitch(
        cast(Any, coordinator), _DOG_ID, _DOG_NAME
    )
    tracker = PawControlGPSTracker(cast(Any, coordinator), _DOG_ID, _DOG_NAME)
    online_sensor = PawControlOnlineBinarySensor(
        cast(Any, coordinator), _DOG_ID, _DOG_NAME
    )

    assert status_entity.native_value == "resting"
    assert health_select.current_option == "good"
    assert visitor_switch.is_on is False
    assert tracker.state == STATE_HOME
    assert online_sensor.is_on is True

    coordinator.data[_DOG_ID].update(
        {
            "status_snapshot": {"state": "playing"},
            "health": {"health_status": "warning"},
            "visitor_mode_active": True,
            "gps": {"zone": "park"},
            "last_update": (dt_util.utcnow() - timedelta(hours=1)).isoformat(),
        },
    )

    assert status_entity.native_value == "playing"
    assert health_select.current_option == "warning"
    assert visitor_switch.is_on is True
    assert tracker.state == "park"
    assert online_sensor.is_on is False
