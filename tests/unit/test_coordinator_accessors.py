"""Tests for the coordinator accessors and typed module fallbacks."""

from custom_components.pawcontrol.coordinator_accessors import (
  CoordinatorDataAccessMixin,
)
from custom_components.pawcontrol.coordinator_support import DogConfigRegistry
from custom_components.pawcontrol.types import CoordinatorRuntimeManagers


class _DummyCoordinator(CoordinatorDataAccessMixin):
  """Minimal coordinator that exposes the mixin helpers for tests."""  # noqa: E111

  def __init__(self) -> None:  # noqa: E111
    self.registry = DogConfigRegistry([
      {
        "dog_id": "alpha",
        "dog_name": "Alpha",
        "modules": {"gps": True, "feeding": True},
      }
    ])
    self._data = {
      dog_id: self.registry.empty_payload() for dog_id in self.registry.ids()
    }
    self.runtime_managers = CoordinatorRuntimeManagers()


def test_get_module_data_returns_unknown_status_for_missing_typed_module() -> None:
  """Typed modules fall back to an unknown status payload when absent."""  # noqa: E111

  coordinator = _DummyCoordinator()  # noqa: E111

  payload = coordinator.get_module_data("alpha", "gps")  # noqa: E111

  assert payload["status"] == "unknown"  # noqa: E111


def test_get_module_data_preserves_typed_payloads() -> None:
  """Typed module payloads are returned unchanged when available."""  # noqa: E111

  coordinator = _DummyCoordinator()  # noqa: E111
  coordinator._data["alpha"]["gps"] = {"status": "online", "fix_quality": "3d"}  # noqa: E111

  payload = coordinator.get_module_data("alpha", "gps")  # noqa: E111

  assert payload == {"status": "online", "fix_quality": "3d"}  # noqa: E111


def test_get_module_data_returns_empty_dict_for_unknown_modules() -> None:
  """Untyped modules continue to return empty dictionaries when unavailable."""  # noqa: E111

  coordinator = _DummyCoordinator()  # noqa: E111

  assert coordinator.get_module_data("alpha", "notifications") == {}  # noqa: E111
