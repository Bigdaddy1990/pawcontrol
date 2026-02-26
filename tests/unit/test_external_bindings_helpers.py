"""Tests for lightweight helpers in ``external_bindings``."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.pawcontrol import external_bindings
from custom_components.pawcontrol.const import DOMAIN


def test_domain_store_initializes_and_repairs_domain_bucket() -> None:
    """The domain bucket should always be a mutable mapping."""
    hass = SimpleNamespace(data={})

    store = external_bindings._domain_store(hass)

    assert store == {}
    assert hass.data[DOMAIN] is store

    hass.data[DOMAIN] = "broken"
    repaired = external_bindings._domain_store(hass)
    assert repaired == {}
    assert isinstance(hass.data[DOMAIN], dict)


def test_extract_coords_handles_valid_and_invalid_payloads() -> None:
    """Coordinate extraction should coerce numeric values and reject invalid data."""

    def _state(attributes: Any) -> SimpleNamespace:
        return SimpleNamespace(attributes=attributes)

    state = _state({
        "latitude": 50,
        "longitude": 8.5,
        "gps_accuracy": 12,
        "altitude": 99,
    })

    assert external_bindings._extract_coords(state) == (50.0, 8.5, 12.0, 99.0)
    invalid = _state({"latitude": "x", "longitude": 1})
    assert external_bindings._extract_coords(invalid) == (None, None, None, None)
    assert external_bindings._extract_coords(_state(None)) == (None, None, None, None)


def test_haversine_returns_zero_for_identical_points() -> None:
    """Distance helper should be deterministic for equal coordinates."""
    assert external_bindings._haversine_m(10.0, 20.0, 10.0, 20.0) == 0.0


@pytest.mark.asyncio
async def test_async_unload_external_bindings_cleans_up_registered_bindings() -> None:
    """Unload should unsubscribe and cancel pending tasks."""
    unsub_called = False

    def _unsub() -> None:
        nonlocal unsub_called
        unsub_called = True

    task = asyncio.create_task(asyncio.sleep(5))
    binding = external_bindings._Binding(unsub=_unsub, task=task)

    hass = SimpleNamespace(
        data={DOMAIN: {external_bindings._STORE_KEY: {"entry-id": {"dog": binding}}}}
    )
    entry = SimpleNamespace(entry_id="entry-id")

    await external_bindings.async_unload_external_bindings(hass, entry)

    assert unsub_called is True
    assert task.cancelling() > 0
    assert "entry-id" not in hass.data[DOMAIN][external_bindings._STORE_KEY]


@pytest.mark.asyncio
async def test_async_setup_external_bindings_registers_listener_and_forwards_gps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should subscribe to entity updates and forward valid location data."""

    class _GPSManager:
        def __init__(self) -> None:
            self.add_calls: list[dict[str, Any]] = []

        async def async_get_current_location(self, dog_id: str) -> None:
            return None

        async def async_add_gps_point(self, **kwargs: Any) -> bool:
            self.add_calls.append(kwargs)
            return True

    class _Coordinator:
        def __init__(self, manager: _GPSManager) -> None:
            self.gps_geofence_manager = manager
            self.patch_calls: list[str] = []

        async def async_patch_gps_update(self, dog_id: str) -> None:
            self.patch_calls.append(dog_id)

    gps_manager = _GPSManager()
    coordinator = _Coordinator(gps_manager)
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        gps_geofence_manager=None,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(external_bindings.asyncio, "sleep", _no_sleep)

    callback_box: dict[str, Any] = {}
    unsub_called = False

    def _track(_hass: Any, entities: list[str], callback: Any) -> Any:
        nonlocal unsub_called
        callback_box["entities"] = entities
        callback_box["callback"] = callback

        def _unsub() -> None:
            nonlocal unsub_called
            unsub_called = True

        return _unsub

    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        _track,
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "dogs": [
                {
                    "dog_id": "fido",
                    "gps_config": {"gps_source": "device_tracker.fido"},
                }
            ]
        },
    )

    await external_bindings.async_setup_external_bindings(hass, entry)

    assert callback_box["entities"] == ["device_tracker.fido"]
    binding = hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"]["fido"]
    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 51.0, "longitude": 7.0, "accuracy": 15}
            )
        }
    )
    callback_box["callback"](event)
    assert binding.task is not None
    await binding.task

    assert gps_manager.add_calls and gps_manager.add_calls[0]["dog_id"] == "fido"
    assert coordinator.patch_calls == ["fido"]

    await external_bindings.async_unload_external_bindings(hass, entry)
    assert unsub_called is True


@pytest.mark.asyncio
async def test_async_setup_external_bindings_skips_non_entity_and_manual_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only entity_id-like GPS sources should register listeners."""
    manager = SimpleNamespace()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(gps_geofence_manager=manager),
        gps_geofence_manager=manager,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    track_calls: list[list[str]] = []
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, entities, _callback: track_calls.append(entities),
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "dogs": [
                {"dog_id": "d1", "gps_config": {"gps_source": "manual"}},
                {"dog_id": "d2", "gps_config": {"gps_source": "mqtt"}},
                {"dog_id": "d3", "gps_config": {"gps_source": "webhook"}},
                {"dog_id": "d4", "gps_config": {"gps_source": "rawsource"}},
            ]
        },
    )

    await external_bindings.async_setup_external_bindings(hass, entry)

    assert track_calls == []


@pytest.mark.asyncio
async def test_async_setup_external_bindings_ignores_small_movements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should ignore GPS updates that are below movement threshold."""

    class _GPSManager:
        async def async_get_current_location(self, _dog_id: str) -> Any:
            return SimpleNamespace(latitude=51.0, longitude=7.0)

        async def async_add_gps_point(self, **_kwargs: Any) -> bool:
            msg = "async_add_gps_point should not be called for tiny movements"
            raise AssertionError(msg)

    class _Coordinator:
        def __init__(self, manager: _GPSManager) -> None:
            self.gps_geofence_manager = manager

        async def async_patch_gps_update(self, _dog_id: str) -> None:
            msg = "async_patch_gps_update should not be called for tiny movements"
            raise AssertionError(msg)

    gps_manager = _GPSManager()
    runtime_data = SimpleNamespace(
        coordinator=_Coordinator(gps_manager),
        gps_geofence_manager=gps_manager,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(external_bindings.asyncio, "sleep", _no_sleep)

    callback_box: dict[str, Any] = {}
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _entities, callback: (
            callback_box.setdefault("callback", callback) or (lambda: None)
        ),
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "dogs": [
                {
                    "dog_id": "fido",
                    "gps_config": {"gps_source": "device_tracker.fido"},
                }
            ]
        },
    )

    await external_bindings.async_setup_external_bindings(hass, entry)

    callback = callback_box["callback"]
    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 51.0, "longitude": 7.0}
            )
        }
    )
    callback(event)

    binding = hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"]["fido"]
    assert binding.task is not None
    await binding.task


@pytest.mark.asyncio
async def test_async_setup_external_bindings_cancels_previous_pending_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new state event should cancel the previous in-flight debounce task."""

    class _GPSManager:
        async def async_get_current_location(self, _dog_id: str) -> None:
            return None

        async def async_add_gps_point(self, **_kwargs: Any) -> bool:
            return False

    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            gps_geofence_manager=_GPSManager(),
            async_patch_gps_update=lambda _dog_id: None,
        ),
        gps_geofence_manager=_GPSManager(),
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    blocker = asyncio.Event()

    async def _blocked_sleep(_seconds: float) -> None:
        await blocker.wait()

    monkeypatch.setattr(external_bindings.asyncio, "sleep", _blocked_sleep)

    callbacks: dict[str, Any] = {}

    def _track(_hass: Any, _entities: list[str], callback: Any) -> Any:
        callbacks["cb"] = callback
        return lambda: None

    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        _track,
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "dogs": [
                {
                    "dog_id": "fido",
                    "gps_config": {"gps_source": "device_tracker.fido"},
                }
            ]
        },
    )
    await external_bindings.async_setup_external_bindings(hass, entry)

    event = SimpleNamespace(
        data={
            "new_state": SimpleNamespace(
                attributes={"latitude": 52.0, "longitude": 8.0}
            )
        }
    )
    callbacks["cb"](event)
    binding = hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"]["fido"]
    first_task = binding.task
    assert first_task is not None

    callbacks["cb"](event)
    second_task = binding.task
    assert second_task is not None
    assert second_task is not first_task
    assert first_task.cancelling() > 0

    blocker.set()
    await second_task


@pytest.mark.asyncio
async def test_async_setup_external_bindings_handles_guard_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Setup should short-circuit for missing managers and malformed dog payloads."""
    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(entry_id="entry-id", data={"dogs": "invalid"})

    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(gps_geofence_manager=None),
        gps_geofence_manager=None,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert DOMAIN not in hass.data

    runtime_data.gps_geofence_manager = SimpleNamespace()
    hass.data = {DOMAIN: {external_bindings._STORE_KEY: {"entry-id": "invalid"}}}
    await external_bindings.async_setup_external_bindings(hass, entry)
    assert isinstance(hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"], dict)


@pytest.mark.asyncio
async def test_async_setup_external_bindings_covers_event_and_duplicate_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Listener callbacks should ignore malformed events and duplicate dog bindings."""

    class _GPSManager:
        def __init__(self) -> None:
            self.calls = 0

        async def async_get_current_location(self, _dog_id: str) -> Any:
            self.calls += 1
            raise RuntimeError("boom")

        async def async_add_gps_point(self, **_kwargs: Any) -> bool:
            return False

    gps_manager = _GPSManager()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            gps_geofence_manager=gps_manager,
            async_patch_gps_update=lambda _dog_id: None,
        ),
        gps_geofence_manager=gps_manager,
    )
    monkeypatch.setattr(
        external_bindings,
        "require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(external_bindings.asyncio, "sleep", _no_sleep)

    callbacks: list[Any] = []
    monkeypatch.setattr(
        external_bindings.event_helper,
        "async_track_state_change_event",
        lambda _hass, _entities, callback: callbacks.append(callback) or (lambda: None),
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-id",
        data={
            "dogs": [
                "bad-item",
                {"dog_id": "", "gps_config": {"gps_source": "device_tracker.a"}},
                {"dog_id": "fido", "gps_config": {}},
                {"dog_id": "fido", "gps_config": {"gps_source": "device_tracker.fido"}},
                {"dog_id": "fido", "gps_config": {"gps_source": "device_tracker.fido"}},
            ]
        },
    )

    await external_bindings.async_setup_external_bindings(hass, entry)
    assert len(callbacks) == 1

    callback = callbacks[0]
    callback(SimpleNamespace(data={"new_state": None}))
    binding = hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"]["fido"]
    assert binding.task is not None
    await binding.task

    callback(SimpleNamespace(data={"new_state": SimpleNamespace(attributes={})}))
    await binding.task

    callback(
        SimpleNamespace(
            data={
                "new_state": SimpleNamespace(
                    attributes={"latitude": 50.0, "longitude": 8.0}
                )
            }
        )
    )
    await binding.task
    assert gps_manager.calls == 1

    # Binding removed after setup: callback should return without creating a task.
    del hass.data[DOMAIN][external_bindings._STORE_KEY]["entry-id"]["fido"]
    callback(
        SimpleNamespace(
            data={
                "new_state": SimpleNamespace(
                    attributes={"latitude": 50.0, "longitude": 8.0}
                )
            }
        )
    )


@pytest.mark.asyncio
async def test_async_unload_external_bindings_handles_non_dict_structures() -> None:
    """Unload should tolerate malformed storage structures without raising errors."""
    hass = SimpleNamespace(data={DOMAIN: {external_bindings._STORE_KEY: []}})
    entry = SimpleNamespace(entry_id="entry-id")

    await external_bindings.async_unload_external_bindings(hass, entry)

    hass.data[DOMAIN][external_bindings._STORE_KEY] = {"entry-id": "invalid"}
    await external_bindings.async_unload_external_bindings(hass, entry)
