"""Unit tests for GardenManager snapshots."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.garden_manager import GardenManager, GardenSession


def test_build_garden_snapshot_returns_structured_payload(
  hass: HomeAssistant,
) -> None:
  """Garden snapshots should expose structured payloads."""
  manager = GardenManager(hass, "entry")
  manager._store.async_load = AsyncMock(return_value={})
  manager._store.async_save = AsyncMock()
  now = dt_util.utcnow()

  active_session = GardenSession(
    session_id="garden-active",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=10),
  )
  active_session.weather_conditions = "Sunny"
  active_session.temperature = 24.0
  active_session.activities.append({"activity_type": "play"})
  active_session.poop_count = 1

  completed_session = GardenSession(
    session_id="garden-complete",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(hours=2),
    end_time=now - timedelta(hours=1, minutes=30),
  )
  completed_session.weather_conditions = "Cloudy"
  completed_session.temperature = 20.0

  manager._sessions["dog"] = active_session
  manager._history["dog"] = [completed_session]
  manager._pending_confirmations["confirm"] = {
    "type": "poop_confirmation",
    "dog_id": "dog",
    "session_id": "garden-active",
    "timestamp": now - timedelta(minutes=1),
    "timeout": now + timedelta(minutes=4),
  }

  snapshot = manager.build_garden_snapshot("dog")

  assert snapshot["status"] == "active"
  assert snapshot["active_session"]
  assert snapshot["active_session"]["session_id"] == "garden-active"
  assert snapshot["last_session"]["session_id"] == "garden-complete"
  assert snapshot["pending_confirmations"][0]["session_id"] == "garden-active"


@pytest.mark.asyncio
async def test_end_garden_session_persists_history(
  hass: HomeAssistant,
) -> None:
  """Ending a session should store history."""
  manager = GardenManager(hass, "entry")
  manager._store.async_load = AsyncMock(return_value={})
  manager._store.async_save = AsyncMock()
  now = dt_util.utcnow()

  manager._sessions["dog"] = GardenSession(
    session_id="garden-active",
    dog_id="dog",
    dog_name="Buddy",
    start_time=now - timedelta(minutes=5),
  )

  session = await manager.async_end_garden_session("dog")

  assert session is not None
  assert manager._history["dog"]
  manager._store.async_save.assert_called_once()
