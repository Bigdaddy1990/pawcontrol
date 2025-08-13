import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_reauth_updates_entry(hass):
    import custom_components.pawcontrol.config_flow as cf

    entry = MockConfigEntry(
        domain="pawcontrol",
        data={"api_key": "oldkey"},
        options={},
        entry_id="test123",
    )
    entry.add_to_hass(hass)
    flow = cf.ConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}
    result = await flow.async_step_reauth()
    assert result["type"] == "form"
    result2 = await flow.async_step_reauth({"api_key": "newkey123"})
    assert result2["type"] == "abort"
    assert (
        hass.config_entries.async_get_entry(entry.entry_id).data["api_key"]
        == "newkey123"
    )
