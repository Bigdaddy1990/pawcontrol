"""Unit tests for runtime data helpers."""

from dataclasses import field, fields, make_dataclass
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

from tests.helpers import install_homeassistant_stubs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> ModuleType:
    """Ensure a namespace package exists for dynamic imports."""  # noqa: E111

    module = sys.modules.get(name)  # noqa: E111
    if module is None:  # noqa: E111
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module  # noqa: E111


def _load_module(name: str, path: Path) -> ModuleType:
    """Load ``name`` from ``path`` without importing the package ``__init__``."""  # noqa: E111

    spec = importlib.util.spec_from_file_location(name, path)  # noqa: E111
    if spec is None or spec.loader is None:  # noqa: E111
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)  # noqa: E111
    sys.modules[name] = module  # noqa: E111
    spec.loader.exec_module(module)  # noqa: E111
    return module  # noqa: E111


_ensure_package("custom_components", PROJECT_ROOT / "custom_components")
_ensure_package(
    "custom_components.pawcontrol",
    PROJECT_ROOT / "custom_components" / "pawcontrol",
)

const = _load_module(
    "custom_components.pawcontrol.const",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "const.py",
)
types_module = _load_module(
    "custom_components.pawcontrol.types",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "types.py",
)

if TYPE_CHECKING:
    from custom_components.pawcontrol.types import (  # noqa: E111
        DomainRuntimeStoreEntry as DomainRuntimeStoreEntryType,
        PawControlConfigEntry as PawControlConfigEntryType,
        PawControlRuntimeData as PawControlRuntimeDataType,
    )
else:  # pragma: no cover - runtime aliases for type checkers
    DomainRuntimeStoreEntryType = types_module.DomainRuntimeStoreEntry  # noqa: E111
    PawControlConfigEntryType = types_module.PawControlConfigEntry  # noqa: E111
    PawControlRuntimeDataType = types_module.PawControlRuntimeData  # noqa: E111
install_homeassistant_stubs()
runtime_module = _load_module(
    "custom_components.pawcontrol.runtime_data",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "runtime_data.py",
)

DOMAIN = const.DOMAIN
PawControlRuntimeData = types_module.PawControlRuntimeData
PawControlConfigEntry = types_module.PawControlConfigEntry
store_runtime_data = runtime_module.store_runtime_data
get_runtime_data = runtime_module.get_runtime_data
require_runtime_data = runtime_module.require_runtime_data
RuntimeDataUnavailableError = runtime_module.RuntimeDataUnavailableError
RuntimeDataIncompatibleError = runtime_module.RuntimeDataIncompatibleError
pop_runtime_data = runtime_module.pop_runtime_data
_cleanup_domain_store = runtime_module._cleanup_domain_store
describe_runtime_store_status = runtime_module.describe_runtime_store_status


class _DummyEntry:
    """Lightweight stand-in for a Home Assistant config entry."""  # noqa: E111

    def __init__(self, entry_id: str) -> None:  # noqa: E111
        self.entry_id = entry_id
        self.domain = DOMAIN
        self.runtime_data: PawControlRuntimeDataType | None = None


@pytest.fixture
def runtime_data() -> PawControlRuntimeDataType:
    """Return a fully initialised runtime data container for tests."""  # noqa: E111

    return PawControlRuntimeData(  # noqa: E111
        coordinator=MagicMock(),
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile="standard",
        dogs=[],
    )


def _entry(entry_id: str = "test-entry") -> PawControlConfigEntryType:
    """Create a dummy config entry with the given identifier."""  # noqa: E111

    return cast(PawControlConfigEntryType, _DummyEntry(entry_id))  # noqa: E111


def _build_hass(
    *,
    data: dict[str, object] | None = None,
    entries: dict[str, PawControlConfigEntryType] | None = None,
) -> SimpleNamespace:
    """Create a Home Assistant stub exposing config entry lookups."""  # noqa: E111

    store: dict[str, object] = data or {}  # noqa: E111
    entry_map: dict[str, PawControlConfigEntryType] = entries or {}  # noqa: E111

    def _async_get_entry(entry_id: str) -> PawControlConfigEntryType | None:  # noqa: E111
        return entry_map.get(entry_id)

    return SimpleNamespace(  # noqa: E111
        data=store,
        config_entries=SimpleNamespace(async_get_entry=_async_get_entry),
    )


def test_store_and_get_runtime_data_roundtrip(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should make it retrievable via the helper."""  # noqa: E111

    entry = _entry()  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111

    assert get_runtime_data(hass, entry) is runtime_data  # noqa: E111
    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111


def test_get_runtime_data_ignores_unknown_entries() -> None:
    """Missing entries should return ``None`` without side effects."""  # noqa: E111

    hass = _build_hass(data={})  # noqa: E111

    assert get_runtime_data(hass, "missing") is None  # noqa: E111


def test_require_runtime_data_returns_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """``require_runtime_data`` should return runtime payloads when present."""  # noqa: E111

    entry = _entry("configured")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111

    assert require_runtime_data(hass, entry) is runtime_data  # noqa: E111
    assert require_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111


def test_require_runtime_data_raises_when_missing() -> None:
    """``require_runtime_data`` should raise when no payload can be found."""  # noqa: E111

    entry = _entry("missing")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    with pytest.raises(RuntimeDataUnavailableError):  # noqa: E111
        require_runtime_data(hass, entry)

    with pytest.raises(RuntimeDataUnavailableError):  # noqa: E111
        require_runtime_data(hass, entry.entry_id)


def test_get_runtime_data_with_unexpected_container_type(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Non-mapping containers are treated as absent data."""  # noqa: E111

    entry = _entry("recovered")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={DOMAIN: []},
        entries={entry.entry_id: entry},
    )

    assert get_runtime_data(hass, "legacy") is None  # noqa: E111
    # The invalid container should be cleaned up entirely so future lookups do  # noqa: E114, E501
    # not keep encountering the bad structure.  # noqa: E114
    assert DOMAIN not in hass.data  # noqa: E111

    # After storing data the invalid container should be replaced with a mapping.  # noqa: E114, E501
    store_runtime_data(hass, entry, runtime_data)  # noqa: E111
    assert DOMAIN in hass.data  # noqa: E111
    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111


def test_get_runtime_data_resolves_store_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries should unwrap to runtime data."""  # noqa: E111

    entry = _entry("store-entry")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(
                    runtime_data=runtime_data,
                ),
            },
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111
    assert getattr(entry, "runtime_data", None) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_get_runtime_data_repopulates_store_from_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entries with runtime data should repopulate the hass.data cache."""  # noqa: E111

    entry = _entry("repopulate-store")  # noqa: E111
    entry.runtime_data = runtime_data  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    assert get_runtime_data(hass, entry) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_get_runtime_data_replaces_invalid_store_when_entry_present(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Invalid domain stores should be replaced when an entry has data."""  # noqa: E111

    entry = _entry("replace-store")  # noqa: E111
    entry.runtime_data = runtime_data  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={DOMAIN: []})  # noqa: E111

    assert get_runtime_data(hass, entry) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_get_runtime_data_handles_plain_runtime_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy payloads storing runtime data directly should remain compatible."""  # noqa: E111

    entry = _entry("plain-runtime")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={DOMAIN: {entry.entry_id: runtime_data}},
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_get_runtime_data_resolves_mapping_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Dict-based store entries should unwrap to runtime data."""  # noqa: E111

    entry = _entry("mapping-entry")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                entry.entry_id: {
                    "runtime_data": runtime_data,
                    "version": DomainRuntimeStoreEntryType.MINIMUM_COMPATIBLE_VERSION,
                },
            },
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_pop_runtime_data_removes_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Popping runtime data should remove the stored value."""  # noqa: E111

    entry = _entry("pop-entry")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111
    assert pop_runtime_data(hass, entry) is runtime_data  # noqa: E111
    assert get_runtime_data(hass, entry) is None  # noqa: E111


def test_pop_runtime_data_handles_store_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries should be returned and removed by ``pop``."""  # noqa: E111

    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                "stored": DomainRuntimeStoreEntryType(
                    runtime_data=runtime_data,
                ),
            },
        },
    )

    assert pop_runtime_data(hass, "stored") is runtime_data  # noqa: E111
    assert DOMAIN not in hass.data  # noqa: E111


def test_pop_runtime_data_cleans_up_domain_store(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Removing the final entry should drop the PawControl data namespace."""  # noqa: E111

    hass = _build_hass(  # noqa: E111
        data={DOMAIN: {"entry": DomainRuntimeStoreEntryType(runtime_data)}},
    )

    assert pop_runtime_data(hass, "entry") is runtime_data  # noqa: E111
    assert DOMAIN not in hass.data  # noqa: E111


def test_cleanup_domain_store_removes_empty_store() -> None:
    """Cleanup helper should remove empty PawControl namespaces."""  # noqa: E111

    hass = _build_hass(data={DOMAIN: {}})  # noqa: E111

    _cleanup_domain_store(hass, hass.data[DOMAIN])  # noqa: E111

    assert DOMAIN not in hass.data  # noqa: E111


def test_pop_runtime_data_returns_none_when_store_missing() -> None:
    """Popping runtime data from an empty store should return ``None``."""  # noqa: E111

    hass = _build_hass(data={})  # noqa: E111

    assert pop_runtime_data(hass, "missing") is None  # noqa: E111


def test_describe_runtime_store_status_missing() -> None:
    """A missing entry should report unavailable runtime store metadata."""  # noqa: E111

    hass = _build_hass(entries={}, data={})  # noqa: E111

    snapshot = describe_runtime_store_status(hass, "unknown")  # noqa: E111

    assert snapshot["status"] == "missing"  # noqa: E111
    assert snapshot["entry"]["status"] == "missing"  # noqa: E111
    assert snapshot["store"]["status"] == "missing"  # noqa: E111
    assert snapshot["divergence_detected"] is False  # noqa: E111


def test_describe_runtime_store_status_current(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should report a current snapshot."""  # noqa: E111

    entry = _entry("runtime-store-current")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111

    snapshot = describe_runtime_store_status(hass, entry)  # noqa: E111

    assert snapshot["status"] == "current"  # noqa: E111
    assert snapshot["entry"]["status"] == "current"  # noqa: E111
    assert snapshot["store"]["status"] == "current"  # noqa: E111
    assert snapshot["divergence_detected"] is False  # noqa: E111


def test_describe_runtime_store_status_needs_migration(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entries without stamped metadata should require migration."""  # noqa: E111

    entry = _entry("runtime-store-needs-migration")  # noqa: E111
    entry.runtime_data = runtime_data  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    snapshot = describe_runtime_store_status(hass, entry)  # noqa: E111

    assert snapshot["status"] == "needs_migration"  # noqa: E111
    assert snapshot["entry"]["status"] == "unstamped"  # noqa: E111
    assert snapshot["store"]["status"] == "missing"  # noqa: E111


def test_describe_runtime_store_status_detached_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Store entries without config entry adoption should be flagged."""  # noqa: E111

    entry = _entry("runtime-store-detached-entry")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        entries={entry.entry_id: entry},
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(
                    runtime_data=runtime_data,
                ),
            },
        },
    )

    snapshot = describe_runtime_store_status(hass, entry)  # noqa: E111

    assert snapshot["status"] == "detached_entry"  # noqa: E111
    assert snapshot["entry"]["status"] == "missing"  # noqa: E111
    assert snapshot["store"]["status"] == "current"  # noqa: E111


def test_describe_runtime_store_status_future_incompatible(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Future schema versions should be reported as incompatible."""  # noqa: E111

    entry = _entry("runtime-store-future")  # noqa: E111
    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1  # noqa: E111

    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111
    entry.runtime_data = runtime_data  # noqa: E111
    entry._pawcontrol_runtime_store_version = future_version  # noqa: E111
    entry._pawcontrol_runtime_store_created_version = future_version  # noqa: E111

    hass.data[DOMAIN] = {  # noqa: E111
        entry.entry_id: DomainRuntimeStoreEntryType(
            runtime_data=runtime_data,
            version=future_version,
            created_version=future_version,
        ),
    }

    snapshot = describe_runtime_store_status(hass, entry)  # noqa: E111

    assert snapshot["status"] == "future_incompatible"  # noqa: E111
    assert snapshot["entry"]["status"] == "future_incompatible"  # noqa: E111
    assert snapshot["store"]["status"] == "future_incompatible"  # noqa: E111


def test_describe_runtime_store_status_detects_divergence(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Different runtime payload objects should trigger divergence reporting."""  # noqa: E111

    entry = _entry("runtime-store-divergence")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    other_runtime = PawControlRuntimeDataType(  # noqa: E111
        coordinator=runtime_data.coordinator,
        data_manager=runtime_data.data_manager,
        notification_manager=runtime_data.notification_manager,
        feeding_manager=runtime_data.feeding_manager,
        walk_manager=runtime_data.walk_manager,
        entity_factory=runtime_data.entity_factory,
        entity_profile=runtime_data.entity_profile,
        dogs=runtime_data.dogs,
    )

    entry.runtime_data = runtime_data  # noqa: E111
    entry._pawcontrol_runtime_store_version = (
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )  # noqa: E111
    entry._pawcontrol_runtime_store_created_version = (  # noqa: E111
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    hass.data[DOMAIN] = {  # noqa: E111
        entry.entry_id: DomainRuntimeStoreEntryType(runtime_data=other_runtime),
    }

    snapshot = describe_runtime_store_status(hass, entry)  # noqa: E111

    assert snapshot["status"] == "diverged"  # noqa: E111
    assert snapshot["entry"]["status"] == "current"  # noqa: E111
    assert snapshot["store"]["status"] == "current"  # noqa: E111
    assert snapshot["divergence_detected"] is True  # noqa: E111


def test_store_runtime_data_records_current_version(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Stored entries should advertise the current schema version."""  # noqa: E111

    entry = _entry("versioned-entry")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111


def test_runtime_data_roundtrip_survives_module_reload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Runtime data stored from a previous module load should still resolve."""  # noqa: E111

    entry = _entry("reloaded-entry")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    reloaded_cls = make_dataclass(  # noqa: E111
        "PawControlRuntimeData",
        [(field.name, object) for field in fields(PawControlRuntimeData)],
    )
    reloaded_cls.__module__ = PawControlRuntimeData.__module__  # noqa: E111

    reloaded_instance = reloaded_cls(  # noqa: E111
        **{
            field.name: getattr(runtime_data, field.name)
            for field in fields(PawControlRuntimeData)
        },
    )

    entry.runtime_data = cast(PawControlRuntimeDataType, reloaded_instance)  # noqa: E111

    assert get_runtime_data(hass, entry) is reloaded_instance  # noqa: E111


def test_store_entry_handles_reloaded_dataclass(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries created before reload should remain compatible."""  # noqa: E111

    entry = _entry("store-reloaded")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    reloaded_runtime_cls = make_dataclass(  # noqa: E111
        "PawControlRuntimeData",
        [(field.name, object) for field in fields(PawControlRuntimeData)],
    )
    reloaded_runtime_cls.__module__ = PawControlRuntimeData.__module__  # noqa: E111

    reloaded_instance = reloaded_runtime_cls(  # noqa: E111
        **{
            field.name: getattr(runtime_data, field.name)
            for field in fields(PawControlRuntimeData)
        },
    )

    reloaded_store_cls = make_dataclass(  # noqa: E111
        "DomainRuntimeStoreEntry",
        [
            ("runtime_data", object),
            (
                "version",
                int,
                field(default=DomainRuntimeStoreEntryType.CURRENT_VERSION),
            ),
        ],
    )
    reloaded_store_cls.__module__ = DomainRuntimeStoreEntryType.__module__  # noqa: E111

    store_payload = reloaded_store_cls(  # noqa: E111
        runtime_data=cast(PawControlRuntimeDataType, reloaded_instance),
    )

    hass.data[DOMAIN] = {entry.entry_id: store_payload}  # noqa: E111
    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is reloaded_instance  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert isinstance(persisted, DomainRuntimeStoreEntryType)  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is reloaded_instance  # noqa: E111


def test_get_runtime_data_upgrades_outdated_version(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy store entries should be stamped with the current schema version."""  # noqa: E111

    entry = _entry("outdated-version")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                entry.entry_id: {
                    "runtime_data": runtime_data,
                    "version": 0,
                },
            },
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is runtime_data  # noqa: E111

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])  # noqa: E111
    persisted = store[entry.entry_id]  # noqa: E111
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert persisted.runtime_data is runtime_data  # noqa: E111


def test_get_runtime_data_future_schema_returns_none(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Future schema versions should be treated as incompatible."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1  # noqa: E111
    entry = _entry("future-schema")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                entry.entry_id: {
                    "runtime_data": runtime_data,
                    "version": future_version,
                    "created_version": future_version,
                },
            },
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is None  # noqa: E111
    assert DOMAIN not in hass.data  # noqa: E111
    assert getattr(entry, "runtime_data", None) is None  # noqa: E111


def test_require_runtime_data_raises_on_future_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """``require_runtime_data`` should fail fast for future schemas."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 2  # noqa: E111
    entry = _entry("require-future")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        data={
            DOMAIN: {
                entry.entry_id: {
                    "runtime_data": runtime_data,
                    "version": future_version,
                    "created_version": future_version,
                },
            },
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None  # noqa: E111

    with pytest.raises(RuntimeDataIncompatibleError):  # noqa: E111
        require_runtime_data(hass, entry.entry_id)

    assert DOMAIN not in hass.data  # noqa: E111


def test_store_runtime_data_sets_entry_metadata(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should stamp metadata on the entry."""  # noqa: E111

    entry = _entry("metadata-stamp")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    store_runtime_data(hass, entry, runtime_data)  # noqa: E111

    assert entry._pawcontrol_runtime_store_version == (  # noqa: E111
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    assert entry._pawcontrol_runtime_store_created_version == (  # noqa: E111
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    assert runtime_data.schema_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert (  # noqa: E111
        runtime_data.schema_created_version
        == DomainRuntimeStoreEntryType.CURRENT_VERSION
    )


def test_store_runtime_data_rejects_future_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data with a future schema should raise."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1  # noqa: E111
    runtime_data.schema_version = future_version  # noqa: E111
    runtime_data.schema_created_version = future_version  # noqa: E111

    entry = _entry("future-runtime-schema")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    with pytest.raises(RuntimeDataIncompatibleError):  # noqa: E111
        store_runtime_data(hass, entry, runtime_data)


def test_get_runtime_data_detects_future_entry_metadata(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entry metadata indicating a future schema should reset the cache."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1  # noqa: E111
    entry = _entry("future-metadata")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    entry.runtime_data = runtime_data  # noqa: E111
    entry._pawcontrol_runtime_store_version = future_version  # noqa: E111
    entry._pawcontrol_runtime_store_created_version = future_version  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is None  # noqa: E111
    assert getattr(entry, "runtime_data", None) is None  # noqa: E111
    assert entry._pawcontrol_runtime_store_version is None  # noqa: E111
    assert entry._pawcontrol_runtime_store_created_version is None  # noqa: E111


def test_get_runtime_data_upgrades_legacy_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy runtime payloads without schema metadata should upgrade in-place."""  # noqa: E111

    entry = _entry("legacy-runtime-schema")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    delattr(runtime_data, "schema_version")  # noqa: E111
    delattr(runtime_data, "schema_created_version")  # noqa: E111
    entry.runtime_data = runtime_data  # noqa: E111

    resolved = get_runtime_data(hass, entry.entry_id)  # noqa: E111
    assert resolved is runtime_data  # noqa: E111
    assert runtime_data.schema_version == DomainRuntimeStoreEntryType.CURRENT_VERSION  # noqa: E111
    assert (  # noqa: E111
        runtime_data.schema_created_version
        == DomainRuntimeStoreEntryType.CURRENT_VERSION
    )


def test_get_runtime_data_detects_future_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Runtime payloads stamped with future schemas should be rejected."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 2  # noqa: E111
    runtime_data.schema_version = future_version  # noqa: E111
    runtime_data.schema_created_version = future_version  # noqa: E111

    entry = _entry("future-runtime-schema-entry")  # noqa: E111
    hass = _build_hass(entries={entry.entry_id: entry}, data={})  # noqa: E111

    entry.runtime_data = runtime_data  # noqa: E111

    assert get_runtime_data(hass, entry.entry_id) is None  # noqa: E111
    assert getattr(entry, "runtime_data", None) is None  # noqa: E111


def test_get_runtime_data_detects_future_runtime_schema_in_store(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Store entries with future runtime schemas should be dropped."""  # noqa: E111

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 3  # noqa: E111
    runtime_data.schema_version = future_version  # noqa: E111
    runtime_data.schema_created_version = future_version  # noqa: E111

    entry = _entry("future-runtime-store")  # noqa: E111
    hass = _build_hass(  # noqa: E111
        entries={entry.entry_id: entry},
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(
                    runtime_data=runtime_data,
                    version=DomainRuntimeStoreEntryType.CURRENT_VERSION,
                    created_version=DomainRuntimeStoreEntryType.CURRENT_VERSION,
                ),
            },
        },
    )

    assert get_runtime_data(hass, entry.entry_id) is None  # noqa: E111
    domain_store = hass.data.get(DOMAIN)  # noqa: E111
    if isinstance(domain_store, dict):  # noqa: E111
        assert entry.entry_id not in domain_store
