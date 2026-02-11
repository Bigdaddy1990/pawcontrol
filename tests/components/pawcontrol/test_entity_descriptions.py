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
    entry_id: str


class _DummyCoordinator:
    """Coordinator double for entity description tests."""

    def __init__(self) -> None:
        self.data: dict[str, dict[str, object]] = {}
        self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
        self.last_update_success = True
        self.last_update_success_time = None
        self.runtime_managers = None

    def async_add_listener(self, _callback):  # pragma: no cover - protocol stub
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - protocol stub
        return None

    def get_dog_data(self, dog_id: str):
        return self.data.get(dog_id)

    def get_enabled_modules(self, _dog_id: str):
        return frozenset()

    @property
    def available(self) -> bool:  # pragma: no cover - compatibility helper
        return True


def _make_coordinator() -> _DummyCoordinator:
    return _DummyCoordinator()


def test_entity_descriptions_match_sensor_metadata() -> None:
    coordinator = _make_coordinator()
    entity = PawControlWeightSensor(coordinator, "dog-1", "Buddy")

    description = entity.entity_description

    assert description is not None
    assert description.translation_key == "weight"
    assert description.device_class == SensorDeviceClass.WEIGHT
    assert description.state_class == SensorStateClass.MEASUREMENT
    assert description.native_unit_of_measurement == MASS_KILOGRAMS
    assert description.suggested_display_precision == 1
    assert entity.has_entity_name is True


def test_entity_descriptions_cover_binary_sensor() -> None:
    coordinator = _make_coordinator()
    entity = PawControlOnlineBinarySensor(coordinator, "dog-1", "Buddy")

    description = entity.entity_description

    assert description is not None
    assert description.translation_key == "online"
    assert description.device_class == BinarySensorDeviceClass.CONNECTIVITY


def test_entity_descriptions_cover_switch_button_number() -> None:
    coordinator = _make_coordinator()

    switch = PawControlMainPowerSwitch(coordinator, "dog-1", "Buddy")
    switch_description = switch.entity_description

    assert switch_description is not None
    assert switch_description.translation_key == "main_power"
    assert switch_description.device_class == SwitchDeviceClass.SWITCH

    button = PawControlResetDailyStatsButton(coordinator, "dog-1", "Buddy")
    button_description = button.entity_description

    assert button_description is not None
    assert button_description.translation_key == "reset_daily_stats"
    assert button_description.device_class is not None

    number = PawControlDogWeightNumber(coordinator, "dog-1", "Buddy")
    number_description = number.entity_description

    assert number_description is not None
    assert number_description.translation_key == "weight"
    assert number_description.device_class == NumberDeviceClass.WEIGHT


def test_entity_descriptions_cover_select_text_date() -> None:
    coordinator = _make_coordinator()

    select = PawControlDogSizeSelect(coordinator, "dog-1", "Buddy")
    select_description = select.entity_description

    assert select_description is not None
    assert select_description.translation_key == "size"
    assert select_description.entity_category == EntityCategory.CONFIG

    text = PawControlDogNotesText(coordinator, "dog-1", "Buddy")
    text_description = text.entity_description

    assert text_description is not None
    assert text_description.translation_key == "notes"

    date_entity = PawControlBirthdateDate(coordinator, "dog-1", "Buddy")
    date_description = date_entity.entity_description

    assert date_description is not None
    assert date_description.translation_key == "birthdate"
