"""Additional runtime coverage for ``device_tracker.py``."""

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.const import Platform
from homeassistant.util import dt as dt_util
import pytest

from custom_components.pawcontrol import device_tracker
from custom_components.pawcontrol.device_tracker import PawControlGPSTracker


class _Coordinator:
    """Coordinator stub exposing only what tracker tests need."""

    def __init__(
        self,
        payload: Mapping[str, object] | None = None,
        *,
        available: bool = True,
    ) -> None:
        self.available = available
        self._payload = dict(payload) if payload is not None else None
        self.config_entry = None
        self.async_apply_module_updates = AsyncMock()

    def get_module_data(self, _dog_id: str, module: str) -> Mapping[str, object]:
        if module != device_tracker.MODULE_GPS or self._payload is None:
            return {}
        return self._payload

    def get_dog_data(self, dog_id: str) -> Mapping[str, object]:
        return {
            device_tracker.MODULE_GPS: self.get_module_data(
                dog_id,
                device_tracker.MODULE_GPS,
            )
        }


def _build_tracker(
    payload: Mapping[str, object] | None = None,
    *,
    available: bool = True,
) -> tuple[PawControlGPSTracker, _Coordinator]:
    coordinator = _Coordinator(payload, available=available)
    tracker = PawControlGPSTracker(coordinator, "dog-1", "Maple")
    tracker.async_write_ha_state = MagicMock()
    return tracker, coordinator


def _patched_dog_normaliser(
    payload: Mapping[str, object] | object,
) -> Mapping[str, object] | None:
    """Normalize synthetic dog payloads for async setup tests."""
    if not isinstance(payload, Mapping):
        return None
    if payload.get("invalid"):
        return None
    dog_id = str(payload.get("dog_id", "dog-1"))
    dog_name = str(payload.get("dog_name", dog_id))
    return {
        device_tracker.DOG_ID_FIELD: dog_id,
        device_tracker.DOG_NAME_FIELD: dog_name,
        "gps_enabled": bool(payload.get("gps_enabled", False)),
    }


def _patched_module_projection(dog: Mapping[str, object]) -> SimpleNamespace:
    """Return a minimal modules projection object for setup-entry tests."""
    enabled = bool(dog.get("gps_enabled", False))
    return SimpleNamespace(
        mapping={device_tracker.MODULE_GPS: enabled},
        config={device_tracker.MODULE_GPS: enabled},
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_entry_handles_runtime_and_gps_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should short-circuit when runtime or GPS-enabled dogs are missing."""
    hass = object()
    entry = SimpleNamespace(entry_id="entry-1")
    async_add_entities = AsyncMock()

    monkeypatch.setattr(device_tracker, "get_runtime_data", lambda *_args: None)
    await device_tracker.async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_not_awaited()

    entity_factory = MagicMock()
    entity_factory.get_profile_info.return_value = SimpleNamespace(platforms=set())
    runtime_data_empty = SimpleNamespace(
        coordinator=MagicMock(),
        dogs=[],
        entity_factory=entity_factory,
        entity_profile="default",
    )
    monkeypatch.setattr(
        device_tracker, "get_runtime_data", lambda *_args: runtime_data_empty
    )
    await device_tracker.async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_not_awaited()

    runtime_data_non_gps = SimpleNamespace(
        coordinator=MagicMock(),
        dogs=[
            {"dog_id": "dog-a", "dog_name": "A", "gps_enabled": False},
            {"dog_id": "dog-b", "dog_name": "B", "gps_enabled": False},
            "invalid-dog",
            {"invalid": True},
        ],
        entity_factory=entity_factory,
        entity_profile="default",
    )
    monkeypatch.setattr(
        device_tracker, "get_runtime_data", lambda *_args: runtime_data_non_gps
    )
    monkeypatch.setattr(
        device_tracker, "ensure_dog_config_data", _patched_dog_normaliser
    )
    monkeypatch.setattr(
        device_tracker, "ensure_dog_modules_projection", _patched_module_projection
    )
    await device_tracker.async_setup_entry(hass, entry, async_add_entities)
    async_add_entities.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_entry_entity_creation_and_baseline_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should create trackers via config and fallback baseline when needed."""
    hass = object()
    entry = SimpleNamespace(entry_id="entry-1")
    add_entities = AsyncMock()
    created_trackers: list[tuple[str, str]] = []

    def _fake_tracker(
        _coordinator: object, dog_id: str, dog_name: str
    ) -> dict[str, str]:
        created_trackers.append((dog_id, dog_name))
        return {"dog_id": dog_id, "dog_name": dog_name}

    monkeypatch.setattr(device_tracker, "PawControlGPSTracker", _fake_tracker)
    monkeypatch.setattr(
        device_tracker, "ensure_dog_config_data", _patched_dog_normaliser
    )
    monkeypatch.setattr(
        device_tracker, "ensure_dog_modules_projection", _patched_module_projection
    )
    monkeypatch.setattr(device_tracker, "async_call_add_entities", AsyncMock())

    snapshot = SimpleNamespace(total_allocated=5)
    entity_factory = MagicMock()
    entity_factory.get_budget_snapshot.return_value = snapshot
    entity_factory.create_entity_config.side_effect = [object(), None]
    entity_factory.get_profile_info.return_value = SimpleNamespace(platforms=set())
    runtime_data = SimpleNamespace(
        coordinator=MagicMock(),
        dogs=[
            {"dog_id": "dog-a", "dog_name": "A", "gps_enabled": True},
            {"dog_id": "dog-b", "dog_name": "B", "gps_enabled": True},
        ],
        entity_factory=entity_factory,
        entity_profile="profile-a",
    )
    monkeypatch.setattr(device_tracker, "get_runtime_data", lambda *_args: runtime_data)

    await device_tracker.async_setup_entry(hass, entry, add_entities)
    device_tracker.async_call_add_entities.assert_awaited_once()
    assert created_trackers == [("dog-a", "A")]
    assert entity_factory.begin_budget.call_count == 2
    assert entity_factory.finalize_budget.call_count == 2

    created_trackers.clear()
    device_tracker.async_call_add_entities.reset_mock()
    entity_factory.create_entity_config.side_effect = [None, None]
    entity_factory.get_profile_info.return_value = SimpleNamespace(
        platforms={Platform.DEVICE_TRACKER},
    )
    await device_tracker.async_setup_entry(hass, entry, add_entities)
    assert created_trackers == [("dog-a", "A"), ("dog-b", "B")]
    device_tracker.async_call_add_entities.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_setup_entry_no_entities_when_profile_blocks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should skip add_entities when profile disallows baseline trackers."""
    hass = object()
    entry = SimpleNamespace(entry_id="entry-1")
    add_entities = AsyncMock()

    entity_factory = MagicMock()
    entity_factory.get_budget_snapshot.return_value = None
    entity_factory.create_entity_config.return_value = None
    entity_factory.get_profile_info.return_value = SimpleNamespace(platforms=set())
    runtime_data = SimpleNamespace(
        coordinator=MagicMock(),
        dogs=[{"dog_id": "dog-a", "dog_name": "A", "gps_enabled": True}],
        entity_factory=entity_factory,
        entity_profile="profile-a",
    )

    monkeypatch.setattr(device_tracker, "get_runtime_data", lambda *_args: runtime_data)
    monkeypatch.setattr(
        device_tracker, "ensure_dog_config_data", _patched_dog_normaliser
    )
    monkeypatch.setattr(
        device_tracker, "ensure_dog_modules_projection", _patched_module_projection
    )
    monkeypatch.setattr(device_tracker, "async_call_add_entities", AsyncMock())
    monkeypatch.setattr(device_tracker, "PawControlGPSTracker", lambda *_args: object())

    await device_tracker.async_setup_entry(hass, entry, add_entities)
    device_tracker.async_call_add_entities.assert_not_awaited()


@pytest.mark.unit
def test_serialize_helpers_and_state_property_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timestamp/route serialization and state transitions should be stable."""
    tracker, _coordinator = _build_tracker({"zone": "home"})
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)

    assert tracker._serialize_timestamp(now) == dt_util.as_utc(now).isoformat()
    assert (
        tracker._serialize_timestamp("2026-04-07T12:00:00+00:00")
        == "2026-04-07T12:00:00+00:00"
    )
    assert tracker._serialize_timestamp(None) is None

    monkeypatch.setattr(device_tracker.dt_util, "utcnow", lambda: now)
    serialized = tracker._serialize_route_point({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": None,
        "accuracy": 5,
        "altitude": 42.0,
        "speed": 3.5,
        "heading": 180.0,
    })
    assert serialized["timestamp"] == now.isoformat()
    assert serialized["accuracy"] == 5.0
    assert serialized["altitude"] == 42.0
    assert serialized["speed"] == 3.5
    assert serialized["heading"] == 180.0

    tracker_home, _ = _build_tracker({"zone": "home"})
    tracker_zone, _ = _build_tracker({"zone": "park"})
    tracker_unknown_zone, _ = _build_tracker({"zone": "unknown"})
    tracker_empty, _ = _build_tracker(None)

    assert tracker_home.state == device_tracker.STATE_HOME
    assert tracker_zone.state == "park"
    assert tracker_unknown_zone.state == device_tracker.STATE_NOT_HOME
    assert tracker_empty.state == device_tracker.STATE_UNKNOWN


@pytest.mark.unit
def test_serialize_route_point_skips_non_numeric_optional_fields() -> None:
    """Route-point serialization should omit optional fields with invalid types."""
    tracker, _ = _build_tracker({})
    serialized = tracker._serialize_route_point({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": "2026-04-07T12:00:00+00:00",
        "accuracy": "bad",
        "altitude": "bad",
        "speed": "bad",
        "heading": "bad",
    })
    assert "accuracy" not in serialized
    assert "altitude" not in serialized
    assert "speed" not in serialized
    assert "heading" not in serialized


@pytest.mark.unit
def test_coordinate_accuracy_battery_and_location_name_branches() -> None:
    """Numeric parsing properties should handle valid and invalid values."""
    tracker_ok, _ = _build_tracker({
        "latitude": "52.5",
        "longitude": "13.4",
        "accuracy": "9",
        "battery": "82",
        "zone": "yard",
    })
    assert tracker_ok.latitude == 52.5
    assert tracker_ok.longitude == 13.4
    assert tracker_ok.location_accuracy == 9
    assert tracker_ok.battery_level == 82
    assert tracker_ok.location_name == "yard"

    tracker_bad, _ = _build_tracker({
        "latitude": "bad",
        "longitude": [],
        "accuracy": "bad",
        "battery": "bad",
        "zone": "unknown",
    })
    assert tracker_bad.latitude is None
    assert tracker_bad.longitude is None
    assert tracker_bad.location_accuracy == device_tracker.DEFAULT_GPS_ACCURACY
    assert tracker_bad.battery_level is None
    assert tracker_bad.location_name is None

    tracker_unavailable, _ = _build_tracker({"latitude": 1.0}, available=False)
    assert tracker_unavailable.available is False
    assert tracker_unavailable._get_gps_data() is None


@pytest.mark.unit
def test_coordinate_and_numeric_properties_cover_value_and_type_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Parsing properties should handle both ValueError and TypeError paths."""
    tracker, _ = _build_tracker({})

    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"latitude": "bad"})
    assert tracker.latitude is None
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"latitude": []})
    assert tracker.latitude is None

    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"longitude": "bad"})
    assert tracker.longitude is None
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"longitude": []})
    assert tracker.longitude is None

    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"accuracy": "bad"})
    assert tracker.location_accuracy == device_tracker.DEFAULT_GPS_ACCURACY
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"accuracy": []})
    assert tracker.location_accuracy == device_tracker.DEFAULT_GPS_ACCURACY

    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"battery": "bad"})
    assert tracker.battery_level is None
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: {"battery": []})
    assert tracker.battery_level is None

    monkeypatch.setattr(tracker, "_get_gps_data", lambda: None)
    assert tracker.location_name is None


@pytest.mark.unit
def test_extra_state_attributes_with_string_and_snapshot_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Attribute export should include geofence and status snapshot fallback handling."""
    tracker, _ = _build_tracker({
        "source": 123,
        "last_seen": "2026-04-07T10:00:00+00:00",
        "distance_from_home": 12,
        "current_route": {
            "active": False,
            "points": [],
            "start_time": "2026-04-07T09:00:00+00:00",
        },
        "geofence_status": {
            "in_safe_zone": False,
            "zone_name": "Fence",
            "distance_to_boundary": 3.2,
        },
        "walk_info": {
            "active": False,
            "walk_id": "walk-2",
            "start_time": "2026-04-07T08:00:00+00:00",
        },
    })
    monkeypatch.setattr(tracker, "_get_status_snapshot", lambda: {"in_safe_zone": True})
    attrs = tracker.extra_state_attributes
    assert attrs["location_source"] == "unknown"
    assert attrs["last_seen"] == "2026-04-07T10:00:00+00:00"
    assert attrs["route_start_time"] == "2026-04-07T09:00:00+00:00"
    assert attrs["zone_name"] == "Fence"
    assert attrs["zone_distance"] == 3.2
    assert attrs["in_safe_zone"] is True
    assert attrs["walk_id"] == "walk-2"
    assert attrs["walk_start_time"] == "2026-04-07T08:00:00+00:00"


@pytest.mark.unit
def test_extra_state_attributes_datetime_branches_with_status_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Datetime-based route/walk fields should serialize to ISO strings."""
    tracker, _ = _build_tracker({})
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    gps_payload = {
        "altitude": 20.0,
        "speed": 1.2,
        "heading": 45.0,
        "satellites": 7,
        "source": "gps",
        "last_seen": now,
        "distance_from_home": 5.5,
        "current_route": {
            "active": True,
            "points": [{"latitude": 1.0, "longitude": 2.0}],
            "distance": 100.0,
            "duration": 60.0,
            "start_time": now,
        },
        "geofence_status": {
            "in_safe_zone": False,
            "zone_name": "Home",
            "distance_to_boundary": 1.0,
        },
        "walk_info": {
            "active": True,
            "walk_id": "walk-a",
            "start_time": now,
        },
    }
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: gps_payload)
    monkeypatch.setattr(tracker, "_get_status_snapshot", lambda: {"in_safe_zone": True})
    attrs = tracker.extra_state_attributes
    assert attrs["last_seen"] == dt_util.as_utc(now).isoformat()
    assert attrs["route_start_time"] == dt_util.as_utc(now).isoformat()
    assert attrs["walk_start_time"] == dt_util.as_utc(now).isoformat()
    assert attrs["in_safe_zone"] is True


@pytest.mark.unit
def test_extra_state_attributes_false_branch_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extra attributes should cover false branches for optional payload sections."""
    tracker, _ = _build_tracker({})
    payload = {
        "source": "gps",
        "last_seen": "2026-04-07T12:00:00+00:00",
        "distance_from_home": "unknown",
        "current_route": None,
        "geofence_status": None,
        "walk_info": None,
    }
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: payload)
    monkeypatch.setattr(tracker, "_get_status_snapshot", lambda: None)
    attrs = tracker.extra_state_attributes
    assert attrs["last_seen"] == "2026-04-07T12:00:00+00:00"
    assert "distance_from_home" not in attrs
    assert attrs["route_active"] is False
    assert "zone_name" not in attrs
    assert "walk_id" not in attrs


@pytest.mark.unit
def test_extra_state_attributes_optional_type_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional type guards should skip non-string/non-numeric sub-fields."""
    tracker, _ = _build_tracker({})
    payload = {
        "source": "gps",
        "current_route": {
            "active": True,
            "points": [],
            "start_time": 123,
        },
        "geofence_status": {
            "in_safe_zone": True,
            "zone_name": 123,
            "distance_to_boundary": "far",
        },
        "walk_info": {
            "active": True,
            "walk_id": 123,
            "start_time": 456,
        },
    }
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: payload)
    monkeypatch.setattr(tracker, "_get_status_snapshot", lambda: {"in_safe_zone": True})
    attrs = tracker.extra_state_attributes
    assert "route_start_time" not in attrs
    assert "zone_name" not in attrs
    assert "zone_distance" not in attrs
    assert "walk_id" not in attrs
    assert "walk_start_time" not in attrs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_location_validation_throttle_priority_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Location updates should validate, throttle, prioritize and handle exceptions."""
    tracker, _ = _build_tracker({"current_route": {"active": True}})
    route_mock = AsyncMock()
    coord_mock = AsyncMock()
    monkeypatch.setattr(tracker, "_update_route_tracking", route_mock)
    monkeypatch.setattr(tracker, "_update_coordinator_gps_data", coord_mock)

    await tracker.async_update_location(200.0, 13.0)
    route_mock.assert_not_awaited()
    coord_mock.assert_not_awaited()

    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    tracker._last_update = now
    await tracker.async_update_location(
        52.5,
        13.4,
        source="gps",
        timestamp=now + timedelta(seconds=5),
    )
    route_mock.assert_not_awaited()

    tracker._last_update = None
    tracker._last_location = {
        "latitude": 0.0,
        "longitude": 0.0,
        "accuracy": 1,
        "altitude": None,
        "speed": None,
        "heading": None,
        "source": "gps",
        "timestamp": now,
        "priority": 10,
    }
    await tracker.async_update_location(
        52.5,
        13.4,
        source="manual",
        timestamp=now + timedelta(minutes=5),
    )
    route_mock.assert_not_awaited()

    tracker._last_location = None
    await tracker.async_update_location(
        52.5,
        13.4,
        accuracy=7,
        altitude=10.0,
        speed=2.0,
        heading=90.0,
        source="network",
        timestamp=now + timedelta(minutes=10),
    )
    route_mock.assert_awaited_once()
    coord_mock.assert_awaited_once()
    tracker.async_write_ha_state.assert_called_once()

    monkeypatch.setattr(
        tracker,
        "_update_route_tracking",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    await tracker.async_update_location(
        52.5,
        13.4,
        timestamp=now + timedelta(minutes=20),
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_route_tracking_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route tracking should support inactive, active and exception flows."""
    now = dt_util.utcnow()
    location_data = {
        "latitude": 52.5,
        "longitude": 13.4,
        "accuracy": 5,
        "altitude": 50.0,
        "speed": 2.0,
        "heading": 180.0,
        "timestamp": now,
        "source": "gps",
        "priority": 10,
    }

    tracker_none, _ = _build_tracker(None)
    await tracker_none._update_route_tracking(location_data)
    assert len(tracker_none._route_points) == 0

    tracker_inactive, _ = _build_tracker({"current_route": {"active": False}})
    monkeypatch.setattr(
        tracker_inactive, "_get_gps_data", lambda: {"current_route": {"active": False}}
    )
    await tracker_inactive._update_route_tracking(location_data)
    assert len(tracker_inactive._route_points) == 0

    tracker_active, _ = _build_tracker({"current_route": {"active": True}})
    monkeypatch.setattr(
        tracker_active, "_get_gps_data", lambda: {"current_route": {"active": True}}
    )
    await tracker_active._update_route_tracking(location_data)
    assert len(tracker_active._route_points) == 1

    class _BrokenBuffer:
        def append(self, _point: object) -> None:
            raise RuntimeError("append failure")

    tracker_error, _ = _build_tracker({"current_route": {"active": True}})
    monkeypatch.setattr(
        tracker_error, "_get_gps_data", lambda: {"current_route": {"active": True}}
    )
    monkeypatch.setattr(tracker_error, "_route_points", _BrokenBuffer())
    await tracker_error._update_route_tracking(location_data)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_update_coordinator_gps_data_base_route_and_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordinator updates should include optional route snapshots when active."""
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    location_data = {
        "latitude": 52.5,
        "longitude": 13.4,
        "accuracy": 5,
        "altitude": 50.0,
        "speed": 2.0,
        "heading": 180.0,
        "timestamp": now,
        "source": "gps",
        "priority": 10,
    }

    tracker_basic, coordinator_basic = _build_tracker({})
    await tracker_basic._update_coordinator_gps_data(location_data)
    coordinator_basic.async_apply_module_updates.assert_awaited_once()
    args = coordinator_basic.async_apply_module_updates.await_args.args
    assert args[0] == "dog-1"
    assert args[1] == device_tracker.MODULE_GPS
    assert "current_route" not in args[2]

    tracker_route, coordinator_route = _build_tracker({
        "current_route": {
            "id": "route-1",
            "name": "Route",
            "active": True,
            "start_time": now - timedelta(minutes=5),
            "end_time": now,
            "distance": 123.4,
            "duration": 300.0,
        }
    })
    tracker_route._route_points.append({
        "latitude": 52.4,
        "longitude": 13.3,
        "timestamp": now - timedelta(minutes=1),
        "accuracy": 3,
    })
    await tracker_route._update_coordinator_gps_data(location_data)
    route_payload = coordinator_route.async_apply_module_updates.await_args.args[2]
    assert route_payload["current_route"]["id"] == "route-1"
    assert route_payload["current_route"]["distance"] == 123.4
    assert route_payload["current_route"]["duration"] == 300.0
    assert route_payload["current_route"]["end_time"] is not None

    tracker_error, coordinator_error = _build_tracker({})
    coordinator_error.async_apply_module_updates = AsyncMock(
        side_effect=RuntimeError("apply failed")
    )
    await tracker_error._update_coordinator_gps_data(location_data)

    tracker_fallback, coordinator_fallback = _build_tracker({})
    location_without_ts = dict(location_data)
    location_without_ts["timestamp"] = None
    monkeypatch.setattr(
        device_tracker.dt_util, "utcnow", lambda: now + timedelta(minutes=1)
    )
    await tracker_fallback._update_coordinator_gps_data(location_without_ts)
    fallback_payload = coordinator_fallback.async_apply_module_updates.await_args.args[
        2
    ]
    assert fallback_payload["last_seen"] == (now + timedelta(minutes=1)).isoformat()

    tracker_optional, coordinator_optional = _build_tracker({})
    tracker_optional._route_points.append({
        "latitude": 1.0,
        "longitude": 2.0,
        "timestamp": now,
        "accuracy": 1,
    })
    monkeypatch.setattr(
        tracker_optional,
        "_get_gps_data",
        lambda: {
            "current_route": {
                "id": "route-2",
                "name": "Route 2",
                "active": True,
                "start_time": now.isoformat(),
                "end_time": None,
                "distance": "bad",
                "duration": "bad",
            }
        },
    )
    await tracker_optional._update_coordinator_gps_data(location_data)
    optional_payload = coordinator_optional.async_apply_module_updates.await_args.args[
        2
    ]
    current_route = optional_payload["current_route"]
    assert "end_time" not in current_route
    assert "distance" not in current_route
    assert "duration" not in current_route


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_and_stop_route_recording_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route lifecycle should cover start, stop, discard and exception branches."""
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    tracker, _ = _build_tracker({})
    gps_store: dict[str, object] = {"status": "tracking"}
    monkeypatch.setattr(tracker, "_get_gps_data", lambda: gps_store)
    monkeypatch.setattr(device_tracker.dt_util, "utcnow", lambda: now)

    route_id = await tracker.async_start_route_recording("Lunch Walk")
    assert route_id == f"route_dog-1_{int(now.timestamp())}"
    assert gps_store["current_route"]["active"] is True  # type: ignore[index]

    tracker._route_points.append({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": now - timedelta(minutes=2),
        "accuracy": 5,
        "altitude": 30.0,
        "speed": 2.0,
        "heading": 90.0,
    })
    tracker._route_points.append({
        "latitude": 52.6,
        "longitude": 13.5,
        "timestamp": now,
        "accuracy": 4,
    })
    route_data = await tracker.async_stop_route_recording(save_route=True)
    assert route_data is not None
    assert route_data["active"] is False
    assert route_data["point_count"] == 2
    assert gps_store["current_route"]["active"] is False  # type: ignore[index]

    tracker_discard, _ = _build_tracker({
        "current_route": {"id": "x", "active": True, "start_time": now.isoformat()}
    })
    gps_discard = {
        "current_route": {"id": "x", "active": True, "start_time": now.isoformat()}
    }
    monkeypatch.setattr(tracker_discard, "_get_gps_data", lambda: gps_discard)
    tracker_discard._route_points.append({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": now,
        "accuracy": 1,
    })
    assert await tracker_discard.async_stop_route_recording(save_route=False) is None

    tracker_none, _ = _build_tracker(None)
    monkeypatch.setattr(tracker_none, "_get_gps_data", lambda: None)
    assert await tracker_none.async_stop_route_recording() is None

    tracker_inactive, _ = _build_tracker({"current_route": {"active": False}})
    monkeypatch.setattr(
        tracker_inactive, "_get_gps_data", lambda: {"current_route": {"active": False}}
    )
    assert await tracker_inactive.async_stop_route_recording() is None

    tracker_error, _ = _build_tracker({
        "current_route": {"active": True, "start_time": now}
    })
    monkeypatch.setattr(
        tracker_error,
        "_get_gps_data",
        lambda: {"current_route": {"active": True, "start_time": now}},
    )
    tracker_error._route_points.append({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": now,
        "accuracy": 1,
    })
    monkeypatch.setattr(
        tracker_error,
        "_calculate_route_distance",
        lambda _points: (_ for _ in ()).throw(RuntimeError("distance failure")),
    )
    assert await tracker_error.async_stop_route_recording() is None

    tracker_start_error, _ = _build_tracker({})
    monkeypatch.setattr(
        tracker_start_error,
        "_get_gps_data",
        lambda: (_ for _ in ()).throw(RuntimeError("gps unavailable")),
    )
    with pytest.raises(RuntimeError, match="gps unavailable"):
        await tracker_start_error.async_start_route_recording()


@pytest.mark.unit
def test_calculate_route_distance_paths() -> None:
    """Distance helper should handle short, valid and invalid routes."""
    tracker, _ = _build_tracker({})
    assert tracker._calculate_route_distance([]) == 0.0
    assert (
        tracker._calculate_route_distance([{"latitude": 1.0, "longitude": 2.0}]) == 0.0
    )

    valid_distance = tracker._calculate_route_distance([
        {"latitude": 52.5, "longitude": 13.4},
        {"latitude": 52.6, "longitude": 13.5},
    ])
    assert valid_distance > 0.0

    invalid_distance = tracker._calculate_route_distance([
        {"latitude": "bad", "longitude": 13.4},
        {"latitude": 52.6, "longitude": 13.5},
    ])
    assert invalid_distance == 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_export_route_dispatch_and_payload_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Export dispatch should cover empty, gpx/json/csv, invalid format and exceptions."""
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    tracker_empty, _ = _build_tracker({})
    assert await tracker_empty.async_export_route("gpx") is None

    tracker, _ = _build_tracker({})
    tracker._route_points.append({
        "latitude": 52.5,
        "longitude": 13.4,
        "timestamp": now - timedelta(minutes=2),
        "altitude": 30.0,
        "accuracy": 5,
        "speed": 2.0,
        "heading": 90.0,
    })
    tracker._route_points.append({
        "latitude": 52.6,
        "longitude": 13.5,
        "timestamp": "2026-04-07T12:01:00+00:00",
        "accuracy": "n/a",
    })

    gpx_payload = await tracker.async_export_route("gpx")
    json_payload = await tracker.async_export_route("json")
    csv_payload = await tracker.async_export_route("csv")
    assert gpx_payload is not None and gpx_payload["format"] == "gpx"
    assert "<ele>30.0</ele>" in gpx_payload["content"]
    assert json_payload is not None and json_payload["format"] == "json"
    assert json_payload["content"]["routes"][0]["duration_minutes"] is None
    assert csv_payload is not None and csv_payload["format"] == "csv"
    assert (
        "timestamp,latitude,longitude,altitude,accuracy,speed,heading"
        in csv_payload["content"]
    )

    assert await tracker.async_export_route("unsupported") is None

    monkeypatch.setattr(
        tracker, "_export_route_gpx", AsyncMock(side_effect=RuntimeError("export boom"))
    )
    assert await tracker.async_export_route("gpx") is None


@pytest.mark.unit
def test_source_type_and_empty_gps_property_branches() -> None:
    """Properties should return defaults when GPS payload is unavailable."""
    tracker, _ = _build_tracker(None)

    assert tracker.source_type == device_tracker.SourceType.GPS
    assert tracker.latitude is None
    assert tracker.longitude is None
    assert tracker.location_accuracy is None
    assert tracker.battery_level is None

    attrs = tracker.extra_state_attributes
    assert attrs["tracker_type"] == device_tracker.MODULE_GPS
    assert attrs["route_active"] is False
    assert attrs["route_points"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_update_location_uses_default_timestamp_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Location updates should default to ``dt_util.utcnow`` when timestamp is omitted."""
    tracker, _ = _build_tracker({})
    route_mock = AsyncMock()
    coord_mock = AsyncMock()
    monkeypatch.setattr(tracker, "_update_route_tracking", route_mock)
    monkeypatch.setattr(tracker, "_update_coordinator_gps_data", coord_mock)

    now = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(device_tracker.dt_util, "utcnow", lambda: now)

    await tracker.async_update_location(
        52.5,
        13.4,
        accuracy=5,
        source="gps",
        timestamp=None,
    )

    assert tracker._last_update == now
    assert tracker._last_location is not None
    assert tracker._last_location["timestamp"] == now
    route_mock.assert_awaited_once()
    coord_mock.assert_awaited_once()
