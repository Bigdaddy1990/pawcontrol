"""Tests for the PawControl config flow."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from custom_components.pawcontrol import compat, config_flow
from custom_components.pawcontrol.const import (
    CONF_DOG_AGE,
    CONF_DOG_BREED,
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOG_SIZE,
    CONF_DOG_WEIGHT,
    CONF_MODULES,
    DOMAIN,
    MODULE_DASHBOARD,
    MODULE_GPS,
)
from custom_components.pawcontrol.entity_factory import ENTITY_PROFILES
from custom_components.pawcontrol.exceptions import PawControlSetupError
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

try:  # pragma: no cover - Home Assistant import path available in full test runs
    from homeassistant.exceptions import ConfigEntryNotReady
except Exception:  # pragma: no cover - fall back to compat alias
    from custom_components.pawcontrol.compat import ConfigEntryNotReady
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


def test_config_flow_alias_exports() -> None:
    """Ensure the compatibility ConfigFlow alias remains intact."""

    assert config_flow.ConfigFlow is config_flow.PawControlConfigFlow
    assert "ConfigFlow" in config_flow.__all__


def test_config_flow_not_ready_alias_rebinds() -> None:
    """The config flow updates its not-ready alias when exceptions refresh."""

    original_module = sys.modules.get("homeassistant.exceptions")
    original_class = config_flow.ConfigEntryNotReady

    sentinel_module = ModuleType("homeassistant.exceptions")

    base_error = type("_SentinelHomeAssistantError", (Exception,), {})
    entry_error = type("_SentinelConfigEntryError", (base_error,), {})
    auth_failed = type("_SentinelConfigEntryAuthFailed", (entry_error,), {})
    not_ready = type("_SentinelConfigEntryNotReady", (entry_error,), {})
    service_validation = type("_SentinelServiceValidationError", (base_error,), {})

    sentinel_module.HomeAssistantError = base_error
    sentinel_module.ConfigEntryError = entry_error
    sentinel_module.ConfigEntryAuthFailed = auth_failed
    sentinel_module.ConfigEntryNotReady = not_ready
    sentinel_module.ServiceValidationError = service_validation

    try:
        sys.modules["homeassistant.exceptions"] = sentinel_module
        compat.ensure_homeassistant_exception_symbols()

        assert config_flow.ConfigEntryNotReady is not original_class
        assert config_flow.ConfigEntryNotReady is sentinel_module.ConfigEntryNotReady
    finally:
        if original_module is None:
            sys.modules.pop("homeassistant.exceptions", None)
        else:
            sys.modules["homeassistant.exceptions"] = original_module
        compat.ensure_homeassistant_exception_symbols()

    restored = config_flow.ConfigEntryNotReady
    assert restored.__name__.endswith("ConfigEntryNotReady")
    if original_module is not None:
        original_candidate = getattr(original_module, "ConfigEntryNotReady", None)
        if isinstance(original_candidate, type):
            assert restored is original_candidate


def _assert_step_id(result: dict[str, Any], expected: str) -> None:
    """Assert the underlying flow step matches the expectation."""

    actual = result.get("__real_step_id", result["step_id"])
    assert actual == expected


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
    _assert_step_id(result, "add_dog")

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
    _assert_step_id(result, "dog_modules")

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
    _assert_step_id(result, "add_another")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"add_another": False}
    )
    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "entity_profile")

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


async def test_dog_modules_invalid_input(hass: HomeAssistant) -> None:
    """Ensure invalid module data surfaces form errors."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

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

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"feeding": "definitely"},
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "dog_modules")
    assert result["errors"] == {"base": "invalid_modules"}


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
    _assert_step_id(result, "reauth_confirm")

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
    _assert_step_id(result, "reconfigure")
    placeholders = result["description_placeholders"]
    assert placeholders["current_profile"] == "standard"
    assert placeholders["dogs_count"] == "0"

    with patch(
        "homeassistant.config_entries.ConfigFlow.async_update_reload_and_abort",
    ) as update_mock:
        update_mock.return_value = {
            "type": FlowResultType.ABORT,
            "reason": "reconfigure_successful",
        }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"entity_profile": "basic"}
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    update_mock.assert_called_once()
    call_kwargs = update_mock.call_args.kwargs
    data_updates = call_kwargs["data_updates"]
    options_updates = call_kwargs["options_updates"]

    assert data_updates["entity_profile"] == "basic"
    assert (
        data_updates["reconfigure_version"] == config_flow.PawControlConfigFlow.VERSION
    )

    telemetry = options_updates["reconfigure_telemetry"]
    assert telemetry["requested_profile"] == "basic"
    assert telemetry["previous_profile"] == "standard"
    assert telemetry["dogs_count"] == 0
    assert telemetry["estimated_entities"] == 0
    assert telemetry["version"] == config_flow.PawControlConfigFlow.VERSION
    assert telemetry["health_summary"]["healthy"] is True

    timestamp = telemetry["timestamp"]
    assert timestamp == data_updates["reconfigure_timestamp"]
    assert timestamp == options_updates["last_reconfigure"]
    assert options_updates["previous_profile"] == "standard"
    assert options_updates["entity_profile"] == "basic"


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
    _assert_step_id(result, "discovery_confirm")
    assert result["description_placeholders"]["discovery_source"] == "dhcp"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "add_dog")


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
    _assert_step_id(result, "discovery_confirm")
    assert result["description_placeholders"]["discovery_source"] == "zeroconf"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "add_dog")


async def test_discovery_rejection_aborts(hass: HomeAssistant) -> None:
    """Validate that users can decline discovered devices."""

    zeroconf_info = ZeroconfServiceInfo(
        host="192.168.1.42",
        hostname="paw-control-acceptance.local",
        name="_pawcontrol._tcp.local.",
        port=443,
        properties={"serial": "paw-accept"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=zeroconf_info,
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"confirm": False}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "discovery_rejected"


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


@pytest.mark.asyncio
async def test_reauth_confirm_records_health_summary(hass: HomeAssistant) -> None:
    """Reauth should persist typed health summaries and sanitise issues."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Paw Control",
            "dogs": [{"dog_id": "fido", "dog_name": "Fido"}],
            "entity_profile": "standard",
        },
        options={"entity_profile": "standard"},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.pawcontrol.config_flow.dt_util.utcnow",
            return_value=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        patch.object(
            config_flow.PawControlConfigFlow,
            "_check_config_health_enhanced",
            return_value={
                "healthy": False,
                "issues": ["alpha", 2],
                "warnings": ["beta", None],
                "validated_dogs": 1,
                "total_dogs": 2,
            },
        ),
        patch.object(
            config_flow.PawControlConfigFlow,
            "async_update_reload_and_abort",
            AsyncMock(
                return_value={
                    "type": FlowResultType.ABORT,
                    "reason": "reauth_successful",
                }
            ),
        ) as mock_update,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )

        await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"confirm": True}
        )

    assert mock_update.call_count == 1
    update_kwargs = mock_update.call_args.kwargs
    data_updates = update_kwargs["data_updates"]
    options_updates = update_kwargs["options_updates"]

    assert data_updates["health_validated_dogs"] == 1
    assert data_updates["health_total_dogs"] == 2
    assert options_updates["reauth_health_issues"] == ["alpha", "2"]
    assert options_updates["reauth_health_warnings"] == ["beta"]
    assert options_updates["last_reauth_summary"].startswith("Status: ")


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
    _assert_step_id(result, "discovery_confirm")
    assert result["description_placeholders"]["discovery_source"] == "usb"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "add_dog")


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
    _assert_step_id(result, "discovery_confirm")
    assert result["description_placeholders"]["discovery_source"] == "bluetooth"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"confirm": True},
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "add_dog")


async def test_import_flow_success_with_warnings(hass: HomeAssistant) -> None:
    """Exercise the enhanced import validation path."""

    import_payload = {
        "name": "PawControl YAML",
        "entity_profile": "standard",
        "dogs": [
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Buddy",
                CONF_DOG_BREED: "Collie",
                CONF_DOG_AGE: 4,
                CONF_DOG_WEIGHT: 18.5,
                CONF_DOG_SIZE: "medium",
                "modules": {"feeding": True, "walk": True, "gps": True},
            },
            {
                CONF_DOG_ID: "buddy",
                CONF_DOG_NAME: "Duplicate",
                CONF_DOG_BREED: "Collie",
                CONF_DOG_AGE: 4,
                CONF_DOG_WEIGHT: 18.5,
                CONF_DOG_SIZE: "medium",
            },
        ],
    }

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data=import_payload,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "PawControl (Imported)"
    assert result["data"]["entity_profile"] == "standard"
    assert len(result["data"]["dogs"]) == 1
    assert result["options"]["import_source"] == "configuration_yaml"
    assert "Duplicate dog ID" in "; ".join(result["data"]["import_warnings"])


async def test_import_flow_without_valid_dogs(hass: HomeAssistant) -> None:
    """Ensure invalid YAML imports raise ConfigEntryNotReady."""

    flow = config_flow.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}

    with pytest.raises(Exception) as excinfo:
        await flow.async_step_import({"dogs": []})

    error_type = excinfo.value.__class__
    assert error_type.__name__.endswith("ConfigEntryNotReady")


async def test_entity_profile_invalid_input(hass: HomeAssistant) -> None:
    """Cover the profile validation failure branch."""

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

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

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"feeding": True, "walk": True, "health": True},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"add_another": False}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"entity_profile": "nonexistent"}
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "entity_profile")
    assert result["errors"] == {"base": "invalid_profile"}


async def test_final_setup_validation_failure(hass: HomeAssistant) -> None:
    """The final validation step should reject invalid dog data."""

    flow = config_flow.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._dogs = [  # pylint: disable=protected-access
        {
            CONF_DOG_ID: "buddy",
            CONF_DOG_NAME: "",
            CONF_DOG_SIZE: "medium",
            CONF_DOG_WEIGHT: 20.0,
            CONF_DOG_AGE: 5,
            "modules": {"feeding": True},
        }
    ]

    with pytest.raises(PawControlSetupError):
        await flow.async_step_final_setup()


async def test_reconfigure_invalid_profile_error(hass: HomeAssistant) -> None:
    """Submitting an invalid profile during reconfigure returns the form."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Paw Control",
            "dogs": [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}],
            "entity_profile": "standard",
        },
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

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"entity_profile": "invalid"}
    )

    assert result["type"] == FlowResultType.FORM
    _assert_step_id(result, "reconfigure")
    assert result["errors"] == {"base": "invalid_profile"}
    assert "error_details" in result["description_placeholders"]


async def test_reconfigure_telemetry_records_warnings(hass: HomeAssistant) -> None:
    """Compatibility warnings and telemetry metadata are captured during reconfigure."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "name": "Paw Control",
            "dogs": [{CONF_DOG_ID: "buddy", CONF_DOG_NAME: "Buddy"}],
            "entity_profile": "standard",
        },
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

    with (
        patch(
            "homeassistant.config_entries.ConfigFlow.async_update_reload_and_abort",
        ) as update_mock,
        patch.object(
            config_flow.PawControlConfigFlow,
            "_check_profile_compatibility",
            return_value={
                "compatible": False,
                "warnings": ["Profile 'basic' may not be optimal for Buddy"],
            },
        ),
        patch.object(
            config_flow.PawControlConfigFlow,
            "_check_config_health_enhanced",
            AsyncMock(
                return_value={
                    "healthy": True,
                    "issues": [],
                    "warnings": [],
                    "validated_dogs": 1,
                    "total_dogs": 1,
                }
            ),
        ),
        patch.object(
            config_flow.PawControlConfigFlow,
            "_estimate_entities_for_reconfigure",
            AsyncMock(return_value=3),
        ),
    ):
        update_mock.return_value = {
            "type": FlowResultType.ABORT,
            "reason": "reconfigure_successful",
        }
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={"entity_profile": "basic"}
        )

    assert result["type"] == FlowResultType.ABORT
    update_mock.assert_called_once()

    telemetry = update_mock.call_args.kwargs["options_updates"]["reconfigure_telemetry"]
    assert telemetry["estimated_entities"] == 3
    assert telemetry["compatibility_warnings"] == [
        "Profile 'basic' may not be optimal for Buddy"
    ]
    assert telemetry["health_summary"]["validated_dogs"] == 1


async def test_configure_dashboard_form_includes_context(hass: HomeAssistant) -> None:
    """The dashboard configuration step should surface helpful placeholders."""

    flow = config_flow.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._dogs = [
        {CONF_DOG_ID: "buddy", CONF_MODULES: {MODULE_DASHBOARD: True}},
        {CONF_DOG_ID: "max", CONF_MODULES: {MODULE_DASHBOARD: True}},
    ]
    flow._enabled_modules = {MODULE_GPS: True}

    result = await flow.async_step_configure_dashboard()

    assert result["type"] == FlowResultType.FORM
    placeholders = result["description_placeholders"]
    assert placeholders["dog_count"] == 2
    assert "dashboard" in placeholders["dashboard_info"].lower()


async def test_configure_dashboard_with_gps_routes_external(
    hass: HomeAssistant,
) -> None:
    """Submitting dashboard settings with GPS enabled should request external setup."""

    flow = config_flow.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._dogs = [{CONF_DOG_ID: "buddy", CONF_MODULES: {MODULE_DASHBOARD: True}}]
    flow._enabled_modules = {MODULE_GPS: True}
    flow.async_step_configure_external_entities = AsyncMock(
        return_value={"type": FlowResultType.FORM, "step_id": "configure_external"}
    )
    flow.async_step_final_setup = AsyncMock()

    result = await flow.async_step_configure_dashboard(
        {
            "auto_create_dashboard": True,
            "create_per_dog_dashboards": True,
            "dashboard_theme": "default",
            "dashboard_mode": "cards",
            "show_statistics": True,
            "show_maps": True,
        }
    )

    _assert_step_id(result, "configure_external")
    flow.async_step_configure_external_entities.assert_awaited_once()
    flow.async_step_final_setup.assert_not_awaited()


async def test_configure_modules_routes_to_dashboard_when_enabled(
    hass: HomeAssistant,
) -> None:
    """The modules step should branch to dashboard configuration when enabled."""

    flow = config_flow.PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._dogs = [
        {
            CONF_DOG_ID: "buddy",
            CONF_MODULES: {MODULE_DASHBOARD: True, MODULE_GPS: False},
        }
    ]
    flow._enabled_modules = {MODULE_DASHBOARD: True}
    flow.async_step_configure_dashboard = AsyncMock(
        return_value={"type": FlowResultType.FORM, "step_id": "configure_dashboard"}
    )

    result = await flow.async_step_configure_modules(
        {
            "performance_mode": "balanced",
            "enable_analytics": False,
            "enable_cloud_backup": False,
            "data_retention_days": 90,
            "debug_logging": False,
        }
    )

    _assert_step_id(result, "configure_dashboard")
    flow.async_step_configure_dashboard.assert_awaited_once()
