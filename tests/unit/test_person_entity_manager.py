"""Tests for person entity manager diagnostics hooks."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest
from custom_components.pawcontrol.person_entity_manager import (
    PersonEntityInfo,
    PersonEntityManager,
)
from custom_components.pawcontrol.types import (
    CacheDiagnosticsSnapshot,
    PersonEntityDiagnostics,
    PersonEntityDiscoveryResult,
    PersonEntitySnapshot,
    PersonEntityValidationResult,
)
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.mark.unit
@pytest.mark.asyncio
async def test_person_entity_manager_coordinator_snapshot(
    mock_hass: HomeAssistant,
) -> None:
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

    assert isinstance(snapshot, CacheDiagnosticsSnapshot)
    diagnostics = cast(PersonEntityDiagnostics, snapshot.diagnostics)
    assert diagnostics is not None
    assert diagnostics["listener_count"] == 1
    assert diagnostics["discovery_task_state"] == "running"
    cache_entries = diagnostics["cache_entries"]["home"]
    assert cache_entries["targets"] == ("notify.mobile_app",)
    summary = diagnostics.get("summary")
    assert summary is not None
    assert summary["persons_home"] == 1

    snapshot_payload = cast(PersonEntitySnapshot, snapshot.snapshot)
    assert (
        snapshot_payload["persons"]["person.jane"]["notification_service"]
        == "notify.mobile_app"
    )

    manager._discovery_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await manager._discovery_task


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_discovery_returns_typed_payload(
    mock_hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force discovery should expose the structured TypedDict payload."""

    manager = PersonEntityManager(mock_hass, "typed-entry")
    manager._persons["person.jane"] = PersonEntityInfo(
        entity_id="person.jane",
        name="jane",
        friendly_name="Jane",
        state="home",
        is_home=True,
        last_updated=dt_util.utcnow(),
    )

    async def _noop_discovery() -> None:
        manager._last_discovery = dt_util.utcnow()

    monkeypatch.setattr(manager, "_discover_person_entities", AsyncMock(side_effect=_noop_discovery))

    result: PersonEntityDiscoveryResult = await manager.async_force_discovery()

    assert result["previous_count"] == 1
    assert result["current_count"] == 1
    assert result["persons_added"] == 0
    assert isinstance(result["discovery_time"], str)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_configuration_returns_structured_payload(
    mock_hass: HomeAssistant,
) -> None:
    """Validation should return the TypedDict with issues and recommendations."""

    mock_hass.services.has_service = lambda *_: False
    manager = PersonEntityManager(mock_hass, "validate-entry")

    result: PersonEntityValidationResult = (
        await manager.async_validate_configuration()
    )

    assert result["valid"] is False
    assert any("Fallback to static enabled" in issue for issue in result["issues"])
    assert isinstance(result["recommendations"], list)
