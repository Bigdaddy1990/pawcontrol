"""Unit tests for WalkManager."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.util import dt as dt_util

from custom_components.pawcontrol.exceptions import (
  WalkAlreadyInProgressError,
  WalkNotInProgressError,
)
from custom_components.pawcontrol.walk_manager import WalkManager


@pytest.fixture
def walk_manager(mock_hass) -> WalkManager:
  """Return a WalkManager with storage mocked."""
  manager = WalkManager(mock_hass, "entry")
  manager._store.async_load = AsyncMock(return_value={})
  manager._store.async_save = AsyncMock()
  return manager


@pytest.mark.unit
@pytest.mark.asyncio
async def test_initialize_sets_history(walk_manager: WalkManager) -> None:
  """Initialize should seed history for provided dogs."""
  await walk_manager.async_initialize(["buddy", "max"])

  assert "buddy" in walk_manager._history
  assert "max" in walk_manager._history


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_walk_tracks_active_session(walk_manager: WalkManager) -> None:
  """Starting a walk should create an active session."""
  await walk_manager.async_initialize(["buddy"])

  walk_id = await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")

  assert walk_id
  assert "buddy" in walk_manager._active_walks


@pytest.mark.unit
@pytest.mark.asyncio
async def test_start_walk_raises_when_active(walk_manager: WalkManager) -> None:
  """Starting another walk while one is active should fail."""
  await walk_manager.async_initialize(["buddy"])
  await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")

  with pytest.raises(WalkAlreadyInProgressError):
    await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_walk_persists_history(walk_manager: WalkManager) -> None:
  """Ending a walk should append to history and persist."""
  await walk_manager.async_initialize(["buddy"])
  await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")

  finished = await walk_manager.async_end_walk(dog_id="buddy")

  assert finished["status"] == "completed"
  assert walk_manager._history["buddy"]
  walk_manager._store.async_save.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_walk_without_active_raises(walk_manager: WalkManager) -> None:
  """Ending without an active walk raises an error."""
  await walk_manager.async_initialize(["buddy"])

  with pytest.raises(WalkNotInProgressError):
    await walk_manager.async_end_walk(dog_id="buddy")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_add_gps_point_requires_active_walk(walk_manager: WalkManager) -> None:
  """GPS points only add when an active walk exists."""
  await walk_manager.async_initialize(["buddy"])

  added = await walk_manager.async_add_gps_point(
    dog_id="buddy",
    latitude=52.52,
    longitude=13.405,
  )
  assert added is False

  await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")
  added = await walk_manager.async_add_gps_point(
    dog_id="buddy",
    latitude=52.52,
    longitude=13.405,
  )
  assert added is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_walk_data_aggregates_history(walk_manager: WalkManager) -> None:
  """Aggregated stats should reflect stored history."""
  await walk_manager.async_initialize(["buddy"])

  start = dt_util.utcnow() - timedelta(minutes=30)
  walk_manager._history["buddy"] = [
    {
      "walk_id": "walk-buddy-1",
      "dog_id": "buddy",
      "walk_type": "manual",
      "start_time": dt_util.as_utc(start).isoformat(),
      "end_time": dt_util.as_utc(dt_util.utcnow()).isoformat(),
      "duration": 1800.0,
      "distance": 1200.0,
      "status": "completed",
      "path": [],
    },
  ]

  data = await walk_manager.async_get_walk_data("buddy")

  assert data["walks_today"] == 1
  assert data["total_duration_today"] == 1800.0
  assert data["total_distance_today"] == 1200.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_history_limit_is_enforced(walk_manager: WalkManager) -> None:
  """History should trim to the configured limit."""
  await walk_manager.async_initialize(["buddy"])
  now = dt_util.utcnow()

  walk_manager._history["buddy"] = [
    {
      "walk_id": f"walk-{idx}",
      "dog_id": "buddy",
      "walk_type": "manual",
      "start_time": dt_util.as_utc(now - timedelta(minutes=idx)).isoformat(),
      "end_time": dt_util.as_utc(now - timedelta(minutes=idx - 1)).isoformat(),
      "duration": 60.0,
      "distance": 100.0,
      "status": "completed",
      "path": [],
    }
    for idx in range(105)
  ]

  await walk_manager.async_start_walk(dog_id="buddy", walk_type="manual")
  await walk_manager.async_end_walk(dog_id="buddy")

  assert len(walk_manager._history["buddy"]) <= 100
