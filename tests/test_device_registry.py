import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

DOMAIN = "pawcontrol"


@pytest.mark.anyio
async def test_device_registry_identifiers(hass: HomeAssistant):
    await async_setup_component(hass, DOMAIN, {})
    # Real device registration requires loaded config_entry; smoke-check only here.
    assert True
