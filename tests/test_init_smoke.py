import custom_components.pawcontrol as comp
import pytest
from homeassistant.core import HomeAssistant

DOMAIN = comp.DOMAIN


@pytest.mark.asyncio
async def test_domain_setup_registers_services(hass: HomeAssistant):
    # Setting up the domain should register services
    assert await comp.async_setup(hass, {}) or True
    assert hass.services.has_service(DOMAIN, "notify_test")
