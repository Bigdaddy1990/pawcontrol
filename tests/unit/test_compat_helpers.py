"""Additional coverage for compatibility helpers."""

from types import ModuleType

import pytest

from custom_components.pawcontrol import compat


@pytest.mark.asyncio
async def test_support_hooks_reflect_registered_handler_capabilities() -> None:
    """Support helpers should check the handler registry for known hooks."""

    class HandlerWithHooks:
        async def async_unload_entry(self) -> bool:  # pragma: no cover - shape only
            return True

        async def async_remove_config_entry_device(self) -> bool:  # pragma: no cover
            return True

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = HandlerWithHooks()

    assert await compat.support_entry_unload(None, "pawcontrol") is True
    assert await compat.support_remove_from_device(None, "pawcontrol") is True


@pytest.mark.asyncio
async def test_support_hooks_return_false_for_unknown_or_partial_handlers() -> None:
    """Support helpers should fail closed when hooks are missing."""

    class HandlerWithoutHooks:
        pass

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = HandlerWithoutHooks()

    assert await compat.support_entry_unload(None, "pawcontrol") is False
    assert await compat.support_remove_from_device(None, "pawcontrol") is False
    assert await compat.support_entry_unload(None, "missing") is False


def test_config_entry_state_from_value_supports_name_and_raw_value() -> None:
    """ConfigEntryState conversion should handle both enum names and values."""
    assert (
        compat.ConfigEntryState.from_value("loaded") is compat.ConfigEntryState.LOADED
    )
    assert (
        compat.ConfigEntryState.from_value("SETUP_RETRY")
        is compat.ConfigEntryState.SETUP_RETRY
    )

    with pytest.raises(ValueError):
        compat.ConfigEntryState.from_value("definitely_unknown")


def test_build_subentries_normalizes_input() -> None:
    """Subentry builder should coerce optional fields into deterministic structures."""
    built = compat._build_subentries(
        [
            {
                "subentry_type": "dog",
                "title": "Rex",
                "data": {"age": 3},
                "unique_id": 42,
            },
            {
                "subentry_id": "garden",
                "data": "not_a_mapping",
                "title": "Backyard",
            },
        ],
    )

    assert set(built) == {"subentry_1", "garden"}
    assert built["subentry_1"].data == {"age": 3}
    assert built["subentry_1"].unique_id == "42"
    assert built["garden"].data == {}
    assert built["garden"].subentry_type == "subentry"


def test_resolve_binding_module_rejects_unknown_module_name() -> None:
    """Resolving a missing module name should raise a descriptive runtime error."""
    with pytest.raises(RuntimeError, match="could not locate module"):
        compat._resolve_binding_module("tests.unit.missing_alias_target")


def test_bind_exception_alias_combine_with_current_creates_hybrid_alias() -> None:
    """Alias binding should combine classes when requested and unregister cleanly."""

    class ExistingAlias(Exception):
        """Local marker class used as the existing alias target."""

    module_name = "tests.unit.dynamic_alias_module_combine"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    dynamic_module.LocalAlias = ExistingAlias

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
            combine_with_current=True,
        )
        bound_alias = dynamic_module.LocalAlias

        assert issubclass(bound_alias, compat.HomeAssistantError)
        assert issubclass(bound_alias, ExistingAlias)

        unregister()
        rebound_alias = dynamic_module.LocalAlias
        compat.ensure_homeassistant_exception_symbols()
        assert dynamic_module.LocalAlias is rebound_alias
    finally:
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


def test_sync_config_entry_symbols_populates_missing_module_exports() -> None:
    """Config-entry symbol sync should install fallback classes when absent."""
    config_entries_module = ModuleType("homeassistant.config_entries")
    core_module = ModuleType("homeassistant.core")

    compat._sync_config_entry_symbols(config_entries_module, core_module)

    assert config_entries_module.ConfigEntry is compat.ConfigEntry
    assert config_entries_module.ConfigEntryState is compat.ConfigEntryState
    assert config_entries_module.ConfigEntryChange is compat.ConfigEntryChange
    assert core_module.ConfigEntry is compat.ConfigEntry
    assert core_module.ConfigEntryState is compat.ConfigEntryState
    assert core_module.ConfigEntryChange is compat.ConfigEntryChange


def test_sync_config_entry_symbols_preserves_valid_homeassistant_exports() -> None:
    """Config-entry symbol sync should keep Home Assistant compatible symbols."""

    class NativeConfigEntry:
        def __init__(self, domain: str, entry_id: str) -> None:
            self.domain = domain
            self.entry_id = entry_id

    class NativeState(compat.Enum):
        LOADED = "loaded"

    class NativeChange(compat.Enum):
        ADDED = "added"

    config_entries_module = ModuleType("homeassistant.config_entries")
    config_entries_module.ConfigEntry = NativeConfigEntry
    config_entries_module.ConfigEntryState = NativeState
    config_entries_module.ConfigEntryChange = NativeChange

    compat._sync_config_entry_symbols(config_entries_module, None)

    assert compat.ConfigEntry is NativeConfigEntry
    assert compat.ConfigEntryState is NativeState
    assert compat.ConfigEntryChange is NativeChange


@pytest.mark.asyncio
async def test_fallback_service_registry_invokes_sync_and_async_handlers() -> None:
    """Fallback registry should support sync/async handlers and missing lookups."""
    registry = compat.ServiceRegistry()

    calls: list[tuple[str, str]] = []

    def _sync_handler(call: object) -> None:
        calls.append((call.domain, call.service))

    async def _async_handler(call: object) -> None:
        calls.append((call.domain, call.service))

    registry.async_register("notify", "sync", _sync_handler)
    registry.async_register("notify", "async", _async_handler)

    await registry.async_call("notify", "sync", {"x": 1})
    await registry.async_call("notify", "async", {"x": 2})

    assert calls == [("notify", "sync"), ("notify", "async")]
    if hasattr(registry, "has_service"):
        assert registry.has_service("notify", "sync") is True

    if type(registry).__module__ == compat.__name__:
        with pytest.raises(KeyError, match=r"Service notify\.missing not registered"):
            await registry.async_call("notify", "missing")
