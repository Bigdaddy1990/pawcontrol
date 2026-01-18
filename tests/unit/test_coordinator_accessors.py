"""Tests for the coordinator accessors and typed module fallbacks."""

from __future__ import annotations

from custom_components.pawcontrol.coordinator_accessors import (
  CoordinatorDataAccessMixin,
)
from custom_components.pawcontrol.coordinator_support import DogConfigRegistry
from custom_components.pawcontrol.types import CoordinatorRuntimeManagers


class _DummyCoordinator(CoordinatorDataAccessMixin):
  """Minimal coordinator that exposes the mixin helpers for tests."""

  def __init__(self) -> None:
    self.registry = DogConfigRegistry(
      [
        {
          "dog_id": "alpha",
          "dog_name": "Alpha",
          "modules": {"gps": True, "feeding": True},
        }
      ]
    )
    self._data = {
      dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
    }
    self.runtime_managers = CoordinatorRuntimeManagers()


def test_get_module_data_returns_unknown_status_for_missing_typed_module() -> None:
  """Typed modules fall back to an unknown status payload when absent."""

  coordinator = _DummyCoordinator()

  payload = coordinator.get_module_data("alpha", "gps")

  assert payload["status"] == "unknown"


def test_get_module_data_preserves_typed_payloads() -> None:
  """Typed module payloads are returned unchanged when available."""

  coordinator = _DummyCoordinator()
  coordinator._data["alpha"]["gps"] = {"status": "online", "fix_quality": "3d"}

  payload = coordinator.get_module_data("alpha", "gps")

  assert payload == {"status": "online", "fix_quality": "3d"}


def test_get_module_data_returns_empty_dict_for_unknown_modules() -> None:
  """Untyped modules continue to return empty dictionaries when unavailable."""

  coordinator = _DummyCoordinator()

  assert coordinator.get_module_data("alpha", "notifications") == {}
