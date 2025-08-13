import pytest

pytestmark = pytest.mark.asyncio


async def test_invalid_geofence_fix_starts_options_flow(hass, monkeypatch):
    import custom_components.pawcontrol as comp
    from custom_components.pawcontrol import repairs as rep
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="r1",
        options={},
    )
    await comp.async_setup_entry(hass, entry)

    started = {"count": 0}

    async def fake_init(entry_id, context=None):
        started["count"] += 1
        return {"type": "form", "flow_id": "x"}

    monkeypatch.setattr(
        hass.config_entries.options, "async_init", fake_init, raising=True
    )

    flow = rep.InvalidGeofenceRepairFlow()
    flow.hass = hass
    result = await flow.async_step_init(user_input={})
    assert result["type"] == "create_entry"
    assert started["count"] == 1
