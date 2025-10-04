"""Unit tests for runtime data helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast
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
            self.data = {}

    core.HomeAssistant = HomeAssistant
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


@pytest.fixture
def runtime_data() -> PawControlRuntimeData:
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


def _entry(entry_id: str = "test-entry") -> PawControlConfigEntry:
    """Create a dummy config entry with the given identifier."""

    return cast(PawControlConfigEntry, _DummyEntry(entry_id))


def test_store_and_get_runtime_data_roundtrip(
    runtime_data: PawControlRuntimeData,
) -> None:
    """Storing runtime data should make it retrievable via the helper."""

    hass = SimpleNamespace(data={})
    entry = _entry()

    store_runtime_data(hass, entry, runtime_data)

    assert get_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry.entry_id) is runtime_data


def test_get_runtime_data_handles_legacy_container(
    runtime_data: PawControlRuntimeData,
) -> None:
    """Legacy dict containers should still be unwrapped."""

    hass = SimpleNamespace(data={DOMAIN: {"legacy": {"runtime_data": runtime_data}}})

    assert get_runtime_data(hass, "legacy") is runtime_data
    # The legacy container should be replaced with the actual runtime data for
    # subsequent lookups to avoid repeated migrations.
    assert hass.data[DOMAIN]["legacy"] is runtime_data


def test_get_runtime_data_ignores_unknown_entries() -> None:
    """Missing entries should return ``None`` without side effects."""

    hass = SimpleNamespace(data={})

    assert get_runtime_data(hass, "missing") is None


def test_get_runtime_data_with_unexpected_container_type(
    runtime_data: PawControlRuntimeData,
) -> None:
    """Non-mapping containers are treated as absent data."""

    hass = SimpleNamespace(data={DOMAIN: []})

    assert get_runtime_data(hass, "legacy") is None

    # After storing data the invalid container should be replaced with a mapping.
    entry = _entry("recovered")
    store_runtime_data(hass, entry, runtime_data)
    assert isinstance(hass.data[DOMAIN], dict)
    assert get_runtime_data(hass, entry.entry_id) is runtime_data


def test_pop_runtime_data_removes_entry(runtime_data: PawControlRuntimeData) -> None:
    """Popping runtime data should remove the stored value."""

    hass = SimpleNamespace(data={})
    entry = _entry("pop-entry")

    store_runtime_data(hass, entry, runtime_data)
    assert pop_runtime_data(hass, entry) is runtime_data
    assert get_runtime_data(hass, entry) is None


def test_pop_runtime_data_handles_legacy_container(
    runtime_data: PawControlRuntimeData,
) -> None:
    """Legacy dict containers should be handled by ``pop_runtime_data`` too."""

    hass = SimpleNamespace(data={DOMAIN: {"legacy": {"runtime_data": runtime_data}}})

    assert pop_runtime_data(hass, "legacy") is runtime_data
    assert DOMAIN not in hass.data


def test_pop_runtime_data_cleans_up_domain_store(
    runtime_data: PawControlRuntimeData,
) -> None:
    """Removing the final entry should drop the PawControl data namespace."""

    hass = SimpleNamespace(data={DOMAIN: {"entry": runtime_data}})

    assert pop_runtime_data(hass, "entry") is runtime_data
    assert DOMAIN not in hass.data


def test_coerce_runtime_data_returns_none_for_unknown_payload() -> None:
    """Unexpected payloads should be ignored without requesting migration."""

    coerced, needs_migration = _coerce_runtime_data("not-runtime-data")

    assert coerced is None
    assert needs_migration is False


def test_cleanup_domain_store_removes_empty_store() -> None:
    """Cleanup helper should remove empty PawControl namespaces."""

    hass = SimpleNamespace(data={DOMAIN: {}})

    _cleanup_domain_store(hass, hass.data[DOMAIN])

    assert DOMAIN not in hass.data


def test_pop_runtime_data_returns_none_when_store_missing() -> None:
    """Popping runtime data from an empty store should return ``None``."""

    hass = SimpleNamespace(data={})

    assert pop_runtime_data(hass, "missing") is None


def test_get_runtime_data_discards_uncoercible_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy payloads that cannot be migrated should be removed."""

    hass = SimpleNamespace(data={DOMAIN: {"legacy": {"runtime_data": object()}}})

    monkeypatch.setattr(
        runtime_module,
        "_coerce_runtime_data",
        lambda value: (None, True),
    )

    assert get_runtime_data(hass, "legacy") is None
    assert DOMAIN not in hass.data
