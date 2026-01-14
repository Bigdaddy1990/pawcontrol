"""Compatibility helpers that keep the integration functional without Home Assistant."""
from __future__ import annotations

import inspect
import sys
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Coroutine
from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from datetime import UTC
from enum import Enum
from itertools import count
from types import ModuleType
from typing import Any
from typing import cast
from typing import TypeVar

type JSONPrimitive = None | bool | int | float | str
"""Primitive JSON-compatible value."""

type JSONValue = JSONPrimitive | Sequence['JSONValue'] | Mapping[str, 'JSONValue']
"""Recursive JSON-compatible value supporting nested mappings."""

type JSONMapping = Mapping[str, JSONValue]
"""Immutable JSON mapping payload."""

type JSONMutableMapping = dict[str, JSONValue]
"""Mutable JSON mapping payload used for config entry data."""

type ConfigEntryData = JSONMutableMapping
"""Mutable configuration data stored on compatibility config entries."""

type ConfigEntryDataMapping = JSONMapping
"""Readonly view for compatibility config entry payloads."""

type ConfigEntryOptions = JSONMutableMapping
"""Mutable options payload stored on compatibility config entries."""

type TranslationPlaceholders = dict[str, str]
"""Translation placeholder mapping for compatibility error payloads."""

RuntimeT = TypeVar('RuntimeT')


def _build_exception(
    name: str,
    base: type[Exception],
    doc: str,
    extra_attrs: dict[str, object] | None = None,
) -> type[Exception]:
    """Create a lightweight exception class used when Home Assistant isn't available."""

    namespace: dict[str, object] = {'__doc__': doc}
    if extra_attrs:
        namespace.update(extra_attrs)
    return type(name, (base,), namespace)


def _import_optional(module: str) -> Any:
    try:  # pragma: no cover - executed when Home Assistant is installed
        return __import__(module, fromlist=['*'])
    except (ImportError, ModuleNotFoundError):
        return None


_ha_exceptions = _import_optional('homeassistant.exceptions')
_ha_config_entries = _import_optional('homeassistant.config_entries')
_ha_core = _import_optional('homeassistant.core')

type _ExceptionRebindCallback = Callable[[dict[str, type[Exception]]], None]

_EXCEPTION_REBIND_CALLBACKS: list[_ExceptionRebindCallback] = []

# Minimal registry mirroring Home Assistant's config flow handler mapping.
HANDLERS: dict[str, object] = {}


async def support_entry_unload(hass: Any, domain: str) -> bool:
    """Return ``True`` if the registered handler exposes an unload hook."""

    handler = HANDLERS.get(domain)
    return bool(handler and hasattr(handler, 'async_unload_entry'))


async def support_remove_from_device(hass: Any, domain: str) -> bool:
    """Return ``True`` if the handler exposes a remove-device hook."""

    handler = HANDLERS.get(domain)
    return bool(handler and hasattr(handler, 'async_remove_config_entry_device'))


@dataclass(slots=True)
class _BoundExceptionAlias:
    """Container describing an installed exception alias binding."""

    source: str
    module_name: str
    target: str
    combine_with_current: bool
    callback: _ExceptionRebindCallback


_BOUND_EXCEPTION_ALIASES: dict[tuple[str, str], _BoundExceptionAlias] = {}


def _current_exception_mapping() -> dict[str, type[Exception]]:
    """Return the latest Home Assistant exception bindings."""

    return {
        'HomeAssistantError': HomeAssistantError,
        'ConfigEntryError': ConfigEntryError,
        'ConfigEntryAuthFailed': ConfigEntryAuthFailed,
        'ConfigEntryNotReady': ConfigEntryNotReady,
        'ServiceValidationError': ServiceValidationError,
    }


def _notify_exception_callbacks() -> None:
    """Invoke registered callbacks with the refreshed exception mapping."""

    if not _EXCEPTION_REBIND_CALLBACKS:
        return

    mapping = _current_exception_mapping()
    for callback in tuple(_EXCEPTION_REBIND_CALLBACKS):
        try:
            callback(mapping)
        except Exception:  # pragma: no cover - defensive guard for test hooks
            continue


def register_exception_rebind_callback(
    callback: _ExceptionRebindCallback,
) -> Callable[[], None]:
    """Register a callback that fires whenever exception bindings change."""

    _EXCEPTION_REBIND_CALLBACKS.append(callback)
    callback(_current_exception_mapping())

    def _unregister() -> None:
        with suppress(ValueError):  # pragma: no branch - suppress missing callback
            _EXCEPTION_REBIND_CALLBACKS.remove(callback)

    return _unregister


def _resolve_binding_module(module: ModuleType | str | None) -> ModuleType:
    """Return the module that should receive a rebound alias."""

    if isinstance(module, ModuleType):
        return module

    if isinstance(module, str):
        resolved = sys.modules.get(module)
        if resolved is None:
            raise RuntimeError(
                f"bind_exception_alias could not locate module '{module}'",
            )
        return resolved

    frame = None
    try:
        frame = sys._getframe(2)
    except ValueError as exc:  # pragma: no cover - extremely defensive
        raise RuntimeError(
            'bind_exception_alias could not determine the caller module',
        ) from exc

    try:
        while frame is not None:
            module_name = frame.f_globals.get('__name__')
            if module_name and module_name != __name__:
                candidate = sys.modules.get(module_name)
                if candidate is not None:
                    return candidate
            frame = frame.f_back
    finally:
        del frame

    raise RuntimeError(
        'bind_exception_alias could not determine the caller module',
    )


def bind_exception_alias(
    name: str,
    *,
    module: ModuleType | str | None = None,
    attr: str | None = None,
    combine_with_current: bool = False,
) -> Callable[[], None]:
    """Keep ``module.attr`` in sync with the active Home Assistant class."""

    # ``module`` may be supplied as a module object, a module name, or omitted to
    # infer the caller.  The binding survives module reloads by resolving fresh
    # module objects from :data:`sys.modules` each time the callback fires.

    # Default to the caller's module so integration files can bind aliases
    # without importing ``sys`` purely for ``sys.modules[__name__]``.

    module_obj = _resolve_binding_module(module)

    target = attr or name
    module_name = getattr(module_obj, '__name__', None)
    if not module_name:
        raise RuntimeError('bind_exception_alias requires a named module')

    key = (module_name, target)

    previous = _BOUND_EXCEPTION_ALIASES.pop(key, None)
    if previous is not None:
        with suppress(ValueError):
            _EXCEPTION_REBIND_CALLBACKS.remove(previous.callback)

    bound: _BoundExceptionAlias | None = None

    def _unregister() -> None:
        stored = _BOUND_EXCEPTION_ALIASES.get(key)
        if stored is bound:
            _BOUND_EXCEPTION_ALIASES.pop(key, None)
        with suppress(ValueError):
            _EXCEPTION_REBIND_CALLBACKS.remove(_apply)

    def _apply(mapping: dict[str, type[Exception]]) -> None:
        current_module = sys.modules.get(module_name)
        if not isinstance(current_module, ModuleType):
            return

        namespace = current_module.__dict__
        candidate = mapping.get(name)
        if not isinstance(candidate, type) or not issubclass(candidate, Exception):
            return

        if combine_with_current:
            current = namespace.get(target)
            if isinstance(current, type) and current is not candidate:
                if issubclass(candidate, current):
                    namespace[target] = candidate
                    return
                if issubclass(current, candidate):
                    namespace[target] = current
                    return
                try:
                    namespace[target] = type(
                        f"PawControl{name}Alias",
                        (candidate, current),
                        {'__module__': module_name},
                    )
                except TypeError:
                    namespace[target] = candidate
                return

        namespace[target] = candidate

    bound = _BoundExceptionAlias(
        name,
        module_name,
        target,
        combine_with_current,
        _apply,
    )
    _BOUND_EXCEPTION_ALIASES[key] = bound
    _apply(_current_exception_mapping())
    _EXCEPTION_REBIND_CALLBACKS.append(_apply)
    return _unregister


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


class _FallbackHomeAssistantError(RuntimeError):
    """Fallback base error used when Home Assistant isn't installed."""


HomeAssistantError: type[Exception] = _FallbackHomeAssistantError
_HOMEASSISTANT_ERROR_IS_FALLBACK = True


# These globals are re-bound as soon as either Home Assistant or the unit test
# stubs import the integration module. Declaring them up-front keeps MyPy
# informed about the exported types while still allowing `_refresh_exception_
# symbols` to swap in the runtime variants when available.
ConfigEntryError: type[Exception]
ConfigEntryAuthFailed: type[Exception]
ConfigEntryNotReady: type[Exception]
ServiceValidationError: type[Exception]


def _config_entry_error_factory() -> type[Exception]:
    base = cast(type[Exception], HomeAssistantError)
    return type(
        'ConfigEntryError',
        (base,),
        {'__doc__': 'Fallback ConfigEntry error used outside Home Assistant.'},
    )


def _auth_failed_factory() -> type[Exception]:
    base = cast(type[Exception], ConfigEntryError)

    def _init(
        self: Any,
        message: str | None = None,
        *,
        auth_migration: bool | None = None,
    ) -> None:
        base.__init__(self, message)
        self.auth_migration = auth_migration

    namespace = {
        '__doc__': 'Fallback ConfigEntryAuthFailed stand-in.',
        '__slots__': ('auth_migration',),
        '__init__': _init,
    }
    return type('ConfigEntryAuthFailed', (base,), namespace)


def _not_ready_factory() -> type[Exception]:
    base = cast(type[Exception], ConfigEntryError)
    return type(
        'ConfigEntryNotReady',
        (base,),
        {'__doc__': 'Fallback ConfigEntryNotReady used when HA is unavailable.'},
    )


def _service_validation_error_factory() -> type[Exception]:
    base = cast(type[Exception], HomeAssistantError)
    return type(
        'ServiceValidationError',
        (base,),
        {'__doc__': 'Fallback validation error raised for invalid service payloads.'},
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
        candidate = getattr(exceptions_module, 'HomeAssistantError', None)
        if isinstance(candidate, type) and issubclass(candidate, Exception):
            resolved_homeassistant_error = cast(type[Exception], candidate)

    if resolved_homeassistant_error is None:
        HomeAssistantError = _FallbackHomeAssistantError
        _HOMEASSISTANT_ERROR_IS_FALLBACK = True
    else:
        HomeAssistantError = resolved_homeassistant_error
        _HOMEASSISTANT_ERROR_IS_FALLBACK = False

    ConfigEntryError = _get_exception(
        'ConfigEntryError',
        _config_entry_error_factory,
        exceptions_module,
    )
    ConfigEntryAuthFailed = _get_exception(
        'ConfigEntryAuthFailed',
        _auth_failed_factory,
        exceptions_module,
    )
    ConfigEntryNotReady = _get_exception(
        'ConfigEntryNotReady',
        _not_ready_factory,
        exceptions_module,
    )
    ServiceValidationError = _get_exception(
        'ServiceValidationError',
        _service_validation_error_factory,
        exceptions_module,
    )

    _notify_exception_callbacks()


def ensure_homeassistant_exception_symbols() -> None:
    """Ensure exception exports mirror the active Home Assistant module."""

    _refresh_exception_symbols(sys.modules.get('homeassistant.exceptions'))


ConfigEntryError = _config_entry_error_factory()
ConfigEntryAuthFailed = _auth_failed_factory()
ConfigEntryNotReady = _not_ready_factory()
ServiceValidationError = _service_validation_error_factory()

_refresh_exception_symbols(_ha_exceptions)


def _utcnow() -> datetime:
    """Return the current UTC time."""

    return datetime.now(tz=UTC)


class ConfigEntryState(Enum):
    """Minimal stand-in mirroring Home Assistant config entry states."""

    NOT_LOADED = ('not_loaded', True)
    LOADED = ('loaded', True)
    SETUP_IN_PROGRESS = ('setup_in_progress', False)
    SETUP_RETRY = ('setup_retry', True)
    SETUP_ERROR = ('setup_error', True)
    MIGRATION_ERROR = ('migration_error', False)
    FAILED_UNLOAD = ('failed_unload', False)
    UNLOAD_IN_PROGRESS = ('unload_in_progress', False)

    def __new__(cls, value: str, recoverable: bool) -> ConfigEntryState:
        """Create enum members that store the recoverability flag."""

        obj = object.__new__(cls)
        obj._value_ = value
        return obj

    def __init__(self, _value: str, recoverable: bool) -> None:
        """Store whether the state can be automatically recovered."""

        self._recoverable: bool = recoverable

    @property
    def recoverable(self) -> bool:
        """Return whether the state can be recovered without user intervention."""

        return self._recoverable

    @classmethod
    def from_value(cls, value: str) -> ConfigEntryState:
        """Return the enum member matching ``value`` regardless of casing."""

        try:
            return cls[value.upper()]
        except KeyError:
            for member in cls:
                if member.value == value:
                    return member
        raise ValueError(value)


class ConfigEntryChange(Enum):
    """Enum describing why a config entry update listener fired."""

    ADDED = 'added'
    REMOVED = 'removed'
    UPDATED = 'updated'


class ConfigSubentry:
    """Minimal compatibility stand-in for Home Assistant subentries."""

    def __init__(
        self,
        *,
        subentry_id: str,
        data: ConfigEntryDataMapping | None = None,
        subentry_type: str,
        title: str,
        unique_id: str | None = None,
    ) -> None:
        self.subentry_id = subentry_id
        self.data = dict(data or {})
        self.subentry_type = subentry_type
        self.title = title
        self.unique_id = unique_id


def _build_subentries(
    subentries_data: Iterable[ConfigEntryDataMapping] | None,
) -> dict[str, ConfigSubentry]:
    """Construct deterministic subentry placeholders."""

    subentries: dict[str, ConfigSubentry] = {}
    for index, subentry_data in enumerate(subentries_data or (), start=1):
        subentry_id = (
            str(subentry_data.get('subentry_id'))
            if 'subentry_id' in subentry_data
            else f"subentry_{index}"
        )
        raw_data = subentry_data.get('data', {})
        data_mapping = dict(raw_data) if isinstance(raw_data, Mapping) else {}
        raw_unique_id = subentry_data.get('unique_id')
        subentries[subentry_id] = ConfigSubentry(
            subentry_id=subentry_id,
            data=data_mapping,
            subentry_type=str(subentry_data.get('subentry_type', 'subentry')),
            title=str(subentry_data.get('title', subentry_id)),
            unique_id=str(
                raw_unique_id,
            )
            if raw_unique_id is not None
            else None,
        )

    return subentries


class ConfigEntry[RuntimeT]:  # type: ignore[override]
    """Lightweight ConfigEntry implementation for test environments."""

    _id_source = count(1)

    def __init__(
        self,
        entry_id: str | None = None,
        *,
        created_at: datetime | None = None,
        domain: str | None = None,
        data: ConfigEntryDataMapping | None = None,
        options: ConfigEntryDataMapping | None = None,
        discovery_keys: dict[str, tuple[object, ...]] | None = None,
        subentries_data: Iterable[ConfigEntryDataMapping] | None = None,
        title: str | None = None,
        source: str = 'user',
        version: int = 1,
        minor_version: int = 0,
        unique_id: str | None = None,
        pref_disable_new_entities: bool = False,
        pref_disable_polling: bool = False,
        pref_disable_discovery: bool = False,
        disabled_by: str | None = None,
        state: ConfigEntryState | str = ConfigEntryState.NOT_LOADED,
        supports_unload: bool | None = None,
        supports_remove_device: bool | None = None,
        supports_options: bool | None = None,
        supports_reconfigure: bool | None = None,
        supported_subentry_types: dict[str, dict[str, bool]] | None = None,
        reason: str | None = None,
        error_reason_translation_key: str | None = None,
        error_reason_translation_placeholders: TranslationPlaceholders | None = None,
        modified_at: datetime | None = None,
    ) -> None:
        """Initialize a shim config entry compatible with Home Assistant tests."""

        self.entry_id = entry_id or f"entry_{next(self._id_source)}"
        self.domain = domain or 'unknown'
        self.data: ConfigEntryData = dict(data or {})
        self.options: ConfigEntryOptions = dict(options or {})
        self.title = title or self.domain
        self.source = source
        self.version = version
        self.minor_version = minor_version
        self.unique_id = unique_id
        self.pref_disable_new_entities = pref_disable_new_entities
        self.pref_disable_polling = pref_disable_polling
        self.pref_disable_discovery = pref_disable_discovery
        self.disabled_by = disabled_by
        if isinstance(state, str):
            try:
                self.state = ConfigEntryState.from_value(state)
            except ValueError:
                self.state = ConfigEntryState[state.upper()]
        else:
            self.state = state
        self.discovery_keys = dict(discovery_keys or {})
        self.subentries = _build_subentries(subentries_data)
        self._supports_unload = supports_unload
        self._supports_remove_device = supports_remove_device
        self._supports_options = supports_options
        self._supports_reconfigure = supports_reconfigure
        self._supported_subentry_types = (
            dict(supported_subentry_types) if supported_subentry_types else None
        )
        self.reason = reason
        self.error_reason_translation_key = error_reason_translation_key
        self.error_reason_translation_placeholders: TranslationPlaceholders = dict(
            error_reason_translation_placeholders or {},
        )
        self.runtime_data: RuntimeT | None = None
        self.update_listeners: list[
            Callable[[Any, ConfigEntry[RuntimeT]], Awaitable[None] | None]
        ] = []
        self._on_unload: list[
            Callable[
                [],
                Coroutine[Any, Any, None] | None,
            ]
        ] = []
        self._async_cancel_retry_setup: Callable[[], Any] | None = None
        self._hass: Any | None = None
        self.created_at: datetime = created_at or _utcnow()
        self.modified_at: datetime = modified_at or self.created_at

    @property
    def supports_options(self) -> bool:
        """Return whether the entry exposes an options flow."""

        if self._supports_options is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, 'async_supports_options_flow'):
                self._supports_options = bool(
                    handler.async_supports_options_flow(self),
                )

        return bool(self._supports_options)

    @property
    def supports_unload(self) -> bool:
        """Return whether the entry exposes an unload hook."""

        if self._supports_unload is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, 'async_unload_entry'):
                self._supports_unload = True

        return bool(self._supports_unload)

    @property
    def supports_remove_device(self) -> bool:
        """Return whether the entry exposes a remove-device hook."""

        if self._supports_remove_device is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, 'async_remove_config_entry_device'):
                self._supports_remove_device = True

        return bool(self._supports_remove_device)

    @property
    def supports_reconfigure(self) -> bool:
        """Return whether the entry exposes a reconfigure flow."""

        if self._supports_reconfigure is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, 'async_supports_reconfigure_flow'):
                self._supports_reconfigure = bool(
                    handler.async_supports_reconfigure_flow(self),
                )

        return bool(self._supports_reconfigure)

    @property
    def supported_subentry_types(self) -> dict[str, dict[str, bool]]:
        """Return the supported subentry types mapping."""

        if self._supported_subentry_types is None:
            handler = HANDLERS.get(self.domain)
            if handler and hasattr(handler, 'async_get_supported_subentry_types'):
                supported_flows = handler.async_get_supported_subentry_types(
                    self,
                )
                self._supported_subentry_types = {
                    subentry_type: {
                        'supports_reconfigure': hasattr(
                            subentry_handler,
                            'async_step_reconfigure',
                        ),
                    }
                    for subentry_type, subentry_handler in supported_flows.items()
                }

        return self._supported_subentry_types or {}

    def add_to_hass(self, hass: Any) -> None:
        """Associate the entry with a Home Assistant instance."""

        self._hass = hass
        manager = getattr(
            getattr(hass, 'config_entries', None),
            '_entries',
            None,
        )
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
        self,
        callback: Callable[[], Coroutine[Any, Any, None] | None],
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
            if hasattr(result, '__await__'):
                await cast(Awaitable[Any], result)
        return True


def _should_use_module_entry(entry_cls: Any) -> bool:
    """Return ``True`` if the imported ConfigEntry already exposes HA semantics."""

    if not isinstance(entry_cls, type):
        return False

    init = getattr(entry_cls, '__init__', None)
    if init is None:
        return False

    try:
        signature = inspect.signature(init)  # type: ignore[arg-type]
    except (TypeError, ValueError):  # pragma: no cover - signature unavailable
        return False

    parameter_names = {parameter.name for parameter in signature.parameters.values()}
    return {'domain', 'entry_id'}.issubset(parameter_names)


def _is_enum_type(value: Any) -> bool:
    """Return ``True`` if ``value`` is an :class:`Enum` subclass."""

    return isinstance(value, type) and issubclass(value, Enum)


def _sync_config_entry_symbols(
    config_entries_module: Any | None,
    core_module: Any | None,
) -> None:
    """Ensure Home Assistant modules expose the compatibility ConfigEntry types."""

    # The compatibility layer needs to operate in two very different execution
    # environments:
    #
    # 1. When the integration runs inside Home Assistant we should defer to the
    #    real ``ConfigEntry`` implementation that ships with HA so that we do
    #    not accidentally diverge from core behaviour.
    # 2. When tests import PawControl without Home Assistant installed we fall
    #    back to the lightweight shim defined in this module.  In that
    #    situation multiple imports may race each other, so we patch both the
    #    module globals and the ``homeassistant`` namespaces to ensure every
    #    caller sees the same symbols.
    #
    # The branching below therefore checks whether a real Home Assistant
    # implementation is available and, if not, injects the compatibility
    # classes in the places the rest of the codebase expects to find them.
    if config_entries_module is not None:
        module_entry_cls = getattr(config_entries_module, 'ConfigEntry', None)
        if _should_use_module_entry(module_entry_cls):
            globals()['ConfigEntry'] = cast(type[Any], module_entry_cls)
        else:
            config_entries_module.ConfigEntry = ConfigEntry

        module_state = getattr(config_entries_module, 'ConfigEntryState', None)
        if _is_enum_type(module_state):
            globals()['ConfigEntryState'] = cast(type[Enum], module_state)
        else:
            config_entries_module.ConfigEntryState = ConfigEntryState

        module_change = getattr(
            config_entries_module,
            'ConfigEntryChange',
            None,
        )
        if _is_enum_type(module_change):
            globals()['ConfigEntryChange'] = cast(type[Enum], module_change)
        else:
            config_entries_module.ConfigEntryChange = ConfigEntryChange

    if core_module is not None:
        module_entry_cls = getattr(core_module, 'ConfigEntry', None)
        if _should_use_module_entry(module_entry_cls):
            globals()['ConfigEntry'] = cast(type[Any], module_entry_cls)
        else:
            core_module.ConfigEntry = ConfigEntry

        state_cls = getattr(core_module, 'ConfigEntryState', None)
        if _is_enum_type(state_cls):
            globals()['ConfigEntryState'] = cast(type[Enum], state_cls)
        else:
            core_module.ConfigEntryState = ConfigEntryState

        change_cls = getattr(core_module, 'ConfigEntryChange', None)
        if _is_enum_type(change_cls):
            globals()['ConfigEntryChange'] = cast(type[Enum], change_cls)
        else:
            core_module.ConfigEntryChange = ConfigEntryChange


_sync_config_entry_symbols(_ha_config_entries, _ha_core)


def ensure_homeassistant_config_entry_symbols() -> None:
    """Re-apply ConfigEntry exports when Home Assistant stubs are installed late."""

    _sync_config_entry_symbols(
        sys.modules.get('homeassistant.config_entries'),
        sys.modules.get('homeassistant.core'),
    )


def _fallback_service_registry() -> type[Any]:
    if _ha_core is not None:
        registry = getattr(_ha_core, 'ServiceRegistry', None)
        if isinstance(registry, type):  # pragma: no cover - prefer HA implementation
            return registry

    @dataclass
    class _ServiceCall:
        domain: str
        service: str
        data: JSONMapping

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
            data: JSONMapping | None = None,
        ) -> None:
            handler = self._services.get(domain, {}).get(service)
            if handler is None:
                raise KeyError(f"Service {domain}.{service} not registered")
            result = handler(_ServiceCall(domain, service, data or {}))
            if hasattr(result, '__await__'):
                await cast(Awaitable[Any], result)

        def async_services(self) -> dict[str, dict[str, Callable[..., Any]]]:
            return self._services

        def has_service(self, domain: str, service: str) -> bool:
            return service in self._services.get(domain, {})

    return ServiceRegistry


ServiceRegistry = _fallback_service_registry()


__all__ = [
    'HANDLERS',
    'ConfigEntry',
    'ConfigEntryAuthFailed',
    'ConfigEntryChange',
    'ConfigEntryError',
    'ConfigEntryNotReady',
    'ConfigEntryState',
    'ConfigSubentry',
    'HomeAssistantError',
    'ServiceRegistry',
    'ServiceValidationError',
    'bind_exception_alias',
    'ensure_homeassistant_config_entry_symbols',
    'ensure_homeassistant_exception_symbols',
    'register_exception_rebind_callback',
    'support_entry_unload',
    'support_remove_from_device',
]
