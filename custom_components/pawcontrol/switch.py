"""Switch platform for PawControl."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import PawControlCoordinator
from .entity import PawControlDogEntityBase
from .runtime_data import get_runtime_data
from .types import (
  DOG_ID_FIELD,
  DOG_NAME_FIELD,
  PawControlConfigEntry,
)


async def async_setup_entry(
  hass: HomeAssistant,
  entry: PawControlConfigEntry,
  async_add_entities: AddEntitiesCallback,
) -> None:
  """Set up PawControl switch platform."""
  runtime_data = get_runtime_data(hass, entry)
  if not runtime_data:
    return

  entities: list[SwitchEntity] = []
  for dog in runtime_data.dogs:
    dog_id = dog[DOG_ID_FIELD]
    dog_name = dog[DOG_NAME_FIELD]

    entities.append(
      PawControlMainPowerSwitch(runtime_data.coordinator, dog_id, dog_name),
    )
    entities.append(
      PawControlDoNotDisturbSwitch(runtime_data.coordinator, dog_id, dog_name),
    )
    entities.append(
      PawControlVisitorModeSwitch(runtime_data.coordinator, dog_id, dog_name),
    )

  async_add_entities(entities)


class PawControlSwitchBase(PawControlDogEntityBase, SwitchEntity):
  """Base class for PawControl switches."""

  _attr_has_entity_name = True

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
    switch_type: str,
    icon: str,
    device_class: SwitchDeviceClass | None = None,
    entity_category: EntityCategory | None = None,
  ) -> None:
    super().__init__(coordinator, dog_id, dog_name)
    self._switch_type = switch_type
    self._attr_unique_id = f"pawcontrol_{dog_id}_{switch_type}"
    self._attr_translation_key = switch_type
    self._attr_icon = icon
    self._attr_device_class = device_class
    self._attr_entity_category = entity_category

  @property
  def is_on(self) -> bool:
    """Return true if switch is on."""
    return self._get_is_on()

  def _get_is_on(self) -> bool:
    """Override in subclasses."""
    return False

  async def async_turn_on(self, **kwargs: Any) -> None:
    """Turn the switch on."""
    await self._async_set_state(True)
    self.async_write_ha_state()

  async def async_turn_off(self, **kwargs: Any) -> None:
    """Turn the switch off."""
    await self._async_set_state(False)
    self.async_write_ha_state()

  async def _async_set_state(self, state: bool) -> None:
    """Override in subclasses."""
    return


class PawControlMainPowerSwitch(PawControlSwitchBase):
  """Main power switch."""

  def __init__(
    self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
  ) -> None:
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "main_power",
      icon="mdi:power",
      device_class=SwitchDeviceClass.SWITCH,
    )

  def _get_is_on(self) -> bool:
    data = self._get_dog_data()
    return data.get("power_state", True) if data else True

  async def _async_set_state(self, state: bool) -> None:
    return


class PawControlDoNotDisturbSwitch(PawControlSwitchBase):
  """DND switch."""

  def __init__(
    self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
  ) -> None:
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "do_not_disturb",
      icon="mdi:sleep",
    )

  def _get_is_on(self) -> bool:
    data = self._get_dog_data()
    return data.get("dnd_enabled", False) if data else False


class PawControlVisitorModeSwitch(PawControlSwitchBase):
  """Visitor mode switch."""

  def __init__(
    self, coordinator: PawControlCoordinator, dog_id: str, dog_name: str
  ) -> None:
    super().__init__(
      coordinator,
      dog_id,
      dog_name,
      "visitor_mode",
      icon="mdi:account-group",
    )

  def _get_is_on(self) -> bool:
    data = self._get_dog_data()
    return data.get("visitor_mode_active", False) if data else False
