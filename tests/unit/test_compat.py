from collections.abc import Iterator
from contextlib import contextmanager
import importlib
import sys
from types import ModuleType

import pytest


@contextmanager
def _reload_compat_with_stub(
    stub: ModuleType | None,
    *,
    const_stub: ModuleType | None = None,
    config_entries_stub: ModuleType | None = None,
    core_stub: ModuleType | None = None,
) -> Iterator[ModuleType]:
    """Reload the compat module with an optional Home Assistant stub."""
    module_name = "custom_components.pawcontrol.compat"
    original_compat = sys.modules.pop(module_name, None)
    original_exceptions = sys.modules.pop("homeassistant.exceptions", None)
    original_const = sys.modules.pop("homeassistant.const", None)
    original_config_entries = sys.modules.pop("homeassistant.config_entries", None)
    original_core = sys.modules.pop("homeassistant.core", None)

    if stub is not None:
        sys.modules["homeassistant.exceptions"] = stub
    if const_stub is not None:
        sys.modules["homeassistant.const"] = const_stub
    if config_entries_stub is not None:
        sys.modules["homeassistant.config_entries"] = config_entries_stub
    if core_stub is not None:
        sys.modules["homeassistant.core"] = core_stub

    try:
        yield importlib.import_module(module_name)
    finally:
        sys.modules.pop(module_name, None)
        if original_compat is not None:
            sys.modules[module_name] = original_compat
        if original_exceptions is not None:
            sys.modules["homeassistant.exceptions"] = original_exceptions
        else:
            sys.modules.pop("homeassistant.exceptions", None)
        if original_const is not None:
            sys.modules["homeassistant.const"] = original_const
        else:
            sys.modules.pop("homeassistant.const", None)
        if original_config_entries is not None:
            sys.modules["homeassistant.config_entries"] = original_config_entries
        else:
            sys.modules.pop("homeassistant.config_entries", None)
        if original_core is not None:
            sys.modules["homeassistant.core"] = original_core
        else:
            sys.modules.pop("homeassistant.core", None)


def test_config_entry_auth_failed_fallback_accepts_auth_migration() -> None:
    """ConfigEntryAuthFailed fallback should accept auth_migration flag."""
    stub = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub HomeAssistantError base."""

    class ConfigEntryError(HomeAssistantError):
        """Stub ConfigEntryError base."""

    class ConfigEntryNotReady(ConfigEntryError):
        """Stub ConfigEntryNotReady error."""

    class ServiceValidationError(HomeAssistantError):
        """Stub ServiceValidationError."""

    stub.HomeAssistantError = HomeAssistantError
    stub.ConfigEntryError = ConfigEntryError
    stub.ConfigEntryNotReady = ConfigEntryNotReady
    stub.ServiceValidationError = ServiceValidationError

    with _reload_compat_with_stub(stub) as compat:
        exc = compat.ConfigEntryAuthFailed("boom", auth_migration=True)
        assert exc.args == ("boom",)
        assert exc.auth_migration is True
        assert issubclass(compat.ConfigEntryAuthFailed, stub.ConfigEntryError)


def test_config_entry_auth_failed_fallback_without_config_entry_error() -> None:
    """Fallback should inherit from HomeAssistantError when ConfigEntryError missing."""
    stub = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        """Stub HomeAssistantError base."""

    stub.HomeAssistantError = HomeAssistantError

    with _reload_compat_with_stub(stub) as compat:
        assert issubclass(compat.ConfigEntryAuthFailed, HomeAssistantError)
        exc = compat.ConfigEntryAuthFailed("boom")
        assert exc.auth_migration is None


def test_config_entry_auth_failed_fallback_without_home_assistant_error() -> None:
    """Fallback should still work when Home Assistant exceptions module is empty."""
    stub = ModuleType("homeassistant.exceptions")

    with _reload_compat_with_stub(stub) as compat:
        assert issubclass(compat.ConfigEntryAuthFailed, RuntimeError)


def test_unit_of_mass_fallback_uses_default_units() -> None:
    """Compat should supply a UnitOfMass fallback when HA consts are missing."""
    const_stub = ModuleType("homeassistant.const")

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:
        assert compat.UnitOfMass.GRAMS == "g"
        assert compat.UnitOfMass.KILOGRAMS == "kg"
        assert compat.MASS_GRAMS == "g"
        assert compat.MASS_KILOGRAMS == "kg"


def test_unit_of_mass_prefers_homeassistant_enum() -> None:
    """Compat should prefer UnitOfMass from Home Assistant when available."""
    const_stub = ModuleType("homeassistant.const")

    class UnitOfMass:
        GRAMS = "g"
        KILOGRAMS = "kg"

    const_stub.UnitOfMass = UnitOfMass

    with _reload_compat_with_stub(None, const_stub=const_stub) as compat:
        assert compat.UnitOfMass is UnitOfMass
        assert compat.MASS_GRAMS == UnitOfMass.GRAMS
        assert compat.MASS_KILOGRAMS == UnitOfMass.KILOGRAMS


def test_fallback_config_entry_resolves_state_and_support_hooks() -> None:
    """Fallback ConfigEntry should resolve string states and derive handler flags."""
    with _reload_compat_with_stub(
        None,
        config_entries_stub=ModuleType("homeassistant.config_entries"),
        core_stub=ModuleType("homeassistant.core"),
    ) as compat:

        class SubentryHandlerWithReconfigure:
            async def async_step_reconfigure(
                self,
            ) -> None:  # pragma: no cover - shape only
                return None

        class SubentryHandlerWithoutReconfigure:
            pass

        class Handler:
            def async_supports_options_flow(self, _entry: object) -> bool:
                return True

            async def async_unload_entry(self, _entry: object) -> bool:
                return True

            async def async_remove_config_entry_device(self, _entry: object) -> bool:
                return True

            def async_supports_reconfigure_flow(self, _entry: object) -> bool:
                return False

            def async_get_supported_subentry_types(
                self, _entry: object
            ) -> dict[str, object]:
                return {
                    "dog": SubentryHandlerWithReconfigure(),
                    "yard": SubentryHandlerWithoutReconfigure(),
                }

        compat.HANDLERS.clear()
        compat.HANDLERS["pawcontrol"] = Handler()

        entry = compat.ConfigEntry(domain="pawcontrol", state="loaded")
        assert entry.state is compat.ConfigEntryState.LOADED
        assert entry.supports_options is True
        assert entry.supports_unload is True
        assert entry.supports_remove_device is True
        assert entry.supports_reconfigure is False
        assert entry.supported_subentry_types == {
            "dog": {"supports_reconfigure": True},
            "yard": {"supports_reconfigure": False},
        }

        compat.HANDLERS.clear()
        assert entry.supported_subentry_types == {
            "dog": {"supports_reconfigure": True},
            "yard": {"supports_reconfigure": False},
        }


def test_fallback_config_entry_adds_to_hass_and_runs_unload_callbacks() -> None:
    """Fallback ConfigEntry should attach to hass and execute unload callbacks."""
    with _reload_compat_with_stub(
        None,
        config_entries_stub=ModuleType("homeassistant.config_entries"),
        core_stub=ModuleType("homeassistant.core"),
    ) as compat:
        entry = compat.ConfigEntry(domain="pawcontrol", entry_id="entry_42")

        class _Entries:
            _entries: dict[str, object] = {}

        class _Hass:
            config_entries = _Entries()

        hass = _Hass()
        entry.add_to_hass(hass)
        assert hass.config_entries._entries["entry_42"] is entry

        removed: list[str] = []

        async def _listener(_hass: object, _entry: object) -> None:
            removed.append("listener")

        remove_listener = entry.add_update_listener(_listener)
        assert _listener in entry.update_listeners
        remove_listener()
        assert _listener not in entry.update_listeners
        remove_listener()
        assert _listener not in entry.update_listeners

        unload_calls: list[str] = []

        def _sync_unload() -> None:
            unload_calls.append("sync")

        async def _async_unload() -> None:
            unload_calls.append("async")

        entry.async_on_unload(_sync_unload)
        entry.async_on_unload(_async_unload)

        import asyncio

        assert asyncio.run(entry.async_unload()) is True
        assert unload_calls == ["sync", "async"]
        assert entry.state is compat.ConfigEntryState.NOT_LOADED


def test_fallback_config_entry_state_lookup_uses_enum_name_fallback(
    monkeypatch,
) -> None:
    """Fallback ConfigEntry should use enum-name fallback when from_value fails."""
    with _reload_compat_with_stub(
        None,
        config_entries_stub=ModuleType("homeassistant.config_entries"),
        core_stub=ModuleType("homeassistant.core"),
    ) as compat:

        def _raise_value_error(_: str) -> compat.ConfigEntryState:
            raise ValueError("forced")

        monkeypatch.setattr(compat.ConfigEntryState, "from_value", _raise_value_error)
        entry = compat.ConfigEntry(domain="pawcontrol", state="loaded")
        assert entry.state is compat.ConfigEntryState.LOADED


def test_fallback_config_entry_support_flags_cache_false_without_handlers() -> None:
    """Fallback ConfigEntry should cache negative support checks per property."""
    with _reload_compat_with_stub(
        None,
        config_entries_stub=ModuleType("homeassistant.config_entries"),
        core_stub=ModuleType("homeassistant.core"),
    ) as compat:
        compat.HANDLERS.clear()
        entry = compat.ConfigEntry(domain="pawcontrol")
        entry._supports_unload = True

        assert entry.supported_subentry_types == {}
        assert entry.supports_unload is True
        assert entry.supports_unload is True
        assert entry.supports_remove_device is False
        assert entry.supports_reconfigure is False


def test_fallback_config_entry_state_recoverable_property() -> None:
    """Fallback ConfigEntryState should expose the stored recoverable flag."""
    with _reload_compat_with_stub(None) as compat:
        assert compat.ConfigEntryState.LOADED.recoverable is True
        assert compat.ConfigEntryState.MIGRATION_ERROR.recoverable is False
        with pytest.raises(ValueError):
            compat.ConfigEntryState.from_value("missing")


def test_ensure_homeassistant_config_entry_symbols_syncs_late_modules() -> None:
    """Late-installed Home Assistant stubs should receive compat config exports."""
    with _reload_compat_with_stub(None) as compat:
        config_entries_module = ModuleType("homeassistant.config_entries")
        core_module = ModuleType("homeassistant.core")
        sys.modules["homeassistant.config_entries"] = config_entries_module
        sys.modules["homeassistant.core"] = core_module

        compat.ensure_homeassistant_config_entry_symbols()

        assert config_entries_module.ConfigEntry is compat.ConfigEntry
        assert config_entries_module.ConfigEntryState is compat.ConfigEntryState
        assert config_entries_module.ConfigEntryChange is compat.ConfigEntryChange
        assert core_module.ConfigEntry is compat.ConfigEntry
        assert core_module.ConfigEntryState is compat.ConfigEntryState
        assert core_module.ConfigEntryChange is compat.ConfigEntryChange


def test_fallback_service_registry_exposes_registry_helpers() -> None:
    """Fallback service registry should track registered handlers offline."""
    with _reload_compat_with_stub(
        None,
        core_stub=ModuleType("homeassistant.core"),
    ) as compat:
        registry = compat.ServiceRegistry()
        calls: list[tuple[str, str, dict[str, object]]] = []

        def _handler(call: object) -> None:
            calls.append((call.domain, call.service, dict(call.data)))

        async def _async_handler(call: object) -> None:
            calls.append((call.domain, call.service, dict(call.data)))

        registry.async_register("notify", "send", _handler)
        registry.async_register("notify", "async_send", _async_handler)

        import asyncio

        asyncio.run(registry.async_call("notify", "send", {"message": "hello"}))
        asyncio.run(registry.async_call("notify", "async_send", {"message": "async"}))

        assert calls == [
            ("notify", "send", {"message": "hello"}),
            ("notify", "async_send", {"message": "async"}),
        ]
        assert registry.async_services() == {
            "notify": {"send": _handler, "async_send": _async_handler},
        }
        assert registry.has_service("notify", "send") is True
        assert registry.has_service("notify", "missing") is False

        with pytest.raises(KeyError, match=r"Service notify\.missing not registered"):
            asyncio.run(registry.async_call("notify", "missing"))
