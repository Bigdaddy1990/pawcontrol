"""Integration tests for PawControl config flow.

Tests the complete configuration flow including user input,
validation, and entry creation.

Quality Scale: Platinum target
Python: 3.13+
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from custom_components.pawcontrol.const import DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

DEFAULT_MODULE_SELECTION = {
    "feeding": True,
    "walk": True,
    "health": True,
    "gps": False,
    "notifications": True,
}

EXTERNAL_ENTITY_MODULE_TOGGLES = {
    "feeding": False,
    "walk": False,
    "health": False,
    "gps": True,
    "notifications": True,
}


def _current_step(result: dict[str, Any]) -> str:
    """Return the underlying flow step identifier."""

    return result.get("__real_step_id", result["step_id"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_flow_single_dog(hass: HomeAssistant):
    """Test user configuration flow with single dog."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    # Provide dog configuration
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Buddy",
            "dog_id": "buddy",
            "dog_weight": 30.0,
            "breed": "Golden Retriever",
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "dog_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULT_MODULE_SELECTION)
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_another"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": False}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "entity_profile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"entity_profile": "standard"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Paw Control (Standard (≤12 entities))"
    assert result["data"]["dogs"][0]["dog_id"] == "buddy"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_flow_multiple_dogs(hass: HomeAssistant):
    """Test adding multiple dogs through flow."""
    # First dog
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Buddy",
            "dog_id": "buddy",
            "dog_weight": 30.0,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "dog_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULT_MODULE_SELECTION)
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_another"

    # User chooses to add another dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": True}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    # Second dog
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Max",
            "dog_id": "max",
            "dog_weight": 15.0,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "dog_modules"

    second_modules = dict(DEFAULT_MODULE_SELECTION)
    second_modules["walk"] = False
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], second_modules
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_another"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": False}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "entity_profile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"entity_profile": "standard"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert len(result["data"]["dogs"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_flow_configures_external_entities(hass: HomeAssistant) -> None:
    """Validate that the flow collects and stores external entity selections."""

    hass.states.async_set(
        "device_tracker.main_phone",
        "home",
        {"friendly_name": "Main phone"},
    )
    hass.states.async_set(
        "person.dog_walker",
        "home",
        {"friendly_name": "Dog Walker"},
    )
    hass.states.async_set(
        "binary_sensor.back_door",
        "off",
        {"device_class": "door", "friendly_name": "Back door"},
    )

    async def _notify_handler(call: ServiceCall) -> None:
        return None

    hass.services.async_register(
        "notify", "mobile_app_main_phone", _notify_handler
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Buddy",
            "dog_id": "buddy",
            "dog_weight": 30.0,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "dog_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        dict(EXTERNAL_ENTITY_MODULE_TOGGLES),
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_another"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": False}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "entity_profile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"entity_profile": "standard"}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "configure_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "configure_dashboard"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "auto_create_dashboard": True,
            "create_per_dog_dashboards": False,
            "dashboard_theme": "modern",
            "dashboard_mode": "cards",
            "show_statistics": True,
            "show_maps": True,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "configure_external_entities"

    placeholders = result["description_placeholders"]
    assert placeholders["gps_enabled"] is True
    assert placeholders["visitor_enabled"] is False
    assert placeholders["dog_count"] == 1

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "gps_source": "device_tracker.main_phone",
            "door_sensor": "binary_sensor.back_door",
            "notify_fallback": "notify.mobile_app_main_phone",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["external_entities"] == {
        "gps_source": "device_tracker.main_phone",
        "door_sensor": "binary_sensor.back_door",
        "notify_fallback": "notify.mobile_app_main_phone",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_zeroconf_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure Zeroconf discovery shows confirmation step."""

    info = ZeroconfServiceInfo(
        host="192.168.1.10",
        hostname="paw-control-tracker.local.",
        port=1234,
        type="_pawcontrol._tcp.local.",
        name="Paw Control Tracker",
        properties={"device_id": "paw-1234"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dhcp_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure DHCP discovery populates confirmation form."""

    info = DhcpServiceInfo(
        ip="192.168.1.20",
        hostname="paw-control-dog",
        macaddress="AA:BB:CC:DD:EE:FF",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_options_flow_basic(hass: HomeAssistant, mock_config_entry):
    """Test options flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Configure options
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "entity_profile": "advanced",
            "external_integrations": True,
            "update_interval": 60,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options["entity_profile"] == "advanced"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_flow_validates_dog_id_unique(hass: HomeAssistant):
    """Test that flow validates dog IDs are unique."""
    # Create entry with dog
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Buddy",
            "dog_id": "buddy",
            "dog_weight": 30.0,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "dog_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(DEFAULT_MODULE_SELECTION)
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_another"

    # Try to add dog with same ID
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"add_another": True}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Max",
            "dog_id": "buddy",  # Same ID
            "dog_weight": 15.0,
        },
    )

    # Should show error on add_dog step
    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"
    assert "errors" in result
    assert "dog_id" in result["errors"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_flow_validates_input(hass: HomeAssistant):
    """Test input validation in config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"

    # Provide invalid weight
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "dog_name": "Buddy",
            "dog_id": "buddy",
            "dog_weight": -5.0,  # Invalid
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert _current_step(result) == "add_dog"
    assert "errors" in result


@pytest.mark.integration
@pytest.mark.asyncio
async def test_import_flow(hass: HomeAssistant):
    """Test import from YAML."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={
            "dogs": [
                {
                    "dog_id": "buddy",
                    "dog_name": "Buddy",
                    "dog_weight": 30.0,
                }
            ]
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["dogs"][0]["dog_id"] == "buddy"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_reauth_flow(hass: HomeAssistant, mock_config_entry):
    """Test reauthentication flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    # Provide new credentials
    with patch("custom_components.pawcontrol.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "confirm": True,
                "api_token": "new_token",
            },
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
