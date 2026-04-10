"""Focused branch coverage tests for compatibility helpers."""

import asyncio
import sys
from types import ModuleType

import pytest

from custom_components.pawcontrol import compat


def test_support_handler_flags_reflect_registered_hooks() -> None:
    """Handler feature probes should follow available async hook attributes."""

    class _UnloadOnly:
        async def async_unload_entry(self) -> None:  # pragma: no cover - signature stub
            return None

    class _RemoveOnly:
        async def async_remove_config_entry_device(
            self,
        ) -> None:  # pragma: no cover - signature stub
            return None

    compat.HANDLERS.clear()
    compat.HANDLERS["unload"] = _UnloadOnly()
    compat.HANDLERS["remove"] = _RemoveOnly()

    assert asyncio.run(compat.support_entry_unload(None, "unload"))
    assert not asyncio.run(compat.support_entry_unload(None, "remove"))
    assert asyncio.run(compat.support_remove_from_device(None, "remove"))
    assert not asyncio.run(compat.support_remove_from_device(None, "missing"))


def test_bind_exception_alias_with_composed_type_and_unregister() -> None:
    """Alias rebinding should compose classes when combine mode is enabled."""
    module_name = "test_bind_exception_alias_module"
    module = ModuleType(module_name)
    module.AliasError = RuntimeError
    sys.modules[module_name] = module

    unregister = compat.bind_exception_alias(
        "ConfigEntryError",
        module=module,
        attr="AliasError",
        combine_with_current=True,
    )

    alias = module.AliasError
    assert isinstance(alias, type)
    assert issubclass(alias, compat.ConfigEntryError)
    assert issubclass(alias, RuntimeError)

    unregister()
    sys.modules.pop(module_name, None)


def test_config_entry_state_from_value_covers_error_path() -> None:
    """State lookup should be case-insensitive and reject unknown values."""
    assert (
        compat.ConfigEntryState.from_value("loaded") is compat.ConfigEntryState.LOADED
    )

    with pytest.raises(ValueError):
        compat.ConfigEntryState.from_value("not-a-real-state")


def test_resolve_binding_module_missing_named_module_raises() -> None:
    """String-based module resolution should fail for unknown modules."""
    with pytest.raises(RuntimeError, match="could not locate module"):
        compat._resolve_binding_module("module_does_not_exist")


def test_build_subentries_normalizes_defaults_and_raw_values() -> None:
    """Subentry builder should coerce optional data and fallback ids/titles."""
    subentries = compat._build_subentries([
        {"data": "invalid"},
        {
            "subentry_id": "custom",
            "subentry_type": "dog",
            "title": "Bravo",
            "data": {"age": 5},
            "unique_id": 42,
        },
    ])

    first = subentries["subentry_1"]
    assert first.data == {}
    assert first.subentry_type == "subentry"
    assert first.title == "subentry_1"

    second = subentries["custom"]
    assert second.data == {"age": 5}
    assert second.subentry_type == "dog"
    assert second.title == "Bravo"
    assert second.unique_id == "42"
