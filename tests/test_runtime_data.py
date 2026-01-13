"""Unit tests for runtime data helpers."""
from __future__ import annotations

import importlib.util
import sys
from dataclasses import field
from dataclasses import fields
from dataclasses import make_dataclass
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from typing import cast
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from tests.helpers import install_homeassistant_stubs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _ensure_package(name: str, path: Path) -> ModuleType:
    """Ensure a namespace package exists for dynamic imports."""

    module = sys.modules.get(name)
    if module is None:
        module = ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module
    return module


def _load_module(name: str, path: Path) -> ModuleType:
    """Load ``name`` from ``path`` without importing the package ``__init__``."""

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module {name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_package('custom_components', PROJECT_ROOT / 'custom_components')
_ensure_package(
    'custom_components.pawcontrol',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol',
)

const = _load_module(
    'custom_components.pawcontrol.const',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol' / 'const.py',
)
types_module = _load_module(
    'custom_components.pawcontrol.types',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol' / 'types.py',
)

if TYPE_CHECKING:
    from custom_components.pawcontrol.types import (
        DomainRuntimeStoreEntry as DomainRuntimeStoreEntryType,
    )
    from custom_components.pawcontrol.types import (
        PawControlConfigEntry as PawControlConfigEntryType,
    )
    from custom_components.pawcontrol.types import (
        PawControlRuntimeData as PawControlRuntimeDataType,
    )
else:  # pragma: no cover - runtime aliases for type checkers
    DomainRuntimeStoreEntryType = types_module.DomainRuntimeStoreEntry
    PawControlConfigEntryType = types_module.PawControlConfigEntry
    PawControlRuntimeDataType = types_module.PawControlRuntimeData
install_homeassistant_stubs()
runtime_module = _load_module(
    'custom_components.pawcontrol.runtime_data',
    PROJECT_ROOT / 'custom_components' / 'pawcontrol' / 'runtime_data.py',
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
    """Lightweight stand-in for a Home Assistant config entry."""

    def __init__(self, entry_id: str) -> None:
        self.entry_id = entry_id
        self.domain = DOMAIN
        self.runtime_data: PawControlRuntimeDataType | None = None


@pytest.fixture
def runtime_data() -> PawControlRuntimeDataType:
    """Return a fully initialised runtime data container for tests."""

    return PawControlRuntimeData(
        coordinator=MagicMock(),
        data_manager=MagicMock(),
        notification_manager=MagicMock(),
        feeding_manager=MagicMock(),
        walk_manager=MagicMock(),
        entity_factory=MagicMock(),
        entity_profile='standard',
        dogs=[],
    )


def _entry(entry_id: str = 'test-entry') -> PawControlConfigEntryType:
    """Create a dummy config entry with the given identifier."""

    return cast(PawControlConfigEntryType, _DummyEntry(entry_id))


def _build_hass(
    *,
    data: dict[str, object] | None = None,
    entries: dict[str, PawControlConfigEntryType] | None = None,
) -> SimpleNamespace:
    """Create a Home Assistant stub exposing config entry lookups."""

    store: dict[str, object] = data or {}
    entry_map: dict[str, PawControlConfigEntryType] = entries or {}

    def _async_get_entry(entry_id: str) -> PawControlConfigEntryType | None:
        return entry_map.get(entry_id)

    return SimpleNamespace(
        data=store,
        config_entries=SimpleNamespace(async_get_entry=_async_get_entry),
    )


def test_store_and_get_runtime_data_roundtrip(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should make it retrievable via the helper."""

    entry = _entry()
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)

    assert get_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry.entry_id) is runtime_data


def test_get_runtime_data_ignores_unknown_entries() -> None:
    """Missing entries should return ``None`` without side effects."""

    hass = _build_hass(data={})

    assert get_runtime_data(hass, 'missing') is None


def test_require_runtime_data_returns_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """``require_runtime_data`` should return runtime payloads when present."""

    entry = _entry('configured')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)

    assert require_runtime_data(hass, entry) is runtime_data
    assert require_runtime_data(hass, entry.entry_id) is runtime_data


def test_require_runtime_data_raises_when_missing() -> None:
    """``require_runtime_data`` should raise when no payload can be found."""

    entry = _entry('missing')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    with pytest.raises(RuntimeDataUnavailableError):
        require_runtime_data(hass, entry)

    with pytest.raises(RuntimeDataUnavailableError):
        require_runtime_data(hass, entry.entry_id)


def test_get_runtime_data_with_unexpected_container_type(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Non-mapping containers are treated as absent data."""

    entry = _entry('recovered')
    hass = _build_hass(
        data={DOMAIN: []},
        entries={entry.entry_id: entry},
    )

    assert get_runtime_data(hass, 'legacy') is None
    # The invalid container should be cleaned up entirely so future lookups do
    # not keep encountering the bad structure.
    assert DOMAIN not in hass.data

    # After storing data the invalid container should be replaced with a mapping.
    store_runtime_data(hass, entry, runtime_data)
    assert DOMAIN in hass.data
    assert get_runtime_data(hass, entry.entry_id) is runtime_data


def test_get_runtime_data_resolves_store_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries should unwrap to runtime data."""

    entry = _entry('store-entry')
    hass = _build_hass(
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(runtime_data=runtime_data)
            }
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is runtime_data
    assert getattr(entry, 'runtime_data', None) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_get_runtime_data_repopulates_store_from_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entries with runtime data should repopulate the hass.data cache."""

    entry = _entry('repopulate-store')
    entry.runtime_data = runtime_data
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    assert get_runtime_data(hass, entry) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_get_runtime_data_replaces_invalid_store_when_entry_present(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Invalid domain stores should be replaced when an entry has data."""

    entry = _entry('replace-store')
    entry.runtime_data = runtime_data
    hass = _build_hass(entries={entry.entry_id: entry}, data={DOMAIN: []})

    assert get_runtime_data(hass, entry) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_get_runtime_data_handles_plain_runtime_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy payloads storing runtime data directly should remain compatible."""

    entry = _entry('plain-runtime')
    hass = _build_hass(
        data={DOMAIN: {entry.entry_id: runtime_data}},
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_get_runtime_data_resolves_mapping_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Dict-based store entries should unwrap to runtime data."""

    entry = _entry('mapping-entry')
    hass = _build_hass(
        data={
            DOMAIN: {
                entry.entry_id: {
                    'runtime_data': runtime_data,
                    'version': DomainRuntimeStoreEntryType.MINIMUM_COMPATIBLE_VERSION,
                }
            }
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_pop_runtime_data_removes_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Popping runtime data should remove the stored value."""

    entry = _entry('pop-entry')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)
    assert pop_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry) is None


def test_pop_runtime_data_handles_store_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries should be returned and removed by ``pop``."""

    hass = _build_hass(
        data={
            DOMAIN: {'stored': DomainRuntimeStoreEntryType(runtime_data=runtime_data)}
        }
    )

    assert pop_runtime_data(hass, 'stored') is runtime_data
    assert DOMAIN not in hass.data


def test_pop_runtime_data_cleans_up_domain_store(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Removing the final entry should drop the PawControl data namespace."""

    hass = _build_hass(
        data={DOMAIN: {'entry': DomainRuntimeStoreEntryType(runtime_data)}},
    )

    assert pop_runtime_data(hass, 'entry') is runtime_data
    assert DOMAIN not in hass.data


def test_cleanup_domain_store_removes_empty_store() -> None:
    """Cleanup helper should remove empty PawControl namespaces."""

    hass = _build_hass(data={DOMAIN: {}})

    _cleanup_domain_store(hass, hass.data[DOMAIN])

    assert DOMAIN not in hass.data


def test_pop_runtime_data_returns_none_when_store_missing() -> None:
    """Popping runtime data from an empty store should return ``None``."""

    hass = _build_hass(data={})

    assert pop_runtime_data(hass, 'missing') is None


def test_describe_runtime_store_status_missing() -> None:
    """A missing entry should report unavailable runtime store metadata."""

    hass = _build_hass(entries={}, data={})

    snapshot = describe_runtime_store_status(hass, 'unknown')

    assert snapshot['status'] == 'missing'
    assert snapshot['entry']['status'] == 'missing'
    assert snapshot['store']['status'] == 'missing'
    assert snapshot['divergence_detected'] is False


def test_describe_runtime_store_status_current(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should report a current snapshot."""

    entry = _entry('runtime-store-current')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)

    snapshot = describe_runtime_store_status(hass, entry)

    assert snapshot['status'] == 'current'
    assert snapshot['entry']['status'] == 'current'
    assert snapshot['store']['status'] == 'current'
    assert snapshot['divergence_detected'] is False


def test_describe_runtime_store_status_needs_migration(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entries without stamped metadata should require migration."""

    entry = _entry('runtime-store-needs-migration')
    entry.runtime_data = runtime_data
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    snapshot = describe_runtime_store_status(hass, entry)

    assert snapshot['status'] == 'needs_migration'
    assert snapshot['entry']['status'] == 'unstamped'
    assert snapshot['store']['status'] == 'missing'


def test_describe_runtime_store_status_detached_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Store entries without config entry adoption should be flagged."""

    entry = _entry('runtime-store-detached-entry')
    hass = _build_hass(
        entries={entry.entry_id: entry},
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(runtime_data=runtime_data)
            }
        },
    )

    snapshot = describe_runtime_store_status(hass, entry)

    assert snapshot['status'] == 'detached_entry'
    assert snapshot['entry']['status'] == 'missing'
    assert snapshot['store']['status'] == 'current'


def test_describe_runtime_store_status_future_incompatible(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Future schema versions should be reported as incompatible."""

    entry = _entry('runtime-store-future')
    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1

    hass = _build_hass(entries={entry.entry_id: entry}, data={})
    entry.runtime_data = runtime_data
    entry._pawcontrol_runtime_store_version = future_version
    entry._pawcontrol_runtime_store_created_version = future_version

    hass.data[DOMAIN] = {
        entry.entry_id: DomainRuntimeStoreEntryType(
            runtime_data=runtime_data,
            version=future_version,
            created_version=future_version,
        )
    }

    snapshot = describe_runtime_store_status(hass, entry)

    assert snapshot['status'] == 'future_incompatible'
    assert snapshot['entry']['status'] == 'future_incompatible'
    assert snapshot['store']['status'] == 'future_incompatible'


def test_describe_runtime_store_status_detects_divergence(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Different runtime payload objects should trigger divergence reporting."""

    entry = _entry('runtime-store-divergence')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    other_runtime = PawControlRuntimeDataType(
        coordinator=runtime_data.coordinator,
        data_manager=runtime_data.data_manager,
        notification_manager=runtime_data.notification_manager,
        feeding_manager=runtime_data.feeding_manager,
        walk_manager=runtime_data.walk_manager,
        entity_factory=runtime_data.entity_factory,
        entity_profile=runtime_data.entity_profile,
        dogs=runtime_data.dogs,
    )

    entry.runtime_data = runtime_data
    entry._pawcontrol_runtime_store_version = (
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    entry._pawcontrol_runtime_store_created_version = (
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    hass.data[DOMAIN] = {
        entry.entry_id: DomainRuntimeStoreEntryType(runtime_data=other_runtime)
    }

    snapshot = describe_runtime_store_status(hass, entry)

    assert snapshot['status'] == 'diverged'
    assert snapshot['entry']['status'] == 'current'
    assert snapshot['store']['status'] == 'current'
    assert snapshot['divergence_detected'] is True


def test_store_runtime_data_records_current_version(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Stored entries should advertise the current schema version."""

    entry = _entry('versioned-entry')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION


def test_runtime_data_roundtrip_survives_module_reload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Runtime data stored from a previous module load should still resolve."""

    entry = _entry('reloaded-entry')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    reloaded_cls = make_dataclass(
        'PawControlRuntimeData',
        [(field.name, object) for field in fields(PawControlRuntimeData)],
    )
    reloaded_cls.__module__ = PawControlRuntimeData.__module__

    reloaded_instance = reloaded_cls(
        **{
            field.name: getattr(runtime_data, field.name)
            for field in fields(PawControlRuntimeData)
        }
    )

    entry.runtime_data = cast(PawControlRuntimeDataType, reloaded_instance)

    assert get_runtime_data(hass, entry) is reloaded_instance


def test_store_entry_handles_reloaded_dataclass(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Domain store entries created before reload should remain compatible."""

    entry = _entry('store-reloaded')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    reloaded_runtime_cls = make_dataclass(
        'PawControlRuntimeData',
        [(field.name, object) for field in fields(PawControlRuntimeData)],
    )
    reloaded_runtime_cls.__module__ = PawControlRuntimeData.__module__

    reloaded_instance = reloaded_runtime_cls(
        **{
            field.name: getattr(runtime_data, field.name)
            for field in fields(PawControlRuntimeData)
        }
    )

    reloaded_store_cls = make_dataclass(
        'DomainRuntimeStoreEntry',
        [
            ('runtime_data', object),
            (
                'version',
                int,
                field(default=DomainRuntimeStoreEntryType.CURRENT_VERSION),
            ),
        ],
    )
    reloaded_store_cls.__module__ = DomainRuntimeStoreEntryType.__module__

    store_payload = reloaded_store_cls(
        runtime_data=cast(PawControlRuntimeDataType, reloaded_instance),
    )

    hass.data[DOMAIN] = {entry.entry_id: store_payload}
    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is reloaded_instance

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert isinstance(persisted, DomainRuntimeStoreEntryType)
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is reloaded_instance


def test_get_runtime_data_upgrades_outdated_version(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy store entries should be stamped with the current schema version."""

    entry = _entry('outdated-version')
    hass = _build_hass(
        data={
            DOMAIN: {
                entry.entry_id: {
                    'runtime_data': runtime_data,
                    'version': 0,
                }
            }
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is runtime_data

    store = cast(dict[str, DomainRuntimeStoreEntryType], hass.data[DOMAIN])
    persisted = store[entry.entry_id]
    assert persisted.version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.created_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert persisted.runtime_data is runtime_data


def test_get_runtime_data_future_schema_returns_none(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Future schema versions should be treated as incompatible."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1
    entry = _entry('future-schema')
    hass = _build_hass(
        data={
            DOMAIN: {
                entry.entry_id: {
                    'runtime_data': runtime_data,
                    'version': future_version,
                    'created_version': future_version,
                }
            }
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    assert get_runtime_data(hass, entry.entry_id) is None
    assert DOMAIN not in hass.data
    assert getattr(entry, 'runtime_data', None) is None


def test_require_runtime_data_raises_on_future_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """``require_runtime_data`` should fail fast for future schemas."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 2
    entry = _entry('require-future')
    hass = _build_hass(
        data={
            DOMAIN: {
                entry.entry_id: {
                    'runtime_data': runtime_data,
                    'version': future_version,
                    'created_version': future_version,
                }
            }
        },
        entries={entry.entry_id: entry},
    )

    entry.runtime_data = None

    with pytest.raises(RuntimeDataIncompatibleError):
        require_runtime_data(hass, entry.entry_id)

    assert DOMAIN not in hass.data


def test_store_runtime_data_sets_entry_metadata(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data should stamp metadata on the entry."""

    entry = _entry('metadata-stamp')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)

    assert entry._pawcontrol_runtime_store_version == (
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    assert entry._pawcontrol_runtime_store_created_version == (
        DomainRuntimeStoreEntryType.CURRENT_VERSION
    )
    assert runtime_data.schema_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert (
        runtime_data.schema_created_version
        == DomainRuntimeStoreEntryType.CURRENT_VERSION
    )


def test_store_runtime_data_rejects_future_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Storing runtime data with a future schema should raise."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1
    runtime_data.schema_version = future_version
    runtime_data.schema_created_version = future_version

    entry = _entry('future-runtime-schema')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    with pytest.raises(RuntimeDataIncompatibleError):
        store_runtime_data(hass, entry, runtime_data)


def test_get_runtime_data_detects_future_entry_metadata(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Entry metadata indicating a future schema should reset the cache."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 1
    entry = _entry('future-metadata')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    entry.runtime_data = runtime_data
    entry._pawcontrol_runtime_store_version = future_version
    entry._pawcontrol_runtime_store_created_version = future_version

    assert get_runtime_data(hass, entry.entry_id) is None
    assert getattr(entry, 'runtime_data', None) is None
    assert entry._pawcontrol_runtime_store_version is None
    assert entry._pawcontrol_runtime_store_created_version is None


def test_get_runtime_data_upgrades_legacy_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy runtime payloads without schema metadata should upgrade in-place."""

    entry = _entry('legacy-runtime-schema')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    delattr(runtime_data, 'schema_version')
    delattr(runtime_data, 'schema_created_version')
    entry.runtime_data = runtime_data

    resolved = get_runtime_data(hass, entry.entry_id)
    assert resolved is runtime_data
    assert runtime_data.schema_version == DomainRuntimeStoreEntryType.CURRENT_VERSION
    assert (
        runtime_data.schema_created_version
        == DomainRuntimeStoreEntryType.CURRENT_VERSION
    )


def test_get_runtime_data_detects_future_runtime_schema(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Runtime payloads stamped with future schemas should be rejected."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 2
    runtime_data.schema_version = future_version
    runtime_data.schema_created_version = future_version

    entry = _entry('future-runtime-schema-entry')
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    entry.runtime_data = runtime_data

    assert get_runtime_data(hass, entry.entry_id) is None
    assert getattr(entry, 'runtime_data', None) is None


def test_get_runtime_data_detects_future_runtime_schema_in_store(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Store entries with future runtime schemas should be dropped."""

    future_version = DomainRuntimeStoreEntryType.CURRENT_VERSION + 3
    runtime_data.schema_version = future_version
    runtime_data.schema_created_version = future_version

    entry = _entry('future-runtime-store')
    hass = _build_hass(
        entries={entry.entry_id: entry},
        data={
            DOMAIN: {
                entry.entry_id: DomainRuntimeStoreEntryType(
                    runtime_data=runtime_data,
                    version=DomainRuntimeStoreEntryType.CURRENT_VERSION,
                    created_version=DomainRuntimeStoreEntryType.CURRENT_VERSION,
                )
            }
        },
    )

    assert get_runtime_data(hass, entry.entry_id) is None
    domain_store = hass.data.get(DOMAIN)
    if isinstance(domain_store, dict):
        assert entry.entry_id not in domain_store
