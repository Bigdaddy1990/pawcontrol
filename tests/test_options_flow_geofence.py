import pytest
pytestmark = pytest.mark.asyncio

async def test_options_flow_geofence_triggers_reload(hass, monkeypatch):
    import custom_components.pawcontrol as comp
    from custom_components.pawcontrol import config_flow as cf
    from homeassistant.config_entries import ConfigEntry

    entry = ConfigEntry(version=1, domain=comp.DOMAIN, title="Paw", data={}, source="user", entry_id="opt1", options={})
    await comp.async_setup_entry(hass, entry)

    reloaded = {"count": 0}
    async def fake_reload(entry_id):
        reloaded["count"] += 1
        return True
    monkeypatch.setattr(hass.config_entries, "async_reload", fake_reload, raising=True)

    flow = await cf.async_get_options_flow(entry)
    flow.hass = hass

    res = await flow.async_step_init()
    assert res["type"] == "form"

    data = {"home_lat": "50.0", "home_lon": "8.0", "geofence_radius_m": 120.0, "auto_prune_devices": True}
    res2 = await flow.async_step_geofence(data)
    assert res2["type"] == "create_entry"

    hass.config_entries.async_update_entry(entry, options=data)
    assert reloaded["count"] >= 1
