"""Tests for person entity manager diagnostics hooks."""

from __future__ import annotations

import asyncio

import pytest
from custom_components.pawcontrol.person_entity_manager import PersonEntityManager
from homeassistant.util import dt as dt_util


@pytest.mark.unit
@pytest.mark.asyncio
async def test_person_entity_manager_coordinator_snapshot(mock_hass) -> None:
    """Coordinator snapshots should include statistics and diagnostics payloads."""

    manager = PersonEntityManager(mock_hass, "test-entry")
    manager._notification_targets_cache = {"home": ["notify.mobile_app"]}
    manager._cache_timestamps = {"home": dt_util.now()}
    manager._state_listeners.append(lambda: None)
    manager._stats["cache_hits"] = 3
    manager._stats["cache_misses"] = 1

    manager._discovery_task = asyncio.create_task(asyncio.sleep(0))
    snapshot = manager.coordinator_snapshot()

    assert "stats" in snapshot and "diagnostics" in snapshot
    diagnostics = snapshot["diagnostics"]
    assert diagnostics["listener_count"] == 1
    cache_entries = diagnostics["cache_entries"]["home"]
    assert cache_entries["targets"] == ["notify.mobile_app"]

    manager._discovery_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await manager._discovery_task
