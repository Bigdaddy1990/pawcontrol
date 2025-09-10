"""Test environment compatibility helpers.

This module is loaded automatically by Python before any other imports. It
ensures that optional Home Assistant helpers exist when the test environment
provides a minimal stub of the framework.
"""

from __future__ import annotations

import importlib
import os
import sys
from contextlib import suppress
from datetime import UTC, datetime
from enum import StrEnum
from types import ModuleType, SimpleNamespace
from typing import Callable

# Prevent external pytest plugins from auto-loading during test collection.
# This keeps the test environment lightweight and ensures that the minimal
# Home Assistant stubs provided below remain sufficient.
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

try:  # pragma: no cover - Home Assistant available
    from homeassistant.helpers import device_registry, entity  # type: ignore

    ha = sys.modules["homeassistant"]
except Exception:  # pragma: no cover - create minimal stubs
    ha = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    ha.__path__ = []  # mark as package
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []  # mark as package
    ha.helpers = helpers  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers"] = helpers
    entity = ModuleType("homeassistant.helpers.entity")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    sys.modules["homeassistant.helpers.entity"] = entity
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
    helpers.entity_registry = entity_registry  # type: ignore[attr-defined]

    class DeviceRegistry:  # pragma: no cover - stub
        pass

    device_registry.DeviceRegistry = DeviceRegistry  # type: ignore[attr-defined]

    class EntityRegistry:  # pragma: no cover - stub
        pass

    entity_registry.EntityRegistry = EntityRegistry  # type: ignore[attr-defined]

    config_validation = ModuleType("homeassistant.helpers.config_validation")
    helpers.config_validation = config_validation  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.config_validation"] = config_validation

    def ensure_list(value):  # pragma: no cover - simple helper
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    def config_entry_only_config_schema(domain):  # pragma: no cover - test stub
        def schema(config):
            return config

        return schema

    config_validation.ensure_list = ensure_list  # type: ignore[attr-defined]
    config_validation.config_entry_only_config_schema = config_entry_only_config_schema  # type: ignore[attr-defined]
    config_validation.string = str  # type: ignore[attr-defined]
    config_validation.boolean = bool  # type: ignore[attr-defined]

    helpers_typing = ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict  # type: ignore[attr-defined]
    helpers.typing = helpers_typing  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.typing"] = helpers_typing

    selector = ModuleType("homeassistant.helpers.selector")
    helpers.selector = selector  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.selector"] = selector

    class BooleanSelector:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelector:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelectorMode(StrEnum):  # pragma: no cover - stub
        BOX = "box"

    class NumberSelectorConfig:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelector:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelectorMode(StrEnum):  # pragma: no cover - stub
        DROPDOWN = "dropdown"

    class SelectSelectorConfig:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            pass

    selector.BooleanSelector = BooleanSelector  # type: ignore[attr-defined]
    selector.NumberSelector = NumberSelector  # type: ignore[attr-defined]
    selector.NumberSelectorMode = NumberSelectorMode  # type: ignore[attr-defined]
    selector.NumberSelectorConfig = NumberSelectorConfig  # type: ignore[attr-defined]
    selector.SelectSelector = SelectSelector  # type: ignore[attr-defined]
    selector.SelectSelectorMode = SelectSelectorMode  # type: ignore[attr-defined]
    selector.SelectSelectorConfig = SelectSelectorConfig  # type: ignore[attr-defined]

    def _selector(cfg):  # pragma: no cover - stub
        return cfg

    selector.selector = _selector  # type: ignore[attr-defined]

    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    helpers.entity_platform = entity_platform  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    entity_platform.AddEntitiesCallback = Callable[..., None]  # type: ignore[attr-defined]

    storage = ModuleType("homeassistant.helpers.storage")

    class Store:  # pragma: no cover - stub
        def __init__(self, *args, **kwargs):
            self.data = None

        async def async_load(self):
            return self.data

        async def async_save(self, data):
            self.data = data

    storage.Store = Store  # type: ignore[attr-defined]
    helpers.storage = storage  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.storage"] = storage

    event = ModuleType("homeassistant.helpers.event")

    async def async_track_time_interval(*args, **kwargs):  # pragma: no cover - stub
        return None

    async def async_track_time(*args, **kwargs):  # pragma: no cover - stub
        return None

    event.async_track_time_interval = async_track_time_interval  # type: ignore[attr-defined]
    event.async_track_time = async_track_time  # type: ignore[attr-defined]
    helpers.event = event  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.event"] = event

    setup = ModuleType("homeassistant.setup")

    async def async_setup_component(*args, **kwargs):  # pragma: no cover - stub
        return True

    setup.async_setup_component = async_setup_component  # type: ignore[attr-defined]
    sys.modules["homeassistant.setup"] = setup

    issue_registry = ModuleType("homeassistant.helpers.issue_registry")

    class IssueSeverity(StrEnum):  # pragma: no cover - stub
        WARNING = "warning"

    async def async_create_issue(*args, **kwargs):  # pragma: no cover - stub
        return None

    issue_registry.IssueSeverity = IssueSeverity  # type: ignore[attr-defined]
    issue_registry.async_create_issue = async_create_issue  # type: ignore[attr-defined]
    helpers.issue_registry = issue_registry  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.issue_registry"] = issue_registry

    restore_state = ModuleType("homeassistant.helpers.restore_state")

    class RestoreEntity:  # pragma: no cover - stub
        pass

    class RestoreStateData:  # pragma: no cover - stub
        def __init__(self, state=None, attributes=None):
            self.state = state
            self.attributes = attributes or {}

    restore_state.RestoreEntity = RestoreEntity  # type: ignore[attr-defined]
    restore_state.RestoreStateData = RestoreStateData  # type: ignore[attr-defined]
    helpers.restore_state = restore_state  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.restore_state"] = restore_state

    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    helpers.update_coordinator = update_coordinator  # type: ignore[attr-defined]
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    class UpdateFailed(Exception):
        pass

    from typing import Generic, TypeVar

    _T = TypeVar("_T")

    class DataUpdateCoordinator(Generic[_T]):
        def __init__(
            self,
            hass=None,
            logger=None,
            name=None,
            update_interval=None,
            always_update=False,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.always_update = always_update
            self.data = None

        async def async_config_entry_first_refresh(self):  # pragma: no cover - stub
            await self._async_update_data()

        async def _async_update_data(self):  # pragma: no cover - stub
            return None

        async def async_request_refresh(self):  # pragma: no cover - stub
            await self._async_update_data()

        def async_set_updated_data(self, data):  # pragma: no cover - stub
            self.data = data

    _C = TypeVar("_C")

    class CoordinatorEntity(Generic[_C]):
        def __init__(self, coordinator: _C) -> None:
            self.coordinator = coordinator

    update_coordinator.UpdateFailed = UpdateFailed  # type: ignore[attr-defined]
    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator  # type: ignore[attr-defined]
    update_coordinator.CoordinatorEntity = CoordinatorEntity  # type: ignore[attr-defined]
    # Alias für CoordinatorUpdateFailed, um alte Importe zu simulieren

try:
    from homeassistant.helpers.update_coordinator import UpdateFailed
    # Nur wenn Home Assistant schon geladen ist, Alias setzen
    import homeassistant.helpers.update_coordinator as update_coordinator
    update_coordinator.CoordinatorUpdateFailed = UpdateFailed  # Typ: ignore
except ImportError:
    # Falls Home Assistant noch nicht installiert ist, ist es egal
    pass


# Ensure ``homeassistant.util`` is loaded or provide minimal implementation
try:  # pragma: no cover - Home Assistant provides util module
    import homeassistant.util as util  # type: ignore[assignment]

    ha.util = util  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - create minimal util package
    util = ModuleType("homeassistant.util")
    util.__path__ = []
    ha.util = util  # type: ignore[attr-defined]
    sys.modules["homeassistant.util"] = util

    util_logging = ModuleType("homeassistant.util.logging")

    def log_exception(format_err, *args, **kwargs):  # pragma: no cover - stub
        return None

    util_logging.log_exception = log_exception  # type: ignore[attr-defined]
    util.logging = util_logging  # type: ignore[attr-defined]
    sys.modules["homeassistant.util.logging"] = util_logging

    def slugify(value):  # pragma: no cover - simple slugifier
        return str(value).lower().replace(" ", "_")

    util.slugify = slugify  # type: ignore[attr-defined]

    location = ModuleType("homeassistant.util.location")

    def distance(*args, **kwargs):  # pragma: no cover - stub
        return 0.0

    location.distance = distance  # type: ignore[attr-defined]
    util.location = location  # type: ignore[attr-defined]
    sys.modules["homeassistant.util.location"] = location

# Provide logging submodule if missing
try:  # pragma: no cover - Home Assistant provides logging helper
    importlib.import_module("homeassistant.util.logging")
except Exception:  # pragma: no cover - create minimal version
    util_logging = ModuleType("homeassistant.util.logging")

    def log_exception(format_err, *args, **kwargs):  # pragma: no cover - stub
        return None

    util_logging.log_exception = log_exception  # type: ignore[attr-defined]
    util.logging = util_logging  # type: ignore[attr-defined]
    sys.modules["homeassistant.util.logging"] = util_logging

# Provide datetime helper submodule if missing
try:  # pragma: no cover - Home Assistant provides dt helper
    importlib.import_module("homeassistant.util.dt")
except Exception:  # pragma: no cover - create minimal version
    util_dt = ModuleType("homeassistant.util.dt")

    UTC = UTC

    def now() -> datetime:  # pragma: no cover - stub
        return datetime.now(UTC)

    def utcnow() -> datetime:  # pragma: no cover - stub
        return datetime.now(UTC)

    def as_local(dt_obj: datetime) -> datetime:  # pragma: no cover - stub
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj.replace(tzinfo=UTC)
        return dt_obj.astimezone()

    def as_utc(dt_obj: datetime) -> datetime:  # pragma: no cover - stub
        if dt_obj.tzinfo is None:
            return dt_obj.replace(tzinfo=UTC)
        return dt_obj.astimezone(UTC)

    def parse_datetime(value: str) -> datetime:  # pragma: no cover - stub
        return datetime.fromisoformat(value)

    def parse_date(value: str):  # pragma: no cover - stub
        return datetime.fromisoformat(value).date()

    util_dt.now = now  # type: ignore[attr-defined]
    util_dt.utcnow = utcnow  # type: ignore[attr-defined]
    util_dt.UTC = UTC  # type: ignore[attr-defined]
    util_dt.as_local = as_local  # type: ignore[attr-defined]
    util_dt.as_utc = as_utc  # type: ignore[attr-defined]
    util_dt.parse_datetime = parse_datetime  # type: ignore[attr-defined]
    util_dt.parse_date = parse_date  # type: ignore[attr-defined]

    util.dt = util_dt  # type: ignore[attr-defined]
    sys.modules["homeassistant.util.dt"] = util_dt

if not hasattr(entity, "EntityCategory"):

    class EntityCategory(StrEnum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    entity.EntityCategory = EntityCategory  # type: ignore[attr-defined]

if not hasattr(device_registry, "DeviceInfo"):

    class DeviceInfo(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    device_registry.DeviceInfo = DeviceInfo  # type: ignore[attr-defined]

# Provide minimal config entry and core stubs when Home Assistant isn't installed
try:  # pragma: no cover - Home Assistant provides config entries
    from homeassistant.config_entries import ConfigEntry  # type: ignore
except Exception:  # pragma: no cover - create minimal config_entries module
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntryState(StrEnum):
        NOT_LOADED = "not_loaded"
        LOADED = "loaded"

    class ConfigEntry:  # pragma: no cover - test stub
        def __init__(
            self,
            *,
            version: int = 1,
            minor_version: int = 1,
            domain: str | None = None,
            title: str | None = None,
            data: dict | None = None,
            options: dict | None = None,
            entry_id: str | None = None,
            source: str | None = None,
            unique_id: str | None = None,
            discovery_keys=None,
            subentries_data=None,
        ) -> None:
            self.version = version
            self.minor_version = minor_version
            self.domain = domain
            self.title = title
            self.data = data or {}
            self.options = options or {}
            self.entry_id = entry_id or ""
            self.source = source or "user"
            self.unique_id = unique_id
            self.discovery_keys = discovery_keys
            self.subentries_data = subentries_data or []
            self.state = ConfigEntryState.NOT_LOADED

    class ConfigFlow:  # pragma: no cover - test stub
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class OptionsFlow:  # pragma: no cover - test stub
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    ConfigFlowResult = dict

    config_entries.ConfigEntry = ConfigEntry  # type: ignore[attr-defined]
    config_entries.ConfigEntryState = ConfigEntryState  # type: ignore[attr-defined]
    config_entries.ConfigFlow = ConfigFlow  # type: ignore[attr-defined]
    config_entries.OptionsFlow = OptionsFlow  # type: ignore[attr-defined]
    config_entries.ConfigFlowResult = ConfigFlowResult  # type: ignore[attr-defined]
    config_entries.HANDLERS = {}
    ha.config_entries = config_entries  # type: ignore[attr-defined]
    sys.modules["homeassistant.config_entries"] = config_entries

    data_entry_flow = ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.FlowResultType = StrEnum(
        "FlowResultType",
        {"FORM": "form", "CREATE_ENTRY": "create_entry", "ABORT": "abort"},
    )
    data_entry_flow.FlowResult = dict
    sys.modules["homeassistant.data_entry_flow"] = data_entry_flow

try:  # pragma: no cover - Home Assistant provides core module
    from homeassistant.core import HomeAssistant  # type: ignore
except Exception:  # pragma: no cover - create minimal core module
    core = ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - test stub
        def __init__(self) -> None:
            self.data = {}
            self.services = SimpleNamespace(async_services=None)
            self.config_entries = SimpleNamespace(
                flow=SimpleNamespace(async_init=lambda *a, **k: None)
            )

    def callback(func):  # pragma: no cover - stub decorator
        return func

    class ServiceCall:  # pragma: no cover - stub
        def __init__(self, data=None):
            self.data = data or {}

    core.HomeAssistant = HomeAssistant  # type: ignore[attr-defined]
    core.callback = callback  # type: ignore[attr-defined]
    core.ServiceCall = ServiceCall  # type: ignore[attr-defined]
    sys.modules["homeassistant.core"] = core
    ha.core = core  # type: ignore[attr-defined]

try:  # pragma: no cover - Home Assistant provides exceptions
    from homeassistant.exceptions import HomeAssistantError  # type: ignore
except Exception:  # pragma: no cover - create minimal exceptions module
    exceptions = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ConfigEntryNotReady(HomeAssistantError):
        pass

    class ServiceValidationError(HomeAssistantError):
        pass

    class ServiceNotFound(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = HomeAssistantError  # type: ignore[attr-defined]
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady  # type: ignore[attr-defined]
    exceptions.ServiceValidationError = ServiceValidationError  # type: ignore[attr-defined]
    exceptions.ServiceNotFound = ServiceNotFound  # type: ignore[attr-defined]
    sys.modules["homeassistant.exceptions"] = exceptions

try:  # pragma: no cover - Home Assistant provides const module
    import homeassistant.const as const  # type: ignore
except Exception:  # pragma: no cover - create minimal const module
    const = ModuleType("homeassistant.const")

    class Platform(StrEnum):  # pragma: no cover - test stub
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

    const.Platform = Platform  # type: ignore[attr-defined]
    const.STATE_UNKNOWN = "unknown"  # type: ignore[attr-defined]
    const.STATE_UNAVAILABLE = "unavailable"  # type: ignore[attr-defined]
    const.PERCENTAGE = "%"  # type: ignore[attr-defined]
    const.CONF_NAME = "name"  # type: ignore[attr-defined]
    const.ATTR_BATTERY_LEVEL = "battery_level"  # type: ignore[attr-defined]
    const.ATTR_GPS_ACCURACY = "gps_accuracy"  # type: ignore[attr-defined]
    const.ATTR_LATITUDE = "latitude"  # type: ignore[attr-defined]
    const.ATTR_LONGITUDE = "longitude"  # type: ignore[attr-defined]
    const.STATE_HOME = "home"  # type: ignore[attr-defined]
    const.UnitOfLength = StrEnum("UnitOfLength", {"METERS": "m", "KILOMETERS": "km"})  # type: ignore[attr-defined]
    const.STATE_NOT_HOME = "not_home"  # type: ignore[attr-defined]
    const.UnitOfMass = StrEnum("UnitOfMass", {"GRAMS": "g", "KILOGRAMS": "kg"})  # type: ignore[attr-defined]
    const.UnitOfSpeed = StrEnum("UnitOfSpeed", {"METERS_PER_SECOND": "m/s"})  # type: ignore[attr-defined]
    const.UnitOfTime = StrEnum("UnitOfTime", {"SECONDS": "s"})  # type: ignore[attr-defined]
    sys.modules["homeassistant.const"] = const

# ---------------------------------------------------------------------------
# Component stubs
# ---------------------------------------------------------------------------
components = ModuleType("homeassistant.components")
ha.components = components  # type: ignore[attr-defined]
sys.modules["homeassistant.components"] = components

for comp in ["bluetooth", "dhcp", "usb", "zeroconf"]:
    mod = ModuleType(f"homeassistant.components.{comp}")
    setattr(components, comp, mod)  # type: ignore[attr-defined]
    sys.modules[f"homeassistant.components.{comp}"] = mod


def _register_component(name, **attrs):  # pragma: no cover - helper
    module = ModuleType(f"homeassistant.components.{name}")
    for key, value in attrs.items():
        setattr(module, key, value)
    module.DOMAIN = name  # type: ignore[attr-defined]
    sys.modules[f"homeassistant.components.{name}"] = module
    setattr(components, name, module)


class _BaseEntity:  # pragma: no cover - base stub
    pass


class _StrEnum(StrEnum):  # pragma: no cover - simple StrEnum base
    pass


_register_component(
    "api",
)

_register_component(
    "button",
    ButtonDeviceClass=_StrEnum("ButtonDeviceClass", {"RESTART": "restart"}),
    ButtonEntity=_BaseEntity,
)
_register_component("date", DateEntity=_BaseEntity)
_register_component("datetime", DateTimeEntity=_BaseEntity)
_register_component(
    "binary_sensor",
    BinarySensorDeviceClass=_StrEnum(
        "BinarySensorDeviceClass",
        {
            "BATTERY": "battery",
            "CONNECTIVITY": "connectivity",
            "PROBLEM": "problem",
            "RUNNING": "running",
            "PRESENCE": "presence",
            "SAFETY": "safety",
            "MOTION": "motion",
        },
    ),
    BinarySensorEntity=_BaseEntity,
)
_register_component(
    "device_tracker",
    SourceType=_StrEnum("SourceType", {"GPS": "gps"}),
    TrackerEntity=_BaseEntity,
)
device_tracker_pkg = components.device_tracker  # type: ignore[attr-defined]
config_entry_mod = ModuleType("homeassistant.components.device_tracker.config_entry")
config_entry_mod.TrackerEntity = _BaseEntity  # type: ignore[attr-defined]
sys.modules["homeassistant.components.device_tracker.config_entry"] = config_entry_mod
device_tracker_pkg.config_entry = config_entry_mod  # type: ignore[attr-defined]
_register_component(
    "number",
    NumberDeviceClass=_StrEnum("NumberDeviceClass", {"NONE": "none"}),
    NumberEntity=_BaseEntity,
    NumberMode=_StrEnum(
        "NumberMode", {"AUTO": "auto", "BOX": "box", "SLIDER": "slider"}
    ),
)
_register_component("select", SelectEntity=_BaseEntity)
_register_component(
    "switch",
    SwitchDeviceClass=_StrEnum("SwitchDeviceClass", {"SWITCH": "switch"}),
    SwitchEntity=_BaseEntity,
)
_register_component(
    "sensor",
    SensorDeviceClass=_StrEnum("SensorDeviceClass", {"TEMPERATURE": "temperature"}),
    SensorStateClass=_StrEnum("SensorStateClass", {"MEASUREMENT": "measurement"}),
    SensorEntity=_BaseEntity,
)
_register_component(
    "text",
    TextEntity=_BaseEntity,
    TextMode=_StrEnum("TextMode", {"TEXT": "text"}),
)

_register_component(
    "repairs",
    RepairsFlow=_BaseEntity,
)

system_health = ModuleType("homeassistant.components.system_health")


async def async_check_can_reach_url(*args, **kwargs):
    return True


system_health.async_check_can_reach_url = async_check_can_reach_url  # type: ignore[attr-defined]
sys.modules["homeassistant.components.system_health"] = system_health
components.system_health = system_health  # type: ignore[attr-defined]

persistent_notification = ModuleType("homeassistant.components.persistent_notification")


async def async_create(*args, **kwargs):
    return None


async def async_dismiss(*args, **kwargs):
    return None


persistent_notification.async_create = async_create  # type: ignore[attr-defined]
persistent_notification.async_dismiss = async_dismiss  # type: ignore[attr-defined]
sys.modules["homeassistant.components.persistent_notification"] = (
    persistent_notification
)
components.persistent_notification = persistent_notification  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Event loop compatibility
# ---------------------------------------------------------------------------
#
# Some of the tests exercise Home Assistant using ``pytest-anyio`` which
# creates a new running loop per test.  Home Assistant's default
# ``async_add_executor_job`` implementation schedules work on ``self.loop``
# which was created when the ``HomeAssistant`` instance was initialised and can
# therefore differ from the currently running loop.  Awaiting the resulting
# future from a different loop raises ``RuntimeError: Task ... got Future ...
# attached to a different loop``.  To keep the tests lightweight we replace the
# method with a version that always targets the running loop.
with suppress(
    Exception
):  # pragma: no cover - ensure ``HomeAssistant.config`` exists for mocks
    from homeassistant.core import HomeAssistant

    if not hasattr(HomeAssistant, "config"):
        HomeAssistant.config = None  # type: ignore[assignment]

with suppress(Exception):  # pragma: no cover - patch executor job helper when possible
    import asyncio

    from homeassistant.core import HomeAssistant

    if not hasattr(HomeAssistant, "_pawcontrol_executor_patch"):

        async def async_add_executor_job(self, func, *args):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func, *args)

        HomeAssistant.async_add_executor_job = async_add_executor_job  # type: ignore[assignment]
        HomeAssistant._pawcontrol_executor_patch = True  # type: ignore[attr-defined]


# Register the config flow class directly with Home Assistant's flow handler
# registry to avoid expensive integration discovery during tests.  This keeps
# ``hass.config_entries.flow.async_init("pawcontrol")`` working even when the
# loader cannot resolve the custom component from the filesystem in the minimal
# test environment.
with suppress(
    Exception
):  # pragma: no cover - import may fail when Home Assistant is absent
    from custom_components import pawcontrol as paw_module
    from custom_components.pawcontrol import config_flow as paw_config_flow
    from homeassistant import config_entries

    if "pawcontrol" not in config_entries.HANDLERS:
        config_entries.HANDLERS["pawcontrol"] = paw_config_flow.PawControlConfigFlow

    # Expose the integration as a built-in component so the loader can
    # resolve it even when custom component paths aren't configured.
    sys.modules.setdefault("homeassistant.components.pawcontrol", paw_module)

# Ensure the repository's custom_components path is available when Home
# Assistant mounts the config dir during integration setup. This allows the
# loader to resolve the Paw Control integration even when the config directory
# used for tests doesn't contain a copy of the custom component.
with suppress(Exception):  # pragma: no cover - Home Assistant may not be installed
    from pathlib import Path

    import homeassistant.loader as loader

    _orig_mount = loader._async_mount_config_dir
    repo_root = Path(__file__).resolve().parent

    def _patched_mount_config_dir(hass):  # pragma: no cover - test helper
        _orig_mount(hass)
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
            sys.path_importer_cache.pop(str(repo_root), None)

    loader._async_mount_config_dir = _patched_mount_config_dir
