from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from custom_components.pawcontrol.config_flow import PawControlConfigFlow
from custom_components.pawcontrol.const import (
    CONF_DOG_ID,
    CONF_DOG_NAME,
    CONF_DOGS,
    CONF_NAME,
    DOMAIN,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest_asyncio.fixture
async def hass(tmp_path) -> HomeAssistant:
    """Provide a minimal Home Assistant instance for tests."""
    hass = HomeAssistant(str(tmp_path))
    hass.data["components"] = set()
    hass.data["integrations"] = {}
    hass.data["preload_platforms"] = {}
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.async_start()
    try:
        yield hass
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
@patch("homeassistant.config_entries._load_integration", new_callable=AsyncMock)
async def test_full_config_flow(mock_load, hass: HomeAssistant) -> None:
    """Test a full successful config flow."""
    mock_load.return_value = None
    with patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Paw Setup"}
        )
        flow_id = result["flow_id"]
        assert result["step_id"] == "add_dog"

        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido"}
        )
        assert result["step_id"] == "dog_modules"

        result = await hass.config_entries.flow.async_configure(flow_id, {})
        assert result["step_id"] == "add_another"

        result = await hass.config_entries.flow.async_configure(
            flow_id, {"add_another": False}
        )
        assert result["step_id"] == "entity_profile"

        result = await hass.config_entries.flow.async_configure(
            flow_id, {"entity_profile": "standard"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"].startswith("Paw Setup (")
        assert result["data"]["name"] == "Paw Setup"
        assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "fido"
        assert result["data"][CONF_DOGS][0][CONF_DOG_NAME] == "Fido"


@pytest.mark.asyncio
@patch("homeassistant.config_entries._load_integration", new_callable=AsyncMock)
async def test_invalid_name(mock_load, hass: HomeAssistant) -> None:
    """Test submitting an empty integration name."""
    mock_load.return_value = None
    with patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: ""}
        )
        assert result["type"] == FlowResultType.FORM
        assert CONF_NAME in result["errors"]


@pytest.mark.asyncio
@patch("homeassistant.config_entries._load_integration", new_callable=AsyncMock)
async def test_invalid_dog_id(mock_load, hass: HomeAssistant) -> None:
    """Test submitting an invalid dog ID."""
    mock_load.return_value = None
    with patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Paw Setup"}
        )
        flow_id = result["flow_id"]
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_DOG_ID: "INVALID ID", CONF_DOG_NAME: "Fido"}
        )
        assert result["type"] == FlowResultType.FORM
        assert CONF_DOG_ID in result["errors"]


@pytest.mark.asyncio
@patch("homeassistant.config_entries._load_integration", new_callable=AsyncMock)
async def test_add_second_dog(mock_load, hass: HomeAssistant) -> None:
    """Test adding a second dog in the flow."""
    mock_load.return_value = None
    with patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Paw Setup"}
        )
        flow_id = result["flow_id"]

        # First dog
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_DOG_ID: "fido", CONF_DOG_NAME: "Fido"}
        )
        assert result["step_id"] == "dog_modules"
        result = await hass.config_entries.flow.async_configure(flow_id, {})
        assert result["step_id"] == "add_another"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"add_another": True}
        )
        assert result["step_id"] == "add_dog"

        # Second dog
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_DOG_ID: "spot", CONF_DOG_NAME: "Spot"}
        )
        assert result["step_id"] == "dog_modules"
        result = await hass.config_entries.flow.async_configure(flow_id, {})
        assert result["step_id"] == "add_another"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"add_another": False}
        )
        assert result["step_id"] == "entity_profile"
        result = await hass.config_entries.flow.async_configure(
            flow_id, {"entity_profile": "standard"}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert len(result["data"][CONF_DOGS]) == 2


@pytest.mark.asyncio
@patch("homeassistant.loader.async_get_integration", new_callable=AsyncMock)
@patch("homeassistant.config_entries._load_integration", new_callable=AsyncMock)
async def test_unique_id_conflict(
    mock_load, mock_get_integration, hass: HomeAssistant
) -> None:
    """Test abort when the integration is already configured."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="paw_setup")
    entry.add_to_hass(hass)
    mock_load.return_value = None
    mock_get_integration.return_value = AsyncMock()
    with patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_abort_no_dogs(hass: HomeAssistant) -> None:
    """Test aborting final setup when no dogs configured."""
    with (
        patch(
            "homeassistant.config_entries._load_integration",
            new=AsyncMock(return_value=None),
        ),
        patch.dict(config_entries.HANDLERS, {DOMAIN: PawControlConfigFlow}),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        # Configure through normal flow to reach final_setup with no dogs
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_NAME: "Test"}
        )
        # Skip adding dogs and go directly to final setup
        flow = hass.config_entries.flow._progress[result["flow_id"]]
        flow._dogs = []  # Ensure no dogs
        result = await flow.async_step_final_setup()
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "no_dogs_configured"
