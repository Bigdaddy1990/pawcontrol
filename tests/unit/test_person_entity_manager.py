"""Tests for person entity manager diagnostics hooks."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_person_entity_manager_coordinator_snapshot(
    mock_hass: HomeAssistant,
) -> None:
    """Coordinator snapshots should include statistics and diagnostics payloads."""  # noqa: E111

    manager = PersonEntityManager(mock_hass, "test-entry")  # noqa: E111
    manager._targets_cache.store("home", ["notify.mobile_app"], dt_util.now())  # noqa: E111
    manager._state_listeners.append(lambda: None)  # noqa: E111
    manager._stats["cache_hits"] = 3  # noqa: E111
    manager._stats["cache_misses"] = 1  # noqa: E111
    manager._persons["person.jane"] = PersonEntityInfo(  # noqa: E111
        entity_id="person.jane",
        name="jane",
        friendly_name="Jane",
        state="home",
        is_home=True,
        last_updated=dt_util.utcnow(),
        notification_service="notify.mobile_app",
    )

    manager._discovery_task = asyncio.create_task(asyncio.sleep(0))  # noqa: E111
    snapshot = manager.coordinator_snapshot()  # noqa: E111

    assert isinstance(snapshot, CacheDiagnosticsSnapshot)  # noqa: E111
    diagnostics = cast(PersonEntityDiagnostics, snapshot.diagnostics)  # noqa: E111
    assert diagnostics is not None  # noqa: E111
    assert diagnostics["listener_count"] == 1  # noqa: E111
    assert diagnostics["discovery_task_state"] == "running"  # noqa: E111
    cache_entries = diagnostics["cache_entries"]["home"]  # noqa: E111
    assert cache_entries["targets"] == ("notify.mobile_app",)  # noqa: E111
    summary = diagnostics.get("summary")  # noqa: E111
    assert summary is not None  # noqa: E111
    assert summary["persons_home"] == 1  # noqa: E111

    snapshot_payload = cast(PersonEntitySnapshot, snapshot.snapshot)  # noqa: E111
    assert (  # noqa: E111
        snapshot_payload["persons"]["person.jane"]["notification_service"]
        == "notify.mobile_app"
    )

    manager._discovery_task.cancel()  # noqa: E111
    with pytest.raises(asyncio.CancelledError):  # noqa: E111
        await manager._discovery_task


@pytest.mark.unit
@pytest.mark.asyncio
async def test_force_discovery_returns_typed_payload(
    mock_hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force discovery should expose the structured TypedDict payload."""  # noqa: E111

    manager = PersonEntityManager(mock_hass, "typed-entry")  # noqa: E111
    manager._persons["person.jane"] = PersonEntityInfo(  # noqa: E111
        entity_id="person.jane",
        name="jane",
        friendly_name="Jane",
        state="home",
        is_home=True,
        last_updated=dt_util.utcnow(),
    )

    async def _noop_discovery() -> None:  # noqa: E111
        manager._last_discovery = dt_util.utcnow()

    monkeypatch.setattr(  # noqa: E111
        manager, "_discover_person_entities", AsyncMock(side_effect=_noop_discovery)
    )

    result: PersonEntityDiscoveryResult = await manager.async_force_discovery()  # noqa: E111

    assert result["previous_count"] == 1  # noqa: E111
    assert result["current_count"] == 1  # noqa: E111
    assert result["persons_added"] == 0  # noqa: E111
    assert isinstance(result["discovery_time"], str)  # noqa: E111


@pytest.mark.unit
@pytest.mark.asyncio
async def test_validate_configuration_returns_structured_payload(
    mock_hass: HomeAssistant,
) -> None:
    """Validation should return the TypedDict with issues and recommendations."""  # noqa: E111

    mock_hass.services.has_service = lambda *_: False  # noqa: E111
    manager = PersonEntityManager(mock_hass, "validate-entry")  # noqa: E111

    result: PersonEntityValidationResult = await manager.async_validate_configuration()  # noqa: E111

    assert result["valid"] is False  # noqa: E111
    assert any("Fallback to static enabled" in issue for issue in result["issues"])  # noqa: E111
    assert isinstance(result["recommendations"], list)  # noqa: E111
