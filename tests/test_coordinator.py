"""Coordinator refresh resilience regression tests."""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.exceptions import ConfigEntryAuthFailed, UpdateFailed


class _DummyRegistry:
    def __init__(self, ids: list[str]) -> None:
        self._ids = ids

    def __len__(self) -> int:
        return len(self._ids)

    def ids(self) -> list[str]:
        return list(self._ids)

    def empty_payload(self) -> dict[str, Any]:
        return {"status": {}}


def _make_coordinator() -> PawControlCoordinator:
    coordinator = cast(
        PawControlCoordinator,
        PawControlCoordinator.__new__(PawControlCoordinator),
    )
    coordinator.registry = _DummyRegistry(["dog-1"])
    coordinator._data = {"dog-1": {"health": {"status": "cached"}}}
    coordinator._metrics = SimpleNamespace(consecutive_errors=0)
    coordinator.last_update_success = True
    coordinator.update_interval = timedelta(seconds=60)
    return coordinator


@pytest.mark.asyncio
async def test_success_refresh_updates_state_and_keeps_availability() -> None:
    coordinator = _make_coordinator()

    async def _prepare_entry() -> None:
        return None

    async def _execute_cycle(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        return {"dog-1": {"health": {"status": "fresh"}}}, object()

    async def _sync(_data: dict[str, Any]) -> None:
        return None

    coordinator.async_prepare_entry = _prepare_entry
    coordinator._execute_cycle = _execute_cycle
    coordinator._synchronize_module_states = _sync

    refreshed = await coordinator._async_update_data()

    assert refreshed["dog-1"]["health"]["status"] == "fresh"
    assert coordinator._data["dog-1"]["health"]["status"] == "fresh"
    assert coordinator.available is True


@pytest.mark.asyncio
async def test_timeout_raises_update_failed_and_preserves_cached_state() -> None:
    coordinator = _make_coordinator()
    coordinator.last_update_success = False
    coordinator._metrics.consecutive_errors = 6

    async def _prepare_entry() -> None:
        return None

    async def _execute_cycle(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        raise TimeoutError("refresh timed out")

    coordinator.async_prepare_entry = _prepare_entry
    coordinator._execute_cycle = _execute_cycle

    with pytest.raises(UpdateFailed, match="refresh timed out"):
        await coordinator._async_update_data()

    assert coordinator._data == {"dog-1": {"health": {"status": "cached"}}}
    assert coordinator.available is False


@pytest.mark.asyncio
async def test_auth_error_is_propagated_and_state_remains_consistent() -> None:
    coordinator = _make_coordinator()
    coordinator.last_update_success = False
    coordinator._metrics.consecutive_errors = 5

    async def _prepare_entry() -> None:
        return None

    async def _execute_cycle(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        raise ConfigEntryAuthFailed("token expired")

    coordinator.async_prepare_entry = _prepare_entry
    coordinator._execute_cycle = _execute_cycle

    with pytest.raises(ConfigEntryAuthFailed, match="token expired"):
        await coordinator._async_update_data()

    assert coordinator._data == {"dog-1": {"health": {"status": "cached"}}}
    assert coordinator.available is False


@pytest.mark.asyncio
async def test_inconsistent_payload_is_returned_and_stored_without_crash() -> None:
    coordinator = _make_coordinator()

    async def _prepare_entry() -> None:
        return None

    async def _execute_cycle(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        return {"dog-1": cast(Any, "invalid-shape")}, object()

    async def _sync(_data: dict[str, Any]) -> None:
        return None

    coordinator.async_prepare_entry = _prepare_entry
    coordinator._execute_cycle = _execute_cycle
    coordinator._synchronize_module_states = _sync

    refreshed = await coordinator._async_update_data()

    assert refreshed == {"dog-1": "invalid-shape"}
    assert coordinator._data == {"dog-1": "invalid-shape"}
    assert coordinator.available is True


@pytest.mark.asyncio
async def test_recovery_after_error_restores_availability_with_fresh_state() -> None:
    coordinator = _make_coordinator()
    coordinator.last_update_success = False
    coordinator._metrics.consecutive_errors = 8

    async def _prepare_entry() -> None:
        return None

    async def _execute_cycle_fail(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        raise TimeoutError("temporary outage")

    coordinator.async_prepare_entry = _prepare_entry
    coordinator._execute_cycle = _execute_cycle_fail

    with pytest.raises(UpdateFailed, match="temporary outage"):
        await coordinator._async_update_data()

    assert coordinator.available is False
    assert coordinator._data == {"dog-1": {"health": {"status": "cached"}}}

    async def _execute_cycle_ok(_dog_ids: list[str]) -> tuple[dict[str, Any], object]:
        return {"dog-1": {"health": {"status": "recovered"}}}, object()

    async def _sync(_data: dict[str, Any]) -> None:
        return None

    coordinator._execute_cycle = _execute_cycle_ok
    coordinator._synchronize_module_states = _sync
    coordinator.last_update_success = True
    coordinator._metrics.consecutive_errors = 0

    refreshed = await coordinator._async_update_data()

    assert refreshed["dog-1"]["health"]["status"] == "recovered"
    assert coordinator._data["dog-1"]["health"]["status"] == "recovered"
    assert coordinator.available is True
