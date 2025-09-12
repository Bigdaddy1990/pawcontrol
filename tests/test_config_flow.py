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
async def hass(tmp_path):
    """Provide a minimal Home Assistant instance for tests."""
    hass = HomeAssistant(str(tmp_path))
    hass.data[DATA_COMPONENTS] = set()
    hass.data[DATA_INTEGRATIONS] = {}
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    await hass.async_start()
    try:
        yield hass
    finally:
        await hass.async_stop()


@pytest.mark.asyncio
async def test_full_config_flow(hass):
    """Test a full successful config flow."""
    init = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert init["type"] == FlowResultType.FORM
    assert init["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        init["flow_id"], {CONF_NAME: "Paw Setup"}
    )
    flow_id = result["flow_id"]
    flow = hass.config_entries.flow._progress[flow_id].handler
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
    assert result["title"].startswith("Paw Setup (")
    assert result["data"]["name"] == "Paw Setup"
    assert result["data"][CONF_DOGS][0][CONF_DOG_ID] == "fido"
    assert result["data"][CONF_DOGS][0][CONF_DOG_NAME] == "Fido"
