"""Focused contract tests for the dog status entity."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pytest

pytest.importorskip("homeassistant")

from homeassistant.const import STATE_UNKNOWN

from custom_components.pawcontrol.sensor import PawControlDogStatusSensor
from custom_components.pawcontrol.types import CoordinatorDogData, JSONMutableMapping

_DOG_ID = "dog-1"
_DOG_NAME = "Buddy"


@dataclass
class _DummyEntry:
    entry_id: str


class _CoordinatorDouble:
    """Coordinator double for dog status entity tests."""

    def __init__(self, data: dict[str, CoordinatorDogData] | None = None) -> None:
        self.data = data or {}
        self.available = True
        self.config_entry = _DummyEntry("entry-1")
        self.last_update_success = True
        self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
        self.last_exception: Exception | None = None

    def async_add_listener(self, _callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: None

    async def async_request_refresh(self) -> None:  # pragma: no cover - protocol
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_module_data(self, dog_id: str, module: str) -> JSONMutableMapping:
        dog_data = self.data.get(dog_id)
        if not isinstance(dog_data, Mapping):
            return cast(JSONMutableMapping, {})
        module_data = dog_data.get(module)
        if isinstance(module_data, Mapping):
            return cast(JSONMutableMapping, dict(module_data))
        return cast(JSONMutableMapping, {})


def _make_entity(payload: Mapping[str, object] | None) -> PawControlDogStatusSensor:
    data: dict[str, CoordinatorDogData] = {}
    if payload is not None:
        data[_DOG_ID] = cast(CoordinatorDogData, dict(payload))
    coordinator = _CoordinatorDouble(data)
    entity = PawControlDogStatusSensor(cast(Any, coordinator), _DOG_ID, _DOG_NAME)
    entity._set_cache_ttl(0.0)
    return entity


def test_entity_unique_id_name_device_info() -> None:
    """Entity should expose stable identity and device metadata."""
    entity = _make_entity({"status_snapshot": {"state": "home"}})

    assert entity.unique_id == "pawcontrol_dog-1_status"
    assert entity.name == _DOG_NAME
    assert entity.device_info is not None


def test_entity_available_true_false() -> None:
    """Availability should mirror coordinator state and payload availability."""
    entity = _make_entity({"status_snapshot": {"state": "home"}})

    assert entity.available is True

    entity.coordinator.available = False
    assert entity.available is False


@pytest.mark.parametrize("status_value", ["home", "walking", "needs_walk"])
def test_entity_state_mapping_valid_values(status_value: str) -> None:
    """Known status snapshot strings should pass through unchanged."""
    entity = _make_entity({"status_snapshot": {"state": status_value}})

    assert entity.native_value == status_value


@pytest.mark.parametrize("status_value", ["", None, 123, []])
def test_entity_state_mapping_unknown_values(status_value: object) -> None:
    """Unknown snapshot values should fallback to deterministic defaults."""
    entity = _make_entity({"status_snapshot": {"state": status_value}})

    assert entity.native_value == "away"


def test_entity_attributes_complete() -> None:
    """Attributes should include core identity and dog metadata fields."""
    entity = _make_entity(
        {
            "status_snapshot": {"state": "home"},
            "dog_info": {
                "dog_breed": "Collie",
                "dog_age": 4,
                "dog_size": "large",
                "dog_weight": 22,
            },
        },
    )

    attrs = entity.extra_state_attributes

    assert attrs["dog_id"] == _DOG_ID
    assert attrs["dog_name"] == _DOG_NAME
    assert attrs["sensor_type"] == "status"
    assert attrs["dog_breed"] == "Collie"
    assert attrs["dog_age"] == 4
    assert attrs["dog_size"] == "large"
    assert attrs["dog_weight"] == 22
    assert "last_updated" in attrs


def test_entity_handles_none_payload() -> None:
    """Entity should handle missing coordinator payload without raising."""
    entity = _make_entity(None)

    assert entity.native_value == STATE_UNKNOWN
    assert entity.available is False


def test_entity_updates_after_coordinator_refresh() -> None:
    """Entity state should reflect coordinator payload changes."""
    entity = _make_entity({"status_snapshot": {"state": "home"}})

    assert entity.native_value == "home"

    entity.coordinator.data[_DOG_ID] = cast(
        CoordinatorDogData,
        {
            "walk": {"walk_in_progress": True},
            "gps": {"zone": "park"},
        },
    )

    assert entity.native_value == "walking"
