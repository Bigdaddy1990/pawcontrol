"""Minimal Home Assistant compatibility stubs for PawControl tests."""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Optional

import voluptuous as vol


class _UnitEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - debug helper
        return str(self.value)


def _install_const_module() -> None:
    const_module = ModuleType("homeassistant.const")

    class Platform(str, Enum):
        BUTTON = "button"
        SENSOR = "sensor"
        SWITCH = "switch"
        BINARY_SENSOR = "binary_sensor"
        SELECT = "select"
        DEVICE_TRACKER = "device_tracker"
        NUMBER = "number"
        TEXT = "text"
        DATE = "date"
        DATETIME = "datetime"

    const_module.Platform = Platform
    const_module.STATE_UNKNOWN = "unknown"
    const_module.STATE_UNAVAILABLE = "unavailable"
    const_module.STATE_ON = "on"
    const_module.STATE_OFF = "off"
    const_module.STATE_HOME = "home"
    const_module.STATE_NOT_HOME = "not_home"
    const_module.ATTR_LATITUDE = "latitude"
    const_module.ATTR_LONGITUDE = "longitude"

    const_module.CONF_NAME = "name"
    const_module.CONF_USERNAME = "username"
    const_module.CONF_PASSWORD = "password"
    const_module.CONF_ALIAS = "alias"
    const_module.CONF_DEFAULT = "default"
    const_module.CONF_DESCRIPTION = "description"
    const_module.CONF_SEQUENCE = "sequence"
    const_module.PERCENTAGE = "%"

    class UnitOfEnergy(_UnitEnum):
        KILO_WATT_HOUR = "kWh"

    class UnitOfLength(_UnitEnum):
        METERS = "m"

    class UnitOfMass(_UnitEnum):
        KILOGRAMS = "kg"

    class UnitOfSpeed(_UnitEnum):
        METERS_PER_SECOND = "m/s"

    class UnitOfTime(_UnitEnum):
        MINUTES = "min"
        HOURS = "h"
        SECONDS = "s"

    const_module.UnitOfEnergy = UnitOfEnergy
    const_module.UnitOfLength = UnitOfLength
    const_module.UnitOfMass = UnitOfMass
    const_module.UnitOfSpeed = UnitOfSpeed
    const_module.UnitOfTime = UnitOfTime

    sys.modules["homeassistant.const"] = const_module


def _install_util_modules() -> None:
    util_module = ModuleType("homeassistant.util")
    util_module.__path__ = []  # type: ignore[attr-defined]

    dt_module = ModuleType("homeassistant.util.dt")

    def utcnow() -> datetime:
        return datetime.now(UTC)

    def now() -> datetime:
        return datetime.now(UTC).astimezone()

    def as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def as_local(value: datetime) -> datetime:
        return value.astimezone()

    def parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    dt_module.utcnow = utcnow
    dt_module.now = now
    dt_module.as_utc = as_utc
    dt_module.as_local = as_local
    dt_module.parse_datetime = parse_datetime
    dt_module.DEFAULT_TIME_ZONE = UTC
    dt_module.start_of_local_day = lambda value: as_local(value).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    util_module.dt = dt_module

    slugify_module = ModuleType("homeassistant.util.slugify")
    slugify_module.slugify = lambda value: value.lower().replace(" ", "_")

    yaml_module = ModuleType("homeassistant.util.yaml")
    yaml_module.__path__ = []  # type: ignore[attr-defined]
    yaml_loader_module = ModuleType("homeassistant.util.yaml.loader")

    def _parse_scalar(value: str) -> object:
        if value in {"null", "None", "~"}:
            return None
        if value in {"true", "True"}:
            return True
        if value in {"false", "False"}:
            return False
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            return value[1:-1]
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def parse_yaml(stream) -> object:
        text = stream.read() if hasattr(stream, "read") else str(stream)
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        indexed = [
            (len(line) - len(line.lstrip(" ")), line.lstrip(" ")) for line in lines
        ]

        def parse_block(index: int, indent: int) -> tuple[int, object]:
            container: object | None = None
            while index < len(indexed):
                current_indent, content = indexed[index]
                if current_indent < indent:
                    break
                if content.startswith("- "):
                    if not isinstance(container, list):
                        container = []
                    value_str = content[2:].strip()
                    if value_str:
                        container.append(_parse_scalar(value_str))
                        index += 1
                    else:
                        index, value = parse_block(index + 1, current_indent + 2)
                        container.append(value)
                    continue

                if container is None:
                    container = {}
                elif isinstance(container, list):
                    break

                if ":" not in content:
                    raise ValueError(f"Invalid YAML line: {content}")

                key, value_part = content.split(":", 1)
                key = key.strip()
                value_part = value_part.strip()
                if value_part:
                    container[key] = _parse_scalar(value_part)
                    index += 1
                else:
                    index, value = parse_block(index + 1, current_indent + 2)
                    container[key] = value
            if container is None:
                return index, {}
            return index, container

        _, parsed = parse_block(0, 0)
        return parsed

    yaml_loader_module.parse_yaml = parse_yaml

    sys.modules["homeassistant.util.yaml.loader"] = yaml_loader_module
    yaml_module.loader = yaml_loader_module
    util_module.yaml = yaml_module

    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = dt_module
    sys.modules["homeassistant.util.slugify"] = slugify_module
    sys.modules["homeassistant.util.yaml"] = yaml_module


def _install_core_module() -> None:
    core_module = ModuleType("homeassistant.core")

    callback_type = Callable[..., None]

    def callback(func: callback_type) -> callback_type:
        return func

    class ServiceCall:
        def __init__(self, data: Mapping[str, Any] | None = None) -> None:
            self.data = dict(data or {})

    @dataclass
    class Event:
        event_type: str
        data: Mapping[str, Any] | None = None
        time_fired: datetime | None = None

    event_state_changed_data = MutableMapping[str, Any]

    class _ServiceRegistry:
        def __init__(self) -> None:
            self._services: dict[str, dict[str, Callable[..., Any]]] = defaultdict(dict)

        def async_register(
            self,
            domain: str,
            service: str,
            handler: Callable[..., Any],
            schema: Any | None = None,
        ) -> None:
            self._services[domain][service] = handler

        async def async_call(
            self, domain: str, service: str, data: Mapping[str, Any] | None = None
        ) -> None:
            handler = self._services.get(domain, {}).get(service)
            if handler is None:
                raise KeyError(f"Service {domain}.{service} not registered")
            result = handler(ServiceCall(data))
            if asyncio.iscoroutine(result):
                await result

        def has_service(self, domain: str, service: str) -> bool:
            return service in self._services.get(domain, {})

        def async_services(self) -> dict[str, dict[str, Callable[..., Any]]]:
            return self._services

    @dataclass
    class State:
        entity_id: str
        state: str
        attributes: dict[str, Any] = field(default_factory=dict)
        last_changed: datetime | None = None
        last_updated: datetime | None = None

    class _StateMachine:
        def __init__(self) -> None:
            self._states: dict[str, State] = {}

        def get(self, entity_id: str) -> State | None:
            return self._states.get(entity_id)

        def async_set(
            self,
            entity_id: str,
            state: str,
            attributes: Mapping[str, Any] | None = None,
        ) -> None:
            self._states[entity_id] = State(
                entity_id,
                state,
                dict(attributes or {}),
                datetime.now(UTC),
                datetime.now(UTC),
            )

        def async_entity_ids(self, domain: str | None = None) -> list[str]:
            if domain is None:
                return list(self._states)
            prefix = f"{domain}."
            return [
                entity_id for entity_id in self._states if entity_id.startswith(prefix)
            ]

        def async_all(self, domain: str | None = None) -> list[State]:
            ids = self.async_entity_ids(domain)
            return [self._states[entity_id] for entity_id in ids]

    class _EventBus:
        def __init__(self) -> None:
            self._events: list[Event] = []

        async def async_fire(
            self, event_type: str, event_data: Mapping[str, Any] | None = None
        ) -> None:
            self._events.append(Event(event_type, dict(event_data or {})))

    class _Config:
        def __init__(self) -> None:
            self.latitude = 0.0
            self.longitude = 0.0
            self.location = SimpleNamespace(lat=self.latitude, lon=self.longitude)
            self.version = "test"
            self.python_version = "3.13"
            self.start_time = datetime.now(UTC)
            self.components: set[str] = set()

        def path(self, path: str) -> str:
            return str(Path(path))

    class ConfigEntryState(Enum):
        NOT_LOADED = "not_loaded"
        LOADED = "loaded"
        SETUP_RETRY = "setup_retry"
        SETUP_ERROR = "setup_error"

    class ConfigEntryChange(Enum):
        ADDED = "added"
        REMOVED = "removed"
        UPDATED = "updated"

    class ConfigEntry:
        _id_counter = 0

        def __init__(
            self,
            *,
            domain: str,
            data: MutableMapping[str, Any] | None = None,
            options: MutableMapping[str, Any] | None = None,
            title: str | None = None,
        ) -> None:
            ConfigEntry._id_counter += 1
            self.entry_id = f"entry_{ConfigEntry._id_counter}"
            self.domain = domain
            self.data = dict(data or {})
            self.options = dict(options or {})
            self.title = title or domain
            self.runtime_data: Any | None = None
            self.state = ConfigEntryState.NOT_LOADED
            self.unique_id = self.entry_id
            self.update_listeners: list[Callable[..., Any]] = []

        def add_to_hass(self, hass: HomeAssistant) -> None:
            hass.config_entries._entries[self.entry_id] = self
            self.hass = hass

    class ConfigEntriesManager:
        def __init__(self, hass: HomeAssistant) -> None:
            self.hass = hass
            self._entries: dict[str, ConfigEntry] = {}

        def async_entries(self, domain: str | None = None) -> list[ConfigEntry]:
            if domain is None:
                return list(self._entries.values())
            return [entry for entry in self._entries.values() if entry.domain == domain]

        def async_get_entry(self, entry_id: str) -> ConfigEntry | None:
            return self._entries.get(entry_id)

        def async_update_entry(
            self,
            entry: ConfigEntry,
            *,
            data: Mapping[str, Any] | None = None,
            options: Mapping[str, Any] | None = None,
        ) -> None:
            if data is not None:
                entry.data = dict(data)
            if options is not None:
                entry.options = dict(options)

        async def async_forward_entry_setups(
            self, entry: ConfigEntry, platforms: Iterable[str]
        ) -> None:
            entry.state = ConfigEntryState.LOADED
            entry.forwarded_platforms = tuple(platforms)

        async def async_unload_platforms(
            self, entry: ConfigEntry, platforms: Iterable[str]
        ) -> bool:
            entry.state = ConfigEntryState.NOT_LOADED
            return True

        async def async_reload(self, entry_id: str) -> bool:
            entry = self.async_get_entry(entry_id)
            if entry is None:
                return False
            entry.state = ConfigEntryState.LOADED
            return True

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}
            self.loop = asyncio.get_event_loop()
            self.services = _ServiceRegistry()
            self.states = _StateMachine()
            self.bus = _EventBus()
            self.config = _Config()
            self.config_entries = ConfigEntriesManager(self)

        def async_create_task(self, coro: Any) -> asyncio.Task[Any]:
            return asyncio.create_task(coro)

        async def async_add_executor_job(
            self, func: Callable[..., Any], *args: Any
        ) -> Any:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, *args)

    core_module.HomeAssistant = HomeAssistant
    core_module.callback = callback
    core_module.CALLBACK_TYPE = callback_type
    core_module.ServiceCall = ServiceCall
    core_module.Event = Event
    core_module.EventStateChangedData = event_state_changed_data
    core_module.State = State
    core_module.ConfigEntry = ConfigEntry
    core_module.ConfigEntryState = ConfigEntryState
    core_module.ConfigEntryChange = ConfigEntryChange

    sys.modules["homeassistant.core"] = core_module


def _install_exception_module() -> None:
    exceptions_module = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryAuthFailedError(HomeAssistantError):
        pass

    class ConfigEntryNotReadyError(HomeAssistantError):
        pass

    class ServiceValidationError(HomeAssistantError):
        pass

    exceptions_module.HomeAssistantError = HomeAssistantError
    exceptions_module.ConfigEntryAuthFailed = ConfigEntryAuthFailedError
    exceptions_module.ConfigEntryNotReady = ConfigEntryNotReadyError
    exceptions_module.ServiceValidationError = ServiceValidationError

    sys.modules["homeassistant.exceptions"] = exceptions_module


def _install_helper_modules() -> None:
    helpers_module = ModuleType("homeassistant.helpers")
    sys.modules["homeassistant.helpers"] = helpers_module

    cv_module = ModuleType("homeassistant.helpers.config_validation")

    def config_entry_only_config_schema(domain: str) -> Callable[[Any], Any]:
        def _wrapper(config: Any) -> Any:
            return config

        return _wrapper

    cv_module.config_entry_only_config_schema = config_entry_only_config_schema
    cv_module.string = vol.All(str)
    cv_module.boolean = vol.Boolean()
    cv_module.datetime = vol.Datetime()
    cv_module.date = vol.Date()
    sys.modules["homeassistant.helpers.config_validation"] = cv_module

    config_entries_module = ModuleType("homeassistant.config_entries")
    core_module = sys.modules["homeassistant.core"]

    class ConfigFlow:
        VERSION = 1
        MINOR_VERSION = 1

        def __init_subclass__(cls, *, domain: str | None = None, **kwargs) -> None:
            """Mimic Home Assistant's ConfigFlow subclass registration behaviour."""

            super().__init_subclass__(**kwargs)
            if domain is not None:
                cls.domain = domain

        async def async_set_unique_id(
            self, unique_id: str, *, raise_on_progress: bool = False
        ) -> None:
            self._unique_id = unique_id

        async def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any | None = None,
            errors: Mapping[str, str] | None = None,
            description_placeholders: Mapping[str, Any] | None = None,
        ) -> Mapping[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": dict(errors or {}),
                "description_placeholders": dict(description_placeholders or {}),
            }

        async def async_create_entry(
            self,
            *,
            title: str,
            data: Mapping[str, Any],
            options: Mapping[str, Any] | None = None,
        ) -> Mapping[str, Any]:
            return {
                "type": "create_entry",
                "title": title,
                "data": dict(data),
                "options": dict(options or {}),
            }

        async def async_abort(
            self,
            *,
            reason: str,
            description_placeholders: Mapping[str, Any] | None = None,
        ) -> Mapping[str, Any]:
            return {
                "type": "abort",
                "reason": reason,
                "description_placeholders": dict(description_placeholders or {}),
            }

    config_entries_module.ConfigFlow = ConfigFlow
    config_entries_module.ConfigEntry = core_module.ConfigEntry
    config_entries_module.ConfigEntryState = core_module.ConfigEntryState
    config_entries_module.ConfigEntryChange = core_module.ConfigEntryChange
    config_entries_module.ConfigFlowResult = Mapping[str, Any]
    config_entries_module.OptionsFlowResult = Mapping[str, Any]
    config_entries_module.ConfigFlowResultDict = Mapping[str, Any]

    class OptionsFlow:
        async def async_step_init(
            self, user_input: Mapping[str, Any] | None = None
        ) -> Mapping[str, Any]:
            return {"type": "create_entry", "data": dict(user_input or {})}

    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.SOURCE_USER = "user"
    config_entries_module.SOURCE_REAUTH = "reauth"
    config_entries_module.SOURCE_DHCP = "dhcp"
    config_entries_module.SOURCE_USB = "usb"
    config_entries_module.SOURCE_ZEROCONF = "zeroconf"
    config_entries_module.SOURCE_IMPORT = "import"
    config_entries_module.SIGNAL_CONFIG_ENTRY_CHANGED = "config_entry_changed"
    config_entries_module.HANDLERS = {}
    sys.modules["homeassistant.config_entries"] = config_entries_module

    aiohttp_module = ModuleType("homeassistant.helpers.aiohttp_client")

    class DummySession:
        async def close(self) -> None:
            return None

    def async_get_clientsession(hass: Any) -> DummySession:
        return DummySession()

    aiohttp_module.async_get_clientsession = async_get_clientsession
    sys.modules["homeassistant.helpers.aiohttp_client"] = aiohttp_module

    dispatcher_module = ModuleType("homeassistant.helpers.dispatcher")
    dispatcher_module.async_dispatcher_connect = (
        lambda hass, signal, target: lambda: None
    )
    dispatcher_module.async_dispatcher_send = lambda hass, signal, *args, **kwargs: None
    sys.modules["homeassistant.helpers.dispatcher"] = dispatcher_module

    event_module = ModuleType("homeassistant.helpers.event")

    def _track_callback(*args: Any, **kwargs: Any) -> Callable[[], None]:
        return lambda: None

    event_module.async_track_time_interval = _track_callback
    event_module.async_track_time_change = _track_callback
    event_module.async_track_state_change_event = _track_callback
    sys.modules["homeassistant.helpers.event"] = event_module

    selector_module = ModuleType("homeassistant.helpers.selector")
    selector_module.selector = lambda config: config
    sys.modules["homeassistant.helpers.selector"] = selector_module

    service_info_package = ModuleType("homeassistant.helpers.service_info")
    service_info_package.__path__ = []  # type: ignore[attr-defined]
    dhcp_module = ModuleType("homeassistant.helpers.service_info.dhcp")
    usb_module = ModuleType("homeassistant.helpers.service_info.usb")
    zeroconf_module = ModuleType("homeassistant.helpers.service_info.zeroconf")

    @dataclass
    class DhcpServiceInfo:
        ip: str | None = None
        hostname: str | None = None
        macaddress: str | None = None

    dhcp_module.DhcpServiceInfo = DhcpServiceInfo
    sys.modules["homeassistant.helpers.service_info.dhcp"] = dhcp_module

    @dataclass
    class UsbServiceInfo:
        device: str | None = None
        vid: str | None = None
        pid: str | None = None
        serial_number: str | None = None

    usb_module.UsbServiceInfo = UsbServiceInfo
    sys.modules["homeassistant.helpers.service_info.usb"] = usb_module

    @dataclass
    class ZeroconfServiceInfo:
        host: str | None = None
        port: int | None = None
        hostname: str | None = None
        properties: dict[str, str] | None = None

    zeroconf_module.ZeroconfServiceInfo = ZeroconfServiceInfo
    sys.modules["homeassistant.helpers.service_info.zeroconf"] = zeroconf_module

    service_info_package.dhcp = dhcp_module
    service_info_package.usb = usb_module
    service_info_package.zeroconf = zeroconf_module
    sys.modules["homeassistant.helpers.service_info"] = service_info_package

    issue_module = ModuleType("homeassistant.helpers.issue_registry")
    issue_module.DOMAIN = "issue_registry"

    class IssueSeverity(str, Enum):
        WARNING = "warning"
        ERROR = "error"

    issue_module.IssueSeverity = IssueSeverity
    issue_module.IssueRegistry = SimpleNamespace
    issue_module.async_create_issue = lambda *args, **kwargs: None
    issue_module.async_delete_issue = lambda *args, **kwargs: None
    sys.modules["homeassistant.helpers.issue_registry"] = issue_module

    entity_module = ModuleType("homeassistant.helpers.entity")

    class Entity:
        entity_id: str | None = None

        async def async_added_to_hass(self) -> None:  # pragma: no cover - stub
            return None

    class EntityCategory(str, Enum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity_module.Entity = Entity
    entity_module.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = entity_module

    entity_platform_module = ModuleType("homeassistant.helpers.entity_platform")
    entity_platform_module.AddEntitiesCallback = Callable[[Iterable[Entity]], None]
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform_module

    restore_module = ModuleType("homeassistant.helpers.restore_state")

    class RestoreEntity(Entity):
        pass

    restore_module.RestoreEntity = RestoreEntity
    sys.modules["homeassistant.helpers.restore_state"] = restore_module

    storage_module = ModuleType("homeassistant.helpers.storage")

    class Store:
        def __init__(self, hass: Any, version: int, key: str) -> None:
            self.data: Any | None = None

        async def async_load(self) -> Any | None:
            return self.data

        async def async_save(self, data: Any) -> None:
            self.data = data

    storage_module.Store = Store
    sys.modules["homeassistant.helpers.storage"] = storage_module

    entity_component_module = ModuleType("homeassistant.helpers.entity_component")

    class EntityComponent:
        def __init__(self, logger: Any, domain: str, hass: Any) -> None:
            self.entities: list[Any] = []

        async def async_setup_entry(self, entry: Any) -> None:
            return None

    entity_component_module.EntityComponent = EntityComponent
    sys.modules["homeassistant.helpers.entity_component"] = entity_component_module

    typing_module = ModuleType("homeassistant.helpers.typing")
    typing_module.ConfigType = Mapping[str, Any]
    sys.modules["homeassistant.helpers.typing"] = typing_module

    integration_module = ModuleType("homeassistant.helpers.integration_platform")
    integration_module.async_process_integration_platforms = lambda *args, **kwargs: []
    sys.modules["homeassistant.helpers.integration_platform"] = integration_module

    update_module = ModuleType("homeassistant.helpers.update_coordinator")

    class UpdateFailedError(Exception):
        pass

    class CoordinatorEntity(entity_module.Entity):
        def __init__(self, coordinator: DataUpdateCoordinator) -> None:
            self.coordinator = coordinator

        def __class_getitem__(cls, item: Any) -> type[CoordinatorEntity]:
            return cls

    class DataUpdateCoordinator:
        def __init__(
            self,
            hass: Any,
            logger: Any,
            *,
            name: str,
            update_interval: timedelta | None = None,
            config_entry: Any | None = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval or timedelta(seconds=60)
            self.config_entry = config_entry
            self.data: Any | None = None
            self.last_update_success = True
            self.last_update_time: datetime | None = None

        def __class_getitem__(cls, item: Any) -> type[DataUpdateCoordinator]:
            return cls

        async def async_config_entry_first_refresh(self) -> None:
            return None

        async def async_request_refresh(self) -> None:
            return None

        async def async_refresh(self) -> None:
            return None

    update_module.DataUpdateCoordinator = DataUpdateCoordinator
    update_module.CoordinatorEntity = CoordinatorEntity
    update_module.UpdateFailed = UpdateFailedError
    sys.modules["homeassistant.helpers.update_coordinator"] = update_module

    device_registry_module = ModuleType("homeassistant.helpers.device_registry")

    @dataclass
    class DeviceEntry:
        id: str
        identifiers: set[tuple[str, str]] = field(default_factory=set)
        manufacturer: str | None = None
        model: str | None = None
        name: str | None = None

    @dataclass
    class DeviceInfo:
        identifiers: set[tuple[str, str]]
        manufacturer: str | None = None
        model: str | None = None
        name: str | None = None
        sw_version: str | None = None
        hw_version: str | None = None
        configuration_url: str | None = None
        suggested_area: str | None = None
        serial_number: str | None = None

    class DeviceRegistry:
        def __init__(self) -> None:
            self._devices: dict[str, DeviceEntry] = {}
            self._counter = 0

        def async_get_or_create(
            self,
            *,
            config_entry_id: str,
            identifiers: Iterable[tuple[str, str]],
            manufacturer: str | None = None,
            model: str | None = None,
            name: str | None = None,
        ) -> DeviceEntry:
            key = next(iter(identifiers))
            for device in self._devices.values():
                if key in device.identifiers:
                    return device
            self._counter += 1
            device = DeviceEntry(
                id=f"device_{self._counter}",
                identifiers=set(identifiers),
                manufacturer=manufacturer,
                model=model,
                name=name,
            )
            self._devices[device.id] = device
            return device

    _device_registry = DeviceRegistry()

    device_registry_module.DeviceEntry = DeviceEntry
    device_registry_module.DeviceInfo = DeviceInfo
    device_registry_module.DeviceRegistry = DeviceRegistry
    device_registry_module.async_get = lambda hass: _device_registry
    sys.modules["homeassistant.helpers.device_registry"] = device_registry_module

    entity_registry_module = ModuleType("homeassistant.helpers.entity_registry")

    @dataclass
    class EntityRegistryEntry:
        entity_id: str
        unique_id: str
        platform: str
        device_id: str | None = None

    class EntityRegistry:
        def __init__(self) -> None:
            self._entities: dict[str, EntityRegistryEntry] = {}

        def async_get_or_create(
            self,
            domain: str,
            platform: str,
            unique_id: str,
            *,
            config_entry: Any | None = None,
            device_id: str | None = None,
            suggested_object_id: str | None = None,
        ) -> EntityRegistryEntry:
            object_id = suggested_object_id or unique_id
            entity_id = f"{domain}.{object_id}"
            entry = EntityRegistryEntry(
                entity_id=entity_id,
                unique_id=unique_id,
                platform=platform,
                device_id=device_id,
            )
            self._entities[entity_id] = entry
            return entry

    _entity_registry = EntityRegistry()

    entity_registry_module.EntityRegistryEntry = EntityRegistryEntry
    entity_registry_module.async_get = lambda hass: _entity_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry_module


def _install_component_modules() -> None:
    entity_module: ModuleType = sys.modules["homeassistant.helpers.entity"]

    components_package = ModuleType("homeassistant.components")
    components_package.__path__ = []  # type: ignore[attr-defined]
    sys.modules["homeassistant.components"] = components_package

    def _register(module_name: str, entity_cls: type[entity_module.Entity]) -> None:
        module = ModuleType(module_name)
        module.Entity = entity_cls
        sys.modules[module_name] = module

    class ButtonEntity(entity_module.Entity):
        pass

    button_module = ModuleType("homeassistant.components.button")
    button_module.ButtonEntity = ButtonEntity

    class ButtonDeviceClass(str, Enum):
        RESTART = "restart"

    button_module.ButtonDeviceClass = ButtonDeviceClass
    sys.modules["homeassistant.components.button"] = button_module
    components_package.button = button_module

    class SwitchEntity(entity_module.Entity):
        pass

    switch_module = ModuleType("homeassistant.components.switch")
    switch_module.SwitchEntity = SwitchEntity

    class SwitchDeviceClass(str, Enum):
        SWITCH = "switch"

    switch_module.SwitchDeviceClass = SwitchDeviceClass
    sys.modules["homeassistant.components.switch"] = switch_module
    components_package.switch = switch_module

    class SensorEntity(entity_module.Entity):
        pass

    sensor_module = ModuleType("homeassistant.components.sensor")
    sensor_module.SensorEntity = SensorEntity

    class SensorStateClass(str, Enum):
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    class SensorDeviceClass(str, Enum):
        TEMPERATURE = "temperature"
        TIMESTAMP = "timestamp"
        DURATION = "duration"
        BATTERY = "battery"
        WEIGHT = "weight"

    sensor_module.SensorStateClass = SensorStateClass
    sensor_module.SensorDeviceClass = SensorDeviceClass
    sys.modules["homeassistant.components.sensor"] = sensor_module
    components_package.sensor = sensor_module

    class NumberEntity(entity_module.Entity):
        pass

    number_module = ModuleType("homeassistant.components.number")
    number_module.NumberEntity = NumberEntity

    class NumberDeviceClass(str, Enum):
        TEMPERATURE = "temperature"
        WEIGHT = "weight"

    class NumberMode(str, Enum):
        BOX = "box"
        SLIDER = "slider"
        AUTO = "auto"

    number_module.NumberDeviceClass = NumberDeviceClass
    number_module.NumberMode = NumberMode
    sys.modules["homeassistant.components.number"] = number_module
    components_package.number = number_module

    class TextEntity(entity_module.Entity):
        pass

    text_module = ModuleType("homeassistant.components.text")
    text_module.TextEntity = TextEntity

    class TextMode(str, Enum):
        TEXT = "text"
        PASSWORD = "password"

    text_module.TextMode = TextMode
    sys.modules["homeassistant.components.text"] = text_module
    components_package.text = text_module

    class SelectEntity(entity_module.Entity):
        pass

    select_module = ModuleType("homeassistant.components.select")
    select_module.SelectEntity = SelectEntity
    sys.modules["homeassistant.components.select"] = select_module
    components_package.select = select_module

    class DateEntity(entity_module.Entity):
        pass

    date_module = ModuleType("homeassistant.components.date")
    date_module.DateEntity = DateEntity
    sys.modules["homeassistant.components.date"] = date_module
    components_package.date = date_module

    class DateTimeEntity(entity_module.Entity):
        pass

    datetime_module = ModuleType("homeassistant.components.datetime")
    datetime_module.DateTimeEntity = DateTimeEntity
    sys.modules["homeassistant.components.datetime"] = datetime_module
    components_package.datetime = datetime_module

    input_boolean_module = ModuleType("homeassistant.components.input_boolean")
    input_boolean_module.DOMAIN = "input_boolean"
    sys.modules["homeassistant.components.input_boolean"] = input_boolean_module
    components_package.input_boolean = input_boolean_module

    input_datetime_module = ModuleType("homeassistant.components.input_datetime")
    input_datetime_module.DOMAIN = "input_datetime"
    sys.modules["homeassistant.components.input_datetime"] = input_datetime_module
    components_package.input_datetime = input_datetime_module

    input_number_module = ModuleType("homeassistant.components.input_number")
    input_number_module.DOMAIN = "input_number"
    sys.modules["homeassistant.components.input_number"] = input_number_module
    components_package.input_number = input_number_module

    input_select_module = ModuleType("homeassistant.components.input_select")
    input_select_module.DOMAIN = "input_select"
    sys.modules["homeassistant.components.input_select"] = input_select_module
    components_package.input_select = input_select_module

    class DeviceTrackerEntity(entity_module.Entity):
        pass

    device_tracker_module = ModuleType("homeassistant.components.device_tracker")
    device_tracker_module.DeviceTrackerEntity = DeviceTrackerEntity
    device_tracker_module.TrackerEntity = DeviceTrackerEntity

    class SourceType(str, Enum):
        GPS = "gps"

    device_tracker_module.SourceType = SourceType
    sys.modules["homeassistant.components.device_tracker"] = device_tracker_module
    components_package.device_tracker = device_tracker_module

    system_health_module = ModuleType("homeassistant.components.system_health")

    class SystemHealthRegistration:
        def __init__(self, hass: Any, domain: str) -> None:
            self.callbacks: list[Callable[..., Any]] = []

        def async_register_info(self, callback: Callable[..., Any]) -> None:
            self.callbacks.append(callback)

    async def async_check_can_reach_url(hass: Any, url: str) -> bool:
        return True

    system_health_module.SystemHealthRegistration = SystemHealthRegistration
    system_health_module.async_check_can_reach_url = async_check_can_reach_url
    sys.modules["homeassistant.components.system_health"] = system_health_module
    components_package.system_health = system_health_module

    script_module = ModuleType("homeassistant.components.script")

    class ScriptEntity(entity_module.Entity):
        pass

    script_module.ScriptEntity = ScriptEntity
    script_module.DOMAIN = "script"
    script_module.SCRIPT_ENTITY_SCHEMA = {}
    sys.modules["homeassistant.components.script"] = script_module
    components_package.script = script_module

    script_config_module = ModuleType("homeassistant.components.script.config")
    script_config_module.SCRIPT_ENTITY_SCHEMA = {}
    sys.modules["homeassistant.components.script.config"] = script_config_module

    script_const_module = ModuleType("homeassistant.components.script.const")
    script_const_module.CONF_FIELDS = "fields"
    script_const_module.CONF_TRACE = "trace"
    script_const_module.CONF_ALIAS = "alias"
    script_const_module.CONF_DEFAULT = "default"
    script_const_module.CONF_DESCRIPTION = "description"
    script_const_module.CONF_NAME = "name"
    script_const_module.CONF_SEQUENCE = "sequence"
    sys.modules["homeassistant.components.script.const"] = script_const_module

    repairs_module = ModuleType("homeassistant.components.repairs")

    class RepairsFlow:
        pass

    repairs_module.RepairsFlow = RepairsFlow
    sys.modules["homeassistant.components.repairs"] = repairs_module

    class BinarySensorEntity(entity_module.Entity):
        _attr_is_on = False

        @property
        def is_on(self) -> bool:
            return self._attr_is_on

    binary_sensor_module = ModuleType("homeassistant.components.binary_sensor")
    binary_sensor_module.BinarySensorEntity = BinarySensorEntity

    class BinarySensorDeviceClass(str, Enum):
        MOTION = "motion"
        PROBLEM = "problem"
        CONNECTIVITY = "connectivity"
        SAFETY = "safety"
        RUNNING = "running"
        PRESENCE = "presence"
        BATTERY = "battery"

    binary_sensor_module.BinarySensorDeviceClass = BinarySensorDeviceClass
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor_module
    components_package.binary_sensor = binary_sensor_module

    class WeatherEntity(entity_module.Entity):
        pass

    weather_module = ModuleType("homeassistant.components.weather")
    weather_module.WeatherEntity = WeatherEntity

    class WeatherCondition(str, Enum):
        SUNNY = "sunny"
        CLOUDY = "cloudy"
        RAINY = "rainy"

    weather_module.WeatherCondition = WeatherCondition
    sys.modules["homeassistant.components.weather"] = weather_module
    components_package.weather = weather_module

    data_entry_flow_module = ModuleType("homeassistant.data_entry_flow")

    class FlowResultType(str, Enum):
        FORM = "form"
        CREATE_ENTRY = "create_entry"
        ABORT = "abort"
        MENU = "menu"

    data_entry_flow_module.FlowResultType = FlowResultType
    data_entry_flow_module.FlowResult = Mapping[str, Any]
    data_entry_flow_module.RESULT_TYPE_FORM = FlowResultType.FORM
    data_entry_flow_module.RESULT_TYPE_CREATE_ENTRY = FlowResultType.CREATE_ENTRY
    data_entry_flow_module.RESULT_TYPE_ABORT = FlowResultType.ABORT
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow_module


def install_homeassistant_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    root = ModuleType("homeassistant")
    root.__path__ = []  # type: ignore[attr-defined]
    sys.modules["homeassistant"] = root

    _install_const_module()
    _install_util_modules()
    _install_core_module()
    _install_exception_module()
    _install_helper_modules()
    _install_component_modules()


install_homeassistant_stubs()
