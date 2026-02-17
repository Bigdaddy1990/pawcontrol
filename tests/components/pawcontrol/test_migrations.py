"""Tests for PawControl config entry migrations."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
import pytest

from custom_components.pawcontrol.const import (
    CONF_DOG_OPTIONS,
    CONF_DOGS,
    CONF_MODULES,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
)
from custom_components.pawcontrol.migrations import async_migrate_entry
from custom_components.pawcontrol.types import (
    DOG_ID_FIELD,
    DOG_MODULES_FIELD,
    DOG_NAME_FIELD,
)


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2(hass: HomeAssistant) -> None:
    """Ensure legacy entry data is migrated into the latest schema."""  # noqa: E111

    entry = ConfigEntry(  # noqa: E111
        domain=DOMAIN,
        version=1,
        data={
            "name": "PawControl",
            CONF_DOGS: {
                "Buddy": {
                    "name": "Buddy",
                    "dog_weight": 22.5,
                    "modules": ["gps", "feeding"],
                },
                "Luna": {
                    "dog_name": "Luna",
                },
            },
            CONF_MODULES: {"gps": True, "feeding": True, "walk": False},
            CONF_DOG_OPTIONS: {
                "Buddy": {
                    "gps_settings": {"gps_update_interval": 30},
                }
            },
        },
        options={},
    )
    entry.add_to_hass(hass)  # noqa: E111

    result = await async_migrate_entry(hass, entry)  # noqa: E111

    assert result is True  # noqa: E111
    assert entry.version == CONFIG_ENTRY_VERSION  # noqa: E111
    assert CONF_MODULES not in entry.data  # noqa: E111
    assert CONF_DOG_OPTIONS not in entry.data  # noqa: E111

    dogs = entry.data[CONF_DOGS]  # noqa: E111
    assert isinstance(dogs, list)  # noqa: E111
    dog_map = {dog[DOG_ID_FIELD]: dog for dog in dogs}  # noqa: E111

    buddy = dog_map["buddy"]  # noqa: E111
    assert buddy[DOG_NAME_FIELD] == "Buddy"  # noqa: E111
    assert buddy[DOG_MODULES_FIELD]["gps"] is True  # noqa: E111
    assert buddy[DOG_MODULES_FIELD]["feeding"] is True  # noqa: E111

    luna = dog_map["luna"]  # noqa: E111
    assert luna[DOG_MODULES_FIELD]["gps"] is True  # noqa: E111
    assert luna[DOG_MODULES_FIELD]["walk"] is False  # noqa: E111

    dog_options = entry.options[CONF_DOG_OPTIONS]  # noqa: E111
    assert dog_options["buddy"]["gps_settings"]["gps_update_interval"] == 30  # noqa: E111
