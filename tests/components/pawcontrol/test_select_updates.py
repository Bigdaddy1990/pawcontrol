"""Tests for PawControl select updates and persistence."""

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
  hass.config.config_dir = str(tmp_path)  # noqa: E111
  data_manager = PawControlDataManager(  # noqa: E111
    hass,
    coordinator=coordinator,
    dogs_config=config_entry.data["dogs"],
  )
  await data_manager.async_initialize()  # noqa: E111

  runtime_data = PawControlRuntimeData(  # noqa: E111
    coordinator=coordinator,
    data_manager=data_manager,
    notification_manager=MagicMock(),
    feeding_manager=feeding_manager or MagicMock(),
    walk_manager=walk_manager or MagicMock(),
    entity_factory=EntityFactory(coordinator),
    entity_profile="standard",
    dogs=config_entry.data["dogs"],
  )
  store_runtime_data(hass, config_entry, runtime_data)  # noqa: E111
  return data_manager  # noqa: E111


@pytest.mark.asyncio
async def test_default_meal_type_select_persists_config(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  data_manager = await _setup_runtime_data(  # noqa: E111
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlDefaultMealTypeSelect(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass  # noqa: E111

  await select.async_select_option("breakfast")  # noqa: E111

  assert (  # noqa: E111
    data_manager._dogs_config["test_dog"]["feeding"]["default_meal_type"] == "breakfast"
  )
  assert (  # noqa: E111
    mock_coordinator.data["test_dog"]["feeding"]["default_meal_type"] == "breakfast"
  )


@pytest.mark.asyncio
async def test_feeding_mode_select_persists_config_and_refreshes(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  mock_coordinator.async_refresh_dog = AsyncMock()  # noqa: E111
  data_manager = await _setup_runtime_data(  # noqa: E111
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlFeedingModeSelect(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass  # noqa: E111

  await select.async_select_option("scheduled")  # noqa: E111

  assert data_manager._dogs_config["test_dog"]["feeding"]["mode"] == "scheduled"  # noqa: E111
  assert mock_coordinator.data["test_dog"]["feeding"]["mode"] == "scheduled"  # noqa: E111
  mock_coordinator.async_refresh_dog.assert_awaited_once_with("test_dog")  # noqa: E111


@pytest.mark.asyncio
async def test_walk_mode_select_persists_config(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  data_manager = await _setup_runtime_data(  # noqa: E111
    mock_hass,
    mock_config_entry,
    mock_coordinator,
    tmp_path,
  )
  select = PawControlWalkModeSelect(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  select.hass = mock_hass  # noqa: E111

  await select.async_select_option("manual")  # noqa: E111

  assert data_manager._dogs_config["test_dog"]["walk"]["mode"] == "manual"  # noqa: E111
  assert mock_coordinator.data["test_dog"]["walk"]["mode"] == "manual"  # noqa: E111
