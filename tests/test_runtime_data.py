"""Unit tests for runtime data helpers."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import fields, make_dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest

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


def _install_homeassistant_stub() -> None:
    """Register lightweight stubs for the Home Assistant modules we use."""

    if "homeassistant.core" in sys.modules:
        return

    homeassistant = ModuleType("homeassistant")
    sys.modules.setdefault("homeassistant", homeassistant)

    core = ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - simple attribute container
        def __init__(self) -> None:
            self.data: dict[str, object] = {}

    core.HomeAssistant = HomeAssistant  # type: ignore[attr-defined]
    sys.modules["homeassistant.core"] = core


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
    from custom_components.pawcontrol.types import (
        LegacyRuntimeStorePayload as LegacyRuntimeStorePayloadType,
    )
    from custom_components.pawcontrol.types import (
        PawControlConfigEntry as PawControlConfigEntryType,
    )
    from custom_components.pawcontrol.types import (
        PawControlRuntimeData as PawControlRuntimeDataType,
    )
else:  # pragma: no cover - runtime aliases for type checkers
    LegacyRuntimeStorePayloadType = types_module.LegacyRuntimeStorePayload
    PawControlConfigEntryType = types_module.PawControlConfigEntry
    PawControlRuntimeDataType = types_module.PawControlRuntimeData
_install_homeassistant_stub()
runtime_module = _load_module(
    "custom_components.pawcontrol.runtime_data",
    PROJECT_ROOT / "custom_components" / "pawcontrol" / "runtime_data.py",
)

DOMAIN = const.DOMAIN
PawControlRuntimeData = types_module.PawControlRuntimeData
PawControlConfigEntry = types_module.PawControlConfigEntry
store_runtime_data = runtime_module.store_runtime_data
get_runtime_data = runtime_module.get_runtime_data
pop_runtime_data = runtime_module.pop_runtime_data
_coerce_runtime_data = runtime_module._coerce_runtime_data
_cleanup_domain_store = runtime_module._cleanup_domain_store


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
        entity_profile="standard",
        dogs=[],
    )


def _entry(entry_id: str = "test-entry") -> PawControlConfigEntryType:
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


def test_get_runtime_data_handles_legacy_container(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy dict containers should still be unwrapped."""

    entry = _entry("legacy")
    legacy_payload: LegacyRuntimeStorePayloadType = {"runtime_data": runtime_data}
    hass = _build_hass(
        data={DOMAIN: {entry.entry_id: legacy_payload}},
        entries={entry.entry_id: entry},
    )

    assert get_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry.entry_id) is runtime_data
    assert getattr(entry, "runtime_data", None) is runtime_data
    assert DOMAIN not in hass.data


def test_get_runtime_data_ignores_unknown_entries() -> None:
    """Missing entries should return ``None`` without side effects."""

    hass = _build_hass(data={})

    assert get_runtime_data(hass, "missing") is None


def test_get_runtime_data_with_unexpected_container_type(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Non-mapping containers are treated as absent data."""

    entry = _entry("recovered")
    hass = _build_hass(
        data={DOMAIN: []},
        entries={entry.entry_id: entry},
    )

    assert get_runtime_data(hass, "legacy") is None
    # The invalid container should be cleaned up entirely so future lookups do
    # not keep encountering the bad structure.
    assert DOMAIN not in hass.data

    # After storing data the invalid container should be replaced with a mapping.
    store_runtime_data(hass, entry, runtime_data)
    assert DOMAIN not in hass.data
    assert get_runtime_data(hass, entry.entry_id) is runtime_data


def test_pop_runtime_data_removes_entry(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Popping runtime data should remove the stored value."""

    entry = _entry("pop-entry")
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    store_runtime_data(hass, entry, runtime_data)
    assert pop_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry) is None


def test_pop_runtime_data_handles_legacy_container(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy dict containers should be handled by ``pop_runtime_data`` too."""

    legacy_payload: LegacyRuntimeStorePayloadType = {"runtime_data": runtime_data}
    hass = _build_hass(data={DOMAIN: {"legacy": legacy_payload}})

    assert pop_runtime_data(hass, "legacy") is runtime_data
    assert DOMAIN not in hass.data


def test_pop_runtime_data_cleans_up_domain_store(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Removing the final entry should drop the PawControl data namespace."""

    hass = _build_hass(data={DOMAIN: {"entry": runtime_data}})

    assert pop_runtime_data(hass, "entry") is runtime_data
    assert DOMAIN not in hass.data


def test_coerce_runtime_data_returns_none_for_unknown_payload() -> None:
    """Unexpected payloads should be ignored without requesting migration."""

    coerced, needs_migration = _coerce_runtime_data("not-runtime-data")

    assert coerced is None
    assert needs_migration is False


def test_coerce_runtime_data_accepts_typed_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Typed legacy payloads should be returned without migration."""

    payload: LegacyRuntimeStorePayloadType = {"runtime_data": runtime_data}

    coerced, needs_migration = _coerce_runtime_data(payload)

    assert coerced is runtime_data
    assert needs_migration is False


def test_cleanup_domain_store_removes_empty_store() -> None:
    """Cleanup helper should remove empty PawControl namespaces."""

    hass = _build_hass(data={DOMAIN: {}})

    _cleanup_domain_store(hass, hass.data[DOMAIN])

    assert DOMAIN not in hass.data


def test_pop_runtime_data_returns_none_when_store_missing() -> None:
    """Popping runtime data from an empty store should return ``None``."""

    hass = _build_hass(data={})

    assert pop_runtime_data(hass, "missing") is None


def test_get_runtime_data_discards_uncoercible_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy payloads that cannot be migrated should be removed."""

    invalid_payload: dict[str, object] = {"runtime_data": object()}
    hass = _build_hass(data={DOMAIN: {"legacy": invalid_payload}})

    monkeypatch.setattr(
        runtime_module,
        "_coerce_runtime_data",
        lambda value: (None, True),
    )

    assert get_runtime_data(hass, "legacy") is None
    assert DOMAIN not in hass.data


def test_runtime_data_roundtrip_survives_module_reload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Runtime data stored from a previous module load should still resolve."""

    entry = _entry("reloaded-entry")
    hass = _build_hass(entries={entry.entry_id: entry}, data={})

    reloaded_cls = make_dataclass(
        "PawControlRuntimeData",
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


def test_coerce_runtime_data_handles_reloaded_payload(
    runtime_data: PawControlRuntimeDataType,
) -> None:
    """Legacy stores containing reloaded runtime data should be accepted."""

    reloaded_cls = make_dataclass(
        "PawControlRuntimeData",
        [(field.name, object) for field in fields(PawControlRuntimeData)],
    )
    reloaded_cls.__module__ = PawControlRuntimeData.__module__

    reloaded_instance = reloaded_cls(
        **{
            field.name: getattr(runtime_data, field.name)
            for field in fields(PawControlRuntimeData)
        }
    )

    entry = _entry("reloaded-legacy")
    compatibility_payload: LegacyRuntimeStorePayloadType = {
        "runtime_data": cast(PawControlRuntimeDataType, reloaded_instance)
    }
    hass = _build_hass(
        data={DOMAIN: {entry.entry_id: compatibility_payload}},
        entries={entry.entry_id: entry},
    )

    assert get_runtime_data(hass, entry.entry_id) is reloaded_instance
    assert DOMAIN not in hass.data
