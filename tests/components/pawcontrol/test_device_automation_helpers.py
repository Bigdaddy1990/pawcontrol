"""Tests for device automation helper utilities."""

from dataclasses import dataclass
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.device_automation_helpers import (
    _coerce_runtime_data,
    _extract_dog_id,
    build_device_automation_metadata,
    build_unique_id,
    resolve_device_context,
    resolve_dog_data,
    resolve_entity_id,
    resolve_status_snapshot,
)
from custom_components.pawcontrol.types import (
    DomainRuntimeStoreEntry,
    PawControlRuntimeData,
)


@dataclass(slots=True)
class _CoordinatorStub:
    payload: Any

    def get_dog_data(self, dog_id: str) -> Any:
        return self.payload


@dataclass(slots=True)
class _RuntimeDataStub:
    coordinator: _CoordinatorStub


def test_build_device_automation_metadata_returns_copy() -> None:
    """Metadata helper should return an isolated mutable mapping."""
    metadata = build_device_automation_metadata()
    metadata["secondary"] = True

    assert metadata == {"secondary": True}
    assert build_device_automation_metadata() == {"secondary": False}


def test_extract_dog_id_returns_none_when_identifier_missing(
    hass: HomeAssistant,
) -> None:
    """Dog id extraction should only read identifiers for the integration domain."""
    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id="entry",
        identifiers={("other_domain", "other-id")},
    )

    assert _extract_dog_id(None) is None
    assert _extract_dog_id(device_entry) is None


def test_coerce_runtime_data_handles_supported_shapes() -> None:
    """Runtime data coercion should support direct, wrapped, and mapping payloads."""
    runtime_data = _RuntimeDataStub(coordinator=_CoordinatorStub(payload={}))
    typed_runtime_data = PawControlRuntimeData.__new__(PawControlRuntimeData)
    wrapped_data = DomainRuntimeStoreEntry(runtime_data=runtime_data)

    assert _coerce_runtime_data(typed_runtime_data) is typed_runtime_data
    assert _coerce_runtime_data(runtime_data) is runtime_data
    assert _coerce_runtime_data(wrapped_data) is runtime_data
    assert _coerce_runtime_data({"runtime_data": runtime_data}) is runtime_data
    assert _coerce_runtime_data({"runtime_data": wrapped_data}) is runtime_data
    assert _coerce_runtime_data({"runtime_data": None}) is None
    assert _coerce_runtime_data({"coordinator": object()}) is None


def test_coerce_runtime_data_accepts_reloaded_runtime_shapes() -> None:
    """Runtime coercion should support reloaded class/module identity checks."""
    runtime_data = _RuntimeDataStub(coordinator=_CoordinatorStub(payload={}))

    reloaded_runtime_type = type("PawControlRuntimeData", (), {})
    reloaded_runtime_type.__module__ = "custom_components.pawcontrol.types"
    reloaded_runtime = reloaded_runtime_type()

    reloaded_store_type = type("DomainRuntimeStoreEntry", (), {})
    reloaded_store_type.__module__ = "custom_components.pawcontrol.types"
    reloaded_store = reloaded_store_type()
    reloaded_store.runtime_data = runtime_data

    assert _coerce_runtime_data(None) is None
    assert _coerce_runtime_data(reloaded_runtime) is reloaded_runtime
    assert _coerce_runtime_data(reloaded_store) is runtime_data


def test_resolve_device_context_and_entity_id(hass: HomeAssistant) -> None:
    """Context and entity resolution should honor registry and runtime store data."""
    runtime_data = _RuntimeDataStub(coordinator=_CoordinatorStub(payload={}))
    hass.data[DOMAIN] = {"entry-1": DomainRuntimeStoreEntry(runtime_data=runtime_data)}

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id="entry-1",
        identifiers={(DOMAIN, "buddy")},
    )

    entity_registry = er.async_get(hass)
    entity_registry.async_get_or_create(
        "binary_sensor.pawcontrol_buddy_is_hungry",
        config_entry_id="entry-1",
        device_id=device_entry.id,
        platform="binary_sensor",
        unique_id=build_unique_id("buddy", "is_hungry"),
    )

    context = resolve_device_context(hass, device_entry.id)

    assert context.device_id == device_entry.id
    assert context.dog_id == "buddy"
    assert context.runtime_data is runtime_data
    assert (
        resolve_entity_id(
            hass,
            device_entry.id,
            build_unique_id("buddy", "is_hungry"),
            "binary_sensor",
        )
        == "binary_sensor.pawcontrol_buddy_is_hungry"
    )
    assert resolve_entity_id(hass, device_entry.id, "missing", "binary_sensor") is None


def test_resolve_device_context_without_matching_runtime_data(
    hass: HomeAssistant,
) -> None:
    """Context resolution should return ``None`` runtime data when store misses."""
    hass.data[DOMAIN] = {"other-entry": object()}

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id="entry-missing",
        identifiers={(DOMAIN, "buddy")},
    )

    context = resolve_device_context(hass, device_entry.id)

    assert context.device_id == device_entry.id
    assert context.dog_id == "buddy"
    assert context.runtime_data is None


def test_resolve_device_context_ignores_non_mapping_domain_store(
    hass: HomeAssistant,
) -> None:
    """Context resolution should ignore non-mapping domain stores safely."""
    hass.data[DOMAIN] = object()

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get_or_create(
        config_entry_id="entry-missing",
        identifiers={(DOMAIN, "buddy")},
    )

    context = resolve_device_context(hass, device_entry.id)

    assert context.device_id == device_entry.id
    assert context.dog_id == "buddy"
    assert context.runtime_data is None


def test_resolve_dog_data_and_snapshot_paths() -> None:
    """Dog data and status snapshot helpers should handle mapping and fallback paths."""
    dog_data = {
        "feeding": {"is_hungry": True},
        "walk": {"needs_walk": True},
        "gps": {"zone": "home"},
    }
    runtime_data = _RuntimeDataStub(coordinator=_CoordinatorStub(payload=dog_data))

    assert resolve_dog_data(runtime_data, "buddy") == dog_data
    assert resolve_dog_data(None, "buddy") is None
    assert resolve_dog_data(runtime_data, None) is None

    existing_snapshot = {"state": "custom", "dog_id": "buddy"}
    runtime_with_snapshot = _RuntimeDataStub(
        coordinator=_CoordinatorStub(payload={"status_snapshot": existing_snapshot})
    )
    assert resolve_status_snapshot(runtime_with_snapshot, "buddy") == existing_snapshot

    generated_snapshot = resolve_status_snapshot(runtime_data, "buddy")
    assert generated_snapshot is not None
    assert generated_snapshot["dog_id"] == "buddy"
    assert generated_snapshot["state"] == "hungry"
    assert resolve_status_snapshot(runtime_data, None) is None


def test_resolve_dog_data_returns_none_for_non_mapping_payload() -> None:
    """Non-mapping coordinator payloads should not be treated as dog data."""
    runtime_data = _RuntimeDataStub(coordinator=_CoordinatorStub(payload="invalid"))

    assert resolve_dog_data(runtime_data, "buddy") is None
