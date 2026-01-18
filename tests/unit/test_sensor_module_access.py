"""Tests for PawControl sensor module data access helpers."""

from __future__ import annotations

from typing import Any, cast

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.sensor import PawControlSensorBase
from custom_components.pawcontrol.types import (
  CoordinatorDogData,
  CoordinatorModuleLookupResult,
  CoordinatorModuleState,
)


class _CoordinatorStub:
  """Minimal coordinator stub exposing typed module accessors."""

  def __init__(self, payload: dict[str, CoordinatorDogData]) -> None:
    self.available = True
    self._data = payload
    self.last_update_success_time = None

  def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
    """Return coordinator dog payload for ``dog_id``."""

    return self._data.get(dog_id)

  def get_module_data(self, dog_id: str, module: str) -> CoordinatorModuleLookupResult:
    """Return module data for ``dog_id`` and ``module``."""

    dog_payload = self._data.get(dog_id, cast(CoordinatorDogData, {}))
    return cast(CoordinatorModuleLookupResult, dog_payload.get(module, {}))


class _DummySensor(PawControlSensorBase):
  """Concrete PawControl sensor used for module access tests."""

  def __init__(self, coordinator: _CoordinatorStub) -> None:
    super().__init__(
      coordinator=cast(PawControlCoordinator, coordinator),
      dog_id="alpha",
      dog_name="Alpha",
      sensor_type="dummy",
    )

  @property
  def native_value(self) -> int | None:
    """Return a static value; not relevant for module tests."""

    return 0


def _build_sensor(payload: dict[str, CoordinatorDogData]) -> _DummySensor:
  """Helper to instantiate a sensor against ``payload``."""

  coordinator = _CoordinatorStub(payload)
  return _DummySensor(coordinator)


def test_get_module_data_preserves_typed_payload() -> None:
  """Typed modules should pass through coordinator payloads unchanged."""

  sensor = _build_sensor(
    {
      "alpha": cast(
        CoordinatorDogData,
        {"gps": {"status": "active", "last_fix": "2025-01-01T12:00:00"}},
      )
    }
  )

  payload = sensor._get_module_data("gps")

  assert payload["status"] == "active"
  assert payload["last_fix"] == "2025-01-01T12:00:00"


def test_get_module_data_returns_empty_mapping_for_unknown_module() -> None:
  """Unknown modules should yield empty payloads."""

  sensor = _build_sensor({"alpha": cast(CoordinatorDogData, {})})

  payload = sensor._get_module_data("notifications")

  assert payload == {}


def test_get_module_data_filters_invalid_payload_types() -> None:
  """Non-mapping payloads from the coordinator fall back to empty mappings."""

  class _InvalidCoordinator(_CoordinatorStub):
    def get_module_data(self, dog_id: str, module: str) -> CoordinatorModuleState:
      return cast(CoordinatorModuleState, cast(Any, "invalid"))

  coordinator = _InvalidCoordinator({"alpha": cast(CoordinatorDogData, {})})
  sensor = _DummySensor(coordinator)

  payload = sensor._get_module_data("gps")

  assert payload == {}
