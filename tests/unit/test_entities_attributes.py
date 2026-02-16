from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.sensor import PawControlGardenTimeTodaySensor
from custom_components.pawcontrol.types import CoordinatorDogData, PawControlConfigEntry


@dataclass
class _DummyEntry:
  entry_id: str  # noqa: E111


class _DummyCoordinator:
  """Minimal coordinator double for entity attribute tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.data: dict[str, CoordinatorDogData] = {}
    self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
    self.last_update_success = True
    self.runtime_managers = None

  def async_add_listener(
    self, _callback
  ):  # pragma: no cover - protocol stub  # noqa: E111
    return lambda: None

  async def async_request_refresh(
    self,
  ) -> None:  # pragma: no cover - stub  # noqa: E111
    return None

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:  # noqa: E111
    return self.data.get(dog_id)

  def get_enabled_modules(
    self, dog_id: str
  ) -> frozenset[str]:  # pragma: no cover  # noqa: E111
    return frozenset()

  @property  # noqa: E111
  def available(self) -> bool:  # pragma: no cover - compatibility helper  # noqa: E111
    return True


@dataclass
class _ComplexPayload:
  label: str  # noqa: E111
  duration: timedelta  # noqa: E111


class _AttributeEntity(PawControlDogEntityBase):
  """Expose extra attributes for normalization checks."""  # noqa: E111

  def __init__(  # noqa: E111
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    super().__init__(coordinator, dog_id, dog_name)
    self._attr_unique_id = f"pawcontrol_{dog_id}_attributes"

  @property  # noqa: E111
  def extra_state_attributes(self):  # noqa: E111
    payload = _ComplexPayload("snapshot", timedelta(minutes=5))
    attrs = self._build_base_state_attributes(
      {
        "as_of": datetime(2024, 5, 1, 12, 0, tzinfo=UTC),
        "delta": timedelta(minutes=15),
        "payload": payload,
        "values": {1, 2},
      },
    )
    return self._finalize_entity_attributes(attrs)


@pytest.mark.asyncio
async def test_entity_attributes_normalise_complex_types(hass) -> None:
  """Ensure entity attributes are normalized into JSON-serialisable values."""  # noqa: E111

  coordinator = _DummyCoordinator()  # noqa: E111
  entity = _AttributeEntity(  # noqa: E111
    cast(PawControlCoordinator, coordinator),
    "dog-1",
    "Buddy",
  )
  entity.hass = hass  # noqa: E111

  attrs = entity.extra_state_attributes  # noqa: E111

  assert attrs["as_of"] == "2024-05-01T12:00:00+00:00"  # noqa: E111
  assert attrs["delta"] == "0:15:00"  # noqa: E111
  assert attrs["payload"] == {"label": "snapshot", "duration": "0:05:00"}  # noqa: E111
  assert set(cast(list[int], attrs["values"])) == {1, 2}  # noqa: E111


@pytest.mark.asyncio
async def test_garden_sensor_attributes_normalise_datetimes(hass) -> None:
  """Ensure garden attributes normalise datetime values."""  # noqa: E111

  coordinator = _DummyCoordinator()  # noqa: E111
  coordinator.data["dog-1"] = cast(  # noqa: E111
    CoordinatorDogData,
    {
      "dog_info": {"dog_id": "dog-1", "dog_name": "Buddy"},
      "status": "online",
      "last_update": datetime(2024, 5, 1, 12, 0, tzinfo=UTC).isoformat(),
      "garden": {
        "status": "active",
        "sessions_today": 1,
        "last_session": {
          "start_time": datetime(2024, 5, 1, 8, 30, tzinfo=UTC),
          "end_time": datetime(2024, 5, 1, 9, 0, tzinfo=UTC),
          "duration_minutes": 30,
        },
      },
    },
  )

  entity = PawControlGardenTimeTodaySensor(  # noqa: E111
    cast(PawControlCoordinator, coordinator),
    "dog-1",
    "Buddy",
  )
  entity.hass = hass  # noqa: E111

  attrs = entity.extra_state_attributes  # noqa: E111

  assert attrs["started_at"] == "2024-05-01T08:30:00+00:00"  # noqa: E111
  assert attrs["last_seen"] == "2024-05-01T09:00:00+00:00"  # noqa: E111
