# ruff: noqa: D103
"""Tests for coordinator data accessor mixin helpers."""

from custom_components.pawcontrol.coordinator_accessors import (
    CoordinatorDataAccessMixin,
)


class _Registry:
    def __init__(self) -> None:
        self._configs = {
            "dog-1": {"name": "Milo", "breed": "Beagle"},
            "dog-2": {"name": "Luna", "breed": "Collie"},
        }

    def get(self, dog_id: str):
        return self._configs.get(dog_id)

    def ids(self) -> list[str]:
        return list(self._configs)

    def get_name(self, dog_id: str):
        config = self._configs.get(dog_id)
        return None if config is None else config["name"]


class _AccessorHarness(CoordinatorDataAccessMixin):
    def __init__(self) -> None:
        self.registry = _Registry()
        self._data = {
            "dog-1": {
                "dog_info": {"name": "Milo Runtime", "age": 4},
                "health": {"status": "ok", "heart_rate": 72},
                "custom": {"last_seen": "now"},
                "walk": "invalid",
                "raw": "text",
            }
        }
        self.runtime_managers = {}


def test_basic_registry_and_payload_accessors() -> None:
    harness = _AccessorHarness()

    assert harness.get_dog_config("dog-1") == {"name": "Milo", "breed": "Beagle"}
    assert harness.get_dog_ids() == ["dog-1", "dog-2"]
    assert harness.get_configured_dog_ids() == ["dog-1", "dog-2"]
    assert harness.get_dog_data("dog-1") == harness._data["dog-1"]
    assert harness.get_configured_dog_name("dog-2") == "Luna"


def test_get_module_data_handles_typed_and_untyped_modules() -> None:
    harness = _AccessorHarness()

    assert harness.get_module_data("dog-1", "health") == {
        "status": "ok",
        "heart_rate": 72,
    }
    assert harness.get_module_data("dog-1", "walk") == {"status": "unknown"}
    assert harness.get_module_data("dog-1", "custom") == {"last_seen": "now"}
    assert harness.get_module_data("dog-1", "raw") == {}


def test_get_module_data_missing_dogs_and_invalid_module_type() -> None:
    harness = _AccessorHarness()

    assert harness.get_module_data("missing", "health") == {"status": "unknown"}
    assert harness.get_module_data("missing", "something_custom") == {}
    assert harness.get_module_data("dog-1", 123) == {}  # type: ignore[arg-type]


def test_get_dog_info_prefers_runtime_payload_then_config_then_empty() -> None:
    harness = _AccessorHarness()

    assert harness.get_dog_info("dog-1") == {"name": "Milo Runtime", "age": 4}
    assert harness.get_dog_info("dog-2") == {"name": "Luna", "breed": "Collie"}
    assert harness.get_dog_info("missing") == {}


def test_is_typed_module_accepts_known_modules_only() -> None:
    assert _AccessorHarness._is_typed_module("health") is True
    assert _AccessorHarness._is_typed_module("weather") is True
    assert _AccessorHarness._is_typed_module("custom") is False
