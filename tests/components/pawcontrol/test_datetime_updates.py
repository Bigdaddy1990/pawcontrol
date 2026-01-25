"""Tests for PawControl datetime updates and persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.datetime import PawControlNextFeedingDateTime
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData


async def _setup_runtime_data(
  hass,
  config_entry,
  coordinator,
  tmp_path,
  *,
  feeding_manager: MagicMock,
) -> PawControlDataManager:
  hass.config.config_dir = str(tmp_path)
  data_manager = PawControlDataManager(
    hass,
    coordinator=coordinator,
    dogs_config=config_entry.data["dogs"],
  )
  await data_manager.async_initialize()

  runtime_data = PawControlRuntimeData(
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=MagicMock(),
    feeding_manager=feeding_manager,
    walk_manager=MagicMock(),
    entity_factory=EntityFactory(coordinator),
    entity_profile="standard",
    dogs=config_entry.data["dogs"],
  )
  store_runtime_data(hass, config_entry, runtime_data)
  return data_manager


@pytest.mark.asyncio
async def test_next_feeding_datetime_persists_and_refreshes(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  feeding_manager = MagicMock()
  feeding_manager.async_refresh_reminder = AsyncMock()
  data_manager = await _setup_runtime_data(
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
    feeding_manager=feeding_manager,
  )
  entity = PawControlNextFeedingDateTime(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  entity.hass = mock_hass

  reminder_time = datetime(2024, 1, 2, 9, 30, tzinfo=UTC)
  await entity.async_set_value(reminder_time)

  assert (
    data_manager._dogs_config["test_dog"]["feeding"]["next_feeding"]
    == reminder_time.isoformat()
  )
  feeding_manager.async_refresh_reminder.assert_awaited_once_with("test_dog")
