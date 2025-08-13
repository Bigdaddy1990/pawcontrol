import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_invalid_geofence_fix_starts_options_flow(hass, monkeypatch):
    import custom_components.pawcontrol as comp
    from custom_components.pawcontrol import repairs as rep

    entry = MockConfigEntry(domain=comp.DOMAIN, data={}, options={}, entry_id="r1")
    entry.add_to_hass(hass)
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
