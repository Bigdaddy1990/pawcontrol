import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.exceptions import ServiceValidationError

DOMAIN = "pawcontrol"

@pytest.mark.anyio
async def test_service_validation_no_entries(hass: HomeAssistant):
    # Setup domain (registers services) but no config entry loaded
    await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "route_history_list", blocking=True)
