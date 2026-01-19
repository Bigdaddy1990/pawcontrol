"""Unit tests for entity platform setup flows."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import PawControlRuntimeData

PLATFORM_MODULES: tuple[str, ...] = (
  "custom_components.pawcontrol.binary_sensor",
  "custom_components.pawcontrol.button",
  "custom_components.pawcontrol.date",
  "custom_components.pawcontrol.datetime",
  "custom_components.pawcontrol.device_tracker",
  "custom_components.pawcontrol.number",
  "custom_components.pawcontrol.select",
  "custom_components.pawcontrol.sensor",
  "custom_components.pawcontrol.switch",
  "custom_components.pawcontrol.text",
)


@pytest.fixture
def runtime_data(mock_coordinator, mock_dog_config) -> PawControlRuntimeData:
  entity_factory = EntityFactory(mock_coordinator)
  return PawControlRuntimeData(
    coordinator=mock_coordinator,
    data_manager=MagicMock(),
    notification_manager=MagicMock(),
    feeding_manager=MagicMock(),
    walk_manager=MagicMock(),
    entity_factory=entity_factory,
    entity_profile="standard",
    dogs=[mock_dog_config],
  )


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", PLATFORM_MODULES)
async def test_platform_setup_skips_without_runtime_data(
  hass,
  mock_config_entry,
  module_path: str,
) -> None:
  module = importlib.import_module(module_path)
  async_add_entities = AsyncMock()

  await module.async_setup_entry(hass, mock_config_entry, async_add_entities)

  async_add_entities.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", PLATFORM_MODULES)
async def test_platform_setup_adds_entities_when_configured(
  hass,
  mock_config_entry,
  runtime_data: PawControlRuntimeData,
  module_path: str,
) -> None:
  store_runtime_data(hass, mock_config_entry, runtime_data)
  module = importlib.import_module(module_path)
  async_add_entities = AsyncMock()

  await module.async_setup_entry(hass, mock_config_entry, async_add_entities)

  assert async_add_entities.called
  args, _ = async_add_entities.call_args
  added_entities: Iterable[Any] = args[0]
  assert list(added_entities)
