"""Compatibility helpers that keep the integration functional without Home Assistant."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
import inspect
from itertools import count
import sys
from types import ModuleType
from typing import Any, Final, TypeVar, cast

type JSONPrimitive = None | bool | int | float | str
"""Primitive JSON-compatible value."""

type JSONValue = JSONPrimitive | Sequence["JSONValue"] | Mapping[str, "JSONValue"]
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

RuntimeT = TypeVar("RuntimeT")


def _build_exception(
  name: str,
  base: type[Exception],
  doc: str,
  extra_attrs: dict[str, object] | None = None,
) -> type[Exception]:
  """Create a lightweight exception class used when Home Assistant isn't available."""  # noqa: E111

  namespace: dict[str, object] = {"__doc__": doc}  # noqa: E111
  if extra_attrs:  # noqa: E111
    namespace.update(extra_attrs)
  return type(name, (base,), namespace)  # noqa: E111


def _import_optional(module_name: str) -> ModuleType | None:
  """Import a module when available, returning ``None`` in fallback mode."""  # noqa: E111

  try:  # noqa: E111
    return __import__(module_name, fromlist=["*"])
  except ImportError, ModuleNotFoundError:  # noqa: E111
    return None


_ha_exceptions = _import_optional("homeassistant.exceptions")
_ha_config_entries = _import_optional("homeassistant.config_entries")
_ha_core = _import_optional("homeassistant.core")
_ha_const = _import_optional("homeassistant.const")

if _ha_const is not None and hasattr(_ha_const, "UnitOfMass"):
  UnitOfMass = _ha_const.UnitOfMass  # noqa: E111
  _mass_grams = UnitOfMass.GRAMS  # noqa: E111
  _mass_kilograms = UnitOfMass.KILOGRAMS  # noqa: E111
else:

  class _FallbackUnitOfMass:  # noqa: E111
    GRAMS = "g"
    KILOGRAMS = "kg"

  UnitOfMass = _FallbackUnitOfMass  # noqa: E111
  _mass_grams = UnitOfMass.GRAMS  # noqa: E111
  _mass_kilograms = UnitOfMass.KILOGRAMS  # noqa: E111

MASS_GRAMS: Final[str] = str(_mass_grams)
MASS_KILOGRAMS: Final[str] = str(_mass_kilograms)

type _ExceptionRebindCallback = Callable[[dict[str, type[Exception]]], None]

_EXCEPTION_REBIND_CALLBACKS: list[_ExceptionRebindCallback] = []

# Minimal registry mirroring Home Assistant's config flow handler mapping.
HANDLERS: dict[str, object] = {}


async def support_entry_unload(hass: Any, domain: str) -> bool:
  """Return ``True`` if the registered handler exposes an unload hook."""  # noqa: E111

  handler = HANDLERS.get(domain)  # noqa: E111
  return bool(handler and hasattr(handler, "async_unload_entry"))  # noqa: E111


async def support_remove_from_device(hass: Any, domain: str) -> bool:
  """Return ``True`` if the handler exposes a remove-device hook."""  # noqa: E111

  handler = HANDLERS.get(domain)  # noqa: E111
  return bool(handler and hasattr(handler, "async_remove_config_entry_device"))  # noqa: E111


@dataclass(slots=True)
class _BoundExceptionAlias:
  """Container describing an installed exception alias binding."""  # noqa: E111

  source: str  # noqa: E111
  module_name: str  # noqa: E111
  target: str  # noqa: E111
  combine_with_current: bool  # noqa: E111
  callback: _ExceptionRebindCallback  # noqa: E111


_BOUND_EXCEPTION_ALIASES: dict[tuple[str, str], _BoundExceptionAlias] = {}


def _current_exception_mapping() -> dict[str, type[Exception]]:
  """Return the latest Home Assistant exception bindings."""  # noqa: E111

  return {  # noqa: E111
    "HomeAssistantError": HomeAssistantError,
    "ConfigEntryError": ConfigEntryError,
    "ConfigEntryAuthFailed": ConfigEntryAuthFailed,
    "ConfigEntryNotReady": ConfigEntryNotReady,
    "ServiceValidationError": ServiceValidationError,
  }


def _notify_exception_callbacks() -> None:
  """Invoke registered callbacks with the refreshed exception mapping."""  # noqa: E111

  if not _EXCEPTION_REBIND_CALLBACKS:  # noqa: E111
    return

  mapping = _current_exception_mapping()  # noqa: E111
  for callback in tuple(_EXCEPTION_REBIND_CALLBACKS):  # noqa: E111
    try:
      callback(mapping)  # noqa: E111
    except Exception:  # pragma: no cover - defensive guard for test hooks
      continue  # noqa: E111


def register_exception_rebind_callback(
  callback: _ExceptionRebindCallback,
) -> Callable[[], None]:
  """Register a callback that fires whenever exception bindings change."""  # noqa: E111

  _EXCEPTION_REBIND_CALLBACKS.append(callback)  # noqa: E111
  callback(_current_exception_mapping())  # noqa: E111

  def _unregister() -> None:  # noqa: E111
    with suppress(ValueError):  # pragma: no branch - suppress missing callback
      _EXCEPTION_REBIND_CALLBACKS.remove(callback)  # noqa: E111

  return _unregister  # noqa: E111


def _resolve_binding_module(module: ModuleType | str | None) -> ModuleType:
  """Return the module that should receive a rebound alias."""  # noqa: E111

  if isinstance(module, ModuleType):  # noqa: E111
    return module

  if isinstance(module, str):  # noqa: E111
    resolved = sys.modules.get(module)
    if resolved is None:
      raise RuntimeError(  # noqa: E111
        f"bind_exception_alias could not locate module '{module}'",
      )
    return resolved

  frame = None  # noqa: E111
  try:  # noqa: E111
    frame = sys._getframe(2)
  except ValueError as exc:  # pragma: no cover - extremely defensive  # noqa: E111
    raise RuntimeError(
      "bind_exception_alias could not determine the caller module",
    ) from exc

  try:  # noqa: E111
    while frame is not None:
      module_name = frame.f_globals.get("__name__")  # noqa: E111
      if module_name and module_name != __name__:  # noqa: E111
        candidate = sys.modules.get(module_name)
        if candidate is not None:
          return candidate  # noqa: E111
      frame = frame.f_back  # noqa: E111
  finally:  # noqa: E111
    del frame

  raise RuntimeError(  # noqa: E111
    "bind_exception_alias could not determine the caller module",
  )


def bind_exception_alias(
  name: str,
  *,
  module: ModuleType | str | None = None,
  attr: str | None = None,
  combine_with_current: bool = False,
) -> Callable[[], None]:
  """Keep ``module.attr`` in sync with the active Home Assistant class."""  # noqa: E111

  # ``module`` may be supplied as a module object, a module name, or omitted to  # noqa: E114, E501
  # infer the caller.  The binding survives module reloads by resolving fresh  # noqa: E114, E501
  # module objects from :data:`sys.modules` each time the callback fires.  # noqa: E114

  # Default to the caller's module so integration files can bind aliases  # noqa: E114
  # without importing ``sys`` purely for ``sys.modules[__name__]``.  # noqa: E114

  module_obj = _resolve_binding_module(module)  # noqa: E111

  target = attr or name  # noqa: E111
  module_name = getattr(module_obj, "__name__", None)  # noqa: E111
  if not module_name:  # noqa: E111
    raise RuntimeError("bind_exception_alias requires a named module")

  key = (module_name, target)  # noqa: E111

  previous = _BOUND_EXCEPTION_ALIASES.pop(key, None)  # noqa: E111
  if previous is not None:  # noqa: E111
    with suppress(ValueError):
      _EXCEPTION_REBIND_CALLBACKS.remove(previous.callback)  # noqa: E111

  bound: _BoundExceptionAlias | None = None  # noqa: E111

  def _unregister() -> None:  # noqa: E111
    stored = _BOUND_EXCEPTION_ALIASES.get(key)
    if stored is bound:
      _BOUND_EXCEPTION_ALIASES.pop(key, None)  # noqa: E111
    with suppress(ValueError):
      _EXCEPTION_REBIND_CALLBACKS.remove(_apply)  # noqa: E111

  def _apply(mapping: dict[str, type[Exception]]) -> None:  # noqa: E111
    current_module = sys.modules.get(module_name)
    if not isinstance(current_module, ModuleType):
      return  # noqa: E111

    namespace = current_module.__dict__
    candidate = mapping.get(name)
    if not isinstance(candidate, type) or not issubclass(candidate, Exception):
      return  # noqa: E111

    if combine_with_current:
      current = namespace.get(target)  # noqa: E111
      if isinstance(current, type) and current is not candidate:  # noqa: E111
        if issubclass(candidate, current):
          namespace[target] = candidate  # noqa: E111
          return  # noqa: E111
        if issubclass(current, candidate):
          namespace[target] = current  # noqa: E111
          return  # noqa: E111
        try:
          namespace[target] = type(  # noqa: E111
            f"PawControl{name}Alias",
            (candidate, current),
            {"__module__": module_name},
          )
        except TypeError:
          namespace[target] = candidate  # noqa: E111
        return

    namespace[target] = candidate

  bound = _BoundExceptionAlias(  # noqa: E111
    name,
    module_name,
    target,
    combine_with_current,
    _apply,
  )
  _BOUND_EXCEPTION_ALIASES[key] = bound  # noqa: E111
  _apply(_current_exception_mapping())  # noqa: E111
  _EXCEPTION_REBIND_CALLBACKS.append(_apply)  # noqa: E111
  return _unregister  # noqa: E111


def _get_exception(
  name: str,
  default_factory: Callable[[], type[Exception]],
  exceptions_module: ModuleType | None = None,
) -> type[Exception]:
  """Return an exception class from Home Assistant or build a fallback."""  # noqa: E111

  module = exceptions_module if exceptions_module is not None else _ha_exceptions  # noqa: E111
  if module is None:  # noqa: E111
    return default_factory()

  attr = getattr(module, name, None)  # noqa: E111
  if isinstance(attr, type) and issubclass(attr, Exception):  # noqa: E111
    return cast(type[Exception], attr)

  return default_factory()  # noqa: E111


class _FallbackHomeAssistantError(RuntimeError):
  """Fallback base error used when Home Assistant isn't installed."""  # noqa: E111


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
  base = cast(type[Exception], HomeAssistantError)  # noqa: E111
  return type(  # noqa: E111
    "ConfigEntryError",
    (base,),
    {"__doc__": "Fallback ConfigEntry error used outside Home Assistant."},
  )


def _auth_failed_factory() -> type[Exception]:
  base = cast(type[Exception], ConfigEntryError)  # noqa: E111

  def _init(  # noqa: E111
    self: Any,
    message: str | None = None,
    *,
    auth_migration: bool | None = None,
  ) -> None:
    base.__init__(self, message)
    self.auth_migration = auth_migration

  namespace = {  # noqa: E111
    "__doc__": "Fallback ConfigEntryAuthFailed stand-in.",
    "__slots__": ("auth_migration",),
    "__init__": _init,
  }
  return type("ConfigEntryAuthFailed", (base,), namespace)  # noqa: E111


def _not_ready_factory() -> type[Exception]:
  base = cast(type[Exception], ConfigEntryError)  # noqa: E111
  return type(  # noqa: E111
    "ConfigEntryNotReady",
    (base,),
    {"__doc__": "Fallback ConfigEntryNotReady used when HA is unavailable."},
  )


def _service_validation_error_factory() -> type[Exception]:
  base = cast(type[Exception], HomeAssistantError)  # noqa: E111
  return type(  # noqa: E111
    "ServiceValidationError",
    (base,),
    {"__doc__": "Fallback validation error raised for invalid service payloads."},
  )


def _refresh_exception_symbols(exceptions_module: ModuleType | None) -> None:
  """Refresh exported exception classes when Home Assistant stubs appear."""  # noqa: E111

  global _ha_exceptions  # noqa: E111
  global HomeAssistantError  # noqa: E111
  global _HOMEASSISTANT_ERROR_IS_FALLBACK  # noqa: E111
  global ConfigEntryError  # noqa: E111
  global ConfigEntryAuthFailed  # noqa: E111
  global ConfigEntryNotReady  # noqa: E111
  global ServiceValidationError  # noqa: E111

  _ha_exceptions = exceptions_module  # noqa: E111

  resolved_homeassistant_error: type[Exception] | None = None  # noqa: E111
  if exceptions_module is not None:  # noqa: E111
    candidate = getattr(exceptions_module, "HomeAssistantError", None)
    if isinstance(candidate, type) and issubclass(candidate, Exception):
      resolved_homeassistant_error = cast(type[Exception], candidate)  # noqa: E111

  if resolved_homeassistant_error is None:  # noqa: E111
    HomeAssistantError = _FallbackHomeAssistantError
    _HOMEASSISTANT_ERROR_IS_FALLBACK = True
  else:  # noqa: E111
    HomeAssistantError = resolved_homeassistant_error
    _HOMEASSISTANT_ERROR_IS_FALLBACK = False

  ConfigEntryError = _get_exception(  # noqa: E111
    "ConfigEntryError",
    _config_entry_error_factory,
    exceptions_module,
  )
  ConfigEntryAuthFailed = _get_exception(  # noqa: E111
    "ConfigEntryAuthFailed",
    _auth_failed_factory,
    exceptions_module,
  )
  ConfigEntryNotReady = _get_exception(  # noqa: E111
    "ConfigEntryNotReady",
    _not_ready_factory,
    exceptions_module,
  )
  ServiceValidationError = _get_exception(  # noqa: E111
    "ServiceValidationError",
    _service_validation_error_factory,
    exceptions_module,
  )

  _notify_exception_callbacks()  # noqa: E111


def ensure_homeassistant_exception_symbols() -> None:
  """Ensure exception exports mirror the active Home Assistant module."""  # noqa: E111

  _refresh_exception_symbols(sys.modules.get("homeassistant.exceptions"))  # noqa: E111


ConfigEntryError = _config_entry_error_factory()
ConfigEntryAuthFailed = _auth_failed_factory()
ConfigEntryNotReady = _not_ready_factory()
ServiceValidationError = _service_validation_error_factory()

_refresh_exception_symbols(_ha_exceptions)


def _utcnow() -> datetime:
  """Return the current UTC time."""  # noqa: E111

  return datetime.now(tz=UTC)  # noqa: E111


class ConfigEntryState(Enum):
  """Minimal stand-in mirroring Home Assistant config entry states."""  # noqa: E111

  NOT_LOADED = ("not_loaded", True)  # noqa: E111
  LOADED = ("loaded", True)  # noqa: E111
  SETUP_IN_PROGRESS = ("setup_in_progress", False)  # noqa: E111
  SETUP_RETRY = ("setup_retry", True)  # noqa: E111
  SETUP_ERROR = ("setup_error", True)  # noqa: E111
  MIGRATION_ERROR = ("migration_error", False)  # noqa: E111
  FAILED_UNLOAD = ("failed_unload", False)  # noqa: E111
  UNLOAD_IN_PROGRESS = ("unload_in_progress", False)  # noqa: E111

  def __new__(cls, value: str, recoverable: bool) -> ConfigEntryState:  # noqa: E111
    """Create enum members that store the recoverability flag."""

    obj = object.__new__(cls)
    obj._value_ = value
    return obj

  def __init__(self, _value: str, recoverable: bool) -> None:  # noqa: E111
    """Store whether the state can be automatically recovered."""

    self._recoverable: bool = recoverable

  @property  # noqa: E111
  def recoverable(self) -> bool:  # noqa: E111
    """Return whether the state can be recovered without user intervention."""

    return self._recoverable

  @classmethod  # noqa: E111
  def from_value(cls, value: str) -> ConfigEntryState:  # noqa: E111
    """Return the enum member matching ``value`` regardless of casing."""

    try:
      return cls[value.upper()]  # noqa: E111
    except KeyError:
      for member in cls:  # noqa: E111
        if member.value == value:
          return member  # noqa: E111
    raise ValueError(value)


class ConfigEntryChange(Enum):
  """Enum describing why a config entry update listener fired."""  # noqa: E111

  ADDED = "added"  # noqa: E111
  REMOVED = "removed"  # noqa: E111
  UPDATED = "updated"  # noqa: E111


class ConfigSubentry:
  """Minimal compatibility stand-in for Home Assistant subentries."""  # noqa: E111

  def __init__(  # noqa: E111
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
  """Construct deterministic subentry placeholders."""  # noqa: E111

  subentries: dict[str, ConfigSubentry] = {}  # noqa: E111
  for index, subentry_data in enumerate(subentries_data or (), start=1):  # noqa: E111
    subentry_id = (
      str(subentry_data.get("subentry_id"))
      if "subentry_id" in subentry_data
      else f"subentry_{index}"
    )
    raw_data = subentry_data.get("data", {})
    data_mapping = dict(raw_data) if isinstance(raw_data, Mapping) else {}
    raw_unique_id = subentry_data.get("unique_id")
    subentries[subentry_id] = ConfigSubentry(
      subentry_id=subentry_id,
      data=data_mapping,
      subentry_type=str(subentry_data.get("subentry_type", "subentry")),
      title=str(subentry_data.get("title", subentry_id)),
      unique_id=str(
        raw_unique_id,
      )
      if raw_unique_id is not None
      else None,
    )

  return subentries  # noqa: E111


class ConfigEntry[RuntimeT]:  # type: ignore[override]
  """Lightweight ConfigEntry implementation for test environments."""  # noqa: E111

  _id_source = count(1)  # noqa: E111

  def __init__(  # noqa: E111
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
    source: str = "user",
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
    self.domain = domain or "unknown"
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
      try:  # noqa: E111
        self.state = ConfigEntryState.from_value(state)
      except ValueError:  # noqa: E111
        self.state = ConfigEntryState[state.upper()]
    else:
      self.state = state  # noqa: E111
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

  @property  # noqa: E111
  def supports_options(self) -> bool:  # noqa: E111
    """Return whether the entry exposes an options flow."""

    return self._resolve_supports_flag(
      "_supports_options",
      "async_supports_options_flow",
      call_handler=True,
    )

  @property  # noqa: E111
  def supports_unload(self) -> bool:  # noqa: E111
    """Return whether the entry exposes an unload hook."""

    return self._resolve_supports_flag("_supports_unload", "async_unload_entry")

  @property  # noqa: E111
  def supports_remove_device(self) -> bool:  # noqa: E111
    """Return whether the entry exposes a remove-device hook."""

    return self._resolve_supports_flag(
      "_supports_remove_device",
      "async_remove_config_entry_device",
    )

  @property  # noqa: E111
  def supports_reconfigure(self) -> bool:  # noqa: E111
    """Return whether the entry exposes a reconfigure flow."""

    return self._resolve_supports_flag(
      "_supports_reconfigure",
      "async_supports_reconfigure_flow",
      call_handler=True,
    )

  @property  # noqa: E111
  def supported_subentry_types(self) -> dict[str, dict[str, bool]]:  # noqa: E111
    """Return the supported subentry types mapping."""

    if self._supported_subentry_types is not None:
      return self._supported_subentry_types  # noqa: E111

    handler = HANDLERS.get(self.domain)
    if not handler or not hasattr(handler, "async_get_supported_subentry_types"):
      return {}  # noqa: E111

    supported_flows = handler.async_get_supported_subentry_types(self)
    self._supported_subentry_types = {
      subentry_type: {
        "supports_reconfigure": hasattr(
          subentry_handler,
          "async_step_reconfigure",
        ),
      }
      for subentry_type, subentry_handler in supported_flows.items()
    }
    return self._supported_subentry_types

  def _resolve_supports_flag(  # noqa: E111
    self,
    attr_name: str,
    handler_attribute: str,
    *,
    call_handler: bool = False,
  ) -> bool:
    current = getattr(self, attr_name)
    if current is not None:
      return current  # noqa: E111

    handler = HANDLERS.get(self.domain)
    if not handler or not hasattr(handler, handler_attribute):
      return False  # noqa: E111

    current = bool(getattr(handler, handler_attribute)(self)) if call_handler else True
    setattr(self, attr_name, current)
    return current

  def add_to_hass(self, hass: Any) -> None:  # noqa: E111
    """Associate the entry with a Home Assistant instance."""

    self._hass = hass
    manager = getattr(
      getattr(hass, "config_entries", None),
      "_entries",
      None,
    )
    if isinstance(manager, dict):  # pragma: no branch - test helper hook
      manager[self.entry_id] = self  # noqa: E111

  def add_update_listener(  # noqa: E111
    self,
    listener: Callable[[Any, ConfigEntry[RuntimeT]], Awaitable[None] | None],
  ) -> Callable[[], None]:
    """Register a callback for config entry updates."""

    self.update_listeners.append(listener)

    def _remove() -> None:
      if listener in self.update_listeners:  # noqa: E111
        self.update_listeners.remove(listener)

    return _remove

  def async_on_unload(  # noqa: E111
    self,
    callback: Callable[[], Coroutine[Any, Any, None] | None],
  ) -> Callable[[], Coroutine[Any, Any, None] | None]:
    """Register a callback invoked when the entry unloads."""

    self._on_unload.append(callback)
    return callback

  async def async_setup(  # noqa: E111
    self, hass: Any
  ) -> bool:  # pragma: no cover - helper
    """Mark the entry as loaded when set up in tests."""

    self._hass = hass
    self.state = ConfigEntryState.LOADED
    return True

  async def async_unload(self, hass: Any | None = None) -> bool:  # noqa: E111
    """Mark the entry as not loaded and invoke unload callbacks."""

    self.state = ConfigEntryState.NOT_LOADED
    for callback in list(self._on_unload):
      result = callback()  # noqa: E111
      if hasattr(result, "__await__"):  # noqa: E111
        await cast(Awaitable[Any], result)
    return True


def _should_use_module_entry(entry_cls: Any) -> bool:
  """Return ``True`` if the imported ConfigEntry already exposes HA semantics."""  # noqa: E111

  if not isinstance(entry_cls, type):  # noqa: E111
    return False

  init = getattr(entry_cls, "__init__", None)  # noqa: E111
  if init is None:  # noqa: E111
    return False

  try:  # noqa: E111
    signature = inspect.signature(init)  # type: ignore[arg-type]
  except ValueError:  # pragma: no cover - signature unavailable  # noqa: E111
    return False
  except TypeError:  # pragma: no cover - signature unavailable  # noqa: E111
    return False

  parameter_names = {parameter.name for parameter in signature.parameters.values()}  # noqa: E111
  return {"domain", "entry_id"}.issubset(parameter_names)  # noqa: E111


def _is_enum_type(value: Any) -> bool:
  """Return ``True`` if ``value`` is an :class:`Enum` subclass."""  # noqa: E111

  return isinstance(value, type) and issubclass(value, Enum)  # noqa: E111


def _sync_config_entry_symbols(
  config_entries_module: Any | None,
  core_module: Any | None,
) -> None:
  """Ensure Home Assistant modules expose the compatibility ConfigEntry types."""  # noqa: E111

  # The compatibility layer needs to operate in two very different execution  # noqa: E114, E501
  # environments:  # noqa: E114
  #  # noqa: E114
  # 1. When the integration runs inside Home Assistant we should defer to the  # noqa: E114, E501
  #    real ``ConfigEntry`` implementation that ships with HA so that we do  # noqa: E114, E501
  #    not accidentally diverge from core behaviour.  # noqa: E114
  # 2. When tests import PawControl without Home Assistant installed we fall  # noqa: E114, E501
  #    back to the lightweight shim defined in this module.  In that  # noqa: E114
  #    situation multiple imports may race each other, so we patch both the  # noqa: E114, E501
  #    module globals and the ``homeassistant`` namespaces to ensure every  # noqa: E114
  #    caller sees the same symbols.  # noqa: E114
  #  # noqa: E114
  # The branching below therefore checks whether a real Home Assistant  # noqa: E114
  # implementation is available and, if not, injects the compatibility  # noqa: E114
  # classes in the places the rest of the codebase expects to find them.  # noqa: E114
  if config_entries_module is not None:  # noqa: E111
    module_entry_cls = getattr(config_entries_module, "ConfigEntry", None)
    if _should_use_module_entry(module_entry_cls):
      globals()["ConfigEntry"] = cast(type[Any], module_entry_cls)  # noqa: E111
    else:
      config_entries_module.ConfigEntry = ConfigEntry  # noqa: E111

    module_state = getattr(config_entries_module, "ConfigEntryState", None)
    if _is_enum_type(module_state):
      globals()["ConfigEntryState"] = cast(type[Enum], module_state)  # noqa: E111
    else:
      config_entries_module.ConfigEntryState = ConfigEntryState  # noqa: E111

    module_change = getattr(
      config_entries_module,
      "ConfigEntryChange",
      None,
    )
    if _is_enum_type(module_change):
      globals()["ConfigEntryChange"] = cast(type[Enum], module_change)  # noqa: E111
    else:
      config_entries_module.ConfigEntryChange = ConfigEntryChange  # noqa: E111

  if core_module is not None:  # noqa: E111
    module_entry_cls = getattr(core_module, "ConfigEntry", None)
    if _should_use_module_entry(module_entry_cls):
      globals()["ConfigEntry"] = cast(type[Any], module_entry_cls)  # noqa: E111
    else:
      core_module.ConfigEntry = ConfigEntry  # noqa: E111

    state_cls = getattr(core_module, "ConfigEntryState", None)
    if _is_enum_type(state_cls):
      globals()["ConfigEntryState"] = cast(type[Enum], state_cls)  # noqa: E111
    else:
      core_module.ConfigEntryState = ConfigEntryState  # noqa: E111

    change_cls = getattr(core_module, "ConfigEntryChange", None)
    if _is_enum_type(change_cls):
      globals()["ConfigEntryChange"] = cast(type[Enum], change_cls)  # noqa: E111
    else:
      core_module.ConfigEntryChange = ConfigEntryChange  # noqa: E111


_sync_config_entry_symbols(_ha_config_entries, _ha_core)


def ensure_homeassistant_config_entry_symbols() -> None:
  """Re-apply ConfigEntry exports when Home Assistant stubs are installed late."""  # noqa: E111

  _sync_config_entry_symbols(  # noqa: E111
    sys.modules.get("homeassistant.config_entries"),
    sys.modules.get("homeassistant.core"),
  )


def _fallback_service_registry() -> type[Any]:
  if _ha_core is not None:  # noqa: E111
    registry = getattr(_ha_core, "ServiceRegistry", None)
    if isinstance(registry, type):  # pragma: no cover - prefer HA implementation
      return registry  # noqa: E111

  @dataclass  # noqa: E111
  class _ServiceCall:  # noqa: E111
    domain: str
    service: str
    data: JSONMapping

  class ServiceRegistry:  # noqa: E111
    """Simplified service registry for offline test environments."""

    def __init__(self) -> None:
      self._services: dict[str, dict[str, Callable[..., Any]]] = {}  # noqa: E111

    def async_register(
      self,
      domain: str,
      service: str,
      handler: Callable[..., Any],
      schema: Any | None = None,
    ) -> None:
      self._services.setdefault(domain, {})[service] = handler  # noqa: E111

    async def async_call(
      self,
      domain: str,
      service: str,
      data: JSONMapping | None = None,
    ) -> None:
      handler = self._services.get(domain, {}).get(service)  # noqa: E111
      if handler is None:  # noqa: E111
        raise KeyError(f"Service {domain}.{service} not registered")
      result = handler(_ServiceCall(domain, service, data or {}))  # noqa: E111
      if hasattr(result, "__await__"):  # noqa: E111
        await cast(Awaitable[Any], result)

    def async_services(self) -> dict[str, dict[str, Callable[..., Any]]]:
      return self._services  # noqa: E111

    def has_service(self, domain: str, service: str) -> bool:
      return service in self._services.get(domain, {})  # noqa: E111

  return ServiceRegistry  # noqa: E111


ServiceRegistry = _fallback_service_registry()


__all__ = [
  "HANDLERS",
  "ConfigEntry",
  "ConfigEntryAuthFailed",
  "ConfigEntryChange",
  "ConfigEntryError",
  "ConfigEntryNotReady",
  "ConfigEntryState",
  "ConfigSubentry",
  "HomeAssistantError",
  "ServiceRegistry",
  "ServiceValidationError",
  "UnitOfMass",
  "bind_exception_alias",
  "ensure_homeassistant_config_entry_symbols",
  "ensure_homeassistant_exception_symbols",
  "register_exception_rebind_callback",
  "support_entry_unload",
  "support_remove_from_device",
]
