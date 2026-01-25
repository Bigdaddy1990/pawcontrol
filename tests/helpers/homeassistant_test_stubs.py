"""Home Assistant compatibility shims for PawControl's test suite."""

from __future__ import annotations

import asyncio
import builtins
import importlib
import re
import sys
import types
from collections.abc import Callable, Iterable
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any, Generic, TypeVar
from unittest.mock import AsyncMock

import voluptuous as vol
__all__ = [
  "ConfigEntry",
  "ConfigEntryAuthFailed",
  "ConfigEntryNotReady",
  "ConfigEntryState",
  "ConfigSubentry",
  "HomeAssistantError",
  "IssueSeverity",
  "MutableFlowResultDict",
  "Platform",
  "RestoreEntity",
  "install_homeassistant_stubs",
  "support_entry_unload",
  "support_remove_from_device",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = REPO_ROOT / "custom_components"
PAWCONTROL_ROOT = COMPONENT_ROOT / "pawcontrol"

_DEVICE_REGISTRY: DeviceRegistry | None = None
_ENTITY_REGISTRY: EntityRegistry | None = None
_ISSUE_REGISTRY: IssueRegistry | None = None
HOME_ASSISTANT_VERSION = "2025.1.0"


def _utcnow() -> datetime:
  """Return a timezone-aware UTC timestamp."""

  return datetime.now(UTC)


def _now() -> datetime:
  """Return a timezone-aware current timestamp."""

  return datetime.now(UTC)


def _parse_datetime(value: str | None) -> datetime | None:
  """Parse ISO formatted datetimes used by telemetry helpers."""

  if not value:
    return None
  try:
    return datetime.fromisoformat(value)
  except ValueError:
    return None


def _as_utc(value: datetime) -> datetime:
  """Return the datetime converted to UTC."""

  if value.tzinfo is None:
    return value.replace(tzinfo=UTC)
  return value.astimezone(UTC)


def _as_local(value: datetime) -> datetime:
  """Return the datetime converted to local time (UTC fallback)."""

  if value.tzinfo is None:
    return value.replace(tzinfo=UTC)
  return value


def _start_of_local_day(value: datetime) -> datetime:
  """Return the start of the local day for the provided datetime."""

  if isinstance(value, date) and not isinstance(value, datetime):
    return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
  local = _as_local(value)
  return local.replace(hour=0, minute=0, second=0, microsecond=0)


class Platform(StrEnum):
  """StrEnum stub that mirrors ``homeassistant.const.Platform``."""

  SENSOR = "sensor"
  BINARY_SENSOR = "binary_sensor"
  BUTTON = "button"
  SWITCH = "switch"
  NUMBER = "number"
  SELECT = "select"
  TEXT = "text"
  DEVICE_TRACKER = "device_tracker"
  DATE = "date"
  DATETIME = "datetime"


class EntityCategory(StrEnum):
  """Subset of Home Assistant's entity categories."""

  CONFIG = "config"
  DIAGNOSTIC = "diagnostic"


class ConfigEntryState(Enum):
  """Enum mirroring Home Assistant's config entry states."""

  LOADED = ("loaded", True)
  SETUP_ERROR = ("setup_error", True)
  MIGRATION_ERROR = ("migration_error", False)
  SETUP_RETRY = ("setup_retry", True)
  NOT_LOADED = ("not_loaded", True)
  FAILED_UNLOAD = ("failed_unload", False)
  SETUP_IN_PROGRESS = ("setup_in_progress", False)
  UNLOAD_IN_PROGRESS = ("unload_in_progress", False)

  def __new__(cls, value: str, recoverable: bool) -> ConfigEntryState:
    """Store the string value and recoverability flag."""

    obj = object.__new__(cls)
    obj._value_ = value
    obj._recoverable = recoverable
    return obj

  @property
  def recoverable(self) -> bool:
    """Return whether the state can be auto-recovered."""

    return self._recoverable

  @classmethod
  def from_value(cls, value: str | ConfigEntryState) -> ConfigEntryState:
    """Return the enum member matching ``value`` regardless of casing."""

    if isinstance(value, cls):
      return value

    for member in cls:
      if member.value == value:
        return member
      if isinstance(value, str) and member.name == value.upper():
        return member
    raise ValueError(value)


class IssueSeverity(StrEnum):
  """Home Assistant issue severity mirror."""

  WARNING = "warning"
  ERROR = "error"
  CRITICAL = "critical"

  @classmethod
  def from_value(cls, value: str | IssueSeverity | None) -> IssueSeverity:
    """Return the severity matching ``value`` with graceful fallback."""

    if isinstance(value, cls):
      return value
    if isinstance(value, str):
      try:
        return cls(value.lower())
      except ValueError:
        return cls.WARNING
    return cls.WARNING


class UnitOfEnergy(StrEnum):
  """Subset of Home Assistant energy units."""

  KILO_CALORIE = "kcal"


class UnitOfLength(StrEnum):
  """Subset of Home Assistant length units."""

  METERS = "m"
  KILOMETERS = "km"


class UnitOfTime(StrEnum):
  """Subset of Home Assistant time units."""

  SECONDS = "s"
  MINUTES = "min"
  HOURS = "h"
  DAYS = "d"
  MONTHS = "mo"
  YEARS = "y"


class UnitOfTemperature(StrEnum):
  """Subset of Home Assistant temperature units."""

  CELSIUS = "°C"
  FAHRENHEIT = "°F"
  KELVIN = "K"


class _ConfigEntryError(Exception):
  """Base class for stub config entry exceptions."""


class ConfigEntryAuthFailed(_ConfigEntryError):
  """Replacement for :class:`homeassistant.exceptions.ConfigEntryAuthFailed`."""


class ConfigEntryNotReady(_ConfigEntryError):
  """Replacement for :class:`homeassistant.exceptions.ConfigEntryNotReady`."""


class HomeAssistantError(Exception):
  """Replacement for :class:`homeassistant.exceptions.HomeAssistantError`."""


class HomeAssistant:
  """Minimal stand-in for :class:`homeassistant.core.HomeAssistant`."""

  def __init__(self) -> None:
    self.data: dict[str, object] = {}
    self.config = types.SimpleNamespace(language=None)
    self.config_entries = types.SimpleNamespace(async_update_entry=AsyncMock())
    self.services = types.SimpleNamespace(async_call=AsyncMock())
    self.states = StateMachine()

  def async_create_task(
    self,
    awaitable: object,
    *,
    name: str | None = None,
  ) -> asyncio.Task:
    loop = asyncio.get_running_loop()
    return loop.create_task(awaitable, name=name)

  async def async_add_executor_job(
    self,
    func: Callable[..., Any],
    *args: Any,
  ) -> Any:
    """Run a synchronous function in the default executor."""

    return await asyncio.to_thread(func, *args)


class Event:
  """Simplified version of ``homeassistant.core.Event`` used by tests."""

  def __init__(self, event_type: str, data: dict[str, object] | None = None) -> None:
    self.event_type = event_type
    self.data = data or {}


class State:
  """Simplified version of ``homeassistant.core.State``."""

  def __init__(
    self,
    entity_id: str,
    state: str,
    attributes: dict[str, object] | None = None,
  ) -> None:
    self.entity_id = entity_id
    self.state = state
    self.attributes = attributes or {}


class StateMachine:
  """Minimal state storage for tests."""

  def __init__(self) -> None:
    self._states: dict[str, State] = {}

  def get(self, entity_id: str) -> State | None:
    return self._states.get(entity_id)

  def async_set(
    self,
    entity_id: str,
    state: str,
    attributes: dict[str, object] | None = None,
  ) -> None:
    self._states[entity_id] = State(entity_id, state, attributes)

  def async_entity_ids(self, domain: str | None = None) -> list[str]:
    """Return entity ids, optionally filtered by domain."""

    if domain is None:
      return list(self._states)
    prefix = f"{domain}."
    return [entity_id for entity_id in self._states if entity_id.startswith(prefix)]


class Context:
  """Lightweight ``homeassistant.core.Context`` replacement."""

  def __init__(
    self,
    user_id: str | None = None,
    context_id: str | None = None,
    parent_id: str | None = None,
  ) -> None:
    self.user_id = user_id
    self.context_id = context_id or "context"
    self.id = self.context_id
    self.parent_id = parent_id


class ServiceCall:
  """Simplified version of ``homeassistant.core.ServiceCall``."""

  def __init__(
    self,
    domain: str,
    service: str,
    data: dict[str, object] | None = None,
    context: Context | None = None,
  ) -> None:
    self.domain = domain
    self.service = service
    self.data = data or {}
    self.context = context


def _callback(func: Callable[..., None]) -> Callable[..., None]:
  return func


class ServiceRegistry:
  """Minimal stand-in for Home Assistant's ServiceRegistry."""

  async def async_register(self, *args: object, **kwargs: object) -> None:
    return None


# Minimal registry matching Home Assistant's ConfigEntry handler mapping.
HANDLERS: dict[str, object] = {}


async def support_entry_unload(hass: object, domain: str) -> bool:
  """Return ``True`` if the handler exposes an unload hook."""

  handler = HANDLERS.get(domain)
  return bool(handler and hasattr(handler, "async_unload_entry"))


async def support_remove_from_device(hass: object, domain: str) -> bool:
  """Return ``True`` if the handler exposes a remove-device hook."""

  handler = HANDLERS.get(domain)
  return bool(handler and hasattr(handler, "async_remove_config_entry_device"))


class ConfigSubentry:
  """Minimal representation of a Home Assistant configuration subentry."""

  def __init__(
    self,
    *,
    subentry_id: str,
    data: dict[str, Any] | None = None,
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
  subentries_data: Iterable[dict[str, Any]] | None,
) -> dict[str, ConfigSubentry]:
  """Construct deterministic subentries from the provided data."""

  subentries: dict[str, ConfigSubentry] = {}
  for index, subentry_data in enumerate(subentries_data or (), start=1):
    subentry_id = (
      str(subentry_data.get("subentry_id"))
      if "subentry_id" in subentry_data
      else f"subentry_{index}"
    )
    subentries[subentry_id] = ConfigSubentry(
      subentry_id=subentry_id,
      data=dict(subentry_data.get("data", {})),
      subentry_type=str(subentry_data.get("subentry_type", "subentry")),
      title=str(subentry_data.get("title", subentry_id)),
      unique_id=subentry_data.get("unique_id"),
    )

  return subentries


class ConfigEntry:
  """Minimal representation of Home Assistant config entries."""

  def __init__(
    self,
    entry_id: str | None = None,
    *,
    created_at: datetime | None = None,
    domain: str | None = None,
    data: dict[str, object] | None = None,
    options: dict[str, object] | None = None,
    discovery_keys: dict[str, tuple[object, ...]] | None = None,
    subentries_data: Iterable[dict[str, Any]] | None = None,
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
    error_reason_translation_placeholders: dict[str, object] | None = None,
    modified_at: datetime | None = None,
  ) -> None:
    self.entry_id = entry_id or "stub-entry"
    self.domain = domain or "unknown"
    self.data = dict(data or {})
    self.options = dict(options or {})
    self.title = title or self.domain
    self.source = source
    self.version = version
    self.minor_version = minor_version
    self.unique_id = unique_id
    self.pref_disable_new_entities = pref_disable_new_entities
    self.pref_disable_polling = pref_disable_polling
    self.pref_disable_discovery = pref_disable_discovery
    self.disabled_by = disabled_by
    self.state = ConfigEntryState.from_value(state)
    self.discovery_keys = dict(discovery_keys or {})
    self.subentries = _build_subentries(subentries_data)
    self._supports_unload = supports_unload
    self._supports_remove_device = supports_remove_device
    self._supports_options = supports_options
    self._supports_reconfigure = supports_reconfigure
    self._supported_subentry_types = (
      dict(supported_subentry_types) if supported_subentry_types else None
    )
    self.runtime_data: object | None = None
    self.reason = reason
    self.error_reason_translation_key = error_reason_translation_key
    self.error_reason_translation_placeholders = dict(
      error_reason_translation_placeholders or {},
    )
    self.update_listeners: list[Callable[..., object]] = []
    self.created_at: datetime = created_at or _utcnow()
    self.modified_at: datetime = modified_at or self.created_at

  @property
  def supports_options(self) -> bool:
    """Return whether the entry exposes an options flow."""

    if self._supports_options is None:
      handler = HANDLERS.get(self.domain)
      if handler and hasattr(handler, "async_supports_options_flow"):
        self._supports_options = bool(
          handler.async_supports_options_flow(self),
        )

    return bool(self._supports_options)

  @property
  def supports_unload(self) -> bool:
    """Return whether the entry exposes an unload hook."""

    if self._supports_unload is None:
      handler = HANDLERS.get(self.domain)
      if handler and hasattr(handler, "async_unload_entry"):
        self._supports_unload = True

    return bool(self._supports_unload)

  @property
  def supports_remove_device(self) -> bool:
    """Return whether the entry exposes a remove-device hook."""

    if self._supports_remove_device is None:
      handler = HANDLERS.get(self.domain)
      if handler and hasattr(handler, "async_remove_config_entry_device"):
        self._supports_remove_device = True

    return bool(self._supports_remove_device)

  @property
  def supports_reconfigure(self) -> bool:
    """Return whether the entry exposes a reconfigure flow."""

    if self._supports_reconfigure is None:
      handler = HANDLERS.get(self.domain)
      if handler and hasattr(handler, "async_supports_reconfigure_flow"):
        self._supports_reconfigure = bool(
          handler.async_supports_reconfigure_flow(self),
        )

    return bool(self._supports_reconfigure)

  @property
  def supported_subentry_types(self) -> dict[str, dict[str, bool]]:
    """Return the supported subentry types mapping."""

    if self._supported_subentry_types is None:
      handler = HANDLERS.get(self.domain)
      if handler and hasattr(handler, "async_get_supported_subentry_types"):
        supported_flows = handler.async_get_supported_subentry_types(
          self,
        )
        self._supported_subentry_types = {
          subentry_type: {
            "supports_reconfigure": hasattr(
              subentry_handler,
              "async_step_reconfigure",
            ),
          }
          for subentry_type, subentry_handler in supported_flows.items()
        }

    return self._supported_subentry_types or {}


class _FlowBase:
  """Common helpers shared by flow handler stubs."""

  def async_show_form(
    self,
    *,
    step_id: str,
    data_schema: dict[str, object] | None = None,
    description_placeholders: dict[str, object] | None = None,
    errors: dict[str, object] | None = None,
  ) -> FlowResult:
    return {
      "type": "form",
      "step_id": step_id,
      "data_schema": data_schema,
      "description_placeholders": dict(description_placeholders or {}),
      "errors": dict(errors or {}),
    }

  def async_external_step(self, *, step_id: str, url: str) -> FlowResult:
    return {"type": "external", "step_id": step_id, "url": url}

  def async_create_entry(
    self,
    *,
    title: str | None = None,
    data: dict[str, object] | None = None,
  ) -> FlowResult:
    return {
      "type": "create_entry",
      **({"title": title} if title is not None else {}),
      "data": dict(data or {}),
    }

  def async_abort(self, *, reason: str) -> FlowResult:
    return {"type": "abort", "reason": reason}

  def async_show_menu(
    self,
    *,
    step_id: str,
    menu_options: Iterable[str],
    description_placeholders: dict[str, object] | None = None,
  ) -> FlowResult:
    return {
      "type": "menu",
      "step_id": step_id,
      "menu_options": list(menu_options),
      "description_placeholders": dict(description_placeholders or {}),
    }

  def async_show_progress(
    self,
    *,
    step_id: str,
    progress_action: str,
    description_placeholders: dict[str, object] | None = None,
  ) -> FlowResult:
    return {
      "type": "progress",
      "step_id": step_id,
      "progress_action": progress_action,
      "description_placeholders": dict(description_placeholders or {}),
    }

  def async_show_progress_done(
    self,
    *,
    next_step_id: str,
    description_placeholders: dict[str, object] | None = None,
  ) -> FlowResult:
    return {
      "type": "progress_done",
      "next_step_id": next_step_id,
      "description_placeholders": dict(description_placeholders or {}),
    }

  def async_external_step_done(self, *, next_step_id: str) -> FlowResult:
    return {"type": "external_done", "next_step_id": next_step_id}


class OptionsFlow(_FlowBase):
  """Options flow stub used by coordinator tests."""

  async def async_step_init(self, user_input: dict[str, object] | None = None):
    return self.async_create_entry(data=user_input or {})


class ConfigFlowResult(dict):
  """Dictionary wrapper to mimic Home Assistant flow results."""


class DeviceInfo(dict):
  """Match Home Assistant's mapping-style device info container."""


FlowResult = dict[str, object]
MutableFlowResultDict = dict[str, object]


class FlowResultType(StrEnum):
  """Subset of flow result types used by tests."""

  FORM = "form"
  CREATE_ENTRY = "create_entry"
  ABORT = "abort"
  MENU = "menu"
  EXTERNAL = "external"
  EXTERNAL_DONE = "external_done"
  SHOW_PROGRESS = "progress"
  SHOW_PROGRESS_DONE = "progress_done"


class DeviceEntry:
  """Simple device registry entry stub."""

  def __init__(self, **kwargs: object) -> None:
    self.id = kwargs.get("id", "device")
    self.name = kwargs.get("name")
    self.manufacturer = kwargs.get("manufacturer")
    self.model = kwargs.get("model")
    self.model_id = kwargs.get("model_id")
    self.sw_version = kwargs.get("sw_version")
    self.via_device_id = kwargs.get("via_device_id")
    self.configuration_url = kwargs.get("configuration_url")
    self.area_id = kwargs.get("area_id")
    self.suggested_area = kwargs.get("suggested_area")
    self.disabled_by = kwargs.get("disabled_by")
    self.primary_config_entry = kwargs.get("primary_config_entry")
    self.hw_version = kwargs.get("hw_version")
    self.serial_number = kwargs.get("serial_number")
    self.name_by_user = kwargs.get("name_by_user")
    self.entry_type = kwargs.get("entry_type")
    self.identifiers = set(kwargs.get("identifiers", set()))
    self.connections = set(kwargs.get("connections", set()))
    self.created_at: datetime = kwargs.get("created_at") or _utcnow()
    self.modified_at: datetime = (
      kwargs.get(
        "modified_at",
      )
      or self.created_at
    )
    self.config_entries: set[str] = set()
    config_entry_id = kwargs.get("config_entry_id")
    if isinstance(config_entry_id, str):
      self.config_entries.add(config_entry_id)
    self.config_entries.update(
      entry for entry in kwargs.get("config_entries", set()) if isinstance(entry, str)
    )
    for key, value in kwargs.items():
      if not hasattr(self, key):
        setattr(self, key, value)


class DeviceRegistryEvent:
  """Event payload used by device registry listeners."""

  def __init__(self, action: str, device_id: str) -> None:
    self.action = action
    self.device_id = device_id


class DeviceRegistry:
  """In-memory registry used by device tests."""

  def __init__(self) -> None:
    self.devices: dict[str, DeviceEntry] = {}
    self._id_sequence = 0

  def async_get_or_create(self, **kwargs: object) -> DeviceEntry:
    creation_kwargs = dict(kwargs)
    identifiers = set(creation_kwargs.get("identifiers", set()))
    connections = set(creation_kwargs.get("connections", set()))

    entry_id = creation_kwargs.pop("id", None)
    stored = (
      self.devices.get(entry_id)
      if isinstance(
        entry_id,
        str,
      )
      else None
    )

    if stored is None and (identifiers or connections):
      stored = self.async_get_device(
        identifiers=identifiers or None,
        connections=connections or None,
      )

    if stored is None:
      stored = DeviceEntry(
        id=entry_id
        if isinstance(
          entry_id,
          str,
        )
        else self._next_device_id(),
        **creation_kwargs,
      )
      self.devices.setdefault(stored.id, stored)

    self._track_device_id(stored.id)
    self._update_device(stored, **creation_kwargs)
    return stored

  def async_update_device(self, device_id: str, **kwargs: object) -> DeviceEntry:
    entry = self.devices.setdefault(device_id, DeviceEntry(id=device_id))
    self._update_device(entry, **kwargs)
    return entry

  def async_remove_device(self, device_id: str) -> bool:
    """Remove a device by ID, mirroring Home Assistant's registry helper."""

    return self.devices.pop(device_id, None) is not None

  def async_get(self, device_id: str) -> DeviceEntry | None:
    return self.devices.get(device_id)

  def async_get_device(
    self,
    *,
    identifiers: set[tuple[str, str]] | None = None,
    connections: set[tuple[str, str]] | None = None,
    device_id: str | None = None,
  ) -> DeviceEntry | None:
    if isinstance(device_id, str) and device_id in self.devices:
      return self.devices[device_id]

    identifier_matches = identifiers or set()
    connection_matches = connections or set()
    if not identifier_matches and not connection_matches:
      return None

    for device in self.devices.values():
      if (device.identifiers & identifier_matches) or (
        device.connections & connection_matches
      ):
        return device

    return None

  def async_entries_for_config_entry(self, entry_id: str) -> list[DeviceEntry]:
    return [
      device for device in self.devices.values() if entry_id in device.config_entries
    ]

  def async_listen(self, callback):  # type: ignore[no-untyped-def]
    return None

  def _update_device(self, entry: DeviceEntry, **kwargs: object) -> None:
    if isinstance(kwargs.get("config_entry_id"), str):
      entry.config_entries.add(kwargs["config_entry_id"])
    if "config_entries" in kwargs:
      entry.config_entries.update(
        entry_id for entry_id in kwargs["config_entries"] if isinstance(entry_id, str)
      )
    if "name" in kwargs:
      entry.name = kwargs["name"]
    if "manufacturer" in kwargs:
      entry.manufacturer = kwargs["manufacturer"]
    if "model" in kwargs:
      entry.model = kwargs["model"]
    if "model_id" in kwargs:
      entry.model_id = kwargs["model_id"]
    if "sw_version" in kwargs:
      entry.sw_version = kwargs["sw_version"]
    if "via_device_id" in kwargs:
      entry.via_device_id = kwargs["via_device_id"]
    if "configuration_url" in kwargs:
      entry.configuration_url = kwargs["configuration_url"]
    if "area_id" in kwargs:
      entry.area_id = kwargs["area_id"]
    if "suggested_area" in kwargs:
      entry.suggested_area = kwargs["suggested_area"]
    if "disabled_by" in kwargs:
      entry.disabled_by = kwargs["disabled_by"]
    if "primary_config_entry" in kwargs:
      entry.primary_config_entry = kwargs["primary_config_entry"]
    if "hw_version" in kwargs:
      entry.hw_version = kwargs["hw_version"]
    if "serial_number" in kwargs:
      entry.serial_number = kwargs["serial_number"]
    if "identifiers" in kwargs:
      entry.identifiers.update(set(kwargs["identifiers"]))
    if "connections" in kwargs:
      entry.connections.update(set(kwargs["connections"]))
    if "name_by_user" in kwargs:
      entry.name_by_user = kwargs["name_by_user"]
    if "entry_type" in kwargs:
      entry.entry_type = kwargs["entry_type"]
    if "preferred_area_id" in kwargs:
      entry.preferred_area_id = kwargs["preferred_area_id"]
    if "created_at" in kwargs:
      entry.created_at = kwargs["created_at"]
    if "modified_at" in kwargs:
      entry.modified_at = kwargs["modified_at"]
    elif kwargs:
      entry.modified_at = _utcnow()
    for key, value in kwargs.items():
      if not hasattr(entry, key):
        setattr(entry, key, value)

  def _track_device_id(self, device_id: str) -> None:
    match = re.fullmatch(r"device-(\d+)", device_id)
    if match:
      self._id_sequence = max(self._id_sequence, int(match.group(1)))

  def _next_device_id(self) -> str:
    self._id_sequence += 1
    return f"device-{self._id_sequence}"


def _async_get_device_registry(*args: object, **kwargs: object) -> DeviceRegistry:
  global _DEVICE_REGISTRY

  if _DEVICE_REGISTRY is None:
    _DEVICE_REGISTRY = DeviceRegistry()

  return _DEVICE_REGISTRY


def _async_get_device_by_hints(
  registry: DeviceRegistry,
  *,
  identifiers: Iterable[tuple[str, str]] | None = None,
  connections: Iterable[tuple[str, str]] | None = None,
  device_id: str | None = None,
) -> DeviceEntry | None:
  return registry.async_get_device(
    identifiers=set(identifiers or set()),
    connections=set(connections or set()),
    device_id=device_id,
  )


def _async_entries_for_device_config(
  registry: DeviceRegistry,
  entry_id: str,
) -> list[DeviceEntry]:
  return registry.async_entries_for_config_entry(entry_id)


def _async_remove_device_entry(registry: DeviceRegistry, device_id: str) -> bool:
  return registry.async_remove_device(device_id)


def _async_get_issue_registry(*args: object, **kwargs: object) -> IssueRegistry:
  global _ISSUE_REGISTRY

  if _ISSUE_REGISTRY is None:
    _ISSUE_REGISTRY = IssueRegistry()

  return _ISSUE_REGISTRY


def _async_create_issue(
  hass: object,
  domain: str,
  issue_id: str,
  *,
  active: bool | None = None,
  is_persistent: bool | None = None,
  issue_domain: str | None = None,
  translation_domain: str | None = None,
  translation_key: str | None = None,
  translation_placeholders: dict[str, object] | None = None,
  severity: str | None = None,
  is_fixable: bool | None = None,
  breaks_in_ha_version: str | None = None,
  learn_more_url: str | None = None,
  data: dict[str, object] | None = None,
  dismissed_version: str | None = None,
) -> dict[str, object]:
  registry = _async_get_issue_registry(hass)
  return registry.async_create_issue(
    domain,
    issue_id,
    active=active,
    is_persistent=is_persistent,
    issue_domain=issue_domain,
    translation_domain=translation_domain,
    translation_key=translation_key,
    translation_placeholders=translation_placeholders,
    severity=severity,
    is_fixable=is_fixable,
    breaks_in_ha_version=breaks_in_ha_version,
    learn_more_url=learn_more_url,
    data=data,
    dismissed_version=dismissed_version,
  )


def _async_delete_issue(hass: object, domain: str, issue_id: str) -> bool:
  registry = _async_get_issue_registry(hass)
  return registry.async_delete_issue(domain, issue_id)


def _async_get_issue(
  hass: object,
  domain: str,
  issue_id: str,
) -> dict[str, object] | None:
  registry = _async_get_issue_registry(hass)
  return registry.async_get_issue(domain, issue_id)


def _async_ignore_issue(
  hass: object,
  domain: str,
  issue_id: str,
  ignore: bool,
) -> dict[str, object]:
  registry = _async_get_issue_registry(hass)
  return registry.async_ignore_issue(domain, issue_id, ignore)


class IssueRegistry:
  """Minimal Home Assistant issue registry stub."""

  def __init__(self) -> None:
    self.issues: dict[tuple[str, str], dict[str, object]] = {}

  def async_create_issue(
    self,
    domain: str,
    issue_id: str,
    *,
    active: bool | None = None,
    is_persistent: bool | None = None,
    issue_domain: str | None = None,
    translation_domain: str | None = None,
    translation_key: str | None = None,
    translation_placeholders: dict[str, object] | None = None,
    severity: str | None = None,
    is_fixable: bool | None = None,
    breaks_in_ha_version: str | None = None,
    learn_more_url: str | None = None,
    data: dict[str, object] | None = None,
    dismissed_version: str | None = None,
  ) -> dict[str, object]:
    key = (domain, issue_id)
    existing = self.issues.get(key, {})
    severity_value = IssueSeverity.from_value(
      severity if severity is not None else existing.get("severity"),
    )
    is_fixable_value = (
      is_fixable
      if is_fixable is not None
      else existing.get(
        "is_fixable",
        False,
      )
    )
    translation_key_value = (
      translation_key
      if translation_key is not None
      else existing.get("translation_key") or issue_id
    )
    data_value: dict[str, object] | None
    if data is not None:
      data_value = dict(data)
    else:
      data_value = (
        dict(existing_data)
        if (existing_data := existing.get("data")) is not None
        else None
      )
    translation_placeholders_value: dict[str, object] | None
    if translation_placeholders is not None:
      translation_placeholders_value = dict(translation_placeholders)
    else:
      translation_placeholders_value = (
        dict(existing_placeholders)
        if (existing_placeholders := existing.get("translation_placeholders"))
        is not None
        else None
      )
    dismissed_version_value = (
      dismissed_version
      if dismissed_version is not None
      else existing.get("dismissed_version")
    )
    dismissed_at = existing.get("dismissed")
    if dismissed_version is not None:
      dismissed_at = dismissed_at or _utcnow()
    if dismissed_version is None and dismissed_version_value is None:
      dismissed_at = None
    details = {
      **existing,
      "active": active if active is not None else existing.get("active", True),
      "created": existing.get("created", _utcnow()),
      "domain": domain,
      "issue_domain": issue_domain
      if issue_domain is not None
      else existing.get("issue_domain") or domain,
      "issue_id": issue_id,
      "translation_domain": translation_domain
      if translation_domain is not None
      else existing.get("translation_domain", domain),
      "translation_key": translation_key_value,
      "translation_placeholders": translation_placeholders_value,
      "severity": severity_value,
      "is_fixable": is_fixable_value,
      "breaks_in_ha_version": (
        breaks_in_ha_version
        if breaks_in_ha_version is not None
        else existing.get("breaks_in_ha_version")
      ),
      "learn_more_url": (
        learn_more_url if learn_more_url is not None else existing.get("learn_more_url")
      ),
      "is_persistent": (
        is_persistent
        if is_persistent is not None
        else existing.get("is_persistent", False)
      ),
      "data": data_value,
      "dismissed": dismissed_at,
      "dismissed_version": dismissed_version_value,
      "ignored": existing.get("ignored", False),
    }
    self.issues[key] = details
    return details

  def async_ignore_issue(
    self,
    domain: str,
    issue_id: str,
    ignore: bool,
  ) -> dict[str, object]:
    key = (domain, issue_id)
    if key not in self.issues:
      msg = f"Issue {domain}/{issue_id} not found"
      raise KeyError(msg)

    details = dict(self.issues[key])
    dismissed_version_value = HOME_ASSISTANT_VERSION if ignore else None

    if (
      details.get("dismissed_version") == dismissed_version_value
      and details.get("ignored") is ignore
    ):
      return details

    details["dismissed_version"] = dismissed_version_value
    details["dismissed"] = _utcnow() if ignore else None
    details["ignored"] = ignore
    details["active"] = not ignore
    self.issues[key] = details
    return details

  def async_delete_issue(self, domain: str, issue_id: str) -> bool:
    return self.issues.pop((domain, issue_id), None) is not None

  def async_get_issue(self, domain: str, issue_id: str) -> dict[str, object] | None:
    return self.issues.get((domain, issue_id))


class RegistryEntry:
  """Entity registry entry stub."""

  def __init__(self, entity_id: str, **kwargs: object) -> None:
    self.entity_id = entity_id
    self.device_id = kwargs.get("device_id")
    self.config_entries: set[str] = set()
    if isinstance(kwargs.get("config_entry_id"), str):
      self.config_entries.add(kwargs["config_entry_id"])
    self.config_entries.update(
      entry for entry in kwargs.get("config_entries", set()) if isinstance(entry, str)
    )
    self.unique_id = kwargs.get("unique_id")
    self.platform = kwargs.get("platform")
    self.original_name = kwargs.get("original_name")
    self.name = kwargs.get("name")
    self.original_device_class = kwargs.get("original_device_class")
    self.device_class = kwargs.get("device_class")
    self.translation_key = kwargs.get("translation_key")
    self.has_entity_name = kwargs.get("has_entity_name")
    self.area_id = kwargs.get("area_id")
    self.disabled_by = kwargs.get("disabled_by")
    self.entity_category = kwargs.get("entity_category")
    self.icon = kwargs.get("icon")
    self.original_icon = kwargs.get("original_icon")
    self.aliases = set(kwargs.get("aliases", set()))
    self.hidden_by = kwargs.get("hidden_by")
    self.preferred_area_id = kwargs.get("preferred_area_id")
    self.options = dict(kwargs.get("options", {}))
    self.capabilities = dict(kwargs.get("capabilities", {}))
    self.supported_features = kwargs.get("supported_features")
    self.unit_of_measurement = kwargs.get("unit_of_measurement")
    self.original_unit_of_measurement = kwargs.get(
      "original_unit_of_measurement",
    )
    self.created_at: datetime = kwargs.get("created_at") or _utcnow()
    self.modified_at: datetime = (
      kwargs.get(
        "modified_at",
      )
      or self.created_at
    )
    for key, value in kwargs.items():
      if not hasattr(self, key):
        setattr(self, key, value)


class EntityRegistry:
  """Simple entity registry storing entries in a dict."""

  def __init__(self) -> None:
    self.entities: dict[str, RegistryEntry] = {}

  def async_get(self, entity_id: str) -> RegistryEntry | None:
    return self.entities.get(entity_id)

  def async_get_or_create(self, entity_id: str, **kwargs: object) -> RegistryEntry:
    unique_id = kwargs.get("unique_id")
    platform = kwargs.get("platform")

    entry = self.entities.get(entity_id)
    if entry is None and unique_id is not None:
      entry = next(
        (
          candidate
          for candidate in self.entities.values()
          if candidate.unique_id == unique_id
          and (platform is None or candidate.platform == platform)
        ),
        None,
      )

    if entry is None:
      entry = RegistryEntry(entity_id, **kwargs)
      self.entities[entity_id] = entry

    self._update_entry(entry, **kwargs)
    return entry

  def async_update_entity(self, entity_id: str, **kwargs: object) -> RegistryEntry:
    entry = self.entities.setdefault(entity_id, RegistryEntry(entity_id))
    self._update_entry(entry, **kwargs)
    return entry

  def async_entries_for_config_entry(self, entry_id: str) -> list[RegistryEntry]:
    return [
      entity for entity in self.entities.values() if entry_id in entity.config_entries
    ]

  def async_entries_for_device(self, device_id: str) -> list[RegistryEntry]:
    return [
      entity for entity in self.entities.values() if entity.device_id == device_id
    ]

  def async_remove(self, entity_id: str) -> bool:
    """Remove an entity by ID, mirroring Home Assistant's registry helper."""

    return self.entities.pop(entity_id, None) is not None

  def async_listen(self, callback):  # type: ignore[no-untyped-def]
    return None

  def _update_entry(self, entry: RegistryEntry, **kwargs: object) -> None:
    if isinstance(kwargs.get("config_entry_id"), str):
      entry.config_entries.add(kwargs["config_entry_id"])
    if "config_entries" in kwargs:
      entry.config_entries.update(
        entry_id for entry_id in kwargs["config_entries"] if isinstance(entry_id, str)
      )
    if "device_id" in kwargs:
      entry.device_id = kwargs["device_id"]
    if "unique_id" in kwargs:
      entry.unique_id = kwargs["unique_id"]
    if "platform" in kwargs:
      entry.platform = kwargs["platform"]
    if "original_name" in kwargs:
      entry.original_name = kwargs["original_name"]
    if "name" in kwargs:
      entry.name = kwargs["name"]
    if "original_device_class" in kwargs:
      entry.original_device_class = kwargs["original_device_class"]
    if "device_class" in kwargs:
      entry.device_class = kwargs["device_class"]
    if "translation_key" in kwargs:
      entry.translation_key = kwargs["translation_key"]
    if "has_entity_name" in kwargs:
      entry.has_entity_name = kwargs["has_entity_name"]
    if "area_id" in kwargs:
      entry.area_id = kwargs["area_id"]
    if "disabled_by" in kwargs:
      entry.disabled_by = kwargs["disabled_by"]
    if "entity_category" in kwargs:
      entry.entity_category = kwargs["entity_category"]
    if "icon" in kwargs:
      entry.icon = kwargs["icon"]
    if "original_icon" in kwargs:
      entry.original_icon = kwargs["original_icon"]
    if "aliases" in kwargs:
      entry.aliases = set(kwargs["aliases"])
    if "hidden_by" in kwargs:
      entry.hidden_by = kwargs["hidden_by"]
    if "preferred_area_id" in kwargs:
      entry.preferred_area_id = kwargs["preferred_area_id"]
    if "options" in kwargs:
      entry.options = dict(kwargs["options"])
    if "capabilities" in kwargs:
      entry.capabilities = dict(kwargs["capabilities"])
    if "supported_features" in kwargs:
      entry.supported_features = kwargs["supported_features"]
    if "unit_of_measurement" in kwargs:
      entry.unit_of_measurement = kwargs["unit_of_measurement"]
    if "original_unit_of_measurement" in kwargs:
      entry.original_unit_of_measurement = kwargs["original_unit_of_measurement"]
    if "created_at" in kwargs:
      entry.created_at = kwargs["created_at"]
    if "modified_at" in kwargs:
      entry.modified_at = kwargs["modified_at"]
    elif kwargs:
      entry.modified_at = _utcnow()
    for key, value in kwargs.items():
      if not hasattr(entry, key):
        setattr(entry, key, value)


class EntityRegistryEvent:
  """Event payload used by entity registry listeners."""

  def __init__(self, action: str, entity_id: str) -> None:
    self.action = action
    self.entity_id = entity_id


def _async_get_entity_registry(*args: object, **kwargs: object) -> EntityRegistry:
  global _ENTITY_REGISTRY

  if _ENTITY_REGISTRY is None:
    _ENTITY_REGISTRY = EntityRegistry()

  return _ENTITY_REGISTRY


def _async_entries_for_registry_config(
  registry: EntityRegistry,
  entry_id: str,
) -> list[RegistryEntry]:
  return registry.async_entries_for_config_entry(entry_id)


def _async_entries_for_registry_device(
  registry: EntityRegistry,
  device_id: str,
) -> list[RegistryEntry]:
  return registry.async_entries_for_device(device_id)


def _async_remove_registry_entry(registry: EntityRegistry, entity_id: str) -> bool:
  return registry.async_remove(entity_id)


class Store:
  """Persistence helper used by coordinator storage tests."""

  def __init__(self, *args: object, **kwargs: object) -> None:
    _ = args, kwargs
    self.data: object | None = None

  async def async_load(self) -> object | None:
    return self.data

  async def async_save(self, data: object) -> None:
    self.data = data


def async_dispatcher_connect(
  hass: HomeAssistant, signal: str, target: Callable
) -> Callable:
  """Minimal dispatcher connect helper used by service wiring."""

  dispatcher = hass.data.setdefault("_dispatcher", {})
  listeners = dispatcher.setdefault(signal, [])
  listeners.append(target)

  def _unsubscribe() -> None:
    if target in listeners:
      listeners.remove(target)

  return _unsubscribe


class Entity:
  """Base entity stub."""

  pass


class RestoreEntity(Entity):
  """Mixin stub for state restoration helpers."""

  async def async_get_last_state(self) -> State | None:
    return None


EntityT = TypeVar("EntityT", bound=Entity)


class EntityComponent[EntityT: Entity]:
  """Minimal entity component container."""

  def __init__(self) -> None:
    self._entities: dict[str, EntityT] = {}

  def get_entity(self, entity_id: str) -> EntityT | None:
    return self._entities.get(entity_id)

  async def async_add_entities(self, entities: Iterable[EntityT]) -> None:
    for entity in entities:
      entity_id = getattr(entity, "entity_id", None)
      if entity_id is None:
        entity_id = getattr(entity, "_attr_unique_id", None)
      if entity_id is None:
        entity_id = f"entity.{len(self._entities)}"
      self._entities[str(entity_id)] = entity

  async def async_remove_entity(self, entity_id: str) -> None:
    self._entities.pop(entity_id, None)


class SensorEntity(Entity):
  """Sensor entity stub."""


class BinarySensorEntity(Entity):
  """Binary sensor entity stub."""


class ButtonEntity(Entity):
  """Button entity stub."""


class SwitchEntity(Entity):
  """Switch entity stub."""


class NumberEntity(Entity):
  """Number entity stub."""


class SelectEntity(Entity):
  """Select entity stub."""


class TextEntity(Entity):
  """Text entity stub."""


class DateEntity(Entity):
  """Date entity stub."""


class DateTimeEntity(Entity):
  """Datetime entity stub."""


class TrackerEntity(Entity):
  """Device tracker entity stub."""


class ScriptEntity(Entity):
  """Script entity stub."""


class SensorDeviceClass(StrEnum):
  TEMPERATURE = "temperature"
  HUMIDITY = "humidity"
  TIMESTAMP = "timestamp"
  DURATION = "duration"
  BATTERY = "battery"
  WEIGHT = "weight"


class SensorStateClass(StrEnum):
  MEASUREMENT = "measurement"
  TOTAL = "total"
  TOTAL_INCREASING = "total_increasing"


class BinarySensorDeviceClass(StrEnum):
  MOTION = "motion"
  PROBLEM = "problem"
  CONNECTIVITY = "connectivity"
  RUNNING = "running"
  PRESENCE = "presence"
  SAFETY = "safety"
  BATTERY = "battery"


class ButtonDeviceClass(StrEnum):
  RESTART = "restart"
  UPDATE = "update"
  IDENTIFY = "identify"


class SwitchDeviceClass(StrEnum):
  SWITCH = "switch"


class NumberDeviceClass(StrEnum):
  DISTANCE = "distance"
  DURATION = "duration"
  TEMPERATURE = "temperature"
  WEIGHT = "weight"


class NumberMode(StrEnum):
  AUTO = "auto"
  BOX = "box"
  SLIDER = "slider"


class TextMode(StrEnum):
  TEXT = "text"
  PASSWORD = "password"


class SourceType(StrEnum):
  GPS = "gps"


class WeatherEntity(Entity):
  """Weather entity stub."""


def _config_entry_only_config_schema(domain: str):
  def _schema(data: object) -> object:
    return data

  return _schema


def _cv_string(value: Any) -> str:
  """Coerce values to strings for config validation."""

  if isinstance(value, str):
    return value
  return str(value)


def _cv_boolean(value: Any) -> bool:
  """Coerce values to booleans for config validation."""

  if isinstance(value, bool):
    return value
  if isinstance(value, str):
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
      return True
    if lowered in {"0", "false", "no", "off"}:
      return False
  if isinstance(value, (int, float)):
    return bool(value)
  raise ValueError(value)


def _cv_date(value: Any) -> date:
  """Coerce values to dates for config validation."""

  if isinstance(value, date) and not isinstance(value, datetime):
    return value
  if isinstance(value, datetime):
    return value.date()
  if isinstance(value, str):
    return date.fromisoformat(value)
  raise ValueError(value)


def _cv_datetime(value: Any) -> datetime:
  """Coerce values to datetimes for config validation."""

  if isinstance(value, datetime):
    return value
  if isinstance(value, str):
    return datetime.fromisoformat(value)
  raise ValueError(value)


class _AsyncFile:
  def __init__(self, handle: Any) -> None:
    self._handle = handle
    self.name = getattr(handle, "name", None)
    self.mode = getattr(handle, "mode", None)
    self.encoding = getattr(handle, "encoding", None)
    self.read = AsyncMock(side_effect=handle.read)
    self.write = AsyncMock(side_effect=handle.write)
    self.readline = AsyncMock(side_effect=handle.readline)
    self.readlines = AsyncMock(side_effect=handle.readlines)
    self.writelines = AsyncMock(side_effect=handle.writelines)
    self.seek = AsyncMock(side_effect=handle.seek)
    self.tell = AsyncMock(side_effect=handle.tell)
    self.flush = AsyncMock(side_effect=handle.flush)
    self.close = AsyncMock(side_effect=handle.close)

  def __getattr__(self, name: str) -> Any:
    return getattr(self._handle, name)

  def __aiter__(self) -> _AsyncFile:
    return self

  async def __anext__(self) -> str:
    line = self._handle.readline()
    if not line:
      raise StopAsyncIteration
    return line

  async def __aenter__(self) -> _AsyncFile:
    return self

  async def __aexit__(
    self,
    exc_type: type[BaseException] | None,
    exc: BaseException | None,
    traceback: Any,
  ) -> None:
    self._handle.close()


def _async_file_handle(handle: Any) -> _AsyncFile:
  """Return an async-compatible file handle wrapper."""

  return _AsyncFile(handle)


async def _async_get_clientsession(hass: object) -> object:
  """Return a stub clientsession for aiohttp helper tests."""

  return object()


def _async_make_resolver(hass: object) -> Callable[[str], object]:
  """Return a zeroconf resolver stub compatible with HACC fixtures."""

  def _resolve(host: str) -> object:
    return host

  return _resolve


def _log_exception(format_err: Callable[..., str], *args: object) -> None:
  """Mimic the logging helper Home Assistant exposes."""

  format_err(*args)


def _async_track_time_interval(*args: object, **kwargs: object):
  return lambda: None


def _async_track_time_change(*args: object, **kwargs: object):
  return lambda: None


def _async_call_later(*args: object, **kwargs: object):
  return lambda: None


def _async_track_state_change_event(*args: object, **kwargs: object):
  return lambda: None


class DataUpdateCoordinator:
  """Simplified coordinator used by runtime data tests."""

  def __init__(
    self,
    hass: object,
    logger: object | None = None,
    *args: object,
    name: str | None = None,
    **kwargs: object,
  ) -> None:
    self.hass = hass
    self.logger = logger
    self.name = name or "stub"

  async def async_config_entry_first_refresh(self) -> None:
    return None

  async def async_request_refresh(self) -> None:
    return None

  @classmethod
  def __class_getitem__(cls, item):  # pragma: no cover - helper stub
    return cls


class CoordinatorUpdateFailed(Exception):
  """Error raised when DataUpdateCoordinator refreshes fail."""


class CoordinatorEntity(Entity):
  """Minimal CoordinatorEntity shim used by PawControl entities."""

  def __init__(self, coordinator: DataUpdateCoordinator) -> None:
    super().__init__()
    self.coordinator = coordinator

  def __class_getitem__(cls, item: object) -> type[CoordinatorEntity]:
    return cls

  @property
  def available(self) -> bool:
    if (
      last_update_success := getattr(
        self.coordinator,
        "last_update_success",
        None,
      )
    ) is not None:
      return bool(last_update_success)
    return bool(getattr(self.coordinator, "available", True))


class _SelectorBase:
  def __init__(self, config: object | None = None) -> None:
    self.config = config


class SelectSelectorMode(StrEnum):
  DROPDOWN = "dropdown"
  LIST = "list"


class SelectSelectorConfig:
  def __init__(self, **kwargs: object) -> None:
    self.options = kwargs


class SelectSelector(_SelectorBase):
  pass


class BooleanSelector(_SelectorBase):
  pass


class NumberSelectorMode(StrEnum):
  BOX = "box"
  SLIDER = "slider"


class NumberSelectorConfig:
  def __init__(self, **kwargs: object) -> None:
    self.options = kwargs


class NumberSelector(_SelectorBase):
  pass


class TextSelectorType(StrEnum):
  TEXT = "text"
  TEL = "tel"


class TextSelectorConfig:
  def __init__(self, **kwargs: object) -> None:
    self.options = kwargs


class TextSelector(_SelectorBase):
  pass


class TimeSelector(_SelectorBase):
  pass


class DateSelector(_SelectorBase):
  pass


def selector(config: object) -> object:
  """Return selector configuration unchanged for schema validation tests."""

  return config


def _register_custom_component_packages() -> None:
  custom_components_pkg = sys.modules.setdefault(
    "custom_components",
    types.ModuleType("custom_components"),
  )
  custom_components_pkg.__path__ = [str(COMPONENT_ROOT)]

  pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
  pawcontrol_pkg.__path__ = [str(PAWCONTROL_ROOT)]

  def _load_submodule(name: str):
    module_name = f"custom_components.pawcontrol.{name}"
    try:
      return importlib.import_module(module_name)
    except ModuleNotFoundError as err:
      if err.name != module_name:
        raise
      init_module = importlib.import_module("custom_components.pawcontrol.__init__")
      if hasattr(init_module, name):
        value = getattr(init_module, name)
        setattr(pawcontrol_pkg, name, value)
        return value
      raise

  pawcontrol_pkg.__getattr__ = _load_submodule  # type: ignore[assignment]
  sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg
  custom_components_pkg.pawcontrol = pawcontrol_pkg


def install_homeassistant_stubs() -> None:
  """Register lightweight Home Assistant modules required by the tests."""

  for module_name in [
    "aiofiles",
    "homeassistant",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_component",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.config_validation",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.event",
    "homeassistant.helpers.restore_state",
    "homeassistant.helpers.typing",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.helpers.selector",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.storage",
    "homeassistant.helpers.issue_registry",
    "homeassistant.helpers.service_info",
    "homeassistant.helpers.service_info.dhcp",
    "homeassistant.helpers.service_info.usb",
    "homeassistant.helpers.service_info.zeroconf",
    "homeassistant.util",
    "homeassistant.util.dt",
    "homeassistant.util.logging",
    "homeassistant.config_entries",
    "homeassistant.components",
    "homeassistant.components.binary_sensor",
    "homeassistant.components.button",
    "homeassistant.components.date",
    "homeassistant.components.datetime",
    "homeassistant.components.device_automation",
    "homeassistant.components.device_tracker",
    "homeassistant.components.input_boolean",
    "homeassistant.components.input_datetime",
    "homeassistant.components.input_number",
    "homeassistant.components.input_select",
    "homeassistant.components.number",
    "homeassistant.components.script",
    "homeassistant.components.script.config",
    "homeassistant.components.script.const",
    "homeassistant.components.select",
    "homeassistant.components.sensor",
    "homeassistant.components.switch",
    "homeassistant.components.system_health",
    "homeassistant.components.text",
    "homeassistant.components.weather",
    "homeassistant.components.repairs",
    "homeassistant.data_entry_flow",
  ]:
    sys.modules.pop(module_name, None)

  global _DEVICE_REGISTRY, _ENTITY_REGISTRY, _ISSUE_REGISTRY
  _DEVICE_REGISTRY = None
  _ENTITY_REGISTRY = None
  _ISSUE_REGISTRY = None

  _register_custom_component_packages()

  homeassistant = types.ModuleType("homeassistant")
  const_module = types.ModuleType("homeassistant.const")
  core_module = types.ModuleType("homeassistant.core")
  exceptions_module = types.ModuleType("homeassistant.exceptions")
  helpers_module = types.ModuleType("homeassistant.helpers")
  helpers_module.__path__ = []
  entity_module = types.ModuleType("homeassistant.helpers.entity")
  entity_component_module = types.ModuleType(
    "homeassistant.helpers.entity_component",
  )
  entity_platform_module = types.ModuleType(
    "homeassistant.helpers.entity_platform",
  )
  config_validation_module = types.ModuleType(
    "homeassistant.helpers.config_validation",
  )
  aiohttp_client_module = types.ModuleType(
    "homeassistant.helpers.aiohttp_client",
  )
  dispatcher_module = types.ModuleType("homeassistant.helpers.dispatcher")
  event_module = types.ModuleType("homeassistant.helpers.event")
  restore_state_module = types.ModuleType("homeassistant.helpers.restore_state")
  typing_module = types.ModuleType("homeassistant.helpers.typing")
  update_coordinator_module = types.ModuleType(
    "homeassistant.helpers.update_coordinator",
  )
  device_registry_module = types.ModuleType(
    "homeassistant.helpers.device_registry",
  )
  entity_registry_module = types.ModuleType(
    "homeassistant.helpers.entity_registry",
  )
  issue_registry_module = types.ModuleType(
    "homeassistant.helpers.issue_registry",
  )
  storage_module = types.ModuleType("homeassistant.helpers.storage")
  config_entries_module = types.ModuleType("homeassistant.config_entries")
  util_module = types.ModuleType("homeassistant.util")
  util_module.__path__ = []
  dt_util_module = types.ModuleType("homeassistant.util.dt")
  logging_util_module = types.ModuleType("homeassistant.util.logging")
  selector_module = types.ModuleType("homeassistant.helpers.selector")
  service_info_module = types.ModuleType("homeassistant.helpers.service_info")
  service_info_module.__path__ = []
  dhcp_module = types.ModuleType("homeassistant.helpers.service_info.dhcp")
  usb_module = types.ModuleType("homeassistant.helpers.service_info.usb")
  zeroconf_module = types.ModuleType("homeassistant.helpers.service_info.zeroconf")
  components_module = types.ModuleType("homeassistant.components")
  components_module.__path__ = []
  binary_sensor_component_module = types.ModuleType(
    "homeassistant.components.binary_sensor",
  )
  button_component_module = types.ModuleType("homeassistant.components.button")
  date_component_module = types.ModuleType("homeassistant.components.date")
  datetime_component_module = types.ModuleType("homeassistant.components.datetime")
  device_automation_component_module = types.ModuleType(
    "homeassistant.components.device_automation",
  )
  device_tracker_component_module = types.ModuleType(
    "homeassistant.components.device_tracker",
  )
  input_boolean_component_module = types.ModuleType(
    "homeassistant.components.input_boolean",
  )
  input_datetime_component_module = types.ModuleType(
    "homeassistant.components.input_datetime",
  )
  input_number_component_module = types.ModuleType(
    "homeassistant.components.input_number",
  )
  input_select_component_module = types.ModuleType(
    "homeassistant.components.input_select",
  )
  number_component_module = types.ModuleType("homeassistant.components.number")
  script_component_module = types.ModuleType("homeassistant.components.script")
  script_config_module = types.ModuleType("homeassistant.components.script.config")
  script_const_module = types.ModuleType("homeassistant.components.script.const")
  select_component_module = types.ModuleType("homeassistant.components.select")
  sensor_component_module = types.ModuleType("homeassistant.components.sensor")
  switch_component_module = types.ModuleType("homeassistant.components.switch")
  system_health_component_module = types.ModuleType(
    "homeassistant.components.system_health",
  )
  text_component_module = types.ModuleType("homeassistant.components.text")
  weather_component_module = types.ModuleType("homeassistant.components.weather")
  repairs_component_module = types.ModuleType(
    "homeassistant.components.repairs",
  )
  data_entry_flow_module = types.ModuleType("homeassistant.data_entry_flow")
  aiofiles_module = types.ModuleType("aiofiles")

  const_module.Platform = Platform
  const_module.__version__ = HOME_ASSISTANT_VERSION
  const_module.CONF_NAME = "name"
  const_module.CONF_ALIAS = "alias"
  const_module.CONF_DEFAULT = "default"
  const_module.CONF_DESCRIPTION = "description"
  const_module.CONF_SEQUENCE = "sequence"
  const_module.CONF_DEVICE_ID = "device_id"
  const_module.CONF_ENTITY_ID = "entity_id"
  const_module.CONF_DOMAIN = "domain"
  const_module.CONF_PLATFORM = "platform"
  const_module.CONF_TYPE = "type"
  const_module.CONF_FROM = "from"
  const_module.CONF_TO = "to"
  const_module.CONF_CONDITION = "condition"
  const_module.STATE_ON = "on"
  const_module.STATE_OFF = "off"
  const_module.STATE_UNKNOWN = "unknown"
  const_module.STATE_UNAVAILABLE = "unavailable"
  const_module.STATE_HOME = "home"
  const_module.STATE_NOT_HOME = "not_home"
  const_module.UnitOfEnergy = UnitOfEnergy
  const_module.UnitOfLength = UnitOfLength
  const_module.UnitOfTime = UnitOfTime
  const_module.UnitOfTemperature = UnitOfTemperature
  const_module.PERCENTAGE = "%"

  device_automation_component_module.DEVICE_TRIGGER_BASE_SCHEMA = vol.Schema(
    {
      vol.Required(const_module.CONF_PLATFORM): vol.Any("device"),
      vol.Required(const_module.CONF_DEVICE_ID): vol.Coerce(str),
      vol.Required(const_module.CONF_DOMAIN): vol.Coerce(str),
    },
  )
  device_automation_component_module.DEVICE_CONDITION_BASE_SCHEMA = vol.Schema(
    {
      vol.Required(const_module.CONF_CONDITION): vol.Any("device"),
      vol.Required(const_module.CONF_DEVICE_ID): vol.Coerce(str),
      vol.Required(const_module.CONF_DOMAIN): vol.Coerce(str),
    },
  )
  device_automation_component_module.DEVICE_ACTION_BASE_SCHEMA = vol.Schema(
    {
      vol.Required(const_module.CONF_DEVICE_ID): vol.Coerce(str),
      vol.Required(const_module.CONF_DOMAIN): vol.Coerce(str),
    },
  )

  core_module.HomeAssistant = HomeAssistant
  core_module.Event = Event
  core_module.EventStateChangedData = dict[str, object]
  core_module.State = State
  core_module.Context = Context
  core_module.ServiceCall = ServiceCall
  core_module.callback = _callback
  core_module.CALLBACK_TYPE = Callable[..., None]
  core_module.ServiceRegistry = ServiceRegistry

  exceptions_module.ConfigEntryAuthFailed = ConfigEntryAuthFailed
  exceptions_module.ConfigEntryNotReady = ConfigEntryNotReady
  exceptions_module.HomeAssistantError = HomeAssistantError

  config_entries_module.HANDLERS = HANDLERS
  config_entries_module.support_entry_unload = support_entry_unload
  config_entries_module.support_remove_from_device = support_remove_from_device
  config_entries_module.ConfigEntry = ConfigEntry
  config_entries_module.ConfigEntryState = ConfigEntryState
  config_entries_module.OptionsFlow = OptionsFlow
  config_entries_module.ConfigFlowResult = ConfigFlowResult
  config_entries_module.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"

  device_registry_module.DeviceInfo = DeviceInfo
  device_registry_module.DeviceEntry = DeviceEntry
  device_registry_module.DeviceRegistry = DeviceRegistry
  device_registry_module.DeviceRegistryEvent = DeviceRegistryEvent
  device_registry_module.async_get = _async_get_device_registry
  device_registry_module.async_get_device = _async_get_device_by_hints
  device_registry_module.async_entries_for_config_entry = (
    _async_entries_for_device_config
  )
  device_registry_module.async_remove_device = _async_remove_device_entry

  entity_registry_module.RegistryEntry = RegistryEntry
  entity_registry_module.EntityRegistry = EntityRegistry
  entity_registry_module.EntityRegistryEvent = EntityRegistryEvent
  entity_registry_module.async_get = _async_get_entity_registry
  entity_registry_module.async_entries_for_config_entry = (
    _async_entries_for_registry_config
  )
  entity_registry_module.async_entries_for_device = _async_entries_for_registry_device
  entity_registry_module.async_remove = _async_remove_registry_entry

  issue_registry_module.DOMAIN = "issue_registry"
  issue_registry_module.IssueSeverity = IssueSeverity
  issue_registry_module.async_get = _async_get_issue_registry
  issue_registry_module.async_get_issue = _async_get_issue
  issue_registry_module.async_create_issue = _async_create_issue
  issue_registry_module.async_delete_issue = _async_delete_issue
  issue_registry_module.async_ignore_issue = _async_ignore_issue

  storage_module.Store = Store

  entity_module.Entity = Entity
  entity_module.EntityCategory = EntityCategory
  entity_component_module.EntityComponent = EntityComponent
  restore_state_module.RestoreEntity = RestoreEntity
  dispatcher_module.async_dispatcher_connect = async_dispatcher_connect

  entity_platform_module.AddEntitiesCallback = Callable[
    [list[Entity], bool],
    None,
  ]

  config_validation_module.config_entry_only_config_schema = (
    _config_entry_only_config_schema
  )
  config_validation_module.string = _cv_string
  config_validation_module.boolean = _cv_boolean
  config_validation_module.date = _cv_date
  config_validation_module.datetime = _cv_datetime
  aiohttp_client_module.async_get_clientsession = _async_get_clientsession
  aiohttp_client_module._async_make_resolver = _async_make_resolver
  event_module.async_track_time_interval = _async_track_time_interval
  event_module.async_track_time_change = _async_track_time_change
  event_module.async_call_later = _async_call_later
  event_module.async_track_state_change_event = _async_track_state_change_event

  typing_module.ConfigType = dict[str, Any]

  update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator
  update_coordinator_module.CoordinatorEntity = CoordinatorEntity
  update_coordinator_module.CoordinatorUpdateFailed = CoordinatorUpdateFailed

  dt_util_module.utcnow = _utcnow
  dt_util_module.now = _now
  dt_util_module.parse_datetime = _parse_datetime
  dt_util_module.as_utc = _as_utc
  dt_util_module.as_local = _as_local
  dt_util_module.start_of_local_day = _start_of_local_day
  logging_util_module.log_exception = _log_exception

  def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")

  util_module.slugify = _slugify

  class _RepairsFlow(_FlowBase):
    """Placeholder for Home Assistant repairs flow base class."""

  repairs_component_module.RepairsFlow = _RepairsFlow
  repairs_component_module.DOMAIN = "repairs"

  class _ServiceInfo:
    def __init__(self, **kwargs: object) -> None:
      for key, value in kwargs.items():
        setattr(self, key, value)

  dhcp_module.DhcpServiceInfo = _ServiceInfo
  usb_module.UsbServiceInfo = _ServiceInfo
  zeroconf_module.ZeroconfServiceInfo = _ServiceInfo

  data_entry_flow_module.FlowResult = FlowResult
  data_entry_flow_module.FlowResultType = FlowResultType
  config_entries_module.FlowResult = FlowResult

  selector_module.SelectSelectorMode = SelectSelectorMode
  selector_module.SelectSelectorConfig = SelectSelectorConfig
  selector_module.SelectSelector = SelectSelector
  selector_module.BooleanSelector = BooleanSelector
  selector_module.NumberSelectorMode = NumberSelectorMode
  selector_module.NumberSelectorConfig = NumberSelectorConfig
  selector_module.NumberSelector = NumberSelector
  selector_module.TextSelectorType = TextSelectorType
  selector_module.TextSelectorConfig = TextSelectorConfig
  selector_module.TextSelector = TextSelector
  selector_module.TimeSelector = TimeSelector
  selector_module.DateSelector = DateSelector
  selector_module.selector = selector

  @asynccontextmanager
  async def _aiofiles_open(
    file: str | Path,
    mode: str = "r",
    encoding: str | None = None,
  ):
    with builtins.open(file, mode, encoding=encoding) as handle:
      yield _async_file_handle(handle)

  aiofiles_module.open = _aiofiles_open

  sensor_component_module.SensorEntity = SensorEntity
  sensor_component_module.SensorDeviceClass = SensorDeviceClass
  sensor_component_module.SensorStateClass = SensorStateClass
  binary_sensor_component_module.BinarySensorEntity = BinarySensorEntity
  binary_sensor_component_module.BinarySensorDeviceClass = BinarySensorDeviceClass
  button_component_module.ButtonEntity = ButtonEntity
  button_component_module.ButtonDeviceClass = ButtonDeviceClass
  switch_component_module.SwitchEntity = SwitchEntity
  switch_component_module.SwitchDeviceClass = SwitchDeviceClass
  number_component_module.NumberEntity = NumberEntity
  number_component_module.NumberDeviceClass = NumberDeviceClass
  number_component_module.NumberMode = NumberMode
  select_component_module.SelectEntity = SelectEntity
  text_component_module.TextEntity = TextEntity
  text_component_module.TextMode = TextMode
  date_component_module.DateEntity = DateEntity
  datetime_component_module.DateTimeEntity = DateTimeEntity
  device_tracker_component_module.TrackerEntity = TrackerEntity
  device_tracker_component_module.SourceType = SourceType
  weather_component_module.WeatherEntity = WeatherEntity
  weather_component_module.DOMAIN = "weather"
  weather_component_module.ATTR_FORECAST = "forecast"
  weather_component_module.ATTR_FORECAST_CONDITION = "condition"
  weather_component_module.ATTR_FORECAST_HUMIDITY = "humidity"
  weather_component_module.ATTR_FORECAST_PRECIPITATION = "precipitation"
  weather_component_module.ATTR_FORECAST_PRECIPITATION_PROBABILITY = (
    "precipitation_probability"
  )
  weather_component_module.ATTR_FORECAST_PRESSURE = "pressure"
  weather_component_module.ATTR_FORECAST_TEMP = "temperature"
  weather_component_module.ATTR_FORECAST_TEMP_LOW = "templow"
  weather_component_module.ATTR_FORECAST_TIME = "datetime"
  weather_component_module.ATTR_FORECAST_UV_INDEX = "uv_index"
  weather_component_module.ATTR_FORECAST_WIND_SPEED = "wind_speed"
  weather_component_module.ATTR_WEATHER_HUMIDITY = "humidity"
  weather_component_module.ATTR_WEATHER_PRESSURE = "pressure"
  weather_component_module.ATTR_WEATHER_TEMPERATURE = "temperature"
  weather_component_module.ATTR_WEATHER_UV_INDEX = "uv_index"
  weather_component_module.ATTR_WEATHER_VISIBILITY = "visibility"
  weather_component_module.ATTR_WEATHER_WIND_SPEED = "wind_speed"
  input_boolean_component_module.DOMAIN = "input_boolean"
  input_datetime_component_module.DOMAIN = "input_datetime"
  input_number_component_module.DOMAIN = "input_number"
  input_select_component_module.DOMAIN = "input_select"
  script_component_module.DOMAIN = "script"
  script_component_module.ScriptEntity = ScriptEntity
  script_config_module.SCRIPT_ENTITY_SCHEMA = {}
  script_const_module.CONF_FIELDS = "fields"
  script_const_module.CONF_TRACE = "trace"
  system_health_component_module.DOMAIN = "system_health"

  homeassistant.const = const_module
  homeassistant.core = core_module
  homeassistant.exceptions = exceptions_module
  homeassistant.helpers = helpers_module
  homeassistant.config_entries = config_entries_module
  homeassistant.util = util_module

  helpers_module.entity = entity_module
  helpers_module.entity_component = entity_component_module
  helpers_module.entity_platform = entity_platform_module
  helpers_module.config_validation = config_validation_module
  helpers_module.aiohttp_client = aiohttp_client_module
  helpers_module.dispatcher = dispatcher_module
  helpers_module.event = event_module
  helpers_module.restore_state = restore_state_module
  helpers_module.typing = typing_module
  helpers_module.update_coordinator = update_coordinator_module
  helpers_module.selector = selector_module
  helpers_module.device_registry = device_registry_module
  helpers_module.entity_registry = entity_registry_module
  helpers_module.issue_registry = issue_registry_module
  helpers_module.storage = storage_module
  helpers_module.service_info = service_info_module

  util_module.dt = dt_util_module
  util_module.logging = logging_util_module

  components_module.binary_sensor = binary_sensor_component_module
  components_module.button = button_component_module
  components_module.date = date_component_module
  components_module.datetime = datetime_component_module
  components_module.device_automation = device_automation_component_module
  components_module.device_tracker = device_tracker_component_module
  components_module.input_boolean = input_boolean_component_module
  components_module.input_datetime = input_datetime_component_module
  components_module.input_number = input_number_component_module
  components_module.input_select = input_select_component_module
  components_module.number = number_component_module
  components_module.script = script_component_module
  components_module.select = select_component_module
  components_module.sensor = sensor_component_module
  components_module.switch = switch_component_module
  components_module.system_health = system_health_component_module
  components_module.text = text_component_module
  components_module.weather = weather_component_module
  components_module.repairs = repairs_component_module

  sys.modules["homeassistant"] = homeassistant
  sys.modules["homeassistant.const"] = const_module
  sys.modules["homeassistant.core"] = core_module
  sys.modules["homeassistant.exceptions"] = exceptions_module
  sys.modules["homeassistant.helpers"] = helpers_module
  sys.modules["homeassistant.helpers.entity"] = entity_module
  sys.modules["homeassistant.helpers.entity_component"] = entity_component_module
  sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module
  sys.modules["homeassistant.helpers.config_validation"] = config_validation_module
  sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module
  sys.modules["homeassistant.helpers.dispatcher"] = dispatcher_module
  sys.modules["homeassistant.helpers.event"] = event_module
  sys.modules["homeassistant.helpers.restore_state"] = restore_state_module
  sys.modules["homeassistant.helpers.typing"] = typing_module
  sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module
  sys.modules["homeassistant.helpers.selector"] = selector_module
  sys.modules["homeassistant.helpers.device_registry"] = device_registry_module
  sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module
  sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_module
  sys.modules["homeassistant.helpers.storage"] = storage_module
  sys.modules["homeassistant.helpers.service_info"] = service_info_module
  sys.modules["homeassistant.helpers.service_info.dhcp"] = dhcp_module
  sys.modules["homeassistant.helpers.service_info.usb"] = usb_module
  sys.modules["homeassistant.helpers.service_info.zeroconf"] = zeroconf_module
  sys.modules["homeassistant.util"] = util_module
  sys.modules["homeassistant.util.dt"] = dt_util_module
  sys.modules["homeassistant.util.logging"] = logging_util_module
  sys.modules["homeassistant.config_entries"] = config_entries_module
  sys.modules["homeassistant.components"] = components_module
  sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_component_module
  sys.modules["homeassistant.components.button"] = button_component_module
  sys.modules["homeassistant.components.date"] = date_component_module
  sys.modules["homeassistant.components.datetime"] = datetime_component_module
  sys.modules["homeassistant.components.device_automation"] = (
    device_automation_component_module
  )
  sys.modules["homeassistant.components.device_tracker"] = (
    device_tracker_component_module
  )
  sys.modules["homeassistant.components.input_boolean"] = input_boolean_component_module
  sys.modules["homeassistant.components.input_datetime"] = (
    input_datetime_component_module
  )
  sys.modules["homeassistant.components.input_number"] = input_number_component_module
  sys.modules["homeassistant.components.input_select"] = input_select_component_module
  sys.modules["homeassistant.components.number"] = number_component_module
  sys.modules["homeassistant.components.script"] = script_component_module
  sys.modules["homeassistant.components.script.config"] = script_config_module
  sys.modules["homeassistant.components.script.const"] = script_const_module
  sys.modules["homeassistant.components.select"] = select_component_module
  sys.modules["homeassistant.components.sensor"] = sensor_component_module
  sys.modules["homeassistant.components.switch"] = switch_component_module
  sys.modules["homeassistant.components.system_health"] = system_health_component_module
  sys.modules["homeassistant.components.text"] = text_component_module
  sys.modules["homeassistant.components.weather"] = weather_component_module
  sys.modules["homeassistant.components.repairs"] = repairs_component_module
  sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_module
  sys.modules["aiofiles"] = aiofiles_module
