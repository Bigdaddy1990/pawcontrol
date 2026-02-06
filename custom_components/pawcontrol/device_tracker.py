"""Device tracker for PawControl."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PawControlCoordinator
from .entity import PawControlEntity
from .runtime_data import get_runtime_data
from .types import (
  DOG_GPS_CONFIG_FIELD,
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  PawControlConfigEntry,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up device tracker."""
  runtime_data = get_runtime_data(hass, entry)
  if not runtime_data:
    return

  entities: list[PawControlDeviceTracker] = []
  for dog in runtime_data.dogs:
    if dog.get(DOG_GPS_CONFIG_FIELD):
      entities.append(
        PawControlDeviceTracker(
          runtime_data.coordinator,
          dog[DOG_ID_FIELD],
          dog[DOG_NAME_FIELD],
        ),
      )

  async_add_entities(entities)


class PawControlDeviceTracker(PawControlEntity, TrackerEntity):
  """PawControl GPS Tracker."""

  _attr_icon = "mdi:dog-side"
  _attr_translation_key = "dog_tracker"

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    super().__init__(coordinator, dog_id, dog_name)
    self._attr_unique_id = f"pawcontrol_{dog_id}_tracker"

  @property
  def source_type(self) -> SourceType:
    """Return the source type."""
    return SourceType.GPS

  @property
  def latitude(self) -> float | None:
    """Return latitude value of the device."""
    data = self._get_gps_data()
    return data.get("latitude")

  @property
  def longitude(self) -> float | None:
    """Return longitude value of the device."""
    data = self._get_gps_data()
    return data.get("longitude")

  @property
  def battery_level(self) -> int | None:
    """Return battery value of the device."""
    data = self._get_gps_data()
    battery = data.get("battery_level", data.get("battery"))
    if battery is None:
      return None
    try:
      return int(battery)
    except (TypeError, ValueError):
      return None

  @property
  def location_accuracy(self) -> int | None:
    """Return GPS accuracy of the device."""
    data = self._get_gps_data()
    accuracy = data.get("accuracy")
    if accuracy is None:
      return None
    try:
      return int(accuracy)
    except (TypeError, ValueError):
      return None

  @property
  def extra_state_attributes(self) -> dict[str, Any]:
    """Return device state attributes."""
    attrs = dict(super().extra_state_attributes)
    gps_data = self._get_gps_data()

    if last_update := gps_data.get("last_push"):
      attrs["last_push"] = last_update

    if speed := gps_data.get("speed"):
      attrs["speed"] = speed

    return attrs

  def _get_gps_data(self) -> dict[str, Any]:
    """Return GPS module data for the dog."""
    if hasattr(self.coordinator, "get_module_data"):
      gps_data = self.coordinator.get_module_data(self._dog_id, "gps")
    else:
      dog_data = self.coordinator.get_dog_data(self._dog_id) or {}
      gps_data = dog_data.get("gps", {})

    return gps_data if isinstance(gps_data, dict) else dict(gps_data)
