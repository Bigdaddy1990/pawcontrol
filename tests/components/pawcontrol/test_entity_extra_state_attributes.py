from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable, cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.binary_sensor import PawControlOnlineBinarySensor
from custom_components.pawcontrol.button import PawControlTestNotificationButton
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.date import PawControlBirthdateDate
from custom_components.pawcontrol.datetime import PawControlBirthdateDateTime
from custom_components.pawcontrol.number import PawControlDogWeightNumber
from custom_components.pawcontrol.select import PawControlDogSizeSelect
from custom_components.pawcontrol.sensor import PawControlDogStatusSensor
from custom_components.pawcontrol.text import PawControlDogNotesText
from custom_components.pawcontrol.types import (
  CoordinatorDogData,
  JSONMutableMapping,
  PawControlConfigEntry,
)


@dataclass
class _DummyEntry:
  entry_id: str


class _DummyCoordinator:
  """Coordinator double for extra attribute normalisation tests."""

  def __init__(self) -> None:
    self.data: dict[str, CoordinatorDogData] = {}
    self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
    self.last_update_success = True
    self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
    self.runtime_managers = None

  def async_add_listener(self, _callback):  # pragma: no cover - protocol stub
    return lambda: None

  async def async_request_refresh(self) -> None:  # pragma: no cover - protocol stub
    return None

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
    return self.data.get(dog_id)

  def get_enabled_modules(self, _dog_id: str) -> frozenset[str]:
    return frozenset()

  @property
  def available(self) -> bool:  # pragma: no cover - compatibility helper
    return True


def _make_coordinator() -> _DummyCoordinator:
  coordinator = _DummyCoordinator()
  coordinator.data["dog-1"] = cast(
    CoordinatorDogData,
    {
      "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
      "status": "online",
      "last_update": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
    },
  )
  return coordinator


@pytest.mark.parametrize(
  ("factory", "mutator", "expected_key", "expected_type"),
  [
    (
      lambda coordinator: PawControlTestNotificationButton(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: setattr(
        entity,
        "_last_pressed",
        datetime(2024, 2, 1, tzinfo=UTC),
      ),
      "last_pressed",
      str,
    ),
    (
      lambda coordinator: PawControlDogNotesText(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: setattr(
        entity,
        "_last_updated",
        datetime(2024, 2, 2, tzinfo=UTC),
      ),
      "last_updated",
      str,
    ),
    (
      lambda coordinator: PawControlDogSizeSelect(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"non_serializable": {"small", "large"}},
      ),
      "non_serializable",
      list,
    ),
    (
      lambda coordinator: PawControlDogWeightNumber(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"duration": timedelta(seconds=30)},
      ),
      "duration",
      str,
    ),
    (
      lambda coordinator: PawControlDogStatusSensor(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"moment": datetime(2024, 2, 3, tzinfo=UTC)},
      ),
      "moment",
      str,
    ),
    (
      lambda coordinator: PawControlOnlineBinarySensor(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"flags": {1, 2}},
      ),
      "flags",
      list,
    ),
    (
      lambda coordinator: PawControlBirthdateDate(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"marker": date(2024, 2, 4)},
      ),
      "marker",
      str,
    ),
    (
      lambda coordinator: PawControlBirthdateDateTime(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"marker": datetime(2024, 2, 5, tzinfo=UTC)},
      ),
      "marker",
      str,
    ),
  ],
)
@pytest.mark.asyncio
async def test_extra_state_attributes_json_serialisable(
  hass,
  factory: Callable[[object], object],
  mutator: Callable[[object], None],
  expected_key: str,
  expected_type: type[object],
) -> None:
  """Ensure extra state attributes stay JSON serialisable."""

  coordinator = _make_coordinator()
  entity = factory(coordinator)
  entity.hass = hass
  mutator(entity)

  attrs = cast(JSONMutableMapping, entity.extra_state_attributes)

  assert isinstance(attrs, dict)
  json.dumps(attrs)
  assert isinstance(attrs[expected_key], expected_type)
