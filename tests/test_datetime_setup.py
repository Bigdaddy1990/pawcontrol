from collections.abc import Callable, Iterable
from enum import Enum
import importlib
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

# Home Assistant stubs
ha_core = types.ModuleType("homeassistant.core")


class HomeAssistant:
    pass


class ServiceCall:
    def __init__(self, domain=None, service=None, data=None, context=None):
        self.domain = domain
        self.service = service
        self.data = data or {}
        self.context = context


ha_core.HomeAssistant = HomeAssistant
ha_core.ServiceCall = ServiceCall

ha_config_entries = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:
    def __init__(self, *, options=None):
        self.options = options or {}


class ConfigEntryState(Enum):
    LOADED = "loaded"


ha_config_entries.ConfigEntry = ConfigEntry
ha_config_entries.ConfigEntryState = ConfigEntryState

ha_const = types.ModuleType("homeassistant.const")


class Platform(Enum):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    BUTTON = "button"
    NUMBER = "number"
    SELECT = "select"
    TEXT = "text"
    DATETIME = "datetime"
    SWITCH = "switch"
    DEVICE_TRACKER = "device_tracker"


ha_const.Platform = Platform

ha_helpers_entity = types.ModuleType("homeassistant.helpers.entity")


class DeviceInfo:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


ha_helpers_entity.DeviceInfo = DeviceInfo

ha_helpers_entity_platform = types.ModuleType("homeassistant.helpers.entity_platform")
AddEntitiesCallback = Callable[[Iterable], None]
ha_helpers_entity_platform.AddEntitiesCallback = AddEntitiesCallback

ha_components_datetime = types.ModuleType("homeassistant.components.datetime")


class DateTimeEntity:
    def async_write_ha_state(self):
        pass


ha_components_datetime.DateTimeEntity = DateTimeEntity

ha_components = types.ModuleType("homeassistant.components")
ha_components.datetime = ha_components_datetime

# Register stub modules
sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
sys.modules["homeassistant.core"] = ha_core
sys.modules["homeassistant.config_entries"] = ha_config_entries
sys.modules["homeassistant.const"] = ha_const
sys.modules.setdefault(
    "homeassistant.helpers", types.ModuleType("homeassistant.helpers")
)
sys.modules["homeassistant.helpers.entity"] = ha_helpers_entity
sys.modules["homeassistant.helpers.entity_platform"] = ha_helpers_entity_platform
sys.modules["homeassistant.components"] = ha_components
sys.modules["homeassistant.components.datetime"] = ha_components_datetime

# Prepare package structure without executing integration __init__
root_path = pathlib.Path(__file__).resolve().parent.parent / "custom_components"
custom_pkg = types.ModuleType("custom_components")
custom_pkg.__path__ = [str(root_path)]
sys.modules.setdefault("custom_components", custom_pkg)

paw_pkg = types.ModuleType("custom_components.pawcontrol")
paw_pkg.__path__ = [str(root_path / "pawcontrol")]
sys.modules["custom_components.pawcontrol"] = paw_pkg

# Import module under test
paw_datetime = importlib.import_module("custom_components.pawcontrol.datetime")
NextMedicationDateTime = paw_datetime.NextMedicationDateTime
async_setup_entry = paw_datetime.async_setup_entry
DOMAIN = paw_datetime.DOMAIN

# Clean up stub package to avoid interfering with other tests
sys.modules.pop("custom_components.pawcontrol", None)
# Remove stubbed Home Assistant modules to restore global state for other tests
for mod in [
    "homeassistant.core",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.helpers",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.components",
    "homeassistant.components.datetime",
    "homeassistant",
]:
    sys.modules.pop(mod, None)


@pytest.mark.asyncio
async def test_async_setup_entry_creates_entities_for_dogs() -> None:
    hass = MagicMock()
    hass.states = MagicMock(get=MagicMock(return_value=None))
    entry = ConfigEntry(
        options={
            "dogs": [
                {"dog_id": "abc", "name": "Rex", "modules": {"health": True}},
                {"name": "Fido", "modules": {"health": True}},
            ]
        }
    )

    added: dict[str, list[NextMedicationDateTime]] = {}

    def add_entities(
        entities: Iterable[NextMedicationDateTime],
        update_before_add: bool = False,
    ) -> None:
        added["entities"] = list(entities)
        added["update_before_add"] = update_before_add

    await async_setup_entry(hass, entry, add_entities)

    assert added["update_before_add"] is False
    assert added["entities"]
