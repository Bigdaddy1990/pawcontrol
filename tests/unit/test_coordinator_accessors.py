"""Tests for the coordinator accessors and typed module fallbacks."""

from typing import Any, cast

from custom_components.pawcontrol.coordinator_accessors import (
    CoordinatorDataAccessMixin,
)
from custom_components.pawcontrol.coordinator_support import DogConfigRegistry
from custom_components.pawcontrol.types import CoordinatorRuntimeManagers


class _DummyCoordinator(CoordinatorDataAccessMixin):
    """Minimal coordinator that exposes the mixin helpers for tests."""

    def __init__(self) -> None:
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


def test_basic_registry_and_data_accessors_return_expected_values() -> None:
    """Simple accessor aliases expose registry and in-memory payloads."""
    coordinator = _DummyCoordinator()

    assert coordinator.get_dog_config("alpha") == {
        "dog_id": "alpha",
        "dog_name": "Alpha",
        "modules": {"gps": True, "feeding": True},
    }
    assert coordinator.get_dog_ids() == ["alpha"]
    assert coordinator.get_configured_dog_ids() == ["alpha"]
    assert coordinator.get_dog_data("alpha") == coordinator._data["alpha"]
    assert coordinator.get_configured_dog_name("alpha") == "Alpha"


def test_get_module_data_handles_non_string_module_values() -> None:
    """Non-string module keys are guarded and produce empty mappings."""
    coordinator = _DummyCoordinator()

    payload = coordinator.get_module_data("alpha", cast(Any, 42))

    assert payload == {}


def test_get_module_data_missing_dog_returns_typed_or_untyped_fallback() -> None:
    """Missing dogs use unknown status for typed modules and empty for untyped."""
    coordinator = _DummyCoordinator()

    assert coordinator.get_module_data("unknown", "gps") == {"status": "unknown"}
    assert coordinator.get_module_data("unknown", "notifications") == {}


def test_get_module_data_validates_payload_shape_for_typed_and_untyped_modules() -> None:
    """Typed payloads require a mapping while untyped payloads allow any mapping."""
    coordinator = _DummyCoordinator()
    coordinator._data["alpha"]["gps"] = cast(Any, "invalid")
    coordinator._data["alpha"]["notifications"] = {"enabled": True}

    assert coordinator.get_module_data("alpha", "gps") == {"status": "unknown"}
    assert coordinator.get_module_data("alpha", "notifications") == {"enabled": True}


def test_get_dog_info_prefers_runtime_mapping_then_registry_then_empty_dict() -> None:
    """Dog info helper prioritizes runtime data and has deterministic fallback."""
    coordinator = _DummyCoordinator()
    coordinator._data["alpha"]["dog_info"] = {"dog_name": "Runtime Alpha"}

    assert coordinator.get_dog_info("alpha") == {"dog_name": "Runtime Alpha"}

    coordinator._data["alpha"]["dog_info"] = cast(Any, "invalid")

    assert coordinator.get_dog_info("alpha")["dog_name"] == "Alpha"
    assert coordinator.get_dog_info("unknown") == {}
