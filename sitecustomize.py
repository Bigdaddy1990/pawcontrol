"""Minimal test scaffolding for Home Assistant components.

If the real Home Assistant package isn't available, this module
creates lightweight stand‑ins for the parts of the API used in tests.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from types import ModuleType
from types import SimpleNamespace
from typing import Any
from typing import TypeVar

# Prevent unexpected plugins from loading during test collection
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

T = TypeVar("T")

try:  # pragma: no cover - prefer real Home Assistant when present
    import homeassistant  # noqa: F401

    # Ensure ConfigEntry is available for legacy imports
    try:  # pragma: no cover - best effort
        from homeassistant.helpers import entity as ha_entity

        if not hasattr(ha_entity, "ConfigEntry"):
            ha_entity.ConfigEntry = object  # type: ignore[attr-defined]
    except Exception:
        pass
except Exception:  # pragma: no cover - fall back to minimal stubs
    ha = sys.modules.setdefault("homeassistant", ModuleType("homeassistant"))
    ha.__path__ = []

    helpers = ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    ha.helpers = helpers
    sys.modules["homeassistant.helpers"] = helpers

    components = ModuleType("homeassistant.components")
    components.__path__ = []
    ha.components = components
    sys.modules["homeassistant.components"] = components

    event = ModuleType("homeassistant.helpers.event")
    helpers.event = event
    sys.modules["homeassistant.helpers.event"] = event

    def async_track_time_change(hass, action, *args, **kwargs):  # pragma: no cover
        action(datetime.now())
        return lambda: None

    event.async_track_time_change = async_track_time_change

    persistent_notification = ModuleType(
        "homeassistant.components.persistent_notification"
    )

    async def async_create(
        hass, message, title=None, notification_id=None
    ):  # pragma: no cover
        return None

    async def async_dismiss(hass, notification_id):  # pragma: no cover
        return None

    persistent_notification.async_create = async_create
    persistent_notification.async_dismiss = async_dismiss
    components.persistent_notification = persistent_notification
    sys.modules["homeassistant.components.persistent_notification"] = (
        persistent_notification
    )

    binary_sensor = ModuleType("homeassistant.components.binary_sensor")
    components.binary_sensor = binary_sensor
    sys.modules["homeassistant.components.binary_sensor"] = binary_sensor

    # ---- const -------------------------------------------------------------
    class _ConstModule(ModuleType):
        def __getattr__(self, name: str) -> str:  # pragma: no cover
            return name.lower()

    const = _ConstModule("homeassistant.const")
    ha.const = const
    sys.modules["homeassistant.const"] = const

    class Platform(StrEnum):  # pragma: no cover
        SENSOR = "sensor"
        BUTTON = "button"
        BINARY_SENSOR = "binary_sensor"
        DATETIME = "datetime"
        TEXT = "text"
        DEVICE_TRACKER = "device_tracker"
        NUMBER = "number"
        SELECT = "select"
        SWITCH = "switch"
        DATE = "date"

    const.Platform = Platform

    exceptions = ModuleType("homeassistant.exceptions")

    class HomeAssistantError(Exception):  # pragma: no cover - simple base
        pass

    class ConfigEntryNotReady(HomeAssistantError):  # pragma: no cover
        pass

    class ServiceValidationError(HomeAssistantError):  # pragma: no cover
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ConfigEntryNotReady = ConfigEntryNotReady
    exceptions.ServiceValidationError = ServiceValidationError
    ha.exceptions = exceptions
    sys.modules["homeassistant.exceptions"] = exceptions

    util = ModuleType("homeassistant.util")
    ha.util = util
    sys.modules["homeassistant.util"] = util

    dt_util = ModuleType("homeassistant.util.dt")
    util.dt = dt_util
    sys.modules["homeassistant.util.dt"] = dt_util

    def now(tz=None):  # pragma: no cover
        return datetime.now(tz)

    dt_util.utcnow = datetime.utcnow
    dt_util.now = now

    # ---- config entries ---------------------------------------------------
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigEntry:  # pragma: no cover - simple placeholder
        def __init__(self, data: dict | None = None, options: dict | None = None):
            self.data = data or {}
            self.options = options or {}
            self.entry_id = "test"

    class ConfigFlow:  # pragma: no cover - simple placeholder
        def __init_subclass__(cls, *, domain: str | None = None) -> None:
            cls.domain = domain

    class OptionsFlow:  # pragma: no cover - simple placeholder
        pass

    ConfigFlowResult = dict

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigFlowResult = ConfigFlowResult
    ha.config_entries = config_entries
    sys.modules["homeassistant.config_entries"] = config_entries

    # ---- config validation -------------------------------------------------
    config_validation = ModuleType("homeassistant.helpers.config_validation")
    helpers.config_validation = config_validation
    sys.modules["homeassistant.helpers.config_validation"] = config_validation

    def ensure_list(value):  # pragma: no cover
        return [] if value is None else (value if isinstance(value, list) else [value])

    def config_entry_only_config_schema(domain):  # pragma: no cover
        def schema(config):
            return config

        return schema

    config_validation.ensure_list = ensure_list
    config_validation.config_entry_only_config_schema = config_entry_only_config_schema
    config_validation.string = str
    config_validation.boolean = bool

    # ---- typing ------------------------------------------------------------
    helpers_typing = ModuleType("homeassistant.helpers.typing")
    helpers_typing.ConfigType = dict
    helpers.typing = helpers_typing
    sys.modules["homeassistant.helpers.typing"] = helpers_typing

    # ---- selector ----------------------------------------------------------
    selector = ModuleType("homeassistant.helpers.selector")
    helpers.selector = selector
    sys.modules["homeassistant.helpers.selector"] = selector

    class BooleanSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class NumberSelectorMode(StrEnum):  # pragma: no cover
        BOX = "box"

    class NumberSelectorConfig:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelector:  # pragma: no cover - simple placeholder
        def __init__(self, *args, **kwargs):
            pass

    class SelectSelectorMode(StrEnum):  # pragma: no cover
        DROPDOWN = "dropdown"

    class SelectSelectorConfig:  # pragma: no cover
        def __init__(self, *args, **kwargs):
            pass

    def _selector(cfg):  # pragma: no cover
        return cfg

    selector.BooleanSelector = BooleanSelector
    selector.NumberSelector = NumberSelector
    selector.NumberSelectorMode = NumberSelectorMode
    selector.NumberSelectorConfig = NumberSelectorConfig
    selector.SelectSelector = SelectSelector
    selector.SelectSelectorMode = SelectSelectorMode
    selector.SelectSelectorConfig = SelectSelectorConfig
    selector.selector = _selector

    entity_helper = ModuleType("homeassistant.helpers.entity")

    class Entity:  # pragma: no cover - simple placeholder
        pass

    entity_helper.Entity = Entity
    helpers.entity = entity_helper
    sys.modules["homeassistant.helpers.entity"] = entity_helper

    # ---- entity platform ---------------------------------------------------
    entity_platform = ModuleType("homeassistant.helpers.entity_platform")
    helpers.entity_platform = entity_platform
    sys.modules["homeassistant.helpers.entity_platform"] = entity_platform
    entity_platform.AddEntitiesCallback = Callable[..., None]

    # ---- entity registry ---------------------------------------------------
    entity_registry = ModuleType("homeassistant.helpers.entity_registry")

    class EntityRegistry:  # pragma: no cover - simple placeholder
        pass

    entity_registry.EntityRegistry = EntityRegistry
    helpers.entity_registry = entity_registry
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry

    # ---- storage -----------------------------------------------------------
    storage = ModuleType("homeassistant.helpers.storage")
    helpers.storage = storage
    sys.modules["homeassistant.helpers.storage"] = storage

    class Store:  # pragma: no cover - minimal in-memory store
        def __init__(self, *args, **kwargs):
            self.data = None

        async def async_load(self):
            return self.data

        async def async_save(self, data):
            self.data = data

    storage.Store = Store

    # ---- update coordinator ------------------------------------------------
    update_coordinator = ModuleType("homeassistant.helpers.update_coordinator")
    helpers.update_coordinator = update_coordinator
    sys.modules["homeassistant.helpers.update_coordinator"] = update_coordinator

    class UpdateFailed(Exception):  # pragma: no cover - simple placeholder
        pass

    update_coordinator.UpdateFailed = UpdateFailed
    update_coordinator.CoordinatorUpdateFailed = UpdateFailed

    class DataUpdateCoordinator[T]:  # pragma: no cover - minimal stub
        def __init__(
            self,
            hass: HomeAssistant,
            logger: Any,
            name: str,
            update_method: Callable[[], Awaitable[T]] | None = None,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_method = update_method
            self.last_update_success = True
            self.data: T | None = None
            self._listeners: list[Callable[[], None]] = []

        async def async_refresh(self) -> None:
            if self.update_method is None:
                return
            try:
                self.data = await self.update_method()
                self.last_update_success = True
                for listener in list(self._listeners):
                    listener()
            except Exception as err:  # pragma: no cover - minimal error handling
                self.last_update_success = False
                raise UpdateFailed(
                    f"Error fetching {self.name} data: {err}") from err

        def async_add_listener(
            self, listener: Callable[[], None]
        ) -> Callable[[], None]:
            self._listeners.append(listener)

            def remove() -> None:
                self._listeners.remove(listener)

            return remove

        def async_set_updated_data(self, data: T) -> None:
            self.data = data
            for listener in list(self._listeners):
                listener()

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator

    # ---- core --------------------------------------------------------------
    core = ModuleType("homeassistant.core")

    class HomeAssistant:  # pragma: no cover - minimal stub
        def __init__(self) -> None:
            self.config: dict[str, object] = {}
            self.services = SimpleNamespace(async_services=None)

        @staticmethod
        def callback(func: Callable) -> Callable:  # pragma: no cover
            return func

    class ServiceCall:  # pragma: no cover - simple placeholder
        def __init__(self, data: dict | None = None) -> None:
            self.data = data or {}

    def callback(func: Callable) -> Callable:  # pragma: no cover
        return func

    core.HomeAssistant = HomeAssistant
    core.ServiceCall = ServiceCall
    core.callback = callback
    ha.core = core
    sys.modules["homeassistant.core"] = core
