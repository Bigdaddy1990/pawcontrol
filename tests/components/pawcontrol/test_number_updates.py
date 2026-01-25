from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components import number as number_component
from homeassistant.const import ATTR_ENTITY_ID, ATTR_VALUE

from custom_components.pawcontrol.const import (
  CONF_GPS_UPDATE_INTERVAL,
  CONF_MEALS_PER_DAY,
)
from custom_components.pawcontrol.number import (
  PawControlGPSUpdateIntervalNumber,
  PawControlMealsPerDayNumber,
)
from custom_components.pawcontrol.types import (
  CoordinatorRuntimeManagers,
  DOG_FEEDING_CONFIG_FIELD,
  DOG_GPS_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  DogConfigData,
  JSONMutableMapping,
  JSONValue,
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
