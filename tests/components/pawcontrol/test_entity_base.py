"""Coverage tests for shared PawControl entity helpers."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pytest

pytest.importorskip("homeassistant")

from custom_components.pawcontrol.entity import PawControlDogEntityBase
from custom_components.pawcontrol.service_guard import ServiceGuardResult
from custom_components.pawcontrol.types import (
    CoordinatorDogData,
    CoordinatorRuntimeManagers,
)


class _DummyCoordinator:
    """Coordinator double used to exercise base-entity helper methods."""

    def __init__(self) -> None:
        self.available = True
        self.data: dict[str, CoordinatorDogData] = {}
        self.config_entry = object()
        self.last_update_success = True
        self.last_update_success_time = datetime(2024, 1, 1, tzinfo=UTC)
        self.last_exception: Exception | None = None

    def async_add_listener(
        self,
        _callback: Callable[[], None],  # noqa: F821
    ) -> Callable[[], None]:  # pragma: no cover - protocol stub  # noqa: F821
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


def test_entity_name_device_class_and_icon_properties() -> None:
    """Base entity property helpers should mirror configured attributes."""
    entity = _make_entity()

    entity._attr_name = "Tracker"
    entity._attr_translation_key = "dog_tracker"
    entity._attr_device_class = "enum"
    entity._attr_icon = "mdi:dog"
    assert entity.name == "Tracker"
    assert entity.device_class == "enum"
    assert entity.icon == "mdi:dog"

    del entity._attr_name
    assert entity.name is None


def test_entity_basics_contract(assert_entity_basics) -> None:
    """Shared entity baseline helper should validate required attributes."""
    entity = _make_entity()
    entity._attr_unique_id = "dog-1-status"
    assert_entity_basics(entity)


def test_entity_extra_state_attributes_include_last_exception_details() -> None:
    """Entity attributes should include coordinator exception context."""
    entity = _make_entity()
    entity.coordinator.last_exception = RuntimeError("update failed")

    attrs = entity._build_base_state_attributes()

    assert attrs["last_update_error"] == "update failed"
    assert attrs["last_update_error_type"] == "RuntimeError"


def test_update_device_metadata_delegates_to_link_mixin() -> None:
    """update_device_metadata should pass through all provided kwargs."""
    entity = _make_entity()
    recorded: dict[str, object] = {}

    def _capture(**details: object) -> None:
        recorded.update(details)

    entity._set_device_link_info = _capture  # type: ignore[method-assign]

    entity.update_device_metadata(room="garden", floor=1)

    assert recorded == {"room": "garden", "floor": 1}


def test_runtime_manager_accessors_use_runtime_data_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime manager accessors should hydrate from runtime_data before fallback."""
    entity = _make_entity()
    entity.hass = cast(Any, object())

    class _RuntimeData:
        runtime_managers = CoordinatorRuntimeManagers()
        data_manager = "dm"
        notification_manager = "nm"

    monkeypatch.setattr(
        "custom_components.pawcontrol.entity.get_runtime_data",
        lambda _hass, _entry: _RuntimeData(),
    )

    managers = entity._get_runtime_managers()

    assert managers.data_manager == "dm"
    assert managers.notification_manager == "nm"
    assert entity._get_data_manager() == "dm"
    assert entity._get_notification_manager() == "nm"


def test_get_runtime_data_returns_none_when_config_entry_missing() -> None:
    """Runtime data lookup should short-circuit when coordinator has no entry."""
    entity = _make_entity()
    entity.hass = cast(Any, object())
    entity.coordinator.config_entry = None

    assert entity._get_runtime_data() is None


def test_get_data_manager_falls_back_to_runtime_manager_container() -> None:
    """Data manager accessor should fallback to runtime manager container."""
    entity = _make_entity()
    entity.hass = cast(Any, object())
    entity.coordinator.config_entry = None
    entity.coordinator.runtime_managers = CoordinatorRuntimeManagers(
        data_manager="fallback-dm",
    )

    assert entity._get_data_manager() == "fallback-dm"


@pytest.mark.asyncio
async def test_async_call_hass_service_delegates_to_guard_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_async_call_hass_service should pass normalized context into helper."""
    entity = _make_entity()
    entity._attr_hass = object()
    entity.entity_id = "sensor.dog_1"

    captured: dict[str, object] = {}

    async def _fake_async_call(
        hass: object,
        domain: str,
        service: str,
        service_data: object,
        *,
        blocking: bool,
        description: str,
        logger: object,
    ) -> ServiceGuardResult:
        captured.update({
            "hass": hass,
            "domain": domain,
            "service": service,
            "service_data": service_data,
            "blocking": blocking,
            "description": description,
            "logger": logger,
        })
        return ServiceGuardResult(domain=domain, service=service, executed=True)

    monkeypatch.setattr(
        "custom_components.pawcontrol.entity.async_call_hass_service_if_available",
        _fake_async_call,
    )

    result = await entity._async_call_hass_service(
        "notify",
        "mobile_app",
        {"message": "hi"},
        blocking=True,
    )

    assert result.executed is True
    assert captured["domain"] == "notify"
    assert captured["service"] == "mobile_app"
    assert captured["service_data"] == {"message": "hi"}
    assert captured["blocking"] is True
    assert captured["description"] == "dog dog-1 (sensor.dog_1)"


@pytest.mark.asyncio
async def test_async_call_hass_service_uses_unregistered_guard_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guard helper context should fallback when no entity_id is assigned."""
    entity = _make_entity()
    entity._attr_hass = object()

    captured: dict[str, object] = {}

    async def _fake_async_call(
        hass: object,
        domain: str,
        service: str,
        service_data: object,
        *,
        blocking: bool,
        description: str,
        logger: object,
    ) -> ServiceGuardResult:
        captured.update({
            "hass": hass,
            "domain": domain,
            "service": service,
            "service_data": service_data,
            "blocking": blocking,
            "description": description,
            "logger": logger,
        })
        return ServiceGuardResult(
            domain=domain,
            service=service,
            executed=False,
            reason="hass_unavailable",
        )

    monkeypatch.setattr(
        "custom_components.pawcontrol.entity.async_call_hass_service_if_available",
        _fake_async_call,
    )

    result = await entity._async_call_hass_service(
        "switch",
        "turn_off",
        {"entity_id": "switch.demo"},
    )

    assert result.executed is False
    assert result.reason == "hass_unavailable"
    assert captured["description"] == "dog dog-1 (unregistered)"


def test_get_module_data_handles_unexpected_exception_and_invalid_payload() -> None:
    """Unexpected lookup failures and non-mappings should return empty payloads."""
    entity = _make_entity()

    def _explode(_dog_id: str, _module: str) -> Mapping[str, object]:
        raise RuntimeError("broken")

    entity.coordinator.get_module_data = _explode  # type: ignore[attr-defined]
    assert entity._get_module_data("health") == {}

    entity.coordinator.get_module_data = (  # type: ignore[attr-defined]
        lambda _dog_id, _module: "invalid"
    )
    assert entity._get_module_data("health") == {}


def test_get_status_snapshot_uses_embedded_and_computed_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Status snapshot should prefer embedded values and fallback to builder."""
    entity = _make_entity()
    entity.coordinator.data["dog-1"] = cast(
        CoordinatorDogData,
        {"status_snapshot": {"state": "ready"}},
    )
    assert entity._get_status_snapshot() == {"state": "ready"}

    entity.coordinator.data["dog-1"] = cast(CoordinatorDogData, {"status": "idle"})
    entity._dog_data_cache.clear()
    entity._cache_timestamp.clear()
    monkeypatch.setattr(
        "custom_components.pawcontrol.entity.build_dog_status_snapshot",
        lambda dog_id, data: {"id": dog_id, "status": data.get("status")},
    )
    assert entity._get_status_snapshot() == {"id": "dog-1", "status": "idle"}


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


def test_identity_properties_and_name_fallbacks() -> None:
    """Entity identity helpers should expose ids and fallback naming."""
    entity = _make_entity()

    assert entity.dog_id == "dog-1"
    assert entity.dog_name == "Buddy"
    assert entity.unique_id is None

    entity._attr_translation_key = "status"
    entity._attr_has_entity_name = False
    assert entity.name == "Buddy"


def test_runtime_manager_fallback_paths_cover_missing_runtime_data() -> None:
    """Runtime manager lookup should fallback through coordinator containers."""
    entity = _make_entity()

    # No hass => no runtime data lookup.
    assert entity._get_runtime_data() is None

    # Existing coordinator runtime container is reused.
    existing = CoordinatorRuntimeManagers(data_manager="coordinator-dm")
    entity.coordinator.runtime_managers = existing  # type: ignore[attr-defined]
    assert entity._get_runtime_managers() is existing

    # Coordinator attributes should be hydrated into a new container.
    entity.coordinator.runtime_managers = object()  # type: ignore[attr-defined]
    entity.coordinator.data_manager = "hydrated-dm"  # type: ignore[attr-defined]
    hydrated = entity._get_runtime_managers()
    assert hydrated.data_manager == "hydrated-dm"

    # When no runtime managers are present, an empty container is returned.
    entity.coordinator.runtime_managers = None  # type: ignore[attr-defined]
    entity.coordinator.data_manager = None  # type: ignore[attr-defined]
    empty = entity._get_runtime_managers()
    assert isinstance(empty, CoordinatorRuntimeManagers)


def test_dog_data_cache_and_status_snapshot_handle_unavailable_or_invalid_data() -> (
    None
):
    """Dog-data helpers should handle unavailable coordinators and bad payloads."""
    entity = _make_entity()
    entity.coordinator.available = False

    assert entity._get_dog_data() is None
    assert entity._get_status_snapshot() is None

    entity.coordinator.available = True
    entity.coordinator.data["dog-1"] = cast(CoordinatorDogData, {"dog_info": "bad"})
    entity._dog_data_cache.clear()
    entity._cache_timestamp.clear()

    attrs: dict[str, object] = {}
    entity._append_dog_info_attributes(attrs)
    assert attrs == {}


def test_extra_state_attributes_sets_last_updated_none_without_datetime() -> None:
    """Last-updated should be None when coordinator timestamp is not a datetime."""
    entity = _make_entity()
    entity.coordinator.last_update_success_time = "invalid"  # type: ignore[assignment]

    attrs = entity.extra_state_attributes

    assert attrs["last_updated"] is None


def test_append_dog_info_attributes_ignores_non_mapping_dog_data() -> None:
    """Dog-info enrichment should skip payloads that are not mappings."""
    entity = _make_entity()
    entity._dog_data_cache.clear()
    entity._cache_timestamp.clear()
    entity.coordinator.data["dog-1"] = cast(CoordinatorDogData, ["not", "mapping"])

    attrs: dict[str, object] = {}
    entity._append_dog_info_attributes(attrs)

    assert attrs == {}


@pytest.mark.parametrize("module_name", ["", "   ", cast(Any, 123)])
def test_get_module_data_rejects_invalid_module_identifiers(module_name: Any) -> None:
    """Module lookup should short-circuit for invalid or empty module names."""
    entity = _make_entity()

    assert entity._get_module_data(module_name) == {}
