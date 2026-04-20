"""Unit tests for PawControlEntity and PawControlDogEntityBase base classes.

Exercises dog data caching, module lookup, status snapshot retrieval,
and extra_state_attributes enrichment without requiring a full HA stack.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.coordinator import PawControlCoordinator
from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    CoordinatorRuntimeManagers,
    PawControlConfigEntry,
)

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
def test_entity_name_prefers_attr_name_and_supports_translated_none() -> None:
    """Name property should return explicit attr name or None for translated entities."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "milo", "Milo")

    entity._attr_name = "Custom Milo"
    assert entity.name == "Custom Milo"

    entity._attr_name = None
    entity._attr_translation_key = "status"
    entity._attr_has_entity_name = True
    assert entity.name is None


@pytest.mark.unit
def test_entity_device_class_and_icon_properties() -> None:
    """Device class and icon properties should expose configured attributes."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "luna", "Luna")
    entity._attr_device_class = "connectivity"
    entity._attr_icon = "mdi:dog"

    assert entity.device_class == "connectivity"
    assert entity.icon == "mdi:dog"


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


@pytest.mark.unit
def test_get_dog_data_alias_uses_cached_lookup() -> None:
    """_get_dog_data should call the cached getter alias path."""
    dog_data: CoordinatorDogData = cast(
        CoordinatorDogData,
        {
            "dog_info": {"dog_id": "buddy", "dog_name": "Buddy"},
            "status": "online",
            "last_update": datetime.now(UTC).isoformat(),
        },
    )
    coord = _StubCoordinator({"buddy": dog_data})
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "buddy", "Buddy")

    result = entity._get_dog_data()
    assert result is not None
    assert result["status"] == "online"


@pytest.mark.unit
def test_get_runtime_data_returns_none_when_config_entry_missing(hass: Any) -> None:
    """_get_runtime_data should short-circuit when coordinator has no config entry."""
    coord = _StubCoordinator()
    coord.config_entry = None
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "cfg", "Cfg")
    entity.hass = hass

    assert entity._get_runtime_data() is None


@pytest.mark.unit
def test_get_runtime_managers_builds_container_from_coordinator_attributes() -> None:
    """Runtime manager fallback should build and attach a CoordinatorRuntimeManagers."""
    coord = _StubCoordinator()
    coord.runtime_managers = object()
    coord.data_manager = SimpleNamespace(name="data")
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "dog", "Dog")

    managers = entity._get_runtime_managers()

    assert isinstance(managers, CoordinatorRuntimeManagers)
    assert managers.data_manager is coord.data_manager
    assert coord.runtime_managers is managers


# ---------------------------------------------------------------------------
# Module data lookup
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_module_data_returns_empty_mapping_for_unknown_module() -> None:
    """Querying a missing module returns an empty mapping without raising."""
    coord = _StubCoordinator({
        "dog1": cast(
            CoordinatorDogData,
            {"dog_info": {}, "status": "online", "last_update": None},
        )
    })
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "dog1", "Dog1")
    result = entity._get_module_data("nonexistent_module")
    assert isinstance(result, Mapping)
    assert len(result) == 0


@pytest.mark.unit
def test_get_module_data_returns_module_payload() -> None:
    """Returns the module payload when available in coordinator data."""
    walk_data = {"walk_in_progress": True, "distance": 1.5}
    coord = _StubCoordinator({
        "runner": cast(
            CoordinatorDogData,
            {
                "dog_info": {"dog_id": "runner", "dog_name": "Runner"},
                "status": "online",
                "last_update": datetime.now(UTC).isoformat(),
                "walk": walk_data,
            },
        )
    })
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "runner", "Runner")
    result = entity._get_module_data("walk")
    assert isinstance(result, Mapping)
    assert result.get("walk_in_progress") is True


@pytest.mark.unit
def test_get_module_data_normalizes_whitespace_module_keys() -> None:
    """Module lookup should normalize whitespace-surrounded module names."""
    walk_data = {"walk_in_progress": True}
    coord = _StubCoordinator({
        "runner": cast(
            CoordinatorDogData,
            {
                "dog_info": {"dog_id": "runner", "dog_name": "Runner"},
                "status": "online",
                "last_update": datetime.now(UTC).isoformat(),
                "walk": walk_data,
            },
        )
    })
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "runner", "Runner")

    result = entity._get_module_data(" walk ")
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
def test_extra_state_attributes_localize_last_update_timestamp(hass: Any) -> None:
    """A datetime last_update_success_time should be converted to an ISO local string."""
    coord = _StubCoordinator()
    coord.last_update_success_time = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "atlas", "Atlas")
    entity.hass = hass

    attrs = entity.extra_state_attributes
    assert isinstance(attrs.get("last_updated"), str)


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
                "dog_size": "medium",
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
    assert attrs.get("dog_size") == "medium"
    assert attrs.get("dog_weight") == 12.0


@pytest.mark.unit
def test_get_status_snapshot_returns_none_for_non_mapping_data() -> None:
    """Status snapshot lookup should return None when cached dog data is invalid."""

    class _BadDataCoordinator(_StubCoordinator):
        def get_dog_data(self, dog_id: str) -> CoordinatorDogData | None:
            return cast(CoordinatorDogData, "invalid")

    coord = _BadDataCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "ghost", "Ghost")

    assert entity._get_status_snapshot() is None


@pytest.mark.unit
def test_get_status_snapshot_prefers_existing_snapshot_mapping() -> None:
    """When a mapping snapshot exists it should be returned without rebuilding."""
    snapshot = {"state": "home", "is_home": True}
    coord = _StubCoordinator({
        "buddy": cast(
            CoordinatorDogData,
            {
                "dog_info": {"dog_id": "buddy", "dog_name": "Buddy"},
                "status": "online",
                "last_update": datetime.now(UTC).isoformat(),
                "status_snapshot": snapshot,
            },
        )
    })
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "buddy", "Buddy")

    assert entity._get_status_snapshot() == snapshot


@pytest.mark.unit
def test_get_runtime_data_returns_runtime_value_when_available(
    monkeypatch: pytest.MonkeyPatch,
    hass: Any,
) -> None:
    """Runtime lookup should return get_runtime_data output when hass and entry exist."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "r1", "R1")
    entity.hass = hass
    runtime_value = SimpleNamespace(marker="runtime")
    monkeypatch.setattr("custom_components.pawcontrol.entity.get_runtime_data", lambda *_args: runtime_value)

    assert entity._get_runtime_data() is runtime_value


@pytest.mark.unit
def test_get_runtime_managers_prefers_runtime_data_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime manager container should be hydrated from runtime_data attributes."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "hydrated", "Hydrated")

    data_manager = SimpleNamespace(name="dm")
    runtime_container = CoordinatorRuntimeManagers()
    runtime_data = SimpleNamespace(
        runtime_managers=runtime_container,
        data_manager=data_manager,
    )
    monkeypatch.setattr(entity, "_get_runtime_data", lambda: runtime_data)

    managers = entity._get_runtime_managers()
    assert managers is runtime_container
    assert managers.data_manager is data_manager


@pytest.mark.unit
def test_get_runtime_managers_returns_existing_container_instance() -> None:
    """Existing CoordinatorRuntimeManagers should be returned directly."""
    coord = _StubCoordinator()
    existing = CoordinatorRuntimeManagers(notification_manager=SimpleNamespace(name="notify"))
    coord.runtime_managers = existing
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "existing", "Existing")

    assert entity._get_runtime_managers() is existing


@pytest.mark.unit
def test_get_runtime_managers_returns_empty_container_when_no_sources() -> None:
    """Without runtime data or coordinator managers an empty container should be returned."""
    coord = _StubCoordinator()
    coord.runtime_managers = None
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "empty", "Empty")

    managers = entity._get_runtime_managers()
    assert isinstance(managers, CoordinatorRuntimeManagers)
    assert managers.data_manager is None


@pytest.mark.unit
def test_get_data_manager_and_notification_manager_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manager accessors should use runtime_data first and fallback containers second."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "mgr", "Mgr")

    runtime_data_manager = SimpleNamespace(name="runtime_dm")
    runtime_data = SimpleNamespace(data_manager=runtime_data_manager)
    monkeypatch.setattr(entity, "_get_runtime_data", lambda: runtime_data)
    assert entity._get_data_manager() is runtime_data_manager

    fallback_dm = SimpleNamespace(name="fallback_dm")
    fallback_nm = SimpleNamespace(name="fallback_nm")
    coord.runtime_managers = CoordinatorRuntimeManagers(
        data_manager=fallback_dm,
        notification_manager=fallback_nm,
    )
    monkeypatch.setattr(entity, "_get_runtime_data", lambda: None)
    assert entity._get_data_manager() is fallback_dm
    assert entity._get_notification_manager() is fallback_nm


@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_call_hass_service_wrapper_forwards_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service-call wrapper should delegate to async_call_hass_service_if_available."""
    coord = _StubCoordinator()
    entity = _ConcreteEntity(cast(PawControlCoordinator, coord), "svc", "Svc")
    entity.hass = SimpleNamespace()
    entity.entity_id = "sensor.svc"
    expected = object()

    async def _fake_call(*args: Any, **kwargs: Any) -> object:
        assert args[0] is entity.hass
        assert args[1] == "notify"
        assert args[2] == "mobile_app"
        assert args[3] == {"message": "hi"}
        assert kwargs["blocking"] is True
        assert "dog svc" in kwargs["description"]
        return expected

    monkeypatch.setattr("custom_components.pawcontrol.entity.async_call_hass_service_if_available", _fake_call)

    result = await entity._async_call_hass_service(
        "notify",
        "mobile_app",
        {"message": "hi"},
        blocking=True,
    )

    assert result is expected


def test_get_module_data_handles_lookup_type_value_and_generic_errors() -> None:
    """Lookup/Type/Value and generic exceptions should return empty mappings."""

    class _LookupCoordinator(_StubCoordinator):
        def get_module_data(self, dog_id: str, module: str) -> None:
            raise LookupError("missing")

    class _TypeCoordinator(_StubCoordinator):
        def get_module_data(self, dog_id: str, module: str) -> None:
            raise TypeError("bad type")

    class _ValueCoordinator(_StubCoordinator):
        def get_module_data(self, dog_id: str, module: str) -> None:
            raise ValueError("bad value")

    class _GenericCoordinator(_StubCoordinator):
        def get_module_data(self, dog_id: str, module: str) -> None:
            raise RuntimeError("boom")

    for coordinator in (
        _LookupCoordinator(),
        _TypeCoordinator(),
        _ValueCoordinator(),
        _GenericCoordinator(),
    ):
        entity = _ConcreteEntity(cast(PawControlCoordinator, coordinator), "dog", "Dog")
        assert entity._get_module_data("walk") == {}
