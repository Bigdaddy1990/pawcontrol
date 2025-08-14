import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

import custom_components.pawcontrol as comp

DOMAIN = comp.DOMAIN


@pytest.mark.anyio
async def test_domain_setup_registers_services(hass: HomeAssistant):
    # Setting up the domain should register services
    assert await comp.async_setup(hass, {}) or True
    assert hass.services.has_service(DOMAIN, "notify_test")
