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
    """Ensure legacy entry data is migrated into the latest schema."""
    entry = ConfigEntry(
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
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == CONFIG_ENTRY_VERSION
    assert CONF_MODULES not in entry.data
    assert CONF_DOG_OPTIONS not in entry.data

    dogs = entry.data[CONF_DOGS]
    assert isinstance(dogs, list)
    dog_map = {dog[DOG_ID_FIELD]: dog for dog in dogs}

    buddy = dog_map["buddy"]
    assert buddy[DOG_NAME_FIELD] == "Buddy"
    assert buddy[DOG_MODULES_FIELD]["gps"] is True
    assert buddy[DOG_MODULES_FIELD]["feeding"] is True

    luna = dog_map["luna"]
    assert luna[DOG_MODULES_FIELD]["gps"] is True
    assert luna[DOG_MODULES_FIELD]["walk"] is False

    dog_options = entry.options[CONF_DOG_OPTIONS]
    assert dog_options["buddy"]["gps_settings"]["gps_update_interval"] == 30


@pytest.mark.asyncio
async def test_async_migrate_entry_rejects_newer_version(
    hass: HomeAssistant,
) -> None:
    """Migration fails when an entry advertises a future schema version."""
    entry = ConfigEntry(
        domain=DOMAIN,
        version=CONFIG_ENTRY_VERSION + 1,
        data={},
        options={},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is False
    assert entry.version == CONFIG_ENTRY_VERSION + 1


@pytest.mark.asyncio
async def test_async_migrate_entry_normalizes_legacy_dog_payload_shapes(
    hass: HomeAssistant,
) -> None:
    """Legacy list payloads and mixed module toggles are normalized."""
    entry = ConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_DOGS: [
                {
                    "dogId": " Shadow ",
                    "name": " ",
                    "modules": [
                        "gps",
                        {"module": "feeding", "enabled": "off"},
                        {"module": "walk", "value": "yes"},
                    ],
                },
                {
                    "id": "Milo",
                    "dog_name": "Milo",
                },
            ]
        },
        options={
            CONF_DOG_OPTIONS: [
                {DOG_ID_FIELD: "Shadow", "gps_settings": {"gps_update_interval": 5}},
            ]
        },
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    dogs = entry.data[CONF_DOGS]
    dog_map = {dog[DOG_ID_FIELD]: dog for dog in dogs}
    assert dog_map["shadow"][DOG_NAME_FIELD] == "shadow"
    assert dog_map["shadow"][DOG_MODULES_FIELD] == {
        "gps": True,
        "feeding": False,
        "walk": True,
    }
    assert dog_map["milo"][DOG_NAME_FIELD] == "Milo"
    assert entry.options[CONF_DOG_OPTIONS]["Shadow"]["gps_settings"] == {
        "gps_update_interval": 5,
    }


@pytest.mark.asyncio
async def test_async_migrate_entry_from_pre_v1_applies_default_path(
    hass: HomeAssistant,
) -> None:
    """Version zero entries are promoted through the v1 migration logic."""
    entry = ConfigEntry(
        domain=DOMAIN,
        version=0,
        data={
            CONF_DOGS: {
                " Daisy ": {
                    "identifier": " DAISY ",
                    "name": "Daisy",
                }
            }
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await async_migrate_entry(hass, entry)

    assert result is True
    assert entry.version == CONFIG_ENTRY_VERSION
    assert entry.data[CONF_DOGS][0][DOG_ID_FIELD] == "daisy"
