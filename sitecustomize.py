"""Test environment compatibility helpers.

This module is loaded automatically by Python before any other imports.
It ensures that optional Home Assistant helpers exist when the test
environment provides a minimal stub of the framework.
"""

from __future__ import annotations

import os
import sys
from enum import StrEnum
from types import ModuleType, SimpleNamespace
from typing import Callable

# Prevent external pytest plugins from auto-loading during test collection.
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

# Create minimal Home Assistant stubs
try:  # pragma: no cover — Home Assistant available
    ha = sys.modules["homeassistant"]
except Exception:
    ha = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    ha.__path__ = []
    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    ha.helpers = helpers
    sys.modules["homeassistant.helpers"] = helpers

    # Stubs for entity and device registry
    entity = ModuleType("homeassistant.helpers.entity")
    device_registry = ModuleType("homeassistant.helpers.device_registry")
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    sys.modules["homeassistant.helpers.entity"] = entity
    sys.modules["homeassistant.helpers.device_registry"] = device_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry
    helpers.entity = entity
    helpers.device_registry = device_registry
    helpers.entity_registry = entity_registry

    class DeviceRegistry:  # pragma: no cover
        pass

    device_registry.DeviceRegistry = DeviceRegistry

    class EntityRegistry:  # pragma: no cover
        pass

    entity_registry.EntityRegistry = EntityRegistry

# Stub for config validation
config_validation = ModuleType("homeassistant.helpers.config_validation")
helpers.config_validation = config_validation
sys.modules["homeassistant.helpers.config_validation"] = config_validation


def ensure_list(value):  # pragma: no cover
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def config_entry_only_config_schema(domain):  # pragma: no cover
    def schema(config):
        return config

    return schema


config_validation.ensure_list = ensure_list
config_validation.config_entry_only_config_schema = config_entry_only_config_schema
config_validation.string = str
config_validation.boolean = bool

# Stub for typing
helpers_typing = ModuleType("homeassistant.helpers.typing")
helpers_typing.ConfigType = dict
helpers.typing = helpers_typing
sys.modules["homeassistant.helpers.typing"] = helpers_typing

# Stub for selector
selector = ModuleType("homeassistant.helpers.selector")
helpers.selector = selector
sys.modules["homeassistant.helpers.selector"] = selector


class BooleanSelector:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass


class NumberSelector:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass


class NumberSelectorMode(StrEnum):  # pragma: no cover
    BOX = "box"


class NumberSelectorConfig:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass


class SelectSelector:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass


class SelectSelectorMode(StrEnum):  # pragma: no cover
    DROPDOWN = "dropdown"


class SelectSelectorConfig:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        pass


selector.BooleanSelector = BooleanSelector
selector.NumberSelector = NumberSelector
selector.NumberSelectorMode = NumberSelectorMode
selector.NumberSelectorConfig = NumberSelectorConfig
selector.SelectSelector = SelectSelector
selector.SelectSelectorMode = SelectSelectorMode
selector.SelectSelectorConfig = SelectSelectorConfig


def _selector(cfg):  # pragma: no cover
    return cfg


selector.selector = _selector

# Stub for entity_platform
entity_platform = ModuleType("homeassistant.helpers.entity_platform")
helpers.entity_platform = entity_platform
sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
entity_platform.AddEntitiesCallback = Callable[..., None]

# Stub for storage
storage = ModuleType("homeassistant.helpers.storage")


class Store:  # pragma: no cover
    def __init__(self, *args, **kwargs):
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


storage.Store = Store
helpers.storage = storage
sys.modules["homeassistant.helpers.storage"] = storage

# Stub for event
event = ModuleType("homeassistant.helpers.event")


async def async_track_time_interval(*args, **kwargs):  # pragma: no cover
    return None


async def async_track_time(*args, **kwargs):  # pragma: no cover
    return None


event.async_track_time_interval = async_track_time_interval
event.async_track_time = async_track_time
helpers.event = event
sys.modules["homeassistant.helpers.event"] = event

# Stub for setup
setup = ModuleType("homeassistant.setup")


async def async_setup_component(*args, **kwargs):  # pragma: no cover
    return True


setup.async_setup_component = async_setup_component
sys.modules["homeassistant.setup"] = setup

# Stub for issue_registry
issue_registry = ModuleType("homeassistant.helpers.issue_registry")


class IssueSeverity(StrEnum):  # pragma: no cover
    WARNING = "warning"


async def async_create_issue(*args, **kwargs):  # pragma: no cover
    return None


issue_registry.IssueSeverity = IssueSeverity
issue_registry.async_create_issue = async_create_issue
helpers.issue_registry = issue_registry
sys.modules["homeassistant.helpers.issue_registry"] = issue_registry

# Stub for restore_state
restore_state = ModuleType("homeassistant.helpers.restore_state")


class RestoreEntity:  # pragma: no cover
    pass


class RestoreStateData:  # pragma: no cover
    def __init__(self, state=None, attributes=None):
        self.state = state
        self.attributes = attributes or {}


restore_state.RestoreEntity = RestoreEntity
restore_state.RestoreStateData = RestoreStateData
helpers.restore_state = restore_state
sys.modules["homeassistant.helpers.restore_state"] = restore_state

# Stub for update_coordinator
update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
helpers.update_coordinator = update_coordinator
sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator


class UpdateFailed(Exception):
    pass


update_coordinator.UpdateFailed = UpdateFailed

# **Alias hinzufügen für alte Importe**
update_coordinator.CoordinatorUpdateFailed = UpdateFailed  # noqa: type: ignore[attr-defined]

# Stub for core HomeAssistant
core = ModuleType("homeassistant.core")


class HomeAssistant:
    def __init__(self, config_dir: str | None = None) -> None:
        self.config = {}
        self.services = SimpleNamespace(async_services=None)
        self.config_entries = SimpleNamespace(
            flow=SimpleNamespace(async_init=lambda *a, **k: None)
        )

    @staticmethod
    def callback(func):
        return func

    class ServiceCall:
        def __init__(self, data=None):
            self.data = data or {}


core.HomeAssistant = HomeAssistant
sys.modules["homeassistant.core"] = core
ha.core = core

# Stub for exceptions
exceptions = ModuleType("homeassistant.exceptions")


class HomeAssistantError(Exception):
    pass


class ConfigEntryNotReady(HomeAssistantError):
    pass


class ServiceValidationError(HomeAssistantError):
    pass


class ServiceNotFound(HomeAssistantError):
    pass


exceptions.HomeAssistantError = HomeAssistantError
exceptions.ConfigEntryNotReady = ConfigEntryNotReady
exceptions.ServiceValidationError = ServiceValidationError
exceptions.ServiceNotFound = ServiceNotFound
sys.modules["homeassistant.exceptions"] = exceptions

# Stub for const
const = ModuleType("homeassistant.const")


class Platform(StrEnum):  # pragma: no cover
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


const.Platform = Platform
const.STATE_UNKNOWN = "unknown"
const.STATE_UNAVAILABLE = "unavailable"
const.PERCENTAGE = "%"
const.CONF_NAME = "name"
const.STATE_ONLINE = "online"
const.ATTR_BATTERY_LEVEL = "battery_level"
const.ATTR_GPS_ACCURACY = "gps_accuracy"
const.ATTR_LATITUDE = "latitude"
const.ATTR_LONGITUDE = "longitude"
const.STATE_HOME = "home"
const.UnitOfLength = StrEnum("UnitOfLength", {"METERS": "m", "KILOMETERS": "km"})
const.STATE_NOT_HOME = "not_home"
const.UnitOfMass = StrEnum("UnitOfMass", {"GRAMS": "g", "KILOGRAMS": "kg"})
const.UnitOfSpeed = StrEnum("UnitOfSpeed", {"METERS_PER_SECOND": "m/s"})
const.UnitOfTime = StrEnum("UnitOfTime", {"SECONDS": "s"})
sys.modules["homeassistant.const"] = const
ha.const = const
