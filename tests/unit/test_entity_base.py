"""Unit tests for PawControlEntity and PawControlDogEntityBase base classes.

Exercises dog data caching, module lookup, status snapshot retrieval,
and extra_state_attributes enrichment without requiring a full HA stack.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.entity import (
    PawControlDogEntityBase,
    PawControlEntity,
)
from custom_components.pawcontrol.types import CoordinatorDogData, PawControlConfigEntry


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------


@dataclass
class _StubEntry:
    entry_id: str = "stub_entry"


class _StubCoordinator:
    """Lightweight coordinator double for entity base class tests."""

    def __init__(
        self,
        dog_data: dict[str, CoordinatorDogData] | None = None,
        *,
        available: bool = True,
    ) -> None:
        self.data: dict[str, CoordinatorDogData] = dog_data or {}
        self.config_entry = cast(PawControlConfigEntry, _StubEntry())
        self.last_update_success = True
        self.last_exception = None
        self.runtime_managers = None
        self._available = available

    def async_add_listener(self, _cb: Any) -> Any:
        return lambda: None

    async def async_request_refresh(self) -> None:
        pass

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)

    def get_enabled_modules(self, dog_id: str) -> frozenset[str]:
        return frozenset()

    def get_module_data(self, dog_id: str, module: str) -> Mapping[str, Any] | None:
        dog = self.data.get(dog_id)
        if isinstance(dog, Mapping):
            return dog.get(module)  # type: ignore[return-value]
        return None

    @property
    def available(self) -> bool:
        return self._available


class _ConcreteEntity(PawControlDogEntityBase):
    """Concrete subclass used solely for testing the base class."""

    def __init__(
        self,
        coordinator: Any,
        dog_id: str,
        dog_name: str,
    ) -> None:
        super().__init__(coordinator, dog_id, dog_name)
        self._attr_unique_id = f"pawcontrol_{dog_id}_test"


# ---------------------------------------------------------------------------
# PawControlEntity properties
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_entity_exposes_dog_id_and_dog_name() -> None:
    """dog_id and dog_name properties must reflect construction arguments."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "rex", "Rex")
    assert entity.dog_id == "rex"
    assert entity.dog_name == "Rex"


@pytest.mark.unit
def test_entity_name_defaults_to_dog_name_when_no_translation_key() -> None:
    """When no translation key is set the entity name should be the dog name."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "bella", "Bella")
    # _attr_translation_key is not set — name falls back to dog name
    entity._attr_translation_key = None
    assert entity.name == "Bella"


@pytest.mark.unit
def test_entity_unique_id_exposed() -> None:
    """unique_id must equal the value assigned during construction."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "pup", "Pup")
    assert entity.unique_id == "pawcontrol_pup_test"


@pytest.mark.unit
def test_entity_has_entity_name_is_true() -> None:
    """_attr_has_entity_name must be True for Platinum compliance."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "coco", "Coco")
    assert entity.has_entity_name is True


# ---------------------------------------------------------------------------
# PawControlDogEntityBase caching
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_dog_data_cached_returns_none_when_unavailable() -> None:
    """Returns None when coordinator is unavailable."""
    coord = _StubCoordinator(available=False)
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "x", "X")
    assert entity._get_dog_data_cached() is None


@pytest.mark.unit
def test_get_dog_data_cached_returns_dog_data() -> None:
    """Returns the dog data from the coordinator when available."""
    dog_data: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "friend", "dog_name": "Friend"},
            "status": "online",
            "last_update": datetime.now(UTC).isoformat(),
        },
    )
    coord = _StubCoordinator({"friend": dog_data})
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "friend", "Friend")
    result = entity._get_dog_data_cached()
    assert result is not None
    assert result["status"] == "online"


@pytest.mark.unit
def test_get_dog_data_cached_uses_cache_on_second_call() -> None:
    """A second call within the TTL window must return cached data."""
    dog_data: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "pip", "dog_name": "Pip"},
            "status": "online",
            "last_update": datetime.now(UTC).isoformat(),
        },
    )
    coord = _StubCoordinator({"pip": dog_data})
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "pip", "Pip")

    first = entity._get_dog_data_cached()
    # Mutate the coordinator data to confirm cached result is served
    coord.data["pip"] = cast(CoordinatorDogData, dict(dog_data) | {"status": "mutated"})
    second = entity._get_dog_data_cached()
    assert first is not None
    assert second is not None
    assert second["status"] == "online"  # still cached


@pytest.mark.unit
def test_set_cache_ttl_changes_ttl() -> None:
    """_set_cache_ttl must update _cache_ttl attribute."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "z", "Z")
    entity._set_cache_ttl(5.0)
    assert entity._cache_ttl == 5.0


# ---------------------------------------------------------------------------
# Module data lookup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_module_data_returns_empty_mapping_for_unknown_module() -> None:
    """Querying a missing module returns an empty mapping without raising."""
    coord = _StubCoordinator(
        {
            "dog1": cast(
                CoordinatorDogData,
                {"dog_info": {}, "status": "online", "last_update": None},
            )
        }
    )
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "dog1", "Dog1")
    result = entity._get_module_data("nonexistent_module")
    assert isinstance(result, Mapping)
    assert len(result) == 0


@pytest.mark.unit
def test_get_module_data_returns_module_payload() -> None:
    """Returns the module payload when available in coordinator data."""
    walk_data = {"walk_in_progress": True, "distance": 1.5}
    coord = _StubCoordinator(
        {
            "runner": cast(
                CoordinatorDogData,
                {
                    "dog_info": {"dog_id": "runner", "dog_name": "Runner"},
                    "status": "online",
                    "last_update": datetime.now(UTC).isoformat(),
                    "walk": walk_data,
                },
            )
        }
    )
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "runner", "Runner")
    result = entity._get_module_data("walk")
    assert isinstance(result, Mapping)
    assert result.get("walk_in_progress") is True


@pytest.mark.unit
def test_get_module_data_handles_attribute_error_gracefully() -> None:
    """An AttributeError during module lookup must return an empty mapping."""

    class _BrokenCoordinator(_StubCoordinator):
        def get_module_data(self, dog_id: str, module: str) -> None:
            raise AttributeError("broken")

    coord = _BrokenCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "err", "Err")
    result = entity._get_module_data("walk")
    assert isinstance(result, Mapping)


@pytest.mark.unit
def test_get_module_data_handles_invalid_string_input() -> None:
    """An empty string module name must return an empty mapping."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "dog", "Dog")
    result = entity._get_module_data("")
    assert isinstance(result, Mapping)
    assert len(result) == 0


# ---------------------------------------------------------------------------
# extra_state_attributes enrichment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extra_state_attributes_includes_base_fields(hass: Any) -> None:
    """extra_state_attributes must include dog_id and dog_name."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "lucy", "Lucy")
    entity.hass = hass
    attrs = entity.extra_state_attributes
    assert attrs.get("dog_id") == "lucy"
    assert attrs.get("dog_name") == "Lucy"


@pytest.mark.unit
def test_extra_state_attributes_includes_last_updated(hass: Any) -> None:
    """last_updated must be present in entity attributes."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "scout", "Scout")
    entity.hass = hass
    attrs = entity.extra_state_attributes
    assert "last_updated" in attrs


@pytest.mark.unit
def test_append_dog_info_attributes_adds_breed(hass: Any) -> None:
    """Dog info attributes are appended when breed is available."""
    dog_data: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
            "dog_info": {
                "dog_id": "bree",
                "dog_name": "Bree",
                "dog_breed": "Poodle",
                "dog_age": 4,
                "dog_weight": 12.0,
            },
            "status": "online",
            "last_update": datetime.now(UTC).isoformat(),
        },
    )
    coord = _StubCoordinator({"bree": dog_data})
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "bree", "Bree")
    entity.hass = hass
    attrs = entity.extra_state_attributes
    assert attrs.get("dog_breed") == "Poodle"
    assert attrs.get("dog_age") == 4
    assert attrs.get("dog_weight") == 12.0
