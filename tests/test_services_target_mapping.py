import pytest
from homeassistant.exceptions import HomeAssistantError
pytestmark = pytest.mark.asyncio

async def test_service_wrapper_requires_target(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.core import ServiceCall

    # Register services via setup so wrappers exist
    from homeassistant.config_entries import ConfigEntry
    entry = ConfigEntry(version=1, domain=comp.DOMAIN, title="Paw", data={}, source="user", entry_id="e1", options={})
    await comp.async_setup_entry(hass, entry)

    # Wrapper resolve path should raise if no device/dog_id
    with pytest.raises(HomeAssistantError):
        # Build a fake service call with no target/dog_id
        call = ServiceCall(comp.DOMAIN, "gps_post_location", data={"latitude": 1.0, "longitude": 2.0, "accuracy": 5})
        await comp.handle_gps_post_location(call)
