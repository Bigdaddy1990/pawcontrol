"""Focused coordinator coverage tests for guard and fallback branches."""

from collections.abc import Mapping
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.pawcontrol import coordinator as coordinator_module
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


@pytest.mark.asyncio
async def test_refresh_subset_merges_data_and_updates_subscribers() -> None:
    coordinator = _make_coordinator()
    coordinator._data = {"dog-2": {"health": {"status": "ok"}}}
    synchronized: list[dict[str, dict[str, dict[str, str]]]] = []

    async def _execute_cycle(
        _dog_ids: list[str],
    ) -> tuple[dict[str, dict[str, dict[str, str]]], object]:
        return {"dog-1": {"gps": {"status": "fresh"}}}, object()

    async def _sync(data: dict[str, dict[str, dict[str, str]]]) -> None:
        synchronized.append(data)

    coordinator._execute_cycle = _execute_cycle
    coordinator._synchronize_module_states = _sync

    await coordinator._refresh_subset(["dog-1"])

    assert synchronized == [{"dog-1": {"gps": {"status": "fresh"}}}]
    assert coordinator._data["dog-1"] == {"gps": {"status": "fresh"}}
    assert coordinator._last_updated == {
        "dog-1": {"gps": {"status": "fresh"}},
        "dog-2": {"health": {"status": "ok"}},
    }


@pytest.mark.asyncio
async def test_request_selective_refresh_handles_none_and_deduplicates_ids() -> None:
    coordinator = _make_coordinator()
    requested_full = False
    requested_subset: list[list[str]] = []

    async def _request_refresh() -> None:
        nonlocal requested_full
        requested_full = True

    async def _refresh_subset(dog_ids: list[str]) -> None:
        requested_subset.append(dog_ids)

    coordinator.async_request_refresh = _request_refresh
    coordinator._refresh_subset = _refresh_subset

    await coordinator.async_request_selective_refresh()
    await coordinator.async_request_selective_refresh(["dog-1", "", "dog-1", "dog-2"])

    assert requested_full is True
    assert requested_subset == [["dog-1", "dog-2"]]


@pytest.mark.asyncio
async def test_async_patch_gps_update_merges_latest_module_payloads() -> None:
    """GPS patch updates existing payload in place and notifies subscribers."""
    coordinator = _make_coordinator()
    coordinator.registry = _DummyRegistry(["dog-1"])
    coordinator._setup_complete = True
    coordinator.last_update_success = True
    coordinator._data = {"dog-1": {"health": {"status": "ok"}}}

    async def _gps_payload(_dog_id: str) -> dict[str, float]:
        return {"lat": 50.0, "lon": 8.0}

    async def _geofencing_payload(_dog_id: str) -> dict[str, bool]:
        return {"inside_zone": True}

    coordinator._modules = SimpleNamespace(
        gps=SimpleNamespace(async_get_data=_gps_payload),
        geofencing=SimpleNamespace(async_get_data=_geofencing_payload),
    )

    updates: list[dict[str, Any]] = []
    coordinator.async_set_updated_data = lambda data: updates.append(data)

    await coordinator.async_patch_gps_update("dog-1")

    assert coordinator._data["dog-1"]["health"] == {"status": "ok"}
    assert coordinator._data["dog-1"]["gps"] == {"lat": 50.0, "lon": 8.0}
    assert coordinator._data["dog-1"]["geofencing"] == {"inside_zone": True}
    assert updates and updates[-1]["dog-1"]["gps"]["lat"] == 50.0


@pytest.mark.asyncio
async def test_async_maintenance_delegates_to_runtime_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _make_coordinator()
    called_with: list[PawControlCoordinator] = []

    async def _fake_run_maintenance(instance: PawControlCoordinator) -> None:
        called_with.append(instance)

    monkeypatch.setattr(
        coordinator_module.coordinator_tasks, "run_maintenance", _fake_run_maintenance
    )

    await coordinator._async_maintenance()

    assert called_with == [coordinator]


@pytest.mark.asyncio
async def test_prepare_entry_returns_early_when_setup_completed() -> None:
    coordinator = _make_coordinator()
    coordinator._setup_complete = True
    coordinator._modules = SimpleNamespace(
        clear_caches=lambda: (_ for _ in ()).throw(AssertionError("should not run"))
    )

    await coordinator.async_prepare_entry()

    assert coordinator._setup_complete is True


@pytest.mark.asyncio
async def test_fetch_dog_data_delegates_to_runtime_fetcher() -> None:
    coordinator = _make_coordinator()
    expected = {"status": {"ok": True}}

    async def _fetch_dog_data(dog_id: str) -> dict[str, dict[str, bool]]:
        assert dog_id == "dog-1"
        return expected

    coordinator._runtime = SimpleNamespace(_fetch_dog_data=_fetch_dog_data)

    result = await coordinator._fetch_dog_data("dog-1")

    assert result == expected


@pytest.mark.asyncio
async def test_async_patch_gps_update_updates_gps_and_geofencing_payloads() -> None:
    coordinator = _make_coordinator()
    coordinator._setup_complete = True
    coordinator.last_update_success = True
    coordinator._data = {"dog-1": {"health": {"status": "ok"}}}

    async def _gps_get_data(dog_id: str) -> dict[str, float]:
        assert dog_id == "dog-1"
        return {"lat": 1.0, "lon": 2.0}

    async def _geofencing_get_data(dog_id: str) -> dict[str, str]:
        assert dog_id == "dog-1"
        return {"zone": "home"}

    coordinator._modules = SimpleNamespace(
        gps=SimpleNamespace(async_get_data=_gps_get_data),
        geofencing=SimpleNamespace(async_get_data=_geofencing_get_data),
    )

    await coordinator.async_patch_gps_update("dog-1")

    assert coordinator._data["dog-1"]["gps"] == {"lat": 1.0, "lon": 2.0}
    assert coordinator._data["dog-1"]["geofencing"] == {"zone": "home"}
    assert coordinator._last_updated["dog-1"]["gps"] == {"lat": 1.0, "lon": 2.0}


def test_get_performance_snapshot_uses_default_rejection_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = _make_coordinator()
    coordinator._adaptive_polling = SimpleNamespace(
        as_diagnostics=lambda: {"state": "healthy"}
    )
    coordinator._entity_budget = SimpleNamespace(summary=lambda: {"tracked": 0})
    coordinator._metrics = {"latency_ms": 12}
    coordinator.last_update_success = True
    coordinator.notification_manager = None
    coordinator._last_cycle = SimpleNamespace(to_dict=lambda: {"duration_ms": 5})
    coordinator.config_entry = SimpleNamespace(runtime_data=None)

    monkeypatch.setattr(
        coordinator_module,
        "collect_resilience_diagnostics",
        lambda _coordinator: {"summary": {"status": "ok"}},
    )
    monkeypatch.setattr(
        coordinator_module.coordinator_observability,
        "build_performance_snapshot",
        lambda **_: {"executed": 1},
    )
    monkeypatch.setattr(
        coordinator_module.coordinator_tasks,
        "default_rejection_metrics",
        lambda: {"blocked": 0},
    )
    monkeypatch.setattr(
        coordinator_module,
        "get_runtime_performance_stats",
        lambda _runtime_data: {},
    )
    monkeypatch.setattr(
        coordinator_module.coordinator_tasks,
        "resolve_service_guard_metrics",
        lambda _payload: {"skipped": 0},
    )
    monkeypatch.setattr(
        coordinator_module.coordinator_tasks,
        "resolve_entity_factory_guard_metrics",
        lambda _payload: {"total": 0},
    )

    snapshot = coordinator.get_performance_snapshot()

    assert snapshot["rejection_metrics"] == {"blocked": 0}
    assert snapshot["service_execution"] == {
        "guard_metrics": {"skipped": 0},
        "entity_factory_guard": {"total": 0},
        "rejection_metrics": {"blocked": 0},
    }
    assert snapshot["last_cycle"] == {"duration_ms": 5}
