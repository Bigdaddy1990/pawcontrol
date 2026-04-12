"""Additional coverage for compatibility helpers."""

from dataclasses import dataclass
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
    """ConfigEntryState conversion should handle enum names and raw values."""
    state_cls = compat.ConfigEntryState
    first_state = next(iter(state_cls))

    assert state_cls.from_value(first_state.name) is first_state

    if isinstance(first_state.value, str):
        assert state_cls.from_value(first_state.value) is first_state

    with pytest.raises(ValueError):
        state_cls.from_value("definitely_unknown")


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


def test_resolve_binding_module_uses_caller_module_by_default() -> None:
    """Resolving without an explicit module should return the caller module."""

    def _inner() -> ModuleType:
        return compat._resolve_binding_module(None)

    resolved = _inner()
    assert resolved is compat.sys.modules[__name__]


def test_bind_exception_alias_ignores_non_module_registry_entries() -> None:
    """Alias callbacks should no-op when module registry entries are invalid."""
    module_name = "tests.unit.dynamic_alias_non_module"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
        )
        assert dynamic_module.LocalAlias is compat.HomeAssistantError

        compat.sys.modules[module_name] = object()
        compat.ensure_homeassistant_exception_symbols()

        assert dynamic_module.LocalAlias is compat.HomeAssistantError
        unregister()
    finally:
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


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


def test_bind_exception_alias_prefers_more_specific_candidate() -> None:
    """Alias binding should keep the most specific class when possible."""

    class ExistingAlias(compat.HomeAssistantError):
        """A pre-existing alias that is narrower than HomeAssistantError."""

    class CandidateAlias(ExistingAlias):
        """A candidate class that should replace the existing alias."""

    original_home_assistant_error = compat.HomeAssistantError
    module_name = "tests.unit.dynamic_alias_module_specific_candidate"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    dynamic_module.LocalAlias = ExistingAlias

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    compat.HomeAssistantError = CandidateAlias
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
            combine_with_current=True,
        )
        assert dynamic_module.LocalAlias is CandidateAlias
        unregister()
    finally:
        compat.HomeAssistantError = original_home_assistant_error
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


def test_bind_exception_alias_prefers_more_specific_existing_alias() -> None:
    """Alias binding should preserve a narrower existing class when appropriate."""

    class CandidateAlias(compat.HomeAssistantError):
        """The mapped HomeAssistantError candidate."""

    class ExistingAlias(CandidateAlias):
        """A narrower existing alias that should be preserved."""

    original_home_assistant_error = compat.HomeAssistantError
    module_name = "tests.unit.dynamic_alias_module_specific_current"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    dynamic_module.LocalAlias = ExistingAlias

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    compat.HomeAssistantError = CandidateAlias
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
            combine_with_current=True,
        )
        assert dynamic_module.LocalAlias is ExistingAlias
        unregister()
    finally:
        compat.HomeAssistantError = original_home_assistant_error
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


def test_bind_exception_alias_type_error_falls_back_to_candidate() -> None:
    """Hybrid alias creation should fall back to the candidate on MRO conflicts."""

    class CandidateMeta(type):
        """Distinct metaclass for the candidate exception."""

    class ExistingMeta(type):
        """Distinct metaclass for the current exception."""

    class CandidateAlias(Exception, metaclass=CandidateMeta):
        """Mapped Home Assistant exception candidate."""

    class ExistingAlias(Exception, metaclass=ExistingMeta):
        """Existing alias with an incompatible metaclass."""

    original_home_assistant_error = compat.HomeAssistantError
    module_name = "tests.unit.dynamic_alias_type_error"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    dynamic_module.LocalAlias = ExistingAlias

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    compat.HomeAssistantError = CandidateAlias
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
            combine_with_current=True,
        )
        assert dynamic_module.LocalAlias is CandidateAlias
        unregister()
    finally:
        compat.HomeAssistantError = original_home_assistant_error
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


def test_bind_exception_alias_ignores_unknown_exception_names() -> None:
    """Alias binding should leave targets unchanged when no exception maps exist."""
    module_name = "tests.unit.dynamic_alias_unknown_name"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name
    dynamic_module.LocalAlias = RuntimeError

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    try:
        unregister = compat.bind_exception_alias(
            "MissingCompatError",
            module=module_name,
            attr="LocalAlias",
        )
        assert dynamic_module.LocalAlias is RuntimeError
        compat.ensure_homeassistant_exception_symbols()
        assert dynamic_module.LocalAlias is RuntimeError
        unregister()
    finally:
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module


def test_config_entry_supported_subentry_types_without_handler_method() -> None:
    """Subentry support should fail closed when handlers omit capability hooks."""

    class HandlerWithoutSubentrySupport:
        pass

    compat.HANDLERS.clear()
    compat.HANDLERS["pawcontrol"] = HandlerWithoutSubentrySupport()
    entry = compat.ConfigEntry(
        domain="pawcontrol",
        entry_id="entry-1",
        data={},
        options={},
    )

    assert entry.supported_subentry_types == {}


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

    @dataclass
    class NativeConfigEntry:
        domain: str
        entry_id: str

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


def test_sync_config_entry_symbols_adds_from_value_for_native_states() -> None:
    """Native ConfigEntryState enums should receive the compatibility resolver."""

    class NativeState(compat.Enum):
        LOADED = "loaded"
        FAILED = 5

    config_entries_module = ModuleType("homeassistant.config_entries")
    config_entries_module.ConfigEntryState = NativeState

    compat._sync_config_entry_symbols(config_entries_module, None)

    assert compat.ConfigEntryState.from_value("loaded") is NativeState.LOADED
    assert compat.ConfigEntryState.from_value("FAILED") is NativeState.FAILED
    assert compat.ConfigEntryState.from_value("5") is NativeState.FAILED


def test_register_exception_rebind_callback_unregisters_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registered callbacks should receive updates until they are unregistered."""
    monkeypatch.setattr(compat, "_EXCEPTION_REBIND_CALLBACKS", [])
    received: list[dict[str, type[Exception]]] = []

    unregister = compat.register_exception_rebind_callback(received.append)
    compat._notify_exception_callbacks()
    unregister()
    compat._notify_exception_callbacks()

    assert len(received) == 2


def test_bind_exception_alias_rebinding_replaces_previous_callback() -> None:
    """Rebinding the same alias target should replace the stale callback."""
    module_name = "tests.unit.dynamic_alias_rebind"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name

    original_module = compat.sys.modules.get(module_name)
    original_callbacks = list(compat._EXCEPTION_REBIND_CALLBACKS)
    compat.sys.modules[module_name] = dynamic_module
    try:
        unregister_first = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="Alias",
        )
        callbacks_after_first = list(compat._EXCEPTION_REBIND_CALLBACKS)

        unregister_second = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="Alias",
        )
        callbacks_after_second = list(compat._EXCEPTION_REBIND_CALLBACKS)

        assert len(callbacks_after_second) == len(callbacks_after_first)

        unregister_first()
        unregister_second()
    finally:
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module
        compat._EXCEPTION_REBIND_CALLBACKS[:] = original_callbacks


def test_get_exception_uses_default_factory_for_invalid_exports() -> None:
    """Invalid Home Assistant exports should fall back to generated exceptions."""
    exceptions_module = ModuleType("homeassistant.exceptions")
    exceptions_module.ConfigEntryError = object()

    marker = RuntimeError
    assert (
        compat._get_exception(
            "ConfigEntryError",
            lambda: marker,
            exceptions_module,
        )
        is marker
    )


def test_bind_exception_alias_rejects_modules_without_name() -> None:
    """Binding should fail when the provided module object has no __name__."""
    module_without_name = ModuleType("temporary")
    del module_without_name.__dict__["__name__"]

    with pytest.raises(RuntimeError, match="requires a named module"):
        compat.bind_exception_alias("HomeAssistantError", module=module_without_name)


def test_fallback_config_entry_state_helpers_cover_name_and_member_value() -> None:
    """Fallback state helper should resolve enum names and values consistently."""
    state_cls = compat.ConfigEntryState
    first = next(iter(state_cls))

    assert state_cls.from_value(first.name) is first
    assert state_cls.from_value(str(first.value)) is first


def test_sync_config_entry_symbols_uses_core_exports_when_compatible() -> None:
    """Core module exports should be adopted when they match HA semantics."""

    @dataclass
    class NativeCoreEntry:
        domain: str
        entry_id: str

    class NativeCoreState(compat.Enum):
        LOADED = "loaded"

    class NativeCoreChange(compat.Enum):
        ADDED = "added"

    core_module = ModuleType("homeassistant.core")
    core_module.ConfigEntry = NativeCoreEntry
    core_module.ConfigEntryState = NativeCoreState
    core_module.ConfigEntryChange = NativeCoreChange

    compat._sync_config_entry_symbols(None, core_module)

    assert compat.ConfigEntry is NativeCoreEntry
    assert compat.ConfigEntryState is NativeCoreState
    assert compat.ConfigEntryChange is NativeCoreChange


def test_should_use_module_entry_rejects_none_initializer() -> None:
    """Entries exposing no initializer should not be treated as HA compatible."""

    class InvalidEntry:
        __init__ = None

    assert compat._should_use_module_entry(InvalidEntry) is False


def test_ensure_config_entry_state_helpers_handles_name_and_string_values() -> None:
    """Installed from_value helper should resolve both names and string values."""

    class NativeState(compat.Enum):
        LOADED = "loaded"
        FAILED = "FAILED"

    helper_state = compat._ensure_config_entry_state_helpers(NativeState)

    assert helper_state.from_value("loaded") is NativeState.LOADED
    assert helper_state.from_value("failed") is NativeState.FAILED


def test_ensure_config_entry_state_helpers_handles_casefold_and_unknown_values() -> (
    None
):
    """Installed helpers should resolve name/value fallbacks and reject unknowns."""

    class NativeState(compat.Enum):
        LOADED = "Load-Ed"
        FAILED = 5

    helper_state = compat._ensure_config_entry_state_helpers(NativeState)

    assert helper_state.from_value("load-ed") is NativeState.LOADED
    assert helper_state.from_value("5") is NativeState.FAILED

    with pytest.raises(ValueError):
        helper_state.from_value("missing")


def test_ensure_config_entry_state_helpers_handles_unicode_casefold_names() -> None:
    """Installed helpers should fall back to casefolded enum names when needed."""

    class NativeState(compat.Enum):
        STRAẞE = "street"

    helper_state = compat._ensure_config_entry_state_helpers(NativeState)

    assert helper_state.from_value("straße") is NativeState.STRAẞE


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
    if hasattr(registry, "async_services"):
        assert set(registry.async_services().get("notify", {})) == {"sync", "async"}
    if hasattr(registry, "has_service"):
        assert registry.has_service("notify", "sync") is True
        assert registry.has_service("notify", "missing") is False

    if type(registry).__module__ == compat.__name__:
        with pytest.raises(KeyError, match=r"Service notify\.missing not registered"):
            await registry.async_call("notify", "missing")


def test_build_exception_adds_doc_and_extra_attrs() -> None:
    """Generated fallback exceptions should include custom metadata when supplied."""
    generated = compat._build_exception(
        "CustomCompatError",
        RuntimeError,
        "compatibility error",
        extra_attrs={"source": "test-suite"},
    )

    assert generated.__doc__ == "compatibility error"
    assert generated.source == "test-suite"
    assert issubclass(generated, RuntimeError)


def test_build_exception_skips_empty_extra_attrs() -> None:
    """Empty extra attributes should leave generated exception namespace untouched."""
    generated = compat._build_exception(
        "CustomCompatErrorWithoutAttrs",
        RuntimeError,
        "compatibility error without extras",
        extra_attrs={},
    )

    assert generated.__doc__ == "compatibility error without extras"
    assert not hasattr(generated, "source")


def test_import_optional_handles_import_error_and_missing_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional imports should return ``None`` for ImportError variants."""
    native_import = __import__

    def _raise_import_error(name: str, *args: object, **kwargs: object) -> ModuleType:
        if name == "does.not.exist":
            raise ImportError(name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raise_import_error)
    assert compat._import_optional("does.not.exist") is None

    def _raise_module_not_found(
        name: str, *args: object, **kwargs: object
    ) -> ModuleType:
        if name == "still.missing":
            raise ModuleNotFoundError(name)
        return native_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raise_module_not_found)
    assert compat._import_optional("still.missing") is None


def test_resolve_binding_module_raises_when_stack_has_no_registered_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller inference should fail cleanly when no frame resolves to a module."""

    class _Frame:
        def __init__(self, module_name: str | None, back: _Frame | None = None) -> None:
            self.f_globals = {} if module_name is None else {"__name__": module_name}
            self.f_back = back

    monkeypatch.setattr(
        compat.sys,
        "_getframe",
        lambda _depth: _Frame("custom_components.pawcontrol.compat", _Frame(None)),
    )

    with pytest.raises(RuntimeError, match="could not determine the caller module"):
        compat._resolve_binding_module(None)


def test_resolve_binding_module_skips_unregistered_frame_modules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller-module resolution should continue with unregistered frames."""

    class _Frame:
        def __init__(self, module_name: str | None, back: _Frame | None = None) -> None:
            self.f_globals = {} if module_name is None else {"__name__": module_name}
            self.f_back = back

    monkeypatch.setattr(
        compat.sys,
        "_getframe",
        lambda _depth: _Frame("tests.unit.unregistered_alias_target", _Frame(__name__)),
    )

    resolved = compat._resolve_binding_module(None)
    assert resolved is compat.sys.modules[__name__]


def test_bind_exception_alias_combine_mode_without_existing_target_uses_candidate() -> (
    None
):
    """Combine mode should directly assign candidate when no current alias exists."""
    module_name = "tests.unit.dynamic_alias_no_current"
    dynamic_module = ModuleType(module_name)
    dynamic_module.__dict__["__name__"] = module_name

    original_module = compat.sys.modules.get(module_name)
    compat.sys.modules[module_name] = dynamic_module
    try:
        unregister = compat.bind_exception_alias(
            "HomeAssistantError",
            module=module_name,
            attr="LocalAlias",
            combine_with_current=True,
        )
        assert dynamic_module.LocalAlias is compat.HomeAssistantError
        unregister()
    finally:
        if original_module is None:
            compat.sys.modules.pop(module_name, None)
        else:
            compat.sys.modules[module_name] = original_module
