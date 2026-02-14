"""Tests for PawControl config entry migrations."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.pawcontrol.const import CONF_DOG_OPTIONS
from custom_components.pawcontrol.const import CONF_DOGS
from custom_components.pawcontrol.const import CONF_MODULES
from custom_components.pawcontrol.const import CONFIG_ENTRY_VERSION
from custom_components.pawcontrol.const import DOMAIN
from custom_components.pawcontrol.migrations import async_migrate_entry
from custom_components.pawcontrol.types import DOG_ID_FIELD
from custom_components.pawcontrol.types import DOG_MODULES_FIELD
from custom_components.pawcontrol.types import DOG_NAME_FIELD


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
