"""Tests for PawControlOptionsFlow."""

import pytest

from custom_components.pawcontrol import config_flow, const
from homeassistant.config_entries import ConfigEntry

pytestmark = pytest.mark.asyncio


def _make_config_entry(options: dict | None = None) -> ConfigEntry:
    """Create a minimal config entry for tests."""
    from custom_components.pawcontrol import DOMAIN

    return ConfigEntry(
        version=1,
        minor_version=0,
        domain=DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="test123",
        unique_id=None,
        discovery_keys={},
        options=options or {},
        subentries_data=[],
    )


async def test_options_flow_instantiation_and_options_copy(hass):
    """Options flow should copy config entry options on init."""
    entry = _make_config_entry({"existing": True})

    flow = config_flow.PawControlOptionsFlow(entry)
    flow.hass = hass

    assert flow.config_entry is entry
    assert flow._options == {"existing": True}

    # Modifying internal options should not mutate original config entry
    flow._options["new"] = 1
    assert "new" not in entry.options


async def test_options_flow_menu_options(hass):
    """Initial step should present all available menu options."""
    entry = _make_config_entry()

    flow = config_flow.PawControlOptionsFlow(entry)
    flow.hass = hass
    result = await flow.async_step_init()

    assert result["type"] == "menu"
    assert result["step_id"] == "init"
    assert result["menu_options"] == [
        "medications",
        "reminders",
        "safe_zones",
        "advanced",
        "schedule",
        "modules",
        "dogs",
        "medication_mapping",
        "sources",
        "notifications",
        "system",
    ]


async def test_options_flow_sources_updates_options(hass):
    """Sources step should store provided source configuration."""
    entry = _make_config_entry()
    flow = config_flow.PawControlOptionsFlow(entry)
    flow.hass = hass

    user_input = {const.CONF_DOOR_SENSOR: "binary_sensor.front_door"}
    result = await flow.async_step_sources(user_input)

    assert result["type"] == "create_entry"
    assert flow._options[const.CONF_SOURCES] == user_input

