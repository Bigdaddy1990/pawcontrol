"""Coverage tests for shared PawControl entity helpers."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.types import CoordinatorDogData


class _DummyCoordinator:
    """Coordinator double used to exercise base-entity helper methods."""

    def __init__(self) -> None:
        self.available = True
        self.data: dict[str, CoordinatorDogData] = {}
        self.last_update_success = True
        self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
        self.last_exception: Exception | None = None

    def async_add_listener(self, _callback: "Callable[[], None]") -> "Callable[[], None]":  # pragma: no cover - protocol stub
        return lambda: None

    async def async_request_refresh(
        self,
    ) -> None:  # pragma: no cover - protocol stub
        return None

    def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
        return self.data.get(dog_id)


class _EntityUnderTest(PawControlDogEntityBase):
    """Concrete entity used to test helper logic on the shared base class."""

    @property
    def native_value(self) -> str:
        return "ok"


def _make_entity() -> _EntityUnderTest:
    coordinator = _DummyCoordinator()
    coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {
            "dog_info": {
                "dog_breed": "Collie",
                "dog_age": 4,
                "dog_size": "large",
                "dog_weight": 22,
            },
            "health": {"score": 5},
        },
    )
    entity = _EntityUnderTest(cast(Any, coordinator), "dog-1", "Buddy")
    entity._set_cache_ttl(999.0)
    return entity


def test_build_base_state_attributes_merges_dog_info() -> None:
    """Base attribute builder should include dog info and normalized extra payload."""
    entity = _make_entity()

    attrs = entity._build_base_state_attributes({"tags": {"a", "b"}})

    assert attrs["dog_breed"] == "Collie"
    assert attrs["dog_age"] == 4
    assert attrs["dog_size"] == "large"
    assert attrs["dog_weight"] == 22
    assert sorted(cast(list[str], attrs["tags"])) == ["a", "b"]


def test_get_module_data_falls_back_to_dog_payload_when_lookup_missing() -> None:
    """Module lookup should fallback to dog data if the coordinator lacks helper."""
    entity = _make_entity()

    module_data = entity._get_module_data(" health ")

    assert isinstance(module_data, Mapping)
    assert module_data == {"score": 5}


@pytest.mark.parametrize(
    "exc",
    [
        AttributeError("boom"),
        LookupError("boom"),
        TypeError("boom"),
        ValueError("boom"),
    ],
)
def test_get_module_data_returns_empty_mapping_for_expected_errors(
    exc: Exception,
) -> None:
    """Expected lookup failures should be absorbed and return an empty mapping."""
    entity = _make_entity()

    def _raiser(_dog_id: str, _module: str) -> Mapping[str, object]:
        raise exc

    entity.coordinator.get_module_data = _raiser  # type: ignore[attr-defined]

    assert entity._get_module_data("health") == {}
