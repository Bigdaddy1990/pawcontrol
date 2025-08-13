import pytest

async def test_reauth_updates_entry(hass):
    import custom_components.pawcontrol.config_flow as cf
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        domain="pawcontrol",
        title="Paw",
        data={"api_key": "oldkey"},
        source="user",
        entry_id="test123",
        options={},
    )
    hass.config_entries._entries.append(entry)
    flow = cf.ConfigFlow()
    flow.hass = hass
    flow.context = {"entry_id": entry.entry_id}
    result = await flow.async_step_reauth()
    assert result["type"] == "form"
    result2 = await flow.async_step_reauth({"api_key": "newkey123"})
    assert result2["type"] == "abort"
    assert hass.config_entries.async_get_entry(entry.entry_id).data["api_key"] == "newkey123"
