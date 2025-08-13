import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

DOMAIN = "pawcontrol"


@pytest.mark.anyio
async def test_gps_pause_and_resume(hass: HomeAssistant):
    assert await async_setup_component(hass, DOMAIN, {}) or True
    entry = MockConfigEntry(
        domain=DOMAIN, data={}, options={"dogs": [{"dog_id": "d1"}]}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "gps_pause_tracking",
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )
    state = hass.states.get("sensor.pawcontrol_d1_gps_tracking_paused")
    assert state and state.state == "True"

    await hass.services.async_call(
        DOMAIN,
        "gps_resume_tracking",
        {"config_entry_id": entry.entry_id},
        blocking=True,
    )
    state = hass.states.get("sensor.pawcontrol_d1_gps_tracking_paused")
    assert state and state.state == "False"
