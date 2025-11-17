"""Home Assistant compatibility shims for PawControl's test suite."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

__all__ = [
    "ConfigEntryAuthFailed",
    "ConfigEntryNotReady",
    "ConfigEntryState",
    "HomeAssistantError",
    "Platform",
    "install_homeassistant_stubs",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_ROOT = REPO_ROOT / "custom_components"
PAWCONTROL_ROOT = COMPONENT_ROOT / "pawcontrol"


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


class ConfigEntryState(StrEnum):
    """Enum mirroring Home Assistant's config entry states."""

    LOADED = "loaded"
    SETUP_RETRY = "setup_retry"
    NOT_LOADED = "not_loaded"


class _ConfigEntryError(Exception):
    """Base class for stub config entry exceptions."""


class ConfigEntryAuthFailed(_ConfigEntryError):  # noqa: N818
    """Replacement for :class:`homeassistant.exceptions.ConfigEntryAuthFailed`."""


class ConfigEntryNotReady(_ConfigEntryError):  # noqa: N818
    """Replacement for :class:`homeassistant.exceptions.ConfigEntryNotReady`."""


class HomeAssistantError(Exception):
    """Replacement for :class:`homeassistant.exceptions.HomeAssistantError`."""


class HomeAssistant:
    """Minimal stand-in for :class:`homeassistant.core.HomeAssistant`."""

    def __init__(self) -> None:
        self.data: dict[str, object] = {}


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


class Context:
    """Lightweight ``homeassistant.core.Context`` replacement."""

    def __init__(self, user_id: str | None = None) -> None:
        self.user_id = user_id


def _callback(func: Callable[..., None]) -> Callable[..., None]:
    return func


class ConfigEntry:
    """Minimal representation of Home Assistant config entries."""

    def __init__(
        self,
        entry_id: str | None = None,
        *,
        data: dict[str, object] | None = None,
        options: dict[str, object] | None = None,
    ) -> None:
        self.entry_id = entry_id or "stub-entry"
        self.data = data or {}
        self.options = options or {}
        self.state = ConfigEntryState.LOADED
        self.runtime_data: object | None = None


class OptionsFlow:
    """Options flow stub used by coordinator tests."""

    async def async_step_init(self, user_input: dict[str, object] | None = None):
        return {"type": "create_entry", "data": user_input or {}}


class ConfigFlowResult(dict):
    """Dictionary wrapper to mimic Home Assistant flow results."""


class DeviceInfo(dict):
    """Match Home Assistant's mapping-style device info container."""


class DeviceEntry:
    """Simple device registry entry stub."""

    def __init__(self, **kwargs: object) -> None:
        self.id = kwargs.get("id", "device")


class DeviceRegistry:
    """In-memory registry used by device tests."""

    def __init__(self) -> None:
        self.devices: dict[str, DeviceEntry] = {}

    def async_get_or_create(self, **kwargs: object) -> DeviceEntry:
        entry = DeviceEntry(**kwargs)
        self.devices[entry.id] = entry
        return entry

    def async_update_device(self, device_id: str, **kwargs: object) -> DeviceEntry:
        return self.devices.setdefault(device_id, DeviceEntry(id=device_id))

    def async_entries_for_config_entry(self, entry_id: str) -> list[DeviceEntry]:
        return list(self.devices.values())

    def async_listen(self, callback):  # type: ignore[no-untyped-def]
        return None


def _async_get_device_registry(*args: object, **kwargs: object) -> DeviceRegistry:
    return DeviceRegistry()


def _async_entries_for_device_config(
    registry: DeviceRegistry, entry_id: str
) -> list[DeviceEntry]:
    return list(registry.devices.values())


class RegistryEntry:
    """Entity registry entry stub."""

    def __init__(self, entity_id: str, **kwargs: object) -> None:
        self.entity_id = entity_id
        self.device_id = kwargs.get("device_id")


class EntityRegistry:
    """Simple entity registry storing entries in a dict."""

    def __init__(self) -> None:
        self.entities: dict[str, RegistryEntry] = {}

    def async_get(self, entity_id: str) -> RegistryEntry | None:
        return self.entities.get(entity_id)

    def async_get_or_create(self, entity_id: str, **kwargs: object) -> RegistryEntry:
        entry = RegistryEntry(entity_id, **kwargs)
        self.entities[entity_id] = entry
        return entry

    def async_update_entity(self, entity_id: str, **kwargs: object) -> RegistryEntry:
        return self.entities.setdefault(entity_id, RegistryEntry(entity_id))

    def async_entries_for_config_entry(self, entry_id: str) -> list[RegistryEntry]:
        return list(self.entities.values())

    def async_listen(self, callback):  # type: ignore[no-untyped-def]
        return None


def _async_get_entity_registry(*args: object, **kwargs: object) -> EntityRegistry:
    return EntityRegistry()


def _async_entries_for_registry_config(
    registry: EntityRegistry, entry_id: str
) -> list[RegistryEntry]:
    return list(registry.entities.values())


class Store:
    """Persistence helper used by coordinator storage tests."""

    def __init__(self) -> None:
        self.data: object | None = None

    async def async_load(self) -> object | None:
        return self.data

    async def async_save(self, data: object) -> None:
        self.data = data


class Entity:
    """Base entity stub."""

    pass


def _config_entry_only_config_schema(domain: str):
    def _schema(data: object) -> object:
        return data

    return _schema


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


async def _async_track_time_interval(*args: object, **kwargs: object):
    return None


async def _async_track_time_change(*args: object, **kwargs: object):
    return None


async def _async_call_later(*args: object, **kwargs: object):
    return None


async def _async_track_state_change_event(*args: object, **kwargs: object):
    return None


class DataUpdateCoordinator:
    """Simplified coordinator used by runtime data tests."""

    def __init__(
        self, hass: object, *, name: str | None = None, **kwargs: object
    ) -> None:
        self.hass = hass
        self.name = name or "stub"

    async def async_config_entry_first_refresh(self) -> None:
        return None

    async def async_request_refresh(self) -> None:
        return None

    @classmethod
    def __class_getitem__(cls, item):  # pragma: no cover - helper stub
        return cls


class CoordinatorUpdateFailed(Exception):  # noqa: N818
    """Error raised when DataUpdateCoordinator refreshes fail."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
        "custom_components", types.ModuleType("custom_components")
    )
    custom_components_pkg.__path__ = [str(COMPONENT_ROOT)]

    pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
    pawcontrol_pkg.__path__ = [str(PAWCONTROL_ROOT)]
    sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg


def install_homeassistant_stubs() -> None:
    """Register lightweight Home Assistant modules required by the tests."""

    for module_name in [
        "homeassistant",
        "homeassistant.const",
        "homeassistant.core",
        "homeassistant.exceptions",
        "homeassistant.helpers",
        "homeassistant.helpers.entity",
        "homeassistant.helpers.config_validation",
        "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.event",
        "homeassistant.helpers.update_coordinator",
        "homeassistant.helpers.selector",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.entity_registry",
        "homeassistant.helpers.storage",
        "homeassistant.helpers.issue_registry",
        "homeassistant.util",
        "homeassistant.util.dt",
        "homeassistant.util.logging",
        "homeassistant.config_entries",
    ]:
        sys.modules.pop(module_name, None)

    _register_custom_component_packages()

    homeassistant = types.ModuleType("homeassistant")
    const_module = types.ModuleType("homeassistant.const")
    core_module = types.ModuleType("homeassistant.core")
    exceptions_module = types.ModuleType("homeassistant.exceptions")
    helpers_module = types.ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []
    entity_module = types.ModuleType("homeassistant.helpers.entity")
    config_validation_module = types.ModuleType(
        "homeassistant.helpers.config_validation"
    )
    aiohttp_client_module = types.ModuleType("homeassistant.helpers.aiohttp_client")
    event_module = types.ModuleType("homeassistant.helpers.event")
    update_coordinator_module = types.ModuleType(
        "homeassistant.helpers.update_coordinator"
    )
    device_registry_module = types.ModuleType("homeassistant.helpers.device_registry")
    entity_registry_module = types.ModuleType("homeassistant.helpers.entity_registry")
    issue_registry_module = types.ModuleType("homeassistant.helpers.issue_registry")
    storage_module = types.ModuleType("homeassistant.helpers.storage")
    config_entries_module = types.ModuleType("homeassistant.config_entries")
    util_module = types.ModuleType("homeassistant.util")
    util_module.__path__ = []
    dt_util_module = types.ModuleType("homeassistant.util.dt")
    logging_util_module = types.ModuleType("homeassistant.util.logging")
    selector_module = types.ModuleType("homeassistant.helpers.selector")

    const_module.Platform = Platform
    const_module.STATE_ON = "on"
    const_module.STATE_OFF = "off"
    const_module.STATE_UNKNOWN = "unknown"
    const_module.STATE_HOME = "home"
    const_module.STATE_NOT_HOME = "not_home"

    core_module.HomeAssistant = HomeAssistant
    core_module.Event = Event
    core_module.EventStateChangedData = dict[str, object]
    core_module.State = State
    core_module.Context = Context
    core_module.callback = _callback
    core_module.CALLBACK_TYPE = Callable[..., None]

    exceptions_module.ConfigEntryAuthFailed = ConfigEntryAuthFailed
    exceptions_module.ConfigEntryNotReady = ConfigEntryNotReady
    exceptions_module.HomeAssistantError = HomeAssistantError

    config_entries_module.ConfigEntry = ConfigEntry
    config_entries_module.ConfigEntryState = ConfigEntryState
    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.ConfigFlowResult = ConfigFlowResult

    device_registry_module.DeviceInfo = DeviceInfo
    device_registry_module.DeviceEntry = DeviceEntry
    device_registry_module.DeviceRegistry = DeviceRegistry
    device_registry_module.async_get = _async_get_device_registry
    device_registry_module.async_entries_for_config_entry = (
        _async_entries_for_device_config
    )

    entity_registry_module.RegistryEntry = RegistryEntry
    entity_registry_module.EntityRegistry = EntityRegistry
    entity_registry_module.async_get = _async_get_entity_registry
    entity_registry_module.async_entries_for_config_entry = (
        _async_entries_for_registry_config
    )

    issue_registry_module.DOMAIN = "issue_registry"
    issue_registry_module.async_create_issue = lambda *args, **kwargs: None
    issue_registry_module.async_delete_issue = lambda *args, **kwargs: None

    storage_module.Store = Store

    entity_module.Entity = Entity

    config_validation_module.config_entry_only_config_schema = (
        _config_entry_only_config_schema
    )
    aiohttp_client_module.async_get_clientsession = _async_get_clientsession
    setattr(aiohttp_client_module, "_async_make_resolver", _async_make_resolver)
    event_module.async_track_time_interval = _async_track_time_interval
    event_module.async_track_time_change = _async_track_time_change
    event_module.async_call_later = _async_call_later
    event_module.async_track_state_change_event = _async_track_state_change_event

    update_coordinator_module.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator_module.CoordinatorUpdateFailed = CoordinatorUpdateFailed

    dt_util_module.utcnow = _utcnow
    logging_util_module.log_exception = _log_exception

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

    homeassistant.const = const_module
    homeassistant.core = core_module
    homeassistant.exceptions = exceptions_module
    homeassistant.helpers = helpers_module
    homeassistant.config_entries = config_entries_module
    homeassistant.util = util_module

    helpers_module.entity = entity_module
    helpers_module.config_validation = config_validation_module
    helpers_module.aiohttp_client = aiohttp_client_module
    helpers_module.event = event_module
    helpers_module.update_coordinator = update_coordinator_module
    helpers_module.selector = selector_module
    helpers_module.device_registry = device_registry_module
    helpers_module.entity_registry = entity_registry_module
    helpers_module.issue_registry = issue_registry_module
    helpers_module.storage = storage_module

    util_module.dt = dt_util_module
    util_module.logging = logging_util_module

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.const"] = const_module
    sys.modules["homeassistant.core"] = core_module
    sys.modules["homeassistant.exceptions"] = exceptions_module
    sys.modules["homeassistant.helpers"] = helpers_module
    sys.modules["homeassistant.helpers.entity"] = entity_module
    sys.modules["homeassistant.helpers.config_validation"] = config_validation_module
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_client_module
    sys.modules["homeassistant.helpers.event"] = event_module
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator_module
    sys.modules["homeassistant.helpers.selector"] = selector_module
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_module
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry_module
    sys.modules["homeassistant.helpers.storage"] = storage_module
    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = dt_util_module
    sys.modules["homeassistant.util.logging"] = logging_util_module
    sys.modules["homeassistant.config_entries"] = config_entries_module
