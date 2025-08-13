import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytestmark = pytest.mark.asyncio


async def test_invalid_geofence_creates_issue(hass):
    import custom_components.pawcontrol as comp
    from homeassistant.helpers import issue_registry as ir

    entry = MockConfigEntry(
        domain=comp.DOMAIN,
        data={},
        options={"geofence_radius_m": 0, "home_lat": 50.0},
        entry_id="g1",
    )
    entry.add_to_hass(hass)
    await comp.async_setup_entry(hass, entry)

    reg = ir.async_get(hass)
    issues = [
        i
        for i in reg.issues.values()
        if i.domain == comp.DOMAIN and i.issue_id == "invalid_geofence"
    ]
    assert issues, "Expected invalid_geofence issue"
