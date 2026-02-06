"""Base entity classes for PawControl integration.

Standard Home Assistant entity implementation without custom memory management.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
  ATTR_DOG_ID,
  ATTR_DOG_NAME,
  DEFAULT_MODEL,
  DEFAULT_SW_VERSION,
  MANUFACTURER,
)
from .coordinator import PawControlCoordinator
from .types import CoordinatorDogData, DeviceLinkDetails, JSONMutableMapping
from .utils import PawControlDeviceLinkMixin

_LOGGER = logging.getLogger(__name__)


class PawControlEntity(
  PawControlDeviceLinkMixin,
  CoordinatorEntity[PawControlCoordinator],
  RestoreEntity,
):
  """Base entity class for PawControl."""

  _attr_has_entity_name = True
  _attr_should_poll = False

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    entity_type: str,
    *,
    unique_id_suffix: str | None = None,
    name_suffix: str | None = None,
    device_class: str | None = None,
    entity_category: EntityCategory | None = None,
    icon: str | None = None,
  ) -> None:
    """Initialize the entity."""
    super().__init__(coordinator)
    self._dog_id = dog_id
    self._dog_name = dog_name
    self._entity_type = entity_type

    unique_id_parts = ["pawcontrol", dog_id, entity_type]
    if unique_id_suffix:
      unique_id_parts.append(unique_id_suffix)
    self._attr_unique_id = "_".join(unique_id_parts)

    name_parts = [dog_name]
    if name_suffix:
      name_parts.append(name_suffix)
    else:
      name_parts.append(entity_type.replace("_", " ").title())
    self._attr_name = " ".join(name_parts)

    self._attr_device_class = device_class
    self._attr_entity_category = entity_category
    self._attr_icon = icon
    self._attr_suggested_area = f"Pet Area - {dog_name}"

    self._set_device_link_info(
      model=DEFAULT_MODEL,
      sw_version=DEFAULT_SW_VERSION,
      configuration_url=f"https://github.com/BigDaddy1990/pawcontrol/wiki/dog-{dog_id}",
      manufacturer=MANUFACTURER,
    )

  @property
  def available(self) -> bool:
    """Return if entity is available."""
    if not self.coordinator.last_update_success:
      return False

    dog_data = self._get_dog_data()
    if not dog_data:
      return False

    return dog_data.get("status") != "missing"

  @property
  def extra_state_attributes(self) -> JSONMutableMapping:
    """Return entity specific state attributes."""
    attributes: dict[str, Any] = {
      ATTR_DOG_ID: self._dog_id,
      ATTR_DOG_NAME: self._dog_name,
      "entity_type": self._entity_type,
      "last_updated": dt_util.utcnow().isoformat(),
    }

    dog_data = self._get_dog_data()
    if dog_data:
      if status := dog_data.get("status"):
        attributes["status"] = status
      if last_update := dog_data.get("last_update"):
        attributes["data_last_update"] = last_update

    return cast(JSONMutableMapping, attributes)

  def _get_dog_data(self) -> CoordinatorDogData | None:
    """Get data for this dog from coordinator."""
    return self.coordinator.data.get(self._dog_id)

  def _get_module_data(self, module: str) -> Any:
    """Get module specific data."""
    dog_data = self._get_dog_data()
    if not dog_data:
      return {}
    return dog_data.get(module, {})

  def _device_link_details(self) -> DeviceLinkDetails:
    """Extend base device metadata."""
    info = cast(DeviceLinkDetails, super()._device_link_details())
    dog_data = self._get_dog_data()
    if (
      dog_data
      and (dog_info := dog_data.get("dog_info"))
      and (dog_breed := dog_info.get("dog_breed"))
    ):
      info["breed"] = dog_breed
    return info


class PawControlSensorEntity(PawControlEntity):
  """Base class for sensors."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    sensor_type: str,
    *,
    state_class: str | None = None,
    unit_of_measurement: str | None = None,
    **kwargs: Any,
  ) -> None:
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      f"sensor_{sensor_type}",
      unique_id_suffix=sensor_type,
      name_suffix=sensor_type.replace("_", " ").title(),
      **kwargs,
    )
    self._attr_state_class = state_class
    self._attr_native_unit_of_measurement = unit_of_measurement

  @property
  def native_value(self) -> Any:
    """Return the native value of the sensor."""
    return self._get_native_value()

  def _get_native_value(self) -> Any:
    """To be implemented by subclasses."""
    return None


class PawControlBinarySensorEntity(PawControlEntity):
  """Base class for binary sensors."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    sensor_type: str,
    *,
    icon_on: str | None = None,
    icon_off: str | None = None,
    **kwargs: Any,
  ) -> None:
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      f"binary_sensor_{sensor_type}",
      unique_id_suffix=sensor_type,
      name_suffix=sensor_type.replace("_", " ").title(),
      **kwargs,
    )
    self._icon_on = icon_on
    self._icon_off = icon_off

  @property
  def is_on(self) -> bool:
    """Return true if the binary sensor is on."""
    return self._get_is_on()

  @property
  def icon(self) -> str | None:
    """Return dynamic icon."""
    if self.is_on and self._icon_on:
      return self._icon_on
    if not self.is_on and self._icon_off:
      return self._icon_off
    return super().icon

  def _get_is_on(self) -> bool:
    """To be implemented by subclasses."""
    return False


OptimizedEntityBase = PawControlEntity
OptimizedSensorBase = PawControlSensorEntity
OptimizedBinarySensorBase = PawControlBinarySensorEntity
