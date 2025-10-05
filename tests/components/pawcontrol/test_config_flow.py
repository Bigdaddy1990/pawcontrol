"""Tests for the PawControl config flow."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    DOMAIN,
)
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.usb import UsbServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

sys.modules.setdefault("bluetooth_adapters", ModuleType("bluetooth_adapters"))
sys.modules.setdefault(
    "homeassistant.components.bluetooth_adapters", ModuleType("bluetooth_adapters")
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture(autouse=True)
def mock_dependencies(hass: HomeAssistant) -> None:
    """Mock required dependencies for the integration."""
    mock_integration(hass, MockModule(domain="bluetooth-adapters"))


async def test_full_user_flow(hass: HomeAssistant) -> None:
    """Test a full successful user initiated config flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"

    dog = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        CONF_DOG_BREED: "Labrador",
        CONF_DOG_AGE: 5,
        CONF_DOG_WEIGHT: 25.0,
        CONF_DOG_SIZE: "medium",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=dog
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "dog_modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": False,
            "notifications": True,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_another"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"add_another": False}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "entity_profile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"entity_profile": "standard"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == f"Paw Control ({ENTITY_PROFILES['standard']['name']})"
    assert result["data"]["name"] == "Paw Control"
    assert len(result["data"]["dogs"]) == 1
    dog_result = result["data"]["dogs"][0]
    assert dog_result[CONF_DOG_ID] == "fido"
    assert dog_result[CONF_DOG_NAME] == "Fido"
    assert dog_result[CONF_DOG_BREED] == "Labrador"
    assert dog_result[CONF_DOG_AGE] == 5
    assert dog_result[CONF_DOG_WEIGHT] == 25.0
    assert dog_result[CONF_DOG_SIZE] == "medium"


async def test_duplicate_dog_id(hass: HomeAssistant) -> None:
    """Test that duplicate dog IDs are rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # First dog
    dog_data = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Fido",
        CONF_DOG_BREED: "Labrador",
        CONF_DOG_AGE: 5,
        CONF_DOG_WEIGHT: 25.0,
        CONF_DOG_SIZE: "medium",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=dog_data
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "feeding": True,
            "walk": True,
            "health": True,
            "gps": False,
            "notifications": True,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"add_another": True}
    )
    # Second dog with same ID
    second_dog = {
        CONF_DOG_ID: "fido",
        CONF_DOG_NAME: "Spot",
        CONF_DOG_BREED: "Beagle",
        CONF_DOG_AGE: 3,
        CONF_DOG_WEIGHT: 10.0,
        CONF_DOG_SIZE: "small",
    }
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=second_dog
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_ID: "ID already exists"}


async def test_reauth_confirm(hass: HomeAssistant) -> None:
    """Test reauthentication confirmation flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_reconfigure_flow(hass: HomeAssistant) -> None:
    """Test the reconfigure flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        options={"entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    with patch(
        "homeassistant.config_entries.ConfigFlow.async_update_reload_and_abort",
        return_value={"type": FlowResultType.ABORT, "reason": "reconfigure_successful"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"entity_profile": "basic"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_dhcp_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure DHCP discovery guides the user through confirmation before setup."""

    dhcp_info = DhcpServiceInfo(
        ip="192.168.1.25",
        hostname="tractive-42",
        macaddress="00:11:22:33:44:55",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_DHCP},
        data=dhcp_info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["discovery_source"] == "dhcp"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"


async def test_zeroconf_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure Zeroconf discovery surfaces the confirmation step."""

    zeroconf_info = ZeroconfServiceInfo(
        host="192.168.1.31",
        hostname="paw-control-7f.local",
        port=1234,
        type="_pawcontrol._tcp.local.",
        name="paw-control-7f",
        properties={"serial": "paw-7f"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf_info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["discovery_source"] == "zeroconf"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"


async def test_single_instance(hass: HomeAssistant) -> None:
    """Test that only a single instance can be configured."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_invalid_dog_id(hass: HomeAssistant) -> None:
    """Test that invalid dog IDs are rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_DOG_ID: "Invalid ID", CONF_DOG_NAME: "Fido"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_DOG_ID: "Invalid ID format"}


async def test_reauth_confirm_fail(hass: HomeAssistant) -> None:
    """Test reauthentication confirmation failure."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Paw Control", "dogs": [], "entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": False}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "reauth_unsuccessful"}


async def test_usb_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure USB discovery initiates the confirmation step."""

    usb_info = UsbServiceInfo(
        device="/dev/ttyUSB0",
        vid=0x1234,
        pid=0x5678,
        serial_number="TRACTIVEUSB01",
        manufacturer="Tractive",
        description="tractive-gps-tracker",
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USB},
        data=usb_info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["discovery_source"] == "usb"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"


async def test_bluetooth_discovery_flow(hass: HomeAssistant) -> None:
    """Ensure Bluetooth discovery funnels into confirmation."""

    bluetooth_info = SimpleNamespace(
        name="tractive-ble-tracker",
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=["0000180f-0000-1000-8000-00805f9b34fb"],
        manufacturer_data={},
        service_data={},
        source="local",
        advertisement=None,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=bluetooth_info,
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["discovery_source"] == "bluetooth"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_dog"
