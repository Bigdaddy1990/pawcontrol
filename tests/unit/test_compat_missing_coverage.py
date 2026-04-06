"""Additional branch coverage tests for ``custom_components.pawcontrol.compat``."""

from enum import Enum
import inspect
import sys
from types import ModuleType

import pytest

from custom_components.pawcontrol import compat


def test_support_helpers_detect_registered_handler_hooks() -> None:
    """Support helpers should reflect whether handler hooks exist."""

    class Handler:
        async def async_unload_entry(self, _hass: object, _entry: object) -> bool:
            return True

        async def async_remove_config_entry_device(
            self, _hass: object, _entry: object
        ) -> bool:
            return True

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = Handler()

    import asyncio

    assert asyncio.run(compat.support_entry_unload(object(), "pawcontrol")) is True
    assert (
        asyncio.run(compat.support_remove_from_device(object(), "pawcontrol")) is True
    )

    compat.HANDLERS.clear()
    assert asyncio.run(compat.support_entry_unload(object(), "pawcontrol")) is False
    assert (
        asyncio.run(compat.support_remove_from_device(object(), "pawcontrol")) is False
    )


def test_notify_exception_callbacks_ignores_broken_callbacks() -> None:
    """Broken callbacks should be ignored by the notifier."""
    calls: list[dict[str, type[Exception]]] = []

    def _healthy_callback(mapping: dict[str, type[Exception]]) -> None:
        calls.append(mapping)

    def _broken_callback(_mapping: dict[str, type[Exception]]) -> None:
        raise RuntimeError("boom")

    unregister = compat.register_exception_rebind_callback(_healthy_callback)
    compat._EXCEPTION_REBIND_CALLBACKS.append(_broken_callback)
    try:
        compat._notify_exception_callbacks()
        assert calls
    finally:
        unregister()
        with compat.suppress(ValueError):
            compat._EXCEPTION_REBIND_CALLBACKS.remove(_broken_callback)


def test_resolve_binding_module_validates_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Module resolver should raise clear errors for unresolved modules/frames."""
    with pytest.raises(RuntimeError, match="could not locate module"):
        compat._resolve_binding_module("does.not.exist")

    monkeypatch.setattr(
        compat.sys,
        "_getframe",
        lambda _depth: (_ for _ in ()).throw(ValueError("no frame")),
    )
    with pytest.raises(RuntimeError, match="could not determine the caller module"):
        compat._resolve_binding_module(None)


def test_bind_exception_alias_combine_mode_and_unregistration() -> None:
    """Alias binding should combine classes and cleanly unregister."""
    module_name = "tests.unit._compat_alias_target"
    target_module = ModuleType(module_name)

    class ExistingError(Exception):
        pass

    target_module.TargetError = ExistingError
    sys.modules[module_name] = target_module

    unregister = compat.bind_exception_alias(
        "ConfigEntryError",
        module=module_name,
        attr="TargetError",
        combine_with_current=True,
    )
    try:
        alias_cls = target_module.TargetError
        assert issubclass(alias_cls, Exception)
        assert issubclass(alias_cls, compat.ConfigEntryError)
        assert issubclass(alias_cls, ExistingError)
    finally:
        unregister()
        sys.modules.pop(module_name, None)


def test_bind_exception_alias_requires_named_module() -> None:
    """Anonymous modules should be rejected when binding aliases."""
    module = ModuleType("temporary")
    module.__name__ = ""
    with pytest.raises(RuntimeError, match="requires a named module"):
        compat.bind_exception_alias("ConfigEntryError", module=module)


def test_build_subentries_handles_non_mapping_data() -> None:
    """Subentry helper should normalize IDs, payloads and unique IDs."""
    result = compat._build_subentries([
        {
            "title": "First",
            "subentry_type": "dog",
            "data": ["not", "a", "mapping"],
            "unique_id": 123,
        },
        {
            "subentry_id": "known",
            "title": "Second",
            "subentry_type": "yard",
            "data": {"enabled": True},
        },
    ])

    assert "subentry_1" in result
    assert result["subentry_1"].data == {}
    assert result["subentry_1"].unique_id == "123"

    assert result["known"].data == {"enabled": True}
    assert result["known"].unique_id is None


def test_should_use_module_entry_handles_typeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signature inspection TypeError should produce a False decision."""

    class Entry:
        def __init__(self, domain: str, entry_id: str) -> None:
            self.domain = domain
            self.entry_id = entry_id

    monkeypatch.setattr(
        inspect,
        "signature",
        lambda _obj: (_ for _ in ()).throw(TypeError("no signature")),
    )
    assert compat._should_use_module_entry(Entry) is False


class _StringState(Enum):
    READY = "ready"


class _NumericState(Enum):
    READY = 1


def test_ensure_config_entry_state_helpers_matches_names_and_values() -> None:
    """Injected from_value helper should support names and values case-insensitively."""
    string_enum = compat._ensure_config_entry_state_helpers(_StringState)
    numeric_enum = compat._ensure_config_entry_state_helpers(_NumericState)

    assert string_enum.from_value("ready") is _StringState.READY
    assert string_enum.from_value("READY") is _StringState.READY
    assert numeric_enum.from_value("1") is _NumericState.READY

    with pytest.raises(ValueError):
        string_enum.from_value("missing")
