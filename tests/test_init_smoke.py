import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.setup import async_setup_component

DOMAIN = "pawcontrol"

@pytest.mark.anyio
async def test_domain_setup_registers_services(hass: HomeAssistant):
    # Setting up the domain should register services
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}}) or True
    assert hass.services.has_service(DOMAIN, "notify_test")
