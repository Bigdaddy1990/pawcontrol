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
from homeassistant.loader import DATA_COMPONENTS, DATA_INTEGRATIONS


@pytest_asyncio.fixture
async def hass():
    """Provide a minimal Home Assistant instance for tests."""
    hass = HomeAssistant("/tmp")
    hass.data[DATA_COMPONENTS] = set()
    hass.data[DATA_INTEGRATIONS] = {}
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    yield hass


@pytest.mark.asyncio
async def test_full_config_flow(hass):
    """Test a full successful config flow."""
    flow = PawControlConfigFlow()
    flow.hass = hass
    flow.context = {}

    result = await flow.async_step_user()
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await flow.async_step_user({CONF_NAME: "Paw Setup"})
    assert result["step_id"] == "add_dog"

    result = await flow.async_step_add_dog(
        {
            CONF_DOG_ID: "fido",
            CONF_DOG_NAME: "Fido",
        }
    )
    assert result["step_id"] == "dog_modules"

    result = await flow.async_step_dog_modules({})
    assert result["step_id"] == "add_another"

    result = await flow.async_step_add_another({"add_another": False})
    assert result["step_id"] == "entity_profile"

    result = await flow.async_step_entity_profile({"entity_profile": "standard"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Paw Setup (Standard (12 entities))"
    assert result["data"]["name"] == "Paw Setup"
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "fido"
    assert result["data"][CONF_DOGS][0][CONF_DOG_NAME] == "Fido"
