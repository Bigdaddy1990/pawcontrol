from __future__ import annotations
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock
from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import number as number_component

# The lightweight Home Assistant test harness used in this repository does not
# always export ``ATTR_VALUE`` from ``homeassistant.const``. Use the canonical
# service call key instead.
ATTR_VALUE = "value"

# ``ATTR_ENTITY_ID`` is not available in all Home Assistant test harness
# versions used by this repo.
ATTR_ENTITY_ID = "entity_id"

from custom_components.pawcontrol.const import (
  CONF_GPS_UPDATE_INTERVAL,
  CONF_MEALS_PER_DAY,
)
from custom_components.pawcontrol.data_manager import PawControlDataManager
from custom_components.pawcontrol.entity_factory import EntityFactory
from custom_components.pawcontrol.number import (
  PawControlGPSUpdateIntervalNumber,
  PawControlMealsPerDayNumber,
)
from custom_components.pawcontrol.runtime_data import store_runtime_data
from custom_components.pawcontrol.types import (
  CoordinatorRuntimeManagers,
  DOG_FEEDING_CONFIG_FIELD,
  DOG_GPS_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DogConfigData,
  JSONMutableMapping,
  JSONValue,
  PawControlRuntimeData,
)


class _FakeDataManager:
  def __init__(self, configs: dict[str, DogConfigData]) -> None:
    self.configs = configs

  async def async_update_dog_data(
    self,
    dog_id: str,
    updates: Mapping[str, JSONValue],
    *,
    persist: bool = True,
  ) -> bool:
    config = self.configs.setdefault(dog_id, {})
    for section, payload in updates.items():
      if isinstance(payload, Mapping):
        current = config.get(section)
        merged: JSONMutableMapping = (
          dict(current) if isinstance(current, Mapping) else {}
        )
        merged.update(dict(payload))
        config[section] = merged
      else:
        config[section] = payload
    return True


class _FakeFeedingManager:
  def __init__(self) -> None:
    self.async_update_config = AsyncMock()


class _FakeGPSManager:
  def __init__(self) -> None:
    self.async_configure_dog_gps = AsyncMock()


class _DummyCoordinator:
  def __init__(
    self,
    *,
    dog_id: str,
    dog_name: str,
    runtime_managers: CoordinatorRuntimeManagers,
  ) -> None:
    self.data: dict[str, JSONMutableMapping] = {
      dog_id: {
        "dog_info": {
          DOG_ID_FIELD: dog_id,
          DOG_NAME_FIELD: dog_name,
        },
      }
    }
    self.runtime_managers = runtime_managers
    self.last_update_success = True
    self.refreshed: list[str] = []

  def get_dog_data(self, dog_id: str) -> JSONMutableMapping | None:
    return self.data.get(dog_id)

  def get_dog_config(self, dog_id: str) -> DogConfigData | None:
    manager = self.runtime_managers.data_manager
    if manager is None:
      return None
    return manager.configs.get(dog_id)

  async def async_refresh_dog(self, dog_id: str) -> None:
    self.refreshed.append(dog_id)
    config = self.get_dog_config(dog_id) or {}
    dog_data = self.data.setdefault(dog_id, {})
    dog_data["config"] = dict(config)

  @property
  def available(self) -> bool:
    return True


def _configure_number_entity(entity: Any, hass: Any, entity_id: str) -> None:
  entity.hass = hass
  entity.entity_id = entity_id
  entity.async_write_ha_state = Mock()
  entity.native_min_value = entity._attr_native_min_value
  entity.native_max_value = entity._attr_native_max_value


async def _async_call_number_service(
  hass: Any,
  entity_id: str,
  value: float,
  *,
  entity_lookup: dict[str, Any],
) -> None:
  number_domain = getattr(number_component, "DOMAIN", "number")
  service_name = getattr(number_component, "SERVICE_SET_VALUE", "set_value")

  async def _async_call(
    domain: str,
    service: str,
    data: dict[str, Any] | None = None,
    *_,
    **__,
  ) -> None:
    if domain != number_domain or service != service_name:
      return
    payload = data or {}
    entity_target = entity_lookup[payload[ATTR_ENTITY_ID]]
    await entity_target.async_set_native_value(payload[ATTR_VALUE])

  hass.services.async_call = _async_call
  await hass.services.async_call(
    number_domain,
    service_name,
    {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
    blocking=True,
  )


@pytest.mark.asyncio
async def test_number_set_value_updates_feeding_config(
  hass: Any,
) -> None:
  dog_id = "dog-1"
  dog_name = "Buddy"
  data_manager = _FakeDataManager(
    {
      dog_id: {
        DOG_ID_FIELD: dog_id,
        DOG_NAME_FIELD: dog_name,
        DOG_FEEDING_CONFIG_FIELD: {CONF_MEALS_PER_DAY: 2},
      }
    },
  )
  feeding_manager = _FakeFeedingManager()
  runtime_managers = CoordinatorRuntimeManagers(
    data_manager=data_manager,
    feeding_manager=feeding_manager,
  )
  coordinator = _DummyCoordinator(
    dog_id=dog_id,
    dog_name=dog_name,
    runtime_managers=runtime_managers,
  )
  entity = PawControlMealsPerDayNumber(coordinator, dog_id, dog_name)
  _configure_number_entity(entity, hass, "number.pawcontrol_meals_per_day")

  await _async_call_number_service(
    hass,
    entity.entity_id,
    3,
    entity_lookup={entity.entity_id: entity},
  )

  assert data_manager.configs[dog_id][DOG_FEEDING_CONFIG_FIELD][CONF_MEALS_PER_DAY] == 3
  feeding_manager.async_update_config.assert_awaited_once()
  assert coordinator.refreshed == [dog_id]
  assert (
    coordinator.data[dog_id]["config"][DOG_FEEDING_CONFIG_FIELD][CONF_MEALS_PER_DAY]
    == 3
  )


@pytest.mark.asyncio
async def test_number_set_value_updates_gps_config(
  hass: Any,
) -> None:
  dog_id = "dog-2"
  dog_name = "Juno"
  data_manager = _FakeDataManager(
    {
      dog_id: {
        DOG_ID_FIELD: dog_id,
        DOG_NAME_FIELD: dog_name,
        DOG_GPS_CONFIG_FIELD: {CONF_GPS_UPDATE_INTERVAL: 60},
      }
    },
  )
  gps_manager = _FakeGPSManager()
  runtime_managers = CoordinatorRuntimeManagers(
    data_manager=data_manager,
    gps_geofence_manager=gps_manager,
  )
  coordinator = _DummyCoordinator(
    dog_id=dog_id,
    dog_name=dog_name,
    runtime_managers=runtime_managers,
  )
  entity = PawControlGPSUpdateIntervalNumber(coordinator, dog_id, dog_name)
  _configure_number_entity(entity, hass, "number.pawcontrol_gps_update_interval")

  await _async_call_number_service(
    hass,
    entity.entity_id,
    120,
    entity_lookup={entity.entity_id: entity},
  )

  assert (
    data_manager.configs[dog_id][DOG_GPS_CONFIG_FIELD][CONF_GPS_UPDATE_INTERVAL] == 120
  )
  gps_manager.async_configure_dog_gps.assert_awaited_once()
  args, _kwargs = gps_manager.async_configure_dog_gps.await_args
  assert args[0] == dog_id
  assert args[1]["update_interval_seconds"] == 120
  assert coordinator.refreshed == [dog_id]
  assert (
    coordinator.data[dog_id]["config"][DOG_GPS_CONFIG_FIELD][CONF_GPS_UPDATE_INTERVAL]
    == 120
  )


@pytest.mark.asyncio
async def test_number_update_flows_through_runtime_managers(
  mock_hass,
  mock_config_entry,
  mock_coordinator,
  tmp_path,
) -> None:
  mock_hass.config.config_dir = str(tmp_path)
  mock_coordinator.async_refresh_dog = AsyncMock()
  mock_client = Mock()
  mock_coordinator.client = mock_client

  data_manager = PawControlDataManager(
    mock_hass,
    coordinator=mock_coordinator,
    dogs_config=mock_config_entry.data["dogs"],
  )
  await data_manager.async_initialize()

  feeding_manager = MagicMock()
  feeding_manager.async_update_config = AsyncMock()

  runtime_data = PawControlRuntimeData(
    coordinator=mock_coordinator,
    data_manager=data_manager,
    notification_manager=MagicMock(),
    feeding_manager=feeding_manager,
    walk_manager=MagicMock(),
    entity_factory=EntityFactory(mock_coordinator),
    entity_profile="standard",
    dogs=mock_config_entry.data["dogs"],
  )
  store_runtime_data(mock_hass, mock_config_entry, runtime_data)

  entity = PawControlMealsPerDayNumber(mock_coordinator, "test_dog", "Buddy")
  _configure_number_entity(entity, mock_hass, "number.pawcontrol_meals_per_day")

  await _async_call_number_service(
    mock_hass,
    entity.entity_id,
    4,
    entity_lookup={entity.entity_id: entity},
  )

  assert (
    data_manager._dogs_config["test_dog"][DOG_FEEDING_CONFIG_FIELD][CONF_MEALS_PER_DAY]
    == 4
  )
  feeding_manager.async_update_config.assert_awaited_once()
  mock_coordinator.async_refresh_dog.assert_awaited_once_with("test_dog")
  assert mock_client.mock_calls == []
