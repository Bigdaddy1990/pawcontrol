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
  entry_id: str


class _DummyCoordinator:
  """Minimal coordinator double for entity attribute tests."""

  def __init__(self) -> None:
    self.data: dict[str, CoordinatorDogData] = {}
    self.config_entry = cast(PawControlConfigEntry, _DummyEntry("entry"))
    self.last_update_success = True
    self.runtime_managers = None

  def async_add_listener(self, _callback):  # pragma: no cover - protocol stub
    return lambda: None

  async def async_request_refresh(self) -> None:  # pragma: no cover - stub
    return None

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
    return self.data.get(dog_id)

  def get_enabled_modules(self, dog_id: str) -> frozenset[str]:  # pragma: no cover
    return frozenset()

  @property
  def available(self) -> bool:  # pragma: no cover - compatibility helper
    return True


@dataclass
class _ComplexPayload:
  label: str
  duration: timedelta


class _AttributeEntity(PawControlDogEntityBase):
  """Expose extra attributes for normalization checks."""

  def __init__(
    self,
    coordinator: PawControlCoordinator,
    dog_id: str,
    dog_name: str,
  ) -> None:
    super().__init__(coordinator, dog_id, dog_name)
    self._attr_unique_id = f"pawcontrol_{dog_id}_attributes"

  @property
  def extra_state_attributes(self):
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
  """Ensure entity attributes are normalized into JSON-serialisable values."""

  coordinator = _DummyCoordinator()
  entity = _AttributeEntity(
    cast(PawControlCoordinator, coordinator),
    "dog-1",
    "Buddy",
  )
  entity.hass = hass

  attrs = entity.extra_state_attributes

  assert attrs["as_of"] == "2024-05-01T12:00:00+00:00"
  assert attrs["delta"] == "0:15:00"
  assert attrs["payload"] == {"label": "snapshot", "duration": "0:05:00"}
  assert set(cast(list[int], attrs["values"])) == {1, 2}


@pytest.mark.asyncio
async def test_garden_sensor_attributes_normalise_datetimes(hass) -> None:
  """Ensure garden attributes normalise datetime values."""

  coordinator = _DummyCoordinator()
  coordinator.data["dog-1"] = cast(
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

  entity = PawControlGardenTimeTodaySensor(
    cast(PawControlCoordinator, coordinator),
    "dog-1",
    "Buddy",
  )
  entity.hass = hass

  attrs = entity.extra_state_attributes

  assert attrs["started_at"] == "2024-05-01T08:30:00+00:00"
  assert attrs["last_seen"] == "2024-05-01T09:00:00+00:00"
