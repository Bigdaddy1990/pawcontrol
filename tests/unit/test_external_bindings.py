"""Unit tests for external entity bindings."""

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.pawcontrol.const import CONF_DOGS, CONF_GPS_SOURCE, DOMAIN
from custom_components.pawcontrol.external_bindings import (
    _STORE_KEY,
    _Binding,
    async_setup_external_bindings,
    async_unload_external_bindings,
)
from custom_components.pawcontrol.gps_manager import LocationSource


@pytest.mark.asyncio
async def test_async_setup_external_bindings_processes_entity_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity state changes should enqueue GPS updates and patch coordinator state."""
    recorded_points: list[dict[str, Any]] = []

    class _GpsManager:
        async def async_get_current_location(self, _dog_id: str) -> Any:
            return None

        async def async_add_gps_point(self, **kwargs: Any) -> bool:
            recorded_points.append(kwargs)
            return True

    gps_manager = _GpsManager()
    coordinator = SimpleNamespace(
        gps_geofence_manager=None,
        async_patch_gps_update=AsyncMock(),
    )
    runtime_data = SimpleNamespace(
        coordinator=coordinator,
        gps_geofence_manager=gps_manager,
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    callbacks: dict[str, Any] = {}
    unsubscribed = {"called": False}

    def _track_state_change_event(
        _hass: Any, entities: list[str], callback: Any
    ) -> Any:
        callbacks[entities[0]] = callback

        def _unsub() -> None:
            unsubscribed["called"] = True

        return _unsub

    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.event_helper.async_track_state_change_event",
        _track_state_change_event,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.asyncio.sleep",
        _no_sleep,
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={
            CONF_DOGS: [
                {
                    "dog_id": "buddy",
                    "gps_config": {CONF_GPS_SOURCE: "device_tracker.buddy_phone"},
                }
            ]
        },
    )

    await async_setup_external_bindings(hass, entry)

    callback = callbacks["device_tracker.buddy_phone"]
    callback(
        SimpleNamespace(
            data={
                "new_state": SimpleNamespace(
                    attributes={"latitude": 51.5, "longitude": -0.13, "gps_accuracy": 8}
                )
            }
        )
    )

    bindings = hass.data[DOMAIN][_STORE_KEY][entry.entry_id]
    binding = bindings["buddy"]
    assert isinstance(binding, _Binding)
    assert binding.task is not None
    await binding.task

    assert len(recorded_points) == 1
    assert recorded_points[0]["dog_id"] == "buddy"
    assert recorded_points[0]["source"] is LocationSource.ENTITY
    coordinator.async_patch_gps_update.assert_awaited_once_with("buddy")

    await async_unload_external_bindings(hass, entry)

    assert unsubscribed["called"] is True


@pytest.mark.asyncio
async def test_async_setup_external_bindings_ignores_tiny_movement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tiny coordinate changes should be ignored as movement noise."""
    add_point = AsyncMock(return_value=True)

    class _GpsManager:
        async def async_get_current_location(self, _dog_id: str) -> Any:
            return SimpleNamespace(latitude=10.0, longitude=20.0)

        async def async_add_gps_point(self, **kwargs: Any) -> bool:
            return await add_point(**kwargs)

    gps_manager = _GpsManager()
    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            gps_geofence_manager=None,
            async_patch_gps_update=AsyncMock(),
        ),
        gps_geofence_manager=gps_manager,
    )

    async def _no_sleep(_seconds: float) -> None:
        return None

    callbacks: dict[str, Any] = {}

    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.require_runtime_data",
        lambda _hass, _entry: runtime_data,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.asyncio.sleep",
        _no_sleep,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.external_bindings.event_helper.async_track_state_change_event",
        lambda _hass, entities, callback: (
            callbacks.setdefault(entities[0], callback) or (lambda: None)
        ),
    )

    hass = SimpleNamespace(data={}, async_create_task=asyncio.create_task)
    entry = SimpleNamespace(
        entry_id="entry-2",
        data={
            CONF_DOGS: [
                {
                    "dog_id": "max",
                    "gps_config": {CONF_GPS_SOURCE: "person.max"},
                }
            ]
        },
    )

    await async_setup_external_bindings(hass, entry)

    callback = callbacks["person.max"]
    callback(
        SimpleNamespace(
            data={
                "new_state": SimpleNamespace(
                    attributes={"latitude": 10.000001, "longitude": 20.000001}
                )
            }
        )
    )

    binding = hass.data[DOMAIN][_STORE_KEY][entry.entry_id]["max"]
    assert binding.task is not None
    await binding.task

    add_point.assert_not_awaited()
