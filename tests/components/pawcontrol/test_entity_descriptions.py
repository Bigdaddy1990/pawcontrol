from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

pytest.importorskip("homeassistant")

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.pawcontrol.binary_sensor import PawControlOnlineBinarySensor
from custom_components.pawcontrol.button import PawControlResetDailyStatsButton
from custom_components.pawcontrol.compat import MASS_KILOGRAMS
from custom_components.pawcontrol.date import PawControlBirthdateDate
from custom_components.pawcontrol.number import PawControlDogWeightNumber
from custom_components.pawcontrol.select import PawControlDogSizeSelect
from custom_components.pawcontrol.sensor import PawControlWeightSensor
from custom_components.pawcontrol.switch import PawControlMainPowerSwitch
from custom_components.pawcontrol.text import PawControlDogNotesText
from custom_components.pawcontrol.types import PawControlConfigEntry


@dataclass
class _DummyEntry:
  entry_id: str  # noqa: E111


class _DummyCoordinator:
  """Coordinator double for entity description tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.data: dict[str, dict[str, object]] = {}
    self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
    self.last_update_success = True
    self.last_update_success_time = None
    self.runtime_managers = None

  def async_add_listener(
    self, _callback
  ):  # pragma: no cover - protocol stub  # noqa: E111
    return lambda: None

  async def async_request_refresh(
    self,
  ) -> None:  # pragma: no cover - protocol stub  # noqa: E111
    return None

  def get_dog_data(self, dog_id: str):  # noqa: E111
    return self.data.get(dog_id)

  def get_enabled_modules(self, _dog_id: str):  # noqa: E111
    return frozenset()

  @property  # noqa: E111
  def available(self) -> bool:  # pragma: no cover - compatibility helper  # noqa: E111
    return True


def _make_coordinator() -> _DummyCoordinator:
  return _DummyCoordinator()  # noqa: E111


def test_entity_descriptions_match_sensor_metadata() -> None:
  coordinator = _make_coordinator()  # noqa: E111
  entity = PawControlWeightSensor(coordinator, "dog-1", "Buddy")  # noqa: E111

  description = entity.entity_description  # noqa: E111

  assert description is not None  # noqa: E111
  assert description.translation_key == "weight"  # noqa: E111
  assert description.device_class == SensorDeviceClass.WEIGHT  # noqa: E111
  assert description.state_class == SensorStateClass.MEASUREMENT  # noqa: E111
  assert description.native_unit_of_measurement == MASS_KILOGRAMS  # noqa: E111
  assert description.suggested_display_precision == 1  # noqa: E111
  assert entity.has_entity_name is True  # noqa: E111


def test_entity_descriptions_cover_binary_sensor() -> None:
  coordinator = _make_coordinator()  # noqa: E111
  entity = PawControlOnlineBinarySensor(coordinator, "dog-1", "Buddy")  # noqa: E111

  description = entity.entity_description  # noqa: E111

  assert description is not None  # noqa: E111
  assert description.translation_key == "online"  # noqa: E111
  assert description.device_class == BinarySensorDeviceClass.CONNECTIVITY  # noqa: E111


def test_entity_descriptions_cover_switch_button_number() -> None:
  coordinator = _make_coordinator()  # noqa: E111

  switch = PawControlMainPowerSwitch(coordinator, "dog-1", "Buddy")  # noqa: E111
  switch_description = switch.entity_description  # noqa: E111

  assert switch_description is not None  # noqa: E111
  assert switch_description.translation_key == "main_power"  # noqa: E111
  assert switch_description.device_class == SwitchDeviceClass.SWITCH  # noqa: E111

  button = PawControlResetDailyStatsButton(coordinator, "dog-1", "Buddy")  # noqa: E111
  button_description = button.entity_description  # noqa: E111

  assert button_description is not None  # noqa: E111
  assert button_description.translation_key == "reset_daily_stats"  # noqa: E111
  assert button_description.device_class is not None  # noqa: E111

  number = PawControlDogWeightNumber(coordinator, "dog-1", "Buddy")  # noqa: E111
  number_description = number.entity_description  # noqa: E111

  assert number_description is not None  # noqa: E111
  assert number_description.translation_key == "weight"  # noqa: E111
  assert number_description.device_class == NumberDeviceClass.WEIGHT  # noqa: E111


def test_entity_descriptions_cover_select_text_date() -> None:
  coordinator = _make_coordinator()  # noqa: E111

  select = PawControlDogSizeSelect(coordinator, "dog-1", "Buddy")  # noqa: E111
  select_description = select.entity_description  # noqa: E111

  assert select_description is not None  # noqa: E111
  assert select_description.translation_key == "size"  # noqa: E111
  assert select_description.entity_category == EntityCategory.CONFIG  # noqa: E111

  text = PawControlDogNotesText(coordinator, "dog-1", "Buddy")  # noqa: E111
  text_description = text.entity_description  # noqa: E111

  assert text_description is not None  # noqa: E111
  assert text_description.translation_key == "notes"  # noqa: E111

  date_entity = PawControlBirthdateDate(coordinator, "dog-1", "Buddy")  # noqa: E111
  date_description = date_entity.entity_description  # noqa: E111

  assert date_description is not None  # noqa: E111
  assert date_description.translation_key == "birthdate"  # noqa: E111
