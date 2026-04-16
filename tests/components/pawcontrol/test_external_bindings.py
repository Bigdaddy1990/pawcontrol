import asyncio  # noqa: D100
from types import SimpleNamespace

import pytest

from custom_components.pawcontrol import external_bindings
from custom_components.pawcontrol.const import CONF_DOGS, CONF_GPS_SOURCE


class _FakeGPSManager:
    def __init__(self) -> None:
        self.current_location: SimpleNamespace | None = None
        self.points: list[dict[str, object]] = []

    async def async_get_current_location(self, dog_id: str) -> SimpleNamespace | None:
        return self.current_location

    async def async_add_gps_point(self, **kwargs: object) -> bool:
        self.points.append(kwargs)
        return True


class _FakeCoordinator:
    def __init__(self, gps_manager: _FakeGPSManager | None = None) -> None:
        self.gps_geofence_manager = gps_manager
        self.patched: list[str] = []

    async def async_patch_gps_update(self, dog_id: str) -> None:
        self.patched.append(dog_id)


class _PendingTask:
    def __init__(self) -> None:
        self.cancelled = False

    def done(self) -> bool:
        return False

    def cancel(self) -> None:
        self.cancelled = True


@pytest.mark.asyncio
async def test_async_setup_external_bindings_registers_and_unloads(  # noqa: D103
    hass, monkeypatch
) -> None:
    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_DOGS: [
                {
                    "dog_id": "dog-1",
                    "gps_config": {CONF_GPS_SOURCE: "device_tracker.fido"},
                }
            ]
        },
    )

    callbacks: list[object] = []
    unsub_calls: list[str] = []

    def _track_state_change_event(_hass, entity_ids, callback):
        assert entity_ids == ["device_tracker.fido"]
        callbacks.append(callback)

        def _unsubscribe() -> None:
            unsub_calls.append("called")

        return _unsubscribe

    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        _track_state_change_event,
    )
    monkeypatch.setattr(external_bindings, "_DEBOUNCE_SECONDS", 0)

    await external_bindings.async_setup_external_bindings(hass, entry)

    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 52.52, "longitude": 13.405, "gps_accuracy": 8}
            )
        }
    )
    callbacks[0](event)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(gps_manager.points) == 1
    assert gps_manager.points[0]["dog_id"] == "dog-1"
    assert coordinator.patched == ["dog-1"]

    await external_bindings.async_unload_external_bindings(hass, entry)
    assert unsub_calls == ["called"]


@pytest.mark.asyncio
async def test_async_setup_external_bindings_ignores_noise_and_invalid_sources(  # noqa: D103
    hass, monkeypatch
) -> None:
    gps_manager = _FakeGPSManager()
    gps_manager.current_location = SimpleNamespace(latitude=52.52, longitude=13.405)
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-2",
        data={
            CONF_DOGS: [
                {"dog_id": "dog-manual", "gps_config": {CONF_GPS_SOURCE: "manual"}},
                {"dog_id": "dog-bad", "gps_config": {CONF_GPS_SOURCE: "not_an_entity"}},
                {
                    "dog_id": "dog-live",
                    "gps_config": {CONF_GPS_SOURCE: "person.owner"},
                },
            ]
        },
    )

    callbacks: list[object] = []

    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _ids, callback: callbacks.append(callback) or (lambda: None),
    )
    monkeypatch.setattr(external_bindings, "_DEBOUNCE_SECONDS", 0)

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert len(callbacks) == 1

    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 52.52001, "longitude": 13.40501}
            )
        }
    )
    callbacks[0](event)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert gps_manager.points == []
    assert coordinator.patched == []


@pytest.mark.asyncio
async def test_async_setup_external_bindings_returns_when_no_gps_manager(  # noqa: D103
    hass, monkeypatch
) -> None:
    coordinator = _FakeCoordinator(gps_manager=None)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(entry_id="entry-3", data={CONF_DOGS: []})

    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert hass.data.get("pawcontrol") is None


def test_extract_coords_handles_non_mapping_attributes() -> None:  # noqa: D103
    assert external_bindings._extract_coords(SimpleNamespace(attributes=None)) == (
        None,
        None,
        None,
        None,
    )
    assert external_bindings._extract_coords(
        SimpleNamespace(attributes={"latitude": 1, "longitude": 2, "altitude": 9})
    ) == (1.0, 2.0, None, 9.0)


def test_haversine_distance_zero_for_same_point() -> None:  # noqa: D103
    assert external_bindings._haversine_m(10.0, 11.0, 10.0, 11.0) == 0.0


@pytest.mark.asyncio
async def test_external_bindings_handle_invalid_store_shapes(hass, monkeypatch) -> None:
    """Setup and unload should recover from malformed hass.data payloads."""
    entry = SimpleNamespace(entry_id="entry-store", data={CONF_DOGS: []})
    hass.data[external_bindings.DOMAIN] = "invalid"

    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager=gps_manager)
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        gps_geofence_manager=gps_manager,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert hass.data[external_bindings.DOMAIN] == {
        external_bindings._STORE_KEY: {entry.entry_id: {}}
    }

    hass.data[external_bindings.DOMAIN] = {external_bindings._STORE_KEY: "invalid"}
    await external_bindings.async_unload_external_bindings(hass, entry)

    hass.data[external_bindings.DOMAIN] = {
        external_bindings._STORE_KEY: {"entry-store": "invalid"}
    }
    await external_bindings.async_unload_external_bindings(hass, entry)


@pytest.mark.asyncio
async def test_external_binding_callback_handles_cancel_and_missing_binding(
    hass, monkeypatch
) -> None:
    """Callback should cancel pending work and ignore deleted bindings."""
    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-callback",
        data={
            CONF_DOGS: [
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: "person.owner"}}
            ]
        },
    )
    callbacks: list[object] = []
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _ids, callback: callbacks.append(callback) or (lambda: None),
    )
    monkeypatch.setattr(external_bindings, "_DEBOUNCE_SECONDS", 0)

    await external_bindings.async_setup_external_bindings(hass, entry)
    bindings = hass.data[external_bindings.DOMAIN][external_bindings._STORE_KEY][
        entry.entry_id
    ]
    pending = _PendingTask()
    bindings["dog-1"].task = pending

    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 52.53, "longitude": 13.41, "accuracy": 10}
            )
        }
    )
    callbacks[0](event)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert pending.cancelled is True
    assert len(gps_manager.points) == 1

    bindings.pop("dog-1")
    callbacks[0](event)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_external_bindings_skip_invalid_events_and_duplicate_dogs(
    hass, monkeypatch
) -> None:
    """Invalid payloads, duplicate dog ids and lookup errors should be ignored."""
    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-events",
        data={
            CONF_DOGS: [
                "invalid-dog",
                {"dog_id": "", "gps_config": {CONF_GPS_SOURCE: "person.owner"}},
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: ""}},
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: "person.owner"}},
            ]
        },
    )
    callbacks: list[object] = []
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _ids, callback: callbacks.append(callback) or (lambda: None),
    )
    monkeypatch.setattr(external_bindings, "_DEBOUNCE_SECONDS", 0)
    monkeypatch.setattr(
        gps_manager,
        "async_get_current_location",
        lambda _dog_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert len(callbacks) == 1

    callbacks[0](SimpleNamespace(data={"new_state": None}))
    callbacks[0](SimpleNamespace(data={"new_state": SimpleNamespace(attributes={})}))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert gps_manager.points == []

    callbacks[0](
        SimpleNamespace(
            data={
                "new_state": SimpleNamespace(
                    attributes={"latitude": 52.6, "longitude": 13.5}
                )
            }
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert len(gps_manager.points) == 1


@pytest.mark.asyncio
async def test_external_bindings_cover_store_and_unload_edge_paths(
    hass, monkeypatch
) -> None:
    """Cover malformed store entries, duplicate dog IDs and pending task unload."""
    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-edge",
        data={
            CONF_DOGS: [
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: "person.one"}},
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: "person.two"}},
            ]
        },
    )
    callbacks: list[object] = []
    unsub_calls: list[str] = []

    def _track_state_change_event(_hass, _ids, callback):
        callbacks.append(callback)

        def _unsubscribe() -> None:
            unsub_calls.append("called")

        return _unsubscribe

    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        _track_state_change_event,
    )

    hass.data[external_bindings.DOMAIN] = {
        external_bindings._STORE_KEY: {entry.entry_id: "not-a-dict"}
    }

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert len(callbacks) == 1

    bindings = hass.data[external_bindings.DOMAIN][external_bindings._STORE_KEY][
        entry.entry_id
    ]
    pending = _PendingTask()
    bindings["dog-1"].task = pending

    await external_bindings.async_unload_external_bindings(hass, entry)

    assert pending.cancelled is True
    assert unsub_calls == ["called"]

    invalid_dogs_entry = SimpleNamespace(
        entry_id="entry-invalid-dogs",
        data={CONF_DOGS: "not-a-list"},
    )
    await external_bindings.async_setup_external_bindings(hass, invalid_dogs_entry)


@pytest.mark.asyncio
async def test_external_bindings_ignores_event_without_new_state(
    hass, monkeypatch
) -> None:
    """Events without a new state should be ignored without GPS updates."""
    gps_manager = _FakeGPSManager()
    coordinator = _FakeCoordinator(gps_manager)
    runtime_data = SimpleNamespace(coordinator=coordinator, gps_geofence_manager=None)
    entry = SimpleNamespace(
        entry_id="entry-no-state",
        data={
            CONF_DOGS: [
                {"dog_id": "dog-1", "gps_config": {CONF_GPS_SOURCE: "person.owner"}}
            ]
        },
    )
    callbacks: list[object] = []
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _ids, callback: callbacks.append(callback) or (lambda: None),
    )
    monkeypatch.setattr(external_bindings, "_DEBOUNCE_SECONDS", 0)

    await external_bindings.async_setup_external_bindings(hass, entry)
    callbacks[0](SimpleNamespace(data={}))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert gps_manager.points == []
    assert coordinator.patched == []
