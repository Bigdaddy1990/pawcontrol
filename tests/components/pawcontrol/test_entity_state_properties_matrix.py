"""Entity state/property matrix tests for PawControl platforms."""

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


@dataclass(frozen=True)
class _EntityMatrixCase:
    """Input/output contract for per-entity property matrix checks."""

    label: str
    payload: Mapping[str, object] | None
    coordinator_available: bool
    expected_available: bool


@dataclass(frozen=True)
class _EntityMatrixSpec:
    """Parametric matrix definition for a single entity type."""

    name: str
    factory: Callable[[_CoordinatorDouble], Any]
    state_accessor: Callable[[Any], object]
    cases: tuple[_EntityMatrixCase, ...]


def _coordinator_from_payload(
    payload: Mapping[str, object] | None,
    *,
    available: bool = True,
) -> _CoordinatorDouble:
    data: dict[str, CoordinatorDogData] = {}
    if payload is not None:
        data[_DOG_ID] = cast(CoordinatorDogData, dict(payload))
    coordinator = _CoordinatorDouble(data=data)
    coordinator.available = available
    return coordinator


@pytest.mark.parametrize(
    "spec",
    [
        _EntityMatrixSpec(
            name="dog_status_sensor",
            factory=lambda coordinator: PawControlDogStatusSensor(
                cast(Any, coordinator), _DOG_ID, _DOG_NAME
            ),
            state_accessor=lambda entity: entity.native_value,
            cases=(
                _EntityMatrixCase(
                    label="normal",
                    payload={
                        "status_snapshot": {"state": "calm"},
                        "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
                    },
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="unknown_state",
                    payload={
                        "status_snapshot": {"state": ""},
                        "gps": {"zone": "unknown"},
                        "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
                    },
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="missing_keys",
                    payload={},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="no_payload",
                    payload=None,
                    coordinator_available=True,
                    expected_available=False,
                ),
            ),
        ),
        _EntityMatrixSpec(
            name="online_binary_sensor",
            factory=lambda coordinator: PawControlOnlineBinarySensor(
                cast(Any, coordinator), _DOG_ID, _DOG_NAME
            ),
            state_accessor=lambda entity: entity.is_on,
            cases=(
                _EntityMatrixCase(
                    label="normal",
                    payload={
                        "last_update": dt_util.utcnow().isoformat(),
                        "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
                    },
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="none_timestamp",
                    payload={"last_update": None},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="missing_keys",
                    payload={},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="coordinator_unavailable",
                    payload={"last_update": dt_util.utcnow().isoformat()},
                    coordinator_available=False,
                    expected_available=False,
                ),
            ),
        ),
        _EntityMatrixSpec(
            name="health_status_select",
            factory=lambda coordinator: PawControlHealthStatusSelect(
                cast(Any, coordinator), _DOG_ID, _DOG_NAME
            ),
            state_accessor=lambda entity: entity.current_option,
            cases=(
                _EntityMatrixCase(
                    label="normal",
                    payload={"health": {"health_status": "excellent"}},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="none_value",
                    payload={"health": {"health_status": None}},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="missing_keys",
                    payload={},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="no_payload",
                    payload=None,
                    coordinator_available=True,
                    expected_available=False,
                ),
            ),
        ),
        _EntityMatrixSpec(
            name="visitor_mode_switch",
            factory=lambda coordinator: PawControlVisitorModeSwitch(
                cast(Any, coordinator), _DOG_ID, _DOG_NAME
            ),
            state_accessor=lambda entity: entity.is_on,
            cases=(
                _EntityMatrixCase(
                    label="normal",
                    payload={"visitor_mode_active": True},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="unknown_value",
                    payload={"visitor_mode_active": "??"},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="missing_keys",
                    payload={},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="coordinator_unavailable",
                    payload={"visitor_mode_active": False},
                    coordinator_available=False,
                    expected_available=False,
                ),
            ),
        ),
        _EntityMatrixSpec(
            name="gps_tracker",
            factory=lambda coordinator: PawControlGPSTracker(
                cast(Any, coordinator), _DOG_ID, _DOG_NAME
            ),
            state_accessor=lambda entity: entity.state,
            cases=(
                _EntityMatrixCase(
                    label="normal",
                    payload={
                        "gps": {"zone": "park", "latitude": 48.1, "longitude": 11.5},
                    },
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="unknown_zone",
                    payload={"gps": {"zone": "unknown"}},
                    coordinator_available=True,
                    expected_available=True,
                ),
                _EntityMatrixCase(
                    label="none_gps",
                    payload={"gps": None},
                    coordinator_available=True,
                    expected_available=False,
                ),
                _EntityMatrixCase(
                    label="missing_keys",
                    payload={},
                    coordinator_available=True,
                    expected_available=False,
                ),
            ),
        ),
    ],
    ids=lambda spec: spec.name,
)
def test_entity_property_matrix_per_entity_type(
    spec: _EntityMatrixSpec,
) -> None:
    """Apply the same matrix on every entity type for core entity properties."""
    for case in spec.cases:
        coordinator = _coordinator_from_payload(
            case.payload,
            available=case.coordinator_available,
        )
        entity = spec.factory(coordinator)

        # state/native_value/is_on branch
        spec.state_accessor(entity)
        # available branch
        assert entity.available is case.expected_available, case.label
        # attributes/device_info/unique_id branches
        attrs = entity.extra_state_attributes
        assert isinstance(attrs, Mapping)
        assert attrs.get("dog_id") == _DOG_ID
        assert attrs.get("dog_name") == _DOG_NAME
        assert "last_updated" in attrs
        assert entity.device_info is not None
        assert isinstance(entity.unique_id, str) and entity.unique_id


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


@pytest.mark.parametrize(
    ("factory", "payload", "coordinator_available", "expected_available"),
    [
        (
            lambda coordinator: PawControlDogStatusSensor(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            {"dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME}},
            True,
            True,
        ),
        (
            lambda coordinator: PawControlDogStatusSensor(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            None,
            True,
            False,
        ),
        (
            lambda coordinator: PawControlOnlineBinarySensor(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            {"dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME}},
            True,
            True,
        ),
        (
            lambda coordinator: PawControlVisitorModeSwitch(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            {
                "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
            },
            False,
            False,
        ),
        (
            lambda coordinator: PawControlHealthStatusSelect(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            None,
            True,
            False,
        ),
        (
            lambda coordinator: PawControlGPSTracker(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            {"gps": {"zone": "home"}},
            True,
            True,
        ),
        (
            lambda coordinator: PawControlGPSTracker(
                cast(Any, coordinator),
                _DOG_ID,
                _DOG_NAME,
            ),
            {"dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME}},
            True,
            False,
        ),
    ],
)
def test_entity_available_matrix(
    factory: Callable[[_CoordinatorDouble], Any],
    payload: Mapping[str, object] | None,
    coordinator_available: bool,
    expected_available: bool,
) -> None:
    """Entities should expose availability from coordinator and required data."""
    coordinator = _coordinator_from_payload(payload, available=coordinator_available)
    entity = factory(coordinator)

    assert entity.available is expected_available


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"last_update": dt_util.utcnow().isoformat()}, True),
        (
            {"last_update": (dt_util.utcnow() - timedelta(minutes=11)).isoformat()},
            False,
        ),
        ({"last_update": None}, False),
        ({}, False),
    ],
)
def test_online_sensor_api_to_is_on_mapping(
    payload: Mapping[str, object],
    expected: bool,
) -> None:
    """Online binary sensor should map API timestamp payloads to is_on state."""
    coordinator = _coordinator_from_payload(payload)
    entity = PawControlOnlineBinarySensor(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.is_on is expected


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (False, False),
        ("yes", True),
        ("", False),
        (None, False),
    ],
)
def test_visitor_mode_switch_api_to_is_on_mapping(
    raw_value: object,
    expected: bool,
) -> None:
    """Visitor switch should coerce API values to deterministic bool states."""
    coordinator = _coordinator_from_payload({"visitor_mode_active": raw_value})
    entity = PawControlVisitorModeSwitch(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.is_on is expected


@pytest.mark.parametrize(
    ("health_status", "expected"),
    [
        ("excellent", "excellent"),
        ("", ""),
        (None, "good"),
        (123, "good"),
    ],
)
def test_health_select_api_to_state_mapping(
    health_status: object,
    expected: str,
) -> None:
    """Health select should accept strings and fallback for invalid API values."""
    coordinator = _coordinator_from_payload(
        {"health": {"health_status": health_status}},
    )
    entity = PawControlHealthStatusSelect(cast(Any, coordinator), _DOG_ID, _DOG_NAME)

    assert entity.current_option == expected


def test_entity_metadata_and_attributes_include_core_identity_fields() -> None:
    """Entities should expose stable identity and attribute metadata."""
    coordinator = _coordinator_from_payload(
        {
            "status_snapshot": {"state": "resting"},
            "last_update": dt_util.utcnow().isoformat(),
            "dog_info": {"dog_id": _DOG_ID, "dog_name": _DOG_NAME},
        },
    )

    entities = [
        PawControlDogStatusSensor(cast(Any, coordinator), _DOG_ID, _DOG_NAME),
        PawControlOnlineBinarySensor(cast(Any, coordinator), _DOG_ID, _DOG_NAME),
        PawControlVisitorModeSwitch(cast(Any, coordinator), _DOG_ID, _DOG_NAME),
        PawControlHealthStatusSelect(cast(Any, coordinator), _DOG_ID, _DOG_NAME),
        PawControlGPSTracker(cast(Any, coordinator), _DOG_ID, _DOG_NAME),
    ]

    for entity in entities:
        assert isinstance(entity.unique_id, str)
        assert entity.unique_id
        assert isinstance(entity.name, str | None)
        assert entity.device_info is not None
        assert entity.extra_state_attributes.get("dog_id") == _DOG_ID
        assert entity.extra_state_attributes.get("dog_name") == _DOG_NAME
        assert "last_updated" in entity.extra_state_attributes
