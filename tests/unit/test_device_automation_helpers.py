"""Unit tests for device automation helper utilities."""

from types import SimpleNamespace

from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.device_automation_helpers import (
    _coerce_runtime_data,
    _extract_dog_id,
    build_device_automation_metadata,
    resolve_device_context,
    resolve_dog_data,
    resolve_entity_id,
    resolve_status_snapshot,
)
from custom_components.pawcontrol.types import DomainRuntimeStoreEntry, PawControlRuntimeData


def _runtime_data_with_coordinator(coordinator: object) -> PawControlRuntimeData:
    """Create a lightweight runtime data instance for helper tests."""
    runtime_data = object.__new__(PawControlRuntimeData)
    runtime_data.coordinator = coordinator
    return runtime_data


def test_build_device_automation_metadata_returns_isolated_copy() -> None:
    """Metadata payload should be mutable without affecting future calls."""
    metadata = build_device_automation_metadata()
    metadata["secondary"] = True

    assert build_device_automation_metadata() == {"secondary": False}


def test_extract_dog_id_uses_domain_identifier() -> None:
    """The helper should return the PawControl identifier when present."""
    device_entry = SimpleNamespace(
        identifiers={("other", "abc"), (DOMAIN, "dog-123")},
    )

    assert _extract_dog_id(device_entry) == "dog-123"
    assert _extract_dog_id(None) is None


def test_coerce_runtime_data_supports_store_entries() -> None:
    """Runtime data should be unwrapped from domain store entry containers."""
    runtime_data = _runtime_data_with_coordinator(SimpleNamespace())

    assert _coerce_runtime_data(runtime_data) is runtime_data
    assert _coerce_runtime_data(DomainRuntimeStoreEntry(runtime_data=runtime_data)) is runtime_data
    assert _coerce_runtime_data(object()) is None


def test_resolve_device_context_and_entity_id(monkeypatch) -> None:
    """Device context and entity-id lookups should use registries and runtime store."""
    runtime_data = _runtime_data_with_coordinator(SimpleNamespace())
    device_entry = SimpleNamespace(
        identifiers={(DOMAIN, "buddy")},
        config_entries=["entry_missing", "entry_present"],
    )
    device_registry = SimpleNamespace(async_get=lambda _device_id: device_entry)
    entity_registry = SimpleNamespace(
        async_entries_for_device=lambda _device_id: [
            SimpleNamespace(
                unique_id="pawcontrol_buddy_sensor",
                platform="sensor",
                entity_id="sensor.buddy",
            ),
            SimpleNamespace(
                unique_id="pawcontrol_buddy_binary",
                platform="binary_sensor",
                entity_id="binary_sensor.buddy",
            ),
        ]
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.device_automation_helpers.dr.async_get",
        lambda _hass: device_registry,
    )
    monkeypatch.setattr(
        "custom_components.pawcontrol.device_automation_helpers.er.async_get",
        lambda _hass: entity_registry,
    )

    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_present": DomainRuntimeStoreEntry(runtime_data=runtime_data),
            }
        }
    )

    context = resolve_device_context(hass, "device-1")

    assert context.device_id == "device-1"
    assert context.dog_id == "buddy"
    assert context.runtime_data is runtime_data
    assert resolve_entity_id(hass, "device-1", "pawcontrol_buddy_sensor", "sensor") == "sensor.buddy"
    assert resolve_entity_id(hass, "device-1", "missing", "sensor") is None


def test_resolve_dog_data_and_status_snapshot_paths() -> None:
    """Dog data and snapshots should support direct snapshots and fallback synthesis."""
    direct_snapshot = {"health": "good", "activity": "active"}
    dog_payload_with_snapshot = {
        "status_snapshot": direct_snapshot,
        "name": "Buddy",
    }
    dog_payload_without_snapshot = {
        "feeding": {"is_hungry": True},
        "gps": {"zone": "park"},
        "walk": {"walk_in_progress": False, "needs_walk": False},
    }
    coordinator = SimpleNamespace(
        get_dog_data=lambda dog_id: (
            dog_payload_with_snapshot if dog_id == "buddy" else dog_payload_without_snapshot
        )
    )
    runtime_data = _runtime_data_with_coordinator(coordinator)

    assert resolve_dog_data(runtime_data, "buddy") == dog_payload_with_snapshot
    assert resolve_dog_data(runtime_data, None) is None
    assert resolve_status_snapshot(runtime_data, "buddy") == direct_snapshot

    fallback_snapshot = resolve_status_snapshot(runtime_data, "max")
    assert fallback_snapshot is not None
    assert fallback_snapshot.get("dog_id") == "max"
    assert fallback_snapshot.get("state") == "at_park"
