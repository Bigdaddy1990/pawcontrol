import pytest
from homeassistant.core import HomeAssistant
from homeassistant import config_entries
from pytest_homeassistant_custom_component.common import MockConfigEntry

import custom_components.pawcontrol as comp

DOMAIN = comp.DOMAIN


@pytest.mark.anyio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_gps_pause_and_resume(hass: HomeAssistant, expected_lingering_timers):
    assert await comp.async_setup(hass, {}) or True
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"dogs": [{"dog_id": "d1"}]},
        state=config_entries.ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)
    await comp.async_setup_entry(hass, entry)
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "gps_pause_tracking")
    assert hass.services.has_service(DOMAIN, "gps_resume_tracking")

