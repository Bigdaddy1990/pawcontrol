import pytest

pytestmark = pytest.mark.asyncio


async def test_invalid_geofence_creates_issue(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.helpers import issue_registry as ir

    entry = ConfigEntry(
        version=1,
        domain=comp.DOMAIN,
        title="Paw",
        data={},
        source="user",
        entry_id="g1",
        options={"geofence_radius_m": 0, "home_lat": 50.0},
    )
    await comp.async_setup_entry(hass, entry)

    reg = ir.async_get(hass)
    issues = [
        i
        for i in reg.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "invalid_geofence"
    ]
    assert issues, "Expected invalid_geofence issue"
