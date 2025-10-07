"""Unit tests for :mod:`custom_components.pawcontrol.entity_factory`.

These tests provide lightweight coverage for the profile guard rails without
requiring the full Home Assistant runtime.  The integration normally imports
``homeassistant.const.Platform`` and ``homeassistant.helpers.entity.Entity`` on
module import which are not available in the execution environment.  We stub
the minimal interfaces that the entity factory relies on so the module can be
imported and exercised directly.
"""

from __future__ import annotations

import pathlib
import sys
import types
from collections.abc import Callable
from datetime import UTC, datetime, timezone
from enum import Enum, StrEnum


class _Platform(StrEnum):
    """StrEnum stub replicating the Home Assistant ``Platform`` enum."""

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


class _PlatformStringAlias(Enum):
    """Enum stub exposing string values for compatibility testing."""

    SENSOR = "sensor"


class _PlatformEnumAlias(Enum):
    """Enum stub whose values point to another enum."""

    SENSOR = _Platform.SENSOR


class _NestedPlatformAlias(Enum):
    """Enum stub with nested enum indirection for platform aliases."""

    SENSOR = _PlatformEnumAlias.SENSOR


def _install_homeassistant_stubs() -> None:
    """Install minimal ``homeassistant`` modules needed by the entity factory."""

    if "homeassistant" in sys.modules:
        # The real package (or another stub) is already available.
        return

    homeassistant = types.ModuleType("homeassistant")
    const_module = types.ModuleType("homeassistant.const")
    core_module = types.ModuleType("homeassistant.core")
    exceptions_module = types.ModuleType("homeassistant.exceptions")
    helpers_module = types.ModuleType("homeassistant.helpers")
    helpers_module.__path__ = []  # mark as package
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
    storage_module = types.ModuleType("homeassistant.helpers.storage")
    config_entries_module = types.ModuleType("homeassistant.config_entries")
    util_module = types.ModuleType("homeassistant.util")
    util_module.__path__ = []
    dt_util_module = types.ModuleType("homeassistant.util.dt")
    selector_module = types.ModuleType("homeassistant.helpers.selector")

    const_module.Platform = _Platform
    const_module.STATE_ON = "on"
    const_module.STATE_OFF = "off"
    const_module.STATE_UNKNOWN = "unknown"
    const_module.STATE_HOME = "home"
    const_module.STATE_NOT_HOME = "not_home"

    class _HomeAssistant:  # pragma: no cover - behaviour is not exercised directly
        """Placeholder for :class:`homeassistant.core.HomeAssistant`."""

        data: dict[str, object]

        def __init__(self) -> None:
            self.data = {}

    core_module.HomeAssistant = _HomeAssistant

    class Event:  # pragma: no cover - helper stub
        def __init__(
            self, event_type: str, data: dict[str, object] | None = None
        ) -> None:
            self.event_type = event_type
            self.data = data or {}

    core_module.Event = Event
    core_module.EventStateChangedData = dict[str, object]

    class State:  # pragma: no cover - helper stub
        def __init__(
            self,
            entity_id: str,
            state: str,
            attributes: dict[str, object] | None = None,
        ) -> None:
            self.entity_id = entity_id
            self.state = state
            self.attributes = attributes or {}

    core_module.State = State

    def _callback(func):  # pragma: no cover - helper stub
        return func

    core_module.callback = _callback
    core_module.CALLBACK_TYPE = Callable[..., None]

    class _ConfigEntryError(Exception):
        """Base class for fake config entry errors."""

    class _ConfigEntryAuthFailedError(_ConfigEntryError): ...

    class _ConfigEntryNotReadyError(_ConfigEntryError): ...

    class _HomeAssistantError(Exception): ...

    exceptions_module.ConfigEntryAuthFailed = _ConfigEntryAuthFailedError
    exceptions_module.ConfigEntryNotReady = _ConfigEntryNotReadyError
    exceptions_module.HomeAssistantError = _HomeAssistantError

    class ConfigEntryState(StrEnum):
        LOADED = "loaded"
        SETUP_RETRY = "setup_retry"
        NOT_LOADED = "not_loaded"

    class ConfigEntry:  # pragma: no cover - helper stub
        def __init__(
            self,
            *,
            entry_id: str = "stub-entry",
            data: dict[str, object] | None = None,
            options: dict[str, object] | None = None,
        ) -> None:
            self.entry_id = entry_id
            self.data = data or {}
            self.options = options or {}
            self.state = ConfigEntryState.LOADED
            self.runtime_data: object | None = None

    class OptionsFlow:  # pragma: no cover - helper stub
        async def async_step_init(self, user_input: dict[str, object] | None = None):
            return {"type": "create_entry", "data": user_input or {}}

    class ConfigFlowResult(dict):  # pragma: no cover - helper stub
        pass

    config_entries_module.ConfigEntry = ConfigEntry
    config_entries_module.ConfigEntryState = ConfigEntryState
    config_entries_module.OptionsFlow = OptionsFlow
    config_entries_module.ConfigFlowResult = ConfigFlowResult

    class DeviceInfo(dict):  # pragma: no cover - helper stub
        pass

    class DeviceEntry:  # pragma: no cover - helper stub
        def __init__(self, **kwargs: object) -> None:
            self.id = kwargs.get("id", "device")

    class DeviceRegistry:  # pragma: no cover - helper stub
        def __init__(self) -> None:
            self.devices: dict[str, DeviceEntry] = {}

        def async_get_or_create(self, **kwargs: object) -> DeviceEntry:
            entry = DeviceEntry(**kwargs)
            self.devices[entry.id] = entry
            return entry

        def async_update_device(self, device_id: str, **kwargs: object) -> DeviceEntry:
            entry = self.devices.setdefault(device_id, DeviceEntry(id=device_id))
            return entry

        def async_listen(self, callback):  # type: ignore[no-untyped-def]
            return None

    def _async_get_device_registry(*args: object, **kwargs: object) -> DeviceRegistry:
        return DeviceRegistry()

    def _async_entries_for_config_entry(
        registry: DeviceRegistry, entry_id: str
    ) -> list[DeviceEntry]:
        return list(registry.devices.values())

    device_registry_module.DeviceInfo = DeviceInfo
    device_registry_module.DeviceEntry = DeviceEntry
    device_registry_module.DeviceRegistry = DeviceRegistry
    device_registry_module.async_get = _async_get_device_registry
    device_registry_module.async_entries_for_config_entry = (
        _async_entries_for_config_entry
    )

    class RegistryEntry:  # pragma: no cover - helper stub
        def __init__(self, entity_id: str, **kwargs: object) -> None:
            self.entity_id = entity_id
            self.device_id = kwargs.get("device_id")

    class EntityRegistry:  # pragma: no cover - helper stub
        def __init__(self) -> None:
            self.entities: dict[str, RegistryEntry] = {}

        def async_get(self, entity_id: str) -> RegistryEntry | None:
            return self.entities.get(entity_id)

        def async_get_or_create(
            self, entity_id: str, **kwargs: object
        ) -> RegistryEntry:
            entry = RegistryEntry(entity_id, **kwargs)
            self.entities[entity_id] = entry
            return entry

        def async_update_entity(
            self, entity_id: str, **kwargs: object
        ) -> RegistryEntry:
            entry = self.entities.setdefault(entity_id, RegistryEntry(entity_id))
            return entry

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

    entity_registry_module.RegistryEntry = RegistryEntry
    entity_registry_module.EntityRegistry = EntityRegistry
    entity_registry_module.async_get = _async_get_entity_registry
    entity_registry_module.async_entries_for_config_entry = (
        _async_entries_for_registry_config
    )

    class Store:  # pragma: no cover - helper stub
        def __init__(self, hass: object, version: int, key: str) -> None:
            self.hass = hass
            self.version = version
            self.key = key
            self.data: object | None = None

        async def async_load(self) -> object | None:
            return self.data

        async def async_save(self, data: object) -> None:
            self.data = data

    storage_module.Store = Store

    class _Entity:  # pragma: no cover - behaviour is not exercised directly
        """Placeholder for :class:`homeassistant.helpers.entity.Entity`."""

        pass

    entity_module.Entity = _Entity

    def _config_entry_only_config_schema(domain: str):  # pragma: no cover - helper stub
        def _schema(data: object) -> object:
            return data

        return _schema

    async def _async_get_clientsession(hass: object):  # pragma: no cover - helper stub
        return None

    async def _async_track_time_interval(*args: object, **kwargs: object):
        return None

    async def _async_track_time_change(*args: object, **kwargs: object):
        return None

    async def _async_call_later(*args: object, **kwargs: object):
        return None

    async def _async_track_state_change_event(*args: object, **kwargs: object):
        return None

    config_validation_module.config_entry_only_config_schema = (
        _config_entry_only_config_schema
    )
    aiohttp_client_module.async_get_clientsession = _async_get_clientsession
    event_module.async_track_time_interval = _async_track_time_interval
    event_module.async_track_time_change = _async_track_time_change
    event_module.async_call_later = _async_call_later
    event_module.async_track_state_change_event = _async_track_state_change_event

    class _DataUpdateCoordinator:  # pragma: no cover - helper stub
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

    class _CoordinatorUpdateFailedError(Exception): ...

    update_coordinator_module.DataUpdateCoordinator = _DataUpdateCoordinator
    update_coordinator_module.CoordinatorUpdateFailed = _CoordinatorUpdateFailedError

    def _utcnow() -> datetime:
        return datetime.now(UTC)

    dt_util_module.utcnow = _utcnow

    class _SelectorBase:  # pragma: no cover - helper stub
        def __init__(self, config: object | None = None) -> None:
            self.config = config

    class SelectSelectorMode(StrEnum):
        DROPDOWN = "dropdown"
        LIST = "list"

    class SelectSelectorConfig:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    class SelectSelector(_SelectorBase): ...

    class BooleanSelector(_SelectorBase): ...

    class NumberSelectorMode(StrEnum):
        BOX = "box"
        SLIDER = "slider"

    class NumberSelectorConfig:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    class NumberSelector(_SelectorBase): ...

    class TextSelectorType(StrEnum):
        TEXT = "text"
        TEL = "tel"

    class TextSelectorConfig:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs

    class TextSelector(_SelectorBase): ...

    class TimeSelector(_SelectorBase): ...

    class DateSelector(_SelectorBase): ...

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
    helpers_module.storage = storage_module
    util_module.dt = dt_util_module

    package_root = (
        pathlib.Path(__file__).resolve().parent.parent
        / "custom_components"
        / "pawcontrol"
    )

    custom_components_pkg = sys.modules.setdefault(
        "custom_components", types.ModuleType("custom_components")
    )
    custom_components_pkg.__path__ = [str(package_root.parent)]

    pawcontrol_pkg = types.ModuleType("custom_components.pawcontrol")
    pawcontrol_pkg.__path__ = [str(package_root)]
    sys.modules["custom_components.pawcontrol"] = pawcontrol_pkg

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
    sys.modules["homeassistant.helpers.storage"] = storage_module
    sys.modules["homeassistant.util"] = util_module
    sys.modules["homeassistant.util.dt"] = dt_util_module
    sys.modules["homeassistant.config_entries"] = config_entries_module


_install_homeassistant_stubs()

from custom_components.pawcontrol.entity_factory import (
    ENTITY_PROFILES,
    EntityFactory,
)


def test_basic_profile_supports_buttons() -> None:
    """The basic profile must now recognise button entities."""

    assert _Platform.BUTTON in ENTITY_PROFILES["basic"]["platforms"]


def test_validate_profile_rejects_unknown_modules() -> None:
    """Unknown modules should cause profile validation to fail."""

    factory = EntityFactory(coordinator=None)
    modules = {"feeding": True, "unknown": True}

    assert not factory.validate_profile_for_modules("standard", modules)


def test_should_create_entity_accepts_platform_enum() -> None:
    """Passing the Platform enum is supported and validated."""

    factory = EntityFactory(coordinator=None)

    assert factory.should_create_entity(
        "standard", _Platform.SENSOR, "feeding", priority=6
    )


def test_should_create_entity_accepts_nested_enum_alias() -> None:
    """Nested enum aliases should resolve to their underlying platform."""

    factory = EntityFactory(coordinator=None)

    assert factory.should_create_entity(
        "standard", _NestedPlatformAlias.SENSOR, "feeding", priority=6
    )


def test_should_create_entity_blocks_unknown_module() -> None:
    """Unknown modules are rejected even for high-priority requests."""

    factory = EntityFactory(coordinator=None)

    assert not factory.should_create_entity(
        "advanced", _Platform.SENSOR, "unknown", priority=9
    )


def test_create_entity_config_normalises_output() -> None:
    """Entity configuration results expose canonical values."""

    factory = EntityFactory(coordinator=None)
    config = factory.create_entity_config(
        dog_id="buddy",
        entity_type=_Platform.BUTTON,
        module="feeding",
        profile="basic",
        priority=9,
    )

    assert config is not None
    assert config["entity_type"] == "button"
    assert config["platform"] is _Platform.BUTTON


def test_create_entity_config_preserves_alias_enum_platform() -> None:
    """Entity configs should preserve alias enums when values match."""

    factory = EntityFactory(coordinator=None)

    config = factory.create_entity_config(
        dog_id="buddy",
        entity_type=_NestedPlatformAlias.SENSOR,
        module="feeding",
        profile="basic",
        priority=9,
    )

    assert config is not None
    assert config["platform"] is _NestedPlatformAlias.SENSOR


def test_create_entity_config_rejects_invalid_type() -> None:
    """Unsupported entity types should return ``None``."""

    factory = EntityFactory(coordinator=None)

    assert (
        factory.create_entity_config(
            dog_id="buddy",
            entity_type="unsupported",
            module="feeding",
            profile="standard",
        )
        is None
    )
