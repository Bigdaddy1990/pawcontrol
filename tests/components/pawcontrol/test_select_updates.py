"""Tests for PawControl select updates and persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.select import (
  PawControlDefaultMealTypeSelect,
  PawControlFeedingModeSelect,
  PawControlWalkModeSelect,
)
from custom_components.pawcontrol.types import PawControlRuntimeData


async def _setup_runtime_data(
  hass,
  config_entry,
  coordinator,
  tmp_path,
  *,
  feeding_manager: MagicMock | None = None,
  walk_manager: MagicMock | None = None,
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
    feeding_manager=feeding_manager or MagicMock(),
    walk_manager=walk_manager or MagicMock(),
    entity_factory=EntityFactory(coordinator),
    entity_profile="standard",
    dogs=config_entry.data["dogs"],
  )
  store_runtime_data(hass, config_entry, runtime_data)
  return data_manager


@pytest.mark.asyncio
async def test_default_meal_type_select_persists_config(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  data_manager = await _setup_runtime_data(
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlDefaultMealTypeSelect(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass

  await select.async_select_option("breakfast")

  assert (
    data_manager._dogs_config["test_dog"]["feeding"]["default_meal_type"] == "breakfast"
  )


@pytest.mark.asyncio
async def test_feeding_mode_select_persists_config_and_refreshes(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  mock_coordinator.async_refresh_dog = AsyncMock()
  data_manager = await _setup_runtime_data(
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlFeedingModeSelect(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass

  await select.async_select_option("scheduled")

  assert data_manager._dogs_config["test_dog"]["feeding"]["mode"] == "scheduled"
  mock_coordinator.async_refresh_dog.assert_awaited_once_with("test_dog")


@pytest.mark.asyncio
async def test_walk_mode_select_persists_config(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  data_manager = await _setup_runtime_data(
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlWalkModeSelect(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass

  await select.async_select_option("manual")

  assert data_manager._dogs_config["test_dog"]["walk"]["mode"] == "manual"
