"""Tests for person entity manager diagnostics hooks."""

from __future__ import annotations

import asyncio

import pytest
from custom_components.pawcontrol.person_entity_manager import (
    PersonEntityInfo,
    PersonEntityManager,
)
from homeassistant.util import dt as dt_util


@pytest.mark.unit
@pytest.mark.asyncio
async def test_person_entity_manager_coordinator_snapshot(mock_hass) -> None:
    """Coordinator snapshots should include statistics and diagnostics payloads."""

    manager = PersonEntityManager(mock_hass, "test-entry")
    manager._targets_cache.store("home", ["notify.mobile_app"], dt_util.now())
    manager._state_listeners.append(lambda: None)
    manager._stats["cache_hits"] = 3
    manager._stats["cache_misses"] = 1
    manager._persons["person.jane"] = PersonEntityInfo(
        entity_id="person.jane",
        name="jane",
        friendly_name="Jane",
        state="home",
        is_home=True,
        last_updated=dt_util.utcnow(),
        notification_service="notify.mobile_app",
    )

    manager._discovery_task = asyncio.create_task(asyncio.sleep(0))
    snapshot = manager.coordinator_snapshot()

    assert "stats" in snapshot and "diagnostics" in snapshot and "snapshot" in snapshot
    diagnostics = snapshot["diagnostics"]
    assert diagnostics["listener_count"] == 1
    assert diagnostics["discovery_task_state"] == "running"
    cache_entries = diagnostics["cache_entries"]["home"]
    assert cache_entries["targets"] == ("notify.mobile_app",)
    assert diagnostics["summary"]["persons_home"] == 1

    snapshot_payload = snapshot["snapshot"]
    assert (
        snapshot_payload["persons"]["person.jane"]["notification_service"]
        == "notify.mobile_app"
    )

    manager._discovery_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await manager._discovery_task
