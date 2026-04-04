"""Focused coordinator coverage tests for guard and fallback branches."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.pawcontrol.coordinator import PawControlCoordinator


class _DummyRegistry:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def ids(self) -> list[str]:
        return list(self._ids)

    def empty_payload(self) -> dict[str, Any]:
        return {"status": {}}


class _DummyGardenManager:
    def __init__(self) -> None:
        self.ended: list[str] = []

    def get_active_session(self, dog_id: str) -> object | None:
        return None if dog_id == "dog-none" else object()

    async def async_end_garden_session(
        self,
        dog_id: str,
        notes: str,
        suppress_notifications: bool,
    ) -> None:
        assert notes == "Paused due to active walk"
        assert suppress_notifications is True
        self.ended.append(dog_id)

    def build_garden_snapshot(self, dog_id: str) -> dict[str, Any]:
        return {"dog_id": dog_id, "state": "ended"}


def _make_coordinator() -> PawControlCoordinator:
    coordinator = cast(
        PawControlCoordinator, PawControlCoordinator.__new__(PawControlCoordinator)
    )
    coordinator.registry = _DummyRegistry(["dog-1", "dog-none"])
    coordinator._data = {}
    coordinator.update_interval = timedelta(seconds=60)
    coordinator.async_set_updated_data = lambda data: setattr(
        coordinator, "_last_updated", data
    )
    return coordinator


@pytest.mark.asyncio
async def test_refresh_subset_returns_early_for_empty_ids() -> None:
    coordinator = _make_coordinator()
    called = False

    async def _execute_cycle(
        _dog_ids: list[str],
    ) -> tuple[dict[str, dict[str, Any]], object]:
        nonlocal called
        called = True
        return {}, object()

    coordinator._execute_cycle = _execute_cycle
    coordinator._synchronize_module_states = lambda _: None

    await coordinator._refresh_subset([])

    assert called is False


@pytest.mark.asyncio
async def test_async_apply_module_updates_ignores_unknown_and_invalid_module() -> None:
    coordinator = _make_coordinator()

    await coordinator.async_apply_module_updates("unknown", "gps", {"lat": 1})
    await coordinator.async_apply_module_updates("dog-1", "", {"lat": 1})

    assert coordinator._data == {}


@pytest.mark.asyncio
async def test_apply_module_updates_uses_empty_payload_for_non_mapping() -> None:
    coordinator = _make_coordinator()
    coordinator._data["dog-1"] = cast(Any, "stale")

    await coordinator.async_apply_module_updates("dog-1", "gps", {"lat": 1, "lng": 2})

    payload = coordinator._data["dog-1"]
    assert isinstance(payload, Mapping)
    assert payload["gps"] == {"lat": 1, "lng": 2}


@pytest.mark.asyncio
async def test_synchronize_module_states_handles_non_mapping_and_inactive_walk() -> (
    None
):
    coordinator = _make_coordinator()
    garden_manager = _DummyGardenManager()
    coordinator.garden_manager = garden_manager

    data: dict[str, Any] = {
        "bad": "payload",
        "dog-1": {"walk": {"walk_in_progress": False}},
        "dog-none": {"walk": {"walk_in_progress": True}},
        "dog-active": {"walk": {"walk_in_progress": True}},
    }

    await coordinator._synchronize_module_states(cast(dict[str, Any], data))

    assert garden_manager.ended == ["dog-active"]
    assert data["dog-active"]["garden"]["state"] == "ended"


def test_apply_adaptive_interval_skips_tiny_changes() -> None:
    coordinator = _make_coordinator()

    coordinator._apply_adaptive_interval(60.005)

    assert coordinator.update_interval.total_seconds() == 60
