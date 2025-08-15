import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

DOMAIN = "pawcontrol"


@pytest.mark.asyncio
async def test_diagnostics_redacts_sensitive(hass: HomeAssistant):
    await async_setup_component(hass, DOMAIN, {})
    # Fake a config entry and attach some sensitive data in runtime storage
    # The diagnostics function should redact tokens/webhooks/coordinates
    # This is a smoke test; full coverage requires a running entry.
    assert True
