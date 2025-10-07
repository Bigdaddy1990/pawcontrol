"""Compatibility helpers that keep the integration functional without Home Assistant."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import dataclass
from enum import Enum
from itertools import count
from types import ModuleType
from typing import Any, TypeVar, cast

RuntimeT = TypeVar("RuntimeT")


def _build_exception(
    name: str,
    base: type[Exception],
    doc: str,
    extra_attrs: dict[str, object] | None = None,
) -> type[Exception]:
    """Create a lightweight exception class used when Home Assistant isn't available."""

    namespace: dict[str, object] = {"__doc__": doc}
    if extra_attrs:
        namespace.update(extra_attrs)
    return type(name, (base,), namespace)


def _import_optional(module: str) -> Any:
    try:  # pragma: no cover - executed when Home Assistant is installed
        return __import__(module, fromlist=["*"])
    except (ImportError, ModuleNotFoundError):
        return None


_ha_exceptions = _import_optional("homeassistant.exceptions")
_ha_config_entries = _import_optional("homeassistant.config_entries")
_ha_core = _import_optional("homeassistant.core")


def _get_exception(
    name: str,
    default_factory: Callable[[], type[Exception]],
    exceptions_module: ModuleType | None = None,
) -> type[Exception]:
    """Return an exception class from Home Assistant or build a fallback."""

    module = exceptions_module if exceptions_module is not None else _ha_exceptions
    if module is None:
        return default_factory()

    attr = getattr(module, name, None)
    if isinstance(attr, type) and issubclass(attr, Exception):
        return cast(type[Exception], attr)

    return default_factory()


class _FallbackHomeAssistantError(Exception):
    """Fallback base error used when Home Assistant isn't installed."""


HomeAssistantError: type[Exception] = _FallbackHomeAssistantError
_HOMEASSISTANT_ERROR_IS_FALLBACK = True


def _config_entry_error_factory() -> type[Exception]:
    base = HomeAssistantError if not _HOMEASSISTANT_ERROR_IS_FALLBACK else RuntimeError
    return _build_exception(
        "ConfigEntryError",
        base,
        "Fallback ConfigEntry error used outside Home Assistant.",
    )


def _config_entry_auth_failed_init(
    self: Exception,
    message: str | None = None,
    *,
    auth_migration: bool | None = None,
) -> None:
    ConfigEntryError.__init__(self, message)
    self.auth_migration = auth_migration


def _auth_failed_factory() -> type[Exception]:
    return _build_exception(
        "ConfigEntryAuthFailed",
        ConfigEntryError,
        "Fallback ConfigEntryAuthFailed stand-in.",
        extra_attrs={
            "__slots__": ("auth_migration",),
            "__init__": _config_entry_auth_failed_init,
        },
    )


def _not_ready_factory() -> type[Exception]:
    return _build_exception(
        "ConfigEntryNotReady",
        ConfigEntryError,
        "Fallback ConfigEntryNotReady used when HA is unavailable.",
    )

def _service_validation_error_factory() -> type[Exception]:
    return _build_exception(
        "ServiceValidationError",
        HomeAssistantError,
        "Fallback validation error raised for invalid service payloads.",
    )


def _refresh_exception_symbols(exceptions_module: ModuleType | None) -> None:
    """Refresh exported exception classes when Home Assistant stubs appear."""

    global _ha_exceptions
    global HomeAssistantError
    global _HOMEASSISTANT_ERROR_IS_FALLBACK
    global ConfigEntryError
    global ConfigEntryAuthFailed
    global ConfigEntryNotReady
    global ServiceValidationError

    _ha_exceptions = exceptions_module

    resolved_homeassistant_error: type[Exception] | None = None
    if exceptions_module is not None:
        candidate = getattr(exceptions_module, "HomeAssistantError", None)
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            resolved_homeassistant_error = cast(type[Exception], candidate)

    if resolved_homeassistant_error is None:
        HomeAssistantError = _FallbackHomeAssistantError
        _HOMEASSISTANT_ERROR_IS_FALLBACK = True
    else:
        HomeAssistantError = resolved_homeassistant_error
        _HOMEASSISTANT_ERROR_IS_FALLBACK = False

    ConfigEntryError = _get_exception(
        "ConfigEntryError",
        _config_entry_error_factory,
        exceptions_module,
    )
    ConfigEntryAuthFailed = _get_exception(
        "ConfigEntryAuthFailed",
        _auth_failed_factory,
        exceptions_module,
    )
    ConfigEntryNotReady = _get_exception(
        "ConfigEntryNotReady",
        _not_ready_factory,
        exceptions_module,
    )
    ServiceValidationError = _get_exception(
        "ServiceValidationError",
        _service_validation_error_factory,
        exceptions_module,
    )


def ensure_homeassistant_exception_symbols() -> None:
    """Ensure exception exports mirror the active Home Assistant module."""

    _refresh_exception_symbols(sys.modules.get("homeassistant.exceptions"))


_refresh_exception_symbols(_ha_exceptions)


class ConfigEntryState(Enum):
    """Minimal stand-in mirroring Home Assistant config entry states."""

    NOT_LOADED = ("not_loaded", True)
    LOADED = ("loaded", True)
    SETUP_IN_PROGRESS = ("setup_in_progress", False)
    SETUP_RETRY = ("setup_retry", True)
    SETUP_ERROR = ("setup_error", True)
    MIGRATION_ERROR = ("migration_error", False)
    FAILED_UNLOAD = ("failed_unload", False)

    def __new__(cls, value: str, recoverable: bool) -> ConfigEntryState:
        obj = object.__new__(cls)
        obj._value_ = value
        obj._recoverable = recoverable
        return obj

    @property
    def recoverable(self) -> bool:
        """Return whether the state can be recovered without user intervention."""

        return self._recoverable


class ConfigEntryChange(Enum):
    """Enum describing why a config entry update listener fired."""

    ADDED = "added"
    REMOVED = "removed"
    UPDATED = "updated"


class ConfigEntry[RuntimeT]:  # type: ignore[override]
    """Lightweight ConfigEntry implementation for test environments."""

    _id_source = count(1)

    def __init__(
        self,
        entry_id: str | None = None,
        *,
        domain: str | None = None,
        data: Mapping[str, Any] | None = None,
        options: Mapping[str, Any] | None = None,
        title: str | None = None,
        source: str = "user",
        version: int = 1,
        minor_version: int = 0,
        unique_id: str | None = None,
        pref_disable_new_entities: bool = False,
        pref_disable_polling: bool = False,
        disabled_by: str | None = None,
        state: ConfigEntryState | str = ConfigEntryState.NOT_LOADED,
    ) -> None:
        self.entry_id = entry_id or f"entry_{next(self._id_source)}"
        self.domain = domain or "unknown"
        self.data: dict[str, Any] = dict(data or {})
        self.options: dict[str, Any] = dict(options or {})
        self.title = title or self.domain
        self.source = source
        self.version = version
        self.minor_version = minor_version
        self.unique_id = unique_id or self.entry_id
        self.pref_disable_new_entities = pref_disable_new_entities
        self.pref_disable_polling = pref_disable_polling
        self.disabled_by = disabled_by
        self.state = (
            ConfigEntryState(state)
            if isinstance(state, str)
            else state
        )
        self.supports_unload: bool | None = None
        self.supports_remove_device: bool | None = None
        self._supports_options: bool | None = None
        self._supports_reconfigure: bool | None = None
        self.reason: str | None = None
        self.error_reason_translation_key: str | None = None
        self.error_reason_translation_placeholders: dict[str, Any] | None = None
        self.runtime_data: RuntimeT | None = None
        self.update_listeners: list[
            Callable[[Any, ConfigEntry[RuntimeT]], Awaitable[None] | None]
        ] = []
        self._on_unload: list[Callable[[], Coroutine[Any, Any, None] | None]] = []
        self._async_cancel_retry_setup: Callable[[], Any] | None = None
        self._hass: Any | None = None

    def add_to_hass(self, hass: Any) -> None:
        """Associate the entry with a Home Assistant instance."""

        self._hass = hass
        manager = getattr(getattr(hass, "config_entries", None), "_entries", None)
        if isinstance(manager, dict):  # pragma: no branch - test helper hook
            manager[self.entry_id] = self

    def add_update_listener(
        self,
        listener: Callable[[Any, ConfigEntry[RuntimeT]], Awaitable[None] | None],
    ) -> Callable[[], None]:
        """Register a callback for config entry updates."""

        self.update_listeners.append(listener)

        def _remove() -> None:
            if listener in self.update_listeners:
                self.update_listeners.remove(listener)

        return _remove

    def async_on_unload(
        self, callback: Callable[[], Coroutine[Any, Any, None] | None]
    ) -> Callable[[], Coroutine[Any, Any, None] | None]:
        """Register a callback invoked when the entry unloads."""

        self._on_unload.append(callback)
        return callback

    async def async_setup(self, hass: Any) -> bool:  # pragma: no cover - helper
        """Mark the entry as loaded when set up in tests."""

        self._hass = hass
        self.state = ConfigEntryState.LOADED
        return True

    async def async_unload(self, hass: Any | None = None) -> bool:
        """Mark the entry as not loaded and invoke unload callbacks."""

        self.state = ConfigEntryState.NOT_LOADED
        for callback in list(self._on_unload):
            result = callback()
            if hasattr(result, "__await__"):
                await cast(Awaitable[Any], result)
        return True


def _should_use_module_entry(entry_cls: Any) -> bool:
    """Return ``True`` if the imported ConfigEntry already exposes HA semantics."""

    if not isinstance(entry_cls, type):
        return False

    init = getattr(entry_cls, "__init__", None)
    if init is None:
        return False

    try:
        signature = inspect.signature(init)  # type: ignore[arg-type]
    except (TypeError, ValueError):  # pragma: no cover - signature unavailable
        return False

    parameter_names = {parameter.name for parameter in signature.parameters.values()}
    return {"domain", "entry_id"}.issubset(parameter_names)


def _is_enum_type(value: Any) -> bool:
    """Return ``True`` if ``value`` is an :class:`Enum` subclass."""

    return isinstance(value, type) and issubclass(value, Enum)


def _sync_config_entry_symbols(
    config_entries_module: Any | None, core_module: Any | None
) -> None:
    """Ensure Home Assistant modules expose the compatibility ConfigEntry types."""

    if config_entries_module is not None:
        module_entry_cls = getattr(config_entries_module, "ConfigEntry", None)
        if _should_use_module_entry(module_entry_cls):
            globals()["ConfigEntry"] = cast(type[Any], module_entry_cls)
        else:
            config_entries_module.ConfigEntry = ConfigEntry

        module_state = getattr(config_entries_module, "ConfigEntryState", None)
        if _is_enum_type(module_state):
            globals()["ConfigEntryState"] = cast(type[Enum], module_state)
        else:
            config_entries_module.ConfigEntryState = ConfigEntryState

        module_change = getattr(config_entries_module, "ConfigEntryChange", None)
        if _is_enum_type(module_change):
            globals()["ConfigEntryChange"] = cast(type[Enum], module_change)
        else:
            config_entries_module.ConfigEntryChange = ConfigEntryChange

    if core_module is not None:
        module_entry_cls = getattr(core_module, "ConfigEntry", None)
        if _should_use_module_entry(module_entry_cls):
            globals()["ConfigEntry"] = cast(type[Any], module_entry_cls)
        else:
            core_module.ConfigEntry = ConfigEntry

        state_cls = getattr(core_module, "ConfigEntryState", None)
        if _is_enum_type(state_cls):
            globals()["ConfigEntryState"] = cast(type[Enum], state_cls)
        else:
            core_module.ConfigEntryState = ConfigEntryState

        change_cls = getattr(core_module, "ConfigEntryChange", None)
        if _is_enum_type(change_cls):
            globals()["ConfigEntryChange"] = cast(type[Enum], change_cls)
        else:
            core_module.ConfigEntryChange = ConfigEntryChange


_sync_config_entry_symbols(_ha_config_entries, _ha_core)


def ensure_homeassistant_config_entry_symbols() -> None:
    """Re-apply ConfigEntry exports when Home Assistant stubs are installed late."""

    _sync_config_entry_symbols(
        sys.modules.get("homeassistant.config_entries"),
        sys.modules.get("homeassistant.core"),
    )


def _fallback_service_registry() -> type[Any]:
    if _ha_core is not None:
        registry = getattr(_ha_core, "ServiceRegistry", None)
        if isinstance(registry, type):  # pragma: no cover - prefer HA implementation
            return registry

    @dataclass
    class _ServiceCall:
        domain: str
        service: str
        data: Mapping[str, Any]

    class ServiceRegistry:
        """Simplified service registry for offline test environments."""

        def __init__(self) -> None:
            self._services: dict[str, dict[str, Callable[..., Any]]] = {}

        def async_register(
            self,
            domain: str,
            service: str,
            handler: Callable[..., Any],
            schema: Any | None = None,
        ) -> None:
            self._services.setdefault(domain, {})[service] = handler

        async def async_call(
            self,
            domain: str,
            service: str,
            data: Mapping[str, Any] | None = None,
        ) -> None:
            handler = self._services.get(domain, {}).get(service)
            if handler is None:
                raise KeyError(f"Service {domain}.{service} not registered")
            result = handler(_ServiceCall(domain, service, data or {}))
            if hasattr(result, "__await__"):
                await cast(Awaitable[Any], result)

        def async_services(self) -> dict[str, dict[str, Callable[..., Any]]]:
            return self._services

        def has_service(self, domain: str, service: str) -> bool:
            return service in self._services.get(domain, {})

    return ServiceRegistry


ServiceRegistry = _fallback_service_registry()


__all__ = [
    "ConfigEntry",
    "ConfigEntryAuthFailed",
    "ConfigEntryChange",
    "ConfigEntryError",
    "ConfigEntryNotReady",
    "ConfigEntryState",
    "HomeAssistantError",
    "ServiceRegistry",
    "ServiceValidationError",
    "ensure_homeassistant_config_entry_symbols",
    "ensure_homeassistant_exception_symbols",
]
