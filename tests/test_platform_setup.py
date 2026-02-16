"""Unit tests for entity platform setup flows."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import importlib
import json
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
  entity_factory = EntityFactory(mock_coordinator)  # noqa: E111
  return PawControlRuntimeData(  # noqa: E111
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
  module = importlib.import_module(module_path)  # noqa: E111
  async_add_entities = AsyncMock()  # noqa: E111

  await module.async_setup_entry(hass, mock_config_entry, async_add_entities)  # noqa: E111

  async_add_entities.assert_not_called()  # noqa: E111


@pytest.mark.asyncio
@pytest.mark.parametrize("module_path", PLATFORM_MODULES)
async def test_platform_setup_adds_entities_when_configured(
  hass,
  mock_config_entry,
  runtime_data: PawControlRuntimeData,
  module_path: str,
) -> None:
  store_runtime_data(hass, mock_config_entry, runtime_data)  # noqa: E111
  module = importlib.import_module(module_path)  # noqa: E111
  async_add_entities = AsyncMock()  # noqa: E111

  await module.async_setup_entry(hass, mock_config_entry, async_add_entities)  # noqa: E111

  assert async_add_entities.called  # noqa: E111
  args, _ = async_add_entities.call_args  # noqa: E111
  added_entities: Iterable[Any] = args[0]  # noqa: E111
  assert list(added_entities)  # noqa: E111


def test_walk_and_garden_attributes_are_standardised(mock_coordinator) -> None:
  from custom_components.pawcontrol.binary_sensor import (  # noqa: E111
    PawControlInSafeZoneBinarySensor,
    PawControlWalkInProgressBinarySensor,
  )
  from custom_components.pawcontrol.sensor import PawControlGardenTimeTodaySensor

  started_at = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)  # noqa: E111
  last_seen = datetime(2024, 1, 1, 12, 45, tzinfo=UTC)  # noqa: E111

  dog_payload = mock_coordinator._data["test_dog"]  # noqa: E111
  dog_payload["walk"] = {  # noqa: E111
    "walk_in_progress": True,
    "current_walk_start": started_at,
    "current_walk_duration": 15,
    "current_walk_distance": 1200,
  }
  dog_payload["gps"] = {  # noqa: E111
    "last_seen": last_seen,
    "in_safe_zone": True,
  }
  dog_payload["garden"] = {  # noqa: E111
    "status": "active",
    "active_session": {
      "session_id": "garden-1",
      "start_time": started_at,
      "duration_minutes": 12,
    },
    "last_session": {
      "session_id": "garden-0",
      "start_time": started_at,
      "end_time": last_seen,
      "duration_minutes": 10,
    },
    "stats": {"last_garden_visit": last_seen},
  }

  walk_sensor = PawControlWalkInProgressBinarySensor(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  walk_attrs = walk_sensor.extra_state_attributes  # noqa: E111
  assert walk_attrs["started_at"] == started_at.isoformat()  # noqa: E111
  assert walk_attrs["duration_minutes"] == 15.0  # noqa: E111
  assert walk_attrs["last_seen"] == last_seen.isoformat()  # noqa: E111

  safe_zone_sensor = PawControlInSafeZoneBinarySensor(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  safe_zone_attrs = safe_zone_sensor.extra_state_attributes  # noqa: E111
  assert safe_zone_attrs["last_seen"] == last_seen.isoformat()  # noqa: E111

  garden_sensor = PawControlGardenTimeTodaySensor(  # noqa: E111
    mock_coordinator,
    "test_dog",
    "Buddy",
  )
  garden_attrs = garden_sensor.extra_state_attributes  # noqa: E111
  assert garden_attrs["started_at"] == started_at.isoformat()  # noqa: E111
  assert garden_attrs["duration_minutes"] == 12.0  # noqa: E111
  assert garden_attrs["last_seen"] == last_seen.isoformat()  # noqa: E111
