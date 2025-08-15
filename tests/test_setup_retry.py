import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_setup_retry_on_initial_refresh(hass, monkeypatch):
    """If the coordinator initial refresh fails, integration should raise ConfigEntryNotReady."""
    # Arrange: minimal environment
    import custom_components.pawcontrol as comp

    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="test123")
    entry.add_to_hass(hass)

    # Spy to capture created coordinator and make its first refresh fail

    real_setup_entry = comp.async_setup_entry

    async def fake_setup_entry(hass, entry):
        # Run the real setup to create the coordinator in hass.data
        result = await real_setup_entry(hass, entry)
        # Patch the coordinator method afterwards to simulate failure on first refresh
        coord = hass.data[comp.DOMAIN][entry.entry_id].get("coordinator")
        assert coord is not None

        async def boom():
            raise RuntimeError("temporary backend offline")

        monkeypatch.setattr(
            coord, "async_config_entry_first_refresh", boom, raising=True
        )
        # Now call setup again and expect retry
        with pytest.raises(ConfigEntryNotReady):
            await real_setup_entry(hass, entry)
        return result

    # Act / Assert
    await fake_setup_entry(hass, entry)
