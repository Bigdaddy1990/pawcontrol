"""Unit tests for entity platform setup flows."""

from __future__ import annotations

import importlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
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


def test_walk_and_garden_attributes_are_standardised(mock_coordinator) -> None:
  from custom_components.pawcontrol.binary_sensor import (
    PawControlInSafeZoneBinarySensor,
    PawControlWalkInProgressBinarySensor,
  )
  from custom_components.pawcontrol.sensor import PawControlGardenTimeTodaySensor

  started_at = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
  last_seen = datetime(2024, 1, 1, 12, 45, tzinfo=UTC)

  dog_payload = mock_coordinator._data["test_dog"]
  dog_payload["walk"] = {
    "walk_in_progress": True,
    "current_walk_start": started_at,
    "current_walk_duration": 15,
    "current_walk_distance": 1200,
  }
  dog_payload["gps"] = {
    "last_seen": last_seen,
    "in_safe_zone": True,
  }
  dog_payload["garden"] = {
    "status": "active",
    "active_session": {
      "session_id": "garden-1",
      "start_time": started_at.isoformat(),
      "duration_minutes": 12,
    },
    "last_session": {
      "session_id": "garden-0",
      "start_time": started_at.isoformat(),
      "end_time": last_seen.isoformat(),
      "duration_minutes": 10,
    },
    "stats": {"last_garden_visit": last_seen.isoformat()},
  }

  walk_sensor = PawControlWalkInProgressBinarySensor(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  walk_attrs = walk_sensor.extra_state_attributes
  assert walk_attrs["started_at"] == started_at.isoformat()
  assert walk_attrs["duration_minutes"] == 15.0
  assert walk_attrs["last_seen"] == last_seen.isoformat()

  safe_zone_sensor = PawControlInSafeZoneBinarySensor(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  safe_zone_attrs = safe_zone_sensor.extra_state_attributes
  assert safe_zone_attrs["last_seen"] == last_seen.isoformat()

  garden_sensor = PawControlGardenTimeTodaySensor(
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  garden_attrs = garden_sensor.extra_state_attributes
  assert garden_attrs["started_at"] == started_at.isoformat()
  assert garden_attrs["duration_minutes"] == 12.0
  assert garden_attrs["last_seen"] == last_seen.isoformat()
