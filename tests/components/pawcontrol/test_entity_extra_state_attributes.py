from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import json
from typing import cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.binary_sensor import PawControlOnlineBinarySensor
from custom_components.pawcontrol.button import PawControlTestNotificationButton
from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.date import PawControlBirthdateDate
from custom_components.pawcontrol.datetime import PawControlBirthdateDateTime
from custom_components.pawcontrol.device_tracker import PawControlGPSTracker
from custom_components.pawcontrol.missing_sensors import (
  PawControlActivityLevelSensor,
  PawControlLastFeedingHoursSensor,
)
from custom_components.pawcontrol.number import PawControlDogWeightNumber
from custom_components.pawcontrol.select import PawControlDogSizeSelect
from custom_components.pawcontrol.sensor import PawControlDogStatusSensor
from custom_components.pawcontrol.switch import PawControlMainPowerSwitch
from custom_components.pawcontrol.text import PawControlDogNotesText
from custom_components.pawcontrol.types import (
  CoordinatorDogData,
  JSONMutableMapping,
  PawControlConfigEntry,
)


@dataclass
class _DummyEntry:
  entry_id: str  # noqa: E111


class _DummyCoordinator:
  """Coordinator double for extra attribute normalisation tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.data: dict[str, CoordinatorDogData] = {}
    self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
    self.last_update_success = True
    self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
    self.runtime_managers = None

  def async_add_listener(  # noqa: E111
    self, _callback
  ):  # pragma: no cover - protocol stub
    return lambda: None

  async def async_request_refresh(  # noqa: E111
    self,
  ) -> None:  # pragma: no cover - protocol stub
    return None

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:  # noqa: E111
    return self.data.get(dog_id)

  def get_enabled_modules(self, _dog_id: str) -> frozenset[str]:  # noqa: E111
    return frozenset()

  @property  # noqa: E111
  def available(self) -> bool:  # pragma: no cover - compatibility helper  # noqa: E111
    return True


@dataclass
class _DummyPayload:
  token: str  # noqa: E111
  count: int  # noqa: E111
  moment: datetime  # noqa: E111
  duration: timedelta  # noqa: E111


def _make_coordinator() -> _DummyCoordinator:
  coordinator = _DummyCoordinator()  # noqa: E111
  coordinator.data["dog-1"] = cast(  # noqa: E111
    CoordinatorDogData,
    {
      "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
      "status": "online",
      "last_update": datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
    },
  )
  return coordinator  # noqa: E111


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
      lambda coordinator: PawControlOnlineBinarySensor(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {
          "payload": _DummyPayload(
            token="ok",
            count=5,
            moment=datetime(2024, 2, 6, tzinfo=UTC),
            duration=timedelta(seconds=90),
          ),
        },
      ),
      "payload",
      dict,
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
    (
      lambda coordinator: PawControlMainPowerSwitch(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {
          "payload": _DummyPayload(
            token="ok",
            count=3,
            moment=datetime(2024, 2, 6, tzinfo=UTC),
            duration=timedelta(seconds=45),
          ),
        },
      ),
      "payload",
      dict,
    ),
    (
      lambda coordinator: PawControlGPSTracker(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"last_route_update": datetime(2024, 2, 6, tzinfo=UTC)},
      ),
      "last_route_update",
      str,
    ),
    (
      lambda coordinator: PawControlActivityLevelSensor(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity._attr_extra_state_attributes.update(
        {"duration": timedelta(minutes=12)},
      ),
      "duration",
      str,
    ),
    (
      lambda coordinator: PawControlLastFeedingHoursSensor(
        cast(PawControlCoordinator, coordinator),
        "dog-1",
        "Buddy",
      ),
      lambda entity: entity.coordinator.data["dog-1"].update(
        {
          "feeding": {
            "last_feeding": datetime(2024, 2, 7, tzinfo=UTC),
            "total_feedings_today": 2,
            "config": {"meals_per_day": 2},
          },
        },
      ),
      "last_feeding_time",
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
  """Ensure extra state attributes stay JSON serialisable."""  # noqa: E111

  coordinator = _make_coordinator()  # noqa: E111
  entity = factory(coordinator)  # noqa: E111
  entity.hass = hass  # noqa: E111
  mutator(entity)  # noqa: E111

  attrs = cast(JSONMutableMapping, entity.extra_state_attributes)  # noqa: E111

  assert isinstance(attrs, dict)  # noqa: E111
  attrs["mutation_check"] = "ok"  # noqa: E111
  json.dumps(attrs)  # noqa: E111
  assert isinstance(attrs[expected_key], expected_type)  # noqa: E111
  if expected_key == "payload":  # noqa: E111
    payload = cast(dict[str, object], attrs[expected_key])
    assert isinstance(payload["moment"], str)
    assert isinstance(payload["duration"], str)
